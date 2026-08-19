from __future__ import annotations

import math
import os
import re
import signal
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..hashing import canonical_json_bytes
from ..models import FrozenModel, Identifier, UtcDateTime

AttributionQuality = Literal[
    "measured_bound",
    "sampled_partial",
    "aggregate_only",
    "estimated",
    "unavailable",
]
MeasurementScope = Literal[
    "isolated_process_tree",
    "shared_process",
    "remote_request",
    "cloud_container",
    "context_payload",
]
MeasurementCategory = Literal[
    "managed_runtime",
    "context_footprint",
    "provider_telemetry",
]

_OWNER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_CURRENT_RSS_SEMANTICS = "non_atomic_sum_of_current_process_rss"


class ResourceError(RuntimeError):
    pass


class ProcessIdentityError(ResourceError):
    pass


class ResourcePoint(FrozenModel):
    subject: Identifier
    metric: Identifier
    units: Identifier
    category: MeasurementCategory
    scope: MeasurementScope
    attribution_quality: AttributionQuality
    observed_at: UtcDateTime
    value: float | None = Field(default=None, ge=0)
    semantics: Identifier

    @model_validator(mode="after")
    def value_matches_quality(self) -> ResourcePoint:
        if (self.value is None) != (self.attribution_quality == "unavailable"):
            raise ValueError("only unavailable resource points omit a value")
        return self


class ResourceSummary(FrozenModel):
    subject: Identifier
    metric: Identifier
    units: Identifier
    category: MeasurementCategory
    scope: MeasurementScope
    attribution_quality: AttributionQuality
    observed_from: UtcDateTime
    observed_until: UtcDateTime
    latest_value: float | None = Field(default=None, ge=0)
    maximum_sampled_value: float | None = Field(default=None, ge=0)
    retained_samples: int = Field(ge=1)
    unavailable_samples: int = Field(ge=0)
    dropped_samples: int = Field(ge=0)
    semantics: Identifier


class DispatchGovernorPolicy(FrozenModel):
    soft_managed_rss_bytes: int = Field(gt=0)
    hard_managed_rss_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> DispatchGovernorPolicy:
        if self.soft_managed_rss_bytes >= self.hard_managed_rss_bytes:
            raise ValueError("soft managed-memory threshold must be below hard threshold")
        return self


class DispatchGovernorDecision(FrozenModel):
    configured_limit: int = Field(gt=0)
    dispatch_limit: int = Field(ge=0)
    action: Literal["unchanged", "reduced", "paused"]
    managed_rss_bytes: float = Field(ge=0)
    pressure_quality: Literal["measured_bound", "sampled_partial", "unavailable"]
    managed_subjects: int = Field(ge=0)
    advisory_points: int = Field(ge=0)
    effect: Literal["dispatch_only"] = "dispatch_only"

    @model_validator(mode="after")
    def action_matches_limit(self) -> DispatchGovernorDecision:
        expected = (
            "paused"
            if self.dispatch_limit == 0
            else "unchanged"
            if self.dispatch_limit == self.configured_limit
            else "reduced"
        )
        if self.dispatch_limit > self.configured_limit or self.action != expected:
            raise ValueError("dispatch governor action is inconsistent")
        if (self.managed_subjects == 0) != (self.pressure_quality == "unavailable"):
            raise ValueError("dispatch governor pressure quality is inconsistent")
        return self


def govern_dispatch(
    *,
    configured_limit: int,
    policy: DispatchGovernorPolicy,
    points: Sequence[ResourcePoint],
) -> DispatchGovernorDecision:
    """Throttle only from isolated managed RSS; all other telemetry is advisory."""

    if configured_limit <= 0:
        raise ValueError("configured dispatch limit must be positive")
    latest_local: dict[str, ResourcePoint] = {}
    advisory = 0
    for point in points:
        local_rss = (
            point.category == "managed_runtime"
            and point.scope == "isolated_process_tree"
            and point.metric == "current-rss-bytes"
            and point.units == "bytes"
        )
        if not local_rss:
            advisory += 1
            continue
        previous = latest_local.get(point.subject)
        if previous is None or point.observed_at >= previous.observed_at:
            latest_local[point.subject] = point

    latest: dict[str, ResourcePoint] = {}
    for subject, point in latest_local.items():
        if point.value is not None and point.attribution_quality in {
            "measured_bound",
            "sampled_partial",
        }:
            latest[subject] = point
        else:
            advisory += 1

    total = sum(point.value or 0 for point in latest.values())
    if total >= policy.hard_managed_rss_bytes:
        dispatch_limit = 0
    elif total >= policy.soft_managed_rss_bytes:
        dispatch_limit = max(1, configured_limit // 2)
    else:
        dispatch_limit = configured_limit
    quality: Literal["measured_bound", "sampled_partial", "unavailable"]
    if not latest:
        quality = "unavailable"
    elif any(
        point.attribution_quality == "sampled_partial" for point in latest.values()
    ):
        quality = "sampled_partial"
    else:
        quality = "measured_bound"
    action: Literal["unchanged", "reduced", "paused"] = (
        "paused"
        if dispatch_limit == 0
        else "unchanged"
        if dispatch_limit == configured_limit
        else "reduced"
    )
    return DispatchGovernorDecision(
        configured_limit=configured_limit,
        dispatch_limit=dispatch_limit,
        action=action,
        managed_rss_bytes=total,
        pressure_quality=quality,
        managed_subjects=len(latest),
        advisory_points=advisory,
    )


class BoundedResourceWindow:
    """Bound one metric series in memory and emit one durable-sized summary."""

    def __init__(self, max_samples: int = 120) -> None:
        if not 1 <= max_samples <= 10_000:
            raise ValueError("resource window size is outside the supported bounds")
        self._points: deque[ResourcePoint] = deque(maxlen=max_samples)
        self._dropped = 0

    def append(self, point: ResourcePoint) -> None:
        if self._points:
            first = self._points[0]
            series = (
                point.subject,
                point.metric,
                point.units,
                point.category,
                point.scope,
                point.semantics,
            )
            expected = (
                first.subject,
                first.metric,
                first.units,
                first.category,
                first.scope,
                first.semantics,
            )
            if series != expected:
                raise ValueError("resource window accepts exactly one metric series")
            available = {
                item.attribution_quality
                for item in (*self._points, point)
                if item.attribution_quality != "unavailable"
            }
            if len(available) > 1:
                raise ValueError("resource series cannot mix attribution qualities")
            if point.observed_at < self._points[-1].observed_at:
                raise ValueError("resource observations must be monotonic")
        if len(self._points) == self._points.maxlen:
            self._dropped += 1
        self._points.append(point)

    def __len__(self) -> int:
        return len(self._points)

    def summary(self) -> ResourceSummary:
        if not self._points:
            raise ValueError("cannot summarize an empty resource window")
        first, last = self._points[0], self._points[-1]
        values = [item.value for item in self._points if item.value is not None]
        qualities = {
            item.attribution_quality
            for item in self._points
            if item.attribution_quality != "unavailable"
        }
        quality: AttributionQuality = next(iter(qualities)) if qualities else "unavailable"
        return ResourceSummary(
            subject=first.subject,
            metric=first.metric,
            units=first.units,
            category=first.category,
            scope=first.scope,
            attribution_quality=quality,
            observed_from=first.observed_at,
            observed_until=last.observed_at,
            latest_value=last.value,
            maximum_sampled_value=max(values) if values else None,
            retained_samples=len(self._points),
            unavailable_samples=sum(item.value is None for item in self._points),
            dropped_samples=self._dropped,
            semantics=first.semantics,
        )


class ContextFootprint(FrozenModel):
    instruction_bytes: int = Field(ge=0)
    skill_instruction_bytes: int = Field(ge=0)
    tool_schema_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    invocation_count: int = Field(ge=1)
    byte_quality: Literal["measured_bound"] = "measured_bound"
    token_quality: Literal["estimated"] = "estimated"
    token_estimation: Literal["ceil_utf8_bytes_divided_by_4"] = (
        "ceil_utf8_bytes_divided_by_4"
    )
    skill_cpu_ram_attribution: Literal["unavailable"] = "unavailable"

    @model_validator(mode="after")
    def totals_match(self) -> ContextFootprint:
        if self.total_bytes != (
            self.instruction_bytes
            + self.skill_instruction_bytes
            + self.tool_schema_bytes
        ):
            raise ValueError("context byte total is inconsistent")
        if self.estimated_tokens != math.ceil(self.total_bytes / 4):
            raise ValueError("context token estimate is inconsistent")
        return self


def estimate_context_footprint(
    *,
    instructions: str,
    skill_instructions: Mapping[str, str] | None = None,
    tool_schemas: Sequence[Mapping[str, object]] = (),
    invocation_count: int = 1,
) -> ContextFootprint:
    instruction_bytes = len(instructions.encode("utf-8"))
    skill_bytes = sum(
        len(value.encode("utf-8")) for value in (skill_instructions or {}).values()
    )
    tool_bytes = sum(len(canonical_json_bytes(value)) for value in tool_schemas)
    total = instruction_bytes + skill_bytes + tool_bytes
    return ContextFootprint(
        instruction_bytes=instruction_bytes,
        skill_instruction_bytes=skill_bytes,
        tool_schema_bytes=tool_bytes,
        total_bytes=total,
        estimated_tokens=math.ceil(total / 4),
        invocation_count=invocation_count,
    )


def unavailable_remote_metric(
    *,
    subject: str,
    metric: str,
    units: str,
    observed_at: datetime | None = None,
) -> ResourcePoint:
    return ResourcePoint(
        subject=subject,
        metric=metric,
        units=units,
        category="provider_telemetry",
        scope="remote_request",
        attribution_quality="unavailable",
        observed_at=observed_at or datetime.now(UTC),
        value=None,
        semantics="not_reported_by_remote_provider",
    )


class ProcessIdentity(FrozenModel):
    pid: int = Field(gt=0)
    boot_id: Identifier
    start_time_ticks: int = Field(ge=0)


class OwnedProcess(FrozenModel):
    owner_id: Identifier
    identity: ProcessIdentity
    process_group_id: int = Field(gt=0)
    started_monotonic_ns: int = Field(ge=0)

    @model_validator(mode="after")
    def owns_a_dedicated_process_group(self) -> OwnedProcess:
        if self.process_group_id != self.identity.pid:
            raise ValueError("owned worker must lead its dedicated process group")
        return self


class ProcessTreeSample(FrozenModel):
    subject: Identifier
    scope: Literal["isolated_process_tree"] = "isolated_process_tree"
    attribution_quality: Literal["sampled_partial", "unavailable"]
    observed_at: UtcDateTime
    wall_seconds: float | None = Field(default=None, ge=0)
    cpu_seconds: float | None = Field(default=None, ge=0)
    current_rss_bytes: int | None = Field(default=None, ge=0)
    subprocess_count: int | None = Field(default=None, ge=0)
    current_rss_semantics: Literal[_CURRENT_RSS_SEMANTICS] = _CURRENT_RSS_SEMANTICS
    peak_rss_bytes: None = None
    peak_rss_quality: Literal["unavailable"] = "unavailable"

    @model_validator(mode="after")
    def values_match_quality(self) -> ProcessTreeSample:
        values = (
            self.wall_seconds,
            self.cpu_seconds,
            self.current_rss_bytes,
            self.subprocess_count,
        )
        if self.attribution_quality == "unavailable" and any(
            item is not None for item in values
        ):
            raise ValueError("unavailable process sample cannot contain values")
        if self.attribution_quality == "sampled_partial" and any(
            item is None for item in values
        ):
            raise ValueError("partial process sample requires all sampled values")
        return self


def process_tree_rss_point(sample: ProcessTreeSample) -> ResourcePoint:
    """Project the sampler's RSS field into the dispatch governor series."""

    return ResourcePoint(
        subject=sample.subject,
        metric="current-rss-bytes",
        units="bytes",
        category="managed_runtime",
        scope=sample.scope,
        attribution_quality=sample.attribution_quality,
        observed_at=sample.observed_at,
        value=sample.current_rss_bytes,
        semantics=sample.current_rss_semantics,
    )


def read_process_identity(
    pid: int,
    *,
    proc_root: Path = Path("/proc"),
) -> ProcessIdentity | None:
    """Read Linux process creation identity; unsupported platforms return None."""

    if pid <= 0 or not proc_root.is_dir():
        return None
    stat_fields = _read_proc_stat(proc_root, pid)
    if stat_fields is None:
        return None
    try:
        boot_id = (proc_root / "sys/kernel/random/boot_id").read_text().strip()
        return ProcessIdentity(
            pid=pid,
            boot_id=boot_id,
            start_time_ticks=int(stat_fields[19]),
        )
    except (OSError, ValueError):
        return None


def sample_owned_process_tree(
    process: OwnedProcess,
    *,
    proc_root: Path = Path("/proc"),
    observed_at: datetime | None = None,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    clock_ticks: int | None = None,
    page_size: int | None = None,
) -> ProcessTreeSample:
    """Sample a Linux-owned process tree; this is partial, never a cgroup claim."""

    at = observed_at or datetime.now(UTC)
    current = read_process_identity(process.identity.pid, proc_root=proc_root)
    if current is None:
        return _unavailable_process_sample(process.owner_id, at)
    if current != process.identity:
        raise ProcessIdentityError("owned process identity changed before sampling")

    stats: dict[int, list[str]] = {}
    try:
        entries = tuple(proc_root.iterdir())
    except OSError:
        return _unavailable_process_sample(process.owner_id, at)
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        fields = _read_proc_stat(proc_root, int(entry.name))
        if fields is not None:
            stats[int(entry.name)] = fields

    members = {process.identity.pid}
    changed = True
    while changed:
        changed = False
        for pid, fields in stats.items():
            if pid not in members and int(fields[1]) in members:
                members.add(pid)
                changed = True
    if process.identity.pid not in stats:
        raise ProcessIdentityError("owned process exited during sampling")
    if read_process_identity(process.identity.pid, proc_root=proc_root) != process.identity:
        raise ProcessIdentityError("owned process identity changed during sampling")

    ticks = clock_ticks or int(os.sysconf("SC_CLK_TCK"))
    pages = page_size or int(os.sysconf("SC_PAGE_SIZE"))
    cpu_ticks = sum(int(stats[pid][11]) + int(stats[pid][12]) for pid in members)
    rss_pages = sum(max(0, int(stats[pid][21])) for pid in members)
    return ProcessTreeSample(
        subject=process.owner_id,
        attribution_quality="sampled_partial",
        observed_at=at,
        wall_seconds=max(0, monotonic_ns() - process.started_monotonic_ns) / 1e9,
        cpu_seconds=cpu_ticks / ticks,
        current_rss_bytes=rss_pages * pages,
        subprocess_count=len(members) - 1,
    )


def terminate_owned_process_group(
    process: OwnedProcess,
    *,
    owner_id: str,
    sig: int = signal.SIGTERM,
    identity_reader: Callable[[int], ProcessIdentity | None] = read_process_identity,
    process_group_reader: Callable[[int], int] = os.getpgid,
    group_signaler: Callable[[int, int], None] = os.killpg,
) -> None:
    """Signal only a registered group after two creation-identity checks."""

    if sig not in {signal.SIGTERM, signal.SIGKILL}:
        raise ProcessIdentityError("only termination signals are allowed")
    if not _OWNER_ID.fullmatch(owner_id) or owner_id != process.owner_id:
        raise ProcessIdentityError("process owner identity mismatch")
    if identity_reader(process.identity.pid) != process.identity:
        raise ProcessIdentityError("owned process identity changed before action")
    try:
        group_id = process_group_reader(process.identity.pid)
    except OSError:
        raise ProcessIdentityError("owned process group is unavailable") from None
    if group_id != process.process_group_id:
        raise ProcessIdentityError("owned process group identity mismatch")
    if identity_reader(process.identity.pid) != process.identity:
        raise ProcessIdentityError("owned process identity changed before signal")
    group_signaler(process.process_group_id, sig)


def _unavailable_process_sample(subject: str, at: datetime) -> ProcessTreeSample:
    return ProcessTreeSample(
        subject=subject,
        attribution_quality="unavailable",
        observed_at=at,
    )


def _read_proc_stat(proc_root: Path, pid: int) -> list[str] | None:
    try:
        raw = (proc_root / str(pid) / "stat").read_text()
        _, separator, tail = raw.rpartition(") ")
        fields = tail.split()
        if not separator or len(fields) < 22:
            return None
        int(fields[1])
        int(fields[11])
        int(fields[12])
        int(fields[19])
        int(fields[21])
        return fields
    except (OSError, ValueError):
        return None
