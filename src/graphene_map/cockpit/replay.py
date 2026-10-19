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
from .. import plan as P
from ..store import Store
from .app import KEYS, Cockpit
from .help import Help
from .lines import fit
from .look import short
from .model import Model
from .read import OURS, epoch, read

REFUSED = "a replay: nothing runs here"
REPLAY_KEYS = (("space", "pause, or play on"), (".", "the next change, and stay paused"),
               ("r", "play it again from the start"))  # fmt: skip


# a row of the plan's log as a narrator says it of its task, the task's title in {}; a kind in none of these
# tables (precheck, usage, model, attempt, ended, a run's summary) is bookkeeping and says nothing
MILESTONES = {
    "proposed": "proposed: {}", "accepted": "you accepted {}", "started": "{} started",
    "check_passed": "{}: its check passed", "check_failed": "{}: its check failed", "finished": "{} is done",
    "signed_off": "you signed off {}", "landed": "{} landed", "rolled_up": "{} is done",
    "reopened": "{} reopened", "dropped": "{} dropped", "overruled": "{} is done over its check",
    "added": "{} added",
}  # fmt: skip
GOALS = {"asked": "you asked", "goal_proposed": "proposed goal", "goal": "your goal"}  # its note is the words
ASKS = {"question": "asks", "assume": "assumes", "risk": "flags a risk", "leave out": "leaves out",
        "note": "a note"}  # fmt: skip
TAKES = {"question": "you took the default", "assume": "you confirmed", "risk": "you noted",
         "leave out": "you agreed to leave out"}  # fmt: skip
LISTS = {"scope": ("may now write", "may no longer write"), "needs": ("now waits on", "no longer waits on")}


def words(text) -> str:
    """What someone wrote, on one line, cut with an ellipsis to leave room for the rest of the news."""
    return fit(" ".join(str(text or "").split()), 60)


def news(line: dict, titles: dict[str, str] | None = None) -> str:
    """One recorded change as a narrator says it, each task by its title (``titles``): what an agent did or
    said, a write the gate stopped, why a task came back, what the board asks and what you answered, what
    an edit changed, what was accepted, proven and landed. Bookkeeping (precheck, usage, model, attempt,
    ended, an executor's output, the settings, the agent's own `graphene node` commands) says nothing, so
    the last news stays up. Three at most, in the order they happened: the latest of the rest before an
    agent's moves, so a hand-back is not crowded out by the edits that came before it."""
    titles = titles or {}
    items = {it["id"]: it for it in json.loads((line.get("plan_meta") or {}).get("board") or "[]")}
    said: list[str] = []
    moves: set[int] = set()  # which of them are an agent's own moves: what it did or said
    for row in line.get("node_log") or []:
        d, kind = json.loads(row.get("detail") or "{}"), row["kind"]
        title = titles.get(row["node_id"], row["node_id"])
        if kind == "did" and not OURS.search(str(d.get("target") or "")):
            moves.add(len(said))
            said.append(f"{title}: {d.get('verb', '')} {words(d.get('target'))}")
        elif kind == "said":
            moves.add(len(said))
            said.append(f"{title}: {words(d.get('text'))}")
        elif kind == "denied" and d.get("path"):
            said.append(f"{title}: stopped writing {d['path']}")
        elif kind == "released":
            said.append(f"{title} came back: {words(d.get('why'))}")
        elif kind == "refused" and d.get("outside"):
            said.append(f"{title} is not done: {words(', '.join(d['outside']))} is outside its scope")
        elif kind == "board":
            said.append(board_act(d, items))
        elif kind == "edited":
            said += edit_said(title, d.get("changed") or {}, titles)
        elif kind in GOALS:
            said.append(f"{GOALS[kind]}: {words(d.get('note'))}")
        elif kind in MILESTONES:
            said.append(MILESTONES[kind].format(title))
    kept = sorted(sorted(range(len(said)), key=lambda k: (k not in moves, k))[-3:])
    return " · ".join(said[k] for k in kept)


def board_act(d: dict, items: dict[str, dict]) -> str:
    """A board act in the item's own words: what an agent asks, assumes or leaves out, and what you answered.
    Its row's note is `<act> <item>: <its text>`, and ` → <the answer>` once there is one."""
    act, kind = d.get("act", ""), items.get(d.get("item"), {}).get("kind", "question")
    text, _, answer = str(d.get("note") or "").partition(": ")[2].partition(" → ")
    if act == "put up":
        return f"{ASKS.get(kind, 'asks')}: {words(text)}"
    if act == "took":
        return f"{TAKES.get(kind, 'you took')}: {words(answer if kind == 'question' and answer else text)}"
    if act in ("picked", "answered"):
        return f"you {act}: {words(answer)}"
    return f"{act}: {words(text)}"


def edit_said(title: str, changed: dict, titles: dict[str, str]) -> list[str]:
    """An edit as what it changed: the files the task may write now or no longer, the tasks it waits on now or
    no longer, else the field and its new value."""
    out = []
    for field, (was, now) in changed.items():
        if field not in LISTS:
            out.append(f"{title}: its {field} is now “{words(now)}”")
            continue
        gained = [x for x in now or [] if x not in (was or [])]
        lost = [x for x in was or [] if x not in (now or [])]
        if field == "needs":
            gained, lost = [titles.get(x, x) for x in gained], [titles.get(x, x) for x in lost]
        for phrase, those in zip(LISTS[field], (gained, lost), strict=True):
            if those:
                out.append(f"{title} {phrase} {', '.join(those)}")
    return out


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
        self.keys["cockpit"] = KEYS_PLAYING

    def look_at(self, previous: Model | None) -> Model:
        """The replay's store as the recording had it by now: the recording's clock is its newest row."""
        with Store.open(self.root) as store:
            stamps = [epoch(r["timestamp"]) for r in store.node_log()]
            m = read(store, self.root, previous, now=max(stamps) if stamps else 0.0, files=self.files)
        m.source, m.banner = "replay", banner(self.head, self.state)
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
        of = f"{self.next} of {len(self.lines)}"
        self.state = "ended: last frame" if self.next == len(self.lines) else of
        self.look()
        said = " · ".join(filter(None, (news(line, titles) for line in applied)))
        if said:  # what changed, in the news; bookkeeping says nothing, and the last news stays up
            self.model.say(said)
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
        self.began = time.monotonic() - opening(self.lines)
        self.play()
