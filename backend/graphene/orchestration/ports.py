from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..core_models import TruthKind
from .mission_models import (
    AttemptResult,
    Dispatch,
    Lease,
    MissionHead,
    MissionSnapshot,
    Task,
    TaskKind,
    WorkerRegistration,
    WorkerRevocation,
)
from .sqlite_mission_store import BudgetExhausted, LeaseConflict


@runtime_checkable
class SchedulerStore(Protocol):
    """Persistence operations required by ``MissionScheduler``."""

    def register_worker(
        self,
        mission_id: str,
        worker_id: str,
        runtime_id: str,
        capabilities: tuple[TaskKind, ...],
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> WorkerRegistration: ...

    def revoke_worker(
        self,
        mission_id: str,
        worker_id: str,
        reason_code: str,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> WorkerRevocation: ...

    def worker_registration(
        self,
        mission_id: str,
        worker_id: str,
        *,
        active_only: bool = False,
    ) -> WorkerRegistration | None: ...

    def head(self, mission_id: str) -> MissionHead: ...

    def expire_leases(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
        retry_backoff_seconds: int,
    ) -> tuple[str, ...]: ...

    def snapshot(self, mission_id: str) -> MissionSnapshot: ...

    def enter_awaiting_result(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> MissionHead: ...

    def refresh_ready(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> tuple[str, ...]: ...

    def recover_dispatches(
        self,
        mission_id: str,
        worker_ids: tuple[str, ...],
        *,
        recorded_at: datetime,
    ) -> tuple[Dispatch, ...]: ...

    def ready_tasks(self, mission_id: str) -> tuple[Task, ...]: ...

    def claim_task(
        self,
        mission_id: str,
        task_id: str,
        worker_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
        ttl_seconds: int,
    ) -> Dispatch: ...

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
    ) -> Lease: ...

    def assert_fence(self, dispatch: Dispatch, *, recorded_at: datetime) -> None: ...

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
    ) -> MissionHead: ...

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
    ) -> MissionHead: ...

    def resume(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_head: MissionHead,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead: ...

    def cancel(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_head: MissionHead,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead: ...


__all__ = ["BudgetExhausted", "LeaseConflict", "SchedulerStore"]
