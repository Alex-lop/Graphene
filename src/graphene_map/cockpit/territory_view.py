"""The territory screen: which folders each task may write, as bars and numbers.

One row a folder: a bar shared between the tasks whose scope covers its files (or, in the changed lens,
between the tasks that changed them), who owns it, and what is happening at its edge. The selected task's
folders are lit. Before a plan is accepted this is its blast radius (13 of 636 files may be touched);
while it runs, what is being touched and what the gate stopped; after, what changed and whether any of it
was outside the scope.
"""

from __future__ import annotations

from . import territory as T
from .lines import Line, Seg, pad
from .model import Model


def build_territory(m: Model, width: int, cursor: int = 0) -> tuple[list[Line], list[T.Group]]:
    groups, summary = T.compute(m.files, m.tasks_dict(), m.protected, lens=m.lens)
    out: list[Line] = []
    lens = {"plan": "what tasks may touch", "live": "what is happening now", "changed": "what changed"}[
        m.lens
    ]
    more = f" + new files in {summary['new']} place{'s' * (summary['new'] != 1)}" if summary["new"] else ""
    head = [
        Seg(" TERRITORY ", "bold"),
        Seg(
            f"{summary['may']} of {summary['files']} files may be touched ({summary['percent']}%){more}",
            "bold #e9c46a" if m.lens != "changed" else "bold #8ab17d",
        ),
    ]
    out.append(Line(pad(head, width)))
    note = [Seg(" lens ", "grey50"), Seg(lens, "#4cc9f0"), Seg("   v next lens", "grey50")]
    if summary["protected"]:
        note += [Seg("   protected: " + " ".join(summary["protected"]), "#ef476f")]
    out.append(Line(pad(note, width)))
    out.append(Line([Seg("─" * width, "grey30")]))
    namew = min(28, max(16, max((len(g.name) for g in groups), default=16)))
    barw = max(12, min(30, width - namew - 30))
    sel = m.tasks.get(m.selected)
    for k, g in enumerate(groups):
        mine = bool(sel) and g.owners.get(sel.id, 0) > 0
        runs = T.bar(g, barw, m.lens, m.color)
        label = g.name if len(g.name) <= namew else "…" + g.name[-(namew - 1) :]
        segs = [
            Seg("▶" if k == cursor else " ", "bold"),
            Seg(f" {label:<{namew}} ", "bold" if k == cursor else ("#e9c46a" if mine else ""), f"group:{k}"),
        ]
        segs += [Seg(text, style, f"group:{k}") for text, style in runs]
        segs += [Seg("  ")]
        if m.lens == "changed":
            for tid, n in g.changed.most_common(3):
                segs += [Seg(f"{m.tasks[tid].agent or tid} {n}  ", m.color(tid))]
            if g.outside:
                segs += [Seg(f"{g.outside} OUTSIDE", "bold #ef476f")]
            if not g.changed:
                segs += [Seg("untouched", "grey42")]
        else:
            for tid, n in g.owners.most_common(3):
                segs += [Seg(f"{m.tasks[tid].agent or tid} {n}  ", m.color(tid))]
            if g.protected:
                segs += [Seg("PROTECTED", "bold #ef476f")]
            elif not g.owners:
                segs += [Seg("nobody", "grey42")]
            if m.lens == "live":
                if g.touched:
                    segs += [Seg(f"● {g.touched} now  ", "#e9c46a")]
                if g.stopped:
                    who = m.tasks[g.stopped_by[-1]].agent or g.stopped_by[-1]
                    segs += [
                        Seg(f" !{g.stopped} stopped", "bold #ef476f"),
                        Seg(f"  a: allow {who}", "#e9a23b", "allow"),
                    ]
        out.append(Line(pad(segs, width, "reverse" if k == cursor and False else "")))
    waits = _waits(m)
    if waits:
        out.append(Line([Seg("")]))
        for w in waits:
            out.append(Line([Seg(" " + w, "#e9a23b")]))
    out.append(Line([Seg("")]))
    out.append(
        Line([Seg(" p paint the selected task here   left/right pick task   j/k move   v lens", "grey50")])
    )
    return out, groups


def _waits(m: Model) -> list[str]:
    """Tasks held back because a task in front of them owns the files: why work is not parallel."""
    out = []
    live = [t for t in m.tasks.values() if t.state in ("running", "ready", "review")]
    for t in m.tasks.values():
        if t.state != "waiting" or not t.scope:
            continue
        for o in live:
            if o.scope and any(T._in(f, tuple(t.scope)) and T._in(f, tuple(o.scope)) for f in m.files[:400]):
                out.append(f"{t.title} waits for {o.agent or o.id}: it owns the same files")
                break
    return out[:3]
