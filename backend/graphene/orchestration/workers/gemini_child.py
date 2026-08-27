"""Private length-framed Gemini invocation child; it has no repository API."""

from __future__ import annotations

import asyncio
import os
import struct
import sys
import time
from datetime import UTC, datetime

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.telemetry import ContentCapturingMode, TelemetryConfig
from google.genai import errors as genai_errors, types

from ...hashing import canonical_json_bytes, canonical_json_sha256
from ..adk_planner import LIVE_GEMINI_MODEL, _canonical_model, describe_output_schema
from ..worker_runtime import RuntimeErrorCode, format_provider_call_timestamp
from .gemini import (
    CHILD_MAX_FRAME_BYTES,
    GeminiChildFrame,
    GeminiChildRequest,
    GeminiWorkerAdapter,
    StampedGemini,
    WorkerIntent,
    _Observation,
    child_frame_bytes,
)


def _read_request() -> GeminiChildRequest:
    header = sys.stdin.buffer.read(4)
    if len(header) != 4:
        raise ValueError("missing child request frame")
    size = struct.unpack(">I", header)[0]
    if not 0 < size <= CHILD_MAX_FRAME_BYTES:
        raise ValueError("child request frame exceeds its byte limit")
    payload = sys.stdin.buffer.read(size)
    if len(payload) != size or sys.stdin.buffer.read(1):
        raise ValueError("child request frame is truncated or followed by data")
    request = GeminiChildRequest.model_validate_json(payload)
    if canonical_json_bytes(request.model_dump(mode="json")) != payload:
        raise ValueError("child request frame is not canonical")
    return request


def _write_frame(frame: GeminiChildFrame) -> None:
    sys.stdout.buffer.write(child_frame_bytes(frame))
    sys.stdout.buffer.flush()


def _payload(request: GeminiChildRequest) -> str:
    value: dict[str, object] = {
        "contract": request.contract,
        "operator_inputs": [
            {"reference_id": item.reference_id, "text": item.text}
            for item in request.operator_inputs
        ],
        "sources": [{"path": item.path, "text": item.text} for item in request.sources],
        "title": request.title,
        "write_paths": request.write_paths,
    }
    if request.prior_failure is not None:
        value["prior_failure"] = request.prior_failure.model_dump(mode="json")
    return canonical_json_bytes(value).decode()


def _error_code(error: BaseException) -> RuntimeErrorCode:
    if isinstance(error, genai_errors.APIError):
        if error.code == 429:
            return RuntimeErrorCode.PROVIDER_RATE_LIMITED
        if error.code in {408, 504}:
            return RuntimeErrorCode.PROVIDER_TIMEOUT
        if error.code >= 500 or error.code in {401, 403}:
            return RuntimeErrorCode.PROVIDER_UNAVAILABLE
        return RuntimeErrorCode.ADAPTER_REJECTED
    if isinstance(error, (ConnectionError, OSError)):
        return RuntimeErrorCode.PROVIDER_UNAVAILABLE
    if isinstance(error, TimeoutError):
        return RuntimeErrorCode.PROVIDER_TIMEOUT
    return RuntimeErrorCode.RUNTIME_UNAVAILABLE


async def _run(request: GeminiChildRequest) -> int:
    if request.requested_model != LIVE_GEMINI_MODEL:
        raise ValueError("unsupported child model")
    model = StampedGemini(model=request.requested_model)
    payload = _payload(request)
    sessions = InMemorySessionService()
    session = await sessions.create_session(
        app_name="graphene-workers", user_id=request.worker_id
    )
    agent_name = (
        "worker_" + canonical_json_sha256((request.worker_id, request.attempt_id))[:24]
    )
    observation = _Observation(session.id, agent_name)
    request_sha256 = request.request_sha256()
    dispatched = False

    def provider_dispatched() -> None:
        nonlocal dispatched
        if dispatched:
            return
        if len(observation.invocation_ids) != 1:
            raise RuntimeError("ADK invocation identity unavailable at dispatch")
        dispatched = True
        _write_frame(
            GeminiChildFrame(
                type="provider_dispatched",
                request_sha256=request_sha256,
                sdk_invocation_id=next(iter(observation.invocation_ids)),
                dispatched_at=format_provider_call_timestamp(datetime.now(UTC)),
            )
        )

    model.bind_dispatch_callback(provider_dispatched)
    agent = LlmAgent(
        name=agent_name,
        description="Returns bounded file mutations for one leased task.",
        model=model,
        instruction=(
            "Return only a single JSON object matching this exact schema, with no "
            "markdown fences, prose, or explanation before or after it:\n"
            + describe_output_schema(WorkerIntent)
            + "\nUse ordered create, update, delete, rename, or chmod operations. "
            "Create requires text and mode; update requires text; rename requires "
            "new_path; chmod requires mode. Modes are only 100644 or 100755. Every "
            "path and both rename endpoints must equal the exact write_paths lease. "
            "Do not return explanations, commands, credentials, or hidden reasoning."
            + (
                ""
                if request.prior_failure is None
                else (
                    "\nA prior_failure object is present: Repair the cause it names "
                    "within the bounded task without widening write_paths or weakening "
                    "a check."
                )
            )
        ),
        include_contents="none",
        tools=[],
        mode="chat",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=16_384, response_mime_type="application/json"
        ),
        before_model_callback=observation.before_model,
        after_model_callback=observation.after_model,
    )
    runner = Runner(app_name="graphene-workers", agent=agent, session_service=sessions)
    output: list[str] = []
    started = time.monotonic()
    call_started_at = datetime.now(UTC)
    try:
        async with asyncio.timeout(request.timeout_seconds):
            async for event in runner.run_async(
                user_id=request.worker_id,
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
    except BaseException as error:
        if dispatched:
            _write_frame(
                GeminiChildFrame(
                    type="error",
                    request_sha256=request_sha256,
                    sdk_invocation_id=next(iter(observation.invocation_ids), None),
                    session_id=session.id,
                    result_code=_error_code(error),
                )
            )
            return 0
        raise
    finally:
        await sessions.delete_session(
            app_name="graphene-workers",
            user_id=request.worker_id,
            session_id=session.id,
        )
    if (
        observation.calls != 1
        or len(observation.invocation_ids) != 1
        or len(observation.models) != 1
        or _canonical_model(next(iter(observation.models)))
        != _canonical_model(request.requested_model)
    ):
        code = RuntimeErrorCode.ADAPTER_REJECTED
        intent = None
    else:
        try:
            intent = WorkerIntent.model_validate_json("".join(output).strip())
            code = None
        except ValueError:
            intent = None
            code = RuntimeErrorCode.MODEL_OUTPUT_REJECTED
    receipt = None
    if code != RuntimeErrorCode.ADAPTER_REJECTED:
        adapter = GeminiWorkerAdapter(
            worker_id=request.worker_id,
            model=model,
            driver="gemini_live",
            credential_mode=request.credential_mode,
            model_timeout_seconds=request.timeout_seconds,
        )
        receipt = adapter._receipt(
            observation,
            model,
            0,
            payload=payload,
            raw_output="".join(output).strip(),
            started=started,
            call_started_at=call_started_at,
            call_ended_at=call_ended_at,
        )
    if code is not None:
        _write_frame(
            GeminiChildFrame(
                type="error",
                request_sha256=request_sha256,
                sdk_invocation_id=next(iter(observation.invocation_ids), None),
                session_id=session.id,
                provider=(
                    receipt if code == RuntimeErrorCode.MODEL_OUTPUT_REJECTED else None
                ),
                result_code=code,
            )
        )
        return 0
    assert intent is not None
    assert receipt is not None
    _write_frame(
        GeminiChildFrame(
            type="result",
            request_sha256=request_sha256,
            sdk_invocation_id=next(iter(observation.invocation_ids)),
            session_id=session.id,
            intent=intent,
            provider=receipt,
        )
    )
    return 0


def main() -> int:
    try:
        request = _read_request()
        if os.environ.get("ADK_TELEMETRY_IGNORE_RUN_CONFIG", "").strip().lower() in {
            "1",
            "true",
        }:
            return 2
        return asyncio.run(_run(request))
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
