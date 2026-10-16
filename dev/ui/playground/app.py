"""The playground: a cockpit, a flow graph and a territory map over one model, linked by one selection.

    uv run python dev/ui/playground/app.py                   a designed scene, simulated live
    uv run python dev/ui/playground/app.py --repo .          the plan of this repository, read-only
    uv run python dev/ui/playground/app.py --repo . --simulate   ...with its ready tasks pretending to run
    uv run python dev/ui/playground/app.py --graph pasted    the pasted causal-loop graph, in Flow
    uv run python dev/ui/playground/app.py --frame flow --width 100    print one frame and exit

Keys: c cockpit, g graph (flow), m map (territory), Tab next screen, j/k or arrows move, Enter takes the
default / signs off, t tells the selected agent one line, w or a allows the last stopped write, x pulls
an agent back, b big numbers, v lens, p paint a folder, s speed, r restart, q quit. Everything is also
clickable. Nothing here talks to an agent or writes to your repository.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flowlayout as F  # noqa: E402
import views as V  # noqa: E402
from model import Model, demo_model, repo_model  # noqa: E402
from rich.text import Text  # noqa: E402
from textual.app import App, ComposeResult  # noqa: E402
from textual.containers import Vertical  # noqa: E402
from textual.events import Click  # noqa: E402
from textual.widget import Widget  # noqa: E402
from textual.widgets import Input, Static  # noqa: E402

SCREENS = ("cockpit", "flow", "territory")
KEYS = {
    "cockpit": "j/k move · ⏎ take · t tell · w allow · x pull back · b big · g graph · m map · q quit",
    "flow": "arrows move · ⏎ take · t tell · w allow · c cockpit · m map · q quit",
    "territory": "j/k folder · ←/→ task · p paint · v lens · a allow · c cockpit · g graph · q quit",
}


class Canvas(Widget):
    """Paints lines of segments and turns a click on a segment into that segment's action."""

    DEFAULT_CSS = "Canvas { height: 1fr; width: 1fr; }"

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[V.Line] = []

    def set_lines(self, lines: list[V.Line]) -> None:
        self.lines = lines
        self.refresh()

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
            seg = V.seg_at(line, event.x)
            self.app.clicked(line, seg)  # type: ignore[attr-defined]


class Playground(App):
    AUTO_FOCUS = None  # the hidden tell box must not take the keys
    CSS = """
    Screen { background: #0e1014; }
    #bar { height: 1; background: #181b22; color: #9aa0ad; }
    #feed { height: 1; }
    #keys { height: 1; background: #181b22; color: #7d8492; }
    #tell { display: none; height: 3; }
    #tell.on { display: block; }
    """

    def __init__(self, model: Model, screen: str = "cockpit", graph: tuple | None = None) -> None:
        super().__init__()
        self.model = model
        self.view = screen
        self.big = False
        self.tell_open = False
        self.cursor = 0  # the territory's folder cursor
        self.paint_mode = False
        self.fixture = graph  # (nodes, edges) for --graph pasted
        self.flow_layout: F.Layout | None = None
        self.groups: list = []

    def compose(self) -> ComposeResult:
        yield Static(id="bar")
        with Vertical():
            yield Canvas()
        yield Static(id="feed")
        yield Input(placeholder="tell the agent one line, Enter sends, Esc cancels", id="tell")
        yield Static(id="keys")

    def on_mount(self) -> None:
        self.set_interval(0.25, self.tick)
        self.paint()

    # -- painting ----------------------------------------------------------------------------------

    def tick(self) -> None:
        if self.model.source != "pasted":
            self.model.tick(0.25)
        self.paint()

    def width(self) -> int:
        return max(self.size.width, 40)

    def paint(self) -> None:
        m = self.model
        w = self.width()
        tabs = "  ".join(
            f"[{'b' if s == self.view else 'dim'}]{k} {s}[/]" for k, s in zip("cgm", SCREENS, strict=True)
        )
        self.query_one("#bar", Static).update(
            Text.from_markup(" " + tabs.replace("[b]", "[bold #4cc9f0]").replace("[dim]", "[grey50]"))
        )
        lines: list[V.Line]
        if self.view == "cockpit":
            lines = V.build_cockpit(m, w, big_numbers=self.big, tell="" if self.tell_open else None)
        elif self.view == "territory":
            lines, self.groups = V.build_territory(m, w, self.cursor)
        else:
            nodes, edges = self.fixture or V.flow_graph(m)
            lines, self.flow_layout, note = V.build_flow(nodes, edges, w, m.selected)
            sel = next((n for n in nodes if n.id == m.selected), None)
            t = m.tasks.get(m.selected)
            info = f" {sel.label}" if sel else ""
            if t:
                info += (
                    f"  ·  {t.state}"
                    + (f" · {t.agent}" if t.agent else "")
                    + f" · proof {t.passed}/{t.checks}"
                )
            lines += [
                V.Line([]),
                V.Line([V.Seg(info, "bold")]),
                V.Line([V.Seg(" " + note if note else "", "grey50")]),
            ]
            if self.fixture:
                lines.append(
                    V.Line(
                        [
                            V.Seg(
                                " two-way arrows ◀▶ · a loop runs along the bottom and back into its target",
                                "grey50",
                            )
                        ]
                    )
                )
            else:
                lines.append(V.Line([V.Seg(" amber lane = a retry loop (bounded) · ◀▶ two-way", "grey50")]))
        self.query_one(Canvas).set_lines(lines)
        feed = m.latest()
        legend = "✎ files touched of allowed · ✓ proofs · ! writes stopped · ⏸ quiet · ▁▃▅ activity"
        note = Text()
        note.append(" " + (feed or legend), style="bold #e9c46a" if feed else "grey42")
        self.query_one("#feed", Static).update(note)
        self.query_one("#keys", Static).update(
            " "
            + ("paint mode: click or Enter on folders · p to stop · " if self.paint_mode else "")
            + KEYS[self.view]
        )

    # -- moves -------------------------------------------------------------------------------------

    def rows(self) -> list[str]:
        return [rid for _, rid in self.model.order()]

    def select(self, rid: str) -> None:
        self.model.selected = rid
        self.paint()

    def clicked(self, line: V.Line, seg: V.Seg | None) -> None:
        m = self.model
        if line.row:
            m.selected = line.row
        action = seg.action if seg else ""
        if action.startswith("select:"):
            m.selected = action.split(":", 1)[1] if action.split(":", 1)[1] != "None" else m.selected
        elif action.startswith("group:"):
            self.cursor = int(action.split(":", 1)[1])
            if self.paint_mode and self.groups:
                m.paint(m.selected, self.groups[self.cursor].name)
        elif action.startswith("pick:"):
            q = next((q for q in m.questions if q.id == m.selected), None)
            if q:
                q.answer = q.options[int(action.split(":", 1)[1])]
                m.say(f"answered: {q.answer}")
        elif action == "take":
            m.take(m.selected)
        elif action == "tell":
            self.open_tell()
        elif action in ("allow", "back"):
            m.widen(m.selected) if action == "allow" else m.pull_back(m.selected)
        self.paint()

    def open_tell(self) -> None:
        if self.model.selected not in self.model.tasks:
            self.model.say("select an agent to tell")
            return
        box = self.query_one("#tell", Input)
        box.add_class("on")
        box.value = ""
        box.focus()
        self.tell_open = True

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.model.tell(self.model.selected, event.value)
        self.close_tell()

    def close_tell(self) -> None:
        box = self.query_one("#tell", Input)
        box.remove_class("on")
        self.tell_open = False
        self.set_focus(None)
        self.paint()

    def on_key(self, event) -> None:
        key = event.key
        m = self.model
        if self.tell_open:
            if key == "escape":
                self.close_tell()
            return
        if key == "q":
            self.exit()
            return
        if key in ("c", "g", "m"):
            self.view = {"c": "cockpit", "g": "flow", "m": "territory"}[key]
        elif key == "tab":
            self.view = SCREENS[(SCREENS.index(self.view) + 1) % 3]
        elif key == "b":
            self.big = not self.big
        elif key == "v":
            m.lens = T_next(m.lens)
        elif key == "s":
            m.speed = {1.0: 2.0, 2.0: 4.0, 4.0: 1.0}.get(m.speed, 1.0)
            m.say(f"speed x{int(m.speed)}")
        elif key == "r":
            fresh = demo_model() if m.source == "demo" else m
            self.model = fresh
        elif key in ("j", "down", "k", "up", "left", "right", "h", "l"):
            self.move(key)
        elif key in ("enter",):
            if self.view == "territory" and self.paint_mode and self.groups:
                m.paint(m.selected, self.groups[self.cursor].name)
            else:
                m.take(m.selected)
        elif key == "t":
            self.open_tell()
        elif key in ("w", "a"):
            m.widen(m.selected)
        elif key == "x":
            m.pull_back(m.selected)
        elif key == "p":
            self.paint_mode = not self.paint_mode
            if self.paint_mode:
                self.view = "territory"
        elif key.isdigit():
            q = next((q for q in m.questions if q.id == m.selected), None)
            if q and 1 <= int(key) <= len(q.options):
                q.answer = q.options[int(key) - 1]
                m.say(f"answered: {q.answer}")
        self.paint()

    def move(self, key: str) -> None:
        m = self.model
        rows = self.rows()
        if self.view == "territory":
            if key in ("j", "down", "k", "up"):
                n = max(len(self.groups), 1)
                self.cursor = (self.cursor + (1 if key in ("j", "down") else -1)) % n
                return
            tasks = [t.id for t in m.tasks.values() if t.state != "done"] or list(m.tasks)
            if m.selected in tasks:
                m.selected = tasks[
                    (tasks.index(m.selected) + (1 if key in ("right", "l") else -1)) % len(tasks)
                ]
            elif tasks:
                m.selected = tasks[0]
            return
        if (
            self.view == "flow"
            and self.flow_layout
            and key in ("left", "right", "up", "down", "h", "l", "j", "k")
        ):
            m.selected = nearest(self.flow_layout, m.selected, key) or m.selected
            return
        if not rows:
            return
        at = rows.index(m.selected) if m.selected in rows else -1
        m.selected = rows[(at + (1 if key in ("j", "down", "right", "l") else -1)) % len(rows)]


def T_next(lens: str) -> str:
    import territory as T

    return T.LENSES[(T.LENSES.index(lens) + 1) % len(T.LENSES)]


def nearest(lay: F.Layout, current: str, key: str) -> str | None:
    """The node nearest in a direction, by the centres of the boxes."""
    if current not in lay.rects:
        return next(iter(lay.rects), None)
    x0, y0, x1, y1 = lay.rects[current]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = {
        "right": (1, 0),
        "l": (1, 0),
        "left": (-1, 0),
        "h": (-1, 0),
        "down": (0, 1),
        "j": (0, 1),
        "up": (0, -1),
        "k": (0, -1),
    }[key]
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


def frame(model: Model, which: str, width: int, graph: tuple | None = None, steps: int = 0) -> str:
    """One frame as text, for the docs and the check."""
    for _ in range(steps * 4):
        model.tick(0.25)
    if which == "cockpit":
        lines = V.build_cockpit(model, width)
    elif which == "territory":
        lines, _ = V.build_territory(model, width, 0)
    else:
        nodes, edges = graph or V.flow_graph(model)
        lines, _, note = V.build_flow(nodes, edges, width, model.selected)
        lines += [V.Line([V.Seg(note)])] if note else []
    return "\n".join(line.plain().rstrip() for line in lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--repo", nargs="?", const=".", help="read the plan of this repository (default: a designed scene)"
    )
    ap.add_argument(
        "--simulate", action="store_true", help="with --repo: pretend the ready tasks are running"
    )
    ap.add_argument("--graph", choices=["pasted"], help="show a fixture graph in Flow")
    ap.add_argument("--frame", choices=SCREENS, help="print one frame and exit")
    ap.add_argument("--width", type=int, default=100)
    ap.add_argument("--after", type=int, default=25, help="with --frame: simulated seconds first")
    args = ap.parse_args()
    graph = None
    if args.graph == "pasted":
        from fixtures import PASTED_EDGES, PASTED_NODES

        graph = (PASTED_NODES, PASTED_EDGES)
        model = demo_model(simulate=False)
        model.source = "pasted"
        model.tasks, model.questions = {}, []
        model.selected = "ai"
        args.frame = args.frame or None
    elif args.repo:
        root = Path(args.repo).resolve()
        if not (root / ".graphene").exists():
            sys.exit(
                f"no Graphene plan in {root}: run `graphene init` there, or leave out --repo for the scene"
            )
        model = repo_model(root, simulate=args.simulate)
    else:
        model = demo_model()
    if args.frame:
        model.selected = model.selected or "users"
        if args.frame == "flow" and args.graph != "pasted" and "users" in model.tasks:
            model.selected = "users"
        print(frame(model, args.frame, args.width, graph, args.after if model.simulate else 0))
        return
    Playground(model, "flow" if graph else "cockpit", graph).run()


if __name__ == "__main__":
    main()
