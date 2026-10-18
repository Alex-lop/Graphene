"""The flow screen: the plan as boxes and arrows, the agents on the boxes.

`flow_graph` turns the model's tasks and what they wait on into nodes and edges; `build_flow` lays them out
(flowlayout.py) as wide as the terminal allows, shrinking the labels, then showing the selected task's
neighbourhood, and cuts the cells into lines whose segments know which task they belong to (a click selects).
"""

from __future__ import annotations

from . import flowlayout as F
from .lines import Line, Seg
from .look import FLOW_STYLES
from .model import Model

PER_COLUMN, MOST_COLUMNS = 4, 4  # boxes a column holds before a flat list starts another; most columns


def flow_graph(m: Model) -> tuple[list[F.GNode], list[F.GEdge]]:
    nodes = [
        F.GNode(t.id, t.title, t.state, t.agent if t.state == "running" else "") for t in m.tasks.values()
    ]
    edges = [F.GEdge(n, t.id) for t in m.tasks.values() for n in t.needs if n in m.tasks]
    edges += [F.GEdge(a, b, k) for a, b, k in m.extra_edges if a in m.tasks and b in m.tasks]
    return nodes, edges


def build_flow(
    nodes: list[F.GNode], edges: list[F.GEdge], width: int, selected: str | None, pan: int = 0
) -> tuple[list[Line], F.Layout, str]:
    """Lay the graph out as wide as it will go, then shrink labels, then show the neighbourhood."""
    note = ""
    lay = None
    wrap = max(1, min(MOST_COLUMNS, -(-len(nodes) // PER_COLUMN))) if not edges else 1  # a flat list: a page
    for label_w in (18, 14, 12, 10):
        for columns in range(wrap, 0, -1):
            lay = F.layout(
                nodes, edges, label_w=label_w, selected=selected, styles=FLOW_STYLES, columns=columns
            )
            if lay.width <= width:
                break
        if lay.width <= width:
            break
    if lay is not None and lay.width > width and selected and len(nodes) > 5:
        for hops in (2, 1):
            n2, e2 = F.neighbourhood(nodes, edges, selected, hops)
            lay = F.layout(n2, e2, label_w=12, selected=selected, styles=FLOW_STYLES)
            lay.hidden = len(nodes) - len(n2)
            steps = f"{hops} step{'s' * (hops > 1)}"
            note = f"showing {len(n2)} of {len(nodes)}: {selected} and what is within {steps}"
            if lay.width <= width:
                break
    assert lay is not None
    lines = []
    for y, row in enumerate(lay.cells):
        segs: list[Seg] = []
        for x, (ch, st) in enumerate(row[pan : pan + width]):
            nid = lay.at(x + pan, y)
            style = FLOW_STYLES.get(st, st) if st in FLOW_STYLES else st
            if segs and segs[-1].style == style and segs[-1].action == (f"select:{nid}" if nid else ""):
                segs[-1].text += ch
            else:
                segs.append(Seg(ch, style, f"select:{nid}" if nid else ""))
        lines.append(Line(segs))
    return lines, lay, note
