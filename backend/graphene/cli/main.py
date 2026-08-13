from __future__ import annotations

import argparse
import math
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from ..hashing import canonical_json_bytes
from ..lineage import (
    EvidenceInvalid,
    LineageStoreError,
    SQLiteArtifactStore,
    SQLiteLineageStore,
)
from ..lineage.reducer import ProjectionError, reduce_events
from ..models import (
    Event,
    EvidenceInvalidState,
    LineageEventType,
    LineageOperation,
    LineageProjection,
    ScopeId,
    TaskId,
)
from .render import render_human, render_ndjson

EXIT_UNAVAILABLE = 69
_PROFILES = (
    "platform-maintainer@1",
    "auth-maintainer@1",
    "billing-observer@1",
)
_READ_ONLY = {"watch", "inspect", "why", "replay"}


class _ConfigurationError(ValueError):
    pass


class _NotFound(LookupError):
    pass


def _positive_number(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("speed must be a positive number") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("speed must be a positive number")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphene", allow_abbrev=False)
    parser.add_argument("--json", action="store_true", dest="json_mode")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", allow_abbrev=False)
    run.add_argument("task", choices=tuple(item.value for item in TaskId))
    run.add_argument("--profile", required=True, choices=_PROFILES)

    watch = commands.add_parser("watch", allow_abbrev=False)
    watch.add_argument("run_id")

    inspect = commands.add_parser("inspect", allow_abbrev=False)
    inspect.add_argument("evidence_id")
    inspect.add_argument("--run", required=True, dest="run_id")

    why = commands.add_parser("why", allow_abbrev=False)
    why.add_argument("path")
    why.add_argument("--run", required=True, dest="run_id")

    replay = commands.add_parser("replay", allow_abbrev=False)
    replay.add_argument("run_id")
    replay.add_argument("--speed", required=True, type=_positive_number)

    feedback = commands.add_parser("feedback", allow_abbrev=False)
    feedback.add_argument("hunk_id")
    feedback.add_argument("--event", required=True, dest="event_id")
    feedback.add_argument("--run", required=True, dest="run_id")
    feedback.add_argument("--message", required=True)

    answer = commands.add_parser("answer", allow_abbrev=False)
    answer.add_argument("question_id")
    answer.add_argument(
        "--choice", required=True, choices=tuple(item.value for item in ScopeId)
    )

    memory = commands.add_parser("memory", allow_abbrev=False)
    memory_commands = memory.add_subparsers(dest="memory_action", required=True)
    for action in ("approve", "reject"):
        decision = memory_commands.add_parser(action, allow_abbrev=False)
        decision.add_argument("memory_id")

    handoff = commands.add_parser("handoff", allow_abbrev=False)
    handoff.add_argument("source_run_id")
    handoff.add_argument("--to", required=True, choices=_PROFILES, dest="profile")
    handoff.add_argument(
        "--task", required=True, choices=tuple(item.value for item in TaskId)
    )
    handoff.add_argument("--start", action="store_true")

    promote = commands.add_parser("promote", allow_abbrev=False)
    promote.add_argument("consumer_run_id")
    return parser


def _database_path() -> Path:
    value = os.environ.get("GRAPHENE_LINEAGE_DB")
    if not value:
        raise _ConfigurationError("GRAPHENE_LINEAGE_DB is required")
    path = Path(value).resolve()
    if not path.is_file():
        raise _ConfigurationError("GRAPHENE_LINEAGE_DB must name an existing file")
    try:
        with closing(
            sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        ) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
    except sqlite3.Error as error:
        raise _ConfigurationError(
            "GRAPHENE_LINEAGE_DB is not a lineage database"
        ) from error
    if not {"lineage_artifacts", "run_heads", "events"} <= tables:
        raise _ConfigurationError("GRAPHENE_LINEAGE_DB is not a lineage database")
    return path


def _load(
    path: Path,
    run_id: str,
    *,
    immutable: bool = False,
) -> tuple[tuple[Event, ...], LineageProjection]:
    artifacts = SQLiteArtifactStore(path, read_only=True, immutable=immutable)
    store = SQLiteLineageStore(
        path,
        artifact_resolver=artifacts.resolve,
        read_only=True,
        immutable=immutable,
    )
    head = store.verify(run_id)
    if isinstance(head, EvidenceInvalidState):
        raise EvidenceInvalid(head)
    if head.seq == 0:
        raise _NotFound

    events: list[Event] = []
    after_seq = 0
    while after_seq < head.seq:
        batch = store.tail(run_id, after_seq, min(256, head.seq - after_seq))
        if not batch:
            raise ProjectionError(
                "verified head could not be replayed",
                run_id=run_id,
                seq=after_seq + 1,
            )
        events.extend(batch)
        after_seq = batch[-1].seq
    stream = tuple(events)
    if len(stream) != head.seq or stream[-1].event_sha256 != head.event_sha256:
        raise ProjectionError("verified head changed during replay", run_id=run_id)
    return stream, reduce_events(stream)


def _observations(
    events: tuple[Event, ...],
    projection: LineageProjection,
    path: str,
) -> list[dict[str, object]]:
    rail = {item.seq: item for item in projection.event_rail}
    observations: list[dict[str, object]] = []
    for event in events:
        if event.event_type != LineageEventType.TOOL_COMPLETED:
            continue
        item = rail.get(event.seq)
        if item is None:
            continue
        paths = event.payload.get("paths")
        observed = item.path == path or (
            item.operation == LineageOperation.SEARCH_REPO
            and isinstance(paths, (list, tuple))
            and path in paths
        )
        if not observed:
            continue
        observations.append(
            {
                "event_id": item.event_id,
                "event_type": item.event_type.value,
                "operation": None if item.operation is None else item.operation.value,
                "seq": item.seq,
                "status": item.status,
                "truth_kind": item.truth_kind.value,
            }
        )
    if not observations:
        raise _NotFound
    return observations


def _human_lines(lines: list[str]) -> str:
    return "".join(
        (line if len(line) <= 80 else line[:79] + "~") + "\n" for line in lines
    )


def _render_why(
    events: tuple[Event, ...],
    projection: LineageProjection,
    path: str,
    *,
    json_mode: bool,
) -> str:
    observations = _observations(events, projection, path)
    if json_mode:
        return (
            canonical_json_bytes(
                {
                    "observations": observations,
                    "path": path,
                    "run_id": projection.run_id,
                    "unknowns": list(projection.unknowns),
                }
            ).decode()
            + "\n"
        )
    lines = [f"PATH {path} RUN {projection.run_id}"]
    lines.extend(
        f"OBSERVED {item['seq']:03d} {item['truth_kind']} "
        f"{item['operation']} {item['status']} {item['event_id']}"
        for item in observations
    )
    lines.extend(f"UNKNOWN {item}" for item in projection.unknowns)
    return _human_lines(lines)


def _evidence_invalid(state: EvidenceInvalidState) -> int:
    seq = "unknown" if state.first_invalid_seq is None else str(state.first_invalid_seq)
    sys.stderr.write(f"EVIDENCE_INVALID: run={state.run_id} seq={seq} {state.reason}\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command not in _READ_ONLY:
        command = (
            f"memory {args.memory_action}" if args.command == "memory" else args.command
        )
        sys.stderr.write(
            f"UNAVAILABLE: graphene {command} is not implemented in Stage 2\n"
        )
        return EXIT_UNAVAILABLE

    try:
        events, projection = _load(
            _database_path(),
            args.run_id,
            immutable=args.command == "replay",
        )
        if args.command in {"watch", "replay"}:
            output = (
                render_ndjson(events)
                if args.json_mode
                else render_human(
                    projection,
                    no_color="NO_COLOR" in os.environ or not sys.stdout.isatty(),
                    width=shutil.get_terminal_size((80, 24)).columns,
                )
            )
        elif args.command == "inspect":
            event = next(
                (item for item in events if item.event_id == args.evidence_id), None
            )
            if event is None:
                raise _NotFound
            output = canonical_json_bytes(event.model_dump(mode="json")).decode() + "\n"
        else:
            output = _render_why(
                events, projection, args.path, json_mode=args.json_mode
            )
    except _ConfigurationError as error:
        sys.stderr.write(f"CONFIG_ERROR: {error}\n")
        return 1
    except _NotFound:
        sys.stderr.write("NOT_FOUND: no matching committed lineage evidence\n")
        return 1
    except EvidenceInvalid as error:
        return _evidence_invalid(error.state)
    except ProjectionError as error:
        return _evidence_invalid(error.as_state())
    except (LineageStoreError, sqlite3.Error, OSError, ValueError):
        sys.stderr.write("DATABASE_ERROR: unable to open or verify lineage database\n")
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
