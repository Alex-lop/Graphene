"""The cockpit's model: what the plan's store says, shaped for the screens, and what the person has selected.

The data is rebuilt from the store on every look (`read.py`); the selection, the lens and the line of news
belong to the person and survive it. The screens never touch the store: they take the model, so a test
builds one by hand and a frame is a function of it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from . import territory as T
from .look import PALETTE, SPARK, color_of, name_for

LIVE_STATES = ("running", "ready", "review", "proposed", "came back", "waiting", "yours")
NEEDS_YOU = ("review", "came back", "yours")  # where the move is the person's


@dataclass
class Ev:
    t: float  # seconds, on the model's clock
    kind: str  # read, edit, run, search, said, you, stop
    text: str = ""
    path: str = ""


@dataclass
class Task:
    id: str
    title: str  # a short name (look.short)
    state: str = "waiting"  # running, review, came back, ready, waiting, proposed, done
    scope: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    agent: str = ""  # the name its agent goes by while it holds the leaf
    checks: int = 1  # the proofs it has to pass: its check, and your sign-off when it asks for one
    passed: int = 0
    events: list[Ev] = field(default_factory=list)
    touched: dict[str, float] = field(default_factory=dict)  # path -> when, for the files edited so far
    stopped: list[tuple[str, float]] = field(default_factory=list)  # writes the gate refused: path, when
    changed: list[str] = field(default_factory=list)  # what a finished task changed
    told: list[tuple[str, float, float]] = field(default_factory=list)  # text, sent, heard (0 = not yet)
    note: str = ""  # why it came back
    full: str = ""  # the whole title
    why: str = ""  # the path down from the goal
    hears: bool = True  # whether its executor is told a note mid-run (a Claude Code session with hooks)
    started: float = 0.0  # when its agent took it, on the model's clock; 0 before
    idle: float | None = None  # seconds since its last sign of life (`run.live`); None: no sign at all
    outside: list[str] = field(default_factory=list)  # touched files its scope does not cover
    offers: dict[str, list[str]] = field(default_factory=dict)  # a came-back leaf: key -> command


@dataclass
class Question:
    id: str
    text: str
    default: str
    options: list[str]
    about: str = ""
    kind: str = "question"  # or "risk"


class Model:
    def __init__(self, goal: str = "", source: str = "plan") -> None:
        self.source, self.goal = source, goal
        self.files: list[str] = []
        self.files_at = 0.0  # when `files` was read (seconds, on the model's clock)
        self.protected: list[str] = []
        self.tasks: dict[str, Task] = {}
        self.questions: list[Question] = []
        self.extra_edges: list[tuple[str, str, str]] = []  # a, b, kind: loops and two-way links
        self.folded_done = 0  # finished tasks the rows leave out, counted
        self.clock = 0.0  # now, as the events' times are told
        self.selected = ""  # a task id or a question id
        self.moved = False  # the person has chosen a row: until then the selection follows what needs them
        self.lens = "plan"
        self.first = ""  # plan first, as the person set it: on, auto or off
        self.banner = ""  # what the top row says it is, when it is not "your plan" (a replay)
        self.feed: list[tuple[float, str]] = []
        self.names: dict[str, str] = {}  # an agent's key (its session) -> its name, kept across looks
        self.seen: dict[str, tuple[float, list[str]]] = {}  # a leaf -> when git was asked, what it said
        self._allowed: dict[tuple[str, tuple[str, ...]], int] = {}

    # -- reading ---------------------------------------------------------------------------------

    def say(self, text: str) -> None:
        self.feed.append((self.clock, text))
        del self.feed[:-6]

    def latest(self, within: float = 6.0) -> str:
        return self.feed[-1][1] if self.feed and self.clock - self.feed[-1][0] <= within else ""

    def order(self) -> list[tuple[str, str]]:
        """The cockpit's rows in the order a person should look at them: (kind, id)."""
        rows: list[tuple[str, str]] = [("question", q.id) for q in self.questions]
        need = [t for t in self.tasks.values() if t.state in NEEDS_YOU]
        rest = {
            s: [t for t in self.tasks.values() if t.state == s]
            for s in ("running", "ready", "waiting", "proposed", "done")
        }
        rows += [("task", t.id) for t in need]
        for s in ("running", "ready", "waiting", "proposed", "done"):
            rows += [("task", t.id) for t in rest[s]]
        return rows

    def scoreboard(self) -> tuple[int, int, int, int]:
        """(need you, running, proven, total): proven counts finished tasks, folded ones included."""
        need = len(self.questions) + sum(1 for t in self.tasks.values() if t.state in NEEDS_YOU)
        running = sum(1 for t in self.tasks.values() if t.state == "running")
        done = self.folded_done + sum(1 for t in self.tasks.values() if t.state == "done")
        return need, running, done, self.folded_done + len(self.tasks)

    def allowed(self, t: Task) -> int:
        """How many files the task's scope allows: the tracked ones it covers (protected folders left out, as
        for the gate), and one for each glob that covers none, a file still to be made."""
        key = (t.id, tuple(t.scope))
        if key not in self._allowed:
            scope, held = tuple(t.scope), tuple(self.protected)
            covered = sum(1 for f in self.files if T._in(f, scope) and not (held and T._in(f, held)))
            still = sum(  # a glob that matches no tracked file is a file still to be made: one more allowed
                1 for g in scope if not g.startswith("!") and not any(T._in(f, (g,)) for f in self.files)
            )
            self._allowed[key] = covered + still if t.scope else 0
        return self._allowed[key]

    def pace(self, t: Task, buckets: int = 12, width: float = 5.0) -> str:
        counts = [0] * buckets
        for e in t.events:
            age = self.clock - e.t
            if 0 <= age < buckets * width:
                counts[buckets - 1 - int(age // width)] += 1
        top = max(max(counts), 4)
        return "".join(SPARK[min(7, int(c * 8 / (top + 1)))] if c else "▁" for c in counts)

    def quiet(self, t: Task) -> float:
        """Seconds since the agent's last sign of life, as `run.live` counts them (its meter, its hooks, its
        log), else since its last event, else since it began."""
        if t.idle is not None:
            return float(t.idle)
        last = max((e.t for e in t.events), default=t.started) or self.clock
        return self.clock - last

    def tail(self, t: Task, n: int = 3) -> list[str]:
        out = []
        for e in t.events[-n:]:
            out.append(
                {
                    "read": "read ",
                    "edit": "edit ",
                    "run": "run  ",
                    "search": "find ",
                    "said": "says ",
                    "you": "you  ",
                    "stop": "stopped ",
                }.get(e.kind, "")
                + (e.path or e.text)
            )
        return out

    def color(self, tid: str) -> str:
        t = self.tasks.get(tid)
        if t and t.agent:
            return color_of(t.agent)
        return PALETTE[int(hashlib.sha1(tid.encode()).hexdigest(), 16) % len(PALETTE)]

    def tasks_dict(self) -> dict[str, dict]:
        return {
            t.id: {
                "state": t.state,
                "scope": t.scope,
                "changed": t.changed,
                "touched": list(t.touched),
                "stopped": [p for p, _ in t.stopped],
            }
            for t in self.tasks.values()
        }

    def agent_name(self, key: str, taken: set[str] | None = None) -> str:
        """The name an agent goes by: kept for its key once chosen, so a name never flips between looks."""
        if key not in self.names:
            self.names[key] = name_for(key, taken if taken is not None else set(self.names.values()))
        return self.names[key]
