"""`graphene ui`: the signed map in the terminal, followed live, read-only.

Textual was chosen over a hand-rolled Rich Live loop because the directive's
acceptance needs key handling (select a node, drill in, quit with the terminal
restored) and headless snapshot tests; Textual's `run_test` pilot gives both
without a raw-mode terminal shim. Rendering itself is the pure code in
`dag_render.py` and `sources.py`; this module only places it on screen.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from ..orchestration.mission_projection import task_detail
from .dag_render import nodes_from_snapshot, render_banner, render_dag
from .sources import UiSource, stage_for_tasks, summary_pane, why_pane

_TERMINAL = {"completed", "failed", "cancelled", "rejected"}


class GrapheneUI(App[None]):
    CSS = """
    Screen { layout: vertical; }
    #banner { height: auto; padding: 0 1; background: $panel; }
    #body { height: 1fr; }
    #dag-scroll { width: 1fr; }
    #dag { padding: 0 1; }
    #pane-scroll { width: 52; border-left: solid $primary; display: none; }
    #pane-scroll.open { display: block; }
    #pane { padding: 0 1; }
    #status { height: 1; padding: 0 1; color: $text-muted; }
    """
    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("j,down", "select_next", "next node"),
        Binding("k,up", "select_prev", "previous node"),
        Binding("enter", "drill", "why"),
        Binding("s", "summary", "summary"),
        Binding("escape", "close_pane", "close pane"),
        Binding("n,right", "step_forward", "next checkpoint"),
        Binding("p,left", "step_back", "previous checkpoint"),
    ]

    def __init__(
        self,
        source: UiSource,
        *,
        poll_seconds: float = 0.25,
        autoplay_seconds: float | None = None,
    ) -> None:
        super().__init__()
        self.source = source
        self.poll_seconds = poll_seconds
        self.autoplay_seconds = autoplay_seconds
        self.selected: str | None = None
        self.pane: str | None = None
        self.task_ids: tuple[str, ...] = ()
        self.last_plain = ""

    def compose(self) -> ComposeResult:
        yield Static(id="banner")
        with Horizontal(id="body"):
            with VerticalScroll(id="dag-scroll"):
                yield Static(id="dag")
            with VerticalScroll(id="pane-scroll"):
                yield Static(id="pane")
        yield Static(id="status")

    def on_mount(self) -> None:
        self.refresh_view()
        if self.source.label == "live":
            self.set_interval(self.poll_seconds, self.refresh_view)
        if self.autoplay_seconds:
            self.set_interval(self.autoplay_seconds, self._autoplay)

    def _autoplay(self) -> None:
        if self.source.step(1):
            self.refresh_view()

    def refresh_view(self) -> None:
        snapshot = self.source.snapshot()
        status = self.query_one("#status", Static)
        if snapshot is None:
            status.update(f"waiting for the store · {self.source.notice() or ''} · q quit")
            return
        self.task_ids = tuple(task.task_id for task in snapshot.tasks)
        if self.selected not in self.task_ids:
            self.selected = None
        banner = render_banner(
            mission_id=snapshot.mission.mission_id,
            status=str(snapshot.mission.status),
            plan_revision=snapshot.mission.plan_revision,
            plan_sha256=snapshot.mission.plan_sha256,
            approved_plan_revision=snapshot.mission.approved_plan_revision,
            source=f"{self.source.label} · {self.source.position()}",
        )
        nodes, deps = nodes_from_snapshot(
            snapshot, stages=stage_for_tasks(snapshot, self.source.stages()), selected=self.selected
        )
        dag = render_dag(nodes, deps)
        self.query_one("#banner", Static).update(banner)
        self.query_one("#dag", Static).update(dag)
        pane = self.query_one("#pane", Static)
        pane_scroll = self.query_one("#pane-scroll", VerticalScroll)
        if self.pane == "summary":
            pane.update(summary_pane(snapshot))
            pane_scroll.add_class("open")
        elif self.pane == "why" and self.selected:
            detail = task_detail(snapshot, self.selected)
            pane.update(why_pane(detail, self.source.lineage(self.selected), source_label=self.source.label))
            pane_scroll.add_class("open")
        else:
            pane.update(Text(""))
            pane_scroll.remove_class("open")
        hint = "j/k select · enter why · s summary · q quit"
        if self.source.label == "replay":
            hint = "n/p step · " + hint
        finished = str(snapshot.mission.status) in _TERMINAL
        notice = self.source.notice()
        status.update(
            f"{self.source.position()} · {'finished — s for the summary · ' if finished else ''}{hint}"
            + (f" · {notice}" if notice else "")
        )
        self.last_plain = "\n".join((banner.plain, dag.plain, pane.content.plain if isinstance(pane.content, Text) else ""))

    def _move(self, delta: int) -> None:
        if not self.task_ids:
            return
        if self.selected is None:
            index = 0 if delta > 0 else len(self.task_ids) - 1
        else:
            index = (self.task_ids.index(self.selected) + delta) % len(self.task_ids)
        self.selected = self.task_ids[index]
        if self.pane == "summary":
            self.pane = None
        self.refresh_view()

    def action_select_next(self) -> None:
        self._move(1)

    def action_select_prev(self) -> None:
        self._move(-1)

    def action_drill(self) -> None:
        if self.selected is None and self.task_ids:
            self.selected = self.task_ids[0]
        self.pane = "why" if self.selected else None
        self.refresh_view()

    def action_summary(self) -> None:
        self.pane = None if self.pane == "summary" else "summary"
        self.refresh_view()

    def action_close_pane(self) -> None:
        self.pane = None
        self.refresh_view()

    def action_step_forward(self) -> None:
        if self.source.step(1):
            self.refresh_view()

    def action_step_back(self) -> None:
        if self.source.step(-1):
            self.refresh_view()
