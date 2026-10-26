"""`graphene demo`: a recorded run, replayed in the cockpit change by change as it happened.

A recording is the plan's store over a run (demo.py says how it is made and applied), and a replay applies
it to a store of its own, so the cockpit reads it as it reads a live plan: the same rows, the same numbers.
Its clock is the recording's, so a leaf is as quiet or as old as it was. Every key that would change the
plan or start anything answers with one line and does nothing; moving, the details and the help work, and
the replay's own keys: space pauses and plays on, `.` applies the next change and stays paused, `r` plays
it again from the start. At the end nothing is left to play, and the news line says what to do next.
"""

from __future__ import annotations

import asyncio
import json
import signal
import time
from pathlib import Path

from textual.binding import Binding

from .. import demo as D
from .. import plan as P
from ..store import Store
from .app import KEYS, Cockpit
from .help import GROUPS, Help
from .look import short
from .model import Model
from .narrate import (  # noqa: F401  (the narrator, as the replay's own names: tests and state.py read them)
    ASKS,
    FIELDS,
    GOALS,
    LISTS,
    MILESTONES,
    TAKES,
    auto_said,
    board_act,
    edit_said,
    item,
    news,
    words,
)
from .read import epoch, read

REFUSED = "a replay: nothing runs here"
REPLAY_KEYS = (("space", "pause, or play on"), (".", "the next change, and stay paused"),
               ("r", "play it again from the start"), ("q", "quit"))  # fmt: skip
# `?` in a replay: its own keys, then only the cockpit's that work in one, the screens (but p, which paints a
# folder to a task) and the marks; every other key acts in your own repo
HELP = (("replay", REPLAY_KEYS),
        ("screens", tuple(("v", "on the map: changes the lens") if key == "v p" else (key, what)
                          for key, what in dict(GROUPS)["screens"])),
        ("marks", dict(GROUPS)["marks"]))  # fmt: skip
HELP_END = "Every other key acts in your own repo, in graphene watch."
NO_DIRECTION = "a replay has no direction: in your own repo, D shows the goals above your plan"


def opening(lines: list[dict]) -> float:
    """When on the replay's clock its first frame is: the first change that puts up a task or a board item,
    so the settings a recording begins with are applied before the screen is first drawn, and it opens on
    the plan."""
    for line in lines:
        if line.get("nodes") or json.loads((line.get("plan_meta") or {}).get("board") or "[]"):
            return line["at"]
    return 0.0


# the replay's own keys first; paused, space says it plays on (a narrow head drops "paused at"; this keeps it)
KEYS_PLAYING = "space pause · . next · r again · i details · g graph · m map · ? keys · q"
KEYS_PAUSED = "space play · . next · r again · i details · g graph · m map · ? keys · q"
KEYS_ENDED = "r again · i details · g graph · m map · ? keys · q"  # the end: nothing is left to play


def banner(head: dict, state: str = "") -> str:
    """What the top row says it is: a replay, whether a model made it, which day, and where it is."""
    return " · ".join(filter(None, ["replay", head["shown"], head["day"], state]))


class CockpitReplay(Cockpit):
    BINDINGS = [
        *Cockpit.BINDINGS,
        Binding("space", "pause", show=False, priority=True),
        Binding("full_stop", "next_change", show=False),
        Binding("r", "again", show=False, priority=True),  # before the cockpit's own r, which would refuse
    ]

    def __init__(self, repo: Path, head: dict, lines: list[dict]) -> None:
        self.head, self.lines, self.next, self.began = head, lines, 0, 0.0
        self.paused: float | None = None  # when it was paused; None: playing
        self.files: list[str] = []  # what git tracked is the recording's, never asked here
        self.state = ""  # where it is: `3 of 16`, `paused at 3 of 16`, `ended: last frame`
        super().__init__(self.look_at, 1.0, "cockpit", repo, lambda: Store.open(repo))
        self.doer = None  # nothing runs here: every verb says so
        self.refusal, self.replay = REFUSED, True
        self.keys = {name: line for name, line in KEYS.items()}
        self.keys["cockpit"] = KEYS_PLAYING
        self.keys["territory"] = "j/k folder · ←/→ task · v lens · c cockpit · ? keys · q"  # no paint

    def look_at(self, previous: Model | None) -> Model:
        """The replay's store as the recording had it by now: the recording's clock is its newest row."""
        with Store.open(self.root) as store:
            stamps = [epoch(r["timestamp"]) for r in store.node_log()]
            m = read(store, self.root, previous, now=max(stamps) if stamps else 0.0, files=self.files)
        m.source, m.banner = "replay", banner(self.head, self.state)
        if m.feed:  # the last news stays up: the clock jumps with the recording's, a quiet change too
            m.feed[-1] = (m.clock, m.feed[-1][1])
        return m

    def on_mount(self) -> None:
        self.began = time.monotonic() - opening(self.lines)
        for sig in (signal.SIGHUP, signal.SIGTERM):  # its terminal closed, or a kill: an exit, which removes
            asyncio.get_running_loop().add_signal_handler(sig, self.exit)  # the replay's repository
        self.play()  # the plan is there when the screen is first drawn
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
        applied = []
        with Store.open(self.root) as store:
            while self.next < len(self.lines) and self.lines[self.next]["at"] <= due:
                D.apply(store, self.lines[self.next], self.root)
                applied.append(self.lines[self.next])
                self.files = self.lines[self.next].get("tracked", self.files)
                self.next += 1
            titles = {n.id: short(n.title) for n in P.nodes(store)}
        of, ended = f"{self.next} of {len(self.lines)}", self.next == len(self.lines)
        self.state = D.ENDED if ended else of if self.paused is None else f"paused at {of}"
        if ended:
            self.keys["cockpit"] = KEYS_ENDED
        self.look()
        models = {tid: {f.letter: f.model for f in t.forks} for tid, t in self.model.tasks.items() if t.forks}
        said = " · ".join(filter(None, (news(line, titles, self.model.names, models) for line in applied)))
        if said:  # what changed, in the news; bookkeeping says nothing, and the last news stays up
            self.model.say(said)
        if ended:  # then the reader's next step: at 80 columns the head has no room for "ended"
            self.model.say(D.NEXT)
        self.paint()

    def action_help(self) -> None:
        from ..tui import Ask
        from .details import Details

        if not isinstance(self.screen, (Ask, Help, Details)):
            self.push_screen(Help(HELP, HELP_END))

    def act(self, action: str) -> None:
        """As the cockpit acts, but D: the direction is a file of your own repo's, and a replay's has none."""
        if action != "direction":
            return super().act(action)
        self.model.say(NO_DIRECTION)
        self.paint()

    def action_pause(self) -> None:
        """Space: paused, the replay's clock stops where it is; again, it goes on from there. Ended, it stays
        ended."""
        if self.next == len(self.lines):
            return
        now = time.monotonic()
        if self.paused is None:
            self.paused = now
            self.state = f"paused at {self.next} of {len(self.lines)}"
        else:
            self.began, self.paused = self.began + now - self.paused, None
            self.state = f"{self.next} of {len(self.lines)}"
        self.keys["cockpit"] = KEYS_PLAYING if self.paused is None else KEYS_PAUSED  # what space does now
        self.look()

    def action_next_change(self) -> None:
        """`.`: the next change, now, and the replay stays paused there."""
        if self.next < len(self.lines):
            self.paused = self.paused or time.monotonic()
            self.began = self.paused - self.lines[self.next]["at"]
            self.keys["cockpit"] = KEYS_PAUSED
        self.play()

    def action_again(self) -> None:
        """`r`: the replay's store emptied, and the recording played from its first change."""
        with Store.open(self.root) as store, store.transaction():
            for table in ("nodes", "node_log"):
                store.conn.execute(f"DELETE FROM {table}")
            store.conn.execute(f"DELETE FROM plan_meta WHERE key IN ({', '.join('?' * len(D.META))})", D.META)
        for output in (self.root / ".graphene" / "runs").glob("*"):
            output.unlink()
        self.next, self.paused, self.files, self.state = 0, None, [], ""
        self.keys["cockpit"] = KEYS_PLAYING
        self.model.moved = False  # it opens as it first did: on what needs you, with no news of its end
        self.model.feed.clear()
        self.began = time.monotonic() - opening(self.lines)
        self.play()
