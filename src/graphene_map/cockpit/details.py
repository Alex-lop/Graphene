"""`i` on a row (⏎, on one that waits for nothing): everything about one task, in four panes the old watch
already knew how to write.

contract (what it is for, its scope and check, why it came back), output (what the agent did and said,
newest last), changes (what it changed, whole, as `graphene node diff` shows it) and record (each hold: who,
when, how it ended, what the check said, what was refused). 1 to 4 show one, Tab goes on, Esc goes back: no
key here means what it means one screen down (d drop, r run). They are the same builders the classic screen
uses (`tui.detail`, `tail_pane`, `diff_pane`, `record_pane`), so a row reads the same here, but for the
classic screen's `t ask the planner`: in the cockpit t tells the agent.
"""

from __future__ import annotations

import contextlib
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
                return tui.record_pane(store, node, s, wide)
            return untold(tui.detail(store, node, s, P.tracked(root), (wide, high)))
    except Exception as no:  # a pane is a view: whatever went wrong, the screen stays up
        return Text(f"the {which} pane could not be made: {type(no).__name__}: {no}", style="#ef476f")


def untold(text: Text) -> Text:
    """A leaf that came back, without the classic screen's `t ask the planner` row (and the command under
    it, where the pane is narrow): the cockpit's t tells the agent, so the row would offer a key that does
    something else. `:ask` asks the planner."""
    kept, dropped = [], False
    for line in text.split("\n", allow_blank=True):
        said = line.plain.lstrip()
        dropped = said.startswith("t  ask the planner") or (dropped and said.startswith("graphene ask"))
        if not dropped:
            kept.append(line)
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
