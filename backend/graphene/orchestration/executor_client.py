from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep as _sleep
from typing import Protocol
from urllib.parse import urlparse

import google.auth
from google.auth import exceptions, impersonated_credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from pydantic import BaseModel

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from .cloud_protocol import (
    ArtifactFetchCapability,
    ArtifactFetchRequest,
    ClaimRequest,
    CompleteRequest,
    CoordinatorError,
    CoordinatorResult,
    DispatchOutboxRecord,
    ExecutorArtifactObservation,
    HeartbeatRequest,
    RegisterExecutorRequest,
)
from .evidence import TrustedCheckReceipt
from .mission_models import AttemptResult, EvidenceReference, MissionHead, TaskKind


class AudienceTokenProvider(Protocol):
    def __call__(self, audience: str) -> str: ...


class GoogleAdcAudienceTokenProvider:
    """Mint a fresh Google-signed audience token from ADC for each request."""

    def __init__(self, *, fetch_token: Callable[..., str] = id_token.fetch_id_token):
        self._fetch_token = fetch_token

    def __call__(self, audience: str) -> str:
        parsed = urlparse(audience)
        if (
            len(audience) > 512
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("audience must be an HTTPS service origin")
        request = GoogleAuthRequest()
        try:
            token = self._fetch_token(request, audience)
        except exceptions.DefaultCredentialsError:
            source, _project = google.auth.default()
            if not isinstance(source, impersonated_credentials.Credentials):
                raise
            credentials = impersonated_credentials.IDTokenCredentials(
                source,
                target_audience=audience,
                include_email=True,
            )
            credentials.refresh(request)
            token = credentials.token
        if not isinstance(token, str) or not token or len(token) > 8_192:
            raise RuntimeError("Google ADC did not return a bounded identity token")
        return token


class CoordinatorClientError(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


Transport = Callable[[str, bytes, dict[str, str], float], tuple[int, bytes]]


@dataclass(frozen=True)
class ExecutorCompletion:
    result: AttemptResult
    artifacts: tuple[ExecutorArtifactObservation, ...] = ()
    check_receipt: TrustedCheckReceipt | None = None


@dataclass(frozen=True)
class ExecutorConnectionSummary:
    executor_id: str
    session_id: str
    head: MissionHead
    claimed: int
    completed: int


class DispatchExecutor(Protocol):
    def __call__(
        self,
        dispatch: DispatchOutboxRecord,
        heartbeat: Callable[[], DispatchOutboxRecord],
        fetch_artifact: Callable[[EvidenceReference], bytes],
    ) -> ExecutorCompletion: ...


def _urllib_transport(
    url: str, body: bytes, headers: dict[str, str], timeout: float
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(1_048_577)
    except urllib.error.HTTPError as error:
        return error.code, error.read(1_048_577)


class CoordinatorClient:
    """Small outbound client; the token provider supplies a fresh audience token."""

    def __init__(
        self,
        coordinator_url: str,
        audience: str,
        token_provider: AudienceTokenProvider,
        *,
        timeout_seconds: float = 15,
        transport: Transport = _urllib_transport,
    ) -> None:
        parsed = urlparse(coordinator_url)
        audience_url = urlparse(audience)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or len(audience) > 512
            or audience_url.scheme != "https"
            or not audience_url.netloc
            or audience_url.username is not None
            or audience_url.password is not None
            or audience_url.path not in {"", "/"}
            or audience_url.query
            or audience_url.fragment
            or parsed.netloc != audience_url.netloc
        ):
            raise ValueError(
                "coordinator_url and audience must share one exact HTTPS origin"
            )
        if not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between zero and 60")
        self._base = coordinator_url.rstrip("/")
        self._audience = audience
        self._token_provider = token_provider
        self._timeout = timeout_seconds
        self._transport = transport

    def _send(self, path: str, request: BaseModel) -> tuple[int, bytes]:
        if (
            not path.startswith("/v1/")
            or "?" in path
            or "#" in path
            or ".." in path.split("/")
        ):
            raise ValueError("coordinator path must be a bounded v1 path")
        try:
            token = self._token_provider(self._audience)
        except Exception as error:
            raise CoordinatorClientError("TOKEN_UNAVAILABLE", 0) from error
        if not isinstance(token, str) or not token or len(token) > 8_192:
            raise CoordinatorClientError("TOKEN_UNAVAILABLE", 0)
        return self._transport(
            self._base + path,
            canonical_json_bytes(request.model_dump(mode="json")),
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            self._timeout,
        )

    @staticmethod
    def _error(status: int, response: bytes) -> CoordinatorClientError:
        try:
            code = CoordinatorError.model_validate_json(response).code
        except ValueError:
            code = "COORDINATOR_REQUEST_FAILED"
        return CoordinatorClientError(code, status)

    def post(self, path: str, request: BaseModel) -> CoordinatorResult:
        status, response = self._send(path, request)
        if len(response) > 65_536:
            raise CoordinatorClientError("RESPONSE_TOO_LARGE", status)
        if 200 <= status < 300:
            return CoordinatorResult.model_validate_json(response)
        raise self._error(status, response)

    def fetch_artifact(
        self,
        capability: ArtifactFetchCapability,
        expected_head: MissionHead,
        *,
        session_id: str,
        worker_id: str,
    ) -> bytes:
        """Redeem one exact capability and verify the returned artifact digest."""

        if (
            capability.mission_id != expected_head.mission_id
            or capability.session_id != session_id
            or capability.worker_id != worker_id
        ):
            raise ValueError("artifact capability is outside the executor scope")
        request = ArtifactFetchRequest(
            command_id=_command(
                "fetch_artifact",
                capability.capability_id,
                capability.token,
                session_id,
                worker_id,
            ),
            expected_head=expected_head,
            session_id=session_id,
            worker_id=worker_id,
            token=capability.token,
        )
        status, response = self._send(
            f"/v1/missions/{capability.mission_id}/artifacts/"
            f"{capability.capability_id}:fetch",
            request,
        )
        if not 200 <= status < 300:
            raise self._error(status, response)
        if len(response) > 1_048_576:
            raise CoordinatorClientError("RESPONSE_TOO_LARGE", status)
        if sha256_hex(response) != capability.reference.sha256:
            raise CoordinatorClientError("ARTIFACT_DIGEST_MISMATCH", status)
        return response


def _command(label: str, *values: object) -> str:
    return f"{label}_{canonical_json_sha256(values)[:32]}"


def _transient(error: CoordinatorClientError) -> bool:
    return error.status_code in {0, 408, 425, 429} or error.status_code >= 500


def _post_with_reconnect(
    client: CoordinatorClient,
    path: str,
    request: BaseModel,
    *,
    max_reconnect_attempts: int,
    sleep: Callable[[float], object],
) -> CoordinatorResult:
    for attempt in range(max_reconnect_attempts + 1):
        try:
            return client.post(path, request)
        except CoordinatorClientError as error:
            if not _transient(error) or attempt == max_reconnect_attempts:
                raise
        except OSError:
            if attempt == max_reconnect_attempts:
                raise
        sleep(min(2**attempt, 10))
    raise AssertionError("bounded reconnect loop did not return")


def connect_executor(
    client: CoordinatorClient,
    *,
    mission_id: str,
    expected_head: MissionHead,
    session_id: str,
    worker_id: str,
    capabilities: tuple[TaskKind, ...],
    execute: DispatchExecutor,
    should_stop: Callable[[], bool],
    poll_interval_seconds: float = 2,
    max_reconnect_attempts: int = 3,
    sleep: Callable[[float], object] = _sleep,
) -> ExecutorConnectionSummary:
    """Register and run one owner-scoped executor connection until shutdown.

    Every reconnect retries the same idempotency key. A caller should implement
    ``should_stop`` with a signal-safe event and may pass ``event.wait`` as sleep.
    Shutdown or failure never abandons a claimed dispatch: abandon is
    unsupported in this release, so the claimed lease expires on its TTL.
    """

    if expected_head.mission_id != mission_id:
        raise ValueError("expected head belongs to another mission")
    if not callable(execute) or not callable(should_stop) or not callable(sleep):
        raise TypeError("executor callbacks must be callable")
    if not 0 <= poll_interval_seconds <= 60:
        raise ValueError("poll interval must be between zero and 60 seconds")
    if (
        type(max_reconnect_attempts) is not int
        or not 0 <= max_reconnect_attempts <= 10
    ):
        raise ValueError("max reconnect attempts must be between zero and 10")

    register = RegisterExecutorRequest(
        command_id=_command(
            "register_executor",
            mission_id,
            session_id,
            worker_id,
            expected_head.seq,
            capabilities,
        ),
        expected_head=expected_head,
        session_id=session_id,
        worker_ids=(worker_id,),
        capabilities=capabilities,
    )
    mission_path = f"/v1/missions/{mission_id}"
    registered = _post_with_reconnect(
        client,
        mission_path + "/executor-sessions",
        register,
        max_reconnect_attempts=max_reconnect_attempts,
        sleep=sleep,
    )
    if (
        registered.status != "registered"
        or registered.session is None
        or registered.session.mission_id != mission_id
        or registered.session.session_id != session_id
        or registered.session.worker_ids != (worker_id,)
        or registered.session.capabilities != capabilities
    ):
        raise CoordinatorClientError("INVALID_COORDINATOR_RESPONSE", 200)
    if registered.authoritative_completion is not True:
        raise CoordinatorClientError("DOMAIN_TRANSITION_UNAVAILABLE", 409)
    executor_id = registered.session.executor_id
    head = registered.head
    claimed = 0
    completed = 0
    claim_number = 0

    def summary() -> ExecutorConnectionSummary:
        return ExecutorConnectionSummary(
            executor_id=executor_id,
            session_id=session_id,
            head=head,
            claimed=claimed,
            completed=completed,
        )

    while not should_stop():
        claim = ClaimRequest(
            command_id=_command(
                "claim_dispatch", mission_id, session_id, worker_id, claim_number
            ),
            expected_head=head,
            session_id=session_id,
            worker_id=worker_id,
        )
        claimed_result = _post_with_reconnect(
            client,
            mission_path + "/claims",
            claim,
            max_reconnect_attempts=max_reconnect_attempts,
            sleep=sleep,
        )
        head = claimed_result.head
        claim_number += 1
        dispatch = claimed_result.dispatch
        if claimed_result.status == "no_work" and dispatch is None:
            if not should_stop():
                sleep(poll_interval_seconds)
            continue
        if (
            claimed_result.status != "delivered"
            or dispatch is None
            or dispatch.mission_id != mission_id
            or dispatch.session_id != session_id
            or dispatch.worker_id != worker_id
            or dispatch.executor_id != executor_id
            or dispatch.task_kind not in capabilities
        ):
            raise CoordinatorClientError("INVALID_COORDINATOR_RESPONSE", 200)
        received_capabilities = claimed_result.artifact_capabilities
        capability_by_reference = {
            (
                capability.reference.kind,
                capability.reference.id,
                capability.reference.sha256,
            ): capability
            for capability in received_capabilities
        }
        accepted_keys = {
            (reference.kind, reference.id, reference.sha256)
            for reference in dispatch.accepted_inputs
        }
        executor_local_inputs = (
            dispatch.artifact_executor_id == executor_id
            and not received_capabilities
        )
        if (
            len(capability_by_reference) != len(received_capabilities)
            or (
                not executor_local_inputs
                and set(capability_by_reference) != accepted_keys
            )
            or any(
                capability.mission_id != dispatch.mission_id
                or capability.dispatch_sha256 != dispatch.dispatch_sha256
                or capability.delivery_count != dispatch.delivery_count
                or capability.attempt_id != dispatch.attempt_id
                or capability.executor_id != dispatch.executor_id
                or capability.session_id != dispatch.session_id
                or capability.worker_id != dispatch.worker_id
                or capability.lease_id != dispatch.lease.lease_id
                or capability.fencing_token != dispatch.lease.fencing_token
                for capability in received_capabilities
            )
        ):
            raise CoordinatorClientError("INVALID_COORDINATOR_RESPONSE", 200)
        claimed += 1
        attempt_path = mission_path + f"/attempts/{dispatch.attempt_id}"
        heartbeat_number = 0

        def heartbeat() -> DispatchOutboxRecord:
            nonlocal head, heartbeat_number
            request = HeartbeatRequest(
                command_id=_command(
                    "heartbeat_dispatch",
                    dispatch.dispatch_sha256,
                    heartbeat_number,
                ),
                expected_head=head,
                session_id=session_id,
                worker_id=worker_id,
                lease_id=dispatch.lease.lease_id,
                fencing_token=dispatch.lease.fencing_token,
            )
            result = _post_with_reconnect(
                client,
                attempt_path + ":heartbeat",
                request,
                max_reconnect_attempts=max_reconnect_attempts,
                sleep=sleep,
            )
            if result.status != "heartbeat" or result.dispatch is None:
                raise CoordinatorClientError("INVALID_COORDINATOR_RESPONSE", 200)
            head = result.head
            heartbeat_number += 1
            return result.dispatch

        def fetch_artifact(reference: EvidenceReference) -> bytes:
            key = (reference.kind, reference.id, reference.sha256)
            capability = capability_by_reference.get(key)
            if capability is None:
                raise CoordinatorClientError("ARTIFACT_CAPABILITY_UNAVAILABLE", 409)
            return client.fetch_artifact(
                capability,
                head,
                session_id=session_id,
                worker_id=worker_id,
            )

        if should_stop():
            # §6.4: abandon is unsupported in this release; shut down without
            # it and let the claimed lease expire on its TTL.
            return summary()
        completion = execute(dispatch, heartbeat, fetch_artifact)
        if not isinstance(completion, ExecutorCompletion):
            raise TypeError("execute must return ExecutorCompletion")

        complete = CompleteRequest(
            command_id=_command(
                "complete_dispatch",
                dispatch.dispatch_sha256,
                completion.result.model_dump(mode="json"),
            ),
            expected_head=head,
            session_id=session_id,
            worker_id=worker_id,
            lease_id=dispatch.lease.lease_id,
            fencing_token=dispatch.lease.fencing_token,
            result=completion.result,
            artifacts=completion.artifacts,
            check_receipt=completion.check_receipt,
        )
        completed_result = _post_with_reconnect(
            client,
            attempt_path + ":complete",
            complete,
            max_reconnect_attempts=max_reconnect_attempts,
            sleep=sleep,
        )
        if completed_result.status != "completed":
            raise CoordinatorClientError("INVALID_COORDINATOR_RESPONSE", 200)
        head = completed_result.head
        completed += 1

    return summary()


__all__ = [
    "AudienceTokenProvider",
    "DispatchExecutor",
    "CoordinatorClient",
    "CoordinatorClientError",
    "ExecutorCompletion",
    "ExecutorConnectionSummary",
    "GoogleAdcAudienceTokenProvider",
    "connect_executor",
]
