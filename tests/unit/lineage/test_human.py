from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from graphene.bootstrap import BootstrappedRun, bootstrap_local_run
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.lineage import (
    HumanConflict,
    HumanEvidenceError,
    HumanWorkflowService,
)
from graphene.lineage.service import ToolCallIdentity
from graphene.core_models import (
    ClarificationAnswer,
    ClarificationQuestion,
    Event,
    EvidenceKind,
    FeedbackRecord,
    GoldenContract,
    HunkEvidence,
    LineageEventType,
    MemoryDecisionValue,
    MemoryRevision,
    MemoryState,
    ScopeId,
    SourceKind,
    TruthKind,
    LineageAuthority,
    VerifiedHead,
)

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)


def _head(event: Event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _call(run: BootstrappedRun, number: int) -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=run.session_id,
        invocation_id=run.invocation_id,
        model_id=run.model_id,
        tool_call_id=f"tool_call_human_{number:03d}",
        agent_name="graphene_local",
        adapter_kind="local",
    )


def _bootstrap(
    tmp_path: Path, *, task: str = "baseline_max_attempts"
) -> BootstrappedRun:
    runtime = tmp_path / f"runtime-{task}"
    runtime.mkdir(mode=0o700, parents=True)
    return bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id=task,
        profile_id=(
            "platform-maintainer@1"
            if task == "baseline_max_attempts"
            else "auth-maintainer@1"
        ),
        repository_root=ROOT,
    )


@dataclass(frozen=True)
class ReviewReady:
    run: BootstrappedRun
    workflow: HumanWorkflowService
    write: Event
    tested: Event
    changeset: Event
    test_receipt: Event
    hunk: HunkEvidence


def _review_ready(tmp_path: Path) -> ReviewReady:
    run = _bootstrap(tmp_path)
    read = run.service.read_file(
        run.handle,
        _call(run, 1),
        path="app/auth/limiter.py",
    )
    run.service.write_file(
        run.handle,
        _call(run, 2),
        path="app/auth/limiter.py",
        content=read.content.replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4"),
    )
    result = run.service.run_fixed_test(run.handle, _call(run, 3))
    assert result.passed is True
    run.service.request_completion(run.handle, _call(run, 4))
    observed = run.store.tail(run.run_id, 0, 256)
    write = next(
        event
        for event in observed
        if event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == "write_file"
    )
    tested = next(
        event
        for event in observed
        if event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == "run_fixed_test"
    )
    workflow = HumanWorkflowService(run.store, run.artifacts, GOLDEN.memory)
    changeset = workflow.derive_changeset(
        run.run_id,
        run.handle.head,
        idempotency_key="human_changeset_0001",
    )
    test_receipt = workflow.record_test_receipt(
        run.run_id,
        _head(changeset),
        test_event_id=tested.event_id,
        idempotency_key="human_test_receipt_01",
    )
    hunk_ref = next(
        reference
        for reference in changeset.references
        if reference.kind == EvidenceKind.HUNK
    )
    raw = run.artifacts.resolve(hunk_ref.kind.value, hunk_ref.id)
    assert raw is not None
    hunk = HunkEvidence.model_validate_json(raw)
    return ReviewReady(
        run,
        workflow,
        write,
        tested,
        changeset,
        test_receipt,
        hunk,
    )


def _artifact(run: BootstrappedRun, kind: EvidenceKind, event: Event) -> dict:
    reference = next(item for item in event.references if item.kind == kind)
    raw = run.artifacts.resolve(reference.kind.value, reference.id)
    assert raw is not None and sha256_hex(raw) == reference.sha256
    return json.loads(raw)


@pytest.mark.parametrize(
    ("decision", "event_type", "state"),
    (
        (
            MemoryDecisionValue.APPROVE,
            LineageEventType.MEMORY_APPROVED,
            MemoryState.APPROVED,
        ),
        (
            MemoryDecisionValue.REJECT,
            LineageEventType.MEMORY_REJECTED,
            MemoryState.REJECTED,
        ),
    ),
)
def test_real_run_derives_exact_private_review_and_explicit_memory_decision(
    tmp_path: Path,
    decision: MemoryDecisionValue,
    event_type: LineageEventType,
    state: MemoryState,
):
    ready = _review_ready(tmp_path)
    run, workflow = ready.run, ready.workflow

    changeset = _artifact(run, EvidenceKind.CHANGESET, ready.changeset)
    patch = json.loads(json.dumps(changeset))["canonical_patch_base64"]
    assert changeset["changed_paths"] == ["app/auth/limiter.py"]
    assert changeset["source_write_events"] == [
        {
            "kind": "event",
            "id": ready.write.event_id,
            "sha256": ready.write.event_sha256,
        }
    ]
    assert ready.hunk.path == "app/auth/limiter.py"
    assert "-MAX_ATTEMPTS = 5" in ready.hunk.unified_diff
    assert "+MAX_ATTEMPTS = 4" in ready.hunk.unified_diff
    assert patch
    assert ready.test_receipt.payload == {
        "bound_paths": ["app/auth/limiter.py"],
        "passed": True,
        "receipt_id": ready.tested.references[0].id,
        "receipt_sha256": ready.tested.references[0].sha256,
        "status": "created",
    }

    asked = workflow.ask_clarification(
        run.run_id,
        _head(ready.test_receipt),
        write_event_id=ready.write.event_id,
        hunk_id=ready.hunk.hunk_id,
        correction=GOLDEN.memory.correction,
        idempotency_key="human_clarification_01",
    )
    policy_raw = run.artifacts.resolve(
        asked.source_ref.kind.value,
        asked.source_ref.id,
    )
    assert policy_raw is not None
    question = ClarificationQuestion.model_validate(json.loads(policy_raw)["question"])
    assert question.choices == (ScopeId.ALL_AUTH, ScopeId.RATE_LIMITER_ONLY)
    pending_ref = next(
        item for item in asked.references if item.kind == EvidenceKind.OPERATOR_REQUEST
    )
    pending_raw = run.artifacts.resolve(pending_ref.kind.value, pending_ref.id)
    assert pending_raw is not None and GOLDEN.memory.correction in pending_raw.decode()
    assert GOLDEN.memory.correction.encode() not in canonical_json_bytes(
        asked.model_dump(mode="json")
    )

    answered = workflow.answer_clarification(
        run.run_id,
        _head(asked),
        question_id=question.question_id,
        choice=ScopeId.ALL_AUTH,
        idempotency_key="human_clarification_answer_01",
        human_attestation=True,
        operator_label="reviewer-a",
        operator_rationale="scope matches the affected auth policy",
    )
    answer_raw = run.artifacts.resolve(
        answered.source_ref.kind.value,
        answered.source_ref.id,
    )
    assert answer_raw is not None
    answer_record = json.loads(answer_raw)
    answer = ClarificationAnswer.model_validate(answer_record["answer"])
    assert answer.actor == "human" and answer.choice == ScopeId.ALL_AUTH
    assert answer_record["operator_label"] == "reviewer-a"
    assert answer_record["operator_rationale"] == (
        "scope matches the affected auth policy"
    )

    feedback_event = workflow.record_feedback(
        run.run_id,
        _head(answered),
        question_id=question.question_id,
        idempotency_key="human_feedback_record_01",
        human_attestation=True,
        operator_label="reviewer-a",
        operator_rationale="scope matches the affected auth policy",
    )
    feedback = FeedbackRecord.model_validate(
        _artifact(run, EvidenceKind.FEEDBACK, feedback_event)
    )
    assert (
        feedback.run_id,
        feedback.evidence_event_id,
        feedback.selected_hunk_id,
        feedback.selected_scope_id,
    ) == (
        run.run_id,
        ready.write.event_id,
        ready.hunk.hunk_id,
        ScopeId.ALL_AUTH,
    )
    assert GOLDEN.memory.correction.encode() not in canonical_json_bytes(
        feedback_event.model_dump(mode="json")
    )
    assert feedback_event.payload["correction_sha256"] == sha256_hex(
        GOLDEN.memory.correction.encode()
    )

    proposed_event = workflow.propose_memory(
        run.run_id,
        _head(feedback_event),
        feedback_id=feedback.feedback_id,
        idempotency_key="human_memory_proposed_01",
    )
    proposed = MemoryRevision.model_validate(
        _artifact(run, EvidenceKind.MEMORY_REVISION, proposed_event)
    )
    assert proposed.state == MemoryState.PROPOSED
    assert proposed.path_globs == ("app/auth/**",)
    assert proposed.feedback_id == feedback.feedback_id
    proposed_event_ids = {
        item.id for item in proposed_event.references if item.kind == EvidenceKind.EVENT
    }
    assert {
        asked.event_id,
        answered.event_id,
        feedback_event.event_id,
    } <= proposed_event_ids

    decided_event = workflow.decide_memory(
        run.run_id,
        _head(proposed_event),
        memory_id=proposed.memory_id,
        revision=proposed.revision,
        decision=decision,
        idempotency_key=f"human_memory_{decision.value}_01",
        human_attestation=True,
        operator_label="reviewer-a",
        operator_rationale="bounded review completed",
    )
    decided_refs = [
        item
        for item in decided_event.references
        if item.kind == EvidenceKind.MEMORY_REVISION
    ]
    decided_raw = run.artifacts.resolve(
        decided_refs[-1].kind.value,
        decided_refs[-1].id,
    )
    assert decided_raw is not None
    decided = MemoryRevision.model_validate_json(decided_raw)
    assert decided_event.event_type == event_type
    assert decided.state == state
    assert decided.decision is not None
    assert decided.decision.actor == "human"
    assert decided.decision.value == decision
    assert decided.decision.bound_digest == canonical_json_sha256(
        proposed.model_dump(mode="json", exclude={"state", "decision"})
    )
    decision_record = json.loads(
        run.artifacts.resolve(
            decided_event.source_ref.kind.value,
            decided_event.source_ref.id,
        )
    )
    assert decision_record["operator_label"] == "reviewer-a"
    assert decision_record["operator_rationale"] == "bounded review completed"
    assert run.store.verify(run.run_id) == _head(decided_event)
    assert GOLDEN.memory.correction.encode() not in canonical_json_bytes(
        [event.model_dump(mode="json") for event in run.store.tail(run.run_id, 0, 256)]
    )


def test_simulated_fixture_decisions_are_explicit_and_provenance_locked(tmp_path):
    ready = _review_ready(tmp_path)
    run, workflow = ready.run, ready.workflow
    asked = workflow.ask_clarification(
        run.run_id,
        _head(ready.test_receipt),
        write_event_id=ready.write.event_id,
        hunk_id=ready.hunk.hunk_id,
        correction=GOLDEN.memory.correction,
        idempotency_key="fixture_question_001",
    )
    question = ClarificationQuestion.model_validate(
        json.loads(
            run.artifacts.resolve(asked.source_ref.kind.value, asked.source_ref.id)
        )["question"]
    )
    answered = workflow.answer_clarification(
        run.run_id,
        _head(asked),
        question_id=question.question_id,
        choice=ScopeId.ALL_AUTH,
        idempotency_key="fixture_answer_001",
        simulated_fixture=True,
    )
    with pytest.raises(HumanConflict, match="provenance"):
        workflow.record_feedback(
            run.run_id,
            _head(answered),
            question_id=question.question_id,
            idempotency_key="fixture_feedback_wrong_001",
            human_attestation=True,
        )
    feedback = workflow.record_feedback(
        run.run_id,
        _head(answered),
        question_id=question.question_id,
        idempotency_key="fixture_feedback_001",
        simulated_fixture=True,
    )
    proposed = workflow.propose_memory(
        run.run_id,
        _head(feedback),
        feedback_id=feedback.payload["feedback_id"],
        idempotency_key="fixture_proposed_001",
    )
    decided = workflow.decide_memory(
        run.run_id,
        _head(proposed),
        memory_id=proposed.payload["memory_id"],
        revision=proposed.payload["revision"],
        decision=MemoryDecisionValue.APPROVE,
        idempotency_key="fixture_memory_001",
        simulated_fixture=True,
    )

    for event in (answered, feedback, decided):
        assert event.truth_kind == TruthKind.SIMULATED_FIXTURE
        assert event.authority == LineageAuthority.SIMULATED_FIXTURE
        assert event.source_ref.kind == SourceKind.SIMULATED_FIXTURE
    answer_record = json.loads(
        run.artifacts.resolve(answered.source_ref.kind.value, answered.source_ref.id)
    )
    assert answer_record["answer"]["actor"] == "simulated_fixture"
    decided_ref = next(
        reference
        for reference in decided.references
        if reference.kind == EvidenceKind.MEMORY_REVISION
        and reference.sha256 == decided.payload["memory_sha256"]
    )
    memory = MemoryRevision.model_validate_json(
        run.artifacts.resolve(decided_ref.kind.value, decided_ref.id)
    )
    assert memory.decision is not None
    assert memory.decision.actor == "simulated_fixture"


def test_human_provenance_requires_explicit_verified_tty_attestation(tmp_path):
    ready = _review_ready(tmp_path)
    run, workflow = ready.run, ready.workflow
    asked = workflow.ask_clarification(
        run.run_id,
        _head(ready.test_receipt),
        write_event_id=ready.write.event_id,
        hunk_id=ready.hunk.hunk_id,
        correction=GOLDEN.memory.correction,
        idempotency_key="tty_question_0001",
    )
    head = _head(asked)

    with pytest.raises(HumanConflict, match="verified interactive TTY"):
        workflow.answer_clarification(
            run.run_id,
            head,
            question_id=asked.payload["question_id"],
            choice=ScopeId.ALL_AUTH,
            idempotency_key="tty_missing_0001",
        )
    with pytest.raises(HumanConflict, match="both human and simulated"):
        workflow.answer_clarification(
            run.run_id,
            head,
            question_id=asked.payload["question_id"],
            choice=ScopeId.ALL_AUTH,
            idempotency_key="tty_conflict_0001",
            simulated_fixture=True,
            human_attestation=True,
        )
    with pytest.raises(HumanConflict, match="1 to 64 UTF-8 bytes"):
        workflow.answer_clarification(
            run.run_id,
            head,
            question_id=asked.payload["question_id"],
            choice=ScopeId.ALL_AUTH,
            idempotency_key="tty_label_000001",
            human_attestation=True,
            operator_label="x" * 65,
        )
    with pytest.raises(HumanConflict, match="rationale exceeds"):
        workflow.answer_clarification(
            run.run_id,
            head,
            question_id=asked.payload["question_id"],
            choice=ScopeId.ALL_AUTH,
            idempotency_key="tty_reason_00001",
            human_attestation=True,
            operator_rationale="x" * 257,
        )

    assert run.store.verify(run.run_id) == head


def test_rate_limiter_scope_has_a_durable_narrower_memory_consequence(tmp_path):
    ready = _review_ready(tmp_path)
    run, workflow = ready.run, ready.workflow
    asked = workflow.ask_clarification(
        run.run_id,
        _head(ready.test_receipt),
        write_event_id=ready.write.event_id,
        hunk_id=ready.hunk.hunk_id,
        correction=GOLDEN.memory.correction,
        idempotency_key="narrow_question_01",
    )
    answered = workflow.answer_clarification(
        run.run_id,
        _head(asked),
        question_id=asked.payload["question_id"],
        choice=ScopeId.RATE_LIMITER_ONLY,
        idempotency_key="narrow_answer_0001",
        human_attestation=True,
    )
    feedback = workflow.record_feedback(
        run.run_id,
        _head(answered),
        question_id=asked.payload["question_id"],
        idempotency_key="narrow_feedback_01",
        human_attestation=True,
    )
    proposed = workflow.propose_memory(
        run.run_id,
        _head(feedback),
        feedback_id=feedback.payload["feedback_id"],
        idempotency_key="narrow_proposed_01",
    )
    revision = MemoryRevision.model_validate(
        _artifact(run, EvidenceKind.MEMORY_REVISION, proposed)
    )

    assert feedback.payload["scope_id"] == ScopeId.RATE_LIMITER_ONLY.value
    assert revision.scope_id == ScopeId.RATE_LIMITER_ONLY
    assert revision.path_globs == ("app/auth/limiter.py",)


def test_stale_cross_run_wrong_hunk_test_and_substitution_fail_before_append(
    tmp_path: Path,
):
    ready = _review_ready(tmp_path)
    run, workflow = ready.run, ready.workflow
    current = _head(ready.test_receipt)

    with pytest.raises(HumanConflict, match="stale"):
        workflow.derive_changeset(
            run.run_id,
            run.handle.head,
            idempotency_key="human_stale_changeset_01",
        )
    with pytest.raises(HumanEvidenceError, match="selected hunk"):
        workflow.ask_clarification(
            run.run_id,
            current,
            write_event_id=ready.write.event_id,
            hunk_id="hunk:not_the_observed_hunk",
            correction=GOLDEN.memory.correction,
            idempotency_key="human_wrong_hunk_0001",
        )
    with pytest.raises(HumanEvidenceError, match="matching write"):
        workflow.ask_clarification(
            run.run_id,
            current,
            write_event_id=ready.tested.event_id,
            hunk_id=ready.hunk.hunk_id,
            correction=GOLDEN.memory.correction,
            idempotency_key="human_non_write_00001",
        )
    with pytest.raises(HumanConflict, match="server-owned"):
        workflow.ask_clarification(
            run.run_id,
            current,
            write_event_id=ready.write.event_id,
            hunk_id=ready.hunk.hunk_id,
            correction="substitute an unrelated lesson",
            idempotency_key="human_substitute_0001",
        )
    with pytest.raises(HumanEvidenceError, match="observed fixed test"):
        workflow.record_test_receipt(
            run.run_id,
            current,
            test_event_id=ready.write.event_id,
            idempotency_key="human_wrong_test_0001",
        )
    assert run.store.verify(run.run_id) == current

    other = _bootstrap(tmp_path / "other", task="adapted_window_seconds")
    other_workflow = HumanWorkflowService(other.store, other.artifacts, GOLDEN.memory)
    with pytest.raises(HumanEvidenceError, match="not in the verified run"):
        other_workflow.ask_clarification(
            other.run_id,
            other.head,
            write_event_id=ready.write.event_id,
            hunk_id=ready.hunk.hunk_id,
            correction=GOLDEN.memory.correction,
            idempotency_key="human_cross_run_00001",
        )
    assert other.store.verify(other.run_id) == other.head

    asked = workflow.ask_clarification(
        run.run_id,
        current,
        write_event_id=ready.write.event_id,
        hunk_id=ready.hunk.hunk_id,
        correction=GOLDEN.memory.correction,
        idempotency_key="human_valid_question_1",
    )
    with pytest.raises(HumanConflict, match="unknown"):
        workflow.answer_clarification(
            run.run_id,
            _head(asked),
            question_id=asked.payload["question_id"],
            choice="billing_scope",
            idempotency_key="human_wrong_choice_001",
        )
    assert run.store.verify(run.run_id) == _head(asked)
