"""`?`: the keys, on one screen of 80 by 24. Every key is a `graphene` command; the line under the rows says
which one ran, and the words on a row are buttons you can click."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

GROUPS = (
    ("move", (("j k", "down, up the rows"), ("← →", "the task (territory), the box (graph)"))),
    ("answer", (
        ("⏎", "take what waits for you: a default, a proposal, a sign-off, a leaf to try again"),
        ("1-9", "pick that option"), ("a", "answer in your own words"),
        ("d", "drop a proposal or a question"),
    )),
    ("agents", (
        ("t", "tell it one line: it hears it with its next write"),
        ("w", "give it the path the gate stopped (a leaf that came back also offers b n r)"),
        ("x", "hand a running agent back; reopen a finished one with what is wrong"),
        ("r R", "run this leaf; run every ready one"),
    )),
    ("screens", (
        ("c g m", "cockpit, graph of the plan, map of the folders each task may write; Tab goes on"),
        ("v p", "the map's lens (plan, live, changed); paint a folder to the selected task"),
    )),
    ("anything", ((":", "any graphene command as typed (:stop stops the runs, :ask what you want)"),
                  ("q", "quit; a run started here goes on"))),
)  # fmt: skip


def help_text(width: int) -> Text:
    out = Text()
    for name, keys in GROUPS:
        out.append(f" {name}\n", style="bold #4cc9f0")
        for key, what in keys:
            line = Text.assemble(("   " + key.ljust(6), "bold"), (what, "grey70"))
            out.append_text(line)
            out.append("\n")
    closing = "\n a row's words are buttons: click them. Every key is a graphene command, and the line\n"
    out.append(closing + " under the rows says which one ran.", style="grey50")
    return out


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", show=False), Binding("q", "close", show=False),
                Binding("question_mark", "close", show=False)]  # fmt: skip
    DEFAULT_CSS = """
    Help { align: center middle; }
    Help > VerticalScroll { width: 84; max-width: 100%; height: auto; max-height: 100%;
                            background: #14171d; border: round #4cc9f0; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static(help_text(80))

    def action_close(self) -> None:
        self.dismiss(None)
