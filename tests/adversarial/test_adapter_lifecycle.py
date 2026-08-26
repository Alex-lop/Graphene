from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.genai import types
from graphene.bootstrap import bootstrap_local_run
from graphene.integrations.adk_adapter import AdkRuntimeAdapter
from graphene.integrations.mcp import create_mcp_server
from graphene.lineage.lineage_reducer import reduce_events
from graphene.lineage.service import (
    RuntimeIdentityError,
    RuntimeIntegrityError,
    RuntimeTerminalError,
    ScopedApplicationService,
    ToolCallIdentity,
)
from graphene.core_models import (
    LineageAuthority,
    LineageEventType,
    LineageRunState,
    SourceKind,
    VerifiedHead,
)
from mcp import Client

ROOT = Path(__file__).parents[2]


class _MismatchedModel(BaseLlm):
    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse]:
        del llm_request, stream
        yield LlmResponse(
            model_version="returned-model-v2",
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="bounded result")],
            ),
        )


class _MatchingModel(BaseLlm):
    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse]:
        del llm_request, stream
        yield LlmResponse(
            model_version="graphene-local-scripted",
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="bounded result")],
            ),
        )


class _FailingModel(BaseLlm):
    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse]:
        del llm_request, stream
        raise RuntimeError("synthetic model failure")
        yield  # pragma: no cover - makes this an async generator


def _call(handle, call_id: str, adapter_kind: str = "adk") -> ToolCallIdentity:
    return ToolCallIdentity(
        session_id=handle.session_id,
        invocation_id=handle.invocation_id,
        model_id=handle.model_id,
        tool_call_id=call_id,
        agent_name=f"graphene_{adapter_kind}",
        adapter_kind=adapter_kind,
    )


def _reopen(run):
    service = ScopedApplicationService(run.store, run.artifacts)
    handle = service.create_handle(
        run_id=run.run_id,
        repo_id=run.handle.repo_id,
        base_sha=run.handle.base_sha,
        agent_profile_id=run.handle.agent_profile_id,
        policy_revision=run.handle.policy_revision,
        session_id=run.handle.session_id,
        invocation_id=run.handle.invocation_id,
        model_id=run.handle.model_id,
        read_scope=run.handle.read_scope,
        write_scope=run.handle.write_scope,
        tools=run.handle.tools,
        evidence=run.handle.evidence,
        fixed_test_profile=run.handle.fixed_test_profile,
        fixture_policy=run.handle.fixture_policy,
        checkout_root=run.handle.checkout_root,
    )
    return service, handle


def _bootstrap(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    return bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )


async def _run_adk(run, model: BaseLlm):
    adapter = AdkRuntimeAdapter(
        run.service,
        run.handle,
        agent_name="graphene_agent",
    )
    agent = LlmAgent(
        name=adapter.agent_name,
        model=model,
        instruction="Return the bounded result.",
        tools=list(adapter.tools()),
        before_model_callback=adapter.before_model_callback,
        mode="chat",
    )
    sessions = InMemorySessionService()
    await sessions.create_session(
        app_name="graphene",
        user_id="graphene-user",
        session_id=run.session_id,
    )
    runner = Runner(
        app_name="graphene",
        agent=agent,
        session_service=sessions,
    )
    observed = []
    error = None
    try:
        observed = [
            event
            async for event in adapter.run_async(
                runner,
                user_id="graphene-user",
                new_message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Execute now.")],
                ),
            )
        ]
    except Exception as caught:  # noqa: BLE001 - lifecycle failure is under test
        error = caught
    return observed, error


def test_needs_human_is_terminal_for_a_fresh_service_after_restart(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    run = bootstrap_local_run(
        runtime / "lineage.sqlite3",
        task_id="baseline_max_attempts",
        profile_id="platform-maintainer@1",
        repository_root=ROOT,
    )
    run.service.ensure_invocation_started(
        run.handle,
        session_id=run.handle.session_id,
        invocation_id=run.handle.invocation_id,
        model_id=run.handle.model_id,
        framework_version="2.5.0",
    )
    run.service.request_completion(
        run.handle,
        _call(run.handle, "completion_call_before_restart_001"),
    )
    terminal = reduce_events(run.store.tail(run.run_id, 0, 256))
    assert terminal.state == LineageRunState.NEEDS_HUMAN

    service, handle = _reopen(run)
    try:
        service.read_file(
            handle,
            _call(handle, "forbidden_read_after_restart_001"),
            path="app/auth/limiter.py",
        )
    except RuntimeTerminalError:
        return

    verified = run.store.verify(run.run_id)
    assert isinstance(verified, VerifiedHead)
    forged = reduce_events(run.store.tail(run.run_id, 0, verified.seq))
    assert forged.state == LineageRunState.NEEDS_HUMAN
    pytest.fail(
        "fresh service accepted a post-terminal event that verifies and reduces"
    )


def test_mcp_completion_never_claims_adk_provenance(tmp_path):
    run = _bootstrap(tmp_path)

    async def invoke():
        async with Client(create_mcp_server(run.service, run.handle)) as client:
            return await client.call_tool("request_completion")

    result = asyncio.run(invoke())
    if result.is_error:
        return
    events = run.store.tail(run.run_id, 0, 256)
    attempted = next(
        event
        for event in events
        if event.event_type == LineageEventType.COMPLETION_ATTEMPTED
    )

    assert attempted.authority != LineageAuthority.ADK_ADAPTER
    assert attempted.source_ref.kind != SourceKind.ADK_EVENT_RECEIPT


def test_adk_returned_model_mismatch_fails_without_persisting_provider_value(tmp_path):
    run = _bootstrap(tmp_path)
    observed, error = asyncio.run(_run_adk(run, _MismatchedModel(model=run.model_id)))

    assert observed == []
    assert isinstance(error, RuntimeIdentityError)
    assert "returned-model-v2" not in str(error)
    lineage = run.store.tail(run.run_id, 0, 256)
    assert lineage[-1].event_type == LineageEventType.INVOCATION_FAILED
    assert {event.model_id for event in lineage[1:]} == {run.model_id}


def test_adk_records_successful_invocation_completion(tmp_path):
    run = _bootstrap(tmp_path)
    _, error = asyncio.run(_run_adk(run, _MatchingModel(model=run.model_id)))

    assert error is None
    lineage = run.store.tail(run.run_id, 0, 256)
    completed = [
        event
        for event in lineage
        if event.event_type == LineageEventType.INVOCATION_COMPLETED
    ]
    assert len(completed) == 1
    assert completed[0].model_id == run.model_id


def test_adk_records_failed_invocation_before_propagating_failure(tmp_path):
    run = _bootstrap(tmp_path)
    _, error = asyncio.run(_run_adk(run, _FailingModel(model=run.model_id)))

    assert error is not None
    lineage = run.store.tail(run.run_id, 0, 256)
    assert lineage[-1].event_type == LineageEventType.INVOCATION_FAILED
    assert run.store.verify(run.run_id) == run.handle.head


def test_invocation_start_is_committed_before_runner_dispatch(tmp_path):
    run = _bootstrap(tmp_path)
    observed = []

    class DispatchProbe:
        async def run_async(self, **kwargs):
            del kwargs
            observed.append(run.store.tail(run.run_id, 0, 256)[-1].event_type)
            if False:
                yield SimpleNamespace()

    adapter = AdkRuntimeAdapter(
        run.service,
        run.handle,
        agent_name="graphene_agent",
    )

    async def dispatch():
        return [
            event
            async for event in adapter.run_async(
                DispatchProbe(),
                user_id="graphene-user",
                new_message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Execute now.")],
                ),
            )
        ]

    assert asyncio.run(dispatch()) == []
    assert observed == [LineageEventType.INVOCATION_STARTED]


def test_duplicate_call_id_is_consumed_across_adapters_and_restart(tmp_path):
    run = _bootstrap(tmp_path)
    run.service.ensure_invocation_started(
        run.handle,
        session_id=run.handle.session_id,
        invocation_id=run.handle.invocation_id,
        model_id=run.handle.model_id,
        framework_version="2.5.0",
    )
    call_id = "shared_adapter_call_001"
    run.service.read_file(
        run.handle,
        _call(run.handle, call_id, "adk"),
        path="app/auth/limiter.py",
    )
    before = run.store.verify(run.run_id)

    with pytest.raises(RuntimeIdentityError, match="already consumed"):
        run.service.read_file(
            run.handle,
            _call(run.handle, call_id, "mcp"),
            path="app/auth/limiter.py",
        )
    with pytest.raises(RuntimeIntegrityError, match="unfinished durable dispatch"):
        _reopen(run)
    assert run.store.verify(run.run_id) == before
