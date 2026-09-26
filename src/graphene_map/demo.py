"""`graphene demo`: a recorded run, replayed in `graphene watch` exactly as it happened, and the recorder
that makes one.

A recording is the plan's store over a run, not the model's calls: replaying the calls would run their
tools, which is model-written code. Its first line says what was recorded, when, by which Graphene, and
whether the recorder's terminal was pointed at Token Factory; the replay says "live" only when that is so
and every model call the run logged (its `usage` rows) says it went there. Each line after it is one
change, seen within a fifth of a second: the seconds since the recorder started, the rows of `nodes` that
changed or went, the new rows of `node_log`, the `plan_meta` keys the screen reads that changed, what each
executor wrote to its output under `.graphene/runs/` since the last look (the screen's `l`), and what git
tracks once a leaf has landed (the check a contract names is judged against it). The repository's path is
written `{repo}`, and the replay puts its own there; the home directory is `~`; the key and the project
in the environment, anything shaped like a key, and each sandbox image the run names are taken out.

demo.jsonl, beside this file, is the recording Graphene ships. It was made on 25 September 2026, when no
Token Factory key existed, by docs/proof/nemotron.sh on a tiny repository against the scripted fake
(tests/fake_tokenfactory.py), and its first line says it is a scripted stand-in, which the screen shows.
It is made again from the fake with

    RECORD_DEMO=src/graphene_map/demo.jsonl uv run pytest tests/test_demo_script.py

and from a live run on Token Factory, with NEBIUS_API_KEY set, with

    RECORD=$PWD/src/graphene_map/demo.jsonl docs/proof/nemotron.sh

Read what that writes before committing it: tests/test_demo.py checks it holds no path and no key, and
names tonight's leaves, which a new recording changes.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from textual.widgets import Static

from . import __version__
from . import plan as P
from . import tokenfactory as tf
from .store import Store
from .tui import Help, Watch, fit

SHIPPED = Path(__file__).with_name("demo.jsonl")
ENDED = "ended: last frame"
REFUSED = "a replay: nothing runs here"
LIVE, STAND_IN = "as it ran, live", "a scripted stand-in, not Nemotron"  # what the top line says made it
NO_CALLS = "a run with no model calls on record"
EVERY = 0.2  # seconds between the recorder's looks at the store
LONG = 3.0  # seconds: a longer wait is replayed in this long, and the top line says by how much
META = ("goal", "goal:proposed", "goal:proposed:by", "planner", "executor", "plan_first", "paused")  # read
# Shaped like a key: 20 or more letters and digits in a row, a capital, a small letter and a digit among
# them (a key, a token, a JWT's part). The whole word it sits in goes (up to a space, a slash or a quote),
# so no piece of a key is left. A git sha, a uuid, a node's id, a log's name and a model's name have none.
ALNUM = "[A-Za-z0-9]"
KEY = re.compile(rf"(?<!{ALNUM})(?={ALNUM}*[A-Z])(?={ALNUM}*[a-z])(?={ALNUM}*[0-9]){ALNUM}{{20}}")
WORD = re.compile(r"[\w.\-]{20,}", re.ASCII)
# base64, which a word above ends at a / or a + (an AWS secret access key): 30 or more of its letters with a
# capital, a small letter, a digit and a / or a +, and its padding. A . - or _ breaks it, so a path is kept
# unless 30 of its characters in a row are letters, digits and slashes alone.
B64 = "[A-Za-z0-9+/]"
BASE64 = re.compile(
    rf"(?<!{B64})(?={B64}*[A-Z])(?={B64}*[a-z])(?={B64}*[0-9])(?={B64}*[+/]){B64}{{30,}}=*"
)
REMOVED = "[removed: shaped like a key]"


def hider(root: Path) -> tuple:
    """What a recording must not hold, taken out of every string: the repository's path (`{repo}`), the
    home directory (`~`), the key and the project in the environment, and anything shaped like a key.
    Returns the function and its list of (text, instead), to which a sandbox image is added when seen."""
    home = str(Path.home())
    said = [(p, "{repo}") for p in sorted({str(root), str(root.resolve())}, key=len, reverse=True)]
    said += [(home, "~")] if len(home) > 1 else []
    said += [(os.environ[k], "[removed]") for k in (tf.KEY, "NEBIUS_PROJECT_ID") if len(os.getenv(k, "")) > 7]

    def hide(value):
        if isinstance(value, dict):
            return {k: hide(v) for k, v in value.items()}
        if not isinstance(value, str):
            return value
        for text, instead in said:  # as written, and as JSON writes it inside a node's or a log row's detail
            for form in {text, json.dumps(text)[1:-1], json.dumps(text, ensure_ascii=False)[1:-1]}:
                value = value.replace(form, instead)
        return WORD.sub(lambda word: REMOVED if KEY.search(word[0]) else word[0], BASE64.sub(REMOVED, value))

    return hide, said


def record(root: Path, out: Path, every: float = EVERY) -> int:
    """Record the plan of ``root`` into ``out`` until Ctrl-C or TERM, waiting for its store when there is
    none yet (a run that starts with `graphene init`). Returns how many changes it wrote."""
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    stand_in = tf.base() != tf.BASE  # this terminal's view; the replay decides from the run's usage rows
    head = {"graphene demo": 1, "recorded": P._now(), "graphene": __version__, "repository": root.name,
            "stand_in": stand_in, "shown": STAND_IN if stand_in else LIVE}  # fmt: skip
    db, runs, began = root / ".graphene" / "graphene.db", root / ".graphene" / "runs", time.monotonic()
    hide, said = hider(root)
    conn, last, read, seen, tracked, n = None, 0, {}, {}, None, 0
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head) + "\n")
        f.flush()  # on disk at once: a recorder stopped before the store appears has still said what it is
        while True:
            stopping = stop.wait(every)  # and one look after it, for what was written as it was told
            change: dict = {}
            outputs = {}  # read before the store: a line printed after a write is then never ahead of it
            for path in sorted(runs.glob("*")):
                try:
                    with open(path, "rb") as log:
                        log.seek(read.get(path.name, 0))
                        new = log.read()
                except OSError:  # not a file, or gone: the recording goes on without it
                    continue
                if not stopping:  # whole lines, the rest at the next look: a key or a path written across
                    new = new[: new.rfind(b"\n") + 1]  # two looks is taken out whole, and no character is cut
                if new or path.name not in read:
                    outputs[path.name] = new.decode("utf-8", "replace")
                    read[path.name] = read.get(path.name, 0) + len(new)
            if conn is None and db.exists():
                conn = sqlite3.connect(db, timeout=5, isolation_level=None)
                conn.row_factory = sqlite3.Row
            try:
                nodes, rows, meta = _snapshot(conn, last) if conn is not None else ({}, [], {})
            except sqlite3.Error:  # its tables are still being made (`graphene init`): the next look
                nodes, rows, meta = seen.get("nodes", {}), [], seen.get("plan_meta", {})
            for table, now in (("nodes", nodes), ("plan_meta", meta)):
                was = seen.get(table, {})  # a row that went is None
                diff = {k: v for k, v in now.items() if was.get(k) != v} | dict.fromkeys(was.keys() - now)
                if diff:
                    change[table] = hide(diff)
                seen[table] = now
            for row in rows:  # a sandbox's image is its id: out of this line and every one after it
                image = json.loads(row["detail"] or "{}").get("image") if row["kind"] == "placement" else None
                if image:
                    said += [(i, "[a sandbox image]") for i in dict.fromkeys((image, image[:19]))]
            if rows:
                change["node_log"], last = [hide(r) for r in rows], rows[-1]["id"]
            if conn is not None and (rows or tracked is None):  # a leaf lands by a commit, which the log says
                now = P.tracked(root)
                if now != tracked:
                    change["tracked"] = tracked = now
            if outputs:
                change["runs"] = hide(outputs)
            if change:
                f.write(json.dumps({"t": round(time.monotonic() - began, 2), **change}) + "\n")
                f.flush()
                n += 1
            if stopping:
                break
    if conn is not None:
        conn.close()
    return n


def _snapshot(conn: sqlite3.Connection, after: int) -> tuple[dict, list[dict], dict]:
    """What a recording holds of the store, as one write left it: every node, the log after ``after``, and
    the plan_meta keys the screen reads."""
    conn.execute("BEGIN")
    try:
        nodes = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM nodes")}
        rows = [dict(r) for r in conn.execute("SELECT * FROM node_log WHERE id > ? ORDER BY id", (after,))]
        asked = f"SELECT key, value FROM plan_meta WHERE key IN ({', '.join('?' * len(META))})"
        return nodes, rows, dict(conn.execute(asked, META).fetchall())
    finally:
        conn.execute("COMMIT")


def load(path: Path) -> tuple[dict, list[dict]]:
    """A recording's first line, with ``day``: the day it was recorded, local as the screen's clocks are;
    and its changes, each with ``at``: when the replay applies it (the first at once, each wait after it
    as recorded, or LONG seconds for a longer one) and ``cut``: how many times faster that wait is played
    (0 when it is not cut); ``shown``, what made it, is decided from the run. A file that is not a
    recording is a ValueError."""
    head, *lines = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]
    if not isinstance(head, dict) or not {"graphene demo", "recorded", "shown", "repository"} <= head.keys():
        raise ValueError("it is not a recording `graphene demo --record` made")
    head["day"] = str(datetime.fromisoformat(head["recorded"].replace("Z", "+00:00")).astimezone().date())
    # the run says what made it, not the terminal that recorded it: live only when every model call on
    # record says it went to Token Factory (a row from before rows said so is a stand-in's)
    calls = [json.loads(r["detail"] or "{}") for line in lines for r in line.get("node_log") or []
             if r["kind"] == "usage"]  # fmt: skip
    live = not head.get("stand_in", True) and all(c.get("endpoint") == "token factory" for c in calls)
    head["shown"] = NO_CALLS if not calls else LIVE if live else STAND_IN
    at, was = 0.0, lines[0]["t"] if lines else 0.0
    for line in lines:
        gap, was = line["t"] - was, line["t"]
        at += min(gap, LONG)
        line["at"], line["cut"] = at, gap / LONG if gap > LONG else 0
    return head, lines


def repository(tmp: Path, head: dict) -> Path:
    """The replay's own repository, named as the recorded one was: git's, with nothing in it."""
    repo = tmp / (Path(str(head.get("repository") or "")).name or "demo")
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    return repo


def apply(store: Store, line: dict, repo: Path) -> None:
    """One recorded change, applied to the replay's store and to its executors' outputs, with the
    repository's path put back as the replay's own."""

    def here(value):
        return value.replace("{repo}", str(repo)) if isinstance(value, str) else value

    known = {t: {c[1] for c in store.conn.execute(f"PRAGMA table_info({t})")} for t in ("nodes", "node_log")}

    def put(table: str, row: dict) -> None:  # this store's own columns only: a recording never names SQL
        cols = [c for c in row if c in known[table]]
        store.conn.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES "
                           f"({', '.join('?' * len(cols))})", [here(row[c]) for c in cols])  # fmt: skip

    with store.transaction():
        for node_id, row in (line.get("nodes") or {}).items():
            if row:
                put("nodes", row)
            else:
                store.conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        for row in line.get("node_log") or []:
            put("node_log", row)
        for key, value in (line.get("plan_meta") or {}).items():
            store.set_meta(key, here(value))
    runs = repo / ".graphene" / "runs"
    for name, text in (line.get("runs") or {}).items():
        runs.mkdir(exist_ok=True)
        with open(runs / Path(name).name, "a", encoding="utf-8") as out:  # its name: never a path out of here
            out.write(here(text))


def banner(head: dict, state: str = "") -> list[tuple[str, str]]:
    """A replay's top line, in pieces, whole ones dropped from the end when it is narrow: that it is a
    replay, whether a model made it and on which day, never dropped; then a wait cut short or its end;
    then whose plan it was. At 80 columns only the last is left off."""
    first = f"replay · {head['shown']} · {head['day']}"
    whose = f"the plan of {head['repository']}"
    return [(first, "bold"), *([(state, "")] if state else []), (whose, "dim")]


def last_frame(repo: Path, lines: list[dict]) -> None:
    """Every change at once: the replay's store as the run left it."""
    with Store.open(repo) as store:
        for line in lines:
            apply(store, line, repo)


class Replay(Watch):
    """`graphene watch` over a recording: its changes applied to the replay's own store on the recorded
    clock, the top line saying what it is, and every key that would change the plan or start anything
    answered with one line, nothing done. Moving, folding, the record, the output and the help work."""

    def __init__(self, repo: Path, head: dict, lines: list[dict]) -> None:
        super().__init__(repo, lambda: Store.open(repo), every=1.0)
        self.head, self.lines, self.next, self.began = head, lines, 0, 0.0
        self.files, self.files_at = [], math.inf  # what git tracked is the recording's, never asked here

    def on_mount(self) -> None:
        self.began = time.monotonic()
        for sig in (signal.SIGHUP, signal.SIGTERM):  # its terminal closed, or a kill: an exit, which removes
            asyncio.get_running_loop().add_signal_handler(sig, self.exit)  # the replay's repository
        self.play()  # the first change is there when the screen is first drawn
        super().on_mount()
        self.set_interval(0.1, self.play)

    def play(self) -> None:
        """Apply what is due by the replay's clock, and draw the screen again when anything was."""
        due = time.monotonic() - self.began
        if self.next == len(self.lines) or self.lines[self.next]["at"] > due:
            return
        with Store.open(self.root_path) as store:
            while self.next < len(self.lines) and self.lines[self.next]["at"] <= due:
                apply(store, self.lines[self.next], self.root_path)
                self.files = self.lines[self.next].get("tracked", self.files)
                self.next += 1
        self.refresh_plan()

    def draw(self, store) -> None:
        """As `graphene watch` draws it, the top line the replay's: what it is, a wait being cut short
        and by how much, or its end, then which run and when."""
        super().draw(store)
        cut = self.lines[self.next]["cut"] if self.next < len(self.lines) else 0
        state = ENDED if self.next == len(self.lines) else f"×{round(cut, 1):g}: a wait, cut" if cut else ""
        self.query_one("#where", Static).update(fit(banner(self.head, state), max(self.size.width - 2, 20)))

    def refuse(self, *_, **__) -> None:
        self.message = REFUSED
        self.say_status()

    def ran(self, text: str) -> None:
        """The line `/` opened: a search, or (its / erased) a command, refused."""
        super().ran(text if text.startswith("/") else "")  # closes the line; nothing else for ""
        if not text.startswith("/"):
            self.refuse()

    # every key that would change the plan or start anything, and every way a key reaches a command
    action_add = action_edit = action_drop = action_yes = action_split = action_undo = refuse
    action_run = action_release_or_reopen = action_offer = action_plan_first = action_visual = refuse
    did = background = edit_with = stop_runs = refuse

    def action_line(self, kind: str) -> None:
        if kind == ":":  # `/` searches; `:` would run a command
            return self.refuse()
        super().action_line(kind)

    def action_help_or_ask(self) -> None:
        self.push_screen(Help())  # the help everywhere: on a leaf that came back it would start a planner

    def keys(self) -> list[str]:
        """What the keys do here, for the bottom line: only those that work in a replay."""
        if self.view == "contract":
            return ["j k move", "Enter record", "l output", "za fold", "? help", "q quit"]
        return ["? help" if k[0] == "?" else k for k in super().keys() if k[:2] not in ("w ", "b ", "n ")]
