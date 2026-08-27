from __future__ import annotations

from datetime import timedelta

import pytest

from graphene.hashing import canonical_json_bytes
from graphene.core_models import TruthKind
from graphene.orchestration.mission_models import (
    AuthorizationMode,
    FinalizationMode,
    MissionAuthority,
    MissionEventType,
    MissionStatus,
    PlanPolicyDecisionV1,
    ProjectPolicy,
)
from graphene.orchestration.sqlite_mission_store import (
    MissionConflict,
    SQLiteMissionStore,
)
from graphene.orchestration.validation import evaluate_plan_policy

from .test_store import NOW, _command, _complete_ready, _create, _plan, _policy


def _automatic_policy() -> ProjectPolicy:
    return ProjectPolicy.model_validate(
        {
            **_policy().model_dump(mode="json"),
            "schema_version": 2,
            "authorization_mode": AuthorizationMode.POLICY_PRE_AUTHORIZED,
            "finalization_mode": FinalizationMode.AUTO_FINALIZE_ISOLATED,
        }
    )


def _decision(policy: ProjectPolicy) -> PlanPolicyDecisionV1:
    return evaluate_plan_policy(
        policy,
        _plan(),
        goal_request_id="goal-request-0001",
        requested_mode=AuthorizationMode.POLICY_PRE_AUTHORIZED,
    )


def test_policy_decision_is_recomputed_and_preauthorization_is_atomic(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "policy.sqlite")
    policy = _automatic_policy()
    _create(store, approve=False, policy=policy)
    initial = store.head("mission-1")
    decision = _decision(policy)
    wrong = PlanPolicyDecisionV1.create(
        **{
            **decision.model_dump(mode="json", exclude={"decision_sha256"}),
            "policy_sha256": "f" * 64,
        }
    )

    with pytest.raises(MissionConflict, match="does not match current plan"):
        store.record_plan_policy_decision(
            "mission-1",
            _command("wrong-policy-decision"),
            wrong,
            expected_head=initial,
            recorded_at=NOW,
        )

    head = store.record_plan_policy_decision(
        "mission-1",
        _command("policy-decision"),
        decision,
        expected_head=initial,
        recorded_at=NOW,
    )
    retry = store.record_plan_policy_decision(
        "mission-1",
        _command("policy-decision"),
        decision,
        expected_head=initial,
        recorded_at=NOW + timedelta(minutes=1),
    )

    assert retry == head
    assert head.seq == initial.seq + 2
    events = store.tail("mission-1", initial.seq, 2)
    assert [event.event_type for event in events] == [
        MissionEventType.PLAN_POLICY_DECIDED,
        MissionEventType.PLAN_APPROVED,
    ]
    assert all(event.truth_kind == TruthKind.POLICY_AUTHORITATIVE for event in events)
    assert all(event.authority == MissionAuthority.POLICY_ENGINE for event in events)
    assert events[1].payload["policy_decision_sha256"] == decision.decision_sha256
    snapshot = store.snapshot("mission-1")
    assert snapshot.mission.status == MissionStatus.RUNNING
    assert snapshot.policy.schema_version == 2
    assert snapshot.policy.authorization_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
    assert snapshot.policy.finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED
    assert store.verify("mission-1") == head


def test_review_decision_stays_proposed_and_manual_approval_binds_it(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "review.sqlite")
    policy = _policy()
    _create(store, approve=False, policy=policy)
    initial = store.head("mission-1")
    decision = _decision(policy)

    decided = store.record_plan_policy_decision(
        "mission-1",
        _command("review-decision"),
        decision,
        expected_head=initial,
        recorded_at=NOW,
    )

    assert decided.seq == initial.seq + 1
    assert store.snapshot("mission-1").mission.status == MissionStatus.PROPOSED
    approved = store.approve_plan(
        "mission-1",
        _command("approve-reviewed-plan"),
        expected_revision=1,
        expected_head=decided,
        operator_label="reviewer",
        rationale="Reviewed exact policy-bounded plan.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=1),
    )

    event = store.tail("mission-1", decided.seq, 1)[0]
    assert event.payload["policy_decision_sha256"] == decision.decision_sha256
    assert store.snapshot("mission-1").mission.status == MissionStatus.RUNNING
    assert store.verify("mission-1") == approved


def test_schema_v2_plan_cannot_be_manually_approved_before_policy_decision(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "undecided.sqlite")
    _create(store, approve=False, policy=_automatic_policy())

    with pytest.raises(MissionConflict, match="policy decision is not committed"):
        store.approve_plan(
            "mission-1",
            _command("approve-undecided-plan"),
            expected_revision=1,
            expected_head=store.head("mission-1"),
            operator_label="reviewer",
            rationale="This must not bypass policy evaluation.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )

    assert store.snapshot("mission-1").mission.status == MissionStatus.PROPOSED


def test_policy_final_approval_binds_exact_registered_bundle(tmp_path) -> None:
    from tests.adversarial.test_final_approval_bundle import (
        _complete_trusted_verification,
        _pending_bundle,
    )

    store = SQLiteMissionStore(tmp_path / "automatic-result.sqlite")
    policy = _automatic_policy()
    _create(store, approve=False, policy=policy)
    store.record_plan_policy_decision(
        "mission-1",
        _command("policy-result-decision"),
        _decision(policy),
        expected_head=store.head("mission-1"),
        recorded_at=NOW,
    )
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(
        store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2
    )
    _complete_trusted_verification(store)
    store.enter_awaiting_result(
        "mission-1",
        _command("await-policy-result"),
        recorded_at=NOW + timedelta(seconds=6),
    )
    bundle = _pending_bundle(store)
    artifacts = store.artifact_resolver
    assert artifacts is not None
    reference = artifacts.put(
        "final-result-bundle",
        canonical_json_bytes(bundle.model_dump(mode="json")),
    )
    store.bind_final_bundle_verifier(lambda _raw, _snapshot: True)
    store.register_final_result_bundle(
        "mission-1",
        reference,
        _command("register-policy-bundle"),
        expected_head=store.head("mission-1"),
        recorded_at=NOW + timedelta(seconds=7),
    )
    ready = store.snapshot("mission-1")

    with pytest.raises(MissionConflict, match="requires policy authority"):
        store.approve_final_result(
            "mission-1",
            _command("manual-auto-result"),
            expected_head=ready.head,
            expected_bundle_id=bundle.bundle_id,
            operator_label="reviewer",
            rationale=None,
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW + timedelta(seconds=8),
        )
    head = store.approve_final_result_by_policy(
        "mission-1",
        _command("policy-auto-result"),
        expected_head=ready.head,
        expected_bundle_id=bundle.bundle_id,
        recorded_at=NOW + timedelta(seconds=8),
    )

    event = store.tail("mission-1", ready.head.seq, 1)[0]
    decision = _decision(policy)
    assert event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
    assert event.truth_kind == TruthKind.POLICY_AUTHORITATIVE
    assert event.authority == MissionAuthority.POLICY_ENGINE
    assert event.payload["decision_mode"] == "auto_finalize_isolated"
    assert event.payload["policy_decision_sha256"] == decision.decision_sha256
    assert store.snapshot("mission-1").mission.final_outcome == "approved_pending_commit"
    assert store.verify("mission-1") == head
