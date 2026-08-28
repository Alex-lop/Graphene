from __future__ import annotations

import argparse
import os
import signal
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..core_models import (
    BoundedText,
    FrozenModel,
    GitSha,
    Identifier,
    IdempotencyKey,
    Sha256,
)
from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex

_REQUEST = "supervisor-request.json"
_PROCESS = "supervisor-process.json"
_STATE = "supervisor-state.json"
_LOG = "supervisor.log"
_PLANNER = "planner"
_MAX_PRIVATE_BYTES = 1_048_576
_RUNTIME_ENVIRONMENT_KEYS = frozenset(
    {
        "ADK_TELEMETRY_IGNORE_RUN_CONFIG",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GRAPHENE_CHECK_EXECUTOR",
        "GRAPHENE_COORDINATOR_AUDIENCE",
        "GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS",
        "GRAPHENE_COORDINATOR_URL",
        "GRAPHENE_FIRESTORE_DATABASE",
        "GRAPHENE_FIRESTORE_NAMESPACE",
        "GRAPHENE_STATE_DIR",
        "HOME",
        "HTTPS_PROXY",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "NO_COLOR",
        "NO_PROXY",
        "PATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "TMPDIR",
        "USER",
        "VIRTUAL_ENV",
    }
)


class SupervisorError(RuntimeError):
    pass


class SupervisorRequest(FrozenModel):
    schema_version: Literal[1, 2] = 2
    mission_id: Identifier
    command_id: IdempotencyKey
    repository_path: str = Field(min_length=1, max_length=4_096)
    goal: BoundedText
    success_criteria: tuple[BoundedText, ...] = Field(min_length=1, max_length=32)
    driver: Literal["scripted-local", "gemini-adk"]
    max_workers: int = Field(ge=1, le=5)
    base_sha: GitSha
    policy_revision: int = Field(ge=1)
    policy_sha256: Sha256
    requested_mode: Literal["policy_pre_authorized", "review_required"]
    finalization_mode: Literal["auto_finalize_isolated", "review_required"]
    check_executor: Literal["docker", "host-sandbox"] | None = None
    accepted_at: datetime
    request_sha256: Sha256

    @model_validator(mode="after")
    def request_is_bound(self) -> SupervisorRequest:
        if not Path(self.repository_path).is_absolute():
            raise ValueError("supervisor repository path must be absolute")
        if self.success_criteria != tuple(sorted(set(self.success_criteria))):
            raise ValueError("supervisor criteria must be sorted and unique")
        if (
            self.requested_mode == "review_required"
            and self.finalization_mode != "review_required"
        ):
            raise ValueError(
                "review-required missions require a reviewed final decision"
            )
        if (self.schema_version == 1) != (self.check_executor is None):
            raise ValueError("supervisor check executor binding is invalid")
        payload = self.model_dump(mode="json", exclude={"request_sha256"})
        if self.schema_version == 1:
            payload.pop("check_executor")
        expected = canonical_json_sha256(payload)
        if self.request_sha256 != expected:
            raise ValueError("supervisor request digest does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> SupervisorRequest:
        payload = cls.model_construct(
            schema_version=2, **values, request_sha256="0" * 64
        ).model_dump(mode="json", exclude={"request_sha256"})
        return cls.model_validate(
            {**payload, "request_sha256": canonical_json_sha256(payload)}
        )


class SupervisorProcess(FrozenModel):
    schema_version: Literal[2] = 2
    mission_id: Identifier
    request_sha256: Sha256
    generation: int = Field(ge=1)
    pid: int = Field(gt=1)
    pgid: int = Field(gt=1)
    started_at: str = Field(min_length=1, max_length=128)
    birth_token: str = Field(min_length=1, max_length=256, pattern=r"^[^\x00\r\n]+$")
    executable: str = Field(min_length=1, max_length=1_024)

    @model_validator(mode="after")
    def process_owns_group(self) -> SupervisorProcess:
        if self.pid != self.pgid:
            raise ValueError("supervisor must own its process group")
        return self


class _LegacySupervisorProcess(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    request_sha256: Sha256
    generation: int = Field(ge=1)
    pid: int = Field(gt=1)
    pgid: int = Field(gt=1)
    started_at: str = Field(min_length=1, max_length=128)
    executable: str = Field(min_length=1, max_length=1_024)

    @model_validator(mode="after")
    def process_owns_group(self) -> _LegacySupervisorProcess:
        if self.pid != self.pgid:
            raise ValueError("supervisor must own its process group")
        return self


class SupervisorState(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    request_sha256: Sha256
    phase: Literal[
        "accepted",
        "planning",
        "review_required",
        "running",
        "finalizing",
        "completed",
        "failed",
    ]
    generation: int = Field(ge=0)
    updated_at: datetime
    error_code: Identifier | None = None

    @model_validator(mode="after")
    def error_matches_phase(self) -> SupervisorState:
        if (self.phase == "failed") != (self.error_code is not None):
            raise ValueError("only failed supervisor state carries an error code")
        return self


def _private_file(path: Path) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise SupervisorError("supervisor file is unsafe")


def _read(path: Path, model):
    try:
        _private_file(path)
        raw = path.read_bytes()
        if not raw or len(raw) > _MAX_PRIVATE_BYTES:
            raise ValueError
        value = model.model_validate_json(raw)
        payload = value.model_dump(mode="json")
        if isinstance(value, SupervisorRequest) and value.schema_version == 1:
            payload.pop("check_executor")
        if canonical_json_bytes(payload) + b"\n" != raw:
            raise ValueError
        return value
    except (OSError, ValueError) as error:
        raise SupervisorError("supervisor file is invalid") from error


def _write(path: Path, value: FrozenModel, *, create_only: bool = False) -> None:
    directory = path.parent
    if directory.is_symlink() or not directory.is_dir():
        raise SupervisorError("supervisor runtime is unsafe")
    content = canonical_json_bytes(value.model_dump(mode="json")) + b"\n"
    temporary = directory / f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if create_only:
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                existing = _read(path, type(value))
                if existing != value:
                    raise SupervisorError(
                        "supervisor command is already bound to another request"
                    )
        else:
            if path.is_symlink():
                raise SupervisorError("supervisor file is unsafe")
            os.replace(temporary, path)
        directory_descriptor = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _read_process(
    path: Path, request: SupervisorRequest
) -> SupervisorProcess | _LegacySupervisorProcess:
    try:
        process = _read(path, SupervisorProcess)
    except SupervisorError as strong_error:
        try:
            process = _read(path, _LegacySupervisorProcess)
        except SupervisorError:
            raise strong_error
        if (
            process.mission_id != request.mission_id
            or process.request_sha256 != request.request_sha256
        ):
            raise SupervisorError("supervisor process binding changed")
        # Legacy identity has no strong birth token. Keep it only as a weak
        # liveness sentinel: never signal it or treat it as exact ownership,
        # but do not overlap it with a replacement while that PID still exists.
        return process
    if (
        process.mission_id != request.mission_id
        or process.request_sha256 != request.request_sha256
    ):
        raise SupervisorError("supervisor process binding changed")
    return process


def _state(
    runtime: Path,
    request: SupervisorRequest,
    phase: str,
    generation: int,
    *,
    error_code: str | None = None,
) -> SupervisorState:
    try:
        import fcntl
    except ImportError as error:
        raise SupervisorError("supervisor state locking is unavailable") from error

    value = SupervisorState(
        mission_id=request.mission_id,
        request_sha256=request.request_sha256,
        phase=phase,
        generation=generation,
        updated_at=datetime.now(UTC),
        error_code=error_code,
    )
    lock_path = runtime / "supervisor-state.lock"
    try:
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as error:
        raise SupervisorError("supervisor state lock is unavailable") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise SupervisorError("supervisor state lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        state_path = runtime / _STATE
        if state_path.exists() or state_path.is_symlink():
            current = _read(state_path, SupervisorState)
            if (
                current.mission_id != request.mission_id
                or current.request_sha256 != request.request_sha256
            ):
                raise SupervisorError("supervisor state binding changed")
            if current.generation > generation:
                raise SupervisorError("stale supervisor generation cannot write state")
        _write(state_path, value)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return value


def _live(record: SupervisorProcess | _LegacySupervisorProcess) -> bool:
    if isinstance(record, _LegacySupervisorProcess):
        try:
            os.kill(record.pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True

    from .process_control import (
        ProcessControlError,
        _matches_live_image,
        _owned_process_identity,
    )

    try:
        pgid, started_at, process_state, executable, birth_token = (
            _owned_process_identity(record.pid)
        )
    except ProcessControlError:
        try:
            os.kill(record.pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True
    if process_state.startswith("Z"):
        return False
    if (pgid, started_at, birth_token) != (
        record.pgid,
        record.started_at,
        record.birth_token,
    ):
        return False
    return _matches_live_image(record.pid, record.executable, executable)


def _runtime_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in _RUNTIME_ENVIRONMENT_KEYS
    }
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def _planner_directory(runtime: Path, attempt_number: int | None = None) -> Path:
    root = runtime / _PLANNER
    for directory in (
        (root,)
        if attempt_number is None
        else (root, root / f"attempt-{attempt_number}")
    ):
        directory.mkdir(mode=0o700, exist_ok=True)
        metadata = directory.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise SupervisorError("planner runtime is unsafe")
    return directory


def _planner_frames(directory: Path, child_request):
    from .planner_child import read_planner_frames

    try:
        frames = read_planner_frames(directory / "planner.frames")
    except ValueError as error:
        raise SupervisorError("planner child journal is invalid") from error
    expected = (
        child_request.mission_id,
        child_request.supervisor_request_sha256,
        child_request.request_sha256(),
        child_request.attempt_number,
    )
    if any(
        (
            frame.mission_id,
            frame.supervisor_request_sha256,
            frame.child_request_sha256,
            frame.attempt_number,
        )
        != expected
        for frame in frames
    ):
        raise SupervisorError("planner child journal binding changed")
    kinds = tuple(frame.type for frame in frames)
    if kinds not in {
        (),
        ("ready",),
        ("ready", "error"),
        ("ready", "provider_dispatched"),
        ("ready", "provider_dispatched", "error"),
        ("ready", "provider_dispatched", "result"),
    }:
        raise SupervisorError("planner child journal sequence is invalid")
    if frames and frames[-1].type == "result":
        dispatch, result = frames[-2:]
        assert result.proposal is not None
        if (
            dispatch.sdk_invocation_id != result.sdk_invocation_id
            or result.proposal.receipt.invocation_id != result.sdk_invocation_id
            or result.proposal.plan.mission_id != child_request.mission_id
        ):
            raise SupervisorError("planner child result identity changed")
    return frames


def _planner_outcome(directory: Path, child_request):
    from .planner_child import PlannerAttemptOutcome

    path = directory / "planner-outcome.json"
    if not path.exists() and not path.is_symlink():
        return None
    outcome = _read(path, PlannerAttemptOutcome)
    if (
        outcome.mission_id != child_request.mission_id
        or outcome.supervisor_request_sha256 != child_request.supervisor_request_sha256
        or outcome.child_request_sha256 != child_request.request_sha256()
        or outcome.attempt_number != child_request.attempt_number
    ):
        raise SupervisorError("planner attempt outcome binding changed")
    return outcome


def _record_planner_outcome(directory: Path, child_request, kind: str, dispatch=None):
    from .planner_child import PlannerAttemptOutcome

    outcome = PlannerAttemptOutcome(
        mission_id=child_request.mission_id,
        supervisor_request_sha256=child_request.supervisor_request_sha256,
        child_request_sha256=child_request.request_sha256(),
        attempt_number=child_request.attempt_number,
        outcome=kind,
        sdk_invocation_id=(None if dispatch is None else dispatch.sdk_invocation_id),
        dispatched_at=(None if dispatch is None else dispatch.dispatched_at),
        recorded_at=datetime.now(UTC),
    )
    _write(directory / "planner-outcome.json", outcome, create_only=True)
    return outcome


def _planner_child_live(process) -> bool:
    return _live(process)


def _authorize_planner_child(directory: Path, child_request) -> None:
    from .planner_child import PlannerGo

    _write(
        directory / "planner-go.json",
        PlannerGo(child_request_sha256=child_request.request_sha256()),
        create_only=True,
    )


def _spawn_planner_child(directory: Path, child_request) -> None:
    from .planner_child import planner_frame_bytes

    executable_path = Path(os.path.abspath(sys.executable))
    if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
        raise SupervisorError("planner child executable is unavailable")
    process = subprocess.Popen(
        (
            str(executable_path),
            "-I",
            "-m",
            "graphene.orchestration.planner_child",
        ),
        cwd=directory,
        env=_runtime_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    assert process.stdin is not None
    try:
        process.stdin.write(planner_frame_bytes(child_request))
        process.stdin.flush()
    except BrokenPipeError:
        pass
    finally:
        process.stdin.close()


def _stop_planner_child(process) -> None:
    from .process_control import (
        ProcessControlError,
        _matches_live_image,
        _owned_process_identity,
    )

    try:
        current = _owned_process_identity(process.pid)
    except ProcessControlError:
        try:
            os.kill(process.pid, 0)
        except ProcessLookupError:
            return
        raise SupervisorError("planner child identity is unavailable") from None
    pgid, started_at, state, executable, birth_token = current
    if state.startswith("Z"):
        return
    if (pgid, started_at, birth_token) != (
        process.pgid,
        process.started_at,
        process.birth_token,
    ) or not _matches_live_image(process.pid, process.executable, executable):
        raise SupervisorError("planner child identity changed")
    os.killpg(process.pgid, signal.SIGKILL)


def _await_planner_attempt(directory: Path, child_request):
    deadline = time.monotonic() + child_request.planning.timeout_seconds + 15
    startup_deadline = time.monotonic() + 5
    while True:
        frames = _planner_frames(directory, child_request)
        outcome = _planner_outcome(directory, child_request)
        if outcome is not None:
            if outcome.outcome == "completed":
                result = next(
                    (frame for frame in frames if frame.type == "result"), None
                )
                if result is None or result.proposal is None:
                    raise SupervisorError("completed planner result is unavailable")
                return result.proposal
            if outcome.outcome == "child_error":
                return None
            return None
        terminal = frames[-1] if frames else None
        dispatch = next(
            (frame for frame in frames if frame.type == "provider_dispatched"), None
        )
        if terminal is not None and terminal.type == "result":
            _record_planner_outcome(directory, child_request, "completed", dispatch)
            assert terminal.proposal is not None
            return terminal.proposal
        if terminal is not None and terminal.type == "error":
            _record_planner_outcome(directory, child_request, "child_error", dispatch)
            return None
        process = frames[0].process if frames else None
        if process is not None and _planner_child_live(process):
            _authorize_planner_child(directory, child_request)
        elif process is not None:
            if _planner_frames(directory, child_request) != frames:
                continue
            _record_planner_outcome(
                directory,
                child_request,
                (
                    "provider_outcome_unknown"
                    if dispatch is not None
                    else "pre_dispatch_interrupted"
                ),
                dispatch,
            )
            return None
        elif time.monotonic() >= startup_deadline:
            _record_planner_outcome(
                directory,
                child_request,
                "pre_dispatch_interrupted",
                dispatch,
            )
            return None
        if time.monotonic() >= deadline:
            if process is not None and _planner_child_live(process):
                _stop_planner_child(process)
                continue
            if (
                process is not None
                and _planner_frames(directory, child_request) != frames
            ):
                continue
            _record_planner_outcome(
                directory,
                child_request,
                (
                    "provider_outcome_unknown"
                    if dispatch is not None
                    else "pre_dispatch_interrupted"
                ),
                dispatch,
            )
            return None
        time.sleep(0.02)


def _supervised_gemini_proposal(
    request: SupervisorRequest, policy, repository: Path, runtime: Path
):
    from ..cli.mission import _planning_repository_context
    from .adk_planner import PlanningRequest
    from .planner_child import PlannerChildRequest

    manifest, excerpts = _planning_repository_context(repository, policy)
    for attempt_number in (1, 2):
        child_request = PlannerChildRequest(
            mission_id=request.mission_id,
            supervisor_request_sha256=request.request_sha256,
            attempt_number=attempt_number,
            policy=policy,
            planning=PlanningRequest(
                mission_id=request.mission_id,
                revision=1,
                goal=request.goal,
                success_criteria=request.success_criteria,
                repository_manifest=manifest,
                repository_excerpts=excerpts,
            ),
        )
        directory = _planner_directory(runtime, attempt_number)
        marker = directory / "planner-request.json"
        if marker.exists() or marker.is_symlink():
            if _read(marker, PlannerChildRequest) != child_request:
                raise SupervisorError("planner child request binding changed")
        else:
            _write(marker, child_request, create_only=True)
            _spawn_planner_child(directory, child_request)
        proposal = _await_planner_attempt(directory, child_request)
        if proposal is not None:
            return proposal
    raise SupervisorError("planner attempts exhausted")


def _spawn(
    runtime: Path, request: SupervisorRequest, generation: int
) -> SupervisorProcess:
    # Keep the virtual-environment launcher path: resolving its symlink makes
    # Python lose pyvenv.cfg under ``-I`` and therefore lose the installed package.
    executable_path = Path(os.path.abspath(sys.executable))
    if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
        raise SupervisorError("supervisor executable is unavailable")
    executable = str(executable_path)
    log_path = runtime / _LOG
    if log_path.is_symlink():
        raise SupervisorError("supervisor log is unsafe")
    descriptor = os.open(
        log_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    _state(runtime, request, "accepted", generation)
    os.close(descriptor)
    process = subprocess.Popen(
        (
            executable,
            "-I",
            "-m",
            "graphene.orchestration.supervisor",
            "--run",
            request.mission_id,
            "--request-sha256",
            request.request_sha256,
            "--generation",
            str(generation),
        ),
        cwd=runtime,
        env=_runtime_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    assert process.stdin is not None
    try:
        from .process_control import ProcessControlError, _owned_process_identity

        deadline = time.monotonic() + 1
        while True:
            try:
                pgid, started_at, process_state, observed, birth_token = (
                    _owned_process_identity(process.pid)
                )
                if not process_state.startswith("Z"):
                    break
            except ProcessControlError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise SupervisorError("supervisor process did not start") from None
            time.sleep(0.01)
        if pgid != process.pid:
            os.kill(process.pid, signal.SIGKILL)
            raise SupervisorError("supervisor did not establish an owned process group")
        if observed.startswith("(") and observed.endswith(")"):
            observed = executable
        record = SupervisorProcess(
            mission_id=request.mission_id,
            request_sha256=request.request_sha256,
            generation=generation,
            pid=process.pid,
            pgid=pgid,
            started_at=started_at,
            birth_token=birth_token,
            executable=observed,
        )
        _write(runtime / _PROCESS, record)
        return record
    finally:
        process.stdin.close()


def _request_path(runtime: Path) -> Path:
    return runtime / _REQUEST


def _start_binding(request: SupervisorRequest) -> dict[str, object]:
    repository = request.repository_path
    binding = {
        "auto_approve": (
            request.driver == "scripted-local"
            and request.requested_mode == "policy_pre_authorized"
        ),
        "authorization_mode": request.requested_mode,
        "command_id": request.command_id,
        "demo_injected_check_fault": False,
        "driver": request.driver,
        "finalization_mode": request.finalization_mode,
        "goal_sha256": sha256_hex(request.goal.encode()),
        "max_workers": request.max_workers,
        "policy_base_sha": request.base_sha,
        "policy_revision": request.policy_revision,
        "policy_sha256": request.policy_sha256,
        "repository_head": request.base_sha,
        "repository_path": repository,
        "repository_path_sha256": sha256_hex(repository.encode()),
        "success_criteria_sha256": sha256_hex(
            canonical_json_bytes(request.success_criteria)
        ),
    }
    if request.check_executor is not None:
        binding["check_executor"] = request.check_executor
    return binding


def _authoritative_mission_status(mission_id: str):
    from ..cli.mission import _store_for_mission
    from .sqlite_mission_store import MissionNotFound

    store = _store_for_mission(mission_id)
    try:
        try:
            return store.snapshot(mission_id).mission.status
        except MissionNotFound:
            return None
    finally:
        store.close()


def _reconcile_completed(
    runtime: Path,
    request: SupervisorRequest,
    state: SupervisorState,
    status=None,
) -> SupervisorState:
    from .mission_models import MissionStatus

    if state.phase == "completed":
        return state
    status = status or _authoritative_mission_status(request.mission_id)
    if status == MissionStatus.COMPLETED:
        return _state(runtime, request, "completed", state.generation)
    return state


def _completed_view(
    request: SupervisorRequest,
    state: SupervisorState,
) -> SupervisorState:
    """Report authoritative completion without mutating a read-only request."""

    from .mission_models import MissionStatus

    if state.phase != "completed" and (
        _authoritative_mission_status(request.mission_id) == MissionStatus.COMPLETED
    ):
        return state.model_copy(update={"phase": "completed", "error_code": None})
    return state


def accept_goal(
    *,
    repository: Path,
    goal: str,
    success_criteria: tuple[str, ...],
    driver: str,
    max_workers: int,
    command_id: str,
    requested_mode: str,
    finalization_mode: str,
) -> tuple[SupervisorRequest, SupervisorState]:
    """Durably accept and signal one mission without awaiting model work."""

    from argparse import Namespace

    from ..cli.mission import (
        _bind_start_request,
        _mission_runtime,
        _select_check_executor,
        _start_identity,
        _start_lock,
    )

    criteria = tuple(sorted(set(success_criteria)))
    if driver == "scripted-local":
        from .scripted import load_scenario

        scripted_criteria = load_scenario().success_criteria
        if any(item not in scripted_criteria for item in criteria):
            raise SupervisorError(
                "scripted-local only accepts its fixed fixture criteria"
            )
        criteria = scripted_criteria
    arguments = Namespace(
        repo=repository,
        goal=goal,
        success_criteria=list(criteria),
        driver=driver,
        max_workers=max_workers,
        auto_approve=(
            driver == "scripted-local" and requested_mode == "policy_pre_authorized"
        ),
        command_id=command_id,
        open_viewer=False,
        json_mode=True,
        demo_injected_check_fault=False,
        authorization_mode=requested_mode,
        finalization_mode=finalization_mode,
    )
    actual_command, mission_id, resolved, head, policy, binding = _start_identity(
        arguments
    )
    request_values = {
        "mission_id": mission_id,
        "command_id": actual_command,
        "repository_path": str(resolved),
        "goal": goal,
        "success_criteria": criteria,
        "driver": driver,
        "max_workers": max_workers,
        "base_sha": head,
        "policy_revision": policy.revision,
        "policy_sha256": canonical_json_sha256(policy.model_dump(mode="json")),
        "requested_mode": requested_mode,
        "finalization_mode": finalization_mode,
    }
    runtime = _mission_runtime(mission_id)
    with _start_lock(runtime):
        request_path = _request_path(runtime)
        if request_path.exists() or request_path.is_symlink():
            committed = _read(request_path, SupervisorRequest)
            committed_semantics = committed.model_dump(
                mode="json",
                exclude={
                    "accepted_at",
                    "check_executor",
                    "request_sha256",
                    "schema_version",
                },
            )
            expected_semantics = {
                **request_values,
                "success_criteria": list(criteria),
            }
            if committed_semantics != expected_semantics:
                raise SupervisorError(
                    "supervisor command is already bound to another request"
                )
            request = committed
        else:
            request = SupervisorRequest.create(
                **request_values,
                check_executor=_select_check_executor(),
                accepted_at=datetime.now(UTC),
            )
            _write(request_path, request, create_only=True)
        durable_binding = _start_binding(request)
        expected_binding = dict(binding)
        if request.check_executor is not None:
            expected_binding["check_executor"] = request.check_executor
        if expected_binding != durable_binding:
            raise SupervisorError("supervisor request binding changed")
        _bind_start_request(runtime, durable_binding)
        state_path = runtime / _STATE
        state = (
            _read(state_path, SupervisorState)
            if state_path.exists() or state_path.is_symlink()
            else _state(runtime, request, "accepted", 0)
        )
        state = _reconcile_completed(runtime, request, state)
        process_path = runtime / _PROCESS
        record = (
            _read_process(process_path, request)
            if process_path.exists() or process_path.is_symlink()
            else None
        )
        live = record is not None and _live(record)
        if state.phase not in {"completed", "failed"} and not live:
            generation = max(state.generation, 0) + 1
            _spawn(runtime, request, generation)
            state = _read(state_path, SupervisorState)
    return request, state


def ensure_supervisor(
    mission_id: str, *, recover_failed: bool = False
) -> SupervisorState:
    from ..cli.mission import _mission_runtime, _start_lock
    from .mission_models import MissionStatus

    runtime = _mission_runtime(mission_id)
    request = _read(_request_path(runtime), SupervisorRequest)
    if request.mission_id != mission_id:
        raise SupervisorError("supervisor request belongs to another mission")
    with _start_lock(runtime):
        state_path = runtime / _STATE
        state = _read(state_path, SupervisorState)
        state = _reconcile_completed(runtime, request, state)
        if state.phase == "completed" or (
            state.phase == "failed" and not recover_failed
        ):
            return state
        process_path = runtime / _PROCESS
        record = (
            _read_process(process_path, request)
            if process_path.exists() or process_path.is_symlink()
            else None
        )
        status = _authoritative_mission_status(mission_id)
        if (
            (state.phase == "failed" and recover_failed)
            or (state.phase == "review_required" and status != MissionStatus.PROPOSED)
            or record is None
            or not _live(record)
        ):
            _spawn(runtime, request, state.generation + 1)
            state = _read(state_path, SupervisorState)
        return state


def supervisor_acceptance(
    mission_id: str,
) -> tuple[SupervisorRequest, SupervisorState]:
    from ..cli.mission import _mission_runtime, _start_lock

    runtime = _mission_runtime(mission_id)
    request = _read(_request_path(runtime), SupervisorRequest)
    with _start_lock(runtime):
        state = _read(runtime / _STATE, SupervisorState)
        if (
            state.mission_id != request.mission_id
            or state.request_sha256 != request.request_sha256
        ):
            raise SupervisorError("supervisor state binding changed")
        return request, _completed_view(request, state)


def supervisor_status(mission_id: str) -> SupervisorState:
    return supervisor_acceptance(mission_id)[1]


def _spawn_cancellation_reconciler(state_root: Path) -> None:
    """Detach slow exact-owner cleanup from the MCP startup/READY path."""

    executable = os.path.abspath(sys.executable)
    if not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise SupervisorError("cancellation reconciler executable is unavailable")
    subprocess.Popen(
        (
            executable,
            "-I",
            "-m",
            "graphene.orchestration.supervisor",
            "--recover-cancellations",
        ),
        cwd=state_root,
        env=_runtime_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def recover_supervisors() -> int:
    from ..cli.mission import (
        _CANCELLATION_REQUEST,
        _bind_start_request,
        _mission_runtime,
        _reconcile_cancellation_request,
        _start_lock,
        _state_root,
    )
    from .mission_models import MissionStatus

    state_root = _state_root()
    pending_cancellation = False
    seen = 0
    for parent in (state_root / "missions", state_root / "scripted"):
        if not parent.exists():
            continue
        for runtime in sorted(parent.iterdir()):
            seen += 1
            if seen > 4_096:
                raise SupervisorError("supervisor runtime count exceeds its safe limit")
            journal = runtime / _CANCELLATION_REQUEST
            if journal.exists() or journal.is_symlink():
                pending_cancellation = True
    if pending_cancellation:
        _spawn_cancellation_reconciler(state_root)
    directory = state_root / "missions"
    if not directory.exists():
        return 0
    recovered = 0
    for index, runtime in enumerate(sorted(directory.iterdir())):
        if index >= 4_096:
            raise SupervisorError("supervisor runtime count exceeds its safe limit")
        try:
            request_path = runtime / _REQUEST
            if not request_path.is_file() or request_path.is_symlink():
                continue
            request = _read(request_path, SupervisorRequest)
            cancellation = runtime / _CANCELLATION_REQUEST
            if cancellation.exists() or cancellation.is_symlink():
                continue
            if runtime != _mission_runtime(request.mission_id):
                raise SupervisorError("supervisor request is in the wrong runtime")
            with _start_lock(runtime):
                _bind_start_request(runtime, _start_binding(request))
                state_path = runtime / _STATE
                state = (
                    _read(state_path, SupervisorState)
                    if state_path.exists() or state_path.is_symlink()
                    else _state(runtime, request, "accepted", 0)
                )
                _reconcile_cancellation_request(request.mission_id)
                _reconcile_terminal_worker_receipts(request.mission_id)
                if state.phase == "completed":
                    continue
                status = _authoritative_mission_status(request.mission_id)
                state = _reconcile_completed(runtime, request, state, status)
                if state.phase == "completed":
                    recovered += 1
                    continue
                process_path = runtime / _PROCESS
                record = (
                    _read_process(process_path, request)
                    if process_path.exists() or process_path.is_symlink()
                    else None
                )
                live = record is not None and _live(record)
                recover_failed = state.phase == "failed"
                if (
                    state.phase == "review_required"
                    and status == MissionStatus.PROPOSED
                ):
                    continue
                if recover_failed and status not in {
                    MissionStatus.RUNNING,
                    MissionStatus.AWAITING_RESULT,
                }:
                    continue
                if recover_failed or state.phase == "review_required" or not live:
                    _spawn(runtime, request, state.generation + 1)
            recovered += 1
        except Exception:
            # A damaged private journal must not prevent unrelated missions
            # from recovering when the MCP server starts.
            continue
    return recovered


def _bundle_id(store, mission_id: str) -> str:
    from .mission_models import MissionEventType

    head = store.head(mission_id)
    events = []
    after = 0
    while after < head.seq:
        batch = store.tail(mission_id, after, min(256, head.seq - after))
        if not batch:
            raise SupervisorError("final result event stream is incomplete")
        events.extend(batch)
        after = batch[-1].seq
    matches = [
        event.payload.get("bundle_id")
        for event in events
        if event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
    ]
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise SupervisorError("exact final result bundle is unavailable")
    return matches[0]


def _reconcile_terminal_worker_receipts(mission_id: str) -> int:
    """Clear retained worker ownership only from exact committed terminal proof."""

    from ..cli.mission import _mission_evidence, _mission_runtime, _store_for_mission
    from .mission_models import AttemptState
    from .process_control import OwnedProcessRegistry, ProcessControlError
    from .worker_runtime import WorkerRuntime

    runtime = _mission_runtime(mission_id)
    registry = OwnedProcessRegistry(runtime)
    records = registry.records_for_mission(mission_id)
    if not records:
        return 0
    store = _store_for_mission(mission_id)
    try:
        snapshot = store.snapshot(mission_id)
        evidence = _mission_evidence(store, mission_id)
        attempts = {item.attempt_id: item for item in snapshot.attempts}
        reconciled = 0
        for attempt_id in sorted({item.attempt_id for item in records}):
            attempt = attempts.get(attempt_id)
            if attempt is None or attempt.state not in {
                AttemptState.COMMITTED,
                AttemptState.FAILED,
                AttemptState.CANCELLED,
            }:
                continue
            receipt_name = sha256_hex(attempt_id.encode()) + ".json"
            candidates = tuple(
                root
                for root in (
                    runtime / "adk-runtime",
                    runtime / "outbound-executor",
                )
                if (root / "worker-receipts" / receipt_name).is_file()
            )
            if len(candidates) > 1:
                raise ProcessControlError("owned worker runtime is ambiguous")
            if not candidates:
                continue
            dispatch, committed_attempt = WorkerRuntime.dispatch_from_snapshot(
                snapshot, attempt_id
            )
            if WorkerRuntime.reconcile_terminal_receipt(
                dispatch,
                committed_attempt,
                runtime=candidates[0],
                evidence=evidence,
            ):
                reconciled += 1
        return reconciled
    finally:
        store.close()


def _run(request: SupervisorRequest, generation: int) -> None:
    from argparse import Namespace

    from ..cli.mission import (
        _execute_adk_mission,
        _mission_runtime,
        _reconcile_cancellation_request,
        _start_bound,
        _start_identity,
        _store_for_mission,
        execute_scripted_mission,
    )
    from ..core_models import TruthKind
    from .local_result import finalize_local_result_decision
    from .mission_models import (
        AuthorizationMode,
        FinalizationMode,
        MissionStatus,
        plan_policy_decision,
    )

    runtime = _mission_runtime(request.mission_id)
    arguments = Namespace(
        repo=Path(request.repository_path),
        goal=request.goal,
        success_criteria=list(request.success_criteria),
        driver=request.driver,
        max_workers=request.max_workers,
        auto_approve=(
            request.driver == "scripted-local"
            and request.requested_mode == "policy_pre_authorized"
        ),
        command_id=request.command_id,
        open_viewer=False,
        json_mode=True,
        demo_injected_check_fault=False,
        authorization_mode=request.requested_mode,
        finalization_mode=request.finalization_mode,
    )
    command_id, mission_id, repository, _head, policy, binding = _start_identity(
        arguments
    )
    if mission_id != request.mission_id or command_id != request.command_id:
        raise SupervisorError("supervisor request identity changed")
    if request.check_executor is not None:
        binding["check_executor"] = request.check_executor
    _reconcile_cancellation_request(mission_id)
    _reconcile_terminal_worker_receipts(mission_id)
    _state(runtime, request, "planning", generation)
    gemini_proposal = None
    if (
        request.driver == "gemini-adk"
        and _authoritative_mission_status(request.mission_id) is None
    ):
        gemini_proposal = _supervised_gemini_proposal(
            request, policy, repository, runtime
        )
    _start_bound(
        arguments,
        command_id=command_id,
        mission_id=mission_id,
        policy=policy,
        repository=repository,
        runtime=runtime,
        binding=binding,
        gemini_proposal=gemini_proposal,
    )
    store = _store_for_mission(mission_id)
    snapshot = store.snapshot(mission_id)
    if snapshot.mission.status == MissionStatus.PROPOSED:
        _state(runtime, request, "review_required", generation)
        return
    if snapshot.mission.status == MissionStatus.RUNNING:
        _state(runtime, request, "running", generation)
        if request.driver == "gemini-adk":
            _execute_adk_mission(store=store, mission_id=mission_id)
        else:
            execute_scripted_mission(
                store=store,
                runtime=runtime,
                mission_id=mission_id,
            )
        snapshot = store.snapshot(mission_id)
    if snapshot.mission.status == MissionStatus.AWAITING_RESULT:
        # Reconcile the crash window between the terminal worker transition and
        # durable bundle registration. The helper is content-addressed and
        # idempotent when the exact current bundle is already registered.
        from ..cli.mission import _prepare_pending_bundle

        if snapshot.mission.final_outcome is None:
            _prepare_pending_bundle(mission_id)
            snapshot = store.snapshot(mission_id)
        events = []
        after = 0
        while after < snapshot.head.seq:
            batch = store.tail(mission_id, after, min(256, snapshot.head.seq - after))
            if not batch:
                raise SupervisorError("mission policy event stream is incomplete")
            events.extend(batch)
            after = batch[-1].seq
        try:
            decision = plan_policy_decision(tuple(events), snapshot.plan.revision)
        except ValueError as error:
            raise SupervisorError("mission policy decision is invalid") from error
        policy_auto_finalize = (
            decision is not None
            and decision.effective_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
            and decision.finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED
        )
        scripted_auto_finalize = (
            request.driver == "scripted-local"
            and request.finalization_mode == "auto_finalize_isolated"
        )
        if not policy_auto_finalize and not scripted_auto_finalize:
            _state(runtime, request, "review_required", generation)
            return
        _state(runtime, request, "finalizing", generation)
        bundle_id = _bundle_id(store, mission_id)
        if request.driver == "scripted-local":
            finalize_local_result_decision(
                store=store,
                mission_id=mission_id,
                command_id="auto_finalize_" + request.request_sha256[:32],
                expected_head=snapshot.head,
                expected_bundle_id=bundle_id,
                operator_label="scripted-fixture",
                rationale="Explicit simulated fixture automatic finalization.",
                truth_kind=TruthKind.SIMULATED_FIXTURE,
                recorded_at=datetime.now(UTC),
                approved=True,
                allow_simulated_fixture=True,
            )
        else:
            from .local_result import auto_finalize_local_result

            auto_finalize_local_result(
                store=store,
                mission_id=mission_id,
                expected_head=snapshot.head,
                expected_bundle_id=bundle_id,
                recorded_at=datetime.now(UTC),
            )
        snapshot = store.snapshot(mission_id)
    if snapshot.mission.status != MissionStatus.COMPLETED:
        raise SupervisorError("supervisor stopped before mission completion")
    _state(runtime, request, "completed", generation)


def run_supervisor(mission_id: str, request_sha256: str, generation: int) -> int:
    from ..cli.mission import _mission_runtime

    runtime = _mission_runtime(mission_id)
    request = _read(_request_path(runtime), SupervisorRequest)
    if request.mission_id != mission_id or request.request_sha256 != request_sha256:
        return 2
    try:
        if sys.stdin.buffer.read(1) != b"":
            return 2
        process = _read_process(runtime / _PROCESS, request)
    except (AttributeError, OSError, SupervisorError):
        return 2
    if not (
        isinstance(process, SupervisorProcess)
        and process.mission_id == mission_id
        and process.request_sha256 == request_sha256
        and process.generation == generation
        and process.pid == os.getpid()
        and _live(process)
    ):
        return 2
    try:
        _run(request, generation)
    except BaseException as error:  # child boundary: persist only a bounded class label
        code = type(error).__name__.lower().replace("_", "-")[:64]
        try:
            _state(runtime, request, "failed", generation, error_code=code)
        except Exception:
            pass
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphene-supervisor", allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", dest="mission_id")
    mode.add_argument("--recover-cancellations", action="store_true")
    parser.add_argument("--request-sha256")
    parser.add_argument("--generation", type=int)
    return parser


def main() -> int:
    parser = _parser()
    arguments = parser.parse_args()
    if arguments.recover_cancellations:
        from ..cli.mission import _reconcile_cancellation_requests

        _reconcile_cancellation_requests()
        return 0
    if arguments.request_sha256 is None or arguments.generation is None:
        parser.error("--run requires --request-sha256 and --generation")
    assert arguments.mission_id is not None
    return run_supervisor(
        arguments.mission_id, arguments.request_sha256, arguments.generation
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SupervisorError",
    "SupervisorProcess",
    "SupervisorRequest",
    "SupervisorState",
    "accept_goal",
    "ensure_supervisor",
    "recover_supervisors",
    "run_supervisor",
    "supervisor_acceptance",
    "supervisor_status",
]
