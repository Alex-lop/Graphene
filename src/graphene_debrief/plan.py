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
import subprocess
import sys
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
CHECK_TIMEOUT = 1800  # seconds; ponytail: one fixed cap, a per-node value when a real check needs longer
TAIL = 2000  # characters of a check's output kept in the log
EDITABLE = ("title", "goal", "scope", "check", "signoff", "needs", "owner")


class Refused(Exception):
    """The plan says no, and the message is the reason, written for whoever asked."""


@dataclass(slots=True)
class Node:
    id: str
    title: str
    goal: str = ""
    scope: list[str] = field(default_factory=list)  # globs, repo-relative; "!glob" takes paths back out
    check: str | None = None  # a shell command that must exit 0, run by Graphene in the node's checkout
    signoff: bool = False  # a person must also say so
    needs: list[str] = field(default_factory=list)
    owner: str = AGENT
    state: str = OPEN
    rev: int = 1  # the contract's revision: goes up on every edit
    proposed_by: str | None = None
    executor: str | None = None  # who holds it, as they named themselves
    session_id: str | None = None  # the Claude Code session holding it, when that is who holds it
    agent_id: str | None = None
    checkout: str | None = None  # the working tree it runs in (a worktree is its own checkout)
    base_sha: str | None = None  # HEAD when it was started
    dirty_at_start: dict[str, str | None] = field(default_factory=dict)  # path -> content hash
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


def caller(env: dict[str, str] | None = None, tty: bool | None = None) -> Caller:
    """A person is someone at a terminal. An agent's shell says what it is (Codex exports
    CODEX_SESSION_ID, Claude Code CLAUDECODE and its session id), and whatever has no terminal at all
    is not a person either, so an executor nobody has heard of cannot sign anything off. A script
    that stands in for someone says so with GRAPHENE_AS=person:<name>; the Claude Code hook refuses
    an agent's shell command that carries that variable. An agent that forges it where no hook runs
    passes for a person: that hole is printed wherever a person-only control is described."""
    env = os.environ if env is None else env
    forced = env.get("GRAPHENE_AS")
    if forced:
        kind, _, name = forced.partition(":")
        return Caller(name or kind, kind == "person", env.get("CLAUDE_CODE_SESSION_ID"))
    if env.get("CODEX_SESSION_ID") or env.get("CODEX_SANDBOX"):  # first: Codex may run inside Claude Code
        return Caller(f"codex:{env.get('CODEX_SESSION_ID', '?')[:8]}", False, None)
    sid = env.get("CLAUDE_CODE_SESSION_ID")
    if sid or env.get("CLAUDECODE"):
        return Caller(f"claude:{(sid or '?')[:8]}", False, sid)
    if env.get("AI_AGENT"):
        return Caller(env["AI_AGENT"], False, None)
    if not (sys.stdin.isatty() if tty is None else tty):
        return Caller("a script", False, None)
    return Caller(person_name(env), True, None)


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
    beneath = "" if glob.endswith("**") else "(?:/.*)?"
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
    the other also covers. ponytail: a file neither scope names literally and that does not exist
    yet is not seen; the write-time refusal still holds for it, since no scope is ever widened."""
    both = [f for f in files if in_scope(f, a) and in_scope(f, b)]
    literal = [g for g in a if not g.startswith("!") and in_scope(g.rstrip("/*") or g, b)]
    literal += [g for g in b if not g.startswith("!") and in_scope(g.rstrip("/*") or g, a)]
    return sorted(set(both + literal))


# -- the graph ------------------------------------------------------------------------------------


def validate(nodes: list[Node]) -> None:
    """Refuse a plan that cannot run: an unknown dependency, a cycle, a node with nothing to touch
    and nothing to pass."""
    by_id = {n.id: n for n in nodes if n.state not in GONE}
    for n in by_id.values():
        if not n.title.strip():
            raise Refused(f"{n.id}: a node needs a title")
        if not n.scope:
            raise Refused(f"{n.id}: a node needs a scope (the paths it may touch), e.g. --scope 'src/api/**'")
        if not n.check and not n.signoff:
            raise Refused(
                f"{n.id}: a node needs a check, a person's sign-off, or both; else nobody knows it is done"
            )
        for need in n.needs:
            if need not in by_id:
                raise Refused(f"{n.id} waits on {need}, which is not in the plan")
    seen: dict[str, int] = {}

    def visit(i: str, trail: tuple[str, ...]) -> None:
        if seen.get(i) == 2:
            return
        if seen.get(i) == 1:
            raise Refused("the plan has a cycle: " + " -> ".join((*trail[trail.index(i) :], i)))
        seen[i] = 1
        for need in by_id[i].needs:
            visit(need, (*trail, i))
        seen[i] = 2

    for i in by_id:
        visit(i, ())


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
    return [by_id[i] for i in node.needs if i in by_id and by_id[i].state != DONE]


def ready(nodes: list[Node], who: Caller | None = None) -> list[Node]:
    """Open nodes with nothing left to wait on; for ``who``, only the ones they may take."""
    by_id = {n.id: n for n in nodes}
    out = [n for n in order(nodes) if n.state == OPEN and not unmet(n, by_id)]
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

    def walk(n: Node) -> None:
        if n.id in seen or n.state == DONE:
            return
        seen.add(n.id)
        if n.state == PROPOSED:
            reasons.append(f"{n.id} is a proposal nobody has accepted")
        elif n.owner != AGENT:
            reasons.append(f"{n.id} is {n.owner}'s")
        elif n.signoff and n.id != node.id:
            reasons.append(f"{n.id} needs a sign-off")
        for need in n.needs:
            if need in by_id:
                walk(by_id[need])

    walk(node)
    return reasons


def forecast(nodes: list[Node]) -> tuple[list[Node], list[tuple[Node, list[str]]]]:
    """What an unattended run will do: the nodes agents can reach by themselves, in order, and the
    ones that will sit waiting, each with who it waits for. Said before the run, so that a plan that
    stops at a person's node at 01:00 surprises nobody at 08:00."""
    by_id = {n.id: n for n in nodes}
    runs, waits = [], []
    for n in order(nodes):
        if n.state in (DONE, *GONE):
            continue
        why = waits_on_person(n, by_id)
        if why:
            waits.append((n, why))
        else:
            runs.append(n)
    return runs, waits


# -- git: what changed since a node was started -------------------------------------------------------


def _git(checkout: str | Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, timeout=30)
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
    it has changed again."""
    changed: set[str] = set(dirty_at_start)
    if base_sha:
        changed.update(
            p for p in _git(checkout, "diff", "--name-only", "-z", base_sha, "HEAD").split("\0") if p
        )
    changed.update(dirty(checkout))
    return sorted(p for p in changed if p not in dirty_at_start or _hash(checkout, p) != dirty_at_start[p])


def run_check(command: str, checkout: str | Path) -> tuple[bool, str]:
    """Run a node's check where the node ran. Graphene runs it, not the executor: "it passed" is
    then a fact about the repo and not a sentence in somebody's summary."""
    env = {k: v for k, v in os.environ.items() if k != "GRAPHENE_AS"}
    try:
        out = subprocess.run(
            command, shell=True, cwd=checkout, capture_output=True, text=True, timeout=CHECK_TIMEOUT, env=env
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {CHECK_TIMEOUT} s"
    text = (out.stdout + out.stderr).strip()
    return out.returncode == 0, (text[-TAIL:] if text else f"exit {out.returncode}, no output")


# -- the operations -------------------------------------------------------------------------------


def contract(node: Node) -> str:
    """The node as its executor is told it: the whole of what they are bound to, and nothing else."""
    lines = [
        f"{node.id} (revision {node.rev}): {node.title}",
        f"  goal:   {node.goal or node.title}",
        f"  scope:  {', '.join(node.scope)}   (a write anywhere else is refused, and blocks `done`)",
        f"  done:   {done_means(node)}",
        f"  finish: graphene node done {node.id}   (runs the check and asks git what changed)",
        f"  stuck:  graphene node release {node.id} --why '<what is in the way>'   (hands it back; say why)",
    ]
    return "\n".join(lines)


def done_means(node: Node) -> str:
    parts = [f"`{node.check}` passes" if node.check else ""]
    parts.append(f"{'and ' if node.check else ''}a person signs it off" if node.signoff else "")
    return " ".join(p for p in parts if p)


def from_dict(raw: dict, fallback_id: str) -> Node:
    """One node from a proposal's JSON. Unknown keys are refused, so a typo is not a silent default."""
    if not isinstance(raw, dict):
        raise Refused("a node is a JSON object with at least a title, a scope and a check")
    unknown = set(raw) - {"id", *EDITABLE}
    if unknown:
        raise Refused(
            f"unknown field{'s' if len(unknown) > 1 else ''} {', '.join(sorted(unknown))}; "
            f"a node has: id, {', '.join(EDITABLE)}"
        )
    scope = raw.get("scope") or []
    needs = raw.get("needs") or []
    return Node(
        id=str(raw.get("id") or fallback_id),
        title=str(raw.get("title") or ""),
        goal=str(raw.get("goal") or ""),
        scope=[scope] if isinstance(scope, str) else [str(s) for s in scope],
        check=str(raw["check"]) if raw.get("check") else None,
        signoff=bool(raw.get("signoff")),
        needs=[needs] if isinstance(needs, str) else [str(n) for n in needs],
        owner=str(raw.get("owner") or AGENT),
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
    store.log_node(node.id, now, kind, who.name, who.session_id, node.agent_id, detail or None)


def _person_only(who: Caller, what: str) -> None:
    if not who.person:
        raise Refused(
            f"{what} is the person's to do, at a terminal or in the map, and this call comes from "
            f"{who.name}. Say what you need and why; they decide"
        )


def paused(store) -> bool:
    return store.meta("paused") == "1"


def in_force(store) -> bool:
    """Is there a plan an executor is bound to right now?"""
    return not paused(store) and bool(store.node_rows(LIVE))


def propose(store, raw: list[dict], who: Caller, now: str | None = None) -> list[Node]:
    """Add nodes. From a person they are part of the plan at once; from an agent they are proposals,
    which nobody can start until a person accepts them."""
    now = now or _now()
    with store.claim():
        existing = nodes(store)
        taken = {n.id for n in existing}
        added: list[Node] = []
        for item in raw:
            k = len(taken) + 1
            while f"n{k}" in taken:
                k += 1
            node = from_dict(item, f"n{k}")
            if node.id in taken:
                raise Refused(f"{node.id} is already in the plan; `graphene node set {node.id} …` edits it")
            if not re.fullmatch(r"[A-Za-z0-9][\w.-]{0,31}", node.id):
                raise Refused(
                    f"{node.id!r} is not a usable id: letters, digits, '-', '_' and '.', at most 32"
                )
            taken.add(node.id)
            if node.owner == "me":
                node.owner = who.name if who.person else person_name()
            node.state = OPEN if who.person else PROPOSED
            node.proposed_by = who.name
            node.created_at = now
            added.append(node)
        validate(existing + added)
        for node in added:
            _save(store, node, "added" if who.person else "proposed", who, now)
    return added


def accept(store, ids: list[str], who: Caller, now: str | None = None) -> list[Node]:
    _person_only(who, "accepting a proposal")
    now = now or _now()
    with store.claim():
        chosen = [get(store, i) for i in ids] if ids else nodes(store, (PROPOSED,))
        for node in chosen:
            if node.state != PROPOSED:
                raise Refused(f"{node.id} is {node.state}, not a proposal")
            node.state = OPEN
            _save(store, node, "accepted", who, now)
    return chosen


def edit(store, node_id: str, changes: dict, who: Caller, now: str | None = None) -> Node:
    """Change a node's contract. The hook reads the row on every event, so a tighter scope binds the
    very next write, even on a node that is running; what waits to start is told the new contract."""
    _person_only(who, "editing a node's contract")
    now = now or _now()
    with store.claim():
        node = get(store, node_id)
        if node.state in (DONE, *GONE):
            raise Refused(f"{node.id} is {node.state}; `graphene node reopen {node.id}` first")
        fresh = from_dict({**{f: getattr(node, f) for f in EDITABLE}, **changes, "id": node.id}, node.id)
        if fresh.owner == "me":
            fresh.owner = who.name
        before = {f: getattr(node, f) for f in EDITABLE}
        for f in EDITABLE:
            setattr(node, f, getattr(fresh, f))
        changed = {f: [before[f], getattr(node, f)] for f in EDITABLE if before[f] != getattr(node, f)}
        if not changed:
            return node
        validate([node if n.id == node.id else n for n in nodes(store)])
        node.rev += 1
        _save(store, node, "edited", who, now, changed=changed, rev=node.rev)
    return node


def drop(store, node_id: str, who: Caller, now: str | None = None) -> Node:
    now = now or _now()
    with store.claim():
        node = get(store, node_id)
        if not who.person and node.state != PROPOSED:
            _person_only(who, "dropping an accepted node")
        if node.state == RUNNING:
            raise Refused(f"{node.id} is running ({node.executor}); `graphene node release {node.id}` first")
        waiting = [n.id for n in nodes(store) if node.id in n.needs and n.state not in GONE]
        if waiting:
            raise Refused(
                f"{', '.join(waiting)} wait{'s' if len(waiting) == 1 else ''} on {node.id}; "
                "change what they need first"
            )
        node.state = DROPPED
        _save(store, node, "dropped", who, now)
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


def unowned(store, checkout: str | Path, but: str | None = None) -> list[str]:
    """Paths changed since the last boundary in this checkout that no node can answer for: outside
    the scope of every node started since then. An executor that finishes its node inside the scope
    and then does the rest "after the audited window closed" lands here."""
    checkout = str(Path(checkout).resolve())
    mark = _boundary(store, checkout)
    if mark is None:
        return []
    since = [
        n
        for n in nodes(store)
        if n.id != but and n.checkout == checkout and (n.started_at or "") >= mark["at"]
    ]
    changed = changed_since(checkout, mark["head"], mark["dirty"])
    return [p for p in changed if not any(in_scope(p, n.scope) for n in since)]


def acknowledge(store, checkout: str | Path, who: Caller, now: str | None = None) -> list[str]:
    """The person says the tree is fine as it stands: what changed between nodes is theirs now."""
    _person_only(who, "accepting changes made while no node owned them")
    now = now or _now()
    paths = unowned(store, checkout)
    mark_boundary(store, checkout, now)
    store.log_node("*", now, "acknowledged", who.name, None, None, {"paths": paths})
    return paths


def start(
    store,
    node_id: str,
    who: Caller,
    checkout: str | Path,
    now: str | None = None,
    agent_id: str | None = None,
) -> Node:
    """Take a node. Refused unless it is open, everything it waits on is done, the caller may take
    it, and no running node in the same checkout claims a path this one claims."""
    now = now or _now()
    checkout = str(Path(checkout).resolve())
    with store.claim():
        node = get(store, node_id)
        everything = nodes(store)
        by_id = {n.id: n for n in everything}
        if paused(store):
            raise Refused("the plan is paused; `graphene plan resume` is the person's to run")
        if node.state == RUNNING:
            raise Refused(f"{node.id} is already running ({node.executor}, since {node.started_at})")
        if node.state == PROPOSED:
            raise Refused(
                f"{node.id} is a proposal; a person accepts it with `graphene plan accept {node.id}`"
            )
        if node.state != OPEN:
            raise Refused(f"{node.id} is {node.state}")
        if not may_take(node, who):
            raise Refused(
                f"{node.id} is {node.owner}'s node, not {'yours' if who.person else 'an agent’s'}; "
                "take another (`graphene plan`), or stop if everything left waits on it"
            )
        blockers = unmet(node, by_id)
        if blockers:
            told = ", ".join(
                f"{b.id} ({b.state}{', ' + b.owner + chr(39) + 's' if b.owner != AGENT else ''})"
                for b in blockers
            )
            raise Refused(f"{node.id} waits on {told}")
        if _boundary(store, checkout) is None:
            mark_boundary(store, checkout, now)  # the first start in a checkout: the tree as it stands
        loose = unowned(store, checkout, but=node.id)
        if loose and not who.person:
            listed = ", ".join(loose[:8]) + (f" and {len(loose) - 8} more" if len(loose) > 8 else "")
            raise Refused(
                f"{node.id} cannot start: {listed} changed while no node owned "
                f"{'it' if len(loose) == 1 else 'them'}. Put {'it' if len(loose) == 1 else 'them'} back, "
                "or tell the person: `graphene plan ack` is theirs to run if the change is theirs"
            )
        files = tracked(checkout)
        for other in everything:
            if other.state == RUNNING and other.checkout == checkout:
                shared = overlap(node.scope, other.scope, files)
                if shared:
                    raise Refused(
                        f"{node.id} and {other.id} ({other.executor}, running) both claim "
                        f"{', '.join(shared[:5])}; one writer at a time: wait for {other.id}"
                    )
        node.state, node.executor, node.session_id, node.agent_id = (
            RUNNING,
            who.name,
            who.session_id,
            agent_id,
        )
        node.checkout, node.base_sha, node.dirty_at_start = checkout, head(checkout), dirty(checkout)
        node.started_at, node.finished_at, node.told_rev = now, None, node.rev
        extra = {"unowned": loose} if loose else {}  # a person starting over them has seen them
        _save(store, node, "started", who, now, rev=node.rev, base=node.base_sha, checkout=checkout, **extra)
    return node


def outside_scope(store, node: Node) -> list[str]:
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
    changed = changed_since(node.checkout or ".", node.base_sha, node.dirty_at_start)
    return [
        p for p in changed if not in_scope(p, node.scope) and not any(in_scope(p, n.scope) for n in beside)
    ]


def finish(store, node_id: str, who: Caller, now: str | None = None, override: str | None = None) -> Node:
    """The boundary. Graphene asks git what changed and runs the check; only then is the node done
    (or waiting for its sign-off). A person may overrule either with a reason, and the log says so."""
    now = now or _now()
    node = get(store, node_id)
    if node.state != RUNNING:
        raise Refused(f"{node.id} is {node.state}, not running; `graphene node start {node.id}` takes it")
    if not who.person and node.session_id and who.session_id and node.session_id != who.session_id:
        raise Refused(f"{node.id} is held by {node.executor}, not by this session")
    if override is not None:
        _person_only(who, "overruling a node's check or scope")
    stray = outside_scope(store, node)
    if stray and override is None:
        store.log_node(node.id, now, "refused", who.name, who.session_id, None, {"outside": stray})
        listed = ", ".join(stray[:8]) + (f" and {len(stray) - 8} more" if len(stray) > 8 else "")
        raise Refused(
            f"{node.id} is not done: changed outside its scope ({', '.join(node.scope)}): {listed}. "
            "Put those back as they were (`git checkout <base> -- <path>`, or delete a new file), or say "
            f"why the scope is wrong: `graphene node release {node.id} --why '…'`. "
            "Only the person widens a scope, and only they decide a build leftover belongs in .gitignore"
        )
    before = dirty(node.checkout or ".") if node.check else {}
    passed, output = (True, "") if not node.check else run_check(node.check, node.checkout or ".")
    if node.check:
        # what Graphene's own run of the check left behind (a cache, a coverage file) is not the
        # executor's change: it is taken as it is, so a second `done` is not refused over it
        after = dirty(node.checkout or ".")
        left = {p: h for p, h in after.items() if before.get(p, "") != h and not in_scope(p, node.scope)}
        if left:
            with store.claim():
                node = get(store, node_id)
                node.dirty_at_start.update(left)
                store.put_node(to_dict(node))
        store.log_node(
            node.id,
            _now(),
            "check_passed" if passed else "check_failed",
            who.name,
            who.session_id,
            None,
            {"command": node.check, "output": output},
        )
    if not passed and override is None:
        raise Refused(f"{node.id} is not done: `{node.check}` failed:\n{output}")
    with store.claim():
        node = get(store, node_id)
        node.state = REVIEW if node.signoff and override is None else DONE
        node.finished_at = now
        detail = (
            {"override": override, "outside": stray, "check_passed": passed} if override is not None else {}
        )
        _save(
            store, node, "overruled" if override is not None else "finished", who, node.finished_at, **detail
        )
    mark_boundary(store, node.checkout or ".", now)
    return node


def release(store, node_id: str, who: Caller, why: str, now: str | None = None) -> Node:
    """Hand a running node back, with the reason. The way out for an executor that cannot finish:
    it may not stop silently, and it may not widen its own scope; it can say what is in the way."""
    now = now or _now()
    if not why.strip():
        raise Refused("say why: --why 'what is in the way'; the person reads it to decide what to change")
    with store.claim():
        node = get(store, node_id)
        if node.state != RUNNING:
            raise Refused(f"{node.id} is {node.state}, not running")
        node.state, node.executor, node.session_id, node.agent_id = OPEN, None, None, None
        _save(store, node, "released", who, now, why=why)
    return node


def signoff(store, node_id: str, who: Caller, now: str | None = None) -> Node:
    _person_only(who, "signing a node off")
    now = now or _now()
    with store.claim():
        node = get(store, node_id)
        if node.state != REVIEW:
            raise Refused(
                f"{node.id} is {node.state}; a sign-off comes after its executor ran `graphene node done`"
            )
        node.state = DONE
        _save(store, node, "signed_off", who, now)
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
        put_away = [n for n in finished if n.id not in kept]  # what unfinished work waits on stays
        for node in put_away:
            was, node.state = node.state, ARCHIVED
            _save(store, node, "archived", who, now, was=was)
    return put_away


def set_paused(store, value: bool, who: Caller) -> None:
    _person_only(who, "pausing or resuming the plan")
    store.set_meta("paused", "1" if value else "0")
