import json
import tomllib
from pathlib import Path

from graphene import __version__
from graphene.app import create_app
from graphene.cli.main import build_parser as cli_parser
from graphene.integrations.stdio import build_parser as mcp_parser
from graphene.store import InMemoryStore

ROOT = Path(__file__).parents[2]


def test_readme_matches_the_public_cli_mcp_auth_and_version_contract() -> None:
    readme = (ROOT / "README.md").read_text()
    commands = cli_parser()._subparsers._group_actions[0].choices
    config = json.loads((ROOT / "docs/mcp_client_config.example.json").read_text())
    entry = config["mcpServers"]["graphene"]
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert set(commands) == {
        "run",
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
    assert all(f"`graphene {command}" in readme for command in commands)
    assert mcp_parser().parse_args(entry["args"]).task == "baseline_max_attempts"
    assert entry["command"].endswith("/.venv/bin/graphene-mcp")
    assert set(entry["env"]) == {"GRAPHENE_LINEAGE_DB"}
    assert "Authorization: Bearer" in readme and "X-Graphene-Token" not in readme
    assert "Linux / Docker fixed tests | Unsupported and fail closed" in readme
    assert package["version"] == __version__
    assert create_app(InMemoryStore(), "test-token").version == __version__
