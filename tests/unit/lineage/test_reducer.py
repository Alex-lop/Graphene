from __future__ import annotations

import pytest

from graphene.hashing import canonical_json_bytes, canonical_json_sha256
from graphene.lineage.reducer import ProjectionError, reduce_events
from graphene.models import (
    Event,
    EventInput,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    LineageRunState,
    SourceKind,
    SourceReference,
    TruthKind,
)

BASE_SHA = "a" * 40
VERSION_1 = "1" * 64
VERSION_2 = "2" * 64


def _events(*specs: tuple[LineageEventType, dict[str, object], str | None]) -> tuple[Event, ...]:
    events: list[Event] = []
    previous = None
    for seq, (event_type, payload, call_id) in enumerate(specs, 1):
        tool = event_type in {
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_FAILED,
        }
        policy = event_type in {
            LineageEventType.SCOPE_DENIED,
            LineageEventType.HANDOFF_DENIED,
            LineageEventType.COMPLETION_DENIED,
            LineageEventType.PROMOTION_DENIED,
        }
        adapter = event_type in {
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.INVOCATION_COMPLETED,
            LineageEventType.INVOCATION_FAILED,
            LineageEventType.COMPLETION_ATTEMPTED,
        }
        completion = event_type in {
            LineageEventType.COMPLETION_ATTEMPTED,
            LineageEventType.COMPLETION_DENIED,
        }
        promotion = event_type == LineageEventType.PROMOTION_COMPLETED
        draft = EventInput(
            session_id="session_1" if tool or adapter or completion else None,
            invocation_id="invocation_1" if tool or adapter or completion else None,
            model_id="model-test" if tool or adapter or completion else None,
            tool_call_id=call_id,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=event_type,
            truth_kind=(
                TruthKind.RUNTIME_OBSERVED
                if tool
                else TruthKind.MODEL_PROPOSED
                if event_type == LineageEventType.COMPLETION_ATTEMPTED
                else TruthKind.POLICY_AUTHORITATIVE
                if policy
                else TruthKind.SERVER_DERIVED
            ),
            authority=(
                LineageAuthority.SCOPED_TOOL_WRAPPER
                if tool
                else LineageAuthority.LOCAL_ADAPTER
                if event_type == LineageEventType.COMPLETION_ATTEMPTED
                else LineageAuthority.POLICY_ENGINE
                if policy
                else LineageAuthority.PROMOTION_SERVICE
                if promotion
                else LineageAuthority.LIFECYCLE_SERVICE
            ),
            references=(),
            source_ref=SourceReference(
                kind=(
                    SourceKind.TOOL_RECEIPT
                    if tool
                    else SourceKind.LOCAL_ADAPTER_RECEIPT
                    if event_type == LineageEventType.COMPLETION_ATTEMPTED
                    else SourceKind.POLICY_EVALUATION
                    if policy
                    else SourceKind.PROMOTION_RECEIPT
                    if promotion
                    else SourceKind.LIFECYCLE_REQUEST
                ),
                id=f"source_{seq}",
                sha256=f"{seq % 10}" * 64,
            ),
            payload=payload,
        )
        values = {
            **draft.model_dump(mode="json"),
            "schema_version": 2,
            "event_id": f"evt_{seq}",
            "run_id": "run_1",
            "seq": seq,
            "server_recorded_at": f"2026-08-12T12:00:{seq:02d}Z",
            "idempotency_key": f"event_key_{seq:08d}",
            "payload_sha256": canonical_json_sha256(payload),
            "previous_event_sha256": previous,
        }
        values["event_sha256"] = canonical_json_sha256(values)
        event = Event.model_validate(values)
        events.append(event)
        previous = event.event_sha256
    return tuple(events)


def _run_started():
    return LineageEventType.RUN_STARTED, {"state": "STARTING"}, None


def _read(call: str, *, completed: bool, version: str = VERSION_1):
    payload: dict[str, object] = {"operation": LineageOperation.READ_FILE.value}
    if completed:
        payload.update(
            path="app/auth/limiter.py",
            file_version_id=version,
            byte_count=2_048,
            line_count=40,
        )
    return (
        LineageEventType.TOOL_COMPLETED if completed else LineageEventType.TOOL_STARTED,
        payload,
        call,
    )


def test_identical_stream_is_byte_identical_and_reorder_is_rejected():
    events = _events(_run_started(), _read("call_1", completed=False), _read("call_1", completed=True))

    first = reduce_events(events)
    second = reduce_events(events)

    assert first == second
    assert canonical_json_bytes(first.model_dump(mode="json")) == canonical_json_bytes(
        second.model_dump(mode="json")
    )
    assert first.projection_sha256 == second.projection_sha256
    with pytest.raises(ProjectionError, match="sequence"):
        reduce_events((events[0], events[2], events[1]))


def test_repeated_reads_aggregate_but_every_event_remains_on_the_rail():
    events = _events(
        _run_started(),
        _read("call_1", completed=False),
        _read("call_1", completed=True),
        _read("call_2", completed=False),
        _read("call_2", completed=True),
    )

    projection = reduce_events(events)

    assert len(projection.files) == 1
    assert projection.files[0].model_dump() == {
        "path": "app/auth/limiter.py",
        "state": "READ",
        "file_version_id": VERSION_1,
        "baseline_bytes": 2_048,
        "baseline_lines": 40,
        "size_bucket": 2,
        "first_seq": 3,
        "last_seq": 5,
        "read_count": 2,
        "added_lines": 0,
        "deleted_lines": 0,
        "bound_test_pass": False,
    }
    assert [item.seq for item in projection.event_rail] == [1, 2, 3, 4, 5]


def test_denied_or_failed_action_never_exposes_a_file():
    events = _events(
        _run_started(),
        (
            LineageEventType.TOOL_STARTED,
            {"operation": "read_file"},
            "call_denied",
        ),
        (
            LineageEventType.TOOL_FAILED,
            {
                "operation": "read_file",
                "status": "denied",
                "error_code": "scope_denied",
            },
            "call_denied",
        ),
        (
            LineageEventType.SCOPE_DENIED,
            {
                "operation": "read_file",
                "status": "denied",
                "reason_code": "path_out_of_scope",
            },
            None,
        ),
    )

    projection = reduce_events(events)

    assert projection.state == LineageRunState.ACCESS_DENIED
    assert projection.files == ()
    assert all(item.path is None for item in projection.event_rail)


def test_write_preserves_exact_counts_and_only_bound_paths_receive_test_marker():
    path = "app/auth/limiter.py"
    events = _events(
        _run_started(),
        (LineageEventType.TOOL_STARTED, {"operation": "write_file"}, "call_write"),
        (
            LineageEventType.TOOL_COMPLETED,
            {
                "operation": "write_file",
                "path": path,
                "before_file_version_id": VERSION_1,
                "after_file_version_id": VERSION_2,
                "baseline_bytes": 1_700,
                "baseline_lines": 58,
                "added_lines": 7,
                "deleted_lines": 3,
                "state": "EDITED",
            },
            "call_write",
        ),
        (LineageEventType.TOOL_STARTED, {"operation": "run_fixed_test"}, "call_test"),
        (
            LineageEventType.TOOL_COMPLETED,
            {
                "operation": "run_fixed_test",
                "passed": True,
                "bound_paths": [path],
            },
            "call_test",
        ),
    )

    projection = reduce_events(events)
    changed = projection.files[0]

    assert (changed.state, changed.added_lines, changed.deleted_lines) == ("EDITED", 7, 3)
    assert changed.file_version_id == VERSION_2
    assert changed.bound_test_pass is True
    assert next(
        item for item in projection.obligations if item.obligation_id == "bound_fixed_test"
    ).status == "SATISFIED"


def test_visible_file_cap_has_an_exact_omission_count():
    paths = [f"src/file_{number:02d}.py" for number in range(20)]
    events = _events(
        _run_started(),
        (LineageEventType.TOOL_STARTED, {"operation": "search_repo"}, "call_search"),
        (
            LineageEventType.TOOL_COMPLETED,
            {"operation": "search_repo", "paths": paths},
            "call_search",
        ),
    )

    projection = reduce_events(events)

    assert len(projection.files) == 15
    assert projection.omitted_counts == {"files": 5, "directory:src": 5}
    assert tuple(item.path for item in projection.files) == tuple(paths[:15])


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        (LineageEventType.RUN_FAILED, LineageRunState.FAILED),
        (LineageEventType.RUN_INTERRUPTED, LineageRunState.INTERRUPTED),
        (LineageEventType.COMPLETION_DENIED, LineageRunState.NEEDS_HUMAN),
        (LineageEventType.PROMOTION_COMPLETED, LineageRunState.PROMOTED),
    ],
)
def test_terminal_states_are_explicit(event_type, expected):
    specs = [_run_started()]
    if event_type == LineageEventType.COMPLETION_DENIED:
        specs.extend(
            (
                (
                    LineageEventType.COMPLETION_ATTEMPTED,
                    {"adapter_kind": "local", "operation": "request_completion"},
                    "completion_1",
                ),
                (event_type, {"status": expected.value}, "completion_1"),
            )
        )
        events = list(_events(*specs))
        attempt = events[-2]
        denial = events[-1]
        reference = {
            "kind": "event",
            "id": attempt.event_id,
            "sha256": attempt.event_sha256,
        }
        values = denial.model_dump(mode="json")
        values["references"] = [reference]
        values["event_sha256"] = canonical_json_sha256(
            {key: value for key, value in values.items() if key != "event_sha256"}
        )
        events[-1] = Event.model_validate(values)
        projection = reduce_events(tuple(events))
    else:
        projection = reduce_events(_events(*specs, (event_type, {"status": expected.value}, None)))
    assert projection.state == expected


def test_digest_failure_has_an_explicit_evidence_invalid_representation():
    events = _events(_run_started())
    damaged = events[0].model_copy(update={"event_sha256": "f" * 64})

    with pytest.raises(ProjectionError) as raised:
        reduce_events((damaged,))

    assert raised.value.state == LineageRunState.EVIDENCE_INVALID
    assert raised.value.as_state().model_dump() == {
        "run_id": "run_1",
        "first_invalid_seq": 1,
        "reason": "event envelope digest does not match",
    }


def test_unknowns_never_invent_causality_or_repository_impact():
    projection = reduce_events(_events(_run_started()))
    assert projection.unknowns == (
        "Timing does not prove causality.",
        "Whole-repository impact is unknown.",
    )
