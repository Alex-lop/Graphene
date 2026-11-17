"""`graphene state --json`: the plan as one JSON snapshot for an editor, and `graphene plan log --json
--since ID`: the plan's log as rows after a cursor, so the editor follows changes cheaply.

The snapshot is what `graphene watch` draws once a second, as data: it is built from the cockpit's own
reader (`cockpit.read.read` and its Task, Fork and Question), the plan's nodes for the sub-goals and the
edges, the settings and `auto.state` for the envelope and the round, the run's lock for the run, the log's
usage rows for what was spent, and its last id as the cursor. Schema 1: a key may gain siblings and is never
renamed; what is not known is null or empty. Read-only: nothing here writes the store or holds a lock.

While a planner writes a plan (`graphene ask`), ``drafting`` says who, whether its stream carries the plan's
text as it is written (``live``), and the steps whose lines are complete so far, for a graph to draw before
they are proposals; null when nobody is, and in the same commit that makes them proposals.

Following the plan: `graphene state --json --watch` (``follow``) prints the snapshot once, then once more
each time the store's own version moves: SQLite's `PRAGMA data_version` (another connection committed), the
log's last id, the run lock coming or going, or an ask that was drafting going. It looks every TICK seconds,
a few cheap reads a look and nothing printed when nothing changed, and ends with exit 0 when its stdout
closes or on SIGTERM. An editor on an older CLI,
which answers `--watch` with "No such option", keeps the snapshot's ``cursor`` and asks
`graphene plan log --json --since <cursor>` for what happened since (one row a line, nothing when nothing
did), then reads `state --json` again when a row came. The cheapest trigger there is the store's own files:
`.graphene/graphene.db-wal` changes on every write while a run or a session holds a connection,
`.graphene/graphene.db` on a checkpoint, so it watches that directory for `graphene.db*` and debounces about
200 ms; `.graphene/run.lock` appears with a run and goes with it. A WAL reader blocks no writer.

What a step may do, in plain view (the Scope pane's keys, siblings of the ones above): ``tree``, the
repository's top-level entries, and ``allows``, the shell commands the executor's own command line lets it
run without asking; and on each task ``files`` and ``files_n`` (the tracked files its scope covers now),
``touched`` (written so far by the attempt going now), ``stops`` (every write of its that was refused, with
the time and how), ``checked`` (its check's verdict before the work and after), ``tokens`` (read, cached,
written, turns) and ``held``: how a write outside its files is held, by what tests/test_every_agent.py
proves and nothing more.

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
import re
import shlex
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
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
LISTED = 200  # the most paths `tree` and a task's `files` list; `files_n` counts them all
VERDICTS = ("red", "passes", "outside", "environment", "landed")  # a `precheck` row's, as `checked` says them


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
    connection committed (`PRAGMA data_version`, one page read), the log's last id (an index lookup), the
    run lock as a file (its size and mtime, or None when there is no run), and whether the ask that says it
    is drafting is there (a killed one writes nothing more: its going is the change). Any of them moving is
    a change; none moving is nothing to say."""
    from .run import _alive

    moved = store.conn.execute("PRAGMA data_version").fetchone()[0]
    try:
        lock = os.stat(root / ".graphene" / "run.lock")
        held = (lock.st_size, lock.st_mtime_ns)
    except OSError:
        held = None
    draft = _draft(store)
    return moved, cursor(store), held, draft is not None and _alive(draft["pid"])


def identity(root: Path) -> tuple | None:
    """The store's file itself, as `--watch` tells one store from the next: its device and inode, or None
    while there is none. A connection keeps the file it opened even after `git clean -fdx` unlinks it, so
    the version read on it would never move again; the file's identity says the store went or is another."""
    try:
        own = os.stat(root / ".graphene" / "graphene.db")
    except OSError:
        return None
    return own.st_dev, own.st_ino


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
) -> bool:
    """`graphene state --json --watch`: one line at once, then one more each time ``version`` moves, while
    ``alive`` says to go on (the caller's: stdout open, no SIGTERM); True then. The version is read before
    the snapshot, so a write that lands between the two is said again on the next look rather than missed.
    False when the store's file went or is another (``identity``): nothing more is said on this store, and
    the caller follows what is there now."""
    was, own = None, identity(root)
    while alive():
        if identity(root) != own:
            return False
        now = version(store, root)
        if now != was:
            say(line(store, root))
            was = now
        time.sleep(tick)
    return True


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

    if now is None and replay(store):  # a replay's clock is the recording's: its newest row
        newest = store.conn.execute("SELECT MAX(timestamp) FROM node_log").fetchone()[0]
        now = datetime.fromisoformat(newest.replace("Z", "+00:00")).timestamp() if newest else None
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
    standing = P.standing(store)  # no scope covers these, whatever its globs say: the gate's `plan.binds`
    files = sorted(f for f in m.files if P.kept_out_by(f, standing) is None)
    hooks = hooked(root)
    return {
        "schema": SCHEMA,
        "graphene": __version__,
        "repo": str(root),
        "replay": replay(store),
        "stand_in": stand_in(rows),
        "cursor": cursor(store),
        "goal": P.goal(store) or store.meta("goal:proposed") or "",
        "first": m.first,
        "planner": chosen(store, "planner"),
        "executor": m.executor,
        "allows": allows(store),
        "tree": tree(m.files),
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
        "drafting": drafting(store),
        "spent": bill["dollars"] if bill else 0.0,
        "scoreboard": {"need_you": need, "running": running, "proven": proven, "total": total},
        "width": wide["most"] if wide else 0,
        "questions": [asdict(q) for q in m.questions],
        "goals": [
            {"id": n.id, "title": n.title, "parent": n.parent, "state": n.state, "check": n.check}
            for n in nodes
            if kids.get(n.id)
        ],
        "tasks": [
            task(m, t, by.get(t.id, []), by_id.get(t.id), root)
            | pane(t, by.get(t.id, []), by_id.get(t.id), files, m.executor, hooks)
            for t in m.tasks.values()
        ],
        "edges": [[need_id, n.id, "needs"] for n in nodes for need_id in n.needs if need_id in ids]
        + [[a, b, kind] for a, b, kind in m.extra_edges],
        "news": news(store, m),
    }


def _draft(store) -> dict | None:
    """What `graphene ask` wrote while its planner writes (the plan_meta key `ask.DRAFTING`), as it wrote it:
    who plans, the steps so far, and the ask's own pid and start. None when no ask says it is drafting."""
    try:
        said = json.loads(store.meta("drafting") or "null")
    except ValueError:
        return None
    return said if isinstance(said, dict) and isinstance(said.get("pid"), int) else None


def drafting(store) -> dict | None:
    """The plan a planner is writing now: who (as ``planner`` names one), whether its stream carries the
    plan's text as it is written (``live``: its steps appear one by one; else the plan arrives whole, and
    ``steps`` stays empty until it does), and each step whose own line is complete, in the order written
    (`plan_text.drafted`). None when no planner is writing: the ask made its proposals or ended some other
    way, or its process is gone (killed, so it never said so: the store still holds what it wrote, and the
    pid and start time it wrote beside it name no process now, as a dead run's lock does not)."""
    from .run import _still

    said = _draft(store)
    if said is None or not _still(said["pid"], said.get("start")):
        return None
    return {"by": str(said.get("by") or ""), "live": bool(said.get("live")), "steps": said.get("steps") or []}


def stand_in(rows: list[dict]) -> bool:
    """Whether every model call the log priced was a stand-in's (`tokenfactory.endpoint`: the tests' fake, the
    harness's dev/proof/standin.py), so an editor filming a free race says on screen that it is one. False
    with no call on record, or when any call went to a real endpoint."""
    said = [(r.get("detail") or {}).get("endpoint") for r in rows if r.get("kind") == "usage"]
    return bool(said) and all(e == "a stand-in" for e in said)


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


def passes_before(log: list[dict], node: P.Node | None) -> bool:
    """Its check already passes on the code as it is, before any work, so it proves nothing yet: the leaf's
    last `precheck` row is about the check and the revision it has now and says `passes`. Said from red
    first until the work is done (open, and while it runs), so a card is marked before its agent starts; done
    or in review, the cockpit's own `hollow` says it. Red first runs as a run starts and in auto's gate, and
    never on a proposal: with the plan still suggested, no check has run and nothing is marked."""
    if node is None or node.state not in (P.OPEN, P.RUNNING):
        return False
    said = [r["detail"] for r in log if r["kind"] == "precheck"]
    last = said[-1] if said else {}
    return last.get("verdict") == "passes" and last.get("rev") == node.rev and last.get("check") == node.check


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
        "hollow": t.hollow or passes_before(log, node),
        "why": t.note if t.state == "came back" else "",
        "checkout": where if where and Path(where).is_dir() else None,
        "base": (node.base_sha or None) if node else None,
        "attempts": len(own) or max((f["attempts"] for f in forks), default=0),
    }


def tree(files: list[str]) -> list[str]:
    """The repository's top-level entries as git tracks them, from the files the cockpit's model already
    holds (git is not asked again; a replay's repository is not on disk, so it has none): the folders, each
    ending "/", then the files, each group sorted, LISTED at most."""
    folders = sorted({f.split("/", 1)[0] + "/" for f in files if "/" in f})
    return [*folders, *sorted(f for f in files if "/" not in f)][:LISTED]


def allows(store) -> list[str] | None:
    """The shell commands the executor's own command line lets it run without asking: for Claude Code, the
    `Bash(...)` entries of its `--allowedTools`, read from the whole command `graphene run` starts
    (`run.named` of the store's `executor`: the default names two, `graphene node *` and `graphene plan *`).
    None when the command line names no such list (Codex, the Nemotron executor, a command of the person's
    own, nobody chosen) or switches the asking off: it may run any command, and what a command writes is
    still held to the step's files. Never an entry of `--disallowedTools`: that list says the opposite.
    Only a command that begins as Claude Code's is resolved: Nemotron's is an extra's to say."""
    from . import meter as M
    from . import run as R

    argv: list[str] = []
    if chosen(store, "executor").startswith("claude"):
        try:
            argv = shlex.split(R.named(store.meta("executor")))
        except ValueError:  # a quote left open: nothing `graphene run` could start
            pass
    if not argv or Path(argv[0]).name != "claude":
        return None
    if "--dangerously-skip-permissions" in argv or M.option(argv, "--permission-mode") == "bypassPermissions":
        return None
    said: list[str] = []
    listing = False
    for arg in argv[1:]:
        flag, _, joined = arg.partition("=")
        if flag in ("--allowedTools", "--allowed-tools"):
            listing, arg = True, joined
        elif arg.startswith("-"):
            listing = False
        if listing:
            said += re.findall(r"Bash\(([^)]*)\)", arg)
    return said or None


def hooked(root: Path) -> bool:
    """Whether this repository has Graphene's gate among Claude Code's hooks: our command on PreToolUse, in
    the settings file `graphene init` put it in (`hooks.hooks_file`). That hook is what refuses a write
    before it happens; our command on another event alone refuses nothing. False when the file is not there
    or does not read."""
    from . import hooks as H

    try:
        groups = json.loads(H.hooks_file(root).read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        return any(H._is_ours(h) for g in groups if isinstance(g, dict) for h in H._handlers(g))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def checked(log: list[dict], check: str) -> dict:
    """The check's verdict before the work and after, each only while it is about the check the task has
    now: ``before`` from its last `precheck` row (red first, precheck.py: one of VERDICTS), ``after``
    "passed" or "failed" from its last `check_passed` or `check_failed` row. None for a check that was
    edited since, was not run, or is not there: what an older check said is not this one's result."""
    before = next((r["detail"] for r in reversed(log) if r["kind"] == "precheck"), {})
    after = next((r for r in reversed(log) if r["kind"] in ("check_passed", "check_failed")), None)
    out: dict[str, str | None] = {"before": None, "after": None}
    if check and before.get("check") == check and before.get("verdict") in VERDICTS:
        out["before"] = before["verdict"]
    if check and after is not None and after["detail"].get("command") == check:
        out["after"] = after["kind"].removeprefix("check_")
    return out


def tokens(log: list[dict]) -> dict | None:
    """What the task's attempts spent, its forks' included, from its `usage` rows as `node_record.bill` adds
    them up: ``read`` the prompt tokens, ``cached`` how many of those came from the cache (None when no row
    says: Codex reports none), ``written`` the completion tokens, ``turns`` the model turns. None when no
    attempt of it has a metered row: not started, or an executor with no meter."""
    from . import meter as M
    from . import node_record as NR

    bill = NR.bill(log)
    if bill is None:
        return None
    cached = [u[M.PROMPT[2]] for r in log if r["kind"] == "usage" and M.PROMPT[2] in (u := r["detail"])]
    return {"read": bill["prompt_tokens"], "cached": sum(cached) if cached else None,
            "written": bill["completion_tokens"], "turns": bill["calls"]}  # fmt: skip


def held(node: P.Node | None, chosen: str, hooks: bool, log: list[dict] | tuple = ()) -> dict:
    """How a write outside the task's files is held, by what is proven and nothing more (tests/
    test_every_agent.py, dev/process/graph-edit/hooks.md). "refused", before the write: its executor is
    Claude Code and this repository has the gate among its hooks (``hooked``). "caught", when it finishes:
    anyone else holding it (Codex, the Nemotron executor, a command of the person's own), and Claude Code
    without the hooks; the finish checks what changed against the scope whoever did the work. "none": a task
    that is the person's to do, where nothing stops whatever writes it (the person, or an editor's own agent)
    and nothing checks it until it is marked done; and a task held by something no run started and no proven
    session is (an editor's own agent, a person who took an agent's task): nobody has tested those. Codex is
    never "refused": whether its hooks are trusted is not in the store. Nor is a step whose forks are not all
    Claude Code (``log``'s last `forked` row says who runs each): the weakest fork is what holds.
    ``by`` is who holds it while it runs (`run:claude` and a session's `claude:5e55105e`
    are both claude), else the executor chosen for the repository (``chosen``, the snapshot's `executor`),
    or "you"."""
    if node is not None and node.owner != P.AGENT:
        return {"state": "none", "by": "you"}
    holds = (node.executor or "") if node is not None and node.state == P.RUNNING else ""
    by = holds.removeprefix("run:").partition(":")[0] or chosen
    if holds and not holds.startswith(("run:", "claude:", "codex:")):
        return {"state": "none", "by": by}
    forks = next((r["detail"].get("with") or {} for r in reversed(log) if r["kind"] == "forked"), {})
    mixed = bool(holds and node.forked) and any(str(w).partition(":")[0] != "claude" for w in forks.values())
    claude = by.partition(":")[0] == "claude" and not mixed
    return {"state": "refused" if claude and hooks else "caught", "by": by}


def pane(t, log: list[dict], node: P.Node | None, files: list[str], chosen: str, hooks: bool) -> dict:
    """What the step pane's Scope tab reads for one task, beside `scope`, `changed` and `stopped`, which stay
    as they are. `files` are the tracked files its scope covers, matched as the gate matches a write
    (`plan.in_scope`: the last glob that matches decides, so a `!` glob takes paths back out), LISTED at most
    and `files_n` in all. ``files`` is every tracked file no standing setting keeps out, sorted: a scope's
    are a slice of it (`plan._within`, as `plan.one_writer` finds them), so a plan of forty steps does not
    match every file against every scope. `touched` is the cockpit's own (`Task.touched`) while it runs;
    `stops` is the whole history, oldest first, where `stopped` is the attempt going now."""
    covered = [f for f in P._within(files, P._prefixes(t.scope)) if P.in_scope(f, t.scope)]
    return {
        "files": covered[:LISTED],
        "files_n": len(covered),
        "touched": sorted(t.touched) if t.state == "running" else [],
        "stops": [
            {"path": str(d["path"]), "at": r["timestamp"], "how": str(d.get("how") or "")}
            for r in log
            if r["kind"] == "denied" and (d := r["detail"]).get("path")
        ],
        "checked": checked(log, t.check),
        "tokens": tokens(log),
        "held": held(node, chosen, hooks, log),
    }


def news(store, m) -> list[str]:
    """The last few things that happened, each a line as the replay's narrator says it (`replay.news`, a
    row at a time): bookkeeping rows say nothing, so the lines are what a person would be told."""
    from .cockpit import narrate as replay  # the narrator alone: no Textual

    raw = store.conn.execute("SELECT * FROM node_log ORDER BY id DESC LIMIT ?", (NEWS_ROWS,)).fetchall()
    titles = {t.id: t.title for t in m.tasks.values()}
    said = [replay.news({"node_log": [dict(r)]}, titles, m.names) for r in reversed(raw)]
    return [line for line in said if line][-NEWS:]
