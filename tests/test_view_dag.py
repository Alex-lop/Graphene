"""The plan as a directed graph, left to right (`view_dag`): columns by the longest chain of needs,
lines that never run through a cell and say exactly what waits on what, the critical path, and no
graph at all when glyph and id do not fit the width."""

import random
import sys
import types
from dataclasses import dataclass

from rich.cells import cell_len, split_graphemes
from rich.text import Text

try:
    from graphene_map.views import Drawn
except ImportError:  # the seam lane's views.py is not here yet: its Drawn, as the coordinator fixed it

    @dataclass
    class Drawn:
        lines: list[Text]
        at: dict[str, tuple[int, int, int]]
        order: list[str]
        note: str

    sys.modules["graphene_map.views"] = types.ModuleType("graphene_map.views")
    sys.modules["graphene_map.views"].Drawn = Drawn

from graphene_map import plan as P
from graphene_map import view_dag as V


def leaf(i, title="", needs=(), **more):
    return P.Node(i, title or f"the {i} leaf", scope=[f"{i}.py"], check="true", needs=list(needs), **more)


def diamond_and_chain(done=()):
    nodes = [
        leaf("a", "read the feed"),
        leaf("b", "parse rows", ["a"]),
        leaf("c", "check prices", ["a"]),
        leaf("d", "write the report", ["b", "c"]),
        leaf("x1", "one"),
        leaf("x2", "two", ["x1"]),
        leaf("x3", "three", ["x2"]),
        leaf("x4", "four", ["x3"]),
        leaf("x5", "five", ["x4"]),
    ]
    for n in nodes:
        n.state = P.DONE if n.id in done else n.state
    return nodes


def words_of(nodes):
    return {n.id: P.reads(n, nodes) for n in nodes}


def cells(text):
    """A line as one entry a terminal column, as rich measures it: a wide character's second column
    is a NUL, and what a terminal draws as one (❤️, 👩‍👩‍👧) is one entry."""
    out = []
    for a, b, wide in split_graphemes(text)[0]:
        out += [text[a:b]] + ["\0"] * (wide - 1)
    return out


ARMS = {char: dict(zip("udlr", arms, strict=True)) for arms, char in V.BOX.items()}


def traced(drawn):
    """What the picture says waits on what: from each ▸, back along its line to the cells it starts
    at: a track's corner into its leaf (└ ┌ ├) is followed up and down, each join on the track (┘ ┤
    ┼) back to its cell, and a track crossed (│ between two dashes) or joined by a line that goes on
    past it (┬ ┴) is not the leaf's.
    Every arm has to meet an arm, so a line that ran into a cell would fail here."""
    lines = [cells(line.plain) for line in drawn.lines]
    ends = {(y, b): i for i, (y, _, b) in drawn.at.items()}
    starts = {(y, a): i for i, (y, a, _) in drawn.at.items()}

    def char(y, x):
        return lines[y][x] if 0 <= y < len(lines) and 0 <= x < len(lines[y]) else " "

    def arm(y, x, a):
        return ARMS.get(char(y, x), {}).get(a, 0)

    def left_of(y, x):  # the next line character to the left, over the tracks this line crosses
        over = x - 1
        while char(y, over) in "│┃":
            over -= 1
        if arm(y, over, "r"):
            return over
        assert (y, x - 2) in ends and char(y, x - 1) == " ", f"line {y} col {x} meets nothing: {lines[y]}"
        return None

    got: dict[str, set[str]] = {}
    for y, line in enumerate(lines):
        for x, c in enumerate(line):
            if c != "▸":
                continue
            target = starts[(y, x + 2)]
            assert arm(y, x - 1, "r"), lines[y]
            found, seen = got.setdefault(target, set()), set()
            todo = [(y, x - 1, "entry")]
            while todo:
                y0, x0, how = todo.pop()
                if (y0, x0, how) in seen:
                    continue
                seen.add((y0, x0, how))
                a = ARMS[char(y0, x0)]
                assert all(arm(y0 + d, x0, b) for d, u, b in ((-1, "u", "d"), (1, "d", "u")) if a[u]), lines
                if how == "track":
                    todo += [(y0 + d, x0, "track") for d, u in ((-1, "u"), (1, "d")) if a[u]]
                    if not a["l"]:
                        continue
                    how = "lead"
                elif how == "entry" and (a["u"] or a["d"]) and not a["l"]:
                    todo += [(y0 + d, x0, "track") for d, u in ((-1, "u"), (1, "d")) if a[u]]
                    continue  # a track's corner into its leaf: what comes in on it is that leaf's
                elif a["u"] or a["d"]:
                    how = "lead"  # a line from the left that also joins a track on its way: its own need
                if a["l"]:
                    nxt = left_of(y0, x0)
                    if nxt is None:
                        found.add(ends[(y0, x0 - 2)])
                    else:
                        todo.append((y0, nxt, how))
    return got


def checked(nodes, width, height=24, cursor=None):
    """The graph drawn, with what holds of every drawing: each line fits, each id is whole, and the
    lines say exactly the needs, none implied by another."""
    drawn = V.draw(nodes, words_of(nodes), "the goal", width, height, cursor)
    assert drawn is not None
    assert all(line.cell_len <= width for line in drawn.lines)
    for i, (y, a, b) in drawn.at.items():
        assert "".join(cells(drawn.lines[y].plain)[a : b + 1]).replace("\0", "").split(" ")[1] == i
    g = V._graph(nodes)
    assert traced(drawn) == {t: set(r) for t, r in g.needs.items() if r}
    return drawn


def test_a_column_is_the_longest_chain_of_needs_before_it_and_a_sub_goals_needs_are_its_leaves():
    nodes = [
        P.Node("source", "read it"),
        leaf("reader", parent="source"),
        leaf("wire", needs=["reader"], parent="source"),
        leaf("rule"),
        P.Node("proof", "prove it", needs=["source"]),
        leaf("e2e", needs=["rule"], parent="proof"),
        leaf("late", needs=["reader", "wire"]),  # reader is implied by wire: one line, from wire
    ]
    g = V._graph(nodes)
    assert [n.id for n in g.leaves] == ["reader", "wire", "rule", "e2e", "late"]  # sub-goals are not drawn
    assert g.level == {"reader": 0, "wire": 1, "rule": 0, "e2e": 2, "late": 2}
    assert g.needs == {
        "reader": [],
        "wire": ["reader"],
        "rule": [],
        "e2e": ["rule", "wire"],
        "late": ["wire"],
    }
    checked(nodes, 80)


def test_the_critical_path_is_the_longest_chain_not_done_and_a_tie_goes_to_the_plans_order():
    assert V.critical_path(diamond_and_chain()) == ["x1", "x2", "x3", "x4", "x5"]
    assert V.critical_path(diamond_and_chain(done={"x1", "x2", "x3"})) == ["a", "b", "d"]  # b before c
    assert V.critical_path(diamond_and_chain(done={"x1", "x2", "x3", "x4", "x5", "a", "b", "c", "d"})) == []
    assert V.critical_path(diamond_and_chain()[:4]) == ["a", "b", "d"]


def test_what_could_start_now_and_the_note():
    nodes = diamond_and_chain(done={"a"})
    words = words_of(nodes)
    assert V.at_once(nodes, words) == ["b", "c", "x1"]
    assert V.note(nodes, words) == "critical ━ x1 > x2 > … > x5 (5) · 3 ready · 5 wait · 1 done"
    proposed = [leaf("p"), leaf("q", needs=["p"])]
    for n in proposed:
        n.state = P.PROPOSED
    said = V.note(proposed, words_of(proposed))
    assert said == "critical ━ p > q (2) · none ready · 1 once accepted · 1 wait"
    both = [*nodes, *proposed]
    said = V.note(both, words_of(both))
    assert said == "critical ━ x1 > x2 > … > x5 (5) · 3 ready · 1 more once accepted · 6 wait · 1 done"


def test_a_need_on_a_sub_goal_is_on_the_path_and_at_once_is_only_the_agents_leaves_free_to_start():
    """A need on a sub-goal is a wait on each leaf beneath it. A proposal whose needs are done can start
    once accepted. The person's own leaf, and a leaf that came back, never start at once."""
    nodes = [leaf("a"), leaf("b", needs=["a"]), P.Node("top", "the top", needs=["b"]),
             leaf("c", parent="top"), leaf("d", needs=["c"], parent="top"), leaf("e")]  # fmt: skip
    assert V.critical_path(nodes) == ["a", "b", "c", "d"]
    nodes[0].state = P.DONE
    assert V.critical_path(nodes) == ["b", "c", "d"] and V.at_once(nodes, words_of(nodes)) == ["b", "e"]
    nodes += [leaf("p"), leaf("mine", owner="alex")]
    nodes[-2].state = P.PROPOSED
    words = {**words_of(nodes), "e": "came back"}
    assert V.at_once(nodes, words) == ["b", "p"]


def test_the_notes_counts_add_up_to_the_leaves_and_a_flat_plan_has_no_critical_path():
    """A leaf that came back, in review or the person's own was counted neither at once nor waiting,
    and a flat plan said "critical path: f0 (1)"."""
    nodes = diamond_and_chain(done={"a"})
    words = {**words_of(nodes), "b": "came back", "x1": "review", "c": "running"}
    said = V.note(nodes, words)
    assert said.endswith("none ready · 5 wait · 1 running · 2 on you · 1 done")
    assert sum(int(part.split()[0]) for part in said.split(" · ")[2:]) == len(nodes)
    flat = [leaf(f"f{k}") for k in range(3)]
    assert V.note(flat, words_of(flat)) == "3 ready · 0 wait"


def test_an_accepted_leaf_with_a_proposed_child_is_drawn_and_on_the_path():
    """What `node split` leaves: the graph took c for a sub-goal and drew its proposed child in its
    place, while the note named c on the critical path and `graphene plan` counted four leaves."""
    nodes = diamond_and_chain()[:2] + [leaf("c", "write it", ["b"]), leaf("kid", "a piece of c", parent="c")]
    nodes[-1].state = P.PROPOSED
    drawn = checked(nodes, 80)
    assert V.critical_path(nodes) == ["a", "b", "c"]
    assert set(drawn.at) == {n.id for n in P.leaves(nodes)} == {"a", "b", "c", "kid"}
    said = drawn.note
    assert said.startswith("critical ━ a > b > c (3)")
    assert sum(int(part.split()[0]) for part in said.split(" · ")[1:]) == 4


def test_the_note_keeps_the_paths_end_and_every_count_at_the_width_it_is_drawn_at():
    """The note shortened a path past four leaves only: four ids of a dozen letters drew at 80, and
    the status line cut the note's last leaf, its count and "1 ready" (`critical ━ … > write-report >…`)."""
    ids = ["parse-billing", "reconcile-rows", "write-report", "notify-finance"]
    nodes = [leaf(i, "x", ids[k - 1 : k]) for k, i in enumerate(ids)]
    for width in (73, 78, 90):
        said = V.draw(nodes, words_of(nodes), "", width, 24, None).note
        assert cell_len(said) <= width and said.endswith(" > notify-finance (4) · 1 ready · 3 wait"), said
    assert V.draw(nodes, words_of(nodes), "", 90, 24, None).note == (
        "critical ━ parse-billing > reconcile-rows > … > notify-finance (4) · 1 ready · 3 wait"
    )
    assert V.draw(nodes, words_of(nodes), "", 78, 24, None).note.startswith("critical ━ parse-billing > … >")
    assert " > write-report > " in V.note(nodes, words_of(nodes))  # no width: the whole path


def style_at(line, x):
    return " ".join(str(span.style) for span in line.spans if span.start <= x < span.end)


def test_the_diamond_and_the_chain_at_80_columns():
    """The golden text. d needs two, so it sits on a row of its own and the track's corner leads
    into it; the chain is the critical path, heavy; a is done, and dim but its ✓."""
    nodes = diamond_and_chain(done={"a"})
    drawn = checked(nodes, 80, cursor="c")
    assert [line.plain for line in drawn.lines] == [
        "the goal",
        "✓ a   read… ────┬─▸ ○ b   parse… ──┐",
        "                └─▸ ○ c   check… ──┤",
        "                                   └─▸ ◌ d   write…",
        "○ x1  one ━━━━━━━━▸ ◌ x2  two ━━━━━━━▸ ◌ x3  three ━━━▸ ◌ x4  four ━▸ ◌ x5  five",
    ]  # a column's titles start two after its widest id (walk 2026-09-28, alex 25)
    assert drawn.order == ["a", "x1", "b", "c", "x2", "d", "x3", "x4", "x5"]  # a column, then the next
    assert drawn.at["c"] == (2, 20, 31) and drawn.at["x5"] == (4, 70, 79)
    assert all("reverse" in style_at(drawn.lines[2], x) for x in range(20, 30))  # the cursor
    assert "reverse" not in style_at(drawn.lines[1], 20)
    assert style_at(drawn.lines[4], 10) == "bold" and style_at(drawn.lines[4], 2) == "bold"  # x1 > …
    assert style_at(drawn.lines[1], 0) == "green" and style_at(drawn.lines[1], 6) == "dim"  # a is done
    assert style_at(drawn.lines[1], 15) == "dim"  # and so is the line out of it
    assert drawn.note == "critical ━ x1 > x2 > … > x5 (5) · 3 ready · 5 wait · 1 done"


def test_a_columns_titles_line_up_two_columns_after_its_widest_id():
    """Walk 2026-09-28 (alex 25, judge 24): a cell read `? xml-reader an xml reader` and `○
    readme-lists-xml README lists xml`, the id run into the title. The ids of a column take the
    width of its widest, and its titles start two columns after it, as the outline's columns do."""
    nodes = [leaf("xml-reader", "read the xml feed"), leaf("xml-register", "register xml in READERS"),
             leaf("readme", "say xml in the README", ["xml-reader"])]  # fmt: skip
    lines = [line.plain for line in checked(nodes, 120).lines]
    assert "○ xml-reader    read the xml feed" in lines[1], lines
    assert lines[2].startswith("○ xml-register  register xml in READERS"), lines
    assert "▸ ◌ readme  say xml in the README" in lines[1], lines


def test_every_line_fits_and_titles_go_before_ids_and_then_the_graph():
    """Five columns of glyph and a two-letter id (4 each), the gaps before the two columns with a
    track (6 each) and before the two without (4 each): 40. Below that there is no graph."""
    nodes = diamond_and_chain()
    assert V.draw(nodes, words_of(nodes), "", 39, 24, None) is None
    assert V.suits(nodes, 39, 24) == 0
    assert not any("read" in line.plain for line in checked(nodes, 40).lines)
    for width in range(40, 130):
        checked(nodes, width)
    assert any("read the feed" in line.plain for line in checked(nodes, 120).lines)


def test_random_plans_never_draw_a_line_through_a_cell_and_say_exactly_their_needs():
    for seed in range(150):
        rng = random.Random(seed)
        count = rng.randint(2, 14)
        nodes = [
            leaf(f"n{k}", needs=rng.sample([f"n{j}" for j in range(k)], rng.randint(0, min(k, 3))))
            for k in range(count)
        ]
        for n in nodes:
            n.state = rng.choice((P.OPEN, P.OPEN, P.DONE, P.RUNNING))
        if V.draw(nodes, words_of(nodes), "", 200, 24, None) is not None:
            checked(nodes, 200)


def test_it_suits_a_plan_with_needs_that_fits_and_never_a_list():
    assert V.suits([leaf("a"), leaf("b")], 80, 24) == 0
    assert V.suits(diamond_and_chain(), 80, 24) == 100
    assert V.suits(diamond_and_chain(), 80, 3) == 50  # taller than the screen


def test_wide_characters_take_two_columns_and_the_lines_still_meet():
    """Cells and the grid counted characters: CJK titles pushed a line to 126 cells at 80, and the
    lines of different rows no longer met."""
    nodes = [
        leaf("a", "フィードを読む " * 6),
        leaf("b読む", "行を解析する", ["a"]),
        leaf("c", "価格を確認する", ["a"]),
        leaf("d", "報告書を書く", ["b読む", "c"]),
    ]
    for width in (40, 60, 80, 120):
        checked(nodes, width)
    goal = V.draw(nodes, words_of(nodes), "目標を書く " * 30, 80, 24, None).lines[0]
    assert goal.cell_len <= 80 and goal.plain.endswith("…")


def test_an_emoji_takes_the_cells_a_terminal_gives_it_and_the_lines_still_meet():
    """A joined emoji (👩‍👩‍👧, two cells) raised IndexError: each code point took columns of its own,
    six in all. An emoji with a variation selector (❤️, two cells) was counted one, so a line ran
    past the width."""
    for title in ("thank the 👩‍👩‍👧 team", "👩‍👩‍👧 " * 9, "❤️" * 12, "ok ✔️ ⚠️ done 👍🏽"):
        nodes = [leaf("a", "read the feed"), leaf("b", title, ["a"]), leaf("c", "x", ["b"])]
        for width in range(20, 90, 7):
            checked(nodes, width)


def test_a_fan_out_past_seven_crosses_nothing():
    """Past six tracks in a gap the order was top to bottom, and one leaf feeding twelve drew a comb
    of 55 crossings (└││││││││││─▸)."""
    fan = [leaf("r")] + [leaf(f"k{i}", needs=["r"]) for i in range(12)]
    fan += [leaf("sink", needs=[f"k{i}" for i in range(12)])]
    crossing = [c for c, arms in ARMS.items() if arms["r"]]  # a line going right, then a track it crosses
    drawn = checked(fan, 80)
    assert not any(c + "│" in line.plain for line in drawn.lines for c in crossing)
