#!/usr/bin/env python3
"""Failure laboratory: list and SIGKILL strongly identified Graphene-owned processes.

Usage::

    uv run --frozen python scripts/failure_lab.py list MISSION_ID
    uv run --frozen python scripts/failure_lab.py kill MISSION_ID --attempt ATTEMPT_ID

``list`` prints a JSON array with one object per owned-process record the
mission's registry holds for MISSION_ID: ``attempt_id``, ``worker_id`` (read
from the mission snapshot), ``pid``, ``pgid``, ``started_at``, and the
executable ``ps`` observed when the record was written.

``kill`` sends SIGKILL to exactly one process group through
``OwnedProcessRegistry.signal`` -- the same identity-checked path that
``graphene mission cancel`` uses -- and prints a JSON object describing
exactly what it signalled. It refuses, signalling nothing, when the registry
holds no record for ATTEMPT_ID, when that record belongs to a different
mission, or when the attempt is not running under a live lease. Nothing is
ever killed by name.

On the ``gemini-adk`` path workers run in-process; the strongly identified
Graphene-owned process is the attempt's check subprocess, which exists only
while ``GRAPHENE_CHECK_EXECUTOR=host-sandbox`` runs the frozen
``fixture-tests`` command for that attempt.

Exit status: 0 on success, 2 when the kill was refused, 1 on any other error.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import IO

from graphene.cli.mission import MissionCliError, _mission_runtime, _store_for_mission
from graphene.orchestration.models import AttemptState, Dispatch
from graphene.orchestration.process_control import (
    OwnedProcess,
    OwnedProcessRegistry,
    ProcessControlError,
)
from graphene.orchestration.store import MissionNotFound, MissionStoreError


class FailureLabError(RuntimeError):
    """A refusal. Nothing was signalled."""


def record_for_attempt(
    registry: OwnedProcessRegistry, attempt_id: str
) -> OwnedProcess | None:
    """Read the durable record for one attempt, whichever mission owns it.

    ``records_for_mission`` filters by mission, which would hide a foreign
    record instead of letting ``kill`` refuse it by name. The registry's own
    validated reader is used so symlinks, loose modes, and malformed records
    are rejected exactly as they are everywhere else.
    """

    path = registry._path(attempt_id)
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    return registry._read(path)


def record_value(owned: OwnedProcess, worker_id: str | None) -> dict[str, object]:
    return {
        "attempt_id": owned.attempt_id,
        "executable": owned.executable,
        "mission_id": owned.mission_id,
        "pgid": owned.pgid,
        "pid": owned.pid,
        "started_at": owned.started_at,
        "worker_id": worker_id,
    }


def list_records(
    registry: OwnedProcessRegistry,
    mission_id: str,
    worker_ids: Mapping[str, str],
) -> list[dict[str, object]]:
    """Owned-process records for ``mission_id`` with each attempt's worker."""

    records = sorted(
        registry.records_for_mission(mission_id), key=lambda item: item.attempt_id
    )
    return [record_value(item, worker_ids.get(item.attempt_id)) for item in records]


def kill_attempt(
    registry: OwnedProcessRegistry,
    mission_id: str,
    attempt_id: str,
    dispatch: Dispatch | None,
) -> dict[str, object]:
    """SIGKILL one attempt's owned process group, or refuse and signal nothing."""

    try:
        owned = record_for_attempt(registry, attempt_id)
    except ProcessControlError as error:
        raise FailureLabError(
            f"refused: owned-process record for attempt {attempt_id} "
            f"is unusable: {error}"
        ) from error
    if owned is None:
        raise FailureLabError(
            f"refused: no owned-process record exists for attempt {attempt_id}"
        )
    if owned.mission_id != mission_id:
        raise FailureLabError(
            f"refused: owned-process record for attempt {attempt_id} belongs to "
            f"mission {owned.mission_id}, not {mission_id}"
        )
    if (
        dispatch is None
        or dispatch.mission_id != mission_id
        or dispatch.attempt_id != attempt_id
    ):
        raise FailureLabError(
            f"refused: attempt {attempt_id} is not running under a live lease "
            f"in mission {mission_id}"
        )
    try:
        registry.signal(dispatch, signal.SIGKILL)
    except ProcessControlError as error:
        raise FailureLabError(f"refused: {error}") from error
    return {
        **record_value(owned, dispatch.worker_id),
        "action": "kill",
        "signal": "SIGKILL",
        "task_id": dispatch.task_id,
        "fencing_token": dispatch.fencing_token,
    }


def worker_ids(store: object, mission_id: str) -> dict[str, str]:
    snapshot = store.snapshot(mission_id)  # type: ignore[attr-defined]
    return {item.attempt_id: item.worker_id for item in snapshot.attempts}


def running_dispatch(
    store: object, mission_id: str, attempt_id: str, *, now: datetime | None = None
) -> Dispatch | None:
    """Rebuild the attempt's Dispatch the way ``graphene mission cancel`` does."""

    snapshot = store.snapshot(mission_id)  # type: ignore[attr-defined]
    attempt = next(
        (item for item in snapshot.attempts if item.attempt_id == attempt_id), None
    )
    if attempt is None or attempt.state != AttemptState.RUNNING:
        return None
    dispatches = store.recover_dispatches(  # type: ignore[attr-defined]
        mission_id, (attempt.worker_id,), recorded_at=now or datetime.now(UTC)
    )
    return next((item for item in dispatches if item.attempt_id == attempt_id), None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="failure_lab",
        allow_abbrev=False,
        description=(
            "List or SIGKILL strongly identified Graphene-owned check processes."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser(
        "list", allow_abbrev=False, help="print the mission's owned-process records"
    )
    listing.add_argument("mission_id", help="exact mission ID")
    kill = commands.add_parser(
        "kill",
        allow_abbrev=False,
        help="SIGKILL one attempt's owned process group via the registry",
    )
    kill.add_argument("mission_id", help="exact mission ID")
    kill.add_argument(
        "--attempt", required=True, dest="attempt_id", help="exact attempt ID"
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: IO[str] = sys.stdout,
    stderr: IO[str] = sys.stderr,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        store = _store_for_mission(args.mission_id)
        store.snapshot(args.mission_id)  # the mission must exist before any kill
        registry = OwnedProcessRegistry(_mission_runtime(args.mission_id))
        if args.command == "list":
            value: object = list_records(
                registry, args.mission_id, worker_ids(store, args.mission_id)
            )
        else:
            dispatch = running_dispatch(store, args.mission_id, args.attempt_id)
            value = kill_attempt(registry, args.mission_id, args.attempt_id, dispatch)
    except FailureLabError as error:
        print(str(error), file=stderr)
        return 2
    except MissionNotFound:
        print(
            f"error: mission {args.mission_id} is not in the local mission store",
            file=stderr,
        )
        return 1
    except (MissionCliError, MissionStoreError, ProcessControlError) as error:
        print(f"error: {error}", file=stderr)
        return 1
    print(json.dumps(value, sort_keys=True, indent=2), file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
