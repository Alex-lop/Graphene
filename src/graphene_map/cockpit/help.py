"""`?`: the keys, on one screen of 80 by 24. Every key is a `graphene` command; the line under the rows says
which one ran, and the words on a row are buttons you can click. A replay shows its own keys and the ones
that work in it."""

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
        ("⏎ y", "the row's own move: the default, accept, sign off, try again"),
        ("1-9 a", "pick that option; answer in your own words"),
        ("d A", "drop a proposal or a question; accept every proposal"),
    )),
    ("agents", (
        ("t", "tell its agent one line: it hears it with its next write"),
        ("w", "widen: give the task the path the gate stopped"),
        ("x", "hand back a running task; reopen a finished one (say why)"),
        ("b n r", "came back: a new task, wait on another, reopen the one named"),
        ("r R s", "run this task, or every ready one; s: the planner splits one"),
    )),
    ("plan", (
        ("e E", "edit the task, or the whole plan, in your $EDITOR"),
        ("P u", "plan first: on, auto, off; undo your last act"),
        ("D", "the direction: the goals above this plan"),
    )),
    ("screens", (
        ("j k", "move; ← → the task on the map, the box on the graph"),
        ("i", "details: the task's contract, output, changes and record"),
        ("c g m", "the cockpit, the graph, the map; Tab goes on, Esc comes back"),
        ("v p", "on the map: v changes the lens, p paints a folder to a task"),
    )),
    ("anything", (("`:`", "any graphene command (:stop stops runs, :ask a sentence)"),
                  ("q", "quit; a run started here goes on"))),
    ("marks", (("", "● running  ◆ sign-off  ↩ came back  ○ ready  ◌ waiting"),
               ("", "+ proposed  ✓ proven  ◇ yours  ? a question  ! a risk"),
               ("", "✎ files written of allowed  ✓ checks  ⏸ quiet  ▁▃▅ activity"))),
)  # fmt: skip
INDENT = 16  # the group name and the key, before the words
END = "A row's words are buttons. The keys' commands call a task a leaf."


def help_text(width: int, groups: tuple = GROUPS, end: str = END) -> Text:
    """The keys of ``groups``, one row each, in ``width`` columns: words that do not fit wrap under
    themselves. ``end`` is the line under them."""
    out = Text()
    for name, keys in groups:
        for k, (key, what) in enumerate(keys):
            first, *more = textwrap.wrap(what, max(width - INDENT, 20)) or [""]
            out.append(f" {name if k == 0 else '':<9}", style="bold #4cc9f0")
            out.append_text(Text.assemble((key.strip("`").ljust(6), "bold"), (first, "grey70")))
            for line in more:
                out.append("\n" + " " * INDENT + line, style="grey70")
            out.append("\n")
    out.append("\n " + end, style="grey50")
    return out


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", show=False), Binding("q", "close", show=False),
                Binding("question_mark", "close", show=False), Binding("j", "scroll(1)", show=False),
                Binding("k", "scroll(-1)", show=False)]  # fmt: skip
    AUTO_FOCUS = "VerticalScroll"  # the arrows and PageDown scroll it, where it is taller than the screen

    def __init__(self, groups: tuple = GROUPS, end: str = END) -> None:
        super().__init__()
        self.groups, self.end = groups, end  # a replay's: its own keys, and only the ones that work in it

    DEFAULT_CSS = """
    Help { align: center middle; }
    Help > VerticalScroll { width: 96; max-width: 100%; height: auto; max-height: 100%;
                            background: #14171d; border: round #4cc9f0; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(help_text(max(min(96, self.app.size.width) - 4, 40), self.groups, self.end))

    def action_scroll(self, lines: int) -> None:
        self.query_one(VerticalScroll).scroll_relative(y=lines, animate=False)

    def action_close(self) -> None:
        self.dismiss(None)
