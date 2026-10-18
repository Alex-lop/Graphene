"""`?`: the keys, on one screen of 80 by 24. Every key is a `graphene` command; the line under the rows says
which one ran, and the words on a row are buttons you can click."""

from __future__ import annotations

import textwrap

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

GROUPS = (
    ("answer", (
        ("⏎ y", "take what waits for you: default, proposal, sign-off, retry"),
        ("1-9", "pick that option"), ("a", "answer in your own words"),
        ("d", "drop a proposal or a question"),
    )),
    ("agents", (
        ("t", "tell it one line: it hears it with its next write"),
        ("w", "give it the path the gate stopped"),
        ("b n", "a leaf that came back: write a sibling, or wait on another"),
        ("x", "hand a running agent back; reopen a finished one (say why)"),
        ("r R", "run this leaf (or reopen its owner); run every ready one"),
        ("s", "the planner splits a leaf still to do"),
    )),
    ("plan", (
        ("e E", "edit the task, or the whole plan, in your $EDITOR"),
        ("P u", "plan first: on, auto, off; undo your last act"),
        ("D", "the direction above your plans"),
    )),
    ("screens", (
        ("j k", "move; ← → the task on the map, the box on the graph"),
        ("i", "everything about the row: contract, output, changes, record"),
        ("c g m", "the cockpit, the graph, the folder map; Tab goes on"),
        ("v p", "on the map: v changes the lens, p paints a folder to a task"),
    )),
    ("anything", (("`:`", "any graphene command (:stop stops runs, :ask a sentence)"),
                  ("q", "quit; a run started here goes on"))),
)  # fmt: skip
INDENT = 16  # the group name and the key, before the words


def help_text(width: int, extra: tuple = ()) -> Text:
    """Every key, one row each, in ``width`` columns: words that do not fit wrap under themselves."""
    out = Text()
    for name, keys in (*extra, *GROUPS):
        for k, (key, what) in enumerate(keys):
            first, *more = textwrap.wrap(what, max(width - INDENT, 20)) or [""]
            out.append(f" {name if k == 0 else '':<9}", style="bold #4cc9f0")
            out.append_text(Text.assemble((key.strip("`").ljust(6), "bold"), (first, "grey70")))
            for line in more:
                out.append("\n" + " " * INDENT + line, style="grey70")
            out.append("\n")
    closing = "\n A row's words are buttons: click them. Every key is a graphene command;\n"
    out.append(closing + " the line under the rows says which one ran.", style="grey50")
    return out


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", show=False), Binding("q", "close", show=False),
                Binding("question_mark", "close", show=False), Binding("j", "scroll(1)", show=False),
                Binding("k", "scroll(-1)", show=False)]  # fmt: skip
    AUTO_FOCUS = "VerticalScroll"  # the arrows and PageDown scroll it, where it is taller than the screen

    def __init__(self, extra: tuple = ()) -> None:
        super().__init__()
        self.extra = extra  # groups a screen adds in front (a replay's)

    DEFAULT_CSS = """
    Help { align: center middle; }
    Help > VerticalScroll { width: 96; max-width: 100%; height: auto; max-height: 100%;
                            background: #14171d; border: round #4cc9f0; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(help_text(max(min(96, self.app.size.width) - 4, 40), self.extra))

    def action_scroll(self, lines: int) -> None:
        self.query_one(VerticalScroll).scroll_relative(y=lines, animate=False)

    def action_close(self) -> None:
        self.dismiss(None)
