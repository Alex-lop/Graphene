from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import Any

from ..hashing import canonical_json_bytes, sha256_hex
from ..models import EvidenceKind, EvidenceReference
from .store import LineageConflict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_artifacts (
    artifact_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    artifact_bytes BLOB NOT NULL
);
"""

_SOURCE_ARTIFACT_KINDS = {
    "adk_event_receipt": frozenset({"adk_event_receipt"}),
    "context_compiler_receipt": frozenset(
        {"context_brief", "handoff_decision", "injection_receipt", "policy_receipt"}
    ),
    "lifecycle_request": frozenset({"operator_request"}),
    "operator_request": frozenset({"operator_request"}),
    "policy_evaluation": frozenset({"policy_receipt"}),
    "promotion_receipt": frozenset({"promotion_receipt"}),
    "reducer_receipt": frozenset({"changeset", "evidence_blob", "test_receipt"}),
    "tool_receipt": frozenset({"tool_receipt"}),
}


class SQLiteArtifactStore:
    """Private, digest-addressed JSON artifacts for one local lineage database."""

    def __init__(
        self,
        path: str | Path,
        *,
        read_only: bool = False,
        immutable: bool = False,
    ) -> None:
        if str(path) == ":memory:":
            raise ValueError("the artifact store requires a durable SQLite path")
        self.path = str(path)
        self._read_only = read_only
        if immutable and not read_only:
            raise ValueError("immutable mode requires a read-only artifact store")
        self._immutable = immutable
        with closing(self._connect()) as connection:
            if read_only:
                if connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'lineage_artifacts'"
                ).fetchone() is None:
                    raise LineageConflict("lineage artifact table is missing")
                return
            connection.execute("PRAGMA journal_mode=WAL")
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
        if self._read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.execute("PRAGMA synchronous=FULL")
        return connection

    def __call__(
        self,
        kind: EvidenceKind,
        record: Mapping[str, Any],
    ) -> EvidenceReference:
        if self._read_only:
            raise LineageConflict("read-only artifact stores cannot record artifacts")
        raw = canonical_json_bytes(dict(record))
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:32]}"
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT OR IGNORE INTO lineage_artifacts VALUES (?, ?, ?, ?)",
                    (artifact_id, kind.value, digest, raw),
                )
                row = connection.execute(
                    "SELECT kind, sha256, artifact_bytes FROM lineage_artifacts "
                    "WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchone()
                if row is None or (row["kind"], row["sha256"], row["artifact_bytes"]) != (
                    kind.value,
                    digest,
                    raw,
                ):
                    raise LineageConflict("artifact ID collision or conflicting replay")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return EvidenceReference(kind=kind, id=artifact_id, sha256=digest)

    def resolve(self, kind: str, artifact_id: str) -> bytes | None:
        """Resolve exact evidence kinds or the frozen source-to-artifact aliases."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT kind, sha256, artifact_bytes FROM lineage_artifacts "
                "WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if (
            row is None
            or not isinstance(row["artifact_bytes"], bytes)
            or (
                row["kind"] != kind
                and row["kind"] not in _SOURCE_ARTIFACT_KINDS.get(kind, ())
            )
        ):
            return None
        raw = row["artifact_bytes"]
        try:
            canonical = canonical_json_bytes(json.loads(raw))
        except (TypeError, ValueError, UnicodeError):
            return None
        return raw if canonical == raw and sha256_hex(raw) == row["sha256"] else None
