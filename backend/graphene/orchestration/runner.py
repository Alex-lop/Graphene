from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from ..hashing import sha256_hex
from .mission_models import (
    ArtifactEnvelopeReferenceV2,
    ArtifactInputReference,
    AttemptResult,
    Dispatch,
    MissionSnapshot,
    MissionStatus,
    PublishedArtifactReferenceV2,
)
from .worker_runtime import (
    RuntimeErrorCode,
    RuntimeReceipt,
    WorkerRun,
    WorkerRuntime,
    stable_operation_id,
)
from .scheduler import MissionScheduler


class ArtifactSource(Protocol):
    def resolve(self, kind: str, artifact_id: str) -> bytes | None: ...

    def resolve_enveloped(
        self, reference: ArtifactEnvelopeReferenceV2
    ) -> bytes | None: ...


class RunnerError(RuntimeError):
    pass


class RunnerDeadlineExceeded(RunnerError):
    pass


class RunnerStalled(RunnerError):
    pass


class RunnerCancelled(RunnerError):
    pass


class RunnerExecutionFailed(RunnerError):
    def __init__(
        self,
        message: str,
        *,
        result_code: RuntimeErrorCode = RuntimeErrorCode.OUTCOME_UNKNOWN,
    ) -> None:
        self.result_code = result_code
        super().__init__(message)


class AcceptedArtifactCache:
    """Coordinator-filled cache; workers receive no store or artifact authority."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str, str], bytes] = {}

    @staticmethod
    def _key(reference: ArtifactInputReference) -> tuple[str, str, str]:
        if isinstance(reference, PublishedArtifactReferenceV2):
            return (
                "v2",
                reference.publication_id,
                reference.artifact_envelope_sha256,
            )
        return (reference.kind, reference.id, reference.sha256)

    def prefetch(
        self,
        dispatches: tuple[Dispatch, ...],
        source: ArtifactSource,
        snapshot: MissionSnapshot,
    ) -> None:
        publications = {item.publication_id: item for item in snapshot.publications}
        for dispatch in dispatches:
            for reference in dispatch.input_publications:
                key = self._key(reference)
                if isinstance(reference, PublishedArtifactReferenceV2):
                    publication = publications.get(reference.publication_id)
                    if (
                        publication is None
                        or publication.kind != reference.kind
                        or publication.sha256 != reference.content_sha256
                        or dispatch.task_id not in publication.consumers
                    ):
                        raise RunnerExecutionFailed(
                            "accepted publication binding is invalid",
                            result_code=RuntimeErrorCode.INPUT_REJECTED,
                        )
                    try:
                        exact = publication.published_reference()
                    except ValueError as error:
                        raise RunnerExecutionFailed(
                            "accepted publication has no V2 envelope",
                            result_code=RuntimeErrorCode.INPUT_REJECTED,
                        ) from error
                    if exact != reference:
                        raise RunnerExecutionFailed(
                            "accepted publication envelope was swapped",
                            result_code=RuntimeErrorCode.INPUT_REJECTED,
                        )
                    try:
                        value = source.resolve_enveloped(reference)
                    except Exception as error:
                        raise RunnerExecutionFailed(
                            "accepted artifact is unavailable",
                            result_code=RuntimeErrorCode.ARTIFACT_TAMPERED,
                        ) from error
                    expected_sha256 = reference.content_sha256
                else:
                    if reference.kind != "operator-input":
                        raise RunnerExecutionFailed(
                            "legacy publication references are not fetchable",
                            result_code=RuntimeErrorCode.INPUT_REJECTED,
                        )
                    try:
                        value = source.resolve(reference.kind, reference.id)
                    except Exception as error:
                        raise RunnerExecutionFailed(
                            "accepted artifact is unavailable",
                            result_code=RuntimeErrorCode.ARTIFACT_TAMPERED,
                        ) from error
                    expected_sha256 = reference.sha256
                if value is None or sha256_hex(value) != expected_sha256:
                    raise RunnerExecutionFailed(
                        "accepted artifact is unavailable",
                        result_code=RuntimeErrorCode.ARTIFACT_TAMPERED,
                    )
                self._values[key] = value

    def __call__(self, dispatch: Dispatch, reference: ArtifactInputReference) -> bytes:
        if reference not in dispatch.input_publications:
            raise RunnerExecutionFailed("artifact capability is outside the dispatch")
        try:
            return self._values[self._key(reference)]
        except KeyError:
            raise RunnerExecutionFailed("artifact was not prefetched") from None


@dataclass(frozen=True, slots=True)
class MissionRun:
    snapshot: MissionSnapshot
    batches: tuple[tuple[str, ...], ...]
    completion_order: tuple[str, ...]
    replayed_attempt_ids: tuple[str, ...]
    receipts: tuple[RuntimeReceipt, ...]


class MissionRunner:
    """Run one approved mission through the scheduler and isolated worker runtime."""

    def __init__(
        self,
        *,
        scheduler: MissionScheduler,
        runtime: WorkerRuntime,
        worker_ids: tuple[str, ...],
        accepted_artifacts: AcceptedArtifactCache,
        deadline_seconds: float = 300,
        max_no_progress_cycles: int = 3,
        poll_seconds: float = 0.05,
        should_cancel: Callable[[], bool] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not worker_ids or worker_ids != tuple(sorted(set(worker_ids))):
            raise ValueError("worker IDs must be sorted and unique")
        if runtime.accepted_artifact is not accepted_artifacts:
            raise ValueError("runtime must use the runner's accepted artifact cache")
        if not 0 < deadline_seconds <= 3_600:
            raise ValueError("runner deadline must be between zero and one hour")
        if not 1 <= max_no_progress_cycles <= 1_000:
            raise ValueError("no-progress limit must be between 1 and 1000")
        if not 0 <= poll_seconds <= 60:
            raise ValueError("poll interval must be between zero and 60 seconds")
        self.scheduler = scheduler
        self.runtime = runtime
        self.worker_ids = worker_ids
        self.accepted_artifacts = accepted_artifacts
        self.deadline_seconds = deadline_seconds
        self.max_no_progress_cycles = max_no_progress_cycles
        self.poll_seconds = poll_seconds
        self.should_cancel = should_cancel
        # Injectable so a test can assert what the scheduler did without also
        # asserting that the host finished several Git rounds inside a real
        # wall-clock budget. Deadline behaviour gets its own test that drives
        # this forward on purpose.
        self.monotonic = monotonic

    def _cancellation_requested(self) -> bool:
        if self.should_cancel is None:
            return False
        try:
            return self.should_cancel() is True
        except Exception as error:
            raise RunnerExecutionFailed("mission cancellation signal failed") from error

    async def _execute(
        self, dispatch: Dispatch, timeout: float
    ) -> tuple[Dispatch, WorkerRun | AttemptResult | None, RunnerError | None]:
        try:
            run = await asyncio.wait_for(
                self.runtime.execute_async(dispatch), timeout=timeout
            )
            return dispatch, run, None
        except asyncio.CancelledError:
            try:
                recovered = self.runtime.recover_durable_receipt(dispatch)
            except Exception as recovery_error:
                error = RunnerExecutionFailed(
                    f"durable receipt recovery failed for {dispatch.task_id}"
                )
                error.__cause__ = recovery_error
                return dispatch, None, error
            if recovered is not None:
                return (
                    dispatch,
                    recovered,
                    RunnerCancelled("mission cancellation requested"),
                )
            try:
                cancelled = await asyncio.to_thread(
                    self.runtime.cancel_and_reconcile, dispatch
                )
                error: RunnerError = RunnerCancelled("mission cancellation requested")
            except Exception as cleanup_error:
                error = RunnerExecutionFailed(
                    f"worker cancellation cleanup failed for {dispatch.task_id}"
                )
                error.__cause__ = cleanup_error
                return dispatch, None, error
            return dispatch, cancelled, error
        except TimeoutError:
            try:
                recovered = self.runtime.recover_durable_receipt(dispatch)
            except Exception as recovery_error:
                error = RunnerExecutionFailed(
                    f"durable receipt recovery failed for {dispatch.task_id}"
                )
                error.__cause__ = recovery_error
                return dispatch, None, error
            if recovered is not None:
                return (
                    dispatch,
                    recovered,
                    RunnerDeadlineExceeded("mission deadline exceeded"),
                )
            try:
                cancelled = await asyncio.to_thread(
                    self.runtime.cancel_and_reconcile,
                    dispatch,
                    retryable=True,
                )
                error = RunnerDeadlineExceeded("mission deadline exceeded")
                return dispatch, cancelled, error
            except Exception as cleanup_error:
                error = RunnerDeadlineExceeded(
                    "mission deadline exceeded and cleanup failed"
                )
                error.__cause__ = cleanup_error
                return dispatch, None, error
        except Exception:
            try:
                recovered = self.runtime.recover_durable_receipt(dispatch)
            except Exception as recovery_error:
                error = RunnerExecutionFailed(
                    f"durable receipt recovery failed for {dispatch.task_id}"
                )
                error.__cause__ = recovery_error
                return dispatch, None, error
            if recovered is not None:
                return dispatch, recovered, None
            try:
                cancelled = await asyncio.to_thread(
                    self.runtime.cancel_and_reconcile,
                    dispatch,
                    retryable=True,
                )
                error = RunnerExecutionFailed(
                    f"worker execution failed for {dispatch.task_id}"
                )
                return dispatch, cancelled, error
            except Exception as cleanup_error:
                error = RunnerExecutionFailed(
                    f"worker execution and cleanup failed for {dispatch.task_id}"
                )
                error.__cause__ = cleanup_error
                return dispatch, None, error

    async def _reject_prefetch(
        self,
        dispatches: tuple[Dispatch, ...],
        error: RunnerExecutionFailed,
    ) -> None:
        failures: list[Exception] = []
        for dispatch in dispatches:
            result_code = error.result_code
            try:
                await asyncio.to_thread(self.runtime.cancel, dispatch)
            except Exception as cleanup_error:
                failures.append(cleanup_error)
                result_code = RuntimeErrorCode.OUTCOME_UNKNOWN
            try:
                self.scheduler.complete(
                    dispatch,
                    AttemptResult(
                        succeeded=False,
                        result_code=result_code,
                        session_id="runner-" + dispatch.attempt_id[-16:],
                        invocation_id=stable_operation_id(
                            dispatch, "prefetch-rejected"
                        ),
                    ),
                )
            except Exception as completion_error:
                failures.append(completion_error)
        if failures:
            raise RunnerExecutionFailed(
                "accepted artifact rejection cleanup failed"
            ) from failures[0]

    async def run_async(self, mission_id: str) -> MissionRun:
        started = self.monotonic()
        no_progress = 0
        batches: list[tuple[str, ...]] = []
        completion_order: list[str] = []
        replayed: list[str] = []
        receipts: list[RuntimeReceipt] = []
        reconciled_attempts: set[str] = set()

        while True:
            snapshot = self.scheduler.store.snapshot(mission_id)
            if snapshot.mission.status == MissionStatus.AWAITING_RESULT:
                return MissionRun(
                    snapshot=snapshot,
                    batches=tuple(batches),
                    completion_order=tuple(completion_order),
                    replayed_attempt_ids=tuple(replayed),
                    receipts=tuple(receipts),
                )
            if snapshot.mission.status != MissionStatus.RUNNING:
                raise RunnerExecutionFailed("mission is not running")
            if self._cancellation_requested():
                raise RunnerCancelled("mission cancellation requested")

            remaining = self.deadline_seconds - (self.monotonic() - started)
            if remaining <= 0:
                raise RunnerDeadlineExceeded("mission deadline exceeded")
            reconciled_results: dict[str, AttemptResult] = {}
            for dispatch in self.scheduler.recover(
                mission_id, self.worker_ids, include_expired=True
            ):
                if (
                    dispatch.expires_at <= self.scheduler.clock.now()
                    and dispatch.attempt_id not in reconciled_attempts
                ):
                    recovered = await self.runtime.reconcile_expired_async(dispatch)
                    reconciled_attempts.add(dispatch.attempt_id)
                    if recovered is not None:
                        receipts.append(recovered.receipt)
                        if recovered.replayed:
                            try:
                                self.scheduler.reconcile_expired_receipt(
                                    dispatch, recovered.result
                                )
                            except Exception as error:
                                raise RunnerExecutionFailed(
                                    f"completion reconciliation failed for {dispatch.task_id}"
                                ) from error
                            try:
                                self.runtime.finalize_reconciled_attempt(
                                    dispatch, recovered.receipt
                                )
                            except Exception as error:
                                raise RunnerExecutionFailed(
                                    f"committed receipt cleanup failed for {dispatch.task_id}"
                                ) from error
                            completion_order.append(dispatch.task_id)
                            replayed.append(dispatch.attempt_id)
                        else:
                            reconciled_results[dispatch.attempt_id] = recovered.result
            dispatches = self.scheduler.tick(
                mission_id,
                self.worker_ids,
                reconciled_results=reconciled_results,
            )
            if not dispatches:
                snapshot = self.scheduler.store.snapshot(mission_id)
                if snapshot.mission.status == MissionStatus.AWAITING_RESULT:
                    continue
                no_progress += 1
                if no_progress >= self.max_no_progress_cycles:
                    raise RunnerStalled("mission made no progress")
                await asyncio.sleep(min(self.poll_seconds, remaining))
                continue

            no_progress = 0
            batches.append(tuple(item.task_id for item in dispatches))
            snapshot = self.scheduler.store.snapshot(mission_id)
            try:
                self.accepted_artifacts.prefetch(
                    dispatches, self.runtime.evidence, snapshot
                )
            except RunnerExecutionFailed as error:
                await self._reject_prefetch(dispatches, error)
                raise
            pending = {
                asyncio.create_task(self._execute(dispatch, remaining)): dispatch
                for dispatch in dispatches
            }
            failures: list[RunnerError] = []
            cancellation_requested = False
            while pending:
                if not cancellation_requested and self._cancellation_requested():
                    cancellation_requested = True
                if cancellation_requested:
                    for task, dispatch in pending.items():
                        if self.runtime.cancellation_safe(dispatch):
                            task.cancel()
                completed, _ = await asyncio.wait(
                    pending,
                    timeout=min(max(self.poll_seconds, 0.01), 0.1),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in completed:
                    pending.pop(task)
                    dispatch, run, error = await task
                    if run is None:
                        assert error is not None
                        failures.append(error)
                        continue
                    result = run.result if isinstance(run, WorkerRun) else run
                    try:
                        self.scheduler.complete(dispatch, result)
                    except Exception as completion_error:
                        failure = RunnerExecutionFailed(
                            f"completion commit failed for {dispatch.task_id}"
                        )
                        failure.__cause__ = completion_error
                        failures.append(failure)
                        continue
                    if isinstance(run, WorkerRun):
                        try:
                            self.runtime.finalize_reconciled_attempt(
                                dispatch, run.receipt
                            )
                        except Exception as cleanup_error:
                            failure = RunnerExecutionFailed(
                                f"committed receipt cleanup failed for {dispatch.task_id}"
                            )
                            failure.__cause__ = cleanup_error
                            failures.append(failure)
                            continue
                    if error is not None:
                        if not (
                            cancellation_requested
                            and isinstance(error, RunnerCancelled)
                        ):
                            failures.append(error)
                        continue
                    completion_order.append(dispatch.task_id)
                    assert isinstance(run, WorkerRun)
                    receipts.append(run.receipt)
                    if run.replayed:
                        replayed.append(dispatch.attempt_id)
            if failures:
                raise failures[0]
            if cancellation_requested:
                raise RunnerCancelled("mission cancellation requested")

    def run(self, mission_id: str) -> MissionRun:
        return asyncio.run(self.run_async(mission_id))


__all__ = [
    "AcceptedArtifactCache",
    "MissionRun",
    "MissionRunner",
    "RunnerCancelled",
    "RunnerDeadlineExceeded",
    "RunnerError",
    "RunnerExecutionFailed",
    "RunnerStalled",
]
