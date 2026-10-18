"""A real throwaway plan to drive the cockpit against, and typing into it."""

from graphene_map import board, plan
from graphene_map.cockpit.app import Cockpit
from graphene_map.cockpit.read import looker
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")


def make_plan(repo, *, running=False, question=False, proposal=False):
    """ids (api.py) and docs (README.md, waits on ids); optionally ids is running, a question about it is on
    the board, and an agent has proposed `notes`."""
    with Store.open(repo) as store:
        plan.propose(
            store,
            [
                {"id": "ids", "title": "ids", "scope": ["api.py"], "check": "true"},
                {"id": "docs", "title": "docs", "scope": ["README.md"], "check": "true", "needs": ["ids"]},
            ],
            ALEX,
        )
        if running:
            plan.start(store, "ids", BOT, repo)
        if question:
            opts = [{"text": "tabs"}]
            board.add(store, "question", "tabs or spaces?", BOT, default="spaces", options=opts, about="ids")
        if proposal:
            notes = {"id": "notes", "title": "notes", "scope": ["NOTES.md"], "check": "true"}
            plan.propose(store, [notes], BOT)


def cockpit(repo, screen="cockpit"):
    return Cockpit(looker(repo, lambda: Store.open(repo)), every=60, root=repo, screen=screen)


async def type_in(pilot, text):
    for ch in text:
        await pilot.press("space" if ch == " " else ch)


def items(repo):
    with Store.open(repo) as store:
        return board.items(store)


def node(repo, node_id):
    with Store.open(repo) as store:
        return plan.get(store, node_id)
