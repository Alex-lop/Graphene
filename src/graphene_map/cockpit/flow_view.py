"""The graph screen: your goal, the sub-goals under it and the tasks under those, the agents on the boxes.

`flow_graph` turns the model into nodes and edges: the tree (goal, sub-goals, tasks) as quiet lines with no
arrowhead, and what each task waits on as arrows. `build_flow` lays them out (flowlayout.py) as wide as the
terminal allows, shrinking the labels, then showing the selected task's neighbourhood, and cuts the cells
into lines whose segments know which task they belong to: a click selects it. The goal and the sub-goals are
not tasks, so a click or an arrow selects none of them.
"""

from __future__ import annotations

from itertools import product

from . import flowlayout as F
from .lines import Line, Seg, fit
from .look import FLOW_STYLES
from .model import Model

PER_COLUMN, MOST_COLUMNS = 4, 4  # boxes a column holds before a flat list starts another; most columns
GOAL = " goal"  # the root box's id: a plan's ids begin with a letter or a digit, so no other box has it
TREE = ("goal", "sub-goal")  # the boxes that are not tasks
STYLES = {**FLOW_STYLES, "label:goal": "bold", "sub-goal": "grey50", "label:sub-goal": "grey70",
          "box:goal": "square", "box:sub-goal": "square", "edge_tree": "grey35"}  # fmt: skip
EMPTY = "Nothing is planned yet: the graph shows your goal and the tasks under it."
LABELS = (28, 24, 18, 14, 12, 10)  # how wide a box's title may be, widest first: whole, when there is room


def flow_graph(m: Model) -> tuple[list[F.GNode], list[F.GEdge]]:
    """Your goal at the root, each sub-goal once, each task under the sub-goals over it; a plan with no
    sub-goals is the goal over its tasks, one with no goal starts at what is under it, and one with no tasks
    has no graph."""
    nodes = {GOAL: F.GNode(GOAL, m.goal, "goal")} if m.tasks and m.goal not in ("", "no goal yet") else {}
    tree: dict[tuple[str, str], None] = {}  # parent, child: each edge once, in the plan's order
    for t in m.tasks.values():
        for sid, name in t.above:
            nodes.setdefault(sid, F.GNode(sid, name, "sub-goal"))
        # a running box carries its agent's number on its border, as its row does
        nodes[t.id] = F.GNode(t.id, t.title, t.state, t.agent if t.state == "running" else "")
        path = [GOAL] * (GOAL in nodes) + [sid for sid, _ in t.above] + [t.id]
        tree.update(dict.fromkeys(zip(path, path[1:], strict=False)))
    edges = [F.GEdge(a, b, "tree") for a, b in tree]
    edges += [F.GEdge(n, t.id) for t in m.tasks.values() for n in t.needs if n in m.tasks]
    edges += [F.GEdge(a, b, k) for a, b, k in m.extra_edges if a in m.tasks and b in m.tasks]
    return list(nodes.values()), edges


def drawn(edges: list[F.GEdge]) -> list[F.GEdge]:
    """The edges the graph draws: a task that waits on one beside it (under the same goal) hangs from it by
    that arrow, so the line from their goal to it is left out; long lines from a goal along a row of arrows
    would say nothing the arrows do not."""
    parent = {e.b: e.a for e in edges if e.kind == "tree"}
    hung = {e.b for e in edges if e.kind == "needs" and e.b in parent and parent.get(e.a) == parent[e.b]}
    return [e for e in edges if not (e.kind == "tree" and e.b in hung)]


def build_flow(
    nodes: list[F.GNode], edges: list[F.GEdge], width: int, selected: str | None, pan: int = 0
) -> tuple[list[Line], F.Layout, str]:
    """Lay the graph out as wide as it will go, then shrink labels, then show the neighbourhood. Nothing to
    draw is one line that says so."""
    if not nodes:
        return [Line([Seg(" " + EMPTY, "grey62")])], F.Layout(), ""
    note = ""
    lay = None
    wrap = max(1, min(MOST_COLUMNS, -(-len(nodes) // PER_COLUMN))) if not edges else 1  # a flat list: a page
    shown = drawn(edges)
    for label_w in LABELS:
        for columns in range(wrap, 0, -1):
            lay = F.layout(nodes, shown, label_w=label_w, selected=selected, styles=STYLES, columns=columns)
            if lay.width <= width:
                break
        if lay.width <= width:
            break
    ids = [n.id for n in nodes]
    focus = selected if selected in ids else GOAL if GOAL in ids else ids[0]  # a question: the goal, or top
    if lay is not None and lay.width > width:  # the goal's layer makes even five boxes too wide
        # a goal's steps are the lines drawn under it: by every task's own line, each would be one step away
        along = shown if nodes[ids.index(focus)].state in TREE else edges
        # the more around it the better, then the wider; last, the goals over it give way to what waits on it
        for (hops, up), label_w in product(((2, True), (1, True), (1, False)), LABELS):
            n2, e2 = F.neighbourhood(nodes, along, focus, hops, up)  # with the goals over it, while they fit
            lay = F.layout(n2, drawn(e2), label_w=label_w, selected=selected, styles=STYLES)
            lay.hidden = len(nodes) - len(n2)
            steps = f"{hops} step{'s' * (hops > 1)}"
            head, tail = f"showing {len(n2)} of {len(nodes)}: ", f" and what is within {steps}"
            room = max(30, width - 1 - len(head) - len(tail))  # a task's short title whole; a long goal cut
            note = head + fit(nodes[ids.index(focus)].label, room) + tail
            if lay.width <= width:
                break
    assert lay is not None
    for n in nodes:  # not a task: nothing to select
        if n.state in TREE:
            lay.rects.pop(n.id, None)
    lines = []
    for y, row in enumerate(lay.cells):
        segs: list[Seg] = []
        for x, (ch, st) in enumerate(row[pan : pan + width]):
            nid = lay.at(x + pan, y)
            style = STYLES.get(st, st)
            if segs and segs[-1].style == style and segs[-1].action == (f"select:{nid}" if nid else ""):
                segs[-1].text += ch
            else:
                segs.append(Seg(ch, style, f"select:{nid}" if nid else ""))
        lines.append(Line(segs))
    return lines, lay, note
