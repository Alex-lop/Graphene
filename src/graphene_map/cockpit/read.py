"""Reading the plan's store into the cockpit's model: one look, once a second.

`read` is a pure function of the store and the last model shown: what the plan says (a task a leaf, its
state as a person reads it, what it waits on, what it is for), what the person still has selected, and the
news they were last told survive from one look to the next. The screens never see the store.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .. import board as B
from .. import board_rows as BR
from .. import plan as P
from .. import run as R
from .. import settings as S
from .. import views as V
from .look import short
from .model import Ev, Model, Question, Task

# what a person reads a leaf as (plan.reads), and the state the cockpit draws it in
STATE = {
    "done": "done", "running": "running", "review": "review", "came back": "came back",
    "proposed": "proposed", "ready": "ready", "waiting": "waiting", "yours": "yours",
    "to fill in": "waiting",
}  # fmt: skip
FOLD_AFTER = 8  # more finished tasks than this, and the rows keep the latest few: the rest are counted
KEEP_DONE = 4
FILES_EVERY = 30.0  # seconds between looks at what git tracks: a big repository's list is not free
GIT_EVERY = 5.0  # seconds between asks of git, for each running leaf: it costs three of its commands
ROWS = 200  # the latest rows of a leaf's log the cockpit reads each look: a run's log can be long
SAYS = 400  # characters kept of what an agent said or ran: the screen cuts it to its width, with an ellipsis
LIVE = ("running", "review", "came back")  # the tasks whose agent the rows are read for
KINDS = {"reading": "read", "editing": "edit", "running": "run", "searching": "search"}  # a did row's verb
TOOLS = {"Read": "read", "NotebookRead": "read", "Grep": "search", "Glob": "search", "Edit": "edit",
         "Write": "edit", "MultiEdit": "edit", "NotebookEdit": "edit", "Bash": "run"}  # a hook's tool call
OURS = re.compile(r"(?:^|[\s/])graphene node ")  # an agent's own `graphene node done …`: bookkeeping


def looker(root: Path, open_store: Callable) -> Callable[[Model | None], Model]:
    """The function `Cockpit` is given: the model now, from the store, keeping what the person has chosen.
    A store too busy to open leaves the last model as it was, with a word on the news."""
    import sqlite3

    import typer

    def look(previous: Model | None) -> Model:
        try:
            with open_store() as store:
                return read(store, root, previous)
        except (sqlite3.Error, OSError, typer.Exit) as no:  # the CLI's opener says Exit when it fails
            model = previous or Model("the plan's store did not open")
            model.say(f"✗ the plan's store did not open ({no}); the screen is as it was")
            return model

    return look


def read(
    store, root: Path, previous: Model | None = None, now: float | None = None,
    files: list[str] | None = None,
) -> Model:
    now = time.time() if now is None else now
    nodes, words, goal = V.inputs(store)
    by_id = {n.id: n for n in nodes}
    kids = P.kids(nodes)  # as the engine counts: a proposed child does not make its parent a sub-goal
    m = Model(goal, "plan")
    m.clock = now
    if previous is not None:  # what is the person's survives a look: the selection, the lens, the news
        m.selected, m.lens, m.feed = previous.selected, previous.lens, previous.feed
        m.moved = previous.moved
        # `v` turns the lens and nothing else: one the plan's stage did not give it last look is the person's
        m.lens_chosen = previous.lens_chosen or previous.lens != lens_for(previous.tasks.values())
        m.files, m.files_at, m.seen = previous.files, previous.files_at, previous.seen
    if files is not None:  # told (a replay's, from its recording): git is never asked
        m.files, m.files_at = files, now
    elif not m.files or now - m.files_at > FILES_EVERY:
        m.files, m.files_at = P.tracked(root), now
    m.names = numbers(store)  # agent 1, agent 2: the tasks in the order they were first taken
    m.protected = S.protected(store) + S.readonly(store)
    m.first = P.plan_first(store)
    chosen = (store.meta("executor") or "").split()  # what R starts, when `graphene init` chose it
    m.executor = Path(chosen[0]).name if chosen else ""
    leaves = [n for n in nodes if not kids.get(n.id)]
    keep = {n.id for n in leaves}
    for n in leaves:
        above = P.above(n, by_id)
        m.tasks[n.id] = Task(
            n.id,
            short(n.title),
            STATE.get(words.get(n.id, ""), "waiting"),
            list(n.scope),
            [x for x in n.needs if x in keep],
            full=n.title,
            why=" › ".join(short(a.title) for a in reversed(above)),
            above=[(a.id, short(a.title)) for a in reversed(above)],
        )
    for node_id in {r["node_id"] for r in store.node_log(kinds=("overruled",))}:  # rare: a person's override
        t = m.tasks.get(node_id)
        if t is not None and t.state == "done":
            row = ended(store, node_id)
            t.overruled = bool(row and row["kind"] == "overruled")  # not since finished properly
    fold_done(m, by_id)
    items = {it["id"]: it for it in B.items(store)}
    for t in m.tasks.values():
        node = by_id[t.id]
        t.agent = m.names.get(t.id, "")  # a task taken once keeps its number, back, ready again and done
        last = ended(store, t.id) if t.state == "done" else None
        proofs(t, node, last)
        if t.state in LIVE:
            live(store, m, t, node)
        if t.state == "running":
            told(store, t, node, by_id, items)
        if t.state == "came back":
            came_back(store, t, node)
        if t.state == "done":
            t.changed = list((last or {"detail": {}})["detail"].get("changed") or [])
    m.questions = [question_of(item) for item in BR.read(store).open]
    if not m.lens_chosen:
        m.lens = lens_for(m.tasks.values())
    rows = m.order()
    if rows and (not m.moved or m.selected not in {rid for _, rid in rows}):
        m.selected = rows[0][1]  # the first row is what needs the person most, until they choose one
    elif not rows:
        m.selected = ""
    return m


def numbers(store) -> dict[str, str]:
    """The number each task's agent goes by: the order in which the plan's tasks were first taken, as its
    log has them. It never changes between looks or when watch opens again, and a task keeps it when it
    comes back and is tried again, by a new session or the same one: "agent 2" is on the second task."""
    rows = store.conn.execute(
        "SELECT node_id FROM node_log WHERE kind = 'started' AND node_id IN (SELECT id FROM nodes) "
        "ORDER BY id"
    ).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(r["node_id"], str(len(out) + 1))
    return out


def lens_for(tasks) -> str:
    """The map's lens for the plan's stage, until the person picks one: what the tasks may touch while
    anything is proposed or nothing has started, what is being touched while anything runs, and what
    changed once every task is done."""
    states = {t.state for t in tasks}
    if "running" in states and "proposed" not in states:
        return "live"
    return "changed" if states == {"done"} else "plan"


def fold_done(m: Model, by_id: dict[str, P.Node]) -> None:
    """The cockpit shows what is alive: when many tasks are finished, the latest few stay and the rest
    are a count."""
    done = [t for t in m.tasks.values() if t.state == "done"]
    if len(done) <= FOLD_AFTER:
        return
    latest = sorted(done, key=lambda t: by_id[t.id].finished_at or "")[-KEEP_DONE:]
    for t in done:
        if t not in latest and not t.overruled:  # one the person finished over its check stays in view
            m.tasks.pop(t.id)
            m.folded_done += 1


def question_of(item: dict) -> Question:
    """A board item the person has not settled, as a row: its words, the default `y` takes (an assumption's
    is "confirm", a risk's "noted"), and the other options, numbered as `graphene board pick` numbers them."""
    default = item["default"] or BR.YES[item["kind"]].split(" ", 1)[1]
    return Question(
        item["id"], item["text"], default, [o["text"] for o in item["options"]], item.get("about") or "",
        item["kind"],
    )  # fmt: skip


def epoch(stamp: str | None) -> float:
    """An ISO timestamp of the log's as seconds since the epoch; 0 for none."""
    try:
        return datetime.fromisoformat((stamp or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def recent(store, node_id: str, kinds: tuple[str, ...], limit: int = ROWS) -> list[dict]:
    """The latest rows of these kinds on a leaf, oldest first, their detail as a dict."""
    import json

    rows = store.conn.execute(
        f"SELECT * FROM node_log WHERE node_id = ? AND kind IN ({', '.join('?' for _ in kinds)}) "
        "ORDER BY id DESC LIMIT ?",
        (node_id, *kinds, limit),
    ).fetchall()
    return [{**dict(r), "detail": json.loads(r["detail"]) if r["detail"] else {}} for r in reversed(rows)]


def live(store, m: Model, t: Task, node: P.Node) -> None:
    """What the agent holding this task is doing, from the rows logged in the attempt going now (after the
    leaf's last `started` or `attempt` row, as `meter.going` reads it: an earlier hold's or attempt's are
    not this one's, and the gate's `denied` rows carry no attempt number): what it read, edited, ran and said
    (`did`, `said`), and the writes the gate stopped (`denied` with a path)."""
    t.started = epoch(node.started_at)
    t.hears = "claude" in (node.executor or "claude")  # only a hooked Claude Code session is told mid-run
    t.agent = m.agent_name(t.id)
    sign = R.live(store, node, m.clock)  # the meter's last row, the hooks' last call, the log's age
    t.idle = sign["idle"]
    rows = recent(store, t.id, ("started", "attempt", "did", "said", "denied"))
    begun = max((k for k, r in enumerate(rows) if r["kind"] in ("started", "attempt")), default=-1)
    tried = [epoch(r["timestamp"]) for r in rows[begun : begun + 1] if r["kind"] == "attempt"]
    since = max([t.started, *tried])  # when the attempt going now began: its hold, or a run's retry in it
    rows = rows[begun + 1 :]
    if not any(r["kind"] == "did" for r in rows) and node.session_id:
        calls(store, t, node, since)  # no stream: a person's own Claude Code session, seen by its hooks only
    for r in rows:
        d, at = r["detail"], epoch(r["timestamp"])
        if r["kind"] == "did":
            kind = KINDS.get(d.get("verb", ""), "run")
            target = str(d.get("target") or "")
            shell = kind == "run"  # a command is words; anything else names a file
            if shell and OURS.search(target):
                continue
            t.events.append(Ev(at, kind, text=target if shell else "", path="" if shell else target))
            if kind == "edit" and target:
                t.touched[target] = at
        elif r["kind"] == "said":
            t.events.append(Ev(at, "said", text=" ".join(str(d.get("text") or "").split())[:SAYS]))
        elif r["kind"] == "denied" and d.get("path"):
            t.events.append(Ev(at, "stop", path=str(d["path"])))
            t.touched.pop(str(d["path"]), None)  # a write it stopped did not happen: git says if another did
            if not P.in_scope(str(d["path"]), node.scope):  # a scope that has taken it in has not stopped it
                t.stopped.append((str(d["path"]), at))
    # no rows and no calls: the last thing its log says, unless the rows above left it out: the agent's own
    # `graphene node` command, or the session's newest call when that is from before this attempt
    last = " ".join(str(sign["last"] or "").split())[:SAYS]
    if not t.events and last and not OURS.search(last):
        newest = store.last_events(node.session_id) if node.session_id else []
        if all(epoch(c["timestamp"]) >= since for c in newest):
            t.events.append(Ev(m.clock - (t.idle or 0), "said", text=last))
    touched_by_git(store, m, t, node)


def proofs(t: Task, node: P.Node, ended: dict | None = None) -> None:
    """A leaf is proved by its check, and by the person's sign-off when it asks for one: at most two. The
    check has passed once the leaf is in review (it waits for the sign-off) or done; there is no partial
    progress inside a check. A leaf the person finished over its check (`--override`) is done, and proved by
    nothing: the row that ended it says whether the check had passed, and sign-off was skipped."""
    t.checks = int(bool(node.check)) + int(node.signoff)
    if t.state == "done" and ended and ended["kind"] == "overruled":
        t.passed = int(bool(node.check and ended["detail"].get("check_passed")))
    elif t.state == "done":
        t.passed = t.checks
    elif t.state == "review":
        t.passed = t.checks - int(node.signoff)
    else:
        t.passed = 0


def ended(store, node_id: str) -> dict | None:
    """The row that ended a leaf: `finished`, or `overruled` when the person made it done over its check."""
    rows = recent(store, node_id, ("finished", "overruled"), 1)
    return rows[-1] if rows else None


def came_back(store, t: Task, node: P.Node) -> None:
    """Why a leaf came back, in the agent's words, and what that offers the person (widen, a sibling,
    wait on another, reopen the owner): each a command."""
    t.note = " ".join(str(P.let_go(store, node).get("why") or "").split())[:SAYS]
    t.offers = {key: argv for key, _what, argv in P.offers(store, node)}


def told(store, t: Task, node: P.Node, by_id: dict[str, P.Node], items: dict[str, dict]) -> None:
    """What the person told this agent and whether it heard: a note about the leaf, a sub-goal above it
    or the whole plan, since the leaf was taken. It is heard when the hook put it next to a tool result
    (a `told` row); until then it is sending."""
    on = {None, node.id, *(a.id for a in P.above(node, by_id))}
    since = node.started_at or ""
    for r in recent(store, t.id, ("told",)):
        for item_id in r["detail"].get("items") or []:
            if item_id in items:
                it = items[item_id]
                t.told.append((" ".join(B.said(it).split()), epoch(it["updated_at"]), epoch(r["timestamp"])))
    ledger = set(json.loads(store.meta(f"told:{node.session_id}:{node.id}:{node.started_at}") or "[]"))
    for it in items.values():
        key = f"{it['id']}@{it['rev']}"
        if B.told(it) and it.get("about") in on and (it["updated_at"] or "") > since and key not in ledger:
            if not any(epoch(it["updated_at"]) == sent for _, sent, _ in t.told):
                t.told.append((" ".join(B.said(it).split()), epoch(it["updated_at"]), 0.0))  # not heard yet
    t.told.sort(key=lambda x: x[1])
    for text, sent, _heard in t.told[-2:]:
        t.events.append(Ev(sent, "you", text=f"“{text}”"))
    t.events.sort(key=lambda e: e.t)


def calls(store, t: Task, node: P.Node, since: float, count: int = 40) -> None:
    """The session's latest tool calls since the attempt going now began (``since``), from what the hooks
    recorded: the agent of a leaf a person's own Claude Code session holds has no executor stream, only
    these."""
    for call in store.last_events(node.session_id, count):
        kind, at = TOOLS.get(call["tool"]), epoch(call["timestamp"])
        command = " ".join(str(call["input"].get("command") or "").split())[:SAYS] if kind == "run" else ""
        if kind is None or at < since or OURS.search(command):  # before this attempt: not what it is doing
            continue
        path = call["file_path"] or ""
        t.events.append(Ev(at, kind, text=command, path="" if kind == "run" else path))
        if kind == "edit" and path and call["success"] is not False:
            t.touched[path] = at


def touched_by_git(store, m: Model, t: Task, node: P.Node) -> None:
    """The files this leaf has changed so far, as the plan itself counts them (`plan.changed_since`: what
    differs from when it began, however it was written, a shell command included), asked of git at most
    every few seconds for each leaf, and at once when it is taken again or its scope changes (a widen must
    not leave the file it gave flagged); and the ones outside its scope as `node done` counts them
    (`plan.outside_scope`: not what a leaf running beside it in the checkout may write, nor what a run
    landed)."""
    if not (node.checkout and node.base_sha):
        t.outside = [p for p in t.touched if not P.in_scope(p, node.scope)]
        return
    hold = (node.started_at, tuple(node.scope))  # what git's answer was for
    when, files, outside, asked = m.seen.get(t.id, (0.0, [], [], None))
    if asked != hold or m.clock - when >= GIT_EVERY or when > m.clock:
        try:
            files = P.changed_since(node.checkout, node.base_sha, node.dirty_at_start)
        except (P.Refused, OSError, subprocess.TimeoutExpired):
            files = list(t.touched)
        both = sorted({*files, *t.touched})
        try:
            outside = P.outside_scope(store, node, both)
        except (P.Refused, OSError, subprocess.TimeoutExpired):
            outside = [p for p in both if not P.in_scope(p, node.scope)]
        m.seen[t.id] = (m.clock, files, outside, hold)
    both = sorted({*files, *t.touched})  # what git sees, and what its own record says it edited
    t.touched = {p: t.touched.get(p, m.clock) for p in both}
    t.outside = [p for p in both if p in outside or (p not in files and not P.in_scope(p, node.scope))]

