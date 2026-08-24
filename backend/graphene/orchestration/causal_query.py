"""Read-only causal queries over a verified mission snapshot and event stream."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import Field

from ..hashing import canonical_json_sha256
from ..models import BoundedText, FrozenModel, Identifier, RepoPath, Sha256
from .models import (
    ArtifactPublication,
    Attempt,
    EvidenceReference,
    MissionEvent,
    PLAN_AWAITING_REVIEW_UNKNOWN,
    MissionEventType,
    MissionSnapshot,
    PublicationState,
    TaskKind,
)


class CausalQueryError(ValueError):
    pass


#: Evidence reference kinds that are receipts minted by trusted authorities
#: (the check runner's ``test-receipt`` and the sanitized worker provider
#: receipt). Kept local so this read-only module never imports the runtime.
RECEIPT_REFERENCE_KINDS = frozenset({"test-receipt", "worker-provider-receipt"})


class CausalNode(FrozenModel):
    node_type: Literal["publication", "attempt", "reference", "event"]
    node_id: Identifier
    kind: Identifier | None = None
    sha256: Sha256 | None = None
    task_id: Identifier | None = None
    attempt_id: Identifier | None = None
    paths: tuple[RepoPath, ...] = ()
    resolvable: bool | None = None
    # Populated on attempt nodes only: who ran it, under which fence, and
    # which retry it was. All three come from the verified snapshot.
    worker_id: Identifier | None = None
    fencing_token: int | None = Field(default=None, ge=1)
    attempt_number: int | None = Field(default=None, ge=1)
    # Populated on prior-attempt nodes only: how that earlier attempt ended.
    state: Identifier | None = None
    result_code: Identifier | None = None


class CausalLink(FrozenModel):
    stage: Literal[
        "trigger",
        "target",
        "producer_attempt",
        "prior_attempts",
        "accepted_inputs",
        "assembly_candidate",
        "verification",
        "approval",
    ]
    status: Literal["established", "not_present", "unknown", "rejected"]
    nodes: tuple[CausalNode, ...] = ()
    event_ids: tuple[Identifier, ...] = ()
    note: BoundedText


class CausalWhyResult(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    query: str = Field(min_length=1, max_length=256)
    matched_by: Literal["path", "identifier", "none"]
    snapshot_sha256: Sha256
    event_head_sha256: Sha256 | None
    # An answer about a file is an answer about the plan it was produced
    # under. Naming the revision and its digest is what lets a reader check
    # that the work followed the graph a person actually approved.
    plan_revision: int = Field(ge=1)
    plan_sha256: Sha256
    approved_plan_revision: int | None = Field(default=None, ge=1)
    links: tuple[CausalLink, ...]
    unknowns: tuple[BoundedText, ...]


ReferenceExists = Callable[[EvidenceReference], bool | None]


def _approved_revision(events: Sequence[MissionEvent]) -> int | None:
    """The revision the last approval named, or None if none has been given."""
    for event in reversed(tuple(events)):
        if event.event_type == MissionEventType.PLAN_APPROVED:
            revision = event.payload.get("plan_revision")
            return revision if isinstance(revision, int) else None
    return None


def _validated_events(
    snapshot: MissionSnapshot, events: Sequence[MissionEvent]
) -> tuple[MissionEvent, ...]:
    ordered = tuple(sorted(events, key=lambda event: event.seq))
    if len(ordered) != snapshot.head.event_count:
        raise CausalQueryError("committed event stream does not match the verified head")
    previous = None
    for sequence, event in enumerate(ordered, 1):
        if (
            event.mission_id != snapshot.mission.mission_id
            or event.seq != sequence
            or event.previous_event_sha256 != previous
        ):
            raise CausalQueryError("committed event stream is incomplete or foreign")
        previous = event.event_sha256
    if previous != snapshot.head.event_sha256:
        raise CausalQueryError("committed event stream head does not match the snapshot")
    return ordered


def _publication_node(publication: ArtifactPublication) -> CausalNode:
    return CausalNode(
        node_type="publication",
        node_id=publication.publication_id,
        kind=publication.kind,
        sha256=publication.sha256,
        task_id=publication.task_id,
        attempt_id=publication.attempt_id,
        paths=publication.paths,
    )


def _attempt_node(attempt: Attempt, *, outcome: bool = False) -> CausalNode:
    return CausalNode(
        node_type="attempt",
        node_id=attempt.attempt_id,
        task_id=attempt.task_id,
        attempt_id=attempt.attempt_id,
        worker_id=attempt.worker_id,
        fencing_token=attempt.fencing_token,
        attempt_number=attempt.attempt_number,
        state=attempt.state.value if outcome else None,
        result_code=attempt.result_code if outcome else None,
    )


def _publication_reference_keys(
    publications: Sequence[ArtifactPublication], attempts: dict[str, Attempt]
) -> set[tuple[str, str, str]]:
    return {
        (reference.kind, reference.id, reference.sha256)
        for publication in publications
        if publication.attempt_id in attempts
        for reference in attempts[publication.attempt_id].evidence_refs
        if reference.kind == publication.kind and reference.sha256 == publication.sha256
    }


def _reference_node(
    reference: EvidenceReference,
    reference_exists: ReferenceExists,
    unknowns: list[str],
) -> CausalNode:
    try:
        resolvable = reference_exists(reference)
    except Exception as error:
        unknowns.append(
            f"Resolver failed for {reference.kind}:{reference.id}: {type(error).__name__}."
        )
        resolvable = None
    if resolvable is not None and type(resolvable) is not bool:
        raise CausalQueryError("reference resolver must return bool or None, never bytes")
    if resolvable is not True:
        unknowns.append(f"Reference availability is unknown: {reference.kind}:{reference.id}.")
    return CausalNode(
        node_type="reference",
        node_id=reference.id,
        kind=reference.kind,
        sha256=reference.sha256,
        resolvable=resolvable,
    )


def _receipt_nodes(
    attempt: Attempt,
    reference_exists: ReferenceExists,
    unknowns: list[str],
) -> tuple[CausalNode, ...]:
    """Reference nodes for the receipts an attempt's evidence binds, attempt-bound."""

    references = sorted(
        (
            reference
            for reference in attempt.evidence_refs
            if reference.kind in RECEIPT_REFERENCE_KINDS
        ),
        key=lambda item: (item.kind, item.id, item.sha256),
    )
    return tuple(
        _reference_node(reference, reference_exists, unknowns).model_copy(
            update={"task_id": attempt.task_id, "attempt_id": attempt.attempt_id}
        )
        for reference in references
    )


def _producer_receipt_nodes(
    publications: Sequence[ArtifactPublication],
    attempts: dict[str, Attempt],
    reference_exists: ReferenceExists,
    unknowns: list[str],
) -> tuple[CausalNode, ...]:
    producers = sorted(
        {item.attempt_id for item in publications if item.attempt_id in attempts}
    )
    return tuple(
        node
        for attempt_id in producers
        for node in _receipt_nodes(attempts[attempt_id], reference_exists, unknowns)
    )


def _event_ids(
    events: Sequence[MissionEvent],
    *,
    event_types: set[MissionEventType],
    publication_ids: set[str] = frozenset(),
    attempt_ids: set[str] = frozenset(),
) -> tuple[str, ...]:
    return tuple(
        event.event_id
        for event in events
        if event.event_type in event_types
        and (
            (publication_ids and event.payload.get("publication_id") in publication_ids)
            or (attempt_ids and event.payload.get("attempt_id") in attempt_ids)
        )
    )


def _trigger_links(events: Sequence[MissionEvent]) -> tuple[CausalLink, ...]:
    """One ``trigger`` link when a watcher created the mission; nothing otherwise."""

    return tuple(
        CausalLink(
            stage="trigger",
            status="established",
            nodes=(
                CausalNode(
                    node_type="event",
                    node_id=event.event_id,
                    kind=str(event.payload.get("source_kind")),
                    sha256=event.payload.get("source_sha256"),
                ),
            ),
            event_ids=(event.event_id,),
            note=(
                f"Triggered by {event.payload.get('source_kind')} "
                f"{event.payload.get('source_ref')}."
            )[:1024],
        )
        for event in events
        if event.event_type == MissionEventType.MISSION_TRIGGERED
    )


def why(
    snapshot: MissionSnapshot,
    events: Sequence[MissionEvent],
    query: str,
    *,
    reference_exists: ReferenceExists,
) -> CausalWhyResult:
    """Return public causal metadata only; artifact bytes never enter the result."""

    if type(query) is not str or not query:
        raise CausalQueryError("query must be a non-empty path or identifier")
    committed = _validated_events(snapshot, events)
    publications = tuple(snapshot.publications)
    attempts = {attempt.attempt_id: attempt for attempt in snapshot.attempts}
    tasks = {task.task_id: task for task in snapshot.tasks}
    unknowns = [
        item
        for item in snapshot.unknowns
        if item != PLAN_AWAITING_REVIEW_UNKNOWN
        or not any(
            event.event_type == MissionEventType.PLAN_APPROVED for event in committed
        )
    ]

    targets = tuple(item for item in publications if query in item.paths)
    matched_by: Literal["path", "identifier", "none"] = "path" if targets else "none"
    if not targets:
        targets = tuple(item for item in publications if item.publication_id == query)
        matched_by = "identifier" if targets else "none"
    if not targets:
        matching_references = tuple(
            (attempt.attempt_id, reference)
            for attempt in snapshot.attempts
            for reference in attempt.evidence_refs
            if reference.id == query
        )
        targets = tuple(
            publication
            for publication in publications
            if any(
                publication.attempt_id == attempt_id
                and publication.kind == reference.kind
                and publication.sha256 == reference.sha256
                for attempt_id, reference in matching_references
            )
        )
        matched_by = "identifier" if targets else "none"
    targets = tuple(sorted(set(targets), key=lambda item: item.publication_id))

    trigger_links = _trigger_links(committed)
    if not targets:
        unknowns.append(f"No committed publication or artifact matches {query}.")
        links = trigger_links + tuple(
            CausalLink(
                stage=stage,
                status="unknown",
                note=f"No evidence establishes {stage.replace('_', ' ')} for this query.",
            )
            for stage in (
                "target",
                "producer_attempt",
                "accepted_inputs",
                "assembly_candidate",
                "verification",
                "approval",
            )
        )
        return CausalWhyResult(
            mission_id=snapshot.mission.mission_id,
            query=query,
            matched_by="none",
            snapshot_sha256=snapshot.snapshot_sha256,
            event_head_sha256=snapshot.head.event_sha256,
            plan_revision=snapshot.plan.revision,
            plan_sha256=canonical_json_sha256(snapshot.plan.model_dump(mode="json")),
            approved_plan_revision=_approved_revision(committed),
            links=links,
            unknowns=tuple(sorted(set(unknowns))),
        )

    target_ids = {item.publication_id for item in targets}
    target_attempts = tuple(
        sorted(
            (attempts[item.attempt_id] for item in targets if item.attempt_id in attempts),
            key=lambda item: item.attempt_id,
        )
    )
    links = [
        *trigger_links,
        CausalLink(
            stage="target",
            status="established",
            nodes=tuple(_publication_node(item) for item in targets),
            event_ids=_event_ids(
                committed,
                event_types={
                    MissionEventType.ARTIFACT_PUBLISHED,
                    MissionEventType.ARTIFACT_ACCEPTED,
                },
                publication_ids=target_ids,
            ),
            note="Committed publication metadata matches the query.",
        )
    ]
    missing_attempts = target_ids - {
        publication.publication_id
        for publication in targets
        if publication.attempt_id in attempts
    }
    if missing_attempts:
        unknowns.append("One or more target producer attempts are missing from the snapshot.")
    links.append(
        CausalLink(
            stage="producer_attempt",
            status="established" if target_attempts else "unknown",
            nodes=tuple(
                node
                for attempt in target_attempts
                for node in (
                    _attempt_node(attempt),
                    *_receipt_nodes(attempt, reference_exists, unknowns),
                )
            ),
            event_ids=_event_ids(
                committed,
                event_types={MissionEventType.TASK_STARTED, MissionEventType.TASK_COMPLETED},
                attempt_ids={item.attempt_id for item in target_attempts},
            ),
            note=(
                "The verified snapshot binds each target to its producer attempt."
                if target_attempts
                else "No producer attempt is present for the target."
            ),
        )
    )
    # Earlier attempts of the producing tasks: a retry's history is part of
    # the explanation, and each earlier fence is strictly lower than the
    # producer's. They published nothing that the target depends on.
    prior_attempts = tuple(
        sorted(
            (
                attempt
                for attempt in snapshot.attempts
                if any(
                    attempt.task_id == producer.task_id
                    and attempt.attempt_number < producer.attempt_number
                    for producer in target_attempts
                )
            ),
            key=lambda item: (item.task_id, item.attempt_number),
        )
    )
    links.append(
        CausalLink(
            stage="prior_attempts",
            status="established" if prior_attempts else "not_present",
            nodes=tuple(
                node
                for attempt in prior_attempts
                for node in (
                    _attempt_node(attempt, outcome=True),
                    *_receipt_nodes(attempt, reference_exists, unknowns),
                )
            ),
            event_ids=_event_ids(
                committed,
                event_types={
                    MissionEventType.TASK_STARTED,
                    MissionEventType.TASK_RETRIED,
                    MissionEventType.TASK_FAILED,
                },
                attempt_ids={item.attempt_id for item in prior_attempts},
            ),
            note=(
                "Earlier attempts of the producing task ended without an accepted "
                "publication; the producer above ran under a strictly higher fence."
                if prior_attempts
                else "The producer attempt was the task's first."
            ),
        )
    )
    input_references = tuple(
        sorted(
            {reference for attempt in target_attempts for reference in attempt.input_publications},
            key=lambda item: (item.kind, item.id, item.sha256),
        )
    )
    links.append(
        CausalLink(
            stage="accepted_inputs",
            status="established" if input_references else "not_present",
            nodes=tuple(
                _reference_node(reference, reference_exists, unknowns)
                for reference in input_references
            ),
            note=(
                "Producer attempts declare these exact accepted inputs."
                if input_references
                else "Producer attempts declare no accepted inputs."
            ),
        )
    )

    target_refs = _publication_reference_keys(targets, attempts)
    if not target_refs:
        unknowns.append("Target publication evidence references are missing.")
    assembly_attempts = tuple(
        attempt
        for attempt in snapshot.attempts
        if tasks.get(attempt.task_id) is not None
        and tasks[attempt.task_id].kind == TaskKind.ASSEMBLY
        and (
            attempt.attempt_id in {item.attempt_id for item in targets}
            or any(
                (reference.kind, reference.id, reference.sha256) in target_refs
                for reference in attempt.input_publications
            )
        )
    )
    assembly_publications = tuple(
        item
        for item in publications
        if item.state == PublicationState.ACCEPTED
        and item.attempt_id in {attempt.attempt_id for attempt in assembly_attempts}
    )
    links.append(
        CausalLink(
            stage="assembly_candidate",
            status="established" if assembly_publications else "unknown",
            nodes=(
                *(_publication_node(item) for item in assembly_publications),
                *_producer_receipt_nodes(
                    assembly_publications, attempts, reference_exists, unknowns
                ),
            ),
            event_ids=_event_ids(
                committed,
                event_types={MissionEventType.ASSEMBLY_COMPLETED},
                attempt_ids={attempt.attempt_id for attempt in assembly_attempts},
            ),
            note=(
                "Accepted assembly output consumes the target publication."
                if assembly_publications
                else "No accepted assembly candidate is causally linked to the target."
            ),
        )
    )

    assembly_refs = _publication_reference_keys(assembly_publications, attempts)
    if assembly_publications and not assembly_refs:
        unknowns.append("Assembly publication evidence references are missing.")
    verification_attempts = tuple(
        attempt
        for attempt in snapshot.attempts
        if tasks.get(attempt.task_id) is not None
        and tasks[attempt.task_id].kind == TaskKind.VERIFICATION
        and any(
            (reference.kind, reference.id, reference.sha256) in assembly_refs
            for reference in attempt.input_publications
        )
    )
    verification_publications = tuple(
        item
        for item in publications
        if item.state == PublicationState.ACCEPTED
        and item.attempt_id in {attempt.attempt_id for attempt in verification_attempts}
    )
    links.append(
        CausalLink(
            stage="verification",
            status="established" if verification_publications else "unknown",
            nodes=(
                *(_publication_node(item) for item in verification_publications),
                *_producer_receipt_nodes(
                    verification_publications, attempts, reference_exists, unknowns
                ),
            ),
            event_ids=_event_ids(
                committed,
                event_types={MissionEventType.VERIFICATION_COMPLETED},
                attempt_ids={attempt.attempt_id for attempt in verification_attempts},
            ),
            note=(
                "Accepted verification output consumes the assembly candidate."
                if verification_publications
                else "No accepted verification is causally linked to the assembly candidate."
            ),
        )
    )

    candidate_ids = {item.publication_id for item in assembly_publications}
    approval_events = tuple(
        event
        for event in committed
        if event.event_type
        in {
            MissionEventType.FINAL_CANDIDATE_APPROVED,
            MissionEventType.FINAL_CANDIDATE_REJECTED,
        }
        and any(reference.id in candidate_ids for reference in event.references)
    )
    approved = tuple(
        event
        for event in approval_events
        if event.event_type == MissionEventType.FINAL_CANDIDATE_APPROVED
    )
    rejected = tuple(
        event
        for event in approval_events
        if event.event_type == MissionEventType.FINAL_CANDIDATE_REJECTED
    )
    decision_events = approved or rejected
    links.append(
        CausalLink(
            stage="approval",
            status="established" if approved else "rejected" if rejected else "unknown",
            nodes=tuple(
                CausalNode(node_type="event", node_id=event.event_id)
                for event in decision_events
            ),
            event_ids=tuple(event.event_id for event in decision_events),
            note=(
                "A committed final approval references the assembly candidate."
                if approved
                else "A committed final rejection references the assembly candidate."
                if rejected
                else "No committed final decision references the assembly candidate."
            ),
        )
    )
    for link in links:
        if link.status == "unknown":
            unknowns.append(link.note)
    return CausalWhyResult(
        mission_id=snapshot.mission.mission_id,
        query=query,
        matched_by=matched_by,
        snapshot_sha256=snapshot.snapshot_sha256,
        event_head_sha256=snapshot.head.event_sha256,
        plan_revision=snapshot.plan.revision,
        plan_sha256=canonical_json_sha256(snapshot.plan.model_dump(mode="json")),
        approved_plan_revision=_approved_revision(committed),
        links=tuple(links),
        unknowns=tuple(sorted(set(unknowns))),
    )


__all__ = (
    "RECEIPT_REFERENCE_KINDS",
    "CausalLink",
    "CausalNode",
    "CausalQueryError",
    "CausalWhyResult",
    "why",
)
