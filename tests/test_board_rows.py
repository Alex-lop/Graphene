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
from graphene_map import settings as S
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
ALEX = P.Caller("alex", True)
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
                    "lines": str(app.query_one("#status").render()).splitlines(),
                    "at": row.id or row.kind if row is not None else app.selected(),
                    "detail": str(app.query_one("#detail").render()),
                    "tree": shown(app, app.query_one("#tree").scrollable_content_region),
                    "view": shown(app, app.query_one("#view").region),
                    "screen": type(app.screen).__name__,
                })  # fmt: skip
        return seen

    return asyncio.run(go())


def test_unpark_opens_a_parked_item_and_refuses_one_that_is_not(repo):
    planned(repo)
    assert person("board", "park", "paging").exit_code == 0
    said = person("board", "unpark", "paging")
    assert said.exit_code == 0 and said.stdout == "open paging\n"
    assert items(repo)["paging"]["state"] == "open"
    said = person("board", "unpark", "paging")
    assert said.exit_code == 1 and "paging is open, not parked" in said.output
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
    # at 80 columns the default's words give way to Tab and ? (walk 2026-09-28, first 16)
    take = "y take: the row id" if size[0] >= 120 else "y take"
    for said in (take, "1 pick", "d drop", "p park", "Enter answer", "a note", "Tab view", "? help"):
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
        ["y"],  # one y too many: on the settled fold it does nothing
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
    # after each answer the cursor is on the next open item, and after the last on the settled fold,
    # not on a node where the same y would accept it (walk 2026-09-28: a quick `y y y` or `a` there
    # edited the plan)
    assert [s["at"] for s in seen] == ["int-ids", "empty-check", "paging", "shape", "fold", "fold"]
    with Store.open(repo) as store:
        assert all(n.state == P.PROPOSED for n in P.nodes(store))  # the extra y accepted nothing
    fold = [r for r in seen[-2]["tree"] if "settled" in r]
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
        "changed ids: scope + schema.py", "told to the executors of ids and under it, as a decided: line",
    ):  # fmt: skip
        assert said in pane, (said, pane)
    assert fold["at"] == "fold"
    assert "the board: 1 settled" in fold["detail"]


def test_question_mark_on_an_item_is_help_and_on_a_node_the_planners_chooser(repo):
    planned(repo)
    item, _, node = drive(repo, [["?"], ["escape"], ["/", *"schema", "enter", "?"]], (80, 24))
    assert item["at"] == "which-id" and item["screen"] == "Help"  # an item's own keys are on the bottom line
    assert node["at"] == "schema" and node["screen"] == "Ask"  # talking on the tree: w s m a, or words


def test_the_views_goal_line_counts_the_open_items(repo, monkeypatch):
    monkeypatch.setitem(V.VIEWS, "tree", view_tree)
    planned(repo)
    [seen] = drive(repo, [["tab"]], (120, 36))
    assert "users come back with their ids · ◇ 5 open on the board" in seen["view"][0]


def test_no_board_no_board_rows(repo):
    said = agent("plan", "propose", "-", input=TREE)
    assert said.exit_code == 0
    [seen] = drive(repo, [[]], (80, 24))
    assert seen["at"] is None and not any("settled" in r for r in seen["tree"])  # the goal, as before
    assert seen["status"].startswith("y accept it all")


@pytest.mark.parametrize("size", SIZES)
def test_a_board_that_asks_nothing_has_no_rows_no_line_and_no_count(repo, size):
    planned(repo)
    assert person("board", "take").exit_code == 0  # every default, in one act
    assert person("board", "drop", "shape").exit_code == 0  # the agent's note: no default, so dropped
    [seen] = drive(repo, [[]], size)
    assert seen["at"] is None  # the goal, as with no board at all
    assert not any(f" {i} " in r or "settled" in r for r in seen["tree"] for i in OPEN), seen["tree"]
    assert "on the board" not in " ".join(seen["lines"])
    shown = person("plan").stdout
    assert "the board" not in shown and "on the board" not in shown


def test_with_board_auto_the_board_shows_only_while_a_question_is_open(repo):
    planned(repo, BOARD.replace("question: which id", "assume: which id").replace(
        "    option: a uuid column, added to schema.py\n    then: scope ids + schema.py\n", ""))
    with Store.open(repo) as store:
        S.apply(store, "board: auto\n", ALEX)
        assert not B.asks(store) and B.waiting(store) == (0, None)
    [seen] = drive(repo, [[]], (80, 24))
    assert seen["at"] is None and not any(" int-ids " in r for r in seen["tree"])
    assert "the board" not in person("plan").stdout
    accepted = person("plan", "accept").stdout  # what was not shown takes its default, in one line
    assert "took the defaults of which-id, int-ids, empty-check, paging, left open" in accepted
    agent("board", "note", "is the id a string?")  # a note is no question: auto still shows nothing
    with Store.open(repo) as store:
        assert not B.asks(store)
        B.add(store, "question", "strings or ints?", P.Caller("planner:script", False, "s1"), default="ints")
        assert B.asks(store) and B.waiting(store)[0] == 3  # a question: the board shows all that is open
    [seen] = drive(repo, [[]], (80, 24))
    assert seen["at"] == "strings-or-ints"


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
            app.exit()  # as `q` or a closed terminal ends a replay, so no tick lands while it is torn down
            await pilot.pause()
        return said

    assert asyncio.run(go()) == [(demo.REFUSED, "Screen")] * 6  # no line opened for words either
    with Store.open(repo) as store:
        assert [it["state"] for it in B.items(store)] == ["open"]
    assert BR.argv({"id": "x", "state": "parked"}, "p") == ["board", "unpark", "x"]


@pytest.mark.parametrize("size", SIZES)
def test_after_an_answer_the_next_items_keys_stay_under_what_the_command_said(repo, size):
    """Four trials lost the key hints: an answer moved the cursor onto the next item and the bottom
    line still held the command, so the next item's keys were nowhere. Now the keys have a line of
    their own and the command's words take a third."""
    planned(repo)
    [seen] = drive(repo, [["y"]], size)
    _, keys, said = seen["lines"]
    assert seen["at"] == "int-ids"
    assert keys.startswith("y confirm · d drop · p park"), keys  # the assumption's own keys
    assert said.startswith("graphene board take which-id")


def test_board_items_are_counted_apart_from_the_plan(repo):
    """rows counted the board's open items into `you: N` with nothing saying so (`you: 6` against the
    view candidate's `you: 1`); they do wait on the person, so they stay counted, but apart."""
    planned(repo)
    for size, said in (((80, 24), "you: 2 + 5 on the board · "), ((120, 36), "waiting on you: 2 + 5 on")):
        [seen] = drive(repo, [[]], size)
        assert seen["lines"][0].startswith(said), seen["lines"]


def test_the_standing_conditions_are_a_dim_row_at_the_root_and_on_a_views_goal_line(repo, monkeypatch):
    """Lane B's settings a person states once show where the plan starts: a row of their own above the
    board's items, no key acting on it, and first on the tree's and the graph's goal line."""
    planned(repo)
    with Store.open(repo) as store:
        S.apply(store, "protected: secrets/**\nreadonly: vendor/**\nnever: add a dependency\n", ALEX)
        assert (
            BR.standing(store)
            == "conditions: protected secrets/** · read-only vendor/** · never add a dependency"
        )
    first, standing, view = drive(repo, [[], ["k"], ["tab"]], (120, 36))
    rows = [r for r in first["tree"] if r.strip()]
    assert "conditions: protected secrets/**" in rows[1] and " which-id " in rows[2]  # above the items
    assert first["at"] == "which-id"  # the screen still opens on the first item
    assert standing["at"] == "standing" and "graphene config shows them" in standing["status"]
    assert standing["detail"].startswith("conditions: protected secrets/**")
    goal = view["view"][0]
    said = "users come back with their ids · ◇ 5 open on the board · conditions: protected secrets/**"
    assert goal.lstrip().startswith(said), goal
    with Store.open(repo) as store:
        S.apply(store, "size: auto\n", ALEX)
        assert BR.standing(store) is None


@pytest.mark.parametrize("size", SIZES)
def test_a_views_first_line_is_the_goal_whole_then_the_board_and_the_conditions(repo, size, monkeypatch):
    """Walks 2026-09-28 (alex 16, judge 24): the tree's and the graph's first line read `conditions:
    protected secrets/**, .env · read-only legacy/** · the Northwind…`, so at 80 columns the goal was
    cut, and at 120 it read like one more condition. The goal comes first; what follows it is cut."""
    monkeypatch.setitem(V.VIEWS, "tree", view_tree)
    planned(repo)
    with Store.open(repo) as store:
        S.apply(store, "protected: secrets/**, .env\nreadonly: legacy/**, vendor/**\n", ALEX)
    [seen] = drive(repo, [["tab"]], size)
    goal = seen["view"][0].strip()
    assert goal.startswith("users come back with their ids · ◇ 5 open on the board · conditions"), goal
    assert seen["at"] is None and seen["lines"][1].startswith("y accept it all")  # the cursor: the goal


@pytest.mark.parametrize("size", SIZES)
def test_plus_and_minus_ask_the_plan_again_finer_and_coarser(repo, size, monkeypatch):
    """One key re-asks the last sentence finer, one coarser: `graphene ask --finer` in the background,
    named on the bottom line with its flag first, so a cut line still says which. Nothing asked yet:
    the line says so and nothing starts."""
    planned(repo)
    started = []

    def background(self, argv):
        started.append(argv)
        self.message = f"graphene {' '.join(argv)}: started"
        self.say_status()

    monkeypatch.setattr(Watch, "background", background)
    [none] = drive(repo, [["plus"]], size)
    assert not started and none["status"].startswith("✗ graphene ask --finer: no plan was asked for yet")
    with Store.open(repo) as store:
        store.log_node("*", P._now(), "asked", "alex", None, None, {"note": "users come back with ids"})
    finer, coarser = drive(repo, [["plus"], ["minus"]], size)
    assert started == [
        ["ask", "--finer", "users come back with ids"],
        ["ask", "--coarser", "users come back with ids"],
    ]
    assert finer["status"].startswith("graphene ask --finer") and coarser["status"].startswith(
        "graphene ask --coarser"
    )


def test_on_the_persons_own_note_the_bottom_line_names_every_key_that_acts(repo, size=(80, 24)):
    assert person("board", "note", "keep", "the", "shape").exit_code == 0
    [note] = items(repo).values()
    hints = BR.hints(note, 80)
    assert hints == ["noted: u undoes your last act", "d drop", "p park", "a note"]
    for act in (["take"], ["answer", note["id"], "yes"], ["pick", note["id"], "1"]):  # y, Enter, 1: not named
        refused = person("board", *act if len(act) > 1 else [*act, note["id"]])
        assert refused.exit_code == 1 and "your note, told as you wrote it" in refused.stderr, refused.output
    assert person("board", "park", note["id"]).exit_code == 0  # p, named: parks it
    assert items(repo)[note["id"]]["state"] == "parked"


def test_the_fold_says_who_is_told_in_words_and_a_long_answer_hangs_under_its_own_row(repo):
    """Walk 2026-09-28 (judge 18): the fold's pane read "told to executors as decided: lines; parked and
    dropped are told to no one", and an answer too long for its line went on at column 1, under the ✓."""
    planned(repo)
    with Store.open(repo) as store:
        B.answer(store, "which-id", "the row id, which schema.py already has and every caller reads", ALEX)
        board, by_id = BR.read(store, shown=True), {n.id: n for n in P.nodes(store)}  # the rows on screen
    said = BR.pane(board, BR.FOLD, by_id, 40).plain.splitlines()
    told = "settled answers are told to the executor of the leaf they are about, in its contract; parked"
    assert told in " ".join(" ".join(said).split())
    row = said.index(next(line for line in said if line.startswith("✓ answered which-id")))
    assert said[row + 1].startswith("  ") and said[row + 1].strip()  # hangs under its own row
