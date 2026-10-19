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

from . import territory as T
from .lines import Line, Seg, ago, fit, fit_end, ljust, pad, span
from .look import STATE_GLYPH, color_of, short, who
from .model import Model, Question, Task

NO_GOAL = "no goal yet"  # what the plan's reader says of a plan with none (views.inputs)
INVITE = 'no goal yet · :plan goal "…" tells every agent what this is for'


def build_head(m: Model, width: int) -> list[Line]:
    """What stays on top while the rows scroll: your goal (or how to give one), then where the plan stands
    in one line, what needs you, what runs and what is proven, with the proven part as a bar."""
    need, running, done, total = m.scoreboard()
    goal = "" if m.goal in ("", NO_GOAL) else m.goal
    tag = m.banner or ("replay" if m.source == "replay" else "")  # the live plan needs no word
    parts = tag.split(" · ") if tag else []
    room = width - min(cell_len(goal or NO_GOAL), 24) - 6  # the goal keeps what it needs, the banner the rest
    while cell_len(" · ".join(parts)) > max(16, room) and len(parts) > 2:
        parts.pop(2)  # narrow: the day goes, then where it is; never what it is and what made it
    tag = " · ".join(parts)
    said = goal or (NO_GOAL if tag else INVITE)  # your goal on top; with none, how to give one (not a title)
    head = [Seg(" " + fit(said, width - (cell_len(tag) + 5 if tag else 2)), "bold" if goal else "grey62")]
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
    return [Line(pad(head, width)), *counted, Line([Seg("─" * width, "grey30")])]


def build_cockpit(m: Model, width: int, *, tell: str | None = None) -> list[Line]:
    """The rows, which scroll under the head (build_head): what needs you first, then the rest."""
    out: list[Line] = []
    sel = m.selected
    cols = max((span(right_of(m, t, width)) for t in m.tasks.values()), default=0)
    if not m.order() and not m.folded_done:
        return empty(m, width)
    for kind, rid in m.order():
        if kind == "question":
            out.append(question_line(next(q for q in m.questions if q.id == rid), width, rid == sel))
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


def question_line(q: Question, width: int, on: bool) -> Line:
    """? the question (! a risk), ⏎ its default, and the other options by the numbers `graphene board pick`
    takes. Its words start where a task's title does, so the rows have one left edge."""
    room = max(width - LEAD - 2, 20)
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
        Seg(f" {mark}    ", style),  # the state's column, then the agent's, empty
        Seg(fit(q.text, max(spare, 12)), "bold" if on else ""),
        Seg("  "),
        Seg(keep, "bold #c77dff", "take"),
        *(Seg(text, "#c77dff", f"pick:{k}") for k, text in options),
    ]
    if on:
        segs = [Seg(s.text, (s.style + FOCUS_BG).strip(), s.action) for s in segs]
    return Line(pad(segs, width, FOCUS_BG.strip() if on else ""), q.id)


LEAD = 8  # "▶ ● 12 ": the arrow, the state, the number of the agent on it
FOCUS_BG = " on #1a2030"
RUNNING = STATE_GLYPH["running"][1].split()[-1]  # the running amber


def right_of(m: Model, t: Task, width: int) -> list[Seg]:
    """The columns on the right of a task's row: what it is doing, in numbers."""
    if t.state == "running":
        quiet = m.quiet(t)
        pace = width >= (100 if t.stopped else 70)  # a stopped row's room goes to the key that frees it
        right = [Seg(m.pace(t) + "  ", RUNNING)] if pace else []  # its pace, in its state's colour
        if width >= 78:
            right += [Seg(f"✎{len(t.touched)}/{m.allowed(t)}".ljust(8), "grey62")]
        if t.checks:
            proven = "#8ab17d" if t.passed == t.checks else "grey62"
            right += [Seg(f"✓{t.passed}/{t.checks}".ljust(6), proven)]
        if t.stopped:  # what the gate stopped, and the key that gives it: the fix, not a count
            path, room, more = t.stopped[-1][0], max(12, width // 5), len({p for p, _ in t.stopped}) - 1
            path = path if cell_len(path) <= room else fit_end(path.rsplit("/", 1)[-1], room)  # else its name
            right += [Seg(f"w widen {path}" + (f" +{more} " if more else " "), "bold #e9a23b", "allow")]
        if t.outside:
            right += [Seg(f"{len(t.outside)} OUTSIDE ", "bold #ef476f")]
        if quiet > 8:
            right += [Seg(f"⏸{ago(quiet)}", "bold #e9a23b")]
        return right
    if t.state == "waiting":
        before = [m.tasks[n] for n in t.needs if n in m.tasks and m.tasks[n].state != "done"]
        after = ", ".join(who(o.agent) or o.title for o in before)  # who is on it, else what it is
        return [Seg("← " + after if after else "", "grey50")]
    if t.state == "review":
        proof = f"✓{t.passed}/{t.checks}  " if t.checks else ""
        return [Seg(proof, "#8ab17d"), Seg("⏎ sign off", "bold #c77dff", "take")]
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
    return [said, Seg(" · overruled", "bold #e9a23b")] if t.overruled else [said]


def task_lines(
    m: Model, t: Task, width: int, *, expanded: bool, tell: str | None, cols: int = 0
) -> list[Line]:
    glyph, gstyle = STATE_GLYPH.get(t.state, ("·", "grey50"))
    colour = color_of(t.agent) if t.agent else "grey62"
    on = expanded
    name = t.agent or ""
    lead = [
        Seg("▶" if on else " ", "bold"),
        Seg(f" {glyph} ", gstyle),
        Seg(f"{name:<2} ", f"bold {colour}" if name else ""),
    ]
    right, more = right_of(m, t, width), 0
    if on and t.state == "came back" and long_note(t, width):  # the open row says it all, once, below:
        more, right = span(right[:1]), right[1:]  # its cut reason gives the title its room
    room = max(12, width - LEAD - cols - 1) + more
    gap = [Seg(" " * max(0, cols - more - span(right)))] if cols else []
    whole = short(t.full, 0) or t.title  # the whole title, its article and what follows a colon left out
    title = Seg(ljust(fit(whole, room - 1), room), "bold" if on else "", f"select:{t.id}")
    segs = lead + [title] + right + gap
    line = Line(pad(segs, width), t.id)
    out = [line]
    if on and t.state in ("running", "review", "came back"):
        out += expansion(m, t, width)
    elif on and t.state == "proposed":
        out += proposal(m, t, width)
    elif t.state == "running" and t.events:  # its last move in one dim line: alive or stuck, at a glance
        out.append(Line([Seg("      ┊ ", "grey35"), Seg(fit(m.tail(t, 1)[0], width - 10), "grey58")], t.id))
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
    check = getattr(t, "check", "")  # its command, once the plan's reader gives it (read.py)
    if check:
        out.append(said([Seg("check  ", "grey50"), Seg(fit(check, width - 17), "grey70")]))
    elif not t.checks:
        out.append(said([Seg("no check yet: nothing can prove it done", "#e9a23b")]))
    before = [o.title for x in t.needs if (o := m.tasks.get(x)) and o.state != "done"]
    if before:
        out.append(said([Seg("waits  ", "grey50"), Seg(fit(", ".join(before), width - 17), "grey70")]))
    keys = [("⏎ accept", "bold #c77dff", "take"), ("d drop", "grey70", "drop"), ("e edit", "grey70", "edit"),
            ("i details", "grey50", "details")]  # fmt: skip
    out.append(Line([Seg("      ")] + [Seg(f"{k}   ", style, act) for k, style, act in keys], t.id))
    return out


def _outside(m: Model, t: Task) -> list[str]:
    return [p for p in t.changed if t.scope and not T._in(p, tuple(t.scope))]


def long_note(t: Task, width: int) -> bool:
    """Is the reason a task came back longer than its row shows (a third of it)?"""
    return len(t.note) > max(width // 3, 16)


def expansion(m: Model, t: Task, width: int) -> list[Line]:
    out: list[Line] = []
    if t.state == "came back" and long_note(t, width):  # what the row had to cut, in three lines at most
        for part in textwrap.wrap(t.note, max(width - 12, 20), max_lines=3, placeholder=" …"):
            out.append(Line([Seg("      ┊ ", "grey35"), Seg(part, "#ef476f")], t.id))
    moves = [ln for ln in m.tail(t, 5) if not (t.told and ln.startswith("you "))][-3:]  # the note: below
    for line in moves:
        style = "#e76f51" if line.startswith("stopped") else "grey70"
        out.append(Line([Seg("      ┊ ", "grey35"), Seg(fit(line, width - 10), style)], t.id))
    for text, _sent, heard in t.told[-1:]:
        out.append(
            Line(
                [
                    Seg("      ┊ ", "grey35"),
                    Seg(f"you “{fit(text, 40)}”  ", "#4cc9f0"),
                    Seg(
                        "heard " + ago(m.clock - heard) + " ago"
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
    for key, what in (("w", "widen"), ("b", "a sibling"), ("n", "wait on it"), ("r", "reopen")):
        if key in t.offers and not (key == "w" and t.stopped):  # what a leaf that came back offers
            verbs += [Seg(f"   {key} {what}", "bold #e9a23b", "allow" if key == "w" else f"offer:{key}")]
    if t.state in ("running", "review"):  # x hands a running task back, and reopens one that waits on you
        verbs += [Seg("   x hand back" if t.state == "running" else "   x reopen", "grey70", "back")]
    verbs += [Seg("   i details", "grey50", "details")]
    while span(verbs) > width and len(verbs) > 2:  # the last verbs give way first
        verbs.pop()
    out.append(Line(verbs, t.id))
    return out
