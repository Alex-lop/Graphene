from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from graphene.core_models import TruthKind
from graphene.orchestration.mission_models import (
    ArtifactRequirement,
    Criterion,
    CriterionVerificationKind,
    Gate,
    GateDecision,
    Mission,
    MissionEventType,
    MissionStatus,
    Plan,
    TaskKind,
    WorkerRegistration,
)
from graphene.orchestration.scheduler import MissionScheduler
from graphene.orchestration.sqlite_mission_store import (
    LeaseConflict,
    MissionStoreError,
    SQLiteMissionStore,
    StaleWorker,
)

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


def test_scheduler_is_deterministic_recovers_and_runs_full_dependency_chain(
    tmp_path,
) -> None:
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


def test_scheduler_returns_only_dispatches_owned_by_the_authenticated_worker(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    clock = FakeClock(NOW)

    worker_a = MissionScheduler(store, clock=clock, lease_ttl_seconds=30)
    worker_b = MissionScheduler(store, clock=clock, lease_ttl_seconds=30)

    first = worker_a.tick("mission-1", ("worker-a",))
    second = worker_b.tick("mission-1", ("worker-b",))

    assert tuple(item.worker_id for item in first) == ("worker-a",)
    assert tuple(item.worker_id for item in second) == ("worker-b",)
    assert first[0].attempt_id != second[0].attempt_id


def test_scheduler_persists_runtime_capabilities_and_denies_other_task_kinds(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    clock = FakeClock(NOW)
    work_scheduler = MissionScheduler(
        store,
        clock=clock,
        runtime_id="gemini_runtime",
        worker_capabilities=(TaskKind.WORK,),
    )

    dispatch = work_scheduler.tick("mission-1", ("worker-work",))[0]
    with sqlite3.connect(store.path) as connection:
        row = connection.execute(
            "SELECT registration_bytes FROM mission_workers "
            "WHERE mission_id = 'mission-1' AND worker_id = 'worker-work'"
        ).fetchone()
    registration = WorkerRegistration.model_validate_json(row[0])

    assert dispatch.task_kind == TaskKind.WORK
    assert registration.runtime_id == "gemini_runtime"
    assert registration.capabilities == (TaskKind.WORK,)
    assembly_only = MissionScheduler(
        store,
        clock=clock,
        runtime_id="integration_runtime",
        worker_capabilities=(TaskKind.ASSEMBLY,),
    )
    assert assembly_only.tick("mission-1", ("worker-assembly",)) == ()


def test_tick_preserves_narrow_registrations_and_selects_capable_worker(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    clock = FakeClock(NOW)
    scheduler = MissionScheduler(store, clock=clock)
    assembly = scheduler.register_worker(
        "mission-1",
        "worker-a-assembly",
        runtime_id="deterministic_runtime",
        capabilities=(TaskKind.ASSEMBLY,),
    )
    work = scheduler.register_worker(
        "mission-1",
        "worker-z-work",
        runtime_id="gemini_runtime",
        capabilities=(TaskKind.WORK,),
    )

    dispatches = scheduler.tick("mission-1", ("worker-a-assembly", "worker-z-work"))

    assert tuple((item.task_kind, item.worker_id) for item in dispatches) == (
        (TaskKind.WORK, "worker-z-work"),
    )
    assert store.worker_registration("mission-1", "worker-a-assembly") == assembly
    assert store.worker_registration("mission-1", "worker-z-work") == work


def test_dispatch_rejects_unapproved_materialized_status(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store, approve=False)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE missions SET status = 'running' WHERE mission_id = 'mission-1'"
        )

    scheduler = MissionScheduler(store, clock=FakeClock(NOW))
    with pytest.raises(MissionStoreError, match="committed events"):
        scheduler.tick("mission-1", ("worker-a",))

    with pytest.raises(MissionStoreError, match="materialized state"):
        store.snapshot("mission-1")
    with sqlite3.connect(store.path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM mission_attempts WHERE mission_id = 'mission-1'"
            ).fetchone()[0]
            == 0
        )
    assert not any(
        event.event_type == MissionEventType.TASK_STARTED
        for event in store.tail("mission-1", 0, 20)
    )


def test_dispatch_rejects_missing_materialized_gate(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.request_gate(
        Gate(
            gate_id="gate-before-work",
            mission_id="mission-1",
            task_id="work-a",
            reason="Confirm the bounded task before dispatch.",
            allowed_decisions=(GateDecision(value="approve", consequence="Continue."),),
            truth_kind=TruthKind.SERVER_DERIVED,
        ),
        _command("request-gate-before-work"),
        recorded_at=NOW,
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "DELETE FROM mission_gates WHERE mission_id = 'mission-1' "
            "AND gate_id = 'gate-before-work'"
        )

    scheduler = MissionScheduler(store, clock=FakeClock(NOW))
    with pytest.raises(MissionStoreError, match="committed events"):
        scheduler.tick("mission-1", ("worker-a",))
    assert not any(
        event.event_type == MissionEventType.TASK_STARTED
        for event in store.tail("mission-1", 0, 20)
    )


def test_unresolved_mission_gate_blocks_every_new_dispatch(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    store.refresh_ready(
        "mission-1", _command("ready-before-mission-gate"), recorded_at=NOW
    )
    gate = Gate(
        gate_id="gate-mission",
        mission_id="mission-1",
        reason="Confirm the mission before any new work is dispatched.",
        allowed_decisions=(
            GateDecision(value="continue", consequence="Resume dispatch."),
        ),
        truth_kind=TruthKind.SERVER_DERIVED,
    )
    store.request_gate(gate, _command("request-mission-gate"), recorded_at=NOW)
    scheduler = MissionScheduler(store, clock=FakeClock(NOW))

    assert scheduler.tick("mission-1", ("worker-a",)) == ()
    assert store.ready_tasks("mission-1") == ()
    with pytest.raises(LeaseConflict, match="mission has an unresolved gate"):
        store.claim_task(
            "mission-1",
            "work-a",
            "worker-a",
            _command("claim-through-mission-gate"),
            recorded_at=NOW,
            ttl_seconds=30,
        )
    assert not any(
        event.event_type == MissionEventType.TASK_STARTED
        for event in store.tail("mission-1", 0, 100)
    )

    store.decide_gate(
        "mission-1",
        gate.gate_id,
        "continue",
        _command("resolve-mission-gate"),
        expected_head=store.head("mission-1"),
        operator_label="non-tty-api",
        rationale="Proceed with the approved mission.",
        truth_kind=TruthKind.SERVER_DERIVED,
        recorded_at=NOW,
    )
    assert tuple(
        dispatch.task_id for dispatch in scheduler.tick("mission-1", ("worker-a",))
    ) == ("work-a",)
    store.request_gate(
        gate.model_copy(
            update={
                "gate_id": "gate-mission-after-dispatch",
                "operator_label": None,
                "rationale": None,
                "resolution": None,
            }
        ),
        _command("request-mission-gate-after-dispatch"),
        recorded_at=NOW,
    )
    assert scheduler.tick("mission-1", ("worker-a",)) == ()
    assert store.recover_dispatches("mission-1", ("worker-a",), recorded_at=NOW) == ()


def test_tick_commits_budget_block_instead_of_spinning_on_claim_conflict(
    tmp_path,
) -> None:
    policy = _policy().model_copy(
        update={
            "resource_budget": _policy().resource_budget.model_copy(
                update={"max_worker_seconds": 1}
            )
        }
    )
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store, policy=policy)
    scheduler = MissionScheduler(store, clock=FakeClock(NOW), lease_ttl_seconds=30)

    dispatched = scheduler.tick("mission-1", ("worker-a", "worker-b"))

    assert tuple(item.task_id for item in dispatched) == ("work-a",)
    assert dispatched[0].expires_at == NOW + timedelta(seconds=1)
    snapshot = store.snapshot("mission-1")
    blocked = next(task for task in snapshot.tasks if task.task_id == "work-b")
    assert snapshot.mission.status == MissionStatus.PAUSED
    assert (blocked.state.value, blocked.blocker) == (
        "blocked",
        "budget:worker_seconds",
    )
    assert scheduler.tick("mission-1", ("worker-a", "worker-b")) == ()


def test_tick_recovers_final_completion_before_awaiting_result_commit(tmp_path) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    scheduler = MissionScheduler(store, clock=FakeClock(NOW), lease_ttl_seconds=30)
    workers = ("worker-a", "worker-b")
    for _ in range(2):
        for dispatch in scheduler.tick("mission-1", workers):
            scheduler.complete(
                dispatch,
                _success(
                    dispatch,
                    _task_for(store, "mission-1", dispatch.task_id),
                    _artifacts(store),
                ),
            )
    verification = scheduler.tick("mission-1", workers)[0]
    result = _success(
        verification,
        _task_for(store, "mission-1", verification.task_id),
        _artifacts(store),
    )
    store.complete_attempt(
        verification.mission_id,
        verification.attempt_id,
        verification.worker_id,
        verification.lease_id,
        verification.fencing_token,
        result,
        _command("complete-before-crash"),
        recorded_at=NOW,
        retry_backoff_seconds=0,
    )
    assert store.snapshot("mission-1").mission.status == MissionStatus.RUNNING

    assert (
        MissionScheduler(store, clock=FakeClock(NOW)).tick("mission-1", workers) == ()
    )
    assert store.snapshot("mission-1").mission.status == MissionStatus.AWAITING_RESULT


def test_dispatch_limiter_caps_only_new_work_and_keeps_recovery_visible(
    tmp_path,
) -> None:
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
    assert (
        len(
            store.recover_dispatches(
                "mission-1", ("worker-a", "worker-b"), recorded_at=NOW
            )
        )
        == 1
    )
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
        command_id="command_scheduler_cancel_001",
        expected_head=store.head("mission-1"),
        workers={"worker-a": worker, "worker-b": worker},
        operator_label="non-tty-api",
        rationale="Cancel all Graphene-owned work.",
        truth_kind=TruthKind.SERVER_DERIVED,
    )

    assert returned == active
    assert tuple(worker.cancelled) == active
    assert store.snapshot("mission-1").mission.status == MissionStatus.CANCELLED
    assert (
        store.recover_dispatches("mission-1", ("worker-a", "worker-b"), recorded_at=NOW)
        == ()
    )


def test_scheduler_cancel_routes_exact_owners_and_continues_after_failure(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    scheduler = MissionScheduler(store, clock=FakeClock(NOW))
    active = scheduler.tick("mission-1", ("worker-a", "worker-b"))

    class CancellingWorker:
        def __init__(self, *, fail: bool = False) -> None:
            self.cancelled = []
            self.fail = fail

        def execute(self, dispatch):  # pragma: no cover - protocol shape only
            raise AssertionError(dispatch)

        def cancel(self, dispatch) -> None:
            self.cancelled.append(dispatch)
            if self.fail:
                raise RuntimeError("owned cleanup failed")

    worker_a = CancellingWorker(fail=True)
    worker_b = CancellingWorker()
    unrelated = CancellingWorker()

    with pytest.raises(RuntimeError, match="worker cancellations failed"):
        scheduler.cancel(
            "mission-1",
            command_id="command_scheduler_cancel_owned_001",
            expected_head=store.head("mission-1"),
            workers={"worker-a": worker_a, "worker-b": worker_b},
            operator_label="non-tty-api",
            rationale="Cancel only Graphene-owned work.",
            truth_kind=TruthKind.SERVER_DERIVED,
        )

    by_owner = {dispatch.worker_id: dispatch for dispatch in active}
    assert worker_a.cancelled == [by_owner["worker-a"]]
    assert worker_b.cancelled == [by_owner["worker-b"]]
    assert unrelated.cancelled == []
    assert store.snapshot("mission-1").mission.status == MissionStatus.RUNNING
    assert store.recover_dispatches(
        "mission-1", ("worker-a", "worker-b"), recorded_at=NOW
    ) == active


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
        "patch",
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
                kind="patch",
            ),
        ),
    )
    return Plan(
        mission_id=mission_id,
        revision=1,
        criteria=(
            Criterion(
                criterion_id="criterion-soak",
                description="All checks pass.",
                producer_task_ids=dependencies,
                verification_kind=CriterionVerificationKind.DETERMINISTIC_CHECK,
                verifier_task_id="verify",
                verifier_id="check",
            ),
        ),
        tasks=tuple(
            sorted((*work, assembly, verification), key=lambda task: task.task_id)
        ),
        max_concurrency=5,
    )


def test_deterministic_fifty_task_five_worker_soak(tmp_path) -> None:
    mission_id = "mission-soak"
    store = SQLiteMissionStore(
        tmp_path / "soak.sqlite", artifact_resolver=MemoryArtifacts()
    )
    policy = _policy(max_concurrency=5)
    _artifacts(store).authorize(mission_id, policy)
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
        expected_head=store.head(mission_id),
        operator_label="soak-fixture",
        rationale="Deterministic bounded soak.",
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        recorded_at=NOW,
    )
    scheduler = MissionScheduler(store, clock=FakeClock(NOW), lease_ttl_seconds=30)
    workers = tuple(f"worker-{index:02d}" for index in range(5))
    trace: list[tuple[str, str, int]] = []

    for _round in range(12):
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
    assert trace[:5] == [
        (f"work-{index:02d}", f"worker-{index:02d}", 1) for index in range(5)
    ]
    assert tuple(
        item.task_id for item in snapshot.tasks if item.state.value == "done"
    ) == tuple(item.task_id for item in snapshot.tasks)
    assert len(snapshot.attempts) == len(snapshot.publications) == 50
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert store.verify(mission_id) == store.head(mission_id)
