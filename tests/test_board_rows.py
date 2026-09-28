# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The board as rows above the tree (`board_rows`): under the goal, each open item is a row in the one
row grammar, the screen opens on the first, and a key on an item answers it with the `graphene board`
command the bottom line then names; on a node the same keys keep their meaning. Driven by keys,
headless, at 80x24 and 120x36, and checked through the store."""

import asyncio

import pytest
from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)
from test_tui import TREE, shown

from graphene_map import board as B
from graphene_map import board_rows as BR
from graphene_map import demo, view_tree
from graphene_map import plan as P
from graphene_map import views as V
from graphene_map.store import Store
from graphene_map.tui import Ask, Watch

SIZES = ((80, 24), (120, 36))
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


def drive(repo, steps, size):
    """Press each step's keys; after each, what the screen showed: the bottom line, the item or node
    under the cursor, the side pane and the outline's rows."""
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        seen = []
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for keys in steps:
                for key in keys:
                    await pilot.press(key)
                    await pilot.pause()
                await pilot.pause()
                row = app.board_row()
                seen.append({
                    "status": str(app.query_one("#status").render()).splitlines()[-1],
                    "at": row.id or row.kind if row is not None else app.selected(),
                    "detail": str(app.query_one("#detail").render()),
                    "tree": shown(app, app.query_one("#tree").scrollable_content_region),
                    "view": shown(app, app.query_one("#view").region),
                })  # fmt: skip
        return seen

    return asyncio.run(go())


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


@pytest.mark.parametrize("size", SIZES)
def test_the_open_items_are_rows_under_the_goal_and_the_screen_opens_on_the_first(repo, size):
    planned(repo)
    [seen] = drive(repo, [[]], size)
    rows = [r for r in seen["tree"] if r.strip()]
    assert "users come back with their ids" in rows[0]
    words = ["asks", "assumes", "risk", "leaves out", "note"]
    for row, item, word in zip(rows[1:6], OPEN, words, strict=True):
        assert f" {item} " in row and row.rstrip().endswith(word), (row, item, word)
        assert "◇" in row  # the person's move, as a node's `yours` reads
    assert "the API" in rows[6] and " api " in rows[6]  # then the tree, after the board
    assert seen["at"] == "which-id"  # the person meets the questions before the tree
    status = seen["status"]
    for said in ("y take: the row id", "1 pick", "d drop", "p park", "Enter answer", "a note"):
        assert said in status, (said, status)


@pytest.mark.parametrize("size", SIZES)
def test_each_key_answers_the_item_under_the_cursor_and_says_its_command(repo, size):
    planned(repo)
    steps = [
        ["1"],  # which-id: option 1, whose effect widens ids' scope
        ["y"],  # int-ids: confirmed
        ["p"],  # empty-check: parked
        ["d"],  # paging: dropped
        ["enter", *"keep it", "enter"],  # shape: answered in words
    ]
    seen = drive(repo, steps, size)
    board = items(repo)
    assert [board[i]["state"] for i in OPEN] == ["picked", "taken", "parked", "dropped", "answered"]
    assert board["which-id"]["answer"] == "a uuid column, added to schema.py"
    assert board["shape"]["answer"] == "keep it"
    with Store.open(repo) as store:
        assert "schema.py" in P.get(store, "ids").scope  # the option's then: applied
    said = [s["status"] for s in seen]
    assert said[0].startswith("graphene board pick which-id 1: picked which-id")
    assert said[1].startswith("graphene board take int-ids: taken int-ids")
    assert said[2].startswith("graphene board park empty-check: parked empty-check")
    assert said[3].startswith("graphene board drop paging: dropped paging")
    assert said[4].startswith("graphene board answer shape 'keep it': answered shape")
    # after each answer the cursor is on the next open item, and after the last, in the tree
    assert [s["at"] for s in seen] == ["int-ids", "empty-check", "paging", "shape", "api"]
    fold = [r for r in seen[-1]["tree"] if "settled" in r]
    assert fold and "3 settled · 1 parked · 1 dropped" in fold[0]


@pytest.mark.parametrize("size", SIZES)
def test_p_again_unparks_a_note_is_about_the_items_node_and_keys_on_a_node_keep_their_meaning(repo, size):
    planned(repo)
    steps = [
        ["p"],  # which-id parked; the cursor goes on to int-ids
        ["G", "k", "k", "k", "k"],  # up from the last row (goal, 4 items, the fold, api, ids, docs, schema)
        ["z", "o", "j"],  # the fold opened, the cursor on the parked item in it
        ["p"],  # unparked
        ["g", "g", "j", "a", *"mind the tests", "enter"],  # a note about ids, from which-id's row
        ["/", *"schema", "enter", "escape", "y"],  # on a node, y accepts it
    ]
    seen = drive(repo, steps, size)
    assert seen[1]["at"] == "fold" and seen[2]["at"] == "which-id"
    assert seen[3]["status"].startswith("graphene board unpark which-id: open which-id")
    board = items(repo)
    assert board["which-id"]["state"] == "open"
    [note] = [it for it in board.values() if it["kind"] == "note" and it["text"] == "mind the tests"]
    assert note["about"] == "ids" and not note["agent"] and B.reads(note) == "noted"
    assert seen[4]["status"].startswith("graphene board note 'mind the tests' --about ids")
    assert seen[5]["status"].startswith("graphene plan accept schema")
    with Store.open(repo) as store:
        assert P.get(store, "schema").state != P.PROPOSED


@pytest.mark.parametrize("size", SIZES)
def test_the_side_pane_shows_the_item_whole_and_what_its_answer_changed(repo, size):
    planned(repo)
    before, _, fold, after = drive(repo, [[], ["1"], ["G", *"kkkk"], ["z", "o", "j"]], size)
    pane = " ".join(before["detail"].split())
    for said in (
        "which id: the row id or a new uuid?", "which-id · question · open",
        "put up by a Claude Code session (5e55105e)", "y default the row id; schema.py already has it",
        "1 a uuid column, added to schema.py then: scope ids + schema.py", "about ids users returns ids",
    ):  # fmt: skip
        assert said in pane, (said, pane)
    assert after["at"] == "which-id"  # in the fold, opened
    pane = " ".join(after["detail"].split())
    for said in (
        "which-id · question · picked", "decided a uuid column, added to schema.py (option 1)",
        "changed ids: scope + schema.py", "told decided: which id: the row id or a new uuid?",
    ):  # fmt: skip
        assert said in pane, (said, pane)
    assert fold["at"] == "fold"
    assert "the board: 1 settled" in fold["detail"]


def test_the_views_goal_line_counts_the_open_items(repo, monkeypatch):
    monkeypatch.setitem(V.VIEWS, "tree", view_tree)
    planned(repo)
    [seen] = drive(repo, [["tab"]], (120, 36))
    assert "◇ 5 open on the board · users come back with their ids" in seen["view"][0]


def test_no_board_no_board_rows(repo):
    said = agent("plan", "propose", "-", input=TREE)
    assert said.exit_code == 0
    [seen] = drive(repo, [[]], (80, 24))
    assert seen["at"] is None and not any("settled" in r for r in seen["tree"])  # the goal, as before
    assert seen["status"].startswith("y accept it all")


def test_the_replay_refuses_every_board_key(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "LONG", 0.01)
    head, lines = demo.load(demo.SHIPPED)
    repo = demo.repository(tmp_path, head)
    app = demo.Replay(repo, head, lines)

    async def go():
        said = []
        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(200):
                if app.next == len(app.lines):
                    break
                await pilot.pause(0.05)
            with Store.open(repo) as store:
                B.add(store, "question", "which greeting?", P.Caller("planner", False), default="hello")
            app.refresh_plan()
            await pilot.press("g", "g", "j")
            await pilot.pause()
            assert app.board_row() is not None
            for key in ("y", "1", "d", "p", "enter", "a"):
                app.message = ""
                await pilot.press(key)
                await pilot.pause()
                status = str(app.query_one("#status").render()).splitlines()[-1]
                said.append((status, type(app.screen).__name__))
                if isinstance(app.screen, Ask):
                    await pilot.press("escape")
        return said

    assert asyncio.run(go()) == [(demo.REFUSED, "Screen")] * 6  # no line opened for words either
    with Store.open(repo) as store:
        assert [it["state"] for it in B.items(store)] == ["open"]
    assert BR.argv({"id": "x", "state": "parked"}, "p") == ["board", "unpark", "x"]
