from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from google.cloud import firestore

from graphene.artifact_envelope import ArtifactEnvelopeV2
from graphene.hashing import canonical_json_sha256
from graphene.core_models import TruthKind
from graphene.orchestration.cloud_protocol import (
    DispatchOutboxState,
    ExecutorArtifactObservation,
)
from graphene.orchestration.cloud_seed import seed_verified_projection
from graphene.orchestration.evidence import TrustedCheckReceipt
from graphene.orchestration.firestore_mission_store import (
    FirestoreMissionStore,
    MissionStateInvalid,
    MultiExecutorUnsupported,
)
from graphene.orchestration.mission_models import (
    ArtifactEnvelopeReferenceV2,
    AttemptResult,
    AttemptState,
    AuthorizationMode,
    EvidenceReference,
    FinalizationMode,
    GenericEvidenceLink,
    Mission,
    MissionEventType,
    MissionHead,
    MissionStatus,
    ProjectPolicy,
    PublicationDraft,
    PublicationState,
    TaskKind,
    TaskState,
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


def _verify_event_chain(store, mission_id: str) -> tuple:
    """Recompute every event hash and its chain link back to the empty head."""

    committed = store.head(mission_id)
    events = store.tail(mission_id, 0)
    assert events, "mission has no events to verify"
    previous_sha = None
    for index, event in enumerate(events, start=1):
        assert event.seq == index
        assert event.previous_event_sha256 == previous_sha
        assert event.payload_sha256 == canonical_json_sha256(event.payload)
        assert event.event_sha256 == canonical_json_sha256(
            event.model_dump(mode="json", exclude={"event_sha256"})
        )
        previous_sha = event.event_sha256
    assert events[-1].seq == committed.seq
    assert events[-1].event_sha256 == committed.event_sha256
    return events


def _assert_materialization_invariants(store, mission_ref, mission_id: str) -> None:
    pointer = mission_ref.collection("materialized").document("current").get().to_dict()
    assert pointer["root_sha256"] == pointer["target_root_sha256"]
    assert pointer["materialization_pending"] is False
    assert "value" not in pointer
    assert len(tuple(mission_ref.collection("state_records").stream())) >= 5
    snapshot = store.snapshot(mission_id)
    assert store.reconcile_materialization(mission_id) == snapshot


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


@pytest.mark.skipif(
    os.environ.get("GRAPHENE_RUN_FIRESTORE_EMULATOR") != "1",
    reason="official Firestore Emulator proof requires exact opt-in",
)
def test_official_emulator_success_round_trip_is_seeded_and_executor_attested():
    """Seed via cloud_seed, run one executor to a successful completion.

    Proves against the official emulator client: schema-2 local-contract
    projection and receipt idempotency, second-session refusal, the
    succeeded=True completion path with a real TrustedCheckReceipt, the recorded
    ``check_authority: executor_attested`` in the committed task.completed
    payload, a fully recomputed event hash chain, and the sharded
    materialization invariants.
    """

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
        base_policy, base_mission, plan = load_scenario().contracts(
            mission_id=mission_id,
            repo_id=f"repo-{suffix}",
            base_sha="a" * 40,
            created_at=issued_at,
        )
        policy = ProjectPolicy.model_validate(
            {
                **base_policy.model_dump(mode="json"),
                "schema_version": 2,
                "authorization_mode": AuthorizationMode.REVIEW_REQUIRED,
                "finalization_mode": FinalizationMode.REVIEW_REQUIRED,
            }
        )
        mission = Mission.model_validate(
            {
                **base_mission.model_dump(mode="json"),
                "schema_version": 2,
                "creation_source": "operator",
                "requested_authorization_mode": AuthorizationMode.REVIEW_REQUIRED,
                "requested_finalization_mode": FinalizationMode.REVIEW_REQUIRED,
            }
        )
        source_head = MissionHead(
            mission_id=mission_id,
            seq=5,
            event_count=5,
            event_sha256="b" * 64,
        )
        seed_values = {
            "source_policy": policy,
            "source_mission": mission,
            "source_head": source_head,
            "plan": plan,
            "command_prefix": f"emuseed_{suffix}",
            "operator_label": "emulator-fixture",
            "rationale": "official emulator success-path proof",
            "truth_kind": TruthKind.SERVER_DERIVED,
            "project_id": _EMULATOR_PROJECT,
            "database_id": "(default)",
            "namespace": namespace,
            "coordinator_audience": "https://coordinator.example.run.app",
        }
        receipt = seed_verified_projection(
            store, recorded_at=issued_at, **seed_values
        )
        seeded = receipt.firestore_head
        assert seeded.seq > 0
        # Retrying the seed replays the same idempotent commands.
        assert seed_verified_projection(
            store,
            recorded_at=issued_at + timedelta(seconds=1),
            **seed_values,
        ) == receipt

        executor_id = f"executor_{suffix}"
        session_id = f"session_{suffix}"
        worker_id = f"worker_{suffix}"
        store.register_executor_session(
            mission_id,
            seeded,
            "command_emulator_session1",
            principal="emulator-principal",
            executor_id=executor_id,
            session_id=session_id,
            worker_ids=(worker_id,),
            capabilities=(TaskKind.WORK,),
        )
        with pytest.raises(MultiExecutorUnsupported):
            store.register_executor_session(
                mission_id,
                seeded,
                "command_emulator_session2",
                principal="emulator-principal",
                executor_id=executor_id,
                session_id=f"session_second_{suffix}",
                worker_ids=(worker_id,),
                capabilities=(TaskKind.WORK,),
            )

        delivered = store.claim_dispatch(
            mission_id,
            seeded,
            "command_emulator_claim_01",
            executor_id=executor_id,
            session_id=session_id,
            worker_id=worker_id,
        )
        assert delivered is not None
        assert delivered.state == DispatchOutboxState.DELIVERED
        assert delivered.accepted_inputs == ()
        heartbeat_head = store.head(mission_id)
        assert heartbeat_head.seq == seeded.seq + 2
        store.heartbeat_dispatch(
            mission_id,
            delivered.attempt_id,
            heartbeat_head,
            "command_emulator_heartbeat1",
            executor_id=executor_id,
            session_id=session_id,
            worker_id=worker_id,
            lease_id=delivered.lease.lease_id,
            fencing_token=delivered.lease.fencing_token,
        )
        completion_head = store.head(mission_id)
        assert completion_head.seq == heartbeat_head.seq + 1

        before = store.snapshot(mission_id)
        task = next(
            item for item in before.tasks if item.task_id == delivered.task_id
        )
        output = task.expected_outputs[0]
        output_bytes = b"emulator success candidate bytes"
        envelope = ArtifactEnvelopeV2.create(
            output_bytes,
            mission_id=mission_id,
            plan_revision=delivered.plan_revision,
            plan_sha256=canonical_json_sha256(before.plan.model_dump(mode="json")),
            task_id=delivered.task_id,
            attempt_id=delivered.attempt_id,
            fencing_token=delivered.lease.fencing_token,
            policy_sha256=before.policy.policy_sha256,
            base_git_commit=before.policy.base_sha,
            direct_inputs=(),
            output_name=output.name,
            artifact_kind=output.kind,
            media_type="application/vnd.graphene.patch",
            created_by="trusted-worker-wrapper",
        )
        envelope_reference = ArtifactEnvelopeReferenceV2(
            schema_version=2,
            artifact_id=f"artifact_output_{suffix}",
            producer_task_id=delivered.task_id,
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
        # The digest fields below are executor-attested by design (§6.3): the
        # coordinator never recomputes them.
        receipt = TrustedCheckReceipt(
            schema_version=2,
            mission_id=mission_id,
            task_id=delivered.task_id,
            attempt_id=delivered.attempt_id,
            plan_revision=delivered.plan_revision,
            fencing_token=delivered.lease.fencing_token,
            policy_sha256=before.policy.policy_sha256,
            base_sha=before.policy.base_sha,
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
            output_sha256="d" * 64,
            output_truncated=False,
            cleanup_complete=True,
        )
        receipt_reference = EvidenceReference(
            kind="test-receipt",
            id=f"artifact_receipt_{suffix}",
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
            session_id=session_id,
            invocation_id=f"invocation_{suffix}",
            evidence_link=GenericEvidenceLink(evidence_id=f"evidence_{suffix}"),
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
        artifacts = tuple(
            ExecutorArtifactObservation(
                reference=reference,
                byte_count=(
                    len(output_bytes)
                    if reference == output_reference
                    else 128
                ),
                envelope=envelope if reference == output_reference else None,
            )
            for reference in references
        )
        completed = store.complete_dispatch(
            mission_id,
            delivered.attempt_id,
            completion_head,
            "command_emulator_complete1",
            executor_id=executor_id,
            session_id=session_id,
            worker_id=worker_id,
            lease_id=delivered.lease.lease_id,
            fencing_token=delivered.lease.fencing_token,
            result=result,
            artifacts=artifacts,
            check_receipt=receipt,
        )
        assert completed.state == DispatchOutboxState.COMPLETED

        after = store.snapshot(mission_id)
        assert after.mission.status == MissionStatus.RUNNING
        assert next(
            item for item in after.tasks if item.task_id == delivered.task_id
        ).state == TaskState.DONE
        assert next(
            item
            for item in after.attempts
            if item.attempt_id == delivered.attempt_id
        ).state == AttemptState.COMMITTED
        assert [item.state for item in after.publications] == [
            PublicationState.ACCEPTED
        ]
        released = next(
            item
            for item in after.leases
            if item.lease_id == delivered.lease.lease_id
        )
        assert released.released_at is not None
        assert released.release_reason == "completed"

        events = _verify_event_chain(store, mission_id)
        completed_events = [
            item
            for item in events
            if item.event_type == MissionEventType.TASK_COMPLETED
        ]
        assert len(completed_events) == 1
        payload = completed_events[0].payload
        assert payload["check_authority"] == "executor_attested"
        assert payload["task_id"] == delivered.task_id
        assert payload["result_code"] == "passed"
        assert {item.event_type for item in events} >= {
            MissionEventType.ARTIFACT_PUBLISHED,
            MissionEventType.ARTIFACT_ACCEPTED,
            MissionEventType.TASK_COMPLETED,
            MissionEventType.DEPENDENCY_SATISFIED,
        }
        _assert_materialization_invariants(store, mission_ref, mission_id)
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
