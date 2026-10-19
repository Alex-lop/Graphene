# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""t on a task an agent is on or still to take opens the box; on one nobody will take, a line says why."""

import asyncio

from cockpit_repo import cockpit, make_plan
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
