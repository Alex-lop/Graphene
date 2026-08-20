#!/usr/bin/env python3
"""Run and verify the deterministic-local Graphene graph demo."""

from __future__ import annotations

import argparse
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from graphene.app import GOLDEN, GRAPH_CONTRACT, create_app
from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.store import JsonFileStore

TOKEN = "graphene-local-demo"
HEADERS = {"authorization": f"Bearer {TOKEN}"}


def _json(response, expected: int = 200) -> dict[str, Any]:
    if response.status_code != expected:
        raise RuntimeError(f"{response.request.method} {response.request.url.path}: {response.text}")
    return response.json()


def _post(client: TestClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _json(client.post(path, json=payload, headers=HEADERS))


def _get(client: TestClient, path: str) -> dict[str, Any]:
    return _json(client.get(path, headers=HEADERS))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def prepare_waiting_demo(client: TestClient) -> dict[str, Any]:
    """Reset and run both frozen tasks through the adapted completion denial."""

    _post(
        client,
        "/api/demo/reset",
        {"idempotency_key": f"demo_reset_{uuid.uuid4().hex}"},
    )
    _require(_get(client, "/api/runs") == [], "reset left persisted runs")

    baseline = _post(
        client,
        "/api/runs",
        {
            "task_id": "baseline_max_attempts",
            "idempotency_key": "baseline_create_0001",
        },
    )
    baseline = _post(
        client,
        f"/api/runs/{baseline['run_id']}/execute",
        {"expected_run_revision": 0, "idempotency_key": "baseline_execute_001"},
    )
    _require(baseline["state"] == "waiting_for_promotion", "baseline did not pause")
    _require(baseline["agent_profile_id"] == "platform-maintainer@1", "wrong origin profile")
    _require(baseline["model_id"] is None, "local baseline claimed a model")
    _require(baseline["promotion_receipt"] is None, "denied baseline was promoted")
    _require(baseline["proof"][-1]["type"] == "completion.denied", "missing baseline denial")

    baseline_graph = _get(client, f"/api/runs/{baseline['run_id']}/graph")
    baseline_hunk = next(node for node in baseline_graph["nodes"] if node["kind"] == "hunk")
    baseline_detail = _get(
        client,
        f"/api/runs/{baseline['run_id']}/graph/nodes/{baseline_hunk['id']}",
    )
    _require(
        sha256_hex(baseline_detail["data"]["unified_diff"].encode())
        == baseline_detail["data"]["exact_hunk_sha256"],
        "origin hunk bytes do not match their digest",
    )

    memory = _post(
        client,
        f"/api/runs/{baseline['run_id']}/feedback",
        {
            "correction": GOLDEN.memory.correction,
            "evidence_event_id": baseline["proof"][0]["event_id"],
            "selected_hunk_id": baseline_hunk["id"],
            "scope_id": "all_auth",
            "expected_run_revision": baseline["revision"],
            "idempotency_key": "baseline_feedback_01",
        },
    )
    _require(memory["state"] == "proposed", "feedback did not propose memory")
    memory = _post(
        client,
        "/api/memories/mem_auth_review/decision",
        {
            "decision": "approve",
            "expected_revision": 1,
            "idempotency_key": "memory_approve_0001",
        },
    )
    _require(memory["state"] == "approved", "human memory approval was not persisted")
    _require(memory["decision"]["actor"] == "human", "memory was not human-approved")

    adapted = _post(
        client,
        "/api/runs",
        {
            "task_id": "adapted_window_seconds",
            "idempotency_key": "adapted_create_0001",
        },
    )
    _require(adapted["session_id"] != baseline["session_id"], "adapted session was reused")
    execute_adapted = {
        "expected_run_revision": 0,
        "idempotency_key": "adapted_execute_001",
    }
    adapted = _post(
        client,
        f"/api/runs/{adapted['run_id']}/execute",
        execute_adapted,
    )
    _require(
        _post(client, f"/api/runs/{adapted['run_id']}/execute", execute_adapted)
        == adapted,
        "exact execute replay did not return its persisted result",
    )
    packet = _get(client, f"/api/runs/{adapted['run_id']}/context-packet")
    injection = client.app.state.store.get_injection_receipt(adapted["run_id"])

    _require(adapted["state"] == "waiting_for_promotion", "adapted run did not pause")
    _require(adapted["agent_profile_id"] == "auth-maintainer@1", "wrong adapted profile")
    _require(adapted["fresh_session"] is True, "adapted run is not fresh")
    _require(adapted["model_id"] is None, "local adapted run claimed a model")
    _require(adapted["promotion_receipt"] is None, "completion denial created a receipt")
    _require(adapted["proof"][-1]["type"] == "completion.denied", "missing real denial")
    _require(packet["decision"] == "allowed", "adapted packet was denied")
    _require(packet["approved_memories"] == [{
        "memory_id": "mem_auth_review",
        "revision": 1,
        "exact_text": GOLDEN.memory.rule,
    }], "packet did not contain exact approved memory")
    _require(
        packet["packet_sha256"]
        == canonical_json_sha256({key: value for key, value in packet.items() if key != "packet_sha256"}),
        "packet hash mismatch",
    )
    _require(
        injection is not None
        and injection.persisted_before_model_call
        and injection.packet_sha256 == packet["packet_sha256"],
        "injection was not bound to the persisted packet",
    )
    _require(
        adapted["candidate"]["changed_paths"]
        == ["app/auth/limiter.py", "tests/test_security_policy.py"],
        "adapted candidate escaped the frozen paths",
    )
    test = adapted["candidate"]["test_receipt"]
    _require(test["candidate_exit_code"] == 0, "candidate tests failed")
    _require(test["base_with_new_test_exit_code"] not in (None, 0), "new test passed on base")

    graph = _get(client, f"/api/runs/{adapted['run_id']}/graph")
    hunk = next(
        node
        for node in graph["nodes"]
        if node["kind"] == "hunk" and node["run_id"] == adapted["run_id"]
    )
    detail = _get(client, f"/api/runs/{adapted['run_id']}/graph/nodes/{hunk['id']}")
    feedback = next(node for node in graph["nodes"] if node["kind"] == "feedback")
    _require(feedback["data"]["exact_correction"] == GOLDEN.memory.correction, "feedback was rewritten")
    _require(
        sha256_hex(detail["data"]["unified_diff"].encode())
        == detail["data"]["exact_hunk_sha256"],
        "adapted hunk bytes do not match their digest",
    )
    return {
        "baseline": baseline,
        "baseline_hunk": baseline_hunk,
        "memory": memory,
        "adapted": adapted,
        "packet": packet,
        "graph": graph,
        "hunk": hunk,
        "detail": detail,
    }


def promotion_request(adapted: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    candidate = adapted["candidate"]
    return {
        "expected_run_revision": adapted["revision"],
        "base_commit_sha": candidate["base_commit_sha"],
        "candidate_patch_sha256": candidate["candidate_patch_sha256"],
        "candidate_tree_sha256": candidate["candidate_tree_sha256"],
        "candidate_tree_hash_version": candidate["candidate_tree_hash_version"],
        "memory_id": "mem_auth_review",
        "memory_revision": 1,
        "context_packet_id": packet["packet_id"],
        "context_packet_sha256": packet["packet_sha256"],
        "source_graph_revision": adapted["source_graph_revision"],
        "source_graph_hash": adapted["source_graph_hash"],
        "selected_node_ids": adapted["selected_node_ids"],
        "test_receipt_sha256": candidate["test_receipt"]["receipt_sha256"],
        "idempotency_key": "adapted_promote_001",
    }


def run_local_demo(store_path: Path) -> dict[str, Any]:
    """Run the golden loop and return a sanitized manifest of observed facts."""

    with TestClient(create_app(JsonFileStore(store_path), TOKEN)) as client:
        waiting = prepare_waiting_demo(client)
        pre_graph = waiting["graph"]
        pre_detail = waiting["detail"]
        run_id = waiting["adapted"]["run_id"]
        request = promotion_request(waiting["adapted"], waiting["packet"])

    with TestClient(create_app(JsonFileStore(store_path), TOKEN)) as client:
        _require(
            _get(client, f"/api/runs/{run_id}/graph") == pre_graph,
            "pre-promotion graph changed after restart",
        )
        _require(
            _get(client, f"/api/runs/{run_id}/graph/nodes/{waiting['hunk']['id']}")
            == pre_detail,
            "pre-promotion detail changed after restart",
        )
        completed = _post(client, f"/api/runs/{run_id}/promote", request)
        _require(completed["state"] == "completed", "exact promotion did not complete")
        _require(
            _post(client, f"/api/runs/{run_id}/promote", request) == completed,
            "exact promotion replay did not return its persisted result",
        )
        _require(completed["promotion_decision"]["actor"] == "human", "promotion was not human-bound")
        receipt = completed["promotion_receipt"]
        _require(receipt["candidate_patch_sha256"] == request["candidate_patch_sha256"], "receipt patch mismatch")
        _require(receipt["context_packet_sha256"] == request["context_packet_sha256"], "receipt packet mismatch")
        _require(receipt["test_receipt_sha256"] == request["test_receipt_sha256"], "receipt test mismatch")
        final_graph = _get(client, f"/api/runs/{run_id}/graph")
        final_detail = _get(
            client, f"/api/runs/{run_id}/graph/nodes/{waiting['hunk']['id']}"
        )

    with TestClient(create_app(JsonFileStore(store_path), TOKEN)) as client:
        rebuilt_graph = _get(client, f"/api/runs/{run_id}/graph")
        rebuilt_detail = _get(
            client, f"/api/runs/{run_id}/graph/nodes/{waiting['hunk']['id']}"
        )
        rebuilt_run = _get(client, f"/api/runs/{run_id}")
        health = _json(client.get("/healthz"))

    _require(rebuilt_graph == final_graph, "final graph changed after restart")
    _require(rebuilt_detail == final_detail, "final hunk detail changed after restart")
    _require(rebuilt_run["promotion_receipt"] == receipt, "promotion receipt changed after restart")
    node_ids = {node["id"] for node in final_graph["nodes"]}
    _require(
        all(edge["source"] in node_ids and edge["target"] in node_ids for edge in final_graph["edges"]),
        "graph contains an unresolved edge",
    )
    _require(final_graph["truncated"] == bool(final_graph["omitted_counts"]), "dishonest truncation")

    candidate = waiting["adapted"]["candidate"]
    manifest = {
        "schema_version": 1,
        "observed_at": rebuilt_run["promotion_decision"]["occurred_at"],
        "contract_hash": canonical_json_sha256(GRAPH_CONTRACT.model_dump(mode="json")),
        "execution_mode": health["execution"],
        "verification": {
            "local_vertical_slice": "verified",
            "json_file_restart": "verified",
            "gemini": health["gemini"],
            "firestore": health["firestore"],
            "cloud_run": health["cloud_run"],
        },
        "origin": {
            "run_id": waiting["baseline"]["run_id"],
            "agent_profile_id": waiting["baseline"]["agent_profile_id"],
            "session_id": waiting["baseline"]["session_id"],
            "selected_hunk_id": waiting["baseline_hunk"]["id"],
            "completion": "denied",
        },
        "memory": {
            "memory_id": waiting["memory"]["memory_id"],
            "revision": waiting["memory"]["revision"],
            "state": waiting["memory"]["state"],
            "correction_sha256": sha256_hex(GOLDEN.memory.correction.encode()),
        },
        "adapted": {
            "run_id": run_id,
            "agent_profile_id": waiting["adapted"]["agent_profile_id"],
            "session_id": waiting["adapted"]["session_id"],
            "fresh_session": waiting["adapted"]["fresh_session"],
            "model_id": waiting["adapted"]["model_id"],
            "base_commit_sha": candidate["base_commit_sha"],
            "context_packet_sha256": waiting["packet"]["packet_sha256"],
            "candidate_patch_sha256": candidate["candidate_patch_sha256"],
            "candidate_tree_sha256": candidate["candidate_tree_sha256"],
            "candidate_tree_hash_version": candidate["candidate_tree_hash_version"],
            "test_receipt_sha256": candidate["test_receipt"]["receipt_sha256"],
            "changed_paths": candidate["changed_paths"],
            "candidate_test_exit_code": candidate["test_receipt"]["candidate_exit_code"],
            "base_with_new_test_exit_code": candidate["test_receipt"]["base_with_new_test_exit_code"],
            "completion": "denied_before_human_promotion",
        },
        "promotion": {
            "state": rebuilt_run["state"],
            "commit_sha": receipt["commit_sha"],
            "human_decision_id": receipt["human_decision_id"],
            "receipt_bindings_verified_after_restart": True,
        },
        "graph": {
            "revision": final_graph["revision"],
            "graph_hash": final_graph["graph_hash"],
            "node_count": len(final_graph["nodes"]),
            "edge_count": len(final_graph["edges"]),
            "truncated": final_graph["truncated"],
            "omitted_counts": final_graph["omitted_counts"],
            "exact_hunk_sha256": final_detail["data"]["exact_hunk_sha256"],
            "graph_detail_and_receipt_stable_after_restart": True,
        },
        "sanitized": True,
    }
    return manifest


def run_local_soak(count: int) -> dict[str, Any]:
    """Run isolated local stores and stop immediately if any golden loop fails."""

    if count < 1:
        raise ValueError("soak count must be positive")
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="graphene-soak-") as temporary:
        root = Path(temporary)
        for number in range(1, count + 1):
            results.append(run_local_demo(root / str(number) / "store.json"))

    verification = results[0]["verification"]
    _require(
        all(result["verification"] == verification for result in results),
        "soak verification labels changed between runs",
    )
    return {
        "schema_version": 1,
        "observed_at": results[-1]["observed_at"],
        "contract_hash": results[0]["contract_hash"],
        "execution_mode": results[0]["execution_mode"],
        "requested_count": count,
        "pass_count": len(results),
        "node_counts": [result["graph"]["node_count"] for result in results],
        "edge_counts": [result["graph"]["edge_count"] for result in results],
        "verification": verification,
        "sanitized": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, help="optional durable local JSON store")
    parser.add_argument("--soak", type=int, help="run N isolated clean local stores")
    parser.add_argument("--evidence", type=Path, help="write the sanitized observed manifest")
    args = parser.parse_args()

    if args.soak is not None:
        if args.store:
            parser.error("--store cannot be combined with --soak")
        if args.soak < 1:
            parser.error("--soak must be positive")
        manifest = run_local_soak(args.soak)
    elif args.store:
        manifest = run_local_demo(args.store)
    else:
        with tempfile.TemporaryDirectory(prefix="graphene-demo-") as temporary:
            manifest = run_local_demo(Path(temporary) / "store.json")
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
