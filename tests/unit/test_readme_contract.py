import json
import tomllib
from pathlib import Path

from graphene import __version__
from graphene.legacy_app import create_app
from graphene.cli.main import build_parser as cli_parser
from graphene.cli.mission import _MISSION_COMMANDS
from graphene.demo import _SCRIPTED_LABEL
from graphene.demo_adk import ADK_FAKE_PROOF_LABEL
from graphene.integrations.mission_mcp import TOOL_ARGUMENTS
from graphene.integrations.stdio import build_parser as mcp_parser
from graphene.orchestration.mission_replay import MISSION_REPLAY_TRUTH_LABEL
from graphene.legacy_store import InMemoryStore
from graphene.viewer.viewer_replay import REPLAY_TRUTH_LABEL

ROOT = Path(__file__).parents[2]


def test_canonical_docs_match_cli_product_and_compatibility_contracts() -> None:
    readme = (ROOT / "README.md").read_text()
    simple = (ROOT / "simplreadme.md").read_text()
    # The README is the newcomer's door (roughly <=100 lines); the proof table
    # and command map live in these documents, and each assertion names its owner.
    proof = (ROOT / "docs/PROOF.md").read_text()
    commands_doc = (ROOT / "docs/COMMANDS.md").read_text()
    product = json.loads((ROOT / "contracts/product_proof.json").read_text())
    parser = cli_parser()
    commands = parser._subparsers._group_actions[0].choices
    mission = commands["mission"]._subparsers._group_actions[0].choices
    demo = commands["demo"]
    driver_action = next(action for action in demo._actions if action.dest == "driver")
    legacy = product["legacy_protocol_tour"]["drivers"]
    config = json.loads((ROOT / "docs/mcp_client_config.example.json").read_text())
    entry = config["mcpServers"]["graphene"]
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert set(commands) == {
        "init",
        "doctor",
        "plan",
        "status",
        "bundle",
        "cancel",
        "mission",
        "request-replan",
        "retry",
        "run",
        "task",
        "watch",
        "inspect",
        "why",
        "replay",
        "review",
        "feedback",
        "answer",
        "memory",
        "handoff",
        "promote",
        "demo",
        "ui",
    }
    assert set(mission) == set(_MISSION_COMMANDS)
    assert all(f"`graphene {command}" in commands_doc for command in commands)
    assert all(f"`graphene mission {command}" in commands_doc for command in mission)
    assert len(readme.splitlines()) <= 100
    assert readme.startswith(
        '<p align="center">\n'
    ) and "# Agents write. Graphene decides what survives." in readme
    assert (
        "**Repository publication control for parallel coding agents: bounded writes, "
        "exact candidates, traceable history.**"
    ) in readme
    assert product["product_thesis"] in readme
    assert (
        readme.index("## Run the verified path")
        < readme.index("docs/assets/ui-terminal.png")
        < readme.index("## Where Graphene fits")
        < readme.index("## Connect a controller")
        < readme.index("## Proven / waiting")
    )
    assert all(
        project in readme
        for project in (
            "[Graft](https://github.com/trailhq/Graft)",
            "[LangGraph](https://github.com/langchain-ai/langgraph)",
            "[Microsoft Agent Framework](https://github.com/microsoft/agent-framework)",
        )
    )
    assert (ROOT / "docs/assets/ui-terminal.png").is_file()
    assert (
        ROOT / "docs/reports/2026-08-28-readme-comparison-research.md"
    ).is_file()
    assert "Approved plan → scoped attempts → accepted artifacts" in readme
    assert "These are complementary layers" in readme
    assert "no token-efficiency claim, and no speed or cost comparison" in readme
    assert "SHA-256" in readme and "exact candidate" in readme
    assert "Graphene never pushes, merges, deploys, or mutates" in readme
    assert "`server_derived` relay evidence, not human attestation" in readme
    assert "no Codex, Claude Code, or Gemini CLI run" in readme
    assert (
        "Current credentialed Gemini Orders mission, real model kill/recovery, "
        "and Codex controller"
    ) in readme
    assert all(
        command in readme
        for command in (
            "`start_goal`",
            "`get_digest`",
            "`approve_plan`",
            "`mission_status`",
            "`why`",
            "`graphene mission result show`",
        )
    )

    assert set(driver_action.choices) == set(legacy)
    assert all(driver in demo.format_help() for driver in legacy)
    assert all(
        label in demo.format_help()
        for label in (_SCRIPTED_LABEL, ADK_FAKE_PROOF_LABEL, REPLAY_TRUTH_LABEL)
    )
    assert {
        "verified-replay": REPLAY_TRUTH_LABEL,
        "scripted-local": _SCRIPTED_LABEL,
        "adk-fake": ADK_FAKE_PROOF_LABEL,
    } == {name: driver["truth_label"] for name, driver in legacy.items()}

    replay = product["mission_paths"]["verified-mission-replay"]
    scripted = product["mission_paths"]["scripted-local"]
    assert replay["truth_label"] == MISSION_REPLAY_TRUTH_LABEL
    assert replay["command"] in readme and replay["command"] in simple
    assert replay["truth_label"] in proof and replay["truth_label"] in simple
    assert scripted["truth_label"] in proof
    assert scripted["execute_command"] in proof and "--auto-approve" in proof
    assert replay["status"] == scripted["status"] == "verified_local"
    gemini = product["mission_paths"]["gemini-adk-planner"]
    assert gemini["status"] == "not_proven"
    assert (ROOT / gemini["historical_evidence"]).is_file()
    assert "NOT PROVEN" in gemini["truth_label"]
    assert "NOT PROVEN" in readme and "NOT PROVEN" in proof
    assert "start_goal" in proof
    assert product["mission_paths"]["cloud-run-firestore"]["status"] == "not_deployed"
    watcher = product["watch"]
    assert watcher["status"] == "verified_local"
    assert "NOT PROVEN" in watcher["truth_label"]
    assert "graphene watch github" in commands_doc
    assert watcher["live_gate_env"] in watcher["github_command"]

    mcp_goal_loop = product["mcp_goal_loop"]
    assert mcp_goal_loop["tools"] == list(TOOL_ARGUMENTS)
    assert "NINE TOOLS" in mcp_goal_loop["truth_label"]
    assert "nine-tool" in mcp_goal_loop["proves"]
    assert all(f"`{tool}`" in commands_doc for tool in TOOL_ARGUMENTS)
    assert "nine-tool server" in proof
    assert package["description"] == (
        "Local-first mission control for bounded multi-agent coding work"
    )
    assert package["version"] == __version__
    assert create_app(InMemoryStore(), "test-token").version == __version__

    assert mcp_parser().parse_args(entry["args"]).task == "baseline_max_attempts"
    assert entry["command"].endswith("/.venv/bin/graphene-mcp")
    assert set(entry["env"]) == {"GRAPHENE_LINEAGE_DB"}
    assert "compatibility-only" in commands_doc

    dockerfile = (ROOT / "Dockerfile").read_text()
    assert 'GRAPHENE_ENTRYPOINT_MODE="legacy-http-compatibility"' in dockerfile
    assert "not authoritative v2 execution" in dockerfile
