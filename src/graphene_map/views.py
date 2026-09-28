"""The views of the plan a terminal can show where the outline goes, by name.

The outline is `graphene watch`'s tree and `graphene plan`'s print. Another view is a module with a
pure `draw(nodes, words, goal, width, height, cursor) -> Drawn | None` and, if it likes, a
`suits(nodes, width, height) -> int` saying how well it fits this plan at this size. It is added to
VIEWS by name. A view never reads the store: it is given the plan's drawn nodes, the word each one
reads as (`plan.reads`), the goal, and the node under the cursor, and it returns None when it does
not fit the width (it may be taller than the screen: the screen scrolls it). Its first line is the
goal's: the cursor on it is on the goal, as on the outline's first row.

Which view opens by itself (`--view auto`, `choose`): the outline scores BASELINE, and a view opens
only when its own `suits` scores more. `suits` is a preference, `draw` decides the fit: a view whose
draw returns None is never chosen, and neither is one taller than the rows it has (it would scroll,
where the outline shows the plan in one look) unless it shows what the outline cannot, which leaf
waits on which (a view that draws `needs` says so with `NEEDS = True`). A tie goes to the outline.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.cells import cell_len
from rich.text import Text

from . import plan as P


@dataclass
class Drawn:
    """A view, drawn: its lines, where each node's cell is, the order j and k walk, and one line
    saying what the view shows at a glance."""

    lines: list[Text]  # every line, each at most the width it was drawn at
    at: dict[str, tuple[int, int, int]]  # node id -> (line, first column, last column) of its cell
    order: list[str]  # the reading order j and k walk
    note: str  # what the view says at a glance, for the bottom line
    tall: int = 1  # the lines each cell takes, from its line down: a click on any of them is on it


VIEWS: dict[str, object] = {"outline": None}  # name -> module (draw, suits), in Tab's order
BASELINE = 50  # what the outline scores, of the 0 to 100 a view's `suits` gives: it must do better


def choose(nodes: list[P.Node], words: dict[str, str], goal: str, width: int, height: int) -> str:
    """The view this plan at this size is best seen in, by the rule above: the outline, unless a view
    that draws here, in the rows it has or showing needs, scores more by its own `suits`."""
    best, score = "outline", BASELINE
    for name, view in VIEWS.items():
        suits = getattr(view, "suits", None)
        mark = suits(nodes, width, height) if suits else 0
        if mark <= score:
            continue
        drawn = view.draw(nodes, words, goal, width, height, None)
        if drawn is not None and (len(drawn.lines) <= height or getattr(view, "NEEDS", False)):
            best, score = name, mark
    return best


def graphemes(text: str) -> list[str]:
    """Text as what a terminal draws as one, each measured whole by `cell_len`: a character with the
    zero-width ones after it (a combining accent, the variation selector of ❤️) and whatever a
    zero-width joiner joins to it (👩‍👩‍👧 is two cells, not six)."""
    out: list[str] = []
    for char in text:
        if out and (cell_len(char) == 0 or out[-1].endswith("\u200d")):
            out[-1] += char
        else:
            out.append(char)
    return out


def elide(text: str, wide: int) -> str:
    """`plan_text.elide` counted in terminal cells, as a view lays out its columns: one line of at most
    ``wide`` cells, cut at a word with "…" (a CJK character or an emoji takes two cells), never inside
    what a terminal draws as one (`graphemes`)."""
    text = " ".join(str(text).split())
    if cell_len(text) <= wide:
        return text
    if wide < 2:
        return "…"[: max(wide, 0)]

    def upto(cells: int) -> str:  # the longest start of the text in this many cells
        out = ""
        for piece in graphemes(text):
            if cell_len(out + piece) > cells:
                break
            out += piece
        return out

    cut = upto(wide).rfind(" ")
    return (text[:cut] if cut > 0 else upto(wide - 1)).rstrip(" ,;:·") + "…"


def beside(drawn: Drawn, here: str | None, way: int) -> str | None:
    """The node whose cell is nearest on screen to the left (``way`` -1) or the right (1) of this
    one's: of the cells that begin further that way, the least distance between where the two
    begin, where a line down or up counts as two columns (a terminal's cell is about twice as tall
    as it is wide). Cells in a column begin together, so a longer title never pulls the cursor."""
    if here not in drawn.at:
        return None
    line, first, _ = drawn.at[here]

    def far(cell: tuple[int, int, int]) -> tuple[int, int, int, int]:
        down = abs(cell[0] - line)
        return (cell[1] - first) * way + 2 * down, down, cell[0], cell[1]

    near = [(far(c), i) for i, c in drawn.at.items() if (c[1] - first) * way > 0]
    return min(near)[1] if near else None


def shown(store) -> list[P.Node]:
    """The nodes a view draws: what is gone is not there, and a done aside (a request typed into a
    session, finished) is its record's, not the plan's shape."""
    return [n for n in P.nodes(store) if n.state not in P.GONE and not (n.aside and n.state == P.DONE)]


def inputs(store) -> tuple[list[P.Node], dict[str, str], str]:
    """What a view is given, read from the plan as the screen reads it: the nodes, their words, the goal."""
    nodes = shown(store)
    back = {n.id for n in nodes if P.came_back(store, n)}
    goal = P.goal(store) or store.meta("goal:proposed") or "no goal yet"
    return nodes, {n.id: P.reads(n, nodes, back) for n in nodes}, goal


from . import view_dag, view_tree  # noqa: E402  (they import Drawn and elide from here)

VIEWS["tree"] = view_tree
VIEWS["dag"] = view_dag
