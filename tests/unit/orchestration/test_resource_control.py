from __future__ import annotations

from graphene.orchestration.mission_models import MissionEventType
from graphene.orchestration.resource_control import ResourceDispatchController
from graphene.orchestration.resources import DispatchGovernorPolicy, ResourcePoint
from graphene.orchestration.scheduler import MissionScheduler
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore

from .test_scheduler import FakeClock
from .test_store import NOW, _create


def _rss(value: float) -> ResourcePoint:
    return ResourcePoint(
        subject="managed-worker",
        metric="current-rss-bytes",
        units="bytes",
        category="managed_runtime",
        scope="isolated_process_tree",
        attribution_quality="sampled_partial",
        observed_at=NOW,
        value=value,
        semantics="sampled-current-rss",
    )


def test_sampled_pressure_commits_event_and_pauses_then_resumes_dispatch(
    tmp_path,
) -> None:
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(store)
    samples = [[_rss(250)]]
    clock = FakeClock(NOW)
    control = ResourceDispatchController(
        store,
        DispatchGovernorPolicy(
            soft_managed_rss_bytes=100,
            hard_managed_rss_bytes=200,
        ),
        lambda _mission_id: samples[0],
        clock,
    )
    scheduler = MissionScheduler(
        store,
        clock=clock,
        lease_ttl_seconds=30,
        dispatch_limiter=control,
    )

    assert scheduler.tick("mission-1", ("worker-a", "worker-b")) == ()
    pressure = store.tail("mission-1", 0, 100)[-1]
    assert pressure.event_type == MissionEventType.RESOURCE_BUDGET_CROSSED
    assert pressure.payload["action"] == "pause-new-dispatch"

    samples[0] = [_rss(50)]
    dispatches = scheduler.tick("mission-1", ("worker-a", "worker-b"))
    healthy = next(
        event
        for event in store.tail("mission-1", pressure.seq, 100)
        if event.event_type == MissionEventType.RESOURCE_SUMMARY_RECORDED
    )

    assert len(dispatches) == 2
    assert healthy.event_type == MissionEventType.RESOURCE_SUMMARY_RECORDED
    assert healthy.payload["action"] == "allow-new-dispatch"
