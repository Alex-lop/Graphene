from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from google.cloud import firestore

from ..hashing import canonical_json_bytes
from .coordinator import IdentityVerifier, create_coordinator_app
from .firestore_mission_store import FirestoreMissionStore
from .google_oidc import GoogleOidcExecutorVerifier
from .mission_control import create_mission_control_app
from .mission_models import MissionHead
from .mission_projection import MissionProjection

CLOUD_PROOF = "NOT PROVEN"
CLOUD_STREAM_INTERVAL_SECONDS = 2.0
_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_READ_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
_MAX_EXECUTOR_BINDINGS_BYTES = 16_384


class CloudConfigurationError(RuntimeError):
    """The Cloud Run control plane is missing explicit durable configuration."""


def _required(value: str | None, environment_name: str, *, limit: int = 512) -> str:
    if value is None:
        value = os.environ.get(environment_name)
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > limit
    ):
        raise CloudConfigurationError(
            f"{environment_name} must be explicitly configured"
        )
    return value


def create_cloud_app(
    *,
    project_id: str | None = None,
    database_id: str | None = None,
    namespace: str | None = None,
    mission_id: str | None = None,
    read_token: str | None = None,
    store: Any | None = None,
) -> FastAPI:
    """Build the read-only Firestore Mission Control Cloud Run process.

    There is deliberately no local-store fallback and no repository executor in
    this process. Cloud Run stores and projects control state only.
    """

    project_id = _required(project_id, "GOOGLE_CLOUD_PROJECT", limit=128)
    database_id = _required(database_id, "GRAPHENE_FIRESTORE_DATABASE", limit=128)
    namespace = _required(namespace, "GRAPHENE_FIRESTORE_NAMESPACE", limit=32)
    mission_id = _required(mission_id, "GRAPHENE_MISSION_ID", limit=128)
    read_token = _required(read_token, "GRAPHENE_MISSION_CONTROL_READ_TOKEN", limit=512)
    if _READ_TOKEN.fullmatch(read_token) is None:
        raise CloudConfigurationError(
            "GRAPHENE_MISSION_CONTROL_READ_TOKEN must be 16-256 URL-safe characters"
        )
    if _PROJECT_ID.fullmatch(project_id) is None:
        raise CloudConfigurationError("GOOGLE_CLOUD_PROJECT is not a valid project ID")
    if "/" in database_id or any(character.isspace() for character in database_id):
        raise CloudConfigurationError(
            "GRAPHENE_FIRESTORE_DATABASE is not a valid database ID"
        )
    if _NAMESPACE.fullmatch(namespace) is None:
        raise CloudConfigurationError(
            "GRAPHENE_FIRESTORE_NAMESPACE is not a valid namespace"
        )
    try:
        MissionHead(mission_id=mission_id, seq=0, event_sha256=None, event_count=0)
    except ValueError as error:
        raise CloudConfigurationError(
            "GRAPHENE_MISSION_ID is not a valid mission identifier"
        ) from error

    if store is None:
        if os.environ.get("FIRESTORE_EMULATOR_HOST"):
            raise CloudConfigurationError(
                "FIRESTORE_EMULATOR_HOST is not allowed in the Cloud Run entrypoint"
            )
        client = firestore.Client(project=project_id, database=database_id)
        store = FirestoreMissionStore(client, namespace=namespace)

    app = create_mission_control_app(
        MissionProjection(store),
        mission_id,
        read_token,
        "CLOUD CONTROL PLANE — READ ONLY",
        replay=False,
        truth_label="CLOUD PATH NOT PROVEN — COMMITTED FIRESTORE PROJECTION",
        stream_interval_seconds=CLOUD_STREAM_INTERVAL_SECONDS,
    )

    @app.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
    async def healthz(request: Request) -> Response:
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(
                {
                    "status": "configured",
                    "read_only": True,
                    "repository_execution": False,
                    "cloud_proof": CLOUD_PROOF,
                    "readiness": CLOUD_PROOF,
                }
            )
        )
        return Response(body, media_type="application/json")

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(f"/mission-control/{mission_id}", status_code=307)

    app.state.cloud_configuration = {
        "project_id": project_id,
        "database_id": database_id,
        "namespace": namespace,
        "mission_id": mission_id,
        "cloud_proof": CLOUD_PROOF,
        "stream_interval_seconds": CLOUD_STREAM_INTERVAL_SECONDS,
    }
    return app


def create_cloud_coordinator_app(
    *,
    verify_identity: IdentityVerifier | None = None,
    project_id: str | None = None,
    database_id: str | None = None,
    namespace: str | None = None,
    store: Any | None = None,
) -> FastAPI:
    """Build the private multi-mission coordinator with an explicit verifier.

    Deployment remains opt-in and NOT PROVEN. There is no permissive identity
    fallback and no repository executor in this process.
    """

    project_id = _required(project_id, "GOOGLE_CLOUD_PROJECT", limit=128)
    database_id = _required(database_id, "GRAPHENE_FIRESTORE_DATABASE", limit=128)
    namespace = _required(namespace, "GRAPHENE_FIRESTORE_NAMESPACE", limit=32)
    if verify_identity is None:
        raise CloudConfigurationError(
            "a server-side coordinator identity verifier must be configured"
        )
    if _PROJECT_ID.fullmatch(project_id) is None:
        raise CloudConfigurationError("GOOGLE_CLOUD_PROJECT is not a valid project ID")
    if "/" in database_id or any(character.isspace() for character in database_id):
        raise CloudConfigurationError(
            "GRAPHENE_FIRESTORE_DATABASE is not a valid database ID"
        )
    if _NAMESPACE.fullmatch(namespace) is None:
        raise CloudConfigurationError(
            "GRAPHENE_FIRESTORE_NAMESPACE is not a valid namespace"
        )
    if store is None:
        if os.environ.get("FIRESTORE_EMULATOR_HOST"):
            raise CloudConfigurationError(
                "FIRESTORE_EMULATOR_HOST is not allowed in the Cloud Run entrypoint"
            )
        store = FirestoreMissionStore(
            firestore.Client(project=project_id, database=database_id),
            namespace=namespace,
        )
    app = create_coordinator_app(store, verify_identity)

    @app.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
    async def coordinator_healthz(request: Request) -> Response:
        body = (
            b""
            if request.method == "HEAD"
            else canonical_json_bytes(
                {
                    "cloud_proof": CLOUD_PROOF,
                    "multi_mission": True,
                    "repository_execution": False,
                    "status": "configured",
                }
            )
        )
        return Response(
            body,
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    app.state.cloud_configuration = {
        "project_id": project_id,
        "database_id": database_id,
        "namespace": namespace,
        "multi_mission": True,
        "cloud_proof": CLOUD_PROOF,
    }
    return app


def create_private_coordinator_app(
    *,
    project_id: str | None = None,
    database_id: str | None = None,
    namespace: str | None = None,
    audience: str | None = None,
    executor_bindings_json: str | None = None,
    store: Any | None = None,
) -> FastAPI:
    """Production factory for the private Google-authenticated coordinator.

    This is an explicit, fail-closed entrypoint suitable for ``uvicorn --factory``.
    It configures an application process only; it does not prove a deployment.
    """

    audience = _required(
        audience, "GRAPHENE_COORDINATOR_AUDIENCE", limit=512
    )
    executor_bindings_json = _required(
        executor_bindings_json,
        "GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS",
        limit=_MAX_EXECUTOR_BINDINGS_BYTES,
    )
    try:
        executor_bindings = json.loads(executor_bindings_json)
    except (json.JSONDecodeError, TypeError) as error:
        raise CloudConfigurationError(
            "GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS must be a JSON object"
        ) from error
    if not isinstance(executor_bindings, dict) or not all(
        isinstance(subject, str) and isinstance(executor_id, str)
        for subject, executor_id in executor_bindings.items()
    ):
        raise CloudConfigurationError(
            "GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS must be a JSON object"
        )
    try:
        verifier = GoogleOidcExecutorVerifier(audience, executor_bindings)
    except ValueError as error:
        raise CloudConfigurationError(
            "private coordinator identity configuration is invalid"
        ) from error
    app = create_cloud_coordinator_app(
        verify_identity=verifier,
        project_id=project_id,
        database_id=database_id,
        namespace=namespace,
        store=store,
    )
    app.state.cloud_configuration["identity_provider"] = "google_oidc"
    return app


__all__ = [
    "CLOUD_PROOF",
    "CLOUD_STREAM_INTERVAL_SECONDS",
    "CloudConfigurationError",
    "create_cloud_app",
    "create_cloud_coordinator_app",
    "create_private_coordinator_app",
]
