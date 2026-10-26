# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The commands the VS Code extension runs, as the CLI takes them from the person. The argv shapes are the
ones editors/vscode/src/commands.ts builds (pinned there by test/commands.test.ts); here the CLI itself is
the judge: each one lands, and reads back as the extension expects."""

import json

import pytest
from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)


def plan():
    return {n["id"]: n for n in json.loads(person("plan", "--json").stdout)["nodes"]}


def test_add_step_after_a_task_under_a_sub_goal_lands_at_once_for_the_person(repo):
    assert person("node", "add", "the API", "--id", "api").exit_code == 0  # a sub-goal: a node with no scope
    first = person("node", "add", "greet route", "--parent", "api", "--scope", "app.py", "--check", "pytest")
    assert first.exit_code == 0, first.output
    (greet,) = [n for n in plan().values() if n["title"] == "greet route"]
    assert greet["parent"] == "api" and greet["state"] == "open"  # the person's: in the plan, not a proposal
    after = person("node", "add", "farewell route", "--parent", "api", "--needs", greet["id"],
                   "--scope", "bye.py", "--scope", "tests/**", "--check", "pytest -q")
    assert after.exit_code == 0, after.output
    (farewell,) = [n for n in plan().values() if n["title"] == "farewell route"]
    assert farewell["needs"] == [greet["id"]] and farewell["scope"] == ["bye.py", "tests/**"]


def test_edit_step_replaces_the_title_the_scope_or_the_check(repo):
    assert person("node", "add", "one", "--id", "l1", "--scope", "api.py", "--check", "true").exit_code == 0
    assert person("node", "set", "l1", "--title", "the one").exit_code == 0
    assert person("node", "set", "l1", "--scope", "api.py", "--scope", "schema.py").exit_code == 0
    assert person("node", "set", "l1", "--check", "pytest -q").exit_code == 0
    node = plan()["l1"]
    assert (node["title"], node["scope"], node["check"]) == ("the one", ["api.py", "schema.py"], "pytest -q")


def test_drop_tell_and_stop_answer_as_the_extension_reads_them(repo):
    assert person("node", "add", "one", "--id", "l1", "--scope", "api.py", "--check", "true").exit_code == 0
    told = person("board", "note", "keep both routes", "--about", "l1")
    assert told.exit_code == 0, told.output
    dropped = person("node", "drop", "l1")
    assert dropped.exit_code == 0, dropped.output
    assert plan()["l1"]["state"] == "dropped"
    stop = person("run", "--stop")  # nothing is going: a plain answer, not a crash
    assert stop.exit_code in (0, 1) and stop.output.strip()


def test_accept_takes_one_proposal_by_id_and_accept_all_the_rest(repo):
    for t in ("a", "b"):
        assert agent("node", "add", t, "--id", t, "--scope", f"{t}.py", "--check", "true").exit_code == 0
    assert {n["state"] for n in plan().values()} == {"proposed"}
    one = person("plan", "accept", "a")
    assert one.exit_code == 0, one.output
    assert plan()["a"]["state"] == "open" and plan()["b"]["state"] == "proposed"
    assert person("plan", "accept").exit_code == 0
    assert plan()["b"]["state"] == "open"


def test_link_adds_to_what_a_task_waits_on_without_replacing_it(repo):
    if "--add-needs" not in person("node", "set", "--help").output:
        pytest.skip("`node set --add-needs` is the night's shared contract; not in this CLI yet")
    for t in ("a", "b", "c"):
        assert person("node", "add", t, "--id", t, "--scope", f"{t}.py", "--check", "true").exit_code == 0
    assert person("node", "set", "c", "--needs", "a").exit_code == 0
    linked = person("node", "set", "c", "--add-needs", "b")
    assert linked.exit_code == 0, linked.output
    assert plan()["c"]["needs"] == ["a", "b"]


def test_unlink_drops_one_need_and_keeps_the_rest_as_the_cli_reads_them(repo):
    for t in ("a", "b", "c", "d"):
        assert person("node", "add", t, "--id", t, "--scope", f"{t}.py", "--check", "true").exit_code == 0
    assert person("node", "set", "c", "--needs", "a", "--needs", "b").exit_code == 0
    assert person("node", "set", "c", "--add-needs", "d").exit_code == 0  # a link the extension has not seen
    dropped = person("node", "set", "c", "--drop-needs", "a")  # the × beside a, from a snapshot without d
    assert dropped.exit_code == 0, dropped.output
    assert plan()["c"]["needs"] == ["b", "d"]
    both = person("node", "set", "c", "--needs", "b", "--drop-needs", "b")
    assert both.exit_code == 2 and "one or the other" in both.output
