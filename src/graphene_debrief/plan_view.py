"""The plan as the page draws it: nodes in topological columns, one lane per owner, every number here.

The columns are the dependency graph's own depth, so a node's column is decided by what it waits on
and by nothing else: adding a node never moves a node whose depth did not change. Lanes are owners,
the agents' lane first and then each person, because whose node it is is the first thing a person
looks for. Rows inside a lane are stacked so that no two boxes touch. The page adds pan and scroll
and decides no position of its own, exactly as it already does for the map.

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
    state: str
    display_state: str  # waiting | ready | the state itself
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


def display_state(node: P.Node, by_id: dict[str, P.Node]) -> str:
    """What the page labels the node: an open node that cannot start yet is waiting, not ready."""
    if node.state != P.OPEN:
        return node.state
    return "waiting" if P.unmet(node, by_id) else "ready"


def waits(node: P.Node, by_id: dict[str, P.Node]) -> list[str]:
    """Why this node is not moving, in plain sentences: what it needs from a person on its own
    account first, then what it waits on in the plan, then which person the rest of it waits for."""
    reasons: list[str] = []
    if node.state == P.PROPOSED:
        reasons.append("waits for a person to accept it into the plan")
    elif node.state == P.REVIEW:
        reasons.append("waits for a person's sign-off")
    for blocker in P.unmet(node, by_id):
        reasons.append(f"waits on {blocker.id} ({blocker.title}), which is {display_state(blocker, by_id)}")
    # waits_on_person walks the whole chain above this node; its line about the node itself says
    # nothing the state and the lane do not already say, so only the ones upstream are kept.
    reasons += [r for r in P.waits_on_person(node, by_id) if not r.startswith(f"{node.id} ")]
    return list(dict.fromkeys(reasons))


def _said(detail: dict) -> str:
    """The one thing a log entry has to say, in the order the terminal prints it."""
    said = (
        detail.get("why")
        or detail.get("note")
        or detail.get("override")
        or ", ".join(detail.get("outside") or detail.get("paths") or [])
        or detail.get("path")
        or "; ".join(f"{k}: {a!r} → {b!r}" for k, (a, b) in (detail.get("changed") or {}).items())
        or detail.get("output")
        or detail.get("command")
        or ""
    )
    return said[:SAID_CAP]


def node_log(store, node_id: str) -> list[dict]:
    entries = store.node_log(node_id)[-LOG_TAIL:]
    return [
        {"at": e["timestamp"], "kind": e["kind"], "actor": e["actor"] or "", "said": _said(e["detail"])}
        for e in entries
    ]


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


def build_plan_view(store, logs: bool = True, checkout: Path | None = None) -> dict:
    """Everything the plan screen draws, with every x, y and point computed here. ``logs`` is False
    for a file that leaves the machine: a node's log can hold the output of its check, and the
    export promises no tool output. ``checkout`` is where to ask git what changed between nodes."""
    live = [n for n in P.nodes(store) if n.state not in P.GONE]
    by_id = {n.id: n for n in live}
    person = P.person_name()
    # the store lives at <repo>/.graphene/graphene.db, and the page names the repo even when no
    # session has been recorded in it yet, which is exactly when the graph cannot name it
    view = PlanView(repo=store.path.parent.parent.name, person=person, paused=P.paused(store))
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
            placed[n.id] = ViewNode(
                id=n.id,
                title=n.title,
                goal=n.goal,
                scope=list(n.scope),
                check=n.check,
                signoff=n.signoff,
                needs=list(n.needs),
                owner=n.owner,
                state=n.state,
                display_state=display_state(n, by_id),
                rev=n.rev,
                executor=n.executor,
                started_at=n.started_at,
                finished_at=n.finished_at,
                waits=waits(n, by_id),
                log=node_log(store, n.id) if logs else [],
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

    view.nodes = [placed[n.id] for n in ordered]
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
