from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from graphene.hashing import canonical_json_sha256
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import (
    PromotionCheckpointError,
    PromotionConflict,
    PromotionEvidenceError,
    PromotionReceiptV2,
    PromotionRequest,
    PromotionRetestError,
    PromotionRetestRequest,
    PromotionRetestResult,
    SQLiteCheckpointRecorder,
    promote,
)
from graphene.lineage.lineage_reducer import reduce_events
from graphene.lineage.sqlite_lineage_store import SQLiteLineageStore
from graphene.core_models import (
    EventInput,
    EvidenceKind,
    EvidenceReference,
    HeadCheckpoint,
    HumanDecision,
    LineageAuthority,
    LineageEventType,
    LineageRunState,
    MemoryDecisionValue,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from pydantic import ValidationError

RUN_ID = "run_promotion_001"
BASE_SHA = "a" * 40


def _head(event):
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _source(artifacts, evidence_kind, source_kind, record):
    reference = artifacts(evidence_kind, record)
    return SourceReference(
        kind=source_kind,
        id=reference.id,
        sha256=reference.sha256,
    )


class _Checkpoints:
    def __init__(self):
        self.values: list[HeadCheckpoint] = []

    def __call__(self, checkpoint):
        self.values.append(checkpoint)

    def read(self, run_id):
        return tuple(self.values) if run_id == RUN_ID else ()


class _DroppedCheckpoints:
    def __call__(self, checkpoint):
        pass

    def read(self, run_id):
        return ()


class Harness:
    def __init__(self, tmp_path: Path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.path = tmp_path / "promotion.sqlite3"
        self.artifacts = SQLiteArtifactStore(self.path)
        self.checkpoint = _Checkpoints()
        self.checkpoints = self.checkpoint.values
        self.store = SQLiteLineageStore(
            self.path,
            artifact_resolver=self.artifacts.resolve,
            checkpoint_reader=self.checkpoint.read,
        )
        empty = VerifiedHead(
            run_id=RUN_ID,
            seq=0,
            event_sha256=None,
            event_count=0,
        )
        started = self.store.append(
            RUN_ID,
            empty,
            "promotion_start_key_001",
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.RUN_STARTED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.LIFECYCLE_SERVICE,
                references=(),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.OPERATOR_REQUEST,
                    SourceKind.LIFECYCLE_REQUEST,
                    {"schema_version": 2, "action": "start"},
                ),
                payload={"state": "STARTING"},
            ),
        )
        attempted = self.store.append(
            RUN_ID,
            _head(started),
            "promotion_attempted_key_001",
            EventInput(
                session_id="session_promotion_001",
                invocation_id="invocation_promotion_001",
                model_id="model-test",
                tool_call_id="call_completion_001",
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.COMPLETION_ATTEMPTED,
                truth_kind=TruthKind.MODEL_PROPOSED,
                authority=LineageAuthority.LOCAL_ADAPTER,
                references=(),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.LOCAL_ADAPTER_RECEIPT,
                    SourceKind.LOCAL_ADAPTER_RECEIPT,
                    {"schema_version": 2, "action": "attempt_completion"},
                ),
                payload={
                    "adapter_kind": "local",
                    "operation": "request_completion",
                    "status": "attempted",
                },
            ),
        )
        denied = self.store.append(
            RUN_ID,
            _head(attempted),
            "promotion_denied_key_001",
            EventInput(
                session_id="session_promotion_001",
                invocation_id="invocation_promotion_001",
                model_id="model-test",
                tool_call_id="call_completion_001",
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.COMPLETION_DENIED,
                truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                authority=LineageAuthority.POLICY_ENGINE,
                references=(
                    EvidenceReference(
                        kind=EvidenceKind.EVENT,
                        id=attempted.event_id,
                        sha256=attempted.event_sha256,
                    ),
                ),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.POLICY_RECEIPT,
                    SourceKind.POLICY_EVALUATION,
                    {"schema_version": 2, "action": "deny_completion"},
                ),
                payload={
                    "operation": "request_completion",
                    "reason_code": "human_promotion_required",
                    "state": "NEEDS_HUMAN",
                    "status": "denied",
                },
            ),
        )
        self.expected = _head(denied)
        candidate = self.artifacts(
            EvidenceKind.EVIDENCE_BLOB,
            {"schema_version": 2, "candidate": "candidate-1"},
        )
        changeset = self.artifacts(
            EvidenceKind.CHANGESET,
            {"schema_version": 2, "changeset": "changeset-1"},
        )
        test = self.artifacts(
            EvidenceKind.TEST_RECEIPT,
            {"schema_version": 2, "passed": True},
        )
        brief = self.artifacts(
            EvidenceKind.CONTEXT_BRIEF,
            {"schema_version": 2, "brief": "brief-1"},
        )
        decision = self.artifacts(
            EvidenceKind.HANDOFF_DECISION,
            {"schema_version": 2, "decision": "allowed"},
        )
        memory = self.artifacts(
            EvidenceKind.MEMORY_REVISION,
            {"schema_version": 2, "memory": "approved"},
        )
        patch_sha = "1" * 64
        tree_sha = "2" * 64
        test_sha = test.sha256
        brief_sha = brief.sha256
        decision_sha = decision.sha256
        memory_sha = memory.sha256
        memory_event = self.store.append(
            RUN_ID,
            self.expected,
            "promotion_memory_key_001",
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.MEMORY_APPROVED,
                truth_kind=TruthKind.HUMAN_ATTESTED,
                authority=LineageAuthority.OPERATOR_REQUEST,
                references=(memory,),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.OPERATOR_REQUEST,
                    SourceKind.OPERATOR_REQUEST,
                    {"schema_version": 2, "action": "approve_memory"},
                ),
                payload={
                    "decision_id": "memory_decision_001",
                    "memory_id": "memory_auth_001",
                    "memory_sha256": memory_sha,
                    "revision": 1,
                    "status": "approved",
                },
            ),
        )
        context_event = self.store.append(
            RUN_ID,
            _head(memory_event),
            "promotion_context_key_001",
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.CONTEXT_COMPILED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.CONTEXT_COMPILER,
                references=(decision, brief),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.HANDOFF_DECISION,
                    SourceKind.CONTEXT_COMPILER_RECEIPT,
                    {"schema_version": 2, "action": "compile_context"},
                ),
                payload={
                    "brief_artifact_sha256": brief.sha256,
                    "brief_sha256": brief_sha,
                    "candidate_set_sha256": "c" * 64,
                    "decision_artifact_sha256": decision.sha256,
                    "decision_sha256": decision_sha,
                    "source_graph_sha256": "d" * 64,
                    "status": "compiled",
                },
            ),
        )
        changeset_event = self.store.append(
            RUN_ID,
            _head(context_event),
            "promotion_changeset_key_001",
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.CHANGESET_PARSED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.ARTIFACT_PARSER,
                references=(changeset,),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.CHANGESET,
                    SourceKind.REDUCER_RECEIPT,
                    {"schema_version": 2, "action": "parse_changeset"},
                ),
                payload={
                    "candidate_patch_sha256": patch_sha,
                    "changed_paths": [
                        "app/auth/limiter.py",
                        "tests/test_security_policy.py",
                    ],
                    "changeset_id": changeset.id,
                    "hunk_count": 2,
                    "status": "parsed",
                },
            ),
        )
        test_event = self.store.append(
            RUN_ID,
            _head(changeset_event),
            "promotion_test_key_001",
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.TEST_RECEIPT_CREATED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.ARTIFACT_PARSER,
                references=(test,),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.TEST_RECEIPT,
                    SourceKind.REDUCER_RECEIPT,
                    {"schema_version": 2, "action": "record_test"},
                ),
                payload={
                    "bound_paths": [
                        "app/auth/limiter.py",
                        "tests/test_security_policy.py",
                    ],
                    "passed": True,
                    "receipt_id": test.id,
                    "receipt_sha256": test_sha,
                    "status": "created",
                },
            ),
        )
        candidate_event = self.store.append(
            RUN_ID,
            _head(test_event),
            "promotion_candidate_key_001",
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.CANDIDATE_CREATED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.ARTIFACT_PARSER,
                references=(candidate, changeset, test, brief, decision, memory),
                source_ref=_source(
                    self.artifacts,
                    EvidenceKind.EVIDENCE_BLOB,
                    SourceKind.REDUCER_RECEIPT,
                    {"schema_version": 2, "action": "candidate_created"},
                ),
                payload={
                    "candidate_id": candidate.id,
                    "candidate_patch_sha256": patch_sha,
                    "candidate_tree_sha256": tree_sha,
                    "candidate_tree_hash_version": "graphene.tree.v2",
                    "changed_path_count": 2,
                    "status": "created",
                },
            ),
        )
        self.expected = _head(candidate_event)
        approval = HumanDecision(
            decision_id="human_promotion_001",
            value=MemoryDecisionValue.APPROVE,
            purpose="promotion",
            bound_digest=patch_sha,
            occurred_at=datetime(2026, 8, 12, 18, tzinfo=UTC),
        )
        self.request = PromotionRequest(
            run_id=RUN_ID,
            expected_head=self.expected,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            candidate_id=candidate.id,
            candidate_sha256=candidate.sha256,
            candidate_patch_sha256=patch_sha,
            candidate_tree_sha256=tree_sha,
            candidate_tree_hash_version="graphene.tree.v2",
            changeset_sha256=changeset.sha256,
            test_receipt_sha256=test_sha,
            brief_sha256=brief_sha,
            decision_sha256=decision_sha,
            memory_sha256=memory_sha,
            candidate_reference=candidate,
            changeset_reference=changeset,
            test_reference=test,
            brief_reference=brief,
            decision_reference=decision,
            memory_reference=memory,
            human_approval=approval,
        )

    def receipt(self, retest, **changes):
        values = {
            "authoritative_test_receipt_sha256": "3" * 64,
            "retest_base_sha": "b" * 40,
            "passed": True,
            "timed_out": False,
            **changes,
        }
        return PromotionRetestResult.model_validate(values)

    def events(self):
        head = self.store.verify(RUN_ID)
        assert isinstance(head, VerifiedHead)
        return self.store.tail(RUN_ID, 0, head.seq)


def test_exact_non_circular_sequence_and_precommit_checkpoint(tmp_path):
    harness = Harness(tmp_path)
    observed = []

    def reconstruct(retest):
        observed.append("callback")
        assert harness.store.verify(RUN_ID) == retest.approval_head
        assert harness.events()[-1].event_type == LineageEventType.PROMOTION_APPROVED
        assert not harness.checkpoints
        return harness.receipt(retest)

    outcome = promote(
        harness.store,
        harness.request,
        record_artifact=harness.artifacts,
        reconstruct_and_retest=reconstruct,
        record_checkpoint=harness.checkpoint,
    )
    events = harness.events()

    assert observed == ["callback"]
    assert [event.event_type for event in events[-2:]] == [
        LineageEventType.PROMOTION_APPROVED,
        LineageEventType.PROMOTION_COMPLETED,
    ]
    assert outcome.approval_event.seq == harness.expected.seq + 1
    assert outcome.receipt.approval_head == _head(outcome.approval_event)
    assert outcome.completion_event.seq == harness.expected.seq + 2
    assert outcome.completion_event.references[:2] == (
        outcome.completion_event.references[0],
        outcome.receipt_reference,
    )
    assert len(outcome.completion_event.references) == 3
    checkpoint_reference = outcome.completion_event.references[2]
    assert checkpoint_reference.kind == EvidenceKind.CHECKPOINT
    assert checkpoint_reference.sha256 == canonical_json_sha256(
        outcome.checkpoint.model_dump(mode="json")
    )
    assert outcome.approval_event.authority == LineageAuthority.OPERATOR_REQUEST
    assert outcome.approval_event.truth_kind == TruthKind.HUMAN_ATTESTED
    assert outcome.approval_event.source_ref.kind == SourceKind.OPERATOR_REQUEST
    assert outcome.completion_event.source_ref.kind == SourceKind.PROMOTION_RECEIPT
    assert harness.checkpoints == [outcome.checkpoint]
    assert outcome.checkpoint.expected_seq == outcome.approval_event.seq
    assert outcome.checkpoint.event_head_sha256 == outcome.approval_event.event_sha256
    assert outcome.checkpoint.bound_artifact_id == outcome.receipt_reference.id
    assert harness.store.verify(RUN_ID) == outcome.final_head
    assert reduce_events(events).state == LineageRunState.PROMOTED


def test_sqlite_checkpoint_exact_replay_and_read_only_restart(tmp_path):
    harness = Harness(tmp_path)
    checkpoints = SQLiteCheckpointRecorder(harness.path)
    outcome = promote(
        harness.store,
        harness.request,
        record_artifact=harness.artifacts,
        reconstruct_and_retest=harness.receipt,
        record_checkpoint=checkpoints,
    )

    checkpoints(outcome.checkpoint)
    assert checkpoints.read(RUN_ID) == (outcome.checkpoint,)
    read_only_checkpoints = SQLiteCheckpointRecorder(harness.path, read_only=True)
    read_only_artifacts = SQLiteArtifactStore(harness.path, read_only=True)
    restarted = SQLiteLineageStore(
        harness.path,
        artifact_resolver=read_only_artifacts.resolve,
        checkpoint_reader=read_only_checkpoints.read,
        read_only=True,
    )
    assert restarted.verify(RUN_ID) == outcome.final_head
    assert reduce_events(restarted.tail(RUN_ID, 0, outcome.final_head.seq)).state == (
        LineageRunState.PROMOTED
    )


@pytest.mark.parametrize(
    "field",
    (
        "candidate_sha256",
        "candidate_patch_sha256",
        "candidate_tree_sha256",
        "changeset_sha256",
        "test_receipt_sha256",
        "brief_sha256",
        "decision_sha256",
        "memory_sha256",
    ),
)
def test_substituted_retest_binding_is_denied_and_never_completed(tmp_path, field):
    harness = Harness(tmp_path)

    def forged(retest):
        bindings = retest.model_dump(mode="json")
        bindings[field] = "f" * 64
        return PromotionReceiptV2.create(
            **bindings,
            receipt_id="promotion_receipt_forged",
            authoritative_test_receipt_sha256="3" * 64,
            retest_base_sha="b" * 40,
            passed=True,
            timed_out=False,
        )

    with pytest.raises(PromotionRetestError, match="core-owned"):
        promote(
            harness.store,
            harness.request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=forged,
            record_checkpoint=harness.checkpoint,
        )

    assert [event.event_type for event in harness.events()[-2:]] == [
        LineageEventType.PROMOTION_APPROVED,
        LineageEventType.PROMOTION_DENIED,
    ]
    assert not harness.checkpoints


def test_callback_failure_and_nonpassing_receipt_fail_closed(tmp_path):
    first = Harness(tmp_path / "callback")

    def fail(_):
        raise RuntimeError("private callback failure")

    with pytest.raises(PromotionRetestError, match="reconstruction"):
        promote(
            first.store,
            first.request,
            record_artifact=first.artifacts,
            reconstruct_and_retest=fail,
            record_checkpoint=first.checkpoint,
        )
    assert first.events()[-1].event_type == LineageEventType.PROMOTION_DENIED

    second = Harness(tmp_path / "retest")

    def nonpassing(retest):
        return PromotionRetestResult(
            authoritative_test_receipt_sha256="3" * 64,
            retest_base_sha="b" * 40,
            passed=False,
            timed_out=False,
        )

    with pytest.raises(PromotionRetestError, match="did not pass"):
        promote(
            second.store,
            second.request,
            record_artifact=second.artifacts,
            reconstruct_and_retest=nonpassing,
            record_checkpoint=second.checkpoint,
        )
    assert second.events()[-1].event_type == LineageEventType.PROMOTION_DENIED

    third = Harness(tmp_path / "digest")

    def bad_digest(retest):
        return PromotionRetestResult.model_construct(
            authoritative_test_receipt_sha256="not-a-digest",
            retest_base_sha="b" * 40,
            passed=True,
            timed_out=False,
        )

    with pytest.raises(PromotionRetestError, match="core-owned"):
        promote(
            third.store,
            third.request,
            record_artifact=third.artifacts,
            reconstruct_and_retest=bad_digest,
            record_checkpoint=third.checkpoint,
        )
    assert third.events()[-1].event_type == LineageEventType.PROMOTION_DENIED


def test_stale_and_concurrent_heads_never_complete(tmp_path):
    stale = Harness(tmp_path / "stale")
    concurrent_source = _source(
        stale.artifacts,
        EvidenceKind.POLICY_RECEIPT,
        SourceKind.POLICY_EVALUATION,
        {"schema_version": 2, "action": "concurrent"},
    )
    stale.store.append(
        RUN_ID,
        stale.expected,
        "promotion_concurrent_key_001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.PROMOTION_DENIED,
            truth_kind=TruthKind.POLICY_AUTHORITATIVE,
            authority=LineageAuthority.POLICY_ENGINE,
            references=(),
            source_ref=concurrent_source,
            payload={
                "candidate_patch_sha256": stale.request.candidate_patch_sha256,
                "reason_code": "concurrent",
                "status": "denied",
            },
        ),
    )
    with pytest.raises(PromotionConflict, match="stale"):
        promote(
            stale.store,
            stale.request,
            record_artifact=stale.artifacts,
            reconstruct_and_retest=stale.receipt,
            record_checkpoint=stale.checkpoint,
        )

    race = Harness(tmp_path / "race")

    def concurrent(retest):
        source = _source(
            race.artifacts,
            EvidenceKind.POLICY_RECEIPT,
            SourceKind.POLICY_EVALUATION,
            {"schema_version": 2, "action": "race"},
        )
        race.store.append(
            RUN_ID,
            retest.approval_head,
            "promotion_race_key_001",
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id="graphene-demo",
                base_sha=BASE_SHA,
                agent_profile_id="auth-maintainer@1",
                policy_revision=1,
                event_type=LineageEventType.PROMOTION_DENIED,
                truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                authority=LineageAuthority.POLICY_ENGINE,
                references=(),
                source_ref=source,
                payload={
                    "candidate_patch_sha256": race.request.candidate_patch_sha256,
                    "reason_code": "concurrent",
                    "status": "denied",
                },
            ),
        )
        return race.receipt(retest)

    with pytest.raises(PromotionConflict, match="stale"):
        promote(
            race.store,
            race.request,
            record_artifact=race.artifacts,
            reconstruct_and_retest=concurrent,
            record_checkpoint=race.checkpoint,
        )
    assert LineageEventType.PROMOTION_COMPLETED not in {
        event.event_type for event in race.events()
    }


def test_checkpoint_failure_never_returns_success(tmp_path):
    harness = Harness(tmp_path)

    with pytest.raises(PromotionCheckpointError, match="not retained"):
        promote(
            harness.store,
            harness.request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=harness.receipt,
            record_checkpoint=_DroppedCheckpoints(),
        )

    assert harness.events()[-1].event_type == LineageEventType.PROMOTION_APPROVED
    assert not harness.checkpoints
    assert reduce_events(harness.events()).state == LineageRunState.NEEDS_HUMAN


def test_checkpoint_failure_retries_the_exact_retained_approval(tmp_path):
    harness = Harness(tmp_path)
    calls = 0

    def retest(request):
        nonlocal calls
        calls += 1
        return harness.receipt(request)

    with pytest.raises(PromotionCheckpointError):
        promote(
            harness.store,
            harness.request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=retest,
            record_checkpoint=_DroppedCheckpoints(),
        )

    outcome = promote(
        harness.store,
        harness.request,
        record_artifact=harness.artifacts,
        reconstruct_and_retest=retest,
        record_checkpoint=harness.checkpoint,
    )

    assert calls == 2
    assert outcome.completion_event.event_type == LineageEventType.PROMOTION_COMPLETED
    assert reduce_events(harness.events()).state == LineageRunState.PROMOTED


def test_request_and_receipt_types_are_strict_and_human_only(tmp_path):
    harness = Harness(tmp_path)
    values = harness.request.model_dump(mode="json")
    with pytest.raises(ValidationError):
        PromotionRequest.model_validate({**values, "unexpected": True})
    with pytest.raises(ValidationError, match="human approval"):
        PromotionRequest.model_validate(
            {
                **values,
                "human_approval": {
                    **values["human_approval"],
                    "purpose": "memory",
                },
            }
        )
    simulated = PromotionRequest.model_validate(
        {
            **values,
            "human_approval": {
                **values["human_approval"],
                "actor": "simulated_fixture",
            },
        }
    )
    with pytest.raises(PromotionConflict, match="explicitly enabled"):
        promote(
            harness.store,
            simulated,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=harness.receipt,
            record_checkpoint=harness.checkpoint,
        )
    approval_head = VerifiedHead(
        run_id=RUN_ID,
        seq=harness.expected.seq + 1,
        event_sha256="4" * 64,
        event_count=harness.expected.seq + 1,
    )
    retest = PromotionRetestRequest(
        run_id=RUN_ID,
        approval_head=approval_head,
        approval_event_id="event_approval_001",
        approval_event_sha256="4" * 64,
        repo_id=harness.request.repo_id,
        base_sha=harness.request.base_sha,
        agent_profile_id=harness.request.agent_profile_id,
        policy_revision=harness.request.policy_revision,
        candidate_id=harness.request.candidate_id,
        candidate_sha256=harness.request.candidate_sha256,
        candidate_patch_sha256=harness.request.candidate_patch_sha256,
        candidate_tree_sha256=harness.request.candidate_tree_sha256,
        candidate_tree_hash_version=harness.request.candidate_tree_hash_version,
        changeset_sha256=harness.request.changeset_sha256,
        test_receipt_sha256=harness.request.test_receipt_sha256,
        brief_sha256=harness.request.brief_sha256,
        decision_sha256=harness.request.decision_sha256,
        memory_sha256=harness.request.memory_sha256,
        human_approval_sha256=canonical_json_sha256(
            harness.request.human_approval.model_dump(mode="json")
        ),
        artifact_references=(
            harness.request.candidate_reference,
            harness.request.changeset_reference,
            harness.request.test_reference,
            harness.request.brief_reference,
            harness.request.decision_reference,
            harness.request.memory_reference,
        ),
    )
    result = harness.receipt(retest)
    with pytest.raises(ValidationError):
        PromotionRetestResult.model_validate(
            {**result.model_dump(mode="json"), "unexpected": True}
        )
    receipt = PromotionReceiptV2.create(
        **retest.model_dump(mode="json"),
        receipt_id="promotion_receipt_strict",
        **result.model_dump(mode="json"),
    )
    with pytest.raises(ValidationError):
        PromotionReceiptV2.model_validate(
            {
                **receipt.model_dump(mode="json"),
                "unexpected": True,
            }
        )
    legacy = receipt.model_dump(mode="json")
    legacy["reconstructed_commit_sha"] = legacy.pop("retest_base_sha")
    legacy["receipt_sha256"] = canonical_json_sha256(
        {key: value for key, value in legacy.items() if key != "receipt_sha256"}
    )
    parsed = PromotionReceiptV2.model_validate(legacy)
    assert parsed.retest_base_sha is None
    assert parsed.legacy_reconstructed_commit_sha == "b" * 40
    assert parsed.receipt_sha256 == legacy["receipt_sha256"]
    with pytest.raises(ValueError, match="require retest_base_sha"):
        PromotionReceiptV2.create(**legacy)


@pytest.mark.parametrize(
    "field",
    (
        "candidate_sha256",
        "changeset_sha256",
        "test_receipt_sha256",
        "brief_sha256",
        "decision_sha256",
        "memory_sha256",
    ),
)
def test_request_rejects_one_byte_reference_digest_substitution(tmp_path, field):
    harness = Harness(tmp_path)
    values = harness.request.model_dump(mode="json")
    original = values[field]
    substituted = ("0" if original[0] != "0" else "1") + original[1:]

    with pytest.raises(ValidationError, match="artifact and head bindings"):
        PromotionRequest.model_validate({**values, field: substituted})


def test_candidate_artifacts_must_be_observed_before_the_bound_head(tmp_path):
    harness = Harness(tmp_path)
    head = harness.store.verify(RUN_ID)
    assert isinstance(head, VerifiedHead)
    events = harness.store.tail(RUN_ID, 0, head.seq)
    candidate_event = next(
        event
        for event in events
        if event.event_type == LineageEventType.CANDIDATE_CREATED
    )
    with harness.store._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM events WHERE event_id = ?",
            (candidate_event.event_id,),
        )
        previous = events[-2]
        connection.execute(
            "UPDATE run_heads SET seq = ?, event_sha256 = ?, event_count = ? "
            "WHERE run_id = ?",
            (previous.seq, previous.event_sha256, previous.seq, RUN_ID),
        )
        connection.commit()
    harness.request = PromotionRequest.model_validate(
        {
            **harness.request.model_dump(mode="json"),
            "expected_head": _head(previous).model_dump(mode="json"),
        }
    )

    with pytest.raises(PromotionEvidenceError, match="not bound"):
        promote(
            harness.store,
            harness.request,
            record_artifact=harness.artifacts,
            reconstruct_and_retest=harness.receipt,
            record_checkpoint=harness.checkpoint,
        )
