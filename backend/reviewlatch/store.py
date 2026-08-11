from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from threading import RLock
from typing import Protocol

from google.cloud import firestore

from .models import (
    ContextPacket,
    FeedbackRecord,
    HumanDecision,
    InjectionReceipt,
    MEMORY_TRANSITIONS,
    MemoryRevision,
    MemoryState,
    RUN_TRANSITIONS,
    RunRecord,
    RunState,
)


class StoreConflict(RuntimeError):
    """A compare-and-set precondition failed."""


class IdempotencyConflict(RuntimeError):
    """An idempotency key was reused with a different request hash."""


class Store(Protocol):
    """Persistence contract shared by in-memory and Firestore stores.

    Mutations atomically bind operation + idempotency key to request hash and
    the original result. Run saves require ``new.revision == expected + 1``;
    promotion is exactly waiting -> promoting -> completed, so its receipt
    binds the final revision to the request's expected revision plus two.
    ``create_run`` accepts only queued revision zero; saves follow
    ``RUN_TRANSITIONS``. ``create_memory`` accepts only proposed revisions;
    ``decide_memory`` follows ``MEMORY_TRANSITIONS`` without rewriting content.
    Memory revisions are append-only and exact revisions remain readable.
    """

    def reset_demo(
        self, idempotency_key: str, request_sha256: str
    ) -> None: ...

    def list_runs(self) -> tuple[RunRecord, ...]: ...

    def get_run(self, run_id: str) -> RunRecord | None: ...

    def create_run(
        self, run: RunRecord, idempotency_key: str, request_sha256: str
    ) -> RunRecord: ...

    def save_run(
        self,
        run: RunRecord,
        expected_revision: int,
        idempotency_key: str,
        request_sha256: str,
    ) -> RunRecord: ...

    def get_memory(
        self, memory_id: str, revision: int
    ) -> MemoryRevision | None: ...

    def list_approved_memories(self, repo_id: str) -> tuple[MemoryRevision, ...]: ...

    def create_memory(
        self,
        memory: MemoryRevision,
        idempotency_key: str,
        request_sha256: str,
    ) -> MemoryRevision: ...

    def decide_memory(
        self,
        memory_id: str,
        expected_revision: int,
        decision: HumanDecision,
        idempotency_key: str,
        request_sha256: str,
    ) -> MemoryRevision: ...

    def get_feedback(self, feedback_id: str) -> FeedbackRecord | None: ...

    def create_feedback(
        self,
        feedback: FeedbackRecord,
        idempotency_key: str,
        request_sha256: str,
    ) -> FeedbackRecord: ...

    def get_context_packet(self, run_id: str) -> ContextPacket | None: ...

    def create_context_packet(
        self,
        packet: ContextPacket,
        idempotency_key: str,
        request_sha256: str,
    ) -> ContextPacket: ...

    def get_injection_receipt(self, run_id: str) -> InjectionReceipt | None: ...

    def create_injection_receipt(
        self,
        receipt: InjectionReceipt,
        idempotency_key: str,
        request_sha256: str,
    ) -> InjectionReceipt: ...


class InMemoryStore:
    """Small compare-and-set store used by the local vertical slice."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._runs: dict[str, RunRecord] = {}
        self._memories: dict[tuple[str, int], MemoryRevision] = {}
        self._feedback: dict[str, FeedbackRecord] = {}
        self._packets: dict[str, ContextPacket] = {}
        self._injections: dict[str, InjectionReceipt] = {}
        self._operations: dict[tuple[str, str], tuple[str, object]] = {}

    def _after_change(self) -> None:
        pass

    def _idempotent(self, operation: str, key: str, request_sha256: str, mutate):
        token = (operation, key)
        with self._lock:
            previous = self._operations.get(token)
            if previous is not None:
                if previous[0] != request_sha256:
                    raise IdempotencyConflict(f"idempotency key reused for {operation}")
                return previous[1]
            result = mutate()
            self._operations[token] = (request_sha256, result)
            self._after_change()
            return result

    def reset_demo(self, idempotency_key: str, request_sha256: str) -> None:
        token = ("reset_demo", idempotency_key)
        with self._lock:
            previous = self._operations.get(token)
            if previous is not None:
                if previous[0] != request_sha256:
                    raise IdempotencyConflict("idempotency key reused for reset_demo")
                return None
            self._runs.clear()
            self._memories.clear()
            self._feedback.clear()
            self._packets.clear()
            self._injections.clear()
            self._operations = {token: (request_sha256, None)}
            self._after_change()

    def list_runs(self) -> tuple[RunRecord, ...]:
        with self._lock:
            return tuple(sorted(self._runs.values(), key=lambda run: run.run_id))

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def create_run(
        self, run: RunRecord, idempotency_key: str, request_sha256: str
    ) -> RunRecord:
        def mutate() -> RunRecord:
            if run.run_id in self._runs or run.state != RunState.QUEUED or run.revision != 0:
                raise StoreConflict("run must be a new queued revision zero")
            self._runs[run.run_id] = run
            return run

        return self._idempotent("create_run", idempotency_key, request_sha256, mutate)

    def save_run(
        self,
        run: RunRecord,
        expected_revision: int,
        idempotency_key: str,
        request_sha256: str,
    ) -> RunRecord:
        def mutate() -> RunRecord:
            current = self._runs.get(run.run_id)
            if (
                current is None
                or current.revision != expected_revision
                or run.revision != expected_revision + 1
                or (current.state, run.state) not in RUN_TRANSITIONS
            ):
                raise StoreConflict("stale or illegal run transition")
            self._runs[run.run_id] = run
            return run

        return self._idempotent("save_run", idempotency_key, request_sha256, mutate)

    def get_memory(self, memory_id: str, revision: int) -> MemoryRevision | None:
        with self._lock:
            return self._memories.get((memory_id, revision))

    def list_approved_memories(self, repo_id: str) -> tuple[MemoryRevision, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        memory
                        for memory in self._memories.values()
                        if memory.repo_id == repo_id and memory.state == MemoryState.APPROVED
                    ),
                    key=lambda memory: (memory.memory_id, memory.revision),
                )
            )

    def create_memory(
        self,
        memory: MemoryRevision,
        idempotency_key: str,
        request_sha256: str,
    ) -> MemoryRevision:
        def mutate() -> MemoryRevision:
            key = (memory.memory_id, memory.revision)
            if key in self._memories or memory.state != MemoryState.PROPOSED:
                raise StoreConflict("memory revision must be a new proposal")
            self._memories[key] = memory
            return memory

        return self._idempotent("create_memory", idempotency_key, request_sha256, mutate)

    def decide_memory(
        self,
        memory_id: str,
        expected_revision: int,
        decision: HumanDecision,
        idempotency_key: str,
        request_sha256: str,
    ) -> MemoryRevision:
        def mutate() -> MemoryRevision:
            key = (memory_id, expected_revision)
            current = self._memories.get(key)
            target = {
                "approve": MemoryState.APPROVED,
                "reject": MemoryState.REJECTED,
            }[decision.value.value]
            if current is None or (current.state, target) not in MEMORY_TRANSITIONS:
                raise StoreConflict("stale or illegal memory decision")
            decided = MemoryRevision.model_validate(
                {**current.model_dump(), "state": target, "decision": decision}
            )
            self._memories[key] = decided
            return decided

        return self._idempotent("decide_memory", idempotency_key, request_sha256, mutate)

    def get_feedback(self, feedback_id: str) -> FeedbackRecord | None:
        with self._lock:
            return self._feedback.get(feedback_id)

    def create_feedback(
        self,
        feedback: FeedbackRecord,
        idempotency_key: str,
        request_sha256: str,
    ) -> FeedbackRecord:
        def mutate() -> FeedbackRecord:
            if feedback.feedback_id in self._feedback:
                raise StoreConflict("feedback already exists")
            self._feedback[feedback.feedback_id] = feedback
            return feedback

        return self._idempotent("create_feedback", idempotency_key, request_sha256, mutate)

    def get_context_packet(self, run_id: str) -> ContextPacket | None:
        with self._lock:
            return self._packets.get(run_id)

    def create_context_packet(
        self,
        packet: ContextPacket,
        idempotency_key: str,
        request_sha256: str,
    ) -> ContextPacket:
        def mutate() -> ContextPacket:
            if packet.consumer_run_id in self._packets:
                raise StoreConflict("context packet already exists")
            self._packets[packet.consumer_run_id] = packet
            return packet

        return self._idempotent("create_context_packet", idempotency_key, request_sha256, mutate)

    def get_injection_receipt(self, run_id: str) -> InjectionReceipt | None:
        with self._lock:
            return self._injections.get(run_id)

    def create_injection_receipt(
        self,
        receipt: InjectionReceipt,
        idempotency_key: str,
        request_sha256: str,
    ) -> InjectionReceipt:
        def mutate() -> InjectionReceipt:
            packet = self._packets.get(receipt.run_id)
            if (
                receipt.run_id in self._injections
                or packet is None
                or receipt.packet_id != packet.packet_id
                or receipt.packet_sha256 != packet.packet_sha256
            ):
                raise StoreConflict("injection receipt requires its persisted packet")
            self._injections[receipt.run_id] = receipt
            return receipt

        return self._idempotent("create_injection_receipt", idempotency_key, request_sha256, mutate)

    @staticmethod
    def _encode_result(value: object) -> dict[str, object]:
        if value is None:
            return {"kind": "none", "value": None}
        return {"kind": type(value).__name__, "value": value.model_dump(mode="json")}

    @staticmethod
    def _decode_result(item: dict[str, object]) -> object:
        models = {
            cls.__name__: cls
            for cls in (
                RunRecord,
                MemoryRevision,
                FeedbackRecord,
                ContextPacket,
                InjectionReceipt,
            )
        }
        kind = item["kind"]
        return None if kind == "none" else models[str(kind)].model_validate(item["value"])

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "runs": [
                    item.model_dump(mode="json")
                    for item in sorted(self._runs.values(), key=lambda value: value.run_id)
                ],
                "memories": [
                    item.model_dump(mode="json")
                    for item in sorted(
                        self._memories.values(), key=lambda value: (value.memory_id, value.revision)
                    )
                ],
                "feedback": [
                    item.model_dump(mode="json")
                    for item in sorted(self._feedback.values(), key=lambda value: value.feedback_id)
                ],
                "packets": [
                    item.model_dump(mode="json")
                    for item in sorted(self._packets.values(), key=lambda value: value.consumer_run_id)
                ],
                "injections": [
                    item.model_dump(mode="json")
                    for item in sorted(self._injections.values(), key=lambda value: value.run_id)
                ],
                "operations": [
                    {
                        "operation": operation,
                        "key": key,
                        "request_sha256": request_sha256,
                        "result": self._encode_result(result),
                    }
                    for (operation, key), (request_sha256, result) in sorted(
                        self._operations.items()
                    )
                ],
            }

    def restore(self, snapshot: dict[str, object]) -> None:
        with self._lock:
            self._runs = {
                item.run_id: item
                for item in map(RunRecord.model_validate, snapshot.get("runs", []))
            }
            memories = tuple(
                map(MemoryRevision.model_validate, snapshot.get("memories", []))
            )
            self._memories = {
                (item.memory_id, item.revision): item for item in memories
            }
            self._feedback = {
                item.feedback_id: item
                for item in map(FeedbackRecord.model_validate, snapshot.get("feedback", []))
            }
            self._packets = {
                item.consumer_run_id: item
                for item in map(ContextPacket.model_validate, snapshot.get("packets", []))
            }
            self._injections = {
                item.run_id: item
                for item in map(InjectionReceipt.model_validate, snapshot.get("injections", []))
            }
            self._operations = {
                (str(item["operation"]), str(item["key"])): (
                    str(item["request_sha256"]),
                    self._decode_result(item["result"]),
                )
                for item in snapshot.get("operations", [])
            }


class JsonFileStore(InMemoryStore):
    """Local durable store for restart tests; not presented as Firestore proof."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__()
        if self.path.exists():
            self.restore(json.loads(self.path.read_text()))

    def _after_change(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(self.snapshot(), handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class FirestoreStore(InMemoryStore):
    """Transactional Firestore persistence for the single demo namespace.

    ponytail: one document keeps the bounded demo atomic; split authoritative
    records into collections if the snapshot approaches Firestore's 1 MiB limit.
    """

    _COLLECTION = "reviewlatch_demo"

    def __init__(self, client=None, namespace: str = "hackathon") -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", namespace) is None:
            raise ValueError("Firestore namespace must be a simple identifier")
        super().__init__()
        self._client = client or firestore.Client()
        self._document = self._client.collection(self._COLLECTION).document(namespace)

    def _after_change(self) -> None:
        pass

    @staticmethod
    def _snapshot_data(snapshot) -> dict[str, object]:
        return snapshot.to_dict() if snapshot.exists else {}

    def _refresh(self) -> None:
        snapshot = self._document.get()
        with self._lock:
            self.restore(self._snapshot_data(snapshot))

    def _idempotent(self, operation: str, key: str, request_sha256: str, mutate):
        @firestore.transactional
        def apply(transaction):
            snapshot = self._document.get(transaction=transaction)
            with self._lock:
                self.restore(self._snapshot_data(snapshot))
                result = InMemoryStore._idempotent(
                    self, operation, key, request_sha256, mutate
                )
                transaction.set(self._document, self.snapshot())
                return result

        return apply(self._client.transaction())

    def reset_demo(self, idempotency_key: str, request_sha256: str) -> None:
        @firestore.transactional
        def apply(transaction):
            snapshot = self._document.get(transaction=transaction)
            with self._lock:
                self.restore(self._snapshot_data(snapshot))
                InMemoryStore.reset_demo(self, idempotency_key, request_sha256)
                transaction.set(self._document, self.snapshot())

        apply(self._client.transaction())

    def list_runs(self) -> tuple[RunRecord, ...]:
        self._refresh()
        return super().list_runs()

    def get_run(self, run_id: str) -> RunRecord | None:
        self._refresh()
        return super().get_run(run_id)

    def get_memory(self, memory_id: str, revision: int) -> MemoryRevision | None:
        self._refresh()
        return super().get_memory(memory_id, revision)

    def list_approved_memories(self, repo_id: str) -> tuple[MemoryRevision, ...]:
        self._refresh()
        return super().list_approved_memories(repo_id)

    def get_feedback(self, feedback_id: str) -> FeedbackRecord | None:
        self._refresh()
        return super().get_feedback(feedback_id)

    def get_context_packet(self, run_id: str) -> ContextPacket | None:
        self._refresh()
        return super().get_context_packet(run_id)

    def get_injection_receipt(self, run_id: str) -> InjectionReceipt | None:
        self._refresh()
        return super().get_injection_receipt(run_id)
