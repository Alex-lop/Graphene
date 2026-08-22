"""Fail-closed behavior of the isolated shadow store.

Schema and row tampering is simulated through raw sqlite3 connections using
named columns only, so these tests keep passing when the session table gains
columns.
"""

from __future__ import annotations

import sqlite3
import stat
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from graphene.hashing import canonical_json_bytes
from graphene.shadow import store as store_module
from graphene.shadow.events import ShadowEvent, session_sha256
from graphene.shadow.store import (
    SHADOW_DB_FILENAME,
    SHADOW_SCHEMA_VERSION,
    ShadowConflict,
    ShadowNotFound,
    ShadowStore,
    ShadowStoreError,
    shadow_id_for,
)

ADAPTER = "ndjson"
VERSION = "1.0.0"
SOURCE_SHA256 = "5a" * 32
NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
SESSION_COLUMNS = {
    "shadow_id",
    "adapter",
    "adapter_version",
    "session_id",
    "source_sha256",
    "source_bytes",
    "event_count",
    "session_sha256",
    "repo_label",
    "ingested_at",
    "summary",
}


def _source(
    adapter: str = ADAPTER, version: str = VERSION, ref: str = "line:1"
) -> dict[str, str]:
    return {
        "adapter": adapter,
        "adapter_version": version,
        "record_ref": ref,
        "raw_type": "assistant_message",
    }


def _event(seq: int, **over: object) -> ShadowEvent:
    fields: dict[str, object] = {
        "session_id": "sess-1",
        "seq": seq,
        "ts": None,
        "actor": "agent",
        "kind": "message",
        "excerpt": f"message {seq}",
        "content_digest": f"{seq:02x}" * 32,
        "provenance": "observed",
        "source": _source(ref=f"line:{seq}"),
    }
    fields.update(over)
    return ShadowEvent.create(**fields)


def _stream(count: int = 3, **over: object) -> tuple[ShadowEvent, ...]:
    return tuple(_event(seq, **over) for seq in range(1, count + 1))


def _ingest(
    store: ShadowStore, events: tuple[ShadowEvent, ...], **over: object
) -> tuple[str, bool]:
    kwargs: dict[str, object] = {
        "adapter": ADAPTER,
        "adapter_version": VERSION,
        "source_sha256": SOURCE_SHA256,
        "source_bytes": 321,
        "repo_label": "graphene",
        "summary": {"event_count": len(events)},
        "now": NOW,
    }
    kwargs.update(over)
    return store.ingest(events, **kwargs)  # type: ignore[arg-type]


def _execute(path: Path, statement: str, *params: object) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(statement, params)
        connection.commit()


def _scalar(path: Path, statement: str, *params: object) -> object:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(statement, params).fetchone()[0]


def _rewrite_event(
    path: Path, shadow_id: str, seq: int, transform: Callable[[bytes], bytes]
) -> None:
    with closing(sqlite3.connect(path)) as connection:
        raw = connection.execute(
            "SELECT event_bytes FROM shadow_events WHERE shadow_id = ? AND seq = ?",
            (shadow_id, seq),
        ).fetchone()[0]
        connection.execute(
            "UPDATE shadow_events SET event_bytes = ? WHERE shadow_id = ? AND seq = ?",
            (transform(bytes(raw)), shadow_id, seq),
        )
        connection.commit()


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / SHADOW_DB_FILENAME


# -- creation and schema ledger ---------------------------------------------


def test_fresh_store_has_its_own_user_version_ledger_and_wal(store_path: Path) -> None:
    store = ShadowStore(store_path)

    assert SHADOW_SCHEMA_VERSION == 1
    assert store_path.is_file()
    assert _scalar(store_path, "PRAGMA user_version") == 1
    assert str(_scalar(store_path, "PRAGMA journal_mode")).lower() == "wal"
    status = store.status()
    assert status["path"] == str(store_path)
    assert status["schema_version"] == 1
    assert status["session_count"] == 0
    assert len(status["ledger"]) == 1
    ledger = status["ledger"][0]
    assert ledger["version"] == 1
    assert ledger["note"] == "fresh-shadow-v1"
    assert len(ledger["schema_sha256"]) == 64


def test_fresh_store_file_is_owner_only(store_path: Path) -> None:
    ShadowStore(store_path)

    assert stat.S_IMODE(store_path.stat().st_mode) == 0o600
    ShadowStore(store_path)
    assert stat.S_IMODE(store_path.stat().st_mode) == 0o600


def test_reopening_an_existing_store_keeps_its_sessions(store_path: Path) -> None:
    shadow_id, _ = _ingest(ShadowStore(store_path), _stream())

    reopened = ShadowStore(store_path)
    assert [record.shadow_id for record in reopened.sessions()] == [shadow_id]
    assert len(reopened.events(shadow_id)) == 3


def test_ledger_mismatch_fails_closed(store_path: Path) -> None:
    ShadowStore(store_path)
    _execute(
        store_path,
        "UPDATE shadow_schema_migrations SET schema_sha256 = ? WHERE version = 1",
        "0" * 64,
    )

    with pytest.raises(ShadowStoreError, match="ledger does not match code"):
        ShadowStore(store_path)


def test_missing_ledger_row_fails_closed(store_path: Path) -> None:
    ShadowStore(store_path)
    _execute(store_path, "DELETE FROM shadow_schema_migrations WHERE version = 1")

    with pytest.raises(ShadowStoreError, match="ledger does not match code"):
        ShadowStore(store_path)


def test_tables_without_version_fail_closed(store_path: Path) -> None:
    ShadowStore(store_path)
    _execute(store_path, "PRAGMA user_version=0")

    with pytest.raises(ShadowStoreError, match="tables but no schema version"):
        ShadowStore(store_path)


def test_version_without_tables_fails_closed(store_path: Path) -> None:
    _execute(store_path, "PRAGMA user_version=1")

    with pytest.raises(ShadowStoreError, match="schema version 1 without its tables"):
        ShadowStore(store_path)


def test_unsupported_version_fails_closed(store_path: Path) -> None:
    ShadowStore(store_path)
    _execute(store_path, "PRAGMA user_version=7")

    with pytest.raises(ShadowStoreError, match="unsupported shadow schema version 7"):
        ShadowStore(store_path)


# -- path discipline ---------------------------------------------------------


def test_symlink_path_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.sqlite3"
    ShadowStore(real)
    link = tmp_path / "link.sqlite3"
    link.symlink_to(real)
    dangling = tmp_path / "dangling.sqlite3"
    dangling.symlink_to(tmp_path / "absent.sqlite3")

    with pytest.raises(ShadowStoreError, match="cannot be a symlink"):
        ShadowStore(link)
    with pytest.raises(ShadowStoreError, match="cannot be a symlink"):
        ShadowStore(dangling)
    assert not (tmp_path / "absent.sqlite3").exists()


def test_relative_path_is_rejected() -> None:
    with pytest.raises(ShadowStoreError, match="must be absolute"):
        ShadowStore("shadow.sqlite3")
    with pytest.raises(ShadowStoreError, match="must be absolute"):
        ShadowStore(Path("state") / SHADOW_DB_FILENAME)
    assert not Path("shadow.sqlite3").exists()


def test_memory_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="durable SQLite path"):
        ShadowStore(":memory:")


def test_directory_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ShadowStoreError, match="regular file"):
        ShadowStore(tmp_path)


# -- ingest ------------------------------------------------------------------


def test_ingest_persists_a_session_and_its_events(store_path: Path) -> None:
    store = ShadowStore(store_path)
    events = _stream()

    shadow_id, created = _ingest(store, events, summary={"heuristics": {"x": "é"}})

    assert created is True
    expected_digest = session_sha256(event.event_id for event in events)
    assert shadow_id == shadow_id_for(ADAPTER, VERSION, expected_digest)
    assert shadow_id.startswith("shadow_")
    assert len(shadow_id) == len("shadow_") + 32
    record = store.session(shadow_id)
    assert record.shadow_id == shadow_id
    assert record.adapter == ADAPTER
    assert record.adapter_version == VERSION
    assert record.session_id == "sess-1"
    assert record.source_sha256 == SOURCE_SHA256
    assert record.source_bytes == 321
    assert record.event_count == 3
    assert record.session_sha256 == expected_digest
    assert record.repo_label == "graphene"
    assert record.ingested_at == "2026-08-22T10:00:00Z"
    assert record.summary == {"heuristics": {"x": "é"}}
    assert SESSION_COLUMNS <= set(record.to_dict())
    assert record.to_dict()["summary"] == {"heuristics": {"x": "é"}}
    assert store.events(shadow_id) == events
    assert store.status()["session_count"] == 1


def test_ingest_is_idempotent_for_the_same_normalized_stream(store_path: Path) -> None:
    store = ShadowStore(store_path)
    events = _stream()
    first_id, created = _ingest(store, events)

    second_id, created_again = _ingest(
        store,
        events,
        source_sha256="7b" * 32,
        source_bytes=999,
        summary={"different": True},
        now=NOW + timedelta(days=1),
    )

    assert created is True
    assert (second_id, created_again) == (first_id, False)
    record = store.session(first_id)
    assert record.source_sha256 == SOURCE_SHA256
    assert record.source_bytes == 321
    assert record.summary == {"event_count": 3}
    assert record.ingested_at == "2026-08-22T10:00:00Z"
    assert len(store.sessions()) == 1
    assert _scalar(store_path, "SELECT COUNT(*) FROM shadow_events") == 3


def test_shadow_id_is_deterministic_across_stores(tmp_path: Path) -> None:
    events = _stream()
    first, _ = _ingest(ShadowStore(tmp_path / "one.sqlite3"), events)
    second, _ = _ingest(ShadowStore(tmp_path / "two.sqlite3"), events)

    assert first == second
    digest = session_sha256(event.event_id for event in events)
    assert shadow_id_for(ADAPTER, "1.0.1", digest) != first
    assert shadow_id_for("claude-code", VERSION, digest) != first


def test_different_streams_get_different_sessions(store_path: Path) -> None:
    store = ShadowStore(store_path)
    first, _ = _ingest(store, _stream(), now=NOW)
    second, _ = _ingest(store, _stream(session_id="sess-2"), now=NOW + timedelta(1))

    assert first != second
    assert [record.shadow_id for record in store.sessions()] == [first, second]
    assert store.status()["session_count"] == 2


@pytest.mark.parametrize("column", ("event_count", "session_sha256"))
def test_conflicting_existing_row_is_detected(store_path: Path, column: str) -> None:
    store = ShadowStore(store_path)
    events = _stream()
    shadow_id, _ = _ingest(store, events)
    value = 4 if column == "event_count" else "0" * 64
    _execute(
        store_path,
        f"UPDATE shadow_sessions SET {column} = ? WHERE shadow_id = ?",
        value,
        shadow_id,
    )

    with pytest.raises(ShadowConflict, match="exists with different content"):
        _ingest(store, events)
    assert issubclass(ShadowConflict, ShadowStoreError)


def test_seq_contiguity_is_enforced(store_path: Path) -> None:
    store = ShadowStore(store_path)

    with pytest.raises(ShadowStoreError, match="seq 3 breaks contiguity at 2"):
        _ingest(store, (_event(1), _event(3)))
    with pytest.raises(ShadowStoreError, match="seq 2 breaks contiguity at 1"):
        _ingest(store, (_event(2), _event(3)))
    with pytest.raises(ShadowStoreError, match="seq 2 breaks contiguity at 1"):
        _ingest(store, (_event(2), _event(1)))
    assert store.sessions() == []


def test_session_id_must_not_change_mid_stream(store_path: Path) -> None:
    store = ShadowStore(store_path)

    with pytest.raises(ShadowStoreError, match="must not change mid-stream"):
        _ingest(store, (_event(1), _event(2, session_id="sess-2")))


def test_events_must_share_one_source_adapter(store_path: Path) -> None:
    store = ShadowStore(store_path)

    with pytest.raises(ShadowStoreError, match="adapter"):
        _ingest(store, (_event(1), _event(2, source=_source(adapter="other"))))
    with pytest.raises(ShadowStoreError, match="adapter"):
        _ingest(store, (_event(1), _event(2, source=_source(version="1.0.1"))))
    assert store.sessions() == []


def test_ingest_rejects_empty_streams_and_unverified_records(store_path: Path) -> None:
    store = ShadowStore(store_path)

    with pytest.raises(ShadowStoreError, match="at least one event"):
        _ingest(store, ())
    with pytest.raises(ShadowStoreError, match="only verified shadow events"):
        _ingest(store, (_event(1), _event(2).to_record()))  # type: ignore[arg-type]
    assert store.sessions() == []


def test_unverified_first_record_fails_with_a_precise_error(store_path: Path) -> None:
    store = ShadowStore(store_path)

    with pytest.raises(ShadowStoreError, match="only verified shadow events"):
        _ingest(store, (_event(1).to_record(),))  # type: ignore[arg-type]


def test_failed_ingest_persists_nothing(
    store_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ShadowStore(store_path)

    def exploding(value: object) -> bytes:
        if isinstance(value, dict) and value.get("seq") == 2:
            raise RuntimeError("disk full")
        return canonical_json_bytes(value)

    monkeypatch.setattr(store_module, "canonical_json_bytes", exploding)
    with pytest.raises(RuntimeError, match="disk full"):
        _ingest(store, _stream())

    assert _scalar(store_path, "SELECT COUNT(*) FROM shadow_sessions") == 0
    assert _scalar(store_path, "SELECT COUNT(*) FROM shadow_events") == 0


# -- reads re-verify ---------------------------------------------------------


def test_unknown_shadow_id_raises_not_found(store_path: Path) -> None:
    store = ShadowStore(store_path)

    with pytest.raises(ShadowNotFound, match="unknown shadow session shadow_nope"):
        store.session("shadow_nope")
    with pytest.raises(ShadowNotFound, match="unknown shadow session shadow_nope"):
        store.events("shadow_nope")
    assert issubclass(ShadowNotFound, ShadowStoreError)


def test_verify_reports_the_session_digest(store_path: Path) -> None:
    store = ShadowStore(store_path)
    events = _stream()
    shadow_id, _ = _ingest(store, events)

    assert store.verify(shadow_id) == {
        "shadow_id": shadow_id,
        "event_count": 3,
        "session_sha256": session_sha256(event.event_id for event in events),
        "verified": True,
    }


def test_events_are_stored_as_canonical_record_bytes(store_path: Path) -> None:
    store = ShadowStore(store_path)
    events = _stream()
    shadow_id, _ = _ingest(store, events)

    with closing(sqlite3.connect(store_path)) as connection:
        rows = connection.execute(
            "SELECT seq, event_id, kind, provenance, event_bytes FROM shadow_events "
            "WHERE shadow_id = ? ORDER BY seq",
            (shadow_id,),
        ).fetchall()
    assert [(row[0], row[1], row[2], row[3], bytes(row[4])) for row in rows] == [
        (
            event.seq,
            event.event_id,
            event.kind,
            event.provenance,
            canonical_json_bytes(event.to_record()),
        )
        for event in events
    ]


def test_tampered_event_content_fails_closed(store_path: Path) -> None:
    store = ShadowStore(store_path)
    shadow_id, _ = _ingest(store, _stream())
    _rewrite_event(
        store_path,
        shadow_id,
        2,
        lambda raw: raw.replace(b"message 2", b"message 2 (edited)"),
    )

    with pytest.raises(ShadowStoreError, match=f"{shadow_id}#2 failed verification"):
        store.events(shadow_id)
    with pytest.raises(ShadowStoreError, match="failed verification"):
        store.verify(shadow_id)


@pytest.mark.parametrize(
    "transform",
    (
        pytest.param(lambda raw: b"{", id="invalid-json"),
        pytest.param(lambda raw: b"\xff" + raw, id="invalid-utf8"),
        pytest.param(lambda raw: b"[" + raw + b"]", id="not-an-object"),
    ),
)
def test_unreadable_event_blob_fails_closed(
    store_path: Path, transform: Callable[[bytes], bytes]
) -> None:
    store = ShadowStore(store_path)
    shadow_id, _ = _ingest(store, _stream())
    _rewrite_event(store_path, shadow_id, 3, transform)

    with pytest.raises(ShadowStoreError, match=f"{shadow_id}#3 failed verification"):
        store.events(shadow_id)


def test_non_canonical_but_valid_blob_fails_closed(store_path: Path) -> None:
    store = ShadowStore(store_path)
    shadow_id, _ = _ingest(store, _stream())
    _rewrite_event(store_path, shadow_id, 1, lambda raw: raw.replace(b",", b", ", 1))

    with pytest.raises(ShadowStoreError, match=f"{shadow_id}#1 index disagrees"):
        store.events(shadow_id)


@pytest.mark.parametrize(
    ("statement", "message"),
    (
        (
            "UPDATE shadow_events SET kind = 'tool_call' WHERE seq = 2",
            "#2 index disagrees with its record",
        ),
        (
            "UPDATE shadow_events SET provenance = 'inferred' WHERE seq = 2",
            "#2 index disagrees with its record",
        ),
        (
            "UPDATE shadow_events SET seq = 4 WHERE seq = 3",
            "#4 index disagrees with its record",
        ),
        (
            "DELETE FROM shadow_events WHERE seq = 3",
            "event count mismatch",
        ),
        (
            "UPDATE shadow_sessions SET session_sha256 = '" + "0" * 64 + "'",
            "digest mismatch",
        ),
        (
            "UPDATE shadow_sessions SET adapter_version = '9.9.9'",
            "identifier mismatch",
        ),
    ),
)
def test_tampered_index_columns_fail_closed(
    store_path: Path, statement: str, message: str
) -> None:
    store = ShadowStore(store_path)
    shadow_id, _ = _ingest(store, _stream())
    _execute(store_path, statement)

    with pytest.raises(ShadowStoreError, match=message):
        store.events(shadow_id)


def test_swapped_event_ids_fail_closed(store_path: Path) -> None:
    store = ShadowStore(store_path)
    events = _stream()
    shadow_id, _ = _ingest(store, events)
    _execute(
        store_path,
        "UPDATE shadow_events SET event_id = ? WHERE seq = 1",
        "0" * 64,
    )

    with pytest.raises(ShadowStoreError, match=f"{shadow_id}#1 index disagrees"):
        store.events(shadow_id)
