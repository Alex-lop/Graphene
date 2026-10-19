# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""t on a task an agent is on or still to take opens the box; on one nobody will take, a line says why."""

import asyncio

from cockpit_repo import cockpit, make_plan, type_in
from test_plan_cli import repo  # noqa: F401  (fixture)


def test_t_on_a_task_nobody_is_on_yet_opens_the_box_and_on_a_finished_one_says_what_to_do(repo):
    make_plan(repo)  # ids is ready, docs waits on it: nobody is on either yet
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "docs"
            await pilot.press("t")
            assert app.tell_open and app.tell_for == "docs"
            await pilot.press("escape")
            app.model.tasks["docs"].state = "done"
            await pilot.press("t")
            assert not app.tell_open and app.model.latest() == (
                "docs is done: x reopens it, and its next agent is told why"
            )

    asyncio.run(go())


def test_the_line_that_takes_words_meant_for_nobody_says_in_the_key_bar_that_nothing_is_sent(repo):
    """t on a finished task opens a line so that what is typed next does not run as keys; its key bar said
    "Enter sends", and after Enter it kept saying so over the rows until the next look."""
    make_plan(repo)
    app = cockpit(repo)

    def keys():
        return str(app.query_one("#keys").render()).strip()

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "docs"
            app.model.tasks["docs"].state = "done"
            await pilot.press("t")
            await pilot.pause(0.2)
            assert type(app.screen).__name__ == "Ask" and keys() == "nothing is sent · Esc or Enter closes"
            await type_in(pilot, "also index the column")
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert type(app.screen).__name__ != "Ask" and keys().startswith("i details · x reopen")

    asyncio.run(go())
