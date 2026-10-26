"""The cockpit screen: one row a task, the questions that wait for the person first, numbers on the right.

`build_head` (the goal and the counts, which stay on top) and `build_cockpit` (the rows, which scroll) take
the model and a width and return lines (lines.py). A row says who is on the task,
what its title is, and in numbers whether it is alive and on track: a sparkline of pace, files touched of
files allowed, checks passed of checks asked, writes stopped, seconds quiet. The row under the cursor
opens: the last lines of what the agent did, what the person told it and whether it heard, and the verbs.
"""

from __future__ import annotations

import textwrap

from rich.cells import cell_len

from ..views import money
from . import territory as T
from .lines import Line, Seg, ago, fit, fit_end, ljust, pad, span
from .look import STATE_GLYPH, color_of, short, who
from .model import Fork, Model, Question, Task

NO_GOAL = "no goal yet"  # what the plan's reader says of a plan with none (views.inputs)
INVITE = 'no goal yet · :plan goal "…" tells every agent what this is for'


def build_head(m: Model, width: int) -> list[Line]:
    """What stays on top while the rows scroll: your goal (or how to give one), then where the plan stands
    in one line, what needs you, what runs and what is proven, with the proven part as a bar."""
    need, running, done, total = m.scoreboard()
    goal = "" if m.goal in ("", NO_GOAL) else m.goal
    tag = tag_of(m, width - min(cell_len(goal or NO_GOAL), 24) - 4)  # the goal keeps what it needs
    said = goal or (NO_GOAL if tag else INVITE)  # your goal on top; with none, how to give one (not a title)
    head = [Seg(" " + fit(said, width - (cell_len(tag) + 4 if tag else 2)), "bold" if goal else "grey62")]
    head += [Seg(" · " + tag, "grey50")] if tag else []
    counts = [
        Seg(f" {need}", "bold #c77dff"), Seg(" need you   ", "#c77dff"),
        Seg(str(running), "bold #e9c46a"), Seg(" running   ", "#e9c46a"),
        Seg(f"{done}/{total}", "bold #8ab17d"), Seg(" proven  ", "#8ab17d"),
    ]  # fmt: skip
    cells = min(width - span(counts) - 2, 30)
    if cells >= 10:  # the bar, where it fits beside the numbers: proven in green, running in amber
        fill = round(cells * done / max(total, 1))
        busy = min(cells - fill, round(cells * running / max(total, 1)))
        counts += [Seg("▰" * fill, "#8ab17d"), Seg("▰" * busy, RUNNING)]
        counts += [Seg("▱" * (cells - fill - busy), "grey35")]
    counted = [Line(pad(counts, width))] if m.order() or m.folded_done else []  # nothing planned: no count
    lines = [Line(pad(head, width)), *counted]
    if (auto := auto_head(m, width)) is not None:  # the envelope's round: on top while it waits for you
        lines = [auto, *lines] if m.auto.get("stage") == "waits" else [*lines, auto]
    return [*lines, Line([Seg("─" * width, "grey30")])]


AUTO_WAITS = "bold #c77dff"  # the envelope's line while it waits for the person: the need-you purple


def auto_line(a: dict) -> str:
    """The envelope's round in one line: `auto · round 1 of 3 · running · $0.42 of $2.00 · 5 of 12 tasks`.
    A round is the first plan or a fix round after the goal's check failed, `rounds + 1` in all; `waits`
    says why it waits for the person; what is not set (no round yet, no budget, no cap on the tasks) is
    left out, never said as a zero."""
    parts = ["auto"]
    if a.get("stage"):
        parts.append(f"round {a['round']} of {a['rounds'] + 1}")
        parts.append(f"waits: {a.get('why') or 'needs you'}" if a["stage"] == "waits" else a["stage"])
    else:
        parts.append("on")
    if a.get("spent") is not None or a.get("budget") is not None:
        spent = f"${a.get('spent') or 0:.2f}"
        parts.append(spent + (f" of ${a['budget']:.2f}" if a.get("budget") is not None else ""))
    n, of = a.get("tasks") or 0, a.get("of")
    parts.append(f"{n} of {of} tasks" if of else f"{n} task{'s' * (n != 1)}")
    return " · ".join(parts)


def auto_head(m: Model, width: int) -> Line | None:
    """The envelope's line for a head (the cockpit's, the graph's) while auto is on: dim while it runs, in the
    need-you purple while it waits for the person. None while auto is off: today's head, unchanged."""
    if not m.auto:
        return None
    waits = m.auto.get("stage") == "waits"
    return Line([Seg(" " + fit(auto_line(m.auto), width - 2), AUTO_WAITS if waits else "grey62")])


def tag_of(m: Model, room: int) -> str:
    """What the screens say it is when it is not your live plan (a replay's banner; the live plan needs no
    word), in ``room`` cells: narrow, the day goes, then "paused at" (the key bar's `space play` says
    it), then where it is; never what it is and what made it."""
    parts = [p for p in (m.banner or ("replay" if m.source == "replay" else "")).split(" · ") if p]
    while cell_len(" · ".join(parts)) > max(16, room) and len(parts) > 2:
        if parts[2].startswith("paused at "):  # stepping is done paused: where it is is what it needs
            parts[2] = parts[2].removeprefix("paused at ")
            continue
        parts.pop(2)
    return " · ".join(parts)


def build_cockpit(m: Model, width: int, *, tell: str | None = None) -> list[Line]:
    """The rows, which scroll under the head (build_head): what needs you first, then the rest."""
    out: list[Line] = []
    sel = m.selected
    cols = max((span(right_of(m, t, width)) for t in m.tasks.values()), default=0)
    if not m.order() and not m.folded_done:
        return empty(m, width)
    for kind, rid in m.order():
        if kind == "question":
            q = next(q for q in m.questions if q.id == rid)
            out.append(question_line(q, width, rid == sel, model_col(m)))
            out += question_open(q, width) if rid == sel else []
            continue
        t = m.tasks[rid]
        out += task_lines(m, t, width, expanded=(rid == sel), tell=tell if rid == sel else None, cols=cols)
    if m.folded_done:
        out.append(Line([Seg(f"   ✓ {m.folded_done} more proven", "grey50")]))
    need, _running, done, total = m.scoreboard()
    if done == total and not need:  # every task proven, nothing asked: the plan is done, so what next
        said = "Every task is proven." + ("" if m.source == "replay" else " Next: :ask, or tell Claude Code.")
        out += [Line([]), Line([Seg(" " + fit(said, width - 2), "grey62")])]
    return out


EMPTY = (
    "In Claude Code, say what you want: it proposes the tasks here.",
    ":ask what you want · see a run: graphene demo",
)
NO_EXECUTOR = "No agent is chosen to run tasks: graphene init, in a terminal of your own."


def empty(m: Model, width: int) -> list[Line]:
    """A plan with nothing in it: what to do next, in lines that fit 80 columns. A replay only says so."""
    said = [Seg("Nothing is planned yet.", "bold")]
    if m.source != "replay":
        said += [Seg(NO_EXECUTOR, "#e9a23b")] if not m.executor else []  # `graphene init` chose no one yet
        said += [Seg(t, "grey62") for t in EMPTY]
    return [Line([]), *(Line([Seg(" " + fit(s.text, width - 2), s.style)]) for s in said)]


def question_line(q: Question, width: int, on: bool, models: int = 0) -> Line:
    """? the question (! a risk), ⏎ its default, and the other options by the numbers `graphene board pick`
    takes. Its words start where a task's title does (``models``: the model column's cells, when the rows
    have one), so the rows have one left edge."""
    room = max(width - LEAD - models - 2, 20)
    keep = fit("⏎ " + q.default, max(room // 3, 12))
    words = min(cell_len(q.text), room // 2)  # the question keeps up to half the row, the options the rest
    each = max(16, (room - cell_len(keep) - words - 2) // max(len(q.options[:2]), 1))
    options = [(k, fit(f"   {k} {o}", each)) for k, o in enumerate(q.options, 1)][:2]  # the first two fit
    while options and room - cell_len(keep) - sum(cell_len(text) for _, text in options) - 2 < 12:
        options.pop()  # narrow: the question keeps twelve cells, and its last option gives way
    spare = room - cell_len(keep) - sum(cell_len(text) for _, text in options) - 2
    mark, style = ("!", "bold #e9a23b") if q.kind == "risk" else ("?", "bold #c77dff")
    segs = [
        Seg("▶" if on else " ", "bold"),
        Seg(f" {mark}    " + " " * models, style),  # the state's column, then the agent's, empty
        Seg(fit(q.text, max(spare, 12)), "bold" if on else ""),
        Seg("  "),
        Seg(keep, "bold #c77dff", "take"),
        *(Seg(text, "#c77dff", f"pick:{k}") for k, text in options),
    ]
    if on:  # opened (question_open lists the default and every option): the row is the question's words
        segs = segs[:2] + [Seg(fit(q.text, room), "bold")]
    if on:
        segs = [Seg(s.text, (s.style + FOCUS_BG).strip(), s.action) for s in segs]
    return Line(pad(segs, width, FOCUS_BG.strip() if on else ""), q.id)


def question_open(q: Question, width: int) -> list[Line]:
    """A selected question opens: its whole words, its default and every option by the number that picks it
    (the row has room for two at most), then how to answer it otherwise."""

    def lit(segs: list[Seg]) -> Line:  # on the selected row's ground, as the row above it
        return Line(pad([Seg(s.text, (s.style + FOCUS_BG).strip(), s.action) for s in segs], width,
                        FOCUS_BG.strip()), q.id)  # fmt: skip

    bar, room = Seg("      ┊ ", "grey35"), max(width - 10, 20)
    cut = cell_len(q.text) > max(width - LEAD - 2, 20)  # the row says the words whole when they fit
    out = [lit([bar, Seg(part)]) for part in textwrap.wrap(q.text, room)[:3]] if cut else []
    out.append(lit([bar, Seg(fit(f"⏎ {q.default}", room), "bold #c77dff", "take")]))
    for k, option in enumerate(q.options, 1):
        out.append(lit([bar, Seg(fit(f"{k} {option}", room), "#c77dff", f"pick:{k}")]))
    keys = [Seg("      a answer in your words", "grey70", "answer"), Seg("   d drop", "grey70", "drop")]
    out.append(lit(keys))
    return out


LEAD = 8  # "▶ ● 12 ": the arrow, the state, the number of the agent on it
MODEL_COL = 14  # the most cells the model's column takes: `stand-in-Nano` whole, a longer name cut
FOCUS_BG = " on #1a2030"


def model_col(m: Model) -> int:
    """The cells the model's column takes on every row, after the agent's number: the widest name any task
    says and one space, or nothing when no task names one (a plan nobody metered keeps today's rows)."""
    widest = max((cell_len(t.model) for t in m.tasks.values()), default=0)
    return min(widest, MODEL_COL) + 2 if widest else 0  # two spaces after it, as after the number


def forks_said(t: Task, width: int) -> str:
    """How many agents race on a forked task, and on which models, where one agent's pace goes: `3 forks ·
    Nano ×3` when they share one, else each in its turn (`Nano, Nano, Super`), cut to a third of the row
    (the stand-in's `3 forks · stand-in-Nano ×3` is whole at 80 columns)."""
    n, models = len(t.forks), [f.model for f in t.forks]
    said = f"{n} forks"
    if any(models):
        one = len(set(models)) == 1
        said += f" · {models[0]} ×{n}" if one else " · " + ", ".join(x or "?" for x in models)
    return f"{fit(said, max(14, width // 3))}  ".ljust(14)


def cents(usd: float | None) -> str:
    """Dollars on a row, as the bills spell them (`views.money`), or nothing for a spend too small to show
    at four places (`$0.0000` says less than no number)."""
    return money(usd) if usd and round(usd, 4) else ""
RUNNING = STATE_GLYPH["running"][1].split()[-1]  # the running amber
FORK_GLYPH = {  # how a fork ended, on its line: passed in the proven green, the rest in the came-back red
    "passed": ("✓", "#8ab17d"), "refused": ("✗", "#ef476f"), "failed": ("✗", "#ef476f"),
    "gave up": ("↩", "#ef476f"), "stopped": ("·", "grey50"),
}  # fmt: skip
# a fork's state, as the screens say it: `stopped` on these rows is the gate's word, for a write it refused
# (`stopped db/x.py`, `w widen`), so a fork the run stopped (another passed first) is `ended`
FORK_WORD = {"stopped": "ended"}


def right_of(m: Model, t: Task, width: int) -> list[Seg]:
    """The columns on the right of a task's row: what it is doing, in numbers."""
    if t.state == "running":
        quiet = m.quiet(t)
        pace = width >= (100 if t.stopped else 70)  # a stopped row's room goes to the key that frees it
        right = [Seg(m.pace(t) + "  ", RUNNING)] if pace else []  # its pace, in its state's colour
        if pace and t.forks:  # how many agents race on it, on what, where one agent's pace goes
            right = [Seg(forks_said(t, width), RUNNING)]
        if width >= 78:
            right += [Seg(f"✎{len(t.touched)}/{m.allowed(t)}".ljust(8), "grey62")]
        if t.checks:
            proven = "#8ab17d" if t.passed == t.checks else "grey62"
            right += [Seg(f"✓{t.passed}/{t.checks}".ljust(6), proven)]
        if cents(t.usd) and width >= 100:  # what it has cost so far, where the row has the room
            right += [Seg(cents(t.usd).ljust(8), "grey62")]
        if t.stopped:  # what the gate stopped, and the key that gives it: the fix, not a count
            path, room, more = t.stopped[-1][0], max(12, width // 5), len({p for p, _ in t.stopped}) - 1
            path = path if cell_len(path) <= room else fit_end(path.rsplit("/", 1)[-1], room)  # else its name
            right += [Seg(f"w widen {path}" + (f" +{more} " if more else " "), "bold #e9a23b", "allow")]
        if t.outside:
            right += [Seg(f"{len(t.outside)} OUTSIDE ", "bold #ef476f")]
        if quiet > 8:
            right += [Seg(f"⏸{ago(quiet)}", "bold #e9a23b")]
        return right
    if t.state == "waiting":  # who is on what it waits on, else what that is; one in review waits on you
        before = [m.tasks[n] for n in t.needs if n in m.tasks and m.tasks[n].state != "done"]
        after = sorted(("your sign-off: " * (o.state == "review") + named(m, o.id) for o in before), key=len)
        said = fit("← " + ", ".join(after), max(width // 3, 16))  # the short first: cut to a third of the row
        return [Seg(said if after else "", "grey50")]
    if t.state == "review":
        proof = f"✓{t.passed}/{t.checks}  " if t.checks else ""
        hollow = [Seg("passed before the work  ", "#e9a23b")] if t.hollow else []
        return [Seg(proof, "#8ab17d"), *hollow, Seg("⏎ sign off", "bold #c77dff", "take")]
    if t.state == "came back":  # the reason is cut to a third of the row: the open row says all of it
        why = fit(t.note or "stuck", max(width // 3, 16))
        return [Seg(why, "#ef476f"), Seg("   ⏎ try again", "bold #c77dff", "take")]
    if t.state == "proposed":  # how many files accepting it lets an agent write; ⏎, yours, in need-you purple
        n = m.allowed(t)
        return [Seg(f"{n} file{'s' * (n != 1)}".ljust(11), "grey50"), Seg("⏎ accept", "bold #c77dff", "take")]
    if t.state == "yours":
        return [Seg("yours", "#c77dff"), Seg("   ⏎ mark done", "bold #c77dff", "take")]
    if t.state == "ready":
        return [Seg("ready", "#d0d0d0")]
    n = len(t.changed)
    outside = bool(_outside(m, t))
    said = Seg(
        f"{n} file{'s' if n != 1 else ''}" + (" · OUTSIDE" if outside else ""),
        "bold #ef476f" if outside else "grey50",
    )
    if t.overruled:
        return [said, Seg(" · overruled", "bold #e9a23b")]
    return [said, Seg(" · check passed before the work", "#e9a23b")] if t.hollow else [said]


def task_lines(
    m: Model, t: Task, width: int, *, expanded: bool, tell: str | None, cols: int = 0
) -> list[Line]:
    glyph, gstyle = STATE_GLYPH.get(t.state, ("·", "grey50"))
    colour = color_of(t.agent) if t.agent else "grey62"
    on = expanded
    name = t.agent or ""
    models = model_col(m)  # the model after the number, in a column of its own, when any task names one
    lead = [
        Seg("▶" if on else " ", "bold"),
        Seg(f" {glyph} ", gstyle),
        Seg(f"{name:<2} ", f"bold {colour}" if name else ""),
        *([Seg(ljust(fit(t.model, models - 2), models), "grey62")] if models else []),
    ]
    right, more = right_of(m, t, width), 0
    if on and t.state == "came back" and long_note(t, width):  # the open row says it all, once, below:
        more, right = span(right[:1]), right[1:]  # its cut reason gives the title its room
    room = max(12, width - LEAD - models - cols - 1) + more
    gap = [Seg(" " * max(0, cols - more - span(right)))] if cols else []
    whole = short(t.full, 0) or t.title  # the whole title, its article and what follows a colon left out
    title = Seg(ljust(fit(whole, room - 1), room), "bold" if on else "", f"select:{t.id}")
    segs = lead + [title] + right + gap
    line = Line(pad(segs, width), t.id)
    out = [line]
    if t.kept:  # its hold forked, and this is the fork that landed, by the rule's one line
        out.append(Line([Seg("      ┊ ", "grey35"), Seg(fit(kept_said(t.kept), width - 10), "grey58")], t.id))
    if on and t.state in ("running", "review", "came back"):
        out += expansion(m, t, width)
    elif on and t.state == "proposed":
        out += proposal(m, t, width)
    elif t.state == "running" and t.events:  # its last move in one dim line: alive or stuck, at a glance
        said = m.tail(t, 1)[0]
        moved = [f for f in t.forks if f.events]  # forked: the newest fork's move, with its letter
        if moved and not said.startswith("you "):  # the person's own note is no fork's move
            said = f"{t.agent}{max(moved, key=lambda f: f.events[-1].t).letter} {said}"
        out.append(Line([Seg("      ┊ ", "grey35"), Seg(fit(said, width - 10), "grey58")], t.id))
    if tell is not None:  # the line being typed, under the row it is for: the only place it shows
        whom = who(t.agent) or "its agent"
        typed = [Seg(f"      tell {whom}: ", "bold #4cc9f0")]
        room = width - span(typed) - 2
        when = "" if t.state == "running" and t.hears else "starts" if t.state != "running" else "next starts"
        hint = f"   {whom} reads this when it {when}" if when else ""  # its contract tells it (board.decided)
        if cell_len(tell) + cell_len(hint) > room:  # a long line: its end, where you type, and no hint
            tell, hint = fit_end(tell, room), ""
        out.append(Line([*typed, Seg(tell + "▌", "bold"), Seg(hint, "grey50")], t.id))
    if on:
        for ln in out:
            for s in ln.segs:
                s.style = (s.style + FOCUS_BG).strip()
            ln.segs = pad(ln.segs, width, FOCUS_BG.strip())
    return out


def proposal(m: Model, t: Task, width: int) -> list[Line]:
    """What accepting a proposal agrees to: the files it may write, the check that proves it done, what it
    waits on; then its keys."""

    def said(words: list[Seg]) -> Line:
        return Line([Seg("      ┊ ", "grey35"), *words], t.id)

    out = [said([Seg("files  ", "grey50"), Seg(fit(", ".join(t.scope) or "none yet", width - 17), "grey70")])]
    if t.check:
        out.append(said([Seg("check  ", "grey50"), Seg(fit(t.check, width - 17), "grey70")]))
    elif not t.checks:
        out.append(said([Seg("no check yet: nothing can prove it done", "#e9a23b")]))
    before = [o.title for x in t.needs if (o := m.tasks.get(x)) and o.state != "done"]
    if before:
        out.append(said([Seg("waits  ", "grey50"), Seg(fit(", ".join(before), width - 17), "grey70")]))
    keys = [("⏎ accept", "bold #c77dff", "take"), ("d drop", "grey70", "drop"), ("e edit", "grey70", "edit"),
            ("i details", "grey50", "details")]  # fmt: skip
    out.append(Line([Seg("      ")] + [Seg(f"{k}   ", style, act) for k, style, act in keys], t.id))
    return out


OFFERS = (  # what a task that came back offers: its key, what it does, the word before what it acts on
    ("w", "widen", ""), ("b", "a new task", "for "), ("n", "wait on", ""), ("r", "reopen", ""),
)


def offered(m: Model, t: Task, key: str) -> str:
    """What an offer acts on, as its command names it: the paths a widen or a new task takes, the tasks it
    would wait on (not the ones it waits on now), the finished tasks it reopens."""
    argv = t.offers[key]
    if key in ("w", "b"):  # `node widen ID [PATH…]`, `node sibling ID [PATH…]`
        return ", ".join(argv[3:])
    if key == "n":  # `node set ID --needs A --needs B`
        ids = [x for flag, x in zip(argv, argv[1:], strict=False) if flag == "--needs" and x not in t.needs]
    else:  # `node reopen A [B…] --note … --for ID`
        ids = argv[2 : argv.index("--note")] if "--note" in argv else argv[2:]
    return ", ".join(named(m, i) for i in ids)


def named(m: Model, task_id: str) -> str:
    """Another task, as a row names it: by the agent on it, else (finished, waiting for your sign-off, or
    never taken) by its title; one the rows leave out (a finished task counted, not shown) by its id, the
    word its command takes."""
    o = m.tasks.get(task_id)
    if o is None:
        return task_id
    return who(o.agent) if o.agent and o.state not in ("done", "review") else short(o.full, 0) or o.title


def _outside(m: Model, t: Task) -> list[str]:
    return [p for p in t.changed if t.scope and not T._in(p, tuple(t.scope))]


def long_note(t: Task, width: int) -> bool:
    """Is the reason a task came back longer than its row shows (a third of it)?"""
    return len(t.note) > max(width // 3, 16)


def kept_said(kept: tuple[str, str, str], then: str = " · ") -> str:
    """The fork that landed, in one line: its letter, ``then`` the rule's reason, or that the person picked
    it (the news, whose items ` · ` parts, says `kept b: …`)."""
    letter, reason, by = kept
    if by == "person":  # the record names them; this screen says you
        return f"kept {letter}{then}your pick"
    return f"kept {letter}" + (f"{then}{reason}" if reason else "")


def fork_line(m: Model, t: Task, f: Fork, room: int) -> list[Seg]:
    """One fork of an open row: its number and letter in the agent's colour, then its model; running, its
    pace, its files, its dollars so far and its last move (and how long it has been quiet); ended, how, what
    it changed and cost (`1b Nano ✓ passed · 4 lines · $0.002`), and why when it did not pass."""
    name = [Seg(f"{t.agent}{f.letter} ", f"bold {color_of(t.agent)}" if t.agent else "")]
    name += [Seg(f"{f.model} ", "grey62")] if f.model else []
    if f.state != "running":
        glyph, style = FORK_GLYPH.get(f.state, ("·", "grey50"))
        said = FORK_WORD.get(f.state, f.state)
        said += f" · {f.lines} lines" if f.state == "passed" and f.lines else ""
        said += f" · {cents(f.usd)}" if cents(f.usd) else ""
        said += f": {f.why}" if f.why and f.state != "passed" else ""
        return [*name, Seg(f"{glyph} ", style), Seg(fit(said, room - span(name) - 2), style)]
    quiet = m.quiet(f)
    segs = [*name, Seg(m.pace(f, 6, 10.0) + " ", RUNNING), Seg(f"✎{len(f.touched)}  ", "grey62")]
    if cents(f.usd):
        segs.append(Seg(f"{cents(f.usd)}  ", "grey62"))
    if quiet > 8:
        segs.append(Seg(f"⏸{ago(quiet)}  ", "bold #e9a23b"))
    return segs + [Seg(fit((m.tail(f, 1) or [""])[0], room - span(segs)), "grey70")]


def expansion(m: Model, t: Task, width: int) -> list[Line]:
    out: list[Line] = []
    if t.state == "came back" and long_note(t, width):  # what the row had to cut, in three lines at most
        for part in textwrap.wrap(t.note, max(width - 12, 20), max_lines=3, placeholder=" …"):
            out.append(Line([Seg("      ┊ ", "grey35"), Seg(part, "#ef476f")], t.id))
    moves = [ln for ln in m.tail(t, 5) if not (t.told and ln.startswith("you "))][-3:]  # the note: below
    if t.forks and t.state in ("running", "review"):  # a line a fork, in place of one agent's moves
        for f in t.forks:
            out.append(Line([Seg("      ┊ ", "grey35"), *fork_line(m, t, f, width - 8)], t.id))
        moves = []
    for line in moves:
        style = "#e76f51" if line.startswith("stopped") else "grey70"
        out.append(Line([Seg("      ┊ ", "grey35"), Seg(fit(line, width - 10), style)], t.id))
    for text, sent, heard in t.told[-1:]:
        some = f"by {t.heard_by[sent]} of {len(t.forks)} " if t.forks and sent in t.heard_by else ""
        out.append(
            Line(
                [
                    Seg("      ┊ ", "grey35"),
                    Seg(f"you “{fit(text, 40)}”  ", "#4cc9f0"),
                    Seg(
                        f"heard {some}" + ago(m.clock - heard) + " ago"
                        if heard
                        else ("sending…" if t.hears else "it reads this when it next starts"),
                        "#8ab17d" if heard else "grey50",
                    ),
                ],
                t.id,
            )
        )
    verbs = [Seg("      ", ""), Seg("t tell", "bold #4cc9f0", "tell")]
    if t.state == "review":  # nobody is on it to tell: x reopens it, and its next agent is told why
        verbs = [Seg("   ", "")]
    if t.stopped:  # `graphene node widen` gives what the gate stopped: say which path, not a guess
        path, more = t.stopped[-1][0], len({p for p, _ in t.stopped}) - 1  # paths: a retry is no new one
        give = f"   w widen {fit(path, 28)}" + (f" +{more}" if more else "")
        verbs += [Seg(give, "bold #e9a23b", "allow")]
    for key, what, before in OFFERS:
        if key in t.offers and not (key == "w" and t.stopped):  # what a task that came back offers, on what
            on = offered(m, t, key)
            said = f"   {key} {what}" + (f" {before}{fit(on, max(12, width // 5))}" if on else "")
            verbs += [Seg(said, "bold #e9a23b", "allow" if key == "w" else f"offer:{key}")]
    if t.state in ("running", "review"):  # x hands a running task back, and reopens one that waits on you
        verbs += [Seg("   x hand back" if t.state == "running" else "   x reopen", "grey70", "back")]
    if t.state == "review" and t.forks:  # the digits pick another fork's work to sign off: 1 is a, 2 is b
        verbs += [Seg(f"   1-{len(t.forks)} pick", "bold #c77dff")]
    verbs += [Seg("   i details", "grey50", "details")]
    while span(verbs) > width and len(verbs) > 2:  # the last verbs give way first
        verbs.pop()
    out.append(Line(verbs, t.id))
    return out
