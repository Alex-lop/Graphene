from __future__ import annotations

import json
import os
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
from .models import Dispatch, MissionStatus


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


def _process_identity(pid: int) -> tuple[int, str, str]:
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
    fields = result.stdout.strip().split(None, 6)
    if result.returncode or len(fields) != 7:
        raise ProcessControlError("owned process is no longer running")
    try:
        pgid = int(fields[0])
    except ValueError as error:
        raise ProcessControlError("owned process identity is invalid") from error
    return pgid, " ".join(fields[1:6]), fields[6]


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
        self, dispatch: Dispatch, process: subprocess.Popen[str], executable: str
    ) -> None:
        pgid, started_at, observed_executable = _process_identity(process.pid)
        executable_path = Path(executable)
        if not executable_path.is_absolute() or not executable_path.is_file():
            raise ProcessControlError("owned process executable is unavailable")
        expected_executable = str(executable_path)
        if pgid != process.pid or observed_executable != expected_executable:
            raise ProcessControlError(
                "child process did not establish its owned process group"
            )
        owned = OwnedProcess(
            dispatch.mission_id,
            dispatch.attempt_id,
            process.pid,
            pgid,
            started_at,
            expected_executable,
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
                raise ProcessControlError("owned process record already exists") from error
            directory_descriptor = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def remove(self, dispatch: Dispatch) -> None:
        self._path(dispatch.attempt_id).unlink(missing_ok=True)

    def validate(self, dispatch: Dispatch) -> OwnedProcess:
        path = self._path(dispatch.attempt_id)
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
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as error:
            raise ProcessControlError("owned process record is invalid") from error
        if (
            owned.mission_id != dispatch.mission_id
            or owned.attempt_id != dispatch.attempt_id
            or not isinstance(owned.mission_id, str)
            or not isinstance(owned.attempt_id, str)
            or type(owned.pid) is not int
            or owned.pid <= 1
            or type(owned.pgid) is not int
            or owned.pgid != owned.pid
            or not isinstance(owned.started_at, str)
            or not isinstance(owned.executable, str)
            or not owned.executable.startswith("/")
        ):
            raise ProcessControlError("owned process record does not match dispatch")
        pgid, started_at, executable = _process_identity(owned.pid)
        if (pgid, started_at, executable) != (
            owned.pgid,
            owned.started_at,
            owned.executable,
        ):
            raise ProcessControlError("owned process identity changed")
        return owned

    def prepare_cancel(self, dispatches: Sequence[Dispatch]) -> tuple[OwnedProcess, ...]:
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
        os.killpg(owned.pgid, requested)

    def signal_prepared(self, owned: OwnedProcess, requested: int) -> None:
        """Signal an identity captured before a mission-state transition."""

        self._validate_signal(requested)
        try:
            current = _process_identity(owned.pid)
        except ProcessControlError:
            try:
                os.kill(owned.pid, 0)
            except ProcessLookupError:
                return
            raise
        if current != (owned.pgid, owned.started_at, owned.executable):
            raise ProcessControlError("owned process identity changed")
        os.killpg(owned.pgid, requested)


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
                self.registry.record(self.dispatch, process, arguments[0])
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
                return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
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
