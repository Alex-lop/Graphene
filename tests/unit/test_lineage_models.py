import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.models import (
    ContextBrief,
    Event,
    EventInput,
    EvidenceKind,
    EvidenceReference,
    FileVersion,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    LineageRunState,
    SourceReference,
    SourceKind,
    TruthKind,
)


def test_v2_contract_tracks_runtime_public_enums_and_demo_command():
    contract = json.loads(Path("contracts/lineage_v2.json").read_text())
    assert contract["run_states"] == [item.value for item in LineageRunState]
    assert contract["event_types"] == [item.value for item in LineageEventType]
    assert contract["truth_kinds"] == [item.value for item in TruthKind]
    assert contract["evidence_kinds"] == [item.value for item in EvidenceKind]
    assert contract["source_kinds"] == [item.value for item in SourceKind]
    assert "demo" in contract["cli"]


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


def test_simulated_fixture_provenance_is_limited_to_gate_events():
    simulated_source = SourceReference(
        kind="simulated_fixture", id="fixture_1", sha256="f" * 64
    )
    answer = _draft(
        event_type=LineageEventType.CLARIFICATION_ANSWERED,
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        authority=LineageAuthority.SIMULATED_FIXTURE,
        source_ref=simulated_source,
        payload={
            "answer_id": "answer_1",
            "answer_sha256": "a" * 64,
            "choice": "all_auth",
            "question_id": "question_1",
            "status": "answered",
        },
    )
    assert answer.truth_kind == TruthKind.SIMULATED_FIXTURE

    with pytest.raises(ValidationError, match="truth and authority"):
        _draft(
            truth_kind=TruthKind.SIMULATED_FIXTURE,
            authority=LineageAuthority.SIMULATED_FIXTURE,
            source_ref=simulated_source,
        )
    with pytest.raises(ValidationError, match="source reference"):
        _draft(
            event_type=LineageEventType.CLARIFICATION_ANSWERED,
            truth_kind=TruthKind.SIMULATED_FIXTURE,
            authority=LineageAuthority.SIMULATED_FIXTURE,
            source_ref=SourceReference(
                kind="operator_request", id="fixture_1", sha256="f" * 64
            ),
            payload=answer.payload,
        )


def test_local_commit_result_binds_runtime_receipt_and_supporting_evidence():
    approval = EvidenceReference(kind="event", id="approval_1", sha256="1" * 64)
    promotion = EvidenceReference(
        kind="promotion_receipt", id="promotion_1", sha256="2" * 64
    )
    test = EvidenceReference(kind="test_receipt", id="test_1", sha256="3" * 64)
    receipt = EvidenceReference(
        kind="local_commit_receipt", id="local_commit_1", sha256="4" * 64
    )
    payload = {
        "local_commit_sha": "c" * 40,
        "parent_sha": "b" * 40,
        "tree_sha": "d" * 40,
        "candidate_patch_sha256": "5" * 64,
        "candidate_tree_sha256": "6" * 64,
        "changed_paths": ["app/auth/limiter.py"],
        "test_receipt_id": test.id,
        "test_receipt_sha256": test.sha256,
        "approval_event_id": approval.id,
        "approval_event_sha256": approval.sha256,
        "local_commit_receipt_id": receipt.id,
        "local_commit_receipt_sha256": receipt.sha256,
        "outcome": "local_isolated_commit",
        "pushed": False,
        "pull_request_created": False,
        "deployed": False,
        "status": "recorded",
    }
    result = _draft(
        event_type=LineageEventType.LOCAL_RESULT_RECORDED,
        truth_kind=TruthKind.RUNTIME_OBSERVED,
        authority=LineageAuthority.LOCAL_COMMIT_SERVICE,
        source_ref=SourceReference(
            kind="local_commit_receipt", id=receipt.id, sha256=receipt.sha256
        ),
        references=(approval, promotion, test, receipt),
        payload=payload,
    )
    assert result.payload["local_commit_sha"] == "c" * 40

    with pytest.raises(ValidationError, match="local commit result bindings"):
        _draft(
            event_type=LineageEventType.LOCAL_RESULT_RECORDED,
            truth_kind=TruthKind.RUNTIME_OBSERVED,
            authority=LineageAuthority.LOCAL_COMMIT_SERVICE,
            source_ref=SourceReference(
                kind="local_commit_receipt", id="other", sha256=receipt.sha256
            ),
            references=(approval, promotion, test, receipt),
            payload=payload,
        )


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
