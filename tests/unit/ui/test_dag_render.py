"""The DAG renderer: layout, edges, states, banner, and the no-arrow-art rule."""

from __future__ import annotations

import pytest

from graphene.orchestration.mission_replay import load_verified_mission_replay
from graphene.ui.dag_render import (
    DagNode,
    assert_no_arrow_art,
    nodes_from_snapshot,
    render_banner,
    render_dag,
)

BOX_EDGE_CHARS = set("│─┌┐└┘├┤┬┴┼▼")


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _card_row(lines: list[str], node_id: str) -> int:
    return next(i for i, line in enumerate(lines) if f"│ {node_id}" in line or f"┃ {node_id}" in line)


def test_replay_fixture_renders_every_node_state_and_edge_top_to_bottom() -> None:
    replay = load_verified_mission_replay()
    stage = replay.stages[3]  # render_markdown retrying, redact_notes running
    nodes, deps = nodes_from_snapshot(stage)
    plain = render_dag(nodes, deps).plain
    lines = _lines(plain)

    for task in stage.tasks:
        assert task.task_id in plain
        assert f" {task.state}" in plain
    # Dependencies are drawn above their dependents.
    assert _card_row(lines, "redact_notes") < _card_row(lines, "wire_cli")
    assert _card_row(lines, "wire_cli") < _card_row(lines, "assemble") < _card_row(lines, "verify")
    # Three work nodes converge on wire_cli through a bus row with an arrow into it.
    bus = lines[_card_row(lines, "redact_notes") + 4]
    assert bus.count("┴") + bus.count("┬") >= 2 and "─" in bus
    assert "▼" in lines[_card_row(lines, "wire_cli") - 2]
    assert BOX_EDGE_CHARS & set(plain)
    assert_no_arrow_art(plain)


def test_states_carry_glyph_and_cancelled_carries_its_stage() -> None:
    nodes = [
        DagNode("a", "done"),
        DagNode("b", "cancelled", detail="store-check-receipt"),
        DagNode("c", "failed"),
        DagNode("d", "queued"),
    ]
    plain = render_dag(nodes, {"b": ("a",), "c": ("a",), "d": ("b", "c")}).plain
    assert "✓ done" in plain and "✗ failed" in plain and "○ queued" in plain
    assert "⊘ cancelled · store-check-receipt" in plain
    assert_no_arrow_art(plain)


def test_an_edge_that_skips_a_layer_is_routed_through_a_pass_through_not_across_a_card() -> None:
    # work_a -> work_b -> assemble, and assemble also depends on work_a directly:
    # that edge spans two layers and must pass beside work_b, not through it.
    nodes = [DagNode("work_a", "done"), DagNode("work_b", "running"), DagNode("assemble", "queued")]
    plain = render_dag(nodes, {"work_b": ("work_a",), "assemble": ("work_a", "work_b")}).plain
    lines = _lines(plain)
    row = _card_row(lines, "work_b")
    top = lines[row - 1]
    left, right = top.index("┌"), top.index("┐")
    card = lines[row][left : right + 1]
    assert card.count("│") == 2, card  # nothing crosses the card's interior
    # A vertical pass-through exists on the card rows outside the card.
    outside = lines[row][:left] + lines[row][right + 1 :]
    assert "│" in outside, lines[row]
    assert_no_arrow_art(plain)


def test_selected_node_is_drawn_with_a_heavy_border() -> None:
    nodes, deps = nodes_from_snapshot(load_verified_mission_replay().stages[0], selected="render_json")
    plain = render_dag(nodes, deps).plain
    assert "┃ render_json" in plain and "┏" in plain
    assert "│ redact_notes" in plain


def test_banner_names_mission_revision_digest_and_signed_state() -> None:
    signed = render_banner(
        mission_id="mission_x", status="running", plan_revision=2,
        plan_sha256="b48aabfb4827" + "0" * 52, approved_plan_revision=2,
    ).plain
    assert "mission_x" in signed and "PLAN v2" in signed and "digest b48aabfb4827" in signed
    assert "SIGNED — revision 2 approved" in signed
    stale = render_banner(
        mission_id="mission_x", status="proposed", plan_revision=2,
        plan_sha256="b48aabfb4827" + "0" * 52, approved_plan_revision=1,
    ).plain
    assert "UNSIGNED" in stale and "revision 1 was signed" in stale
    unsigned = render_banner(
        mission_id="mission_x", status="proposed", plan_revision=1, plan_sha256=None, approved_plan_revision=None,
    ).plain
    assert "UNSIGNED — nothing runs until you sign" in unsigned and "no digest" in unsigned


def test_the_no_arrow_art_rule_can_fail() -> None:
    """A guard that cannot fire is decoration; prove it fires on planted art."""

    with pytest.raises(AssertionError):
        assert_no_arrow_art("redact_notes -> wire_cli -> assemble")
    assert_no_arrow_art("│ redact_notes │\n└──┬──┘\n   ▼")


def test_a_dependency_cycle_is_refused_not_drawn_forever() -> None:
    with pytest.raises(ValueError, match="cycle"):
        render_dag([DagNode("a", "queued"), DagNode("b", "queued")], {"a": ("b",), "b": ("a",)})
