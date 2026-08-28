from __future__ import annotations

from dataclasses import dataclass

from .mission_models import (
    AuthorizationMode,
    FinalizationMode,
    MISSION_TRANSITIONS,
    TASK_TRANSITIONS,
    Mission,
    MissionAuthority,
    MissionEvent,
    MissionEventType,
    MissionStatus,
    PlanPolicyDecisionV1,
    Task,
    TaskKind,
    TaskState,
    TruthKind,
)


class TransitionError(ValueError):
    pass


def transition_task(current: TaskState, target: TaskState) -> TaskState:
    if (current, target) not in TASK_TRANSITIONS:
        raise TransitionError(f"illegal task transition: {current} -> {target}")
    return target


def transition_mission(current: MissionStatus, target: MissionStatus) -> MissionStatus:
    if (current, target) not in MISSION_TRANSITIONS:
        raise TransitionError(f"illegal mission transition: {current} -> {target}")
    return target


@dataclass(frozen=True, slots=True)
class ReducedMission:
    status: MissionStatus
    task_states: dict[str, TaskState]
    attempt_counts: dict[str, int]
    requested_mode: AuthorizationMode = AuthorizationMode.REVIEW_REQUIRED
    effective_mode: AuthorizationMode | None = None
    finalization_mode: FinalizationMode = FinalizationMode.REVIEW_REQUIRED
    policy_decision_sha256: str | None = None


_TASK_TARGETS = {
    MissionEventType.TASK_READY: TaskState.READY,
    MissionEventType.TASK_BLOCKED: TaskState.BLOCKED,
    MissionEventType.TASK_RETRIED: TaskState.RETRYING,
    MissionEventType.TASK_COMPLETED: TaskState.DONE,
    MissionEventType.TASK_FAILED: TaskState.FAILED,
    MissionEventType.TASK_CANCELLED: TaskState.CANCELLED,
}


def reduce_events(
    mission: Mission,
    tasks: tuple[Task, ...],
    events: tuple[MissionEvent, ...],
    *,
    plan_revision: int | None = None,
    policy_schema_version: int = 1,
) -> ReducedMission:
    """Purely replay committed events against immutable initial contracts."""

    target_revision = mission.plan_revision if plan_revision is None else plan_revision
    active_revision = 1
    status = mission.status
    states = {task.task_id: task.state for task in tasks}
    kinds = {task.task_id: task.kind for task in tasks}
    attempts = {task.task_id: task.attempt_count for task in tasks}
    policy_decisions: dict[int, PlanPolicyDecisionV1] = {}
    plan_digests: dict[int, str] = {}
    previous: str | None = None
    for seq, event in enumerate(events, 1):
        if (
            event.mission_id != mission.mission_id
            or event.seq != seq
            or event.previous_event_sha256 != previous
        ):
            raise TransitionError("mission event stream is not contiguous")
        previous = event.event_sha256

        if event.event_type == MissionEventType.PLAN_PROPOSED:
            revision = event.payload.get("plan_revision")
            digest = event.payload.get("plan_sha256")
            if revision != active_revision or not isinstance(digest, str):
                raise TransitionError("plan proposal payload is invalid")
            if revision in plan_digests:
                raise TransitionError("plan proposal is ambiguous")
            plan_digests[revision] = digest
        elif event.event_type == MissionEventType.PLAN_REVISED:
            previous_revision = event.payload.get("previous_plan_revision")
            revision = event.payload.get("plan_revision")
            if (
                not isinstance(previous_revision, int)
                or not isinstance(revision, int)
                or previous_revision != active_revision
                or revision != active_revision + 1
            ):
                raise TransitionError("plan revision sequence is not contiguous")
            active_revision = revision
            digest = event.payload.get("plan_sha256")
            if not isinstance(digest, str):
                raise TransitionError("plan revision digest is missing")
            if revision in plan_digests:
                raise TransitionError("plan revision is ambiguous")
            plan_digests[revision] = digest
        elif event.event_type == MissionEventType.PLAN_POLICY_DECIDED:
            if (
                event.truth_kind != TruthKind.POLICY_AUTHORITATIVE
                or event.authority != MissionAuthority.POLICY_ENGINE
                or set(event.payload) != {"policy_decision"}
            ):
                raise TransitionError("plan policy decision authority is invalid")
            try:
                decision = PlanPolicyDecisionV1.model_validate(
                    event.payload["policy_decision"]
                )
            except ValueError as error:
                raise TransitionError("plan policy decision is invalid") from error
            if (
                decision.plan_revision != active_revision
                or decision.policy_id != mission.policy_id
                or decision.policy_revision != mission.policy_revision
                or decision.base_sha != mission.base_sha
                or decision.plan_sha256 != plan_digests.get(active_revision)
                or (
                    mission.schema_version == 1
                    and (
                        decision.requested_mode != AuthorizationMode.REVIEW_REQUIRED
                        or decision.effective_mode != AuthorizationMode.REVIEW_REQUIRED
                        or decision.finalization_mode
                        != FinalizationMode.REVIEW_REQUIRED
                    )
                )
                or (
                    mission.schema_version == 2
                    and (
                        decision.requested_mode != mission.requested_authorization_mode
                        or (
                            decision.finalization_mode
                            == FinalizationMode.AUTO_FINALIZE_ISOLATED
                            and mission.requested_finalization_mode
                            != FinalizationMode.AUTO_FINALIZE_ISOLATED
                        )
                    )
                )
            ):
                raise TransitionError("plan policy decision bindings are invalid")
            if decision.plan_revision in policy_decisions:
                raise TransitionError("plan policy decision is ambiguous")
            policy_decisions[decision.plan_revision] = decision
        elif event.event_type == MissionEventType.PLAN_APPROVED:
            decision = policy_decisions.get(active_revision)
            if (
                mission.schema_version == 2 or policy_schema_version >= 2
            ) and decision is None:
                raise TransitionError("plan approval lacks its policy decision")
            if decision is not None:
                if (
                    event.payload.get("plan_revision") != decision.plan_revision
                    or event.payload.get("plan_sha256") != decision.plan_sha256
                    or event.payload.get("base_sha") != decision.base_sha
                    or event.payload.get("policy_decision_sha256")
                    != decision.decision_sha256
                ):
                    raise TransitionError(
                        "plan approval does not bind its policy decision"
                    )
                policy_grant = (
                    event.truth_kind == TruthKind.POLICY_AUTHORITATIVE
                    and event.authority == MissionAuthority.POLICY_ENGINE
                )
                if policy_grant != (
                    decision.effective_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
                ):
                    raise TransitionError(
                        "plan approval authority disagrees with policy"
                    )
            status = transition_mission(status, MissionStatus.RUNNING)
        elif event.event_type == MissionEventType.PLAN_REJECTED:
            status = transition_mission(status, MissionStatus.REJECTED)
        elif event.event_type == MissionEventType.OPERATOR_PAUSED:
            status = transition_mission(status, MissionStatus.PAUSED)
        elif event.event_type == MissionEventType.OPERATOR_RESUMED:
            status = transition_mission(status, MissionStatus.RUNNING)
        elif event.event_type == MissionEventType.OPERATOR_REPLAN_REQUESTED:
            if status == MissionStatus.RUNNING:
                status = transition_mission(status, MissionStatus.PAUSED)
        elif event.event_type == MissionEventType.OPERATOR_CANCELLED:
            status = transition_mission(status, MissionStatus.CANCELLED)
        elif event.event_type == MissionEventType.FINAL_CANDIDATE_READY:
            status = transition_mission(status, MissionStatus.AWAITING_RESULT)
        elif event.event_type == MissionEventType.FINAL_CANDIDATE_REJECTED:
            status = transition_mission(status, MissionStatus.REJECTED)
        elif event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED:
            decision = policy_decisions.get(active_revision)
            claims_automatic = (
                event.payload.get("decision_mode")
                == FinalizationMode.AUTO_FINALIZE_ISOLATED
                or event.truth_kind == TruthKind.POLICY_AUTHORITATIVE
            )
            if claims_automatic and (
                decision is None
                or decision.finalization_mode != FinalizationMode.AUTO_FINALIZE_ISOLATED
                or event.payload.get("policy_decision_sha256")
                != decision.decision_sha256
                or event.truth_kind != TruthKind.POLICY_AUTHORITATIVE
                or event.authority != MissionAuthority.POLICY_ENGINE
            ):
                raise TransitionError("automatic final approval authority is invalid")
        elif event.event_type == MissionEventType.ISOLATED_COMMIT_CREATED:
            status = transition_mission(status, MissionStatus.COMPLETED)
        elif event.event_type in {
            MissionEventType.ASSEMBLY_FAILED,
            MissionEventType.VERIFICATION_FAILED,
        }:
            if status not in {MissionStatus.FAILED, MissionStatus.CANCELLED}:
                status = transition_mission(status, MissionStatus.FAILED)

        task_id = event.payload.get("task_id")
        if not isinstance(task_id, str):
            continue
        if active_revision != target_revision:
            continue
        if task_id not in states:
            raise TransitionError("event references an unknown task")
        target = _TASK_TARGETS.get(event.event_type)
        if event.event_type == MissionEventType.GATE_DECIDED and isinstance(
            event.payload.get("task_state"), str
        ):
            try:
                target = TaskState(event.payload["task_state"])
            except ValueError as error:
                raise TransitionError(
                    "gate decision has an invalid task state"
                ) from error
        if event.event_type == MissionEventType.TASK_STARTED:
            target = (
                TaskState.VERIFYING
                if kinds[task_id] == TaskKind.VERIFICATION
                else TaskState.RUNNING
            )
        if target is not None:
            states[task_id] = transition_task(states[task_id], target)
            if target == TaskState.FAILED and status not in {
                MissionStatus.FAILED,
                MissionStatus.CANCELLED,
            }:
                status = transition_mission(status, MissionStatus.FAILED)
        if event.event_type == MissionEventType.TASK_LEASED:
            number = event.payload.get("attempt_number")
            if not isinstance(number, int) or number != attempts[task_id] + 1:
                raise TransitionError("task attempt sequence is not contiguous")
            attempts[task_id] = number

    decision = policy_decisions.get(target_revision)
    return ReducedMission(
        status=status,
        task_states=states,
        attempt_counts=attempts,
        requested_mode=(
            mission.requested_authorization_mode
            if decision is None
            else decision.requested_mode
        ),
        effective_mode=(
            AuthorizationMode.REVIEW_REQUIRED
            if decision is None and mission.schema_version == policy_schema_version == 1
            else None
            if decision is None
            else decision.effective_mode
        ),
        finalization_mode=(
            mission.requested_finalization_mode
            if decision is None
            else decision.finalization_mode
        ),
        policy_decision_sha256=(None if decision is None else decision.decision_sha256),
    )
