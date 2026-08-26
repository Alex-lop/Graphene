from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import graphene.lineage.sqlite_lineage_store as store_module
import graphene.lineage.lineage_reducer as reducer_module
import pytest
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.lineage import EvidenceInvalid, LineageConflict, SQLiteLineageStore
from graphene.core_models import (
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    HeadCheckpoint,
    LineageAuthority,
    LineageEventType,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

BASE_SHA = "a" * 40
SOURCE_BYTES = canonical_json_bytes({"request": "fixture"})
SOURCE_SHA = sha256_hex(SOURCE_BYTES)


def _store(path: Path) -> SQLiteLineageStore:
    return SQLiteLineageStore(
        path,
        artifact_resolver=lambda kind, id: (
            SOURCE_BYTES if (kind, id) == ("lifecycle_request", "request_001") else None
        ),
    )


def _head(run_id: str) -> VerifiedHead:
    return VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0)


def _draft(
    event_type: LineageEventType = LineageEventType.RUN_STARTED,
    **changes,
) -> EventInput:
    values = {
        "session_id": None,
        "invocation_id": None,
        "model_id": None,
        "tool_call_id": None,
        "repo_id": "graphene-demo",
        "base_sha": BASE_SHA,
        "agent_profile_id": "auth-maintainer@1",
        "policy_revision": 1,
        "event_type": event_type,
        "truth_kind": TruthKind.SERVER_DERIVED,
        "authority": LineageAuthority.LIFECYCLE_SERVICE,
        "references": (),
        "source_ref": SourceReference(
            kind="lifecycle_request",
            id="request_001",
            sha256=SOURCE_SHA,
        ),
        "payload": {"state": event_type.value},
    }
    return EventInput.model_validate({**values, **changes})


def _append_three(store: SQLiteLineageStore, run_id: str = "run_001"):
    first = store.append(run_id, _head(run_id), "idempotency_key_001", _draft())
    second = store.append(
        run_id,
        VerifiedHead(
            run_id=run_id,
            seq=1,
            event_sha256=first.event_sha256,
            event_count=1,
        ),
        "idempotency_key_002",
        _draft(LineageEventType.MEMORY_PROPOSED, payload={}),
    )
    third = store.append(
        run_id,
        VerifiedHead(
            run_id=run_id,
            seq=2,
            event_sha256=second.event_sha256,
            event_count=2,
        ),
        "idempotency_key_003",
        _draft(LineageEventType.MEMORY_PROPOSED, payload={}),
    )
    return first, second, third


def test_append_tail_exact_idempotency_and_restart(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    store = _store(path)
    empty = _head("run_001")
    draft = _draft()
    event = store.append("run_001", empty, "idempotency_key_001", draft)

    assert event.schema_version == 2
    assert event.seq == 1
    assert event.previous_event_sha256 is None
    assert store.append("run_001", empty, "idempotency_key_001", draft) == event
    assert store.tail("run_001", 0, 256) == (event,)
    assert store.verify("run_001") == VerifiedHead(
        run_id="run_001",
        seq=1,
        event_sha256=event.event_sha256,
        event_count=1,
    )

    reopened = _store(path)
    assert reopened.tail("run_001", 0, 1) == (event,)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        raw = connection.execute("SELECT event_bytes FROM events").fetchone()[0]
        assert raw == canonical_json_bytes(event.model_dump(mode="json"))
    connection = store._connect()
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        connection.close()


def test_idempotency_reuse_and_stale_cas_fail_closed(tmp_path: Path):
    store = _store(tmp_path / "lineage.sqlite3")
    empty = _head("run_001")
    first = store.append("run_001", empty, "idempotency_key_001", _draft())
    with pytest.raises(LineageConflict, match="idempotency"):
        store.append(
            "run_001",
            empty,
            "idempotency_key_001",
            _draft(payload={"state": "different"}),
        )
    current = VerifiedHead(
        run_id="run_001",
        seq=1,
        event_sha256=first.event_sha256,
        event_count=1,
    )
    with pytest.raises(LineageConflict, match="idempotency"):
        store.append("run_001", current, "idempotency_key_001", _draft())
    with pytest.raises(LineageConflict, match="committed head"):
        store.append(
            "run_001",
            empty,
            "idempotency_key_002",
            _draft(LineageEventType.RUN_ENDED),
        )


def test_first_event_and_run_identity_are_frozen(tmp_path: Path):
    store = _store(tmp_path / "lineage.sqlite3")
    with pytest.raises(LineageConflict, match="first event"):
        store.append(
            "run_001",
            _head("run_001"),
            "idempotency_key_001",
            _draft(LineageEventType.RUN_ENDED),
        )
    first = store.append(
        "run_001",
        _head("run_001"),
        "idempotency_key_002",
        _draft(),
    )
    current = VerifiedHead(
        run_id="run_001",
        seq=1,
        event_sha256=first.event_sha256,
        event_count=1,
    )
    for field, value in (
        ("repo_id", "other-repo"),
        ("base_sha", "c" * 40),
        ("agent_profile_id", "platform-maintainer@1"),
        ("policy_revision", 2),
    ):
        with pytest.raises(LineageConflict, match="frozen run identity"):
            store.append(
                "run_001",
                current,
                f"identity_change_{field}_001",
                _draft(LineageEventType.RUN_ENDED, **{field: value}),
            )


def test_concurrent_exact_retry_returns_one_committed_event(tmp_path: Path):
    store = _store(tmp_path / "lineage.sqlite3")
    expected = _head("run_001")
    draft = _draft()

    def append():
        return store.append("run_001", expected, "concurrent_retry_001", draft)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = tuple(pool.map(lambda _: append(), range(2)))
    assert first == second
    assert store.tail("run_001", 0, 256) == (first,)


def test_interrupted_run_rejects_later_events_but_allows_exact_replay(tmp_path: Path):
    store = _store(tmp_path / "lineage.sqlite3")
    first = store.append(
        "run_001", _head("run_001"), "interrupt_start_001", _draft()
    )
    current = VerifiedHead(
        run_id="run_001",
        seq=1,
        event_sha256=first.event_sha256,
        event_count=1,
    )
    draft = _draft(LineageEventType.RUN_INTERRUPTED)
    interrupted = store.append(
        "run_001", current, "interrupt_event_001", draft
    )

    assert store.append(
        "run_001", current, "interrupt_event_001", draft
    ) == interrupted
    with pytest.raises(LineageConflict, match="interrupted"):
        store.append(
            "run_001",
            VerifiedHead(
                run_id="run_001",
                seq=2,
                event_sha256=interrupted.event_sha256,
                event_count=2,
            ),
            "late_event_key_001",
            _draft(LineageEventType.RUN_FAILED),
        )
    assert store.tail("run_001", 0, 256) == (first, interrupted)


def test_event_ids_are_globally_unique(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = _store(tmp_path / "lineage.sqlite3")
    monkeypatch.setattr(store_module, "_new_event_id", lambda: "event_fixed_global_id")
    store.append("run_001", _head("run_001"), "idempotency_key_001", _draft())

    with pytest.raises(LineageConflict, match="uniqueness"):
        store.append("run_002", _head("run_002"), "idempotency_key_002", _draft())
    assert store.verify("run_002") == _head("run_002")


@pytest.mark.parametrize("tamper", ["gap", "reorder", "event", "request", "head"])
def test_verify_rejects_corruption_without_returning_a_partial_tail(
    tmp_path: Path,
    tamper: str,
):
    path = tmp_path / "lineage.sqlite3"
    store = _store(path)
    _append_three(store)
    with sqlite3.connect(path) as connection:
        if tamper == "gap":
            connection.execute(
                "UPDATE events SET seq = 4 WHERE run_id = 'run_001' AND seq = 2"
            )
        elif tamper == "reorder":
            second, third = connection.execute(
                "SELECT event_bytes FROM events WHERE run_id = 'run_001' "
                "AND seq IN (2, 3) ORDER BY seq"
            ).fetchall()
            connection.execute(
                "UPDATE events SET event_bytes = ? WHERE run_id = 'run_001' AND seq = 2",
                (third[0],),
            )
            connection.execute(
                "UPDATE events SET event_bytes = ? WHERE run_id = 'run_001' AND seq = 3",
                (second[0],),
            )
        elif tamper == "event":
            raw = connection.execute(
                "SELECT event_bytes FROM events WHERE run_id = 'run_001' AND seq = 2"
            ).fetchone()[0]
            value = json.loads(raw)
            value["payload"]["tampered"] = True
            connection.execute(
                "UPDATE events SET event_bytes = ? WHERE run_id = 'run_001' AND seq = 2",
                (canonical_json_bytes(value),),
            )
        elif tamper == "request":
            connection.execute(
                "UPDATE events SET request_sha256 = ? "
                "WHERE run_id = 'run_001' AND seq = 2",
                ("0" * 64,),
            )
        else:
            connection.execute(
                "UPDATE run_heads SET event_sha256 = ? WHERE run_id = 'run_001'",
                ("0" * 64,),
            )

    invalid = store.verify("run_001")
    assert isinstance(invalid, EvidenceInvalidState)
    with pytest.raises(EvidenceInvalid) as error:
        store.tail("run_001", 0, 256)
    assert error.value.state == invalid


def test_tail_limits_and_expected_run_are_validated(tmp_path: Path):
    store = _store(tmp_path / "lineage.sqlite3")
    with pytest.raises(LineageConflict, match="different run"):
        store.append("run_001", _head("run_002"), "idempotency_key_001", _draft())
    with pytest.raises(ValueError, match="after_seq"):
        store.tail("run_001", -1, 1)
    with pytest.raises(ValueError, match="limit"):
        store.tail("run_001", 0, 0)
    with pytest.raises(ValueError, match="limit"):
        store.tail("run_001", 0, 257)


def test_references_are_resolved_before_commit_and_on_replay(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    artifacts = {("lifecycle_request", "request_001"): SOURCE_BYTES}
    store = SQLiteLineageStore(
        path,
        artifact_resolver=lambda kind, id: artifacts.get((kind, id)),
    )
    event = store.append("run_001", _head("run_001"), "idempotency_key_001", _draft())
    artifacts.clear()

    assert isinstance(store.verify("run_001"), EvidenceInvalidState)
    artifacts[("lifecycle_request", "request_001")] = SOURCE_BYTES
    bad = _draft(
        LineageEventType.RUN_ENDED,
        references=(
            EvidenceReference(kind="event", id="missing_event", sha256="0" * 64),
        ),
    )
    with pytest.raises(EvidenceInvalid, match="event reference"):
        store.append(
            "run_001",
            VerifiedHead(
                run_id="run_001",
                seq=1,
                event_sha256=event.event_sha256,
                event_count=1,
            ),
            "idempotency_key_002",
            bad,
        )
    assert store.verify("run_001").seq == 1


def test_forged_local_result_receipt_is_rejected_on_append_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    artifacts = {("lifecycle_request", "request_001"): SOURCE_BYTES}

    def artifact(kind: EvidenceKind, artifact_id: str, value: dict[str, object]):
        raw = canonical_json_bytes(value)
        artifacts[(kind.value, artifact_id)] = raw
        return EvidenceReference(kind=kind, id=artifact_id, sha256=sha256_hex(raw))

    store = SQLiteLineageStore(
        tmp_path / "lineage.sqlite3",
        artifact_resolver=lambda kind, artifact_id: artifacts.get((kind, artifact_id)),
    )
    started = store.append("run_001", _head("run_001"), "forged_start_001", _draft())
    approval_source = artifact(
        EvidenceKind.OPERATOR_REQUEST,
        "approval_source_001",
        {"action": "promotion.approved"},
    )
    approval = store.append(
        "run_001",
        VerifiedHead(
            run_id="run_001",
            seq=1,
            event_sha256=started.event_sha256,
            event_count=1,
        ),
        "forged_approval_001",
        _draft(
            LineageEventType.PROMOTION_APPROVED,
            truth_kind=TruthKind.HUMAN_ATTESTED,
            authority=LineageAuthority.OPERATOR_REQUEST,
            source_ref=SourceReference(
                kind="operator_request",
                id=approval_source.id,
                sha256=approval_source.sha256,
            ),
            payload={
                "candidate_patch_sha256": "1" * 64,
                "decision_id": "decision_001",
                "decision_sha256": "2" * 64,
                "expected_head_sha256": started.event_sha256,
                "status": "approved",
            },
        ),
    )
    promotion_reference = artifact(
        EvidenceKind.PROMOTION_RECEIPT,
        "promotion_receipt_001",
        {"result": "promoted"},
    )
    promotion = store.append(
        "run_001",
        VerifiedHead(
            run_id="run_001",
            seq=2,
            event_sha256=approval.event_sha256,
            event_count=2,
        ),
        "forged_promotion_001",
        _draft(
            LineageEventType.PROMOTION_COMPLETED,
            authority=LineageAuthority.PROMOTION_SERVICE,
            references=(
                EvidenceReference(
                    kind=EvidenceKind.EVENT,
                    id=approval.event_id,
                    sha256=approval.event_sha256,
                ),
                promotion_reference,
            ),
            source_ref=SourceReference(
                kind="promotion_receipt",
                id=promotion_reference.id,
                sha256=promotion_reference.sha256,
            ),
            payload={
                "candidate_patch_sha256": "1" * 64,
                "promotion_receipt_id": promotion_reference.id,
                "promotion_receipt_sha256": "3" * 64,
                "status": "completed",
            },
        ),
    )
    test_reference = artifact(
        EvidenceKind.TEST_RECEIPT, "test_receipt_001", {"passed": True}
    )
    local_reference = artifact(
        EvidenceKind.LOCAL_COMMIT_RECEIPT,
        "local_commit_receipt_001",
        {"result": "verified"},
    )
    local = _draft(
        LineageEventType.LOCAL_RESULT_RECORDED,
        truth_kind=TruthKind.RUNTIME_OBSERVED,
        authority=LineageAuthority.LOCAL_COMMIT_SERVICE,
        references=(
            EvidenceReference(
                kind=EvidenceKind.EVENT,
                id=approval.event_id,
                sha256=approval.event_sha256,
            ),
            promotion_reference,
            test_reference,
            local_reference,
        ),
        source_ref=SourceReference(
            kind="local_commit_receipt",
            id=local_reference.id,
            sha256=local_reference.sha256,
        ),
        payload={
            "approval_event_id": approval.event_id,
            "approval_event_sha256": approval.event_sha256,
            "candidate_patch_sha256": "1" * 64,
            "candidate_tree_sha256": "4" * 64,
            "candidate_tree_hash_version": "graphene.tree.v2",
            "changed_paths": ["app/auth/limiter.py"],
            "deployed": False,
            "local_commit_receipt_id": local_reference.id,
            "local_commit_receipt_sha256": local_reference.sha256,
            "local_commit_sha": "5" * 40,
            "outcome": "local_isolated_commit",
            "parent_sha": BASE_SHA,
            "pull_request_created": False,
            "pushed": False,
            "status": "recorded",
            "test_receipt_id": test_reference.id,
            "test_receipt_sha256": test_reference.sha256,
            "tree_sha": "6" * 40,
        },
    )

    with pytest.raises(EvidenceInvalid, match="semantic artifacts"):
        store.append(
            "run_001",
            VerifiedHead(
                run_id="run_001",
                seq=3,
                event_sha256=promotion.event_sha256,
                event_count=3,
            ),
            "forged_local_result_001",
            local,
        )
    assert store.verify("run_001").seq == 3

    validate = reducer_module.validate_semantic_artifacts
    monkeypatch.setattr(reducer_module, "validate_semantic_artifacts", lambda *_: None)
    store.append(
        "run_001",
        VerifiedHead(
            run_id="run_001",
            seq=3,
            event_sha256=promotion.event_sha256,
            event_count=3,
        ),
        "forged_local_result_001",
        local,
    )
    monkeypatch.setattr(reducer_module, "validate_semantic_artifacts", validate)
    replay = store.verify("run_001")
    assert isinstance(replay, EvidenceInvalidState)
    assert replay.reason.endswith("local result semantic artifacts are invalid")


def test_retained_checkpoint_binds_prefix_and_artifact(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    brief = canonical_json_bytes({"brief_id": "brief_001"})
    artifacts = {
        ("lifecycle_request", "request_001"): SOURCE_BYTES,
        ("context_brief", "brief_001"): brief,
    }
    checkpoints: list[HeadCheckpoint] = []
    store = SQLiteLineageStore(
        path,
        artifact_resolver=lambda kind, id: artifacts.get((kind, id)),
        checkpoint_reader=lambda _run_id: checkpoints,
    )
    event = store.append("run_001", _head("run_001"), "idempotency_key_001", _draft())
    payload = {
        "schema_version": 2,
        "checkpoint_id": "checkpoint_001",
        "run_id": "run_001",
        "expected_seq": 1,
        "event_head_sha256": event.event_sha256,
        "purpose": "handoff",
        "bound_artifact_kind": "context_brief",
        "bound_artifact_id": "brief_001",
        "bound_artifact_sha256": sha256_hex(brief),
        "server_recorded_at": datetime(2026, 8, 12, tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    checkpoints.append(
        HeadCheckpoint(
            **payload,
            checkpoint_sha256=canonical_json_sha256(payload),
        )
    )
    assert store.verify("run_001").event_sha256 == event.event_sha256

    artifacts[("context_brief", "brief_001")] = b"mutated"
    invalid = store.verify("run_001")
    assert isinstance(invalid, EvidenceInvalidState)
    assert invalid.reason == "checkpointed prefix is unresolved"
