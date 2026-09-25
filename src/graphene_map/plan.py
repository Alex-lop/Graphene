"""The plan: nodes of work, what each may touch, how anyone knows it is done, and what it waits on.

Standard library only, because the hook imports this on every agent event.

A node's contract is the same whoever executes it (an agent of any vendor, or a person), and it binds
at the boundary by a mechanism that needs no vendor: ``finish`` runs the node's check itself and asks
git which paths changed since the node was started. A node with a failing check, or with a change
outside its scope, is not done, and what waits on it cannot start. What the Claude Code hooks add on
top (a write refused before it happens, a stop refused while a node is open) lives in
``sources/claude_code.py`` and reads the same rows.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

AGENT = "agent"  # the owner of a node any agent may take; every other owner is a person's name
PROPOSED, OPEN, RUNNING, REVIEW, DONE, DROPPED = "proposed", "open", "running", "review", "done", "dropped"
ARCHIVED = "archived"  # done or dropped, and put away by the person: no longer part of the plan
# A plan with a node in one of these is in force. Done counts: the first real agent run against this
# waited until every node was done and then made the edit no node allowed ("no node was open"), so a
# finished plan stays in force until the person pauses or archives it. A proposal binds nobody.
LIVE = (OPEN, RUNNING, REVIEW, DONE)
GONE = (DROPPED, ARCHIVED)
CHECK_TIMEOUT = 1800  # seconds; TODO: one fixed cap, a per-node value when a real check needs longer
TAIL = 2000  # characters of a check's output kept in the log
BASH = next((b for b in ("/bin/bash", "/usr/bin/bash") if os.path.exists(b)), None)  # a check's shell
KEPT_PATHS = 200  # changed paths kept in a node's log when it ends; the count of the rest is kept too
EDITABLE = ("title", "goal", "scope", "check", "signoff", "needs", "owner", "parent")
# Environment variables an agent's shell carries. GRAPHENE_NODE is ours: `graphene run` sets it for
# every executor it starts. TODO: the last two are from the vendors' docs, not yet seen on a real run.
AGENT_MARKS = ("GRAPHENE_NODE", "GRAPHENE_PLANNER", "GEMINI_CLI", "CURSOR_AGENT")


class Refused(Exception):
    """The plan says no, and the message is the reason, written for whoever asked."""


WIDE = 96  # the columns a refusal's line of paths fills before it says "and N more"


def refusal(what: str, paths: list[str] | tuple = (), do: str = "") -> Refused:
    """A refusal in one shape: what was refused and why, in a line; the paths, indented, as many as
    fit; then the one or two commands. Nothing more: an explanation is said once (``first_time``)."""
    lines = [what]
    if paths:
        shown, rest = [paths[0]], list(paths[1:])
        while rest and len(", ".join([*shown, rest[0]])) + len(f" and {len(rest) - 1} more") <= WIDE:
            shown.append(rest.pop(0))
        lines.append("  " + ", ".join(shown) + (f" and {len(rest)} more" if rest else ""))
    if do:
        lines.append("  " + do)
    return Refused("\n".join(lines))


SAID_KEPT = 200  # the refusals remembered as said; the oldest is forgotten first


def first_time(store, who: Caller, node: Node, kind: str) -> bool:
    """Is this the first time this caller meets this refusal of this node, in this hold? A refusal
    lectures once and is short after that. Kept in the store's meta, keyed by who, the node, the
    hold's start and the kind; a caller refused inside a claim asks this before the claim, or the
    rollback forgets it."""
    key = f"{who.name}|{node.id}|{node.started_at or ''}|{kind}"
    said = json.loads(store.meta("said") or "[]")
    if key in said:
        return False
    store.set_meta("said", json.dumps([*said, key][-SAID_KEPT:]))
    return True


@dataclass(slots=True)
class Node:
    id: str
    title: str
    goal: str = ""
    scope: list[str] = field(default_factory=list)  # globs, repo-relative; "!glob" takes paths back out
    check: str | None = None  # a shell command that must exit 0, run by Graphene on the node's state
    signoff: bool = False  # a person must also say so
    needs: list[str] = field(default_factory=list)
    owner: str = AGENT
    parent: str | None = None  # the node this one helps achieve; None is directly under the plan's goal
    aside: bool = False  # made from what the person typed into a session, not planned beforehand
    state: str = OPEN
    rev: int = 1  # the contract's revision: goes up on every edit
    proposed_by: str | None = None
    executor: str | None = None  # who holds it, as they named themselves
    session_id: str | None = None  # the Claude Code session holding it, when that is who holds it
    agent_id: str | None = None
    checkout: str | None = None  # the working tree it runs in (a worktree is its own checkout)
    base_sha: str | None = None  # HEAD when it was started
    dirty_at_start: dict[str, str | None] = field(default_factory=dict)  # path -> content hash
    unseen_at_start: dict[str, str] = field(default_factory=dict)  # what git could not see then
    others_at_start: dict[str, dict] = field(default_factory=dict)  # the repo's other working trees then
    told_rev: int | None = None  # the revision the executor was shown when it started
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class Caller:
    """Who is asking. ``person`` is False inside an agent's shell, by the vendor's own environment."""

    name: str
    person: bool
    session_id: str | None = None
    stand_in: bool = False  # said who it is through GRAPHENE_AS, with no terminal to show for it

    @property
    def label(self) -> str:
        """The name as the log keeps it: a person's act made with no terminal says so, for ever."""
        return f"{self.name} (no terminal)" if self.person and self.stand_in else self.name


def caller(env: dict[str, str] | None = None, tty: bool | None = None) -> Caller:
    """An agent's shell says what it is (Codex exports CODEX_SESSION_ID, Claude Code CLAUDECODE and
    its session id, `graphene run` gives every executor GRAPHENE_NODE), and that outranks everything:
    a command that sets GRAPHENE_AS inside an agent's shell is still the agent's. Whoever carries no
    such mark is the person. Having no terminal does not change that: a person's command run from
    an editor task or a pipe must never turn into a proposal they then cannot accept. It is logged
    as made with no terminal, for ever, and that is the whole of what the terminal test decides.
    An agent that strips its own marks passes for a person: no command line can rule that out, the
    log shows it, and the hole is printed wherever a person-only control is described.
    GRAPHENE_WATCH=1 is `graphene watch`'s, on a command the person typed there that it runs as a
    process of its own (with no terminal): it was typed at the watch's terminal. It is read after
    every agent's mark and after GRAPHENE_AS, so it makes nobody a person who was not one; what it
    lets through is a caller with no terminal and no mark (a script, or an agent that stripped its
    own) that sets it: logged as at a terminal, without "(no terminal)"."""
    env = os.environ if env is None else env
    if env.get("CODEX_SESSION_ID") or env.get("CODEX_SANDBOX"):  # first: Codex may run inside Claude Code
        return Caller(f"codex:{env.get('CODEX_SESSION_ID', '?')[:8]}", False, None)
    sid = env.get("CLAUDE_CODE_SESSION_ID")
    if sid or env.get("CLAUDECODE"):
        return Caller(f"claude:{(sid or '?')[:8]}", False, sid)
    if env.get("AI_AGENT"):
        return Caller(env["AI_AGENT"], False, None)
    mark = next((m for m in AGENT_MARKS if env.get(m)), None)
    if mark:
        names = {"GRAPHENE_NODE": f"run:{env[mark]}", "GRAPHENE_PLANNER": "planner"}
        return Caller(names.get(mark, "an agent"), False, None)
    forced = env.get("GRAPHENE_AS")
    if forced:
        kind, _, name = forced.partition(":")
        return Caller(name or kind, kind == "person", None, stand_in=True)
    at_terminal = (sys.stdin.isatty() or env.get("GRAPHENE_WATCH") == "1") if tty is None else tty
    return Caller(person_name(env), True, None, stand_in=not at_terminal)


def person_name(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return (env.get("GRAPHENE_PERSON") or env.get("USER") or "me").lower()


# -- scope ----------------------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _pattern(glob: str) -> re.Pattern[str]:
    """``**`` crosses directories, ``*`` and ``?`` stay inside one; a name with no wildcard in it also
    covers everything beneath it, so ``src/api``, ``src/api/`` and ``src/api/**`` mean the same."""
    glob = glob.strip().removeprefix("./")
    if glob.endswith("/"):
        glob += "**"
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    last = glob.rsplit("/", 1)[-1]  # only a plain name covers what is beneath it: `src/*` is one level
    beneath = "" if any(c in last for c in "*?") else "(?:/.*)?"
    return re.compile("".join(out) + beneath + r"\Z")


def in_scope(path: str, scope: list[str]) -> bool:
    """Is this repo-relative path inside the scope? The last glob that matches decides, as in a
    .gitignore, so ``["src/**", "!src/db/**"]`` is src without its db directory."""
    inside = False
    for glob in scope:
        negated = glob.startswith("!")
        if _pattern(glob[1:] if negated else glob).match(path):
            inside = not negated
    return inside


def overlap(a: list[str], b: list[str], files: list[str]) -> list[str]:
    """Paths both scopes claim: the tracked files either matches, and a glob one scope spells that
    the other also covers. TODO: a file neither scope names literally and that does not exist
    yet is not seen; the write-time refusal still holds for it, since no scope is ever widened."""
    both = [f for f in files if in_scope(f, a) and in_scope(f, b)]
    literal = [g for g in a if not g.startswith("!") and in_scope(g.rstrip("/*") or g, b)]
    literal += [g for g in b if not g.startswith("!") and in_scope(g.rstrip("/*") or g, a)]
    return sorted(set(both + literal))


# -- the tree ---------------------------------------------------------------------------------------
#
# Hierarchy is meaning, edges are order. A node's ``parent`` says what it helps achieve; its
# ``needs`` say what must be finished first. A node with children is a sub-goal: nobody takes it, it
# is done when its children are (and its own check, if it has one, passes then). A node without
# children is a leaf: work someone does, with a scope and a check. The root is the plan's goal, in
# the person's words (``goal``); a flat plan from 0.3 is a tree whose nodes all sit under it.


def kids(nodes: list[Node], drawn: bool = False) -> dict[str | None, list[Node]]:
    """Each node's children that are still part of the plan, in the order they were added. A proposal
    binds nobody: a proposed child under an accepted node does not make that node a sub-goal (one
    `node add --parent` from an agent froze a leaf and its holder). ``drawn`` keeps them, for whoever
    prints the tree."""
    by_id = {n.id: n for n in nodes}
    out: dict[str | None, list[Node]] = {}
    for n in nodes:
        if n.state in GONE:
            continue
        parent = by_id.get(n.parent or "")
        if drawn or n.state != PROPOSED or parent is None or parent.state == PROPOSED:
            out.setdefault(n.parent, []).append(n)
    return out


def above(node: Node, by_id: dict[str, Node]) -> list[Node]:
    """The node's ancestors, nearest first. A parent cycle (refused by ``validate``) ends the walk."""
    out: list[Node] = []
    while node.parent in by_id and by_id[node.parent] not in out:
        node = by_id[node.parent]
        out.append(node)
    return out


def below(node_id: str, nodes: list[Node]) -> list[Node]:
    """Everything under a node, proposals included, parents before their children."""
    under = kids(nodes, drawn=True)
    out, queue = [], list(under.get(node_id, []))
    while queue:
        n = queue.pop(0)
        out.append(n)
        queue[:0] = under.get(n.id, [])
    return out


def leaves(nodes: list[Node]) -> list[Node]:
    under = kids(nodes)
    return [n for n in nodes if n.state not in GONE and not under.get(n.id)]


def all_needs(node: Node, by_id: dict[str, Node]) -> list[str]:
    """What a node waits on: its own needs, and those of everything above it."""
    out: list[str] = []
    for n in (node, *above(node, by_id)):
        out += [i for i in n.needs if i not in out]
    return out


def validate(nodes: list[Node], fresh: set[str] | None = None) -> None:
    """Refuse a plan that cannot run: an unknown parent or dependency, a cycle (through needs, through
    the tree, or through both), a leaf with nothing to touch or nothing to pass. The leaf rule is
    asked of ``fresh`` (what is being added or edited) only: a sub-goal whose children were all
    dropped is a node with a check and no scope, and it must not make every later edit fail."""
    by_id = {n.id: n for n in nodes if n.state not in GONE}
    under = kids(nodes, drawn=True)  # a proposed child still makes its parent a sub-goal to be
    for n in by_id.values():
        if not n.title.strip():
            raise Refused(f"{n.id}: a node needs a title")
        if fresh is None or n.id in fresh:
            _globs_ok(n)
            if "#" in n.owner:  # a name; the text reads what follows a # as a note
                raise Refused(f"{n.id}: an owner is a name ({n.owner!r} has a # in it)")
        if n.parent is not None and n.parent not in by_id:
            raise Refused(f"{n.id} is under {n.parent}, which is not in the plan")
        if n.parent is not None and by_id[n.parent].aside:
            raise Refused(f"{n.parent} was made from a prompt and is done as typed; it takes no children")
        for need in n.needs:
            if need not in by_id:
                raise Refused(f"{n.id} waits on {need}, which is not in the plan")
        if under.get(n.id) or not (n.scope or n.check or n.signoff or n.aside):
            continue
        if fresh is not None and n.id not in fresh:
            continue  # a sub-goal (or one whose children are still to come): they carry scope and check
        if not n.scope:
            raise Refused(
                f"{n.id}: a leaf needs a scope (the paths it may touch), e.g. --scope 'src/api/**'; "
                "or give it children, and it is a sub-goal"
            )
        if not n.check and not n.signoff and not n.aside:
            raise Refused(
                f"{n.id}: a leaf needs a check, a person's sign-off, or both; else nobody knows it is done"
            )
    seen: dict[str, int] = {}

    def visit(i: str, trail: tuple[str, ...]) -> None:
        if seen.get(i) == 2:
            return
        if seen.get(i) == 1:
            raise Refused(
                "the plan has a cycle: "
                + " -> ".join((*trail[trail.index(i) :], i))
                + " (a node waits on what it needs, on what the nodes above it need, and on its children)"
            )
        seen[i] = 1
        for nxt in (*all_needs(by_id[i], by_id), *(c.id for c in under.get(i, []))):
            visit(nxt, (*trail, i))
        seen[i] = 2

    for n in by_id.values():
        if n in above(n, by_id):
            raise Refused(f"the plan has a cycle: {n.id} is under itself")
    for i in by_id:
        visit(i, ())


def _globs_ok(node: Node) -> None:
    """A glob is refused when it is written if it could not be read back from the plan's text as it
    is, or if it means nothing to the matcher (braces, a word for none)."""
    for glob in node.scope:
        if not glob.strip() or len(glob.splitlines()) > 1 or any(ord(c) < 32 for c in glob):
            raise Refused(
                f"{node.id}: a scope glob is empty or has a line break or a control character in it"
            )
        if "{" in glob or "}" in glob:
            raise Refused(f"{node.id}: braces are not read in a scope ({glob}); list each glob instead")
        bare = glob.lstrip("!")
        if bare.startswith(("/", "~")) or ".." in bare.split("/"):
            raise Refused(f"{node.id}: a scope is a path inside the repo, from its top ({glob} is not)")
        if "`" in glob or glob.strip().lower() in ("none", "n/a", "-"):
            raise Refused(
                f"{node.id}: {glob!r} is not a path; a leaf with nothing to write has no leaf's work"
            )


def order(nodes: list[Node]) -> list[Node]:
    """Topological, stable: a node after everything it waits on, otherwise in the order given."""
    by_id = {n.id: n for n in nodes}
    out: list[Node] = []
    placed: set[str] = set()

    def place(n: Node) -> None:
        if n.id in placed:
            return
        placed.add(n.id)
        for need in n.needs:
            if need in by_id:
                place(by_id[need])
        out.append(n)

    for n in nodes:
        place(n)
    return out


def unmet(node: Node, by_id: dict[str, Node]) -> list[Node]:
    return [by_id[i] for i in all_needs(node, by_id) if i in by_id and by_id[i].state != DONE]


def ready(nodes: list[Node], who: Caller | None = None) -> list[Node]:
    """Open leaves with nothing left to wait on, under nothing still a proposal; for ``who``, only
    the ones they may take."""
    by_id = {n.id: n for n in nodes}
    out = [
        n
        for n in order(leaves(nodes))
        if n.state == OPEN
        and n.scope  # a sub-goal whose children are still to come is nobody's to take
        and not unmet(n, by_id)
        and all(a.state != PROPOSED for a in above(n, by_id))
    ]
    if who is not None:
        out = [n for n in out if may_take(n, who)]
    return out


def may_take(node: Node, who: Caller) -> bool:
    return node.owner == AGENT if not who.person else node.owner in (AGENT, who.name)


def waits_on_person(node: Node, by_id: dict[str, Node]) -> list[str]:
    """Why an agent cannot get to this node without a person, as readable reasons; empty when it
    can. A person's node, a sign-off and an unaccepted proposal each stop everything downstream."""
    reasons: list[str] = []
    seen: set[str] = set()
    under = kids(list(by_id.values()))

    def walk(n: Node) -> None:
        if n.id in seen or n.state == DONE:
            return
        seen.add(n.id)
        if n.state == PROPOSED:
            reasons.append(f"{n.id} is a proposal nobody has accepted")
        elif under.get(n.id):
            for child in under[n.id]:
                walk(child)
            if n.signoff and n.id != node.id:
                reasons.append(f"{n.id} needs a sign-off")
        elif n.owner != AGENT:
            reasons.append(f"{n.id} is {n.owner}'s")
        elif n.signoff and n.id != node.id:
            reasons.append(f"{n.id} needs a sign-off")
        for need in all_needs(n, by_id):
            if need in by_id:
                walk(by_id[need])

    reasons += [
        f"{a.id} is a proposal nobody has accepted" for a in above(node, by_id) if a.state == PROPOSED
    ]
    walk(node)
    return reasons


def forecast(nodes: list[Node]) -> tuple[list[Node], list[tuple[Node, list[str]]]]:
    """What an unattended run will do: the leaves agents can reach by themselves, in order, and the
    ones that will sit waiting, each with who it waits for. Said before the run, so that a plan that
    stops at a person's node at 01:00 surprises nobody at 08:00."""
    by_id = {n.id: n for n in nodes}
    runs, waits = [], []
    for n in order(leaves(nodes)):
        if n.state in (DONE, *GONE):
            continue
        why = [f"{n.id} waits for a sign-off"] if n.state == REVIEW else waits_on_person(n, by_id)
        if why:
            waits.append((n, why))
        else:
            runs.append(n)
    return runs, waits


# -- git: what changed since a node was started -------------------------------------------------------


def _git(checkout: str | Path, *args: str) -> str:
    # every call here is a read, and a read must not take the index lock: with leaves in worktrees of
    # their own, one node's look at the other trees (`git status`) met another's commit and broke it
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    out = subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, text=True, timeout=30, env=env
    )
    if out.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed in {checkout}: {out.stderr.strip()[:200]}")
    return out.stdout


def head(checkout: str | Path) -> str | None:
    try:
        return _git(checkout, "rev-parse", "HEAD").strip() or None
    except (Refused, OSError, subprocess.TimeoutExpired):
        return None  # a repo with no commit yet


def _hash(checkout: str | Path, path: str) -> str | None:
    import hashlib  # here: the hook imports this module on every event and never hashes anything

    try:
        return hashlib.sha1((Path(checkout) / path).read_bytes()).hexdigest()
    except OSError:
        return None  # deleted, or a directory


def dirty(checkout: str | Path) -> dict[str, str | None]:
    """Every path git calls modified, staged, deleted or untracked right now, with its content hash,
    so that a later look can tell "was already like that" from "changed since"."""
    out = _git(checkout, "status", "--porcelain", "-z", "--untracked-files=all")
    paths, fields = [], out.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":  # a rename or copy carries its source as the next field
            if i < len(fields) and fields[i]:
                paths.append(fields[i])
            i += 1
    return {p: _hash(checkout, p) for p in paths}


def tracked(checkout: str | Path) -> list[str]:
    try:
        return [p for p in _git(checkout, "ls-files", "-z").split("\0") if p]
    except (Refused, OSError, subprocess.TimeoutExpired):
        return []


def changed_since(
    checkout: str | Path, base_sha: str | None, dirty_at_start: dict[str, str | None]
) -> list[str]:
    """Paths whose content differs from when the node was started: committed since, or changed in
    the working tree, however they were written. A path that was already dirty then counts only if
    it has changed again. A file git did not track then and that is gone now, and not by a commit, is
    not a change: the tree is back to what git has (an executor that deletes a cache a check left,
    as a refusal told it to, was refused for deleting it)."""
    changed: set[str] = set(dirty_at_start)
    committed: set[str] = set()
    if base_sha:
        committed = {
            p for p in _git(checkout, "diff", "--name-only", "-z", base_sha, "HEAD").split("\0") if p
        }
    changed |= committed
    now = dirty(checkout)
    changed.update(now)
    gone = {p for p in dirty_at_start if p not in now and p not in committed}
    if gone and base_sha:
        gone -= set(_git(checkout, "ls-tree", "-r", "-z", "--name-only", base_sha).split("\0"))
    return sorted(
        p
        for p in changed
        if p not in gone and (p not in dirty_at_start or _hash(checkout, p) != dirty_at_start[p])
    )


@contextmanager
def ctrl_c_on_hangup():
    """A closed terminal (SIGHUP) or a `kill` (SIGTERM) is taken as Ctrl-C while this lasts, so what
    must not be left behind (a check and what it started; a run's executors, leaves and lock) is
    ended before the process goes: left to the defaults, it died where it stood, and they worked on
    unattended. Once the terminal is gone, what is said goes nowhere rather than failing the
    cleanup half done. Only the main thread is told of a signal; elsewhere this does nothing."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def hung_up(signum, _frame):
        if signum == signal.SIGHUP:
            nowhere = os.open(os.devnull, os.O_WRONLY)
            os.dup2(nowhere, 1)
            os.dup2(nowhere, 2)
        raise KeyboardInterrupt

    # SIGINT too: started from a shell that ignores it (a job in the background, a CI step), the
    # process inherits the ignoring, and neither Ctrl-C nor `:stop` would ever reach it
    was = {sig: signal.signal(sig, hung_up) for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)}
    try:
        yield
    finally:
        for sig, handler in was.items():
            signal.signal(sig, handler)


_checks: set[subprocess.Popen] = set()  # what the checks are running now; a run that is stopped ends it
_stopped = float("-inf")  # when a run last ended its checks: every check begun before is stopped


def _ended(
    args: str | list[str], cwd: str | Path, env: dict, began: float, given: str | None = None
) -> tuple[int, str, str]:
    """Run a step of the check begun at ``began`` (the check itself, a string bash runs, or one of
    git's, a list): its exit code and what it said on stdout and on stderr. It runs in a session of
    its own and is ended with everything it started when the check's time is up (TimeoutExpired), on
    a Ctrl-C, a closed terminal or a `kill`, and when a run is stopped (``end_checks``), which says
    nothing of the work, so it is not taken as a result (KeyboardInterrupt), whether the stop came
    while it ran or before it started. Killing bash alone had left its `sleep` running; killing git
    alone left the `git reset` it had started writing a worktree after the check was over; a stop
    that came while the worktree was being made was lost, and the check ran to its end; and a
    terminal's Ctrl-C that reached the check itself had been recorded as the executor's failed check."""
    shell = isinstance(args, str)
    with subprocess.Popen(
        args,
        shell=shell,
        executable=BASH if shell else None,  # people write bash (`[[ ]]`, `set -o pipefail`); else sh
        cwd=cwd,
        stdin=None if given is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    ) as proc:
        _checks.add(proc)
        try:
            if began <= _stopped:
                _end_check(proc)
            out, err = proc.communicate(given, timeout=max(began + CHECK_TIMEOUT - time.monotonic(), 0))
        except BaseException:
            _end_check(proc)
            raise
        finally:
            _checks.discard(proc)
    if began <= _stopped:
        raise KeyboardInterrupt
    return proc.returncode, out, err


@contextmanager
def _clean_tree(checkout: str | Path, leave_out: list[str] | tuple, began: float):
    """A worktree of ``checkout`` as git sees it now, whether committed or not (what it tracks, as it
    is on disk, and the new files it does not ignore), but for ``leave_out``: cut from a commit on no
    branch, under the run's own worktrees (which ``elsewhere`` never asks about), and removed when
    the block ends, however it ends. Making it is a part of the check (``_ended``: its time, its stop)
    and runs none of the person's git hooks (a post-checkout hook that failed made every check "could
    not be run"). What git ignores is not there: a .venv linked in from the checkout was the check's
    to change, and `uv run` in the worktree re-installed the project into it, pointing the checkout's
    .venv at a worktree that was then deleted."""
    import shutil  # here: the hook imports this module on every event and never runs a check
    import tempfile

    def git(*args: str, index: Path | None = None, given: str | None = None) -> str:
        # ``index`` is the check's own, so the checkout's index lock is never taken
        env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", **({"GIT_INDEX_FILE": str(index)} if index else {})}
        argv = ["git", "-c", "core.hooksPath=/dev/null", "-C", str(checkout), *args]
        code, out, err = _ended(argv, checkout, env, began, given)
        if code:
            raise Refused(f"git {' '.join(args)} failed in {checkout}: {err.strip()[:200]}")
        return out

    common, had = git("rev-parse", "--git-common-dir", "--git-path", "index").splitlines()
    trees = Path(checkout, common).parent / ".graphene" / "worktrees"
    trees.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".check-", dir=trees))
    tree, index = tmp / "tree", tmp / "index"
    try:
        # a copy of the checkout's index, so what git tracks is taken as git has it (a tracked file an
        # ignore rule matches, a sparse checkout's), and then everything else git sees on disk
        with suppress(OSError):  # a repo where nothing was ever added has no index yet
            shutil.copyfile(Path(checkout, had), index)
        git("add", "-A", index=index)
        if leave_out:
            out = "".join(f"{p}\0" for p in leave_out)
            git("update-index", "-z", "--force-remove", "--stdin", index=index, given=out)
        state, base = git("write-tree", index=index).strip(), head(checkout)
        nobody = ("-c", "user.name=graphene", "-c", "user.email=graphene@localhost")  # on no branch
        commit = git(*nobody, "commit-tree", state, *(("-p", base) if base else ()), "-m", "check")
        # ponytail: a whole checkout per check, which grows with the repository; a kept worktree moved
        # to each commit (`git checkout --detach`) if a large repository needs it
        git("worktree", "add", "--quiet", "--detach", str(tree), commit.strip())
        yield tree
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        # then git's record of it; twice forced: a worktree whose making was stopped is locked
        with suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["git", "-C", str(checkout), "worktree", "remove", "--force", "--force", str(tree)],
                capture_output=True,
                timeout=30,
            )


@ctrl_c_on_hangup()
def run_check(
    command: str, checkout: str | Path, leave_out: list[str] | tuple = ()
) -> tuple[bool, str, list[str]]:
    """Run a check on the state of ``checkout``: whether it passed, the tail of what it said, and
    which of ``leave_out`` (new files, left out of what it runs on) it made again. This is the one
    place Graphene runs a check. Graphene runs it, not the executor: "it passed" is then a fact about
    the repo and not a sentence in somebody's summary. It runs in a clean worktree of that state
    (``_clean_tree``), never in the checkout itself: run in place, a check left its caches in the
    executor's tree, to be counted as its change and committed with its leaf. Its time limit and its
    stop (``_ended``) are the whole of it, the making of that worktree included."""
    began = time.monotonic()
    # Whatever the check starts is not the person, terminal or none: pytest takes the terminal away
    # from the tests it runs, and a test file is something an executor writes inside its own scope.
    env = {**os.environ, "GRAPHENE_AS": "agent:check"}
    try:
        with _clean_tree(checkout, leave_out, began) as tree:
            code, out, err = _ended(command, tree, env, began)
            made = [p for p in leave_out if os.path.lexists(tree / p)]
    except subprocess.TimeoutExpired:
        return False, f"timed out after {CHECK_TIMEOUT} s", []
    except (Refused, OSError) as no:  # it never ran, which is no pass
        return False, f"the check could not be run: {no}", []
    text = (out + err).strip()
    return code == 0, (text[-TAIL:] if text else f"exit {code}, no output"), made


def end_checks() -> None:
    """End every check running in this process (a stopped parallel run's are in its worker threads,
    where no Ctrl-C lands), and every one begun before now that is still making its worktree; each
    then says it was stopped instead of giving a result."""
    global _stopped
    _stopped = time.monotonic()
    while _checks:
        _end_check(_checks.pop())


def _end_check(proc: subprocess.Popen) -> None:
    with suppress(OSError):  # the group outlives bash while anything it started is still running
        os.killpg(proc.pid, signal.SIGKILL)


# -- the operations -------------------------------------------------------------------------------


def contract(node: Node, why: list[str] | None = None) -> str:
    """The node as its executor is told it: the whole of what they are bound to, and why it is being
    done at all (``trail``: from the plan's goal down to this node, in the person's words)."""
    lines = [
        f"{node.id} (revision {node.rev}): {node.title}",
        *(f"  {'why:' if k == 0 else '    '}    {'  ' * k}{line}" for k, line in enumerate(why or [])),
        f"  goal:   {node.goal or node.title}",
        f"  scope:  {', '.join(node.scope)}   (a write anywhere else is refused, and blocks `done`)",
        *(
            [f"  needs:  {', '.join(node.needs)}   (it cannot start until they are done)"]
            if node.needs
            else []
        ),
        f"  done:   {done_means(node)}",
        f"  finish: graphene node done {node.id}   (runs the check and asks git what changed)",
        f"  stuck:  graphene node release {node.id} --why '<what is in the way>' [--wants <paths it needs>]"
        "   (hands it back; say why)",
    ]
    return "\n".join(lines)


def trail(store, node: Node) -> list[str]:
    """The path from the root to the node, one line a level: the plan's goal, then each sub-goal
    above the node with its own goal when it has one. What every executor is told."""
    by_id = {n.id: n for n in nodes(store)}
    lines = [goal(store)] if goal(store) else []
    for a in reversed(above(node, by_id)):
        lines.append(f"{a.title} ({a.id})" + (f": {a.goal}" if a.goal and a.goal != a.title else ""))
    return lines


def done_means(node: Node) -> str:
    parts = [f"`{node.check}` passes" if node.check else ""]
    parts.append(f"{'and ' if node.check else ''}a person signs it off" if node.signoff else "")
    return " ".join(p for p in parts if p)


def from_dict(raw: dict, fallback_id: str) -> Node:
    """One node from a proposal's JSON. Unknown keys are refused, so a typo is not a silent default."""
    if not isinstance(raw, dict):
        raise Refused("a node is a JSON object with at least a title, a scope and a check")
    unknown = set(raw) - {"id", "children", *EDITABLE}
    if unknown:
        raise Refused(
            f"unknown field{'s' if len(unknown) > 1 else ''} {', '.join(sorted(unknown))}; "
            f"a node has: id, {', '.join(EDITABLE)}"
        )
    scope = raw.get("scope") or []
    needs = raw.get("needs") or []
    owner = " ".join(str(raw.get("owner") or AGENT).split()) or AGENT  # one line, as the text writes it
    return Node(
        id=str(raw.get("id") or fallback_id),
        title=str(raw.get("title") or ""),
        goal=str(raw.get("goal") or ""),
        scope=[scope] if isinstance(scope, str) else [str(s) for s in scope],
        check=str(raw["check"]).strip() or None if raw.get("check") else None,  # blank is no check
        signoff=bool(raw.get("signoff")),
        needs=[needs] if isinstance(needs, str) else [str(n) for n in needs],
        owner=owner,
        parent=str(raw["parent"]) if raw.get("parent") not in (None, "", "none") else None,
    )


def to_dict(node: Node) -> dict:
    return {f: getattr(node, f) for f in Node.__slots__}


def to_json(nodes: list[Node]) -> str:
    return json.dumps({"nodes": [to_dict(n) for n in order(nodes)]}, indent=2)


# -- the operations: every one is a row changed and a line in the node's log ---------------------------


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def nodes(store, states: tuple[str, ...] | None = None) -> list[Node]:
    return [Node(**row) for row in store.node_rows(states)]


def get(store, node_id: str) -> Node:
    row = store.node_row(node_id)
    if row is None:
        known = ", ".join(n.id for n in nodes(store)) or "none yet"
        raise Refused(f"no node {node_id} in the plan (nodes: {known})")
    return Node(**row)


def _save(store, node: Node, kind: str, who: Caller, now: str, **detail) -> None:
    node.updated_at = now
    store.put_node(to_dict(node))
    store.log_node(node.id, now, kind, who.label, who.session_id, node.agent_id, detail or None)


def _under_hands(held: Node, child: str | None = None) -> Refused:
    """A child under a running leaf would make it a sub-goal while its executor works on it."""
    return refusal(
        f"{child + ' would make ' if child else 'a child would make '}{held.id} a sub-goal while "
        f"{held.executor} holds it",
        do=f"they hand it back first: graphene node release {held.id} --why '…'",
    )


def _person_only(who: Caller, what: str) -> None:
    if not who.person:
        raise refusal(
            f"{what} is the person's to do, and this call comes from {who.name}",
            do="say what you need and why; they decide",
        )


def goal(store) -> str:
    """The root of the tree: why any of this is being done, in the person's words."""
    return store.meta("goal") or ""


def set_goal(store, text: str, who: Caller, now: str | None = None) -> None:
    _person_only(who, "saying what the plan is for")
    was = goal(store)  # kept in the log: a goal set in the wrong repo can be put back word for word
    store.set_meta("goal", text.strip())
    store.set_meta("goal:proposed", None)  # the person's own words replace a planner's
    store.log_node("*", now or _now(), "goal", who.label, None, None, {"note": text.strip(), "was": was})


_KINDS = "py js ts tsx json toml yaml yml md txt sh xml csv html css rs go rb java c h cfg ini sql"
_EXTENSIONS = tuple(f".{e}" for e in _KINDS.split())


_BUILT = ("dist/", "build/", "out/", "target/", "node_modules/", ".venv/", "coverage/")


def unreachable(
    node: Node, files: list[str], root: str | Path, everything: list[Node] | tuple = ()
) -> list[str]:
    """Paths a leaf's check names that are neither in the repo nor inside a scope that may still write
    them: its own, its needs', or that of a node in ``everything`` (the plan) that is open, running or
    proposed. A finished leaf writes nothing more, and the `**` of a leaf made from a prompt would
    cover every typo. It is a guess (a person typed `test/test_csvfeed.py` for `tests/`), said when the
    leaf is written, before anything is spent. A path on disk that git does not track comes back
    marked, because a worktree cut for `--parallel` will not have it. A check that changes directory
    (cd, pushd, `--prefix`, `-C <dir>`), and what a build makes, are not judged."""
    moves = r"(^|[;&|(\s])(cd|pushd)\s|--prefix[\s=]|(^|\s)-C\s"
    if not node.check or not node.scope or re.search(moves, node.check):
        return []
    live = (OPEN, RUNNING, PROPOSED)
    covered = [
        g
        for n in everything
        if n.id != node.id and (n.id in node.needs or n.state in live)
        for g in n.scope
        if g != "**"
    ]
    out: list[str] = []
    for word in re.findall(r"[\w./-]+", node.check):
        word = word.removeprefix("./").rstrip(".")
        if word.startswith(("/", "-", ".")) or ("/" not in word and not word.endswith(_EXTENSIONS)):
            continue
        if word in out or word.startswith(_BUILT) or in_scope(word, [*node.scope, *covered]):
            continue
        if any(f == word or f.startswith(word.rstrip("/") + "/") for f in files):
            continue
        if os.path.exists(os.path.join(root, word)):
            out.append(f"{word} (on disk, not committed)")
            continue
        if re.search(rf"\w:/*{re.escape(word)}", node.check):
            continue  # part of an address (host:8000/api)
        out.append(word)
    return out


def unreachable_said(missing: list[str]) -> str:
    """What ``unreachable`` found, said as the guess it is, the same at the command line and on screen."""
    one = len(missing) == 1
    return (
        f"names {', '.join(missing)}, which {'is' if one else 'are'} not in the repo and no leaf's scope may "
        f"create {'it' if one else 'them'}: check the spelling"
    )


def _owner(name: str) -> str:
    """An owner as the one it names: 'Agent' is the agent, 'Me' is me, and the person's own name in
    any case is the person; else as written."""
    low = name.lower()
    return low if low in (AGENT, "me", person_name()) else name


def propose_goal(store, text: str, who: Caller, now: str | None = None) -> bool:
    """A planner's one sentence for the root, from the person's paragraph. It is used only while
    the plan has no goal of the person's in force: none yet, or one whose tree is finished (something
    was finished since it was set, and nothing is open, running or waiting for a sign-off; a goal with
    nothing finished under it yet is the person's word for what is to come). A finished one is put
    aside, kept in the log, so the sentence shows everywhere as the proposal it is; it becomes the
    goal when the person accepts any of the tree. True when it was taken."""
    was = goal(store)
    if was:
        said = (store.node_log("*", ("goal",)) or [{"timestamp": ""}])[-1]["timestamp"]
        ended = store.node_log(kinds=("finished", "overruled", "rolled_up"))
        if store.node_rows((OPEN, RUNNING, REVIEW)) or not any(e["timestamp"] > said for e in ended):
            return False  # the person's own words are never replaced while anything under them is to do
        store.set_meta("goal", None)
    store.set_meta("goal:proposed", text.strip())
    store.set_meta("goal:proposed:by", who.label)
    detail = {"note": text.strip(), **({"was": was} if was else {})}
    store.log_node("*", now or _now(), "goal_proposed", who.label, who.session_id, None, detail)
    return True


def wanted(store, node: Node) -> list[str]:
    """The paths outside its scope that the node's last holder tried to write, as Graphene saw them:
    a write the hook refused, a change `done` refused, or what was changed when it was handed back.
    The hand-back's offers are made of these: widen the scope to them, or a sibling leaf for them."""
    log = store.node_log(node.id)
    last = max((k for k, e in enumerate(log) if e["kind"] == "started"), default=-1)
    out: list[str] = []
    for e in log[last + 1 :]:
        d = e["detail"]
        if e["kind"] == "denied" and d.get("path"):
            found = [d["path"]]
        elif e["kind"] in ("refused", "breach"):
            found = [p.split(" (in the worktree ")[0] for p in d.get("outside") or d.get("paths") or []]
        elif e["kind"] == "released":
            found = [*(d.get("wants") or []), *(d.get("changed") or [])]  # what it said it needs, first
        else:
            continue
        out += [
            p
            for p in found
            if p not in out and not in_scope(p, node.scope) and p.split("/")[0] not in (".graphene",)
        ]
    return out


def offerable(store, node: Node, everything: list[Node] | None = None) -> list[str]:
    """What it wanted that a widen or a sibling can take: not what a node it waits on already may
    write, and nothing a scope cannot hold (braces, `~`, a path from `/`). The offer shows these and
    the command takes these, so an offer is never refused when taken."""
    everything = nodes(store) if everything is None else everything
    by_id = {n.id: n for n in everything}
    waited = [g for i in all_needs(node, by_id) if i in by_id for g in by_id[i].scope]
    return [
        p for p in wanted(store, node)
        if not in_scope(p, waited) and not any(c in p for c in "{}~") and not p.startswith("/")
    ]  # fmt: skip


def offers(store, node: Node) -> list[tuple[str, str, list[str]]]:
    """What a leaf that came back offers the person, as (key in `graphene watch`, what it does, the
    command that does it): widen its scope to the paths it wanted, a sibling leaf for those paths,
    or make it wait on the nodes its reason names. Each is a command that exists on its own."""
    last = (store.node_log(node.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
    if node.state != OPEN or last["kind"] != "released":
        return []
    out: list[tuple[str, str, list[str]]] = []
    everything = nodes(store)
    by_id = {n.id: n for n in everything}
    paths = offerable(store, node, everything)
    if paths:
        listed = ", ".join(paths[:3]) + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")
        out.append(("w", f"widen {node.id}'s scope to {listed}", ["node", "widen", node.id]))
        out.append(("b", f"a sibling leaf for {listed}; {node.id} waits on it", ["node", "sibling", node.id]))
    family = {a.id for a in above(node, by_id)} | {c.id for c in below(node.id, everything)}
    why = str(last["detail"].get("why", ""))
    candidates = [
        n.id
        for n in everything
        if n.id != node.id
        and n.id not in family
        and n.state not in (DONE, *GONE)
        and n.id not in all_needs(node, by_id)
        and re.search(rf"(?<![\w.-]){re.escape(n.id)}(?![\w-])", why)
    ]

    def acyclic(ids: list[str]) -> bool:  # waiting on them must not make a cycle
        trial = [
            Node(**{**to_dict(x), "needs": [*x.needs, *ids]}) if x.id == node.id else x for x in everything
        ]
        try:
            validate(trial, set())
        except Refused:
            return False
        return True

    # one check for all of them, the usual case; one each only when that fails (a reason naming 100
    # nodes of 300 cost a validate each, on every refresh of the screen)
    named = candidates if not candidates or acyclic(candidates) else [i for i in candidates if acyclic([i])]
    if named:
        argv = ["node", "set", node.id, *(x for i in [*node.needs, *named] for x in ("--needs", i))]
        out.append(("n", f"make {node.id} wait on {', '.join(named)}", argv))
    return out


def widen(store, node_id: str, paths: list[str], who: Caller, files: list[str] | None = None) -> Node:
    """The first offer: the leaf's scope takes in the paths it wanted (or the ones named)."""
    node = get(store, node_id)
    paths = paths or offerable(store, node)
    if not paths:
        raise Refused(f"nothing {node_id} wanted outside its scope is on record; name the paths")
    return edit(store, node_id, {"scope": [*node.scope, *(p for p in paths if p not in node.scope)]}, who,
                files=files)  # fmt: skip


def sibling(store, node_id: str, paths: list[str], who: Caller, files: list[str] | None = None) -> Node:
    """The second offer: a leaf beside it for the paths it wanted, which it then waits on. Its own
    check only says that something there changed; the first leaf's check, run after it, says whether
    the two work together, which is the question that was open."""
    _person_only(who, "adding a sibling leaf")
    node = get(store, node_id)
    paths = paths or offerable(store, node)
    if not paths:  # asked twice: the first sibling's scope already has what it wanted
        raise Refused(
            f"nothing {node_id} wanted is outside its scope and the scopes it waits on; name the paths"
        )
    taken = {n.id for n in nodes(store)}
    stem = re.sub(r"[^A-Za-z0-9]+", "-", Path(paths[0]).stem).strip("-") or "more"
    new_id, k = f"{node.id}-{stem}"[:32].rstrip(".-"), 2
    while new_id in taken:
        new_id, k = f"{node.id}-{stem}"[:29].rstrip(".-") + f"-{k}", k + 1
    why = (store.node_log(node.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get("why", "")
    item = {
        "id": new_id,
        "title": f"what {node.id} needs in {', '.join(paths[:2])}" + (" and more" if len(paths) > 2 else ""),
        "goal": f"{node.id} ({node.title}) came back: {why}\nThis leaf makes that change; {node.id}'s check, "
        "run after it, says whether the two work together.",
        "scope": paths,
        "check": "true",
        "parent": node.parent,
    }
    with store.claim():
        [made] = propose(store, [item], who, files=files)
        edit(store, node.id, {"needs": [*node.needs, made.id]}, who, files=files)
    return made


def paused(store) -> bool:
    return store.meta("paused") == "1"


def in_force(store) -> bool:
    """Is there a plan an executor is bound to right now?"""
    return not paused(store) and bool(store.node_rows(LIVE))


def miscased(scope: list[str], files: list[str]) -> str | None:
    """A glob that matches nothing git tracks as spelled and something when case is ignored, with
    the path it nearly matched. On a filesystem that ignores case the hook would allow the write (it
    judges the spelling) and `done` would refuse it (git's spelling differs): better said now."""
    for glob in scope:
        if glob.startswith("!") or any(in_scope(f, [glob]) for f in files):
            continue
        near = next((f for f in files if in_scope(f.lower(), [glob.lower()])), None)
        if near:
            return (
                f"`{glob}` matches nothing git tracks, and `{near}` differs from it only in upper and "
                "lower case"
            )
    return None


def propose(
    store,
    raw: list[dict],
    who: Caller,
    now: str | None = None,
    files: list[str] | None = None,
    aside: bool = False,
    proposals: frozenset[str] | set[str] = frozenset(),
    containers: frozenset[str] | set[str] = frozenset(),
) -> list[Node]:
    """Add nodes. From a person they are part of the plan at once; from an agent they are proposals,
    which nobody can start until a person accepts them. ``proposals``: ids a person wrote as
    proposals themselves (a "?" line in the text), which stay proposals."""
    now = now or _now()
    with store.claim():
        existing = nodes(store)
        taken = {n.id for n in existing}
        added: list[Node] = []
        flat: list[tuple[dict, str | None]] = [(item, None) for item in raw]
        while flat:  # a proposal is a subtree: a node's "children" are added under it, in order
            item, under = flat.pop(0)
            k = len(taken) + 1
            while f"n{k}" in taken:
                k += 1
            node = from_dict(item, f"n{k}")
            node.parent = under or node.parent
            node.aside = aside
            if isinstance(item.get("children"), list):
                flat[:0] = [(child, node.id) for child in item["children"]]
            if node.id in taken:
                raise refusal(
                    f"{node.id} is already in the plan", do=f"graphene node set {node.id} … edits it"
                )
            bad = ".." in node.id or node.id.endswith((".", ".lock"))  # graphene/<id> is a branch name
            if bad or not re.fullmatch(r"[A-Za-z0-9][\w.-]{0,31}", node.id):
                raise Refused(
                    f"{node.id!r} is not a usable id: letters, digits, '-', '_' and '.', at most 32, "
                    "no '..', and not ending in '.' or '.lock'"
                )
            taken.add(node.id)
            node.owner = _owner(node.owner)
            if not who.person and node.owner not in (AGENT, "me", person_name()):
                raise Refused(
                    f"{node.id}: its owner is a person's name, and {node.owner!r} is not the person here. An "
                    "agent's node has no owner; owner 'me' is the person"
                )
            if node.owner == "me":
                node.owner = who.name if who.person else person_name()
            node.state = OPEN if who.person and node.id not in proposals else PROPOSED
            node.proposed_by = who.name
            node.created_at = now
            added.append(node)
        # ``containers``: new nodes the same text gives children (existing nodes moved under them come
        # after): they are sub-goals, and the leaf rule is asked of the tree once they are in place
        validate(existing + added, {n.id for n in added} - set(containers))
        held = {n.id: n for n in existing if n.state == RUNNING}
        for node in added:
            if node.state == OPEN and node.parent in held:
                raise _under_hands(held[node.parent])
        for node in added:
            wrong = miscased(node.scope, files or [])
            if wrong:
                raise Refused(f"{node.id}: {wrong}; spell the scope as git does")
        for node in added:
            _save(store, node, "added" if who.person else "proposed", who, now)
        _settle(store, who, now)
    return added


def accept(
    store, ids: list[str], who: Caller, now: str | None = None, exact: bool = False, **detail
) -> list[Node]:
    """``exact``: the nodes named and the proposals above them, not the ones under them (the text
    form says each node's mark, so a child left as a proposal stays one)."""
    _person_only(who, "accepting a proposal")
    now = now or _now()
    with store.claim():
        everything = nodes(store)
        by_id = {n.id: n for n in everything}
        named = [get(store, i) for i in ids] if ids else nodes(store, (PROPOSED,))
        chosen: list[Node] = []
        for node in named:
            # accepting a node accepts the proposals under it, and the proposals it sits under: a
            # subtree is accepted as one, and a leaf is never in the plan without its why
            family = [*reversed(above(node, by_id)), node, *([] if exact else below(node.id, everything))]
            fresh = [by_id[n.id] for n in family if n.state == PROPOSED and n not in chosen]
            if not fresh and node not in chosen:
                raise Refused(f"{node.id} is {node.state}, not a proposal")
            chosen += fresh
        for node in chosen:
            parent = by_id.get(node.parent or "")
            if parent is not None and parent.state == RUNNING:
                raise _under_hands(parent, node.id)
            node.state = OPEN
            _save(store, node, "accepted", who, now, **detail)
        proposed_goal, by = store.meta("goal:proposed"), store.meta("goal:proposed:by")
        if proposed_goal and any(n.proposed_by == by for n in chosen) and not goal(store):
            set_goal(store, proposed_goal, who, now)  # the planner's echo of the paragraph, with its tree
        _settle(store, who, now)
    return chosen


def edit(
    store,
    node_id: str,
    changes: dict,
    who: Caller,
    now: str | None = None,
    files: list[str] | None = None,
    check: bool = True,
) -> Node:
    """Change a node's contract. The hook reads the row on every event, so a tighter scope binds the
    very next write, even on a node that is running; what waits to start is told the new contract."""
    _person_only(who, "editing a node's contract")
    now = now or _now()
    with store.claim():
        node = get(store, node_id)
        if node.state in (DONE, *GONE):
            if node.state != DONE:
                raise Refused(f"{node.id} is {node.state}: it is not in the plan any more")
            raise refusal(
                f"{node.id} is done, and a finished node's contract is not edited",
                do=f"graphene node reopen {node.id} --note '…' opens it again",
            )
        fresh = from_dict({**{f: getattr(node, f) for f in EDITABLE}, **changes, "id": node.id}, node.id)
        fresh.owner = _owner(fresh.owner)
        if fresh.owner == "me":
            fresh.owner = who.name
        before = {f: getattr(node, f) for f in EDITABLE}
        for f in EDITABLE:
            setattr(node, f, getattr(fresh, f))
        changed = {f: [before[f], getattr(node, f)] for f in EDITABLE if before[f] != getattr(node, f)}
        if not changed:
            return node
        if check:  # else the caller validates once every edit it makes is in (a text saved whole)
            validate([node if n.id == node.id else n for n in nodes(store)], {node.id})
        target = next((n for n in nodes(store) if n.id == node.parent), None)
        if "parent" in changed and target is not None and target.state == RUNNING:
            raise _under_hands(target)
        wrong = miscased(node.scope, files or []) if "scope" in changed else None
        if wrong:
            raise Refused(f"{node.id}: {wrong}; spell the scope as git does")
        node.rev += 1
        _save(store, node, "edited", who, now, changed=changed, rev=node.rev)
        _settle(store, who, now)
    return node


def drop(store, node_id: str, who: Caller, now: str | None = None, waiting: bool = True) -> Node:
    """Take a node out of the plan, with everything under it. ``waiting``: refuse when a node left in
    the plan waits on it (a caller dropping several at once asks that of all of them together)."""
    now = now or _now()
    with store.claim():
        node = get(store, node_id)
        everything = nodes(store)
        going = [node, *below(node.id, everything)]  # a sub-goal goes with everything under it
        if not who.person and any(n.state != PROPOSED for n in going):
            _person_only(who, "dropping an accepted node")
        held = [n for n in going if n.state == RUNNING]
        if held and not who.person:
            raise refusal(
                f"{held[0].id} is running ({held[0].executor})",
                do=f"graphene node release {held[0].id} --why '…' first",
            )
        gone = {n.id for n in going}
        left = [n for n in everything if n.id not in gone and gone & set(n.needs) and n.state not in GONE]
        if left and waiting:
            told = "; ".join(f"{n.id} waits on {', '.join(sorted(gone & set(n.needs)))}" for n in left)
            raise Refused(f"{told}; change what {'it needs' if len(left) == 1 else 'they need'} first")
        for n in going:
            n.state = DROPPED
            _save(store, n, "dropped", who, now)
        by = store.meta("goal:proposed:by")
        if store.meta("goal:proposed") and not any(n.proposed_by == by for n in nodes(store, (PROPOSED,))):
            store.set_meta("goal:proposed", None)  # the planner's tree is gone, and its sentence with it
        _settle(store, who, now)
    return node


def _boundary(store, checkout: str) -> dict | None:
    raw = store.meta(f"boundary:{checkout}")
    return json.loads(raw) if raw else None


def mark_boundary(store, checkout: str | Path, now: str | None = None) -> None:
    """Remember the tree as it stands when a node closes (or when the person says it is fine as it
    is). Whatever differs from this at the next start was changed while no node owned it."""
    checkout = str(Path(checkout).resolve())
    snapshot = {"at": now or _now(), "head": head(checkout), "dirty": dirty(checkout)}
    store.set_meta(f"boundary:{checkout}", json.dumps(snapshot))


def _blobs(checkout: str | Path, paths: list[str]) -> dict[str, str]:
    """Git's name for the content of each path as it is on disk now (deleted paths are left out)."""
    present = [p for p in paths if os.path.isfile(os.path.join(checkout, p))]
    if not present:
        return {}
    try:
        names = _git(checkout, "hash-object", "--", *present).split()
    except (Refused, OSError, subprocess.TimeoutExpired):
        return {}
    return dict(zip(present, names, strict=False))


def _reaches(
    checkout: str | Path,
    blobs: dict[str, str],
    worktree_too: bool,
    since: str | None = None,
    base: str | None = None,
) -> list[str]:
    """The paths whose content a finished leaf left that this checkout does not have: not in its
    files (when ``worktree_too``), never in its history, and not committed after the leaf finished
    (``since``) on top of the HEAD it finished on (``base``). A file built on before any commit (by
    a later leaf, the person, a formatter) never reaches history as the leaf left it, and its
    dependant waited for ever."""
    missing = []
    now = _blobs(checkout, list(blobs)) if worktree_too else {}
    for path, blob in blobs.items():
        if now.get(path) == blob:
            continue
        try:
            seen = _git(
                checkout, "log", "-1", "--format=%H", f"--find-object={blob}", "HEAD", "--", path
            ).strip()
            if not seen and since:  # the range keeps out its own base, which may share that second
                after = [f"--since={since}", f"{base}..HEAD" if base else "HEAD"]
                seen = _git(checkout, "log", "-1", "--format=%H", *after, "--", path).strip()
        except (Refused, OSError, subprocess.TimeoutExpired):
            seen = "?"
        if not seen:
            missing.append(path)
    return missing


def unowned(store, checkout: str | Path, but: str | None = None) -> list[str]:
    """Uncommitted changes in this checkout that were not there, as they are, at the last boundary,
    and that no node can answer for: outside the scope of every node started since then. An executor
    that finishes its node inside the scope and then does the rest "after the audited window closed"
    lands here. Only the working tree is compared: a commit (the person's, or pulled) is the
    repository moving, and the plan follows it; a person's `.gitignore`, committed, had blocked every
    start. TODO: the hole this opens is that an agent that commits what it wrote between leaves is
    not seen here; it is written down, not guarded."""
    checkout = str(Path(checkout).resolve())
    mark = _boundary(store, checkout)
    if mark is None:
        return []
    since = [
        n
        for n in nodes(store)
        if n.id != but and n.checkout == checkout and (n.started_at or "") >= mark["at"]
    ]
    changed = sorted(p for p, h in dirty(checkout).items() if p not in mark["dirty"] or mark["dirty"][p] != h)
    by_id = {n.id: n for n in nodes(store)}
    left: set[str] = set()  # a hand-back's own leftovers, now inside its scope or a leaf it waits on
    for e in store.node_log(kinds=("released",)):
        back = by_id.get(e["node_id"])
        if back is None or e["timestamp"] < mark["at"]:
            continue
        owned = [*back.scope, *(g for i in back.needs if i in by_id for g in by_id[i].scope)]
        left |= {p for p in e["detail"].get("changed") or [] if in_scope(p, owned)}
    return [p for p in changed if p not in left and not any(in_scope(p, n.scope) for n in since)]


def accept_path(store, checkout: str | Path, path: str | Path) -> None:
    """A file the person just had Graphene write inside the checkout (an exported page) is theirs as
    it stands: it goes into the boundary, so the next start is not refused over Graphene's own output."""
    checkout = str(Path(checkout).resolve())
    mark = _boundary(store, checkout)
    try:
        rel = str(Path(path).resolve().relative_to(checkout))
    except ValueError:
        return  # written somewhere else: not this checkout's business
    if mark is not None:
        mark["dirty"][rel] = _hash(checkout, rel)
        store.set_meta(f"boundary:{checkout}", json.dumps(mark))


def acknowledge(store, checkout: str | Path, who: Caller, now: str | None = None) -> list[str]:
    """`graphene plan ack`: the uncommitted changes in the checkout are the person's as they stand
    (committing them does the same, since only the working tree is compared)."""
    _person_only(who, "making the uncommitted changes in the checkout yours")
    now = now or _now()
    paths = unowned(store, checkout)
    mark_boundary(store, checkout, now)
    store.log_node("*", now, "acknowledged", who.label, None, None, {"paths": paths})
    return paths


RUN_TREE = f"{os.sep}.graphene{os.sep}worktrees{os.sep}"  # where `graphene run --parallel` puts a leaf


def _may_start(store, node: Node, who: Caller, everything: list[Node]) -> None:
    """The refusals that need only the plan: read twice, before git is asked and again under the
    write lock, because the plan may have moved in between."""
    by_id = {n.id: n for n in everything}
    if paused(store):
        raise refusal("the plan is paused, so nothing starts", do="graphene plan resume (the person's)")
    under = kids(everything).get(node.id)
    if under:
        raise refusal(
            f"{node.id} is a sub-goal: the work is in its leaves ({', '.join(n.id for n in under)})",
            do="graphene plan shows which are ready",
        )
    if node.state == RUNNING:
        raise Refused(f"{node.id} is already running ({node.executor}, since {node.started_at})")
    if node.state != OPEN or any(a.state == PROPOSED for a in above(node, by_id)):
        raise _as_it_stands(node, everything, who)
    if not node.scope:
        raise _no_scope(node, who, "start")
    if os.environ.get("GRAPHENE_PLANNER") and not who.person:
        raise Refused("you are the planner: you propose the tree, and executors take its leaves")
    if not may_take(node, who):
        raise refusal(
            f"{node.id} is {node.owner}'s node, not {'yours' if who.person else "an agent's"}",
            do="graphene plan shows what else is ready; stop if everything left waits on it",
        )
    blockers = unmet(node, by_id)
    if blockers:
        raise Refused(f"{node.id} waits on {_told(blockers)}")


def _told(blockers: list[Node]) -> str:
    return ", ".join(
        f"{b.id} ({b.state}{', ' + b.owner + chr(39) + 's' if b.owner != AGENT else ''})" for b in blockers
    )


def _no_scope(node: Node, who: Caller, verb: str) -> Refused:
    """A node with no scope and no children: a person's own to-do, done by hand, or a node an agent
    left to be filled in (a placeholder `s` in graphene watch fills in)."""
    if node.owner != AGENT:
        whose = "yours" if who.person else f"{node.owner}'s"
        return refusal(
            f"{node.id} is {whose} to do by hand: it has no scope, so there is nothing to {verb}",
            do=f"graphene node done {node.id} when it is done"
            if who.person
            else "graphene plan shows what is ready",
        )
    return refusal(
        f"{node.id} has no scope and no leaves yet, so there is nothing to {verb}",
        do=f"s in graphene watch asks the planner to split it, or graphene node edit {node.id} gives it a "
        "scope and a check",
    )


def _as_it_stands(node: Node, everything: list[Node], who: Caller, verb: str = "start") -> Refused:
    """The line for the state a node is in, for a `start` or a `done` it is not in the state for:
    each state says what it is and what moves it on, and never the command that was just refused."""
    if node.state in GONE:
        return Refused(f"{node.id} is {node.state}: it is not in the plan any more")
    by_id = {n.id: n for n in everything}
    word = reads(node, everything)
    if word == "proposed":
        top = next((a for a in reversed(above(node, by_id)) if a.state == PROPOSED), node)
        return refusal(
            f"{node.id} is a proposal: nothing to {verb} until the person accepts it",
            do=f"graphene plan accept {top.id}" + ("" if who.person else " (the person's)"),
        )
    if word == "done":
        return Refused(f"{node.id} is done already")
    if word == "review":
        return refusal(
            f"{node.id} is finished and waits for the person's sign-off",
            do=f"graphene node signoff {node.id}" + ("" if who.person else " (the person's)"),
        )
    if not node.scope and not kids(everything).get(node.id):
        return _no_scope(node, who, verb)
    blockers = unmet(node, by_id)
    if blockers:
        return Refused(f"{node.id} is not running: it waits on {_told(blockers)}")
    return refusal(f"{node.id} is ready, not running", do=f"graphene node start {node.id} takes it")


def start(
    store,
    node_id: str,
    who: Caller,
    checkout: str | Path,
    now: str | None = None,
    agent_id: str | None = None,
    attended: bool = False,
) -> Node:
    """Take a node. Refused unless it is open, everything it waits on is done and its work is here,
    the caller may take it, and no running node in the same checkout claims a path this one claims.
    ``attended``: the person is in the session and asked for this, so what changed between nodes is
    theirs to have seen, as when they start a node themselves."""
    now = now or _now()
    checkout = str(Path(checkout).resolve())
    first = get(store, node_id)
    _may_start(store, first, who, nodes(store))
    # Everything git is asked is asked before the write lock is taken: with twenty worktrees on a large
    # repo it took seconds, and every hook waiting on the lock meanwhile gave up after a quarter of one.
    if _boundary(store, checkout) is None:
        mark_boundary(store, checkout, now)  # the first start in a checkout: the tree as it stands
    loose = unowned(store, checkout, but=node_id)
    if loose and not (who.person or attended):  # refused here, not under the claim: its rollback forgets
        it, change, stand = (
            ("it", "an uncommitted change", "it stands")
            if len(loose) == 1
            else ("them", "uncommitted changes", "they stand")
        )
        why = f" makes {it} theirs as {stand}, and so does committing {it}"
        raise refusal(
            f"{node_id} cannot start: the checkout has {change} no node made",
            loose,
            f"put {it} back, or ask the person: graphene plan ack"
            + (why if first_time(store, who, first, "loose") else ""),
        )
    away = not_here(store, first, checkout)
    files, base, was_dirty = tracked(checkout), head(checkout), dirty(checkout)
    # a leaf made from a prompt is a record, not a gate (``close_aside``): it skips the two looks
    # that only `finish` reads, which on a repo with thirty worktrees cost the hook over a second; and
    # a leaf in a run's own worktree never answers for the other trees (``elsewhere``)
    hidden = {} if first.aside else unseen(checkout)
    others = {} if first.aside or RUN_TREE in checkout else snapshot_others(checkout)
    with store.claim():
        node = get(store, node_id)
        everything = nodes(store)
        _may_start(store, node, who, everything)
        if away:
            raise Refused(f"{node.id} waits on {'; '.join(away)}")
        for other in everything:
            if (
                other.state == RUNNING
                and other.aside
                and who.session_id
                and other.session_id == who.session_id
            ):
                continue  # this session's own leaf from a prompt: it closes when the turn does
            if other.state == RUNNING and other.checkout == checkout:
                shared = overlap(node.scope, other.scope, files)
                if shared:
                    raise refusal(
                        f"{node.id} and {other.id} ({other.executor}, running) both claim these; one "
                        f"writer at a time, so wait for {other.id}",
                        shared,
                    )
        node.state, node.executor, node.session_id, node.agent_id = (
            RUNNING,
            who.name,
            who.session_id,
            agent_id,
        )
        node.checkout, node.base_sha, node.dirty_at_start = checkout, base, was_dirty
        node.unseen_at_start, node.others_at_start = hidden, others
        node.started_at, node.finished_at, node.told_rev = now, None, node.rev
        extra = {"unowned": loose} if loose else {}  # a person starting over them has seen them
        _save(store, node, "started", who, now, rev=node.rev, base=node.base_sha, checkout=checkout, **extra)
    return node


def not_here(store, node: Node, checkout: str | Path, committed: bool = False) -> list[str]:
    """What the node needs that is done, but whose work is not in ``checkout``: done in a run's
    worktree and never landed, landed somewhere this checkout's history does not reach yet, or done
    in another checkout and not committed there (a worktree cut from that checkout's HEAD would not
    have it). ``committed``: ask it of a worktree about to be cut from ``checkout``, so work left
    uncommitted in ``checkout`` itself does not count either. One reason each, for the refusal."""
    checkout = os.path.realpath(checkout)
    everything = nodes(store)
    by_id, under = {n.id: n for n in everything}, kids(everything)
    out: list[str] = []
    for need_id in all_needs(node, by_id):
        need = by_id.get(need_id)
        if need is None:
            continue
        done = (
            [need]
            if not under.get(need.id)
            else [c for c in below(need.id, everything) if not under.get(c.id)]
        )
        for leaf in done:
            if leaf.state != DONE or not leaf.checkout:
                continue
            where = os.path.realpath(leaf.checkout)
            if where == checkout and not committed:
                continue
            landed = (store.node_log(leaf.id, ("landed",)) or [None])[-1]
            if landed is not None:
                sha = landed["detail"].get("commit")
                ok = subprocess.run(["git", "-C", checkout, "merge-base", "--is-ancestor", sha or "", "HEAD"],
                                    capture_output=True).returncode == 0  # fmt: skip
                if not ok:
                    out.append(
                        f"{leaf.id} (it landed as {str(sha)[:10]}, which this checkout does not have yet)"
                    )
                continue
            if RUN_TREE in where + os.sep:
                out.append(
                    f"{leaf.id} (done in its worktree and never landed: `git merge graphene/{leaf.id}`)"
                )
                continue
            ended = (store.node_log(leaf.id, ("finished", "overruled")) or [{"detail": {}}])[-1]["detail"]
            if ended.get("blobs"):
                missing = _reaches(
                    checkout, ended["blobs"], not committed, leaf.finished_at, ended.get("head")
                )
                if missing:
                    why = "not committed where it was done" if where == checkout else f"done in {where}"
                    out.append(f"{leaf.id} ({why}, and {', '.join(missing[:3])} here does not have it yet)")
                continue
            paths = [p for p in ended.get("changed") or [] if in_scope(p, leaf.scope)]
            try:
                loose = set(dirty(where)) & set(paths) if paths and os.path.isdir(where) else set()
            except (Refused, OSError, subprocess.TimeoutExpired):
                loose = set()
            if loose:
                out.append(
                    f"{leaf.id} (its work is not committed in {where}: {', '.join(sorted(loose)[:3])}; "
                    "commit it, and a worktree cut from there has it)"
                )
    return out


def other_checkouts(checkout: str | Path) -> list[str]:
    """The repo's other working trees that still exist, as git lists them, but for the ones `graphene
    run --parallel` gives its leaves: each is its leaf's own checkout, and that leaf's boundary answers
    for it (a leaf's leftover there was charged to a node the person held in their own checkout)."""
    here = os.path.realpath(checkout)
    try:
        listed = _git(checkout, "worktree", "list", "--porcelain")
    except (Refused, OSError, subprocess.TimeoutExpired):
        return []
    paths = [os.path.realpath(line[9:]) for line in listed.splitlines() if line.startswith("worktree ")]
    return [p for p in paths if p != here and os.path.isdir(p) and RUN_TREE not in p + os.sep]


def snapshot_others(checkout: str | Path) -> dict[str, dict]:
    """HEAD and the dirty paths of each other working tree, as a node starts. A tree git lists and
    can no longer read (its directory emptied, its .git file gone: this repo had one) is left out;
    it answers for nothing, and it must not stop a node from starting."""
    out = {}
    for tree in other_checkouts(checkout):
        try:
            out[tree] = {"head": head(tree), "dirty": dirty(tree)}
        except (Refused, OSError, subprocess.TimeoutExpired):
            continue
    return out


def elsewhere(store, node: Node) -> list[str]:
    """What changed since the node was started in the repo's OTHER working trees, outside its scope
    and outside the scope of any node that ran there meanwhile, each path named with its tree. A
    closing review wrote one file by absolute path into a second worktree, and `done` said "nothing
    outside its scope": it had only asked about the checkout the node was started in. A worktree
    made after the start is compared with the commit the node started from."""
    if RUN_TREE in (node.checkout or ""):
        # a leaf `graphene run --parallel` put in a worktree of its own: meanwhile its siblings land
        # in the person's checkout and the person works there, and none of that is this leaf's doing
        # (a review ran 8 leaves on 4 workers and 3 were refused over a sibling's landed file)
        return []
    out = []
    for tree in other_checkouts(node.checkout or "."):
        was = node.others_at_start.get(tree) or {"head": node.base_sha, "dirty": {}}
        # any node that ran meanwhile, in whichever tree: a leaf run in its own worktree lands in the
        # person's checkout as a merge, and that change is the leaf's, not this node's
        theirs = [
            n
            for n in nodes(store)
            if n.id != node.id and n.started_at and (n.finished_at or "9") >= (node.started_at or "")
        ]
        try:
            changed = changed_since(tree, was["head"], was["dirty"])
        except (Refused, OSError, subprocess.TimeoutExpired):
            continue  # a working tree git cannot read any more answers for nothing
        out += [
            f"{p} (in the worktree {tree})"
            for p in changed
            if not in_scope(p, node.scope) and not any(in_scope(p, n.scope) for n in theirs)
        ]
    return out


def _holder_only(node: Node, who: Caller, what: str) -> None:
    """Only whoever holds a running node finishes it or hands it back; a person may always. A Claude
    Code session is known by its session id; an executor `graphene run` started is known by the
    GRAPHENE_NODE it was given; anyone else by the name they took the node under."""
    if who.person:
        return
    same_session = bool(node.session_id) and who.session_id == node.session_id
    run_gave_it = (
        (node.executor or "").startswith("run:")
        and os.environ.get("GRAPHENE_NODE") == node.id
        and os.environ.get("GRAPHENE_ATTEMPT", node.session_id)
        == node.session_id  # not an orphan of a dead run
    )
    if not (same_session or run_gave_it or (not node.session_id and who.name == node.executor)):
        raise Refused(
            f"{node.id} is held by {node.executor}, not by {who.name}: {what} is theirs, or a person's"
        )


def unseen(checkout: str | Path) -> dict[str, str]:
    """What stops git from answering for this checkout, as it stands: the paths marked
    assume-unchanged or skip-worktree (a change to them never shows), and the clone's own exclude
    file (a line in it hides a new file). `done` trusts git, so it first checks that nothing here
    has changed since the node was started: a review made a tracked file invisible with one
    `git update-index --assume-unchanged`, and the boundary passed."""
    flagged = [
        line[2:]
        for line in _git(checkout, "ls-files", "-v").splitlines()
        if line[:1].islower() or line[:1] == "S"
    ]
    exclude = Path(_git(checkout, "rev-parse", "--git-path", "info/exclude").strip())
    exclude = exclude if exclude.is_absolute() else Path(checkout) / exclude
    try:
        text = exclude.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return {"flagged": "\n".join(sorted(flagged)), "exclude": text}


def links_out(checkout: str | Path, paths: list[str]) -> list[str]:
    """Changed paths that are symbolic links to somewhere outside the checkout (or into the plan's
    own store): a write "inside the scope" through one lands where no scope reaches."""
    root = os.path.realpath(checkout)
    out = []
    for path in paths:
        full = os.path.join(root, path)
        if os.path.islink(full):
            target = os.path.realpath(full)
            inside = target == root or target.startswith(root + os.sep)
            if not inside or os.path.relpath(target, root).split(os.sep, 1)[0] == ".graphene":
                out.append(path)
    return out


def outside_scope(store, node: Node, changed: list[str] | None = None) -> list[str]:
    """What changed since the node was started that its scope does not cover, leaving out what a
    node that ran beside it in the same checkout was entitled to change."""
    beside = [
        n
        for n in nodes(store)
        if n.id != node.id
        and n.checkout == node.checkout
        and n.started_at
        and (n.finished_at or "9") >= (node.started_at or "")
        and n.state in (RUNNING, REVIEW, DONE)
    ]
    if changed is None:
        changed = changed_since(node.checkout or ".", node.base_sha, node.dirty_at_start)
    here = os.path.realpath(node.checkout or ".")
    landed: set[str] = set()  # what a leaf `graphene run --parallel` merged into this checkout meanwhile
    for e in store.node_log(kinds=("landed",)):
        d = e["detail"]
        if e["node_id"] == node.id or e["timestamp"] < (node.started_at or "") or not d.get("commit"):
            continue
        if os.path.realpath(d.get("into") or "") != here:
            continue
        ours = [p for p in d.get("paths") or [] if p in changed]
        now = _blobs(here, ours)
        for path in ours:  # the landing's only while the file is exactly what the merge brought
            try:
                merged = _git(here, "rev-parse", f"{d['commit']}:{path}").strip()
            except (Refused, OSError, subprocess.TimeoutExpired):
                merged = None
            if merged and now.get(path) == merged:
                landed.add(path)
    return [
        p
        for p in changed
        if not in_scope(p, node.scope) and p not in landed and not any(in_scope(p, n.scope) for n in beside)
    ]


def _stray(store, node: Node, who: Caller, now: str, stray: list[str]) -> Refused:
    """`done` refused over what changed outside the scope: logged, and said with its explanation the
    first time in a hold, and short after that."""
    store.log_node(node.id, now, "refused", who.label, who.session_id, None, {"outside": stray})
    first = first_time(store, who, node, "outside")
    what = f"{node.id} is not done: changed outside its scope ({', '.join(node.scope)})"
    what += ", which only the person widens" if first else ""
    folded = [p for p in stray if in_scope(p.lower(), [g.lower() for g in node.scope])]
    what += (
        f"; {folded[0]} differs from it only in upper and lower case, and git's spelling counts"
        if folded
        else ""
    )
    linked = links_out(node.checkout or ".", stray)
    what += f"; {linked[0]} is a symbolic link that leaves the repo" if linked else ""
    back = (
        f" (git checkout {(node.base_sha or 'HEAD')[:10]} -- <path>, or delete a new file)" if first else ""
    )
    it = "it" if len(stray) == 1 else "them"
    return refusal(what, stray, f"put {it} back{back}, or say why: graphene node release {node.id} --why '…'")


def _untracked(checkout: str | Path, paths: list[str]) -> list[str]:
    """Of ``paths``, the files git does not track (nor ignore): what a run of a check may have made."""
    new = {e[3:] for e in _git(checkout, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
           if e.startswith("?? ")}  # fmt: skip
    full = [(p, os.path.join(checkout, p)) for p in paths if p in new]
    return [p for p, f in full if os.path.isfile(f) and not os.path.islink(f)]


def _done_by_hand(store, node: Node, who: Caller, now: str, checkout: str | Path | None) -> Node:
    """A person's own leaf with no scope is their to-do: there is no check to run and nothing to ask
    git, so `done` is their word, and the log says so."""
    with store.claim():
        node = get(store, node.id)
        everything = nodes(store)
        by_id = {n.id: n for n in everything}
        if node.state != OPEN or any(a.state == PROPOSED for a in above(node, by_id)):
            raise _as_it_stands(node, everything, who, "finish")
        if unmet(node, by_id):
            raise Refused(f"{node.id} waits on {_told(unmet(node, by_id))}")
        node.state, node.finished_at = DONE, now
        _save(store, node, "finished", who, now, note="done by hand: the person's word, with no check to run")
    roll_up(store, who, checkout, now)
    return node


def finish(
    store,
    node_id: str,
    who: Caller,
    now: str | None = None,
    override: str | None = None,
    checkout: str | Path | None = None,
) -> Node:
    """The boundary. Graphene asks git what changed and runs the check; only then is the node done
    (or waiting for its sign-off). A person may overrule either with a reason, and the log says so."""
    now = now or _now()
    node = get(store, node_id)
    began = node.started_at  # the hold this `done` answers for: it may be let go, and taken again, meanwhile
    if kids(nodes(store)).get(node.id):
        if override is not None:
            _person_only(who, "overruling a node's check or scope")
        return _finish_subgoal(store, node, who, now, checkout or ".", override)
    if node.state == OPEN and not node.scope and node.owner != AGENT and who.person:
        return _done_by_hand(store, node, who, now, checkout)
    if node.state != RUNNING:
        raise _as_it_stands(node, nodes(store), who, "finish")
    _holder_only(node, who, "finishing it")
    if override is not None:
        _person_only(who, "overruling a node's check or scope")
    checkout = node.checkout or "."
    if override is None and node.unseen_at_start:
        now_unseen = unseen(checkout)
        if now_unseen != node.unseen_at_start:
            hidden = sorted(
                set(now_unseen["flagged"].splitlines()) - set(node.unseen_at_start["flagged"].splitlines())
            )
            what = (
                "marked assume-unchanged or skip-worktree since it was started"
                if hidden
                else ".git/info/exclude edited since it was started"
            )
            store.log_node(node.id, now, "refused", who.label, who.session_id, None, {"unseen": what})
            raise refusal(
                f"{node.id} is not done: git can no longer answer for this checkout: {what}",
                hidden,
                "git update-index --no-assume-unchanged --no-skip-worktree <path> undoes it"
                if hidden
                else "put it back as it was",
            )
    changed = changed_since(checkout, node.base_sha, node.dirty_at_start)
    stray = sorted(set(outside_scope(store, node, changed)) | set(links_out(checkout, changed)))
    stray += elsewhere(store, node)
    # A file git does not track, outside the scope, may be what a run of the check left (a cache from
    # the executor's own test run). The check runs without them, and what it makes again is its own:
    # it is neither counted nor committed. The rest are refused as ever. Anything else outside the
    # scope is refused before the check runs. The check writes nothing here git sees (``run_check``).
    aside = _untracked(checkout, stray) if stray and override is None and node.check else []
    if stray and override is None and len(aside) < len(stray):
        raise _stray(store, node, who, now, stray)
    passed, output, theirs = (True, "", []) if not node.check else run_check(node.check, checkout, aside)
    if node.check:
        store.log_node(
            node.id,
            _now(),
            "check_passed" if passed else "check_failed",
            who.label,
            who.session_id,
            None,
            {"command": node.check, "output": output},
        )
    if len(theirs) < len(aside):
        raise _stray(store, node, who, now, [p for p in stray if p not in theirs])
    changed = [p for p in changed if p not in theirs]  # `run` commits what `changed` names
    if not passed and override is None:
        raise Refused(f"{node.id} is not done: `{node.check}` failed:\n{output}")
    if override is None and not any(in_scope(p, node.scope) for p in changed):
        raise refusal(
            f"{node.id} is not done: nothing inside its scope ({', '.join(node.scope)}) has changed since "
            "it was started, so a passing check shows nothing",
            do=f"if there was nothing to do, say so: graphene node release {node.id} --why '…'",
        )
    # where it ended and what git said had changed by then: what the node's record reads, asked of
    # git before the write lock is taken (hundreds of files are hashed while every hook would wait)
    detail = {"head": head(checkout), "changed": changed[:KEPT_PATHS]}
    blobs = _blobs(checkout, [p for p in changed if in_scope(p, node.scope)][:KEPT_PATHS])
    with store.claim():
        node = get(store, node_id)
        if node.state != RUNNING or node.started_at != began:
            # let go while its check ran (a check can take minutes): that stands
            was = {OPEN: "handed back", DROPPED: "dropped", RUNNING: "handed back and taken again"}
            raise Refused(
                f"{node.id} was {was.get(node.state, node.state)} while its check ran, so it is not done; "
                "its work stays"
            )
        node.state = REVIEW if node.signoff and override is None else DONE
        node.finished_at = now
        if blobs:  # the content it left: what a leaf that needs it asks for, wherever it starts
            detail["blobs"] = blobs
        if len(changed) > KEPT_PATHS:
            detail["more_changed"] = len(changed) - KEPT_PATHS
        if override is not None:
            detail |= {"override": override, "outside": stray, "check_passed": passed}
        _save(
            store, node, "overruled" if override is not None else "finished", who, node.finished_at, **detail
        )
    if RUN_TREE not in (node.checkout or ""):
        # in a run's own worktree the sub-goal's check would not see its sibling leaves: `run.land`
        # rolls up after the merge, in the checkout where they are all together
        roll_up(store, who, node.checkout or ".", now)
    mark_boundary(store, node.checkout or ".", now)
    return node


def _settle(store, who: Caller, now: str) -> None:
    """After the tree changed shape: a finished sub-goal with a child that is not finished is open
    again. (The other direction runs a check, so it is ``roll_up``'s, outside the store's claim.)"""
    everything = nodes(store)
    under = kids(everything)
    for n in everything:
        if n.state in (DONE, REVIEW) and any(c.state != DONE for c in under.get(n.id, [])):
            n.state, n.finished_at = OPEN, None
            _save(store, n, "reopened", who, now, note="a node under it is not done")
            return _settle(store, who, now)


def roll_up(
    store,
    who: Caller,
    checkout: str | Path | None,
    now: str | None = None,
    not_here: frozenset[str] | set[str] = frozenset(),
) -> list[Node]:
    """Done rolls up: a sub-goal whose children are all done is done, once its own check (if it has
    one) passes in ``checkout``. That check is where integration lives: the leaves each passed
    theirs, and this one says they work together. A failing one leaves the sub-goal open, and the
    plan says so; with no checkout to run it in, it waits for `graphene node done <id>`.
    ``not_here``: leaves done in a worktree of their own whose work has not reached ``checkout``
    yet; a sub-goal above one of them waits, or its check would run without them and fail."""
    now = now or _now()
    rolled: list[Node] = []
    tried: set[str] = set()
    while True:
        everything = nodes(store)
        under = kids(everything)
        due = [
            n
            for n in everything
            if n.state == OPEN
            and n.id not in tried
            and under.get(n.id)
            and all(c.state == DONE for c in under[n.id])
            and not_here.isdisjoint(c.id for c in below(n.id, everything))
        ]
        if not due:
            return rolled
        node = due[0]
        tried.add(node.id)
        if node.check:
            if checkout is None:
                continue
            passed, output, _ = run_check(node.check, checkout)
            kind = "check_passed" if passed else "check_failed"
            store.log_node(node.id, _now(), kind, who.label, who.session_id, None,
                           {"command": node.check, "output": output})  # fmt: skip
            if not passed:
                continue
        with store.claim():
            node = get(store, node.id)
            if node.state != OPEN:
                continue  # another `done` got here first
            node.state, node.finished_at = (REVIEW if node.signoff else DONE), now
            _save(store, node, "rolled_up", who, now, children=[c.id for c in under[node.id]])
        rolled.append(node)


def _finish_subgoal(
    store, node: Node, who: Caller, now: str, checkout: str | Path, override: str | None = None
) -> Node:
    """`done` on a sub-goal: nothing to diff (its leaves answered for their changes); its children
    must be done, and its own check runs here."""
    open_kids = [c for c in kids(nodes(store))[node.id] if c.state != DONE]
    if open_kids:
        listed = ", ".join(f"{c.id} ({c.state})" for c in open_kids)
        raise Refused(f"{node.id} is a sub-goal and is done when its children are: {listed}")
    if node.state != OPEN:
        raise Refused(
            f"{node.id} is {node.state}" + (f" ({node.executor} holds it)" if node.executor else "")
        )
    if override is not None:  # the person says its leaves do work together, whatever its check says
        with store.claim():
            node = get(store, node.id)
            node.state, node.finished_at = DONE, now
            _save(store, node, "overruled", who, now, override=override)
        roll_up(store, who, checkout, now)
        return node
    if node not in roll_up(store, who, checkout, now) and get(store, node.id).state == OPEN:
        last = (store.node_log(node.id, ("check_failed",)) or [{"detail": {}}])[-1]["detail"]
        raise refusal(
            f"{node.id} is not done: its children are, and its own check `{node.check}` fails, so they "
            f"do not yet work together:\n{last.get('output', '')}",
            do=f"graphene node edit {node.id}: a line you add under it is a leaf for what is missing"
            if who.person
            else f"propose a leaf under it for what is missing: graphene plan propose - (parent: {node.id})",
        )
    return get(store, node.id)


def close_aside(store, node_id: str, who: Caller, now: str | None = None) -> Node:
    """The end of a leaf made from a prompt, when the turn it was typed for ends. It is a record,
    not a gate: git says what changed under it, and its check runs if the person gave one. Nothing
    changed, nothing kept: the leaf goes, so a question that led to no edit leaves no trace."""
    now = now or _now()
    node = get(store, node_id)
    checkout = node.checkout or "."
    changed = changed_since(checkout, node.base_sha, node.dirty_at_start)
    passed = None
    if node.check and changed:
        passed, output, _ = run_check(node.check, checkout)
        kind = "check_passed" if passed else "check_failed"
        store.log_node(node.id, _now(), kind, who.label, who.session_id, None,
                       {"command": node.check, "output": output})  # fmt: skip
        if not passed and len(store.node_log(node.id, ("check_failed",))) == 1:
            # said once, so the agent can put it right; asked to stop again, the leaf closes with the
            # failure on its record. It is a record, not a gate: a session is never trapped by it
            raise refusal(
                f"`{node.check}` failed:\n{output}",
                do="put it right, or stop again and it is recorded as it is",
            )
    with store.claim():
        node = get(store, node_id)
        waited_on = any(node.id in n.needs and n.state not in GONE for n in nodes(store))
        node.state, node.finished_at = (DONE if changed or waited_on else DROPPED), now
        stray = [p for p in changed if not in_scope(p, node.scope)]
        detail = {"head": head(checkout), "changed": changed[:KEPT_PATHS]} | (
            {"outside": stray} if stray else {}
        )
        detail |= {"check_passed": False} if passed is False else {}
        _save(store, node, "finished" if node.state == DONE else "dropped", who, now, **detail)
    mark_boundary(store, checkout, now)
    return node


def release(
    store, node_id: str, who: Caller, why: str, now: str | None = None, wants: list[str] | None = None
) -> Node:
    """Hand a running node back, with the reason. The way out for an executor that cannot finish:
    it may not stop silently, and it may not widen its own scope; it can say what is in the way, and
    name the paths it would need (``wants``), which the person is then offered in one key."""
    now = now or _now()
    if not why.strip():
        raise Refused("say why: --why 'what is in the way'; the person reads it to decide what to change")
    node = get(store, node_id)
    began, changed = node.started_at, []
    if node.state == RUNNING:  # git is asked before the write lock is taken
        try:
            changed = changed_since(node.checkout or ".", node.base_sha, node.dirty_at_start)
        except (Refused, OSError, subprocess.TimeoutExpired):
            pass  # a checkout git cannot read any more: the hand-back still stands
    with store.claim():
        node = get(store, node_id)
        if node.state != RUNNING:
            raise Refused(f"{node.id} is {node.state}, not running")
        _holder_only(node, who, "handing it back")
        if node.started_at != began:
            raise refusal(f"{node.id} changed hands just now", do="graphene plan shows who holds it")
        node.state, node.executor, node.session_id, node.agent_id = OPEN, None, None, None
        extra = {"wants": [w.strip() for w in wants if w.strip()]} if wants else {}
        _save(
            store,
            node,
            "released",
            who,
            now,
            why=why,
            changed=changed[:KEPT_PATHS],
            person=who.person,
            **extra,
        )
    return node


def unlanded(store, node_id: str) -> dict | None:
    """What the last hold of a leaf left when it passed and could not be merged here (its branch, its
    worktree, and why): None once it landed, or when it was taken again since."""
    log = store.node_log(node_id, ("started", "landed", "unlanded"))
    return log[-1]["detail"] if log and log[-1]["kind"] == "unlanded" else None


def signoff(
    store, node_id: str, who: Caller, now: str | None = None, checkout: str | Path | None = None
) -> Node:
    """A person's say-so: a node waiting in review is done. One that did not land was merged by hand,
    as they were told, and where it landed is recorded, or what needs it waits for ever. ``checkout``:
    where they merged it; the page passes none, and the repo the store belongs to is meant."""
    _person_only(who, "signing a node off")
    now = now or _now()
    checkout = checkout if checkout is not None else store.path.parent.parent
    left = unlanded(store, node_id)
    landed = None
    if left:  # asked of git before the write lock is taken
        branch = left.get("branch", f"graphene/{node_id}")
        try:
            sha = _git(checkout, "rev-parse", "-q", "--verify", branch).strip()
        except (Refused, OSError, subprocess.TimeoutExpired):
            sha = ""  # the branch is gone: merged and deleted
        merged = not sha or subprocess.run(
            ["git", "-C", str(checkout), "merge-base", "--is-ancestor", sha, "HEAD"], capture_output=True
        ).returncode == 0  # fmt: skip
        if not merged:  # signed off unmerged, it read as landed and what needed it went ahead without it
            raise refusal(
                f"{node_id}'s work is on {branch} and not in this checkout yet",
                do=f"git merge {branch} (commit or stash first what git says is in the way), "
                f"then graphene node signoff {node_id}",
            )
        landed = {"commit": sha or head(checkout), "branch": branch, "into": str(Path(checkout).resolve())}
    with store.claim():
        node = get(store, node_id)
        if node.state != REVIEW:
            raise Refused(
                f"{node.id} is {reads(node, nodes(store))}, and a sign-off comes once its check has passed"
            )
        node.state = DONE
        _save(store, node, "signed_off", who, now)
        if landed:
            store.log_node(node.id, now, "landed", who.label, None, None, landed)
    roll_up(store, who, checkout, now)
    if landed:
        mark_boundary(store, checkout, now)  # the person merged it by hand, as they were told to
    return node


def reopen(store, node_id: str, who: Caller, note: str, now: str | None = None) -> Node:
    """Not good enough: back to open, with what is wrong. The note is printed to whoever takes it next."""
    _person_only(who, "reopening a node")
    now = now or _now()
    with store.claim():
        node = get(store, node_id)
        if node.state not in (REVIEW, DONE):
            raise Refused(f"{node.id} is {node.state}; only a finished node is reopened")
        node.state, node.executor, node.session_id, node.agent_id = OPEN, None, None, None
        node.rev += 1
        _save(store, node, "reopened", who, now, note=note, rev=node.rev)
        _settle(store, who, now)
    return node


def notes(store, node_id: str) -> list[str]:
    """What the person said when sending a node back, newest last: part of what its next executor is told."""
    return [
        e["detail"].get("note", "") for e in store.node_log(node_id, ("reopened",)) if e["detail"].get("note")
    ]


def archive(store, who: Caller, now: str | None = None) -> list[Node]:
    """Put finished work away. With nothing left but archived nodes the plan is no longer in force."""
    _person_only(who, "archiving the plan")
    now = now or _now()
    with store.claim():
        finished = nodes(store, (DONE, DROPPED))
        kept = {need for n in nodes(store, (PROPOSED, OPEN, RUNNING, REVIEW)) for need in n.needs}
        by_id = {n.id: n for n in nodes(store)}
        everything = list(by_id.values())
        while True:  # what stays keeps what it needs, and what it sits under: until nothing more is kept
            put_away = [
                n
                for n in finished
                if n.id not in kept
                and all(a.state in (DONE, *GONE) for a in above(n, by_id))
                and all(c.state in (DONE, DROPPED) and c.id not in kept for c in below(n.id, everything))
            ]
            going = {n.id for n in put_away}
            more = {
                i for n in everything if n.id not in going and n.state not in GONE for i in n.needs
            } & going
            if not more:
                break
            kept |= more
        for node in put_away:
            was, node.state = node.state, ARCHIVED
            _save(store, node, "archived", who, now, was=was)
    return put_away


def set_paused(store, value: bool, who: Caller) -> None:
    _person_only(who, "pausing or resuming the plan")
    store.set_meta("paused", "1" if value else "0")


# -- undo: the person's last act on the plan's shape, put back ----------------------------------------

UNDO_KEPT = 20
_GOALS = ("goal", "goal:proposed")


def _shape(store) -> dict:
    seqs = store.node_seqs()
    return {
        "rows": {row["id"]: {**row, "_seq": seqs.get(row["id"])} for row in store.node_rows()},
        "meta": {k: store.meta(k) for k in _GOALS},
    }


@contextmanager
def undoable(store, who: Caller, what: str):
    """Around one act of the person's on the plan (an edit, an add, a drop, an acceptance, a text
    saved from the editor): what it changed is kept, so `graphene plan undo` can put it back. An
    agent's acts are not kept: an agent's proposal is dropped, not undone."""
    if not who.person:
        yield
        return
    with store.claim():  # one transaction: the act, and the record of it holds only the person's own changes
        before = _shape(store)
        yield
        after = _shape(store)
        _keep(store, what, before, after)


def _keep(store, what: str, before: dict, after: dict) -> None:
    rows = {
        i: [before["rows"].get(i), row] for i, row in after["rows"].items() if before["rows"].get(i) != row
    }
    meta = {k: [before["meta"][k], after["meta"][k]] for k in _GOALS if before["meta"][k] != after["meta"][k]}
    if rows or meta:
        stack = json.loads(store.meta("undo") or "[]")[-(UNDO_KEPT - 1) :]
        stack.append({"what": what, "at": _now(), "rows": rows, "meta": meta})
        store.set_meta("undo", json.dumps(stack))


def undo(store, who: Caller, now: str | None = None) -> str:
    """Put back the person's last act, if nothing it touched has moved on since (a node an executor
    started since is not taken from under it). Returns what was undone."""
    _person_only(who, "undoing an act on the plan")
    now = now or _now()
    with store.claim():
        stack = json.loads(store.meta("undo") or "[]")
        if not stack:
            raise Refused("nothing to undo: no act of yours on the plan is kept")
        act = stack.pop()
        current = _shape(store)
        moved = [i for i, (_, after) in act["rows"].items() if current["rows"].get(i) != after]
        added = {i for i, (before, _) in act["rows"].items() if before is None}
        hanging = [
            row["id"]
            for row in current["rows"].values()
            if row["id"] not in act["rows"] and row["state"] not in GONE
            and (row.get("parent") in added or added & set(row.get("needs") or []))
        ]  # fmt: skip
        if hanging:
            raise Refused(
                f"cannot undo {act['what']!r}: {', '.join(hanging)} was put under or made to wait on what it "
                "added, since; drop that first"
            )
        if moved:
            states = ", ".join(f"{i} ({(current['rows'].get(i) or {}).get('state', 'gone')})" for i in moved)
            raise Refused(
                f"cannot undo {act['what']!r}: {states} changed since, and undoing it would lose that"
            )
        for node_id, (before, after) in act["rows"].items():
            row = dict(before) if before is not None else {**after, "state": DROPPED}
            held = after is not None and all(
                after.get(k) == row.get(k) for k in ("state", "session_id", "started_at")
            )
            if row["state"] == RUNNING and not held:  # its executor was let go by the act undone (a drop)
                row.update(state=OPEN, executor=None, session_id=None, agent_id=None)
            row["rev"] = max(row.get("rev") or 1, (after or {}).get("rev") or 1) + (1 if before else 0)
            seq = row.pop("_seq", None)
            store.put_node(row)
            if seq is not None:
                store.set_seq(node_id, seq)
            store.log_node(node_id, now, "undone", who.label, None, None, {"note": act["what"]})
        for key, (before, _) in act["meta"].items():
            store.set_meta(key, before)
        try:
            # never put back a node whose parent or need is gone since; a state the plan was just in
            # is not asked the rules for a new node
            validate(nodes(store), set())
        except Refused as no:
            raise Refused(f"cannot undo {act['what']!r}: {no}") from None
        if "goal" in act["meta"]:
            back, was = act["meta"]["goal"]
            store.log_node("*", now, "goal", who.label, None, None, {"note": back or "", "was": was or ""})
        store.set_meta("undo", json.dumps(stack))
    return act["what"]


# -- how a node reads to a person -------------------------------------------------------------------
# One word, one glyph and one colour for each state, the same on the screen, in `graphene plan` and in
# the text form's notes. The colour says who has the move: cyan, the agent's guess, yours to prune;
# magenta, it waits on you; yellow, an agent is on it; green, done; plain, an agent can take it; dim,
# nothing to do yet. Red is kept for a command that failed. A sub-goal reads as "2/3 done".
LOOK = {
    "proposed": ("?", "cyan"),
    "ready": ("○", ""),
    "waiting": ("◌", "dim"),
    "running": ("●", "yellow"),
    "came back": ("↩", "magenta"),
    "review": ("◆", "magenta"),
    "yours": ("◇", "magenta"),
    "to fill in": ("·", "dim"),
    "done": ("✓", "green"),
}


def came_back(store, node: Node) -> bool:
    """Open, and its last hold ended with its executor handing it back, and the person has not
    changed it since (a widen or a sibling is an edit: after it, it is ready or waiting again)."""
    if node.state != OPEN:
        return False
    last = (store.node_log(node.id, ("started", "released", "reopened", "edited")) or [{"kind": ""}])[-1]
    return last["kind"] == "released" and not last["detail"].get("person")


def reads(node: Node, everything: list[Node], back: set[str] | frozenset[str] = frozenset()) -> str:
    """The word a node's state reads as, for a person: proposed, ready, waiting, running, came back
    (``back``: the ids `came_back` says so of), review, done, yours (a person's), to fill in (no
    leaves and no scope yet), or a sub-goal's "2/3 done"."""
    by_id = {n.id: n for n in everything}
    if node.state == PROPOSED or any(a.state == PROPOSED for a in above(node, by_id)):
        return "proposed"
    if node.state in (DONE, REVIEW, RUNNING):
        return {DONE: "done", REVIEW: "review", RUNNING: "running"}[node.state]
    under = kids(everything)
    if under.get(node.id):
        mine = [c for c in below(node.id, everything) if not under.get(c.id) and c.state != PROPOSED]
        return f"{sum(c.state == DONE for c in mine)}/{len(mine)} done"
    if node.id in back:
        return "came back"
    if unmet(node, by_id):
        return "waiting"
    if node.owner != AGENT:
        return "yours"
    return "ready" if node.scope else "to fill in"


def look(word: str) -> tuple[str, str]:
    """The glyph and the colour (a Rich style) of a word `reads` returns."""
    return LOOK.get(word, ("○", ""))


def said_by(label: str | None) -> str:
    """Who an actor on the plan is, in a person's words: `run:claude` is claude started by `graphene
    run`, `claude:5940…` a Claude Code session, `planner` the planner `graphene ask` started."""
    if not label:
        return "nobody on record"
    if label.startswith("run:"):
        return f"{label[4:]}, started by graphene run"
    if label.startswith("planner"):
        return "the planner (graphene ask)"
    kind, _, rest = label.partition(":")
    if kind in ("claude", "codex") and rest:
        return f"a {'Claude Code' if kind == 'claude' else 'Codex'} session ({rest})"
    return label


def where(root: str | Path) -> str:
    """The repository as the screen's top line and every write's last line name it."""
    path, home = str(root), str(Path.home())
    return "~" + path[len(home) :] if path.startswith(home + os.sep) else path


def plan_first(store) -> bool:
    """Plan first: what a person asks for in a session is proposed as a tree before any code. The
    person's setting (`graphene plan first on|off`, `P` in graphene watch); never set, it is on while
    a plan is in force. `graphene init` sets it on in a repository it sets up."""
    said = store.meta("plan_first")
    return said == "on" if said in ("on", "off") else in_force(store)


def set_plan_first(store, on: bool, who: Caller) -> None:
    """The person turns plan first on or off; it is theirs, like the plan's other settings."""
    _person_only(who, "turning plan first on or off")
    store.set_meta("plan_first", "on" if on else "off")
    store.log_node("*", _now(), "plan_first", who.label, None, None, {"note": "on" if on else "off"})
