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
from ..lineage.reducer import ProjectionError, reduce_events
from ..lineage.store import (
    CheckpointReader,
    EvidenceInvalid,
    LineageStoreError,
    SQLiteLineageStore,
)
from ..models import Event, EvidenceInvalidState, LineageEventType, LineageOperation
from .contract import GraphDelta, GraphSnapshot, ViewEdge, ViewHead, ViewNode, ViewReference

MAX_FAMILY_RUNS = 16
MAX_DATABASE_RUNS = 256
MAX_NODES = 320
MAX_EDGES = 640
UNKNOWN_LIMITS = (
    "Timing does not prove causality.",
    "The view includes only explicit committed Graphene evidence.",
    "Bubble activity is bounded interaction count, not importance or correctness.",
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
    edges: dict[str, ViewEdge], source: str, target: str, kind: str, event: Event
) -> None:
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
    )


_ENTITY_KIND = {
    LineageEventType.CANDIDATE_CREATED: "changeset",
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

_SAFE_METADATA = (
    "operation",
    "path",
    "reason_code",
    "passed",
    "changed_path_count",
    "hunk_count",
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

    for run_id, events in family.items():
        projection = reduce_events(events)
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
            source_ref=_reference(events[-1].source_ref),
            metadata={
                "agent_profile_id": events[0].agent_profile_id,
                "base_sha": events[0].base_sha,
                "projection_sha256": projection.projection_sha256,
            },
        )
        source_run = events[0].payload.get("source_run_id")
        if isinstance(source_run, str) and source_run in family:
            _add_edge(edges, _node_id("run", source_run), run_node, "continued_as", events[0])

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
                    source_ref=source_ref,
                    metadata={"adapter_kind": event.payload.get("adapter_kind", "unknown")},
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
                    source_ref=source_ref,
                    metadata={key: event.payload[key] for key in _SAFE_METADATA if key in event.payload},
                )
                _add_edge(edges, parent, tool_id, "performed", event)

            kind = _ENTITY_KIND.get(event.event_type)
            if kind:
                entity_id = _node_id("event", run_id, event.event_id)
                event_nodes[event.event_id] = entity_id
                nodes[entity_id] = ViewNode(
                    id=entity_id,
                    kind=kind,
                    status=statuses[event.event_id],
                    truth_kind=event.truth_kind.value,
                    activity_count=min(32, 1 + len(event.references)),
                    label=_LABELS[event.event_type],
                    run_id=run_id,
                    seq=event.seq,
                    event_id=event.event_id,
                    source_ref=source_ref,
                    metadata={key: event.payload[key] for key in _SAFE_METADATA if key in event.payload},
                )
                _add_edge(edges, parent, entity_id, "recorded", event)
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
                        ),
                    )
                    _add_edge(edges, entity_id, reference_id, "evidenced_by", event)

        for file in projection.files:
            file_id = _node_id(
                "file",
                run_id,
                canonical_json_sha256({"path": file.path, "repo": events[0].repo_id}),
            )
            evidence_event = events[file.last_seq - 1]
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
                source_ref=_reference(evidence_event.source_ref),
                metadata={
                    "path": file.path,
                    "read_count": file.read_count,
                    "added_lines": file.added_lines,
                    "deleted_lines": file.deleted_lines,
                    "bound_test_pass": file.bound_test_pass,
                    "file_version_id": file.file_version_id,
                },
            )
            _add_edge(edges, run_node, file_id, "observed", evidence_event)

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
                    _add_edge(edges, source, target, "evidenced_by", event)

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
    public = {
        "view_version": 1,
        "root_run_id": root_run_id,
        "heads": [item.model_dump(mode="json") for item in heads],
        "nodes": [item.model_dump(mode="json") for item in nodes],
        "edges": [item.model_dump(mode="json") for item in edges],
        "omitted_counts": dict(sorted(omitted.items())),
        "unknowns": UNKNOWN_LIMITS,
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
    public = {
        "view_version": 1,
        "root_run_id": root_run_id,
        "heads": [item.model_dump(mode="json") for item in heads],
        "nodes": [item.model_dump(mode="json") for item in nodes],
        "edges": [item.model_dump(mode="json") for item in edges],
        "omitted_counts": dict(sorted(omitted.items())),
        "unknowns": UNKNOWN_LIMITS,
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
            node.seq or 0,
            not node.id.startswith("run:"),
            node.id,
        ),
    ).id


def diff_snapshots(before: GraphSnapshot, after: GraphSnapshot) -> tuple[GraphDelta, ...]:
    old_nodes = {item.id: item for item in before.nodes}
    new_nodes = {item.id: item for item in after.nodes}
    old_edges = {item.id: item for item in before.edges}
    new_edges = {item.id: item for item in after.edges}
    if set(old_nodes) - set(new_nodes) or set(old_edges) - set(new_edges):
        return (GraphDelta(op="reset", snapshot=after),)
    deltas: list[GraphDelta] = []
    for node_id, node in new_nodes.items():
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
    for edge_id, edge in new_edges.items():
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
