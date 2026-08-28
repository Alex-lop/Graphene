from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from ..artifact_envelope import ArtifactEnvelopeV2
from ..hashing import canonical_json_sha256
from ..core_models import (
    BoundedText,
    FrozenModel,
    Identifier,
    IdempotencyKey,
    Sha256,
    UtcDateTime,
)
from .evidence import TrustedCheckReceipt
from .mission_models import (
    MAX_ARTIFACT_BYTES,
    ArtifactInputReference,
    AttemptResult,
    EvidenceReference,
    Lease,
    MissionHead,
    TaskKind,
    artifact_input_reference_key,
)


PrincipalSubject = Annotated[str, Field(min_length=1, max_length=256)]


class FirestoreNamespaceSchema(FrozenModel):
    schema_version: Literal[1] = 1
    current_version: int = Field(ge=1, le=32)
    min_reader_version: int = Field(ge=1, le=32)
    min_writer_version: int = Field(ge=1, le=32)

    @model_validator(mode="after")
    def versions_are_ordered(self) -> FirestoreNamespaceSchema:
        if max(self.min_reader_version, self.min_writer_version) > self.current_version:
            raise ValueError("namespace schema compatibility versions are reversed")
        return self


class StateShardKind(StrEnum):
    SUMMARY = "summary"
    TASKS = "tasks"
    ATTEMPTS_LEASES = "attempts_leases"
    PUBLICATIONS_GATES = "publications_gates"
    RESULT = "result"


class StateShardRecord(FrozenModel):
    schema_version: Literal[2] = 2
    kind: StateShardKind
    committed_head: MissionHead
    value: dict[str, Any]
    shard_sha256: Sha256

    @model_validator(mode="after")
    def digest_is_canonical(self) -> StateShardRecord:
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"shard_sha256"})
        )
        if self.shard_sha256 != expected:
            raise ValueError("state shard digest does not match")
        return self


class StateShardReference(FrozenModel):
    kind: StateShardKind
    shard_sha256: Sha256


class StateRootRecord(FrozenModel):
    schema_version: Literal[2] = 2
    committed_head: MissionHead
    snapshot_sha256: Sha256
    shards: tuple[StateShardReference, ...] = Field(min_length=5, max_length=5)
    root_sha256: Sha256

    @model_validator(mode="after")
    def root_is_canonical(self) -> StateRootRecord:
        kinds = tuple(item.kind for item in self.shards)
        if kinds != tuple(StateShardKind):
            raise ValueError("state root requires every canonical shard in order")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"root_sha256"})
        )
        if self.root_sha256 != expected:
            raise ValueError("state root digest does not match")
        return self


class MaterializedStatePointer(FrozenModel):
    schema_version: Literal[2] = 2
    committed_head: MissionHead
    materialization_pending: bool
    root_sha256: Sha256 | None = None
    target_root_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def target_matches_state(self) -> MaterializedStatePointer:
        if self.materialization_pending:
            return self
        if self.root_sha256 is None or self.target_root_sha256 not in {
            None,
            self.root_sha256,
        }:
            raise ValueError("finalized materialization requires one root")
        return self


class AuthenticatedExecutor(FrozenModel):
    """Identity established by the server-side IAM/OIDC verifier."""

    principal: PrincipalSubject
    executor_id: Identifier


class ExecutorSessionState(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class ExecutorSession(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    session_id: Identifier
    executor_id: Identifier
    principal: PrincipalSubject
    worker_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1)
    capabilities: tuple[TaskKind, ...] = Field(min_length=1, max_length=1)
    state: ExecutorSessionState = ExecutorSessionState.ACTIVE
    created_at: UtcDateTime
    last_seen_at: UtcDateTime
    queued_attempt_ids: tuple[Identifier, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def values_are_canonical(self) -> ExecutorSession:
        if self.worker_ids != tuple(sorted(set(self.worker_ids))):
            raise ValueError("worker_ids must be sorted and unique")
        if self.capabilities != (TaskKind.WORK,):
            raise ValueError("the narrow cloud executor supports WORK only")
        if len(self.queued_attempt_ids) != len(set(self.queued_attempt_ids)):
            raise ValueError("queued_attempt_ids must be unique")
        if self.last_seen_at < self.created_at:
            raise ValueError("session timestamps are not monotonic")
        return self


class DispatchOutboxState(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


class ExecutorArtifactObservation(FrozenModel):
    reference: EvidenceReference
    byte_count: int = Field(ge=0, le=MAX_ARTIFACT_BYTES)
    spool: Literal["executor_private"] = "executor_private"
    envelope: ArtifactEnvelopeV2 | None = None

    @model_validator(mode="after")
    def envelope_matches_reference(self) -> ExecutorArtifactObservation:
        if self.envelope is not None and (
            self.envelope.artifact_kind != self.reference.kind
            or self.envelope.content_sha256 != self.reference.sha256
            or self.envelope.byte_count != self.byte_count
        ):
            raise ValueError("artifact envelope does not match the observed bytes")
        return self


class ExecutorArtifactReference(ExecutorArtifactObservation):
    executor_id: Identifier


class ArtifactFetchScope(FrozenModel):
    schema_version: Literal[1] = 1
    capability_id: Identifier
    mission_id: Identifier
    dispatch_sha256: Sha256
    delivery_count: int = Field(ge=1, le=64)
    attempt_id: Identifier
    executor_id: Identifier
    session_id: Identifier
    worker_id: Identifier
    lease_id: Identifier
    fencing_token: int = Field(ge=1)
    reference: ArtifactInputReference
    issued_at: UtcDateTime
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def expiry_is_bounded(self) -> ArtifactFetchScope:
        if self.expires_at <= self.issued_at:
            raise ValueError("artifact fetch capability must expire after issuance")
        return self


class ArtifactFetchGrant(ArtifactFetchScope):
    """Server-side capability state. Raw bearer material is never persisted."""

    token_sha256: Sha256
    consumed_at: UtcDateTime | None = None
    consumed_command_id: IdempotencyKey | None = None

    @model_validator(mode="after")
    def consumption_is_exact(self) -> ArtifactFetchGrant:
        if (self.consumed_at is None) != (self.consumed_command_id is None):
            raise ValueError("artifact fetch consumption fields must appear together")
        return self


class ArtifactFetchCapability(ArtifactFetchScope):
    """Single-input bearer capability returned only to its authenticated executor."""

    token: Sha256


class DispatchTransition(FrozenModel):
    state: DispatchOutboxState
    recorded_at: UtcDateTime
    delivery_count: int = Field(ge=0, le=64)
    code: Identifier | None = None


def dispatch_digest_payload(value: DispatchOutboxRecord) -> dict[str, object]:
    return {
        "accepted_inputs": [item.model_dump(mode="json") for item in value.accepted_inputs],
        "artifact_executor_id": value.artifact_executor_id,
        "attempt_id": value.attempt_id,
        "attempt_number": value.attempt_number,
        "creation_seq": value.creation_seq,
        "executor_id": value.executor_id,
        "lease_fence": {
            "capability": value.lease.capability,
            "fencing_token": value.lease.fencing_token,
            "issued_at": value.lease.issued_at.isoformat(),
            "lease_id": value.lease.lease_id,
            "write_paths": list(value.lease.write_paths),
        },
        "mission_id": value.mission_id,
        "plan_revision": value.plan_revision,
        "session_id": value.session_id,
        "task_id": value.task_id,
        "task_kind": value.task_kind,
        "worker_id": value.worker_id,
    }


class DispatchOutboxRecord(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    task_id: Identifier
    task_kind: TaskKind
    attempt_id: Identifier
    attempt_number: int = Field(ge=1, le=20)
    executor_id: Identifier
    worker_id: Identifier
    session_id: Identifier
    lease: Lease
    accepted_inputs: tuple[ArtifactInputReference, ...] = Field(
        default=(), max_length=64
    )
    artifact_executor_id: Identifier
    creation_seq: int = Field(ge=1)
    dispatch_sha256: Sha256
    delivery_count: int = Field(default=0, ge=0, le=64)
    state: DispatchOutboxState = DispatchOutboxState.PENDING
    last_delivery_at: UtcDateTime | None = None
    completed_at: UtcDateTime | None = None
    result_code: Identifier | None = None
    blocker_code: Literal["artifact_locality_unavailable"] | None = None
    artifacts: tuple[ExecutorArtifactReference, ...] = Field(default=(), max_length=64)
    history: tuple[DispatchTransition, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def bindings_are_exact(self) -> DispatchOutboxRecord:
        if (
            self.lease.mission_id != self.mission_id
            or self.lease.plan_revision != self.plan_revision
            or self.lease.task_id != self.task_id
            or self.lease.attempt_id != self.attempt_id
            or self.lease.owner != self.worker_id
        ):
            raise ValueError("dispatch lease bindings do not match")
        inputs = tuple(
            artifact_input_reference_key(item) for item in self.accepted_inputs
        )
        if inputs != tuple(sorted(set(inputs))):
            raise ValueError("accepted_inputs must be sorted and unique")
        if self.dispatch_sha256 != canonical_json_sha256(dispatch_digest_payload(self)):
            raise ValueError("dispatch digest does not match")
        terminal = self.state in {
            DispatchOutboxState.COMPLETED,
            DispatchOutboxState.ABANDONED,
        }
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal dispatches require completed_at")
        if self.state == DispatchOutboxState.BLOCKED:
            if self.blocker_code != "artifact_locality_unavailable":
                raise ValueError("blocked dispatch requires an artifact locality blocker")
        elif self.blocker_code is not None:
            raise ValueError("only blocked dispatches may have a blocker")
        artifact_keys = tuple(
            (item.reference.kind, item.reference.id, item.reference.sha256)
            for item in self.artifacts
        )
        if artifact_keys != tuple(sorted(set(artifact_keys))):
            raise ValueError("artifacts must be sorted and unique")
        if any(item.executor_id != self.artifact_executor_id for item in self.artifacts):
            raise ValueError("artifact references belong to another executor")
        if (
            self.history[0].state != DispatchOutboxState.PENDING
            or self.history[0].delivery_count != 0
            or self.history[-1].state != self.state
            or self.history[-1].delivery_count != self.delivery_count
            or any(
                right.recorded_at < left.recorded_at
                for left, right in zip(self.history, self.history[1:], strict=False)
            )
        ):
            raise ValueError("dispatch transition history is inconsistent")
        return self


class CoordinatorRequest(FrozenModel):
    command_id: IdempotencyKey
    expected_head: MissionHead
    session_id: Identifier
    worker_id: Identifier


class RegisterExecutorRequest(FrozenModel):
    command_id: IdempotencyKey
    expected_head: MissionHead
    session_id: Identifier
    worker_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1)
    capabilities: tuple[TaskKind, ...] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def values_are_canonical(self) -> RegisterExecutorRequest:
        if self.worker_ids != tuple(sorted(set(self.worker_ids))):
            raise ValueError("worker_ids must be sorted and unique")
        if self.capabilities != (TaskKind.WORK,):
            raise ValueError("the narrow cloud executor supports WORK only")
        return self


class ClaimRequest(CoordinatorRequest):
    pass


class ArtifactFetchRequest(CoordinatorRequest):
    token: Sha256


class AttemptRequest(CoordinatorRequest):
    lease_id: Identifier
    fencing_token: int = Field(ge=1)


class HeartbeatRequest(AttemptRequest):
    pass


class CompleteRequest(AttemptRequest):
    result: AttemptResult
    # The executor reports bytes it observed in its private spool.  The
    # coordinator binds the authenticated executor identity server-side before
    # persisting an ExecutorArtifactReference.
    artifacts: tuple[ExecutorArtifactObservation, ...] = Field(
        default=(), max_length=64
    )
    check_receipt: TrustedCheckReceipt | None = None

    @model_validator(mode="after")
    def success_metadata_is_exact(self) -> CompleteRequest:
        artifacts = tuple(item.reference for item in self.artifacts)
        if self.result.succeeded:
            if self.check_receipt is None or artifacts != self.result.evidence_refs:
                raise ValueError(
                    "successful completion requires ordered executor-local evidence"
                )
        elif self.artifacts or self.check_receipt is not None:
            raise ValueError("failed completion cannot publish executor artifacts")
        return self


class AbandonRequest(AttemptRequest):
    reason_code: Identifier


class CoordinatorResult(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    head: MissionHead
    authoritative_completion: bool = False
    artifact_capabilities: tuple[ArtifactFetchCapability, ...] = Field(
        default=(), max_length=64
    )
    dispatch: DispatchOutboxRecord | None = None
    session: ExecutorSession | None = None
    status: Literal["registered", "delivered", "heartbeat", "completed", "abandoned", "no_work"]


class CoordinatorError(FrozenModel):
    code: Identifier
    detail: BoundedText


def new_dispatch_record(
    *,
    mission_id: str,
    plan_revision: int,
    task_id: str,
    task_kind: TaskKind,
    attempt_id: str,
    attempt_number: int,
    executor_id: str,
    worker_id: str,
    session_id: str,
    lease: Lease,
    accepted_inputs: tuple[ArtifactInputReference, ...],
    artifact_executor_id: str,
    creation_seq: int,
) -> DispatchOutboxRecord:
    values = {
        "mission_id": mission_id,
        "plan_revision": plan_revision,
        "task_id": task_id,
        "task_kind": task_kind,
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "executor_id": executor_id,
        "worker_id": worker_id,
        "session_id": session_id,
        "lease": lease,
        "accepted_inputs": accepted_inputs,
        "artifact_executor_id": artifact_executor_id,
        "creation_seq": creation_seq,
    }
    provisional = DispatchOutboxRecord.model_construct(
        **values,
        schema_version=1,
        dispatch_sha256="0" * 64,
        delivery_count=0,
        state=DispatchOutboxState.PENDING,
        last_delivery_at=None,
        completed_at=None,
        result_code=None,
        blocker_code=None,
        artifacts=(),
        history=(
            DispatchTransition(
                state=DispatchOutboxState.PENDING,
                recorded_at=lease.issued_at,
                delivery_count=0,
            ),
        ),
    )
    return DispatchOutboxRecord.model_validate(
        {
            **values,
            "dispatch_sha256": canonical_json_sha256(
                dispatch_digest_payload(provisional)
            ),
            "history": provisional.history,
        }
    )


__all__ = [
    "AbandonRequest",
    "ArtifactFetchCapability",
    "ArtifactFetchGrant",
    "ArtifactFetchRequest",
    "ArtifactFetchScope",
    "AuthenticatedExecutor",
    "ClaimRequest",
    "CompleteRequest",
    "CoordinatorError",
    "CoordinatorResult",
    "DispatchOutboxRecord",
    "DispatchOutboxState",
    "DispatchTransition",
    "ExecutorArtifactReference",
    "ExecutorSession",
    "ExecutorSessionState",
    "FirestoreNamespaceSchema",
    "HeartbeatRequest",
    "RegisterExecutorRequest",
    "MaterializedStatePointer",
    "StateRootRecord",
    "StateShardKind",
    "StateShardRecord",
    "StateShardReference",
    "new_dispatch_record",
]
