from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic

from ..hashing import sha256_hex
from .cloud_protocol import DispatchOutboxRecord
from .executor_client import (
    CoordinatorClient,
    ExecutorCompletion,
    ExecutorConnectionSummary,
    connect_executor,
)
from .mission_models import EvidenceReference, MissionHead, TaskKind


LOCAL_EXECUTOR_TRUTH = (
    "LOCAL ADAPTER LOOP — CLOUD/FIRESTORE NOT DEPLOYED"
)


class LocalExecutorError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedExecutorInput:
    reference: EvidenceReference
    content: bytes


@dataclass(frozen=True)
class LocalAttemptContext:
    dispatch: DispatchOutboxRecord
    accepted_inputs: tuple[ResolvedExecutorInput, ...]
    cancelled: Event


ArtifactFetcher = Callable[[DispatchOutboxRecord, EvidenceReference], bytes]
LocalAttempt = Callable[[LocalAttemptContext], ExecutorCompletion]


class LocalDispatchExecutor:
    """Adapt one local attempt to the coordinator client's synchronous callback."""

    def __init__(
        self,
        run_attempt: LocalAttempt,
        should_stop: Callable[[], bool],
        *,
        fetch_artifact: ArtifactFetcher | None = None,
        heartbeat_interval_seconds: float = 10,
        cancellation_grace_seconds: float = 30,
        max_input_bytes: int = 10_485_760,
    ) -> None:
        if not callable(run_attempt) or not callable(should_stop):
            raise TypeError("local executor callbacks must be callable")
        if fetch_artifact is not None and not callable(fetch_artifact):
            raise TypeError("artifact fetcher must be callable")
        if not 0 < heartbeat_interval_seconds <= 60:
            raise ValueError("heartbeat interval must be between zero and 60 seconds")
        if not 0 < cancellation_grace_seconds <= 300:
            raise ValueError("cancellation grace must be between zero and 300 seconds")
        if type(max_input_bytes) is not int or not 1 <= max_input_bytes <= 104_857_600:
            raise ValueError("input byte limit must be between one and 104857600")
        self._run_attempt = run_attempt
        self._should_stop = should_stop
        self._fetch_artifact = fetch_artifact
        self._heartbeat_interval = heartbeat_interval_seconds
        self._cancellation_grace = cancellation_grace_seconds
        self._max_input_bytes = max_input_bytes

    def _inputs(
        self,
        dispatch: DispatchOutboxRecord,
        fetch_artifact: Callable[[EvidenceReference], bytes] | None = None,
    ) -> tuple[ResolvedExecutorInput, ...]:
        if (
            dispatch.accepted_inputs
            and fetch_artifact is None
            and self._fetch_artifact is None
        ):
            raise LocalExecutorError("ARTIFACT_FETCH_CAPABILITY_UNAVAILABLE")
        resolved = []
        total = 0
        for reference in dispatch.accepted_inputs:
            try:
                if self._fetch_artifact is not None:
                    content = self._fetch_artifact(dispatch, reference)
                else:
                    assert fetch_artifact is not None
                    content = fetch_artifact(reference)
            except Exception as error:
                raise LocalExecutorError("ARTIFACT_FETCH_FAILED") from error
            if not isinstance(content, bytes) or sha256_hex(content) != reference.sha256:
                raise LocalExecutorError("ARTIFACT_DIGEST_MISMATCH")
            total += len(content)
            if total > self._max_input_bytes:
                raise LocalExecutorError("ARTIFACT_BUDGET_EXCEEDED")
            resolved.append(ResolvedExecutorInput(reference=reference, content=content))
        return tuple(resolved)

    def __call__(
        self,
        dispatch: DispatchOutboxRecord,
        heartbeat: Callable[[], DispatchOutboxRecord],
        fetch_artifact: Callable[[EvidenceReference], bytes] | None = None,
    ) -> ExecutorCompletion:
        if not callable(heartbeat):
            raise TypeError("heartbeat callback must be callable")
        cancelled = Event()
        context = LocalAttemptContext(
            dispatch=dispatch,
            accepted_inputs=self._inputs(dispatch, fetch_artifact),
            cancelled=cancelled,
        )
        outcome: Queue[ExecutorCompletion | BaseException] = Queue(maxsize=1)

        def execute() -> None:
            try:
                result = self._run_attempt(context)
                if not isinstance(result, ExecutorCompletion):
                    raise TypeError("local attempt must return ExecutorCompletion")
                outcome.put(result)
            except BaseException as error:
                outcome.put(error)

        Thread(target=execute, daemon=True, name=f"graphene-{dispatch.attempt_id}").start()
        cancellation_started: float | None = None
        while True:
            try:
                result = outcome.get(timeout=self._heartbeat_interval)
            except Empty:
                if self._should_stop():
                    cancelled.set()
                    cancellation_started = cancellation_started or monotonic()
                if (
                    cancellation_started is not None
                    and monotonic() - cancellation_started > self._cancellation_grace
                ):
                    raise LocalExecutorError("CANCELLATION_TIMEOUT")
                try:
                    heartbeat()
                except BaseException:
                    cancelled.set()
                    raise
                continue
            if isinstance(result, BaseException):
                raise result
            return result


def run_local_executor(
    client: CoordinatorClient,
    *,
    mission_id: str,
    expected_head: MissionHead,
    session_id: str,
    worker_id: str,
    capabilities: tuple[TaskKind, ...],
    run_attempt: LocalAttempt,
    should_stop: Callable[[], bool],
    fetch_artifact: ArtifactFetcher | None = None,
    heartbeat_interval_seconds: float = 10,
    cancellation_grace_seconds: float = 30,
    max_input_bytes: int = 10_485_760,
    poll_interval_seconds: float = 2,
    max_reconnect_attempts: int = 3,
    sleep: Callable[[float], object] | None = None,
) -> ExecutorConnectionSummary:
    """Run the authenticated outbound loop. Cloud deployment remains unproven."""

    execute = LocalDispatchExecutor(
        run_attempt,
        should_stop,
        fetch_artifact=fetch_artifact,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        cancellation_grace_seconds=cancellation_grace_seconds,
        max_input_bytes=max_input_bytes,
    )
    values = {
        "mission_id": mission_id,
        "expected_head": expected_head,
        "session_id": session_id,
        "worker_id": worker_id,
        "capabilities": capabilities,
        "execute": execute,
        "should_stop": should_stop,
        "poll_interval_seconds": poll_interval_seconds,
        "max_reconnect_attempts": max_reconnect_attempts,
    }
    if sleep is not None:
        values["sleep"] = sleep
    return connect_executor(client, **values)


__all__ = [
    "ArtifactFetcher",
    "LOCAL_EXECUTOR_TRUTH",
    "LocalAttempt",
    "LocalAttemptContext",
    "LocalDispatchExecutor",
    "LocalExecutorError",
    "ResolvedExecutorInput",
    "run_local_executor",
]
