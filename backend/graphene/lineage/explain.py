from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Protocol

from pydantic import TypeAdapter, ValidationError

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..core_models import (
    ContextBrief,
    ContextInjectionReceipt,
    Event,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    FeedbackRecord,
    HandoffDecision,
    HunkEvidence,
    LineageEventType,
    LineageOperation,
    MemoryRevision,
    RepoPath,
    VerifiedHead,
)

_PATH = TypeAdapter(RepoPath)
_PAGE_SIZE = 256
_DEFAULT_ARTIFACT_LIMIT = 262_144
_DEFAULT_OBSERVATION_LIMIT = 64
_DEFAULT_RELATIONSHIP_LIMIT = 40


class ExplainError(RuntimeError):
    pass


class ExplainEvidenceError(ExplainError):
    pass


class ExplainNotFound(ExplainError):
    pass


class ExplainStore(Protocol):
    def verify(self, run_id: str) -> VerifiedHead | EvidenceInvalidState: ...

    def tail(self, run_id: str, after_seq: int, limit: int) -> tuple[Event, ...]: ...


class ArtifactReader(Protocol):
    def resolve(self, kind: str, artifact_id: str) -> bytes | None: ...


@dataclass(slots=True)
class _Binding:
    id: str
    sha256: str
    kinds: set[str] = field(default_factory=set)
    event_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True, order=True, slots=True)
class _Edge:
    event_id: str
    relation: str
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    paths: tuple[str, ...]

    def public(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "relation": self.relation,
            "source": {"kind": self.source_kind, "id": self.source_id},
            "target": {"kind": self.target_kind, "id": self.target_id},
        }


class _Snapshot:
    def __init__(
        self,
        head: VerifiedHead,
        events: tuple[Event, ...],
        artifacts: ArtifactReader,
    ) -> None:
        self.head = head
        self.events = events
        self.by_event_id = {event.event_id: event for event in events}
        self.artifacts = artifacts
        self.bindings: dict[str, _Binding] = {}
        self.records: dict[str, dict[str, Any]] = {}
        for event in events:
            self._bind(
                event.source_ref.id,
                event.source_ref.sha256,
                event.source_ref.kind.value,
                event.event_id,
            )
            for reference in event.references:
                if reference.kind == EvidenceKind.EVENT:
                    target = self.by_event_id.get(reference.id)
                    if (
                        target is None
                        or target.seq >= event.seq
                        or target.event_sha256 != reference.sha256
                    ):
                        raise ExplainEvidenceError(
                            "run contains an invalid event relationship"
                        )
                    continue
                self._bind(
                    reference.id,
                    reference.sha256,
                    reference.kind.value,
                    event.event_id,
                )

    def _bind(self, artifact_id: str, digest: str, kind: str, event_id: str) -> None:
        binding = self.bindings.get(artifact_id)
        if binding is None:
            binding = _Binding(id=artifact_id, sha256=digest)
            self.bindings[artifact_id] = binding
        elif binding.sha256 != digest:
            raise ExplainEvidenceError("run contains a conflicting artifact binding")
        binding.kinds.add(kind)
        binding.event_ids.add(event_id)

    def record(self, artifact_id: str) -> dict[str, Any]:
        cached = self.records.get(artifact_id)
        if cached is not None:
            return cached
        binding = self.bindings.get(artifact_id)
        if binding is None:
            raise ExplainNotFound("item is not referenced by the selected run")
        raws: list[bytes] = []
        for kind in sorted(binding.kinds):
            try:
                raw = self.artifacts.resolve(kind, artifact_id)
            except Exception as error:
                raise ExplainEvidenceError(
                    "referenced artifact could not be resolved"
                ) from error
            if raw is None or sha256_hex(raw) != binding.sha256:
                raise ExplainEvidenceError(
                    "referenced artifact bytes do not match their digest"
                )
            raws.append(raw)
        if not raws or any(raw != raws[0] for raw in raws[1:]):
            raise ExplainEvidenceError("artifact aliases resolve to different bytes")
        try:
            value = json.loads(raws[0])
        except (TypeError, ValueError, UnicodeError) as error:
            raise ExplainEvidenceError("referenced artifact is malformed") from error
        if not isinstance(value, dict) or canonical_json_bytes(value) != raws[0]:
            raise ExplainEvidenceError("referenced artifact is not canonical JSON")
        self.records[artifact_id] = value
        return value


def _snapshot(
    store: ExplainStore,
    artifacts: ArtifactReader,
    run_id: str,
) -> _Snapshot:
    before = store.verify(run_id)
    if isinstance(before, EvidenceInvalidState):
        raise ExplainEvidenceError("selected run evidence is invalid")
    if before.seq == 0:
        raise ExplainNotFound("selected run does not exist")
    events: list[Event] = []
    after_seq = 0
    while after_seq < before.seq:
        page = store.tail(
            run_id,
            after_seq,
            min(_PAGE_SIZE, before.seq - after_seq),
        )
        if not page or page[0].seq != after_seq + 1:
            raise ExplainEvidenceError("verified run enumeration is incomplete")
        events.extend(page)
        after_seq = page[-1].seq
    after = store.verify(run_id)
    if (
        after != before
        or len(events) != before.event_count
        or tuple(event.seq for event in events) != tuple(range(1, before.seq + 1))
        or events[-1].event_sha256 != before.event_sha256
        or any(event.run_id != run_id for event in events)
    ):
        raise ExplainEvidenceError("selected run changed during inspection")
    return _Snapshot(before, tuple(events), artifacts)


def _positive_limit(value: int, name: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def inspect_run_item(
    store: ExplainStore,
    artifacts: ArtifactReader,
    run_id: str,
    item_id: str,
    *,
    max_artifact_bytes: int = _DEFAULT_ARTIFACT_LIMIT,
) -> dict[str, object]:
    """Inspect one public event or one private artifact bound by the selected run."""

    limit = _positive_limit(max_artifact_bytes, "max_artifact_bytes", 1_048_576)
    snapshot = _snapshot(store, artifacts, run_id)
    event = snapshot.by_event_id.get(item_id)
    if event is not None:
        return {
            "query": "inspect",
            "run_id": run_id,
            "head": snapshot.head.model_dump(mode="json"),
            "item": {
                "type": "event",
                "event": event.model_dump(mode="json"),
            },
            "omissions": [],
            "unknowns": [],
        }

    binding = snapshot.bindings.get(item_id)
    if binding is None:
        # Deliberately identical for unknown and cross-run identifiers.
        raise ExplainNotFound("item is not referenced by the selected run")
    record = snapshot.record(item_id)
    raw = canonical_json_bytes(record)
    omitted: list[dict[str, object]] = []
    exposed: Mapping[str, Any] | None = record
    if len(raw) > limit:
        exposed = None
        omitted.append(
            {
                "field": "item.record",
                "reason": "artifact_byte_limit",
                "byte_count": len(raw),
                "limit": limit,
            }
        )
    referenced_by = sorted(binding.event_ids)
    if len(referenced_by) > _DEFAULT_OBSERVATION_LIMIT:
        omitted.append(
            {
                "field": "item.referenced_by",
                "reason": "reference_limit",
                "count": len(referenced_by) - _DEFAULT_OBSERVATION_LIMIT,
                "limit": _DEFAULT_OBSERVATION_LIMIT,
            }
        )
        referenced_by = referenced_by[:_DEFAULT_OBSERVATION_LIMIT]
    return {
        "query": "inspect",
        "run_id": run_id,
        "head": snapshot.head.model_dump(mode="json"),
        "item": {
            "type": "artifact",
            "id": binding.id,
            "sha256": binding.sha256,
            "kinds": sorted(binding.kinds),
            "byte_count": len(raw),
            "referenced_by": referenced_by,
            "record": exposed,
        },
        "omissions": omitted,
        "unknowns": [],
    }


def _references(event: Event, kind: EvidenceKind) -> tuple[EvidenceReference, ...]:
    return tuple(reference for reference in event.references if reference.kind == kind)


def _one_reference(event: Event, kind: EvidenceKind) -> EvidenceReference:
    references = _references(event, kind)
    if len(references) != 1:
        raise ExplainEvidenceError(
            f"{event.event_type.value} does not bind exactly one {kind.value} artifact"
        )
    return references[0]


def _event_reference_ids(event: Event) -> set[str]:
    return {
        reference.id
        for reference in event.references
        if reference.kind == EvidenceKind.EVENT
    }


def _paths(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()
    value = payload.get("path")
    if isinstance(value, str):
        values.add(value)
    for key in ("paths", "bound_paths", "changed_paths"):
        many = payload.get(key)
        if isinstance(many, list) and all(isinstance(item, str) for item in many):
            values.update(many)
    return tuple(sorted(values))


def _add(
    edges: set[_Edge],
    event: Event,
    relation: str,
    source_kind: str,
    source_id: str,
    target_kind: str,
    target_id: str,
    paths: tuple[str, ...],
) -> None:
    edges.add(
        _Edge(
            event_id=event.event_id,
            relation=relation,
            source_kind=source_kind,
            source_id=source_id,
            target_kind=target_kind,
            target_id=target_id,
            paths=tuple(sorted(set(paths))),
        )
    )


def _tool_edges(snapshot: _Snapshot, event: Event, edges: set[_Edge]) -> None:
    if event.event_type != LineageEventType.TOOL_COMPLETED:
        return
    paths = _paths(event.payload)
    operation = event.payload.get("operation")
    relation = {
        LineageOperation.SEARCH_REPO.value: "OBSERVED",
        LineageOperation.READ_FILE.value: "READ",
        LineageOperation.WRITE_FILE.value: "WROTE",
        LineageOperation.RUN_FIXED_TEST.value: "VALIDATED",
    }.get(operation)
    if relation is not None:
        for path in paths:
            _add(edges, event, relation, "event", event.event_id, "path", path, (path,))

    versions = _references(event, EvidenceKind.FILE_VERSION)
    for reference in versions:
        record = snapshot.record(reference.id)
        path = record.get("path")
        version_id = record.get("file_version_id")
        if not isinstance(path, str) or not isinstance(version_id, str):
            raise ExplainEvidenceError("file-version relationship is malformed")
        expected_ids = {
            value
            for value in (
                event.payload.get("file_version_id"),
                event.payload.get("before_file_version_id"),
                event.payload.get("after_file_version_id"),
            )
            if isinstance(value, str)
        }
        if version_id not in expected_ids or (paths and path not in paths):
            raise ExplainEvidenceError("file-version relationship is not payload-bound")
        kind = (
            "READ_VERSION"
            if operation == LineageOperation.READ_FILE.value
            else "WROTE_VERSION"
        )
        _add(
            edges,
            event,
            kind,
            "event",
            event.event_id,
            "file_version",
            reference.id,
            (path,),
        )


def _changeset_edges(snapshot: _Snapshot, event: Event, edges: set[_Edge]) -> None:
    if event.event_type != LineageEventType.CHANGESET_PARSED:
        return
    reference = _one_reference(event, EvidenceKind.CHANGESET)
    record = snapshot.record(reference.id)
    paths = tuple(record.get("changed_paths", ()))
    if (
        not paths
        or not all(isinstance(path, str) for path in paths)
        or list(paths) != event.payload.get("changed_paths")
        or record.get("changeset_id") != event.payload.get("changeset_id")
        or record.get("candidate_patch_sha256")
        != event.payload.get("candidate_patch_sha256")
    ):
        raise ExplainEvidenceError("changeset artifact is not payload-bound")
    for path in paths:
        _add(edges, event, "MODIFIES", "changeset", reference.id, "path", path, (path,))

    write_ids = _event_reference_ids(event)
    file_changes = record.get("file_changes")
    if not isinstance(file_changes, list):
        raise ExplainEvidenceError("changeset file bindings are malformed")
    for change in file_changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str):
            raise ExplainEvidenceError("changeset file binding is malformed")
        path = change["path"]
        ids = change.get("write_event_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or not all(isinstance(item, str) for item in ids)
        ):
            raise ExplainEvidenceError("changeset write bindings are malformed")
        for event_id in ids:
            write = snapshot.by_event_id.get(event_id)
            if (
                event_id not in write_ids
                or write is None
                or write.event_type != LineageEventType.TOOL_COMPLETED
                or write.payload.get("operation") != LineageOperation.WRITE_FILE.value
                or write.payload.get("path") != path
            ):
                raise ExplainEvidenceError("changeset write is not event-bound")
            _add(
                edges,
                event,
                "PRODUCED",
                "event",
                event_id,
                "changeset",
                reference.id,
                (path,),
            )

    hunk_refs = _references(event, EvidenceKind.HUNK)
    if len(hunk_refs) != event.payload.get("hunk_count"):
        raise ExplainEvidenceError("changeset hunk count is not reference-bound")
    for hunk_ref in hunk_refs:
        try:
            hunk = HunkEvidence.model_validate(snapshot.record(hunk_ref.id))
        except ValidationError as error:
            raise ExplainEvidenceError("hunk artifact is malformed") from error
        if hunk.canonical_patch_sha256 != record.get("candidate_patch_sha256"):
            raise ExplainEvidenceError("hunk is not bound to its changeset")
        _add(
            edges,
            event,
            "CONTAINS",
            "changeset",
            reference.id,
            "hunk",
            hunk_ref.id,
            (hunk.path,),
        )
        _add(
            edges,
            event,
            "MODIFIES",
            "hunk",
            hunk_ref.id,
            "path",
            hunk.path,
            (hunk.path,),
        )


def _feedback_edges(snapshot: _Snapshot, event: Event, edges: set[_Edge]) -> None:
    if event.event_type != LineageEventType.FEEDBACK_RECORDED:
        return
    feedback_ref = _one_reference(event, EvidenceKind.FEEDBACK)
    hunk_ref = _one_reference(event, EvidenceKind.HUNK)
    try:
        feedback = FeedbackRecord.model_validate(snapshot.record(feedback_ref.id))
        hunk = HunkEvidence.model_validate(snapshot.record(hunk_ref.id))
    except ValidationError as error:
        raise ExplainEvidenceError("feedback relationship is malformed") from error
    if (
        feedback.run_id != event.run_id
        or feedback.feedback_id != event.payload.get("feedback_id")
        or feedback.selected_hunk_id != event.payload.get("hunk_id")
        or feedback.evidence_event_id != event.payload.get("evidence_event_id")
        or feedback.evidence_event_id not in _event_reference_ids(event)
        or hunk.hunk_id != feedback.selected_hunk_id
    ):
        raise ExplainEvidenceError("feedback relationship is not payload-bound")
    _add(
        edges,
        event,
        "TRIGGERED",
        "hunk",
        hunk_ref.id,
        "feedback",
        feedback_ref.id,
        (hunk.path,),
    )
    _add(
        edges,
        event,
        "EVIDENCED",
        "event",
        feedback.evidence_event_id,
        "feedback",
        feedback_ref.id,
        (hunk.path,),
    )


def _memory_edges(
    snapshot: _Snapshot,
    event: Event,
    edges: set[_Edge],
    query_path: str,
) -> None:
    if event.event_type not in {
        LineageEventType.MEMORY_PROPOSED,
        LineageEventType.MEMORY_APPROVED,
        LineageEventType.MEMORY_REJECTED,
    }:
        return
    references = _references(event, EvidenceKind.MEMORY_REVISION)
    if not references:
        raise ExplainEvidenceError("memory event has no revision artifact")
    memories: list[tuple[EvidenceReference, MemoryRevision]] = []
    for reference in references:
        try:
            memory = MemoryRevision.model_validate(snapshot.record(reference.id))
        except ValidationError as error:
            raise ExplainEvidenceError("memory revision is malformed") from error
        if memory.memory_id != event.payload.get(
            "memory_id"
        ) or memory.revision != event.payload.get("revision"):
            raise ExplainEvidenceError("memory revision is not payload-bound")
        memories.append((reference, memory))
    decided = memories[-1]
    if decided[0].sha256 != event.payload.get("memory_sha256"):
        raise ExplainEvidenceError("memory digest is not payload-bound")
    relevant = tuple(
        [query_path]
        if any(fnmatchcase(query_path, pattern) for pattern in decided[1].path_globs)
        else []
    )
    feedback_refs = _references(event, EvidenceKind.FEEDBACK)
    if event.event_type == LineageEventType.MEMORY_PROPOSED:
        if len(feedback_refs) != 1 or decided[1].feedback_id != snapshot.record(
            feedback_refs[0].id
        ).get("feedback_id"):
            raise ExplainEvidenceError("memory proposal is not feedback-bound")
        _add(
            edges,
            event,
            "LEARNED_AS",
            "feedback",
            feedback_refs[0].id,
            "memory_revision",
            decided[0].id,
            relevant,
        )
    else:
        if len(memories) != 2:
            raise ExplainEvidenceError("memory decision does not bind both revisions")
        relation = (
            "APPROVED"
            if event.event_type == LineageEventType.MEMORY_APPROVED
            else "REJECTED"
        )
        _add(
            edges,
            event,
            relation,
            "memory_revision",
            memories[0][0].id,
            "memory_revision",
            memories[1][0].id,
            relevant,
        )


def _test_edges(snapshot: _Snapshot, event: Event, edges: set[_Edge]) -> None:
    if event.event_type != LineageEventType.TEST_RECEIPT_CREATED:
        return
    test_ref = _one_reference(event, EvidenceKind.TEST_RECEIPT)
    changeset_ref = _one_reference(event, EvidenceKind.CHANGESET)
    receipt = snapshot.record(test_ref.id)
    changeset = snapshot.record(changeset_ref.id)
    paths = tuple(event.payload.get("bound_paths", ()))
    if (
        receipt.get("bound_paths") != list(paths)
        or event.payload.get("receipt_id") != test_ref.id
        or event.payload.get("receipt_sha256") != test_ref.sha256
        or changeset.get("changed_paths") != list(paths)
    ):
        raise ExplainEvidenceError("test receipt is not changeset-bound")
    _add(
        edges,
        event,
        "VALIDATED",
        "test_receipt",
        test_ref.id,
        "changeset",
        changeset_ref.id,
        paths,
    )
    for path in paths:
        _add(
            edges,
            event,
            "VALIDATED",
            "test_receipt",
            test_ref.id,
            "path",
            path,
            (path,),
        )


def _context_edges(snapshot: _Snapshot, event: Event, edges: set[_Edge]) -> None:
    if event.event_type not in {
        LineageEventType.CONTEXT_COMPILED,
        LineageEventType.CONTEXT_INJECTED,
    }:
        return
    brief_ref = _one_reference(event, EvidenceKind.CONTEXT_BRIEF)
    decision_ref = _one_reference(event, EvidenceKind.HANDOFF_DECISION)
    try:
        brief = ContextBrief.model_validate(snapshot.record(brief_ref.id))
        decision = HandoffDecision.model_validate(snapshot.record(decision_ref.id))
    except ValidationError as error:
        raise ExplainEvidenceError("context relationship is malformed") from error
    if (
        brief.brief_sha256 != event.payload.get("brief_sha256")
        or decision.decision_sha256 != event.payload.get("decision_sha256")
        or brief.repo_id != event.repo_id
        or brief.base_sha != event.base_sha
    ):
        raise ExplainEvidenceError("context relationship is not payload-bound")
    paths = tuple(
        sorted({*brief.required_paths, *brief.read_scope, *brief.write_scope})
    )
    if event.event_type == LineageEventType.CONTEXT_COMPILED:
        if (
            event.payload.get("brief_artifact_sha256") != brief_ref.sha256
            or event.payload.get("decision_artifact_sha256") != decision_ref.sha256
        ):
            raise ExplainEvidenceError("compiled context artifact digest changed")
        _add(
            edges,
            event,
            "COMPILED",
            "handoff_decision",
            decision_ref.id,
            "context_brief",
            brief_ref.id,
            paths,
        )
        included = {
            (entry.candidate_kind, entry.id, entry.sha256)
            for entry in decision.entries
            if entry.include
        }
        for selected in brief.selected_evidence:
            reference = selected.reference
            binding = snapshot.bindings.get(reference.id)
            if (
                binding is None
                or binding.sha256 != reference.sha256
                or ("source_artifact", reference.id, reference.sha256) not in included
            ):
                raise ExplainEvidenceError("brief evidence was not explicitly selected")
            selected_paths: tuple[str, ...] = ()
            if reference.kind == EvidenceKind.HUNK:
                try:
                    selected_paths = (
                        HunkEvidence.model_validate(snapshot.record(reference.id)).path,
                    )
                except ValidationError as error:
                    raise ExplainEvidenceError(
                        "selected context hunk is malformed"
                    ) from error
            _add(
                edges,
                event,
                "PACKED_IN",
                reference.kind.value,
                reference.id,
                "context_brief",
                brief_ref.id,
                selected_paths,
            )
        for selected in brief.approved_memories:
            matches: list[tuple[str, MemoryRevision]] = []
            for artifact_id, binding in snapshot.bindings.items():
                if EvidenceKind.MEMORY_REVISION.value not in binding.kinds:
                    continue
                try:
                    memory = MemoryRevision.model_validate(snapshot.record(artifact_id))
                except ValidationError as error:
                    raise ExplainEvidenceError(
                        "context memory revision is malformed"
                    ) from error
                if (
                    memory.state.value == "approved"
                    and memory.memory_id == selected.memory_id
                    and memory.revision == selected.revision
                    and memory.rule == selected.exact_text
                ):
                    matches.append((artifact_id, memory))
            if len(matches) != 1:
                raise ExplainEvidenceError(
                    "brief memory is not bound to one approved revision"
                )
            artifact_id, memory = matches[0]
            candidate_id = (
                "memory_revision:"
                + sha256_hex(f"{memory.memory_id}:{memory.revision}".encode())[:24]
            )
            candidate_sha256 = canonical_json_sha256(
                {
                    "candidate_kind": "memory_revision",
                    "value": memory.model_dump(mode="json"),
                }
            )
            if (
                "memory_revision",
                candidate_id,
                candidate_sha256,
            ) not in included:
                raise ExplainEvidenceError("brief memory was not explicitly selected")
            memory_paths = tuple(
                path
                for path in paths
                if any(fnmatchcase(path, pattern) for pattern in memory.path_globs)
            )
            _add(
                edges,
                event,
                "PACKED_IN",
                "memory_revision",
                artifact_id,
                "context_brief",
                brief_ref.id,
                memory_paths,
            )
    else:
        injection_ref = _one_reference(event, EvidenceKind.INJECTION_RECEIPT)
        try:
            injection = ContextInjectionReceipt.model_validate(
                snapshot.record(injection_ref.id)
            )
        except ValidationError as error:
            raise ExplainEvidenceError(
                "context injection receipt is malformed"
            ) from error
        if (
            injection.consumer_run_id != event.run_id
            or injection.brief_sha256 != brief.brief_sha256
            or injection.decision_sha256 != decision.decision_sha256
            or injection.receipt_sha256 != event.payload.get("injection_receipt_sha256")
            or injection.prior_message_count != event.payload.get("prior_message_count")
        ):
            raise ExplainEvidenceError("context injection is not payload-bound")
        _add(
            edges,
            event,
            "INJECTED_INTO",
            "context_brief",
            brief_ref.id,
            "run",
            event.run_id,
            paths,
        )


def _promotion_edges(snapshot: _Snapshot, event: Event, edges: set[_Edge]) -> None:
    if event.event_type == LineageEventType.PROMOTION_APPROVED:
        changeset_ref = _one_reference(event, EvidenceKind.CHANGESET)
        changeset = snapshot.record(changeset_ref.id)
        paths = tuple(changeset.get("changed_paths", ()))
        if changeset.get("candidate_patch_sha256") != event.payload.get(
            "candidate_patch_sha256"
        ):
            raise ExplainEvidenceError("promotion approval is not changeset-bound")
        _add(
            edges,
            event,
            "AUTHORIZED",
            "changeset",
            changeset_ref.id,
            "event",
            event.event_id,
            paths,
        )
        return
    if event.event_type != LineageEventType.PROMOTION_COMPLETED:
        return
    receipt_ref = _one_reference(event, EvidenceKind.PROMOTION_RECEIPT)
    receipt = snapshot.record(receipt_ref.id)
    if (
        event.payload.get("promotion_receipt_id") != receipt_ref.id
        or event.payload.get("promotion_receipt_sha256")
        != receipt.get("receipt_sha256")
        or receipt.get("candidate_patch_sha256")
        != event.payload.get("candidate_patch_sha256")
    ):
        raise ExplainEvidenceError("promotion receipt is not payload-bound")
    raw_references = receipt.get("artifact_references")
    if not isinstance(raw_references, list):
        raise ExplainEvidenceError("promotion receipt artifact bindings are malformed")
    try:
        nested = tuple(
            EvidenceReference.model_validate(item) for item in raw_references
        )
    except ValidationError as error:
        raise ExplainEvidenceError(
            "promotion receipt artifact binding is malformed"
        ) from error
    changesets = [item for item in nested if item.kind == EvidenceKind.CHANGESET]
    if len(changesets) != 1:
        raise ExplainEvidenceError("promotion receipt does not bind one changeset")
    changeset_ref = changesets[0]
    binding = snapshot.bindings.get(changeset_ref.id)
    if binding is None or binding.sha256 != changeset_ref.sha256:
        raise ExplainEvidenceError("promotion changeset is not authorized by this run")
    changeset = snapshot.record(changeset_ref.id)
    paths = tuple(changeset.get("changed_paths", ()))
    if changeset.get("candidate_patch_sha256") != receipt.get("candidate_patch_sha256"):
        raise ExplainEvidenceError("promotion receipt changeset digest changed")
    _add(
        edges,
        event,
        "PROMOTED_AS",
        "changeset",
        changeset_ref.id,
        "promotion_receipt",
        receipt_ref.id,
        paths,
    )


def _derive(
    snapshot: _Snapshot,
    query_path: str,
) -> tuple[set[_Edge], set[str]]:
    edges: set[_Edge] = set()
    for event in snapshot.events:
        _tool_edges(snapshot, event, edges)
        _changeset_edges(snapshot, event, edges)
        _feedback_edges(snapshot, event, edges)
        _memory_edges(snapshot, event, edges, query_path)
        _test_edges(snapshot, event, edges)
        _context_edges(snapshot, event, edges)
        _promotion_edges(snapshot, event, edges)
    used = {
        node_id
        for edge in edges
        for node_kind, node_id in (
            (edge.source_kind, edge.source_id),
            (edge.target_kind, edge.target_id),
        )
        if node_kind not in {"event", "path", "run"}
    }
    return edges, used


def _linked_source(snapshot: _Snapshot, store: ExplainStore) -> _Snapshot | None:
    injected = tuple(
        event
        for event in snapshot.events
        if event.event_type == LineageEventType.CONTEXT_INJECTED
    )
    if not injected:
        return None
    if len(injected) != 1:
        raise ExplainEvidenceError("run binds multiple context injections")
    event = injected[0]
    brief_ref = _one_reference(event, EvidenceKind.CONTEXT_BRIEF)
    try:
        brief = ContextBrief.model_validate(snapshot.record(brief_ref.id))
    except ValidationError as error:
        raise ExplainEvidenceError("injected source brief is malformed") from error
    if (
        event.payload.get("source_run_id") != brief.source_run_id
        or brief.source_run_id == snapshot.head.run_id
    ):
        raise ExplainEvidenceError("injected source run binding is invalid")
    source = _snapshot(store, snapshot.artifacts, brief.source_run_id)
    if (
        brief.source_head.seq < 1
        or brief.source_head.seq >= source.head.seq
        or source.events[brief.source_head.seq - 1].event_sha256
        != brief.source_head.event_sha256
    ):
        raise ExplainEvidenceError("injected source head is not a verified prefix")
    compiled = source.events[brief.source_head.seq]
    if (
        compiled.event_type != LineageEventType.CONTEXT_COMPILED
        or brief_ref not in compiled.references
        or compiled.payload.get("brief_sha256") != brief.brief_sha256
    ):
        raise ExplainEvidenceError("source run does not bind the injected brief")
    return source


def explain_path(
    store: ExplainStore,
    artifacts: ArtifactReader,
    run_id: str,
    path: str,
    *,
    max_observations: int = _DEFAULT_OBSERVATION_LIMIT,
    max_relationships: int = _DEFAULT_RELATIONSHIP_LIMIT,
) -> dict[str, object]:
    """Return bounded relationships whose stored bindings explicitly name a path."""

    try:
        path = _PATH.validate_python(path)
    except ValidationError as error:
        raise ValueError("path must be canonical and repository-relative") from error
    observation_limit = _positive_limit(max_observations, "max_observations", 256)
    relationship_limit = _positive_limit(max_relationships, "max_relationships", 256)
    snapshot = _snapshot(store, artifacts, run_id)
    source = _linked_source(snapshot, store)
    snapshots = (snapshot,) if source is None else (source, snapshot)
    if source is not None and set(source.by_event_id) & set(snapshot.by_event_id):
        raise ExplainEvidenceError("linked runs reuse an event identity")
    edges: set[_Edge] = set()
    used_artifacts: set[str] = set()
    for item in snapshots:
        derived, used = _derive(item, path)
        edges.update(derived)
        used_artifacts.update(used)
    selected = sorted(edge for edge in edges if path in edge.paths)
    by_event_id = {
        event_id: event
        for item in snapshots
        for event_id, event in item.by_event_id.items()
    }
    event_order = {
        event.event_id: (snapshot_index, event.seq)
        for snapshot_index, item in enumerate(snapshots)
        for event in item.events
    }
    observation_ids = sorted(
        {
            edge.event_id
            for edge in selected
            if by_event_id[edge.event_id].event_type == LineageEventType.TOOL_COMPLETED
        },
        key=event_order.__getitem__,
    )
    observations = [
        {
            "event_id": event.event_id,
            "seq": event.seq,
            "event_type": event.event_type.value,
            "operation": event.payload.get("operation"),
            "status": event.payload.get("status"),
            "truth_kind": event.truth_kind.value,
            "authority": event.authority.value,
        }
        for event in (
            by_event_id[event_id] for event_id in observation_ids[:observation_limit]
        )
    ]
    relationships = [edge.public() for edge in selected[:relationship_limit]]
    unused = Counter(
        kind
        for artifact_id, kind in {
            (artifact_id, kind)
            for item in snapshots
            for artifact_id, binding in item.bindings.items()
            if artifact_id not in used_artifacts
            for kind in binding.kinds
        }
    )
    omissions = {
        "observations_due_to_limit": max(0, len(observation_ids) - len(observations)),
        "relationships_due_to_limit": max(0, len(selected) - len(relationships)),
        "unmodeled_bound_artifacts_by_kind": dict(sorted(unused.items())),
    }
    unknowns = [
        "Timing does not prove causality.",
        "Relationships without an explicit stored payload/reference binding are unknown.",
        "Whole-repository impact is unknown.",
    ]
    if not selected:
        unknowns.append("No stored relationship binds the requested path in this run.")
    return {
        "query": "why",
        "run_id": run_id,
        "path": path,
        "head": snapshot.head.model_dump(mode="json"),
        "observations": observations,
        "relationships": relationships,
        "omissions": omissions,
        "unknowns": unknowns,
    }


__all__ = [
    "ArtifactReader",
    "ExplainError",
    "ExplainEvidenceError",
    "ExplainNotFound",
    "ExplainStore",
    "explain_path",
    "inspect_run_item",
]
