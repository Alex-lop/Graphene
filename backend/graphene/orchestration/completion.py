"""Credential-free completion reducers for the cloud dispatch path.

Trust boundary (convergence directive §6.3): an authenticated remote executor
is part of the trusted computing base for cloud check results. The coordinator
recomputes *bindings* — the receipt's mission/task/attempt/plan/fence/policy
identity, the exact publication envelopes, and the receipt-to-evidence digest —
not test results: ``template_sha256``, ``candidate_tree_sha256``,
``output_sha256``, ``exit_code``, ``timed_out``, and ``cleanup_complete`` are
attested by the executor and are never independently re-executed or recomputed
server-side, and the ``test-receipt`` evidence reference binds the receipt to
itself by hashing the receipt's own canonical JSON. A hand-built passing
receipt with arbitrary digests is therefore accepted at this boundary by
design. To keep that provenance in the hash chain, every successful cloud
completion records ``check_authority: "executor_attested"`` in the committed
``task.completed`` event payload, where a local SQLite mission's checks run
under the coordinator's own trusted check runner (authority label
``trusted_check``; the local event payload is owned by ``store.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..artifact_envelope import DirectArtifactInputV2
from ..hashing import canonical_json_sha256
from ..models import TruthKind
from .cloud_protocol import DispatchOutboxRecord, ExecutorArtifactReference
from .evidence import TrustedCheckReceipt
from .models import (
    Attempt,
    AttemptResult,
    AttemptState,
    ArtifactPublication,
    GenericEvidenceLink,
    Lease,
    Mission,
    MissionAuthority,
    MissionEventInput,
    MissionEventType,
    MissionSnapshot,
    MissionStatus,
    PublicationState,
    PublishedArtifactReferenceV2,
    Task,
    TaskKind,
    TaskState,
)
from .reducer import transition_mission, transition_task
from .store import MissionConflict


@dataclass(frozen=True, slots=True)
class FailedCompletionTransition:
    mission: Mission
    tasks: tuple[Task, ...]
    attempts: tuple[Attempt, ...]
    leases: tuple[Lease, ...]
    publications: tuple[ArtifactPublication, ...]
    drafts: tuple[MissionEventInput, ...]


def _lease_authority_matches(materialized: Lease, active: Lease) -> bool:
    return (
        (
            materialized.lease_id,
            materialized.mission_id,
            materialized.plan_revision,
            materialized.task_id,
            materialized.attempt_id,
            materialized.owner,
            materialized.capability,
            materialized.write_paths,
            materialized.fencing_token,
            materialized.issued_at,
        )
        == (
            active.lease_id,
            active.mission_id,
            active.plan_revision,
            active.task_id,
            active.attempt_id,
            active.owner,
            active.capability,
            active.write_paths,
            active.fencing_token,
            active.issued_at,
        )
        and materialized.released_at is None
        and active.released_at is None
        and materialized.heartbeat_at <= active.heartbeat_at
        and materialized.expires_at <= active.expires_at
    )


def reduce_failed_completion(
    snapshot: MissionSnapshot,
    dispatch: DispatchOutboxRecord,
    result: AttemptResult,
    *,
    recorded_at: datetime,
    retry_backoff_seconds: int,
) -> FailedCompletionTransition:
    """Apply the credential-free failed-attempt subset shared with SQLite."""

    if result.succeeded:
        raise MissionConflict(
            "successful completion requires private artifact-spool verification"
        )
    if result.evidence_link is not None or result.evidence_refs or result.publications:
        raise MissionConflict(
            "credential-free failed completion cannot carry artifact evidence"
        )
    if result.session_id != dispatch.session_id or result.invocation_id is None:
        raise MissionConflict("attempt result runtime binding is unavailable")
    if snapshot.mission.status != MissionStatus.RUNNING:
        raise MissionConflict("mission is not accepting attempt completion")

    tasks = {item.task_id: item for item in snapshot.tasks}
    attempts = {item.attempt_id: item for item in snapshot.attempts}
    leases = {item.lease_id: item for item in snapshot.leases}
    task = tasks.get(dispatch.task_id)
    attempt = attempts.get(dispatch.attempt_id)
    lease = leases.get(dispatch.lease.lease_id)
    if task is None or attempt is None or lease is None:
        raise MissionConflict("materialized attempt binding is unavailable")
    if (
        attempt.state != AttemptState.RUNNING
        or task.state
        != (
            TaskState.VERIFYING
            if task.kind == TaskKind.VERIFICATION
            else TaskState.RUNNING
        )
        or task.attempt_count != attempt.attempt_number
        or (
            attempt.mission_id,
            attempt.plan_revision,
            attempt.task_id,
            attempt.attempt_number,
            attempt.worker_id,
            attempt.lease_id,
            attempt.fencing_token,
            attempt.input_publications,
        )
        != (
            dispatch.mission_id,
            dispatch.plan_revision,
            dispatch.task_id,
            dispatch.attempt_number,
            dispatch.worker_id,
            dispatch.lease.lease_id,
            dispatch.lease.fencing_token,
            dispatch.accepted_inputs,
        )
        or not _lease_authority_matches(lease, dispatch.lease)
        or task.kind != dispatch.task_kind
    ):
        raise MissionConflict("materialized dispatch binding is stale")

    failed_attempt = Attempt.model_validate(
        {
            **attempt.model_dump(mode="json"),
            "ended_at": recorded_at,
            "invocation_id": result.invocation_id,
            "result_code": result.result_code,
            "session_id": result.session_id,
            "state": AttemptState.FAILED,
        }
    )
    released = Lease.model_validate(
        {
            **dispatch.lease.model_dump(mode="json"),
            "released_at": recorded_at,
            "release_reason": "failed",
        }
    )
    drafts: list[MissionEventInput] = []
    mission = snapshot.mission
    if result.retryable and task.attempt_count < task.attempt_limit:
        target = transition_task(task.state, TaskState.RETRYING)
        retry_at = recorded_at + timedelta(seconds=retry_backoff_seconds)
        next_task = Task.model_validate(
            {
                **task.model_dump(mode="json"),
                "retry_at": retry_at,
                "state": target,
            }
        )
        drafts.append(
            MissionEventInput(
                event_type=MissionEventType.TASK_RETRIED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=MissionAuthority.SCHEDULER,
                payload={
                    "attempt_id": attempt.attempt_id,
                    "result_code": result.result_code,
                    "retry_at": retry_at.isoformat(),
                    "state": target.value,
                    "task_id": task.task_id,
                },
            )
        )
    else:
        target = transition_task(task.state, TaskState.FAILED)
        next_task = Task.model_validate(
            {**task.model_dump(mode="json"), "state": target}
        )
        drafts.append(
            MissionEventInput(
                event_type=MissionEventType.TASK_FAILED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=MissionAuthority.SCHEDULER,
                payload={
                    "attempt_id": attempt.attempt_id,
                    "result_code": result.result_code,
                    "state": target.value,
                    "task_id": task.task_id,
                },
            )
        )
        kind_event = {
            TaskKind.ASSEMBLY: MissionEventType.ASSEMBLY_FAILED,
            TaskKind.VERIFICATION: MissionEventType.VERIFICATION_FAILED,
        }.get(task.kind)
        if kind_event is not None:
            drafts.append(
                MissionEventInput(
                    event_type=kind_event,
                    truth_kind=TruthKind.SERVER_DERIVED,
                    authority=MissionAuthority.SCHEDULER,
                    payload={
                        "attempt_id": attempt.attempt_id,
                        "result_code": result.result_code,
                        "task_id": task.task_id,
                    },
                )
            )
        mission = Mission.model_validate(
            {
                **mission.model_dump(mode="json"),
                "status": transition_mission(
                    mission.status, MissionStatus.FAILED
                ),
            }
        )

    tasks[task.task_id] = next_task
    attempts[attempt.attempt_id] = failed_attempt
    leases[lease.lease_id] = released
    return FailedCompletionTransition(
        mission=mission,
        tasks=tuple(tasks[key] for key in sorted(tasks)),
        attempts=tuple(attempts[key] for key in sorted(attempts)),
        leases=tuple(leases[key] for key in sorted(leases)),
        publications=snapshot.publications,
        drafts=tuple(drafts),
    )


def reduce_successful_completion(
    snapshot: MissionSnapshot,
    dispatch: DispatchOutboxRecord,
    result: AttemptResult,
    artifacts: tuple[ExecutorArtifactReference, ...],
    check_receipt: TrustedCheckReceipt,
    *,
    recorded_at: datetime,
) -> FailedCompletionTransition:
    """Apply the bounded generic-v1 success transition trusted to one executor."""

    if (
        not result.succeeded
        or not isinstance(result.evidence_link, GenericEvidenceLink)
        or result.session_id != dispatch.session_id
        or result.invocation_id is None
    ):
        raise MissionConflict("successful result runtime binding is unavailable")
    if tuple(item.reference for item in artifacts) != result.evidence_refs or any(
        item.executor_id != dispatch.executor_id for item in artifacts
    ):
        raise MissionConflict("successful evidence is outside the executor spool")
    if sum(item.byte_count for item in artifacts) > snapshot.mission.resource_budget.max_artifact_bytes:
        raise MissionConflict("attempt artifact bytes exceed the mission budget")

    tasks = {item.task_id: item for item in snapshot.tasks}
    attempts = {item.attempt_id: item for item in snapshot.attempts}
    leases = {item.lease_id: item for item in snapshot.leases}
    task = tasks.get(dispatch.task_id)
    attempt = attempts.get(dispatch.attempt_id)
    lease = leases.get(dispatch.lease.lease_id)
    expected_state = (
        TaskState.VERIFYING
        if task is not None and task.kind == TaskKind.VERIFICATION
        else TaskState.RUNNING
    )
    if (
        snapshot.mission.status != MissionStatus.RUNNING
        or task is None
        or attempt is None
        or lease is None
        or task.evidence_adapter != "generic_v1"
        or attempt.state != AttemptState.RUNNING
        or task.state != expected_state
        or task.attempt_count != attempt.attempt_number
        or (
            attempt.mission_id,
            attempt.plan_revision,
            attempt.task_id,
            attempt.attempt_number,
            attempt.worker_id,
            attempt.lease_id,
            attempt.fencing_token,
            attempt.input_publications,
        )
        != (
            dispatch.mission_id,
            dispatch.plan_revision,
            dispatch.task_id,
            dispatch.attempt_number,
            dispatch.worker_id,
            dispatch.lease.lease_id,
            dispatch.lease.fencing_token,
            dispatch.accepted_inputs,
        )
        or not _lease_authority_matches(lease, dispatch.lease)
        or task.kind != dispatch.task_kind
    ):
        raise MissionConflict("materialized dispatch binding is stale")

    expected_outputs = {(item.name, item.kind): item for item in task.expected_outputs}
    actual = {(item.output_name, item.kind): item for item in result.publications}
    if set(actual) != set(expected_outputs) or any(
        actual[key].paths != expected_outputs[key].paths for key in expected_outputs
    ):
        raise MissionConflict("attempt publications do not match task outputs")
    publication_references = tuple(
        reference
        for publication in result.publications
        for reference in result.evidence_refs
        if reference.kind == publication.kind
        and reference.sha256 == publication.sha256
    )
    if len(publication_references) != len(result.publications):
        raise MissionConflict("each publication requires one exact artifact reference")
    publication_artifacts = tuple(
        sorted(
            (
                publication.artifact
                for publication in result.publications
                if publication.artifact is not None
            ),
            key=lambda item: item.artifact_envelope_sha256,
        )
    )
    if (
        len(publication_artifacts) != len(result.publications)
        or result.artifact_envelopes != publication_artifacts
    ):
        raise MissionConflict("publication requires exact V2 artifact envelopes")
    direct_inputs = tuple(
        DirectArtifactInputV2(
            publication_id=item.publication_id,
            producer_task_id=item.producer_task_id,
            output_name=item.output_name,
            artifact_envelope_sha256=item.artifact_envelope_sha256,
        )
        for item in attempt.input_publications
        if isinstance(item, PublishedArtifactReferenceV2)
    )
    if len(direct_inputs) != len(
        tuple(
            item
            for item in attempt.input_publications
            if not (hasattr(item, "kind") and item.kind == "operator-input")
        )
    ):
        raise MissionConflict("legacy publication input has no V2 envelope identity")
    plan_sha256 = canonical_json_sha256(snapshot.plan.model_dump(mode="json"))
    for publication in result.publications:
        assert publication.artifact is not None
        sources = tuple(
            item
            for item in artifacts
            if item.reference.kind == publication.kind
            and item.reference.id == publication.artifact.artifact_id
            and item.reference.sha256 == publication.sha256
        )
        if len(sources) != 1 or sources[0].envelope is None:
            raise MissionConflict("publication V2 envelope observation is unavailable")
        envelope = sources[0].envelope
        if (
            envelope.artifact_envelope_sha256
            != publication.artifact.artifact_envelope_sha256
            or envelope.mission_id != attempt.mission_id
            or envelope.plan_revision != attempt.plan_revision
            or envelope.plan_sha256 != plan_sha256
            or envelope.task_id != attempt.task_id
            or envelope.attempt_id != attempt.attempt_id
            or envelope.fencing_token != attempt.fencing_token
            or envelope.policy_sha256 != snapshot.policy.policy_sha256
            or envelope.base_git_commit != snapshot.policy.base_sha
            or envelope.direct_inputs != direct_inputs
            or envelope.output_name != publication.output_name
            or envelope.artifact_kind != publication.kind
            or envelope.created_by != "trusted-worker-wrapper"
        ):
            raise MissionConflict("publication artifact envelope binding changed")
    receipt_references = tuple(
        item
        for item in result.evidence_refs
        if item.kind == "test-receipt"
        and item.sha256
        == canonical_json_sha256(check_receipt.model_dump(mode="json"))
    )
    candidates = (
        attempt.input_publications
        if task.kind == TaskKind.VERIFICATION
        else publication_artifacts
    )
    if (
        len(task.acceptance_checks) != 1
        or len(receipt_references) != 1
        or check_receipt.mission_id != attempt.mission_id
        or check_receipt.task_id != attempt.task_id
        or check_receipt.attempt_id != attempt.attempt_id
        or check_receipt.plan_revision != attempt.plan_revision
        or check_receipt.fencing_token != attempt.fencing_token
        or check_receipt.policy_sha256 != snapshot.policy.policy_sha256
        or check_receipt.base_sha != snapshot.policy.base_sha
        or check_receipt.template_id != task.acceptance_checks[0]
        or check_receipt.accepted_input_references != attempt.input_publications
        or check_receipt.candidate_references != candidates
        or check_receipt.result_code != result.result_code
        or result.result_code != "passed"
    ):
        raise MissionConflict("trusted check receipt is not bound to the attempt")

    publications = {item.publication_id: item for item in snapshot.publications}
    drafts: list[MissionEventInput] = []
    for key in sorted(actual):
        publication = actual[key]
        publication_id = "publication_" + canonical_json_sha256(
            {
                "attempt_id": attempt.attempt_id,
                "kind": publication.kind,
                "output_name": publication.output_name,
                "sha256": publication.sha256,
            }
        )[:32]
        consumers = tuple(
            item.task_id
            for item in snapshot.tasks
            if any(
                requirement.producer_task_id == task.task_id
                and requirement.name == publication.output_name
                and requirement.kind == publication.kind
                for requirement in item.inputs
            )
        )
        accepted = ArtifactPublication(
            **publication.model_dump(mode="json"),
            publication_id=publication_id,
            mission_id=attempt.mission_id,
            plan_revision=attempt.plan_revision,
            task_id=task.task_id,
            attempt_id=attempt.attempt_id,
            state=PublicationState.ACCEPTED,
            consumers=consumers,
        )
        if publication_id in publications:
            raise MissionConflict("publication identity is already committed")
        publications[publication_id] = accepted
        reference = next(
            item
            for item in publication_references
            if item.kind == accepted.kind and item.sha256 == accepted.sha256
        )
        common = {
            "attempt_id": attempt.attempt_id,
            "kind": accepted.kind,
            "output_name": accepted.output_name,
            "publication_id": publication_id,
            "sha256": accepted.sha256,
            "task_id": task.task_id,
        }
        drafts.extend(
            (
                MissionEventInput(
                    event_type=MissionEventType.ARTIFACT_PUBLISHED,
                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                    authority=MissionAuthority.WORKER_ADAPTER,
                    references=(reference,),
                    payload={**common, "status": "published"},
                ),
                MissionEventInput(
                    event_type=MissionEventType.ARTIFACT_ACCEPTED,
                    truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                    authority=MissionAuthority.POLICY_ENGINE,
                    references=(reference,),
                    payload={**common, "status": "accepted"},
                ),
            )
        )

    attempts[attempt.attempt_id] = Attempt.model_validate(
        {
            **attempt.model_dump(mode="json"),
            "ended_at": recorded_at,
            "evidence_link": result.evidence_link,
            "evidence_refs": result.evidence_refs,
            "invocation_id": result.invocation_id,
            "result_code": result.result_code,
            "session_id": result.session_id,
            "state": AttemptState.COMMITTED,
        }
    )
    leases[lease.lease_id] = Lease.model_validate(
        {
            **dispatch.lease.model_dump(mode="json"),
            "released_at": recorded_at,
            "release_reason": "completed",
        }
    )
    target = transition_task(task.state, TaskState.DONE)
    tasks[task.task_id] = Task.model_validate(
        {**task.model_dump(mode="json"), "state": target}
    )
    drafts.append(
        MissionEventInput(
            event_type=MissionEventType.TASK_COMPLETED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=MissionAuthority.SCHEDULER,
            payload={
                "attempt_id": attempt.attempt_id,
                # See the module docstring: cloud check results are attested by
                # the authenticated executor, not recomputed server-side.
                "check_authority": "executor_attested",
                "evidence_kind": result.evidence_link.kind,
                "result_code": result.result_code,
                "state": target.value,
                "task_id": task.task_id,
            },
        )
    )
    kind_event = {
        TaskKind.ASSEMBLY: MissionEventType.ASSEMBLY_COMPLETED,
        TaskKind.VERIFICATION: MissionEventType.VERIFICATION_COMPLETED,
    }.get(task.kind)
    if kind_event is not None:
        drafts.append(
            MissionEventInput(
                event_type=kind_event,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=MissionAuthority.SCHEDULER,
                payload={"attempt_id": attempt.attempt_id, "task_id": task.task_id},
            )
        )
    for dependent_id in sorted(
        item.task_id for item in snapshot.tasks if task.task_id in item.dependencies
    ):
        drafts.append(
            MissionEventInput(
                event_type=MissionEventType.DEPENDENCY_SATISFIED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=MissionAuthority.SCHEDULER,
                payload={
                    "attempt_id": attempt.attempt_id,
                    "dependency_id": task.task_id,
                    "task_id": dependent_id,
                },
            )
        )
    return FailedCompletionTransition(
        mission=snapshot.mission,
        tasks=tuple(tasks[key] for key in sorted(tasks)),
        attempts=tuple(attempts[key] for key in sorted(attempts)),
        leases=tuple(leases[key] for key in sorted(leases)),
        publications=tuple(publications[key] for key in sorted(publications)),
        drafts=tuple(drafts),
    )


__all__ = [
    "FailedCompletionTransition",
    "reduce_failed_completion",
    "reduce_successful_completion",
]
