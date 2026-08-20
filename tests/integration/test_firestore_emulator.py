from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime

import pytest
from google.cloud import firestore

from graphene.models import TruthKind
from graphene.orchestration.cloud_protocol import DispatchOutboxState
from graphene.orchestration.firestore import (
    FirestoreMissionStore,
    MissionStateInvalid,
)
from graphene.orchestration.models import (
    AttemptResult,
    MissionEventType,
    MissionStatus,
    TaskKind,
)
from graphene.orchestration.scripted import load_scenario


_EMULATOR_PROJECT = "demo-graphene-emulator"
_TEST_DOCUMENT_LIMIT = 128
_TEST_COLLECTIONS = (
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


def _cleanup_test_mission(
    mission_ref, namespace: str, mission_id: str, *, schema_ref=None
) -> None:
    suffix = namespace.removeprefix("emulator_")
    if (
        re.fullmatch(r"[0-9a-f]{12}", suffix) is None
        or mission_id != f"mission_emulator_{suffix}"
        or mission_ref.parent.id != f"{namespace}_missions"
        or mission_ref.id != mission_id
    ):
        raise RuntimeError("refusing cleanup outside the exact emulator test namespace")
    if schema_ref is not None and (
        schema_ref.parent.id != f"{namespace}_system" or schema_ref.id != "schema"
    ):
        raise RuntimeError("refusing cleanup outside the exact emulator schema")

    snapshots = []
    for collection_name in _TEST_COLLECTIONS:
        remaining = _TEST_DOCUMENT_LIMIT + 1 - len(snapshots)
        if remaining <= 0:
            break
        snapshots.extend(
            mission_ref.collection(collection_name).limit(remaining).stream()
        )
    if len(snapshots) > _TEST_DOCUMENT_LIMIT:
        raise RuntimeError("emulator cleanup exceeded its bounded document allowance")
    for snapshot in snapshots:
        snapshot.reference.delete()
    mission_ref.delete()
    if schema_ref is not None:
        schema_ref.delete()


class _FakeReference:
    def __init__(self) -> None:
        self.deleted = False

    def delete(self) -> None:
        self.deleted = True


class _FakeCollection:
    def __init__(self, references: list[_FakeReference]) -> None:
        self._references = references
        self._limit = len(references)

    def limit(self, value: int):
        self._limit = value
        return self

    def stream(self):
        return [
            type("Snapshot", (), {"reference": reference})()
            for reference in self._references[: self._limit]
        ]


class _FakeMissionReference:
    def __init__(self, namespace: str, mission_id: str, document_count: int) -> None:
        self.parent = type("Parent", (), {"id": f"{namespace}_missions"})()
        self.id = mission_id
        self.references = [_FakeReference() for _ in range(document_count)]
        self.deleted = False

    def collection(self, collection_name: str):
        references = self.references if collection_name == _TEST_COLLECTIONS[0] else []
        return _FakeCollection(references)

    def delete(self) -> None:
        self.deleted = True


def test_emulator_cleanup_is_exact_and_bounded():
    namespace = "emulator_012345abcdef"
    mission_id = "mission_emulator_012345abcdef"
    mission_ref = _FakeMissionReference(namespace, mission_id, 3)

    _cleanup_test_mission(mission_ref, namespace, mission_id)

    assert mission_ref.deleted is True
    assert all(reference.deleted for reference in mission_ref.references)


def test_emulator_cleanup_refuses_an_overlarge_namespace_without_deleting():
    namespace = "emulator_012345abcdef"
    mission_id = "mission_emulator_012345abcdef"
    mission_ref = _FakeMissionReference(
        namespace, mission_id, _TEST_DOCUMENT_LIMIT + 1
    )

    with pytest.raises(RuntimeError, match="bounded document allowance"):
        _cleanup_test_mission(mission_ref, namespace, mission_id)

    assert mission_ref.deleted is False
    assert not any(reference.deleted for reference in mission_ref.references)


@pytest.mark.skipif(
    os.environ.get("GRAPHENE_RUN_FIRESTORE_EMULATOR") != "1",
    reason="official Firestore Emulator proof requires exact opt-in",
)
def test_official_firestore_client_dispatch_round_trip():
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    if re.fullmatch(r"(?:127\.0\.0\.1|localhost):[0-9]{2,5}", host) is None:
        pytest.fail("FIRESTORE_EMULATOR_HOST must name an explicit loopback emulator")
    suffix = uuid.uuid4().hex[:12]
    namespace = f"emulator_{suffix}"
    mission_id = f"mission_emulator_{suffix}"
    client = firestore.Client(project=_EMULATOR_PROJECT, database="(default)")
    mission_ref = client.collection(f"{namespace}_missions").document(mission_id)
    schema_ref = client.collection(f"{namespace}_system").document("schema")
    store = FirestoreMissionStore(client, namespace=namespace)
    try:
        issued_at = datetime.now(UTC)
        store.initialize_namespace_schema()
        policy, mission, plan = load_scenario().contracts(
            mission_id=mission_id,
            repo_id=f"repo-{suffix}",
            base_sha="a" * 40,
            created_at=issued_at,
        )
        created = store.create_mission(
            policy,
            mission,
            plan,
            "command_emulator_create_1",
            recorded_at=issued_at,
        )
        approved = store.approve_plan(
            mission_id,
            "command_emulator_approve1",
            expected_revision=1,
            expected_head=created,
            operator_label="emulator-fixture",
            rationale="official emulator production transition proof",
            truth_kind=TruthKind.SIMULATED_FIXTURE,
            recorded_at=issued_at,
        )
        ready = store.refresh_ready(
            mission_id,
            "command_emulator_ready_01",
            recorded_at=issued_at,
        )
        assert ready
        ready_head = store.head(mission_id)
        worker_id = f"worker_{suffix}"
        store.register_executor_session(
            mission_id,
            ready_head,
            "command_emulator_session1",
            principal="emulator-principal",
            executor_id=f"executor_{suffix}",
            session_id=f"session_{suffix}",
            worker_ids=(worker_id,),
            capabilities=(TaskKind.WORK,),
        )
        delivered = store.claim_dispatch(
            mission_id,
            ready_head,
            "command_emulator_claim_01",
            executor_id=f"executor_{suffix}",
            session_id=f"session_{suffix}",
            worker_id=worker_id,
        )
        assert delivered is not None
        assert delivered.state == DispatchOutboxState.DELIVERED
        assert store.snapshot(mission_id).head.seq == ready_head.seq + 2
        heartbeat_head = store.head(mission_id)
        heartbeat = store.heartbeat_dispatch(
            mission_id,
            delivered.attempt_id,
            heartbeat_head,
            "command_emulator_heartbeat1",
            executor_id=delivered.executor_id,
            session_id=delivered.session_id,
            worker_id=delivered.worker_id,
            lease_id=delivered.lease.lease_id,
            fencing_token=delivered.lease.fencing_token,
        )
        completion_head = store.head(mission_id)
        assert completion_head.seq == heartbeat_head.seq + 1
        assert heartbeat.lease.heartbeat_at > delivered.lease.heartbeat_at
        completed = store.complete_dispatch(
            mission_id,
            delivered.attempt_id,
            completion_head,
            "command_emulator_complete1",
            executor_id=delivered.executor_id,
            session_id=delivered.session_id,
            worker_id=delivered.worker_id,
            lease_id=delivered.lease.lease_id,
            fencing_token=delivered.lease.fencing_token,
            result=AttemptResult(
                succeeded=False,
                result_code="provider_unavailable",
                session_id=delivered.session_id,
                invocation_id=f"invocation_{suffix}",
            ),
            retry_backoff_seconds=0,
        )
        assert completed.state == DispatchOutboxState.COMPLETED
        completed_snapshot = store.snapshot(mission_id)
        assert completed_snapshot.mission.status == MissionStatus.FAILED
        assert store.tail(mission_id, completion_head.seq)[0].event_type == (
            MissionEventType.TASK_FAILED
        )
        pointer_ref = mission_ref.collection("materialized").document("current")
        pointer = pointer_ref.get().to_dict()
        assert pointer["root_sha256"] == pointer["target_root_sha256"]
        assert pointer["materialization_pending"] is False
        assert "value" not in pointer
        assert len(tuple(mission_ref.collection("state_records").stream())) >= 5
        pointer_ref.set({**pointer, "materialization_pending": True})
        with pytest.raises(MissionStateInvalid, match="not materialized"):
            store.snapshot(mission_id)
        assert store.reconcile_materialization(mission_id) == completed_snapshot
        assert store.reconcile_materialization(mission_id) == completed_snapshot

        schema_ref.set(
            {
                "schema_version": 1,
                "current_version": 3,
                "min_reader_version": 3,
                "min_writer_version": 3,
            }
        )
        with pytest.raises(MissionStateInvalid, match="schema is incompatible"):
            store.snapshot(mission_id)
        assert approved.seq < ready_head.seq < completed_snapshot.head.seq
    finally:
        try:
            _cleanup_test_mission(
                mission_ref,
                namespace,
                mission_id,
                schema_ref=schema_ref,
            )
        finally:
            client.close()
