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
from .lines import fit
from .look import short
from .model import Model
from .read import OURS, epoch, fork_why, read
from .rows import FORK_WORD, kept_said

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


# a row of the plan's log as a narrator says it of its task, the task's title in {}; a kind in none of these
# tables (precheck, usage, model, attempt, ended, a run's summary) is bookkeeping and says nothing
MILESTONES = {
    "proposed": "proposed: {}", "accepted": "you accepted {}", "started": "{} started",
    "check_passed": "{}: its check passed", "check_failed": "{}: its check failed",
    "finished": "{} is proven", "rolled_up": "{} is proven",  # the screen's word; overruled stays "done"
    "signed_off": "you signed off {}", "landed": "{} landed",
    "reopened": "{} reopened", "dropped": "{} dropped", "overruled": "{} is done over its check",
    "added": "{} added",
    "auto": "auto · {}",  # a round of `graphene auto`: its words are `auto_said`'s, not a task's title
}  # fmt: skip
GOALS = {"asked": "you asked", "goal_proposed": "proposed goal", "goal": "your goal"}  # its note is the words
ASKS = {"question": "asks", "assume": "assumes", "risk": "flags a risk", "leave out": "leaves out",
        "note": "a note"}  # fmt: skip
TAKES = {"question": "you took the default", "assume": "you confirmed", "risk": "you noted",
         "leave out": "you agreed to leave out"}  # fmt: skip
LISTS = {"scope": ("may now write", "may no longer write"), "needs": ("now waits on", "no longer waits on")}
FIELDS = {"goal": "it should now achieve"}  # in a task's own terms: "goal" is the headline's word for yours


def words(text) -> str:
    """What someone wrote, on one line, cut with an ellipsis to leave room for the rest of the news."""
    return fit(" ".join(str(text or "").split()), 60)


def item(text) -> str:
    """A fork's words as one item of the news, which ` · ` parts: its own ` · ` (the rule's reason has one)
    reads as a comma, so one verdict does not read as two."""
    return words(text).replace(" · ", ", ")


def auto_said(d: dict) -> str:
    """A round of `graphene auto` as the news says it (its row's detail is `auto.state`'s): `round 2 of 3:
    fixing`, a round being the first plan or a fix round after the goal's check failed; or why it waits."""
    where = f"round {d.get('round') or 1} of {int(d.get('rounds') or 2) + 1}"
    if d.get("stage") == "waits":
        return f"{where} waits: {item(d.get('why') or 'needs you')}"
    return f"{where}: {d.get('stage') or 'on'}"


def news(
    line: dict, titles: dict[str, str] | None = None, names: dict[str, str] | None = None,
    models: dict[str, dict[str, str]] | None = None,
) -> str:
    """One recorded change as a narrator says it, each task by its title (``titles``): what an agent did or
    said, a write the gate stopped, why a task came back, what the board asks and what you answered, what
    an edit changed, what was accepted, proven and landed. A fork's row names the fork as the rows do, the
    agent's number (``names``) and its letter, and its model when known (``models``, a task's letters to
    their names): "agent 3b (Nano): editing app.py", its check's verdict, which was kept. Bookkeeping
    (precheck, usage, model, attempt, ended, an executor's output, the settings, the
    agent's own `graphene node` commands) says nothing, so the last news stays up. Three at most, in the
    order they happened: the latest of the rest before an agent's moves, so a hand-back is not crowded out
    by the edits that came before it; and your answer before the edits it made, which the log has first.
    Tasks accepted together are one item, their count: the last three of six accepts read as if two tasks
    were, and a sub-goal comes with its tasks."""
    titles, names, models = titles or {}, names or {}, models or {}
    items = {it["id"]: it for it in json.loads((line.get("plan_meta") or {}).get("board") or "[]")}
    parents = {json.loads(n.get("data") or "{}").get("parent") for n in (line.get("nodes") or {}).values()}
    accepted: list[int] = []  # where the accepts' one item is, once per accepted task
    said: list[str] = []
    moves: set[int] = set()  # which of them are an agent's own moves: what it did or said
    first: dict[int, int] = {}  # an answer that edited the plan -> where the edits it made begin
    edits = 0  # where the edits said just before this row begin
    ends = ("finished", "overruled", "refused")  # a check that passed with none of these was not done yet
    ended = {r["node_id"] for r in line.get("node_log") or [] if r["kind"] in ends}
    for row in line.get("node_log") or []:
        d, kind = json.loads(row.get("detail") or "{}"), row["kind"]
        title = titles.get(row["node_id"], row["node_id"])
        fork = d["fork"] if isinstance(d.get("fork"), str) else ""  # a run's fork (Nemotron's are numbered)
        who = title  # a fork's row: its agent's number and its letter, as its row says it, and its model
        if fork and row["node_id"] in names:
            who = f"agent {names[row['node_id']]}{fork}"
        elif fork:
            who = f"{title} fork {fork}"
        if fork and (model := (models.get(row["node_id"]) or {}).get(fork)):
            who += f" ({model})"
        if kind == "did" and not OURS.search(str(d.get("target") or "")):
            moves.add(len(said))
            said.append(f"{who}: {d.get('verb', '')} {words(d.get('target'))}")
        elif kind == "said":
            moves.add(len(said))
            said.append(f"{who}: {words(d.get('text'))}")
        elif kind == "denied" and d.get("path"):
            said.append(f"{who}: stopped writing {d['path']}" + (" in another copy" if d.get("copy") else ""))
        elif kind == "forked":
            said.append(f"{title} forked {d.get('of') or len(d.get('forks') or [])} ways")
        elif kind == "fork" and fork and "attempts" in d and d.get("state") == "passed":  # as the fork ended
            said.append(f"{who}: its check passed" + (f", {d['lines']} lines" if d.get("lines") else ""))
        elif kind == "fork" and fork and "attempts" in d and d.get("state") not in (None, "running"):
            state = FORK_WORD.get(d["state"], d["state"])
            said.append(f"{who}: {state}" + (f": {item(fork_why(d['why']))}" if d.get("why") else ""))
        elif kind == "picked":  # as the run says it: `greet kept b: …`
            said.append(f"{title} " + kept_said((str(d.get("fork") or ""), item(d.get("reason")),
                                                  str(d.get("by") or "")), ": "))  # fmt: skip
        elif kind == "released":
            said.append(f"{title} came back: {words(d.get('why'))}")
        elif kind == "refused" and d.get("outside"):
            said.append(f"{title} is not done: {words(', '.join(d['outside']))} is outside its scope")
        elif kind == "refused" and "unchanged" in d:
            said.append(f"{title} is not done: nothing in its scope changed")
        elif kind == "check_passed" and row["node_id"] not in ended:  # 0.5.0 logged no refusal after it
            said.append(f"{title}: its check passed, not done yet")
        elif kind == "board":
            if d.get("became"):  # what it changed is in the rows just before it
                first[len(said)] = edits
            said.append(board_act(d, items))
        elif kind == "edited":
            said += edit_said(title, d.get("changed") or {}, titles)
        elif kind in GOALS:
            said.append(f"{GOALS[kind]}: {words(d.get('note'))}")
        elif kind == "accepted" and row["node_id"] not in parents:
            accepted.append(accepted[0] if accepted else len(said))
            if len(accepted) == 1:
                said.append(MILESTONES[kind].format(title))
            else:
                said[accepted[0]] = f"you accepted {len(accepted)} tasks"
        elif kind == "accepted":
            continue  # a sub-goal accepted with its tasks: they say it
        elif kind == "auto":
            said.append(MILESTONES[kind].format(auto_said(d)))
        elif kind in MILESTONES:
            said.append(MILESTONES[kind].format(title))
        if kind != "edited":
            edits = len(said)
    kept = sorted(range(len(said)), key=lambda k: (k not in moves, k))[-3:]
    kept.sort(key=lambda k: (first.get(k, k), k not in first))  # as they happened, an answer before its edits
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
    no longer, what it should achieve, else the field and its new value."""
    out = []
    for field, (was, now) in changed.items():
        if field not in LISTS:
            out.append(f"{title}: {FIELDS.get(field, f'its {field} is now')} “{words(now)}”")
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
