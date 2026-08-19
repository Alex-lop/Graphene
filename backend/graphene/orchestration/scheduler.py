from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from ..hashing import canonical_json_sha256
from ..models import TruthKind
from .models import AttemptResult, Dispatch, Lease, MissionHead, MissionStatus
from .store import LeaseConflict, SQLiteMissionStore


class Clock(Protocol):
    def now(self) -> datetime: ...


class Worker(Protocol):
    """Runtime seam; the scheduler never grants arbitrary shell authority."""

    def execute(self, dispatch: Dispatch) -> AttemptResult: ...

    def cancel(self, dispatch: Dispatch) -> None: ...


class DispatchLimiter(Protocol):
    """Return the number of currently available slots allowed for new work."""

    def __call__(self, mission_id: str, configured_limit: int) -> int: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _command(label: str, *values: object) -> str:
    return f"{label}_{canonical_json_sha256(values)[:32]}"


class MissionScheduler:
    """Deterministic decisions over committed mission state."""

    def __init__(
        self,
        store: SQLiteMissionStore,
        *,
        clock: Clock,
        lease_ttl_seconds: int = 30,
        retry_backoff_seconds: int = 1,
        dispatch_limiter: DispatchLimiter | None = None,
    ) -> None:
        if type(lease_ttl_seconds) is not int or not 1 <= lease_ttl_seconds <= 3_600:
            raise ValueError("lease TTL must be between 1 and 3600 seconds")
        if (
            type(retry_backoff_seconds) is not int
            or not 0 <= retry_backoff_seconds <= 3_600
        ):
            raise ValueError("retry backoff must be between 0 and 3600 seconds")
        self.store = store
        self.clock = clock
        self.lease_ttl_seconds = lease_ttl_seconds
        self.retry_backoff_seconds = retry_backoff_seconds
        self.dispatch_limiter = dispatch_limiter

    def tick(
        self, mission_id: str, worker_ids: tuple[str, ...]
    ) -> tuple[Dispatch, ...]:
        if len(worker_ids) != len(set(worker_ids)):
            raise ValueError("worker IDs must be unique")
        now = self.clock.now()
        head = self.store.head(mission_id)
        self.store.expire_leases(
            mission_id,
            _command("expire", mission_id, head.seq, now.isoformat()),
            recorded_at=now,
            retry_backoff_seconds=self.retry_backoff_seconds,
        )
        head = self.store.head(mission_id)
        snapshot = self.store.snapshot(mission_id)
        if (
            snapshot.mission.status == MissionStatus.RUNNING
            and snapshot.tasks
            and all(task.state.value == "done" for task in snapshot.tasks)
        ):
            self.store.enter_awaiting_result(
                mission_id,
                _command("await_result", mission_id, head.seq),
                recorded_at=now,
            )
            return ()
        if snapshot.mission.status != MissionStatus.RUNNING:
            return ()
        self.store.refresh_ready(
            mission_id,
            _command("ready", mission_id, head.seq, now.isoformat()),
            recorded_at=now,
        )
        recovered = self.store.recover_dispatches(mission_id, recorded_at=now)
        busy = {item.worker_id for item in recovered}
        available = [item for item in sorted(worker_ids) if item not in busy]
        if self.dispatch_limiter is not None and available:
            limit = self.dispatch_limiter(mission_id, len(available))
            if type(limit) is not int or not 0 <= limit <= len(available):
                raise ValueError("dispatch limiter returned an invalid slot count")
            available = available[:limit]
        claimed: list[Dispatch] = []
        for task in self.store.ready_tasks(mission_id):
            if not available:
                break
            worker_id = available[0]
            head = self.store.head(mission_id)
            try:
                dispatch = self.store.claim_task(
                    mission_id,
                    task.task_id,
                    worker_id,
                    _command(
                        "claim",
                        mission_id,
                        task.task_id,
                        worker_id,
                        head.seq,
                        now.isoformat(),
                    ),
                    recorded_at=now,
                    ttl_seconds=self.lease_ttl_seconds,
                )
            except LeaseConflict:
                continue
            available.pop(0)
            claimed.append(dispatch)
        return (*recovered, *claimed)

    def recover(self, mission_id: str) -> tuple[Dispatch, ...]:
        return self.store.recover_dispatches(mission_id, recorded_at=self.clock.now())

    def heartbeat(self, dispatch: Dispatch) -> Lease:
        now = self.clock.now()
        return self.store.heartbeat(
            dispatch.mission_id,
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            _command("heartbeat", dispatch.dispatch_command_id, now.isoformat()),
            recorded_at=now,
            ttl_seconds=self.lease_ttl_seconds,
        )

    def complete(self, dispatch: Dispatch, result: AttemptResult) -> MissionHead:
        now = self.clock.now()
        head = self.store.complete_attempt(
            dispatch.mission_id,
            dispatch.attempt_id,
            dispatch.worker_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            result,
            _command(
                "complete",
                dispatch.dispatch_command_id,
                canonical_json_sha256(result.model_dump(mode="json")),
            ),
            recorded_at=now,
            retry_backoff_seconds=self.retry_backoff_seconds,
        )
        snapshot = self.store.snapshot(dispatch.mission_id)
        if (
            result.succeeded
            and snapshot.mission.status == MissionStatus.RUNNING
            and snapshot.tasks
            and all(task.state.value == "done" for task in snapshot.tasks)
        ):
            head = self.store.enter_awaiting_result(
                dispatch.mission_id,
                _command("await_result", dispatch.mission_id, head.seq),
                recorded_at=now,
            )
        return head

    def pause(
        self,
        mission_id: str,
        *,
        command_id: str,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
    ) -> MissionHead:
        now = self.clock.now()
        return self.store.pause(
            mission_id,
            command_id,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )

    def resume(
        self,
        mission_id: str,
        *,
        command_id: str,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
    ) -> MissionHead:
        now = self.clock.now()
        return self.store.resume(
            mission_id,
            command_id,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )

    def cancel(
        self,
        mission_id: str,
        *,
        command_id: str,
        worker: Worker,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
    ) -> tuple[Dispatch, ...]:
        now = self.clock.now()
        active = self.store.recover_dispatches(mission_id, recorded_at=now)
        self.store.cancel(
            mission_id,
            command_id,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
        errors: list[Exception] = []
        for dispatch in active:
            try:
                worker.cancel(dispatch)
            except (
                Exception
            ) as error:  # cleanup all owned workers before surfacing failure
                errors.append(error)
        if errors:
            raise RuntimeError("one or more worker cancellations failed") from errors[0]
        return active
