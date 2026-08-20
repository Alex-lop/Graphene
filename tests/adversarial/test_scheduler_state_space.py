from __future__ import annotations

from itertools import permutations

import pytest

from graphene.orchestration.models import AttemptState, MissionEventType
from graphene.orchestration.scheduler import MissionScheduler
from graphene.orchestration.store import SQLiteMissionStore, StaleWorker

from tests.unit.orchestration.test_scheduler import FakeClock
from tests.unit.orchestration.test_store import (
    NOW,
    _artifacts,
    _create,
    _success,
    _task_for_snapshot,
)


def test_scheduler_store_interleavings_preserve_fences_and_publication_uniqueness(
    tmp_path,
) -> None:
    outcomes = set()

    for order in permutations(("stale", "replacement", "sibling")):
        store = SQLiteMissionStore(tmp_path / ("-".join(order) + ".sqlite"))
        _create(store)
        clock = FakeClock(NOW)
        scheduler = MissionScheduler(
            store, clock=clock, lease_ttl_seconds=5, retry_backoff_seconds=0
        )
        initial = scheduler.tick("mission-1", ("worker-a", "worker-b"))
        stale = next(item for item in initial if item.task_id == "work-a")
        sibling = next(item for item in initial if item.task_id == "work-b")

        clock.advance(4)
        scheduler.heartbeat(sibling)
        clock.advance(2)
        recovered = scheduler.tick(
            "mission-1", ("worker-a", "worker-b", "worker-c")
        )
        replacement = next(
            item
            for item in recovered
            if item.task_id == "work-a" and item.attempt_id != stale.attempt_id
        )
        assert replacement.fencing_token == stale.fencing_token + 1
        recovered_sibling = next(
            item for item in recovered if item.task_id == "work-b"
        )
        assert (
            recovered_sibling.attempt_id,
            recovered_sibling.lease_id,
            recovered_sibling.fencing_token,
        ) == (sibling.attempt_id, sibling.lease_id, sibling.fencing_token)
        sibling = recovered_sibling

        results = {
            "stale": _success(
                stale, _task_for_snapshot(store, "work-a"), _artifacts(store)
            ),
            "replacement": _success(
                replacement, _task_for_snapshot(store, "work-a"), _artifacts(store)
            ),
            "sibling": _success(
                sibling, _task_for_snapshot(store, "work-b"), _artifacts(store)
            ),
        }
        dispatches = {
            "stale": stale,
            "replacement": replacement,
            "sibling": sibling,
        }

        for operation in order:
            if operation == "stale":
                with pytest.raises(StaleWorker):
                    scheduler.complete(dispatches[operation], results[operation])
            else:
                scheduler.complete(dispatches[operation], results[operation])

        snapshot = store.snapshot("mission-1")
        publications = tuple(
            sorted(
                (
                    item.task_id,
                    item.output_name,
                    item.kind,
                    item.attempt_id,
                )
                for item in snapshot.publications
            )
        )
        assert publications == (
            ("work-a", "patch-a", "patch", replacement.attempt_id),
            ("work-b", "patch-b", "patch", sibling.attempt_id),
        )
        assert stale.attempt_id not in {item.attempt_id for item in snapshot.publications}
        assert next(
            item for item in snapshot.attempts if item.attempt_id == stale.attempt_id
        ).state == AttemptState.ABANDONED
        assert [
            event.payload["task_id"]
            for event in store.tail("mission-1", 0, 256)
            if event.event_type == MissionEventType.TASK_COMPLETED
        ] == [
            dispatches[item].task_id for item in order if item != "stale"
        ]
        assert store.verify("mission-1") == store.head("mission-1")
        outcomes.add(tuple(item[:3] for item in publications))

    assert outcomes == {
        (("work-a", "patch-a", "patch"), ("work-b", "patch-b", "patch"))
    }
