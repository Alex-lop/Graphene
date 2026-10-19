# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""A accepts every proposal at once, after one line that says how many: the plan you read, in one key."""

import asyncio

from cockpit_repo import BOT, cockpit, items, make_plan, node, type_in
from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import board, plan
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


def test_enter_on_the_last_proposal_asks_first_as_it_takes_the_defaults_of_the_open_questions(repo):
    """`plan accept` takes the board's defaults once no proposal is left, so ⏎ on the last one is A: it asks
    first, in A's words. ⏎ on a proposal that leaves another accepts it at once, and takes no default."""
    make_plan(repo, question=True, proposal=True)
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "more", "title": "more", "scope": ["MORE.md"], "check": "true"}], BOT)
    app = cockpit(repo)

    async def go():
        async with app.run_test(size=(110, 30)) as pilot:
            await pilot.pause(0.1)
            app.model.selected = "notes"
            await pilot.press("enter")  # another proposal is left: no question, and no default taken
            await pilot.pause(0.3)
            assert type(app.screen).__name__ != "Ask" and node(repo, "notes").state == plan.OPEN
            app.model.selected = "more"
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert type(app.screen).__name__ == "Ask"
            assert app.screen.prompt == "accept 1 proposed task and the defaults of 1 question? y and Enter"
            await pilot.press("escape")  # no y: nothing is accepted, nothing is taken
            await pilot.pause(0.2)
            assert node(repo, "more").state == plan.PROPOSED and board.reads(items(repo)[0]) == "open"
            await pilot.press("enter")
            await pilot.pause(0.2)
            await type_in(pilot, "y")
            await pilot.press("enter")
            await pilot.pause(0.3)

    asyncio.run(go())
    assert node(repo, "more").state == plan.OPEN and board.reads(items(repo)[0]) == "taken"
