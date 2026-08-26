from __future__ import annotations

import json

from graphene.cli.render import render_evidence_invalid, render_human, render_ndjson
from graphene.hashing import canonical_json_bytes, canonical_json_sha256
from graphene.lineage.lineage_reducer import reduce_events
from graphene.core_models import (
    Event,
    EventInput,
    EvidenceInvalidState,
    LineageAuthority,
    LineageEventType,
    SourceKind,
    SourceReference,
    TruthKind,
)


def _events() -> tuple[Event, ...]:
    specs = (
        (
            LineageEventType.RUN_STARTED,
            TruthKind.SERVER_DERIVED,
            LineageAuthority.LIFECYCLE_SERVICE,
            None,
            {"state": "STARTING"},
        ),
        (
            LineageEventType.TOOL_STARTED,
            TruthKind.RUNTIME_OBSERVED,
            LineageAuthority.SCOPED_TOOL_WRAPPER,
            "call_write",
            {"operation": "write_file"},
        ),
        (
            LineageEventType.TOOL_COMPLETED,
            TruthKind.RUNTIME_OBSERVED,
            LineageAuthority.SCOPED_TOOL_WRAPPER,
            "call_write",
            {
                "operation": "write_file",
                "path": "app/auth/a_very_long_authentication_limiter_name.py",
                "before_file_version_id": "1" * 64,
                "after_file_version_id": "2" * 64,
                "baseline_bytes": 1_700,
                "baseline_lines": 58,
                "added_lines": 7,
                "deleted_lines": 3,
                "state": "EDITED",
            },
        ),
        (
            LineageEventType.TOOL_STARTED,
            TruthKind.RUNTIME_OBSERVED,
            LineageAuthority.SCOPED_TOOL_WRAPPER,
            "call_test",
            {"operation": "run_fixed_test"},
        ),
        (
            LineageEventType.TOOL_COMPLETED,
            TruthKind.RUNTIME_OBSERVED,
            LineageAuthority.SCOPED_TOOL_WRAPPER,
            "call_test",
            {
                "operation": "run_fixed_test",
                "passed": True,
                "bound_paths": ["app/auth/a_very_long_authentication_limiter_name.py"],
            },
        ),
        (
            LineageEventType.COMPLETION_ATTEMPTED,
            TruthKind.MODEL_PROPOSED,
            LineageAuthority.LOCAL_ADAPTER,
            "call_completion",
            {
                "adapter_kind": "local",
                "operation": "request_completion",
                "status": "attempted",
            },
        ),
        (
            LineageEventType.COMPLETION_DENIED,
            TruthKind.POLICY_AUTHORITATIVE,
            LineageAuthority.POLICY_ENGINE,
            "call_completion",
            {"operation": "request_completion", "status": "denied"},
        ),
    )
    events: list[Event] = []
    previous = None
    for seq, (event_type, truth, authority, call_id, payload) in enumerate(specs, 1):
        tool = call_id is not None
        completion_attempt = event_type == LineageEventType.COMPLETION_ATTEMPTED
        references = (
            (
                {
                    "kind": "event",
                    "id": events[-1].event_id,
                    "sha256": events[-1].event_sha256,
                },
            )
            if event_type == LineageEventType.COMPLETION_DENIED
            else ()
        )
        draft = EventInput(
            session_id="session_1" if tool else None,
            invocation_id="invocation_1" if tool else None,
            model_id="model-test" if tool else None,
            tool_call_id=call_id,
            repo_id="graphene-demo",
            base_sha="a" * 40,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=event_type,
            truth_kind=truth,
            authority=authority,
            references=references,
            source_ref=SourceReference(
                kind=(
                    SourceKind.LOCAL_ADAPTER_RECEIPT
                    if completion_attempt
                    else SourceKind.POLICY_EVALUATION
                    if event_type == LineageEventType.COMPLETION_DENIED
                    else SourceKind.TOOL_RECEIPT
                    if tool
                    else SourceKind.POLICY_EVALUATION
                    if event_type == LineageEventType.SCOPE_DENIED
                    else SourceKind.LIFECYCLE_REQUEST
                ),
                id=f"source_{seq}",
                sha256=f"{seq}" * 64,
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
            "idempotency_key": f"render_event_{seq:06d}",
            "payload_sha256": canonical_json_sha256(payload),
            "previous_event_sha256": previous,
        }
        values["event_sha256"] = canonical_json_sha256(values)
        event = Event.model_validate(values)
        events.append(event)
        previous = event.event_sha256
    return tuple(events)


def test_ndjson_is_canonical_parseable_and_contains_no_terminal_decorations():
    events = _events()
    rendered = render_ndjson(events)
    lines = rendered.splitlines()

    assert rendered.endswith("\n")
    assert len(lines) == len(events)
    assert [json.loads(line)["seq"] for line in lines] == list(range(1, len(events) + 1))
    assert lines == [
        canonical_json_bytes(event.model_dump(mode="json")).decode() for event in events
    ]
    assert "\x1b[" not in rendered
    assert not rendered.startswith(("EVENT", "Graphene", "RUN "))


def test_human_output_is_explicit_readable_at_80_columns_and_has_no_ansi():
    projection = reduce_events(_events())

    rendered = render_human(projection, no_color=True, width=80)

    assert max(map(len, rendered.splitlines())) <= 80
    assert "NEEDS HUMAN" in rendered
    assert "+7/-3" in rendered
    assert "T*" in rendered
    assert "BOUND TEST PASS" in rendered
    assert "Timing does not prove causality" in rendered
    assert "Whole-repository impact is unknown" in rendered
    assert "\x1b[" not in rendered
    assert render_human(projection, no_color=False, width=80) == rendered


def test_evidence_invalid_human_row_is_explicit_and_bounded():
    invalid = EvidenceInvalidState(
        run_id="run_1",
        first_invalid_seq=3,
        reason="event previous digest does not match the verified head",
    )

    rendered = render_evidence_invalid(invalid, no_color=True, width=48)

    assert "EVIDENCE INVALID" in rendered
    assert "seq=3" in rendered
    assert max(map(len, rendered.splitlines())) <= 48
    assert "\x1b[" not in rendered
