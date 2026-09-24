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

from . import plan as P
from . import plan_text as T
from .run import _splits, command_for

# Read-only: Claude Code's built-in tools cut to the three that read (`--tools`), and none of the MCP
# servers the person has connected (`--strict-mcp-config` with no config: some of them send mail and
# write documents), so its only way to say anything is what it prints. Codex: `codex exec --sandbox
# read-only`.
DEFAULT_PLANNER = "claude -p --tools Read,Grep,Glob --strict-mcp-config"
ATTEMPTS = 2
_FENCE = re.compile(r"^```[ \t]*(\w*)[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
_START = re.compile(r"^(?:goal:|[-*+?][ \t])", re.MULTILINE)

RULES = """\
Print the proposal between a line ```plan and a line ```, in this form:

```plan
goal: their aim, in one sentence (only when the plan above has none)
- a sub-goal  [short-id]
  ? a leaf: one piece of work  [leaf-id]
      what it should achieve, in a line or two
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
- Write no file and start no work: what you print is all of your answer."""


def prompt_for(store, sentence: str, about: str | None = None, split: bool = False) -> str:
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
        lines += ["", "It is about this node:", P.contract(node, P.trail(store, node))]
        last = (store.node_log(about, ("released",)) or [None])[-1]
        if last is not None and not split:
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
    lines += ["", "The plan as it stands:", text.rstrip() or "(empty: nothing is planned yet)", "", RULES]
    return "\n".join(lines)


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


def ask(
    store,
    root: Path,
    sentence: str,
    template: str = DEFAULT_PLANNER,
    about: str | None = None,
    split: bool = False,
    say: Callable[[str], None] = print,
) -> list[str]:
    """Start the planner, read its proposal, add it to the plan as the planner's. Returns what was
    proposed, one line each. A proposal Graphene cannot read goes back to the planner once, with the
    refusal, as a refused executor does."""
    _splits(template)  # bad quoting in --with is one refused line, as it is for `graphene run`
    if about is not None:
        P.get(store, about)  # an unknown id is refused before anything is spent
    session = str(uuid.uuid4())
    argv0 = shlex.split(template)[0]
    who = P.Caller(f"planner:{Path(argv0).name}", False, session)
    store.log_node("*", P._now(), "asked", P.person_name(), None, None, {"note": sentence, "about": about})
    asked = prompt = prompt_for(store, sentence, about, split)
    # git is asked before the plan's write lock is taken, never under it: a hook waiting on the lock
    # gives up after a quarter of a second, and lets the call through
    files = P.tracked(root)
    for attempt in range(1, ATTEMPTS + 1):
        argv = command_for(template, prompt, session, attempt > 1)
        env = {**os.environ, "GRAPHENE_PLANNER": "1"}
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
            tail = printed[-300:] or done.stderr[-300:]
            refusal = f"the planner printed no proposal (exit {done.returncode}): {tail}"
        else:
            try:
                with store.claim():
                    said = T.apply(store, text, who, None, files=files)
            except P.Refused as no:
                refusal = f"Graphene could not read the proposal: {no}"
            else:
                rest = _FENCE.sub("", printed).strip() if _FENCE.search(printed) else ""
                if rest:
                    say(f"the planner says: {' '.join(rest.split())[:600]}")
                return said
        say(refusal)
        # whole again: a planner other than Claude Code starts afresh and knows nothing of the first try
        prompt = f"{asked}\n\nYour last answer was not accepted: {refusal}\nPrint the whole proposal again."
    raise P.Refused(f"no proposal after {ATTEMPTS} tries; nothing was added. {refusal}")
