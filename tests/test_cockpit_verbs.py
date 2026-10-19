# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The cockpit's verbs against a real store: each is a graphene command, and the store says what it did."""

import time

import pytest
from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import board as B
from graphene_map import plan
from graphene_map.cockpit.model import Model, Question, Task
from graphene_map.cockpit.verbs import Doer, gist
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")


@pytest.fixture
def doer(repo):
    said = []
    d = Doer(repo, said.append, lambda: None)
    d.said = said
    return d


def plan_of(repo):
    with Store.open(repo) as store:
        plan.propose(
            store,
            [
                {"id": "ids", "title": "ids", "scope": ["api.py"], "check": "true"},
                {"id": "docs", "title": "docs", "scope": ["README.md"], "check": "true"},
            ],
            ALEX,  # a person's leaves are part of the plan at once
        )
        plan.propose(store, [{"id": "notes", "title": "notes", "scope": ["NOTES.md"], "check": "true"}], BOT)


def question(repo, text="tabs or spaces?"):
    with Store.open(repo) as store:
        item = B.add(store, "question", text, BOT, default="spaces", options=[{"text": "tabs"}], about="ids")
    return item["id"]


def items(repo):
    with Store.open(repo) as store:
        return B.items(store)


def model_of(qid=None, **states):
    m = Model("goal")
    scopes = {"ids": ["api.py"], "docs": ["README.md"]}
    m.tasks = {i: Task(i, i, states.get(i, "waiting"), scopes[i]) for i in scopes}
    if qid:
        m.questions = [Question(qid, "tabs or spaces?", "spaces", ["tabs"], "ids")]
    return m


def test_take_on_a_question_takes_its_default(repo, doer):
    plan_of(repo)
    qid = question(repo)
    doer.take(model_of(qid), qid)
    [item] = items(repo)
    assert B.reads(item) == "taken" and item["answer"] == "spaces"
    assert doer.said[-1].startswith("graphene board take")


def test_pick_chooses_an_option_by_number_and_answer_takes_the_words(repo, doer):
    plan_of(repo)
    qid = question(repo)
    doer.pick(model_of(qid), qid, 1)
    assert B.reads(items(repo)[0]) == "picked"
    second = question(repo, "another one?")
    doer.answer(model_of(second), second, "neither, use tabs")
    assert [it["answer"] for it in items(repo) if it["id"] == second] == ["neither, use tabs"]


def test_tell_puts_a_note_about_the_task_on_the_board(repo, doer):
    plan_of(repo)
    doer.tell(model_of(), "ids", "keep ids as strings")
    [note] = [it for it in items(repo) if it["kind"] == "note"]
    assert note["text"] == "keep ids as strings" and note["about"] == "ids"
    doer.tell(model_of(), "ids", "   ")
    assert len(items(repo)) == 1  # nothing said, nothing put up


def test_take_on_a_proposal_accepts_it(repo, doer):
    plan_of(repo)
    m = model_of()
    m.tasks["notes"] = Task("notes", "notes", "proposed", ["NOTES.md"])
    doer.take(m, "notes")
    with Store.open(repo) as store:
        assert plan.get(store, "notes").state != plan.PROPOSED


def test_widen_gives_a_task_the_paths_the_gate_stopped_and_nothing_more(repo, doer):
    plan_of(repo)
    with Store.open(repo) as store:
        plan.start(store, "ids", BOT, repo)
        denied = {"path": "db/ids_2.py", "how": "Write"}
        store.log_node("ids", plan._now(), "denied", BOT.name, BOT.session_id, None, denied)
    m = model_of(ids="running")
    m.tasks["ids"].stopped = [("db/ids_2.py", 1.0)]
    doer.widen(m, "ids")
    with Store.open(repo) as store:
        assert plan.get(store, "ids").scope == ["api.py", "db/ids_2.py"]  # the path, not its folder
    m.tasks["ids"].stopped = []
    doer.widen(m, "ids")
    assert doer.said[-1] == "nothing was stopped, so nothing to widen"


def test_a_leaf_that_came_back_offers_its_own_commands(repo, doer):
    plan_of(repo)
    m = model_of(ids="came back")
    doer.offer(m, "ids", "b")
    assert doer.said[-1].endswith("has no 'b' to offer: it did not come back wanting one")
    m.tasks["ids"].offers = {"n": ["plan"]}
    doer.offer(m, "ids", "n")
    assert doer.said[-1].startswith("graphene plan")


def test_pull_back_hands_a_running_leaf_back(repo, doer):
    plan_of(repo)
    with Store.open(repo) as store:
        plan.start(store, "ids", BOT, repo)
    doer.pull_back(model_of(ids="running"), "ids")
    with Store.open(repo) as store:
        assert plan.get(store, "ids").state != plan.RUNNING


def test_painting_a_folder_gives_it_and_painting_it_again_takes_it_back(repo, doer):
    plan_of(repo)
    m = model_of()
    doer.paint(m, "ids", "docs/")
    with Store.open(repo) as store:
        scope = list(plan.get(store, "ids").scope)
    assert "docs/**" in scope
    m.tasks["ids"].scope = scope
    doer.paint(m, "ids", "docs/")
    with Store.open(repo) as store:
        assert "docs/**" not in plan.get(store, "ids").scope


def test_a_slow_command_runs_as_a_process_of_its_own_and_says_when_it_ended(repo, doer):
    plan_of(repo)
    ended = []
    doer.later = lambda fn: (fn(), ended.append(1))
    doer.background(["plan"])
    for _ in range(100):
        if ended:
            break
        time.sleep(0.1)
    assert ended and "started" in doer.said[0]
    assert any("plan" in line for line in doer.said[1:])
    assert list((repo / ".graphene" / "runs").glob("plan-*.txt"))


def test_the_gist_names_the_command_and_says_the_first_line_it_said():
    assert gist(["board", "take", "q1"], 0, "q1: taken\nmore") == "graphene board take q1: taken"
    assert gist(["node", "drop", "x"], 1, "") == "✗ graphene node drop x"


def test_d_drops_a_proposal_or_a_question_and_never_an_accepted_leaf(repo, doer):
    plan_of(repo)
    qid = question(repo)
    m = model_of(qid, ids="running", docs="ready")
    m.tasks["notes"] = Task("notes", "notes", "proposed", ["NOTES.md"])
    doer.drop(m, "ids")
    doer.drop(m, "docs")
    assert "d drops a proposal or a question" in doer.said[-1] and ":node drop docs` does" in doer.said[-1]
    with Store.open(repo) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {
            "ids": plan.OPEN, "docs": plan.OPEN, "notes": plan.PROPOSED,
        }  # fmt: skip
    doer.drop(m, "notes")
    doer.drop(m, qid)
    with Store.open(repo) as store:
        assert plan.get(store, "notes").state == plan.DROPPED
    assert B.reads(items(repo)[0]) == "dropped"


def test_y_on_a_ready_leaf_starts_nothing_and_points_at_r(repo, doer):
    plan_of(repo)
    doer.take(model_of(ids="ready"), "ids")
    assert "r runs it" in doer.said[-1] and not any("graphene run" in line for line in doer.said)
