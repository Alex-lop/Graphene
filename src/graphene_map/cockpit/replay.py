"""`graphene demo`: a recorded run, replayed in the cockpit change by change as it happened.

A recording is the plan's store over a run (demo.py says how it is made and applied), and a replay applies
it to a store of its own, so the cockpit reads it as it reads a live plan: the same rows, the same numbers.
Its clock is the recording's, so a leaf is as quiet or as old as it was. Every key that would change the
plan or start anything answers with one line and does nothing; moving, the details and the help work, and
the replay's own keys: space pauses and plays on, `.` applies the next change and stays paused, `r` plays
it again from the start.
"""

from __future__ import annotations

import asyncio
import json
import signal
import time
from pathlib import Path

from textual.binding import Binding

from .. import demo as D
from ..store import Store
from .app import KEYS, Cockpit
from .help import Help
from .model import Model
from .read import epoch, read

REFUSED = "a replay: nothing runs here"
REPLAY_KEYS = (("space", "pause, or play on"), (".", "the next change, and stay paused"),
               ("r", "play it again from the start"))  # fmt: skip


MILESTONES = ("finished", "landed", "signed_off", "accepted", "proposed", "added", "reopened", "rolled_up")


def news(line: dict) -> str:
    """One recorded change in a person's words: what an agent did or said, why a leaf came back, what landed;
    not the bookkeeping rows (usage, model, attempt, ended) the log also holds. The last three, if more."""
    said = []
    for row in line.get("node_log") or []:
        detail = json.loads(row.get("detail") or "{}")
        kind, node = row["kind"], row["node_id"]
        if kind == "did":
            said.append(f"{node}: {detail.get('verb', '')} {detail.get('target', '')}".strip())
        elif kind == "said":
            said.append(f"{node}: {' '.join(str(detail.get('text', '')).split())[:60]}")
        elif kind == "released":
            said.append(f"{node} came back: {' '.join(str(detail.get('why', '')).split())[:60]}")
        elif kind in MILESTONES:
            said.append(f"{node} {kind.replace('_', ' ')}")
        elif kind == "board":
            said.append(f"{detail.get('act', 'board')} {detail.get('item', '')}".strip())
    return " · ".join(said[-3:]) or D.what(line)


def banner(head: dict, state: str = "") -> str:
    """What the top row says it is: a replay, whether a model made it, which day, and where it is."""
    return " · ".join(filter(None, ["replay", head["shown"], head["day"], state]))


class CockpitReplay(Cockpit):
    BINDINGS = [
        *Cockpit.BINDINGS,
        Binding("space", "pause", show=False, priority=True),
        Binding("full_stop", "next_change", show=False),
        Binding("r", "again", show=False),
    ]

    def __init__(self, repo: Path, head: dict, lines: list[dict]) -> None:
        self.head, self.lines, self.next, self.began = head, lines, 0, 0.0
        self.paused: float | None = None  # when it was paused; None: playing
        self.files: list[str] = []  # what git tracked is the recording's, never asked here
        self.state = ""  # where it is: `3 of 16`, `paused at 3 of 16`, `ended: last frame`
        super().__init__(self.look_at, 1.0, "cockpit", repo, lambda: Store.open(repo))
        self.doer = None  # nothing runs here: every verb says so
        self.refusal = REFUSED
        self.keys = {name: line for name, line in KEYS.items()}
        self.keys["cockpit"] = "space pause · . next · r again · ⏎ everything · g graph · m map · ? keys · q"

    def look_at(self, previous: Model | None) -> Model:
        """The replay's store as the recording had it by now: the recording's clock is its newest row."""
        with Store.open(self.root) as store:
            stamps = [epoch(r["timestamp"]) for r in store.node_log()]
            m = read(store, self.root, previous, now=max(stamps) if stamps else 0.0, files=self.files)
        m.source, m.banner = "replay", banner(self.head, self.state)
        return m

    def on_mount(self) -> None:
        self.began = time.monotonic()
        for sig in (signal.SIGHUP, signal.SIGTERM):  # its terminal closed, or a kill: an exit, which removes
            asyncio.get_running_loop().add_signal_handler(sig, self.exit)  # the replay's repository
        self.play()  # the first change is there when the screen is first drawn
        super().on_mount()
        self.set_interval(0.1, self.play)

    def play(self) -> None:
        """Apply what is due by the replay's clock, and look again when anything was."""
        if not self.is_running:
            return
        # `.` sets the clock to a change's own time, and a float can land a hair before it
        due = (self.paused or time.monotonic()) - self.began + 1e-6
        if self.next == len(self.lines) or self.lines[self.next]["at"] > due:
            return
        said = []
        with Store.open(self.root) as store:
            while self.next < len(self.lines) and self.lines[self.next]["at"] <= due:
                D.apply(store, self.lines[self.next], self.root)
                said.append(news(self.lines[self.next]))
                self.files = self.lines[self.next].get("tracked", self.files)
                self.next += 1
        of = f"{self.next} of {len(self.lines)}"
        self.state = "ended: last frame" if self.next == len(self.lines) else of
        self.look()
        self.model.say(" · ".join(filter(None, said)))  # what changed, in the news
        self.paint()

    def action_help(self) -> None:
        from ..tui import Ask
        from .details import Details

        if not isinstance(self.screen, (Ask, Help, Details)):
            self.push_screen(Help(extra=(("replay", REPLAY_KEYS),)))

    def action_pause(self) -> None:
        """Space: paused, the replay's clock stops where it is; again, it goes on from there."""
        now = time.monotonic()
        if self.paused is None:
            self.paused = now
            self.state = f"paused at {self.next} of {len(self.lines)}"
        else:
            self.began, self.paused = self.began + now - self.paused, None
            self.state = f"{self.next} of {len(self.lines)}"
        self.look()

    def action_next_change(self) -> None:
        """`.`: the next change, now, and the replay stays paused there."""
        if self.next < len(self.lines):
            self.paused = self.paused or time.monotonic()
            self.began = self.paused - self.lines[self.next]["at"]
        self.play()

    def action_again(self) -> None:
        """`r`: the replay's store emptied, and the recording played from its first change."""
        with Store.open(self.root) as store, store.transaction():
            for table in ("nodes", "node_log"):
                store.conn.execute(f"DELETE FROM {table}")
            store.conn.execute(f"DELETE FROM plan_meta WHERE key IN ({', '.join('?' * len(D.META))})", D.META)
        for output in (self.root / ".graphene" / "runs").glob("*"):
            output.unlink()
        self.next, self.began, self.paused, self.files, self.state = 0, time.monotonic(), None, [], ""
        self.play()
