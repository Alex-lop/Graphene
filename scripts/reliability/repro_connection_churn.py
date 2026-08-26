#!/usr/bin/env python3
"""Reproduce the SQLite VFS inode-mutex wedge, and show what removes it.

    uv run --frozen python scripts/reliability/repro_connection_churn.py churn
    uv run --frozen python scripts/reliability/repro_connection_churn.py cached

Why this exists. Full-matrix runs wedge with three threads parked in
``__psynch_mutexwait`` inside libsqlite3's unix VFS: openers in ``findReusableFd``
against a closer in ``unixLock`` inside ``sqlite3WalClose``. That mutex is
process-wide -- the captured threads were working on *two different database
files* -- so it is not reachable by ``busy_timeout``, which configures the busy
handler for a locked *database*, one layer above.

``churn`` mirrors what the stores do today: open a connection, do one unit of
work, close it, per operation, from several threads, across two databases (the
mission store and the attempt-evidence store, which is opened *while* a mission
connection is held). ``cached`` does exactly the same work with one connection
per thread per database, reused.

This is a measurement harness, not a test: it prints the numbers whoever
implements the real fix in ``backend/graphene/orchestration/sqlite_mission_store.py`` needs as
a before/after target. It touches no product code and needs no credentials.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

SCHEMA = "CREATE TABLE IF NOT EXISTS t (k INTEGER PRIMARY KEY, v TEXT)"


def _prepare(path: Path) -> None:
    connection = sqlite3.connect(path, isolation_level=None, timeout=5)
    try:
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise SystemExit("this reproducer requires WAL, like the real stores")
        connection.execute(SCHEMA)
    finally:
        connection.close()


def _open(path: Path) -> sqlite3.Connection:
    # Exactly the store's own connection settings (store.py:560-565).
    connection = sqlite3.connect(path, isolation_level=None, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def _work(connection: sqlite3.Connection, worker: int, i: int) -> None:
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT OR REPLACE INTO t (k, v) VALUES (?, ?)", (worker, str(i)))
    connection.execute("SELECT count(*) FROM t").fetchone()
    connection.commit()


def churn(missions: Path, evidence: Path, worker: int, iterations: int) -> None:
    """One connection per operation, and the evidence store opened while the
    mission connection is held -- the shape store.py has today."""
    for i in range(iterations):
        mission = _open(missions)
        try:
            _work(mission, worker, i)
            # store.py calls artifact_resolver.resolve() inside its own
            # connection block; that opens a second database on this thread.
            note = _open(evidence)
            try:
                _work(note, worker, i)
            finally:
                note.close()
        finally:
            mission.close()


def cached(missions: Path, evidence: Path, worker: int, iterations: int) -> None:
    """One connection per thread per database, reused. Same work, same PRAGMAs."""
    mission = _open(missions)
    note = _open(evidence)
    try:
        for i in range(iterations):
            _work(mission, worker, i)
            _work(note, worker, i)
    finally:
        note.close()
        mission.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__)
    parser.add_argument("mode", choices=("churn", "cached"))
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=400)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)

    root = Path(tempfile.mkdtemp(prefix="graphene-churn-"))
    missions, evidence = root / "missions.sqlite3", root / "attempt-evidence.sqlite3"
    _prepare(missions)
    _prepare(evidence)
    run = churn if args.mode == "churn" else cached

    started = time.monotonic()
    threads = [
        threading.Thread(
            target=run, args=(missions, evidence, w, args.iterations), daemon=True
        )
        for w in range(args.threads)
    ]
    for thread in threads:
        thread.start()
    deadline = started + args.timeout
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    elapsed = time.monotonic() - started
    stuck = [t.name for t in threads if t.is_alive()]

    operations = args.threads * args.iterations * 2
    print(
        f"mode={args.mode} threads={args.threads} iterations={args.iterations} "
        f"elapsed={elapsed:.2f}s ops={operations} "
        f"ops_per_s={operations / elapsed:.0f} stuck={len(stuck)} pid={os.getpid()}"
    )
    if stuck:
        print(f"WEDGED: {len(stuck)} thread(s) still running after {args.timeout}s")
        print(f"  sample it with:  /usr/bin/sample {os.getpid()} 5", file=sys.stderr)
        return 9
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
