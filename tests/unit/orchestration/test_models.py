from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_sha256
from graphene.models import TruthKind
from graphene.orchestration.models import (
    MISSION_TRANSITIONS,
    TASK_TRANSITIONS,
    ArtifactContract,
    AttemptResult,
    Gate,
    GateDecision,
    GenericEvidenceLink,
    MissionAuthority,
    MissionEvent,
    MissionEventInput,
    MissionEventType,
    MissionStatus,
    NetworkMode,
    NetworkPolicy,
    Task,
    TaskState,
)
from graphene.orchestration.reducer import TransitionError, transition_mission, transition_task


def _task(**updates) -> Task:
    values = {
        "task_id": "task_1",
        "title": "Task one",
        "contract": "Produce the requested bounded change.",
        "assigned_role": "worker",
        "read_paths": ("app/a.py",),
        "write_paths": ("app/a.py",),
        "allowed_commands": ("edit",),
        "expected_outputs": (
            ArtifactContract(name="patch", kind="patch", paths=("app/a.py",)),
        ),
        "acceptance_checks": ("check",),
        "priority": 1,
        "attempt_limit": 2,
    }
    return Task.model_validate({**values, **updates})


def _event(draft: MissionEventInput) -> MissionEvent:
    values = {
        **draft.model_dump(mode="json"),
        "schema_version": 1,
        "event_id": "mission_event_1",
        "mission_id": "mission_1",
        "seq": 1,
        "server_recorded_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace(
            "+00:00", "Z"
        ),
        "command_id": "mission_command_0001",
        "payload_sha256": canonical_json_sha256(draft.payload),
        "previous_event_sha256": None,
    }
    return MissionEvent.model_validate(
        {**values, "event_sha256": canonical_json_sha256(values)}
    )


def test_models_are_strict_frozen_and_canonical() -> None:
    task = _task()
    with pytest.raises(ValidationError):
        _task(unexpected=True)
    with pytest.raises(ValidationError, match="sorted and unique"):
        _task(read_paths=("app/z.py", "app/a.py"))
    with pytest.raises(ValidationError, match="retry_at"):
        _task(state=TaskState.RETRYING)
    with pytest.raises(ValidationError, match="blocker"):
        _task(state=TaskState.BLOCKED)
    with pytest.raises(ValidationError):
        task.state = TaskState.DONE


def test_event_payload_rejects_private_fields_and_binds_hashes() -> None:
    draft = MissionEventInput(
        event_type=MissionEventType.TASK_READY,
        truth_kind=TruthKind.SERVER_DERIVED,
        authority=MissionAuthority.SCHEDULER,
        payload={"state": "ready", "task_id": "task_1"},
    )
    event = _event(draft)
    assert event.event_sha256 == canonical_json_sha256(
        event.model_dump(mode="json", exclude={"event_sha256"})
    )
    with pytest.raises(ValidationError, match="unsafe"):
        MissionEventInput(
            event_type=MissionEventType.TASK_READY,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=MissionAuthority.SCHEDULER,
            payload={"prompt": "hidden"},
        )
    with pytest.raises(ValidationError, match="digest"):
        MissionEvent.model_validate(
            {**event.model_dump(mode="json"), "payload_sha256": "f" * 64}
        )


@pytest.mark.parametrize(
    "payload",
    (
        {"api_key": "not-even-needed"},
        {"rawPrompt": "hidden"},
        {"label": "Bearer abcdefghijklmnopqrstuvwxyz012345"},
        {"label": "sk-abcdefghijklmnopqrstuvwxyz012345"},
        {"label": "-----BEGIN PRIVATE KEY-----"},
        {"label": "/Users/alex/.ssh/id_rsa"},
    ),
)
def test_event_payload_rejects_normalized_secret_canaries(payload) -> None:
    with pytest.raises(ValidationError, match="unsafe"):
        MissionEventInput(
            event_type=MissionEventType.TASK_READY,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=MissionAuthority.SCHEDULER,
            payload=payload,
        )

    safe = MissionEventInput(
        event_type=MissionEventType.TASK_READY,
        truth_kind=TruthKind.SERVER_DERIVED,
        authority=MissionAuthority.SCHEDULER,
        payload={
            "estimated_tokens": 42,
            "label": "Token estimate unavailable.",
            "sha256": "a" * 64,
        },
    )
    assert safe.payload["estimated_tokens"] == 42


def test_truth_kind_requires_matching_authority() -> None:
    with pytest.raises(ValidationError, match="operator authority"):
        MissionEventInput(
            event_type=MissionEventType.GATE_DECIDED,
            truth_kind=TruthKind.HUMAN_ATTESTED,
            authority=MissionAuthority.SCHEDULER,
            payload={"choice": "approve"},
        )
    with pytest.raises(ValidationError, match="operator authority"):
        MissionEventInput(
            event_type=MissionEventType.GATE_DECIDED,
            truth_kind=TruthKind.HUMAN_ATTESTED,
            authority=MissionAuthority.SIMULATED_FIXTURE,
            payload={"choice": "approve"},
        )
    with pytest.raises(ValidationError, match="planner authority"):
        MissionEventInput(
            event_type=MissionEventType.PLAN_PROPOSED,
            truth_kind=TruthKind.MODEL_PROPOSED,
            authority=MissionAuthority.MISSION_SERVICE,
            payload={"status": "proposed"},
        )


def test_transition_tables_accept_only_declared_pairs() -> None:
    for current in TaskState:
        for target in TaskState:
            if (current, target) in TASK_TRANSITIONS:
                assert transition_task(current, target) == target
            else:
                with pytest.raises(TransitionError):
                    transition_task(current, target)
    for current in MissionStatus:
        for target in MissionStatus:
            if (current, target) in MISSION_TRANSITIONS:
                assert transition_mission(current, target) == target
            else:
                with pytest.raises(TransitionError):
                    transition_mission(current, target)


def test_evidence_links_gate_resolution_and_network_policy_are_exact() -> None:
    result = AttemptResult(
        succeeded=True,
        result_code="passed",
        evidence_link=GenericEvidenceLink(evidence_id="attempt_evidence_1"),
    )
    assert result.evidence_link.kind == "generic_v1"
    with pytest.raises(ValidationError, match="require evidence"):
        AttemptResult(succeeded=True, result_code="passed")
    with pytest.raises(ValidationError, match="sorted unique"):
        Gate(
            gate_id="gate_1",
            mission_id="mission_1",
            reason="Choose one bounded option.",
            allowed_decisions=(
                GateDecision(value="z", consequence="Z"),
                GateDecision(value="a", consequence="A"),
            ),
            truth_kind=TruthKind.SERVER_DERIVED,
        )
    assert NetworkPolicy().mode == NetworkMode.DENY
    with pytest.raises(ValidationError, match="deny"):
        NetworkPolicy(mode=NetworkMode.DENY, allowed_hosts=("example.com",))
