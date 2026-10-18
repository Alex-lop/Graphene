"""The cockpit app: three screens over one model and one selection, a canvas that scrolls, a line of news.

`Cockpit` is handed a `looker`: a function from the model last shown (or None) to the model now. In the
product it reads the plan's store (read.py); a test hands it a model it built. Everything on the canvas is
lines (lines.py) painted and turned back into actions when clicked, so the words on a row are its buttons.
The screens: cockpit (c), flow (g), territory (m). The keys are the verbs; a verb is a command that
exists on its own (verbs.py), and the line at the bottom says what the last one did.
"""

from __future__ import annotations

from collections.abc import Callable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer
from textual.events import Click
from textual.geometry import Region
from textual.widget import Widget
from textual.widgets import Input, Static

from . import flow_view as FV
from . import flowlayout as F
from . import territory as T
from .lines import Line, Seg, seg_at
from .model import Model
from .rows import build_cockpit
from .territory_view import build_territory

SCREENS = ("cockpit", "flow", "territory")
KEYS = {
    "cockpit": "j/k move · ⏎ take · t tell · w allow · x pull back · g graph · m map · q quit",
    "flow": "arrows move · ⏎ take · t tell · w allow · c cockpit · m map · q quit",
    "territory": "j/k folder · ←/→ task · p paint · v lens · a allow · c cockpit · g graph · q quit",
}
LEGEND = "✎ files touched of allowed · ✓ proofs · ! writes stopped · ⏸ quiet · ▁▃▅ activity"


class Canvas(Widget):
    """Paints lines of segments and turns a click on a segment into that segment's action."""

    DEFAULT_CSS = "Canvas { height: auto; width: auto; }"

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
    AUTO_FOCUS = None  # the hidden tell box must not take the keys
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #0e1014; }
    #bar { height: 1; background: #181b22; color: #9aa0ad; }
    #feed { height: 1; }
    #keys { height: 1; background: #181b22; color: #7d8492; }
    #tell { display: none; height: 3; }
    #tell.on { display: block; }
    """

    def __init__(
        self, looker: Callable[[Model | None], Model], every: float = 1.0, screen: str = "cockpit"
    ) -> None:
        super().__init__()
        self.looker, self.every = looker, every
        self.model = looker(None)
        self.view = screen if screen in SCREENS else "cockpit"
        self.cursor = 0  # the territory's folder cursor
        self.tell_open = False
        self.paint_mode = False
        self.shown = ""  # the row the screen was last scrolled to
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
        self.set_interval(self.every, self.look)
        self.paint()

    # -- looking and painting --------------------------------------------------------------------

    def look(self) -> None:
        """Ask for the model as it is now, and draw it."""
        self.model = self.looker(self.model)
        self.paint()

    def width(self) -> int:
        return max(self.size.width, 40)

    def paint(self) -> None:
        m, w = self.model, self.width()
        tabs = "  ".join(
            f"[{'b' if s == self.view else 'dim'}]{k} {s}[/]" for k, s in zip("cgm", SCREENS, strict=True)
        )
        self.query_one("#bar", Static).update(
            Text.from_markup(" " + tabs.replace("[b]", "[bold #4cc9f0]").replace("[dim]", "[grey50]"))
        )
        if self.view == "cockpit":
            lines = build_cockpit(m, w, tell="" if self.tell_open else None)
        elif self.view == "territory":
            lines, self.groups = build_territory(m, w, self.cursor)
        else:
            lines = self.flow_lines(w)
        self.query_one(Canvas).set_lines(lines)
        if m.selected != self.shown:  # follow the selection when it moves, not on every tick
            self.shown = m.selected
            self.call_after_refresh(self.follow, lines)
        feed = m.latest()
        note = Text()
        note.append(" " + (feed or LEGEND), style="bold #e9c46a" if feed else "grey42")
        self.query_one("#feed", Static).update(note)
        self.query_one("#keys", Static).update(
            " "
            + ("paint mode: click or Enter on folders · p to stop · " if self.paint_mode else "")
            + KEYS[self.view]
        )

    def flow_lines(self, width: int) -> list[Line]:
        m = self.model
        nodes, edges = FV.flow_graph(m)
        lines, self.flow_layout, note = FV.build_flow(nodes, edges, width, m.selected)
        sel = m.tasks.get(m.selected)
        info = f" {sel.title}" if sel else ""
        if sel:
            info += f"  ·  {sel.state}" + (f" · {sel.agent}" if sel.agent else "")
            info += f" · proof {sel.passed}/{sel.checks}"
        lines += [
            Line([]),
            Line([Seg(info, "bold")]),
            Line([Seg(" " + note if note else "", "grey50")]),
            Line([Seg(" amber lane = a retry loop (bounded) · ◀▶ two-way", "grey50")]),
        ]
        return lines

    def follow(self, lines: list[Line]) -> None:
        """Scroll so the selected row, all its lines, is on screen."""
        at = [k for k, line in enumerate(lines) if line.row and line.row == self.model.selected]
        if at:
            region = Region(0, at[0], 1, at[-1] - at[0] + 1)
            self.query_one(ScrollableContainer).scroll_to_region(region, animate=False)

    # -- moves -----------------------------------------------------------------------------------

    def rows(self) -> list[str]:
        return [rid for _, rid in self.model.order()]

    def move(self, key: str) -> None:
        m = self.model
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
            m.selected = line.row
        action = seg.action if seg else ""
        if action.startswith("select:"):
            m.selected = action.split(":", 1)[1]
        elif action.startswith("group:"):
            self.cursor = int(action.split(":", 1)[1])
        self.paint()

    def on_key(self, event) -> None:
        key = event.key
        if key == "q":
            self.exit()
            return
        if key in ("c", "g", "m"):
            self.view = {"c": "cockpit", "g": "flow", "m": "territory"}[key]
        elif key == "tab":
            self.view = SCREENS[(SCREENS.index(self.view) + 1) % len(SCREENS)]
        elif key in ("j", "down", "k", "up", "left", "right", "h", "l"):
            self.move(key)
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
