from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Protocol

from ..execution.adapter import (
    FixtureAccessError,
    ScopedFixtureTools,
    run_fixture_tests,
)
from ..hashing import canonical_json_sha256, sha256_hex
from ..models import (
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    FixturePolicy,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    LineageRunState,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from .recovery import quarantine_checkout, recover_interrupted_run
from .reducer import ProjectionError, reduce_events


class LineageStore(Protocol):
    def append(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        idempotency_key: str,
        event_without_server_fields: EventInput,
    ) -> Event: ...

    def tail(self, run_id: str, after_seq: int, limit: int) -> tuple[Event, ...]: ...

    def verify(self, run_id: str) -> VerifiedHead | EvidenceInvalidState: ...


class ArtifactRecorder(Protocol):
    def __call__(
        self, kind: EvidenceKind, record: Mapping[str, Any]
    ) -> EvidenceReference: ...

    def resolve(self, kind: str, artifact_id: str) -> bytes | None: ...


class RuntimeServiceError(RuntimeError):
    pass


class RuntimeAccessDenied(RuntimeServiceError):
    pass


class RuntimeIdentityError(RuntimeServiceError):
    pass


class RuntimeOperationError(RuntimeServiceError):
    pass


class RuntimeTerminalError(RuntimeServiceError):
    pass


class RuntimeIntegrityError(RuntimeServiceError):
    pass


@dataclass(frozen=True, slots=True)
class ToolCallIdentity:
    session_id: str
    invocation_id: str
    model_id: str
    tool_call_id: str
    agent_name: str
    adapter_kind: Literal["adk", "mcp", "local"]


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    reference: EvidenceReference
    content: str
    content_sha256: str

    def __post_init__(self) -> None:
        if sha256_hex(self.content.encode()) != self.content_sha256:
            raise ValueError("evidence content digest does not match")


@dataclass(frozen=True, slots=True)
class SearchMatch:
    path: str
    line_number: int
    line: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    paths: tuple[str, ...]
    matches: tuple[SearchMatch, ...]
    truncated: bool
    evidence_ref: EvidenceReference


@dataclass(frozen=True, slots=True)
class ReadResult:
    path: str
    content: str
    content_sha256: str
    file_version_id: str
    byte_count: int
    line_count: int
    artifact_sha256: str
    state: Literal["PRESENT", "ABSENT"] = "PRESENT"


@dataclass(frozen=True, slots=True)
class EvidenceResult:
    evidence_id: str
    content: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class WriteResult:
    path: str
    before_file_version_id: str | None
    after_file_version_id: str
    after_sha256: str
    added_lines: int
    deleted_lines: int
    state: Literal["EDITED", "NEW"]
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class FixedTestResult:
    passed: bool
    bound_paths: tuple[str, ...]
    exit_code: int
    timed_out: bool
    output: str
    output_sha256: str
    output_byte_count: int
    output_truncated: bool
    duration_bucket: str
    receipt_ref: EvidenceReference


@dataclass(frozen=True, slots=True)
class CompletionDenied:
    attempted_event_id: str
    denied_event_id: str
    reason_code: str = "human_promotion_required"
    state: Literal["NEEDS_HUMAN"] = "NEEDS_HUMAN"


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeHandle:
    run_id: str
    repo_id: str
    base_sha: str
    agent_profile_id: str
    policy_revision: int
    session_id: str
    invocation_id: str
    model_id: str
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]
    tools: tuple[LineageOperation, ...]
    evidence: tuple[EvidenceItem, ...]
    fixed_test_profile: str
    fixture_policy: FixturePolicy
    checkout_root: Path
    initial_head: VerifiedHead
    max_result_bytes: int = 16_384
    max_search_matches: int = 12
    closed: bool = field(default=False, init=False)
    needs_human: bool = field(default=False, init=False)
    _head: VerifiedHead = field(init=False, repr=False, compare=False)
    _invocation_started: Event | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _invocation_finished: Event | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _finished_calls: set[str] = field(
        default_factory=set, init=False, repr=False, compare=False
    )
    _baselines: dict[str, tuple[int, int]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _observed_versions: dict[str, str] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _observed_absences: set[str] = field(
        default_factory=set, init=False, repr=False, compare=False
    )
    _written_versions: dict[str, str] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        root = self.checkout_root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("runtime checkout must be a directory")
        read_scope = tuple(sorted(set(self.read_scope)))
        write_scope = tuple(sorted(set(self.write_scope)))
        tools = tuple(self.tools)
        if not read_scope or not set(write_scope) <= set(read_scope):
            raise ValueError("runtime read/write scope is invalid")
        if (
            not tools
            or not all(isinstance(item, LineageOperation) for item in tools)
            or len(set(tools)) != len(tools)
        ):
            raise ValueError("runtime tools must be unique and nonempty")
        if not set(write_scope) <= set(self.fixture_policy.mutable_paths):
            raise ValueError("runtime write scope exceeds the fixture policy")
        if self.initial_head.run_id != self.run_id:
            raise ValueError("runtime head belongs to another run")
        if len({item.reference.id for item in self.evidence}) != len(self.evidence):
            raise ValueError("runtime evidence IDs must be unique")
        if self.max_result_bytes <= 0 or self.max_search_matches <= 0:
            raise ValueError("runtime result caps must be positive")
        ScopedFixtureTools(
            root,
            allowed_paths=read_scope,
            policy=self.fixture_policy,
        )
        object.__setattr__(self, "checkout_root", root)
        object.__setattr__(self, "read_scope", read_scope)
        object.__setattr__(self, "write_scope", write_scope)
        object.__setattr__(self, "tools", tools)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "_head", self.initial_head)

    @property
    def head(self) -> VerifiedHead:
        return self._head

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._written_versions))


class ScopedApplicationService:
    """One wrapper-authoritative runtime shared by ADK and later MCP."""

    def __init__(self, store: LineageStore, record_artifact: ArtifactRecorder) -> None:
        self.store = store
        self.record_artifact = record_artifact

    def create_handle(self, **identity: Any) -> RuntimeHandle:
        run_id = str(identity["run_id"])
        head = self.store.verify(run_id)
        if isinstance(head, EvidenceInvalidState):
            raise RuntimeIntegrityError("lineage store did not verify the run head")
        events: list[Event] = []
        after_seq = 0
        while after_seq < head.seq:
            batch = self.store.tail(run_id, after_seq, min(256, head.seq - after_seq))
            if not batch:
                raise RuntimeIntegrityError("lineage store returned an incomplete run")
            events.extend(batch)
            after_seq = batch[-1].seq
        try:
            projection = reduce_events(tuple(events))
        except ProjectionError as error:
            raise RuntimeIntegrityError(
                "lineage stream is semantically invalid"
            ) from error
        if (
            len(events) != head.event_count
            or events[-1].event_sha256 != head.event_sha256
        ):
            raise RuntimeIntegrityError(
                "lineage stream does not match its verified head"
            )
        handle = RuntimeHandle(initial_head=head, **identity)
        handle._finished_calls.update(
            event.tool_call_id
            for event in events
            if event.tool_call_id is not None
            and event.event_type
            in {LineageEventType.TOOL_COMPLETED, LineageEventType.TOOL_FAILED}
        )
        for event in events:
            if (
                event.event_type != LineageEventType.TOOL_COMPLETED
                or event.invocation_id != handle.invocation_id
            ):
                continue
            operation = event.payload.get("operation")
            path = event.payload.get("path")
            if operation == LineageOperation.READ_FILE and isinstance(path, str):
                version = event.payload.get("file_version_id")
                if event.payload.get("state") == "ABSENT":
                    handle._observed_absences.add(path)
                elif isinstance(version, str):
                    handle._observed_versions[path] = version
                byte_count = event.payload.get("byte_count")
                line_count = event.payload.get("line_count")
                if isinstance(byte_count, int) and isinstance(line_count, int):
                    handle._baselines.setdefault(path, (byte_count, line_count))
            elif operation == LineageOperation.WRITE_FILE and isinstance(path, str):
                version = event.payload.get("after_file_version_id")
                if isinstance(version, str):
                    handle._written_versions[path] = version
                    handle._observed_versions[path] = version
                byte_count = event.payload.get("baseline_bytes")
                line_count = event.payload.get("baseline_lines")
                if isinstance(byte_count, int) and isinstance(line_count, int):
                    handle._baselines.setdefault(path, (byte_count, line_count))
        started = next(
            (
                event
                for event in reversed(events)
                if event.event_type == LineageEventType.INVOCATION_STARTED
                and event.invocation_id == handle.invocation_id
            ),
            None,
        )
        finished = next(
            (
                event
                for event in reversed(events)
                if event.event_type
                in {
                    LineageEventType.INVOCATION_COMPLETED,
                    LineageEventType.INVOCATION_FAILED,
                }
                and event.invocation_id == handle.invocation_id
            ),
            None,
        )
        unfinished_calls = {
            event.tool_call_id
            for event in events
            if event.event_type == LineageEventType.TOOL_STARTED
        } - handle._finished_calls
        if unfinished_calls or (
            started is not None
            and finished is None
            and projection.state != LineageRunState.NEEDS_HUMAN
        ):
            raise RuntimeIntegrityError("runtime has an unfinished durable dispatch")
        object.__setattr__(handle, "_invocation_started", started)
        object.__setattr__(handle, "_invocation_finished", finished)
        if projection.state == LineageRunState.NEEDS_HUMAN:
            object.__setattr__(handle, "needs_human", True)
        elif (
            projection.state
            in {
                LineageRunState.ACCESS_DENIED,
                LineageRunState.FAILED,
                LineageRunState.INTERRUPTED,
                LineageRunState.PROMOTED,
                LineageRunState.REJECTED,
            }
            or finished is not None
        ):
            object.__setattr__(handle, "closed", True)
        return handle

    def ensure_invocation_started(
        self,
        handle: RuntimeHandle,
        *,
        session_id: str,
        invocation_id: str,
        model_id: str,
        adapter_kind: Literal["adk", "mcp"] = "adk",
        framework_version: str | None = None,
        adk_version: str | None = None,
    ) -> Event:
        with handle._lock:
            self._validate_invocation(
                handle,
                session_id=session_id,
                invocation_id=invocation_id,
                model_id=model_id,
            )
            if handle._invocation_started is not None:
                if (
                    handle._invocation_started.payload.get("adapter_kind")
                    != adapter_kind
                ):
                    raise RuntimeIdentityError("runtime adapter identity changed")
                return handle._invocation_started
            self._ensure_active(handle)
            if framework_version is None:
                framework_version = adk_version
            if not framework_version:
                raise RuntimeIdentityError("runtime framework version is missing")
            authority, evidence_kind, source_kind = self._adapter_provenance(
                adapter_kind
            )
            payload = {
                "adapter_kind": adapter_kind,
                "framework": "google_adk" if adapter_kind == "adk" else "mcp",
                "framework_version": framework_version,
                "status": "started",
            }
            source = self._source(
                evidence_kind,
                source_kind,
                self._receipt_record(
                    handle,
                    phase="invocation.started",
                    payload=payload,
                ),
            )
            event = self._append(
                handle,
                self._key(handle, "invocation.started"),
                EventInput(
                    session_id=handle.session_id,
                    invocation_id=handle.invocation_id,
                    model_id=handle.model_id,
                    tool_call_id=None,
                    repo_id=handle.repo_id,
                    base_sha=handle.base_sha,
                    agent_profile_id=handle.agent_profile_id,
                    policy_revision=handle.policy_revision,
                    event_type=LineageEventType.INVOCATION_STARTED,
                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                    authority=authority,
                    references=(),
                    source_ref=source,
                    payload=payload,
                ),
            )
            object.__setattr__(handle, "_invocation_started", event)
            return event

    def complete_invocation(
        self,
        handle: RuntimeHandle,
        *,
        session_id: str,
        invocation_id: str,
        returned_model_id: str,
    ) -> Event | None:
        with handle._lock:
            self._validate_invocation(
                handle,
                session_id=session_id,
                invocation_id=invocation_id,
                model_id=handle.model_id,
            )
            if handle.needs_human:
                return None
            self._ensure_started(handle)
            if handle._invocation_finished is not None:
                return handle._invocation_finished
            if returned_model_id != handle.model_id:
                raise RuntimeIdentityError(
                    "returned model identity does not match runtime"
                )
            payload = {"adapter_kind": "adk", "status": "completed"}
            source = self._source(
                EvidenceKind.ADK_EVENT_RECEIPT,
                SourceKind.ADK_EVENT_RECEIPT,
                self._receipt_record(
                    handle,
                    phase="invocation.completed",
                    payload=payload,
                    model_id=returned_model_id,
                ),
            )
            event = self._append(
                handle,
                self._key(handle, "invocation.completed"),
                EventInput(
                    session_id=session_id,
                    invocation_id=invocation_id,
                    model_id=returned_model_id,
                    tool_call_id=None,
                    repo_id=handle.repo_id,
                    base_sha=handle.base_sha,
                    agent_profile_id=handle.agent_profile_id,
                    policy_revision=handle.policy_revision,
                    event_type=LineageEventType.INVOCATION_COMPLETED,
                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                    authority=LineageAuthority.ADK_ADAPTER,
                    references=(),
                    source_ref=source,
                    payload=payload,
                ),
            )
            object.__setattr__(handle, "_invocation_finished", event)
            object.__setattr__(handle, "closed", True)
            return event

    def fail_invocation(
        self,
        handle: RuntimeHandle,
        *,
        session_id: str,
        invocation_id: str,
        error: Exception,
    ) -> Event | None:
        with handle._lock:
            self._validate_invocation(
                handle,
                session_id=session_id,
                invocation_id=invocation_id,
                model_id=handle.model_id,
            )
            if handle.needs_human:
                return None
            self._ensure_started(handle)
            if handle._invocation_finished is not None:
                return handle._invocation_finished
            payload = {
                "adapter_kind": "adk",
                "error_code": self._error_code(error),
                "status": "failed",
            }
            source = self._source(
                EvidenceKind.ADK_EVENT_RECEIPT,
                SourceKind.ADK_EVENT_RECEIPT,
                self._receipt_record(
                    handle,
                    phase="invocation.failed",
                    payload=payload,
                ),
            )
            event = self._append(
                handle,
                self._key(handle, "invocation.failed"),
                EventInput(
                    session_id=session_id,
                    invocation_id=invocation_id,
                    model_id=handle.model_id,
                    tool_call_id=None,
                    repo_id=handle.repo_id,
                    base_sha=handle.base_sha,
                    agent_profile_id=handle.agent_profile_id,
                    policy_revision=handle.policy_revision,
                    event_type=LineageEventType.INVOCATION_FAILED,
                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                    authority=LineageAuthority.ADK_ADAPTER,
                    references=(),
                    source_ref=source,
                    payload=payload,
                ),
            )
            object.__setattr__(handle, "_invocation_finished", event)
            object.__setattr__(handle, "closed", True)
            return event

    def search_repo(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        *,
        query: str,
    ) -> SearchResult:
        operation = LineageOperation.SEARCH_REPO
        with handle._lock:
            self._authorize(handle, call, operation, operation in handle.tools)
            self._started(handle, call, operation)
            try:
                if not query or len(query.encode()) > 1_024:
                    raise ValueError("query must contain 1 to 1024 UTF-8 bytes")
                matches: list[SearchMatch] = []
                truncated = False
                used = 0
                tools = self._tools(handle)
                for path in handle.read_scope:
                    try:
                        content = tools.read_file(path)
                    except FixtureAccessError:
                        target = handle.checkout_root.joinpath(*path.split("/"))
                        if target.exists():
                            raise
                        continue
                    for number, line in enumerate(content.splitlines(), 1):
                        if query not in line:
                            continue
                        rendered = self._bounded_text(line, 512)
                        cost = len(path.encode()) + len(rendered.encode()) + 16
                        if (
                            len(matches) >= handle.max_search_matches
                            or used + cost > handle.max_result_bytes
                        ):
                            truncated = True
                            break
                        matches.append(SearchMatch(path, number, rendered))
                        used += cost
                    if truncated:
                        break
                paths = tuple(sorted({item.path for item in matches}))
                search_record = {
                    "schema_version": 2,
                    "query_sha256": sha256_hex(query.encode()),
                    "matches": [
                        {
                            "path": item.path,
                            "line_number": item.line_number,
                            "line": item.line,
                        }
                        for item in matches
                    ],
                    "truncated": truncated,
                }
                result_ref = self._record(EvidenceKind.EVIDENCE_BLOB, search_record)
                payload = {
                    "operation": operation.value,
                    "status": "completed",
                    "paths": list(paths),
                    "match_count": len(matches),
                    "truncated": truncated,
                }
                self._complete(handle, call, operation, payload, (result_ref,))
                return SearchResult(paths, tuple(matches), truncated, result_ref)
            except Exception as error:
                self._fail(handle, call, operation, error)

    def read_file(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        *,
        path: str,
    ) -> ReadResult:
        operation = LineageOperation.READ_FILE
        with handle._lock:
            self._authorize(
                handle,
                call,
                operation,
                operation in handle.tools and path in handle.read_scope,
            )
            self._started(handle, call, operation)
            try:
                tools = self._tools(handle)
                if tools.is_absent(path):
                    content_sha256 = sha256_hex(b"")
                    file_id = sha256_hex(f"{handle.repo_id}\0{path}".encode())
                    version_id = sha256_hex(f"{file_id}\0ABSENT".encode())
                    reference = self._record(
                        EvidenceKind.EVIDENCE_BLOB,
                        {
                            "schema_version": 2,
                            "repo_id": handle.repo_id,
                            "path": path,
                            "state": "ABSENT",
                            "file_version_id": version_id,
                            "content_sha256": content_sha256,
                            "byte_count": 0,
                            "line_count": 0,
                        },
                    )
                    payload = {
                        "operation": operation.value,
                        "status": "completed",
                        "state": "ABSENT",
                        "path": path,
                        "file_version_id": version_id,
                        "byte_count": 0,
                        "line_count": 0,
                    }
                    self._complete(handle, call, operation, payload, (reference,))
                    handle._observed_absences.add(path)
                    handle._baselines.setdefault(path, (0, 0))
                    return ReadResult(
                        path=path,
                        content="",
                        content_sha256=content_sha256,
                        file_version_id=version_id,
                        byte_count=0,
                        line_count=0,
                        artifact_sha256=reference.sha256,
                        state="ABSENT",
                    )
                content = tools.read_file(path)
                metadata, reference = self._file_version(handle, path, content)
                payload = {
                    "operation": operation.value,
                    "status": "completed",
                    "path": path,
                    "file_version_id": metadata["file_version_id"],
                    "byte_count": metadata["byte_count"],
                    "line_count": metadata["line_count"],
                }
                self._complete(handle, call, operation, payload, (reference,))
                handle._baselines.setdefault(
                    path,
                    (int(metadata["byte_count"]), int(metadata["line_count"])),
                )
                handle._observed_versions[path] = str(metadata["file_version_id"])
                handle._observed_absences.discard(path)
                return ReadResult(
                    path=path,
                    content=content,
                    content_sha256=str(metadata["content_sha256"]),
                    file_version_id=str(metadata["file_version_id"]),
                    byte_count=int(metadata["byte_count"]),
                    line_count=int(metadata["line_count"]),
                    artifact_sha256=reference.sha256,
                )
            except Exception as error:
                self._fail(handle, call, operation, error)

    def open_evidence(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        *,
        evidence_id: str,
    ) -> EvidenceResult:
        operation = LineageOperation.OPEN_EVIDENCE
        with handle._lock:
            item = next(
                (
                    value
                    for value in handle.evidence
                    if value.reference.id == evidence_id
                ),
                None,
            )
            self._authorize(
                handle,
                call,
                operation,
                operation in handle.tools and item is not None,
            )
            self._started(handle, call, operation)
            try:
                assert item is not None
                payload = {
                    "operation": operation.value,
                    "status": "completed",
                    "evidence_id": evidence_id,
                    "content_sha256": item.content_sha256,
                    "byte_count": len(item.content.encode()),
                }
                self._complete(
                    handle,
                    call,
                    operation,
                    payload,
                    (item.reference,),
                )
                return EvidenceResult(evidence_id, item.content, item.content_sha256)
            except Exception as error:
                self._fail(handle, call, operation, error)

    def write_file(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        *,
        path: str,
        content: str,
    ) -> WriteResult:
        operation = LineageOperation.WRITE_FILE
        with handle._lock:
            tools = self._tools(handle)
            allowed = (
                operation in handle.tools
                and path in handle.write_scope
                and (
                    path in handle._observed_versions
                    or path in handle._observed_absences
                )
            )
            before: str | None = None
            before_sha256: str | None = None
            if allowed:
                if path in handle._observed_absences:
                    allowed = tools.is_absent(path)
                else:
                    try:
                        before = tools.read_file(path)
                    except FixtureAccessError:
                        allowed = False
                    else:
                        before_sha256 = sha256_hex(before.encode())
                        file_id = sha256_hex(f"{handle.repo_id}\0{path}".encode())
                        allowed = (
                            sha256_hex(f"{file_id}\0{before_sha256}".encode())
                            == handle._observed_versions[path]
                        )
            self._authorize(
                handle,
                call,
                operation,
                allowed,
                reason_code=(
                    "stale_file_version"
                    if path in handle._observed_versions
                    or path in handle._observed_absences
                    else "read_required"
                ),
            )
            self._started(handle, call, operation)
            try:
                before_metadata: dict[str, Any] | None = None
                before_ref: EvidenceReference | None = None
                if before is not None:
                    assert before_sha256 is not None
                    before_metadata, before_ref = self._file_version(
                        handle, path, before
                    )
                after_metadata, after_ref = self._file_version(handle, path, content)
                after_sha256 = tools.write_file(
                    path,
                    content,
                    expected_sha256=before_sha256,
                    expected_absent=before is None,
                )
                added, deleted = self._line_changes(before, content)
                state = "NEW" if before is None else "EDITED"
                baseline = handle._baselines.get(path)
                if baseline is None:
                    baseline = (
                        0
                        if before_metadata is None
                        else int(before_metadata["byte_count"]),
                        0
                        if before_metadata is None
                        else int(before_metadata["line_count"]),
                    )
                payload = {
                    "operation": operation.value,
                    "status": "completed",
                    "path": path,
                    "before_file_version_id": (
                        None
                        if before_metadata is None
                        else before_metadata["file_version_id"]
                    ),
                    "after_file_version_id": after_metadata["file_version_id"],
                    "baseline_bytes": baseline[0],
                    "baseline_lines": baseline[1],
                    "added_lines": added,
                    "deleted_lines": deleted,
                    "state": state,
                }
                references = self._unique_refs(before_ref, after_ref)
                self._complete(handle, call, operation, payload, references)
                handle._baselines.setdefault(path, baseline)
                handle._written_versions[path] = str(after_metadata["file_version_id"])
                handle._observed_versions[path] = str(after_metadata["file_version_id"])
                handle._observed_absences.discard(path)
                return WriteResult(
                    path=path,
                    before_file_version_id=(
                        None
                        if before_metadata is None
                        else str(before_metadata["file_version_id"])
                    ),
                    after_file_version_id=str(after_metadata["file_version_id"]),
                    after_sha256=after_sha256,
                    added_lines=added,
                    deleted_lines=deleted,
                    state=state,
                    artifact_sha256=after_ref.sha256,
                )
            except Exception as error:
                self._interrupt_mutated_checkout(handle, error)

    def run_fixed_test(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
    ) -> FixedTestResult:
        operation = LineageOperation.RUN_FIXED_TEST
        with handle._lock:
            self._authorize(handle, call, operation, operation in handle.tools)
            self._started(handle, call, operation)
            try:
                test = run_fixture_tests(handle.checkout_root, handle.fixture_policy)
                output_sha256 = sha256_hex(test.output.encode())
                output_ref = self._record(
                    EvidenceKind.EVIDENCE_BLOB,
                    {
                        "schema_version": 2,
                        "content": test.output,
                        "content_sha256": output_sha256,
                    },
                )
                passed = not test.timed_out and test.exit_code == 0
                bound_paths = handle.changed_paths
                candidate_digest = canonical_json_sha256(
                    dict(sorted(handle._written_versions.items()))
                )
                receipt_record = {
                    "schema_version": 2,
                    "required_test_profile": handle.fixed_test_profile,
                    "command": list(handle.fixture_policy.fixed_test_command),
                    "passed": passed,
                    "exit_code": test.exit_code,
                    "timed_out": test.timed_out,
                    "output_sha256": output_sha256,
                    "output_byte_count": len(test.output.encode()),
                    "output_truncated": test.output_truncated,
                    "duration_bucket": test.duration_bucket,
                    "bound_paths": list(bound_paths),
                    "candidate_written_versions_sha256": candidate_digest,
                    "output_ref": output_ref.model_dump(mode="json"),
                }
                receipt_ref = self._record(EvidenceKind.TEST_RECEIPT, receipt_record)
                payload = {
                    "operation": operation.value,
                    "status": "completed",
                    "passed": passed,
                    "bound_paths": list(bound_paths),
                    "candidate_written_versions_sha256": candidate_digest,
                    "exit_code": test.exit_code,
                    "timed_out": test.timed_out,
                    "output_sha256": output_sha256,
                    "output_byte_count": len(test.output.encode()),
                    "output_truncated": test.output_truncated,
                    "duration_bucket": test.duration_bucket,
                }
                self._complete(
                    handle,
                    call,
                    operation,
                    payload,
                    (receipt_ref, output_ref),
                )
                return FixedTestResult(
                    passed=passed,
                    bound_paths=bound_paths,
                    exit_code=test.exit_code,
                    timed_out=test.timed_out,
                    output=test.output,
                    output_sha256=output_sha256,
                    output_byte_count=len(test.output.encode()),
                    output_truncated=test.output_truncated,
                    duration_bucket=test.duration_bucket,
                    receipt_ref=receipt_ref,
                )
            except Exception as error:
                self._fail(handle, call, operation, error)

    def request_completion(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
    ) -> CompletionDenied:
        operation = LineageOperation.REQUEST_COMPLETION
        with handle._lock:
            self._authorize(handle, call, operation, operation in handle.tools)
            attempted_payload = {
                "adapter_kind": call.adapter_kind,
                "operation": operation.value,
                "status": "attempted",
            }
            authority, evidence_kind, source_kind = self._adapter_provenance(
                call.adapter_kind
            )
            attempted_source = self._source(
                evidence_kind,
                source_kind,
                self._receipt_record(
                    handle,
                    phase="completion.attempted",
                    call=call,
                    payload=attempted_payload,
                ),
            )
            attempted = self._append(
                handle,
                self._key(handle, "completion.attempted", call),
                self._input(
                    handle,
                    call,
                    event_type=LineageEventType.COMPLETION_ATTEMPTED,
                    truth_kind=TruthKind.MODEL_PROPOSED,
                    authority=authority,
                    source_ref=attempted_source,
                    payload=attempted_payload,
                ),
            )
            denied_payload = {
                "operation": operation.value,
                "status": "denied",
                "reason_code": "human_promotion_required",
                "state": "NEEDS_HUMAN",
            }
            denied_source = self._source(
                EvidenceKind.POLICY_RECEIPT,
                SourceKind.POLICY_EVALUATION,
                self._receipt_record(
                    handle,
                    phase="completion.denied",
                    call=call,
                    payload=denied_payload,
                ),
            )
            try:
                denied = self._append(
                    handle,
                    self._key(handle, "completion.denied", call),
                    self._input(
                        handle,
                        call,
                        event_type=LineageEventType.COMPLETION_DENIED,
                        truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                        authority=LineageAuthority.POLICY_ENGINE,
                        source_ref=denied_source,
                        payload=denied_payload,
                        references=(
                            EvidenceReference(
                                kind=EvidenceKind.EVENT,
                                id=attempted.event_id,
                                sha256=attempted.event_sha256,
                            ),
                        ),
                    ),
                )
            except Exception:
                object.__setattr__(handle, "closed", True)
                raise
            handle._finished_calls.add(call.tool_call_id)
            object.__setattr__(handle, "needs_human", True)
            return CompletionDenied(attempted.event_id, denied.event_id)

    def _authorize(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        operation: LineageOperation,
        allowed: bool,
        reason_code: str = "outside_runtime_scope",
    ) -> None:
        self._validate_call(handle, call)
        self._ensure_active(handle)
        if call.adapter_kind != "local":
            self._ensure_started(handle)
        self._ensure_new_call(handle, call)
        if allowed:
            return
        payload = {
            "operation": operation.value,
            "status": "denied",
            "reason_code": reason_code,
        }
        source = self._source(
            EvidenceKind.POLICY_RECEIPT,
            SourceKind.POLICY_EVALUATION,
            self._receipt_record(
                handle,
                phase="scope.denied",
                call=call,
                payload=payload,
            ),
        )
        self._append(
            handle,
            self._key(handle, f"{operation.value}.scope.denied", call),
            self._input(
                handle,
                call,
                event_type=LineageEventType.SCOPE_DENIED,
                truth_kind=TruthKind.POLICY_AUTHORITATIVE,
                authority=LineageAuthority.POLICY_ENGINE,
                source_ref=source,
                payload=payload,
            ),
        )
        handle._finished_calls.add(call.tool_call_id)
        object.__setattr__(handle, "closed", True)
        raise RuntimeAccessDenied("operation denied by runtime scope")

    def _started(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        operation: LineageOperation,
    ) -> Event:
        payload = {"operation": operation.value, "status": "started"}
        source = self._source(
            EvidenceKind.TOOL_RECEIPT,
            SourceKind.TOOL_RECEIPT,
            self._receipt_record(
                handle,
                phase="tool.started",
                call=call,
                payload=payload,
            ),
        )
        return self._append(
            handle,
            self._key(handle, f"{operation.value}.started", call),
            self._input(
                handle,
                call,
                event_type=LineageEventType.TOOL_STARTED,
                truth_kind=TruthKind.RUNTIME_OBSERVED,
                authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
                source_ref=source,
                payload=payload,
            ),
        )

    def _complete(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        operation: LineageOperation,
        payload: dict[str, Any],
        references: tuple[EvidenceReference, ...],
    ) -> Event:
        source = self._source(
            EvidenceKind.TOOL_RECEIPT,
            SourceKind.TOOL_RECEIPT,
            self._receipt_record(
                handle,
                phase="tool.completed",
                call=call,
                payload=payload,
                references=references,
            ),
        )
        event = self._append(
            handle,
            self._key(handle, f"{operation.value}.completed", call),
            self._input(
                handle,
                call,
                event_type=LineageEventType.TOOL_COMPLETED,
                truth_kind=TruthKind.RUNTIME_OBSERVED,
                authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
                source_ref=source,
                payload=payload,
                references=references,
            ),
        )
        handle._finished_calls.add(call.tool_call_id)
        return event

    def _fail(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        operation: LineageOperation,
        error: Exception,
    ) -> None:
        if handle.closed:
            raise error
        payload = {
            "operation": operation.value,
            "status": "failed",
            "error_code": self._error_code(error),
        }
        try:
            source = self._source(
                EvidenceKind.TOOL_RECEIPT,
                SourceKind.TOOL_RECEIPT,
                self._receipt_record(
                    handle,
                    phase="tool.failed",
                    call=call,
                    payload=payload,
                ),
            )
            self._append(
                handle,
                self._key(handle, f"{operation.value}.failed", call),
                self._input(
                    handle,
                    call,
                    event_type=LineageEventType.TOOL_FAILED,
                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                    authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
                    source_ref=source,
                    payload=payload,
                ),
            )
        except Exception:
            object.__setattr__(handle, "closed", True)
            raise
        handle._finished_calls.add(call.tool_call_id)
        raise RuntimeOperationError(f"{operation.value} failed") from error

    def _interrupt_mutated_checkout(
        self,
        handle: RuntimeHandle,
        error: Exception,
    ) -> None:
        object.__setattr__(handle, "closed", True)

        def record_source(record: Mapping[str, Any]) -> SourceReference:
            reference = self._record(EvidenceKind.OPERATOR_REQUEST, record)
            return SourceReference(
                kind=SourceKind.LIFECYCLE_REQUEST,
                id=reference.id,
                sha256=reference.sha256,
            )

        try:
            interrupted = recover_interrupted_run(
                self.store,
                run_id=handle.run_id,
                checkout_path=handle.checkout_root,
                record_source=record_source,
            )
        except Exception as recovery_error:
            try:
                quarantine_checkout(handle.run_id, handle.checkout_root)
            except Exception as quarantine_error:
                raise RuntimeIntegrityError(
                    "mutated checkout could not be durably interrupted or quarantined"
                ) from quarantine_error
            raise RuntimeIntegrityError(
                "mutated checkout was quarantined without a durable interruption"
            ) from recovery_error
        if interrupted is None:
            raise RuntimeIntegrityError(
                "mutated checkout lacked an uncertain tool start"
            )
        object.__setattr__(
            handle,
            "_head",
            VerifiedHead(
                run_id=handle.run_id,
                seq=interrupted.seq,
                event_sha256=interrupted.event_sha256,
                event_count=interrupted.seq,
            ),
        )
        raise RuntimeIntegrityError(
            "write persistence failed after mutation; run interrupted"
        ) from error

    def _input(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
        *,
        event_type: LineageEventType,
        truth_kind: TruthKind,
        authority: LineageAuthority,
        source_ref: SourceReference,
        payload: dict[str, Any],
        references: tuple[EvidenceReference, ...] = (),
    ) -> EventInput:
        return EventInput(
            session_id=call.session_id,
            invocation_id=call.invocation_id,
            model_id=call.model_id,
            tool_call_id=call.tool_call_id,
            repo_id=handle.repo_id,
            base_sha=handle.base_sha,
            agent_profile_id=handle.agent_profile_id,
            policy_revision=handle.policy_revision,
            event_type=event_type,
            truth_kind=truth_kind,
            authority=authority,
            references=references,
            source_ref=source_ref,
            payload=payload,
        )

    def _append(
        self,
        handle: RuntimeHandle,
        key: str,
        event_input: EventInput,
    ) -> Event:
        previous = handle.head
        try:
            event = self.store.append(handle.run_id, previous, key, event_input)
        except Exception:
            object.__setattr__(handle, "closed", True)
            raise
        if (
            event.run_id != handle.run_id
            or event.seq != previous.seq + 1
            or event.previous_event_sha256 != previous.event_sha256
        ):
            object.__setattr__(handle, "closed", True)
            raise RuntimeIntegrityError("lineage store returned a non-successor event")
        object.__setattr__(
            handle,
            "_head",
            VerifiedHead(
                run_id=handle.run_id,
                seq=event.seq,
                event_sha256=event.event_sha256,
                event_count=event.seq,
            ),
        )
        return event

    def _record(
        self,
        kind: EvidenceKind,
        record: Mapping[str, Any],
    ) -> EvidenceReference:
        reference = self.record_artifact(kind, record)
        if reference.kind != kind or reference.sha256 != canonical_json_sha256(record):
            raise RuntimeIntegrityError(
                "artifact recorder returned a mismatched digest"
            )
        return reference

    def _source(
        self,
        evidence_kind: EvidenceKind,
        source_kind: SourceKind,
        record: Mapping[str, Any],
    ) -> SourceReference:
        reference = self._record(evidence_kind, record)
        return SourceReference(
            kind=source_kind,
            id=reference.id,
            sha256=reference.sha256,
        )

    @staticmethod
    def _receipt_record(
        handle: RuntimeHandle,
        *,
        phase: str,
        payload: Mapping[str, Any],
        call: ToolCallIdentity | None = None,
        model_id: str | None = None,
        references: tuple[EvidenceReference, ...] = (),
    ) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "run_id": handle.run_id,
            "session_id": handle.session_id,
            "invocation_id": handle.invocation_id,
            "model_id": handle.model_id if model_id is None else model_id,
            "agent_name": None if call is None else call.agent_name,
            "tool_call_id": None if call is None else call.tool_call_id,
            "phase": phase,
            "payload": dict(payload),
            "references": [item.model_dump(mode="json") for item in references],
        }

    def _file_version(
        self,
        handle: RuntimeHandle,
        path: str,
        content: str,
    ) -> tuple[dict[str, Any], EvidenceReference]:
        raw = content.encode()
        content_sha256 = sha256_hex(raw)
        file_id = sha256_hex(f"{handle.repo_id}\0{path}".encode())
        metadata: dict[str, Any] = {
            "schema_version": 2,
            "file_id": file_id,
            "file_version_id": sha256_hex(f"{file_id}\0{content_sha256}".encode()),
            "repo_id": handle.repo_id,
            "path": path,
            "content_sha256": content_sha256,
            "byte_count": len(raw),
            "line_count": len(content.splitlines()),
        }
        reference = self._record(
            EvidenceKind.FILE_VERSION,
            {**metadata, "content": content},
        )
        metadata["artifact_sha256"] = reference.sha256
        return metadata, reference

    def _tools(self, handle: RuntimeHandle) -> ScopedFixtureTools:
        return ScopedFixtureTools(
            handle.checkout_root,
            allowed_paths=handle.read_scope,
            policy=handle.fixture_policy,
        )

    @staticmethod
    def _line_changes(before: str | None, after: str) -> tuple[int, int]:
        old = [] if before is None else before.splitlines(keepends=True)
        new = after.splitlines(keepends=True)
        added = deleted = 0
        for tag, old_start, old_end, new_start, new_end in SequenceMatcher(
            None, old, new, autojunk=False
        ).get_opcodes():
            if tag in {"replace", "delete"}:
                deleted += old_end - old_start
            if tag in {"replace", "insert"}:
                added += new_end - new_start
        return added, deleted

    @staticmethod
    def _bounded_text(value: str, byte_cap: int) -> str:
        raw = value.encode()
        return value if len(raw) <= byte_cap else raw[:byte_cap].decode(errors="ignore")

    @staticmethod
    def _unique_refs(
        *references: EvidenceReference | None,
    ) -> tuple[EvidenceReference, ...]:
        by_key = {
            (item.kind, item.id, item.sha256): item
            for item in references
            if item is not None
        }
        return tuple(
            by_key[key]
            for key in sorted(by_key, key=lambda item: tuple(map(str, item)))
        )

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, FixtureAccessError):
            return "fixture_access_error"
        if isinstance(error, UnicodeError):
            return "invalid_utf8"
        if isinstance(error, ValueError):
            return "invalid_input"
        return "operation_error"

    @staticmethod
    def _key(
        handle: RuntimeHandle,
        phase: str,
        call: ToolCallIdentity | None = None,
    ) -> str:
        return sha256_hex(
            "\0".join(
                (
                    handle.run_id,
                    handle.invocation_id,
                    "no_tool" if call is None else call.tool_call_id,
                    phase,
                )
            ).encode()
        )

    @staticmethod
    def _validate_invocation(
        handle: RuntimeHandle,
        *,
        session_id: str,
        invocation_id: str,
        model_id: str,
    ) -> None:
        if (session_id, invocation_id, model_id) != (
            handle.session_id,
            handle.invocation_id,
            handle.model_id,
        ):
            raise RuntimeIdentityError("runtime invocation identity mismatch")

    def _validate_call(
        self,
        handle: RuntimeHandle,
        call: ToolCallIdentity,
    ) -> None:
        self._validate_invocation(
            handle,
            session_id=call.session_id,
            invocation_id=call.invocation_id,
            model_id=call.model_id,
        )
        if not call.tool_call_id:
            raise RuntimeIdentityError("tool call identity is missing")

    @staticmethod
    def _ensure_active(handle: RuntimeHandle) -> None:
        if handle.closed or handle.needs_human:
            raise RuntimeTerminalError("runtime invocation is terminal")

    @staticmethod
    def _ensure_started(handle: RuntimeHandle) -> None:
        if handle._invocation_started is None:
            raise RuntimeIntegrityError("runtime invocation was not durably started")

    @staticmethod
    def _adapter_provenance(
        adapter_kind: Literal["adk", "mcp", "local"],
    ) -> tuple[LineageAuthority, EvidenceKind, SourceKind]:
        return {
            "adk": (
                LineageAuthority.ADK_ADAPTER,
                EvidenceKind.ADK_EVENT_RECEIPT,
                SourceKind.ADK_EVENT_RECEIPT,
            ),
            "mcp": (
                LineageAuthority.MCP_ADAPTER,
                EvidenceKind.MCP_REQUEST_RECEIPT,
                SourceKind.MCP_REQUEST_RECEIPT,
            ),
            "local": (
                LineageAuthority.LOCAL_ADAPTER,
                EvidenceKind.LOCAL_ADAPTER_RECEIPT,
                SourceKind.LOCAL_ADAPTER_RECEIPT,
            ),
        }[adapter_kind]

    @staticmethod
    def _ensure_new_call(
        handle: RuntimeHandle,
        call: ToolCallIdentity,
    ) -> None:
        if call.tool_call_id in handle._finished_calls:
            raise RuntimeIdentityError("tool call identity was already consumed")


__all__ = [
    "ArtifactRecorder",
    "CompletionDenied",
    "EvidenceItem",
    "EvidenceResult",
    "FixedTestResult",
    "LineageStore",
    "ReadResult",
    "RuntimeAccessDenied",
    "RuntimeHandle",
    "RuntimeIdentityError",
    "RuntimeIntegrityError",
    "RuntimeOperationError",
    "RuntimeServiceError",
    "RuntimeTerminalError",
    "ScopedApplicationService",
    "SearchMatch",
    "SearchResult",
    "ToolCallIdentity",
    "WriteResult",
]
