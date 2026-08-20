from __future__ import annotations

import asyncio
import hmac
import inspect
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from .cloud_protocol import (
    AbandonRequest,
    ArtifactFetchCapability,
    ArtifactFetchGrant,
    ArtifactFetchRequest,
    AuthenticatedExecutor,
    ClaimRequest,
    CompleteRequest,
    CoordinatorResult,
    HeartbeatRequest,
    RegisterExecutorRequest,
)
from .firestore import (
    ArtifactCapabilityRejected,
    ArtifactLocalityUnavailable,
    DispatchStateRejected,
    DomainTransitionUnavailable,
    ExecutorSessionRejected,
    LeaseFenceRejected,
    MissionConflict,
    MissionNotFound,
    MissionStateInvalid,
)

_MAX_REQUEST_BYTES = 65_536
_MAX_ARTIFACT_BYTES = 1_048_576


class CoordinatorStore(Protocol):
    def head(self, mission_id: str) -> Any: ...

    def register_executor_session(self, *args: Any, **kwargs: Any) -> Any: ...

    def claim_dispatch(self, *args: Any, **kwargs: Any) -> Any: ...

    def heartbeat_dispatch(self, *args: Any, **kwargs: Any) -> Any: ...

    def complete_dispatch(self, *args: Any, **kwargs: Any) -> Any: ...

    def abandon_dispatch(self, *args: Any, **kwargs: Any) -> Any: ...

    def grant_artifact_fetch(self, *args: Any, **kwargs: Any) -> Any: ...

    def redeem_artifact_fetch(self, *args: Any, **kwargs: Any) -> Any: ...


IdentityVerifier = Callable[
    [Request], AuthenticatedExecutor | Awaitable[AuthenticatedExecutor]
]
ArtifactResolver = Callable[[str, str], bytes | None]


def _error(code: str, detail: str, status_code: int) -> Response:
    return Response(
        canonical_json_bytes({"code": code, "detail": detail}),
        status_code=status_code,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def create_coordinator_app(
    store: CoordinatorStore,
    verify_identity: IdentityVerifier,
    *,
    artifact_resolver: ArtifactResolver | None = None,
    artifact_capability_key: bytes | None = None,
) -> FastAPI:
    """Create a private multi-mission transport coordinator.

    The verifier is the only source of executor identity. Request bodies never carry
    an executor_id or principal claim.
    """

    if not callable(verify_identity):
        raise TypeError("verify_identity must be callable")
    if (artifact_resolver is None) != (artifact_capability_key is None):
        raise ValueError("artifact resolver and capability key must be configured together")
    if artifact_resolver is not None and not callable(artifact_resolver):
        raise TypeError("artifact_resolver must be callable")
    if artifact_capability_key is not None and (
        not isinstance(artifact_capability_key, bytes)
        or len(artifact_capability_key) < 32
    ):
        raise ValueError("artifact capability key must contain at least 32 bytes")
    app = FastAPI(
        title="Graphene Private Coordinator",
        version="1",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    @app.middleware("http")
    async def bounded_no_store(request: Request, call_next):
        if request.url.path.startswith("/v1/"):
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > _MAX_REQUEST_BYTES:
                        return _error(
                            "REQUEST_TOO_LARGE",
                            "Coordinator request exceeds the body limit.",
                            413,
                        )
                except ValueError:
                    return _error(
                        "INVALID_REQUEST",
                        "Coordinator request metadata is invalid.",
                        400,
                    )
            if len(await request.body()) > _MAX_REQUEST_BYTES:
                return _error(
                    "REQUEST_TOO_LARGE",
                    "Coordinator request exceeds the body limit.",
                    413,
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    async def authenticated(request: Request) -> AuthenticatedExecutor:
        try:
            if inspect.iscoroutinefunction(verify_identity):
                value = verify_identity(request)
            else:
                value = await asyncio.to_thread(verify_identity, request)
            if inspect.isawaitable(value):
                value = await value
            return AuthenticatedExecutor.model_validate(value)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=401, detail="Coordinator authentication required"
            ) from error

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error_value: RequestValidationError):
        return _error(
            "INVALID_REQUEST", "Coordinator request validation failed.", 422
        )

    @app.exception_handler(MissionNotFound)
    async def mission_not_found(_request: Request, _error_value: MissionNotFound):
        return _error("MISSION_NOT_FOUND", "Mission is unavailable.", 404)

    @app.exception_handler(LeaseFenceRejected)
    async def stale_fence(_request: Request, _error_value: LeaseFenceRejected):
        return _error("STALE_FENCE", "Lease or fencing token is stale.", 409)

    @app.exception_handler(ArtifactLocalityUnavailable)
    async def locality(
        _request: Request, _error_value: ArtifactLocalityUnavailable
    ):
        return _error(
            "ARTIFACT_LOCALITY_UNAVAILABLE",
            "Required artifacts are unavailable from their owning executor.",
            409,
        )

    @app.exception_handler(ArtifactCapabilityRejected)
    async def artifact_capability_rejected(
        _request: Request, _error_value: ArtifactCapabilityRejected
    ):
        return _error(
            "ARTIFACT_CAPABILITY_REJECTED",
            "Artifact capability is unavailable or outside its scope.",
            403,
        )

    @app.exception_handler(ExecutorSessionRejected)
    async def session_rejected(
        _request: Request, _error_value: ExecutorSessionRejected
    ):
        return _error(
            "EXECUTOR_SESSION_REJECTED", "Executor session is unavailable.", 403
        )

    @app.exception_handler(DispatchStateRejected)
    async def dispatch_rejected(
        _request: Request, _error_value: DispatchStateRejected
    ):
        return _error(
            "DISPATCH_STATE_CONFLICT", "Dispatch state rejected the request.", 409
        )

    @app.exception_handler(DomainTransitionUnavailable)
    async def domain_transition_unavailable(
        _request: Request, _error_value: DomainTransitionUnavailable
    ):
        return _error(
            "DOMAIN_TRANSITION_UNAVAILABLE",
            "Authoritative mission completion is unavailable.",
            409,
        )

    async def mission_conflict(_request: Request, _error_value: Exception):
        return _error(
            "MISSION_STATE_CONFLICT", "Committed mission state rejected the request.", 409
        )

    app.add_exception_handler(MissionConflict, mission_conflict)
    app.add_exception_handler(MissionStateInvalid, mission_conflict)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException):
        if error.status_code in {401, 403}:
            return _error(
                "AUTHENTICATION_REQUIRED",
                "Coordinator authentication required.",
                error.status_code,
            )
        return _error("REQUEST_REJECTED", "Coordinator request was rejected.", error.status_code)

    @app.exception_handler(Exception)
    async def unavailable(_request: Request, _error_value: Exception):
        return _error(
            "COORDINATOR_UNAVAILABLE", "Coordinator is temporarily unavailable.", 503
        )

    def require_path_head(mission_id: str, body: Any) -> None:
        if body.expected_head.mission_id != mission_id:
            raise MissionConflict("expected head belongs to another mission")

    def capability_for(
        dispatch: Any, reference: Any
    ) -> tuple[ArtifactFetchCapability, ArtifactFetchGrant]:
        if artifact_capability_key is None:
            raise ArtifactLocalityUnavailable("artifact fetch is not configured")
        assert dispatch.last_delivery_at is not None
        issued_at = dispatch.last_delivery_at
        expires_at = min(dispatch.lease.expires_at, issued_at + timedelta(minutes=5))
        capability_id = "artifact_cap_" + canonical_json_sha256(
            {
                "delivery_count": dispatch.delivery_count,
                "dispatch_sha256": dispatch.dispatch_sha256,
                "reference": reference.model_dump(mode="json"),
            }
        )[:32]
        scope = {
            "capability_id": capability_id,
            "mission_id": dispatch.mission_id,
            "dispatch_sha256": dispatch.dispatch_sha256,
            "delivery_count": dispatch.delivery_count,
            "attempt_id": dispatch.attempt_id,
            "executor_id": dispatch.executor_id,
            "session_id": dispatch.session_id,
            "worker_id": dispatch.worker_id,
            "lease_id": dispatch.lease.lease_id,
            "fencing_token": dispatch.lease.fencing_token,
            "reference": reference,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
        token = hmac.new(
            artifact_capability_key,
            canonical_json_bytes(
                ArtifactFetchGrant(
                    **scope,
                    token_sha256="0" * 64,
                ).model_dump(
                    mode="json",
                    exclude={
                        "token_sha256",
                        "consumed_at",
                        "consumed_command_id",
                    },
                )
            ),
            "sha256",
        ).hexdigest()
        capability = ArtifactFetchCapability(**scope, token=token)
        grant = ArtifactFetchGrant(
            **scope,
            token_sha256=sha256_hex(token.encode()),
        )
        return capability, grant

    @app.post(
        "/v1/missions/{mission_id}/executor-sessions",
        response_model=CoordinatorResult,
    )
    async def register_executor(
        mission_id: str,
        body: RegisterExecutorRequest,
        identity: AuthenticatedExecutor = Depends(authenticated),
    ) -> CoordinatorResult:
        require_path_head(mission_id, body)
        session = await asyncio.to_thread(
            store.register_executor_session,
            mission_id,
            body.expected_head,
            body.command_id,
            principal=identity.principal,
            executor_id=identity.executor_id,
            session_id=body.session_id,
            worker_ids=body.worker_ids,
            capabilities=body.capabilities,
        )
        return CoordinatorResult(
            mission_id=mission_id,
            head=body.expected_head,
            authoritative_completion=True,
            session=session,
            status="registered",
        )

    @app.post("/v1/missions/{mission_id}/claims", response_model=CoordinatorResult)
    async def claim(
        mission_id: str,
        body: ClaimRequest,
        identity: AuthenticatedExecutor = Depends(authenticated),
    ) -> CoordinatorResult:
        require_path_head(mission_id, body)
        dispatch = await asyncio.to_thread(
            store.claim_dispatch,
            mission_id,
            body.expected_head,
            body.command_id,
            executor_id=identity.executor_id,
            session_id=body.session_id,
            worker_id=body.worker_id,
        )
        head = await asyncio.to_thread(store.head, mission_id)
        artifact_capabilities: list[ArtifactFetchCapability] = []
        if dispatch is not None:
            for reference in (
                dispatch.accepted_inputs if artifact_resolver is not None else ()
            ):
                capability, grant = capability_for(dispatch, reference)
                await asyncio.to_thread(
                    store.grant_artifact_fetch,
                    grant,
                    head,
                )
                artifact_capabilities.append(capability)
        return CoordinatorResult(
            mission_id=mission_id,
            head=head,
            artifact_capabilities=tuple(artifact_capabilities),
            dispatch=dispatch,
            status="delivered" if dispatch is not None else "no_work",
        )

    @app.post(
        "/v1/missions/{mission_id}/artifacts/{capability_id}:fetch",
        response_class=Response,
    )
    async def fetch_artifact(
        mission_id: str,
        capability_id: str,
        body: ArtifactFetchRequest,
        identity: AuthenticatedExecutor = Depends(authenticated),
    ) -> Response:
        require_path_head(mission_id, body)
        if artifact_resolver is None:
            raise ArtifactLocalityUnavailable("artifact fetch is not configured")
        grant = await asyncio.to_thread(
            store.redeem_artifact_fetch,
            mission_id,
            capability_id,
            body.expected_head,
            body.command_id,
            executor_id=identity.executor_id,
            session_id=body.session_id,
            worker_id=body.worker_id,
            token_sha256=sha256_hex(body.token.encode()),
        )
        raw = await asyncio.to_thread(
            artifact_resolver, grant.reference.kind, grant.reference.id
        )
        if (
            not isinstance(raw, bytes)
            or len(raw) > _MAX_ARTIFACT_BYTES
            or sha256_hex(raw) != grant.reference.sha256
        ):
            raise ArtifactLocalityUnavailable("artifact bytes failed digest validation")
        return Response(
            raw,
            media_type="application/octet-stream",
            headers={"X-Artifact-SHA256": grant.reference.sha256},
        )

    @app.post(
        "/v1/missions/{mission_id}/attempts/{attempt_id}:heartbeat",
        response_model=CoordinatorResult,
    )
    async def heartbeat(
        mission_id: str,
        attempt_id: str,
        body: HeartbeatRequest,
        identity: AuthenticatedExecutor = Depends(authenticated),
    ) -> CoordinatorResult:
        require_path_head(mission_id, body)
        dispatch = await asyncio.to_thread(
            store.heartbeat_dispatch,
            mission_id,
            attempt_id,
            body.expected_head,
            body.command_id,
            executor_id=identity.executor_id,
            session_id=body.session_id,
            worker_id=body.worker_id,
            lease_id=body.lease_id,
            fencing_token=body.fencing_token,
        )
        head = await asyncio.to_thread(store.head, mission_id)
        return CoordinatorResult(
            mission_id=mission_id,
            head=head,
            dispatch=dispatch,
            status="heartbeat",
        )

    @app.post(
        "/v1/missions/{mission_id}/attempts/{attempt_id}:complete",
        response_model=CoordinatorResult,
    )
    async def complete(
        mission_id: str,
        attempt_id: str,
        body: CompleteRequest,
        identity: AuthenticatedExecutor = Depends(authenticated),
    ) -> CoordinatorResult:
        require_path_head(mission_id, body)
        dispatch = await asyncio.to_thread(
            store.complete_dispatch,
            mission_id,
            attempt_id,
            body.expected_head,
            body.command_id,
            executor_id=identity.executor_id,
            session_id=body.session_id,
            worker_id=body.worker_id,
            lease_id=body.lease_id,
            fencing_token=body.fencing_token,
            result=body.result,
            artifacts=body.artifacts,
            check_receipt=body.check_receipt,
        )
        head = await asyncio.to_thread(store.head, mission_id)
        return CoordinatorResult(
            mission_id=mission_id,
            head=head,
            authoritative_completion=True,
            dispatch=dispatch,
            status="completed",
        )

    @app.post(
        "/v1/missions/{mission_id}/attempts/{attempt_id}:abandon",
        response_model=CoordinatorResult,
    )
    async def abandon(
        mission_id: str,
        attempt_id: str,
        body: AbandonRequest,
        identity: AuthenticatedExecutor = Depends(authenticated),
    ) -> CoordinatorResult:
        require_path_head(mission_id, body)
        dispatch = await asyncio.to_thread(
            store.abandon_dispatch,
            mission_id,
            attempt_id,
            body.expected_head,
            body.command_id,
            executor_id=identity.executor_id,
            session_id=body.session_id,
            worker_id=body.worker_id,
            lease_id=body.lease_id,
            fencing_token=body.fencing_token,
            result_code=body.reason_code,
        )
        return CoordinatorResult(
            mission_id=mission_id,
            head=body.expected_head,
            dispatch=dispatch,
            status="abandoned",
        )

    return app


__all__ = ["CoordinatorStore", "IdentityVerifier", "create_coordinator_app"]
