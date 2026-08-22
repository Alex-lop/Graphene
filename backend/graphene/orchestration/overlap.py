from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ..models import FrozenModel, Identifier
from .models import Lease, MissionSnapshot, TaskKind

OVERLAP_NOTE = (
    "Overlap is derived from durable attempt and lease timestamps recorded by "
    "the mission store clock; it is not a provider-side measurement."
)


class OverlapPair(FrozenModel):
    first_attempt_id: Identifier
    second_attempt_id: Identifier
    first_worker_id: Identifier
    second_worker_id: Identifier
    window_ms: int = Field(ge=0)
    basis: Literal["attempt_timestamps", "lease_timestamps"]


class OverlapMeasurement(FrozenModel):
    observed: bool
    max_window_ms: int = Field(ge=0)
    pairs: tuple[OverlapPair, ...]
    attempt_count: int = Field(ge=0)
    note: str


def _window_ms(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> int:
    window = min(first_end, second_end) - max(first_start, second_start)
    return max(0, int(window.total_seconds() * 1000))


def _lease_end(lease: Lease) -> datetime:
    return lease.released_at if lease.released_at is not None else lease.heartbeat_at


def measure_overlap(
    snapshot: MissionSnapshot, *, task_kind: TaskKind = TaskKind.WORK
) -> OverlapMeasurement:
    """Measure pairwise concurrency of terminal attempts from durable timestamps.

    Every terminal attempt of ``task_kind`` counts, in any terminal state: a
    failed attempt that overlapped still overlapped. Each unordered pair with
    distinct worker IDs yields one ``attempt_timestamps`` pair and, when both
    attempts hold a lease in the snapshot, one ``lease_timestamps`` pair.
    """

    kinds = {task.task_id: task.kind for task in snapshot.plan.tasks}
    kinds.update({task.task_id: task.kind for task in snapshot.tasks})
    attempts = tuple(
        attempt
        for attempt in snapshot.attempts
        if kinds.get(attempt.task_id) == task_kind and attempt.ended_at is not None
    )
    leases = {lease.attempt_id: lease for lease in snapshot.leases}
    pairs: list[OverlapPair] = []
    for index, first in enumerate(attempts):
        for second in attempts[index + 1 :]:
            if first.worker_id == second.worker_id:
                continue
            assert first.ended_at is not None and second.ended_at is not None
            pairs.append(
                OverlapPair(
                    first_attempt_id=first.attempt_id,
                    second_attempt_id=second.attempt_id,
                    first_worker_id=first.worker_id,
                    second_worker_id=second.worker_id,
                    window_ms=_window_ms(
                        first.started_at,
                        first.ended_at,
                        second.started_at,
                        second.ended_at,
                    ),
                    basis="attempt_timestamps",
                )
            )
            first_lease = leases.get(first.attempt_id)
            second_lease = leases.get(second.attempt_id)
            if first_lease is None or second_lease is None:
                continue
            pairs.append(
                OverlapPair(
                    first_attempt_id=first.attempt_id,
                    second_attempt_id=second.attempt_id,
                    first_worker_id=first.worker_id,
                    second_worker_id=second.worker_id,
                    window_ms=_window_ms(
                        first_lease.issued_at,
                        _lease_end(first_lease),
                        second_lease.issued_at,
                        _lease_end(second_lease),
                    ),
                    basis="lease_timestamps",
                )
            )
    return OverlapMeasurement(
        observed=any(pair.window_ms > 0 for pair in pairs),
        max_window_ms=max((pair.window_ms for pair in pairs), default=0),
        pairs=tuple(pairs),
        attempt_count=len(attempts),
        note=OVERLAP_NOTE,
    )


__all__ = [
    "OVERLAP_NOTE",
    "OverlapMeasurement",
    "OverlapPair",
    "measure_overlap",
]
