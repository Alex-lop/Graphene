"""The graph screen: your plan as what must land before what, flowing into your goal at the right.

`flow_graph` turns the model into boxes and arrows: a box for each task and, last, one for your goal; an
arrow from a task to each task that waits on it, and from a task nothing waits on to the goal, so every
arrow says "must land before"; a lane for each sub-goal, a rule across the graph with its title and how
many of its tasks are done; a header over each column, which is a wave: the tasks whose longest chain of
needs is that long, so a column could all run at once; and the longest chain into the goal, drawn double.
`build_flow` lays them out (flowlayout.py) as wide as the terminal allows, shrinking the labels, then
showing the selected task's neighbourhood, and cuts the cells into lines whose segments know which task
they belong to: a click selects it. The goal is not a task, so a click or an arrow never selects its box.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from . import flowlayout as F
from .lines import Line, Seg, fit
from .look import FLOW_STYLES, who
from .model import Model, Task

PER_COLUMN, MOST_COLUMNS = 4, 4  # boxes a column holds before a flat list starts another; most columns
GOAL = " goal"  # the goal box's id: a plan's ids begin with a letter or a digit, so no task has it
STYLES = {**FLOW_STYLES, "label:goal": "bold", "box:goal": "square", "lane": "grey35",
          "lane_label": "grey70", "head": "grey62"}  # fmt: skip
EMPTY = "Nothing is planned yet: the graph shows your goal and the tasks under it."
LABELS = (28, 24, 18, 14, 12, 10)  # how wide a box's title may be, widest first: whole, when there is room


@dataclass
class Graph:
    nodes: list[F.GNode] = field(default_factory=list)  # the goal first, when there is one, then the tasks
    edges: list[F.GEdge] = field(default_factory=list)
    lanes: list[F.Lane] = field(default_factory=list)  # the sub-goals with tasks right under them
    heads: list[str] = field(default_factory=list)  # over each column: `wave 1 · 3 agents`, the goal's `goal`
    wave: dict[str, int] = field(default_factory=dict)  # each box's column


def count(tasks: list[Task]) -> str:
    """`2 of 3`, with a ✓ once every one is done."""
    done = sum(t.state == "done" for t in tasks)
    return f"{done} of {len(tasks)}" + " ✓" * (done == len(tasks))


def badge(t: Task) -> str:
    """The number its agent goes by; while its hold's forks run (`Task.forks`, the rows' field, read softly so
    the graph draws without it), `3 ×3`: three agents on it at once, until one is kept and the task is in
    review or done."""
    forks = getattr(t, "forks", None)
    return f"{t.agent} ×{len(forks)}" if t.agent and forks and t.state == "running" else t.agent


def head(k: int, tasks: list[Task]) -> str:
    """Over wave ``k``: its agents once every task in it has one (`agent 4`, `3 agents`), else its tasks;
    over the goal's column, which holds no task, `goal`."""
    if not tasks:
        return "goal"
    agents = [t.agent for t in tasks if t.agent]
    n = len(tasks)
    if len(agents) == n:
        what = who(agents[0]) if n == 1 else f"{n} agents"
    else:
        what = f"{n} task" + "s" * (n > 1)
    return f"wave {k + 1} · {what}"


def flow_graph(m: Model) -> Graph:
    """A box for each task, each in the lane of the sub-goal right over it, and one for your goal with how
    many tasks are done on its border; an arrow from each task to what waits on it, and to the goal from
    a task nothing waits on; a lane for each sub-goal with tasks, a parent's before its children's, a
    nested one named `parent › child`; a header for each wave. A plan with no goal has no goal box, and
    one with no tasks has no graph."""
    if not m.tasks:
        return Graph()
    g = Graph()
    tasks = list(m.tasks.values())
    goal = m.goal not in ("", "no goal yet")
    if goal:
        g.nodes.append(F.GNode(GOAL, m.goal, "goal", count(tasks)))
    under: dict[str, list[Task]] = {}  # a sub-goal -> the tasks right under it, in the plan's order
    seen: dict[str, int] = {}  # each sub-goal's first appearance, the top first: a lane before its children's
    for t in tasks:
        sid = t.above[-1][0] if t.above else ""
        under.setdefault(sid, []).append(t)
        for over, _ in t.above:
            seen.setdefault(over, len(seen))
        # a box carries its agent's number on its border in every state, as its row does: the state is its
        # colour and its glyph
        g.nodes.append(F.GNode(t.id, t.title, t.state, badge(t), lane=sid))
    for sid, ts in under.items():
        if sid:
            g.lanes.append(F.Lane(sid, " › ".join(name for _, name in ts[0].above), count(ts)))
    g.lanes.sort(key=lambda lane: tuple(seen[over] for over, _ in under[lane.id][0].above))
    g.edges = [F.GEdge(n, t.id) for t in tasks for n in t.needs if n in m.tasks]
    needed = {e.a for e in g.edges}
    g.edges += [F.GEdge(t.id, GOAL) for t in tasks if t.id not in needed] if goal else []
    g.edges += [F.GEdge(a, b, k) for a, b, k in m.extra_edges if a in m.tasks and b in m.tasks]
    g.wave = F.waves(g.nodes, g.edges)
    at = GOAL if goal else ""
    while at:  # the longest chain into the goal, back from it: at each step a need from the wave before
        before = (e for e in g.edges if e.b == at and e.kind != "loop" and g.wave[e.a] == g.wave[at] - 1)
        e = next(before, None)
        if e is None:
            break
        e.double, at = True, e.a
    if g.edges:
        g.heads = [head(k, [t for t in tasks if g.wave[t.id] == k]) for k in range(max(g.wave.values()) + 1)]
    return g


def build_flow(g: Graph, width: int, selected: str | None) -> tuple[list[Line], F.Layout, str]:
    """Lay the graph out as wide as it will go, then shrink labels, then show the neighbourhood. Nothing to
    draw is one line that says so."""
    if not g.nodes:
        return [Line([Seg(" " + EMPTY, "grey62")])], F.Layout(), ""
    note = ""
    lay = None
    ids = [n.id for n in g.nodes]
    wrap = max(1, min(MOST_COLUMNS, -(-len(ids) // PER_COLUMN))) if not g.edges else 1  # a flat list: a page
    for label_w in LABELS:
        for columns in range(wrap, 0, -1):
            lay = F.layout(g.nodes, g.edges, label_w=label_w, selected=selected, styles=STYLES,
                           columns=columns, lanes=g.lanes, heads=g.heads)  # fmt: skip
            if lay.width <= width:
                break
        if lay.width <= width:
            break
    focus = selected if selected in ids else GOAL if GOAL in ids else ids[0]  # a question: the goal, or top
    if lay is not None and lay.width > width:
        # the more around it the better, then the wider; last, the goal it flows into gives way to what is
        # around it
        for (hops, goal), label_w in product(((2, True), (1, True), (1, False)), LABELS):
            near, edges = F.neighbourhood(g.nodes, g.edges, focus, hops, keep=[GOAL] * goal)
            waves = sorted({g.wave[n.id] for n in near})  # the plan's waves with a box here: the columns
            lay = F.layout(near, edges, label_w=label_w, selected=selected, styles=STYLES,
                           lanes=[lane for lane in g.lanes if any(n.lane == lane.id for n in near)],
                           heads=[g.heads[w] for w in waves] if g.heads else [],
                           layers={n.id: waves.index(g.wave[n.id]) for n in near})  # fmt: skip
            lay.hidden = len(ids) - len(near)
            steps = f"{hops} step{'s' * (hops > 1)}"
            head, tail = f"showing {len(near)} of {len(ids)}: ", f" and what is within {steps}"
            room = max(30, width - 1 - len(head) - len(tail))  # a task's short title whole; a long goal cut
            note = head + fit(g.nodes[ids.index(focus)].label, room) + tail
            if lay.width <= width:
                break
    assert lay is not None
    lay.rects.pop(GOAL, None)  # not a task: nothing to select
    lines = []
    for y, row in enumerate(lay.cells):
        segs: list[Seg] = []
        for x, (ch, st) in enumerate(row[:width]):
            nid = lay.at(x, y)
            style = STYLES.get(st, st)
            if segs and segs[-1].style == style and segs[-1].action == (f"select:{nid}" if nid else ""):
                segs[-1].text += ch
            else:
                segs.append(Seg(ch, style, f"select:{nid}" if nid else ""))
        lines.append(Line(segs))
    return lines, lay, note
