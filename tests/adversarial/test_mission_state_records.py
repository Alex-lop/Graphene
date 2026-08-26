from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import timedelta

import pytest

from graphene.hashing import canonical_json_bytes
from graphene.core_models import TruthKind
from graphene.orchestration.mission_models import Gate, GateDecision, TaskKind
from graphene.orchestration.sqlite_mission_store import MissionStoreError, SQLiteMissionStore
from tests.unit.orchestration.test_store import (
    NOW,
    _artifacts,
    _command,
    _create,
    _success,
)

MISSION_ID = "mission-1"
Mutation = Callable[[sqlite3.Connection], None]


def _sql(statement: str, parameters: tuple[object, ...] = ()) -> Mutation:
    return lambda connection: connection.execute(statement, parameters)


def _rewrite_json(
    connection: sqlite3.Connection,
    *,
    table: str,
    column: str,
    selector: str,
    rewrite: Callable[[dict[str, object]], None],
) -> None:
    row = connection.execute(
        f"SELECT rowid, {column} FROM {table} WHERE {selector} ORDER BY rowid LIMIT 1"
    ).fetchone()
    assert row is not None
    value = json.loads(row[1])
    rewrite(value)
    connection.execute(
        f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
        (canonical_json_bytes(value), row[0]),
    )


def _artifact_reference(connection: sqlite3.Connection) -> None:
    def rewrite(value: dict[str, object]) -> None:
        references = value["evidence_refs"]
        assert isinstance(references, list) and references
        references[0]["sha256"] = "f" * 64

    _rewrite_json(
        connection,
        table="mission_attempts",
        column="attempt_bytes",
        selector="mission_id = 'mission-1'",
        rewrite=rewrite,
    )


def _json_value(
    *, table: str, column: str, selector: str, key: str, value: object
) -> Mutation:
    return lambda connection: _rewrite_json(
        connection,
        table=table,
        column=column,
        selector=selector,
        rewrite=lambda document: document.__setitem__(key, value),
    )


def _attempt_evidence_link(connection: sqlite3.Connection) -> None:
    def rewrite(value: dict[str, object]) -> None:
        evidence_link = value["evidence_link"]
        assert isinstance(evidence_link, dict)
        evidence_link["evidence_id"] = "evidence-forged"

    _rewrite_json(
        connection,
        table="mission_attempts",
        column="attempt_bytes",
        selector="mission_id = 'mission-1'",
        rewrite=rewrite,
    )


def _publication_digest(connection: sqlite3.Connection) -> None:
    _rewrite_json(
        connection,
        table="mission_publications",
        column="publication_bytes",
        selector="mission_id = 'mission-1'",
        rewrite=lambda value: value.__setitem__("sha256", "f" * 64),
    )


SQL_MUTATIONS = {
    "mission-status": (
        "UPDATE missions SET status='failed' WHERE mission_id='mission-1'"
    ),
    "mission-final-outcome": (
        "UPDATE missions SET final_outcome='forged' WHERE mission_id='mission-1'"
    ),
    "task-state": (
        "UPDATE mission_tasks SET state='failed' "
        "WHERE mission_id='mission-1' AND task_id='work-b'"
    ),
    "task-blocker": (
        "UPDATE mission_tasks SET blocker='forged' "
        "WHERE mission_id='mission-1' AND task_id='work-b'"
    ),
    "task-attempt-count": (
        "UPDATE mission_tasks SET attempt_count=attempt_count+1 "
        "WHERE mission_id='mission-1' AND task_id='work-b'"
    ),
    "task-accepted-attempt": (
        "UPDATE mission_tasks SET accepted_attempt_id=NULL "
        "WHERE mission_id='mission-1' AND task_id='work-a'"
    ),
    "task-extra-row": (
        "INSERT INTO mission_tasks SELECT mission_id,plan_revision,'forged-extra',"
        "kind,state,priority,attempt_limit,attempt_count,fencing_counter,retry_at,"
        "blocker,accepted_attempt_id,task_bytes,task_contract_event_sha256 "
        "FROM mission_tasks WHERE mission_id='mission-1' AND task_id='verify'"
    ),
    "task-missing-row": (
        "DELETE FROM mission_tasks WHERE mission_id='mission-1' AND task_id='verify'"
    ),
    "dependency-altered": (
        "UPDATE mission_dependencies SET satisfied_attempt_id=NULL "
        "WHERE mission_id='mission-1' AND task_id='assemble' AND dependency_id='work-a'"
    ),
    "dependency-extra-row": (
        "INSERT INTO mission_dependencies VALUES('mission-1',1,'verify','work-a',NULL)"
    ),
    "dependency-missing-row": (
        "DELETE FROM mission_dependencies WHERE mission_id='mission-1' "
        "AND task_id='verify' AND dependency_id='assemble'"
    ),
    "attempt-scalar": (
        "UPDATE mission_attempts SET state='failed' WHERE mission_id='mission-1'"
    ),
    "attempt-bytes": (
        "UPDATE mission_attempts SET attempt_bytes=attempt_bytes||X'20' "
        "WHERE mission_id='mission-1'"
    ),
    "attempt-missing-row": "DELETE FROM mission_attempts WHERE mission_id='mission-1'",
    "lease-owner": (
        "UPDATE mission_leases SET owner='worker-forged' WHERE mission_id='mission-1'"
    ),
    "lease-expiry": (
        "UPDATE mission_leases SET expires_at='2099-01-01T00:00:00+00:00' "
        "WHERE mission_id='mission-1'"
    ),
    "lease-release": (
        "UPDATE mission_leases SET released_at=NULL WHERE mission_id='mission-1'"
    ),
    "lease-fence": (
        "UPDATE mission_leases SET fencing_token=fencing_token+1 "
        "WHERE mission_id='mission-1'"
    ),
    "lease-bytes": (
        "UPDATE mission_leases SET lease_bytes=lease_bytes||X'20' "
        "WHERE mission_id='mission-1'"
    ),
    "lease-missing-row": "DELETE FROM mission_leases WHERE mission_id='mission-1'",
    "publication-kind": (
        "UPDATE mission_publications SET kind='forged' WHERE mission_id='mission-1'"
    ),
    "publication-state": (
        "UPDATE mission_publications SET state='rejected' WHERE mission_id='mission-1'"
    ),
    "publication-extra-row": (
        "INSERT INTO mission_publications SELECT 'publication-forged',mission_id,"
        "plan_revision,task_id,attempt_id,'forged-output',kind,state,publication_bytes "
        "FROM mission_publications WHERE mission_id='mission-1' LIMIT 1"
    ),
    "publication-missing-row": (
        "DELETE FROM mission_publications WHERE mission_id='mission-1'"
    ),
    "gate-resolution": (
        "UPDATE mission_gates SET resolution=NULL WHERE mission_id='mission-1'"
    ),
    "gate-bytes": (
        "UPDATE mission_gates SET gate_bytes=gate_bytes||X'20' "
        "WHERE mission_id='mission-1'"
    ),
    "gate-missing-row": "DELETE FROM mission_gates WHERE mission_id='mission-1'",
    "gate-extra-row": (
        "INSERT INTO mission_gates SELECT 'gate-forged',mission_id,task_id,resolution,"
        "gate_bytes FROM mission_gates WHERE mission_id='mission-1' LIMIT 1"
    ),
    "head-update": (
        "UPDATE mission_heads SET seq=seq+1,event_count=event_count+1 "
        "WHERE mission_id='mission-1'"
    ),
    "command-extra-row": (
        "INSERT INTO mission_commands VALUES('mission-1','command-forged-extra',"
        f"'{('f' * 64)}',X'7b7d')"
    ),
    "state-record-extra-row": (
        "INSERT INTO mission_state_records SELECT mission_id,command_count+100,"
        "'command-forged-state',head_seq,head_event_sha256,state_root_sha256,"
        f"'{('f' * 64)}' FROM mission_state_records WHERE mission_id='mission-1' "
        "ORDER BY command_count DESC LIMIT 1"
    ),
}

MUTATIONS = tuple(
    pytest.param(_sql(statement), id=name) for name, statement in SQL_MUTATIONS.items()
) + (
    pytest.param(
        _json_value(
            table="mission_attempts",
            column="attempt_bytes",
            selector="mission_id='mission-1'",
            key="worker_id",
            value="worker-forged",
        ),
        id="attempt-owner",
    ),
    pytest.param(
        _json_value(
            table="mission_attempts",
            column="attempt_bytes",
            selector="mission_id='mission-1'",
            key="result_code",
            value="forged",
        ),
        id="attempt-result",
    ),
    pytest.param(_attempt_evidence_link, id="attempt-evidence-link"),
    pytest.param(_publication_digest, id="publication-bytes-digest"),
    pytest.param(
        _json_value(
            table="mission_publications",
            column="publication_bytes",
            selector="mission_id='mission-1'",
            key="consumers",
            value=["verify"],
        ),
        id="publication-consumers",
    ),
    pytest.param(
        _json_value(
            table="mission_publications",
            column="publication_bytes",
            selector="mission_id='mission-1'",
            key="paths",
            value=["app/forged.py"],
        ),
        id="publication-paths",
    ),
    pytest.param(
        _json_value(
            table="mission_gates",
            column="gate_bytes",
            selector="mission_id='mission-1'",
            key="operator_label",
            value="forged-operator",
        ),
        id="gate-actor",
    ),
    pytest.param(
        _json_value(
            table="mission_gates",
            column="gate_bytes",
            selector="mission_id='mission-1'",
            key="truth_kind",
            value="simulated_fixture",
        ),
        id="gate-truth-kind",
    ),
    pytest.param(_artifact_reference, id="attempt-artifact-reference"),
)


def _populated_store(tmp_path) -> SQLiteMissionStore:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.register_worker(
        MISSION_ID,
        "worker-a",
        "runtime-a",
        (TaskKind.WORK,),
        _command("v2-register-worker"),
        recorded_at=NOW,
    )
    store.refresh_ready(MISSION_ID, _command("v2-ready"), recorded_at=NOW)
    task = next(
        item for item in store.ready_tasks(MISSION_ID) if item.task_id == "work-a"
    )
    dispatch = store.claim_task(
        MISSION_ID,
        task.task_id,
        "worker-a",
        _command("v2-claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    store.complete_attempt(
        MISSION_ID,
        dispatch.attempt_id,
        dispatch.worker_id,
        dispatch.lease_id,
        dispatch.fencing_token,
        _success(dispatch, task, _artifacts(store)),
        _command("v2-complete"),
        recorded_at=NOW + timedelta(seconds=1),
        retry_backoff_seconds=0,
    )
    store.request_gate(
        Gate(
            gate_id="gate-v2",
            mission_id=MISSION_ID,
            task_id="work-b",
            reason="Exercise the bound gate projection.",
            allowed_decisions=(
                GateDecision(value="continue", consequence="Resume bounded work."),
            ),
            truth_kind=TruthKind.SERVER_DERIVED,
        ),
        _command("v2-gate"),
        recorded_at=NOW + timedelta(seconds=2),
    )
    store.decide_gate(
        MISSION_ID,
        "gate-v2",
        "continue",
        _command("v2-gate-decision"),
        expected_head=store.head(MISSION_ID),
        operator_label="api-operator",
        rationale="Supply a complete attributed gate projection.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=3),
    )
    assert store.verify(MISSION_ID) == store.head(MISSION_ID)
    return store


@pytest.mark.parametrize("mutate", MUTATIONS)
def test_v2_state_record_rejects_every_materialized_mutation_before_read_or_dispatch(
    tmp_path, mutate: Mutation
) -> None:
    store = _populated_store(tmp_path)
    with sqlite3.connect(store.path) as connection:
        mutate(connection)

    operations = (
        lambda: store.snapshot(MISSION_ID),
        lambda: store.verify(MISSION_ID),
        lambda: store.refresh_ready(
            MISSION_ID,
            _command("after-tamper"),
            recorded_at=NOW + timedelta(seconds=4),
        ),
    )
    for operation in operations:
        with pytest.raises(MissionStoreError):
            operation()


@pytest.mark.parametrize(
    ("table", "statement"),
    (
        (
            "mission_commands",
            "UPDATE mission_commands SET request_sha256 = 'forged'",
        ),
        ("mission_commands", "DELETE FROM mission_commands"),
        (
            "mission_state_records",
            "UPDATE mission_state_records SET state_root_sha256 = 'forged'",
        ),
        ("mission_state_records", "DELETE FROM mission_state_records"),
    ),
)
def test_v2_command_and_state_record_ledgers_are_append_only(
    tmp_path, table: str, statement: str
) -> None:
    store = _populated_store(tmp_path)
    with sqlite3.connect(store.path) as connection:
        before = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(statement)
        after = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert after == before


def test_v2_schema_version_and_migration_ledger_are_explicit(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT version, length(schema_sha256), applied_label "
            "FROM schema_migrations"
        ).fetchall() == [(2, 64, "fresh-v2")]


def test_legacy_user_version_zero_mission_database_is_explicitly_refused(
    tmp_path,
) -> None:
    database = tmp_path / "legacy.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE missions (mission_id TEXT PRIMARY KEY)")
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0

    with pytest.raises(MissionStoreError, match="legacy mission schema is read-only"):
        SQLiteMissionStore(database)


def test_recovery_returns_only_dispatches_owned_by_requested_worker(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.register_worker(
        MISSION_ID,
        "worker-a",
        "runtime-a",
        (TaskKind.WORK,),
        _command("owner-register-worker"),
        recorded_at=NOW,
    )
    store.register_worker(
        MISSION_ID,
        "worker-b",
        "runtime-b",
        (TaskKind.WORK,),
        _command("owner-register-other-worker"),
        recorded_at=NOW,
    )
    store.refresh_ready(MISSION_ID, _command("owner-ready"), recorded_at=NOW)
    task = next(
        item for item in store.ready_tasks(MISSION_ID) if item.task_id == "work-a"
    )
    dispatch = store.claim_task(
        MISSION_ID,
        task.task_id,
        "worker-a",
        _command("owner-claim"),
        recorded_at=NOW,
        ttl_seconds=30,
    )

    assert store.recover_dispatches(MISSION_ID, ("worker-b",), recorded_at=NOW) == ()
    assert store.recover_dispatches(MISSION_ID, ("worker-a",), recorded_at=NOW) == (
        dispatch,
    )
