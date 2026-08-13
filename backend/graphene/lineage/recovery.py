from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from ..hashing import canonical_json_sha256, sha256_hex
from ..models import (
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    LineageAuthority,
    LineageEventType,
    LineageRunState,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)
from .reducer import ProjectionError, reduce_events


class RecoveryStore(Protocol):
    def append(
        self,
        run_id: str,
        expected_head: VerifiedHead,
        idempotency_key: str,
        draft: EventInput,
    ) -> Event: ...

    def tail(self, run_id: str, after_seq: int, limit: int) -> tuple[Event, ...]: ...

    def verify(self, run_id: str) -> VerifiedHead | EvidenceInvalidState: ...


SourceArtifactRecorder = Callable[[Mapping[str, Any]], SourceReference]


class RecoveryError(RuntimeError):
    pass


class RecoveryEvidenceError(RecoveryError):
    pass


class RecoveryTerminalError(RecoveryError):
    pass


class RecoveryCheckoutError(RecoveryError):
    pass


def quarantine_checkout(run_id: str, checkout_path: str | Path) -> Path:
    """Atomically move one validated checkout to its recoverable quarantine."""

    checkout, quarantine = _checkout_paths(run_id, checkout_path)
    _discard_checkout(checkout, quarantine)
    return quarantine


def recover_interrupted_run(
    store: RecoveryStore,
    *,
    run_id: str,
    checkout_path: str | Path,
    record_source: SourceArtifactRecorder,
) -> Event | None:
    """Close uncertain dispatch as interrupted, then quarantine its checkout."""

    checkout, quarantine = _checkout_paths(run_id, checkout_path)
    head = store.verify(run_id)
    if isinstance(head, EvidenceInvalidState):
        raise RecoveryEvidenceError("lineage evidence is invalid")
    events = _whole_run(store, head)
    try:
        projection = reduce_events(events)
    except ProjectionError as error:
        raise RecoveryEvidenceError("lineage stream is semantically invalid") from error
    unmatched = _unmatched_starts(events)
    checkout_binding = sha256_hex(str(checkout).encode())

    interrupted = next(
        (
            event
            for event in reversed(events)
            if event.event_type == LineageEventType.RUN_INTERRUPTED
        ),
        None,
    )
    if interrupted is not None:
        if (
            interrupted.payload.get("recovery_kind") != "uncertain_dispatch"
            or interrupted.payload.get("checkout_binding_sha256")
            != checkout_binding
        ):
            raise RecoveryTerminalError("run is already terminal")
        _discard_checkout(checkout, quarantine)
        return interrupted
    if (
        projection.state in {LineageRunState.FAILED, LineageRunState.PROMOTED}
        or any(event.event_type == LineageEventType.RUN_ENDED for event in events)
    ):
        raise RecoveryTerminalError("run is already terminal")

    if not unmatched:
        return None
    if len(unmatched) > 16:
        raise RecoveryEvidenceError("too many unmatched starts for one recovery event")

    references = tuple(
        EvidenceReference(
            kind=EvidenceKind.EVENT,
            id=event.event_id,
            sha256=event.event_sha256,
        )
        for event in unmatched
    )
    source_record = {
        "schema_version": 2,
        "action": "recover_interrupted_run",
        "run_id": run_id,
        "checkout_binding_sha256": checkout_binding,
        "expected_head": head.model_dump(mode="json"),
        "unmatched_starts": [item.model_dump(mode="json") for item in references],
    }
    source = record_source(source_record)
    if (
        not isinstance(source, SourceReference)
        or source.kind != SourceKind.LIFECYCLE_REQUEST
        or source.sha256 != canonical_json_sha256(source_record)
    ):
        raise RecoveryEvidenceError("recovery source artifact is invalid")

    first = events[0]
    tool_count = sum(
        event.event_type == LineageEventType.TOOL_STARTED for event in unmatched
    )
    payload = {
        "status": "INTERRUPTED",
        "state": "INTERRUPTED",
        "reason_code": "uncertain_dispatch",
        "recovery_kind": "uncertain_dispatch",
        "checkout_binding_sha256": checkout_binding,
        "unmatched_tool_starts": tool_count,
        "unmatched_invocations": len(unmatched) - tool_count,
    }
    event = store.append(
        run_id,
        head,
        canonical_json_sha256(
            {
                "run_id": run_id,
                "expected_head": head.model_dump(mode="json"),
                "recovery_kind": "uncertain_dispatch",
            }
        ),
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id=first.repo_id,
            base_sha=first.base_sha,
            agent_profile_id=first.agent_profile_id,
            policy_revision=first.policy_revision,
            event_type=LineageEventType.RUN_INTERRUPTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=references,
            source_ref=source,
            payload=payload,
        ),
    )
    if (
        event.run_id != run_id
        or event.seq != head.seq + 1
        or event.previous_event_sha256 != head.event_sha256
        or event.event_type != LineageEventType.RUN_INTERRUPTED
    ):
        raise RecoveryEvidenceError("lineage store returned a non-successor event")
    _discard_checkout(checkout, quarantine)
    return event


def _whole_run(store: RecoveryStore, head: VerifiedHead) -> tuple[Event, ...]:
    if head.seq == 0:
        raise RecoveryEvidenceError("run has no durable start")
    events: list[Event] = []
    after_seq = 0
    while after_seq < head.seq:
        batch = store.tail(head.run_id, after_seq, min(256, head.seq - after_seq))
        if not batch or batch[0].seq != after_seq + 1:
            raise RecoveryEvidenceError("lineage tail is incomplete")
        events.extend(batch)
        after_seq = batch[-1].seq
    if (
        len(events) != head.event_count
        or events[-1].seq != head.seq
        or events[-1].event_sha256 != head.event_sha256
    ):
        raise RecoveryEvidenceError("lineage tail does not match its verified head")
    return tuple(events)


def _unmatched_starts(events: tuple[Event, ...]) -> tuple[Event, ...]:
    tool_starts = {
        event.tool_call_id: event
        for event in events
        if event.event_type == LineageEventType.TOOL_STARTED
    }
    finished_tools = {
        event.tool_call_id
        for event in events
        if event.event_type
        in {LineageEventType.TOOL_COMPLETED, LineageEventType.TOOL_FAILED}
    }

    invocation_starts: dict[str, Event] = {}
    invocation_results: set[str] = set()
    completion_attempts: dict[str, Event] = {}
    completion_denials: set[str] = set()
    completion_closed_invocations: set[str] = set()
    for event in events:
        if event.event_type == LineageEventType.INVOCATION_STARTED:
            assert event.invocation_id is not None
            if event.invocation_id in invocation_starts:
                raise RecoveryEvidenceError("invocation started more than once")
            invocation_starts[event.invocation_id] = event
        elif event.event_type in {
            LineageEventType.INVOCATION_COMPLETED,
            LineageEventType.INVOCATION_FAILED,
        }:
            assert event.invocation_id is not None
            if (
                event.invocation_id not in invocation_starts
                or event.invocation_id in invocation_results
            ):
                raise RecoveryEvidenceError("invocation result has no unmatched start")
            invocation_results.add(event.invocation_id)
        elif event.event_type == LineageEventType.COMPLETION_ATTEMPTED:
            assert event.tool_call_id is not None
            if event.tool_call_id in completion_attempts:
                raise RecoveryEvidenceError("completion was attempted more than once")
            completion_attempts[event.tool_call_id] = event
        elif event.event_type == LineageEventType.COMPLETION_DENIED:
            attempted = completion_attempts.get(event.tool_call_id or "")
            attempted_ref = (
                None
                if attempted is None
                else EvidenceReference(
                    kind=EvidenceKind.EVENT,
                    id=attempted.event_id,
                    sha256=attempted.event_sha256,
                )
            )
            if (
                attempted is None
                or event.tool_call_id in completion_denials
                or attempted.invocation_id != event.invocation_id
                or event.invocation_id not in invocation_starts
                or attempted_ref not in event.references
            ):
                raise RecoveryEvidenceError("completion denial has no matching attempt")
            completion_denials.add(event.tool_call_id)
            assert event.invocation_id is not None
            completion_closed_invocations.add(event.invocation_id)

    unmatched = [
        event
        for tool_call_id, event in tool_starts.items()
        if tool_call_id not in finished_tools
    ]
    unmatched.extend(
        event
        for invocation_id, event in invocation_starts.items()
        if invocation_id
        not in invocation_results | completion_closed_invocations
    )
    return tuple(sorted(unmatched, key=lambda event: event.seq))


def _checkout_paths(run_id: str, value: str | Path) -> tuple[Path, Path]:
    checkout = Path(value)
    if not checkout.is_absolute():
        raise RecoveryCheckoutError("checkout path must be absolute")
    checkout = Path(os.path.abspath(checkout))
    if any(path.is_symlink() for path in (checkout, *checkout.parents)):
        raise RecoveryCheckoutError("checkout path cannot traverse a symlink")
    if not checkout.parent.is_dir():
        raise RecoveryCheckoutError("checkout parent is unavailable")
    resolved = checkout.resolve(strict=False)
    root = Path(resolved.anchor)
    protected = (Path.cwd().resolve(), Path.home().resolve())
    if (
        resolved == root
        or resolved.parent == root
        or any(resolved == path or resolved in path.parents for path in protected)
    ):
        raise RecoveryCheckoutError("checkout path is too broad")
    if checkout.exists() and not checkout.is_dir():
        raise RecoveryCheckoutError("checkout path is not a real directory")
    quarantine = checkout.parent / (
        ".graphene-interrupted-"
        + sha256_hex(f"{run_id}\0{checkout}".encode())[:24]
    )
    if quarantine.is_symlink() or (
        quarantine.exists() and (not quarantine.is_dir() or checkout.exists())
    ):
        raise RecoveryCheckoutError("checkout quarantine is unavailable")
    return checkout, quarantine


def _discard_checkout(checkout: Path, quarantine: Path) -> None:
    if checkout.is_symlink():
        raise RecoveryCheckoutError("checkout cannot be safely quarantined")
    if not checkout.exists():
        return
    if not checkout.is_dir() or quarantine.exists():
        raise RecoveryCheckoutError("checkout cannot be safely quarantined")
    parent_fd = os.open(
        checkout.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.rename(
            checkout.name,
            quarantine.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    except OSError as error:
        raise RecoveryCheckoutError("checkout quarantine failed") from error
    finally:
        os.close(parent_fd)


__all__ = [
    "RecoveryCheckoutError",
    "RecoveryError",
    "RecoveryEvidenceError",
    "RecoveryStore",
    "RecoveryTerminalError",
    "SourceArtifactRecorder",
    "quarantine_checkout",
    "recover_interrupted_run",
]
