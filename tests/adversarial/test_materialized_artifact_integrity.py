from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from graphene.cli import mission as mission_cli
from graphene.hashing import canonical_json_bytes
from graphene.core_models import TruthKind
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.materialized_integrity import (
    MaterializedArtifactError,
    verify_materialized_artifacts,
)
from graphene.orchestration.mission_models import (
    Attempt,
    AttemptState,
    Criterion,
    CriterionVerificationKind,
    Gate,
    GateDecision,
    MissionStatus,
    Plan,
    Task,
)
from graphene.orchestration.mission_projection import MissionProjection, MissionProjectionError
from graphene.orchestration.worker_runtime import (
    WORKER_PROVIDER_RECEIPT_KIND,
    WorkerProviderReceipt,
)
from graphene.orchestration.sqlite_mission_store import MissionStoreError, SQLiteMissionStore
from tests.unit.orchestration.test_gemini_mission_runtime import (
    prepare_fake_two_worker_mission,
    quiet_resource_sampler,
)
from tests.unit.orchestration.test_store import (
    MemoryArtifacts,
    NOW,
    _artifacts,
    _command,
    _mission,
    _plan,
    _policy,
)


def _materialized_artifact_store(tmp_path):
    path = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(path)
    policy = _policy()
    mission = _mission()
    base_plan = _plan()
    tasks = []
    for task in base_plan.tasks:
        value = task.model_dump(mode="json")
        if task.task_id == "assemble":
            value["expected_outputs"][0]["kind"] = "patch"
        elif task.task_id == "verify":
            value["inputs"][0]["kind"] = "patch"
        tasks.append(Task.model_validate(value))
    plan = Plan.model_validate(
        {
            **base_plan.model_dump(mode="json"),
            "criteria": (
                Criterion(
                    criterion_id="all-checks-pass",
                    description=mission.success_criteria[0],
                    producer_task_ids=("work-a", "work-b"),
                    verification_kind=CriterionVerificationKind.DETERMINISTIC_CHECK,
                    verifier_task_id="verify",
                    verifier_id="check",
                ),
            ),
            "tasks": tasks,
        }
    )
    store.bind_artifact_resolver(MemoryArtifacts())
    created = store.create_mission(
        policy,
        mission,
        plan,
        _command("create-artifact-integrity"),
        recorded_at=NOW,
    )
    store.approve_plan(
        "mission-1",
        _command("approve-artifact-integrity"),
        expected_revision=1,
        expected_head=created,
        operator_label="api-operator",
        rationale="Approve the focused integrity fixture.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    reference = _artifacts(store).put("gate-receipt", b"committed gate evidence")
    store.request_gate(
        Gate(
            gate_id="artifact-integrity-gate",
            mission_id="mission-1",
            reason="Bind the focused cold-state artifact.",
            evidence=(reference,),
            allowed_decisions=(
                GateDecision(value="continue", consequence="Continue bounded work."),
            ),
            truth_kind=TruthKind.SERVER_DERIVED,
        ),
        _command("request-artifact-integrity-gate"),
        recorded_at=NOW + timedelta(seconds=1),
    )
    return path, store, reference


def test_cold_reads_and_final_approval_reject_changed_artifact_bytes(tmp_path) -> None:
    path, store, reference = _materialized_artifact_store(tmp_path)
    artifacts = _artifacts(store)
    artifacts.values[(reference.kind, reference.id)] = b"schema-valid forged bytes"

    cold = SQLiteMissionStore(path, artifact_resolver=artifacts)
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        cold.verify("mission-1")
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        cold.snapshot("mission-1")
    with pytest.raises(MissionProjectionError, match="store validation"):
        MissionProjection(cold).snapshot("mission-1")
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        cold.approve_final_result(
            "mission-1",
            _command("approve-forged-artifact"),
            expected_head=cold.head("mission-1"),
            expected_bundle_id="final_result_" + "a" * 32,
            operator_label="api-operator",
            rationale="Must fail before this decision is committed.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=7),
        )


def test_cold_verification_requires_resolver_after_artifacts_are_committed(
    tmp_path,
) -> None:
    path, store, _reference = _materialized_artifact_store(tmp_path)
    assert store.verify("mission-1") == store.head("mission-1")

    cold = SQLiteMissionStore(path)
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        cold.verify("mission-1")
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        cold.snapshot("mission-1")


def test_materialized_artifact_verifier_reconciles_unique_byte_count(tmp_path) -> None:
    _path, store, reference = _materialized_artifact_store(tmp_path)
    snapshot = store.snapshot("mission-1")
    attempt = Attempt(
        attempt_id="attempt-artifact-integrity",
        mission_id="mission-1",
        plan_revision=1,
        task_id="work-a",
        attempt_number=1,
        worker_id="worker-a",
        workspace_id="workspace-a",
        lease_id="lease-a",
        fencing_token=1,
        dispatch_command_id=_command("dispatch-artifact-integrity"),
        state=AttemptState.RUNNING,
        started_at=NOW,
        evidence_refs=(reference,),
    )
    content = _artifacts(store).resolve(reference.kind, reference.id)
    assert isinstance(content, bytes)

    assert (
        verify_materialized_artifacts(
            attempt_documents=(attempt.model_dump_json().encode("utf-8"),),
            gate_documents=(
                gate.model_dump_json().encode("utf-8") for gate in snapshot.gates
            ),
            resolver=_artifacts(store),
            max_artifact_bytes=len(content),
        )
        == len(content)
    )

    with pytest.raises(MaterializedArtifactError, match="policy budget"):
        verify_materialized_artifacts(
            attempt_documents=(attempt.model_dump_json().encode("utf-8"),),
            gate_documents=(
                gate.model_dump_json().encode("utf-8") for gate in snapshot.gates
            ),
            resolver=_artifacts(store),
            max_artifact_bytes=len(content) - 1,
        )


def test_forged_worker_provider_receipt_bytes_fail_closed_on_cold_reads(
    tmp_path, monkeypatch
) -> None:
    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
        resource_sampler=quiet_resource_sampler,
    )
    assert result["status"] == MissionStatus.AWAITING_RESULT
    assert prepared.store.verify(prepared.mission_id) == prepared.store.head(
        prepared.mission_id
    )
    reference = result["provider_receipt_references"][0]
    assert reference["kind"] == WORKER_PROVIDER_RECEIPT_KIND
    evidence_path = prepared.runtime / "attempt-evidence.sqlite3"
    original = SQLiteAttemptEvidenceStore(evidence_path).resolve(
        reference["kind"], reference["id"]
    )
    assert original is not None
    receipt = WorkerProviderReceipt.model_validate_json(original)
    forged = canonical_json_bytes(
        {**receipt.model_dump(mode="json"), "latency_ms": receipt.latency_ms + 1}
    )
    # Schema-valid, differently-digested bytes stand in for a tampered receipt.
    assert WorkerProviderReceipt.model_validate_json(forged) != receipt
    connection = sqlite3.connect(evidence_path)
    try:
        updated = connection.execute(
            "UPDATE attempt_artifacts SET artifact_bytes = ? WHERE artifact_id = ?",
            (forged, reference["id"]),
        ).rowcount
        connection.commit()
    finally:
        connection.close()
    assert updated == 1

    cold = mission_cli._store_for_mission(prepared.mission_id)
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        cold.verify(prepared.mission_id)
    with pytest.raises(MissionStoreError, match="materialized artifacts"):
        cold.snapshot(prepared.mission_id)
    with pytest.raises(MissionProjectionError, match="store validation"):
        MissionProjection(cold).snapshot(prepared.mission_id)
