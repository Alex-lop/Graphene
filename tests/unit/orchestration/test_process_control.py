from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from graphene.orchestration.models import MissionStatus
from graphene.orchestration.process_control import (
    ControlledProcessRunner,
    OwnedProcessRegistry,
    ProcessControlError,
)
from graphene.orchestration.scheduler import MissionScheduler
from graphene.orchestration.store import SQLiteMissionStore

from .test_scheduler import FakeClock
from .test_store import NOW, _create


def _dispatch(tmp_path: Path):
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    dispatch = MissionScheduler(store, clock=FakeClock(NOW)).tick(
        "mission-1", ("worker-a",)
    )[0]
    return store, dispatch


def _invoke(runner: ControlledProcessRunner, seconds: float = 0.2):
    return runner(
        ("/bin/sleep", str(seconds)),
        cwd=Path("/"),
        env={"PATH": os.defpath},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=1,
        check=False,
    )


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_pause_excludes_stopped_time_and_resume_completes(tmp_path: Path) -> None:
    _, dispatch = _dispatch(tmp_path)
    state = [MissionStatus.RUNNING]
    heartbeats: list[float] = []
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    runner = ControlledProcessRunner(
        registry,
        dispatch,
        lambda: state[0],
        heartbeat=lambda: heartbeats.append(time.monotonic()),
        heartbeat_seconds=0.05,
    )
    result: list[subprocess.CompletedProcess[str]] = []
    thread = threading.Thread(target=lambda: result.append(_invoke(runner)))

    thread.start()
    while not tuple(registry.directory.iterdir()):
        time.sleep(0.01)
    state[0] = MissionStatus.PAUSED
    time.sleep(0.3)
    assert thread.is_alive()
    state[0] = MissionStatus.RUNNING
    thread.join(timeout=2)

    assert result[0].returncode == 0
    assert len(heartbeats) >= 3
    assert not tuple(registry.directory.iterdir())


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_cancel_terminates_only_registered_group_and_cleans_record(
    tmp_path: Path,
) -> None:
    _, dispatch = _dispatch(tmp_path)
    state = [MissionStatus.RUNNING]
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    runner = ControlledProcessRunner(registry, dispatch, lambda: state[0])
    errors: list[Exception] = []

    def execute() -> None:
        try:
            _invoke(runner, 10)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=execute)
    thread.start()
    while not tuple(registry.directory.iterdir()):
        time.sleep(0.01)
    prepared = registry.records_for_mission(dispatch.mission_id)
    assert len(prepared) == 1
    registry.terminate_owned(prepared[0], timeout=1)
    thread.join(timeout=3)

    assert errors == [] and not thread.is_alive()
    assert not tuple(registry.directory.iterdir())


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_identity_mismatch_refuses_to_signal(tmp_path: Path, monkeypatch) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record(dispatch, process, "/bin/sleep")
    path = next(registry.directory.iterdir())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["started_at"] = "Mon Jan 1 00:00:00 1900"
    path.write_text(json.dumps(record), encoding="utf-8")
    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        os, "killpg", lambda pid, requested: signalled.append((pid, requested))
    )

    try:
        with pytest.raises(ProcessControlError, match="identity changed"):
            registry.signal(dispatch, 15)
        assert signalled == []
    finally:
        process.kill()
        process.wait(timeout=2)


@pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").is_file(),
    reason="sandbox-exec identity replacement is macOS-specific",
)
def test_record_accepts_only_frozen_sandbox_exec_target(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    pid = 424_242
    replacement = str(Path(sys.executable).resolve(strict=True))
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda observed_pid: (
            observed_pid,
            "Tue Aug 19 00:00:00 2026",
            "S",
            replacement,
        ),
    )

    class Spawned:
        pass

    process = Spawned()
    process.pid = pid
    registry.record(
        dispatch,
        process,  # type: ignore[arg-type]
        "/usr/bin/sandbox-exec",
        (sys.executable,),
    )
    record = json.loads(next(registry.directory.iterdir()).read_text(encoding="utf-8"))
    assert record["executable"] == replacement

    other_dispatch = dispatch.model_copy(update={"attempt_id": "attempt-unlisted-exec"})
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda observed_pid: (
            observed_pid,
            "Tue Aug 19 00:00:00 2026",
            "S",
            "/bin/sleep",
        ),
    )
    with pytest.raises(ProcessControlError, match="owned process group"):
        registry.record(
            other_dispatch,
            process,  # type: ignore[arg-type]
            "/usr/bin/sandbox-exec",
            (sys.executable,),
        )


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_identity_bound_signal_treats_esrch_as_confirmed_exit(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record(dispatch, process, "/bin/sleep")
    owned = registry.validate(dispatch)
    monkeypatch.setattr(
        os,
        "killpg",
        lambda _pgid, _requested: (_ for _ in ()).throw(ProcessLookupError()),
    )

    try:
        registry.signal_prepared(owned, 15)
    finally:
        process.kill()
        process.wait(timeout=2)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_zombie_state_is_confirmed_not_live_without_signalling(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record(dispatch, process, "/bin/sleep")
    owned = registry.validate(dispatch)
    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda _pid: (owned.pgid, owned.started_at, "Z", "<defunct>"),
    )
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pgid, requested: signalled.append((pgid, requested)),
    )

    try:
        registry.signal_prepared(owned, 15)
        assert signalled == []
    finally:
        process.kill()
        process.wait(timeout=2)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_registry_retry_confirms_gone_and_rejects_public_records(
    tmp_path: Path,
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record(dispatch, process, "/bin/sleep")
    record = next(registry.directory.iterdir())
    record.chmod(0o644)
    with pytest.raises(ProcessControlError, match="unsafe"):
        registry.records_for_mission(dispatch.mission_id)

    record.chmod(0o600)
    process.kill()
    process.wait(timeout=2)
    owned = registry.records_for_mission(dispatch.mission_id)[0]
    registry.terminate_owned(owned)
    assert not tuple(registry.directory.iterdir())


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_status_failure_terminates_reaps_and_removes_owned_process(
    tmp_path: Path,
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    observed_pid: list[int] = []

    def failed_status() -> MissionStatus:
        record = json.loads(
            next(registry.directory.iterdir()).read_text(encoding="utf-8")
        )
        observed_pid.append(record["pid"])
        raise RuntimeError("status unavailable")

    runner = ControlledProcessRunner(registry, dispatch, failed_status)
    with pytest.raises(RuntimeError, match="status unavailable"):
        _invoke(runner, 10)

    assert observed_pid
    with pytest.raises(ProcessLookupError):
        os.kill(observed_pid[0], 0)
    assert not tuple(registry.directory.iterdir())
