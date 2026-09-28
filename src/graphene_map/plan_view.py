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

The same nodes are laid out a second time as the tree a person draws (``tree_x``/``tree_y``, the
goal's box at ``tree_goal``, the links in ``tree_links``): the goal at the top, each node under the
one it helps achieve, each leaf in its own slot left to right in outline order and each parent
centred over its first and last child. ``critical`` is the longest chain of leaves not yet done
through what each waits on, and ``at_once`` the leaves that can start now; both are the plan's, read
the same way whichever view the page shows and in the terminal's graph (`critical_path`, `at_once`).
TODO: ``why`` asks the store for the whole plan once per node; one walk would do, and the page polls
every two seconds. Not worth a second copy of ``plan.trail`` until a plan is large enough to feel it.

``holes`` are the sentences printed next to the controls they belong to. A control here either
changes what an agent can do or says where the mechanism behind it stops; none of them is decoration.
"""

from __future__ import annotations

import math
import subprocess
import unicodedata
from dataclasses import asdict, dataclass, field
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from . import plan as P
from .node_record import forks

NODE_W = 200
NODE_H = 76
COL_GAP = 40  # between a node's right edge and the next column's left edge
ROW_GAP = 12
LANE_PAD = 26  # room above a lane's first row for the lane's name
LANE_GAP = 20
TREE_GAP = 24  # between two boxes side by side in the tree
TREE_MIN = 140  # the narrowest box in the tree: its state word and a sign-off tag side by side
CHAR, SMALL = 6.4, 5.9  # the page's pixels a column of a title (13 px) and of the id line (11 px) take
TREE_DROP = 48  # between a parent's bottom edge and its children's top edge
LOG_TAIL = 12  # log entries kept per node, newest last; the page polls, so every entry is paid for every 2 s
SAID_CAP = 400  # a check's output is up to 2000 characters; the inspector shows its head
STATES = (P.PROPOSED, P.OPEN, P.RUNNING, P.REVIEW, P.DONE)  # a dropped node is not drawn, as in the terminal
# what the page says of a fork; never its image, which is the sandbox's own id on the provider's service
FORK_KEYS = ("fork", "of", "model", "state", "why", "checkpoint", "ops", "seconds")

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
    forks: list[dict]  # its last attempt's forks, as executor.fork_and_pick logged them (FORK_KEYS)
    lane: str
    column: int
    row: int
    x: float
    y: float
    tree_x: float = 0.0  # where it sits in the top-down tree
    tree_y: float = 0.0
    tree_w: float = NODE_W  # its box's width in the tree: as its title and id line need (tree_w)
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
    critical: bool = False  # on the longest chain of leaves not yet done: drawn heavier


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
    critical: list[str] = field(default_factory=list)  # the longest chain of leaves not yet done, first first
    at_once: list[str] = field(default_factory=list)  # the leaves that can start now, proposals too
    tree_width: float = 0.0
    tree_height: float = 0.0
    tree_goal: list[float] = field(default_factory=lambda: [0.0, 0.0])  # the goal's box, at the top
    tree_links: list[ViewEdge] = field(default_factory=list)  # parent to child; "" is the goal
    view: str = "auto"  # the repository's `view` setting, the one `graphene watch` opens in; unset: auto


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


def cols(text: str) -> int:
    """The columns a text takes, an East Asian wide or fullwidth character (and an emoji) counting two,
    as the page's `clip` counts them (ui/src/model.ts)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def tree_w(node: P.Node) -> float:
    """A box in the tree, as wide as its title and its id line need, from TREE_MIN to NODE_W: a plan
    of short leaves fits a window a fixed width would not. The revision is left out, so an edit never
    moves a box; the page cuts what does not fit."""
    who = f"{node.id} · {'any agent' if node.owner == P.AGENT else node.owner}"
    return float(min(NODE_W, max(TREE_MIN, math.ceil(24 + max(CHAR * cols(node.title), SMALL * cols(who))))))


def tidy(tree: list[tuple[P.Node, int]], under: dict, wide: dict[str, float]) -> tuple[dict, float]:
    """The top-down tree: the leaves side by side left to right in outline order, each in a slot as
    wide as its box, and each parent centred over its first and last child. Each subtree is laid out
    on its own and then placed beside the one before, so no two boxes touch at any depth, and a parent
    wider than what is under it widens its subtree instead. The goal (NODE_W wide) is the top row; a
    node's row is its depth plus one. Returns each node's (x, y) and the goal's x."""
    rel: dict[str, dict[str, float]] = {}  # each subtree's xs, from its own left edge
    span: dict[str, float] = {}

    def beside(ids: list[str]) -> tuple[dict[str, float], float]:
        out, left = {}, 0.0
        for i in ids:
            out |= {k: x + left for k, x in rel[i].items()}
            left += span[i] + TREE_GAP
        return out, left - TREE_GAP

    def over(xs: dict[str, float], ids: list[str], width: float) -> float:
        return (xs[ids[0]] + wide[ids[0]] / 2 + xs[ids[-1]] + wide[ids[-1]] / 2) / 2 - width / 2

    for n, _ in reversed(tree):  # children before their parents
        kids = [k.id for k in under.get(n.id, [])]
        if not kids:
            rel[n.id], span[n.id] = {n.id: 0.0}, wide[n.id]
            continue
        xs, width = beside(kids)
        x = over(xs, kids, wide[n.id])
        shift = max(0.0, -x)
        rel[n.id] = {k: v + shift for k, v in xs.items()} | {n.id: x + shift}
        span[n.id] = max(width + shift, x + shift + wide[n.id])
    roots = [n.id for n, depth in tree if depth == 0]
    xs, _ = beside(roots)
    goal = over(xs, roots, NODE_W)
    shift = max(0.0, -goal)
    return {n.id: (xs[n.id] + shift, (depth + 1) * (NODE_H + TREE_DROP)) for n, depth in tree}, goal + shift


Box = tuple[float, float, float]  # a box in the tree: x, y, width


def _link(source: str, at: Box, target: str, to: Box) -> ViewEdge:
    """Down from the parent's bottom edge to the child's top edge, turning halfway between them; each
    box is (x, y, width)."""
    sx, sy = at[0] + at[2] / 2, at[1] + NODE_H
    tx, ty = to[0] + to[2] / 2, to[1]
    middle = sy + TREE_DROP / 2
    points = [[sx, sy], [tx, ty]] if sx == tx else [[sx, sy], [sx, middle], [tx, middle], [tx, ty]]
    return ViewEdge(f"{source}>{target}", source, target, points)


def leaf_needs(nodes: list[P.Node]) -> tuple[list[P.Node], dict[str, list[str]]]:
    """The leaves (`plan.leaves`: a proposed child under an accepted leaf does not make it a sub-goal)
    in `plan.order`, and for each the leaves it waits on: what it and everything above it needs, where
    a need on a sub-goal is a wait on each leaf beneath it (decision 14)."""
    by_id = {n.id: n for n in nodes}
    leaves = P.order(P.leaves(nodes))
    ids = {n.id for n in leaves}
    needs = {}
    for leaf in leaves:
        got = []
        for need in P.all_needs(leaf, by_id):
            got += [need] if need in ids else [n.id for n in P.below(need, nodes) if n.id in ids]
        needs[leaf.id] = [i for i in dict.fromkeys(got) if i != leaf.id]
    return leaves, needs


def critical_path(nodes: list[P.Node]) -> list[str]:
    """The critical path, the page's and the terminal's alike: the longest chain through what each
    waits on of leaves not done, counted in leaves, first first. Ties go to `plan.order`'s first. A
    chain of one is no path: when no leaf not done needs another, there is none."""
    leaves, needs = leaf_needs(nodes)
    todo = {n.id for n in leaves if n.state != P.DONE}
    rank = {n.id: k for k, n in enumerate(leaves)}
    try:  # what a leaf waits on comes first; `validate` refuses a cycle, and one read as it is has no path
        ahead = list(TopologicalSorter({i: needs[i] for i in todo}).static_order())
    except CycleError:
        return []
    best: dict[str, list[str]] = {}  # the longest chain ending at each leaf
    for i in (i for i in ahead if i in todo):
        before = sorted((d for d in needs[i] if d in todo), key=rank.__getitem__)
        best[i] = max((best[d] for d in before), key=len, default=[]) + [i]
    path = max((best[i] for i in sorted(best, key=rank.__getitem__)), key=len, default=[])
    return path if len(path) > 1 else []


def at_once(nodes: list[P.Node]) -> list[str]:
    """What can start at once, the page's and the terminal's alike: the leaves not done, not running,
    not in review and not the person's own, with a scope to work in and nothing left to wait on,
    proposed or accepted alike (the shaping comes before acceptance), in `plan.order`."""
    by_id = {n.id: n for n in nodes}
    return [
        n.id
        for n in leaf_needs(nodes)[0]
        if n.state in (P.PROPOSED, P.OPEN) and n.owner == P.AGENT and n.scope and not P.unmet(n, by_id)
    ]


def _critical_edges(path: list[str], live: list[P.Node]) -> set[str]:
    """The edges the page draws heavier for the path: each carries the need one leaf on it has on the
    one before, from the leaf itself or from what it sits under, on that leaf or on what it sits under."""
    by_id = {n.id: n for n in live}
    out = set()
    for before, leaf in zip(path, path[1:], strict=False):
        for carrier in (by_id[leaf], *P.above(by_id[leaf], by_id)):
            beneath = {i: {i} | {n.id for n in P.below(i, live)} for i in carrier.needs}
            need = next((i for i in carrier.needs if before in beneath[i]), None)
            if need:
                out.add(f"{need}>{carrier.id}")
                break
    return out


def rolls_up(node: P.Node, nodes: list[P.Node], under: dict) -> tuple[int, int]:
    """A sub-goal's progress in the leaves beneath it, done and in all, the terminal's own count."""
    beneath = [n for n in P.below(node.id, nodes) if not under.get(n.id)]
    return sum(1 for n in beneath if n.state == P.DONE), len(beneath)


def display_state(
    node: P.Node, by_id: dict[str, P.Node], under: dict | None = None, back: set[str] = frozenset()
) -> str:
    """What the page labels the node: an open node that cannot start yet is waiting, not ready, one
    with children is a sub-goal, which nobody takes and which is done when its children are, and a
    leaf in ``back`` (`plan.came_back`) came back, which waits on the person, as the terminal says."""
    if under and under.get(node.id):
        return "sub-goal" if node.state == P.OPEN else node.state
    if node.state != P.OPEN:
        return node.state
    if node.id in back:
        return "came back"
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


def waits(
    node: P.Node, by_id: dict[str, P.Node], under: dict | None = None, back: set[str] = frozenset()
) -> list[str]:
    """Why this node is not moving, in plain sentences: what it needs from a person on its own
    account first, then what it waits on in the plan, then which person the rest of it waits for."""
    reasons: list[str] = []
    if node.state == P.PROPOSED:
        reasons.append("waits for a person to accept it into the plan")
    elif node.state == P.REVIEW:
        reasons.append("waits for a person's sign-off")
    for blocker in P.unmet(node, by_id):
        shown = display_state(blocker, by_id, under, back)
        state = "came back" if shown == "came back" else f"is {shown}"
        reasons.append(f"waits on {blocker.id} ({blocker.title}), which {state}")
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
    why = detail.get("why")  # a sentence, or the lines git refused a leaf's merge with (`unlanded`)
    said = (
        (", ".join(why) if isinstance(why, list) else why)
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


def _forks(store, node: P.Node, export: bool) -> list[dict]:
    """The tree of sandboxes under a leaf: its last attempt's forks, each its number, model, state and
    why (in an export, its first line), and its sandbox's checkpoint, operations and seconds."""
    return [{k: f[k] for k in FORK_KEYS if k in f} | {"why": _cut(f.get("why", ""), export)[:SAID_CAP]}
            for f in forks(store.node_log(node.id, ("started", "model", "fork")), node.state)]  # fmt: skip


def waiting_on_person(nodes: list[P.Node], person: str, back: set[str] = frozenset()) -> list[dict]:
    """What is on the person right now: proposals to accept, sign-offs due, the leaves that came back
    (``back``), their own ready nodes."""
    out = []
    for n in P.order(nodes):
        if n.state == P.PROPOSED:
            out.append({"id": n.id, "title": n.title, "why": f"accept it ({n.proposed_by} proposed it)"})
        elif n.state == P.REVIEW:
            out.append({"id": n.id, "title": n.title, "why": "sign it off"})
        elif n.id in back:
            out.append({"id": n.id, "title": n.title, "why": "see why it came back"})
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
        repo=store.path.parent.parent.name,
        goal=P.goal(store),
        person=person,
        paused=P.paused(store),
        view=store.meta("view") or "auto",
    )
    view.counts = {state: sum(1 for n in live if n.state == state) for state in STATES}
    back = {n.id for n in live if P.came_back(store, n)}  # the next move is the person's, as in the terminal
    view.waiting_on_person = waiting_on_person(live, person, back)
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
                display_state=display_state(n, by_id, under, back),
                rev=n.rev,
                executor=n.executor,
                started_at=n.started_at,
                finished_at=n.finished_at,
                waits=came_back(store, n, export) + waits(n, by_id, under, back),
                log=node_log(store, n.id, export),
                forks=_forks(store, n, export),
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
    view.critical, view.at_once = critical_path(live), at_once(live)
    on_path = _critical_edges(view.critical, live)
    for n in ordered:
        for need in n.needs:
            source, target = placed.get(need), placed[n.id]
            if source is None:
                continue  # a dropped node it still names: `validate` refuses it, the view skips it
            view.edges.append(_edge(source, target))
            view.edges[-1].critical = view.edges[-1].id in on_path
    view.width = max(n.x + NODE_W for n in view.nodes)
    view.height = y - LANE_GAP

    wide = {n.id: tree_w(n) for n, _ in tree}
    at, goal = tidy(tree, under, wide)
    box = {i: (x, y, wide[i]) for i, (x, y) in at.items()}
    for shown in view.nodes:
        shown.tree_x, shown.tree_y = at[shown.id]
        shown.tree_w = wide[shown.id]
    view.tree_goal = [goal, 0.0]
    view.tree_links = [_link("", (goal, 0.0, NODE_W), n.id, box[n.id]) for n, d in tree if d == 0] + [
        _link(n.parent, box[n.parent], n.id, box[n.id]) for n, d in tree if d > 0
    ]
    view.tree_width = max(x + w for x, _, w in box.values())
    view.tree_height = max(y for _, y, _ in box.values()) + NODE_H
    return asdict(view)


def _edge(source: ViewNode, target: ViewNode) -> ViewEdge:
    """Out of the source's right edge, into the target's left edge. Between neighbouring columns it
    turns halfway across the gap between them. An edge that skips a column never runs through it: it
    drops into the gap under its source's row, crosses there, and rises in the gap before its target,
    where no box is."""
    sx, sy = source.x + NODE_W, source.y + NODE_H / 2
    tx, ty = target.x, target.y + NODE_H / 2
    if tx - sx > COL_GAP:
        under, out, back = source.y + NODE_H + ROW_GAP / 2, sx + COL_GAP / 2, tx - COL_GAP / 2
        points = [[sx, sy], [out, sy], [out, under], [back, under], [back, ty], [tx, ty]]
    else:
        middle = max(sx, (sx + tx) / 2)
        points = [[sx, sy], [tx, ty]] if sy == ty else [[sx, sy], [middle, sy], [middle, ty], [tx, ty]]
    return ViewEdge(f"{source.id}>{target.id}", source.id, target.id, points)
