"""The /graphene loop over MCP, in process: six tools, one prompt, one load-bearing digest."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest
from mcp import Client, MCPError

from graphene.integrations.mission_mcp import GOAL_PROMPT, TOOL_ARGUMENTS, create_mission_mcp_server
from graphene.orchestration.scripted import load_scenario, scripted_supported

ROOT = Path(__file__).parents[3]
TOOLS = ["plan_goal", "get_digest", "approve_plan", "mission_status", "why", "mission_summary"]


def _repository(path: Path) -> Path:
    path.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "README.md").write_text("# Target\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "fixture"], check=True, env=env)
    return path


@pytest.fixture
def private_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    return state


def test_server_lists_six_tools_and_the_goal_prompt_with_strict_schemas() -> None:
    async def scenario() -> None:
        async with Client(create_mission_mcp_server()) as client:
            listed = await client.list_tools()
            assert [tool.name for tool in listed.tools] == TOOLS
            for tool in listed.tools:
                required, optional = TOOL_ARGUMENTS[tool.name]
                schema = tool.input_schema
                assert schema["type"] == "object" and schema["additionalProperties"] is False
                assert set(schema["properties"]) == required | optional
                assert set(schema.get("required", ())) == required
                assert all(schema["properties"][key]["type"] == "string" for key in schema["properties"])
            prompts = (await client.list_prompts()).prompts
            assert [prompt.name for prompt in prompts] == ["goal"]
            assert [argument.name for argument in prompts[0].arguments] == ["goal"]
            rendered = await client.get_prompt("goal", {"goal": "Add a status export"})
            text = rendered.messages[0].content.text
            assert "Add a status export" in text
            assert "STOP AND ASK THE HUMAN TO SIGN" in text and "approve_plan" in text
            assert "never one you copied for them" in text
            assert text == GOAL_PROMPT.format(goal="Add a status export")

    asyncio.run(scenario())


def test_forged_or_non_string_arguments_are_rejected_before_dispatch() -> None:
    async def scenario() -> None:
        async with Client(create_mission_mcp_server()) as client:
            for name, arguments in (
                ("get_digest", {}),
                ("get_digest", {"mission_id": "x", "extra": "y"}),
                ("approve_plan", {"mission_id": "x"}),
                ("approve_plan", {"mission_id": "x", "digest": 7}),
                ("nonexistent", {"mission_id": "x"}),
            ):
                with pytest.raises(MCPError):
                    await client.call_tool(name, arguments)

    asyncio.run(scenario())


def test_the_loop_plans_shows_the_digest_and_only_signs_the_digest_the_human_typed(
    private_state: Path, tmp_path: Path
) -> None:
    repository = _repository(tmp_path / "target")
    from graphene.cli.mission import initialize

    initialize(repository)

    async def scenario() -> None:
        async with Client(create_mission_mcp_server(operator_label="test-agent")) as client:
            planned = await client.call_tool(
                "plan_goal", {"repo": str(repository), "goal": load_scenario().goal, "driver": "scripted-local"}
            )
            assert planned.is_error is False, planned.content
            plan = planned.structured_content
            mission_id, digest = plan["mission_id"], plan["digest"]
            assert plan["mission_status"] == "proposed" and plan["signed"] is False
            assert plan["review_required"] is True and len(plan["task_graph"]) == 6
            assert len(digest) == 64 and plan["plan_revision"] == 1 and len(plan["base_sha"]) == 40

            shown = await client.call_tool("get_digest", {"mission_id": mission_id})
            assert shown.structured_content["digest"] == digest and shown.structured_content["signed"] is False

            status = (await client.call_tool("mission_status", {"mission_id": mission_id})).structured_content
            assert status["status"] == "proposed" and status["signed"] is False
            assert {task["state"] for task in status["tasks"]} == {"queued"}
            assert any("plan approve" in action for action in status["next_actions"])

            # A digest the human did not sign — one hex digit off — fails closed.
            forged = digest[:-1] + ("0" if digest[-1] != "0" else "1")
            refused = await client.call_tool("approve_plan", {"mission_id": mission_id, "digest": forged})
            assert refused.is_error is True
            assert "digest does not match" in refused.content[0].text
            after = (await client.call_tool("get_digest", {"mission_id": mission_id})).structured_content
            assert after["signed"] is False and after["mission_status"] == "proposed"

            if not scripted_supported():
                return  # approval executes the fixture, which needs the macOS sandbox

            approved = await client.call_tool("approve_plan", {"mission_id": mission_id, "digest": digest})
            assert approved.is_error is False, approved.content
            run = approved.structured_content
            assert run["signed_digest"] == digest and run["revision"] == 1
            assert run["run"]["status"] == "awaiting_result"
            assert "not TTY-attested" in run["approval_truth"]

            status = (await client.call_tool("mission_status", {"mission_id": mission_id})).structured_content
            assert status["status"] == "awaiting_result" and status["signed"] is True
            assert {task["state"] for task in status["tasks"]} == {"done"}

            summary = (await client.call_tool("mission_summary", {"mission_id": mission_id})).structured_content
            assert summary["goal"] == load_scenario().goal and summary["status"] == "awaiting_result"
            assert len(summary["nodes"]) == 6 and all(node["attempts"] >= 1 for node in summary["nodes"])
            assert summary["artifacts_touched"] and summary["receipts"] > 0
            assert "what was done" in summary["text"]

            path = summary["artifacts_touched"][0]
            lineage = (await client.call_tool("why", {"mission_id": mission_id, "path": path})).structured_content
            assert lineage["mission_id"] == mission_id and lineage["matched_by"] == "path"
            assert {link["stage"] for link in lineage["links"]} >= {"target", "producer_attempt", "approval"}

    asyncio.run(scenario())


def test_committed_mcp_json_launches_the_bare_server() -> None:
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    entry = config["mcpServers"]["graphene"]
    assert entry["command"] == "uv" and entry["args"] == ["run", "--frozen", "graphene-mcp"]
    assert "env" not in entry  # nothing secret, nothing machine-specific


def test_mcp_goal_loop_label_is_backed_by_its_evidence_and_config() -> None:
    contract = json.loads((ROOT / "contracts/product_proof.json").read_text(encoding="utf-8"))
    label = contract["mcp_goal_loop"]
    assert label["status"] == "verified_local"
    assert "NO PERSON SIGNED" in label["truth_label"]
    assert label["tools"] == TOOLS and label["prompt"] == "goal"
    assert (ROOT / label["config"]).is_file()
    transcript = (ROOT / label["evidence"]).read_text(encoding="utf-8")
    assert "Beats present: 14/14 — every beat present." in transcript
    for beat in ("forged digest refused", "digest signed", "approve_plan ran the map", "mission_summary", "why lineage", "ui frames captured"):
        assert beat in transcript
    assert "not a person" in transcript
    assert "`GRAPHENE_MCP_STDIO_READY`" in transcript
    for path in ("README.md", "docs/PROOF.md", "docs/COMMANDS.md"):
        assert "approve_plan" in (ROOT / path).read_text(encoding="utf-8")
