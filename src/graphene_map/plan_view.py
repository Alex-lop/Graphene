"""The plan as the page draws it: nodes in topological columns, one lane per owner, every number here.

The columns are the dependency graph's own depth, so a node's column is decided by what it waits on
and by nothing else: adding a node never moves a node whose depth did not change. Lanes are owners,
the agents' lane first and then each person, because whose node it is is the first thing a person
looks for. Rows inside a lane are stacked so that no two boxes touch. The page adds pan and scroll
and decides no position of its own, exactly as it already does for the map.

The plan is a tree, so every node also carries where it sits in it: its ``parent``, its ``depth``
below the root, whether it is a ``sub_goal`` (it has children: nobody takes it, and its progress is
the leaves beneath it), and ``why`` — the path from the plan's ``goal`` down to it, in the person's
words, the same lines ``graphene node start`` prints to its executor. ``nodes`` come out parents
first, so the page indents by ``depth`` and decides no order of its own. The columns, the lanes and
every position are unchanged: hierarchy is meaning, and the edges here are still order.
TODO: ``why`` asks the store for the whole plan once per node; one walk would do, and the page polls
every two seconds. Not worth a second copy of ``plan.trail`` until a plan is large enough to feel it.

``holes`` are the sentences printed next to the controls they belong to. A control here either
changes what an agent can do or says where the mechanism behind it stops; none of them is decoration.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import plan as P

NODE_W = 200
NODE_H = 76
COL_GAP = 40  # between a node's right edge and the next column's left edge
ROW_GAP = 12
LANE_PAD = 26  # room above a lane's first row for the lane's name
LANE_GAP = 20
LOG_TAIL = 12  # log entries kept per node, newest last; the page polls, so every entry is paid for every 2 s
SAID_CAP = 400  # a check's output is up to 2000 characters; the inspector shows its head
STATES = (P.PROPOSED, P.OPEN, P.RUNNING, P.REVIEW, P.DONE)  # a dropped node is not drawn, as in the terminal

# Every one of these is a mechanism that stops somewhere, printed where the control is. They are
# the same holes the hooks' docstring and the README name, in the words a person reads.
HOLES = {
    "scope": (
        "A hook refuses a write outside this scope before it happens, and refuses a shell command "
        "whose writes Claude Code reports. A shell write no parser reads is caught later: `graphene "
        "node done` asks git what changed and refuses while anything outside the scope differs."
    ),
    "check": (
        "Graphene runs this command itself, in the checkout the node ran in, and reads its exit "
        "code; it is not a sentence in the executor's summary. A hook that crashes or times out "
        "lets a call through, and this check still decides."
    ),
    "stop": (
        "While a node is running, the hook refuses the session's stop. Claude Code lets a session "
        "stop anyway after about eight refused stops in a row; the node then stays open, and you "
        "see it here as running with nobody finishing it."
    ),
    "person": (
        "Accepting, signing off, reopening and editing are the person's, and an agent's shell is "
        "refused: the hook denies a command carrying GRAPHENE_AS. An agent that forges it where no "
        "hook runs passes for a person."
    ),
}


@dataclass(slots=True)
class ViewNode:
    id: str
    title: str
    goal: str
    scope: list[str]
    check: str | None
    signoff: bool
    needs: list[str]
    owner: str
    parent: str | None  # the node this one helps achieve; None is directly under the plan's goal
    aside: bool  # made from what the person typed into a session
    sub_goal: bool  # it has children: nobody takes it, and it is done when they are
    depth: int  # how far below the root it sits; the page indents by it and computes no order
    why: list[str]  # the path from the goal down to this node, root first: plan.trail
    leaves_done: int  # a sub-goal's own progress, in leaves, exactly as the terminal counts it
    leaves_total: int
    state: str
    display_state: str  # waiting | ready | sub-goal | the state itself
    rev: int
    executor: str | None
    started_at: str | None
    finished_at: str | None
    waits: list[str]
    log: list[dict]
    lane: str
    column: int
    row: int
    x: float
    y: float
    width: int = NODE_W
    height: int = NODE_H


@dataclass(slots=True)
class ViewLane:
    id: str  # the owner
    label: str
    person: bool
    y: float
    height: float
    nodes: int


@dataclass(slots=True)
class ViewEdge:
    id: str
    source: str  # the node that must finish
    target: str  # the node that waits on it
    points: list[list[float]]


@dataclass(slots=True)
class PlanView:
    version: int = 1
    repo: str = ""  # the checkout this plan belongs to, by name: a plan exists before any run does
    goal: str = ""  # the root of the tree: why any of this is being done, in the person's words
    person: str = ""
    paused: bool = False
    width: float = 0.0
    height: float = 0.0
    nodes: list[ViewNode] = field(default_factory=list)
    lanes: list[ViewLane] = field(default_factory=list)
    edges: list[ViewEdge] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    waiting_on_person: list[dict] = field(default_factory=list)
    loose: list[str] = field(default_factory=list)  # changed while no node owned it
    all_done: bool = False  # every node done: still in force until the person archives or pauses
    forecast: dict = field(default_factory=dict)
    holes: dict = field(default_factory=lambda: dict(HOLES))


def depths(nodes: list[P.Node]) -> dict[str, int]:
    """The longest path to each node through what it waits on. ``validate`` refuses a cycle, but a
    plan is read here as it stands, so a node already on the trail stops the walk instead of looping."""
    by_id = {n.id: n for n in nodes}
    out: dict[str, int] = {}

    def depth(node_id: str, trail: frozenset[str]) -> int:
        if node_id in out:
            return out[node_id]
        node = by_id[node_id]
        found = [
            depth(need, trail | {node_id}) + 1 for need in node.needs if need in by_id and need not in trail
        ]
        out[node_id] = max(found, default=0)
        return out[node_id]

    for n in nodes:
        depth(n.id, frozenset())
    return out


def outline(nodes: list[P.Node]) -> list[tuple[P.Node, int]]:
    """The tree as an outline: every node after its parent, with how far below the root it sits.
    Siblings keep the order they were added, as they do in the terminal. A node whose parent is not
    here (dropped, archived) hangs directly under the goal, so nothing falls out of the view."""
    under = P.kids(nodes, drawn=True)
    here = {n.id for n in nodes}
    roots = [n for n in nodes if n.parent not in here]
    out: list[tuple[P.Node, int]] = []
    stack = [(n, 0) for n in reversed(roots)]
    while stack:
        node, depth = stack.pop()
        out.append((node, depth))
        stack += [(kid, depth + 1) for kid in reversed(under.get(node.id, []))]
    return out


def rolls_up(node: P.Node, nodes: list[P.Node], under: dict) -> tuple[int, int]:
    """A sub-goal's progress in the leaves beneath it, done and in all, the terminal's own count."""
    beneath = [n for n in P.below(node.id, nodes) if not under.get(n.id)]
    return sum(1 for n in beneath if n.state == P.DONE), len(beneath)


def display_state(node: P.Node, by_id: dict[str, P.Node], under: dict | None = None) -> str:
    """What the page labels the node: an open node that cannot start yet is waiting, not ready, and
    one with children is a sub-goal, which nobody takes and which is done when its children are."""
    if under and under.get(node.id):
        return "sub-goal" if node.state == P.OPEN else node.state
    if node.state != P.OPEN:
        return node.state
    return "waiting" if P.unmet(node, by_id) else "ready"


def came_back(store, node: P.Node, export: bool = False) -> list[str]:
    """The words a node came back with: a person's when they sent it back, its executor's when it
    was handed back. They are the plan's, not a log's, so an exported page carries them too, to
    their first line (``_cut``)."""
    if node.state != P.OPEN:
        return []
    last = (store.node_log(node.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
    if last["kind"] == "reopened":
        return [f"sent back: {_cut(last['detail'].get('note', ''), export)}"]
    if last["kind"] == "released":
        return [f"handed back: {_cut(last['detail'].get('why', ''), export)}"]
    return []


def waits(node: P.Node, by_id: dict[str, P.Node], under: dict | None = None) -> list[str]:
    """Why this node is not moving, in plain sentences: what it needs from a person on its own
    account first, then what it waits on in the plan, then which person the rest of it waits for."""
    reasons: list[str] = []
    if node.state == P.PROPOSED:
        reasons.append("waits for a person to accept it into the plan")
    elif node.state == P.REVIEW:
        reasons.append("waits for a person's sign-off")
    for blocker in P.unmet(node, by_id):
        reasons.append(
            f"waits on {blocker.id} ({blocker.title}), which is {display_state(blocker, by_id, under)}"
        )
    # waits_on_person walks the whole chain above this node; its line about the node itself says
    # nothing the state and the lane do not already say, so only the ones upstream are kept.
    reasons += [r for r in P.waits_on_person(node, by_id) if not r.startswith(f"{node.id} ")]
    return list(dict.fromkeys(reasons))


def _cut(said: str, export: bool) -> str:
    """What a file that leaves the machine keeps of a sentence: its first line. The reason `run`
    hands a leaf back with quotes its last refusal, and a failed check's output is under it."""
    return said.split("\n")[0] if export else said


def _said(detail: dict, export: bool = False) -> str:
    """The one thing a log entry has to say, in the order the terminal prints it. In an export a
    check says its command and not its output."""
    changed = detail.get("changed")  # an edit's field changes (a dict), or an ending's paths (a list)
    fields = changed.items() if isinstance(changed, dict) else ()
    paths = changed if isinstance(changed, list) else []
    said = (
        detail.get("why")
        or detail.get("note")
        or detail.get("override")
        or ", ".join(detail.get("outside") or detail.get("paths") or [])
        or detail.get("path")
        or "; ".join(f"{k}: {a!r} → {b!r}" for k, (a, b) in fields)
        or (f"changed: {', '.join(paths)}" if paths else "")
        or (None if export else detail.get("output"))
        or detail.get("command")
        or ""
    )
    return _cut(said, export)[:SAID_CAP]


def node_log(store, node_id: str, export: bool = False) -> list[dict]:
    """The page polls, so it is sent the tail; an export is read once and carries the whole log,
    whose first entries say who held the node."""
    entries = store.node_log(node_id)
    if not export:
        entries = entries[-LOG_TAIL:]
    return [
        {"at": e["timestamp"], "kind": e["kind"], "actor": e["actor"] or "",
         "said": _said(e["detail"], export)}
        for e in entries
    ]  # fmt: skip


def waiting_on_person(nodes: list[P.Node], person: str) -> list[dict]:
    """What is on the person right now: proposals to accept, sign-offs due, their own ready nodes."""
    out = []
    for n in P.order(nodes):
        if n.state == P.PROPOSED:
            out.append({"id": n.id, "title": n.title, "why": f"accept it ({n.proposed_by} proposed it)"})
        elif n.state == P.REVIEW:
            out.append({"id": n.id, "title": n.title, "why": "sign it off"})
    ready = {n.id for n in P.ready(nodes)}
    for n in P.order(nodes):
        if n.id in ready and n.owner == person:  # another person's node waits on them, not on you
            out.append({"id": n.id, "title": n.title, "why": "yours to do"})
    return out


def build_plan_view(store, export: bool = False, checkout: Path | None = None) -> dict:
    """Everything the plan screen draws, with every x, y and point computed here. ``export`` is for
    a file that leaves the machine: each node's log goes whole, as its record, without what a check
    printed, since the export promises no tool output. ``checkout`` is where to ask git what changed
    between nodes."""
    live = [n for n in P.nodes(store) if n.state not in P.GONE]
    by_id = {n.id: n for n in live}
    person = P.person_name()
    # the store lives at <repo>/.graphene/graphene.db, and the page names the repo even when no
    # session has been recorded in it yet, which is exactly when the graph cannot name it
    view = PlanView(
        repo=store.path.parent.parent.name, goal=P.goal(store), person=person, paused=P.paused(store)
    )
    view.counts = {state: sum(1 for n in live if n.state == state) for state in STATES}
    view.waiting_on_person = waiting_on_person(live, person)
    view.all_done = bool(live) and all(n.state == P.DONE for n in live)
    if checkout is not None and not any(n.state == P.RUNNING for n in live):
        try:
            view.loose = P.unowned(store, checkout)
        except (P.Refused, OSError, subprocess.TimeoutExpired):
            view.loose = []  # not a checkout git can read: nothing to compare
    runs, waiting = P.forecast(live)
    view.forecast = {
        "runs": [n.id for n in runs],
        "waits": [{"id": n.id, "why": why} for n, why in waiting],
    }
    if not live:
        return asdict(view)

    column = depths(live)
    under = P.kids(live, drawn=True)
    tree = outline(live)  # the order the page prints, and the depth it indents by
    depth = {n.id: d for n, d in tree}
    owners = [P.AGENT] + sorted({n.owner for n in live if n.owner != P.AGENT})
    ordered = P.order(live)  # a node after everything it waits on: rows read down the same way
    y = 0.0
    taken: dict[tuple[str, int], set[int]] = {}  # (lane, column) -> the rows already used
    placed: dict[str, ViewNode] = {}
    for owner in owners:
        mine = [n for n in ordered if n.owner == owner]
        if not mine:
            continue
        rows = 0
        for n in mine:
            col = column[n.id]
            used = taken.setdefault((owner, col), set())
            row = next(r for r in range(len(mine) + 1) if r not in used)
            used.add(row)
            rows = max(rows, row + 1)
            done, of = rolls_up(n, live, under) if under.get(n.id) else (0, 0)
            placed[n.id] = ViewNode(
                id=n.id,
                title=n.title,
                goal=n.goal,
                scope=list(n.scope),
                check=n.check,
                signoff=n.signoff,
                needs=list(n.needs),
                owner=n.owner,
                parent=n.parent,
                aside=n.aside,
                sub_goal=bool(under.get(n.id)),
                depth=depth[n.id],
                why=P.trail(store, n),
                leaves_done=done,
                leaves_total=of,
                state=n.state,
                display_state=display_state(n, by_id, under),
                rev=n.rev,
                executor=n.executor,
                started_at=n.started_at,
                finished_at=n.finished_at,
                waits=came_back(store, n, export) + waits(n, by_id, under),
                log=node_log(store, n.id, export),
                lane=owner,
                column=col,
                row=row,
                x=float(col * (NODE_W + COL_GAP)),
                y=y + LANE_PAD + row * (NODE_H + ROW_GAP),
            )
        height = LANE_PAD + rows * (NODE_H + ROW_GAP) - ROW_GAP
        view.lanes.append(
            ViewLane(
                id=owner,
                label="agents" if owner == P.AGENT else owner,
                person=owner != P.AGENT,
                y=y,
                height=height,
                nodes=len(mine),
            )
        )
        y += height + LANE_GAP

    view.nodes = [placed[n.id] for n, _ in tree]  # parents before their children: the page indents
    for n in ordered:
        for need in n.needs:
            source, target = placed.get(need), placed[n.id]
            if source is None:
                continue  # a dropped node it still names: `validate` refuses it, the view skips it
            view.edges.append(_edge(source, target))
    view.width = max(n.x + NODE_W for n in view.nodes)
    view.height = y - LANE_GAP
    return asdict(view)


def _edge(source: ViewNode, target: ViewNode) -> ViewEdge:
    """Out of the source's right edge, into the target's left edge, turning halfway between them."""
    sx, sy = source.x + NODE_W, source.y + NODE_H / 2
    tx, ty = target.x, target.y + NODE_H / 2
    middle = max(sx, (sx + tx) / 2)
    points = [[sx, sy], [tx, ty]] if sy == ty else [[sx, sy], [middle, sy], [middle, ty], [tx, ty]]
    return ViewEdge(f"{source.id}>{target.id}", source.id, target.id, points)
