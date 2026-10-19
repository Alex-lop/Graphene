# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""A accepts every proposal at once, after one line that says how many: the plan you read, in one key."""

import asyncio

from cockpit_repo import BOT, cockpit, make_plan, node, type_in
from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import plan
from graphene_map.store import Store


def test_capital_a_accepts_every_proposal_once_y_says_so_and_nothing_without_it(repo):
    make_plan(repo, proposal=True)
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "more", "title": "more", "scope": ["MORE.md"], "check": "true"}], BOT)
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("A")
            await pilot.pause(0.2)
            assert type(app.screen).__name__ == "Ask" and "accept 2 proposed tasks?" in app.screen.prompt
            await pilot.press("escape")  # no y: nothing is accepted
            await pilot.pause(0.2)
            assert node(repo, "notes").state == plan.PROPOSED
            await pilot.press("A")
            await pilot.pause(0.2)
            await type_in(pilot, "y")
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app.model.latest().startswith("graphene plan accept")

    asyncio.run(go())
    assert node(repo, "notes").state == node(repo, "more").state == plan.OPEN


def test_capital_a_with_nothing_proposed_says_so_and_asks_nothing(repo):
    make_plan(repo)
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("A")
            await pilot.pause(0.2)
            assert type(app.screen).__name__ != "Ask"
            assert app.model.latest() == "nothing to accept: no task is proposed"

    asyncio.run(go())
