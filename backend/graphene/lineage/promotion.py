from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..hashing import canonical_json_sha256
from ..models import (
    AgentProfileId,
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    GitSha,
    HeadCheckpoint,
    HumanDecision,
    Identifier,
    LineageAuthority,
    LineageEventType,
    LineageRunState,
    MemoryDecisionValue,
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


ArtifactRecorder = Callable[[EvidenceKind, Mapping[str, Any]], EvidenceReference]
CheckpointRecorder = Callable[[HeadCheckpoint], HeadCheckpoint]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PromotionRequest(_Frozen):
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
    human_approval: HumanDecision

    @model_validator(mode="after")
    def bindings_are_exact_and_human(self) -> PromotionRequest:
        expected = (
            (
                self.candidate_reference,
                EvidenceKind.EVIDENCE_BLOB,
                self.candidate_sha256,
            ),
            (
                self.changeset_reference,
                EvidenceKind.CHANGESET,
                self.changeset_sha256,
            ),
            (
                self.test_reference,
                EvidenceKind.TEST_RECEIPT,
                self.test_receipt_sha256,
            ),
            (
                self.brief_reference,
                EvidenceKind.CONTEXT_BRIEF,
                self.brief_sha256,
            ),
            (
                self.decision_reference,
                EvidenceKind.HANDOFF_DECISION,
                self.decision_sha256,
            ),
            (
                self.memory_reference,
                EvidenceKind.MEMORY_REVISION,
                self.memory_sha256,
            ),
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
        if (
            self.human_approval.actor != "human"
            or self.human_approval.value != MemoryDecisionValue.APPROVE
            or self.human_approval.purpose != "promotion"
            or self.human_approval.bound_digest != self.candidate_patch_sha256
        ):
            raise ValueError("promotion requires exact human approval")
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
    changeset_sha256: Sha256
    test_receipt_sha256: Sha256
    brief_sha256: Sha256
    decision_sha256: Sha256
    memory_sha256: Sha256
    human_approval_sha256: Sha256
    artifact_references: tuple[EvidenceReference, ...]


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
    changeset_sha256: Sha256
    test_receipt_sha256: Sha256
    brief_sha256: Sha256
    decision_sha256: Sha256
    memory_sha256: Sha256
    human_approval_sha256: Sha256
    artifact_references: tuple[EvidenceReference, ...]
    authoritative_test_receipt_sha256: Sha256
    reconstructed_commit_sha: GitSha
    passed: Literal[True]
    timed_out: Literal[False]
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def receipt_is_canonical(self) -> PromotionReceiptV2:
        if self.approval_head.run_id != self.run_id or self.receipt_sha256 != (
            canonical_json_sha256(
                self.model_dump(mode="json", exclude={"receipt_sha256"})
            )
        ):
            raise ValueError("promotion receipt binding or digest does not match")
        return self

    @classmethod
    def create(cls, **values: Any) -> PromotionReceiptV2:
        values = {**values}
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


ReconstructAndRetest = Callable[[PromotionRetestRequest], PromotionReceiptV2]


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


def promote(
    store: PromotionStore,
    request: PromotionRequest,
    *,
    record_artifact: ArtifactRecorder,
    reconstruct_and_retest: ReconstructAndRetest,
    record_checkpoint: CheckpointRecorder,
) -> PromotionOutcome:
    """Run the non-circular N / N+1 / N+2 promotion protocol."""

    if not isinstance(request, PromotionRequest):
        raise TypeError("promote requires a validated PromotionRequest")
    request = PromotionRequest.model_validate(request.model_dump(mode="json"))
    events = _verify_head(store, request.expected_head)
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
    candidate_observed = any(
        event.event_type == LineageEventType.CANDIDATE_CREATED
        and request.candidate_reference in event.references
        and event.payload.get("candidate_id") == request.candidate_id
        and event.payload.get("candidate_patch_sha256")
        == request.candidate_patch_sha256
        and event.payload.get("candidate_tree_sha256") == request.candidate_tree_sha256
        for event in events
    )
    changeset_observed = any(
        event.event_type == LineageEventType.CHANGESET_PARSED
        and request.changeset_reference in event.references
        and event.payload.get("candidate_patch_sha256")
        == request.candidate_patch_sha256
        for event in events
    )
    test_observed = any(
        event.event_type == LineageEventType.TEST_RECEIPT_CREATED
        and request.test_reference in event.references
        and event.payload.get("receipt_sha256") == request.test_receipt_sha256
        and event.payload.get("passed") is True
        for event in events
    )
    context_observed = any(
        event.event_type == LineageEventType.CONTEXT_COMPILED
        and request.brief_reference in event.references
        and request.decision_reference in event.references
        and event.payload.get("brief_sha256") == request.brief_sha256
        and event.payload.get("decision_sha256") == request.decision_sha256
        for event in events
    )
    memory_observed = any(
        event.event_type == LineageEventType.MEMORY_APPROVED
        and request.memory_reference in event.references
        and event.payload.get("memory_sha256") == request.memory_sha256
        for event in events
    )
    if not (
        required_references <= observed_references
        and candidate_observed
        and changeset_observed
        and test_observed
        and context_observed
        and memory_observed
    ):
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

    approval_digest = canonical_json_sha256(
        request.human_approval.model_dump(mode="json")
    )
    approval_record = {
        "schema_version": 2,
        "action": "promotion.approved",
        "run_id": request.run_id,
        "expected_head": request.expected_head.model_dump(mode="json"),
        "human_approval": request.human_approval.model_dump(mode="json"),
        "human_approval_sha256": approval_digest,
        "bindings": {
            key: value
            for key, value in request.model_dump(mode="json").items()
            if key
            not in {
                "schema_version",
                "expected_head",
                "human_approval",
            }
        },
    }
    operator = _record(
        record_artifact,
        EvidenceKind.OPERATOR_REQUEST,
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
                truth_kind=TruthKind.HUMAN_ATTESTED,
                authority=LineageAuthority.OPERATOR_REQUEST,
                references=(
                    request.candidate_reference,
                    request.changeset_reference,
                    request.test_reference,
                    request.brief_reference,
                    request.decision_reference,
                    request.memory_reference,
                ),
                source_ref=SourceReference(
                    kind=SourceKind.OPERATOR_REQUEST,
                    id=operator.id,
                    sha256=operator.sha256,
                ),
                payload={
                    "candidate_patch_sha256": request.candidate_patch_sha256,
                    "decision_id": request.human_approval.decision_id,
                    "decision_sha256": approval_digest,
                    "expected_head_sha256": request.expected_head.event_sha256,
                    "status": "approved",
                },
            ),
        )
    except (LineageConflict, EvidenceInvalid) as error:
        raise PromotionConflict("promotion approval append was rejected") from error
    _successor(approval, request.expected_head, LineageEventType.PROMOTION_APPROVED)
    approval_head = _head(approval)
    retest = _retest_request(request, approval, approval_digest)

    try:
        raw_receipt = reconstruct_and_retest(retest)
    except Exception as error:
        _deny_if_current(
            store,
            record_artifact,
            request,
            approval,
            "reconstruction_failed",
        )
        raise PromotionRetestError("authoritative reconstruction failed") from error
    try:
        if not isinstance(raw_receipt, PromotionReceiptV2):
            raise TypeError("callback did not return PromotionReceiptV2")
        receipt = PromotionReceiptV2.model_validate(raw_receipt.model_dump(mode="json"))
    except (TypeError, ValidationError):
        receipt = None
    if receipt is None or not _receipt_matches(receipt, retest):
        _deny_if_current(
            store,
            record_artifact,
            request,
            approval,
            "retest_binding_mismatch",
        )
        raise PromotionRetestError("authoritative retest receipt does not match")

    try:
        receipt_reference = _record(
            record_artifact,
            EvidenceKind.PROMOTION_RECEIPT,
            receipt.model_dump(mode="json"),
        )
    except Exception:
        _deny_if_current(
            store,
            record_artifact,
            request,
            approval,
            "receipt_persistence_failed",
        )
        raise

    _verify_head(store, approval_head)
    try:
        completion = store.append(
            request.run_id,
            approval_head,
            canonical_json_sha256(
                {
                    "event": "promotion.completed",
                    "receipt_id": receipt_reference.id,
                    "receipt_sha256": receipt_reference.sha256,
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

    checkpoint_payload = {
        "schema_version": 2,
        "checkpoint_id": "checkpoint_"
        + canonical_json_sha256(
            {
                "run_id": request.run_id,
                "seq": final_head.seq,
                "head": final_head.event_sha256,
                "receipt": receipt_reference.sha256,
            }
        )[:32],
        "run_id": request.run_id,
        "expected_seq": final_head.seq,
        "event_head_sha256": final_head.event_sha256,
        "purpose": "promotion_final",
        "bound_artifact_kind": EvidenceKind.PROMOTION_RECEIPT,
        "bound_artifact_id": receipt_reference.id,
        "bound_artifact_sha256": receipt_reference.sha256,
        "server_recorded_at": _now(),
    }
    checkpoint = HeadCheckpoint(
        **checkpoint_payload,
        checkpoint_sha256=canonical_json_sha256(
            {
                **checkpoint_payload,
                "bound_artifact_kind": EvidenceKind.PROMOTION_RECEIPT.value,
                "server_recorded_at": checkpoint_payload["server_recorded_at"]
                .isoformat()
                .replace("+00:00", "Z"),
            }
        ),
    )
    try:
        retained = record_checkpoint(checkpoint)
    except Exception as error:
        raise PromotionCheckpointError("final promotion checkpoint failed") from error
    if retained != checkpoint or store.verify(request.run_id) != final_head:
        raise PromotionCheckpointError("final promotion checkpoint was not retained")
    return PromotionOutcome(
        approval_event=approval,
        receipt=receipt,
        receipt_reference=receipt_reference,
        completion_event=completion,
        checkpoint=checkpoint,
        final_head=final_head,
    )


__all__ = [
    "PromotionCheckpointError",
    "PromotionConflict",
    "PromotionError",
    "PromotionEvidenceError",
    "PromotionOutcome",
    "PromotionReceiptV2",
    "PromotionRequest",
    "PromotionRetestError",
    "PromotionRetestRequest",
    "promote",
]
