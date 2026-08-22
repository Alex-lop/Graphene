from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from graphene.shadow.events import ShadowEvent
from graphene.shadow.reconstruct import (
    GAP_SECONDS,
    LABEL_LIMIT,
    SEGMENTS_VERSION,
    ShadowGraph,
    graph_to_dot,
    reconstruct,
    segment_id_for,
)

_BASE = datetime(2026, 8, 22, 10, 0, 0, tzinfo=UTC)
_ACTORS = {
    "message": "user",
    "check_result": "tool",
    "command_result": "tool",
    "tool_result": "tool",
}
_CLAIM = {"matcher": "claims.v1", "category": "checks_pass", "pattern_id": "tests-pass"}


def _ts(seconds: int) -> str:
    return (_BASE + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event(seq: int, kind: str, **over: object) -> ShadowEvent:
    fields: dict[str, object] = {
        "session_id": "sess-1",
        "seq": seq,
        "actor": _ACTORS.get(kind, "agent"),
        "kind": kind,
        "provenance": "observed",
        "source": {
            "adapter": "ndjson",
            "adapter_version": "1.0.0",
            "record_ref": f"line:{seq}",
            "raw_type": "test",
        },
    }
    fields.update(over)
    return ShadowEvent.create(**fields)


def _claim(seq: int, message: ShadowEvent) -> ShadowEvent:
    return _event(
        seq,
        "claim",
        provenance="inferred",
        derived_from=(message.event_id,),
        claim=_CLAIM,
        excerpt=message.excerpt,
    )


def _ranges(graph: ShadowGraph) -> list[tuple[str, int, int, str]]:
    return [(s.segment_id, s.start_seq, s.end_seq, s.boundary) for s in graph.segments]


def test_session_start_then_user_message_boundaries():
    events = [
        _event(1, "message", excerpt="Fix the bug"),
        _event(2, "file_edit", paths=("app/a.py",)),
        _event(3, "message", excerpt="Now add tests"),
        _event(4, "file_create", paths=("tests/test_a.py",)),
    ]

    graph = reconstruct(events)

    assert graph.segments_version == SEGMENTS_VERSION
    assert graph.session_id == "sess-1"
    assert _ranges(graph) == [
        ("seg_0001", 1, 2, "session_start"),
        ("seg_0002", 3, 4, "user_message"),
    ]
    assert [segment.label for segment in graph.segments] == [
        "Fix the bug",
        "Now add tests",
    ]
    assert [segment.index for segment in graph.segments] == [1, 2]
    assert all(segment.provenance == "inferred" for segment in graph.segments)


def test_first_event_that_is_not_a_user_message_opens_an_unlabelled_segment():
    graph = reconstruct([_event(1, "file_edit", paths=("a.py",))])

    assert _ranges(graph) == [("seg_0001", 1, 1, "session_start")]
    assert graph.segments[0].label is None


def test_consecutive_user_messages_merge_instead_of_opening_empty_segments():
    events = [
        _event(1, "message", excerpt="first"),
        _event(2, "message", excerpt="second"),
        _event(3, "file_edit", paths=("a.py",)),
        _event(4, "message", excerpt="third"),
        _event(5, "message", excerpt="fourth", ts=_ts(GAP_SECONDS * 10)),
        _event(6, "file_edit", paths=("b.py",)),
    ]

    graph = reconstruct(events)

    assert _ranges(graph) == [
        ("seg_0001", 1, 3, "session_start"),
        ("seg_0002", 4, 6, "user_message"),
    ]
    assert [segment.label for segment in graph.segments] == ["first", "third"]
    assert [segment.event_count for segment in graph.segments] == [3, 3]


def test_gap_boundary_uses_timestamped_events_only():
    events = [
        _event(1, "file_edit", paths=("a.py",), ts=_ts(0)),
        _event(2, "file_edit", paths=("a.py",), ts=_ts(GAP_SECONDS)),
        _event(3, "file_edit", paths=("a.py",), ts=_ts(2 * GAP_SECONDS + 1)),
        _event(4, "file_edit", paths=("a.py",)),
        _event(5, "file_edit", paths=("a.py",), ts=_ts(2 * GAP_SECONDS + 100)),
    ]

    graph = reconstruct(events)

    assert _ranges(graph) == [
        ("seg_0001", 1, 2, "session_start"),
        ("seg_0002", 3, 5, "gap"),
    ]
    assert graph.segments[1].label is None


def test_gap_accepts_fractional_timestamps():
    events = [
        _event(1, "file_edit", paths=("a.py",), ts="2026-08-22T10:00:00.123456789Z"),
        _event(2, "file_edit", paths=("a.py",), ts="2026-08-22T10:20:00.5Z"),
    ]

    graph = reconstruct(events)

    assert _ranges(graph) == [
        ("seg_0001", 1, 1, "session_start"),
        ("seg_0002", 2, 2, "gap"),
    ]


@pytest.mark.parametrize(
    ("marker", "label"),
    (
        (dict(kind="tool_call", tool="TodoWrite"), "TodoWrite"),
        (dict(kind="tool_call", tool="update_plan"), "update_plan"),
        (dict(kind="tool_call", tool="plan"), "plan"),
        (
            dict(kind="message", actor="agent", excerpt="## Plan for the fix"),
            "## Plan for the fix",
        ),
        (
            dict(kind="message", actor="agent", excerpt="Plan: split the module"),
            "Plan: split the module",
        ),
    ),
)
def test_plan_marker_boundaries(marker: dict[str, object], label: str):
    kind = str(marker.pop("kind"))
    events = [
        _event(1, "message", excerpt="Do the thing"),
        _event(2, "file_edit", paths=("a.py",)),
        _event(3, kind, **marker),
        _event(4, "file_edit", paths=("b.py",)),
    ]

    graph = reconstruct(events)

    assert _ranges(graph) == [
        ("seg_0001", 1, 2, "session_start"),
        ("seg_0002", 3, 4, "plan_marker"),
    ]
    assert graph.segments[1].label == label


@pytest.mark.parametrize(
    "marker",
    (
        dict(kind="message", actor="agent", excerpt="The plan is fine"),
        dict(kind="message", actor="user", excerpt="## Plan"),
        dict(kind="tool_call", actor="tool", tool="TodoWrite"),
    ),
)
def test_non_markers_do_not_open_plan_segments(marker: dict[str, object]):
    kind = str(marker.pop("kind"))
    events = [
        _event(1, "file_edit", paths=("a.py",)),
        _event(2, kind, **marker),
        _event(3, "file_edit", paths=("b.py",)),
    ]

    graph = reconstruct(events)

    assert all(segment.boundary != "plan_marker" for segment in graph.segments)


def test_user_message_wins_over_gap_and_plan_marker_wins_over_gap():
    events = [
        _event(1, "file_edit", paths=("a.py",), ts=_ts(0)),
        _event(2, "message", excerpt="again", ts=_ts(5 * GAP_SECONDS)),
        _event(3, "tool_call", tool="TodoWrite", ts=_ts(10 * GAP_SECONDS)),
    ]

    graph = reconstruct(events)

    assert [segment.boundary for segment in graph.segments] == [
        "session_start",
        "user_message",
        "plan_marker",
    ]


def test_label_is_bounded_to_limit():
    long_text = "x" * (LABEL_LIMIT + 80)
    graph = reconstruct([_event(1, "message", excerpt=long_text)])

    label = graph.segments[0].label
    assert label is not None
    assert len(label) == LABEL_LIMIT
    assert label.endswith("…")


def test_path_sets_and_seq_lists_are_sorted_unique():
    message = _event(9, "message", actor="agent", excerpt="Tests pass.")
    events = [
        _event(1, "file_read", paths=("b.py",)),
        _event(2, "file_read", paths=("a.py", "b.py")),
        _event(3, "file_edit", paths=("z.py",)),
        _event(4, "file_create", paths=("m.py",)),
        _event(5, "file_delete", paths=("old.py",)),
        _event(6, "command_exec", argv_excerpt="ls"),
        _event(7, "check_run", check_family="pytest"),
        _event(8, "check_result", check_family="pytest", exit_code=0),
        message,
        _claim(10, message),
        _event(11, "install_op", argv_excerpt="uv sync"),
        _event(12, "vcs_op", argv_excerpt="git commit"),
        _event(13, "network_op", argv_excerpt="curl x"),
        _event(14, "command_result", exit_code=0),
    ]

    segment = reconstruct(events).segments[0]

    assert segment.paths_read == ("a.py", "b.py")
    assert segment.paths_written == ("m.py", "z.py")
    assert segment.paths_deleted == ("old.py",)
    assert segment.command_seqs == (6, 11, 12, 13)
    assert segment.check_seqs == (7, 8)
    assert segment.claim_seqs == (10,)
    assert segment.event_count == 14


def test_read_after_write_edge_present_when_later_segment_reads_the_path():
    events = [
        _event(1, "file_edit", paths=("app/a.py",)),
        _event(2, "message", excerpt="next"),
        _event(3, "file_read", paths=("app/a.py", "app/other.py")),
    ]

    graph = reconstruct(events)

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert (edge.src, edge.dst, edge.paths) == ("seg_0001", "seg_0002", ("app/a.py",))
    assert edge.relation == "read_after_write"
    assert edge.provenance == "inferred"


def test_edit_in_later_segment_consumes_but_create_does_not():
    edited = reconstruct(
        [
            _event(1, "file_create", paths=("a.py",)),
            _event(2, "message", excerpt="next"),
            _event(3, "file_edit", paths=("a.py",)),
        ]
    )
    created = reconstruct(
        [
            _event(1, "file_create", paths=("a.py",)),
            _event(2, "message", excerpt="next"),
            _event(3, "file_create", paths=("a.py",)),
        ]
    )

    assert [(e.src, e.dst) for e in edited.edges] == [("seg_0001", "seg_0002")]
    assert created.edges == ()


def test_no_edge_without_shared_paths_and_never_backwards():
    unrelated = reconstruct(
        [
            _event(1, "file_edit", paths=("a.py",)),
            _event(2, "message", excerpt="next"),
            _event(3, "file_read", paths=("b.py",)),
        ]
    )
    read_first = reconstruct(
        [
            _event(1, "file_read", paths=("a.py",)),
            _event(2, "message", excerpt="next"),
            _event(3, "file_edit", paths=("a.py",)),
        ]
    )

    assert unrelated.edges == ()
    assert read_first.edges == ()


def test_edges_span_non_adjacent_segments_and_carry_sorted_paths():
    events = [
        _event(1, "file_edit", paths=("a.py", "b.py", "c.py")),
        _event(2, "message", excerpt="middle"),
        _event(3, "file_read", paths=("unrelated.py",)),
        _event(4, "message", excerpt="last"),
        _event(5, "file_read", paths=("c.py",)),
        _event(6, "file_edit", paths=("a.py",)),
    ]

    graph = reconstruct(events)

    assert [(e.src, e.dst, e.paths) for e in graph.edges] == [
        ("seg_0001", "seg_0003", ("a.py", "c.py"))
    ]


def test_timeline_excludes_messages_and_counts_provenance():
    message = _event(3, "message", actor="agent", excerpt="All tests pass.")
    events = [
        _event(1, "message", excerpt="go"),
        _event(2, "check_result", check_family="pytest", exit_code=0),
        message,
        _claim(4, message),
        _event(5, "unknown"),
        _event(6, "message", excerpt="more"),
        _event(7, "file_edit", paths=("a.py",), outside_paths=("~/notes.txt",)),
    ]

    graph = reconstruct(events)

    assert [entry.seq for entry in graph.timeline] == [2, 4, 5, 7]
    assert [entry.kind for entry in graph.timeline] == [
        "check_result",
        "claim",
        "unknown",
        "file_edit",
    ]
    assert [entry.segment_id for entry in graph.timeline] == [
        "seg_0001",
        "seg_0001",
        "seg_0001",
        "seg_0002",
    ]
    assert graph.timeline[0].check_family == "pytest"
    assert graph.timeline[0].exit_code == 0
    assert graph.timeline[1].provenance == "inferred"
    assert graph.timeline[3].outside_paths == ("~/notes.txt",)
    assert graph.timeline[3].event_id == events[6].event_id
    assert (graph.event_count, graph.observed_count, graph.inferred_count) == (7, 6, 1)
    assert graph.unknown_count == 1


def test_dot_output_has_nodes_edges_and_inferred_marks():
    events = [
        _event(1, "message", excerpt='Fix "quotes" \\ slashes'),
        _event(2, "file_edit", paths=("a.py", "b.py", "c.py", "d.py")),
        _event(3, "message", excerpt="read it"),
        _event(4, "file_read", paths=("a.py", "b.py", "c.py", "d.py")),
    ]

    dot = graph_to_dot(reconstruct(events))

    assert dot.startswith("digraph shadow {\n")
    assert dot.endswith("}\n")
    assert (
        '  "seg_0001" [label="seg_0001\\nFix \\"quotes\\" \\\\ slashes\\nwrites=4" '
        'provenance="inferred"];'
    ) in dot
    assert (
        '"seg_0002" [label="seg_0002\\nread it\\nwrites=0" provenance="inferred"];'
    ) in dot
    assert (
        '  "seg_0001" -> "seg_0002" [label="a.py\\nb.py\\nc.py\\n+1 more" '
        'provenance="inferred"];'
    ) in dot
    assert "inferred" in dot
    assert SEGMENTS_VERSION in dot


def test_dot_uses_boundary_when_segment_has_no_label():
    events = [
        _event(1, "file_edit", paths=("a.py",), ts=_ts(0)),
        _event(2, "file_edit", paths=("a.py",), ts=_ts(2 * GAP_SECONDS)),
    ]

    dot = graph_to_dot(reconstruct(events))

    assert 'label="seg_0001\\n(session_start)\\nwrites=1"' in dot
    assert 'label="seg_0002\\n(gap)\\nwrites=1"' in dot


def test_reconstruct_rejects_empty_noncontiguous_and_mixed_streams():
    with pytest.raises(ValueError, match="empty"):
        reconstruct([])
    with pytest.raises(ValueError, match="contiguity"):
        reconstruct([_event(1, "unknown"), _event(3, "unknown")])
    with pytest.raises(ValueError, match="session identifiers"):
        reconstruct([_event(1, "unknown"), _event(2, "unknown", session_id="other")])
    with pytest.raises(TypeError, match="verified shadow events"):
        reconstruct([{"seq": 1}])  # type: ignore[list-item]


def test_graph_round_trips_through_json():
    events = [
        _event(1, "message", excerpt="go"),
        _event(2, "file_edit", paths=("a.py",)),
        _event(3, "message", excerpt="again"),
        _event(4, "file_read", paths=("a.py",)),
    ]
    graph = reconstruct(events)

    restored = ShadowGraph.model_validate(json.loads(graph.model_dump_json()))

    assert restored == graph


def test_graph_model_fails_closed_on_inconsistent_shapes():
    graph = reconstruct([_event(1, "file_edit", paths=("a.py",)), _event(2, "unknown")])
    payload = graph.model_dump(mode="json")

    broken_count = {**payload, "event_count": 3, "observed_count": 3}
    with pytest.raises(ValueError, match="cover every event"):
        ShadowGraph.model_validate(broken_count)
    backwards = {
        **payload,
        "edges": [{"src": "seg_0001", "dst": "seg_0001", "paths": ["a.py"]}],
    }
    with pytest.raises(ValueError, match="earlier to a later"):
        ShadowGraph.model_validate(backwards)
    assert segment_id_for(12) == "seg_0012"
    with pytest.raises(ValueError, match="1-based"):
        segment_id_for(0)
