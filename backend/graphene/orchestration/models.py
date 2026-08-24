from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from ..hashing import canonical_json_bytes, canonical_json_sha256
from ..models import (
    BoundedText,
    FrozenModel,
    GitSha,
    Identifier,
    IdempotencyKey,
    RepoPath,
    Sha256,
    TruthKind,
    UtcDateTime,
)

SCHEMA_VERSION = 1
MAX_EVENT_PAYLOAD_BYTES = 4_096
MAX_ARTIFACT_BYTES = 1_048_576


class MissionStatus(StrEnum):
    PROPOSED = "proposed"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_RESULT = "awaiting_result"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskKind(StrEnum):
    WORK = "work"
    ASSEMBLY = "assembly"
    VERIFICATION = "verification"


class TaskState(StrEnum):
    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    RETRYING = "retrying"
    NEEDS_INPUT = "needs_input"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptState(StrEnum):
    LEASED = "leased"
    RUNNING = "running"
    COMMITTED = "committed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"


class PublicationState(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ArtifactVisibility(StrEnum):
    PRIVATE = "private"
    MISSION = "mission"


class NetworkMode(StrEnum):
    DENY = "deny"
    ALLOWLIST = "allowlist"


class MissionAuthority(StrEnum):
    MISSION_SERVICE = "mission_service"
    SCHEDULER = "scheduler"
    VALIDATOR = "validator"
    POLICY_ENGINE = "policy_engine"
    OPERATOR = "operator"
    PLANNER = "planner"
    WORKER_ADAPTER = "worker_adapter"
    SIMULATED_FIXTURE = "simulated_fixture"


# The unknown a Gemini-planned mission is created with. It is true at creation and
# false the moment the operator approves the plan, so `why` clears it there
# instead of carrying a stale caveat onto every later answer.
PLAN_AWAITING_REVIEW_UNKNOWN = "The model-proposed plan awaits operator review."


class MissionEventType(StrEnum):
    PROJECT_CREATED = "project.created"
    MISSION_CREATED = "mission.created"
    PLAN_PROPOSED = "plan.proposed"
    PLAN_VALIDATED = "plan.validated"
    PLAN_APPROVED = "plan.approved"
    PLAN_REJECTED = "plan.rejected"
    PLAN_REVISED = "plan.revised"
    TASK_READY = "task.ready"
    TASK_LEASED = "task.leased"
    TASK_STARTED = "task.started"
    TASK_HEARTBEAT = "task.heartbeat"
    TASK_BLOCKED = "task.blocked"
    TASK_RETRIED = "task.retried"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    DEPENDENCY_SATISFIED = "dependency.satisfied"
    ARTIFACT_PUBLISHED = "artifact.published"
    ARTIFACT_ACCEPTED = "artifact.accepted"
    ARTIFACT_REJECTED = "artifact.rejected"
    GATE_REQUESTED = "gate.requested"
    GATE_DECIDED = "gate.decided"
    RESOURCE_BUDGET_CROSSED = "resource.budget_crossed"
    RESOURCE_SUMMARY_RECORDED = "resource.summary_recorded"
    OPERATOR_PAUSED = "operator.paused"
    OPERATOR_RESUMED = "operator.resumed"
    OPERATOR_CANCELLED = "operator.cancelled"
    OPERATOR_REASSIGNED = "operator.reassigned"
    OPERATOR_REPRIORITIZED = "operator.reprioritized"
    OPERATOR_REPLAN_REQUESTED = "operator.replan_requested"
    ASSEMBLY_STARTED = "assembly.started"
    ASSEMBLY_COMPLETED = "assembly.completed"
    ASSEMBLY_FAILED = "assembly.failed"
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_COMPLETED = "verification.completed"
    VERIFICATION_FAILED = "verification.failed"
    FINAL_CANDIDATE_READY = "final_candidate.ready"
    FINAL_RESULT_BUNDLE_READY = "final_result_bundle.ready"
    FINAL_CANDIDATE_APPROVED = "final_candidate.approved"
    FINAL_CANDIDATE_REJECTED = "final_candidate.rejected"
    ISOLATED_COMMIT_CREATED = "isolated_commit.created"
    WORKER_REGISTERED = "worker.registered"
    WORKER_REVOKED = "worker.revoked"
    TASK_INPUT_SUPPLIED = "task.input_supplied"
    MISSION_TRIGGERED = "mission.triggered"


TASK_TRANSITIONS = frozenset(
    {
        (TaskState.QUEUED, TaskState.READY),
        (TaskState.QUEUED, TaskState.BLOCKED),
        (TaskState.READY, TaskState.RUNNING),
        (TaskState.READY, TaskState.VERIFYING),
        (TaskState.READY, TaskState.BLOCKED),
        (TaskState.BLOCKED, TaskState.READY),
        (TaskState.BLOCKED, TaskState.NEEDS_INPUT),
        (TaskState.RUNNING, TaskState.DONE),
        (TaskState.RUNNING, TaskState.RETRYING),
        (TaskState.RUNNING, TaskState.BLOCKED),
        (TaskState.RUNNING, TaskState.NEEDS_INPUT),
        (TaskState.RUNNING, TaskState.FAILED),
        (TaskState.VERIFYING, TaskState.DONE),
        (TaskState.VERIFYING, TaskState.RETRYING),
        (TaskState.VERIFYING, TaskState.BLOCKED),
        (TaskState.VERIFYING, TaskState.NEEDS_INPUT),
        (TaskState.VERIFYING, TaskState.FAILED),
        (TaskState.RETRYING, TaskState.READY),
        (TaskState.RETRYING, TaskState.FAILED),
        (TaskState.NEEDS_INPUT, TaskState.READY),
        (TaskState.FAILED, TaskState.RETRYING),
        *(
            (state, TaskState.CANCELLED)
            for state in TaskState
            if state
            not in {
                TaskState.DONE,
                TaskState.FAILED,
                TaskState.CANCELLED,
            }
        ),
    }
)

MISSION_TRANSITIONS = frozenset(
    {
        (MissionStatus.PROPOSED, MissionStatus.RUNNING),
        (MissionStatus.PROPOSED, MissionStatus.REJECTED),
        (MissionStatus.RUNNING, MissionStatus.PAUSED),
        (MissionStatus.PAUSED, MissionStatus.RUNNING),
        (MissionStatus.RUNNING, MissionStatus.AWAITING_RESULT),
        (MissionStatus.AWAITING_RESULT, MissionStatus.COMPLETED),
        (MissionStatus.AWAITING_RESULT, MissionStatus.REJECTED),
        (MissionStatus.AWAITING_RESULT, MissionStatus.FAILED),
        (MissionStatus.RUNNING, MissionStatus.FAILED),
        (MissionStatus.PAUSED, MissionStatus.FAILED),
        (MissionStatus.FAILED, MissionStatus.RUNNING),
        (MissionStatus.PROPOSED, MissionStatus.CANCELLED),
        (MissionStatus.RUNNING, MissionStatus.CANCELLED),
        (MissionStatus.PAUSED, MissionStatus.CANCELLED),
        (MissionStatus.AWAITING_RESULT, MissionStatus.CANCELLED),
    }
)


class NetworkPolicy(FrozenModel):
    mode: NetworkMode = NetworkMode.DENY
    allowed_hosts: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def mode_matches_hosts(self) -> NetworkPolicy:
        if self.allowed_hosts != tuple(sorted(set(self.allowed_hosts))):
            raise ValueError("network hosts must be sorted and unique")
        if (self.mode == NetworkMode.DENY) != (not self.allowed_hosts):
            raise ValueError("deny network policy cannot contain allowed hosts")
        return self


class CommandTemplate(FrozenModel):
    template_id: Identifier
    argv: tuple[BoundedText, ...] = Field(min_length=1, max_length=32)
    timeout_seconds: int = Field(gt=0, le=3_600)
    cwd: RepoPath | None = None

    @model_validator(mode="after")
    def argv_is_direct(self) -> CommandTemplate:
        if self.argv[0] in {"bash", "sh", "zsh", "cmd", "powershell"}:
            raise ValueError("shell command templates are not allowed")
        return self


class ResourceBudget(FrozenModel):
    max_worker_seconds: int = Field(gt=0, le=86_400)
    max_attempts: int = Field(gt=0, le=10_000)
    max_artifact_bytes: int = Field(gt=0, le=MAX_ARTIFACT_BYTES * 100)
    soft_managed_rss_bytes: int = Field(default=536_870_912, gt=0)
    hard_managed_rss_bytes: int = Field(default=805_306_368, gt=0)

    @model_validator(mode="after")
    def managed_rss_thresholds_are_ordered(self) -> ResourceBudget:
        if self.soft_managed_rss_bytes >= self.hard_managed_rss_bytes:
            raise ValueError("soft managed RSS threshold must be below hard threshold")
        return self


class RetentionPolicy(FrozenModel):
    retain_days: int = Field(ge=1, le=365)
    retain_failed_attempts: bool = True


class ProjectPolicy(FrozenModel):
    schema_version: Literal[1] = 1
    policy_id: Identifier
    revision: int = Field(ge=1)
    repo_id: Identifier
    base_ref: BoundedText
    base_sha: GitSha
    allowed_read_globs: tuple[RepoPath, ...] = Field(min_length=1, max_length=128)
    allowed_write_globs: tuple[RepoPath, ...] = Field(min_length=1, max_length=128)
    exclusions: tuple[RepoPath, ...] = Field(default=(), max_length=128)
    command_templates: tuple[CommandTemplate, ...] = Field(min_length=1, max_length=64)
    network: NetworkPolicy = NetworkPolicy()
    agent_roles: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    max_concurrency: int = Field(gt=0, le=64)
    retry_limit: int = Field(ge=0, le=10)
    resource_budget: ResourceBudget
    retention: RetentionPolicy
    risk_gates: tuple[Identifier, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def collections_are_canonical(self) -> ProjectPolicy:
        collections = (
            self.allowed_read_globs,
            self.allowed_write_globs,
            self.exclusions,
            self.agent_roles,
            self.risk_gates,
        )
        if any(items != tuple(sorted(set(items))) for items in collections):
            raise ValueError("policy collections must be sorted and unique")
        ids = tuple(item.template_id for item in self.command_templates)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("command templates must have sorted unique IDs")
        return self


class ProjectPolicySummary(FrozenModel):
    schema_version: Literal[1] = 1
    policy_id: Identifier
    revision: int = Field(ge=1)
    repo_id: Identifier
    base_ref: BoundedText
    base_sha: GitSha
    command_template_ids: tuple[Identifier, ...]
    max_concurrency: int = Field(gt=0, le=64)
    retry_limit: int = Field(ge=0, le=10)
    network_mode: NetworkMode
    policy_sha256: Sha256


class ArtifactContract(FrozenModel):
    name: Identifier
    kind: Identifier
    paths: tuple[RepoPath, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def paths_are_canonical(self) -> ArtifactContract:
        if self.paths != tuple(sorted(set(self.paths))):
            raise ValueError("artifact paths must be sorted and unique")
        return self


class ArtifactRequirement(FrozenModel):
    producer_task_id: Identifier
    name: Identifier
    kind: Identifier


class CriterionVerificationKind(StrEnum):
    DETERMINISTIC_CHECK = "deterministic_check"
    HUMAN_GATE = "human_gate"
    MODEL_ASSERTION = "model_assertion"


class Criterion(FrozenModel):
    criterion_id: Identifier
    description: BoundedText
    producer_task_ids: tuple[Identifier, ...] = Field(default=(), max_length=64)
    verification_kind: CriterionVerificationKind
    verifier_task_id: Identifier | None = None
    verifier_id: Identifier | None = None

    @model_validator(mode="after")
    def producers_are_canonical(self) -> Criterion:
        if self.producer_task_ids != tuple(sorted(set(self.producer_task_ids))):
            raise ValueError("criterion producers must be sorted and unique")
        if not _safe_public_value(self.description):
            raise ValueError("criterion description is unsafe")
        return self


class Task(FrozenModel):
    schema_version: Literal[1] = 1
    task_id: Identifier
    title: BoundedText
    contract: BoundedText
    kind: TaskKind = TaskKind.WORK
    dependencies: tuple[Identifier, ...] = Field(default=(), max_length=64)
    assigned_role: Identifier
    evidence_adapter: Literal["generic_v1", "legacy_auth_v2"] = "generic_v1"
    read_paths: tuple[RepoPath, ...] = Field(min_length=1, max_length=256)
    write_paths: tuple[RepoPath, ...] = Field(default=(), max_length=128)
    allowed_commands: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    inputs: tuple[ArtifactRequirement, ...] = Field(default=(), max_length=64)
    expected_outputs: tuple[ArtifactContract, ...] = Field(min_length=1, max_length=64)
    acceptance_checks: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    priority: int = Field(ge=-1_000, le=1_000)
    state: TaskState = TaskState.QUEUED
    attempt_limit: int = Field(gt=0, le=20)
    attempt_count: int = Field(default=0, ge=0, le=20)
    retry_at: UtcDateTime | None = None
    blocker: BoundedText | None = None

    @model_validator(mode="after")
    def collections_and_state_are_consistent(self) -> Task:
        if not _safe_public_value(
            {"blocker": self.blocker, "contract": self.contract, "title": self.title}
        ):
            raise ValueError("task public text is unsafe")
        collections = (
            self.dependencies,
            self.read_paths,
            self.write_paths,
            self.allowed_commands,
            self.acceptance_checks,
        )
        if any(items != tuple(sorted(set(items))) for items in collections):
            raise ValueError("task collections must be sorted and unique")
        if self.task_id in self.dependencies:
            raise ValueError("task cannot depend on itself")
        output_keys = tuple((item.name, item.kind) for item in self.expected_outputs)
        input_keys = tuple(
            (item.producer_task_id, item.name, item.kind) for item in self.inputs
        )
        if len(output_keys) != len(set(output_keys)) or len(input_keys) != len(
            set(input_keys)
        ):
            raise ValueError("artifact contracts must be unique")
        if output_keys != tuple(sorted(output_keys)) or input_keys != tuple(
            sorted(input_keys)
        ):
            raise ValueError("artifact contracts must be sorted")
        exact_paths = (
            *self.write_paths,
            *(path for item in self.expected_outputs for path in item.paths),
        )
        if any(any(character in path for character in "*?[") for path in exact_paths):
            raise ValueError("task write and output paths must be exact")
        if self.attempt_count > self.attempt_limit:
            raise ValueError("task attempts exceed the limit")
        if (self.state == TaskState.RETRYING) != (self.retry_at is not None):
            raise ValueError("only retrying tasks carry retry_at")
        if (self.state in {TaskState.BLOCKED, TaskState.NEEDS_INPUT}) != (
            self.blocker is not None
        ):
            raise ValueError("blocked and needs-input tasks require a blocker")
        return self


class Plan(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    revision: int = Field(ge=1)
    previous_revision: int | None = Field(default=None, ge=1)
    criteria: tuple[Criterion, ...] = Field(default=(), max_length=32)
    tasks: tuple[Task, ...] = Field(min_length=3, max_length=256)
    max_concurrency: int = Field(gt=0, le=64)

    @model_validator(mode="after")
    def revision_and_ids_are_canonical(self) -> Plan:
        criterion_ids = tuple(item.criterion_id for item in self.criteria)
        if criterion_ids != tuple(sorted(criterion_ids)) or len(criterion_ids) != len(
            set(criterion_ids)
        ):
            raise ValueError("plan criteria must have sorted unique IDs")
        ids = tuple(item.task_id for item in self.tasks)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("plan tasks must have sorted unique IDs")
        if self.revision == 1 and self.previous_revision is not None:
            raise ValueError("initial plan cannot have a previous revision")
        if self.revision > 1 and self.previous_revision != self.revision - 1:
            raise ValueError("plan revisions must link contiguously")
        return self


class Mission(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    policy_id: Identifier
    policy_revision: int = Field(ge=1)
    repo_id: Identifier
    base_sha: GitSha
    goal: BoundedText
    success_criteria: tuple[BoundedText, ...] = Field(min_length=1, max_length=32)
    plan_revision: int = Field(ge=1)
    status: MissionStatus = MissionStatus.PROPOSED
    creation_source: Literal["operator", "scripted_fixture", "replay"]
    resource_budget: ResourceBudget
    final_outcome: BoundedText | None = None
    unknowns: tuple[BoundedText, ...] = Field(default=(), max_length=32)
    created_at: UtcDateTime

    @model_validator(mode="after")
    def criteria_are_canonical(self) -> Mission:
        if not _safe_public_value(
            {
                "final_outcome": self.final_outcome,
                "goal": self.goal,
                "success_criteria": self.success_criteria,
                "unknowns": self.unknowns,
            }
        ):
            raise ValueError("mission public text is unsafe")
        if self.success_criteria != tuple(sorted(set(self.success_criteria))):
            raise ValueError("success criteria must be sorted and unique")
        if self.unknowns != tuple(sorted(set(self.unknowns))):
            raise ValueError("unknowns must be sorted and unique")
        return self


class MissionTrigger(FrozenModel):
    """Why a watcher created a mission: an annotation event payload, never state.

    ``source_ref`` is a bare file name or ``OWNER/NAME#NUMBER``; absolute paths
    are rejected by the event payload filter. ``source_sha256`` digests the raw
    inbox bytes or the canonical JSON of an issue's title and body. The key is
    not ``content_sha256`` because event payload keys containing ``content``
    are refused by design.
    """

    source_kind: Literal["inbox_file", "github_issue"]
    source_ref: Annotated[str, Field(min_length=1, max_length=256)]
    source_url: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    source_sha256: Sha256
    observed_at: UtcDateTime
    watcher_id: Identifier


class GenericEvidenceLink(FrozenModel):
    kind: Literal["generic_v1"] = "generic_v1"
    evidence_id: Identifier


class LegacyEvidenceLink(FrozenModel):
    kind: Literal["legacy_v2"] = "legacy_v2"
    run_id: Identifier


EvidenceLink = Annotated[
    GenericEvidenceLink | LegacyEvidenceLink,
    Field(discriminator="kind"),
]


class EvidenceReference(FrozenModel):
    kind: Identifier
    id: Identifier
    sha256: Sha256


class ArtifactEnvelopeReferenceV2(FrozenModel):
    """Immutable CAS identity for bytes minted by the trusted worker wrapper."""

    schema_version: Literal[2]
    artifact_id: Identifier
    producer_task_id: Identifier
    output_name: Identifier
    kind: Identifier
    media_type: Annotated[
        str,
        Field(
            min_length=3,
            max_length=128,
            pattern=r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$",
        ),
    ]
    byte_count: int = Field(ge=0, le=MAX_ARTIFACT_BYTES)
    content_sha256: Sha256
    artifact_envelope_sha256: Sha256

    @property
    def id(self) -> str:
        return self.artifact_id

    @property
    def sha256(self) -> str:
        """Compatibility spelling for byte verification, never semantic identity."""

        return self.content_sha256


class PublishedArtifactReferenceV2(ArtifactEnvelopeReferenceV2):
    publication_id: Identifier


ArtifactInputReference = PublishedArtifactReferenceV2 | EvidenceReference


def artifact_input_reference_key(
    reference: ArtifactInputReference,
) -> tuple[str, ...]:
    if isinstance(reference, PublishedArtifactReferenceV2):
        return (
            "v2",
            reference.producer_task_id,
            reference.output_name,
            reference.publication_id,
            reference.artifact_envelope_sha256,
        )
    return ("legacy", reference.kind, reference.id, reference.sha256)


class WorkerRegistration(FrozenModel):
    schema_version: Literal[1] = 1
    registration_id: Identifier
    mission_id: Identifier
    worker_id: Identifier
    runtime_id: Identifier
    capabilities: tuple[TaskKind, ...] = Field(min_length=1, max_length=3)
    registered_at: UtcDateTime

    @model_validator(mode="after")
    def capabilities_are_canonical(self) -> WorkerRegistration:
        if self.capabilities != tuple(sorted(set(self.capabilities))):
            raise ValueError("worker capabilities must be sorted and unique")
        return self


class WorkerRevocation(FrozenModel):
    schema_version: Literal[1] = 1
    registration_id: Identifier
    mission_id: Identifier
    worker_id: Identifier
    reason_code: Identifier
    revoked_at: UtcDateTime


class SuppliedTaskInput(FrozenModel):
    schema_version: Literal[1] = 1
    input_id: Identifier
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    task_id: Identifier
    gate_id: Identifier
    reference: EvidenceReference
    operator_label: str = Field(min_length=1, max_length=64)
    truth_kind: TruthKind
    supplied_at: UtcDateTime

    @model_validator(mode="after")
    def reference_is_private_operator_input(self) -> SuppliedTaskInput:
        if self.reference.kind != "operator-input":
            raise ValueError("supplied task input must use the operator-input kind")
        return self


class Attempt(FrozenModel):
    schema_version: Literal[1] = 1
    attempt_id: Identifier
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    task_id: Identifier
    attempt_number: int = Field(ge=1, le=20)
    worker_id: Identifier
    session_id: Identifier | None = None
    invocation_id: Identifier | None = None
    workspace_id: Identifier
    lease_id: Identifier
    fencing_token: int = Field(ge=1)
    dispatch_command_id: IdempotencyKey
    state: AttemptState
    started_at: UtcDateTime
    ended_at: UtcDateTime | None = None
    evidence_link: EvidenceLink | None = None
    result_code: Identifier | None = None
    input_publications: tuple[ArtifactInputReference, ...] = Field(
        default=(), max_length=64
    )
    evidence_refs: tuple[EvidenceReference, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def terminal_bindings_are_consistent(self) -> Attempt:
        terminal = self.state in {
            AttemptState.COMMITTED,
            AttemptState.FAILED,
            AttemptState.ABANDONED,
            AttemptState.CANCELLED,
        }
        if terminal != (self.ended_at is not None):
            raise ValueError("terminal attempts require an end timestamp")
        if self.state == AttemptState.COMMITTED and self.evidence_link is None:
            raise ValueError("committed attempts require evidence")
        input_keys = tuple(
            artifact_input_reference_key(item) for item in self.input_publications
        )
        if input_keys != tuple(sorted(set(input_keys))):
            raise ValueError("attempt input publications must be sorted and unique")
        return self


class Lease(FrozenModel):
    schema_version: Literal[1] = 1
    lease_id: Identifier
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    task_id: Identifier
    attempt_id: Identifier
    owner: Identifier
    capability: Literal["execute_publish"] = "execute_publish"
    write_paths: tuple[RepoPath, ...] = Field(default=(), max_length=128)
    fencing_token: int = Field(ge=1)
    issued_at: UtcDateTime
    heartbeat_at: UtcDateTime
    expires_at: UtcDateTime
    released_at: UtcDateTime | None = None
    release_reason: Identifier | None = None

    @model_validator(mode="after")
    def times_and_release_are_consistent(self) -> Lease:
        if self.write_paths != tuple(sorted(set(self.write_paths))):
            raise ValueError("lease write paths must be sorted and unique")
        if not self.issued_at <= self.heartbeat_at < self.expires_at:
            raise ValueError("lease timestamps are not monotonic")
        if (self.released_at is None) != (self.release_reason is None):
            raise ValueError("lease release fields must appear together")
        return self


class PublicationDraft(FrozenModel):
    output_name: Identifier
    kind: Identifier
    sha256: Sha256
    artifact: ArtifactEnvelopeReferenceV2 | None = None
    visibility: ArtifactVisibility = ArtifactVisibility.MISSION
    paths: tuple[RepoPath, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def paths_are_canonical(self) -> PublicationDraft:
        if self.paths != tuple(sorted(set(self.paths))):
            raise ValueError("publication paths must be sorted and unique")
        if self.artifact is not None and (
            self.artifact.output_name != self.output_name
            or self.artifact.kind != self.kind
            or self.artifact.content_sha256 != self.sha256
        ):
            raise ValueError("publication artifact binding disagrees")
        return self


class ArtifactPublication(PublicationDraft):
    schema_version: Literal[1] = 1
    publication_id: Identifier
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    task_id: Identifier
    attempt_id: Identifier
    state: PublicationState
    consumers: tuple[Identifier, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def consumers_are_canonical(self) -> ArtifactPublication:
        if self.consumers != tuple(sorted(set(self.consumers))):
            raise ValueError("publication consumers must be sorted and unique")
        return self

    def published_reference(self) -> PublishedArtifactReferenceV2:
        if self.artifact is None:
            raise ValueError("publication has no V2 artifact envelope")
        return PublishedArtifactReferenceV2(
            **self.artifact.model_dump(mode="json"),
            publication_id=self.publication_id,
        )


class GateDecision(FrozenModel):
    value: Identifier
    consequence: BoundedText
    task_effect: Literal["ready", "cancelled", "needs_input"] = "ready"

    @model_validator(mode="after")
    def consequence_is_public(self) -> GateDecision:
        if not _safe_public_value(self.consequence):
            raise ValueError("gate consequence is unsafe")
        return self


class Gate(FrozenModel):
    schema_version: Literal[1] = 1
    gate_id: Identifier
    mission_id: Identifier
    task_id: Identifier | None = None
    reason: BoundedText
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=32)
    allowed_decisions: tuple[GateDecision, ...] = Field(min_length=1, max_length=8)
    truth_kind: TruthKind
    operator_label: str | None = Field(default=None, min_length=1, max_length=64)
    rationale: str | None = Field(default=None, max_length=280)
    resolution: Identifier | None = None

    @model_validator(mode="after")
    def decision_and_operator_are_consistent(self) -> Gate:
        if not _safe_public_value(
            {
                "operator_label": self.operator_label,
                "rationale": self.rationale,
                "reason": self.reason,
            }
        ):
            raise ValueError("gate public text is unsafe")
        values = tuple(item.value for item in self.allowed_decisions)
        if values != tuple(sorted(set(values))):
            raise ValueError("gate decisions must have sorted unique values")
        decided = self.resolution is not None
        if decided != (self.operator_label is not None):
            raise ValueError("resolved gates require an operator label")
        if self.resolution is not None and self.resolution not in values:
            raise ValueError("gate resolution is not an allowed decision")
        return self


class ResourceReceipt(FrozenModel):
    schema_version: Literal[1] = 1
    receipt_id: Identifier
    mission_id: Identifier
    subject: Identifier
    source: Identifier
    platform: Identifier
    scope: Identifier
    semantics: Identifier
    units: Identifier
    observed_from: UtcDateTime
    observed_until: UtcDateTime
    value: float | None = Field(default=None, ge=0)
    attribution_quality: Literal[
        "measured_bound", "sampled_partial", "aggregate_only", "unavailable"
    ]
    threshold: float | None = Field(default=None, ge=0)
    action: Identifier

    @model_validator(mode="after")
    def interval_is_ordered(self) -> ResourceReceipt:
        if self.observed_until < self.observed_from:
            raise ValueError("resource observation interval is reversed")
        if (self.value is None) != (self.attribution_quality == "unavailable"):
            raise ValueError("only unavailable resource receipts omit a value")
        return self


_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "apikey",
        "argv",
        "authorization",
        "chainofthought",
        "command",
        "content",
        "credential",
        "environment",
        "env",
        "password",
        "passwd",
        "patch",
        "prompt",
        "rawprompt",
        "reasoning",
        "secret",
        "token",
        "stdout",
        "stderr",
        "systemprompt",
    }
)

_SAFE_TOKEN_KEYS = frozenset(
    {
        "cachedtokens",
        "candidatetokens",
        "estimatedtokens",
        "fencingtoken",
        "prompttokens",
        "thoughttokens",
        "tokenestimate",
        "tokenestimation",
        "tokenquality",
        "tooltokens",
        "totaltokens",
    }
)

_SECRET_VALUE = re.compile(
    r"(?i)(?:"
    r"\bbearer\s+[a-z0-9._~+/=-]{8,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:api[_-]?key|access[_-]?token|password|passwd|secret)\s*[:=]\s*\S+"
    r"|\b(?:sk-[a-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|AIza[a-z0-9_-]{20,}"
    r"|gh[pousr]_[a-z0-9]{20,}|xox[baprs]-[a-z0-9-]{12,})"
    r"|(?:^|\s)(?:/Users/[^/\s]+/|/home/[^/\s]+/|[A-Z]:\\Users\\[^\\\s]+\\)"
    r"|(?:^|[/\\])(?:\.ssh|\.aws|\.gnupg)(?:[/\\]|$)"
    r"|(?:^|[/\\])\.netrc(?:$|\s)"
    r"|/var/run/secrets/"
    r"|://[^/\s:@]+:[^/\s@]+@"
    r")"
)


def _normalized_payload_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _safe_payload_key(value: str) -> bool:
    normalized = _normalized_payload_key(value)
    if not normalized or len(value) > 128:
        return False
    if normalized in _SAFE_TOKEN_KEYS:
        return True
    if normalized in _FORBIDDEN_PAYLOAD_KEYS:
        return False
    if any(
        word in normalized
        for word in (
            "apikey",
            "authorization",
            "argv",
            "commandargument",
            "secret",
            "password",
            "passwd",
            "credential",
            "content",
            "env",
            "environment",
            "modelreasoning",
            "privatekey",
            "prompt",
            "rawprompt",
            "reasoning",
            "chainofthought",
            "systeminstruction",
            "stderr",
            "stdout",
            "toolpayload",
        )
    ):
        return False
    return "token" not in normalized


def _safe_public_value(value: Any, *, _depth: int = 0) -> bool:
    if _depth > 8:
        return False
    if isinstance(value, dict):
        if len(value) > 128:
            return False
        return all(
            isinstance(key, str)
            and _safe_payload_key(key)
            and _safe_public_value(item, _depth=_depth + 1)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return len(value) <= 128 and all(
            _safe_public_value(item, _depth=_depth + 1) for item in value
        )
    if isinstance(value, str):
        return _SECRET_VALUE.search(value) is None
    return value is None or isinstance(value, (int, float, bool))


class MissionEventInput(FrozenModel):
    event_type: MissionEventType
    truth_kind: TruthKind
    authority: MissionAuthority
    references: tuple[EvidenceReference, ...] = Field(default=(), max_length=32)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def payload_is_public_and_bounded(self) -> MissionEventInput:
        if (
            not _safe_public_value(self.payload)
            or len(canonical_json_bytes(self.payload)) > MAX_EVENT_PAYLOAD_BYTES
        ):
            raise ValueError("mission event payload is unsafe or too large")
        keys = tuple((item.kind, item.id, item.sha256) for item in self.references)
        if len(keys) != len(set(keys)):
            raise ValueError("mission event references must be unique")
        if (
            self.truth_kind == TruthKind.HUMAN_ATTESTED
            and self.authority != MissionAuthority.OPERATOR
        ):
            raise ValueError("human truth requires operator authority")
        if (
            self.truth_kind == TruthKind.MODEL_PROPOSED
            and self.authority != MissionAuthority.PLANNER
        ):
            raise ValueError("model proposals require planner authority")
        if self.truth_kind == TruthKind.POLICY_AUTHORITATIVE and self.authority not in {
            MissionAuthority.POLICY_ENGINE,
            MissionAuthority.VALIDATOR,
        }:
            raise ValueError("policy truth requires policy authority")
        return self


class MissionEvent(MissionEventInput):
    schema_version: Literal[1] = 1
    event_id: Identifier
    mission_id: Identifier
    seq: int = Field(ge=1)
    server_recorded_at: UtcDateTime
    command_id: IdempotencyKey
    payload_sha256: Sha256
    previous_event_sha256: Sha256 | None
    event_sha256: Sha256

    @model_validator(mode="after")
    def hashes_are_canonical(self) -> MissionEvent:
        if self.payload_sha256 != canonical_json_sha256(self.payload):
            raise ValueError("mission payload digest does not match")
        if (self.seq == 1) != (self.previous_event_sha256 is None):
            raise ValueError(
                "only the first mission event may omit its previous digest"
            )
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"event_sha256"})
        )
        if self.event_sha256 != expected:
            raise ValueError("mission event digest does not match")
        return self


class MissionHead(FrozenModel):
    mission_id: Identifier
    seq: int = Field(ge=0)
    event_sha256: Sha256 | None
    event_count: int = Field(ge=0)

    @model_validator(mode="after")
    def fields_agree(self) -> MissionHead:
        if self.seq != self.event_count or (self.seq == 0) != (
            self.event_sha256 is None
        ):
            raise ValueError("mission head fields disagree")
        return self


class Dispatch(FrozenModel):
    schema_version: Literal[1] = 1
    mission_id: Identifier
    plan_revision: int = Field(ge=1)
    plan_sha256: Sha256
    task_id: Identifier
    task_kind: TaskKind
    attempt_id: Identifier
    attempt_number: int = Field(ge=1)
    worker_id: Identifier
    workspace_id: Identifier
    lease_id: Identifier
    fencing_token: int = Field(ge=1)
    dispatch_command_id: IdempotencyKey
    write_paths: tuple[RepoPath, ...]
    allowed_commands: tuple[Identifier, ...]
    acceptance_checks: tuple[Identifier, ...]
    input_publications: tuple[ArtifactInputReference, ...] = Field(
        default=(), max_length=64
    )
    expires_at: UtcDateTime


class AttemptResult(FrozenModel):
    succeeded: bool
    retryable: bool = False
    result_code: Identifier
    session_id: Identifier | None = None
    invocation_id: Identifier | None = None
    evidence_link: EvidenceLink | None = None
    evidence_refs: tuple[EvidenceReference, ...] = Field(default=(), max_length=64)
    artifact_envelopes: tuple[ArtifactEnvelopeReferenceV2, ...] = Field(
        default=(), max_length=64
    )
    publications: tuple[PublicationDraft, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def success_has_evidence(self) -> AttemptResult:
        if self.succeeded and self.evidence_link is None:
            raise ValueError("successful attempts require evidence")
        if self.succeeded and self.retryable:
            raise ValueError("successful results cannot be retryable")
        reference_keys = tuple(
            (item.kind, item.id, item.sha256) for item in self.evidence_refs
        )
        publication_keys = tuple(
            (item.output_name, item.kind) for item in self.publications
        )
        envelope_keys = tuple(
            item.artifact_envelope_sha256 for item in self.artifact_envelopes
        )
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError("attempt evidence references must be unique")
        if len(publication_keys) != len(set(publication_keys)):
            raise ValueError("attempt publications must be unique")
        if envelope_keys != tuple(sorted(set(envelope_keys))):
            raise ValueError("attempt artifact envelopes must be sorted and unique")
        return self


class MissionSnapshot(FrozenModel):
    schema_version: Literal[1] = 1
    policy: ProjectPolicySummary
    mission: Mission
    plan: Plan
    tasks: tuple[Task, ...]
    attempts: tuple[Attempt, ...]
    leases: tuple[Lease, ...]
    publications: tuple[ArtifactPublication, ...]
    gates: tuple[Gate, ...]
    head: MissionHead
    unknowns: tuple[BoundedText, ...]
    snapshot_sha256: Sha256

    @model_validator(mode="after")
    def snapshot_is_canonical(self) -> MissionSnapshot:
        ordered = (
            tuple(item.task_id for item in self.tasks),
            tuple(item.attempt_id for item in self.attempts),
            tuple(item.lease_id for item in self.leases),
            tuple(item.publication_id for item in self.publications),
            tuple(item.gate_id for item in self.gates),
        )
        if any(items != tuple(sorted(items)) for items in ordered):
            raise ValueError("mission snapshot collections must be sorted")
        if self.head.mission_id != self.mission.mission_id:
            raise ValueError("mission snapshot head belongs to another mission")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"snapshot_sha256"})
        )
        if self.snapshot_sha256 != expected:
            raise ValueError("mission snapshot digest does not match")
        return self
