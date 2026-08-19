from __future__ import annotations

import signal
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from graphene.hashing import canonical_json_bytes
from graphene.orchestration.resources import (
    BoundedResourceWindow,
    DispatchGovernorPolicy,
    OwnedProcess,
    ProcessIdentity,
    ProcessIdentityError,
    ResourcePoint,
    estimate_context_footprint,
    govern_dispatch,
    process_tree_rss_point,
    read_process_identity,
    sample_owned_process_tree,
    terminate_owned_process_group,
    unavailable_remote_metric,
)


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _point(
    value: float | None,
    offset: int,
    *,
    quality: str = "sampled_partial",
) -> ResourcePoint:
    return ResourcePoint(
        subject="attempt-1",
        metric="current-rss-bytes",
        units="bytes",
        category="managed_runtime",
        scope="isolated_process_tree",
        attribution_quality=quality,
        observed_at=NOW + timedelta(seconds=offset),
        value=value,
        semantics="sampled-current-rss",
    )


def test_resource_window_is_bounded_and_summarizes_only_retained_samples() -> None:
    window = BoundedResourceWindow(max_samples=2)
    window.append(_point(10, 0))
    window.append(_point(20, 1))
    window.append(_point(None, 2, quality="unavailable"))

    summary = window.summary()

    assert len(window) == 2
    assert summary.observed_from == NOW + timedelta(seconds=1)
    assert summary.observed_until == NOW + timedelta(seconds=2)
    assert summary.latest_value is None
    assert summary.maximum_sampled_value == 20
    assert summary.attribution_quality == "sampled_partial"
    assert summary.unavailable_samples == 1
    assert summary.dropped_samples == 1


def test_resource_window_rejects_mixed_series_and_attribution() -> None:
    window = BoundedResourceWindow(max_samples=2)
    window.append(_point(10, 0))
    with pytest.raises(ValueError, match="attribution"):
        window.append(_point(20, 1, quality="measured_bound"))
    with pytest.raises(ValueError, match="one metric series"):
        window.append(_point(20, 1).model_copy(update={"metric": "cpu-seconds"}))


def test_context_is_bytes_plus_labeled_estimate_not_per_skill_cpu_or_ram() -> None:
    tool = {"name": "read_file", "schema": {"path": "string"}}
    footprint = estimate_context_footprint(
        instructions="plan λ",
        skill_instructions={"one": "bounded skill", "two": "second"},
        tool_schemas=(tool,),
        invocation_count=2,
    )

    expected = (
        len("plan λ".encode())
        + len("bounded skill".encode())
        + len("second".encode())
        + len(canonical_json_bytes(tool))
    )
    assert footprint.total_bytes == expected
    assert footprint.estimated_tokens == (expected + 3) // 4
    assert footprint.byte_quality == "measured_bound"
    assert footprint.token_quality == "estimated"
    assert footprint.skill_cpu_ram_attribution == "unavailable"
    assert not hasattr(footprint, "skill_cpu_seconds")
    assert not hasattr(footprint, "skill_ram_bytes")


def test_remote_cpu_or_ram_is_unavailable_without_provider_receipt() -> None:
    point = unavailable_remote_metric(
        subject="remote-mcp",
        metric="cpu-seconds",
        units="seconds",
        observed_at=NOW,
    )

    assert point.scope == "remote_request"
    assert point.category == "provider_telemetry"
    assert point.attribution_quality == "unavailable"
    assert point.value is None


def test_managed_pressure_reduces_then_pauses_new_dispatch() -> None:
    policy = DispatchGovernorPolicy(
        soft_managed_rss_bytes=100,
        hard_managed_rss_bytes=200,
    )
    points = (
        _point(40, 0).model_copy(update={"subject": "attempt-1"}),
        _point(60, 1).model_copy(update={"subject": "attempt-1"}),
        _point(50, 1).model_copy(
            update={
                "subject": "attempt-2",
                "attribution_quality": "measured_bound",
            }
        ),
    )

    reduced = govern_dispatch(configured_limit=4, policy=policy, points=points)
    paused = govern_dispatch(
        configured_limit=4,
        policy=policy,
        points=(*points, _point(100, 1).model_copy(update={"subject": "attempt-3"})),
    )

    assert reduced.managed_rss_bytes == 110
    assert reduced.managed_subjects == 2
    assert reduced.pressure_quality == "sampled_partial"
    assert reduced.dispatch_limit == 2
    assert reduced.action == "reduced"
    assert reduced.effect == "dispatch_only"
    assert paused.managed_rss_bytes == 210
    assert paused.dispatch_limit == 0
    assert paused.action == "paused"


def test_shared_remote_cloud_and_unavailable_pressure_is_advisory_only() -> None:
    huge = _point(10_000, 0)
    points = (
        huge.model_copy(
            update={
                "subject": "shared-mcp",
                "scope": "shared_process",
                "attribution_quality": "aggregate_only",
            }
        ),
        huge.model_copy(
            update={
                "subject": "cloud-service",
                "scope": "cloud_container",
                "attribution_quality": "aggregate_only",
            }
        ),
        unavailable_remote_metric(
            subject="remote-mcp",
            metric="current-rss-bytes",
            units="bytes",
            observed_at=NOW,
        ),
        _point(None, 1, quality="unavailable"),
    )

    decision = govern_dispatch(
        configured_limit=4,
        policy=DispatchGovernorPolicy(
            soft_managed_rss_bytes=100,
            hard_managed_rss_bytes=200,
        ),
        points=points,
    )

    assert decision.dispatch_limit == 4
    assert decision.action == "unchanged"
    assert decision.managed_rss_bytes == 0
    assert decision.managed_subjects == 0
    assert decision.pressure_quality == "unavailable"
    assert decision.advisory_points == 4


def test_newer_unavailable_sample_does_not_reuse_stale_pressure() -> None:
    decision = govern_dispatch(
        configured_limit=4,
        policy=DispatchGovernorPolicy(
            soft_managed_rss_bytes=100,
            hard_managed_rss_bytes=200,
        ),
        points=(
            _point(150, 0),
            _point(None, 1, quality="unavailable"),
        ),
    )

    assert decision.dispatch_limit == 4
    assert decision.pressure_quality == "unavailable"
    assert decision.managed_subjects == 0
    assert decision.advisory_points == 1


def _write_stat(
    root: Path,
    *,
    pid: int,
    parent: int,
    user_ticks: int,
    system_ticks: int,
    start_ticks: int,
    rss_pages: int,
) -> None:
    fields = ["S", str(parent), *("0" for _ in range(20))]
    fields[11] = str(user_ticks)
    fields[12] = str(system_ticks)
    fields[19] = str(start_ticks)
    fields[21] = str(rss_pages)
    target = root / str(pid)
    target.mkdir()
    (target / "stat").write_text(f"{pid} (worker {pid}) {' '.join(fields)}\n")


def _fake_proc(root: Path) -> ProcessIdentity:
    boot = root / "sys/kernel/random"
    boot.mkdir(parents=True)
    (boot / "boot_id").write_text("boot-id")
    _write_stat(
        root,
        pid=100,
        parent=1,
        user_ticks=10,
        system_ticks=5,
        start_ticks=700,
        rss_pages=3,
    )
    _write_stat(
        root,
        pid=101,
        parent=100,
        user_ticks=20,
        system_ticks=5,
        start_ticks=701,
        rss_pages=2,
    )
    _write_stat(
        root,
        pid=102,
        parent=101,
        user_ticks=10,
        system_ticks=0,
        start_ticks=702,
        rss_pages=1,
    )
    _write_stat(
        root,
        pid=200,
        parent=1,
        user_ticks=999,
        system_ticks=999,
        start_ticks=800,
        rss_pages=999,
    )
    identity = read_process_identity(100, proc_root=root)
    assert identity is not None
    return identity


def test_linux_proc_tree_sample_is_partial_and_peak_is_unavailable(tmp_path: Path) -> None:
    identity = _fake_proc(tmp_path)
    owned = OwnedProcess(
        owner_id="attempt-1",
        identity=identity,
        process_group_id=100,
        started_monotonic_ns=1_000_000_000,
    )

    sample = sample_owned_process_tree(
        owned,
        proc_root=tmp_path,
        observed_at=NOW,
        monotonic_ns=lambda: 3_000_000_000,
        clock_ticks=100,
        page_size=4096,
    )

    assert sample.attribution_quality == "sampled_partial"
    assert sample.wall_seconds == 2
    assert sample.cpu_seconds == 0.5
    assert sample.current_rss_bytes == 6 * 4096
    assert sample.subprocess_count == 2
    assert sample.current_rss_semantics == "non_atomic_sum_of_current_process_rss"
    assert sample.peak_rss_bytes is None
    assert sample.peak_rss_quality == "unavailable"
    point = process_tree_rss_point(sample)
    assert point.value == 6 * 4096
    assert point.attribution_quality == "sampled_partial"


def test_process_sampler_degrades_to_unavailable_without_procfs(tmp_path: Path) -> None:
    identity = ProcessIdentity(pid=100, boot_id="boot-id", start_time_ticks=700)
    sample = sample_owned_process_tree(
        OwnedProcess(
            owner_id="attempt-1",
            identity=identity,
            process_group_id=100,
            started_monotonic_ns=0,
        ),
        proc_root=tmp_path / "missing",
        observed_at=NOW,
    )

    assert sample.attribution_quality == "unavailable"
    assert sample.cpu_seconds is None
    assert sample.current_rss_bytes is None


def test_pid_reuse_or_owner_mismatch_prevents_any_signal() -> None:
    expected = ProcessIdentity(pid=100, boot_id="boot-id", start_time_ticks=700)
    replacement = expected.model_copy(update={"start_time_ticks": 701})
    owned = OwnedProcess(
        owner_id="attempt-1",
        identity=expected,
        process_group_id=100,
        started_monotonic_ns=0,
    )
    signals: list[tuple[int, int]] = []
    identities = iter((expected, replacement))

    with pytest.raises(ProcessIdentityError, match="before signal"):
        terminate_owned_process_group(
            owned,
            owner_id="attempt-1",
            identity_reader=lambda _pid: next(identities),
            process_group_reader=lambda _pid: 100,
            group_signaler=lambda group, sig: signals.append((group, sig)),
        )
    with pytest.raises(ProcessIdentityError, match="owner"):
        terminate_owned_process_group(
            owned,
            owner_id="someone-else",
            identity_reader=lambda _pid: expected,
            process_group_reader=lambda _pid: 100,
            group_signaler=lambda group, sig: signals.append((group, sig)),
        )
    assert signals == []


def test_owned_group_is_signaled_only_after_both_identity_checks() -> None:
    identity = ProcessIdentity(pid=100, boot_id="boot-id", start_time_ticks=700)
    owned = OwnedProcess(
        owner_id="attempt-1",
        identity=identity,
        process_group_id=100,
        started_monotonic_ns=0,
    )
    checks: list[int] = []
    signals: list[tuple[int, int]] = []

    terminate_owned_process_group(
        owned,
        owner_id="attempt-1",
        identity_reader=lambda pid: checks.append(pid) or identity,
        process_group_reader=lambda _pid: 100,
        group_signaler=lambda group, sig: signals.append((group, sig)),
    )

    assert checks == [100, 100]
    assert signals == [(100, signal.SIGTERM)]
