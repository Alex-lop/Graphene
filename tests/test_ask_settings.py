# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The planner is told the person's standing conditions and how big a plan to cut, before the rules;
`graphene ask --finer/--coarser` sizes one ask and leaves the saved size alone."""

import json

from test_ask import GOOD, planner
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import ask as A
from graphene_map import settings
from graphene_map.plan import Caller
from graphene_map.store import Store

ME = Caller("person:alex", True, None)


def said(tmp_path) -> str:
    return json.loads((tmp_path / "seen.jsonl").read_text().splitlines()[-1])["prompt"]


def test_the_prompt_says_the_conditions_and_the_size_before_the_rules(repo):
    with Store.open(repo) as store:
        settings.apply(store, "protected: secrets/**\nnever: a new dependency\nsize: finer\n", ME)
        prompt = A.prompt_for(store, "add ids", root=repo)
    rules = prompt.index(A.RULES)
    assert prompt.endswith(A.RULES)  # the rules as they are
    assert 0 < prompt.index("No scope may include these paths: secrets/**.") < rules
    assert 0 < prompt.index("Never propose this: a new dependency") < rules
    assert 0 < prompt.index("The repo has 2 files") < prompt.index("(finer).") < rules


def test_no_conditions_says_none_and_still_sizes(repo):
    with Store.open(repo) as store:
        prompt = A.prompt_for(store, "add ids", root=repo)
    assert "standing conditions" not in prompt and "(auto)." in prompt


def test_finer_sizes_this_ask_only(repo, tmp_path, monkeypatch):
    got = person("ask", "add ids", "--coarser", "--with", planner(tmp_path, GOOD, monkeypatch))
    assert got.exit_code == 0, got.output
    assert "(coarser)." in said(tmp_path)
    with Store.open(repo) as store:
        assert settings.size(store) == "auto"  # the saved default is untouched
        settings.apply(store, "size: coarser\n", ME)
    person("ask", "add ids", "--finer", "--with", planner(tmp_path, GOOD, monkeypatch))
    prompt = said(tmp_path)
    assert "(finer)." in prompt and "wants a coarser plan" not in prompt  # this ask's size, no contradiction
    with Store.open(repo) as store:
        assert settings.size(store) == "coarser"


def test_finer_and_coarser_together_are_refused(repo):
    got = person("ask", "add ids", "--finer", "--coarser")
    assert got.exit_code == 2 and "not both" in got.output
