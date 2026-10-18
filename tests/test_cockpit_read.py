# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""Reading a real plan's store into the cockpit's model."""

import sqlite3
import time

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import board, plan
from graphene_map.cockpit.model import Model
from graphene_map.cockpit.read import FOLD_AFTER, KEEP_DONE, looker, read
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")


def plan_of(repo):
    with Store.open(repo) as store:
        plan.set_goal(store, "users come back with their ids", ALEX)
        plan.propose(
            store,
            [
                {"id": "api", "title": "The API"},
                {"id": "ids", "title": "users returns ids: each user has its id", "parent": "api",
                 "scope": ["api.py"], "check": "true"},
                {"id": "docs", "title": "document it", "parent": "api", "scope": ["README.md"],
                 "check": "true", "needs": ["ids"]},
                {"id": "schema", "title": "the schema", "scope": ["schema.py"], "check": "true"},
            ],
            ALEX,
        )  # fmt: skip
        plan.propose(store, [{"id": "notes", "title": "notes", "scope": ["NOTES.md"], "check": "true"}], BOT)


def look(repo, previous=None):
    with Store.open(repo) as store:
        return read(store, repo, previous)


def test_the_tasks_are_the_leaves_with_a_state_a_short_name_what_they_wait_on_and_why(repo):
    plan_of(repo)
    m = look(repo)
    assert m.goal == "users come back with their ids"
    assert set(m.tasks) == {"ids", "docs", "schema", "notes"}  # "api" is a sub-goal, not a row
    assert {i: t.state for i, t in m.tasks.items()} == {
        "ids": "ready", "docs": "waiting", "schema": "ready", "notes": "proposed",
    }  # fmt: skip
    assert m.tasks["ids"].title == "users returns ids"
    assert m.tasks["ids"].full.startswith("users returns ids:")
    assert m.tasks["docs"].needs == ["ids"] and m.tasks["ids"].why == "API" and m.tasks["schema"].why == ""
    assert m.tasks["ids"].scope == ["api.py"] and set(m.files) == {"api.py", "schema.py"}


def test_a_leaf_an_agent_holds_reads_as_running(repo):
    plan_of(repo)
    with Store.open(repo) as store:
        plan.start(store, "schema", BOT, repo)
    assert look(repo).tasks["schema"].state == "running"


def test_many_finished_tasks_are_a_count_and_the_latest_few_stay(repo):
    plan_of(repo)
    with Store.open(repo) as store:
        for i in range(FOLD_AFTER + 2):
            done = plan.Node(f"d{i}", f"finished {i}", scope=["x"], check="true", state=plan.DONE)
            done.finished_at = f"2026-10-16T00:00:{i:02d}Z"
            store.put_node(plan.to_dict(done))
    m = look(repo)
    kept = sorted(t.id for t in m.tasks.values() if t.state == "done")
    latest = [f"d{i}" for i in range(FOLD_AFTER + 2 - KEEP_DONE, FOLD_AFTER + 2)]
    assert len(kept) == KEEP_DONE and kept == latest
    assert m.folded_done == FOLD_AFTER + 2 - KEEP_DONE
    assert m.scoreboard()[2:] == (FOLD_AFTER + 2, FOLD_AFTER + 2 + 4)  # proven counts the folded ones


def test_what_the_person_chose_survives_the_next_look(repo):
    plan_of(repo)
    first = look(repo)
    first.selected, first.lens = "schema", "live"
    first.say("told fox")
    again = look(repo, first)
    assert again.selected == "schema" and again.lens == "live" and again.latest() == "told fox"
    assert again.files is first.files  # git's list is not read again within the minute
    first.selected = "gone"
    assert look(repo, first).selected in {rid for _, rid in again.order()}  # falls to the first row


def test_a_store_too_busy_to_open_leaves_the_screen_as_it_was_and_says_so(repo):
    plan_of(repo)
    first = look(repo)

    def busy():
        raise sqlite3.OperationalError("database is locked")

    again = looker(repo, busy)(first)
    assert again is first and "did not open" in again.feed[-1][1]
    assert isinstance(looker(repo, busy)(None), Model)


def test_the_clock_is_now_unless_a_look_is_told_otherwise(repo):
    plan_of(repo)
    with Store.open(repo) as store:
        assert abs(read(store, repo).clock - time.time()) < 5
        assert read(store, repo, now=42.0).clock == 42.0


def put_up(repo, kind, text, **more):
    with Store.open(repo) as store:
        return board.add(store, kind, text, BOT, **more)["id"]


def test_what_waits_on_the_board_is_a_question_row_with_its_default_and_numbered_options(repo):
    plan_of(repo)
    tabs = [{"text": "tabs"}]
    asked = put_up(repo, "question", "tabs or spaces?", default="spaces", options=tabs, about="ids")
    [q] = look(repo).questions
    assert (q.id, q.text, q.default, q.options, q.about, q.kind) == (
        asked, "tabs or spaces?", "spaces", ["tabs"], "ids", "question",
    )  # fmt: skip
    assert look(repo).order()[0] == ("question", asked)  # before every task


def test_an_assumption_and_a_risk_read_as_confirm_and_noted_and_a_settled_item_is_not_a_row(repo):
    plan_of(repo)
    asking = put_up(repo, "question", "anything else?")  # with `board: auto` the others show once one asks
    assumed = put_up(repo, "assume", "ids stay strings")
    risky = put_up(repo, "risk", "the migration may lose rows")
    by_id = {q.id: q for q in look(repo).questions}
    assert by_id[assumed].default == "confirm" and by_id[risky].default == "noted"
    with Store.open(repo) as store:
        board.take(store, assumed, ALEX)
    assert {q.id for q in look(repo).questions} == {asking, risky}


def test_the_board_asks_nothing_while_only_an_assumption_is_open(repo):
    plan_of(repo)
    put_up(repo, "assume", "ids stay strings")
    assert look(repo).questions == []
