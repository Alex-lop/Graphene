# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The seam where a view other than the outline shows the plan (views.py, and the `#view` pane in
`graphene watch`): driven by keys at 80x24 and 120x36 with a small view registered here, a grid of
two cells a line, as the graph views will be. Every key acts on the node under the view's cursor, the
bottom line says the command, and a view that does not fit gives way to the outline."""

import asyncio

import pytest
from rich.text import Text
from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)
from test_tui import proposed, shown, states

from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map import views as V
from graphene_map.store import Store
from graphene_map.tui import Watch

SIZES = ((80, 24), (120, 36))


class Grid:
    """Two cells a line, each half the width, in the plan's order: glyph, id, the title cut to fit.
    It does not fit below 50 columns."""

    least = 50

    @classmethod
    def suits(cls, nodes, width, height) -> int:
        return 1

    @classmethod
    def draw(cls, nodes, words, goal, width, height, cursor):
        if width < cls.least:
            return None
        half, lines, at = width // 2, [Text(T.elide(goal, width), "bold")], {}
        for k, n in enumerate(nodes):
            line, first = 1 + k // 2, (k % 2) * half
            glyph, colour = P.look(words[n.id])
            cell = Text(f"{glyph} {n.id} {T.elide(n.title, half - len(n.id) - 5)}", colour)
            if n.id == cursor:
                cell.stylize("reverse")
            if len(lines) <= line:
                lines.append(Text())
            lines[line].append(" " * (first - lines[line].cell_len))
            lines[line].append_text(cell)
            at[n.id] = (line, first, first + cell.cell_len - 1)
        return V.Drawn(lines, at, [n.id for n in nodes], f"{len(nodes)} in a grid")


class Wide(Grid):
    """The same grid, fitting only a terminal wider than any here: never fits."""

    least = 400

    @classmethod
    def suits(cls, nodes, width, height) -> int:
        return 5


@pytest.fixture
def grid(monkeypatch):
    monkeypatch.setitem(V.VIEWS, "grid", Grid)


def look(repo, keys, size, view=None):
    """Drive the screen with keys; what it shows at the end."""
    app = Watch(repo, lambda: Store.open(repo), every=60, view=view)

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            app.refresh_plan()
            await pilot.pause()
            box = app.query_one("#view")
            return {
                "showing": app.showing,
                "cursor": app.selected(),
                "status": str(app.query_one("#status").render()),
                "detail": str(app.query_one("#detail").render()),
                "view": shown(app, box.region) if box.display else [],
                "tree": app.tree.display,
                "focus": app.focused.id if app.focused else None,
            }

    return asyncio.run(go())


def order(repo):
    with Store.open(repo) as store:
        return [n.id for n in V.shown(store)]


@pytest.mark.parametrize("size", SIZES)
def test_tab_opens_the_view_on_the_same_node_and_tab_again_the_outline(repo, grid, size):
    proposed(repo)
    seen = look(repo, ["j", "j", "tab"], size)  # the outline's cursor on ids, then the grid
    assert seen["showing"] == "grid" and not seen["tree"] and seen["focus"] == "view"
    assert seen["cursor"] == "ids" and "graphene watch --view grid: 4 in a grid" in seen["status"]
    assert any("ids users returns ids" in row for row in seen["view"])
    assert "users returns ids" in seen["detail"]  # the node pane follows the view's cursor
    back = look(repo, ["j", "j", "tab", "j", "tab"], size)  # j in the grid, then the outline
    nodes = order(repo)
    assert back["showing"] == "outline" and back["tree"] and back["focus"] == "tree"
    assert back["cursor"] == nodes[nodes.index("ids") + 1]
    assert "graphene watch --view outline" in back["status"]


@pytest.mark.parametrize("size", SIZES)
def test_j_k_walk_the_order_h_l_the_cells_beside_and_gg_G_the_ends(repo, grid, size):
    proposed(repo)
    nodes = order(repo)  # the grid: nodes[0] nodes[1] on its first line of cells, nodes[2] nodes[3] under
    assert look(repo, ["tab"], size)["cursor"] == nodes[0]  # the goal has no cell: the first node
    assert look(repo, ["tab", "j", "j"], size)["cursor"] == nodes[2]
    assert look(repo, ["tab", "j", "j", "k"], size)["cursor"] == nodes[1]
    assert look(repo, ["tab", "l"], size)["cursor"] == nodes[1]
    assert look(repo, ["tab", "l", "h"], size)["cursor"] == nodes[0]
    assert look(repo, ["tab", "j", "j", "l"], size)["cursor"] == nodes[3]
    assert look(repo, ["tab", "h"], size)["cursor"] == nodes[0]  # nothing to the left: it stays
    assert look(repo, ["tab", "G"], size)["cursor"] == nodes[-1]
    assert look(repo, ["tab", "G", "g", "g"], size)["cursor"] == nodes[0]
    folded = look(repo, ["tab", "z", "a"], size)  # folding is the outline's: za adds nothing here
    assert folded["cursor"] == nodes[0] and folded["showing"] == "grid" and len(order(repo)) == 4


@pytest.mark.parametrize("size", SIZES)
def test_y_d_and_e_act_on_the_node_under_the_views_cursor(repo, grid, size, monkeypatch):
    proposed(repo)
    nodes = order(repo)
    seen = look(repo, ["tab", "l", "y"], size)
    assert states(repo)[nodes[1]] == "open" and f"graphene plan accept {nodes[1]}" in seen["status"]
    seen = look(repo, ["tab", "G", "d"], size)
    assert states(repo)[nodes[-1]] == "dropped" and f"graphene node drop {nodes[-1]}" in seen["status"]
    monkeypatch.setenv("EDITOR", "true")  # an editor that changes nothing
    seen = look(repo, ["tab", "l", "e"], size)
    assert f"graphene node edit {nodes[1]}" in seen["status"] and seen["showing"] == "grid"


@pytest.mark.parametrize("size", SIZES)
def test_enter_the_colon_line_and_help_work_from_the_view(repo, grid, size):
    proposed(repo)
    nodes = order(repo)
    seen = look(repo, ["tab", "l", "enter"], size)
    assert seen["cursor"] == nodes[1] and "record" in seen["detail"] and "Enter back" in seen["status"]
    seen = look(repo, ["tab", "colon", *"plan accept schema", "enter", "j"], size)
    assert states(repo)["schema"] == "open" and seen["focus"] == "view" and seen["cursor"] == nodes[1]
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.press("tab", "question_mark")
            await pilot.pause()
            return type(app.screen).__name__

    assert asyncio.run(go()) == "Help"


def test_a_click_on_a_cell_puts_the_cursor_there(repo, grid):
    proposed(repo)
    nodes = order(repo)
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("tab")
            await pilot.pause()
            line, first, _ = app.drawn.at[nodes[3]]
            await pilot.click("#drawn", offset=(first + 2, line))
            await pilot.pause()
            return app.selected()

    assert asyncio.run(go()) == nodes[3]


@pytest.mark.parametrize("size", SIZES)
def test_search_and_visual_act_in_the_view(repo, grid, size):
    proposed(repo)
    seen = look(repo, ["tab", "slash", *"doc", "enter"], size)
    assert seen["cursor"] == "docs" and seen["showing"] == "grid" and "/doc: 1 of 1" in seen["status"]
    nodes = order(repo)
    look(repo, ["tab", "l", "V", "j", "y"], size)  # nodes[1] and nodes[2], in the view's order
    assert states(repo)[nodes[1]] == states(repo)[nodes[2]] == "open" and states(repo)[nodes[3]] == "proposed"


@pytest.mark.parametrize("size", SIZES)
def test_a_view_that_does_not_fit_gives_way_to_the_outline_and_says_so(repo, grid, size, monkeypatch):
    proposed(repo)
    monkeypatch.setitem(V.VIEWS, "wide", Wide)
    seen = look(repo, [], size, view="wide")
    assert seen["showing"] == "outline" and seen["tree"]
    assert f"the wide does not fit at {size[0]} columns: the outline" in seen["status"]
    seen = look(repo, ["tab", "tab"], size)  # Tab skips what does not fit: grid, then the outline
    assert seen["showing"] == "outline"
    assert V.choose([], *size) == "wide"  # it says it suits best; the screen still falls back
    assert look(repo, [], size, view="auto")["showing"] == "outline"


def test_the_screen_opens_in_the_repositorys_view_setting(repo, grid):
    proposed(repo)
    assert look(repo, [], (80, 24))["showing"] == "outline"  # unset: the outline
    with Store.open(repo) as store:
        store.set_meta("view", "grid")
    assert look(repo, [], (80, 24))["showing"] == "grid"
    assert look(repo, [], (80, 24), view="outline")["showing"] == "outline"  # --view wins


def test_tab_with_only_the_outline_says_so(repo):
    proposed(repo)
    seen = look(repo, ["tab"], (80, 24))
    assert seen["showing"] == "outline" and "graphene watch --view outline: the only view" in seen["status"]


def test_choose_is_the_outline_unless_a_view_scores_higher(grid, monkeypatch):
    assert V.choose([], 80, 24) == "grid"  # Grid scores 1
    monkeypatch.setattr(Grid, "suits", classmethod(lambda cls, *_: 0))
    assert V.choose([], 80, 24) == "outline"  # a tie goes to the outline
    monkeypatch.delattr(Grid, "suits")
    assert V.choose([], 80, 24) == "outline"  # a view with no suits scores 0


def test_the_replay_allows_tab_and_still_refuses_writes(tmp_path, monkeypatch, grid):
    from graphene_map import demo

    monkeypatch.setattr(demo, "LONG", 0.01)
    head, lines = demo.load(demo.SHIPPED)
    repo = demo.repository(tmp_path, head)
    app, seen = demo.Replay(repo, head, lines), {}

    def states():
        with Store.open(repo) as store:
            return {n.id: (n.state, n.rev) for n in P.nodes(store)}

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(200):
                if app.next == len(app.lines):
                    break
                await pilot.pause(0.05)
            before = states()
            await pilot.press("tab")
            await pilot.pause()
            seen["showing"], seen["said"] = app.showing, str(app.query_one("#status").render())
            for key in ["y", "d", "R"]:
                await pilot.press(key)
                await pilot.pause()
                seen.setdefault("refused", []).append(str(app.query_one("#status").render()).splitlines()[-1])
            seen["same"] = states() == before

    asyncio.run(go())
    assert seen["showing"] == "grid" and "graphene watch --view grid" in seen["said"]
    assert seen["refused"] == [demo.REFUSED] * 3 and seen["same"]
