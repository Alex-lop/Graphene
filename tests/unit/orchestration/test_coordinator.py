from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from graphene.artifact_envelope import ArtifactEnvelopeV2
from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.orchestration.cloud_protocol import (
    ArtifactFetchCapability,
    ArtifactFetchGrant,
    AuthenticatedExecutor,
    ClaimRequest,
    CoordinatorResult,
    DispatchOutboxRecord,
    DispatchOutboxState,
    DispatchTransition,
    ExecutorArtifactObservation,
    ExecutorArtifactReference,
    ExecutorSession,
    RegisterExecutorRequest,
    new_dispatch_record,
)
from graphene.orchestration.completion import reduce_successful_completion
from graphene.orchestration.coordinator import create_coordinator_app
from graphene.orchestration.evidence import TrustedCheckReceipt
from graphene.orchestration.executor_client import (
    CoordinatorClient,
    CoordinatorClientError,
    ExecutorCompletion,
    GoogleAdcAudienceTokenProvider,
    connect_executor,
)
from graphene.orchestration.firestore_mission_store import (
    DomainTransitionUnavailable,
    FirestoreMissionStore,
    MultiExecutorUnsupported,
)
from graphene.orchestration.mission_models import (
    ArtifactEnvelopeReferenceV2,
    AttemptResult,
    EvidenceReference,
    GenericEvidenceLink,
    Lease,
    MissionEventType,
    MissionHead,
    PublicationDraft,
    TaskKind,
)
from graphene.orchestration.sqlite_mission_store import MissionConflict

from .test_firestore import (
    MISSION_ID as FIRESTORE_MISSION_ID,
    START as FIRESTORE_START,
    Client as FakeFirestoreClient,
    Clock as FirestoreClock,
    cloud_dispatch,
    draft as firestore_draft,
    empty_head as firestore_empty_head,
    fake_transactional,  # noqa: F401  (autouse fixture for FirestoreMissionStore)
    head as firestore_head,
    lease as firestore_lease,
    running_cloud_snapshot,
)


MISSION_ID = "mission_cloud_api_1"
HEAD = MissionHead(
    mission_id=MISSION_ID, seq=1, event_sha256="a" * 64, event_count=1
)
IDENTITY = AuthenticatedExecutor(
    principal="principal@example.invalid", executor_id="executor_server_bound"
)


def failed_result() -> AttemptResult:
    return AttemptResult(
        succeeded=False,
        result_code="provider_unavailable",
        session_id="session_cloud_api_1",
        invocation_id="invocation_cloud_api_1",
    )


def test_google_adc_provider_mints_a_fresh_audience_token_per_call():
    calls = []

    def fetch(request, audience):
        calls.append((request, audience))
        return f"token-{len(calls)}"

    provider = GoogleAdcAudienceTokenProvider(fetch_token=fetch)
    assert provider("https://coordinator.example.run.app") == "token-1"
    assert provider("https://coordinator.example.run.app") == "token-2"
    assert calls[0][0] is not calls[1][0]
    assert [item[1] for item in calls] == [
        "https://coordinator.example.run.app",
        "https://coordinator.example.run.app",
    ]

    with pytest.raises(ValueError, match="HTTPS service origin"):
        provider("http://coordinator.invalid")


def delivered_dispatch(*, accepted_inputs=()) -> DispatchOutboxRecord:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    lease = Lease(
        lease_id="lease_cloud_api_1",
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id="task_cloud_api_1",
        attempt_id="attempt_cloud_api_1",
        owner="worker_cloud_api_1",
        fencing_token=1,
        issued_at=now,
        heartbeat_at=now,
        expires_at=datetime(2026, 8, 19, 0, 1, tzinfo=UTC),
    )
    pending = new_dispatch_record(
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id=lease.task_id,
        task_kind=TaskKind.WORK,
        attempt_id=lease.attempt_id,
        attempt_number=1,
        executor_id=IDENTITY.executor_id,
        worker_id=lease.owner,
        session_id="session_cloud_api_1",
        lease=lease,
        accepted_inputs=accepted_inputs,
        artifact_executor_id=IDENTITY.executor_id,
        creation_seq=HEAD.seq,
    )
    return DispatchOutboxRecord.model_validate(
        {
            **pending.model_dump(mode="json"),
            "delivery_count": 1,
            "last_delivery_at": now,
            "state": DispatchOutboxState.DELIVERED,
            "history": (
                *pending.history,
                DispatchTransition(
                    state=DispatchOutboxState.DELIVERED,
                    recorded_at=now,
                    delivery_count=1,
                ),
            ),
        }
    )


class RecorderStore:
    def __init__(self):
        self.calls = []
        self.failure = None

    def _record(self, name, args, values):
        if self.failure is not None:
            raise self.failure
        self.calls.append((name, args, values))

    def head(self, mission_id):
        if (
            self.calls
            and self.calls[-1][1][0] == mission_id
            and isinstance(self.calls[-1][1][1], MissionHead)
        ):
            return self.calls[-1][1][1]
        assert mission_id == MISSION_ID
        return HEAD

    def register_executor_session(self, *args, **values):
        self._record("register", args, values)
        now = datetime(2026, 8, 19, tzinfo=UTC)
        return ExecutorSession(
            mission_id=args[0],
            session_id=values["session_id"],
            executor_id=values["executor_id"],
            principal=values["principal"],
            worker_ids=values["worker_ids"],
            capabilities=values["capabilities"],
            created_at=now,
            last_seen_at=now,
        )

    def claim_dispatch(self, *args, **values):
        self._record("claim", args, values)
        return None

    def heartbeat_dispatch(self, *args, **values):
        self._record("heartbeat", args, values)
        return None

    def complete_dispatch(self, *args, **values):
        self._record("complete", args, values)
        return None

    def grant_artifact_fetch(self, grant, expected_head):
        self._record("grant_artifact", (grant, expected_head), {})
        self.grant = grant
        return grant

    def redeem_artifact_fetch(self, *args, **values):
        self._record("redeem_artifact", args, values)
        return self.grant


def verifier(request):
    if request.headers.get("authorization") != "Bearer oidc-test-token":
        raise HTTPException(status_code=401)
    return IDENTITY


def body(command_id):
    return {
        "command_id": command_id,
        "expected_head": HEAD.model_dump(mode="json"),
        "session_id": "session_cloud_api_1",
        "worker_id": "worker_cloud_api_1",
    }


def test_coordinator_binds_server_identity_and_exposes_all_transport_actions():
    store = RecorderStore()
    client = TestClient(create_coordinator_app(store, verifier))
    headers = {"Authorization": "Bearer oidc-test-token"}

    register = client.post(
        f"/v1/missions/{MISSION_ID}/executor-sessions",
        headers=headers,
        json={
            "command_id": "command_register_001",
            "expected_head": HEAD.model_dump(mode="json"),
            "session_id": "session_cloud_api_1",
            "worker_ids": ["worker_cloud_api_1"],
            "capabilities": ["work"],
        },
    )
    assert register.status_code == 200
    assert register.json()["session"]["executor_id"] == IDENTITY.executor_id
    assert register.json()["authoritative_completion"] is True
    assert register.headers["cache-control"] == "no-store"
    assert store.calls[-1][2]["executor_id"] == IDENTITY.executor_id
    assert store.calls[-1][2]["principal"] == IDENTITY.principal

    claim = client.post(
        f"/v1/missions/{MISSION_ID}/claims",
        headers=headers,
        json=body("command_claim_api_01"),
    )
    assert claim.status_code == 200
    assert claim.json()["status"] == "no_work"

    attempt_path = f"/v1/missions/{MISSION_ID}/attempts/attempt_cloud_api_1"
    attempt = {
        **body("command_heartbeat_api1"),
        "lease_id": "lease_cloud_api_1",
        "fencing_token": 1,
    }
    assert client.post(attempt_path + ":heartbeat", headers=headers, json=attempt).status_code == 200
    complete = {
        **attempt,
        "command_id": "command_complete_api_1",
        "result": failed_result().model_dump(mode="json"),
    }
    completed = client.post(attempt_path + ":complete", headers=headers, json=complete)
    assert completed.status_code == 200
    assert completed.json()["authoritative_completion"] is True
    abandon = {
        **attempt,
        "command_id": "command_abandon_api_01",
        "reason_code": "provider_unavailable",
    }
    refused = client.post(attempt_path + ":abandon", headers=headers, json=abandon)
    assert refused.status_code == 501
    assert refused.json()["code"] == "ABANDON_UNSUPPORTED"
    assert [item[0] for item in store.calls] == [
        "register",
        "claim",
        "heartbeat",
        "complete",
    ]
    assert all(
        call[2]["executor_id"] == IDENTITY.executor_id for call in store.calls
    )


def test_success_completion_accepts_executor_attested_receipt_and_binds_identity_server_side():
    # The hand-built receipt below carries arbitrary digests ("e"*64, "f"*64,
    # "a"*64) and is accepted by design: cloud check results are
    # executor-attested (completion.py module docstring, directive §6.3).
    store = RecorderStore()
    client = TestClient(create_coordinator_app(store, verifier))
    reference = EvidenceReference(
        kind="patch", id="artifact_cloud_output_1", sha256="b" * 64
    )
    result = AttemptResult(
        succeeded=True,
        result_code="passed",
        session_id="session_cloud_api_1",
        invocation_id="invocation_cloud_api_1",
        evidence_link=GenericEvidenceLink(evidence_id="evidence_cloud_api_1"),
        evidence_refs=(reference,),
    )
    receipt = TrustedCheckReceipt(
        schema_version=2,
        mission_id=MISSION_ID,
        task_id="task_cloud_api_1",
        attempt_id="attempt_cloud_api_1",
        plan_revision=1,
        fencing_token=1,
        policy_sha256="c" * 64,
        base_sha="d" * 40,
        runner_id="graphene_check_runner_v1",
        template_id="check_cloud_api_1",
        template_sha256="e" * 64,
        accepted_input_references=(),
        candidate_references=(reference,),
        candidate_tree_hash_version="graphene.tree.v2",
        candidate_tree_sha256="f" * 64,
        result_code="passed",
        exit_code=0,
        timed_out=False,
        output_sha256="a" * 64,
        output_truncated=False,
        cleanup_complete=True,
    )
    request = {
        **body("command_complete_success_1"),
        "lease_id": "lease_cloud_api_1",
        "fencing_token": 1,
        "result": result.model_dump(mode="json"),
        "artifacts": [
            ExecutorArtifactObservation(
                reference=reference, byte_count=123
            ).model_dump(mode="json")
        ],
        "check_receipt": receipt.model_dump(mode="json"),
    }
    path = f"/v1/missions/{MISSION_ID}/attempts/attempt_cloud_api_1:complete"
    response = client.post(
        path,
        headers={"Authorization": "Bearer oidc-test-token"},
        json=request,
    )

    assert response.status_code == 200
    complete_call = store.calls[-1]
    assert complete_call[0] == "complete"
    assert complete_call[2]["executor_id"] == IDENTITY.executor_id
    assert complete_call[2]["artifacts"] == (
        ExecutorArtifactObservation(reference=reference, byte_count=123),
    )

    request["artifacts"][0]["executor_id"] = "executor_attacker"
    assert client.post(
        path,
        headers={"Authorization": "Bearer oidc-test-token"},
        json=request,
    ).status_code == 422


def test_coordinator_issues_and_redeems_one_digest_bound_artifact_capability():
    raw = b'{"context":"safe"}'
    reference = EvidenceReference(
        kind="context",
        id="artifact_cloud_context_1",
        sha256=sha256_hex(raw),
    )
    store = RecorderStore()
    store.claim_dispatch = lambda *args, **values: delivered_dispatch(
        accepted_inputs=(reference,)
    )
    client = TestClient(
        create_coordinator_app(
            store,
            verifier,
            artifact_resolver=lambda kind, artifact_id: (
                raw
                if (kind, artifact_id) == (reference.kind, reference.id)
                else None
            ),
            artifact_capability_key=b"k" * 32,
        )
    )
    headers = {"Authorization": "Bearer oidc-test-token"}
    claimed = client.post(
        f"/v1/missions/{MISSION_ID}/claims",
        headers=headers,
        json=body("command_claim_artifact_1"),
    )
    assert claimed.status_code == 200
    capability = claimed.json()["artifact_capabilities"][0]
    assert capability["reference"] == reference.model_dump(mode="json")
    assert "token" in capability
    persisted = store.grant.model_dump(mode="json")
    assert isinstance(store.grant, ArtifactFetchGrant)
    assert "token" not in persisted
    fetch_body = {
        **body("command_fetch_artifact_1"),
        "token": capability["token"],
    }
    fetched = client.post(
        f"/v1/missions/{MISSION_ID}/artifacts/"
        f"{capability['capability_id']}:fetch",
        headers=headers,
        json=fetch_body,
    )
    assert fetched.status_code == 200
    assert fetched.content == raw
    assert fetched.headers["x-artifact-sha256"] == reference.sha256
    assert store.calls[-1][2]["token_sha256"] == store.grant.token_sha256


def test_coordinator_rejects_body_identity_oversize_and_raw_errors():
    store = RecorderStore()
    client = TestClient(create_coordinator_app(store, verifier), raise_server_exceptions=False)
    headers = {"Authorization": "Bearer oidc-test-token"}
    injected = {
        **body("command_claim_api_02"),
        "executor_id": "attacker_selected_executor",
    }
    invalid = client.post(
        f"/v1/missions/{MISSION_ID}/claims", headers=headers, json=injected
    )
    assert invalid.status_code == 422
    assert invalid.json() == {
        "code": "INVALID_REQUEST",
        "detail": "Coordinator request validation failed.",
    }
    assert store.calls == []

    unauthenticated = client.post(
        f"/v1/missions/{MISSION_ID}/claims",
        json=body("command_claim_api_03"),
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == "AUTHENTICATION_REQUIRED"

    oversized = client.post(
        f"/v1/missions/{MISSION_ID}/claims",
        headers={**headers, "Content-Type": "application/json"},
        content=b"{" + b" " * 65_536 + b"}",
    )
    assert oversized.status_code == 413

    store.failure = MissionConflict("PRIVATE_PROVIDER_DETAIL_CANARY")
    rejected = client.post(
        f"/v1/missions/{MISSION_ID}/claims",
        headers=headers,
        json=body("command_claim_api_04"),
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "MISSION_STATE_CONFLICT"
    assert "CANARY" not in rejected.text


def test_coordinator_routes_more_than_one_mission_without_factory_state():
    store = RecorderStore()
    client = TestClient(create_coordinator_app(store, verifier))
    headers = {"Authorization": "Bearer oidc-test-token"}
    other_id = "mission_cloud_api_2"
    other_head = MissionHead(
        mission_id=other_id, seq=2, event_sha256="b" * 64, event_count=2
    )
    response = client.post(
        f"/v1/missions/{other_id}/claims",
        headers=headers,
        json={
            **body("command_claim_other_1"),
            "expected_head": other_head.model_dump(mode="json"),
        },
    )
    assert response.status_code == 200
    assert response.json()["mission_id"] == other_id
    assert store.calls[0][1][0] == other_id


def test_coordinator_reports_missing_authoritative_completion_without_details():
    store = RecorderStore()
    store.failure = DomainTransitionUnavailable("PRIVATE_DOMAIN_ENGINE_CANARY")
    client = TestClient(
        create_coordinator_app(store, verifier), raise_server_exceptions=False
    )
    response = client.post(
        f"/v1/missions/{MISSION_ID}/attempts/attempt_cloud_api_1:complete",
        headers={"Authorization": "Bearer oidc-test-token"},
        json={
            **body("command_complete_fail_closed"),
            "lease_id": "lease_cloud_api_1",
            "fencing_token": 1,
            "result": failed_result().model_dump(mode="json"),
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "DOMAIN_TRANSITION_UNAVAILABLE",
        "detail": "Authoritative mission completion is unavailable.",
    }
    assert "CANARY" not in response.text


def test_outbound_client_injects_a_fresh_audience_token_and_reuses_safe_request():
    calls = []
    tokens = []
    request = ClaimRequest.model_validate(body("command_claim_client1"))
    result = CoordinatorResult(
        mission_id=MISSION_ID, head=HEAD, status="no_work"
    ).model_dump_json().encode()

    def token_provider(audience):
        tokens.append(audience)
        return f"token-{len(tokens)}"

    def transport(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return 200, result

    client = CoordinatorClient(
        "https://coordinator.example.invalid",
        "https://coordinator.example.invalid",
        token_provider,
        transport=transport,
    )
    path = f"/v1/missions/{MISSION_ID}/claims"
    assert client.post(path, request).status == "no_work"
    assert client.post(path, request).status == "no_work"
    assert tokens == [
        "https://coordinator.example.invalid",
        "https://coordinator.example.invalid",
    ]
    assert calls[0][2]["Authorization"] == "Bearer token-1"
    assert calls[1][2]["Authorization"] == "Bearer token-2"
    assert calls[0][1] == calls[1][1]

    def rejected(*_args):
        return 409, b'{"code":"STALE_FENCE","detail":"safe"}'

    failing = CoordinatorClient(
        "https://coordinator.example.invalid",
        "https://coordinator.example.invalid",
        token_provider,
        transport=rejected,
    )
    try:
        failing.post(path, request)
    except CoordinatorClientError as error:
        assert (error.code, error.status_code) == ("STALE_FENCE", 409)
    else:
        raise AssertionError("coordinator client accepted a rejected response")


def test_outbound_client_fetches_and_verifies_one_capability():
    raw = b'{"artifact":"verified"}'
    now = datetime(2026, 8, 19, tzinfo=UTC)
    capability = ArtifactFetchCapability(
        capability_id="artifact_cap_0123456789abcdef0123456789abcdef",
        mission_id=MISSION_ID,
        dispatch_sha256="b" * 64,
        delivery_count=1,
        attempt_id="attempt_cloud_api_1",
        executor_id=IDENTITY.executor_id,
        session_id="session_cloud_api_1",
        worker_id="worker_cloud_api_1",
        lease_id="lease_cloud_api_1",
        fencing_token=1,
        reference={
            "kind": "context",
            "id": "artifact_client_context_1",
            "sha256": sha256_hex(raw),
        },
        issued_at=now,
        expires_at=datetime(2026, 8, 19, 0, 1, tzinfo=UTC),
        token="c" * 64,
    )
    payloads = []

    def transport(url, payload, headers, timeout):
        payloads.append((url, payload, headers, timeout))
        return 200, raw

    client = CoordinatorClient(
        "https://coordinator.example.invalid",
        "https://coordinator.example.invalid",
        lambda _audience: "fresh-token",
        transport=transport,
    )
    assert client.fetch_artifact(
        capability,
        HEAD,
        session_id="session_cloud_api_1",
        worker_id="worker_cloud_api_1",
    ) == raw
    assert payloads[0][2]["Authorization"] == "Bearer fresh-token"

    bad = CoordinatorClient(
        "https://coordinator.example.invalid",
        "https://coordinator.example.invalid",
        lambda _audience: "fresh-token",
        transport=lambda *_args: (200, b"corrupt"),
    )
    try:
        bad.fetch_artifact(
            capability,
            HEAD,
            session_id="session_cloud_api_1",
            worker_id="worker_cloud_api_1",
        )
    except CoordinatorClientError as error:
        assert error.code == "ARTIFACT_DIGEST_MISMATCH"
    else:
        raise AssertionError("coordinator client accepted corrupt artifact bytes")


class LoopClient:
    def __init__(
        self,
        *,
        fail_first_claim: bool = False,
        authoritative_completion: bool = True,
    ):
        self.calls = []
        self.fail_first_claim = fail_first_claim
        self.claim_attempts = 0
        self.claim_returned = False
        self.completed = False
        self.abandoned = False
        self.authoritative_completion = authoritative_completion
        self.dispatch = delivered_dispatch()
        now = datetime(2026, 8, 19, tzinfo=UTC)
        self.session = ExecutorSession(
            mission_id=MISSION_ID,
            session_id="session_cloud_api_1",
            executor_id=IDENTITY.executor_id,
            principal=IDENTITY.principal,
            worker_ids=("worker_cloud_api_1",),
            capabilities=(TaskKind.WORK,),
            created_at=now,
            last_seen_at=now,
            queued_attempt_ids=(self.dispatch.attempt_id,),
        )

    def post(self, path, request):
        self.calls.append((path, request))
        if path.endswith("/executor-sessions"):
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                authoritative_completion=self.authoritative_completion,
                session=self.session,
                status="registered",
            )
        if path.endswith("/claims"):
            self.claim_attempts += 1
            if self.fail_first_claim and self.claim_attempts == 1:
                raise CoordinatorClientError("COORDINATOR_UNAVAILABLE", 503)
            self.claim_returned = True
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                dispatch=self.dispatch,
                status="delivered",
            )
        if path.endswith(":heartbeat"):
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                dispatch=self.dispatch,
                status="heartbeat",
            )
        if path.endswith(":complete"):
            self.completed = True
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                dispatch=self.dispatch,
                status="completed",
            )
        if path.endswith(":abandon"):
            self.abandoned = True
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                dispatch=self.dispatch,
                status="abandoned",
            )
        raise AssertionError(f"unexpected coordinator path: {path}")


def test_connect_executor_registers_reconnects_and_runs_owner_scoped_lifecycle():
    client = LoopClient(fail_first_claim=True)
    sleeps = []
    executions = []

    def execute(dispatch, heartbeat, _fetch_artifact):
        executions.append(dispatch)
        assert heartbeat().attempt_id == dispatch.attempt_id
        return ExecutorCompletion(result=failed_result())

    summary = connect_executor(
        client,
        mission_id=MISSION_ID,
        expected_head=HEAD,
        session_id="session_cloud_api_1",
        worker_id="worker_cloud_api_1",
        capabilities=(TaskKind.WORK,),
        execute=execute,
        should_stop=lambda: client.completed,
        max_reconnect_attempts=2,
        sleep=sleeps.append,
    )

    assert (summary.claimed, summary.completed) == (1, 1)
    assert summary.executor_id == IDENTITY.executor_id
    assert executions == [client.dispatch]
    assert sleeps == [1]
    claims = [request for path, request in client.calls if path.endswith("/claims")]
    assert len(claims) == 2
    assert claims[0].command_id == claims[1].command_id
    assert all(request.worker_id == "worker_cloud_api_1" for request in claims)
    paths = [path for path, _request in client.calls]
    assert any(path.endswith(":heartbeat") for path in paths)
    assert any(path.endswith(":complete") for path in paths)


def test_connect_executor_preflight_refuses_work_without_completion_authority():
    client = LoopClient(authoritative_completion=False)

    try:
        connect_executor(
            client,
            mission_id=MISSION_ID,
            expected_head=HEAD,
            session_id="session_cloud_api_1",
            worker_id="worker_cloud_api_1",
            capabilities=(TaskKind.WORK,),
            execute=lambda *_args: ExecutorCompletion(result=failed_result()),
            should_stop=lambda: False,
            sleep=lambda _seconds: None,
        )
    except CoordinatorClientError as error:
        assert (error.code, error.status_code) == (
            "DOMAIN_TRANSITION_UNAVAILABLE",
            409,
        )
    else:
        raise AssertionError("executor connected without completion authority")

    assert [path for path, _request in client.calls] == [
        f"/v1/missions/{MISSION_ID}/executor-sessions"
    ]


def test_connect_executor_shutdown_and_failure_leave_the_lease_to_ttl_without_abandon():
    # §6.4: abandon is disabled for this release, so neither shutdown after a
    # claim nor a failing execution may call the abandon endpoint; the claimed
    # lease honestly expires on its TTL instead.
    client = LoopClient()

    summary = connect_executor(
        client,
        mission_id=MISSION_ID,
        expected_head=HEAD,
        session_id="session_cloud_api_1",
        worker_id="worker_cloud_api_1",
        capabilities=(TaskKind.WORK,),
        execute=lambda *_args: (_ for _ in ()).throw(
            AssertionError("shutdown work must not execute")
        ),
        should_stop=lambda: client.claim_returned,
        sleep=lambda _seconds: None,
    )

    assert (summary.claimed, summary.completed) == (1, 0)
    assert client.abandoned is False
    assert not any(path.endswith(":abandon") for path, _request in client.calls)

    failing = LoopClient()
    with pytest.raises(RuntimeError, match="executor work exploded"):
        connect_executor(
            failing,
            mission_id=MISSION_ID,
            expected_head=HEAD,
            session_id="session_cloud_api_1",
            worker_id="worker_cloud_api_1",
            capabilities=(TaskKind.WORK,),
            execute=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("executor work exploded")
            ),
            should_stop=lambda: False,
            sleep=lambda _seconds: None,
        )
    assert failing.abandoned is False
    assert not any(path.endswith(":abandon") for path, _request in failing.calls)


def test_abandon_endpoint_is_disabled_in_this_release_and_never_reaches_the_store():
    store = RecorderStore()
    client = TestClient(create_coordinator_app(store, verifier))
    response = client.post(
        f"/v1/missions/{MISSION_ID}/attempts/attempt_cloud_api_1:abandon",
        headers={"Authorization": "Bearer oidc-test-token"},
        json={
            **body("command_abandon_api_02"),
            "lease_id": "lease_cloud_api_1",
            "fencing_token": 1,
            "reason_code": "executor_shutdown",
        },
    )

    assert response.status_code == 501
    assert response.json() == {
        "code": "ABANDON_UNSUPPORTED",
        "detail": (
            "Dispatch abandon is unsupported in this release; "
            "the lease expires on its TTL."
        ),
    }
    assert store.calls == []


def test_coordinator_reports_multi_executor_unsupported_with_a_named_code():
    store = RecorderStore()
    store.failure = MultiExecutorUnsupported("PRIVATE_SECOND_SESSION_CANARY")
    client = TestClient(
        create_coordinator_app(store, verifier), raise_server_exceptions=False
    )
    response = client.post(
        f"/v1/missions/{MISSION_ID}/executor-sessions",
        headers={"Authorization": "Bearer oidc-test-token"},
        json={
            "command_id": "command_register_003",
            "expected_head": HEAD.model_dump(mode="json"),
            "session_id": "session_cloud_api_2",
            "worker_ids": ["worker_cloud_api_1"],
            "capabilities": ["work"],
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "MULTI_EXECUTOR_UNSUPPORTED",
        "detail": (
            "Cloud multi-executor is unsupported in this release; "
            "the mission already has a live executor session."
        ),
    }
    assert "CANARY" not in response.text


def test_second_concurrent_executor_session_is_refused_until_the_first_goes_stale():
    clock = FirestoreClock(FIRESTORE_START)
    store = FirestoreMissionStore(
        FakeFirestoreClient(),
        namespace="test",
        clock=clock,
        allow_test_bootstrap=True,
    )
    event = store.append(
        FIRESTORE_MISSION_ID,
        firestore_empty_head(),
        "command_multi_event_0001",
        firestore_draft("created"),
    )
    current = firestore_head(event)

    def register(session_id: str, command_id: str) -> ExecutorSession:
        return store.register_executor_session(
            FIRESTORE_MISSION_ID,
            current,
            command_id,
            principal="principal@example.invalid",
            executor_id="executor_multi_1",
            session_id=session_id,
            worker_ids=("worker_multi_1",),
            capabilities=(TaskKind.WORK,),
        )

    first = register("session_multi_a", "command_multi_register_a1")
    with pytest.raises(MultiExecutorUnsupported, match="unsupported in this release"):
        register("session_multi_b", "command_multi_register_b1")
    assert register("session_multi_a", "command_multi_register_a1") == first
    # A crashed executor stops blocking once its session sits idle past the
    # store's lease bound; until then the mission honestly refuses new sessions.
    clock.value = FIRESTORE_START + timedelta(seconds=301)
    superseding = register("session_multi_b", "command_multi_register_b2")
    assert superseding.session_id == "session_multi_b"


def test_reduce_successful_completion_records_executor_attested_check_authority():
    # §6.3 made explicit: the receipt's template/tree/output digests are
    # invented here and never recomputed by the coordinator; the transition is
    # accepted and permanently labels the check authority in the committed
    # task.completed payload, inside the event hash chain.
    active = firestore_lease("lease_authority_1", 1, FIRESTORE_START)
    dispatch = cloud_dispatch(active)
    current = MissionHead(
        mission_id=FIRESTORE_MISSION_ID,
        seq=1,
        event_sha256="b" * 64,
        event_count=1,
    )
    snapshot = running_cloud_snapshot(current, active, dispatch)
    task = next(item for item in snapshot.tasks if item.task_id == active.task_id)
    output = task.expected_outputs[0]
    output_bytes = b"executor attested candidate bytes"
    envelope = ArtifactEnvelopeV2.create(
        output_bytes,
        mission_id=FIRESTORE_MISSION_ID,
        plan_revision=active.plan_revision,
        plan_sha256=canonical_json_sha256(snapshot.plan.model_dump(mode="json")),
        task_id=active.task_id,
        attempt_id=active.attempt_id,
        fencing_token=active.fencing_token,
        policy_sha256=snapshot.policy.policy_sha256,
        base_git_commit=snapshot.policy.base_sha,
        direct_inputs=(),
        output_name=output.name,
        artifact_kind=output.kind,
        media_type="application/vnd.graphene.patch",
        created_by="trusted-worker-wrapper",
    )
    envelope_reference = ArtifactEnvelopeReferenceV2(
        schema_version=2,
        artifact_id="artifact_authority_output_1",
        producer_task_id=active.task_id,
        output_name=output.name,
        kind=output.kind,
        media_type=envelope.media_type,
        byte_count=envelope.byte_count,
        content_sha256=envelope.content_sha256,
        artifact_envelope_sha256=envelope.artifact_envelope_sha256,
    )
    output_reference = EvidenceReference(
        kind=output.kind,
        id=envelope_reference.artifact_id,
        sha256=envelope_reference.content_sha256,
    )
    receipt = TrustedCheckReceipt(
        schema_version=2,
        mission_id=FIRESTORE_MISSION_ID,
        task_id=active.task_id,
        attempt_id=active.attempt_id,
        plan_revision=active.plan_revision,
        fencing_token=active.fencing_token,
        policy_sha256=snapshot.policy.policy_sha256,
        base_sha=snapshot.policy.base_sha,
        runner_id="graphene_check_runner_v1",
        template_id=task.acceptance_checks[0],
        template_sha256="e" * 64,
        accepted_input_references=(),
        candidate_references=(envelope_reference,),
        candidate_tree_hash_version="graphene.tree.v2",
        candidate_tree_sha256="f" * 64,
        result_code="passed",
        exit_code=0,
        timed_out=False,
        output_sha256="a" * 64,
        output_truncated=False,
        cleanup_complete=True,
    )
    receipt_reference = EvidenceReference(
        kind="test-receipt",
        id="artifact_authority_receipt_1",
        sha256=canonical_json_sha256(receipt.model_dump(mode="json")),
    )
    references = tuple(
        sorted(
            (output_reference, receipt_reference),
            key=lambda item: (item.kind, item.id, item.sha256),
        )
    )
    result = AttemptResult(
        succeeded=True,
        result_code="passed",
        session_id=dispatch.session_id,
        invocation_id="invocation_authority_1",
        evidence_link=GenericEvidenceLink(evidence_id="evidence_authority_1"),
        evidence_refs=references,
        artifact_envelopes=(envelope_reference,),
        publications=(
            PublicationDraft(
                output_name=output.name,
                kind=output.kind,
                sha256=output_reference.sha256,
                artifact=envelope_reference,
                paths=output.paths,
            ),
        ),
    )
    artifacts = (
        ExecutorArtifactReference(
            reference=output_reference,
            byte_count=len(output_bytes),
            envelope=envelope,
            executor_id=dispatch.executor_id,
        ),
        ExecutorArtifactReference(
            reference=receipt_reference,
            byte_count=128,
            executor_id=dispatch.executor_id,
        ),
    )

    transition = reduce_successful_completion(
        snapshot,
        dispatch,
        result,
        artifacts,
        receipt,
        recorded_at=FIRESTORE_START + timedelta(seconds=3),
    )

    completed = next(
        item
        for item in transition.drafts
        if item.event_type == MissionEventType.TASK_COMPLETED
    )
    assert completed.payload["check_authority"] == "executor_attested"
    assert completed.payload["task_id"] == active.task_id
    # The arbitrary attested digests really were accepted, not recomputed.
    assert (receipt.template_sha256, receipt.candidate_tree_sha256) == (
        "e" * 64,
        "f" * 64,
    )


def test_protocol_models_forbid_unknown_identity_fields():
    values = {
        "command_id": "command_register_002",
        "expected_head": HEAD.model_dump(mode="json"),
        "session_id": "session_cloud_api_1",
        "worker_ids": ["worker_cloud_api_1"],
        "capabilities": ["work"],
        "executor_id": "body_selected_executor",
    }
    try:
        RegisterExecutorRequest.model_validate(values)
    except ValueError as error:
        assert "extra" in str(error).lower()
    else:
        raise AssertionError("strict request accepted executor_id")
