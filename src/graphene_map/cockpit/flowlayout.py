"""A small layered graph layout, drawn in box-drawing characters. Pure functions: no Textual, no store.

Left to right: a node's layer is its longest path from a source; order inside a layer comes from a few
barycentre sweeps; edges are right-angled and run in lanes between layers, so a crossing is a `┼` and a
fan-out is a trunk with branches. An edge that would close a cycle (found by a depth-first search, or
declared `loop`) is a "back edge": it leaves the right of its source, drops to a lane under every node,
runs back and comes in at the left of its target, so no line ever crosses a box. A `two` edge has an
arrowhead at both ends; a `tree` edge (a goal over what serves it) has none, and is drawn quieter than any
other. Positions are a function of the graph alone, so a recolour never moves a node.

The result is cells: (char, style) per position, plus each node's rectangle for mouse hit-testing.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from rich.cells import cell_len

N, E, S, W = 1, 2, 4, 8
JOIN = {
    0: " ", N: "│", S: "│", N | S: "│", E: "─", W: "─", E | W: "─",
    E | S: "┌", S | W: "┐", N | E: "└", N | W: "┘", N | S | E: "├", N | S | W: "┤",
    E | W | S: "┬", E | W | N: "┴", N | E | S | W: "┼",
}  # fmt: skip
RANK = {"": 0, "edge_tree": 1, "edge": 2, "edge_hot": 3, "edge_loop": 4}  # two edges in a cell: the louder
BOX = {
    "light": "╭╮╰╯─│", "heavy": "┏┓┗┛━┃", "double": "╔╗╚╝═║", "square": "┌┐└┘─│",
}  # fmt: skip


@dataclass
class GNode:
    id: str
    label: str
    state: str = "waiting"  # a key of the caller's style table
    badge: str = ""  # who is on it, shown on the bottom border: it never makes the box wider


@dataclass
class GEdge:
    a: str
    b: str
    kind: str = "needs"  # needs: a to b · two: a and b, both ways · loop: a to b, always drawn as a back edge
    # · tree: b is under a (a goal over what serves it): a line with no arrowhead


@dataclass
class Layout:
    width: int = 0
    height: int = 0
    cells: list[list[tuple[str, str]]] = field(default_factory=list)  # row -> [(char, style)]
    rects: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)  # id -> x0, y0, x1, y1
    layers: dict[str, int] = field(default_factory=dict)
    back: list[tuple[str, str]] = field(default_factory=list)
    hidden: int = 0  # nodes left out of a neighbourhood view

    def text(self) -> str:
        return "\n".join("".join(c for c, _ in row).rstrip() for row in self.cells)

    def at(self, x: int, y: int) -> str | None:
        for nid, (x0, y0, x1, y1) in self.rects.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return nid
        return None


def neighbourhood(
    nodes: list[GNode], edges: list[GEdge], focus: str, hops: int, up: bool = True
) -> tuple[list[GNode], list[GEdge]]:
    """The nodes within ``hops`` of ``focus``, either direction, the goals over ``focus`` by `tree` edges, up
    to the top (why it is there) unless ``up`` is False, and the edges among them."""
    near, front = {focus}, {focus}
    for _ in range(hops):
        front = {y for e in edges for x, y in ((e.a, e.b), (e.b, e.a)) if x in front} - near
        near |= front
    parent, at = {e.b: e.a for e in edges if e.kind == "tree"}, focus
    for _ in nodes if up else ():  # a tree has no cycle; this is the most steps up there can be if one did
        if (at := parent.get(at)) is None:
            break
        near.add(at)
    return [n for n in nodes if n.id in near], [e for e in edges if e.a in near and e.b in near]


def layout(
    nodes: list[GNode],
    edges: list[GEdge],
    *,
    label_w: int = 18,
    selected: str | None = None,
    styles: dict[str, str] | None = None,
    columns: int = 1,
) -> Layout:
    """Lay ``nodes`` out left to right and draw them. ``styles`` maps a node state to a style string. With no
    edges there is nothing to order, so ``columns`` wraps the list into that many (the first column first)."""
    styles = styles or {}
    ids = [n.id for n in nodes]
    if not ids:
        return Layout()
    by_id = {n.id: n for n in nodes}
    edges = [e for e in edges if e.a in by_id and e.b in by_id and e.a != e.b]
    forward, back = _split(ids, edges)
    layer = _layers(ids, forward)
    if columns > 1 and not edges:
        per = -(-len(ids) // columns)
        layer = {n: k // per for k, n in enumerate(ids)}
    rows = _order(ids, forward, layer)  # layer -> [id or dummy]
    boxes = {n.id: _box(n, label_w) for n in nodes}
    return _draw(nodes, boxes, edges, forward, back, layer, rows, selected, styles)


# -- structure ---------------------------------------------------------------------------------------


def _split(ids: list[str], edges: list[GEdge]) -> tuple[list[GEdge], list[GEdge]]:
    """Edges that keep the graph acyclic, and the ones that close a cycle (a depth-first search finds
    them; a `loop` edge is one by declaration). Everything is judged in the order the caller gave."""
    out: dict[str, list[GEdge]] = {i: [] for i in ids}
    for e in edges:
        if e.kind != "loop":
            out[e.a].append(e)
    state: dict[str, int] = {}
    back: set[int] = {id(e) for e in edges if e.kind == "loop"}

    def visit(root: str) -> None:
        stack = [(root, iter(out[root]))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            for e in it:
                seen = state.get(e.b, 0)
                if seen == 1:
                    back.add(id(e))  # to an ancestor still being visited: it closes a cycle
                elif seen == 0:
                    state[e.b] = 1
                    stack.append((e.b, iter(out[e.b])))
                    break
            else:
                state[node] = 2
                stack.pop()

    for i in ids:
        if state.get(i, 0) == 0:
            visit(i)
    return [e for e in edges if id(e) not in back], [e for e in edges if id(e) in back]


def _layers(ids: list[str], forward: list[GEdge]) -> dict[str, int]:
    preds: dict[str, list[str]] = {i: [] for i in ids}
    for e in forward:
        preds[e.b].append(e.a)
    layer: dict[str, int] = {}

    def depth(i: str) -> int:
        if i not in layer:
            layer[i] = -1  # a guard: the forward edges are acyclic, so it is never read
            layer[i] = 1 + max((depth(p) for p in preds[i]), default=-1)
        return layer[i]

    for i in ids:
        depth(i)
    return layer


def _order(ids: list[str], forward: list[GEdge], layer: dict[str, int]) -> list[list[str]]:
    """Nodes (and one dummy for each layer an edge passes) in each layer, ordered to cut crossings."""
    top = max(layer.values())
    rows: list[list[str]] = [[] for _ in range(top + 1)]
    for i in ids:
        rows[layer[i]].append(i)
    links: list[tuple[str, str]] = []  # consecutive pairs along every edge, through dummies
    for n, e in enumerate(forward):
        chain = [e.a, *(f"~{n}:{k}" for k in range(layer[e.a] + 1, layer[e.b])), e.b]
        for k in range(layer[e.a] + 1, layer[e.b]):
            rows[k].append(f"~{n}:{k}")
        links += list(zip(chain, chain[1:], strict=False))
    above: dict[str, list[str]] = {}
    below: dict[str, list[str]] = {}
    for a, b in links:
        below.setdefault(a, []).append(b)
        above.setdefault(b, []).append(a)

    def bary(n: str, near: dict[str, list[str]], pos: dict[str, int]) -> float:
        got = [pos[m] for m in near.get(n, ())]
        return sum(got) / len(got) if got else pos[n]

    for sweep in range(4):
        pos = {n: k for row in rows for k, n in enumerate(row)}
        order = range(1, len(rows)) if sweep % 2 == 0 else range(len(rows) - 2, -1, -1)
        near = above if sweep % 2 == 0 else below
        for li in order:
            rows[li].sort(key=lambda n, near=near, pos=pos: (bary(n, near, pos), pos[n]))
            pos.update({n: k for k, n in enumerate(rows[li])})
    return rows


# -- boxes -------------------------------------------------------------------------------------------


@dataclass
class Box:
    lines: list[str]
    w: int
    h: int


def _box(n: GNode, label_w: int) -> Box:
    lines = textwrap.wrap(n.label, label_w, break_long_words=True) or [n.id]
    for w in range(-(-len(n.label) // len(lines)), label_w) if 1 < len(lines) <= 3 else ():
        even = textwrap.wrap(n.label, w, break_long_words=False)  # a word longer than w is never cut for it
        if len(even) == len(lines) and max(map(len, even)) <= w:
            lines = even  # as many lines, as even as they go: no word left alone on the last
            break
    if len(lines) > 3:
        lines = [*lines[:2], lines[2][: label_w - 1] + "…"]
    inner = max(max(cell_len(x) for x in lines), 6)  # in cells: a wide character is two
    return Box([x + " " * (inner - cell_len(x)) for x in lines], inner + 4, len(lines) + 2)


def spread(text: str) -> list[str]:
    """One entry for each terminal cell the text covers: a wide character is itself, then an empty cell."""
    out: list[str] = []
    for ch in text:
        out.append(ch)
        out += [""] * (cell_len(ch) - 1)
    return out


# -- drawing -----------------------------------------------------------------------------------------


def _draw(nodes, boxes, edges, forward, back, layer, rows, selected, styles) -> Layout:
    chains: list[tuple[GEdge, list[str]]] = []
    for n, e in enumerate(forward):
        chains.append((e, [e.a, *(f"~{n}:{k}" for k in range(layer[e.a] + 1, layer[e.b])), e.b]))

    def hgt(n: str) -> int:
        return boxes[n].h if n in boxes else 1

    def wid(n: str) -> int:
        return boxes[n].w if n in boxes else 1

    # -- y: stack each layer, then pull nodes toward their neighbours, keeping the order
    y: dict[str, int] = {}
    for row in rows:
        at = 0
        for n in row:
            y[n] = at
            at += hgt(n) + 1
    nbr: dict[str, list[str]] = {}
    for _, chain in chains:
        for a, b in zip(chain, chain[1:], strict=False):
            nbr.setdefault(a, []).append(b)
            nbr.setdefault(b, []).append(a)

    def mid(n: str) -> float:
        return y[n] + (hgt(n) - 1) / 2

    for sweep in range(6):
        for row in rows if sweep % 2 == 0 else reversed(rows):
            want = {
                n: (sum(mid(m) for m in nbr[n]) / len(nbr[n]) - (hgt(n) - 1) / 2 if n in nbr else y[n])
                for n in row
            }
            at = 0.0
            for n in row:
                y[n] = int(round(max(want[n], at)))
                at = y[n] + hgt(n) + 1
    low = min(y.values())
    for n in y:
        y[n] -= low
    body = max(y[n] + hgt(n) for n in y)

    # -- lanes: each gap between layers gets one lane per overlapping vertical run
    pieces: dict[int, list[tuple[int, int, str, str]]] = {}  # gap -> (y from, y to, src node, dst node)
    for _, chain in chains:
        for a, b in zip(chain, chain[1:], strict=False):
            ya, yb = int(mid(a)), int(mid(b))
            pieces.setdefault(layer_of(a, layer, chain), []).append((ya, yb, a, b))
    back_runs = [(e, k) for k, e in enumerate(back)]
    lane_y = {k: body + 1 + k for _, k in back_runs}  # one row under the boxes for each back edge
    lanes: dict[int, dict[tuple[str, str], int]] = {}
    used: dict[int, int] = {}
    for gap, items in pieces.items():
        lanes[gap] = {}
        placed: list[tuple[int, int, str, str, int]] = []
        for ya, yb, a, b in sorted(items, key=lambda t: (min(t[0], t[1]), max(t[0], t[1]))):
            if ya == yb:
                lanes[gap][(a, b)] = -1  # straight across: no lane
                continue
            lo, hi = min(ya, yb), max(ya, yb)
            taken = {
                ln
                for plo, phi, pa, pb, ln in placed
                if not (hi < plo or phi < lo) and not (pa == a or pb == b)  # a trunk is shared by one end
            }
            ln = next(k for k in range(len(items) + 1) if k not in taken)
            placed.append((lo, hi, a, b, ln))
            lanes[gap][(a, b)] = ln
        used[gap] = 1 + max((v for v in lanes[gap].values()), default=-1)
    # back edges: down in the gap after the source's layer, up in the gap before the target's
    back_lane: dict[tuple[int, int], int] = {}
    for e, k in back_runs:
        for gap in (layer[e.a], layer[e.b] - 1):
            back_lane[(k, gap)] = used.get(gap, 0)
            used[gap] = used.get(gap, 0) + 1
    gaps = len(rows)
    width_of = [max(wid(n) for n in row) for row in rows]
    gap_w = {g: max(4, used.get(g, 0) + 3) for g in range(-1, gaps)}
    if not any(layer[e.b] == 0 for e in back):
        gap_w[-1] = 0
    x0 = []
    at = gap_w[-1]
    for li in range(gaps):
        x0.append(at)
        at += width_of[li] + gap_w[li]
    total_w = at - gap_w[gaps - 1] + 1
    total_h = body + len(back) + 1

    mask = [[0] * (total_w + 2) for _ in range(total_h + 1)]
    style = [[""] * (total_w + 2) for _ in range(total_h + 1)]
    mark: dict[tuple[int, int], tuple[str, str]] = {}

    def x_of(n: str) -> int:
        return x0[layer_of(n, layer, None, rows)]

    def lane_x(gap: int, ln: int) -> int:
        return x0[gap] + width_of[gap] + 1 + ln

    def line(points: list[tuple[int, int]], st: str) -> None:
        for (ax, ay), (bx, by) in zip(points, points[1:], strict=False):
            if (ax, ay) == (bx, by):
                continue
            step = (1 if bx > ax else -1 if bx < ax else 0, 1 if by > ay else -1 if by < ay else 0)
            x, yy = ax, ay
            while True:
                nx, ny = x + step[0], yy + step[1]
                d = {(1, 0): (E, W), (-1, 0): (W, E), (0, 1): (S, N), (0, -1): (N, S)}[step]
                mask[yy][x] |= d[0]
                mask[ny][nx] |= d[1]
                for cx, cy in ((x, yy), (nx, ny)):
                    if RANK.get(st, 1) >= RANK.get(style[cy][cx], 0):
                        style[cy][cx] = st
                x, yy = nx, ny
                if (x, yy) == (bx, by):
                    break

    loops = {(e.a, e.b) for e in edges if e.kind == "loop"}
    trees = {(e.a, e.b) for e in edges if e.kind == "tree"}

    def hot(a: str, b: str) -> str:
        if (a, b) in loops:
            return "edge_loop"
        if (a, b) in trees:  # the tree stays quiet: what lights up is what the selected task waits on
            return "edge_tree"
        return "edge_hot" if selected in (a, b) else "edge"

    # forward edges
    for e, chain in chains:  # noqa: B007
        pts: list[tuple[int, int]] = []
        first, last = chain[0], chain[-1]
        sx = x_of(first) + wid(first)
        pts.append((sx, int(mid(first))))
        for a, b in zip(chain, chain[1:], strict=False):
            gap = layer[first] + chain.index(a)
            ln = lanes[gap][(a, b)]
            ya, yb = int(mid(a)), int(mid(b))
            if ln >= 0:
                lx = lane_x(gap, ln)
                pts += [(lx, ya), (lx, yb)]
            tx = x_of(b) if b not in boxes else x_of(b) - 1
            if b in boxes:
                pts.append((tx - 1, yb))
            else:  # through a dummy: across its layer
                pts += [(x_of(b), yb), (x_of(b) + width_of[layer_of(b, layer, None, rows)], yb)]
        st = hot(e.a, e.b)
        end = (x_of(last) - 1, int(mid(last)))
        if e.kind == "tree":  # no arrowhead: the line runs on to the box
            pts.append(end)
        line(_dedupe(pts), st)
        if e.kind != "tree":
            mark[end] = ("▶", st)
        if e.kind == "two":
            mark[(sx, int(mid(first)))] = ("◀", st)
    # back edges
    for e, k in back_runs:
        st = hot(e.a, e.b)
        ya, yb = int(mid(e.a)), int(mid(e.b))
        gl = layer[e.a]
        gx = lane_x(gl, back_lane[(k, gl)])
        gt = layer[e.b] - 1
        tx = lane_x(gt, back_lane[(k, gt)]) if gt >= 0 else back_lane[(k, gt)] + 1
        pts = [
            (x_of(e.a) + wid(e.a), ya),
            (gx, ya),
            (gx, lane_y[k]),
            (tx, lane_y[k]),
            (tx, yb),
            (x_of(e.b) - 2, yb),
        ]
        line(_dedupe(pts), st)
        mark[(x_of(e.b) - 1, yb)] = ("▶", st)
        if e.kind == "two":
            mark[(x_of(e.a) + wid(e.a), ya)] = ("◀", st)

    # compose cells
    cells: list[list[tuple[str, str]]] = []
    for yy in range(total_h + 1):
        cells.append(
            [
                (JOIN[mask[yy][x] & 15], style[yy][x] or "edge") if mask[yy][x] else (" ", "")
                for x in range(total_w + 2)
            ]
        )
    for row in cells:  # a loop is drawn dashed, so it is never mistaken for a dependency
        for x, (ch, st) in enumerate(row):
            if st == "edge_loop":
                row[x] = ({"─": "┄", "│": "┆"}.get(ch, ch), st)
    for (x, yy), (ch, st) in mark.items():
        cells[yy][x] = (ch, st)
    rects: dict[str, tuple[int, int, int, int]] = {}
    for n in nodes:
        b = boxes[n.id]
        bx, by = x_of(n.id), y[n.id]
        rects[n.id] = (bx, by, bx + b.w - 1, by + b.h - 1)
        look = styles.get(f"box:{n.state}", "light")  # its own shape, when the style table gives one
        look = "double" if n.id == selected else "heavy" if n.state == "running" else look
        tl, tr, bl, br, hz, vt = BOX[look]
        st = styles.get(n.state, "")
        sel = "node_sel" if n.id == selected else st or "node"
        glyph = styles.get(f"glyph:{n.state}", "")
        top = tl + hz + (glyph or hz) + hz * (b.w - 4) + tr
        bot = bl + hz * (b.w - 2) + br
        if n.badge:  # on the border the box has, whatever its width: a badge appearing moves no box
            tag = f" {n.badge} "[: b.w - 3]
            bot = bl + hz + tag + hz * (b.w - 3 - len(tag)) + br
        for dx, ch in enumerate(top):
            cells[by][bx + dx] = (ch, sel)
        for dy, text in enumerate(b.lines, 1):
            cells[by + dy][bx] = (vt, sel)
            for dx, ch in enumerate(spread(" " + text + " ")):
                cells[by + dy][bx + 1 + dx] = (
                    ch,
                    sel if n.id == selected else styles.get(f"label:{n.state}", ""),
                )
            cells[by + dy][bx + b.w - 1] = (vt, sel)
        for dx, ch in enumerate(bot):
            cells[by + b.h - 1][bx + dx] = (ch, sel)
    width = max((x1 for _, _, x1, _ in rects.values()), default=0) + 1
    width = max(
        [width, *(max((i for i, (c, _) in enumerate(row) if c != " "), default=-1) + 1 for row in cells)]
    )
    return Layout(
        width, total_h, [row[:width] for row in cells], rects, dict(layer), [(e.a, e.b) for e in back]
    )


def layer_of(
    n: str, layer: dict[str, int], chain: list[str] | None, rows: list[list[str]] | None = None
) -> int:
    """The layer of a node or a dummy; for a piece ``a -> b`` of ``chain``, the gap after ``a``."""
    if rows is not None:
        return next(li for li, row in enumerate(rows) if n in row)
    if chain is not None:
        return layer[chain[0]] + chain.index(n)
    return layer[n]


def _dedupe(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for p in points:
        if not out or out[-1] != p:
            out.append(p)
    return out
