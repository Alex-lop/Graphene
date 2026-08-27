import json
import tomllib
from pathlib import Path

from graphene import __version__
from graphene.legacy_app import create_app
from graphene.cli.main import build_parser as cli_parser
from graphene.cli.mission import _MISSION_COMMANDS
from graphene.demo import _SCRIPTED_LABEL
from graphene.demo_adk import ADK_FAKE_PROOF_LABEL
from graphene.integrations.stdio import build_parser as mcp_parser
from graphene.orchestration.mission_replay import MISSION_REPLAY_TRUTH_LABEL
from graphene.legacy_store import InMemoryStore
from graphene.viewer.viewer_replay import REPLAY_TRUTH_LABEL

ROOT = Path(__file__).parents[2]


def test_canonical_docs_match_cli_product_and_compatibility_contracts() -> None:
    readme = (ROOT / "README.md").read_text()
    simple = (ROOT / "simplreadme.md").read_text()
    # The README is the newcomer's door (<=120 lines); the proof table and the
    # command map moved to these two documents on 2026-08-26 and the contract
    # follows the content: each assertion names the document that owns it.
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
    assert len(readme.splitlines()) <= 120

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

    assert product["product_thesis"] in readme
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
