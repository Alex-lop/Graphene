"""What PyPI shows a stranger, and the command `uvx graphene-map` finds."""

import re
import tomllib
from pathlib import Path

PROJECT = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())["project"]


def test_uvx_graphene_map_runs_the_same_app_as_graphene():
    assert PROJECT["scripts"]["graphene-map"] == PROJECT["scripts"]["graphene"]


def test_the_description_is_one_plain_sentence():
    text = PROJECT["description"]
    assert len(text) < 160
    assert text.endswith(".") and not re.search(r"[.!?]\s", text)  # one sentence
    assert not re.search(r"\b(node|scope|check|hook)", text, re.IGNORECASE)  # the plan's own words


def test_the_keywords_lead_with_what_a_stranger_searches_for():
    assert PROJECT["keywords"][:3] == ["claude-code", "coding-agents", "ai-agents"]
