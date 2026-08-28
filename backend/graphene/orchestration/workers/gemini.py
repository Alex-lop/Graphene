from __future__ import annotations

import asyncio
import os
import re
import signal
import stat
import struct
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import cached_property
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

import google.adk
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.models import BaseLlm, LlmResponse
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.telemetry import ContentCapturingMode, TelemetryConfig
from google.genai import Client, errors as genai_errors, types
from pydantic import Field, PrivateAttr, model_validator

from ...hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ...core_models import FrozenModel, Identifier, RepoPath
from ..adk_planner import (
    ADK_VERSION,
    LIVE_GEMINI_MODEL,
    PlannerUnavailable,
    _canonical_model,
    _credential_preflight,
    describe_output_schema,
)
from ..mission_models import Dispatch, TaskKind
from ..worker_runtime import (
    CompletionOutcome,
    PriorFailure,
    RuntimeAssignment,
    RuntimeErrorCode,
    RuntimeFailure,
    WorkerCapabilities,
    WorkerCompletion,
    WorkerContext,
    WorkerProviderReceipt,
    WorkerProviderInterruption,
    PROVIDER_CALL_TIMESTAMP_PATTERN,
    format_provider_call_timestamp,
    stable_operation_id,
)
from ..process_control import (
    ModelDispatchBarrier,
    OwnedProcess,
    OwnedProcessRegistry,
    ProcessControlError,
)


class FileMutation(FrozenModel):
    operation: Literal["create", "update", "delete", "rename", "chmod"]
    path: RepoPath
    text: str | None = Field(default=None, max_length=262_144)
    new_path: RepoPath | None = None
    mode: Literal["100644", "100755"] | None = None

    @model_validator(mode="after")
    def shape_matches_operation(self) -> FileMutation:
        shape = (
            self.text is not None,
            self.new_path is not None,
            self.mode is not None,
        )
        expected = {
            "create": (True, False, True),
            "update": (True, False, False),
            "delete": (False, False, False),
            "rename": (False, True, False),
            "chmod": (False, False, True),
        }
        if shape != expected[self.operation] or (
            self.operation == "rename" and self.new_path == self.path
        ):
            raise ValueError("file mutation fields do not match operation")
        return self


class WorkerIntent(FrozenModel):
    mutations: tuple[FileMutation, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def mutations_are_bounded(self) -> WorkerIntent:
        if (
            sum(
                len(item.text.encode("utf-8"))
                for item in self.mutations
                if item.text is not None
            )
            > 1_048_576
        ):
            raise ValueError("worker mutations exceed their total byte limit")
        return self


CHILD_PROTOCOL_VERSION = 1
CHILD_MAX_FRAME_BYTES = 2_097_152
CHILD_MAX_STDERR_BYTES = 65_536
_CHILD_MODULE = "graphene.orchestration.workers.gemini_child"


class GeminiChildSource(FrozenModel):
    path: RepoPath
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str = Field(max_length=262_144)

    @model_validator(mode="after")
    def digest_matches_text(self) -> GeminiChildSource:
        if self.sha256 != sha256_hex(self.text.encode()):
            raise ValueError("child source digest does not match its text")
        return self


class GeminiChildInput(FrozenModel):
    reference_id: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str = Field(max_length=65_536)

    @model_validator(mode="after")
    def digest_matches_text(self) -> GeminiChildInput:
        if self.sha256 != sha256_hex(self.text.encode()):
            raise ValueError("child input digest does not match its text")
        return self


class GeminiChildRequest(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: str = Field(min_length=1, max_length=128)
    plan_revision: int = Field(ge=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_id: str = Field(min_length=1, max_length=128)
    attempt_id: str = Field(min_length=1, max_length=128)
    attempt_number: int = Field(ge=1)
    worker_id: str = Field(min_length=1, max_length=128)
    lease_id: str = Field(min_length=1, max_length=128)
    fencing_token: int = Field(ge=1)
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_input_sha256: tuple[str, ...] = Field(max_length=64)
    title: str = Field(min_length=1, max_length=4_096)
    contract: str = Field(min_length=1, max_length=16_384)
    sources: tuple[GeminiChildSource, ...] = Field(max_length=256)
    operator_inputs: tuple[GeminiChildInput, ...] = Field(max_length=64)
    write_paths: tuple[RepoPath, ...] = Field(min_length=1, max_length=64)
    prior_failure: PriorFailure | None = None
    requested_model: str = Field(min_length=1, max_length=128)
    credential_mode: Literal["gemini_api", "vertex_ai"]
    timeout_seconds: float = Field(gt=0, le=300)

    @model_validator(mode="after")
    def request_is_canonical_and_bounded(self) -> GeminiChildRequest:
        if self.write_paths != tuple(sorted(set(self.write_paths))):
            raise ValueError("child write paths must be sorted and unique")
        if tuple(item.path for item in self.sources) != tuple(
            sorted({item.path for item in self.sources})
        ):
            raise ValueError("child source paths must be sorted and unique")
        if self.accepted_input_sha256 != tuple(
            sorted(self.accepted_input_sha256)
        ) or any(
            re.fullmatch(r"[0-9a-f]{64}", item) is None
            for item in self.accepted_input_sha256
        ):
            raise ValueError("accepted input hashes must be valid and sorted")
        if sum(len(item.text.encode()) for item in self.sources) > 1_048_576:
            raise ValueError("child sources exceed their byte limit")
        if sum(len(item.text.encode()) for item in self.operator_inputs) > 131_072:
            raise ValueError("child operator inputs exceed their byte limit")
        return self

    def request_sha256(self) -> str:
        return canonical_json_sha256(self.model_dump(mode="json"))


class GeminiChildFrame(FrozenModel):
    schema_version: Literal[1] = 1
    type: Literal["provider_dispatched", "result", "error"]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sdk_invocation_id: Identifier | None = None
    session_id: Identifier | None = None
    dispatched_at: str | None = Field(
        default=None, pattern=PROVIDER_CALL_TIMESTAMP_PATTERN
    )
    intent: WorkerIntent | None = None
    provider: WorkerProviderReceipt | None = None
    result_code: RuntimeErrorCode | None = None

    @model_validator(mode="after")
    def frame_shape_matches_type(self) -> GeminiChildFrame:
        if self.type == "provider_dispatched":
            if (
                self.sdk_invocation_id is None
                or self.dispatched_at is None
                or any(
                    value is not None
                    for value in (
                        self.session_id,
                        self.intent,
                        self.provider,
                        self.result_code,
                    )
                )
            ):
                raise ValueError("provider dispatch frame has the wrong shape")
        elif self.type == "result":
            if (
                self.intent is None
                or self.provider is None
                or self.sdk_invocation_id is None
                or self.session_id is None
                or self.dispatched_at is not None
                or self.result_code is not None
            ):
                raise ValueError("child result frame has the wrong shape")
        elif (
            self.result_code is None
            or self.sdk_invocation_id is None
            or self.session_id is None
            or self.intent is not None
            or self.dispatched_at is not None
        ):
            raise ValueError("child error frame has the wrong shape")
        return self


def child_frame_bytes(value: FrozenModel) -> bytes:
    payload = canonical_json_bytes(value.model_dump(mode="json"))
    if len(payload) > CHILD_MAX_FRAME_BYTES:
        raise ValueError("Gemini child frame exceeds its byte limit")
    return struct.pack(">I", len(payload)) + payload


class ProviderStamp(FrozenModel):
    """What the provider itself said about one call: identifiers and instants only."""

    response_id: str | None = None
    create_time: str | None = None
    response_date: str | None = None


_RESPONSE_ID = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")


def provider_stamp(response: Any) -> ProviderStamp:
    """Read the provider-side stamps off a raw ``GenerateContentResponse``.

    Never raises and never reads content: a response missing any field
    yields ``None`` for that field, so a stamp can only be absent, not wrong.
    """

    response_id = getattr(response, "response_id", None)
    if not isinstance(response_id, str) or _RESPONSE_ID.match(response_id) is None:
        response_id = None
    create_time = None
    created = getattr(response, "create_time", None)
    if isinstance(created, datetime) and created.tzinfo is not None:
        create_time = format_provider_call_timestamp(created)
    response_date = None
    http = getattr(response, "sdk_http_response", None)
    headers = getattr(http, "headers", None)
    if isinstance(headers, Mapping):
        date = next(
            (value for key, value in headers.items() if str(key).lower() == "date"),
            None,
        )
        try:
            parsed = parsedate_to_datetime(str(date)) if date else None
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            response_date = format_provider_call_timestamp(parsed)
    return ProviderStamp(
        response_id=response_id, create_time=create_time, response_date=response_date
    )


class StampedGemini(Gemini):
    """ADK ``Gemini`` whose client records ``provider_stamp`` for every call.

    The runtime's clock brackets each call in the receipt; these stamps are
    the provider's own view of it, so overlap between workers can be measured
    on a clock Graphene does not own. The wrapper only observes the response
    object after the SDK returns it and cannot alter the call.
    """

    _stamps: list[ProviderStamp] = PrivateAttr(default_factory=list)
    _dispatch_callback: Callable[[], None] | None = PrivateAttr(default=None)
    _dispatch_acknowledged: bool = PrivateAttr(default=False)

    @cached_property
    def api_client(self) -> Client:
        client = Gemini.api_client.func(self)
        api = client._api_client
        if api._use_aiohttp() or api._async_httpx_client is None:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        httpx_client = api._async_httpx_client
        original_transport_for_url = httpx_client._transport_for_url
        wrapped: dict[int, Any] = {}

        def transport_for_url(url: Any) -> Any:
            transport = original_transport_for_url(url)
            if id(transport) not in wrapped:
                original_send = transport.handle_async_request

                async def handle_async_request(*args: Any, **kwargs: Any) -> Any:
                    if (
                        self._dispatch_callback is not None
                        and not self._dispatch_acknowledged
                    ):
                        self._dispatch_callback()
                        self._dispatch_acknowledged = True
                    return await original_send(*args, **kwargs)

                transport.handle_async_request = handle_async_request
                wrapped[id(transport)] = transport
            return transport

        httpx_client._transport_for_url = transport_for_url
        models = client.aio.models
        original = models.generate_content

        async def generate_content(*args: Any, **kwargs: Any) -> Any:
            response = await original(*args, **kwargs)
            self._stamps.append(provider_stamp(response))
            return response

        models.generate_content = generate_content  # type: ignore[method-assign]
        return client

    def bind_dispatch_callback(self, callback: Callable[[], None]) -> None:
        self._dispatch_callback = callback
        self._dispatch_acknowledged = False

    @property
    def stamps(self) -> tuple[ProviderStamp, ...]:
        return tuple(self._stamps)


class _Observation:
    def __init__(self, session_id: str, agent_name: str) -> None:
        self.session_id = session_id
        self.agent_name = agent_name
        self.calls = 0
        self.invocation_ids: set[str] = set()
        self.models: set[str] = set()
        self.usage: types.GenerateContentResponseUsageMetadata | None = None

    def before_model(
        self, callback_context: CallbackContext, llm_request: object
    ) -> None:
        del llm_request
        if (
            callback_context.session.id != self.session_id
            or callback_context.agent_name != self.agent_name
        ):
            raise RuntimeFailure(RuntimeErrorCode.OUTCOME_UNKNOWN, outcome_unknown=True)
        self.invocation_ids.add(callback_context.invocation_id)

    def after_model(
        self, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> None:
        if (
            callback_context.session.id != self.session_id
            or callback_context.agent_name != self.agent_name
        ):
            raise RuntimeFailure(RuntimeErrorCode.OUTCOME_UNKNOWN, outcome_unknown=True)
        self.calls += 1
        self.invocation_ids.add(callback_context.invocation_id)
        if llm_response.model_version:
            self.models.add(llm_response.model_version)
        if llm_response.usage_metadata is not None:
            self.usage = llm_response.usage_metadata


class GeminiWorkerAdapter:
    """One-turn typed Gemini worker; all filesystem effects remain Graphene-owned."""

    def __init__(
        self,
        *,
        worker_id: str,
        model: BaseLlm | str,
        driver: Literal["adk_fake", "gemini_live"],
        credential_mode: Literal["not_applicable", "gemini_api", "vertex_ai"],
        heartbeat_seconds: float = 5,
        model_timeout_seconds: float = 120,
    ) -> None:
        if google.adk.__version__ != ADK_VERSION:
            raise PlannerUnavailable(
                f"Google ADK {ADK_VERSION} is required; found {google.adk.__version__}"
            )
        if not 0 < heartbeat_seconds <= 60:
            raise ValueError("worker heartbeat interval is invalid")
        if not 0 < model_timeout_seconds <= 300:
            raise ValueError("worker model timeout is invalid")
        self.model = model
        self.driver = driver
        self.credential_mode = credential_mode
        self.heartbeat_seconds = heartbeat_seconds
        self.model_timeout_seconds = model_timeout_seconds
        requested = model.model if isinstance(model, BaseLlm) else model
        self.requested_model = requested
        self._capabilities = WorkerCapabilities(
            worker_id=worker_id,
            driver=driver,
            task_kinds=(TaskKind.WORK,),
            model_id=requested,
            max_parallel_attempts=1,
        )

    @property
    def capabilities(self) -> WorkerCapabilities:
        return self._capabilities

    @classmethod
    def fake(
        cls,
        *,
        worker_id: str,
        model: BaseLlm,
        heartbeat_seconds: float = 0.01,
        model_timeout_seconds: float = 120,
    ) -> GeminiWorkerAdapter:
        return cls(
            worker_id=worker_id,
            model=model,
            driver="adk_fake",
            credential_mode="not_applicable",
            heartbeat_seconds=heartbeat_seconds,
            model_timeout_seconds=model_timeout_seconds,
        )

    @classmethod
    def live(
        cls,
        *,
        worker_id: str,
        model: str = LIVE_GEMINI_MODEL,
        environ: Mapping[str, str] | None = None,
        adc_probe: Callable[[], object] | None = None,
        heartbeat_seconds: float = 5,
        model_timeout_seconds: float = 120,
    ) -> GeminiWorkerAdapter:
        if model != LIVE_GEMINI_MODEL:
            raise PlannerUnavailable(
                f"live workers require the explicit model {LIVE_GEMINI_MODEL}"
            )
        credential_mode = _credential_preflight(
            os.environ if environ is None else environ, adc_probe=adc_probe
        )
        return cls(
            worker_id=worker_id,
            model=StampedGemini(model=model),
            driver="gemini_live",
            credential_mode=credential_mode,
            heartbeat_seconds=heartbeat_seconds,
            model_timeout_seconds=model_timeout_seconds,
        )

    async def _heartbeat(self, context: WorkerContext, done: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(done.wait(), timeout=self.heartbeat_seconds)
                return
            except TimeoutError:
                await context.heartbeat()

    @staticmethod
    async def _read_child_frame(stream: asyncio.StreamReader) -> GeminiChildFrame:
        try:
            size = struct.unpack(">I", await stream.readexactly(4))[0]
        except (asyncio.IncompleteReadError, struct.error) as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if not 0 < size <= CHILD_MAX_FRAME_BYTES:
            raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
        try:
            payload = await stream.readexactly(size)
        except asyncio.IncompleteReadError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        try:
            frame = GeminiChildFrame.model_validate_json(payload)
        except ValueError as error:
            raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED) from error
        if canonical_json_bytes(frame.model_dump(mode="json")) != payload:
            raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
        return frame

    @staticmethod
    async def _read_child_stderr(stream: asyncio.StreamReader) -> tuple[bytes, bool]:
        output = bytearray()
        truncated = False
        while chunk := await stream.read(8_192):
            remaining = CHILD_MAX_STDERR_BYTES - len(output)
            output.extend(chunk[:remaining])
            truncated = truncated or len(chunk) > remaining
        return bytes(output), truncated

    @staticmethod
    def _child_environment() -> dict[str, str]:
        allowed = {
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            "GOOGLE_GENAI_USE_VERTEXAI",
            "HOME",
            "HTTPS_PROXY",
            "NO_PROXY",
            "REQUESTS_CA_BUNDLE",
            "SSL_CERT_FILE",
        }
        return {
            **{key: value for key, value in os.environ.items() if key in allowed},
            "LC_ALL": "C",
            "PYTHONUNBUFFERED": "1",
        }

    def _valid_child_provider(self, provider: WorkerProviderReceipt) -> bool:
        return (
            provider.driver == "gemini_live"
            and provider.requested_model == self.requested_model
            and provider.credential_mode == self.credential_mode
            and _canonical_model(provider.returned_model)
            == _canonical_model(self.requested_model)
        )

    async def _execute_child(
        self, context: WorkerContext, request: GeminiChildRequest
    ) -> tuple[WorkerIntent | None, WorkerCompletion]:
        runtime = context.runtime.runtime
        children = runtime / "model-children"
        try:
            children.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(
                children,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    raise OSError("model child path is not a directory")
                os.fchmod(descriptor, 0o700)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        registry = OwnedProcessRegistry(runtime.parent)
        interpreter = os.path.abspath(sys.executable)
        if not Path(interpreter).is_file() or not os.access(interpreter, os.X_OK):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        arguments = (interpreter, "-I", "-m", _CHILD_MODULE)
        deadline = asyncio.get_running_loop().time() + self.model_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                process = await asyncio.create_subprocess_exec(
                    *arguments,
                    cwd=children,
                    env=self._child_environment(),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                    close_fds=True,
                )
        except TimeoutError:
            raise RuntimeFailure(RuntimeErrorCode.PROVIDER_TIMEOUT) from None
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        request_sha256 = request.request_sha256()
        input_frame = child_frame_bytes(request)
        try:
            owned = registry.record_pid(
                context.dispatch,
                process.pid,
                interpreter,
                model_request_sha256=request_sha256,
                model_input_bytes=len(input_frame) - 4,
            )
        except Exception:
            process.kill()
            await process.wait()
            raise
        stderr_task = asyncio.create_task(self._read_child_stderr(process.stderr))
        done = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(context, done))
        barrier: ModelDispatchBarrier | None = None
        retain_unconfirmed = False
        try:
            async with asyncio.timeout_at(deadline):
                process.stdin.write(input_frame)
                await process.stdin.drain()
                process.stdin.close()
                await process.stdin.wait_closed()
                first = await self._read_child_frame(process.stdout)
                if (
                    first.type != "provider_dispatched"
                    or first.request_sha256 != request_sha256
                    or first.sdk_invocation_id is None
                    or first.dispatched_at is None
                ):
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                # Provider transport is now observed. Retain the exact v3
                # process even if barrier linking/fsync raises before the
                # local barrier variable is assigned.
                retain_unconfirmed = True
                try:
                    barrier = registry.acknowledge_model_dispatch(
                        context.dispatch,
                        owned,
                        request_sha256=request_sha256,
                        sdk_invocation_id=first.sdk_invocation_id,
                        dispatched_at=first.dispatched_at,
                    )
                except (OSError, ProcessControlError) as error:
                    try:
                        barrier = registry.confirm_model_dispatch_barrier(
                            context.dispatch
                        )
                    except (OSError, ProcessControlError):
                        barrier = None
                    raise RuntimeFailure(
                        RuntimeErrorCode.OUTCOME_UNKNOWN,
                        outcome_unknown=True,
                    ) from error
                final = await self._read_child_frame(process.stdout)
                if final.request_sha256 != request_sha256:
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                if await process.stdout.read(1):
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                returncode = await process.wait()
                if returncode:
                    raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
                if final.type == "error":
                    code = final.result_code or RuntimeErrorCode.RUNTIME_UNAVAILABLE
                    if (
                        final.sdk_invocation_id != barrier.sdk_invocation_id
                        or final.session_id is None
                        or (
                            final.provider is not None
                            and not self._valid_child_provider(final.provider)
                        )
                    ):
                        raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                    retryable = code in {
                        RuntimeErrorCode.MODEL_OUTPUT_REJECTED,
                        RuntimeErrorCode.PROVIDER_RATE_LIMITED,
                        RuntimeErrorCode.PROVIDER_TIMEOUT,
                        RuntimeErrorCode.PROVIDER_UNAVAILABLE,
                        RuntimeErrorCode.RUNTIME_UNAVAILABLE,
                    }
                    interruption = None
                    if final.provider is None:
                        stderr, truncated = await stderr_task
                        interruption = self._interruption_proof(
                            context.dispatch,
                            barrier,
                            request_sha256=request_sha256,
                            input_bytes=len(input_frame) - 4,
                            returncode=returncode,
                            stderr=stderr,
                            stderr_truncated=truncated,
                        )
                    return None, WorkerCompletion(
                        outcome=(
                            CompletionOutcome.RETRYABLE_FAILURE
                            if retryable
                            else CompletionOutcome.TERMINAL_FAILURE
                        ),
                        result_code=code.value,
                        session_id=final.session_id,
                        invocation_id=barrier.sdk_invocation_id,
                        provider=final.provider,
                        provider_interruption=interruption,
                    )
                if final.type != "result":
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                if (
                    final.intent is None
                    or final.provider is None
                    or final.session_id is None
                    or final.sdk_invocation_id != barrier.sdk_invocation_id
                    or not self._valid_child_provider(final.provider)
                ):
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                return final.intent, WorkerCompletion(
                    outcome=CompletionOutcome.COMPLETED,
                    result_code="passed",
                    session_id=final.session_id,
                    invocation_id=final.sdk_invocation_id,
                    provider=final.provider,
                )
        except TimeoutError:
            sent = None
            if process.returncode is None:
                if registry.signal_prepared(owned, signal.SIGTERM):
                    sent = signal.SIGTERM
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    if registry.signal_prepared(owned, signal.SIGKILL):
                        sent = signal.SIGKILL
                    await process.wait()
            if barrier is not None:
                stderr, truncated = await stderr_task
                return None, self._interrupted_completion(
                    context.dispatch,
                    barrier,
                    request_sha256=request_sha256,
                    input_bytes=len(input_frame) - 4,
                    returncode=(
                        process.returncode if process.returncode is not None else -1
                    ),
                    stderr=stderr,
                    stderr_truncated=truncated,
                )
            retain_unconfirmed = True
            return None, self._unconfirmed_interruption(
                context.dispatch,
                owned,
                request_sha256=request_sha256,
                input_bytes=len(input_frame) - 4,
                sent=sent,
            )
        except asyncio.CancelledError:
            retain_unconfirmed = barrier is None
            if process.returncode is None:
                registry.signal_prepared(owned, signal.SIGTERM)
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    registry.signal_prepared(owned, signal.SIGKILL)
                    await process.wait()
            raise
        except RuntimeFailure:
            sent = None
            if process.returncode is None:
                # A malformed child must not outlive the adapter that rejected it.
                if registry.signal_prepared(owned, signal.SIGKILL):
                    sent = signal.SIGKILL
                await process.wait()
            if barrier is None:
                retain_unconfirmed = True
                return None, self._unconfirmed_interruption(
                    context.dispatch,
                    owned,
                    request_sha256=request_sha256,
                    input_bytes=len(input_frame) - 4,
                    sent=sent,
                )
            stderr, truncated = await stderr_task
            return None, self._interrupted_completion(
                context.dispatch,
                barrier,
                request_sha256=request_sha256,
                input_bytes=len(input_frame) - 4,
                returncode=(
                    process.returncode if process.returncode is not None else -1
                ),
                stderr=stderr,
                stderr_truncated=truncated,
            )
        finally:
            done.set()
            await heartbeat
            if process.returncode is None:
                registry.signal_prepared(owned, signal.SIGKILL)
                await process.wait()
            if not stderr_task.done():
                await stderr_task
            # A transport-acknowledged result is cleared only after the parent
            # persists the whole-attempt receipt. A restart before then can
            # conservatively reconcile the exact barrier without replaying a
            # potentially billed provider call.
            if barrier is None and not retain_unconfirmed:
                registry.remove_exact(owned)

    def _interrupted_completion(
        self,
        dispatch: Dispatch,
        barrier: ModelDispatchBarrier,
        *,
        request_sha256: str,
        input_bytes: int | None,
        returncode: int,
        stderr: bytes,
        stderr_truncated: bool,
        derive_signal_name: bool = True,
    ) -> WorkerCompletion:
        interruption = self._interruption_proof(
            dispatch,
            barrier,
            request_sha256=request_sha256,
            input_bytes=input_bytes,
            returncode=returncode,
            stderr=stderr,
            stderr_truncated=stderr_truncated,
            derive_signal_name=derive_signal_name,
        )
        return WorkerCompletion(
            outcome=CompletionOutcome.RETRYABLE_FAILURE,
            result_code=RuntimeErrorCode.PROVIDER_INTERRUPTED.value,
            session_id="interrupted-" + dispatch.attempt_id[-16:],
            invocation_id=barrier.sdk_invocation_id,
            provider_interruption=interruption,
        )

    def _interruption_proof(
        self,
        dispatch: Dispatch,
        barrier: ModelDispatchBarrier,
        *,
        request_sha256: str,
        input_bytes: int | None,
        returncode: int,
        stderr: bytes,
        stderr_truncated: bool,
        derive_signal_name: bool = True,
    ) -> WorkerProviderInterruption:
        signal_name = None
        if derive_signal_name and returncode < 0:
            try:
                signal_name = signal.Signals(-returncode).name.lower()
            except ValueError:
                signal_name = "signal_unknown"
        return WorkerProviderInterruption(
            schema_version=1 if input_bytes is not None else 2,
            requested_model=self.requested_model,
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            lease_id=dispatch.lease_id,
            fencing_token=dispatch.fencing_token,
            request_sha256=request_sha256,
            input_bytes=input_bytes,
            sdk_invocation_id=barrier.sdk_invocation_id,
            dispatched_at=barrier.dispatched_at,
            pid=barrier.pid,
            pgid=barrier.pgid,
            process_started_at=barrier.started_at,
            process_identity_version=barrier.schema_version,
            process_birth_token=barrier.birth_token,
            executable=barrier.executable,
            exit_code=returncode,
            signal_name=signal_name,
            stderr_sha256=sha256_hex(stderr),
            stderr_truncated=stderr_truncated,
        )

    def _recover_interrupted_child(
        self, context: WorkerContext, request: GeminiChildRequest
    ) -> WorkerCompletion | None:
        registry = OwnedProcessRegistry(context.runtime.runtime.parent)
        try:
            recovered = registry.recover_model_dispatch(context.dispatch)
            if recovered is None:
                owned = registry.owned_process(
                    context.dispatch, require_live=False, model=True
                )
                if owned is None:
                    return None
                sent = registry.terminate_owned(owned, retain_record=True)
                request_sha256 = request.request_sha256()
                input_bytes = len(child_frame_bytes(request)) - 4
                if (
                    owned.model_request_sha256 is None
                    or owned.model_input_bytes is None
                ):
                    raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
                if (
                    owned.model_request_sha256 != request_sha256
                    or owned.model_input_bytes != input_bytes
                ):
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                return self._unconfirmed_interruption(
                    context.dispatch,
                    owned,
                    request_sha256=request_sha256,
                    input_bytes=input_bytes,
                    sent=sent,
                )
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        barrier, sent = recovered
        request_sha256 = request.request_sha256()
        if barrier.request_sha256 != request_sha256:
            raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
        input_bytes = len(child_frame_bytes(request)) - 4
        owned = registry.owned_process(
            context.dispatch, require_live=False, model=True
        )
        assert owned is not None
        if owned.model_request_sha256 is not None and (
            owned.model_request_sha256 != request_sha256
            or owned.model_input_bytes != input_bytes
        ):
            raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
        # An orphan is no longer our child, so POSIX exposes no wait status.
        # -1 means unavailable when the exact identity was already gone.
        return self._interrupted_completion(
            context.dispatch,
            barrier,
            request_sha256=request_sha256,
            input_bytes=input_bytes,
            returncode=-int(sent) if sent is not None else -1,
            stderr=b"",
            stderr_truncated=False,
            derive_signal_name=sent is not None,
        )

    def _unconfirmed_interruption(
        self,
        dispatch: Dispatch,
        owned: OwnedProcess,
        *,
        request_sha256: str,
        input_bytes: int,
        sent: int | None,
    ) -> WorkerCompletion:
        signal_name = None
        if sent is not None:
            signal_name = signal.Signals(sent).name.lower()
        interruption = WorkerProviderInterruption(
            requested_model=self.requested_model,
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            lease_id=dispatch.lease_id,
            fencing_token=dispatch.fencing_token,
            request_sha256=request_sha256,
            input_bytes=input_bytes,
            provider_dispatch_state="unconfirmed",
            pid=owned.pid,
            pgid=owned.pgid,
            process_started_at=owned.started_at,
            process_identity_version=1 if owned.birth_token is None else 2,
            process_birth_token=owned.birth_token,
            executable=owned.executable,
            exit_code=-int(sent) if sent is not None else -1,
            signal_name=signal_name,
            stderr_sha256=sha256_hex(b""),
            stderr_truncated=False,
        )
        return WorkerCompletion(
            outcome=CompletionOutcome.RETRYABLE_FAILURE,
            result_code=RuntimeErrorCode.PROVIDER_INTERRUPTED.value,
            session_id="interrupted-" + dispatch.attempt_id[-16:],
            invocation_id=stable_operation_id(dispatch, "unconfirmed-provider"),
            provider_interruption=interruption,
        )

    def reconcile_owned(
        self, dispatch: Dispatch, runtime: Path
    ) -> WorkerCompletion | None:
        """Stop one exact orphan without re-entering its expired lease."""

        if self.driver != "gemini_live":
            return None
        registry = OwnedProcessRegistry(runtime)
        try:
            recovered = registry.recover_model_dispatch(dispatch)
            if recovered is not None:
                barrier, sent = recovered
                owned = registry.owned_process(
                    dispatch, require_live=False, model=True
                )
                assert owned is not None
                return self._interrupted_completion(
                    dispatch,
                    barrier,
                    request_sha256=barrier.request_sha256,
                    input_bytes=owned.model_input_bytes,
                    returncode=-int(sent) if sent is not None else -1,
                    stderr=b"",
                    stderr_truncated=False,
                    derive_signal_name=sent is not None,
                )
            owned = registry.owned_process(
                dispatch, require_live=False, model=True
            )
            if owned is None:
                return None
            if (
                owned.model_request_sha256 is None
                or owned.model_input_bytes is None
            ):
                raise ProcessControlError("model process intent is unavailable")
            sent = registry.terminate_owned(owned, retain_record=True)
            return self._unconfirmed_interruption(
                dispatch,
                owned,
                request_sha256=owned.model_request_sha256,
                input_bytes=owned.model_input_bytes,
                sent=sent,
            )
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error

    async def recover_interrupted(
        self, context: WorkerContext, assignment: RuntimeAssignment
    ) -> WorkerCompletion | None:
        """Re-enter only an exact durable transport barrier, before model replay."""

        if self.driver != "gemini_live":
            return None
        registry = OwnedProcessRegistry(context.runtime.runtime.parent)
        try:
            barrier = registry.model_dispatch_barrier(
                context.dispatch, require_live=False
            )
            owned = registry.owned_process(
                context.dispatch, require_live=False, model=True
            )
            legacy_live = registry.live_legacy_record_blocks_model_spawn(
                context.dispatch
            )
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if legacy_live:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        if barrier is None and owned is None:
            return None
        return await self.execute(context, assignment)

    async def execute(
        self, context: WorkerContext, assignment: RuntimeAssignment
    ) -> WorkerCompletion:
        telemetry_unsafe = os.environ.get(
            "ADK_TELEMETRY_IGNORE_RUN_CONFIG", ""
        ).strip().lower() in {
            "1",
            "true",
        }
        sources = []
        source_bytes = 0
        for path in assignment.read_paths:
            try:
                text = await context.read_text(path)
            except FileNotFoundError:
                continue
            source_bytes += len(text.encode("utf-8"))
            if source_bytes > 1_048_576:
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
            sources.append({"path": path, "text": text})
        supplied_inputs = [
            {"reference_id": reference_id, "text": text}
            for reference_id, text in await context.read_supplied_inputs()
        ]
        request: dict[str, object] = {
            "contract": assignment.contract,
            "operator_inputs": supplied_inputs,
            "sources": sources,
            "title": assignment.title,
            "write_paths": context.dispatch.write_paths,
        }
        # The one thing a retry is allowed to learn. Absent on a first attempt, so
        # the first prompt is byte-identical to what it always was.
        if assignment.prior_failure is not None:
            request["prior_failure"] = assignment.prior_failure.model_dump(mode="json")
        payload = canonical_json_bytes(request).decode()
        if self.driver == "gemini_live":
            child_request = GeminiChildRequest(
                mission_id=context.dispatch.mission_id,
                plan_revision=context.dispatch.plan_revision,
                plan_sha256=context.dispatch.plan_sha256,
                task_id=context.dispatch.task_id,
                attempt_id=context.dispatch.attempt_id,
                attempt_number=context.dispatch.attempt_number,
                worker_id=context.dispatch.worker_id,
                lease_id=context.dispatch.lease_id,
                fencing_token=context.dispatch.fencing_token,
                base_sha=context.runtime.base_sha,
                policy_sha256=context.runtime.policy_sha256,
                accepted_input_sha256=tuple(
                    sorted(item.sha256 for item in context.dispatch.input_publications)
                ),
                title=assignment.title,
                contract=assignment.contract,
                sources=tuple(
                    GeminiChildSource(
                        path=item["path"],
                        sha256=sha256_hex(str(item["text"]).encode()),
                        text=str(item["text"]),
                    )
                    for item in sources
                ),
                operator_inputs=tuple(
                    GeminiChildInput(
                        reference_id=str(item["reference_id"]),
                        sha256=sha256_hex(str(item["text"]).encode()),
                        text=str(item["text"]),
                    )
                    for item in supplied_inputs
                ),
                write_paths=context.dispatch.write_paths,
                prior_failure=assignment.prior_failure,
                requested_model=self.requested_model,
                credential_mode=self.credential_mode,
                timeout_seconds=self.model_timeout_seconds,
            )
            recovered = await asyncio.to_thread(
                self._recover_interrupted_child, context, child_request
            )
            if recovered is not None:
                return recovered
            if telemetry_unsafe:
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
            intent, completion = await self._execute_child(context, child_request)
            if completion.outcome != CompletionOutcome.COMPLETED:
                return completion
            if intent is None:
                raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
            touched_paths = tuple(
                sorted(
                    {
                        path
                        for mutation in intent.mutations
                        for path in (mutation.path, mutation.new_path)
                        if path is not None
                    }
                )
            )
            if touched_paths != context.dispatch.write_paths:
                return WorkerCompletion(
                    outcome=CompletionOutcome.TERMINAL_FAILURE,
                    result_code=RuntimeErrorCode.POLICY_REJECTED.value,
                    session_id=completion.session_id,
                    invocation_id=completion.invocation_id,
                    provider=completion.provider,
                )
            for index, mutation in enumerate(intent.mutations):
                await context.apply_file_mutation(
                    index,
                    mutation.operation,
                    mutation.path,
                    text=mutation.text,
                    new_path=mutation.new_path,
                    mode=mutation.mode,
                )
            return completion
        if telemetry_unsafe:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        sessions = InMemorySessionService()
        session = await sessions.create_session(
            app_name="graphene-workers", user_id=context.dispatch.worker_id
        )
        agent_name = (
            "worker_"
            + canonical_json_sha256(
                (context.dispatch.worker_id, context.dispatch.attempt_id)
            )[:24]
        )
        observation = _Observation(session.id, agent_name)
        agent = LlmAgent(
            name=agent_name,
            description="Returns bounded file mutations for one leased task.",
            model=self.model,
            instruction=(
                "Return only a single JSON object matching this exact schema, with no "
                "markdown fences, prose, or explanation before or after it:\n"
                + describe_output_schema(WorkerIntent)
                + "\nUse ordered create, update, delete, rename, or chmod operations. "
                "Create requires text and mode; update requires text; rename requires "
                "new_path; chmod requires mode. Modes are only 100644 or 100755. Every "
                "path and both rename endpoints must equal the exact write_paths "
                "lease. Do not return explanations, commands, credentials, or hidden "
                "reasoning."
                + (
                    ""
                    if assignment.prior_failure is None
                    else (
                        "\nA prior_failure object is present: your previous attempt at "
                        "this exact task failed. Repair the cause it names within the "
                        "bounded task. The write_paths lease is unchanged — do not widen it, "
                        "do not touch any other file, and do not weaken or delete a "
                        "check to make it pass."
                    )
                )
            ),
            include_contents="none",
            tools=[],
            mode="chat",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(
                max_output_tokens=16_384,
                response_mime_type="application/json",
            ),
            before_model_callback=observation.before_model,
            after_model_callback=observation.after_model,
        )
        runner = Runner(
            app_name="graphene-workers", agent=agent, session_service=sessions
        )
        done = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(context, done))
        output = []
        started = time.monotonic()
        stamped = self.model if isinstance(self.model, StampedGemini) else None
        stamps_before = len(stamped.stamps) if stamped is not None else 0
        # The provider call window is stamped on the wall clock immediately
        # around the model run, for both the fake and the live driver, so the
        # receipt carries a measured execution window rather than a lifetime.
        call_started_at = datetime.now(UTC)
        try:
            async with asyncio.timeout(self.model_timeout_seconds):
                async for event in runner.run_async(
                    user_id=context.dispatch.worker_id,
                    session_id=session.id,
                    new_message=types.Content(
                        role="user", parts=[types.Part.from_text(text=payload)]
                    ),
                    run_config=RunConfig(
                        max_llm_calls=1,
                        telemetry=TelemetryConfig(
                            capture_message_content=ContentCapturingMode.NO_CONTENT
                        ),
                    ),
                ):
                    if event.invocation_id:
                        observation.invocation_ids.add(event.invocation_id)
                    if event.author == agent_name and event.is_final_response():
                        for part in event.content.parts if event.content else ():
                            if part.text and not part.thought:
                                output.append(part.text)
                call_ended_at = datetime.now(UTC)
        except asyncio.CancelledError as error:
            raise RuntimeFailure(RuntimeErrorCode.CANCELLED) from error
        except TimeoutError as error:
            raise RuntimeFailure(RuntimeErrorCode.PROVIDER_TIMEOUT) from error
        except genai_errors.APIError as error:
            if error.code == 429:
                code = RuntimeErrorCode.PROVIDER_RATE_LIMITED
            elif error.code in {408, 504}:
                code = RuntimeErrorCode.PROVIDER_TIMEOUT
            elif error.code >= 500 or error.code in {401, 403}:
                code = RuntimeErrorCode.PROVIDER_UNAVAILABLE
            else:
                code = RuntimeErrorCode.ADAPTER_REJECTED
            raise RuntimeFailure(code) from error
        except (ConnectionError, OSError) as error:
            raise RuntimeFailure(RuntimeErrorCode.PROVIDER_UNAVAILABLE) from error
        except RuntimeFailure:
            raise
        except Exception as error:
            raise RuntimeFailure(
                RuntimeErrorCode.OUTCOME_UNKNOWN, outcome_unknown=True
            ) from error
        finally:
            done.set()
            await heartbeat
            await sessions.delete_session(
                app_name="graphene-workers",
                user_id=context.dispatch.worker_id,
                session_id=session.id,
            )
        if (
            observation.calls != 1
            or len(observation.invocation_ids) != 1
            or len(observation.models) != 1
            or _canonical_model(next(iter(observation.models)))
            != _canonical_model(self.requested_model)
        ):
            raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
        raw_output = "".join(output).strip()
        receipt = self._receipt(
            observation,
            stamped,
            stamps_before,
            payload=payload,
            raw_output=raw_output,
            started=started,
            call_started_at=call_started_at,
            call_ended_at=call_ended_at,
        )

        def rejected(code: RuntimeErrorCode) -> WorkerCompletion:
            # The call was made and billed; its receipt is bound to the
            # failed attempt so spend and provider identity stay auditable.
            return WorkerCompletion(
                outcome=(
                    CompletionOutcome.RETRYABLE_FAILURE
                    if code == RuntimeErrorCode.MODEL_OUTPUT_REJECTED
                    else CompletionOutcome.TERMINAL_FAILURE
                ),
                result_code=code.value,
                session_id=session.id,
                invocation_id=next(iter(observation.invocation_ids)),
                provider=receipt,
            )

        try:
            intent = WorkerIntent.model_validate_json(raw_output)
        except ValueError:
            # Live contact: gemini-3.5-flash occasionally returns a reply that
            # is not a WorkerIntent. That is a retryable model failure, bounded
            # by the policy's retry_limit, not a terminal adapter fault.
            return rejected(RuntimeErrorCode.MODEL_OUTPUT_REJECTED)
        touched_paths = tuple(
            sorted(
                {
                    path
                    for mutation in intent.mutations
                    for path in (mutation.path, mutation.new_path)
                    if path is not None
                }
            )
        )
        if touched_paths != context.dispatch.write_paths:
            return rejected(RuntimeErrorCode.POLICY_REJECTED)
        for index, mutation in enumerate(intent.mutations):
            try:
                await context.apply_file_mutation(
                    index,
                    mutation.operation,
                    mutation.path,
                    text=mutation.text,
                    new_path=mutation.new_path,
                    mode=mutation.mode,
                )
            except RuntimeFailure as error:
                # A mutation the runtime refuses (wrong shape, outside policy,
                # tampered) still came from a billed call: keep the receipt.
                if error.outcome_unknown or error.code not in {
                    RuntimeErrorCode.POLICY_REJECTED,
                    RuntimeErrorCode.ARTIFACT_TAMPERED,
                    RuntimeErrorCode.INPUT_REJECTED,
                }:
                    raise
                return rejected(error.code)
        return WorkerCompletion(
            outcome=CompletionOutcome.COMPLETED,
            result_code="passed",
            session_id=session.id,
            invocation_id=next(iter(observation.invocation_ids)),
            provider=receipt,
        )

    def _receipt(
        self,
        observation: _Observation,
        stamped: StampedGemini | None,
        stamps_before: int,
        *,
        payload: str,
        raw_output: str,
        started: float,
        call_started_at: datetime,
        call_ended_at: datetime,
    ) -> WorkerProviderReceipt:
        usage = observation.usage
        usage_values = (
            None
            if usage is None or self.driver != "gemini_live"
            else (
                usage.prompt_token_count,
                usage.candidates_token_count,
                usage.thoughts_token_count,
                usage.tool_use_prompt_token_count,
                usage.cached_content_token_count,
                usage.total_token_count,
            )
        )
        reported = usage_values is not None and any(
            value is not None for value in usage_values
        )
        counts = usage_values if reported else (None,) * 6
        # Exactly one call was observed above; its provider stamp, if the
        # client recorded one, is the provider's own account of that call.
        new_stamps = stamped.stamps[stamps_before:] if stamped is not None else ()
        stamp = new_stamps[0] if len(new_stamps) == 1 else ProviderStamp()
        return WorkerProviderReceipt(
            driver=self.driver,
            client_version=version("google-genai"),
            requested_model=self.requested_model,
            returned_model=_canonical_model(next(iter(observation.models))),
            credential_mode=self.credential_mode,
            input_bytes=len(payload.encode("utf-8")),
            # An empty reply is still a billed call; the receipt floor is 1.
            output_bytes=max(1, len(raw_output.encode("utf-8"))),
            latency_ms=min(300_000, int((time.monotonic() - started) * 1_000)),
            call_started_at=format_provider_call_timestamp(call_started_at),
            call_ended_at=format_provider_call_timestamp(call_ended_at),
            provider_response_id=stamp.response_id,
            provider_create_time=stamp.create_time,
            provider_response_date=stamp.response_date,
            usage_source="provider_reported" if reported else "unavailable",
            prompt_tokens=counts[0],
            candidate_tokens=counts[1],
            thought_tokens=counts[2],
            tool_tokens=counts[3],
            cached_tokens=counts[4],
            total_tokens=counts[5],
        )


__all__ = [
    "FileMutation",
    "GeminiWorkerAdapter",
    "ProviderStamp",
    "StampedGemini",
    "provider_stamp",
    "WorkerIntent",
]
