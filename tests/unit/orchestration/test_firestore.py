from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import RLock

import graphene.orchestration.firestore as firestore_module
import pytest
from graphene.hashing import canonical_json_sha256
from graphene.models import TruthKind
from graphene.orchestration.firestore import (
    FirestoreMissionStore,
    LeaseFenceRejected,
    MissionConflict,
    MissionStateInvalid,
)
from graphene.orchestration.models import (
    Lease,
    MissionAuthority,
    MissionEventInput,
    MissionEventType,
    MissionHead,
    MissionSnapshot,
    ProjectPolicySummary,
)
from graphene.orchestration.projection import MissionProjection
from graphene.orchestration.scripted import load_scenario


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
    store = FirestoreMissionStore(client, namespace="test", clock=lambda: START)
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


def test_materialized_snapshot_poll_is_one_document_not_a_mission_scan():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(client, namespace="test", clock=clock)
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

    assert client.document_reads[:2] == [
        f"test_missions/{MISSION_ID}/materialized/current",
        f"test_missions/{MISSION_ID}/materialized/current",
    ]
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
    with pytest.raises(MissionStateInvalid, match="behind the committed"):
        store.snapshot(MISSION_ID)


def test_oversized_materialized_snapshot_is_rejected_before_a_write(monkeypatch):
    client = Client()
    store = FirestoreMissionStore(client, namespace="test", clock=lambda: START)
    assert firestore_module._MAX_MATERIALIZED_JSON_BYTES < 1_048_576
    monkeypatch.setattr(firestore_module, "_MAX_MATERIALIZED_JSON_BYTES", 1)

    with pytest.raises(ValueError, match="Firestore size bound"):
        store.save_snapshot(domain_snapshot(empty_head()))
    assert client.transaction_attempts == []


def test_fencing_token_supersedes_a_released_worker_and_guards_append():
    client = Client()
    clock = Clock(START)
    store = FirestoreMissionStore(client, namespace="test", clock=clock)
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
    store = FirestoreMissionStore(client, namespace="test", clock=clock)
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
    store = FirestoreMissionStore(client, namespace="test", clock=clock)
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
        client, namespace="test", clock=clock, max_lease_seconds=30
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
