"""The cockpit's verbs: each is a `graphene` command that exists on its own, run here as the person at
this terminal. A key never does anything a command could not: the line of news says which one ran.

Quick commands run in this process (`tui._cli`: the exit code and what it said). A run or a command that
can take minutes (a check, a planner, an agent) is a process of its own, with its output in
`.graphene/runs/`, so it goes on whatever happens to this screen; the person's marker is set in its
environment so the log says it was typed at a terminal (`plan.caller`).
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .. import run as R
from ..tui import _cli, as_typed
from .model import Model

RUN_WITH = ["--parallel", "4"]  # ready leaves at once, a worktree each, landed here as they pass
SLOW = (["run"], ["ask"], ["node", "split"], ["node", "done"], ["node", "signoff"])


def gist(argv: list[str], code: int, said: str) -> str:
    """One line for the bottom: which command ran and the gist of what it said."""
    lines = [line.strip() for line in said.splitlines() if line.strip() and "(the plan of " not in line]
    first = lines[0] if lines else ""
    for word in argv[1:]:  # `graphene node edit x: x: scope changed` says x once
        first = first.removeprefix(f"{word}: ")
    first = first.removeprefix(f"{' '.join(argv[:2])}: ")
    return f"{'✗ ' if code else ''}graphene {as_typed(argv)}" + (f": {first}" if first else "")


class Doer:
    """Runs the cockpit's commands. ``say`` puts a line on the news; ``look`` asks for the model again;
    ``later`` runs a function on the app's thread (a background command ends on one of its own)."""

    def __init__(self, root: Path, say: Callable[[str], None], look: Callable[[], None],
                 later: Callable[[Callable[[], None]], None] | None = None) -> None:  # fmt: skip
        self.root, self.say, self.look = root, say, look
        self.later = later or (lambda fn: fn())
        self.runs: list[subprocess.Popen] = []

    # -- running a command --------------------------------------------------------------------------

    def run(self, argv: list[str]) -> int:
        """A quick command, now. Says which it was; the model is looked at again after it."""
        code, said = _cli(argv)
        self.say(gist(argv, code, said))
        self.look()
        return code

    def background(self, argv: list[str]) -> Path:
        """A slow command as its own process; when it ends the news says how, and the model is read again."""
        logs = self.root / ".graphene" / "runs"
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / f"{argv[0]}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{len(self.runs)}.txt"
        cli = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
        env = {**os.environ, "GRAPHENE_WATCH": "1" if sys.stdin.isatty() else ""}
        with open(log, "w", encoding="utf-8") as sink:
            proc = subprocess.Popen(
                [sys.executable, "-c", cli, *argv], cwd=self.root, stdin=subprocess.DEVNULL,
                stdout=sink, stderr=subprocess.STDOUT, start_new_session=True, env=env,
            )  # fmt: skip
        self.runs.append(proc)
        self.say(f"graphene {as_typed(argv)}: started (its output: {log.relative_to(self.root)})")
        threading.Thread(target=self._follow, args=(proc, argv, log), daemon=True).start()
        return log

    def _follow(self, proc: subprocess.Popen, argv: list[str], log: Path) -> None:
        code = proc.wait()
        lines = [line.strip() for line in R.tail(log, 400) if line.strip() and "(the plan of " not in line]
        last = lines[-1] if lines else ""
        mark = "✗ " if code else ""
        told = last if last.startswith(argv[0]) else f"{mark}graphene {as_typed(argv[:2])} ended: {last}"
        with contextlib.suppress(Exception):  # the screen may be gone by now
            self.later(lambda: (self.say(told), self.look()))

    def stop(self) -> str:
        """Ctrl-C to a run started here, or to the parallel run this repository has going: it hands back
        what it holds and stops its executors."""
        pids = [p.pid for p in self.runs if p.poll() is None]
        held = R.run_holding(self.root)
        if held is not None:
            ps = ["ps", "-ww", "-o", "command=", "-p", str(held)]
            shown = subprocess.run(ps, capture_output=True, text=True)
            if "graphene" in shown.stdout:
                pids.append(held)
        for pid in set(pids):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGINT)
        said = "no run to stop"
        if pids:
            said = f"stopping {len(set(pids))} run(s): what they hold goes back to the plan"
        self.say(said)
        return said

    # -- the verbs ----------------------------------------------------------------------------------

    def take(self, m: Model, sel: str) -> None:
        """Enter on a row that waits for the person: take the default, sign off, accept, try again."""
        q = next((q for q in m.questions if q.id == sel), None)
        if q:
            self.run(["board", "take", q.id])
            return
        t = m.tasks.get(sel)
        if t is None:
            return
        if t.state == "review":
            self.background(["node", "signoff", t.id])  # runs the roll-up check: minutes
        elif t.state == "proposed":
            self.run(["plan", "accept", t.id])
        elif t.state == "yours":
            self.background(["node", "done", t.id])
        elif t.state == "came back":
            self.background(["run", *RUN_WITH, "--node", t.id])
        elif t.state == "ready":
            self.say(f"{t.title} is ready and waits for no one: r runs it, R runs every ready leaf")
        else:
            self.say(f"{t.agent or t.title} is {t.state}: nothing to take")

    def pick(self, m: Model, sel: str, n: int) -> None:
        q = next((q for q in m.questions if q.id == sel), None)
        if q is None or not 1 <= n <= len(q.options):
            self.say("pick needs a question and one of its numbers")
            return
        self.run(["board", "pick", q.id, str(n)])

    def answer(self, m: Model, sel: str, words: str) -> None:
        q = next((q for q in m.questions if q.id == sel), None)
        if q is None or not words.strip():
            return
        self.run(["board", "answer", q.id, words.strip()])

    def tell(self, m: Model, sel: str, words: str) -> None:
        """A note about the task: told to its executor with its next write or command, once."""
        t = m.tasks.get(sel)
        if t is None or not words.strip():
            self.say("select a task to tell")
            return
        self.run(["board", "note", words.strip(), "--about", t.id])

    def widen(self, m: Model, sel: str) -> None:
        """Give a task the paths its gate stopped (or, for a leaf that came back, the ones it wanted):
        `graphene node widen`, which takes exactly what is on record and nothing more."""
        t = m.tasks.get(sel)
        if t is None:
            return
        if not t.stopped and "w" not in t.offers:
            self.say("nothing was stopped, so nothing to allow")
            return
        self.run(t.offers.get("w") or ["node", "widen", t.id])

    def offer(self, m: Model, sel: str, key: str) -> None:
        """A key a leaf that came back offers (b a sibling for what it wanted, n wait on another, r reopen
        the owner): the command it names."""
        t = m.tasks.get(sel)
        if t is None or key not in t.offers:
            who = (t.agent or t.title) if t else "this"
            self.say(f"{who} has no '{key}' to offer: it did not come back wanting one")
            return
        self.run(t.offers[key])

    def pull_back(self, m: Model, sel: str) -> None:
        t = m.tasks.get(sel)
        if t is None or t.state != "running":
            self.say("x pulls back a task that is running")
            return
        self.run(["node", "release", t.id, "--why", "the person pulled it back, from graphene watch"])

    def paint(self, m: Model, sel: str, folder: str) -> None:
        """Give the task a folder, or take it back: its scope gains or loses the folder's glob."""
        t = m.tasks.get(sel)
        if t is None or not folder:
            self.say("select a task first")
            return
        glob = folder + "**" if folder != "(root)" else "*"
        if glob in t.scope:
            self.run(["node", "set", t.id, *[a for g in t.scope if g != glob for a in ("--scope", g)]])
        else:
            self.run(["node", "set", t.id, "--add-scope", glob])

    def run_ready(self, node_id: str | None = None) -> None:
        self.background(["run", *RUN_WITH, *(["--node", node_id] if node_id else [])])

    def drop(self, m: Model, sel: str) -> None:
        """d on a proposal drops it; on a question, the board drops it. Work already accepted is never one key
        away from leaving the plan: typed, `:node drop ID` does it, and the engine says what waits on it."""
        t = m.tasks.get(sel)
        if any(q.id == sel for q in m.questions):
            self.run(["board", "drop", sel])
        elif t is not None and t.state == "proposed":
            self.run(["node", "drop", sel])
        elif t is not None:
            self.say(f"d drops a proposal or a question; {t.title} is {t.state}: `:node drop {t.id}` does")

    def reopen(self, m: Model, sel: str, note: str) -> None:
        """Send a finished or reviewed leaf back, with what is wrong: its next executor is told."""
        if sel in m.tasks and note.strip():
            self.run(["node", "reopen", sel, "--note", note.strip()])

    def command(self, text: str) -> None:
        """The `:` line: any graphene command as typed. What can take minutes is a process of its own,
        `stop` stops the runs, and what needs a terminal (watch, init) says so."""
        words = text.strip().removeprefix(":").strip().removeprefix("graphene ").strip()
        if not words:
            return
        if re.match(r"ask\s", words):  # a sentence, not shell words: apostrophes are the person's
            self.background(["ask", words[3:].strip()])
            return
        try:
            argv = shlex.split(words)
        except ValueError as no:
            self.say(f"✗ {no}")
            return
        if argv[:1] == ["stop"]:
            self.stop()
        elif argv[:1] in (["watch"], ["ingest"], ["init"]):
            self.say(f"✗ `graphene {argv[0]}` takes a terminal of its own: run it outside this screen")
        elif any(argv[: len(slow)] == slow for slow in SLOW):
            self.background(argv)
        else:
            self.run(argv)

    def split(self, m: Model, sel: str) -> None:
        """s: the planner splits a leaf still to do. It spends, so never one that runs, waits for sign-off
        or is done."""
        t = m.tasks.get(sel)
        if t is None:
            self.say("select a leaf to split")
        elif t.state in ("running", "review", "done"):
            self.say(f"✗ {t.title} is {t.state}: s splits a leaf still to do, so no planner was started")
        else:
            self.background(["node", "split", t.id])

    def plan_first(self, m: Model) -> None:
        """P: plan first goes on, auto, off, round (strictest to loosest)."""
        order = ("on", "auto", "off")
        now = m.first if m.first in order else "off"
        self.run(["plan", "first", order[(order.index(now) + 1) % 3]])

    def undo(self) -> None:
        self.run(["plan", "undo"])
