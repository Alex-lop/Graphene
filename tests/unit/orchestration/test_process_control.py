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


def _wait_for_owned_process(registry: OwnedProcessRegistry) -> None:
    deadline = time.monotonic() + 2
    while not any(path.suffix == ".json" for path in registry.directory.iterdir()):
        if time.monotonic() >= deadline:
            pytest.fail("owned process record did not appear within two seconds")
        time.sleep(0.01)


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
    _wait_for_owned_process(registry)
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
    _wait_for_owned_process(registry)
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


def test_record_binds_live_popen_to_observed_exec_identity(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    pid = 424_242
    observed_executable = "Python-3.13-hosted-launcher-target"
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda observed_pid: (
            observed_pid,
            "Tue Aug 19 00:00:00 2026",
            "S",
            observed_executable,
        ),
    )

    class Spawned:
        pid = 424_242
        args = (sys.executable, "-c", "pass")

        @staticmethod
        def poll():
            return None

    registry.record(
        dispatch,
        Spawned(),  # type: ignore[arg-type]
        sys.executable,
    )
    record = json.loads(next(registry.directory.iterdir()).read_text(encoding="utf-8"))
    assert record["pid"] == pid
    assert record["executable"] == observed_executable


def test_record_refuses_child_that_exits_during_identity_capture(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda observed_pid: (
            observed_pid,
            "Tue Aug 19 00:00:00 2026",
            "S",
            "Python-3.13-hosted-launcher-target",
        ),
    )

    class Exited:
        pid = 424_243
        args = (sys.executable, "-c", "pass")

        def __init__(self) -> None:
            self.polls = iter((None, 0))

        def poll(self):
            return next(self.polls)

    with pytest.raises(ProcessControlError, match="no longer running"):
        registry.record(
            dispatch,
            Exited(),  # type: ignore[arg-type]
            sys.executable,
        )
    assert not tuple(registry.directory.iterdir())


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


SANDBOX_EXEC = "/usr/bin/sandbox-exec"


@pytest.mark.skipif(
    sys.platform != "darwin" or not Path(SANDBOX_EXEC).is_file(),
    reason="exec-in-place wrapper identity requires macOS /usr/bin/sandbox-exec",
)
def test_exec_in_place_wrapper_keeps_identity_and_signals(tmp_path: Path) -> None:
    """sandbox-exec replaces its own image; the registry must still own the group.

    Identity is pid, process group, and start time. The executable may change
    only for a child recorded under the documented exec-in-place wrapper.
    """

    from graphene.orchestration import process_control

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(
        (SANDBOX_EXEC, "-p", "(version 1)(allow default)", "/bin/sleep", "30"),
        start_new_session=True,
    )
    try:
        registry.record(dispatch, process, SANDBOX_EXEC)
        owned = registry.records_for_mission(dispatch.mission_id)[0]
        assert owned.pid == owned.pgid == process.pid
        assert owned.executable in {SANDBOX_EXEC, "/bin/sleep"}
        deadline = time.monotonic() + 5
        observed = owned.executable
        while time.monotonic() < deadline:
            _, _, _, observed = process_control._process_identity(process.pid)
            if observed != SANDBOX_EXEC:
                break
            time.sleep(0.02)
        assert observed != SANDBOX_EXEC, "sandbox-exec did not exec in place"
        # The exec'd image is re-identified, not refused.
        assert registry.records_for_mission(dispatch.mission_id) == (owned,)
        assert registry.validate(dispatch) == owned
        assert registry.has_record(dispatch.attempt_id)
        registry.signal(dispatch, 15)
        assert process.wait(timeout=2) == -15
        registry.remove(dispatch)
        assert not registry.has_record(dispatch.attempt_id)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=2)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_executable_change_without_wrapper_still_refuses_to_signal(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record(dispatch, process, "/bin/sleep")
    path = next(registry.directory.iterdir())
    record = json.loads(path.read_text(encoding="utf-8"))
    record["executable"] = "/bin/other"
    path.write_text(json.dumps(record), encoding="utf-8")
    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        os, "killpg", lambda pid, requested: signalled.append((pid, requested))
    )

    try:
        with pytest.raises(ProcessControlError, match="identity changed"):
            registry.signal(dispatch, 15)
        with pytest.raises(ProcessControlError, match="identity changed"):
            registry.records_for_mission(dispatch.mission_id)
        assert signalled == []
    finally:
        process.kill()
        process.wait(timeout=2)
