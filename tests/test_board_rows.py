# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The board as rows above the tree (`board_rows`): under the goal, each open item is a row in the one
row grammar, the screen opens on the first, and a key on an item answers it with the `graphene board`
command the bottom line then names; on a node the same keys keep their meaning. Driven by keys,
headless, at 80x24 and 120x36, and checked through the store."""

from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)
from test_tui import TREE

from graphene_map import board as B
from graphene_map.store import Store

BOARD = """\
question: which id: the row id or a new uuid?  [which-id]
    default: the row id; schema.py already has it
    option: a uuid column, added to schema.py
    then: scope ids + schema.py
    about: ids
assume: ids are integers  [int-ids]
risk: the check could pass on an empty list  [empty-check]
    default: add a sample user
leave out: pagination; nobody asked for it  [paging]
note: keep the response shape  [shape]
"""
OPEN = ["which-id", "int-ids", "empty-check", "paging", "shape"]


def planned(repo, board=BOARD):
    said = agent("plan", "propose", "-", input=TREE + board)
    assert said.exit_code == 0, said.output


def items(repo):
    with Store.open(repo) as store:
        return {it["id"]: it for it in B.items(store)}


def test_unpark_opens_a_parked_item_and_refuses_one_that_is_not(repo):
    planned(repo)
    assert person("board", "park", "paging").exit_code == 0
    said = person("board", "unpark", "paging")
    assert said.exit_code == 0 and said.stdout.startswith("open paging: pagination")
    assert items(repo)["paging"]["state"] == "open"
    said = person("board", "unpark", "paging")
    assert said.exit_code == 1 and "paging is not parked" in said.output
    assert person("plan", "undo").exit_code == 0  # one act, undone as any other
    assert items(repo)["paging"]["state"] == "parked"
