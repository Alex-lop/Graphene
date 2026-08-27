from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import RLock

_pid = os.getpid()
# ponytail: one process-wide gate; split ownership only if measured throughput demands it.
_lock = RLock()


def _process_lock() -> RLock:
    """Return a fresh lock after fork instead of acquiring an inherited one."""

    global _lock, _pid
    pid = os.getpid()
    if pid != _pid:
        _lock = RLock()
        _pid = pid
    return _lock


@contextmanager
def serialized_sqlite() -> Iterator[None]:
    """Serialize SQLite connection lifecycle work within this process."""

    with _process_lock():
        yield


@contextmanager
def serialized_connection(
    connect: Callable[[], sqlite3.Connection],
) -> Iterator[sqlite3.Connection]:
    """Open, reset, and close one connection without concurrent VFS churn."""

    with serialized_sqlite():
        connection = connect()
        try:
            yield connection
        finally:
            try:
                if connection.in_transaction:
                    connection.rollback()
            finally:
                connection.close()
