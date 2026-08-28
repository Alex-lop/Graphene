from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene.hashing import canonical_json_bytes
from graphene.orchestration.mission_models import MissionStatus
from graphene.orchestration.process_control import (
    ControlledProcessRunner,
    OwnedProcessRegistry,
    ProcessCancelled,
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
def test_model_dispatch_barrier_is_bound_to_exact_process_and_fence(
    tmp_path: Path,
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    try:
        owned = registry.record_pid(
            dispatch,
            process.pid,
            "/bin/sleep",
            model_request_sha256="a" * 64,
            model_input_bytes=1,
        )
        barrier = registry.acknowledge_model_dispatch(
            dispatch,
            owned,
            request_sha256="a" * 64,
            sdk_invocation_id="invocation-1",
            dispatched_at="2026-08-27T12:00:00.000Z",
        )

        assert registry.model_dispatch_barrier(dispatch) == barrier
        changed = dispatch.model_copy(
            update={"fencing_token": dispatch.fencing_token + 1}
        )
        with pytest.raises(ProcessControlError, match="barrier identity changed"):
            registry.model_dispatch_barrier(changed)
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=2)
        registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_fast_model_child_can_be_acknowledged_after_exact_exit(tmp_path: Path) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(
        dispatch,
        process.pid,
        "/bin/sleep",
        model_request_sha256="c" * 64,
        model_input_bytes=1,
    )
    process.kill()
    process.wait(timeout=2)

    barrier = registry.acknowledge_model_dispatch(
        dispatch,
        owned,
        request_sha256="c" * 64,
        sdk_invocation_id="invocation-fast-child",
        dispatched_at="2026-08-27T12:00:00.000Z",
    )

    assert registry.model_dispatch_barrier(dispatch, require_live=False) == barrier
    registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_linked_barrier_is_refsynced_after_initial_directory_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(
        dispatch,
        process.pid,
        "/bin/sleep",
        model_request_sha256="d" * 64,
        model_input_bytes=1,
    )

    def link_then_raise(_directory: Path, target: Path, value: object) -> None:
        target.write_bytes(canonical_json_bytes(value))
        target.chmod(0o600)
        raise OSError("first directory fsync failed")

    monkeypatch.setattr(registry, "_atomic_create", link_then_raise)
    with pytest.raises(OSError, match="first directory fsync failed"):
        registry.acknowledge_model_dispatch(
            dispatch,
            owned,
            request_sha256="d" * 64,
            sdk_invocation_id="invocation-refsync",
            dispatched_at="2026-08-27T12:00:00.000Z",
        )

    barrier = registry.confirm_model_dispatch_barrier(dispatch)
    assert barrier is not None
    assert barrier.sdk_invocation_id == "invocation-refsync"
    process.kill()
    process.wait(timeout=2)
    registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_model_and_check_records_coexist_and_model_signal_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    model = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    check = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    try:
        model_owned = registry.record_pid(
            dispatch,
            model.pid,
            "/bin/sleep",
            model_request_sha256="b" * 64,
            model_input_bytes=1,
        )
        registry.acknowledge_model_dispatch(
            dispatch,
            model_owned,
            request_sha256="b" * 64,
            sdk_invocation_id="invocation-model",
            dispatched_at="2026-08-27T12:00:00.000Z",
        )
        registry.record(dispatch, check, "/bin/sleep")
        signalled: list[tuple[int, int]] = []
        monkeypatch.setattr(
            os,
            "killpg",
            lambda pgid, requested: signalled.append((pgid, requested)),
        )

        registry.signal(dispatch, 9, model=True)

        assert signalled == [(model.pid, 9)]
        assert registry.validate(dispatch).pid == check.pid
        assert registry.owned_process(dispatch, model=True) == model_owned
        monkeypatch.undo()
        with pytest.raises(ProcessControlError, match="still running"):
            registry.remove(dispatch)
        check.kill()
        check.wait(timeout=2)
        registry.remove(dispatch)
        assert not registry.has_record(dispatch.attempt_id, model=False)
        assert registry.has_record(dispatch.attempt_id, model=True)
    finally:
        monkeypatch.undo()
        for process in (model, check):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
        registry.remove(dispatch)
        registry.remove_exact(model_owned)


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
    results: list[subprocess.CompletedProcess[str]] = []

    def execute() -> None:
        try:
            results.append(_invoke(runner, 10))
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=execute)
    thread.start()
    _wait_for_owned_process(registry)
    prepared = registry.records_for_mission(dispatch.mission_id)
    assert len(prepared) == 1
    registry.terminate_owned(prepared[0], timeout=1, retain_record=True)
    thread.join(timeout=3)
    registry.remove_exact(prepared[0])

    assert errors == [] and not thread.is_alive()
    assert len(results) == 1 and results[0].returncode < 0
    assert not tuple(registry.directory.iterdir())


@pytest.mark.skipif(
    sys.platform != "darwin", reason="macOS zombies temporarily lose libproc identity"
)
def test_default_termination_window_allows_delayed_owner_reap(tmp_path: Path) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "30"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")

    def delayed_reap() -> None:
        time.sleep(2.25)
        process.wait(timeout=2)

    reaper = threading.Thread(target=delayed_reap)
    reaper.start()
    try:
        assert registry.terminate_owned(owned, retain_record=True) == signal.SIGTERM
        reaper.join(timeout=3)
        assert not reaper.is_alive()
        registry.remove_exact(owned)
    finally:
        reaper.join(timeout=3)
        if reaper.is_alive():
            process.kill()
            reaper.join(timeout=5)
        if process.returncode is None:
            process.kill()
            process.wait(timeout=5)
        assert not reaper.is_alive()
        if registry.has_record(dispatch.attempt_id):
            registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_post_signal_wait_requires_exact_zombie_to_be_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from graphene.orchestration import process_control

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")
    identities = iter(
        (
            (
                owned.pgid,
                owned.started_at,
                "Z",
                owned.executable,
                owned.birth_token,
            ),
            (
                owned.pgid,
                owned.started_at,
                "S",
                owned.executable,
                "reused-birth-token",
            ),
        )
    )
    observations: list[int] = []

    def identity(pid: int):
        observations.append(pid)
        return next(identities)

    monkeypatch.setattr(process_control, "_owned_process_identity", identity)
    monkeypatch.setattr(
        os,
        "waitpid",
        lambda *_args: pytest.fail("post-signal observation must not reap"),
    )
    try:
        assert registry._wait_for_exit_after_signal(
            owned, timeout=0.1, poll_seconds=0
        )
        assert observations == [owned.pid, owned.pid]
    finally:
        monkeypatch.undo()
        process.kill()
        process.wait(timeout=2)
        registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_termination_waits_when_leader_is_already_a_zombie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")
    waited: list[object] = []
    monkeypatch.setattr(registry, "signal_prepared", lambda *_args: False)
    monkeypatch.setattr(
        registry,
        "_wait_for_exit_after_signal",
        lambda current, **_kwargs: waited.append(current) or True,
    )
    monkeypatch.setattr(registry, "terminate_descendants", lambda *_a, **_k: None)
    try:
        assert registry.terminate_owned(owned, retain_record=True) is None
        assert waited == [owned]
    finally:
        monkeypatch.undo()
        process.kill()
        process.wait(timeout=2)
        registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_conflicted_cancellation_removes_dead_process_records(tmp_path: Path) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record_pid(dispatch, process.pid, "/bin/sleep")
    process.kill()
    process.wait(timeout=2)

    registry.remove_dead_records_for_mission(dispatch.mission_id)

    assert not registry.has_record(dispatch.attempt_id)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
@pytest.mark.parametrize(
    "marker", ("cancellation-request.json", "cancellation-complete.json")
)
def test_cancellation_marker_refuses_worker_registration(
    tmp_path: Path, marker: str
) -> None:
    _, dispatch = _dispatch(tmp_path)
    runtime = tmp_path / "runtime"
    registry = OwnedProcessRegistry(runtime)
    cancellation = runtime / marker
    cancellation.write_text("{}", encoding="utf-8")
    runner = ControlledProcessRunner(
        registry,
        dispatch,
        lambda: MissionStatus.RUNNING,
        heartbeat=lambda: pytest.fail("cancelling worker must not heartbeat"),
        heartbeat_seconds=-1,
    )

    try:
        with pytest.raises(ProcessCancelled, match="prevents process registration"):
            _invoke(runner, 0.05)
        assert not registry.has_record(dispatch.attempt_id)
    finally:
        cancellation.unlink(missing_ok=True)
        owned = registry.owned_process(dispatch, require_live=False)
        if owned is not None:
            registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_cancellation_journal_waits_for_inflight_process_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from graphene.cli import mission as mission_cli

    store, dispatch = _dispatch(tmp_path)
    runtime = tmp_path / "runtime"
    registry = OwnedProcessRegistry(runtime)
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    published = threading.Event()
    release = threading.Event()
    original_create = registry._atomic_create

    def pause_after_publish(directory, target, value) -> None:
        original_create(directory, target, value)
        published.set()
        assert release.wait(timeout=2)

    monkeypatch.setattr(registry, "_atomic_create", pause_after_publish)
    registered: list[object] = []
    registration = threading.Thread(
        target=lambda: registered.append(
            registry.record_pid(dispatch, process.pid, "/bin/sleep")
        )
    )
    journaled: list[object] = []
    journal = threading.Thread(
        target=lambda: journaled.append(
            mission_cli._ensure_cancellation_request(
                runtime,
                mission_id=dispatch.mission_id,
                command_id="command-cancel-registration-race",
                expected_head=store.head(dispatch.mission_id),
                operator_label="test-operator",
                rationale=None,
                truth_kind=mission_cli.TruthKind.HUMAN_ATTESTED,
                recorded_at=datetime.now(UTC),
            )
        )
    )
    try:
        registration.start()
        assert published.wait(timeout=2)
        journal.start()
        journal.join(timeout=0.1)
        assert journal.is_alive()
        assert not (runtime / "cancellation-request.json").exists()
        release.set()
        registration.join(timeout=2)
        journal.join(timeout=2)
        assert len(registered) == len(journaled) == 1
        assert registry.has_record(dispatch.attempt_id)
        assert (runtime / "cancellation-request.json").is_file()
    finally:
        release.set()
        registration.join(timeout=2)
        if journal.ident is not None:
            journal.join(timeout=2)
        monkeypatch.undo()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        owned = registry.owned_process(dispatch, require_live=False)
        if owned is not None:
            registry.remove_exact(owned)
        (runtime / "cancellation-request.json").unlink(missing_ok=True)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_durable_cancel_retains_runner_record_until_exact_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    state = [MissionStatus.RUNNING]
    runtime = tmp_path / "runtime"
    registry = OwnedProcessRegistry(runtime)
    runner = ControlledProcessRunner(registry, dispatch, lambda: state[0])
    results: list[subprocess.CompletedProcess[str]] = []
    errors: list[Exception] = []

    def execute() -> None:
        try:
            results.append(_invoke(runner, 10))
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=execute)
    thread.start()
    _wait_for_owned_process(registry)
    owned = registry.records_for_mission(dispatch.mission_id)[0]
    cancellation = runtime / "cancellation-request.json"
    cancellation.write_text("{}", encoding="utf-8")
    runner_cleanup_attempted = threading.Event()
    original_remove = registry.remove

    def observe_runner_remove(current_dispatch) -> None:
        original_remove(current_dispatch)
        runner_cleanup_attempted.set()

    original_descendant_cleanup = registry.terminate_descendants
    cancelling_thread = threading.current_thread()

    def force_runner_cleanup_first(current, *, timeout: float = 2):
        if threading.current_thread() is cancelling_thread:
            assert runner_cleanup_attempted.wait(timeout=2)
        return original_descendant_cleanup(current, timeout=timeout)

    monkeypatch.setattr(registry, "remove", observe_runner_remove)
    monkeypatch.setattr(registry, "terminate_descendants", force_runner_cleanup_first)
    try:
        registry.terminate_owned(owned, timeout=1, retain_record=True)
        thread.join(timeout=3)

        assert runner_cleanup_attempted.is_set()
        assert registry.has_record(dispatch.attempt_id, model=False)
        registry.remove_exact(owned)
        assert not registry.has_record(dispatch.attempt_id, model=False)
        assert errors == [] and not thread.is_alive()
        assert len(results) == 1 and results[0].returncode < 0
    finally:
        monkeypatch.undo()
        state[0] = MissionStatus.CANCELLED
        thread.join(timeout=3)
        cancellation.unlink(missing_ok=True)
        remaining = registry.owned_process(dispatch, require_live=False)
        if remaining is not None:
            registry.terminate_owned(remaining)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_child_killed_after_registration_before_release_returns_signal_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    runner = ControlledProcessRunner(registry, dispatch, lambda: MissionStatus.RUNNING)
    record = registry.record

    def kill_after_record(current_dispatch, process, executable):
        record(current_dispatch, process, executable)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)

    monkeypatch.setattr(registry, "record", kill_after_record)
    result = _invoke(runner, 10)

    assert result.returncode == -signal.SIGKILL
    assert result.stdout == result.stderr == ""
    assert not registry.has_record(dispatch.attempt_id)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_controlled_process_kills_output_above_cap(tmp_path: Path) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    runner = ControlledProcessRunner(
        registry,
        dispatch,
        lambda: MissionStatus.RUNNING,
        max_output_bytes=1_024,
    )

    result = runner(
        (sys.executable, "-c", "import sys; sys.stdout.write('x' * 1000000)"),
        cwd=Path("/"),
        env={"PATH": os.defpath},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode != 0
    assert len((result.stdout + result.stderr).encode()) == 1_025
    assert not registry.has_record(dispatch.attempt_id)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_completed_leader_without_zombie_anchor_fails_closed(
    tmp_path: Path,
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    runner = ControlledProcessRunner(registry, dispatch, lambda: MissionStatus.RUNNING)
    descendant_path = tmp_path / "descendant.pid"

    with pytest.raises(ProcessControlError, match="cannot anchor descendant cleanup"):
        runner(
            (
                sys.executable,
                "-c",
                "import pathlib, subprocess; "
                "p=subprocess.Popen(['/bin/sleep','30']); "
                f"pathlib.Path({str(descendant_path)!r}).write_text(str(p.pid))",
            ),
            cwd=Path("/"),
            env={"PATH": os.defpath},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    descendant = int(descendant_path.read_text(encoding="utf-8"))
    assert registry.has_record(dispatch.attempt_id)
    os.kill(descendant, signal.SIGKILL)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(descendant, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("test-owned descendant was not reaped")
    owned = registry.owned_process(dispatch, require_live=False)
    assert owned is not None
    registry.remove_exact(owned)


@pytest.mark.parametrize("reap_leader", (False, True))
@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_recovery_refuses_descendants_after_owned_leader_exit(
    tmp_path: Path, reap_leader: bool
) -> None:
    from graphene.orchestration import process_control

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    release = tmp_path / "release-leader"
    program = (
        "import os, pathlib, subprocess, sys, time; "
        "p=subprocess.Popen(['/bin/sleep','30']); "
        "print(p.pid, flush=True); "
        f"path=pathlib.Path({str(release)!r}); "
        "\nwhile not path.exists(): time.sleep(0.01)\n"
        "os._exit(0)"
    )
    leader = subprocess.Popen(
        (sys.executable, "-c", program),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    assert leader.stdout is not None
    descendant = int(leader.stdout.readline().strip())
    owned = registry.record_pid(dispatch, leader.pid, sys.executable)
    release.touch()
    if reap_leader:
        leader.wait(timeout=2)
    else:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if process_control._process_identity(leader.pid)[2].startswith("Z"):
                break
            time.sleep(0.02)
        else:
            pytest.fail("owned group leader did not become a zombie")

    expected = (
        "birth token is unavailable"
        if sys.platform == "darwin" and not reap_leader
        else (
            "cannot anchor descendant cleanup"
            if reap_leader
            else "cannot be safely signalled after leader exit"
        )
    )
    with pytest.raises(ProcessControlError, match=expected):
        registry.terminate_owned(owned, retain_record=True)
    assert registry.has_record(dispatch.attempt_id)
    if leader.poll() is None:
        leader.wait(timeout=2)
    os.kill(descendant, signal.SIGKILL)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(descendant, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("test-owned descendant was not reaped")
    registry.remove_exact(owned)
    leader.stdout.close()


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_controller_crash_before_record_releases_no_host_child(tmp_path: Path) -> None:
    pid_path = tmp_path / "inert-child.pid"
    executed_path = tmp_path / "target-executed"
    program = f"""
import os
import subprocess
import sys
from pathlib import Path
from graphene.orchestration.mission_models import MissionStatus
from graphene.orchestration.process_control import ControlledProcessRunner

class CrashBeforeRecord:
    def record(self, _dispatch, process, _executable):
        Path({str(pid_path)!r}).write_text(str(process.pid), encoding="utf-8")
        os._exit(73)

runner = ControlledProcessRunner(
    CrashBeforeRecord(), object(), lambda: MissionStatus.RUNNING
)
runner(
    (sys.executable, "-c", "from pathlib import Path; Path({str(executed_path)!r}).touch()"),
    cwd=Path("/"),
    env={{**os.environ}},
    stdin=subprocess.DEVNULL,
    capture_output=True,
    text=True,
    timeout=5,
    check=False,
)
"""
    controller = subprocess.Popen((sys.executable, "-c", program))
    assert controller.wait(timeout=5) == 73
    pid = int(pid_path.read_text(encoding="utf-8"))

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        observed = subprocess.run(
            ("/bin/ps", "-o", "state=", "-p", str(pid)),
            capture_output=True,
            text=True,
            check=False,
        )
        if observed.returncode or observed.stdout.strip().startswith("Z"):
            break
        time.sleep(0.02)
    else:
        os.killpg(pid, signal.SIGKILL)
        pytest.fail("pre-record controlled child survived its controller")

    assert not executed_path.exists()


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


def test_identity_read_refuses_birth_token_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphene.orchestration import process_control

    tokens = iter(("birth-before", "birth-after"))
    monkeypatch.setattr(
        process_control, "_process_birth_token", lambda _pid: next(tokens)
    )
    monkeypatch.setattr(
        process_control,
        "_process_identity",
        lambda _pid: (123, "Thu Aug 27 12:00:00 2026", "S", "/bin/sleep"),
    )

    with pytest.raises(ProcessControlError, match="changed while reading"):
        process_control._owned_process_identity(123)


def test_zombie_identity_refuses_birth_token_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphene.orchestration import process_control

    tokens = iter(("birth-before", "birth-reused"))
    monkeypatch.setattr(
        process_control, "_process_birth_token", lambda _pid: next(tokens)
    )
    monkeypatch.setattr(
        process_control,
        "_process_identity",
        lambda _pid: (123, "Thu Aug 27 12:00:00 2026", "Z", "python3"),
    )

    with pytest.raises(ProcessControlError, match="changed while reading"):
        process_control._owned_process_identity(123)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_strong_zombie_without_birth_token_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from graphene.orchestration import process_control

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")
    process.kill()
    process.wait(timeout=2)
    monkeypatch.setattr(
        process_control,
        "_owned_process_identity",
        lambda _pid: (
            owned.pgid,
            owned.started_at,
            "Z",
            owned.executable,
            "",
        ),
    )
    monkeypatch.setattr(
        os,
        "waitpid",
        lambda *_args: pytest.fail("unverified PID must not be reaped"),
    )
    monkeypatch.setattr(
        os,
        "killpg",
        lambda *_args: pytest.fail("unverified PGID must not be signalled"),
    )

    with pytest.raises(ProcessControlError, match="birth token is unavailable"):
        registry.terminate_descendants(owned)
    assert registry.has_record(dispatch.attempt_id)

    monkeypatch.undo()
    registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_exact_signal_still_refuses_tokenless_zombie_descendant_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from graphene.orchestration import process_control

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")
    zombie = False
    signals: list[int] = []

    def identity(_pid: int):
        return (
            owned.pgid,
            owned.started_at,
            "Z" if zombie else "S",
            owned.executable,
            "" if zombie else owned.birth_token,
        )

    def signal_group(pgid: int, requested: int) -> None:
        nonlocal zombie
        assert pgid == owned.pgid
        signals.append(requested)
        zombie = True

    monkeypatch.setattr(process_control, "_owned_process_identity", identity)
    monkeypatch.setattr(os, "killpg", signal_group)
    monkeypatch.setattr(
        process_control.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail(
            "unverified descendant group must not be inspected"
        ),
    )
    monkeypatch.setattr(
        os,
        "waitpid",
        lambda *_args: pytest.fail("signalled zombie must not be reaped"),
    )

    with pytest.raises(ProcessControlError, match="birth token is unavailable"):
        registry.terminate_owned(owned, timeout=0.01, retain_record=True)
    assert signals == [signal.SIGTERM]
    assert registry.has_record(dispatch.attempt_id)

    monkeypatch.undo()
    process.kill()
    process.wait(timeout=2)
    registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_exit_during_sigkill_revalidation_is_not_a_termination_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")
    requested: list[int] = []

    def signal_prepared(_owned, requested_signal: int) -> bool:
        requested.append(requested_signal)
        return len(requested) == 1

    monkeypatch.setattr(registry, "signal_prepared", signal_prepared)
    waits = iter((False, True))
    monkeypatch.setattr(
        registry, "_wait_for_exit_after_signal", lambda *_a, **_k: next(waits)
    )
    monkeypatch.setattr(registry, "terminate_descendants", lambda *_a, **_k: None)

    assert registry.terminate_owned(owned, retain_record=True) == signal.SIGTERM
    assert requested == [signal.SIGTERM, signal.SIGKILL]
    assert registry.has_record(dispatch.attempt_id)

    monkeypatch.undo()
    process.kill()
    process.wait(timeout=2)
    registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_absent_leader_never_authorizes_descendant_group_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from graphene.orchestration import process_control

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")
    process.kill()
    process.wait(timeout=2)
    probes: list[tuple[int, int]] = []

    monkeypatch.setattr(
        process_control,
        "_owned_process_identity",
        lambda _pid: (_ for _ in ()).throw(
            ProcessControlError("owned process is no longer running")
        ),
    )
    monkeypatch.setattr(
        os,
        "kill",
        lambda _pid, _requested: (_ for _ in ()).throw(ProcessLookupError()),
    )

    def probe_group(pgid: int, requested: int) -> None:
        probes.append((pgid, requested))
        if requested:
            pytest.fail("unanchored PGID must not be signalled")

    monkeypatch.setattr(os, "killpg", probe_group)

    with pytest.raises(ProcessControlError, match="cannot anchor descendant cleanup"):
        registry.terminate_descendants(owned)
    assert probes == [(owned.pgid, 0)]
    assert registry.has_record(dispatch.attempt_id)

    monkeypatch.undo()
    registry.remove_exact(owned)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_exact_zombie_never_authorizes_descendant_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from graphene.orchestration import process_control

    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    owned = registry.record_pid(dispatch, process.pid, "/bin/sleep")
    identity = (
        owned.pgid,
        owned.started_at,
        "Z",
        owned.executable,
        owned.birth_token,
    )

    monkeypatch.setattr(registry, "_live_identity", lambda _owned: False)
    monkeypatch.setattr(
        process_control, "_owned_process_identity", lambda _pid: identity
    )
    monkeypatch.setattr(
        process_control.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("/bin/ps",),
            returncode=0,
            stdout=f"999 {owned.pgid} S\n",
        ),
    )
    monkeypatch.setattr(
        os,
        "killpg",
        lambda *_args: pytest.fail("zombie anchor must not authorize a signal"),
    )

    with pytest.raises(ProcessControlError, match="cannot be safely signalled"):
        registry.terminate_descendants(owned)
    assert registry.has_record(dispatch.attempt_id)

    monkeypatch.undo()
    process.kill()
    process.wait(timeout=2)
    registry.remove_exact(owned)


def test_linux_identity_uses_proc_executable_instead_of_bare_ps_comm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphene.orchestration import process_control

    monkeypatch.setattr(process_control.sys, "platform", "linux")
    monkeypatch.setattr(
        process_control.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("/bin/ps",),
            returncode=0,
            stdout="424 Tue Aug 19 00:00:00 2026 S sleep\n",
        ),
    )
    monkeypatch.setattr(
        process_control.os,
        "readlink",
        lambda path: "/usr/bin/sleep" if path == "/proc/424/exe" else "",
    )

    assert process_control._process_identity(424) == (
        424,
        "Tue Aug 19 00:00:00 2026",
        "S",
        "/usr/bin/sleep",
    )


def test_linux_identity_recognizes_exit_during_executable_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphene.orchestration import process_control

    observations = iter(
        (
            "424 Tue Aug 19 00:00:00 2026 S python3\n",
            "424 Tue Aug 19 00:00:00 2026 Z python3\n",
        )
    )
    monkeypatch.setattr(process_control.sys, "platform", "linux")
    monkeypatch.setattr(
        process_control.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("/bin/ps",),
            returncode=0,
            stdout=next(observations),
        ),
    )

    def missing_executable(_path: str) -> str:
        raise FileNotFoundError

    monkeypatch.setattr(
        process_control.os,
        "readlink",
        missing_executable,
    )

    assert process_control._process_identity(424)[2:] == ("Z", "python3")
    with pytest.raises(StopIteration):
        next(observations)

    observations = iter(
        (
            "424 Tue Aug 19 00:00:00 2026 S python3\n",
            "424 Tue Aug 19 00:00:00 2026 S python3\n",
        )
    )
    with pytest.raises(ProcessControlError, match="identity is unavailable"):
        process_control._process_identity(424)


def test_linux_strong_legacy_comm_identity_remains_recoverable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphene.orchestration import process_control

    monkeypatch.setattr(process_control.sys, "platform", "linux")
    monkeypatch.setattr(
        process_control.Path,
        "read_text",
        lambda path: "python3\n" if str(path) == "/proc/424/comm" else "",
    )

    assert process_control._matches_live_image(424, "python3", "/usr/bin/python3.13")
    assert process_control._matches_live_image(424, "sh", "/usr/bin/sleep")
    assert not process_control._matches_live_image(424, "other", "/usr/bin/python3.13")

    def unavailable(_path):
        raise OSError("proc comm unavailable")

    monkeypatch.setattr(process_control.Path, "read_text", unavailable)
    with pytest.raises(ProcessControlError, match="identity is unavailable"):
        process_control._matches_live_image(424, "python3", "/usr/bin/python3.13")


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_reused_pid_is_not_signalled_and_stale_record_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record(dispatch, process, "/bin/sleep")
    owned = registry.validate(dispatch)
    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda _pid: (
            owned.pgid,
            owned.started_at,
            "S",
            owned.executable,
        ),
    )
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_birth_token",
        lambda _pid: owned.birth_token + "-reused",
    )
    monkeypatch.setattr(
        os, "killpg", lambda pgid, requested: signalled.append((pgid, requested))
    )

    try:
        assert registry.signal_prepared(owned, 15) is False
        registry.terminate_owned(owned)
        assert signalled == []
        assert not registry.has_record(dispatch.attempt_id)
    finally:
        process.kill()
        process.wait(timeout=2)


@pytest.mark.skipif(
    not Path("/bin/ps").is_file(), reason="POSIX process identity required"
)
def test_legacy_weak_record_is_read_but_never_signalled(tmp_path: Path) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    process = subprocess.Popen(("/bin/sleep", "10"), start_new_session=True)
    registry.record(dispatch, process, "/bin/sleep")
    path = next(registry.directory.iterdir())
    record = json.loads(path.read_text(encoding="utf-8"))
    record.pop("birth_token")
    record.pop("model_input_bytes")
    record.pop("model_request_sha256")
    record.pop("schema_version")
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ProcessControlError, match="cannot be safely signalled"):
        registry.signal(dispatch, 15)
    registry.remove_dead_records_for_mission(dispatch.mission_id)
    assert registry.has_record(dispatch.attempt_id)
    assert process.poll() is None

    process.kill()
    process.wait(timeout=2)
    legacy = registry.owned_process(dispatch, require_live=False)
    assert legacy is not None and legacy.schema_version == 1
    registry.terminate_owned(legacy)
    assert not registry.has_record(dispatch.attempt_id)


def test_record_binds_live_popen_to_validated_observed_exec_identity(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    pid = 424_242
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda observed_pid: (
            observed_pid,
            "Tue Aug 19 00:00:00 2026",
            "S",
            os.path.realpath(sys.executable),
        ),
    )
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_birth_token",
        lambda _pid: "test:birth:424242",
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
    assert record["executable"] == os.path.realpath(sys.executable)
    assert record["birth_token"] == "test:birth:424242"


def test_record_pid_refuses_an_observed_image_other_than_the_launched_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        lambda pid: (
            pid,
            "Tue Aug 19 00:00:00 2026",
            "S",
            "/bin/other",
        ),
    )
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_birth_token",
        lambda _pid: "test:birth:424244",
    )

    with pytest.raises(ProcessControlError, match="does not match child"):
        registry.record_pid(dispatch, 424_244, sys.executable)

    assert not tuple(registry.directory.iterdir())


def test_record_refuses_child_that_exits_during_identity_capture(
    tmp_path: Path, monkeypatch
) -> None:
    _, dispatch = _dispatch(tmp_path)
    registry = OwnedProcessRegistry(tmp_path / "runtime")
    identity_reads = 0

    def exiting_identity(observed_pid: int):
        nonlocal identity_reads
        identity_reads += 1
        if identity_reads > 1:
            raise ProcessControlError("owned process is no longer running")
        return (
            observed_pid,
            "Tue Aug 19 00:00:00 2026",
            "S",
            os.path.realpath(sys.executable),
        )

    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_identity",
        exiting_identity,
    )
    monkeypatch.setattr(
        "graphene.orchestration.process_control._process_birth_token",
        lambda _pid: "test:birth:424243",
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
        lambda _pid: (
            owned.pgid,
            owned.started_at,
            "Z",
            "<defunct>",
        ),
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
