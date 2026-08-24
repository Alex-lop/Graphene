from __future__ import annotations

import fcntl
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from graphene.orchestration.evidence import (
    AttemptEvidenceEventType,
    SQLiteAttemptEvidenceStore,
)
from graphene.orchestration.models import AttemptResult, Dispatch, GenericEvidenceLink
from graphene.orchestration.process_control import (
    OwnedProcessRegistry,
    ProcessCancelled,
)
from graphene.hashing import sha256_hex
from graphene.orchestration.scripted import (
    ScriptedError,
    ScriptedWorker,
    _execute_scripted_batch,
    _git,
)
from graphene.orchestration.store import LeaseConflict, MissionConflict, StaleWorker


def _dispatch(task_id: str) -> Dispatch:
    return Dispatch(
        mission_id="mission-concurrency",
        plan_revision=1,
        plan_sha256="0" * 64,
        task_id=task_id,
        task_kind="work",
        attempt_id=f"attempt-{task_id}",
        attempt_number=1,
        worker_id=f"worker-{task_id}",
        workspace_id=f"workspace-{task_id}",
        lease_id=f"lease-{task_id}",
        fencing_token=1,
        dispatch_command_id=f"dispatch-concurrency-{task_id}",
        write_paths=(),
        allowed_commands=("check",),
        acceptance_checks=("check",),
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )


def _result(code: str, *, succeeded: bool) -> AttemptResult:
    return AttemptResult(
        succeeded=succeeded,
        retryable=not succeeded,
        result_code=code,
        evidence_link=(
            GenericEvidenceLink(evidence_id=f"evidence-{code}")
            if succeeded
            else None
        ),
    )


class _Scheduler:
    def __init__(self, release_failure: threading.Event | None = None) -> None:
        self.completed: list[tuple[str, str]] = []
        self.release_failure = release_failure

    def complete(self, dispatch: Dispatch, result: AttemptResult) -> None:
        self.completed.append((dispatch.task_id, result.result_code))
        if result.succeeded and self.release_failure is not None:
            self.release_failure.set()


class _Worker:
    def __init__(self, execute) -> None:
        self._execute = execute
        self.failures: list[tuple[str, str]] = []
        self.cancelled: list[str] = []

    def execute(self, dispatch: Dispatch) -> AttemptResult:
        return self._execute(dispatch)

    def terminal_failure(
        self, dispatch: Dispatch, error: Exception
    ) -> AttemptResult:
        code = (
            "worker_timeout"
            if isinstance(error, TimeoutError)
            else "malformed_output"
            if isinstance(error, ValidationError)
            else "worker_exception"
        )
        self.failures.append((dispatch.task_id, code))
        return _result(code, succeeded=False)

    def cancel(self, dispatch: Dispatch) -> None:
        self.cancelled.append(dispatch.task_id)


def test_completed_sibling_commits_before_other_worker_exception() -> None:
    release_failure = threading.Event()

    def execute(dispatch: Dispatch) -> AttemptResult:
        if dispatch.task_id == "raise":
            assert release_failure.wait(1)
            raise RuntimeError("boom")
        return _result("passed", succeeded=True)

    scheduler = _Scheduler(release_failure)
    worker = _Worker(execute)
    _execute_scripted_batch(
        (_dispatch("success"), _dispatch("raise")),
        worker,  # type: ignore[arg-type]
        scheduler,  # type: ignore[arg-type]
        timeout_seconds=1,
    )

    assert scheduler.completed == [
        ("success", "passed"),
        ("raise", "worker_exception"),
    ]


def test_hung_worker_is_timed_out_without_losing_completed_sibling() -> None:
    release_hang = threading.Event()

    def execute(dispatch: Dispatch) -> AttemptResult:
        if dispatch.task_id == "hang":
            assert release_hang.wait(1)
        return _result("passed", succeeded=True)

    scheduler = _Scheduler()
    worker = _Worker(execute)
    started = time.monotonic()
    _execute_scripted_batch(
        (_dispatch("success"), _dispatch("hang")),
        worker,  # type: ignore[arg-type]
        scheduler,  # type: ignore[arg-type]
        timeout_seconds=0.05,
    )
    elapsed = time.monotonic() - started
    release_hang.set()

    assert elapsed < 0.5
    assert scheduler.completed == [
        ("success", "passed"),
        ("hang", "worker_timeout"),
    ]
    assert worker.cancelled == ["hang"]


def test_two_simultaneous_worker_failures_are_both_committed() -> None:
    barrier = threading.Barrier(2)

    def execute(dispatch: Dispatch) -> AttemptResult:
        barrier.wait(timeout=1)
        raise RuntimeError(dispatch.task_id)

    scheduler = _Scheduler()
    worker = _Worker(execute)
    _execute_scripted_batch(
        (_dispatch("failure-a"), _dispatch("failure-b")),
        worker,  # type: ignore[arg-type]
        scheduler,  # type: ignore[arg-type]
        timeout_seconds=1,
    )

    assert set(scheduler.completed) == {
        ("failure-a", "worker_exception"),
        ("failure-b", "worker_exception"),
    }


def test_worker_returning_malformed_output_is_committed_as_typed_failure() -> None:
    scheduler = _Scheduler()
    worker = _Worker(lambda dispatch: {"not": "an attempt result"})

    _execute_scripted_batch(
        (_dispatch("malformed"),),
        worker,  # type: ignore[arg-type]
        scheduler,  # type: ignore[arg-type]
        timeout_seconds=1,
    )

    assert scheduler.completed == [("malformed", "malformed_output")]


def test_worker_adapter_classifies_bounded_terminal_failures() -> None:
    worker = object.__new__(ScriptedWorker)
    worker.store = None
    dispatch = _dispatch("classify")

    assert worker._failure_code(dispatch, TimeoutError()) == ("worker_timeout", True)
    assert worker._failure_code(dispatch, ProcessCancelled()) == (
        "process_killed",
        True,
    )
    assert worker._failure_code(dispatch, LeaseConflict()) == ("heartbeat_lost", True)
    assert worker._failure_code(dispatch, StaleWorker()) == ("lease_lost", True)
    assert worker._failure_code(dispatch, MissionConflict()) == (
        "store_conflict",
        False,
    )
    assert worker._failure_code(dispatch, RuntimeError()) == ("worker_exception", True)


def test_worker_adapter_durably_seals_exception_as_terminal_evidence(
    tmp_path: Path,
) -> None:
    worker = object.__new__(ScriptedWorker)
    worker.store = None
    worker.evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite")
    worker._process_registry = OwnedProcessRegistry(tmp_path)
    worker.clock = lambda: datetime.now(UTC)
    dispatch = _dispatch("durable-failure")

    result = worker.terminal_failure(dispatch, RuntimeError("private detail"))
    events = worker.evidence.tail(result.evidence_link.evidence_id, 0, 3)

    assert result.result_code == "worker_exception" and result.retryable
    assert tuple(item.event_type for item in events) == (
        AttemptEvidenceEventType.ATTEMPT_STARTED,
        AttemptEvidenceEventType.ATTEMPT_FAILED,
    )
    assert events[-1].payload == {"result_code": "worker_exception"}


def test_assembly_patch_stages_deleted_authorized_path(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "main")
    (repository / "delete.txt").write_text("remove me\n", encoding="utf-8")
    (repository / "unchanged.txt").write_text("keep me\n", encoding="utf-8")
    _git(repository, "add", "--all", "--")
    _git(repository, "commit", "-q", "-m", "base")
    base_sha = _git(repository, "rev-parse", "HEAD").decode().strip()
    (repository / "delete.txt").unlink()

    worker = object.__new__(ScriptedWorker)
    worker.base_sha = base_sha
    patch, changed = worker._patch(
        repository,
        ("delete.txt", "unchanged.txt"),
        require_exact=False,
    )

    assert changed == ("delete.txt",)
    assert b"deleted file mode" in patch
    assert b"delete.txt" in patch


def test_a_contended_attempt_lock_fails_closed_instead_of_parking_the_thread(
    tmp_path: Path,
) -> None:
    """``execute`` must never block on an attempt lock a live executor holds.

    ``_execute_scripted_batch`` abandons a running worker on timeout
    (``executor.shutdown(wait=False)``), and ``recover_dispatches`` rebuilds the
    recovered Dispatch with the *same* ``attempt_id``. So the next batch hands
    that attempt to a fresh pool thread while the abandoned one still holds the
    attempt lock. A blocking ``flock`` parks that thread forever, and a
    non-daemon pool thread is joined with **no timeout** by
    ``concurrent.futures.thread._python_exit`` at interpreter shutdown -- after
    the last test, after pytest's summary, and after pytest-timeout has
    cancelled its per-item timer. Nothing in the suite can catch that: it is a
    silent wedge with no traceback.

    Owning an attempt exclusively means refusing it when someone else owns it,
    which is what ``lineage/observation.py`` already does with ``LOCK_NB``.
    """
    class _UnreachableStore:
        """Reaching the store means the contended lock was taken anyway."""

        def snapshot(self, mission_id: str) -> object:
            raise AssertionError("execute() acquired a lock another executor holds")

    worker = object.__new__(ScriptedWorker)
    worker.store = _UnreachableStore()
    worker._attempt_locks = tmp_path / "attempt-locks"
    worker._attempt_locks.mkdir(mode=0o700)
    dispatch = _dispatch("contended")
    lock = worker._attempt_locks / (sha256_hex(dispatch.attempt_id.encode()) + ".lock")

    held = threading.Event()
    release = threading.Event()

    def hold_the_lock() -> None:
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            held.set()
            release.wait(30)
        finally:
            os.close(descriptor)

    # Both threads are daemons on purpose: if the assertion below fails, the
    # parked thread must not become the very hang this test is about.
    owner = threading.Thread(target=hold_the_lock, daemon=True)
    owner.start()
    try:
        assert held.wait(10), "the stand-in executor never took the attempt lock"
        outcome: list[BaseException | None] = []

        def attempt() -> None:
            try:
                worker.execute(dispatch)
                outcome.append(None)
            except BaseException as error:  # noqa: BLE001 - recorded, then asserted
                outcome.append(error)

        second = threading.Thread(target=attempt, daemon=True)
        second.start()
        second.join(timeout=10)

        assert not second.is_alive(), (
            "execute() parked on an attempt lock another live executor holds; "
            "_python_exit joins that thread without a timeout at shutdown"
        )
        assert isinstance(outcome[0], ScriptedError), outcome
        assert "already owned" in str(outcome[0]), outcome
    finally:
        release.set()
        owner.join(timeout=10)
