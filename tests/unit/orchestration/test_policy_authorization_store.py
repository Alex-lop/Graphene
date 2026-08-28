from __future__ import annotations

from datetime import timedelta

import pytest

from graphene.hashing import canonical_json_bytes, canonical_json_sha256
from graphene.core_models import TruthKind
from graphene.orchestration.causal_query import why
from graphene.orchestration.mission_models import (
    AuthorizationMode,
    FinalizationMode,
    Mission,
    MissionAuthority,
    MissionEventInput,
    MissionEventType,
    MissionStatus,
    PlanPolicyDecisionV1,
    ProjectPolicy,
)
from graphene.orchestration.mission_projection import project_snapshot
from graphene.orchestration.mission_reducer import TransitionError, reduce_events
from graphene.orchestration.sqlite_mission_store import (
    MissionConflict,
    SQLiteMissionStore,
)
from graphene.orchestration.validation import evaluate_plan_policy

from .test_store import (
    NOW,
    _command,
    _complete_ready,
    _create,
    _mission,
    _plan,
    _policy,
)


def _automatic_policy() -> ProjectPolicy:
    return ProjectPolicy.model_validate(
        {
            **_policy().model_dump(mode="json"),
            "schema_version": 2,
            "authorization_mode": AuthorizationMode.POLICY_PRE_AUTHORIZED,
            "finalization_mode": FinalizationMode.AUTO_FINALIZE_ISOLATED,
        }
    )


def _decision(
    policy: ProjectPolicy,
    *,
    requested_mode: AuthorizationMode = AuthorizationMode.POLICY_PRE_AUTHORIZED,
) -> PlanPolicyDecisionV1:
    return evaluate_plan_policy(
        policy,
        _plan(),
        goal_request_id="goal-request-0001",
        requested_mode=requested_mode,
    )


def test_policy_decision_is_recomputed_and_preauthorization_is_atomic(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "policy.sqlite")
    policy = _automatic_policy()
    _create(
        store,
        approve=False,
        policy=policy,
        mission_schema_version=2,
        requested_authorization_mode=AuthorizationMode.POLICY_PRE_AUTHORIZED,
        requested_finalization_mode=FinalizationMode.AUTO_FINALIZE_ISOLATED,
    )
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


def test_schema_v2_requested_modes_survive_creation_before_policy_decision(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "policy-crash-window.sqlite")
    policy = _automatic_policy()
    plan = _plan()
    mission = Mission.model_validate(
        {
            **_mission().model_dump(mode="json"),
            "schema_version": 2,
            "requested_authorization_mode": AuthorizationMode.POLICY_PRE_AUTHORIZED,
            "requested_finalization_mode": FinalizationMode.AUTO_FINALIZE_ISOLATED,
        }
    )
    initial = store.create_mission(
        policy,
        mission,
        plan,
        _command("create-policy-crash-window"),
        recorded_at=NOW,
    )
    snapshot = store.snapshot("mission-1")
    events = store.tail("mission-1", 0, initial.seq)
    reduced = reduce_events(mission, plan.tasks, events)
    projected = project_snapshot(snapshot, events).mission

    assert reduced.requested_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
    assert reduced.effective_mode is None
    assert reduced.finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED
    assert (
        projected.requested_authorization_mode
        == AuthorizationMode.POLICY_PRE_AUTHORIZED
    )
    assert projected.effective_authorization_mode is None
    assert projected.finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED

    forged = SQLiteMissionStore._event(
        "mission-1",
        initial,
        _command("forged-auto-finalization"),
        MissionEventInput(
            event_type=MissionEventType.PLAN_POLICY_DECIDED,
            truth_kind=TruthKind.POLICY_AUTHORITATIVE,
            authority=MissionAuthority.POLICY_ENGINE,
            payload={"policy_decision": _decision(policy).model_dump(mode="json")},
        ),
        NOW,
    )
    with pytest.raises(TransitionError, match="bindings are invalid"):
        reduce_events(
            mission.model_copy(
                update={"requested_finalization_mode": FinalizationMode.REVIEW_REQUIRED}
            ),
            plan.tasks,
            (*events, forged),
        )

    for label, requested_mode in (
        ("authorization", AuthorizationMode.REVIEW_REQUIRED),
        ("finalization", AuthorizationMode.POLICY_PRE_AUTHORIZED),
    ):
        mismatched = evaluate_plan_policy(
            policy,
            plan,
            goal_request_id="goal-request-0001",
            requested_mode=requested_mode,
            requested_finalization_mode=FinalizationMode.REVIEW_REQUIRED,
        )
        with pytest.raises(MissionConflict, match="does not match current plan"):
            store.record_plan_policy_decision(
                "mission-1",
                _command(f"mismatched-requested-{label}"),
                mismatched,
                expected_head=initial,
                recorded_at=NOW,
            )

    decided = store.record_plan_policy_decision(
        "mission-1",
        _command("persisted-requested-mode"),
        _decision(policy),
        expected_head=initial,
        recorded_at=NOW,
    )
    snapshot = store.snapshot("mission-1")
    projected = project_snapshot(
        snapshot, store.tail("mission-1", 0, decided.seq)
    ).mission
    assert projected.effective_authorization_mode == (
        AuthorizationMode.POLICY_PRE_AUTHORIZED
    )
    assert projected.finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED
    assert store.verify("mission-1") == decided


def test_review_decision_stays_proposed_and_manual_approval_binds_it(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "review.sqlite")
    policy = _policy()
    _create(store, approve=False, policy=policy)
    initial = store.head("mission-1")
    decision = _decision(policy, requested_mode=AuthorizationMode.REVIEW_REQUIRED)

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
    policy = _automatic_policy()
    _create(store, approve=False, policy=policy)
    snapshot = store.snapshot("mission-1")
    events = store.tail("mission-1", 0, snapshot.head.event_count)
    reduced = reduce_events(
        snapshot.mission,
        snapshot.plan.tasks,
        events,
        policy_schema_version=snapshot.policy.schema_version,
    )
    projected = project_snapshot(snapshot, events)
    causal = why(
        snapshot,
        events,
        "missing-publication",
        reference_exists=lambda _reference: None,
    )

    assert snapshot.mission.schema_version == 1
    assert snapshot.policy.schema_version == 2
    assert reduced.requested_mode == AuthorizationMode.REVIEW_REQUIRED
    assert reduced.effective_mode is None
    assert reduced.finalization_mode == FinalizationMode.REVIEW_REQUIRED
    assert (
        projected.mission.requested_authorization_mode
        == AuthorizationMode.REVIEW_REQUIRED
    )
    assert projected.mission.effective_authorization_mode is None
    assert projected.mission.finalization_mode == FinalizationMode.REVIEW_REQUIRED
    assert (
        projected.model_dump(mode="json")["mission"]["effective_authorization_mode"]
        is None
    )
    assert causal.requested_authorization_mode == AuthorizationMode.REVIEW_REQUIRED
    assert causal.effective_authorization_mode is None
    assert causal.finalization_mode == FinalizationMode.REVIEW_REQUIRED

    forged_decision = _decision(policy)
    with pytest.raises(MissionConflict, match="does not match current plan"):
        store.record_plan_policy_decision(
            "mission-1",
            _command("forged-legacy-preauthorization"),
            forged_decision,
            expected_head=snapshot.head,
            recorded_at=NOW,
        )
    forged_event = SQLiteMissionStore._event(
        "mission-1",
        snapshot.head,
        _command("replay-forged-legacy-preauthorization"),
        MissionEventInput(
            event_type=MissionEventType.PLAN_POLICY_DECIDED,
            truth_kind=TruthKind.POLICY_AUTHORITATIVE,
            authority=MissionAuthority.POLICY_ENGINE,
            payload={"policy_decision": forged_decision.model_dump(mode="json")},
        ),
        NOW,
    )
    with pytest.raises(TransitionError, match="bindings are invalid"):
        reduce_events(
            snapshot.mission,
            snapshot.plan.tasks,
            (*events, forged_event),
            policy_schema_version=snapshot.policy.schema_version,
        )

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


def test_schema_v2_mission_requires_policy_decision_with_legacy_policy(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "v2-mission-v1-policy.sqlite")
    policy = _policy()
    plan = _plan()
    mission = Mission.model_validate(
        {
            **_mission().model_dump(mode="json"),
            "schema_version": 2,
            "requested_authorization_mode": AuthorizationMode.REVIEW_REQUIRED,
            "requested_finalization_mode": FinalizationMode.REVIEW_REQUIRED,
        }
    )
    initial = store.create_mission(
        policy,
        mission,
        plan,
        _command("create-v2-mission-v1-policy"),
        recorded_at=NOW,
    )

    with pytest.raises(MissionConflict, match="policy decision is not committed"):
        store.approve_plan(
            "mission-1",
            _command("approve-v2-mission-without-decision"),
            expected_revision=1,
            expected_head=initial,
            operator_label="reviewer",
            rationale="This must not bypass the mission's policy decision.",
            truth_kind=TruthKind.SERVER_DERIVED,
            recorded_at=NOW,
        )

    events = store.tail("mission-1", 0, initial.seq)
    forged = SQLiteMissionStore._event(
        "mission-1",
        initial,
        _command("forged-approval-without-decision"),
        MissionEventInput(
            event_type=MissionEventType.PLAN_APPROVED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=MissionAuthority.MISSION_SERVICE,
            payload={
                "base_sha": mission.base_sha,
                "operator_label": "reviewer",
                "operator_rationale": "Forged replay must fail closed.",
                "plan_revision": 1,
                "plan_sha256": canonical_json_sha256(plan.model_dump(mode="json")),
                "status": "approved",
            },
        ),
        NOW,
    )
    with pytest.raises(TransitionError, match="lacks its policy decision"):
        reduce_events(mission, plan.tasks, (*events, forged))

    with pytest.raises(TransitionError, match="lacks its policy decision"):
        reduce_events(
            _mission(),
            plan.tasks,
            (*events, forged),
            policy_schema_version=2,
        )


def test_schema_v2_replay_cannot_approve_without_policy_decision(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "v2-replay.sqlite")
    policy = _automatic_policy()
    mission = Mission.model_validate(
        {
            **_mission(creation_source="replay").model_dump(mode="json"),
            "schema_version": 2,
            "requested_authorization_mode": AuthorizationMode.POLICY_PRE_AUTHORIZED,
            "requested_finalization_mode": FinalizationMode.AUTO_FINALIZE_ISOLATED,
        }
    )

    with pytest.raises(MissionConflict, match="persisted policy decision"):
        store.create_mission(
            policy,
            mission,
            _plan(),
            _command("create-v2-replay"),
            recorded_at=NOW,
        )

    with pytest.raises(MissionConflict, match="persisted policy decision"):
        store.create_mission(
            policy,
            _mission(creation_source="replay"),
            _plan(),
            _command("create-v1-replay-v2-policy"),
            recorded_at=NOW,
        )

    legacy = store.create_mission(
        _policy(),
        _mission(creation_source="replay"),
        _plan(),
        _command("create-v1-replay"),
        recorded_at=NOW,
    )
    assert store.tail("mission-1", legacy.seq - 1, 1)[0].event_type == (
        MissionEventType.PLAN_APPROVED
    )


def test_policy_final_approval_binds_exact_registered_bundle(tmp_path) -> None:
    from tests.adversarial.test_final_approval_bundle import (
        _complete_trusted_verification,
        _pending_bundle,
    )

    store = SQLiteMissionStore(tmp_path / "automatic-result.sqlite")
    policy = _automatic_policy()
    _create(
        store,
        approve=False,
        policy=policy,
        mission_schema_version=2,
        requested_authorization_mode=AuthorizationMode.POLICY_PRE_AUTHORIZED,
        requested_finalization_mode=FinalizationMode.AUTO_FINALIZE_ISOLATED,
    )
    store.record_plan_policy_decision(
        "mission-1",
        _command("policy-result-decision"),
        _decision(policy),
        expected_head=store.head("mission-1"),
        recorded_at=NOW,
    )
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2)
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
    assert (
        store.snapshot("mission-1").mission.final_outcome == "approved_pending_commit"
    )
    assert store.verify("mission-1") == head
