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
import subprocess
from pathlib import Path

from . import plan as P

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
OURS = (".graphene",)  # the plan's own store: never inside any scope
_AS_PERSON = re.compile(r"\bGRAPHENE_(AS|WATCH)\b")
PARSED = 64_000  # characters of a shell command the hook will parse: the parser is superlinear, and the
# vendor lets a call through when a hook runs out of time (3 MB took 234 s in the closing review)


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
    from .sources.claude_code import _map_path  # here, not at the top: that module imports this one

    full = path if os.path.isabs(path) else os.path.join(cwd or str(root), path)
    rel = _map_path(full, root, cwd, None)
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
    argv = ["git", "-C", str(root), "check-ignore", "-z", "--stdin"]
    try:
        out = subprocess.run(argv, input="\0".join(rels) + "\0", capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(filter(None, out.stdout.split("\0")))


def _link(rel: str) -> dict:
    return _deny(f"{rel} is a symbolic link that leaves the repo; no scope covers where it points")


def _how_out(held: list[P.Node]) -> str:
    n = held[0]
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
    "- a sub-goal  [short-id]\n"
    "  - a leaf: one piece of work  [leaf-id]\n"
    "      what it should achieve, in a line\n"
    "      scope: src/pdf/**, tests/pdf/**\n"
    "      check: python3 -m pytest tests/pdf -q\n"
    "      needs: other-leaf-id\n"
    "EOF\n"
    "A leaf's scope is every path it may write: look at the repo, never guess one. Its check is a command "
    "that exits 0 only when the leaf is done, and that can pass with what its scope and its needs write. "
    "`needs` orders leaves that build on each other."
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


def _first(store) -> bool:
    """Plan first, as the person set it (``P.plan_first``). A paused plan enforces nothing, this
    included."""
    return P.plan_first(store) and not P.paused(store)


def _strict(store) -> bool:
    """`graphene plan prompts strict`: nothing is made or accepted by a prompt; the person accepts."""
    return store.meta("asides") == "off"


def _first_said(store) -> str:
    """Plan first, as a session is told it when it starts and at every prompt while it holds no leaf.
    Nothing here reads the person's words: the agent judges what they asked for, and the tree or the
    leaf it proposes is what the person sees and prunes."""
    taken = "theirs at once, and `graphene node start <id>` takes it"
    one = "a proposal they accept like any other" if _strict(store) else taken
    return (
        "Plan first is on: before you write anything, propose what you will do in the plan's text "
        "(`graphene plan propose - <<'EOF' … EOF`) and do what it prints. A piece of work is a tree: "
        "propose it, then stop and tell the person it is ready to prune in `graphene watch`. A one-line "
        f"ask is one leaf with its scope and check, {one}. Nothing to write, nothing to propose."
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


def _vendor_made(said: str) -> bool:
    """What the vendor sends as a prompt on its own (a finished background task, a reminder, a slash
    command): never the person's words, so it neither starts nor ends anything."""
    from .sources.claude_code import _NOT_A_PROMPT, _SLASH_COMMAND

    return said.startswith((*_NOT_A_PROMPT, "[SYSTEM NOTIFICATION")) or bool(_SLASH_COMMAND.match(said))


def _session_start(store) -> dict | None:
    """What a new session is told, by the state the plan is in: plan first on or off, a plan in force
    or none, and whether a prompt is a leaf (decision 18) or not (strict)."""
    if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
        return None  # started by `graphene run` or `graphene ask`: its prompt is the whole of its task
    first, force = _first(store), P.in_force(store)
    said = [TEACH, _first_said(store) if first else FREE]
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
    return _context("UserPromptSubmit", f"Graphene: {_first_said(store)}" + (f" Or {take}." if take else ""))


def one_line_ask(store, added: list[P.Node], who: P.Caller) -> str | None:
    """The one-line ask stays free. One leaf, with its scope and its check and nothing under it,
    proposed by a Claude Code session that holds no leaf, after the person's last prompt there and
    before any other proposal of that session since, is what that prompt asked for: it is accepted
    at once, as the person's, and the log says "by their prompt in the session". A tree waits for
    them, and so does a leaf that would make a sub-goal of another (a split) or bring a proposal
    above it along. Returns what `graphene plan propose` says instead of "proposed", or None.
    The hole is decision 19's: an agent that starts a second agent chooses its prompt, and a
    subagent carries its session's id. `graphene plan prompts strict` turns this off."""
    sid = who.session_id
    asked = store.meta(f"prompt_at:{sid}") if sid and not who.person else None
    if not asked or len(added) != 1 or _strict(store) or _held(store, sid):
        return None
    everything = P.nodes(store)
    by_id, under = {n.id: n for n in everything}, P.kids(everything)
    node = by_id[added[0].id]
    since = [n.id for n in everything if n.proposed_by == who.name and (n.created_at or "") >= asked]
    parent = by_id.get(node.parent or "")
    if (
        since != [node.id]
        or not (node.scope and node.check)
        or under.get(node.id)
        or any(a.state == P.PROPOSED for a in P.above(node, by_id))
        or (parent is not None and not under.get(parent.id))
    ):
        return None
    me, said = _me(sid), store.meta(f"prompt:{sid}") or ""
    try:
        with P.undoable(store, me, f"a one-line ask in the session: {said[:40]}"):
            P.accept(store, [node.id], me, by="prompt", prompt=said[:80])
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
    if rel.split("/", 1)[0] in OURS:
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
    if any(P.in_scope(rel, n.scope) for n in held):
        return None  # inside the scope: say nothing, so the person's own permission settings still apply
    n = held[0]
    store.log_node(
        n.id, P._now(), "denied", n.executor, event.get("session_id"), agent_id, {"path": rel, "how": how}
    )
    scopes = "; ".join(f"{h.id}: {', '.join(h.scope)}" for h in held)
    return _deny(f"{rel} is outside the scope of the node you hold ({scopes}). {_how_out(held)}")


def _guard_command(event: dict) -> dict | None:
    """The shell commands refused whatever the scope: speaking for the person, feeding the hook by
    hand, reaching round `graphene` into its store."""
    if event.get("tool_name") != "Bash":
        return None
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    command = str(tool_input.get("command") or "")
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
    if ".graphene" in command and not re.match(r"\s*graphene\s", command):
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
        from .attribute import bash_written_paths

        command = str(tool_input.get("command") or "")
        if len(command) > PARSED:
            return None
        written = [w for w, _kind in bash_written_paths(command, Path(cwd or root)) if w.strip()]
        rels = [r for r in (_rel(w, root, cwd) for w in written) if r is not None]
        ignored = _ignored(root, rels)
        return next((r for r in rels if r not in ignored), None)
    return None


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
        guarded = _guard_command(event)  # the store and the hooks are nobody's to reach round
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
        from .attribute import bash_written_paths

        held = _held(store, sid)
        rels = []
        for written, _kind in bash_written_paths(command, Path(cwd or root)):
            if not written.strip():
                continue  # `echo hi > "\n"`: the parser's artefact, not a path anyone can write
            if _leaves(written, root, cwd):
                return _link(_leaves(written, root, cwd))
            rel = _rel(written, root, cwd)
            if rel is not None and (rel.split("/", 1)[0] in OURS or rel in HOOKS):
                # before any scope is asked: `**` does not cover the store, nor the hooks' settings
                return _check_write(store, held, rel, event, "shell")
            if rel is not None and not (held and any(P.in_scope(rel, n.scope) for n in held)):
                rels.append(rel)
        ignored = _ignored(root, rels)  # a build leftover git ignores is nobody's change
        for rel in rels:
            if rel in ignored or (held and any(P.in_scope(rel, n.scope) for n in held)):
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
        stray = [r for r in changed if r and not any(P.in_scope(r, n.scope) for n in held)]
        ignored = _ignored(root, stray)
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
                f"git and will refuse while it differs. {_how_out(held)}"
            ),
        }
    return None
