from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphene.cli import mission as mission_cli
from graphene.orchestration.mission_models import MissionStatus, TaskKind
from graphene.orchestration.overlap import (
    OVERLAP_NOTE,
    PROVIDER_CALL_BASIS,
    OverlapMeasurement,
    measure_overlap,
)
from graphene.orchestration.worker_runtime import WorkerProviderReceipt, WorkerRuntime
from graphene.orchestration.workers import DeterministicWorkerModel
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


def _receipt(call_started_at: str, call_ended_at: str) -> WorkerProviderReceipt:
    return WorkerProviderReceipt(
        driver="adk_fake",
        client_version="test",
        requested_model="stub-model",
        returned_model="stub-model",
        credential_mode="not_applicable",
        input_bytes=12,
        output_bytes=34,
        latency_ms=5,
        call_started_at=call_started_at,
        call_ended_at=call_ended_at,
        usage_source="unavailable",
    )


def _bases(overlap: dict) -> list[tuple[str, int]]:
    return [(pair["basis"], pair["window_ms"]) for pair in overlap["pairs"]]


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
    # No receipts were offered, so no provider-call basis exists to report.
    assert measurement.provider_call_observed is False
    assert measurement.provider_call_max_window_ms == 0
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
    assert "proves simultaneous leases, not concurrent execution" in measurement.note
    assert "provider call windows stamped by the runtime" in measurement.note
    assert (
        OverlapMeasurement.model_validate(measurement.model_dump(mode="json"))
        == measurement
    )


def test_measure_overlap_reports_provider_call_basis_from_receipts() -> None:
    snapshot = _snapshot(
        attempts=(
            _attempt("attempt-a", "work-a", "worker-a", 0, 3),
            _attempt("attempt-b", "work-b", "worker-b", 1, 5),
        )
    )
    receipt_a = _receipt("2026-08-22T12:00:00.250Z", "2026-08-22T12:00:02.000Z")

    overlapping = measure_overlap(
        snapshot,
        provider_receipts={
            "attempt-a": receipt_a,
            "attempt-b": _receipt(
                "2026-08-22T12:00:01.500Z", "2026-08-22T12:00:04.750Z"
            ),
        },
    )

    assert overlapping.observed is True
    assert overlapping.max_window_ms == 2000
    assert overlapping.provider_call_observed is True
    assert overlapping.provider_call_max_window_ms == 500
    assert [(pair.basis, pair.window_ms) for pair in overlapping.pairs] == [
        ("attempt_timestamps", 2000),
        (PROVIDER_CALL_BASIS, 500),
    ]
    provider_pair = overlapping.pairs[-1]
    assert (provider_pair.first_attempt_id, provider_pair.second_attempt_id) == (
        "attempt-a",
        "attempt-b",
    )
    assert (provider_pair.first_worker_id, provider_pair.second_worker_id) == (
        "worker-a",
        "worker-b",
    )
    assert (
        OverlapMeasurement.model_validate(overlapping.model_dump(mode="json"))
        == overlapping
    )

    # Disjoint call windows inside overlapping lifetimes: the leases were held
    # at the same time, the provider calls were not. Only the lifetime basis
    # reports overlap; the provider-call basis honestly reports none.
    disjoint = measure_overlap(
        snapshot,
        provider_receipts={
            "attempt-a": receipt_a,
            "attempt-b": _receipt(
                "2026-08-22T12:00:02.000Z", "2026-08-22T12:00:04.750Z"
            ),
        },
    )

    assert disjoint.observed is True
    assert disjoint.max_window_ms == 2000
    assert disjoint.provider_call_observed is False
    assert disjoint.provider_call_max_window_ms == 0
    assert [(pair.basis, pair.window_ms) for pair in disjoint.pairs] == [
        ("attempt_timestamps", 2000),
        (PROVIDER_CALL_BASIS, 0),
    ]

    # A pair with a receipt on one side only gets no provider-call pair at all:
    # a missing receipt is never treated as a zero-width call window.
    partial = measure_overlap(snapshot, provider_receipts={"attempt-a": receipt_a})

    assert [pair.basis for pair in partial.pairs] == ["attempt_timestamps"]
    assert partial.provider_call_observed is False
    assert partial.provider_call_max_window_ms == 0


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
        provider_call_observed=False,
        provider_call_max_window_ms=0,
        pairs=(),
        attempt_count=0,
        note=OVERLAP_NOTE,
    )


def _evidence_receipts(prepared: SimpleNamespace) -> dict[str, WorkerProviderReceipt]:
    snapshot = prepared.store.snapshot(prepared.mission_id)
    evidence = mission_cli._mission_evidence(prepared.store, prepared.mission_id)
    *_, unknowns, receipts = mission_cli._replayed_provider_receipts(snapshot, evidence)
    assert unknowns == []
    return receipts


def test_fake_two_worker_mission_records_measured_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    # Gate each fake model call on the other worker's arrival, so both provider
    # calls are provably in flight at once; the short sleep keeps the measured
    # window above the receipt's millisecond resolution.
    arrived_a, arrived_b = asyncio.Event(), asyncio.Event()
    prepared.model_a.bind(
        prepared.model_a.mutations, arrived=arrived_a, release=arrived_b
    )
    prepared.model_b.bind(
        prepared.model_b.mutations, arrived=arrived_b, release=arrived_a
    )
    generate = DeterministicWorkerModel.generate_content_async

    async def delayed_generate(self, llm_request, stream=False):
        await asyncio.sleep(0.02)
        async for response in generate(self, llm_request, stream):
            yield response

    monkeypatch.setattr(
        DeterministicWorkerModel, "generate_content_async", delayed_generate
    )

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
    assert result["provider_call_overlap_observed"] is True
    overlap = result["parallel_overlap"]
    assert overlap["max_window_ms"] > 0
    assert overlap["provider_call_observed"] is True
    assert overlap["provider_call_max_window_ms"] > 0
    assert overlap["attempt_count"] == 2
    assert [basis for basis, _window in _bases(overlap)] == [
        "attempt_timestamps",
        "lease_timestamps",
        PROVIDER_CALL_BASIS,
    ]
    assert all(window > 0 for _basis, window in _bases(overlap))
    assert {pair["first_worker_id"] for pair in overlap["pairs"]} == {"fake-a"}
    assert {pair["second_worker_id"] for pair in overlap["pairs"]} == {"fake-b"}
    assert overlap["note"] == OVERLAP_NOTE
    # The provider-call pair is rebuilt from evidence-resolved receipts only:
    # the same snapshot without receipts carries no provider-call basis.
    receipts = _evidence_receipts(prepared)
    provider_pair = overlap["pairs"][-1]
    assert set(receipts) == {
        provider_pair["first_attempt_id"],
        provider_pair["second_attempt_id"],
    }
    for receipt in receipts.values():
        assert receipt.call_started_at <= receipt.call_ended_at
    snapshot = prepared.store.snapshot(prepared.mission_id)
    measurement = measure_overlap(snapshot, provider_receipts=receipts)
    assert measurement.model_dump(mode="json") == overlap
    bare = measure_overlap(snapshot)
    assert bare.observed is True
    assert bare.provider_call_observed is False
    assert bare.provider_call_max_window_ms == 0
    assert [pair.basis for pair in bare.pairs] == [
        "attempt_timestamps",
        "lease_timestamps",
    ]


def test_serialized_fake_workers_overlap_in_lifetime_but_not_in_provider_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The honesty gate: simultaneous leases must not pass as concurrent calls."""

    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    execute_async = WorkerRuntime.execute_async
    state: dict[str, asyncio.Lock] = {}

    async def serialized(self, dispatch):
        lock = state.setdefault("lock", asyncio.Lock())
        async with lock:
            run = await execute_async(self, dispatch)
            await asyncio.sleep(0.05)
            return run

    monkeypatch.setattr(WorkerRuntime, "execute_async", serialized)

    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
        resource_sampler=quiet_resource_sampler,
    )

    assert result["status"] == MissionStatus.AWAITING_RESULT
    assert result["dispatch_batches"][0] == ["report-a", "report-b"]
    overlap = result["parallel_overlap"]
    # Both attempts were claimed in one batch, so their lifetimes overlap on
    # the store clock and the lease basis agrees with the attempt basis...
    assert result["parallel_overlap_observed"] is True
    assert overlap["observed"] is True
    assert overlap["max_window_ms"] > 0
    # ...but the runtime executed them strictly one after another, and the
    # receipts' call windows say so.
    assert result["provider_call_overlap_observed"] is False
    assert overlap["provider_call_observed"] is False
    assert overlap["provider_call_max_window_ms"] == 0
    assert _bases(overlap)[:2] == [
        ("attempt_timestamps", overlap["max_window_ms"]),
        ("lease_timestamps", overlap["max_window_ms"]),
    ]
    assert _bases(overlap)[2:] == [(PROVIDER_CALL_BASIS, 0)]
    first, second = sorted(
        _evidence_receipts(prepared).values(), key=lambda item: item.call_started_at
    )
    assert first.call_ended_at <= second.call_started_at
