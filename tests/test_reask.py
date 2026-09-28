# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene ask --finer/--coarser` (+ and - on the screens) asks the last sentence again, with the
planner that ask started."""

import json

from test_ask import GOOD, planner
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import ask as A
from graphene_map.plan import Caller
from graphene_map.store import Store

ME = Caller("person:alex", True, None)


def prompts(tmp_path) -> list[str]:
    return [json.loads(line)["prompt"] for line in (tmp_path / "seen.jsonl").read_text().splitlines()]


def test_a_reask_starts_the_planner_the_ask_named_not_the_repos(repo, tmp_path, monkeypatch):
    mine = planner(tmp_path, GOOD, monkeypatch)
    assert person("ask", "add ids", "--with", mine).exit_code == 0
    with Store.open(repo) as store:
        store.set_meta("planner", "no-such-planner")  # the repo's planner changes after the ask
        argv = A.reask_argv(store, "finer")
    assert argv == ["graphene", "ask", "add ids", "--with", mine, "--finer"]
    again = person(*argv[1:])
    assert again.exit_code == 0, again.output
    assert len(prompts(tmp_path)) == 2  # the script ran again; no-such-planner never started


def test_an_ask_without_with_keeps_the_planner_it_started(repo, tmp_path, monkeypatch):
    with Store.open(repo) as store:
        store.set_meta("planner", planner(tmp_path, GOOD, monkeypatch))
    assert person("ask", "add ids").exit_code == 0
    with Store.open(repo) as store:
        first = store.meta("planner")
        store.set_meta("planner", "codex")
        assert A.reask_argv(store, "coarser") == ["graphene", "ask", "add ids", "--with", first, "--coarser"]
