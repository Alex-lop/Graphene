"""`i` on a row (⏎, on one that waits for nothing): everything about one task, in four panes the old watch
already knew how to write.

contract (what it is for, its scope and check, why it came back), output (what the agent did and said,
newest last), changes (what it changed, whole, as `graphene node diff` shows it) and record (each hold: who,
when, how it ended, what the check said, what was refused). 1 to 4 show one, Tab goes on, Esc goes back: no
key here means what it means one screen down (d drop, r run). They are the same builders the classic screen
uses (`tui.detail`, `tail_pane`, `diff_pane`, `record_pane`), so a row reads the same here, but for the
classic screen's keys, which this screen does not bind (`untold`): the row's own keys act in the cockpit.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from .. import plan as P
from .. import tui
from .. import views as V
from .lines import fit_keys
from .rows import kept_said

PANES = ("contract", "output", "changes", "record")
DIRECTION = ("direction",)  # D: the goals above your plans, a pane of its own
KEYS = {"1": "contract", "2": "output", "3": "changes", "4": "record", "c": "changes"}  # c: the README's diff


REPLAYED = "a replay keeps no commits: what each task changed is in 4 record; in your repo this is its diff"


def pane_text(
    store, root: Path, node_id: str, which: str, wide: int, high: int = 20, replay: bool = False
) -> Text:
    """One pane for one node, as the person at this terminal would read it. A node that has left the plan,
    or a pane that cannot be made (git, a missing file), says so in a line: it never crashes the screen. Each
    is made in ``root``, whatever directory the screen was started in; a replay (``replay``) has no commits,
    so its changes pane says where what changed is instead of asking git."""
    if which == "direction":
        return tui.direction_pane(store, root, wide)
    nodes, words, _goal = V.inputs(store)
    by_id = {n.id: n for n in nodes}
    node = by_id.get(node_id)
    if node is None:
        return Text(f"{node_id} is not in the plan any more", style="grey62")
    s = SimpleNamespace(
        words=words, nodes=nodes, under=P.kids(nodes, drawn=True), by_id=by_id, root_path=root, counts={},
        events=None,
    )  # fmt: skip
    word = words.get(node_id, "")
    if which == "changes" and replay:
        return Text(REPLAYED, style="grey62")
    try:
        with contextlib.chdir(root):  # the command a pane runs (node diff) reads the plan where it runs
            if which == "output":
                return tui.tail_pane(store, node, root, wide)
            if which == "changes":
                return tui.diff_pane(store, node, word, wide)
            if which == "record":
                record, forks = tui.record_pane(store, node, s, wide), forks_text(store, node_id)
                return Text("\n\n").join([record, forks]) if forks else record
            return untold(tui.detail(store, node, s, P.tracked(root), (wide, high)))
    except Exception as no:  # a pane is a view: whatever went wrong, the screen stays up
        return Text(f"the {which} pane could not be made: {type(no).__name__}: {no}", style="#ef476f")


COLUMNS = ("fork", "with", "attempts", "state", "lines", "dollars", "seconds")


def forks_text(store, node_id: str) -> Text | None:
    """The forks of the node's last hold, when it forked (its `forked` row): a table, a fork a row, from its
    last `fork` row (none yet: running, with what the `forked` row said it runs with), then the fork kept,
    the rule's reason and by whom, from the `picked` row. None for a hold that did not fork."""
    log = store.node_log(node_id, ("started", "forked", "fork", "picked"))
    held = log[max((k for k, e in enumerate(log) if e["kind"] == "started"), default=-1) + 1 :]
    forked = next((e["detail"] for e in held if e["kind"] == "forked"), None)
    if forked is None:
        return None
    last = {str(e["detail"].get("fork")): e["detail"] for e in held if e["kind"] == "fork"}
    rows = [COLUMNS]
    for letter in forked.get("forks") or []:
        f = last.get(str(letter), {})
        dollars, seconds = f.get("dollars"), f.get("seconds")
        rows.append((str(letter), str(f.get("with") or (forked.get("with") or {}).get(letter) or ""),
                     str(f.get("attempts") or ""), str(f.get("state") or "running"),
                     "" if f.get("lines") is None else str(f["lines"]),
                     V.money(dollars) if dollars else "",
                     V.elapsed(int(seconds)) if seconds else ""))  # fmt: skip
    wide = [max(len(r[k]) for r in rows) for k in range(len(COLUMNS))]
    out = Text("forks", "bold")
    for k, r in enumerate(rows):
        out.append("\n  " + "  ".join(cell.ljust(w) for cell, w in zip(r, wide, strict=True)).rstrip(),
                   "dim" if k == 0 else "")  # fmt: skip
    picked = next((e["detail"] for e in reversed(held) if e["kind"] == "picked"), None)
    if picked:
        kept = (str(picked.get("fork") or ""), str(picked.get("reason") or ""), str(picked.get("by") or ""))
        out.append("\n  " + kept_said(kept))
    else:
        out.append("\n  none kept yet", "dim")
    return out


OFFER = re.compile(r"  [wbnrt]  ")  # a way out of a task that came back, as the classic pane has it: its key
ROW_KEYS = "the row's keys act on the screen under this one: Esc goes back to it"  # the cockpit, or the graph


def untold(text: Text) -> Text:
    """A task's contract without the classic screen's keys, which this screen does not bind: the ways out of a
    task that came back (w b n r, and t, which asks the planner there and tells the agent in the cockpit),
    each with what it does and the command under it, and `l shows the tool calls`, which 2 shows here. In the
    ways out's place, once, a line says where the row's keys act."""
    kept, gone, at = [], "", None
    for line in text.split("\n", allow_blank=True):
        said = line.plain
        if OFFER.match(said):
            gone, at = "offer", len(kept) if at is None else at
        elif said.startswith("its output is the session's"):
            gone = "sentence"
        elif not (gone == "offer" and said.startswith("     ") or gone == "sentence" and said.strip()):
            gone = ""  # past what it does and its command (indented), past the sentence (to its blank line)
        if not gone:
            kept.append(line)
    if at is not None:
        kept.insert(at, Text(ROW_KEYS, style="dim"))
    return Text("\n").join(kept)


class Details(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", show=False), Binding("q", "close", show=False),
        Binding("tab", "next", show=False), Binding("j", "scroll(1)", show=False),
        Binding("down", "scroll(1)", show=False), Binding("k", "scroll(-1)", show=False),
        Binding("up", "scroll(-1)", show=False), Binding("ctrl+d", "page(1)", show=False),
        Binding("ctrl+u", "page(-1)", show=False), Binding("space", "page(1)", show=False),
        *(Binding(key, f"show('{which}')", show=False) for key, which in KEYS.items()),
    ]  # fmt: skip
    DEFAULT_CSS = """
    Details { background: #0e1014; }
    #title { height: 1; background: #181b22; padding: 0 1; }
    #body { padding: 0 1; }
    #foot { height: 1; background: #181b22; color: #7d8492; padding: 0 1; }
    """

    def __init__(
        self, open_store: Callable, root: Path, node_id: str, title: str, which: str = "contract",
        panes: tuple[str, ...] = PANES, replay: bool = False,
    ):  # fmt: skip
        super().__init__()
        self.open_store, self.root, self.node_id, self.title_text = open_store, root, node_id, title
        self.panes, self.replay = panes, replay
        self.which = which if which in panes else panes[0]

    def compose(self) -> ComposeResult:
        yield Static(id="title")
        with VerticalScroll(id="body"):
            yield Static(id="pane", markup=False)
        yield Static(id="foot")

    def on_mount(self) -> None:
        self.show(self.which)
        self.feet()
        self.set_interval(1.0, self.refresh_pane)  # an agent's output moves

    def on_resize(self) -> None:
        self.feet()

    def feet(self) -> None:
        """The keys this screen has, in the room there is (Esc back always); a lone pane has no Tab."""
        many = len(self.panes) > 1
        pieces = ["Tab next pane", f"1-{len(self.panes)} a pane"] if many else []
        pieces += ["j k scroll", "Esc back"]
        room = max(self.size.width - 3, 20)
        self.query_one("#foot", Static).update(" " + fit_keys(" · ".join(pieces), room))

    def show(self, which: str) -> None:
        self.which = which
        tabs = Text(" ")
        for k, name in enumerate(self.panes, 1):  # numbered, as the keys that show them
            shown = f" {k} {name} " if len(self.panes) > 1 else f" {name} "
            tabs.append(shown, style="bold reverse #4cc9f0" if name == which else "grey62")
            tabs.append(" ")
        tabs.append(f" {self.title_text}", style="bold")
        self.query_one("#title", Static).update(tabs)
        self.refresh_pane()

    def refresh_pane(self) -> None:
        if not self.app.is_running:  # a tick while the app shuts down: its widgets are going (as `look`)
            return
        wide = max(self.size.width - 4, 40)
        high = max(self.size.height - 4, 10)
        try:
            with self.open_store() as store:
                text = pane_text(store, self.root, self.node_id, self.which, wide, high, self.replay)
        except Exception as no:  # a store too busy to open: the pane stays as it was, and says so
            text = Text(f"the plan's store did not open ({no}); the pane is as it was", style="#ef476f")
        self.query_one("#pane", Static).update(text)

    def action_show(self, which: str) -> None:
        if which in self.panes:
            self.show(which)

    def action_next(self) -> None:
        self.show(self.panes[(self.panes.index(self.which) + 1) % len(self.panes)])

    def action_scroll(self, lines: int) -> None:
        self.query_one("#body", VerticalScroll).scroll_relative(y=lines, animate=False)

    def action_page(self, way: int) -> None:
        body = self.query_one("#body", VerticalScroll)
        body.scroll_relative(y=way * max(body.size.height - 2, 3), animate=False)

    def action_close(self) -> None:
        self.dismiss(None)
