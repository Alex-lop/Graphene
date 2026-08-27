"""The durable /graphene MCP contract, exercised in process."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest
from mcp import Client, MCPError

import graphene.orchestration.supervisor as supervisor_module
from graphene.integrations.mission_mcp import (
    GOAL_PROMPT,
    TOOL_ARGUMENTS,
    create_mission_mcp_server,
)
from graphene.orchestration.scripted import load_scenario, scripted_supported
from graphene.orchestration.supervisor import (
    SupervisorProcess,
    SupervisorRequest,
    _live,
    _state,
)

ROOT = Path(__file__).parents[3]
TOOLS = [
    "start_goal",
    "plan_goal",
    "get_digest",
    "approve_plan",
    "approve_result",
    "reject_result",
    "mission_status",
    "why",
    "mission_summary",
]
MUTATING_TOOLS = {
    "start_goal",
    "plan_goal",
    "approve_plan",
    "approve_result",
    "reject_result",
}
OPEN_WORLD_TOOLS = {"start_goal", "plan_goal", "approve_plan"}


def _repository(path: Path) -> Path:
    path.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "README.md").write_text("# Target\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True, env=env)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "fixture"], check=True, env=env
    )
    return path


def _stop_owned_supervisors(state: Path) -> None:
    for path in (state / "missions").glob("*/supervisor-process.json"):
        try:
            record = SupervisorProcess.model_validate_json(path.read_bytes())
        except (OSError, ValueError):
            continue
        if not _live(record):
            continue
        os.killpg(record.pgid, signal.SIGTERM)
        deadline = time.monotonic() + 2
        while _live(record) and time.monotonic() < deadline:
            time.sleep(0.01)
        if _live(record):
            os.killpg(record.pgid, signal.SIGKILL)


@pytest.fixture
def private_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    try:
        yield state
    finally:
        _stop_owned_supervisors(state)


def test_server_lists_durable_tools_prompt_strict_schemas_and_annotations() -> None:
    async def scenario() -> None:
        async with Client(create_mission_mcp_server()) as client:
            listed = await client.list_tools()
            assert [tool.name for tool in listed.tools] == TOOLS
            for tool in listed.tools:
                required, optional = TOOL_ARGUMENTS[tool.name]
                schema = tool.input_schema
                assert (
                    schema["type"] == "object"
                    and schema["additionalProperties"] is False
                )
                assert set(schema["properties"]) == required | optional
                assert set(schema.get("required", ())) == required
                assert all(
                    schema["properties"][key]["type"] == "string"
                    for key in schema["properties"]
                )
                assert tool.annotations is not None
                assert tool.annotations.read_only_hint is (
                    tool.name not in MUTATING_TOOLS
                )
                assert tool.annotations.destructive_hint is False
                assert tool.annotations.idempotent_hint is True
                assert tool.annotations.open_world_hint is (
                    tool.name in OPEN_WORLD_TOOLS
                )

            prompts = (await client.list_prompts()).prompts
            assert [prompt.name for prompt in prompts] == ["goal"]
            assert [argument.name for argument in prompts[0].arguments] == ["goal"]
            rendered = await client.get_prompt("goal", {"goal": "Add a status export"})
            text = rendered.messages[0].content.text
            assert "Add a status export" in text
            assert "start_goal" in text and "detached supervisor" in text
            assert "plan_review" in text and "result_review" in text
            assert "approve_result" in text and "reject_result" in text
            assert text == GOAL_PROMPT.format(goal="Add a status export")

    asyncio.run(scenario())


def test_forged_or_non_string_arguments_are_rejected_before_dispatch() -> None:
    async def scenario() -> None:
        async with Client(create_mission_mcp_server()) as client:
            for name, arguments in (
                (
                    "start_goal",
                    {"repo": "/tmp/repo", "goal": "x", "success_criterion": "done"},
                ),
                (
                    "start_goal",
                    {
                        "repo": "/tmp/repo",
                        "goal": "x",
                        "request_id": "request-x",
                        "success_criterion": "done",
                        "extra": "y",
                    },
                ),
                (
                    "start_goal",
                    {
                        "repo": "/tmp/repo",
                        "goal": "x",
                        "request_id": 7,
                        "success_criterion": "done",
                    },
                ),
                ("get_digest", {}),
                ("get_digest", {"mission_id": "x", "extra": "y"}),
                ("approve_plan", {"mission_id": "x"}),
                ("approve_plan", {"mission_id": "x", "digest": 7}),
                ("approve_result", {"mission_id": "x", "bundle_id": "y"}),
                (
                    "reject_result",
                    {"mission_id": "x", "bundle_id": "y", "rationale": 7},
                ),
                ("nonexistent", {"mission_id": "x"}),
            ):
                with pytest.raises(MCPError):
                    await client.call_tool(name, arguments)

    asyncio.run(scenario())


def test_result_review_requires_a_bounded_public_rationale() -> None:
    async def scenario() -> None:
        async with Client(create_mission_mcp_server()) as client:
            result = await client.call_tool(
                "approve_result",
                {
                    "mission_id": "mission-result-review",
                    "bundle_id": "final_result_" + "a" * 32,
                    "rationale": "x" * 281,
                },
            )
            assert result.is_error is True
            assert "rationale" in result.content[0].text

    asyncio.run(scenario())


def test_gemini_start_requires_exactly_one_string_encoded_criteria_form(
    private_state: Path, tmp_path: Path
) -> None:
    repository = _repository(tmp_path / "target")
    from graphene.cli.mission import initialize

    initialize(repository)
    common = {
        "repo": str(repository),
        "goal": load_scenario().goal,
        "request_id": "request-criteria-choice-1",
        "driver": "gemini-adk",
    }

    async def scenario() -> None:
        async with Client(create_mission_mcp_server()) as client:
            missing = await client.call_tool("start_goal", common)
            assert missing.is_error is True
            assert "explicit success criteria" in missing.content[0].text

            both = await client.call_tool(
                "start_goal",
                {
                    **common,
                    "success_criterion": load_scenario().success_criteria[0],
                    "success_criteria_json": json.dumps(
                        load_scenario().success_criteria
                    ),
                },
            )
            assert both.is_error is True
            assert "exactly one" in both.content[0].text

    asyncio.run(scenario())


def test_one_shot_status_projection_closes_its_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphene.cli import mission

    closed = []

    class Store:
        def close(self) -> None:
            closed.append(True)

    class Snapshot:
        def model_dump(self, *, mode: str) -> dict[str, str]:
            assert mode == "json"
            return {"mission_id": "mission-status-close"}

    class Projection:
        store = Store()

        def snapshot(self, mission_id: str) -> Snapshot:
            assert mission_id == "mission-status-close"
            return Snapshot()

    monkeypatch.setattr(mission, "_projection", lambda _mission_id: Projection())
    assert mission._status_value("mission-status-close") == {
        "mission_id": "mission-status-close"
    }
    assert closed == [True]


def test_fresh_session_reports_durable_preplan_request_truth(
    private_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path / "target")
    from graphene.cli.mission import initialize

    initialize(repository)

    def accept_without_planning(runtime: Path, request, generation: int) -> None:
        _state(runtime, request, "accepted", generation)

    monkeypatch.setattr(supervisor_module, "_spawn", accept_without_planning)
    request = {
        "repo": str(repository),
        "goal": "Keep a durable pre-plan truth",
        "request_id": "request-preplan-fresh-session",
        "success_criterion": "The request survives controller restart",
        "driver": "gemini-adk",
        "authorization_mode": "review_required",
        "finalization_mode": "review_required",
    }

    async def scenario() -> None:
        async with Client(create_mission_mcp_server()) as first:
            result = await first.call_tool("start_goal", request)
            assert result.is_error is False, result.content
            accepted = result.structured_content
            mission_id = accepted["mission_id"]
            assert accepted["requested_authorization_mode"] == "review_required"
            assert accepted["effective_authorization_mode"] is None
            assert accepted["authorization_mode"] is None
            assert accepted["finalization_mode"] == "review_required"

        async with Client(create_mission_mcp_server()) as fresh:
            status = await fresh.call_tool(
                "mission_status", {"mission_id": mission_id}
            )
            assert status.is_error is False, status.content
            value = status.structured_content
            assert value["goal"] == request["goal"]
            assert value["status"] == "accepted"
            assert value["requested_authorization_mode"] == "review_required"
            assert value["effective_authorization_mode"] is None
            assert value["finalization_mode"] == "review_required"
            digest = await fresh.call_tool("get_digest", {"mission_id": mission_id})
            assert digest.is_error is False, digest.content
            assert (
                digest.structured_content["requested_authorization_mode"]
                == "review_required"
            )
            assert digest.structured_content["effective_authorization_mode"] is None
            assert digest.structured_content["finalization_mode"] == "review_required"

    asyncio.run(scenario())


def test_start_returns_promptly_is_idempotent_and_review_approval_is_nonblocking(
    private_state: Path, tmp_path: Path
) -> None:
    repository = _repository(tmp_path / "target")
    from graphene.cli.mission import initialize

    initialize(repository)
    request = {
        "repo": str(repository),
        "goal": load_scenario().goal,
        "request_id": "request-mcp-review-1",
        "success_criterion": load_scenario().success_criteria[0],
        "driver": "scripted-local",
        "authorization_mode": "review_required",
        "finalization_mode": "review_required",
    }

    async def poll(
        client: Client, mission_id: str, expected: set[str], timeout: float = 20
    ) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = await client.call_tool(
                "mission_status", {"mission_id": mission_id}
            )
            assert result.is_error is False, result.content
            status = result.structured_content
            if status["status"] in expected:
                return status
            await asyncio.sleep(0.1)
        pytest.fail(f"mission {mission_id} did not reach {sorted(expected)}")

    async def scenario() -> None:
        async with Client(
            create_mission_mcp_server(operator_label="test-agent")
        ) as client:
            started_at = time.monotonic()
            accepted = await client.call_tool("start_goal", request)
            assert time.monotonic() - started_at < 5
            assert accepted.is_error is False, accepted.content
            first = accepted.structured_content
            assert first["accepted_request_id"] == request["request_id"]
            assert first["requested_authorization_mode"] == "review_required"
            assert first["effective_authorization_mode"] is None
            assert first["authorization_mode"] is None
            assert first["finalization_mode"] == "review_required"
            assert first["plan_revision"] is None and first["digest"] is None
            assert first["state"] in {"accepted", "planning", "review_required"}

            duplicate = await client.call_tool("start_goal", request)
            assert duplicate.is_error is False, duplicate.content
            assert duplicate.structured_content["mission_id"] == first["mission_id"]
            assert (
                duplicate.structured_content["accepted_request_id"]
                == first["accepted_request_id"]
            )

            status = await poll(client, first["mission_id"], {"proposed", "failed"})
            assert status["status"] == "proposed", status
            deadline = time.monotonic() + 5
            while (
                status["supervisor"]["phase"] != "review_required"
                and time.monotonic() < deadline
            ):
                await asyncio.sleep(0.02)
                result = await client.call_tool(
                    "mission_status", {"mission_id": first["mission_id"]}
                )
                status = result.structured_content
            assert status["signed"] is False
            assert status["signed_digest"] is None
            assert status["approved_revision"] is None
            assert status["approved_digest"] is None
            assert status["approval_truth"] is None
            assert status["approval_authority"] is None
            assert status["requested_authorization_mode"] == "review_required"
            assert status["effective_authorization_mode"] == "review_required"
            assert status["finalization_mode"] == "review_required"
            assert status["supervisor"]["phase"] == "review_required"
            review_generation = status["supervisor"]["generation"]
            digest = status["digest"]
            assert isinstance(digest, str) and len(digest) == 64

            forged = digest[:-1] + ("0" if digest[-1] != "0" else "1")
            refused = await client.call_tool(
                "approve_plan", {"mission_id": first["mission_id"], "digest": forged}
            )
            assert refused.is_error is True
            assert "digest does not match" in refused.content[0].text

            if not scripted_supported():
                return
            request_path = next(
                (private_state / "missions").glob("*/supervisor-request.json")
            )
            supervisor_request = SupervisorRequest.model_validate_json(
                request_path.read_bytes()
            )
            _state(
                request_path.parent,
                supervisor_request,
                "failed",
                review_generation,
                error_code="approval-signal-window",
            )
            approved_at = time.monotonic()
            approved = await client.call_tool(
                "approve_plan", {"mission_id": first["mission_id"], "digest": digest}
            )
            assert time.monotonic() - approved_at < 5
            assert approved.is_error is False, approved.content
            assert approved.structured_content["signed"] is False
            assert approved.structured_content["signed_digest"] is None
            assert approved.structured_content["approved_revision"] == 1
            assert approved.structured_content["approved_digest"] == digest
            assert approved.structured_content["approval_truth"] == "server_derived"
            assert (
                approved.structured_content["approval_authority"] == "mission_service"
            )
            assert approved.structured_content["run"]["status"] in {
                "accepted",
                "planning",
                "running",
            }
            assert (
                approved.structured_content["run"]["supervisor_generation"]
                > review_generation
            )

            committed = await client.call_tool(
                "get_digest", {"mission_id": first["mission_id"]}
            )
            assert committed.structured_content["signed"] is False
            assert committed.structured_content["signed_digest"] is None
            assert committed.structured_content["approved_revision"] == 1
            assert committed.structured_content["approved_digest"] == digest
            assert committed.structured_content["approval_truth"] == "server_derived"
            assert (
                committed.structured_content["approval_authority"] == "mission_service"
            )

    asyncio.run(scenario())


def test_committed_mcp_json_launches_the_bare_server() -> None:
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    entry = config["mcpServers"]["graphene"]
    assert entry["command"] == "uv" and entry["args"] == [
        "run",
        "--frozen",
        "graphene-mcp",
    ]
    assert "env" not in entry
