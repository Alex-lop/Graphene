from __future__ import annotations

from dataclasses import dataclass

from .models import (
    MISSION_TRANSITIONS,
    TASK_TRANSITIONS,
    Mission,
    MissionEvent,
    MissionEventType,
    MissionStatus,
    Task,
    TaskKind,
    TaskState,
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
) -> ReducedMission:
    """Purely replay committed events against immutable initial contracts."""

    status = mission.status
    states = {task.task_id: task.state for task in tasks}
    kinds = {task.task_id: task.kind for task in tasks}
    attempts = {task.task_id: task.attempt_count for task in tasks}
    previous: str | None = None
    for seq, event in enumerate(events, 1):
        if (
            event.mission_id != mission.mission_id
            or event.seq != seq
            or event.previous_event_sha256 != previous
        ):
            raise TransitionError("mission event stream is not contiguous")
        previous = event.event_sha256

        if event.event_type == MissionEventType.PLAN_APPROVED:
            status = transition_mission(status, MissionStatus.RUNNING)
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
        elif event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED:
            status = transition_mission(status, MissionStatus.COMPLETED)
        elif event.event_type == MissionEventType.FINAL_CANDIDATE_REJECTED:
            status = transition_mission(status, MissionStatus.REJECTED)
        elif event.event_type in {
            MissionEventType.ASSEMBLY_FAILED,
            MissionEventType.VERIFICATION_FAILED,
        }:
            if status not in {MissionStatus.FAILED, MissionStatus.CANCELLED}:
                status = transition_mission(status, MissionStatus.FAILED)

        task_id = event.payload.get("task_id")
        if not isinstance(task_id, str):
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
                raise TransitionError("gate decision has an invalid task state") from error
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

    return ReducedMission(status=status, task_states=states, attempt_counts=attempts)
