"""The plan over time, left to right: a lane for each leaf that has been held, and what its executor
was doing when.

A lane is a leaf with a `started` row, in the outline's order, under one for the person: a tick (`|`)
for each of their acts. Time runs from the plan's first ask, acceptance or start, whichever came first, to
now while a leaf runs, else to the last row. One cell is one slice: the span over the time column's
cells, a span under a minute drawn as a minute. A leaf's lane is a bar for each attempt. Each cell is
what most of the slice's rows say the executor did: editing █, running a command ▓, reading or
searching ▒, talking ░. A slice with no row carries the last one on until it is a minute old. Then,
and before the first row, the executor is idle (─). A hold with no attempt, an attempt with no meter,
or one that ended with no row the meter read, is a plain bar (━): the meter never sees a Claude Code
session, nor an executor that writes no stream it reads, nor what one did before the meter (its bill
alone). Marks sit at their moment: a write refused !, a check passed ✓ or failed ✗, came back ↩,
landed ◆, running now ●. A mark that falls on another moves right. The glyph says it alone, so the
plain print reads too. The note's clocks are this plan's, as the lanes are. A pure function of the
nodes and the log's rows the screen already read (`views.happened`).
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

from rich.cells import cell_len
from rich.text import Text

from . import meter as M
from . import plan as P
from .view_dag import outline
from .views import BASELINE, Drawn, elide, money

EVENTS = True  # its draw takes the log's rows (views.happened)
LEAST, IDLE = 30, 60  # the time column's least cells; idle after (s)
BLOCK = {"editing": "█", "running": "▓", "reading": "▒", "searching": "▒"}  # by a did row's verb: else ▓
TALK, QUIET, HELD, NOW = "░", "─", "━", "●"  # a said row; idle; a hold with no attempt; running now
MARKS = {"denied": ("!", "magenta"), "breach": ("!", "magenta"), "refused": ("!", "magenta"),
         "check_passed": ("✓", "green"), "check_failed": ("✗", "magenta"), "released": ("↩", "magenta"),
         "landed": ("◆", "green")}  # fmt: skip
STEPS = (1, 2, 5, 10, 15, 30, 60)  # the axis's, in minutes; in seconds under two minutes
EPOCH = datetime.fromtimestamp(0, UTC)  # the end of a log with no row: only the axis is drawn then


def held(nodes: list[P.Node]) -> list[P.Node]:
    """The leaves that have been held, in the outline's order: one lane each."""
    ids = {n.id for n in P.leaves(nodes) if n.started_at}
    return [n for n, _ in outline(nodes) if n.id in ids]


def suits(nodes: list[P.Node], width: int, height: int) -> int:
    """Just above the outline once a leaf has been held, so a tree or a graph that fits still wins;
    0 before."""
    return BASELINE + 1 if held(nodes) else 0


def _came_back(e: dict) -> bool:
    """A `released` row of a hand-back: not the person's, not a stopped run's (`plan.came_back`)."""
    return e["kind"] == "released" and not e["detail"].get("person") and not e["detail"].get("stopped")


def _tries(rows: list[dict], now: datetime | None) -> list[tuple[dict, list[dict]]]:
    """Each attempt (`meter.attempts`) and its did and said rows: its number's, from its start to the
    next attempt's, as the screen's `l` takes them."""
    tries, out = M.attempts(rows, now=now), []
    talk = [e for e in rows if e["kind"] in ("did", "said")]
    ends = [*(a["started"] for a in tries[1:]), "9"][: len(tries)]  # "9" sorts after every timestamp
    for a, end in zip(tries, ends, strict=True):
        out.append((a, [e for e in talk if e["detail"].get("attempt") == a["attempt"]
                        and a["started"] <= e["timestamp"] < end]))  # fmt: skip
    return out


def _phrase(e: dict) -> str:
    d = e["detail"]
    if e["kind"] == "said":
        return " ".join(str(d.get("text") or "").split())
    return M.doing(d.get("verb") or "", d.get("target") or "")


def _glyph(e: dict) -> str:
    return TALK if e["kind"] == "said" else BLOCK.get(e["detail"].get("verb"), BLOCK["running"])


def activity(rows: list[dict], now: datetime | None = None) -> list[tuple[dict, list[tuple[int, str, int]]]]:
    """What a leaf's executor did and said, attempt by attempt: each phrase with the seconds after its
    attempt began, and a run of the same phrase once, with how many (`editing cli/main.py`, 4)."""
    out = []
    for a, mine in _tries(rows, now):
        begun, said = datetime.fromisoformat(a["started"]), []
        for phrase, run in itertools.groupby(mine, key=_phrase):
            run = list(run)
            after = datetime.fromisoformat(run[0]["timestamp"]) - begun
            said.append((int(after.total_seconds()), phrase, len(run)))
        out.append((a, said))
    return out


def draw(
    nodes: list[P.Node], words: dict[str, str], goal: str, width: int, height: int, cursor: str | None,
    events: dict | None = None,
) -> Drawn | None:
    """The goal's line, the person's lane, a lane for each leaf held, and the axis. None when the time
    column has fewer than LEAST cells; taller than ``height`` is the screen's to scroll. ``events``:
    the log's rows (`views.happened`); with none, the lanes are drawn bare."""
    lanes = held(nodes)
    label = 3 + max(cell_len(i) for i in ["you", *(n.id for n in lanes)])  # an id is never cut
    cells = width - label
    if cells < LEAST:
        return None
    events = events or {"by": {}, "person": None, "now": None}
    by, now = events["by"], events["now"]
    flat = [e for rows in by.values() for e in rows]
    star = by.get("*", [])  # what an archived plan asked is not this one's
    asked = star[max((k + 1 for k, e in enumerate(star) if e["kind"] == "archived"), default=0) :]
    begun = [e["timestamp"] for e in asked if e["kind"] == "asked"]
    begun += [e["timestamp"] for n in nodes for e in by.get(n.id, []) if e["kind"] == "accepted"]  # your y
    begun += [e["timestamp"] for n in lanes for e in by.get(n.id, []) if e["kind"] == "started"]
    running = now is not None and any(n.state == P.RUNNING for n in lanes)
    end = now if running else datetime.fromisoformat(max(e["timestamp"] for e in flat)) if flat else EPOCH
    start = datetime.fromisoformat(min(begun)) if begun else end - timedelta(minutes=1)
    stop = (end - start).total_seconds()  # where the span ends, in seconds from its start
    span = max(stop, 60)
    per = span / cells

    def sec(stamp: str) -> float:
        return (datetime.fromisoformat(stamp) - start).total_seconds()

    def x(s: float) -> int:
        return min(cells - 1, max(0, int(s // per)))

    def lane(n: P.Node) -> list[tuple[str, str]]:
        rows, colour = by.get(n.id, []), P.look(words.get(n.id, ""))[1]
        out, live = [(" ", "")] * cells, None
        for a, mine in _tries(rows, now):
            ats, t0 = [sec(e["timestamp"]) for e in mine], sec(a["started"])
            t1 = max([t0 + a["seconds"], *ats])  # `seconds` is whole: a row in its last half second counts
            if not mine and not (a["meter"] and a["running"]):  # nothing the meter read: held, unseen
                out[x(t0) : x(t1) + 1] = [(HELD, colour)] * (x(t1) - x(t0) + 1)
                live = x(t1) if a["running"] else live
                continue
            k, last = 0, None  # the next row; the last row's moment and glyph
            for i in range(x(t0), x(t1) + 1):
                got = []
                while k < len(mine) and (ats[k] < (i + 1) * per or i == cells - 1):
                    last = (ats[k], _glyph(mine[k]))
                    got.append(last[1])
                    k += 1
                quiet = not got and (last is None or min((i + 0.5) * per, t1) - last[0] > IDLE)
                glyph = QUIET if quiet else max(reversed(got), key=got.count) if got else last[1]
                out[i] = (glyph, "dim" if quiet else colour)
            live = x(t1) if a["running"] else live
        starts = [k for k, e in enumerate(rows) if e["kind"] == "started"]
        for k, j in itertools.pairwise([*starts, len(rows)]):  # a hold no attempt was made in
            hold = rows[k:j]
            if any(e["kind"] == "attempt" for e in hold):
                continue
            ends = [sec(e["timestamp"]) for e in hold if e["kind"] in M.HOLD_ENDS]
            going = not ends and j == len(rows) and n.state == P.RUNNING
            until = ends[0] if ends else stop if going else sec(hold[-1]["timestamp"])
            for i in range(x(sec(hold[0]["timestamp"])), x(until) + 1):
                out[i] = (HELD, colour)
            live = x(until) if going else live
        marks = [(x(sec(e["timestamp"])), *MARKS[e["kind"]]) for e in rows
                 if e["kind"] in MARKS and (e["kind"] != "released" or _came_back(e))]  # fmt: skip
        marks += [(live, NOW, f"{colour} bold".strip())] if live is not None else []
        taken = set()
        for i, glyph, how in marks:
            while i in taken and i + 1 < cells:  # the later of two in one cell moves right
                i += 1
            taken.add(i)
            out[i] = (glyph, how)
        return out

    you = [(" ", "")] * cells
    for stamp in M.acts(flat, events["person"]):
        if 0 <= sec(stamp) <= stop:
            you[x(sec(stamp))] = ("|", "bold")
    lines, at = [Text(elide(goal, width), "bold"), Text(" you".ljust(label)) + _text(you)], {}
    for n in lanes:
        how, line = P.look(words.get(n.id, ""))[1], Text()
        line.append(f" {n.id} ", f"{how} reverse".strip() if n.id == cursor else how)
        at[n.id] = (len(lines), 0, line.cell_len - 1)
        lines.append(line + " " * (label - line.cell_len) + _text(lane(n)))
    lines.append(Text(" " * label + _axis(span, per, cells), "dim"))
    for line in lines:
        line.rstrip()
    back = sum(_came_back(e) for n in lanes for e in by.get(n.id, []))
    since = [e for e in flat if sec(e["timestamp"]) >= 0]  # this plan's clocks, as its lanes are
    said = note(len(lanes), stop, back, M.agents(since, now), M.you(since, events["person"]), width)
    return Drawn(lines=lines, at=at, order=[n.id for n in lanes], note=said)


def _text(cells: list[tuple[str, str]]) -> Text:
    out = Text()
    for how, run in itertools.groupby(cells, key=lambda cell: cell[1]):
        out.append("".join(char for char, _ in run), how)
    return out


def _axis(span: float, per: float, cells: int) -> str:
    """The moments under the lanes, from 0 at the first step that leaves 8 cells between two labels:
    `0m        3m        6m`. Seconds under two minutes; hours from a step of an hour."""
    unit = 1 if span < 120 else 60
    for step in itertools.chain(STEPS, (60 * 2**k for k in itertools.count(1))):
        said = [(int(k * step * unit / per), f"{k * step}s" if unit == 1 else f"{k * step}m" if step < 60
                 else f"{k * step // 60}h") for k in range(int(span // (step * unit)) + 1)]  # fmt: skip
        if all(b - a - len(t) >= 8 for (a, t), (b, _) in itertools.pairwise(said)):
            break
    line = ""
    for i, text in said:
        if i + len(text) <= cells:
            line = line.ljust(i) + text
    return line


def note(lanes: int, seconds: float, back: int, agents: dict, you: dict, width: int | None = None) -> str:
    """What the lanes say at a glance: `3 lanes · 12 min · 1 came back · agents 31 min $2.41 · you 4
    acts ~3 min`. Whole pieces go from the end until it fits ``width``."""
    took = agents["seconds"] // 60 or ("<1" if agents["seconds"] or agents["running"] else 0)
    said = [f"{lanes} lane{'s' * (lanes != 1)}", f"{int(seconds // 60) or '<1'} min"]
    said += [f"{back} came back"] if back else []
    said += [f"agents {took} min" + (f" {money(agents['dollars'])}" if agents["dollars"] else "")]
    said += [f"you {you['acts']} act{'s' * (you['acts'] != 1)} ~{you['minutes']} min"]
    while len(said) > 1 and width is not None and cell_len(" · ".join(said)) > width:
        said.pop()
    return " · ".join(said)
