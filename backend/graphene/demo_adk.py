from __future__ import annotations

import asyncio
import logging
import os
import warnings
from collections.abc import AsyncGenerator
from contextlib import contextmanager
from typing import Any, Literal

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from .integrations.adk import ADK_VERSION, AdkRuntimeAdapter
from .lineage.service import RuntimeHandle, ScopedApplicationService
from .models import Identifier, LineageOperation

ADK_FAKE_PROOF_LABEL = (
    "REAL ADK RUNNER + DETERMINISTIC FAKE MODEL — "
    "NOT GEMINI OR INDEPENDENT-AGENT PROOF"
)
_CREDENTIAL_VARIABLES = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GCLOUD_PROJECT",
    "GCP_PROJECT",
)
_ARGUMENTS = {
    LineageOperation.SEARCH_REPO: {"query": str},
    LineageOperation.READ_FILE: {"path": str},
    LineageOperation.OPEN_EVIDENCE: {"evidence_id": str},
    LineageOperation.WRITE_FILE: {"path": str, "content": str},
    LineageOperation.RUN_FIXED_TEST: {},
    LineageOperation.REQUEST_COMPLETION: {},
}


class AdkFakeError(RuntimeError):
    pass


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdkFakeToolCall(_Frozen):
    call_id: Identifier
    operation: LineageOperation
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def arguments_match_operation(self) -> AdkFakeToolCall:
        expected = _ARGUMENTS[self.operation]
        if set(self.arguments) != set(expected) or any(
            type(self.arguments[name]) is not value_type
            for name, value_type in expected.items()
        ):
            raise ValueError("fake ADK call arguments do not match the bounded tool")
        return self


class AdkFakeExecution(_Frozen):
    proof_label: Literal[ADK_FAKE_PROOF_LABEL] = ADK_FAKE_PROOF_LABEL
    role: Literal["source", "consumer"]
    framework: Literal["google_adk"] = "google_adk"
    framework_version: Literal[ADK_VERSION] = ADK_VERSION
    run_id: Identifier
    session_id: Identifier
    invocation_id: Identifier
    model_id: Identifier
    agent_name: Identifier
    fake_model_turn_count: int = Field(ge=1)
    tool_call_count: int = Field(ge=1)
    adk_event_count: int = Field(ge=1)
    external_model_dispatch_count: Literal[0] = 0
    credential_environment_unset: Literal[True] = True


class _DeterministicFakeLlm(BaseLlm):
    _calls: tuple[AdkFakeToolCall, ...] = PrivateAttr()
    _turns: int = PrivateAttr(default=0)

    def bind(self, calls: tuple[AdkFakeToolCall, ...]) -> None:
        self._calls = calls

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse]:
        del stream
        if any(name in os.environ for name in _CREDENTIAL_VARIABLES):
            raise AdkFakeError("Google credential environment was not isolated")
        declarations = {
            declaration.name
            for tool in llm_request.config.tools or []
            for declaration in tool.function_declarations or []
        }
        if declarations != {operation.value for operation in LineageOperation}:
            raise AdkFakeError("ADK bounded tool declarations changed")
        if self._turns >= len(self._calls):
            raise AdkFakeError("deterministic fake model exhausted its frozen calls")
        call = self._calls[self._turns]
        self._turns += 1
        yield LlmResponse(
            model_version=self.model,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id=call.call_id,
                            name=call.operation.value,
                            args=dict(call.arguments),
                        )
                    )
                ],
            ),
        )

    @property
    def turns(self) -> int:
        return self._turns


@contextmanager
def _credentials_unset():
    # ponytail: process-wide env isolation assumes one demo dispatch at a time.
    retained = {
        name: os.environ.pop(name)
        for name in _CREDENTIAL_VARIABLES
        if name in os.environ
    }
    try:
        yield
    finally:
        for name in _CREDENTIAL_VARIABLES:
            os.environ.pop(name, None)
        os.environ.update(retained)


def _validate_plan(calls: tuple[AdkFakeToolCall, ...]) -> None:
    if (
        not calls
        or calls[-1].operation != LineageOperation.REQUEST_COMPLETION
        or any(
            call.operation == LineageOperation.REQUEST_COMPLETION
            for call in calls[:-1]
        )
        or len({call.call_id for call in calls}) != len(calls)
    ):
        raise AdkFakeError(
            "ADK fake plan requires unique calls and one final completion request"
        )


async def _execute(
    service: ScopedApplicationService,
    handle: RuntimeHandle,
    *,
    role: Literal["source", "consumer"],
    calls: tuple[AdkFakeToolCall, ...],
) -> AdkFakeExecution:
    agent_name = f"graphene_adk_fake_{role}"
    adapter = AdkRuntimeAdapter(service, handle, agent_name=agent_name)
    model = _DeterministicFakeLlm(model=handle.model_id)
    model.bind(calls)
    agent = LlmAgent(
        name=agent_name,
        model=model,
        instruction=(
            "Execute only the frozen bounded tool calls. This is a deterministic "
            "fake model, not Gemini."
        ),
        tools=list(adapter.tools()),
        before_model_callback=adapter.before_model_callback,
        mode="chat",
    )
    sessions = InMemorySessionService()
    user_id = f"graphene-{role}"
    await sessions.create_session(
        app_name="graphene-adk-fake",
        user_id=user_id,
        session_id=handle.session_id,
    )
    runner = Runner(
        app_name="graphene-adk-fake",
        agent=agent,
        session_service=sessions,
    )
    events = [
        event
        async for event in adapter.run_async(
            runner,
            user_id=user_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text="Execute the frozen bounded plan.")],
            ),
        )
    ]
    if (
        model.turns != len(calls)
        or not handle.needs_human
        or not events
        or {event.invocation_id for event in events} != {handle.invocation_id}
    ):
        raise AdkFakeError("real ADK Runner did not complete the frozen tool lifecycle")
    return AdkFakeExecution(
        role=role,
        run_id=handle.run_id,
        session_id=handle.session_id,
        invocation_id=handle.invocation_id,
        model_id=handle.model_id,
        agent_name=agent_name,
        fake_model_turn_count=model.turns,
        tool_call_count=len(calls),
        adk_event_count=len(events),
    )


def run_adk_fake(
    service: ScopedApplicationService,
    handle: RuntimeHandle,
    *,
    role: Literal["source", "consumer"],
    calls: tuple[AdkFakeToolCall, ...],
) -> AdkFakeExecution:
    """Run frozen calls through real ADK sessions, Runner, and Graphene tools."""

    if not isinstance(service, ScopedApplicationService) or not isinstance(
        handle, RuntimeHandle
    ):
        raise TypeError("ADK fake execution requires the scoped Graphene runtime")
    calls = tuple(
        call
        if isinstance(call, AdkFakeToolCall)
        else AdkFakeToolCall.model_validate(call)
        for call in calls
    )
    _validate_plan(calls)
    metrics = logging.getLogger("google_adk.google.adk.telemetry._metrics")
    previous_level = metrics.level
    with _credentials_unset(), warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"\[EXPERIMENTAL\] feature .*JSON_SCHEMA_FOR_FUNC_DECL.*",
            category=UserWarning,
        )
        metrics.setLevel(logging.ERROR)
        try:
            return asyncio.run(
                _execute(service, handle, role=role, calls=calls)
            )
        finally:
            metrics.setLevel(previous_level)


def validate_distinct_adk_fake_runtimes(
    source: AdkFakeExecution,
    consumer: AdkFakeExecution,
) -> None:
    if (
        source.role != "source"
        or consumer.role != "consumer"
        or len(
            {
                source.run_id,
                source.session_id,
                source.invocation_id,
                source.agent_name,
                consumer.run_id,
                consumer.session_id,
                consumer.invocation_id,
                consumer.agent_name,
            }
        )
        != 8
    ):
        raise AdkFakeError("source and consumer ADK identities are not distinct")


__all__ = [
    "ADK_FAKE_PROOF_LABEL",
    "AdkFakeError",
    "AdkFakeExecution",
    "AdkFakeToolCall",
    "run_adk_fake",
    "validate_distinct_adk_fake_runtimes",
]
