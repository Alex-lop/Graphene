"""The map screen: which folders each task may write, as bars and numbers.

One row a folder: a bar shared between the tasks whose scope covers its files (or, in the changed lens,
between the tasks that changed them), who owns it, and what is happening at its edge. The selected task's
folders are lit. Before a plan is accepted this is its blast radius (13 of 636 files may be touched);
while it runs, what is being touched and what the gate stopped; after, what changed and whether any of it
was outside the scope.
"""

from __future__ import annotations

from rich.cells import cell_len

from . import territory as T
from .lines import Line, Seg, fit, fit_end, ljust, pad, span
from .look import who
from .model import Model, Task

HEAD = 3  # lines above the first folder: the total, the lens, the rule
EMPTY = "Nothing is planned yet: the map shows which folders each task may write."


def build_territory(m: Model, width: int, cursor: int = 0) -> tuple[list[Line], list[T.Group]]:
    if not m.tasks:  # one line, not a row of "nobody" for every folder
        return [Line([Seg(" " + EMPTY, "grey62")])], []
    groups, summary = T.compute(m.files, m.tasks_dict(), m.protected, lens=m.lens)
    out: list[Line] = []
    lens = {"plan": "what tasks may touch", "live": "what is happening now", "changed": "what changed"}[
        m.lens
    ]
    out.append(Line(pad([Seg(" MAP ", "bold"), *headline(m.lens, summary)], width)))
    note = [Seg(" lens ", "grey50"), Seg(lens, "#4cc9f0"), Seg("   v next lens", "grey50")]
    if summary["protected"]:
        note += [Seg("   protected: " + " ".join(summary["protected"]), "#ef476f")]
    sel = m.tasks.get(m.selected)
    room = width - span(note) - 7
    if sel and room >= 8:  # whose folders are lit, and what w and p act on
        named = " · ".join(filter(None, (who(sel.agent), sel.title)))
        note += [Seg("   ←/→ ", "grey50"), Seg(fit(named, room), m.color(sel.id))]
    out.append(Line(pad(note, width)))
    out.append(Line([Seg("─" * width, "grey30")]))
    namew = min(28, max(16, max((cell_len(g.name) for g in groups), default=16)))
    barw = max(10, min(30, width - namew - 40))  # at 80 columns the marks after the bar still fit
    for k, g in enumerate(groups):
        mine = bool(sel) and g.owners.get(sel.id, 0) > 0
        runs = T.bar(g, barw, m.lens, m.color)
        label = fit_end(g.name, namew)
        name_style = "bold" if k == cursor else ("#e9c46a" if mine else "")
        name = Seg(f" {ljust(label, namew)} ", name_style, f"group:{k}")
        segs = [Seg("▶" if k == cursor else " ", "bold"), name]
        segs += [Seg(text, style, f"group:{k}") for text, style in runs]
        segs += [Seg("  ")]
        if m.lens == "live" and g.touched:  # what happens at the folder comes first: a narrow screen keeps it
            segs += [Seg(f"● {g.touched} now  ", "#e9c46a")]
        if m.lens == "live" and g.stopped:
            stopper = m.tasks[g.stopped_by[-1]]
            segs += [Seg(f"!{g.stopped} stopped  ", "bold #ef476f")]
            if stopper is sel:  # w gives the selected task what its gate stopped
                segs += [Seg("w widen  ", "bold #e9a23b", "allow")]
            else:  # someone else's: a click selects it
                segs += [Seg(f"by {name_of(stopper)}  ", m.color(stopper.id), f"select:{stopper.id}")]
        flag = []  # a red word after the names, kept when they give way
        if m.lens == "changed" and g.outside:
            flag = [Seg(f"{g.outside} OUTSIDE", "bold #ef476f")]
        elif g.protected and m.lens != "changed":
            flag = [Seg("PROTECTED", "bold #ef476f")]
        keep = len(segs)
        counts = g.changed if m.lens == "changed" else g.owners
        for tid, n in counts.most_common(3):
            segs += [Seg(f"{name_of(m.tasks[tid])} ({n})  ", m.color(tid))]
        if not counts and not flag:
            segs += [Seg("untouched" if m.lens == "changed" else "nobody", "grey42")]
        while span(segs + flag) > width and len(segs) > keep:  # the names give way first
            segs.pop()
        out.append(Line(pad(segs + flag, width)))
    waits = _waits(m)
    if waits:
        out.append(Line([Seg("")]))
        for w in waits:
            out.append(Line([Seg(" " + w, "#e9a23b")]))
    return out, groups


def name_of(t: Task, room: int = 16) -> str:
    """A task as the map names it: by its agent ("agent 1"), else by its title, never by its id."""
    return who(t.agent) or fit(t.title, room)


def headline(lens: str, summary: dict) -> list[Seg]:
    """What the lens says in one line, from the summary `territory.compute` made: before the run what the plan
    may touch, during it what is being written and stopped, after it what changed and whether all of it was
    inside its task's scope."""
    if lens == "live":
        writing, stopped = summary["writing"], summary["stopped"]
        if not writing and not stopped:
            return [Seg("nothing is being written now", "grey62")]
        return [
            Seg(f"{writing} file{'s' * (writing != 1)} being written", "bold #e9c46a"),
            Seg(f" · {stopped} write{'s' * (stopped != 1)} stopped", "bold #ef476f" if stopped else "grey50"),
        ]
    if lens == "changed":
        changed, folders, outside = summary["changed"], summary["folders"], summary["outside"]
        if not changed:
            return [Seg("no files changed yet", "grey62")]
        return [
            Seg(f"{changed} file{'s' * (changed != 1)} changed in {folders} folder{'s' * (folders != 1)}",
                "bold #8ab17d"),
            Seg(f" · {outside} outside {'its' if outside == 1 else 'their'} scope",
                "bold #ef476f" if outside else "grey50"),
        ]  # fmt: skip
    new = summary["new"]
    more = f" + new files in {new} place{'s' * (new != 1)}" if new else ""
    said = f"{summary['may']} of {summary['files']} files may be touched ({summary['percent']}%){more}"
    return [Seg(said, "bold #e9c46a")]


def _waits(m: Model) -> list[str]:
    """Tasks held back because a task in front of them owns the files: why work is not parallel."""
    out = []
    live = [t for t in m.tasks.values() if t.state in ("running", "ready", "review")]
    for t in m.tasks.values():
        if t.state != "waiting" or not t.scope:
            continue
        for o in live:
            if o.scope and any(T._in(f, tuple(t.scope)) and T._in(f, tuple(o.scope)) for f in m.files[:400]):
                out.append(f"{t.title} waits for {name_of(o)}: it owns the same files")
                break
    return out[:3]
