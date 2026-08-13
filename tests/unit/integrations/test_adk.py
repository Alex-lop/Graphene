from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types
from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.integrations.adk import ADK_VERSION, AdkRuntimeAdapter
from graphene.lineage.service import ScopedApplicationService
from graphene.lineage.store import SQLiteLineageStore
from graphene.models import (
    EventInput,
    EvidenceKind,
    EvidenceReference,
    GoldenContract,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from pydantic import PrivateAttr

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
BASE_SHA = "a" * 40


class _Artifacts:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], bytes] = {}

    def __call__(
        self,
        kind: EvidenceKind,
        record: Mapping[str, Any],
    ) -> EvidenceReference:
        raw = canonical_json_bytes(record)
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:24]}"
        self.values[(kind.value, artifact_id)] = raw
        return EvidenceReference(kind=kind, id=artifact_id, sha256=digest)

    def source(self, kind: SourceKind, record: Mapping[str, Any]) -> SourceReference:
        raw = canonical_json_bytes(record)
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:24]}"
        self.values[(kind.value, artifact_id)] = raw
        return SourceReference(kind=kind, id=artifact_id, sha256=digest)

    def resolve(self, kind: str, artifact_id: str) -> bytes | None:
        exact = self.values.get((kind, artifact_id))
        if exact is not None:
            return exact
        matches = [
            raw for (_, item_id), raw in self.values.items() if item_id == artifact_id
        ]
        return matches[0] if len(matches) == 1 else None


def _seed(store: SQLiteLineageStore, artifacts: _Artifacts, run_id: str) -> None:
    store.append(
        run_id,
        VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0),
        "adk_run_start_key_001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.RUN_STARTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=artifacts.source(
                SourceKind.LIFECYCLE_REQUEST,
                {"schema_version": 2, "run_id": run_id, "action": "start"},
            ),
            payload={"state": "STARTING"},
        ),
    )


class _TwoTurnLlm(BaseLlm):
    _turns: int = PrivateAttr(default=0)
    _store: SQLiteLineageStore = PrivateAttr()
    _run_id: str = PrivateAttr()

    def bind(self, store: SQLiteLineageStore, run_id: str) -> None:
        self._store = store
        self._run_id = run_id

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse]:
        del stream
        self._turns += 1
        declarations = {
            declaration.name: declaration
            for tool in llm_request.config.tools or []
            for declaration in tool.function_declarations or []
        }
        assert set(declarations) == {
            "search_repo",
            "read_file",
            "open_evidence",
            "write_file",
            "run_fixed_test",
            "request_completion",
        }
        assert declarations["request_completion"].parameters is None
        assert declarations["request_completion"].parameters_json_schema is None

        if self._turns == 1:
            function_call = types.FunctionCall(
                id="adk_read_call_001",
                name="read_file",
                args={"path": "app/auth/limiter.py"},
            )
        elif self._turns == 2:
            assert self._store.tail(self._run_id, 0, 256)[-1].event_type == (
                LineageEventType.TOOL_COMPLETED
            )
            function_call = types.FunctionCall(
                id="adk_completion_call_001",
                name="request_completion",
                args={},
            )
        else:
            raise AssertionError("completion denial must prevent a third model turn")
        yield LlmResponse(
            model_version="fake-runtime-model",
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=function_call)],
            ),
        )


def test_installed_adk_correlates_real_tool_context_and_stops_after_denial(
    tmp_path: Path,
):
    async def scenario() -> None:
        checkout = tmp_path / "fixture"
        shutil.copytree(ROOT / GOLDEN.fixture.root, checkout)
        artifacts = _Artifacts()
        store = SQLiteLineageStore(
            tmp_path / "lineage.sqlite3",
            artifact_resolver=artifacts.resolve,
        )
        run_id = "run_adk_001"
        _seed(store, artifacts, run_id)
        service = ScopedApplicationService(store, artifacts)
        handle = service.create_handle(
            run_id=run_id,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            session_id="session_adk_001",
            invocation_id="invocation_adk_001",
            model_id="fake-runtime-model",
            read_scope=("app/auth/limiter.py",),
            write_scope=(),
            tools=tuple(LineageOperation),
            evidence=(),
            fixed_test_profile="fixture_pytest",
            fixture_policy=GOLDEN.fixture,
            checkout_root=checkout,
        )
        adapter = AdkRuntimeAdapter(service, handle, agent_name="graphene_agent")
        completion_tool = next(
            tool for tool in adapter.tools() if tool.__name__ == "request_completion"
        )
        declaration = FunctionTool(completion_tool)._get_declaration()
        assert declaration.parameters is None
        assert declaration.parameters_json_schema is None

        model = _TwoTurnLlm(model=handle.model_id)
        model.bind(store, run_id)
        agent = LlmAgent(
            name=adapter.agent_name,
            model=model,
            instruction="Read the limiter, then request completion.",
            tools=list(adapter.tools()),
            before_model_callback=adapter.before_model_callback,
            mode="chat",
        )
        sessions = InMemorySessionService()
        await sessions.create_session(
            app_name="graphene",
            user_id="graphene-user",
            session_id=handle.session_id,
        )
        runner = Runner(
            app_name="graphene",
            agent=agent,
            session_service=sessions,
        )
        adk_events = [
            event
            async for event in adapter.run_async(
                runner,
                user_id="graphene-user",
                new_message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Execute the bounded task.")],
                ),
            )
        ]

        assert ADK_VERSION == "2.5.0"
        assert model._turns == 2
        assert adk_events
        assert {event.invocation_id for event in adk_events} == {handle.invocation_id}
        assert handle.needs_human is True
        lineage = store.tail(run_id, 0, 256)
        assert [event.event_type for event in lineage] == [
            LineageEventType.RUN_STARTED,
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.COMPLETION_ATTEMPTED,
            LineageEventType.COMPLETION_DENIED,
        ]
        assert [event.tool_call_id for event in lineage[2:]] == [
            "adk_call_" + sha256_hex(b"adk_read_call_001")[:32],
            "adk_call_" + sha256_hex(b"adk_read_call_001")[:32],
            "adk_call_" + sha256_hex(b"adk_completion_call_001")[:32],
            "adk_call_" + sha256_hex(b"adk_completion_call_001")[:32],
        ]
        assert {event.session_id for event in lineage[1:]} == {handle.session_id}
        assert {event.invocation_id for event in lineage[1:]} == {handle.invocation_id}
        assert {event.model_id for event in lineage[1:]} == {handle.model_id}

    asyncio.run(scenario())
