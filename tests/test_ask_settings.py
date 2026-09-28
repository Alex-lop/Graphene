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


def test_the_planner_is_told_never_to_read_a_protected_path(repo):
    with Store.open(repo) as store:
        settings.apply(store, "protected: secrets/**\n", ME)
        prompt = A.prompt_for(store, "add ids", root=repo)
    assert "Never read these paths either: secrets/**." in prompt


def test_asking_again_finer_replaces_the_planners_last_proposal(repo, tmp_path, monkeypatch):
    first = person("ask", "add ids", "--with", planner(tmp_path, GOOD, monkeypatch))
    assert first.exit_code == 0, first.output
    finer = GOOD.replace("[users-api]", "[users-api2]").replace("[ids]", "[ids2]")
    again = person("ask", "add ids", "--finer", "--with", planner(tmp_path, finer, monkeypatch))
    assert again.exit_code == 0, again.output
    with Store.open(repo) as store:
        pending = sorted(n.id for n in A.P.nodes(store) if n.state == "proposed")
    assert pending == ["ids2", "users-api2"]  # one tree to prune, not two side by side
    assert "replaces the tree you proposed last" in said(tmp_path)


def test_a_saved_size_and_the_flag_tell_the_planner_the_same_thing_once(repo):
    with Store.open(repo) as store:
        flagged = A.prompt_for(store, "add ids", root=repo, size="finer")
        settings.apply(store, "size: finer\n", ME)
        saved = A.prompt_for(store, "add ids", root=repo)
    assert saved == flagged and "wants a finer plan" not in saved  # the numbers carry the size, once


def test_a_split_or_a_follow_up_is_not_told_how_big_the_whole_tree_should_be(repo):
    with Store.open(repo) as store:
        settings.apply(store, "size: coarser\n", ME)
        A.P.propose(store, [{"id": "ids1", "title": "ids", "scope": ["api.py"], "check": "true"}], ME)
        for split in (True, False):
            prompt = A.prompt_for(store, "add ids", about="ids1", split=split, root=repo)
            assert "cut the tree into" not in prompt and ("Split ids1" in prompt) == split
