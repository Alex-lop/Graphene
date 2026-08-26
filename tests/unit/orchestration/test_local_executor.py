from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event

import pytest

from graphene.hashing import sha256_hex
from graphene.orchestration.cloud_protocol import (
    ArtifactFetchCapability,
    CoordinatorResult,
    DispatchOutboxRecord,
    DispatchOutboxState,
    DispatchTransition,
    ExecutorSession,
    new_dispatch_record,
)
from graphene.orchestration.executor_client import (
    CoordinatorClientError,
    ExecutorCompletion,
)
from graphene.orchestration.local_executor import (
    LOCAL_EXECUTOR_TRUTH,
    LocalDispatchExecutor,
    LocalExecutorError,
    run_local_executor,
)
from graphene.orchestration.mission_models import (
    AttemptResult,
    EvidenceReference,
    Lease,
    MissionHead,
    TaskKind,
)


MISSION_ID = "mission_local_executor"
HEAD = MissionHead(
    mission_id=MISSION_ID, seq=1, event_sha256="a" * 64, event_count=1
)
CONTENT = b"accepted input"
INPUT = EvidenceReference(
    kind="patch", id="artifact_local_input", sha256=sha256_hex(CONTENT)
)


def _completion() -> ExecutorCompletion:
    return ExecutorCompletion(
        result=AttemptResult(
            succeeded=False,
            result_code="provider_unavailable",
            session_id="session_local_executor",
            invocation_id="invocation_local_executor",
        )
    )


def _dispatch() -> DispatchOutboxRecord:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    lease = Lease(
        lease_id="lease_local_executor",
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id="task_local_executor",
        attempt_id="attempt_local_executor",
        owner="worker_local_executor",
        fencing_token=1,
        issued_at=now,
        heartbeat_at=now,
        expires_at=now + timedelta(minutes=1),
    )
    pending = new_dispatch_record(
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id=lease.task_id,
        task_kind=TaskKind.WORK,
        attempt_id=lease.attempt_id,
        attempt_number=1,
        executor_id="executor_local",
        worker_id=lease.owner,
        session_id="session_local_executor",
        lease=lease,
        accepted_inputs=(INPUT,),
        artifact_executor_id="executor_local",
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


def test_local_dispatch_fetches_verified_inputs_and_heartbeats() -> None:
    dispatch = _dispatch()
    heartbeats = []
    release = Event()

    def run(context):
        assert context.accepted_inputs[0].content == CONTENT
        assert release.wait(1)
        return _completion()

    def heartbeat():
        heartbeats.append(True)
        release.set()
        return dispatch

    result = LocalDispatchExecutor(
        run,
        lambda: False,
        fetch_artifact=lambda _dispatch, _reference: CONTENT,
        heartbeat_interval_seconds=0.01,
    )(dispatch, heartbeat)

    assert result.result.result_code == "provider_unavailable"
    assert heartbeats


@pytest.mark.parametrize(
    ("fetch", "code"),
    (
        (None, "ARTIFACT_FETCH_CAPABILITY_UNAVAILABLE"),
        (lambda _dispatch, _reference: b"tampered", "ARTIFACT_DIGEST_MISMATCH"),
    ),
)
def test_local_dispatch_fails_closed_without_verified_artifact_fetch(fetch, code) -> None:
    executor = LocalDispatchExecutor(
        lambda _context: _completion(),
        lambda: False,
        fetch_artifact=fetch,
    )

    with pytest.raises(LocalExecutorError) as caught:
        executor(_dispatch(), lambda: _dispatch())
    assert caught.value.code == code


def test_local_dispatch_propagates_cooperative_cancellation() -> None:
    cancelled = []
    dispatch = _dispatch()

    def run(context):
        assert context.cancelled.wait(1)
        cancelled.append(True)
        raise LocalExecutorError("EXECUTION_CANCELLED")

    executor = LocalDispatchExecutor(
        run,
        lambda: True,
        fetch_artifact=lambda _dispatch, _reference: CONTENT,
        heartbeat_interval_seconds=0.01,
    )

    with pytest.raises(LocalExecutorError) as caught:
        executor(dispatch, lambda: dispatch)
    assert caught.value.code == "EXECUTION_CANCELLED"
    assert cancelled == [True]


def test_rejected_heartbeat_signals_the_running_attempt_to_cancel() -> None:
    observed = Event()

    def run(context):
        assert context.cancelled.wait(1)
        observed.set()
        raise LocalExecutorError("STALE_FENCE")

    executor = LocalDispatchExecutor(
        run,
        lambda: False,
        fetch_artifact=lambda _dispatch, _reference: CONTENT,
        heartbeat_interval_seconds=0.01,
    )

    with pytest.raises(CoordinatorClientError, match="STALE_FENCE"):
        executor(
            _dispatch(),
            lambda: (_ for _ in ()).throw(
                CoordinatorClientError("STALE_FENCE", 409)
            ),
        )
    assert observed.wait(1)


class ReplayClient:
    def __init__(self, *, authoritative_completion: bool = True) -> None:
        self.dispatch = _dispatch()
        self.authoritative_completion = authoritative_completion
        self.calls = []
        self.complete_attempts = 0
        self.completed = False
        now = datetime(2026, 8, 20, tzinfo=UTC)
        self.session = ExecutorSession(
            mission_id=MISSION_ID,
            session_id=self.dispatch.session_id,
            executor_id=self.dispatch.executor_id,
            principal="executor@example.invalid",
            worker_ids=(self.dispatch.worker_id,),
            capabilities=(TaskKind.WORK,),
            created_at=now,
            last_seen_at=now,
            queued_attempt_ids=(self.dispatch.attempt_id,),
        )
        self.artifact_capability = ArtifactFetchCapability(
            capability_id="artifact_cap_0123456789abcdef0123456789abcdef",
            mission_id=MISSION_ID,
            dispatch_sha256=self.dispatch.dispatch_sha256,
            delivery_count=self.dispatch.delivery_count,
            attempt_id=self.dispatch.attempt_id,
            executor_id=self.dispatch.executor_id,
            session_id=self.dispatch.session_id,
            worker_id=self.dispatch.worker_id,
            lease_id=self.dispatch.lease.lease_id,
            fencing_token=self.dispatch.lease.fencing_token,
            reference=INPUT,
            issued_at=self.dispatch.last_delivery_at,
            expires_at=self.dispatch.lease.expires_at,
            token="d" * 64,
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
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                artifact_capabilities=(self.artifact_capability,),
                dispatch=self.dispatch,
                status="delivered",
            )
        if path.endswith(":complete"):
            self.complete_attempts += 1
            if self.complete_attempts == 1:
                raise CoordinatorClientError("COORDINATOR_UNAVAILABLE", 503)
            self.completed = True
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                dispatch=self.dispatch,
                status="completed",
            )
        if path.endswith(":abandon"):
            return CoordinatorResult(
                mission_id=MISSION_ID,
                head=HEAD,
                dispatch=self.dispatch,
                status="abandoned",
            )
        raise AssertionError(f"unexpected path: {path}")

    def fetch_artifact(self, capability, expected_head, *, session_id, worker_id):
        assert capability == self.artifact_capability
        assert expected_head == HEAD
        assert (session_id, worker_id) == (
            self.dispatch.session_id,
            self.dispatch.worker_id,
        )
        return CONTENT


def test_local_executor_replays_the_exact_completion_request() -> None:
    client = ReplayClient()
    sleeps = []

    summary = run_local_executor(
        client,
        mission_id=MISSION_ID,
        expected_head=HEAD,
        session_id=client.dispatch.session_id,
        worker_id=client.dispatch.worker_id,
        capabilities=(TaskKind.WORK,),
        run_attempt=lambda context: (
            _completion()
            if context.accepted_inputs[0].content == CONTENT
            else (_ for _ in ()).throw(AssertionError("input mismatch"))
        ),
        should_stop=lambda: client.completed,
        max_reconnect_attempts=1,
        sleep=sleeps.append,
    )

    completions = [
        request for path, request in client.calls if path.endswith(":complete")
    ]
    assert (summary.claimed, summary.completed) == (1, 1)
    assert len(completions) == 2
    assert completions[0] == completions[1]
    assert sleeps == [1]


def test_executor_still_fails_closed_if_a_coordinator_denies_completion_authority() -> None:
    client = ReplayClient(authoritative_completion=False)

    with pytest.raises(CoordinatorClientError) as caught:
        run_local_executor(
            client,
            mission_id=MISSION_ID,
            expected_head=HEAD,
            session_id=client.dispatch.session_id,
            worker_id=client.dispatch.worker_id,
            capabilities=(TaskKind.WORK,),
            run_attempt=lambda _context: _completion(),
            should_stop=lambda: False,
            fetch_artifact=lambda _dispatch, _reference: CONTENT,
            sleep=lambda _seconds: None,
        )

    assert caught.value.code == "DOMAIN_TRANSITION_UNAVAILABLE"
    assert "NOT DEPLOYED" in LOCAL_EXECUTOR_TRUTH
    assert [path for path, _request in client.calls] == [
        f"/v1/missions/{MISSION_ID}/executor-sessions"
    ]
