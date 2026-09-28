"""The plan drawn top-down (`view_tree`): a pure function of the nodes, so every test builds nodes and
reads what is drawn, with no store."""

import sys
import types
from dataclasses import dataclass

import pytest
from rich.cells import cell_len
from rich.text import Text

from graphene_map import plan as P

try:
    from graphene_map.views import Drawn
except ImportError:  # until the seam lands: the coordinator's interface, copied as it was given

    @dataclass
    class Drawn:
        lines: list[Text]
        at: dict[str, tuple[int, int, int]]
        order: list[str]
        note: str

    sys.modules["graphene_map.views"] = types.ModuleType("graphene_map.views")
    sys.modules["graphene_map.views"].Drawn = Drawn

from graphene_map import view_tree  # noqa: E402

GOAL = "the importer reads every feed and names every bad row"


def leaf(i, parent=None, state=P.OPEN, **more):
    return P.Node(
        i,
        more.pop("title", f"the {i} leaf"),
        scope=[f"{i}.py"],
        check="true",
        parent=parent,
        state=state,
        **more,
    )


def small():
    """Two sub-goals and a leaf of the person's under the goal: five leaves in five states."""
    return [
        P.Node("read", "read every feed"),
        leaf("open", "read", P.DONE, title="open a feed whatever its encoding"),
        leaf("sniff", "read", P.RUNNING, title="sniff the delimiter"),
        P.Node("check", "every row checked"),
        leaf("types", "check", title="numbers and dates parse"),
        leaf("dupes", "check", needs=["types"], title="duplicate skus in one feed"),
        leaf("try", owner="alex", title="try it on last month's feeds"),
    ]


def thirty(done=2):
    """Six sub-goals of five leaves, the first ``done`` of them finished; a finished leaf has a long
    id (`g0-finished-leaf3`), so folding is what makes the tree narrower."""
    out = []
    for g in range(6):
        out.append(P.Node(f"goal{g}", f"sub-goal number {g}"))
        name = "finished-leaf" if g < done else "leaf"
        out += [leaf(f"g{g}-{name}{k}", f"goal{g}", P.DONE if g < done else P.OPEN) for k in range(5)]
    return out


def deep():
    return [
        P.Node("a", "a"),
        P.Node("b", "b", parent="a"),
        leaf("c", "b"),
        leaf("d", "b"),
        leaf("e", "a"),
        leaf("f"),
    ]


def words(nodes):
    return {n.id: P.reads(n, nodes) for n in nodes}


def drawn(nodes, width, height=24, cursor=None):
    return view_tree.draw(nodes, words(nodes), GOAL, width, height, cursor)


def plain(d):
    return "\n".join(line.plain.rstrip() for line in d.lines)


GOLDEN = """\
                  the importer reads every feed and names every bad row
                ┌───────────────────────────┴───┬───────────────────────┐
             ○ read                          ○ check                  ◇ try
         read every feed                every row checked          try it on…
        ┌───────┴───────┐               ┌───────┴───────┐
     ✓ open          ● sniff         ○ types       ◌ dupes ←1
  open a feed…     sniff the…     numbers and…     duplicate…"""


def test_golden_text_of_a_small_plan_at_80():
    d = drawn(small(), 80)
    assert plain(d) == GOLDEN
    assert d.order == ["read", "open", "sniff", "check", "types", "dupes", "try"]
    assert d.note == "2 sub-goals · 5 leaves · 1 waits on you"


def test_the_glyph_and_id_take_the_state_colour_and_the_mark_is_dim():
    d = drawn(small(), 80)
    y, x, _ = d.at["sniff"]
    line = d.lines[y]
    head = line.plain.index("● sniff")
    styles = {str(s.style) for s in line.spans if s.start <= head < s.end}
    assert styles == {P.look("running")[1]}
    y, _, _ = d.at["dupes"]
    mark = d.lines[y].plain.index("←1")
    assert {str(s.style) for s in d.lines[y].spans if s.start <= mark < s.end} == {"dim"}


PLANS = {
    "small": small,
    "thirty": thirty,
    "deep": deep,
    "all done": lambda: thirty(6),
    "none done": lambda: thirty(0),
}


def heads(d, nodes):
    """Each shown node's first line reads its glyph and id where `at` says, whole."""
    for n in nodes:
        if n.id not in d.at:
            continue
        y, x0, x1 = d.at[n.id]
        cut = "".join(c + "\0" * (cell_len(c) - 1) for c in d.lines[y].plain)[x0 : x1 + 1].replace("\0", "")
        assert n.id in cut.split(), (n.id, cut)


@pytest.mark.parametrize("name", sorted(PLANS))
@pytest.mark.parametrize("width", range(20, 170, 7))
def test_layout_invariants(name, width):
    nodes = PLANS[name]()
    d = drawn(nodes, width)
    if d is None:
        return
    assert all(line.cell_len <= width for line in d.lines)
    heads(d, nodes)
    cells = sorted(d.at.values())
    for (y0, _, b0), (y1, a1, _) in zip(cells, cells[1:], strict=False):
        assert y0 != y1 or b0 < a1, "two cells overlap"
    stacked = any("├" in line.plain or "└" in line.plain for line in d.lines)
    by_id = {n.id: n for n in nodes}
    for n in nodes:
        kids = [k.id for k in nodes if k.parent == n.id and k.id in d.at]
        if n.id not in d.at or not kids or d.at[kids[0]][1] == d.at[n.id][1] + 2:
            continue  # folded, a leaf, or its leaves listed down under it
        if stacked:  # everything starts at its glyph: the parent's is over the middle of its children's
            middle, mine = (d.at[kids[0]][1] + d.at[kids[-1]][1]) / 2, d.at[n.id][1]
        else:
            centre = [(d.at[k][1] + d.at[k][2]) / 2 for k in kids]
            middle, mine = (centre[0] + centre[-1]) / 2, (d.at[n.id][1] + d.at[n.id][2]) / 2
        assert abs(middle - mine) <= 1, (n.id, middle, mine, by_id[n.id].title)


@pytest.mark.parametrize("name", sorted(PLANS))
def test_none_exactly_when_no_form_fits(name):
    """Every width from the least that draws draws too; below it, nothing does."""
    nodes = PLANS[name]()
    fits = [w for w in range(4, 200) if drawn(nodes, w) is not None]
    assert fits == list(range(fits[0], 200))
    assert all(line.cell_len <= fits[0] for line in drawn(nodes, fits[0]).lines)


def test_the_least_width_is_the_folded_ids_listed_down():
    """Thirty leaves under six sub-goals, two finished: each sub-goal is a column as wide as its
    widest `├ ○ g2-leaf0`, and a finished one folded is as narrow as `✓ goal0 5/5`. Every slot was
    as wide as the widest, so folding made the tree no narrower (6 x 12 + 5 columns, folded or not)."""
    least = 2 * len("✓ goal0 5/5") + 4 * len("├ ○ g2-leaf0") + 5
    assert drawn(thirty(), least - 1) is None
    d = drawn(thirty(), least)
    assert "✓ goal0 5/5" in plain(d) and "g0-finished-leaf0" not in d.at
    assert "├ ○ g2-leaf0" in plain(d)


def form(d) -> tuple[bool, bool, bool]:
    """Which form a drawing is in, read off it: (folded, leaves listed down, titles)."""
    text = plain(d)
    return "5/5" in text, "├" in text, "sub-goal" in text


def test_the_forms_come_in_order_as_the_width_shrinks():
    """Titles; then ids alone, across; then leaves listed down; then finished sub-goals folded."""
    seen = [form(d) for w in range(700, 20, -1) if (d := drawn(thirty(), w, 100))]
    order = [view_tree.FORMS.index(f) for f in seen]
    assert order == sorted(order)
    assert order[0] == 0 and order[-1] == len(view_tree.FORMS) - 1
    assert len(set(order)) >= 6


def test_a_form_that_fits_the_height_wins_over_one_that_says_more():
    tall, short = drawn(thirty(), 120, 40), drawn(thirty(), 120, 10)
    assert len(tall.lines) > 10 and "│ sub-goal" in plain(tall)
    assert len(short.lines) <= 10 and "sub-goal" not in plain(short)


def reversed_spans(d):
    return [
        (y, s.start, s.end) for y, line in enumerate(d.lines) for s in line.spans if "reverse" in str(s.style)
    ]


@pytest.mark.parametrize("width", (80, 120))
def test_the_cursors_cell_is_reversed_and_nothing_else(width):
    d = drawn(small(), width, cursor="types")
    y, x0, x1 = d.at["types"]
    spans = reversed_spans(d)
    assert {s[0] for s in spans} == {y, y + 1}  # the id's line and the title's
    assert all(x0 <= start and end <= x1 + 1 for _, start, end in spans)
    head = d.lines[y].plain.index("○ types")
    assert any(sy == y and start <= head and head + len("○ types") <= end for sy, start, end in spans)
    assert reversed_spans(drawn(small(), width)) == []


def test_a_cursor_inside_a_folded_sub_goal_reverses_the_fold():
    d = drawn(thirty(), 6 * 12 + 5, cursor="g0-finished-leaf3")
    y, x0, _ = d.at["goal0"]
    assert [s[:2] for s in reversed_spans(d)] == [(y, x0)]
    assert "g0-finished-leaf3" not in d.order and d.order[:2] == ["goal0", "goal1"]


def test_order_walks_parents_before_children_left_to_right():
    d = drawn(deep(), 80)
    assert d.order == ["a", "b", "c", "d", "e", "f"]


def test_suits_a_shallow_tree_that_fits_and_not_one_that_cannot():
    assert view_tree.suits(small(), 80, 24) == 90
    assert view_tree.suits(thirty(), 2 * 11 + 4 * 12 + 4, 24) == 0
    assert 0 < view_tree.suits(thirty(), 120, 36) < view_tree.suits(small(), 120, 36)
    assert view_tree.suits(thirty(), 120, 5) < view_tree.suits(thirty(), 120, 36)
    assert view_tree.suits([], 80, 24) == 0


def test_an_empty_plan_is_its_goal():
    d = view_tree.draw([], {}, "", 80, 24, None)
    assert plain(d).strip() == "no goal yet" and d.order == [] and d.at == {}


def test_note_counts_what_waits_on_the_person_and_what_is_proposed():
    nodes = [P.Node("x", "x", state=P.PROPOSED), leaf("y", "x", P.PROPOSED), leaf("z", state=P.REVIEW)]
    assert view_tree.note(nodes, words(nodes)) == "1 sub-goal · 2 leaves · 1 waits on you · 2 proposed"


def test_an_emoji_with_a_variation_selector_is_counted_in_the_two_cells_it_takes():
    """❤️ ✔️ ⚠️ are two cells, but a character at a time they counted one: `elide` cut ❤️ x 8 to
    11 cells at 6, and three such titles at 40 ran into each other and to 45 cells."""
    assert cell_len(view_tree.elide("❤️" * 8, 6)) <= 6
    nodes = [leaf(i, title="emoji ❤️❤️❤️❤️ hearts") for i in "abc"] + [leaf("d", title="ok ✔️ ⚠️ done")]
    for width in range(30, 81, 5):
        d = drawn(nodes, width, 10)
        assert d is None or all(line.cell_len <= width for line in d.lines)
        assert d is None or all(last < width for _, _, last in d.at.values())


def test_wide_characters_are_counted_in_cells():
    """Titles and the goal were cut by characters: CJK lines ran to 123 cells at 80, cut with no …"""
    nodes = [
        P.Node("r読む", "フィードを読む" * 4),
        leaf("a読む", "r読む", title="行を解析する" * 5),
        leaf("b", "r読む", title="価格" * 20),
        leaf("c", title="報告書を書く"),
    ]
    for width in (40, 80, 120):
        d = view_tree.draw(nodes, words(nodes), "目標を書く" * 30, width, 24, None)
        assert d is not None and all(line.cell_len <= width for line in d.lines)
        assert d.lines[0].plain.strip().endswith("…")
        heads(d, nodes)
