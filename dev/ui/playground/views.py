"""The three screens as lines of styled segments. No Textual here: each `build_*` takes the model and a
width and returns `Line`s, so a headless check can print a frame and a widget can paint and hit-test it.

A segment can carry an `action` ("take", "tell", "select:fox", "paint:models/"...): a click on it does
that. That is how a row's words are also its buttons.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import flowlayout as F
import territory as T
from model import Model, Task, color_of

STATE_GLYPH = {
    "running": ("●", "bold #e9c46a"), "review": ("◆", "bold #c77dff"), "came back": ("↩", "bold #ef476f"),
    "ready": ("○", "#d0d0d0"), "waiting": ("◌", "grey50"),
    "proposed": ("?", "#4cc9f0"), "done": ("✓", "#8ab17d"),
}  # fmt: skip
FLOW_STYLES = {
    "running": "bold #e9c46a", "done": "#8ab17d", "review": "bold #c77dff", "came back": "bold #ef476f",
    "ready": "#d0d0d0", "waiting": "grey50", "proposed": "#4cc9f0", "edge": "grey42",
    "edge_hot": "bold #4cc9f0",
    "node_sel": "bold #ffffff", "plain": "grey62", "label:plain": "#d8dee9",
    "node": "grey70",
    "label:running": "bold", "label:done": "grey62", "label:waiting": "grey58", "edge_loop": "#e9a23b",
    "glyph:running": "●", "glyph:done": "✓", "glyph:review": "◆", "glyph:came back": "↩", "glyph:ready": "○",
    "glyph:waiting": "◌", "glyph:proposed": "?",
}  # fmt: skip


@dataclass
class Seg:
    text: str
    style: str = ""
    action: str = ""


@dataclass
class Line:
    segs: list[Seg] = field(default_factory=list)
    row: str = ""  # the model row this line belongs to (a task or question id)

    def plain(self) -> str:
        return "".join(s.text for s in self.segs)

    def width(self) -> int:
        return sum(len(s.text) for s in self.segs)


def seg_at(line: Line, x: int) -> Seg | None:
    at = 0
    for s in line.segs:
        if at <= x < at + len(s.text):
            return s
        at += len(s.text)
    return None


def pad(segs: list[Seg], width: int, style: str = "") -> list[Seg]:
    used = sum(len(s.text) for s in segs)
    return segs + ([Seg(" " * (width - used), style)] if used < width else [])


def fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 0)] + "…"


def ago(seconds: float) -> str:
    return f"{int(seconds)}s" if seconds < 90 else f"{int(seconds // 60)}m"


# -- cockpit ---------------------------------------------------------------------------------------

def build_cockpit(m: Model, width: int, *, tell: str | None = None) -> list[Line]:
    out: list[Line] = []
    need, running, done, total = m.scoreboard()
    tag = "replay" if m.source == "demo" else ("replay" if m.simulate else "your plan")
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
            q = next(q for q in m.questions if q.id == rid)
            on = rid == sel
            room = max(width - 6, 20)
            keep = fit("⏎ " + q.default, max(room // 3, 12))
            others = [fit(f"   {k + 1} {o}", 16) for k, o in enumerate(q.options) if o != q.default][:2]
            spare = room - len(keep) - sum(len(o) for o in others)
            segs = [
                Seg(" ? ", "bold #c77dff"),
                Seg(fit(q.text, max(spare, 12)), "bold" if on else ""),
                Seg("  "),
            ]
            segs += [Seg(keep, "bold #c77dff", "take")]
            for k, o in enumerate(q.options):
                if (
                    o != q.default
                    and f"   {k + 1} {o}" in [x for x in others] + [fit(f"   {k + 1} {o}", 16)]
                    and len(segs) < 8
                ):
                    segs += [Seg(fit(f"   {k + 1} {o}", 16), "#c77dff", f"pick:{k}")]
            out.append(Line(pad(segs, width, "reverse" if on else ""), rid))
            continue
        t = m.tasks[rid]
        out += task_lines(m, t, width, expanded=(rid == sel), tell=tell if rid == sel else None, cols=cols)
    if m.folded_done:
        out.append(Line([Seg(f"   ✓ {m.folded_done} more proven", "grey50")]))
    return out


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
    from territory import _in

    return [p for p in t.changed if t.scope and not _in(p, tuple(t.scope))]


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


# -- territory -------------------------------------------------------------------------------------


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
    from territory import _in

    out = []
    live = [t for t in m.tasks.values() if t.state in ("running", "ready", "review")]
    for t in m.tasks.values():
        if t.state != "waiting" or not t.scope:
            continue
        for o in live:
            if o.scope and any(_in(f, tuple(t.scope)) and _in(f, tuple(o.scope)) for f in m.files[:400]):
                out.append(f"{t.title} waits for {o.agent or o.id}: it owns the same files")
                break
    return out[:3]


# -- flow ------------------------------------------------------------------------------------------


def flow_graph(m: Model) -> tuple[list[F.GNode], list[F.GEdge]]:
    nodes = [
        F.GNode(t.id, t.title, t.state, t.agent if t.state == "running" else "") for t in m.tasks.values()
    ]
    edges = [F.GEdge(n, t.id) for t in m.tasks.values() for n in t.needs if n in m.tasks]
    edges += [F.GEdge(a, b, k) for a, b, k in m.extra_edges if a in m.tasks and b in m.tasks]
    return nodes, edges


def build_flow(
    nodes: list[F.GNode], edges: list[F.GEdge], width: int, selected: str | None, pan: int = 0
) -> tuple[list[Line], F.Layout, str]:
    """Lay the graph out as wide as it will go, then shrink labels, then show the neighbourhood."""
    note = ""
    lay = None
    for label_w in (18, 14, 12, 10):
        lay = F.layout(nodes, edges, label_w=label_w, selected=selected, styles=FLOW_STYLES)
        if lay.width <= width:
            break
    if lay is not None and lay.width > width and selected and len(nodes) > 5:
        for hops in (2, 1):
            n2, e2 = F.neighbourhood(nodes, edges, selected, hops)
            lay = F.layout(n2, e2, label_w=12, selected=selected, styles=FLOW_STYLES)
            lay.hidden = len(nodes) - len(n2)
            steps = f"{hops} step{'s' * (hops > 1)}"
            note = f"showing {len(n2)} of {len(nodes)}: {selected} and what is within {steps}"
            if lay.width <= width:
                break
    assert lay is not None
    lines = []
    for y, row in enumerate(lay.cells):
        segs: list[Seg] = []
        for x, (ch, st) in enumerate(row[pan : pan + width]):
            nid = lay.at(x + pan, y)
            style = FLOW_STYLES.get(st, st) if st in FLOW_STYLES else st
            if segs and segs[-1].style == style and segs[-1].action == (f"select:{nid}" if nid else ""):
                segs[-1].text += ch
            else:
                segs.append(Seg(ch, style, f"select:{nid}" if nid else ""))
        lines.append(Line(segs))
    return lines, lay, note
