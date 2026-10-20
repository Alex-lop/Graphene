"""The cockpit app: three screens over one model and one selection, a canvas that scrolls, a line of news.

`Cockpit` is handed a `looker`: a function from the model last shown (or None) to the model now. In the
product it reads the plan's store (read.py); a test hands it a model it built. Everything on the canvas is
lines (lines.py) painted and turned back into actions when clicked, so the words on a row are its buttons.
The screens: cockpit (c), graph (g), map (m). The keys are the verbs; a verb is a command that exists
on its own (verbs.py), and the line at the bottom says what the last one did.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from functools import partial
from pathlib import Path

from rich.cells import cell_len
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
from .. import run as R
from .. import settings as S
from ..tui import ASK_HINT, Ask
from . import flow_view as FV
from . import flowlayout as F
from . import territory as T
from .details import DIRECTION, Details
from .help import Help
from .lines import Line, Seg, fit, fit_keys, seg_at
from .look import short, who
from .model import Model
from .rows import build_cockpit, build_head, offered, tag_of
from .territory_view import HEAD, build_territory
from .verbs import Doer

SCREENS = ("cockpit", "flow", "territory")
TABS = ("cockpit", "graph", "map")  # what the top line calls them
KEYS = {  # one line each, at most 79 columns: the screen's own keys, then the ones every screen has
    "cockpit": "",  # empty: what the keys do to the selected row (row_keys)
    "flow": "",
    "territory": "j/k folder · ←/→ task · p paint · v lens · w widen · c cockpit · ? keys · q",
}
# the map draws folders, not rows: only its bar's keys act there (and t, whose line is typed under the task's
# row, in the cockpit); ⏎ paints in paint mode, and every other key says where it acts
ON_THE_MAP = "only the keys below act on the map: c goes back to the cockpit for the rest"
UNSENT = "nothing typed here is sent · Esc closes"  # t that nobody hears: words go nowhere, not to keys
ROW_KEYS = {  # a task's own keys, by its state: ⏎ first when it has a move, then the letters
    "proposed": ["⏎ accept", "A all", "d drop", "i details"],
    "came back": ["⏎ try again", "f fork", "w widen", "b new task", "n wait", "r reopen", "t tell",
                  "i details"],  # fmt: skip
    "review": ["⏎ sign off", "x reopen", "i details"],
    "yours": ["⏎ mark done", "i details"],
    "running": ["t tell", "w widen", "x hand back", "i details"],
    "ready": ["r run", "f fork", "R run ready", "t tell", "i details"],
    "waiting": ["t tell", "i details"],
    "done": ["i details", "x reopen"],
}
OFFERED = ("w widen", "b new task", "n wait", "r reopen")  # a task that came back offers these, by its offers
KEYS_TO_VERBS = {  # a key, and the verb it asks for (`act`)
    "t": "tell", "w": "allow", "x": "back", "d": "drop", "r": "run", "R": "run-all", "a": "answer",
    "b": "offer:b", "n": "offer:n", "colon": "command", "y": "take", "s": "split", "P": "first", "u": "undo",
    "e": "edit", "E": "edit-plan", "D": "direction", "i": "details", "A": "accept-all", "f": "fork",
}  # fmt: skip


def needs(m: Model) -> dict[str, str]:
    """What needs the person now that the terminal should say, each with the line it says: a question, a
    task that came back, one that waits for a sign-off, a write the gate stopped. Keyed so that each is
    said once (a task that comes back again, or is stopped again, in a new attempt, is a new one). Proposals
    are not here: they ring once a batch (``proposals``), when nothing here comes with them."""
    out = {f"q:{q.id}": f"{'a risk' if q.kind == 'risk' else 'a question'}: {q.text}" for q in m.questions}
    for t in m.tasks.values():
        title = fit(t.title, 40)  # a whole title is cut here, so the line keeps what happened
        name = who(t.agent) or title
        if t.state == "came back":
            out[f"back:{t.id}:{t.started}"] = f"{name} came back" + (f": {t.note}" if t.note else "")
        elif t.state == "review":
            out[f"review:{t.id}:{t.started}"] = f"{title} passed its check and waits for your sign-off"
        for path, _when in t.stopped if t.state == "running" else []:
            out[f"stop:{t.id}:{t.started}:{path}"] = f"{name} was stopped writing {path}: w widens it"
    return out


def proposals(m: Model) -> set[str]:
    """The tasks proposed now, keyed apart from `needs`: a batch of new ones rings once ("3 tasks proposed")
    when no question came with them (a planner's questions do; a Claude Code `plan propose` brings none)."""
    return {f"proposed:{t.id}" for t in m.tasks.values() if t.state == "proposed"}


def text_of(lines: list[Line]) -> Text:
    """Lines as one Text, each cut at the screen's edge, never wrapped."""
    out = Text(no_wrap=True, overflow="crop")
    for k, line in enumerate(lines):
        for s in line.segs:
            out.append(s.text, style=s.style or None)
        if k < len(lines) - 1:
            out.append("\n")
    return out


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
        return text_of(self.lines)

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
    #head { height: auto; text-wrap: nowrap; text-overflow: clip; }  /* a wrapped head moves every row */
    ScrollableContainer { scrollbar-size-vertical: 1; scrollbar-background: #0e1014; scrollbar-color: #2b3242;
                          scrollbar-color-hover: #3a4357; scrollbar-color-active: #4cc9f0; }
    #feed { height: 1; }
    #keys { height: 1; background: #181b22; color: #7d8492; }
    #tell { display: none; height: 0; border: none; padding: 0; }  /* it takes the keys; its row shows it */
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
        self.replay = False  # a recording played back (replay.py): nothing in it has commits or runs
        self.cursor = 0  # the territory's folder cursor
        self.tell_open, self.tell_for = False, ""
        self.paint_mode = False
        self.shown: tuple = ()  # the screen, row and folder the canvas was last scrolled to
        self.flow_layout: F.Layout | None = None
        self.groups: list[T.Group] = []
        self.told = set(needs(self.model)) | proposals(self.model)  # what needed you on opening: seen, unrung
        self.writer: Callable[[str], None] | None = None  # where the bell goes; None: this terminal

    def compose(self) -> ComposeResult:
        yield Static(id="bar")
        yield Static(id="head")  # the goal and the counts: they stay while the rows scroll
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
        self.ring()
        self.paint()

    def ring(self) -> None:
        """When something new needs you, the terminal says so: its bell, and a desktop notification with the
        reason in one line (OSC 9), once for each (``needs``). Never in a replay, nor with `notify: off`,
        nor with no terminal to say it in (a test's, unless it hands a writer)."""
        now = needs(self.model)
        new = [said for key, said in now.items() if key not in self.told]
        offered = proposals(self.model) - self.told
        self.told |= set(now) | offered
        if offered and not new:  # the batch, once; with a question, the question says it
            new = [f"{len(offered)} task{'s' * (len(offered) > 1)} proposed"]
        write = self.writer or (self._driver.write if self._driver and not self.is_headless else None)
        if not new or write is None or self.model.source == "replay" or self.quiet():
            return
        said = new[0] + (f" (and {len(new) - 1} more)" if len(new) > 1 else "")
        said = "".join(ch for ch in " ".join(said.split()) if ch.isprintable())  # no escape of its own
        write(f"\a\x1b]9;graphene: {fit(said, 200)}\a")

    def quiet(self) -> bool:
        """`notify: off` in graphene config. A store that does not open now says nothing to the contrary."""
        if self.open_store is None:
            return False
        try:
            with self.open_store() as store:
                return S.notify(store) == "off"
        except Exception:  # the screen stays up whatever the store says; the bell is not worth a crash
            return False

    def width(self) -> int:
        return max(self.size.width, 40)

    def paint(self) -> None:
        m, w = self.model, self.width()
        if self.tell_open and m.selected != self.tell_for:  # a click moved on: the line was for the other row
            self.close_tell()
        shown = zip("cgm", SCREENS, TABS, strict=True)
        tabs = "  ".join(f"[{'b' if s == self.view else 'dim'}]{k} {tab}[/]" for k, s, tab in shown)
        bar = Text.from_markup(" " + tabs.replace("[b]", "[bold #4cc9f0]").replace("[dim]", "[grey50]"))
        name = self.root.name if self.root else ""
        name += " · plan first off" if m.first == "off" else ""  # said only when agents may write unplanned
        if m.source == "replay" and self.view != "cockpit":  # what it is, on every screen (the cockpit's head
            name = tag_of(m, w - bar.cell_len - 3)  # says it there)
        if bar.cell_len + len(name) + 3 > w:  # narrow: just whose plan this is, cut, or nothing
            name = name.split(" · ")[0][: max(w - bar.cell_len - 3, 0)]
        bar.append(" " * max(2, w - bar.cell_len - len(name) - 1) + name, style="grey42")  # whose plan
        self.query_one("#bar", Static).update(bar)
        top: list[Line] = []  # what stays on top while the canvas under it scrolls
        if self.view == "cockpit":
            top = build_head(m, w)
            lines = build_cockpit(m, w, tell=self.query_one("#tell", Input).value if self.tell_open else None)
        elif self.view == "territory":
            lines, self.groups = build_territory(m, w, self.cursor)
            if self.groups:  # its headline, its lens and the task it lights, over the folders
                top, lines = lines[:HEAD], lines[HEAD:]
        else:
            top, lines = self.flow_lines(w)
        head = self.query_one("#head", Static)
        head.display = bool(top)
        head.update(text_of(top))
        self.query_one(Canvas).set_lines(lines)
        at = (self.view, m.selected, self.cursor if self.view == "territory" else 0)
        if at != self.shown:  # follow the selection when it moves, not on every tick
            self.shown = at
            self.call_after_refresh(self.follow, lines)
        feed = m.latest()
        note = Text()
        note.append(" " + feed if feed else "", style="bold #e9c46a")  # no news: a quiet line (the marks: ?)
        note.truncate(w, overflow="ellipsis")  # a long line ends in …, not mid-word
        self.query_one("#feed", Static).update(note)
        painting = "paint mode: click or Enter on folders · p to stop · " if self.paint_mode else ""
        keys = painting + (self.keys[self.view] or self.row_keys())
        self.query_one("#keys", Static).update(" " + fit_keys(keys, w - 1))

    def row_keys(self) -> str:
        """The keys line for what is selected: what ⏎ and each letter do to it, then the other screens.
        While the tell box has the keys, what Enter and Esc do there."""
        m = self.model
        if self.tell_open:
            t = m.tasks.get(self.tell_for)
            return f"Enter sends to {who(t.agent) if t and t.agent else 'its agent'} · Esc cancels"
        if self.screen_stack and isinstance(self.screen_stack[-1], Ask):  # a prompt has the keys
            unsent = self.screen_stack[-1].prompt == UNSENT
            return "nothing is sent · Esc or Enter closes" if unsent else "Enter sends · Esc cancels"
        q = next((q for q in m.questions if q.id == m.selected), None)
        t = m.tasks.get(m.selected)
        if m.source == "replay":  # a recording: what it shows can be read, nothing in it is yours to act on
            own = ["i details"]
        elif q:
            picks = {0: [], 1: ["1 pick"], 2: ["1 2 pick"]}.get(len(q.options), [f"1-{len(q.options)} pick"])
            own = [f"⏎ {fit(q.default, 12)}", *picks, "a answer", "d drop"]
        elif t:  # an offer's key only where it is offered; w also where the gate stopped a write
            own = [k for k in ROW_KEYS.get(t.state, ["i details"])
                   if k not in OFFERED or k[0] in t.offers or k == "w widen" and t.stopped]  # fmt: skip
            if t.state == "review" and t.forks:  # its hold forked: a digit picks another fork's work
                own.insert(-1, f"1-{len(t.forks)} pick")
        else:
            own = [":ask what you want"]
        screens = ["c cockpit", "m map"] if self.view == "flow" else ["g graph", "m map"]
        return " · ".join([*own, *screens, "? keys", "q"])

    def flow_lines(self, width: int) -> tuple[list[Line], list[Line]]:
        """The graph's head, which stays on top: what is selected, in one line (a question has no box, so what
        it asks); then the graph, and under it what it leaves out and what its marks mean."""
        m = self.model
        nodes, edges = FV.flow_graph(m)
        # one column kept for the scrollbar a tall graph shows, so a box at the right edge keeps its border
        lines, self.flow_layout, note = FV.build_flow(nodes, edges, width - 1, m.selected)
        if not nodes:  # the graph's own sentence says what it will show (flow_view.EMPTY)
            return [], lines
        sel = m.tasks.get(m.selected)
        whole = lambda t: short(t.full, 0) or t.title  # noqa: E731  (the line has the room a box has not)
        title = whole(sel) if sel else ""
        q = next((q for q in m.questions if q.id == m.selected), None)
        if q:  # a question has no box: what it asks, and the task it is about
            about = m.tasks.get(q.about)
            title = f"{'!' if q.kind == 'risk' else '?'} {q.text}"
            title += f"  ·  about {whole(about)}" if about else ""
        bits = [sel.state, who(sel.agent), f"✓{sel.passed}/{sel.checks}" if sel.checks else ""] if sel else []
        rest = "  ·  " + " · ".join(b for b in bits if b) if sel else ""
        info = fit(title, max(width - 2 - cell_len(rest), 12)) + rest  # a long title is cut, never its state
        if sel and sel.why and cell_len(info) + cell_len(sel.why) + 7 <= width - 2:
            info += f" · for {sel.why}"
        top = [Line([Seg(" " + fit(info, width - 2), "bold")]), Line([Seg("─" * width, "grey30")])]
        drawn = [cell for row in self.flow_layout.cells for cell in row]
        legend = [said for said, there in (  # what the graph's own marks mean, only those it drew
            ("amber lane = a retry loop (bounded)", any(style == "edge_loop" for _, style in drawn)),
            ("◀▶ two-way", any(ch == "◀" for ch, _ in drawn)),
        ) if there]  # fmt: skip
        under = [Line([Seg(" " + said, "grey50")]) for said in (note, " · ".join(legend)) if said]
        return top, lines + ([Line([]), *under] if under else [])

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
            box.scroll_to_region(Region(0, self.cursor, 1, 1), animate=False)  # its head is on top, apart
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
            q = next((q for q in m.questions if q.id == sel), None)
            node = q.about if q else sel  # a question's details are those of the task it is about
            if q and not q.about:
                n = len(q.options)  # the numbers that pick one, as its key bar has them
                keys = "" if not n else "1 picks its option, " if n == 1 else f"1-{n} pick an option, "
                m.say(f"it is about the whole plan: ⏎ takes its default, {keys}a answers in your own words")
            elif not (node in m.tasks or q) or self.open_store is None or self.root is None:
                m.say("select a task to see its details")
            else:
                t = m.tasks.get(node)
                name = " · ".join(x for x in (t.title if t else node, who(t.agent) if t else "") if x)
                self.push_screen(Details(self.open_store, self.root, node, name, replay=self.replay))
        elif d is None:
            m.say(self.refusal)
        elif action == "take":
            proposed = [t.id for t in m.tasks.values() if t.state == "proposed"]
            if m.questions and proposed == [sel]:  # the last one takes the questions' defaults: it asks, as A
                self.accept_all(sel)
            else:
                d.take(m, sel)
        elif action.startswith("pick:"):
            d.pick(m, sel, int(action.split(":", 1)[1]))
        elif action == "allow":
            d.widen(m, sel)
        elif action.startswith("paint:"):
            d.paint(m, sel, action.split(":", 1)[1])
        elif action in ("run", "offer:r") and task is not None and "r" in task.offers:
            self.reopen_offered(task)
        elif action.startswith("offer:"):
            d.offer(m, sel, action.split(":", 1)[1])
        elif action == "back":
            if task is not None and task.state in ("review", "done"):
                about = " · ".join(x for x in ("reopen " + task.title, who(task.agent)) if x)
                ask = Ask("what is wrong? the agent that takes it next is told", about=about)
                m.moved = True  # opening it is choosing the row: the selection stays here until you move
                self.push_screen(ask, partial(self.reopened, sel))
            elif task is not None and task.state == "running":  # its agent stops: asked first, as R is
                whose = who(task.agent) or "its agent"
                said = f"hand {whose}'s task back? it stops · y and Enter"
                ask = Ask(said, about=task.title)
                self.push_screen(ask, partial(self.handed_back, sel))
            else:
                d.pull_back(m, sel)
        elif action == "drop":
            d.drop(m, sel)
        elif action == "run":
            if task is None:
                m.say("select a task to run: r runs the one under the cursor, R every ready task")
            else:
                d.run_ready(sel)
        elif action == "run-all":
            self.run_all()
        elif action == "fork":
            d.fork(m, sel)
        elif action == "accept-all":
            self.accept_all()
        elif action == "answer":
            q = next((q for q in m.questions if q.id == sel), None)
            if q is None:
                m.say("a answers a question in your own words: select one")
            else:
                m.moved = True
                ask = Ask("your answer, in your own words", about=q.text)
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
            self.push_screen(Ask("a graphene command: ask …, run, plan accept, stop"), self.commanded)
        self.paint()

    def commanded(self, text: str | None) -> None:
        """The line typed after `:`. `ask` alone is a paragraph, written in your editor, not on one line."""
        if not text or self.doer is None:
            self.paint()  # the prompt is gone: the key bar says the row's keys again
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
        """R: every ready task. A run that could start more than one (each an executor that spends) asks
        first; one task starts at once, and so does a run when no executor is chosen (it says so)."""
        m, d = self.model, self.doer
        could = [(n, w) for w in ("ready", "waiting") if (n := sum(t.state == w for t in m.tasks.values()))]
        total = sum(n for n, _ in could)
        if total <= 1 or not m.executor:
            d.run_ready()
            return
        which = ", ".join(f"{n} {w}" for n, w in could)
        going = self.root is not None and R.run_holding(self.root) is not None  # it takes them, with room
        said = f"run up to {total} tasks ({which}), at most 4 at once with {m.executor}"
        said += "? y and Enter start them"
        if going:
            said = f"hand up to {total} tasks ({which}) to the run going here? y and Enter"

        def answered(typed: str | None) -> None:
            if (typed or "").lower() in ("y", "yes"):
                d.run_ready()
            self.paint()

        self.push_screen(Ask(said), answered)

    def accept_all(self, *ids: str) -> None:
        """A: every proposal, as `graphene plan accept` takes them, once a line has said how many (and that
        the questions still open then take their defaults, as they do when the whole plan is accepted). ⏎ on
        the last one names it (``ids``): one an agent proposes while the line is up is not accepted unread."""
        m, d = self.model, self.doer
        n = sum(t.state == "proposed" for t in m.tasks.values())
        if not n:
            m.say("nothing to accept: no task is proposed")
            return
        said = f"accept {n} proposed task{'s' * (n > 1)}"
        if m.questions:
            said += f" and the defaults of {len(m.questions)} question{'s' * (len(m.questions) > 1)}"
        said += "? y and Enter"

        def answered(typed: str | None) -> None:
            if (typed or "").lower() in ("y", "yes"):
                d.run(["plan", "accept", *ids])
            self.paint()

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

    def reopen_offered(self, task) -> None:
        """r on a task that came back reopens the finished task that has the paths it wanted, which it then
        waits on: asked first, as x reopen is, since a task that was proven goes back to work."""
        names = offered(self.model, task, "r")
        said = f"reopen {fit(names, 22)}? its next agent is told why · y and Enter"
        self.push_screen(Ask(said, about=f"reopen {names}"), partial(self.took_offer, task.id, "r"))

    def took_offer(self, node_id: str, key: str, typed: str | None) -> None:
        if (typed or "").strip().lower() in ("y", "yes") and self.doer:
            self.doer.offer(self.model, node_id, key)
        self.paint()

    def handed_back(self, node_id: str, typed: str | None) -> None:
        if (typed or "").strip().lower() in ("y", "yes") and self.doer:
            self.doer.pull_back(self.model, node_id)
        self.paint()

    def reopened(self, node_id: str, note: str | None) -> None:
        if note and self.doer:
            self.doer.reopen(self.model, node_id, note)
        self.paint()

    # -- tell --------------------------------------------------------------------------------------

    def open_tell(self) -> None:
        t = self.model.tasks.get(self.model.selected)
        if self.doer is None:  # a replay, or no repository: nothing is told, whatever the row
            self.model.say(self.refusal)
            return
        if t is None and any(q.id == self.model.selected for q in self.model.questions):
            self.act("answer")  # a question is told its answer, in your own words
            return
        nobody = {  # no agent is on it, nor still to take it
            "review": "waits for your sign-off: x reopens it, and its next agent is told why",
            "done": "is done: x reopens it, and its next agent is told why",
            "yours": "is yours to do: no agent takes it",
        }.get(t.state if t else "")
        if t is None or nobody:
            said = f"{fit(t.title, 32)} {nobody}" if t else "select a task to tell"
            self.model.say(said)
            # what is typed next was meant as words: a line that sends nothing keeps it from running as keys
            self.push_screen(Ask(UNSENT, about=said), lambda _typed: self.paint())
            return
        box = self.query_one("#tell", Input)
        box.add_class("on")
        box.value = ""
        box.focus()
        self.tell_open, self.tell_for = True, t.id  # the line is for this task, wherever the selection goes
        self.model.moved = True
        self.view, self.paint_mode, self.shown = "cockpit", False, ()  # typed under its row: the row, in view

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
        if key == "escape":  # from the graph or the map, back to the rows (and out of painting)
            self.view, self.paint_mode = "cockpit", False
        elif key in ("c", "g", "m"):
            self.view = {"c": "cockpit", "g": "flow", "m": "territory"}[key]
        elif key == "tab":
            self.view = SCREENS[(SCREENS.index(self.view) + 1) % len(SCREENS)]
        elif key in ("j", "down", "k", "up", "left", "right", "h", "l"):
            self.move(key)
        elif self.view == "territory" and key not in ("v", "p", "w", "t"):  # no row is drawn (ON_THE_MAP)
            if key == "enter" and self.paint_mode and self.groups:
                self.act(f"paint:{self.groups[self.cursor].name}")
            elif key == "enter" or key in KEYS_TO_VERBS or key.isdigit():
                self.model.say(ON_THE_MAP)
        elif key == "enter":
            if self.takes():
                self.act("take")
            else:
                self.act("details")
        elif key == "v":
            self.model.lens = T.LENSES[(T.LENSES.index(self.model.lens) + 1) % len(T.LENSES)]
        elif key == "p" and self.replay:  # a replay's scopes are the recording's: nothing is painted
            self.model.say(self.refusal)
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
