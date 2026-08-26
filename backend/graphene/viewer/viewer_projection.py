from __future__ import annotations

import base64
import json
import sqlite3
import stat
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..hashing import canonical_json_bytes, canonical_json_sha256
from ..lineage.artifacts import SQLiteArtifactStore
from ..lineage.promotion import PromotionCheckpointError, SQLiteCheckpointRecorder
from ..lineage.lineage_reducer import ProjectionError, reduce_events
from ..lineage.sqlite_lineage_store import (
    CheckpointReader,
    EvidenceInvalid,
    LineageStoreError,
    SQLiteLineageStore,
)
from ..core_models import Event, EvidenceInvalidState, LineageEventType, LineageOperation
from .contract import (
    GraphDelta,
    GraphSnapshot,
    ReviewBrief,
    ReviewFact,
    ReviewSection,
    ViewCounts,
    ViewEdge,
    ViewHead,
    ViewMemoryScope,
    ViewNode,
    ViewReference,
    VerifiedSupportPath,
)

MAX_FAMILY_RUNS = 16
MAX_DATABASE_RUNS = 256
MAX_NODES = 320
MAX_EDGES = 640
MAX_REVIEW_PATHS = 30
UNKNOWN_LIMITS = (
    "Timing does not prove causality.",
    "The view includes only explicit committed Graphene evidence.",
    "Graph layout and sequence do not prove importance, correctness, or causality.",
    "No pull request, push, deployment, or activity outside Graphene's six scoped operations was observed.",
    "An isolated local Git commit is not established without an explicit local-result event.",
)

SUPPORT_EDGE_KINDS = frozenset(
    {"supported_by", "authorized_by", "changes_path", "binds_path", "result_supported_by"}
)


class ViewerEvidenceInvalid(RuntimeError):
    pass


class ViewerRunNotFound(LookupError):
    pass


def database_identity(path: str | Path) -> tuple[int, int]:
    try:
        metadata = Path(path).stat(follow_symlinks=False)
    except OSError as error:
        raise ViewerEvidenceInvalid("lineage database identity is unavailable") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise ViewerEvidenceInvalid("lineage database is not a regular file")
    return metadata.st_dev, metadata.st_ino


def _store(path: Path) -> tuple[SQLiteLineageStore, CheckpointReader | None]:
    artifacts = SQLiteArtifactStore(path, read_only=True)
    try:
        checkpoints = SQLiteCheckpointRecorder(path, read_only=True).read
    except PromotionCheckpointError:
        checkpoints = None
    return (
        SQLiteLineageStore(
            path,
            artifact_resolver=artifacts.resolve,
            checkpoint_reader=checkpoints,
            read_only=True,
        ),
        checkpoints,
    )


def _run_ids(path: Path) -> tuple[str, ...]:
    target = path.resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(target, uri=True)) as connection:
            rows = connection.execute(
                "SELECT run_id FROM run_heads ORDER BY run_id LIMIT ?",
                (MAX_DATABASE_RUNS + 1,),
            ).fetchall()
    except sqlite3.Error as error:
        raise ViewerEvidenceInvalid("lineage run enumeration failed") from error
    if len(rows) > MAX_DATABASE_RUNS:
        raise ViewerEvidenceInvalid("lineage database exceeds the bounded run limit")
    return tuple(str(row[0]) for row in rows)


def _verified_events(
    store: SQLiteLineageStore,
    run_id: str,
    *,
    checkpoint_reader: CheckpointReader | None,
) -> tuple[Event, ...]:
    state = store.verify(run_id)
    if isinstance(state, EvidenceInvalidState):
        raise ViewerEvidenceInvalid(f"{run_id}: {state.reason}")
    if state.seq == 0:
        raise ViewerRunNotFound(run_id)
    try:
        events = store.tail(run_id, 0, min(256, state.seq))
        while events and events[-1].seq < state.seq:
            events += store.tail(run_id, events[-1].seq, min(256, state.seq - events[-1].seq))
    except EvidenceInvalid as error:
        raise ViewerEvidenceInvalid(f"{run_id}: {error.state.reason}") from error
    if (
        len(events) != state.seq
        or events[-1].event_sha256 != state.event_sha256
        or tuple(event.seq for event in events) != tuple(range(1, state.seq + 1))
    ):
        raise ViewerEvidenceInvalid(f"{run_id}: verified prefix changed during replay")
    promotions = tuple(
        event
        for event in events
        if event.event_type == LineageEventType.PROMOTION_COMPLETED
    )
    if promotions:
        try:
            checkpoints = () if checkpoint_reader is None else tuple(checkpoint_reader(run_id))
        except Exception as error:
            raise ViewerEvidenceInvalid(
                f"{run_id}: promotion checkpoint evidence is unreadable"
            ) from error
        if any(
            not any(
                checkpoint.purpose == "promotion_precommit"
                and checkpoint.expected_seq == promotion.seq - 1
                for checkpoint in checkpoints
            )
            for promotion in promotions
        ):
            raise ViewerEvidenceInvalid(
                f"{run_id}: promotion checkpoint evidence is unavailable"
            )
    return events


def _family(path: Path, root_run_id: str) -> tuple[dict[str, tuple[Event, ...]], int]:
    store, checkpoint_reader = _store(path)
    valid: dict[str, tuple[Event, ...]] = {}
    invalid: dict[str, ViewerEvidenceInvalid] = {}
    for run_id in _run_ids(path):
        try:
            valid[run_id] = _verified_events(
                store, run_id, checkpoint_reader=checkpoint_reader
            )
        except ViewerEvidenceInvalid as error:
            invalid[run_id] = error
    if invalid:
        raise invalid[sorted(invalid)[0]]
    if root_run_id not in valid:
        raise ViewerRunNotFound(root_run_id)

    related = {root_run_id}
    changed = True
    while changed:
        changed = False
        for run_id, events in valid.items():
            source = events[0].payload.get("source_run_id")
            if run_id in related or source in related:
                before = len(related)
                related.add(run_id)
                if isinstance(source, str) and source in valid:
                    related.add(source)
                changed |= len(related) != before
    ordered = sorted(related, key=lambda value: (value != root_run_id, value))
    omitted = max(0, len(ordered) - MAX_FAMILY_RUNS)
    return {run_id: valid[run_id] for run_id in ordered[:MAX_FAMILY_RUNS]}, omitted


def _reference(value: Any) -> ViewReference:
    return ViewReference(kind=value.kind.value, id=value.id, sha256=value.sha256)


def _node_id(prefix: str, *parts: str) -> str:
    return ":".join((prefix, *parts))


def _add_edge(
    edges: dict[str, ViewEdge],
    source: str,
    target: str,
    kind: str,
    event: Event,
    *,
    relationship_class: str = "membership",
    support_path: bool = False,
) -> None:
    if support_path and (
        relationship_class not in {"verified_support", "authorization"}
        or kind not in SUPPORT_EDGE_KINDS
    ):
        raise ViewerEvidenceInvalid("support relationship is not directionally allowlisted")
    identity = canonical_json_sha256(
        {"kind": kind, "source": source, "target": target}
    )
    edge_id = f"edge:{identity}"
    previous = edges.get(edge_id)
    edges[edge_id] = ViewEdge(
        id=edge_id,
        source=source,
        target=target,
        kind=kind,
        activity_count=min(32, 1 + (previous.activity_count if previous else 0)),
        run_id=event.run_id,
        seq=event.seq,
        event_id=event.event_id,
        evidence_ref=ViewReference(kind="event", id=event.event_id, sha256=event.event_sha256),
        relationship_class=relationship_class,
        support_path=support_path,
    )


_ENTITY_KIND = {
    LineageEventType.CANDIDATE_CREATED: "changeset",
    LineageEventType.CANDIDATE_REJECTED: "result",
    LineageEventType.CHANGESET_PARSED: "changeset",
    LineageEventType.TEST_RECEIPT_CREATED: "test",
    LineageEventType.FEEDBACK_RECORDED: "feedback",
    LineageEventType.MEMORY_PROPOSED: "memory",
    LineageEventType.MEMORY_APPROVED: "memory",
    LineageEventType.MEMORY_REJECTED: "memory",
    LineageEventType.CLARIFICATION_ASKED: "human",
    LineageEventType.CLARIFICATION_ANSWERED: "human",
    LineageEventType.PROMOTION_APPROVED: "promotion",
    LineageEventType.PROMOTION_DENIED: "promotion",
    LineageEventType.PROMOTION_COMPLETED: "promotion",
    LineageEventType.CONTEXT_COMPILED: "handoff",
    LineageEventType.CONTEXT_INJECTED: "handoff",
    LineageEventType.HANDOFF_DENIED: "policy",
    LineageEventType.SCOPE_ALLOWED: "policy",
    LineageEventType.SCOPE_DENIED: "policy",
    LineageEventType.COMPLETION_DENIED: "policy",
}

_LABELS = {
    event_type: event_type.value.replace(".", " ").replace("_", " ").title()
    for event_type in _ENTITY_KIND
}

_STAGE_ORDER = {
    "source_work": 0,
    "human_correction_scope": 1,
    "approved_handoff": 2,
    "consumer_work": 3,
    "candidate_decision": 4,
    "local_result": 5,
}


def _stage(event: Event, *, consumer: bool) -> str:
    if event.event_type in {
        LineageEventType.CLARIFICATION_ASKED,
        LineageEventType.CLARIFICATION_ANSWERED,
        LineageEventType.FEEDBACK_RECORDED,
        LineageEventType.MEMORY_PROPOSED,
        LineageEventType.MEMORY_APPROVED,
        LineageEventType.MEMORY_REJECTED,
    }:
        return "human_correction_scope"
    if event.event_type in {
        LineageEventType.CONTEXT_COMPILED,
        LineageEventType.CONTEXT_INJECTED,
        LineageEventType.HANDOFF_DENIED,
    }:
        return "approved_handoff"
    if event.event_type in {
        LineageEventType.PROMOTION_COMPLETED,
        LineageEventType.LOCAL_RESULT_RECORDED,
    }:
        return "local_result"
    if event.event_type in {
        LineageEventType.CHANGESET_PARSED,
        LineageEventType.TEST_RECEIPT_CREATED,
        LineageEventType.CANDIDATE_CREATED,
        LineageEventType.CANDIDATE_REJECTED,
        LineageEventType.PROMOTION_APPROVED,
        LineageEventType.PROMOTION_DENIED,
        LineageEventType.COMPLETION_DENIED,
    }:
        return "candidate_decision"
    return "consumer_work" if consumer else "source_work"


def _reference_edge(event: Event) -> tuple[str, str, bool]:
    if (
        event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == LineageOperation.OPEN_EVIDENCE.value
    ):
        return "opens_reference", "context_transfer", False
    if event.event_type in {
        LineageEventType.CANDIDATE_REJECTED,
        LineageEventType.LOCAL_RESULT_RECORDED,
    }:
        return "result_supported_by", "verified_support", True
    if event.event_type == LineageEventType.PROMOTION_COMPLETED:
        return "result_supported_by", "verified_support", True
    if event.event_type == LineageEventType.PROMOTION_APPROVED:
        return "authorized_by", "authorization", True
    if event.event_type in {
        LineageEventType.CANDIDATE_CREATED,
        LineageEventType.CHANGESET_PARSED,
        LineageEventType.TEST_RECEIPT_CREATED,
    }:
        return "supported_by", "verified_support", True
    if event.event_type in {
        LineageEventType.CONTEXT_COMPILED,
        LineageEventType.CONTEXT_INJECTED,
    }:
        return "transfers_context", "context_transfer", False
    if event.event_type == LineageEventType.HANDOFF_DENIED:
        return "supported_by", "verified_support", True
    if event.event_type in {
        LineageEventType.MEMORY_APPROVED,
        LineageEventType.MEMORY_REJECTED,
    }:
        return "authorizes", "authorization", False
    return "references", "verified_support", False

_SAFE_METADATA = (
    "operation",
    "path",
    "reason_code",
    "passed",
    "choice",
    "question_id",
    "scope_id",
    "hunk_id",
    "memory_id",
    "operator_label",
    "status",
    "evidence_count",
    "memory_count",
    "model_dispatch_count",
    "source_path_count",
    "tool_count",
    "candidate_id",
    "candidate_patch_sha256",
    "candidate_tree_sha256",
    "candidate_tree_hash_version",
    "decision_id",
    "changed_paths",
    "changed_path_count",
    "hunk_count",
    "outcome",
    "local_commit_sha",
    "pushed",
    "pull_request_created",
    "deployed",
    "revision",
    "target_profile_id",
    "task_id",
    "source_run_id",
)


def _build_graph(
    family: dict[str, tuple[Event, ...]],
) -> tuple[list[ViewNode], list[ViewEdge], list[ViewHead], dict[str, int]]:
    nodes: dict[str, ViewNode] = {}
    edges: dict[str, ViewEdge] = {}
    heads: list[ViewHead] = []
    omitted: dict[str, int] = {}
    event_nodes: dict[str, str] = {}
    evidence_contexts: dict[str, list[tuple[str, str, str]]] = {}

    for run_id, events in family.items():
        projection = reduce_events(events)
        consumer = isinstance(events[0].payload.get("source_run_id"), str)
        omitted.update(
            {
                f"{run_id}:{key}": value
                for key, value in projection.omitted_counts.items()
                if value
            }
        )
        heads.append(
            ViewHead(
                run_id=run_id,
                seq=projection.head_seq,
                event_sha256=projection.head_sha256,
                projection_sha256=projection.projection_sha256,
            )
        )
        run_node = _node_id("run", run_id)
        nodes[run_node] = ViewNode(
            id=run_node,
            kind="agent",
            status=projection.state.value,
            truth_kind="server_derived",
            activity_count=min(32, len(events)),
            label=events[0].agent_profile_id.split("@", 1)[0].replace("-", " ").title(),
            run_id=run_id,
            seq=projection.head_seq,
            event_id=events[-1].event_id,
            recorded_at=events[-1].server_recorded_at,
            source_ref=_reference(events[-1].source_ref),
            metadata={
                "agent_profile_id": events[0].agent_profile_id,
                "base_sha": events[0].base_sha,
                "projection_sha256": projection.projection_sha256,
            },
            stage="consumer_work" if consumer else "source_work",
        )
        source_run = events[0].payload.get("source_run_id")
        if isinstance(source_run, str) and source_run in family:
            _add_edge(
                edges,
                _node_id("run", source_run),
                run_node,
                "continued_as",
                events[0],
                relationship_class="handoff_continuation",
            )

        statuses = {item.event_id: item.status for item in projection.event_rail}
        visible_events = tuple(events[item.seq - 1] for item in projection.event_rail)
        invocation_activity: dict[str, int] = {}
        tool_activity: dict[str, int] = {}
        for event in visible_events:
            if event.invocation_id:
                invocation_activity[event.invocation_id] = invocation_activity.get(event.invocation_id, 0) + 1
            if event.tool_call_id:
                tool_activity[event.tool_call_id] = tool_activity.get(event.tool_call_id, 0) + 1

        for event in visible_events:
            source_ref = _reference(event.source_ref)
            parent = run_node
            reference_owner: str | None = None
            if event.invocation_id:
                invocation_id = _node_id("invocation", run_id, event.invocation_id)
                parent = invocation_id
                nodes[invocation_id] = ViewNode(
                    id=invocation_id,
                    kind="agent",
                    status=statuses[event.event_id],
                    truth_kind=event.truth_kind.value,
                    activity_count=min(32, invocation_activity[event.invocation_id]),
                    label="Agent Invocation",
                    run_id=run_id,
                    seq=event.seq,
                    event_id=event.event_id,
                    recorded_at=event.server_recorded_at,
                    source_ref=source_ref,
                    metadata={"adapter_kind": event.payload.get("adapter_kind", "unknown")},
                    stage=_stage(event, consumer=consumer),
                )
                _add_edge(edges, run_node, invocation_id, "contains", event)

            if event.tool_call_id and event.payload.get("operation"):
                operation = str(event.payload["operation"])
                tool_id = _node_id("tool", run_id, event.tool_call_id)
                nodes[tool_id] = ViewNode(
                    id=tool_id,
                    kind="test" if operation == LineageOperation.RUN_FIXED_TEST.value else "tool",
                    status=statuses[event.event_id],
                    truth_kind=event.truth_kind.value,
                    activity_count=min(32, tool_activity[event.tool_call_id]),
                    label=operation.replace("_", " ").title(),
                    run_id=run_id,
                    seq=event.seq,
                    event_id=event.event_id,
                    recorded_at=event.server_recorded_at,
                    source_ref=source_ref,
                    metadata={key: event.payload[key] for key in _SAFE_METADATA if key in event.payload},
                    stage=_stage(event, consumer=consumer),
                )
                _add_edge(edges, parent, tool_id, "performed", event)
                event_nodes[event.event_id] = tool_id
                reference_owner = tool_id

            kind = (
                "result"
                if event.event_type == LineageEventType.LOCAL_RESULT_RECORDED
                else _ENTITY_KIND.get(event.event_type)
            )
            if kind:
                entity_id = _node_id("event", run_id, event.event_id)
                event_nodes[event.event_id] = entity_id
                nodes[entity_id] = ViewNode(
                    id=entity_id,
                    kind=kind,
                    status=statuses[event.event_id],
                    truth_kind=event.truth_kind.value,
                    activity_count=min(32, 1 + len(event.references)),
                    label=(
                        "Local Result Recorded"
                        if event.event_type == LineageEventType.LOCAL_RESULT_RECORDED
                        else _LABELS[event.event_type]
                    ),
                    run_id=run_id,
                    seq=event.seq,
                    event_id=event.event_id,
                    recorded_at=event.server_recorded_at,
                    source_ref=source_ref,
                    metadata={key: event.payload[key] for key in _SAFE_METADATA if key in event.payload},
                    stage=_stage(event, consumer=consumer),
                )
                _add_edge(edges, parent, entity_id, "recorded", event)
                reference_owner = entity_id
            if reference_owner is not None:
                for reference in event.references:
                    if reference.kind.value == "event":
                        continue
                    reference_id = _node_id("evidence", reference.kind.value, reference.id)
                    nodes.setdefault(
                        reference_id,
                        ViewNode(
                            id=reference_id,
                            kind="evidence",
                            status="VERIFIED",
                            truth_kind="evidence_bound",
                            activity_count=1,
                            label=reference.kind.value.replace("_", " ").title(),
                            source_ref=_reference(reference),
                            metadata={"shared_reference": True},
                            stage=_stage(event, consumer=consumer),
                        ),
                    )
                    evidence_contexts.setdefault(reference_id, []).append(
                        (
                            _stage(event, consumer=consumer),
                            "consumer" if consumer else "source",
                            event.event_type.value,
                        )
                    )
                    edge_kind, relationship_class, support_path = _reference_edge(event)
                    _add_edge(
                        edges,
                        reference_owner,
                        reference_id,
                        edge_kind,
                        event,
                        relationship_class=relationship_class,
                        support_path=support_path,
                    )

        file_nodes: dict[str, str] = {}
        for file in projection.files:
            file_id = _node_id(
                "file",
                run_id,
                canonical_json_sha256({"path": file.path, "repo": events[0].repo_id}),
            )
            evidence_event = events[file.last_seq - 1]
            file_nodes[file.path] = file_id
            nodes[file_id] = ViewNode(
                id=file_id,
                kind="file",
                status=file.state,
                truth_kind="runtime_observed",
                activity_count=min(32, max(1, file.read_count + file.added_lines + file.deleted_lines)),
                label=file.path,
                run_id=run_id,
                seq=file.last_seq,
                event_id=evidence_event.event_id,
                recorded_at=evidence_event.server_recorded_at,
                source_ref=_reference(evidence_event.source_ref),
                metadata={
                    "path": file.path,
                    "read_count": file.read_count,
                    "added_lines": file.added_lines,
                    "deleted_lines": file.deleted_lines,
                    "bound_test_pass": file.bound_test_pass,
                    "file_version_id": file.file_version_id,
                },
                stage=_stage(evidence_event, consumer=consumer),
            )
            _add_edge(edges, run_node, file_id, "observed", evidence_event)

        path_events = tuple(
            event
            for event in visible_events
            if event.event_type
            in {LineageEventType.CHANGESET_PARSED, LineageEventType.TEST_RECEIPT_CREATED}
        )
        for event in path_events:
            field = (
                "changed_paths"
                if event.event_type == LineageEventType.CHANGESET_PARSED
                else "bound_paths"
            )
            for path in event.payload.get(field, ()):
                file_id = file_nodes.get(path)
                if file_id is None:
                    file_id = _node_id(
                        "file",
                        run_id,
                        canonical_json_sha256({"path": path, "repo": events[0].repo_id}),
                    )
                    file_nodes[path] = file_id
                    nodes[file_id] = ViewNode(
                        id=file_id,
                        kind="file",
                        status="CHANGED_REFERENCE" if field == "changed_paths" else "BOUND_REFERENCE",
                        truth_kind=event.truth_kind.value,
                        activity_count=1,
                        label=path,
                        run_id=run_id,
                        seq=event.seq,
                        event_id=event.event_id,
                        recorded_at=event.server_recorded_at,
                        source_ref=_reference(event.source_ref),
                        metadata={"path": path, "public_reference": field},
                        stage="candidate_decision",
                    )
                source_id = event_nodes.get(event.event_id)
                if source_id:
                    _add_edge(
                        edges,
                        source_id,
                        file_id,
                        "changes_path" if field == "changed_paths" else "binds_path",
                        event,
                        relationship_class="verified_support",
                        support_path=True,
                    )

    for events in family.values():
        projection = reduce_events(events)
        for item in projection.event_rail:
            event = events[item.seq - 1]
            source = event_nodes.get(event.event_id)
            if source is None:
                continue
            for reference in event.references:
                target = event_nodes.get(reference.id)
                if target:
                    edge_kind, relationship_class, support_path = _reference_edge(event)
                    _add_edge(
                        edges,
                        source,
                        target,
                        edge_kind,
                        event,
                        relationship_class=relationship_class,
                        support_path=support_path,
                    )

    for node_id, contexts in evidence_contexts.items():
        node = nodes[node_id]
        canonical_contexts = tuple(sorted(set(contexts)))
        stages = tuple(sorted({item[0] for item in canonical_contexts}, key=_STAGE_ORDER.get))
        run_roles = tuple(sorted({item[1] for item in canonical_contexts}))
        roles = tuple(sorted({item[2] for item in canonical_contexts}))
        context = stages[-1].replace("_", " ").title() if stages else "Evidence"
        role = (
            roles[0].replace(".", " ").replace("_", " ").title()
            if len(roles) == 1
            else f"{len(roles)} roles"
        )
        nodes[node_id] = node.model_copy(
            update={
                "activity_count": min(32, len(contexts)),
                "label": f"{node.label} · {context} · {role} · {len(contexts)} ref{'s' if len(contexts) != 1 else ''}",
                "metadata": {
                    "shared_reference": True,
                    "reference_count": len(contexts),
                    "stages": stages,
                    "run_roles": run_roles,
                    "roles": roles,
                },
                "stage": stages[-1] if stages else node.stage,
            }
        )

    all_nodes = list(nodes.values())
    if len(all_nodes) > MAX_NODES:
        omitted["nodes"] = len(all_nodes) - MAX_NODES
        run_nodes = sorted(
            (item for item in all_nodes if item.id.startswith("run:")),
            key=lambda item: item.id,
        )[:MAX_NODES]
        recent = sorted(
            (item for item in all_nodes if not item.id.startswith("run:")),
            key=lambda item: (item.seq or 0, item.id),
            reverse=True,
        )[: MAX_NODES - len(run_nodes)]
        all_nodes = [*run_nodes, *recent]
    ordered_nodes = sorted(
        all_nodes,
        key=lambda item: (item.run_id or "", item.seq or 0, item.kind, item.id),
    )
    visible = {item.id for item in ordered_nodes}
    ordered_edges = sorted(
        (item for item in edges.values() if item.source in visible and item.target in visible),
        key=lambda item: item.id,
    )
    omitted_edges = len(edges) - len(ordered_edges)
    if len(ordered_edges) > MAX_EDGES:
        omitted_edges += len(ordered_edges) - MAX_EDGES
        ordered_edges = ordered_edges[:MAX_EDGES]
    if omitted_edges:
        omitted["edges"] = omitted_edges
    return ordered_nodes, ordered_edges, sorted(heads, key=lambda item: item.run_id), omitted


_SECTION_TITLES = {
    "attention": "Needs attention now",
    "candidate": "Candidate / changed paths",
    "verified_evidence": "Verified evidence",
    "human_intervention": "Human intervention",
    "inherited_context": "Inherited context: included and excluded",
    "outcome": "Outcome",
    "unknown": "Unknown / not captured",
}


def _fact(
    fact_id: str,
    section: str,
    text: str,
    *,
    status: str = "established",
    truth_kind: str = "server_derived",
    node_ids: Iterable[str] = (),
    edges: Iterable[ViewEdge] = (),
    metadata: dict[str, Any] | None = None,
) -> ReviewFact:
    ids = set(node_ids)
    supporting_edges = tuple(
        edge
        for edge in edges
        if edge.relationship_class != "membership"
        and (edge.source in ids or edge.target in ids)
    )
    ids.update(
        endpoint
        for edge in supporting_edges
        for endpoint in (edge.source, edge.target)
    )
    focused_ids = tuple(sorted(ids))[:32]
    focused_edges = tuple(
        edge
        for edge in supporting_edges
        if edge.source in focused_ids and edge.target in focused_ids
    )
    return ReviewFact(
        id=fact_id,
        section=section,
        status=status,
        text=text,
        truth_kind=truth_kind,
        node_ids=focused_ids,
        edge_ids=tuple(sorted(edge.id for edge in focused_edges))[:64],
        metadata=metadata or {},
    )


def _path_fact_text(label: str, paths: tuple[str, ...], total: int) -> str:
    text = f"{label}: {', '.join(paths)}."
    if len(text) <= 512:
        return text
    return f"{label}: {len(paths)} of {total} safe path references; inspect the structured path list."


def _memory_scopes(events: Iterable[Event]) -> tuple[ViewMemoryScope, ...]:
    scopes: dict[tuple[str, int], ViewMemoryScope] = {}
    try:
        for event in events:
            raw = event.payload.get("memory_scopes", ())
            if not isinstance(raw, (list, tuple)):
                raise TypeError
            for item in raw:
                scope = ViewMemoryScope.model_validate(item)
                key = (scope.memory_id, scope.revision)
                if key in scopes and scopes[key] != scope:
                    raise ValueError
                scopes[key] = scope
    except (TypeError, ValueError, ValidationError) as error:
        raise ViewerEvidenceInvalid("compiled memory scope is invalid") from error
    return tuple(scopes[key] for key in sorted(scopes))


def _build_review_brief(
    family: dict[str, tuple[Event, ...]],
    nodes: list[ViewNode],
    edges: list[ViewEdge],
    omitted: dict[str, int],
    unknowns: tuple[str, ...],
) -> ReviewBrief:
    all_events = tuple(
        sorted(
            (
                events[item.seq - 1]
                for events in family.values()
                for item in reduce_events(events).event_rail
            ),
            key=lambda event: (
                event.server_recorded_at,
                event.run_id,
                event.seq,
                event.event_id,
            ),
        )
    )
    visible_ids = {node.id for node in nodes}
    nodes_by_event: dict[str, list[str]] = {}
    for node in nodes:
        if node.event_id and not node.id.startswith("run:"):
            nodes_by_event.setdefault(node.event_id, []).append(node.id)

    def event_nodes(events: Iterable[Event]) -> tuple[str, ...]:
        return tuple(
            node_id
            for event in events
            for node_id in nodes_by_event.get(event.event_id, ())
            if node_id in visible_ids
        )

    questions = {
        (event.run_id, event.payload.get("question_id")): event
        for event in all_events
        if event.event_type == LineageEventType.CLARIFICATION_ASKED
    }
    answered = {
        (event.run_id, event.payload.get("question_id"))
        for event in all_events
        if event.event_type == LineageEventType.CLARIFICATION_ANSWERED
    }
    proposals = {
        (
            event.run_id,
            event.payload.get("memory_id"),
            event.payload.get("revision"),
        ): event
        for event in all_events
        if event.event_type == LineageEventType.MEMORY_PROPOSED
    }
    memory_decisions = {
        (
            event.run_id,
            event.payload.get("memory_id"),
            event.payload.get("revision"),
        )
        for event in all_events
        if event.event_type
        in {LineageEventType.MEMORY_APPROVED, LineageEventType.MEMORY_REJECTED}
    }
    candidates = {
        (event.run_id, event.payload.get("candidate_patch_sha256")): event
        for event in all_events
        if event.event_type == LineageEventType.CANDIDATE_CREATED
    }
    candidate_decisions = {
        (event.run_id, event.payload.get("candidate_patch_sha256"))
        for event in all_events
        if event.event_type
        in {
            LineageEventType.CANDIDATE_REJECTED,
            LineageEventType.PROMOTION_APPROVED,
            LineageEventType.PROMOTION_DENIED,
        }
    }
    pending: list[tuple[int, int, Event, str]] = []
    pending.extend(
        (1, event.seq, event, "Scope decision is awaiting an explicit answer.")
        for key, event in questions.items()
        if key not in answered
    )
    pending.extend(
        (2, event.seq, event, "Memory revision is awaiting approval or rejection.")
        for key, event in proposals.items()
        if key not in memory_decisions
    )
    pending.extend(
        (3, event.seq, event, "Candidate is awaiting approval or rejection.")
        for key, event in candidates.items()
        if key not in candidate_decisions
    )
    if pending:
        _priority, _seq, pending_event, pending_text = max(
            pending, key=lambda item: (item[0], item[1], item[2].run_id)
        )
        attention = _fact(
            "attention:pending",
            "attention",
            pending_text,
            status="pending",
            truth_kind=pending_event.truth_kind.value,
            node_ids=event_nodes((pending_event,)),
            edges=edges,
            metadata={"event_id": pending_event.event_id, "pending_count": len(pending)},
        )
    else:
        attention = _fact(
            "attention:clear",
            "attention",
            "No unresolved Graphene decision.",
            metadata={"pending_count": 0},
        )

    changesets = tuple(
        event for event in all_events if event.event_type == LineageEventType.CHANGESET_PARSED
    )[-1:]
    tests = tuple(
        event for event in all_events if event.event_type == LineageEventType.TEST_RECEIPT_CREATED
    )[-1:]
    all_changed_paths = tuple(
        sorted(
            {
                path
                for event in changesets
                for path in event.payload.get("changed_paths", ())
            }
        )
    )
    all_bound_paths = tuple(
        sorted(
            {
                path
                for event in tests
                for path in event.payload.get("bound_paths", ())
            }
        )
    )
    changed_paths = all_changed_paths[:MAX_REVIEW_PATHS]
    bound_paths = all_bound_paths[:MAX_REVIEW_PATHS]
    if len(all_changed_paths) > len(changed_paths):
        omitted["review_changed_paths"] = len(all_changed_paths) - len(changed_paths)
    if len(all_bound_paths) > len(bound_paths):
        omitted["review_bound_paths"] = len(all_bound_paths) - len(bound_paths)
    changed_path_nodes = tuple(
        node.id
        for node in nodes
        if node.kind == "file" and node.metadata.get("path") in set(changed_paths)
    )
    bound_path_nodes = tuple(
        node.id
        for node in nodes
        if node.kind == "file" and node.metadata.get("path") in set(bound_paths)
    )
    candidate_facts = (
        _fact(
            "candidate:paths",
            "candidate",
            (
                _path_fact_text(
                    "Captured changed paths",
                    changed_paths,
                    len(all_changed_paths),
                )
                if changed_paths
                else "Exact changed paths were not established by captured evidence."
            ),
            status="established" if changed_paths else "not_established",
            node_ids=(*event_nodes(changesets), *changed_path_nodes),
            edges=edges,
            metadata={
                "changed_paths": changed_paths,
                "changed_path_count": len(all_changed_paths),
            },
        ),
        _fact(
            "candidate:hunks",
            "candidate",
            (
                f"Captured hunk count: {sum(int(event.payload.get('hunk_count', 0)) for event in changesets)}."
                if changesets
                else "Hunk count was not established by captured evidence."
            ),
            status="established" if changesets else "not_established",
            node_ids=event_nodes(changesets),
            edges=edges,
            metadata={
                "hunk_count": sum(
                    int(event.payload.get("hunk_count", 0)) for event in changesets
                )
            },
        ),
        _fact(
            "candidate:bound_test",
            "candidate",
            (
                _path_fact_text(
                    "Passing fixed-test receipt is bound to",
                    bound_paths,
                    len(all_bound_paths),
                )
                if any(event.payload.get("passed") is True for event in tests) and bound_paths
                else "A passing fixed-test receipt bound to candidate paths was not established by captured evidence."
            ),
            status=(
                "established"
                if any(event.payload.get("passed") is True for event in tests) and bound_paths
                else "not_established"
            ),
            node_ids=(*event_nodes(tests), *bound_path_nodes),
            edges=edges,
            metadata={
                "bound_paths": bound_paths,
                "bound_path_count": len(all_bound_paths),
                "passed": any(event.payload.get("passed") is True for event in tests),
            },
        ),
    )

    all_denied = tuple(
        event for event in all_events if event.event_type == LineageEventType.HANDOFF_DENIED
    )
    denied = all_denied[-24:]
    if len(all_denied) > len(denied):
        omitted["review_handoff_denials"] = len(all_denied) - len(denied)
    denial_count_keys = (
        "evidence_count",
        "memory_count",
        "model_dispatch_count",
        "source_path_count",
        "tool_count",
    )
    verified_facts = tuple(
        _fact(
            f"evidence:handoff_denial:{event.event_id}",
            "verified_evidence",
            (
                f"{str(event.payload.get('target_profile_id', 'Unknown target')).split('@', 1)[0].replace('-', ' ').title()} "
                "handoff was denied with zero evidence, memory, source paths, tools, and model dispatch."
                if all(int(event.payload.get(key, 0)) == 0 for key in denial_count_keys)
                else f"{str(event.payload.get('target_profile_id', 'Unknown target')).split('@', 1)[0].replace('-', ' ').title()} handoff denial counts were captured."
            ),
            status="historical",
            truth_kind=event.truth_kind.value,
            node_ids=event_nodes((event,)),
            edges=edges,
            metadata={
                **{key: int(event.payload.get(key, 0)) for key in denial_count_keys},
                "reason_code": event.payload.get("reason_code"),
                "target_profile_id": event.payload.get("target_profile_id"),
            },
        )
        for event in denied
    ) or (
        _fact(
            "evidence:handoff_denial:none",
            "verified_evidence",
            "A denied handoff was not established by captured evidence.",
            status="not_established",
        ),
    )

    human_events = tuple(
        event
        for event in all_events
        if event.event_type
        in {
            LineageEventType.CLARIFICATION_ANSWERED,
            LineageEventType.CANDIDATE_REJECTED,
            LineageEventType.FEEDBACK_RECORDED,
            LineageEventType.MEMORY_APPROVED,
            LineageEventType.MEMORY_REJECTED,
            LineageEventType.PROMOTION_APPROVED,
            LineageEventType.PROMOTION_DENIED,
        }
    )
    human_facts = tuple(
        _fact(
            f"human:{event.event_id}",
            "human_intervention",
            (
                f"Scope choice {event.payload['choice']} was recorded ({event.truth_kind.value})."
                if event.event_type == LineageEventType.CLARIFICATION_ANSWERED
                else f"Human correction was bound to scope {event.payload['scope_id']} ({event.truth_kind.value})."
                if event.event_type == LineageEventType.FEEDBACK_RECORDED
                else f"{event.event_type.value.replace('.', ' ').title()} ({event.truth_kind.value})."
            ),
            truth_kind=event.truth_kind.value,
            node_ids=event_nodes((event,)),
            edges=edges,
            metadata={
                key: event.payload[key]
                for key in (
                    "candidate_patch_sha256",
                    "choice",
                    "decision_id",
                    "memory_id",
                    "operator_label",
                    "revision",
                    "scope_id",
                    "status",
                )
                if key in event.payload
            },
        )
        for event in human_events[-8:]
    ) or (
        _fact(
            "human:none",
            "human_intervention",
            "Human intervention was not established by captured evidence.",
            status="not_established",
        ),
    )

    compiled = tuple(
        event for event in all_events if event.event_type == LineageEventType.CONTEXT_COMPILED
    )
    injected = tuple(
        event for event in all_events if event.event_type == LineageEventType.CONTEXT_INJECTED
    )
    opened = tuple(
        event
        for event in all_events
        if event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == LineageOperation.OPEN_EVIDENCE.value
    )
    memory_scopes = _memory_scopes(compiled)
    included_text = "Approved context was compiled and injected into a fresh isolated consumer runtime."
    if memory_scopes:
        scopes_text = "; ".join(
            f"{scope.scope_id.value} applies to {', '.join(scope.path_globs)}"
            for scope in memory_scopes
        )
        scope_label = "scope" if len(memory_scopes) == 1 else "scopes"
        detailed_text = f"{included_text} Included memory {scope_label}: {scopes_text}."
        included_text = (
            detailed_text
            if len(detailed_text) <= 512
            else f"{included_text} Included {len(memory_scopes)} validated memory scopes; inspect memory_scopes metadata."
        )
    context_facts = (
        _fact(
            "context:included",
            "inherited_context",
            (
                included_text
                if compiled and injected
                else "Approved context inclusion and injection were not both established."
            ),
            status="established" if compiled and injected else "not_established",
            node_ids=event_nodes((*compiled, *injected)),
            edges=edges,
            metadata={
                "compiled_count": len(compiled),
                "injected_count": len(injected),
                "memory_scopes": tuple(
                    scope.model_dump(mode="json") for scope in memory_scopes
                ),
                "reference_kinds": tuple(
                    sorted(
                        {
                            reference.kind.value
                            for event in (*compiled, *injected)
                            for reference in event.references
                        }
                    )
                ),
            },
        ),
        _fact(
            "context:opened",
            "inherited_context",
            (
                "Injected context was explicitly opened by the isolated consumer runtime."
                if opened
                else "A later explicit opening of injected context was not established."
            ),
            status="established" if opened else "not_established",
            truth_kind=(
                opened[-1].truth_kind.value if opened else "server_derived"
            ),
            node_ids=event_nodes(opened),
            edges=edges,
            metadata={
                "opened_count": len(opened),
                "evidence_ids": tuple(
                    sorted(
                        {
                            reference.id
                            for event in opened
                            for reference in event.references
                        }
                    )
                ),
                "reference_kinds": tuple(
                    sorted(
                        {
                            reference.kind.value
                            for event in opened
                            for reference in event.references
                        }
                    )
                ),
            },
        ),
        _fact(
            "context:excluded",
            "inherited_context",
            (
                f"Excluded handoffs: {len(denied)}."
                if denied
                else "Excluded handoff evidence was not established."
            ),
            status="historical" if denied else "not_established",
            truth_kind="policy_authoritative",
            node_ids=event_nodes(denied),
            edges=edges,
        ),
    )

    local_results = tuple(
        event
        for event in all_events
        if event.event_type == LineageEventType.LOCAL_RESULT_RECORDED
    )
    promotions = tuple(
        event for event in all_events if event.event_type == LineageEventType.PROMOTION_COMPLETED
    )
    rejected = tuple(
        event
        for event in all_events
        if event.event_type
        in {LineageEventType.CANDIDATE_REJECTED, LineageEventType.PROMOTION_DENIED}
    )
    failures = tuple(
        event for event in all_events if event.event_type == LineageEventType.RUN_FAILED
    )
    if local_results:
        result = local_results[-1]
        outcome_kind = (
            "isolated_local_commit"
            if result.payload.get("outcome") == "local_isolated_commit"
            else "rejected"
        )
        outcome_text = (
            "An isolated local commit was explicitly recorded."
            if outcome_kind == "isolated_local_commit"
            else "The local candidate was explicitly rejected."
        )
        outcome_events = (result,)
    elif promotions:
        outcome_kind = "graphene_receipt_only"
        outcome_text = "Graphene promotion receipt recorded; an isolated local Git commit is not established."
        outcome_events = (promotions[-1],)
    elif rejected:
        outcome_kind = "rejected"
        outcome_text = "Candidate rejection was explicitly recorded; no local commit is established."
        outcome_events = (rejected[-1],)
    elif failures:
        outcome_kind = "failed"
        outcome_text = "The run failed; no successful local result is established."
        outcome_events = (failures[-1],)
    else:
        outcome_kind = "not_established"
        outcome_text = "Final outcome was not established by captured evidence."
        outcome_events = ()
    outcome_fact = _fact(
        "outcome:current",
        "outcome",
        outcome_text,
        status="established" if outcome_events else "not_established",
        truth_kind=outcome_events[-1].truth_kind.value if outcome_events else "server_derived",
        node_ids=event_nodes(outcome_events),
        edges=edges,
        metadata={"outcome_kind": outcome_kind},
    )
    unknown_facts = tuple(
        _fact(
            f"unknown:{index}",
            "unknown",
            text,
            status="not_established",
            metadata={"capture_boundary": True},
        )
        for index, text in enumerate(unknowns, 1)
    )
    facts = {
        "attention": (attention,),
        "candidate": candidate_facts,
        "verified_evidence": verified_facts,
        "human_intervention": human_facts,
        "inherited_context": context_facts,
        "outcome": (outcome_fact,),
        "unknown": unknown_facts,
    }
    stages = [node.stage for node in nodes if node.stage]
    current_stage = max(stages, key=_STAGE_ORDER.get) if stages else "source_work"
    collapsed = sum(
        max(0, int(node.metadata.get("reference_count", 1)) - 1)
        for node in nodes
        if node.kind == "evidence"
    )
    omitted_nodes = omitted.get("nodes", 0) + sum(
        count for key, count in omitted.items() if key.endswith(":events")
    )
    return ReviewBrief(
        attention=attention,
        sections=tuple(
            ReviewSection(key=key, title=_SECTION_TITLES[key], facts=facts[key])
            for key in _SECTION_TITLES
        ),
        changed_paths=changed_paths,
        bound_paths=bound_paths,
        stage=current_stage,
        outcome_kind=outcome_kind,
        counts=ViewCounts(
            total_nodes=len(nodes) + omitted_nodes + collapsed,
            visible_nodes=len(nodes),
            filtered_nodes=0,
            collapsed_nodes=collapsed,
            omitted_nodes=omitted_nodes,
            total_edges=len(edges) + omitted.get("edges", 0),
            visible_edges=len(edges),
        ),
    )


def verified_support_path(
    nodes: Iterable[ViewNode], edges: Iterable[ViewEdge], root_node_id: str
) -> VerifiedSupportPath:
    node_ids = {node.id for node in nodes}
    if root_node_id not in node_ids:
        raise ViewerEvidenceInvalid("support path root is not visible")
    outgoing: dict[str, list[ViewEdge]] = {}
    for edge in edges:
        if edge.support_path is True and edge.kind in SUPPORT_EDGE_KINDS:
            outgoing.setdefault(edge.source, []).append(edge)
    visited = {root_node_id}
    selected_edges: list[ViewEdge] = []
    queue = [root_node_id]
    while queue:
        source = queue.pop(0)
        for edge in sorted(outgoing.get(source, ()), key=lambda item: item.id):
            if edge.target not in node_ids:
                continue
            selected_edges.append(edge)
            if edge.target not in visited:
                visited.add(edge.target)
                queue.append(edge.target)
    return VerifiedSupportPath(
        root_node_id=root_node_id,
        label="Verified support relationships",
        node_ids=tuple(sorted(visited)),
        edge_ids=tuple(sorted({edge.id for edge in selected_edges})),
    )


def _snapshot_unknowns(family: dict[str, tuple[Event, ...]]) -> tuple[str, ...]:
    if any(
        event.event_type == LineageEventType.LOCAL_RESULT_RECORDED
        for events in family.values()
        for event in events
    ):
        return UNKNOWN_LIMITS[:-1]
    return UNKNOWN_LIMITS


def _encode_cursor(root_run_id: str, heads: Iterable[ViewHead]) -> str:
    raw = canonical_json_bytes(
        {
            "root_run_id": root_run_id,
            "view_version": 1,
            "heads": [
                {"run_id": head.run_id, "seq": head.seq, "event_sha256": head.event_sha256}
                for head in heads
            ],
        }
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(cursor: str, root_run_id: str) -> dict[str, tuple[int, str]]:
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= 8_192:
        raise ViewerEvidenceInvalid("stream cursor is invalid")
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(raw)
        heads = value["heads"]
        if (
            canonical_json_bytes(value) != raw
            or set(value) != {"heads", "root_run_id", "view_version"}
            or value["root_run_id"] != root_run_id
            or value["view_version"] != 1
            or not isinstance(heads, list)
            or len(heads) > MAX_FAMILY_RUNS
        ):
            raise ValueError
        result: dict[str, tuple[int, str]] = {}
        for head in heads:
            if set(head) != {"event_sha256", "run_id", "seq"}:
                raise ValueError
            run_id, seq, digest = head["run_id"], head["seq"], head["event_sha256"]
            if (
                not isinstance(run_id, str)
                or not isinstance(seq, int)
                or isinstance(seq, bool)
                or seq < 1
                or not isinstance(digest, str)
                or len(digest) != 64
                or run_id in result
            ):
                raise ValueError
            result[run_id] = (seq, digest)
        return result
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise ViewerEvidenceInvalid("stream cursor is invalid") from error


def _build_snapshot(path: str | Path, root_run_id: str) -> GraphSnapshot:
    database_path = Path(path)
    identity = database_identity(database_path)
    family, omitted_runs = _family(database_path, root_run_id)
    if database_identity(database_path) != identity:
        raise ViewerEvidenceInvalid("lineage database was replaced during projection")
    nodes, edges, heads, omitted = _build_graph(family)
    if omitted_runs:
        omitted["family_runs"] = omitted_runs
    unknowns = _snapshot_unknowns(family)
    review_brief = _build_review_brief(family, nodes, edges, omitted, unknowns)
    support_roots = tuple(
        node.id
        for node in nodes
        if node.kind == "result"
        or node.label == "Promotion Completed"
        or node.label == "Handoff Denied"
    )
    support_paths = tuple(
        verified_support_path(nodes, edges, root_id) for root_id in support_roots
    )
    public = {
        "view_version": 1,
        "root_run_id": root_run_id,
        "heads": [item.model_dump(mode="json") for item in heads],
        "nodes": [item.model_dump(mode="json") for item in nodes],
        "edges": [item.model_dump(mode="json") for item in edges],
        "omitted_counts": dict(sorted(omitted.items())),
        "unknowns": unknowns,
        "review_brief": review_brief.model_dump(mode="json"),
        "support_paths": [item.model_dump(mode="json") for item in support_paths],
    }
    return GraphSnapshot(
        **public,
        cursor=_encode_cursor(root_run_id, heads),
        graph_sha256=canonical_json_sha256(public),
    )


def _snapshot_at_cursor(path: str | Path, root_run_id: str, cursor: str) -> GraphSnapshot:
    expected = decode_cursor(cursor, root_run_id)
    current_family, omitted_runs = _family(Path(path), root_run_id)
    if not expected or not set(expected) <= set(current_family):
        raise ViewerEvidenceInvalid("stream cursor does not belong to the verified family")
    prefix: dict[str, tuple[Event, ...]] = {}
    for run_id, (seq, digest) in expected.items():
        events = current_family[run_id]
        if seq > len(events) or events[seq - 1].event_sha256 != digest:
            raise ViewerEvidenceInvalid("verified lineage prefix changed")
        prefix[run_id] = events[:seq]
    nodes, edges, heads, omitted = _build_graph(prefix)
    if omitted_runs:
        omitted["family_runs"] = omitted_runs
    unknowns = _snapshot_unknowns(prefix)
    review_brief = _build_review_brief(prefix, nodes, edges, omitted, unknowns)
    support_roots = tuple(
        node.id
        for node in nodes
        if node.kind == "result"
        or node.label == "Promotion Completed"
        or node.label == "Handoff Denied"
    )
    support_paths = tuple(
        verified_support_path(nodes, edges, root_id) for root_id in support_roots
    )
    public = {
        "view_version": 1,
        "root_run_id": root_run_id,
        "heads": [item.model_dump(mode="json") for item in heads],
        "nodes": [item.model_dump(mode="json") for item in nodes],
        "edges": [item.model_dump(mode="json") for item in edges],
        "omitted_counts": dict(sorted(omitted.items())),
        "unknowns": unknowns,
        "review_brief": review_brief.model_dump(mode="json"),
        "support_paths": [item.model_dump(mode="json") for item in support_paths],
    }
    return GraphSnapshot(
        **public,
        cursor=cursor,
        graph_sha256=canonical_json_sha256(public),
    )


_PROJECTION_FAILURES = (
    LineageStoreError,
    PromotionCheckpointError,
    ProjectionError,
    ValidationError,
    sqlite3.Error,
)


def build_snapshot(path: str | Path, root_run_id: str) -> GraphSnapshot:
    try:
        return _build_snapshot(path, root_run_id)
    except (ViewerEvidenceInvalid, ViewerRunNotFound):
        raise
    except _PROJECTION_FAILURES as error:
        raise ViewerEvidenceInvalid(
            "viewer could not verify authoritative lineage"
        ) from error


def snapshot_at_cursor(path: str | Path, root_run_id: str, cursor: str) -> GraphSnapshot:
    try:
        return _snapshot_at_cursor(path, root_run_id, cursor)
    except (ViewerEvidenceInvalid, ViewerRunNotFound):
        raise
    except _PROJECTION_FAILURES as error:
        raise ViewerEvidenceInvalid(
            "viewer could not verify authoritative lineage"
        ) from error


def current_node_id(snapshot: GraphSnapshot) -> str:
    if not snapshot.nodes:
        raise ViewerEvidenceInvalid("verified graph has no visible current node")
    return max(
        snapshot.nodes,
        key=lambda node: (
            node.recorded_at.timestamp() if node.recorded_at else float("-inf"),
            not node.id.startswith("run:"),
            node.id,
        ),
    ).id


def diff_snapshots(before: GraphSnapshot, after: GraphSnapshot) -> tuple[GraphDelta, ...]:
    if before.root_run_id != after.root_run_id or before.view_version != after.view_version:
        return (GraphDelta(op="reset", snapshot=after),)
    old_nodes = {item.id: item for item in before.nodes}
    new_nodes = {item.id: item for item in after.nodes}
    old_edges = {item.id: item for item in before.edges}
    new_edges = {item.id: item for item in after.edges}
    deltas: list[GraphDelta] = []
    for edge_id in sorted(set(old_edges) - set(new_edges)):
        edge = old_edges[edge_id]
        deltas.append(
            GraphDelta(
                op="remove",
                id=edge_id,
                run_id=edge.run_id,
                seq=edge.seq,
                event_id=edge.event_id,
                remove_kind="edge",
            )
        )
    for node_id in sorted(set(old_nodes) - set(new_nodes)):
        node = old_nodes[node_id]
        deltas.append(
            GraphDelta(
                op="remove",
                id=node_id,
                run_id=node.run_id,
                seq=node.seq,
                event_id=node.event_id,
                remove_kind="node",
            )
        )
    for node_id, node in sorted(new_nodes.items()):
        previous = old_nodes.get(node_id)
        if previous == node:
            continue
        if previous is not None and previous.model_copy(update={"status": node.status}) == node:
            deltas.append(
                GraphDelta(
                    op="set_status",
                    id=node_id,
                    run_id=node.run_id,
                    seq=node.seq,
                    event_id=node.event_id,
                    status=node.status,
                )
            )
        else:
            deltas.append(
                GraphDelta(
                    op="upsert_node",
                    id=node_id,
                    run_id=node.run_id,
                    seq=node.seq,
                    event_id=node.event_id,
                    node=node,
                )
            )
    for edge_id, edge in sorted(new_edges.items()):
        if old_edges.get(edge_id) != edge:
            deltas.append(
                GraphDelta(
                    op="upsert_edge",
                    id=edge_id,
                    run_id=edge.run_id,
                    seq=edge.seq,
                    event_id=edge.event_id,
                    edge=edge,
                )
            )
    return tuple(deltas)


def apply_deltas(
    before: GraphSnapshot,
    deltas: Iterable[GraphDelta],
    *,
    cursor: str,
    heads: Iterable[ViewHead],
    graph_sha256: str,
    omitted_counts: dict[str, int],
    unknowns: Iterable[str],
    review_brief: ReviewBrief,
    support_paths: Iterable[VerifiedSupportPath],
) -> GraphSnapshot:
    heads = tuple(ViewHead.model_validate(item) for item in heads)
    review_brief = ReviewBrief.model_validate(review_brief)
    support_paths = tuple(
        VerifiedSupportPath.model_validate(item) for item in support_paths
    )
    nodes = {node.id: node for node in before.nodes}
    edges = {edge.id: edge for edge in before.edges}
    for raw in deltas:
        delta = GraphDelta.model_validate(raw)
        if delta.op == "reset":
            assert delta.snapshot is not None
            snapshot = delta.snapshot
            public = snapshot.model_dump(mode="json", exclude={"cursor", "graph_sha256"})
            if (
                snapshot.cursor != cursor
                or snapshot.graph_sha256 != graph_sha256
                or canonical_json_sha256(public) != graph_sha256
            ):
                raise ViewerEvidenceInvalid("reset delta does not match its graph hash")
            return snapshot
        if delta.op == "remove":
            (nodes if delta.remove_kind == "node" else edges).pop(delta.id, None)
        elif delta.op == "upsert_node":
            assert delta.node is not None
            nodes[delta.node.id] = delta.node
        elif delta.op == "upsert_edge":
            assert delta.edge is not None
            edges[delta.edge.id] = delta.edge
        elif delta.op == "set_status":
            if delta.id not in nodes:
                raise ViewerEvidenceInvalid("status delta targets an unknown node")
            nodes[delta.id] = nodes[delta.id].model_copy(update={"status": delta.status})
    if any(edge.source not in nodes or edge.target not in nodes for edge in edges.values()):
        raise ViewerEvidenceInvalid("delta result contains an edge with a missing endpoint")
    public = {
        "view_version": before.view_version,
        "root_run_id": before.root_run_id,
        "heads": [item.model_dump(mode="json") for item in heads],
        "nodes": [item.model_dump(mode="json") for item in sorted(nodes.values(), key=lambda item: (item.run_id or "", item.seq or 0, item.kind, item.id))],
        "edges": [item.model_dump(mode="json") for item in sorted(edges.values(), key=lambda item: item.id)],
        "omitted_counts": dict(sorted(omitted_counts.items())),
        "unknowns": tuple(unknowns),
        "review_brief": review_brief.model_dump(mode="json"),
        "support_paths": [item.model_dump(mode="json") for item in support_paths],
    }
    if canonical_json_sha256(public) != graph_sha256:
        raise ViewerEvidenceInvalid("delta result does not match its graph hash")
    return GraphSnapshot(**public, cursor=cursor, graph_sha256=graph_sha256)
