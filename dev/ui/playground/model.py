"""The playground's model: tasks, questions, a clock, and a little simulator that makes the numbers move.

Two sources. `demo` is a designed scene (a synthetic repo of 212 files, five tasks, one question) so the
screens have something live to show; `repo` reads the plan of the repository you run it in (read-only),
and `--simulate` pretends its ready tasks are running. Nothing here talks to an agent: it is a place to
feel the interface, not a runner. Every screen says "replay" while a simulator is on.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from graphene_map import plan as P

NAMES = [
    "fox", "oak", "river", "bee", "crab", "hen", "elm", "ant", "owl", "ivy", "jay", "koi", "lynx", "moth",
    "newt", "otter", "pine", "quail", "reed", "seal", "tern", "vole", "wren", "yak", "zebu", "dove",
]  # fmt: skip
PALETTE = [
    "#f4a261", "#8ab17d", "#5fa8d3", "#e9c46a", "#e76f51", "#c77dff", "#2a9d8f", "#ef476f", "#90be6d",
    "#4cc9f0", "#f9c74f", "#b5838d", "#43aa8b", "#f3722c", "#577590", "#bc6c25",
]  # fmt: skip
SPARK = "▁▂▃▄▅▆▇█"
LIVE_STATES = ("running", "ready", "review", "proposed", "came back", "waiting", "yours")


@dataclass
class Ev:
    t: float
    kind: str  # read, edit, run, search, said, you, stop
    text: str = ""
    path: str = ""


@dataclass
class Task:
    id: str
    title: str
    state: str = "waiting"  # running, review, came back, ready, waiting, proposed, done
    scope: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    agent: str = ""
    checks: int = 1  # proofs this task has to pass
    passed: int = 0
    events: list[Ev] = field(default_factory=list)
    touched: dict[str, float] = field(default_factory=dict)
    stopped: list[tuple[str, float]] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    told: list[tuple[str, float, float]] = field(default_factory=list)  # text, sent, heard (0 = not yet)
    note: str = ""
    # simulator parameters
    rate: float = 1.4
    work: int = 60
    done_work: int = 0
    mute: tuple[int, int] = (0, 0)  # (from work, seconds of quiet): a stall to look at
    muted_until: float = 0.0
    stops: list[tuple[int, str]] = field(default_factory=list)  # (at work, path outside scope)
    blocked_by: str = ""  # a question id it waits for once half done


@dataclass
class Question:
    id: str
    text: str
    default: str
    options: list[str]
    about: str = ""
    answer: str = ""


def name_for(key: str, taken: set[str]) -> str:
    start = int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(NAMES)
    for k in range(len(NAMES)):
        name = NAMES[(start + k) % len(NAMES)]
        if name not in taken:
            return name
    return NAMES[start]


def short(title: str, words: int = 5) -> str:
    """A glanceable name for a sentence-long title: what comes before a colon, without a leading
    article, at most ``words`` words. (Real plans have sentences for titles; a screen with almost no text
    needs a name.)"""
    head = title.split(":")[0].strip()
    parts = head.split()
    if parts and parts[0].lower() in ("the", "a", "an"):
        parts = parts[1:]
    return " ".join(parts[:words]) or title


def color_of(name: str) -> str:
    return PALETTE[NAMES.index(name) % len(PALETTE)] if name in NAMES else "white"


class Model:
    def __init__(
        self, source: str, goal: str, files: list[str], protected: list[str], simulate: bool = True
    ) -> None:
        self.source, self.goal, self.files, self.protected = source, goal, files, protected
        self.tasks: dict[str, Task] = {}
        self.questions: list[Question] = []
        self.extra_edges: list[tuple[str, str, str]] = []  # a, b, kind: loops and two-way links
        self.clock = 0.0
        self.selected = ""  # a task id or a question id
        self.lens = "plan"
        self.simulate = simulate
        self.speed = 1.0
        self.feed: list[tuple[float, str]] = []
        self.rng = random.Random(7)
        self.folded_done = 0
        self._allowed: dict[tuple[str, tuple[str, ...]], int] = {}
        self.hints: dict[str, str] = {}  # task id -> the name its agent goes by

    # -- reading ---------------------------------------------------------------------------------

    def say(self, text: str) -> None:
        self.feed.append((self.clock, text))
        del self.feed[:-6]

    def latest(self, within: float = 6.0) -> str:
        return self.feed[-1][1] if self.feed and self.clock - self.feed[-1][0] <= within else ""

    def order(self) -> list[tuple[str, str]]:
        """The cockpit's rows in the order a person should look at them: (kind, id)."""
        rows: list[tuple[str, str]] = [("question", q.id) for q in self.questions if not q.answer]
        need = [t for t in self.tasks.values() if t.state in ("review", "came back")]
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
        need = sum(1 for q in self.questions if not q.answer) + sum(
            1 for t in self.tasks.values() if t.state in ("review", "came back")
        )
        running = sum(1 for t in self.tasks.values() if t.state == "running")
        done = self.folded_done + sum(1 for t in self.tasks.values() if t.state == "done")
        return need, running, done, self.folded_done + len(self.tasks)

    def allowed(self, t: Task) -> int:
        from territory import _in

        key = (t.id, tuple(t.scope))
        if key not in self._allowed:
            self._allowed[key] = sum(1 for f in self.files if _in(f, tuple(t.scope))) if t.scope else 0
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
        last = max((e.t for e in t.events), default=self.clock)
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

    # -- moves (the verbs) ----------------------------------------------------------------------

    def start(self, t: Task) -> None:
        taken = {x.agent for x in self.tasks.values() if x.agent and x.state == "running"}
        t.agent = t.agent or self.hints.get(t.id) or name_for(t.id, taken)
        t.state = "running"
        t.events.append(Ev(self.clock, "read", path=(t.scope[0].replace("/**", "/") if t.scope else "")))

    def take(self, sel: str) -> str:
        q = next((q for q in self.questions if q.id == sel), None)
        if q:
            q.answer = q.default
            self.say(f"answered: {q.default}")
            return q.default
        t = self.tasks.get(sel)
        if not t:
            return ""
        if t.state == "review":
            t.state = "done"
            t.changed = t.changed or [p for p in t.touched]
            self.say(f"{t.agent or t.id} signed off: proven")
        elif t.state == "proposed":
            t.state = "ready"
            self.say(f"accepted: {t.title}")
        elif t.state == "came back":
            self.start(t)
            self.say(f"{t.agent} is on it again")
        return t.state

    def tell(self, sel: str, text: str) -> None:
        t = self.tasks.get(sel)
        if t and text.strip():
            t.told.append((text.strip(), self.clock, 0.0))
            t.events.append(Ev(self.clock, "you", text=f"“{text.strip()}”"))
            self.say(f"told {t.agent or t.id}")

    def widen(self, sel: str, folder: str | None = None) -> str:
        """Give a task the folder of its last stopped write (or ``folder``)."""
        t = self.tasks.get(sel)
        if not t:
            return ""
        if folder is None:
            if not t.stopped:
                self.say("nothing was stopped, so nothing to allow")
                return ""
            path = t.stopped[-1][0]
            folder = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
        glob = folder + "**" if folder else "*"
        if glob not in t.scope:
            t.scope.append(glob)
        t.stopped = [(p, at) for p, at in t.stopped if not p.startswith(folder)]
        self.say(f"{t.agent or t.id} may now touch {folder or 'the root'}")
        return glob

    def pull_back(self, sel: str) -> None:
        t = self.tasks.get(sel)
        if t and t.state == "running":
            t.state = "came back"
            t.note = "pulled back by you"
            self.say(f"pulled back {t.agent}")

    def paint(self, sel: str, folder: str) -> None:
        """Give the selected task a folder, or take it back."""
        t = self.tasks.get(sel)
        if not t or not folder:
            self.say("select a task first")
            return
        glob = folder + "**" if folder != "(root)" else "*"
        if glob in t.scope:
            t.scope.remove(glob)
            self.say(f"{t.agent or t.id} no longer may touch {folder}")
        else:
            t.scope.append(glob)
            self.say(f"{t.agent or t.id} may now touch {folder}")

    # -- time ------------------------------------------------------------------------------------

    def tick(self, dt: float) -> None:
        dt *= self.speed
        self.clock += dt
        for t in self.tasks.values():
            for k, (text, sent, heard) in enumerate(t.told):
                if not heard and self.clock - sent >= 1.2:
                    t.told[k] = (text, sent, self.clock)
        if self.simulate:
            Simulator(self).step(dt)


class Simulator:
    """Makes running tasks do things: a read, an edit, a command, a few words; now and then a write the
    hook stops; a task that waits for an answer goes quiet. Deterministic for a seed."""

    SAYS = [
        "the old ids are strings, so I…", "this needs the new column first", "tests pass locally",
        "two callers still use the old shape", "keeping both, as asked", "running the check",
    ]  # fmt: skip

    def __init__(self, m: Model) -> None:
        self.m = m

    def step(self, dt: float) -> None:
        m = self.m
        for t in list(m.tasks.values()):
            if (
                t.state == "waiting"
                and t.needs
                and all(m.tasks[n].state == "done" for n in t.needs if n in m.tasks)
            ):
                m.start(t)
                m.say(f"{t.agent} starts {t.title}")
            if t.state == "ready":
                m.start(t)
            if t.state != "running":
                continue
            if m.clock < t.muted_until:
                continue
            q = next((q for q in m.questions if q.id == t.blocked_by and not q.answer), None)
            if q and t.done_work >= t.work // 2:
                if not t.events or t.events[-1].kind != "said" or "waiting" not in t.events[-1].text:
                    t.events.append(Ev(m.clock, "said", text=f"waiting for you: {q.text}"))
                continue
            rate = t.rate * (0.55 + 0.45 * math.sin(m.clock / 6 + len(t.id)) ** 2 * 1.6)
            if m.rng.random() < rate * dt:
                self.emit(t)
            if t.mute[0] and t.done_work == t.mute[0] and not t.muted_until:
                t.muted_until = m.clock + t.mute[1]
            for at, path in t.stops:
                if t.done_work >= at:
                    t.stops.remove((at, path))
                    t.stopped.append((path, m.clock))
                    t.events.append(Ev(m.clock, "stop", path=path))
                    m.say(f"stopped a write by {t.agent}: {path}")
            passed = min(t.checks, t.done_work * t.checks // max(t.work, 1))
            if passed > t.passed:
                t.passed = passed
                m.say(f"proof {t.passed}/{t.checks} for {t.agent}")
            if t.done_work >= t.work:
                t.passed = t.checks
                t.state = "review"
                t.changed = list(t.touched)
                m.say(f"{t.agent} is done: needs your sign-off")
        for t in m.tasks.values():
            del t.events[:-200]

    def emit(self, t: Task) -> None:
        m = self.m
        files = [f for f in m.files if self._inside(t, f)] or m.files
        kind = m.rng.choices(["read", "edit", "run", "search", "said"], [45, 24, 14, 11, 6])[0]
        if kind == "edit":
            path = m.rng.choice(files)
            t.touched[path] = m.clock
            t.events.append(Ev(m.clock, "edit", path=path))
            t.done_work += 1
        elif kind == "read":
            t.events.append(Ev(m.clock, "read", path=m.rng.choice(m.files)))
            t.done_work += 1
        elif kind == "run":
            t.events.append(
                Ev(
                    m.clock,
                    "run",
                    text="pytest -q " + (t.scope[0].split("/")[0] if t.scope else "tests"),
                    path="",
                )
            )
            t.done_work += 1
        elif kind == "search":
            t.events.append(Ev(m.clock, "search", text="grep -rn id_type", path=""))
            t.done_work += 1
        else:
            t.events.append(Ev(m.clock, "said", text="“" + m.rng.choice(self.SAYS) + "”"))

    @staticmethod
    def _inside(t: Task, f: str) -> bool:
        from territory import _in

        return bool(t.scope) and _in(f, tuple(t.scope))


# -- sources ---------------------------------------------------------------------------------------


def demo_files() -> list[str]:
    spec = {
        "api/users": 12, "api/orders": 14, "api/auth": 10, "api/misc": 12, "models": 30, "db/schema": 8,
        "db": 14, "migrations": 18, "scripts/migrate": 6, "scripts": 8, "tests/ids": 10, "tests/api": 30,
        "tests": 20, "vendor": 14, "docs": 6,
    }  # fmt: skip
    files = []
    for folder, n in spec.items():
        for k in range(n):
            files.append(f"{folder}/{['user', 'order', 'auth', 'ids', 'cart', 'util', 'core'][k % 7]}_{k}.py")
    return files


def demo_model(simulate: bool = True) -> Model:
    m = Model(
        "demo", "users come back with their ids", demo_files(), ["vendor/**", "migrations/**"], simulate
    )
    m.tasks = {
        "schema": Task(
            "schema",
            "the schema",
            "done",
            ["db/schema/**"],
            [],
            "river",
            1,
            1,
            changed=["db/schema/user_0.py", "db/schema/ids_3.py", "db/schema/order_1.py"],
        ),
        "users": Task(
            "users",
            "users return ids",
            "waiting",
            ["models/**", "api/users/**"],
            ["schema"],
            "",
            3,
            work=70,
            rate=2.2,
            stops=[(14, "db/ids_2.py"), (34, "db/ids_2.py")],
            blocked_by="keep",
        ),
        "migrate": Task(
            "migrate",
            "migrate old ids",
            "waiting",
            ["scripts/migrate/**"],
            ["schema"],
            "",
            2,
            work=50,
            rate=1.6,
            mute=(18, 14),
        ),
        "tests": Task(
            "tests",
            "tests for ids",
            "waiting",
            ["tests/ids/**"],
            ["users", "migrate"],
            "",
            1,
            work=30,
            rate=2.0,
        ),
        "docs": Task("docs", "docs for ids", "proposed", ["docs/**"], ["users"], "", 1, work=18),
    }
    m.tasks["schema"].agent = "river"
    m.questions = [Question("keep", "Keep old ids working?", "keep both", ["keep both", "drop old"], "users")]
    m.extra_edges = [("tests", "users", "loop")]
    m.hints = {"users": "fox", "migrate": "oak", "tests": "wren", "docs": "dove"}
    m.folded_done = 0
    m.selected = "keep"
    m.say("replay: a designed scene, not a live run")
    for tid in ("users", "migrate"):
        m.start(m.tasks[tid])
    return m


def repo_model(root: Path, simulate: bool = False) -> Model:
    """The plan of the repository at ``root``: read-only."""
    from graphene_map import settings as S
    from graphene_map.store import Store

    with Store.open(root) as store:
        nodes = P.nodes(store)
        goal = P.goal(store) or "the plan"
        files = P.tracked(root)
        protected = S.protected(store) + S.readonly(store)
        kids = P.kids(nodes)
        leaves = [n for n in nodes if not kids.get(n.id) and n.state not in P.GONE]
        m = Model("repo", goal, files, protected, simulate)
        keep = {n.id for n in leaves}
        for n in leaves:
            word = P.reads(n, nodes)
            state = {
                "done": "done",
                "running": "running",
                "review": "review",
                "came back": "came back",
                "proposed": "proposed",
                "ready": "ready",
                "waiting": "waiting",
                "yours": "ready",
                "to fill in": "waiting",
            }.get(word, "waiting")
            t = Task(
                n.id,
                short(n.title),
                state,
                list(n.scope),
                [x for x in n.needs if x in keep],
                "",
                1,
                1 if state == "done" else 0,
            )
            if state == "done":
                done = store.node_log(n.id, ("finished",))
                t.changed = list(done[-1]["detail"].get("changed") or []) if done else []
            m.tasks[n.id] = t
        # the board's questions, as the cockpit's rows
        try:
            from graphene_map import board as B

            for it in B.items(store):
                if not it.get("answer") and it.get("kind") == "question":

                    def text(o) -> str:
                        return str(o.get("text") if isinstance(o, dict) else o)

                    options = [text(o) for o in it.get("options") or []]
                    default = text(it.get("default") or "yes")
                    m.questions.append(
                        Question(
                            str(it["id"]),
                            str(it["text"]),
                            default,
                            [default] + [o for o in options if o != default],
                        )
                    )
        except Exception:  # the board is a nicety here
            pass
    done = [t for t in m.tasks.values() if t.state == "done"]
    m.folded_done = 0
    if len(done) > 8:  # the cockpit shows what is alive; the finished are a count
        for t in done[:-4]:
            m.tasks.pop(t.id)
            m.folded_done += 1
    m.say("your own plan, read-only" + ("; ready tasks are simulated" if simulate else ""))
    live = [t for t in m.tasks.values() if t.state != "done"]
    m.selected = live[0].id if live else (next(iter(m.tasks), ""))
    if simulate:
        for t in m.tasks.values():
            if t.state == "ready":
                t.work, t.rate, t.checks = 40, 1.8, 2
                m.start(t)
    return m


def now() -> float:
    return time.monotonic()
