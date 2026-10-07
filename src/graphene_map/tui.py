"""`graphene watch`: the plan on one screen, with vim keys.

A view over commands and text, never the only way to do anything: every key runs a `graphene`
command that exists on its own (the bottom line says which), editing opens the plan's text in the
person's $EDITOR, and a run or a planner started from here is its own process, which goes on when
this screen is closed. The left pane is the tree, the goal its first row; the right one (below it,
when the terminal is narrow) is the node under the cursor. A row reads the same everywhere (the
tree, the node pane, `graphene plan`): glyph, title cut at a word, id, and the word its state reads
as (`plan.reads`), in the colour of who has the move (`plan.look`). Under a leaf the Nemotron
executor forked, each fork is a row in the same grammar (its model, which fork, its state); a fork
is not a node, and a key on its row acts on its leaf. The top line says whose plan this is in the
words every write ends with; the bottom two say what waits on the person and the two clocks, and
what the last key did (or a step up the ladder, once) or what the keys do on the node under the
cursor. Above them, each leaf an executor runs has a row of what its meter reads (`meter.py`).
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
from datetime import UTC, datetime
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

from . import board_rows as BR
from . import direction as D
from . import meter as M
from . import plan as P
from . import plan_text as T
from . import run as R
from . import views as V
from .node_record import bill, forks, models, sandbox
from .views import money

RUN_WITH = "--parallel 4"  # `R` and `r`: ready leaves at once, a worktree each, landed here as they pass
WIDE = 110  # columns: from here the node pane sits beside the tree, below it under the tree
HELP_WIDE = 72  # a help row's columns: from twice this the groups sit in two columns
PANE = 44  # beside the tree, the node pane keeps at least this many columns
QUIET = 120  # seconds without a sign of life before a running leaf reads "quiet for n min"
METERED = 4  # the running leaves the meter's strip has rows for: the rest are counted
WRAP = Console(width=400, color_system=None)  # only for Text.wrap: styled text wrapped at words

HELP = (  # what answering the board needs first: at 80x24 the first screen ends inside "run"
    ("move", (
        ("j k", "down, up"), ("gg G / n", "the goal, the last row; search, the next match"),
        ("Esc", "ends a search, a selection, a pane"),
        ("Tab", "the next view that fits (graphene watch --view)"),
        ("h l", "in a view: the node to the left, to the right"),
    )),
    ("board", (("y 1..9", "take the default, confirm, agree; pick one"),
               ("d p", "drop it; park it (p again: unpark)"), ("Enter a", "answer in your words; a note"))),
    ("shape", (
        ("y d", "accept, sign off, it is done; drop"), ("e E", "edit it in $EDITOR; with what is under it"),
        ("a A s", "add a sibling, a child; the planner splits it"),
        ("?", "ask the planner why, split, merge, another way"),
        ("+ -", "the plan asked again, finer, coarser"), ("V u", "select several, then y or d; undo"),
        ("m", "mark all seen: then + and ~ show what changed"),
    )),
    (":", ((":<command>", "any graphene command (:ask, :stop, :node set)"),
           ("q", "quit; a run started here goes on"))),
    ("fold", (("za zo zc", "fold or unfold, unfold, fold (on the goal: all)"),
              ("zR zM zx", "all open, all closed, as it opened"))),
    ("run", (("R r", "run every ready leaf; the ready ones under this"),
             ("x", "release it; send it back; reopen it"), ("P", "plan first: on, auto, off"))),
    ("see", (("Enter l D", "the record; the executor's output; the direction"),
             ("ctrl-d -u", "scroll the pane"))),
    ("came back", (("w b n", "widen its scope; a sibling first; wait on those"),
                   ("?", "ask the planner what would let it be done"))),
)  # fmt: skip
HELP_END = (
    "The status line counts agents: what runs, its minutes, its dollars at list price; and you: your acts "
    "and their minutes, by your keys, not by what you read. Every key is a graphene command. The bottom "
    "line says which it ran."
)
# the glyphs and colours every row, view and pane uses, the help's first line
LEGEND = ("yours", "review", "came back", "proposed", "ready", "running", "waiting", "done")
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
FOLDED = 20  # the columns a folded row's count of states takes, as a rule: whole states, the rest "n more"
WHOSE = ("came back", "review", "yours", "proposed", "running", "ready", "waiting", "to fill in", "done")
# A fork's words (executor.Fork.outcome), its glyph and its colour, whose move as a node's are: running is
# the executor's, passed is done work, and a fork that ended any other way is nobody's move (dim): what
# is next is its leaf's row, which came back to the person when every fork failed
FORK = {"passed": ("✓", "green"), "lost": ("·", "dim"), "check failed": ("✗", "dim"), "gave up": ("↩", "dim"),
        "no tool call": ("·", "dim"), "out of steps": ("·", "dim"), "stopped": ("·", "dim")}  # fmt: skip


def _look(word: str) -> tuple[str, str]:
    return FORK.get(word) or BR.LOOK.get(word) or P.look(word)  # board: an item's word


def _short(model: str) -> str:
    return model.rsplit("/", 1)[-1]  # a model's name, as the bill says it


def direction_text(said: list[tuple[str, str]]) -> Text:
    """Rows of the direction (`direction.lines`), each glyph in its row's colour."""
    text = Text()
    for k, (line, style) in enumerate(said):
        row = Text(("\n" if k else "") + line)
        glyph = len(row.plain) - len(row.plain.lstrip("\n "))
        row.stylize(style, glyph, glyph + 1)
        text.append_text(row)
    return text


def direction_pane(store, root: Path, wide: int) -> Text:
    """What D shows: `graphene direction`'s print at the pane's width, from the store as it is now."""
    try:
        d = D.read(root)
    except P.Refused as no:
        return Text(str(no))
    st = D.status(store, d)
    said = [(D.head(st, P.where(root), wide), "bold"), *D.lines(st, wide)]
    if d is None:
        said.insert(1, (D.EMPTY, "dim"))
    return direction_text(said)


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


def row(
    glyph: str, word: str, title: str, node_id: str, wide: int, ids: int, words: int, bold=False, inside="",
    least=4, mark="",
) -> Text:
    """One row: glyph, the title cut at a word, the id (dim) and the state word in its colour, in
    fixed columns so ids line up with ids and words with words, whatever the depth. ``wide`` is
    what the row may take; an id is never cut, the title gives way, to ``least`` columns. ``inside``:
    a folded row's count of its leaves by state, in the word's column, each state in its own colour.
    ``mark``: `+` or `~` in the gap before the id, when it changed since the person last looked."""
    colour = _look(word or glyph)[1]  # board: its fold row has no word, and its glyph's colour
    title_w = max(wide - 2 - (2 + ids if ids else 0) - (2 + words), least)
    if not node_id:  # the goal's row: no id, so its title takes the id's column too
        title_w += 2 + ids if ids else 0
    out = Text()
    out.append(f"{glyph} ", colour)
    out.append(T.elide(title, title_w).ljust(title_w), "bold" if bold else "")
    if ids and node_id and mark:
        out.append(" ")
        out.append(mark, "bold")
        out.append(node_id.ljust(ids), "dim")
    elif ids and node_id:
        out.append(f"  {node_id.ljust(ids)}", "dim")
    if not inside:
        out.append(f"  {word.ljust(words)}", colour)
        return out
    out.append("  ")
    for k, piece in enumerate(inside.split(", ")):  # `1 came back`: the state after the count, its colour
        out.append(", " if k else "")
        out.append(piece, P.look(piece.partition(" ")[2])[1])
    out.append(" " * (words - len(inside)))
    return out


def inside(words: list[str]) -> str:
    """What a folded row says in its word's column: how many leaves are inside and in which states,
    whose move first (`1 came back, 4 more`, `12 done`), as many whole states as fit FOLDED; the
    rest is counted, never cut."""
    order = sorted(set(words), key=lambda w: WHOSE.index(w) if w in WHOSE else len(WHOSE))
    counts = [(words.count(w), w) for w in order]
    for k in range(len(counts), 0, -1):
        rest = sum(n for n, _ in counts[k:])
        said = ", ".join([f"{n} {w}" for n, w in counts[:k]] + ([f"{rest} more"] if rest else []))
        if len(said) <= FOLDED or k == 1:
            return said
    return ""


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


def elapsed(seconds: int) -> str:
    """A running time as a clock reads it, to the second: `12s`, `6m12s`, `1h04m`."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"


def tokens(n: int) -> str:
    """A count of tokens, short: `950`, `9k`, `412k`, `1.2M`."""
    return str(n) if n < 1000 else f"{n // 1000}k" if n < 1_000_000 else f"{n / 1_000_000:.1f}M"


def _s(n: int, word: str) -> str:
    return f"{n} {word}{'s' * (n != 1)}"


def live_row(node_id: str, a: dict, seen: dict, room: int, one: bool) -> list[Text]:
    """A running leaf in the meter's strip, from its attempt (`meter.attempts`) and what `run.live` saw:
    in one row from WIDE columns, the pieces whole and the least wanted dropped off the end; else two,
    who and how much over what it did last. A leaf whose executor writes no stream the meter reads says
    "no meter" where its numbers would be, and what its log said last."""
    glyph, colour = P.look("running")
    model = _short(a["model"]).removeprefix(f"{a['executor']}-") if a.get("model") else ""
    who = " ".join(filter(None, [a["executor"], model]))
    age = ago(seen.get("idle"))
    last = seen.get("last") or "nothing yet"
    attempt = f"attempt {a['attempt'] or 1}"
    if a["meter"]:
        out = len(a["files_out"])
        files = _s(len(a["files_in"]) + out, "file") + (f", {out} outside" if out else "")
        spent = money(a["dollars"]) if a["priced"] else "no list price"
        said = f"{tokens(a['prompt_tokens'])} in, {tokens(a['completion_tokens'])} out"
        numbers = [(spent, ""), (_s(a["turns"], "turn"), ""), (files, ""), (said, "dim")]
        if not (a["turns"] or a["prompt_tokens"] or a["dollars"]):  # Codex says its usage only as it ends
            numbers = [("no usage yet", "dim"), (files, "")]
    else:
        numbers = [("no meter", "dim")]
    head = [(f"{glyph} {node_id}", colour), (who, ""), (elapsed(a["seconds"]), "")]
    if one:
        last = T.elide(last, max(room // 3, 12))
        rest = [*numbers[:1], (last, ""), age, *numbers[1:], (attempt, "dim")]
        return [fit([*head, *rest], room)]
    last = T.elide(last, max(room - 2 - len(age[0]) - 3, 12))
    first = fit([*head[:2], (attempt, "dim"), head[2], *numbers[1:2], *numbers[:1]], room)
    return [first, Text("  ") + fit([(last, ""), age, *numbers[2:]], room - 2)]


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

    def __init__(self, prompt: str, value: str = "", about: str = "") -> None:
        super().__init__()
        self.prompt, self.value, self.about = prompt, value, about

    def compose(self) -> ComposeResult:
        line = Input(value=self.value, placeholder=self.prompt, id="ask")
        line.border_title = self.about  # what the line is about, when the prompt has no room for it
        yield line

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

    @on(Input.Changed)
    def at_once(self, event: Input.Changed) -> None:
        """A line that offers `? help` opens it on the one key, as ? does everywhere else."""
        if event.value == "?" and "? help" in self.prompt:
            self.dismiss("?")

    def action_cancel(self) -> None:
        self.dismiss(None)


def legend(wide: int) -> Text:
    """The glyphs and colours, one line: what each state reads as, and the graph's heavy line; where
    the words do not fit, the person's move (magenta: yours, review, came back) as one."""
    looks = [(P.look(w)[0], P.look(w)[1], w) for w in LEGEND]
    short = [("".join(g for g, _, _ in looks[:3]), P.look("yours")[1], "yours"), *looks[3:]]
    for form in (looks, short):
        out = Text()
        for glyph, colour, word in form:
            out.append(glyph, colour).append(f" {word}  ")
        out.append("━", "bold").append(" critical path" if form is looks else " critical")
        if out.cell_len <= wide or form is short:
            return out
    return out


def help_text(groups, wide: int) -> Text:
    """The keys, a row each: the group's name on its first row, the keys, what they do, cut at a word
    rather than wrapped, so a group is as tall as its keys. A setting too long for its row names a
    command's files without their directories (`python3 planner.py`), before it is cut."""
    out = Pane(wide)
    names = max(len(name) for name, _ in groups) + 2
    keys = max(len(k) for _, rows in groups for k, _ in rows) + 2
    for name, rows in groups:
        for k, (key, what) in enumerate(rows):
            head = (name if k == 0 else "").ljust(names)
            if len(what) > wide - names - keys:
                what = re.sub(r"(?<!\S)[/~]\S*/", "", what)
            what = T.elide(what, wide - names - keys)
            out.line(Text.assemble((head, "dim"), (key.ljust(keys), "bold"), what))
    return out.render()


def help_groups(settings: list[str] = ()) -> tuple:
    """HELP, less the keys of the views when the outline is the only one, then the settings
    (`settings.lines_for_screen`), a row each, as `graphene config` shows them."""
    groups = HELP
    if len(V.VIEWS) <= 1:
        groups = tuple((name, tuple(r for r in rows if r[0] not in ("Tab", "h l"))) for name, rows in HELP)
    said = [tuple(line.split(": ", 1)) for line in settings[:-1] if ": " in line]
    return (*groups, ("settings", tuple(said))) if said else groups


class Help(ModalScreen[None]):
    """The keys, grouped as the README groups them: two columns from 110 columns, one below."""

    BINDINGS = [
        Binding("escape,q,question_mark", "app.pop_screen", show=False),
        Binding("j,down", "scroll(1)", show=False),
        Binding("k,up", "scroll(-1)", show=False),
        Binding("ctrl+d", "scroll(8)", show=False),
        Binding("ctrl+u", "scroll(-8)", show=False),
        Binding("G,end", "edge(True)", show=False),
        Binding("g,home", "edge(False)", show=False),  # gg is two of it
    ]
    DEFAULT_CSS = """
    Help { align: center middle; }
    Help > VerticalScroll {
        width: auto; max-width: 100%; height: auto; max-height: 100%;
        border: round $primary; background: $surface; padding: 0 1; scrollbar-size-vertical: 1;
    }
    Help #help { width: auto; height: auto; }
    Help #help > Static { width: auto; padding: 0 1; }
    Help #end { width: auto; padding: 0 1; color: $text-muted; }
    Help #legend { width: auto; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        from .settings import lines_for_screen

        width = self.app.size.width
        said = self.app.read(lines_for_screen, []) if hasattr(self.app, "read") else []
        groups = getattr(self.app, "help_groups", help_groups)(said)  # a replay's: its own keys first
        two = width >= 2 * HELP_WIDE + 10
        column = HELP_WIDE if two else max(width - 8, 30)
        with VerticalScroll() as box:
            box.border_subtitle = "Esc closes this · j k G gg scroll"  # on the border: in sight when scrolled
            yield Static(legend(column * (2 if two else 1)), id="legend")
            with Horizontal(id="help"):
                if two:
                    yield Static(help_text(groups[:5], column))
                    yield Static(help_text(groups[5:], column))
                else:
                    yield Static(help_text(groups, column))
            end = getattr(self.app, "HELP_END", HELP_END)
            end = f"{end} {said[-1]}." if said else end
            yield Static(Text("\n".join(textwrap.wrap(end, column * (2 if two else 1)))), id="end")

    def action_scroll(self, lines: int) -> None:
        self.query_one(VerticalScroll).scroll_relative(y=lines, animate=False)

    def action_edge(self, end: bool) -> None:
        box = self.query_one(VerticalScroll)
        (box.scroll_end if end else box.scroll_home)(animate=False)


def _ahead(app, event, pending: str) -> bool:
    """A key the outline or a view takes before its own bindings: one queued before a prompt it opened
    was up, one typed after `:` or `/` before the line took the keyboard, or one that asks for words.
    True when it was taken."""
    if isinstance(app.screen, Ask):  # queued here before the prompt a key opened was up
        app.screen.typed(event)
        return True
    line = app.query_one("#line", Input)
    if line.has_class("-open") and not line.has_focus:  # typed after : or /, before the line took focus
        event.stop()
        event.prevent_default()
        if event.key == "enter":
            app.submit_line()
        elif event.key == "escape":
            app.action_escape()
        elif event.key == "backspace":
            line.value = line.value[:-1]
        elif event.is_printable and event.character:
            line.value += event.character
        line.cursor_position = len(line.value)
        return True
    char = event.character or ""
    if char in (":", "/", "a", "A", "x") and not pending:
        # opened here, at once: an app binding's action runs after the keys a terminal sent with
        # it, and `:plan log` typed in one burst ran l and a on the tree before the line opened;
        # `A` and a title typed at once ran the title's d and y. A key that asks for words acts now
        event.stop()
        event.prevent_default()
        opens = {":": lambda: app.action_line(":"), "/": lambda: app.action_line("/"),
                 "a": lambda: app.action_add(False), "A": lambda: app.action_add(True),
                 "x": app.action_release_or_reopen}  # fmt: skip
        opens[char]()
        return True
    return False


class PlanView(VerticalScroll):
    """A view of the plan other than the outline (a graph), where the outline goes: the lines the
    view drew, and a cursor on its nodes' cells that every key acts on, as on the outline's rows. j k
    walk the view's reading order, h l go to the nearest cell left or right, gg G the first and the
    last; folding is the outline's, so z and what follows it do nothing here."""

    BINDINGS = [
        Binding("j,down", "app.step(1)", show=False),
        Binding("k,up", "app.step(-1)", show=False),
        Binding("h,left", "app.beside(-1)", show=False),
        Binding("l,right", "app.beside(1)", show=False),
        Binding("G", "app.end(-1)", show=False),
        Binding("enter", "app.record", show=False),
        Binding("tab", "app.next_view", show=False),
    ]
    pending = ""

    def compose(self) -> ComposeResult:
        yield Static(id="drawn", markup=False)

    async def on_key(self, event) -> None:
        if _ahead(self.app, event, self.pending):
            return
        char = event.character or ""
        if self.pending or char in ("g", "z"):
            sequence, self.pending = self.pending + char, "" if self.pending else char
            event.stop()
            event.prevent_default()
            if sequence == "gg":
                self.app.action_end(0)

    def on_click(self, event) -> None:
        """A click on a node's cell puts the cursor there; on the first line, the goal's, on the goal."""
        spot = event.get_content_offset(self.query_one("#drawn"))
        drawn = self.app.drawn
        if spot is None or drawn is None:
            return
        if spot.y == 0:
            self.app.go(None)
        for node_id, (line, first, last) in drawn.at.items():
            if line <= spot.y < line + drawn.tall and first <= spot.x <= last:
                self.app.go(node_id)


class PlanTree(Tree[str]):
    """The tree, with vim's movement and folding, and every row in the row grammar at the width the
    tree has. Two-key sequences (gg, za, …) are read here, so the `a` of `za` never adds a node; so
    are keys typed after `:` or `/` before the line has taken the keyboard."""

    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("G", "scroll_end_node", show=False),
        Binding("enter", "app.record", show=False),
        Binding("tab", "app.next_view", show=False),
    ]
    CHORDS = {
        "gg": "top",
        "za": "toggle_here",
        "zo": "open",
        "zc": "close",
        "zR": "open_all",
        "zM": "close_all",
        "zx": "app.fold_as_opened",
    }
    pending = ""
    rows: dict = {}  # a node's data (None: the goal) -> (glyph, word, title, id, bold, inside when folded)
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
        glyph, word, title, node_id, bold, folded = said
        # a fork's row is a level below its leaf's: its title (the model's name) gives way further, so
        # its id and word stay in their columns as deep as its leaf's do
        least = 1 if isinstance(node.data, tuple) else 4
        mark = self.app.mark(node)
        label = row(glyph, word, title, node_id, wide - 2, self.ids, self.words, bold, folded, least, mark)
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
        if _ahead(self.app, event, self.pending):
            return
        char = event.character or ""
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

    RUNS_HERE = True  # R runs and P switches plan first; a replay says neither
    METERS = True  # the meter's strip, above the bottom lines

    CSS = """
    Screen { layout: vertical; }
    #where { height: 1; background: $boost; color: $text; padding: 0 1; }
    #direction { height: auto; max-height: 4; padding: 0 1; }  /* direction: the path above the plan */
    #main { height: 1fr; layout: horizontal; }
    #tree { width: 1fr; min-width: 30; overflow-x: hidden; scrollbar-size-vertical: 1; padding-right: 1; }
    #side { width: 1fr; border-left: solid $primary; padding: 0 1; scrollbar-size-vertical: 1; }
    Screen.-narrow #main { layout: vertical; }
    #view { width: 1fr; display: none; overflow-x: hidden; scrollbar-size-vertical: 1; padding-right: 1; }
    #drawn { width: auto; }
    Screen.-narrow #tree, Screen.-narrow #view { height: 3fr; width: 100%; }
    Screen.-narrow #side { height: 1fr; width: 100%; border-left: none; border-top: solid $primary; }
    #main.-stacked { layout: vertical; }
    #main.-stacked #view { width: 100%; }
    #main.-stacked #side { height: 1fr; width: 100%; border-left: none; border-top: solid $primary; }
    #side.-alone, Screen.-narrow #side.-alone { border-left: none; border-top: none; }
    #meter { height: auto; background: $boost; padding: 0 1; display: none; }  /* rows for running leaves */
    #status { height: 2; background: $boost; padding: 0 1; }  /* 3 while a command has spoken */
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
        Binding("D", "direction", show=False),  # direction: the tree above the plans, in the pane
        Binding("m", "seen", show=False),
        Binding("plus", "reask('finer')", show=False),
        Binding("minus", "reask('coarser')", show=False),
        Binding("ctrl+d", "page(1)", show=False),
        Binding("ctrl+u", "page(-1)", show=False),
        # board: on an item p parks it and 1..9 picks an option (y d a Enter answer it too, see action_board)
        Binding("p", "board('p')", show=False),
        *(Binding(str(n), f"board('{n}')", show=False) for n in range(1, 10)),
    ]

    def __init__(self, root: Path, open_store: Callable, every: float = 1.0, view: str | None = None) -> None:
        super().__init__()
        self.root_path, self.open_store, self.every = root, open_store, every
        self.wanted = view  # the view asked for (`--view`); None: the repository's `view` setting
        self.showing: str | None = None  # the view where the outline goes: "outline", or one in views.VIEWS
        self.drawn: V.Drawn | None = None  # that view as last drawn; None while the outline shows
        self.here: str | None = None  # the node under that view's cursor; None: its first line, the goal
        self.mapped: tuple[str, str] | None = None  # a node the view has no cell for, and its stand-in
        self.goal_text = ""
        self.view = "contract"  # or "tail", "record", "said": what the side pane shows for the selected node
        self.message = ""  # what the last command said: the bottom line's, until the cursor moves
        self.busy = ""  # why the last look at the plan failed; the next tick tries again
        self.search = ""
        self.anchor: int | None = None  # the line visual selection started on
        self.shape: object = None  # what the tree was last built from: rebuilt only when it changed
        self.runs: list[subprocess.Popen] = []
        self.known: set[str] = set()
        self.complete: set[str] = set()  # the sub-goals whose leaves were all done when the tree was built
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
        self.forks: dict[str, list[dict]] = {}  # a leaf's forks in its last attempt: rows under it
        self.heard: set = set()  # the steps up the ladder the bottom line has said
        self.board = BR.Board()  # board: the items shown as rows above the tree
        self.opened: list[str] = []  # board: the open items' ids when the tree was last built
        self.skips: set[tuple[str, int]] = set()  # the views Tab went past, and at what width, said once
        self.billed: dict[str, str] = {}  # what each leaf an executor held spent and took (views.billed)
        self.metered = 0  # the rows the meter's strip takes

    # -- the screen ----------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(id="where")
        yield Static(id="direction", markup=False)
        with Horizontal(id="main"):
            tree = PlanTree("the plan", id="tree")
            tree.show_root = False  # until there is a plan: then the goal is its first row
            tree.guide_depth = 2
            tree.rows = {}
            yield tree
            yield PlanView(id="view")
            with VerticalScroll(id="side"):
                yield Static(id="detail", markup=False)
        yield Static(id="meter", markup=False)
        yield Static(id="status", markup=False)
        yield Input(id="line", select_on_focus=False)  # else the first key typed replaces the ":"

    def on_mount(self) -> None:
        self.refresh_plan()
        self.call_after_refresh(self.refresh_plan)  # the panes have their sizes now
        self.set_interval(self.every, self.refresh_plan)
        self.set_interval(0.5, self.terminal_gone)

    def terminal_gone(self) -> None:
        """A terminal that closed without the hangup ends the screen as `q` does (``P.terminal_closed``):
        Textual would read its end of file as no key, again and again, at full speed, forever."""
        if not self.is_headless and P.terminal_closed():
            self.exit()

    def on_resize(self) -> None:
        if self.shape is not None:
            self.refresh_plan()

    @property
    def tree(self) -> PlanTree:
        return self.query_one("#tree", PlanTree)

    def selected(self) -> str | None:
        """The node under the cursor; on a fork's row, its leaf: every key acts on the leaf there. In a
        view, the node under the view's cursor."""
        if self.drawn is not None:
            return self.here
        node = self.tree.cursor_node
        return _node(node.data) if node is not None else None

    def on_goal(self) -> bool:
        if self.drawn is not None:  # a view's first line is the goal's: no node under the cursor
            return self.here is None
        return self.tree.show_root and self.tree.cursor_node is self.tree.root

    def stops(self) -> list[str | None]:
        """Where j and k stop in a view: the goal (None), then the view's reading order."""
        return [None, *(self.drawn.order if self.drawn is not None else [])]

    def word(self, node_id: str | None) -> str:
        return self.words.get(node_id or "", "")

    def chosen(self) -> list[str]:
        """The nodes a key acts on: the visual selection, else the one under the cursor. In a view the
        selection runs along the view's reading order."""
        if self.anchor is None:
            return [i for i in [self.selected()] if i]
        if self.drawn is not None:
            stops = self.stops()
            low, high = sorted((self.anchor, stops.index(self.here) if self.here in stops else self.anchor))
            return [i for i in stops[low : high + 1] if i is not None]
        low, high = sorted((self.anchor, self.tree.cursor_line))
        out = []
        for line in range(low, high + 1):
            node = self.tree.get_node_at_line(line)
            if node is not None and node.data and _node(node.data) and _node(node.data) not in out:
                out.append(_node(node.data))  # a board row is no node: skipped
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
        tries again. A tick that lands once the app has stopped running draws nothing: its widgets may
        already be gone (a test harness tears an app down without the exit that stops its timers)."""
        if not self.is_running:
            return
        try:
            with self.open_store() as store:
                self.draw(store)
            self.busy = ""
        except (sqlite3.Error, OSError) as no:
            self.busy = f"✗ the plan's store did not open ({no}); the screen is as it was, and tries again"
        self.say_status()

    def draw(self, store) -> None:
        nodes = V.shown(store)
        self.board = BR.read(store, shown=bool(self.board.open or self.board.folded))  # rows stay once seen
        goal, proposed = P.goal(store), store.meta("goal:proposed")
        by_id = {n.id: n for n in nodes}
        under = P.kids(nodes, drawn=True)
        self.nodes, self.by_id, self.under = nodes, by_id, under
        self.back = {n.id for n in nodes if P.came_back(store, n)}
        self.offered = {i: [k for k, _, _ in P.offers(store, by_id[i])] for i in self.back}
        self.words = {n.id: P.reads(n, nodes, self.back) for n in nodes}
        leaves = P.counted(nodes)  # what `graphene` counts: "3 leaves, 0 done" is "0/3 done" here
        done = sum(n.state == P.DONE for n in leaves)
        tops = [
            n
            for n in nodes
            if n.state == P.PROPOSED and (n.parent not in by_id or by_id[n.parent].state != P.PROPOSED)
        ]
        yours = [i for i, w in self.words.items() if w in ("came back", "review", "yours")]
        logs: dict[str, list[dict]] = {}
        for e in store.node_log(kinds=("started", "model", "fork")):  # what the Nemotron executors noted
            logs.setdefault(e["node_id"], []).append(e)
        held = [
            n
            for n in nodes
            if n.state in (P.RUNNING, P.DONE, P.REVIEW)
            or n.id in self.back
            or (n.id in logs and P.let_go(store, n).get("stopped"))  # its forks read stopped
        ]
        self.forks = {n.id: mine for n in held if (mine := forks(logs.get(n.id, []), n.state))}
        # a step up the ladder is news: the bottom line says it once, while its leaf runs, and only when
        # nothing else is said there; one that is not said yet waits for the line to be free
        for n in held:
            step = (models(logs.get(n.id, [])) or [{}])[-1]
            news = (n.id, n.started_at, step.get("attempt"))
            if n.state == P.RUNNING and step.get("from") and news not in self.heard and not self.message:
                self.heard.add(news)
                self.message = f"{n.id} stepped up to {_short(step['model'])}: {step['why']}"
        executor = (store.meta("executor") or "").split()  # what R starts, when `graphene init` chose it
        everything = store.node_log()  # ponytail: all of it each tick; read on from the last id if it slows
        now = self.clock(everything)
        usage = [e for e in everything if e["kind"] == "usage"]  # what the planners and executors cost
        self.counts = {
            "you": len(tops) + len(yours),
            "proposed": len(tops),  # what y on the goal accepts: `you` counts leaves that came back too
            "board": len(self.board.open),  # they wait on the person too: `1 on you + 5 on the board`
            "running": sum(n.state == P.RUNNING for n in leaves),
            "ready": sum(w == "ready" for w in self.words.values()),
            "back": sum(w == "came back" for w in self.words.values()),  # R leaves them: they are yours
            "done": f"{done}/{len(leaves)} done",
            # every leaf done, and every sub-goal rolled up: the goal never reads done above one still open
            "finished": bool(leaves) and done == len(leaves) and not tops and not yours
            and all(n.state == P.DONE for n in nodes if under.get(n.id)),
            "first": P.plan_first(store),
            "with": f" with {Path(executor[0]).name}" if executor else "",
            "spent": sum(e["detail"].get("dollars") or 0 for e in usage) if usage else None,
            "agents": M.agents(everything, now),  # the two clocks
            "mine": M.you(everything, P.caller().name),
        }
        self.billed = V.billed(everything, now)
        self.draw_meter(store, everything, now)
        goal_word = "proposed" if proposed and not goal else self.counts["done"]
        if self.counts["finished"]:  # what `graphene` says; the goal row reads done, as a sub-goal does
            self.counts["done"] += ", finished"
            goal_word = "done"
        shape = [(n.id, n.parent, n.state, n.title, n.rev, n.id in self.back) for n in nodes]
        shape += [(i, f["fork"]) for i, mine in self.forks.items() for f in mine] + self.board.shape()
        tree = self.tree
        with self.prevent(Tree.NodeHighlighted):  # the tree moved, not the person
            show = bool(nodes or goal or proposed or self.board)
            if tree.show_root != show:
                tree.show_root = show
            hidden = not tree.display
            tree.display = show and self.drawn is None  # no plan yet: the pane says so, across the screen
            if hidden and tree.display and not self.query_one("#line").has_class("-open"):
                tree.focus()  # hidden, it lost the focus, and j k with it (a replay played again)
            self.query_one("#side").set_class(not show, "-alone")
            if shape != self.shape:
                self.rebuild(nodes, under)
                if self.shape is not None and self.view == "said":
                    self.view = "contract"  # the plan moved: what a `:` command printed is old news
                self.shape = shape
            self.goal_text = goal or proposed or "no goal yet"
            self.relabel(nodes, under, goal_word, self.goal_text)
        if self.showing is None:
            self.showing = self.opening(store)
        self.paint(show)
        self.size_panes(nodes, tree.ids, tree.words)
        where, room = P.where(self.root_path), max(self.size.width - 2 - len("the plan of "), 10)
        if len(where) > room:  # the repository's own name, and what is above it as far as it fits
            where = "…" + where[len(where) - room + 1 :]
        self.query_one("#where", Static).update(Text(f"the plan of {where}", "bold"))
        self.draw_direction(store)
        self.look_changed(store)
        self.show_detail(store)

    def clock(self, everything: list[dict]) -> datetime:
        """Now, for the clocks and a leaf's minutes."""
        return datetime.now(UTC)

    def draw_meter(self, store, everything: list[dict], now: datetime) -> None:
        """The meter's strip, between the plan and the bottom lines: a block for each running leaf whose
        executor `graphene run` started (`live_row`), METERED at most, the rest counted."""
        running = {n.id: n for n in self.nodes if n.state == P.RUNNING}
        logs: dict[str, list[dict]] = {}
        for e in everything:
            if e["node_id"] in running:
                logs.setdefault(e["node_id"], []).append(e)
        going = {i: M.going(logs.get(i, []), n.scope, now) for i, n in running.items() if self.METERS}
        held = [i for i in going if going[i]]  # a person or a session that took it after a run has none
        room, one = max(self.size.width - 2, 20), self.size.width >= WIDE
        lines = []
        for i in held[:METERED]:
            lines += live_row(i, going[i], R.live(store, running[i], now.timestamp()), room, one)
        if len(held) > METERED:
            lines.append(Text(f"+{len(held) - METERED} more", "dim"))
        strip = self.query_one("#meter", Static)
        strip.display, self.metered = bool(lines), len(lines)
        strip.update(Text("\n").join(lines))

    def draw_direction(self, store) -> None:
        """The direction above the plan, in every view: the path to the node the plan hangs from, each
        row with what waits on you below it, what runs and what is next (`direction.above_plan`)."""
        said = D.above_plan(store, self.root_path, max(self.size.width - 2, 20))
        # the strip has four lines: past that, whole ancestors go from the top, and the node the plan
        # hangs from, the one the strip is for, stays
        starts = D.row_starts(said)
        said = said[next((k for k in starts if len(said) - k <= 4), starts[-1] if starts else 0) :]
        pane = self.query_one("#direction", Static)
        pane.display = bool(said)
        pane.update(direction_text(said))

    def action_direction(self) -> None:
        """D: the direction in the node pane, across the screen's width, read again every tick like the
        plan (so what a `:direction` command changes shows at once); D again, or Esc, closes it. It
        shows and opens nothing: the keys stay the tree's, and attaching is typed at `:`."""
        self.view = "contract" if self.view == "direction" else "direction"
        self.message = ""  # the bottom line says the keys: D back, and what is typed at `:`
        self.sized = ()  # the layout changes: the pane goes under the tree, across the width
        self.refresh_plan()

    def relabel(self, nodes: list[P.Node], under: dict, goal_word: str, goal: str) -> None:
        """Each row's cells. A folded row's word is what is inside it (`inside`), so a folded
        sub-goal says whether anything in it is the person's move without being opened."""
        tree = self.tree
        shut = {t.data for t in [tree.root, *_walk(tree.root)] if t.allow_expand and not t.is_expanded}
        goals = P.kids(nodes)  # a leaf with a proposal under it is a leaf: counted, and folded keeps its word

        def folded(node_id: str | None) -> str:
            if node_id not in shut or not goals.get(node_id):
                return ""
            below = nodes if node_id is None else P.below(node_id, nodes)
            return inside([self.words[c.id] for c in below if not goals.get(c.id)])

        rows = {
            n.id: (P.look(w := self.words[n.id])[0], w, n.title, n.id, bool(under.get(n.id)), folded(n.id))
            for n in nodes
        }
        glyph = P.look("done" if self.counts.get("finished") else goal_word)[0]  # ✓ once every leaf is done
        rows[None] = (glyph, goal_word, goal, "", True, folded(None))
        for i, mine in self.forks.items():  # a fork's row: its model where a title goes, which fork for an id
            for f in mine:
                word, model = f["state"], _short(f["model"])
                rows[(i, f["fork"])] = (_look(word)[0], word, model, f"fork {f['fork']}", False, "")
        rows.update(BR.rows(self.board))
        ids = max(len(r[3]) for r in rows.values())
        words = max(len(r[5] or r[1]) for r in rows.values())  # what each row shows in the word's column
        chosen = frozenset(self.chosen()) if self.anchor is not None else frozenset()
        if (rows, ids, words, chosen) != (tree.rows, tree.ids, tree.words, tree.chosen):
            tree.rows, tree.ids, tree.words, tree.chosen = rows, ids, words, chosen
            tree._invalidate()  # every row is laid out again: a column may have changed width

    # -- a view other than the outline ---------------------------------------------------------------

    def opening(self, store) -> str:
        """The view the screen opens in: the one `--view` asked for, else the repository's `view`
        setting, else the outline. `auto` is the view that suits this plan at this size (views.choose)."""
        name = self.wanted or store.meta("view") or "outline"
        if name == "auto":
            return V.choose(self.nodes, self.words, self.goal_text, *self.view_room())
        if name not in V.VIEWS:
            self.message = f"no view named {name} here: the outline"
            return "outline"
        return name

    def view_room(self) -> tuple[int, int]:
        """The columns and rows a view is drawn in at this screen's size (`views.room`)."""
        return V.room(self.size.width, self.size.height - self.metered)

    def draw_view(self, name: str) -> V.Drawn | None:
        """A registered view drawn at the room it has, its cursor on the node under the cursor, or on
        the one standing in for it when the view has no cell for it; None when it does not fit."""
        view = V.VIEWS.get(name)
        if view is None:
            return None
        (width, height), goal = self.view_room(), BR.goal(self.goal_text, self.board)  # board: its count
        noted = {"meter": self.billed} if getattr(view, "METER", False) else {}  # a view that takes them
        drawn = view.draw(self.nodes, self.words, goal, width, height, self.here, **noted)
        if drawn is not None and self.here is not None and self.here not in drawn.at:
            was, self.here = self.here, self.stand_in(drawn)
            if was in self.by_id and self.here is not None:
                self.mapped = (was, self.here)  # Tab from the stand-in goes back to the node itself
            drawn = view.draw(self.nodes, self.words, goal, width, height, self.here, **noted)
        return drawn

    def stand_in(self, drawn: V.Drawn) -> str | None:
        """The cell for a node a view has none for: a sub-goal's first node drawn under it (a graph of
        leaves), else its nearest drawn one above it (a fold). A node gone from the plan (dropped): the
        next in the order it was in, else the one before, as the outline moves. Else the goal (None)."""
        if self.here in self.by_id:
            under = [n.id for n in P.below(self.here, self.nodes)]
            up = [a.id for a in P.above(self.by_id[self.here], self.by_id)]
            return next((i for i in under + up if i in drawn.at), None)
        was = self.drawn.order if self.drawn is not None else []
        if self.here not in was:
            return None
        k = was.index(self.here)
        return next((i for i in [*was[k + 1 :], *reversed(was[:k])] if i in drawn.at), None)

    def paint(self, show: bool) -> None:
        """The view where the outline goes, when it is not the outline: its lines, with its cursor and
        the selection reversed, the cursor's line kept in sight. A view that does not fit (the terminal
        got narrower) gives way to the outline, on the same node, and the bottom line says so once."""
        box, name, was = self.query_one("#view", PlanView), self.showing, self.drawn
        drawn = self.draw_view(name) if show and name != "outline" else None
        if show and name != "outline" and drawn is None:
            self.showing = "outline"
            self.message = f"the {name} does not fit at {self.size.width} columns: the outline"
            if self.mapped is not None and self.mapped[1] == self.here:  # a stand-in: the node itself
                self.here = self.mapped[0]
            self.mapped = None
            self.tree_to(self.here)
        self.drawn = drawn
        self.tree.display, box.display = show and drawn is None, drawn is not None
        if (was is None) != (drawn is None) and not self.query_one("#line").has_class("-open"):
            (self.tree if drawn is None else box).focus()
        if drawn is None:
            return
        lines = [line.copy() for line in drawn.lines]
        if self.here is None and lines:  # on the goal
            lines[0].stylize("reverse")
        for node_id in self.chosen() if self.anchor is not None else []:
            line, first, last = drawn.at.get(node_id, (0, 0, -1))
            lines[line].stylize("reverse", first, last + 1)
        box.query_one("#drawn", Static).update(Text("\n").join(lines))
        line = drawn.at[self.here][0] if self.here in drawn.at else 0
        rows = box.scrollable_content_region.height or self.view_room()[1]  # not laid out yet: its room
        if not box.scroll_y <= line < box.scroll_y + rows:
            box.call_after_refresh(box.scroll_to, y=max(line - rows // 2, 0), animate=False)

    def tree_to(self, node_id: str | None) -> None:
        """The outline's cursor on this node, its branch unfolded to it; None, the goal."""
        if node_id is None and self.tree.show_root:
            with self.prevent(Tree.NodeHighlighted):
                self.tree.move_cursor(self.tree.root)
        for node in _walk(self.tree.root):
            if node.data == node_id:
                parent = node.parent
                while parent is not None:
                    parent.expand()
                    parent = parent.parent
                _ = self.tree.last_line
                with self.prevent(Tree.NodeHighlighted):  # moved for the person: what the line says stays
                    self.tree.move_cursor(node)

    def go(self, node_id: str | None) -> None:
        """The view's cursor on this node: the node pane and the bottom line follow it, as the
        outline's do. None is the goal."""
        if node_id == self.here:
            return
        self.here, self.mapped = node_id, None
        if self.view == "said":
            self.view = "contract"
        self.message = ""
        self.refresh_plan()

    def action_step(self, way: int) -> None:
        stops = self.stops()
        at = stops.index(self.here) if self.here in stops else 0
        self.go(stops[max(0, min(at + way, len(stops) - 1))])

    def action_end(self, which: int) -> None:
        self.go(self.stops()[which])

    def action_beside(self, way: int) -> None:
        if self.drawn is not None and (to := V.beside(self.drawn, self.here, way)) is not None:
            self.go(to)

    def action_next_view(self) -> None:
        """Tab: the next view that fits this plan at this size, in the order the views were added,
        then the outline again. The cursor stays on its node; the bottom line says the command that
        opens this view, and what it shows at a glance."""
        if not self.nodes:  # nothing to draw: Tab would switch to a view no one sees
            self.message = "graphene watch --view: nothing is planned yet (:ask what you want)"
            return self.say_status()
        names, here, was = list(V.VIEWS), self.selected(), self.showing or "outline"
        if self.mapped is not None and self.mapped[1] == here:  # on a stand-in: the node the person was on
            here = self.mapped[0]
        self.mapped = None
        skipped = []
        for name in [*names[names.index(was) + 1 :], "outline"]:
            self.here = here
            if name == "outline" or self.draw_view(name) is not None:
                break
            skipped.append(name)
        self.showing, self.here, self.anchor = name, here, None
        if self.view == "said":
            self.view = "contract"
        if name == "outline":
            self.tree_to(here)
        self.refresh_plan()
        note = self.drawn.note if self.drawn is not None else ""
        if name == was == "outline":
            note = f"no other view fits at {self.size.width} columns" if len(names) > 1 else "the only view"
        # a view Tab went past is said once a width (what the view shows is then on the line above):
        # the stand-ins never learned the tree was there at 80 columns
        news = [v for v in skipped if (v, self.size.width) not in self.skips]
        self.skips.update((v, self.size.width) for v in news)
        if news:
            verb = "do" if len(news) > 1 else "does"
            note = f"the {' and the '.join(news)} {verb} not fit at {self.size.width} columns"
        self.message = f"graphene watch --view {name}" + (f": {note}" if note else "")
        self.say_status()

    def main_pane(self):
        """What shows where the outline goes: the outline, or the view."""
        return self.tree if self.drawn is None else self.query_one("#view", PlanView)

    def size_panes(self, nodes: list[P.Node], ids: int, words: int) -> None:
        """At 110 columns and more the tree is as wide as its rows need, and the node pane has the
        rest (never less than PANE); below that the tree is as tall as its rows, up to half the
        screen, and the node pane has what is left under it. A view is as tall as its lines, up to
        its room, over the whole width, and the node pane under it at every width."""
        tree, width = self.tree, self.size.width
        if not width:
            return
        self.query_one("#main").set_class(self.drawn is not None or self.view == "direction", "-stacked")
        if self.drawn is not None:
            lines, box = self.drawn.lines, self.query_one("#view", PlanView)
            sized = ("narrow", max(3, min(len(lines), self.view_room()[1])), "view")
            if sized != self.sized:
                self.sized = sized
                box.styles.height = sized[1]
            return
        by_id = {n.id: n for n in nodes}
        if not tree.display:
            return
        if width >= WIDE and self.view != "direction":  # the direction takes the width, under the tree
            opened = not any(n.data == BR.FOLD and not n.is_expanded for n in tree.root.children)
            need = max(
                [2 * (len(P.above(n, by_id)) + 1) + 4 + len(n.title) for n in nodes]
                + [2 * (len(P.above(by_id[i], by_id)) + 2) + 4 + len(_short(f["model"]))
                   for i, mine in self.forks.items() for f in mine]
                + BR.widths(self.board, opened), default=30
            ) + 2 + ids + 2 + words + 2  # fmt: skip
            sized = ("wide", max(30, min(need, width - PANE - 3)))
        else:
            lines = tree.last_line + 1 if tree.show_root else 0
            sized = ("narrow", max(3, min(lines, self.tree_room())))
        if sized != self.sized:
            self.sized = sized
            kind, amount = sized
            tree.styles.width = amount if kind == "wide" else None
            tree.styles.height = amount if kind == "narrow" else None

    def tree_room(self) -> int:
        """The rows the tree may take: the screen less its top line, the meter's strip and the two at the
        bottom, and below 110 columns half of that, the node pane under it."""
        rows = self.size.height - 3 - self.metered
        return rows if self.size.width >= WIDE and self.view != "direction" else max(3, rows // 2)

    def pane_room(self) -> tuple[int, int]:
        """The node pane's width and height, from the layout this screen sets (known before Textual
        has laid it out): its text is wrapped to it, and a leaf that came back fitted to it."""
        width, height = self.size.width, self.size.height - self.metered
        kind, amount = (self.sized or ("narrow", 10))[:2]
        if kind == "wide":
            return max(width - amount - 4, 20), max(height - 3, 5)
        return max(width - 3, 20), max(height - 3 - amount - 1, 3)

    def rebuild(self, nodes: list[P.Node], under: dict) -> None:
        tree = self.tree
        y = tree.scroll_y
        was_open = {n.data for n in _walk(tree.root) if n.is_expanded}
        cursor, at_goal = self.selected(), tree.cursor_node is tree.root
        row_at = tree.cursor_node.data if tree.cursor_node is not None else None  # a fork's row stays
        tree.clear()
        placed, finished, new = {}, set(), []
        by_id = {n.id: n for n in nodes}
        placed.update(self.board_rows(was_open))  # board: its rows, under the goal and before the tree
        queue = [n for n in nodes if n.parent not in by_id]  # the tops, then each one's children
        while queue:
            node = queue.pop(0)
            parent = placed.get(node.parent) if node.parent in by_id else tree.root
            has_kids, mine = bool(under.get(node.id)), self.forks.get(node.id, [])
            if has_kids and all(c.state == P.DONE for c in P.below(node.id, nodes)):
                finished.add(node.id)
            if mine and node.state == P.DONE:  # its forks are history, folded as a finished subtree is
                finished.add(node.id)
            # a subtree folds when it finishes and opens when it stops being finished (a leaf in it
            # reopened, a new one added); otherwise it stays as the person left it
            moved = node.id not in self.known or (node.id in finished) != (node.id in self.complete)
            opened = node.id not in finished if moved else node.id in was_open
            placed[node.id] = parent.add(
                Text(node.title), data=node.id, expand=opened, allow_expand=has_kids or bool(mine)
            )
            for f in mine:  # its forks: rows, not nodes (no command takes one); their keys are the leaf's
                fork = (node.id, f["fork"])
                placed[fork] = placed[node.id].add_leaf(Text(f"fork {f['fork']}"), data=fork)
            if node.id not in self.known:
                new.append(placed[node.id])
            queue[:0] = [c for c in under.get(node.id, []) if c.id in by_id]
        tree.root.allow_expand = bool(nodes or self.board)
        if self.shape is None:
            tree.root.expand()  # the goal's row starts open
        self.known, self.complete = {n.id for n in nodes}, finished
        self.outline(new)  # when the screen opens every node is new; later, what a planner adds
        _ = tree.last_line  # lays the new tree out, so the line of each node is known
        # the row it was on; one that folded away (a fork's row with its finished leaf, a leaf with its
        # finished sub-goal): the first row above it still shown, as vim does
        here = placed.get(row_at) or placed.get(cursor)
        was, self.opened = self.opened, [it["id"] for it in self.board.open]
        to = BR.landing(was, self.board, row_at, at_goal or self.shape is None)  # board: onto the next item
        if to is not None:
            top = next((n.id for n in nodes if n.parent not in by_id), None)
            here, at_goal = placed.get(top if to == BR.TREE else to), False
        while here is not None and here.line < 0:
            here = here.parent
        if here is not None and not at_goal:
            tree.cursor_line = here.line
        elif tree.cursor_line < 0:
            tree.cursor_line = 0  # a screen opens on the first row: the goal
        tree.scroll_to(y=y, animate=False)
        rows, line = tree.scrollable_content_region.height, tree.cursor_line
        if rows and not y <= line < y + rows:  # rows put up above it pushed the cursor off the pane
            tree.call_after_refresh(tree.scroll_to_line, line, animate=False)

    def outline(self, among: list) -> None:
        """A tree taller than its pane folds the sub-goals ``among`` to one row each, which counts what
        is inside (a thirty-leaf plan at 80x24). A leaf with a proposal under it stays open: the
        proposal is the person's move."""
        if self.tree.last_line + 1 <= self.tree_room():
            return
        goals = P.kids(self.nodes)
        with self.prevent(Tree.NodeExpanded, Tree.NodeCollapsed):  # one redraw after, not one a node
            for node in among:
                if goals.get(node.data):
                    node.collapse()

    def fold_as_opened(self) -> None:
        """The folds the tree opens with, and zx puts back: a subtree whose leaves are all done is
        folded, the rest is open, and a tree still taller than its pane is folded to its outline.
        Then, as vim's zx does, the row under the cursor is shown."""
        tree, cursor = self.tree, self.tree.cursor_node
        with self.prevent(Tree.NodeExpanded, Tree.NodeCollapsed):  # one redraw after, not one a node
            for node in _walk(tree.root):
                if node.allow_expand:
                    (node.collapse if node.data in self.complete else node.expand)()
            tree.root.expand()
            self.outline(list(_walk(tree.root)))
            up = cursor.parent if cursor is not None else None
            while up is not None:
                up.expand()
                up = up.parent
        _ = tree.last_line
        if cursor is not None:
            tree.move_cursor(cursor)

    def action_fold_as_opened(self) -> None:
        self.fold_as_opened()
        self.refresh_plan()

    def say_status(self) -> None:
        """Two lines, each fitted at a word, and more when there is something to say: the plan (what
        waits on the person, the two clocks, what R would start, how much is done, plan first), what the
        keys do on the row under the cursor, in a view what it shows at a glance (the graph's critical
        path), then what the last command said. The keys never give way to what a command said: after
        an answer on the board the cursor is on the next item, and its keys are what is next. The short
        forms at 80 columns; whole pieces drop off the end. What R starts, when `graphene init` chose
        it, is named only where the long form still fits with it, and "by your keys" too. The clocks
        (`meter.agents`, `meter.you`): the executors running, their minutes and the plan's dollars; the
        person's acts and the minutes that hold one."""
        if not self.is_running:
            return
        room = max(self.size.width - 2, 20)
        c = self.counts or {"you": 0, "running": 0, "ready": 0, "done": "0/0 done", "first": "off"}
        board = f" + {c['board']} on the board" if c.get("board") else ""
        you = "magenta" if c["you"] or board else ""
        busy = P.look("running")[1] if c["running"] else ""
        spent = money(c["spent"]) if c.get("spent") is not None else ""  # the plan's: planner and leaves
        agents = c.get("agents") or {"running": 0, "seconds": 0}
        mine = c.get("mine") or {"acts": 0, "minutes": 0}
        ran, acts = agents["running"] or agents["seconds"] or spent, _s(mine["acts"], "act")
        took = agents["seconds"] // 60 or ("<1" if agents["seconds"] or agents["running"] else 0)
        clock = " · ".join([f"{agents['running']} running", f"{took} min", *([spent] if spent else [])])
        long = [
            (f"waiting on you: {c['you']}{board}", you),
            (f"agents: {clock}" if ran else "agents: none", busy),
            (f"you: {acts} · ~{mine['minutes']} min", ""),
            (f"R runs {c['ready']} ready" if c["ready"] else "nothing ready to run", ""),
            *([(f"{c['back']} came back", "")] if c.get("back") else []),
            (c["done"], ""),
            (f"plan first: {c['first']} (P)", ""),
        ]
        short = [
            (f"{c['you']} on you{board}", you),  # the graph's note says it so too
            (f"agents {clock.replace(' running', '').replace(' min', 'm')}" if ran else "agents 0", busy),
            (f"you {acts} ~{mine['minutes']}m", ""),
            (f"R: {c['ready']} ready" if c["ready"] else "none ready", ""),
            *([(f"{c['back']} came back", "")] if c.get("back") else []),
            (c["done"], ""),
            (f"plan first: {c['first']}", ""),
        ]
        named = [*long[:3], (long[3][0] + (c.get("with", "") if c["ready"] else ""), ""), *long[4:]]
        keyed = [[(f"{text} by your keys" if k == 2 else text, how) for k, (text, how) in enumerate(form)]
                 for form in (named, long)]  # fmt: skip
        if not self.RUNS_HERE:  # a replay: R and P start nothing, one form holds from frame to frame, and
            # its own clock is the recording's: the executors running and the bill, as it was played
            ready = (f"{c['ready']} ready" if c["ready"] else "none ready", "")
            short = [short[0], (f"{c['running']} running", busy), ready, *short[4:-1]]
            named = long = short = [*short, *([(f"bill {spent}", "dim")] if spent else [])]
            keyed = []
        forms = (*keyed[:1], named, *keyed[1:], long, [*long[:1], *short[1:3], *long[3:]])  # clocks short
        fits = [form for form in forms if len(" · ".join(text for text, _ in form)) <= room]
        top = fit([*self.news(), *short] if self.news() else fits[0] if fits else short, room)
        lines = [top, fit([(k, "") for k in self.keys()], room)]
        said = self.busy or self.message
        note = self.drawn.note if self.drawn is not None else ""
        if note and note not in said:  # a view's glance stays in sight whatever a command said after it
            lines.append(Text(T.elide(note, room)))
        if said:  # a command that failed says why last: it takes a second line before it is cut
            pieces = textwrap.wrap(said.splitlines()[0], room, break_on_hyphens=False) or [""]
            if not said.startswith("✗") or len(pieces) < 2:
                pieces = [T.elide(said.splitlines()[0], room)]
            else:
                pieces = [pieces[0], T.elide(" ".join(pieces[1:]), room)]
            bottom = Text("\n".join(pieces))
            if bottom.plain.startswith("✗"):  # red is for a command that failed, and only its mark
                bottom.stylize("red", 0, 1)
            lines.append(bottom)
        status = self.query_one("#status", Static)
        status.styles.height = sum(len(line.plain.splitlines()) for line in lines)
        status.update(Text("\n").join(lines))

    def keys(self) -> list[str]:
        """What the keys do on the row under the cursor, for the bottom line. In a view the outline's
        own keys (l for the output, the folds) are left out: there l moves, and nothing folds."""
        keys = self.row_keys()
        if self.drawn is None:
            return keys
        keys = [k for k in keys if k != "l output" and not k.startswith("za ")]
        return ["Esc back" if k == "l back" else k for k in keys]

    def row_keys(self) -> list[str]:
        tail = [*(["Tab view"] if len(V.VIEWS) > 1 else []), "? talk" if self.selected() else "? help"]
        tail.append("q quit")
        if self.anchor is not None:
            return ["VISUAL", "y accept", "d drop", "? m merge", "j k widen it", "Esc ends"]
        if self.view == "record":
            offers = [OFFERED[k] for k in self.offer_keys()]
            ask = ["? ask the planner", "q quit"] if offers else tail  # there ? is no help: it spends
            return ["ctrl-d ctrl-u scroll", "Enter back", *offers, *ask]
        if self.view == "tail":
            return ["ctrl-d ctrl-u scroll", "l back", *tail]
        if self.view == "said":
            return ["ctrl-d ctrl-u scroll", "Esc back", *tail]
        if self.view == "direction":  # D: what attaches and accepts is typed at `:`
            return ["D back", ":direction attach SESSION NODE", ":direction accept ID", "ctrl-d -u scroll"]
        row = self.board_row()
        if row is not None:  # board: what each key would do on this item, in words
            item = self.board.get(row)
            if item is not None:  # its words give way to Tab and ? (q quit, last, is the first to go)
                room = max(self.size.width - 2, 20) - sum(len(k) + 3 for k in tail[:-1])
                return [*BR.hints(item, room), *tail]
            if row == BR.STANDING:
                return ["standing conditions: graphene config shows them", *tail]
            fold = ["za fold" if self.tree.cursor_node.is_expanded else "za unfold"] if row == BR.FOLD else []
            return [*fold, "a note", *tail]
        if not self.nodes:
            return [":ask what you want", *tail]
        if self.on_goal():
            ended = [":plan archive puts it away"] if self.counts.get("finished") else []
            ended = ended or (["R run all ready"] if self.counts.get("ready") else [])  # as the status says
            keys = ["y accept it all"] if self.counts.get("proposed") else ended
            fold = "za fold all" if self.tree.root.is_expanded else "za unfold"
            return [*keys, "E edit the plan as text", fold, *tail]
        word, node = self.word(self.selected()), self.tree.cursor_node if self.drawn is None else None
        fork = node.data if node is not None and isinstance(node.data, tuple) else None
        on = [f"fork {fork[1]}: keys act on {fork[0]}"] if fork else []  # its row is its leaf's to act on
        if word == "came back":
            offers = [OFFERED[k] for k in self.offer_keys()]
            return [*on, *offers, "? ask the planner", "r run it again", "Enter record", "q quit"]
        shut = ["za unfold"] if node is not None and node.allow_expand and not node.is_expanded else []
        if word in KEYS:
            return [*on, *shut, *KEYS[word], *tail]
        return [*(shut or ["za fold"]), "r run what is ready here", "E edit it as text", *tail]  # a sub-goal

    def offer_keys(self) -> list[str]:
        return self.offered.get(self.selected() or "", [])

    shown_as: tuple = (None, None)  # the pane's view and node last drawn: another opens at its top

    def show_detail(self, store) -> None:
        node_id = self.selected()
        pane = self.query_one("#detail", Static)
        if (self.view, node_id) != self.shown_as:  # a scroll made in one pane never hides another's top
            self.shown_as = (self.view, node_id)
            self.query_one("#side", VerticalScroll).scroll_home(animate=False)
        wide, high = self.pane_room()
        if self.view == "direction":  # D: the direction, read again every tick, plan or no plan
            return pane.update(direction_pane(store, self.root_path, wide))
        if not self.nodes and not self.tree.show_root:
            empty = Pane(wide)
            empty.text(EMPTY)
            pane.update(empty.render())
            return
        if self.view == "said":
            return  # what a `:` command printed stays until the cursor moves
        if self.board_row() is not None:  # board: the item whole
            return pane.update(BR.pane(self.board, self.board_row(), self.by_id, wide))
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
        self.message = f"{'✗ ' if code else ''}graphene {as_typed(argv)}" + (f": {first}" if first else "")
        if not quiet:
            self.refresh_plan()
        return said if keep else code

    @on(Tree.NodeHighlighted)
    def moved(self, event: Tree.NodeHighlighted) -> None:
        if event.node is not self.tree.cursor_node:  # a row of the tree before it was laid out again
            return
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
            self.background(asked_about(node_id))
        elif node_id is not None:
            self.talk_to()
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
        self.main_pane().focus()
        if text.startswith("/"):
            self.search = text[1:].strip().lower()
            self.find(self.search)
            return
        words = text[1:].strip().removeprefix("graphene ").strip()
        if not words:
            return
        read = words  # `:ask don't … isn't`: apostrophes, not a quote, unless the sentence is in "…"
        if re.match(r"ask\s", words) and '"' not in words:
            read = re.sub(r"(?<=\w)'(?=\w)", r"\\'", words)
        try:
            argv = shlex.split(read)
        except ValueError as no:
            if re.match(r"ask\s", words):  # `:ask don't …`: not the shell's, so the sentence as typed
                return self.background(["ask", words[3:].strip()])
            self.message = f"✗ {no}"
            return self.say_status()
        if argv[:1] == ["ask"]:
            argv = _sentence(argv)
        if argv[:1] == ["stop"]:
            return self.stop_runs()
        if argv[:1] in (["watch"], ["ingest"], ["init"]):
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
            self.message = f"graphene {as_typed(argv)}: {len(lines)} lines, in the pane"
            self.say_status()

    def action_escape(self) -> None:
        line = self.query_one("#line", Input)
        if line.has_class("-open"):
            line.remove_class("-open")
            self.main_pane().focus()
        self.anchor = None
        self.search = ""
        self.view = "contract"
        self.message = ""
        self.refresh_plan()

    def find(self, text: str, after: int | None = None) -> None:
        if not text:
            return
        titles = {n.id: n.title for n in self.nodes}
        order = self.drawn.order if self.drawn is not None else [n.data for n in _walk(self.tree.root)]
        shown = [i for i in order if i in titles]
        # what the row shows: its title, its id, and the word its state reads as (`/came back`)
        hits = [i for i in shown if any(text in f.lower() for f in (titles[i], i, self.word(i)))]
        if not hits:
            self.message = f"✗ nothing matches {text!r}"
            return self.say_status()
        current = self.selected()
        start = hits.index(current) + 1 if current in hits else 0
        target = hits[start % len(hits)]
        if self.drawn is not None:
            self.here = target
        else:
            self.tree_to(target)  # the search moved it: its line stays said
        if self.view == "said":
            self.view = "contract"  # the search moved the cursor: the node's pane, not the output
        self.message = f"/{text}: {hits.index(target) + 1} of {len(hits)} (n next · Esc ends the search)"
        self.refresh_plan()

    def action_next_or_needs(self) -> None:
        if self.search:
            return self.find(self.search)
        self.action_offer("n")

    def action_add(self, child: bool) -> None:
        if self.board_row() is not None:
            return self.action_board("a")
        node_id = self.selected()
        parent = node_id if child else self.read(lambda s: P.get(s, node_id).parent if node_id else None)

        def added(title: str | None) -> None:
            if not title:
                return
            before = set(self.read(lambda s: [n.id for n in P.nodes(s)], []))
            self.did(["node", "add", *(["--parent", parent] if parent else []), "--", title])
            new = [i for i in self.read(lambda s: [n.id for n in P.nodes(s)], []) if i not in before]
            if new:  # the cursor on the new node, where the prompt's next step (e, or s) acts
                if self.drawn is not None:
                    self.here = new[0]
                else:
                    self.tree_to(new[0])
                self.refresh_plan()

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
        if self.anchor is None and self.board_row() is not None:
            return self.action_board("y")
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
        if self.anchor is None and self.board_row() is not None:
            return self.action_board("d")
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

    def action_reask(self, size: str) -> None:
        """+ and -: the last sentence asked of the planner, asked again for a finer or a coarser tree,
        which takes the place of the proposals still waiting (graphene ask --finer, --coarser)."""
        from .ask import reask_argv

        argv = self.read(lambda s: reask_argv(s, size))
        if argv is None:
            self.message = f"✗ graphene ask --{size}: no plan was asked for yet (:ask what you want)"
            return self.say_status()
        self.background(["ask", f"--{size}", *argv[2:-1]])  # the flag first: a cut line still names it

    def action_run(self, here: bool) -> None:
        node_id = self.selected()
        argv = ["run", *shlex.split(RUN_WITH), *(["--node", node_id] if here and node_id else [])]
        self.background(argv)

    def action_plan_first(self) -> None:
        now = self.counts.get("first", "off")  # on, auto, off: strictest to loosest, then round
        self.did(["plan", "first", P.FIRST[(P.FIRST.index(now) + 1) % 3]])

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
            again = "; r runs it again" if node_id in self.back else ""
            self.message = f"x releases a running leaf or reopens a finished one; {node_id} is neither{again}"
            self.say_status()

    def action_tail(self) -> None:
        self.view = "contract" if self.view == "tail" else "tail"
        self.refresh_plan()

    def action_record(self) -> None:
        if self.board_row() is not None:
            return self.action_board("enter")
        if self.on_goal():  # the goal has no record of its own: its pane already says what is under it
            return
        self.view = "contract" if self.view == "record" else "record"
        self.query_one("#side", VerticalScroll).scroll_home(animate=False)
        self.refresh_plan()

    def action_visual(self) -> None:
        stops = self.stops()
        in_view = self.drawn is not None and self.here in stops
        here = stops.index(self.here) if in_view else self.tree.cursor_line
        self.anchor = None if self.anchor is not None else here
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

    # -- talking on the tree: `?` on a node (graphene talk), `m` (graphene plan seen) -----------------

    TALK = {"w": "why", "s": "split", "m": "merge", "a": "another", "another way": "another", "?": "help"}
    changed: tuple[dict[str, str], int] = ({}, 0)  # talk.marks: what changed since the person last looked

    def talk_to(self) -> None:
        """`?` on a node: one line saying what to ask the planner about it, or about the selection."""
        ids, here = self.chosen(), self.selected()
        about = ", ".join(ids) if len(ids) > 1 else here
        choices = "w why · s split · m merge · a another way · ? help · or your words"
        said = f"{about}: {choices}"  # the line's room is the width less its border and padding
        ask = Ask(said) if len(said) <= self.size.width - 4 else Ask(choices, about=about)
        self.push_screen(ask, lambda words: self.talked(ids, here, words))

    def talked(self, ids: list[str], here: str, words: str | None) -> None:
        """What the line said, as the command it runs: slow, so off the screen, and the bottom line
        says which. One letter or the word picks; anything else is asked as it was typed."""
        self.anchor = None
        low = (words or "").lower()
        kind = self.TALK.get(low, low if low in ("why", "split", "merge", "another", "help") else None)
        if not words:
            return self.refresh_plan()
        if kind == "help":
            return self.push_screen(Help())
        if kind == "split":
            return self.action_split()  # graphene node split, refused on what is running or done
        if kind:
            return self.background(["talk", kind, *(ids if kind == "merge" else [here])])
        self.background(["ask", words, "--about", here])

    def action_seen(self) -> None:
        self.did(["plan", "seen"])

    def look_changed(self, store) -> None:
        from .talk import marks

        now = marks(store, P.caller().name)
        if now != self.changed:
            self.changed = now
            self.tree._invalidate()  # a mark is not a row's cell: its rows are laid out again

    def mark(self, node) -> str:
        """`+` (added) or `~` (changed) before a row's id when someone else changed it since the person
        last looked; on a folded row, `~` when anything inside it did, so no change hides in a fold."""
        marks, data = self.changed[0], node.data
        if not marks or not isinstance(data, str):  # the goal's row has no id; a fork's is its leaf's
            return ""
        if data in marks or node.is_expanded or not node.allow_expand:
            return marks.get(data, "")
        return "~" if any(n.id in marks for n in P.below(data, self.nodes)) else ""

    def news(self) -> list[tuple[str, str]]:
        """The first bottom line's first words, while anything changed since the person last looked."""
        count = self.changed[1]
        return [(f"{count} changed since you last looked", "magenta"), ("graphene plan changes", ""),
                ("m seen", "")] if count else []  # fmt: skip

    # -- the board, as rows above the tree (board_rows.py) --------------------------------------------

    def board_rows(self, was_open: set) -> dict:
        """The board's rows, put under the goal before the tree is: the line of standing conditions,
        each open item, then the fold that holds what is settled, parked or dropped."""
        root, placed, board = self.tree.root, {}, self.board
        if board.standing:
            placed[BR.STANDING] = root.add_leaf(Text(""), data=BR.STANDING)
        for item in board.open:
            placed[BR.Row("item", item["id"])] = root.add_leaf(Text(""), data=BR.Row("item", item["id"]))
        if board.folded:
            fold = placed[BR.FOLD] = root.add(Text(""), data=BR.FOLD, expand=BR.FOLD in was_open)
            for item in board.folded:
                placed[BR.Row("item", item["id"])] = fold.add_leaf(Text(""), data=BR.Row("item", item["id"]))
        return placed

    def board_row(self) -> BR.Row | None:
        """The board row under the outline's cursor, if it is on one."""
        node = self.tree.cursor_node if self.drawn is None else None
        return node.data if node is not None and isinstance(node.data, BR.Row) else None

    def action_board(self, key: str) -> None:
        """A key on a board row: y d p 1..9 run the `graphene board` command for the item (board_rows.
        argv), Enter answers it in words, a puts up a note; on the fold row Enter opens or closes it.
        On a node (no board row here) p and the digits do nothing."""
        row = self.board_row()
        item = self.board.get(row)
        if key == "a":
            about = (item or {}).get("about")

            def noted(words: str | None) -> None:
                if words:
                    self.did(["board", "note", words, *(["--about", about] if about else [])])

            where = f"about {about}" if about else "for the whole plan"
            return self.push_screen(Ask(f"a note of yours {where}: told to executors as you write it"), noted)
        if item is None:
            if row == BR.FOLD and key == "enter":
                self.tree.cursor_node.toggle()
            return
        if key == "enter":

            def answered(words: str | None) -> None:
                if words:
                    self.did(["board", "answer", item["id"], words])

            return self.push_screen(Ask(f"answer {item['id']} in your own words: {item['text']}"), answered)
        self.did(BR.argv(item, key))

    # -- what runs on its own ------------------------------------------------------------------------

    def background(self, argv: list[str]) -> None:
        """A run or a planner: its own process, with its output in .graphene/runs/, so it goes on
        whatever happens to this screen. It has no terminal; what the person typed here was typed at
        this screen's, and GRAPHENE_WATCH says so to the log (`plan.caller`)."""
        logs = self.root_path / ".graphene" / "runs"
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / f"{argv[0]}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{len(self.runs)}.txt"
        cli = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
        env = {**os.environ, "GRAPHENE_WATCH": "1" if sys.stdin.isatty() else ""}
        with open(log, "w", encoding="utf-8") as sink:
            proc = subprocess.Popen(
                [sys.executable, "-c", cli, *argv], cwd=self.root_path, stdin=subprocess.DEVNULL,
                stdout=sink, stderr=subprocess.STDOUT, start_new_session=True, env=env,
            )  # fmt: skip
        self.runs.append(proc)
        self.message = f"graphene {as_typed(argv)}: started (its output: {log.relative_to(self.root_path)})"
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
        gist = (news[-1] if argv[0] in ("run", "talk") else news[0]) if news else ""
        named = argv[: next((k for k, word in enumerate(argv) if word.startswith("-")), len(argv))]
        mark = "✗ " if code else ""  # its options were on the bottom line when it started: room for the gist
        whole = [f"{mark}graphene {as_typed(argv)} ended (exit {code}); all it said, kept in "
                 f"{log.relative_to(self.root_path)}:", "", *said]  # fmt: skip
        # a run's own last line says what it did (`run: 3 done, …`): said once, not after "run ended"
        told = f"{mark}{gist}" if re.match(rf"{re.escape(argv[0])}\b", gist) else (
            f"{mark}graphene {as_typed(named)} ended: {gist}"
        )  # fmt: skip
        made = [line.removeprefix("proposed ").split(":")[0] for line in news if line.startswith("proposed ")]
        put = [line.removeprefix("put up ").split(":")[0] for line in news if line.startswith("put up ")]
        repo = [line.split()[1] for line in news if line.startswith("settled ") and " from the repo " in line]
        kept = [line.split()[0 if " is on the board already " in line else 1] for line in news
                if " is on the board already " in line or line.startswith("kept ")]  # fmt: skip
        if argv[0] == "ask" or argv[:2] == ["node", "split"]:  # the sentence was on the line when it began
            did = [*([f"proposed {', '.join(made)}"] if made else []),
                   *([f"put {', '.join(put)} on the board"] if put else []),
                   *([f"put {', '.join(kept)} up again, which the board has already"] if kept else []),
                   *([f"found {', '.join(repo)} answered in the repo"] if repo else [])]  # fmt: skip
            if did or code:
                told = mark + (f"the planner {' and '.join(did)}" if did else f"the planner: {gist}")
            else:  # its prose alone said nothing was added, and the person could not tell
                told = "the planner proposed nothing and put nothing on the board"
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


def _node(data):
    """A row's node id: a fork's row is (its leaf, its number), and stands for its leaf."""
    if isinstance(data, BR.Row):  # board: an item's row stands for no node
        return None
    return data[0] if isinstance(data, tuple) else data


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
    # the run's own count (its hold's last attempt), never every hold the leaf ever had: a new run's first
    # attempt read `attempt 3`, and a leaf that came back `attempt 2` over its `3 attempts`
    tries = (M.going(store.node_log(node.id)) or {}).get("attempt") or 0
    attempt = f" · attempt {tries}" if tries > 1 and word in ("running", "came back") else ""
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
    if word in ("came back", "review", "done"):
        _attempt(pane, store, node)
    spent = bill(store.node_log(node.id, ("usage",)))
    if spent:
        models = ", ".join(m.rsplit("/", 1)[-1] for m in spent["models"])
        calls = f"for this leaf's {spent['calls']} calls"
        pane.field("bill", f"${spent['dollars']:.4f} at list price {calls} · {models}")
    if word in ("done", "review"):
        ended = (store.node_log(node.id, ("finished", "overruled")) or [{"detail": {}}])[-1]["detail"]
        pane.field("changed", ", ".join(ended.get("changed") or []) or "nothing on record")
    last = (store.node_log(node.id, ("started", "released", "reopened")) or [{"kind": ""}])[-1]
    if word != "came back" and node.state == P.OPEN and last["kind"] == "released":
        pane.field("handed back", str(last["detail"].get("why", "")))
    elif node.state == P.OPEN and last["kind"] == "reopened":
        pane.field("sent back", str(last["detail"].get("note", "")))
    return pane.render()


def as_typed(argv: list[str]) -> str:
    """A command as a person would type it: shlex's quoting, except that a word with an apostrophe and
    nothing a shell expands inside double quotes is double-quoted (`"don't"`, not `'don'"'"'t'`)."""
    return " ".join(f'"{w}"' if "'" in w and not re.search(r'["$`\\!]', w) else shlex.quote(w) for w in argv)


def asked_about(node_id: str) -> list[str]:
    """What ? on a leaf that came back runs, and its pane shows as the command it is."""
    return ["ask", f"{node_id} came back: propose what would let it be done", "--about", node_id]


def _came_back(pane: Pane, store, node: P.Node, high: int) -> None:
    """Why it came back, then the fixes it offers as rows of one shape (key, what it does, the
    command), fitted so that at 80×24 every key is in sight: the reason gives way first."""
    why = (store.node_log(node.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get("why", "")
    offers = [*P.offers(store, node), ("?", "ask the planner", asked_about(node.id))]
    rows = [(key, _its(does, node.id), f"graphene {as_typed(argv)}") for key, does, argv in offers]
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
    if P.not_offered(store, node):
        pane.text(P.not_offered(store, node), "dim")


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
    """Which executor, where, what its meter reads (model, turns, tokens, dollars, the files it edited
    in its scope and outside it), what it did last and how long ago; for a session that took it itself,
    what is not known is said in a line rather than left out."""
    seen = R.live(store, node)
    label = node.executor or ""
    by_run = label.startswith("run:")
    who = P.said_by(label)
    if not by_run:
        agent = label.startswith(("claude:", "codex:", "planner"))
        who += f", {'which' if agent else 'who'} took it with graphene node start"
    pane.field("executor", who)
    _attempt(pane, store, node, running=True)
    rows = store.node_log(node.id)
    a = M.going(rows, node.scope)
    if a and a["meter"]:
        if a["model"] and not models(rows):  # a Nemotron executor's model is said above, with its ladder
            pane.field("model", _short(a["model"]))
        spent = f"{money(a['dollars'])} at list price" if a["priced"] else "no list price"
        said = f"{tokens(a['prompt_tokens'])} tokens in, {tokens(a['completion_tokens'])} out"
        used = a["turns"] or a["prompt_tokens"] or a["dollars"]  # Codex says its usage only as it ends
        pane.field("meter", f"{_s(a['turns'], 'turn')} · {said} · {spent}" if used else "no usage yet")
        pane.field("edited", ", ".join(a["files_in"]))
        pane.field("outside", ", ".join(a["files_out"]), "magenta")
    elif a:
        pane.field("meter", "nothing read from its stream", "dim")
    pane.field("worktree", _where(node.checkout, s.root_path))
    age, colour = ago(seen.get("idle"))
    last = (seen.get("last") or "nothing yet").removeprefix("running ")  # the state word is said once
    last = T.elide(last, 2 * (pane.wide - 12) - len(age))  # two lines at most: what it did, then how long ago
    pane.field("last", Text.assemble(last, " · ", (age, colour)))
    if not by_run:
        pane.text(
            "its output is the session's, not Graphene's: l shows the tool calls its hooks recorded", "dim"
        )


def _attempt(pane: Pane, store, node: P.Node, running: bool = False) -> None:
    """The model its last attempt ran on, as its Nemotron executor noted it (after a step up the
    ladder, from which model and why), and its sandbox: the checkpoint it made or forked, and once
    the attempt is over, the operations and seconds it took (its forks', added up)."""
    log = store.node_log(node.id, ("started", "model", "fork", "placement"))
    step = (models(log) or [None])[-1]
    if step:
        up = f", stepped up from {_short(step['from'])}: {step['why']}" if step.get("from") else ""
        pane.field("model", _short(step["model"]) + up)
    box = sandbox(log)
    if box:
        made = "forked from the commit's checkpoint" if box.get("checkpoint") == "forked" else "made"
        said = f"{made}, image {box['image'].removeprefix('sha256:')[:12]}"
        if not running and "ops" in box:
            said += f" · {box['ops']} operations · {box['seconds']:.1f} s"
            said += f" in its {box['forks']} forks" if box.get("forks") else ""
        pane.field("sandbox", said)


def tail_pane(store, node: P.Node, root: Path, wide: int) -> Text:
    """`l`: what the executor did and said, as its meter read it from its stream, newest last; for an
    executor with no meter, what it printed; while it has printed nothing, the tool calls the hooks
    recorded for its session, newest last, said as such. Never the stream's JSON. A sub-goal is run by
    its leaves, so it has none of its own."""
    pane = Pane(wide)
    if P.kids(P.nodes(store)).get(node.id):
        pane.text(f"{node.id} · a sub-goal: no executor runs it, so it has no output of its own", "bold")
        pane.text("each of its leaves has its own output: l on a leaf shows it", "dim")
        return pane.render()
    a = M.going(store.node_log(node.id)) or {}  # its hold's: attempt 1 of an earlier hold is not this one
    pane.text(f"{node.id} · output of attempt {a.get('attempt') or 1}", "bold")
    log = a.get("log")
    if log:
        with contextlib.suppress(ValueError):
            log = str(Path(log).relative_to(root))
        pane.text(log, "dim")
    pane.gap()
    rows = [e for e in store.node_log(node.id, ("did", "said")) if a and e["timestamp"] >= a["started"]
            and e["detail"].get("attempt") == a["attempt"]][-200:]  # fmt: skip  (its number, since it began)
    for e in rows:
        d, at = e["detail"], (_clock(e["timestamp"], True), "dim")
        if e["kind"] == "did":
            pane.line(Text.assemble(at, "  ", T.elide(M.doing(d.get("verb") or "", d.get("target") or ""),
                                                      wide - 10)))  # fmt: skip
        else:
            pane.text(Text.assemble(at, "  ", " ".join(str(d.get("text") or "").split())))
    if rows:
        return pane.render()
    lines = [line for line in R.tail(a.get("log"), 200) if not line.startswith('{"type"')]
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
    ran = forks(store.node_log(node.id, ("started", "model", "fork")), node.state)
    if ran:  # its last attempt's forks: the one that won first, then why each other one did not
        pane.gap()
        pane.text("forks", "bold")
        for f in sorted(ran, key=lambda f: f["state"] != "passed"):
            word = "won" if f["state"] == "passed" else f["state"]
            said = Text.assemble(f"fork {f['fork']} of {f['of']}  ", (word, _look(f["state"])[1]))
            said.append((f": {f['why']}" if f.get("why") else "") + " · " + _short(f["model"]))
            if "ops" in f and f["state"] != "running":
                said.append(f" · {f['ops']} operations, {f['seconds']:.1f} s")
            pane.text(said, indent=2)
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


def run(root: Path, open_store: Callable, every: float = 1.0, view: str | None = None) -> None:
    Watch(root, open_store, every, view).run()
