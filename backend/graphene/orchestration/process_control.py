from __future__ import annotations

import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..hashing import canonical_json_bytes, sha256_hex
from .mission_models import Dispatch, MissionStatus


class ProcessControlError(RuntimeError):
    pass


class ProcessCancelled(ProcessControlError):
    pass


@dataclass(frozen=True, slots=True)
class OwnedProcess:
    mission_id: str
    attempt_id: str
    pid: int
    pgid: int
    started_at: str
    executable: str


def _process_identity(pid: int) -> tuple[int, str, str, str]:
    if pid <= 1 or not Path("/bin/ps").is_file():
        raise ProcessControlError("owned process identity is unavailable")
    try:
        result = subprocess.run(
            (
                "/bin/ps",
                "-o",
                "pgid=",
                "-o",
                "lstart=",
                "-o",
                "state=",
                "-o",
                "comm=",
                "-p",
                str(pid),
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProcessControlError("owned process identity is unavailable") from error
    fields = result.stdout.strip().split(None, 7)
    if result.returncode or len(fields) != 8:
        raise ProcessControlError("owned process is no longer running")
    try:
        pgid = int(fields[0])
    except ValueError as error:
        raise ProcessControlError("owned process identity is invalid") from error
    return pgid, " ".join(fields[1:6]), fields[6], fields[7]


# Wrappers that replace their own image with the wrapped command (``exec`` in
# place) without forking. The process identity (pid, process group, start
# time) survives the exec while ``comm`` changes, so an executable change is
# accepted only for a child that was recorded under one of these wrappers.
_EXEC_IN_PLACE_WRAPPERS = frozenset({"/usr/bin/sandbox-exec"})

# python.org's macOS framework build ships ``bin/python3.x`` as a launcher that
# execs ``Resources/Python.app/Contents/MacOS/Python`` in place, so a child
# started through that interpreter -- or a venv symlink to it -- is reported
# under the app binary a few milliseconds after Popen returns. The GitHub macOS
# runner's toolcache interpreter is exactly this build; Homebrew, uv and
# Anaconda interpreters are not, which is why the refusal only reproduced in CI.
_FRAMEWORK_LAUNCHER = re.compile(
    r"(?P<framework>.*/Python\.framework/Versions/[^/]+)/bin/python[0-9.]*t?(-intel64)?$"
)
_FRAMEWORK_APP_BINARY = "/Resources/Python.app/Contents/MacOS/Python"


def _expected_images(executable: str) -> frozenset[str] | None:
    """Every image a child launched as ``executable`` may legitimately report.

    ``None`` means any image: the executable is a wrapper that execs an
    arbitrary command in place.
    """
    if executable in _EXEC_IN_PLACE_WRAPPERS:
        return None
    real = os.path.realpath(executable)
    images = {executable, real}
    match = _FRAMEWORK_LAUNCHER.match(real)
    if match:
        images.add(match.group("framework") + _FRAMEWORK_APP_BINARY)
    return frozenset(images)


class OwnedProcessRegistry:
    """Private identity records for Graphene-created process-group leaders."""

    def __init__(self, runtime: Path) -> None:
        self.directory = runtime / "processes"
        if self.directory.exists() and (
            self.directory.is_symlink() or not self.directory.is_dir()
        ):
            raise ProcessControlError("process registry is unsafe")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)

    def _path(self, attempt_id: str) -> Path:
        return self.directory / (sha256_hex(attempt_id.encode()) + ".json")

    def record(
        self,
        dispatch: Dispatch,
        process: subprocess.Popen[str],
        executable: str,
    ) -> None:
        executable_path = Path(executable)
        arguments = process.args
        if (
            not executable_path.is_absolute()
            or not executable_path.is_file()
            or not os.access(executable_path, os.X_OK)
            or isinstance(arguments, (str, bytes))
            or not arguments
            or arguments[0] != executable
        ):
            raise ProcessControlError("owned process executable is unavailable")
        if process.poll() is not None:
            raise ProcessControlError("owned process is no longer running")
        pgid, started_at, state, observed_executable = _process_identity(process.pid)
        if state.startswith("Z") or process.poll() is not None:
            raise ProcessControlError("owned process is no longer running")
        if (
            not observed_executable
            or len(observed_executable) > 1_024
            or any(character in observed_executable for character in "\0\n\r")
        ):
            raise ProcessControlError("owned process identity is invalid")
        if observed_executable.startswith("(") and observed_executable.endswith(")"):
            # BSD ps parenthesises comm while the child is still replacing its
            # image, which is exactly when a launcher that execs in place gets
            # recorded under load. We launched this child with ``executable``
            # as argv[0] a moment ago, so that is the better fact; whatever it
            # becomes is judged later by _live_identity against the images that
            # launcher is allowed to turn into.
            observed_executable = executable
        if pgid != process.pid:
            raise ProcessControlError(
                "child process did not establish its owned process group"
            )
        owned = OwnedProcess(
            dispatch.mission_id,
            dispatch.attempt_id,
            process.pid,
            pgid,
            started_at,
            observed_executable,
        )
        target = self._path(dispatch.attempt_id)
        temporary = self.directory / f".{target.name}.{secrets.token_hex(12)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(
                    canonical_json_bytes(
                        {
                            "attempt_id": owned.attempt_id,
                            "executable": owned.executable,
                            "mission_id": owned.mission_id,
                            "pgid": owned.pgid,
                            "pid": owned.pid,
                            "started_at": owned.started_at,
                        }
                    )
                )
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as error:
                raise ProcessControlError(
                    "owned process record already exists"
                ) from error
            directory_descriptor = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def remove(self, dispatch: Dispatch) -> None:
        self._path(dispatch.attempt_id).unlink(missing_ok=True)

    def _read(self, path: Path) -> OwnedProcess:
        try:
            metadata = path.lstat()
        except OSError as error:
            raise ProcessControlError("owned process record is unavailable") from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ProcessControlError("owned process record is unsafe")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if set(raw) != {
                "attempt_id",
                "executable",
                "mission_id",
                "pgid",
                "pid",
                "started_at",
            }:
                raise ValueError("unexpected process identity fields")
            owned = OwnedProcess(
                mission_id=raw["mission_id"],
                attempt_id=raw["attempt_id"],
                pid=raw["pid"],
                pgid=raw["pgid"],
                started_at=raw["started_at"],
                executable=raw["executable"],
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            OSError,
        ) as error:
            raise ProcessControlError("owned process record is invalid") from error
        if (
            not isinstance(owned.mission_id, str)
            or not isinstance(owned.attempt_id, str)
            or type(owned.pid) is not int
            or owned.pid <= 1
            or type(owned.pgid) is not int
            or owned.pgid != owned.pid
            or not isinstance(owned.started_at, str)
            or not isinstance(owned.executable, str)
            or not owned.executable
            or len(owned.executable) > 1_024
            or any(character in owned.executable for character in "\0\n\r")
        ):
            raise ProcessControlError("owned process record is invalid")
        if path != self._path(owned.attempt_id):
            raise ProcessControlError("owned process record path does not match")
        return owned

    @staticmethod
    def _live_identity(owned: OwnedProcess) -> bool:
        try:
            current = _process_identity(owned.pid)
        except ProcessControlError:
            try:
                os.kill(owned.pid, 0)
            except ProcessLookupError:
                return False
            raise
        pgid, started_at, state, executable = current
        if state.startswith("Z"):
            return False
        if (pgid, started_at) != (owned.pgid, owned.started_at):
            raise ProcessControlError("owned process identity changed")
        if executable != owned.executable:
            images = _expected_images(owned.executable)
            if (
                images is not None
                and executable not in images
                and os.path.realpath(executable) not in images
            ):
                raise ProcessControlError("owned process identity changed")
        return True

    def has_record(self, attempt_id: str) -> bool:
        """True while a durable record for ``attempt_id`` exists on disk."""

        try:
            self._path(attempt_id).lstat()
        except FileNotFoundError:
            return False
        return True

    def validate(self, dispatch: Dispatch) -> OwnedProcess:
        owned = self._read(self._path(dispatch.attempt_id))
        if (
            owned.mission_id != dispatch.mission_id
            or owned.attempt_id != dispatch.attempt_id
        ):
            raise ProcessControlError("owned process record does not match dispatch")
        if not self._live_identity(owned):
            raise ProcessControlError("owned process is no longer running")
        return owned

    def records_for_mission(self, mission_id: str) -> tuple[OwnedProcess, ...]:
        records: list[OwnedProcess] = []
        for index, path in enumerate(sorted(self.directory.iterdir())):
            if index >= 4_096:
                raise ProcessControlError("process registry exceeds its safe limit")
            stem, suffix = path.name.rsplit(".", 1) if "." in path.name else ("", "")
            if (
                suffix != "json"
                or len(stem) != 64
                or any(character not in "0123456789abcdef" for character in stem)
            ):
                continue
            owned = self._read(path)
            if owned.mission_id == mission_id:
                self._live_identity(owned)  # exact live identity or confirmed gone
                records.append(owned)
        return tuple(records)

    def prepare_cancel(
        self, dispatches: Sequence[Dispatch]
    ) -> tuple[OwnedProcess, ...]:
        return tuple(self.validate(dispatch) for dispatch in dispatches)

    @staticmethod
    def _validate_signal(requested: int) -> None:
        allowed = {
            signal.SIGTERM,
            signal.SIGKILL,
            getattr(signal, "SIGSTOP", signal.SIGTERM),
            getattr(signal, "SIGCONT", signal.SIGTERM),
        }
        if requested not in allowed:
            raise ProcessControlError("process signal is not allowed")

    def signal(self, dispatch: Dispatch, requested: int) -> None:
        self._validate_signal(requested)
        owned = self.validate(dispatch)
        self._kill_group(owned, requested)

    @staticmethod
    def _kill_group(owned: OwnedProcess, requested: int) -> None:
        try:
            os.killpg(owned.pgid, requested)
        except ProcessLookupError:
            return

    def signal_prepared(self, owned: OwnedProcess, requested: int) -> None:
        """Signal an identity captured before a mission-state transition."""

        self._validate_signal(requested)
        if self._live_identity(owned):
            self._kill_group(owned, requested)

    def terminate_owned(self, owned: OwnedProcess, *, timeout: float = 2) -> None:
        """Terminate a prevalidated group, confirm absence, then remove its exact record."""

        if timeout <= 0:
            raise ProcessControlError("process termination timeout must be positive")
        path = self._path(owned.attempt_id)
        try:
            if self._read(path) != owned:
                raise ProcessControlError(
                    "owned process record changed before termination"
                )
        except ProcessControlError:
            try:
                path.lstat()
            except FileNotFoundError:
                if not self._live_identity(owned):
                    return
            raise
        self.signal_prepared(owned, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while self._live_identity(owned) and time.monotonic() < deadline:
            time.sleep(0.05)
        if self._live_identity(owned):
            self.signal_prepared(owned, signal.SIGKILL)
            deadline = time.monotonic() + timeout
            while self._live_identity(owned) and time.monotonic() < deadline:
                time.sleep(0.05)
        if self._live_identity(owned):
            raise ProcessControlError("owned process could not be terminated")
        try:
            recorded = self._read(path)
        except ProcessControlError as error:
            try:
                path.lstat()
            except FileNotFoundError:
                return
            raise error
        if recorded != owned:
            raise ProcessControlError("owned process record changed during termination")
        path.unlink()
        directory_descriptor = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)


class ControlledProcessRunner:
    """subprocess.run-compatible runner for one scripted attempt."""

    def __init__(
        self,
        registry: OwnedProcessRegistry,
        dispatch: Dispatch,
        status: Callable[[], MissionStatus],
        *,
        heartbeat: Callable[[], object] | None = None,
        heartbeat_seconds: float = 10,
        poll_seconds: float = 0.05,
    ) -> None:
        self.registry = registry
        self.dispatch = dispatch
        self.status = status
        self.heartbeat = heartbeat
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_seconds = poll_seconds

    def __call__(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdin: int,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        if (
            not arguments
            or stdin is not subprocess.DEVNULL
            or not capture_output
            or not text
            or check
        ):
            raise ProcessControlError("controlled process invocation is unsupported")
        process = subprocess.Popen(
            arguments,
            cwd=cwd,
            env=env,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        stopped = False
        registered = False
        elapsed = 0.0
        last = time.monotonic()
        last_heartbeat = last
        try:
            try:
                self.registry.record(
                    self.dispatch,
                    process,
                    arguments[0],
                )
                registered = True
            except Exception:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
                raise
            while True:
                state = self.status()
                now = time.monotonic()
                if not stopped:
                    elapsed += now - last
                last = now
                if (
                    self.heartbeat is not None
                    and now - last_heartbeat >= self.heartbeat_seconds
                ):
                    self.heartbeat()
                    last_heartbeat = now
                if state == MissionStatus.CANCELLED:
                    self.registry.signal(self.dispatch, signal.SIGTERM)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.registry.signal(self.dispatch, signal.SIGKILL)
                    process.communicate()
                    raise ProcessCancelled("scripted attempt was cancelled")
                if state == MissionStatus.PAUSED and not stopped:
                    self.registry.signal(self.dispatch, signal.SIGSTOP)
                    stopped = True
                elif state == MissionStatus.RUNNING and stopped:
                    self.registry.signal(self.dispatch, signal.SIGCONT)
                    stopped = False
                if elapsed >= timeout:
                    if stopped:
                        self.registry.signal(self.dispatch, signal.SIGCONT)
                        stopped = False
                    self.registry.signal(self.dispatch, signal.SIGKILL)
                    stdout, stderr = process.communicate()
                    raise subprocess.TimeoutExpired(arguments, timeout, stdout, stderr)
                try:
                    stdout, stderr = process.communicate(timeout=self.poll_seconds)
                except subprocess.TimeoutExpired:
                    continue
                if self.status() == MissionStatus.CANCELLED:
                    raise ProcessCancelled("scripted attempt was cancelled")
                return subprocess.CompletedProcess(
                    arguments, process.returncode, stdout, stderr
                )
        finally:
            original_error = sys.exc_info()[0] is not None
            cleanup_error: Exception | None = None
            try:
                if process.poll() is None:
                    if stopped:
                        self.registry.signal(self.dispatch, signal.SIGCONT)
                    self.registry.signal(self.dispatch, signal.SIGTERM)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.registry.signal(self.dispatch, signal.SIGKILL)
                        process.wait(timeout=2)
                if registered:
                    self.registry.remove(self.dispatch)
            except Exception as error:
                cleanup_error = error
            if cleanup_error is not None and not original_error:
                raise cleanup_error


__all__ = [
    "ControlledProcessRunner",
    "OwnedProcess",
    "OwnedProcessRegistry",
    "ProcessCancelled",
    "ProcessControlError",
]
