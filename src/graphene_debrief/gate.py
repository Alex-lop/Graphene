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
_AS_PERSON = re.compile(r"\bGRAPHENE_AS\b")
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


# What a session is told when it starts, plan or no plan: how the person's paragraph becomes a tree.
# The person never types the tree; the agent proposes it in the text the person prunes. A few lines,
# because every session in a repo with Graphene's hooks reads them.
TEACH = (
    "This repository uses Graphene: a plan the person and their coding agents share, as a tree. When the "
    "person describes work bigger than one quick change, or asks for a plan, do not start it: read what "
    "you need, propose the tree, then stop and tell them it is ready to prune (they see it at once in "
    "`graphene watch`):\n"
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
    "`needs` orders leaves that build on each other. A quick change they want done now, just do."
)
IN_FORCE = (
    "A plan is in force here: `graphene plan` shows it and what is ready; `graphene node start <id>` takes "
    "a leaf and tells you what it is for, from the goal down. While you hold a leaf, writes outside its "
    "scope are refused. A leaf too big to do well is split: propose its children in the same text (its "
    "line, with theirs under it) and hand it back. When the person asks you here for something no leaf "
    "covers, and you hold no leaf, just do it: Graphene makes a leaf from their prompt and records what "
    "you changed."
)


# A paragraph is a piece of work, and a piece of work becomes a tree before any code: the person
# reads the agent's understanding of it, prunes it, and runs it. One line is a Tuesday request, done
# at once (a leaf made from the prompt, decision 18). "just do it" in a paragraph skips the tree;
# while a paragraph waits, a short prompt that says "no plan" lifts the wait too.
PARAGRAPH = 240  # characters: Alex's paragraph on 22 September was 330; his one-line asks, under 100
_JUST = re.compile(r"\b(just do it|do it now|skip the (?:plan|tree)|no need (?:for a|to) plan)\b", re.I)
_NO_PLAN = re.compile(r"\b(no|without a|forget the) (plan|tree)\b(?!\s+(to|for)\b)", re.I)
# "don't just do it", "I can't do it now", "I don't want you to just do it"; not "don't worry, just do it"
_NEGATED = re.compile(
    r"\b(don['’]?t|do not|not|never|can['’]?t|cannot|won['’]?t|shouldn['’]?t|didn['’]?t)"
    r"(?:\s+(?:want|wanted|need|you|me|us|to|going|have))*\s+$",
    re.I,
)
# a paragraph that asks for a leaf already in the plan is a request to do it, not new work
_TAKE = r"\b(?:do|take|start|run|work on|finish|pick up)\s+(?:the\s+)?(?:leaf\s+)?[`'\"]?"
TREE_ASK = (
    "Graphene: the person wrote a paragraph, so this becomes a tree before any code. Read what you need, "
    "then propose the tree with `graphene plan propose -` in the plan's text (the form shown when this "
    "session started: sub-goals, leaves with scope: and check:, needs: between leaves that build on each "
    "other), and stop: tell them it is ready to prune in `graphene watch`, where y accepts and R runs it. "
    "Writing files waits until they accept it and a leaf of it is taken (had they wanted it done at once "
    "they would have said 'just do it')."
)
TREE_WAIT = (
    "The person's paragraph becomes a tree before any code: propose it with `graphene plan propose - "
    "<<'EOF' … EOF` and stop. They prune and accept it in `graphene watch`; its leaves are worked after "
    "that (`graphene node start <id>`, or R there). If what they now ask is not that paragraph's work, "
    "tell them: writing waits until they answer with 'just do it' or 'no plan', or accept a tree"
)


def _vendor_made(said: str) -> bool:
    """What the vendor sends as a prompt on its own (a finished background task, a reminder, a slash
    command): never the person's words, so it neither starts nor ends anything."""
    from .sources.claude_code import _NOT_A_PROMPT, _SLASH_COMMAND

    return said.startswith((*_NOT_A_PROMPT, "[SYSTEM NOTIFICATION")) or bool(_SLASH_COMMAND.match(said))


def _said(pattern: re.Pattern[str], said: str) -> bool:
    """Said and not negated in its own clause."""
    clauses = (re.split(r"[,.;:!?\n]", said[: m.start()])[-1] for m in pattern.finditer(said))
    return any(not _NEGATED.search(clause) for clause in clauses)


def just_do_it(said: str) -> bool:
    """The person's way to skip the tree: "just do it", and not "don't just do it". While a paragraph
    waits, a short answer that says "no plan" or "without a plan" lifts the wait as well; inside a
    paragraph those words are prose ("we have no plan for the feed yet") and skip nothing."""
    return _said(_JUST, said) or (len(said.strip()) < PARAGRAPH and _said(_NO_PLAN, said))


def paragraph(text: str, ready: tuple[str, ...] | list[str] = ()) -> bool:
    """A piece of work as people write one: a paragraph, not a line. Not what the vendor sends, not
    one that says "just do it", and not one that asks for its own leaf: "do <a ready leaf>", or the
    CLI's --scope and quoted --check that a leaf made from the prompt reads. A leaf's id or a
    `--check` flag said in passing ("the ids first", "ruff format --check") is prose."""
    said = text.strip()
    if len(said) < PARAGRAPH or _vendor_made(said) or just_do_it(said):
        return False
    if _SCOPE.search(said) and _CHECK.search(said):
        return False
    return not any(re.search(rf"{_TAKE}{re.escape(i)}(?![\w-])", said, re.I) for i in ready)


def _tree_wait(store, sid: str) -> str | None:
    """What this session is told while its paragraph waits for its tree, or None when it no longer
    waits: it holds a leaf (whose scope binds), or the tree is all done or dropped. The tree is what
    was proposed since the paragraph by this session, the planner (`:ask`) or the person, never by
    another agent's session."""
    since = store.meta(f"tree:{sid}")
    if not since or _held(store, sid):
        return None
    everything = P.nodes(store)
    me = f"claude:{sid[:8]}"
    tree = [
        n
        for n in everything
        if (n.created_at or "") >= since
        and not n.aside
        and (n.proposed_by == me or not (n.proposed_by or "").startswith(("claude:", "codex:")))
    ]
    if not tree:
        return TREE_WAIT
    if all(n.state in (P.DONE, *P.GONE) for n in tree):
        store.set_meta(f"tree:{sid}", None)  # the paragraph is answered
        return None
    ours = {n.id for n in tree}
    ready = [n for n in P.ready(everything, P.Caller("agent", False)) if n.id in ours]
    if ready:
        return (
            "The paragraph's tree is accepted; its leaves are worked one at a time, inside their "
            f"scopes. `graphene node start {ready[0].id}` takes the first that is ready (or the person runs "
            "them with R in `graphene watch`). Nothing is written outside a leaf you hold"
        )
    if any(n.state == P.PROPOSED for n in tree):
        return (
            "The paragraph's tree waits for the person: they prune and accept it in `graphene watch` (y). "
            "Nothing is written before a leaf of it is accepted and taken"
        )
    return "The paragraph's tree is being worked; nothing is written outside a leaf you hold"


def _session_start(store) -> dict | None:
    if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
        return None  # started by `graphene run` or `graphene ask`: its prompt is the whole of its task
    said = TEACH + ("\n\n" + IN_FORCE if P.in_force(store) else "")
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": said}}


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
        "then tell the person; a plain yes typed here accepts it, or they change it or say no. "
        "`graphene plan` shows what each node waits for"
    )


_YES = re.compile(
    r"^\W*(yes|yep|yeah|ok|okay|sure|accept|accepted|approve|approved|go ahead|do it|do that|do them|"
    r"lgtm|sounds good|looks good)\b",
    re.IGNORECASE,
)
# The CLI's own flags, typed into the prompt: `fix the header --scope README.md --check 'make lint'`.
# A review ran prose through the first spelling (`scope:` / `check:` anywhere in the text): "double
# check: ./scripts/deploy.sh is never called" executed the script. Nobody writes `--check` in prose.
_SCOPE = re.compile(r"""(?<!\S)--scope[ =]+(?:'([^']+)'|"([^"]+)"|(\S+))""")
_CHECK = re.compile(r"""(?<!\S)--check[ =]+(?:'([^']+)'|"([^"]+)")""")  # quoted, so its end is said
_NOT_YES = re.compile(r"[?]|\b(but|except|not|no|don'?t|drop|skip|instead|first|before|unless|wrong)\b", re.I)
# `graphene ingest …` as a command, not the word: a repo with an ingest/ package had three hand-backs
# refused for naming ingest/__init__.py in their reason
_HOOK = re.compile(r"\bgraphene\s+ingest\b|\bingest\s+hook\b|\bhook_main\s*\(")
_READS = re.compile(r"\s*(rg|e?grep|git\s+grep|graphene\s+node\s+release)\b")
SHORT = 80  # a prompt longer than this is a request, not an answer
HOOKS = (".claude/settings.json", ".claude/settings.local.json")


def _me(sid: str) -> P.Caller:
    """What the person types into their own session is taken as the person's act: the vendor hands
    the hook their prompt. It rests on the vendor being the only caller of the hook, and any command
    an agent can run is also a caller: `graphene ingest hook` fed a hand-written event is refused by
    its ordinary spellings (``decide``) and not by a determined one, and an agent that starts a
    second agent chooses its prompt. So every act made this way is logged as made with no terminal,
    "by prompt", with the words; `graphene plan prompts strict` turns the whole route off."""
    return P.Caller(P.person_name(), True, sid, stand_in=True)


def _on_prompt(store, sid: str, text: str) -> dict | None:
    """A prompt is remembered (the next write may become a leaf made from it); a paragraph becomes a
    tree first; and a short yes accepts what this session proposed, or the proposals it names."""
    if os.environ.get("GRAPHENE_NODE") or os.environ.get("GRAPHENE_PLANNER"):
        return None  # an executor or a planner Graphene started: its prompt is ours, not a person's
    said = text.strip()
    if _vendor_made(said):
        return None
    planned = store.node_count() > 0
    ready = [n.id for n in P.ready(P.nodes(store))] if planned else []
    routed = paragraph(said, ready)
    if not planned and not routed and not store.meta(f"tree:{sid}"):
        return None  # no plan, no paragraph, nothing waiting: a repo without a plan pays one read
    for n in _held(store, sid):
        if n.aside:  # the turn before ended without a Stop (interrupted): its record closes here
            _close(store, n, sid)
    before = store.meta(f"prompt_at:{sid}") or ""
    store.set_meta(f"prompt_at:{sid}", P._now())
    if just_do_it(said):
        store.set_meta(f"tree:{sid}", None)  # the person lifts the wait
    if routed and not _held(store, sid):
        # a second paragraph while the first still waits (feedback on its tree, "do them in order")
        # keeps the first one's start: the tree proposed in between is still its tree
        store.set_meta(f"tree:{sid}", store.meta(f"tree:{sid}") or P._now())
        store.set_meta(f"prompt:{sid}", None)  # no leaf is made from it: it becomes a tree instead
        return _context("UserPromptSubmit", TREE_ASK)
    store.set_meta(f"prompt:{sid}", text)  # TODO: two rows a session, never pruned
    proposals = P.nodes(store, (P.PROPOSED,))
    if store.meta("asides") == "off" or not proposals or len(text) > SHORT:
        return None
    if not _YES.match(text) or _NOT_YES.search(text) or text.lstrip().startswith("/"):
        return None  # "sure, drop n1", "ok so what is n1?": a yes with a no in it accepts nothing
    named = [n for n in proposals if re.search(rf"(?<![\w.-]){re.escape(n.id)}(?![\w-])", text)]
    if not named and re.search(r"\b(all|everything|the plan)\b", text, re.IGNORECASE):
        named = proposals
    # an unnamed yes answers what this session proposed since the person last spoke, not hours ago
    mine = [n for n in proposals if n.proposed_by == f"claude:{sid[:8]}" and (n.created_at or "") >= before]
    chosen = named or mine
    if not chosen:
        return None
    try:
        with P.undoable(store, _me(sid), f"yes in the session: {text[:40]}"):
            accepted = P.accept(store, [n.id for n in chosen], _me(sid), by="prompt", prompt=text[:SHORT])
    except P.Refused as no:
        return _context(
            "UserPromptSubmit", f"Graphene read that as accepting a proposal, and could not: {no}"
        )
    ready = P.ready(P.nodes(store), P.Caller("agent", False))
    told = ", ".join(f"{n.id} ({n.title})" for n in accepted)
    return _context(
        "UserPromptSubmit",
        f"The person's answer accepted {told}: in the plan now, as they stand."
        + (f" `graphene node start {ready[0].id}` takes the first that is ready." if ready else ""),
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
    Its scope and check are what they wrote after `scope:` and `check:`, when they wrote any; else it
    may touch anything and is done when the turn ends, and its record says what it did touch. The
    scope is never guessed from the prose."""
    text = store.meta(f"prompt:{sid}")
    if not text or os.environ.get("GRAPHENE_NODE") or store.meta("asides") == "off":
        return None
    ready = P.ready(P.nodes(store), P.Caller("agent", False))
    if any(re.search(rf"(?<![\w.-]){re.escape(n.id)}(?![\w-])", text) for n in ready):
        return None  # "do n1": the leaf they named is there to be taken, with its own scope
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
            "GRAPHENE_AS is how a script says it speaks for a person; an agent's command may not "
            "carry it. Say what you need, and the person decides"
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
    if name == "SessionStart":  # with or without a plan: this is where a paragraph learns to be a tree
        return _session_start(store)
    planner = bool(os.environ.get("GRAPHENE_PLANNER"))
    waiting = name == "PreToolUse" and _tree_wait(store, sid)
    if name == "PreToolUse" and (planner or waiting or P.in_force(store)):
        guarded = _guard_command(event)  # the store and the hooks are nobody's to reach round
        if guarded is not None:
            return guarded
    if name == "PreToolUse" and (planner or waiting):
        written = _first_write(event, root)
        if written is not None:
            how = "planner" if planner else "paragraph"
            store.log_node("*", P._now(), "denied", None, sid, None, {"path": written, "how": how})
            return _deny("you are the planner: your only output is the proposal you print. Write no file"
                         if planner else waiting)  # fmt: skip
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
