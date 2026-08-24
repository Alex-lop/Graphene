from __future__ import annotations

import asyncio
import inspect
import os
import re
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
from ..execution.adapter import _FIXED_TEST_COMMAND, ExecutionError, run_fixture_tests
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
from ..models import BoundedText, FrozenModel, Identifier, RepoPath, Sha256, TruthKind
from .diagnostics import CHECK_DIAGNOSTIC_KIND, CheckDiagnostic, summarize_check_failure
from .evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceEventType,
    AttemptEvidenceInput,
    SQLiteAttemptEvidenceStore,
    TrustedCheckReceipt,
)
from .models import (
    ArtifactEnvelopeReferenceV2,
    ArtifactInputReference,
    ArtifactVisibility,
    AttemptResult,
    CommandTemplate,
    Dispatch,
    EvidenceReference,
    GenericEvidenceLink,
    MissionStatus,
    PublishedArtifactReferenceV2,
    PublicationDraft,
    TaskKind,
    artifact_input_reference_key,
)
from .process_control import (
    ControlledProcessRunner,
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
    checks that failed, the digest of its trusted check receipt, and a redacted,
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


class WorkerCompletion(FrozenModel):
    outcome: CompletionOutcome
    result_code: Identifier
    session_id: Identifier
    invocation_id: Identifier
    provider: WorkerProviderReceipt | None = None

    @model_validator(mode="after")
    def code_matches_outcome(self) -> WorkerCompletion:
        allowed = {
            CompletionOutcome.COMPLETED: {"passed"},
            CompletionOutcome.RETRYABLE_FAILURE: {
                RuntimeErrorCode.ACCEPTANCE_CHECK_FAILED.value,
                RuntimeErrorCode.MODEL_OUTPUT_REJECTED.value,
                RuntimeErrorCode.PROVIDER_RATE_LIMITED.value,
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
            result: SandboxResult = await asyncio.to_thread(
                self.executor.execute,
                source=workspace,
                scopes=tuple(
                    sorted(set((*assignment.read_paths, *assignment.output_paths)))
                ),
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
    """Run the frozen ``fixture-tests`` template on the host under sandbox-exec.

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
            tuple(template.argv) != _FIXED_TEST_COMMAND
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
        heartbeat = self.heartbeat
        process_runner = ControlledProcessRunner(
            self.registry,
            dispatch,
            self.status,
            heartbeat=None if heartbeat is None else (lambda: heartbeat(dispatch)),
        )
        try:
            policy = fixture_policy_for(
                workspace, test_timeout_seconds=template.timeout_seconds
            )
        except (ScriptedError, ValidationError) as error:
            # An unrepresentable workspace (for example a path longer than the
            # fixture policy allows) is a deterministic policy condition.
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED) from error
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
        cleanup_complete = not self.registry.has_record(dispatch.attempt_id)
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
        self._baseline: WorkspaceBaseline | None = None
        self._admin_roots: tuple[tuple[str, Path], ...] = ()
        self._workspace_identity: tuple[int, int] | None = None

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
            self._verify_workspace(after=True)
        if non_replayable:
            try:
                self.runtime._complete_nonreplayable(self.dispatch, operation_id, label)
            except Exception as error:
                raise _OutcomeUnknown() from error
        try:
            await self.runtime._fence(self.dispatch, operation_id, after=True)
        except Exception as error:
            raise _OutcomeUnknown() from error
        if action_error is not None:
            raise action_error
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
        path = self._receipt_path(dispatch)
        if not path.exists():
            return None
        try:
            receipt = RuntimeReceipt.model_validate_json(path.read_bytes())
        except (OSError, ValueError) as error:
            raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE) from error
        if (
            receipt.worker_id,
            receipt.attempt_id,
            receipt.lease_id,
            receipt.fencing_token,
            receipt.workspace_id,
        ) != (
            dispatch.worker_id,
            dispatch.attempt_id,
            dispatch.lease_id,
            dispatch.fencing_token,
            dispatch.workspace_id,
        ):
            raise RuntimeFailure(RuntimeErrorCode.POLICY_REJECTED)
        return receipt

    def _save_receipt(self, dispatch: Dispatch, receipt: RuntimeReceipt) -> None:
        target = self._receipt_path(dispatch)
        temporary = target.with_suffix(".tmp-" + receipt.receipt_sha256[:16])
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(receipt.model_dump(mode="json")))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

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

    def _evidence_id(self, dispatch: Dispatch) -> str:
        return (
            "attempt_evidence_"
            + canonical_json_sha256((dispatch.mission_id, dispatch.attempt_id))[:24]
        )

    def _record(
        self,
        dispatch: Dispatch,
        event_type: AttemptEvidenceEventType,
        payload: dict[str, object],
        references: tuple[EvidenceReference, ...] = (),
    ) -> str:
        evidence_id = self._evidence_id(dispatch)
        head = self.evidence.head(evidence_id)
        command_id = (
            "runtime_"
            + canonical_json_sha256(
                (dispatch.attempt_id, event_type.value, head.seq + 1)
            )[:24]
        )
        if event_type == AttemptEvidenceEventType.CHECK_COMPLETED:
            if len(references) != 1:
                raise RuntimeFailure(RuntimeErrorCode.RUNTIME_UNAVAILABLE)
            self.evidence.append_check(
                evidence_id,
                head,
                command_id,
                mission_id=dispatch.mission_id,
                task_id=dispatch.task_id,
                attempt_id=dispatch.attempt_id,
                receipt=references[0],
                payload=payload,
                recorded_at=self.clock(),
            )
        else:
            self.evidence.append(
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
                recorded_at=self.clock(),
            )
        return evidence_id

    async def execute_async(self, dispatch: Dispatch) -> WorkerRun:
        lock = self._attempt_locks.setdefault(dispatch.attempt_id, asyncio.Lock())
        async with lock:
            self._active[dispatch.attempt_id] = dispatch
            try:
                return await self._execute_locked(dispatch)
            finally:
                self._active.pop(dispatch.attempt_id, None)

    async def _execute_locked(self, dispatch: Dispatch) -> WorkerRun:
        recovered = self._load_receipt(dispatch)
        if recovered is not None:
            workspace = self._workspace(dispatch)
            cleanup_id = stable_operation_id(dispatch, "cleanup")
            await self._fence(dispatch, cleanup_id, after=False)
            if workspace.exists():
                await asyncio.to_thread(shutil.rmtree, workspace)
            await self._fence(dispatch, cleanup_id, after=True)
            return WorkerRun(result=recovered.result, receipt=recovered, replayed=True)
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
                    completion = await context._effect(
                        "model", lambda: adapter.execute(context, assignment)
                    )
                finally:
                    self._cancellation_safe_attempts.discard(dispatch.attempt_id)
                if not isinstance(completion, WorkerCompletion):
                    raise RuntimeFailure(RuntimeErrorCode.ADAPTER_REJECTED)
                if completion.provider is not None:
                    # Bind the receipt on success and failure alike so the
                    # terminal evidence event and Attempt.evidence_refs cite it.
                    references.append(
                        await self._store_provider_receipt(
                            context, completion.provider
                        )
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
                RuntimeErrorCode.PROVIDER_TIMEOUT,
                RuntimeErrorCode.PROVIDER_UNAVAILABLE,
                RuntimeErrorCode.RUNTIME_UNAVAILABLE,
                RuntimeErrorCode.SANDBOX_UNAVAILABLE,
            }
            completion = completion or WorkerCompletion(
                outcome=(
                    CompletionOutcome.OUTCOME_UNKNOWN
                    if error.outcome_unknown
                    else CompletionOutcome.RETRYABLE_FAILURE
                    if retryable
                    else CompletionOutcome.TERMINAL_FAILURE
                ),
                result_code=result_code,
                session_id="runtime-" + dispatch.attempt_id[-16:],
                invocation_id=stable_operation_id(dispatch, "failure"),
            )
        except Exception:
            result_code = RuntimeErrorCode.OUTCOME_UNKNOWN.value
            succeeded = retryable = False
            completion = WorkerCompletion(
                outcome=CompletionOutcome.OUTCOME_UNKNOWN,
                result_code=result_code,
                session_id="runtime-" + dispatch.attempt_id[-16:],
                invocation_id=stable_operation_id(dispatch, "failure"),
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
                invocation_id=stable_operation_id(dispatch, "cleanup-failure"),
                provider=completion.provider if completion else None,
            )
        event_type = (
            AttemptEvidenceEventType.ATTEMPT_COMPLETED
            if succeeded
            else AttemptEvidenceEventType.ATTEMPT_FAILED
        )
        evidence_id = self._record(
            dispatch, event_type, {"result_code": result_code}, references_tuple
        )
        result = AttemptResult(
            succeeded=succeeded,
            retryable=retryable,
            result_code=result_code,
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
        return WorkerRun(result=result, receipt=receipt)

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


__all__ = [
    "PROVIDER_CALL_TIMESTAMP_PATTERN",
    "WORKER_PROVIDER_RECEIPT_KIND",
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
    "WorkerRegistry",
    "WorkerRun",
    "WorkerRuntime",
    "format_provider_call_timestamp",
    "parse_provider_call_timestamp",
    "stable_operation_id",
]
