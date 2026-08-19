from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from graphene.orchestration.cloud import (
    CLOUD_PROOF,
    CLOUD_STREAM_INTERVAL_SECONDS,
    CloudConfigurationError,
    create_cloud_app,
)


CONFIGURATION = {
    "project_id": "authorized-sandbox-project",
    "database_id": "(default)",
    "namespace": "graphene",
    "mission_id": "mission_cloud_001",
    "read_token": "read_token_0000000001",
}
ROOT = Path(__file__).resolve().parents[3]


class UnusedStore:
    def snapshot(self, _mission_id):
        raise AssertionError("liveness must not claim Firestore readiness")

    def tail(self, _mission_id, _after_seq, _limit):
        raise AssertionError("liveness must not scan mission events")


def test_factory_fails_closed_without_every_explicit_setting(monkeypatch):
    for name in (
        "GOOGLE_CLOUD_PROJECT",
        "GRAPHENE_FIRESTORE_DATABASE",
        "GRAPHENE_FIRESTORE_NAMESPACE",
        "GRAPHENE_MISSION_ID",
        "GRAPHENE_MISSION_CONTROL_READ_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(
        CloudConfigurationError, match="GOOGLE_CLOUD_PROJECT must be explicitly"
    ):
        create_cloud_app(store=UnusedStore())


def test_health_and_mission_control_are_read_only_and_honest():
    app = create_cloud_app(**CONFIGURATION, store=UnusedStore())
    client = TestClient(app)

    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "cloud_proof": "NOT PROVEN",
        "read_only": True,
        "readiness": "NOT PROVEN",
        "repository_execution": False,
        "status": "configured",
    }
    assert CLOUD_PROOF == "NOT PROVEN"

    page = client.get("/mission-control/mission_cloud_001")
    assert page.status_code == 200
    assert "CLOUD PATH NOT PROVEN" in page.text
    assert CONFIGURATION["read_token"] not in page.text
    assert CONFIGURATION["read_token"] not in str(page.headers)
    redirect = client.get("/", follow_redirects=False)
    assert redirect.headers["location"] == "/mission-control/mission_cloud_001"
    assert CONFIGURATION["read_token"] not in str(redirect.headers)

    unsafe = {"POST", "PUT", "PATCH", "DELETE"}
    assert all(
        not (getattr(route, "methods", None) or set()) & unsafe for route in app.routes
    )
    assert app.state.cloud_configuration == {
        "project_id": "authorized-sandbox-project",
        "database_id": "(default)",
        "namespace": "graphene",
        "mission_id": "mission_cloud_001",
        "cloud_proof": "NOT PROVEN",
        "stream_interval_seconds": 2.0,
    }
    assert CLOUD_STREAM_INTERVAL_SECONDS == 2.0


def test_factory_passes_explicit_project_and_database_without_fallback(monkeypatch):
    captured = {}
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)

    def client(*, project, database):
        captured.update(project=project, database=database)
        raise RuntimeError("credentials unavailable")

    monkeypatch.setattr("graphene.orchestration.cloud.firestore.Client", client)
    with pytest.raises(RuntimeError, match="credentials unavailable"):
        create_cloud_app(**CONFIGURATION)
    assert captured == {
        "project": "authorized-sandbox-project",
        "database": "(default)",
    }

    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    with pytest.raises(CloudConfigurationError, match="not allowed"):
        create_cloud_app(**CONFIGURATION)


def test_cloudrun_image_is_non_root_and_starts_only_the_cloud_factory():
    dockerfile = (ROOT / "deploy/cloudrun/Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.count("@sha256:") == 2
    assert "USER 10001:10001" in dockerfile
    assert '"graphene.orchestration.cloud:create_cloud_app", "--factory"' in dockerfile
    assert "graphene.cli" not in dockerfile
    assert "scheduler" not in dockerfile
    assert "worker" not in dockerfile
    assert "chown" not in dockerfile


def test_deploy_uses_an_existing_secret_instead_of_a_literal_read_token():
    readme = (ROOT / "deploy/cloudrun/README.md").read_text(encoding="utf-8")
    plain_environment = next(
        line for line in readme.splitlines() if "--set-env-vars=" in line
    )

    assert "export READ_TOKEN='" not in readme
    assert "GRAPHENE_MISSION_CONTROL_READ_TOKEN" not in plain_environment
    assert (
        '--set-secrets="GRAPHENE_MISSION_CONTROL_READ_TOKEN='
        '$READ_TOKEN_SECRET:$READ_TOKEN_SECRET_VERSION"'
    ) in readme
    assert 'gcloud secrets describe "$READ_TOKEN_SECRET"' in readme
    assert 'gcloud secrets versions describe "$READ_TOKEN_SECRET_VERSION"' in readme
    assert "roles/secretmanager.secretAccessor" in readme
    assert "not an additional service claimed to pad the hackathon stack" in readme
