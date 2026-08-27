from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from graphene.orchestration import evidence as evidence_module
from graphene.hashing import canonical_json_bytes
from graphene.core_models import TruthKind
from graphene.orchestration.evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceConflict,
    AttemptEvidenceEventType,
    AttemptEvidenceInput,
    AttemptEvidenceStoreError,
    SQLiteAttemptEvidenceStore,
    TrustedCheckReceipt,
)
from graphene.orchestration.mission_models import ArtifactVisibility, EvidenceReference


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_evidence_schema_is_initialized_once_and_version_checked(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "evidence.sqlite"
    SQLiteAttemptEvidenceStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1

    monkeypatch.setattr(evidence_module, "_SCHEMA", "invalid SQL")
    SQLiteAttemptEvidenceStore(path)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=2")
    with pytest.raises(AttemptEvidenceStoreError, match="unsupported.*version 2"):
        SQLiteAttemptEvidenceStore(path)


def _draft(
    event_type: AttemptEvidenceEventType,
    *,
    attempt_id: str = "attempt-1",
    references: tuple[EvidenceReference, ...] = (),
    payload: dict[str, object] | None = None,
) -> AttemptEvidenceInput:
    return AttemptEvidenceInput(
        mission_id="mission-1",
        task_id="task-1",
        attempt_id=attempt_id,
        event_type=event_type,
        truth_kind=TruthKind.RUNTIME_OBSERVED,
        authority=AttemptEvidenceAuthority.SCOPED_TOOL_WRAPPER,
        references=references,
        payload=payload or {"status": event_type.value},
    )


def test_evidence_chain_is_durable_idempotent_and_artifact_bound(tmp_path) -> None:
    path = tmp_path / "evidence.sqlite"
    store = SQLiteAttemptEvidenceStore(path)
    artifact = store.put_artifact(
        "patch", b"bounded patch", visibility=ArtifactVisibility.MISSION
    )
    empty = store.empty_head("evidence-1")
    started = _draft(AttemptEvidenceEventType.ATTEMPT_STARTED)

    first = store.append(
        "evidence-1", empty, "evidence-command-0001", started, recorded_at=NOW
    )
    duplicate = store.append(
        "evidence-1", empty, "evidence-command-0001", started, recorded_at=NOW
    )
    second = store.append(
        "evidence-1",
        store.head("evidence-1"),
        "evidence-command-0002",
        _draft(
            AttemptEvidenceEventType.ARTIFACT_OBSERVED,
            references=(artifact,),
            payload={"artifact_id": artifact.id, "sha256": artifact.sha256},
        ),
        recorded_at=NOW + timedelta(seconds=1),
    )
    terminal = store.append(
        "evidence-1",
        store.head("evidence-1"),
        "evidence-command-0003",
        _draft(AttemptEvidenceEventType.ATTEMPT_COMPLETED),
        recorded_at=NOW + timedelta(seconds=2),
    )

    reopened = SQLiteAttemptEvidenceStore(path)
    assert duplicate == first
    assert second.previous_event_sha256 == first.event_sha256
    assert terminal.previous_event_sha256 == second.event_sha256
    assert reopened.resolve("patch", artifact.id) == b"bounded patch"
    assert reopened.tail("evidence-1", 1, 10) == (second, terminal)
    assert reopened.verify("evidence-1") == reopened.head("evidence-1")
    with (
        sqlite3.connect(path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="append-only"),
    ):
        connection.execute(
            "UPDATE attempt_evidence_events SET event_sha256 = ? WHERE event_id = ?",
            ("f" * 64, first.event_id),
        )


def test_evidence_rejects_stale_identity_idempotency_and_terminal_writes(
    tmp_path,
) -> None:
    store = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    empty = store.empty_head("evidence-1")
    started = _draft(AttemptEvidenceEventType.ATTEMPT_STARTED)
    store.append("evidence-1", empty, "evidence-command-0001", started, recorded_at=NOW)

    with pytest.raises(AttemptEvidenceConflict, match="reused"):
        store.append(
            "evidence-1",
            empty,
            "evidence-command-0001",
            _draft(
                AttemptEvidenceEventType.ATTEMPT_STARTED, payload={"status": "changed"}
            ),
            recorded_at=NOW,
        )
    with pytest.raises(AttemptEvidenceConflict, match="head changed"):
        store.append(
            "evidence-1",
            empty,
            "evidence-command-0002",
            _draft(AttemptEvidenceEventType.OPERATION_COMPLETED),
            recorded_at=NOW,
        )
    with pytest.raises(AttemptEvidenceConflict, match="identity changed"):
        store.append(
            "evidence-1",
            store.head("evidence-1"),
            "evidence-command-0003",
            _draft(
                AttemptEvidenceEventType.OPERATION_COMPLETED, attempt_id="attempt-2"
            ),
            recorded_at=NOW,
        )

    store.append(
        "evidence-1",
        store.head("evidence-1"),
        "evidence-command-0004",
        _draft(AttemptEvidenceEventType.ATTEMPT_FAILED),
        recorded_at=NOW,
    )
    with pytest.raises(AttemptEvidenceConflict, match="terminal"):
        store.append(
            "evidence-1",
            store.head("evidence-1"),
            "evidence-command-0005",
            _draft(AttemptEvidenceEventType.OPERATION_COMPLETED),
            recorded_at=NOW,
        )


def test_evidence_rejects_private_payloads_and_unresolved_artifacts(tmp_path) -> None:
    store = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    with pytest.raises(ValidationError, match="unsafe"):
        _draft(AttemptEvidenceEventType.ATTEMPT_STARTED, payload={"stdout": "secret"})
    for payload in (
        {"apiKey": "hidden"},
        {"google_api_key": "hidden"},
        {"authorization_header": "hidden"},
        {"model_reasoning": "hidden"},
        {"user_prompt": "hidden"},
        {"command_argv": ["hidden"]},
        {"process_environment": {"SAFE": "hidden"}},
        {"process.env": {"SAFE": "hidden"}},
        {"result_content": "hidden"},
        {"tool.stdout": "hidden"},
        {"trace.stderr": "hidden"},
        {"label": "api_key=abcdefghijklmnopqrstuvwxyz012345"},
        {"label": "Bearer abcdefghijklmnopqrstuvwxyz012345"},
        {"label": "/home/runner/.ssh/id_rsa"},
    ):
        with pytest.raises(ValidationError, match="unsafe"):
            _draft(AttemptEvidenceEventType.ATTEMPT_STARTED, payload=payload)
    safe = _draft(
        AttemptEvidenceEventType.ATTEMPT_STARTED,
        payload={"estimated_tokens": 42, "label": "Token estimate unavailable."},
    )
    assert safe.payload["estimated_tokens"] == 42
    missing = EvidenceReference(kind="patch", id="artifact-missing", sha256="a" * 64)
    with pytest.raises(AttemptEvidenceConflict, match="unresolved"):
        store.append(
            "evidence-1",
            store.empty_head("evidence-1"),
            "evidence-command-0001",
            _draft(AttemptEvidenceEventType.ATTEMPT_STARTED, references=(missing,)),
            recorded_at=NOW,
        )
    real = store.put_artifact("patch", b"real")
    lying = EvidenceReference(kind=real.kind, id=real.id, sha256="f" * 64)
    with pytest.raises(AttemptEvidenceConflict, match="unresolved"):
        store.append(
            "evidence-2",
            store.empty_head("evidence-2"),
            "evidence-command-0002",
            _draft(AttemptEvidenceEventType.ATTEMPT_STARTED, references=(lying,)),
            recorded_at=NOW,
        )


def test_evidence_verification_detects_head_corruption(tmp_path) -> None:
    path = tmp_path / "evidence.sqlite"
    store = SQLiteAttemptEvidenceStore(path)
    store.append(
        "evidence-1",
        store.empty_head("evidence-1"),
        "evidence-command-0001",
        _draft(AttemptEvidenceEventType.ATTEMPT_STARTED),
        recorded_at=NOW,
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE attempt_evidence_heads SET event_sha256 = ? WHERE evidence_id = ?",
            ("f" * 64, "evidence-1"),
        )

    with pytest.raises(AttemptEvidenceStoreError, match="head is invalid"):
        store.verify("evidence-1")


def _trusted_attempt(store: SQLiteAttemptEvidenceStore):
    candidate = store.put_artifact("patch", b"candidate")
    receipt = TrustedCheckReceipt(
        schema_version=2,
        mission_id="mission-1",
        task_id="task-1",
        attempt_id="attempt-1",
        plan_revision=3,
        fencing_token=7,
        policy_sha256="a" * 64,
        base_sha="b" * 40,
        runner_id="graphene_check_runner_v1",
        template_id="fixture-tests",
        template_sha256="c" * 64,
        accepted_input_references=(),
        candidate_references=(candidate,),
        candidate_tree_hash_version="graphene.tree.v2",
        candidate_tree_sha256="d" * 64,
        result_code="passed",
        exit_code=0,
        timed_out=False,
        output_sha256="e" * 64,
        output_truncated=False,
        cleanup_complete=True,
    )
    receipt_reference = store.put_artifact(
        "test-receipt", canonical_json_bytes(receipt.model_dump(mode="json"))
    )
    evidence_id = "evidence-trusted"
    store.append(
        evidence_id,
        store.empty_head(evidence_id),
        "evidence-trusted-start",
        _draft(AttemptEvidenceEventType.ATTEMPT_STARTED),
        recorded_at=NOW,
    )
    store.append_check(
        evidence_id,
        store.head(evidence_id),
        "evidence-trusted-check",
        mission_id="mission-1",
        task_id="task-1",
        attempt_id="attempt-1",
        receipt=receipt_reference,
        payload=receipt.event_payload(receipt_reference.sha256),
        recorded_at=NOW + timedelta(seconds=1),
    )
    references = tuple(
        sorted(
            (candidate, receipt_reference),
            key=lambda item: (item.kind, item.id, item.sha256),
        )
    )
    store.append(
        evidence_id,
        store.head(evidence_id),
        "evidence-trusted-terminal",
        _draft(
            AttemptEvidenceEventType.ATTEMPT_COMPLETED,
            references=references,
            payload={"result_code": "passed"},
        ),
        recorded_at=NOW + timedelta(seconds=2),
    )
    binding = {
        "mission_id": "mission-1",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "succeeded": True,
        "result_code": "passed",
        "references": references,
        "plan_revision": 3,
        "fencing_token": 7,
        "policy_sha256": "a" * 64,
        "base_sha": "b" * 40,
        "template_id": "fixture-tests",
        "template_sha256": "c" * 64,
        "accepted_inputs": (),
        "candidate_references": (candidate,),
    }
    return evidence_id, candidate, receipt_reference, binding


def test_trusted_check_requires_runner_authority_and_minting_api(tmp_path) -> None:
    store = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    _evidence_id, _candidate, receipt_reference, _binding = _trusted_attempt(store)
    receipt = TrustedCheckReceipt.model_validate_json(
        store.resolve(receipt_reference.kind, receipt_reference.id)
    )
    for missing in ("schema_version", "runner_id", "candidate_tree_hash_version"):
        with pytest.raises(ValidationError):
            TrustedCheckReceipt.model_validate(
                receipt.model_dump(mode="json", exclude={missing})
            )
    with pytest.raises(ValidationError, match="truth and authority"):
        _draft(AttemptEvidenceEventType.CHECK_COMPLETED)
    forged = AttemptEvidenceInput(
        mission_id="mission-1",
        task_id="task-1",
        attempt_id="attempt-1",
        event_type=AttemptEvidenceEventType.CHECK_COMPLETED,
        truth_kind=TruthKind.RUNTIME_OBSERVED,
        authority=AttemptEvidenceAuthority.CHECK_RUNNER,
        payload={"result_code": "passed"},
    )
    with pytest.raises(AttemptEvidenceConflict, match="trusted check runner"):
        store.append(
            "evidence-forged",
            store.empty_head("evidence-forged"),
            "evidence-forged-check",
            forged,
            recorded_at=NOW,
        )


def test_success_requires_check_event_and_exact_references(tmp_path) -> None:
    store = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    evidence_id, _candidate, _receipt, binding = _trusted_attempt(store)
    assert store.verify_attempt(evidence_id, **binding)

    missing = {**binding, "references": binding["references"][:-1]}
    assert not store.verify_attempt(evidence_id, **missing)
    extra_reference = store.put_artifact("resource-receipt", b"extra")
    extra = {
        **binding,
        "references": (*binding["references"], extra_reference),
    }
    assert not store.verify_attempt(evidence_id, **extra)

    no_check_id = "evidence-no-check"
    store.append(
        no_check_id,
        store.empty_head(no_check_id),
        "evidence-no-check-start",
        _draft(AttemptEvidenceEventType.ATTEMPT_STARTED),
        recorded_at=NOW,
    )
    store.append(
        no_check_id,
        store.head(no_check_id),
        "evidence-no-check-terminal",
        _draft(
            AttemptEvidenceEventType.ATTEMPT_COMPLETED,
            references=binding["references"],
            payload={"result_code": "passed"},
        ),
        recorded_at=NOW,
    )
    assert not store.verify_attempt(no_check_id, **binding)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("result_code", "fabricated_pass"),
        ("fencing_token", 8),
        ("plan_revision", 4),
        ("policy_sha256", "f" * 64),
        ("base_sha", "f" * 40),
        ("template_id", "drifted-template"),
        ("template_sha256", "f" * 64),
    ),
)
def test_trusted_check_rejects_stale_or_drifted_binding(
    tmp_path, field: str, value: object
) -> None:
    store = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    evidence_id, _candidate, _receipt, binding = _trusted_attempt(store)
    assert not store.verify_attempt(evidence_id, **{**binding, field: value})


def test_trusted_check_rejects_tested_output_swap(tmp_path) -> None:
    store = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    evidence_id, _candidate, _receipt, binding = _trusted_attempt(store)
    swapped = store.put_artifact("patch", b"published-but-not-tested")
    assert not store.verify_attempt(
        evidence_id,
        **{**binding, "candidate_references": (swapped,)},
    )


def test_trusted_check_rejects_receipt_content_change(tmp_path) -> None:
    path = tmp_path / "evidence.sqlite"
    store = SQLiteAttemptEvidenceStore(path)
    evidence_id, _candidate, receipt, binding = _trusted_attempt(store)
    changed = b'{"exit_code":0}'
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE attempt_artifacts SET artifact_bytes = ?, byte_count = ? "
            "WHERE artifact_id = ?",
            (changed, len(changed), receipt.id),
        )

    with pytest.raises(AttemptEvidenceStoreError, match="artifact is unavailable"):
        store.verify_attempt(evidence_id, **binding)
