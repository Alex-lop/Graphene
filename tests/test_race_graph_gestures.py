# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""Acting on the graph: `+` adds a step after the selected task (its title typed in one line, then `e` fills
it in), `L` on one task and then on another links them (the second waits on the first), Esc cancels, a cycle
is refused with its reason, and a replay refuses both as it refuses every verb. The graph's head says the
plan's width, the key bar and `?` list the keys."""

import asyncio

from cockpit_repo import ALEX, cockpit, node, type_in
from cockpit_scene import scene
from test_cockpit_replay import replay
from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import plan
from graphene_map.cockpit.app import ON_THE_GRAPH, Cockpit
from graphene_map.cockpit.help import help_text
from graphene_map.cockpit.model import Task
from graphene_map.cockpit.replay import REFUSED
from graphene_map.store import Store
from graphene_map.tui import Ask


def three(repo):
    """a and b under the sub-goal api (b waits on a), c at the top: a -> b -> goal, c -> goal."""
    with Store.open(repo) as store:
        plan.propose(store, [
            {"id": "api", "title": "the API"},
            {"id": "a", "title": "greet says hello", "scope": ["a.py"], "check": "true", "parent": "api"},
            {"id": "b", "title": "bye says goodbye", "scope": ["b.py"], "check": "true", "parent": "api",
             "needs": ["a"]},
            {"id": "c", "title": "count the users", "scope": ["c.py"], "check": "true"},
        ], ALEX)  # fmt: skip


def drive(repo, steps, screen="flow"):
    three(repo)
    app = cockpit(repo, screen)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            await steps(app, pilot)
            await pilot.pause(0.1)

    asyncio.run(go())
    return app


def head_of(app) -> str:
    return str(app.query_one("#head").render()).splitlines()[0]


def test_plus_asks_for_a_title_then_adds_a_step_after_the_task_under_its_sub_goal_and_selects_it(repo):
    async def steps(app, pilot):
        app.model.selected = "a"
        app.paint()
        await pilot.press("plus")
        await pilot.pause(0.1)
        assert isinstance(app.screen, Ask) and "a new step after greet says hello" in app.screen.prompt
        assert app.row_keys() == "Enter sends · Esc cancels"
        await type_in(pilot, "greet writes the tests")
        await pilot.press("enter")
        await pilot.pause(0.3)

    app = drive(repo, steps)
    with Store.open(repo) as store:
        [new] = [n for n in plan.nodes(store) if n.title == "greet writes the tests"]
    assert new.needs == ["a"] and new.parent == "api" and new.state == plan.OPEN  # a person's, in at once
    assert app.model.selected == new.id and app.view == "flow"
    said = "added greet writes the tests after greet says hello: e fills in its scope and check"
    assert app.model.feed[-1][1] == said
    assert node(repo, "a").needs == [] and node(repo, "b").needs == ["a"]  # nothing else moved


def test_plus_at_the_top_adds_a_step_with_no_parent_and_an_empty_title_adds_nothing(repo):
    async def steps(app, pilot):
        app.model.selected = "c"
        app.paint()
        await pilot.press("plus")
        await pilot.pause(0.1)
        await pilot.press("enter")  # nothing typed: nothing added
        await pilot.pause(0.2)
        await pilot.press("plus")
        await pilot.pause(0.1)
        await type_in(pilot, "d")
        await pilot.press("enter")
        await pilot.pause(0.3)

    drive(repo, steps)
    with Store.open(repo) as store:
        titles = {n.title: n for n in plan.nodes(store)}
    assert len(titles) == 5 and titles["d"].parent is None and titles["d"].needs == ["c"]


def test_l_on_a_then_on_b_makes_b_wait_on_a_and_the_head_says_what_to_do_meanwhile(repo):
    async def steps(app, pilot):
        app.model.selected = "a"
        app.paint()
        await pilot.press("L")
        await pilot.pause(0.1)
        assert app.linking == "a"
        told = "link: move to the task that waits on greet says hello, then L or ⏎ · Esc cancels"
        assert head_of(app).strip() == told
        assert app.row_keys().startswith("L or ⏎ link here · Esc cancels")
        assert "linking: move to the task that waits on greet says hello" in app.model.feed[-1][1]
        app.model.selected = "c"  # as the arrows move it
        await pilot.press("L")
        await pilot.pause(0.3)
        assert app.linking == "" and "link:" not in head_of(app)

    app = drive(repo, steps)
    assert node(repo, "c").needs == ["a"]
    said = "graphene node set c --add-needs a: count the users now waits on greet says hello"
    assert app.model.feed[-1][1] == said
    assert "c" in app.model.tasks and app.model.tasks["c"].needs == ["a"]  # the new arrow is drawn


def test_enter_ends_a_link_too_and_a_link_that_makes_a_cycle_is_refused_with_its_reason(repo):
    async def steps(app, pilot):
        app.model.selected = "b"  # b waits on a already
        app.paint()
        await pilot.press("L")
        await pilot.pause(0.1)
        app.model.selected = "a"
        await pilot.press("enter")  # a would wait on b: a cycle
        await pilot.pause(0.3)

    app = drive(repo, steps)
    assert node(repo, "a").needs == [] and app.linking == ""
    said = app.model.feed[-1][1]
    assert said.startswith("✗ graphene node set a --add-needs b: the plan has a cycle")
    assert "a -> b -> a" in said  # the cycle spelled out, as the CLI refuses it


def test_esc_cancels_a_link_and_stays_on_the_graph_and_a_task_cannot_wait_on_itself(repo):
    async def steps(app, pilot):
        app.model.selected = "a"
        app.paint()
        await pilot.press("L")
        await pilot.press("L")  # again on the same task
        await pilot.pause(0.1)
        assert app.linking == "a" and "cannot wait on itself" in app.model.feed[-1][1]
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.linking == "" and app.view == "flow" and "cancelled" in app.model.feed[-1][1]
        await pilot.press("escape")  # the second Esc leaves the graph, as before
        await pilot.pause(0.1)
        assert app.view == "cockpit"
        await pilot.press("g")
        await pilot.press("L")
        await pilot.press("c")  # leaving the graph ends the link begun there
        await pilot.pause(0.1)
        assert app.linking == ""

    drive(repo, steps)
    assert node(repo, "a").needs == [] and node(repo, "c").needs == []


def test_the_gestures_say_where_they_act_when_pressed_off_the_graph(repo):
    async def steps(app, pilot):
        await pilot.press("plus")
        await pilot.pause(0.1)
        assert app.model.feed[-1][1] == ON_THE_GRAPH["add-step"] and not isinstance(app.screen, Ask)
        await pilot.press("L")
        await pilot.pause(0.1)
        assert app.model.feed[-1][1] == ON_THE_GRAPH["link"] and app.linking == ""

    drive(repo, steps, screen="cockpit")
    with Store.open(repo) as store:
        assert len(plan.nodes(store)) == 4


def test_a_replay_refuses_both_gestures_as_it_refuses_every_verb(tmp_path):
    async def go():
        app, _head, _lines = replay(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("g")
            await pilot.pause(0.1)
            for key in ("plus", "L"):
                await pilot.press(key)
                await pilot.pause(0.1)
                assert app.model.feed[-1][1] == REFUSED and not isinstance(app.screen, Ask)
            assert app.linking == "" and "+ step" not in app.row_keys()

    asyncio.run(go())


def test_the_graphs_head_says_how_many_tasks_can_run_at_once_and_the_bar_and_the_help_list_the_keys():
    async def go():
        m = scene()  # four tasks wait on nothing between them: one wave of four, then tests
        app = Cockpit(lambda previous: previous or m, screen="flow", root=None)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            head = head_of(app)
            assert "4 can run at once" in head and "running · agent 1" in head and len(head.rstrip()) <= 80
            # on the graph a task's keys are its gestures, with its ⏎ move and the details: under 80 cells
            assert app.row_keys() == "+ step · L link · i details · c cockpit · m map · ? keys · q"
            m.selected = "docs"
            assert app.row_keys() == "⏎ accept · + step · L link · i details · c cockpit · m map · ? keys · q"
            m.selected = "q"  # a question has no box: its own keys
            assert app.row_keys().startswith("⏎ keep both · 1 pick · a answer · d drop · c cockpit")
            m.tasks["a"] = Task("a", "one", "running", why="API", agent="1", checks=1)  # one task: no width
            m.tasks = {"a": m.tasks["a"]}
            m.selected = "a"
            app.paint()
            await pilot.pause(0.1)
            assert "can run at once" not in head_of(app) and "for API" in head_of(app)

    asyncio.run(go())
    said = help_text(76).plain
    keys = {line[10:16].strip(): line[16:] for line in said.splitlines() if line[10:16].strip()}
    assert keys["+ L"].startswith("graph: + adds a step after; L on A, then on B")
    assert "q quits" in keys[": q"] and len(said.splitlines()) <= 22
