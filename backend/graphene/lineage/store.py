from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..models import (
    Event,
    EventInput,
    EvidenceInvalidState,
    HeadCheckpoint,
    LineageEventType,
    VerifiedHead,
)

ArtifactResolver = Callable[[str, str], bytes | None]
CheckpointReader = Callable[[str], Iterable[HeadCheckpoint]]

_EVENT_INPUT_FIELDS = set(EventInput.model_fields)
_NO_APPEND_AFTER = frozenset({LineageEventType.RUN_INTERRUPTED})
_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_heads (
    run_id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL CHECK (seq >= 0),
    event_sha256 TEXT,
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    repo_id TEXT NOT NULL,
    base_sha TEXT NOT NULL,
    agent_profile_id TEXT NOT NULL,
    policy_revision INTEGER NOT NULL CHECK (policy_revision >= 1),
    CHECK ((seq = 0 AND event_sha256 IS NULL AND event_count = 0)
        OR (seq > 0 AND event_sha256 IS NOT NULL AND event_count > 0))
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_heads(run_id),
    seq INTEGER NOT NULL CHECK (seq >= 1),
    idempotency_key TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    previous_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL,
    event_bytes BLOB NOT NULL,
    request_sha256 TEXT NOT NULL,
    request_bytes BLOB NOT NULL,
    UNIQUE (run_id, seq),
    UNIQUE (run_id, idempotency_key)
);
"""


class LineageStoreError(RuntimeError):
    pass


class LineageConflict(LineageStoreError):
    pass


class EvidenceInvalid(LineageStoreError):
    def __init__(self, state: EvidenceInvalidState) -> None:
        self.state = state
        super().__init__(f"lineage evidence is invalid: {state.reason}")


def _new_event_id() -> str:
    return f"event_{uuid.uuid4().hex}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _invalid(run_id: str, reason: str, seq: int | None = None) -> EvidenceInvalidState:
    return EvidenceInvalidState(run_id=run_id, first_invalid_seq=seq, reason=reason)


def _canonical_object(raw: object) -> dict[str, object]:
    if not isinstance(raw, bytes):
        raise ValueError("stored value is not a byte string")
    value = json.loads(raw)
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise ValueError("stored bytes are not canonical JSON")
    return value


class SQLiteLineageStore:
    """Durable append-only lineage events backed by one SQLite file."""

    def __init__(
        self,
        path: str | Path,
        *,
        artifact_resolver: ArtifactResolver,
        checkpoint_reader: CheckpointReader | None = None,
        read_only: bool = False,
        immutable: bool = False,
    ) -> None:
        if str(path) == ":memory:":
            raise ValueError("the lineage store requires a durable SQLite path")
        self.path = str(path)
        self._artifact_resolver = artifact_resolver
        self._checkpoint_reader = checkpoint_reader or (lambda _run_id: ())
        self._read_only = read_only
        if immutable and not read_only:
            raise ValueError("immutable mode requires a read-only lineage store")
        self._immutable = immutable
        with closing(self._connect()) as connection:
            if read_only:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                if not {"run_heads", "events"} <= tables:
                    raise LineageStoreError("lineage tables are missing")
                return
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise LineageStoreError("SQLite WAL mode is required")
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        target = (
            Path(self.path).resolve().as_uri()
            + ("?mode=ro&immutable=1" if self._immutable else "?mode=ro")
            if self._read_only
            else self.path
        )
        connection = sqlite3.connect(
            target,
            isolation_level=None,
            timeout=5,
            uri=self._read_only,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        if self._read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _artifact(self, kind: str, artifact_id: str) -> bytes | None:
        try:
            value = self._artifact_resolver(kind, artifact_id)
        except Exception:
            return None
        return value if isinstance(value, bytes) else None

    @staticmethod
    def _request_bytes(
        run_id: str,
        expected_head: VerifiedHead,
        idempotency_key: str,
        draft: EventInput,
    ) -> bytes:
        return canonical_json_bytes(
            {
                "draft": draft.model_dump(mode="json"),
                "expected_head": expected_head.model_dump(mode="json"),
                "idempotency_key": idempotency_key,
                "run_id": run_id,
            }
        )

    @staticmethod
    def _event(
        run_id: str,
        head: VerifiedHead,
        idempotency_key: str,
        draft: EventInput,
    ) -> Event:
        fields = {
            **{name: getattr(draft, name) for name in _EVENT_INPUT_FIELDS},
            "schema_version": 2,
            "event_id": _new_event_id(),
            "run_id": run_id,
            "seq": head.seq + 1,
            "server_recorded_at": _now(),
            "idempotency_key": idempotency_key,
            "payload_sha256": canonical_json_sha256(draft.payload),
            "previous_event_sha256": head.event_sha256,
        }
        canonical = Event.model_construct(
            **fields,
            event_sha256="0" * 64,
        ).model_dump(mode="json", exclude={"event_sha256"})
        return Event.model_validate(
            {**canonical, "event_sha256": canonical_json_sha256(canonical)}
        )

    def _verify_connection(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> tuple[VerifiedHead | EvidenceInvalidState, tuple[Event, ...]]:
        # ponytail: full scans suit bounded MVP runs; verify trusted prefixes if volume grows.
        head_row = connection.execute(
            "SELECT * FROM run_heads WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        rows = connection.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
        if head_row is None:
            if rows:
                return _invalid(run_id, "events exist without a run head"), ()
            return VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0), ()
        if not rows:
            return _invalid(run_id, "run head exists without events"), ()

        events: list[Event] = []
        previous_sha256: str | None = None
        identity: tuple[object, ...] | None = None
        for expected_seq, row in enumerate(rows, 1):
            if row["seq"] != expected_seq:
                return _invalid(run_id, "event sequence is not contiguous", expected_seq), ()
            try:
                value = _canonical_object(row["event_bytes"])
                event = Event.model_validate(value)
                if canonical_json_bytes(event.model_dump(mode="json")) != row["event_bytes"]:
                    raise ValueError("event bytes do not round-trip canonically")
            except (TypeError, ValueError, UnicodeError):
                return _invalid(run_id, "stored event bytes are malformed", expected_seq), ()

            row_values = (
                row["event_id"],
                row["run_id"],
                row["seq"],
                row["idempotency_key"],
                row["payload_sha256"],
                row["previous_event_sha256"],
                row["event_sha256"],
            )
            event_values = (
                event.event_id,
                event.run_id,
                event.seq,
                event.idempotency_key,
                event.payload_sha256,
                event.previous_event_sha256,
                event.event_sha256,
            )
            if row_values != event_values or event.run_id != run_id:
                return _invalid(run_id, "event index does not match its canonical bytes", expected_seq), ()
            if event.previous_event_sha256 != previous_sha256:
                return _invalid(run_id, "event digest chain is broken", expected_seq), ()
            if expected_seq == 1 and event.event_type != LineageEventType.RUN_STARTED:
                return _invalid(run_id, "first event is not run.started", expected_seq), ()

            current_identity = (
                event.repo_id,
                event.base_sha,
                event.agent_profile_id,
                event.policy_revision,
            )
            identity = identity or current_identity
            if current_identity != identity:
                return _invalid(run_id, "run identity changed within the event stream", expected_seq), ()

            references = (*event.references, event.source_ref)
            for reference in references:
                if reference.kind == "event":
                    resolved = next(
                        (
                            item.event_sha256
                            for item in events
                            if item.event_id == reference.id
                        ),
                        None,
                    )
                    if resolved != reference.sha256:
                        return _invalid(run_id, "event reference is unresolved", expected_seq), ()
                    continue
                artifact = self._artifact(reference.kind.value, reference.id)
                if artifact is None or sha256_hex(artifact) != reference.sha256:
                    return _invalid(run_id, "artifact reference is unresolved", expected_seq), ()

            try:
                request = _canonical_object(row["request_bytes"])
                request_head = VerifiedHead.model_validate(request["expected_head"])
                request_draft = EventInput.model_validate(request["draft"])
            except (KeyError, TypeError, ValueError, UnicodeError):
                return _invalid(run_id, "stored idempotency request is malformed", expected_seq), ()
            if (
                set(request) != {"draft", "expected_head", "idempotency_key", "run_id"}
                or sha256_hex(row["request_bytes"]) != row["request_sha256"]
                or request["run_id"] != run_id
                or request["idempotency_key"] != event.idempotency_key
                or request_head.model_dump(mode="json") != request["expected_head"]
                or request_draft.model_dump(mode="json") != request["draft"]
                or request_head
                != VerifiedHead(
                    run_id=run_id,
                    seq=expected_seq - 1,
                    event_sha256=previous_sha256,
                    event_count=expected_seq - 1,
                )
                or request_draft.model_dump(mode="json")
                != event.model_dump(mode="json", include=_EVENT_INPUT_FIELDS)
            ):
                return _invalid(run_id, "idempotency request is not reciprocal", expected_seq), ()

            events.append(event)
            previous_sha256 = event.event_sha256

        if identity != (
            head_row["repo_id"],
            head_row["base_sha"],
            head_row["agent_profile_id"],
            head_row["policy_revision"],
        ):
            return _invalid(run_id, "run head identity does not match its events"), ()
        verified = VerifiedHead(
            run_id=run_id,
            seq=len(events),
            event_sha256=previous_sha256,
            event_count=len(events),
        )
        if (
            head_row["seq"],
            head_row["event_sha256"],
            head_row["event_count"],
        ) != (verified.seq, verified.event_sha256, verified.event_count):
            return _invalid(run_id, "stored run head does not match the event stream"), ()
        by_seq = {event.seq: event for event in events}
        try:
            checkpoints = tuple(self._checkpoint_reader(run_id))
        except Exception:
            return _invalid(run_id, "checkpoint reader failed"), ()
        for raw_checkpoint in checkpoints:
            try:
                checkpoint = HeadCheckpoint.model_validate(raw_checkpoint)
            except (TypeError, ValueError):
                return _invalid(run_id, "checkpoint is malformed"), ()
            artifact = self._artifact(
                checkpoint.bound_artifact_kind.value,
                checkpoint.bound_artifact_id,
            )
            if (
                checkpoint.run_id != run_id
                or checkpoint.expected_seq not in by_seq
                or by_seq[checkpoint.expected_seq].event_sha256
                != checkpoint.event_head_sha256
                or artifact is None
                or sha256_hex(artifact) != checkpoint.bound_artifact_sha256
            ):
                return _invalid(run_id, "checkpointed prefix is unresolved"), ()
        return verified, tuple(events)

    def append(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        idempotency_key: str,
        draft: EventInput,
    ) -> Event:
        if self._read_only:
            raise LineageStoreError("read-only lineage stores cannot append events")
        if not isinstance(expected_head, VerifiedHead) or not isinstance(draft, EventInput):
            raise TypeError("append requires validated EventInput and VerifiedHead values")
        if expected_head.run_id != run_id:
            raise LineageConflict("expected head belongs to a different run")
        request_bytes = self._request_bytes(
            run_id,
            expected_head,
            idempotency_key,
            draft,
        )

        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                state, events = self._verify_connection(connection, run_id)
                if isinstance(state, EvidenceInvalidState):
                    raise EvidenceInvalid(state)
                existing = next(
                    (event for event in events if event.idempotency_key == idempotency_key),
                    None,
                )
                if existing is not None:
                    stored = connection.execute(
                        "SELECT request_bytes, request_sha256 FROM events WHERE event_id = ?",
                        (existing.event_id,),
                    ).fetchone()
                    if (
                        stored is None
                        or stored["request_bytes"] != request_bytes
                        or stored["request_sha256"] != sha256_hex(request_bytes)
                    ):
                        raise LineageConflict("idempotency key was reused for another request")
                    connection.commit()
                    return existing
                if state != expected_head:
                    raise LineageConflict("expected head does not match the committed head")
                if events and events[-1].event_type in _NO_APPEND_AFTER:
                    raise LineageConflict("interrupted runs cannot accept later events")
                for reference in (*draft.references, draft.source_ref):
                    if reference.kind == "event":
                        resolved = next(
                            (
                                event.event_sha256
                                for event in events
                                if event.event_id == reference.id
                            ),
                            None,
                        )
                        if resolved != reference.sha256:
                            raise EvidenceInvalid(
                                _invalid(
                                    run_id,
                                    "event reference is unresolved",
                                    state.seq + 1,
                                )
                            )
                        continue
                    artifact = self._artifact(
                        reference.kind.value,
                        reference.id,
                    )
                    if artifact is None or sha256_hex(artifact) != reference.sha256:
                        raise EvidenceInvalid(
                            _invalid(
                                run_id,
                                "artifact reference is unresolved",
                                state.seq + 1,
                            )
                        )
                if state.seq == 0:
                    if draft.event_type != LineageEventType.RUN_STARTED:
                        raise LineageConflict("the first event must be run.started")
                    connection.execute(
                        """
                        INSERT INTO run_heads (
                            run_id, seq, event_sha256, event_count,
                            repo_id, base_sha, agent_profile_id, policy_revision
                        ) VALUES (?, 0, NULL, 0, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            draft.repo_id,
                            draft.base_sha,
                            draft.agent_profile_id,
                            draft.policy_revision,
                        ),
                    )
                else:
                    head_row = connection.execute(
                        "SELECT repo_id, base_sha, agent_profile_id, policy_revision "
                        "FROM run_heads WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()
                    if (
                        draft.event_type == LineageEventType.RUN_STARTED
                        or head_row is None
                        or (
                            draft.repo_id,
                            draft.base_sha,
                            draft.agent_profile_id,
                            draft.policy_revision,
                        )
                        != tuple(head_row)
                    ):
                        raise LineageConflict("event does not match the frozen run identity")

                event = self._event(run_id, state, idempotency_key, draft)
                event_bytes = canonical_json_bytes(event.model_dump(mode="json"))
                try:
                    connection.execute(
                        """
                        INSERT INTO events (
                            event_id, run_id, seq, idempotency_key, payload_sha256,
                            previous_event_sha256, event_sha256, event_bytes,
                            request_sha256, request_bytes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.event_id,
                            run_id,
                            event.seq,
                            idempotency_key,
                            event.payload_sha256,
                            event.previous_event_sha256,
                            event.event_sha256,
                            event_bytes,
                            sha256_hex(request_bytes),
                            request_bytes,
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    raise LineageConflict("event uniqueness constraint rejected the append") from error
                updated = connection.execute(
                    """
                    UPDATE run_heads
                    SET seq = ?, event_sha256 = ?, event_count = event_count + 1
                    WHERE run_id = ? AND seq = ? AND event_count = ?
                        AND event_sha256 IS ?
                    """,
                    (
                        event.seq,
                        event.event_sha256,
                        run_id,
                        state.seq,
                        state.event_count,
                        state.event_sha256,
                    ),
                )
                if updated.rowcount != 1:
                    raise LineageConflict("run head changed during append")
                connection.commit()
                return event
            except Exception:
                connection.rollback()
                raise

    def verify(self, run_id: str) -> VerifiedHead | EvidenceInvalidState:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            try:
                state, _ = self._verify_connection(connection, run_id)
                connection.commit()
                return state
            except Exception:
                connection.rollback()
                raise

    def tail(
        self,
        run_id: str,
        after_seq: int,
        limit: int,
    ) -> tuple[Event, ...]:
        if type(after_seq) is not int or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("limit must be between 1 and 256")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            try:
                state, events = self._verify_connection(connection, run_id)
                if isinstance(state, EvidenceInvalidState):
                    raise EvidenceInvalid(state)
                result = tuple(event for event in events if event.seq > after_seq)[:limit]
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise
