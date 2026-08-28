"""Private framed planner child; only the supervisor owns repository state."""

from __future__ import annotations

import asyncio
import os
import stat
import struct
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..core_models import FrozenModel, Identifier, Sha256, UtcDateTime
from ..hashing import canonical_json_bytes, canonical_json_sha256
from .adk_planner import (
    LIVE_GEMINI_MODEL,
    AdkPlanner,
    PlanProposal,
    PlanningRequest,
    _credential_preflight,
)
from .mission_models import ProjectPolicy
from .process_control import _owned_process_identity
from .worker_runtime import PROVIDER_CALL_TIMESTAMP_PATTERN, format_provider_call_timestamp
from .workers.gemini import StampedGemini

PLANNER_CHILD_MAX_FRAME_BYTES = 2_097_152
PLANNER_CHILD_MAX_JOURNAL_BYTES = 6_291_456
_GO = "planner-go.json"
_JOURNAL = "planner.frames"


class PlannerChildRequest(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    supervisor_request_sha256: Sha256
    attempt_number: int = Field(ge=1, le=2)
    policy: ProjectPolicy
    planning: PlanningRequest

    @model_validator(mode="after")
    def identities_match(self) -> PlannerChildRequest:
        if self.planning.mission_id != self.mission_id:
            raise ValueError("planner child mission identity changed")
        return self

    def request_sha256(self) -> str:
        return canonical_json_sha256(self.model_dump(mode="json"))


class PlannerChildProcess(FrozenModel):
    schema_version: Literal[1] = 1
    pid: int = Field(gt=1)
    pgid: int = Field(gt=1)
    started_at: str = Field(min_length=1, max_length=128)
    birth_token: str = Field(min_length=1, max_length=256)
    executable: str = Field(min_length=1, max_length=1_024)

    @model_validator(mode="after")
    def owns_group(self) -> PlannerChildProcess:
        if self.pid != self.pgid:
            raise ValueError("planner child must own its process group")
        return self


class PlannerChildFrame(FrozenModel):
    schema_version: Literal[1] = 1
    type: Literal["ready", "provider_dispatched", "result", "error"]
    mission_id: Identifier
    supervisor_request_sha256: Sha256
    child_request_sha256: Sha256
    attempt_number: int = Field(ge=1, le=2)
    process: PlannerChildProcess | None = None
    sdk_invocation_id: Identifier | None = None
    dispatched_at: str | None = Field(
        default=None, pattern=PROVIDER_CALL_TIMESTAMP_PATTERN
    )
    proposal: PlanProposal | None = None
    error_code: Identifier | None = None

    @model_validator(mode="after")
    def shape_matches_type(self) -> PlannerChildFrame:
        present = {
            "process": self.process is not None,
            "sdk": self.sdk_invocation_id is not None,
            "dispatched": self.dispatched_at is not None,
            "proposal": self.proposal is not None,
            "error": self.error_code is not None,
        }
        expected = {
            "ready": {
                "process": True,
                "sdk": False,
                "dispatched": False,
                "proposal": False,
                "error": False,
            },
            "provider_dispatched": {
                "process": False,
                "sdk": True,
                "dispatched": True,
                "proposal": False,
                "error": False,
            },
            "result": {
                "process": False,
                "sdk": True,
                "dispatched": False,
                "proposal": True,
                "error": False,
            },
            "error": {
                "process": False,
                "sdk": False,
                "dispatched": False,
                "proposal": False,
                "error": True,
            },
        }[self.type]
        if present != expected:
            raise ValueError("planner child frame has the wrong shape")
        return self


class PlannerGo(FrozenModel):
    schema_version: Literal[1] = 1
    child_request_sha256: Sha256


class PlannerAttemptOutcome(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    supervisor_request_sha256: Sha256
    child_request_sha256: Sha256
    attempt_number: int = Field(ge=1, le=2)
    outcome: Literal[
        "pre_dispatch_interrupted",
        "provider_outcome_unknown",
        "completed",
        "child_error",
    ]
    sdk_invocation_id: Identifier | None = None
    dispatched_at: str | None = Field(
        default=None, pattern=PROVIDER_CALL_TIMESTAMP_PATTERN
    )
    recorded_at: UtcDateTime

    @model_validator(mode="after")
    def provider_identity_matches_outcome(self) -> PlannerAttemptOutcome:
        has_identity = self.sdk_invocation_id is not None
        if has_identity != (self.dispatched_at is not None) or (
            self.outcome in {"provider_outcome_unknown", "completed"}
            and not has_identity
        ) or (self.outcome == "pre_dispatch_interrupted" and has_identity):
            raise ValueError("planner outcome provider identity is inconsistent")
        return self


def planner_frame_bytes(value: FrozenModel) -> bytes:
    payload = canonical_json_bytes(value.model_dump(mode="json"))
    if len(payload) > PLANNER_CHILD_MAX_FRAME_BYTES:
        raise ValueError("planner child frame exceeds its byte limit")
    return struct.pack(">I", len(payload)) + payload


def read_planner_frames(path: Path) -> tuple[PlannerChildFrame, ...]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return ()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_size > PLANNER_CHILD_MAX_JOURNAL_BYTES
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise ValueError("planner child journal is unsafe")
    raw = path.read_bytes()
    frames: list[PlannerChildFrame] = []
    offset = 0
    while len(raw) - offset >= 4:
        size = struct.unpack(">I", raw[offset : offset + 4])[0]
        if not 0 < size <= PLANNER_CHILD_MAX_FRAME_BYTES:
            raise ValueError("planner child journal frame is invalid")
        end = offset + 4 + size
        if end > len(raw):
            break
        payload = raw[offset + 4 : end]
        frame = PlannerChildFrame.model_validate_json(payload)
        if canonical_json_bytes(frame.model_dump(mode="json")) != payload:
            raise ValueError("planner child journal is not canonical")
        frames.append(frame)
        offset = end
    return tuple(frames)


def _private_directory(path: Path) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise ValueError("planner child directory is unsafe")


def _read_request() -> PlannerChildRequest:
    header = sys.stdin.buffer.read(4)
    if len(header) != 4:
        raise ValueError("missing planner child request frame")
    size = struct.unpack(">I", header)[0]
    if not 0 < size <= PLANNER_CHILD_MAX_FRAME_BYTES:
        raise ValueError("planner child request exceeds its byte limit")
    payload = sys.stdin.buffer.read(size)
    if len(payload) != size or sys.stdin.buffer.read(1):
        raise ValueError("planner child request is invalid")
    request = PlannerChildRequest.model_validate_json(payload)
    if canonical_json_bytes(request.model_dump(mode="json")) != payload:
        raise ValueError("planner child request is not canonical")
    return request


def _append_frame(path: Path, frame: PlannerChildFrame) -> None:
    content = planner_frame_bytes(frame)
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_APPEND
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size + len(content) > PLANNER_CHILD_MAX_JOURNAL_BYTES
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise ValueError("planner child journal is unsafe")
        view = memoryview(content)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        os.close(descriptor)


def _wait_for_go(directory: Path, request_sha256: str) -> None:
    deadline = time.monotonic() + 300
    path = directory / _GO
    while time.monotonic() < deadline:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            time.sleep(0.02)
            continue
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ValueError("planner child go record is unsafe")
        value = PlannerGo.model_validate_json(path.read_bytes())
        if value.child_request_sha256 != request_sha256:
            raise ValueError("planner child go binding changed")
        return
    raise TimeoutError("planner child was never authorized to dispatch")


async def _run(request: PlannerChildRequest, directory: Path) -> int:
    journal = directory / _JOURNAL
    child_request_sha256 = request.request_sha256()
    pgid, started_at, state, executable, birth_token = _owned_process_identity(
        os.getpid()
    )
    if state.startswith("Z") or pgid != os.getpid():
        raise ValueError("planner child process identity is invalid")
    if executable.startswith("(") and executable.endswith(")"):
        executable = os.path.abspath(sys.executable)

    def frame(kind: str, **values: object) -> None:
        _append_frame(
            journal,
            PlannerChildFrame(
                type=kind,
                mission_id=request.mission_id,
                supervisor_request_sha256=request.supervisor_request_sha256,
                child_request_sha256=child_request_sha256,
                attempt_number=request.attempt_number,
                **values,
            ),
        )

    frame(
        "ready",
        process=PlannerChildProcess(
            pid=os.getpid(),
            pgid=pgid,
            started_at=started_at,
            birth_token=birth_token,
            executable=executable,
        ),
    )
    _wait_for_go(directory, child_request_sha256)
    credential_mode = _credential_preflight(os.environ, adc_probe=None)
    model = StampedGemini(model=LIVE_GEMINI_MODEL)

    def dispatched(invocation_id: str) -> None:
        frame(
            "provider_dispatched",
            sdk_invocation_id=invocation_id,
            dispatched_at=format_provider_call_timestamp(datetime.now(UTC)),
        )

    planner = AdkPlanner(
        model=model,
        driver="gemini_live",
        credential_mode=credential_mode,
        dispatch_callback=dispatched,
    )
    try:
        proposal = await planner.propose(request.policy, request.planning)
    except BaseException as error:
        frame(
            "error",
            error_code=type(error).__name__.lower().replace("_", "-")[:64],
        )
        return 1
    frame(
        "result",
        sdk_invocation_id=proposal.receipt.invocation_id,
        proposal=proposal,
    )
    return 0


def main() -> int:
    try:
        directory = Path.cwd()
        _private_directory(directory)
        request = _read_request()
        return asyncio.run(_run(request, directory))
    except BaseException:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PLANNER_CHILD_MAX_FRAME_BYTES",
    "PlannerAttemptOutcome",
    "PlannerChildFrame",
    "PlannerChildProcess",
    "PlannerChildRequest",
    "PlannerGo",
    "planner_frame_bytes",
    "read_planner_frames",
]
