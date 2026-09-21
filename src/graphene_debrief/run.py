"""`graphene run`: Graphene takes each ready node, hands it to an executor, and decides itself whether
it is done.

The executor is a command the person chooses (`claude -p …`, `codex exec …`, anything that takes a
prompt as its last argument). It is given one node's contract and nothing else. When its process
ends, however it ended, Graphene runs the same boundary as `graphene node done`: git says what
changed, the check says whether it works. Refused, the executor is sent back with the refusal; out
of attempts, the node is handed back with the reason and the run moves on. Nothing here trusts an
exit code or a closing message, and no vendor's ceiling on refused stops applies: the loop is ours.

One node at a time, in the checkout the command was started in.
TODO: no worktree per node and no parallel nodes; add them when two agents must run at once.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from . import plan as P

DEFAULT_WITH = "claude -p --permission-mode acceptEdits"
ATTEMPTS = 3


def prompt_for(node: P.Node, notes: list[str], refusal: str | None, why: list[str] | None = None) -> str:
    lines = [
        "You are doing one leaf of a plan that a person and their agents share. `why` is the path from "
        "the plan's goal down to your leaf, in the person's words: it is what your work is for. The "
        "leaf is the whole of what you are asked to do; the rest of the plan is not yours.",
        "",
        P.contract(node, why),
        *(f"  sent back with: {note}" for note in notes),
        "",
        "Do the work inside the scope. Read anything you need; write only inside the scope. When you "
        f"believe it is done run `graphene node done {node.id}`: it runs the check and asks git what "
        "changed, and tells you what is wrong if it refuses. If it cannot be done as written, run the "
        "`release` command above and say why. Do not start any other node.",
    ]
    if refusal:
        lines += ["", "Your last attempt was not accepted:", refusal]
    return "\n".join(lines)


def command_for(template: str, prompt: str, session: str, again: bool) -> list[str]:
    """The executor's argv. Claude Code is told which session this is, so its hooks hold it to the
    node from its first call and a second attempt resumes with what the first one learned; any other
    executor gets the prompt (refusal included) as its last argument, fresh each time."""
    argv = shlex.split(template)
    if argv and Path(argv[0]).name == "claude":
        argv += ["--resume", session] if again else ["--session-id", session]
    return [*argv, prompt]


def run_plan(
    store,
    checkout: Path,
    template: str = DEFAULT_WITH,
    attempts: int = ATTEMPTS,
    only: list[str] | None = None,
    say: Callable[[str], None] = print,
    logs: Path | None = None,
) -> list[P.Node]:
    """Run every node an agent can reach, in order. Returns the nodes that ended done (or in review)."""
    finished: list[P.Node] = []
    gave_up: set[str] = set()
    # The nodes that exist when the run starts are the run: a plan that grows while it is going (a
    # proposal accepted, or an executor adding nodes) does not make an unattended run unbounded.
    planned = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    while True:
        ready = [
            n
            for n in P.ready(P.nodes(store), P.Caller("agent", False))
            if n.id in planned and n.id not in gave_up and (not only or n.id in only)
        ]
        if not ready:
            return finished
        session = str(uuid.uuid4())
        who = P.Caller(f"run:{shlex.split(template)[0]}", False, session)
        try:
            node = P.start(store, ready[0].id, who, checkout)
        except P.Refused as no:
            say(f"{ready[0].id} cannot start: {no}")
            gave_up.add(ready[0].id)
            continue
        say(f"{node.id} started (revision {node.rev}): {node.title}")
        refusal: str | None = None
        for attempt in range(1, attempts + 1):
            argv = command_for(
                template,
                prompt_for(node, P.notes(store, node.id), refusal, P.trail(store, node)),
                session,
                attempt > 1,
            )
            env = {**os.environ, "GRAPHENE_NODE": node.id}
            env.pop("GRAPHENE_AS", None)  # whoever started the run, the executor speaks for nobody
            try:
                done = subprocess.run(
                    argv, cwd=checkout, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL
                )
            except OSError as no:  # the executor is not installed, or not executable: nothing ran
                P.release(store, node.id, who, f"the executor could not be started: {argv[0]}: {no.strerror}")
                raise P.Refused(
                    f"cannot run `{argv[0]}`: {no.strerror}. {node.id} was handed back untouched; name "
                    "another executor with --with"
                ) from None
            if logs is not None:
                logs.mkdir(parents=True, exist_ok=True)
                (logs / f"{node.id}-{attempt}.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
            say(f"{node.id} attempt {attempt}: the executor ended (exit {done.returncode})")
            current = P.get(store, node.id)
            if current.state in (P.DONE, P.REVIEW):  # it ran `done` itself, and the boundary agreed
                finished.append(current)
                break
            if current.state != P.RUNNING:  # it handed the node back, and said why
                why = (store.node_log(node.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get(
                    "why", ""
                )
                say(f"{node.id} handed back by the executor: {why}")
                gave_up.add(node.id)
                break
            try:
                finished.append(P.finish(store, node.id, who))
                break
            except P.Refused as no:
                refusal = str(no)
                say(f"{node.id} attempt {attempt} refused: {refusal.splitlines()[0]}")
        else:
            P.release(store, node.id, who, f"{attempts} attempts, the last one refused: {refusal}")
            say(f"{node.id} handed back after {attempts} attempts")
            gave_up.add(node.id)
            continue
        if finished and finished[-1].id == node.id:
            state = "done" if finished[-1].state == P.DONE else "finished; it waits for a sign-off"
            say(f"{node.id} is {state}")
