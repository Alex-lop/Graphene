import json
import tomllib
from pathlib import Path

from graphene import __version__
from graphene.app import create_app
from graphene.cli.main import build_parser as cli_parser
from graphene.cli.mission import _MISSION_COMMANDS
from graphene.demo import _SCRIPTED_LABEL
from graphene.demo_adk import ADK_FAKE_PROOF_LABEL
from graphene.integrations.stdio import build_parser as mcp_parser
from graphene.orchestration.replay import MISSION_REPLAY_TRUTH_LABEL
from graphene.store import InMemoryStore
from graphene.viewer.replay import REPLAY_TRUTH_LABEL

ROOT = Path(__file__).parents[2]


def test_canonical_docs_match_cli_product_and_compatibility_contracts() -> None:
    readme = (ROOT / "README.md").read_text()
    simple = (ROOT / "simplreadme.md").read_text()
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
    }
    assert set(mission) == set(_MISSION_COMMANDS)
    assert all(f"`graphene {command}" in readme for command in commands)
    assert all(f"`graphene mission {command}" in readme for command in mission)

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
    assert scripted["truth_label"] in readme
    assert scripted["execute_command"] in readme and "--auto-approve" in readme
    assert replay["status"] == scripted["status"] == "verified_local"
    assert product["mission_paths"]["gemini-adk-planner"]["status"] == "not_proven"
    assert (
        product["mission_paths"]["gemini-adk-planner"]["product_command"]
        in " ".join(readme.replace("\\\n", "").split())
    )
    assert product["mission_paths"]["cloud-run-firestore"]["status"] == "not_deployed"

    assert product["product_thesis"] in readme
    assert package["description"] == (
        "Local-first mission control for bounded multi-agent coding work"
    )
    assert package["version"] == __version__
    assert create_app(InMemoryStore(), "test-token").version == __version__

    assert mcp_parser().parse_args(entry["args"]).task == "baseline_max_attempts"
    assert entry["command"].endswith("/.venv/bin/graphene-mcp")
    assert set(entry["env"]) == {"GRAPHENE_LINEAGE_DB"}
    assert "compatibility-only" in readme

    dockerfile = (ROOT / "Dockerfile").read_text()
    assert 'GRAPHENE_ENTRYPOINT_MODE="legacy-http-compatibility"' in dockerfile
    assert "not authoritative v2 execution" in dockerfile
