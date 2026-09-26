"""`graphene demo`: a recorded run, replayed in `graphene watch` exactly as it happened, and the recorder
that makes one.

A recording is the plan's store over a run, not the model's calls: replaying the calls would run their
tools, which is model-written code. Its first line says what was recorded, when, by which Graphene, and
whether it was live or a stand-in, in the words the screen shows. Each line after it is one change, seen
within a fifth of a second: the seconds since the recorder started, the rows of `nodes` that changed or
went, the new rows of `node_log`, the `plan_meta` keys the screen reads that changed, what each executor
wrote to its output under `.graphene/runs/` since the last look (the screen's `l`), and what git tracks
once a leaf has landed (the check a contract names is judged against it). The repository's path is
written `{repo}`, and the replay puts its own there; the home directory is `~`; the key and the project
in the environment, anything shaped like a key, and each sandbox image the run names are taken out.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from . import __version__
from . import plan as P
from . import tokenfactory as tf
from .store import Store

SHIPPED = Path(__file__).with_name("demo.jsonl")
ENDED = "ended: this is its last frame"
EVERY = 0.2  # seconds between the recorder's looks at the store
LONG = 3.0  # seconds: a longer wait is replayed in this long, and the top line says by how much
META = ("goal", "goal:proposed", "goal:proposed:by", "planner", "executor", "plan_first", "paused")  # read
# Shaped like a key: 20 or more letters and digits in a row, a capital, a small letter and a digit among
# them (a key, a token, a JWT's part). The whole word it sits in goes (up to a space, a slash or a quote),
# so no piece of a key is left. A git sha, a uuid, a node's id, a log's name and a model's name have none.
ALNUM = "[A-Za-z0-9]"
KEY = re.compile(rf"(?<!{ALNUM})(?={ALNUM}*[A-Z])(?={ALNUM}*[a-z])(?={ALNUM}*[0-9]){ALNUM}{{20}}")
WORD = re.compile(r"[\w.\-]{20,}", re.ASCII)
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
        return WORD.sub(lambda word: REMOVED if KEY.search(word[0]) else word[0], value)

    return hide, said


def record(root: Path, out: Path, every: float = EVERY) -> int:
    """Record the plan of ``root`` into ``out`` until Ctrl-C or TERM, waiting for its store when there is
    none yet (a run that starts with `graphene init`). Returns how many changes it wrote."""
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    stand_in = tf.base() != tf.BASE  # the tests' fake, or any endpoint that is not Token Factory
    shown = "a scripted stand-in, not Nemotron" if stand_in else "as it ran, live"
    head = {"graphene demo": 1, "recorded": P._now(), "graphene": __version__, "repository": root.name,
            "stand_in": stand_in, "shown": shown}  # fmt: skip
    db, runs, began = root / ".graphene" / "graphene.db", root / ".graphene" / "runs", time.monotonic()
    hide, said = hider(root)
    conn, last, read, seen, tracked, n = None, 0, {}, {}, None, 0
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head) + "\n")
        while True:
            stopping = stop.wait(every)  # and one look after it, for what was written as it was told
            change: dict = {}
            outputs = {}  # read before the store: a line printed after a write is then never ahead of it
            for path in sorted(runs.glob("*")):
                with open(path, "rb") as log:
                    log.seek(read.get(path.name, 0))
                    new = log.read()
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
    """A recording's first line, and its changes, each with ``at``: when the replay applies it (the first at
    once, each wait after it as recorded, or LONG seconds for a longer one) and ``cut``: how many times
    faster that wait is played (0 when it is not cut)."""
    head, *lines = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]
    if not isinstance(head, dict) or "graphene demo" not in head:
        raise ValueError("it is not a recording `graphene demo --record` made")
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
    replay and whether a model made it, then where the replay is, then which run and when."""
    when = f"{head.get('repository', 'demo')}, recorded {str(head.get('recorded', ''))[:10]}"
    return [(f"replay · {head.get('shown', '')}", "bold"), *([(state, "")] if state else []), (when, "dim")]


def last_frame(repo: Path, lines: list[dict]) -> None:
    """Every change at once: the replay's store as the run left it."""
    with Store.open(repo) as store:
        for line in lines:
            apply(store, line, repo)
