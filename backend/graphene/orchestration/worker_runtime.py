from __future__ import annotations

import asyncio
import inspect
import os
import re
import secrets
import signal
import shutil
import stat
import subprocess
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

from pydantic import Field, ValidationError, model_serializer, model_validator

from ..artifact_envelope import ArtifactEnvelopeV2, DirectArtifactInputV2
from ..execution.adapter import (
    NORTH_STAR_CHECK_COMMAND,
    NORTH_STAR_FINAL_CHECK_COMMAND,
    NORTH_STAR_CHECK_PATHS,
    SANDBOX_CHECK_TEMPLATES,
    ExecutionError,
    run_fixture_tests,
)
from ..hashing import (
    EXECUTABLE_FILE_MODE,
    REGULAR_FILE_MODE,
    TREE_HASH_VERSION,
    TreeEntry,
    candidate_tree_sha256,
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_hex,
)
from ..core_models import (
    BoundedText,
    FrozenModel,
    Identifier,
    MAX_TEST_OUTPUT_BYTES,
    RepoPath,
    Sha256,
    TruthKind,
)
from .diagnostics import CHECK_DIAGNOSTIC_KIND, CheckDiagnostic, summarize_check_failure
from .evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceEventType,
    AttemptEvidenceInput,
    SQLiteAttemptEvidenceStore,
    TrustedCheckReceipt,
)
from .mission_models import (
    ArtifactEnvelopeReferenceV2,
    ArtifactInputReference,
    ArtifactVisibility,
    Attempt,
    AttemptResult,
    AttemptState,
    CommandTemplate,
    Dispatch,
    EvidenceReference,
    GenericEvidenceLink,
    MissionSnapshot,
    MissionStatus,
    PublishedArtifactReferenceV2,
    PublicationDraft,
    TaskKind,
    artifact_input_reference_key,
)
from .process_control import (
    ControlledProcessRunner,
    ModelDispatchBarrier,
    OwnedProcess,
    OwnedProcessRegistry,
    ProcessCancelled,
    ProcessControlError,
)
from .sandbox import DockerExecutor, SandboxResult, command_template_sha256
from .scripted import ScriptedError, fixture_policy_for
from .workspace_audit import (
    WorkspaceBaseline,
    _admin_files,
    _admin_digest,
    audit_workspace,
    capture_workspace_baseline,
)

# Evidence artifact kind that binds a sanitized provider receipt (model names,
# credential mode, byte and token counts; never prompts or outputs) to the
# attempt that produced it.
WORKER_PROVIDER_RECEIPT_KIND = "worker-provider-receipt"
WORKER_PROVIDER_INTERRUPTION_KIND = "worker-provider-interruption"

# The fixture policy caps a single check at 60 seconds; a template asking for
# more cannot be honoured exactly and is rejected rather than silently clamped.
HOST_SANDBOX_MAX_TIMEOUT_SECONDS = 60


class RuntimeErrorCode(StrEnum):
    ACCEPTANCE_CHECK_FAILED = "acceptance_check_failed"
    ADAPTER_REJECTED = "adapter_rejected"
    ARTIFACT_TAMPERED = "artifact_tampered"
    CANCELLED = "cancelled"
    INPUT_REJECTED = "input_rejected"
    # The provider answered, but not with a parseable WorkerIntent: a bounded
    # retry under a higher fence is the right response, unlike ADAPTER_REJECTED
    # (identity or framework problems), which stays terminal.
    MODEL_OUTPUT_REJECTED = "model_output_rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"
    POLICY_REJECTED = "policy_rejected"
    PROVIDER_INTERRUPTED = "provider_interrupted"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    STALE_LEASE = "stale_lease"


class CompletionOutcome(StrEnum):
    COMPLETED = "completed"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"
    OUTCOME_UNKNOWN = "outcome_unknown"


class RuntimeFailure(RuntimeError):
    def __init__(
        self,
        code: RuntimeErrorCode,
        *,
        outcome_unknown: bool = False,
        terminal: bool = False,
    ) -> None:
        self.code = code
        self.outcome_unknown = outcome_unknown
        # An otherwise-retryable code that has already been seen with the exact
        # same failure signature. Retrying it again is a blind third attempt.
        self.terminal = terminal
        super().__init__(code.value)


class WorkerCapabilities(FrozenModel):
    worker_id: Identifier
    driver: Literal["deterministic", "gemini_live", "adk_fake"]
    task_kinds: tuple[TaskKind, ...] = Field(min_length=1, max_length=3)
    model_id: Identifier | None = None
    max_parallel_attempts: int = Field(default=1, ge=1, le=64)
    network_access: Literal[False] = False

    @model_validator(mode="after")
    def kinds_are_canonical(self) -> WorkerCapabilities:
        values = tuple(item.value for item in self.task_kinds)
        if values != tuple(sorted(set(values))):
            raise ValueError("worker task capabilities must be sorted and unique")
        return self


class PriorFailure(FrozenModel):
    """What the previous attempt at this task learned, in a form safe to send onward.

    A retry that re-sends a byte-identical prompt is a coin flip, not recovery.
    This carries exactly what the next attempt needs and nothing that could leak:
    the prior attempt's identity and fence, its result code, the names of the
    checks that failed, the digest of its trusted evidence, and a redacted,
    bounded summary. The repair scope is deliberately absent — it is unchanged,
    and it is already on the assignment as ``output_paths``.
    """

    schema_version: Literal[1] = 1
    attempt_id: Identifier
    attempt_number: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    result_code: Identifier
    failure_class: Identifier
    failed_check_names: tuple[BoundedText, ...] = Field(default=(), max_length=8)
    summary: BoundedText
    receipt_sha256: Sha256
    failure_signature: BoundedText


class RuntimeAssignment(FrozenModel):
    task_id: Identifier
    title: BoundedText
    contract: BoundedText
    read_paths: tuple[RepoPath, ...] = Field(min_length=1, max_length=256)
    output_name: Identifier
    output_kind: Identifier
    output_paths: tuple[RepoPath, ...] = Field(default=(), max_length=64)
    command_template: CommandTemplate
    prior_failure: PriorFailure | None = None

    @model_validator(mode="after")
    def assignment_is_canonical(self) -> RuntimeAssignment:
        for items in (self.read_paths, self.output_paths):
            if items != tuple(sorted(set(items))):
                raise ValueError("runtime assignment paths must be sorted and unique")
        return self


class CheckOutcome(FrozenModel):
    template_id: Identifier
    template_sha256: Sha256
    exit_code: int
    timed_out: bool
    output_sha256: Sha256
    output_truncated: bool
    cleanup_complete: bool
    truth_kind: Literal["simulated_fixture"] | None = None
    truth_label: Identifier | None = None
    # Populated by the runner only when the check did not pass. The raw output is
    # still never persisted; this is the redacted, bounded structure derived from
    # it, and it is the only thing a retry is allowed to learn.
    diagnostic: CheckDiagnostic | None = None

    @model_validator(mode="after")
    def simulation_truth_is_explicit(self) -> CheckOutcome:
        if (self.truth_kind is None) != (self.truth_label is None):
            raise ValueError("check simulation truth kind and label must be paired")
        return self


PROVIDER_CALL_TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
_PROVIDER_CALL_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_provider_call_timestamp(moment: datetime) -> str:
    """Render an aware instant as RFC 3339 UTC with millisecond precision."""

    if moment.tzinfo is None:
        raise ValueError("provider call timestamps must be timezone-aware")
    utc = moment.astimezone(UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"


def parse_provider_call_timestamp(value: str) -> datetime:
    """Parse a receipt call timestamp; anything outside the receipt format fails."""

    if re.fullmatch(PROVIDER_CALL_TIMESTAMP_PATTERN, value) is None:
        raise ValueError("provider call timestamp is not RFC 3339 UTC milliseconds")
    return datetime.strptime(value, _PROVIDER_CALL_TIMESTAMP_FORMAT).replace(tzinfo=UTC)


class WorkerProviderReceipt(FrozenModel):
    driver: Literal["adk_fake", "gemini_live"]
    framework: Literal["google_adk"] = "google_adk"
    framework_version: Literal["2.5.0"] = "2.5.0"
    client: Literal["google_genai"] = "google_genai"
    client_version: str = Field(
        min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$"
    )
    requested_model: Identifier
    returned_model: Identifier
    credential_mode: Literal["not_applicable", "gemini_api", "vertex_ai"]
    model_call_count: Literal[1] = 1
    telemetry_content_capture: Literal["NO_CONTENT"] = "NO_CONTENT"
    input_bytes: int = Field(ge=1, le=1_048_576)
    output_bytes: int = Field(ge=1, le=1_048_576)
    latency_ms: int = Field(ge=0, le=300_000)
    # Wall-clock window of the single provider call, stamped by the runtime
    # immediately around the model run. This, not the attempt lifetime, is the
    # basis for a measured provider-call overlap claim between workers.
    call_started_at: str = Field(pattern=PROVIDER_CALL_TIMESTAMP_PATTERN)
    call_ended_at: str = Field(pattern=PROVIDER_CALL_TIMESTAMP_PATTERN)
    usage_source: Literal["provider_reported", "unavailable"]
    # The provider's own view of the same call, read from the response rather
    # than stamped by the runtime: the response id, the server-side request
    # arrival time (`create_time`), and the HTTP `Date` header of the reply
    # (whole seconds). Identifiers and instants only, never content. Absent
    # when the provider did not report them; the fake driver never has them.
    provider_response_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:/-]+$"
    )
    provider_create_time: str | None = Field(
        default=None, pattern=PROVIDER_CALL_TIMESTAMP_PATTERN
    )
    provider_response_date: str | None = Field(
        default=None, pattern=PROVIDER_CALL_TIMESTAMP_PATTERN
    )
    prompt_tokens: int | None = Field(default=None, ge=0)
    candidate_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    tool_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def usage_is_explicit(self) -> WorkerProviderReceipt:
        counts = (
            self.prompt_tokens,
            self.candidate_tokens,
            self.thought_tokens,
            self.tool_tokens,
            self.cached_tokens,
            self.total_tokens,
        )
        if self.usage_source == "unavailable" and any(
            item is not None for item in counts
        ):
            raise ValueError("unavailable worker usage cannot contain token counts")
        if self.usage_source == "provider_reported" and all(
            item is None for item in counts
        ):
            raise ValueError("provider-reported worker usage requires a token count")
        return self

    @model_validator(mode="after")
    def call_window_is_ordered(self) -> WorkerProviderReceipt:
        started = parse_provider_call_timestamp(self.call_started_at)
        ended = parse_provider_call_timestamp(self.call_ended_at)
        if started > ended:
            raise ValueError("provider call cannot end before it starts")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent_provider_stamps(self, handler: Any) -> Any:
        # Receipts minted before provider stamps existed must keep hashing to
        # the same canonical bytes, so absent stamps are omitted, not nulled.
        value = handler(self)
        if isinstance(value, dict):
            for key in (
                "provider_response_id",
                "provider_create_time",
                "provider_response_date",
            ):
                if value.get(key) is None:
                    value.pop(key, None)
        return value

    def provider_reported_window(self) -> tuple[datetime, datetime] | None:
        """The provider's own [request arrival, reply sent] window, if reported.

        The `Date` header is truncated to whole seconds, so the end may sit
        up to one second before the true reply instant and even before
        `create_time` for a sub-second call; consumers clamp, which makes any
        overlap measured on this basis an underestimate, never an overclaim.
        """

        if self.provider_create_time is None or self.provider_response_date is None:
            return None
        return (
            parse_provider_call_timestamp(self.provider_create_time),
            parse_provider_call_timestamp(self.provider_response_date),
        )


class WorkerProviderInterruption(FrozenModel):
    """Sanitized proof of a transport-entered call without a provider receipt."""

    schema_version: Literal[1, 2] = 1
    driver: Literal["gemini_live"] = "gemini_live"
    requested_model: Identifier
    mission_id: Identifier
    task_id: Identifier
    attempt_id: Identifier
    lease_id: Identifier
    fencing_token: int = Field(ge=1)
    request_sha256: Sha256
    input_bytes: int | None = Field(default=None, ge=1, le=2_097_152)
    provider_dispatch_state: Literal[
        "transport_acknowledged", "unconfirmed"
    ] = "transport_acknowledged"
    sdk_invocation_id: Identifier | None = None
    dispatched_at: str | None = Field(
        default=None, pattern=PROVIDER_CALL_TIMESTAMP_PATTERN
    )
    pid: int = Field(gt=1)
    pgid: int = Field(gt=1)
    process_started_at: BoundedText
    process_identity_version: Literal[1, 2] = 2
    process_birth_token: BoundedText | None = None
    executable: BoundedText
    exit_code: int
    signal_name: Identifier | None = None
    repository_effect: Literal["known_absent"] = "known_absent"
    provider_outcome: Literal["unknown"] = "unknown"
    billing_outcome: Literal["unknown"] = "unknown"
    stderr_sha256: Sha256
    stderr_truncated: bool

    @model_validator(mode="after")
    def process_group_is_owned(self) -> WorkerProviderInterruption:
        if self.pid != self.pgid:
            raise ValueError("interrupted model child must lead its process group")
        acknowledged = self.provider_dispatch_state == "transport_acknowledged"
        if acknowledged != (
            self.sdk_invocation_id is not None and self.dispatched_at is not None
        ):
            raise ValueError("provider dispatch proof does not match its state")
        if (self.process_identity_version == 1) != (
            self.process_birth_token is None
        ):
            raise ValueError("process birth proof does not match its version")
        if (self.schema_version == 1) != (self.input_bytes is not None):
            raise ValueError("interruption input size does not match its version")
        return self


class WorkerCompletion(FrozenModel):
    outcome: CompletionOutcome
    result_code: Identifier
    session_id: Identifier
    invocation_id: Identifier
    provider: WorkerProviderReceipt | None = None
    provider_interruption: WorkerProviderInterruption | None = None

    @model_validator(mode="after")
    def code_matches_outcome(self) -> WorkerCompletion:
        allowed = {
            CompletionOutcome.COMPLETED: {"passed"},
            CompletionOutcome.RETRYABLE_FAILURE: {
                RuntimeErrorCode.ACCEPTANCE_CHECK_FAILED.value,
                RuntimeErrorCode.MODEL_OUTPUT_REJECTED.value,
                RuntimeErrorCode.PROVIDER_RATE_LIMITED.value,
                RuntimeErrorCode.PROVIDER_INTERRUPTED.value,
                RuntimeErrorCode.PROVIDER_TIMEOUT.value,
                RuntimeErrorCode.PROVIDER_UNAVAILABLE.value,
                RuntimeErrorCode.RUNTIME_UNAVAILABLE.value,
                RuntimeErrorCode.SANDBOX_UNAVAILABLE.value,
            },
            CompletionOutcome.TERMINAL_FAILURE: {
                RuntimeErrorCode.ADAPTER_REJECTED.value,
                RuntimeErrorCode.ARTIFACT_TAMPERED.value,
                RuntimeErrorCode.CANCELLED.value,
                RuntimeErrorCode.INPUT_REJECTED.value,
                RuntimeErrorCode.POLICY_REJECTED.value,
                RuntimeErrorCode.STALE_LEASE.value,
            },
            CompletionOutcome.OUTCOME_UNKNOWN: {RuntimeErrorCode.OUTCOME_UNKNOWN.value},
        }
        if self.result_code not in allowed[self.outcome]:
            raise ValueError("worker completion is outside the failure taxonomy")
        if (
            self.result_code == RuntimeErrorCode.PROVIDER_INTERRUPTED.value
            and self.provider_interruption is None
        ) or (
            self.outcome == CompletionOutcome.COMPLETED
            and self.provider_interruption is not None
        ):
            raise ValueError("provider interruption proof does not match completion")
        return self


class RuntimeReceipt(FrozenModel):
    schema_version: Literal[1] = 1
    operation_id: Identifier
    worker_id: Identifier
    attempt_id: Identifier
    lease_id: Identifier
    fencing_token: int = Field(ge=1)
    workspace_id: Identifier
    completion: WorkerCompletion
    operation_ids: tuple[Identifier, ...]
    accepted_input_sha256: tuple[Sha256, ...]
    result: AttemptResult
    receipt_sha256: Sha256

    @model_validator(mode="after")
    def receipt_is_bound(self) -> RuntimeReceipt:
        if self.operation_ids != tuple(sorted(set(self.operation_ids))):
            raise ValueError("runtime operations must be sorted and unique")
        if (
            self.completion.result_code != self.result.result_code
            or self.completion.session_id != self.result.session_id
            or self.completion.invocation_id != self.result.invocation_id
        ):
            raise ValueError("runtime completion and attempt result disagree")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        )
        if self.receipt_sha256 != expected:
            raise ValueError("runtime receipt digest does not match")
        return self

    @classmethod
    def create(cls, **values: object) -> RuntimeReceipt:
        canonical = cls.model_construct(
            schema_version=1, **values, receipt_sha256="0" * 64
        ).model_dump(mode="json", exclude={"receipt_sha256"})
        return cls.model_validate(
            {**canonical, "receipt_sha256": canonical_json_sha256(canonical)}
        )


class WorkerRun(FrozenModel):
    result: AttemptResult
    receipt: RuntimeReceipt
    replayed: bool = False


class WorkerAdapter(Protocol):
    @property
    def capabilities(self) -> WorkerCapabilities: ...

    async def execute(
        self, context: WorkerContext, assignment: RuntimeAssignment
    ) -> WorkerCompletion: ...


class AcceptedArtifactResolver(Protocol):
    def __call__(
        self, dispatch: Dispatch, reference: ArtifactInputReference
    ) -> bytes: ...


class CheckRunner(Protocol):
    def __call__(
        self, workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome | Awaitable[CheckOutcome]: ...


FenceCallback = Callable[[Dispatch, str], object | Awaitable[object]]
HeartbeatCallback = Callable[[Dispatch], object | Awaitable[object]]
AssignmentResolver = Callable[[Dispatch], RuntimeAssignment]


async def _maybe_await(value: object | Awaitable[object]) -> object:
    return await value if inspect.isawaitable(value) else value


def stable_operation_id(dispatch: Dispatch, label: str) -> str:
    return (
        "op_"
        + canonical_json_sha256(
            {
                "attempt_id": dispatch.attempt_id,
                "fencing_token": dispatch.fencing_token,
                "label": label,
                "lease_id": dispatch.lease_id,
            }
        )[:32]
    )


class WorkerRegistry:
    def __init__(self, adapters: tuple[WorkerAdapter, ...] = ()) -> None:
        self._adapters: dict[str, WorkerAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: WorkerAdapter) -> None:
        worker_id = adapter.capabilities.worker_id
        if worker_id in self._adapters:
            raise ValueError("worker ID is already registered")
        self._adapters[worker_id] = adapter

    def resolve(self, dispatch: Dispatch) -> WorkerAdapter:
        adapter = self._adapters.get(dispatch.worker_id)
        if adapter is None or dispatch.task_kind not in adapter.capabilities.task_kinds:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        return adapter

    def capabilities(self) -> tuple[WorkerCapabilities, ...]:
        return tuple(self._adapters[key].capabilities for key in sorted(self._adapters))


def _check_diagnostic(
    output: str,
    *,
    exit_code: int,
    timed_out: bool,
    output_truncated: bool,
    cleanup_complete: bool,
    output_sha256: str,
    output_byte_count: int,
) -> CheckDiagnostic | None:
    """Summarise a failing check; a passing check has nothing to teach a retry."""

    if exit_code == 0 and not timed_out and not output_truncated and cleanup_complete:
        return None
    return summarize_check_failure(
        output,
        exit_code=exit_code,
        timed_out=timed_out,
        output_truncated=output_truncated,
        cleanup_complete=cleanup_complete,
        output_sha256=output_sha256,
        output_byte_count=output_byte_count,
    )


class DockerCheckRunner:
    def __init__(self, executor: DockerExecutor) -> None:
        self.executor = executor

    async def __call__(
        self, workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        try:
            scopes = (*assignment.read_paths, *assignment.output_paths)
            if tuple(assignment.command_template.argv) in {
                NORTH_STAR_CHECK_COMMAND,
                NORTH_STAR_FINAL_CHECK_COMMAND,
            }:
                scopes += NORTH_STAR_CHECK_PATHS
            result: SandboxResult = await asyncio.to_thread(
                self.executor.execute,
                source=workspace,
                scopes=tuple(sorted(set(scopes))),
                exclusions=(),
                template=assignment.command_template,
                owner_id=owner_id,
            )
        except Exception as error:
            raise RuntimeFailure(RuntimeErrorCode.SANDBOX_UNAVAILABLE) from error
        return CheckOutcome(
            template_id=result.template_id,
            template_sha256=result.template_sha256,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            output_sha256=sha256_hex(result.output),
            output_truncated=result.output_truncated,
            cleanup_complete=result.cleanup_complete,
            diagnostic=_check_diagnostic(
                result.output.decode("utf-8", "replace"),
                exit_code=result.exit_code,
                timed_out=result.timed_out,
                output_truncated=result.output_truncated,
                cleanup_complete=result.cleanup_complete,
                output_sha256=sha256_hex(result.output),
                output_byte_count=len(result.output),
            ),
        )


class HostSandboxCheckRunner:
    """Run one reviewed policy check on the host under sandbox-exec.

    This is the explicit macOS alternative to :class:`DockerCheckRunner`. It
    reuses the scripted path's trusted machinery: the same frozen command, the
    same fixture materialization, and a :class:`ControlledProcessRunner` that
    registers the check subprocess in the :class:`OwnedProcessRegistry` for
    the duration of the check. That registration is what lets cancellation
    and the failure laboratory act on a strongly identified Graphene-owned
    process group instead of guessing by name. Anything else fails closed.
    """

    def __init__(
        self,
        registry: OwnedProcessRegistry,
        *,
        dispatch_for: Callable[[str], Dispatch],
        status: Callable[[], MissionStatus],
        heartbeat: Callable[[Dispatch], object] | None = None,
    ) -> None:
        self.registry = registry
        self.dispatch_for = dispatch_for
        self.status = status
        self.heartbeat = heartbeat

    async def __call__(
        self, workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        template = assignment.command_template
        if (
            (template.template_id, tuple(template.argv)) not in SANDBOX_CHECK_TEMPLATES
            or template.cwd is not None
            or not 0 < template.timeout_seconds <= HOST_SANDBOX_MAX_TIMEOUT_SECONDS
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            raise RuntimeFailure(RuntimeErrorCode.SANDBOX_UNAVAILABLE)
        try:
            dispatch = self.dispatch_for(owner_id)
        except KeyError as error:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
        if not isinstance(dispatch, Dispatch) or dispatch.attempt_id != owner_id:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        try:
            policy = fixture_policy_for(
                workspace,
                test_timeout_seconds=template.timeout_seconds,
                fixed_test_command=tuple(template.argv),
            )
        except (ScriptedError, ValidationError) as error:
            # An unrepresentable workspace (for example a path longer than the
            # fixture policy allows) is a deterministic policy condition.
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
        heartbeat = self.heartbeat
        process_runner = ControlledProcessRunner(
            self.registry,
            dispatch,
            self.status,
            heartbeat=None if heartbeat is None else (lambda: heartbeat(dispatch)),
            max_output_bytes=min(
                policy.max_test_output_bytes, MAX_TEST_OUTPUT_BYTES
            ),
        )
        try:
            run = await asyncio.to_thread(
                run_fixture_tests,
                workspace,
                policy,
                process_runner=process_runner,
            )
        except ProcessCancelled as error:
            raise RuntimeFailure(RuntimeErrorCode.CANCELLED) from error
        except (ExecutionError, ProcessControlError) as error:
            raise RuntimeFailure(RuntimeErrorCode.SANDBOX_UNAVAILABLE) from error
        cleanup_complete = not self.registry.has_record(
            dispatch.attempt_id, model=False
        )
        encoded = run.output.encode("utf-8")
        return CheckOutcome(
            template_id=template.template_id,
            template_sha256=command_template_sha256(template),
            exit_code=run.exit_code,
            timed_out=run.timed_out,
            output_sha256=sha256_hex(encoded),
            output_truncated=run.output_truncated,
            # Measured, not asserted: the controlled runner removes the owned
            # record only after the process group is confirmed gone.
            cleanup_complete=cleanup_complete,
            # run.output has already been through the adapter's sanitiser; the
            # summariser is idempotent with respect to it and redacts again.
            diagnostic=_check_diagnostic(
                run.output,
                exit_code=run.exit_code,
                timed_out=run.timed_out,
                output_truncated=run.output_truncated,
                cleanup_complete=cleanup_complete,
                output_sha256=sha256_hex(encoded),
                output_byte_count=len(encoded),
            ),
        )


class _OutcomeUnknown(RuntimeFailure):
    def __init__(self) -> None:
        super().__init__(RuntimeErrorCode.OUTCOME_UNKNOWN, outcome_unknown=True)


class _ModelEffectUncommitted(_OutcomeUnknown):
    """A model returned, but its post-effect journal/fence did not commit."""


class WorkerContext:
    def __init__(
        self,
        runtime: WorkerRuntime,
        dispatch: Dispatch,
        assignment: RuntimeAssignment,
        workspace: Path,
    ) -> None:
        self.runtime = runtime
        self.dispatch = dispatch
        self.assignment = assignment
        self.workspace = workspace
        self.operation_ids: set[str] = set()
        # Which stages this attempt actually got through. A cancellation can
        # land at any await, and "cancelled" on its own cannot say whether the
        # acceptance check had already passed when it did.
        self.completed_stages: list[str] = []
        self._baseline: WorkspaceBaseline | None = None
        self._admin_roots: tuple[tuple[str, Path], ...] = ()
        self._workspace_identity: tuple[int, int] | None = None

    def _has_exact_model_ownership(self) -> bool:
        try:
            return (
                OwnedProcessRegistry(self.runtime.runtime.parent).owned_process(
                    self.dispatch, require_live=False, model=True
                )
                is not None
            )
        except ProcessControlError:
            # A present but unreadable exact proof must also fail closed.
            return True

    def _identity(self) -> tuple[int, int]:
        try:
            metadata = self.workspace.lstat()
            resolved = self.workspace.resolve(strict=True)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or resolved != self.workspace
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        return metadata.st_dev, metadata.st_ino

    def capture_baseline(self, base_sha: str) -> WorkspaceBaseline:
        identity = self._identity()
        try:
            baseline = capture_workspace_baseline(self.workspace, base_sha)
        except Exception as error:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
        if self._identity() != identity:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        admin_roots = _admin_files(self.workspace)
        if _admin_digest(self.workspace, admin_roots) != baseline.git_admin_sha256:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        self._baseline = baseline
        self._admin_roots = admin_roots
        self._workspace_identity = identity
        return baseline

    def _verify_workspace(self, *, after: bool) -> None:
        if self._baseline is None:
            return
        try:
            if (
                self._identity() != self._workspace_identity
                or _admin_digest(self.workspace, self._admin_roots)
                != self._baseline.git_admin_sha256
            ):
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        except Exception as error:
            if after:
                raise _OutcomeUnknown() from error
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error

    async def _effect(self, label: str, action: Callable[[], object]) -> object:
        operation_id = stable_operation_id(self.dispatch, label)
        self.operation_ids.add(operation_id)
        await self.runtime._fence(self.dispatch, operation_id, after=False)
        guard_workspace = self._baseline is not None and (
            label
            in {
                "check",
                "cleanup",
                "intent-to-add",
                "model",
                "reset-index",
                "stage",
                "stage-accepted",
            }
            or label.startswith(("apply:", "store-", "write:"))
        )
        if guard_workspace:
            self._verify_workspace(after=False)
        non_replayable = label in {"check", "model"}
        if non_replayable:
            self.runtime._begin_nonreplayable(self.dispatch, operation_id, label)
        action_error: BaseException | None = None
        try:
            value = action()
            if inspect.isawaitable(value):
                value = await value
        except BaseException as error:
            action_error = error
            value = None
        if guard_workspace and label == "cleanup":
            try:
                self.runtime._validate_directory(self.runtime.workspaces)
                self.workspace.lstat()
            except FileNotFoundError:
                pass
            except Exception as error:
                raise _OutcomeUnknown() from error
            else:
                raise _OutcomeUnknown()
        elif guard_workspace:
            try:
                self._verify_workspace(after=True)
            except _OutcomeUnknown as error:
                if label == "model" and self._has_exact_model_ownership():
                    raise _ModelEffectUncommitted() from error
                raise
        if non_replayable:
            try:
                self.runtime._complete_nonreplayable(self.dispatch, operation_id, label)
            except Exception as error:
                if label == "model" and self._has_exact_model_ownership():
                    raise _ModelEffectUncommitted() from error
                raise _OutcomeUnknown() from error
        try:
            await self.runtime._fence(self.dispatch, operation_id, after=True)
        except Exception as error:
            if label == "model" and self._has_exact_model_ownership():
                raise _ModelEffectUncommitted() from error
            raise _OutcomeUnknown() from error
        if action_error is not None:
            if (
                label == "model"
                and isinstance(action_error, Exception)
                and self._has_exact_model_ownership()
            ):
                raise _ModelEffectUncommitted() from action_error
            raise action_error
        self.completed_stages.append(label)
        return value

    def _target(self, path: str, allowed: tuple[str, ...]) -> Path:
        relative = PurePosixPath(path)
        if path not in allowed or relative.is_absolute() or ".." in relative.parts:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        target = self.workspace.joinpath(*relative.parts)
        try:
            target.resolve(strict=False).relative_to(self.workspace)
        except (OSError, ValueError) as error:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
        return target

    async def read_text(self, path: str) -> str:
        target = self._target(
            path,
            tuple(
                sorted(set((*self.assignment.read_paths, *self.dispatch.write_paths)))
            ),
        )

        def read() -> str:
            metadata = target.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise RuntimeFailure(RuntimeErrorCode.INPUT_REJECTED)
            if metadata.st_size > 65_536:
                raise RuntimeFailure(RuntimeErrorCode.INPUT_REJECTED)
            return target.read_text(encoding="utf-8")

        return str(await self._effect(f"read:{path}", read))

    async def read_supplied_inputs(self) -> tuple[tuple[str, str], ...]:
        """Open only private operator-input references bound to this dispatch."""

        values: list[tuple[str, str]] = []
        total = 0
        for reference in self.dispatch.input_publications:
            if reference.kind != "operator-input":
                continue

            def resolve(reference: ArtifactInputReference = reference) -> bytes:
                content = self.runtime.accepted_artifact(self.dispatch, reference)
                if (
                    not isinstance(content, bytes)
                    or sha256_hex(content) != reference.sha256
                ):
                    raise RuntimeFailure(RuntimeErrorCode.ARTIFACT_TAMPERED)
                return content

            content = bytes(
                await self._effect(f"supplied-input:{reference.id}", resolve)
            )
            total += len(content)
            if len(content) > 65_536 or total > 131_072 or b"\0" in content:
                raise RuntimeFailure(RuntimeErrorCode.INPUT_REJECTED)
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise RuntimeFailure(RuntimeErrorCode.INPUT_REJECTED) from error
            values.append((reference.id, text))
        return tuple(values)

    async def write_text(self, path: str, text: str) -> None:
        content = text.encode("utf-8") if isinstance(text, str) else b""
        if not isinstance(text, str) or len(content) > 262_144:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        self._target(path, self.dispatch.write_paths)
        relative = PurePosixPath(path)

        def write() -> None:
            descriptors: list[int] = []
            temporary = (
                ".graphene-write-"
                + stable_operation_id(self.dispatch, f"write:{path}")[-16:]
            )
            try:
                descriptor = os.open(
                    self.workspace,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                descriptors.append(descriptor)
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != self._workspace_identity:
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                for part in relative.parts[:-1]:
                    try:
                        os.mkdir(part, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    child = os.open(
                        part,
                        os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=descriptor,
                    )
                    if not stat.S_ISDIR(os.fstat(child).st_mode):
                        os.close(child)
                        raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                    descriptors.append(child)
                    descriptor = child
                mode = 0o644
                try:
                    target = os.stat(
                        relative.name, dir_fd=descriptor, follow_symlinks=False
                    )
                except FileNotFoundError:
                    pass
                else:
                    if not stat.S_ISREG(target.st_mode):
                        raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                    mode = 0o755 if target.st_mode & 0o111 else 0o644
                output = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    mode,
                    dir_fd=descriptor,
                )
                try:
                    with os.fdopen(output, "wb") as stream:
                        output = -1
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(
                        temporary,
                        relative.name,
                        src_dir_fd=descriptor,
                        dst_dir_fd=descriptor,
                    )
                finally:
                    if output >= 0:
                        os.close(output)
                    try:
                        os.unlink(temporary, dir_fd=descriptor)
                    except FileNotFoundError:
                        pass
            except OSError as error:
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
            finally:
                for descriptor in reversed(descriptors):
                    os.close(descriptor)

        await self._effect(f"write:{path}", write)

    async def apply_file_mutation(
        self,
        index: int,
        operation: Literal["create", "update", "delete", "rename", "chmod"],
        path: str,
        *,
        text: str | None = None,
        new_path: str | None = None,
        mode: Literal["100644", "100755"] | None = None,
    ) -> None:
        shape = (text is not None, new_path is not None, mode is not None)
        expected = {
            "create": (True, False, True),
            "update": (True, False, False),
            "delete": (False, False, False),
            "rename": (False, True, False),
            "chmod": (False, False, True),
        }
        content = text.encode("utf-8") if isinstance(text, str) else b""
        if (
            type(index) is not int
            or not 0 <= index < 128
            or operation not in expected
            or not isinstance(path, str)
            or (text is not None and not isinstance(text, str))
            or (new_path is not None and not isinstance(new_path, str))
            or (mode is not None and mode not in {"100644", "100755"})
            or shape != expected[operation]
            or len(content) > 262_144
            or (operation == "rename" and new_path == path)
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        self._target(path, self.dispatch.write_paths)
        if new_path is not None:
            self._target(new_path, self.dispatch.write_paths)
        relative = PurePosixPath(path)
        destination = None if new_path is None else PurePosixPath(new_path)
        file_mode = {"100644": 0o644, "100755": 0o755}.get(mode)

        def mutate() -> None:
            descriptors: list[int] = []

            def parent(target: PurePosixPath, *, create: bool) -> int:
                descriptor = os.open(
                    self.workspace,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                descriptors.append(descriptor)
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != self._workspace_identity:
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                for part in target.parts[:-1]:
                    if create:
                        try:
                            os.mkdir(part, 0o700, dir_fd=descriptor)
                        except FileExistsError:
                            pass
                    child = os.open(
                        part,
                        os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=descriptor,
                    )
                    if not stat.S_ISDIR(os.fstat(child).st_mode):
                        os.close(child)
                        raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                    descriptors.append(child)
                    descriptor = child
                return descriptor

            def regular_file(descriptor: int, name: str) -> int:
                opened = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
                if not stat.S_ISREG(os.fstat(opened).st_mode):
                    os.close(opened)
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                return opened

            try:
                source_parent = parent(relative, create=operation == "create")
                if operation == "create":
                    assert file_mode is not None
                    output = os.open(
                        relative.name,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        file_mode,
                        dir_fd=source_parent,
                    )
                    try:
                        os.fchmod(output, file_mode)
                        with os.fdopen(output, "wb") as stream:
                            output = -1
                            stream.write(content)
                            stream.flush()
                            os.fsync(stream.fileno())
                    finally:
                        if output >= 0:
                            os.close(output)
                elif operation == "update":
                    output = os.open(
                        relative.name,
                        os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=source_parent,
                    )
                    try:
                        if not stat.S_ISREG(os.fstat(output).st_mode):
                            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                        os.ftruncate(output, 0)
                        with os.fdopen(output, "wb") as stream:
                            output = -1
                            stream.write(content)
                            stream.flush()
                            os.fsync(stream.fileno())
                    finally:
                        if output >= 0:
                            os.close(output)
                elif operation == "delete":
                    opened = regular_file(source_parent, relative.name)
                    try:
                        os.unlink(relative.name, dir_fd=source_parent)
                    finally:
                        os.close(opened)
                elif operation == "rename":
                    assert destination is not None
                    source = regular_file(source_parent, relative.name)
                    destination_parent = parent(destination, create=True)
                    try:
                        try:
                            os.stat(
                                destination.name,
                                dir_fd=destination_parent,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            pass
                        else:
                            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                        os.link(
                            relative.name,
                            destination.name,
                            src_dir_fd=source_parent,
                            dst_dir_fd=destination_parent,
                            follow_symlinks=False,
                        )
                        os.unlink(relative.name, dir_fd=source_parent)
                    finally:
                        os.close(source)
                else:
                    assert file_mode is not None
                    opened = regular_file(source_parent, relative.name)
                    try:
                        os.fchmod(opened, file_mode)
                    finally:
                        os.close(opened)
            except OSError as error:
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
            finally:
                for descriptor in reversed(descriptors):
                    os.close(descriptor)

        await self._effect(f"mutation:{index}:{operation}", mutate)

    async def heartbeat(self) -> None:
        await _maybe_await(self.runtime.heartbeat(self.dispatch))


class WorkerRuntime:
    """Lease-fenced execution in one private clone per attempt."""

    def __init__(
        self,
        *,
        repository: Path,
        base_sha: str,
        runtime: Path,
        evidence: SQLiteAttemptEvidenceStore,
        registry: WorkerRegistry,
        assignment: AssignmentResolver,
        accepted_artifact: AcceptedArtifactResolver,
        check_runner: CheckRunner,
        policy_sha256: str,
        fence: FenceCallback,
        heartbeat: HeartbeatCallback,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        try:
            repository_metadata = repository.lstat()
            runtime_metadata = runtime.lstat()
            self.repository = repository.resolve(strict=True)
            self.runtime = runtime.resolve(strict=True)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if stat.S_ISLNK(repository_metadata.st_mode) or stat.S_ISLNK(
            runtime_metadata.st_mode
        ):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        self.base_sha = base_sha
        self.evidence = evidence
        self.registry = registry
        self.assignment = assignment
        self.accepted_artifact = accepted_artifact
        self.check_runner = check_runner
        self.policy_sha256 = policy_sha256
        self.fence = fence
        self.heartbeat = heartbeat
        self.clock = clock
        self.workspaces = self.runtime / "worker-workspaces"
        self.receipts = self.runtime / "worker-receipts"
        self.operation_journal = self.runtime / "operation-journal"
        self._directory_identities: dict[Path, tuple[int, int]] = {}
        self._initialize_directories()
        self._attempt_locks: dict[str, asyncio.Lock] = {}
        self._cancellation_safe_attempts: set[str] = set()
        self._active: dict[str, Dispatch] = {}
        # Kept only so a cancelled attempt can still say which stages it
        # completed; discarded the moment the attempt ends.
        self._contexts: dict[str, WorkerContext] = {}
        # The stage a cancelled attempt reached, held until the runner — which
        # is what decides between `cancelled` and `outcome_unknown` — takes it.
        self._cancelled_stages: dict[str, str] = {}

    def cancelled_stage(self, attempt_id: str) -> str | None:
        """Take the stage a cancelled attempt reached, or None if it recorded none."""

        return self._cancelled_stages.pop(attempt_id, None)

    def cancellation_safe(self, dispatch: Dispatch) -> bool:
        """True only while cancellation cannot orphan a local thread/subprocess."""

        return dispatch.attempt_id in self._cancellation_safe_attempts

    def dispatch_for(self, attempt_id: str) -> Dispatch:
        """Return the dispatch currently executing ``attempt_id`` or raise KeyError."""

        return self._active[attempt_id]

    def _initialize_directories(self) -> None:
        root = -1
        try:
            root = os.open(
                self.runtime,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            opened_root = os.fstat(root)
            visible_root = self.runtime.lstat()
            if (
                not stat.S_ISDIR(opened_root.st_mode)
                or stat.S_ISLNK(visible_root.st_mode)
                or (opened_root.st_dev, opened_root.st_ino)
                != (visible_root.st_dev, visible_root.st_ino)
            ):
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
            for directory in (self.workspaces, self.receipts, self.operation_journal):
                try:
                    os.mkdir(directory.name, 0o700, dir_fd=root)
                except FileExistsError:
                    pass
                child = os.open(
                    directory.name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root,
                )
                try:
                    opened = os.fstat(child)
                    visible = directory.lstat()
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or stat.S_ISLNK(visible.st_mode)
                        or (opened.st_dev, opened.st_ino)
                        != (visible.st_dev, visible.st_ino)
                    ):
                        raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
                    os.fchmod(child, 0o700)
                    self._directory_identities[directory] = (
                        opened.st_dev,
                        opened.st_ino,
                    )
                finally:
                    os.close(child)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        finally:
            if root >= 0:
                os.close(root)

    def _validate_directory(self, directory: Path) -> None:
        try:
            metadata = directory.lstat()
            resolved = directory.resolve(strict=True)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino)
            != self._directory_identities[directory]
            or resolved.parent != self.runtime
        ):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)

    def _operation_path(self, operation_id: str) -> Path:
        self._validate_directory(self.operation_journal)
        return self.operation_journal / (sha256_hex(operation_id.encode()) + ".json")

    def _operation_record(
        self, dispatch: Dispatch, operation_id: str, label: str, state: str
    ) -> bytes:
        return canonical_json_bytes(
            {
                "attempt_id": dispatch.attempt_id,
                "fencing_token": dispatch.fencing_token,
                "label": label,
                "lease_id": dispatch.lease_id,
                "operation_id": operation_id,
                "state": state,
            }
        )

    def _begin_nonreplayable(
        self, dispatch: Dispatch, operation_id: str, label: str
    ) -> None:
        path = self._operation_path(operation_id)
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError as error:
            # Without a complete whole-attempt receipt, both a started marker
            # and a completed marker mean the external outcome cannot be safely
            # replayed under this lease/fence identity.
            raise _OutcomeUnknown() from error
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(
                self._operation_record(dispatch, operation_id, label, "started")
            )
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(
            self.operation_journal,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _complete_nonreplayable(
        self, dispatch: Dispatch, operation_id: str, label: str
    ) -> None:
        path = self._operation_path(operation_id)
        expected = self._operation_record(dispatch, operation_id, label, "started")
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise _OutcomeUnknown()
        temporary = path.with_suffix(".completed.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(
                    self._operation_record(dispatch, operation_id, label, "completed")
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(
                self.operation_journal,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def _workspace(self, dispatch: Dispatch) -> Path:
        self._validate_directory(self.workspaces)
        return self.workspaces / sha256_hex(dispatch.attempt_id.encode())

    def _receipt_path(self, dispatch: Dispatch) -> Path:
        self._validate_directory(self.receipts)
        return self.receipts / (sha256_hex(dispatch.attempt_id.encode()) + ".json")

    @staticmethod
    def _read_receipt(path: Path) -> RuntimeReceipt | None:
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        try:
            with os.fdopen(descriptor, "rb") as stream:
                content = stream.read(1_048_577)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if len(content) > 1_048_576:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        try:
            return RuntimeReceipt.model_validate_json(content)
        except ValueError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error

    @staticmethod
    def _sync_receipt(path: Path) -> None:
        file_descriptor = directory_descriptor = -1
        try:
            file_descriptor = os.open(
                path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            os.fsync(file_descriptor)
            directory_descriptor = os.open(
                path.parent,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            os.fsync(directory_descriptor)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        finally:
            if directory_descriptor >= 0:
                os.close(directory_descriptor)
            if file_descriptor >= 0:
                os.close(file_descriptor)

    @staticmethod
    def _write_receipt(path: Path, receipt: RuntimeReceipt) -> None:
        content = canonical_json_bytes(receipt.model_dump(mode="json"))
        temporary = path.parent / f".{path.name}.{secrets.token_hex(12)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                if WorkerRuntime._read_receipt(path) != receipt:
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                WorkerRuntime._sync_receipt(path)
                return
            WorkerRuntime._sync_receipt(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _receipt_matches_dispatch(
        receipt: RuntimeReceipt, dispatch: Dispatch
    ) -> bool:
        return (
            receipt.worker_id,
            receipt.attempt_id,
            receipt.lease_id,
            receipt.fencing_token,
            receipt.workspace_id,
        ) == (
            dispatch.worker_id,
            dispatch.attempt_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            dispatch.workspace_id,
        ) and receipt.operation_id == stable_operation_id(
            dispatch, "attempt"
        ) and receipt.accepted_input_sha256 == tuple(
            item.sha256
            for item in sorted(
                dispatch.input_publications,
                key=lambda item: (item.kind, item.id, item.sha256),
            )
        ) and receipt.result.evidence_link == GenericEvidenceLink(
            evidence_id=WorkerRuntime._evidence_id_for(dispatch)
        )

    async def _fence(
        self, dispatch: Dispatch, operation_id: str, *, after: bool
    ) -> None:
        try:
            await _maybe_await(self.fence(dispatch, operation_id))
        except Exception as error:
            if after:
                raise _OutcomeUnknown() from error
            raise RuntimeFailure(RuntimeErrorCode.STALE_LEASE) from error

    def _load_receipt(self, dispatch: Dispatch) -> RuntimeReceipt | None:
        receipt = self._read_receipt(self._receipt_path(dispatch))
        if receipt is not None and not self._receipt_matches_dispatch(
            receipt, dispatch
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        return receipt

    def recover_durable_receipt(self, dispatch: Dispatch) -> WorkerRun | None:
        """Return only the exact durable result after repairing terminal evidence."""

        receipt = self._load_receipt(dispatch)
        if receipt is None:
            return None
        self._sync_receipt(self._receipt_path(dispatch))
        self._ensure_terminal_evidence(dispatch, receipt.result)
        return WorkerRun(result=receipt.result, receipt=receipt, replayed=True)

    def _save_receipt(self, dispatch: Dispatch, receipt: RuntimeReceipt) -> None:
        self._write_receipt(self._receipt_path(dispatch), receipt)

    def _ensure_terminal_evidence(
        self, dispatch: Dispatch, result: AttemptResult
    ) -> None:
        self._ensure_terminal_evidence_at(
            self.evidence, self.clock, dispatch, result, record=self._record
        )

    @staticmethod
    def _ensure_terminal_evidence_at(
        evidence: SQLiteAttemptEvidenceStore,
        clock: Callable[[], datetime],
        dispatch: Dispatch,
        result: AttemptResult,
        *,
        record: Callable[
            [
                Dispatch,
                AttemptEvidenceEventType,
                dict[str, object],
                tuple[EvidenceReference, ...],
            ],
            str,
        ]
        | None = None,
    ) -> None:
        append = record or (
            lambda current_dispatch, event_type, payload, references=():
            WorkerRuntime._record_at(
                evidence,
                clock,
                current_dispatch,
                event_type,
                payload,
                references,
            )
        )
        evidence_id = WorkerRuntime._evidence_id_for(dispatch)
        head = evidence.verify(evidence_id)
        if not head.seq:
            append(
                dispatch,
                AttemptEvidenceEventType.ATTEMPT_STARTED,
                {
                    "attempt_number": dispatch.attempt_number,
                    "worker_id": dispatch.worker_id,
                },
            )
            head = evidence.verify(evidence_id)
        expected_type = (
            AttemptEvidenceEventType.ATTEMPT_COMPLETED
            if result.succeeded
            else AttemptEvidenceEventType.ATTEMPT_FAILED
        )
        if head.seq:
            last = evidence.tail(evidence_id, head.seq - 1, 1)[0]
            if last.event_type in {
                AttemptEvidenceEventType.ATTEMPT_COMPLETED,
                AttemptEvidenceEventType.ATTEMPT_FAILED,
            }:
                if (
                    last.event_type != expected_type
                    or (
                        last.mission_id,
                        last.task_id,
                        last.attempt_id,
                    )
                    != (
                        dispatch.mission_id,
                        dispatch.task_id,
                        dispatch.attempt_id,
                    )
                    or last.payload != {"result_code": result.result_code}
                    or last.references != result.evidence_refs
                ):
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                return
        append(
            dispatch,
            expected_type,
            {"result_code": result.result_code},
            result.evidence_refs,
        )

    @staticmethod
    def _external_receipt_path(runtime: Path, attempt_id: str) -> Path:
        receipts = runtime / "worker-receipts"
        root_descriptor = child_descriptor = -1
        try:
            root_descriptor = os.open(
                runtime,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            child_descriptor = os.open(
                receipts.name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_descriptor,
            )
            opened_root = os.fstat(root_descriptor)
            opened_child = os.fstat(child_descriptor)
            visible_root = runtime.lstat()
            visible_child = receipts.lstat()
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        finally:
            if child_descriptor >= 0:
                os.close(child_descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)
        if (
            stat.S_ISLNK(visible_root.st_mode)
            or stat.S_ISLNK(visible_child.st_mode)
            or not stat.S_ISDIR(opened_root.st_mode)
            or not stat.S_ISDIR(opened_child.st_mode)
            or (opened_root.st_dev, opened_root.st_ino)
            != (visible_root.st_dev, visible_root.st_ino)
            or (opened_child.st_dev, opened_child.st_ino)
            != (visible_child.st_dev, visible_child.st_ino)
            or receipts.resolve(strict=True).parent != runtime.resolve(strict=True)
        ):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        return receipts / (sha256_hex(attempt_id.encode()) + ".json")

    @classmethod
    def reconcile_cancellation(
        cls,
        dispatch: Dispatch,
        *,
        runtime: Path,
        evidence: SQLiteAttemptEvidenceStore,
        interruption: WorkerProviderInterruption | None = None,
        retryable: bool = False,
        stage: str | None = None,
        failure_code: RuntimeErrorCode | None = None,
        recorded_at: datetime | None = None,
        operation_ids: tuple[str, ...] = (),
    ) -> WorkerRun:
        """Durably journal one cancelled dispatch without clearing ownership."""

        when = recorded_at or datetime.now(UTC)
        if failure_code is not None and (
            not retryable
            or failure_code
            not in {
                RuntimeErrorCode.RUNTIME_UNAVAILABLE,
                RuntimeErrorCode.SANDBOX_UNAVAILABLE,
            }
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        if interruption is not None and (
            interruption.mission_id,
            interruption.task_id,
            interruption.attempt_id,
            interruption.lease_id,
            interruption.fencing_token,
        ) != (
            dispatch.mission_id,
            dispatch.task_id,
            dispatch.attempt_id,
            dispatch.lease_id,
            dispatch.fencing_token,
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        path = cls._external_receipt_path(runtime, dispatch.attempt_id)
        receipt = cls._read_receipt(path)
        if receipt is not None and not cls._receipt_matches_dispatch(
            receipt, dispatch
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        if receipt is None:
            interruption_reference = (
                None
                if interruption is None
                else cls._store_provider_interruption_at(evidence, interruption)
            )
            retained_references, retained_envelopes = cls._evidence_state_at(
                evidence, dispatch
            )
            if interruption_reference is not None:
                retained_references = (*retained_references, interruption_reference)
            retained_references = tuple(
                sorted(
                    {
                        (item.kind, item.id, item.sha256): item
                        for item in retained_references
                    }.values(),
                    key=lambda item: (item.kind, item.id, item.sha256),
                )
            )
            result_code = (
                RuntimeErrorCode.CANCELLED.value
                if not retryable
                else failure_code.value
                if failure_code is not None
                else (
                    RuntimeErrorCode.PROVIDER_INTERRUPTED.value
                    if interruption is not None
                    else RuntimeErrorCode.RUNTIME_UNAVAILABLE.value
                )
            )
            completion = WorkerCompletion(
                outcome=(
                    CompletionOutcome.RETRYABLE_FAILURE
                    if retryable
                    else CompletionOutcome.TERMINAL_FAILURE
                ),
                result_code=result_code,
                session_id="cancelled-" + dispatch.attempt_id[-16:],
                invocation_id=(
                    interruption.sdk_invocation_id
                    if interruption is not None
                    and interruption.sdk_invocation_id is not None
                    else stable_operation_id(dispatch, "cancelled")
                ),
                provider_interruption=interruption,
            )
            result = AttemptResult(
                succeeded=False,
                retryable=retryable,
                result_code=result_code,
                stage=stage or "start",
                session_id=completion.session_id,
                invocation_id=completion.invocation_id,
                evidence_link=GenericEvidenceLink(
                    evidence_id=cls._evidence_id_for(dispatch)
                ),
                evidence_refs=retained_references,
                artifact_envelopes=retained_envelopes,
            )
            receipt = RuntimeReceipt.create(
                operation_id=stable_operation_id(dispatch, "attempt"),
                worker_id=dispatch.worker_id,
                attempt_id=dispatch.attempt_id,
                lease_id=dispatch.lease_id,
                fencing_token=dispatch.fencing_token,
                workspace_id=dispatch.workspace_id,
                completion=completion,
                operation_ids=operation_ids,
                accepted_input_sha256=tuple(
                    item.sha256
                    for item in sorted(
                        dispatch.input_publications,
                        key=lambda item: (item.kind, item.id, item.sha256),
                    )
                ),
                result=result,
            )
            cls._write_receipt(path, receipt)
        cls._ensure_terminal_evidence_at(
            evidence, lambda: when, dispatch, receipt.result
        )
        return WorkerRun(result=receipt.result, receipt=receipt, replayed=False)

    @staticmethod
    def _evidence_state_at(
        evidence: SQLiteAttemptEvidenceStore, dispatch: Dispatch
    ) -> tuple[
        tuple[EvidenceReference, ...],
        tuple[ArtifactEnvelopeReferenceV2, ...],
    ]:
        evidence_id = WorkerRuntime._evidence_id_for(dispatch)
        head = evidence.verify(evidence_id)
        references: list[EvidenceReference] = []
        envelopes: list[ArtifactEnvelopeReferenceV2] = []
        after = 0
        while after < head.seq:
            batch = evidence.tail(evidence_id, after, min(256, head.seq - after))
            if not batch:
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
            for event in batch:
                if (
                    event.mission_id,
                    event.task_id,
                    event.attempt_id,
                ) != (
                    dispatch.mission_id,
                    dispatch.task_id,
                    dispatch.attempt_id,
                ):
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                references.extend(event.references)
                if event.event_type == AttemptEvidenceEventType.CHECK_COMPLETED:
                    if (
                        len(event.references) != 1
                        or event.references[0].kind != "test-receipt"
                    ):
                        raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                    content = evidence.resolve(
                        event.references[0].kind, event.references[0].id
                    )
                    if content is None:
                        raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
                    try:
                        check_receipt = TrustedCheckReceipt.model_validate_json(content)
                    except ValueError as error:
                        raise RuntimeFailure(
                            RuntimeErrorCode.POLICY_REJECTED
                        ) from error
                    envelopes.extend(
                        item
                        for item in check_receipt.candidate_references
                        if isinstance(item, ArtifactEnvelopeReferenceV2)
                    )
            after = batch[-1].seq
        return (
            tuple(references),
            tuple(
                sorted(
                    {
                        item.artifact_envelope_sha256: item for item in envelopes
                    }.values(),
                    key=lambda item: item.artifact_envelope_sha256,
                )
            ),
        )

    @staticmethod
    def cancellation_interruption(
        dispatch: Dispatch,
        owned: OwnedProcess,
        barrier: ModelDispatchBarrier | None,
        *,
        requested_model: str,
        signal_number: int | None = None,
    ) -> WorkerProviderInterruption | None:
        if owned.model_request_sha256 is None and barrier is None:
            return None
        request_sha256 = (
            barrier.request_sha256
            if owned.model_request_sha256 is None and barrier is not None
            else owned.model_request_sha256
        )
        assert request_sha256 is not None
        if barrier is not None and (
            (
                barrier.mission_id,
                barrier.task_id,
                barrier.attempt_id,
                barrier.lease_id,
                barrier.fencing_token,
                barrier.request_sha256,
                barrier.pid,
                barrier.pgid,
                barrier.started_at,
                barrier.birth_token,
                barrier.executable,
            )
            != (
                dispatch.mission_id,
                dispatch.task_id,
                dispatch.attempt_id,
                dispatch.lease_id,
                dispatch.fencing_token,
                request_sha256,
                owned.pid,
                owned.pgid,
                owned.started_at,
                owned.birth_token,
                owned.executable,
            )
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        signal_name = (
            None
            if signal_number is None
            else signal.Signals(signal_number).name.lower()
        )
        return WorkerProviderInterruption(
            schema_version=1 if owned.model_input_bytes is not None else 2,
            requested_model=requested_model,
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            lease_id=dispatch.lease_id,
            fencing_token=dispatch.fencing_token,
            request_sha256=request_sha256,
            input_bytes=owned.model_input_bytes,
            provider_dispatch_state=(
                "unconfirmed" if barrier is None else "transport_acknowledged"
            ),
            sdk_invocation_id=(None if barrier is None else barrier.sdk_invocation_id),
            dispatched_at=None if barrier is None else barrier.dispatched_at,
            pid=owned.pid,
            pgid=owned.pgid,
            process_started_at=owned.started_at,
            process_identity_version=(
                barrier.schema_version
                if barrier is not None
                else (1 if owned.birth_token is None else 2)
            ),
            process_birth_token=owned.birth_token,
            executable=owned.executable,
            exit_code=(-1 if signal_number is None else -int(signal_number)),
            signal_name=signal_name,
            stderr_sha256=sha256_hex(b""),
            stderr_truncated=False,
        )

    @classmethod
    def cancellation_receipt_for_attempt(
        cls,
        *,
        runtime: Path,
        evidence: SQLiteAttemptEvidenceStore,
        attempt: Attempt,
    ) -> RuntimeReceipt | None:
        """Load only a receipt whose terminal evidence names this exact attempt."""

        receipt = cls._read_receipt(
            cls._external_receipt_path(runtime, attempt.attempt_id)
        )
        if receipt is None:
            return None
        if (
            (
                receipt.worker_id,
                receipt.attempt_id,
                receipt.lease_id,
                receipt.fencing_token,
                receipt.workspace_id,
            )
            != (
                attempt.worker_id,
                attempt.attempt_id,
                attempt.lease_id,
                attempt.fencing_token,
                attempt.workspace_id,
            )
            or receipt.operation_id
            != "op_"
            + canonical_json_sha256(
                {
                    "attempt_id": attempt.attempt_id,
                    "fencing_token": attempt.fencing_token,
                    "label": "attempt",
                    "lease_id": attempt.lease_id,
                }
            )[:32]
            or receipt.accepted_input_sha256
            != tuple(
                item.sha256
                for item in sorted(
                    attempt.input_publications,
                    key=lambda item: (item.kind, item.id, item.sha256),
                )
            )
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        evidence_id = cls._evidence_id_for_values(
            attempt.mission_id, attempt.attempt_id
        )
        if receipt.result.evidence_link != GenericEvidenceLink(
            evidence_id=evidence_id
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        head = evidence.verify(evidence_id)
        if not head.seq:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        last = evidence.tail(evidence_id, head.seq - 1, 1)[0]
        if (
            last.event_type
            != (
                AttemptEvidenceEventType.ATTEMPT_COMPLETED
                if receipt.result.succeeded
                else AttemptEvidenceEventType.ATTEMPT_FAILED
            )
            or (last.mission_id, last.task_id, last.attempt_id)
            != (attempt.mission_id, attempt.task_id, attempt.attempt_id)
            or last.payload != {"result_code": receipt.result.result_code}
            or last.references != receipt.result.evidence_refs
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        return receipt

    @staticmethod
    def cancellation_receipt_is_committed(
        receipt: RuntimeReceipt, attempt: Attempt
    ) -> bool:
        return attempt.state == AttemptState.CANCELLED and WorkerRuntime.terminal_receipt_is_committed(
            receipt, attempt
        )

    @staticmethod
    def terminal_receipt_is_committed(
        receipt: RuntimeReceipt, attempt: Attempt
    ) -> bool:
        return attempt.state in {
            AttemptState.COMMITTED,
            AttemptState.FAILED,
            AttemptState.CANCELLED,
        } and (
            attempt.session_id,
            attempt.invocation_id,
            attempt.evidence_link,
            attempt.evidence_refs,
            attempt.result_code,
        ) == (
            receipt.result.session_id,
            receipt.result.invocation_id,
            receipt.result.evidence_link,
            receipt.result.evidence_refs,
            receipt.result.result_code,
        )

    @classmethod
    def reconcile_terminal_receipt(
        cls,
        dispatch: Dispatch,
        attempt: Attempt,
        *,
        runtime: Path,
        evidence: SQLiteAttemptEvidenceStore,
    ) -> bool:
        """Idempotently clear retained process proof for a committed receipt."""

        receipt = cls.cancellation_receipt_for_attempt(
            runtime=runtime,
            evidence=evidence,
            attempt=attempt,
        )
        if receipt is None:
            return False
        if not cls._receipt_matches_dispatch(
            receipt, dispatch
        ) or not cls.terminal_receipt_is_committed(receipt, attempt):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        cls._clear_provider_process_at(runtime, dispatch, receipt.completion)
        cls._clear_normal_process_at(runtime, dispatch)
        return True

    @staticmethod
    def dispatch_from_snapshot(
        snapshot: MissionSnapshot, attempt_id: str
    ) -> tuple[Dispatch, Attempt]:
        matches = tuple(
            item for item in snapshot.attempts if item.attempt_id == attempt_id
        )
        if len(matches) != 1:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        attempt = matches[0]
        tasks = tuple(
            item
            for item in snapshot.tasks
            if item.task_id == attempt.task_id
            and attempt.plan_revision == snapshot.plan.revision
        )
        leases = tuple(
            item for item in snapshot.leases if item.lease_id == attempt.lease_id
        )
        if len(tasks) != 1 or len(leases) != 1:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        task, lease = tasks[0], leases[0]
        return (
            Dispatch(
                mission_id=attempt.mission_id,
                plan_revision=attempt.plan_revision,
                plan_sha256=canonical_json_sha256(
                    snapshot.plan.model_dump(mode="json")
                ),
                task_id=attempt.task_id,
                task_kind=task.kind,
                attempt_id=attempt.attempt_id,
                attempt_number=attempt.attempt_number,
                worker_id=attempt.worker_id,
                workspace_id=attempt.workspace_id,
                lease_id=attempt.lease_id,
                fencing_token=attempt.fencing_token,
                dispatch_command_id=attempt.dispatch_command_id,
                write_paths=task.write_paths,
                allowed_commands=task.allowed_commands,
                acceptance_checks=task.acceptance_checks,
                input_publications=attempt.input_publications,
                expires_at=lease.expires_at,
            ),
            attempt,
        )

    def _clear_recovered_provider_process(
        self, dispatch: Dispatch, completion: WorkerCompletion
    ) -> None:
        self._clear_provider_process_at(self.runtime, dispatch, completion)

    @staticmethod
    def _clear_provider_process_at(
        runtime: Path, dispatch: Dispatch, completion: WorkerCompletion
    ) -> None:
        interruption = completion.provider_interruption
        registry = OwnedProcessRegistry(runtime.parent)
        try:
            owned, barrier = registry.terminal_model_state(dispatch)
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if owned is None and barrier is None:
            return
        if barrier is None:
            assert owned is not None
            provider_bound = (
                interruption is None
                and completion.provider is not None
                and completion.provider.driver == "gemini_live"
                and owned.model_request_sha256 is not None
                and owned.model_input_bytes is not None
            )
            interruption_bound = (
                interruption is not None
                and interruption.provider_dispatch_state
                in {"unconfirmed", "transport_acknowledged"}
                and owned.model_request_sha256 is not None
                and owned.model_input_bytes is not None
                and (
                    owned.model_request_sha256,
                    owned.model_input_bytes,
                )
                == (
                    interruption.request_sha256,
                    interruption.input_bytes,
                )
                and (
                    owned.pid,
                    owned.pgid,
                    owned.started_at,
                    owned.birth_token,
                    owned.executable,
                )
                == (
                    interruption.pid,
                    interruption.pgid,
                    interruption.process_started_at,
                    interruption.process_birth_token,
                    interruption.executable,
                )
            )
            if not provider_bound and not interruption_bound:
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
            try:
                registry.remove_exact(owned)
            except ProcessControlError as error:
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
            return
        if owned is None:
            if interruption is None:
                bound = (
                    completion.provider is not None
                    and completion.provider.driver == "gemini_live"
                    and completion.invocation_id == barrier.sdk_invocation_id
                )
            else:
                bound = (
                    interruption.provider_dispatch_state
                    == "transport_acknowledged"
                    and (
                        barrier.request_sha256,
                        barrier.sdk_invocation_id,
                        barrier.pid,
                        barrier.pgid,
                        barrier.started_at,
                        barrier.birth_token,
                        barrier.executable,
                    )
                    == (
                        interruption.request_sha256,
                        interruption.sdk_invocation_id,
                        interruption.pid,
                        interruption.pgid,
                        interruption.process_started_at,
                        interruption.process_birth_token,
                        interruption.executable,
                    )
                )
            if not bound:
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
            try:
                registry.remove_barrier_exact(dispatch, barrier)
            except ProcessControlError as error:
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
            return
        if interruption is None:
            if (
                completion.provider is None
                or completion.provider.driver != "gemini_live"
                or completion.invocation_id != barrier.sdk_invocation_id
            ):
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        elif (
            interruption.provider_dispatch_state != "transport_acknowledged"
            or (
                barrier.request_sha256,
                barrier.sdk_invocation_id,
                barrier.pid,
                barrier.pgid,
                barrier.started_at,
                barrier.birth_token,
                barrier.executable,
            )
            != (
                interruption.request_sha256,
                interruption.sdk_invocation_id,
                interruption.pid,
                interruption.pgid,
                interruption.process_started_at,
                interruption.process_birth_token,
                interruption.executable,
            )
            or (
                owned.model_request_sha256 is None
                and (
                    interruption.schema_version != 2
                    or interruption.input_bytes is not None
                )
            )
            or (
                owned.model_request_sha256 is not None
                and (
                    owned.model_request_sha256,
                    owned.model_input_bytes,
                )
                != (
                    interruption.request_sha256,
                    interruption.input_bytes,
                )
            )
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        try:
            registry.remove_exact(owned)
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error

    @staticmethod
    def _clear_normal_process_at(runtime: Path, dispatch: Dispatch) -> None:
        registry = OwnedProcessRegistry(runtime.parent)
        try:
            normal = registry.owned_process(
                dispatch, require_live=False, model=False
            )
            model = registry.owned_process(
                dispatch, require_live=False, model=True
            )
            if normal is None or normal == model:
                return
            registry.terminate_owned(normal, retain_record=True)
            registry.remove_exact(normal)
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error

    @staticmethod
    def _git(
        repository: Path, *arguments: str, input_bytes: bytes | None = None
    ) -> bytes:
        result = subprocess.run(
            ("git", "-c", "core.hooksPath=/dev/null", *arguments),
            cwd=repository,
            env={
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
                "PATH": os.defpath,
            },
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        return result.stdout

    async def _clone(self, context: WorkerContext) -> None:
        workspace = context.workspace

        def clone() -> None:
            if workspace.exists():
                if workspace.is_symlink() or not workspace.is_dir():
                    raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
                return
            result = subprocess.run(
                (
                    "git",
                    "clone",
                    "--no-local",
                    "--no-checkout",
                    "--quiet",
                    os.fspath(self.repository),
                    os.fspath(workspace),
                ),
                env={
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0",
                    "LC_ALL": "C",
                    "PATH": os.defpath,
                },
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            if result.returncode:
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
            self._git(workspace, "checkout", "--detach", "--quiet", self.base_sha)
            for remote in self._git(workspace, "remote").decode().splitlines():
                if remote:
                    self._git(workspace, "remote", "remove", remote)
            if self._git(workspace, "remote").strip():
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)

        await context._effect("clone", clone)

    @staticmethod
    def _media_type(kind: str) -> str:
        return {
            "patch": "application/vnd.graphene.git-patch",
            "test-receipt": "application/vnd.graphene.check-receipt+json",
        }.get(kind, "application/octet-stream")

    @staticmethod
    def _direct_inputs(dispatch: Dispatch) -> tuple[DirectArtifactInputV2, ...]:
        direct = []
        for reference in dispatch.input_publications:
            if isinstance(reference, PublishedArtifactReferenceV2):
                direct.append(
                    DirectArtifactInputV2(
                        publication_id=reference.publication_id,
                        producer_task_id=reference.producer_task_id,
                        output_name=reference.output_name,
                        artifact_envelope_sha256=reference.artifact_envelope_sha256,
                    )
                )
            elif reference.kind != "operator-input":
                raise RuntimeFailure(RuntimeErrorCode.INPUT_REJECTED)
        return tuple(
            sorted(
                direct,
                key=lambda item: (
                    item.producer_task_id,
                    item.output_name,
                    item.publication_id,
                    item.artifact_envelope_sha256,
                ),
            )
        )

    def _store_enveloped_artifact(
        self,
        dispatch: Dispatch,
        *,
        output_name: str,
        kind: str,
        content: bytes,
        tree_sha256: str | None = None,
        mutation_manifest_sha256: str | None = None,
    ) -> tuple[EvidenceReference, ArtifactEnvelopeReferenceV2]:
        envelope = ArtifactEnvelopeV2.create(
            content,
            mission_id=dispatch.mission_id,
            plan_revision=dispatch.plan_revision,
            plan_sha256=dispatch.plan_sha256,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            fencing_token=dispatch.fencing_token,
            policy_sha256=self.policy_sha256,
            base_git_commit=self.base_sha,
            direct_inputs=self._direct_inputs(dispatch),
            output_name=output_name,
            artifact_kind=kind,
            media_type=self._media_type(kind),
            mutation_manifest_sha256=mutation_manifest_sha256,
            tree_hash_version=None if tree_sha256 is None else TREE_HASH_VERSION,
            tree_sha256=tree_sha256,
            created_by="trusted-worker-wrapper",
        )
        return self.evidence.put_artifact_envelope(
            envelope, content, visibility=ArtifactVisibility.MISSION
        )

    async def _accepted_inputs(self, context: WorkerContext) -> tuple[bytes, ...]:
        values = []
        for reference in sorted(
            context.dispatch.input_publications,
            key=lambda item: (item.kind, item.id, item.sha256),
        ):
            if reference.kind == "operator-input":
                continue
            if not isinstance(reference, PublishedArtifactReferenceV2) or (
                reference.kind != "patch"
            ):
                raise RuntimeFailure(RuntimeErrorCode.INPUT_REJECTED)

            def resolve(reference: ArtifactInputReference = reference) -> bytes:
                content = self.accepted_artifact(context.dispatch, reference)
                if (
                    not isinstance(content, bytes)
                    or sha256_hex(content) != reference.sha256
                ):
                    raise RuntimeFailure(RuntimeErrorCode.ARTIFACT_TAMPERED)
                return content

            value = await context._effect(f"accepted:{reference.id}", resolve)
            values.append(bytes(value))
        return tuple(values)

    async def _apply(self, context: WorkerContext, patches: tuple[bytes, ...]) -> None:
        for index, patch in enumerate(patches):
            await context._effect(
                f"apply:{index}",
                lambda patch=patch: self._git(
                    context.workspace,
                    "apply",
                    "--whitespace=nowarn",
                    "-",
                    input_bytes=patch,
                ),
            )

    async def _patch(
        self, context: WorkerContext, *, work_only: bool
    ) -> tuple[bytes, tuple[str, ...]]:
        if work_only:
            untracked = bytes(
                await context._effect(
                    "untracked-paths",
                    lambda: self._git(
                        context.workspace,
                        "ls-files",
                        "--others",
                        "--exclude-standard",
                        "-z",
                        "--",
                        ".",
                    ),
                )
            )
            untracked_paths = tuple(
                item.decode() for item in untracked.split(b"\0") if item
            )
            if untracked_paths:
                await context._effect(
                    "intent-to-add",
                    lambda: self._git(
                        context.workspace,
                        "add",
                        "--intent-to-add",
                        "--",
                        *untracked_paths,
                    ),
                )
        else:
            await context._effect(
                "stage",
                lambda: self._git(context.workspace, "add", "--all", "--", "."),
            )
        diff_mode = () if work_only else ("--cached", self.base_sha)
        changed = bytes(
            await context._effect(
                "changed-paths",
                lambda: self._git(
                    context.workspace,
                    "diff",
                    *diff_mode,
                    "--no-renames",
                    "--name-only",
                    "-z",
                    "--",
                ),
            )
        )
        paths = tuple(sorted(item.decode() for item in changed.split(b"\0") if item))
        patch = bytes(
            await context._effect(
                "patch",
                lambda: self._git(
                    context.workspace,
                    "diff",
                    *diff_mode,
                    "--binary",
                    "--",
                ),
            )
        )
        if not patch or len(patch) > 1_048_576:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        return patch, paths

    @staticmethod
    def _candidate_tree(workspace: Path) -> str:
        files: dict[str, TreeEntry] = {}
        for root, directories, names in os.walk(workspace):
            if Path(root) == workspace:
                directories[:] = [item for item in directories if item != ".git"]
            if any(
                not stat.S_ISDIR(Path(root, item).lstat().st_mode)
                for item in directories
            ):
                raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
            for name in names:
                path = Path(root, name)
                metadata = path.lstat()
                if not stat.S_ISREG(metadata.st_mode):
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                files[path.relative_to(workspace).as_posix()] = TreeEntry(
                    path.read_bytes(),
                    EXECUTABLE_FILE_MODE
                    if metadata.st_mode & 0o111
                    else REGULAR_FILE_MODE,
                )
        return candidate_tree_sha256(files)

    async def _check(
        self,
        context: WorkerContext,
        candidate_references: tuple[ArtifactEnvelopeReferenceV2, ...],
    ) -> tuple[
        CheckOutcome,
        EvidenceReference,
        ArtifactEnvelopeReferenceV2,
        EvidenceReference | None,
        EvidenceReference | None,
    ]:
        candidate_tree = self._candidate_tree(context.workspace)
        outcome = await context._effect(
            "check",
            lambda: self.check_runner(
                context.workspace, context.assignment, context.dispatch.attempt_id
            ),
        )
        if (
            not isinstance(outcome, CheckOutcome)
            or self._candidate_tree(context.workspace) != candidate_tree
        ):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        passed = (
            outcome.exit_code == 0
            and not outcome.timed_out
            and not outcome.output_truncated
            and outcome.cleanup_complete
        )
        receipt = TrustedCheckReceipt(
            schema_version=2,
            mission_id=context.dispatch.mission_id,
            task_id=context.dispatch.task_id,
            attempt_id=context.dispatch.attempt_id,
            plan_revision=context.dispatch.plan_revision,
            fencing_token=context.dispatch.fencing_token,
            policy_sha256=self.policy_sha256,
            base_sha=self.base_sha,
            runner_id="graphene_check_runner_v1",
            template_id=outcome.template_id,
            template_sha256=outcome.template_sha256,
            accepted_input_references=tuple(
                sorted(
                    context.dispatch.input_publications,
                    key=artifact_input_reference_key,
                )
            ),
            candidate_references=tuple(
                sorted(
                    candidate_references,
                    key=lambda item: item.artifact_envelope_sha256,
                )
            ),
            candidate_tree_hash_version=TREE_HASH_VERSION,
            candidate_tree_sha256=candidate_tree,
            result_code="passed" if passed else "acceptance_check_failed",
            exit_code=outcome.exit_code,
            timed_out=outcome.timed_out,
            output_sha256=outcome.output_sha256,
            output_truncated=outcome.output_truncated,
            cleanup_complete=outcome.cleanup_complete,
        )
        record = canonical_json_bytes(receipt.model_dump(mode="json"))
        stored = await context._effect(
            "store-check-receipt",
            lambda: self._store_enveloped_artifact(
                context.dispatch,
                output_name=context.assignment.output_name,
                kind="test-receipt",
                content=record,
                tree_sha256=candidate_tree,
            ),
        )
        if (
            not isinstance(stored, tuple)
            or len(stored) != 2
            or not isinstance(stored[0], EvidenceReference)
            or not isinstance(stored[1], ArtifactEnvelopeReferenceV2)
        ):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        reference, envelope_reference = stored
        self._record(
            context.dispatch,
            AttemptEvidenceEventType.CHECK_COMPLETED,
            receipt.event_payload(reference.sha256),
            (reference,),
        )
        diagnostic_reference = None
        if outcome.diagnostic is not None:
            diagnostic = outcome.diagnostic
            diagnostic_reference = await context._effect(
                "store-check-diagnostic",
                lambda: self.evidence.put_artifact(
                    CHECK_DIAGNOSTIC_KIND,
                    canonical_json_bytes(diagnostic.model_dump(mode="json")),
                    visibility=ArtifactVisibility.MISSION,
                ),
            )
            if not isinstance(diagnostic_reference, EvidenceReference):
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        truth_reference = None
        if outcome.truth_label is not None:
            truth_reference = await context._effect(
                "store-check-truth-receipt",
                lambda: self.evidence.put_artifact(
                    "simulation-truth-receipt",
                    canonical_json_bytes(
                        {
                            "schema_version": 1,
                            "truth_kind": outcome.truth_kind,
                            "truth_label": outcome.truth_label,
                            "task_id": context.dispatch.task_id,
                            "attempt_id": context.dispatch.attempt_id,
                            "template_id": outcome.template_id,
                            "result_code": receipt.result_code,
                        }
                    ),
                    visibility=ArtifactVisibility.MISSION,
                ),
            )
        return (
            outcome,
            reference,
            envelope_reference,
            truth_reference,
            diagnostic_reference,
        )

    async def _store_provider_receipt(
        self, context: WorkerContext, provider: WorkerProviderReceipt
    ) -> EvidenceReference:
        """Bind the sanitized provider receipt to the attempt as evidence.

        A failed write must never yield a COMPLETED attempt: non-runtime errors
        map to ``runtime_unavailable`` and post-effect fence loss keeps the
        surrounding outcome-unknown discipline.
        """

        record = canonical_json_bytes(provider.model_dump(mode="json"))
        try:
            stored = await context._effect(
                "store-provider-receipt",
                lambda: self.evidence.put_artifact(
                    WORKER_PROVIDER_RECEIPT_KIND,
                    record,
                    visibility=ArtifactVisibility.MISSION,
                ),
            )
        except RuntimeFailure:
            raise
        except Exception as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if (
            not isinstance(stored, EvidenceReference)
            or stored.kind != WORKER_PROVIDER_RECEIPT_KIND
            or stored.sha256 != sha256_hex(record)
        ):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        return stored

    @staticmethod
    def _store_provider_interruption_at(
        evidence: SQLiteAttemptEvidenceStore,
        interruption: WorkerProviderInterruption,
    ) -> EvidenceReference:
        """Bind sanitized child-interruption proof without persisting stderr."""

        record = canonical_json_bytes(interruption.model_dump(mode="json"))
        try:
            # Content addressing makes this write replay-safe across a crash
            # before the whole-attempt receipt is durable.
            stored = evidence.put_artifact(
                WORKER_PROVIDER_INTERRUPTION_KIND,
                record,
                visibility=ArtifactVisibility.MISSION,
            )
        except RuntimeFailure:
            raise
        except Exception as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if (
            not isinstance(stored, EvidenceReference)
            or stored.kind != WORKER_PROVIDER_INTERRUPTION_KIND
            or stored.sha256 != sha256_hex(record)
        ):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        return stored

    def _store_provider_interruption(
        self, interruption: WorkerProviderInterruption
    ) -> EvidenceReference:
        return self._store_provider_interruption_at(self.evidence, interruption)

    @staticmethod
    def _evidence_id_for(dispatch: Dispatch) -> str:
        return WorkerRuntime._evidence_id_for_values(
            dispatch.mission_id, dispatch.attempt_id
        )

    @staticmethod
    def _evidence_id_for_values(mission_id: str, attempt_id: str) -> str:
        return (
            "attempt_evidence_"
            + canonical_json_sha256((mission_id, attempt_id))[:24]
        )

    def _evidence_id(self, dispatch: Dispatch) -> str:
        return self._evidence_id_for(dispatch)

    @staticmethod
    def _record_at(
        evidence: SQLiteAttemptEvidenceStore,
        clock: Callable[[], datetime],
        dispatch: Dispatch,
        event_type: AttemptEvidenceEventType,
        payload: dict[str, object],
        references: tuple[EvidenceReference, ...] = (),
    ) -> str:
        evidence_id = WorkerRuntime._evidence_id_for(dispatch)
        head = evidence.head(evidence_id)
        command_id = (
            "runtime_"
            + canonical_json_sha256(
                (dispatch.attempt_id, event_type.value, head.seq + 1)
            )[:24]
        )
        if event_type == AttemptEvidenceEventType.CHECK_COMPLETED:
            if len(references) != 1:
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
            evidence.append_check(
                evidence_id,
                head,
                command_id,
                mission_id=dispatch.mission_id,
                task_id=dispatch.task_id,
                attempt_id=dispatch.attempt_id,
                receipt=references[0],
                payload=payload,
                recorded_at=clock(),
            )
        else:
            evidence.append(
                evidence_id,
                head,
                command_id,
                AttemptEvidenceInput(
                    mission_id=dispatch.mission_id,
                    task_id=dispatch.task_id,
                    attempt_id=dispatch.attempt_id,
                    event_type=event_type,
                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                    authority=AttemptEvidenceAuthority.SCOPED_TOOL_WRAPPER,
                    references=references,
                    payload=payload,
                ),
                recorded_at=clock(),
            )
        return evidence_id

    def _record(
        self,
        dispatch: Dispatch,
        event_type: AttemptEvidenceEventType,
        payload: dict[str, object],
        references: tuple[EvidenceReference, ...] = (),
    ) -> str:
        return self._record_at(
            self.evidence,
            self.clock,
            dispatch,
            event_type,
            payload,
            references,
        )

    def _record_cancelled_stage(self, dispatch: Dispatch) -> None:
        """Say how far a cancelled attempt got, before it disappears.

        A cancellation is a `BaseException`, so it bypasses every failure
        handler in `_execute_locked` and none of the terminal bookkeeping
        runs: without this the attempt reaches the store as a bare
        `cancelled` or `outcome_unknown` with no evidence at all. That is
        exactly the case where a reader most needs to know whether the
        acceptance check had already passed. This adds one non-terminal
        evidence event naming the stages the attempt completed, and remembers
        the last of them for `cancelled_stage`, which the runner reads.
        """
        context = self._contexts.get(dispatch.attempt_id)
        stages = list(context.completed_stages) if context is not None else []
        # Set before the evidence append, which is allowed to fail: the stage
        # the runner reports must not depend on the evidence store being up.
        self._cancelled_stages[dispatch.attempt_id] = stages[-1] if stages else "start"
        try:
            self._record(
                dispatch,
                AttemptEvidenceEventType.OPERATION_FAILED,
                {
                    "reason": "cancelled",
                    "stage_reached": stages[-1] if stages else "start",
                    "check_completed": "check" in stages,
                    "completed_stages": ",".join(stages),
                },
            )
        except Exception:
            # Losing the stage record must never turn a cancellation into a
            # different failure; the cancellation is what propagates.
            return

    async def execute_async(self, dispatch: Dispatch) -> WorkerRun:
        lock = self._attempt_locks.setdefault(dispatch.attempt_id, asyncio.Lock())
        async with lock:
            self._active[dispatch.attempt_id] = dispatch
            try:
                return await self._execute_locked(dispatch)
            except BaseException as error:
                if not isinstance(error, Exception):
                    self._record_cancelled_stage(dispatch)
                raise
            finally:
                self._active.pop(dispatch.attempt_id, None)
                self._contexts.pop(dispatch.attempt_id, None)

    async def reconcile_expired_async(self, dispatch: Dispatch) -> WorkerRun | None:
        """Durably stop an exact owned child without reviving an expired lease."""

        lock = self._attempt_locks.setdefault(dispatch.attempt_id, asyncio.Lock())
        async with lock:
            normal = self._owned_normal_process(dispatch)
            if normal is not None:
                try:
                    await asyncio.to_thread(
                        OwnedProcessRegistry(self.runtime.parent).terminate_owned,
                        normal,
                        retain_record=True,
                    )
                except ProcessControlError as error:
                    raise RuntimeFailure(
                        RuntimeErrorCode.RUNTIME_UNAVAILABLE
                    ) from error
            container_reconciled = await self._reconcile_owned_container(dispatch)
            recovered = self.recover_durable_receipt(dispatch)
            if recovered is not None:
                await self._remove_expired_workspace(dispatch)
                return recovered
            if dispatch.task_kind != TaskKind.WORK:
                if normal is None and not container_reconciled:
                    return None
                reconciled = self.reconcile_cancellation(
                    dispatch,
                    runtime=self.runtime,
                    evidence=self.evidence,
                    retryable=True,
                    stage="check",
                    recorded_at=self.clock(),
                    operation_ids=(
                        stable_operation_id(dispatch, "expired-reconciliation"),
                    ),
                )
                self._clear_normal_process_at(self.runtime, dispatch)
                await self._remove_expired_workspace(dispatch)
                return reconciled
            adapter = self.registry.resolve(dispatch)
            reconcile = getattr(adapter, "reconcile_owned", None)
            if not callable(reconcile):
                return None
            completion = await asyncio.to_thread(
                reconcile, dispatch, self.runtime.parent
            )
            if completion is None:
                if normal is None and not container_reconciled:
                    return None
                reconciled = self.reconcile_cancellation(
                    dispatch,
                    runtime=self.runtime,
                    evidence=self.evidence,
                    retryable=True,
                    stage="check",
                    recorded_at=self.clock(),
                    operation_ids=(
                        stable_operation_id(dispatch, "expired-reconciliation"),
                    ),
                )
                self._clear_normal_process_at(self.runtime, dispatch)
                await self._remove_expired_workspace(dispatch)
                return reconciled
            interruption = completion.provider_interruption
            if (
                completion.result_code
                != RuntimeErrorCode.PROVIDER_INTERRUPTED.value
                or interruption is None
                or (
                    interruption.mission_id,
                    interruption.task_id,
                    interruption.attempt_id,
                    interruption.lease_id,
                    interruption.fencing_token,
                )
                != (
                    dispatch.mission_id,
                    dispatch.task_id,
                    dispatch.attempt_id,
                    dispatch.lease_id,
                    dispatch.fencing_token,
                )
                or (
                    interruption.sdk_invocation_id is not None
                    and interruption.sdk_invocation_id != completion.invocation_id
                )
            ):
                raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
            reference = self._store_provider_interruption(interruption)
            operation_id = stable_operation_id(dispatch, "expired-reconciliation")
            result = AttemptResult(
                succeeded=False,
                retryable=True,
                result_code=RuntimeErrorCode.PROVIDER_INTERRUPTED,
                stage="model",
                session_id=completion.session_id,
                invocation_id=completion.invocation_id,
                evidence_link=GenericEvidenceLink(
                    evidence_id=self._evidence_id(dispatch)
                ),
                evidence_refs=(reference,),
            )
            receipt = RuntimeReceipt.create(
                operation_id=stable_operation_id(dispatch, "attempt"),
                worker_id=dispatch.worker_id,
                attempt_id=dispatch.attempt_id,
                lease_id=dispatch.lease_id,
                fencing_token=dispatch.fencing_token,
                workspace_id=dispatch.workspace_id,
                completion=completion,
                operation_ids=(operation_id,),
                accepted_input_sha256=tuple(
                    item.sha256
                    for item in sorted(
                        dispatch.input_publications,
                        key=lambda item: (item.kind, item.id, item.sha256),
                    )
                ),
                result=result,
            )
            self._save_receipt(dispatch, receipt)
            self._ensure_terminal_evidence(dispatch, result)
            self._clear_recovered_provider_process(dispatch, completion)
            self._clear_normal_process_at(self.runtime, dispatch)
            await self._remove_expired_workspace(dispatch)
            return WorkerRun(result=result, receipt=receipt)

    async def _remove_expired_workspace(self, dispatch: Dispatch) -> None:
        self._validate_directory(self.workspaces)
        workspace = self._workspace(dispatch)
        try:
            metadata = workspace.lstat()
        except FileNotFoundError:
            return
        try:
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or workspace.resolve(strict=True).parent != self.workspaces
            ):
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
            await asyncio.to_thread(shutil.rmtree, workspace)
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error

    async def _execute_locked(self, dispatch: Dispatch) -> WorkerRun:
        recovered = self.recover_durable_receipt(dispatch)
        if recovered is not None:
            workspace = self._workspace(dispatch)
            cleanup_id = stable_operation_id(dispatch, "cleanup")
            await self._fence(dispatch, cleanup_id, after=False)
            if workspace.exists():
                await asyncio.to_thread(shutil.rmtree, workspace)
            await self._fence(dispatch, cleanup_id, after=True)
            return recovered
        interrupted_check = await self._reconcile_started_check(dispatch)
        if interrupted_check is not None:
            return interrupted_check
        assignment = self.assignment(dispatch)
        if (
            assignment.task_id != dispatch.task_id
            or dispatch.acceptance_checks != (assignment.command_template.template_id,)
            or dispatch.allowed_commands != (assignment.command_template.template_id,)
            or (
                dispatch.task_kind == TaskKind.WORK
                and assignment.output_paths != dispatch.write_paths
            )
            or (
                dispatch.task_kind == TaskKind.ASSEMBLY
                and not dispatch.input_publications
            )
            or (
                dispatch.task_kind == TaskKind.VERIFICATION
                and (
                    len(dispatch.input_publications) != 1
                    or dispatch.input_publications[0].kind != "patch"
                )
            )
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        adapter = (
            self.registry.resolve(dispatch)
            if dispatch.task_kind == TaskKind.WORK
            else None
        )
        workspace = self._workspace(dispatch)
        context = WorkerContext(self, dispatch, assignment, workspace)
        self._contexts[dispatch.attempt_id] = context
        self._record(
            dispatch,
            AttemptEvidenceEventType.ATTEMPT_STARTED,
            {
                "attempt_number": dispatch.attempt_number,
                "worker_id": dispatch.worker_id,
            },
        )
        completion: WorkerCompletion | None = None
        references: list[EvidenceReference] = []
        envelope_references: list[ArtifactEnvelopeReferenceV2] = []
        publication: PublicationDraft | None = None
        try:
            await self._clone(context)
            baseline = await context._effect(
                "baseline", lambda: context.capture_baseline(self.base_sha)
            )
            patches = await self._accepted_inputs(context)
            await self._apply(context, patches)
            accepted_paths: tuple[str, ...] = ()
            if dispatch.task_kind == TaskKind.WORK and patches:
                await context._effect(
                    "stage-accepted",
                    lambda: self._git(workspace, "add", "--all", "--", "."),
                )
                accepted_raw = bytes(
                    await context._effect(
                        "accepted-paths",
                        lambda: self._git(
                            workspace,
                            "diff",
                            "--cached",
                            "--name-only",
                            "-z",
                            self.base_sha,
                            "--",
                        ),
                    )
                )
                accepted_paths = tuple(
                    sorted(item.decode() for item in accepted_raw.split(b"\0") if item)
                )
            if dispatch.task_kind == TaskKind.WORK:
                assert adapter is not None
                self._cancellation_safe_attempts.add(dispatch.attempt_id)
                try:
                    recover = getattr(adapter, "recover_interrupted", None)
                    completion = (
                        await recover(context, assignment)
                        if callable(recover)
                        else None
                    )
                    if completion is None:
                        completion = await context._effect(
                            "model", lambda: adapter.execute(context, assignment)
                        )
                finally:
                    self._cancellation_safe_attempts.discard(dispatch.attempt_id)
                if not isinstance(completion, WorkerCompletion):
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                interruption = completion.provider_interruption
                if interruption is not None and (
                    (
                        interruption.mission_id,
                        interruption.task_id,
                        interruption.attempt_id,
                        interruption.lease_id,
                        interruption.fencing_token,
                    )
                    != (
                        dispatch.mission_id,
                        dispatch.task_id,
                        dispatch.attempt_id,
                        dispatch.lease_id,
                        dispatch.fencing_token,
                    )
                    or (
                        interruption.sdk_invocation_id is not None
                        and interruption.sdk_invocation_id != completion.invocation_id
                    )
                ):
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                if interruption is not None:
                    references.append(
                        self._store_provider_interruption(interruption)
                    )
                if completion.provider is not None:
                    # Bind the receipt on success and failure alike so the
                    # terminal evidence event and Attempt.evidence_refs cite it.
                    references.append(
                        await self._store_provider_receipt(context, completion.provider)
                    )
                if completion.outcome != CompletionOutcome.COMPLETED:
                    raise RuntimeFailure(
                        RuntimeErrorCode(completion.result_code),
                        outcome_unknown=completion.outcome
                        == CompletionOutcome.OUTCOME_UNKNOWN,
                    )
            else:
                stable = stable_operation_id(dispatch, "deterministic")
                completion = WorkerCompletion(
                    outcome=CompletionOutcome.COMPLETED,
                    result_code="passed",
                    session_id="deterministic-" + stable[-16:],
                    invocation_id=stable,
                )

            artifact: EvidenceReference | None = None
            artifact_envelope: ArtifactEnvelopeReferenceV2 | None = None
            if dispatch.task_kind != TaskKind.VERIFICATION:
                work_only = dispatch.task_kind == TaskKind.WORK
                patch, changed_paths = await self._patch(context, work_only=work_only)
                if work_only and changed_paths != dispatch.write_paths:
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                allowed_paths = (
                    tuple(sorted(set((*accepted_paths, *dispatch.write_paths))))
                    if work_only
                    else changed_paths
                )
                audit = await context._effect(
                    "audit", lambda: audit_workspace(workspace, baseline, allowed_paths)
                )
                expected_audit_paths = (
                    tuple(sorted(set((*accepted_paths, *changed_paths))))
                    if work_only
                    else changed_paths
                )
                if audit.changed_paths != expected_audit_paths:
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                stored_artifact = await context._effect(
                    "store-patch",
                    lambda: self._store_enveloped_artifact(
                        dispatch,
                        output_name=assignment.output_name,
                        kind="patch",
                        content=patch,
                        tree_sha256=self._candidate_tree(workspace),
                        mutation_manifest_sha256=audit.patch_sha256,
                    ),
                )
                if (
                    not isinstance(stored_artifact, tuple)
                    or len(stored_artifact) != 2
                    or not isinstance(stored_artifact[0], EvidenceReference)
                    or not isinstance(stored_artifact[1], ArtifactEnvelopeReferenceV2)
                ):
                    raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
                artifact, artifact_envelope = stored_artifact
                references.append(artifact)
                envelope_references.append(artifact_envelope)
                if dispatch.task_kind == TaskKind.ASSEMBLY:
                    # The candidate is staged only to produce exact deterministic
                    # bytes. Restore it to the working tree before the reviewed
                    # `git diff --check --` command runs.
                    await context._effect(
                        "reset-index",
                        lambda: self._git(
                            workspace, "reset", "--mixed", "--quiet", self.base_sha
                        ),
                    )
            candidate_references = (
                tuple(
                    item
                    for item in dispatch.input_publications
                    if isinstance(item, PublishedArtifactReferenceV2)
                    and item.kind == "patch"
                )
                if dispatch.task_kind == TaskKind.VERIFICATION
                else (() if artifact_envelope is None else (artifact_envelope,))
            )
            (
                check,
                check_reference,
                check_envelope,
                truth_reference,
                diagnostic_reference,
            ) = await self._check(context, candidate_references)
            references.append(check_reference)
            envelope_references.append(check_envelope)
            if truth_reference is not None:
                references.append(truth_reference)
            if diagnostic_reference is not None:
                references.append(diagnostic_reference)
            if (
                check.exit_code
                or check.timed_out
                or check.output_truncated
                or not check.cleanup_complete
            ):
                prior = assignment.prior_failure
                repeated = (
                    prior is not None
                    and check.diagnostic is not None
                    and check.diagnostic.signature() == prior.failure_signature
                )
                raise RuntimeFailure(
                    RuntimeErrorCode.ACCEPTANCE_CHECK_FAILED, terminal=repeated
                )
            output_reference = (
                check_reference
                if dispatch.task_kind == TaskKind.VERIFICATION
                else artifact
            )
            output_envelope = (
                check_envelope
                if dispatch.task_kind == TaskKind.VERIFICATION
                else artifact_envelope
            )
            assert output_reference is not None
            assert output_envelope is not None
            publication = PublicationDraft(
                output_name=assignment.output_name,
                kind=assignment.output_kind,
                sha256=output_reference.sha256,
                artifact=output_envelope,
                visibility=ArtifactVisibility.MISSION,
                paths=assignment.output_paths,
            )
            result_code = "passed"
            succeeded = True
            retryable = False
        except _ModelEffectUncommitted:
            # The adapter may have crossed provider transport while the local
            # completion marker/fence failed. Leave the exact process/barrier
            # and attempt untouched so Runner/restart can reconcile it into a
            # capability-bound interruption receipt.
            raise
        except RuntimeFailure as error:
            result_code = (
                RuntimeErrorCode.OUTCOME_UNKNOWN.value
                if error.outcome_unknown
                else error.code.value
            )
            succeeded = False
            retryable = not error.terminal and error.code in {
                RuntimeErrorCode.ACCEPTANCE_CHECK_FAILED,
                RuntimeErrorCode.MODEL_OUTPUT_REJECTED,
                RuntimeErrorCode.PROVIDER_RATE_LIMITED,
                RuntimeErrorCode.PROVIDER_INTERRUPTED,
                RuntimeErrorCode.PROVIDER_TIMEOUT,
                RuntimeErrorCode.PROVIDER_UNAVAILABLE,
                RuntimeErrorCode.RUNTIME_UNAVAILABLE,
                RuntimeErrorCode.SANDBOX_UNAVAILABLE,
            }
            completion = WorkerCompletion(
                outcome=(
                    CompletionOutcome.OUTCOME_UNKNOWN
                    if error.outcome_unknown
                    else CompletionOutcome.RETRYABLE_FAILURE
                    if retryable
                    else CompletionOutcome.TERMINAL_FAILURE
                ),
                result_code=result_code,
                session_id=(
                    completion.session_id
                    if completion is not None
                    else "runtime-" + dispatch.attempt_id[-16:]
                ),
                invocation_id=(
                    completion.invocation_id
                    if completion is not None
                    else stable_operation_id(dispatch, "failure")
                ),
                provider=completion.provider if completion is not None else None,
                provider_interruption=(
                    completion.provider_interruption
                    if completion is not None
                    else None
                ),
            )
        except Exception:
            result_code = RuntimeErrorCode.OUTCOME_UNKNOWN.value
            succeeded = retryable = False
            completion = WorkerCompletion(
                outcome=CompletionOutcome.OUTCOME_UNKNOWN,
                result_code=result_code,
                session_id=(
                    completion.session_id
                    if completion is not None
                    else "runtime-" + dispatch.attempt_id[-16:]
                ),
                invocation_id=(
                    completion.invocation_id
                    if completion is not None
                    else stable_operation_id(dispatch, "failure")
                ),
                provider=completion.provider if completion is not None else None,
                provider_interruption=(
                    completion.provider_interruption
                    if completion is not None
                    else None
                ),
            )

        references_tuple = tuple(
            sorted(
                {
                    (item.kind, item.id, item.sha256): item for item in references
                }.values(),
                key=lambda item: (item.kind, item.id, item.sha256),
            )
        )
        try:
            await context._effect(
                "cleanup",
                lambda: (
                    asyncio.to_thread(shutil.rmtree, workspace)
                    if workspace.exists()
                    else None
                ),
            )
        except Exception:
            result_code = RuntimeErrorCode.OUTCOME_UNKNOWN.value
            succeeded = retryable = False
            publication = None
            completion = WorkerCompletion(
                outcome=CompletionOutcome.OUTCOME_UNKNOWN,
                result_code=result_code,
                session_id=completion.session_id if completion else "runtime-cleanup",
                invocation_id=(
                    completion.invocation_id
                    if completion is not None
                    else stable_operation_id(dispatch, "cleanup-failure")
                ),
                provider=completion.provider if completion else None,
                provider_interruption=(
                    completion.provider_interruption if completion else None
                ),
            )
        evidence_id = self._evidence_id(dispatch)
        result = AttemptResult(
            succeeded=succeeded,
            retryable=retryable,
            result_code=result_code,
            stage=(
                None
                if succeeded
                else (
                    context.completed_stages[-1]
                    if context.completed_stages
                    else "start"
                )
            ),
            session_id=completion.session_id,
            invocation_id=completion.invocation_id,
            evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
            evidence_refs=references_tuple,
            artifact_envelopes=tuple(
                sorted(
                    {
                        item.artifact_envelope_sha256: item
                        for item in envelope_references
                    }.values(),
                    key=lambda item: item.artifact_envelope_sha256,
                )
            ),
            publications=(publication,)
            if publication is not None and succeeded
            else (),
        )
        assert completion is not None
        receipt = RuntimeReceipt.create(
            operation_id=stable_operation_id(dispatch, "attempt"),
            worker_id=dispatch.worker_id,
            attempt_id=dispatch.attempt_id,
            lease_id=dispatch.lease_id,
            fencing_token=dispatch.fencing_token,
            workspace_id=dispatch.workspace_id,
            completion=completion,
            operation_ids=tuple(sorted(context.operation_ids)),
            accepted_input_sha256=tuple(
                item.sha256
                for item in sorted(
                    dispatch.input_publications,
                    key=lambda item: (item.kind, item.id, item.sha256),
                )
            ),
            result=result,
        )
        self._save_receipt(dispatch, receipt)
        self._ensure_terminal_evidence(dispatch, result)
        return WorkerRun(result=result, receipt=receipt)

    async def _reconcile_started_check(
        self, dispatch: Dispatch
    ) -> WorkerRun | None:
        operation_id = stable_operation_id(dispatch, "check")
        path = self._operation_path(operation_id)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if content not in {
            self._operation_record(dispatch, operation_id, "check", "started"),
            self._operation_record(dispatch, operation_id, "check", "completed"),
        }:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)

        normal = self._owned_normal_process(dispatch)
        if normal is not None:
            try:
                await asyncio.to_thread(
                    OwnedProcessRegistry(self.runtime.parent).terminate_owned,
                    normal,
                    retain_record=True,
                )
            except ProcessControlError as error:
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        await self._reconcile_owned_container(dispatch)
        code = (
            RuntimeErrorCode.SANDBOX_UNAVAILABLE
            if isinstance(self.check_runner, DockerCheckRunner)
            else RuntimeErrorCode.RUNTIME_UNAVAILABLE
        )
        reconciled = self.reconcile_cancellation(
            dispatch,
            runtime=self.runtime,
            evidence=self.evidence,
            retryable=True,
            stage="check",
            failure_code=code,
            recorded_at=self.clock(),
        )
        self._clear_normal_process_at(self.runtime, dispatch)
        await self._remove_expired_workspace(dispatch)
        return reconciled

    def execute(self, dispatch: Dispatch) -> AttemptResult:
        return asyncio.run(self.execute_async(dispatch)).result

    def cancel(self, dispatch: Dispatch) -> None:
        async def cleanup() -> None:
            workspace = self._workspace(dispatch)
            operation_id = stable_operation_id(dispatch, "cancel-cleanup")
            await self._fence(dispatch, operation_id, after=False)
            if workspace.exists():
                await asyncio.to_thread(shutil.rmtree, workspace)
            await self._fence(dispatch, operation_id, after=True)

        asyncio.run(cleanup())

    def cancel_and_reconcile(
        self, dispatch: Dispatch, *, retryable: bool = False
    ) -> WorkerRun:
        interruption = None
        process_registry = OwnedProcessRegistry(self.runtime.parent)
        try:
            owned = process_registry.owned_process(
                dispatch, require_live=False, model=True
            )
            normal = process_registry.owned_process(
                dispatch, require_live=False, model=False
            )
            barrier = process_registry.confirm_model_dispatch_barrier(dispatch)
            if normal is not None and normal != owned:
                process_registry.terminate_owned(normal, retain_record=True)
            if owned is not None and (
                owned.model_request_sha256 is not None or barrier is not None
            ):
                requested_model = getattr(
                    self.registry.resolve(dispatch), "requested_model", None
                )
                if not isinstance(requested_model, str):
                    raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
                sent = process_registry.terminate_owned(
                    owned, retain_record=True
                )
                interruption = self.cancellation_interruption(
                    dispatch,
                    owned,
                    barrier,
                    requested_model=requested_model,
                    signal_number=sent,
                )
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        asyncio.run(self._reconcile_owned_container(dispatch))
        self.cancel(dispatch)
        return self.reconcile_cancellation(
            dispatch,
            runtime=self.runtime,
            evidence=self.evidence,
            interruption=interruption,
            retryable=retryable,
            stage=self.cancelled_stage(dispatch.attempt_id),
            recorded_at=self.clock(),
        )

    def finalize_reconciled_attempt(
        self, dispatch: Dispatch, receipt: RuntimeReceipt
    ) -> None:
        """Clear exact process proof after the caller commits this receipt's result."""

        if self._load_receipt(dispatch) != receipt:
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        self._ensure_terminal_evidence(dispatch, receipt.result)
        self._clear_recovered_provider_process(dispatch, receipt.completion)
        self._clear_normal_process_at(self.runtime, dispatch)

    def _owned_normal_process(self, dispatch: Dispatch) -> OwnedProcess | None:
        registry = OwnedProcessRegistry(self.runtime.parent)
        try:
            normal = registry.owned_process(
                dispatch, require_live=False, model=False
            )
            model = registry.owned_process(
                dispatch, require_live=False, model=True
            )
        except ProcessControlError as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        return None if normal == model else normal

    async def _reconcile_owned_container(self, dispatch: Dispatch) -> bool:
        if not isinstance(self.check_runner, DockerCheckRunner):
            return False
        try:
            return await asyncio.to_thread(
                self.check_runner.executor.reconcile_owned,
                dispatch.attempt_id,
            )
        except Exception as error:
            raise RuntimeFailure(RuntimeErrorCode.SANDBOX_UNAVAILABLE) from error


__all__ = [
    "PROVIDER_CALL_TIMESTAMP_PATTERN",
    "WORKER_PROVIDER_RECEIPT_KIND",
    "WORKER_PROVIDER_INTERRUPTION_KIND",
    "AcceptedArtifactResolver",
    "CheckOutcome",
    "CheckRunner",
    "CompletionOutcome",
    "DockerCheckRunner",
    "HostSandboxCheckRunner",
    "RuntimeAssignment",
    "RuntimeErrorCode",
    "RuntimeFailure",
    "RuntimeReceipt",
    "WorkerAdapter",
    "WorkerCapabilities",
    "WorkerCompletion",
    "WorkerContext",
    "WorkerProviderReceipt",
    "WorkerProviderInterruption",
    "WorkerRegistry",
    "WorkerRun",
    "WorkerRuntime",
    "format_provider_call_timestamp",
    "parse_provider_call_timestamp",
    "stable_operation_id",
]
