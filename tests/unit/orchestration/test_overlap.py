from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphene.cli import mission as mission_cli
from graphene.orchestration.models import MissionStatus, TaskKind
from graphene.orchestration.overlap import (
    OVERLAP_NOTE,
    OverlapMeasurement,
    measure_overlap,
)
from tests.unit.orchestration.test_gemini_mission_runtime import (
    prepare_fake_two_worker_mission,
    quiet_resource_sampler,
)

T0 = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _attempt(
    attempt_id: str,
    task_id: str,
    worker_id: str,
    started: float,
    ended: float | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        attempt_id=attempt_id,
        task_id=task_id,
        worker_id=worker_id,
        started_at=_at(started),
        ended_at=None if ended is None else _at(ended),
    )


def _lease(
    attempt_id: str, issued: float, heartbeat: float, released: float | None
) -> SimpleNamespace:
    return SimpleNamespace(
        attempt_id=attempt_id,
        issued_at=_at(issued),
        heartbeat_at=_at(heartbeat),
        released_at=None if released is None else _at(released),
    )


def _snapshot(attempts, leases=()) -> SimpleNamespace:
    tasks = (
        SimpleNamespace(task_id="work-a", kind=TaskKind.WORK),
        SimpleNamespace(task_id="work-b", kind=TaskKind.WORK),
        SimpleNamespace(task_id="assemble", kind=TaskKind.ASSEMBLY),
    )
    return SimpleNamespace(
        plan=SimpleNamespace(tasks=tasks),
        tasks=tasks,
        attempts=tuple(attempts),
        leases=tuple(leases),
    )


def test_measure_overlap_reports_attempt_and_lease_bases_from_durable_clocks() -> None:
    snapshot = _snapshot(
        attempts=(
            _attempt("attempt-a", "work-a", "worker-a", 0, 3),
            _attempt("attempt-b", "work-b", "worker-b", 1, 5),
        ),
        leases=(
            _lease("attempt-a", 0, 2.5, 3),
            # Never released: the last heartbeat is the only durable end mark.
            _lease("attempt-b", 1, 2, None),
        ),
    )

    measurement = measure_overlap(snapshot)

    assert measurement.observed is True
    assert measurement.attempt_count == 2
    assert measurement.max_window_ms == 2000
    assert [(pair.basis, pair.window_ms) for pair in measurement.pairs] == [
        ("attempt_timestamps", 2000),
        ("lease_timestamps", 1000),
    ]
    for pair in measurement.pairs:
        assert (pair.first_attempt_id, pair.second_attempt_id) == (
            "attempt-a",
            "attempt-b",
        )
        assert (pair.first_worker_id, pair.second_worker_id) == (
            "worker-a",
            "worker-b",
        )
    assert measurement.note == OVERLAP_NOTE
    assert "not a provider-side measurement" in measurement.note
    assert (
        OverlapMeasurement.model_validate(measurement.model_dump(mode="json"))
        == measurement
    )


def test_measure_overlap_excludes_same_worker_open_and_other_kind_attempts() -> None:
    snapshot = _snapshot(
        attempts=(
            _attempt("attempt-a", "work-a", "worker-a", 0, 2),
            _attempt("attempt-a2", "work-a", "worker-a", 1, 3),
            _attempt("attempt-b", "work-b", "worker-b", 3, 4),
            _attempt("attempt-open", "work-b", "worker-c", 0, None),
            _attempt("attempt-assembly", "assemble", "worker-b", 0, 9),
        )
    )

    measurement = measure_overlap(snapshot)

    assert measurement.observed is False
    assert measurement.max_window_ms == 0
    assert measurement.attempt_count == 3
    assert [
        (pair.first_attempt_id, pair.second_attempt_id, pair.basis, pair.window_ms)
        for pair in measurement.pairs
    ] == [
        ("attempt-a", "attempt-b", "attempt_timestamps", 0),
        ("attempt-a2", "attempt-b", "attempt_timestamps", 0),
    ]
    assert measure_overlap(snapshot, task_kind=TaskKind.ASSEMBLY).attempt_count == 1
    assert measure_overlap(_snapshot(attempts=())) == OverlapMeasurement(
        observed=False,
        max_window_ms=0,
        pairs=(),
        attempt_count=0,
        note=OVERLAP_NOTE,
    )


def test_fake_two_worker_mission_records_measured_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)

    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
        resource_sampler=quiet_resource_sampler,
    )

    assert result["status"] == MissionStatus.AWAITING_RESULT
    assert result["dispatch_batches"][0] == ["report-a", "report-b"]
    assert result["parallel_overlap_observed"] is True
    overlap = result["parallel_overlap"]
    assert overlap["max_window_ms"] > 0
    assert overlap["attempt_count"] == 2
    assert {pair["basis"] for pair in overlap["pairs"]} == {
        "attempt_timestamps",
        "lease_timestamps",
    }
    assert all(pair["window_ms"] > 0 for pair in overlap["pairs"])
    assert {pair["first_worker_id"] for pair in overlap["pairs"]} == {"fake-a"}
    assert {pair["second_worker_id"] for pair in overlap["pairs"]} == {"fake-b"}
    assert overlap["note"] == OVERLAP_NOTE
    measurement = measure_overlap(prepared.store.snapshot(prepared.mission_id))
    assert measurement.model_dump(mode="json") == overlap
