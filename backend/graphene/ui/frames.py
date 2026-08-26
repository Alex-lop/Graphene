"""One plain-text frame of the terminal view, for `--once`, frame dumps, and tests."""

from __future__ import annotations

from .dag_render import assert_no_arrow_art, nodes_from_snapshot, render_banner, render_dag
from .sources import UiSource, stage_for_tasks, summary_pane, why_pane
from ..orchestration.mission_projection import MissionControlSnapshot, task_detail


def compose_frame(
    source: UiSource,
    *,
    selected: str | None = None,
    pane: str | None = None,
    snapshot: MissionControlSnapshot | None = None,
) -> str:
    """Banner, DAG, and optionally a pane, as plain text with no escape codes."""

    if snapshot is None:
        snapshot = source.snapshot()
    if snapshot is None:
        return f"GRAPHENE  ·  waiting for the store ({source.notice() or 'no snapshot yet'})"
    banner = render_banner(
        mission_id=snapshot.mission.mission_id,
        status=str(snapshot.mission.status),
        plan_revision=snapshot.mission.plan_revision,
        plan_sha256=snapshot.mission.plan_sha256,
        approved_plan_revision=snapshot.mission.approved_plan_revision,
        source=f"{source.label} · {source.position()}",
    ).plain
    nodes, deps = nodes_from_snapshot(snapshot, stages=stage_for_tasks(snapshot, source.stages()), selected=selected)
    dag = render_dag(nodes, deps).plain
    parts = [banner, "", dag]
    if pane == "summary":
        parts += ["", summary_pane(snapshot).plain]
    elif pane == "why" and selected:
        parts += ["", why_pane(task_detail(snapshot, selected), source.lineage(selected), source_label=source.label).plain]
    notice = source.notice()
    if notice:
        parts += ["", notice]
    frame = "\n".join(parts)
    assert_no_arrow_art(frame)
    return frame
