import sqlite3
from pathlib import Path

import pytest

from graphene.lineage import LineageConflict, SQLiteArtifactStore
from graphene.models import EvidenceKind


def test_private_artifacts_are_canonical_restart_safe_and_fail_closed(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    store = SQLiteArtifactStore(path)
    record = {"schema_version": 2, "content": "private source", "byte_count": 14}
    reference = store(EvidenceKind.EVIDENCE_BLOB, record)

    assert store(EvidenceKind.EVIDENCE_BLOB, record) == reference
    assert SQLiteArtifactStore(path).resolve(reference.kind.value, reference.id) is not None
    assert store.resolve("hunk", reference.id) is None

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE lineage_artifacts SET artifact_bytes = ? WHERE artifact_id = ?",
            (b'{"content":"tampered"}', reference.id),
        )
    assert store.resolve(reference.kind.value, reference.id) is None


def test_source_kind_aliases_are_explicit_and_fail_closed(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    store = SQLiteArtifactStore(path)
    policy = store(EvidenceKind.POLICY_RECEIPT, {"schema_version": 2})
    operator = store(EvidenceKind.OPERATOR_REQUEST, {"schema_version": 2})

    assert store.resolve("policy_evaluation", policy.id) is not None
    assert store.resolve("lifecycle_request", operator.id) is not None
    assert store.resolve("context_compiler_receipt", operator.id) is None
    assert store.resolve("unknown_kind", policy.id) is None


def test_read_only_artifact_store_resolves_without_writing(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    writable = SQLiteArtifactStore(path)
    reference = writable(EvidenceKind.EVIDENCE_BLOB, {"schema_version": 2})
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = set(tmp_path.iterdir())

    read_only = SQLiteArtifactStore(path, read_only=True)
    assert read_only.resolve(reference.kind.value, reference.id) is not None
    with pytest.raises(LineageConflict, match="read-only"):
        read_only(EvidenceKind.EVIDENCE_BLOB, {"schema_version": 2})
    assert set(tmp_path.iterdir()) == before
