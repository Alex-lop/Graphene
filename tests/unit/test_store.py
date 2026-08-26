from copy import deepcopy
from pathlib import Path

import pytest

from graphene.core_models import RunRecord, RunState, TaskId
from graphene import legacy_store as store_module
from graphene.legacy_store import FirestoreStore, IdempotencyConflict, JsonFileStore


def test_json_store_restarts_and_keeps_idempotency(tmp_path: Path):
    path = tmp_path / "graphene.json"
    run = RunRecord(
        run_id="run_1",
        task_id=TaskId.ADAPTED_WINDOW_SECONDS,
        repo_id="graphene-demo",
        state=RunState.QUEUED,
        revision=0,
    )

    first = JsonFileStore(path)
    assert first.create_run(run, "create_run_key_1", "a" * 64) == run

    restarted = JsonFileStore(path)
    assert restarted.get_run(run.run_id) == run
    assert restarted.create_run(run, "create_run_key_1", "a" * 64) == run
    with pytest.raises(IdempotencyConflict):
        restarted.create_run(run, "create_run_key_1", "b" * 64)


def test_firestore_store_restarts_and_keeps_idempotency(monkeypatch):
    class Snapshot:
        def __init__(self, data):
            self.exists = data is not None
            self._data = data

        def to_dict(self):
            return deepcopy(self._data)

    class Document:
        data = None

        def get(self, transaction=None):
            return Snapshot(deepcopy(self.data))

    class Transaction:
        def set(self, document, data):
            document.data = deepcopy(data)

    class Collection:
        def __init__(self, document):
            self._document = document

        def document(self, namespace):
            assert namespace == "test"
            return self._document

    class Client:
        def __init__(self):
            self.document = Document()

        def collection(self, name):
            assert name == "graphene_demo"
            return Collection(self.document)

        def transaction(self):
            return Transaction()

    monkeypatch.setattr(
        store_module.firestore,
        "transactional",
        lambda function: lambda transaction: function(transaction),
    )
    client = Client()
    run = RunRecord(
        run_id="run_firestore",
        task_id=TaskId.ADAPTED_WINDOW_SECONDS,
        repo_id="graphene-demo",
        state=RunState.QUEUED,
        revision=0,
    )

    first = FirestoreStore(client, "test")
    assert first.create_run(run, "create_run_key_1", "a" * 64) == run

    restarted = FirestoreStore(client, "test")
    assert restarted.get_run(run.run_id) == run
    assert restarted.create_run(run, "create_run_key_1", "a" * 64) == run
    with pytest.raises(IdempotencyConflict):
        restarted.create_run(run, "create_run_key_1", "b" * 64)
