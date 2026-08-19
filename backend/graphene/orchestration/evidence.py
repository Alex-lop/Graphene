from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, TypeAdapter, model_validator

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..models import (
    FrozenModel,
    Identifier,
    IdempotencyKey,
    Sha256,
    TruthKind,
    UtcDateTime,
)
from .models import (
    MAX_ARTIFACT_BYTES,
    MAX_EVENT_PAYLOAD_BYTES,
    ArtifactVisibility,
    EvidenceReference,
    _safe_public_value,
)

_UTC_TIME = TypeAdapter(UtcDateTime)


class AttemptEvidenceEventType(StrEnum):
    ATTEMPT_STARTED = "attempt.started"
    OPERATION_STARTED = "operation.started"
    OPERATION_COMPLETED = "operation.completed"
    OPERATION_FAILED = "operation.failed"
    CHECK_COMPLETED = "check.completed"
    ARTIFACT_OBSERVED = "artifact.observed"
    ATTEMPT_COMPLETED = "attempt.completed"
    ATTEMPT_FAILED = "attempt.failed"


class AttemptEvidenceAuthority(StrEnum):
    SCRIPTED_WORKER = "scripted_worker"
    ADK_ADAPTER = "adk_adapter"
    SCOPED_TOOL_WRAPPER = "scoped_tool_wrapper"
    CHECK_RUNNER = "check_runner"
    POLICY_ENGINE = "policy_engine"


class AttemptEvidenceInput(FrozenModel):
    mission_id: Identifier
    task_id: Identifier
    attempt_id: Identifier
    event_type: AttemptEvidenceEventType
    truth_kind: TruthKind
    authority: AttemptEvidenceAuthority
    references: tuple[EvidenceReference, ...] = Field(default=(), max_length=32)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def public_payload_is_safe(self) -> AttemptEvidenceInput:
        if (
            not _safe_public_value(self.payload)
            or len(canonical_json_bytes(self.payload)) > MAX_EVENT_PAYLOAD_BYTES
        ):
            raise ValueError("attempt evidence payload is unsafe or too large")
        keys = tuple((item.kind, item.id, item.sha256) for item in self.references)
        if len(keys) != len(set(keys)):
            raise ValueError("attempt evidence references must be unique")
        return self


class AttemptEvidenceEvent(AttemptEvidenceInput):
    schema_version: Literal[1] = 1
    evidence_id: Identifier
    event_id: Identifier
    seq: int = Field(ge=1)
    server_recorded_at: UtcDateTime
    idempotency_key: IdempotencyKey
    payload_sha256: Sha256
    previous_event_sha256: Sha256 | None
    event_sha256: Sha256

    @model_validator(mode="after")
    def hashes_are_canonical(self) -> AttemptEvidenceEvent:
        if self.payload_sha256 != canonical_json_sha256(self.payload):
            raise ValueError("attempt payload digest does not match")
        if (self.seq == 1) != (self.previous_event_sha256 is None):
            raise ValueError("only first attempt evidence may omit previous digest")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"event_sha256"})
        )
        if self.event_sha256 != expected:
            raise ValueError("attempt evidence digest does not match")
        return self


class AttemptEvidenceHead(FrozenModel):
    evidence_id: Identifier
    seq: int = Field(ge=0)
    event_sha256: Sha256 | None
    event_count: int = Field(ge=0)

    @model_validator(mode="after")
    def fields_agree(self) -> AttemptEvidenceHead:
        if self.seq != self.event_count or (self.seq == 0) != (
            self.event_sha256 is None
        ):
            raise ValueError("attempt evidence head fields disagree")
        return self


class AttemptArtifact(FrozenModel):
    schema_version: Literal[1] = 1
    artifact_id: Identifier
    kind: Identifier
    sha256: Sha256
    byte_count: int = Field(ge=0, le=MAX_ARTIFACT_BYTES)
    visibility: ArtifactVisibility


class AttemptEvidenceStoreError(RuntimeError):
    pass


class AttemptEvidenceConflict(AttemptEvidenceStoreError):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempt_evidence_heads (
    evidence_id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL CHECK (seq >= 0),
    event_sha256 TEXT,
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    mission_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    terminal INTEGER NOT NULL CHECK (terminal IN (0, 1))
);

CREATE TABLE IF NOT EXISTS attempt_evidence_events (
    event_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES attempt_evidence_heads(evidence_id),
    seq INTEGER NOT NULL CHECK (seq >= 1),
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL,
    event_bytes BLOB NOT NULL,
    UNIQUE (evidence_id, seq),
    UNIQUE (evidence_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_attempt_evidence_tail
ON attempt_evidence_events(evidence_id, seq);

CREATE TRIGGER IF NOT EXISTS attempt_evidence_events_no_update
BEFORE UPDATE ON attempt_evidence_events BEGIN
    SELECT RAISE(ABORT, 'attempt evidence events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS attempt_evidence_events_no_delete
BEFORE DELETE ON attempt_evidence_events BEGIN
    SELECT RAISE(ABORT, 'attempt evidence events are append-only');
END;

CREATE TABLE IF NOT EXISTS attempt_artifacts (
    artifact_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    visibility TEXT NOT NULL,
    artifact_bytes BLOB NOT NULL
);
"""


class SQLiteAttemptEvidenceStore:
    """Generic v1 attempt evidence, semantically separate from Auth lineage v2."""

    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            raise ValueError("attempt evidence requires a durable SQLite path")
        self.path = str(path)
        with closing(self._connect()) as connection:
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise AttemptEvidenceStoreError("SQLite WAL mode is required")
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def empty_head(evidence_id: str) -> AttemptEvidenceHead:
        return AttemptEvidenceHead(
            evidence_id=evidence_id, seq=0, event_sha256=None, event_count=0
        )

    @staticmethod
    def _request_sha256(
        evidence_id: str,
        expected_head: AttemptEvidenceHead,
        idempotency_key: str,
        draft: AttemptEvidenceInput,
    ) -> str:
        return canonical_json_sha256(
            {
                "draft": draft.model_dump(mode="json"),
                "evidence_id": evidence_id,
                "expected_head": expected_head.model_dump(mode="json"),
                "idempotency_key": idempotency_key,
            }
        )

    @staticmethod
    def _event(
        evidence_id: str,
        head: AttemptEvidenceHead,
        idempotency_key: str,
        draft: AttemptEvidenceInput,
        recorded_at: datetime,
    ) -> AttemptEvidenceEvent:
        seq = head.seq + 1
        event_id = "attempt_event_" + canonical_json_sha256(
            {
                "evidence_id": evidence_id,
                "idempotency_key": idempotency_key,
                "seq": seq,
            }
        )[:32]
        core = {
            **{
                name: getattr(draft, name)
                for name in AttemptEvidenceInput.model_fields
            },
            "schema_version": 1,
            "evidence_id": evidence_id,
            "event_id": event_id,
            "seq": seq,
            "server_recorded_at": recorded_at,
            "idempotency_key": idempotency_key,
            "payload_sha256": canonical_json_sha256(draft.payload),
            "previous_event_sha256": head.event_sha256,
        }
        canonical = AttemptEvidenceEvent.model_construct(
            **core, event_sha256="0" * 64
        ).model_dump(mode="json", exclude={"event_sha256"})
        return AttemptEvidenceEvent.model_validate(
            {**canonical, "event_sha256": canonical_json_sha256(canonical)}
        )

    def append(
        self,
        evidence_id: str,
        expected_head: AttemptEvidenceHead,
        idempotency_key: str,
        draft: AttemptEvidenceInput,
        *,
        recorded_at: datetime,
    ) -> AttemptEvidenceEvent:
        recorded_at = _UTC_TIME.validate_python(recorded_at)
        request_sha = self._request_sha256(
            evidence_id, expected_head, idempotency_key, draft
        )
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT request_sha256, event_bytes FROM attempt_evidence_events "
                    "WHERE evidence_id = ? AND idempotency_key = ?",
                    (evidence_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["request_sha256"] != request_sha:
                        raise AttemptEvidenceConflict(
                            "attempt evidence idempotency key was reused"
                        )
                    event = AttemptEvidenceEvent.model_validate_json(
                        existing["event_bytes"]
                    )
                    connection.commit()
                    return event

                row = connection.execute(
                    "SELECT * FROM attempt_evidence_heads WHERE evidence_id = ?",
                    (evidence_id,),
                ).fetchone()
                head = (
                    self.empty_head(evidence_id)
                    if row is None
                    else AttemptEvidenceHead(
                        evidence_id=evidence_id,
                        seq=row["seq"],
                        event_sha256=row["event_sha256"],
                        event_count=row["event_count"],
                    )
                )
                if head != expected_head:
                    raise AttemptEvidenceConflict("attempt evidence head changed")
                if row is not None and row["terminal"]:
                    raise AttemptEvidenceConflict("attempt evidence is terminal")
                if head.seq == 0 and draft.event_type != AttemptEvidenceEventType.ATTEMPT_STARTED:
                    raise AttemptEvidenceConflict("attempt evidence must start with attempt.started")
                if head.seq > 0 and row is not None and (
                    row["mission_id"], row["task_id"], row["attempt_id"]
                ) != (draft.mission_id, draft.task_id, draft.attempt_id):
                    raise AttemptEvidenceConflict("attempt evidence identity changed")
                for reference in draft.references:
                    content = self.resolve(reference.kind, reference.id)
                    if content is None or sha256_hex(content) != reference.sha256:
                        raise AttemptEvidenceConflict("attempt artifact reference is unresolved")

                event = self._event(
                    evidence_id, head, idempotency_key, draft, recorded_at
                )
                terminal = event.event_type in {
                    AttemptEvidenceEventType.ATTEMPT_COMPLETED,
                    AttemptEvidenceEventType.ATTEMPT_FAILED,
                }
                if row is None:
                    connection.execute(
                        "INSERT INTO attempt_evidence_heads VALUES (?, 0, NULL, 0, ?, ?, ?, 0)",
                        (evidence_id, draft.mission_id, draft.task_id, draft.attempt_id),
                    )
                event_bytes = canonical_json_bytes(event.model_dump(mode="json"))
                connection.execute(
                    "INSERT INTO attempt_evidence_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        evidence_id,
                        event.seq,
                        idempotency_key,
                        request_sha,
                        event.event_sha256,
                        event_bytes,
                    ),
                )
                updated = connection.execute(
                    "UPDATE attempt_evidence_heads SET seq = ?, event_sha256 = ?, "
                    "event_count = event_count + 1, terminal = ? "
                    "WHERE evidence_id = ? AND seq = ? AND event_count = ? "
                    "AND event_sha256 IS ?",
                    (
                        event.seq,
                        event.event_sha256,
                        int(terminal),
                        evidence_id,
                        head.seq,
                        head.event_count,
                        head.event_sha256,
                    ),
                )
                if updated.rowcount != 1:
                    raise AttemptEvidenceConflict("attempt evidence CAS failed")
                connection.commit()
                return event
            except Exception:
                connection.rollback()
                raise

    def head(self, evidence_id: str) -> AttemptEvidenceHead:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT seq, event_sha256, event_count FROM attempt_evidence_heads "
                "WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        return (
            self.empty_head(evidence_id)
            if row is None
            else AttemptEvidenceHead(
                evidence_id=evidence_id,
                seq=row["seq"],
                event_sha256=row["event_sha256"],
                event_count=row["event_count"],
            )
        )

    def tail(
        self, evidence_id: str, after_seq: int, limit: int
    ) -> tuple[AttemptEvidenceEvent, ...]:
        if type(after_seq) is not int or after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("limit must be between 1 and 256")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT event_bytes FROM attempt_evidence_events "
                "WHERE evidence_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (evidence_id, after_seq, limit),
            ).fetchall()
        return tuple(
            AttemptEvidenceEvent.model_validate_json(row["event_bytes"])
            for row in rows
        )

    def verify(self, evidence_id: str) -> AttemptEvidenceHead:
        head = self.head(evidence_id)
        events: list[AttemptEvidenceEvent] = []
        after = 0
        while after < head.seq:
            batch = self.tail(evidence_id, after, min(256, head.seq - after))
            if not batch:
                raise AttemptEvidenceStoreError("attempt evidence is incomplete")
            events.extend(batch)
            after = batch[-1].seq
        previous: str | None = None
        identity: tuple[str, str, str] | None = None
        for seq, event in enumerate(events, 1):
            current = (event.mission_id, event.task_id, event.attempt_id)
            identity = identity or current
            if (
                event.seq != seq
                or event.previous_event_sha256 != previous
                or current != identity
            ):
                raise AttemptEvidenceStoreError("attempt evidence chain is invalid")
            if seq == 1 and event.event_type != AttemptEvidenceEventType.ATTEMPT_STARTED:
                raise AttemptEvidenceStoreError("attempt evidence start is invalid")
            for reference in event.references:
                content = self.resolve(reference.kind, reference.id)
                if content is None or sha256_hex(content) != reference.sha256:
                    raise AttemptEvidenceStoreError("attempt artifact is unavailable")
            previous = event.event_sha256
        if len(events) != head.event_count or previous != head.event_sha256:
            raise AttemptEvidenceStoreError("attempt evidence head is invalid")
        return head

    def verify_attempt(
        self,
        evidence_id: str,
        *,
        mission_id: str,
        task_id: str,
        attempt_id: str,
        succeeded: bool,
        references: tuple[EvidenceReference, ...],
    ) -> bool:
        head = self.verify(evidence_id)
        if head.seq == 0:
            return False
        tail = self.tail(evidence_id, head.seq - 1, 1)
        if len(tail) != 1:
            return False
        terminal = tail[0]
        recorded = {
            (item.kind, item.id, item.sha256) for item in terminal.references
        }
        required = {(item.kind, item.id, item.sha256) for item in references}
        return (
            terminal.event_type
            == (
                AttemptEvidenceEventType.ATTEMPT_COMPLETED
                if succeeded
                else AttemptEvidenceEventType.ATTEMPT_FAILED
            )
            and (
                terminal.mission_id,
                terminal.task_id,
                terminal.attempt_id,
            )
            == (mission_id, task_id, attempt_id)
            and required <= recorded
        )

    def put_artifact(
        self,
        kind: str,
        content: bytes,
        *,
        visibility: ArtifactVisibility = ArtifactVisibility.PRIVATE,
    ) -> EvidenceReference:
        if not isinstance(content, bytes) or len(content) > MAX_ARTIFACT_BYTES:
            raise ValueError("attempt artifact must be bounded bytes")
        digest = sha256_hex(content)
        artifact_id = f"artifact_{digest[:32]}"
        artifact = AttemptArtifact(
            artifact_id=artifact_id,
            kind=kind,
            sha256=digest,
            byte_count=len(content),
            visibility=visibility,
        )
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT OR IGNORE INTO attempt_artifacts VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        artifact.artifact_id,
                        artifact.kind,
                        artifact.sha256,
                        artifact.byte_count,
                        artifact.visibility.value,
                        content,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM attempt_artifacts WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchone()
                if row is None or (
                    row["kind"], row["sha256"], row["visibility"], row["artifact_bytes"]
                ) != (kind, digest, visibility.value, content):
                    raise AttemptEvidenceConflict("attempt artifact collision")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return EvidenceReference(kind=kind, id=artifact_id, sha256=digest)

    def resolve(self, kind: str, artifact_id: str) -> bytes | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT kind, sha256, byte_count, artifact_bytes FROM attempt_artifacts "
                "WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None or row["kind"] != kind:
            return None
        content = row["artifact_bytes"]
        return (
            content
            if isinstance(content, bytes)
            and len(content) == row["byte_count"]
            and sha256_hex(content) == row["sha256"]
            else None
        )
