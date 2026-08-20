from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Mapping
from importlib.metadata import version
from typing import Literal

import google.adk
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.telemetry import ContentCapturingMode, TelemetryConfig
from google.genai import errors as genai_errors, types
from pydantic import Field, model_validator

from ...hashing import canonical_json_bytes, canonical_json_sha256
from ...models import FrozenModel, RepoPath
from ..adk import (
    ADK_VERSION,
    LIVE_GEMINI_MODEL,
    PlannerUnavailable,
    _canonical_model,
    _credential_preflight,
)
from ..models import TaskKind
from ..runtime import (
    CompletionOutcome,
    RuntimeAssignment,
    RuntimeErrorCode,
    RuntimeFailure,
    WorkerCapabilities,
    WorkerCompletion,
    WorkerContext,
    WorkerProviderReceipt,
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


class _Observation:
    def __init__(self, session_id: str, agent_name: str) -> None:
        self.session_id = session_id
        self.agent_name = agent_name
        self.calls = 0
        self.invocation_ids: set[str] = set()
        self.models: set[str] = set()
        self.usage: types.GenerateContentResponseUsageMetadata | None = None

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
            model=model,
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

    async def execute(
        self, context: WorkerContext, assignment: RuntimeAssignment
    ) -> WorkerCompletion:
        if os.environ.get("ADK_TELEMETRY_IGNORE_RUN_CONFIG", "").strip().lower() in {
            "1",
            "true",
        }:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
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
        payload = canonical_json_bytes(
            {
                "contract": assignment.contract,
                "operator_inputs": [
                    {"reference_id": reference_id, "text": text}
                    for reference_id, text in await context.read_supplied_inputs()
                ],
                "sources": sources,
                "title": assignment.title,
                "write_paths": context.dispatch.write_paths,
            }
        ).decode()
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
                "Return only WorkerIntent with ordered create, update, delete, rename, "
                "or chmod operations. Create requires text and mode; update requires "
                "text; rename requires new_path; chmod requires mode. Modes are only "
                "100644 or 100755. Every path and both rename endpoints must equal the "
                "exact write_paths lease. Do not return explanations, commands, "
                "credentials, or hidden reasoning."
            ),
            output_schema=WorkerIntent,
            include_contents="none",
            tools=[],
            mode="chat",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=types.GenerateContentConfig(
                max_output_tokens=16_384
            ),
            after_model_callback=observation.after_model,
        )
        runner = Runner(
            app_name="graphene-workers", agent=agent, session_service=sessions
        )
        done = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(context, done))
        output = []
        started = time.monotonic()
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
        try:
            raw_output = "".join(output).strip()
            intent = WorkerIntent.model_validate_json(raw_output)
        except ValueError as error:
            raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED) from error
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
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        for index, mutation in enumerate(intent.mutations):
            await context.apply_file_mutation(
                index,
                mutation.operation,
                mutation.path,
                text=mutation.text,
                new_path=mutation.new_path,
                mode=mutation.mode,
            )
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
        return WorkerCompletion(
            outcome=CompletionOutcome.COMPLETED,
            result_code="passed",
            session_id=session.id,
            invocation_id=next(iter(observation.invocation_ids)),
            provider=WorkerProviderReceipt(
                driver=self.driver,
                client_version=version("google-genai"),
                requested_model=self.requested_model,
                returned_model=_canonical_model(next(iter(observation.models))),
                credential_mode=self.credential_mode,
                input_bytes=len(payload.encode("utf-8")),
                output_bytes=len(raw_output.encode("utf-8")),
                latency_ms=min(300_000, int((time.monotonic() - started) * 1_000)),
                usage_source="provider_reported" if reported else "unavailable",
                prompt_tokens=counts[0],
                candidate_tokens=counts[1],
                thought_tokens=counts[2],
                tool_tokens=counts[3],
                cached_tokens=counts[4],
                total_tokens=counts[5],
            ),
        )


__all__ = [
    "FileMutation",
    "GeminiWorkerAdapter",
    "WorkerIntent",
]
