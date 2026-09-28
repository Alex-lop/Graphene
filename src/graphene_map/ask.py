"""`graphene ask`: a planner for when the person is not in a session.

A planner is an executor whose scope is the plan. It is started the way `graphene run` starts one,
with the command the person names, and it is given read-only tools: it reads the repo and prints a
proposal in the plan's text. Graphene reads the proposal from what it printed and adds it to the
plan as the planner's, every line a proposal the person prunes. It writes no file, holds no leaf and
accepts nothing; the hooks refuse it a write and `start` refuses it a leaf, by the mark it carries.

`graphene node split <id>` is the same, asked to cut one leaf into leaves under it; `--about <id>`
asks it about a leaf that came back.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from . import board as B
from . import cover, precheck
from . import plan as P
from . import plan_text as T
from .run import _splits, command_for

# Read-only: Claude Code's built-in tools cut to the three that read (`--tools`), and none of the MCP
# servers the person has connected (`--strict-mcp-config` with no config: some of them send mail and
# write documents), so its only way to say anything is what it prints. Codex: `codex exec --sandbox
# read-only`.
DEFAULT_PLANNER = "claude -p --tools Read,Grep,Glob --strict-mcp-config"
ATTEMPTS = 2


def named(spec: str | None) -> str:
    """What --with names, as the planner to start: `nemotron [options]` is Graphene's own planner on
    Token Factory; `claude` and `codex` alone are those agents with read-only tools; anything else is a
    command, as it is."""
    spec = (spec or "").strip()
    if spec.split(None, 1)[:1] == ["nemotron"]:
        from .planner import template

        return template(spec)
    return {"": DEFAULT_PLANNER, "claude": DEFAULT_PLANNER, "codex": "codex exec --sandbox read-only"}.get(
        spec, spec
    )


def label(template: str) -> str:
    argv = shlex.split(template)
    return "nemotron" if "graphene_map.planner" in argv else Path(argv[0]).name


_FENCE = re.compile(r"^```[ \t]*(\w*)[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
_START = re.compile(r"^(?:goal:|question:|assume:|risk:|leave out:|note:|[-*+?][ \t])", re.MULTILINE)

RULES = """\
Print the proposal between a line ```plan and a line ```, in this form:

```plan
goal: their aim, in one sentence (only when the plan above has none)
question: what the words leave open and the repository cannot settle  [short-id]
    default: what you will assume if the person does not answer
    option: another reasonable way (a line each, only when there is more than one)
    then: scope leaf-id + pyproject.toml
    about: leaf-id
risk: what could make a check pass on nothing, or a leaf go wrong  [short-id]
    default: what you would do about it
    then: check leaf-id: python3 -m pytest tests/pdf -q
- a sub-goal  [short-id]
  ? a leaf: one piece of work  [leaf-id]
      what it should achieve, in a line or two; what you assumed for it, in a sentence
      scope: src/pdf/**, tests/pdf/**
      check: python3 -m pytest tests/pdf -q
      needs: other-leaf-id
```

- A leaf is one piece of work one agent can finish in a sitting. Its scope is every path it may write:
  read the repo to find them, never guess. Its check is a command, run with bash from the repo root,
  that exits 0 only when the leaf is done, and that can pass with what its scope and its needs write.
  Use the repo's own test runner and files that exist or that the leaf creates.
- A leaf whose check needs another leaf's work says so with needs:. Two leaves never share a path.
- To put new lines under a node already in the plan, write that node's line as it is above, with its
  [id], and your lines under it. You cannot change a node that is there; say what should change in a
  sentence after the block, and the person decides.
- Mark every new line "?". Keep ids short, lower case, with dashes.
- Read the repository before you ask anything. Never ask what it answers: name the file that answers
  it in the leaf instead. The board carries only what changes the tree: put up at most three items,
  the most important first, at the left edge after the goal and before the first node, and none when
  nothing is open. Each is a question: for what the person's words leave open and the code cannot
  settle, with the default you would assume (and option: lines when there is more than one reasonable
  way), or a risk: for what could go wrong, with the default you would do about it. An assumption you
  are confident of is not an item: write it as a sentence in the goal of the leaf it bears on. Never
  put up an item whose answer would change nothing in the tree. What is on the board above is answered
  or waiting: do not write it again.
- A then: line under a default: or option: is what choosing it changes in the plan: scope NODE +
  GLOB, check NODE: COMMAND, goal NODE + "SENTENCE", drop NODE, leaf "TITLE" under NODE, or condition
  GLOB (no leaf may write it); NODE is an [id] in the plan or in your block. Write each leaf as the
  default has it. Every option, and every default the leaves do not already follow, that changes what
  a leaf does, which files it may touch or how it is checked carries the then: lines that make that
  change (goal for what the leaf does instead, scope, check, drop, leaf), so choosing it changes the
  tree and the person never rewrites a leaf by hand. An item none of whose answers carries a then:
  line changes nothing: do not put it up.
- Write no file and start no work: what you print is all of your answer."""


def prompt_for(
    store,
    sentence: str,
    about: str | None = None,
    split: bool = False,
    root: Path | None = None,
    files: list[str] | None = None,
    size: str | None = None,
    talk: str | None = None,
) -> str:
    """What the planner is told. `size` is this ask's (--finer/--coarser), else the saved one."""
    from . import settings, sizing

    text, _ = T.render(store)
    lines = [
        "You are the planner for a plan that a person and their coding agents share (Graphene). The "
        "person has said what they want; you read the repository and propose the tree of work, which "
        "they will prune before anything runs.",
        "",
        f"The person said: {sentence}",
    ]
    if about:
        node = P.get(store, about)
        told = P.contract(node, P.trail(store, node), B.decided(store, node))
        lines += ["", "It is about this node:", told]
        last = (store.node_log(about, ("released",)) or [None])[-1]
        if last is not None and not split and not talk:
            wanted = P.wanted(store, node)
            lines += [
                f"It came back from its executor: {last['detail'].get('why', '')}",
                *([f"It wanted, outside its scope: {', '.join(wanted)}"] if wanted else []),
                "Propose what would let it be done: new leaves beside or under it, with needs: where one "
                "must come first; and say after the block whether its own scope or check should change.",
            ]
        if split:
            lines.append(
                f"Split {about} into smaller leaves: write its line with its [{about}], and the new leaves "
                "under it; together they do all of it, and its check still says it is done."
            )
    lines += ["", talk] if talk else []
    lines += ["", "The plan as it stands:", text.rstrip() or "(empty: nothing is planned yet)", ""]
    gone = B.dropped(store)
    if gone:
        lines += ["The person dropped these from the board; do not put them up again:"]
        lines += [f"- {words}" for words in gone] + [""]
    conditions = settings.conditions_for_planner(store)  # the size is said once, by sizing.measure
    if conditions:
        lines += ["The person's standing conditions:", conditions, ""]
    if root is not None and about is None:  # a split or a follow-up is about one node, not the whole tree
        files = P.tracked(root) if files is None else files
        lines += [sizing.measure(root, sentence, files, size or settings.size(store)), ""]
    lines.append(RULES)
    return "\n".join(lines)


def talking(store, kind: str, ids: list[str]) -> str:
    """What the planner is asked when the person talks on the tree (`graphene talk`), after the node
    it is about: why it is there (a note on the board), one leaf for several (merge), or another way
    to reach what it is for. Whether to merge, or which way, is the person's: Graphene puts that
    question on the board itself, so the planner is asked for the leaves only."""
    node = P.get(store, ids[0])
    under = (
        f"write {node.parent}'s line as it is above, with its [{node.parent}], and under it"
        if node.parent
        else "at the left edge, write"
    )
    if kind == "why":
        taken = {it["id"] for it in B.items(store)} | {n.id for n in P.nodes(store)}
        return (
            f"Say why {ids[0]} is in the plan: what it is for, and why its scope and check are what they "
            "are, in two or three sentences, from the plan and the repository. Print it as a note on the "
            f"board about it; the whole block is:\n```plan\nnote: what you would say  "
            f"[{T.slug(f'why {ids[0]}', taken)}]\n    about: {ids[0]}\n```"
        )
    if kind == "merge":
        others = [P.get(store, i) for i in ids[1:]]
        others = [P.contract(n, P.trail(store, n), B.decided(store, n)) for n in others]
        return "\n".join([
            "And about these:", *others,
            f"Propose one leaf that does all of {', '.join(ids)}: its scope takes in theirs, and its check "
            f"says all of it is done. {under[0].upper()}{under[1:]} that one new leaf, and nothing else.",
        ])  # fmt: skip
    return (
        f"Propose another way to reach what {ids[0]} is for: {under} one new leaf, or one new sub-goal "
        f"with its leaves, that would do it by other means in place of {ids[0]} and all under it; and "
        "nothing else."
    )


def proposal_in(said: str) -> str:
    """The proposal in what the planner printed: its last fenced block, or else everything from the
    first line that reads as the plan's text."""
    blocks = _FENCE.findall(said)
    marked = [body for label, body in blocks if label.lower() == "plan"]
    plain = [
        body for label, body in blocks if label.lower() in ("", "text", "graphene") and _START.search(body)
    ]
    if marked or plain:  # the block it was asked for, else the last one that reads as the plan
        return (marked or plain)[-1]
    start = _START.search(said)
    return said[start.start() :] if start else ""


def reask_argv(store, size: str) -> list[str] | None:
    """The command a screen's re-ask key runs: the last sentence asked of a planner (not a follow-up
    about one node), again, sized finer or coarser. None when nothing was asked yet."""
    asked = [r["detail"] for r in store.node_log("*", ("asked",)) if not (r["detail"] or {}).get("about")]
    return ["graphene", "ask", asked[-1]["note"], f"--{size}"] if asked else None


def _replace_last(store) -> list[str]:
    """Drop the planner's proposals still waiting on the person: `ask --finer/--coarser` gives one tree
    to prune in their place, not a second beside them. Returns the ids dropped."""
    pending = [n for n in P.nodes(store, (P.PROPOSED,)) if (n.proposed_by or "").startswith("planner:")]
    ids = {n.id for n in pending}
    dropped = []
    for n in [n for n in pending if n.parent not in ids]:  # a sub-goal goes with what is under it
        try:
            P.drop(store, n.id, P.caller())
            dropped.append(n.id)
        except P.Refused:
            pass  # something accepted waits on it: it stays, and the person sees both
    return dropped


def ask(
    store,
    root: Path,
    sentence: str,
    template: str = DEFAULT_PLANNER,
    about: str | None = None,
    split: bool = False,
    say: Callable[[str], None] = print,
    size: str | None = None,
    talk: str | None = None,
) -> list[str]:
    """Start the planner, read its proposal, add it to the plan as the planner's. Returns what was
    proposed, one line each. A proposal Graphene cannot read goes back to the planner once, with the
    refusal, as a refused executor does."""
    _splits(template)  # bad quoting in --with is one refused line, as it is for `graphene run`
    if about is not None:
        P.get(store, about)  # an unknown id is refused before anything is spent
    session = str(uuid.uuid4())
    argv0 = label(template)
    who = P.Caller(f"planner:{argv0}", False, session)
    store.log_node("*", P._now(), "asked", P.person_name(), None, None, {"note": sentence, "about": about})
    # git is asked before the plan's write lock is taken, never under it: a hook waiting on the lock
    # gives up after a quarter of a second, and lets the call through
    files = P.tracked(root)
    asked = prompt = prompt_for(store, sentence, about, split, root, files, size, talk)
    if size and about is None and not split and _replace_last(store):  # asked again, finer or coarser
        asked = prompt = prompt.replace(
            RULES, f"This replaces the tree you proposed last, which the person wants {size}; it is "
            "dropped, so propose the whole tree afresh.\n\n" + RULES)  # fmt: skip
    for attempt in range(1, ATTEMPTS + 1):
        argv = command_for(template, prompt, session, attempt > 1)
        env = {**os.environ, "GRAPHENE_PLANNER": "1"}
        if argv0 != "nemotron":  # only Graphene's own planner calls Token Factory
            env["GRAPHENE_KEYCHAIN"] = "off"
        env.pop("GRAPHENE_AS", None)
        env.pop("GRAPHENE_NODE", None)
        say(f"asking the planner ({argv0}){' again' if attempt > 1 else ''}…")
        try:
            done = subprocess.run(
                argv, cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True
            )
        except OSError as no:
            raise P.Refused(f"cannot run `{argv0}`: {no.strerror}; name a planner with --with") from None
        printed = done.stdout.strip()
        text = proposal_in(printed)
        if not text.strip():
            said = [line for line in done.stderr.splitlines() if line.strip()]  # its last word, whole
            tail = printed[-300:] or (said[-1][:300] if said else "it said nothing")
            refusal = f"no proposal (exit {done.returncode}): {tail}"
        else:
            try:
                with store.claim():
                    said = T.apply(store, text, who, None, files=files)
            except P.Refused as no:
                refusal = f"Graphene could not read the proposal: {no}"
            else:
                rest = _FENCE.sub("", printed).strip() if _FENCE.search(printed) else ""
                if rest:  # its lines as it wrote them (a list stays a list), not run together
                    lines = [" ".join(line.split()).replace("**", "") for line in rest.splitlines()]
                    said_lines = [line for line in lines if line][:12]
                    say("the planner says:")
                    for line in said_lines:
                        say(f"  {line[:300]}")
                if about is None:  # GRAPHENE_SHAPE: what reads the proposal once it has landed
                    cover.after_ask(store, sentence, say)
                said += precheck.after_proposal(store, root, said.ids)  # GRAPHENE_SHAPE=precheck, after it
                return said
        if done.returncode == 3 and not text.strip():  # it could not work at all; again would not help
            raise P.Refused(f"nothing was added. {refusal}")
        say(refusal)
        # whole again: a planner other than Claude Code starts afresh and knows nothing of the first try
        prompt = f"{asked}\n\nYour last answer was not accepted: {refusal}\nPrint the whole proposal again."
    raise P.Refused(f"no proposal after {ATTEMPTS} tries; nothing was added. {refusal}")
