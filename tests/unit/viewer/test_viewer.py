from __future__ import annotations

import http.client
import json
import os
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from graphene.lineage.artifacts import SQLiteArtifactStore
from graphene.lineage.promotion import SQLiteCheckpointRecorder
from graphene.lineage.sqlite_lineage_store import SQLiteLineageStore
from graphene.hashing import canonical_json_sha256
from graphene.core_models import (
    Event,
    EventInput,
    EvidenceKind,
    LineageAuthority,
    LineageEventType,
    SourceReference,
    SourceKind,
    TruthKind,
    VerifiedHead,
)
from graphene.viewer import (
    ViewerEvidenceInvalid,
    apply_deltas,
    build_snapshot,
    create_viewer_app,
    current_node_id,
    diff_snapshots,
)
from graphene.viewer.contract import GraphDelta, GraphSnapshot
from graphene.viewer.viewer_projection import (
    UNKNOWN_LIMITS,
    _add_edge,
    _build_graph,
    _build_review_brief,
    snapshot_at_cursor,
)
from graphene.viewer.viewer_replay import apply_replay_envelope
from scripts.generate_viewer_replay import DEFAULT_SOURCE, materialize

BASE_SHA = "a" * 40
TOKEN = "ephemeral-view-token"


def test_checked_in_replay_is_a_canonical_sanitized_view_contract():
    path = Path("backend/graphene/viewer/static/replay.json")
    replay = json.loads(path.read_text())
    snapshots = [GraphSnapshot.model_validate(replay["snapshot"])]
    for envelope in replay["deltas"]:
        snapshots.append(apply_replay_envelope(snapshots[-1], envelope))

    for snapshot in snapshots:
        public = snapshot.model_dump(mode="json", exclude={"cursor", "graph_sha256"})
        assert canonical_json_sha256(public) == snapshot.graph_sha256
    assert all(item["type"] == "delta" and "snapshot" not in item for item in replay["deltas"])
    assert replay["meta"]["final_graph_sha256"] == snapshots[-1].graph_sha256
    assert replay["meta"]["source_heads"] == snapshots[-1].model_dump(mode="json")["heads"]
    assert replay["meta"]["decision_proof"] == "SIMULATED FIXTURE — NOT HUMAN ATTESTATION"
    assert [tuple(head.seq for head in snapshot.heads) for snapshot in snapshots] == [
        (4,),
        (8,),
        (8, 8),
        (9, 8),
        (11, 8),
    ]
    assert snapshots[-2].review_brief.attention.metadata["pending_count"] == 1
    assert snapshots[-2].review_brief.attention.status == "pending"
    assert snapshots[-1].review_brief.attention.metadata["pending_count"] == 0
    public_bytes = path.read_bytes().lower()
    assert not any(
        forbidden in public_bytes
        for forbidden in (b"unified_diff", b"test stdout", b"/private/", b"prompt", b"sk-")
    )


def _stores(path: Path):
    artifacts = SQLiteArtifactStore(path)
    source = artifacts(EvidenceKind.OPERATOR_REQUEST, {"action": "viewer-test"})
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    return store, SourceReference(kind="lifecycle_request", id=source.id, sha256=source.sha256)


def _append(
    store: SQLiteLineageStore,
    source: SourceReference,
    run_id: str,
    event_type: LineageEventType,
    payload: dict[str, object],
):
    head = store.verify(run_id)
    assert isinstance(head, VerifiedHead)
    return store.append(
        run_id,
        head,
        f"viewer_event_{run_id}_{head.seq + 1:04d}",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=event_type,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=source,
            payload=payload,
        ),
    )


@pytest.fixture
def family(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    store, source = _stores(path)
    _append(store, source, "run_source", LineageEventType.RUN_STARTED, {"state": "STARTING"})
    _append(store, source, "run_source", LineageEventType.MEMORY_PROPOSED, {})
    _append(
        store,
        source,
        "run_consumer",
        LineageEventType.RUN_STARTED,
        {"state": "STARTING", "source_run_id": "run_source", "context_compiled_event_sha256": "b" * 64},
    )
    return path, store, source


@pytest.fixture
def replay_family(tmp_path: Path):
    path = tmp_path / "replay.sqlite3"
    fixture, events = materialize(DEFAULT_SOURCE, path)
    root_run_id = fixture["runs"][fixture["root_run"]]["run_id"]
    return path, fixture, events, root_run_id


def test_review_brief_answers_checked_replay_without_inference(replay_family):
    path, _fixture, _events, root_run_id = replay_family
    snapshot = build_snapshot(path, root_run_id)
    brief = snapshot.review_brief
    assert brief is not None
    assert snapshot_at_cursor(path, root_run_id, snapshot.cursor) == snapshot
    assert tuple(section.key for section in brief.sections) == (
        "attention",
        "candidate",
        "verified_evidence",
        "human_intervention",
        "inherited_context",
        "outcome",
        "unknown",
    )
    assert brief.attention.text == "No unresolved Graphene decision."
    assert brief.changed_paths == (
        "app/auth/limiter.py",
        "tests/test_security_policy.py",
    )
    assert brief.bound_paths == brief.changed_paths
    assert brief.outcome_kind == "graphene_receipt_only"
    assert brief.stage == "local_result"

    facts = {
        fact.id: fact
        for section in brief.sections
        for fact in section.facts
    }
    assert facts["candidate:hunks"].text == "Captured hunk count: 1."
    assert facts["candidate:bound_test"].status == "established"
    denial = next(
        fact for fact in facts.values() if fact.id.startswith("evidence:handoff_denial:")
    )
    assert denial.text.startswith("Billing Observer handoff was denied with zero")
    assert denial.metadata == {
        "evidence_count": 0,
        "memory_count": 0,
        "model_dispatch_count": 0,
        "source_path_count": 0,
        "tool_count": 0,
        "reason_code": "scope_intersection_empty",
        "target_profile_id": "billing-observer@1",
    }
    assert facts["context:included"].metadata == {
        "compiled_count": 1,
        "injected_count": 1,
        "memory_scopes": [
            {
                "memory_id": "fixture_auth_memory",
                "revision": 1,
                "scope_id": "all_auth",
                "path_globs": ["app/auth/**"],
            }
        ],
        "reference_kinds": [
            "context_brief",
            "handoff_decision",
            "injection_receipt",
        ],
    }
    assert "all_auth applies to app/auth/**" in facts["context:included"].text
    assert facts["context:opened"].status == "established"
    assert facts["context:opened"].truth_kind == "runtime_observed"
    assert facts["context:opened"].metadata["opened_count"] == 1
    assert facts["context:opened"].metadata["reference_kinds"] == ["context_brief"]
    opened_nodes = {node.id: node for node in snapshot.nodes if node.id in facts["context:opened"].node_ids}
    opened_tool = next(node for node in opened_nodes.values() if node.metadata.get("operation") == "open_evidence")
    opened_edges = [edge for edge in snapshot.edges if edge.id in facts["context:opened"].edge_ids]
    assert any(
        edge.source == opened_tool.id
        and edge.kind == "opens_reference"
        and edge.relationship_class == "context_transfer"
        and snapshot_node.source_ref is not None
        and snapshot_node.source_ref.kind == "context_brief"
        for edge in opened_edges
        for snapshot_node in snapshot.nodes
        if snapshot_node.id == edge.target
    )
    assert {
        fact.truth_kind
        for fact in facts.values()
        if fact.section == "human_intervention"
    } == {"simulated_fixture"}
    assert any("No pull request, push, deployment" in value for value in snapshot.unknowns)
    assert brief.counts.total_nodes == (
        brief.counts.visible_nodes
        + brief.counts.collapsed_nodes
        + brief.counts.omitted_nodes
    )
    contextual = [
        node
        for node in snapshot.nodes
        if node.kind == "evidence" and node.metadata.get("reference_count", 0) >= 1
    ]
    assert contextual
    assert all(" · " in node.label for node in contextual)
    assert all(node.metadata["stages"] and node.metadata["run_roles"] for node in contextual)
    denial_node = next(
        node
        for node in snapshot.nodes
        if node.id in denial.node_ids and node.metadata.get("reason_code") == "scope_intersection_empty"
    )
    assert {
        key: denial_node.metadata[key]
        for key in (
            "evidence_count",
            "memory_count",
            "model_dispatch_count",
            "source_path_count",
            "tool_count",
        )
    } == {key: 0 for key in (
        "evidence_count",
        "memory_count",
        "model_dispatch_count",
        "source_path_count",
        "tool_count",
    )}


def test_inherited_context_distinguishes_narrow_memory_scope(tmp_path: Path):
    fixture = json.loads(DEFAULT_SOURCE.read_text())
    compiled = fixture["runs"]["source"]["events"][7]
    compiled["payload"]["memory_scopes"] = [
        {
            "memory_id": "fixture_auth_memory",
            "revision": 1,
            "scope_id": "rate_limiter_only",
            "path_globs": ["app/auth/limiter.py"],
        }
    ]
    source = tmp_path / "narrow_replay.json"
    source.write_text(json.dumps(fixture))
    database = tmp_path / "narrow_replay.sqlite3"
    narrow, _events = materialize(source, database)
    snapshot = build_snapshot(database, narrow["runs"]["source"]["run_id"])
    fact = next(
        fact
        for section in snapshot.review_brief.sections
        for fact in section.facts
        if fact.id == "context:included"
    )

    assert fact.metadata["memory_scopes"] == compiled["payload"]["memory_scopes"]
    assert "rate_limiter_only applies to app/auth/limiter.py" in fact.text
    assert "all_auth" not in fact.text


def test_promotion_receipt_has_explicit_typed_support_chain(replay_family):
    path, _fixture, _events, root_run_id = replay_family
    snapshot = build_snapshot(path, root_run_id)
    assert snapshot.review_brief.outcome_kind == "graphene_receipt_only"
    result_node = next(node for node in snapshot.nodes if node.label == "Promotion Completed")
    assert result_node.stage == "local_result"
    support = next(
        item for item in snapshot.support_paths if item.root_node_id == result_node.id
    )
    nodes = {node.id: node for node in snapshot.nodes}
    support_edges = [edge for edge in snapshot.edges if edge.id in support.edge_ids]
    assert all(edge.support_path is True for edge in support_edges)
    assert {edge.relationship_class for edge in support_edges} <= {
        "verified_support",
        "authorization",
    }
    assert {edge.kind for edge in support_edges} <= {
        "supported_by",
        "authorized_by",
        "changes_path",
        "binds_path",
        "result_supported_by",
    }
    direct_targets = {
        edge.target for edge in support_edges if edge.source == result_node.id
    }
    assert any(nodes[node_id].label == "Promotion Approved" for node_id in direct_targets)
    assert {
        nodes[node_id].source_ref.kind
        for node_id in direct_targets
        if nodes[node_id].kind == "evidence" and nodes[node_id].source_ref is not None
    } == {"promotion_receipt"}
    assert {nodes[node_id].label for node_id in support.node_ids} >= {
        "app/auth/limiter.py",
        "tests/test_security_policy.py",
        "Candidate Created",
        "Promotion Approved",
        "Promotion Completed",
    }
    assert all(nodes[node_id].label != "Handoff Denied" for node_id in support.node_ids)


def test_snapshot_is_deterministic_bounded_and_connects_run_family(family):
    path, _store, _source = family

    first = build_snapshot(path, "run_source")
    second = build_snapshot(path, "run_source")

    assert first == second
    assert tuple(head.run_id for head in first.heads) == ("run_consumer", "run_source")
    assert len(first.nodes) <= 320 and len(first.edges) <= 640
    assert any(edge.kind == "continued_as" for edge in first.edges)
    assert all("content" not in node.metadata and "prompt" not in node.metadata for node in first.nodes)
    assert first.graph_sha256 == second.graph_sha256
    assert current_node_id(first) == current_node_id(second)
    assert current_node_id(first) in {node.id for node in first.nodes}


def test_attention_decisions_are_scoped_to_their_run(family):
    path, store, source = family
    consumer_proposal = _append(
        store,
        source,
        "run_consumer",
        LineageEventType.MEMORY_PROPOSED,
        {},
    )
    head = store.verify("run_source")
    assert isinstance(head, VerifiedHead)
    store.append(
        "run_source",
        head,
        "viewer_event_run_source_memory_approved",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.MEMORY_APPROVED,
            truth_kind=TruthKind.HUMAN_ATTESTED,
            authority=LineageAuthority.OPERATOR_REQUEST,
            references=(),
            source_ref=SourceReference(
                kind=SourceKind.OPERATOR_REQUEST,
                id=source.id,
                sha256=source.sha256,
            ),
            payload={},
        ),
    )

    snapshot = build_snapshot(path, "run_source")
    assert snapshot.review_brief.attention.status == "pending"
    assert snapshot.review_brief.attention.metadata["pending_count"] == 1
    assert any(
        node.event_id == consumer_proposal.event_id
        and node.run_id == "run_consumer"
        for node in snapshot.nodes
        if node.id in snapshot.review_brief.attention.node_ids
    )


def test_current_action_uses_recorded_time_across_runs(family):
    path, _store, _source = family
    snapshot = build_snapshot(path, "run_source")
    source = next(node for node in snapshot.nodes if node.id == "run:run_source")
    consumer = next(node for node in snapshot.nodes if node.id == "run:run_consumer")
    cross_run = snapshot.model_copy(
        update={
            "nodes": (
                source.model_copy(update={"seq": 99}),
                consumer.model_copy(update={"seq": 1}),
            ),
            "edges": (),
        }
    )

    assert source.recorded_at < consumer.recorded_at
    assert current_node_id(cross_run) == consumer.id


def test_shared_evidence_nodes_are_order_independent_and_final_cursor_is_exact(family):
    path, store, source = family
    shared = SQLiteArtifactStore(path)(EvidenceKind.MEMORY_REVISION, {"memory": "shared"})
    events_by_run = {
        run_id: store.tail(run_id, 0, store.verify(run_id).seq)
        for run_id in ("run_source", "run_consumer")
    }
    for run_id in events_by_run:
        events = list(events_by_run[run_id])
        last = events[-1]
        values = last.model_dump(mode="json")
        values["references"] = [shared.model_dump(mode="json")]
        values["event_sha256"] = canonical_json_sha256(
            {key: value for key, value in values.items() if key != "event_sha256"}
        )
        events[-1] = Event.model_validate(values)
        events_by_run[run_id] = tuple(events)

    forward = _build_graph(events_by_run)
    reverse = _build_graph(dict(reversed(tuple(events_by_run.items()))))
    assert forward == reverse
    evidence = next(node for node in forward[0] if node.source_ref and node.source_ref.id == shared.id)
    assert evidence.run_id is None
    assert evidence.metadata["shared_reference"] is True
    assert evidence.metadata["reference_count"] == 1

    final = build_snapshot(path, "run_source")
    assert snapshot_at_cursor(path, "run_source", final.cursor) == final


def test_cursor_resume_emits_only_idempotent_changes(family):
    path, store, source = family
    before = build_snapshot(path, "run_source")
    assert snapshot_at_cursor(path, "run_source", before.cursor) == before

    first_event = _append(store, source, "run_source", LineageEventType.MEMORY_PROPOSED, {})
    second_event = _append(store, source, "run_source", LineageEventType.MEMORY_PROPOSED, {})
    after = build_snapshot(path, "run_source")
    deltas = diff_snapshots(before, after)

    assert after.graph_sha256 != before.graph_sha256
    assert {
        delta.node.event_id
        for delta in deltas
        if delta.op == "upsert_node" and delta.node is not None
    } >= {first_event.event_id, second_event.event_id}
    assert len({(delta.op, delta.id) for delta in deltas}) == len(deltas)
    assert all(delta.run_id and delta.seq and delta.event_id for delta in deltas)
    assert diff_snapshots(after, after) == ()
    values = {
        "cursor": after.cursor,
        "heads": after.heads,
        "graph_sha256": after.graph_sha256,
        "omitted_counts": after.omitted_counts,
        "unknowns": after.unknowns,
        "review_brief": after.review_brief,
        "support_paths": after.support_paths or (),
    }
    rebuilt = apply_deltas(before, deltas, **values)
    assert rebuilt == after
    assert apply_deltas(rebuilt, deltas, **values) == after
    with pytest.raises(ViewerEvidenceInvalid, match="graph hash"):
        apply_deltas(before, deltas, **{**values, "graph_sha256": "0" * 64})


def test_delta_removals_are_ordered_and_malformed_payloads_fail_closed(family):
    path, _store, _source = family
    before = build_snapshot(path, "run_source")
    removed = next(node for node in reversed(before.nodes) if not node.id.startswith("run:"))
    adjacent = {
        edge.id
        for edge in before.edges
        if edge.source == removed.id or edge.target == removed.id
    }
    after = before.model_copy(
        update={
            "nodes": tuple(node for node in before.nodes if node.id != removed.id),
            "edges": tuple(edge for edge in before.edges if edge.id not in adjacent),
        }
    )
    deltas = diff_snapshots(before, after)
    assert [delta.remove_kind for delta in deltas] == [
        *("edge" for _edge_id in sorted(adjacent)),
        "node",
    ]
    assert diff_snapshots(
        before,
        after.model_copy(update={"root_run_id": "another_run"}),
    )[0].op == "reset"
    with pytest.raises(ValueError, match="operation"):
        GraphDelta(op="remove", id=removed.id, remove_kind="node", status="STALE")


def test_repeated_verified_relationships_have_stable_weighted_edges(family):
    _path, store, _source = family
    events = store.tail("run_source", 0, 2)
    edges = {}

    _add_edge(edges, "source", "target", "recorded", events[0])
    _add_edge(edges, "source", "target", "recorded", events[1])

    assert len(edges) == 1
    edge = next(iter(edges.values()))
    assert edge.activity_count == 2
    assert edge.event_id == events[1].event_id


def test_viewer_api_is_header_authenticated_get_head_only_and_bootstraps_safely(family):
    path, _store, _source = family
    app = create_viewer_app(path, "run_source", TOKEN, "SCRIPTED LOCAL", "scripted-local")
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with TestClient(app) as client:
        assert client.get("/api/viewer/health").status_code == 401
        health = client.get("/api/viewer/health", headers=headers)
        assert health.json()["read_only"] is True
        assert health.headers["cache-control"] == "no-store"
        assert client.head("/api/viewer/runs/run_source/snapshot", headers=headers).status_code == 200
        snapshot = client.get("/api/viewer/runs/run_source/snapshot", headers=headers)
        assert snapshot.json()["root_run_id"] == "run_source"
        before = path.read_bytes()
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(
                "/api/viewer/runs/run_source/snapshot", headers=headers
            ).status_code == 405
        assert path.read_bytes() == before
        page = client.get("/viewer/run_source")
        assert "window.__GRAPHENE_VIEWER__" in page.text
        assert TOKEN in page.text and "scripted-local" in page.text
        assert page.headers["cache-control"] == "no-store"
        policy = page.headers["content-security-policy"]
        assert "script-src 'self' 'nonce-" in policy
        assert "'unsafe-inline'" not in next(
            directive for directive in policy.split(";") if directive.strip().startswith("script-src")
        )
        assert "style-src-attr 'unsafe-inline'" in policy
        assert "nonce=" in page.text


def test_invalid_stream_cursor_returns_structured_evidence_invalid(family):
    path, _store, _source = family
    with TestClient(create_viewer_app(path, "run_source", TOKEN, "TEST")) as client:
        response = client.get(
            "/api/viewer/runs/run_source/stream?cursor=not-a-valid-cursor",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        head = client.head(
            "/api/viewer/runs/run_source/stream?cursor=not-a-valid-cursor",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 409
    assert head.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "code": "EVIDENCE_INVALID",
        "detail": "stream cursor is invalid",
    }


def test_tampered_verified_prefix_fails_closed(family):
    path, _store, _source = family
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE events SET event_bytes = ? WHERE run_id = ? AND seq = 1",
            (b'{}', "run_source"),
        )

    with pytest.raises(ViewerEvidenceInvalid):
        build_snapshot(path, "run_source")
    with TestClient(create_viewer_app(path, "run_source", TOKEN, "TEST"), raise_server_exceptions=False) as client:
        response = client.get(
            "/api/viewer/runs/run_source/snapshot",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "EVIDENCE_INVALID"


def test_reconnect_revalidates_every_previously_visible_run(family):
    path, _store, _source = family
    snapshot = build_snapshot(path, "run_source")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE events SET event_bytes = ? WHERE run_id = ? AND seq = 1",
            (b'{}', "run_consumer"),
        )

    with pytest.raises(ViewerEvidenceInvalid):
        snapshot_at_cursor(path, "run_source", snapshot.cursor)


def test_database_replacement_fails_closed(family, tmp_path: Path):
    path, _store, _source = family
    app = create_viewer_app(path, "run_source", TOKEN, "TEST")
    replacement = tmp_path / "replacement.sqlite3"
    replacement.write_bytes(path.read_bytes())
    os.replace(replacement, path)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/viewer/runs/run_source/snapshot",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "EVIDENCE_INVALID"


def test_projection_uses_bounded_public_rail_and_keeps_latest_nodes():
    source = SourceReference(kind="lifecycle_request", id="source_001", sha256="1" * 64)
    events = []
    previous = None
    for seq in range(1, 1_003):
        event_type = LineageEventType.RUN_STARTED if seq == 1 else LineageEventType.MEMORY_PROPOSED
        payload = {"state": "STARTING"} if seq == 1 else {}
        draft = EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=event_type,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=source,
            payload=payload,
        )
        values = {
            **draft.model_dump(mode="json"),
            "schema_version": 2,
            "event_id": f"event_{seq:04d}",
            "run_id": "run_over_cap",
            "seq": seq,
            "server_recorded_at": "2026-08-13T00:00:00Z",
            "idempotency_key": f"viewer_over_cap_{seq:04d}",
            "payload_sha256": canonical_json_sha256(payload),
            "previous_event_sha256": previous,
        }
        values["event_sha256"] = canonical_json_sha256(values)
        event = Event.model_validate(values)
        events.append(event)
        previous = event.event_sha256

    family = {"run_over_cap": tuple(events)}
    nodes, edges, _heads, omitted = _build_graph(family)
    brief = _build_review_brief(family, nodes, edges, omitted, UNKNOWN_LIMITS)

    assert len(nodes) == 320 and len(edges) <= 640
    assert omitted["run_over_cap:events"] == 2
    assert omitted["nodes"] == 681
    assert brief.counts.omitted_nodes == 683
    assert brief.counts.total_nodes == 1_003
    assert any(node.event_id == "event_1002" for node in nodes)
    assert all(node.event_id != "event_0002" for node in nodes)


def test_completed_promotion_requires_readable_checkpoint_table(family):
    path, store, _source = family
    checkpoints = SQLiteCheckpointRecorder(path)
    artifacts = SQLiteArtifactStore(path)
    receipt = artifacts(EvidenceKind.PROMOTION_RECEIPT, {"promotion": "test"})
    head = store.verify("run_source")
    assert isinstance(head, VerifiedHead)
    store.append(
        "run_source",
        head,
        "viewer_promotion_completed_0001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha=BASE_SHA,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.PROMOTION_COMPLETED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.PROMOTION_SERVICE,
            references=(),
            source_ref=SourceReference(
                kind="promotion_receipt", id=receipt.id, sha256=receipt.sha256
            ),
            payload={
                "candidate_patch_sha256": "2" * 64,
                "promotion_receipt_id": receipt.id,
                "promotion_receipt_sha256": receipt.sha256,
                "status": "PROMOTED",
            },
        ),
    )
    del checkpoints
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE promotion_checkpoints")

    with pytest.raises(ViewerEvidenceInvalid, match="checkpoint"):
        build_snapshot(path, "run_source")


def test_file_nodes_bind_the_exact_observation_event(family):
    path, store, _source = family
    artifacts = SQLiteArtifactStore(path)
    receipt = artifacts(EvidenceKind.TOOL_RECEIPT, {"operation": "read_file"})
    source = SourceReference(kind="tool_receipt", id=receipt.id, sha256=receipt.sha256)
    previous = store.verify("run_source")
    assert isinstance(previous, VerifiedHead)
    common = {
        "session_id": "session_001",
        "invocation_id": "invocation_001",
        "model_id": "model-test",
        "tool_call_id": "tool_call_001",
        "repo_id": "graphene-demo",
        "base_sha": BASE_SHA,
        "agent_profile_id": "auth-maintainer@1",
        "policy_revision": 1,
        "truth_kind": TruthKind.RUNTIME_OBSERVED,
        "authority": LineageAuthority.SCOPED_TOOL_WRAPPER,
        "references": (),
        "source_ref": source,
    }
    started = store.append(
        "run_source",
        previous,
        "viewer_tool_started_0001",
        EventInput(
            **common,
            event_type=LineageEventType.TOOL_STARTED,
            payload={"operation": "read_file", "status": "STARTED"},
        ),
    )
    completed = store.append(
        "run_source",
        VerifiedHead(
            run_id="run_source",
            seq=started.seq,
            event_sha256=started.event_sha256,
            event_count=started.seq,
        ),
        "viewer_tool_completed_0001",
        EventInput(
            **common,
            event_type=LineageEventType.TOOL_COMPLETED,
            payload={
                "operation": "read_file",
                "status": "COMPLETED",
                "path": "app/auth/limiter.py",
                "file_version_id": "3" * 64,
                "byte_count": 128,
                "line_count": 4,
            },
        ),
    )

    file_node = next(node for node in build_snapshot(path, "run_source").nodes if node.kind == "file")
    assert file_node.event_id == completed.event_id
    assert file_node.seq == completed.seq
    assert file_node.source_ref is not None
    assert file_node.source_ref.id == receipt.id
    assert file_node.source_ref.sha256 == receipt.sha256


def test_committed_event_streams_once_within_visibility_target(family):
    path, store, source = family
    before = build_snapshot(path, "run_source")
    app = create_viewer_app(path, "run_source", TOKEN, "TEST")
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off")
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 2
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started

    connections: list[tuple[http.client.HTTPConnection, http.client.HTTPResponse]] = []

    def connect(cursor: str):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request(
            "GET",
            f"/api/viewer/runs/run_source/stream?cursor={cursor}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        response = connection.getresponse()
        assert response.status == 200
        connections.append((connection, response))
        return connection, response

    try:
        first_connection, first_response = connect(before.cursor)
        started = time.monotonic()
        first_event = _append(
            store, source, "run_source", LineageEventType.MEMORY_PROPOSED, {}
        )
        first = json.loads(first_response.readline())
        assert time.monotonic() - started <= 0.5
        assert first["type"] == "delta" and "snapshot" not in first
        current = build_snapshot(path, "run_source")
        assert first["current_id"] == current_node_id(current)
        assert apply_deltas(
            before,
            first["deltas"],
            cursor=first["cursor"],
            heads=first["heads"],
            graph_sha256=first["graph_sha256"],
            omitted_counts=first["omitted_counts"],
            unknowns=first["unknowns"],
            review_brief=first["review_brief"],
            support_paths=first["support_paths"],
        ) == current
        assert first["cursor"] != before.cursor
        assert {
            "heads",
            "graph_sha256",
            "omitted_counts",
        } <= set(first)
        assert sum(
            delta["op"] == "upsert_node"
            and delta["node"]["id"] == f"event:run_source:{first_event.event_id}"
            for delta in first["deltas"]
        ) == 1

        first_response.close()
        first_connection.close()
        connections.remove((first_connection, first_response))

        _second_connection, second_response = connect(first["cursor"])
        started = time.monotonic()
        second_event = _append(
            store, source, "run_source", LineageEventType.MEMORY_PROPOSED, {}
        )
        second = json.loads(second_response.readline())
        assert time.monotonic() - started <= 0.5
        assert second["type"] == "delta" and second["cursor"] != first["cursor"]
        latest = build_snapshot(path, "run_source")
        assert second["current_id"] == current_node_id(latest)
        assert apply_deltas(
            current,
            second["deltas"],
            cursor=second["cursor"],
            heads=second["heads"],
            graph_sha256=second["graph_sha256"],
            omitted_counts=second["omitted_counts"],
            unknowns=second["unknowns"],
            review_brief=second["review_brief"],
            support_paths=second["support_paths"],
        ) == latest
        assert sum(
            delta["op"] == "upsert_node"
            and delta["node"]["id"] == f"event:run_source:{second_event.event_id}"
            for delta in second["deltas"]
        ) == 1
    finally:
        for connection, response in connections:
            response.close()
            connection.close()
        server.should_exit = True
        thread.join(timeout=2)
        listener.close()
    assert not thread.is_alive()
