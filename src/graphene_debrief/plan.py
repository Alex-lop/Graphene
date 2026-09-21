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
CHECK_TIMEOUT = 1800  # seconds; TODO: one fixed cap, a per-node value when a real check needs longer
TAIL = 2000  # characters of a check's output kept in the log
KEPT_PATHS = 200  # changed paths kept in a node's log when it ends; the count of the rest is kept too
EDITABLE = ("title", "goal", "scope", "check", "signoff", "needs", "owner", "parent")
# Environment variables an agent's shell carries. GRAPHENE_NODE is ours: `graphene run` sets it for
# every executor it starts. TODO: the last two are from the vendors' docs, not yet seen on a real run.
AGENT_MARKS = ("GRAPHENE_NODE", "GEMINI_CLI", "CURSOR_AGENT")


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
    log shows it, and the hole is printed wherever a person-only control is described."""
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
        return Caller("an agent" if mark != "GRAPHENE_NODE" else f"run:{env[mark]}", False, None)
    forced = env.get("GRAPHENE_AS")
    if forced:
        kind, _, name = forced.partition(":")
        return Caller(name or kind, kind == "person", None, stand_in=True)
    at_terminal = sys.stdin.isatty() if tty is None else tty
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


def kids(nodes: list[Node]) -> dict[str | None, list[Node]]:
    """Each node's children that are still part of the plan, in the order they were added."""
    out: dict[str | None, list[Node]] = {}
    for n in nodes:
        if n.state not in GONE:
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
    """Everything under a node, parents before their children."""
    under = kids(nodes)
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


def validate(nodes: list[Node]) -> None:
    """Refuse a plan that cannot run: an unknown parent or dependency, a cycle (through needs, through
    the tree, or through both), a leaf with nothing to touch or nothing to pass."""
    by_id = {n.id: n for n in nodes if n.state not in GONE}
    under = kids(nodes)
    for n in by_id.values():
        if not n.title.strip():
            raise Refused(f"{n.id}: a node needs a title")
        if n.parent is not None and n.parent not in by_id:
            raise Refused(f"{n.id} is under {n.parent}, which is not in the plan")
        if n.parent is not None and by_id[n.parent].aside:
            raise Refused(f"{n.parent} was made from a prompt and is done as typed; it takes no children")
        for need in n.needs:
            if need not in by_id:
                raise Refused(f"{n.id} waits on {need}, which is not in the plan")
        if under.get(n.id) or not (n.scope or n.check or n.signoff or n.aside):
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
        f"  stuck:  graphene node release {node.id} --why '<what is in the way>'   (hands it back; say why)",
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
    return Node(
        id=str(raw.get("id") or fallback_id),
        title=str(raw.get("title") or ""),
        goal=str(raw.get("goal") or ""),
        scope=[scope] if isinstance(scope, str) else [str(s) for s in scope],
        check=str(raw["check"]) if raw.get("check") else None,
        signoff=bool(raw.get("signoff")),
        needs=[needs] if isinstance(needs, str) else [str(n) for n in needs],
        owner=str(raw.get("owner") or AGENT),
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


def _person_only(who: Caller, what: str) -> None:
    if not who.person:
        raise Refused(
            f"{what} is the person's to do, at a terminal or in the map, and this call comes from "
            f"{who.name}. Say what you need and why; they decide"
        )


def goal(store) -> str:
    """The root of the tree: why any of this is being done, in the person's words."""
    return store.meta("goal") or ""


def set_goal(store, text: str, who: Caller, now: str | None = None) -> None:
    _person_only(who, "saying what the plan is for")
    store.set_meta("goal", text.strip())
    store.log_node("*", now or _now(), "goal", who.label, None, None, {"note": text.strip()})


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
) -> list[Node]:
    """Add nodes. From a person they are part of the plan at once; from an agent they are proposals,
    which nobody can start until a person accepts them."""
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
        held = {n.id: n for n in existing if n.state == RUNNING}
        for node in added:
            if node.state == OPEN and node.parent in held:
                raise Refused(
                    f"{node.parent} is running ({held[node.parent].executor}); a child would make it a "
                    f"sub-goal under their hands. `graphene node release {node.parent} --why …` first"
                )
        for node in added:
            wrong = miscased(node.scope, files or [])
            if wrong:
                raise Refused(f"{node.id}: {wrong}; spell the scope as git does")
        for node in added:
            _save(store, node, "added" if who.person else "proposed", who, now)
        _settle(store, who, now)
    return added


def accept(store, ids: list[str], who: Caller, now: str | None = None, **detail) -> list[Node]:
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
            family = [*reversed(above(node, by_id)), node, *below(node.id, everything)]
            fresh = [by_id[n.id] for n in family if n.state == PROPOSED and n not in chosen]
            if not fresh and node not in chosen:
                raise Refused(f"{node.id} is {node.state}, not a proposal")
            chosen += fresh
        for node in chosen:
            parent = by_id.get(node.parent or "")
            if parent is not None and parent.state == RUNNING:
                raise Refused(
                    f"{node.id} would make {parent.id} a sub-goal while {parent.executor} holds it; they "
                    f"hand it back first (`graphene node release {parent.id} --why …`)"
                )
            node.state = OPEN
            _save(store, node, "accepted", who, now, **detail)
        _settle(store, who, now)
    return chosen


def edit(
    store, node_id: str, changes: dict, who: Caller, now: str | None = None, files: list[str] | None = None
) -> Node:
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
        wrong = miscased(node.scope, files or []) if "scope" in changed else None
        if wrong:
            raise Refused(f"{node.id}: {wrong}; spell the scope as git does")
        node.rev += 1
        _save(store, node, "edited", who, now, changed=changed, rev=node.rev)
        _settle(store, who, now)
    return node


def drop(store, node_id: str, who: Caller, now: str | None = None) -> Node:
    now = now or _now()
    with store.claim():
        node = get(store, node_id)
        everything = nodes(store)
        going = [node, *below(node.id, everything)]  # a sub-goal goes with everything under it
        if not who.person and any(n.state != PROPOSED for n in going):
            _person_only(who, "dropping an accepted node")
        held = [n for n in going if n.state == RUNNING]
        if held and not who.person:
            raise Refused(f"{held[0].id} is running ({held[0].executor}); `graphene node release` first")
        gone = {n.id for n in going}
        waiting = [
            n.id for n in everything if n.id not in gone and gone & set(n.needs) and n.state not in GONE
        ]
        if waiting:
            raise Refused(
                f"{', '.join(waiting)} wait{'s' if len(waiting) == 1 else ''} on {node.id}; "
                "change what they need first"
            )
        for n in going:
            n.state = DROPPED
            _save(store, n, "dropped", who, now)
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
    """The person says the tree is fine as it stands: what changed between nodes is theirs now."""
    _person_only(who, "accepting changes made while no node owned them")
    now = now or _now()
    paths = unowned(store, checkout)
    mark_boundary(store, checkout, now)
    store.log_node("*", now, "acknowledged", who.label, None, None, {"paths": paths})
    return paths


def start(
    store,
    node_id: str,
    who: Caller,
    checkout: str | Path,
    now: str | None = None,
    agent_id: str | None = None,
    attended: bool = False,
) -> Node:
    """Take a node. Refused unless it is open, everything it waits on is done, the caller may take
    it, and no running node in the same checkout claims a path this one claims. ``attended``: the
    person is in the session and asked for this, so what changed between nodes is theirs to have
    seen, as when they start a node themselves."""
    now = now or _now()
    checkout = str(Path(checkout).resolve())
    with store.claim():
        node = get(store, node_id)
        everything = nodes(store)
        by_id = {n.id: n for n in everything}
        if paused(store):
            raise Refused("the plan is paused; `graphene plan resume` is the person's to run")
        under = kids(everything).get(node.id)
        if under or not node.scope:
            inside = (
                ", ".join(n.id for n in under or []) or f"none yet: `graphene node add … --parent {node.id}`"
            )
            raise Refused(
                f"{node.id} is a sub-goal: the work is in its leaves ({inside}). "
                "`graphene plan` shows which are ready"
            )
        if node.state == RUNNING:
            raise Refused(f"{node.id} is already running ({node.executor}, since {node.started_at})")
        if node.state == PROPOSED or any(a.state == PROPOSED for a in above(node, by_id)):
            raise Refused(
                f"{node.id} is a proposal; a person accepts it with `graphene plan accept {node.id}`"
            )
        if node.state != OPEN:
            raise Refused(f"{node.id} is {node.state}")
        if not may_take(node, who):
            raise Refused(
                f"{node.id} is {node.owner}'s node, not {'yours' if who.person else "an agent's"}; "
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
        if loose and not (who.person or attended):
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
        # a leaf made from a prompt is a record, not a gate (``close_aside``): it skips the two looks
        # that only `finish` reads, which on a repo with thirty worktrees cost the hook over a second
        node.unseen_at_start = {} if node.aside else unseen(checkout)
        node.others_at_start = {} if node.aside else snapshot_others(checkout)
        node.started_at, node.finished_at, node.told_rev = now, None, node.rev
        extra = {"unowned": loose} if loose else {}  # a person starting over them has seen them
        _save(store, node, "started", who, now, rev=node.rev, base=node.base_sha, checkout=checkout, **extra)
    return node


def other_checkouts(checkout: str | Path) -> list[str]:
    """The repo's other working trees that still exist, as git lists them."""
    here = os.path.realpath(checkout)
    try:
        listed = _git(checkout, "worktree", "list", "--porcelain")
    except (Refused, OSError, subprocess.TimeoutExpired):
        return []
    paths = [os.path.realpath(line[9:]) for line in listed.splitlines() if line.startswith("worktree ")]
    return [p for p in paths if p != here and os.path.isdir(p)]


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
    run_gave_it = (node.executor or "").startswith("run:") and os.environ.get("GRAPHENE_NODE") == node.id
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
    return [
        p for p in changed if not in_scope(p, node.scope) and not any(in_scope(p, n.scope) for n in beside)
    ]


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
    if kids(nodes(store)).get(node.id):
        return _finish_subgoal(store, node, who, now, checkout or ".")
    if node.state != RUNNING:
        raise Refused(f"{node.id} is {node.state}, not running; `graphene node start {node.id}` takes it")
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
                f"{', '.join(hidden)} marked assume-unchanged or skip-worktree since it was started "
                "(`git update-index --no-assume-unchanged --no-skip-worktree <path>` undoes it)"
                if hidden
                else ".git/info/exclude edited since it was started (put it back as it was)"
            )
            store.log_node(node.id, now, "refused", who.label, who.session_id, None, {"unseen": what})
            raise Refused(f"{node.id} is not done: git can no longer answer for this checkout: {what}")
    changed = changed_since(checkout, node.base_sha, node.dirty_at_start)
    stray = sorted(set(outside_scope(store, node, changed)) | set(links_out(checkout, changed)))
    stray += elsewhere(store, node)
    if stray and override is None:
        store.log_node(node.id, now, "refused", who.label, who.session_id, None, {"outside": stray})
        listed = ", ".join(stray[:8]) + (f" and {len(stray) - 8} more" if len(stray) > 8 else "")
        folded = [p for p in stray if in_scope(p.lower(), [g.lower() for g in node.scope])]
        hint = (
            f" ({folded[0]} differs from the scope only in upper and lower case: git's spelling is the "
            "one that counts, and the person can correct the scope.)"
            if folded
            else ""
        )
        linked = links_out(checkout, stray)
        hint += f" ({linked[0]} is a symbolic link that leaves the repo.)" if linked else ""
        raise Refused(
            f"{node.id} is not done: changed outside its scope ({', '.join(node.scope)}): {listed}.{hint} "
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
            who.label,
            who.session_id,
            None,
            {"command": node.check, "output": output},
        )
    if not passed and override is None:
        raise Refused(f"{node.id} is not done: `{node.check}` failed:\n{output}")
    if override is None and not any(in_scope(p, node.scope) for p in changed):
        raise Refused(
            f"{node.id} is not done: nothing inside its scope ({', '.join(node.scope)}) has changed since "
            "it was started, so a passing check shows nothing. If there was nothing to do, hand it "
            f"back and say so: `graphene node release {node.id} --why '…'`"
        )
    with store.claim():
        node = get(store, node_id)
        node.state = REVIEW if node.signoff and override is None else DONE
        node.finished_at = now
        # where it ended and what git said had changed by then: what the node's record reads
        detail = {"head": head(node.checkout or "."), "changed": changed[:KEPT_PATHS]}
        if len(changed) > KEPT_PATHS:
            detail["more_changed"] = len(changed) - KEPT_PATHS
        if override is not None:
            detail |= {"override": override, "outside": stray, "check_passed": passed}
        _save(
            store, node, "overruled" if override is not None else "finished", who, node.finished_at, **detail
        )
    mark_boundary(store, node.checkout or ".", now)
    if f"{os.sep}.graphene{os.sep}worktrees{os.sep}" not in (node.checkout or ""):
        # in a run's own worktree the sub-goal's check would not see its sibling leaves: `run.land`
        # rolls up after the merge, in the checkout where they are all together
        roll_up(store, who, node.checkout or ".", now)
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
            passed, output = run_check(node.check, checkout)
            kind = "check_passed" if passed else "check_failed"
            store.log_node(node.id, _now(), kind, who.label, who.session_id, None,
                           {"command": node.check, "output": output})  # fmt: skip
            if not passed:
                continue
        with store.claim():
            node = get(store, node.id)
            node.state, node.finished_at = (REVIEW if node.signoff else DONE), now
            _save(store, node, "rolled_up", who, now, children=[c.id for c in under[node.id]])
        rolled.append(node)


def _finish_subgoal(store, node: Node, who: Caller, now: str, checkout: str | Path) -> Node:
    """`done` on a sub-goal: nothing to diff (its leaves answered for their changes); its children
    must be done, and its own check runs here."""
    open_kids = [c for c in kids(nodes(store))[node.id] if c.state != DONE]
    if open_kids:
        listed = ", ".join(f"{c.id} ({c.state})" for c in open_kids)
        raise Refused(f"{node.id} is a sub-goal and is done when its children are: {listed}")
    if node.state in (DONE, REVIEW):
        raise Refused(f"{node.id} is already {node.state}")
    if node not in roll_up(store, who, checkout, now) and get(store, node.id).state == OPEN:
        last = (store.node_log(node.id, ("check_failed",)) or [{"detail": {}}])[-1]["detail"]
        raise Refused(
            f"{node.id} is not done: its children are, and its own check `{node.check}` fails, so they "
            f"do not yet work together:\n{last.get('output', '')}\nAdd a leaf under {node.id} for what is "
            f"missing (`graphene node add '…' --parent {node.id} --scope … --check …`)"
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
    if node.check and changed:
        passed, output = run_check(node.check, checkout)
        kind = "check_passed" if passed else "check_failed"
        store.log_node(node.id, _now(), kind, who.label, who.session_id, None,
                       {"command": node.check, "output": output})  # fmt: skip
        if not passed:
            raise Refused(f"`{node.check}` failed:\n{output}")
    with store.claim():
        node = get(store, node_id)
        node.state, node.finished_at = (DONE if changed else DROPPED), now
        stray = [p for p in changed if not in_scope(p, node.scope)]
        detail = {"head": head(checkout), "changed": changed[:KEPT_PATHS]} | (
            {"outside": stray} if stray else {}
        )
        _save(store, node, "finished" if changed else "dropped", who, now, **detail)
    mark_boundary(store, checkout, now)
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
        _holder_only(node, who, "handing it back")
        try:
            changed = changed_since(node.checkout or ".", node.base_sha, node.dirty_at_start)
        except (Refused, OSError, subprocess.TimeoutExpired):
            changed = []  # a checkout git cannot read any more: the hand-back still stands
        node.state, node.executor, node.session_id, node.agent_id = OPEN, None, None, None
        _save(store, node, "released", who, now, why=why, changed=changed[:KEPT_PATHS])
    return node


def signoff(
    store, node_id: str, who: Caller, now: str | None = None, checkout: str | Path | None = None
) -> Node:
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
    roll_up(store, who, checkout, now)
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
        put_away = [  # what unfinished work waits on stays, and so does what sits under a sub-goal still open
            n for n in finished if n.id not in kept and all(a.state in (DONE, *GONE) for a in above(n, by_id))
        ]
        for node in put_away:
            was, node.state = node.state, ARCHIVED
            _save(store, node, "archived", who, now, was=was)
    return put_away


def set_paused(store, value: bool, who: Caller) -> None:
    _person_only(who, "pausing or resuming the plan")
    store.set_meta("paused", "1" if value else "0")
