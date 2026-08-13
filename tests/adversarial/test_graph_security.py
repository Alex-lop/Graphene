from __future__ import annotations

import base64
import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))
from demo.graph_mvp import (  # noqa: E402
    HEADERS,
    TOKEN,
    prepare_waiting_demo,
    promotion_request,
)
from graphene.app import FIXTURE_ROOT, GOLDEN, GRAPH_CONTRACT, create_app  # noqa: E402
from graphene.context import build_context_packet  # noqa: E402
from graphene.execution import FixtureAccessError, ScopedFixtureTools  # noqa: E402
from graphene.hashing import canonical_json_sha256  # noqa: E402
from graphene.models import (  # noqa: E402
    ExecuteRunRequest,
    GraphResponse,
    PromoteRunRequest,
    TaskSpec,
)
from graphene.store import InMemoryStore, JsonFileStore  # noqa: E402


def _flip(value: str) -> str:
    return ("0" if value[0] != "0" else "1") + value[1:]


def _assert_empty_context(packet) -> None:
    assert packet.decision.value == "denied_out_of_scope"
    assert packet.allowed_paths == ()
    assert packet.allowed_tools == ()
    assert packet.approved_memories == ()
    assert packet.related_files == ()
    assert packet.selected_node_ids == ()


@pytest.fixture
def waiting(tmp_path):
    path = tmp_path / "store.json"
    client = TestClient(create_app(JsonFileStore(path), TOKEN))
    client.headers.update(HEADERS)
    data = prepare_waiting_demo(client)
    yield client, data, path
    client.close()


def test_mutations_require_the_server_token():
    store = InMemoryStore()
    with TestClient(create_app(store, TOKEN)) as client:
        response = client.post(
            "/api/runs",
            json={
                "task_id": "baseline_max_attempts",
                "idempotency_key": "unauthorized_create_1",
            },
        )
        assert response.status_code == 401
        assert store.list_runs() == ()


@pytest.mark.parametrize(
    ("profile", "task"),
    [
        ("billing-observer@1", GOLDEN.tasks[1]),
        (
            "auth-maintainer@1",
            TaskSpec.model_validate(
                {
                    **GOLDEN.tasks[1].model_dump(),
                    "target_paths": ("docs/security.md",),
                    "expected_changed_paths": ("docs/security.md",),
                }
            ),
        ),
    ],
)
def test_billing_and_wrong_path_receive_empty_context(profile, task):
    packet = build_context_packet(
        contract=GRAPH_CONTRACT,
        task=task,
        consumer_run_id="denied_run",
        consumer_agent_profile_id=profile,
        packet_id="ctx_denied",
        base_sha="a" * 40,
        tool_names=GOLDEN.tool_names,
        memories=(),
        source_graph_hash="b" * 64,
        selected_node_ids=("secret_node",),
    )
    _assert_empty_context(packet)


def test_graph_has_no_mutation_route_and_depth_and_caps_are_honest(waiting):
    client, data, _ = waiting
    run_id = data["adapted"]["run_id"]
    path = f"/api/runs/{run_id}/graph"
    before = client.get(path).json()

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, path, json={}, headers=HEADERS).status_code in {404, 405}
    assert client.get(path).json() == before
    assert client.get(path, params={"depth": 3}).status_code == 422
    assert len(before["nodes"]) <= GRAPH_CONTRACT.caps.max_nodes
    assert len(before["edges"]) <= GRAPH_CONTRACT.caps.max_edges
    assert before["truncated"] == any(before["omitted_counts"].values())
    assert all(
        edge["source"] in {node["id"] for node in before["nodes"]}
        and edge["target"] in {node["id"] for node in before["nodes"]}
        for edge in before["edges"]
    )

    dishonest = {**before, "truncated": False, "omitted_counts": {"nodes": 1}}
    dishonest["graph_hash"] = canonical_json_sha256(
        {key: value for key, value in dishonest.items() if key != "graph_hash"}
    )
    with pytest.raises(ValidationError):
        GraphResponse.model_validate(dishonest)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("candidate_patch_sha256", _flip),
        ("context_packet_sha256", _flip),
        ("test_receipt_sha256", _flip),
        ("base_commit_sha", _flip),
        ("source_graph_hash", _flip),
        ("memory_revision", lambda value: value + 1),
        ("expected_run_revision", lambda value: value + 1),
    ],
)
def test_promotion_rejects_each_stale_or_substituted_binding(waiting, field, tampered):
    client, data, _ = waiting
    run_id = data["adapted"]["run_id"]
    request = promotion_request(data["adapted"], data["packet"])
    request[field] = tampered(request[field])

    response = client.post(
        f"/api/runs/{run_id}/promote",
        json=request,
        headers=HEADERS,
    )
    assert response.status_code == 409
    persisted = client.get(f"/api/runs/{run_id}").json()
    assert persisted["state"] == "waiting_for_promotion"
    assert persisted["promotion_decision"] is None
    assert persisted["promotion_receipt"] is None


def test_changed_execute_request_cannot_reuse_the_successful_key(waiting):
    client, data, _ = waiting
    run_id = data["adapted"]["run_id"]
    response = client.post(
        f"/api/runs/{run_id}/execute",
        json={
            "expected_run_revision": 1,
            "idempotency_key": "adapted_execute_001",
        },
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert client.get(f"/api/runs/{run_id}").json() == data["adapted"]


def test_model_cannot_supply_scope_graph_test_or_approval_authority():
    forbidden = {
        "agent_profile_id",
        "allowed_paths",
        "allowed_tools",
        "approval",
        "human_decision_id",
        "graph_facts",
        "test_success",
        "model_id",
    }
    assert forbidden.isdisjoint(ExecuteRunRequest.model_fields)
    assert {"approval", "human_decision_id"}.isdisjoint(PromoteRunRequest.model_fields)

    store = InMemoryStore()
    with TestClient(create_app(store, TOKEN)) as client:
        run = client.post(
            "/api/runs",
            json={
                "task_id": "baseline_max_attempts",
                "idempotency_key": "authority_create_001",
            },
            headers=HEADERS,
        ).json()
        response = client.post(
            f"/api/runs/{run['run_id']}/execute",
            json={
                "expected_run_revision": 0,
                "idempotency_key": "authority_execute_01",
                "agent_profile_id": "billing-observer@1",
                "allowed_paths": ["billing/**"],
                "approval": "approve",
                "graph_facts": [{"kind": "promotion_receipt"}],
                "test_success": True,
                "model_id": "forged-model",
            },
            headers=HEADERS,
        )
        assert response.status_code == 422
        assert store.get_run(run["run_id"]).state.value == "queued"


def test_one_byte_patch_tamper_is_rejected_when_the_store_reopens(waiting):
    client, data, path = waiting
    client.close()
    snapshot = json.loads(path.read_text())
    run = next(item for item in snapshot["runs"] if item["run_id"] == data["adapted"]["run_id"])
    patch = bytearray(base64.b64decode(run["candidate"]["canonical_patch_base64"]))
    patch[0] ^= 1
    run["candidate"]["canonical_patch_base64"] = base64.b64encode(patch).decode()
    path.write_text(json.dumps(snapshot, separators=(",", ":"), sort_keys=True))

    with pytest.raises(ValidationError):
        JsonFileStore(path)


def test_one_byte_human_decision_tamper_is_rejected_when_the_store_reopens(waiting):
    client, data, path = waiting
    request = promotion_request(data["adapted"], data["packet"])
    completed = client.post(
        f"/api/runs/{data['adapted']['run_id']}/promote",
        json=request,
        headers=HEADERS,
    )
    assert completed.status_code == 200
    changed = {**request, "candidate_tree_sha256": _flip(request["candidate_tree_sha256"])}
    assert client.post(
        f"/api/runs/{data['adapted']['run_id']}/promote",
        json=changed,
        headers=HEADERS,
    ).status_code == 409
    assert client.post(
        f"/api/runs/{data['adapted']['run_id']}/promote",
        json={**request, "idempotency_key": "second_promote_001"},
        headers=HEADERS,
    ).status_code == 409
    assert client.get(f"/api/runs/{data['adapted']['run_id']}").json() == completed.json()
    client.close()

    snapshot = json.loads(path.read_text())
    run = next(item for item in snapshot["runs"] if item["run_id"] == data["adapted"]["run_id"])
    run["promotion_decision"]["bound_digest"] = _flip(
        run["promotion_decision"]["bound_digest"]
    )
    path.write_text(json.dumps(snapshot, separators=(",", ":"), sort_keys=True))

    with pytest.raises(ValidationError):
        JsonFileStore(path)


def test_traversal_and_symlink_escape_reuse_the_scoped_tool_boundary(tmp_path):
    root = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, root)
    tools = ScopedFixtureTools(
        root,
        allowed_paths=GOLDEN.fixture.mutable_paths,
        policy=GOLDEN.fixture,
    )
    with pytest.raises(FixtureAccessError):
        tools.read_file("../outside")

    outside = tmp_path / "secret.py"
    outside.write_text("SECRET_CANARY")
    (root / "tests/test_security_policy.py").symlink_to(outside)
    with pytest.raises(FixtureAccessError):
        tools.write_file("tests/test_security_policy.py", "forged")
    assert outside.read_text() == "SECRET_CANARY"


def test_fake_environment_cannot_upgrade_unverified_truth_labels(monkeypatch):
    canary = "SECRET_CANARY_DO_NOT_PERSIST"
    monkeypatch.setenv("GOOGLE_API_KEY", canary)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "forged-project")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")

    with TestClient(create_app(InMemoryStore(), TOKEN)) as client:
        client.headers.update(HEADERS)
        health = client.get("/healthz").json()
        catalog = client.get("/api/agent-catalog").json()
    assert health == {
        "status": "ok",
        "execution": "deterministic-local",
        "gemini": "unverified",
        "firestore": "unverified",
        "cloud_run": "unverified",
    }
    assert all(
        "unverified" in profile["model_policy"].lower()
        or profile["agent_profile_id"] == "billing-observer@1"
        for profile in catalog
    )
    assert canary not in json.dumps({"health": health, "catalog": catalog})


def test_generated_local_evidence_is_sanitized_and_claims_no_cloud_or_model_run():
    evidence = json.loads((ROOT / "evidence/local_vertical_slice.json").read_text())
    soak = json.loads((ROOT / "evidence/local_soak.json").read_text())
    assert evidence["contract_hash"] == (
        "74c871a9f06b1dbd2c54a2837d0cfc4812177b780425300d41497b0a24655be2"
    )
    assert evidence["execution_mode"] == "deterministic-local"
    assert evidence["adapted"]["model_id"] is None
    assert evidence["verification"] == {
        "cloud_run": "unverified",
        "firestore": "unverified",
        "gemini": "unverified",
        "json_file_restart": "verified",
        "local_vertical_slice": "verified",
    }
    assert soak["requested_count"] == soak["pass_count"] == 10
    assert soak["node_counts"] == [20] * 10
    assert soak["edge_counts"] == [19] * 10
    assert soak["verification"] == evidence["verification"]
    rendered = json.dumps({"vertical_slice": evidence, "soak": soak}).lower()
    assert all(
        value not in rendered
        for value in (
            "secret_canary",
            "api_key",
            "bearer ",
            "password",
            "canonical_patch_base64",
            "unified_diff",
        )
    )
