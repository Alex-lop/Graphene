from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.models import (
    ContextBrief,
    Event,
    EventInput,
    EvidenceReference,
    FileVersion,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    SourceReference,
    TruthKind,
)


def _source() -> SourceReference:
    return SourceReference(kind="lifecycle_request", id="request_1", sha256="a" * 64)


def _draft(**updates) -> EventInput:
    values = {
        "session_id": None,
        "invocation_id": None,
        "model_id": None,
        "tool_call_id": None,
        "repo_id": "graphene-demo",
        "base_sha": "b" * 40,
        "agent_profile_id": "platform-maintainer@1",
        "policy_revision": 1,
        "event_type": LineageEventType.RUN_STARTED,
        "truth_kind": TruthKind.SERVER_DERIVED,
        "authority": LineageAuthority.LIFECYCLE_SERVICE,
        "references": (),
        "source_ref": _source(),
        "payload": {"state": "STARTING"},
    }
    values.update(updates)
    return EventInput(**values)


def _event(draft: EventInput) -> Event:
    timestamp = datetime(2026, 8, 12, tzinfo=timezone.utc)
    values = {
        **draft.model_dump(mode="json"),
        "schema_version": 2,
        "event_id": "evt_1",
        "run_id": "run_1",
        "seq": 1,
        "server_recorded_at": timestamp.isoformat().replace("+00:00", "Z"),
        "idempotency_key": "run_started_key_1",
        "payload_sha256": canonical_json_sha256(draft.payload),
        "previous_event_sha256": None,
    }
    values["event_sha256"] = canonical_json_sha256(values)
    return Event(**values)


def test_v2_event_serializes_null_identity_and_binds_payload_and_chain():
    event = _event(_draft())

    serialized = event.model_dump(mode="json")
    assert {serialized[key] for key in ("session_id", "invocation_id", "model_id", "tool_call_id")} == {None}
    assert event.payload_sha256 == canonical_json_sha256(event.payload)
    assert event.event_sha256 == canonical_json_sha256(
        event.model_dump(mode="json", exclude={"event_sha256"})
    )

    with pytest.raises(ValidationError, match="payload digest"):
        Event.model_validate({**serialized, "payload_sha256": "c" * 64})
    with pytest.raises(ValidationError, match="previous digest"):
        Event.model_validate({**serialized, "previous_event_sha256": "d" * 64})


def test_tool_events_require_wrapper_identity_and_reject_raw_payloads():
    tool_source = SourceReference(kind="tool_receipt", id="receipt_1", sha256="f" * 64)
    with pytest.raises(ValidationError, match="wrapper identity"):
        _draft(
            event_type=LineageEventType.TOOL_STARTED,
            truth_kind=TruthKind.RUNTIME_OBSERVED,
            authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
            source_ref=tool_source,
            payload={"operation": "read_file"},
        )
    with pytest.raises(ValidationError, match="unsafe"):
        _draft(payload={"stdout": "forbidden"})
    with pytest.raises(ValidationError, match="public allowlist"):
        _draft(payload={"state": "STARTING", "innocent_note": "private source"})
    with pytest.raises(ValidationError):
        _draft(unexpected=True)

    draft = _draft(
        session_id="session_1",
        invocation_id="invocation_1",
        model_id="gemini-test",
        tool_call_id="call_1",
        event_type=LineageEventType.TOOL_COMPLETED,
        truth_kind=TruthKind.RUNTIME_OBSERVED,
        authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
        source_ref=tool_source,
        references=(EvidenceReference(kind="file_version", id="version_1", sha256="e" * 64),),
        payload={"operation": "read_file", "path": "app/auth/limiter.py", "byte_count": 10},
    )
    assert draft.payload["operation"] == LineageOperation.READ_FILE.value

    with pytest.raises(ValidationError, match="truth and authority"):
        _draft(authority=LineageAuthority.OPERATOR_REQUEST)


def test_file_version_ids_are_content_bound():
    content_sha = sha256_hex(b"hello\n")
    file_id = sha256_hex(b"graphene-demo\0app/auth/limiter.py")
    version_id = sha256_hex(f"{file_id}\0{content_sha}".encode())
    version = FileVersion(
        schema_version=2,
        file_id=file_id,
        file_version_id=version_id,
        repo_id="graphene-demo",
        path="app/auth/limiter.py",
        content_sha256=content_sha,
        byte_count=6,
        line_count=1,
        artifact_sha256=canonical_json_sha256(
            {"path": "app/auth/limiter.py", "content_sha256": content_sha}
        ),
    )
    assert version.file_version_id == version_id
    with pytest.raises(ValidationError, match="identifiers"):
        FileVersion.model_validate({**version.model_dump(), "file_version_id": "f" * 64})


def test_context_brief_is_included_only_and_hash_bound():
    payload = {
        "schema_version": 2,
        "brief_id": "brief_1",
        "repo_id": "graphene-demo",
        "base_sha": "b" * 40,
        "task_id": "adapted_window_seconds",
        "task_text": "Change the bounded authentication window.",
        "target_profile_id": "auth-maintainer@1",
        "target_profile_revision": 1,
        "policy_revision": 1,
        "approved_memories": (),
        "selected_evidence": (),
        "required_paths": ("app/auth/limiter.py",),
        "read_scope": ("app/auth/limiter.py", "tests/test_security_policy.py"),
        "write_scope": ("app/auth/limiter.py",),
        "tools": ("read_file", "write_file", "run_fixed_test", "request_completion"),
        "fixed_test_profile": "auth-fixture-v1",
        "byte_caps": {"read": 32768, "write": 32768},
        "event_caps": {"run": 256},
        "source_run_id": "run_a",
        "source_session_id": "session_a",
        "source_head": {
            "run_id": "run_a",
            "seq": 2,
            "event_sha256": "c" * 64,
            "event_count": 2,
        },
        "source_graph_sha256": "d" * 64,
        "fresh_session_required": True,
    }
    brief = ContextBrief(**payload, brief_sha256=canonical_json_sha256(payload))
    assert not {"excluded", "exclusion_reasons", "candidate_set_sha256"} & set(
        ContextBrief.model_fields
    )
    invalid = {
        **brief.model_dump(mode="json", exclude={"brief_sha256"}),
        "write_scope": ["docs/security.md"],
    }
    with pytest.raises(ValidationError, match="subset"):
        ContextBrief.model_validate(
            {
                **invalid,
                "brief_sha256": canonical_json_sha256(invalid),
            }
        )
