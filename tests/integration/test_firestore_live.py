from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from google.cloud import firestore

from graphene.hashing import canonical_json_sha256
from graphene.models import TruthKind
from graphene.orchestration.cloud_protocol import DispatchOutboxState, new_dispatch_record
from graphene.orchestration.firestore import FirestoreMissionStore
from graphene.orchestration.models import (
    Attempt,
    AttemptResult,
    AttemptState,
    Lease,
    MissionAuthority,
    MissionEventInput,
    MissionEventType,
    MissionHead,
    MissionSnapshot,
    MissionStatus,
    ProjectPolicySummary,
    TaskKind,
    TaskState,
)
from graphene.orchestration.scripted import load_scenario


_OPTED_IN = (
    os.environ.get("GRAPHENE_RUN_LIVE_FIRESTORE") == "1"
    and os.environ.get("GRAPHENE_RUN_CLOUD_SMOKE") == "1"
)
_MAX_CLEANUP_DOCUMENTS = 96
_SUBCOLLECTIONS = (
    "artifact_capabilities",
    "artifact_locality",
    "commands",
    "dispatch_outbox",
    "events",
    "executor_sessions",
    "lease_slots",
    "leases",
    "materialized",
    "state_records",
    "state_roots",
)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value or value != value.strip():
        pytest.fail(f"{name} is required for the explicitly opted-in live smoke")
    return value


def _cleanup(mission_ref, schema_ref, *, namespace: str, mission_id: str) -> None:
    if (
        mission_ref.parent.id != f"{namespace}_missions"
        or mission_ref.id != mission_id
        or schema_ref.parent.id != f"{namespace}_system"
        or schema_ref.id != "schema"
    ):
        raise RuntimeError("refusing live cleanup outside the exact smoke namespace")
    documents = []
    for name in _SUBCOLLECTIONS:
        remaining = _MAX_CLEANUP_DOCUMENTS + 1 - len(documents)
        if remaining <= 0:
            break
        documents.extend(mission_ref.collection(name).limit(remaining).stream())
    if len(documents) > _MAX_CLEANUP_DOCUMENTS:
        raise RuntimeError("live smoke cleanup exceeded its bounded allowance")
    for document in documents:
        document.reference.delete()
    mission_ref.delete()
    schema_ref.delete()


@pytest.mark.skipif(
    not _OPTED_IN,
    reason=(
        "live Firestore smoke requires exact GRAPHENE_RUN_LIVE_FIRESTORE=1 and "
        "GRAPHENE_RUN_CLOUD_SMOKE=1 opt-in"
    ),
)
def test_live_firestore_exact_namespace_round_trip() -> None:
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.fail("live Firestore smoke refuses FIRESTORE_EMULATOR_HOST")
    project = _required("GRAPHENE_LIVE_FIRESTORE_PROJECT")
    database = _required("GRAPHENE_LIVE_FIRESTORE_DATABASE")
    namespace_prefix = _required("GRAPHENE_LIVE_FIRESTORE_NAMESPACE")
    if re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project) is None:
        pytest.fail("GRAPHENE_LIVE_FIRESTORE_PROJECT is invalid")
    if (
        len(database) > 128
        or "/" in database
        or any(character.isspace() for character in database)
    ):
        pytest.fail("GRAPHENE_LIVE_FIRESTORE_DATABASE is invalid")
    if re.fullmatch(r"[a-z][a-z0-9_]{2,15}", namespace_prefix) is None:
        pytest.fail("GRAPHENE_LIVE_FIRESTORE_NAMESPACE is not a bounded prefix")

    suffix = uuid.uuid4().hex[:12]
    namespace = f"{namespace_prefix}_{suffix}"
    mission_id = f"mission_live_{suffix}"
    client = firestore.Client(project=project, database=database)
    mission_ref = client.collection(f"{namespace}_missions").document(mission_id)
    schema_ref = client.collection(f"{namespace}_system").document("schema")
    now = datetime.now(UTC)
    clock = _Clock(now)
    store = FirestoreMissionStore(
        client,
        namespace=namespace,
        clock=clock,
        allow_test_bootstrap=True,
    )
    try:
        empty = MissionHead(
            mission_id=mission_id, seq=0, event_sha256=None, event_count=0
        )
        event = store.append(
            mission_id,
            empty,
            f"command_live_create_{suffix}",
            MissionEventInput(
                event_type=MissionEventType.MISSION_CREATED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=MissionAuthority.MISSION_SERVICE,
                payload={"label": "explicit-live-firestore-smoke"},
            ),
        )
        head = MissionHead(
            mission_id=mission_id,
            seq=event.seq,
            event_sha256=event.event_sha256,
            event_count=event.seq,
        )
        policy, mission, plan = load_scenario().contracts(
            mission_id=mission_id,
            repo_id=f"repo-{suffix}",
            base_sha="a" * 40,
            created_at=now,
        )
        task = next(item for item in plan.tasks if item.task_id == "redact_notes")
        lease = Lease(
            lease_id=f"lease_{suffix}",
            mission_id=mission_id,
            plan_revision=1,
            task_id=task.task_id,
            attempt_id=f"attempt_{suffix}",
            owner=f"worker_{suffix}",
            write_paths=task.write_paths,
            fencing_token=1,
            issued_at=now,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=120),
        )
        dispatch = new_dispatch_record(
            mission_id=mission_id,
            plan_revision=1,
            task_id=task.task_id,
            task_kind=task.kind,
            attempt_id=lease.attempt_id,
            attempt_number=1,
            executor_id=f"executor_{suffix}",
            worker_id=lease.owner,
            session_id=f"session_{suffix}",
            lease=lease,
            accepted_inputs=(),
            artifact_executor_id=f"executor_{suffix}",
            creation_seq=head.seq,
        )
        attempt = Attempt(
            attempt_id=lease.attempt_id,
            mission_id=mission_id,
            plan_revision=1,
            task_id=task.task_id,
            attempt_number=1,
            worker_id=lease.owner,
            workspace_id=f"workspace_{suffix}",
            lease_id=lease.lease_id,
            fencing_token=lease.fencing_token,
            dispatch_command_id=f"dispatch_{suffix}",
            state=AttemptState.RUNNING,
            started_at=now,
        )
        summary = ProjectPolicySummary(
            policy_id=policy.policy_id,
            revision=policy.revision,
            repo_id=policy.repo_id,
            base_ref=policy.base_ref,
            base_sha=policy.base_sha,
            command_template_ids=tuple(
                item.template_id for item in policy.command_templates
            ),
            max_concurrency=policy.max_concurrency,
            retry_limit=policy.retry_limit,
            network_mode=policy.network.mode,
            policy_sha256=canonical_json_sha256(policy.model_dump(mode="json")),
        )
        values = {
            "schema_version": 1,
            "policy": summary.model_dump(mode="json"),
            "mission": mission.model_copy(
                update={"status": MissionStatus.RUNNING}
            ).model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            "tasks": [
                (
                    item.model_copy(
                        update={"attempt_count": 1, "state": TaskState.RUNNING}
                    )
                    if item.task_id == task.task_id
                    else item
                ).model_dump(mode="json")
                for item in plan.tasks
            ],
            "attempts": [attempt.model_dump(mode="json")],
            "leases": [lease.model_dump(mode="json")],
            "publications": [],
            "gates": [],
            "head": head.model_dump(mode="json"),
            "unknowns": list(mission.unknowns),
        }
        snapshot = MissionSnapshot.model_validate(
            {**values, "snapshot_sha256": canonical_json_sha256(values)}
        )
        store.claim_lease(lease, f"command_live_lease_{suffix}")
        store.save_snapshot(snapshot)
        session = store.register_executor_session(
            mission_id,
            head,
            f"command_live_register_{suffix}",
            principal="live-smoke-principal",
            executor_id=dispatch.executor_id,
            session_id=dispatch.session_id,
            worker_ids=(dispatch.worker_id,),
            capabilities=(TaskKind.WORK,),
        )
        store.enqueue_dispatch(dispatch, head, f"command_live_enqueue_{suffix}")
        delivered = store.claim_dispatch(
            mission_id,
            head,
            f"command_live_claim_{suffix}",
            executor_id=dispatch.executor_id,
            session_id=dispatch.session_id,
            worker_id=dispatch.worker_id,
        )
        assert delivered is not None
        reconnected = store.register_executor_session(
            mission_id,
            head,
            f"command_live_reconnect_{suffix}",
            principal=session.principal,
            executor_id=session.executor_id,
            session_id=session.session_id,
            worker_ids=session.worker_ids,
            capabilities=session.capabilities,
        )
        assert reconnected.session_id == session.session_id
        clock.value = now + timedelta(seconds=1)
        heartbeat = store.heartbeat_dispatch(
            mission_id,
            delivered.attempt_id,
            head,
            f"command_live_heartbeat_{suffix}",
            executor_id=delivered.executor_id,
            session_id=delivered.session_id,
            worker_id=delivered.worker_id,
            lease_id=delivered.lease.lease_id,
            fencing_token=delivered.lease.fencing_token,
        )
        completed = store.complete_dispatch(
            mission_id,
            heartbeat.attempt_id,
            head,
            f"command_live_complete_{suffix}",
            executor_id=heartbeat.executor_id,
            session_id=heartbeat.session_id,
            worker_id=heartbeat.worker_id,
            lease_id=heartbeat.lease.lease_id,
            fencing_token=heartbeat.lease.fencing_token,
            result=AttemptResult(
                succeeded=False,
                result_code="live_smoke_complete",
                session_id=heartbeat.session_id,
                invocation_id=f"invocation_{suffix}",
            ),
            retry_backoff_seconds=0,
        )
        assert completed.state == DispatchOutboxState.COMPLETED
        authoritative = store.snapshot(mission_id)
        assert authoritative.mission.status == MissionStatus.FAILED
        assert store.head(mission_id) == authoritative.head
        assert store.tail(mission_id, head.seq)[0].event_type == MissionEventType.TASK_FAILED
    finally:
        try:
            _cleanup(
                mission_ref,
                schema_ref,
                namespace=namespace,
                mission_id=mission_id,
            )
        finally:
            client.close()
