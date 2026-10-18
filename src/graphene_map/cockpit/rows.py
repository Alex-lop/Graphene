"""The cockpit screen: one row a task, the questions that wait for the person first, numbers on the right.

`build_cockpit` takes the model and a width and returns lines (lines.py). A row says who is on the task,
what its title is, and in numbers whether it is alive and on track: a sparkline of pace, files touched of
files allowed, proofs passed of proofs asked, writes stopped, seconds quiet. The row under the cursor
opens: the last lines of what the agent did, what the person told it and whether it heard, and the verbs.
"""

from __future__ import annotations

from . import territory as T
from .lines import Line, Seg, ago, fit, pad
from .look import STATE_GLYPH, color_of
from .model import Model, Question, Task


def build_cockpit(m: Model, width: int, *, tell: str | None = None) -> list[Line]:
    out: list[Line] = []
    need, running, done, total = m.scoreboard()
    tag = "replay" if m.source == "replay" else "your plan"
    head = [Seg(" " + fit(m.goal, width - len(tag) - 4), "bold"), Seg(" " * 1), Seg(tag, "grey50")]
    out.append(Line(pad(head, width)))
    out.append(
        Line(
            pad(
                [
                    Seg(f" {need}", "bold #c77dff"),
                    Seg(" need you   ", "#c77dff"),
                    Seg(str(running), "bold #e9c46a"),
                    Seg(" running   ", "#e9c46a"),
                    Seg(f"{done}/{total}", "bold #8ab17d"),
                    Seg(" proven", "#8ab17d"),
                ],
                width,
            )
        )
    )
    cells = max(10, min(width - 12, 40))
    fill = round(cells * done / max(total, 1))
    out.append(Line(pad([Seg(" " + "▰" * fill, "#8ab17d"), Seg("▱" * (cells - fill), "grey35")], width)))
    out.append(Line([Seg("─" * width, "grey30")]))
    sel = m.selected
    cols = max((sum(len(s.text) for s in right_of(m, t, width)) for t in m.tasks.values()), default=0)
    for kind, rid in m.order():
        if kind == "question":
            out.append(question_line(next(q for q in m.questions if q.id == rid), width, rid == sel))
            continue
        t = m.tasks[rid]
        out += task_lines(m, t, width, expanded=(rid == sel), tell=tell if rid == sel else None, cols=cols)
    if m.folded_done:
        out.append(Line([Seg(f"   ✓ {m.folded_done} more proven", "grey50")]))
    return out


def question_line(q: Question, width: int, on: bool) -> Line:
    """? the question, ⏎ its default, and the other options by the numbers `graphene board pick` takes."""
    room = max(width - 6, 20)
    keep = fit("⏎ " + q.default, max(room // 3, 12))
    options = [(k, fit(f"   {k} {o}", 16)) for k, o in enumerate(q.options, 1)][:2]  # the first two fit
    spare = room - len(keep) - sum(len(text) for _, text in options)
    segs = [
        Seg(" ? ", "bold #c77dff"),
        Seg(fit(q.text, max(spare, 12)), "bold" if on else ""),
        Seg("  "),
        Seg(keep, "bold #c77dff", "take"),
        *(Seg(text, "#c77dff", f"pick:{k}") for k, text in options),
    ]
    if on:
        segs = [Seg(s.text, (s.style + FOCUS_BG).strip(), s.action) for s in segs]
    return Line(pad(segs, width, FOCUS_BG.strip() if on else ""), q.id)


LEAD = 12  # "▶ ● fox    "
FOCUS_BG = " on #1a2030"


def right_of(m: Model, t: Task, width: int) -> list[Seg]:
    """The columns on the right of a task's row: what it is doing, in numbers."""
    colour = color_of(t.agent) if t.agent else "grey62"
    if t.state == "running":
        quiet = m.quiet(t)
        right = [Seg(m.pace(t) + "  ", colour)] if width >= 70 else []
        if width >= 78:
            right += [Seg(f"✎{len(t.touched)}/{m.allowed(t)}".ljust(8), "grey62")]
        right += [Seg(f"✓{t.passed}/{t.checks}".ljust(6), "#8ab17d" if t.passed == t.checks else "grey62")]
        if t.stopped:
            right += [Seg(f"!{len(t.stopped)} ", "bold #ef476f", "allow")]
        if quiet > 8:
            right += [Seg(f"⏸{ago(quiet)}", "bold #e9a23b")]
        return right
    if t.state == "waiting":
        after = " ".join(
            m.tasks[n].agent or m.tasks[n].id for n in t.needs if n in m.tasks and m.tasks[n].state != "done"
        )
        return [Seg("← " + after if after else "", "grey50")]
    if t.state == "review":
        return [Seg(f"✓{t.passed}/{t.checks}  ", "#8ab17d"), Seg("⏎ sign off", "bold #c77dff", "take")]
    if t.state == "came back":
        return [Seg(t.note or "stuck", "#ef476f"), Seg("   ⏎ try again", "bold #c77dff", "take")]
    if t.state == "proposed":
        return [Seg("⏎ accept", "bold #4cc9f0", "take")]
    if t.state == "ready":
        return [Seg("ready", "#d0d0d0")]
    n = len(t.changed)
    outside = bool(_outside(m, t))
    return [
        Seg(
            f"{n} file{'s' if n != 1 else ''}" + (" · OUTSIDE" if outside else ""),
            "bold #ef476f" if outside else "grey50",
        )
    ]


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
        Seg(f"{name:<6} ", f"bold {colour}" if name else ""),
    ]
    right = right_of(m, t, width)
    room = max(12, width - LEAD - cols - 1)
    gap = [Seg(" " * max(0, cols - sum(len(s.text) for s in right)))] if cols else []
    segs = (
        lead + [Seg(fit(t.title, room - 1).ljust(room), "bold" if on else "", f"select:{t.id}")] + right + gap
    )
    line = Line(pad(segs, width), t.id)
    out = [line]
    if on and t.state in ("running", "review", "came back"):
        out += expansion(m, t, width, tell)
    if on:
        for ln in out:
            for s in ln.segs:
                s.style = (s.style + FOCUS_BG).strip()
            ln.segs = pad(ln.segs, width, FOCUS_BG.strip())
    return out


def _outside(m: Model, t: Task) -> list[str]:
    return [p for p in t.changed if t.scope and not T._in(p, tuple(t.scope))]


def expansion(m: Model, t: Task, width: int, tell: str | None) -> list[Line]:
    out: list[Line] = []
    for line in m.tail(t, 3):
        style = "#e76f51" if line.startswith("stopped") else "grey70"
        out.append(Line([Seg("      ┊ ", "grey35"), Seg(fit(line, width - 10), style)], t.id))
    for text, _sent, heard in t.told[-1:]:
        out.append(
            Line(
                [
                    Seg("      ┊ ", "grey35"),
                    Seg(f"you “{fit(text, 40)}”  ", "#4cc9f0"),
                    Seg(
                        "heard " + ago(m.clock - heard) + " ago" if heard else "sending…",
                        "#8ab17d" if heard else "grey50",
                    ),
                ],
                t.id,
            )
        )
    verbs = [Seg("      ", ""), Seg("t tell", "bold #4cc9f0", "tell")]
    if t.stopped:
        folder = t.stopped[-1][0].rsplit("/", 1)[0] + "/"
        verbs += [Seg("   w give it " + folder, "bold #e9a23b", "allow")]
    if t.state == "running":
        verbs += [Seg("   x pull back", "grey70", "back")]
    verbs += [Seg("   ⏎ everything", "grey50")]
    out.append(Line(verbs, t.id))
    if tell is not None:
        out.append(
            Line([Seg(f"      tell {t.agent or t.id}: ", "bold #4cc9f0"), Seg(tell + "▌", "bold")], t.id)
        )
    return out
