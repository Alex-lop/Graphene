from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from graphene.hashing import sha256_hex
from graphene.integrations.mcp import create_mcp_server
from graphene.lineage import SQLiteArtifactStore, SQLiteLineageStore
from graphene.lineage.service import EvidenceItem, ScopedApplicationService
from graphene.models import (
    EventInput,
    EvidenceKind,
    GoldenContract,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from mcp import Client, MCPError

ROOT = Path(__file__).parents[3]
GOLDEN = GoldenContract.model_validate_json(
    (ROOT / "contracts/golden_path.json").read_text()
)
BASE_SHA = "a" * 40

_SCHEMAS = {
    "search_repo": {"query"},
    "read_file": {"path"},
    "open_evidence": {"evidence_id"},
    "write_file": {"path", "content"},
    "run_fixed_test": set(),
    "request_completion": set(),
}


def _runtime(tmp_path: Path, run_id: str):
    checkout = tmp_path / "fixture"
    shutil.copytree(ROOT / GOLDEN.fixture.root, checkout)
    path = tmp_path / "lineage.sqlite3"
    artifacts = SQLiteArtifactStore(path)
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    source_artifact = artifacts(
        EvidenceKind.OPERATOR_REQUEST,
        {"schema_version": 2, "run_id": run_id, "action": "start"},
    )
    store.append(
        run_id,
        VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0),
        f"{run_id}_start_key",
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
            source_ref=SourceReference(
                kind=SourceKind.LIFECYCLE_REQUEST,
                id=source_artifact.id,
                sha256=source_artifact.sha256,
            ),
            payload={"state": "STARTING"},
        ),
    )
    evidence_content = "approved memory evidence"
    evidence_ref = artifacts(
        EvidenceKind.EVIDENCE_BLOB,
        {"schema_version": 2, "content": evidence_content},
    )
    service = ScopedApplicationService(store, artifacts)
    handle = service.create_handle(
        run_id=run_id,
        repo_id="graphene-demo",
        base_sha=BASE_SHA,
        agent_profile_id="auth-maintainer@1",
        policy_revision=1,
        session_id=f"session_{run_id}",
        invocation_id=f"invocation_{run_id}",
        model_id="mcp-runtime-model",
        read_scope=tuple(
            sorted(
                set(GOLDEN.fixture.tracked_paths) | set(GOLDEN.fixture.mutable_paths)
            )
        ),
        write_scope=GOLDEN.fixture.mutable_paths,
        tools=tuple(LineageOperation),
        evidence=(
            EvidenceItem(
                reference=evidence_ref,
                content=evidence_content,
                content_sha256=sha256_hex(evidence_content.encode()),
            ),
        ),
        fixed_test_profile="fixture_pytest",
        fixture_policy=GOLDEN.fixture,
        checkout_root=checkout,
    )
    return service, handle, store, evidence_ref


def test_official_client_sees_six_strict_tools_and_common_service_events(
    tmp_path: Path,
):
    async def scenario() -> None:
        service, handle, store, evidence_ref = _runtime(tmp_path, "run_mcp_001")
        server = create_mcp_server(service, handle)

        async with Client(server) as client:
            assert client.protocol_version == "2026-07-28"
            listed = await client.list_tools()
            assert [tool.name for tool in listed.tools] == list(_SCHEMAS)
            for tool in listed.tools:
                schema = tool.input_schema
                expected = _SCHEMAS[tool.name]
                assert schema["type"] == "object"
                assert schema["additionalProperties"] is False
                assert set(schema["properties"]) == expected
                assert set(schema.get("required", ())) == expected

            assert (await client.list_resources()).resources == []
            assert (await client.list_resource_templates()).resource_templates == []
            assert (await client.list_prompts()).prompts == []
            assert not any(
                word in tool.name
                for tool in listed.tools
                for word in ("human", "approve", "promote", "feedback")
            )

            search = await client.call_tool(
                "search_repo",
                {"query": "MAX_ATTEMPTS"},
            )
            read = await client.call_tool(
                "read_file",
                {"path": "app/auth/limiter.py"},
            )
            opened = await client.call_tool(
                "open_evidence",
                {"evidence_id": evidence_ref.id},
            )
            original = read.structured_content["content"]
            write = await client.call_tool(
                "write_file",
                {
                    "path": "app/auth/limiter.py",
                    "content": original + "\n# MCP_WRITE_CANARY\n",
                },
            )
            tested = await client.call_tool("run_fixed_test")
            completion = await client.call_tool("request_completion")

            assert all(
                result.is_error is False
                for result in (search, read, opened, write, tested, completion)
            )
            assert search.structured_content["paths"] == [
                "app/auth/limiter.py",
                "tests/test_rate_limit.py",
            ]
            assert "MAX_ATTEMPTS" in original
            assert opened.structured_content["content"] == "approved memory evidence"
            assert write.structured_content["state"] == "EDITED"
            assert tested.structured_content["passed"] is True
            assert tested.structured_content["bound_paths"] == ["app/auth/limiter.py"]
            assert completion.structured_content == {
                "status": "denied",
                "reason_code": "human_promotion_required",
                "state": "NEEDS_HUMAN",
            }

            committed = handle.head.event_count
            late = await client.call_tool(
                "read_file",
                {"path": "app/auth/limiter.py"},
            )
            assert late.is_error is True
            assert "Graphene tool request failed" in str(late.model_dump(mode="json"))
            assert store.verify(handle.run_id).event_count == committed

        events = store.tail(handle.run_id, 0, 256)
        assert [event.event_type for event in events] == [
            LineageEventType.RUN_STARTED,
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.COMPLETION_ATTEMPTED,
            LineageEventType.COMPLETION_DENIED,
        ]
        assert events[1].authority == LineageAuthority.MCP_ADAPTER
        assert events[1].source_ref.kind == SourceKind.MCP_REQUEST_RECEIPT
        calls = [event.tool_call_id for event in events[2:]]
        assert all(value and value.startswith("mcp_call_") for value in calls)
        assert calls[::2] == calls[1::2]
        assert len(set(calls[::2])) == 6
        assert {event.session_id for event in events[1:]} == {handle.session_id}
        assert {event.invocation_id for event in events[1:]} == {handle.invocation_id}
        assert {event.model_id for event in events[1:]} == {handle.model_id}
        public = json.dumps([event.model_dump(mode="json") for event in events])
        assert "MCP_WRITE_CANARY" not in public
        assert "approved memory evidence" not in public
        assert store.verify(handle.run_id) == handle.head
        assert handle.needs_human is True

    asyncio.run(scenario())


def test_forged_arguments_and_errors_are_rejected_without_identity_leaks(
    tmp_path: Path,
):
    async def scenario() -> None:
        service, handle, store, _ = _runtime(tmp_path, "run_mcp_002")
        server = create_mcp_server(service, handle)
        before = handle.head.event_count
        canary = "TOKEN_SOURCE_CANARY_93f8"

        async with Client(server) as client:
            for forged in (
                "authority",
                "order",
                "repo_id",
                "agent_profile_id",
                "digest",
                "extra",
            ):
                with pytest.raises(MCPError) as caught:
                    await client.call_tool(
                        "read_file",
                        {"path": "app/auth/limiter.py", forged: canary},
                    )
                assert str(caught.value) == "Invalid tool request"
                assert canary not in str(caught.value)
                assert forged not in str(caught.value)

            with pytest.raises(MCPError, match="Invalid tool request"):
                await client.call_tool("read_file", {"path": {"secret": canary}})
            for human_tool in ("approve_promotion", "record_human_feedback"):
                with pytest.raises(MCPError) as caught:
                    await client.call_tool(human_tool, {"token": canary})
                assert str(caught.value) == "Invalid tool request"

            assert store.verify(handle.run_id).event_count == before

            denied = await client.call_tool("read_file", {"path": canary})
            assert denied.is_error is True
            rendered = str(denied.model_dump(mode="json"))
            assert "Graphene tool request failed" in rendered
            assert canary not in rendered

        denial = store.tail(handle.run_id, before, 256)
        assert [event.event_type for event in denial] == [
            LineageEventType.SCOPE_DENIED,
        ]
        assert canary not in json.dumps(denial[-1].model_dump(mode="json"))

    asyncio.run(scenario())
