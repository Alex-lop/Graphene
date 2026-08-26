"""A mission store handle that cannot write, by construction.

`SQLiteMissionStore.__init__` runs the schema script and `_connect` opens a
read-write connection; a viewer must do neither. This subclass opens the
database with SQLite's `mode=ro` URI flag and `PRAGMA query_only=ON` on every
connection, keeps the schema-ledger check (a viewer over a foreign schema
should refuse, not guess), and inherits every read method unchanged: the
projection, `snapshot`, `head`, `tail`, and `integrity_marker` all go through
`_connect`, so they inherit the read-only guarantee. Any write attempt raises
`sqlite3.OperationalError` from SQLite itself, which is what
`tests/unit/ui/test_read_only.py` proves.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock

from ..hashing import sha256_hex
from ..orchestration.evidence import SQLiteAttemptEvidenceStore
from ..orchestration.mission_models import Mission, MissionStatus
from ..orchestration.sqlite_mission_store import (
    _SCHEMA,
    _SCHEMA_VERSION,
    MissionStoreError,
    SQLiteMissionStore,
)

ACTIVE_STATUSES = frozenset(
    {MissionStatus.PROPOSED, MissionStatus.RUNNING, MissionStatus.PAUSED, MissionStatus.AWAITING_RESULT}
)


class ReadOnlyMissionStore(SQLiteMissionStore):
    """Read the mission store without the ability to change it."""

    def __init__(self, path: str | Path) -> None:
        if not Path(path).is_file():
            raise MissionStoreError(f"no mission store at {path}")
        self.path = str(path)
        self.artifact_resolver = None
        self.local_commit_verifier = None
        self.final_bundle_verifier = None
        self._integrity_monitor = None
        self._integrity_monitor_pid = None
        self._integrity_monitor_lock = RLock()
        with closing(self._connect()) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version != _SCHEMA_VERSION:
                raise MissionStoreError(f"unsupported mission schema version {version}")
            migration = connection.execute(
                "SELECT schema_sha256 FROM schema_migrations WHERE version = ?",
                (_SCHEMA_VERSION,),
            ).fetchone()
            if migration is None or migration["schema_sha256"] != sha256_hex(_SCHEMA.encode("utf-8")):
                raise MissionStoreError("mission schema ledger does not match code")

    def _connect(self) -> sqlite3.Connection:
        uri = Path(self.path).resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA query_only=ON")
        return connection

    def mission_ids(self) -> tuple[str, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT mission_id FROM missions ORDER BY mission_id").fetchall()
        return tuple(str(row["mission_id"]) for row in rows)

    def most_recent_active_mission(self) -> str | None:
        """The active mission with the latest event; None when nothing is active."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT m.mission_id, m.status, m.mission_bytes, "
                "(SELECT MAX(seq) FROM mission_events e WHERE e.mission_id = m.mission_id) AS last_seq "
                "FROM missions m"
            ).fetchall()
        candidates = []
        for row in rows:
            if str(row["status"]) not in {status.value for status in ACTIVE_STATUSES}:
                continue
            created = Mission.model_validate_json(row["mission_bytes"]).created_at
            candidates.append((created, int(row["last_seq"] or 0), str(row["mission_id"])))
        if not candidates:
            return None
        return max(candidates)[2]


class ReadOnlyAttemptEvidenceStore(SQLiteAttemptEvidenceStore):
    """The evidence resolver the viewer binds: `mode=ro`, no schema script."""

    def __init__(self, path: str | Path) -> None:
        if not Path(path).is_file():
            raise MissionStoreError(f"no attempt evidence store at {path}")
        self.path = str(path)
        self._lock = RLock()
        with closing(self._connect()) as connection:
            connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()

    def _connect(self) -> sqlite3.Connection:
        uri = Path(self.path).resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA query_only=ON")
        return connection
