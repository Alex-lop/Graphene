"""What the Claude Code hooks answer while a plan is in force. Standard library only.

The plan binds at the boundary whoever executes a node (``plan.finish``: git and the check decide).
This is the part only a vendor's hooks can add: the write refused before it happens, with the reason;
the stop refused while a node is open; the person's word kept out of an agent's mouth. Each answer is
the vendor's documented JSON (code.claude.com/docs/en/hooks), printed by ``hook_main``.

The holes, which the README and the map print beside the controls:
- a hook that crashes or times out lets the call through (the vendor's rule); ``finish`` still holds;
- a write through an MCP server's tool (a filesystem server's included) is not seen here at all;
- a shell command can write a file in a way no parser reads (a script that opens files itself);
  when the vendor reports what a command changed it is refused after the fact, and ``finish`` asks
  git, which sees every write however it was made;
- the vendor lets a session stop after 8 refused stops in a row; the node then stays open, visibly;
- the refusals that read a command's text (GRAPHENE_AS, .graphene/) stop the ordinary spellings and
  not a determined one. What holds against that is elsewhere: ``plan.caller`` ranks an agent's own
  environment above the variable, and the store is the one thing nothing here can defend against a
  script that opens it directly.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import plan as P

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
OURS = (".graphene",)  # the plan's own store: never inside any scope
_AS_PERSON = re.compile(r"\bGRAPHENE_(AS|WATCH)\b")
PARSED = 64_000  # characters of a shell command the hook will parse: the parser is superlinear, and the
# vendor lets a call through when a hook runs out of time (3 MB took 234 s in the closing review)
WIDE = 8  # paths a one-leaf ask may reach and still be the person's at once: every one-leaf ask of
# 7 October on feeds reached exactly 8, and 7 stops them all (dev/process/meter/auto-evidence.md)


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _held(store, session_id: str) -> list[P.Node]:
    return [n for n in P.nodes(store, (P.RUNNING,)) if n.session_id == session_id]


def _rel(path: str, root: Path, cwd: str | None) -> str | None:
    """Repo-relative for a path in the repo or a worktree of it; None for anywhere else."""
    from .hooks import _map_path  # here, not at the top: that module imports this one

    full = path if os.path.isabs(path) else os.path.join(cwd or str(root), path)
    rel = _map_path(full, root)
    return None if os.path.isabs(rel) or rel.startswith("..") else rel


def _leaves(path: str, root: Path, cwd: str | None) -> str | None:
    """The repo-relative spelling of a path inside the repo whose real file is not: a symbolic link
    (or a directory that is one) pointing out of the repo, or into the plan's own store. A write
    through it would land where no scope reaches, so it is refused whatever the scope says."""
    rel = _rel(path, root, cwd)
    if rel is None:
        return None
    full = path if os.path.isabs(path) else os.path.join(cwd or str(root), path)
    real, home = os.path.realpath(full), os.path.realpath(root)
    if os.path.realpath(os.path.dirname(full)) == os.path.dirname(
        os.path.abspath(full)
    ) and not os.path.islink(full):
        return None  # nothing on the way is a link: the common case, decided without touching git
    inside = _rel(real, Path(home), None)
    return rel if inside is None or inside.split("/", 1)[0] in OURS else None


def _ignored(root: Path, rels: list[str]) -> set[str]:
    """The paths git ignores, asked once for all of them: a command with 250 redirects into build/
    asked 250 times and passed the vendor's hook timeout. Asked only on the way to a refusal."""
    if not rels:
        return set()
    import subprocess  # here: the hook imports this module, and most events never ask git

    argv = ["git", "-C", str(root), "check-ignore", "-z", "--stdin"]
    try:
        out = subprocess.run(argv, input="\0".join(rels) + "\0", capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(filter(None, out.stdout.split("\0")))


def _link(rel: str) -> dict:
    return _deny(f"{rel} is a symbolic link that leaves the repo; no scope covers where it points")


def _how_out(store, sid: object, held: list[P.Node], paths: list[str]) -> str:
    """The way out of a scope refusal. Why (do not work around it; only the person widens a scope) is
    said the first time a session meets it in a hold of that node, and a short line after that: the
    same lecture read twice is noise. TODO: one row a hold that met a refusal, never pruned."""
    import shlex

    n = held[0]
    told = f"told:{sid}:{n.id}:{n.started_at}:scope"
    if store.meta(told):
        wants = " ".join(f"--wants {shlex.quote(p)}" for p in paths[:3])
        return f"`graphene node release {n.id} --why '…' {wants}` hands it back"
    store.set_meta(told, "1")
    return (
        f"If the work cannot be done inside that scope, do not work around it: "
        f"`graphene node release {n.id} --why '<what you need and why>' --wants <a path> --wants <another>` "
        "hands it back, and the person decides whether the scope is wrong. Only they can widen it"
    )


# What a session is told when it starts, plan or no plan: the text the plan is proposed in. The
# person never types the tree; the agent proposes it and the person prunes it. A few lines, because
# every session in a repo with Graphene's hooks reads them.
TEACH = (
    "This repository uses Graphene: a plan the person and their coding agents share, as a tree. You "
    "propose it in this text, and the person prunes it (they see it at once in `graphene watch`):\n"
    "graphene plan propose - <<'EOF'\n"
    "goal: their aim, in one sentence\n"
    "question: what their words leave open and the repo cannot settle  [q-id]\n"
    "    default: what you will assume if they do not answer\n"
    "    option: another way, when there is one\n"
    "    then: goal leaf-id + what the leaf does instead, in a sentence\n"
    "risk: what could make a check pass on nothing, or a leaf go wrong  [r-id]\n"
    "    default: what you would do about it\n"
    "    then: check leaf-id: python3 -m pytest tests/pdf -q\n"
    "- a sub-goal  [short-id]\n"
    "  - a leaf: one piece of work  [leaf-id]\n"
    "      what it should achieve, in a line\n"
    "      scope: src/pdf/**, tests/pdf/**\n"
    "      check: python3 -m pytest tests/pdf -q\n"
    "      needs: other-leaf-id\n"
    "EOF\n"
    "A leaf's scope is every path it may write: look at the repo, never guess one. Its check is a command "
    "that exits 0 only when the leaf is done, and that can pass with what its scope and its needs write. "
    "`needs` orders leaves that build on each other. A leaf's check runs only files in its own scope and "
    "files already in the repository. A leaf that needs a test another leaf writes waits on it with "
    "needs:. Two leaves never share a test file: give each leaf its own, or make one tests leaf that "
    "waits on all of them. Ask instead of guessing, and only what changes the "
    "tree: put up on the board, at the left edge before the tree, at most three items, each a question: "
    "with its default (and option: lines) or a risk: with its default, for what the repo cannot answer, "
    "never what a file answers. An assumption you are confident of is not an item but a sentence in the "
    "goal of the leaf it bears on; never put up an item whose answer would change nothing. Write each "
    "leaf as the default has it; an option (or a default the leaves do not follow) that changes what a "
    "leaf does, which files it may touch or how it is checked carries the then: lines that make the "
    'change (goal LEAF + SENTENCE, scope LEAF + GLOB, check LEAF: COMMAND, drop LEAF, leaf "TITLE" '
    "under NODE), so the answer changes the tree. Only the person "
    "answers them (`graphene board`); what they decide is told to you in your leaf's contract."
)
FREE = (  # plan first off: the session's judgement, and decision 18 while a plan is in force
    "When the person describes work bigger than one quick change, or asks for a plan, do not start it: "
    "read what you need, propose the tree, then stop and tell them it is ready to prune. A quick change "
    "they want done now, just do."
)
IN_FORCE = (
    "A plan is in force here: `graphene plan` shows it and what is ready; `graphene node start <id>` takes "
    "a leaf and tells you what it is for, from the goal down. While you hold a leaf, writes outside its "
    "scope are refused. A leaf too big to do well is split: propose its children in the same text (its "
    "line, with theirs under it) and hand it back."
)
ASIDE = (  # decision 18: plan first off, prompts are leaves
    "When the person asks you here for something no leaf covers, and you hold no leaf, just do it: "
    "Graphene makes a leaf from their prompt and records what you changed."
)


def _first(store) -> str | None:
    """Plan first on or auto, as the person set it (``P.plan_first``): a session that holds no leaf
    writes nothing. None when it is off. A paused plan enforces nothing, this included."""
    how = P.plan_first(store)
    return how if how != "off" and not P.paused(store) else None


def _strict(store) -> bool:
    """`graphene plan prompts strict`: nothing is made or accepted by a prompt; the person accepts."""
    return store.meta("asides") == "off"


# Plan first auto: the agent always proposes, and what it proposed decides whether the person is asked
# first (``one_line_ask``), never the agent's judgment and never the words of the prompt.
AUTO = (
    "Plan first is auto. Before you write, propose what you will do with `graphene plan propose -`: one "
    "leaf or a tree, as the work is. Then do what it prints. When it says your leaf is the person's at "
    "once, run `graphene node start <id>` and do it. Otherwise write nothing, stop, and tell the person "
    "it waits for them in `graphene watch`. Nothing to write, nothing to propose."
)


def _first_said(store, how: str) -> str:
    """Plan first, as a session is told it when it starts and at every prompt while it holds no leaf.
    Nothing here reads the person's words: the agent proposes, and what it proposed decides whether
    the person sees it before the work (``one_line_ask``). Under strict prompts auto is on: no leaf is
    the person's at once."""
    if how == "auto" and not _strict(store):
        return AUTO
    return (
        "Plan first is on: before you write anything, propose what you will do in the plan's text "
        "(`graphene plan propose - <<'EOF' … EOF`) and do what it prints. A piece of work is a tree: "
        "propose it, then stop and tell the person it is ready to prune in `graphene watch`. A one-line "
        "ask is one leaf with its scope and check, a proposal they accept like any other. Nothing to "
        "write, nothing to propose."
    )


def _take(store) -> str:
    """A leaf already planned is taken, not proposed again: the next of an accepted tree, say."""
    ready = P.ready(P.nodes(store), P.Caller("agent", False))
    return (
        f"take a leaf already planned (`graphene node start {ready[0].id}` takes the first that is ready)"
        if ready
        else ""
    )


def _first_refused(store) -> str:
    """The write refused while plan first is on and the session holds no leaf: in a line, and how the
    person turns it off."""
    take = _take(store)
    return (
        "plan first: this session holds no leaf, so it writes nothing yet. Propose what you will do "
        f"(`graphene plan propose -`){f', or {take}' if take else ''}. The person turns plan first off "
        "with P in graphene watch or `graphene plan first off`"
    )


# What Claude Code delivers as a prompt that nobody typed: its own notices, and other agents' words.
_NOT_A_PROMPT = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<task-notification>",
    "<system-reminder>",
    "[Request interrupted",
    "Another Claude session sent a message",  # a subagent's hand-back, delivered as a prompt
    "<agent-message",
)


def _vendor_made(said: str) -> bool:
    """What the vendor sends as a prompt on its own (a finished background task, a reminder, a slash
    command): never the person's words, so it neither starts nor ends anything."""
    from .hooks import _SLASH_COMMAND  # here, not at the top: that module imports this one

    return said.startswith((*_NOT_A_PROMPT, "[SYSTEM NOTIFICATION")) or bool(_SLASH_COMMAND.match(said))


def _session_start(store) -> dict | None:
    """What a new session is told, by the state the plan is in: plan first on or off, a plan in force
    or none, and whether a prompt is a leaf (decision 18) or not (strict)."""
    if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
        return None  # started by `graphene run` or `graphene ask`: its prompt is the whole of its task
    first, force = _first(store), P.in_force(store)
    said = [TEACH, _first_said(store, first) if first else FREE]
    if force:
        said.append(IN_FORCE + ("" if first or _strict(store) else " " + ASIDE))
    return _context("SessionStart", "\n\n".join(said))


def _claim_first(store) -> str:
    ready = P.ready(P.nodes(store), P.Caller("agent", False))
    if ready:
        return (
            f"This repo has a plan in force and this session holds no node, so nothing here may be "
            f"written yet. `graphene plan` shows the plan; `graphene node start {ready[0].id}` takes the "
            "first node that is ready and prints what you may touch and how it is checked"
        )
    running = [f"{n.id} is held by {n.executor}" for n in P.nodes(store, (P.RUNNING,))]
    return (
        "This repo has a plan in force and no node is ready for an agent to take"
        + (f" ({'; '.join(running)})" if running else "")
        + ", so nothing here may be written: work happens inside a node, and a plan stays in force "
        "after its last node is done. If this change is worth making, propose a node for it: "
        "`graphene node add '<what>' --scope '<paths it needs>' --check '<command that shows it is done>'`, "
        "then tell the person: they accept it, change it or drop it in `graphene watch`. "
        "`graphene plan` shows what each node waits for"
    )


# The CLI's own flags, typed into the prompt: `fix the header --scope README.md --check 'make lint'`.
# A review ran prose through the first spelling (`scope:` / `check:` anywhere in the text): "double
# check: ./scripts/deploy.sh is never called" executed the script. Nobody writes `--check` in prose.
_SCOPE = re.compile(r"""(?<!\S)--scope[ =]+(?:'([^']+)'|"([^"]+)"|(\S+))""")
_CHECK = re.compile(r"""(?<!\S)--check[ =]+(?:'([^']+)'|"([^"]+)")""")  # quoted, so its end is said
# `graphene ingest …` as a command, not the word: a repo with an ingest/ package had three hand-backs
# refused for naming ingest/__init__.py in their reason
_HOOK = re.compile(r"\bgraphene\s+ingest\b|\bingest\s+hook\b|\bhook_main\s*\(")
_READS = re.compile(r"\s*(rg|e?grep|git\s+grep|graphene\s+node\s+release)\b")
HOOKS = (".claude/settings.json", ".claude/settings.local.json")


def _me(sid: str) -> P.Caller:
    """What the person types into their own session is taken as the person's act: the vendor hands
    the hook their prompt. It rests on the vendor being the only caller of the hook, and any command
    an agent can run is also a caller: `graphene ingest hook` fed a hand-written event is refused by
    its ordinary spellings (``decide``) and not by a determined one, and an agent that starts a
    second agent chooses its prompt. So every act made this way is logged as made with no terminal,
    "by prompt", with the words; `graphene plan prompts strict` turns the whole route off."""
    return P.Caller(P.person_name(), True, sid, stand_in=True)


def _contract(text: str | None) -> bool:
    """The person typed a leaf's scope and check in the CLI's own flags: that prompt is a leaf they
    wrote themselves, planned already. Syntax, not prose."""
    return bool(text and _SCOPE.search(text) and _CHECK.search(text))


def _on_prompt(store, sid: str, text: str) -> dict | None:
    """A prompt is remembered: with plan first off the next write may become a leaf made from it, and
    either way a one-leaf proposal made after it is the person's ask (``one_line_ask``). With plan
    first on, a session that holds no leaf is told, next to every prompt, to propose before it
    writes. No word of the prompt is read for that: not its length, not "just do it"."""
    if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
        return None  # an executor or a planner Graphene started: its prompt is ours, not a person's
    if _vendor_made(text.strip()):
        return None
    first = _first(store)
    if not first and not store.node_count():
        return None  # no plan and plan first off: a repo without a plan pays a read or two
    for n in _held(store, sid):
        if n.aside:  # the turn before ended without a Stop (interrupted): its record closes here
            _close(store, n, sid)
    store.set_meta(f"prompt_at:{sid}", P._now())
    store.set_meta(f"prompt:{sid}", text)  # TODO: two rows a session, never pruned
    if not first or _held(store, sid) or _contract(text):
        return None
    take = _take(store)
    said = f"Graphene: {_first_said(store, first)}" + (f" Or {take}." if take else "")
    return _context("UserPromptSubmit", said)


def _width(scope: list[str], files: list[str]) -> int:
    """The paths a scope reaches: the tracked files it covers, and one for each glob that covers none
    (a file still to be made)."""
    unmatched = [g for g in scope if not g.startswith("!") and not any(P.in_scope(f, [g]) for f in files)]
    return sum(P.in_scope(f, scope) for f in files) + len(unmatched)


def one_line_ask(
    store, added: list[P.Node], who: P.Caller, files: list[str], board: list[dict], root: Path
) -> str | None:
    """The one-line ask stays free. One leaf, with its scope and its check and nothing under it,
    proposed by a Claude Code session that holds no leaf, after the person's last prompt there and
    before any other proposal of that session since, is what that prompt asked for: it is accepted
    at once, as the person's, and the log says "by their prompt in the session". The sub-goals it
    came in, one above the other with nothing else under them, are accepted with it: they are still
    one leaf of work. A tree waits for them, and so does a leaf that would make a sub-goal of another
    (a split) or bring an older proposal above it along, one put up with a board item still open (in
    its text, ``board``, on the board already or not, or by the session since the prompt), and one whose
    scope reaches more than WIDE paths (the tracked ``files``). Returns what `graphene plan propose`
    says instead of "proposed", or None. A standing path in the scope is refused before this, at
    propose, when git tracks it or a glob names it; one git does not track in ``root``, the checkout
    (an ignored .env), makes the leaf wait. The hole is decision 19's: an agent that starts a second
    agent chooses its prompt, and a subagent carries its session's id. Plan first on and
    `graphene plan prompts strict` turn this off."""
    sid = who.session_id
    asked = store.meta(f"prompt_at:{sid}") if sid and not who.person else None
    if not asked or not added or _strict(store) or P.plan_first(store) == "on" or _held(store, sid):
        return None
    everything = P.nodes(store)
    by_id, under = {n.id: n for n in everything}, P.kids(everything)
    new = {n.id for n in added}
    leaves = [by_id[i] for i in new if not any(m.parent == i for m in everything)]
    if len(leaves) != 1:
        return None
    node = leaves[0]
    came_in = [a for a in P.above(node, by_id) if a.id in new]  # the sub-goals it came in, nearest first
    since = {n.id for n in everything if n.proposed_by == who.name and (n.created_at or "") >= asked}
    parent = by_id.get((came_in[-1] if came_in else node).parent or "")
    if (
        since != new
        or len(came_in) != len(new) - 1
        or not (node.scope and node.check)
        or any(a.state == P.PROPOSED and a.id not in new for a in P.above(node, by_id))
        or (parent is not None and not under.get(parent.id))
    ):
        return None
    from . import board as B  # here, not at the top: no hook event reads the board

    # what the session put up since the prompt, and what its text names, new on the board or not: one
    # still open waits for the person; one the person settled, parked or dropped waits on nothing
    ids, words = {f["id"] for f in board}, {B._one(f["text"]).lower() for f in board}
    items = B.items(store)
    mine = [
        it
        for it in items
        if (it["by"] == who.label and it["created_at"] >= asked)
        or it["id"] in ids
        or B._one(it["text"]).lower() in words
    ]
    # words no item on the board has: their [id] named another item, so they were never put up or settled
    unasked = words - {B._one(it["text"]).lower() for it in items}
    reach = _width(node.scope, files)
    # propose sees what git tracks; a file it does not, ignored or not, is asked of git here, under no lock
    standing = P.standing(store)
    specs = [f":(glob,icase){g}{tail}" for _, g in standing for tail in ("", "/**")]
    near = P._git(root, "ls-files", "-z", "--others", "--", *specs).split("\0") if standing else []
    kept = next((p for p in near if p and P.in_scope(p, node.scope) and P.kept_out_by(p, standing)), None)
    why = (
        "it put up a board item"
        if unasked or any(B.reads(it) == "open" for it in mine)
        else f"its scope reaches {kept}, which the setting `{P.kept_out_by(kept, standing)}` keeps out"
        if kept
        else f"its scope reaches {reach} paths, more than {WIDE}"
        if reach > WIDE
        else None
    )
    if why:
        return (
            f"{len(new)} proposed: it waits for the person: {why}. Nobody can start it until the person "
            "accepts, in `graphene watch`. Tell them it waits, and stop"
        )
    me, said = _me(sid), store.meta(f"prompt:{sid}") or ""
    try:
        with P.undoable(store, me, f"a one-line ask in the session: {said[:40]}"):
            P.accept(store, [node.id], me, told=[], by="prompt", prompt=said[:80])  # as the person's accept
    except P.Refused:
        return None  # its parent is held, say: it waits for the person like any proposal
    return (
        f"{node.id} is accepted, as the person's: one leaf for what they asked in this session is theirs "
        f"at once. `graphene node start {node.id}` takes it"
    )


def _context(event: str, text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _close(store, node: P.Node, sid: str) -> str | None:
    """End a leaf made from a prompt. Returns what is wrong when the person gave a check and it fails."""
    import subprocess

    try:
        P.close_aside(store, node.id, P.Caller(node.executor or f"claude:{sid[:8]}", False, sid))
    except P.Refused as no:
        return str(no)
    except (OSError, subprocess.SubprocessError):
        pass  # git could not answer: the leaf stays open on the plan, which is how it is seen
    return None


def _aside(store, sid: str, cwd: str | None, root: Path) -> P.Node | None:
    """The person typed a request into a session that holds no node, and the agent is about to write
    for it: that request becomes a leaf, held by this session, with nothing for the person to do.
    Its scope and check are what they wrote after `--scope` and `--check`, when they wrote any; else it
    may touch anything and is done when the turn ends, and its record says what it did touch. The
    scope is never guessed from the prose."""
    import subprocess

    text = store.meta(f"prompt:{sid}")
    if not text or os.environ.get("GRAPHENE_NODE") or _strict(store):
        return None
    scope = [next(g for g in m.groups() if g) for m in _SCOPE.finditer(text)]
    check = _CHECK.search(text)
    words = _SCOPE.sub("", _CHECK.sub("", text)).strip() or text
    item = {
        "title": " ".join(words.split())[:72],
        "goal": words[:2000],
        "scope": scope or ["**"],
        "check": next(g for g in check.groups() if g) if check else None,
    }
    made = None
    try:
        argv = ["git", "-C", cwd or str(root), "rev-parse", "--show-toplevel"]
        top = subprocess.run(argv, capture_output=True, text=True, timeout=5).stdout.strip() or str(root)
        [made] = P.propose(store, [item], _me(sid), files=P.tracked(top), aside=True)
        return P.start(store, made.id, P.Caller(f"claude:{sid[:8]}", False, sid), top, attended=True)
    except (P.Refused, OSError, subprocess.SubprocessError) as no:
        if made is not None:  # it could not start: never leave a `**` leaf open for whoever comes next
            P.drop(store, made.id, _me(sid))
        store.log_node("*", P._now(), "denied", None, sid, None, {"note": f"no leaf from the prompt: {no}"})
        return None


def _check_write(
    store, held: list[P.Node], rel: str, event: dict, how: str, root: Path | None = None
) -> dict | None:
    if rel.split("/", 1)[0].casefold() in OURS:  # a disk that ignores case writes .GRAPHENE/ there too
        return _deny(f"{rel} is the plan's own store; no node's scope covers it")
    agent_id = event.get("agent_id") if isinstance(event.get("agent_id"), str) else None
    if not held and root is not None:
        cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
        made = _aside(store, str(event.get("session_id")), cwd, root)
        held = [made] if made else held
    if not held:  # "*" is the plan's own log: what happened that belongs to no node
        store.log_node(
            "*", P._now(), "denied", None, event.get("session_id"), agent_id, {"path": rel, "how": how}
        )
        if os.environ.get("GRAPHENE_PLANNER"):
            return _deny("you are the planner: your only output is the proposal you print. Write no file")
        return _deny(_claim_first(store))
    if rel in HOOKS and all(n.aside for n in held):
        return _deny(
            f"{rel} holds the hooks that keep this plan; a leaf made from a prompt does not reach it. "
            "The person edits it themselves, or plans a leaf whose scope names it"
        )
    said = scope_refused(store, held, rel, event.get("session_id"), how, agent_id)
    return None if said is None else _deny(said)  # inside: say nothing, so the person's own rules apply


def scope_refused(
    store, held: list[P.Node], rel: str, session: object, how: str, agent_id: str | None = None
) -> str | None:
    """Why a write of ``rel`` by whoever holds ``held`` is refused, or None when a scope covers it. The
    refusal is logged on the node, where a hand-back's offers are read from. The Claude Code hook and
    the Nemotron executor's write tools both say it, so an agent of either meets the same words."""
    standing = P.standing(store)
    if any(P.binds(rel, n, standing) for n in held):
        return None
    n = held[0]
    store.log_node(n.id, P._now(), "denied", n.executor, session, agent_id, {"path": rel, "how": how})
    kept = P.kept_out_by(rel, standing)
    if kept:
        return (f"{rel} is kept out of every scope by the setting `{kept}` (`graphene config`); only the "
                "person changes that. Leave it as it is")  # fmt: skip
    scopes = "; ".join(f"{h.id}: {', '.join(h.scope)}" for h in held)
    way_out = _how_out(store, session, held, [rel])
    return f"{rel} is outside the scope of the node you hold ({scopes}). {way_out}"


def _guard_command(event: dict, root: Path) -> dict | None:
    """The shell commands refused whatever the scope: speaking for the person, feeding the hook by
    hand, reaching round `graphene` into its store."""
    if event.get("tool_name") != "Bash":
        return None
    from .hooks import worktree_root

    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    command = str(tool_input.get("command") or "")
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    top = worktree_root(cwd, root) if cwd else None  # a run's worktree: its own path is not the store
    if _AS_PERSON.search(command):
        return _deny(
            "GRAPHENE_AS and GRAPHENE_WATCH are how a script says it speaks for a person at their "
            "terminal; an agent's command may not carry them. Say what you need, and the person decides"
        )
    # a search for the words, or a hand-back that names them in its reason, is not running the hook
    parts = [c for c in re.split(r"[;&|\n]+", command) if not _READS.match(c)]
    if any(_HOOK.search(c) for c in parts):
        return _deny(
            "`graphene ingest` is what the vendor's hooks call, with events only they make; it is "
            "not an agent's to run"
        )
    if ".graphene" in command.replace(top or "\0", "").casefold() and not re.match(r"\s*graphene\s", command):
        return _deny(
            "the plan's own store (.graphene/) is not an agent's to read around or write: use "
            "`graphene plan`, `graphene node show <id>` and `graphene plan log`"
        )
    return None


def _first_write(event: dict, root: Path) -> str | None:
    """The first repo path a tool call would write, as the hook can tell before it runs; None for a
    call that writes nothing here (a read, `graphene plan propose -`, a path outside the repo)."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    if tool in WRITE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return _rel(path, root, cwd) if isinstance(path, str) and path else None
    if tool == "Bash":
        from .shell import bash_written_paths

        command = str(tool_input.get("command") or "")
        if len(command) > PARSED:
            return None
        written = [w for w, _kind in bash_written_paths(command, Path(cwd or root)) if w.strip()]
        rels = [r for r in (_rel(w, root, cwd) for w in written) if r is not None]
        ignored = _ignored(root, rels)
        return next((r for r in rels if r not in ignored), None)
    return None


READ_TOOLS = {"Read", "Grep", "Glob"}


def _protected_read(store, event: dict, root: Path) -> str | None:
    """The protected path a Read, Grep or Glob would reach, or None. A Read names its file; a Grep or a
    Glob reaches every file under its path (a Glob, those its pattern matches), so one that would pass
    over a protected file is refused whole: what a planner reads is sent to its model."""
    from . import settings  # here, not at the top: it imports plan, as this module does

    tool = event.get("tool_name")
    hidden = settings.protected(store) if tool in READ_TOOLS else []
    if not hidden:
        return None
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    path = tool_input.get("file_path" if tool == "Read" else "path") or cwd or str(root)
    rel = _rel(path, root, cwd) if isinstance(path, str) else None
    if rel is None:
        return None
    # what the path reaches, not how it is spelled: a tracked link is followed, and on a disk that
    # ignores case (a Mac's) SECRETS/ is secrets/, so the globs are matched casefolded
    full = path if os.path.isabs(path) else os.path.join(cwd or str(root), path)
    real = _rel(os.path.realpath(full), Path(os.path.realpath(root)), None) or rel
    folded = [g.casefold() for g in hidden]
    for spelled in (rel, real):
        if P.in_scope(spelled.casefold(), folded):
            return spelled
    if tool == "Read":
        return None
    base = "" if real in ("", ".") else real.rstrip("/").casefold() + "/"
    under = [f for f in P.in_tree(root) if f.casefold().startswith(base)]
    pattern = tool_input.get("pattern" if tool == "Glob" else "glob")
    if isinstance(pattern, str) and pattern:  # a Grep's glob with no / matches a name at any depth, as rg's
        named = tool == "Grep" and "/" not in pattern
        under = [f for f in under if P.in_scope(f.rsplit("/", 1)[-1] if named else f[len(base) :], [pattern])]
    return next((f for f in under if P.in_scope(f, hidden)), None)


def decide(store, event: dict, root: Path) -> dict | None:
    """The hook's answer for this event, or None to say nothing."""
    name = event.get("hook_event_name")
    sid = event.get("session_id")
    events = ("PreToolUse", "PostToolUse", "Stop", "SessionStart", "UserPromptSubmit")
    if not isinstance(sid, str) or name not in events:
        return None
    if name == "UserPromptSubmit":  # before "in force": a plan of nothing but proposals binds nobody yet
        return _on_prompt(store, sid, str(event.get("prompt") or ""))
    if name == "SessionStart":  # with or without a plan: this is where a session learns the text
        return _session_start(store)
    planner = bool(os.environ.get("GRAPHENE_PLANNER"))
    # plan first: a session that holds no leaf writes nothing, plan or no plan yet
    first = name == "PreToolUse" and not planner and _first(store) and not _held(store, sid)
    if name == "PreToolUse" and (planner or first or P.in_force(store)):
        guarded = _guard_command(event, root)  # the store and the hooks are nobody's to reach round
        if guarded is not None:
            return guarded
    if name == "PreToolUse" and (planner or first):
        written = _first_write(event, root)
        cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
        # a prompt that typed its own --scope and --check planned its leaf: made at its first write
        planned = first and _contract(store.meta(f"prompt:{sid}"))
        if written is not None and not (planned and _aside(store, sid, cwd, root)):
            how = "planner" if planner else "plan first"
            store.log_node("*", P._now(), "denied", None, sid, None, {"path": written, "how": how})
            return _deny("you are the planner: your only output is the proposal you print. Write no file"
                         if planner else _first_refused(store))  # fmt: skip
    hidden = _protected_read(store, event, root) if name == "PreToolUse" and planner else None
    if hidden is not None:
        store.log_node("*", P._now(), "denied", None, sid, None, {"path": hidden, "how": "planner read"})
        return _deny(f"{hidden} is protected (`graphene config`): the planner never reads it, and so "
                     "never sends it to a model. Search a narrower path, or a glob, that leaves it out")
    if not P.in_force(store):
        return None
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None

    if name == "Stop":
        held = _held(store, sid)
        for n in [h for h in held if h.aside]:
            wrong = _close(store, n, sid)  # the turn is over: the leaf made from the prompt is too
            if wrong:
                return {"decision": "block", "reason": f"{n.id} ({n.title}) is not done: {wrong}"}
        held = [h for h in held if not h.aside]
        if not held:
            return None
        n = held[0]
        store.log_node(n.id, P._now(), "stop_refused", n.executor, sid, None, None)
        return {
            "decision": "block",
            "reason": (
                f"You hold {', '.join(h.id for h in held)} and {'it is' if len(held) == 1 else 'they are'} "
                f"not done. `graphene node done {n.id}` finishes it: Graphene runs the check "
                f"({P.done_means(n)}) and asks git what changed. If it cannot be finished as written, "
                f"`graphene node release {n.id} --why '<what is in the way>'` hands it back. "
                "Then you may stop."
            ),
        }

    if name == "PreToolUse" and tool in WRITE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not (isinstance(path, str) and path):
            return None
        if _leaves(path, root, cwd):
            return _link(_leaves(path, root, cwd))
        rel = _rel(path, root, cwd)
        return None if rel is None else _check_write(store, _held(store, sid), rel, event, tool, root)

    if name == "PreToolUse" and tool == "Bash":
        command = str(tool_input.get("command") or "")
        if len(command) > PARSED:
            return None  # TODO: too long to parse inside the hook's time; `done` asks git anyway
        from .shell import bash_written_paths

        held = _held(store, sid)
        standing = P.standing(store)
        rels = []
        for written, _kind in bash_written_paths(command, Path(cwd or root)):
            if not written.strip():
                continue  # `echo hi > "\n"`: the parser's artefact, not a path anyone can write
            if _leaves(written, root, cwd):
                return _link(_leaves(written, root, cwd))
            from .hooks import ours

            if ours(written, cwd, root):  # the store or the direction, however it is spelled
                return _deny(f"{written} is the plan's own store; no node's scope covers it")
            rel = _rel(written, root, cwd)
            if rel is not None and (rel.split("/", 1)[0].casefold() in OURS or rel in HOOKS):
                # before any scope is asked: `**` does not cover the store, nor the hooks' settings
                return _check_write(store, held, rel, event, "shell")
            bound = held and any(P.binds(rel, n, standing) for n in held)
            if rel is not None and not bound:
                rels.append(rel)
        # a build leftover git ignores is nobody's change; a standing path (an ignored .env) is never one
        ignored = {r for r in _ignored(root, rels) if not P.kept_out_by(r, standing)}
        for rel in rels:
            if rel in ignored or (held and any(P.binds(rel, n, standing) for n in held)):
                continue
            answer = _check_write(store, held, rel, event, "shell", root)
            if answer is not None:
                return answer
            held = _held(store, sid)  # a leaf was just made from the prompt: it covers the rest
        return None

    if name == "PostToolUse" and tool == "Bash":
        held = _held(store, sid)
        response = event.get("tool_response") if isinstance(event.get("tool_response"), dict) else {}
        diff = response.get("bashEditDiff") if isinstance(response.get("bashEditDiff"), dict) else {}
        if not held or diff.get("shared"):  # a list another command's changes leaked into proves nothing
            return None
        changed = [_rel(p, root, cwd) for p in diff.get("changedFiles") or [] if isinstance(p, str)]
        standing = P.standing(store)
        # Graphene's own directory is written by `graphene` (a proposal to the direction): never a stray
        stray = [r for r in changed if r and r.split("/", 1)[0] not in OURS]
        stray = [r for r in stray if not any(P.binds(r, n, standing) for n in held)]
        ignored = {r for r in _ignored(root, stray) if not P.kept_out_by(r, standing)}
        stray = [r for r in stray if r not in ignored]
        if not stray:
            return None
        n = held[0]
        store.log_node(n.id, P._now(), "breach", n.executor, sid, None, {"paths": stray, "how": "shell"})
        return {
            "decision": "block",
            "reason": (
                f"That command changed {', '.join(stray)}, outside the scope of the node you hold "
                f"({n.id}: {', '.join(n.scope)}). Put it back as it was now; `graphene node done` asks "
                f"git and will refuse while it differs. {_how_out(store, sid, held, stray)}"
            ),
        }
    return None
