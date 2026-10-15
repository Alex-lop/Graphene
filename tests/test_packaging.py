"""What PyPI shows a stranger, and the command `uvx graphene-map` finds."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
CI = (ROOT / ".github/workflows/ci.yml").read_text()


def test_uvx_graphene_map_runs_the_same_app_as_graphene():
    assert PROJECT["scripts"]["graphene-map"] == PROJECT["scripts"]["graphene"]


def test_the_description_is_one_plain_sentence():
    text = PROJECT["description"]
    assert len(text) < 160
    assert text.endswith(".") and not re.search(r"[.!?]\s", text)  # one sentence
    assert not re.search(r"\b(node|scope|check|hook)", text, re.IGNORECASE)  # the plan's own words


def test_the_keywords_lead_with_what_a_stranger_searches_for():
    assert PROJECT["keywords"][:3] == ["claude-code", "coding-agents", "ai-agents"]


def test_ci_is_callable_by_the_release_and_not_triggered_twice_for_a_tag():
    assert re.search(r"^  workflow_call:", CI, re.MULTILINE)  # the release runs the suite itself
    assert "tags:" not in CI  # so a tag push does not run it a second time


def test_the_suite_lists_its_skips():
    assert re.search(r"uv run pytest .*-rs", CI)  # each leg's log names what it skipped
