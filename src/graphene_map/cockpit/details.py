"""`i` on a row (⏎, on one that waits for nothing): everything about one task, in four panes the old watch
already knew how to write.

contract (what it is for, its scope and check, why it came back), output (what the agent did and said,
newest last), changes (what it changed, whole, as `graphene node diff` shows it) and record (each hold: who,
when, how it ended, what the check said, what was refused). Tab goes on; Esc goes back. They are the same
builders the classic screen uses (`tui.detail`, `tail_pane`, `diff_pane`, `record_pane`), so a row reads the
same here.
"""

from __future__ import annotations

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
KEYS = {"d": "contract", "l": "output", "c": "changes", "r": "record"}  # a key, and the pane it shows


def pane_text(store, root: Path, node_id: str, which: str, wide: int, high: int = 20) -> Text:
    """One pane for one node, as the person at this terminal would read it. A node that has left the plan,
    or a pane that cannot be made (git, a missing file), says so in a line: it never crashes the screen."""
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
    try:
        if which == "output":
            return tui.tail_pane(store, node, root, wide)
        if which == "changes":
            return tui.diff_pane(store, node, word, wide)
        if which == "record":
            return tui.record_pane(store, node, s, wide)
        return tui.detail(store, node, s, P.tracked(root), (wide, high))
    except Exception as no:  # a pane is a view: whatever went wrong, the screen stays up
        return Text(f"the {which} pane could not be made: {type(no).__name__}: {no}", style="#ef476f")


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
        panes: tuple[str, ...] = PANES,
    ):  # fmt: skip
        super().__init__()
        self.open_store, self.root, self.node_id, self.title_text = open_store, root, node_id, title
        self.panes = panes
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
        pieces = ["Tab next pane"] if many else []
        pieces += [f"{key} {pane}" for key, pane in KEYS.items() if many and pane in self.panes]
        pieces += ["j k scroll", "Esc back"]
        room = max(self.size.width - 3, 20)
        self.query_one("#foot", Static).update(" " + fit_keys(" · ".join(pieces), room))

    def show(self, which: str) -> None:
        self.which = which
        tabs = Text(" ")
        for name in self.panes:
            tabs.append(f" {name} ", style="bold reverse #4cc9f0" if name == which else "grey62")
            tabs.append(" ")
        tabs.append(f" {self.title_text}", style="bold")
        self.query_one("#title", Static).update(tabs)
        self.refresh_pane()

    def refresh_pane(self) -> None:
        wide = max(self.size.width - 4, 40)
        high = max(self.size.height - 4, 10)
        try:
            with self.open_store() as store:
                text = pane_text(store, self.root, self.node_id, self.which, wide, high)
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
