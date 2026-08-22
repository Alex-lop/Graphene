"""The isolated shadow store.

Shadow observations live in their own SQLite file with their own
`PRAGMA user_version` and schema ledger. The discipline mirrors the mission
store: WAL is required, an unknown or altered schema fails closed, and every
persisted event is the canonical bytes of a verified `shadow.event.v1` record.
Nothing here is mission authority, and the mission store never reads it.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from .events import ShadowEvent, session_sha256

SHADOW_SCHEMA_VERSION = 1
SHADOW_DB_FILENAME = "shadow.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version >= 1),
    schema_sha256 TEXT NOT NULL,
    note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shadow_sessions (
    shadow_id TEXT PRIMARY KEY,
    adapter TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_adapter TEXT NOT NULL,
    source_adapter_version TEXT NOT NULL,
    session_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_bytes INTEGER NOT NULL CHECK (source_bytes >= 0),
    event_count INTEGER NOT NULL CHECK (event_count >= 1),
    session_sha256 TEXT NOT NULL,
    repo_label TEXT,
    ingested_at TEXT NOT NULL,
    summary_bytes BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS shadow_events (
    shadow_id TEXT NOT NULL REFERENCES shadow_sessions(shadow_id),
    seq INTEGER NOT NULL CHECK (seq >= 1),
    event_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    provenance TEXT NOT NULL,
    event_bytes BLOB NOT NULL,
    PRIMARY KEY (shadow_id, seq),
    UNIQUE (shadow_id, event_id)
);
"""


class ShadowStoreError(RuntimeError):
    pass


class ShadowNotFound(ShadowStoreError):
    pass


class ShadowConflict(ShadowStoreError):
    pass


class ShadowSessionRecord:
    __slots__ = (
        "shadow_id",
        "adapter",
        "adapter_version",
        "source_adapter",
        "source_adapter_version",
        "session_id",
        "source_sha256",
        "source_bytes",
        "event_count",
        "session_sha256",
        "repo_label",
        "ingested_at",
        "summary",
    )

    def __init__(self, row: sqlite3.Row) -> None:
        self.shadow_id = row["shadow_id"]
        self.adapter = row["adapter"]
        self.adapter_version = row["adapter_version"]
        self.source_adapter = row["source_adapter"]
        self.source_adapter_version = row["source_adapter_version"]
        self.session_id = row["session_id"]
        self.source_sha256 = row["source_sha256"]
        self.source_bytes = row["source_bytes"]
        self.event_count = row["event_count"]
        self.session_sha256 = row["session_sha256"]
        self.repo_label = row["repo_label"]
        self.ingested_at = row["ingested_at"]
        self.summary = json.loads(bytes(row["summary_bytes"]).decode("utf-8"))

    def to_dict(self) -> dict[str, object]:
        return {
            "shadow_id": self.shadow_id,
            "adapter": self.adapter,
            "adapter_version": self.adapter_version,
            "source_adapter": self.source_adapter,
            "source_adapter_version": self.source_adapter_version,
            "session_id": self.session_id,
            "source_sha256": self.source_sha256,
            "source_bytes": self.source_bytes,
            "event_count": self.event_count,
            "session_sha256": self.session_sha256,
            "repo_label": self.repo_label,
            "ingested_at": self.ingested_at,
            "summary": self.summary,
        }


def shadow_id_for(adapter: str, adapter_version: str, session_digest: str) -> str:
    """Deterministic identifier: the same normalized stream yields the same ID."""

    return (
        "shadow_"
        + canonical_json_sha256(
            {
                "adapter": adapter,
                "adapter_version": adapter_version,
                "session_sha256": session_digest,
            }
        )[:32]
    )


class ShadowStore:
    """Append-only observation store, separate from mission authority."""

    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            raise ValueError("shadow state requires a durable SQLite path")
        target = Path(path)
        if not target.is_absolute():
            raise ShadowStoreError("shadow store path must be absolute")
        if target.is_symlink():
            raise ShadowStoreError("shadow store path cannot be a symlink")
        if target.exists() and not stat.S_ISREG(target.lstat().st_mode):
            raise ShadowStoreError("shadow store path must be a regular file")
        created = not target.exists()
        self.path = str(target)
        with closing(self._connect()) as connection:
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise ShadowStoreError("SQLite WAL mode is required")
            existing = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'shadow_sessions'"
            ).fetchone()
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if existing is not None and version == 0:
                raise ShadowStoreError("shadow store has tables but no schema version")
            if existing is None and version != 0:
                raise ShadowStoreError(
                    f"shadow store declares schema version {version} without its tables"
                )
            if version not in {0, SHADOW_SCHEMA_VERSION}:
                raise ShadowStoreError(f"unsupported shadow schema version {version}")
            connection.executescript(_SCHEMA)
            schema_sha256 = sha256_hex(_SCHEMA.encode("utf-8"))
            if version == 0:
                connection.execute(
                    "INSERT INTO shadow_schema_migrations VALUES (?, ?, ?)",
                    (SHADOW_SCHEMA_VERSION, schema_sha256, "fresh-shadow-v1"),
                )
                connection.execute(f"PRAGMA user_version={SHADOW_SCHEMA_VERSION}")
            else:
                migration = connection.execute(
                    "SELECT schema_sha256 FROM shadow_schema_migrations "
                    "WHERE version = ?",
                    (SHADOW_SCHEMA_VERSION,),
                ).fetchone()
                if migration is None or migration["schema_sha256"] != schema_sha256:
                    raise ShadowStoreError("shadow schema ledger does not match code")
        if created:
            os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    # -- writes -----------------------------------------------------------

    def ingest(
        self,
        events: list[ShadowEvent] | tuple[ShadowEvent, ...],
        *,
        adapter: str,
        adapter_version: str,
        source_sha256: str,
        source_bytes: int,
        repo_label: str | None,
        summary: dict[str, object],
        now: datetime | None = None,
    ) -> tuple[str, bool]:
        """Persist one verified session. Returns (shadow_id, created).

        Re-ingesting a stream that normalizes to the same events is idempotent
        and returns the existing identifier without rewriting anything.
        `adapter` is the ingesting adapter; the events' `source` names the
        emitter, which may differ, but must be one adapter for the whole stream.
        """

        if not events:
            raise ShadowStoreError("a shadow session must contain at least one event")
        first = events[0]
        if not isinstance(first, ShadowEvent):
            raise ShadowStoreError("only verified shadow events can be stored")
        session_id = first.session_id
        source = first.source
        for index, event in enumerate(events, start=1):
            if not isinstance(event, ShadowEvent):
                raise ShadowStoreError("only verified shadow events can be stored")
            if event.seq != index:
                raise ShadowStoreError(
                    f"shadow event seq {event.seq} breaks contiguity at {index}"
                )
            if event.session_id != session_id:
                raise ShadowStoreError(
                    "shadow session identifiers must not change mid-stream"
                )
            if (
                event.source.adapter != source.adapter
                or event.source.adapter_version != source.adapter_version
            ):
                raise ShadowStoreError(
                    "every event must share one source.adapter "
                    "and source.adapter_version"
                )
        digest = session_sha256(event.event_id for event in events)
        shadow_id = shadow_id_for(adapter, adapter_version, digest)
        ingested_at = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary_bytes = canonical_json_bytes(summary)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT * FROM shadow_sessions WHERE shadow_id = ?", (shadow_id,)
                ).fetchone()
                if existing is not None:
                    if existing["session_sha256"] != digest or existing[
                        "event_count"
                    ] != len(events):
                        raise ShadowConflict(
                            f"shadow session {shadow_id} exists with different content"
                        )
                    connection.execute("COMMIT")
                    return shadow_id, False
                connection.execute(
                    "INSERT INTO shadow_sessions ("
                    "shadow_id, adapter, adapter_version, source_adapter, "
                    "source_adapter_version, session_id, source_sha256, source_bytes, "
                    "event_count, session_sha256, repo_label, ingested_at, "
                    "summary_bytes"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        shadow_id,
                        adapter,
                        adapter_version,
                        source.adapter,
                        source.adapter_version,
                        session_id,
                        source_sha256,
                        source_bytes,
                        len(events),
                        digest,
                        repo_label,
                        ingested_at,
                        summary_bytes,
                    ),
                )
                connection.executemany(
                    "INSERT INTO shadow_events VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            shadow_id,
                            event.seq,
                            event.event_id,
                            event.kind,
                            event.provenance,
                            canonical_json_bytes(event.to_record()),
                        )
                        for event in events
                    ],
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return shadow_id, True

    # -- reads ------------------------------------------------------------

    def session(self, shadow_id: str) -> ShadowSessionRecord:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM shadow_sessions WHERE shadow_id = ?", (shadow_id,)
            ).fetchone()
        if row is None:
            raise ShadowNotFound(f"unknown shadow session {shadow_id}")
        return ShadowSessionRecord(row)

    def sessions(self) -> list[ShadowSessionRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM shadow_sessions ORDER BY ingested_at, shadow_id"
            ).fetchall()
        return [ShadowSessionRecord(row) for row in rows]

    def events(self, shadow_id: str) -> tuple[ShadowEvent, ...]:
        """Load and re-verify every event; tampered bytes fail closed."""

        record = self.session(shadow_id)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT seq, event_id, kind, provenance, event_bytes "
                "FROM shadow_events WHERE shadow_id = ? ORDER BY seq",
                (shadow_id,),
            ).fetchall()
        events: list[ShadowEvent] = []
        for index, row in enumerate(rows, start=1):
            raw = bytes(row["event_bytes"])
            try:
                event = ShadowEvent.model_validate(json.loads(raw.decode("utf-8")))
            except ValueError as error:
                raise ShadowStoreError(
                    f"shadow event {shadow_id}#{row['seq']} failed verification"
                ) from error
            if (
                event.seq != index
                or event.seq != row["seq"]
                or event.event_id != row["event_id"]
                or event.kind != row["kind"]
                or event.provenance != row["provenance"]
                or canonical_json_bytes(event.to_record()) != raw
            ):
                raise ShadowStoreError(
                    f"shadow event {shadow_id}#{row['seq']} "
                    "index disagrees with its record"
                )
            events.append(event)
        if len(events) != record.event_count:
            raise ShadowStoreError(f"shadow session {shadow_id} event count mismatch")
        if session_sha256(event.event_id for event in events) != record.session_sha256:
            raise ShadowStoreError(f"shadow session {shadow_id} digest mismatch")
        expected = shadow_id_for(
            record.adapter, record.adapter_version, record.session_sha256
        )
        if expected != shadow_id:
            raise ShadowStoreError(f"shadow session {shadow_id} identifier mismatch")
        return tuple(events)

    def verify(self, shadow_id: str) -> dict[str, object]:
        events = self.events(shadow_id)
        record = self.session(shadow_id)
        return {
            "shadow_id": shadow_id,
            "event_count": len(events),
            "session_sha256": record.session_sha256,
            "verified": True,
        }

    def status(self) -> dict[str, object]:
        with closing(self._connect()) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            ledger = connection.execute(
                "SELECT version, schema_sha256, note "
                "FROM shadow_schema_migrations ORDER BY version"
            ).fetchall()
            count = connection.execute(
                "SELECT COUNT(*) FROM shadow_sessions"
            ).fetchone()[0]
        return {
            "path": self.path,
            "schema_version": version,
            "ledger": [dict(row) for row in ledger],
            "session_count": count,
        }


__all__ = [
    "SHADOW_DB_FILENAME",
    "SHADOW_SCHEMA_VERSION",
    "ShadowConflict",
    "ShadowNotFound",
    "ShadowSessionRecord",
    "ShadowStore",
    "ShadowStoreError",
    "shadow_id_for",
]
