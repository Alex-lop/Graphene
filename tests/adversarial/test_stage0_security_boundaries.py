from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from graphene import legacy_app as app_module
from graphene import legacy_store as store_module
from graphene.legacy_app import GOLDEN, create_app
from graphene.execution import TestRun as _TestRun
from graphene.execution import adapter as adapter_module
from graphene.legacy_store import FirestoreStore, InMemoryStore


BEARER_CANARY = "stage0-synthetic-bearer-canary-7f0c1a"
WORK_CANARY = "stage0-synthetic-forbidden-work-canary-9b2e4d"
AUTH_HEADERS = {
    "authorization": f"Bearer {BEARER_CANARY}",
}


def _request(client: TestClient, method: str, path: str, body=None):
    return client.request(method, path, json=body, headers=AUTH_HEADERS)


def _execute(client: TestClient, task: str, key: str):
    created = _request(
        client,
        "POST",
        "/api/runs",
        {"task_id": task, "idempotency_key": f"{key}_create"},
    )
    assert created.status_code == 200
    run = created.json()
    executed = _request(
        client,
        "POST",
        f"/api/runs/{run['run_id']}/execute",
        {"expected_run_revision": 0, "idempotency_key": f"{key}_execute"},
    )
    assert executed.status_code == 200
    return executed.json()


def _hunks(client: TestClient, run_id: str):
    response = _request(client, "GET", f"/api/runs/{run_id}/graph")
    assert response.status_code == 200
    return [
        node
        for node in response.json()["nodes"]
        if node["kind"] == "hunk" and node["run_id"] == run_id
    ]


def _write_event(run: dict, path: str):
    return next(
        event
        for event in run["proof"]
        if event["type"] == "tool.file_written" and event["payload"]["path"] == path
    )


def _feedback(run: dict, hunk: dict, evidence_event_id: str, key: str):
    return {
        "correction": GOLDEN.memory.correction,
        "evidence_event_id": evidence_event_id,
        "selected_hunk_id": hunk["id"],
        "scope_id": "all_auth",
        "expected_run_revision": run["revision"],
        "idempotency_key": key,
    }


READ_PATHS = (
    "/api/runs",
    "/api/runs/not_a_run",
    "/api/runs/not_a_run/proof",
    "/api/runs/not_a_run/graph",
    "/api/runs/not_a_run/graph/nodes/not_a_node",
    "/api/runs/not_a_run/context-packet",
    "/api/agent-catalog",
    "/",
    "/openapi.json",
    "/docs",
    "/redoc",
)


@pytest.mark.parametrize("path", READ_PATHS)
def test_every_non_health_read_authenticates_before_store_access(path):
    store = Mock(wraps=InMemoryStore())
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        response = client.get(path)

    assert (response.status_code, store.method_calls) == (401, [])


def test_health_remains_public_and_does_not_touch_the_store():
    store = Mock(wraps=InMemoryStore())
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        response = client.get("/healthz")

    assert (response.status_code, store.method_calls) == (200, [])


MUTATION_CASES = (
    ("/api/demo/reset", {"idempotency_key": "unauth_reset"}),
    (
        "/api/runs",
        {"task_id": "baseline_max_attempts", "idempotency_key": "unauth_create"},
    ),
    (
        "/api/runs/not_a_run/execute",
        {"expected_run_revision": 0, "idempotency_key": "unauth_execute"},
    ),
    (
        "/api/runs/not_a_run/feedback",
        {
            "correction": GOLDEN.memory.correction,
            "evidence_event_id": "event_unknown",
            "selected_hunk_id": "hunk_unknown",
            "scope_id": "all_auth",
            "expected_run_revision": 0,
            "idempotency_key": "unauth_feedback",
        },
    ),
    (
        "/api/memories/not_a_memory/decision",
        {
            "decision": "approve",
            "expected_revision": 1,
            "idempotency_key": "unauth_memory_decision",
        },
    ),
    (
        "/api/runs/not_a_run/promote",
        {
            "expected_run_revision": 0,
            "base_commit_sha": "a" * 40,
            "candidate_patch_sha256": "b" * 64,
            "candidate_tree_sha256": "c" * 64,
            "candidate_tree_hash_version": "graphene.tree.v2",
            "memory_id": "memory_unknown",
            "memory_revision": 1,
            "context_packet_id": "packet_unknown",
            "context_packet_sha256": "d" * 64,
            "source_graph_revision": 1,
            "source_graph_hash": "e" * 64,
            "selected_node_ids": ["node_unknown"],
            "test_receipt_sha256": "f" * 64,
            "idempotency_key": "unauth_promote",
        },
    ),
)


@pytest.mark.parametrize(("path", "body"), MUTATION_CASES)
def test_every_non_health_mutation_authenticates_before_store_access(path, body):
    store = Mock(wraps=InMemoryStore())
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        response = client.post(path, json=body)

    assert (response.status_code, store.method_calls) == (401, [])


def test_bearer_header_replaces_the_legacy_token_header():
    store = InMemoryStore()
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        bearer = client.post(
            "/api/runs",
            json={
                "task_id": "baseline_max_attempts",
                "idempotency_key": "bearer_only_create",
            },
            headers={"authorization": f"Bearer {BEARER_CANARY}"},
        )
        legacy = client.post(
            "/api/runs",
            json={
                "task_id": "baseline_max_attempts",
                "idempotency_key": "legacy_only_create",
            },
            headers={"x-graphene-token": BEARER_CANARY},
        )

    assert (bearer.status_code, legacy.status_code, len(store.list_runs())) == (200, 401, 1)


def test_invalid_bearer_is_not_echoed_and_cannot_probe_a_resource(caplog):
    store = Mock(wraps=InMemoryStore())
    with TestClient(create_app(store, "different-synthetic-token")) as client:
        response = client.get(
            "/api/runs/not_a_run",
            headers={"authorization": f"Bearer {BEARER_CANARY}"},
        )

    leaks = {
        surface
        for surface, value in {
            "http_response": response.text,
            "application_log": caplog.text,
        }.items()
        if BEARER_CANARY in value
    }
    assert (response.status_code, store.method_calls, leaks) == (401, [], set())


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return deepcopy(self._data)


def _fake_firestore(monkeypatch):
    document = Mock()
    document.data = None
    document.get.side_effect = lambda transaction=None: _Snapshot(deepcopy(document.data))
    transaction = Mock()
    transaction.set.side_effect = lambda target, data: setattr(target, "data", deepcopy(data))
    client = Mock()
    client.collection.return_value.document.return_value = document
    client.transaction.return_value = transaction
    monkeypatch.setattr(store_module.firestore, "transactional", lambda function: function)
    return FirestoreStore(client, "stage0"), document


def test_raw_work_and_bearer_canaries_never_reach_http_firestore_or_logs(monkeypatch, caplog):
    monkeypatch.setattr(
        adapter_module,
        "run_fixture_tests",
        lambda *_: _TestRun(0, False, WORK_CANARY, False),
    )
    store, document = _fake_firestore(monkeypatch)
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        run = _execute(client, "baseline_max_attempts", "canary_output")

    surfaces = {
        "http_response": json.dumps(run, sort_keys=True),
        "firestore": json.dumps(document.data, sort_keys=True),
        "application_log": caplog.text,
    }
    leaks = {
        f"{canary_name}:{surface}"
        for canary_name, canary in (
            ("work", WORK_CANARY),
            ("bearer", BEARER_CANARY),
        )
        for surface, value in surfaces.items()
        if canary in value
    }
    assert leaks == set()


def test_raw_execution_error_is_not_persisted_or_returned(monkeypatch, caplog):
    def fail(**_):
        raise RuntimeError(WORK_CANARY)

    monkeypatch.setattr(app_module, "execute_deterministic_local", fail)
    store = InMemoryStore()
    with TestClient(create_app(store, BEARER_CANARY), raise_server_exceptions=False) as client:
        created = _request(
            client,
            "POST",
            "/api/runs",
            {
                "task_id": "baseline_max_attempts",
                "idempotency_key": "canary_error_create",
            },
        )
        assert created.status_code == 200
        response = _request(
            client,
            "POST",
            f"/api/runs/{created.json()['run_id']}/execute",
            {"expected_run_revision": 0, "idempotency_key": "canary_error_execute"},
        )

    leaks = {
        surface
        for surface, value in {
            "http_response": response.text,
            "store_snapshot": json.dumps(store.snapshot(), sort_keys=True),
            "application_log": caplog.text,
        }.items()
        if WORK_CANARY in value
    }
    assert leaks == set()


@pytest.mark.parametrize("invalid_kind", ("unknown", "non_write", "foreign_run"))
def test_invalid_evidence_event_cannot_create_feedback_or_memory(invalid_kind):
    store = InMemoryStore()
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        run = _execute(client, "baseline_max_attempts", f"invalid_{invalid_kind}_origin")
        hunk = _hunks(client, run["run_id"])[0]
        if invalid_kind == "unknown":
            evidence_event_id = "event_not_persisted"
        elif invalid_kind == "non_write":
            evidence_event_id = next(
                event["event_id"]
                for event in run["proof"]
                if event["type"] == "completion.denied"
            )
        else:
            foreign = _execute(
                client,
                "baseline_max_attempts",
                "invalid_foreign_run_source",
            )
            evidence_event_id = _write_event(foreign, hunk["data"]["path"])["event_id"]

        response = _request(
            client,
            "POST",
            f"/api/runs/{run['run_id']}/feedback",
            _feedback(run, hunk, evidence_event_id, f"invalid_{invalid_kind}_feedback"),
        )

    snapshot = store.snapshot()
    rejected = 400 <= response.status_code < 500
    assert (rejected, len(snapshot["feedback"]), len(snapshot["memories"])) == (True, 0, 0)


def test_valid_feedback_anchor_matches_run_repo_base_profile_write_and_hunk():
    store = InMemoryStore()
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        run = _execute(client, "baseline_max_attempts", "valid_anchor_origin")
        hunk = _hunks(client, run["run_id"])[0]
        write = _write_event(run, hunk["data"]["path"])
        response = _request(
            client,
            "POST",
            f"/api/runs/{run['run_id']}/feedback",
            _feedback(run, hunk, write["event_id"], "valid_anchor_feedback"),
        )

    assert response.status_code == 200
    memory = response.json()
    feedback = store.get_feedback(memory["feedback_id"])
    assert feedback is not None
    assert (
        feedback.run_id,
        feedback.selected_hunk_id,
        memory["evidence_run_id"],
        memory["repo_id"],
    ) == (run["run_id"], hunk["id"], run["run_id"], run["repo_id"])
    assert run["repo_id"] == GOLDEN.repo_id
    assert run["base_sha"] == run["candidate"]["base_commit_sha"]
    assert run["agent_profile_id"] == "platform-maintainer@1"
    assert write["run_id"] == run["run_id"]
    assert write["payload"]["path"] == hunk["data"]["path"]
    assert write["payload"]["after_sha256"] == hunk["data"]["after_sha256"]


def test_evidence_write_must_match_the_selected_hunk_before_any_feedback_write():
    store = InMemoryStore()
    with TestClient(create_app(store, BEARER_CANARY)) as client:
        origin = _execute(client, "baseline_max_attempts", "mismatch_origin")
        origin_hunk = _hunks(client, origin["run_id"])[0]
        origin_write = _write_event(origin, origin_hunk["data"]["path"])
        proposed = _request(
            client,
            "POST",
            f"/api/runs/{origin['run_id']}/feedback",
            _feedback(origin, origin_hunk, origin_write["event_id"], "mismatch_seed_feedback"),
        )
        assert proposed.status_code == 200
        approved = _request(
            client,
            "POST",
            f"/api/memories/{proposed.json()['memory_id']}/decision",
            {
                "decision": "approve",
                "expected_revision": proposed.json()["revision"],
                "idempotency_key": "mismatch_seed_approval",
            },
        )
        assert approved.status_code == 200
        adapted = _execute(client, "adapted_window_seconds", "mismatch_adapted")
        hunks = _hunks(client, adapted["run_id"])
        limiter_hunk = next(node for node in hunks if node["data"]["path"] == "app/auth/limiter.py")
        test_write = _write_event(adapted, "tests/test_security_policy.py")
        before = store.snapshot()

        response = _request(
            client,
            "POST",
            f"/api/runs/{adapted['run_id']}/feedback",
            _feedback(
                adapted,
                limiter_hunk,
                test_write["event_id"],
                "mismatch_adapted_feedback",
            ),
        )

    after = store.snapshot()
    rejected = 400 <= response.status_code < 500
    assert (
        rejected,
        len(after["feedback"]),
        len(after["memories"]),
    ) == (True, len(before["feedback"]), len(before["memories"]))
