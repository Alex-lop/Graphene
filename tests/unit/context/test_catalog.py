from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest
from graphene.context.handoff import (
    AUTH_CAPABILITIES,
    HandoffCompileError,
    compile_verified_handoff,
    start_handoff,
)
from graphene.hashing import canonical_json_sha256
from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.sqlite_lineage_store import SQLiteLineageStore
from graphene.core_models import (
    EventInput,
    EvidenceKind,
    EvidenceReference,
    GoldenContract,
    GraphMvpContract,
    HumanDecision,
    LineageAuthority,
    LineageEventType,
    MemoryDecisionValue,
    MemoryRevision,
    MemoryState,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
GRAPH = GraphMvpContract.model_validate_json(
    (ROOT / "contracts/graph_mvp.json").read_text()
)
NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)
BASE_SHA = "a" * 40
EXCLUDED_CANARY = "EXCLUDED_HANDOFF_CANARY"


def _profile(profile_id: str):
    return next(item for item in GRAPH.catalog if item.agent_profile_id == profile_id)


def _head(run_id: str) -> VerifiedHead:
    return VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0)


def _event_head(event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _memory(run_id: str, suffix: str) -> MemoryRevision:
    spec = GOLDEN.memory
    proposed = MemoryRevision(
        memory_id=f"{spec.memory_id}_{suffix}",
        revision=spec.revision,
        state=MemoryState.PROPOSED,
        rule=spec.rule,
        repo_id=spec.repo_id,
        path_globs=spec.path_globs,
        task_tags=spec.task_tags,
        required_test_path=spec.required_test_path,
        required_check=spec.required_check,
        evidence_run_id=run_id,
        feedback_id=f"feedback_{suffix}",
    )
    decision = HumanDecision(
        decision_id=f"memory_decision_{suffix}",
        value=MemoryDecisionValue.APPROVE,
        purpose="memory",
        bound_digest=canonical_json_sha256(
            proposed.model_dump(mode="json", exclude={"state", "decision"})
        ),
        occurred_at=NOW,
    )
    return MemoryRevision.model_validate(
        {
            **proposed.model_dump(mode="json"),
            "state": MemoryState.APPROVED,
            "decision": decision,
        }
    )


def _seed_run(
    store: SQLiteLineageStore,
    artifacts: SQLiteArtifactStore,
    run_id: str,
    suffix: str,
    *,
    substituted_proposal: bool = False,
):
    started_source = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {"schema_version": 2, "action": "run.started", "run_id": run_id},
    )
    started = store.append(
        run_id,
        _head(run_id),
        f"seed_{suffix}_started_0001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id=GOLDEN.repo_id,
            base_sha=BASE_SHA,
            agent_profile_id="platform-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.RUN_STARTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=SourceReference(
                kind=SourceKind.LIFECYCLE_REQUEST,
                id=started_source.id,
                sha256=started_source.sha256,
            ),
            payload={"state": "STARTING"},
        ),
    )

    selected = artifacts(
        EvidenceKind.HUNK,
        {
            "schema_version": 2,
            "summary": f"Verified bounded Auth hunk {suffix}.",
            "content": f"private selected content {suffix}",
        },
    )
    excluded = artifacts(
        EvidenceKind.HUNK,
        {
            "schema_version": 2,
            "summary": EXCLUDED_CANARY,
            "content": EXCLUDED_CANARY,
        },
    )
    memory = _memory(run_id, suffix)
    memory_ref = artifacts(
        EvidenceKind.MEMORY_REVISION,
        memory.model_dump(mode="json"),
    )
    proposal_ref = None
    if substituted_proposal:
        proposal = MemoryRevision.model_validate(
            {
                **memory.model_dump(mode="json", exclude={"state", "decision"}),
                "state": MemoryState.PROPOSED,
                "decision": None,
                "rule": "Substituted memory content must not be ignored.",
            }
        )
        proposal_ref = artifacts(
            EvidenceKind.MEMORY_REVISION,
            proposal.model_dump(mode="json"),
        )
    approval_source = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {"schema_version": 2, "action": "memory.approved", "run_id": run_id},
    )
    approved = store.append(
        run_id,
        _event_head(started),
        f"seed_{suffix}_approved_0002",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id=GOLDEN.repo_id,
            base_sha=BASE_SHA,
            agent_profile_id="platform-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.MEMORY_APPROVED,
            truth_kind=TruthKind.HUMAN_ATTESTED,
            authority=LineageAuthority.OPERATOR_REQUEST,
            references=(
                EvidenceReference(
                    kind=EvidenceKind.EVENT,
                    id=started.event_id,
                    sha256=started.event_sha256,
                ),
                selected,
                excluded,
                memory_ref,
                *((proposal_ref,) if proposal_ref is not None else ()),
            ),
            source_ref=SourceReference(
                kind=SourceKind.OPERATOR_REQUEST,
                id=approval_source.id,
                sha256=approval_source.sha256,
            ),
            payload={
                "decision_id": memory.decision.decision_id,
                "memory_id": memory.memory_id,
                "memory_sha256": memory_ref.sha256,
                "revision": memory.revision,
                "status": "approved",
            },
        ),
    )
    return started, approved, selected, excluded, memory_ref


def _compile(store, artifacts, run_id: str, selected_id: str, **updates):
    values = {
        "store": store,
        "artifacts": artifacts,
        "decision_id": f"handoff_decision_{run_id}",
        "brief_id": f"brief_{run_id}",
        "source_run_id": run_id,
        "source_session_id": f"session_{run_id}",
        "source_graph_sha256": "f" * 64,
        "repo_id": GOLDEN.repo_id,
        "base_sha": BASE_SHA,
        "task": GOLDEN.tasks[1],
        "target_profile": _profile("auth-maintainer@1"),
        "target_profile_revision": 1,
        "policy_revision": 1,
        "selected_evidence_ids": (selected_id,),
        "policy_required_paths": (GOLDEN.memory.required_test_path,),
        "read_scope": ("app/auth/limiter.py", "tests/test_security_policy.py"),
        "write_scope": GOLDEN.tasks[1].expected_changed_paths,
        "capabilities": AUTH_CAPABILITIES,
        "fixed_test_profile": GRAPH.required_test_profile,
        "byte_caps": {"read": 32_768, "write": 32_768},
        "event_caps": {"run": 256},
        "server_recorded_at": NOW,
    }
    values.update(updates)
    return compile_verified_handoff(**values)


@pytest.fixture
def ledger(tmp_path: Path):
    database = tmp_path / "lineage.sqlite3"
    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    seeded = _seed_run(store, artifacts, "source_run", "source")
    return store, artifacts, seeded


def test_server_enumerates_complete_bound_universe_and_dependency_closure(ledger):
    store, artifacts, (started, approved, selected, excluded, memory_ref) = ledger
    orphan = artifacts(
        EvidenceKind.HUNK,
        {"schema_version": 2, "summary": "orphan", "content": "orphan"},
    )

    compiled = _compile(store, artifacts, "source_run", selected.id)
    assert compiled.brief is not None and compiled.denial is None
    entries = {item.id: item for item in compiled.decision.entries}
    assert {
        started.event_id,
        approved.event_id,
        selected.id,
        excluded.id,
        memory_ref.id,
    } <= set(entries)
    assert orphan.id not in entries
    assert entries[selected.id].include is True
    assert entries[approved.event_id].reason_code == "selected_evidence_dependency"
    assert entries[started.event_id].reason_code == "selected_evidence_dependency"
    assert entries[excluded.id].reason_code == "not_selected"
    assert tuple(item.evidence_id for item in compiled.brief.selected_evidence) == (
        selected.id,
    )
    assert tuple(item.memory_id for item in compiled.brief.approved_memories) == (
        GOLDEN.memory.memory_id + "_source",
    )
    assert EXCLUDED_CANARY not in compiled.brief.model_dump_json()
    assert (
        "source_candidates"
        not in inspect.signature(compile_verified_handoff).parameters
    )
    assert (
        "expected_source_candidate_set_sha256"
        not in inspect.signature(compile_verified_handoff).parameters
    )


def test_cross_run_selection_stale_head_and_artifact_substitution_fail_closed(ledger):
    store, artifacts, (_, _, selected, _, _) = ledger
    _, _, other_selected, _, _ = _seed_run(
        store,
        artifacts,
        "other_run",
        "other",
    )
    with pytest.raises(HandoffCompileError, match="absent"):
        _compile(store, artifacts, "source_run", other_selected.id)

    class StaleStore:
        def __init__(self):
            self.verifications = 0

        def verify(self, run_id):
            self.verifications += 1
            head = store.verify(run_id)
            if self.verifications == 1:
                return head
            assert isinstance(head, VerifiedHead)
            return VerifiedHead(
                run_id=run_id,
                seq=head.seq + 1,
                event_sha256="e" * 64,
                event_count=head.event_count + 1,
            )

        def tail(self, run_id, after_seq, limit):
            return store.tail(run_id, after_seq, limit)

    with pytest.raises(HandoffCompileError, match="head changed"):
        _compile(StaleStore(), artifacts, "source_run", selected.id)

    class SubstitutedArtifacts:
        def resolve(self, kind, artifact_id):
            if artifact_id == selected.id:
                return b'{"content":"substituted","schema_version":2}'
            return artifacts.resolve(kind, artifact_id)

    with pytest.raises(HandoffCompileError, match="unresolved"):
        _compile(store, SubstitutedArtifacts(), "source_run", selected.id)


def test_approved_memory_validates_every_referenced_revision(tmp_path: Path):
    database = tmp_path / "lineage.sqlite3"
    artifacts = SQLiteArtifactStore(database)
    store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    _, _, selected, _, _ = _seed_run(
        store,
        artifacts,
        "source_run",
        "source",
        substituted_proposal=True,
    )

    with pytest.raises(HandoffCompileError, match="event and artifact disagree"):
        _compile(store, artifacts, "source_run", selected.id)


def test_billing_denial_constructs_no_consumer_runtime(ledger):
    store, artifacts, (_, _, selected, _, _) = ledger
    billing = _compile(
        store,
        artifacts,
        "source_run",
        selected.id,
        target_profile=_profile("billing-observer@1"),
        capabilities=(),
    )
    counters = {
        "checkout": 0,
        "runtime": 0,
        "session": 0,
        "invocation": 0,
        "tool": 0,
        "dispatch": 0,
    }

    def forbidden_construction(_brief):
        for name in counters:
            counters[name] += 1
        raise AssertionError("Billing reached consumer construction")

    denied = start_handoff(billing, forbidden_construction)
    assert denied is billing.denial
    assert billing.brief is None
    assert counters == dict.fromkeys(counters, 0)
    assert denied.model_dump(mode="json") == {
        "schema_version": 2,
        "source_run_id": "source_run",
        "target_profile_id": "billing-observer@1",
        "task_id": GOLDEN.tasks[1].task_id.value,
        "reason_code": "scope_intersection_empty",
        "memory_count": 0,
        "evidence_count": 0,
        "source_path_count": 0,
        "tool_count": 0,
        "consumer_run_id": None,
        "session_id": None,
        "invocation_id": None,
        "model_dispatch_count": 0,
    }
