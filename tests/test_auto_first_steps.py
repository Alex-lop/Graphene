# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""A stranger's first `graphene auto`, as the night's walk found it: before `graphene init` it named `--with`,
which is the executor's flag here, and it had already turned auto on for a command that started nothing; with
no Token Factory key the reason came wrapped in three others."""

from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import settings as S
from graphene_map.store import Store


def test_no_planner_chosen_says_planner_and_leaves_the_envelope_as_it_was(repo):
    said = person("auto", "add a --top N option", "--budget", "2")
    assert said.exit_code == 1
    assert "no planner is chosen for this repo" in said.output and "`--planner claude`" in said.output
    assert "--with claude" not in said.output
    with Store.open(repo) as store:
        assert (S.auto(store), S.budget(store)) == ("off", None)  # nothing started, nothing turned on


def test_no_executor_chosen_says_with(repo):
    said = person("auto", "add a --top N option", "--planner", "claude")
    assert said.exit_code == 1
    assert "no executor is chosen for this repo" in said.output and "`--with claude`" in said.output
    with Store.open(repo) as store:
        assert S.auto(store) == "off"


def test_a_planner_that_cannot_start_says_why_in_one_reason(repo, monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    said = person("auto", "add a --top N option", "--planner", "nemotron", "--with", "nemotron")
    assert said.exit_code == 3
    line = [x for x in said.output.splitlines() if x.startswith("waits for you: ")][-1]
    assert line.startswith("waits for you: the planner could not start: NEBIUS_API_KEY is not set"), line
    assert "nothing was added" not in line and "(exit 3)" not in line
    assert "`graphene key set` keeps one" in line  # what to do, in the same line
    shown = person("plan").output  # the next look says the same, and how auto mode goes on from there
    assert "auto · round 1 of 3 · waits: the planner could not start: NEBIUS_API_KEY is not set" in shown
    assert shown.rstrip().count("then `graphene auto` goes on") == 1
