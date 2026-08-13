from __future__ import annotations

import json
from pathlib import Path

import pytest
from graphene.bootstrap import BootstrappedRun, bootstrap_local_run
from graphene.lineage.explain import (
    ExplainNotFound,
    explain_path,
    inspect_run_item,
)
from graphene.lineage.human import HumanWorkflowService
from graphene.lineage.service import ToolCallIdentity
from graphene.models import (
    Event,
    EvidenceKind,
    GoldenContract,
    LineageEventType,
    MemoryDecisionValue,
    VerifiedHead,
)

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
PATH = "app/auth/limiter.py"
CANARY = "EXPLAIN_PRIVATE_CANARY_7e23"


def _head(event: Event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _bootstrap(
    tmp_path: Path,
    *,
    task: str = "baseline_max_attempts",
    database: Path | None = None,
) -> BootstrappedRun:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    return bootstrap_local_run(
        database or runtime / "lineage.sqlite3",
        task_id=task,
        profile_id=(
            "platform-maintainer@1"
            if task == "baseline_max_attempts"
            else "auth-maintainer@1"
        ),
        repository_root=ROOT,
    )


def _call(run: BootstrappedRun, number: int) -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=run.session_id,
        invocation_id=run.invocation_id,
        model_id=run.model_id,
        tool_call_id=f"tool_call_explain_{number:03d}",
        agent_name="graphene_local",
        adapter_kind="local",
    )


def _review_run(tmp_path: Path) -> tuple[BootstrappedRun, Event, Event, Event]:
    run = _bootstrap(tmp_path)
    read = run.service.read_file(run.handle, _call(run, 1), path=PATH)
    run.service.write_file(
        run.handle,
        _call(run, 2),
        path=PATH,
        content=(
            read.content.replace("MAX_ATTEMPTS = 5", "MAX_ATTEMPTS = 4")
            + f"\n# {CANARY}\n"
        ),
    )
    assert run.service.run_fixed_test(run.handle, _call(run, 3)).passed is True
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
        idempotency_key="explain_changeset_0001",
    )
    receipt = workflow.record_test_receipt(
        run.run_id,
        _head(changeset),
        test_event_id=tested.event_id,
        idempotency_key="explain_test_receipt_01",
    )
    return run, write, changeset, receipt


def test_inspect_and_why_use_only_verified_explicit_bindings(tmp_path: Path):
    run, write, changeset, _ = _review_run(tmp_path)
    changeset_ref = next(
        reference
        for reference in changeset.references
        if reference.kind == EvidenceKind.CHANGESET
    )

    inspected = inspect_run_item(
        run.store,
        run.artifacts,
        run.run_id,
        changeset_ref.id,
    )
    capped = inspect_run_item(
        run.store,
        run.artifacts,
        run.run_id,
        changeset_ref.id,
        max_artifact_bytes=1,
    )
    why = explain_path(run.store, run.artifacts, run.run_id, PATH)

    assert inspected["item"]["sha256"] == changeset_ref.sha256
    assert (
        inspected["item"]["record"]["changeset_id"] == changeset.payload["changeset_id"]
    )
    assert capped["item"]["record"] is None
    assert capped["omissions"] == [
        {
            "field": "item.record",
            "reason": "artifact_byte_limit",
            "byte_count": inspected["item"]["byte_count"],
            "limit": 1,
        }
    ]
    relations = {item["relation"] for item in why["relationships"]}
    assert {
        "READ",
        "WROTE",
        "WROTE_VERSION",
        "PRODUCED",
        "CONTAINS",
        "MODIFIES",
        "VALIDATED",
    } <= relations
    assert any(item["event_id"] == write.event_id for item in why["observations"])
    assert why["omissions"]["relationships_due_to_limit"] == 0
    assert CANARY not in json.dumps(why)
    json.dumps(inspected)
    json.dumps(why)


def test_feedback_and_memory_relationships_remain_reference_backed(tmp_path: Path):
    run, write, changeset, receipt = _review_run(tmp_path)
    workflow = HumanWorkflowService(run.store, run.artifacts, GOLDEN.memory)
    hunk_ref = next(
        reference
        for reference in changeset.references
        if reference.kind == EvidenceKind.HUNK
    )
    hunk = json.loads(run.artifacts.resolve(hunk_ref.kind.value, hunk_ref.id))
    asked = workflow.ask_clarification(
        run.run_id,
        _head(receipt),
        write_event_id=write.event_id,
        hunk_id=hunk["hunk_id"],
        correction=GOLDEN.memory.correction,
        idempotency_key="explain_question_0001",
    )
    source = json.loads(
        run.artifacts.resolve(asked.source_ref.kind.value, asked.source_ref.id)
    )
    question_id = source["question"]["question_id"]
    answered = workflow.answer_clarification(
        run.run_id,
        _head(asked),
        question_id=question_id,
        choice="all_auth",
        idempotency_key="explain_answer_00001",
    )
    feedback = workflow.record_feedback(
        run.run_id,
        _head(answered),
        question_id=question_id,
        idempotency_key="explain_feedback_0001",
    )
    proposed = workflow.propose_memory(
        run.run_id,
        _head(feedback),
        feedback_id=feedback.payload["feedback_id"],
        idempotency_key="explain_memory_prop_01",
    )
    workflow.decide_memory(
        run.run_id,
        _head(proposed),
        memory_id=proposed.payload["memory_id"],
        revision=proposed.payload["revision"],
        decision=MemoryDecisionValue.APPROVE,
        idempotency_key="explain_memory_appr_01",
    )

    why = explain_path(run.store, run.artifacts, run.run_id, PATH)

    relations = {item["relation"] for item in why["relationships"]}
    assert {"TRIGGERED", "EVIDENCED", "LEARNED_AS", "APPROVED"} <= relations
    assert GOLDEN.memory.correction not in json.dumps(why)


def test_cross_run_artifact_is_unknown_and_canary_is_not_disclosed(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    database = runtime / "lineage.sqlite3"
    selected = _bootstrap(tmp_path, database=database)
    other = _bootstrap(
        tmp_path,
        task="adapted_window_seconds",
        database=database,
    )
    read = other.service.read_file(other.handle, _call(other, 20), path=PATH)
    other.service.write_file(
        other.handle,
        _call(other, 21),
        path=PATH,
        content=read.content + f"\n# {CANARY}\n",
    )
    write = next(
        event
        for event in other.store.tail(other.run_id, 0, 256)
        if event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == "write_file"
    )
    after_id = write.payload["after_file_version_id"]
    private_ref = next(
        reference
        for reference in write.references
        if reference.kind == EvidenceKind.FILE_VERSION
        and json.loads(other.artifacts.resolve(reference.kind.value, reference.id))[
            "file_version_id"
        ]
        == after_id
    )

    with pytest.raises(
        ExplainNotFound,
        match="item is not referenced by the selected run",
    ) as caught:
        inspect_run_item(
            selected.store,
            selected.artifacts,
            selected.run_id,
            private_ref.id,
        )

    assert CANARY not in str(caught.value)
    assert private_ref.id not in str(caught.value)
    assert CANARY not in json.dumps(
        explain_path(selected.store, selected.artifacts, selected.run_id, PATH)
    )


def test_unknown_path_reports_no_inferred_relationship(tmp_path: Path):
    run = _bootstrap(tmp_path)

    result = explain_path(
        run.store,
        run.artifacts,
        run.run_id,
        "docs/unknown.py",
    )

    assert result["relationships"] == []
    assert result["observations"] == []
    assert result["unknowns"][-1] == (
        "No stored relationship binds the requested path in this run."
    )
    assert result["omissions"]["unmodeled_bound_artifacts_by_kind"]
