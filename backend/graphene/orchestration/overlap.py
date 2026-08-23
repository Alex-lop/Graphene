from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import Field

from ..models import FrozenModel, Identifier
from .models import Lease, MissionSnapshot, TaskKind
from .runtime import WorkerProviderReceipt, parse_provider_call_timestamp

OVERLAP_NOTE = (
    "`observed` is the intersection of attempt lifetimes on the mission store "
    "clock (scheduler claim to completion), which proves simultaneous leases, "
    "not concurrent execution. `provider_call_observed` is the intersection of "
    "the workers' provider call windows stamped by the runtime and bound into "
    "evidence receipts; a real-agent overlap claim must cite that measurement. "
    "`provider_reported_observed` is the same intersection measured on the "
    "provider's own clock, from each receipt's server-side `create_time` to "
    "its whole-second HTTP `Date` reply header; it is independent of every "
    "Graphene clock and underestimates the true window by up to one second."
)

OverlapBasis = Literal[
    "attempt_timestamps",
    "lease_timestamps",
    "provider_call_timestamps",
    "provider_reported_timestamps",
]
PROVIDER_CALL_BASIS: OverlapBasis = "provider_call_timestamps"
PROVIDER_REPORTED_BASIS: OverlapBasis = "provider_reported_timestamps"


class OverlapPair(FrozenModel):
    first_attempt_id: Identifier
    second_attempt_id: Identifier
    first_worker_id: Identifier
    second_worker_id: Identifier
    window_ms: int = Field(ge=0)
    basis: OverlapBasis


class OverlapMeasurement(FrozenModel):
    observed: bool
    max_window_ms: int = Field(ge=0)
    provider_call_observed: bool
    provider_call_max_window_ms: int = Field(ge=0)
    provider_reported_observed: bool = False
    provider_reported_max_window_ms: int = Field(default=0, ge=0)
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
    snapshot: MissionSnapshot,
    *,
    task_kind: TaskKind = TaskKind.WORK,
    provider_receipts: Mapping[str, WorkerProviderReceipt] | None = None,
) -> OverlapMeasurement:
    """Measure pairwise concurrency of terminal attempts on three bases.

    Every terminal attempt of ``task_kind`` counts, in any terminal state: a
    failed attempt that overlapped still overlapped. Each unordered pair with
    distinct worker IDs yields one ``attempt_timestamps`` pair (attempt
    lifetime: scheduler claim to completion on the mission store clock) and,
    when both attempts hold a lease in the snapshot, one ``lease_timestamps``
    pair. The lease basis is durable, but for terminal attempts it coincides
    with the attempt basis because the store stamps ``issued_at`` at claim and
    ``released_at`` at completion; neither proves concurrent execution.

    ``provider_receipts`` maps attempt id to that attempt's evidence-resolved
    ``WorkerProviderReceipt``. When both attempts of a pair have one, a
    ``provider_call_timestamps`` pair is computed from the receipts'
    ``call_started_at``/``call_ended_at`` windows, which the runtime stamps
    immediately around the model run. ``observed``/``max_window_ms`` report the
    lifetime bases only; ``provider_call_observed``/``provider_call_max_window_ms``
    report the provider-call basis only. When both receipts also carry the
    provider's own stamps (``provider_reported_window``), a fourth
    ``provider_reported_timestamps`` pair is measured on the provider clock
    alone and reported as ``provider_reported_observed``/``_max_window_ms``.
    """

    receipts: Mapping[str, WorkerProviderReceipt] = (
        {} if provider_receipts is None else provider_receipts
    )
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
            identity = {
                "first_attempt_id": first.attempt_id,
                "second_attempt_id": second.attempt_id,
                "first_worker_id": first.worker_id,
                "second_worker_id": second.worker_id,
            }
            pairs.append(
                OverlapPair(
                    **identity,
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
            if first_lease is not None and second_lease is not None:
                pairs.append(
                    OverlapPair(
                        **identity,
                        window_ms=_window_ms(
                            first_lease.issued_at,
                            _lease_end(first_lease),
                            second_lease.issued_at,
                            _lease_end(second_lease),
                        ),
                        basis="lease_timestamps",
                    )
                )
            first_receipt = receipts.get(first.attempt_id)
            second_receipt = receipts.get(second.attempt_id)
            if first_receipt is not None and second_receipt is not None:
                pairs.append(
                    OverlapPair(
                        **identity,
                        window_ms=_window_ms(
                            parse_provider_call_timestamp(
                                first_receipt.call_started_at
                            ),
                            parse_provider_call_timestamp(first_receipt.call_ended_at),
                            parse_provider_call_timestamp(
                                second_receipt.call_started_at
                            ),
                            parse_provider_call_timestamp(second_receipt.call_ended_at),
                        ),
                        basis=PROVIDER_CALL_BASIS,
                    )
                )
                first_window = first_receipt.provider_reported_window()
                second_window = second_receipt.provider_reported_window()
                if first_window is not None and second_window is not None:
                    pairs.append(
                        OverlapPair(
                            **identity,
                            window_ms=_window_ms(*first_window, *second_window),
                            basis=PROVIDER_REPORTED_BASIS,
                        )
                    )
    lifetime = tuple(
        pair
        for pair in pairs
        if pair.basis not in {PROVIDER_CALL_BASIS, PROVIDER_REPORTED_BASIS}
    )
    provider = tuple(pair for pair in pairs if pair.basis == PROVIDER_CALL_BASIS)
    reported = tuple(pair for pair in pairs if pair.basis == PROVIDER_REPORTED_BASIS)
    return OverlapMeasurement(
        observed=any(pair.window_ms > 0 for pair in lifetime),
        max_window_ms=max((pair.window_ms for pair in lifetime), default=0),
        provider_call_observed=any(pair.window_ms > 0 for pair in provider),
        provider_call_max_window_ms=max(
            (pair.window_ms for pair in provider), default=0
        ),
        provider_reported_observed=any(pair.window_ms > 0 for pair in reported),
        provider_reported_max_window_ms=max(
            (pair.window_ms for pair in reported), default=0
        ),
        pairs=tuple(pairs),
        attempt_count=len(attempts),
        note=OVERLAP_NOTE,
    )


__all__ = [
    "OVERLAP_NOTE",
    "PROVIDER_CALL_BASIS",
    "PROVIDER_REPORTED_BASIS",
    "OverlapBasis",
    "OverlapMeasurement",
    "OverlapPair",
    "measure_overlap",
]
