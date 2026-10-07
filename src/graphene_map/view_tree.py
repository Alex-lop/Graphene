"""The plan drawn top-down, the way a person draws one by hand: the goal at the top, its sub-goals
under it, their leaves under them, each parent centred over its children with a line down to each.

It is about the plan's shape. A node is its glyph and its id in its state's colour (the one row
grammar: `plan.look`), its title under them when there is room, and how many nodes it waits on
(`←2`), never which: the graph of needs is another view's. When the tree is wider than the screen
it drops the titles, then folds the sub-goals whose leaves are all done to one cell (`✓ reader 6/6`),
then lists each sub-goal's leaves down under it instead of across, and only then gives up (None),
so the screen falls back to the outline. A leaf an executor held notes what it spent and took after
its title, dim (`$0.42 · 6m`). A pure function of the nodes the screen already read: it never reads
the store."""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text

from . import plan as P
from .views import Drawn, elide

WIDEST = 30  # a cell never takes more, however few the leaves: a tree, not a table
TITLE = 8  # the least room a title needs to be worth its own line
YOURS = ("came back", "review", "yours")
# the forms tried, the one that says most first: (fold finished sub-goals, list leaves down, titles);
# finished work folds before leaves are listed down, since what is done says least
METER = True  # its draw takes the leaves' notes (views.billed)
FORMS = [(fold, stack, two) for stack in (False, True) for fold in (False, True) for two in (True, False)]


def draw(
    nodes: list[P.Node], words: dict[str, str], goal: str, width: int, height: int, cursor: str | None,
    meter: dict[str, str] | None = None,
) -> Drawn | None:
    """The tree in the first form that fits ``width``, preferring one that also fits ``height``;
    None when no form fits the width. ``meter``: a leaf's note, after its title where there is room."""
    return _pick(nodes, words, goal, width, height, cursor, meter)[0]


def suits(nodes: list[P.Node], width: int, height: int) -> int:
    """How well this view shows the plan at this size, 0 to 100: 90 when the whole tree fits with its
    titles, 10 less for each step it has to take (ids alone, folding, leaves listed down), a third of
    that when it is taller than the screen, and 0 when it cannot be drawn in the width."""
    words = {n.id: P.reads(n, nodes) for n in nodes}
    drawn, form = _pick(nodes, words, "", width, height, None)
    if drawn is None or not nodes:
        return 0
    score = 90 - 10 * form
    return score if len(drawn.lines) <= height else score // 3


def note(nodes: list[P.Node], words: dict[str, str]) -> str:
    """What the tree says at a glance: `3 sub-goals · 7 leaves · 2 wait on you · 4 proposed`."""
    parents = {n.parent for n in nodes}
    subs = sum(n.id in parents for n in nodes)
    leaves = len(nodes) - subs
    yours = sum(words.get(n.id) in YOURS for n in nodes)
    proposed = sum(words.get(n.id) == "proposed" for n in nodes)
    said = [f"{subs} sub-goal{'s' * (subs != 1)}", f"{leaves} lea{'ves' if leaves != 1 else 'f'}"]
    said += [f"{yours} wait{'s' * (yours == 1)} on you"] if yours else []
    said += [f"{proposed} proposed"] if proposed else []
    return " · ".join(said)


def _pick(nodes, words, goal, width, height, cursor, meter=None) -> tuple[Drawn | None, int]:
    fits = [
        (d, k)
        for k, form in enumerate(FORMS)
        if (d := _Tree(nodes, words, *form, meter=meter).draw(goal, width, cursor))
    ]
    return next((f for f in fits if len(f[0].lines) <= height), fits[0] if fits else (None, -1))


def _joins(xs: list[int], at: int) -> str:
    """The line from a parent at column ``at`` to its children at columns ``xs``, from ``xs[0]``."""
    if len(xs) == 1:
        return "│"
    line = ["─"] * (xs[-1] - xs[0] + 1)
    for x in xs[1:-1]:
        line[x - xs[0]] = "┬"
    line[0], line[-1] = "┌", "┐"
    line[at - xs[0]] = "┼" if at in xs[1:-1] else "┴"
    return "".join(line)


class _Tree:
    """One form of the tree: ``fold`` shows a sub-goal whose leaves are all done as one cell,
    ``stack`` lists the leaves of a sub-goal down under it (its glyph the spine), ``two`` gives
    each cell its title on a second line."""

    def __init__(self, nodes: list[P.Node], words: dict[str, str], fold: bool, stack: bool, two: bool,
                 meter: dict[str, str] | None = None):  # fmt: skip
        self.meter = meter or {}
        self.by_id = {n.id: n for n in nodes}
        self.under: dict[str | None, list[P.Node]] = {}
        for n in nodes:  # a node whose parent is not drawn hangs from the goal
            self.under.setdefault(n.parent if n.parent in self.by_id else None, []).append(n)
        self.words, self.stack, self.two = words, stack, two
        self.h, self.gap = (2, 2) if two else (1, 1)
        mine = {n.id: self.leaves(n.id) for n in nodes if fold and self.under.get(n.id)}
        self.folded = {i: len(xs) for i, xs in mine.items() if all(words.get(x.id) == "done" for x in xs)}
        self.rows: dict[int, list[tuple[int, Text]]] = {}
        self.at: dict[str, tuple[int, int, int]] = {}
        self.slot = 0

    def leaves(self, node_id: str) -> list[P.Node]:
        return [x for n in self.under.get(node_id, []) for x in (self.leaves(n.id) or [n])]

    def kids(self, node_id: str | None) -> list[P.Node]:
        return [] if node_id in self.folded else self.under.get(node_id, [])

    def stacked(self, node_id: str | None) -> bool:
        """A sub-goal (never the goal) whose children are all leaves, listed down under it."""
        kids = self.kids(node_id)
        return self.stack and node_id is not None and bool(kids) and not any(self.kids(k.id) for k in kids)

    def head(self, n: P.Node) -> Text:
        """A cell's first line: glyph and id in the state's colour, then a folded sub-goal's count or
        how many nodes it waits on."""
        glyph, colour = P.look("done" if n.id in self.folded else self.words.get(n.id, ""))
        out = Text(f"{glyph} {n.id}", colour)
        waits = sum(1 for i in n.needs if i in self.by_id and self.by_id[i].state != P.DONE)
        if n.id in self.folded:
            out.append(f" {self.folded[n.id]}/{self.folded[n.id]}", colour)
        elif self.two and waits:
            out.append(f" ←{waits}", "dim")
        return out

    def need(self, n: P.Node, down: bool) -> int:
        """The columns a node's cell needs; ``down``: listed under its sub-goal, after `├ `."""
        least = self.head(n).cell_len + 2 * down
        return max(least, 2 + 2 * down + TITLE) if self.two else least

    def spans(self, node_id: str | None) -> list[int]:
        """The least columns of each slot under a node, in order: a leaf's cell, or a sub-goal listed
        down (its head, and its leaves under it after `├ `). A sub-goal drawn across widens the slots
        under it, evenly, until its own cell fits over them; a folded one is as narrow as its cell."""
        kids = self.kids(node_id)
        if node_id is None and not kids:
            return [1]
        if not kids or self.stacked(node_id):
            return [max([self.need(self.by_id[node_id], False)] + [self.need(k, True) for k in kids])]
        out = [w for k in kids for w in self.spans(k.id)]
        mine = self.need(self.by_id[node_id], False) if node_id is not None else 0
        for k in range(mine - sum(out) - self.gap * (len(out) - 1)):
            out[k % len(out)] += 1
        return out

    def widths(self, width: int) -> list[int] | None:
        """Each slot's columns: every slot as wide as the others while that fits (with titles, as wide
        as an even share, up to WIDEST), then the narrow ones narrower, down to what each needs."""
        need = self.spans(None)
        gaps = self.gap * (len(need) - 1)
        target = min((width - gaps) // len(need), WIDEST) if self.two else max(need)
        while target >= 0:
            got = [max(n, target) for n in need]
            if sum(got) + gaps <= width:
                return got
            target -= 1
        return None

    def draw(self, goal: str, width: int, cursor: str | None) -> Drawn | None:
        wide = self.widths(width)
        if wide is None:
            return None
        self.left = [(width - sum(wide) - self.gap * (len(wide) - 1)) // 2]
        for w in wide:
            self.left.append(self.left[-1] + w + self.gap)
        while cursor is not None and cursor in self.by_id and not self.visible(self.by_id[cursor]):
            cursor = self.by_id[cursor].parent  # inside a folded sub-goal: the fold is where it is
        self.cursor = cursor
        mid = self.place(None, 0)
        said = elide(goal or "no goal yet", width)
        self.put(0, min(max(mid - cell_len(said) // 2, 0), width - cell_len(said)), Text(said, "bold"))
        order = [n.id for n in self.walk(None)]
        return Drawn(self.lines(), dict(self.at), order, note(list(self.by_id.values()), self.words), self.h)

    def visible(self, n: P.Node) -> bool:
        return not any(a.id in self.folded for a in P.above(n, self.by_id))

    def walk(self, node_id: str | None) -> list[P.Node]:
        return [x for k in self.kids(node_id) for x in (k, *self.walk(k.id))]

    def row(self, depth: int) -> int:
        return 0 if depth == 0 else 2 + (depth - 1) * (self.h + 1)

    def place(self, node_id: str | None, depth: int) -> int:
        """Lay out a node and everything under it; the column its line from above lands on. Its cell
        may take the columns of every slot under it, as long as it stays centred (or starts) there."""
        kids, first = self.kids(node_id), self.slot
        if not kids or self.stacked(node_id):
            left, wide = self.left[self.slot], self.left[self.slot + 1] - self.left[self.slot] - self.gap
            self.slot += 1
            at = left if self.stack else left + wide // 2
        else:
            xs = [self.place(k.id, depth + 1) for k in kids]
            at = (xs[0] + xs[-1]) // 2
            self.put(self.row(depth) + (1 if depth == 0 else self.h), xs[0], Text(_joins(xs, at), "dim"))
        if node_id is None:
            return at
        lo, hi = self.left[first], self.left[self.slot] - self.gap - 1
        a, b = at - lo, hi - at
        room = b + 1 if self.stack else max(2 * min(a, b + 1), 2 * min(a, b) + 1)
        n = self.by_id[node_id]
        self.cell(n, self.row(depth), at, room, "│ " if self.stacked(node_id) else "  ")
        for i, k in enumerate(kids if self.stacked(node_id) else []):
            last = i == len(kids) - 1
            y = self.row(depth) + self.h * (i + 1)
            self.put(y, at, Text("└ " if last else "├ ", "dim"))
            if self.two and not last:
                self.put(y + 1, at, Text("│", "dim"))
            self.cell(k, y, at + 2, hi - at - 1, "  ")
        return at

    def cell(self, n: P.Node, y: int, at: int, room: int, lead: str) -> None:
        """A node's cell at line ``y``, in at most ``room`` columns: each line centred on ``at``, or
        starting there when leaves are listed down (the glyph is the spine, and ``lead`` goes before
        the title on the second line)."""
        head, lead = self.head(n), lead if self.stack else ""
        lines = [head]
        if self.two:
            note, left = self.meter.get(n.id, ""), room - len(lead)
            if note and left - 1 - cell_len(note) >= min(cell_len(n.title), TITLE):  # the title keeps room
                left -= 1 + cell_len(note)
            else:
                note = ""
            lines.append(Text(lead, "dim") + Text(elide(n.title, left)))
            if note:
                lines[-1].append(f" {note}", "dim")
        xs = [at if self.stack else at - line.cell_len // 2 for line in lines]
        for k, (x, line) in enumerate(zip(xs, lines, strict=True)):
            if n.id == self.cursor:
                line.stylize("reverse")
            self.put(y + k, x, line)
        self.at[n.id] = (y, min(xs), max(x + line.cell_len for x, line in zip(xs, lines, strict=True)) - 1)

    def put(self, y: int, x: int, piece: Text) -> None:
        self.rows.setdefault(y, []).append((x, piece))

    def lines(self) -> list[Text]:
        out = []
        for y in range(max(self.rows) + 1):
            line = Text()
            for x, piece in sorted(self.rows.get(y, []), key=lambda p: p[0]):
                line.append(" " * (x - line.cell_len))
                line.append_text(piece)
            out.append(line)
        return out
