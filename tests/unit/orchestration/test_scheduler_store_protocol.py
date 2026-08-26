from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from graphene.core_models import TruthKind
from graphene.orchestration.mission_models import (
    AttemptResult,
    Dispatch,
    Lease,
    MissionHead,
    MissionSnapshot,
    MissionStatus,
    Task,
    TaskKind,
    WorkerRegistration,
    WorkerRevocation,
)
from graphene.orchestration.ports import SchedulerStore
from graphene.orchestration.scheduler import MissionScheduler
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore

NOW = datetime(2026, 8, 20, tzinfo=UTC)


class FakeClock:
    def now(self) -> datetime:
        return NOW


class FakeSchedulerStore:
    """Small in-memory structural fake; only the empty-mission path is stateful."""

    def __init__(self) -> None:
        self.registration: WorkerRegistration | None = None
        self.calls: list[str] = []

    def register_worker(
        self,
        mission_id: str,
        worker_id: str,
        runtime_id: str,
        capabilities: tuple[TaskKind, ...],
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> WorkerRegistration:
        self.calls.append("register_worker")
        self.registration = WorkerRegistration(
            registration_id="worker-registration-1",
            mission_id=mission_id,
            worker_id=worker_id,
            runtime_id=runtime_id,
            capabilities=capabilities,
            registered_at=recorded_at,
        )
        return self.registration

    def revoke_worker(
        self,
        mission_id: str,
        worker_id: str,
        reason_code: str,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> WorkerRevocation:
        raise NotImplementedError

    def worker_registration(
        self, mission_id: str, worker_id: str, *, active_only: bool = False
    ) -> WorkerRegistration | None:
        self.calls.append("worker_registration")
        return self.registration

    def head(self, mission_id: str) -> MissionHead:
        self.calls.append("head")
        return MissionHead(
            mission_id=mission_id, seq=0, event_sha256=None, event_count=0
        )

    def expire_leases(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
        retry_backoff_seconds: int,
    ) -> tuple[str, ...]:
        self.calls.append("expire_leases")
        return ()

    def snapshot(self, mission_id: str) -> MissionSnapshot:
        self.calls.append("snapshot")
        return cast(
            MissionSnapshot,
            SimpleNamespace(
                mission=SimpleNamespace(status=MissionStatus.RUNNING),
                tasks=(),
                attempts=(),
            ),
        )

    def enter_awaiting_result(
        self, mission_id: str, command_id: str, *, recorded_at: datetime
    ) -> MissionHead:
        raise NotImplementedError

    def refresh_ready(
        self, mission_id: str, command_id: str, *, recorded_at: datetime
    ) -> tuple[str, ...]:
        self.calls.append("refresh_ready")
        return ()

    def recover_dispatches(
        self, mission_id: str, worker_ids: tuple[str, ...], *, recorded_at: datetime
    ) -> tuple[Dispatch, ...]:
        self.calls.append("recover_dispatches")
        return ()

    def ready_tasks(self, mission_id: str) -> tuple[Task, ...]:
        self.calls.append("ready_tasks")
        return ()

    def claim_task(
        self,
        mission_id: str,
        task_id: str,
        worker_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
        ttl_seconds: int,
    ) -> Dispatch:
        raise NotImplementedError

    def heartbeat(
        self,
        mission_id: str,
        attempt_id: str,
        owner: str,
        lease_id: str,
        fencing_token: int,
        command_id: str,
        *,
        recorded_at: datetime,
        ttl_seconds: int,
    ) -> Lease:
        raise NotImplementedError

    def assert_fence(self, dispatch: Dispatch, *, recorded_at: datetime) -> None:
        raise NotImplementedError

    def complete_attempt(
        self,
        mission_id: str,
        attempt_id: str,
        owner: str,
        lease_id: str,
        fencing_token: int,
        result: AttemptResult,
        command_id: str,
        *,
        recorded_at: datetime,
        retry_backoff_seconds: int,
    ) -> MissionHead:
        raise NotImplementedError

    def pause(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_head: MissionHead,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        raise NotImplementedError

    resume = pause
    cancel = pause


def test_sqlite_and_structural_fake_conform_to_scheduler_store(tmp_path) -> None:
    assert isinstance(SQLiteMissionStore(tmp_path / "missions.sqlite"), SchedulerStore)
    assert isinstance(FakeSchedulerStore(), SchedulerStore)


def test_structural_fake_drives_scheduler_without_sqlite() -> None:
    store = FakeSchedulerStore()

    assert (
        MissionScheduler(store, clock=FakeClock()).tick("mission-1", ("worker-1",))
        == ()
    )
    assert store.registration is not None
    assert store.calls == [
        "head",
        "expire_leases",
        "head",
        "snapshot",
        "worker_registration",
        "register_worker",
        "worker_registration",
        "head",
        "refresh_ready",
        "recover_dispatches",
        "ready_tasks",
    ]
