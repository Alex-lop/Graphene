from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from hmac import compare_digest
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from google.api_core.exceptions import Aborted, AlreadyExists, Conflict
from google.cloud import firestore

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from .completion import reduce_failed_completion, reduce_successful_completion
from .cloud_protocol import (
    ArtifactFetchGrant,
    DispatchOutboxRecord,
    DispatchOutboxState,
    DispatchTransition,
    ExecutorArtifactObservation,
    ExecutorArtifactReference,
    ExecutorSession,
    ExecutorSessionState,
    FirestoreNamespaceSchema,
    MaterializedStatePointer,
    StateRootRecord,
    StateShardKind,
    StateShardRecord,
    StateShardReference,
    new_dispatch_record,
)
from .evidence import TrustedCheckReceipt
from .mission_models import (
    Attempt,
    AttemptResult,
    AttemptState,
    EvidenceReference,
    Lease,
    Mission,
    MissionAuthority,
    MissionEvent,
    MissionEventInput,
    MissionEventType,
    MissionHead,
    MissionSnapshot,
    MissionStatus,
    Plan,
    ProjectPolicy,
    ProjectPolicySummary,
    PublicationState,
    PublishedArtifactReferenceV2,
    Task,
    TaskKind,
    TaskState,
)
from .mission_reducer import transition_mission, transition_task
from .sqlite_mission_store import (
    BudgetExhausted,
    MissionConflict,
    MissionNotFound,
    MissionStoreError,
    StaleWorker,
)
from .validation import require_valid_plan
from ..core_models import TruthKind

_EVENTS = "events"
_COMMANDS = "commands"
_MATERIALIZED = "materialized"
_STATE_RECORDS = "state_records"
_STATE_ROOTS = "state_roots"
_LEASE_SLOTS = "lease_slots"
_LEASES = "leases"
_DISPATCH_OUTBOX = "dispatch_outbox"
_EXECUTOR_SESSIONS = "executor_sessions"
_ARTIFACT_CAPABILITIES = "artifact_capabilities"
_ARTIFACT_LOCALITY = "artifact_locality"
_CURRENT = "current"
_SCHEMA = "schema"
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_COMMAND_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_MAX_LEASE_SECONDS = 3_600
_MAX_STATE_DOCUMENT_BYTES = 450_000
_MAX_STATE_ROOT_BYTES = 65_536
_FIRESTORE_SCHEMA_VERSION = 2
_FIRESTORE_READER_VERSION = 2
_FIRESTORE_WRITER_VERSION = 2
_NAMESPACE_SCHEMA = FirestoreNamespaceSchema(
    current_version=_FIRESTORE_SCHEMA_VERSION,
    min_reader_version=_FIRESTORE_READER_VERSION,
    min_writer_version=_FIRESTORE_WRITER_VERSION,
)


class FirestoreMissionError(MissionStoreError):
    """Base error for rejected or malformed Firestore mission state."""


class LeaseFenceRejected(StaleWorker):
    """A missing, expired, released, or superseded lease rejected an effect."""


class MissionStateInvalid(FirestoreMissionError):
    """Stored mission state did not validate against the frozen domain model."""


class ExecutorSessionRejected(FirestoreMissionError):
    """The authenticated executor does not own the requested session."""


class MultiExecutorUnsupported(ExecutorSessionRejected):
    """Cloud multi-executor is unsupported in this release (§6.4).

    The store keeps one mission-wide expected head, so a second concurrent
    executor session would fail at a random later claim with a bare conflict.
    Registration refuses the second session up front instead; the
    transactional-head redesign is post-demo work.
    """


class DispatchStateRejected(FirestoreMissionError):
    """The dispatch outbox state does not allow the requested transition."""


class ArtifactLocalityUnavailable(FirestoreMissionError):
    """Required private artifact bytes belong to an unavailable executor."""


class ArtifactCapabilityRejected(FirestoreMissionError):
    """An artifact capability was expired, replayed, or outside its exact scope."""


class DomainTransitionUnavailable(FirestoreMissionError):
    """No shared authoritative domain transition can commit this effect."""


def _now() -> datetime:
    return datetime.now(UTC)


def _document_data(snapshot: Any) -> dict[str, Any] | None:
    if not snapshot.exists:
        return None
    value = snapshot.to_dict()
    if not isinstance(value, dict):
        raise MissionStateInvalid("Firestore document is not an object")
    return value


def _sequence_id(seq: int) -> str:
    return f"{seq:020d}"


def _command_ref_id(command_id: str) -> str:
    if not isinstance(command_id, str) or _COMMAND_ID.fullmatch(command_id) is None:
        raise ValueError("command_id must be a valid idempotency key")
    return sha256_hex(command_id.encode())


def _event(
    mission_id: str,
    head: MissionHead,
    command_id: str,
    draft: MissionEventInput,
    *,
    event_id: str,
    recorded_at: datetime,
) -> MissionEvent:
    fields = {
        **{name: getattr(draft, name) for name in MissionEventInput.model_fields},
        "schema_version": 1,
        "event_id": event_id,
        "mission_id": mission_id,
        "seq": head.seq + 1,
        "server_recorded_at": recorded_at,
        "command_id": command_id,
        "payload_sha256": canonical_json_sha256(draft.payload),
        "previous_event_sha256": head.event_sha256,
    }
    canonical = MissionEvent.model_construct(
        **fields, event_sha256="0" * 64
    ).model_dump(mode="json", exclude={"event_sha256"})
    return MissionEvent.model_validate(
        {**canonical, "event_sha256": canonical_json_sha256(canonical)}
    )


def _lease_identity(lease: Lease) -> tuple[object, ...]:
    return (
        lease.lease_id,
        lease.mission_id,
        lease.plan_revision,
        lease.task_id,
        lease.attempt_id,
        lease.owner,
        lease.capability,
        lease.write_paths,
        lease.fencing_token,
        lease.issued_at,
    )


def _lease_fence_request(lease: Lease) -> dict[str, object]:
    return {
        "lease_id": lease.lease_id,
        "mission_id": lease.mission_id,
        "plan_revision": lease.plan_revision,
        "task_id": lease.task_id,
        "attempt_id": lease.attempt_id,
        "owner": lease.owner,
        "capability": lease.capability,
        "write_paths": list(lease.write_paths),
        "fencing_token": lease.fencing_token,
        "issued_at": lease.issued_at.isoformat(),
    }


@dataclass(frozen=True, slots=True)
class _StateBundle:
    root: StateRootRecord
    shards: tuple[StateShardRecord, ...]


def _state_shard(
    kind: StateShardKind,
    head: MissionHead,
    value: dict[str, Any],
) -> StateShardRecord:
    provisional = StateShardRecord.model_construct(
        kind=kind,
        committed_head=head,
        value=value,
        schema_version=2,
        shard_sha256="0" * 64,
    )
    canonical = provisional.model_dump(mode="json", exclude={"shard_sha256"})
    return StateShardRecord.model_validate(
        {**canonical, "shard_sha256": canonical_json_sha256(canonical)}
    )


def _state_bundle(snapshot: MissionSnapshot) -> _StateBundle:
    shards = (
        _state_shard(
            StateShardKind.SUMMARY,
            snapshot.head,
            {
                "policy": snapshot.policy.model_dump(mode="json"),
                "mission": snapshot.mission.model_dump(mode="json"),
                "plan": snapshot.plan.model_dump(mode="json"),
            },
        ),
        _state_shard(
            StateShardKind.TASKS,
            snapshot.head,
            {"tasks": [item.model_dump(mode="json") for item in snapshot.tasks]},
        ),
        _state_shard(
            StateShardKind.ATTEMPTS_LEASES,
            snapshot.head,
            {
                "attempts": [
                    item.model_dump(mode="json") for item in snapshot.attempts
                ],
                "leases": [item.model_dump(mode="json") for item in snapshot.leases],
            },
        ),
        _state_shard(
            StateShardKind.PUBLICATIONS_GATES,
            snapshot.head,
            {
                "publications": [
                    item.model_dump(mode="json") for item in snapshot.publications
                ],
                "gates": [item.model_dump(mode="json") for item in snapshot.gates],
            },
        ),
        _state_shard(
            StateShardKind.RESULT,
            snapshot.head,
            {
                "mission_status": snapshot.mission.status.value,
                "final_outcome": snapshot.mission.final_outcome,
                "unknowns": list(snapshot.unknowns),
            },
        ),
    )
    references = tuple(
        StateShardReference(kind=item.kind, shard_sha256=item.shard_sha256)
        for item in shards
    )
    provisional = StateRootRecord.model_construct(
        schema_version=2,
        committed_head=snapshot.head,
        snapshot_sha256=snapshot.snapshot_sha256,
        shards=references,
        root_sha256="0" * 64,
    )
    canonical = provisional.model_dump(mode="json", exclude={"root_sha256"})
    root = StateRootRecord.model_validate(
        {**canonical, "root_sha256": canonical_json_sha256(canonical)}
    )
    for shard in shards:
        if len(canonical_json_bytes(shard.model_dump(mode="json"))) > _MAX_STATE_DOCUMENT_BYTES:
            raise ValueError(f"materialized {shard.kind.value} shard exceeds its bound")
    if len(canonical_json_bytes(root.model_dump(mode="json"))) > _MAX_STATE_ROOT_BYTES:
        raise ValueError("materialized state root exceeds its bound")
    return _StateBundle(root=root, shards=shards)


def _snapshot_from_bundle(bundle: _StateBundle) -> MissionSnapshot:
    values = {item.kind: item.value for item in bundle.shards}
    summary = values[StateShardKind.SUMMARY]
    tasks = values[StateShardKind.TASKS]
    attempts_leases = values[StateShardKind.ATTEMPTS_LEASES]
    publications_gates = values[StateShardKind.PUBLICATIONS_GATES]
    result = values[StateShardKind.RESULT]
    if (
        summary["mission"].get("status") != result["mission_status"]
        or summary["mission"].get("final_outcome") != result["final_outcome"]
        or summary["mission"].get("unknowns") != result["unknowns"]
    ):
        raise MissionStateInvalid("result shard diverges from the mission summary")
    snapshot = MissionSnapshot.model_validate(
        {
            "schema_version": 1,
            "policy": summary["policy"],
            "mission": summary["mission"],
            "plan": summary["plan"],
            "tasks": tasks["tasks"],
            "attempts": attempts_leases["attempts"],
            "leases": attempts_leases["leases"],
            "publications": publications_gates["publications"],
            "gates": publications_gates["gates"],
            "head": bundle.root.committed_head.model_dump(mode="json"),
            "unknowns": result["unknowns"],
            "snapshot_sha256": bundle.root.snapshot_sha256,
        }
    )
    if snapshot.head != bundle.root.committed_head:
        raise MissionStateInvalid("state shards belong to another head")
    return snapshot


def _policy_summary(policy: ProjectPolicy) -> ProjectPolicySummary:
    return ProjectPolicySummary(
        schema_version=policy.schema_version,
        policy_id=policy.policy_id,
        revision=policy.revision,
        repo_id=policy.repo_id,
        base_ref=policy.base_ref,
        base_sha=policy.base_sha,
        command_template_ids=tuple(
            item.template_id for item in policy.command_templates
        ),
        max_concurrency=policy.max_concurrency,
        retry_limit=policy.retry_limit,
        network_mode=policy.network.mode,
        policy_sha256=canonical_json_sha256(policy.model_dump(mode="json")),
        authorization_mode=policy.authorization_mode,
        finalization_mode=policy.finalization_mode,
    )


def _snapshot_with(
    snapshot: MissionSnapshot,
    head: MissionHead,
    *,
    mission: Mission | None = None,
    tasks: tuple[Task, ...] | None = None,
    attempts: tuple[Attempt, ...] | None = None,
    leases: tuple[Lease, ...] | None = None,
) -> MissionSnapshot:
    values = {
        **snapshot.model_dump(mode="json", exclude={"snapshot_sha256"}),
        "head": head.model_dump(mode="json"),
    }
    for name, value in {
        "mission": mission,
        "tasks": tasks,
        "attempts": attempts,
        "leases": leases,
    }.items():
        if value is not None:
            values[name] = (
                value.model_dump(mode="json")
                if isinstance(value, Mission)
                else [item.model_dump(mode="json") for item in value]
            )
    return MissionSnapshot.model_validate(
        {**values, "snapshot_sha256": canonical_json_sha256(values)}
    )


class FirestoreMissionStore:
    """Transactional Firestore adapter for mission heads, views, and leases.

    Event appends read a head and one command index, while projection polls read
    one content-addressed root, five bounded head-bound shards, and an indexed
    event tail. They never scan every event in a mission.

    The lease methods are internal persistence primitives, not a scheduler or a
    public claim service. Their caller remains responsible for policy, mission
    concurrency, task readiness, cross-task write-scope conflict checks, and
    appending the domain event that publishes a lease transition. Lease records
    deliberately do not mutate the event-head-bound materialized snapshot.
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        namespace: str,
        clock: Callable[[], datetime] = _now,
        max_lease_seconds: int = 300,
        allow_test_bootstrap: bool = False,
    ) -> None:
        if not isinstance(namespace, str) or _NAMESPACE.fullmatch(namespace) is None:
            raise ValueError("namespace must match ^[a-z][a-z0-9_-]{0,31}$")
        if (
            type(max_lease_seconds) is not int
            or not 1 <= max_lease_seconds <= _MAX_LEASE_SECONDS
        ):
            raise ValueError("max_lease_seconds must be between 1 and 3600")
        if type(allow_test_bootstrap) is not bool:
            raise TypeError("allow_test_bootstrap must be a boolean")
        self._client = client or firestore.Client()
        self._clock = clock
        self._max_lease_seconds = max_lease_seconds
        self._allow_test_bootstrap = allow_test_bootstrap
        self._namespace = namespace
        self._missions = self._client.collection(f"{namespace}_missions")
        self._schema_ref = self._client.collection(f"{namespace}_system").document(
            _SCHEMA
        )

    def _mission(self, mission_id: str):
        # MissionHead provides the shared Identifier validation without a second
        # identifier grammar in this adapter.
        MissionHead(mission_id=mission_id, seq=0, event_sha256=None, event_count=0)
        return self._missions.document(mission_id)

    @staticmethod
    def empty_head(mission_id: str) -> MissionHead:
        return MissionHead(
            mission_id=mission_id, seq=0, event_sha256=None, event_count=0
        )

    @staticmethod
    def _materialized_ref(mission: Any):
        return mission.collection(_MATERIALIZED).document(_CURRENT)

    def _head_from_snapshot(self, mission_id: str, snapshot: Any) -> MissionHead:
        data = _document_data(snapshot)
        if data is None:
            return self.empty_head(mission_id)
        try:
            head = MissionHead.model_validate(data["head"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("stored mission head is malformed") from error
        if head.mission_id != mission_id:
            raise MissionStateInvalid("stored mission head belongs to another mission")
        return head

    @staticmethod
    def _compatible_schema(snapshot: Any, *, writer: bool) -> bool:
        data = _document_data(snapshot)
        if data is None:
            return False
        try:
            schema = FirestoreNamespaceSchema.model_validate(data)
        except (TypeError, ValueError) as error:
            raise MissionStateInvalid("namespace schema document is malformed") from error
        supported = (
            schema.min_writer_version
            if writer
            else schema.min_reader_version
        )
        local = (
            _FIRESTORE_WRITER_VERSION if writer else _FIRESTORE_READER_VERSION
        )
        if schema.current_version != _FIRESTORE_SCHEMA_VERSION or not (
            supported <= local <= schema.current_version
        ):
            raise MissionStateInvalid("namespace schema is incompatible")
        return True

    def _require_read_schema(self) -> None:
        if not self._compatible_schema(self._schema_ref.get(), writer=False):
            raise MissionStateInvalid("namespace schema is not initialized")

    def namespace_schema(self) -> FirestoreNamespaceSchema:
        self._require_read_schema()
        data = _document_data(self._schema_ref.get())
        assert data is not None
        return FirestoreNamespaceSchema.model_validate(data)

    def initialize_namespace_schema(self) -> FirestoreNamespaceSchema:
        """Idempotently install only this adapter's exact namespace schema."""

        return self._transact(
            lambda _transaction: _NAMESPACE_SCHEMA,
            initialize_schema=True,
        )

    def _transact(
        self,
        callback: Callable[[Any], Any],
        *,
        initialize_schema: bool = False,
    ) -> Any:
        def guarded(transaction: Any) -> Any:
            schema_snapshot = self._schema_ref.get(transaction=transaction)
            missing = not self._compatible_schema(schema_snapshot, writer=True)
            if missing and not initialize_schema:
                raise MissionStateInvalid("namespace schema is not initialized")
            result = callback(transaction)
            if missing:
                transaction.create(
                    self._schema_ref, _NAMESPACE_SCHEMA.model_dump(mode="json")
                )
            return result

        try:
            return firestore.transactional(guarded)(self._client.transaction())
        except (Aborted, AlreadyExists, Conflict) as error:
            raise MissionConflict("Firestore transaction rejected the write") from error
        except ValueError as error:
            if isinstance(error.__cause__, Aborted):
                raise MissionConflict(
                    "Firestore transaction retry limit was exhausted"
                ) from error
            raise

    @staticmethod
    def _command_result(
        snapshot: Any, *, kind: str, request_sha256: str
    ) -> dict[str, Any] | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        if (
            data.get("schema_version") != 1
            or data.get("kind") != kind
            or data.get("request_sha256") != request_sha256
            or not isinstance(data.get("result"), dict)
        ):
            raise MissionConflict("command id was reused for another request")
        return data["result"]

    def head(self, mission_id: str) -> MissionHead:
        self._require_read_schema()
        mission = self._mission(mission_id)
        snapshot = mission.get()
        if not snapshot.exists:
            raise MissionNotFound(mission_id)
        return self._head_from_snapshot(mission_id, snapshot)

    @staticmethod
    def _events_for(
        mission_id: str,
        current: MissionHead,
        command_id: str,
        request_sha256: str,
        drafts: tuple[MissionEventInput, ...],
        recorded_at: datetime,
    ) -> tuple[tuple[MissionEvent, ...], MissionHead]:
        events: list[MissionEvent] = []
        head = current
        for index, draft in enumerate(drafts, start=1):
            event = _event(
                mission_id,
                head,
                command_id,
                draft,
                event_id=f"event_{request_sha256[:24]}_{index:04d}",
                recorded_at=recorded_at,
            )
            events.append(event)
            head = MissionHead(
                mission_id=mission_id,
                seq=event.seq,
                event_sha256=event.event_sha256,
                event_count=event.seq,
            )
        return tuple(events), head

    def _write_state_transition(
        self,
        transaction: Any,
        mission: Any,
        events: tuple[MissionEvent, ...],
        snapshot: MissionSnapshot,
        missing_state_writes: tuple[tuple[Any, dict[str, Any]], ...],
    ) -> None:
        bundle = _state_bundle(snapshot)
        for reference, value in missing_state_writes:
            transaction.create(reference, value)
        for event in events:
            transaction.create(
                mission.collection(_EVENTS).document(_sequence_id(event.seq)),
                {
                    "schema_version": 1,
                    "seq": event.seq,
                    "event_sha256": event.event_sha256,
                    "value": event.model_dump(mode="json"),
                },
            )
        transaction.set(
            mission,
            {"schema_version": 1, "head": snapshot.head.model_dump(mode="json")},
        )
        transaction.set(
            self._materialized_ref(mission),
            MaterializedStatePointer(
                committed_head=snapshot.head,
                materialization_pending=False,
                root_sha256=bundle.root.root_sha256,
                target_root_sha256=bundle.root.root_sha256,
            ).model_dump(mode="json"),
        )

    def create_mission(
        self,
        policy: ProjectPolicy,
        mission_contract: Mission,
        plan: Plan,
        command_id: str,
        *,
        plan_proposal_receipt: EvidenceReference | None = None,
        recorded_at: datetime,
    ) -> MissionHead:
        """Create the canonical aggregate, events, and five-shard view atomically."""

        if not all(
            (
                isinstance(policy, ProjectPolicy),
                isinstance(mission_contract, Mission),
                isinstance(plan, Plan),
            )
        ):
            raise TypeError("create_mission requires validated domain contracts")
        require_valid_plan(policy, plan)
        if plan_proposal_receipt is not None:
            raise DomainTransitionUnavailable(
                "cloud plan proposal receipt verification is unavailable"
            )
        if (
            mission_contract.status != MissionStatus.PROPOSED
            or mission_contract.mission_id != plan.mission_id
            or mission_contract.policy_id != policy.policy_id
            or mission_contract.policy_revision != policy.revision
            or mission_contract.repo_id != policy.repo_id
            or mission_contract.base_sha != policy.base_sha
            or mission_contract.plan_revision != plan.revision
            or mission_contract.resource_budget != policy.resource_budget
            or tuple(sorted(item.description for item in plan.criteria))
            != mission_contract.success_criteria
        ):
            raise MissionConflict("mission, plan, and policy bindings do not match")
        if max(mission_contract.schema_version, policy.schema_version) >= 2:
            raise DomainTransitionUnavailable(
                "cloud schema-2 policy decision persistence is unavailable"
            )
        mission_id = mission_contract.mission_id
        request_sha256 = canonical_json_sha256(
            {
                "action": "mission.create",
                "mission": mission_contract.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
            }
        )
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )

        def apply(transaction: Any) -> MissionHead:
            existing = self._command_result(
                command_ref.get(transaction=transaction),
                kind="mission.create",
                request_sha256=request_sha256,
            )
            if existing is not None:
                return MissionHead.model_validate(existing)
            if mission.get(transaction=transaction).exists:
                raise MissionConflict("mission already exists")
            plan_sha256 = canonical_json_sha256(plan.model_dump(mode="json"))
            policy_sha256 = canonical_json_sha256(policy.model_dump(mode="json"))
            fixture = mission_contract.creation_source in {"scripted_fixture", "replay"}
            auto_approve = mission_contract.creation_source == "replay"
            drafts = [
                MissionEventInput(
                    event_type=MissionEventType.PROJECT_CREATED,
                    truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                    authority=MissionAuthority.POLICY_ENGINE,
                    payload={
                        "base_sha": policy.base_sha,
                        "policy_id": policy.policy_id,
                        "policy_revision": policy.revision,
                        "policy_sha256": policy_sha256,
                        "repo_id": policy.repo_id,
                    },
                ),
                MissionEventInput(
                    event_type=MissionEventType.MISSION_CREATED,
                    truth_kind=TruthKind.SERVER_DERIVED,
                    authority=MissionAuthority.MISSION_SERVICE,
                    payload={
                        "creation_source": mission_contract.creation_source,
                        "goal_sha256": canonical_json_sha256(mission_contract.goal),
                        "mission_sha256": canonical_json_sha256(
                            mission_contract.model_dump(mode="json")
                        ),
                        "plan_revision": plan.revision,
                        "status": MissionStatus.PROPOSED.value,
                        "success_criteria_count": len(
                            mission_contract.success_criteria
                        ),
                    },
                ),
                MissionEventInput(
                    event_type=MissionEventType.PLAN_PROPOSED,
                    truth_kind=(
                        TruthKind.SIMULATED_FIXTURE
                        if fixture
                        else TruthKind.SERVER_DERIVED
                    ),
                    authority=(
                        MissionAuthority.SIMULATED_FIXTURE
                        if fixture
                        else MissionAuthority.MISSION_SERVICE
                    ),
                    payload={
                        "plan_revision": plan.revision,
                        "plan_sha256": plan_sha256,
                        "task_count": len(plan.tasks),
                    },
                ),
                MissionEventInput(
                    event_type=MissionEventType.PLAN_VALIDATED,
                    truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                    authority=MissionAuthority.VALIDATOR,
                    payload={
                        "plan_revision": plan.revision,
                        "plan_sha256": plan_sha256,
                        "status": "valid",
                    },
                ),
            ]
            stored_mission = mission_contract
            if auto_approve:
                drafts.append(
                    MissionEventInput(
                        event_type=MissionEventType.PLAN_APPROVED,
                        truth_kind=TruthKind.SIMULATED_FIXTURE,
                        authority=MissionAuthority.SIMULATED_FIXTURE,
                        payload={
                            "operator_label": "scripted-fixture",
                            "plan_revision": plan.revision,
                            "plan_sha256": plan_sha256,
                            "status": "approved",
                        },
                    )
                )
                stored_mission = Mission.model_validate(
                    {
                        **mission_contract.model_dump(mode="json"),
                        "status": MissionStatus.RUNNING,
                    }
                )
            events, head = self._events_for(
                mission_id,
                self.empty_head(mission_id),
                command_id,
                request_sha256,
                tuple(drafts),
                recorded_at,
            )
            values = {
                "schema_version": 1,
                "policy": _policy_summary(policy).model_dump(mode="json"),
                "mission": stored_mission.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "tasks": [item.model_dump(mode="json") for item in plan.tasks],
                "attempts": [],
                "leases": [],
                "publications": [],
                "gates": [],
                "head": head.model_dump(mode="json"),
                "unknowns": list(stored_mission.unknowns),
            }
            snapshot = MissionSnapshot.model_validate(
                {**values, "snapshot_sha256": canonical_json_sha256(values)}
            )
            bundle = _state_bundle(snapshot)
            missing = self._missing_state_writes(transaction, mission, bundle)
            self._write_state_transition(transaction, mission, events, snapshot, missing)
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "mission.create",
                    "request_sha256": request_sha256,
                    "result": head.model_dump(mode="json"),
                },
            )
            return head

        return self._transact(apply)

    @staticmethod
    def _operator_authority(truth_kind: TruthKind) -> MissionAuthority:
        if truth_kind not in {
            TruthKind.HUMAN_ATTESTED,
            TruthKind.SERVER_DERIVED,
            TruthKind.SIMULATED_FIXTURE,
        }:
            raise ValueError(
                "operator commands require human, server-derived, or fixture truth"
            )
        return {
            TruthKind.HUMAN_ATTESTED: MissionAuthority.OPERATOR,
            TruthKind.SERVER_DERIVED: MissionAuthority.MISSION_SERVICE,
            TruthKind.SIMULATED_FIXTURE: MissionAuthority.SIMULATED_FIXTURE,
        }[truth_kind]

    def approve_plan(
        self,
        mission_id: str,
        command_id: str,
        *,
        expected_revision: int,
        expected_head: MissionHead,
        operator_label: str,
        rationale: str | None,
        truth_kind: TruthKind,
        recorded_at: datetime,
    ) -> MissionHead:
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected revision must be a positive integer")
        if not 1 <= len(operator_label) <= 64 or (
            rationale is not None and not 1 <= len(rationale) <= 280
        ):
            raise ValueError("operator attribution must be bounded")
        authority = self._operator_authority(truth_kind)
        request_sha256 = canonical_json_sha256(
            {
                "action": "plan.approve",
                "expected_head": expected_head.model_dump(mode="json"),
                "expected_revision": expected_revision,
                "mission_id": mission_id,
                "operator_label": operator_label,
                "rationale": rationale,
                "truth_kind": truth_kind,
            }
        )
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )

        def apply(transaction: Any) -> MissionHead:
            existing = self._command_result(
                command_ref.get(transaction=transaction),
                kind="plan.approve",
                request_sha256=request_sha256,
            )
            if existing is not None:
                return MissionHead.model_validate(existing)
            current = self._require_expected_head(transaction, mission, expected_head)
            pointer = self._stored_pointer(
                self._materialized_ref(mission).get(transaction=transaction)
            )
            if (
                pointer is None
                or pointer.materialization_pending
                or pointer.root_sha256 is None
                or pointer.committed_head != current
            ):
                raise MissionStateInvalid("approval requires current materialized state")
            snapshot = self._load_state_root(
                mission, pointer.root_sha256, current, transaction=transaction
            )
            if max(
                snapshot.mission.schema_version, snapshot.policy.schema_version
            ) >= 2:
                raise DomainTransitionUnavailable(
                    "cloud schema-2 policy decision persistence is unavailable"
                )
            if (
                snapshot.mission.status
                != (
                    MissionStatus.PROPOSED
                    if expected_revision == 1
                    else MissionStatus.PAUSED
                )
                or snapshot.plan.revision != expected_revision
                or snapshot.mission.plan_revision != expected_revision
            ):
                raise MissionConflict("mission plan cannot be approved now")
            plan_sha256 = canonical_json_sha256(
                snapshot.plan.model_dump(mode="json")
            )
            draft = MissionEventInput(
                event_type=MissionEventType.PLAN_APPROVED,
                truth_kind=truth_kind,
                authority=authority,
                payload={
                    "operator_label": operator_label,
                    "operator_rationale": rationale,
                    "plan_revision": expected_revision,
                    "plan_sha256": plan_sha256,
                    "status": "approved",
                },
            )
            events, head = self._events_for(
                mission_id,
                current,
                command_id,
                request_sha256,
                (draft,),
                recorded_at,
            )
            next_mission = Mission.model_validate(
                {
                    **snapshot.mission.model_dump(mode="json"),
                    "status": transition_mission(
                        snapshot.mission.status, MissionStatus.RUNNING
                    ),
                }
            )
            next_snapshot = _snapshot_with(snapshot, head, mission=next_mission)
            bundle = _state_bundle(next_snapshot)
            missing = self._missing_state_writes(transaction, mission, bundle)
            self._write_state_transition(
                transaction, mission, events, next_snapshot, missing
            )
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "plan.approve",
                    "request_sha256": request_sha256,
                    "result": head.model_dump(mode="json"),
                },
            )
            return head

        return self._transact(apply)

    def refresh_ready(
        self,
        mission_id: str,
        command_id: str,
        *,
        recorded_at: datetime,
    ) -> tuple[str, ...]:
        request_sha256 = canonical_json_sha256(
            {
                "action": "tasks.refresh_ready",
                "mission_id": mission_id,
            }
        )
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )

        def apply(transaction: Any) -> tuple[str, ...]:
            existing = self._command_result(
                command_ref.get(transaction=transaction),
                kind="tasks.refresh_ready",
                request_sha256=request_sha256,
            )
            if existing is not None:
                values = existing.get("task_ids")
                if not isinstance(values, list):
                    raise MissionStateInvalid("stored readiness result is malformed")
                return tuple(values)
            current = self._head_from_snapshot(
                mission_id, mission.get(transaction=transaction)
            )
            if current.seq == 0:
                raise MissionNotFound(mission_id)
            pointer = self._stored_pointer(
                self._materialized_ref(mission).get(transaction=transaction)
            )
            if (
                pointer is None
                or pointer.materialization_pending
                or pointer.root_sha256 is None
                or pointer.committed_head != current
            ):
                raise MissionStateInvalid("readiness requires current materialized state")
            snapshot = self._load_state_root(
                mission, pointer.root_sha256, current, transaction=transaction
            )
            if snapshot.mission.status != MissionStatus.RUNNING:
                raise MissionConflict("mission is not dispatchable")
            if any(item.resolution is None for item in snapshot.gates):
                ready: list[str] = []
                drafts: list[MissionEventInput] = []
                next_tasks = snapshot.tasks
            else:
                tasks = {item.task_id: item for item in snapshot.tasks}
                ready = []
                drafts = []
                for task in sorted(
                    snapshot.tasks, key=lambda item: (-item.priority, item.task_id)
                ):
                    if task.state not in {TaskState.QUEUED, TaskState.RETRYING}:
                        continue
                    if task.retry_at is not None and task.retry_at > recorded_at:
                        continue
                    if not all(
                        tasks[dependency].state == TaskState.DONE
                        for dependency in task.dependencies
                    ):
                        continue
                    next_task = Task.model_validate(
                        {
                            **task.model_dump(mode="json"),
                            "retry_at": None,
                            "state": transition_task(task.state, TaskState.READY),
                        }
                    )
                    tasks[task.task_id] = next_task
                    ready.append(task.task_id)
                    drafts.append(
                        MissionEventInput(
                            event_type=MissionEventType.TASK_READY,
                            truth_kind=TruthKind.SERVER_DERIVED,
                            authority=MissionAuthority.SCHEDULER,
                            payload={"state": "ready", "task_id": task.task_id},
                        )
                    )
                next_tasks = tuple(tasks[key] for key in sorted(tasks))
            events, head = self._events_for(
                mission_id,
                current,
                command_id,
                request_sha256,
                tuple(drafts),
                recorded_at,
            )
            if events:
                next_snapshot = _snapshot_with(snapshot, head, tasks=next_tasks)
                bundle = _state_bundle(next_snapshot)
                missing = self._missing_state_writes(transaction, mission, bundle)
                self._write_state_transition(
                    transaction, mission, events, next_snapshot, missing
                )
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "tasks.refresh_ready",
                    "request_sha256": request_sha256,
                    "result": {"task_ids": ready},
                },
            )
            return tuple(ready)

        return self._transact(apply)

    def append(
        self,
        mission_id: str,
        expected_head: MissionHead,
        command_id: str,
        draft: MissionEventInput,
        *,
        lease: Lease | None = None,
    ) -> MissionEvent:
        if not self._allow_test_bootstrap:
            raise DomainTransitionUnavailable(
                "bare event append has no canonical next aggregate; use an authoritative transition"
            )
        if not isinstance(expected_head, MissionHead) or not isinstance(
            draft, MissionEventInput
        ):
            raise TypeError(
                "append requires validated MissionHead and MissionEventInput values"
            )
        if expected_head.mission_id != mission_id:
            raise MissionConflict("expected head belongs to another mission")
        if lease is not None and (
            not isinstance(lease, Lease) or lease.mission_id != mission_id
        ):
            raise LeaseFenceRejected("lease belongs to another mission")
        if lease is not None and (
            draft.payload.get("task_id") != lease.task_id
            or draft.payload.get("attempt_id") != lease.attempt_id
        ):
            raise LeaseFenceRejected(
                "fenced effect is not bound to the lease task and attempt"
            )

        command_ref_id = _command_ref_id(command_id)
        request_sha256 = canonical_json_sha256(
            {
                "command_id": command_id,
                "draft": draft.model_dump(mode="json"),
                "expected_head": expected_head.model_dump(mode="json"),
                "lease_fence": _lease_fence_request(lease) if lease else None,
                "mission_id": mission_id,
            }
        )
        event_id = f"event_{uuid.uuid4().hex}"
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(command_ref_id)

        def apply(transaction: Any) -> MissionEvent:
            command_snapshot = command_ref.get(transaction=transaction)
            result = self._command_result(
                command_snapshot, kind="event", request_sha256=request_sha256
            )
            if result is not None:
                try:
                    return MissionEvent.model_validate(result)
                except (TypeError, ValueError) as error:
                    raise MissionStateInvalid(
                        "stored command result is malformed"
                    ) from error
            recorded_at = self._clock()

            head_snapshot = mission.get(transaction=transaction)
            materialized_ref = self._materialized_ref(mission)
            materialized_snapshot = materialized_ref.get(transaction=transaction)
            current = self._head_from_snapshot(mission_id, head_snapshot)
            if current != expected_head:
                raise MissionConflict(
                    "expected head does not match the committed mission head"
                )
            if lease is not None:
                self._require_fence(transaction, lease, recorded_at)

            event = _event(
                mission_id,
                current,
                command_id,
                draft,
                event_id=event_id,
                recorded_at=recorded_at,
            )
            event_value = event.model_dump(mode="json")
            event_ref = mission.collection(_EVENTS).document(_sequence_id(event.seq))
            next_head = MissionHead(
                mission_id=mission_id,
                seq=event.seq,
                event_sha256=event.event_sha256,
                event_count=event.seq,
            )
            materialized = _document_data(materialized_snapshot)
            try:
                pointer = (
                    None
                    if materialized is None
                    else MaterializedStatePointer.model_validate(materialized)
                )
            except (TypeError, ValueError) as error:
                raise MissionStateInvalid(
                    "stored materialized pointer is malformed"
                ) from error
            if pointer is None and current.seq != 0:
                raise MissionStateInvalid("committed mission state pointer is missing")
            if pointer is not None and pointer.committed_head != current:
                raise MissionStateInvalid(
                    "materialized pointer does not match the mission head"
                )
            transaction.create(
                event_ref,
                {
                    "schema_version": 1,
                    "seq": event.seq,
                    "event_sha256": event.event_sha256,
                    "value": event_value,
                },
            )
            transaction.set(
                mission,
                {"schema_version": 1, "head": next_head.model_dump(mode="json")},
            )
            transaction.set(
                materialized_ref,
                MaterializedStatePointer(
                    committed_head=next_head,
                    materialization_pending=True,
                    root_sha256=None if pointer is None else pointer.root_sha256,
                    target_root_sha256=None,
                ).model_dump(mode="json"),
            )
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "event",
                    "request_sha256": request_sha256,
                    "result": event_value,
                },
            )
            return event

        return self._transact(apply, initialize_schema=True)

    def tail(
        self, mission_id: str, after_seq: int, limit: int = 256
    ) -> tuple[MissionEvent, ...]:
        if type(after_seq) is not int or after_seq < 0:
            raise ValueError("after_seq must be a non-negative integer")
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("limit must be between 1 and 256")
        self._require_read_schema()
        mission = self._mission(mission_id)
        if not mission.get().exists:
            raise MissionNotFound(mission_id)
        query = (
            mission.collection(_EVENTS)
            .where(filter=firestore.FieldFilter("seq", ">", after_seq))
            .order_by("seq")
            .limit(limit)
        )
        events: list[MissionEvent] = []
        for snapshot in query.stream():
            data = _document_data(snapshot)
            try:
                event = MissionEvent.model_validate(data["value"] if data else None)
            except (KeyError, TypeError, ValueError) as error:
                raise MissionStateInvalid(
                    "stored mission event is malformed"
                ) from error
            if event.mission_id != mission_id:
                raise MissionStateInvalid("stored event belongs to another mission")
            expected_seq = after_seq + len(events) + 1
            if event.seq != expected_seq:
                raise MissionStateInvalid("mission event tail is not contiguous")
            if events and event.previous_event_sha256 != events[-1].event_sha256:
                raise MissionStateInvalid("mission event tail hash link is broken")
            events.append(event)
        return tuple(events)

    @staticmethod
    def _state_record_ref(mission: Any, shard_sha256: str):
        return mission.collection(_STATE_RECORDS).document(shard_sha256)

    @staticmethod
    def _state_root_ref(mission: Any, root_sha256: str):
        return mission.collection(_STATE_ROOTS).document(root_sha256)

    @staticmethod
    def _stored_pointer(snapshot: Any) -> MaterializedStatePointer | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        try:
            return MaterializedStatePointer.model_validate(data)
        except (TypeError, ValueError) as error:
            raise MissionStateInvalid(
                "stored materialized pointer is malformed"
            ) from error

    def _load_state_root(
        self,
        mission: Any,
        root_sha256: str,
        expected_head: MissionHead,
        *,
        transaction: Any | None = None,
    ) -> MissionSnapshot:
        root_data = _document_data(
            self._state_root_ref(mission, root_sha256).get(transaction=transaction)
        )
        if (
            root_data is not None
            and len(canonical_json_bytes(root_data)) > _MAX_STATE_ROOT_BYTES
        ):
            raise MissionStateInvalid("canonical state root exceeds its bound")
        try:
            root = StateRootRecord.model_validate(root_data)
        except (TypeError, ValueError) as error:
            raise MissionStateInvalid("canonical state root is malformed") from error
        if root.root_sha256 != root_sha256 or root.committed_head != expected_head:
            raise MissionStateInvalid("canonical state root binding diverged")
        shards: list[StateShardRecord] = []
        for reference in root.shards:
            data = _document_data(
                self._state_record_ref(mission, reference.shard_sha256).get(
                    transaction=transaction
                )
            )
            if (
                data is not None
                and len(canonical_json_bytes(data)) > _MAX_STATE_DOCUMENT_BYTES
            ):
                raise MissionStateInvalid("canonical state shard exceeds its bound")
            try:
                shard = StateShardRecord.model_validate(data)
            except (TypeError, ValueError) as error:
                raise MissionStateInvalid("canonical state shard is malformed") from error
            if (
                shard.kind != reference.kind
                or shard.shard_sha256 != reference.shard_sha256
                or shard.committed_head != expected_head
            ):
                raise MissionStateInvalid("canonical state shard binding diverged")
            shards.append(shard)
        try:
            return _snapshot_from_bundle(_StateBundle(root=root, shards=tuple(shards)))
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("canonical state shards do not form a snapshot") from error

    def _missing_state_writes(
        self,
        transaction: Any,
        mission: Any,
        bundle: _StateBundle,
    ) -> tuple[tuple[Any, dict[str, Any]], ...]:
        documents = (
            (
                self._state_root_ref(mission, bundle.root.root_sha256),
                bundle.root.model_dump(mode="json"),
            ),
            *(
                (
                    self._state_record_ref(mission, shard.shard_sha256),
                    shard.model_dump(mode="json"),
                )
                for shard in bundle.shards
            ),
        )
        missing = []
        snapshots = tuple(
            (reference, value, reference.get(transaction=transaction))
            for reference, value in documents
        )
        for reference, value, snapshot in snapshots:
            existing = _document_data(snapshot)
            if existing is None:
                missing.append((reference, value))
            elif existing != value:
                raise MissionStateInvalid(
                    "content-addressed state record diverged from its digest"
                )
        return tuple(missing)

    def snapshot(self, mission_id: str) -> MissionSnapshot:
        self._require_read_schema()
        mission = self._mission(mission_id)
        mission_snapshot = mission.get()
        if not mission_snapshot.exists:
            raise MissionNotFound(mission_id)
        current = self._head_from_snapshot(mission_id, mission_snapshot)
        pointer = self._stored_pointer(self._materialized_ref(mission).get())
        if pointer is None:
            raise MissionNotFound(mission_id)
        if pointer.committed_head != current:
            raise MissionStateInvalid(
                "materialized pointer is behind the committed mission head"
            )
        if pointer.materialization_pending or pointer.root_sha256 is None:
            raise MissionStateInvalid("committed mission state is not materialized")
        value = self._load_state_root(mission, pointer.root_sha256, current)
        if value.mission.mission_id != mission_id:
            raise MissionStateInvalid("stored snapshot belongs to another mission")
        return value

    def save_snapshot(self, snapshot: MissionSnapshot) -> MissionSnapshot:
        if not self._allow_test_bootstrap:
            raise DomainTransitionUnavailable(
                "save_snapshot is a bootstrap primitive without an authoritative "
                "domain command"
            )
        if not isinstance(snapshot, MissionSnapshot):
            raise TypeError("save_snapshot requires a validated MissionSnapshot")
        mission_id = snapshot.mission.mission_id
        mission = self._mission(mission_id)
        snapshot_ref = self._materialized_ref(mission)
        bundle = _state_bundle(snapshot)
        pointer_value = MaterializedStatePointer(
            committed_head=snapshot.head,
            materialization_pending=False,
            root_sha256=bundle.root.root_sha256,
            target_root_sha256=bundle.root.root_sha256,
        ).model_dump(mode="json")

        def apply(transaction: Any) -> MissionSnapshot:
            head_snapshot = mission.get(transaction=transaction)
            stored_snapshot = snapshot_ref.get(transaction=transaction)
            current = self._head_from_snapshot(mission_id, head_snapshot)
            if current != snapshot.head:
                raise MissionConflict(
                    "materialized snapshot does not match the committed mission head"
                )
            pointer = self._stored_pointer(stored_snapshot)
            if pointer is not None and pointer.committed_head != current:
                raise MissionStateInvalid(
                    "materialized head marker does not match the mission head"
                )
            missing = self._missing_state_writes(transaction, mission, bundle)
            if pointer is not None and not pointer.materialization_pending:
                if pointer.root_sha256 != bundle.root.root_sha256:
                    raise MissionConflict(
                        "mission head already has another materialized state root"
                    )
                previous = self._load_state_root(
                    mission,
                    pointer.root_sha256,
                    current,
                    transaction=transaction,
                )
                if previous != snapshot:
                    raise MissionConflict(
                        "mission head already has another materialized snapshot"
                    )
                return previous
            for reference, value in missing:
                transaction.create(reference, value)
            transaction.set(snapshot_ref, pointer_value)
            return snapshot

        return self._transact(apply)

    # Scheduler call sites can use either name without another adapter layer.
    materialize = save_snapshot

    def _verified_event_head(
        self, mission_id: str, *, max_events: int
    ) -> MissionHead:
        committed = self.head(mission_id)
        observed = self.empty_head(mission_id)
        while observed.seq < committed.seq:
            if observed.seq >= max_events:
                raise MissionStateInvalid("event verification exceeded its bound")
            events = self.tail(
                mission_id,
                observed.seq,
                min(256, max_events - observed.seq),
            )
            if not events:
                raise MissionStateInvalid("mission event history is not contiguous")
            for event in events:
                if (
                    event.seq != observed.seq + 1
                    or event.previous_event_sha256 != observed.event_sha256
                ):
                    raise MissionStateInvalid(
                        "mission event history hash chain diverged"
                    )
                observed = MissionHead(
                    mission_id=mission_id,
                    seq=event.seq,
                    event_sha256=event.event_sha256,
                    event_count=event.seq,
                )
        if observed != committed:
            raise MissionStateInvalid("mission event history does not reach its head")
        return observed

    def reconcile_materialization(
        self, mission_id: str, *, max_events: int = 10_000
    ) -> MissionSnapshot:
        """Finalize a pending pointer only from immutable canonical state records."""

        if type(max_events) is not int or not 1 <= max_events <= 10_000:
            raise ValueError("max_events must be between one and 10000")
        verified_head = self._verified_event_head(
            mission_id, max_events=max_events
        )
        mission = self._mission(mission_id)
        pointer_ref = self._materialized_ref(mission)

        def apply(transaction: Any) -> MissionSnapshot:
            current = self._head_from_snapshot(
                mission_id, mission.get(transaction=transaction)
            )
            if current != verified_head:
                raise MissionConflict("mission head advanced during reconciliation")
            pointer = self._stored_pointer(pointer_ref.get(transaction=transaction))
            if pointer is None or pointer.committed_head != current:
                raise MissionStateInvalid(
                    "materialized pointer does not match the verified head"
                )
            root_sha256 = (
                pointer.target_root_sha256
                if pointer.materialization_pending
                else pointer.root_sha256
            )
            if root_sha256 is None:
                raise MissionStateInvalid(
                    "pending materialization has no canonical repair root"
                )
            snapshot = self._load_state_root(
                mission,
                root_sha256,
                current,
                transaction=transaction,
            )
            if pointer.materialization_pending:
                transaction.set(
                    pointer_ref,
                    MaterializedStatePointer(
                        committed_head=current,
                        materialization_pending=False,
                        root_sha256=root_sha256,
                        target_root_sha256=root_sha256,
                    ).model_dump(mode="json"),
                )
            return snapshot

        return self._transact(apply)

    def _lease_slot(self, lease: Lease):
        mission = self._mission(lease.mission_id)
        slot_id = f"{lease.plan_revision:020d}--{lease.task_id}"
        return mission.collection(_LEASE_SLOTS).document(slot_id)

    def _stored_lease(self, snapshot: Any) -> Lease | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        try:
            return Lease.model_validate(data["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("stored lease is malformed") from error

    def _require_fence(
        self, transaction: Any, lease: Lease, observed_at: datetime
    ) -> Lease:
        current = self._stored_lease(
            self._lease_slot(lease).get(transaction=transaction)
        )
        if (
            current is None
            or _lease_identity(current) != _lease_identity(lease)
            or current.released_at is not None
            or current.issued_at > observed_at
            or current.expires_at <= observed_at
        ):
            raise LeaseFenceRejected("lease fencing token is not current and active")
        return current

    def assert_fence(self, lease: Lease) -> None:
        if not isinstance(lease, Lease):
            raise TypeError("assert_fence requires a validated Lease")
        self._require_read_schema()
        current = self._stored_lease(self._lease_slot(lease).get())
        when = self._clock()
        if (
            current is None
            or _lease_identity(current) != _lease_identity(lease)
            or current.released_at is not None
            or current.issued_at > when
            or current.expires_at <= when
        ):
            raise LeaseFenceRejected("lease fencing token is not current and active")

    def claim_lease(self, lease: Lease, command_id: str) -> Lease:
        if not isinstance(lease, Lease):
            raise TypeError("claim_lease requires a validated Lease")
        if lease.released_at is not None:
            raise ValueError("a new lease claim cannot already be released")
        mission = self._mission(lease.mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )
        slot_ref = self._lease_slot(lease)
        history_ref = mission.collection(_LEASES).document(lease.lease_id)
        request_sha256 = canonical_json_sha256(
            {
                "action": "lease.claim",
                "command_id": command_id,
                "lease": lease.model_dump(mode="json"),
            }
        )

        def apply(transaction: Any) -> Lease:
            command_snapshot = command_ref.get(transaction=transaction)
            result = self._command_result(
                command_snapshot, kind="lease.claim", request_sha256=request_sha256
            )
            if result is not None:
                return Lease.model_validate(result)
            observed_at = self._clock()
            if (
                lease.issued_at > observed_at
                or lease.heartbeat_at != lease.issued_at
                or lease.expires_at <= observed_at
                or (lease.expires_at - observed_at).total_seconds()
                > self._max_lease_seconds
                or (lease.expires_at - lease.issued_at).total_seconds()
                > self._max_lease_seconds
            ):
                raise LeaseFenceRejected(
                    "lease claim timestamps are not server-current"
                )

            head_snapshot = mission.get(transaction=transaction)
            slot_snapshot = slot_ref.get(transaction=transaction)
            history_snapshot = history_ref.get(transaction=transaction)
            if self._head_from_snapshot(lease.mission_id, head_snapshot).seq == 0:
                raise MissionConflict("cannot claim a lease for an unknown mission")
            current = self._stored_lease(slot_snapshot)
            if (
                current is not None
                and current.released_at is None
                and current.expires_at > observed_at
            ):
                raise LeaseFenceRejected("task already has an active lease")
            expected_token = 1 if current is None else current.fencing_token + 1
            if lease.fencing_token != expected_token:
                raise LeaseFenceRejected(
                    f"lease claim requires fencing token {expected_token}"
                )
            if history_snapshot.exists:
                raise MissionConflict("lease_id was already used")
            value = lease.model_dump(mode="json")
            document = {
                "schema_version": 1,
                "fencing_token": lease.fencing_token,
                "task_id": lease.task_id,
                "value": value,
            }
            transaction.set(slot_ref, document)
            transaction.create(history_ref, document)
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "lease.claim",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return lease

        return self._transact(apply)

    def heartbeat_lease(self, lease: Lease, command_id: str) -> Lease:
        if not isinstance(lease, Lease):
            raise TypeError("heartbeat_lease requires a validated Lease")
        if lease.released_at is not None:
            raise ValueError("a heartbeat cannot release a lease")
        return self._update_lease(lease, command_id, action="lease.heartbeat")

    def release_lease(self, lease: Lease, command_id: str) -> Lease:
        if not isinstance(lease, Lease):
            raise TypeError("release_lease requires a validated Lease")
        if lease.released_at is None:
            raise ValueError("a released lease requires release fields")
        return self._update_lease(lease, command_id, action="lease.release")

    def _update_lease(self, lease: Lease, command_id: str, *, action: str) -> Lease:
        mission = self._mission(lease.mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )
        slot_ref = self._lease_slot(lease)
        history_ref = mission.collection(_LEASES).document(lease.lease_id)
        request_sha256 = canonical_json_sha256(
            {
                "action": action,
                "command_id": command_id,
                "lease": lease.model_dump(mode="json"),
            }
        )

        def apply(transaction: Any) -> Lease:
            command_snapshot = command_ref.get(transaction=transaction)
            result = self._command_result(
                command_snapshot, kind=action, request_sha256=request_sha256
            )
            if result is not None:
                return Lease.model_validate(result)
            observed_at = self._clock()

            slot_snapshot = slot_ref.get(transaction=transaction)
            history_snapshot = history_ref.get(transaction=transaction)
            current = self._stored_lease(slot_snapshot)
            history = self._stored_lease(history_snapshot)
            if (
                current is None
                or history is None
                or _lease_identity(current) != _lease_identity(lease)
                or _lease_identity(history) != _lease_identity(lease)
                or current.released_at is not None
                or current.expires_at <= observed_at
            ):
                raise LeaseFenceRejected("lease fencing token is not current")

            if action == "lease.heartbeat":
                if (
                    lease.heartbeat_at <= current.heartbeat_at
                    or lease.heartbeat_at >= current.expires_at
                    or lease.heartbeat_at > observed_at
                    or lease.expires_at <= observed_at
                    or lease.expires_at < current.expires_at
                    or (lease.expires_at - observed_at).total_seconds()
                    > self._max_lease_seconds
                    or (lease.expires_at - lease.issued_at).total_seconds()
                    > self._max_lease_seconds
                ):
                    raise LeaseFenceRejected(
                        "heartbeat is stale, expired, or outside the TTL bound"
                    )
            else:
                assert lease.released_at is not None
                if (
                    lease.heartbeat_at != current.heartbeat_at
                    or lease.expires_at != current.expires_at
                    or lease.released_at < current.heartbeat_at
                    or lease.released_at > observed_at
                    or lease.released_at >= current.expires_at
                ):
                    raise LeaseFenceRejected("lease release is stale or inconsistent")

            value = lease.model_dump(mode="json")
            document = {
                "schema_version": 1,
                "fencing_token": lease.fencing_token,
                "task_id": lease.task_id,
                "value": value,
            }
            transaction.set(slot_ref, document)
            transaction.set(history_ref, document)
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": action,
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return lease

        return self._transact(apply)

    @staticmethod
    def _session_ref(mission: Any, session_id: str):
        return mission.collection(_EXECUTOR_SESSIONS).document(session_id)

    @staticmethod
    def _outbox_ref(mission: Any, attempt_id: str):
        return mission.collection(_DISPATCH_OUTBOX).document(attempt_id)

    @staticmethod
    def _artifact_capability_ref(mission: Any, capability_id: str):
        return mission.collection(_ARTIFACT_CAPABILITIES).document(capability_id)

    @staticmethod
    def _stored_session(snapshot: Any) -> ExecutorSession | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        try:
            return ExecutorSession.model_validate(data["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("stored executor session is malformed") from error

    @staticmethod
    def _stored_dispatch(snapshot: Any) -> DispatchOutboxRecord | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        try:
            return DispatchOutboxRecord.model_validate(data["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("stored dispatch outbox entry is malformed") from error

    @staticmethod
    def _stored_artifact_grant(snapshot: Any) -> ArtifactFetchGrant | None:
        data = _document_data(snapshot)
        if data is None:
            return None
        try:
            return ArtifactFetchGrant.model_validate(data["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise MissionStateInvalid("stored artifact capability is malformed") from error

    def _require_expected_head(
        self, transaction: Any, mission: Any, expected_head: MissionHead
    ) -> MissionHead:
        if expected_head.mission_id != mission.id:
            raise MissionConflict("expected head belongs to another mission")
        snapshot = mission.get(transaction=transaction)
        if not snapshot.exists:
            raise MissionNotFound(expected_head.mission_id)
        current = self._head_from_snapshot(expected_head.mission_id, snapshot)
        if current != expected_head:
            raise MissionConflict("expected head does not match the committed mission head")
        return current

    @staticmethod
    def _require_session_owner(
        session: ExecutorSession | None,
        *,
        mission_id: str,
        session_id: str,
        executor_id: str,
        worker_id: str | None = None,
    ) -> ExecutorSession:
        if (
            session is None
            or session.mission_id != mission_id
            or session.session_id != session_id
            or session.executor_id != executor_id
            or session.state != ExecutorSessionState.ACTIVE
            or (worker_id is not None and worker_id not in session.worker_ids)
        ):
            raise ExecutorSessionRejected("executor session is unavailable")
        return session

    @staticmethod
    def _session_document(session: ExecutorSession) -> dict[str, object]:
        return {
            "schema_version": 1,
            "executor_id": session.executor_id,
            "state": session.state.value,
            "value": session.model_dump(mode="json"),
        }

    @staticmethod
    def _dispatch_document(dispatch: DispatchOutboxRecord) -> dict[str, object]:
        return {
            "schema_version": 1,
            "executor_id": dispatch.executor_id,
            "worker_id": dispatch.worker_id,
            "state": dispatch.state.value,
            "delivery_count": dispatch.delivery_count,
            "dispatch_sha256": dispatch.dispatch_sha256,
            "value": dispatch.model_dump(mode="json"),
        }

    @staticmethod
    def _artifact_grant_document(grant: ArtifactFetchGrant) -> dict[str, object]:
        return {
            "schema_version": 1,
            "attempt_id": grant.attempt_id,
            "executor_id": grant.executor_id,
            "expires_at": grant.expires_at,
            "consumed_at": grant.consumed_at,
            "value": grant.model_dump(mode="json"),
        }

    def register_executor_session(
        self,
        mission_id: str,
        expected_head: MissionHead,
        command_id: str,
        *,
        principal: str,
        executor_id: str,
        session_id: str,
        worker_ids: tuple[str, ...],
        capabilities: tuple[TaskKind, ...],
    ) -> ExecutorSession:
        request_sha256 = canonical_json_sha256(
            {
                "action": "executor.register",
                "command_id": command_id,
                "expected_head": expected_head.model_dump(mode="json"),
                "executor_id": executor_id,
                "mission_id": mission_id,
                "principal": principal,
                "session_id": session_id,
                "worker_ids": list(worker_ids),
                "capabilities": list(capabilities),
            }
        )
        mission = self._mission(mission_id)
        session_ref = self._session_ref(mission, session_id)
        command_ref = mission.collection(_COMMANDS).document(_command_ref_id(command_id))

        def apply(transaction: Any) -> ExecutorSession:
            result = self._command_result(
                command_ref.get(transaction=transaction),
                kind="executor.register",
                request_sha256=request_sha256,
            )
            if result is not None:
                return ExecutorSession.model_validate(result)
            self._require_expected_head(transaction, mission, expected_head)
            existing = self._stored_session(session_ref.get(transaction=transaction))
            now = self._clock()
            stale_before = now - timedelta(seconds=self._max_lease_seconds)
            # ponytail: full scan of the per-mission session collection; the
            # guard below keeps it at one live session, so it stays bounded.
            for stored in mission.collection(_EXECUTOR_SESSIONS).stream(
                transaction=transaction
            ):
                other = self._stored_session(stored)
                if (
                    other is not None
                    and other.session_id != session_id
                    and other.state == ExecutorSessionState.ACTIVE
                    and other.last_seen_at > stale_before
                ):
                    raise MultiExecutorUnsupported(
                        "cloud multi-executor is unsupported in this release: "
                        "the mission already has a live executor session"
                    )
            if existing is not None:
                if (
                    existing.mission_id != mission_id
                    or existing.executor_id != executor_id
                    or existing.principal != principal
                    or existing.worker_ids != worker_ids
                    or existing.capabilities != capabilities
                    or existing.state != ExecutorSessionState.ACTIVE
                ):
                    raise ExecutorSessionRejected("executor session id was already used")
                value = existing.model_dump(mode="json")
                transaction.create(
                    command_ref,
                    {
                        "schema_version": 1,
                        "kind": "executor.register",
                        "request_sha256": request_sha256,
                        "result": value,
                    },
                )
                return existing
            session = ExecutorSession(
                mission_id=mission_id,
                session_id=session_id,
                executor_id=executor_id,
                principal=principal,
                worker_ids=worker_ids,
                capabilities=capabilities,
                created_at=now,
                last_seen_at=now,
            )
            value = session.model_dump(mode="json")
            transaction.create(session_ref, self._session_document(session))
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "executor.register",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return session

        return self._transact(apply)

    def enqueue_dispatch(
        self,
        dispatch: DispatchOutboxRecord,
        expected_head: MissionHead,
        command_id: str,
    ) -> DispatchOutboxRecord:
        if not isinstance(dispatch, DispatchOutboxRecord):
            raise TypeError("enqueue_dispatch requires a validated dispatch")
        dispatch = DispatchOutboxRecord.model_validate(
            dispatch.model_dump(mode="json")
        )
        if dispatch.state != DispatchOutboxState.PENDING or dispatch.delivery_count != 0:
            raise DispatchStateRejected("new dispatch must be pending and undelivered")
        mission = self._mission(dispatch.mission_id)
        session_ref = self._session_ref(mission, dispatch.session_id)
        outbox_ref = self._outbox_ref(mission, dispatch.attempt_id)
        command_ref = mission.collection(_COMMANDS).document(_command_ref_id(command_id))
        request_sha256 = canonical_json_sha256(
            {
                "action": "dispatch.enqueue",
                "command_id": command_id,
                "dispatch": dispatch.model_dump(mode="json"),
                "expected_head": expected_head.model_dump(mode="json"),
            }
        )

        def apply(transaction: Any) -> DispatchOutboxRecord:
            result = self._command_result(
                command_ref.get(transaction=transaction),
                kind="dispatch.enqueue",
                request_sha256=request_sha256,
            )
            if result is not None:
                return DispatchOutboxRecord.model_validate(result)
            current = self._require_expected_head(transaction, mission, expected_head)
            session = self._require_session_owner(
                self._stored_session(session_ref.get(transaction=transaction)),
                mission_id=dispatch.mission_id,
                session_id=dispatch.session_id,
                executor_id=dispatch.executor_id,
                worker_id=dispatch.worker_id,
            )
            if dispatch.task_kind not in session.capabilities:
                raise ExecutorSessionRejected("executor session lacks the task capability")
            if dispatch.artifact_executor_id != dispatch.executor_id:
                raise ArtifactLocalityUnavailable(
                    "dispatch artifacts belong to another executor"
                )
            if dispatch.creation_seq != current.seq:
                raise MissionConflict("dispatch creation sequence does not match the head")
            self._require_fence(transaction, dispatch.lease, self._clock())
            if self._stored_dispatch(outbox_ref.get(transaction=transaction)) is not None:
                raise DispatchStateRejected("attempt already has a dispatch outbox entry")
            queued = (*session.queued_attempt_ids, dispatch.attempt_id)
            if len(queued) > 64:
                raise DispatchStateRejected("executor session dispatch queue is full")
            updated_session = ExecutorSession.model_validate(
                {**session.model_dump(mode="json"), "queued_attempt_ids": queued}
            )
            value = dispatch.model_dump(mode="json")
            transaction.create(outbox_ref, self._dispatch_document(dispatch))
            transaction.set(session_ref, self._session_document(updated_session))
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "dispatch.enqueue",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return dispatch

        return self._transact(apply)

    def _claim_ready_task(
        self,
        transaction: Any,
        mission: Any,
        session_ref: Any,
        command_ref: Any,
        session: ExecutorSession,
        current: MissionHead,
        command_id: str,
        request_sha256: str,
        worker_id: str,
        recorded_at: datetime,
    ) -> DispatchOutboxRecord | None:
        pointer = self._stored_pointer(
            self._materialized_ref(mission).get(transaction=transaction)
        )
        if (
            pointer is None
            or pointer.materialization_pending
            or pointer.root_sha256 is None
            or pointer.committed_head != current
        ):
            raise MissionStateInvalid("claim requires current materialized state")
        snapshot = self._load_state_root(
            mission, pointer.root_sha256, current, transaction=transaction
        )
        if snapshot.mission.status != MissionStatus.RUNNING or any(
            gate.resolution is None for gate in snapshot.gates
        ):
            return None
        active_leases = tuple(
            item
            for item in snapshot.leases
            if item.released_at is None and item.expires_at > recorded_at
        )
        if len(active_leases) >= snapshot.plan.max_concurrency:
            return None
        if len(snapshot.attempts) >= snapshot.mission.resource_budget.max_attempts:
            raise BudgetExhausted("mission attempt budget is exhausted")
        reserved_seconds = sum(
            (
                (attempt.ended_at or lease.expires_at) - attempt.started_at
            ).total_seconds()
            for attempt in snapshot.attempts
            for lease in snapshot.leases
            if lease.attempt_id == attempt.attempt_id
        )
        remaining_seconds = (
            snapshot.mission.resource_budget.max_worker_seconds - reserved_seconds
        )
        if remaining_seconds <= 0:
            raise BudgetExhausted("mission worker-time budget is exhausted")

        selected: Task | None = None
        accepted_inputs: tuple[PublishedArtifactReferenceV2, ...] = ()
        for task in sorted(
            snapshot.tasks, key=lambda item: (-item.priority, item.task_id)
        ):
            if task.state != TaskState.READY or task.kind not in session.capabilities:
                continue
            if any(
                set(task.write_paths) & set(lease.write_paths)
                for lease in active_leases
            ):
                continue
            if any(
                gate.resolution is None and gate.task_id == task.task_id
                for gate in snapshot.gates
            ):
                continue
            references: list[PublishedArtifactReferenceV2] = []
            locality_available = True
            for requirement in task.inputs:
                matches = tuple(
                    publication
                    for publication in snapshot.publications
                    if publication.plan_revision == snapshot.plan.revision
                    and publication.task_id == requirement.producer_task_id
                    and publication.output_name == requirement.name
                    and publication.kind == requirement.kind
                    and publication.state == PublicationState.ACCEPTED
                )
                if len(matches) != 1 or task.task_id not in matches[0].consumers:
                    raise MissionConflict("accepted task input is unavailable")
                try:
                    reference = matches[0].published_reference()
                except ValueError as error:
                    raise MissionConflict(
                        "accepted task input has no V2 artifact envelope"
                    ) from error
                locality = _document_data(
                    mission.collection(_ARTIFACT_LOCALITY)
                    .document(
                        "publication_"
                        + canonical_json_sha256(reference.model_dump(mode="json"))
                    )
                    .get(transaction=transaction)
                )
                if locality is None:
                    raise ArtifactLocalityUnavailable(
                        "accepted artifact locality is unavailable"
                    )
                if (
                    locality.get("schema_version") != 2
                    or locality.get("executor_id") != session.executor_id
                    or locality.get("reference") != reference.model_dump(mode="json")
                ):
                    locality_available = False
                    break
                references.append(reference)
            if not locality_available:
                continue
            accepted_inputs = tuple(
                sorted(
                    references,
                    key=lambda item: (
                        item.producer_task_id,
                        item.output_name,
                        item.publication_id,
                        item.artifact_envelope_sha256,
                    ),
                )
            )
            selected = task
            break
        if selected is None:
            return None

        number = selected.attempt_count + 1
        token = max(
            (
                item.fencing_token
                for item in snapshot.leases
                if item.task_id == selected.task_id
            ),
            default=0,
        ) + 1
        identity = canonical_json_sha256(
            (
                snapshot.mission.mission_id,
                snapshot.plan.revision,
                selected.task_id,
                number,
                token,
            )
        )
        attempt_id = f"attempt_{identity[:32]}"
        lease_id = f"lease_{identity[:32]}"
        expires_at = recorded_at + timedelta(
            seconds=min(self._max_lease_seconds, int(remaining_seconds))
        )
        if expires_at <= recorded_at:
            raise BudgetExhausted("mission worker-time budget is exhausted")
        target = (
            TaskState.VERIFYING
            if selected.kind == TaskKind.VERIFICATION
            else TaskState.RUNNING
        )
        updated_task = Task.model_validate(
            {
                **selected.model_dump(mode="json"),
                "attempt_count": number,
                "state": transition_task(selected.state, target),
            }
        )
        attempt = Attempt(
            attempt_id=attempt_id,
            mission_id=snapshot.mission.mission_id,
            plan_revision=snapshot.plan.revision,
            task_id=selected.task_id,
            attempt_number=number,
            worker_id=worker_id,
            session_id=session.session_id,
            workspace_id=f"workspace_{identity[:24]}",
            lease_id=lease_id,
            fencing_token=token,
            dispatch_command_id=f"dispatch_{identity[:32]}",
            state=AttemptState.RUNNING,
            started_at=recorded_at,
            input_publications=accepted_inputs,
        )
        lease = Lease(
            lease_id=lease_id,
            mission_id=snapshot.mission.mission_id,
            plan_revision=snapshot.plan.revision,
            task_id=selected.task_id,
            attempt_id=attempt_id,
            owner=worker_id,
            write_paths=selected.write_paths,
            fencing_token=token,
            issued_at=recorded_at,
            heartbeat_at=recorded_at,
            expires_at=expires_at,
        )
        drafts = [
            MissionEventInput(
                event_type=MissionEventType.TASK_LEASED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=MissionAuthority.SCHEDULER,
                payload={
                    "attempt_id": attempt_id,
                    "attempt_number": number,
                    "fencing_token": token,
                    "lease_id": lease_id,
                    "runtime_id": session.executor_id,
                    "task_id": selected.task_id,
                    "worker_id": worker_id,
                },
            ),
            MissionEventInput(
                event_type=MissionEventType.TASK_STARTED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=MissionAuthority.SCHEDULER,
                payload={
                    "attempt_id": attempt_id,
                    "state": target.value,
                    "task_id": selected.task_id,
                    "worker_id": worker_id,
                },
            ),
        ]
        kind_event = {
            TaskKind.ASSEMBLY: MissionEventType.ASSEMBLY_STARTED,
            TaskKind.VERIFICATION: MissionEventType.VERIFICATION_STARTED,
        }.get(selected.kind)
        if kind_event is not None:
            drafts.append(
                MissionEventInput(
                    event_type=kind_event,
                    truth_kind=TruthKind.SERVER_DERIVED,
                    authority=MissionAuthority.SCHEDULER,
                    payload={"attempt_id": attempt_id, "task_id": selected.task_id},
                )
            )
        events, next_head = self._events_for(
            snapshot.mission.mission_id,
            current,
            command_id,
            request_sha256,
            tuple(drafts),
            recorded_at,
        )
        tasks = {item.task_id: item for item in snapshot.tasks}
        tasks[selected.task_id] = updated_task
        next_snapshot = _snapshot_with(
            snapshot,
            next_head,
            tasks=tuple(tasks[key] for key in sorted(tasks)),
            attempts=tuple(sorted((*snapshot.attempts, attempt), key=lambda item: item.attempt_id)),
            leases=tuple(sorted((*snapshot.leases, lease), key=lambda item: item.lease_id)),
        )
        pending = new_dispatch_record(
            mission_id=snapshot.mission.mission_id,
            plan_revision=snapshot.plan.revision,
            task_id=selected.task_id,
            task_kind=selected.kind,
            attempt_id=attempt_id,
            attempt_number=number,
            executor_id=session.executor_id,
            worker_id=worker_id,
            session_id=session.session_id,
            lease=lease,
            accepted_inputs=accepted_inputs,
            artifact_executor_id=session.executor_id,
            creation_seq=next_head.seq,
        )
        delivered = DispatchOutboxRecord.model_validate(
            {
                **pending.model_dump(mode="json"),
                "delivery_count": 1,
                "history": (
                    *pending.history,
                    DispatchTransition(
                        state=DispatchOutboxState.DELIVERED,
                        recorded_at=recorded_at,
                        delivery_count=1,
                    ),
                ),
                "last_delivery_at": recorded_at,
                "state": DispatchOutboxState.DELIVERED,
            }
        )
        outbox_ref = self._outbox_ref(mission, attempt_id)
        history_ref = mission.collection(_LEASES).document(lease_id)
        slot_ref = self._lease_slot(lease)
        if (
            self._stored_dispatch(outbox_ref.get(transaction=transaction)) is not None
            or history_ref.get(transaction=transaction).exists
        ):
            raise MissionConflict("authoritative dispatch identity was already used")
        previous_slot = self._stored_lease(slot_ref.get(transaction=transaction))
        if previous_slot is not None and (
            previous_slot.fencing_token != token - 1
            or previous_slot.released_at is None
        ):
            raise LeaseFenceRejected("stored lease slot diverges from mission state")
        bundle = _state_bundle(next_snapshot)
        missing = self._missing_state_writes(transaction, mission, bundle)
        updated_session = ExecutorSession.model_validate(
            {
                **session.model_dump(mode="json"),
                "last_seen_at": recorded_at,
                "queued_attempt_ids": (*session.queued_attempt_ids, attempt_id),
            }
        )
        lease_document = {
            "schema_version": 1,
            "fencing_token": token,
            "task_id": selected.task_id,
            "value": lease.model_dump(mode="json"),
        }
        self._write_state_transition(
            transaction, mission, events, next_snapshot, missing
        )
        transaction.set(slot_ref, lease_document)
        transaction.create(history_ref, lease_document)
        transaction.create(outbox_ref, self._dispatch_document(delivered))
        transaction.set(session_ref, self._session_document(updated_session))
        transaction.create(
            command_ref,
            {
                "schema_version": 1,
                "kind": "dispatch.claim",
                "request_sha256": request_sha256,
                "result": delivered.model_dump(mode="json"),
            },
        )
        return delivered

    def claim_dispatch(
        self,
        mission_id: str,
        expected_head: MissionHead,
        command_id: str,
        *,
        executor_id: str,
        session_id: str,
        worker_id: str,
    ) -> DispatchOutboxRecord | None:
        mission = self._mission(mission_id)
        session_ref = self._session_ref(mission, session_id)
        command_ref = mission.collection(_COMMANDS).document(_command_ref_id(command_id))
        request_sha256 = canonical_json_sha256(
            {
                "action": "dispatch.claim",
                "command_id": command_id,
                "executor_id": executor_id,
                "expected_head": expected_head.model_dump(mode="json"),
                "mission_id": mission_id,
                "session_id": session_id,
                "worker_id": worker_id,
            }
        )

        def apply(transaction: Any) -> DispatchOutboxRecord | None:
            result = self._command_result(
                command_ref.get(transaction=transaction),
                kind="dispatch.claim",
                request_sha256=request_sha256,
            )
            if result is not None:
                return (
                    None
                    if result.get("no_work") is True
                    else DispatchOutboxRecord.model_validate(result)
                )
            current = self._require_expected_head(
                transaction, mission, expected_head
            )
            session = self._require_session_owner(
                self._stored_session(session_ref.get(transaction=transaction)),
                mission_id=mission_id,
                session_id=session_id,
                executor_id=executor_id,
                worker_id=worker_id,
            )
            now = self._clock()
            selected: DispatchOutboxRecord | None = None
            selected_ref = None
            for attempt_id in session.queued_attempt_ids:
                candidate_ref = self._outbox_ref(mission, attempt_id)
                candidate = self._stored_dispatch(
                    candidate_ref.get(transaction=transaction)
                )
                if candidate is None:
                    raise MissionStateInvalid("executor session references missing dispatch")
                if (
                    candidate.executor_id == executor_id
                    and candidate.worker_id == worker_id
                    and candidate.session_id == session_id
                    and candidate.state
                    in {DispatchOutboxState.PENDING, DispatchOutboxState.DELIVERED}
                ):
                    selected, selected_ref = candidate, candidate_ref
                    break
            if selected is None:
                selected = self._claim_ready_task(
                    transaction,
                    mission,
                    session_ref,
                    command_ref,
                    session,
                    current,
                    command_id,
                    request_sha256,
                    worker_id,
                    now,
                )
                if selected is not None:
                    return selected
                result_value: dict[str, object] = {"no_work": True}
            else:
                if selected.artifact_executor_id != executor_id:
                    raise ArtifactLocalityUnavailable(
                        "dispatch artifact locality is unavailable"
                    )
                self._require_fence(transaction, selected.lease, now)
                if selected.delivery_count >= 64:
                    raise DispatchStateRejected("dispatch delivery limit was reached")
                delivery_count = selected.delivery_count + 1
                selected = DispatchOutboxRecord.model_validate(
                    {
                        **selected.model_dump(mode="json"),
                        "delivery_count": delivery_count,
                        "history": (
                            *selected.history,
                            DispatchTransition(
                                state=DispatchOutboxState.DELIVERED,
                                recorded_at=now,
                                delivery_count=delivery_count,
                            ),
                        ),
                        "last_delivery_at": now,
                        "state": DispatchOutboxState.DELIVERED,
                    }
                )
                assert selected_ref is not None
                transaction.set(selected_ref, self._dispatch_document(selected))
                result_value = selected.model_dump(mode="json")
            updated_session = ExecutorSession.model_validate(
                {**session.model_dump(mode="json"), "last_seen_at": now}
            )
            transaction.set(session_ref, self._session_document(updated_session))
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "dispatch.claim",
                    "request_sha256": request_sha256,
                    "result": result_value,
                },
            )
            return selected

        return self._transact(apply)

    def grant_artifact_fetch(
        self,
        grant: ArtifactFetchGrant,
        expected_head: MissionHead,
    ) -> ArtifactFetchGrant:
        """CAS-create one short-lived capability for one accepted input."""

        if not isinstance(grant, ArtifactFetchGrant):
            raise TypeError("grant_artifact_fetch requires a validated grant")
        mission = self._mission(grant.mission_id)
        grant_ref = self._artifact_capability_ref(mission, grant.capability_id)

        def apply(transaction: Any) -> ArtifactFetchGrant:
            existing = self._stored_artifact_grant(
                grant_ref.get(transaction=transaction)
            )
            if existing is not None:
                requested = grant.model_dump(
                    mode="json", exclude={"consumed_at", "consumed_command_id"}
                )
                stored = existing.model_dump(
                    mode="json", exclude={"consumed_at", "consumed_command_id"}
                )
                if requested != stored:
                    raise ArtifactCapabilityRejected(
                        "artifact capability id was already used"
                    )
                return existing
            self._require_expected_head(transaction, mission, expected_head)
            session = self._require_session_owner(
                self._stored_session(
                    self._session_ref(mission, grant.session_id).get(
                        transaction=transaction
                    )
                ),
                mission_id=grant.mission_id,
                session_id=grant.session_id,
                executor_id=grant.executor_id,
                worker_id=grant.worker_id,
            )
            dispatch = self._stored_dispatch(
                self._outbox_ref(mission, grant.attempt_id).get(
                    transaction=transaction
                )
            )
            if (
                dispatch is None
                or dispatch.state != DispatchOutboxState.DELIVERED
                or dispatch.session_id != session.session_id
                or dispatch.executor_id != grant.executor_id
                or dispatch.worker_id != grant.worker_id
                or dispatch.dispatch_sha256 != grant.dispatch_sha256
                or dispatch.delivery_count != grant.delivery_count
                or dispatch.lease.lease_id != grant.lease_id
                or dispatch.lease.fencing_token != grant.fencing_token
                or dispatch.last_delivery_at != grant.issued_at
                or grant.reference not in dispatch.accepted_inputs
            ):
                raise ArtifactCapabilityRejected(
                    "artifact capability is outside the active dispatch scope"
                )
            now = self._clock()
            self._require_fence(transaction, dispatch.lease, now)
            if (
                grant.issued_at > now
                or grant.expires_at > dispatch.lease.expires_at
                or grant.expires_at <= now
                or (grant.expires_at - grant.issued_at).total_seconds() > 300
            ):
                raise ArtifactCapabilityRejected(
                    "artifact capability expiry is outside the lease scope"
                )
            transaction.create(grant_ref, self._artifact_grant_document(grant))
            return grant

        return self._transact(apply)

    def redeem_artifact_fetch(
        self,
        mission_id: str,
        capability_id: str,
        expected_head: MissionHead,
        command_id: str,
        *,
        executor_id: str,
        session_id: str,
        worker_id: str,
        token_sha256: str,
    ) -> ArtifactFetchGrant:
        """Consume one exact artifact capability; every replay is rejected."""

        mission = self._mission(mission_id)
        grant_ref = self._artifact_capability_ref(mission, capability_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )
        request_sha256 = canonical_json_sha256(
            {
                "action": "artifact.fetch",
                "capability_id": capability_id,
                "command_id": command_id,
                "executor_id": executor_id,
                "expected_head": expected_head.model_dump(mode="json"),
                "mission_id": mission_id,
                "session_id": session_id,
                "token_sha256": token_sha256,
                "worker_id": worker_id,
            }
        )

        def apply(transaction: Any) -> ArtifactFetchGrant:
            result = self._command_result(
                command_ref.get(transaction=transaction),
                kind="artifact.fetch",
                request_sha256=request_sha256,
            )
            if result is not None:
                raise ArtifactCapabilityRejected(
                    "artifact capability replay was rejected"
                )
            self._require_expected_head(transaction, mission, expected_head)
            grant = self._stored_artifact_grant(
                grant_ref.get(transaction=transaction)
            )
            if (
                grant is None
                or grant.capability_id != capability_id
                or grant.mission_id != mission_id
                or grant.executor_id != executor_id
                or grant.session_id != session_id
                or grant.worker_id != worker_id
                or not compare_digest(grant.token_sha256, token_sha256)
                or grant.consumed_at is not None
            ):
                raise ArtifactCapabilityRejected(
                    "artifact capability binding or replay was rejected"
                )
            now = self._clock()
            if grant.issued_at > now or grant.expires_at <= now:
                raise ArtifactCapabilityRejected("artifact capability has expired")
            _session, dispatch, _session_ref, _outbox_ref = self._active_dispatch(
                transaction,
                mission,
                mission_id=mission_id,
                attempt_id=grant.attempt_id,
                executor_id=executor_id,
                session_id=session_id,
                worker_id=worker_id,
                lease_id=grant.lease_id,
                fencing_token=grant.fencing_token,
            )
            self._require_fence(transaction, dispatch.lease, now)
            if (
                dispatch.dispatch_sha256 != grant.dispatch_sha256
                or dispatch.delivery_count != grant.delivery_count
                or grant.reference not in dispatch.accepted_inputs
            ):
                raise ArtifactCapabilityRejected(
                    "artifact capability dispatch scope was rejected"
                )
            consumed = ArtifactFetchGrant.model_validate(
                {
                    **grant.model_dump(mode="json"),
                    "consumed_at": now,
                    "consumed_command_id": command_id,
                }
            )
            value = consumed.model_dump(mode="json")
            transaction.set(grant_ref, self._artifact_grant_document(consumed))
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "artifact.fetch",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return consumed

        return self._transact(apply)

    def _active_dispatch(
        self,
        transaction: Any,
        mission: Any,
        *,
        mission_id: str,
        attempt_id: str,
        executor_id: str,
        session_id: str,
        worker_id: str,
        lease_id: str,
        fencing_token: int,
    ) -> tuple[ExecutorSession, DispatchOutboxRecord, Any, Any]:
        session_ref = self._session_ref(mission, session_id)
        outbox_ref = self._outbox_ref(mission, attempt_id)
        session = self._require_session_owner(
            self._stored_session(session_ref.get(transaction=transaction)),
            mission_id=mission_id,
            session_id=session_id,
            executor_id=executor_id,
            worker_id=worker_id,
        )
        dispatch = self._stored_dispatch(outbox_ref.get(transaction=transaction))
        if (
            dispatch is None
            or dispatch.mission_id != mission_id
            or dispatch.attempt_id != attempt_id
            or dispatch.executor_id != executor_id
            or dispatch.worker_id != worker_id
            or dispatch.session_id != session_id
            or dispatch.state != DispatchOutboxState.DELIVERED
        ):
            raise DispatchStateRejected("active dispatch binding was rejected")
        if (
            dispatch.lease.lease_id != lease_id
            or dispatch.lease.fencing_token != fencing_token
        ):
            raise LeaseFenceRejected("dispatch lease or fencing token is stale")
        if dispatch.artifact_executor_id != executor_id:
            raise ArtifactLocalityUnavailable("dispatch artifact locality is unavailable")
        return session, dispatch, session_ref, outbox_ref

    def heartbeat_dispatch(
        self,
        mission_id: str,
        attempt_id: str,
        expected_head: MissionHead,
        command_id: str,
        *,
        executor_id: str,
        session_id: str,
        worker_id: str,
        lease_id: str,
        fencing_token: int,
    ) -> DispatchOutboxRecord:
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(_command_ref_id(command_id))
        request = {
            "action": "dispatch.heartbeat",
            "attempt_id": attempt_id,
            "command_id": command_id,
            "executor_id": executor_id,
            "expected_head": expected_head.model_dump(mode="json"),
            "fencing_token": fencing_token,
            "lease_id": lease_id,
            "mission_id": mission_id,
            "session_id": session_id,
            "worker_id": worker_id,
        }
        request_sha256 = canonical_json_sha256(request)

        def apply(transaction: Any) -> DispatchOutboxRecord:
            result = self._command_result(
                command_ref.get(transaction=transaction),
                kind="dispatch.heartbeat",
                request_sha256=request_sha256,
            )
            if result is not None:
                return DispatchOutboxRecord.model_validate(result)
            committed = self._require_expected_head(
                transaction, mission, expected_head
            )
            session, dispatch, session_ref, outbox_ref = self._active_dispatch(
                transaction,
                mission,
                mission_id=mission_id,
                attempt_id=attempt_id,
                executor_id=executor_id,
                session_id=session_id,
                worker_id=worker_id,
                lease_id=lease_id,
                fencing_token=fencing_token,
            )
            now = self._clock()
            current = self._require_fence(transaction, dispatch.lease, now)
            maximum = current.issued_at + timedelta(seconds=self._max_lease_seconds)
            expires_at = max(
                current.expires_at,
                min(maximum, now + timedelta(seconds=60)),
            )
            if now <= current.heartbeat_at or expires_at <= now:
                raise LeaseFenceRejected("lease cannot be extended within its TTL bound")
            lease = Lease.model_validate(
                {
                    **current.model_dump(mode="json"),
                    "heartbeat_at": now,
                    "expires_at": expires_at,
                }
            )
            dispatch = DispatchOutboxRecord.model_validate(
                {**dispatch.model_dump(mode="json"), "lease": lease}
            )
            pointer = self._stored_pointer(
                self._materialized_ref(mission).get(transaction=transaction)
            )
            if (
                pointer is None
                or pointer.materialization_pending
                or pointer.root_sha256 is None
                or pointer.committed_head != committed
            ):
                raise MissionStateInvalid(
                    "heartbeat requires current materialized state"
                )
            snapshot = self._load_state_root(
                mission,
                pointer.root_sha256,
                committed,
                transaction=transaction,
            )
            materialized_lease = next(
                (
                    item
                    for item in snapshot.leases
                    if item.lease_id == lease.lease_id
                ),
                None,
            )
            materialized_attempt = next(
                (
                    item
                    for item in snapshot.attempts
                    if item.attempt_id == attempt_id
                ),
                None,
            )
            if (
                materialized_lease is None
                or materialized_attempt is None
                or materialized_attempt.state != AttemptState.RUNNING
                or materialized_attempt.worker_id != worker_id
                or materialized_attempt.fencing_token != fencing_token
                or _lease_identity(materialized_lease)
                != _lease_identity(lease)
                or materialized_lease.released_at is not None
            ):
                raise LeaseFenceRejected(
                    "materialized heartbeat lease binding is stale"
                )
            draft = MissionEventInput(
                event_type=MissionEventType.TASK_HEARTBEAT,
                truth_kind=TruthKind.RUNTIME_OBSERVED,
                authority=MissionAuthority.WORKER_ADAPTER,
                payload={
                    "attempt_id": attempt_id,
                    "fencing_token": fencing_token,
                    "lease_id": lease_id,
                    "task_id": lease.task_id,
                    "worker_id": worker_id,
                },
            )
            events, next_head = self._events_for(
                mission_id,
                committed,
                command_id,
                request_sha256,
                (draft,),
                now,
            )
            leases = {
                item.lease_id: item for item in snapshot.leases
            }
            leases[lease.lease_id] = lease
            next_snapshot = _snapshot_with(
                snapshot,
                next_head,
                leases=tuple(leases[key] for key in sorted(leases)),
            )
            bundle = _state_bundle(next_snapshot)
            missing = self._missing_state_writes(transaction, mission, bundle)
            updated_session = ExecutorSession.model_validate(
                {**session.model_dump(mode="json"), "last_seen_at": now}
            )
            lease_document = {
                "schema_version": 1,
                "fencing_token": lease.fencing_token,
                "task_id": lease.task_id,
                "value": lease.model_dump(mode="json"),
            }
            self._write_state_transition(
                transaction, mission, events, next_snapshot, missing
            )
            transaction.set(self._lease_slot(lease), lease_document)
            transaction.set(
                mission.collection(_LEASES).document(lease.lease_id), lease_document
            )
            transaction.set(outbox_ref, self._dispatch_document(dispatch))
            transaction.set(session_ref, self._session_document(updated_session))
            value = dispatch.model_dump(mode="json")
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "dispatch.heartbeat",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return dispatch

        return self._transact(apply)

    def _finish_dispatch(
        self,
        action: str,
        mission_id: str,
        attempt_id: str,
        expected_head: MissionHead,
        command_id: str,
        *,
        executor_id: str,
        session_id: str,
        worker_id: str,
        lease_id: str,
        fencing_token: int,
        result_code: str,
        artifacts: tuple[ExecutorArtifactObservation, ...] = (),
    ) -> DispatchOutboxRecord:
        if action not in {"dispatch.abandon", "dispatch.complete"}:
            raise ValueError("unsupported dispatch terminal action")
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(_command_ref_id(command_id))
        request_sha256 = canonical_json_sha256(
            {
                "action": action,
                "artifacts": [item.model_dump(mode="json") for item in artifacts],
                "attempt_id": attempt_id,
                "command_id": command_id,
                "executor_id": executor_id,
                "expected_head": expected_head.model_dump(mode="json"),
                "fencing_token": fencing_token,
                "lease_id": lease_id,
                "mission_id": mission_id,
                "result_code": result_code,
                "session_id": session_id,
                "worker_id": worker_id,
            }
        )

        def apply(transaction: Any) -> DispatchOutboxRecord:
            result = self._command_result(
                command_ref.get(transaction=transaction),
                kind=action,
                request_sha256=request_sha256,
            )
            if result is not None:
                return DispatchOutboxRecord.model_validate(result)
            self._require_expected_head(transaction, mission, expected_head)
            session, dispatch, session_ref, outbox_ref = self._active_dispatch(
                transaction,
                mission,
                mission_id=mission_id,
                attempt_id=attempt_id,
                executor_id=executor_id,
                session_id=session_id,
                worker_id=worker_id,
                lease_id=lease_id,
                fencing_token=fencing_token,
            )
            now = self._clock()
            current = self._require_fence(transaction, dispatch.lease, now)
            if any(item.executor_id != executor_id for item in artifacts):
                raise ArtifactLocalityUnavailable(
                    "completion artifact belongs to another executor"
                )
            released = Lease.model_validate(
                {
                    **current.model_dump(mode="json"),
                    "released_at": now,
                    "release_reason": (
                        "completed" if action == "dispatch.complete" else "abandoned"
                    ),
                }
            )
            state = (
                DispatchOutboxState.COMPLETED
                if action == "dispatch.complete"
                else DispatchOutboxState.ABANDONED
            )
            dispatch = DispatchOutboxRecord.model_validate(
                {
                    **dispatch.model_dump(mode="json"),
                    "artifacts": [item.model_dump(mode="json") for item in artifacts],
                    "completed_at": now,
                    "lease": released,
                    "result_code": result_code,
                    "state": state,
                    "history": (
                        *dispatch.history,
                        DispatchTransition(
                            state=state,
                            recorded_at=now,
                            delivery_count=dispatch.delivery_count,
                            code=result_code,
                        ),
                    ),
                }
            )
            queued = tuple(
                item for item in session.queued_attempt_ids if item != attempt_id
            )
            updated_session = ExecutorSession.model_validate(
                {
                    **session.model_dump(mode="json"),
                    "last_seen_at": now,
                    "queued_attempt_ids": queued,
                }
            )
            lease_document = {
                "schema_version": 1,
                "fencing_token": released.fencing_token,
                "task_id": released.task_id,
                "value": released.model_dump(mode="json"),
            }
            transaction.set(self._lease_slot(released), lease_document)
            transaction.set(
                mission.collection(_LEASES).document(released.lease_id), lease_document
            )
            transaction.set(outbox_ref, self._dispatch_document(dispatch))
            transaction.set(session_ref, self._session_document(updated_session))
            value = dispatch.model_dump(mode="json")
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": action,
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return dispatch

        return self._transact(apply)

    def complete_dispatch(
        self,
        mission_id: str,
        attempt_id: str,
        expected_head: MissionHead,
        command_id: str,
        *,
        executor_id: str,
        session_id: str,
        worker_id: str,
        lease_id: str,
        fencing_token: int,
        result: AttemptResult,
        artifacts: tuple[ExecutorArtifactObservation, ...] = (),
        check_receipt: TrustedCheckReceipt | None = None,
        retry_backoff_seconds: int = 1,
    ) -> DispatchOutboxRecord:
        if not isinstance(result, AttemptResult):
            raise TypeError("completion requires a validated AttemptResult")
        if result.succeeded and check_receipt is None:
            raise DomainTransitionUnavailable("trusted check receipt is unavailable")
        bound_artifacts = tuple(
            ExecutorArtifactReference(
                **item.model_dump(mode="json"), executor_id=executor_id
            )
            for item in artifacts
        )
        if (
            type(retry_backoff_seconds) is not int
            or not 0 <= retry_backoff_seconds <= 3_600
        ):
            raise ValueError("retry backoff must be between zero and 3600 seconds")
        mission = self._mission(mission_id)
        command_ref = mission.collection(_COMMANDS).document(
            _command_ref_id(command_id)
        )
        request_sha256 = canonical_json_sha256(
            {
                "action": "dispatch.complete",
                "attempt_id": attempt_id,
                "command_id": command_id,
                "executor_id": executor_id,
                "expected_head": expected_head.model_dump(mode="json"),
                "fencing_token": fencing_token,
                "lease_id": lease_id,
                "mission_id": mission_id,
                "result": result.model_dump(mode="json"),
                "artifacts": [item.model_dump(mode="json") for item in artifacts],
                "check_receipt": (
                    None if check_receipt is None else check_receipt.model_dump(mode="json")
                ),
                "retry_backoff_seconds": retry_backoff_seconds,
                "session_id": session_id,
                "worker_id": worker_id,
            }
        )
        def apply(transaction: Any) -> DispatchOutboxRecord:
            existing = self._command_result(
                command_ref.get(transaction=transaction),
                kind="dispatch.complete",
                request_sha256=request_sha256,
            )
            if existing is not None:
                return DispatchOutboxRecord.model_validate(existing)
            current = self._require_expected_head(transaction, mission, expected_head)
            materialized_ref = self._materialized_ref(mission)
            pointer = self._stored_pointer(
                materialized_ref.get(transaction=transaction)
            )
            if (
                pointer is None
                or pointer.materialization_pending
                or pointer.committed_head != current
                or pointer.root_sha256 is None
            ):
                raise MissionStateInvalid(
                    "authoritative completion requires current materialized state"
                )
            snapshot = self._load_state_root(
                mission,
                pointer.root_sha256,
                current,
                transaction=transaction,
            )
            session, dispatch, session_ref, outbox_ref = self._active_dispatch(
                transaction,
                mission,
                mission_id=mission_id,
                attempt_id=attempt_id,
                executor_id=executor_id,
                session_id=session_id,
                worker_id=worker_id,
                lease_id=lease_id,
                fencing_token=fencing_token,
            )
            now = self._clock()
            self._require_fence(transaction, dispatch.lease, now)
            transition = (
                reduce_successful_completion(
                    snapshot,
                    dispatch,
                    result,
                    bound_artifacts,
                    check_receipt,
                    recorded_at=now,
                )
                if result.succeeded and check_receipt is not None
                else reduce_failed_completion(
                    snapshot,
                    dispatch,
                    result,
                    recorded_at=now,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
            )
            next_head = current
            events: list[MissionEvent] = []
            for index, draft in enumerate(transition.drafts, start=1):
                event = _event(
                    mission_id,
                    next_head,
                    command_id,
                    draft,
                    event_id=f"event_{request_sha256[:24]}_{index:04d}",
                    recorded_at=now,
                )
                events.append(event)
                next_head = MissionHead(
                    mission_id=mission_id,
                    seq=event.seq,
                    event_sha256=event.event_sha256,
                    event_count=event.seq,
                )
            snapshot_values = {
                **snapshot.model_dump(mode="json", exclude={"snapshot_sha256"}),
                "attempts": [
                    item.model_dump(mode="json") for item in transition.attempts
                ],
                "head": next_head.model_dump(mode="json"),
                "leases": [
                    item.model_dump(mode="json") for item in transition.leases
                ],
                "mission": transition.mission.model_dump(mode="json"),
                "publications": [
                    item.model_dump(mode="json") for item in transition.publications
                ],
                "tasks": [item.model_dump(mode="json") for item in transition.tasks],
            }
            next_snapshot = MissionSnapshot.model_validate(
                {
                    **snapshot_values,
                    "snapshot_sha256": canonical_json_sha256(snapshot_values),
                }
            )
            next_bundle = _state_bundle(next_snapshot)
            released = next(
                item
                for item in transition.leases
                if item.lease_id == dispatch.lease.lease_id
            )
            completed = DispatchOutboxRecord.model_validate(
                {
                    **dispatch.model_dump(mode="json"),
                    "completed_at": now,
                    "artifacts": bound_artifacts,
                    "lease": released,
                    "result_code": result.result_code,
                    "state": DispatchOutboxState.COMPLETED,
                    "history": (
                        *dispatch.history,
                        DispatchTransition(
                            state=DispatchOutboxState.COMPLETED,
                            recorded_at=now,
                            delivery_count=dispatch.delivery_count,
                            code=result.result_code,
                        ),
                    ),
                }
            )
            updated_session = ExecutorSession.model_validate(
                {
                    **session.model_dump(mode="json"),
                    "last_seen_at": now,
                    "queued_attempt_ids": tuple(
                        value
                        for value in session.queued_attempt_ids
                        if value != attempt_id
                    ),
                }
            )
            lease_document = {
                "schema_version": 1,
                "fencing_token": released.fencing_token,
                "task_id": released.task_id,
                "value": released.model_dump(mode="json"),
            }
            missing_state_writes = self._missing_state_writes(
                transaction, mission, next_bundle
            )
            materialized_document = MaterializedStatePointer(
                committed_head=next_head,
                materialization_pending=False,
                root_sha256=next_bundle.root.root_sha256,
                target_root_sha256=next_bundle.root.root_sha256,
            ).model_dump(mode="json")
            for reference, value in missing_state_writes:
                transaction.create(reference, value)
            for event in events:
                transaction.create(
                    mission.collection(_EVENTS).document(_sequence_id(event.seq)),
                    {
                        "schema_version": 1,
                        "seq": event.seq,
                        "event_sha256": event.event_sha256,
                        "value": event.model_dump(mode="json"),
                    },
                )
            for artifact in bound_artifacts:
                transaction.create(
                    mission.collection(_ARTIFACT_LOCALITY).document(
                        "source_" + canonical_json_sha256(
                            artifact.reference.model_dump(mode="json")
                        )
                    ),
                    {
                        "schema_version": 1,
                        "attempt_id": attempt_id,
                        "executor_id": executor_id,
                        "reference": artifact.reference.model_dump(mode="json"),
                        "byte_count": artifact.byte_count,
                        "spool": artifact.spool,
                    },
                )
            for publication in (
                item
                for item in transition.publications
                if item.attempt_id == attempt_id
            ):
                try:
                    publication_reference = publication.published_reference()
                except ValueError as error:
                    raise MissionConflict(
                        "accepted publication has no V2 artifact envelope"
                    ) from error
                source = next(
                    item
                    for item in bound_artifacts
                    if item.reference.kind == publication.kind
                    and item.reference.id == publication_reference.artifact_id
                    and item.reference.sha256 == publication.sha256
                )
                transaction.create(
                    mission.collection(_ARTIFACT_LOCALITY).document(
                        "publication_"
                        + canonical_json_sha256(
                            publication_reference.model_dump(mode="json")
                        )
                    ),
                    {
                        "schema_version": 2,
                        "attempt_id": attempt_id,
                        "executor_id": executor_id,
                        "reference": publication_reference.model_dump(mode="json"),
                        "source_reference": source.reference.model_dump(mode="json"),
                        "artifact_envelope_sha256": (
                            publication_reference.artifact_envelope_sha256
                        ),
                        "byte_count": source.byte_count,
                        "spool": source.spool,
                    },
                )
            transaction.set(
                mission,
                {"schema_version": 1, "head": next_head.model_dump(mode="json")},
            )
            transaction.set(materialized_ref, materialized_document)
            transaction.set(self._lease_slot(released), lease_document)
            transaction.set(
                mission.collection(_LEASES).document(released.lease_id), lease_document
            )
            transaction.set(outbox_ref, self._dispatch_document(completed))
            transaction.set(session_ref, self._session_document(updated_session))
            value = completed.model_dump(mode="json")
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "dispatch.complete",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return completed

        return self._transact(apply)

    def abandon_dispatch(
        self,
        mission_id: str,
        attempt_id: str,
        expected_head: MissionHead,
        command_id: str,
        **values: Any,
    ) -> DispatchOutboxRecord:
        return self._finish_dispatch(
            "dispatch.abandon",
            mission_id,
            attempt_id,
            expected_head,
            command_id,
            **values,
        )

    def block_artifact_locality(
        self,
        mission_id: str,
        attempt_id: str,
        expected_head: MissionHead,
        command_id: str,
        *,
        executor_id: str,
    ) -> DispatchOutboxRecord:
        mission = self._mission(mission_id)
        outbox_ref = self._outbox_ref(mission, attempt_id)
        command_ref = mission.collection(_COMMANDS).document(_command_ref_id(command_id))
        request_sha256 = canonical_json_sha256(
            {
                "action": "dispatch.block_locality",
                "attempt_id": attempt_id,
                "command_id": command_id,
                "executor_id": executor_id,
                "expected_head": expected_head.model_dump(mode="json"),
                "mission_id": mission_id,
            }
        )

        def apply(transaction: Any) -> DispatchOutboxRecord:
            result = self._command_result(
                command_ref.get(transaction=transaction),
                kind="dispatch.block_locality",
                request_sha256=request_sha256,
            )
            if result is not None:
                return DispatchOutboxRecord.model_validate(result)
            self._require_expected_head(transaction, mission, expected_head)
            dispatch = self._stored_dispatch(outbox_ref.get(transaction=transaction))
            if (
                dispatch is None
                or dispatch.executor_id != executor_id
                or dispatch.state
                not in {DispatchOutboxState.PENDING, DispatchOutboxState.DELIVERED}
            ):
                raise DispatchStateRejected("dispatch cannot enter locality blocker")
            session_ref = self._session_ref(mission, dispatch.session_id)
            session = self._stored_session(session_ref.get(transaction=transaction))
            if session is None:
                raise MissionStateInvalid("dispatch executor session is missing")
            blocked = DispatchOutboxRecord.model_validate(
                {
                    **dispatch.model_dump(mode="json"),
                    "blocker_code": "artifact_locality_unavailable",
                    "state": DispatchOutboxState.BLOCKED,
                    "history": (
                        *dispatch.history,
                        DispatchTransition(
                            state=DispatchOutboxState.BLOCKED,
                            recorded_at=self._clock(),
                            delivery_count=dispatch.delivery_count,
                            code="artifact_locality_unavailable",
                        ),
                    ),
                }
            )
            updated_session = ExecutorSession.model_validate(
                {
                    **session.model_dump(mode="json"),
                    "queued_attempt_ids": tuple(
                        item
                        for item in session.queued_attempt_ids
                        if item != attempt_id
                    ),
                }
            )
            transaction.set(outbox_ref, self._dispatch_document(blocked))
            transaction.set(session_ref, self._session_document(updated_session))
            value = blocked.model_dump(mode="json")
            transaction.create(
                command_ref,
                {
                    "schema_version": 1,
                    "kind": "dispatch.block_locality",
                    "request_sha256": request_sha256,
                    "result": value,
                },
            )
            return blocked

        return self._transact(apply)


__all__ = [
    "ArtifactCapabilityRejected",
    "ArtifactLocalityUnavailable",
    "DispatchStateRejected",
    "DomainTransitionUnavailable",
    "ExecutorSessionRejected",
    "FirestoreMissionError",
    "FirestoreMissionStore",
    "LeaseFenceRejected",
    "MissionConflict",
    "MissionStateInvalid",
    "MultiExecutorUnsupported",
]
