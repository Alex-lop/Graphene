from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_sha256
from graphene.models import TruthKind
from graphene.orchestration.models import (
    EvidenceReference,
    Gate,
    GateDecision,
    ResourceReceipt,
)
from graphene.orchestration.projection import (
    MissionControlSnapshot,
    MissionProjection,
    MissionProjectionError,
    RelationshipView,
    _gate_views,
    apply_delta,
    attempt_evidence,
    decode_cursor,
    diff_snapshots,
    task_detail,
)
from graphene.orchestration.store import SQLiteMissionStore
from scripts.generate_mission_replay import stages

from .test_store import NOW, _command, _complete_ready, _create


def test_snapshots_and_deltas_are_deterministic_exact_and_idempotent():
    values = stages()
    assert values == stages()
    current = values[0]
    for expected in values[1:]:
        delta = diff_snapshots(current, expected)
        rebuilt = apply_delta(current, delta)
        assert rebuilt == expected
        assert apply_delta(rebuilt, delta) == expected
        public = rebuilt.model_dump(mode="json", exclude={"cursor", "snapshot_sha256"})
        assert canonical_json_sha256(public) == rebuilt.snapshot_sha256
        current = rebuilt


def test_cursor_is_bound_to_mission_head_and_rejects_tampering():
    value = stages()[0]
    assert decode_cursor(value.cursor, value.mission.mission_id) == (
        value.head.seq,
        value.head.event_sha256,
    )
    with pytest.raises(MissionProjectionError, match="cursor"):
        decode_cursor(value.cursor, "another_mission")
    with pytest.raises(MissionProjectionError, match="cursor"):
        decode_cursor(value.cursor[:-2] + "xx", value.mission.mission_id)


def test_relationships_are_explicit_typed_and_endpoint_checked():
    value = stages()[-1]
    kinds = {item.kind for item in value.relationships}
    assert {
        "decomposed_into",
        "depends_on",
        "assigned_to",
        "produced",
        "accepted_from",
        "verified_by",
        "inherited",
    } <= kinds
    invalid = RelationshipView(
        relationship_id="depends_on:task:wire_cli:task:missing",
        source="task:wire_cli",
        target="task:missing",
        kind="depends_on",
    )
    with pytest.raises(ValidationError, match="endpoint"):
        MissionControlSnapshot.model_validate(
            {
                **value.model_dump(mode="json"),
                "relationships": [
                    *sorted(
                        [
                            *value.model_dump(mode="json")["relationships"],
                            invalid.model_dump(mode="json"),
                        ],
                        key=lambda item: item["relationship_id"],
                    ),
                ],
            }
        )


def test_task_and_generic_attempt_drilldown_remain_bounded():
    value = stages()[-1]
    detail = task_detail(value, "render_markdown")
    assert any("markdown_retry_fix" in item for item in detail.changed_hunks)
    assert any("markdown_acceptance_passed" in item for item in detail.test_receipts)
    assert any("Raw prompts" in item for item in detail.unknowns)
    evidence = attempt_evidence(value, "attempt_render_markdown_2")
    assert evidence.attempt.evidence.kind == "generic_attempt_v1"
    serialized = evidence.model_dump_json()
    for forbidden in ("stdout", "stderr", "argv", "chain_of_thought"):
        assert forbidden not in serialized


def test_materialized_gate_projects_reason_choices_consequences_and_truth():
    evidence_sha = "a" * 64
    gate = Gate(
        gate_id="gate_privacy",
        mission_id="mission_status_reports",
        task_id="redact_notes",
        reason="Choose whether private notes may be included in the report.",
        evidence=(
            EvidenceReference(
                kind="policy_receipt", id="privacy_policy", sha256=evidence_sha
            ),
        ),
        allowed_decisions=(
            GateDecision(
                value="exclude_private",
                consequence="Private notes stay excluded from all downstream artifacts.",
            ),
            GateDecision(
                value="include_redacted",
                consequence="Only policy-redacted notes may enter the report.",
            ),
        ),
        truth_kind=TruthKind.POLICY_AUTHORITATIVE,
    )
    projected = _gate_views((gate,))[0]
    assert projected.reason == gate.reason
    assert [item.value for item in projected.options] == [
        "exclude_private",
        "include_redacted",
    ]
    assert "Private notes stay excluded" in projected.options[0].consequence
    assert projected.evidence_summary == "1 committed evidence reference supports this decision."
    assert projected.truth_kind == "policy_authoritative"


def test_non_tty_gate_decision_does_not_claim_human_attestation(tmp_path):
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    gate = Gate(
        gate_id="gate-non-tty",
        mission_id="mission-1",
        reason="Choose the bounded fixture behavior.",
        allowed_decisions=(
            GateDecision(value="approve", consequence="Continue within policy."),
            GateDecision(value="reject", consequence="Stop before dispatch."),
        ),
        truth_kind=TruthKind.POLICY_AUTHORITATIVE,
    )
    store.request_gate(
        gate, _command("request-non-tty-gate"), recorded_at=NOW + timedelta(seconds=1)
    )
    store.decide_gate(
        "mission-1",
        gate.gate_id,
        "approve",
        _command("decide-non-tty-gate"),
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=2),
    )

    projected = next(
        item
        for item in MissionProjection(store).snapshot("mission-1").gates
        if item.gate_id == gate.gate_id
    )
    assert projected.truth_kind == "server_derived"
    assert 'bounded operator label "non-tty-api"' in projected.evidence_summary
    assert "server_derived/mission_service" in projected.evidence_summary
    assert "human attestation is not established" in projected.evidence_summary


def test_live_flat_resource_receipt_projects_value_threshold_and_pressure(tmp_path):
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    store.record_resource_summary(
        ResourceReceipt(
            receipt_id="resource-runtime",
            mission_id="mission-1",
            subject="worker-memory",
            source="resource-sentinel",
            platform="linux",
            scope="isolated_process_tree",
            semantics="sampled-current-rss",
            units="bytes",
            observed_from=NOW,
            observed_until=NOW,
            value=200,
            attribution_quality="measured_bound",
            threshold=100,
            action="pause-new-dispatch",
        ),
        _command("resource-projection"),
        recorded_at=NOW,
    )

    resources = MissionProjection(store).snapshot("mission-1").resources
    assert resources.status == "pressure"
    assert resources.metrics[0].category == "measured_runtime"
    assert resources.metrics[0].display_value == (
        "200 bytes / 100 bytes threshold · 100 bytes over"
    )
    assert "recorded action: pause-new-dispatch" in resources.summary


def test_cold_projection_rejects_materialized_state_without_an_event(tmp_path):
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE mission_tasks SET state = 'failed' "
            "WHERE mission_id = 'mission-1' AND task_id = 'work-a'"
        )

    with pytest.raises(MissionProjectionError, match="does not match event replay"):
        MissionProjection(store).snapshot("mission-1")


def test_cancelled_integration_stage_uses_authoritative_task_state(tmp_path):
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    store.refresh_ready(
        "mission-1", _command("ready-assembly"), recorded_at=NOW + timedelta(seconds=2)
    )
    assembly = next(
        task for task in store.ready_tasks("mission-1") if task.task_id == "assemble"
    )
    store.claim_task(
        "mission-1",
        assembly.task_id,
        "worker-assembly",
        _command("claim-assembly"),
        recorded_at=NOW + timedelta(seconds=2),
        ttl_seconds=30,
    )
    projection = MissionProjection(store)
    assert projection.snapshot("mission-1").integration.state == "running"
    store.cancel(
        "mission-1",
        _command("cancel-assembly"),
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=3),
    )

    assert projection.snapshot("mission-1").integration.state == "cancelled"


def test_completed_worker_reuse_and_final_result_decision_project_consistently(tmp_path):
    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    assert _complete_ready(store, "mission-1", at=NOW, round_number=1) == (
        "work-a",
        "work-b",
    )
    assert _complete_ready(
        store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2
    ) == ("assemble",)
    assert _complete_ready(
        store, "mission-1", at=NOW + timedelta(seconds=4), round_number=3
    ) == ("verify",)
    store.enter_awaiting_result(
        "mission-1", _command("await-projection"), recorded_at=NOW + timedelta(seconds=6)
    )

    projection = MissionProjection(store)
    view = projection.snapshot("mission-1")
    assert view.mission.status == "awaiting_result"
    assert all(task.worker_id is task.current_attempt_id is None for task in view.tasks)
    assert view.needs_you is not None
    assert view.needs_you.gate_id.startswith("final_result_")
    assert view.needs_you.truth_kind == "server_derived"
    assert [option.value for option in view.needs_you.options] == [
        "approve_result",
        "reject_result",
    ]
    assert "--candidate-sha" in view.needs_you.options[0].consequence
    assert any(
        relationship.source == f"result:{view.mission.mission_id}"
        and relationship.target == f"gate:{view.needs_you.gate_id}"
        and relationship.kind == "blocked_by"
        for relationship in view.relationships
    )

    candidate = next(
        item for item in store.snapshot("mission-1").publications if item.task_id == "assemble"
    )
    store.approve_final_result(
        "mission-1",
        _command("approve-non-tty-result"),
        expected_candidate_sha256=candidate.sha256,
        operator_label="non-tty-api",
        rationale=None,
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=7),
    )
    approved = projection.snapshot("mission-1")
    assert approved.result.state == "approved"
    assert 'bounded operator label "non-tty-api"' in approved.result.summary
    assert "server_derived/mission_service" in approved.result.summary
    assert "human attestation is not established" in approved.result.summary


def test_replay_captures_parallelism_denial_retry_gate_and_ordered_result():
    values = stages()
    parallel = values[1]
    assert sum(item.state == "running" for item in parallel.tasks) == 2
    assert parallel.resources.status == "pressure"
    assert values[0].needs_you is not None
    assert values[1].needs_you is None
    denial = next(
        item for item in values[2].attempts if item.attempt_id == "attempt_render_markdown_1"
    )
    assert any(item.kind == "command_denial" for item in denial.evidence_refs)
    assert next(item for item in values[3].tasks if item.task_id == "render_markdown").state == "retrying"
    assert len(
        [item for item in values[4].attempts if item.task_id == "render_markdown"]
    ) == 2
    final = values[-1]
    assert final.integration.state == final.verification.state == "done"
    assert final.result.state == "commit_created"
