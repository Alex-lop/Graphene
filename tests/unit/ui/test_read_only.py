"""The viewer's store handle cannot write: proven by SQLite refusing, and by bytes."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene.orchestration.mission_projection import MissionProjection
from graphene.orchestration.scripted import load_scenario, propose_scripted_mission
from graphene.orchestration.sqlite_mission_store import MissionStoreError, SQLiteMissionStore
from graphene.ui.read_only_store import ReadOnlyMissionStore


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    for suffix in ("", "-wal"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            digest.update(candidate.read_bytes())
    return digest.hexdigest()


@pytest.fixture(scope="module")
def proposed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    state = tmp_path_factory.mktemp("ro") / "state"
    state.mkdir(mode=0o700)
    store = SQLiteMissionStore(state / "missions.sqlite3")
    runtime = state / "runtime"
    propose_scripted_mission(
        scenario=load_scenario(), store=store, runtime=runtime, mission_id="mission-ro-001"
    )
    return state / "missions.sqlite3", "mission-ro-001"


def test_read_only_store_serves_the_projection_without_changing_a_byte(
    proposed: tuple[Path, str],
) -> None:
    path, mission_id = proposed
    before = _digest(path)
    viewer = ReadOnlyMissionStore(path)
    snapshot = MissionProjection(viewer).snapshot(mission_id)
    assert snapshot.mission.mission_id == mission_id
    assert len(snapshot.tasks) == 6
    assert viewer.head(mission_id).seq >= 1
    assert viewer.tail(mission_id, 0, 8)
    assert viewer.integrity_marker(mission_id)
    assert viewer.mission_ids() == (mission_id,)
    assert viewer.most_recent_active_mission() == mission_id
    assert _digest(path) == before


def test_every_write_through_the_viewer_handle_is_refused_by_sqlite(
    proposed: tuple[Path, str],
) -> None:
    path, mission_id = proposed
    viewer = ReadOnlyMissionStore(path)
    with pytest.raises(sqlite3.OperationalError):
        with viewer._connect() as connection:
            connection.execute("DELETE FROM mission_events WHERE mission_id = ?", (mission_id,))
    with pytest.raises(sqlite3.OperationalError):
        with viewer._connect() as connection:
            connection.execute("CREATE TABLE viewer_scribble (x)")
    # And the store's own mutation path fails the same way, not silently.
    with pytest.raises((sqlite3.OperationalError, MissionStoreError)):
        viewer.refresh_ready(mission_id, "command_viewer_write_probe_0001", recorded_at=datetime.now(UTC))


def test_viewer_refuses_a_missing_store_instead_of_creating_one(tmp_path: Path) -> None:
    missing = tmp_path / "missions.sqlite3"
    with pytest.raises(MissionStoreError, match="no mission store"):
        ReadOnlyMissionStore(missing)
    assert not missing.exists()
