"""The night's bill: one ledger that every live call shares while the person's opening is set.

From an agent's shell the practice ladder's live rungs refuse to run (docs/test/practice.py), unless the
person set GRAPHENE_AGENT_LIVE_USD in the shell that started the session: that is the opening. While it
is set, every Token Factory call and every ConTree operation, whoever starts it (the ladder, `graphene
ask` or `run` with nemotron, a prototype, a harness in docs/test), is written to one ledger for the
night, and the night has one cap: the lower of that figure and $10 (CEILING).

- A Token Factory call reserves its worst case before it is sent (``worst``) and settles to its usage
  after; one whose reservation would take the night past its cap is refused, and nothing is sent.
- Nothing new starts (a rung, a run, a process's first live call) once what is spent and what is in
  flight reach 80% of the cap: the ledger estimates at list price, and the rest is the margin. What a
  started thing starts (a run's executors, a leaf's `node done`) inherits GRAPHENE_NIGHT_STARTED and goes
  on under the cap.
- A ConTree operation is counted with its seconds, at $0 and `price: unknown` until its price is read.
- Every row says `practice: true`: nothing made under the opening enters a registered table
  (docs/test/evidence.py refuses it).

The ledger is ~/.graphene/night/<date>.jsonl, the date of the evening the night began (a night runs noon
to noon, local time), or GRAPHENE_NIGHT_LEDGER. It is locked (flock) for each read and write, so
parallel calls cannot pass the cap between them. It holds a model, a tag, tokens, dollars and seconds:
no prompt, no answer, no key.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

OPENING = "GRAPHENE_AGENT_LIVE_USD"
LEDGER = "GRAPHENE_NIGHT_LEDGER"
STARTED = "GRAPHENE_NIGHT_STARTED"
CEILING = 10.0  # dollars at list price, whatever the opening says
START = 0.8  # of the cap: past it, nothing new starts
UNSAID = 32_768  # completion tokens a call that names no max_tokens may take: the most a planner raises it to


class Refused(RuntimeError):
    """The night's cap, or its 80%, says no: nothing was sent, nothing was started."""


def cap() -> float | None:
    """The night's cap in dollars, or None when the opening is not set. A figure that is not a number
    is a cap of $0: everything live is refused, not let through."""
    said = os.environ.get(OPENING)
    if not said:
        return None
    try:
        return max(0.0, min(float(said), CEILING))
    except ValueError:
        return 0.0


def where() -> Path:
    named = os.environ.get(LEDGER)
    if named:
        return Path(named)
    evening = (datetime.now() - timedelta(hours=12)).date()
    return Path.home() / ".graphene" / "night" / f"{evening}.jsonl"


@contextmanager
def _held():
    """The ledger's rows, read under its lock, and the file to append to while the lock is held."""
    path = where()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as f:  # closing it lets the lock go, however the process ends
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        rows = []
        for line in f.read().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        yield rows, f


def _add(f, row: dict) -> None:
    f.write(json.dumps({"at": round(time.time(), 3), **row, "practice": True}) + "\n")
    f.flush()


def _dollars(row: dict) -> float:
    """A row's dollars; one that is not a number, or is below zero, counts as without end: the cap then
    refuses everything, rather than a row nobody can read letting a call through."""
    try:
        said = float(row.get("dollars") or 0)
    except (TypeError, ValueError):
        return math.inf
    return said if math.isfinite(said) and said >= 0 else math.inf


def _sums(rows: list[dict]) -> tuple[float, float]:
    """Dollars spent (settled), and dollars in flight (reserved and not settled yet)."""
    settled = {r.get("id") for r in rows if r.get("kind") == "settle"}
    spent = sum(_dollars(r) for r in rows if r.get("kind") == "settle")
    held = sum(_dollars(r) for r in rows if r.get("kind") == "reserve" and r.get("id") not in settled)
    return spent, held


def _late(what: str, spent: float, held: float, limit: float) -> str:
    return (f"refused: the night has ${spent:.4f} spent and ${held:.4f} in flight, at or past "
            f"${START * limit:.2f} ({START:.0%} of its ${limit:.2f} cap, {OPENING}): nothing new starts, "
            f"and {what} was not started")  # fmt: skip


def begin(what: str) -> None:
    """Something new and live starts here (``what``: a rung, a run): refused once 80% of the cap is spent or
    in flight. What it starts inherits the mark, and goes on under the cap."""
    limit = cap()
    if limit is None:
        return
    with _held() as (rows, _):
        spent, held = _sums(rows)
    if spent + held >= START * limit:
        raise Refused(_late(what, spent, held, limit))
    os.environ[STARTED] = what


def first(what: str) -> None:
    """A process's first live act starts something, unless what started the process said it had."""
    if not os.environ.get(STARTED):
        begin(what)


def reserve(model: str, worst: float, tag: str, endpoint: str) -> str | None:
    """Hold ``worst`` dollars for one call before it is sent; its id, or None when the night is not open."""
    limit = cap()
    if limit is None:
        return None
    first(f"a call to {model}")
    with _held() as (rows, f):
        spent, held = _sums(rows)
        if spent + held + worst > limit:
            raise Refused(f"refused: a call to {model} may cost up to ${worst:.4f}, and the night has "
                          f"${spent:.4f} spent and ${held:.4f} in flight of its ${limit:.2f} cap "
                          f"({OPENING}): nothing was sent")  # fmt: skip
        held_id = os.urandom(6).hex()
        _add(f, {"kind": "reserve", "id": held_id, "model": model, "tag": tag, "endpoint": endpoint,
                 "dollars": worst})  # fmt: skip
    return held_id


def settle(held_id: str | None, model: str, dollars: float, usage: dict | None = None) -> None:
    """The call's reservation, settled at what it cost (its usage at list price)."""
    if held_id is None:
        return
    usage = usage or {}
    with _held() as (_, f):
        _add(f, {"kind": "settle", "id": held_id, "model": model, "dollars": dollars,
                 "prompt_tokens": usage.get("prompt_tokens") or 0,
                 "completion_tokens": usage.get("completion_tokens") or 0})  # fmt: skip


def sandbox(op: str, seconds: float) -> None:
    """One ConTree operation and how long it ran: a sandbox runs only while an operation does."""
    if cap() is None:
        return
    with _held() as (_, f):
        _add(f, {"kind": "sandbox", "op": op, "seconds": round(seconds, 3), "dollars": 0.0,
                 "price": "unknown"})  # fmt: skip


def bill() -> list[str]:
    """The night so far, for the brief: spent, in flight, the cap, each model (Ultra first), Sandboxes."""
    limit = cap()
    path = where()
    rows = []
    if path.exists():
        with _held() as (read, _):
            rows = read
    spent, held = _sums(rows)
    shown = CEILING if limit is None else limit
    lines = [f"the night's bill: ${spent:.4f} spent, ${held:.4f} in flight, of a ${shown:.2f} cap; "
             f"nothing new starts at ${START * shown:.2f} · {path}"]  # fmt: skip
    if limit is None:
        lines.append(f"  {OPENING} is not set in this shell: the cap shown is the ceiling, and nothing live "
                     "started here is counted")  # fmt: skip
    settles = [r for r in rows if r.get("kind") == "settle"]
    models: dict[str, list[float]] = {}
    for r in settles:
        seen = models.setdefault(str(r.get("model")), [0, 0.0])
        seen[0] += 1
        seen[1] += _dollars(r)
    ultra_first = sorted(models.items(), key=lambda m: ("ultra" not in m[0].lower(), -m[1][1]))
    for model, (calls, dollars) in ultra_first:
        lines.append(f"  {model}: {calls} call{'s' * (calls != 1)}, ${dollars:.4f}")
    flying = len({r.get("id") for r in rows if r.get("kind") == "reserve"} - {r.get("id") for r in settles})
    if flying:
        lines.append(f"  in flight: {flying} call{'s' * (flying != 1)}, ${held:.4f} held at the worst case")
    stand_in = sum(1 for r in rows if r.get("kind") == "reserve" and r.get("endpoint") != "token factory")
    if stand_in:
        lines.append(f"  of these, {stand_in} call{'s' * (stand_in != 1)} went to a stand-in")
    ops = [r for r in rows if r.get("kind") == "sandbox"]
    minutes = sum(float(r.get("seconds") or 0) for r in ops) / 60
    lines.append(f"  Sandboxes: {len(ops)} operations, {minutes:.1f} min, counted at $0 (price: unknown)")
    return lines
