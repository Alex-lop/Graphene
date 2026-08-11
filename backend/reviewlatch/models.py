from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from string import Formatter
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .hashing import canonical_json_sha256, sha256_hex


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
    return value.astimezone(timezone.utc)


UtcDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]
MAX_PATCH_BYTES = 102_400
MAX_TEST_OUTPUT_BYTES = 16_384
MAX_PATCH_BASE64_CHARS = ((MAX_PATCH_BYTES + 2) // 3) * 4
P0_MUTABLE_PATHS = frozenset(
    {"app/auth/limiter.py", "tests/test_security_policy.py"}
)
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
    tree_hash_algorithm: str


class PromptPolicy(FrozenModel):
    template: str
    no_memory_context: str
    approved_memory_template: str

    @model_validator(mode="after")
    def placeholders_are_fixed(self) -> PromptPolicy:
        fields = {field for _, field, _, _ in Formatter().parse(self.template) if field}
        if fields != {"task", "memory_context"}:
            raise ValueError("prompt template may contain only task and memory_context placeholders")
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
        if self.product != "ReviewLatch":
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
        if not set(self.fixture.mutable_paths) <= set(self.fixture.tracked_paths) | allowed_new_paths:
            raise ValueError("mutable paths must be tracked or the required new test")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("task IDs must be unique")
        if any(task.repo_id != self.repo_id for task in self.tasks):
            raise ValueError("task repository IDs are server-owned")
        if any(not set(task.target_paths) <= set(self.fixture.tracked_paths) for task in self.tasks):
            raise ValueError("task targets must exist in the base fixture")
        if any(
            not set(task.expected_changed_paths) <= set(self.fixture.mutable_paths)
            for task in self.tasks
        ):
            raise ValueError("expected changes must remain inside the write allowlist")
        selected_scope = next(
            (scope for scope in self.memory.scope_options if scope.scope_id == self.memory.selected_scope_id),
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
        if any(endpoint.requires_demo_token != (endpoint.method == "POST") for endpoint in self.api):
            raise ValueError("every mutation requires the runtime demo token")
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
    exact_correction: BoundedText
    selected_hunk_id: Identifier
    selected_scope_id: ScopeId
    occurred_at: UtcDateTime


class HumanDecision(FrozenModel):
    decision_id: Identifier
    value: MemoryDecisionValue
    actor: Literal["human"] = "human"
    purpose: Literal["memory", "promotion"]
    bound_digest: Sha256
    occurred_at: UtcDateTime


class MemoryRevision(FrozenModel):
    memory_id: Identifier
    revision: int = Field(ge=1)
    state: MemoryState
    rule: BoundedText
    repo_id: Identifier
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
            != canonical_json_sha256(
                self.model_dump(mode="json", exclude={"state", "decision"})
            )
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
    output: str
    output_truncated: bool
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
        if len(self.output.encode()) > MAX_TEST_OUTPUT_BYTES:
            raise ValueError("test output exceeds the UTF-8 byte cap")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        )
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
        if self.state in {
            RunState.WAITING_FOR_PROMOTION,
            RunState.PROMOTING,
            RunState.COMPLETED,
        } and self.candidate is None:
            raise ValueError("promotion states require a persisted candidate")
        if self.state in {
            RunState.WAITING_FOR_PROMOTION,
            RunState.PROMOTING,
            RunState.COMPLETED,
        } and ProofType.COMPLETION_DENIED not in proof_types:
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
            or self.promotion_decision.bound_digest
            != self.candidate.candidate_patch_sha256
        ):
            raise ValueError("promoting runs require explicit human approval")
        if self.promotion_decision is not None and self.state not in {
            RunState.PROMOTING,
            RunState.COMPLETED,
            RunState.FAILED,
        }:
            raise ValueError("human promotion decisions belong only to promotion attempts")
        if (
            self.promotion_decision is not None
            and ProofType.PROMOTION_APPROVED not in proof_types
        ):
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
    framework: Literal["Google ADK"]
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
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"packet_sha256"})
        )
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
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        )
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
            or any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges)
            or any(value < 0 for value in self.omitted_counts.values())
            or self.truncated != any(value > 0 for value in self.omitted_counts.values())
        ):
            raise ValueError("graph nodes and edges must be sorted, unique, and resolvable")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"graph_hash"})
        )
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
            or self.negative_profile_id not in {
                item.agent_profile_id for item in self.catalog
            }
            or any(endpoint.method != "GET" for endpoint in self.api)
        ):
            raise ValueError("post-Phase-0 graph contract is frozen")
        return self
