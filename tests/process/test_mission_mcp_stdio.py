"""The installed-style mission MCP survives its initiating STDIO controller."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

import graphene.cli.mission as mission_cli
from graphene.orchestration.scripted import load_scenario, scripted_supported
from graphene.orchestration.supervisor import SupervisorProcess, _live, accept_goal

ROOT = Path(__file__).parents[2]
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


def _parameters(state: Path) -> StdioServerParameters:
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][
        "graphene"
    ]
    return StdioServerParameters(
        command=config["command"],
        args=config["args"],
        cwd=ROOT,
        env={**os.environ, "GRAPHENE_STATE_DIR": str(state), "NO_COLOR": "1"},
    )


@pytest.mark.skipif(
    not scripted_supported(), reason="scripted sandbox is unsupported on this host"
)
def test_controller_exit_does_not_stop_auto_finalizing_mission_and_fresh_stdio_reattaches(
    tmp_path: Path,
) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH; .mcp.json launches the server through uv")
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    repository = _repository(tmp_path / "target")
    environment = {**os.environ, "GRAPHENE_STATE_DIR": str(state)}
    subprocess.run(
        ["uv", "run", "--frozen", "graphene", "init", "--repo", str(repository)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=environment,
    )
    first_errors = (tmp_path / "first-server-stderr.txt").open("w+", encoding="utf-8")
    second_errors = (tmp_path / "second-server-stderr.txt").open("w+", encoding="utf-8")
    request = {
        "repo": str(repository),
        "goal": load_scenario().goal,
        "request_id": "request-stdio-disconnect-1",
        "success_criteria_json": json.dumps(load_scenario().success_criteria),
        "driver": "scripted-local",
        "authorization_mode": "policy_pre_authorized",
        "finalization_mode": "auto_finalize_isolated",
    }

    async def start_then_disconnect() -> str:
        async with stdio_client(_parameters(state), errlog=first_errors) as streams:
            async with ClientSession(*streams) as session:
                initialized = await session.initialize()
                assert initialized.server_info.name == "graphene"
                listed = await session.list_tools()
                assert [tool.name for tool in listed.tools] == TOOLS
                assert all(
                    tool.input_schema["additionalProperties"] is False
                    for tool in listed.tools
                )
                rendered = await session.get_prompt(
                    "goal", {"goal": "Add a status export"}
                )
                assert "start_goal" in rendered.messages[0].content.text

                started_at = time.monotonic()
                accepted = await session.call_tool("start_goal", request)
                assert time.monotonic() - started_at < 5
                assert accepted.is_error is False, accepted.content
                value = accepted.structured_content
                assert value["accepted_request_id"] == request["request_id"]
                assert value["plan_revision"] is None and value["digest"] is None
                return value["mission_id"]

    async def reattach(mission_id: str) -> dict:
        async with stdio_client(_parameters(state), errlog=second_errors) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                duplicate = await session.call_tool("start_goal", request)
                assert duplicate.is_error is False, duplicate.content
                assert duplicate.structured_content["mission_id"] == mission_id

                deadline = time.monotonic() + 180
                dead_since = None
                while time.monotonic() < deadline:
                    result = await session.call_tool(
                        "mission_status", {"mission_id": mission_id}
                    )
                    assert result.is_error is False, result.content
                    status = result.structured_content
                    if status["status"] in {"completed", "failed"}:
                        generation = status["supervisor"]["generation"]
                        duplicate = await session.call_tool("start_goal", request)
                        assert duplicate.is_error is False, duplicate.content
                        assert duplicate.structured_content["state"] == "completed"
                        after = await session.call_tool(
                            "mission_status", {"mission_id": mission_id}
                        )
                        assert (
                            after.structured_content["supervisor"]["generation"]
                            == generation
                        )
                        return status
                    process_paths = tuple(
                        (state / "missions").glob("*/supervisor-process.json")
                    )
                    assert len(process_paths) == 1
                    record = SupervisorProcess.model_validate_json(
                        process_paths[0].read_bytes()
                    )
                    if _live(record):
                        dead_since = None
                    else:
                        dead_since = dead_since or time.monotonic()
                        assert time.monotonic() - dead_since < 2, (
                            "detached supervisor exited while the mission remained nonterminal"
                        )
                    await asyncio.sleep(0.1)
                pytest.fail(f"mission {mission_id} did not reach a terminal state")

    try:
        mission_id = asyncio.run(start_then_disconnect())
        # The initiating STDIO transport and controller are gone here. Only the
        # exact detached supervisor process may continue the mission.
        status = asyncio.run(reattach(mission_id))
        assert status["status"] == "completed", status
        assert status["result"]["state"] == "commit_created"
        assert {task["state"] for task in status["tasks"]} == {"done"}
        assert status["signed"] is False
        assert status["signed_digest"] is None
        assert status["approved_revision"] == status["plan_revision"]
        assert status["approved_digest"] == status["digest"]
        assert status["approval_truth"] == "simulated_fixture"
        assert status["approval_authority"] == "simulated_fixture"
    finally:
        first_errors.close()
        second_errors.close()
        _stop_owned_supervisors(state)

    assert (tmp_path / "first-server-stderr.txt").read_text(
        encoding="utf-8"
    ) == "GRAPHENE_MCP_STDIO_READY\n"
    assert (tmp_path / "second-server-stderr.txt").read_text(
        encoding="utf-8"
    ) == "GRAPHENE_MCP_STDIO_READY\n"
    assert (state / "missions.sqlite3").is_file()


@pytest.mark.skipif(
    not scripted_supported(), reason="scripted sandbox is unsupported on this host"
)
@pytest.mark.parametrize(
    ("tool_name", "terminal_status", "decision"),
    [
        ("approve_result", "completed", "approve"),
        ("reject_result", "rejected", "reject"),
    ],
)
def test_reviewed_final_bundle_decision_round_trips_over_stdio(
    tmp_path: Path, tool_name: str, terminal_status: str, decision: str
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    repository = _repository(tmp_path / "target")
    environment = {**os.environ, "GRAPHENE_STATE_DIR": str(state)}
    subprocess.run(
        ["uv", "run", "--frozen", "graphene", "init", "--repo", str(repository)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=environment,
    )
    errors = (tmp_path / "server-stderr.txt").open("w+", encoding="utf-8")
    request = {
        "repo": str(repository),
        "goal": load_scenario().goal,
        "request_id": f"request-stdio-final-{decision}",
        "success_criteria_json": json.dumps(load_scenario().success_criteria),
        "driver": "scripted-local",
        "authorization_mode": "review_required",
        "finalization_mode": "review_required",
    }

    async def poll(
        session: ClientSession, mission_id: str, expected: set[str]
    ) -> dict:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            result = await session.call_tool(
                "mission_status", {"mission_id": mission_id}
            )
            assert result.is_error is False, result.content
            status = result.structured_content
            if status["status"] in expected:
                return status
            await asyncio.sleep(0.1)
        pytest.fail(f"mission {mission_id} did not reach {sorted(expected)}")

    async def scenario() -> None:
        async with stdio_client(_parameters(state), errlog=errors) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                accepted = await session.call_tool("start_goal", request)
                assert accepted.is_error is False, accepted.content
                mission_id = accepted.structured_content["mission_id"]

                proposed = await poll(session, mission_id, {"proposed", "failed"})
                assert proposed["status"] == "proposed", proposed
                assert proposed["needs_you"] == {
                    "decision_kind": "plan_review",
                    "plan_revision": proposed["plan_revision"],
                    "digest": proposed["digest"],
                }
                approved = await session.call_tool(
                    "approve_plan",
                    {
                        "mission_id": mission_id,
                        "digest": proposed["digest"],
                        "rationale": "Reviewed the exact proposed plan.",
                    },
                )
                assert approved.is_error is False, approved.content

                awaiting = await poll(
                    session,
                    mission_id,
                    {"awaiting_result", "failed", "cancelled"},
                )
                assert awaiting["status"] == "awaiting_result", awaiting
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and (
                    awaiting["result"]["bundle_id"] is None
                    or awaiting["needs_you"] is None
                ):
                    await asyncio.sleep(0.05)
                    awaiting = (
                        await session.call_tool(
                            "mission_status", {"mission_id": mission_id}
                        )
                    ).structured_content
                need = awaiting["needs_you"]
                assert need["decision_kind"] == "result_review"
                assert need["bundle_id"] == awaiting["result"]["bundle_id"]
                bundle_id = need["bundle_id"]

                forged = bundle_id[:-1] + ("0" if bundle_id[-1] != "0" else "1")
                refused = await session.call_tool(
                    tool_name,
                    {
                        "mission_id": mission_id,
                        "bundle_id": forged,
                        "rationale": "This must bind the current bundle.",
                    },
                )
                assert refused.is_error is True
                assert "does not match the current bundle" in refused.content[0].text

                result = await session.call_tool(
                    tool_name,
                    {
                        "mission_id": mission_id,
                        "bundle_id": bundle_id,
                        "rationale": "Reviewed the exact verified result bundle.",
                    },
                )
                assert result.is_error is False, result.content
                value = result.structured_content
                assert value["status"] == terminal_status
                assert value["decision"] == decision
                assert value["bundle_id"] == bundle_id
                assert value["decision_truth"] == "server_derived"
                assert value["decision_authority"] == "mission_service"
                assert value["decision_operator"] == "mcp-agent-result-relay"

                terminal = await poll(session, mission_id, {terminal_status})
                assert terminal["needs_you"] is None

    try:
        asyncio.run(scenario())
    finally:
        errors.close()
        _stop_owned_supervisors(state)

    assert (tmp_path / "server-stderr.txt").read_text(
        encoding="utf-8"
    ) == "GRAPHENE_MCP_STDIO_READY\n"


@pytest.mark.skipif(
    not scripted_supported(), reason="scripted sandbox is unsupported on this host"
)
def test_fresh_stdio_recovers_request_committed_before_binding_or_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH; .mcp.json launches the server through uv")
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    repository = _repository(tmp_path / "target")
    environment = {**os.environ, "GRAPHENE_STATE_DIR": str(state)}
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    subprocess.run(
        ["uv", "run", "--frozen", "graphene", "init", "--repo", str(repository)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=environment,
    )
    scenario = load_scenario()
    request = {
        "repo": str(repository),
        "goal": scenario.goal,
        "request_id": "request-stdio-request-only",
        "success_criteria_json": json.dumps(scenario.success_criteria),
        "driver": "scripted-local",
        "authorization_mode": "policy_pre_authorized",
        "finalization_mode": "auto_finalize_isolated",
    }

    def crash_after_request(_runtime: Path, _binding: dict[str, object]) -> None:
        raise RuntimeError("injected crash after request fsync")

    with monkeypatch.context() as fault:
        fault.setattr(mission_cli, "_bind_start_request", crash_after_request)
        with pytest.raises(RuntimeError, match="injected crash"):
            accept_goal(
                repository=repository,
                goal=scenario.goal,
                success_criteria=scenario.success_criteria,
                driver="scripted-local",
                max_workers=2,
                command_id=request["request_id"],
                requested_mode="policy_pre_authorized",
                finalization_mode="auto_finalize_isolated",
            )

    runtimes = tuple((state / "missions").glob("*/supervisor-request.json"))
    assert len(runtimes) == 1
    runtime = runtimes[0].parent
    assert not (runtime / "start-request.json").exists()
    assert not (runtime / "supervisor-state.json").exists()
    assert not (runtime / "supervisor-process.json").exists()
    errors = (tmp_path / "recovery-server-stderr.txt").open("w+", encoding="utf-8")

    async def reattach() -> dict:
        async with stdio_client(_parameters(state), errlog=errors) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                duplicate = await session.call_tool("start_goal", request)
                assert duplicate.is_error is False, duplicate.content
                mission_id = duplicate.structured_content["mission_id"]
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    result = await session.call_tool(
                        "mission_status", {"mission_id": mission_id}
                    )
                    assert result.is_error is False, result.content
                    if result.structured_content["status"] in {"completed", "failed"}:
                        return result.structured_content
                    await asyncio.sleep(0.1)
                pytest.fail(f"mission {mission_id} did not reach a terminal state")

    try:
        status = asyncio.run(reattach())
        assert status["status"] == "completed", status
        assert status["supervisor"]["generation"] == 1
        assert status["result"]["state"] == "commit_created"
    finally:
        errors.close()
        _stop_owned_supervisors(state)

    assert (tmp_path / "recovery-server-stderr.txt").read_text(
        encoding="utf-8"
    ) == "GRAPHENE_MCP_STDIO_READY\n"
