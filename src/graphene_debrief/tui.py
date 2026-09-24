"""`graphene watch`: the plan on one screen, with vim keys.

A view over commands and text, never the only way to do anything: every key runs a `graphene`
command that exists on its own (the bottom line says which), editing opens the plan's text in the
person's $EDITOR, and a run or a planner started from here is its own process, which goes on when
this screen is closed. The left pane is the tree, the goal its first row; the right one (below it,
when the terminal is narrow) is the node under the cursor. A row reads the same everywhere (the
tree, the node pane, `graphene plan`): glyph, title cut at a word, id, and the word its state reads
as (`plan.reads`), in the colour of who has the move (`plan.look`). The top line says whose plan
this is in the words every write ends with; the bottom two say what waits on the person, and what
the last key did or what the keys do on the node under the cursor.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shlex
import signal
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static, Tree
from textual.widgets._tree import TOGGLE_STYLE

from . import plan as P
from . import plan_text as T
from . import run as R

RUN_WITH = "--parallel 4"  # `R` and `r`: ready leaves at once, a worktree each, landed here as they pass
WIDE = 110  # columns: from here the node pane sits beside the tree, below it under the tree
PANE = 44  # beside the tree, the node pane keeps at least this many columns
QUIET = 120  # seconds without a sign of life before a running leaf reads "quiet for n min"
WRAP = Console(width=400, color_system=None)  # only for Text.wrap: styled text wrapped at words

HELP = (
    ("move", (
        ("j k", "down, up"), ("gg G", "the goal, the last row"), ("/", "search; n the next match"),
        ("Esc", "ends a search, a selection, a pane"),
    )),
    ("fold", (("za", "fold or unfold here (on the goal: all)"), ("zo zc", "unfold, fold"),
              ("zR zM", "all open, all closed"))),
    ("shape", (
        ("y", "accept a proposal; sign off a leaf in review; your own leaf is done"),
        ("d", "drop"), ("e", "edit its contract in $EDITOR"), ("E", "edit it with what is under it, as text"),
        ("a A", "add a sibling, a child"), ("s", "the planner splits it into leaves"),
        ("u", "undo your last act on the plan"), ("V", "select several, then y or d"),
    )),
    ("run", (
        ("R", "run every ready leaf"), ("r", "run the ready leaves under this one"),
        ("x", "release a running leaf; send back one in review; reopen a done one"),
        ("P", "plan first on or off: a session proposes a tree before any code"),
    )),
    ("see", (("Enter", "the record: who held it, what changed, the check"), ("l", "the executor's output"),
             ("ctrl-d ctrl-u", "scroll the pane"))),
    ("a leaf that came back", (
        ("w", "widen its scope to what it wanted"), ("b", "a sibling leaf for that, which it waits on"),
        ("n", "wait on the leaves its reason names"), ("?", "ask the planner (elsewhere ? is this help)"),
    )),
    (":", (
        (":<command>", "any graphene command, as you would type it (:node show x, :plan log)"),
        (":ask <what>", "the planner proposes it"), (":stop", "stops a run started here"),
        ("q", "quit; a run started here goes on"),
    )),
)  # fmt: skip
HELP_END = (
    "Every key is a graphene command, and the bottom line says which it ran. Two agents work here: "
    "the planner proposes the tree (a session, or :ask), the executors do its leaves (R, r)."
)
EMPTY = (
    "Nothing is planned here yet. Tell your agent what you want, in a paragraph: it proposes the tree "
    "here. Or :ask <what you want>. ? lists the keys."
)
KEYS = {  # the bottom line, when no command has just spoken: what the keys do on this row
    "proposed": ["y accept", "d drop", "e edit", "E edit with what is under it"],
    "review": ["y sign off", "x send back", "Enter record"],
    "running": ["l output", "x release", "Enter record"],
    "done": ["x reopen", "Enter record"],
    "ready": ["R run all ready", "r run this", "e edit"],
    "yours": ["y done", "e edit", "Enter record"],
    "waiting": ["e edit", "d drop", "Enter record"],
    "to fill in": ["s split it (the planner)", "e edit"],
}
OFFERED = {"w": "w widen", "b": "b sibling", "n": "n wait"}


def _cli(argv: list[str]) -> tuple[int, str]:
    """A `graphene` command, run here, as the person at this terminal: its exit code and what it said."""
    import typer.main

    from .cli import build

    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            result = typer.main.get_command(build()).main(argv, prog_name="graphene", standalone_mode=False)
            code = result if isinstance(result, int) else 0
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else 1
        except Exception as error:  # a click usage error, or a bug: said, never a crash of the screen
            code, _ = 2, out.write(f"{type(error).__name__}: {error}")
    return code, out.getvalue().strip()


# -- how a row reads ---------------------------------------------------------------------------------


def row(glyph: str, word: str, title: str, node_id: str, wide: int, ids: int, words: int, bold=False) -> Text:
    """One row: glyph, the title cut at a word, the id (dim) and the state word in its colour, in
    fixed columns so ids line up with ids and words with words, whatever the depth. ``wide`` is
    what the row may take; an id is never cut, the title gives way."""
    colour = P.look(word)[1] if word else ""
    title_w = max(wide - 2 - (2 + ids if ids else 0) - (2 + words), 4)
    if not node_id:  # the goal's row: no id, so its title takes the id's column too
        title_w += 2 + ids if ids else 0
    out = Text()
    out.append(f"{glyph} ", colour)
    out.append(T.elide(title, title_w).ljust(title_w), "bold" if bold else "")
    if ids and node_id:
        out.append(f"  {node_id.ljust(ids)}", "dim")
    out.append(f"  {word.ljust(words)}", colour)
    return out


def hanging(said: str, wide: int) -> Text:
    """What a command printed, as the pane shows it: each line wrapped at words to the pane, its
    continuation indented under it, so a table's rows and a git error read as lines, not a paste."""
    out = []
    for line in said.splitlines():
        lead = len(line) - len(line.lstrip())
        pieces = textwrap.wrap(
            line.strip(), max(wide - lead, 12), subsequent_indent="    ", break_on_hyphens=False
        )
        out += [" " * lead + piece for piece in pieces] or [""]
    return Text("\n".join(out))


def ago(seconds: int | None) -> tuple[str, str]:
    """How long since a running leaf showed a sign of life, and its colour: past two minutes it is
    quiet, which is the executor's colour, not an alarm."""
    if seconds is None:
        return "no sign of it yet", "dim"
    if seconds < 60:
        return f"{seconds} s ago", ""
    if seconds < QUIET:
        return f"{seconds // 60} min ago", ""
    return f"quiet for {seconds // 60} min", P.look("running")[1]


def fit(pieces: list[tuple[str, str]], room: int) -> Text:
    """Pieces joined with " · ", as many as fit, whole: the ones that do not are left off the end."""
    out = Text()
    for text, style in pieces:
        if out.cell_len and out.cell_len + 3 + len(text) > room:
            break
        if out.cell_len:
            out.append(" · ", "dim")
        out.append(text if len(text) <= room else T.elide(text, room), style)
    return out


class Pane:
    """What the node pane says, laid out: aligned keys, each value wrapped at words under its own
    column, headings, and rows. Built as a list, then written at the width it is shown at."""

    def __init__(self, wide: int) -> None:
        self.wide, self.items = max(wide, 24), []

    def text(self, value: str | Text, style: str = "", indent: int = 0) -> None:
        self.items.append(("text", value if isinstance(value, Text) else Text(value, style), indent))

    def field(self, key: str, value: str | Text | Callable[[int], list[Text]], style: str = "") -> None:
        """A key and its value, wrapped at words under the value's column; a callable is given that
        column's width and lays its own lines out (a line each, cut at a word)."""
        if isinstance(value, str):
            value = Text(" ".join(value.split()), style)
        if callable(value) or value:
            self.items.append(("field", key, value))

    def line(self, value: Text) -> None:
        self.items.append(("line", value))

    def gap(self) -> None:
        if self.items and self.items[-1] != ("gap",):
            self.items.append(("gap",))

    def render(self) -> Text:
        keys = max((len(item[1]) for item in self.items if item[0] == "field"), default=0) + 2
        out = Text()
        for item in self.items:
            if item[0] == "gap":
                out.append("\n")
            elif item[0] == "line":
                out.append_text(item[1])
                out.append("\n")
            elif item[0] == "text":
                _, value, indent = item
                for piece in value.wrap(WRAP, self.wide - indent):
                    out.append(" " * indent)
                    out.append_text(piece)
                    out.append("\n")
            else:
                _, key, value = item
                lines = (
                    value(self.wide - keys) if callable(value) else list(value.wrap(WRAP, self.wide - keys))
                )
                for k, piece in enumerate(lines):
                    out.append(key.ljust(keys) if k == 0 else " " * keys, "bold" if k == 0 else "")
                    out.append_text(piece)
                    out.append("\n")
        out.rstrip()
        return out


# -- the widgets -------------------------------------------------------------------------------------


class Ask(ModalScreen[str | None]):
    """One line typed for a command that needs words (a title, a note, what to ask the planner)."""

    BINDINGS = [Binding("escape", "cancel", show=False)]
    AUTO_FOCUS = "#ask"
    DEFAULT_CSS = """
    Ask { align: center bottom; }
    Ask > Input { width: 100%; margin: 0 0 1 0; }
    """

    def __init__(self, prompt: str, value: str = "") -> None:
        super().__init__()
        self.prompt, self.value = prompt, value

    def compose(self) -> ComposeResult:
        yield Input(value=self.value, placeholder=self.prompt, id="ask")

    ended: str | None = None  # Enter or Esc typed before the line was up: said once it is

    def typed(self, event) -> None:
        """A key typed at once after the one that opened this (a terminal sends `Atidy the tests` in
        one burst): it was queued for the tree before this screen was up, and the tree hands it here,
        to the line, or to what the line will start with when it is not drawn yet."""
        event.stop()
        event.prevent_default()
        boxes = self.query("#ask")
        text = boxes.first(Input).value if boxes else self.value
        if event.key in ("enter", "escape"):
            self.ended = event.key
        elif event.key == "backspace":
            text = text[:-1]
        elif event.is_printable and event.character:
            text += event.character
        if not boxes:
            self.value = text
        else:
            boxes.first(Input).value, boxes.first(Input).cursor_position = text, len(text)
        if self.ended and boxes:
            self.dismiss(text.strip() or None if self.ended == "enter" else None)

    def on_mount(self) -> None:
        if self.ended:  # the whole line was typed, Enter too, before it was drawn
            self.dismiss(self.value.strip() or None if self.ended == "enter" else None)

    @on(Input.Submitted)
    def done(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


def help_text(groups, wide: int) -> Text:
    out = Pane(wide)
    for name, rows in groups:
        keys = max(len(k) for k, _ in rows) + 2
        out.gap()
        out.text(name, "bold")
        for key, what in rows:
            lines = list(Text(what).wrap(WRAP, wide - keys - 2))
            out.line(Text.assemble("  ", (key.ljust(keys), "bold"), lines[0]))
            for more in lines[1:]:
                out.line(Text.assemble(" " * (keys + 2), more))
    return out.render()


class Help(ModalScreen[None]):
    """The keys, grouped as the README groups them: two columns from 110 columns, one below."""

    BINDINGS = [
        Binding("escape,q,question_mark", "app.pop_screen", show=False),
        Binding("j,down", "scroll(1)", show=False),
        Binding("k,up", "scroll(-1)", show=False),
        Binding("ctrl+d", "scroll(8)", show=False),
        Binding("ctrl+u", "scroll(-8)", show=False),
    ]
    DEFAULT_CSS = """
    Help { align: center middle; }
    Help > VerticalScroll {
        width: auto; max-width: 100%; height: auto; max-height: 100%;
        border: round $primary; background: $surface; padding: 0 1; scrollbar-size-vertical: 1;
    }
    Help #help { width: auto; height: auto; }
    Help #help > Static { width: auto; padding: 0 1; }
    Help #end { width: auto; padding: 1 1 0 1; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        width = self.app.size.width
        two = width >= WIDE
        column = min(56, (width - 10) // 2) if two else max(width - 8, 30)
        with VerticalScroll():
            with Horizontal(id="help"):
                if two:
                    yield Static(help_text(HELP[:3], column))
                    yield Static(help_text(HELP[3:], column))
                else:
                    yield Static(help_text(HELP, column))
            yield Static(Text("\n".join(textwrap.wrap(HELP_END, column * (2 if two else 1)))), id="end")

    def action_scroll(self, lines: int) -> None:
        self.query_one(VerticalScroll).scroll_relative(y=lines, animate=False)


class PlanTree(Tree[str]):
    """The tree, with vim's movement and folding, and every row in the row grammar at the width the
    tree has. Two-key sequences (gg, za, …) are read here, so the `a` of `za` never adds a node; so
    are keys typed after `:` or `/` before the line has taken the keyboard."""

    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("G", "scroll_end_node", show=False),
        Binding("enter", "app.record", show=False),
    ]
    CHORDS = {
        "gg": "top",
        "za": "toggle_here",
        "zo": "open",
        "zc": "close",
        "zR": "open_all",
        "zM": "close_all",
    }
    pending = ""
    rows: dict = {}  # a node's data (None: the goal) -> (glyph, word, title, id, bold)
    ids = words = 0  # the widths of the id column and of the state column
    chosen: frozenset = frozenset()  # a visual selection, drawn reversed

    def _room(self, node) -> int:
        depth, up = 0, node
        while up.parent is not None:
            depth, up = depth + 1, up.parent
        width = self.scrollable_content_region.width or self.size.width or 80
        return max(width - depth * self.guide_depth, 8)

    def render_label(self, node, base_style, style) -> Text:
        said = self.rows.get(node.data)
        if said is None:
            return super().render_label(node, base_style, style)
        wide = self._room(node)
        glyph, word, title, node_id, bold = said
        label = row(glyph, word, title, node_id, wide - 2, self.ids, self.words, bold)
        if node.data in self.chosen:
            label.stylize("reverse")
        label.stylize(style)
        icon = (
            (self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE) if node.allow_expand else "  "
        )
        return Text.assemble((icon, base_style + TOGGLE_STYLE), label)

    def get_label_width(self, node) -> int:
        return self._room(node)  # never wider than the tree: no row scrolls sideways

    async def on_key(self, event) -> None:
        if isinstance(self.app.screen, Ask):  # queued here before the prompt a key opened was up
            return self.app.screen.typed(event)
        line = self.app.query_one("#line", Input)
        if line.has_class("-open") and not line.has_focus:  # typed after : or /, before the line took focus
            event.stop()
            event.prevent_default()
            if event.key == "enter":
                self.app.submit_line()
            elif event.key == "escape":
                self.app.action_escape()
            elif event.key == "backspace":
                line.value = line.value[:-1]
            elif event.is_printable and event.character:
                line.value += event.character
            line.cursor_position = len(line.value)
            return
        char = event.character or ""
        if char in (":", "/", "a", "A", "x") and not self.pending:
            # opened here, at once: an app binding's action runs after the keys a terminal sent with
            # it, and `:plan log` typed in one burst ran l and a on the tree before the line opened;
            # `A` and a title typed at once ran the title's d and y. A key that asks for words acts now
            event.stop()
            event.prevent_default()
            opens = {":": lambda: self.app.action_line(":"), "/": lambda: self.app.action_line("/"),
                     "a": lambda: self.app.action_add(False), "A": lambda: self.app.action_add(True),
                     "x": self.app.action_release_or_reopen}  # fmt: skip
            opens[char]()
            return
        if self.pending:
            sequence, self.pending = self.pending + char, ""
            event.stop()
            event.prevent_default()
            if sequence in self.CHORDS:
                await self.run_action(self.CHORDS[sequence])
            return
        if char in ("g", "z"):
            self.pending = char
            event.stop()
            event.prevent_default()

    def action_top(self) -> None:
        self.cursor_line = 0
        self.scroll_home(animate=False)

    def action_scroll_end_node(self) -> None:
        self.cursor_line = max(self.last_line, 0)
        self.scroll_end(animate=False)

    def action_open(self) -> None:
        if self.cursor_node is not None:
            self.cursor_node.expand()

    def _fold_of(self):
        """The node a fold key acts on: itself when it has children, else the branch it sits in."""
        node = self.cursor_node
        if node is not None and not node.children and node.parent not in (None, self.root):
            return node.parent
        return node

    def action_toggle_here(self) -> None:
        node = self._fold_of()
        if node is not None:
            node.toggle()
            self.move_cursor(node)

    def action_close(self) -> None:
        node = self.cursor_node
        if node is not None and (not node.children or not node.is_expanded):
            node = (
                self._fold_of()
                if not node.children
                else (node.parent if node.parent not in (None, self.root) else node)
            )
        if node is not None:
            node.collapse()
            self.move_cursor(node)

    def action_open_all(self) -> None:
        self.root.expand_all()

    def action_close_all(self) -> None:
        node = self.cursor_node
        while node is not None and node.parent is not None and node.parent is not self.root:
            node = node.parent
        for top in self.root.children:
            top.collapse_all()
        _ = self.last_line
        if node is not None:
            self.move_cursor(node)


class Watch(App):
    """The plan, live, on one screen."""

    CSS = """
    Screen { layout: vertical; }
    #where { height: 1; background: $boost; color: $text; padding: 0 1; }
    #main { height: 1fr; layout: horizontal; }
    #tree { width: 1fr; min-width: 30; overflow-x: hidden; scrollbar-size-vertical: 1; padding-right: 1; }
    #side { width: 1fr; border-left: solid $primary; padding: 0 1; scrollbar-size-vertical: 1; }
    Screen.-narrow #main { layout: vertical; }
    Screen.-narrow #tree { height: 3fr; width: 100%; }
    Screen.-narrow #side { height: 1fr; width: 100%; border-left: none; border-top: solid $primary; }
    #side.-alone { border-left: none; border-top: none; }
    #status { height: 2; background: $boost; padding: 0 1; }
    #line { dock: bottom; height: 1; border: none; padding: 0; display: none; }
    #line.-open { display: block; }
    """
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (WIDE, "-wide")]
    AUTO_FOCUS = "#tree"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("q", "quit", show=False),
        Binding("question_mark", "help_or_ask", show=False),
        Binding("colon", "line(':')", show=False),
        Binding("slash", "line('/')", show=False),
        Binding("escape", "escape", show=False),
        Binding("n", "next_or_needs", show=False),
        Binding("a", "add(False)", show=False),
        Binding("A", "add(True)", show=False),
        Binding("e", "edit(True)", show=False),
        Binding("E", "edit(False)", show=False),
        Binding("d", "drop", show=False),
        Binding("y", "yes", show=False),
        Binding("s", "split", show=False),
        Binding("u", "undo", show=False),
        Binding("R", "run(False)", show=False),
        Binding("r", "run(True)", show=False),
        Binding("x", "release_or_reopen", show=False),
        Binding("l", "tail", show=False),
        Binding("V", "visual", show=False),
        Binding("w", "offer('w')", show=False),
        Binding("b", "offer('b')", show=False),
        Binding("P", "plan_first", show=False),
        Binding("ctrl+d", "page(1)", show=False),
        Binding("ctrl+u", "page(-1)", show=False),
    ]

    def __init__(self, root: Path, open_store: Callable, every: float = 1.0) -> None:
        super().__init__()
        self.root_path, self.open_store, self.every = root, open_store, every
        self.view = "contract"  # or "tail", "record", "said": what the side pane shows for the selected node
        self.message = ""  # what the last command said: the bottom line's, until the cursor moves
        self.busy = ""  # why the last look at the plan failed; the next tick tries again
        self.search = ""
        self.anchor: int | None = None  # the line visual selection started on
        self.shape: object = None  # what the tree was last built from: rebuilt only when it changed
        self.runs: list[subprocess.Popen] = []
        self.first = True
        self.known: set[str] = set()
        self.files: list[str] = []  # what git tracks, for the check that names a missing file
        self.files_at = 0.0
        self.nodes: list[P.Node] = []
        self.words: dict[str, str] = {}  # each node's state, as a person reads it (plan.reads)
        self.back: set[str] = set()  # the leaves that came back
        self.counts: dict = {}  # what the bottom line's first line says
        self.records: dict = {}  # a node's record, laid out, kept until the node moves on
        self.sized: tuple = ()
        self.by_id: dict[str, P.Node] = {}
        self.under: dict = {}
        self.offered: dict[str, list[str]] = {}  # the keys each leaf that came back offers

    # -- the screen ----------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="where")
        with Horizontal(id="main"):
            tree = PlanTree("the plan", id="tree")
            tree.show_root = False  # until there is a plan: then the goal is its first row
            tree.guide_depth = 2
            tree.rows = {}
            yield tree
            with VerticalScroll(id="side"):
                yield Static(id="detail", markup=False)
        yield Static(id="status", markup=False)
        yield Input(id="line", select_on_focus=False)  # else the first key typed replaces the ":"

    def on_mount(self) -> None:
        self.refresh_plan()
        self.call_after_refresh(self.refresh_plan)  # the panes have their sizes now
        self.set_interval(self.every, self.refresh_plan)

    def on_resize(self) -> None:
        if self.shape is not None:
            self.refresh_plan()

    @property
    def tree(self) -> PlanTree:
        return self.query_one("#tree", PlanTree)

    def selected(self) -> str | None:
        node = self.tree.cursor_node
        return node.data if node is not None else None

    def on_goal(self) -> bool:
        return self.tree.show_root and self.tree.cursor_node is self.tree.root

    def word(self, node_id: str | None) -> str:
        return self.words.get(node_id or "", "")

    def chosen(self) -> list[str]:
        """The nodes a key acts on: the visual selection, else the one under the cursor."""
        if self.anchor is None:
            return [i for i in [self.selected()] if i]
        low, high = sorted((self.anchor, self.tree.cursor_line))
        out = []
        for line in range(low, high + 1):
            node = self.tree.get_node_at_line(line)
            if node is not None and node.data:
                out.append(node.data)
        return out

    def read(self, what: Callable, default=None):
        """One look at the plan for a key; a store too busy to open is said, never a crash."""
        try:
            with self.open_store() as store:
                return what(store)
        except (sqlite3.Error, OSError) as no:
            self.busy = f"✗ the plan's store did not open ({no}); try again"
            self.say_status()
            return default

    def refresh_plan(self) -> None:
        """Look at the plan and draw it. A store that cannot be opened (busy, or being made by another
        screen that started at the same moment) leaves the last screen up and says so; the next tick
        tries again."""
        try:
            with self.open_store() as store:
                self.draw(store)
            self.busy = ""
        except (sqlite3.Error, OSError) as no:
            self.busy = f"✗ the plan's store did not open ({no}); the screen is as it was, and tries again"
        self.say_status()

    def draw(self, store) -> None:
        nodes = [n for n in P.nodes(store) if n.state not in P.GONE and not (n.aside and n.state == P.DONE)]
        goal, proposed = P.goal(store), store.meta("goal:proposed")
        by_id = {n.id: n for n in nodes}
        under = P.kids(nodes, drawn=True)
        self.nodes, self.by_id, self.under = nodes, by_id, under
        self.back = {n.id for n in nodes if P.came_back(store, n)}
        self.offered = {i: [k for k, _, _ in P.offers(store, by_id[i])] for i in self.back}
        self.words = {n.id: P.reads(n, nodes, self.back) for n in nodes}
        leaves = [n for n in P.leaves(nodes) if n.state != P.PROPOSED and not n.aside]
        done = sum(n.state == P.DONE for n in leaves)
        tops = [
            n
            for n in nodes
            if n.state == P.PROPOSED and (n.parent not in by_id or by_id[n.parent].state != P.PROPOSED)
        ]
        yours = [i for i, w in self.words.items() if w in ("came back", "review", "yours")]
        self.counts = {
            "you": len(tops) + len(yours),
            "running": sum(n.state == P.RUNNING for n in leaves),
            "ready": sum(w == "ready" for w in self.words.values()),
            "done": f"{done}/{len(leaves)} done",
            "first": P.plan_first(store),
        }
        goal_word = "proposed" if proposed and not goal else self.counts["done"]
        shape = [(n.id, n.parent, n.state, n.title, n.rev, n.id in self.back) for n in nodes]
        tree = self.tree
        with self.prevent(Tree.NodeHighlighted):  # the tree moved, not the person
            show = bool(nodes or goal or proposed)
            if tree.show_root != show:
                tree.show_root = show
            tree.display = show  # no plan yet: the pane says so, across the screen
            self.query_one("#side").set_class(not show, "-alone")
            if shape != self.shape:
                self.rebuild(nodes, under)
                if self.shape is not None and self.view == "said":
                    self.view = "contract"  # the plan moved: what a `:` command printed is old news
                self.shape = shape
            self.relabel(nodes, under, goal_word, goal or proposed or "no goal yet")
        self.size_panes(nodes, tree.ids, tree.words)
        where, room = P.where(self.root_path), max(self.size.width - 2 - len("the plan of "), 10)
        if len(where) > room:  # the repository's own name, and what is above it as far as it fits
            where = "…" + where[len(where) - room + 1 :]
        self.query_one("#where", Static).update(Text(f"the plan of {where}", "bold"))
        self.show_detail(store)

    def relabel(self, nodes: list[P.Node], under: dict, goal_word: str, goal: str) -> None:
        tree = self.tree
        rows = {
            n.id: (P.look(self.words[n.id])[0], self.words[n.id], n.title, n.id, bool(under.get(n.id)))
            for n in nodes
        }
        rows[None] = (P.look(goal_word)[0], goal_word, goal, "", True)
        ids = max((len(n.id) for n in nodes), default=0)
        words = max((len(w) for w in [*self.words.values(), goal_word]), default=0)
        chosen = frozenset(self.chosen()) if self.anchor is not None else frozenset()
        if (rows, ids, words, chosen) != (tree.rows, tree.ids, tree.words, tree.chosen):
            tree.rows, tree.ids, tree.words, tree.chosen = rows, ids, words, chosen
            tree._invalidate()  # every row is laid out again: a column may have changed width

    def size_panes(self, nodes: list[P.Node], ids: int, words: int) -> None:
        """At 110 columns and more the tree is as wide as its rows need, and the node pane has the
        rest (never less than PANE); below that the tree is as tall as its rows, up to half the
        screen, and the node pane has what is left under it."""
        tree, width, height = self.tree, self.size.width, self.size.height
        if not width:
            return
        by_id = {n.id: n for n in nodes}
        if not tree.display:
            return
        if width >= WIDE:
            need = max(
                (2 * (len(P.above(n, by_id)) + 1) + 4 + len(n.title) for n in nodes), default=30
            ) + 2 + ids + 2 + words + 2  # fmt: skip
            sized = ("wide", max(30, min(need, width - PANE - 3)))
        else:
            lines = tree.last_line + 1 if tree.show_root else 0
            sized = ("narrow", max(3, min(lines, (height - 3) // 2)))
        if sized != self.sized:
            self.sized = sized
            kind, amount = sized
            tree.styles.width = amount if kind == "wide" else None
            tree.styles.height = amount if kind == "narrow" else None

    def pane_room(self) -> tuple[int, int]:
        """The node pane's width and height, from the layout this screen sets (known before Textual
        has laid it out): its text is wrapped to it, and a leaf that came back fitted to it."""
        width, height = self.size.width, self.size.height
        kind, amount = self.sized or ("narrow", 10)
        if kind == "wide":
            return max(width - amount - 4, 20), max(height - 3, 5)
        return max(width - 3, 20), max(height - 3 - amount - 1, 3)

    def rebuild(self, nodes: list[P.Node], under: dict) -> None:
        tree = self.tree
        y = tree.scroll_y
        was_open = {n.data for n in _walk(tree.root) if n.is_expanded}
        cursor, at_goal = self.selected(), tree.cursor_node is tree.root
        tree.clear()
        placed = {}
        by_id = {n.id: n for n in nodes}
        queue = [n for n in nodes if n.parent not in by_id]  # the tops, then each one's children
        while queue:
            node = queue.pop(0)
            parent = placed.get(node.parent) if node.parent in by_id else tree.root
            has_kids = bool(under.get(node.id))
            finished = has_kids and all(c.state == P.DONE for c in P.below(node.id, nodes))
            opened = (not finished) if self.first else node.id in was_open or node.id not in self.known
            placed[node.id] = parent.add(Text(node.title), data=node.id, expand=opened, allow_expand=has_kids)
            queue[:0] = [c for c in under.get(node.id, []) if c.id in by_id]
        tree.root.allow_expand = bool(nodes)
        if self.first:
            tree.root.expand()  # the goal's row starts open, as every unfinished sub-goal does
        self.known = {n.id for n in nodes}
        self.first = False
        _ = tree.last_line  # lays the new tree out, so the line of each node is known
        if cursor in placed and not at_goal:
            tree.cursor_line = placed[cursor].line
        elif tree.cursor_line < 0:
            tree.cursor_line = 0  # a screen opens on the first row: the goal
        tree.scroll_to(y=y, animate=False)

    def say_status(self) -> None:
        """Two lines, each fitted at a word: the plan (what waits on the person, the executors, what
        R would start, how much is done, plan first), then the moment (what the last command said,
        else what the keys do here). The short forms at 80 columns; whole pieces drop off the end."""
        if not self.is_running:
            return
        room = max(self.size.width - 2, 20)
        c = self.counts or {"you": 0, "running": 0, "ready": 0, "done": "0/0 done", "first": False}
        you = "magenta" if c["you"] else ""
        busy = P.look("running")[1] if c["running"] else ""
        first = "on" if c["first"] else "off"
        long = [
            (f"waiting on you: {c['you']}", you),
            (f"executors: {c['running']} running" if c["running"] else "executors: none", busy),
            (f"R runs {c['ready']} ready" if c["ready"] else "nothing ready to run", ""),
            (c["done"], ""),
            (f"plan first: {first} (P)", ""),
        ]
        short = [
            (f"you: {c['you']}", you),
            (f"{c['running']} running", busy),
            (f"R: {c['ready']} ready" if c["ready"] else "none ready", ""),
            (c["done"], ""),
            (f"plan first: {first}", ""),
        ]
        whole = " · ".join(text for text, _ in long)
        top = fit(long if len(whole) <= room else short, room)
        said = self.busy or self.message
        if said:
            bottom = Text(T.elide(said.splitlines()[0], room))
            if bottom.plain.startswith("✗"):  # red is for a command that failed, and only its mark
                bottom.stylize("red", 0, 1)
        else:
            bottom = fit([(k, "") for k in self.keys()], room)
        self.query_one("#status", Static).update(Text.assemble(top, "\n", bottom))

    def keys(self) -> list[str]:
        """What the keys do on the row under the cursor, for the bottom line."""
        tail = ["? help", "q quit"]
        if self.anchor is not None:
            return ["VISUAL", "y accept", "d drop", "j k widen it", "Esc ends"]
        if self.view == "record":
            offers = [OFFERED[k] for k in self.offer_keys()]
            ask = ["? ask the planner", "q quit"] if offers else tail  # there ? is no help: it spends
            return ["ctrl-d ctrl-u scroll", "Enter back", *offers, *ask]
        if self.view == "tail":
            return ["ctrl-d ctrl-u scroll", "l back", *tail]
        if self.view == "said":
            return ["ctrl-d ctrl-u scroll", "Esc back", *tail]
        if not self.nodes:
            return [":ask what you want", *tail]
        if self.on_goal():
            keys = ["y accept it all"] if self.counts.get("you") else ["R run all ready"]
            return [*keys, "E edit the plan as text", "za fold all", *tail]
        word = self.word(self.selected())
        if word == "came back":
            offers = [OFFERED[k] for k in self.offer_keys()]
            return [*offers, "? ask the planner", "Enter record", "q quit"]
        if word in KEYS:
            return [*KEYS[word], *tail]
        return ["za fold", "r run what is ready here", "E edit it as text", *tail]  # a sub-goal

    def offer_keys(self) -> list[str]:
        return self.offered.get(self.selected() or "", [])

    def show_detail(self, store) -> None:
        node_id = self.selected()
        pane = self.query_one("#detail", Static)
        wide, high = self.pane_room()
        if not self.nodes and not self.tree.show_root:
            empty = Pane(wide)
            empty.text(EMPTY)
            pane.update(empty.render())
            return
        if self.view == "said":
            return  # what a `:` command printed stays until the cursor moves
        if node_id is None or store.node_row(node_id) is None:
            pane.update(goal_pane(store, self, wide))
            return
        node = P.get(store, node_id)
        if self.view == "tail":
            pane.update(tail_pane(store, node, self.root_path, wide))
            return
        if self.view == "record":
            key = (node.id, node.rev, node.state, node.updated_at, len(store.node_log(node.id)), wide)
            key += (int(time.monotonic() // 10),) if node.state == P.RUNNING else ()  # its tree moves
            pane.update(self.recorded(key, lambda: record_pane(store, node, self, wide)))
            return
        if time.monotonic() - self.files_at > 10:
            self.files, self.files_at = P.tracked(self.root_path), time.monotonic()
        pane.update(detail(store, node, self, self.files, (wide, high)))

    def recorded(self, key, make: Callable) -> Text:
        """A record is git and the log read again: made once for a node as it stands, not every tick."""
        if key not in self.records:
            self.records = {key: make()}
        return self.records[key]

    # -- keys ------------------------------------------------------------------------------------

    def did(self, argv: list[str], quiet: bool = False, keep: bool = False):
        """Run one command, and say on the bottom line which it was and the gist of what it said.
        Returns its exit code, or with ``keep`` all it said."""
        code, said = _cli(argv)
        lines = [line for line in said.splitlines() if line.strip() and "(the plan of " not in line]
        first = lines[0].strip() if lines else ""
        for word in argv[1:]:  # `graphene node edit x: x: scope changed` says x once
            first = first.removeprefix(f"{word}: ")
        first = first.removeprefix(f"{' '.join(argv[:2])}: ")  # and `plan first on: plan first: on`
        self.message = f"{'✗ ' if code else ''}graphene {shlex.join(argv)}" + (f": {first}" if first else "")
        if not quiet:
            self.refresh_plan()
        return said if keep else code

    @on(Tree.NodeHighlighted)
    def moved(self) -> None:
        if self.view == "said":
            self.view = "contract"
        self.message = ""  # the person moved on: the bottom line says what the keys do here
        if self.shape is not None:
            self.refresh_plan()

    @on(Tree.NodeExpanded)
    @on(Tree.NodeCollapsed)
    def folded(self) -> None:
        if self.shape is not None:
            self.call_after_refresh(self.refresh_plan)  # below 110 columns the tree is as tall as its rows

    def action_help_or_ask(self) -> None:
        node_id = self.selected()
        if node_id is not None and node_id in self.back:  # there ? asks the planner, which spends
            self.background(
                ["ask", f"{node_id} came back: propose what would let it be done", "--about", node_id]
            )
        else:
            self.push_screen(Help())

    def action_line(self, kind: str) -> None:
        line = self.query_one("#line", Input)
        line.value = kind
        line.add_class("-open")
        line.cursor_position = len(kind)
        # shown first, as a hidden input takes no focus; not if Enter or Esc, typed ahead, closed it
        self.call_after_refresh(lambda: line.has_class("-open") and line.focus())

    def submit_line(self) -> None:
        self.ran(self.query_one("#line", Input).value)

    @on(Input.Submitted, "#line")
    def ran_line(self, event: Input.Submitted) -> None:
        self.ran(event.value)

    def ran(self, text: str) -> None:
        line = self.query_one("#line", Input)
        line.remove_class("-open")
        self.tree.focus()
        if text.startswith("/"):
            self.search = text[1:].strip().lower()
            self.find(self.search)
            return
        words = text[1:].strip().removeprefix("graphene ").strip()
        if not words:
            return
        try:
            argv = shlex.split(words)
        except ValueError as no:
            if re.match(r"ask\s", words):  # `:ask don't …`: not the shell's, so the sentence as typed
                return self.background(["ask", words[3:].strip()])
            self.message = f"✗ {no}"
            return self.say_status()
        if argv[:1] == ["ask"]:
            argv = _sentence(argv)
        if argv[:1] == ["stop"]:
            return self.stop_runs()
        if argv[:1] in (["ui"], ["watch"], ["ingest"], ["init"]):
            self.message = f"✗ `graphene {argv[0]}` takes a terminal of its own: run it outside this screen"
            return self.say_status()
        slow = argv[:1] in (["run"], ["ask"]) or argv[:2] in (
            ["node", n] for n in ("split", "done", "signoff")
        )
        if slow:  # it can take minutes (a check, an agent): the screen stays yours
            return self.background(argv)
        if argv[:2] in (["plan", "edit"], ["node", "edit"]):
            return self.edit_with(argv)
        said = self.did(argv, keep=True)
        lines = [line for line in said.splitlines() if "(the plan of " not in line]
        if len(lines) > 1:  # more than a line (a record, the log): it gets the side pane
            self.view = "said"
            self.query_one("#detail", Static).update(hanging("\n".join(lines), self.pane_room()[0]))
            self.message = f"graphene {shlex.join(argv)}: {len(lines)} lines, in the pane"
            self.say_status()

    def action_escape(self) -> None:
        line = self.query_one("#line", Input)
        if line.has_class("-open"):
            line.remove_class("-open")
            self.tree.focus()
        self.anchor = None
        self.search = ""
        self.view = "contract"
        self.message = ""
        self.refresh_plan()

    def find(self, text: str, after: int | None = None) -> None:
        if not text:
            return
        titles = {n.id: n.title for n in self.nodes}
        shown = [n.data for n in _walk(self.tree.root) if n.data in titles]
        # what the row shows: its title, its id, and the word its state reads as (`/came back`)
        hits = [i for i in shown if any(text in f.lower() for f in (titles[i], i, self.word(i)))]
        if not hits:
            self.message = f"✗ nothing matches {text!r}"
            return self.say_status()
        current = self.selected()
        start = hits.index(current) + 1 if current in hits else 0
        target = hits[start % len(hits)]
        for node in _walk(self.tree.root):
            if node.data == target:
                parent = node.parent
                while parent is not None:
                    parent.expand()
                    parent = parent.parent
                _ = self.tree.last_line
                with self.prevent(Tree.NodeHighlighted):  # the search moved it: its line stays said
                    self.tree.move_cursor(node)
        if self.view == "said":
            self.view = "contract"  # the search moved the cursor: the node's pane, not the output
        self.message = f"/{text}: {hits.index(target) + 1} of {len(hits)} (n next · Esc ends the search)"
        self.refresh_plan()

    def action_next_or_needs(self) -> None:
        if self.search:
            return self.find(self.search)
        self.action_offer("n")

    def action_add(self, child: bool) -> None:
        node_id = self.selected()
        parent = node_id if child else self.read(lambda s: P.get(s, node_id).parent if node_id else None)

        def added(title: str | None) -> None:
            if title:
                self.did(["node", "add", *(["--parent", parent] if parent else []), "--", title])

        where = f"under {parent}" if parent else "at the top"
        kind = "child" if child else "sibling"
        self.push_screen(
            Ask(f"a new {kind} {where}: its title (then e fills in the rest, or s the planner)"),
            added,
        )

    def action_edit(self, alone: bool) -> None:
        node_id = self.selected()
        self.edit_with(
            ["node", "edit", node_id]
            if alone and node_id
            else ["plan", "edit", *([node_id] if node_id else [])]
        )

    def edit_with(self, argv: list[str]) -> None:
        from textual.app import SuspendNotSupported

        try:
            with self.suspend():
                self.did(argv, quiet=True)
        except SuspendNotSupported:  # no terminal to hand over (a test): the editor runs without one
            self.did(argv, quiet=True)
        self.shape = None
        self.refresh_plan()

    def action_yes(self) -> None:
        """y: accept a proposal (or the selection); on a leaf in review, sign it off; on a person's
        own leaf, it is done; on the goal, accept all that is proposed."""
        word = self.word(self.selected())
        if self.anchor is None and word == "review":
            return self.background(["node", "signoff", self.selected()])  # runs the roll-up check: minutes
        if self.anchor is None and word == "yours":
            return self.background(["node", "done", self.selected()])
        if self.anchor is None and self.on_goal():
            self.did(["plan", "accept"], quiet=True)
            return self.refresh_plan()
        ids = self.chosen()
        fresh = self.read(
            lambda s: [i for i in ids if s.node_row(i) and s.node_row(i)["state"] == P.PROPOSED], []
        )
        if ids:  # none a proposal: the command runs as chosen, and its refusal says why
            self.did(["plan", "accept", *(fresh or ids)], quiet=True)  # one act: u undoes all of it
        self.anchor = None
        self.refresh_plan()

    def action_drop(self) -> None:
        ids = self.chosen()
        if ids:
            self.did(["node", "drop", *ids], quiet=True)  # one act too, all or none
        self.anchor = None
        self.refresh_plan()

    def action_split(self) -> None:
        node_id, word = self.selected(), self.word(self.selected())
        if word in ("running", "review", "done"):  # a planner spends: never started for nothing
            self.message = f"✗ {node_id} is {word}: s splits a leaf still to do, so no planner was started"
            return self.say_status()
        if node_id:
            self.background(["node", "split", node_id])

    def action_undo(self) -> None:
        self.did(["plan", "undo"])

    def action_run(self, here: bool) -> None:
        node_id = self.selected()
        argv = ["run", *shlex.split(RUN_WITH), *(["--node", node_id] if here and node_id else [])]
        self.background(argv)

    def action_plan_first(self) -> None:
        self.did(["plan", "first", "off" if self.counts.get("first") else "on"])

    def action_release_or_reopen(self) -> None:
        node_id = self.selected()
        if node_id is None:
            return
        state = self.read(lambda s: P.get(s, node_id).state)
        if state == P.RUNNING:
            self.did(["node", "release", node_id, "--why", "the person released it, from graphene watch"])
        elif state in (P.DONE, P.REVIEW):

            def reopened(note: str | None) -> None:
                if note:
                    self.did(["node", "reopen", node_id, "--note", note])

            self.push_screen(Ask(f"reopen {node_id}: what is wrong (its next executor is told)"), reopened)
        elif state is not None:
            self.message = (
                f"{node_id} is {self.word(node_id)}: x releases a running leaf, or reopens a finished one"
            )
            self.say_status()

    def action_tail(self) -> None:
        self.view = "contract" if self.view == "tail" else "tail"
        self.refresh_plan()

    def action_record(self) -> None:
        if self.on_goal():  # the goal has no record of its own: its pane already says what is under it
            return
        self.view = "contract" if self.view == "record" else "record"
        self.query_one("#side", VerticalScroll).scroll_home(animate=False)
        self.refresh_plan()

    def action_visual(self) -> None:
        self.anchor = None if self.anchor is not None else self.tree.cursor_line
        self.refresh_plan()

    def action_offer(self, key: str) -> None:
        node_id = self.selected()
        if node_id is None:
            return
        offers = self.read(lambda s: {k: argv for k, _, argv in P.offers(s, P.get(s, node_id))}, {})
        if key in offers:
            self.did(offers[key])
        else:
            self.message = f"{node_id} has no '{key}' to offer: it did not come back wanting one"
            self.say_status()

    def action_page(self, way: int) -> None:
        side = self.query_one("#side", VerticalScroll)
        side.scroll_relative(y=way * max(side.size.height - 2, 3), animate=False)

    # -- what runs on its own ------------------------------------------------------------------------

    def background(self, argv: list[str]) -> None:
        """A run or a planner: its own process, with its output in .graphene/runs/, so it goes on
        whatever happens to this screen. It has no terminal; what the person typed here was typed at
        this screen's, and GRAPHENE_WATCH says so to the log (`plan.caller`)."""
        logs = self.root_path / ".graphene" / "runs"
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / f"{argv[0]}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{len(self.runs)}.txt"
        cli = "import sys; from graphene_debrief.cli import app; sys.argv[0] = 'graphene'; app()"
        env = {**os.environ, "GRAPHENE_WATCH": "1" if sys.stdin.isatty() else ""}
        with open(log, "w", encoding="utf-8") as sink:
            proc = subprocess.Popen(
                [sys.executable, "-c", cli, *argv], cwd=self.root_path, stdin=subprocess.DEVNULL,
                stdout=sink, stderr=subprocess.STDOUT, start_new_session=True, env=env,
            )  # fmt: skip
        self.runs.append(proc)
        self.message = f"graphene {shlex.join(argv)}: started (its output: {log.relative_to(self.root_path)})"
        self.say_status()
        threading.Thread(target=self.follow, args=(proc, argv, log), daemon=True).start()

    def follow(self, proc: subprocess.Popen, argv: list[str], log: Path) -> None:
        """On a thread of its own that never keeps the screen from closing (q leaves at once; the
        run goes on). The bottom line gets the line that says what happened: a command's first (a
        check's output and what is next come after it), a planner's first after its last try (what
        it says, else what it proposed), a run's last; the side pane gets all of it."""
        code = proc.wait()
        said = R.tail(log, 400)
        tried = max((k for k, line in enumerate(said) if line.startswith("asking the planner")), default=-1)
        news = [line.strip() for line in said[tried + 1 :] if line.strip() and "(the plan of " not in line]
        gist = (news[-1] if argv[0] == "run" else news[0]) if news else ""
        named = argv[: next((k for k, word in enumerate(argv) if word.startswith("-")), len(argv))]
        mark = "✗ " if code else ""  # its options were on the bottom line when it started: room for the gist
        whole = [f"{mark}graphene {shlex.join(argv)} ended (exit {code}); all it said, kept in "
                 f"{log.relative_to(self.root_path)}:", "", *said]  # fmt: skip
        # a run's own last line says what it did (`run: 3 done, …`): said once, not after "run ended"
        told = f"{mark}{gist}" if re.match(rf"{re.escape(argv[0])}\b", gist) else (
            f"{mark}graphene {shlex.join(named)} ended: {gist}"
        )  # fmt: skip
        made = [line.removeprefix("proposed ").split(":")[0] for line in news if line.startswith("proposed ")]
        if argv[0] == "ask" or argv[:2] == ["node", "split"]:  # the sentence was on the line when it began
            told = mark + (f"the planner proposed {', '.join(made)}" if made else f"the planner: {gist}")
            told += "; what it said is in the pane"
        with contextlib.suppress(Exception):  # the screen may be gone by now
            self.call_from_thread(self.finished, told, "\n".join(whole))

    def finished(self, message: str, whole: str) -> None:
        self.message = message
        self.refresh_plan()  # first: what it did moved the plan, which puts the side pane back
        self.view = "said"  # then all it said is there, until the cursor moves
        self.query_one("#detail", Static).update(hanging(whole, self.pane_room()[0]))
        self.say_status()

    def stop_runs(self) -> None:
        """`:stop`: Ctrl-C to a run started here (or to the parallel run this repo has going): it hands
        back what it holds, and stops its executors."""
        pids = [p.pid for p in self.runs if p.poll() is None]
        pid = R.run_holding(self.root_path)  # by pid and start time: a reused pid is no run
        if pid is not None:
            shown = subprocess.run(
                ["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True
            )
            if "graphene" in shown.stdout:
                pids.append(pid)
        for pid in set(pids):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGINT)
        self.message = (
            f"stopping {len(set(pids))} run(s): what they hold goes back to the plan"
            if pids
            else "no run to stop"
        )
        self.say_status()


def _walk(node):
    for child in node.children:
        yield child
        yield from _walk(child)


def _sentence(argv: list[str]) -> list[str]:
    """`:ask` as the shell reads it, its words one sentence: `:ask --about ids fix it` is `graphene ask
    'fix it' --about ids`, what `?` builds; `:ask add a login page` needs no quotes. Only ask's own
    options are options: `:ask add a --dry-run flag` asks for a --dry-run flag."""
    words, options, rest = [], [], iter(argv[1:])
    for word in rest:
        if word in ("--with", "--about"):
            options += [word, next(rest, "")]
        else:
            words.append(word)
    return ["ask", *([" ".join(words)] if words else []), *options]


# -- the node pane -----------------------------------------------------------------------------------


def _clock(stamp: str | None, seconds: bool = False) -> str:
    if not stamp:
        return ""
    try:
        at = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return stamp[11 : 19 if seconds else 16]
    return at.strftime("%H:%M:%S" if seconds else "%H:%M")


def _where(checkout: str | None, root: Path) -> str:
    if not checkout:
        return "not on record"
    if ".graphene" in checkout:
        return checkout[checkout.index(".graphene") :]
    if Path(checkout) == Path(root):
        return "none: it works in the repository itself"
    return P.where(checkout)


def _header(pane: Pane, node: P.Node, word: str, extra: str = "") -> None:
    pane.text(node.title, "bold")
    head = Text.assemble((node.id, "dim"), " · ", (word, P.look(word)[1]))
    if extra:
        head.append(extra)
    pane.text(head)


def _why(pane: Pane, store, node: P.Node, by_id: dict) -> None:
    """Why the node is there, short: the goal on one line, then each sub-goal down to it."""
    goal, path = P.goal(store), list(reversed(P.above(node, by_id)))

    def lines(wide: int) -> list[Text]:
        out = [Text(T.elide(goal, wide))] if goal else []
        for depth, up in enumerate(path):
            indent = "  " * (depth + (1 if goal else 0))
            title = T.elide(up.title, max(wide - len(indent) - len(up.id) - 2, 8))
            out.append(Text.assemble(indent, title, "  ", (up.id, "dim")))
        return out

    if goal or path:
        pane.field("why", lines)


def _contract(pane: Pane, store, node: P.Node, s, root: Path | None, files: list[str] | None) -> None:
    """The contract, in aligned keys: what it should achieve, where it may write, what shows it is
    done, what it waits on (each with its state) and whose it is, when that is not an agent's."""
    everything = s.nodes
    if node.goal and node.goal != node.title:
        pane.field("goal", node.goal)
    if not s.under.get(node.id):
        pane.field("scope", ", ".join(node.scope))
    if node.check:
        pane.field(
            "check", node.check + ("  (runs when its leaves are done)" if s.under.get(node.id) else "")
        )
    if files is not None and root is not None and not s.under.get(node.id):
        missing = P.unreachable(node, files, root, everything)
        if missing:
            pane.field("", f"⚠ {P.unreachable_said(missing)}", "magenta")  # as `graphene node add` says it
    needs = P.all_needs(node, s.by_id)
    if needs:
        said = Text()
        for k, need in enumerate(needs):
            word = s.words.get(need, "gone")
            said.append(", " if k else "")
            said.append(need)
            said.append(f" ({word})", P.look(word)[1])
        pane.field("needs", said)
    if node.owner != P.AGENT:
        pane.field("owner", node.owner)
    if node.signoff and s.words.get(node.id) != "review":  # in review, the line above says it
        pane.field("signoff", "a person signs it off after its check passes")


def _rows(pane: Pane, children: list[P.Node], words: dict[str, str], under: dict) -> None:
    ids = max((len(c.id) for c in children), default=0)
    width = max((len(words.get(c.id, "")) for c in children), default=0)
    if pane.wide - 4 - (2 + ids) - (2 + width) < 20:  # a narrow pane: the title, not the id, is read
        ids = 0
    for c in children:
        word = words.get(c.id, c.state)
        pane.line(row(P.look(word)[0], word, c.title, c.id, pane.wide, ids, width, bool(under.get(c.id))))


def _waiting(pane: Pane, below: list[P.Node], s) -> None:
    """One line: what under it is waiting, and on what; what came back, is in review, is proposed or
    is the person's own."""
    said, proposed, how = [], [], {"yours": "is yours", "came back": "came back", "review": "is in review"}
    for n in below:
        word = s.words.get(n.id, "")
        if word == "waiting":
            on = [f"{b.id} ({T.blocker(b, s.words)})" for b in P.unmet(n, s.by_id)]
            said.append(f"{n.id} on {', '.join(on)}")
        elif word in how:
            said.append(f"{n.id} {how[word]}")
        elif n.state == P.PROPOSED and (n.parent not in s.by_id or s.by_id[n.parent].state != P.PROPOSED):
            proposed.append(n.id)  # a proposed subtree, once, at its top
    if proposed:
        ids = ", ".join(proposed[:-1]) + (" and " if len(proposed) > 1 else "") + proposed[-1]
        said.append(f"{ids} {'is' if len(proposed) == 1 else 'are'} proposed, for you to accept or prune")
    if said:
        pane.field("waiting", " · ".join(said))


def goal_pane(store, s, wide: int) -> Text:
    """The goal, the plan's first row: the person's sentence whole, how much is done, what sits
    right under it, and what is waiting."""
    pane = Pane(wide)
    goal, proposed = P.goal(store), store.meta("goal:proposed")
    pane.text(goal or proposed or "no goal yet", "bold")
    word = "proposed" if proposed and not goal else s.counts.get("done", "")
    extra = " with the tree: accepting any of it accepts it" if word == "proposed" else ""
    pane.text(Text.assemble(("the goal", "dim"), " · ", (word, P.look(word)[1]), extra))
    if not goal and not proposed:
        pane.text("the root of the tree, in your words: :plan goal '…' says why any of this is done", "dim")
    tops = s.under.get(None, [])
    if tops:
        pane.gap()
        _rows(pane, tops, s.words, s.under)
        pane.gap()
        _waiting(pane, s.nodes, s)
    return pane.render()


def detail(store, node: P.Node, s, files: list[str] | None = None, room: tuple[int, int] = (60, 0)) -> Text:
    """The node under the cursor, for the person: a pane for each kind of node, none of it blank and
    nothing said twice. ``room``: the pane's width and height; a leaf that came back is fitted to it,
    so every key stays in sight at 80×24."""
    wide, high = room
    pane = Pane(wide)
    word = s.words.get(node.id) or P.reads(node, s.nodes)
    kids = s.under.get(node.id, [])
    held = len(store.node_log(node.id, ("started",)))
    attempt = f" · attempt {held}" if held > 1 and word in ("running", "came back") else ""
    if word == "proposed" and node.state == P.PROPOSED:
        _header(pane, node, "proposed", f" by {P.said_by(node.proposed_by)}")
    elif word == "done":
        _header(pane, node, word, f" at {_clock(node.finished_at)}" if node.finished_at else "")
    else:
        _header(pane, node, word, attempt)
    if kids:  # a sub-goal: why, its own goal and check, its children as rows, what is waiting
        pane.gap()
        _why(pane, store, node, s.by_id)
        _contract(pane, store, node, s, None, None)
        pane.gap()
        _rows(pane, kids, s.words, s.under)
        pane.gap()
        _waiting(pane, P.below(node.id, s.nodes), s)
        return pane.render()
    if word == "came back":
        _came_back(pane, store, node, high)
    elif word == "running":
        _running(pane, store, node, s)
    elif word == "review" and P.unlanded(store, node.id) is not None:
        left = P.unlanded(store, node.id) or {}
        pane.text(f"it passed its check, and did not land here: {_unmerged(left)}", "magenta")
        pane.field("then", f"git merge {left.get('branch', 'graphene/' + node.id)}, and y signs it off")
    elif word == "review":
        pane.text("its check passed; it waits for your sign-off", "magenta")
    elif word == "yours":
        pane.text("yours to do: no executor takes it", "magenta")
    elif word == "to fill in":
        pane.text(
            "it has no scope and no leaves yet: the planner can split it, or you give it a scope and a check",
            "dim",
        )
    pane.gap()
    _why(pane, store, node, s.by_id)
    _contract(pane, store, node, s, s.root_path, files)
    if word in ("done", "review"):
        ended = (store.node_log(node.id, ("finished", "overruled")) or [{"detail": {}}])[-1]["detail"]
        pane.field("changed", ", ".join(ended.get("changed") or []) or "nothing on record")
    last = (store.node_log(node.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
    if word != "came back" and node.state == P.OPEN and last["kind"] == "released":
        pane.field("handed back", str(last["detail"].get("why", "")))
    elif node.state == P.OPEN and last["kind"] == "reopened":
        pane.field("sent back", str(last["detail"].get("note", "")))
    return pane.render()


def _came_back(pane: Pane, store, node: P.Node, high: int) -> None:
    """Why it came back, then the fixes it offers as rows of one shape (key, what it does, the
    command), fitted so that at 80×24 every key is in sight: the reason gives way first."""
    why = (store.node_log(node.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get("why", "")
    offers = [*P.offers(store, node), ("?", "ask the planner", ["ask", "…", "--about", node.id])]
    rows = [(key, _its(does, node.id), f"graphene {' '.join(argv)}") for key, does, argv in offers]
    # one line each when every one fits whole; else two each, all alike: what the key does, then the
    # command under it (at 120 columns the pane is narrow, and the commands had gone)
    one = all(5 + len(does) + 2 + len(command) <= pane.wide for _, does, command in rows)
    shaped = []
    for key, does, command in rows:
        if one:
            line = Text.assemble("  ", (key, "bold"), "  ", does)
            line.append(" " * (pane.wide - 5 - len(does) - len(command)) + command, "dim")
            shaped.append(line)
            continue
        for k, piece in enumerate(textwrap.wrap(does, pane.wide - 5, break_on_hyphens=False) or [""]):
            shaped.append(Text.assemble("  ", (key if k == 0 else " ", "bold"), "  ", piece))
        shaped.append(Text("     " + T.elide(command, pane.wide - 5), "dim"))
    used = sum(len(item[1].wrap(WRAP, pane.wide)) for item in pane.items if item[0] == "text")
    lines = max(1, high - used - len(shaped)) if high else 99
    wrapped = textwrap.wrap(" ".join(str(why).split()), pane.wide, max_lines=lines,
                            placeholder=" … (Enter: all of it)", break_on_hyphens=False)  # fmt: skip
    for line in wrapped:
        pane.text(line)
    for line in shaped:
        pane.line(line)


def _unmerged(left: dict) -> str:
    """Why a leaf that passed did not land, in a line: what git said, as a person would say it."""
    said = " ".join(str(w) for w in left.get("why") or [])
    stale = re.search(r"would be overwritten by merge:\s*(.+?)\s+(?:Please|Aborting)", said)
    if stale:
        paths = stale.group(1).split()
        has = "has" if len(paths) == 1 else "have"
        return f"{', '.join(paths)} {has} uncommitted changes in your checkout"
    conflict = re.findall(r"Merge conflict in (\S+)", said)
    if conflict:
        return f"its change to {', '.join(conflict)} conflicts with what is here"
    return said or "the merge did not go through"


def _its(does: str, node_id: str) -> str:
    """An offer as the node's own pane says it: the node is "it" there, not its id again."""
    return (
        does.replace(f"make {node_id} wait on", "wait on")
        .replace(f"{node_id}'s ", "its ")
        .replace(f"; {node_id} waits on it", ", which it waits on")
    )


def _running(pane: Pane, store, node: P.Node, s) -> None:
    """Which executor, where, what it did last and how long ago; for a session that took it itself,
    what is not known is said in a line rather than left out."""
    seen = R.live(store, node)
    label = node.executor or ""
    by_run = label.startswith("run:")
    who = P.said_by(label)
    if not by_run:
        agent = label.startswith(("claude:", "codex:", "planner"))
        who += f", {'which' if agent else 'who'} took it with graphene node start"
    pane.field("executor", who)
    pane.field("worktree", _where(node.checkout, s.root_path))
    age, colour = ago(seen.get("idle"))
    last = seen.get("last") or "nothing yet"
    last = T.elide(last, 2 * (pane.wide - 12) - len(age))  # two lines at most: what it did, then how long ago
    pane.field("last", Text.assemble(last, " · ", (age, colour)))
    if not by_run:
        pane.text(
            "its output is the session's, not Graphene's: l shows the tool calls its hooks recorded", "dim"
        )


def tail_pane(store, node: P.Node, root: Path, wide: int) -> Text:
    """`l`: what the executor printed; while it has printed nothing (claude -p prints only when it
    ends), the tool calls the hooks recorded for its session, newest last, said as such."""
    seen = R.live(store, node)
    pane = Pane(wide)
    pane.text(f"{node.id} · output of attempt {seen.get('attempt') or 1}", "bold")
    log = seen.get("log")
    if log:
        with contextlib.suppress(ValueError):
            log = str(Path(log).relative_to(root))
        pane.text(log, "dim")
    lines = R.tail(seen.get("log"), 200)
    pane.gap()
    if lines:
        for line in lines:
            pane.line(Text(line))
        return pane.render()
    calls = store.last_events(node.session_id, 60) if node.session_id else []
    if not calls:
        pane.text("nothing yet: no output, and no tool call on record", "dim")
        return pane.render()
    whose = "its log is empty until it ends" if log else "its output is the session's, not Graphene's"
    pane.text(f"{whose}; these are the tool calls the hooks recorded for it, newest last:", "dim")
    for call in calls:
        pane.line(
            Text.assemble((_clock(call["timestamp"], True), "dim"), "  ", T.elide(R.said_by(call), wide - 10))
        )
    return pane.render()


# -- the record (Enter) ------------------------------------------------------------------------------


def record_pane(store, node: P.Node, s, wide: int) -> Text:
    """A node's record, laid out: its contract, why it came back, each hold (who, when, how it
    ended, where, what changed in and outside its scope), the check Graphene ran, what was refused,
    how much of it is verified, and what people did. No command spelled out where a key does it."""
    from .node_record import _coverage_lines, node_record, rolled_up

    pane = Pane(wide)
    pane.line(fit([("record", "dim"), ("it scrolls", "dim")], wide))
    word = s.words.get(node.id) or P.reads(node, s.nodes)
    _header(pane, node, word)
    pane.gap()
    pane.text("contract", "bold")
    _why(pane, store, node, s.by_id)
    _contract(pane, store, node, s, None, None)
    kids = [c for c in P.below(node.id, s.nodes) if not s.under.get(c.id)]
    if kids:  # a sub-goal: its leaves' records added up
        pane.gap()
        pane.text("its leaves", "bold")
        for line in rolled_up(store, s.root_path, kids):
            pane.text(_plain(line.strip().removesuffix(":")), indent=2 if line.startswith("    ") else 0)
        return pane.render()
    if word == "came back":
        why = (store.node_log(node.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get("why", "")
        pane.gap()
        pane.text("came back", "bold")
        pane.field("why", str(why))
        offers = Text("\n").join(
            Text.assemble((k, "bold"), f"  {_its(what, node.id)}") for k, what, _ in P.offers(store, node)
        )
        pane.field("offers", offers)
    record = node_record(store, s.root_path, node)
    if not record.windows and not record.acts and not record.refusals.last_check:
        pane.gap()
        pane.text("nothing has happened to it yet: nobody has held it, and no check has run", "dim")
        return pane.render()
    pane.gap()
    pane.text("holds", "bold")
    if not record.windows:
        pane.text("nobody has held it yet", "dim", indent=2)
    ends = {"finished": "done", "released": "handed back", "overruled": "overruled"}
    for w in record.windows:
        pane.text(f"{w.n}  {P.said_by(w.executor)}", indent=2)
        inner = Pane(wide - 5)
        if w.ended_at:
            end = ends.get(w.ended_by, w.ended_by) + (f": {w.said}" if w.said else "")
            inner.field("when", f"{_clock(w.started_at)} → {_clock(w.ended_at)}, {end}")
        else:
            inner.field("when", f"since {_clock(w.started_at)}, held now")
        inner.field("where", _where(w.checkout, s.root_path))
        inside = [p for p in sorted(w.changed) if P.in_scope(p, record.scope)]
        outside = [p for p in sorted(w.changed) if not P.in_scope(p, record.scope)]
        inner.field("in scope", ", ".join(inside))
        inner.field("outside", ", ".join(outside), "magenta")
        if not w.changed:
            inner.field("changed", "nothing")
        for line in inner.render().split():
            pane.line(Text("     ") + line)
    check = record.refusals.last_check
    pane.gap()
    pane.text("the check", "bold")
    if check:
        colour = "green" if check["result"] == "passed" else "red"
        pane.field("command", check["command"])
        pane.field(
            "result", Text.assemble((check["result"], colour), f" at {_clock(check['at'])}, run by Graphene")
        )
    else:
        pane.text("none has run for it yet", "dim", indent=2)
    no = record.refusals
    said = [f"a write denied: {p}" for p in sorted(set(no.denied))]
    said += [f"a change refused after the fact: {p}" for p in sorted(set(no.breaches))]
    said += [f"done refused over {', '.join(stray) or 'a failing check'}" for stray in no.done]
    said += [f"{no.checks_failed} failed check{'s' * (no.checks_failed != 1)}"] if no.checks_failed else []
    pane.gap()
    pane.field("refused", "; ".join(said) or "nothing")
    coverage = [
        _plain(line.strip()) for line in _coverage_lines(record.coverage, None) if "check:" not in line
    ]
    pane.field("coverage", coverage[0].removeprefix("coverage: ") if coverage else "")
    for line in coverage[1:]:
        pane.field("", line, "dim")
    pane.gap()
    pane.text("what people did", "bold")
    if not record.acts:
        pane.text("nothing yet: nobody accepted, edited, signed off or sent it back", "dim", indent=2)
    kinds = max((len(a.kind) for a in record.acts), default=0)
    for a in record.acts:
        pane.text(f"{_clock(a.at)}  {a.kind.replace('_', ' ').ljust(kinds)}  {P.said_by(a.actor)}"
                  + (f": {a.said}" if a.said else ""), indent=2)  # fmt: skip
    return pane.render()


def _plain(line: str) -> str:
    """A line of the record's own text as the pane says it: what it calls a window is a hold here,
    and the key that shows a leaf's record is on the status line, not spelled out as a command."""
    line = line.replace("; each has its own: `graphene node show <id>`", "; Enter on one shows its own")
    return line.replace("windows", "holds").replace("window", "hold").replace("`", "")


def run(root: Path, open_store: Callable, every: float = 1.0) -> None:
    Watch(root, open_store, every).run()
