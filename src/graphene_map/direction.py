"""The direction: a small tree of goals the person authors, above the plans.

    # Graphene's direction. "?" is proposed and waits on you; make it "-" to accept it.
    - Graphene is the shared plan between a person and their coding agents  [graphene]
      - Graphene runs live on Token Factory  [live]
          every rung of the ladder passes live, and the bill is read from the ledger
      ? the submission by 30 October  [submission]

One line a node: "- title  [id]" is accepted, "? title  [id]" is proposed (make it "-" to accept
it). Indentation is the tree. Any other line indented under a node says what it is for. "#" lines
and blank lines are kept as they are. The file is ``.graphene/direction.txt`` in the main checkout,
beside the store, and unlike the store it is tracked by git: another machine's Graphene reads the
same direction. A file with a line Graphene cannot read is not used at all, and the refusal names
each line. Graphene rewrites only the lines an act changes (an accept, a drop, a proposal), so what
the person wrote comes back byte for byte.

Every plan hangs from one node (``graphene direction plan NODE``), and each session the hooks
recorded attaches to one: through the plan's node when it held or proposed one of the plan's
nodes, else where the person attached it (``graphene direction attach``), else it stays visible as
unattached. Nothing is inferred into the direction. Both links are this machine's, in the store's
plan_meta key ``direction``: nothing about a session goes into the file.

Status is read at read time from what the hooks already record (``sessions``, ``prompts``,
``tool_events``, ``agents``): the hook does no work for it. No transcript is read (decision 66).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import plan as P

FILE = ".graphene/direction.txt"
ALIVE = 300  # seconds since a session's last recorded call that it still counts as running
DAY = 86400  # a session quiet for longer than this is not shown: it helps nobody decide anything
IDLE = 3600  # a session or subagent idle (no call, and no end of its turn) for longer is not shown
_NODE = re.compile(
    r"(?P<indent> *)(?P<mark>[-?])\s+(?P<title>\S.*?)\s+\[(?P<id>[A-Za-z0-9][\w.-]{0,31})\]\s*"
)
_MEANT = re.compile(r" *[-?]\s")  # a line that means to be a node


@dataclass
class Node:
    id: str
    title: str
    proposed: bool  # its own mark is "?"
    parent: str | None
    indent: int
    at: int  # the index of its line in ``Direction.lines``
    end: int  # the index after its last line: its own lines and everything under it
    about: list[str] = field(default_factory=list)  # the lines that say what it is for


@dataclass
class Direction:
    lines: list[str]  # the file as it is, each line with its ending
    nodes: list[Node]

    def text(self) -> str:
        return "".join(self.lines)

    def get(self, node_id: str) -> Node:
        found = next((n for n in self.nodes if n.id == node_id), None)
        if found is None:
            raise P.refusal(f"no direction node [{node_id}]", do="`graphene direction` lists them")
        return found

    def above(self, node: Node) -> list[Node]:
        by_id, out = {n.id: n for n in self.nodes}, []
        while node.parent is not None:
            node = by_id[node.parent]
            out.append(node)
        return out

    def below(self, node: Node) -> list[Node]:
        return [n for n in self.nodes if node.at < n.at < node.end]  # a subtree is its lines, in a row

    def proposed(self, node: Node) -> bool:
        """A proposal, or under one: nothing under a guess is the person's until they accept it."""
        return node.proposed or any(a.proposed for a in self.above(node))


def _unsafe(c: str) -> bool:
    """A character a terminal obeys or that reorders what it shows: a control (C0, C1, DEL) other
    than a tab, or a bidirectional override."""
    return (
        (unicodedata.category(c) == "Cc" and c != "\t")
        or "\u202a" <= c <= "\u202e"
        or "\u2066" <= c <= "\u2069"
    )


def parse(text: str) -> Direction:
    """The direction a text says, or a refusal naming every line it cannot read (none of it is used)."""
    lines = [line for line in re.split(r"(?<=\n)", text) if line]  # "\n" only: numbered as an editor does
    nodes: list[Node] = []
    stack: list[Node] = []
    seen: dict[str, int] = {}
    parents: set[str] = set()
    refused: list[str] = []
    for k, raw in enumerate(lines):
        line = raw.rstrip("\r\n").removeprefix("﻿" if k == 0 else "")
        body = line.lstrip(" ")
        indent = len(line) - len(body)
        if any(_unsafe(c) for c in line):  # comments too: `graphene direction --text` prints them
            refused.append(f"line {k + 1}: a control character, which a terminal would obey: take it out")
            continue
        if not body.strip() or body.startswith("#"):
            continue
        if body[0].isspace() or body[0] == "﻿":
            refused.append(
                f"line {k + 1}: indent with spaces only (a tab or another blank is not read as one)"
            )
            continue
        found = _NODE.fullmatch(line)
        if found is None and _MEANT.match(line):
            refused.append(
                f"line {k + 1}: a node's line ends with its id in brackets, "
                f"like `- {body[2:42].strip()}  [an-id]`"
            )
            continue
        while stack and stack[-1].indent >= indent:
            stack.pop()
        if found is not None:
            if found["id"] in seen:
                refused.append(f"line {k + 1}: [{found['id']}] is already the id on line {seen[found['id']]}")
                continue
            parent = stack[-1] if stack else None
            node = Node(
                found["id"], found["title"], found["mark"] == "?", parent and parent.id, indent, k, k + 1
            )
            seen[node.id] = k + 1
            if parent is not None:
                parents.add(parent.id)
            nodes.append(node)
            stack.append(node)
        elif not stack:
            refused.append(
                f"line {k + 1}: a line under no node: indent it under the node it is about, or make it a "
                "node (`- title  [id]`)"
            )
            continue
        elif stack[-1].id in parents:
            refused.append(
                f"line {k + 1}: a line about [{stack[-1].id}] after the nodes under it: move it up, "
                "under its node's own line"
            )
            continue
        else:
            stack[-1].about.append(body.strip())
        for n in stack:
            n.end = k + 1
    if refused:
        raise P.Refused(
            f"{FILE} cannot be read, so none of it is used:\n" + "\n".join(f"  {r}" for r in refused)
        )
    return Direction(lines, nodes)


def _mark(d: Direction, node: Node, mark: str) -> None:
    line = d.lines[node.at]
    at = len(line) - len(line.lstrip("﻿ "))
    d.lines[node.at] = line[:at] + mark + line[at + 1 :]
    node.proposed = mark == "?"


def accept(d: Direction, ids: list[str], who: P.Caller) -> list[str]:
    """The person accepts nodes: each one, the proposals it sits under (a goal is never in the direction
    without its why), and the proposals under it. Returns the ids that changed."""
    P._person_only(who, "accepting a direction node")
    changed: list[str] = []
    for node in [d.get(i) for i in ids]:
        for n in [*d.above(node), node, *d.below(node)]:
            if n.proposed:
                _mark(d, n, "-")
                changed.append(n.id)
    return changed


def drop(d: Direction, node_id: str, who: P.Caller) -> list[str]:
    """The person drops a node and everything under it: its lines leave the file."""
    P._person_only(who, "dropping a direction node")
    node = d.get(node_id)
    gone = [node.id, *(n.id for n in d.below(node))]
    del d.lines[node.at : node.end]
    return gone


def propose(d: Direction, text: str, who: P.Caller, under: str | None = None) -> list[str]:
    """Add a subtree, in the file's own text, at the top or under ``under``. From an agent every node
    is a proposal ("?"), whatever it wrote; the person's own lines keep their marks. Returns the ids."""
    new = parse(text)
    if not new.nodes:
        raise P.refusal("nothing to propose: no node line (`? title  [id]`) in the text")
    taken = [n.id for n in new.nodes if n.id in {m.id for m in d.nodes}]
    if taken:
        raise P.refusal("already in the direction: " + ", ".join(f"[{i}]" for i in taken))
    parent = d.get(under) if under else None
    base = min(n.indent for n in new.nodes if n.parent is None)
    first = next((n for n in d.nodes if parent and n.parent == parent.id), None)
    to = first.indent if first else parent.indent + 2 if parent else 0  # beside its children, as they are
    add = []
    for n in new.nodes:
        if not who.person and not n.proposed:
            _mark(new, n, "?")
    for line in new.lines:
        bare = line.rstrip("\r\n").removeprefix("﻿")
        if not bare.strip() or bare.lstrip().startswith("#"):
            continue  # the proposer's notes are not the direction's
        add.append(" " * to + bare[base:] + "\n")
    at = parent.end if parent else len(d.lines)
    if at and not d.lines[at - 1].endswith("\n"):
        d.lines[at - 1] += "\n"
    d.lines[at:at] = add
    return [n.id for n in new.nodes]


# -- the file -----------------------------------------------------------------------------------------


def path(root: Path) -> Path:
    return Path(root) / FILE


def read(root: Path) -> Direction | None:
    """The direction in the main checkout, or None when there is no file."""
    p = path(root)
    try:
        return parse(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as no:
        raise P.Refused(
            f"{FILE} cannot be read, so none of it is used:\n  it is not UTF-8 (byte {no.start})"
        ) from None


def write(root: Path, d: Direction) -> None:
    """All or nothing: the text is read back before it replaces the file. The store's own .gitignore
    (``*``) is told to leave this one file to git."""
    text = d.text()
    parse(text)
    p = path(root)
    p.parent.mkdir(exist_ok=True)
    ignore = p.parent / ".gitignore"
    if ignore.exists() and f"!{p.name}" not in ignore.read_text(encoding="utf-8").split():
        with open(ignore, "a", encoding="utf-8") as f:
            f.write(f"!{p.name}\n")
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".direction-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.chmod(tmp, p.stat().st_mode & 0o777 if p.exists() else 0o644)  # a committed file, not a secret
    os.replace(tmp, p)


def ignored_by_git(root: Path) -> bool:
    """Does the repository's own .gitignore keep the file out (a `.graphene/` line does)?"""
    said = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", FILE], capture_output=True)
    return said.returncode == 0


# -- what hangs from it: this machine's, in the store -------------------------------------------------


def links(store) -> dict:
    """``plans``: a plan's goal to the node it hangs from; ``attach``: a session (or ``session/agent``)
    to the node the person attached it to."""
    said = json.loads(store.meta("direction") or "{}")
    return {"plans": said.get("plans", {}), "attach": said.get("attach", {})}


def _save_links(store, said: dict) -> None:
    store.set_meta("direction", json.dumps(said, ensure_ascii=False))


def hang(store, d: Direction, node_id: str, who: P.Caller) -> str:
    """The person hangs the plan in force (its goal) from a node. A plan keeps its node when a later
    one hangs elsewhere: that is how an earlier plan stays under its goal."""
    P._person_only(who, "hanging the plan from the direction")
    goal = P.goal(store)
    if not goal:
        raise P.refusal("the plan has no goal yet, so nothing to hang", do="`graphene plan goal '…'` first")
    d.get(node_id)
    said = links(store)
    said["plans"][goal] = node_id
    _save_links(store, said)
    store.log_node(
        "*", P._now(), "direction", who.label, None, None, {"note": f"the plan hangs from {node_id}"}
    )
    return goal


def resolve(store, given: str) -> tuple[str, str]:
    """A session or a subagent from the start of its id: (the key it is attached by, its short id)."""
    if len(given) < 4:
        raise P.refusal(f"{given!r} is too short to name a session: give at least 4 characters of its id")
    rows = store.conn.execute("SELECT id FROM sessions WHERE id LIKE ? || '%'", (given,)).fetchall()
    found = [(r[0], r[0][:8]) for r in rows]
    rows = store.conn.execute("SELECT session_id, id FROM agents WHERE id LIKE ? || '%'", (given,)).fetchall()
    found += [(f"{r[0]}/{r[1]}", r[1][:8]) for r in rows]
    if len(found) != 1:
        what = "no session or subagent" if not found else f"{len(found)} sessions and subagents"
        raise P.refusal(f"{what} with an id starting {given}", do="`graphene direction` shows each one's id")
    return found[0]


def attach(store, d: Direction | None, given: str, node_id: str | None, who: P.Caller) -> str:
    """The person attaches a session (or a subagent) to a node, or with ``None`` lets it go back to
    what it is doing (a plan's node) or to unattached."""
    P._person_only(who, "attaching a session to the direction")
    key, short = resolve(store, given)
    if node_id is not None:
        if d is None:
            raise P.refusal(
                f"there is no direction yet ({FILE})", do="`graphene direction propose -` starts one"
            )
        d.get(node_id)
    said = links(store)
    if node_id is None:
        said["attach"].pop(key, None)
    else:
        said["attach"][key] = node_id
    _save_links(store, said)
    return short


# -- status: read from what the hooks recorded, at read time -----------------------------------------


@dataclass
class Worker:
    """A session's main agent, or one of its subagents, as the person needs it: what it is, whose move
    it is, the last thing it did, and where it hangs."""

    key: str  # a session's id, or "session/agent"
    short: str  # the id a command takes
    label: str  # a subagent's task, else the person's last words to the session
    word: str  # running, idle, your turn, finished
    last: str  # the last thing it did, in a line
    at: str  # when
    node: str | None = None  # the direction node it attaches to; "plan": through the plan, wherever it hangs
    how: str = ""  # why it attaches there
    parent: str | None = None  # the subagent that started this one, when a subagent did
    holds: str | None = None  # the running leaf it holds: shown, and counted, as that leaf


def _stamp(at: datetime) -> str:
    """A time as the hook stamps its rows (``hooks.now_iso``), so the two compare as text."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _age(stamp: str | None, now: datetime) -> float:
    if not stamp:
        return float("inf")
    try:
        at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    return (now - (at if at.tzinfo else at.replace(tzinfo=UTC))).total_seconds()


def did(tool: str, raw: str | None, file_path: str | None, success: int | None) -> str:
    """One recorded call as the last thing a session did: its own description, never its output."""
    try:
        said = json.loads(raw or "{}")
    except ValueError:
        said = {}
    said = said if isinstance(said, dict) else {}
    verb = {
        "Edit": "edited",
        "MultiEdit": "edited",
        "NotebookEdit": "edited",
        "Write": "wrote",
        "Read": "read",
    }
    if tool in verb and file_path:
        line = f"{verb[tool]} {file_path}"
    elif tool == "Bash":
        command = str(said.get("command") or "").strip().splitlines()
        line = str(said.get("description") or "") or f"ran {command[0][:60] if command else 'a command'}"
    elif tool in ("Agent", "Task"):
        line = f"started {said.get('description') or 'a subagent'}"
    elif tool == "SubagentHandback":
        line = "handed back its report"
    elif tool in ("Grep", "Glob"):
        line = f"searched {said.get('pattern') or ''}".strip()
    else:
        line = tool
    return line + (" (failed)" if success == 0 else "")


def _last_call(store, sid: str, aid: str | None, since: datetime):
    """One agent's newest call since ``since``, walked back along the session index. Never a scan of
    the session: a row's agent_id sits after its response, which can be 256 KB."""
    return store.conn.execute(
        "SELECT timestamp, tool, input, file_path, success FROM tool_events WHERE session_id = ? "
        "AND timestamp >= ? AND agent_id IS ? ORDER BY timestamp DESC LIMIT 1",
        (sid, _stamp(since), aid),
    ).fetchone()


def workers(store, now: datetime | None = None) -> tuple[list[Worker], int]:
    """Every session and subagent with something recorded in the last day, and how many older ones
    are left out. Each query goes by the session index the hook already keeps."""
    from .gate import _vendor_made

    now = now or datetime.now(UTC)
    out: list[Worker] = []
    older = 0
    for sid, started, stopped in store.conn.execute(
        "SELECT id, started_at, ended_at FROM sessions ORDER BY started_at"
    ):
        called = store.conn.execute("SELECT MAX(timestamp) FROM tool_events WHERE session_id = ?", (sid,))
        prompts = store.conn.execute(
            "SELECT timestamp, text FROM prompts WHERE session_id = ? ORDER BY ordinal DESC LIMIT 30", (sid,)
        ).fetchall()
        stamps = (started, stopped, called.fetchone()[0], *(p[0] for p in prompts))
        latest = max([s for s in stamps if s], default=None)
        if _age(latest, now) > DAY:
            older += 1  # asked of the index alone: an old session's calls are never read
            continue

        # the Agent call that started a subagent names it, its task, and who made the call (a call
        # still running, a foreground subagent's, is recorded only when it ends)
        started_by = {
            r[0]: (r[1], r[2])
            for r in store.conn.execute(
                "SELECT json_extract(response, '$.agentId'), json_extract(input, '$.description'), agent_id "
                "FROM tool_events WHERE session_id = ? AND tool IN ('Agent', 'Task') "
                "AND json_valid(response) AND json_valid(input)",
                (sid,),
            )
        }
        agents = []
        for aid, _start, a_end, kind in store.conn.execute(
            "SELECT id, started_at, ended_at, type FROM agents WHERE session_id = ? ORDER BY started_at",
            (sid,),
        ):
            task, caller = started_by.get(aid, (None, None))
            label = task or (f"a subagent ({kind})" if kind else "a subagent")
            parent = f"{sid}/{caller}" if caller else None
            if a_end:  # finished: counted when a call started it (the vendor's own helpers are not)
                if aid in started_by:
                    agents.append(
                        Worker(f"{sid}/{aid}", aid[:8], label, "finished", "", a_end, parent=parent)
                    )
                continue
            row = _last_call(store, sid, aid, now - timedelta(seconds=IDLE))
            if row is None:
                continue  # an hour with nothing and no end: gone without its end recorded, most likely
            word = "running" if _age(row[0], now) <= ALIVE else "idle"
            agents.append(Worker(f"{sid}/{aid}", aid[:8], label, word, did(*row[1:]), row[0], parent=parent))
        mine = _last_call(store, sid, None, now - timedelta(seconds=DAY))
        said = next((t for _, t in prompts if not _vendor_made(t.strip())), "")
        heard = max([s for s in (mine and mine[0], prompts[0][0] if prompts else None) if s], default=started)
        running = sum(a.word == "running" for a in agents)
        turn_over = bool(stopped and stopped >= (heard or ""))
        if running:
            word = "running"  # its turn may be over, or it waits on a subagent: its subagents work
        elif turn_over:
            word = "your turn"
            agents = [a for a in agents if a.word != "idle"]  # its turn ended after them: they did too
        else:
            word = "running" if _age(heard, now) <= ALIVE else "idle"
        if word == "idle" and _age(heard, now) > IDLE:
            older += 1
            continue
        first = said.strip().splitlines()[0] if said.strip() else ""
        label = f"session: {first}" if first else "a session"
        last_line = did(*mine[1:]) if mine else "nothing yet"
        if running and (turn_over or _age(heard, now) > ALIVE):
            last_line = f"{running} of its subagents running"
        out.append(Worker(sid, sid[:8], label, word, last_line, max(stopped or "", heard or "")))
        out += agents
    return out, older


def place(store, ws: list[Worker]) -> None:
    """Where each worker attaches: where the person attached it; else through the plan's node, when it
    held, finished or handed back one of the plan's nodes, or proposed one; else with the subagent that
    started it, or with its session; else nowhere."""
    said = links(store)
    # a leaf made from a prompt (decision 18) is that session's own ask, not the plan's work
    alive = [n for n in P.nodes(store) if n.state not in P.GONE and not n.aside]
    if alive:
        marks = ", ".join("?" for _ in alive)
        rows = store.conn.execute(
            "SELECT DISTINCT session_id, agent_id FROM node_log "
            f"WHERE session_id IS NOT NULL AND node_id IN ({marks})",
            [n.id for n in alive],
        ).fetchall()
    else:
        rows = []
    worked = {(s, a) for s, a in rows} | {(n.session_id, n.agent_id) for n in alive if n.session_id}
    proposers = {n.proposed_by.split(":", 1)[1] for n in alive if (n.proposed_by or "").startswith("claude:")}
    placed: dict[str, str | None] = {}  # a session or subagent, as placed so far: a parent comes first
    for w in ws:
        sid, _, aid = w.key.partition("/")
        if w.key in said["attach"]:
            w.node, w.how = said["attach"][w.key], "attached by you"
        elif (sid, aid or None) in worked:
            w.node, w.how = "plan", "worked on the plan"
        elif not aid and sid[:8] in proposers:
            w.node, w.how = "plan", "proposed in the plan"
        elif placed.get(w.parent or ""):
            w.node, w.how = placed[w.parent or ""], "with the subagent that started it"
        elif aid and sid in said["attach"]:
            w.node, w.how = said["attach"][sid], "with its session, attached by you"
        elif aid and placed.get(sid):
            w.node, w.how = placed[sid], "with its session"
        placed[w.key] = w.node


def plan_status(store) -> dict | None:
    """The plan in force, rolled up: what waits on the person, what runs, what is next, and the bill
    when Graphene knows one (its Nemotron executors' and planner's usage rows)."""
    from . import board as B
    from .node_record import bill

    alive = [n for n in P.order(P.nodes(store)) if n.state not in P.GONE]
    goal = P.goal(store) or store.meta("goal:proposed") or ""
    if not alive and not goal:
        return None
    by_id = {n.id: n for n in alive}
    back = {n.id for n in alive if P.came_back(store, n)}
    words = {n.id: P.reads(n, alive, back) for n in alive}
    leaves = [n for n in P.leaves(alive) if not n.aside and n.state != P.PROPOSED]
    tops = [
        n
        for n in alive
        if n.state == P.PROPOSED and (n.parent not in by_id or by_id[n.parent].state != P.PROPOSED)
    ]
    ready = [n.id for n in P.ready(alive, P.Caller("agent", False)) if n.id not in back]
    usage = [e for e in store.node_log(kinds=("usage",)) if e["node_id"] in by_id or e["node_id"] == "*"]
    # each thing that waits on the person, named by the id they act on, with the command that acts
    do = {
        "review": "sign off: `graphene node signoff {}`",
        "came back": "`graphene node show {}`",
        "yours": "yours to do",
    }
    waiting = [
        {"id": n.id, "title": n.title, "word": words[n.id], "do": do[words[n.id]].format(n.id)}
        for n in alive
        if words[n.id] in do
    ]
    waiting += [
        {"id": n.id, "title": n.title, "word": "proposed", "do": f"`graphene plan accept {n.id}`"}
        for n in tops
    ]
    board = [it for name, group in B.groups(store) if name in dict(B.GROUPS) for it in group]
    waiting += [{"id": it["id"], "title": it["text"], "word": BOARD_VERB.get(it["kind"], "asks"),
                 "do": f"`graphene board` ({it['kind']})"} for it in board]  # fmt: skip
    running = [
        {"id": n.id, "title": n.title, "by": P.said_by(n.executor), "_held": (n.session_id, n.agent_id)}
        for n in alive
        if n.state == P.RUNNING and not n.aside
    ]
    return {
        "goal": goal,
        "leaves": len(leaves),
        "done": sum(n.state == P.DONE for n in leaves),
        "you": len(waiting),
        "running": len(running),
        "waiting": waiting,
        "leaves_running": running,
        "next": ready[0] if ready else None,
        "bill": bill(usage),
    }


def _running(ws: list[Worker], plan: dict | None) -> int:
    """What runs, each piece of work once and as the rows name it: each running leaf (the session or
    subagent holding it is beside it, not counted again), and each session or subagent that holds
    none. TODO: a subagent working on a leaf its session took is counted beside that leaf; the hooks
    do not record which leaf a subagent works on."""
    return (plan["running"] if plan else 0) + sum(not w.holds for w in ws)


def status(store, d: Direction | None, now: datetime | None = None) -> dict:
    """The direction with everything attached, rolled up: the page's data and every print's."""
    ws, older = workers(store, now)
    place(store, ws)
    said = links(store)
    plan = plan_status(store)
    goal = P.goal(store)
    plan_node = said["plans"].get(goal) if goal else None
    ids = {n.id for n in d.nodes} if d else set()
    for w in ws:
        if w.node not in ids and w.node != "plan":
            w.node = None  # attached to a node the file no longer has: unattached, visibly
    if plan is not None:
        plan["node"] = plan_node if plan_node in ids else None
        keys = {w.key: w for w in ws}
        for leaf in plan["leaves_running"]:
            sid, aid = leaf.pop("_held")
            key = f"{sid}/{aid}" if sid and aid else sid
            w = keys.get(key or "")
            if w is None and sid and aid:  # held by a subagent the hooks did not see start: its session
                w, key = keys.get(sid), sid
            if w is not None:
                w.holds, w.node = leaf["id"], "plan"
                leaf["by"], leaf["last"] = w.short, w.last
    earlier: dict[str, list[str]] = {}
    for g, n in said["plans"].items():
        if g != goal and n in ids:
            earlier.setdefault(n, []).append(g)
    nodes = []
    for n in d.nodes if d else []:
        mine = {n.id, *(b.id for b in d.below(n))}
        under = [w for w in ws if w.node in mine or (w.node == "plan" and plan and plan["node"] in mine)]
        has_plan = plan is not None and plan["node"] in mine
        proposals = [m for m in d.nodes if m.id in mine and m.proposed]
        you = len(proposals) + sum(w.word == "your turn" for w in under) + (plan["you"] if has_plan else 0)
        running = _running([w for w in under if w.word == "running"], plan if has_plan else None)
        # next is the work that starts next (what `graphene run` takes); a proposal waits on you
        nxt = plan["next"] if has_plan else None
        word = "proposed" if d.proposed(n) else "yours" if you else "running" if running else "quiet"
        nodes.append(asdict(n) | {"word": word, "you": you, "running": running, "next": nxt,
                                  "earlier": earlier.get(n.id, [])})  # fmt: skip
    return {
        "file": FILE,
        "nodes": nodes,
        "plan": plan,
        "sessions": [asdict(w) for w in ws],
        "older": older,
    }


# -- rows: the one row grammar (decision 41) -----------------------------------------------------------

BOARD_VERB = {
    "question": "asks",
    "assume": "assumes",
    "risk": "risk",
    "leave out": "leaves out",
    "note": "note",
}
WORD_LOOK = {
    "asks": "yours",
    "assumes": "yours",
    "risk": "yours",
    "leaves out": "yours",
    "note": "yours",
    "your turn": "yours",
    "idle": "waiting",
    "finished": "done",
    "quiet": "waiting",
}


def look(word: str) -> tuple[str, str]:
    return P.look(WORD_LOOK.get(word, word))


def _ago(stamp: str, now: datetime) -> str:
    s = _age(stamp, now)
    if s == float("inf"):
        return ""
    return "now" if s < 60 else f"{int(s // 60)}m ago" if s < 3600 else f"{int(s // 3600)}h ago"


def rows(
    st: dict, now: datetime | None = None, only: str | None = None
) -> list[tuple[int, str, str, str, str]]:
    """(depth, title, id, word, what) for each row: each node, then the plan hanging from it and the
    sessions attached; what is attached to nothing comes last. ``only`` keeps the path from the top
    to that node and what hangs from it (the line above the plan in `graphene plan` and the screen)."""
    now = now or datetime.now(UTC)
    nodes, plan, ws = st["nodes"], st["plan"], [w for w in st["sessions"] if w["word"] != "finished"]
    done = [w for w in st["sessions"] if w["word"] == "finished"]
    out: list[tuple[int, str, str, str, str]] = []
    by_id = {n["id"]: n for n in nodes}

    def depth(n: dict) -> int:
        return 0 if n["parent"] is None else 1 + depth(by_id[n["parent"]])

    def plan_row(d: int) -> None:
        said = [f"you {plan['you']}"] if plan["you"] else []
        said += [f"{plan['running']} running"] if plan["running"] else []
        said += [f"next: {plan['next']}"] if plan["next"] else []
        if plan["bill"]:
            whose = "Token Factory's" if plan["bill"]["endpoint"] == "token factory" else "a stand-in's"
            said.append(f"bill ${plan['bill']['dollars']:.4f} ({whose} usage)")
        out.append(
            (
                d,
                f"the plan: {plan['goal']}",
                "plan",
                f"{plan['done']}/{plan['leaves']} done",
                " · ".join(said),
            )
        )

    def plan_items(d: int) -> None:
        """Under the plan's row, what waits on the person, each by the id they act on, then each
        running leaf with who holds it beside it: named, not only counted."""
        for it in plan.get("waiting", []):
            out.append((d, it["title"], it["id"], it["word"], it["do"]))
        for leaf in plan.get("leaves_running", []):
            by = leaf.get("by") or ""
            last = leaf.get("last") or ""
            out.append((d, leaf["title"], leaf["id"], "running", " · ".join(s for s in (by, last) if s)))

    def workers_under(node: str | None, d: int) -> None:
        for w in [w for w in ws if w["node"] == node and not w.get("holds")]:
            out.append((d, w["label"], w["short"], w["word"], f"{w['last']} · {_ago(w['at'], now)}"))
        fin = [w for w in done if w["node"] == node and node is not None]  # unattached: helps no one
        if fin:
            out.append((d, f"{len(fin)} finished", "", "finished", ", ".join(w["short"] for w in fin)))

    keep = None
    if only is not None and only in by_id:
        n, keep = by_id[only], {only}
        while n["parent"] is not None:
            keep.add(n["parent"])
            n = by_id[n["parent"]]
    for n in nodes:
        if keep is not None and n["id"] not in keep:
            continue
        d = depth(n)
        said = [f"you {n['you']}"] if n["you"] else []
        said += [f"{n['running']} running"] if n["running"] else []
        said += [f"next: {n['next']}"] if n["next"] else []
        said += (
            [f"{len(n['earlier'])} earlier plan{'s' if len(n['earlier']) > 1 else ''}"]
            if n["earlier"]
            else []
        )
        out.append((d, n["title"], n["id"], n["word"], " · ".join(said)))
        if keep is not None:
            continue
        if plan and plan["node"] == n["id"]:
            plan_row(d + 1)
            plan_items(d + 2)
            workers_under("plan", d + 2)
        workers_under(n["id"], d + 1)
    if keep is not None:
        return out
    loose = [w for w in ws if w["node"] is None] + [w for w in done if w["node"] is None]
    unhung = plan is not None and plan["node"] is None
    if unhung or loose:
        how = "`graphene direction attach SESSION NODE`"
        how = "`graphene direction plan NODE` hangs the plan" if unhung else how
        out.append((0, "not in the direction", "", "", how))
        if unhung:
            plan_row(1)
            plan_items(2)
            workers_under("plan", 2)
        workers_under(None, 1)
    return out


def head(st: dict, where: str, width: int | None = None) -> str:
    """The first line: what waits on the person, what runs and what is next, then whose direction."""
    tops = [n for n in st["nodes"] if n["parent"] is None]
    unhung = st["plan"] is not None and st["plan"]["node"] is None
    loose = [w for w in st["sessions"] if w["node"] is None or (unhung and w["node"] == "plan")]
    you = sum(n["you"] for n in tops) + sum(w["word"] == "your turn" for w in loose)
    running = sum(n["running"] for n in tops)
    running += _running(
        [Worker(**w) for w in loose if w["word"] == "running"], st["plan"] if unhung else None
    )
    if unhung:
        you += st["plan"]["you"]
    nxt = next((n["next"] for n in tops if n["next"]), None) or (st["plan"]["next"] if unhung else None)
    lead = " · ".join([f"you: {you}", f"{running} running", *([f"next: {nxt}"] if nxt else [])])
    lead += " · the direction of "
    if width and len(lead) + len(where) > width:  # the repository's own name, and what is above it
        where = "…" + where[len(where) - max(width - len(lead), 2) + 1 :]
    return lead + where


def lines(
    st: dict, width: int, now: datetime | None = None, only: str | None = None
) -> list[tuple[str, str]]:
    """The rows laid out in fixed columns at ``width`` cells: (the line, the style of its glyph and
    word). The title is cut at a word, the id and the word never; what a row says after its word
    wraps under itself rather than being cut, so an id or a command in it is always whole."""
    import textwrap

    from rich.cells import cell_len

    from . import plan_text as T

    got = rows(st, now, only)
    if not got:
        return []
    wid = max([len(r[2]) for r in got] + [4])
    ww = max(len(r[3]) for r in got)
    need = max(cell_len(f"{'  ' * r[0]}◌ {r[1]}") for r in got)
    said = min(max(len(r[4]) for r in got), int(width * 0.45))  # what a row says after its word
    wt = max(20, min(need, 56, width - wid - ww - 8 - said))
    out = []
    for d, title, rid, word, what in got:
        glyph = look(word)[0] if word else "◌"
        lead = f"{'  ' * d}{glyph} "
        cells = f"{T.pad(lead + T.elide(title, wt - len(lead)), wt)}  {rid.ljust(wid)}  {word.ljust(ww)}"
        at = len(cells) + 4 if width - len(cells) - 4 >= 16 else len(lead) + 2  # else under the title
        said = textwrap.wrap(what, max(width - at, 16), break_long_words=False, break_on_hyphens=False)
        style = look(word)[1] if word else "dim"
        if said and at > len(cells):
            out.append((f"{cells}  · {said.pop(0)}", style))
        else:
            out.append((cells.rstrip(), style))
        out += [(" " * at + part, "dim") for part in said]
    return out


def above_plan(store, root: Path, width: int) -> list[tuple[str, str]]:
    """What `graphene plan`, its views and the screen show above the plan: the path from the top of
    the direction to the node the plan hangs from, each with what waits on you below it, what runs and
    what is next. Nothing when there is no direction or no plan; one line when the plan hangs from no
    node yet, or when the file cannot be read."""
    try:
        d = read(root)
    except P.Refused:
        return [(f"the direction: {FILE} cannot be read (`graphene direction` names the lines)", "")]
    alive = [n for n in P.nodes(store) if n.state not in P.GONE]
    if d is None or not (P.goal(store) or store.meta("goal:proposed") or alive):
        return []
    goal = P.goal(store)
    if links(store)["plans"].get(goal) not in {n.id for n in d.nodes} or not goal:
        said = "the direction: the plan hangs from none of its nodes yet (`graphene direction plan NODE`)"
        return [(said, "dim")]  # said before any session is read: this is on every `graphene plan`
    st = status(store, d)
    return lines(st, width, only=st["plan"]["node"])
