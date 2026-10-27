"""`graphene state --json`: the plan as one JSON snapshot for an editor, and `graphene plan log --json
--since ID`: the plan's log as rows after a cursor, so the editor follows changes cheaply.

The snapshot is what `graphene watch` draws once a second, as data: it is built from the cockpit's own
reader (`cockpit.read.read` and its Task, Fork and Question), the plan's nodes for the sub-goals and the
edges, the settings and `auto.state` for the envelope and the round, the run's lock for the run, the log's
usage rows for what was spent, and its last id as the cursor. Schema 1: a key may gain siblings and is never
renamed; what is not known is null or empty. Read-only: nothing here writes the store or holds a lock.

Following the plan: `graphene state --json --watch` (``follow``) prints the snapshot once, then once more
each time the store's own version moves: SQLite's `PRAGMA data_version` (another connection committed), the
log's last id, or the run lock coming or going. It looks every TICK seconds, three cheap reads a look and
nothing printed when nothing changed, and ends with exit 0 when its stdout closes or on SIGTERM. An editor on
an older CLI, which answers `--watch` with "No such option", keeps the snapshot's ``cursor`` and asks
`graphene plan log --json --since <cursor>` for what happened since (one row a line, nothing when nothing
did), then reads `state --json` again when a row came. The cheapest trigger there is the store's own files:
`.graphene/graphene.db-wal` changes on every write while a run or a session holds a connection,
`.graphene/graphene.db` on a checkpoint, so it watches that directory for `graphene.db*` and debounces about
200 ms; `.graphene/run.lock` appears with a run and goes with it. A WAL reader blocks no writer.

Who is calling: reading needs no mark, so `state --json` answers anyone, an agent's shell included. An editor
that spawns `graphene` for a person's click (accept, add a step, link two steps) must drop the agent marks
from the environment it inherits (``MARKS``): VS Code started from a shell inside Claude Code carries
CLAUDECODE and CLAUDE_CODE_SESSION_ID, and with them every `node add` becomes a proposal the person cannot
accept and every person-only act is refused (`plan.caller`). It must not set GRAPHENE_AS or GRAPHENE_WATCH
either: the gate refuses a hooked session's command that names them, and neither makes anyone the person.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from . import plan as P

SCHEMA = 1
TICK = 0.1  # seconds between `--watch`'s looks at the store's version: at most one line every 100 ms
# what an editor drops from the environment before it spawns `graphene` for a person's click
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX", "AI_AGENT",
         *P.AGENT_MARKS)  # fmt: skip
NEWS_ROWS = 40  # the latest rows the news is read from; six lines of it at most, as the cockpit keeps
NEWS = 6
# a model's short name, when `meter.short` (the race lane's) is not there yet: the family's word
FAMILIES = ("nano", "super", "ultra", "haiku", "sonnet", "opus", "fable")


def error(why: str) -> dict:
    """What `graphene state --json` prints, and exits 1 on, when there is no plan to read here."""
    return {"schema": SCHEMA, "error": why}


def where(cwd: Path) -> tuple[Path | None, str | None]:
    """The repository to read, or why there is no Graphene here: not a git repository, or no store (nothing
    ran `graphene init`, or any command, here). Asked before the store is opened: opening makes one."""
    from .store import repo_root

    root = repo_root(cwd)
    if not (root / ".git").exists():
        return None, f"not a git repository: no .git above {cwd}"
    if not (root / ".graphene" / "graphene.db").exists():
        return None, "no Graphene store here: `graphene init` sets one up"
    return root, None


def unplanned(store) -> str | None:
    """Why an open store has no plan to read: nothing set up (`graphene init`) and nothing planned. A repo
    set up with nothing planned yet is a plan: a snapshot with no tasks, which an editor tells apart."""
    if store.meta("plan_first") is None and not P.nodes(store):
        return "nothing is set up or planned here yet: `graphene init`, then `graphene ask`"
    return None


def short(model: str | None) -> str:
    """A model id's short name: the race lane's `meter.short` when it is there, else the family's word
    (Nemotron's Nano, Super, Ultra; Claude's Haiku, Sonnet, Opus, Fable; Codex for GPT), else the id's last
    path part."""
    from . import meter as M

    if not model:
        return ""
    if (said := getattr(M, "short", None)) is not None:
        return str(said(model))
    low = model.lower()
    family = next((f for f in FAMILIES if f in low), None)
    if family:
        return family.capitalize()
    if "codex" in low or "gpt" in low:
        return "Codex"
    return model.rsplit("/", 1)[-1]


def cursor(store) -> int:
    """The log's last id: `plan log --json --since` this gives what happened after the snapshot."""
    return int(store.conn.execute("SELECT COALESCE(MAX(id), 0) FROM node_log").fetchone()[0])


def version(store, root: Path) -> tuple:
    """The store's own version, as `--watch` compares it from one look to the next: what SQLite says another
    connection committed (`PRAGMA data_version`, one page read), the log's last id (an index lookup), and the
    run lock as a file (its size and mtime, or None when there is no run). Any of the three moving is a
    change; none moving is nothing to say."""
    moved = store.conn.execute("PRAGMA data_version").fetchone()[0]
    try:
        lock = os.stat(root / ".graphene" / "run.lock")
        held = (lock.st_size, lock.st_mtime_ns)
    except OSError:
        held = None
    return moved, cursor(store), held


def line(store, root: Path) -> str:
    """One line for the stream: the snapshot, or the one-line error `state --json` prints in its place, so
    an editor reading lines is never left with half an object."""
    try:
        why = unplanned(store)
        said = snapshot(store, root) if why is None else error(why)
    except Exception as no:  # the same promise as `state --json`: one JSON object on stdout whatever happened
        said = error(f"the plan could not be read ({type(no).__name__}: {no})")
    return json.dumps(said)


def follow(
    store, root: Path, say: Callable[[str], None], alive: Callable[[], bool], tick: float = TICK
) -> None:
    """`graphene state --json --watch`: one line at once, then one more each time ``version`` moves, while
    ``alive`` says to go on (the caller's: stdout open, no SIGTERM). The version is read before the snapshot,
    so a write that lands between the two is said again on the next look rather than missed."""
    was = None
    while alive():
        now = version(store, root)
        if now != was:
            say(line(store, root))
            was = now
        time.sleep(tick)


def log_after(store, since: int = 0) -> list[dict]:
    """The log's rows after ``since``, oldest first, as `Store.node_log` shapes them (detail a dict)."""
    rows = store.conn.execute("SELECT * FROM node_log WHERE id > ? ORDER BY id", (since,)).fetchall()
    return [{**dict(r), "detail": json.loads(r["detail"]) if r["detail"] else {}} for r in rows]


def snapshot(store, root: Path, now: float | None = None) -> dict:
    """The plan now, schema 1 (the brief's): one dict `json.dumps` prints."""
    from . import __version__, auto
    from . import meter as M
    from . import node_record as NR
    from . import run as R
    from . import settings as S
    from . import views as V
    from .cockpit import read as CR

    m = CR.read(store, root, None, now, fold=False)  # every task: an editor folds nothing
    nodes = V.shown(store)
    ids = {n.id for n in nodes}
    kids = P.kids(nodes)
    rows = store.node_log()  # the whole log, read once: the bill, the width, each task's model and spend
    by = M.by_node(rows)
    pid = R.run_holding(root)
    bill = NR.bill(rows)
    wide = M.width(rows)
    need, running, proven, total = m.scoreboard()
    by_id = {n.id: n for n in P.nodes(store)}  # each task's checkout and base, as the plan keeps them
    return {
        "schema": SCHEMA,
        "graphene": __version__,
        "repo": str(root),
        "replay": replay(store),
        "cursor": cursor(store),
        "goal": P.goal(store) or store.meta("goal:proposed") or "",
        "first": m.first,
        "planner": chosen(store, "planner"),
        "executor": m.executor,
        "envelope": {
            "auto": S.auto(store),
            "budget": S.budget(store),
            "tasks": S.tasks(store),
            "rounds": S.rounds(store),
            "forks": S.forks(store),
            "review": S.review(store),
            "protected": S.protected(store),
            "readonly": S.readonly(store),
            "checks": S.checks(store),
        },
        "auto": auto.state(store),
        "run": {"going": pid is not None, "pid": pid},
        "spent": bill["dollars"] if bill else 0.0,
        "scoreboard": {"need_you": need, "running": running, "proven": proven, "total": total},
        "width": wide["most"] if wide else 0,
        "questions": [asdict(q) for q in m.questions],
        "goals": [
            {"id": n.id, "title": n.title, "parent": n.parent, "state": n.state, "check": n.check}
            for n in nodes
            if kids.get(n.id)
        ],
        "tasks": [task(m, t, by.get(t.id, []), by_id.get(t.id), root) for t in m.tasks.values()],
        "edges": [[need_id, n.id, "needs"] for n in nodes for need_id in n.needs if need_id in ids]
        + [[a, b, kind] for a, b, kind in m.extra_edges],
        "news": news(store, m),
    }


def replay(store) -> dict | None:
    """What a replay's store says of itself, or None in a real project's: `graphene demo --into DIR` writes
    the plan_meta key `replay` with what the screen's top line says, `shown` (a scripted stand-in, no model
    ran; or as it ran, live), `day` and `repository`. An editor shows a replay as one, and runs nothing."""
    raw = store.meta("replay")
    try:
        said = json.loads(raw) if raw else None
    except ValueError:
        return None
    return {k: said.get(k) for k in ("shown", "day", "repository")} if isinstance(said, dict) else None


def chosen(store, key: str) -> str:
    """Who `graphene init` chose as the planner or the executor: the command's first word, by its name."""
    said = (store.meta(key) or "").split()
    return Path(said[0]).name if said else ""


def task(m, t, log: list[dict], node: P.Node | None = None, root: Path | None = None) -> dict:
    """One task as the brief's schema has it. Its model and spend are the cockpit's once the race lane adds
    them to Task and Fork (`model`, `usd`); until then, and where it says nothing, the meter's: the attempt
    going now names the model, the task's usage rows its dollars, and a fork's own attempts both of its.
    The editor night's keys (siblings, schema 1): `why`, the reason it came back; `checkout`, the directory
    its agent works in while it runs or after it came back; `base`, the commit its work starts from;
    `attempts`, the last hold's own, or a fork's each; a running fork's `idle` and `checkout`."""
    from . import meter as M
    from . import node_record as NR
    from .cockpit.model import needs_you

    tries = M.attempts(NR._hold(log))  # the last hold's attempts: the one going now is the last
    going = tries[-1] if tries else None
    model = short(getattr(t, "model", "") or (going["model"] if going else None))
    usd = getattr(t, "usd", None)
    if usd is None:
        bill = NR.bill(log)
        usd = bill["dollars"] if bill else 0.0
    forks = []
    for f in t.forks:
        mine = [a for a in tries if a.get("fork") == f.letter]
        its = short(getattr(f, "model", "") or next((a["model"] for a in reversed(mine) if a["model"]), None))
        spent = getattr(f, "usd", None)
        if spent is None:
            spent = round(sum((a["dollars"] for a in mine), 0.0), 6)
        copy = root / ".graphene" / "worktrees" / f"{t.id}.{f.letter}" if root else None
        runs = f.state == "running"
        forks.append({"letter": f.letter, "state": f.state, "why": f.why, "lines": f.lines, "model": its,
                      "usd": spent, "attempts": len(mine),
                      "idle": round(f.idle, 1) if runs and f.idle is not None else None,
                      "checkout": str(copy) if runs and copy and copy.is_dir() else None})  # fmt: skip
    own = [a for a in tries if not a.get("fork")]  # a forked hold's attempts are its forks': the most of one
    where = (node.checkout or "") if node and t.state in ("running", "came back") else ""
    return {
        "id": t.id,
        "title": t.title,
        "full": t.full,
        "state": t.state,
        "parent": t.above[-1][0] if t.above else None,
        "scope": list(t.scope),
        "needs": list(t.needs),
        "check": t.check,
        "agent": t.agent,
        "model": model,
        "usd": usd,
        "idle": round(m.quiet(t), 1) if t.state == "running" else None,
        "needs_you": needs_you(t),
        "tail": m.tail(t),
        "note": t.note,
        "offers": dict(t.offers),  # a came-back task: the cockpit's key -> the command that takes it up
        "changed": list(t.changed),
        "stopped": [path for path, _ in t.stopped],
        "outside": list(t.outside),
        "forks": forks,
        "kept": {"letter": t.kept[0], "why": t.kept[1], "by": t.kept[2]} if t.kept else None,
        "hollow": t.hollow,
        "why": t.note if t.state == "came back" else "",
        "checkout": where if where and Path(where).is_dir() else None,
        "base": (node.base_sha or None) if node else None,
        "attempts": len(own) or max((f["attempts"] for f in forks), default=0),
    }


def news(store, m) -> list[str]:
    """The last few things that happened, each a line as the replay's narrator says it (`replay.news`, a
    row at a time): bookkeeping rows say nothing, so the lines are what a person would be told."""
    from .cockpit import narrate as replay  # the narrator alone: no Textual

    raw = store.conn.execute("SELECT * FROM node_log ORDER BY id DESC LIMIT ?", (NEWS_ROWS,)).fetchall()
    titles = {t.id: t.title for t in m.tasks.values()}
    said = [replay.news({"node_log": [dict(r)]}, titles, m.names) for r in reversed(raw)]
    return [line for line in said if line][-NEWS:]
