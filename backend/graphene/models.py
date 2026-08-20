from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from string import Formatter
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex


def _relative_posix_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        value in {"", "."}
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError("path must be canonical, relative, and remain inside the fixture")
    return value


RepoPath = Annotated[
    str,
    Field(min_length=1, max_length=256),
    AfterValidator(_relative_posix_path),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GitSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Identifier = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"),
]
IdempotencyKey = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9_-]{16,128}$"),
]
AgentProfileId = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9-]{1,63}@[1-9][0-9]*$"),
]
BoundedText = Annotated[str, Field(min_length=1, max_length=1024)]


def _utc_datetime(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]
MAX_PATCH_BYTES = 102_400
MAX_TEST_OUTPUT_BYTES = 16_384
MAX_PATCH_BASE64_CHARS = ((MAX_PATCH_BYTES + 2) // 3) * 4
P0_MUTABLE_PATHS = frozenset({"app/auth/limiter.py", "tests/test_security_policy.py"})
P0_REQUIRED_TEST_PATH = "tests/test_security_policy.py"
GRAPH_MAX_DEPTH = 2
GRAPH_MAX_NODES = 25
GRAPH_MAX_EDGES = 40
GRAPH_MAX_RELATED_FILES = 8
GRAPH_MAX_HUNKS = 12
GRAPH_MAX_MEMORIES = 3


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_PROMOTION = "waiting_for_promotion"
    PROMOTING = "promoting"
    COMPLETED = "completed"
    FAILED = "failed"


class MemoryState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class MemoryDecisionValue(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ScopeId(StrEnum):
    ALL_AUTH = "all_auth"
    RATE_LIMITER_ONLY = "rate_limiter_only"


class TaskId(StrEnum):
    BASELINE_MAX_ATTEMPTS = "baseline_max_attempts"
    ADAPTED_WINDOW_SECONDS = "adapted_window_seconds"


class ProofType(StrEnum):
    MEMORY_PROPOSED = "memory.proposed"
    MEMORY_APPROVED = "memory.approved"
    MEMORY_INJECTED = "memory.injected"
    FILE_WRITTEN = "tool.file_written"
    TEST_COMPLETED = "test.completed"
    COMPLETION_DENIED = "completion.denied"
    PROMOTION_APPROVED = "promotion.approved"
    CANDIDATE_COMMITTED = "candidate.committed"
    RUN_FAILED = "run.failed"


class GraphNodeKind(StrEnum):
    AGENT_RUN = "agent_run"
    CHANGESET = "changeset"
    FILE = "file"
    HUNK = "hunk"
    FEEDBACK = "feedback"
    MEMORY_REVISION = "memory_revision"
    CONTEXT_PACKET = "context_packet"
    POLICY_CHECK = "policy_check"
    TEST_RECEIPT = "test_receipt"
    HUMAN_DECISION = "human_decision"
    PROMOTION_RECEIPT = "promotion_receipt"


class GraphEdgeKind(StrEnum):
    PRODUCED = "PRODUCED"
    CONTAINS = "CONTAINS"
    MODIFIES = "MODIFIES"
    IMPORTS = "IMPORTS"
    TRIGGERED = "TRIGGERED"
    LEARNED_AS = "LEARNED_AS"
    APPROVED = "APPROVED"
    PACKED_IN = "PACKED_IN"
    INJECTED_INTO = "INJECTED_INTO"
    VALIDATED = "VALIDATED"
    DENIED = "DENIED"
    ALLOWED = "ALLOWED"
    AUTHORIZED = "AUTHORIZED"
    PROMOTED_AS = "PROMOTED_AS"


class GraphProvenance(StrEnum):
    SERVER_OBSERVED = "server_observed"
    SERVER_DERIVED = "server_derived"
    HUMAN_ATTESTED = "human_attested"
    SIMULATED_FIXTURE = "simulated_fixture"
    MODEL_PROPOSED = "model_proposed"


class ContextDecision(StrEnum):
    ALLOWED = "allowed"
    DENIED_OUT_OF_SCOPE = "denied_out_of_scope"


RUN_TRANSITIONS = frozenset(
    {
        (RunState.QUEUED, RunState.RUNNING),
        (RunState.RUNNING, RunState.WAITING_FOR_PROMOTION),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.WAITING_FOR_PROMOTION, RunState.PROMOTING),
        (RunState.PROMOTING, RunState.COMPLETED),
        (RunState.PROMOTING, RunState.FAILED),
    }
)
MEMORY_TRANSITIONS = frozenset(
    {
        (MemoryState.PROPOSED, MemoryState.APPROVED),
        (MemoryState.PROPOSED, MemoryState.REJECTED),
    }
)


class ModelPolicy(FrozenModel):
    model_id: str
    adk_version: str
    cloud_location: str
    project_access_verified: bool


class HashPolicy(FrozenModel):
    file: str
    patch: str
    candidate_tree: str
    test_receipt: str
    idempotency_request: str


class FixturePolicy(FrozenModel):
    root: RepoPath
    tracked_paths: tuple[RepoPath, ...]
    mutable_paths: tuple[RepoPath, ...]
    fixed_test_command: tuple[str, ...]
    test_timeout_seconds: int = Field(gt=0, le=60)
    max_test_output_bytes: int = Field(gt=0, le=65_536)
    max_write_bytes: int = Field(gt=0, le=262_144)
    max_patch_bytes: int = Field(gt=0, le=1_048_576)
    tree_sha256: Sha256
    tree_hash_version: Literal["graphene.tree.v2"]
    tree_hash_algorithm: str


class PromptPolicy(FrozenModel):
    template: str
    no_memory_context: str
    approved_memory_template: str

    @model_validator(mode="after")
    def placeholders_are_fixed(self) -> PromptPolicy:
        fields = {field for _, field, _, _ in Formatter().parse(self.template) if field}
        if fields != {"task", "memory_context"}:
            raise ValueError(
                "prompt template may contain only task and memory_context placeholders"
            )
        return self


class TaskSpec(FrozenModel):
    task_id: TaskId
    instruction: BoundedText
    repo_id: Identifier
    task_tags: tuple[str, ...]
    target_paths: tuple[RepoPath, ...]
    expected_changed_paths: tuple[RepoPath, ...]
    replacement_from: str
    replacement_to: str


class ScopeOption(FrozenModel):
    scope_id: ScopeId
    label: BoundedText
    path_globs: tuple[RepoPath, ...]
    task_tags: tuple[str, ...]


class MemorySpec(FrozenModel):
    memory_id: Identifier
    revision: int = Field(ge=1)
    correction: BoundedText
    clarification: BoundedText
    scope_options: tuple[ScopeOption, ...]
    selected_scope_id: ScopeId
    rule: BoundedText
    repo_id: Identifier
    path_globs: tuple[RepoPath, ...]
    task_tags: tuple[str, ...]
    required_test_path: RepoPath
    required_check: str
    evidence_task_id: TaskId
    expected_security_assertion: str
    expected_security_test_content: str


class RetrievalCase(FrozenModel):
    case_id: Identifier
    repo_id: Identifier
    task_tags: tuple[str, ...]
    target_paths: tuple[RepoPath, ...]
    expected_memory_ids: tuple[str, ...]


class RetrievalPolicy(FrozenModel):
    states: tuple[MemoryState, ...]
    repo_match: Literal["exact"]
    task_tag_match: Literal["memory_tags_subset_of_task_tags"]
    path_match: Literal["at_least_one_target_matches_glob"]


class ApiEndpoint(FrozenModel):
    method: Literal["GET", "POST"]
    path: str
    request_model: str | None
    response_model: str
    requires_demo_token: bool


class LoopStep(FrozenModel):
    sequence: int = Field(ge=1)
    actor: str
    action: str
    resulting_state: str
    proof_type: ProofType | None = None


class GoldenContract(FrozenModel):
    schema_version: int = Field(ge=1)
    product: str
    repo_id: Identifier
    model: ModelPolicy
    hashes: HashPolicy
    fixture: FixturePolicy
    tool_names: tuple[str, ...]
    prompt: PromptPolicy
    tasks: tuple[TaskSpec, ...]
    memory: MemorySpec
    retrieval: RetrievalPolicy
    negative_retrieval_case: RetrievalCase
    api: tuple[ApiEndpoint, ...]
    loop: tuple[LoopStep, ...]

    @model_validator(mode="after")
    def contract_is_self_consistent(self) -> GoldenContract:
        if self.product != "Graphene":
            raise ValueError("P0 product name is locked")
        if self.tool_names != ("read_file", "write_file", "run_fixture_tests"):
            raise ValueError("P0 exposes exactly three scoped tools")
        if self.fixture.fixed_test_command != (
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ):
            raise ValueError("P0 test command is fixed")
        if frozenset(self.fixture.mutable_paths) != P0_MUTABLE_PATHS:
            raise ValueError("P0 write allowlist is fixed")
        allowed_new_paths = {self.memory.required_test_path}
        if (
            not set(self.fixture.mutable_paths)
            <= set(self.fixture.tracked_paths) | allowed_new_paths
        ):
            raise ValueError("mutable paths must be tracked or the required new test")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("task IDs must be unique")
        if any(task.repo_id != self.repo_id for task in self.tasks):
            raise ValueError("task repository IDs are server-owned")
        if any(
            not set(task.target_paths) <= set(self.fixture.tracked_paths) for task in self.tasks
        ):
            raise ValueError("task targets must exist in the base fixture")
        if any(
            not set(task.expected_changed_paths) <= set(self.fixture.mutable_paths)
            for task in self.tasks
        ):
            raise ValueError("expected changes must remain inside the write allowlist")
        selected_scope = next(
            (
                scope
                for scope in self.memory.scope_options
                if scope.scope_id == self.memory.selected_scope_id
            ),
            None,
        )
        if (
            self.memory.repo_id != self.repo_id
            or self.memory.required_test_path not in self.fixture.mutable_paths
            or selected_scope is None
            or selected_scope.path_globs != self.memory.path_globs
            or selected_scope.task_tags != self.memory.task_tags
        ):
            raise ValueError("memory scope must match the selected server-owned option")
        if self.negative_retrieval_case.repo_id != self.repo_id:
            raise ValueError("retrieval cases must use the server-owned repository")
        if self.retrieval.states != (MemoryState.APPROVED,):
            raise ValueError("only approved memory may be retrieved")
        if any(
            endpoint.requires_demo_token != (endpoint.path != "/healthz") for endpoint in self.api
        ):
            raise ValueError("every non-health endpoint requires the runtime demo token")
        if tuple(step.sequence for step in self.loop) != tuple(range(1, len(self.loop) + 1)):
            raise ValueError("loop steps must be contiguous")
        return self


class MemoryRef(FrozenModel):
    memory_id: Identifier
    revision: int = Field(ge=1)


class ProofItem(FrozenModel):
    event_id: Identifier
    run_id: Identifier
    sequence: int = Field(ge=1)
    evidence_event_ids: tuple[str, ...] = ()
    type: ProofType
    occurred_at: UtcDateTime
    payload: dict[str, Any] = Field(default_factory=dict)


class FeedbackRecord(FrozenModel):
    feedback_id: Identifier
    run_id: Identifier
    evidence_event_id: Identifier
    exact_correction: BoundedText
    selected_hunk_id: Identifier
    selected_scope_id: ScopeId
    occurred_at: UtcDateTime


class HumanDecision(FrozenModel):
    decision_id: Identifier
    value: MemoryDecisionValue
    actor: Literal["human", "simulated_fixture"] = "human"
    purpose: Literal["memory", "promotion"]
    bound_digest: Sha256
    occurred_at: UtcDateTime


class MemoryRevision(FrozenModel):
    memory_id: Identifier
    revision: int = Field(ge=1)
    state: MemoryState
    rule: BoundedText
    repo_id: Identifier
    scope_id: ScopeId | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    path_globs: tuple[RepoPath, ...]
    task_tags: tuple[str, ...]
    required_test_path: RepoPath
    required_check: str
    evidence_run_id: Identifier
    feedback_id: Identifier
    decision: HumanDecision | None = None

    @model_validator(mode="after")
    def human_decision_matches_state(self) -> MemoryRevision:
        expected = {
            MemoryState.APPROVED: MemoryDecisionValue.APPROVE,
            MemoryState.REJECTED: MemoryDecisionValue.REJECT,
        }.get(self.state)
        if (expected is None) != (self.decision is None):
            raise ValueError("only decided memories may contain a human decision")
        if self.decision is not None and self.decision.value != expected:
            raise ValueError("human decision must match memory state")
        if self.decision is not None and (
            self.decision.purpose != "memory"
            or self.decision.bound_digest
            != canonical_json_sha256(self.model_dump(mode="json", exclude={"state", "decision"}))
        ):
            raise ValueError("memory decision must bind the immutable memory content")
        return self


class TestReceipt(FrozenModel):
    required_test_profile: Identifier
    base_commit_sha: GitSha
    candidate_patch_sha256: Sha256
    command: tuple[str, ...]
    candidate_exit_code: int
    base_with_new_test_exit_code: int | None
    timed_out: bool
    output_sha256: Sha256
    output_byte_count: int = Field(ge=0, le=MAX_TEST_OUTPUT_BYTES)
    output_truncated: bool
    duration_bucket: Literal["under_1s", "1_to_5s", "5_to_15s", "over_15s"]
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def hash_is_canonical(self) -> TestReceipt:
        if self.command != (
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ):
            raise ValueError("test receipt command must match the fixed runner")
        expected = canonical_json_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if self.receipt_sha256 != expected:
            raise ValueError("test receipt hash must cover canonical receipt JSON")
        return self


class FileChange(FrozenModel):
    path: RepoPath
    before_sha256: Sha256 | None
    after_sha256: Sha256


class CandidateArtifact(FrozenModel):
    candidate_revision: int = Field(ge=1)
    base_commit_sha: GitSha
    canonical_patch_base64: Annotated[str, Field(min_length=1, max_length=MAX_PATCH_BASE64_CHARS)]
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    changed_paths: tuple[RepoPath, ...]
    file_changes: tuple[FileChange, ...]
    test_receipt: TestReceipt

    @model_validator(mode="after")
    def artifact_is_canonical_and_passing(self) -> CandidateArtifact:
        try:
            patch = base64.b64decode(self.canonical_patch_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("candidate patch must be strict base64") from error
        if len(patch) > MAX_PATCH_BYTES:
            raise ValueError("candidate patch exceeds the P0 size cap")
        if sha256_hex(patch) != self.candidate_patch_sha256:
            raise ValueError("candidate patch hash does not match its bytes")
        paths = tuple(change.path for change in self.file_changes)
        if (
            not self.changed_paths
            or self.changed_paths != tuple(sorted(set(self.changed_paths)))
            or paths != self.changed_paths
            or not set(self.changed_paths) <= P0_MUTABLE_PATHS
            or any(change.before_sha256 == change.after_sha256 for change in self.file_changes)
        ):
            raise ValueError("changed paths and per-file hashes must be sorted, unique, and equal")
        if self.test_receipt.timed_out or self.test_receipt.candidate_exit_code != 0:
            raise ValueError("only a passing, non-timeout candidate may be persisted")
        if (
            self.test_receipt.required_test_profile != "auth-fixture-v1"
            or self.test_receipt.base_commit_sha != self.base_commit_sha
            or self.test_receipt.candidate_patch_sha256 != self.candidate_patch_sha256
        ):
            raise ValueError("test receipt must bind this candidate, base, and test profile")
        return self


class PromotionReceipt(FrozenModel):
    run_id: Identifier
    base_commit_sha: GitSha
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    memory_id: Identifier
    memory_revision: int = Field(ge=1)
    context_packet_id: Identifier
    context_packet_sha256: Sha256
    source_graph_revision: int = Field(ge=1)
    source_graph_hash: Sha256
    selected_node_ids: tuple[Identifier, ...]
    test_receipt_sha256: Sha256
    human_decision_id: Identifier
    expected_run_revision: int = Field(ge=0)
    commit_sha: GitSha
    commit_metadata: dict[str, str] = Field(default_factory=dict)


class PolicyCheck(FrozenModel):
    policy_check_id: Identifier
    run_id: Identifier
    policy_revision: int = Field(ge=1)
    decision: Literal["allowed", "denied"]
    reason_codes: tuple[Identifier, ...]
    candidate_patch_sha256: Sha256
    context_packet_sha256: Sha256 | None = None
    test_receipt_sha256: Sha256
    occurred_at: UtcDateTime


class RunRecord(FrozenModel):
    run_id: Identifier
    task_id: TaskId
    repo_id: Identifier
    state: RunState
    revision: int = Field(ge=0)
    agent_profile_id: AgentProfileId | None = None
    base_sha: GitSha | None = None
    allowed_paths: tuple[RepoPath, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    fresh_session: bool = False
    context_packet_id: Identifier | None = None
    context_packet_sha256: Sha256 | None = None
    source_graph_revision: int | None = Field(default=None, ge=1)
    source_graph_hash: Sha256 | None = None
    selected_node_ids: tuple[Identifier, ...] = ()
    session_id: Identifier | None = None
    model_id: str | None = None
    injected_memories: tuple[MemoryRef, ...] = ()
    proof: tuple[ProofItem, ...] = ()
    policy_checks: tuple[PolicyCheck, ...] = ()
    candidate: CandidateArtifact | None = None
    promotion_decision: HumanDecision | None = None
    promotion_receipt: PromotionReceipt | None = None
    error: BoundedText | None = None
    created_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def persisted_bindings_are_consistent(self) -> RunRecord:
        sequences = tuple(item.sequence for item in self.proof)
        if sequences != tuple(range(1, len(self.proof) + 1)):
            raise ValueError("proof sequences must be contiguous")
        if any(item.run_id != self.run_id for item in self.proof):
            raise ValueError("proof items must belong to their run")
        if len({item.event_id for item in self.proof}) != len(self.proof):
            raise ValueError("proof event IDs must be unique")
        proof_types = {item.type for item in self.proof}
        expected_profile = {
            TaskId.BASELINE_MAX_ATTEMPTS: "platform-maintainer@1",
            TaskId.ADAPTED_WINDOW_SECONDS: "auth-maintainer@1",
        }[self.task_id]
        if self.agent_profile_id is not None and self.agent_profile_id != expected_profile:
            raise ValueError("task must use its server-owned catalog profile")
        if self.state != RunState.QUEUED and (
            self.agent_profile_id is None
            or self.base_sha is None
            or self.session_id is None
            or not self.allowed_paths
            or not self.allowed_tools
        ):
            raise ValueError("started runs require server-observed identity and scope")
        packet_fields = (
            self.context_packet_id,
            self.context_packet_sha256,
            self.source_graph_revision,
            self.source_graph_hash,
        )
        if any(value is None for value in packet_fields) != all(
            value is None for value in packet_fields
        ):
            raise ValueError("context and source-graph bindings are all-or-none")
        if self.injected_memories and (
            not self.fresh_session
            or any(value is None for value in packet_fields)
            or not self.selected_node_ids
        ):
            raise ValueError("memory injection requires a fresh, packet-bound session")
        if self.state in {RunState.QUEUED, RunState.RUNNING} and self.candidate is not None:
            raise ValueError("candidate artifacts appear only after bounded execution")
        if (
            self.state
            in {
                RunState.WAITING_FOR_PROMOTION,
                RunState.PROMOTING,
                RunState.COMPLETED,
            }
            and self.candidate is None
        ):
            raise ValueError("promotion states require a persisted candidate")
        if (
            self.state
            in {
                RunState.WAITING_FOR_PROMOTION,
                RunState.PROMOTING,
                RunState.COMPLETED,
            }
            and ProofType.COMPLETION_DENIED not in proof_types
        ):
            raise ValueError("promotion states require the automatic completion denial")
        if self.candidate is not None and self.injected_memories:
            base_exit = self.candidate.test_receipt.base_with_new_test_exit_code
            if (
                base_exit is None
                or base_exit == 0
                or P0_REQUIRED_TEST_PATH not in self.candidate.changed_paths
            ):
                raise ValueError("memory-bound candidates require a new test that fails on base")
        if self.candidate is not None and self.base_sha != self.candidate.base_commit_sha:
            raise ValueError("candidate base must match the server-observed run base")
        if self.candidate is not None and not any(
            check.decision == "denied"
            and check.candidate_patch_sha256 == self.candidate.candidate_patch_sha256
            and check.test_receipt_sha256 == self.candidate.test_receipt.receipt_sha256
            and check.run_id == self.run_id
            for check in self.policy_checks
        ):
            raise ValueError("candidate requires the authoritative completion denial")
        if self.state in {RunState.PROMOTING, RunState.COMPLETED} and (
            self.promotion_decision is None
            or self.promotion_decision.value != MemoryDecisionValue.APPROVE
            or self.promotion_decision.purpose != "promotion"
            or self.candidate is None
            or self.promotion_decision.bound_digest != self.candidate.candidate_patch_sha256
        ):
            raise ValueError("promoting runs require explicit human approval")
        if self.promotion_decision is not None and self.state not in {
            RunState.PROMOTING,
            RunState.COMPLETED,
            RunState.FAILED,
        }:
            raise ValueError("human promotion decisions belong only to promotion attempts")
        if self.promotion_decision is not None and ProofType.PROMOTION_APPROVED not in proof_types:
            raise ValueError("human promotion decisions require matching proof")
        if self.state in {RunState.PROMOTING, RunState.COMPLETED} and (
            ProofType.PROMOTION_APPROVED not in proof_types
        ):
            raise ValueError("human promotion approval must appear in the proof")
        if self.state == RunState.COMPLETED and self.promotion_receipt is None:
            raise ValueError("completed runs require a promotion receipt")
        if self.promotion_receipt is not None and self.state != RunState.COMPLETED:
            raise ValueError("only a completed run may contain a promotion receipt")
        if self.state == RunState.COMPLETED and ProofType.CANDIDATE_COMMITTED not in proof_types:
            raise ValueError("completed runs require committed-candidate proof")
        if self.promotion_receipt is not None:
            receipt = self.promotion_receipt
            candidate = self.candidate
            if candidate is None or (
                receipt.run_id != self.run_id
                or receipt.base_commit_sha != candidate.base_commit_sha
                or receipt.candidate_patch_sha256 != candidate.candidate_patch_sha256
                or receipt.candidate_tree_sha256 != candidate.candidate_tree_sha256
                or receipt.test_receipt_sha256 != candidate.test_receipt.receipt_sha256
                or receipt.context_packet_id != self.context_packet_id
                or receipt.context_packet_sha256 != self.context_packet_sha256
                or receipt.source_graph_revision != self.source_graph_revision
                or receipt.source_graph_hash != self.source_graph_hash
                or receipt.selected_node_ids != self.selected_node_ids
                or receipt.expected_run_revision + 2 != self.revision
                or self.promotion_decision is None
                or receipt.human_decision_id != self.promotion_decision.decision_id
                or MemoryRef(
                    memory_id=receipt.memory_id,
                    revision=receipt.memory_revision,
                )
                not in self.injected_memories
            ):
                raise ValueError("promotion receipt must bind the persisted candidate and memory")
        return self


class DemoResetRequest(FrozenModel):
    idempotency_key: IdempotencyKey


class CreateRunRequest(FrozenModel):
    task_id: TaskId
    idempotency_key: IdempotencyKey


class ExecuteRunRequest(FrozenModel):
    expected_run_revision: int = Field(ge=0)
    idempotency_key: IdempotencyKey


class FeedbackRequest(FrozenModel):
    correction: BoundedText
    evidence_event_id: Identifier
    selected_hunk_id: Identifier
    scope_id: ScopeId
    expected_run_revision: int = Field(ge=0)
    idempotency_key: IdempotencyKey


class MemoryDecisionRequest(FrozenModel):
    decision: MemoryDecisionValue
    expected_revision: int = Field(ge=1)
    idempotency_key: IdempotencyKey


class PromoteRunRequest(FrozenModel):
    expected_run_revision: int = Field(ge=0)
    base_commit_sha: GitSha
    candidate_patch_sha256: Sha256
    candidate_tree_sha256: Sha256
    candidate_tree_hash_version: Literal["graphene.tree.v2"]
    memory_id: Identifier
    memory_revision: int = Field(ge=1)
    context_packet_id: Identifier
    context_packet_sha256: Sha256
    source_graph_revision: int = Field(ge=1)
    source_graph_hash: Sha256
    selected_node_ids: tuple[Identifier, ...]
    test_receipt_sha256: Sha256
    idempotency_key: IdempotencyKey


class AgentProfile(FrozenModel):
    agent_profile_id: AgentProfileId
    owner_team: Identifier
    purpose: BoundedText
    model_policy: BoundedText
    framework: Literal["driver-selected"] = "driver-selected"
    repo_ids: tuple[Identifier, ...]
    allowed_paths: tuple[RepoPath, ...]
    allowed_tools: tuple[Literal["read_file", "write_file", "run_fixture_tests"], ...]
    memory_access: tuple[str, ...]
    data_classification: Literal["sanitized_fixture"]
    policy_revision: int = Field(ge=1)
    status: Literal["active"]

    @model_validator(mode="after")
    def scope_is_nonempty_and_unique(self) -> AgentProfile:
        for values in (
            self.repo_ids,
            self.allowed_paths,
            self.allowed_tools,
            self.memory_access,
        ):
            if not values or len(set(values)) != len(values):
                raise ValueError("catalog scopes must be nonempty and unique")
        return self


class PacketMemory(FrozenModel):
    memory_id: Identifier
    revision: int = Field(ge=1)
    exact_text: BoundedText


class RelatedFile(FrozenModel):
    path: RepoPath
    reason: BoundedText


class ContextPacket(FrozenModel):
    packet_id: Identifier
    consumer_run_id: Identifier
    consumer_agent_profile_id: AgentProfileId
    task_id: TaskId
    repo_id: Identifier
    base_sha: GitSha
    allowed_paths: tuple[RepoPath, ...]
    allowed_tools: tuple[str, ...]
    approved_memories: tuple[PacketMemory, ...]
    related_files: tuple[RelatedFile, ...]
    required_test_profile: Identifier
    source_graph_revision: int = Field(ge=1)
    source_graph_hash: Sha256
    selected_node_ids: tuple[Identifier, ...]
    decision: ContextDecision
    packet_sha256: Sha256

    @model_validator(mode="after")
    def packet_is_bounded_and_canonical(self) -> ContextPacket:
        if (
            len(self.approved_memories) > GRAPH_MAX_MEMORIES
            or len(self.related_files) > GRAPH_MAX_RELATED_FILES
            or len(set(self.selected_node_ids)) != len(self.selected_node_ids)
            or len(set(self.allowed_paths)) != len(self.allowed_paths)
            or len(set(self.allowed_tools)) != len(self.allowed_tools)
        ):
            raise ValueError("context packet exceeds a cap or contains duplicates")
        if self.decision == ContextDecision.DENIED_OUT_OF_SCOPE and (
            self.approved_memories
            or self.related_files
            or self.allowed_paths
            or self.allowed_tools
            or self.selected_node_ids
        ):
            raise ValueError("denied packets cannot disclose context or permissions")
        expected = canonical_json_sha256(self.model_dump(mode="json", exclude={"packet_sha256"}))
        if self.packet_sha256 != expected:
            raise ValueError("packet hash must cover canonical packet JSON")
        return self


class InjectionReceipt(FrozenModel):
    receipt_id: Identifier
    run_id: Identifier
    session_id: Identifier
    consumer_agent_profile_id: AgentProfileId
    packet_id: Identifier
    packet_sha256: Sha256
    source_graph_revision: int = Field(ge=1)
    source_graph_hash: Sha256
    selected_node_ids: tuple[Identifier, ...]
    memory_revisions: tuple[MemoryRef, ...]
    persisted_before_model_call: Literal[True]
    occurred_at: UtcDateTime
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def receipt_is_canonical(self) -> InjectionReceipt:
        expected = canonical_json_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if self.receipt_sha256 != expected:
            raise ValueError("injection receipt hash must cover canonical JSON")
        return self


class HunkEvidence(FrozenModel):
    hunk_id: Identifier
    path: RepoPath
    old_start: int = Field(ge=0)
    old_lines: int = Field(ge=0)
    new_start: int = Field(ge=0)
    new_lines: int = Field(ge=0)
    before_sha256: Sha256 | None
    after_sha256: Sha256
    canonical_patch_sha256: Sha256
    exact_hunk_sha256: Sha256
    candidate_revision: int = Field(ge=1)
    unified_diff: str

    @model_validator(mode="after")
    def hunk_bytes_match_digest(self) -> HunkEvidence:
        raw = self.unified_diff.encode()
        if len(raw) > MAX_PATCH_BYTES or sha256_hex(raw) != self.exact_hunk_sha256:
            raise ValueError("hunk digest must match its size-capped exact bytes")
        return self


class GraphNode(FrozenModel):
    id: Identifier
    kind: GraphNodeKind
    label: BoundedText
    repo_id: Identifier
    run_id: Identifier | None = None
    provenance: GraphProvenance
    source_ref: BoundedText
    digest: Sha256
    status: str
    created_at: UtcDateTime
    data: dict[str, Any]


class GraphEdge(FrozenModel):
    id: Identifier
    source: Identifier
    kind: GraphEdgeKind
    target: Identifier
    provenance: GraphProvenance
    source_ref: BoundedText
    digest: Sha256
    advisory: bool = False


class GraphResponse(FrozenModel):
    revision: int = Field(ge=1)
    graph_hash: Sha256
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    truncated: bool
    omitted_counts: dict[str, int]

    @model_validator(mode="after")
    def graph_is_bounded_and_canonical(self) -> GraphResponse:
        if len(self.nodes) > GRAPH_MAX_NODES or len(self.edges) > GRAPH_MAX_EDGES:
            raise ValueError("graph response exceeds hard caps")
        node_ids = tuple(node.id for node in self.nodes)
        edge_ids = tuple(edge.id for edge in self.edges)
        if (
            node_ids != tuple(sorted(set(node_ids)))
            or edge_ids != tuple(sorted(set(edge_ids)))
            or any(
                edge.source not in node_ids or edge.target not in node_ids for edge in self.edges
            )
            or any(value < 0 for value in self.omitted_counts.values())
            or self.truncated != any(value > 0 for value in self.omitted_counts.values())
        ):
            raise ValueError("graph nodes and edges must be sorted, unique, and resolvable")
        expected = canonical_json_sha256(self.model_dump(mode="json", exclude={"graph_hash"}))
        if self.graph_hash != expected:
            raise ValueError("graph hash must cover canonical response JSON")
        return self


class GraphQuery(FrozenModel):
    depth: int = Field(default=1, ge=0, le=GRAPH_MAX_DEPTH)
    path_prefix: RepoPath | None = None
    kinds: tuple[GraphNodeKind, ...] = ()
    current_run_only: bool = False
    show_memory_origin: bool = True


class GraphCaps(FrozenModel):
    default_depth: int = Field(ge=0, le=GRAPH_MAX_DEPTH)
    max_depth: int = Field(ge=1, le=GRAPH_MAX_DEPTH)
    max_nodes: Literal[25]
    max_edges: Literal[40]
    max_related_files: Literal[8]
    max_hunks: Literal[12]
    max_memories: Literal[3]
    max_origin_runs_per_memory: Literal[1]
    max_patch_bytes: Literal[102400]


class TaskProfileBinding(FrozenModel):
    task_id: TaskId
    agent_profile_id: AgentProfileId
    fresh_session: bool


class GraphMvpContract(FrozenModel):
    schema_version: Literal[1]
    repo_id: Identifier
    graph_revision: Literal[1]
    caps: GraphCaps
    catalog: tuple[AgentProfile, ...]
    task_profiles: tuple[TaskProfileBinding, ...]
    node_kinds: tuple[GraphNodeKind, ...]
    edge_kinds: tuple[GraphEdgeKind, ...]
    node_data_fields: dict[GraphNodeKind, tuple[str, ...]]
    binding_requirements: dict[str, tuple[str, ...]]
    depth_semantics: Literal["mandatory_evidence_spine_plus_optional_neighbors"]
    api: tuple[ApiEndpoint, ...]
    negative_profile_id: AgentProfileId
    required_test_profile: Identifier

    @model_validator(mode="after")
    def contract_is_frozen(self) -> GraphMvpContract:
        if (
            tuple(self.node_kinds) != tuple(GraphNodeKind)
            or tuple(self.edge_kinds) != tuple(GraphEdgeKind)
            or len(self.catalog) != 3
            or len({item.agent_profile_id for item in self.catalog}) != 3
            or self.task_profiles
            != (
                TaskProfileBinding(
                    task_id=TaskId.BASELINE_MAX_ATTEMPTS,
                    agent_profile_id="platform-maintainer@1",
                    fresh_session=False,
                ),
                TaskProfileBinding(
                    task_id=TaskId.ADAPTED_WINDOW_SECONDS,
                    agent_profile_id="auth-maintainer@1",
                    fresh_session=True,
                ),
            )
            or set(self.node_data_fields) != set(GraphNodeKind)
            or set(self.binding_requirements)
            != {"test_receipt", "human_decision", "promotion", "adapted_run"}
            or self.negative_profile_id != "billing-observer@1"
            or self.negative_profile_id not in {item.agent_profile_id for item in self.catalog}
            or any(
                endpoint.method != "GET" or not endpoint.requires_demo_token
                for endpoint in self.api
            )
        ):
            raise ValueError("post-Phase-0 graph contract is frozen")
        return self


# Version 2 is additive while the legacy browser receipt contracts remain readable.
class LineageEventType(StrEnum):
    RUN_STARTED = "run.started"
    INVOCATION_STARTED = "invocation.started"
    INVOCATION_COMPLETED = "invocation.completed"
    INVOCATION_FAILED = "invocation.failed"
    RUN_INTERRUPTED = "run.interrupted"
    RUN_FAILED = "run.failed"
    RUN_ENDED = "run.ended"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    CLARIFICATION_ASKED = "clarification.asked"
    CLARIFICATION_ANSWERED = "clarification.answered"
    COMPLETION_ATTEMPTED = "completion.attempted"
    CANDIDATE_CREATED = "candidate.created"
    CANDIDATE_REJECTED = "candidate.rejected"
    CHANGESET_PARSED = "changeset.parsed"
    TEST_RECEIPT_CREATED = "test.receipt.created"
    FEEDBACK_RECORDED = "feedback.recorded"
    MEMORY_PROPOSED = "memory.proposed"
    MEMORY_APPROVED = "memory.approved"
    MEMORY_REJECTED = "memory.rejected"
    PROMOTION_APPROVED = "promotion.approved"
    CONTEXT_COMPILED = "context.compiled"
    CONTEXT_INJECTED = "context.injected"
    HANDOFF_DENIED = "handoff.denied"
    SCOPE_ALLOWED = "scope.allowed"
    SCOPE_DENIED = "scope.denied"
    COMPLETION_DENIED = "completion.denied"
    PROMOTION_DENIED = "promotion.denied"
    PROMOTION_COMPLETED = "promotion.completed"
    LOCAL_RESULT_RECORDED = "local_result.recorded"


class TruthKind(StrEnum):
    RUNTIME_OBSERVED = "runtime_observed"
    SERVER_DERIVED = "server_derived"
    HUMAN_ATTESTED = "human_attested"
    SIMULATED_FIXTURE = "simulated_fixture"
    POLICY_AUTHORITATIVE = "policy_authoritative"
    MODEL_PROPOSED = "model_proposed"


class LineageAuthority(StrEnum):
    SCOPED_TOOL_WRAPPER = "scoped_tool_wrapper"
    ADK_ADAPTER = "adk_adapter"
    MCP_ADAPTER = "mcp_adapter"
    LOCAL_ADAPTER = "local_adapter"
    LIFECYCLE_SERVICE = "lifecycle_service"
    POLICY_ENGINE = "policy_engine"
    OPERATOR_REQUEST = "operator_request"
    SIMULATED_FIXTURE = "simulated_fixture"
    CONTEXT_COMPILER = "context_compiler"
    ARTIFACT_PARSER = "artifact_parser"
    PROMOTION_SERVICE = "promotion_service"
    LOCAL_COMMIT_SERVICE = "local_commit_service"


class LineageOperation(StrEnum):
    SEARCH_REPO = "search_repo"
    READ_FILE = "read_file"
    OPEN_EVIDENCE = "open_evidence"
    WRITE_FILE = "write_file"
    RUN_FIXED_TEST = "run_fixed_test"
    REQUEST_COMPLETION = "request_completion"


class LineageRunState(StrEnum):
    STARTING = "STARTING"
    LIVE = "LIVE"
    WAITING_INPUT = "WAITING_INPUT"
    ACCESS_DENIED = "ACCESS_DENIED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"


class EvidenceKind(StrEnum):
    EVENT = "event"
    FILE_VERSION = "file_version"
    CHANGESET = "changeset"
    HUNK = "hunk"
    TOOL_RECEIPT = "tool_receipt"
    TEST_RECEIPT = "test_receipt"
    FEEDBACK = "feedback"
    MEMORY_REVISION = "memory_revision"
    CHECKPOINT = "checkpoint"
    HANDOFF_DECISION = "handoff_decision"
    CONTEXT_BRIEF = "context_brief"
    INJECTION_RECEIPT = "injection_receipt"
    PROMOTION_RECEIPT = "promotion_receipt"
    EVIDENCE_BLOB = "evidence_blob"
    POLICY_RECEIPT = "policy_receipt"
    OPERATOR_REQUEST = "operator_request"
    SIMULATED_FIXTURE = "simulated_fixture"
    ADK_EVENT_RECEIPT = "adk_event_receipt"
    MCP_REQUEST_RECEIPT = "mcp_request_receipt"
    LOCAL_ADAPTER_RECEIPT = "local_adapter_receipt"
    LOCAL_COMMIT_RECEIPT = "local_commit_receipt"


class SourceKind(StrEnum):
    TOOL_RECEIPT = "tool_receipt"
    LIFECYCLE_REQUEST = "lifecycle_request"
    POLICY_EVALUATION = "policy_evaluation"
    OPERATOR_REQUEST = "operator_request"
    SIMULATED_FIXTURE = "simulated_fixture"
    REDUCER_RECEIPT = "reducer_receipt"
    CONTEXT_COMPILER_RECEIPT = "context_compiler_receipt"
    ADK_EVENT_RECEIPT = "adk_event_receipt"
    MCP_REQUEST_RECEIPT = "mcp_request_receipt"
    LOCAL_ADAPTER_RECEIPT = "local_adapter_receipt"
    PROMOTION_RECEIPT = "promotion_receipt"
    LOCAL_COMMIT_RECEIPT = "local_commit_receipt"


class EvidenceReference(FrozenModel):
    kind: EvidenceKind
    id: Identifier
    sha256: Sha256


class SourceReference(FrozenModel):
    kind: SourceKind
    id: Identifier
    sha256: Sha256


_EVENT_AUTHORITY = {
    LineageEventType.RUN_STARTED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.LIFECYCLE_SERVICE,
    ),
    LineageEventType.INVOCATION_STARTED: (
        TruthKind.RUNTIME_OBSERVED,
        LineageAuthority.ADK_ADAPTER,
    ),
    LineageEventType.INVOCATION_COMPLETED: (
        TruthKind.RUNTIME_OBSERVED,
        LineageAuthority.ADK_ADAPTER,
    ),
    LineageEventType.INVOCATION_FAILED: (
        TruthKind.RUNTIME_OBSERVED,
        LineageAuthority.ADK_ADAPTER,
    ),
    LineageEventType.RUN_INTERRUPTED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.LIFECYCLE_SERVICE,
    ),
    LineageEventType.RUN_FAILED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.LIFECYCLE_SERVICE,
    ),
    LineageEventType.RUN_ENDED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.LIFECYCLE_SERVICE,
    ),
    LineageEventType.TOOL_STARTED: (
        TruthKind.RUNTIME_OBSERVED,
        LineageAuthority.SCOPED_TOOL_WRAPPER,
    ),
    LineageEventType.TOOL_COMPLETED: (
        TruthKind.RUNTIME_OBSERVED,
        LineageAuthority.SCOPED_TOOL_WRAPPER,
    ),
    LineageEventType.TOOL_FAILED: (
        TruthKind.RUNTIME_OBSERVED,
        LineageAuthority.SCOPED_TOOL_WRAPPER,
    ),
    LineageEventType.CLARIFICATION_ASKED: (
        TruthKind.POLICY_AUTHORITATIVE,
        LineageAuthority.POLICY_ENGINE,
    ),
    LineageEventType.CLARIFICATION_ANSWERED: (
        TruthKind.HUMAN_ATTESTED,
        LineageAuthority.OPERATOR_REQUEST,
    ),
    LineageEventType.COMPLETION_ATTEMPTED: (
        TruthKind.MODEL_PROPOSED,
        LineageAuthority.ADK_ADAPTER,
    ),
    LineageEventType.CANDIDATE_CREATED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.ARTIFACT_PARSER,
    ),
    LineageEventType.CANDIDATE_REJECTED: (
        TruthKind.HUMAN_ATTESTED,
        LineageAuthority.OPERATOR_REQUEST,
    ),
    LineageEventType.CHANGESET_PARSED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.ARTIFACT_PARSER,
    ),
    LineageEventType.TEST_RECEIPT_CREATED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.ARTIFACT_PARSER,
    ),
    LineageEventType.FEEDBACK_RECORDED: (
        TruthKind.HUMAN_ATTESTED,
        LineageAuthority.OPERATOR_REQUEST,
    ),
    LineageEventType.MEMORY_PROPOSED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.LIFECYCLE_SERVICE,
    ),
    LineageEventType.MEMORY_APPROVED: (
        TruthKind.HUMAN_ATTESTED,
        LineageAuthority.OPERATOR_REQUEST,
    ),
    LineageEventType.MEMORY_REJECTED: (
        TruthKind.HUMAN_ATTESTED,
        LineageAuthority.OPERATOR_REQUEST,
    ),
    LineageEventType.PROMOTION_APPROVED: (
        TruthKind.HUMAN_ATTESTED,
        LineageAuthority.OPERATOR_REQUEST,
    ),
    LineageEventType.CONTEXT_COMPILED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.CONTEXT_COMPILER,
    ),
    LineageEventType.CONTEXT_INJECTED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.CONTEXT_COMPILER,
    ),
    LineageEventType.HANDOFF_DENIED: (
        TruthKind.POLICY_AUTHORITATIVE,
        LineageAuthority.CONTEXT_COMPILER,
    ),
    LineageEventType.SCOPE_ALLOWED: (
        TruthKind.POLICY_AUTHORITATIVE,
        LineageAuthority.POLICY_ENGINE,
    ),
    LineageEventType.SCOPE_DENIED: (
        TruthKind.POLICY_AUTHORITATIVE,
        LineageAuthority.POLICY_ENGINE,
    ),
    LineageEventType.COMPLETION_DENIED: (
        TruthKind.POLICY_AUTHORITATIVE,
        LineageAuthority.POLICY_ENGINE,
    ),
    LineageEventType.PROMOTION_DENIED: (
        TruthKind.POLICY_AUTHORITATIVE,
        LineageAuthority.POLICY_ENGINE,
    ),
    LineageEventType.PROMOTION_COMPLETED: (
        TruthKind.SERVER_DERIVED,
        LineageAuthority.PROMOTION_SERVICE,
    ),
    LineageEventType.LOCAL_RESULT_RECORDED: (
        TruthKind.RUNTIME_OBSERVED,
        LineageAuthority.LOCAL_COMMIT_SERVICE,
    ),
}

_SOURCE_KIND_BY_AUTHORITY = {
    LineageAuthority.SCOPED_TOOL_WRAPPER: SourceKind.TOOL_RECEIPT,
    LineageAuthority.ADK_ADAPTER: SourceKind.ADK_EVENT_RECEIPT,
    LineageAuthority.MCP_ADAPTER: SourceKind.MCP_REQUEST_RECEIPT,
    LineageAuthority.LOCAL_ADAPTER: SourceKind.LOCAL_ADAPTER_RECEIPT,
    LineageAuthority.LIFECYCLE_SERVICE: SourceKind.LIFECYCLE_REQUEST,
    LineageAuthority.POLICY_ENGINE: SourceKind.POLICY_EVALUATION,
    LineageAuthority.OPERATOR_REQUEST: SourceKind.OPERATOR_REQUEST,
    LineageAuthority.SIMULATED_FIXTURE: SourceKind.SIMULATED_FIXTURE,
    LineageAuthority.CONTEXT_COMPILER: SourceKind.CONTEXT_COMPILER_RECEIPT,
    LineageAuthority.ARTIFACT_PARSER: SourceKind.REDUCER_RECEIPT,
    LineageAuthority.PROMOTION_SERVICE: SourceKind.PROMOTION_RECEIPT,
    LineageAuthority.LOCAL_COMMIT_SERVICE: SourceKind.LOCAL_COMMIT_RECEIPT,
}

_ADAPTER_AUTHORITIES = {
    "adk": LineageAuthority.ADK_ADAPTER,
    "mcp": LineageAuthority.MCP_ADAPTER,
    "local": LineageAuthority.LOCAL_ADAPTER,
}
_ADAPTER_EVENT_TYPES = {
    LineageEventType.INVOCATION_STARTED,
    LineageEventType.INVOCATION_COMPLETED,
    LineageEventType.INVOCATION_FAILED,
    LineageEventType.COMPLETION_ATTEMPTED,
}
_SIMULATED_FIXTURE_EVENT_TYPES = {
    LineageEventType.CLARIFICATION_ANSWERED,
    LineageEventType.FEEDBACK_RECORDED,
    LineageEventType.MEMORY_APPROVED,
    LineageEventType.MEMORY_REJECTED,
    LineageEventType.PROMOTION_APPROVED,
    LineageEventType.CANDIDATE_REJECTED,
}


_FORBIDDEN_EVENT_PAYLOAD_KEYS = frozenset(
    {
        "authorization",
        "content",
        "diff",
        "model_output",
        "patch",
        "prompt",
        "raw_source",
        "secret",
        "stderr",
        "stdout",
        "token",
    }
)

_TOOL_COMPLETED_PAYLOAD_FIELDS = frozenset(
    {
        "added_lines",
        "after_file_version_id",
        "baseline_bytes",
        "baseline_lines",
        "before_file_version_id",
        "bound_paths",
        "byte_count",
        "candidate_written_versions_sha256",
        "content_sha256",
        "deleted_lines",
        "duration_bucket",
        "evidence_id",
        "exit_code",
        "file_version_id",
        "line_count",
        "match_count",
        "operation",
        "output_byte_count",
        "output_sha256",
        "output_truncated",
        "passed",
        "path",
        "paths",
        "state",
        "status",
        "timed_out",
        "truncated",
    }
)
_EVENT_PAYLOAD_FIELDS = {
    LineageEventType.RUN_STARTED: frozenset(
        {"context_compiled_event_sha256", "source_run_id", "state"}
    ),
    LineageEventType.INVOCATION_STARTED: frozenset(
        {"adapter_kind", "framework", "framework_version", "status"}
    ),
    LineageEventType.INVOCATION_COMPLETED: frozenset({"adapter_kind", "status"}),
    LineageEventType.INVOCATION_FAILED: frozenset({"adapter_kind", "error_code", "status"}),
    LineageEventType.RUN_INTERRUPTED: frozenset(
        {
            "checkout_binding_sha256",
            "reason_code",
            "recovery_kind",
            "state",
            "status",
            "unmatched_invocations",
            "unmatched_tool_starts",
        }
    ),
    LineageEventType.RUN_FAILED: frozenset({"error_code", "reason_code", "state", "status"}),
    LineageEventType.RUN_ENDED: frozenset({"reason_code", "state", "status"}),
    LineageEventType.TOOL_STARTED: frozenset({"operation", "status"}),
    LineageEventType.TOOL_COMPLETED: _TOOL_COMPLETED_PAYLOAD_FIELDS,
    LineageEventType.TOOL_FAILED: frozenset({"error_code", "operation", "status"}),
    LineageEventType.CLARIFICATION_ASKED: frozenset(
        {"choice_count", "question_id", "question_sha256", "status"}
    ),
    LineageEventType.CLARIFICATION_ANSWERED: frozenset(
        {
            "answer_id",
            "answer_sha256",
            "choice",
            "operator_label",
            "operator_rationale",
            "question_id",
            "status",
        }
    ),
    LineageEventType.COMPLETION_ATTEMPTED: frozenset({"adapter_kind", "operation", "status"}),
    LineageEventType.CANDIDATE_CREATED: frozenset(
        {
            "candidate_id",
            "candidate_patch_sha256",
            "candidate_tree_sha256",
            "candidate_tree_hash_version",
            "changed_path_count",
            "status",
        }
    ),
    LineageEventType.CANDIDATE_REJECTED: frozenset(
        {
            "candidate_id",
            "candidate_patch_sha256",
            "decision_id",
            "operator_label",
            "operator_rationale",
            "status",
        }
    ),
    LineageEventType.CHANGESET_PARSED: frozenset(
        {
            "candidate_patch_sha256",
            "changed_paths",
            "changeset_id",
            "hunk_count",
            "status",
        }
    ),
    LineageEventType.TEST_RECEIPT_CREATED: frozenset(
        {
            "bound_paths",
            "passed",
            "receipt_id",
            "receipt_sha256",
            "status",
        }
    ),
    LineageEventType.FEEDBACK_RECORDED: frozenset(
        {
            "correction_sha256",
            "evidence_event_id",
            "feedback_id",
            "hunk_id",
            "operator_label",
            "operator_rationale",
            "scope_id",
            "status",
        }
    ),
    LineageEventType.MEMORY_PROPOSED: frozenset(
        {"memory_id", "memory_sha256", "revision", "status"}
    ),
    LineageEventType.MEMORY_APPROVED: frozenset(
        {
            "decision_id",
            "memory_id",
            "memory_sha256",
            "operator_label",
            "operator_rationale",
            "revision",
            "status",
        }
    ),
    LineageEventType.MEMORY_REJECTED: frozenset(
        {
            "decision_id",
            "memory_id",
            "memory_sha256",
            "operator_label",
            "operator_rationale",
            "revision",
            "status",
        }
    ),
    LineageEventType.PROMOTION_APPROVED: frozenset(
        {
            "candidate_patch_sha256",
            "decision_id",
            "decision_sha256",
            "expected_head_sha256",
            "operator_label",
            "operator_rationale",
            "status",
        }
    ),
    LineageEventType.CONTEXT_COMPILED: frozenset(
        {
            "brief_artifact_sha256",
            "brief_sha256",
            "candidate_set_sha256",
            "decision_artifact_sha256",
            "decision_sha256",
            "memory_scopes",
            "source_graph_sha256",
            "status",
        }
    ),
    LineageEventType.CONTEXT_INJECTED: frozenset(
        {
            "brief_sha256",
            "decision_sha256",
            "injection_receipt_sha256",
            "prior_message_count",
            "prompt_sha256",
            "source_head_seq",
            "source_run_id",
            "status",
        }
    ),
    LineageEventType.HANDOFF_DENIED: frozenset(
        {
            "evidence_count",
            "memory_count",
            "model_dispatch_count",
            "reason_code",
            "source_path_count",
            "status",
            "target_profile_id",
            "task_id",
            "tool_count",
        }
    ),
    LineageEventType.SCOPE_ALLOWED: frozenset({"operation", "reason_code", "status"}),
    LineageEventType.SCOPE_DENIED: frozenset({"operation", "reason_code", "status"}),
    LineageEventType.COMPLETION_DENIED: frozenset({"operation", "reason_code", "state", "status"}),
    LineageEventType.PROMOTION_DENIED: frozenset(
        {"candidate_patch_sha256", "reason_code", "status"}
    ),
    LineageEventType.PROMOTION_COMPLETED: frozenset(
        {
            "candidate_patch_sha256",
            "promotion_receipt_id",
            "promotion_receipt_sha256",
            "status",
        }
    ),
    LineageEventType.LOCAL_RESULT_RECORDED: frozenset(
        {
            "approval_event_id",
            "approval_event_sha256",
            "candidate_patch_sha256",
            "candidate_tree_sha256",
            "candidate_tree_hash_version",
            "changed_paths",
            "deployed",
            "local_commit_receipt_id",
            "local_commit_receipt_sha256",
            "local_commit_sha",
            "outcome",
            "parent_sha",
            "pull_request_created",
            "pushed",
            "status",
            "test_receipt_id",
            "test_receipt_sha256",
            "tree_sha",
        }
    ),
}


def _event_payload_is_safe(value: Any) -> bool:
    if isinstance(value, dict):
        return all(
            str(key).lower() not in _FORBIDDEN_EVENT_PAYLOAD_KEYS and _event_payload_is_safe(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_event_payload_is_safe(item) for item in value)
    return value is None or isinstance(value, (str, int, float, bool))


class EventInput(FrozenModel):
    session_id: Identifier | None
    invocation_id: Identifier | None
    model_id: BoundedText | None
    tool_call_id: Identifier | None
    repo_id: Identifier
    base_sha: GitSha
    agent_profile_id: AgentProfileId
    policy_revision: int = Field(ge=1)
    event_type: LineageEventType
    truth_kind: TruthKind
    authority: LineageAuthority
    references: tuple[EvidenceReference, ...] = Field(max_length=16)
    source_ref: SourceReference
    payload: dict[str, Any]

    @model_validator(mode="after")
    def event_input_is_bounded(self) -> EventInput:
        if len(canonical_json_bytes(self.payload)) > 4_096 or not _event_payload_is_safe(
            self.payload
        ):
            raise ValueError("event payload is unsafe or exceeds the byte cap")
        if not set(self.payload) <= _EVENT_PAYLOAD_FIELDS[self.event_type]:
            raise ValueError("event payload contains fields outside its public allowlist")
        if (
            self.event_type == LineageEventType.CANDIDATE_CREATED
            and self.payload.get("candidate_tree_hash_version") != "graphene.tree.v2"
        ):
            raise ValueError("candidate event requires the v2 tree hash binding")
        reference_keys = tuple((item.kind, item.id, item.sha256) for item in self.references)
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError("event references must be unique")
        expected_truth, expected_authority = _EVENT_AUTHORITY[self.event_type]
        adapter_kind = self.payload.get("adapter_kind")
        adapter_authority = _ADAPTER_AUTHORITIES.get(adapter_kind)
        authority_matches = self.authority == expected_authority or (
            self.event_type in _ADAPTER_EVENT_TYPES
            and adapter_authority is not None
            and self.authority == adapter_authority
        )
        simulated_fixture = (
            self.event_type in _SIMULATED_FIXTURE_EVENT_TYPES
            and self.truth_kind == TruthKind.SIMULATED_FIXTURE
            and self.authority == LineageAuthority.SIMULATED_FIXTURE
        )
        if not simulated_fixture and (
            self.truth_kind != expected_truth or not authority_matches
        ):
            raise ValueError("event truth and authority do not match its type")
        if self.source_ref.kind != _SOURCE_KIND_BY_AUTHORITY[self.authority]:
            raise ValueError("event source reference does not match its authority")
        tool_event = self.event_type in {
            LineageEventType.TOOL_STARTED,
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_FAILED,
        }
        if tool_event and (
            self.tool_call_id is None
            or self.truth_kind != TruthKind.RUNTIME_OBSERVED
            or self.authority != LineageAuthority.SCOPED_TOOL_WRAPPER
            or self.payload.get("operation") not in {item.value for item in LineageOperation}
        ):
            raise ValueError("ordinary tool events require wrapper identity and operation")
        if self.event_type in {
            LineageEventType.INVOCATION_STARTED,
            LineageEventType.INVOCATION_COMPLETED,
            LineageEventType.INVOCATION_FAILED,
            LineageEventType.COMPLETION_ATTEMPTED,
        } and (self.session_id is None or self.invocation_id is None or self.model_id is None):
            raise ValueError("invocation events require session, invocation, and model IDs")
        if self.event_type == LineageEventType.COMPLETION_ATTEMPTED and (
            self.truth_kind != TruthKind.MODEL_PROPOSED
            or self.authority not in set(_ADAPTER_AUTHORITIES.values())
            or self.tool_call_id is None
        ):
            raise ValueError("completion attempts require model proposal identity")
        if self.event_type in {
            LineageEventType.CLARIFICATION_ANSWERED,
            LineageEventType.FEEDBACK_RECORDED,
            LineageEventType.MEMORY_APPROVED,
            LineageEventType.MEMORY_REJECTED,
            LineageEventType.PROMOTION_APPROVED,
            LineageEventType.CANDIDATE_REJECTED,
        } and ({"operator_label", "operator_rationale"} & set(self.payload)):
            label = self.payload.get("operator_label")
            rationale = self.payload.get("operator_rationale")
            if (
                not isinstance(label, str)
                or not 1 <= len(label) <= 64
                or (
                    rationale is not None
                    and (not isinstance(rationale, str) or len(rationale) > 280)
                )
            ):
                raise ValueError("operator attribution is invalid")
        if self.event_type == LineageEventType.CANDIDATE_REJECTED:
            kinds = tuple(reference.kind for reference in self.references)
            expected = {
                EvidenceKind.EVIDENCE_BLOB,
                EvidenceKind.CHANGESET,
                EvidenceKind.TEST_RECEIPT,
                EvidenceKind.CONTEXT_BRIEF,
                EvidenceKind.HANDOFF_DECISION,
                EvidenceKind.MEMORY_REVISION,
            }
            label = self.payload.get("operator_label")
            rationale = self.payload.get("operator_rationale")
            if (
                len(kinds) != len(expected)
                or set(kinds) != expected
                or not isinstance(label, str)
                or not 1 <= len(label) <= 64
                or (rationale is not None and (not isinstance(rationale, str) or len(rationale) > 280))
                or self.payload.get("status") != "rejected"
            ):
                raise ValueError("candidate rejection bindings are invalid")
        if self.event_type == LineageEventType.LOCAL_RESULT_RECORDED:
            by_kind = {reference.kind: reference for reference in self.references}
            expected = {
                EvidenceKind.EVENT,
                EvidenceKind.PROMOTION_RECEIPT,
                EvidenceKind.TEST_RECEIPT,
                EvidenceKind.LOCAL_COMMIT_RECEIPT,
            }
            receipt = by_kind.get(EvidenceKind.LOCAL_COMMIT_RECEIPT)
            approval = by_kind.get(EvidenceKind.EVENT)
            test = by_kind.get(EvidenceKind.TEST_RECEIPT)
            changed_paths = self.payload.get("changed_paths")
            git_values = tuple(
                self.payload.get(name)
                for name in ("local_commit_sha", "parent_sha", "tree_sha")
            )
            try:
                paths_are_safe = (
                    isinstance(changed_paths, list)
                    and changed_paths == sorted(set(changed_paths))
                    and all(_relative_posix_path(path) == path for path in changed_paths)
                )
            except (TypeError, ValueError):
                paths_are_safe = False
            if (
                len(self.references) != len(expected)
                or set(by_kind) != expected
                or receipt is None
                or approval is None
                or test is None
                or self.source_ref.kind != SourceKind.LOCAL_COMMIT_RECEIPT
                or (self.source_ref.id, self.source_ref.sha256)
                != (receipt.id, receipt.sha256)
                or self.payload.get("local_commit_receipt_id") != receipt.id
                or self.payload.get("local_commit_receipt_sha256") != receipt.sha256
                or self.payload.get("approval_event_id") != approval.id
                or self.payload.get("approval_event_sha256") != approval.sha256
                or self.payload.get("test_receipt_id") != test.id
                or self.payload.get("test_receipt_sha256") != test.sha256
                or any(
                    not isinstance(value, str)
                    or len(value) != 40
                    or any(character not in "0123456789abcdef" for character in value)
                    for value in git_values
                )
                or not paths_are_safe
                or self.payload.get("outcome") != "local_isolated_commit"
                or any(
                    self.payload.get(name) is not False
                    for name in ("pushed", "pull_request_created", "deployed")
                )
                or self.payload.get("status") != "recorded"
            ):
                raise ValueError("local commit result bindings are invalid")
        return self


class Event(EventInput):
    schema_version: Literal[2]
    event_id: Identifier
    run_id: Identifier
    seq: int = Field(ge=1)
    server_recorded_at: UtcDateTime
    idempotency_key: IdempotencyKey
    payload_sha256: Sha256
    previous_event_sha256: Sha256 | None
    event_sha256: Sha256

    @model_validator(mode="after")
    def event_hashes_are_canonical(self) -> Event:
        if self.payload_sha256 != canonical_json_sha256(self.payload):
            raise ValueError("event payload digest does not match")
        if (self.seq == 1) != (self.previous_event_sha256 is None):
            raise ValueError("only the first event may omit its previous digest")
        expected = canonical_json_sha256(self.model_dump(mode="json", exclude={"event_sha256"}))
        if self.event_sha256 != expected:
            raise ValueError("event digest does not match its canonical envelope")
        return self


class FileVersion(FrozenModel):
    schema_version: Literal[2]
    file_id: Sha256
    file_version_id: Sha256
    repo_id: Identifier
    path: RepoPath
    content_sha256: Sha256
    byte_count: int = Field(ge=0, le=262_144)
    line_count: int = Field(ge=0, le=100_000)
    artifact_sha256: Sha256

    @model_validator(mode="after")
    def identifiers_match_content(self) -> FileVersion:
        file_id = sha256_hex(f"{self.repo_id}\0{self.path}".encode())
        version_id = sha256_hex(f"{file_id}\0{self.content_sha256}".encode())
        if self.file_id != file_id or self.file_version_id != version_id:
            raise ValueError("file version identifiers do not match")
        return self


class ToolReceipt(FrozenModel):
    schema_version: Literal[2]
    receipt_id: Identifier
    run_id: Identifier
    session_id: Identifier
    invocation_id: Identifier
    model_id: BoundedText | None
    tool_call_id: Identifier
    operation: LineageOperation
    phase: Literal["started", "completed", "failed"]
    status: Identifier
    input_sha256: Sha256
    output_sha256: Sha256 | None
    output_byte_count: int | None = Field(default=None, ge=0)
    error_code: Identifier | None
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def receipt_is_canonical(self) -> ToolReceipt:
        completed = self.phase == "completed"
        if completed != (self.output_sha256 is not None) or completed != (
            self.output_byte_count is not None
        ):
            raise ValueError("only completed receipts bind bounded output metadata")
        if (self.phase == "failed") != (self.error_code is not None):
            raise ValueError("only failed receipts require an error code")
        if self.receipt_sha256 != canonical_json_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        ):
            raise ValueError("tool receipt digest does not match")
        return self


class VerifiedHead(FrozenModel):
    run_id: Identifier
    seq: int = Field(ge=0)
    event_sha256: Sha256 | None
    event_count: int = Field(ge=0)

    @model_validator(mode="after")
    def head_is_consistent(self) -> VerifiedHead:
        if self.event_count != self.seq or (self.seq == 0) != (self.event_sha256 is None):
            raise ValueError("verified head sequence, count, and digest disagree")
        return self


class EvidenceInvalidState(FrozenModel):
    run_id: Identifier
    first_invalid_seq: int | None = Field(default=None, ge=1)
    reason: BoundedText


class HeadCheckpoint(FrozenModel):
    schema_version: Literal[2]
    checkpoint_id: Identifier
    run_id: Identifier
    expected_seq: int = Field(ge=1)
    event_head_sha256: Sha256
    purpose: Identifier
    bound_artifact_kind: EvidenceKind
    bound_artifact_id: Identifier
    bound_artifact_sha256: Sha256
    server_recorded_at: UtcDateTime
    checkpoint_sha256: Sha256

    @model_validator(mode="after")
    def checkpoint_is_canonical(self) -> HeadCheckpoint:
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"checkpoint_sha256"})
        )
        if self.checkpoint_sha256 != expected:
            raise ValueError("checkpoint digest does not match")
        return self


class HandoffDecisionItem(FrozenModel):
    candidate_kind: Identifier
    id: Identifier
    sha256: Sha256
    include: bool
    reason_code: Identifier


class HandoffDecision(FrozenModel):
    schema_version: Literal[2]
    decision_id: Identifier
    source_run_id: Identifier
    source_head: VerifiedHead
    repo_id: Identifier
    base_sha: GitSha
    target_profile_id: AgentProfileId
    target_profile_revision: int = Field(ge=1)
    task_id: Identifier
    policy_revision: int = Field(ge=1)
    candidate_set_sha256: Sha256
    entries: tuple[HandoffDecisionItem, ...] = Field(max_length=256)
    decision: Literal["allowed", "denied"]
    safe_reason_codes: tuple[Identifier, ...]
    safe_counts: dict[str, int]
    server_recorded_at: UtcDateTime
    decision_sha256: Sha256

    @model_validator(mode="after")
    def decision_is_complete_and_canonical(self) -> HandoffDecision:
        keys = tuple((item.candidate_kind, item.id) for item in self.entries)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("handoff candidates must be nonempty, sorted, and unique")
        candidate_set = [
            {
                "candidate_kind": item.candidate_kind,
                "id": item.id,
                "sha256": item.sha256,
            }
            for item in self.entries
        ]
        if self.candidate_set_sha256 != canonical_json_sha256(candidate_set):
            raise ValueError("handoff candidate-set digest does not match")
        included = sum(item.include for item in self.entries)
        expected_counts = {
            "candidates": len(self.entries),
            "excluded": len(self.entries) - included,
            "included": included,
        }
        if self.safe_counts != expected_counts:
            raise ValueError("handoff safe counts must match the complete decision")
        if self.safe_reason_codes != tuple(sorted({item.reason_code for item in self.entries})):
            raise ValueError("handoff reason codes must be canonical")
        if self.decision == "denied" and included:
            raise ValueError("denied handoffs cannot include candidates")
        if self.source_head.run_id != self.source_run_id or self.target_profile_id.rsplit("@", 1)[
            -1
        ] != str(self.target_profile_revision):
            raise ValueError("handoff source head or target profile identity does not match")
        if self.decision_sha256 != canonical_json_sha256(
            self.model_dump(mode="json", exclude={"decision_sha256"})
        ):
            raise ValueError("handoff decision digest does not match")
        return self


class BriefMemory(FrozenModel):
    memory_id: Identifier
    revision: int = Field(ge=1)
    exact_text: BoundedText
    scope_id: ScopeId | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    path_globs: tuple[RepoPath, ...] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    task_tags: tuple[str, ...] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def scope_is_complete(self) -> BriefMemory:
        values = (self.scope_id, self.path_globs, self.task_tags)
        if any(value is None for value in values) != all(
            value is None for value in values
        ):
            raise ValueError("brief memory scope must be complete when present")
        return self


class BriefEvidence(FrozenModel):
    evidence_id: Identifier
    summary: BoundedText
    reference: EvidenceReference


class ContextBrief(FrozenModel):
    schema_version: Literal[2]
    brief_id: Identifier
    repo_id: Identifier
    base_sha: GitSha
    task_id: Identifier
    task_text: BoundedText
    target_profile_id: AgentProfileId
    target_profile_revision: int = Field(ge=1)
    policy_revision: int = Field(ge=1)
    approved_memories: tuple[BriefMemory, ...] = Field(max_length=3)
    selected_evidence: tuple[BriefEvidence, ...] = Field(max_length=16)
    required_paths: tuple[RepoPath, ...] = Field(max_length=16)
    read_scope: tuple[RepoPath, ...] = Field(max_length=32)
    write_scope: tuple[RepoPath, ...] = Field(max_length=8)
    tools: tuple[LineageOperation, ...] = Field(max_length=6)
    fixed_test_profile: Identifier
    byte_caps: dict[str, int]
    event_caps: dict[str, int]
    source_run_id: Identifier
    source_session_id: Identifier | None
    source_head: VerifiedHead
    source_graph_sha256: Sha256
    fresh_session_required: Literal[True]
    brief_sha256: Sha256

    @model_validator(mode="after")
    def brief_is_included_only_and_canonical(self) -> ContextBrief:
        if self.source_head.run_id != self.source_run_id or self.target_profile_id.rsplit("@", 1)[
            -1
        ] != str(self.target_profile_revision):
            raise ValueError("context brief source head or target profile identity does not match")
        for values in (
            self.required_paths,
            self.read_scope,
            self.write_scope,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("context brief paths must be sorted and unique")
        if len(self.tools) != len(set(self.tools)):
            raise ValueError("context brief tools must be unique")
        if tuple((item.memory_id, item.revision) for item in self.approved_memories) != tuple(
            sorted({(item.memory_id, item.revision) for item in self.approved_memories})
        ) or tuple(item.evidence_id for item in self.selected_evidence) != tuple(
            sorted({item.evidence_id for item in self.selected_evidence})
        ):
            raise ValueError("context brief memories and evidence must be canonical")
        if not set(self.required_paths) <= set(self.read_scope):
            raise ValueError("required paths must be readable")
        if not set(self.write_scope) <= set(self.read_scope):
            raise ValueError("write scope must be a subset of read scope")
        if (
            not self.byte_caps
            or not self.event_caps
            or any(value <= 0 for value in (*self.byte_caps.values(), *self.event_caps.values()))
        ):
            raise ValueError("context brief caps must be positive")
        if self.brief_sha256 != canonical_json_sha256(
            self.model_dump(mode="json", exclude={"brief_sha256"})
        ):
            raise ValueError("context brief digest does not match")
        return self


class ClarificationQuestion(FrozenModel):
    schema_version: Literal[2]
    question_id: Identifier
    source_run_id: Identifier
    feedback_id: Identifier
    question_text: BoundedText
    choices: tuple[ScopeId, ...]
    policy_revision: int = Field(ge=1)
    created_at: UtcDateTime
    question_sha256: Sha256

    @model_validator(mode="after")
    def question_is_canonical(self) -> ClarificationQuestion:
        if len(self.choices) < 2 or len(self.choices) != len(set(self.choices)):
            raise ValueError("clarification choices must be unique")
        if self.question_sha256 != canonical_json_sha256(
            self.model_dump(mode="json", exclude={"question_sha256"})
        ):
            raise ValueError("clarification question digest does not match")
        return self


class ClarificationAnswer(FrozenModel):
    schema_version: Literal[2]
    answer_id: Identifier
    question_id: Identifier
    choice: ScopeId
    actor: Literal["human", "simulated_fixture"]
    answered_at: UtcDateTime
    answer_sha256: Sha256

    @model_validator(mode="after")
    def answer_is_canonical(self) -> ClarificationAnswer:
        if self.answer_sha256 != canonical_json_sha256(
            self.model_dump(mode="json", exclude={"answer_sha256"})
        ):
            raise ValueError("clarification answer digest does not match")
        return self


class ContextInjectionReceipt(FrozenModel):
    schema_version: Literal[2]
    receipt_id: Identifier
    consumer_run_id: Identifier
    decision_sha256: Sha256
    brief_sha256: Sha256
    prompt_sha256: Sha256
    session_id: Identifier
    invocation_id: Identifier
    target_profile_id: AgentProfileId
    target_profile_revision: int = Field(ge=1)
    policy_revision: int = Field(ge=1)
    model_id: BoundedText
    prior_message_count: Literal[0]
    persisted_before_dispatch: Literal[True]
    injected_at: UtcDateTime
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def injection_is_canonical(self) -> ContextInjectionReceipt:
        if self.receipt_sha256 != canonical_json_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        ):
            raise ValueError("context injection receipt digest does not match")
        return self


class HandoffDenied(FrozenModel):
    schema_version: Literal[2]
    source_run_id: Identifier
    target_profile_id: AgentProfileId
    task_id: Identifier
    reason_code: Identifier
    memory_count: Literal[0]
    evidence_count: Literal[0]
    source_path_count: Literal[0]
    tool_count: Literal[0]
    consumer_run_id: Literal[None]
    session_id: Literal[None]
    invocation_id: Literal[None]
    model_dispatch_count: Literal[0]


class ProjectionFile(FrozenModel):
    path: RepoPath
    state: Literal["DISCOVERED", "READ", "EDITED", "NEW", "DELETED"]
    file_version_id: Sha256 | None
    baseline_bytes: int | None = Field(default=None, ge=0)
    baseline_lines: int | None = Field(default=None, ge=0)
    size_bucket: int | None = Field(default=None, ge=1, le=4)
    first_seq: int = Field(ge=1)
    last_seq: int = Field(ge=1)
    read_count: int = Field(ge=0)
    added_lines: int = Field(ge=0)
    deleted_lines: int = Field(ge=0)
    bound_test_pass: bool


class ProjectionEvent(FrozenModel):
    seq: int = Field(ge=1)
    event_id: Identifier
    event_type: LineageEventType
    truth_kind: TruthKind
    operation: LineageOperation | None
    status: BoundedText
    path: RepoPath | None


class ProjectionObligation(FrozenModel):
    obligation_id: Identifier
    status: Literal["SATISFIED", "MISSING", "NOT_APPLICABLE"]
    evidence_event_ids: tuple[Identifier, ...]


class LineageProjection(FrozenModel):
    schema_version: Literal[2]
    run_id: Identifier
    state: LineageRunState
    head_seq: int = Field(ge=1)
    head_sha256: Sha256
    files: tuple[ProjectionFile, ...] = Field(max_length=15)
    event_rail: tuple[ProjectionEvent, ...] = Field(max_length=1_000)
    obligations: tuple[ProjectionObligation, ...]
    omitted_counts: dict[str, int]
    unknowns: tuple[BoundedText, ...]
    projection_sha256: Sha256

    @model_validator(mode="after")
    def projection_is_bounded_and_canonical(self) -> LineageProjection:
        if tuple(item.path for item in self.files) != tuple(
            sorted(item.path for item in self.files)
        ) or any(value < 0 for value in self.omitted_counts.values()):
            raise ValueError("projection files and omissions must be canonical")
        if self.projection_sha256 != canonical_json_sha256(
            self.model_dump(mode="json", exclude={"projection_sha256"})
        ):
            raise ValueError("projection digest does not match")
        return self
