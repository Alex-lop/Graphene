from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_sha256
from graphene.models import TruthKind
from graphene.orchestration.models import (
    AttemptState,
    MissionEventType,
    MissionStatus,
    Plan,
    PublicationState,
    Task,
    TaskKind,
    TaskState,
)
from graphene.orchestration.projection import MissionProjection
from graphene.orchestration.store import (
    MissionConflict,
    SQLiteMissionStore,
    StaleWorker,
)
from graphene.orchestration.validation import PlanValidationError
from tests.unit.orchestration.test_store import (
    NOW,
    _artifacts,
    _command,
    _create,
    _plan,
    _register_worker,
    _success,
)


def _revision_two() -> Plan:
    original = _plan()
    tasks = []
    for task in original.tasks:
        value = task.model_dump(mode="json")
        if task.task_id == "work-a":
            value["contract"] = "Produce patch-a for the revised plan."
            value["priority"] = 3
        tasks.append(Task.model_validate(value))
    return Plan.model_validate(
        {
            **original.model_dump(mode="json"),
            "previous_revision": 1,
            "revision": 2,
            "tasks": [item.model_dump(mode="json") for item in tasks],
        }
    )


def test_revision_invalidates_old_work_and_cold_replay_uses_fresh_tasks(
    tmp_path,
) -> None:
    path = tmp_path / "missions.sqlite"
    store = SQLiteMissionStore(path)
    _create(store)
    store.refresh_ready("mission-1", _command("ready-old"), recorded_at=NOW)
    _register_worker(store, "worker-a", capabilities=(TaskKind.WORK,))
    _register_worker(store, "worker-b", capabilities=(TaskKind.WORK,))
    old_work_a = store.claim_task(
        "mission-1",
        "work-a",
        "worker-a",
        _command("claim-old-a"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    old_work_b = store.claim_task(
        "mission-1",
        "work-b",
        "worker-b",
        _command("claim-old-b"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    old_task_b = next(task for task in _plan().tasks if task.task_id == "work-b")
    store.complete_attempt(
        "mission-1",
        old_work_b.attempt_id,
        old_work_b.worker_id,
        old_work_b.lease_id,
        old_work_b.fencing_token,
        _success(old_work_b, old_task_b, _artifacts(store)),
        _command("complete-old-b"),
        recorded_at=NOW + timedelta(seconds=1),
        retry_backoff_seconds=0,
    )

    stale_head = store.head("mission-1")
    requested = store.request_replan(
        "mission-1",
        _command("request-replan"),
        expected_head=stale_head,
        reason="The work contract changed.",
        operator_label="api-operator",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=2),
    )
    assert store.snapshot("mission-1").mission.status == MissionStatus.PAUSED

    revised = _revision_two()
    with pytest.raises(MissionConflict, match="expected head"):
        store.revise_plan(
            "mission-1",
            revised,
            _command("revise-stale"),
            expected_head=stale_head,
            recorded_at=NOW + timedelta(seconds=3),
        )
    store.revise_plan(
        "mission-1",
        revised,
        _command("revise-current"),
        expected_head=requested,
        recorded_at=NOW + timedelta(seconds=3),
    )

    snapshot = store.snapshot("mission-1")
    assert snapshot.mission.plan_revision == snapshot.plan.revision == 2
    assert snapshot.mission.status == MissionStatus.PAUSED
    assert all(
        task.state == TaskState.QUEUED and task.attempt_count == 0
        for task in snapshot.tasks
    )
    old_attempt = next(
        item for item in snapshot.attempts if item.attempt_id == old_work_a.attempt_id
    )
    old_lease = next(
        item for item in snapshot.leases if item.lease_id == old_work_a.lease_id
    )
    assert old_attempt.state == AttemptState.ABANDONED
    assert old_attempt.result_code == "plan_revised"
    assert old_lease.release_reason == "plan_revised"
    assert all(
        publication.state == PublicationState.REJECTED
        for publication in snapshot.publications
    )

    diff = store.plan_diff("mission-1", 1, 2)
    revised_event = next(
        event
        for event in store.tail("mission-1", 0, 256)
        if event.event_type == MissionEventType.PLAN_REVISED
    )
    assert revised_event.payload["diff_sha256"] == canonical_json_sha256(
        {key: value for key, value in diff.items() if key != "diff_sha256"}
    )
    assert "tasks" not in revised_event.payload
    assert diff["tasks"]["changed"][0]["after"]["contract"].endswith("revised plan.")

    old_task_a = next(task for task in _plan().tasks if task.task_id == "work-a")
    with pytest.raises(StaleWorker):
        store.complete_attempt(
            "mission-1",
            old_work_a.attempt_id,
            old_work_a.worker_id,
            old_work_a.lease_id,
            old_work_a.fencing_token,
            _success(old_work_a, old_task_a, _artifacts(store)),
            _command("late-old-a"),
            recorded_at=NOW + timedelta(seconds=4),
            retry_backoff_seconds=0,
        )

    store.approve_plan(
        "mission-1",
        _command("approve-revised"),
        expected_revision=2,
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="The revision is validated.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=5),
    )
    artifacts = _artifacts(store)
    cold = SQLiteMissionStore(path, artifact_resolver=artifacts)
    assert cold.verify("mission-1") == cold.head("mission-1")
    assert cold.snapshot("mission-1").mission.status == MissionStatus.RUNNING
    assert MissionProjection(cold).snapshot("mission-1").mission.plan_revision == 2


def test_revision_rejects_unrequested_or_mission_mismatched_plan(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.pause(
        "mission-1",
        _command("pause-not-replan"),
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="Inspect first.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    with pytest.raises(MissionConflict, match="not requested"):
        store.revise_plan(
            "mission-1",
            _revision_two(),
            _command("unrequested"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=1),
        )

    store.resume(
        "mission-1",
        _command("resume-before-request"),
        expected_head=store.head("mission-1"),
        operator_label="api-operator",
        rationale="Continue to request the revision.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=2),
    )
    store.request_replan(
        "mission-1",
        _command("request-mismatch"),
        expected_head=store.head("mission-1"),
        reason="Revise now.",
        operator_label="api-operator",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW + timedelta(seconds=3),
    )
    changed = _revision_two().model_dump(mode="json")
    changed["criteria"][0]["description"] = "A different criterion."
    with pytest.raises(MissionConflict, match="bindings do not match"):
        store.revise_plan(
            "mission-1",
            Plan.model_validate(changed),
            _command("criteria-mismatch"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=4),
        )

    over_policy = _revision_two().model_dump(mode="json")
    over_policy["max_concurrency"] = 5
    with pytest.raises(PlanValidationError):
        store.revise_plan(
            "mission-1",
            Plan.model_validate(over_policy),
            _command("policy-mismatch"),
            expected_head=store.head("mission-1"),
            recorded_at=NOW + timedelta(seconds=5),
        )

    noncontiguous = _revision_two().model_dump(mode="json")
    noncontiguous["previous_revision"] = 2
    with pytest.raises(ValidationError, match="link contiguously"):
        Plan.model_validate(noncontiguous)
