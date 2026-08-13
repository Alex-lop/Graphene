from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import TypeAdapter, ValidationError

from ..hashing import canonical_json_sha256
from ..models import (
    Event,
    EvidenceInvalidState,
    LineageEventType,
    LineageOperation,
    LineageProjection,
    LineageRunState,
    ProjectionEvent,
    ProjectionFile,
    ProjectionObligation,
    RepoPath,
)

MAX_VISIBLE_FILES = 15
MAX_VISIBLE_EVENTS = 1_000
UNKNOWNS = (
    "Timing does not prove causality.",
    "Whole-repository impact is unknown.",
)
_PATH = TypeAdapter(RepoPath)


class ProjectionError(ValueError):
    """A verified-stream precondition failed during defensive reduction."""

    state = LineageRunState.EVIDENCE_INVALID

    def __init__(self, reason: str, *, run_id: str | None = None, seq: int | None = None):
        super().__init__(reason)
        self.run_id = run_id
        self.first_invalid_seq = seq

    def as_state(self) -> EvidenceInvalidState:
        return EvidenceInvalidState(
            run_id=self.run_id or "unknown_run",
            first_invalid_seq=self.first_invalid_seq,
            reason=str(self),
        )


@dataclass(slots=True)
class _File:
    path: str
    state: str
    file_version_id: str | None
    baseline_bytes: int | None
    baseline_lines: int | None
    first_seq: int
    last_seq: int
    read_count: int = 0
    added_lines: int = 0
    deleted_lines: int = 0
    bound_test_pass: bool = False


_TERMINAL_STATES = {
    LineageRunState.FAILED,
    LineageRunState.INTERRUPTED,
    LineageRunState.PROMOTED,
}

_RUNTIME_EVENTS = {
    LineageEventType.INVOCATION_STARTED,
    LineageEventType.INVOCATION_COMPLETED,
    LineageEventType.INVOCATION_FAILED,
    LineageEventType.TOOL_STARTED,
    LineageEventType.TOOL_COMPLETED,
    LineageEventType.TOOL_FAILED,
    LineageEventType.SCOPE_ALLOWED,
    LineageEventType.SCOPE_DENIED,
    LineageEventType.COMPLETION_ATTEMPTED,
    LineageEventType.COMPLETION_DENIED,
}


def _fail(reason: str, event: Event | None = None) -> ProjectionError:
    return ProjectionError(
        reason,
        run_id=None if event is None else event.run_id,
        seq=None if event is None else event.seq,
    )


def _required(payload: dict[str, object], names: tuple[str, ...], event: Event) -> None:
    if any(name not in payload for name in names):
        raise _fail("event payload is missing required projection metadata", event)


def _integer(value: object, event: Event) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _fail("event payload count must be a nonnegative integer", event)
    return value


def _path(value: object, event: Event) -> str:
    try:
        return _PATH.validate_python(value)
    except ValidationError as error:
        raise _fail("event payload path is not canonical", event) from error


def _digest(value: object, event: Event, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _fail("event payload file-version digest is invalid", event)
    return value


def _operation(event: Event) -> LineageOperation | None:
    value = event.payload.get("operation")
    if value is None:
        return None
    try:
        return LineageOperation(value)
    except (TypeError, ValueError) as error:
        raise _fail("event payload operation is invalid", event) from error


def _status(event: Event, operation: LineageOperation | None) -> str:
    explicit = event.payload.get("status")
    if isinstance(explicit, str) and explicit:
        return explicit[:1024]
    if event.event_type in {
        LineageEventType.SCOPE_DENIED,
        LineageEventType.HANDOFF_DENIED,
        LineageEventType.COMPLETION_DENIED,
        LineageEventType.PROMOTION_DENIED,
    }:
        return "DENIED"
    if event.event_type in {
        LineageEventType.RUN_FAILED,
        LineageEventType.INVOCATION_FAILED,
        LineageEventType.TOOL_FAILED,
    }:
        return "FAILED"
    if (
        operation == LineageOperation.RUN_FIXED_TEST
        and event.event_type == LineageEventType.TOOL_COMPLETED
    ):
        return "PASS" if event.payload.get("passed") is True else "FAIL"
    return {
        LineageEventType.RUN_STARTED: "STARTING",
        LineageEventType.RUN_INTERRUPTED: "INTERRUPTED",
        LineageEventType.CLARIFICATION_ASKED: "WAITING INPUT",
        LineageEventType.COMPLETION_ATTEMPTED: "REQUESTED",
        LineageEventType.PROMOTION_COMPLETED: "PROMOTED",
        LineageEventType.TOOL_STARTED: "STARTED",
        LineageEventType.TOOL_COMPLETED: "COMPLETED",
    }.get(event.event_type, event.event_type.value.upper())


def _size_bucket(byte_count: int | None) -> int | None:
    if byte_count is None:
        return None
    return max(1, min(4, math.ceil(math.log2(1 + byte_count / 1024))))


def _verify(events: tuple[Event, ...]) -> None:
    if not isinstance(events, tuple) or any(not isinstance(event, Event) for event in events):
        raise ProjectionError("reduce_events accepts only a tuple of Event records")
    if not events:
        raise ProjectionError("a projection requires at least one event")
    first = events[0]
    identity = (
        first.run_id,
        first.repo_id,
        first.base_sha,
        first.agent_profile_id,
        first.policy_revision,
    )
    previous: str | None = None
    event_ids: set[str] = set()
    reference_digests: dict[tuple[str, str], str] = {}
    for expected_seq, event in enumerate(events, 1):
        if event.seq != expected_seq:
            raise _fail("event sequence is not contiguous and ordered", event)
        if (
            event.run_id,
            event.repo_id,
            event.base_sha,
            event.agent_profile_id,
            event.policy_revision,
        ) != identity:
            raise _fail("event stream identity changed within the run", event)
        if event.event_id in event_ids:
            raise _fail("event ID is duplicated within the run", event)
        if event.previous_event_sha256 != previous:
            raise _fail("event previous digest does not match the verified head", event)
        if event.payload_sha256 != canonical_json_sha256(event.payload):
            raise _fail("event payload digest does not match", event)
        if event.event_sha256 != canonical_json_sha256(
            event.model_dump(mode="json", exclude={"event_sha256"})
        ):
            raise _fail("event envelope digest does not match", event)
        for reference in (*event.references, event.source_ref):
            key = (reference.kind, reference.id)
            known = reference_digests.setdefault(key, reference.sha256)
            if known != reference.sha256:
                raise _fail("an evidence reference changed digest", event)
        event_ids.add(event.event_id)
        previous = event.event_sha256
    if first.event_type != LineageEventType.RUN_STARTED:
        raise _fail("the first event must be run.started", first)


def _read(files: dict[str, _File], event: Event) -> None:
    payload = event.payload
    _required(payload, ("path", "file_version_id", "byte_count", "line_count"), event)
    path = _path(payload["path"], event)
    version = _digest(payload["file_version_id"], event)
    byte_count = _integer(payload["byte_count"], event)
    line_count = _integer(payload["line_count"], event)
    absent = payload.get("state") == "ABSENT"
    if absent and (byte_count != 0 or line_count != 0):
        raise _fail("absent read has nonzero file metadata", event)
    item = files.get(path)
    if item is None:
        files[path] = _File(
            path=path,
            state="READ",
            file_version_id=None if absent else version,
            baseline_bytes=byte_count,
            baseline_lines=line_count,
            first_seq=event.seq,
            last_seq=event.seq,
            read_count=1,
        )
        return
    if not absent and item.file_version_id not in {None, version}:
        raise _fail("read observed an unexpected file version", event)
    if (
        item.state in {"DISCOVERED", "READ"}
        and item.baseline_bytes is not None
        and (item.baseline_bytes != byte_count or item.baseline_lines != line_count)
    ):
        raise _fail("read changed frozen baseline metadata", event)
    item.file_version_id = None if absent else version
    item.baseline_bytes = byte_count if item.baseline_bytes is None else item.baseline_bytes
    item.baseline_lines = line_count if item.baseline_lines is None else item.baseline_lines
    if item.state == "DISCOVERED":
        item.state = "READ"
    item.last_seq = event.seq
    item.read_count += 1


def _search(files: dict[str, _File], event: Event) -> None:
    _required(event.payload, ("paths",), event)
    raw_paths = event.payload["paths"]
    if not isinstance(raw_paths, (list, tuple)):
        raise _fail("search paths must be a sorted unique list", event)
    paths = tuple(_path(value, event) for value in raw_paths)
    if paths != tuple(sorted(set(paths))):
        raise _fail("search paths must be sorted and unique", event)
    for path in paths:
        item = files.get(path)
        if item is None:
            files[path] = _File(
                path=path,
                state="DISCOVERED",
                file_version_id=None,
                baseline_bytes=None,
                baseline_lines=None,
                first_seq=event.seq,
                last_seq=event.seq,
            )
        else:
            item.last_seq = event.seq


def _write(files: dict[str, _File], event: Event) -> None:
    payload = event.payload
    _required(
        payload,
        (
            "path",
            "before_file_version_id",
            "after_file_version_id",
            "baseline_bytes",
            "baseline_lines",
            "added_lines",
            "deleted_lines",
            "state",
        ),
        event,
    )
    path = _path(payload["path"], event)
    before = _digest(payload["before_file_version_id"], event, nullable=True)
    after = _digest(payload["after_file_version_id"], event, nullable=True)
    baseline_bytes = _integer(payload["baseline_bytes"], event)
    baseline_lines = _integer(payload["baseline_lines"], event)
    added = _integer(payload["added_lines"], event)
    deleted = _integer(payload["deleted_lines"], event)
    state = payload["state"]
    if (
        state not in {"EDITED", "NEW", "DELETED"}
        or {
            "EDITED": before is not None and after is not None,
            "NEW": before is None and after is not None,
            "DELETED": before is not None and after is None,
        }[state]
        is False
    ):
        raise _fail("write file-version bindings do not match its state", event)
    item = files.get(path)
    if item is not None:
        if item.file_version_id is not None and item.file_version_id != before:
            raise _fail("write does not continue the observed file-version lineage", event)
        if item.baseline_bytes is not None and (
            item.baseline_bytes != baseline_bytes or item.baseline_lines != baseline_lines
        ):
            raise _fail("write changed frozen baseline metadata", event)
        item.state = state
        item.file_version_id = after if after is not None else before
        item.baseline_bytes = baseline_bytes if item.baseline_bytes is None else item.baseline_bytes
        item.baseline_lines = baseline_lines if item.baseline_lines is None else item.baseline_lines
        item.last_seq = event.seq
        item.added_lines = added
        item.deleted_lines = deleted
        return
    files[path] = _File(
        path=path,
        state=state,
        file_version_id=after if after is not None else before,
        baseline_bytes=baseline_bytes,
        baseline_lines=baseline_lines,
        first_seq=event.seq,
        last_seq=event.seq,
        added_lines=added,
        deleted_lines=deleted,
    )


def _test(files: dict[str, _File], event: Event) -> None:
    _required(event.payload, ("passed", "bound_paths"), event)
    passed = event.payload["passed"]
    raw_paths = event.payload["bound_paths"]
    if not isinstance(passed, bool) or not isinstance(raw_paths, (list, tuple)):
        raise _fail("fixed-test binding metadata is invalid", event)
    paths = tuple(_path(value, event) for value in raw_paths)
    if paths != tuple(sorted(set(paths))):
        raise _fail("fixed-test bound paths must be sorted and unique", event)
    changed = {path for path, item in files.items() if item.state in {"EDITED", "NEW", "DELETED"}}
    if set(paths) != changed:
        raise _fail("fixed test does not bind the current changed-path set", event)
    for item in files.values():
        item.bound_test_pass = False
    for path in paths:
        files[path].bound_test_pass = passed


def _next_state(state: LineageRunState, event: Event) -> LineageRunState:
    if state in _TERMINAL_STATES:
        raise _fail("an event follows a terminal run state", event)
    if state in {LineageRunState.ACCESS_DENIED, LineageRunState.NEEDS_HUMAN} and (
        event.event_type in _RUNTIME_EVENTS
    ):
        raise _fail("a runtime event follows a terminal runtime decision", event)
    event_type = event.event_type
    if event_type == LineageEventType.RUN_STARTED:
        return LineageRunState.STARTING
    if event_type == LineageEventType.CLARIFICATION_ASKED:
        return LineageRunState.WAITING_INPUT
    if event_type in {LineageEventType.SCOPE_DENIED, LineageEventType.HANDOFF_DENIED}:
        return LineageRunState.ACCESS_DENIED
    if event_type in {
        LineageEventType.COMPLETION_DENIED,
        LineageEventType.PROMOTION_DENIED,
    }:
        return LineageRunState.NEEDS_HUMAN
    if event_type in {LineageEventType.RUN_FAILED, LineageEventType.INVOCATION_FAILED}:
        return LineageRunState.FAILED
    if event_type == LineageEventType.RUN_INTERRUPTED:
        return LineageRunState.INTERRUPTED
    if event_type == LineageEventType.PROMOTION_COMPLETED:
        return LineageRunState.PROMOTED
    if event_type == LineageEventType.RUN_ENDED:
        explicit = event.payload.get("state")
        try:
            ended = LineageRunState(explicit)
        except (TypeError, ValueError) as error:
            raise _fail("run.ended requires an explicit lineage state", event) from error
        if ended not in _TERMINAL_STATES | {LineageRunState.NEEDS_HUMAN}:
            raise _fail("run.ended state is not terminal", event)
        return ended
    if event_type == LineageEventType.CLARIFICATION_ANSWERED:
        return LineageRunState.LIVE
    if event_type in {
        LineageEventType.INVOCATION_STARTED,
        LineageEventType.INVOCATION_COMPLETED,
        LineageEventType.TOOL_STARTED,
        LineageEventType.TOOL_COMPLETED,
        LineageEventType.TOOL_FAILED,
    }:
        return (
            state
            if state
            in {
                LineageRunState.WAITING_INPUT,
                LineageRunState.ACCESS_DENIED,
                LineageRunState.NEEDS_HUMAN,
            }
            else LineageRunState.LIVE
        )
    return state


def _obligation(
    obligation_id: str,
    *,
    applicable: bool,
    evidence: list[str],
) -> ProjectionObligation:
    return ProjectionObligation(
        obligation_id=obligation_id,
        status=("SATISFIED" if evidence else "MISSING") if applicable else "NOT_APPLICABLE",
        evidence_event_ids=tuple(evidence),
    )


def reduce_events(events: tuple[Event, ...]) -> LineageProjection:
    """Purely reduce one verified event stream into its bounded working set."""

    _verify(events)
    files: dict[str, _File] = {}
    rail: list[ProjectionEvent] = []
    state = LineageRunState.STARTING
    changesets: list[str] = []
    tests: list[str] = []
    memories: list[str] = []
    injections: list[str] = []
    candidates: list[str] = []
    decisions: list[str] = []
    started_calls: dict[str, LineageOperation] = {}
    finished_calls: set[str] = set()
    started_invocations: dict[str, Event] = {}
    finished_invocations: set[str] = set()
    completion_attempts: dict[str, Event] = {}
    completion_denials: set[str] = set()
    ended = False

    for event in events:
        if ended:
            raise _fail("an event follows an explicit run end", event)
        operation = _operation(event)
        if (
            event.event_type
            in {
                LineageEventType.TOOL_STARTED,
                LineageEventType.TOOL_COMPLETED,
                LineageEventType.TOOL_FAILED,
            }
            and operation is None
        ):
            raise _fail("ordinary tool events require an operation", event)
        if (
            event.event_type
            in {
                LineageEventType.TOOL_STARTED,
                LineageEventType.TOOL_COMPLETED,
                LineageEventType.TOOL_FAILED,
            }
            and operation == LineageOperation.REQUEST_COMPLETION
        ):
            raise _fail("request_completion cannot use ordinary tool events", event)
        if event.event_type == LineageEventType.RUN_STARTED and event.seq != 1:
            raise _fail("run.started may appear only at sequence one", event)
        if event.event_type == LineageEventType.INVOCATION_STARTED:
            assert event.invocation_id is not None
            if event.invocation_id in started_invocations:
                raise _fail("invocation started more than once", event)
            started_invocations[event.invocation_id] = event
        elif event.event_type in {
            LineageEventType.INVOCATION_COMPLETED,
            LineageEventType.INVOCATION_FAILED,
        }:
            assert event.invocation_id is not None
            start = started_invocations.get(event.invocation_id)
            if (
                start is None
                or event.invocation_id in finished_invocations
                or event.session_id != start.session_id
                or event.payload.get("adapter_kind")
                != start.payload.get("adapter_kind")
            ):
                raise _fail("invocation result does not match one unfinished start", event)
            finished_invocations.add(event.invocation_id)
        elif event.event_type == LineageEventType.COMPLETION_ATTEMPTED:
            assert event.tool_call_id is not None
            if event.tool_call_id in completion_attempts:
                raise _fail("completion was attempted more than once", event)
            completion_attempts[event.tool_call_id] = event
        elif event.event_type == LineageEventType.COMPLETION_DENIED:
            if event.tool_call_id is None:
                raise _fail("completion denial lacks a tool-call identity", event)
            attempt = completion_attempts.get(event.tool_call_id)
            matching_reference = (
                attempt is not None
                and any(
                    reference.kind.value == "event"
                    and reference.id == attempt.event_id
                    and reference.sha256 == attempt.event_sha256
                    for reference in event.references
                )
            )
            if (
                attempt is None
                or event.tool_call_id in completion_denials
                or event.session_id != attempt.session_id
                or event.invocation_id != attempt.invocation_id
                or not matching_reference
            ):
                raise _fail("completion denial does not match one attempt", event)
            completion_denials.add(event.tool_call_id)
        elif event.event_type == LineageEventType.TOOL_STARTED:
            assert event.tool_call_id is not None and operation is not None
            if event.tool_call_id in started_calls:
                raise _fail("tool call started more than once", event)
            started_calls[event.tool_call_id] = operation
        elif event.event_type in {
            LineageEventType.TOOL_COMPLETED,
            LineageEventType.TOOL_FAILED,
        }:
            assert event.tool_call_id is not None and operation is not None
            if (
                started_calls.get(event.tool_call_id) != operation
                or event.tool_call_id in finished_calls
            ):
                raise _fail("tool result does not match one unfinished start", event)
            finished_calls.add(event.tool_call_id)
        state = _next_state(state, event)
        ended = event.event_type == LineageEventType.RUN_ENDED
        accepted_path: str | None = None
        if event.event_type == LineageEventType.TOOL_COMPLETED:
            if operation == LineageOperation.SEARCH_REPO:
                _search(files, event)
            elif operation == LineageOperation.READ_FILE:
                _read(files, event)
                accepted_path = _path(event.payload["path"], event)
            elif operation == LineageOperation.WRITE_FILE:
                changesets.clear()
                tests.clear()
                decisions.clear()
                for item in files.values():
                    item.bound_test_pass = False
                _write(files, event)
                accepted_path = _path(event.payload["path"], event)
            elif operation == LineageOperation.RUN_FIXED_TEST:
                _test(files, event)
                tests.clear()
                if event.payload["passed"] is True:
                    tests.append(event.event_id)
        rail.append(
            ProjectionEvent(
                seq=event.seq,
                event_id=event.event_id,
                event_type=event.event_type,
                truth_kind=event.truth_kind,
                operation=operation,
                status=_status(event, operation),
                path=accepted_path,
            )
        )
        if event.event_type == LineageEventType.CHANGESET_PARSED:
            changesets.append(event.event_id)
        elif event.event_type == LineageEventType.MEMORY_APPROVED:
            memories.append(event.event_id)
        elif event.event_type == LineageEventType.CONTEXT_INJECTED:
            injections.append(event.event_id)
        elif event.event_type == LineageEventType.CANDIDATE_CREATED:
            candidates.append(event.event_id)
        elif event.event_type == LineageEventType.PROMOTION_APPROVED:
            decisions.append(event.event_id)

    ordered = sorted(
        files.values(),
        key=lambda item: (
            item.state not in {"EDITED", "NEW", "DELETED"},
            item.state == "DISCOVERED",
            item.path,
        ),
    )
    omitted_counts: dict[str, int] = {}
    if len(ordered) > MAX_VISIBLE_FILES:
        omitted = ordered[MAX_VISIBLE_FILES:]
        omitted_counts["files"] = len(omitted)
        for item in omitted:
            parent = PurePosixPath(item.path).parent.as_posix()
            key = f"directory:{parent}"
            omitted_counts[key] = omitted_counts.get(key, 0) + 1
    visible = sorted(ordered[:MAX_VISIBLE_FILES], key=lambda item: item.path)
    if len(rail) > MAX_VISIBLE_EVENTS:
        omitted_counts["events"] = len(rail) - MAX_VISIBLE_EVENTS
        rail = rail[-MAX_VISIBLE_EVENTS:]
    projected_files = tuple(
        ProjectionFile(
            path=item.path,
            state=item.state,
            file_version_id=item.file_version_id,
            baseline_bytes=item.baseline_bytes,
            baseline_lines=item.baseline_lines,
            size_bucket=_size_bucket(item.baseline_bytes),
            first_seq=item.first_seq,
            last_seq=item.last_seq,
            read_count=item.read_count,
            added_lines=item.added_lines,
            deleted_lines=item.deleted_lines,
            bound_test_pass=item.bound_test_pass,
        )
        for item in visible
    )
    edited = any(item.state in {"EDITED", "NEW", "DELETED"} for item in files.values())
    obligations = (
        _obligation(
            "canonical_changeset",
            applicable=edited or bool(candidates),
            evidence=changesets,
        ),
        _obligation("bound_fixed_test", applicable=edited, evidence=tests),
        _obligation("approved_memory_injected", applicable=bool(memories), evidence=injections),
        _obligation(
            "human_promotion_decision",
            applicable=edited or bool(candidates),
            evidence=decisions,
        ),
    )
    payload = {
        "schema_version": 2,
        "run_id": events[0].run_id,
        "state": state,
        "head_seq": events[-1].seq,
        "head_sha256": events[-1].event_sha256,
        "files": projected_files,
        "event_rail": tuple(rail),
        "obligations": obligations,
        "omitted_counts": omitted_counts,
        "unknowns": UNKNOWNS,
    }
    canonical = {
        key: (
            [item.model_dump(mode="json") for item in value]
            if key in {"files", "event_rail", "obligations"}
            else value.value
            if key == "state"
            else value
        )
        for key, value in payload.items()
    }
    return LineageProjection(
        **payload,
        projection_sha256=canonical_json_sha256(canonical),
    )
