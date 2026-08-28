from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping
from threading import RLock
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from ..hashing import canonical_json_bytes, canonical_json_sha256
from .mission_models import (
    AuthorizationMode,
    ArtifactPublication,
    Attempt,
    AttemptState,
    EvidenceReference,
    Gate,
    MissionEvent,
    MissionEventType,
    MissionStatus,
    FinalizationMode,
    MissionSnapshot as DomainMissionSnapshot,
    TaskKind,
    TaskState,
    plan_policy_decision,
)
from .mission_reducer import TransitionError, reduce_events
from .sqlite_mission_store import MissionNotFound as StoreMissionNotFound
from .sqlite_mission_store import MissionStoreError

TaskStateValue = Literal[
    "queued",
    "ready",
    "running",
    "blocked",
    "retrying",
    "needs_input",
    "verifying",
    "done",
    "failed",
    "cancelled",
]
RelationshipKind = Literal[
    "decomposed_into",
    "depends_on",
    "assigned_to",
    "blocked_by",
    "produced",
    "accepted_from",
    "verified_by",
    "inherited",
]
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_MAX_PROJECTED_EVENTS = 16_384


class MissionProjectionError(RuntimeError):
    pass


class MissionNotFound(LookupError):
    pass


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MissionHeadView(ViewModel):
    mission_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=1)
    event_sha256: str = Field(pattern=_SHA256_PATTERN)


class MissionView(ViewModel):
    mission_id: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=512)
    success_criteria: tuple[str, ...] = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=64)
    plan_revision: int = Field(ge=1)
    # The revision alone names a number; the digest names the graph. Both are
    # carried so a dashboard row, a `why` chain, and an orientation view can
    # each say which exact plan they are describing, and whether a person
    # approved it. A view recorded before this field existed carries None —
    # "this projection does not say", never a fabricated digest.
    plan_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    approved_plan_revision: int | None = Field(default=None, ge=1)
    outcome: str | None = Field(default=None, max_length=512)
    creation_source: str = Field(min_length=1, max_length=64)
    requested_authorization_mode: AuthorizationMode = AuthorizationMode.REVIEW_REQUIRED
    effective_authorization_mode: AuthorizationMode | None = (
        AuthorizationMode.REVIEW_REQUIRED
    )
    finalization_mode: FinalizationMode = FinalizationMode.REVIEW_REQUIRED
    policy_decision_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)

    @model_serializer(mode="wrap")
    def preserve_legacy_view_bytes(self, handler: Any) -> dict[str, Any]:
        value = handler(self)
        optional = {
            "requested_authorization_mode",
            "effective_authorization_mode",
            "finalization_mode",
            "policy_decision_sha256",
        }
        for name in optional - self.model_fields_set:
            value.pop(name, None)
        return value


class EvidenceRefView(ViewModel):
    kind: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=_SHA256_PATTERN)


class AttemptEvidenceView(ViewModel):
    kind: Literal["generic_attempt_v1", "legacy_v2"]
    evidence_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    href: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def discriminator_matches_fields(self) -> AttemptEvidenceView:
        generic = (
            self.kind == "generic_attempt_v1"
            and self.evidence_id is not None
            and self.run_id is self.href is None
        )
        legacy = (
            self.kind == "legacy_v2"
            and self.run_id is not None
            and self.href is not None
            and self.href.startswith("/")
            and not self.href.startswith("//")
            and self.evidence_id is None
        )
        if not (generic or legacy):
            raise ValueError("attempt evidence fields do not match their kind")
        return self


class TaskView(ViewModel):
    task_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    contract: str = Field(min_length=1, max_length=1_024)
    state: TaskStateValue
    kind: str = Field(min_length=1, max_length=32)
    priority: int
    assigned_role: str = Field(min_length=1, max_length=128)
    dependency_ids: tuple[str, ...] = Field(max_length=64)
    worker_id: str | None = Field(default=None, max_length=128)
    current_attempt_id: str | None = Field(default=None, max_length=128)
    blocker_reason: str | None = Field(default=None, max_length=512)
    read_scope: tuple[str, ...] = Field(max_length=256)
    write_scope: tuple[str, ...] = Field(max_length=128)
    allowed_command_templates: tuple[str, ...] = Field(max_length=32)
    acceptance_checks: tuple[str, ...] = Field(max_length=32)


class AttemptView(ViewModel):
    attempt_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    worker_id: str = Field(min_length=1, max_length=128)
    number: int = Field(ge=1, le=20)
    status: str = Field(min_length=1, max_length=64)
    workspace_id: str = Field(min_length=1, max_length=128)
    lease_id: str = Field(min_length=1, max_length=128)
    fencing_token: int = Field(ge=1)
    result_code: str | None = Field(default=None, max_length=128)
    evidence: AttemptEvidenceView | None = None
    evidence_refs: tuple[EvidenceRefView, ...] = Field(max_length=64)


class WorkerView(ViewModel):
    worker_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64)
    task_id: str | None = Field(default=None, max_length=128)
    attempt_id: str | None = Field(default=None, max_length=128)
    fencing_token: int | None = Field(default=None, ge=1)


class GateOptionView(ViewModel):
    value: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=160)
    consequence: str = Field(min_length=1, max_length=512)


class GateView(ViewModel):
    gate_id: str = Field(min_length=1, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(min_length=1, max_length=512)
    status: Literal["pending", "decided"]
    evidence_summary: str | None = Field(default=None, max_length=512)
    options: tuple[GateOptionView, ...] = Field(min_length=1, max_length=8)
    resolution: str | None = Field(default=None, max_length=128)
    truth_kind: str = Field(min_length=1, max_length=64)


class PublicationView(ViewModel):
    publication_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    attempt_id: str = Field(min_length=1, max_length=128)
    output_name: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=64)
    sha256: str = Field(pattern=_SHA256_PATTERN)
    paths: tuple[str, ...] = Field(max_length=64)
    consumers: tuple[str, ...] = Field(max_length=64)


class RelationshipView(ViewModel):
    relationship_id: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=256)
    target: str = Field(min_length=1, max_length=256)
    kind: RelationshipKind
    evidence_refs: tuple[EvidenceRefView, ...] = Field(default=(), max_length=16)


class StageView(ViewModel):
    state: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=512)
    task_id: str | None = Field(default=None, max_length=128)
    attempt_id: str | None = Field(default=None, max_length=128)
    evidence_refs: tuple[EvidenceRefView, ...] = Field(default=(), max_length=32)


class ResourceMetricView(ViewModel):
    label: str = Field(min_length=1, max_length=160)
    display_value: str = Field(min_length=1, max_length=128)
    category: Literal[
        "measured_runtime", "estimated_context", "provider", "unavailable"
    ]
    attribution_quality: Literal[
        "measured_bound", "sampled_partial", "aggregate_only", "unavailable"
    ]


class ResourceSummaryView(ViewModel):
    status: Literal["healthy", "pressure", "exhausted", "unavailable"]
    summary: str = Field(min_length=1, max_length=512)
    metrics: tuple[ResourceMetricView, ...] = Field(default=(), max_length=32)


class ResultView(ViewModel):
    state: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=512)
    bundle_id: str | None = Field(
        default=None,
        pattern=r"^final_result_[0-9a-f]{32}$",
        exclude_if=lambda value: value is None,
    )
    bundle_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    evidence_refs: tuple[EvidenceRefView, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def bundle_identity_is_complete(self) -> ResultView:
        if (self.bundle_id is None) != (self.bundle_sha256 is None):
            raise ValueError("final result bundle identity is incomplete")
        return self


class MissionControlSnapshot(ViewModel):
    view_version: Literal[1] = 1
    mission: MissionView
    head: MissionHeadView
    cursor: str = Field(min_length=1, max_length=8_192)
    tasks: tuple[TaskView, ...] = Field(min_length=1, max_length=256)
    attempts: tuple[AttemptView, ...] = Field(default=(), max_length=5_120)
    workers: tuple[WorkerView, ...] = Field(default=(), max_length=256)
    gates: tuple[GateView, ...] = Field(default=(), max_length=128)
    publications: tuple[PublicationView, ...] = Field(default=(), max_length=5_120)
    relationships: tuple[RelationshipView, ...] = Field(max_length=10_240)
    integration: StageView
    verification: StageView
    resources: ResourceSummaryView
    needs_you: GateView | None = None
    critical_path_task_ids: tuple[str, ...] = Field(default=(), max_length=256)
    result: ResultView
    unknowns: tuple[str, ...] = Field(default=(), max_length=64)
    snapshot_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def references_and_digest_are_valid(self) -> MissionControlSnapshot:
        if self.head.mission_id != self.mission.mission_id:
            raise ValueError("mission view head belongs to another mission")
        try:
            cursor_seq, cursor_sha256 = decode_cursor(
                self.cursor, self.mission.mission_id
            )
        except MissionProjectionError as error:
            raise ValueError("mission view cursor is invalid") from error
        if (cursor_seq, cursor_sha256) != (
            self.head.seq,
            self.head.event_sha256,
        ):
            raise ValueError("mission view cursor does not bind its head")
        collections = (
            tuple(item.task_id for item in self.tasks),
            tuple(item.attempt_id for item in self.attempts),
            tuple(item.worker_id for item in self.workers),
            tuple(item.gate_id for item in self.gates),
            tuple(item.publication_id for item in self.publications),
            tuple(item.relationship_id for item in self.relationships),
        )
        if any(items != tuple(sorted(set(items))) for items in collections):
            raise ValueError("mission view collections must be sorted and unique")
        task_ids = {item.task_id for item in self.tasks}
        attempt_ids = {item.attempt_id for item in self.attempts}
        worker_ids = {item.worker_id for item in self.workers}
        gate_ids = {item.gate_id for item in self.gates}
        if any(not set(item.dependency_ids) <= task_ids for item in self.tasks):
            raise ValueError("mission view task dependency is unknown")
        if any(item.task_id not in task_ids for item in self.attempts):
            raise ValueError("mission view attempt task is unknown")
        if any(item.worker_id not in worker_ids for item in self.attempts):
            raise ValueError("mission view attempt worker is unknown")
        attempts = {item.attempt_id: item for item in self.attempts}
        workers = {item.worker_id: item for item in self.workers}
        if any(
            item.current_attempt_id is not None
            and (
                item.current_attempt_id not in attempts
                or attempts[item.current_attempt_id].task_id != item.task_id
            )
            for item in self.tasks
        ):
            raise ValueError("mission view task attempt is unknown")
        if any(
            item.worker_id is not None and item.worker_id not in workers
            for item in self.tasks
        ):
            raise ValueError("mission view task worker is unknown")
        if any(
            item.task_id not in task_ids
            or item.attempt_id not in attempt_ids
            or attempts[item.attempt_id].task_id != item.task_id
            or not set(item.consumers) <= task_ids
            for item in self.publications
        ):
            raise ValueError("mission view publication reference is unknown")
        if any(
            item.task_id is not None and item.task_id not in task_ids
            for item in self.gates
        ):
            raise ValueError("mission view gate task is unknown")
        if self.needs_you is not None and (
            self.needs_you.gate_id not in gate_ids or self.needs_you.status != "pending"
        ):
            raise ValueError("needs_you must reference a pending projected gate")
        node_ids = {
            f"mission:{self.mission.mission_id}",
            *(f"task:{item.task_id}" for item in self.tasks),
            *(f"worker:{item.worker_id}" for item in self.workers),
            *(f"gate:{item.gate_id}" for item in self.gates),
            f"integration:{self.mission.mission_id}",
            f"verification:{self.mission.mission_id}",
            f"result:{self.mission.mission_id}",
        }
        if any(
            item.source not in node_ids or item.target not in node_ids
            for item in self.relationships
        ):
            raise ValueError("mission relationship endpoint is unknown")
        if not set(self.critical_path_task_ids) <= task_ids:
            raise ValueError("mission critical path references an unknown task")
        if len(self.critical_path_task_ids) != len(set(self.critical_path_task_ids)):
            raise ValueError("mission critical path contains a duplicate task")
        if self.unknowns != tuple(sorted(set(self.unknowns))):
            raise ValueError("mission unknowns must be sorted and unique")
        public = self.model_dump(mode="json", exclude={"cursor", "snapshot_sha256"})
        if self.snapshot_sha256 != canonical_json_sha256(public):
            raise ValueError("mission view snapshot digest does not match")
        return self


ItemT = TypeVar("ItemT", bound=ViewModel)


class CollectionPatch(ViewModel, Generic[ItemT]):
    upsert: tuple[ItemT, ...] = ()
    remove: tuple[str, ...] = ()

    @model_validator(mode="after")
    def collections_are_canonical(self) -> CollectionPatch[ItemT]:
        if self.remove != tuple(sorted(set(self.remove))):
            raise ValueError("collection removals must be sorted and unique")
        identities: list[str] = []
        for item in self.upsert:
            identity = next(
                (
                    str(getattr(item, name))
                    for name in type(item).model_fields
                    if name.endswith("_id") and getattr(item, name) is not None
                ),
                None,
            )
            if identity is None:
                raise ValueError("collection upsert has no stable identity")
            identities.append(identity)
        if identities != sorted(set(identities)):
            raise ValueError("collection upserts must be sorted and unique")
        if set(identities) & set(self.remove):
            raise ValueError("collection patch cannot remove and upsert the same item")
        return self


class MissionDelta(ViewModel):
    view_version: Literal[1] = 1
    mission_id: str = Field(min_length=1, max_length=128)
    from_seq: int = Field(ge=1)
    to_seq: int = Field(ge=2)
    from_head_sha256: str = Field(pattern=_SHA256_PATTERN)
    head: MissionHeadView
    cursor: str = Field(min_length=1, max_length=8_192)
    snapshot_sha256: str = Field(pattern=_SHA256_PATTERN)
    mission: MissionView
    tasks: CollectionPatch[TaskView]
    attempts: CollectionPatch[AttemptView]
    workers: CollectionPatch[WorkerView]
    gates: CollectionPatch[GateView]
    publications: CollectionPatch[PublicationView]
    relationships: CollectionPatch[RelationshipView]
    integration: StageView
    verification: StageView
    resources: ResourceSummaryView
    needs_you: GateView | None = None
    critical_path_task_ids: tuple[str, ...] = Field(max_length=256)
    result: ResultView
    unknowns: tuple[str, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def heads_are_contiguous(self) -> MissionDelta:
        if (
            self.to_seq <= self.from_seq
            or self.head.mission_id != self.mission_id
            or self.head.seq != self.to_seq
            or self.mission.mission_id != self.mission_id
        ):
            raise ValueError("mission delta heads are invalid")
        try:
            cursor_seq, cursor_sha256 = decode_cursor(self.cursor, self.mission_id)
        except MissionProjectionError as error:
            raise ValueError("mission delta cursor is invalid") from error
        if (cursor_seq, cursor_sha256) != (
            self.head.seq,
            self.head.event_sha256,
        ):
            raise ValueError("mission delta cursor does not bind its head")
        return self


class MissionTaskDetail(ViewModel):
    view_version: Literal[1] = 1
    mission_id: str = Field(min_length=1, max_length=128)
    head: MissionHeadView
    task: TaskView
    attempts: tuple[AttemptView, ...] = Field(max_length=20)
    read_scope: tuple[str, ...] = Field(max_length=256)
    write_scope: tuple[str, ...] = Field(max_length=128)
    acceptance_checks: tuple[str, ...] = Field(max_length=32)
    inherited_evidence: tuple[str, ...] = Field(max_length=128)
    publications: tuple[str, ...] = Field(max_length=128)
    changed_hunks: tuple[str, ...] = Field(max_length=128)
    command_receipts: tuple[str, ...] = Field(max_length=128)
    test_receipts: tuple[str, ...] = Field(max_length=128)
    resource_receipts: tuple[str, ...] = Field(max_length=128)
    unknowns: tuple[str, ...] = Field(max_length=64)


class GenericAttemptEvidence(ViewModel):
    view_version: Literal[1] = 1
    mission_id: str = Field(min_length=1, max_length=128)
    head: MissionHeadView
    attempt: AttemptView
    references: tuple[EvidenceRefView, ...] = Field(max_length=64)
    limitations: tuple[str, ...] = Field(max_length=16)


def _reference(item: EvidenceReference) -> EvidenceRefView:
    return EvidenceRefView(
        kind=str(item.kind), id=str(item.id), sha256=str(item.sha256)
    )


def encode_cursor(mission_id: str, seq: int, event_sha256: str) -> str:
    raw = canonical_json_bytes(
        {
            "event_sha256": event_sha256,
            "mission_id": mission_id,
            "seq": seq,
            "view_version": 1,
        }
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(cursor: str, mission_id: str) -> tuple[int, str]:
    try:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 8_192:
            raise ValueError
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(raw)
        if (
            base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != cursor
            or canonical_json_bytes(value) != raw
            or set(value) != {"event_sha256", "mission_id", "seq", "view_version"}
            or value["mission_id"] != mission_id
            or value["view_version"] != 1
            or not isinstance(value["seq"], int)
            or value["seq"] < 1
            or not isinstance(value["event_sha256"], str)
            or len(value["event_sha256"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in value["event_sha256"]
            )
        ):
            raise ValueError
        return value["seq"], value["event_sha256"]
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise MissionProjectionError("mission stream cursor is invalid") from error


def _attempt_evidence(
    attempt: Attempt, legacy_viewer_base: str | None
) -> AttemptEvidenceView | None:
    link = attempt.evidence_link
    if link is None:
        return None
    if link.kind == "generic_v1":
        return AttemptEvidenceView(
            kind="generic_attempt_v1", evidence_id=str(link.evidence_id)
        )
    if legacy_viewer_base is None:
        return None
    base = "/" + legacy_viewer_base.strip("/") if legacy_viewer_base else ""
    return AttemptEvidenceView(
        kind="legacy_v2",
        run_id=str(link.run_id),
        href=f"{base}/viewer/{link.run_id}",
    )


def _attempts(
    snapshot: DomainMissionSnapshot, legacy_viewer_base: str | None
) -> tuple[AttemptView, ...]:
    return tuple(
        AttemptView(
            attempt_id=str(item.attempt_id),
            task_id=str(item.task_id),
            worker_id=str(item.worker_id),
            number=item.attempt_number,
            status=str(item.state),
            workspace_id=str(item.workspace_id),
            lease_id=str(item.lease_id),
            fencing_token=item.fencing_token,
            result_code=str(item.result_code) if item.result_code else None,
            evidence=_attempt_evidence(item, legacy_viewer_base),
            evidence_refs=tuple(_reference(ref) for ref in item.evidence_refs),
        )
        for item in snapshot.attempts
    )


def _workers(snapshot: DomainMissionSnapshot) -> tuple[WorkerView, ...]:
    leases = {item.attempt_id: item for item in snapshot.leases}
    tasks = {item.task_id: item for item in snapshot.tasks}
    latest: dict[str, Attempt] = {}
    for attempt in snapshot.attempts:
        current = latest.get(str(attempt.worker_id))
        if current is None or (
            attempt.started_at,
            attempt.fencing_token,
            str(attempt.attempt_id),
        ) > (
            current.started_at,
            current.fencing_token,
            str(current.attempt_id),
        ):
            latest[str(attempt.worker_id)] = attempt
    return tuple(
        WorkerView(
            worker_id=worker_id,
            label=str(leases[attempt.attempt_id].owner)
            if attempt.attempt_id in leases
            else worker_id,
            role=str(tasks[attempt.task_id].assigned_role),
            status=str(attempt.state),
            task_id=str(attempt.task_id),
            attempt_id=str(attempt.attempt_id),
            fencing_token=attempt.fencing_token,
        )
        for worker_id, attempt in sorted(latest.items())
    )


def _tasks(snapshot: DomainMissionSnapshot) -> tuple[TaskView, ...]:
    attempts_by_task: dict[str, Attempt] = {}
    for attempt in snapshot.attempts:
        task_id = str(attempt.task_id)
        current = attempts_by_task.get(task_id)
        if current is None or attempt.attempt_number > current.attempt_number:
            attempts_by_task[task_id] = attempt
    values: list[TaskView] = []
    for item in snapshot.tasks:
        attempt = attempts_by_task.get(str(item.task_id))
        active_attempt = (
            attempt
            if attempt is not None
            and attempt.state in {AttemptState.LEASED, AttemptState.RUNNING}
            else None
        )
        values.append(
            TaskView(
                task_id=str(item.task_id),
                title=str(item.title),
                contract=str(item.contract),
                state=str(item.state),
                kind=str(item.kind),
                priority=item.priority,
                assigned_role=str(item.assigned_role),
                dependency_ids=tuple(str(value) for value in item.dependencies),
                worker_id=str(active_attempt.worker_id) if active_attempt else None,
                current_attempt_id=(
                    str(active_attempt.attempt_id) if active_attempt else None
                ),
                blocker_reason=str(item.blocker) if item.blocker else None,
                read_scope=tuple(str(value) for value in item.read_paths),
                write_scope=tuple(str(value) for value in item.write_paths),
                allowed_command_templates=tuple(
                    str(value) for value in item.allowed_commands
                ),
                acceptance_checks=tuple(str(value) for value in item.acceptance_checks),
            )
        )
    return tuple(values)


def _publications(
    publications: Iterable[ArtifactPublication],
) -> tuple[PublicationView, ...]:
    return tuple(
        PublicationView(
            publication_id=str(item.publication_id),
            task_id=str(item.task_id),
            attempt_id=str(item.attempt_id),
            output_name=str(item.output_name),
            kind=str(item.kind),
            state=str(item.state),
            sha256=str(item.sha256),
            paths=tuple(str(path) for path in item.paths),
            consumers=tuple(str(value) for value in item.consumers),
        )
        for item in publications
    )


def _decision_attribution(event: MissionEvent, action: str) -> str:
    label = event.payload.get("operator_label")
    bounded_label = (
        str(label)[:64] if isinstance(label, str) and label else "unavailable"
    )
    truth_kind = str(event.truth_kind)
    authority = str(event.authority)
    if truth_kind == "human_attested" and authority == "operator":
        return f'{action} was human-attested under operator label "{bounded_label}".'
    if truth_kind == "simulated_fixture":
        return (
            f"The scripted fixture recorded {action.lower()}; human attestation is "
            "not established."
        )
    return (
        f'{action} command was committed under bounded operator label "{bounded_label}" '
        f"as {truth_kind}/{authority}; human attestation is not established."
    )


def _verify_gate_bindings(
    gates: tuple[Gate, ...], events: tuple[MissionEvent, ...]
) -> None:
    requested = tuple(
        event for event in events if event.event_type == MissionEventType.GATE_REQUESTED
    )
    decided = tuple(
        event for event in events if event.event_type == MissionEventType.GATE_DECIDED
    )
    requested_by_id = {str(event.payload.get("gate_id")): event for event in requested}
    decided_by_id = {str(event.payload.get("gate_id")): event for event in decided}
    gates_by_id = {str(gate.gate_id): gate for gate in gates}
    if (
        len(requested_by_id) != len(requested)
        or len(decided_by_id) != len(decided)
        or set(requested_by_id) != set(gates_by_id)
        or not set(decided_by_id) <= set(gates_by_id)
    ):
        raise MissionProjectionError(
            "materialized mission gates do not match committed gate events"
        )
    for gate_id, gate in gates_by_id.items():
        request = requested_by_id[gate_id]
        requested_gate = gate.model_copy(
            update={"operator_label": None, "rationale": None, "resolution": None}
        )
        decision = decided_by_id.get(gate_id)
        if (
            request.payload.get("gate_sha256")
            != canonical_json_sha256(requested_gate.model_dump(mode="json"))
            or request.truth_kind != gate.truth_kind
            or request.references != gate.evidence
            or (gate.resolution is None) != (decision is None)
            or (
                decision is not None
                and (
                    decision.payload.get("gate_sha256")
                    != canonical_json_sha256(gate.model_dump(mode="json"))
                    or decision.payload.get("choice") != gate.resolution
                    or decision.payload.get("operator_label") != gate.operator_label
                    or decision.payload.get("operator_rationale") != gate.rationale
                    or decision.references != gate.evidence
                )
            )
        ):
            raise MissionProjectionError(
                "materialized mission gate does not match its committed event"
            )


def _gate_views(
    gates: Iterable[Gate], events: Iterable[MissionEvent] = ()
) -> tuple[GateView, ...]:
    """Project materialized gates; their events intentionally expose only hashes/IDs."""

    decisions = {
        str(event.payload.get("gate_id")): event
        for event in events
        if event.event_type == MissionEventType.GATE_DECIDED
        and event.payload.get("gate_id") is not None
    }
    values: list[GateView] = []
    for gate in gates:
        reference_summary = (
            "1 committed evidence reference supports this decision."
            if len(gate.evidence) == 1
            else (
                f"{len(gate.evidence)} committed evidence references support this decision."
                if gate.evidence
                else None
            )
        )
        decision = decisions.get(str(gate.gate_id)) if gate.resolution else None
        if gate.resolution and decision is None:
            raise MissionProjectionError(
                "resolved gate has no committed decision event"
            )
        attribution = (
            _decision_attribution(decision, "Gate decision") if decision else None
        )
        evidence_summary = " ".join(
            item for item in (reference_summary, attribution) if item
        )
        values.append(
            GateView(
                gate_id=str(gate.gate_id),
                task_id=str(gate.task_id) if gate.task_id else None,
                reason=str(gate.reason),
                status="decided" if gate.resolution else "pending",
                evidence_summary=evidence_summary or None,
                options=tuple(
                    GateOptionView(
                        value=str(option.value),
                        label=str(option.value)
                        .replace("_", " ")
                        .replace(".", " ")
                        .title(),
                        consequence=str(option.consequence),
                    )
                    for option in gate.allowed_decisions
                ),
                resolution=str(gate.resolution) if gate.resolution else None,
                truth_kind=str(decision.truth_kind if decision else gate.truth_kind),
            )
        )
    return tuple(values)


def _event_refs(event: MissionEvent | None) -> tuple[EvidenceRefView, ...]:
    return () if event is None else tuple(_reference(item) for item in event.references)


def _stage(
    snapshot: DomainMissionSnapshot,
    events: tuple[MissionEvent, ...],
    kind: TaskKind,
    started_type: MissionEventType,
    completed_type: MissionEventType,
    failed_type: MissionEventType,
    label: str,
) -> StageView:
    task = next((item for item in snapshot.tasks if item.kind == kind), None)
    last = next(
        (
            event
            for event in reversed(events)
            if event.event_type in {started_type, completed_type, failed_type}
        ),
        None,
    )
    if last is not None:
        event_state = (
            "done"
            if last.event_type == completed_type
            else "failed"
            if last.event_type == failed_type
            else "running"
        )
        task_state = (
            "running"
            if task and task.state == TaskState.VERIFYING
            else str(task.state)
            if task
            else event_state
        )
        state = task_state
        summary = (
            str(last.payload.get("summary") or f"{label} {state}.")
            if task_state == event_state
            else f"{label} is {task_state.replace('_', ' ')}."
        )
    elif task is not None:
        state = str(task.state)
        summary = f"{label} is {str(task.state).replace('_', ' ')}."
    else:
        state, summary = "queued", f"{label} has not started."
    attempt = next(
        (
            item
            for item in reversed(snapshot.attempts)
            if task and item.task_id == task.task_id
        ),
        None,
    )
    return StageView(
        state=state,
        summary=summary,
        task_id=str(task.task_id) if task else None,
        attempt_id=str(attempt.attempt_id) if attempt else None,
        evidence_refs=_event_refs(last),
    )


def _resources(events: tuple[MissionEvent, ...]) -> ResourceSummaryView:
    event = next(
        (
            item
            for item in reversed(events)
            if item.event_type
            in {
                MissionEventType.RESOURCE_SUMMARY_RECORDED,
                MissionEventType.RESOURCE_BUDGET_CROSSED,
            }
        ),
        None,
    )
    if event is None:
        return ResourceSummaryView(
            status="unavailable",
            summary="No authoritative resource receipt is available for this checkpoint.",
        )
    payload = event.payload
    metrics = payload.get("metrics")
    if isinstance(metrics, list):
        categories = {
            "managed_runtime": "measured_runtime",
            "context_footprint": "estimated_context",
            "provider_telemetry": "provider",
        }
        parsed = tuple(
            ResourceMetricView(
                label=str(item.get("label") or "Resource")[:160],
                display_value=str(item.get("display_value") or "unavailable")[:128],
                category=categories.get(
                    str(item.get("category")),
                    str(item.get("category") or "unavailable"),
                ),
                attribution_quality=str(
                    item.get("attribution_quality") or "unavailable"
                ),
            )
            for item in metrics
            if isinstance(item, Mapping)
        )
        raw_status = str(payload.get("status") or "")
        status = (
            raw_status
            if raw_status in {"healthy", "pressure", "exhausted", "unavailable"}
            else "pressure"
            if event.event_type == MissionEventType.RESOURCE_BUDGET_CROSSED
            else "healthy"
        )
        return ResourceSummaryView(
            status=status,
            summary=str(
                payload.get("summary") or "A committed resource summary is available."
            )[:512],
            metrics=parsed,
        )

    scope = str(payload.get("scope") or "")
    category = {
        "context_payload": "estimated_context",
        "context-payload": "estimated_context",
        "remote_request": "provider",
        "remote-request": "provider",
        "isolated_process_tree": "measured_runtime",
        "isolated-process-tree": "measured_runtime",
        "shared_process": "measured_runtime",
        "shared-process": "measured_runtime",
        "cloud_container": "measured_runtime",
        "cloud-container": "measured_runtime",
    }.get(scope, "unavailable")
    quality = str(payload.get("attribution_quality") or "unavailable")
    if quality not in {
        "measured_bound",
        "sampled_partial",
        "aggregate_only",
        "unavailable",
    }:
        quality = "unavailable"
    value = payload.get("value")
    threshold = payload.get("threshold")
    available = (
        quality != "unavailable"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    )
    units = str(payload.get("units") or "units")
    if available:
        display = f"{value:g} {units}"
        if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
            display += f" / {threshold:g} {units} threshold"
            remaining = threshold - value
            display += (
                f" · {remaining:g} {units} headroom"
                if remaining >= 0
                else f" · {-remaining:g} {units} over"
            )
    else:
        quality = "unavailable"
        display = "unavailable"
    label = str(payload.get("subject") or "Resource").replace("_", " ").title()
    crossed = bool(payload.get("threshold_crossed")) or (
        event.event_type == MissionEventType.RESOURCE_BUDGET_CROSSED
    )
    status = "unavailable" if not available else "pressure" if crossed else "healthy"
    action = str(payload.get("action") or "none recorded").replace("_", " ")
    source = str(payload.get("source") or "unavailable")
    if not available:
        summary = (
            f"{label} is unavailable from {source}; no resource pressure is inferred."
        )
    elif crossed:
        summary = f"{label} reached its committed threshold; recorded action: {action}."
    elif threshold is not None:
        summary = (
            f"{label} remains below its committed threshold; recorded action: {action}."
        )
    else:
        summary = f"{label} has a committed receipt with no threshold; recorded action: {action}."
    return ResourceSummaryView(
        status=status,
        summary=summary[:512],
        metrics=(
            ResourceMetricView(
                label=label[:160],
                display_value=display[:128],
                category=category,
                attribution_quality=quality,
            ),
        ),
    )


def _approved_plan_revision(events: tuple[MissionEvent, ...]) -> int | None:
    """The revision the last approval named, or None if none has been given."""
    for event in reversed(events):
        if event.event_type == MissionEventType.PLAN_APPROVED:
            revision = event.payload.get("plan_revision")
            return revision if isinstance(revision, int) else None
    return None


def _critical_path(tasks: tuple[TaskView, ...]) -> tuple[str, ...]:
    by_id = {task.task_id: task for task in tasks}
    active = {task.task_id for task in tasks if task.state not in {"done", "cancelled"}}
    memo: dict[str, tuple[str, ...]] = {}

    def path(task_id: str) -> tuple[str, ...]:
        if task_id in memo:
            return memo[task_id]
        dependencies = [
            value for value in by_id[task_id].dependency_ids if value in active
        ]
        candidates = [path(value) for value in dependencies]
        prefix = max(candidates, key=lambda value: (len(value), value), default=())
        memo[task_id] = (*prefix, task_id)
        return memo[task_id]

    return max(
        (path(task_id) for task_id in sorted(active)),
        key=lambda value: (len(value), value),
        default=(),
    )


def _relationships(
    snapshot: DomainMissionSnapshot,
    tasks: tuple[TaskView, ...],
    workers: tuple[WorkerView, ...],
    gates: tuple[GateView, ...],
    publications: tuple[PublicationView, ...],
) -> tuple[RelationshipView, ...]:
    mission_id = str(snapshot.mission.mission_id)
    integration_id = f"integration:{mission_id}"
    verification_id = f"verification:{mission_id}"
    result_id = f"result:{mission_id}"
    values: dict[str, RelationshipView] = {}

    def add(source: str, target: str, kind: RelationshipKind) -> None:
        identity = f"{kind}:{source}:{target}"
        values[identity] = RelationshipView(
            relationship_id=identity, source=source, target=target, kind=kind
        )

    for task in tasks:
        add(f"mission:{mission_id}", f"task:{task.task_id}", "decomposed_into")
        for dependency in task.dependency_ids:
            add(f"task:{task.task_id}", f"task:{dependency}", "depends_on")
    for worker in workers:
        if worker.task_id:
            add(f"task:{worker.task_id}", f"worker:{worker.worker_id}", "assigned_to")
    for gate in gates:
        if gate.status != "pending":
            continue
        if gate.task_id:
            add(f"task:{gate.task_id}", f"gate:{gate.gate_id}", "blocked_by")
        elif gate.gate_id.startswith("final_result_"):
            add(result_id, f"gate:{gate.gate_id}", "blocked_by")
        else:
            add(f"mission:{mission_id}", f"gate:{gate.gate_id}", "blocked_by")
    assembly = next(
        (item for item in tasks if item.kind == str(TaskKind.ASSEMBLY)), None
    )
    verification = next(
        (item for item in tasks if item.kind == str(TaskKind.VERIFICATION)), None
    )
    accepted_tasks = {
        item.task_id
        for item in publications
        if item.state == "accepted"
        and any(
            task.task_id == item.task_id and task.kind == str(TaskKind.WORK)
            for task in tasks
        )
    }
    for task_id in sorted(accepted_tasks):
        add(integration_id, f"task:{task_id}", "accepted_from")
    if assembly:
        add(f"task:{assembly.task_id}", integration_id, "produced")
    add(integration_id, verification_id, "verified_by")
    if verification:
        add(f"task:{verification.task_id}", verification_id, "produced")
    add(verification_id, result_id, "produced")
    for publication in publications:
        if publication.state == "accepted":
            for consumer in publication.consumers:
                if any(task.task_id == consumer for task in tasks):
                    add(f"task:{consumer}", f"task:{publication.task_id}", "inherited")
    return tuple(values[key] for key in sorted(values))


def project_snapshot(
    snapshot: DomainMissionSnapshot,
    events: Iterable[MissionEvent] = (),
    *,
    legacy_viewer_base: str | None = None,
) -> MissionControlSnapshot:
    if snapshot.head.seq < 1 or snapshot.head.event_sha256 is None:
        raise MissionProjectionError("mission has no committed projection head")
    verified_events = tuple(events)
    previous_sha256: str | None = None
    for expected_seq, event in enumerate(verified_events, start=1):
        if (
            str(event.mission_id) != str(snapshot.mission.mission_id)
            or event.seq != expected_seq
            or event.previous_event_sha256 != previous_sha256
        ):
            raise MissionProjectionError("mission event chain is not contiguous")
        previous_sha256 = str(event.event_sha256)
    if (
        not verified_events
        or verified_events[-1].seq != snapshot.head.seq
        or verified_events[-1].event_sha256 != snapshot.head.event_sha256
    ):
        raise MissionProjectionError("mission events do not reach the snapshot head")
    try:
        policy_decision = plan_policy_decision(verified_events, snapshot.plan.revision)
    except ValueError as error:
        raise MissionProjectionError("mission policy decision is invalid") from error
    if policy_decision is not None and (
        policy_decision.policy_id != snapshot.policy.policy_id
        or policy_decision.policy_revision != snapshot.policy.revision
        or policy_decision.policy_sha256 != snapshot.policy.policy_sha256
        or policy_decision.base_sha != snapshot.mission.base_sha
        or policy_decision.plan_sha256
        != canonical_json_sha256(snapshot.plan.model_dump(mode="json"))
    ):
        raise MissionProjectionError("mission policy decision bindings are invalid")
    tasks = _tasks(snapshot)
    attempts = _attempts(snapshot, legacy_viewer_base)
    workers = _workers(snapshot)
    _verify_gate_bindings(snapshot.gates, verified_events)
    gates = _gate_views(snapshot.gates, verified_events)
    publications = _publications(snapshot.publications)
    integration = _stage(
        snapshot,
        verified_events,
        TaskKind.ASSEMBLY,
        MissionEventType.ASSEMBLY_STARTED,
        MissionEventType.ASSEMBLY_COMPLETED,
        MissionEventType.ASSEMBLY_FAILED,
        "Integration",
    )
    verification = _stage(
        snapshot,
        verified_events,
        TaskKind.VERIFICATION,
        MissionEventType.VERIFICATION_STARTED,
        MissionEventType.VERIFICATION_COMPLETED,
        MissionEventType.VERIFICATION_FAILED,
        "Verification",
    )
    candidate_event = next(
        (
            item
            for item in reversed(verified_events)
            if item.event_type == MissionEventType.FINAL_CANDIDATE_READY
        ),
        None,
    )
    bundle_events = tuple(
        item
        for item in verified_events
        if item.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
    )
    if len(bundle_events) > 1:
        raise MissionProjectionError("final result bundle authority is ambiguous")
    bundle_event = bundle_events[0] if bundle_events else None
    final_event = next(
        (
            item
            for item in reversed(verified_events)
            if item.event_type
            in {
                MissionEventType.FINAL_CANDIDATE_READY,
                MissionEventType.FINAL_RESULT_BUNDLE_READY,
                MissionEventType.FINAL_CANDIDATE_APPROVED,
                MissionEventType.FINAL_CANDIDATE_REJECTED,
                MissionEventType.ISOLATED_COMMIT_CREATED,
            }
        ),
        None,
    )
    result_states = {
        MissionEventType.FINAL_CANDIDATE_READY: "preparing",
        MissionEventType.FINAL_RESULT_BUNDLE_READY: "awaiting_decision",
        MissionEventType.FINAL_CANDIDATE_APPROVED: "approved",
        MissionEventType.FINAL_CANDIDATE_REJECTED: "rejected",
        MissionEventType.ISOLATED_COMMIT_CREATED: "commit_created",
    }
    result_summaries = {
        MissionEventType.FINAL_CANDIDATE_READY: (
            "The final candidate and verification evidence are being bound into an "
            "exact review bundle."
        ),
        MissionEventType.FINAL_RESULT_BUNDLE_READY: (
            "The immutable final-result bundle is persisted and awaits an exact "
            "bundle-bound decision."
        ),
        MissionEventType.ISOLATED_COMMIT_CREATED: (
            "The approved result was recorded as an isolated local commit."
        ),
    }
    result_state = (
        result_states.get(final_event.event_type, "pending")
        if final_event
        else "pending"
    )
    if final_event and final_event.event_type in {
        MissionEventType.FINAL_CANDIDATE_APPROVED,
        MissionEventType.FINAL_CANDIDATE_REJECTED,
    }:
        action = (
            "Final approval"
            if final_event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
            else "Final rejection"
        )
        result_summary = _decision_attribution(final_event, action)
        if final_event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED:
            result_summary += " Isolated local commit recording is pending."
        if final_event.event_type == MissionEventType.FINAL_CANDIDATE_REJECTED:
            result_summary += " No isolated commit was authorized."
    elif final_event:
        result_summary = result_summaries[final_event.event_type]
    elif snapshot.mission.final_outcome:
        result_summary = str(snapshot.mission.final_outcome)
    else:
        result_summary = "No final result decision has been committed."
    bundle_id = (
        str(bundle_event.payload.get("bundle_id"))
        if bundle_event and bundle_event.payload.get("bundle_id")
        else None
    )
    bundle_sha256 = (
        str(bundle_event.payload.get("bundle_sha256"))
        if bundle_event and bundle_event.payload.get("bundle_sha256")
        else None
    )
    if bundle_event is not None and (
        candidate_event is None
        or bundle_event.seq != candidate_event.seq + 1
        or bundle_event.previous_event_sha256 != candidate_event.event_sha256
        or (
            final_event is not None
            and final_event.event_type
            in {
                MissionEventType.FINAL_CANDIDATE_APPROVED,
                MissionEventType.FINAL_CANDIDATE_REJECTED,
            }
            and (
                final_event.payload.get("bundle_id") != bundle_id
                or final_event.payload.get("bundle_sha256") != bundle_sha256
            )
        )
    ):
        raise MissionProjectionError("final result bundle event binding is invalid")
    result_references = _event_refs(final_event)
    if final_event is bundle_event and candidate_event is not None:
        result_references = tuple(
            {
                (item.kind, item.id, item.sha256): item
                for item in (*_event_refs(candidate_event), *result_references)
            }.values()
        )
    result = ResultView(
        state=result_state,
        summary=result_summary,
        bundle_id=bundle_id,
        bundle_sha256=bundle_sha256,
        evidence_refs=result_references,
    )
    pending = tuple(item for item in gates if item.status == "pending")
    automatic_finalization = (
        policy_decision is not None
        and policy_decision.effective_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
        and policy_decision.finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED
    )
    if (
        automatic_finalization
        and final_event is not None
        and final_event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
    ):
        result = result.model_copy(
            update={
                "state": "auto_finalizing",
                "summary": (
                    "The exact verified bundle is awaiting policy-authorized isolated "
                    "result recording; no human decision is required."
                ),
            }
        )
    if (
        str(snapshot.mission.status) == "awaiting_result"
        and not pending
        and not automatic_finalization
        and final_event is not None
        and final_event.event_type == MissionEventType.FINAL_RESULT_BUNDLE_READY
    ):
        bundle_id = str(final_event.payload["bundle_id"])
        candidate_sha256 = str(final_event.payload["candidate_sha256"])
        final_decision = GateView(
            gate_id=bundle_id,
            reason=f"Approve or reject immutable bundle {bundle_id}?",
            status="pending",
            evidence_summary=(
                "One committed evidence reference binds the immutable review bundle; "
                "no final decision command is committed yet."
                if len(result.evidence_refs) == 1
                else (
                    f"{len(result.evidence_refs)} committed evidence references bind the "
                    "bundle, candidate, and verification; no final decision is committed yet."
                )
                if result.evidence_refs
                else (
                    "The committed mission state is awaiting result review; no final "
                    "decision command is committed yet."
                )
            ),
            options=(
                GateOptionView(
                    value="approve_result",
                    label="Approve result",
                    consequence=(
                        f"Authorize bundle {bundle_id} containing candidate sha256:"
                        f"{candidate_sha256}; create one isolated local commit with no "
                        "push or user-branch mutation."
                    ),
                ),
                GateOptionView(
                    value="reject_result",
                    label="Reject result",
                    consequence=(
                        f"Reject bundle {bundle_id} containing candidate sha256:"
                        f"{candidate_sha256}; create no local result commit or result ref."
                    ),
                ),
            ),
            truth_kind="server_derived",
        )
        gates = tuple(sorted((*gates, final_decision), key=lambda item: item.gate_id))
        pending = (final_decision,)
    mission = MissionView(
        mission_id=str(snapshot.mission.mission_id),
        goal=str(snapshot.mission.goal),
        success_criteria=tuple(
            str(value) for value in snapshot.mission.success_criteria
        ),
        status=str(snapshot.mission.status),
        plan_revision=snapshot.mission.plan_revision,
        plan_sha256=canonical_json_sha256(snapshot.plan.model_dump(mode="json")),
        approved_plan_revision=_approved_plan_revision(verified_events),
        outcome=str(snapshot.mission.final_outcome)
        if snapshot.mission.final_outcome
        else None,
        creation_source=str(snapshot.mission.creation_source),
        **(
            (
                {}
                if snapshot.mission.schema_version
                == snapshot.policy.schema_version
                == 1
                else {
                    "requested_authorization_mode": (
                        snapshot.mission.requested_authorization_mode
                    ),
                    "effective_authorization_mode": None,
                    "finalization_mode": snapshot.mission.requested_finalization_mode,
                    "policy_decision_sha256": None,
                }
            )
            if policy_decision is None
            else {
                "requested_authorization_mode": policy_decision.requested_mode,
                "effective_authorization_mode": policy_decision.effective_mode,
                "finalization_mode": policy_decision.finalization_mode,
                "policy_decision_sha256": policy_decision.decision_sha256,
            }
        ),
    )
    head = MissionHeadView(
        mission_id=mission.mission_id,
        seq=snapshot.head.seq,
        event_sha256=str(snapshot.head.event_sha256),
    )
    public: dict[str, Any] = {
        "view_version": 1,
        "mission": mission,
        "head": head,
        "tasks": tasks,
        "attempts": attempts,
        "workers": workers,
        "gates": gates,
        "publications": publications,
        "relationships": _relationships(snapshot, tasks, workers, gates, publications),
        "integration": integration,
        "verification": verification,
        "resources": _resources(verified_events),
        "needs_you": pending[0] if pending else None,
        "critical_path_task_ids": _critical_path(tasks),
        "result": result,
        "unknowns": tuple(
            sorted(
                {
                    *(str(value) for value in snapshot.unknowns),
                    *(
                        (
                            "Additional unresolved gates exist; Mission Control shows the first committed gate.",
                        )
                        if len(pending) > 1
                        else ()
                    ),
                }
            )
        ),
    }
    # Nested tuples/models need Pydantic's serializer before hashing.
    provisional = MissionControlSnapshot.model_construct(
        **public,
        cursor=encode_cursor(mission.mission_id, head.seq, head.event_sha256),
        snapshot_sha256="0" * 64,
    )
    digest_public = provisional.model_dump(
        mode="json", exclude={"cursor", "snapshot_sha256"}
    )
    return MissionControlSnapshot(
        **public,
        cursor=encode_cursor(mission.mission_id, head.seq, head.event_sha256),
        snapshot_sha256=canonical_json_sha256(digest_public),
    )


def _patch(
    before: Iterable[ItemT], after: Iterable[ItemT], key: str
) -> CollectionPatch[ItemT]:
    old = {str(getattr(item, key)): item for item in before}
    new = {str(getattr(item, key)): item for item in after}
    return CollectionPatch[ItemT](
        upsert=tuple(
            new[item_id] for item_id in sorted(new) if old.get(item_id) != new[item_id]
        ),
        remove=tuple(sorted(set(old) - set(new))),
    )


def diff_snapshots(
    before: MissionControlSnapshot, after: MissionControlSnapshot
) -> MissionDelta:
    if before.mission.mission_id != after.mission.mission_id:
        raise MissionProjectionError("cannot diff different missions")
    if after.head.seq <= before.head.seq:
        raise MissionProjectionError("mission delta must advance the committed head")
    return MissionDelta(
        mission_id=after.mission.mission_id,
        from_seq=before.head.seq,
        to_seq=after.head.seq,
        from_head_sha256=before.head.event_sha256,
        head=after.head,
        cursor=after.cursor,
        snapshot_sha256=after.snapshot_sha256,
        mission=after.mission,
        tasks=_patch(before.tasks, after.tasks, "task_id"),
        attempts=_patch(before.attempts, after.attempts, "attempt_id"),
        workers=_patch(before.workers, after.workers, "worker_id"),
        gates=_patch(before.gates, after.gates, "gate_id"),
        publications=_patch(before.publications, after.publications, "publication_id"),
        relationships=_patch(
            before.relationships, after.relationships, "relationship_id"
        ),
        integration=after.integration,
        verification=after.verification,
        resources=after.resources,
        needs_you=after.needs_you,
        critical_path_task_ids=after.critical_path_task_ids,
        result=after.result,
        unknowns=after.unknowns,
    )


def _apply_patch(
    items: Iterable[ItemT], patch: CollectionPatch[ItemT], key: str
) -> tuple[ItemT, ...]:
    values = {str(getattr(item, key)): item for item in items}
    for item_id in patch.remove:
        values.pop(item_id, None)
    for item in patch.upsert:
        values[str(getattr(item, key))] = item
    return tuple(values[item_id] for item_id in sorted(values))


def apply_delta(
    before: MissionControlSnapshot, raw: MissionDelta
) -> MissionControlSnapshot:
    delta = MissionDelta.model_validate(raw)
    if (
        before.mission.mission_id == delta.mission_id
        and before.head.seq == delta.to_seq
        and before.snapshot_sha256 == delta.snapshot_sha256
    ):
        return before
    if (
        before.mission.mission_id != delta.mission_id
        or before.head.seq != delta.from_seq
        or before.head.event_sha256 != delta.from_head_sha256
    ):
        raise MissionProjectionError("mission delta does not continue the current head")
    value = MissionControlSnapshot(
        mission=delta.mission,
        head=delta.head,
        cursor=delta.cursor,
        tasks=_apply_patch(before.tasks, delta.tasks, "task_id"),
        attempts=_apply_patch(before.attempts, delta.attempts, "attempt_id"),
        workers=_apply_patch(before.workers, delta.workers, "worker_id"),
        gates=_apply_patch(before.gates, delta.gates, "gate_id"),
        publications=_apply_patch(
            before.publications, delta.publications, "publication_id"
        ),
        relationships=_apply_patch(
            before.relationships, delta.relationships, "relationship_id"
        ),
        integration=delta.integration,
        verification=delta.verification,
        resources=delta.resources,
        needs_you=delta.needs_you,
        critical_path_task_ids=delta.critical_path_task_ids,
        result=delta.result,
        unknowns=delta.unknowns,
        snapshot_sha256=delta.snapshot_sha256,
    )
    return value


def task_detail(snapshot: MissionControlSnapshot, task_id: str) -> MissionTaskDetail:
    task = next((item for item in snapshot.tasks if item.task_id == task_id), None)
    if task is None:
        raise MissionNotFound("mission task not found")
    attempts = tuple(item for item in snapshot.attempts if item.task_id == task_id)
    references = tuple(ref for item in attempts for ref in item.evidence_refs)
    publications = tuple(
        item for item in snapshot.publications if item.task_id == task_id
    )

    def refs(*terms: str) -> tuple[str, ...]:
        return tuple(
            f"{item.kind}:{item.id} · sha256:{item.sha256}"
            for item in references
            if any(term in item.kind for term in terms)
        )

    inherited = tuple(
        f"Accepted {item.kind} {item.output_name} from {item.task_id} · sha256:{item.sha256}"
        for item in snapshot.publications
        if task_id in item.consumers and item.state == "accepted"
    )
    return MissionTaskDetail(
        mission_id=snapshot.mission.mission_id,
        head=snapshot.head,
        task=task,
        attempts=attempts,
        read_scope=task.read_scope,
        write_scope=task.write_scope,
        acceptance_checks=task.acceptance_checks,
        inherited_evidence=inherited,
        publications=tuple(
            f"{item.state} {item.kind} {item.output_name} · "
            f"paths:{', '.join(item.paths) or 'none'} · sha256:{item.sha256}"
            for item in publications
        ),
        changed_hunks=refs("path", "hunk", "change"),
        command_receipts=refs("command"),
        test_receipts=refs("test", "check"),
        resource_receipts=refs("resource"),
        unknowns=(
            "Raw prompts, unrestricted environment, secret-bearing argv, stdout/stderr, private artifact bytes, and hidden reasoning are not exposed.",
        ),
    )


def attempt_evidence(
    snapshot: MissionControlSnapshot, attempt_id: str
) -> GenericAttemptEvidence:
    attempt = next(
        (item for item in snapshot.attempts if item.attempt_id == attempt_id), None
    )
    if (
        attempt is None
        or attempt.evidence is None
        or attempt.evidence.kind != "generic_attempt_v1"
    ):
        raise MissionNotFound("generic attempt evidence not found")
    return GenericAttemptEvidence(
        mission_id=snapshot.mission.mission_id,
        head=snapshot.head,
        attempt=attempt,
        references=attempt.evidence_refs,
        limitations=(
            "This is a bounded generic attempt projection, not the legacy v2 Auth evidence viewer.",
            "Raw prompts, environment, command arguments, output, private artifacts, and hidden reasoning are excluded.",
        ),
    )


class MissionProjection:
    """Cache a public projection while reading only newly committed mission events.

    Cold starts verify a bounded event history; this is not a fully materialized cold
    projection. Live updates read only the committed suffix after the cached head.
    """

    def __init__(self, store: Any, *, legacy_viewer_base: str | None = None):
        self.store = store
        self.legacy_viewer_base = legacy_viewer_base
        self._lock = RLock()
        self._events: dict[str, list[MissionEvent]] = {}
        self._views: dict[str, MissionControlSnapshot] = {}
        self._domain_snapshot_sha256: dict[str, str] = {}
        self._integrity_markers: dict[str, object] = {}
        self._quarantined: set[str] = set()

    def snapshot(self, mission_id: str) -> MissionControlSnapshot:
        with self._lock:
            if mission_id in self._quarantined:
                raise MissionProjectionError("mission evidence is quarantined")
            try:
                return self._unchecked_snapshot(mission_id)
            except MissionProjectionError:
                self._quarantined.add(mission_id)
                raise

    def _unchecked_snapshot(self, mission_id: str) -> MissionControlSnapshot:
        with self._lock:
            marker = getattr(self.store, "integrity_marker", None)

            def read_marker() -> object | None:
                if not callable(marker):
                    return None
                try:
                    return marker(mission_id)
                except (KeyError, StoreMissionNotFound) as error:
                    raise MissionNotFound("mission not found") from error
                except MissionStoreError as error:
                    raise MissionProjectionError(
                        "mission materialized state failed store validation"
                    ) from error

            cached = self._views.get(mission_id)
            if cached is not None and callable(marker):
                current_marker = read_marker()
                if self._integrity_markers.get(mission_id) == current_marker:
                    return cached
            for _attempt in range(2 if callable(marker) else 1):
                before_marker = read_marker()
                try:
                    domain = self.store.snapshot(mission_id)
                except (KeyError, StoreMissionNotFound) as error:
                    raise MissionNotFound("mission not found") from error
                except MissionStoreError as error:
                    raise MissionProjectionError(
                        "mission materialized state failed store validation"
                    ) from error
                if domain is None:
                    raise MissionNotFound("mission not found")
                after_marker = read_marker()
                if before_marker == after_marker:
                    self._integrity_markers[mission_id] = after_marker
                    break
            else:
                raise MissionProjectionError(
                    "mission materialized state changed during validation"
                )
            domain = DomainMissionSnapshot.model_validate(domain)
            if domain.head.seq > _MAX_PROJECTED_EVENTS:
                raise MissionProjectionError(
                    "mission exceeds the bounded Mission Control event window"
                )
            cached = self._views.get(mission_id)
            if cached and cached.head.seq == domain.head.seq:
                if (
                    cached.head.event_sha256 != domain.head.event_sha256
                    or self._domain_snapshot_sha256.get(mission_id)
                    != domain.snapshot_sha256
                ):
                    raise MissionProjectionError(
                        "mission materialized state changed without a new event"
                    )
                return cached
            events = self._events.setdefault(mission_id, [])
            after = events[-1].seq if events else 0
            if after > domain.head.seq:
                raise MissionProjectionError("mission materialized head regressed")
            while after < domain.head.seq:
                batch = tuple(
                    self.store.tail(
                        mission_id,
                        after_seq=after,
                        limit=min(256, domain.head.seq - after),
                    )
                )
                if not batch:
                    raise MissionProjectionError(
                        "mission event tail ended before its head"
                    )
                validated = tuple(MissionEvent.model_validate(item) for item in batch)
                previous_sha256 = events[-1].event_sha256 if events else None
                for offset, event in enumerate(validated, start=1):
                    if (
                        str(event.mission_id) != mission_id
                        or event.seq != after + offset
                        or event.previous_event_sha256 != previous_sha256
                    ):
                        raise MissionProjectionError(
                            "mission event tail is not contiguous"
                        )
                    previous_sha256 = event.event_sha256
                events.extend(validated)
                after = events[-1].seq
            initial_mission = domain.mission.model_copy(
                update={"status": MissionStatus.PROPOSED, "final_outcome": None}
            )
            try:
                reduced = reduce_events(
                    initial_mission,
                    domain.plan.tasks,
                    tuple(events),
                    plan_revision=domain.plan.revision,
                    policy_schema_version=domain.policy.schema_version,
                )
            except TransitionError as error:
                raise MissionProjectionError(
                    "mission materialized state failed event replay"
                ) from error
            if (
                len(events) != domain.head.event_count
                or (events[-1].event_sha256 if events else None)
                != domain.head.event_sha256
                or reduced.status != domain.mission.status
                or reduced.task_states
                != {task.task_id: task.state for task in domain.tasks}
                or reduced.attempt_counts
                != {task.task_id: task.attempt_count for task in domain.tasks}
            ):
                raise MissionProjectionError(
                    "mission materialized state does not match event replay"
                )
            view = project_snapshot(
                domain,
                events,
                legacy_viewer_base=self.legacy_viewer_base,
            )
            self._views[mission_id] = view
            self._domain_snapshot_sha256[mission_id] = str(domain.snapshot_sha256)
            return view

    def task_detail(self, mission_id: str, task_id: str) -> MissionTaskDetail:
        return task_detail(self.snapshot(mission_id), task_id)

    def attempt_evidence(
        self, mission_id: str, attempt_id: str
    ) -> GenericAttemptEvidence:
        return attempt_evidence(self.snapshot(mission_id), attempt_id)
