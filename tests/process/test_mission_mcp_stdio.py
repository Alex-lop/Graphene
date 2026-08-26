"""CP-C1: the bare `graphene-mcp` server over stdio, driven by the official client.

Launched exactly as the committed `.mcp.json` launches it (`uv run --frozen
graphene-mcp` from the repository root), credential-free: initialize,
tools/list, prompts/list, prompts/get, and one tool round trip
(plan_goal -> get_digest) against a throwaway target repository.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from graphene.orchestration.scripted import load_scenario

ROOT = Path(__file__).parents[2]
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


def test_mcp_json_server_answers_initialize_lists_and_one_round_trip(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH; .mcp.json launches the server through uv")
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["graphene"]
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    repository = _repository(tmp_path / "target")
    subprocess.run(
        ["uv", "run", "--frozen", "graphene", "init", "--repo", str(repository)],
        cwd=ROOT, check=True, capture_output=True,
        env={**os.environ, "GRAPHENE_STATE_DIR": str(state)},
    )
    stderr_path = tmp_path / "server-stderr.txt"
    errors = stderr_path.open("w+", encoding="utf-8")
    parameters = StdioServerParameters(
        command=config["command"],
        args=config["args"],
        cwd=ROOT,
        env={**os.environ, "GRAPHENE_STATE_DIR": str(state), "NO_COLOR": "1"},
    )

    async def scenario() -> None:
        async with stdio_client(parameters, errlog=errors) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize()
                assert initialized.server_info.name == "graphene"
                listed = await session.list_tools()
                assert [tool.name for tool in listed.tools] == TOOLS
                assert all(tool.input_schema["additionalProperties"] is False for tool in listed.tools)
                prompts = await session.list_prompts()
                assert [prompt.name for prompt in prompts.prompts] == ["goal"]
                rendered = await session.get_prompt("goal", {"goal": "Add a status export"})
                assert "STOP AND ASK THE HUMAN TO SIGN" in rendered.messages[0].content.text

                planned = await session.call_tool(
                    "plan_goal", {"repo": str(repository), "goal": load_scenario().goal, "driver": "scripted-local"}
                )
                assert planned.is_error is False, planned.content
                plan = planned.structured_content
                assert plan["signed"] is False and len(plan["digest"]) == 64 and len(plan["task_graph"]) == 6
                shown = await session.call_tool("get_digest", {"mission_id": plan["mission_id"]})
                assert shown.structured_content["digest"] == plan["digest"]
                assert shown.structured_content["approved_revision"] is None

    try:
        asyncio.run(scenario())
    finally:
        errors.close()
    assert stderr_path.read_text(encoding="utf-8") == "GRAPHENE_MCP_STDIO_READY\n"
    assert (state / "missions.sqlite3").is_file()
