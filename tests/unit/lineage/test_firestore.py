from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock

import graphene.lineage.firestore as firestore_module
import graphene.lineage.reducer as reducer_module
import pytest
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.lineage.firestore import FirestoreLineageStore
from graphene.lineage.store import EvidenceInvalid, LineageConflict
from graphene.models import (
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    HeadCheckpoint,
    LineageAuthority,
    LineageEventType,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

RUNS = "graphene_lineage_runs"
GLOBAL_EVENTS = "graphene_lineage_event_ids"


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
        with self.client.lock:
            return Snapshot(self, self.client.documents.get(self.path))


class Collection:
    def __init__(self, client, path):
        self.client = client
        self.path = path

    def document(self, document_id):
        return Document(self.client, f"{self.path}/{document_id}")

    def stream(self, transaction=None):
        if transaction is not None:
            return transaction.stream(self)
        with self.client.lock:
            return self.client.snapshots(self)


class Transaction:
    def __init__(self, client, *, read_only=False):
        self.client = client
        self.read_only = read_only
        self.writes = []
        self.operations = []

    def reset(self):
        self.writes = []
        self.operations = []

    def get(self, document):
        self.operations.append(("read", document.path))
        return Snapshot(document, self.client.documents.get(document.path))

    def stream(self, collection):
        self.operations.append(("read", collection.path))
        return self.client.snapshots(collection)

    def create(self, document, data):
        self.operations.append(("write", document.path))
        self.writes.append(("create", document.path, deepcopy(data)))

    def set(self, document, data):
        self.operations.append(("write", document.path))
        self.writes.append(("set", document.path, deepcopy(data)))

    def commit(self):
        if self.read_only and self.writes:
            raise AssertionError("read-only transaction attempted a write")
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
        self.attempt_writes = []
        self.attempt_operations = []
        self.streamed_collections = []

    def collection(self, name):
        return Collection(self, name)

    def transaction(self, read_only=False):
        return Transaction(self, read_only=read_only)

    def snapshots(self, collection):
        self.streamed_collections.append(collection.path)
        prefix = collection.path + "/"
        snapshots = []
        for path, data in self.documents.items():
            remainder = path.removeprefix(prefix)
            if path.startswith(prefix) and "/" not in remainder:
                snapshots.append(Snapshot(Document(self, path), data))
        return tuple(sorted(snapshots, key=lambda item: item.id))


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
                    transaction.client.attempt_writes.append(
                        deepcopy(transaction.writes)
                    )
                    transaction.client.attempt_operations.append(
                        tuple(transaction.operations)
                    )
                    if attempt == attempts - 1:
                        transaction.commit()
                return result

        return invoke

    monkeypatch.setattr(firestore_module.firestore, "transactional", transactional)


class Ledger:
    def __init__(self):
        self.records = {}

    def source(self, kind: SourceKind, record: dict[str, object]) -> SourceReference:
        raw = canonical_json_bytes(record)
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:24]}"
        self.records[(kind.value, artifact_id)] = raw
        return SourceReference(kind=kind, id=artifact_id, sha256=digest)

    def evidence(
        self,
        kind: EvidenceKind,
        record: dict[str, object],
    ) -> EvidenceReference:
        raw = canonical_json_bytes(record)
        digest = sha256_hex(raw)
        artifact_id = f"{kind.value}_{digest[:24]}"
        self.records[(kind.value, artifact_id)] = raw
        return EvidenceReference(kind=kind, id=artifact_id, sha256=digest)

    def resolve(self, kind: str, artifact_id: str) -> bytes | None:
        return self.records.get((kind, artifact_id))


def empty_head(run_id="run_firestore_001"):
    return VerifiedHead(run_id=run_id, seq=0, event_sha256=None, event_count=0)


def head(event):
    return VerifiedHead(
        run_id=event.run_id,
        seq=event.seq,
        event_sha256=event.event_sha256,
        event_count=event.seq,
    )


def draft(
    ledger: Ledger,
    label: str,
    *,
    event_type=LineageEventType.RUN_STARTED,
    repo_id="graphene-demo",
    references=(),
    payload=None,
    source_record=None,
):
    return EventInput(
        session_id=None,
        invocation_id=None,
        model_id=None,
        tool_call_id=None,
        repo_id=repo_id,
        base_sha="a" * 40,
        agent_profile_id="auth-maintainer@1",
        policy_revision=1,
        event_type=event_type,
        truth_kind=TruthKind.SERVER_DERIVED,
        authority=LineageAuthority.LIFECYCLE_SERVICE,
        references=references,
        source_ref=ledger.source(
            SourceKind.LIFECYCLE_REQUEST,
            source_record or {"schema_version": 2, "label": label},
        ),
        payload=payload or {"state": event_type.value},
    )


def store(client=None, ledger=None, *, checkpoint_reader=None):
    client = client or Client()
    ledger = ledger or Ledger()
    return (
        FirestoreLineageStore(
            client,
            artifact_resolver=ledger.resolve,
            checkpoint_reader=checkpoint_reader,
        ),
        client,
        ledger,
    )


def test_first_append_exact_replay_conflict_and_document_layout():
    lineage, client, ledger = store()
    run_id = "run_firestore_001"
    expected = empty_head(run_id)
    request = draft(ledger, "first")
    key = "firestore_append_001"

    event = lineage.append(run_id, expected, key, request)
    committed = deepcopy(client.documents)

    assert lineage.append(run_id, expected, key, request) == event
    assert client.documents == committed
    assert lineage.verify(run_id) == head(event)

    idempotency_digest = sha256_hex(key.encode())
    event_path = f"{RUNS}/{run_id}/events/{event.seq:020d}"
    idempotency_path = f"{RUNS}/{run_id}/idempotency/{idempotency_digest}"
    global_path = f"{GLOBAL_EVENTS}/{event.event_id}"
    assert set(client.documents) == {
        f"{RUNS}/{run_id}",
        event_path,
        idempotency_path,
        global_path,
    }
    assert set(client.documents[event_path]) == {
        "schema_version",
        "event_id",
        "run_id",
        "seq",
        "idempotency_sha256",
        "payload_sha256",
        "previous_event_sha256",
        "event_sha256",
        "event_bytes",
    }
    assert "request_bytes" not in repr(client.documents)
    assert key not in idempotency_path
    assert all("events" not in document for document in client.documents.values())
    assert "graphene_demo" not in client.documents

    changed = draft(ledger, "changed", payload={"state": "different"})
    with pytest.raises(LineageConflict, match="idempotency"):
        lineage.append(run_id, expected, key, changed)
    with pytest.raises(LineageConflict, match="expected head"):
        lineage.append(run_id, expected, "firestore_append_002", changed)


def test_shared_semantic_validator_runs_on_firestore_append_and_verify(monkeypatch):
    lineage, _, ledger = store()
    observed = []
    validate = reducer_module.validate_semantic_artifacts

    def observe(events, resolver):
        observed.append(tuple(event.event_id for event in events))
        validate(events, resolver)

    monkeypatch.setattr(reducer_module, "validate_semantic_artifacts", observe)
    event = lineage.append(
        "run_semantic_validator_001",
        empty_head("run_semantic_validator_001"),
        "semantic_validator_append_001",
        draft(ledger, "semantic-validator"),
    )
    assert observed == [(event.event_id,)]

    observed.clear()
    assert lineage.verify(event.run_id) == head(event)
    assert observed == [(event.event_id,)]


def test_interrupted_run_rejects_later_events_but_allows_exact_replay():
    lineage, _, ledger = store()
    run_id = "run_interrupted_001"
    first = lineage.append(
        run_id,
        empty_head(run_id),
        "interrupt_start_001",
        draft(ledger, "start"),
    )
    request = draft(
        ledger,
        "interrupted",
        event_type=LineageEventType.RUN_INTERRUPTED,
    )
    interrupted = lineage.append(
        run_id,
        head(first),
        "interrupt_event_001",
        request,
    )

    assert lineage.append(
        run_id,
        head(first),
        "interrupt_event_001",
        request,
    ) == interrupted
    with pytest.raises(LineageConflict, match="interrupted"):
        lineage.append(
            run_id,
            head(interrupted),
            "late_event_001",
            draft(ledger, "late", event_type=LineageEventType.RUN_FAILED),
        )
    assert lineage.tail(run_id, 0, 256) == (first, interrupted)


def test_transaction_retry_and_concurrent_exact_calls_are_stable(monkeypatch):
    lineage, client, ledger = store()
    run_id = "run_retry_001"
    expected = empty_head(run_id)
    request = draft(ledger, "retry")
    id_calls = 0
    time_calls = 0

    def event_id():
        nonlocal id_calls
        id_calls += 1
        return "event_retry_stable_001"

    def recorded_at():
        nonlocal time_calls
        time_calls += 1
        return datetime(2026, 8, 12, 18, 0, tzinfo=UTC)

    monkeypatch.setattr(firestore_module, "_new_event_id", event_id)
    monkeypatch.setattr(firestore_module, "_now", recorded_at)
    client.retry_once = True
    event = lineage.append(run_id, expected, "retry_stable_key_001", request)

    assert (id_calls, time_calls) == (1, 1)
    retry_writes = client.attempt_writes[:2]
    first_event_doc = next(
        data for _, path, data in retry_writes[0] if "/events/" in path
    )
    second_event_doc = next(
        data for _, path, data in retry_writes[1] if "/events/" in path
    )
    assert first_event_doc == second_event_doc
    for operations in client.attempt_operations[:2]:
        first_write = next(
            index for index, item in enumerate(operations) if item[0] == "write"
        )
        assert all(item[0] == "read" for item in operations[:first_write])
        assert all(item[0] == "write" for item in operations[first_write:])

    monkeypatch.setattr(
        firestore_module,
        "_new_event_id",
        lambda: f"event_concurrent_{len(client.documents):04d}",
    )

    second_request = draft(
        ledger,
        "second",
        event_type=LineageEventType.RUN_FAILED,
    )
    expected = head(event)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda _: lineage.append(
                    run_id,
                    expected,
                    "concurrent_exact_key_001",
                    second_request,
                ),
                range(2),
            )
        )
    assert results[0] == results[1]
    assert lineage.verify(run_id) == head(results[0])

    conflicting = draft(
        ledger,
        "conflict",
        event_type=LineageEventType.RUN_FAILED,
        payload={"state": "different"},
    )
    with pytest.raises(LineageConflict, match="idempotency"):
        lineage.append(
            run_id,
            expected,
            "concurrent_exact_key_001",
            conflicting,
        )


def test_restart_tail_and_per_event_documents():
    lineage, client, ledger = store()
    run_id = "run_restart_001"
    current = empty_head(run_id)
    events = []
    for number in range(1, 4):
        event = lineage.append(
            run_id,
            current,
            f"restart_event_key_{number:03d}",
            draft(
                ledger,
                f"event-{number}",
                event_type=(
                    LineageEventType.RUN_STARTED
                    if number == 1
                    else LineageEventType.MEMORY_PROPOSED
                ),
                payload=(None if number == 1 else {"status": "proposed"}),
            ),
        )
        events.append(event)
        current = head(event)

    restarted = FirestoreLineageStore(client, artifact_resolver=ledger.resolve)
    assert restarted.verify(run_id) == current
    assert restarted.tail(run_id, 1, 1) == (events[1],)
    assert restarted.tail(run_id, 1, 256) == tuple(events[1:])
    assert len([path for path in client.documents if "/events/" in path]) == 3
    assert f"{RUNS}/{run_id}/events/{1:020d}" in client.documents
    assert f"{RUNS}/{run_id}/events/{3:020d}" in client.documents
    assert "graphene_demo" not in client.streamed_collections
    with pytest.raises(ValueError, match="after_seq"):
        restarted.tail(run_id, True, 1)
    with pytest.raises(ValueError, match="limit"):
        restarted.tail(run_id, 0, 257)


@pytest.mark.parametrize(
    "tamper",
    (
        "gap",
        "event_metadata",
        "idempotency_document_id",
        "idempotency_schema",
        "idempotency_cross_run",
        "idempotency_request",
        "idempotency_event_id",
        "idempotency_event_seq",
        "idempotency_event_sha",
        "global_cross_run",
    ),
)
def test_corruption_gap_and_reciprocal_index_conflicts_fail_closed(tamper):
    lineage, client, ledger = store()
    run_id = "run_corrupt_001"
    first = lineage.append(
        run_id,
        empty_head(run_id),
        "corrupt_event_key_001",
        draft(ledger, "first"),
    )
    second_request = draft(
        ledger,
        "second",
        event_type=LineageEventType.RUN_FAILED,
    )
    second = lineage.append(
        run_id,
        head(first),
        "corrupt_event_key_002",
        second_request,
    )

    second_path = f"{RUNS}/{run_id}/events/{2:020d}"
    digest = sha256_hex(b"corrupt_event_key_002")
    idempotency_path = f"{RUNS}/{run_id}/idempotency/{digest}"
    if tamper == "gap":
        client.documents[f"{RUNS}/{run_id}/events/{3:020d}"] = client.documents.pop(
            second_path
        )
    elif tamper == "event_metadata":
        client.documents[second_path]["raw_content"] = "forbidden"
    elif tamper == "idempotency_document_id":
        client.documents[f"{RUNS}/{run_id}/idempotency/{'0' * 64}"] = (
            client.documents.pop(idempotency_path)
        )
    elif tamper == "idempotency_schema":
        client.documents[idempotency_path]["schema_version"] = 1
    elif tamper == "idempotency_cross_run":
        client.documents[idempotency_path]["run_id"] = "run_other_001"
    elif tamper == "idempotency_request":
        client.documents[idempotency_path]["request_sha256"] = "0" * 64
    elif tamper == "idempotency_event_id":
        client.documents[idempotency_path]["event_id"] = first.event_id
    elif tamper == "idempotency_event_seq":
        client.documents[idempotency_path]["event_seq"] = 1
    elif tamper == "idempotency_event_sha":
        client.documents[idempotency_path]["event_sha256"] = first.event_sha256
    else:
        client.documents[f"{GLOBAL_EVENTS}/{second.event_id}"]["run_id"] = (
            "run_other_001"
        )

    state = lineage.verify(run_id)
    assert isinstance(state, EvidenceInvalidState)
    with pytest.raises(EvidenceInvalid):
        lineage.tail(run_id, 0, 256)
    with pytest.raises(EvidenceInvalid):
        lineage.append(
            run_id,
            head(first),
            "corrupt_event_key_002",
            second_request,
        )


def test_global_event_id_collision_across_runs_is_rejected(monkeypatch):
    lineage, client, ledger = store()
    monkeypatch.setattr(
        firestore_module,
        "_new_event_id",
        lambda: "event_global_collision_001",
    )
    lineage.append(
        "run_collision_a",
        empty_head("run_collision_a"),
        "global_collision_key_001",
        draft(ledger, "first"),
    )

    restarted = FirestoreLineageStore(client, artifact_resolver=ledger.resolve)
    with pytest.raises(LineageConflict, match="uniqueness"):
        restarted.append(
            "run_collision_b",
            empty_head("run_collision_b"),
            "global_collision_key_002",
            draft(ledger, "second"),
        )
    assert restarted.verify("run_collision_b") == empty_head("run_collision_b")


def test_semantically_impossible_event_is_rejected_before_firestore_writes():
    lineage, client, ledger = store()
    run_id = "run_semantic_guard_001"
    first = lineage.append(
        run_id,
        empty_head(run_id),
        "semantic_start_key_001",
        draft(ledger, "first"),
    )
    source = ledger.source(
        SourceKind.TOOL_RECEIPT,
        {"schema_version": 2, "phase": "completed-without-start"},
    )
    malformed = EventInput(
        session_id="session_semantic_001",
        invocation_id="invocation_semantic_001",
        model_id="model-test",
        tool_call_id="tool_semantic_001",
        repo_id="graphene-demo",
        base_sha="a" * 40,
        agent_profile_id="auth-maintainer@1",
        policy_revision=1,
        event_type=LineageEventType.TOOL_COMPLETED,
        truth_kind=TruthKind.RUNTIME_OBSERVED,
        authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
        references=(),
        source_ref=source,
        payload={"operation": "search_repo", "paths": []},
    )
    before = deepcopy(client.documents)

    with pytest.raises(EvidenceInvalid, match="semantically invalid"):
        lineage.append(
            run_id,
            head(first),
            "semantic_result_key_001",
            malformed,
        )

    assert client.documents == before


def test_references_artifacts_and_checkpoints_are_verified():
    lineage, client, ledger = store()
    run_id = "run_checkpoint_001"
    first = lineage.append(
        run_id,
        empty_head(run_id),
        "checkpoint_event_key_001",
        draft(ledger, "first"),
    )
    event_reference = EvidenceReference(
        kind=EvidenceKind.EVENT,
        id=first.event_id,
        sha256=first.event_sha256,
    )
    second = lineage.append(
        run_id,
        head(first),
        "checkpoint_event_key_002",
        draft(
            ledger,
            "second",
            event_type=LineageEventType.RUN_FAILED,
            references=(event_reference,),
        ),
    )
    bound = ledger.evidence(
        EvidenceKind.EVIDENCE_BLOB,
        {"schema_version": 2, "receipt": "checkpoint"},
    )
    values = {
        "schema_version": 2,
        "checkpoint_id": "checkpoint_firestore_001",
        "run_id": run_id,
        "expected_seq": 2,
        "event_head_sha256": second.event_sha256,
        "purpose": "restart_proof",
        "bound_artifact_kind": bound.kind,
        "bound_artifact_id": bound.id,
        "bound_artifact_sha256": bound.sha256,
        "server_recorded_at": "2026-08-12T18:00:00Z",
    }
    checkpoint = HeadCheckpoint(
        **values,
        checkpoint_sha256=canonical_json_sha256(
            {
                **values,
                "bound_artifact_kind": bound.kind.value,
            }
        ),
    )
    checked = FirestoreLineageStore(
        client,
        artifact_resolver=ledger.resolve,
        checkpoint_reader=lambda candidate: (
            (checkpoint,) if candidate == run_id else ()
        ),
    )
    assert checked.verify(run_id) == head(second)

    del ledger.records[(bound.kind.value, bound.id)]
    assert isinstance(checked.verify(run_id), EvidenceInvalidState)

    with pytest.raises(EvidenceInvalid, match="reference"):
        lineage.append(
            "run_cross_reference",
            empty_head("run_cross_reference"),
            "cross_reference_key_001",
            draft(ledger, "cross", references=(event_reference,)),
        )


def test_payload_caps_and_private_artifact_canaries_never_reach_documents():
    lineage, client, ledger = store()
    run_id = "run_canary_001"
    work_canary = "RAW_WORK_CANARY_f31b"
    bearer_canary = "Bearer TOKEN_CANARY_9a7d"
    request = draft(
        ledger,
        "canary",
        source_record={
            "schema_version": 2,
            "raw_source": work_canary,
            "authorization": bearer_canary,
        },
    )

    lineage.append(
        run_id,
        empty_head(run_id),
        "canary_event_key_001",
        request,
    )

    persisted = repr(client.documents)
    assert work_canary not in persisted
    assert bearer_canary not in persisted
    assert all(
        forbidden not in document
        for document in client.documents.values()
        for forbidden in (
            "request_bytes",
            "raw_content",
            "diff",
            "prompt",
            "model_output",
            "stdout",
            "stderr",
            "token",
        )
    )
    committed = deepcopy(client.documents)

    with pytest.raises(ValueError, match="unsafe"):
        draft(ledger, "unsafe", payload={"stdout": work_canary})
    with pytest.raises(ValueError, match="byte cap"):
        draft(ledger, "large", payload={"note": "x" * 4_096})

    bypassed = EventInput.model_construct(
        **{
            **{name: getattr(request, name) for name in EventInput.model_fields},
            "payload": {"stdout": work_canary},
        }
    )
    with pytest.raises(ValueError, match="unsafe"):
        lineage.append(
            "run_bypassed_validation",
            empty_head("run_bypassed_validation"),
            "bypassed_validation_key_001",
            bypassed,
        )
    assert client.documents == committed
