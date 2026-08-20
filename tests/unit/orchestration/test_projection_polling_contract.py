import sqlite3

import pytest
from fastapi.testclient import TestClient

from graphene.orchestration.mission_control import create_mission_control_app
from graphene.orchestration.projection import MissionProjection, MissionProjectionError
from graphene.orchestration.store import SQLiteMissionStore

from .test_store import _create


def test_cached_snapshot_poll_revalidates_canonical_state_root(
    tmp_path, monkeypatch
) -> None:
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    projection = MissionProjection(store)
    state_root = store._state_root
    calls = 0

    def counted_state_root(connection, mission_id):
        nonlocal calls
        calls += 1
        return state_root(connection, mission_id)

    monkeypatch.setattr(store, "_state_root", counted_state_root)
    app = create_mission_control_app(
        projection, "mission-1", "poll-regression-token", "TEST LIVE"
    )
    path = "/api/mission-control/missions/mission-1/snapshot"
    headers = {"Authorization": "Bearer poll-regression-token"}
    with TestClient(app) as client:
        first = client.get(path, headers=headers)
        cold_calls = calls
        second = client.get(path, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert cold_calls > 0
    assert calls == cold_calls


def test_cached_snapshot_revalidates_after_direct_database_write(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    projection = MissionProjection(store)
    projection.snapshot("mission-1")

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE missions SET status = 'failed' WHERE mission_id = 'mission-1'"
        )

    with pytest.raises(MissionProjectionError, match="failed store validation"):
        projection.snapshot("mission-1")


def test_detected_tamper_stays_quarantined_after_bytes_are_restored(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    projection = MissionProjection(store)
    projection.snapshot("mission-1")

    with sqlite3.connect(store.path) as connection:
        original = connection.execute(
            "SELECT status FROM missions WHERE mission_id = 'mission-1'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE missions SET status = 'failed' WHERE mission_id = 'mission-1'"
        )
    with pytest.raises(MissionProjectionError, match="failed store validation"):
        projection.snapshot("mission-1")

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE missions SET status = ? WHERE mission_id = 'mission-1'",
            (original,),
        )
    with pytest.raises(MissionProjectionError, match="quarantined"):
        projection.snapshot("mission-1")
