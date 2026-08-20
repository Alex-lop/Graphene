from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..models import (
    AgentProfileId,
    ContextBrief,
    ContextInjectionReceipt,
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    GitSha,
    HandoffDecision,
    HeadCheckpoint,
    HumanDecision,
    Identifier,
    LineageAuthority,
    LineageEventType,
    LineageRunState,
    MemoryDecisionValue,
    MemoryRevision,
    MemoryState,
    Sha256,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from .reducer import ProjectionError, reduce_events
from .store import EvidenceInvalid, LineageConflict


class PromotionStore(Protocol):
    def append(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        idempotency_key: str,
        draft: EventInput,
    ) -> Event: ...

    def tail(self, run_id: str, after_seq: int, limit: int) -> tuple[Event, ...]: ...

    def verify(self, run_id: str) -> VerifiedHead | EvidenceInvalidState: ...


class PromotionArtifacts(Protocol):
    def __call__(
        self, kind: EvidenceKind, value: Mapping[str, Any]
    ) -> EvidenceReference: ...

    def resolve(self, kind: str, artifact_id: str) -> bytes | None: ...


ArtifactRecorder = Callable[[EvidenceKind, Mapping[str, Any]], EvidenceReference]


class CheckpointRecorder(Protocol):
    def __call__(self, checkpoint: HeadCheckpoint) -> None: ...

    def read(self, run_id: str) -> tuple[HeadCheckpoint, ...]: ...


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PreparedPromotionCandidate(_Frozen):
    schema_version: Literal[2] = 2
    run_id: Identifier
    expected_head: VerifiedHead
    repo_id: Identifier
    base_sha: GitSha
    agent_profile_id: AgentProfileId
    policy_revision: int = Field(ge=1)
    candidate_id: Identifier
    candidate_sha256: Sha256
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    changeset_sha256: Sha256
    test_receipt_sha256: Sha256
    brief_sha256: Sha256
    decision_sha256: Sha256
    memory_sha256: Sha256
    candidate_reference: EvidenceReference
    changeset_reference: EvidenceReference
    test_reference: EvidenceReference
    brief_reference: EvidenceReference
    decision_reference: EvidenceReference
    memory_reference: EvidenceReference

    @model_validator(mode="after")
    def bindings_are_exact(self) -> PreparedPromotionCandidate:
        expected = (
            (
                self.candidate_reference,
                EvidenceKind.EVIDENCE_BLOB,
                self.candidate_sha256,
            ),
            (self.changeset_reference, EvidenceKind.CHANGESET, self.changeset_sha256),
            (self.test_reference, EvidenceKind.TEST_RECEIPT, self.test_receipt_sha256),
            (self.brief_reference, EvidenceKind.CONTEXT_BRIEF, self.brief_sha256),
            (
                self.decision_reference,
                EvidenceKind.HANDOFF_DECISION,
                self.decision_sha256,
            ),
            (self.memory_reference, EvidenceKind.MEMORY_REVISION, self.memory_sha256),
        )
        if (
            self.expected_head.run_id != self.run_id
            or self.expected_head.seq == 0
            or any(
                reference.kind != kind or reference.sha256 != digest
                for reference, kind, digest in expected
            )
            or len({reference.id for reference, _, _ in expected}) != len(expected)
        ):
            raise ValueError("promotion artifact and head bindings do not match")
        return self


class PromotionRequest(PreparedPromotionCandidate):
    human_approval: HumanDecision
    operator_label: str | None = Field(default=None, min_length=1, max_length=64)
    operator_rationale: str | None = Field(default=None, max_length=280)

    @model_validator(mode="after")
    def bindings_are_exact_and_decided(self) -> PromotionRequest:
        if (
            self.human_approval.actor not in {"human", "simulated_fixture"}
            or self.human_approval.value != MemoryDecisionValue.APPROVE
            or self.human_approval.purpose != "promotion"
            or self.human_approval.bound_digest != self.candidate_patch_sha256
        ):
            raise ValueError(
                "promotion requires exact human approval or explicit simulated fixture"
            )
        if self.operator_rationale is not None and self.operator_label is None:
            raise ValueError("promotion rationale requires an operator label")
        return self


class PromotionRetestRequest(_Frozen):
    schema_version: Literal[2] = 2
    run_id: Identifier
    approval_head: VerifiedHead
    approval_event_id: Identifier
    approval_event_sha256: Sha256
    repo_id: Identifier
    base_sha: GitSha
    agent_profile_id: AgentProfileId
    policy_revision: int = Field(ge=1)
    candidate_id: Identifier
    candidate_sha256: Sha256
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    changeset_sha256: Sha256
    test_receipt_sha256: Sha256
    brief_sha256: Sha256
    decision_sha256: Sha256
    memory_sha256: Sha256
    human_approval_sha256: Sha256
    artifact_references: tuple[EvidenceReference, ...]


class PromotionRetestResult(_Frozen):
    """Narrow authoritative observations; the coordinator owns the receipt proof."""

    authoritative_test_receipt_sha256: Sha256
    retest_base_sha: GitSha
    passed: bool = Field(strict=True)
    timed_out: bool = Field(strict=True)


class PromotionReceiptV2(_Frozen):
    schema_version: Literal[2] = 2
    receipt_id: Identifier
    run_id: Identifier
    approval_head: VerifiedHead
    approval_event_id: Identifier
    approval_event_sha256: Sha256
    repo_id: Identifier
    base_sha: GitSha
    agent_profile_id: AgentProfileId
    policy_revision: int = Field(ge=1)
    candidate_id: Identifier
    candidate_sha256: Sha256
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    changeset_sha256: Sha256
    test_receipt_sha256: Sha256
    brief_sha256: Sha256
    decision_sha256: Sha256
    memory_sha256: Sha256
    human_approval_sha256: Sha256
    artifact_references: tuple[EvidenceReference, ...]
    authoritative_test_receipt_sha256: Sha256
    retest_base_sha: GitSha | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    legacy_reconstructed_commit_sha: GitSha | None = Field(
        default=None,
        validation_alias="reconstructed_commit_sha",
        exclude_if=lambda value: value is None,
    )
    passed: Literal[True]
    timed_out: Literal[False]
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def receipt_is_canonical(self) -> PromotionReceiptV2:
        if (self.retest_base_sha is None) == (
            self.legacy_reconstructed_commit_sha is None
        ):
            raise ValueError("promotion receipt must use one retest base field")
        canonical = self.model_dump(
            mode="json",
            exclude={"receipt_sha256", "legacy_reconstructed_commit_sha"},
        )
        if self.legacy_reconstructed_commit_sha is not None:
            canonical["reconstructed_commit_sha"] = (
                self.legacy_reconstructed_commit_sha
            )
        if (
            self.approval_head.run_id != self.run_id
            or self.receipt_sha256 != canonical_json_sha256(canonical)
        ):
            raise ValueError("promotion receipt binding or digest does not match")
        return self

    @classmethod
    def create(cls, **values: Any) -> PromotionReceiptV2:
        values = {**values}
        if "reconstructed_commit_sha" in values:
            raise ValueError("new promotion receipts require retest_base_sha")
        values.pop("receipt_sha256", None)
        values["approval_head"] = VerifiedHead.model_validate(
            values["approval_head"]
        ).model_dump(mode="json")
        canonical = values
        return cls.model_validate(
            {**canonical, "receipt_sha256": canonical_json_sha256(canonical)}
        )


class PromotionOutcome(_Frozen):
    approval_event: Event
    receipt: PromotionReceiptV2
    receipt_reference: EvidenceReference
    completion_event: Event
    checkpoint: HeadCheckpoint
    final_head: VerifiedHead


ReconstructAndRetest = Callable[[PromotionRetestRequest], PromotionRetestResult]


class PromotionError(RuntimeError):
    pass


class PromotionEvidenceError(PromotionError):
    pass


class PromotionConflict(PromotionError):
    pass


class PromotionRetestError(PromotionError):
    pass


class PromotionCheckpointError(PromotionError):
    pass


_CHECKPOINT_SCHEMA = """
CREATE TABLE IF NOT EXISTS promotion_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    expected_seq INTEGER NOT NULL CHECK (expected_seq >= 1),
    checkpoint_bytes BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS promotion_checkpoints_run
ON promotion_checkpoints (run_id, expected_seq, checkpoint_id);
"""


class SQLiteCheckpointRecorder:
    """Durable local checkpoint retention beside the authoritative event store."""

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = str(path)
        self.read_only = read_only
        with closing(self._connect()) as connection:
            if read_only:
                if (
                    connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                        "AND name = 'promotion_checkpoints'"
                    ).fetchone()
                    is None
                ):
                    raise PromotionCheckpointError(
                        "promotion checkpoint table is missing"
                    )
            else:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript(_CHECKPOINT_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        target = (
            Path(self.path).resolve().as_uri() + "?mode=ro"
            if self.read_only
            else self.path
        )
        connection = sqlite3.connect(
            target,
            isolation_level=None,
            timeout=5,
            uri=self.read_only,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        if self.read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.execute("PRAGMA synchronous=FULL")
        return connection

    def __call__(self, checkpoint: HeadCheckpoint) -> None:
        if self.read_only:
            raise PromotionCheckpointError(
                "read-only checkpoint recorders cannot retain checkpoints"
            )
        try:
            checkpoint = HeadCheckpoint.model_validate(
                checkpoint.model_dump(mode="json")
            )
        except (AttributeError, ValidationError) as error:
            raise PromotionCheckpointError("promotion checkpoint is invalid") from error
        raw = canonical_json_bytes(checkpoint.model_dump(mode="json"))
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT OR IGNORE INTO promotion_checkpoints VALUES (?, ?, ?, ?)",
                    (
                        checkpoint.checkpoint_id,
                        checkpoint.run_id,
                        checkpoint.expected_seq,
                        raw,
                    ),
                )
                row = connection.execute(
                    "SELECT run_id, expected_seq, checkpoint_bytes "
                    "FROM promotion_checkpoints WHERE checkpoint_id = ?",
                    (checkpoint.checkpoint_id,),
                ).fetchone()
                if row is None or (
                    row["run_id"],
                    row["expected_seq"],
                    row["checkpoint_bytes"],
                ) != (
                    checkpoint.run_id,
                    checkpoint.expected_seq,
                    raw,
                ):
                    raise PromotionCheckpointError(
                        "promotion checkpoint conflicts with retained state"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def read(self, run_id: str) -> tuple[HeadCheckpoint, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT checkpoint_bytes FROM promotion_checkpoints "
                "WHERE run_id = ? ORDER BY expected_seq, checkpoint_id",
                (run_id,),
            ).fetchall()
        values: list[HeadCheckpoint] = []
        try:
            for row in rows:
                raw = row["checkpoint_bytes"]
                value = json.loads(raw)
                if not isinstance(raw, bytes) or canonical_json_bytes(value) != raw:
                    raise ValueError("checkpoint bytes are not canonical")
                values.append(HeadCheckpoint.model_validate(value))
        except (TypeError, ValueError, ValidationError) as error:
            raise PromotionCheckpointError(
                "retained promotion checkpoint is malformed"
            ) from error
        return tuple(values)


def _now() -> datetime:
    return datetime.now(UTC)


def _head(event: Event) -> VerifiedHead:
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def _whole_run(store: PromotionStore, head: VerifiedHead) -> tuple[Event, ...]:
    events: list[Event] = []
    after = 0
    while after < head.seq:
        batch = store.tail(head.run_id, after, min(256, head.seq - after))
        if not batch or batch[0].seq != after + 1:
            raise PromotionEvidenceError("verified lineage tail is incomplete")
        events.extend(batch)
        after = batch[-1].seq
    if (
        len(events) != head.event_count
        or not events
        or events[-1].event_sha256 != head.event_sha256
    ):
        raise PromotionEvidenceError("verified lineage tail does not match its head")
    return tuple(events)


def _verify_head(store: PromotionStore, expected: VerifiedHead) -> tuple[Event, ...]:
    state = store.verify(expected.run_id)
    if isinstance(state, EvidenceInvalidState):
        raise PromotionEvidenceError("lineage evidence is invalid")
    if state != expected:
        raise PromotionConflict("expected promotion head is stale")
    return _whole_run(store, state)


def _record(
    record_artifact: ArtifactRecorder,
    kind: EvidenceKind,
    value: Mapping[str, Any],
) -> EvidenceReference:
    reference = record_artifact(kind, value)
    if (
        not isinstance(reference, EvidenceReference)
        or reference.kind != kind
        or reference.sha256 != canonical_json_sha256(value)
    ):
        raise PromotionEvidenceError(
            "artifact recorder returned a mismatched reference"
        )
    return reference


def _successor(
    event: Event, expected: VerifiedHead, event_type: LineageEventType
) -> None:
    if (
        event.run_id != expected.run_id
        or event.seq != expected.seq + 1
        or event.previous_event_sha256 != expected.event_sha256
        or event.event_type != event_type
    ):
        raise PromotionEvidenceError("lineage store returned a non-successor event")


def _retest_request(
    request: PromotionRequest,
    approval: Event,
    approval_digest: str,
) -> PromotionRetestRequest:
    return PromotionRetestRequest(
        run_id=request.run_id,
        approval_head=_head(approval),
        approval_event_id=approval.event_id,
        approval_event_sha256=approval.event_sha256,
        repo_id=request.repo_id,
        base_sha=request.base_sha,
        agent_profile_id=request.agent_profile_id,
        policy_revision=request.policy_revision,
        candidate_id=request.candidate_id,
        candidate_sha256=request.candidate_sha256,
        candidate_patch_sha256=request.candidate_patch_sha256,
        candidate_tree_sha256=request.candidate_tree_sha256,
        candidate_tree_hash_version=request.candidate_tree_hash_version,
        changeset_sha256=request.changeset_sha256,
        test_receipt_sha256=request.test_receipt_sha256,
        brief_sha256=request.brief_sha256,
        decision_sha256=request.decision_sha256,
        memory_sha256=request.memory_sha256,
        human_approval_sha256=approval_digest,
        artifact_references=(
            request.candidate_reference,
            request.changeset_reference,
            request.test_reference,
            request.brief_reference,
            request.decision_reference,
            request.memory_reference,
        ),
    )


def _receipt_matches(
    receipt: PromotionReceiptV2,
    retest: PromotionRetestRequest,
) -> bool:
    for name in PromotionRetestRequest.model_fields:
        if name == "schema_version":
            continue
        if getattr(receipt, name) != getattr(retest, name):
            return False
    return receipt.passed and not receipt.timed_out


def _receipt_from_result(
    retest: PromotionRetestRequest,
    result: PromotionRetestResult,
) -> PromotionReceiptV2:
    receipt_id = (
        "promotion_receipt_"
        + canonical_json_sha256(
            {
                "retest": retest.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            }
        )[:32]
    )
    return PromotionReceiptV2.create(
        **retest.model_dump(mode="json"),
        receipt_id=receipt_id,
        **result.model_dump(mode="json"),
    )


def _checkpoint(
    request: PromotionRequest,
    approval_head: VerifiedHead,
    receipt_reference: EvidenceReference,
) -> HeadCheckpoint:
    recorded_at = _now()
    payload = {
        "schema_version": 2,
        "checkpoint_id": "checkpoint_"
        + canonical_json_sha256(
            {
                "run_id": request.run_id,
                "seq": approval_head.seq,
                "head": approval_head.event_sha256,
                "receipt": receipt_reference.sha256,
            }
        )[:32],
        "run_id": request.run_id,
        "expected_seq": approval_head.seq,
        "event_head_sha256": approval_head.event_sha256,
        "purpose": "promotion_precommit",
        "bound_artifact_kind": EvidenceKind.PROMOTION_RECEIPT,
        "bound_artifact_id": receipt_reference.id,
        "bound_artifact_sha256": receipt_reference.sha256,
        "server_recorded_at": recorded_at,
    }
    return HeadCheckpoint(
        **payload,
        checkpoint_sha256=canonical_json_sha256(
            {
                **payload,
                "bound_artifact_kind": EvidenceKind.PROMOTION_RECEIPT.value,
                "server_recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
            }
        ),
    )


def _deny_if_current(
    store: PromotionStore,
    record_artifact: ArtifactRecorder,
    request: PromotionRequest,
    approval: Event,
    reason_code: str,
) -> None:
    approval_head = _head(approval)
    state = store.verify(request.run_id)
    if state != approval_head:
        return
    record = {
        "schema_version": 2,
        "action": "promotion.denied",
        "run_id": request.run_id,
        "approval_event_id": approval.event_id,
        "approval_event_sha256": approval.event_sha256,
        "candidate_patch_sha256": request.candidate_patch_sha256,
        "reason_code": reason_code,
    }
    try:
        source = _record(record_artifact, EvidenceKind.POLICY_RECEIPT, record)
        store.append(
            request.run_id,
            approval_head,
            canonical_json_sha256(record),
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=request.repo_id,
                base_sha=request.base_sha,
                agent_profile_id=request.agent_profile_id,
                policy_revision=request.policy_revision,
                event_type=LineageEventType.PROMOTION_DENIED,
                truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                authority=LineageAuthority.POLICY_ENGINE,
                references=(
                    EvidenceReference(
                        kind=EvidenceKind.EVENT,
                        id=approval.event_id,
                        sha256=approval.event_sha256,
                    ),
                ),
                source_ref=SourceReference(
                    kind=SourceKind.POLICY_EVALUATION,
                    id=source.id,
                    sha256=source.sha256,
                ),
                payload={
                    "candidate_patch_sha256": request.candidate_patch_sha256,
                    "reason_code": reason_code,
                    "status": "denied",
                },
            ),
        )
    except Exception:  # noqa: BLE001 - approval remains durable NEEDS_HUMAN
        return


def _resolve_artifact(
    artifacts: PromotionArtifacts,
    reference: EvidenceReference,
) -> dict[str, Any]:
    try:
        raw = artifacts.resolve(reference.kind.value, reference.id)
    except Exception as error:
        raise PromotionEvidenceError(
            "promotion artifact could not be resolved"
        ) from error
    if raw is None or sha256_hex(raw) != reference.sha256:
        raise PromotionEvidenceError("promotion artifact digest does not match")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeError) as error:
        raise PromotionEvidenceError("promotion artifact is malformed") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise PromotionEvidenceError("promotion artifact is not canonical JSON")
    return value


def _stable_run(
    store: PromotionStore,
    run_id: str,
) -> tuple[VerifiedHead, tuple[Event, ...]]:
    head = store.verify(run_id)
    if isinstance(head, EvidenceInvalidState) or head.seq == 0:
        raise PromotionEvidenceError("promotion run is absent or invalid")
    events = _whole_run(store, head)
    if store.verify(run_id) != head:
        raise PromotionConflict("promotion run changed during preparation")
    return head, events


def _only_event(
    events: tuple[Event, ...],
    event_type: LineageEventType,
) -> Event:
    matches = tuple(event for event in events if event.event_type == event_type)
    if len(matches) != 1:
        raise PromotionEvidenceError(
            f"promotion requires exactly one {event_type.value} event"
        )
    return matches[0]


def _only_reference(event: Event, kind: EvidenceKind) -> EvidenceReference:
    matches = tuple(
        reference for reference in event.references if reference.kind == kind
    )
    if len(matches) != 1:
        raise PromotionEvidenceError(
            f"{event.event_type.value} must bind exactly one {kind.value} artifact"
        )
    return matches[0]


def _approved_memory(
    store: PromotionStore,
    artifacts: PromotionArtifacts,
    brief: ContextBrief,
    decision: HandoffDecision,
    brief_reference: EvidenceReference,
    decision_reference: EvidenceReference,
) -> tuple[EvidenceReference, Event]:
    if len(brief.approved_memories) != 1:
        raise PromotionEvidenceError(
            "promotion requires exactly one approved memory in context"
        )
    _, source_events = _stable_run(store, brief.source_run_id)
    if (
        len(source_events) < brief.source_head.seq
        or source_events[brief.source_head.seq - 1].event_sha256
        != brief.source_head.event_sha256
    ):
        raise PromotionEvidenceError("context source head is not retained")
    compiled = tuple(
        event
        for event in source_events[brief.source_head.seq :]
        if event.event_type == LineageEventType.CONTEXT_COMPILED
        and brief_reference in event.references
        and decision_reference in event.references
        and event.payload.get("brief_sha256") == brief.brief_sha256
        and event.payload.get("decision_sha256") == decision.decision_sha256
    )
    if len(compiled) != 1:
        raise PromotionEvidenceError("source context compilation is not retained")

    selected = brief.approved_memories[0]
    matches = tuple(
        event
        for event in source_events[: brief.source_head.seq]
        if event.event_type == LineageEventType.MEMORY_APPROVED
        and event.payload.get("memory_id") == selected.memory_id
        and event.payload.get("revision") == selected.revision
    )
    if len(matches) != 1:
        raise PromotionEvidenceError("approved source memory is not retained")
    event = matches[0]
    references = tuple(
        reference
        for reference in event.references
        if reference.kind == EvidenceKind.MEMORY_REVISION
        and reference.sha256 == event.payload.get("memory_sha256")
    )
    if len(references) != 1:
        raise PromotionEvidenceError("approved source memory digest is ambiguous")
    reference = references[0]
    try:
        memory = MemoryRevision.model_validate(_resolve_artifact(artifacts, reference))
    except ValidationError as error:
        raise PromotionEvidenceError("approved source memory is malformed") from error
    if (
        memory.state != MemoryState.APPROVED
        or memory.memory_id != selected.memory_id
        or memory.revision != selected.revision
        or memory.rule != selected.exact_text
        or memory.repo_id != brief.repo_id
        or memory.decision is None
        or memory.decision.decision_id != event.payload.get("decision_id")
        or (
            selected.scope_id is not None
            and (
                memory.scope_id != selected.scope_id
                or memory.path_globs != selected.path_globs
                or memory.task_tags != selected.task_tags
            )
        )
    ):
        raise PromotionEvidenceError("approved memory does not match the context")
    candidate_id = (
        "memory_revision:"
        + sha256_hex(f"{memory.memory_id}:{memory.revision}".encode())[:24]
    )
    candidate_sha256 = canonical_json_sha256(
        {
            "candidate_kind": "memory_revision",
            "value": memory.model_dump(mode="json"),
        }
    )
    if not any(
        entry.candidate_kind == "memory_revision"
        and entry.id == candidate_id
        and entry.sha256 == candidate_sha256
        and entry.include
        for entry in decision.entries
    ):
        raise PromotionEvidenceError(
            "approved memory was not selected by context policy"
        )
    return reference, event


def _prepared_candidate_matches(
    artifacts: PromotionArtifacts,
    request: PromotionRequest,
) -> bool:
    try:
        record = _resolve_artifact(artifacts, request.candidate_reference)
    except PromotionEvidenceError:
        return False
    expected_references = {
        "changeset_reference": request.changeset_reference,
        "test_reference": request.test_reference,
        "brief_reference": request.brief_reference,
        "decision_reference": request.decision_reference,
        "memory_reference": request.memory_reference,
    }
    try:
        references_match = all(
            EvidenceReference.model_validate(record.get(name)) == reference
            for name, reference in expected_references.items()
        )
    except ValidationError:
        return False
    return references_match and all(
        (
            record.get("record_type") == "verified_promotion_candidate",
            record.get("schema_version") == 2,
            record.get("candidate_id") == request.candidate_id,
            record.get("run_id") == request.run_id,
            record.get("repo_id") == request.repo_id,
            record.get("base_sha") == request.base_sha,
            record.get("candidate_patch_sha256") == request.candidate_patch_sha256,
            record.get("candidate_tree_sha256") == request.candidate_tree_sha256,
            record.get("candidate_tree_hash_version")
            == request.candidate_tree_hash_version,
            isinstance(record.get("source_memory_event"), dict),
        )
    )


def _approval_record(request: PromotionRequest) -> tuple[str, dict[str, Any]]:
    digest = canonical_json_sha256(request.human_approval.model_dump(mode="json"))
    bindings = {
        key: value
        for key, value in request.model_dump(mode="json").items()
        if key not in {"schema_version", "expected_head", "human_approval"}
    }
    if request.operator_label is None:
        bindings.pop("operator_label")
        bindings.pop("operator_rationale")
    return digest, {
        "schema_version": 2,
        "action": "promotion.approved",
        "run_id": request.run_id,
        "expected_head": request.expected_head.model_dump(mode="json"),
        "human_approval": request.human_approval.model_dump(mode="json"),
        "human_approval_sha256": digest,
        "bindings": bindings,
    }


def _approval_payload(request: PromotionRequest, digest: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate_patch_sha256": request.candidate_patch_sha256,
        "decision_id": request.human_approval.decision_id,
        "decision_sha256": digest,
        "expected_head_sha256": request.expected_head.event_sha256,
        "status": "approved",
    }
    if request.operator_label is not None:
        payload["operator_label"] = request.operator_label
        if request.operator_rationale is not None:
            payload["operator_rationale"] = request.operator_rationale
    return payload


def _validate_promotion_evidence(
    artifacts: PromotionArtifacts,
    request: PromotionRequest,
    events: tuple[Event, ...],
) -> None:
    first = events[0]
    if (
        first.repo_id,
        first.base_sha,
        first.agent_profile_id,
        first.policy_revision,
    ) != (
        request.repo_id,
        request.base_sha,
        request.agent_profile_id,
        request.policy_revision,
    ):
        raise PromotionConflict("promotion identity does not match the verified run")
    required_references = {
        request.candidate_reference,
        request.changeset_reference,
        request.test_reference,
        request.brief_reference,
        request.decision_reference,
        request.memory_reference,
    }
    observed_references = {
        reference for event in events for reference in event.references
    }
    prepared_candidate = _prepared_candidate_matches(artifacts, request)
    valid = (
        required_references <= observed_references
        and any(
            event.event_type == LineageEventType.CANDIDATE_CREATED
            and request.candidate_reference in event.references
            and event.payload.get("candidate_id") == request.candidate_id
            and event.payload.get("candidate_patch_sha256")
            == request.candidate_patch_sha256
            and event.payload.get("candidate_tree_sha256")
            == request.candidate_tree_sha256
            and event.payload.get("candidate_tree_hash_version")
            == request.candidate_tree_hash_version
            for event in events
        )
        and any(
            event.event_type == LineageEventType.CHANGESET_PARSED
            and request.changeset_reference in event.references
            and event.payload.get("candidate_patch_sha256")
            == request.candidate_patch_sha256
            for event in events
        )
        and any(
            event.event_type == LineageEventType.TEST_RECEIPT_CREATED
            and request.test_reference in event.references
            and event.payload.get("receipt_sha256") == request.test_receipt_sha256
            and event.payload.get("passed") is True
            for event in events
        )
        and any(
            request.brief_reference in event.references
            and request.decision_reference in event.references
            and (
                (
                    event.event_type == LineageEventType.CONTEXT_COMPILED
                    and event.payload.get("brief_sha256") == request.brief_sha256
                    and event.payload.get("decision_sha256") == request.decision_sha256
                )
                or (
                    prepared_candidate
                    and event.event_type == LineageEventType.CONTEXT_INJECTED
                )
            )
            for event in events
        )
        and (
            any(
                event.event_type == LineageEventType.MEMORY_APPROVED
                and request.memory_reference in event.references
                and event.payload.get("memory_sha256") == request.memory_sha256
                for event in events
            )
            or prepared_candidate
        )
    )
    if not valid:
        raise PromotionEvidenceError(
            "promotion artifacts are not bound to the verified candidate head"
        )
    try:
        projection = reduce_events(events)
    except ProjectionError as error:
        raise PromotionEvidenceError(
            "lineage stream is semantically invalid"
        ) from error
    if projection.state != LineageRunState.NEEDS_HUMAN:
        raise PromotionConflict("run is not awaiting human promotion")


def _request_from_approval(
    artifacts: PromotionArtifacts,
    events: tuple[Event, ...],
) -> PromotionRequest:
    if len(events) < 2 or events[-1].event_type != LineageEventType.PROMOTION_APPROVED:
        raise PromotionConflict("promotion approval is not recoverable")
    approval = events[-1]
    source_kind = (
        SourceKind.SIMULATED_FIXTURE
        if approval.truth_kind == TruthKind.SIMULATED_FIXTURE
        else SourceKind.OPERATOR_REQUEST
    )
    evidence_kind = (
        EvidenceKind.SIMULATED_FIXTURE
        if approval.truth_kind == TruthKind.SIMULATED_FIXTURE
        else EvidenceKind.OPERATOR_REQUEST
    )
    if approval.source_ref.kind != source_kind:
        raise PromotionEvidenceError("promotion approval source is invalid")
    source_reference = EvidenceReference(
        kind=evidence_kind,
        id=approval.source_ref.id,
        sha256=approval.source_ref.sha256,
    )
    record = _resolve_artifact(artifacts, source_reference)
    if set(record) != {
        "schema_version",
        "action",
        "run_id",
        "expected_head",
        "human_approval",
        "human_approval_sha256",
        "bindings",
    } or not isinstance(record.get("bindings"), dict):
        raise PromotionEvidenceError("promotion approval record is malformed")
    try:
        request = PromotionRequest.model_validate(
            {
                "schema_version": record["schema_version"],
                **record["bindings"],
                "expected_head": record["expected_head"],
                "human_approval": record["human_approval"],
            }
        )
    except (KeyError, TypeError, ValidationError) as error:
        raise PromotionEvidenceError(
            "promotion approval request is malformed"
        ) from error
    digest, expected_record = _approval_record(request)
    expected_references = (
        request.candidate_reference,
        request.changeset_reference,
        request.test_reference,
        request.brief_reference,
        request.decision_reference,
        request.memory_reference,
    )
    if (
        record != expected_record
        or approval.truth_kind
        != (
            TruthKind.SIMULATED_FIXTURE
            if request.human_approval.actor == "simulated_fixture"
            else TruthKind.HUMAN_ATTESTED
        )
        or request.run_id != approval.run_id
        or request.expected_head != _head(events[-2])
        or approval.references != expected_references
        or approval.payload != _approval_payload(request, digest)
    ):
        raise PromotionEvidenceError("promotion approval binding does not match")
    _successor(approval, request.expected_head, LineageEventType.PROMOTION_APPROVED)
    _validate_promotion_evidence(artifacts, request, events[:-1])
    return request


def prepare_verified_promotion(
    store: PromotionStore,
    artifacts: PromotionArtifacts,
    run_id: str,
    *,
    decision_id: str,
    occurred_at: datetime,
    decision_actor: Literal["human", "simulated_fixture"] | None = None,
    operator_label: str | None = None,
    operator_rationale: str | None = None,
) -> PromotionRequest | PreparedPromotionCandidate:
    """Derive and persist one promotion candidate from verified production evidence."""

    head, events = _stable_run(store, run_id)
    decisions = tuple(
        event
        for event in events
        if event.event_type
        in {
            LineageEventType.PROMOTION_APPROVED,
            LineageEventType.PROMOTION_DENIED,
            LineageEventType.PROMOTION_COMPLETED,
        }
    )
    if (
        len(decisions) == 1
        and decisions[0] is events[-1]
        and (decisions[0].event_type == LineageEventType.PROMOTION_APPROVED)
    ):
        recovered = _request_from_approval(artifacts, events)
        if decision_actor is None:
            return PreparedPromotionCandidate.model_validate(
                recovered.model_dump(
                    mode="json",
                    exclude={"human_approval", "operator_label", "operator_rationale"},
                )
            )
        return recovered
    if decisions:
        raise PromotionConflict("promotion preparation follows a promotion decision")
    try:
        if reduce_events(events).state != LineageRunState.NEEDS_HUMAN:
            raise PromotionConflict("run is not awaiting human promotion")
    except ProjectionError as error:
        raise PromotionEvidenceError("promotion run is semantically invalid") from error

    changeset_event = _only_event(events, LineageEventType.CHANGESET_PARSED)
    test_event = _only_event(events, LineageEventType.TEST_RECEIPT_CREATED)
    injected_event = _only_event(events, LineageEventType.CONTEXT_INJECTED)
    changeset_reference = _only_reference(changeset_event, EvidenceKind.CHANGESET)
    test_reference = _only_reference(test_event, EvidenceKind.TEST_RECEIPT)
    brief_reference = _only_reference(injected_event, EvidenceKind.CONTEXT_BRIEF)
    decision_reference = _only_reference(injected_event, EvidenceKind.HANDOFF_DECISION)
    injection_reference = _only_reference(
        injected_event, EvidenceKind.INJECTION_RECEIPT
    )
    changeset = _resolve_artifact(artifacts, changeset_reference)
    test_receipt = _resolve_artifact(artifacts, test_reference)
    try:
        brief = ContextBrief.model_validate(
            _resolve_artifact(artifacts, brief_reference)
        )
        decision = HandoffDecision.model_validate(
            _resolve_artifact(artifacts, decision_reference)
        )
        injection = ContextInjectionReceipt.model_validate(
            _resolve_artifact(artifacts, injection_reference)
        )
    except ValidationError as error:
        raise PromotionEvidenceError("promotion context is malformed") from error
    if (
        brief.repo_id != events[0].repo_id
        or brief.base_sha != events[0].base_sha
        or brief.target_profile_id != events[0].agent_profile_id
        or decision.decision != "allowed"
        or decision.source_run_id != brief.source_run_id
        or decision.source_head != brief.source_head
        or decision.repo_id != brief.repo_id
        or decision.base_sha != brief.base_sha
        or decision.task_id != brief.task_id
        or decision.target_profile_id != brief.target_profile_id
        or decision.target_profile_revision != brief.target_profile_revision
        or decision.policy_revision != brief.policy_revision
        or decision.decision_sha256 != injected_event.payload.get("decision_sha256")
        or brief.brief_sha256 != injected_event.payload.get("brief_sha256")
        or injection.consumer_run_id != run_id
        or injection.decision_sha256 != decision.decision_sha256
        or injection.brief_sha256 != brief.brief_sha256
        or injection.target_profile_id != brief.target_profile_id
        or injection.target_profile_revision != brief.target_profile_revision
        or injection.policy_revision != brief.policy_revision
        or injection.receipt_sha256
        != injected_event.payload.get("injection_receipt_sha256")
    ):
        raise PromotionEvidenceError("promotion context binding does not match the run")

    memory_reference, memory_event = _approved_memory(
        store,
        artifacts,
        brief,
        decision,
        brief_reference,
        decision_reference,
    )
    expected_memory_truth = (
        None
        if decision_actor is None
        else TruthKind.SIMULATED_FIXTURE
        if decision_actor == "simulated_fixture"
        else TruthKind.HUMAN_ATTESTED
    )
    if (
        expected_memory_truth is not None
        and memory_event.truth_kind != expected_memory_truth
    ):
        raise PromotionEvidenceError(
            "promotion approval provenance does not match its approved memory"
        )
    raw_changed_paths = changeset.get("changed_paths")
    raw_bound_paths = test_receipt.get("bound_paths")
    if (
        not isinstance(raw_changed_paths, list)
        or not all(isinstance(path, str) for path in raw_changed_paths)
        or not isinstance(raw_bound_paths, list)
        or not all(isinstance(path, str) for path in raw_bound_paths)
    ):
        raise PromotionEvidenceError("promotion path bindings are malformed")
    changed_paths = tuple(raw_changed_paths)
    canonical_patch = changeset.get("canonical_patch_base64")
    try:
        patch = base64.b64decode(canonical_patch, validate=True)
    except (binascii.Error, TypeError, ValueError) as error:
        raise PromotionEvidenceError(
            "promotion changeset patch is malformed"
        ) from error
    if (
        changeset.get("schema_version") != 2
        or changeset.get("run_id") != run_id
        or changeset.get("repo_id") != events[0].repo_id
        or changeset.get("base_sha") != events[0].base_sha
        or not changed_paths
        or changed_paths != tuple(sorted(set(changed_paths)))
        or changed_paths != brief.write_scope
        or not patch
        or sha256_hex(patch) != changeset.get("candidate_patch_sha256")
        or not isinstance(changeset.get("candidate_tree_sha256"), str)
        or changeset.get("candidate_tree_hash_version") != "graphene.tree.v2"
        or test_event.payload.get("receipt_id") != test_reference.id
        or test_event.payload.get("receipt_sha256") != test_reference.sha256
        or test_event.payload.get("passed") is not True
        or test_event.payload.get("bound_paths") != list(changed_paths)
        or test_receipt.get("passed") is not True
        or tuple(raw_bound_paths) != changed_paths
    ):
        raise PromotionEvidenceError("promotion changeset or test binding is invalid")

    source_memory_event = EvidenceReference(
        kind=EvidenceKind.EVENT,
        id=memory_event.event_id,
        sha256=memory_event.event_sha256,
    )
    references = {
        "changeset_reference": changeset_reference,
        "test_reference": test_reference,
        "brief_reference": brief_reference,
        "decision_reference": decision_reference,
        "memory_reference": memory_reference,
    }
    candidate_id = (
        "candidate_"
        + canonical_json_sha256(
            {
                "run_id": run_id,
                **{
                    name: reference.model_dump(mode="json")
                    for name, reference in references.items()
                },
                "source_memory_event": source_memory_event.model_dump(mode="json"),
            }
        )[:32]
    )
    candidate_record = {
        "schema_version": 2,
        "record_type": "verified_promotion_candidate",
        "candidate_id": candidate_id,
        "run_id": run_id,
        "repo_id": events[0].repo_id,
        "base_sha": events[0].base_sha,
        "candidate_patch_sha256": changeset["candidate_patch_sha256"],
        "candidate_tree_sha256": changeset["candidate_tree_sha256"],
        "candidate_tree_hash_version": changeset["candidate_tree_hash_version"],
        "changed_paths": list(changed_paths),
        **{
            name: reference.model_dump(mode="json")
            for name, reference in references.items()
        },
        "source_run_id": brief.source_run_id,
        "source_head": brief.source_head.model_dump(mode="json"),
        "source_memory_event": source_memory_event.model_dump(mode="json"),
    }
    candidate_events = tuple(
        event
        for event in events
        if event.event_type == LineageEventType.CANDIDATE_CREATED
    )
    if candidate_events:
        if len(candidate_events) != 1 or candidate_events[0] != events[-1]:
            raise PromotionConflict("prepared promotion candidate is not current")
        candidate_event = candidate_events[0]
        candidate_reference = _only_reference(
            candidate_event, EvidenceKind.EVIDENCE_BLOB
        )
        if _resolve_artifact(artifacts, candidate_reference) != candidate_record:
            raise PromotionEvidenceError("prepared promotion candidate changed")
    else:
        candidate_reference = _record(
            artifacts,
            EvidenceKind.EVIDENCE_BLOB,
            candidate_record,
        )
        try:
            candidate_event = store.append(
                run_id,
                head,
                canonical_json_sha256(
                    {"event": "candidate.created", "record": candidate_record}
                ),
                EventInput(
                    session_id=None,
                    invocation_id=None,
                    model_id=None,
                    tool_call_id=None,
                    repo_id=events[0].repo_id,
                    base_sha=events[0].base_sha,
                    agent_profile_id=events[0].agent_profile_id,
                    policy_revision=events[0].policy_revision,
                    event_type=LineageEventType.CANDIDATE_CREATED,
                    truth_kind=TruthKind.SERVER_DERIVED,
                    authority=LineageAuthority.ARTIFACT_PARSER,
                    references=(candidate_reference, *references.values()),
                    source_ref=SourceReference(
                        kind=SourceKind.REDUCER_RECEIPT,
                        id=candidate_reference.id,
                        sha256=candidate_reference.sha256,
                    ),
                    payload={
                        "candidate_id": candidate_id,
                        "candidate_patch_sha256": changeset["candidate_patch_sha256"],
                        "candidate_tree_sha256": changeset["candidate_tree_sha256"],
                        "candidate_tree_hash_version": changeset["candidate_tree_hash_version"],
                        "changed_path_count": len(changed_paths),
                        "status": "created",
                    },
                ),
            )
        except (EvidenceInvalid, LineageConflict) as error:
            raise PromotionConflict(
                "promotion candidate append was rejected"
            ) from error
        _successor(candidate_event, head, LineageEventType.CANDIDATE_CREATED)
        if store.verify(run_id) != _head(candidate_event):
            raise PromotionEvidenceError("prepared promotion candidate did not verify")

    prepared = PreparedPromotionCandidate(
        run_id=run_id,
        expected_head=_head(candidate_event),
        repo_id=events[0].repo_id,
        base_sha=events[0].base_sha,
        agent_profile_id=events[0].agent_profile_id,
        policy_revision=events[0].policy_revision,
        candidate_id=candidate_id,
        candidate_sha256=candidate_reference.sha256,
        candidate_patch_sha256=changeset["candidate_patch_sha256"],
        candidate_tree_sha256=changeset["candidate_tree_sha256"],
        candidate_tree_hash_version=changeset["candidate_tree_hash_version"],
        changeset_sha256=changeset_reference.sha256,
        test_receipt_sha256=test_reference.sha256,
        brief_sha256=brief_reference.sha256,
        decision_sha256=decision_reference.sha256,
        memory_sha256=memory_reference.sha256,
        candidate_reference=candidate_reference,
        changeset_reference=changeset_reference,
        test_reference=test_reference,
        brief_reference=brief_reference,
        decision_reference=decision_reference,
        memory_reference=memory_reference,
    )
    if decision_actor is None:
        return prepared
    approval = HumanDecision(
        decision_id=decision_id,
        value=MemoryDecisionValue.APPROVE,
        purpose="promotion",
        bound_digest=changeset["candidate_patch_sha256"],
        occurred_at=occurred_at,
        actor=decision_actor,
    )
    return PromotionRequest(
        **prepared.model_dump(mode="python"),
        human_approval=approval,
        operator_label=operator_label,
        operator_rationale=operator_rationale,
    )


def _produce_receipt(
    store: PromotionStore,
    request: PromotionRequest,
    approval: Event,
    *,
    record_artifact: PromotionArtifacts,
    reconstruct_and_retest: ReconstructAndRetest,
) -> tuple[PromotionReceiptV2, EvidenceReference]:
    digest, _ = _approval_record(request)
    retest = _retest_request(request, approval, digest)
    try:
        raw_result = reconstruct_and_retest(retest)
    except Exception as error:
        _deny_if_current(
            store, record_artifact, request, approval, "reconstruction_failed"
        )
        raise PromotionRetestError("authoritative reconstruction failed") from error
    try:
        if type(raw_result) is not PromotionRetestResult:
            raise TypeError("callback did not return PromotionRetestResult")
        result = PromotionRetestResult.model_validate(
            raw_result.model_dump(mode="json")
        )
    except (TypeError, ValidationError):
        _deny_if_current(
            store, record_artifact, request, approval, "retest_binding_mismatch"
        )
        raise PromotionRetestError(
            "authoritative retest must return a narrow core-owned result"
        ) from None
    if not result.passed or result.timed_out:
        _deny_if_current(store, record_artifact, request, approval, "retest_failed")
        raise PromotionRetestError("authoritative retest did not pass")
    receipt = _receipt_from_result(retest, result)
    if not _receipt_matches(receipt, retest):
        raise PromotionRetestError("core-owned promotion receipt does not match")
    try:
        reference = _record(
            record_artifact,
            EvidenceKind.PROMOTION_RECEIPT,
            receipt.model_dump(mode="json"),
        )
    except Exception:
        _deny_if_current(
            store, record_artifact, request, approval, "receipt_persistence_failed"
        )
        raise
    _verify_head(store, _head(approval))
    return receipt, reference


def _retain_checkpoint(
    store: PromotionStore,
    request: PromotionRequest,
    approval: Event,
    receipt_reference: EvidenceReference,
    *,
    record_artifact: PromotionArtifacts,
    record_checkpoint: CheckpointRecorder,
) -> tuple[HeadCheckpoint, EvidenceReference]:
    approval_head = _head(approval)
    checkpoint = _checkpoint(request, approval_head, receipt_reference)
    try:
        reference = _record(
            record_artifact,
            EvidenceKind.CHECKPOINT,
            checkpoint.model_dump(mode="json"),
        )
    except Exception as error:
        raise PromotionCheckpointError(
            "promotion checkpoint artifact failed"
        ) from error
    try:
        record_checkpoint(checkpoint)
        raw_retained = record_checkpoint.read(request.run_id)
    except Exception as error:
        raise PromotionCheckpointError("promotion checkpoint failed") from error
    try:
        if not isinstance(raw_retained, tuple):
            raise TypeError("checkpoint callback did not return a readback tuple")
        retained = tuple(HeadCheckpoint.model_validate(item) for item in raw_retained)
    except (TypeError, ValidationError):
        raise PromotionCheckpointError(
            "promotion checkpoint readback is invalid"
        ) from None
    if (
        checkpoint not in retained
        or retained.count(checkpoint) != 1
        or any(item.run_id != request.run_id for item in retained)
        or len({item.checkpoint_id for item in retained}) != len(retained)
    ):
        raise PromotionCheckpointError("promotion checkpoint was not retained")
    retained_head = store.verify(request.run_id)
    if isinstance(retained_head, EvidenceInvalidState):
        raise PromotionCheckpointError("retained promotion checkpoint is invalid")
    if retained_head != approval_head:
        raise PromotionConflict("promotion head changed before completion")
    return checkpoint, reference


def _complete_promotion(
    store: PromotionStore,
    request: PromotionRequest,
    approval: Event,
    receipt: PromotionReceiptV2,
    receipt_reference: EvidenceReference,
    checkpoint: HeadCheckpoint,
    checkpoint_reference: EvidenceReference,
) -> PromotionOutcome:
    approval_head = _head(approval)
    try:
        completion = store.append(
            request.run_id,
            approval_head,
            canonical_json_sha256(
                {
                    "event": "promotion.completed",
                    "receipt_id": receipt_reference.id,
                    "receipt_sha256": receipt_reference.sha256,
                    "checkpoint_id": checkpoint_reference.id,
                    "checkpoint_sha256": checkpoint_reference.sha256,
                }
            ),
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=request.repo_id,
                base_sha=request.base_sha,
                agent_profile_id=request.agent_profile_id,
                policy_revision=request.policy_revision,
                event_type=LineageEventType.PROMOTION_COMPLETED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.PROMOTION_SERVICE,
                references=(
                    EvidenceReference(
                        kind=EvidenceKind.EVENT,
                        id=approval.event_id,
                        sha256=approval.event_sha256,
                    ),
                    receipt_reference,
                    checkpoint_reference,
                ),
                source_ref=SourceReference(
                    kind=SourceKind.PROMOTION_RECEIPT,
                    id=receipt_reference.id,
                    sha256=receipt_reference.sha256,
                ),
                payload={
                    "candidate_patch_sha256": request.candidate_patch_sha256,
                    "promotion_receipt_id": receipt_reference.id,
                    "promotion_receipt_sha256": receipt.receipt_sha256,
                    "status": "completed",
                },
            ),
        )
    except (LineageConflict, EvidenceInvalid) as error:
        raise PromotionConflict("promotion completion append was rejected") from error
    _successor(completion, approval_head, LineageEventType.PROMOTION_COMPLETED)
    final_head = _head(completion)
    if store.verify(request.run_id) != final_head:
        raise PromotionEvidenceError("completed promotion did not verify")
    return PromotionOutcome(
        approval_event=approval,
        receipt=receipt,
        receipt_reference=receipt_reference,
        completion_event=completion,
        checkpoint=checkpoint,
        final_head=final_head,
    )


def _recover_approved_promotion(
    store: PromotionStore,
    request: PromotionRequest,
    events: tuple[Event, ...],
    *,
    record_artifact: PromotionArtifacts,
    reconstruct_and_retest: ReconstructAndRetest,
    record_checkpoint: CheckpointRecorder,
) -> PromotionOutcome:
    recovered = _request_from_approval(record_artifact, events)
    if recovered != request:
        raise PromotionConflict("promotion retry does not match retained approval")
    approval = events[-1]
    approval_head = _head(approval)
    try:
        raw_retained = record_checkpoint.read(request.run_id)
    except Exception as error:
        raise PromotionCheckpointError("promotion checkpoint failed") from error
    if not isinstance(raw_retained, tuple):
        raise PromotionCheckpointError("promotion checkpoint readback is invalid")
    if len(raw_retained) > 1:
        raise PromotionCheckpointError("promotion checkpoint is ambiguous")
    if not raw_retained:
        receipt, receipt_reference = _produce_receipt(
            store,
            request,
            approval,
            record_artifact=record_artifact,
            reconstruct_and_retest=reconstruct_and_retest,
        )
        checkpoint, checkpoint_reference = _retain_checkpoint(
            store,
            request,
            approval,
            receipt_reference,
            record_artifact=record_artifact,
            record_checkpoint=record_checkpoint,
        )
    else:
        try:
            checkpoint = HeadCheckpoint.model_validate(raw_retained[0])
        except ValidationError as error:
            raise PromotionCheckpointError(
                "promotion checkpoint readback is invalid"
            ) from error
        if (
            checkpoint.run_id != request.run_id
            or checkpoint.expected_seq != approval.seq
            or checkpoint.event_head_sha256 != approval.event_sha256
            or checkpoint.purpose != "promotion_precommit"
            or checkpoint.bound_artifact_kind != EvidenceKind.PROMOTION_RECEIPT
        ):
            raise PromotionCheckpointError("promotion checkpoint binding is invalid")
        receipt_reference = EvidenceReference(
            kind=EvidenceKind.PROMOTION_RECEIPT,
            id=checkpoint.bound_artifact_id,
            sha256=checkpoint.bound_artifact_sha256,
        )
        try:
            receipt = PromotionReceiptV2.model_validate(
                _resolve_artifact(record_artifact, receipt_reference)
            )
        except ValidationError as error:
            raise PromotionEvidenceError("promotion receipt is malformed") from error
        digest, _ = _approval_record(request)
        if not _receipt_matches(receipt, _retest_request(request, approval, digest)):
            raise PromotionEvidenceError("retained promotion receipt does not match")
        checkpoint_reference = _record(
            record_artifact,
            EvidenceKind.CHECKPOINT,
            checkpoint.model_dump(mode="json"),
        )
        if store.verify(request.run_id) != approval_head:
            raise PromotionCheckpointError("retained promotion checkpoint is invalid")
    return _complete_promotion(
        store,
        request,
        approval,
        receipt,
        receipt_reference,
        checkpoint,
        checkpoint_reference,
    )


def promote(
    store: PromotionStore,
    request: PromotionRequest,
    *,
    record_artifact: PromotionArtifacts,
    reconstruct_and_retest: ReconstructAndRetest,
    record_checkpoint: CheckpointRecorder,
    allow_simulated_fixture: bool = False,
) -> PromotionOutcome:
    """Run the non-circular N / N+1 / N+2 promotion protocol."""

    if not isinstance(request, PromotionRequest):
        raise TypeError("promote requires a validated PromotionRequest")
    request = PromotionRequest.model_validate(request.model_dump(mode="json"))
    if (
        request.human_approval.actor == "simulated_fixture"
        and not allow_simulated_fixture
    ):
        raise PromotionConflict(
            "simulated fixture promotion was not explicitly enabled"
        )
    current = store.verify(request.run_id)
    if isinstance(current, EvidenceInvalidState):
        raise PromotionEvidenceError("lineage evidence is invalid")
    if current != request.expected_head:
        events = _whole_run(store, current)
        if (
            current.seq == request.expected_head.seq + 1
            and events[-1].event_type == LineageEventType.PROMOTION_APPROVED
        ):
            return _recover_approved_promotion(
                store,
                request,
                events,
                record_artifact=record_artifact,
                reconstruct_and_retest=reconstruct_and_retest,
                record_checkpoint=record_checkpoint,
            )
        raise PromotionConflict("expected promotion head is stale")
    events = _whole_run(store, current)
    _validate_promotion_evidence(record_artifact, request, events)

    approval_digest, approval_record = _approval_record(request)
    simulated_fixture = request.human_approval.actor == "simulated_fixture"
    truth = TruthKind.SIMULATED_FIXTURE if simulated_fixture else TruthKind.HUMAN_ATTESTED
    authority = (
        LineageAuthority.SIMULATED_FIXTURE
        if simulated_fixture
        else LineageAuthority.OPERATOR_REQUEST
    )
    evidence_kind = (
        EvidenceKind.SIMULATED_FIXTURE
        if simulated_fixture
        else EvidenceKind.OPERATOR_REQUEST
    )
    source_kind = (
        SourceKind.SIMULATED_FIXTURE
        if simulated_fixture
        else SourceKind.OPERATOR_REQUEST
    )
    operator = _record(
        record_artifact,
        evidence_kind,
        approval_record,
    )
    try:
        approval = store.append(
            request.run_id,
            request.expected_head,
            canonical_json_sha256(
                {"event": "promotion.approved", "record": approval_record}
            ),
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=request.repo_id,
                base_sha=request.base_sha,
                agent_profile_id=request.agent_profile_id,
                policy_revision=request.policy_revision,
                event_type=LineageEventType.PROMOTION_APPROVED,
                truth_kind=truth,
                authority=authority,
                references=(
                    request.candidate_reference,
                    request.changeset_reference,
                    request.test_reference,
                    request.brief_reference,
                    request.decision_reference,
                    request.memory_reference,
                ),
                source_ref=SourceReference(
                    kind=source_kind,
                    id=operator.id,
                    sha256=operator.sha256,
                ),
                payload=_approval_payload(request, approval_digest),
            ),
        )
    except (LineageConflict, EvidenceInvalid) as error:
        raise PromotionConflict("promotion approval append was rejected") from error
    _successor(approval, request.expected_head, LineageEventType.PROMOTION_APPROVED)
    receipt, receipt_reference = _produce_receipt(
        store,
        request,
        approval,
        record_artifact=record_artifact,
        reconstruct_and_retest=reconstruct_and_retest,
    )
    checkpoint, checkpoint_reference = _retain_checkpoint(
        store,
        request,
        approval,
        receipt_reference,
        record_artifact=record_artifact,
        record_checkpoint=record_checkpoint,
    )
    return _complete_promotion(
        store,
        request,
        approval,
        receipt,
        receipt_reference,
        checkpoint,
        checkpoint_reference,
    )


__all__ = [
    "PreparedPromotionCandidate",
    "PromotionArtifacts",
    "PromotionCheckpointError",
    "PromotionConflict",
    "PromotionError",
    "PromotionEvidenceError",
    "PromotionOutcome",
    "PromotionReceiptV2",
    "PromotionRequest",
    "PromotionRetestError",
    "PromotionRetestRequest",
    "PromotionRetestResult",
    "SQLiteCheckpointRecorder",
    "prepare_verified_promotion",
    "promote",
]
