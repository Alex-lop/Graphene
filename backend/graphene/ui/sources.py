"""What the terminal UI reads from, and the text it derives from it.

Two sources, one shape: the verified replay fixture (a tuple of checkpoints,
credential-free, nothing to write) and a live mission read through
`ReadOnlyMissionStore`. Both hand the app a `MissionControlSnapshot`; the
side panes are built from that snapshot and, when a store is attached, from
the causal query over its events. Nothing here is hardcoded to a mission.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from rich.text import Text

from ..orchestration.causal_query import CausalWhyResult, why
from ..orchestration.mission_models import MissionEvent, MissionEventType
from ..orchestration.mission_projection import (
    MissionControlSnapshot,
    MissionNotFound,
    MissionProjection,
    MissionProjectionError,
    MissionTaskDetail,
    task_detail,
)
from ..orchestration.mission_replay import VerifiedMissionReplay
from ..orchestration.sqlite_mission_store import MissionStoreError
from .read_only_store import ReadOnlyAttemptEvidenceStore, ReadOnlyMissionStore

_STAGE_EVENTS = {
    MissionEventType.TASK_CANCELLED,
    MissionEventType.TASK_FAILED,
    MissionEventType.TASK_RETRIED,
}


class UiSource(Protocol):
    label: str

    def snapshot(self) -> MissionControlSnapshot | None: ...
    def stages(self) -> Mapping[str, str]: ...
    def step(self, delta: int) -> bool: ...
    def position(self) -> str: ...
    def lineage(self, task_id: str) -> CausalWhyResult | None: ...
    def notice(self) -> str | None: ...


@dataclass
class ReplaySource:
    """Step through the checkpoints of a verified replay; never touches a store."""

    replay: VerifiedMissionReplay
    index: int = 0
    label: str = field(default="replay")

    def snapshot(self) -> MissionControlSnapshot:
        return self.replay.stages[self.index]

    def stages(self) -> Mapping[str, str]:
        return {}

    def step(self, delta: int) -> bool:
        target = min(max(self.index + delta, 0), len(self.replay.stages) - 1)
        moved = target != self.index
        self.index = target
        return moved

    def position(self) -> str:
        return f"checkpoint {self.index + 1}/{len(self.replay.stages)}"

    def lineage(self, task_id: str) -> None:
        return None

    def notice(self) -> str | None:
        return None


class LiveSource:
    """Follow a mission through a read-only store handle."""

    label = "live"

    def __init__(
        self,
        store: ReadOnlyMissionStore | None,
        mission_id: str,
        *,
        evidence_path: Path | None = None,
        store_path: Path | None = None,
    ) -> None:
        self.store = store
        self.mission_id = mission_id
        self.evidence_path = evidence_path
        self.store_path = store_path
        self.projection = MissionProjection(store) if store is not None else None
        self._last: MissionControlSnapshot | None = None
        self._events: list[MissionEvent] = []
        self._notice: str | None = None

    def _bind_store(self) -> bool:
        """Attach after durable acceptance once the supervisor creates SQLite."""

        if self.store is not None:
            return True
        if self.store_path is None or not self.store_path.is_file():
            self._notice = "mission durably accepted; waiting for the planner to create the store"
            return False
        try:
            self.store = ReadOnlyMissionStore(self.store_path)
        except MissionStoreError:
            self._notice = "mission durably accepted; waiting for the planner to commit the store"
            return False
        self.projection = MissionProjection(self.store)
        return True

    def _bind_evidence(self) -> None:
        """The viewer usually attaches before the first attempt writes evidence."""

        if self.store is None or self.store.artifact_resolver is not None or self.evidence_path is None:
            return
        if self.evidence_path.is_file() and not self.evidence_path.is_symlink():
            self.store.bind_artifact_resolver(ReadOnlyAttemptEvidenceStore(self.evidence_path))

    def snapshot(self) -> MissionControlSnapshot | None:
        if not self._bind_store():
            return self._last
        self._bind_evidence()
        assert self.projection is not None
        try:
            self._last = self.projection.snapshot(self.mission_id)
            self._notice = None
        except MissionNotFound:
            self._notice = "mission durably accepted; waiting for the planner to materialize its graph"
        except MissionProjectionError as error:
            # The projection quarantines a mission it saw inconsistently; a
            # viewer reopens rather than trusting a sticky refusal.
            self._notice = f"projection refused: {error}"
            self.projection = MissionProjection(self.store)
        return self._last

    def _refresh_events(self) -> None:
        if self.store is None:
            return
        while True:
            after = self._events[-1].seq if self._events else 0
            batch = self.store.tail(self.mission_id, after, 256)
            if not batch:
                return
            self._events.extend(batch)
            if len(batch) < 256:
                return

    def stages(self) -> Mapping[str, str]:
        self._refresh_events()
        stages: dict[str, str] = {}
        for event in self._events:
            if event.event_type in _STAGE_EVENTS:
                stage = event.payload.get("stage")
                task_id = event.payload.get("task_id") or event.task_id
                if stage and task_id:
                    stages[str(task_id)] = str(stage)
        return stages

    def step(self, delta: int) -> bool:
        return False

    def position(self) -> str:
        head = self._last.head.seq if self._last else 0
        return f"seq {head}"

    def lineage(self, task_id: str) -> CausalWhyResult | None:
        snapshot = self._last
        if snapshot is None or self.store is None:
            return None
        publication = next(
            (p for p in snapshot.publications if p.task_id == task_id and p.state == "accepted"),
            None,
        ) or next((p for p in snapshot.publications if p.task_id == task_id), None)
        if publication is None:
            return None
        self._refresh_events()
        domain = self.store.snapshot(self.mission_id)
        return why(domain, tuple(self._events), publication.publication_id, reference_exists=lambda _ref: None)

    def notice(self) -> str | None:
        return self._notice


def stage_for_tasks(snapshot: MissionControlSnapshot, stages: Mapping[str, str]) -> dict[str, str]:
    """Only cancelled or failed nodes carry a stage; a running one has not reached it."""

    return {
        task.task_id: stages[task.task_id]
        for task in snapshot.tasks
        if task.task_id in stages and task.state in {"cancelled", "failed", "retrying"}
    }


def why_pane(detail: MissionTaskDetail, lineage: CausalWhyResult | None, *, source_label: str) -> Text:
    """The drill-in pane: stage reached, checks, receipts, and lineage links."""

    text = Text()
    text.append(f"{detail.task.task_id}\n", "bold cyan")
    text.append(f"{detail.task.title}\n", "bold")
    text.append(f"state {detail.task.state} · kind {detail.task.kind}\n")
    if detail.task.blocker_reason:
        text.append(f"blocked: {detail.task.blocker_reason}\n", "dark_orange")
    text.append("\nattempts\n", "bold")
    if not detail.attempts:
        text.append("  none yet\n", "grey62")
    for attempt in detail.attempts:
        text.append(
            f"  #{attempt.number} {attempt.status} · {attempt.result_code or '—'} · fence {attempt.fencing_token} · {attempt.worker_id}\n"
        )
    text.append("\nchecks\n", "bold")
    for check in detail.acceptance_checks or ("(none declared)",):
        text.append(f"  {check}\n")
    text.append("\nreceipts\n", "bold")
    receipts = (*detail.test_receipts, *detail.command_receipts, *detail.resource_receipts)
    if not receipts:
        text.append("  none yet\n", "grey62")
    for receipt in receipts[:8]:
        text.append(f"  {receipt}\n", "grey70")
    if len(receipts) > 8:
        text.append(f"  … {len(receipts) - 8} more\n", "grey62")
    if detail.publications:
        text.append("\npublications\n", "bold")
        for item in detail.publications:
            text.append(f"  {item}\n", "grey70")
    if detail.unknowns:
        text.append("\nunknowns\n", "bold")
        for item in detail.unknowns:
            text.append(f"  {item}\n", "magenta")
    text.append("\nlineage\n", "bold")
    if lineage is None:
        if source_label == "replay":
            text.append("  the replay carries checkpoints, not the event store; attach live for lineage\n", "grey62")
        else:
            text.append("  no publication yet — lineage starts when this node publishes\n", "grey62")
    else:
        for link in lineage.links:
            style = {"established": "green", "not_present": "grey62", "unknown": "magenta", "rejected": "red"}[link.status]
            text.append(f"  {link.stage:18} {link.status}", style)
            if link.nodes:
                first = link.nodes[0]
                extra = f" · {first.node_type} {first.node_id}"
                if first.stage_reached:
                    extra += f" · stage {first.stage_reached}"
                text.append(extra, "grey70")
            text.append("\n")
        if lineage.unknowns:
            text.append(f"  unknowns: {len(lineage.unknowns)}\n", "magenta")
    return text


def summary_pane(snapshot: MissionControlSnapshot) -> Text:
    """What was done: goal, per-node outcomes, artifacts touched, receipts."""

    text = Text()
    text.append("what was done\n", "bold")
    text.append(f"{snapshot.mission.goal}\n", "italic")
    text.append(f"mission {snapshot.mission.status}", "bold")
    if snapshot.mission.outcome:
        text.append(f" · {snapshot.mission.outcome}")
    text.append("\n\nnodes\n", "bold")
    receipt_count = 0
    for task in snapshot.tasks:
        detail = task_detail(snapshot, task.task_id)
        receipt_count += len(detail.test_receipts) + len(detail.command_receipts) + len(detail.resource_receipts)
        last = detail.attempts[-1] if detail.attempts else None
        outcome = f"{last.result_code or last.status}" if last else "no attempt"
        attempts = f"{len(detail.attempts)} attempt{'s' if len(detail.attempts) != 1 else ''}"
        text.append(f"  {task.task_id:18} {task.state:12} {outcome} · {attempts}\n")
    touched = sorted({path for p in snapshot.publications if p.state == "accepted" for path in p.paths})
    text.append("\nartifacts touched\n", "bold")
    if not touched:
        text.append("  none accepted\n", "grey62")
    for path in touched[:12]:
        text.append(f"  {path}\n", "grey70")
    if len(touched) > 12:
        text.append(f"  … {len(touched) - 12} more\n", "grey62")
    text.append("\nresult\n", "bold")
    text.append(f"  {snapshot.result.state}")
    if snapshot.result.bundle_id:
        text.append(f" · bundle {snapshot.result.bundle_id}")
    text.append("\n")
    if snapshot.result.summary:
        text.append(f"  {snapshot.result.summary}\n", "grey70")
    text.append(f"\nreceipts: {receipt_count} evidence-bound across {len(snapshot.tasks)} nodes · head seq {snapshot.head.seq}\n", "bold")
    if snapshot.unknowns:
        text.append(f"unknowns: {len(snapshot.unknowns)} (listed, never guessed)\n", "magenta")
    return text
