from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from graphene.models import TruthKind
from graphene.orchestration.evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceConflict,
    AttemptEvidenceEventType,
    AttemptEvidenceInput,
    AttemptEvidenceStoreError,
    SQLiteAttemptEvidenceStore,
)
from graphene.orchestration.models import ArtifactVisibility, EvidenceReference


NOW = datetime(2026, 1, 1, tzinfo=UTC)


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
