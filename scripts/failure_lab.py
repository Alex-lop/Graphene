#!/usr/bin/env python3
"""Failure laboratory: list and SIGKILL barrier-proven Gemini model children.

Usage::

    uv run --frozen python scripts/failure_lab.py list MISSION_ID
    uv run --frozen python scripts/failure_lab.py kill MISSION_ID --attempt ATTEMPT_ID --actor-label LABEL
    uv run --frozen python scripts/failure_lab.py auto MISSION_ID --actor-label LABEL [--timeout SECONDS]

``list`` prints a JSON array with one object per owned-process record the
mission's registry holds for MISSION_ID: ``attempt_id``, ``worker_id`` (read
from the mission snapshot), ``pid``, ``pgid``, ``started_at``, and the
executable ``ps`` observed when the record was written.

``kill`` sends SIGKILL to exactly one model-child process group through
``OwnedProcessRegistry.signal`` -- the same identity-checked path that
``graphene mission cancel`` uses -- and prints a JSON object describing
exactly what it signalled. It refuses, signalling nothing, when the registry
holds no record for ATTEMPT_ID, when that record belongs to a different
mission, when the attempt is not running under a live lease, or when the
child has not durably acknowledged entering provider transport under that
lease and fence. Nothing is ever killed by name.

Fake adapters remain in-process and therefore have no model child or kill
window. Live Gemini model calls alone cross this child boundary; repository
mutation and trusted checks remain in the owning worker process.

``auto`` drives the directive's choreography unattended: it polls the mission
store and the registry in-process (the check window is only a few seconds,
too short for one ``uv run`` per poll) and, the first moment a work attempt
from one worker is **already accepted** while a *different* worker's work
attempt is running under a live lease with a barrier-acknowledged model child,
it performs exactly the identity-checked ``kill`` above on that attempt and
prints the same JSON plus the sibling's accepted publication id and the
instant of the kill. If the mission leaves ``running`` before such a moment
exists, it exits 3 having killed nothing; the run is then simply not a
failure-laboratory run.

Exit status: 0 on success, 2 when the kill was refused, 3 when ``auto`` found
no opportunity, 1 on any other error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import IO

from graphene.cli.mission import MissionCliError, _mission_runtime, _store_for_mission
from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.orchestration.mission_models import (
    AttemptState,
    Dispatch,
    MissionStatus,
    PublicationState,
    TaskKind,
)
from graphene.orchestration.process_control import (
    OwnedProcess,
    OwnedProcessRegistry,
    ProcessControlError,
)
from graphene.orchestration.sqlite_mission_store import (
    MissionNotFound,
    MissionStoreError,
)


class FailureLabError(RuntimeError):
    """An operator-visible failure-laboratory refusal."""


def _actor_label(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value) is None:
        raise FailureLabError("refused: actor label is invalid")
    return value


def _injection_directory(registry: OwnedProcessRegistry):
    directory = registry.directory.parent / "failure-injections"
    created = not directory.exists()
    if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
        raise FailureLabError("refused: failure-injection registry is unsafe")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    if created:
        descriptor = os.open(directory.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return directory


def _record_injection(
    registry: OwnedProcessRegistry, value: dict[str, object]
) -> dict[str, object]:
    directory = _injection_directory(registry)
    content = canonical_json_bytes(value)
    digest = sha256_hex(content)
    try:
        registry._atomic_create(directory, directory / f"{digest}.json", value)
    except ProcessControlError as error:
        raise FailureLabError("refused: failure injection could not be recorded") from error
    return {**value, "injection_record_sha256": digest}


def record_for_attempt(
    registry: OwnedProcessRegistry, attempt_id: str, *, model: bool = False
) -> OwnedProcess | None:
    """Read the durable record for one attempt, whichever mission owns it.

    ``records_for_mission`` filters by mission, which would hide a foreign
    record instead of letting ``kill`` refuse it by name. The registry's own
    validated reader is used so symlinks, loose modes, and malformed records
    are rejected exactly as they are everywhere else.
    """

    path = registry._model_path(attempt_id) if model else registry._path(attempt_id)
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
        "birth_token": owned.birth_token,
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


def kill_model_attempt(
    registry: OwnedProcessRegistry,
    mission_id: str,
    attempt_id: str,
    dispatch: Dispatch | None,
    *,
    actor_label: str = "local-operator",
) -> dict[str, object]:
    """Kill only a live child whose provider-transport barrier matches its fence."""

    try:
        owned = record_for_attempt(registry, attempt_id, model=True)
        if owned is None:
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
        barrier = registry.model_dispatch_barrier(dispatch)
    except ProcessControlError as error:
        raise FailureLabError(f"refused: {error}") from error
    if barrier is None:
        raise FailureLabError(
            f"refused: attempt {attempt_id} has no acknowledged model dispatch"
        )
    actor = _actor_label(actor_label)
    requested_at = datetime.now(UTC)
    request_value = {
        **record_value(owned, dispatch.worker_id),
        "record_type": "signal_requested",
        "action": "kill",
        "actor_label": actor,
        "signal": "SIGKILL",
        "requested_at": requested_at.isoformat(timespec="milliseconds"),
        "task_id": dispatch.task_id,
        "fencing_token": dispatch.fencing_token,
        "stage": "model",
        "request_sha256": barrier.request_sha256,
        "sdk_invocation_id": barrier.sdk_invocation_id,
        "provider_dispatched_at": barrier.dispatched_at,
    }
    request = _record_injection(registry, request_value)
    request_record_sha256 = str(request["injection_record_sha256"])
    try:
        if not registry.signal_prepared(owned, signal.SIGKILL):
            raise ProcessControlError("owned process is no longer running")
        deadline = time.monotonic() + 5
        while registry._live_identity(owned) and time.monotonic() < deadline:
            time.sleep(0.01)
        observed_state = (
            "running" if registry._live_identity(owned) else "not_running"
        )
    except ProcessControlError as error:
        _record_injection(
            registry,
            {
                "record_type": "signal_refused",
                "signal_request_record_sha256": request_record_sha256,
                "observed_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "observed_process_state": "unknown",
                "reason": str(error),
            },
        )
        raise FailureLabError(f"refused: {error}") from error
    result = _record_injection(
        registry,
        {
            **request_value,
            "record_type": "signal_observed",
            "signal_request_record_sha256": request_record_sha256,
            "observed_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "observed_process_state": observed_state,
        },
    )
    if observed_state == "running":
        raise FailureLabError("refused: signalled process identity remained live")
    return result


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


def kill_opportunity(
    store: object, registry: OwnedProcessRegistry, mission_id: str
) -> tuple[str, str, str] | None:
    """``(victim_attempt_id, sibling_worker_id, sibling_publication_id)`` or None.

    The victim is a running WORK attempt, under a live lease, with a durable
    owned-process record, whose worker differs from a worker that already has
    an accepted WORK publication. Nothing is signalled here.
    """

    snapshot = store.snapshot(mission_id)  # type: ignore[attr-defined]
    kinds = {task.task_id: task.kind for task in snapshot.tasks}
    attempts = {item.attempt_id: item for item in snapshot.attempts}
    accepted = [
        (attempts[item.attempt_id].worker_id, item.publication_id)
        for item in snapshot.publications
        if item.state == PublicationState.ACCEPTED
        and kinds.get(item.task_id) == TaskKind.WORK
        and item.attempt_id in attempts
    ]
    if not accepted:
        return None
    for attempt in snapshot.attempts:
        if (
            kinds.get(attempt.task_id) != TaskKind.WORK
            or attempt.state != AttemptState.RUNNING
            or not registry.has_record(attempt.attempt_id)
        ):
            continue
        dispatch = running_dispatch(store, mission_id, attempt.attempt_id)
        if dispatch is None:
            continue
        try:
            if registry.model_dispatch_barrier(dispatch) is None:
                continue
        except ProcessControlError:
            continue
        for sibling_worker, publication_id in accepted:
            if sibling_worker != attempt.worker_id:
                return attempt.attempt_id, sibling_worker, publication_id
    return None


def auto_kill(
    store: object,
    registry: OwnedProcessRegistry,
    mission_id: str,
    *,
    timeout: float,
    actor_label: str = "local-operator",
    poll: float = 0.05,
    reopen: Callable[[], object] | None = None,
) -> dict[str, object]:
    """Wait for the first kill opportunity and take it; see ``kill_opportunity``."""

    deadline = time.monotonic() + timeout
    transient_read_errors = 0
    while True:
        try:
            status = store.snapshot(mission_id).mission.status  # type: ignore[attr-defined]
            opportunity = kill_opportunity(store, registry, mission_id)
        except MissionStoreError:
            # Live contact: a reader can observe an attempt row whose evidence
            # artifact is still being written in the separate evidence store
            # ("mission materialized artifacts are invalid"). The store's read
            # quarantine is sticky by design, so the poller reopens the store
            # and keeps polling; a persistent error still ends at the deadline.
            transient_read_errors += 1
            if time.monotonic() > deadline:
                raise
            time.sleep(poll)
            if reopen is not None:
                store = reopen()
            continue
        if opportunity is not None:
            attempt_id, sibling_worker, publication_id = opportunity
            dispatch = running_dispatch(store, mission_id, attempt_id)
            killed_at = datetime.now(UTC)
            value = kill_model_attempt(
                registry,
                mission_id,
                attempt_id,
                dispatch,
                actor_label=actor_label,
            )
            return {
                **value,
                "killed_at": killed_at.isoformat(timespec="milliseconds"),
                "sibling_worker_id": sibling_worker,
                "sibling_accepted_publication_id": publication_id,
                "transient_read_errors": transient_read_errors,
            }
        if status not in {MissionStatus.PROPOSED, MissionStatus.RUNNING}:
            raise FailureLabError(
                f"no kill opportunity: mission {mission_id} is {status.value} and "
                "no running work attempt had an accepted sibling publication"
            )
        if time.monotonic() > deadline:
            raise FailureLabError(
                f"no kill opportunity within {timeout:g}s; nothing was signalled"
            )
        time.sleep(poll)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="failure_lab",
        allow_abbrev=False,
        description=(
            "List or SIGKILL acknowledged Graphene-owned Gemini model children."
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
    kill.add_argument("--actor-label", required=True)
    auto = commands.add_parser(
        "auto",
        allow_abbrev=False,
        help="kill the first running work attempt whose sibling is already accepted",
    )
    auto.add_argument("mission_id", help="exact mission ID")
    auto.add_argument("--timeout", type=float, default=900.0)
    auto.add_argument("--actor-label", required=True)
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
        elif args.command == "auto":
            value = auto_kill(
                store,
                registry,
                args.mission_id,
                timeout=args.timeout,
                actor_label=args.actor_label,
                reopen=lambda: _store_for_mission(args.mission_id),
            )
        else:
            dispatch = running_dispatch(store, args.mission_id, args.attempt_id)
            value = kill_model_attempt(
                registry,
                args.mission_id,
                args.attempt_id,
                dispatch,
                actor_label=args.actor_label,
            )
    except FailureLabError as error:
        print(str(error), file=stderr)
        return 3 if str(error).startswith("no kill opportunity") else 2
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
