# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""Reading a real plan's store into the cockpit's model."""

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import board, plan
from graphene_map.cockpit.look import NAMES
from graphene_map.cockpit.model import Model
from graphene_map.cockpit.read import FOLD_AFTER, KEEP_DONE, looker, read
from graphene_map.model import ToolEvent
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
    first.selected, first.moved, first.lens = "schema", True, "live"
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


def ago(seconds):
    """A log timestamp this many seconds ago, as the store keeps them."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def row(repo, node_id, kind, detail, seconds):
    with Store.open(repo) as store:
        store.log_node(node_id, ago(seconds), kind, "run:claude", BOT.session_id, None, detail)


def start(repo, node_id="ids"):
    with Store.open(repo) as store:
        plan.start(store, node_id, BOT, repo)


def edit(repo, name="api.py"):
    """What an agent's edit did to the checkout: git is what counts the files touched."""
    (repo / name).write_text(f"changed {name}\n")


def test_what_an_executor_did_is_the_agents_tail_pace_touched_files_and_stopped_writes(repo):
    plan_of(repo)
    start(repo)
    row(repo, "ids", "did", {"attempt": 1, "tool": "Read", "target": "api.py", "verb": "reading"}, 30)
    row(repo, "ids", "did", {"attempt": 1, "tool": "Edit", "target": "api.py", "verb": "editing"}, 20)
    row(repo, "ids", "did", {"attempt": 1, "tool": "Bash", "target": "pytest -q", "verb": "running"}, 10)
    row(repo, "ids", "said", {"attempt": 1, "text": "tests pass locally"}, 6)
    row(repo, "ids", "denied", {"attempt": 1, "path": "db/ids_2.py", "how": "outside scope"}, 3)
    edit(repo)
    t = look(repo).tasks["ids"]
    assert [e.kind for e in t.events] == ["read", "edit", "run", "said", "stop"]
    assert list(t.touched) == ["api.py"] and [p for p, _ in t.stopped] == ["db/ids_2.py"]
    assert t.agent in NAMES
    m = look(repo)
    said = ["edit api.py", "run  pytest -q", "says tests pass locally", "stopped db/ids_2.py"]
    assert m.tail(m.tasks["ids"], 4) == said
    assert 2 < m.quiet(m.tasks["ids"]) < 8
    assert m.pace(m.tasks["ids"]) != "▁" * 12


def test_only_the_attempt_that_is_going_now_counts(repo):
    plan_of(repo)
    start(repo)
    row(repo, "ids", "did", {"attempt": 1, "tool": "Edit", "target": "old.py", "verb": "editing"}, 50)
    row(repo, "ids", "did", {"attempt": 2, "tool": "Edit", "target": "api.py", "verb": "editing"}, 5)
    edit(repo)
    t = look(repo).tasks["ids"]
    assert list(t.touched) == ["api.py"] and [e.path for e in t.events] == ["api.py"]  # old.py is attempt 1's


def test_a_write_the_scope_has_since_taken_in_is_no_longer_stopped(repo):
    plan_of(repo)
    start(repo)
    row(repo, "ids", "denied", {"attempt": 1, "path": "api.py", "how": "outside scope"}, 5)  # in scope now
    assert look(repo).tasks["ids"].stopped == []


def test_a_task_with_no_move_yet_is_quiet_from_when_it_began_and_a_ready_one_has_no_agent(repo):
    plan_of(repo)
    start(repo)
    m = look(repo)
    assert m.tasks["ids"].events == [] and m.tasks["ids"].started > 0 and m.quiet(m.tasks["ids"]) < 5
    assert m.tasks["schema"].agent == "" and m.tasks["schema"].events == []


def test_an_agent_keeps_its_name_from_one_look_to_the_next(repo):
    plan_of(repo)
    start(repo)
    first = look(repo)
    assert look(repo, first).tasks["ids"].agent == first.tasks["ids"].agent


def say(repo, words, about="ids"):
    with Store.open(repo) as store:
        return board.note(store, words, ALEX, about=about)


def test_a_note_to_a_running_agent_is_sending_until_the_hook_delivers_it_and_then_heard(repo):
    plan_of(repo)
    start(repo)
    note = say(repo, "keep ids as strings")
    t = look(repo).tasks["ids"]
    assert [(text, heard) for text, _sent, heard in t.told] == [("keep ids as strings", 0.0)]  # sending…
    assert t.events[-1].kind == "you" and "keep ids as strings" in t.events[-1].text
    with Store.open(repo) as store:  # what the gate writes when it tells the session: the row and the ledger
        node = plan.get(store, "ids")
        store.log_node("ids", ago(0), "told", node.executor, node.session_id, None,
                       {"items": [note["id"]], "how": "write"})  # fmt: skip
        ledger = f"told:{node.session_id}:ids:{node.started_at}"
        store.set_meta(ledger, json.dumps([f"{note['id']}@{note['rev']}"]))
    told = look(repo).tasks["ids"].told
    assert len(told) == 1 and told[0][0] == "keep ids as strings" and told[0][2] > 0  # heard


def test_a_note_about_another_task_is_not_this_agents(repo):
    plan_of(repo)
    start(repo)
    say(repo, "for the schema only", about="schema")
    assert look(repo).tasks["ids"].told == []


def test_a_leafs_proofs_are_its_check_and_the_sign_off_it_asks_for(repo):
    plan_of(repo)
    with Store.open(repo) as store:
        asks = plan.get(store, "schema")
        asks.signoff = True
        store.put_node(plan.to_dict(asks))
        made = (("rev", plan.REVIEW, True), ("fin", plan.DONE, True), ("bare", plan.DONE, False))
        for node_id, state, signoff in made:
            leaf = plan.Node(node_id, node_id, scope=["x"], check="true", signoff=signoff, state=state)
            store.put_node(plan.to_dict(leaf))
    t = look(repo).tasks
    assert (t["ids"].checks, t["ids"].passed) == (1, 0)  # a check, not run yet
    assert (t["schema"].checks, t["schema"].passed) == (2, 0)  # the check, then you
    assert (t["rev"].checks, t["rev"].passed) == (2, 1)  # the check passed; your sign-off is the second
    assert (t["fin"].checks, t["fin"].passed) == (2, 2) and (t["bare"].checks, t["bare"].passed) == (1, 1)


def test_only_a_hooked_claude_code_agent_hears_a_note_while_it_works(repo):
    plan_of(repo)
    start(repo)
    assert look(repo).tasks["ids"].hears
    with Store.open(repo) as store:
        node = plan.get(store, "schema")
        node.state, node.executor, node.session_id = plan.RUNNING, "run:nemotron", None
        node.started_at = ago(5)
        store.put_node(plan.to_dict(node))
    assert not look(repo).tasks["schema"].hears


def test_a_leaf_that_came_back_says_why_and_offers_what_it_wanted(repo):
    plan_of(repo)
    with Store.open(repo) as store:
        plan.start(store, "ids", BOT, repo)
        plan.release(store, "ids", BOT, "the id lives in db/models.py", wants=["db/models.py"])
    t = look(repo).tasks["ids"]
    assert t.state == "came back" and t.note == "the id lives in db/models.py"
    assert "w" in t.offers and t.offers["w"][:2] == ["node", "widen"]


def test_what_a_finished_task_changed_is_what_its_last_finished_row_says(repo):
    plan_of(repo)
    with Store.open(repo) as store:
        done = plan.Node("fin", "finished", scope=["x"], check="true", state=plan.DONE)
        store.put_node(plan.to_dict(done))
        store.log_node("fin", ago(5), "finished", "alex", None, None, {"changed": ["a.py", "b.py"]})
    assert look(repo).tasks["fin"].changed == ["a.py", "b.py"]


def test_a_leaf_a_sessions_own_hooks_saw_is_read_from_the_tool_calls_they_recorded(repo):
    plan_of(repo)
    start(repo)
    sid = BOT.session_id
    with Store.open(repo) as store:
        for i, (tool, data, path) in enumerate(
            [("Read", {}, "api.py"), ("Edit", {}, "api.py"), ("Bash", {"command": "pytest -q"}, None)]
        ):
            at = ago(30 - 10 * i)
            store.add_event(ToolEvent(f"e{i}", sid, None, at, tool, data, None, True, None, path))
    edit(repo)
    t = look(repo).tasks["ids"]
    assert [e.kind for e in t.events] == ["read", "edit", "run"]
    assert list(t.touched) == ["api.py"] and t.events[-1].text == "pytest -q"


def test_files_touched_are_what_git_says_a_leaf_changed_and_the_ones_outside_its_scope_are_flagged(repo):
    plan_of(repo)
    start(repo)
    edit(repo, "api.py")
    edit(repo, "schema.py")  # the scope of `ids` is api.py: a shell command may write what the hook never saw
    m = look(repo)
    t = m.tasks["ids"]
    assert sorted(t.touched) == ["api.py", "schema.py"] and t.outside == ["schema.py"]
    assert m.allowed(t) == 1


def test_git_is_asked_again_only_after_a_few_seconds(repo):
    plan_of(repo)
    start(repo)
    edit(repo, "api.py")
    first = look(repo)
    edit(repo, "schema.py")
    assert sorted(look(repo, first).tasks["ids"].touched) == ["api.py"]  # not yet: a look a second later
    with Store.open(repo) as store:
        later = read(store, repo, first, now=first.clock + 6)
    assert sorted(later.tasks["ids"].touched) == ["api.py", "schema.py"]


def test_quiet_is_what_the_plan_counts_for_a_running_leaf_and_a_protected_folder_is_not_allowed(repo):
    plan_of(repo)
    start(repo)
    row(repo, "ids", "did", {"attempt": 1, "tool": "Read", "target": "api.py", "verb": "reading"}, 20)
    m = look(repo)
    assert 19 <= m.quiet(m.tasks["ids"]) <= 23
    m.protected = ["api.py"]
    m._allowed.clear()
    assert m.allowed(m.tasks["ids"]) == 0


def test_the_opener_graphene_watch_hands_in_may_say_exit_and_the_screen_stays_up(repo):
    import typer

    plan_of(repo)
    first = look(repo)

    def refuses():
        raise typer.Exit(1)

    assert looker(repo, refuses)(first) is first


def test_the_selection_follows_what_needs_you_until_you_choose_a_row(repo):
    plan_of(repo)
    first = look(repo)
    assert first.selected == first.order()[0][1]  # nothing chosen: the first row
    with Store.open(repo) as store:
        plan.start(store, "schema", BOT, repo)
        plan.release(store, "schema", BOT, "it needs db/models.py", wants=["db/models.py"])
    again = look(repo, first)
    assert again.tasks["schema"].state == "came back" and again.selected == "schema"  # yours now
    again.selected, again.moved = "docs", True  # the person chose
    with Store.open(repo) as store:
        assert read(store, repo, again).selected == "docs"


def test_files_the_agents_own_record_says_it_edited_count_even_when_git_cannot_say(repo):
    plan_of(repo)
    start(repo)
    row(repo, "ids", "did", {"attempt": 1, "tool": "Edit", "target": "api.py", "verb": "editing"}, 5)
    # nothing is changed on disk (a replay's checkout is not there): the record is what there is
    assert list(look(repo).tasks["ids"].touched) == ["api.py"]


def test_an_agent_has_the_same_name_running_back_and_done(repo):
    plan_of(repo)
    start(repo)
    running = look(repo).tasks["ids"].agent
    assert running in NAMES
    with Store.open(repo) as store:
        plan.release(store, "ids", BOT, "it needs db/models.py", wants=["db/models.py"])
    assert look(repo).tasks["ids"].state == "came back" and look(repo).tasks["ids"].agent == running
    with Store.open(repo) as store:  # finished: the node holds no session any more, its log still says who
        node = plan.get(store, "ids")
        node.state, node.session_id, node.executor = plan.DONE, None, None
        store.put_node(plan.to_dict(node))
    assert look(repo).tasks["ids"].agent == running


def test_a_leaf_with_proposed_children_is_still_a_task_as_the_engine_counts_it(repo):
    """`s` and a planner's split propose children under a leaf; until they are accepted the leaf is still the
    work an agent holds, and the row, the counters and x, t and w must reach it."""
    plan_of(repo)
    with Store.open(repo) as store:
        plan.start(store, "ids", BOT, repo)
        parts = [
            {"id": f"ids_{k}", "title": f"part {k}", "parent": "ids", "scope": [f"{k}.py"], "check": "true"}
            for k in "ab"
        ]
        plan.propose(store, parts, BOT)
    m = look(repo)
    assert m.tasks["ids"].state == "running" and m.tasks["ids_a"].state == "proposed"
    assert m.scoreboard()[1] == 1  # one running
