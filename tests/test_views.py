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
        return 60

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
        return 70


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
    assert look(repo, ["tab"], size)["cursor"] is None  # on the goal, as the outline was
    assert look(repo, ["tab", "j"], size)["cursor"] == nodes[0]
    assert look(repo, ["tab", "j", "j", "j"], size)["cursor"] == nodes[2]
    assert look(repo, ["tab", "j", "j", "j", "k"], size)["cursor"] == nodes[1]
    assert look(repo, ["tab", "j", "l"], size)["cursor"] == nodes[1]
    assert look(repo, ["tab", "j", "l", "h"], size)["cursor"] == nodes[0]
    assert look(repo, ["tab", "j", "j", "j", "l"], size)["cursor"] == nodes[3]
    assert look(repo, ["tab", "j", "h"], size)["cursor"] == nodes[0]  # nothing to the left: it stays
    assert look(repo, ["tab", "G"], size)["cursor"] == nodes[-1]
    assert look(repo, ["tab", "G", "g", "g"], size)["cursor"] is None  # gg: the goal, as in the outline
    folded = look(repo, ["tab", "j", "z", "a"], size)  # folding is the outline's: za adds nothing here
    assert folded["cursor"] == nodes[0] and folded["showing"] == "grid" and len(order(repo)) == 4


@pytest.mark.parametrize("size", SIZES)
def test_the_views_first_line_is_the_goal_and_its_keys_are_the_goal_rows(repo, grid, size, monkeypatch):
    """A view had no place for the goal: y (accept it all) and E (the plan as text) were out of reach."""
    proposed(repo)
    seen = look(repo, ["tab", "j", "k"], size)
    assert seen["cursor"] is None and seen["view"][0].startswith("users come back with their ids")
    assert "y accept it all" in seen["status"] and "E edit the plan as text" in seen["status"]
    assert "za" not in seen["status"]  # folding is the outline's
    look(repo, ["tab", "y"], size)
    assert set(states(repo).values()) == {"open"}  # the whole plan accepted, as y on the goal row does
    monkeypatch.setenv("EDITOR", "true")
    assert "graphene plan edit" in look(repo, ["tab", "E"], size)["status"]
    back = look(repo, ["j", "tab", "k", "tab"], size)  # the goal in the view is the goal in the outline
    assert back["showing"] == "outline" and back["cursor"] is None


@pytest.mark.parametrize("size", SIZES)
def test_a_drop_in_a_view_keeps_the_place_the_next_node_as_the_outline_does(repo, grid, size):
    """A drop sent the cursor to the view's first node, and a long plan scrolled to its top."""
    proposed(repo)
    nodes = order(repo)
    seen = look(repo, ["tab", "j", "j", "j", "d"], size)  # nodes[2] dropped: the cursor on the next
    assert states(repo)[nodes[2]] == "dropped" and seen["cursor"] == nodes[3]
    seen = look(repo, ["tab", "G", "d"], size)  # the last dropped: the one before it
    assert states(repo)[nodes[3]] == "dropped" and seen["cursor"] == nodes[1]


@pytest.mark.parametrize("size", SIZES)
def test_tab_on_a_sub_goal_the_graph_shows_its_first_leaf_and_tab_back_the_sub_goal(repo, size, monkeypatch):
    """The graph draws leaves only: Tab on a sub-goal put the cursor on the plan's first leaf, and Tab
    back left the outline there."""
    from graphene_map import view_dag

    monkeypatch.setattr(V, "VIEWS", {"outline": None, "dag": view_dag})
    proposed(repo)
    seen = look(repo, ["j", "tab"], size)  # j: the sub-goal api, whose leaves are ids and docs
    assert seen["showing"] == "dag" and seen["cursor"] == "ids"
    back = look(repo, ["j", "tab", "tab"], size)
    assert back["showing"] == "outline" and back["cursor"] == "api"
    moved = look(repo, ["j", "tab", "j", "tab"], size)  # moved in the graph: the outline follows it
    assert moved["cursor"] != "api"


@pytest.mark.parametrize("size", SIZES)
def test_a_view_takes_the_whole_width_and_the_node_pane_goes_under_it(repo, grid, size):
    """Beside the node pane a view had 71 of 120 columns, and a tree lost its titles there."""
    proposed(repo)
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.press("tab")
            await pilot.pause()
            view, side = app.query_one("#view").region, app.query_one("#side").region
            return app.view_room(), view, side, max(line.cell_len for line in app.drawn.lines)

    room, view, side, widest = asyncio.run(go())
    assert room == (size[0] - 2, (size[1] - 3) // 2) and widest > size[0] // 2 + 10
    assert view.width == side.width == size[0] and side.y >= view.bottom


@pytest.mark.parametrize("size", SIZES)
def test_y_d_and_e_act_on_the_node_under_the_views_cursor(repo, grid, size, monkeypatch):
    proposed(repo)
    nodes = order(repo)
    seen = look(repo, ["tab", "j", "l", "y"], size)
    assert states(repo)[nodes[1]] == "open" and f"graphene plan accept {nodes[1]}" in seen["status"]
    seen = look(repo, ["tab", "G", "d"], size)
    assert states(repo)[nodes[-1]] == "dropped" and f"graphene node drop {nodes[-1]}" in seen["status"]
    monkeypatch.setenv("EDITOR", "true")  # an editor that changes nothing
    seen = look(repo, ["tab", "j", "l", "e"], size)
    assert f"graphene node edit {nodes[1]}" in seen["status"] and seen["showing"] == "grid"


@pytest.mark.parametrize("size", SIZES)
def test_enter_the_colon_line_and_help_work_from_the_view(repo, grid, size):
    proposed(repo)
    nodes = order(repo)
    seen = look(repo, ["tab", "j", "l", "enter"], size)
    assert seen["cursor"] == nodes[1] and "record" in seen["detail"] and "Enter back" in seen["status"]
    seen = look(repo, ["tab", "colon", *"plan accept schema", "enter", "j"], size)
    assert states(repo)["schema"] == "open" and seen["focus"] == "view" and seen["cursor"] == nodes[0]
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
    look(repo, ["tab", "j", "l", "V", "j", "y"], size)  # nodes[1] and nodes[2], in the view's order
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
    assert look(repo, [], size, view="auto")["showing"] == "grid"  # auto: the best that draws


def test_auto_never_picks_a_view_that_does_not_draw(grid, monkeypatch):
    """`suits` is a preference and `draw` decides the fit: auto took the wide, which scores 70 and
    never draws, and fell back to the outline past the grid, which draws."""
    monkeypatch.setitem(V.VIEWS, "wide", Wide)
    assert V.choose([], {}, "g", 80, 24) == "grid"


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
    assert V.choose([], {}, "g", 80, 24) == "grid"  # Grid scores 60, the outline BASELINE
    monkeypatch.setattr(Grid, "suits", classmethod(lambda cls, *_: V.BASELINE))
    assert V.choose([], {}, "g", 80, 24) == "outline"  # a tie goes to the outline
    monkeypatch.delattr(Grid, "suits")
    assert V.choose([], {}, "g", 80, 24) == "outline"  # a view with no suits scores 0


def node(i, parent=None, needs=(), state=P.OPEN):
    return P.Node(
        i, f"the {i} leaf", scope=[f"{i}.py"], check="true", parent=parent, state=state, needs=list(needs)
    )


def test_auto_keeps_the_outline_for_a_view_taller_than_its_rows_unless_it_shows_needs(grid, monkeypatch):
    """A view that scrolls beat the outline, which shows the plan in one look: the tree of twelve
    nested sub-goals (40 lines in 10 rows), and the graph of the thirty-leaf plan, whose 10 rows at
    80x24 showed done leaves and no line."""
    from graphene_map import view_dag, view_tree

    nodes = [node("n1")]  # the grid of one node: a goal line and a line of cells, 2 lines
    assert V.choose(nodes, {"n1": "ready"}, "g", 80, 2) == "grid"
    assert V.choose(nodes, {"n1": "ready"}, "g", 80, 1) == "outline"  # taller than its rows
    monkeypatch.setattr(Grid, "NEEDS", True, raising=False)
    assert V.choose(nodes, {"n1": "ready"}, "g", 80, 1) == "grid"  # it shows needs: scrolling is its cost
    monkeypatch.setattr(V, "VIEWS", {"outline": None, "tree": view_tree, "dag": view_dag})
    deep = [node(f"s{k}", f"s{k - 1}" if k else None) for k in range(12)] + [node("leaf", "s11")]
    words = {n.id: P.reads(n, deep) for n in deep}
    assert V.choose(deep, words, "g", 78, 10) == "outline"
    subs = ["reader", "dialects", "validate", "report", "cli"]
    thirty = [node(s) for s in subs] + [
        node(f"{s[0]}{k}", s, state=P.DONE if s in subs[:2] else P.OPEN) for s in subs for k in range(6)
    ]
    thirty += [
        node("v-rules", "validate", ["v0"]),
        node("c-exit", "cli", ["c0"]),
        node("c-prog", "cli", ["c0"]),
    ]
    words = {n.id: P.reads(n, thirty) for n in thirty}
    assert V.choose(thirty, words, "g", 78, 10) == "outline"
    assert V.choose(thirty, words, "g", 118, 16) == "tree"  # its leaves listed down fit; the graph scrolls


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


def test_plan_view_prints_the_outline_or_the_view_as_text(repo, grid):
    proposed(repo)
    outline, plain = person("plan", "--view", "outline"), person("plan")
    assert outline.exit_code == 0 and outline.stdout == plain.stdout
    drawn = person("plan", "--view", "grid", "--width", "80", "--height", "24")
    assert drawn.exit_code == 0, drawn.output
    lines = drawn.stdout.splitlines()
    assert lines[0] == "users come back with their ids" and lines[-1] == "4 in a grid"
    assert all(len(line) <= 80 for line in lines) and "? ids users returns ids" in drawn.stdout
    narrow = person("plan", "--view", "grid", "--width", "40")
    assert narrow.stdout == plain.stdout
    assert "the grid does not fit at 40 columns: the outline" in narrow.stderr
    auto = person("plan", "--view", "auto", "--width", "80")
    assert auto.stdout == drawn.stdout
    unknown = person("plan", "--view", "dag")
    assert unknown.exit_code == 2 and "no view named dag" in unknown.output


def test_watch_takes_the_view_too(repo, grid, monkeypatch):
    proposed(repo)
    monkeypatch.setenv("COLUMNS", "80")
    printed = person("watch", "--view", "grid")  # no terminal: printed, as `plan --view` prints it
    assert printed.exit_code == 0 and printed.stdout.splitlines()[-1] == "4 in a grid"
    unknown = person("watch", "--view", "dag")
    assert unknown.exit_code == 2 and "no view named dag: the views are auto, outline, grid" in unknown.output


def test_plan_view_outline_keeps_all_and_a_view_with_json_or_text_is_refused(repo, tmp_path):
    """`plan --view outline --all` dropped --all, and `--view` with --json printed the text tree."""
    import json

    person("plan", "goal", "ship invoices by email")
    person("node", "add", "the HTTP surface", "--id", "api")
    tree = {"nodes": [{"id": f"l{k}", "parent": "api", "title": f"leaf {k}", "scope": [f"f{k}.txt"],
                       "check": "true"} for k in range(14)]}  # fmt: skip
    (tmp_path / "t.json").write_text(json.dumps(tree))
    assert person("plan", "propose", str(tmp_path / "t.json")).exit_code == 0
    every = person("plan", "--all").stdout
    assert person("plan", "--view", "outline", "--all").stdout == every != person("plan").stdout
    for other in ("--json", "--text"):
        refused = person("plan", "--view", "auto", other)
        assert refused.exit_code == 2 and "one or the other" in refused.output


def test_watch_once_in_a_view_that_is_the_outline_says_what_just_happened(repo, monkeypatch):
    """`watch --once --view auto` printed the plan without its "just now" when auto chose the outline."""
    monkeypatch.setattr(V, "VIEWS", {"outline": None})
    proposed(repo)
    once = person("watch", "--once").stdout
    assert "just now" in once and person("watch", "--once", "--view", "auto").stdout == once


@pytest.mark.parametrize("size", SIZES)
def test_help_lists_tab_and_h_l_only_when_there_is_a_view_and_on_one_line(repo, size, monkeypatch):
    """The help advertised Tab and h l with only the outline registered, and Tab's row wrapped at 80."""
    proposed(repo)

    def help_says():
        app = Watch(repo, lambda: Store.open(repo), every=60)

        async def go():
            async with app.run_test(size=size) as pilot:
                await pilot.press("question_mark")
                await pilot.pause()
                return "\n".join(str(s.render()) for s in app.screen.query("Static"))

        return asyncio.run(go())

    monkeypatch.setattr(V, "VIEWS", {"outline": None})
    alone = help_says()
    assert "graphene watch --view" not in alone and "in a view" not in alone
    monkeypatch.setattr(V, "VIEWS", {"outline": None, "grid": Grid})
    said = help_says()
    assert "Tab" in said and "in a view: the node to the left" in said
    assert any("Tab" in line and "(graphene watch --view)" in line for line in said.splitlines())


def test_tab_on_an_empty_plan_says_so_and_changes_nothing(repo, grid):
    """Tab on an empty plan switched to the grid with nothing shown, the keyboard on the hidden tree."""
    seen = look(repo, ["tab"], (80, 24))
    assert seen["showing"] == "outline" and "nothing is planned yet" in seen["status"]


def test_a_click_on_either_line_of_a_tree_cell_puts_the_cursor_there(repo, monkeypatch):
    """A tree cell is its head and its title under it: a click on the title did nothing."""
    from graphene_map import view_tree

    monkeypatch.setattr(V, "VIEWS", {"outline": None, "tree": view_tree})
    proposed(repo)
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("tab")
            await pilot.pause()
            got = []
            for node_id, down in (("docs", 1), ("schema", 0), ("ids", 1)):
                line, first, _ = app.drawn.at[node_id]
                await pilot.click("#drawn", offset=(first + 2, line + down))
                await pilot.pause()
                got.append(app.selected())
            return app.drawn.tall, got

    assert asyncio.run(go()) == (2, ["docs", "schema", "ids"])
