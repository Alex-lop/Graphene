from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from graphene.models import TruthKind
from graphene.orchestration.models import (
    ArtifactRequirement,
    Mission,
    MissionStatus,
    Plan,
    TaskKind,
)
from graphene.orchestration.scheduler import MissionScheduler
from graphene.orchestration.store import SQLiteMissionStore, StaleWorker

from .test_store import (
    NOW,
    MemoryArtifacts,
    _artifacts,
    _command,
    _create,
    _mission,
    _policy,
    _success,
    _task,
)


@dataclass
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def _task_for(store: SQLiteMissionStore, mission_id: str, task_id: str):
    return next(
        task for task in store.snapshot(mission_id).tasks if task.task_id == task_id
    )


def test_scheduler_is_deterministic_recovers_and_runs_full_dependency_chain(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    clock = FakeClock(NOW)
    scheduler = MissionScheduler(store, clock=clock, lease_ttl_seconds=30)

    work = scheduler.tick("mission-1", ("worker-b", "worker-a"))
    recovered = scheduler.tick("mission-1", ("worker-b", "worker-a"))

    assert tuple((item.task_id, item.worker_id) for item in work) == (
        ("work-a", "worker-a"),
        ("work-b", "worker-b"),
    )
    assert recovered == work
    for dispatch in work:
        scheduler.complete(
            dispatch,
            _success(
                dispatch,
                _task_for(store, "mission-1", dispatch.task_id),
                _artifacts(store),
            ),
        )

    assembly = scheduler.tick("mission-1", ("worker-a",))
    assert tuple(item.task_id for item in assembly) == ("assemble",)
    scheduler.complete(
        assembly[0],
        _success(
            assembly[0], _task_for(store, "mission-1", "assemble"), _artifacts(store)
        ),
    )
    verification = scheduler.tick("mission-1", ("worker-a",))
    assert tuple(item.task_id for item in verification) == ("verify",)
    scheduler.complete(
        verification[0],
        _success(
            verification[0],
            _task_for(store, "mission-1", "verify"),
            _artifacts(store),
        ),
    )

    assert store.snapshot("mission-1").mission.status == MissionStatus.AWAITING_RESULT
    assert scheduler.tick("mission-1", ("worker-a",)) == ()
    assert store.verify("mission-1") == store.head("mission-1")


def test_dispatch_limiter_caps_only_new_work_and_keeps_recovery_visible(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    calls: list[tuple[str, int]] = []
    permitted = [0]

    def limiter(mission_id: str, configured_limit: int) -> int:
        calls.append((mission_id, configured_limit))
        return min(permitted[0], configured_limit)

    scheduler = MissionScheduler(
        store,
        clock=FakeClock(NOW),
        lease_ttl_seconds=30,
        dispatch_limiter=limiter,
    )

    assert scheduler.tick("mission-1", ("worker-a", "worker-b")) == ()
    assert calls[-1] == ("mission-1", 2)
    permitted[0] = 1
    active = scheduler.tick("mission-1", ("worker-a", "worker-b"))
    permitted[0] = 0
    under_pressure = scheduler.tick("mission-1", ("worker-a", "worker-b"))

    assert len(active) == 1
    assert under_pressure == active
    assert len(store.recover_dispatches("mission-1", recorded_at=NOW)) == 1
    with pytest.raises(ValueError, match="invalid slot"):
        MissionScheduler(
            store,
            clock=FakeClock(NOW),
            dispatch_limiter=lambda _mission_id, configured: configured + 1,
        ).tick("mission-1", ("worker-a", "worker-b", "worker-c"))


def test_scheduler_expiry_retries_with_a_higher_fence(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    clock = FakeClock(NOW)
    scheduler = MissionScheduler(
        store,
        clock=clock,
        lease_ttl_seconds=5,
        retry_backoff_seconds=0,
    )
    first = scheduler.tick("mission-1", ("worker-a",))[0]
    clock.advance(6)
    second = scheduler.tick("mission-1", ("worker-b",))[0]

    assert second.task_id == first.task_id
    assert second.fencing_token == first.fencing_token + 1
    with pytest.raises(StaleWorker):
        scheduler.complete(
            first,
            _success(
                first, _task_for(store, "mission-1", first.task_id), _artifacts(store)
            ),
        )


def test_scheduler_cancel_cleans_state_and_invokes_worker_cleanup(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    scheduler = MissionScheduler(store, clock=FakeClock(NOW))
    active = scheduler.tick("mission-1", ("worker-a", "worker-b"))

    class CancellingWorker:
        def __init__(self) -> None:
            self.cancelled = []

        def execute(self, dispatch):  # pragma: no cover - protocol shape only
            raise AssertionError(dispatch)

        def cancel(self, dispatch) -> None:
            self.cancelled.append(dispatch)

    worker = CancellingWorker()
    returned = scheduler.cancel(
        "mission-1",
        worker=worker,
        operator_label="non-tty-api",
        rationale="Cancel all Graphene-owned work.",
        truth_kind=TruthKind.SERVER_DERIVED,
    )

    assert returned == active
    assert tuple(worker.cancelled) == active
    assert store.snapshot("mission-1").mission.status == MissionStatus.CANCELLED
    assert store.recover_dispatches("mission-1", recorded_at=NOW) == ()


def _soak_plan(mission_id: str) -> Plan:
    work = tuple(
        _task(
            f"work-{index:02d}",
            f"patch-{index:02d}",
            "patch",
            f"app/generated-{index:02d}.py",
        )
        for index in range(48)
    )
    dependencies = tuple(task.task_id for task in work)
    inputs = tuple(
        ArtifactRequirement(
            producer_task_id=task.task_id,
            name=task.expected_outputs[0].name,
            kind="patch",
        )
        for task in work
    )
    assembly = _task(
        "assemble",
        "candidate",
        "candidate-patch",
        "out/candidate.patch",
        kind=TaskKind.ASSEMBLY,
        role="assembler",
        dependencies=dependencies,
        inputs=inputs,
    )
    verification = _task(
        "verify",
        "verification",
        "test-receipt",
        "out/verification.json",
        kind=TaskKind.VERIFICATION,
        role="verifier",
        dependencies=("assemble",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="assemble",
                name="candidate",
                kind="candidate-patch",
            ),
        ),
    )
    return Plan(
        mission_id=mission_id,
        revision=1,
        tasks=tuple(sorted((*work, assembly, verification), key=lambda task: task.task_id)),
        max_concurrency=10,
    )


def test_deterministic_fifty_task_ten_worker_soak(tmp_path) -> None:
    mission_id = "mission-soak"
    store = SQLiteMissionStore(
        tmp_path / "soak.sqlite", artifact_resolver=MemoryArtifacts()
    )
    policy = _policy(max_concurrency=10)
    base = _mission(mission_id)
    mission = Mission.model_validate(
        {
            **base.model_dump(mode="json"),
            "resource_budget": policy.resource_budget.model_dump(mode="json"),
        }
    )
    store.create_mission(
        policy,
        mission,
        _soak_plan(mission_id),
        _command("soak-create"),
        recorded_at=NOW,
    )
    store.approve_plan(
        mission_id,
        _command("soak-approve"),
        expected_revision=1,
        operator_label="soak-fixture",
        rationale="Deterministic bounded soak.",
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        recorded_at=NOW,
    )
    scheduler = MissionScheduler(store, clock=FakeClock(NOW), lease_ttl_seconds=30)
    workers = tuple(f"worker-{index:02d}" for index in range(10))
    trace: list[tuple[str, str, int]] = []

    for _round in range(10):
        dispatches = scheduler.tick(mission_id, workers)
        for dispatch in dispatches:
            trace.append((dispatch.task_id, dispatch.worker_id, dispatch.fencing_token))
            scheduler.complete(
                dispatch,
                _success(
                    dispatch,
                    _task_for(store, mission_id, dispatch.task_id),
                    _artifacts(store),
                ),
            )
        if store.snapshot(mission_id).mission.status == MissionStatus.AWAITING_RESULT:
            break

    snapshot = store.snapshot(mission_id)
    assert len(trace) == 50
    assert trace[:10] == [
        (f"work-{index:02d}", f"worker-{index:02d}", 1) for index in range(10)
    ]
    assert tuple(item.task_id for item in snapshot.tasks if item.state.value == "done") == tuple(
        item.task_id for item in snapshot.tasks
    )
    assert len(snapshot.attempts) == len(snapshot.publications) == 50
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert store.verify(mission_id) == store.head(mission_id)
