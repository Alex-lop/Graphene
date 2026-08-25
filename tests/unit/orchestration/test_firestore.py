from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import RLock

import graphene.orchestration.firestore as firestore_module
import pytest
from graphene.artifact_envelope import ArtifactEnvelopeV2
from graphene.hashing import canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.cloud_protocol import (
    ArtifactFetchGrant,
    DispatchOutboxState,
    ExecutorArtifactObservation,
    new_dispatch_record,
)
from graphene.orchestration.evidence import TrustedCheckReceipt
from graphene.orchestration.firestore import (
    ArtifactCapabilityRejected,
    ArtifactLocalityUnavailable,
    DomainTransitionUnavailable,
    ExecutorSessionRejected,
    FirestoreMissionStore,
    LeaseFenceRejected,
    MissionConflict,
    MissionStateInvalid,
)
from graphene.orchestration.models import (
    Attempt,
    ArtifactEnvelopeReferenceV2,
    ArtifactPublication,
    AttemptResult,
    AttemptState,
    EvidenceReference,
    GenericEvidenceLink,
    Lease,
    MissionAuthority,
    MissionEventInput,
    MissionEventType,
    MissionHead,
    MissionSnapshot,
    MissionStatus,
    ProjectPolicySummary,
    PublicationDraft,
    PublicationState,
    PublishedArtifactReferenceV2,
    TaskKind,
    TaskState,
)
from graphene.orchestration.projection import MissionProjection
from graphene.orchestration.scripted import load_scenario
from graphene.orchestration.store import SQLiteMissionStore, StaleWorker


class Snapshot:
    def __init__(self, reference, data):
        self.reference = reference
        self.id = reference.id
        self.exists = data is not None
        self._data = deepcopy(data)

    def to_dict(self):
        return deepcopy(self._data)


class Document:
    def __init__(self, client, path):
        self.client = client
        self.path = path
        self.id = path.rsplit("/", 1)[-1]

    def collection(self, name):
        return Collection(self.client, f"{self.path}/{name}")

    def get(self, transaction=None):
        if transaction is not None:
            return transaction.get(self)
        self.client.document_reads.append(self.path)
        return Snapshot(self, self.client.documents.get(self.path))


class Collection:
    def __init__(self, client, path):
        self.client = client
        self.path = path

    def document(self, document_id):
        return Document(self.client, f"{self.path}/{document_id}")

    def stream(self, transaction=None):
        self.client.full_collection_streams.append(self.path)
        return self.client.snapshots(self.path)

    def where(self, *, filter):
        return Query(self.client, self.path, filter=filter)


class Query:
    def __init__(self, client, path, *, filter):
        self.client = client
        self.path = path
        self.filter = filter
        self.order = None
        self.maximum = None

    def order_by(self, field):
        self.order = field
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def stream(self):
        self.client.queries.append(
            {
                "path": self.path,
                "field": self.filter.field_path,
                "operator": self.filter.op_string,
                "value": self.filter.value,
                "order": self.order,
                "limit": self.maximum,
            }
        )
        snapshots = list(self.client.snapshots(self.path))
        snapshots = [
            item
            for item in snapshots
            if item.to_dict()[self.filter.field_path] > self.filter.value
        ]
        snapshots.sort(key=lambda item: item.to_dict()[self.order])
        return tuple(snapshots[: self.maximum])


class Transaction:
    def __init__(self, client):
        self.client = client
        self.writes = []

    def reset(self):
        self.writes = []

    def get(self, document):
        return Snapshot(document, self.client.documents.get(document.path))

    def create(self, document, data):
        self.writes.append(("create", document.path, deepcopy(data)))

    def set(self, document, data):
        self.writes.append(("set", document.path, deepcopy(data)))

    def commit(self):
        result = deepcopy(self.client.documents)
        for operation, path, data in self.writes:
            if operation == "create" and path in result:
                raise AssertionError(f"unexpected create collision: {path}")
            result[path] = data
        self.client.documents = result


class Client:
    def __init__(self):
        self.documents = {}
        self.lock = RLock()
        self.retry_once = False
        self.transaction_attempts = []
        self.document_reads = []
        self.full_collection_streams = []
        self.queries = []

    def collection(self, name):
        return Collection(self, name)

    def transaction(self):
        return Transaction(self)

    def snapshots(self, collection_path):
        prefix = collection_path + "/"
        result = []
        for path, data in self.documents.items():
            remainder = path.removeprefix(prefix)
            if path.startswith(prefix) and "/" not in remainder:
                result.append(Snapshot(Document(self, path), data))
        return tuple(sorted(result, key=lambda item: item.id))


@pytest.fixture(autouse=True)
def fake_transactional(monkeypatch):
    def transactional(function):
        def invoke(transaction):
            with transaction.client.lock:
                attempts = 2 if transaction.client.retry_once else 1
                transaction.client.retry_once = False
                result = None
                for attempt in range(attempts):
                    transaction.reset()
                    result = function(transaction)
                    transaction.client.transaction_attempts.append(
                        deepcopy(transaction.writes)
                    )
                    if attempt == attempts - 1:
                        transaction.commit()
                return result

        return invoke

    monkeypatch.setattr(firestore_module.firestore, "transactional", transactional)


MISSION_ID = "mission_firestore_001"
START = datetime(2026, 8, 18, 12, tzinfo=UTC)


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class SequenceClock:
    def __init__(self, *values: datetime):
        self.values = list(values)

    def __call__(self) -> datetime:
        return self.values.pop(0)


def empty_head() -> MissionHead:
    return MissionHead(mission_id=MISSION_ID, seq=0, event_sha256=None, event_count=0)


def draft(
    label: str,
    event_type=MissionEventType.MISSION_CREATED,
    *,
    payload=None,
):
    return MissionEventInput(
        event_type=event_type,
        truth_kind=TruthKind.SERVER_DERIVED,
        authority=MissionAuthority.MISSION_SERVICE,
        payload=payload or {"label": label},
    )


def head(event) -> MissionHead:
    return MissionHead(
        mission_id=MISSION_ID,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def domain_snapshot(current: MissionHead) -> MissionSnapshot:
    scenario = load_scenario()
    policy, mission, plan = scenario.contracts(
        mission_id=MISSION_ID,
        repo_id="repo-firestore",
        base_sha="a" * 40,
        created_at=START,
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
        "mission": mission.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "tasks": [item.model_dump(mode="json") for item in plan.tasks],
        "attempts": [],
        "leases": [],
        "publications": [],
        "gates": [],
        "head": current.model_dump(mode="json"),
        "unknowns": list(mission.unknowns),
    }
    return MissionSnapshot.model_validate(
        {**values, "snapshot_sha256": canonical_json_sha256(values)}
    )


def test_production_create_approve_ready_and_claim_are_authoritative_transactions():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(client, namespace="domain", clock=clock)
    store.initialize_namespace_schema()
    policy, mission, plan = load_scenario().contracts(
        mission_id=MISSION_ID,
        repo_id="repo-firestore-domain",
        base_sha="a" * 40,
        created_at=START,
    )

    created = store.create_mission(
        policy,
        mission,
        plan,
        "command_domain_create_1",
        recorded_at=START,
    )
    assert created.seq == 4
    assert store.snapshot(MISSION_ID).mission.status == MissionStatus.PROPOSED
    approved = store.approve_plan(
        MISSION_ID,
        "command_domain_approve1",
        expected_revision=1,
        expected_head=created,
        operator_label="scripted-fixture",
        rationale="bounded domain parity proof",
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        recorded_at=START,
    )
    ready = store.refresh_ready(
        MISSION_ID,
        "command_domain_ready_01",
        recorded_at=START,
    )
    assert ready
    ready_head = store.head(MISSION_ID)
    store.register_executor_session(
        MISSION_ID,
        ready_head,
        "command_domain_session1",
        principal="test-principal",
        executor_id="executor_domain_1",
        session_id="session_domain_01",
        worker_ids=("worker_domain_001",),
        capabilities=(TaskKind.WORK,),
    )

    before = len(client.transaction_attempts)
    delivered = store.claim_dispatch(
        MISSION_ID,
        ready_head,
        "command_domain_claim_001",
        executor_id="executor_domain_1",
        session_id="session_domain_01",
        worker_id="worker_domain_001",
    )

    assert delivered is not None
    assert delivered.state == DispatchOutboxState.DELIVERED
    assert delivered.accepted_inputs == ()
    claimed = store.snapshot(MISSION_ID)
    assert claimed.head.seq == ready_head.seq + 2
    assert claimed.attempts[0].attempt_id == delivered.attempt_id
    assert claimed.leases[0] == delivered.lease
    assert store.tail(MISSION_ID, ready_head.seq)[:2] == tuple(
        event
        for event in store.tail(MISSION_ID, ready_head.seq)
        if event.event_type
        in {MissionEventType.TASK_LEASED, MissionEventType.TASK_STARTED}
    )[:2]
    writes = client.transaction_attempts[before]
    paths = {path for _operation, path, _value in writes}
    prefix = f"domain_missions/{MISSION_ID}"
    assert {
        prefix,
        f"{prefix}/materialized/current",
        f"{prefix}/executor_sessions/session_domain_01",
        f"{prefix}/dispatch_outbox/{delivered.attempt_id}",
        f"{prefix}/leases/{delivered.lease.lease_id}",
    } <= paths
    assert len([path for path in paths if "/state_records/" in path]) == 5
    assert len([path for path in paths if "/state_roots/" in path]) == 1
    assert approved.seq < ready_head.seq < claimed.head.seq


def test_sqlite_and_firestore_share_the_authoritative_failure_contract(tmp_path):
    policy, mission, plan = load_scenario().contracts(
        mission_id=MISSION_ID,
        repo_id="repo-contract-corpus",
        base_sha="a" * 40,
        created_at=START,
    )

    sqlite = SQLiteMissionStore(tmp_path / "contract.sqlite")
    sqlite_created = sqlite.create_mission(
        policy,
        mission,
        plan,
        "contract_sql_create_01",
        recorded_at=START,
    )
    sqlite_approved = sqlite.approve_plan(
        MISSION_ID,
        "contract_sql_approve1",
        expected_revision=1,
        expected_head=sqlite_created,
        operator_label="contract-fixture",
        rationale="normalized backend contract",
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        recorded_at=START + timedelta(seconds=1),
    )
    with pytest.raises(MissionConflict):
        sqlite.approve_plan(
            MISSION_ID,
            "contract_sql_stale_001",
            expected_revision=1,
            expected_head=sqlite_created,
            operator_label="contract-fixture",
            rationale="stale head must fail",
            truth_kind=TruthKind.SIMULATED_FIXTURE,
            recorded_at=START + timedelta(seconds=1),
        )
    sqlite.refresh_ready(
        MISSION_ID,
        "contract_sql_ready_001",
        recorded_at=START + timedelta(seconds=2),
    )
    sqlite.register_worker(
        MISSION_ID,
        "worker_contract_1",
        "runtime_contract_1",
        (TaskKind.WORK,),
        "contract_sql_worker_01",
        recorded_at=START + timedelta(seconds=2),
    )
    sqlite_task = sqlite.ready_tasks(MISSION_ID)[0]
    sqlite_dispatch = sqlite.claim_task(
        MISSION_ID,
        sqlite_task.task_id,
        "worker_contract_1",
        "contract_sql_claim_0001",
        recorded_at=START + timedelta(seconds=3),
        ttl_seconds=30,
    )
    assert sqlite.claim_task(
        MISSION_ID,
        sqlite_task.task_id,
        "worker_contract_1",
        "contract_sql_claim_0001",
        recorded_at=START + timedelta(seconds=3),
        ttl_seconds=30,
    ) == sqlite_dispatch
    with pytest.raises(StaleWorker):
        sqlite.heartbeat(
            MISSION_ID,
            sqlite_dispatch.attempt_id,
            "worker_wrong_001",
            sqlite_dispatch.lease_id,
            sqlite_dispatch.fencing_token,
            "contract_sql_bad_owner1",
            recorded_at=START + timedelta(seconds=4),
            ttl_seconds=30,
        )
    with pytest.raises(StaleWorker):
        sqlite.heartbeat(
            MISSION_ID,
            sqlite_dispatch.attempt_id,
            sqlite_dispatch.worker_id,
            sqlite_dispatch.lease_id,
            sqlite_dispatch.fencing_token + 1,
            "contract_sql_bad_fence1",
            recorded_at=START + timedelta(seconds=4),
            ttl_seconds=30,
        )
    sqlite.heartbeat(
        MISSION_ID,
        sqlite_dispatch.attempt_id,
        sqlite_dispatch.worker_id,
        sqlite_dispatch.lease_id,
        sqlite_dispatch.fencing_token,
        "contract_sql_heartbeat1",
        recorded_at=START + timedelta(seconds=4),
        ttl_seconds=30,
    )
    sqlite.complete_attempt(
        MISSION_ID,
        sqlite_dispatch.attempt_id,
        sqlite_dispatch.worker_id,
        sqlite_dispatch.lease_id,
        sqlite_dispatch.fencing_token,
        AttemptResult(
            succeeded=False, result_code="provider_unavailable", stage="model"
        ),
        "contract_sql_complete01",
        recorded_at=START + timedelta(seconds=5),
        retry_backoff_seconds=0,
    )

    client = Client()
    clock = Clock(START)
    cloud = FirestoreMissionStore(client, namespace="contract", clock=clock)
    cloud.initialize_namespace_schema()
    cloud_created = cloud.create_mission(
        policy,
        mission,
        plan,
        "contract_fs_create_001",
        recorded_at=START,
    )
    cloud_approved = cloud.approve_plan(
        MISSION_ID,
        "contract_fs_approve_01",
        expected_revision=1,
        expected_head=cloud_created,
        operator_label="contract-fixture",
        rationale="normalized backend contract",
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        recorded_at=START + timedelta(seconds=1),
    )
    with pytest.raises(MissionConflict):
        cloud.approve_plan(
            MISSION_ID,
            "contract_fs_stale_0001",
            expected_revision=1,
            expected_head=cloud_created,
            operator_label="contract-fixture",
            rationale="stale head must fail",
            truth_kind=TruthKind.SIMULATED_FIXTURE,
            recorded_at=START + timedelta(seconds=1),
        )
    cloud.refresh_ready(
        MISSION_ID,
        "contract_fs_ready_0001",
        recorded_at=START + timedelta(seconds=2),
    )
    cloud_ready_head = cloud.head(MISSION_ID)
    cloud.register_executor_session(
        MISSION_ID,
        cloud_ready_head,
        "contract_fs_session_001",
        principal="contract-principal",
        executor_id="executor_contract_1",
        session_id="session_contract_01",
        worker_ids=("worker_contract_1",),
        capabilities=(TaskKind.WORK,),
    )
    clock.value = START + timedelta(seconds=3)
    cloud_dispatch = cloud.claim_dispatch(
        MISSION_ID,
        cloud_ready_head,
        "contract_fs_claim_0001",
        executor_id="executor_contract_1",
        session_id="session_contract_01",
        worker_id="worker_contract_1",
    )
    assert cloud_dispatch is not None
    assert cloud_dispatch.task_id == sqlite_dispatch.task_id
    assert cloud.claim_dispatch(
        MISSION_ID,
        cloud_ready_head,
        "contract_fs_claim_0001",
        executor_id="executor_contract_1",
        session_id="session_contract_01",
        worker_id="worker_contract_1",
    ) == cloud_dispatch
    cloud_claimed_head = cloud.head(MISSION_ID)
    clock.value = START + timedelta(seconds=4)
    with pytest.raises(ExecutorSessionRejected):
        cloud.heartbeat_dispatch(
            MISSION_ID,
            cloud_dispatch.attempt_id,
            cloud_claimed_head,
            "contract_fs_bad_owner1",
            executor_id="executor_contract_1",
            session_id="session_contract_01",
            worker_id="worker_wrong_001",
            lease_id=cloud_dispatch.lease.lease_id,
            fencing_token=cloud_dispatch.lease.fencing_token,
        )
    with pytest.raises(LeaseFenceRejected):
        cloud.heartbeat_dispatch(
            MISSION_ID,
            cloud_dispatch.attempt_id,
            cloud_claimed_head,
            "contract_fs_bad_fence1",
            executor_id="executor_contract_1",
            session_id="session_contract_01",
            worker_id="worker_contract_1",
            lease_id=cloud_dispatch.lease.lease_id,
            fencing_token=cloud_dispatch.lease.fencing_token + 1,
        )
    cloud.heartbeat_dispatch(
        MISSION_ID,
        cloud_dispatch.attempt_id,
        cloud_claimed_head,
        "contract_fs_heartbeat1",
        executor_id="executor_contract_1",
        session_id="session_contract_01",
        worker_id="worker_contract_1",
        lease_id=cloud_dispatch.lease.lease_id,
        fencing_token=cloud_dispatch.lease.fencing_token,
    )
    cloud_heartbeat_head = cloud.head(MISSION_ID)
    clock.value = START + timedelta(seconds=5)
    cloud.complete_dispatch(
        MISSION_ID,
        cloud_dispatch.attempt_id,
        cloud_heartbeat_head,
        "contract_fs_complete_01",
        executor_id="executor_contract_1",
        session_id="session_contract_01",
        worker_id="worker_contract_1",
        lease_id=cloud_dispatch.lease.lease_id,
        fencing_token=cloud_dispatch.lease.fencing_token,
        result=AttemptResult(
            succeeded=False,
            result_code="provider_unavailable",
            session_id="session_contract_01",
            invocation_id="invocation_contract_1",
            stage="model",
        ),
        retry_backoff_seconds=0,
    )

    def normalized(snapshot: MissionSnapshot, task_id: str) -> dict[str, object]:
        task = next(item for item in snapshot.tasks if item.task_id == task_id)
        attempt = next(item for item in snapshot.attempts if item.task_id == task_id)
        lease_value = next(item for item in snapshot.leases if item.task_id == task_id)
        return {
            "attempt_state": attempt.state,
            "lease_released": lease_value.release_reason,
            "mission_status": snapshot.mission.status,
            "task_state": task.state,
        }

    assert normalized(
        sqlite.snapshot(MISSION_ID), sqlite_dispatch.task_id
    ) == normalized(cloud.snapshot(MISSION_ID), cloud_dispatch.task_id) == {
        "attempt_state": AttemptState.FAILED,
        "lease_released": "failed",
        "mission_status": MissionStatus.FAILED,
        "task_state": TaskState.FAILED,
    }
    required_events = {
        MissionEventType.PLAN_APPROVED,
        MissionEventType.TASK_READY,
        MissionEventType.TASK_LEASED,
        MissionEventType.TASK_STARTED,
        MissionEventType.TASK_HEARTBEAT,
        MissionEventType.TASK_FAILED,
    }
    assert required_events <= {
        event.event_type for event in sqlite.tail(MISSION_ID, 0, 256)
    }
    assert required_events <= {
        event.event_type for event in cloud.tail(MISSION_ID, 0, 256)
    }

    # Two implementations build this payload — store.py inline and the shared
    # `reduce_failed_completion` the cloud path uses. A stage the runner knew
    # must survive both, or `why` answers differently depending on which
    # scheduler ran the mission.
    def failure_stage(events) -> list[object]:
        return [
            event.payload.get("stage")
            for event in events
            if event.event_type == MissionEventType.TASK_FAILED
        ]

    assert failure_stage(sqlite.tail(MISSION_ID, 0, 256)) == ["model"]
    assert failure_stage(cloud.tail(MISSION_ID, 0, 256)) == ["model"]
    assert sqlite_approved.seq > sqlite_created.seq
    assert cloud_approved.seq > cloud_created.seq


def test_authoritative_claim_requires_v2_input_locality_owned_by_executor():
    client = Client()
    clock = Clock(START + timedelta(seconds=2))
    store = FirestoreMissionStore(
        client, namespace="locality", clock=clock, allow_test_bootstrap=True
    )
    event = store.append(
        MISSION_ID,
        empty_head(),
        "command_locality_event1",
        draft("created"),
    )
    current = head(event)
    base = domain_snapshot(current)
    producer = next(item for item in base.tasks if item.task_id == "redact_notes")
    consumer = next(item for item in base.tasks if item.task_id == "wire_cli")
    requirement = consumer.inputs[0]
    producer = producer.model_copy(update={"state": TaskState.DONE})
    consumer = consumer.model_copy(
        update={
            "dependencies": (producer.task_id,),
            "inputs": (requirement,),
            "state": TaskState.READY,
        }
    )
    artifact = ArtifactEnvelopeReferenceV2(
        schema_version=2,
        artifact_id="artifact_locality_v2_1",
        producer_task_id=producer.task_id,
        output_name=requirement.name,
        kind=requirement.kind,
        media_type="application/vnd.graphene.patch",
        byte_count=32,
        content_sha256="b" * 64,
        artifact_envelope_sha256="c" * 64,
    )
    publication = ArtifactPublication(
        publication_id="publication_locality_v2_1",
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id=producer.task_id,
        attempt_id="attempt_locality_producer_1",
        output_name=requirement.name,
        kind=requirement.kind,
        sha256=artifact.content_sha256,
        artifact=artifact,
        paths=producer.expected_outputs[0].paths,
        state=PublicationState.ACCEPTED,
        consumers=(consumer.task_id,),
    )
    tasks = {
        item.task_id: item.model_copy(update={"state": TaskState.QUEUED})
        for item in base.tasks
    }
    tasks[producer.task_id] = producer
    tasks[consumer.task_id] = consumer
    values = {
        **base.model_dump(mode="json", exclude={"snapshot_sha256"}),
        "mission": base.mission.model_copy(
            update={"status": MissionStatus.RUNNING}
        ).model_dump(mode="json"),
        "tasks": [tasks[key].model_dump(mode="json") for key in sorted(tasks)],
        "publications": [publication.model_dump(mode="json")],
    }
    store.save_snapshot(
        MissionSnapshot.model_validate(
            {**values, "snapshot_sha256": canonical_json_sha256(values)}
        )
    )
    published_reference = publication.published_reference()
    locality_path = (
        f"locality_missions/{MISSION_ID}/artifact_locality/publication_"
        + canonical_json_sha256(published_reference.model_dump(mode="json"))
    )
    client.documents[locality_path] = {
        "schema_version": 2,
        "attempt_id": publication.attempt_id,
        "executor_id": "executor_other_1",
        "reference": published_reference.model_dump(mode="json"),
    }
    store.register_executor_session(
        MISSION_ID,
        current,
        "command_locality_session1",
        principal="locality-principal",
        executor_id="executor_locality_1",
        session_id="session_locality_1",
        worker_ids=("worker_locality_1",),
        capabilities=(TaskKind.WORK,),
    )
    assert store.claim_dispatch(
        MISSION_ID,
        current,
        "command_locality_wrong_01",
        executor_id="executor_locality_1",
        session_id="session_locality_1",
        worker_id="worker_locality_1",
    ) is None

    client.documents[locality_path]["executor_id"] = "executor_locality_1"
    dispatch = store.claim_dispatch(
        MISSION_ID,
        current,
        "command_locality_owner_01",
        executor_id="executor_locality_1",
        session_id="session_locality_1",
        worker_id="worker_locality_1",
    )
    assert dispatch is not None
    assert dispatch.accepted_inputs == (published_reference,)
    assert isinstance(dispatch.accepted_inputs[0], PublishedArtifactReferenceV2)


def lease(
    lease_id: str,
    fencing_token: int,
    issued_at: datetime,
    *,
    released_at: datetime | None = None,
) -> Lease:
    return Lease(
        lease_id=lease_id,
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id="redact_notes",
        attempt_id=f"attempt_{fencing_token}",
        owner=f"worker_{fencing_token}",
        write_paths=("status_report/redact.py", "tests/test_redact.py"),
        fencing_token=fencing_token,
        issued_at=issued_at,
        heartbeat_at=issued_at,
        expires_at=issued_at + timedelta(seconds=30),
        released_at=released_at,
        release_reason="completed" if released_at else None,
    )


def test_append_is_retry_safe_idempotent_and_uses_an_indexed_tail():
    client = Client()
    client.retry_once = True
    store = FirestoreMissionStore(
        client, namespace="test", clock=lambda: START, allow_test_bootstrap=True
    )
    request = draft("created")

    event = store.append(MISSION_ID, empty_head(), "command_event_0001", request)
    committed = deepcopy(client.documents)

    assert (
        store.append(MISSION_ID, empty_head(), "command_event_0001", request) == event
    )
    assert client.documents == committed
    assert len(client.transaction_attempts) == 3
    assert store.head(MISSION_ID) == head(event)
    assert store.tail(MISSION_ID, after_seq=0, limit=1) == (event,)
    assert client.queries[-1] == {
        "path": f"test_missions/{MISSION_ID}/events",
        "field": "seq",
        "operator": ">",
        "value": 0,
        "order": "seq",
        "limit": 1,
    }
    assert client.full_collection_streams == []

    with pytest.raises(MissionConflict, match="another request"):
        store.append(
            MISSION_ID,
            empty_head(),
            "command_event_0001",
            draft("different"),
        )


def test_materialized_snapshot_poll_reads_one_root_and_five_bounded_shards():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(
        client, namespace="test", clock=clock, allow_test_bootstrap=True
    )
    event = store.append(
        MISSION_ID, empty_head(), "command_event_0002", draft("created")
    )
    expected = domain_snapshot(head(event))

    assert store.save_snapshot(expected) == expected
    client.document_reads.clear()
    assert store.snapshot(MISSION_ID) == expected
    assert store.snapshot(MISSION_ID) == expected

    mission_projection = MissionProjection(store)
    projection = mission_projection.snapshot(MISSION_ID)
    assert mission_projection.snapshot(MISSION_ID) == projection
    assert projection.mission.mission_id == MISSION_ID
    assert projection.head.seq == expected.head.seq

    first_read = client.document_reads[:9]
    assert first_read[:3] == [
        "test_system/schema",
        f"test_missions/{MISSION_ID}",
        f"test_missions/{MISSION_ID}/materialized/current",
    ]
    assert "/state_roots/" in first_read[3]
    assert all("/state_records/" in path for path in first_read[4:])
    assert client.queries[-1]["value"] == 0
    assert 1 <= client.queries[-1]["limit"] <= 256
    assert len(client.queries) == 1
    assert client.full_collection_streams == []

    clock.value = START + timedelta(seconds=1)
    claimed = lease("lease_materialized_1", 1, START + timedelta(seconds=1))
    store.claim_lease(claimed, "command_claim_view1")
    queries_before_lease_updates = len(client.queries)
    assert store.snapshot(MISSION_ID) == expected
    assert mission_projection.snapshot(MISSION_ID) == projection

    clock.value = START + timedelta(seconds=2)
    heartbeat = Lease.model_validate(
        {
            **claimed.model_dump(mode="json"),
            "heartbeat_at": (START + timedelta(seconds=2)).isoformat(),
            "expires_at": (START + timedelta(seconds=41)).isoformat(),
        }
    )
    store.heartbeat_lease(heartbeat, "command_heartbeat_view1")
    clock.value = START + timedelta(seconds=3)
    released = Lease.model_validate(
        {
            **heartbeat.model_dump(mode="json"),
            "released_at": (START + timedelta(seconds=3)).isoformat(),
            "release_reason": "completed",
        }
    )
    store.release_lease(released, "command_release_view1")
    assert store.snapshot(MISSION_ID) == expected
    assert mission_projection.snapshot(MISSION_ID) == projection
    assert len(client.queries) == queries_before_lease_updates

    store.append(
        MISSION_ID,
        head(event),
        "command_event_0005",
        draft("advanced", MissionEventType.PLAN_PROPOSED),
    )
    with pytest.raises(MissionStateInvalid, match="not materialized"):
        store.snapshot(MISSION_ID)


def test_oversized_materialized_snapshot_is_rejected_before_a_write(monkeypatch):
    client = Client()
    store = FirestoreMissionStore(
        client, namespace="test", clock=lambda: START, allow_test_bootstrap=True
    )
    assert firestore_module._MAX_STATE_DOCUMENT_BYTES < 1_048_576
    monkeypatch.setattr(firestore_module, "_MAX_STATE_DOCUMENT_BYTES", 1)

    with pytest.raises(ValueError, match="shard exceeds its bound"):
        store.save_snapshot(domain_snapshot(empty_head()))
    assert client.transaction_attempts == []


def test_namespace_schema_is_created_once_and_incompatibility_fails_closed():
    client = Client()
    store = FirestoreMissionStore(
        client, namespace="test", clock=lambda: START, allow_test_bootstrap=True
    )
    event = store.append(
        MISSION_ID, empty_head(), "command_schema_event_1", draft("created")
    )
    schema_path = "test_system/schema"
    assert client.documents[schema_path] == {
        "schema_version": 1,
        "current_version": 2,
        "min_reader_version": 2,
        "min_writer_version": 2,
    }
    assert store.namespace_schema().current_version == 2

    client.documents[schema_path] = {
        **client.documents[schema_path],
        "current_version": 3,
        "min_reader_version": 3,
        "min_writer_version": 3,
    }
    with pytest.raises(MissionStateInvalid, match="schema is incompatible"):
        store.head(MISSION_ID)
    with pytest.raises(MissionStateInvalid, match="schema is incompatible"):
        store.save_snapshot(domain_snapshot(head(event)))


def test_namespace_schema_administrative_initialization_is_exact_and_idempotent():
    client = Client()
    store = FirestoreMissionStore(client, namespace="admin", clock=lambda: START)

    first = store.initialize_namespace_schema()
    second = store.initialize_namespace_schema()
    assert first == second == store.namespace_schema()
    assert client.documents == {
        "admin_system/schema": {
            "schema_version": 1,
            "current_version": 2,
            "min_reader_version": 2,
            "min_writer_version": 2,
        }
    }


def test_reconciler_finalizes_only_a_head_bound_canonical_root_and_is_idempotent():
    client = Client()
    store = FirestoreMissionStore(
        client, namespace="test", clock=lambda: START, allow_test_bootstrap=True
    )
    event = store.append(
        MISSION_ID, empty_head(), "command_reconcile_event1", draft("created")
    )
    expected = domain_snapshot(head(event))
    store.save_snapshot(expected)
    pointer_path = f"test_missions/{MISSION_ID}/materialized/current"
    finalized = deepcopy(client.documents[pointer_path])
    client.documents[pointer_path] = {
        **finalized,
        "materialization_pending": True,
        "target_root_sha256": finalized["root_sha256"],
    }

    with pytest.raises(MissionStateInvalid, match="not materialized"):
        store.snapshot(MISSION_ID)
    assert store.reconcile_materialization(MISSION_ID) == expected
    assert store.reconcile_materialization(MISSION_ID) == expected
    assert client.documents[pointer_path] == finalized

    client.documents[pointer_path] = {
        **finalized,
        "materialization_pending": True,
        "target_root_sha256": finalized["root_sha256"],
    }
    root_path = (
        f"test_missions/{MISSION_ID}/state_roots/{finalized['root_sha256']}"
    )
    shard_sha256 = client.documents[root_path]["shards"][0]["shard_sha256"]
    shard_path = f"test_missions/{MISSION_ID}/state_records/{shard_sha256}"
    client.documents[shard_path]["value"]["mission"]["goal"] = "diverged"
    with pytest.raises(MissionStateInvalid, match="canonical state shard"):
        store.reconcile_materialization(MISSION_ID)


def test_reconciler_rejects_event_only_pending_state_without_canonical_aggregate():
    client = Client()
    store = FirestoreMissionStore(
        client, namespace="test", clock=lambda: START, allow_test_bootstrap=True
    )
    event = store.append(
        MISSION_ID, empty_head(), "command_pending_event_1", draft("created")
    )
    store.save_snapshot(domain_snapshot(head(event)))
    store.append(
        MISSION_ID,
        head(event),
        "command_pending_event_2",
        draft("advanced", MissionEventType.PLAN_PROPOSED),
    )

    with pytest.raises(MissionStateInvalid, match="no canonical repair root"):
        store.reconcile_materialization(MISSION_ID)


def test_reconciler_rejects_a_missing_event_before_trusting_state_records():
    client = Client()
    store = FirestoreMissionStore(
        client, namespace="test", clock=lambda: START, allow_test_bootstrap=True
    )
    event = store.append(
        MISSION_ID, empty_head(), "command_reconcile_gap_1", draft("created")
    )
    store.save_snapshot(domain_snapshot(head(event)))
    del client.documents[f"test_missions/{MISSION_ID}/events/{event.seq:020d}"]

    with pytest.raises(MissionStateInvalid, match="history is not contiguous"):
        store.reconcile_materialization(MISSION_ID)


def test_bare_append_is_retired_from_the_production_adapter():
    client = Client()
    store = FirestoreMissionStore(client, namespace="test", clock=lambda: START)

    with pytest.raises(DomainTransitionUnavailable, match="canonical next aggregate"):
        store.append(
            MISSION_ID,
            empty_head(),
            "command_production_bare_append",
            draft("created"),
        )
    with pytest.raises(DomainTransitionUnavailable, match="bootstrap primitive"):
        store.save_snapshot(domain_snapshot(empty_head()))
    assert client.documents == {}


def test_fencing_token_supersedes_a_released_worker_and_guards_append():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(
        client, namespace="test", clock=clock, allow_test_bootstrap=True
    )
    first_event = store.append(
        MISSION_ID, empty_head(), "command_event_0003", draft("created")
    )
    lease_one = lease("lease_0001", 1, START + timedelta(seconds=1))

    clock.value = START + timedelta(seconds=1)
    assert store.claim_lease(lease_one, "command_claim_0001") == lease_one
    assert store.claim_lease(lease_one, "command_claim_0001") == lease_one
    released = lease(
        "lease_0001",
        1,
        START + timedelta(seconds=1),
        released_at=START + timedelta(seconds=10),
    )
    clock.value = START + timedelta(seconds=10)
    assert store.release_lease(released, "command_release_01") == released

    lease_two = lease("lease_0002", 2, START + timedelta(seconds=11))
    clock.value = START + timedelta(seconds=11)
    assert store.claim_lease(lease_two, "command_claim_0002") == lease_two
    clock.value = START + timedelta(seconds=12)
    with pytest.raises(LeaseFenceRejected, match="not current"):
        store.assert_fence(lease_one)
    store.assert_fence(lease_two)

    publication = draft(
        "accepted-digest",
        MissionEventType.ARTIFACT_PUBLISHED,
        payload={
            "attempt_id": lease_two.attempt_id,
            "label": "accepted-digest",
            "task_id": lease_two.task_id,
        },
    )
    stale_publication = draft(
        "accepted-digest",
        MissionEventType.ARTIFACT_PUBLISHED,
        payload={
            "attempt_id": lease_one.attempt_id,
            "label": "accepted-digest",
            "task_id": lease_one.task_id,
        },
    )
    clock.value = START + timedelta(seconds=12)
    unbound_publication = draft(
        "accepted-digest",
        MissionEventType.ARTIFACT_PUBLISHED,
        payload={
            "attempt_id": "attempt_other",
            "label": "accepted-digest",
            "task_id": lease_two.task_id,
        },
    )
    with pytest.raises(LeaseFenceRejected, match="not bound"):
        store.append(
            MISSION_ID,
            head(first_event),
            "command_effect_bad",
            unbound_publication,
            lease=lease_two,
        )
    with pytest.raises(LeaseFenceRejected, match="not current"):
        store.append(
            MISSION_ID,
            head(first_event),
            "command_effect_001",
            stale_publication,
            lease=lease_one,
        )
    assert store.head(MISSION_ID) == head(first_event)

    committed = store.append(
        MISSION_ID,
        head(first_event),
        "command_effect_002",
        publication,
        lease=lease_two,
    )
    assert committed.seq == 2
    excessive_heartbeat = Lease.model_validate(
        {
            **lease_two.model_dump(mode="json"),
            "heartbeat_at": (START + timedelta(seconds=12)).isoformat(),
            "expires_at": (START + timedelta(seconds=600)).isoformat(),
        }
    )
    with pytest.raises(LeaseFenceRejected, match="TTL bound"):
        store.heartbeat_lease(excessive_heartbeat, "command_heartbeat_x")
    heartbeat = Lease.model_validate(
        {
            **lease_two.model_dump(mode="json"),
            "heartbeat_at": (START + timedelta(seconds=12)).isoformat(),
            "expires_at": (START + timedelta(seconds=60)).isoformat(),
        }
    )
    assert store.heartbeat_lease(heartbeat, "command_heartbeat_1") == heartbeat
    assert (
        store.append(
            MISSION_ID,
            head(first_event),
            "command_effect_002",
            publication,
            lease=heartbeat,
        )
        == committed
    )


def test_claim_rejects_an_active_or_skipped_fencing_token():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(
        client, namespace="test", clock=clock, allow_test_bootstrap=True
    )
    store.append(MISSION_ID, empty_head(), "command_event_0004", draft("created"))
    lease_one = lease("lease_1001", 1, START + timedelta(seconds=1))
    clock.value = START + timedelta(seconds=1)
    store.claim_lease(lease_one, "command_claim_1001")

    clock.value = START + timedelta(seconds=2)
    with pytest.raises(LeaseFenceRejected, match="active lease"):
        store.claim_lease(
            lease("lease_1002", 2, START + timedelta(seconds=2)),
            "command_claim_1002",
        )

    with pytest.raises(LeaseFenceRejected, match="server-current"):
        store.claim_lease(
            lease("lease_1003", 2, START + timedelta(seconds=100)),
            "command_claim_1003",
        )

    clock.value = START + timedelta(seconds=1_000)
    assert store.claim_lease(lease_one, "command_claim_1001") == lease_one


def test_transaction_retry_rechecks_the_fence_against_fresh_server_time():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(
        client, namespace="test", clock=clock, allow_test_bootstrap=True
    )
    created = store.append(
        MISSION_ID, empty_head(), "command_event_0007", draft("created")
    )
    active = lease("lease_retry_time", 1, START + timedelta(seconds=1))
    clock.value = START + timedelta(seconds=1)
    store.claim_lease(active, "command_claim_retry_time")

    store._clock = SequenceClock(  # noqa: SLF001 - injected retry clock seam
        START + timedelta(seconds=30),
        START + timedelta(seconds=32),
    )
    client.retry_once = True
    effect = draft(
        "late-effect",
        MissionEventType.ARTIFACT_PUBLISHED,
        payload={
            "attempt_id": active.attempt_id,
            "task_id": active.task_id,
        },
    )
    with pytest.raises(LeaseFenceRejected, match="not current and active"):
        store.append(
            MISSION_ID,
            head(created),
            "command_effect_retry_time",
            effect,
            lease=active,
        )
    assert store.head(MISSION_ID) == head(created)


def test_heartbeat_cannot_extend_a_lease_beyond_its_total_lifetime_bound():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(
        client,
        namespace="test",
        clock=clock,
        max_lease_seconds=30,
        allow_test_bootstrap=True,
    )
    store.append(MISSION_ID, empty_head(), "command_event_0006", draft("created"))
    claimed = lease("lease_lifetime_1", 1, START + timedelta(seconds=1))
    clock.value = START + timedelta(seconds=1)
    store.claim_lease(claimed, "command_claim_lifetime")

    clock.value = START + timedelta(seconds=10)
    extended = Lease.model_validate(
        {
            **claimed.model_dump(mode="json"),
            "heartbeat_at": (START + timedelta(seconds=10)).isoformat(),
            "expires_at": (START + timedelta(seconds=35)).isoformat(),
        }
    )
    with pytest.raises(LeaseFenceRejected, match="TTL bound"):
        store.heartbeat_lease(extended, "command_heartbeat_lifetime")


def cloud_dispatch(
    active: Lease,
    *,
    executor_id: str = "executor_1",
    accepted_inputs=(),
):
    return new_dispatch_record(
        mission_id=MISSION_ID,
        plan_revision=active.plan_revision,
        task_id=active.task_id,
        task_kind=TaskKind.WORK,
        attempt_id=active.attempt_id,
        attempt_number=1,
        executor_id=executor_id,
        worker_id=active.owner,
        session_id="session_cloud_1",
        lease=active,
        accepted_inputs=accepted_inputs,
        artifact_executor_id=executor_id,
        creation_seq=1,
    )


def running_cloud_snapshot(
    current: MissionHead, active: Lease, dispatch
) -> MissionSnapshot:
    snapshot = domain_snapshot(current)
    task = next(item for item in snapshot.tasks if item.task_id == active.task_id)
    running_task = task.model_copy(
        update={"attempt_count": 1, "state": TaskState.RUNNING}
    )
    attempt = Attempt(
        attempt_id=active.attempt_id,
        mission_id=MISSION_ID,
        plan_revision=active.plan_revision,
        task_id=active.task_id,
        attempt_number=1,
        worker_id=active.owner,
        workspace_id="workspace_cloud_1",
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        dispatch_command_id="dispatch_cloud_authority_1",
        state=AttemptState.RUNNING,
        started_at=active.issued_at,
        input_publications=dispatch.accepted_inputs,
    )
    values = {
        **snapshot.model_dump(mode="json", exclude={"snapshot_sha256"}),
        "attempts": [attempt.model_dump(mode="json")],
        "leases": [active.model_dump(mode="json")],
        "mission": snapshot.mission.model_copy(
            update={"status": MissionStatus.RUNNING}
        ).model_dump(mode="json"),
        "tasks": [
            (running_task if item.task_id == task.task_id else item).model_dump(
                mode="json"
            )
            for item in snapshot.tasks
        ],
    }
    return MissionSnapshot.model_validate(
        {**values, "snapshot_sha256": canonical_json_sha256(values)}
    )


def cloud_store():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(
        client, namespace="test", clock=clock, allow_test_bootstrap=True
    )
    event = store.append(
        MISSION_ID, empty_head(), "command_cloud_event_01", draft("created")
    )
    active = lease("lease_cloud_1", 1, START + timedelta(seconds=1))
    clock.value = START + timedelta(seconds=1)
    store.claim_lease(active, "command_cloud_lease_1")
    dispatch = cloud_dispatch(active)
    store.save_snapshot(running_cloud_snapshot(head(event), active, dispatch))
    store.register_executor_session(
        MISSION_ID,
        head(event),
        "command_cloud_session_1",
        principal="principal@example.invalid",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_ids=(active.owner, "worker_other"),
        capabilities=(TaskKind.WORK,),
    )
    return client, clock, store, head(event), active


def test_dispatch_outbox_lifecycle_is_owner_bound_idempotent_and_durable():
    client, clock, store, committed_head, active = cloud_store()
    dispatch = cloud_dispatch(active)

    reconnected = store.register_executor_session(
        MISSION_ID,
        committed_head,
        "command_cloud_session_2",
        principal="principal@example.invalid",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_ids=(active.owner, "worker_other"),
        capabilities=(TaskKind.WORK,),
    )
    assert reconnected.session_id == "session_cloud_1"

    assert (
        store.enqueue_dispatch(
            dispatch, committed_head, "command_cloud_enqueue_1"
        )
        == dispatch
    )
    committed = deepcopy(client.documents)
    assert (
        store.enqueue_dispatch(
            dispatch, committed_head, "command_cloud_enqueue_1"
        )
        == dispatch
    )
    assert client.documents == committed

    assert (
        store.claim_dispatch(
            MISSION_ID,
            committed_head,
            "command_cloud_claim_other",
            executor_id="executor_1",
            session_id="session_cloud_1",
            worker_id="worker_other",
        )
        is None
    )

    with pytest.raises(ExecutorSessionRejected, match="unavailable"):
        store.claim_dispatch(
            MISSION_ID,
            committed_head,
            "command_cloud_claim_bad",
            executor_id="executor_other",
            session_id="session_cloud_1",
            worker_id=active.owner,
        )

    clock.value = START + timedelta(seconds=2)
    delivered = store.claim_dispatch(
        MISSION_ID,
        committed_head,
        "command_cloud_claim_01",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
    )
    assert delivered is not None
    assert delivered.state == DispatchOutboxState.DELIVERED
    assert delivered.delivery_count == 1
    assert (
        store.claim_dispatch(
            MISSION_ID,
            committed_head,
            "command_cloud_claim_01",
            executor_id="executor_1",
            session_id="session_cloud_1",
            worker_id=active.owner,
        )
        == delivered
    )

    redelivered = store.claim_dispatch(
        MISSION_ID,
        committed_head,
        "command_cloud_claim_02",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
    )
    assert redelivered is not None and redelivered.delivery_count == 2

    clock.value = START + timedelta(seconds=3)
    heartbeat = store.heartbeat_dispatch(
        MISSION_ID,
        active.attempt_id,
        committed_head,
        "command_cloud_heartbeat_1",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
    )
    assert heartbeat.lease.heartbeat_at == clock.value
    assert heartbeat.lease.expires_at > active.expires_at
    heartbeat_head = store.head(MISSION_ID)
    assert heartbeat_head.seq == committed_head.seq + 1
    assert store.tail(MISSION_ID, committed_head.seq)[0].event_type == (
        MissionEventType.TASK_HEARTBEAT
    )
    assert store.snapshot(MISSION_ID).head == heartbeat_head

    clock.value = START + timedelta(seconds=4)
    abandoned = store.abandon_dispatch(
        MISSION_ID,
        active.attempt_id,
        heartbeat_head,
        "command_cloud_abandon_1",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        result_code="executor_shutdown",
    )
    assert abandoned.state == DispatchOutboxState.ABANDONED
    outbox_path = f"test_missions/{MISSION_ID}/dispatch_outbox/{active.attempt_id}"
    assert client.documents[outbox_path]["state"] == "abandoned"
    session_path = f"test_missions/{MISSION_ID}/executor_sessions/session_cloud_1"
    assert client.documents[session_path]["value"]["queued_attempt_ids"] == []


def test_failed_completion_commits_domain_event_snapshot_outbox_and_command_atomically():
    client, clock, store, committed_head, active = cloud_store()
    dispatch = cloud_dispatch(active)
    store.enqueue_dispatch(dispatch, committed_head, "command_cloud_enqueue_failure")
    clock.value = START + timedelta(seconds=2)
    delivered = store.claim_dispatch(
        MISSION_ID,
        committed_head,
        "command_cloud_claim_failure",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
    )
    assert delivered is not None
    result = AttemptResult(
        succeeded=False,
        result_code="provider_unavailable",
        session_id="session_cloud_1",
        invocation_id="invocation_cloud_1",
    )

    completed = store.complete_dispatch(
        MISSION_ID,
        active.attempt_id,
        committed_head,
        "command_cloud_complete_failure",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        result=result,
        retry_backoff_seconds=0,
    )

    assert completed.state == DispatchOutboxState.COMPLETED
    transaction_writes = client.transaction_attempts[-1]
    assert store.complete_dispatch(
        MISSION_ID,
        active.attempt_id,
        committed_head,
        "command_cloud_complete_failure",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        result=result,
        retry_backoff_seconds=0,
    ) == completed
    snapshot = store.snapshot(MISSION_ID)
    assert snapshot.mission.status == MissionStatus.FAILED
    assert next(item for item in snapshot.tasks if item.task_id == active.task_id).state == TaskState.FAILED
    attempt = next(item for item in snapshot.attempts if item.attempt_id == active.attempt_id)
    assert (attempt.state, attempt.result_code, attempt.session_id) == (
        AttemptState.FAILED,
        result.result_code,
        result.session_id,
    )
    assert store.tail(MISSION_ID, committed_head.seq)[0].event_type == MissionEventType.TASK_FAILED
    assert any("/events/" in path for _action, path, _value in transaction_writes)
    assert any(path.endswith("/materialized/current") for _action, path, _value in transaction_writes)
    assert any("/state_roots/" in path for _action, path, _value in transaction_writes)
    assert sum(
        "/state_records/" in path for _action, path, _value in transaction_writes
    ) == 5
    pointer = client.documents[
        f"test_missions/{MISSION_ID}/materialized/current"
    ]
    assert "value" not in pointer
    assert pointer["root_sha256"] == pointer["target_root_sha256"]
    assert pointer["materialization_pending"] is False
    assert any("/dispatch_outbox/" in path for _action, path, _value in transaction_writes)


def test_completion_persists_every_reducer_event_without_a_fixed_truncation_cap(
    monkeypatch,
):
    client, clock, store, committed_head, active = cloud_store()
    store.enqueue_dispatch(
        cloud_dispatch(active), committed_head, "command_cloud_enqueue_large_events"
    )
    clock.value = START + timedelta(seconds=2)
    assert store.claim_dispatch(
        MISSION_ID,
        committed_head,
        "command_cloud_claim_large_events",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
    ) is not None
    original_reduce = firestore_module.reduce_failed_completion

    def expanded_reduce(*args, **kwargs):
        transition = original_reduce(*args, **kwargs)
        return transition.__class__(
            mission=transition.mission,
            tasks=transition.tasks,
            attempts=transition.attempts,
            leases=transition.leases,
            publications=transition.publications,
            drafts=transition.drafts * 193,
        )

    monkeypatch.setattr(firestore_module, "reduce_failed_completion", expanded_reduce)
    store.complete_dispatch(
        MISSION_ID,
        active.attempt_id,
        committed_head,
        "command_cloud_complete_large_events",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        result=AttemptResult(
            succeeded=False,
            result_code="provider_unavailable",
            session_id="session_cloud_1",
            invocation_id="invocation_cloud_large_events",
        ),
        retry_backoff_seconds=0,
    )

    events = store.tail(MISSION_ID, committed_head.seq, limit=256)
    assert len(events) == 193
    assert len({item.event_id for item in events}) == 193
    assert store.head(MISSION_ID).seq == committed_head.seq + 193


def test_success_completion_commits_publication_and_executor_locality_atomically():
    client, clock, store, committed_head, active = cloud_store()
    dispatch = cloud_dispatch(active)
    store.enqueue_dispatch(dispatch, committed_head, "command_cloud_enqueue_success")
    clock.value = START + timedelta(seconds=2)
    assert store.claim_dispatch(
        MISSION_ID,
        committed_head,
        "command_cloud_claim_success",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
    ) is not None
    before = store.snapshot(MISSION_ID)
    task = next(item for item in before.tasks if item.task_id == active.task_id)
    output = task.expected_outputs[0]
    output_bytes = b"cloud publication bytes"
    envelope = ArtifactEnvelopeV2.create(
        output_bytes,
        mission_id=MISSION_ID,
        plan_revision=active.plan_revision,
        plan_sha256=canonical_json_sha256(before.plan.model_dump(mode="json")),
        task_id=active.task_id,
        attempt_id=active.attempt_id,
        fencing_token=active.fencing_token,
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
        artifact_id="artifact_cloud_output_1",
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
        mission_id=MISSION_ID,
        task_id=active.task_id,
        attempt_id=active.attempt_id,
        plan_revision=active.plan_revision,
        fencing_token=active.fencing_token,
        policy_sha256=before.policy.policy_sha256,
        base_sha=before.policy.base_sha,
        runner_id="graphene_check_runner_v1",
        template_id=task.acceptance_checks[0],
        template_sha256="c" * 64,
        accepted_input_references=(),
        candidate_references=(envelope_reference,),
        candidate_tree_hash_version="graphene.tree.v2",
        candidate_tree_sha256="d" * 64,
        result_code="passed",
        exit_code=0,
        timed_out=False,
        output_sha256="e" * 64,
        output_truncated=False,
        cleanup_complete=True,
    )
    receipt_reference = EvidenceReference(
        kind="test-receipt",
        id="artifact_cloud_receipt_1",
        sha256=canonical_json_sha256(receipt.model_dump(mode="json")),
    )
    references = tuple(
        sorted((output_reference, receipt_reference), key=lambda item: (item.kind, item.id, item.sha256))
    )
    artifacts = (
        ExecutorArtifactObservation(
            reference=output_reference,
            byte_count=len(output_bytes),
            envelope=envelope,
        ),
        ExecutorArtifactObservation(
            reference=receipt_reference,
            byte_count=128,
        ),
    )
    result = AttemptResult(
        succeeded=True,
        result_code="passed",
        session_id="session_cloud_1",
        invocation_id="invocation_cloud_success_1",
        evidence_link=GenericEvidenceLink(evidence_id="evidence_cloud_success_1"),
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

    completed = store.complete_dispatch(
        MISSION_ID,
        active.attempt_id,
        committed_head,
        "command_cloud_complete_success",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        result=result,
        artifacts=artifacts,
        check_receipt=receipt,
    )
    completion_writes = client.transaction_attempts[-1]
    replayed = store.complete_dispatch(
        MISSION_ID,
        active.attempt_id,
        committed_head,
        "command_cloud_complete_success",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        result=result,
        artifacts=artifacts,
        check_receipt=receipt,
    )

    after = store.snapshot(MISSION_ID)
    assert replayed == completed
    assert tuple(item.reference for item in completed.artifacts) == references
    assert {item.executor_id for item in completed.artifacts} == {"executor_1"}
    assert next(item for item in after.tasks if item.task_id == active.task_id).state == TaskState.DONE
    assert next(item for item in after.attempts if item.attempt_id == active.attempt_id).state == AttemptState.COMMITTED
    assert len(after.publications) == 1
    writes = completion_writes
    locality_writes = tuple(
        value
        for _action, path, value in writes
        if "/artifact_locality/publication_" in path
    )
    assert len(locality_writes) == 1
    assert {item.event_type for item in store.tail(MISSION_ID, committed_head.seq)} >= {
        MissionEventType.ARTIFACT_PUBLISHED,
        MissionEventType.ARTIFACT_ACCEPTED,
        MissionEventType.TASK_COMPLETED,
    }
    publication = after.publications[0]
    assert locality_writes[0]["schema_version"] == 2
    assert locality_writes[0]["executor_id"] == "executor_1"
    assert locality_writes[0]["reference"] == publication.published_reference().model_dump(
        mode="json"
    )
    downstream_lease = Lease(
        lease_id="lease_cloud_downstream_1",
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id="wire_cli",
        attempt_id="attempt_cloud_downstream_1",
        owner="worker_other",
        write_paths=("status_report/cli.py", "tests/test_cli.py"),
        fencing_token=1,
        issued_at=clock.value,
        heartbeat_at=clock.value,
        expires_at=clock.value + timedelta(seconds=30),
    )
    store.claim_lease(downstream_lease, "command_cloud_downstream_lease")
    downstream = new_dispatch_record(
        mission_id=MISSION_ID,
        plan_revision=1,
        task_id=downstream_lease.task_id,
        task_kind=TaskKind.WORK,
        attempt_id=downstream_lease.attempt_id,
        attempt_number=1,
        executor_id="executor_1",
        worker_id=downstream_lease.owner,
        session_id="session_cloud_1",
        lease=downstream_lease,
        accepted_inputs=(
            EvidenceReference(
                kind=publication.kind,
                id=publication.publication_id,
                sha256=publication.sha256,
            ),
        ),
        artifact_executor_id="executor_1",
        creation_seq=after.head.seq,
    )
    store.enqueue_dispatch(
        downstream, after.head, "command_cloud_downstream_enqueue"
    )
    assert store.claim_dispatch(
        MISSION_ID,
        after.head,
        "command_cloud_downstream_claim",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id="worker_other",
    ) == downstream.model_copy(
        update={
            "delivery_count": 1,
            "last_delivery_at": clock.value,
            "state": DispatchOutboxState.DELIVERED,
            "history": (
                *downstream.history,
                downstream.history[0].model_copy(
                    update={
                        "state": DispatchOutboxState.DELIVERED,
                        "delivery_count": 1,
                    }
                ),
            ),
        }
    )


def test_artifact_capability_is_single_input_fenced_expiring_and_replay_safe():
    client, clock, store, committed_head, active = cloud_store()
    raw = b'{"safe":"context"}'
    reference = EvidenceReference(
        kind="context", id="artifact_context_1", sha256=sha256_hex(raw)
    )
    dispatch = cloud_dispatch(active, accepted_inputs=(reference,))
    store.enqueue_dispatch(dispatch, committed_head, "command_cloud_enqueue_cap")
    clock.value = START + timedelta(seconds=2)
    delivered = store.claim_dispatch(
        MISSION_ID,
        committed_head,
        "command_cloud_claim_cap1",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
    )
    assert delivered is not None and delivered.last_delivery_at is not None
    grant = ArtifactFetchGrant(
        capability_id="artifact_cap_0123456789abcdef0123456789abcdef",
        mission_id=MISSION_ID,
        dispatch_sha256=delivered.dispatch_sha256,
        delivery_count=delivered.delivery_count,
        attempt_id=active.attempt_id,
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        lease_id=active.lease_id,
        fencing_token=active.fencing_token,
        reference=reference,
        issued_at=delivered.last_delivery_at,
        expires_at=active.expires_at,
        token_sha256="b" * 64,
    )
    assert store.grant_artifact_fetch(grant, committed_head) == grant
    assert store.grant_artifact_fetch(grant, committed_head) == grant
    foreign = ArtifactFetchGrant.model_validate(
        {
            **grant.model_dump(mode="json"),
            "capability_id": "artifact_cap_ffffffffffffffffffffffffffffffff",
            "reference": {
                "kind": "context",
                "id": "artifact_foreign_1",
                "sha256": "f" * 64,
            },
        }
    )
    with pytest.raises(ArtifactCapabilityRejected, match="dispatch scope"):
        store.grant_artifact_fetch(foreign, committed_head)
    expiring = ArtifactFetchGrant.model_validate(
        {
            **grant.model_dump(mode="json"),
            "capability_id": "artifact_cap_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            "expires_at": (START + timedelta(seconds=4)).isoformat(),
            "token_sha256": "e" * 64,
        }
    )
    store.grant_artifact_fetch(expiring, committed_head)
    capability_path = (
        f"test_missions/{MISSION_ID}/artifact_capabilities/{grant.capability_id}"
    )
    assert "token" not in client.documents[capability_path]
    clock.value = START + timedelta(seconds=3)
    consumed = store.redeem_artifact_fetch(
        MISSION_ID,
        grant.capability_id,
        committed_head,
        "command_fetch_artifact_1",
        executor_id="executor_1",
        session_id="session_cloud_1",
        worker_id=active.owner,
        token_sha256=grant.token_sha256,
    )
    assert consumed.consumed_at == clock.value
    with pytest.raises(ArtifactCapabilityRejected, match="replay"):
        store.redeem_artifact_fetch(
            MISSION_ID,
            grant.capability_id,
            committed_head,
            "command_fetch_artifact_1",
            executor_id="executor_1",
            session_id="session_cloud_1",
            worker_id=active.owner,
            token_sha256=grant.token_sha256,
        )
    with pytest.raises(ArtifactCapabilityRejected, match="replay"):
        store.redeem_artifact_fetch(
            MISSION_ID,
            grant.capability_id,
            committed_head,
            "command_fetch_artifact_2",
            executor_id="executor_1",
            session_id="session_cloud_1",
            worker_id=active.owner,
            token_sha256=grant.token_sha256,
        )
    clock.value = START + timedelta(seconds=5)
    with pytest.raises(ArtifactCapabilityRejected, match="expired"):
        store.redeem_artifact_fetch(
            MISSION_ID,
            expiring.capability_id,
            committed_head,
            "command_fetch_expired_1",
            executor_id="executor_1",
            session_id="session_cloud_1",
            worker_id=active.owner,
            token_sha256=expiring.token_sha256,
        )


def test_dispatch_locality_is_enforced_and_has_a_durable_blocker():
    client, _clock, store, committed_head, active = cloud_store()
    dispatch = cloud_dispatch(active)
    foreign = new_dispatch_record(
        mission_id=MISSION_ID,
        plan_revision=active.plan_revision,
        task_id=active.task_id,
        task_kind=TaskKind.WORK,
        attempt_id=active.attempt_id,
        attempt_number=1,
        executor_id="executor_1",
        worker_id=active.owner,
        session_id="session_cloud_1",
        lease=active,
        accepted_inputs=(),
        artifact_executor_id="executor_other",
        creation_seq=1,
    )
    with pytest.raises(ArtifactLocalityUnavailable, match="another executor"):
        store.enqueue_dispatch(
            foreign, committed_head, "command_cloud_enqueue_bad"
        )

    store.enqueue_dispatch(dispatch, committed_head, "command_cloud_enqueue_2")
    blocked = store.block_artifact_locality(
        MISSION_ID,
        active.attempt_id,
        committed_head,
        "command_cloud_block_01",
        executor_id="executor_1",
    )
    assert blocked.state == DispatchOutboxState.BLOCKED
    assert blocked.blocker_code == "artifact_locality_unavailable"
    outbox_path = f"test_missions/{MISSION_ID}/dispatch_outbox/{active.attempt_id}"
    assert client.documents[outbox_path]["state"] == "blocked"
