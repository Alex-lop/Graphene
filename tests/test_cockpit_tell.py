# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""t tells the selected agent one line: a note about its task on the board, which its executor hears."""

import asyncio

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import board, plan
from graphene_map.cockpit.app import Canvas, Cockpit
from graphene_map.cockpit.read import looker
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")


def cockpit(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "ids", "title": "ids", "scope": ["api.py"], "check": "true"}], ALEX)
        plan.start(store, "ids", BOT, repo)
    return Cockpit(looker(repo, lambda: Store.open(repo)), every=60, root=repo)


async def type_in(pilot, text):
    for ch in text:
        await pilot.press("space" if ch == " " else ch)


def test_t_opens_a_box_the_row_shows_what_is_typed_and_enter_puts_the_note_on_the_board(repo):
    async def go():
        app = cockpit(repo)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("t")
            assert app.tell_open
            await type_in(pilot, "keep ids as strings")
            shown = "\n".join(line.plain() for line in app.query_one(Canvas).lines)
            assert "keep ids as strings▌" in shown
            await pilot.press("enter")
            assert not app.tell_open
            await pilot.pause(0.1)

    asyncio.run(go())
    with Store.open(repo) as store:
        [note] = [it for it in board.items(store) if it["kind"] == "note"]
    assert note["text"] == "keep ids as strings" and note["about"] == "ids"


def test_escape_closes_the_box_and_tells_nothing(repo):
    async def go():
        app = cockpit(repo)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("t")
            await type_in(pilot, "never mind")
            await pilot.press("escape")
            assert not app.tell_open

    asyncio.run(go())
    with Store.open(repo) as store:
        assert board.items(store) == []


def test_a_task_nobody_is_on_can_be_told_too_but_with_nothing_selected_it_says_so(repo):
    async def go():
        app = cockpit(repo)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "nothing"
            await pilot.press("t")
            assert not app.tell_open and app.model.latest() == "select a task to tell"

    asyncio.run(go())


def test_a_t_that_cannot_tell_takes_what_is_typed_next_so_no_letter_runs_as_a_key(repo):
    """t on no task opened nothing, so a sentence typed after it ran letter by letter as the cockpit's keys:
    u undid, d dropped, x handed back, s split. The line that opens instead sends nothing."""
    from graphene_map.tui import Ask

    async def go():
        app = cockpit(repo)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected, app.model.moved = "nothing", True
            await pilot.press("t")
            assert isinstance(app.screen, Ask)
            await type_in(pilot, "use dx")
            await pilot.press("enter")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, Ask) and app.model.tasks["ids"].state == "running"

    asyncio.run(go())
    with Store.open(repo) as store:
        assert board.items(store) == [] and plan.get(store, "ids").state == plan.RUNNING


def test_x_on_a_running_task_asks_first_and_only_y_hands_it_back(repo):
    from graphene_map.tui import Ask

    async def go():
        app = cockpit(repo)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected, app.model.moved = "ids", True
            await pilot.press("x")
            assert isinstance(app.screen, Ask)
            await pilot.press("escape")  # not handed back
            await pilot.pause(0.1)
            with Store.open(repo) as store:
                assert plan.get(store, "ids").state == plan.RUNNING
            await pilot.press("x")
            await type_in(pilot, "y")
            await pilot.press("enter")
            await pilot.pause(0.3)

    asyncio.run(go())
    with Store.open(repo) as store:
        assert plan.get(store, "ids").state != plan.RUNNING


def test_the_line_goes_to_the_task_it_was_opened_on_though_the_selection_moves(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "docs", "title": "docs", "scope": ["README.md"], "check": "true"}], ALEX)

    async def go():
        app = cockpit(repo)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "ids"
            await pilot.press("t")
            await type_in(pilot, "for ids")
            app.model.selected = "docs"  # what a look does when something else needs you more
            await pilot.press("enter")
            await pilot.pause(0.1)

    asyncio.run(go())
    with Store.open(repo) as store:
        [note] = [it for it in board.items(store) if it["kind"] == "note"]
    assert note["text"] == "for ids" and note["about"] == "ids"


def test_tab_in_the_tell_box_does_not_move_the_typing_away_from_it(repo):
    from textual.widgets import Input

    async def go():
        app = cockpit(repo)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("t")
            await pilot.press("tab")
            await type_in(pilot, "still here")
            assert app.query_one("#tell", Input).value == "still here" and app.tell_open

    asyncio.run(go())
