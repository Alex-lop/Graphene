from __future__ import annotations

from typing import Protocol

from .models import HumanDecision, MemoryRevision, RunRecord


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
