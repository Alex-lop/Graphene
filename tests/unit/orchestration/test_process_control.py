from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from graphene.orchestration.mission_models import MissionStatus
from graphene.orchestration.process_control import (
    ControlledProcessRunner,
    OwnedProcessRegistry,
    ProcessControlError,
)
from graphene.orchestration.scheduler import MissionScheduler
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore

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


@pytest.mark.skipif(sys.platform != "darwin", reason="BSD ps semantics required")
def test_framework_python_launcher_is_reidentified_under_its_app_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """python.org's framework ``bin/python3.x`` execs Python.app in place.

    A child started through that interpreter (or a venv symlink to it) is
    recorded under the path it was launched as and reported under
    ``Resources/Python.app/Contents/MacOS/Python`` a few milliseconds later.
    The registry refused every later validate/signal for such a child, so the
    scripted worker could not reconcile an interrupted attempt on the GitHub
    macOS runner -- the one place the framework build is the interpreter.
    The layout is faked so this is red at baseline on every macOS host, not
    only on one that has python.org's build installed.
    """

    from graphene.orchestration import process_control

    # The launcher is a real file, as the Mach-O one is: realpath of the venv
    # symlink must stop inside the framework, not skip through to /bin/sleep.
    framework = Path(os.path.realpath(tmp_path)) / "Python.framework/Versions/3.13"
    launcher = framework / "bin" / "python3.13"
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec /bin/sleep "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(launcher)
    app_binary = str(framework / "Resources/Python.app/Contents/MacOS/Python")

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen((str(venv_python), "30"), start_new_session=True)
    try:
        real_identity = process_control._process_identity

        # What the runner's ps reported at record time: the launched path.
        def before_exec(pid: int):
            pgid, started_at, state, _ = real_identity(pid)
            return pgid, started_at, state, str(venv_python)

        monkeypatch.setattr(process_control, "_process_identity", before_exec)
        registry.record(dispatch, process, str(venv_python))
        owned = registry.records_for_mission(dispatch.mission_id)[0]
        assert owned.executable == str(venv_python)

        def after_exec(pid: int):
            pgid, started_at, state, _ = real_identity(pid)
            return pgid, started_at, state, app_binary

        monkeypatch.setattr(process_control, "_process_identity", after_exec)
        assert registry.records_for_mission(dispatch.mission_id) == (owned,)
        assert registry.validate(dispatch) == owned
        registry.signal(dispatch, 15)
        assert process.wait(timeout=5) == -15
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=5)


_FRAMEWORK_LAUNCHERS = sorted(
    Path("/Library/Frameworks/Python.framework/Versions").glob("3.*/bin/python3.*[0-9]")
)


@pytest.mark.skipif(
    sys.platform != "darwin" or not _FRAMEWORK_LAUNCHERS,
    reason="a python.org framework interpreter is required",
)
def test_real_framework_launcher_child_stays_owned_after_it_execs(
    tmp_path: Path,
) -> None:
    """The un-faked version: the host's own python.org launcher, no monkeypatch."""

    from graphene.orchestration import process_control

    launcher = str(_FRAMEWORK_LAUNCHERS[-1])
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(
        (launcher, "-c", "import time; time.sleep(30)"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        registry.record(dispatch, process, launcher)
        owned = registry.records_for_mission(dispatch.mission_id)[0]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, _, _, observed = process_control._process_identity(process.pid)
            if observed.endswith("/Python.app/Contents/MacOS/Python"):
                break
            time.sleep(0.02)
        assert observed.endswith("/Python.app/Contents/MacOS/Python"), observed
        assert registry.validate(dispatch) == owned
        registry.signal(dispatch, 15)
        assert process.wait(timeout=5) == -15
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=5)


@pytest.mark.skipif(sys.platform != "darwin", reason="BSD ps semantics required")
def test_a_parenthesised_ps_read_records_the_launched_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BSD ps parenthesises comm while a process is replacing its image.

    Persisting that string as the identity made every later live check
    compare a real path against ``(name)`` and refuse. We launched the child
    ourselves, so the launched path is the identity; forced here rather than
    raced for. (First seen by the reliability lane as ``(sandbox-exec)``.)
    """

    from graphene.orchestration import process_control

    launched = tmp_path / "bin" / "py"
    launched.parent.mkdir()
    launched.symlink_to("/bin/sleep")
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen((str(launched), "30"), start_new_session=True)
    try:
        real_identity = process_control._process_identity
        monkeypatch.setattr(
            process_control,
            "_process_identity",
            lambda pid: (*real_identity(pid)[:3], "(sleep)"),
        )
        registry.record(dispatch, process, str(launched))
        monkeypatch.undo()
        owned = registry.records_for_mission(dispatch.mission_id)[0]
        assert owned.executable == str(launched)
        assert registry.validate(dispatch) == owned
        registry.signal(dispatch, 15)
        assert process.wait(timeout=5) == -15
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=5)


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
