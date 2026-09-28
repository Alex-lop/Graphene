"""The plan as a directed graph, left to right: what can run at once, what waits, and on what.

Only leaves are drawn, since a leaf is what someone does. A leaf's column is the longest chain of
`needs` before it (`plan_view.depths`, the page's own columns), so everything in one column could
run at once and everything to its right waits on something to its left. What a sub-goal needs, its
leaves wait on, and a need on a sub-goal is a need on each leaf beneath it (decision 14). A need
already implied by another (c needs a and b, b needs a) is not drawn twice.

Each line goes right from the leaf that is needed, down or up a track of its own in the gap before
the leaf that waits, and into it at ▸, so a line never runs through a cell. Where a line crosses a
track it does not join, the track is drawn unbroken (│) and the line gives way; a join is a junction
(┬ ┤ ┼). The critical path, the longest chain of leaves not done yet, is bold and heavy (━).

A cell is the row grammar's glyph and colour (`plan.look`), the id, never cut, and the title as far
as the column allows. When the width is short, titles go first; when even glyph and id do not fit,
there is no graph (`draw` returns None) and the screen shows the outline.
"""

from __future__ import annotations

import itertools
import unicodedata
from dataclasses import dataclass, replace
from functools import partial

from rich.cells import cell_len
from rich.text import Text

from . import plan as P
from . import plan_view
from .plan_view import depths, outline
from .views import Drawn, elide, graphemes

LEAST_TITLE = 6  # a title with less room than this is left out: "the…" says nothing
KINDS = {"done": "done", "running": "running", "came back": "on you", "review": "on you", "yours": "on you"}
NEEDS = True  # it draws which leaf waits on which, as the outline cannot (views.choose)


def _box() -> dict[tuple[int, int, int, int], str]:
    """Every light and heavy box-drawing character, by the weight (0 none, 1 light, 2 heavy) of its
    arm up, down, left and right, read from its Unicode name ("DOWN LIGHT AND RIGHT HEAVY")."""
    arms = {"UP": "u", "DOWN": "d", "LEFT": "l", "RIGHT": "r", "VERTICAL": "ud", "HORIZONTAL": "lr"}
    out = {}
    for code in range(0x2500, 0x2580):
        name = unicodedata.name(chr(code)).removeprefix("BOX DRAWINGS ")
        if any(word in name for word in ("DOUBLE", "DASH", "ARC", "DIAGONAL")):
            continue
        got, weight = dict.fromkeys("udlr", 0), 1
        for part in name.split(" AND "):
            words = part.split()
            weight = 2 if "HEAVY" in words else 1 if "LIGHT" in words else weight
            for word in words:
                for arm in arms.get(word, ""):
                    got[arm] = weight
        out[tuple(got.values())] = chr(code)
    return out


BOX = _box()


@dataclass
class _Graph:
    leaves: list[P.Node]  # in the outline's order
    level: dict[str, int]  # the column
    needs: dict[str, list[str]]  # the leaves each one waits on, none implied by another
    rank: dict[str, int]  # `plan.order`'s place: what breaks a tie


def _graph(nodes: list[P.Node]) -> _Graph:
    under = P.kids(nodes, drawn=True)
    by_id = {n.id: n for n in nodes}
    leaves = [n for n, _ in outline(nodes) if not under.get(n.id)]
    ids = {n.id for n in leaves}
    raw: dict[str, list[str]] = {}
    for leaf in leaves:
        got = []
        for need in P.all_needs(leaf, by_id):
            got += [need] if need in ids else [n.id for n in P.below(need, nodes) if n.id in ids]
        raw[leaf.id] = [i for i in dict.fromkeys(got) if i != leaf.id]
    waits = [replace(n, needs=raw[n.id]) for n in leaves]
    level = depths(waits)
    raw = {i: [x for x in r if level[x] < level[i]] for i, r in raw.items()}  # a cycle: validate refuses it
    upstream: dict[str, set[str]] = {}
    for i in sorted(raw, key=level.__getitem__):
        upstream[i] = set(raw[i]).union(*(upstream[x] for x in raw[i]))
    needs = {i: [x for x in r if not any(x in upstream[y] for y in r)] for i, r in raw.items()}
    return _Graph(leaves, level, needs, {n.id: k for k, n in enumerate(P.order(waits))})


def critical_path(nodes: list[P.Node]) -> list[str]:
    """The longest chain of leaves not done yet, first to last, through what each needs: what
    decides how long the plan takes however many run at once. The page's own (`plan_view`)."""
    return plan_view.critical_path(nodes)


def at_once(nodes: list[P.Node], words: dict[str, str]) -> list[str]:
    """The leaves that could start now, proposed ones too (they start once accepted): the page's own
    (`plan_view`). ``words`` is kept for the view's callers; the plan alone decides it."""
    return plan_view.at_once(nodes)


def note(nodes: list[P.Node], words: dict[str, str]) -> str:
    """What the graph says at a glance, for the bottom line, the critical path first so 80 columns
    never cut it: `critical ━ a > b > c (3) · 2 ready · 1 more once accepted · 2 wait · 1 running ·
    1 on you · 4 done`. "ready" is what `R` starts, the status line's own count; "once accepted" is
    a proposal that could start as soon as it is; "wait" is every other leaf not done. Every leaf is
    counted once, so the counts add up to the leaves drawn. A path of one leaf is no path."""
    g = _graph(nodes)
    if not g.leaves:
        return "no leaves yet"
    if all(words.get(n.id) == "done" for n in g.leaves):
        return "every leaf done"
    now = set(at_once(nodes, words))
    count = dict.fromkeys(["ready", "once accepted", "wait", "running", "on you", "done"], 0)
    for n in g.leaves:
        word = words.get(n.id, "")
        later = "once accepted" if n.id in now and word == "proposed" else "wait"
        count[KINDS.get(word) or ("ready" if word == "ready" else later)] += 1
    path = critical_path(nodes)
    shown = path if len(path) <= 4 else [*path[:2], "…", path[-1]]
    said = [f"critical ━ {' > '.join(shown)} ({len(path)})"] if len(path) > 1 else []
    said.append(f"{count['ready']} ready" if count["ready"] else "none ready")
    if count["once accepted"]:
        said.append(f"{count['once accepted']}{' more' if count['ready'] else ''} once accepted")
    said += [f"{count[k]} {k}" for k in ("wait", "running", "on you", "done") if count[k] or k == "wait"]
    return " · ".join(said)


# -- where everything goes ---------------------------------------------------------------------------


def _edges(g: _Graph) -> list[tuple[str, str]]:
    return [(s, t) for t in g.level for s in g.needs[t]]


def _rows(g: _Graph, path: list[str]) -> dict[str, int]:
    """Each leaf's row. Leaves joined by lines are drawn together, each such group under the one
    before it in the outline's order, so no line runs from one into another. In a group a leaf goes
    as near below the row of what it needs as it can (the critical one's first, so the critical path
    runs straight), on no row a longer line passes through and no row a line not its own comes in on.
    A leaf that needs two or more sits on no row a line comes in on at all: its track ends in a
    corner into it (└▸), so a track's one corner is where it goes and every ┤ ┴ ┼ on it is a need."""
    first, edges = set(path), _edges(g)
    place = {n.id: k for k, n in enumerate(g.leaves)}
    joined = {i: i for i in place}

    def root(i: str) -> str:
        while joined[i] != i:
            i = joined[i]
        return i

    for s, t in edges:
        joined[root(t)] = root(s)
    groups: dict[str, set[str]] = {}
    for n in g.leaves:
        groups.setdefault(root(n.id), set()).add(n.id)
    row: dict[str, int] = {}

    def near(t: str, top: int) -> tuple[int, bool, int]:  # the first column keeps the outline's order
        ups = sorted(g.needs[t], key=lambda s: (s not in first, row[s]))
        return (row[ups[0]], t not in first, place[t]) if ups else (top, False, place[t])

    for members in groups.values():
        top = max(row.values(), default=-1) + 1
        mine = [(s, t) for s, t in edges if t in members]
        for k in sorted({g.level[i] for i in members}):
            taken = {row[s] for s, t in mine if g.level[s] < k < g.level[t]}
            lead: dict[int, set[str]] = {}  # a row a line comes in on from the left: where it goes
            for s, t in mine:
                if g.level[s] < k <= g.level[t]:
                    lead.setdefault(row[s], set()).add(t)
            for t in sorted((i for i in members if g.level[i] == k), key=partial(near, top=top)):
                r, alone = near(t, top)[0], len(g.needs[t]) < 2
                while r in taken or (r in lead and not (alone and t in lead[r])):
                    r += 1
                row[t] = r
                taken.add(r)
    return row


def _tracks(g: _Graph, row: dict[str, int]) -> list[list[str]]:
    """For the gap before each column, the leaves in it that need a track (a line comes from another
    row), in the order that crosses fewest lines; the gap before column 0 has none."""
    edges = _edges(g)
    out: list[list[str]] = [[]]
    for k in range(1, max(g.level.values(), default=-1) + 1):
        joined = {t: {row[s] for s in g.needs[t]} | {row[t]} for t in g.level if g.level[t] == k}
        bus = sorted((t for t, rows in joined.items() if len(rows) > 1), key=row.__getitem__)
        lead: dict[int, list[str]] = {}
        for s, t in edges:
            if g.level[s] < k <= g.level[t]:
                lead.setdefault(row[s], []).append(t)
        # ponytail: every order up to 6 tracks in a gap (720); past that, top to bottom or bottom to top,
        # whichever crosses fewer (a fan-out crosses none bottom to top); a mixed gap may still comb
        orders = itertools.permutations(bus) if len(bus) <= 6 else [tuple(bus), tuple(reversed(bus))]
        out.append(list(min(orders, key=partial(_crossings, lead=lead, joined=joined, row=row), default=())))
    return out


def _crossings(order: tuple[str, ...], lead: dict, joined: dict, row: dict[str, int]) -> int:
    """How many lines in one gap cross a track they do not join, with the tracks in ``order``."""
    at = {t: m + 1 for m, t in enumerate(order)}  # 0 is where a line comes in, len + 1 the ▸
    spans = []
    for r, goes in lead.items():
        through = any(t not in at or row[t] == r for t in goes)
        spans.append((r, 0, len(order) + 1 if through else max(at[t] for t in goes)))
    spans += [(row[t], at[t], len(order) + 1) for t in order]
    return sum(
        1
        for t in order
        for r, a, b in spans
        if a < at[t] < b and min(joined[t]) < r < max(joined[t]) and r not in joined[t]
    )


def _gap(tracks: list[str]) -> int:
    """The gap before a column: a space, a dash, the tracks and a dash after them, ▸ and a space."""
    return len(tracks) + 4 + bool(tracks)


def _share(spare: int, want: dict[int, int]) -> dict[int, int]:
    """``spare`` columns shared out one at a time, each column taking no more than it wants."""
    got = dict.fromkeys(want, 0)
    while spare and (open_ := [k for k in got if got[k] < want[k]]):
        for k in open_[:spare]:
            got[k] += 1
        spare -= len(open_[:spare])
    return got


def _widths(g: _Graph, tracks: list[list[str]], width: int) -> list[int] | None:
    """Each column's width: glyph and id always, then what is left shared out to titles; a column
    whose titles would get less than LEAST_TITLE gets none, and gives its share back to the others.
    None when glyph and id do not fit."""
    levels = max(g.level.values(), default=-1) + 1
    cols = [[n for n in g.leaves if g.level[n.id] == k] for k in range(levels)]
    base = [2 + max(cell_len(n.id) for n in col) for col in cols]
    want = [1 + max(cell_len(n.title) for n in col) for col in cols]
    spare = width - sum(base) - sum(_gap(t) for t in tracks[1:])
    if spare < 0:
        return None
    titled = set(range(levels))
    while True:
        extra = _share(spare, {k: want[k] for k in titled})
        short = {k for k in titled if extra[k] < min(want[k], LEAST_TITLE + 1)}
        if not short:
            return [b + extra.get(k, 0) for k, b in enumerate(base)]
        titled -= short


def _fit(nodes: list[P.Node], width: int):
    g = _graph(nodes)
    path = critical_path(nodes)
    row = _rows(g, path)
    tracks = _tracks(g, row)
    return g, path, row, tracks, _widths(g, tracks, width)


def suits(nodes: list[P.Node], width: int, height: int) -> int:
    """How well this view fits the plan, 0 to 100: none when no leaf needs another (it is a list
    then) or it does not fit the width, more the more leaves a line touches, halved when it is taller
    than the screen."""
    g, _, row, _, widths = _fit(nodes, width)
    edges = _edges(g)
    if not edges or widths is None:
        return 0
    touched = {i for edge in edges for i in edge}
    score = 40 + 60 * len(touched) // len(g.leaves)
    return score // 2 if max(row.values()) + 2 > height else score


# -- drawing -----------------------------------------------------------------------------------------

STRENGTH = {"dim": 0, "": 1, "bold": 2}


def draw(
    nodes: list[P.Node], words: dict[str, str], goal: str, width: int, height: int, cursor: str | None
) -> Drawn | None:
    """The graph at ``width``: the goal's line, then a row for each row of leaves. None when even
    glyph and id do not fit; taller than ``height`` is the seam's to scroll."""
    g, path, row, tracks, widths = _fit(nodes, width)
    if widths is None:
        return None
    levels = len(widths)
    left = [0] * levels
    for k in range(1, levels):
        left[k] = left[k - 1] + widths[k - 1] + _gap(tracks[k])
    track = {t: left[k] - _gap(tracks[k]) + 2 + m for k in range(levels) for m, t in enumerate(tracks[k])}
    arrow = [x - 2 for x in left]
    cell = {n.id: _cell(n, words.get(n.id, ""), widths[g.level[n.id]], n.id in path) for n in g.leaves}
    critical = set(zip(path, path[1:], strict=False))
    arms: dict[tuple[int, int], dict[str, int]] = {}
    style: dict[tuple[int, int], str] = {}
    joins = {t: {row[s] for s in g.needs[t]} | {row[t]} for t in track}

    def crossing(y: int, x: int, t: str) -> bool:  # a track that is not this line's, and not joined here
        return any(x == track[b] and b != t and min(j) < y < max(j) and y not in j for b, j in joins.items())

    def mark(y: int, x: int, arm: str, weight: int, how: str) -> None:
        got = arms.setdefault((y, x), dict.fromkeys("udlr", 0))
        got[arm] = max(got[arm], weight)
        if STRENGTH[how] >= STRENGTH[style.get((y, x), "dim")]:
            style[(y, x)] = how

    for s, t in _edges(g):
        weight = 2 if (s, t) in critical else 1
        how = "bold" if weight == 2 else "dim" if words.get(s) == "done" else ""
        y0, y1, end = row[s], row[t], arrow[g.level[t]]
        turn = track.get(t, end - 1) if y0 != y1 else end - 1
        points = [(y0, x) for x in range(left[g.level[s]] + len(cell[s]) + 1, turn + 1)]
        step = 1 if y1 > y0 else -1
        points += [(y, turn) for y in range(y0 + step, y1 + step, step)] if y0 != y1 else []
        points += [(y1, x) for x in range(turn + 1, end)]
        mark(*points[0], "l", weight, how)
        mark(*points[-1], "r", weight, how)
        for (ya, xa), (yb, xb) in itertools.pairwise(points):
            out, back = ("r", "l") if xb > xa else ("d", "u") if yb > ya else ("u", "d")
            if not (ya == yb and crossing(ya, xa, t)):
                mark(ya, xa, out, weight, how)
            if not (ya == yb and crossing(yb, xb, t)):
                mark(yb, xb, back, weight, how)
        style[(y1, end)] = "bold" if weight == 2 or style.get((y1, end)) == "bold" else how
        arms[(y1, end)] = {}

    rows = max(row.values(), default=-1) + 1
    total = left[-1] + widths[-1] if levels else 0
    grid = [[(" ", "")] * total for _ in range(rows)]
    for (y, x), got in arms.items():
        grid[y][x] = (BOX.get(tuple(got.values()), "▸") if got else "▸", style[(y, x)])
    at: dict[str, tuple[int, int, int]] = {}
    lines = [Text(elide(goal, width), "bold")] if goal else []
    for n in g.leaves:
        x, y = left[g.level[n.id]], row[n.id]
        for k, (char, how) in enumerate(cell[n.id]):
            grid[y][x + k] = (char, f"{how} reverse".strip() if n.id == cursor else how)
        at[n.id] = (len(lines) + y, x, x + len(cell[n.id]) - 1)
    for line in grid:
        text = Text()
        for how, run in itertools.groupby(line, key=lambda cell: cell[1]):
            text.append("".join(char for char, _ in run), how)
        text.rstrip()
        lines.append(text)
    order = sorted(at, key=lambda i: (g.level[i], row[i]))
    return Drawn(lines=lines, at=at, order=order, note=note(nodes, words))


def _cell(node: P.Node, word: str, wide: int, critical: bool) -> list[tuple[str, str]]:
    """A leaf's cell as characters and their styles: its glyph and id in its state's colour, bold
    on the critical path, then its title as far as ``wide`` goes; a done leaf is dim but its ✓."""
    glyph, colour = P.look(word)
    done = word == "done"
    ident = "dim" if done else f"{colour} bold".strip() if critical else colour
    out = [(glyph, colour), (" ", "")] + _columns(node.id, ident)
    room = wide - len(out) - 1
    if room >= min(cell_len(node.title), LEAST_TITLE):
        out += [(" ", "")] + _columns(elide(node.title, room), "dim" if done else "")
    return out


def _columns(text: str, how: str) -> list[tuple[str, str]]:
    """Text as one entry a terminal column, as the grid is laid out: a wide character's second column
    is "", and what a terminal draws as one (`graphemes`) is one entry."""
    out: list[tuple[str, str]] = []
    for char in graphemes(text):
        wide = cell_len(char)
        if wide == 0 and out:
            out[-1] = (out[-1][0] + char, how)
        else:
            out += [(char, how)] + [("", how)] * (wide - 1)
    return out
