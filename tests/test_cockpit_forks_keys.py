# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The forks' keys: `f` forks the task under the cursor (its contract takes `forks: N`, then it runs as r
runs it), the digits pick a fork of a task in review whose hold forked, and the key bar and `?` say so. The
commands are recorded, not run: the engine that takes them is another lane's."""

import asyncio

from cockpit_scene import scene
from test_plan_cli import repo  # noqa: F401  (fixture)
from textual.widgets import Static

from graphene_map.cockpit.app import KEYS_TO_VERBS, Cockpit, fit_keys
from graphene_map.cockpit.help import help_text
from graphene_map.cockpit.model import Fork, Model, Question, Task
from graphene_map.cockpit.verbs import Doer


def doer_of(repo):
    """A Doer whose commands are written down instead of run: `ran` has each argv, `said` the news."""
    d = Doer(repo, [].append, lambda: None)
    d.ran, d.said = [], []
    d.say = d.said.append
    d.run = lambda argv, done="": (d.ran.append(argv), 0)[1]
    d.background = lambda argv: d.ran.append(argv)
    return d


def model_of(**states):
    m = Model("goal")
    m.tasks = {i: Task(i, i, states.get(i, "waiting"), ["api.py"]) for i in ("ids", "docs")}
    return m


def test_f_sets_the_tasks_forks_to_the_setting_or_three_and_then_runs_it_as_r_does(repo):
    d = doer_of(repo)
    d.fork(model_of(ids="ready"), "ids")
    assert d.ran == [["node", "set", "ids", "--forks", "3"], ["run", "--parallel", "4", "--node", "ids"]]
    m = model_of(ids="came back")
    m.forks = 4  # the setting, when it is 2 or more
    d.ran.clear()
    d.fork(m, "ids")
    assert d.ran[0] == ["node", "set", "ids", "--forks", "4"] and d.ran[1][0] == "run"
    d.ran.clear()
    d.run = lambda argv, done="": (d.ran.append(argv), 1)[1]  # `node set` refused (it has no check)
    d.fork(model_of(ids="ready"), "ids")
    assert d.ran == [["node", "set", "ids", "--forks", "3"]]  # nothing runs on a refusal


def test_f_on_a_task_not_still_to_do_or_on_no_task_runs_nothing_and_says_so(repo):
    d = doer_of(repo)
    for state in ("running", "review", "done", "proposed"):
        d.fork(model_of(ids=state), "ids")
        assert d.said[-1] == f"f forks a task still to do, and this one is {state}"
    d.fork(model_of(), "nowhere")
    assert d.said[-1].startswith("select a task to fork") and d.ran == []


def test_a_digit_on_a_task_in_review_whose_hold_forked_picks_that_fork_and_elsewhere_a_questions_option(repo):
    d = doer_of(repo)
    m = model_of(ids="review")
    m.tasks["ids"].forks = [Fork("a", "passed"), Fork("b", "passed"), Fork("c", "gave up")]
    d.pick(m, "ids", 2)
    assert d.ran == [["node", "pick", "ids", "b"]]
    d.pick(m, "ids", 4)
    assert d.said[-1] == "1-3 pick one of its forks" and len(d.ran) == 1
    m.tasks["ids"].forks = []  # a hold that did not fork: the digits are a question's, as before
    d.pick(m, "ids", 1)
    assert d.said[-1] == "pick needs a question and one of its numbers"
    m.questions = [Question("q", "tabs or spaces?", "spaces", ["tabs"], "ids")]
    d.pick(m, "q", 1)
    assert d.ran[-1] == ["board", "pick", "q", "1"]


def test_the_key_bar_offers_f_on_a_ready_or_came_back_task_and_the_digits_on_a_forked_review(tmp_path):
    async def go():
        m = scene()
        m.tasks["tests"].state = "ready"
        m.tasks["migrate"].forks = [Fork("a", "passed"), Fork("b", "passed")]  # in review, forked
        app = Cockpit(lambda previous: previous or m, root=tmp_path)
        async with app.run_test(size=(100, 30)):
            for sel, own in (
                ("tests", "r run · f fork · R run ready · t tell · i details"),
                ("migrate", "⏎ sign off · x reopen · 1-2 pick · i details"),
                ("ids", "t tell · w widen · x hand back · i details"),  # running: no f
            ):
                m.selected = sel
                app.paint()
                keys = str(app.query_one("#keys", Static).render()).strip()
                assert keys == own + " · g graph · m map · ? keys · q", sel
            m.selected = "tests"  # at 80 columns the ready row's bar gives up a screen's key, never f
            narrow = "r run · f fork · R run ready · t tell · i details · g graph · ? keys · q"
            assert fit_keys(app.row_keys(), 79) == narrow

    asyncio.run(go())


def test_f_is_the_fork_verb_and_with_no_repository_it_is_refused_as_every_verb_is():
    assert KEYS_TO_VERBS["f"] == "fork"

    async def go():
        m = scene()
        m.tasks["tests"].state, m.selected = "ready", "tests"
        app = Cockpit(lambda previous: previous or m)  # no root: a replay's refusal path, nothing to act on
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("f")
            assert m.latest() == app.refusal

    asyncio.run(go())


def test_the_help_says_what_f_and_the_digits_do_and_what_a_lettered_number_is_within_its_limits():
    said = help_text(76).plain
    keys = {line[10:16].strip(): line[16:].rstrip() for line in said.splitlines() if line[10:16].strip()}
    assert keys["f"] == "fork: N agents at once, the check keeps one"
    assert keys["1-9 a"].startswith("pick that option, or a fork")
    assert "3b a fork" in said and "D: the plan's direction" in said  # D's line gave f its room
    assert all(len(line) <= 76 for line in said.splitlines()) and len(said.splitlines()) <= 22
