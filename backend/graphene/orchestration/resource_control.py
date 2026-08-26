from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from ..hashing import canonical_json_sha256
from .mission_models import ResourceReceipt
from .resources import (
    DispatchGovernorPolicy,
    ResourcePoint,
    govern_dispatch,
)
from .scheduler import Clock


class ResourceSummaryStore(Protocol):
    def record_resource_summary(
        self,
        receipt: ResourceReceipt,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> object: ...


class ResourceDispatchController:
    """Scheduler limiter that commits every sampled dispatch decision."""

    def __init__(
        self,
        store: ResourceSummaryStore,
        policy: DispatchGovernorPolicy,
        sampler: Callable[[str], Sequence[ResourcePoint]],
        clock: Clock,
    ) -> None:
        self.store = store
        self.policy = policy
        self.sampler = sampler
        self.clock = clock

    def __call__(self, mission_id: str, configured_limit: int) -> int:
        points = tuple(self.sampler(mission_id))
        decision = govern_dispatch(
            configured_limit=configured_limit,
            policy=self.policy,
            points=points,
        )
        recorded_at = max(
            (point.observed_at for point in points), default=self.clock.now()
        )
        threshold = (
            self.policy.hard_managed_rss_bytes
            if decision.action == "paused"
            else self.policy.soft_managed_rss_bytes
        )
        values = {
            "mission_id": mission_id,
            "subject": mission_id,
            "source": "resource-governor",
            "platform": sys.platform,
            "scope": "isolated-process-tree",
            "semantics": "sampled-current-rss",
            "units": "bytes",
            "observed_from": min(
                (point.observed_at for point in points), default=recorded_at
            ),
            "observed_until": recorded_at,
            "value": (
                None
                if decision.pressure_quality == "unavailable"
                else decision.managed_rss_bytes
            ),
            "attribution_quality": decision.pressure_quality,
            "threshold": threshold,
            "action": {
                "paused": "pause-new-dispatch",
                "reduced": "reduce-new-dispatch",
                "unchanged": "allow-new-dispatch",
            }[decision.action],
        }
        digest = canonical_json_sha256(
            {
                **values,
                "observed_from": values["observed_from"].isoformat(),
                "observed_until": values["observed_until"].isoformat(),
            }
        )
        receipt = ResourceReceipt(
            receipt_id=f"resource_{digest[:24]}",
            **values,
        )
        self.store.record_resource_summary(
            receipt,
            f"resource_control_{digest[:32]}",
            recorded_at=recorded_at,
        )
        return decision.dispatch_limit


__all__ = ["ResourceDispatchController", "ResourceSummaryStore"]
