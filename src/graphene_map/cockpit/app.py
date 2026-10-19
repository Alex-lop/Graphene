"""The cockpit app: three screens over one model and one selection, a canvas that scrolls, a line of news.

`Cockpit` is handed a `looker`: a function from the model last shown (or None) to the model now. In the
product it reads the plan's store (read.py); a test hands it a model it built. Everything on the canvas is
lines (lines.py) painted and turned back into actions when clicked, so the words on a row are its buttons.
The screens: cockpit (c), flow (g), territory (m). The keys are the verbs; a verb is a command that
exists on its own (verbs.py), and the line at the bottom says what the last one did.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from functools import partial
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.events import Click
from textual.geometry import Region
from textual.widget import Widget
from textual.widgets import Input, Static

from .. import plan as P
from .. import plan_text as PT
from ..tui import ASK_HINT, Ask
from . import flow_view as FV
from . import flowlayout as F
from . import territory as T
from .details import DIRECTION, Details
from .help import Help
from .lines import Line, Seg, fit_keys, seg_at
from .look import who
from .model import Model
from .rows import build_cockpit
from .territory_view import HEAD, build_territory
from .verbs import Doer

SCREENS = ("cockpit", "flow", "territory")
KEYS = {  # one line each, at most 79 columns: the screen's own keys, then the ones every screen has
    "cockpit": "⏎ take · i all · t tell · w allow · x back · g graph · m map · ? keys · q quit",
    "flow": "arrows · ⏎ take · t tell · w allow · c cockpit · m map · ? keys · q quit",
    "territory": "j/k folder · ←/→ task · p paint · v lens · w allow · c cockpit · ? keys · q",
}
KEYS_TO_VERBS = {  # a key, and the verb it asks for (`act`)
    "t": "tell", "w": "allow", "x": "back", "d": "drop", "r": "run", "R": "run-all", "a": "answer",
    "b": "offer:b", "n": "offer:n", "colon": "command", "y": "take", "s": "split", "P": "first", "u": "undo",
    "e": "edit", "E": "edit-plan", "D": "direction", "i": "details",
}  # fmt: skip
LEGEND = "✎ files touched of allowed · ✓ proofs · ! writes stopped · ⏸ quiet · ▁▃▅ activity"


class Canvas(Widget):
    """Paints lines of segments and turns a click on a segment into that segment's action."""

    # a line wider than the screen is cut, not wrapped: wrapped, it would shift every row and click under it
    DEFAULT_CSS = "Canvas { height: auto; width: auto; text-wrap: nowrap; text-overflow: clip; }"

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[Line] = []

    def set_lines(self, lines: list[Line]) -> None:
        self.lines = lines
        self.refresh(layout=True)

    def render(self) -> Text:
        out = Text(no_wrap=True, overflow="crop")
        for k, line in enumerate(self.lines):
            for s in line.segs:
                out.append(s.text, style=s.style or None)
            if k < len(self.lines) - 1:
                out.append("\n")
        return out

    def on_click(self, event: Click) -> None:
        if 0 <= event.y < len(self.lines):
            line = self.lines[event.y]
            self.app.clicked(line, seg_at(line, event.x))  # type: ignore[attr-defined]


class Cockpit(App):
    TITLE = "graphene watch"
    AUTO_FOCUS = None  # the hidden tell box must not take the keys
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [Binding("question_mark", "help", show=False)]  # a binding, so the key that opens it is spent
    CSS = """
    Screen { background: #0e1014; }
    Ask { background: #0e1014 55%; }
    #bar { height: 1; background: #181b22; color: #9aa0ad; }
    #feed { height: 1; }
    #keys { height: 1; background: #181b22; color: #7d8492; }
    #tell { display: none; height: 3; }
    #tell.on { display: block; }
    """

    def __init__(
        self,
        looker: Callable[[Model | None], Model],
        every: float = 1.0,
        screen: str = "cockpit",
        root: Path | None = None,
        open_store: Callable | None = None,
    ) -> None:
        super().__init__()
        self.looker, self.every, self.root, self.open_store = looker, every, root, open_store
        self.model = looker(None)
        # the verbs need a repository to run their commands in: a test without one only looks
        say = lambda said: self.model.say(said)  # noqa: E731  (the model is a new one each look)
        self.doer = Doer(root, say, self.look, self.call_from_thread) if root else None
        self.view = screen if screen in SCREENS else "cockpit"
        self.keys = dict(KEYS)  # a replay says its own
        self.refusal = "there is no repository here to act on"  # what a verb says when it cannot act
        self.cursor = 0  # the territory's folder cursor
        self.tell_open, self.tell_for = False, ""
        self.paint_mode = False
        self.shown: tuple = ()  # the screen, row and folder the canvas was last scrolled to
        self.flow_layout: F.Layout | None = None
        self.groups: list[T.Group] = []

    def compose(self) -> ComposeResult:
        yield Static(id="bar")
        with ScrollableContainer():
            yield Canvas()
        yield Static(id="feed")
        yield Input(placeholder="tell the agent one line, Enter sends, Esc cancels", id="tell")
        yield Static(id="keys")

    def on_mount(self) -> None:
        self.query_one(ScrollableContainer).can_focus = False  # the wheel scrolls it; the keys are the app's
        self.set_interval(self.every, self.look)
        self.set_interval(0.5, self.terminal_gone)
        self.paint()

    def terminal_gone(self) -> None:
        """A terminal that closed without the hangup ends the screen as `q` does (``P.terminal_closed``):
        Textual would read its end of file as no key, again and again, at full speed, forever."""
        if not self.is_headless and P.terminal_closed():
            self.exit()

    # -- looking and painting --------------------------------------------------------------------

    def look(self) -> None:
        """Ask for the model as it is now, and draw it. A tick that lands once the app has begun to shut
        down draws nothing: its widgets are being removed, and `#bar` was not found (a loaded runner)."""
        if not self.is_running:
            return
        self.model = self.looker(self.model)
        self.paint()

    def width(self) -> int:
        return max(self.size.width, 40)

    def paint(self) -> None:
        m, w = self.model, self.width()
        if self.tell_open and m.selected != self.tell_for:  # a click moved on: the line was for the other row
            self.close_tell()
        tabs = "  ".join(
            f"[{'b' if s == self.view else 'dim'}]{k} {s}[/]" for k, s in zip("cgm", SCREENS, strict=True)
        )
        bar = Text.from_markup(" " + tabs.replace("[b]", "[bold #4cc9f0]").replace("[dim]", "[grey50]"))
        name = self.root.name if self.root else ""
        name += f" · plan first {m.first}" if m.first else ""
        if bar.cell_len + len(name) + 3 > w:  # narrow: just whose plan this is, cut, or nothing
            name = name.split(" · ")[0][: max(w - bar.cell_len - 3, 0)]
        bar.append(" " * max(2, w - bar.cell_len - len(name) - 1) + name, style="grey42")  # whose plan
        self.query_one("#bar", Static).update(bar)
        if self.view == "cockpit":
            lines = build_cockpit(m, w, tell=self.query_one("#tell", Input).value if self.tell_open else None)
        elif self.view == "territory":
            lines, self.groups = build_territory(m, w, self.cursor)
        else:
            lines = self.flow_lines(w)
        self.query_one(Canvas).set_lines(lines)
        at = (self.view, m.selected, self.cursor if self.view == "territory" else 0)
        if at != self.shown:  # follow the selection when it moves, not on every tick
            self.shown = at
            self.call_after_refresh(self.follow, lines)
        feed = m.latest()
        note = Text()
        note.append(" " + (feed or LEGEND), style="bold #e9c46a" if feed else "grey42")
        note.truncate(w, overflow="ellipsis")  # a long line ends in …, not mid-word
        self.query_one("#feed", Static).update(note)
        painting = "paint mode: click or Enter on folders · p to stop · " if self.paint_mode else ""
        keys = painting + self.keys[self.view]
        self.query_one("#keys", Static).update(" " + fit_keys(keys, w - 1))

    def flow_lines(self, width: int) -> list[Line]:
        m = self.model
        nodes, edges = FV.flow_graph(m)
        lines, self.flow_layout, note = FV.build_flow(nodes, edges, width, m.selected)
        sel = m.tasks.get(m.selected)
        info = f" {sel.title}" if sel else ""
        if sel:
            info += f"  ·  {sel.state}" + (f" · {who(sel.agent)}" if sel.agent else "")
            info += f" · proof {sel.passed}/{sel.checks}" if sel.checks else ""
            info += f" · for {sel.why}" if sel.why else ""
        lines += [
            Line([]),
            Line([Seg(info, "bold")]),
            Line([Seg(" " + note if note else "", "grey50")]),
            Line([Seg(" amber lane = a retry loop (bounded) · ◀▶ two-way", "grey50")]),
        ]
        return lines

    def follow(self, lines: list[Line]) -> None:
        """Scroll so what is selected is on screen: a task's row, all its lines; the box on the graph; the
        folder under the cursor on the map."""
        box = self.query_one(ScrollableContainer)
        if self.view == "flow":
            rect = self.flow_layout.rects.get(self.model.selected) if self.flow_layout else None
            if rect:
                box.scroll_to_region(Region(0, rect[1], 1, rect[3] - rect[1] + 1), animate=False)
            return
        if self.view == "territory":
            box.scroll_to_region(Region(0, HEAD + self.cursor, 1, 1), animate=False)
            return
        at = [k for k, line in enumerate(lines) if line.row and line.row == self.model.selected]
        if at:
            box.scroll_to_region(Region(0, at[0], 1, at[-1] - at[0] + 1), animate=False)

    # -- moves -----------------------------------------------------------------------------------

    def rows(self) -> list[str]:
        return [rid for _, rid in self.model.order()]

    def move(self, key: str) -> None:
        m = self.model
        m.moved = True  # from here the selection is the person's
        down = key in ("j", "down", "right", "l")
        if self.view == "territory":
            if key in ("j", "down", "k", "up"):
                self.cursor = (self.cursor + (1 if key in ("j", "down") else -1)) % max(len(self.groups), 1)
                return
            tasks = [t.id for t in m.tasks.values() if t.state != "done"] or list(m.tasks)
            if m.selected in tasks:
                m.selected = tasks[(tasks.index(m.selected) + (1 if down else -1)) % len(tasks)]
            elif tasks:
                m.selected = tasks[0]
            return
        if self.view == "flow" and self.flow_layout:
            m.selected = nearest(self.flow_layout, m.selected, key) or m.selected
            return
        rows = self.rows()
        if rows:
            at = rows.index(m.selected) if m.selected in rows else -1
            m.selected = rows[(at + (1 if down else -1)) % len(rows)]

    def clicked(self, line: Line, seg: Seg | None) -> None:
        m = self.model
        if line.row:
            m.selected, m.moved = line.row, True
        action = seg.action if seg else ""
        if action.startswith("select:"):
            m.selected = action.split(":", 1)[1]
        elif action.startswith("group:"):
            self.cursor = int(action.split(":", 1)[1])
            if self.paint_mode and self.groups and self.doer:
                self.doer.paint(m, m.selected, self.groups[self.cursor].name)
        elif action:
            self.act(action)
        self.paint()

    # -- verbs -------------------------------------------------------------------------------------

    TAKES = ("review", "proposed", "yours", "came back")  # the states a row's Enter acts on

    def takes(self) -> bool:
        m = self.model
        task = m.tasks.get(m.selected)
        return any(q.id == m.selected for q in m.questions) or (task is not None and task.state in self.TAKES)

    def act(self, action: str) -> None:
        """What a key or a click asks for: a verb, run as the command it is."""
        m, sel, d = self.model, self.model.selected, self.doer
        task = m.tasks.get(sel)
        if action == "tell":
            self.open_tell()
        elif action == "direction":
            if self.open_store is None or self.root is None:
                m.say("there is no repository here to read a direction from")
            else:
                self.push_screen(
                    Details(self.open_store, self.root, "", "the direction", "direction", DIRECTION)
                )
        elif action == "details":
            if task is None or self.open_store is None or self.root is None:
                m.say("select a task to see everything about it")
            else:
                name = " · ".join(x for x in (task.title, who(task.agent)) if x)
                self.push_screen(Details(self.open_store, self.root, sel, name))
        elif d is None:
            m.say(self.refusal)
        elif action == "take":
            d.take(m, sel)
        elif action.startswith("pick:"):
            d.pick(m, sel, int(action.split(":", 1)[1]))
        elif action == "allow":
            d.widen(m, sel)
        elif action.startswith("offer:"):
            d.offer(m, sel, action.split(":", 1)[1])
        elif action == "back":
            if task is not None and task.state in ("review", "done"):
                about = " · ".join(x for x in (task.title, who(task.agent)) if x)
                ask = Ask(f"reopen {sel}: what is wrong? its next executor is told", about=about)
                m.moved = True  # opening it is choosing the row: the selection stays here until you move
                self.push_screen(ask, partial(self.reopened, sel))
            else:
                d.pull_back(m, sel)
        elif action == "drop":
            d.drop(m, sel)
        elif action == "run":
            if task is None:
                m.say("select a task to run: r runs the one under the cursor, R every ready leaf")
            elif "r" in task.offers:
                d.offer(m, sel, "r")
            else:
                d.run_ready(sel)
        elif action == "run-all":
            self.run_all()
        elif action == "answer":
            q = next((q for q in m.questions if q.id == sel), None)
            if q is None:
                m.say("a answers a question in your own words: select one")
            else:
                m.moved = True
                ask = Ask(f"answer {q.id} in your own words", about=q.text)
                self.push_screen(ask, partial(self.answered, q.id))
        elif action == "split":
            d.split(m, sel)
        elif action == "first":
            d.plan_first(m)
        elif action == "undo":
            d.undo()
        elif action in ("edit", "edit-plan"):
            self.edit_with(["node", "edit", sel] if action == "edit" and task else ["plan", "edit"])
        elif action == "command":
            self.push_screen(Ask("graphene "), self.commanded)
        self.paint()

    def commanded(self, text: str | None) -> None:
        """The line typed after `:`. `ask` alone is a paragraph, written in your editor, not on one line."""
        if not text or self.doer is None:
            return
        words = text.strip().removeprefix("graphene ").strip()
        if words == "ask":
            self.ask_in_editor()
        elif re.match(r"(plan|node)\s+edit(\s|$)", words):  # an editor needs the terminal: this steps aside
            self.edit_with(shlex.split(words))
        else:
            self.doer.command(text)
        self.paint()

    def ask_in_editor(self) -> None:
        """Your editor opens on a file with one line of guidance, and what you write there is the ask: a
        paragraph does not fit a one-line prompt, and the first ask is the one most worth a paragraph."""
        from textual.app import SuspendNotSupported

        path = PT.edit_path(self.root, "ask")
        path.write_text(ASK_HINT, encoding="utf-8")
        try:
            try:
                with self.suspend():
                    PT.run_editor(path)
            except SuspendNotSupported:  # no terminal to hand over (a test): the editor runs without one
                PT.run_editor(path)
        except P.Refused as no:
            self.model.say(f"✗ {no}")
            return
        lines = [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines()]
        text = "\n".join(ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")).strip()
        if text:
            self.doer.background(["ask", text])
        else:
            self.model.say("nothing asked: the file had no line of yours (:ask what you want asks in a line)")

    def run_all(self) -> None:
        """R: every ready leaf. A run that could start more than one (each an executor that spends) asks
        first; one leaf starts at once, and so does a run when no executor is chosen (it says so)."""
        m, d = self.model, self.doer
        could = [(n, w) for w in ("ready", "waiting") if (n := sum(t.state == w for t in m.tasks.values()))]
        total = sum(n for n, _ in could)
        if total <= 1 or not m.executor:
            d.run_ready()
            return
        which = ", ".join(f"{n} {w}" for n, w in could)
        said = f"run up to {total} leaves ({which}), at most 4 at once with {m.executor}"
        said += "? y and Enter start them"

        def answered(typed: str | None) -> None:
            if (typed or "").lower() in ("y", "yes"):
                d.run_ready()

        self.push_screen(Ask(said), answered)

    def edit_with(self, argv: list[str]) -> None:
        """e and E: the node's contract, or the plan's text, in your $EDITOR: the screen steps aside."""
        from textual.app import SuspendNotSupported

        try:
            with self.suspend():
                self.doer.run(argv)
        except SuspendNotSupported:  # no terminal to hand over (a test): the editor runs without one
            self.doer.run(argv)

    def answered(self, qid: str, words: str | None) -> None:
        if words and self.doer:
            self.doer.answer(self.model, qid, words)
        self.paint()

    def reopened(self, node_id: str, note: str | None) -> None:
        if note and self.doer:
            self.doer.reopen(self.model, node_id, note)
        self.paint()

    # -- tell --------------------------------------------------------------------------------------

    def open_tell(self) -> None:
        t = self.model.tasks.get(self.model.selected)
        if t is None:
            self.model.say("select a task to tell")
            return
        if self.doer is None:
            self.model.say(self.refusal)
            return
        box = self.query_one("#tell", Input)
        box.add_class("on")
        box.value = ""
        box.focus()
        self.tell_open, self.tell_for = True, t.id  # the line is for this task, wherever the selection goes
        self.model.moved = True

    def close_tell(self) -> None:
        self.query_one("#tell", Input).remove_class("on")
        self.tell_open, self.tell_for = False, ""
        self.set_focus(None)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tell" and self.tell_open:
            self.paint()  # the row shows what is typed

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "tell":  # a line typed into a prompt (Ask) is that prompt's, not a tell
            return
        words, sel = event.value, self.tell_for
        self.close_tell()
        if self.doer:
            self.doer.tell(self.model, sel, words)
        self.paint()

    def action_help(self) -> None:
        if not isinstance(self.screen, (Ask, Help)):
            self.push_screen(Help())

    def on_key(self, event) -> None:
        key = event.key
        if isinstance(self.screen, Ask):  # a key queued before the prompt it opened was up: the prompt's
            self.screen.typed(event)
            return
        if isinstance(self.screen, (Help, Details)):  # a screen over this one has its own keys
            return
        if self.tell_open:
            if key == "escape":
                self.close_tell()
                self.paint()
            return
        if key == "q":
            self.exit()
            return
        if key in ("c", "g", "m"):
            self.view = {"c": "cockpit", "g": "flow", "m": "territory"}[key]
        elif key == "tab":
            self.view = SCREENS[(SCREENS.index(self.view) + 1) % len(SCREENS)]
        elif key in ("j", "down", "k", "up", "left", "right", "h", "l"):
            self.move(key)
        elif key == "enter":
            if self.view == "territory" and self.paint_mode and self.groups and self.doer:
                self.doer.paint(self.model, self.model.selected, self.groups[self.cursor].name)
            elif self.takes():
                self.act("take")
            else:
                self.act("details")
        elif key == "v":
            self.model.lens = T.LENSES[(T.LENSES.index(self.model.lens) + 1) % len(T.LENSES)]
        elif key == "p":
            self.paint_mode = not self.paint_mode
            if self.paint_mode:
                self.view = "territory"
        elif key.isdigit() and key != "0":
            self.act(f"pick:{key}")
        elif key in KEYS_TO_VERBS:
            self.act(KEYS_TO_VERBS[key])
        self.paint()

def nearest(lay: F.Layout, current: str, key: str) -> str | None:
    """The node nearest in a direction, by the centres of the boxes."""
    if current not in lay.rects:
        return next(iter(lay.rects), None)
    x0, y0, x1, y1 = lay.rects[current]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = {
        "right": (1, 0), "l": (1, 0), "left": (-1, 0), "h": (-1, 0),
        "down": (0, 1), "j": (0, 1), "up": (0, -1), "k": (0, -1),
    }[key]  # fmt: skip
    best, score = None, 1e9
    for nid, (a, b, c, d) in lay.rects.items():
        if nid == current:
            continue
        ox, oy = (a + c) / 2 - cx, (b + d) / 2 - cy
        along, across = ox * dx + oy * dy, abs(ox * dy) + abs(oy * dx)
        if along <= 0:
            continue
        s = along + 2.5 * across
        if s < score:
            best, score = nid, s
    return best
