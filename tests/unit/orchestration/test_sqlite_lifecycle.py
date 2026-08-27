from __future__ import annotations

import os
import select
import signal
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from graphene.orchestration import sqlite_lifecycle
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.sqlite_lifecycle import serialized_connection
from graphene.orchestration.sqlite_mission_store import (
    MissionNotFound,
    SQLiteMissionStore,
)

from .test_store import _create


class _TrackedConnection:
    def __init__(self, connection: sqlite3.Connection, closed) -> None:
        self._connection = connection
        self._closed = closed

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def close(self) -> None:
        try:
            self._connection.close()
        finally:
            self._closed()


def test_mission_and_evidence_connection_lifecycles_are_serialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission = SQLiteMissionStore(tmp_path / "missions.sqlite3")
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "evidence.sqlite3")
    counter_lock = threading.Lock()
    first_opened = threading.Event()
    concurrent_open = threading.Event()
    counts = {"active": 0, "maximum": 0}

    def tracked(connect):
        def open_connection():
            connection = connect()
            with counter_lock:
                counts["active"] += 1
                counts["maximum"] = max(counts["maximum"], counts["active"])
                first = not first_opened.is_set()
                first_opened.set()
                if counts["active"] > 1:
                    concurrent_open.set()
            if first:
                concurrent_open.wait(0.2)

            def closed() -> None:
                with counter_lock:
                    counts["active"] -= 1

            return _TrackedConnection(connection, closed)

        return open_connection

    monkeypatch.setattr(mission, "_connect", tracked(mission._connect))
    monkeypatch.setattr(evidence, "_connect", tracked(evidence._connect))
    errors: list[BaseException] = []

    def read_mission() -> None:
        try:
            mission.head("mission-lifecycle")
        except MissionNotFound:
            pass
        except BaseException as error:  # pragma: no cover - asserted below
            errors.append(error)

    def read_evidence() -> None:
        try:
            evidence.head("evidence-lifecycle")
        except BaseException as error:  # pragma: no cover - asserted below
            errors.append(error)

    first = threading.Thread(target=read_mission)
    second = threading.Thread(target=read_evidence)
    first.start()
    assert first_opened.wait(1)
    second.start()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert counts == {"active": 0, "maximum": 1}


def test_serialized_connection_rolls_back_before_close(tmp_path: Path) -> None:
    states: list[bool] = []

    class Connection(_TrackedConnection):
        def close(self) -> None:
            states.append(self._connection.in_transaction)
            super().close()

    def connect() -> sqlite3.Connection:
        return Connection(
            sqlite3.connect(tmp_path / "rollback.sqlite3", isolation_level=None),
            lambda: None,
        )

    with pytest.raises(RuntimeError, match="stop"):
        with serialized_connection(connect) as connection:
            connection.execute("BEGIN")
            raise RuntimeError("stop")

    assert states == [False]


def test_process_lock_is_replaced_after_pid_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = sqlite_lifecycle._process_lock()
    child_pid = sqlite_lifecycle._pid + 1
    monkeypatch.setattr(sqlite_lifecycle.os, "getpid", lambda: child_pid)

    assert sqlite_lifecycle._process_lock() is not inherited


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_inherited_store_state_never_blocks_child_sqlite_access(tmp_path: Path) -> None:
    mission = SQLiteMissionStore(tmp_path / "fork-missions.sqlite3")
    evidence = SQLiteAttemptEvidenceStore(tmp_path / "fork-evidence.sqlite3")
    _create(mission, approve=False)
    mission.integrity_marker("mission-1")

    # Old stores carried additional instance locks across fork. Hold them when
    # present so this test fails on that implementation instead of hanging CI.
    inherited_locks = tuple(
        lock
        for lock in (
            getattr(mission, "_integrity_monitor_lock", None),
            getattr(evidence, "_lock", None),
        )
        if lock is not None
    )
    held = threading.Event()
    release = threading.Event()

    def hold_in_parent() -> None:
        for lock in inherited_locks:
            lock.acquire()
        held.set()
        release.wait(10)
        for lock in reversed(inherited_locks):
            lock.release()

    holder = threading.Thread(target=hold_in_parent)
    holder.start()
    assert held.wait(1)
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions live in the parent
        os.close(read_fd)
        try:
            mission.integrity_marker("mission-1")
            evidence.head("evidence-after-fork")
            os.write(write_fd, b"ok")
            os._exit(0)
        except BaseException:
            os.write(write_fd, b"error")
            os._exit(1)

    os.close(write_fd)
    timed_out = not select.select([read_fd], [], [], 3)[0]
    if timed_out:
        os.kill(child_pid, signal.SIGKILL)
        payload = b""
    else:
        payload = os.read(read_fd, 16)
    os.close(read_fd)
    _, status = os.waitpid(child_pid, 0)
    release.set()
    holder.join(2)

    assert not timed_out
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert payload == b"ok"


def test_high_contention_store_connection_churn_shuts_down(tmp_path: Path) -> None:
    mission_path = tmp_path / "churn-missions.sqlite3"
    evidence_path = tmp_path / "churn-evidence.sqlite3"
    workers = 8
    cycles = 20
    start = threading.Barrier(workers)

    def churn() -> int:
        start.wait(timeout=5)
        for _ in range(cycles):
            mission = SQLiteMissionStore(mission_path)
            try:
                mission.head("mission-churn")
            except MissionNotFound:
                pass
            finally:
                mission.close()
            SQLiteAttemptEvidenceStore(evidence_path).head("evidence-churn")
        return cycles

    executor = ThreadPoolExecutor(max_workers=workers)
    futures = [executor.submit(churn) for _ in range(workers)]
    deadline = time.monotonic() + 30
    try:
        assert (
            sum(
                future.result(timeout=max(0.001, deadline - time.monotonic()))
                for future in futures
            )
            == workers * cycles
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
