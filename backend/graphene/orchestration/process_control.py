from __future__ import annotations

import json
import ctypes
import os
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..hashing import canonical_json_bytes, sha256_hex
from ..core_models import MAX_TEST_OUTPUT_BYTES
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
    birth_token: str | None
    executable: str
    model_request_sha256: str | None = None
    model_input_bytes: int | None = None
    schema_version: int = 2


@dataclass(frozen=True, slots=True)
class ModelDispatchBarrier:
    mission_id: str
    task_id: str
    attempt_id: str
    lease_id: str
    fencing_token: int
    request_sha256: str
    sdk_invocation_id: str
    dispatched_at: str
    pid: int
    pgid: int
    started_at: str
    birth_token: str | None
    executable: str
    schema_version: int = 2


def _process_birth_token(pid: int) -> str:
    if sys.platform.startswith("linux"):
        try:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            stat_fields = Path(f"/proc/{pid}/stat").read_text().rstrip()
        except OSError as error:
            raise ProcessControlError(
                "owned process birth token is unavailable"
            ) from error
        end = stat_fields.rfind(")")
        fields = stat_fields[end + 2 :].split() if end >= 0 else []
        start_ticks = fields[19] if len(fields) > 19 else ""
        if (
            re.fullmatch(r"[0-9a-fA-F-]{36}", boot_id) is None
            or not start_ticks.isdigit()
        ):
            raise ProcessControlError("owned process birth token is invalid")
        return f"linux:{boot_id.lower()}:{start_ticks}"
    if sys.platform == "darwin":

        class ProcBSDInfo(ctypes.Structure):
            _fields_ = [
                ("pbi_flags", ctypes.c_uint32),
                ("pbi_status", ctypes.c_uint32),
                ("pbi_xstatus", ctypes.c_uint32),
                ("pbi_pid", ctypes.c_uint32),
                ("pbi_ppid", ctypes.c_uint32),
                ("pbi_uid", ctypes.c_uint32),
                ("pbi_gid", ctypes.c_uint32),
                ("pbi_ruid", ctypes.c_uint32),
                ("pbi_rgid", ctypes.c_uint32),
                ("pbi_svuid", ctypes.c_uint32),
                ("pbi_svgid", ctypes.c_uint32),
                ("pbi_rfu_1", ctypes.c_uint32),
                ("pbi_comm", ctypes.c_char * 16),
                ("pbi_name", ctypes.c_char * 32),
                ("pbi_nfiles", ctypes.c_uint32),
                ("pbi_pgid", ctypes.c_uint32),
                ("pbi_pjobc", ctypes.c_uint32),
                ("e_tdev", ctypes.c_uint32),
                ("e_tpgid", ctypes.c_uint32),
                ("pbi_nice", ctypes.c_int32),
                ("pbi_start_tvsec", ctypes.c_uint64),
                ("pbi_start_tvusec", ctypes.c_uint64),
            ]

        try:
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            proc_pidinfo = libproc.proc_pidinfo
            proc_pidinfo.argtypes = (
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            )
            proc_pidinfo.restype = ctypes.c_int
            info = ProcBSDInfo()
            size = proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        except (AttributeError, OSError) as error:
            raise ProcessControlError(
                "owned process birth token is unavailable"
            ) from error
        if (
            size != ctypes.sizeof(info)
            or info.pbi_pid != pid
            or info.pbi_start_tvsec <= 0
            or info.pbi_start_tvusec >= 1_000_000
        ):
            raise ProcessControlError("owned process birth token is unavailable")
        return f"darwin:{info.pbi_start_tvsec}:{info.pbi_start_tvusec}"
    raise ProcessControlError("owned process birth token is unsupported")


def _process_identity(pid: int) -> tuple[int, str, str, str]:
    if pid <= 1 or not Path("/bin/ps").is_file():
        raise ProcessControlError("owned process identity is unavailable")

    def read_ps() -> tuple[int, str, str, str]:
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
            raise ProcessControlError(
                "owned process identity is unavailable"
            ) from error
        fields = result.stdout.strip().split(None, 7)
        if result.returncode or len(fields) != 8:
            raise ProcessControlError("owned process is no longer running")
        try:
            pgid = int(fields[0])
        except ValueError as error:
            raise ProcessControlError("owned process identity is invalid") from error
        return pgid, " ".join(fields[1:6]), fields[6], fields[7]

    pgid, started_at, state, executable = read_ps()
    if sys.platform.startswith("linux"):
        try:
            executable = os.readlink(f"/proc/{pid}/exe")
        except OSError as error:
            if not state.startswith("Z"):
                current = read_ps()
                if current[:2] != (pgid, started_at) or not current[2].startswith("Z"):
                    raise ProcessControlError(
                        "owned process identity is unavailable"
                    ) from error
                pgid, started_at, state, executable = current
    return pgid, started_at, state, executable


def _owned_process_identity(pid: int) -> tuple[int, str, str, str, str]:
    try:
        birth_before = _process_birth_token(pid)
    except ProcessControlError:
        identity = _process_identity(pid)
        if identity[2].startswith("Z"):
            return (*identity, "")
        raise
    identity = _process_identity(pid)
    birth_after = _process_birth_token(pid)
    if birth_before != birth_after:
        raise ProcessControlError("owned process identity changed while reading")
    return (*identity, birth_after)


# Wrappers that replace their own image with the wrapped command (``exec`` in
# place) without forking. The process identity (pid, process group, start
# time) survives the exec while ``comm`` changes, so an executable change is
# accepted only for a child that was recorded under one of these wrappers.
_EXEC_IN_PLACE_WRAPPERS = frozenset(
    {"/bin/sh", os.path.realpath("/bin/sh"), "/usr/bin/sandbox-exec"}
)

_CONTROLLED_LAUNCH_SCRIPT = """
if IFS= read -r graphene_ready && [ "$graphene_ready" = graphene-go ]; then
    exec </dev/null
    exec "$@"
fi
exit 125
"""

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


def _matches_expected_image(executable: str, observed: str) -> bool:
    images = _expected_images(executable)
    return images is None or observed in images or os.path.realpath(observed) in images


def _matches_live_image(pid: int, executable: str, observed: str) -> bool:
    if _matches_expected_image(executable, observed):
        return True
    if not sys.platform.startswith("linux") or "/" in executable:
        return False
    if executable == "sh":
        return True
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip() == executable
    except OSError as error:
        raise ProcessControlError("owned process identity is unavailable") from error


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
        self.barriers = runtime / "model-dispatches"
        if self.barriers.exists() and (
            self.barriers.is_symlink() or not self.barriers.is_dir()
        ):
            raise ProcessControlError("model dispatch registry is unsafe")
        self.barriers.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.barriers, 0o700)

    def _path(self, attempt_id: str, *, model: bool = False) -> Path:
        suffix = ".model.json" if model else ".json"
        return self.directory / (sha256_hex(attempt_id.encode()) + suffix)

    def _owned_path(self, owned: OwnedProcess) -> Path:
        return self._path(
            owned.attempt_id,
            model=owned.model_request_sha256 is not None,
        )

    def _barrier_path(self, attempt_id: str) -> Path:
        return self.barriers / (sha256_hex(attempt_id.encode()) + ".json")

    def _model_path(self, attempt_id: str) -> Path:
        current = self._path(attempt_id, model=True)
        legacy = self._path(attempt_id)
        return (
            legacy
            if not current.exists() and self._barrier_path(attempt_id).exists()
            else current
        )

    @staticmethod
    def _atomic_create(directory: Path, target: Path, value: object) -> None:
        temporary = directory / f".{target.name}.{secrets.token_hex(12)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as error:
                raise ProcessControlError(
                    "process identity record already exists"
                ) from error
            directory_descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def record_pid(
        self,
        dispatch: Dispatch,
        pid: int,
        executable: str,
        *,
        model_request_sha256: str | None = None,
        model_input_bytes: int | None = None,
    ) -> OwnedProcess:
        """Bind a just-spawned async child to the same identity used for signals."""

        executable_path = Path(executable)
        if (
            type(pid) is not int
            or pid <= 1
            or not executable_path.is_absolute()
            or not executable_path.is_file()
            or not os.access(executable_path, os.X_OK)
        ):
            raise ProcessControlError("owned process executable is unavailable")
        model_process = model_request_sha256 is not None
        if model_process != (model_input_bytes is not None) or (
            model_process
            and (
                re.fullmatch(r"[0-9a-f]{64}", model_request_sha256 or "") is None
                or type(model_input_bytes) is not int
                or not 1 <= model_input_bytes <= 2_097_152
            )
        ):
            raise ProcessControlError("model process intent is invalid")
        pgid, started_at, state, observed_executable, birth_token = (
            _owned_process_identity(pid)
        )
        if state.startswith("Z"):
            raise ProcessControlError("owned process is no longer running")
        if (
            not observed_executable
            or len(observed_executable) > 1_024
            or any(character in observed_executable for character in "\0\n\r")
        ):
            raise ProcessControlError("owned process identity is invalid")
        if (
            _expected_images(executable) is None
            or observed_executable.startswith("(")
            and observed_executable.endswith(")")
        ):
            observed_executable = executable
        if not _matches_expected_image(executable, observed_executable):
            raise ProcessControlError("owned process executable does not match child")
        if pgid != pid:
            raise ProcessControlError(
                "child process did not establish its owned process group"
            )
        owned = OwnedProcess(
            dispatch.mission_id,
            dispatch.attempt_id,
            pid,
            pgid,
            started_at,
            birth_token,
            observed_executable,
            model_request_sha256,
            model_input_bytes,
            3 if model_process else 2,
        )
        self._atomic_create(
            self.directory,
            self._path(dispatch.attempt_id, model=model_process),
            {
                "attempt_id": owned.attempt_id,
                "executable": owned.executable,
                "mission_id": owned.mission_id,
                "model_input_bytes": owned.model_input_bytes,
                "model_request_sha256": owned.model_request_sha256,
                "pgid": owned.pgid,
                "pid": owned.pid,
                "started_at": owned.started_at,
                "birth_token": owned.birth_token,
                "schema_version": owned.schema_version,
            },
        )
        return owned

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
        self.record_pid(dispatch, process.pid, executable)
        if process.poll() is not None:
            self.remove(dispatch)
            raise ProcessControlError("owned process is no longer running")

    def remove(self, dispatch: Dispatch) -> None:
        if (self.directory.parent / "cancellation-request.json").exists():
            return
        path = self._path(dispatch.attempt_id)
        try:
            owned = self._read(path)
        except ProcessControlError:
            path.unlink(missing_ok=True)
        else:
            if owned.mission_id != dispatch.mission_id:
                raise ProcessControlError(
                    "owned process record does not match dispatch"
                )
            self.remove_exact(owned)

    def remove_exact(self, owned: OwnedProcess) -> None:
        path = self._owned_path(owned)
        try:
            recorded = self._read(path)
        except ProcessControlError:
            if path.exists():
                raise
            return
        if recorded != owned:
            raise ProcessControlError("owned process record changed before removal")
        if self._live_identity(owned):
            raise ProcessControlError("owned process is still running")
        self.terminate_descendants(owned)
        barrier_path = self._barrier_path(owned.attempt_id)
        barrier = None
        if barrier_path.exists():
            try:
                raw_barrier = json.loads(barrier_path.read_text(encoding="utf-8"))
                provisional = Dispatch.model_construct(
                    mission_id=raw_barrier["mission_id"],
                    task_id=raw_barrier["task_id"],
                    attempt_id=raw_barrier["attempt_id"],
                    lease_id=raw_barrier["lease_id"],
                    fencing_token=raw_barrier["fencing_token"],
                )
                barrier = self._read_model_dispatch_barrier(provisional)
            except (KeyError, TypeError, json.JSONDecodeError, OSError) as error:
                raise ProcessControlError(
                    "model dispatch barrier is invalid"
                ) from error
            if barrier is not None and (
                barrier.mission_id,
                barrier.attempt_id,
            ) != (owned.mission_id, owned.attempt_id):
                raise ProcessControlError(
                    "model dispatch barrier does not match process record"
                )
        model_record = path == self._path(owned.attempt_id, model=True) or (
            barrier is not None and self._barrier_matches_owned(barrier, owned)
        )
        if model_record:
            self._barrier_path(owned.attempt_id).unlink(missing_ok=True)
            self._fsync_directory(self.barriers)
        path.unlink(missing_ok=True)
        self._fsync_directory(self.directory)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = -1
        try:
            descriptor = os.open(
                directory,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            os.fsync(descriptor)
        except OSError as error:
            raise ProcessControlError(
                "process cleanup durability is unconfirmed"
            ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def remove_barrier_exact(
        self, dispatch: Dispatch, barrier: ModelDispatchBarrier
    ) -> None:
        """Idempotently remove an exact barrier whose process record is gone."""

        current = self._read_model_dispatch_barrier(dispatch)
        if current is None:
            return
        if current != barrier:
            raise ProcessControlError("model dispatch barrier changed before removal")
        owned, rebound = self.terminal_model_state(dispatch)
        if owned is not None or rebound != barrier:
            raise ProcessControlError("model dispatch cleanup state changed")
        self._barrier_path(dispatch.attempt_id).unlink(missing_ok=True)
        self._fsync_directory(self.barriers)

    def acknowledge_model_dispatch(
        self,
        dispatch: Dispatch,
        owned: OwnedProcess,
        *,
        request_sha256: str,
        sdk_invocation_id: str,
        dispatched_at: str,
    ) -> ModelDispatchBarrier:
        recorded = self.owned_process(
            dispatch,
            require_live=False,
            model=owned.model_request_sha256 is not None,
        )
        if recorded != owned or (
            owned.model_request_sha256 is None
            and self._path(dispatch.attempt_id, model=True).exists()
        ):
            raise ProcessControlError("model dispatch process identity changed")
        if not re.fullmatch(r"[0-9a-f]{64}", request_sha256):
            raise ProcessControlError("model dispatch request digest is invalid")
        if (
            not isinstance(sdk_invocation_id, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", sdk_invocation_id)
            is None
        ):
            raise ProcessControlError("model dispatch invocation identity is invalid")
        if (
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", dispatched_at)
            is None
        ):
            raise ProcessControlError("model dispatch timestamp is invalid")
        if owned.schema_version == 3 and owned.model_request_sha256 != request_sha256:
            raise ProcessControlError("model dispatch request changed after spawn")
        barrier = ModelDispatchBarrier(
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            lease_id=dispatch.lease_id,
            fencing_token=dispatch.fencing_token,
            request_sha256=request_sha256,
            sdk_invocation_id=sdk_invocation_id,
            dispatched_at=dispatched_at,
            pid=owned.pid,
            pgid=owned.pgid,
            started_at=owned.started_at,
            birth_token=owned.birth_token,
            executable=owned.executable,
        )
        self._atomic_create(
            self.barriers,
            self._barrier_path(dispatch.attempt_id),
            asdict(barrier),
        )
        return barrier

    def _read_model_dispatch_barrier(
        self, dispatch: Dispatch
    ) -> ModelDispatchBarrier | None:
        path = self._barrier_path(dispatch.attempt_id)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return None
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ProcessControlError("model dispatch barrier is unsafe")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            current_fields = set(ModelDispatchBarrier.__dataclass_fields__)
            legacy_fields = current_fields - {"birth_token", "schema_version"}
            if set(raw) == legacy_fields:
                raw = {**raw, "birth_token": None, "schema_version": 1}
            elif set(raw) != current_fields:
                raise ValueError("unexpected model dispatch barrier fields")
            barrier = ModelDispatchBarrier(**raw)
        except (TypeError, ValueError, json.JSONDecodeError, OSError) as error:
            raise ProcessControlError("model dispatch barrier is invalid") from error
        if (
            not isinstance(barrier.mission_id, str)
            or not isinstance(barrier.task_id, str)
            or not isinstance(barrier.attempt_id, str)
            or not isinstance(barrier.lease_id, str)
            or type(barrier.fencing_token) is not int
            or barrier.fencing_token < 1
            or re.fullmatch(r"[0-9a-f]{64}", barrier.request_sha256) is None
            or not isinstance(barrier.sdk_invocation_id, str)
            or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
                barrier.sdk_invocation_id,
            )
            is None
            or not isinstance(barrier.dispatched_at, str)
            or re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z",
                barrier.dispatched_at,
            )
            is None
            or type(barrier.pid) is not int
            or type(barrier.pgid) is not int
            or barrier.pid <= 1
            or barrier.pgid != barrier.pid
            or not isinstance(barrier.started_at, str)
            or barrier.schema_version not in {1, 2}
            or (barrier.schema_version == 1) != (barrier.birth_token is None)
            or not isinstance(barrier.executable, str)
            or not barrier.executable
        ):
            raise ProcessControlError("model dispatch barrier is invalid")
        if (barrier.mission_id, barrier.task_id, barrier.attempt_id) != (
            dispatch.mission_id,
            dispatch.task_id,
            dispatch.attempt_id,
        ) or (barrier.lease_id, barrier.fencing_token) != (
            dispatch.lease_id,
            dispatch.fencing_token,
        ):
            raise ProcessControlError("model dispatch barrier identity changed")
        return barrier

    @staticmethod
    def _barrier_matches_owned(
        barrier: ModelDispatchBarrier, owned: OwnedProcess
    ) -> bool:
        return (
            barrier.pid,
            barrier.pgid,
            barrier.started_at,
            barrier.birth_token,
            barrier.executable,
        ) == (
            owned.pid,
            owned.pgid,
            owned.started_at,
            owned.birth_token,
            owned.executable,
        )

    def terminal_model_state(
        self, dispatch: Dispatch
    ) -> tuple[OwnedProcess | None, ModelDispatchBarrier | None]:
        """Read every exact cleanup state without requiring both files."""

        barrier = self._read_model_dispatch_barrier(dispatch)
        current = self._path(dispatch.attempt_id, model=True)
        legacy = self._path(dispatch.attempt_id)
        owned = self._read(current) if current.exists() else None
        if owned is None and barrier is not None and legacy.exists():
            candidate = self._read(legacy)
            if self._barrier_matches_owned(barrier, candidate):
                owned = candidate
        if owned is not None and (
            owned.mission_id != dispatch.mission_id
            or owned.attempt_id != dispatch.attempt_id
        ):
            raise ProcessControlError("owned process record does not match dispatch")
        if (
            owned is not None
            and barrier is not None
            and not self._barrier_matches_owned(barrier, owned)
        ):
            raise ProcessControlError("model dispatch barrier identity changed")
        return owned, barrier

    def model_dispatch_barrier(
        self, dispatch: Dispatch, *, require_live: bool = True
    ) -> ModelDispatchBarrier | None:
        owned, barrier = self.terminal_model_state(dispatch)
        if barrier is None:
            return None
        if owned is None:
            raise ProcessControlError("model dispatch process record is unavailable")
        if require_live and not self._live_identity(owned):
            raise ProcessControlError("owned process is no longer running")
        return barrier

    def confirm_model_dispatch_barrier(
        self, dispatch: Dispatch
    ) -> ModelDispatchBarrier | None:
        """Re-establish file+directory durability before trusting a barrier."""

        barrier = self.model_dispatch_barrier(dispatch, require_live=False)
        if barrier is None:
            return None
        path = self._barrier_path(dispatch.attempt_id)
        descriptor = -1
        directory = -1
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            opened = os.fstat(descriptor)
            visible = path.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or stat.S_IMODE(opened.st_mode) & 0o077
                or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
            ):
                raise OSError("model dispatch barrier identity changed")
            os.fsync(descriptor)
            directory = os.open(
                self.barriers,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            os.fsync(directory)
        except OSError as error:
            raise ProcessControlError(
                "model dispatch barrier durability is unconfirmed"
            ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory >= 0:
                os.close(directory)
        if self.model_dispatch_barrier(dispatch, require_live=False) != barrier:
            raise ProcessControlError("model dispatch barrier changed after fsync")
        return barrier

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
            current_fields = {
                "attempt_id",
                "birth_token",
                "executable",
                "mission_id",
                "model_input_bytes",
                "model_request_sha256",
                "pgid",
                "pid",
                "schema_version",
                "started_at",
            }
            version_two_fields = current_fields - {
                "model_input_bytes",
                "model_request_sha256",
            }
            version_one_fields = version_two_fields - {"birth_token", "schema_version"}
            if set(raw) == version_one_fields:
                raw = {
                    **raw,
                    "birth_token": None,
                    "model_input_bytes": None,
                    "model_request_sha256": None,
                    "schema_version": 1,
                }
            elif set(raw) == version_two_fields:
                raw = {
                    **raw,
                    "model_input_bytes": None,
                    "model_request_sha256": None,
                }
            elif set(raw) != current_fields:
                raise ValueError("unexpected process identity fields")
            owned = OwnedProcess(
                mission_id=raw["mission_id"],
                attempt_id=raw["attempt_id"],
                pid=raw["pid"],
                pgid=raw["pgid"],
                started_at=raw["started_at"],
                birth_token=raw["birth_token"],
                executable=raw["executable"],
                model_request_sha256=raw["model_request_sha256"],
                model_input_bytes=raw["model_input_bytes"],
                schema_version=raw["schema_version"],
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
            or owned.schema_version not in {1, 2, 3}
            or (owned.schema_version == 1) != (owned.birth_token is None)
            or (owned.schema_version == 3)
            != (
                re.fullmatch(r"[0-9a-f]{64}", owned.model_request_sha256 or "")
                is not None
                and type(owned.model_input_bytes) is int
                and 1 <= owned.model_input_bytes <= 2_097_152
            )
            or (
                owned.schema_version in {1, 2}
                and (
                    owned.model_request_sha256 is not None
                    or owned.model_input_bytes is not None
                )
            )
            or not isinstance(owned.executable, str)
            or not owned.executable
            or len(owned.executable) > 1_024
            or any(character in owned.executable for character in "\0\n\r")
        ):
            raise ProcessControlError("owned process record is invalid")
        if path != self._owned_path(owned):
            raise ProcessControlError("owned process record path does not match")
        return owned

    @staticmethod
    def _live_identity(owned: OwnedProcess) -> bool:
        if owned.birth_token is None:
            try:
                _, _, state, _ = _process_identity(owned.pid)
            except ProcessControlError:
                try:
                    os.kill(owned.pid, 0)
                except ProcessLookupError:
                    return False
                raise
            if state.startswith("Z"):
                return False
            raise ProcessControlError(
                "legacy process identity cannot be safely signalled"
            )
        try:
            current = _owned_process_identity(owned.pid)
        except ProcessControlError:
            try:
                os.kill(owned.pid, 0)
            except ProcessLookupError:
                return False
            raise
        pgid, started_at, state, executable, birth_token = current
        if not birth_token:
            raise ProcessControlError("owned process birth token is unavailable")
        if state.startswith("Z"):
            return False
        if birth_token != owned.birth_token:
            return False
        if (pgid, started_at) != (owned.pgid, owned.started_at):
            raise ProcessControlError("owned process identity changed")
        if not _matches_live_image(owned.pid, owned.executable, executable):
            raise ProcessControlError("owned process identity changed")
        return True

    def _wait_for_exit_after_signal(
        self, owned: OwnedProcess, *, timeout: float, poll_seconds: float = 0.05
    ) -> bool:
        """Wait for a previously signalled identity to become verifiably absent."""

        deadline = time.monotonic() + timeout
        while True:
            unavailable = None
            try:
                if not self._live_identity(owned):
                    return True
            except ProcessControlError as error:
                if str(error) != "owned process birth token is unavailable":
                    raise
                unavailable = error
            if time.monotonic() >= deadline:
                if unavailable is not None:
                    raise unavailable
                return False
            time.sleep(poll_seconds)

    def has_record(self, attempt_id: str, *, model: bool | None = None) -> bool:
        """True while a durable record for ``attempt_id`` exists on disk."""

        if model is not None:
            return self._path(attempt_id, model=model).exists()
        return any(
            self._path(attempt_id, model=model).exists() for model in (False, True)
        )

    def live_legacy_record_blocks_model_spawn(self, dispatch: Dispatch) -> bool:
        """Fail closed on a pre-namespace child that may be a model call."""

        if (
            self._path(dispatch.attempt_id, model=True).exists()
            or self._barrier_path(dispatch.attempt_id).exists()
        ):
            return False
        owned = self.owned_process(dispatch, require_live=False)
        return owned is not None and self._live_identity(owned)

    def validate(self, dispatch: Dispatch) -> OwnedProcess:
        owned = self.owned_process(dispatch)
        assert owned is not None
        return owned

    def owned_process(
        self,
        dispatch: Dispatch,
        *,
        require_live: bool = True,
        model: bool = False,
    ) -> OwnedProcess | None:
        path = (
            self._model_path(dispatch.attempt_id)
            if model
            else self._path(dispatch.attempt_id)
        )
        try:
            owned = self._read(path)
        except ProcessControlError:
            if not path.exists():
                return None
            raise
        if (
            owned.mission_id != dispatch.mission_id
            or owned.attempt_id != dispatch.attempt_id
        ):
            raise ProcessControlError("owned process record does not match dispatch")
        if require_live and not self._live_identity(owned):
            raise ProcessControlError("owned process is no longer running")
        return owned

    def records_for_mission(self, mission_id: str) -> tuple[OwnedProcess, ...]:
        records: list[OwnedProcess] = []
        for index, path in enumerate(sorted(self.directory.iterdir())):
            if index >= 4_096:
                raise ProcessControlError("process registry exceeds its safe limit")
            stem, suffix = path.name.rsplit(".", 1) if "." in path.name else ("", "")
            if stem.endswith(".model"):
                stem = stem[: -len(".model")]
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
        prepared = []
        for dispatch in dispatches:
            for model in (False, True):
                owned = self.owned_process(dispatch, require_live=False, model=model)
                if owned is not None:
                    prepared.append(owned)
        return tuple(prepared)

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

    def signal(
        self, dispatch: Dispatch, requested: int, *, model: bool = False
    ) -> bool:
        self._validate_signal(requested)
        owned = self.owned_process(dispatch, model=model)
        if owned is None:
            raise ProcessControlError("owned process record is unavailable")
        return self._kill_group(owned, requested)

    @staticmethod
    def _kill_group(owned: OwnedProcess, requested: int) -> bool:
        try:
            os.killpg(owned.pgid, requested)
        except ProcessLookupError:
            return False
        return True

    def signal_prepared(self, owned: OwnedProcess, requested: int) -> bool:
        """Signal an identity captured before a mission-state transition."""

        self._validate_signal(requested)
        if self._live_identity(owned):
            return self._kill_group(owned, requested)
        return False

    def terminate_owned(
        self,
        owned: OwnedProcess,
        *,
        timeout: float = 2,
        retain_record: bool = False,
    ) -> int | None:
        """Terminate a prevalidated group and confirm its exact identity is absent."""

        if timeout <= 0:
            raise ProcessControlError("process termination timeout must be positive")
        path = self._owned_path(owned)
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
                    return None
            raise
        signalled = self.signal_prepared(owned, signal.SIGTERM)
        sent = signal.SIGTERM if signalled else None
        exited = not signalled or self._wait_for_exit_after_signal(
            owned, timeout=timeout
        )
        if not exited:
            if self.signal_prepared(owned, signal.SIGKILL):
                sent = signal.SIGKILL
                exited = self._wait_for_exit_after_signal(owned, timeout=timeout)
            else:
                exited = True
        if not exited:
            raise ProcessControlError("owned process could not be terminated")
        descendant_signal = self.terminate_descendants(owned, timeout=timeout)
        if descendant_signal is not None:
            sent = descendant_signal
        if retain_record:
            return sent
        try:
            recorded = self._read(path)
        except ProcessControlError as error:
            try:
                path.lstat()
            except FileNotFoundError:
                return sent
            raise error
        if recorded != owned:
            raise ProcessControlError("owned process record changed during termination")
        if path == self._model_path(owned.attempt_id):
            self._barrier_path(owned.attempt_id).unlink(missing_ok=True)
        path.unlink()
        directory_descriptor = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return sent

    def terminate_descendants(
        self, owned: OwnedProcess, *, timeout: float = 2
    ) -> int | None:
        """Verify an owned group is empty without signalling an unanchored PGID."""

        if timeout <= 0 or self._read(self._owned_path(owned)) != owned:
            raise ProcessControlError(
                "owned process record changed before group cleanup"
            )
        if self._live_identity(owned):
            raise ProcessControlError("owned process leader is still running")
        try:
            current = _owned_process_identity(owned.pid)
        except ProcessControlError:
            try:
                os.kill(owned.pid, 0)
            except ProcessLookupError:
                current = None
            else:
                raise ProcessControlError(
                    "owned process leader identity is unavailable"
                ) from None
        if current is not None:
            pgid, started_at, state, _executable, birth_token = current
            if owned.birth_token is not None and not birth_token:
                raise ProcessControlError(
                    "owned process leader birth token is unavailable"
                )
            weak_exact_zombie = (
                owned.birth_token is None
                and not birth_token
                and state.startswith("Z")
                and (pgid, started_at) == (owned.pgid, owned.started_at)
            )
            if birth_token != owned.birth_token and not weak_exact_zombie:
                # The numeric PID was reused after this leader exited. Its
                # birth mismatch proves the old process group was empty.
                return None
            if not state.startswith("Z") or (pgid, started_at) != (
                owned.pgid,
                owned.started_at,
            ):
                raise ProcessControlError("owned process leader identity changed")

        exact_zombie = current is not None

        def group_exists() -> bool:
            if exact_zombie:
                try:
                    result = subprocess.run(
                        ("/bin/ps", "-axo", "pid=,pgid=,state="),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=2,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as error:
                    raise ProcessControlError(
                        "owned descendant group status is unavailable"
                    ) from error
                if result.returncode or len(result.stdout) > 2_097_152:
                    raise ProcessControlError(
                        "owned descendant group status is unavailable"
                    )
                for line in result.stdout.splitlines():
                    fields = line.split()
                    if len(fields) != 3:
                        continue
                    try:
                        pid, pgid = int(fields[0]), int(fields[1])
                    except ValueError:
                        continue
                    if (
                        pgid == owned.pgid
                        and pid != owned.pid
                        and not fields[2].startswith("Z")
                    ):
                        return True
                return False
            try:
                os.killpg(owned.pgid, 0)
            except ProcessLookupError:
                return False
            except OSError as error:
                raise ProcessControlError(
                    "owned descendant group status is unavailable"
                ) from error
            return True

        if not group_exists():
            return None
        if current is None:
            raise ProcessControlError(
                "owned process leader cannot anchor descendant cleanup"
            )
        if owned.birth_token is None:
            raise ProcessControlError(
                "legacy descendant group cannot be safely signalled"
            )
        raise ProcessControlError(
            "owned descendant group cannot be safely signalled after leader exit"
        )

    def recover_model_dispatch(
        self, dispatch: Dispatch, *, timeout: float = 2
    ) -> tuple[ModelDispatchBarrier, int | None] | None:
        """Stop an exact barrier-acknowledged orphan, retaining its crash proof."""

        barrier = self.confirm_model_dispatch_barrier(dispatch)
        if barrier is None:
            return None
        owned = self._read(self._model_path(dispatch.attempt_id))
        sent = self.terminate_owned(owned, timeout=timeout, retain_record=True)
        return barrier, sent


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
        max_output_bytes: int = MAX_TEST_OUTPUT_BYTES,
    ) -> None:
        self.registry = registry
        self.dispatch = dispatch
        self.status = status
        self.heartbeat = heartbeat
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_seconds = poll_seconds
        if not 1 <= max_output_bytes <= MAX_TEST_OUTPUT_BYTES:
            raise ProcessControlError("controlled process output cap is invalid")
        self.max_output_bytes = max_output_bytes

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
        # The shell stays blocked until the exact PID/PGID record is durable.
        # If this controller dies anywhere before the release write, pipe EOF
        # makes the inert child exit instead of orphaning an unrecorded group.
        process = subprocess.Popen(
            (
                "/bin/sh",
                "-c",
                _CONTROLLED_LAUNCH_SCRIPT,
                "graphene-controlled",
                *arguments,
            ),
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            start_new_session=True,
        )
        assert (
            process.stdin is not None
            and process.stdout is not None
            and process.stderr is not None
        )
        selector = selectors.DefaultSelector()
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        captured = {process.stdout: bytearray(), process.stderr: bytearray()}
        captured_bytes = 0
        termination: str | None = None
        force_deadline: float | None = None
        drain_deadline: float | None = None
        stopped = False
        registered = False
        owned: OwnedProcess | None = None
        descendants_reconciled = False
        elapsed = 0.0
        last = time.monotonic()
        last_heartbeat = last

        def close_stdin() -> None:
            try:
                process.stdin.close()
            except OSError:
                pass

        def reconcile_descendants() -> None:
            nonlocal descendants_reconciled
            assert owned is not None
            try:
                self.registry.terminate_descendants(owned)
            except ProcessControlError:
                if self.registry.has_record(self.dispatch.attempt_id, model=False):
                    raise
            descendants_reconciled = True

        try:
            try:
                self.registry.record(
                    self.dispatch,
                    process,
                    "/bin/sh",
                )
                registered = True
                owned = self.registry.owned_process(self.dispatch, require_live=False)
                if owned is None:
                    raise ProcessControlError(
                        "owned process record is unavailable after launch"
                    )
            except Exception:
                close_stdin()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
                raise
            try:
                process.stdin.write(b"graphene-go\n")
                process.stdin.flush()
            except OSError as error:
                close_stdin()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    raise ProcessControlError(
                        "controlled process release failed"
                    ) from error
            else:
                close_stdin()
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
                if state == MissionStatus.CANCELLED and termination is None:
                    self.registry.signal(self.dispatch, signal.SIGTERM)
                    termination = "cancelled"
                    force_deadline = now + 2
                if (
                    termination is None
                    and state == MissionStatus.PAUSED
                    and not stopped
                ):
                    self.registry.signal(self.dispatch, signal.SIGSTOP)
                    stopped = True
                elif termination is None and state == MissionStatus.RUNNING and stopped:
                    self.registry.signal(self.dispatch, signal.SIGCONT)
                    stopped = False
                if termination is None and elapsed >= timeout:
                    if stopped:
                        self.registry.signal(self.dispatch, signal.SIGCONT)
                        stopped = False
                    self.registry.signal(self.dispatch, signal.SIGKILL)
                    termination = "timeout"
                    drain_deadline = now + 2
                if (
                    termination == "cancelled"
                    and process.poll() is None
                    and force_deadline is not None
                    and now >= force_deadline
                ):
                    self.registry.signal(self.dispatch, signal.SIGKILL)
                    drain_deadline = now + 2
                    force_deadline = None

                for key, _ in selector.select(self.poll_seconds):
                    stream = key.fileobj
                    try:
                        chunk = os.read(stream.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        continue
                    remaining = self.max_output_bytes + 1 - captured_bytes
                    if remaining > 0:
                        kept = chunk[:remaining]
                        captured[stream].extend(kept)
                        captured_bytes += len(kept)
                    if captured_bytes > self.max_output_bytes and termination is None:
                        self.registry.signal(self.dispatch, signal.SIGKILL)
                        termination = "output_limit"
                        drain_deadline = time.monotonic() + 2

                if process.poll() is not None:
                    if not descendants_reconciled:
                        reconcile_descendants()
                    if drain_deadline is None:
                        drain_deadline = time.monotonic() + 2
                if drain_deadline is not None and time.monotonic() >= drain_deadline:
                    for key in tuple(selector.get_map().values()):
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    if process.poll() is None:
                        raise ProcessControlError(
                            "controlled process did not exit after termination"
                        )
                if process.poll() is None or selector.get_map():
                    continue

                stdout = captured[process.stdout].decode(errors="replace")
                stderr = captured[process.stderr].decode(errors="replace")
                if termination == "cancelled":
                    raise ProcessCancelled("scripted attempt was cancelled")
                if termination == "timeout":
                    raise subprocess.TimeoutExpired(arguments, timeout, stdout, stderr)
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
                if registered and not descendants_reconciled:
                    reconcile_descendants()
                if registered:
                    self.registry.remove(self.dispatch)
            except Exception as error:
                cleanup_error = error
            selector.close()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            if process.stdin is not None:
                close_stdin()
            if cleanup_error is not None and not original_error:
                raise cleanup_error


__all__ = [
    "ControlledProcessRunner",
    "ModelDispatchBarrier",
    "OwnedProcess",
    "OwnedProcessRegistry",
    "ProcessCancelled",
    "ProcessControlError",
]
