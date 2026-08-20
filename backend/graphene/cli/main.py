from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sqlite3
import stat
import sys
import time
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path

from ..bootstrap import (
    BootstrapError,
    _checkout,
    _expected_checkout_files,
    _repository,
    bootstrap_local_run,
)
from ..context.consumer import ConsumerStartError, FreshConsumer, start_fresh_consumer
from ..context.handoff import (
    AUTH_CAPABILITIES,
    CompiledHandoff,
    HandoffCompileError,
    compile_verified_handoff,
)
from ..context.runtime import RuntimeBindingError, bind_and_dispatch
from ..execution import run_fixture_tests
from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..lineage import (
    EvidenceInvalid,
    HumanWorkflowError,
    HumanWorkflowService,
    LineageStoreError,
    SQLiteArtifactStore,
    SQLiteLineageStore,
)
from ..lineage.explain import (
    ExplainEvidenceError,
    ExplainNotFound,
    explain_path,
    inspect_run_item,
)
from ..lineage.observation import ObservationError, register_watch
from ..lineage.local_commit import (
    LocalCommitError,
    commit_promoted_run,
)
from ..lineage.promotion import (
    PreparedPromotionCandidate,
    PromotionError,
    PromotionRequest,
    PromotionRetestResult,
    SQLiteCheckpointRecorder,
    prepare_verified_promotion,
    promote,
)
from ..lineage.reducer import ProjectionError, reduce_events
from ..models import (
    ContextBrief,
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    EvidenceReference,
    HandoffDecision,
    HandoffDenied,
    HunkEvidence,
    LineageEventType,
    LineageAuthority,
    LineageOperation,
    LineageProjection,
    LineageRunState,
    MemoryDecisionValue,
    ScopeId,
    SourceKind,
    SourceReference,
    TaskId,
    TruthKind,
    VerifiedHead,
)
from .render import render_human

_PROFILES = (
    "platform-maintainer@1",
    "auth-maintainer@1",
    "billing-observer@1",
)
_READ_ONLY = {"watch", "inspect", "why", "replay"}
_POLL_SECONDS = 0.05
_WATCH_STOP_STATES = frozenset(
    {
        LineageRunState.ACCESS_DENIED,
        LineageRunState.NEEDS_HUMAN,
        LineageRunState.FAILED,
        LineageRunState.INTERRUPTED,
        LineageRunState.PROMOTED,
        LineageRunState.REJECTED,
    }
)


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


def _nonnegative_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "after-seq must be a non-negative integer"
        ) from error
    if number < 0 or str(number) != value:
        raise argparse.ArgumentTypeError("after-seq must be a non-negative integer")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphene", allow_abbrev=False)
    parser.add_argument("--json", action="store_true", dest="json_mode")
    commands = parser.add_subparsers(dest="command", required=True)

    from .mission import register_commands

    register_commands(commands)

    run = commands.add_parser("run", allow_abbrev=False)
    run.add_argument("task", help="plan ID, or compatibility task with --profile")
    run.add_argument("--profile", choices=_PROFILES)
    run.set_defaults(
        command_id=None,
        confirm_human=False,
        operator_label="local-operator",
        rationale=None,
    )

    watch = commands.add_parser("watch", allow_abbrev=False)
    watch.add_argument("run_id")
    watch.add_argument("--after-seq", type=_nonnegative_integer, default=0)
    watch.add_argument("--snapshot", action="store_true")

    inspect = commands.add_parser("inspect", allow_abbrev=False)
    inspect.add_argument("evidence_id")
    inspect.add_argument("--run", required=True, dest="run_id")

    why = commands.add_parser("why", allow_abbrev=False)
    why.add_argument("path")
    why_identity = why.add_mutually_exclusive_group()
    why_identity.add_argument("--run", dest="run_id")
    why_identity.add_argument("--mission", dest="mission_id")

    replay = commands.add_parser("replay", allow_abbrev=False)
    replay.add_argument("run_id")
    replay.add_argument("--speed", required=True, type=_positive_number)

    review = commands.add_parser("review", allow_abbrev=False)
    review.add_argument("run_id")

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
    answer.add_argument("--operator-label", default="local-operator")
    answer.add_argument("--rationale")

    memory = commands.add_parser("memory", allow_abbrev=False)
    memory_commands = memory.add_subparsers(dest="memory_action", required=True)
    for action in ("approve", "reject"):
        decision = memory_commands.add_parser(action, allow_abbrev=False)
        decision.add_argument("memory_id")
        decision.add_argument("--operator-label", default="local-operator")
        decision.add_argument("--rationale")

    handoff = commands.add_parser("handoff", allow_abbrev=False)
    handoff.add_argument("source_run_id")
    handoff.add_argument("--to", required=True, choices=_PROFILES, dest="profile")
    handoff.add_argument(
        "--task", required=True, choices=tuple(item.value for item in TaskId)
    )
    handoff.add_argument("--start", action="store_true")

    promote = commands.add_parser("promote", allow_abbrev=False)
    promote.add_argument("consumer_run_id")
    promote.add_argument("--decision", required=True, choices=("commit", "reject"))
    promote.add_argument("--operator-label", default="local-operator")
    promote.add_argument("--rationale")

    demo = commands.add_parser(
        "demo",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Driver proof boundaries:\n"
            "  verified-replay  VERIFIED REPLAY — NO LIVE AGENT, HUMAN "
            "ATTESTATION, OR NEW TEST EXECUTION\n"
            "  scripted-local   SCRIPTED LOCAL WORKFLOW FIXTURE — NOT "
            "INDEPENDENT-AGENT OR GOOGLE ADK PROOF\n"
            "  adk-fake         REAL ADK RUNNER + DETERMINISTIC FAKE MODEL — "
            "NOT GEMINI OR INDEPENDENT-AGENT PROOF"
        ),
    )
    demo.add_argument(
        "--driver",
        choices=("verified-replay", "scripted-local", "adk-fake"),
        default="scripted-local",
    )
    demo.add_argument("--speed", type=_positive_number, default=1.0)
    demo.add_argument("--no-open", action="store_true")
    demo.add_argument("--cleanup", action="store_true")
    demo.add_argument("--exit-after-demo", action="store_true", help=argparse.SUPPRESS)
    demo.add_argument(
        "--automated-fixture", action="store_true", help=argparse.SUPPRESS
    )
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
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
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


def _run(args: argparse.Namespace) -> int:
    value = os.environ.get("GRAPHENE_LINEAGE_DB")
    if not value:
        sys.stderr.write("CONFIG_ERROR: GRAPHENE_LINEAGE_DB is required\n")
        return 1
    try:
        result = bootstrap_local_run(
            value,
            task_id=args.task,
            profile_id=args.profile,
        )
    except BootstrapError:
        sys.stderr.write("BOOTSTRAP_ERROR: unable to create or verify local run\n")
        return 1

    if args.json_mode:
        output = {
            "database": str(result.database_path),
            "projection_sha256": result.projection.projection_sha256,
            "run_id": result.run_id,
            "verified_head": result.head.model_dump(mode="json"),
        }
        sys.stdout.write(canonical_json_bytes(output).decode() + "\n")
    else:
        sys.stdout.write(
            f"RUN {result.run_id} STARTED seq={result.head.seq} "
            f"projection={result.projection.projection_sha256[:12]}\n"
        )
    return 0


def _load(
    path: Path,
    run_id: str,
) -> tuple[tuple[Event, ...], LineageProjection]:
    artifacts = SQLiteArtifactStore(path, read_only=True)
    store = SQLiteLineageStore(
        path,
        artifact_resolver=artifacts.resolve,
        read_only=True,
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
        if not batch or tuple(item.seq for item in batch) != tuple(
            range(after_seq + 1, after_seq + len(batch) + 1)
        ):
            raise ProjectionError(
                "verified head could not be replayed",
                run_id=run_id,
                seq=after_seq + 1,
            )
        events.extend(batch)
        after_seq = batch[-1].seq
    stream = tuple(events)
    if (
        len(stream) != head.seq
        or head.event_count != head.seq
        or stream[-1].event_sha256 != head.event_sha256
    ):
        raise ProjectionError("verified head changed during replay", run_id=run_id)
    return stream, reduce_events(stream)


def _database_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("lineage database is not a regular file")
    return metadata.st_dev, metadata.st_ino


def _write_json_events(events: tuple[Event, ...]) -> None:
    for event in events:
        sys.stdout.write(
            canonical_json_bytes(event.model_dump(mode="json")).decode() + "\n"
        )
        sys.stdout.flush()


def _render_projection(projection: LineageProjection) -> None:
    sys.stdout.write(
        render_human(
            projection,
            no_color="NO_COLOR" in os.environ or not sys.stdout.isatty(),
            width=shutil.get_terminal_size((80, 24)).columns,
        )
    )
    sys.stdout.flush()


def _watch(
    path: Path,
    run_id: str,
    *,
    after_seq: int,
    snapshot: bool,
    json_mode: bool,
    sleeper: Callable[[float], None] | None = None,
) -> None:
    sleeper = sleeper or time.sleep
    identity = _database_identity(path)
    previous_head: tuple[int, str] | None = None
    cursor = after_seq
    with register_watch(path, run_id, after_seq) as observed:
        while True:
            if _database_identity(path) != identity:
                raise ProjectionError("lineage database was replaced", run_id=run_id)
            events, projection = _load(path, run_id)
            if _database_identity(path) != identity:
                raise ProjectionError("lineage database was replaced", run_id=run_id)
            if after_seq > projection.head_seq:
                raise ProjectionError(
                    "after sequence exceeds the verified head",
                    run_id=run_id,
                    seq=projection.head_seq,
                )
            if previous_head is not None:
                previous_seq, previous_sha256 = previous_head
                if (
                    projection.head_seq < previous_seq
                    or events[previous_seq - 1].event_sha256 != previous_sha256
                ):
                    raise ProjectionError(
                        "verified lineage prefix changed while watching",
                        run_id=run_id,
                        seq=previous_seq,
                    )
            new_events = tuple(event for event in events if event.seq > cursor)
            if json_mode:
                _write_json_events(new_events)
            elif new_events or previous_head is None:
                _render_projection(projection)
            cursor = projection.head_seq
            observed.acknowledge(cursor)
            previous_head = (projection.head_seq, projection.head_sha256)
            if snapshot or projection.state in _WATCH_STOP_STATES:
                return
            sleeper(_POLL_SECONDS)


def _replay(
    events: tuple[Event, ...],
    projection: LineageProjection,
    *,
    speed: float,
    json_mode: bool,
    sleeper: Callable[[float], None] | None = None,
) -> None:
    sleeper = sleeper or time.sleep
    previous = None
    for event in events:
        if previous is not None:
            delay = min(
                1.0,
                max(
                    0.0,
                    (
                        event.server_recorded_at - previous.server_recorded_at
                    ).total_seconds()
                    / speed,
                ),
            )
            if delay:
                sleeper(delay)
        if json_mode:
            _write_json_events((event,))
        previous = event
    if not json_mode:
        _render_projection(projection)


def _human_lines(lines: list[str]) -> str:
    return "".join(
        (line if len(line) <= 80 else line[:79] + "~") + "\n" for line in lines
    )


def _render_explanation(result: dict[str, object], *, json_mode: bool) -> str:
    if json_mode:
        return canonical_json_bytes(result).decode() + "\n"
    lines = [f"PATH {result['path']} RUN {result['run_id']}"]
    lines.extend(
        f"OBSERVED {item['seq']:03d} {item['truth_kind']} "
        f"{item['operation']} {item['status']} {item['event_id']}"
        for item in result["observations"]
    )
    lines.extend(
        f"LINK {item['relation']} {item['source']['kind']}:{item['source']['id']} "
        f"-> {item['target']['kind']}:{item['target']['id']}"
        for item in result["relationships"]
    )
    lines.extend(f"UNKNOWN {item}" for item in result["unknowns"])
    return _human_lines(lines)


def _evidence_invalid(state: EvidenceInvalidState) -> int:
    seq = "unknown" if state.first_invalid_seq is None else str(state.first_invalid_seq)
    sys.stderr.write(f"EVIDENCE_INVALID: run={state.run_id} seq={seq} {state.reason}\n")
    return 1


def _verified_head(projection: LineageProjection) -> VerifiedHead:
    return VerifiedHead(
        run_id=projection.run_id,
        seq=projection.head_seq,
        event_sha256=projection.head_sha256,
        event_count=projection.head_seq,
    )


def _workflow(path: Path) -> tuple[HumanWorkflowService, SQLiteArtifactStore]:
    _, golden, _, _, _ = _repository(None)
    artifacts = SQLiteArtifactStore(path)
    return (
        HumanWorkflowService(
            SQLiteLineageStore(path, artifact_resolver=artifacts.resolve),
            artifacts,
            golden.memory,
        ),
        artifacts,
    )


def _key(prefix: str, *values: str) -> str:
    return prefix + "_" + sha256_hex("\0".join(values).encode())[:32]


def _find_run(
    path: Path,
    event_type: LineageEventType,
    payload_key: str,
    payload_value: str,
) -> str:
    matches: set[str] = set()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute("SELECT run_id, event_bytes FROM events").fetchall()
    for run_id, raw in rows:
        try:
            event = Event.model_validate_json(raw)
        except (TypeError, ValueError):
            continue
        if (
            event.event_type == event_type
            and event.payload.get(payload_key) == payload_value
        ):
            matches.add(str(run_id))
    if len(matches) != 1:
        raise _NotFound
    run_id = matches.pop()
    _load(path, run_id)
    return run_id


def _review(path: Path, run_id: str) -> dict[str, object]:
    events, projection = _load(path, run_id)
    workflow, artifacts = _workflow(path)
    changeset = next(
        (
            event
            for event in events
            if event.event_type == LineageEventType.CHANGESET_PARSED
        ),
        None,
    )
    if changeset is None:
        changeset = workflow.derive_changeset(
            run_id,
            _verified_head(projection),
            idempotency_key=_key("review_changeset", run_id),
        )
        events, projection = _load(path, run_id)
    if any(
        event.event_type == LineageEventType.TOOL_COMPLETED
        and event.payload.get("operation") == LineageOperation.WRITE_FILE.value
        and event.seq > changeset.seq
        for event in events
    ):
        raise HumanWorkflowError("the parsed changeset is stale")
    test_event = next(
        (
            event
            for event in reversed(events)
            if event.event_type == LineageEventType.TOOL_COMPLETED
            and event.payload.get("operation") == LineageOperation.RUN_FIXED_TEST.value
            and event.seq < changeset.seq
        ),
        None,
    )
    if test_event is None:
        raise HumanWorkflowError("the run has no fixed test for its changeset")
    receipt = next(
        (
            event
            for event in events
            if event.event_type == LineageEventType.TEST_RECEIPT_CREATED
        ),
        None,
    )
    if receipt is None:
        receipt = workflow.record_test_receipt(
            run_id,
            _verified_head(projection),
            test_event_id=test_event.event_id,
            idempotency_key=_key("review_test", run_id, test_event.event_id),
        )
        _, projection = _load(path, run_id)
    hunks: list[dict[str, object]] = []
    for reference in changeset.references:
        if reference.kind != EvidenceKind.HUNK:
            continue
        raw = artifacts.resolve(reference.kind.value, reference.id)
        if raw is None:
            raise HumanWorkflowError("a changeset hunk is unavailable")
        hunk = HunkEvidence.model_validate_json(raw)
        hunks.append(
            {
                "evidence_id": reference.id,
                "hunk_id": hunk.hunk_id,
                "path": hunk.path,
                "new_start": hunk.new_start,
                "new_lines": hunk.new_lines,
            }
        )
    return {
        "run_id": run_id,
        "head": _verified_head(projection).model_dump(mode="json"),
        "changeset_event_id": changeset.event_id,
        "test_receipt_event_id": receipt.event_id,
        "write_event_ids": [
            event.event_id
            for event in events
            if event.event_type == LineageEventType.TOOL_COMPLETED
            and event.payload.get("operation") == LineageOperation.WRITE_FILE.value
        ],
        "hunks": hunks,
    }


def _feedback(path: Path, args: argparse.Namespace) -> dict[str, object]:
    events, projection = _load(path, args.run_id)
    workflow, artifacts = _workflow(path)
    for asked in (
        event
        for event in events
        if event.event_type == LineageEventType.CLARIFICATION_ASKED
    ):
        raw = artifacts.resolve(asked.source_ref.kind.value, asked.source_ref.id)
        try:
            policy = {} if raw is None else json.loads(raw)
            pending_ref = policy["pending_feedback_reference"]
            pending_raw = artifacts.resolve(pending_ref["kind"], pending_ref["id"])
            pending = {} if pending_raw is None else json.loads(pending_raw)
        except (KeyError, TypeError, ValueError):
            continue
        if (
            pending.get("hunk_reference", {}).get("id") == args.hunk_id
            and pending.get("evidence_event", {}).get("id") == args.event_id
            and pending.get("correction_sha256") == sha256_hex(args.message.encode())
        ):
            return {
                "run_id": args.run_id,
                "question_id": asked.payload["question_id"],
                "head": _verified_head(projection).model_dump(mode="json"),
            }
    asked = workflow.ask_clarification(
        args.run_id,
        _verified_head(projection),
        write_event_id=args.event_id,
        hunk_id=args.hunk_id,
        correction=args.message,
        idempotency_key=_key("feedback", args.run_id, args.event_id, args.hunk_id),
    )
    return {
        "run_id": args.run_id,
        "question_id": asked.payload["question_id"],
        "head": _verified_head(_load(path, args.run_id)[1]).model_dump(mode="json"),
    }


def _answer(
    path: Path,
    args: argparse.Namespace,
    *,
    simulated_fixture: bool = False,
    human_attestation: bool = False,
    operator_label: str = "local-operator",
    operator_rationale: str | None = None,
) -> dict[str, object]:
    run_id = _find_run(
        path,
        LineageEventType.CLARIFICATION_ASKED,
        "question_id",
        args.question_id,
    )
    events, projection = _load(path, run_id)
    workflow, artifacts = _workflow(path)
    asked = next(
        event
        for event in events
        if event.event_type == LineageEventType.CLARIFICATION_ASKED
        and event.payload.get("question_id") == args.question_id
    )
    raw = artifacts.resolve(asked.source_ref.kind.value, asked.source_ref.id)
    try:
        policy = {} if raw is None else json.loads(raw)
        pending_ref = policy["pending_feedback_reference"]
        pending_raw = artifacts.resolve(pending_ref["kind"], pending_ref["id"])
        pending = {} if pending_raw is None else json.loads(pending_raw)
        feedback_id = str(pending["feedback_id"])
    except (KeyError, TypeError, ValueError) as error:
        raise HumanWorkflowError("the clarification evidence is unavailable") from error
    answered = next(
        (
            event
            for event in events
            if event.event_type == LineageEventType.CLARIFICATION_ANSWERED
            and event.payload.get("question_id") == args.question_id
        ),
        None,
    )
    if answered is None:
        answered = workflow.answer_clarification(
            run_id,
            _verified_head(projection),
            question_id=args.question_id,
            choice=args.choice,
            idempotency_key=_key("answer", run_id, args.question_id, args.choice),
            simulated_fixture=simulated_fixture,
            human_attestation=human_attestation,
            operator_label=operator_label,
            operator_rationale=operator_rationale,
        )
        events, projection = _load(path, run_id)
    elif answered.payload.get("choice") != args.choice:
        raise HumanWorkflowError("the clarification already has another answer")
    elif (answered.truth_kind == TruthKind.SIMULATED_FIXTURE) != simulated_fixture:
        raise HumanWorkflowError("the clarification has another provenance")
    feedback = next(
        (
            event
            for event in events
            if event.event_type == LineageEventType.FEEDBACK_RECORDED
            and event.payload.get("feedback_id") == feedback_id
        ),
        None,
    )
    if feedback is None:
        feedback = workflow.record_feedback(
            run_id,
            _verified_head(projection),
            question_id=args.question_id,
            idempotency_key=_key("feedback_record", run_id, feedback_id),
            simulated_fixture=simulated_fixture,
            human_attestation=human_attestation,
            operator_label=operator_label,
            operator_rationale=operator_rationale,
        )
        events, projection = _load(path, run_id)
    proposed = next(
        (
            event
            for event in events
            if event.event_type == LineageEventType.MEMORY_PROPOSED
            and any(reference.id == feedback.event_id for reference in event.references)
        ),
        None,
    )
    if proposed is None:
        proposed = workflow.propose_memory(
            run_id,
            _verified_head(projection),
            feedback_id=feedback_id,
            idempotency_key=_key("memory_propose", run_id, feedback_id),
        )
        _, projection = _load(path, run_id)
    return {
        "run_id": run_id,
        "answer_event_id": answered.event_id,
        "feedback_id": feedback_id,
        "memory_id": proposed.payload["memory_id"],
        "revision": proposed.payload["revision"],
        "head": _verified_head(projection).model_dump(mode="json"),
    }


def _memory(
    path: Path,
    args: argparse.Namespace,
    *,
    simulated_fixture: bool = False,
    human_attestation: bool = False,
    operator_label: str = "local-operator",
    operator_rationale: str | None = None,
) -> dict[str, object]:
    run_id = _find_run(
        path,
        LineageEventType.MEMORY_PROPOSED,
        "memory_id",
        args.memory_id,
    )
    events, projection = _load(path, run_id)
    proposed = next(
        event
        for event in events
        if event.event_type == LineageEventType.MEMORY_PROPOSED
        and event.payload.get("memory_id") == args.memory_id
    )
    expected_type = (
        LineageEventType.MEMORY_APPROVED
        if args.memory_action == "approve"
        else LineageEventType.MEMORY_REJECTED
    )
    decided = next(
        (
            event
            for event in events
            if event.event_type
            in {LineageEventType.MEMORY_APPROVED, LineageEventType.MEMORY_REJECTED}
            and event.payload.get("memory_id") == args.memory_id
        ),
        None,
    )
    if decided is not None and decided.event_type != expected_type:
        raise HumanWorkflowError("the memory already has another decision")
    if (
        decided is not None
        and (decided.truth_kind == TruthKind.SIMULATED_FIXTURE) != simulated_fixture
    ):
        raise HumanWorkflowError("the memory already has another provenance")
    if decided is None:
        workflow, _ = _workflow(path)
        decided = workflow.decide_memory(
            run_id,
            _verified_head(projection),
            memory_id=args.memory_id,
            revision=int(proposed.payload["revision"]),
            decision=MemoryDecisionValue(args.memory_action),
            idempotency_key=_key(
                "memory_decide", run_id, args.memory_id, args.memory_action
            ),
            simulated_fixture=simulated_fixture,
            human_attestation=human_attestation,
            operator_label=operator_label,
            operator_rationale=operator_rationale,
        )
        _, projection = _load(path, run_id)
    return {
        "run_id": run_id,
        "memory_id": args.memory_id,
        "decision_event_id": decided.event_id,
        "revision": decided.payload["revision"],
        "state": decided.payload["status"],
        "head": _verified_head(projection).model_dump(mode="json"),
    }


def _decision_actor(*, simulated_fixture: bool, human_attestation: bool) -> str:
    if simulated_fixture:
        return "simulated_fixture"
    if not human_attestation:
        raise HumanWorkflowError("human attestation requires an interactive TTY")
    return "human"


def _end_rejected_run(
    path: Path,
    run_id: str,
    decision_event_id: str,
    reason_code: str,
) -> Event:
    events, projection = _load(path, run_id)
    ended = next(
        (event for event in events if event.event_type == LineageEventType.RUN_ENDED),
        None,
    )
    if ended is not None:
        if (
            projection.state != LineageRunState.REJECTED
            or ended.payload.get("reason_code") != reason_code
            or not any(
                reference.id == decision_event_id for reference in ended.references
            )
        ):
            raise HumanWorkflowError("the run already ended with another decision")
        return ended
    decision = next(
        (event for event in events if event.event_id == decision_event_id),
        None,
    )
    if decision is None or decision is not events[-1]:
        raise HumanWorkflowError("the rejection decision is not the current run head")
    artifacts = SQLiteArtifactStore(path)
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    record = {
        "schema_version": 2,
        "action": "run.ended",
        "run_id": run_id,
        "decision_event_id": decision.event_id,
        "decision_event_sha256": decision.event_sha256,
        "reason_code": reason_code,
        "state": LineageRunState.REJECTED.value,
    }
    source = artifacts(EvidenceKind.OPERATOR_REQUEST, record)
    try:
        ended = store.append(
            run_id,
            _verified_head(projection),
            _key("run_rejected", run_id, decision.event_id, reason_code),
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=events[0].repo_id,
                base_sha=events[0].base_sha,
                agent_profile_id=events[0].agent_profile_id,
                policy_revision=events[0].policy_revision,
                event_type=LineageEventType.RUN_ENDED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.LIFECYCLE_SERVICE,
                references=(
                    EvidenceReference(
                        kind=EvidenceKind.EVENT,
                        id=decision.event_id,
                        sha256=decision.event_sha256,
                    ),
                ),
                source_ref=SourceReference(
                    kind=SourceKind.LIFECYCLE_REQUEST,
                    id=source.id,
                    sha256=source.sha256,
                ),
                payload={
                    "reason_code": reason_code,
                    "state": LineageRunState.REJECTED.value,
                    "status": "ended",
                },
            ),
        )
    except (EvidenceInvalid, LineageStoreError) as error:
        raise HumanWorkflowError("the rejected run could not end durably") from error
    if reduce_events((*events, ended)).state != LineageRunState.REJECTED:
        raise HumanWorkflowError("the rejected run did not reach a terminal state")
    return ended


def _prepare_candidate(
    path: Path,
    run_id: str,
) -> PreparedPromotionCandidate:
    artifacts = SQLiteArtifactStore(path)
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    prepared = prepare_verified_promotion(
        store,
        artifacts,
        run_id,
        decision_id="promotion_" + sha256_hex(run_id.encode())[:24],
        occurred_at=datetime.now(UTC),
        decision_actor=None,
    )
    if not isinstance(prepared, PreparedPromotionCandidate):
        raise PromotionError("promotion candidate preparation returned a decision")
    return prepared


def _reject_candidate(
    path: Path,
    run_id: str,
    *,
    simulated_fixture: bool,
    human_attestation: bool,
    operator_label: str,
    operator_rationale: str | None,
) -> dict[str, object]:
    events, projection = _load(path, run_id)
    existing = next(
        (
            event
            for event in events
            if event.event_type == LineageEventType.CANDIDATE_REJECTED
        ),
        None,
    )
    if existing is not None:
        expected_truth = (
            TruthKind.SIMULATED_FIXTURE
            if simulated_fixture
            else TruthKind.HUMAN_ATTESTED
        )
        if (
            existing.truth_kind != expected_truth
            or existing.payload.get("operator_label") != operator_label
            or existing.payload.get("operator_rationale") != operator_rationale
        ):
            raise HumanWorkflowError("the candidate already has another rejection")
        ended = _end_rejected_run(path, run_id, existing.event_id, "candidate_rejected")
        return {
            "run_id": run_id,
            "candidate_id": existing.payload["candidate_id"],
            "decision_event_id": existing.event_id,
            "end_event_id": ended.event_id,
            "state": LineageRunState.REJECTED.value,
            "head": _verified_head(_load(path, run_id)[1]).model_dump(mode="json"),
        }
    _review(path, run_id)
    request = _prepare_candidate(
        path,
        run_id,
    )
    actor = _decision_actor(
        simulated_fixture=simulated_fixture,
        human_attestation=human_attestation,
    )
    events, projection = _load(path, run_id)
    truth = (
        TruthKind.SIMULATED_FIXTURE
        if actor == "simulated_fixture"
        else TruthKind.HUMAN_ATTESTED
    )
    authority = (
        LineageAuthority.SIMULATED_FIXTURE
        if actor == "simulated_fixture"
        else LineageAuthority.OPERATOR_REQUEST
    )
    evidence_kind = (
        EvidenceKind.SIMULATED_FIXTURE
        if actor == "simulated_fixture"
        else EvidenceKind.OPERATOR_REQUEST
    )
    source_kind = (
        SourceKind.SIMULATED_FIXTURE
        if actor == "simulated_fixture"
        else SourceKind.OPERATOR_REQUEST
    )
    decision_id = "candidate_rejection_" + sha256_hex(run_id.encode())[:24]
    record = {
        "schema_version": 2,
        "action": "candidate.rejected",
        "run_id": run_id,
        "expected_head": _verified_head(projection).model_dump(mode="json"),
        "candidate_id": request.candidate_id,
        "candidate_patch_sha256": request.candidate_patch_sha256,
        "decision_id": decision_id,
        "actor": actor,
        "operator_label": operator_label,
        "operator_rationale": operator_rationale,
        "bindings": [
            reference.model_dump(mode="json")
            for reference in (
                request.candidate_reference,
                request.changeset_reference,
                request.test_reference,
                request.brief_reference,
                request.decision_reference,
                request.memory_reference,
            )
        ],
    }
    artifacts = SQLiteArtifactStore(path)
    source = artifacts(evidence_kind, record)
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    payload: dict[str, object] = {
        "candidate_id": request.candidate_id,
        "candidate_patch_sha256": request.candidate_patch_sha256,
        "decision_id": decision_id,
        "operator_label": operator_label,
        "status": "rejected",
    }
    if operator_rationale is not None:
        payload["operator_rationale"] = operator_rationale
    try:
        rejected = store.append(
            run_id,
            _verified_head(projection),
            _key("candidate_reject", run_id, request.candidate_id, decision_id),
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=request.repo_id,
                base_sha=request.base_sha,
                agent_profile_id=request.agent_profile_id,
                policy_revision=request.policy_revision,
                event_type=LineageEventType.CANDIDATE_REJECTED,
                truth_kind=truth,
                authority=authority,
                references=(
                    request.candidate_reference,
                    request.changeset_reference,
                    request.test_reference,
                    request.brief_reference,
                    request.decision_reference,
                    request.memory_reference,
                ),
                source_ref=SourceReference(
                    kind=source_kind,
                    id=source.id,
                    sha256=source.sha256,
                ),
                payload=payload,
            ),
        )
    except (EvidenceInvalid, LineageStoreError) as error:
        raise HumanWorkflowError("candidate rejection could not be recorded") from error
    ended = _end_rejected_run(path, run_id, rejected.event_id, "candidate_rejected")
    return {
        "run_id": run_id,
        "candidate_id": request.candidate_id,
        "decision_event_id": rejected.event_id,
        "end_event_id": ended.event_id,
        "state": LineageRunState.REJECTED.value,
        "head": _verified_head(_load(path, run_id)[1]).model_dump(mode="json"),
    }


def _replayable_handoff(
    events: tuple[Event, ...],
    args: argparse.Namespace,
    artifacts: SQLiteArtifactStore,
) -> CompiledHandoff | None:
    event = events[-1]
    if event.event_type != LineageEventType.CONTEXT_COMPILED:
        return None
    try:
        decision_ref = next(
            reference
            for reference in event.references
            if reference.kind == EvidenceKind.HANDOFF_DECISION
        )
        brief_ref = next(
            reference
            for reference in event.references
            if reference.kind == EvidenceKind.CONTEXT_BRIEF
        )
        decision_raw = artifacts.resolve(decision_ref.kind.value, decision_ref.id)
        brief_raw = artifacts.resolve(brief_ref.kind.value, brief_ref.id)
        decision = HandoffDecision.model_validate_json(decision_raw)
        brief = ContextBrief.model_validate_json(brief_raw)
    except (StopIteration, TypeError, ValueError) as error:
        raise HandoffCompileError("stored handoff compilation is invalid") from error
    if (
        len(event.references) != 2
        or decision.source_run_id != args.source_run_id
        or decision.target_profile_id != args.profile
        or decision.task_id != args.task
        or decision.decision != "allowed"
        or brief.source_run_id != args.source_run_id
        or brief.target_profile_id != args.profile
        or brief.task_id != args.task
        or decision.source_head.seq != event.seq - 1
        or decision.source_head.event_sha256 != event.previous_event_sha256
        or event.payload.get("decision_sha256") != decision.decision_sha256
        or event.payload.get("brief_sha256") != brief.brief_sha256
    ):
        return None
    return CompiledHandoff(decision=decision, brief=brief, denial=None)


def _existing_consumer_result(
    path: Path,
    compiled: CompiledHandoff,
) -> dict[str, object] | None:
    assert compiled.brief is not None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            "SELECT run_id, event_bytes FROM events WHERE seq = 1 ORDER BY run_id"
        ).fetchall()
    matches: list[dict[str, object]] = []
    for run_id, raw in rows:
        try:
            started = Event.model_validate_json(raw)
        except (TypeError, ValueError):
            continue
        if (
            started.payload.get("source_run_id") != compiled.decision.source_run_id
            or started.payload.get("context_compiled_event_sha256") is None
        ):
            continue
        events, _ = _load(path, str(run_id))
        injected = next(
            (
                event
                for event in events
                if event.event_type == LineageEventType.CONTEXT_INJECTED
                and event.payload.get("decision_sha256")
                == compiled.decision.decision_sha256
                and event.payload.get("brief_sha256") == compiled.brief.brief_sha256
            ),
            None,
        )
        if injected is None:
            continue
        matches.append(
            {
                "decision_sha256": compiled.decision.decision_sha256,
                "brief_sha256": compiled.brief.brief_sha256,
                "consumer_run_id": str(run_id),
                "session_id": injected.session_id,
                "invocation_id": injected.invocation_id,
                "head": VerifiedHead(
                    run_id=str(run_id),
                    seq=injected.seq,
                    event_sha256=injected.event_sha256,
                    event_count=injected.seq,
                ).model_dump(mode="json"),
            }
        )
    if len(matches) > 1:
        raise HandoffCompileError("handoff compilation has multiple consumers")
    return matches[0] if matches else None


def _promote(
    path: Path,
    run_id: str,
    *,
    simulated_fixture: bool = False,
    human_attestation: bool = False,
    operator_label: str = "local-operator",
    operator_rationale: str | None = None,
) -> dict[str, object]:
    events, projection = _load(path, run_id)
    artifacts = SQLiteArtifactStore(path)
    checkpoints = SQLiteCheckpointRecorder(path)
    store = SQLiteLineageStore(
        path,
        artifact_resolver=artifacts.resolve,
        checkpoint_reader=checkpoints.read,
    )
    if projection.state == LineageRunState.PROMOTED:
        approval = next(
            event
            for event in events
            if event.event_type == LineageEventType.PROMOTION_APPROVED
        )
        if (approval.truth_kind == TruthKind.SIMULATED_FIXTURE) != simulated_fixture:
            raise PromotionError("completed promotion has another provenance")
        retained = checkpoints.read(run_id)
        if len(retained) != 1 or store.verify(run_id) != _verified_head(projection):
            raise PromotionError("completed promotion checkpoint is unavailable")
        completion = next(
            event
            for event in events
            if event.event_type == LineageEventType.PROMOTION_COMPLETED
        )
        local = commit_promoted_run(
            path,
            run_id,
            allow_simulated_fixture=simulated_fixture,
        )
        return {
            "run_id": run_id,
            "state": LineageRunState.PROMOTED.value,
            "head": local.final_head.model_dump(mode="json"),
            "checkpoint_id": retained[0].checkpoint_id,
            "checkpoint_sha256": retained[0].checkpoint_sha256,
            "promotion_receipt_id": completion.payload["promotion_receipt_id"],
            "promotion_receipt_sha256": completion.payload["promotion_receipt_sha256"],
            "outcome": local.receipt.outcome,
            "local_commit_sha": local.receipt.local_commit_sha,
            "local_commit_receipt_id": local.receipt_reference.id,
            "local_commit_receipt_sha256": local.receipt_reference.sha256,
        }

    _review(path, run_id)
    events, _ = _load(path, run_id)
    _, golden, _, fixture, base_sha = _repository(None)
    checkout = path.parent / "checkouts" / run_id
    _checkout(
        checkout,
        checkout.parent,
        golden=golden,
        fixture=fixture,
        expected_base_sha=base_sha,
        expected_files=_expected_checkout_files(
            golden=golden,
            fixture=fixture,
            events=events,
            artifacts=artifacts,
        ),
        max_file_bytes=golden.fixture.max_write_bytes,
    )
    actor = _decision_actor(
        simulated_fixture=simulated_fixture,
        human_attestation=human_attestation,
    )
    request = prepare_verified_promotion(
        store,
        artifacts,
        run_id,
        decision_id="promotion_" + sha256_hex(run_id.encode())[:24],
        occurred_at=datetime.now(UTC),
        decision_actor=actor,
        operator_label=operator_label,
        operator_rationale=operator_rationale,
    )
    if not isinstance(request, PromotionRequest):
        raise PromotionError("promotion approval was not prepared")

    def trusted_retest(retest) -> PromotionRetestResult:
        rerun = run_fixture_tests(checkout, golden.fixture)
        return PromotionRetestResult(
            authoritative_test_receipt_sha256=canonical_json_sha256(
                {
                    "bound_candidate": retest.candidate_patch_sha256,
                    "command": list(golden.fixture.fixed_test_command),
                    "exit_code": rerun.exit_code,
                    "output_sha256": sha256_hex(rerun.output.encode()),
                    "timed_out": rerun.timed_out,
                }
            ),
            retest_base_sha=retest.base_sha,
            passed=rerun.exit_code == 0,
            timed_out=rerun.timed_out,
        )

    outcome = promote(
        store,
        request,
        record_artifact=artifacts,
        reconstruct_and_retest=trusted_retest,
        record_checkpoint=checkpoints,
        allow_simulated_fixture=simulated_fixture,
    )
    local = commit_promoted_run(
        path,
        run_id,
        allow_simulated_fixture=simulated_fixture,
    )
    return {
        "run_id": run_id,
        "state": LineageRunState.PROMOTED.value,
        "head": local.final_head.model_dump(mode="json"),
        "checkpoint_id": outcome.checkpoint.checkpoint_id,
        "checkpoint_sha256": outcome.checkpoint.checkpoint_sha256,
        "promotion_receipt_id": outcome.receipt_reference.id,
        "promotion_receipt_sha256": outcome.receipt.receipt_sha256,
        "outcome": local.receipt.outcome,
        "local_commit_sha": local.receipt.local_commit_sha,
        "local_commit_receipt_id": local.receipt_reference.id,
        "local_commit_receipt_sha256": local.receipt_reference.sha256,
    }


def _handoff(path: Path, args: argparse.Namespace) -> dict[str, object]:
    events, projection = _load(path, args.source_run_id)
    repository, golden, graph, _, base_sha = _repository(None)
    del repository
    task = next(item for item in golden.tasks if item.task_id.value == args.task)
    profile = next(
        item for item in graph.catalog if item.agent_profile_id == args.profile
    )
    fixture_paths = set(golden.fixture.tracked_paths) | set(
        golden.fixture.mutable_paths
    )
    read_scope = tuple(
        sorted(
            candidate
            for candidate in fixture_paths
            if any(fnmatchcase(candidate, pattern) for pattern in profile.allowed_paths)
        )
    )
    selected = tuple(
        sorted(
            {
                reference.id
                for event in events
                if event.event_type == LineageEventType.FEEDBACK_RECORDED
                for reference in event.references
                if reference.kind == EvidenceKind.HUNK
            }
        )
    )
    artifacts = SQLiteArtifactStore(path)
    replay = _replayable_handoff(events, args, artifacts)
    if replay is not None:
        if not args.start:
            return {
                "decision": replay.decision.model_dump(mode="json"),
                "brief": replay.brief.model_dump(mode="json"),
            }
        existing = _existing_consumer_result(path, replay)
        if existing is not None:
            return existing
        consumer = start_fresh_consumer(replay, path)
        if not isinstance(consumer, FreshConsumer):
            raise HandoffCompileError("allowed handoff did not create a consumer")
        return {
            "decision_sha256": replay.decision.decision_sha256,
            "brief_sha256": replay.brief.brief_sha256,
            "consumer_run_id": consumer.run_id,
            "session_id": consumer.session_id,
            "invocation_id": consumer.invocation_id,
            "head": consumer.handle.head.model_dump(mode="json"),
        }
    namespace = canonical_json_sha256(
        {
            "source_run_id": args.source_run_id,
            "source_head": projection.head_sha256,
            "task_id": args.task,
            "profile_id": args.profile,
        }
    )
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    compiled = compile_verified_handoff(
        store=store,
        artifacts=artifacts,
        decision_id="handoff_" + namespace[:24],
        brief_id="brief_" + namespace[:24],
        source_run_id=args.source_run_id,
        source_session_id=next(
            (event.session_id for event in events if event.session_id is not None),
            None,
        ),
        source_graph_sha256=projection.projection_sha256,
        repo_id=golden.repo_id,
        base_sha=base_sha,
        task=task,
        target_profile=profile,
        target_profile_revision=int(profile.agent_profile_id.rsplit("@", 1)[1]),
        policy_revision=profile.policy_revision,
        selected_evidence_ids=selected,
        policy_required_paths=(golden.memory.required_test_path,),
        read_scope=read_scope,
        write_scope=task.expected_changed_paths,
        capabilities=(AUTH_CAPABILITIES if args.profile == "auth-maintainer@1" else ()),
        fixed_test_profile=graph.required_test_profile,
        byte_caps={"read": 32_768, "result": 16_384, "write": 32_768},
        event_caps={"run": 1_000},
        server_recorded_at=datetime.now(UTC),
    )
    if isinstance(compiled.denial, HandoffDenied):
        denial = bind_and_dispatch(
            compiled=compiled,
            store=store,
            artifacts=artifacts,
            source_expected_head=compiled.decision.source_head,
            expected_decision_sha256=compiled.decision.decision_sha256,
            expected_brief_sha256=None,
            consumer_run_id=None,
            session_id=None,
            invocation_id=None,
            model_id=None,
            injection_receipt_id=None,
            prompt=None,
            fixture_policy=None,
            checkout_factory=None,
            dispatch_callback=None,
            context_compiled_idempotency_key=_key("handoff_denied", namespace),
            consumer_started_idempotency_key="unused_consumer_start",
            context_injected_idempotency_key="unused_context_injection",
            injected_at=datetime.now(UTC),
        )
        assert isinstance(denial, HandoffDenied)
        return {
            "decision": compiled.decision.model_dump(mode="json"),
            "denial": denial.model_dump(mode="json"),
        }
    if not args.start:
        assert compiled.brief is not None
        return {
            "decision": compiled.decision.model_dump(mode="json"),
            "brief": compiled.brief.model_dump(mode="json"),
        }
    consumer = start_fresh_consumer(compiled, path)
    if not isinstance(consumer, FreshConsumer):
        raise HandoffCompileError("allowed handoff did not create a consumer")
    return {
        "decision_sha256": compiled.decision.decision_sha256,
        "brief_sha256": compiled.brief.brief_sha256 if compiled.brief else None,
        "consumer_run_id": consumer.run_id,
        "session_id": consumer.session_id,
        "invocation_id": consumer.invocation_id,
        "head": consumer.handle.head.model_dump(mode="json"),
    }


def _write_result(value: dict[str, object], *, json_mode: bool) -> None:
    if json_mode:
        sys.stdout.write(canonical_json_bytes(value).decode() + "\n")
    else:
        fields = " ".join(
            f"{key}={item}"
            for key, item in value.items()
            if not isinstance(item, (dict, list))
        )
        sys.stdout.write(f"GRAPHENE {fields}\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mission_alias = (
        args.command
        in {
            "bundle",
            "cancel",
            "doctor",
            "init",
            "mission",
            "plan",
            "request-replan",
            "retry",
            "status",
            "task",
        }
        or (args.command == "run" and args.profile is None)
        or (
            args.command == "watch"
            and (
                not args.run_id.startswith("run_")
                or os.environ.get("GRAPHENE_MISSION_ID") == args.run_id
            )
        )
        or (args.command == "why" and args.run_id is None)
    )
    if mission_alias:
        from .mission import handle as handle_mission

        return handle_mission(args, json_mode=args.json_mode)
    if args.command == "run":
        return _run(args)
    if args.command == "demo":
        from ..demo import DemoError, run_demo

        try:
            return run_demo(
                driver=args.driver,
                speed=args.speed,
                no_open=args.no_open,
                cleanup=args.cleanup,
                keep_open=not args.exit_after_demo,
                automated_fixture=args.automated_fixture,
            )
        except DemoError as error:
            sys.stderr.write(f"DEMO_ERROR: {error}\n")
            return 1

    try:
        path = _database_path()
        if args.command == "review":
            _write_result(_review(path, args.run_id), json_mode=args.json_mode)
            return 0
        if args.command == "feedback":
            _write_result(_feedback(path, args), json_mode=args.json_mode)
            return 0
        if args.command == "answer":
            _write_result(
                _answer(
                    path,
                    args,
                    human_attestation=(sys.stdin.isatty() and sys.stdout.isatty()),
                    operator_label=args.operator_label,
                    operator_rationale=args.rationale,
                ),
                json_mode=args.json_mode,
            )
            return 0
        if args.command == "memory":
            result = _memory(
                path,
                args,
                human_attestation=(sys.stdin.isatty() and sys.stdout.isatty()),
                operator_label=args.operator_label,
                operator_rationale=args.rationale,
            )
            if args.memory_action == "reject":
                ended = _end_rejected_run(
                    path,
                    str(result["run_id"]),
                    str(result["decision_event_id"]),
                    "memory_rejected",
                )
                result.update(
                    state=LineageRunState.REJECTED.value,
                    end_event_id=ended.event_id,
                    head=_verified_head(
                        _load(path, str(result["run_id"]))[1]
                    ).model_dump(mode="json"),
                )
            _write_result(result, json_mode=args.json_mode)
            return 0
        if args.command == "handoff":
            _write_result(_handoff(path, args), json_mode=args.json_mode)
            return 0
        if args.command == "promote":
            human_attestation = sys.stdin.isatty() and sys.stdout.isatty()
            result = (
                _promote(
                    path,
                    args.consumer_run_id,
                    human_attestation=human_attestation,
                    operator_label=args.operator_label,
                    operator_rationale=args.rationale,
                )
                if args.decision == "commit"
                else _reject_candidate(
                    path,
                    args.consumer_run_id,
                    simulated_fixture=False,
                    human_attestation=human_attestation,
                    operator_label=args.operator_label,
                    operator_rationale=args.rationale,
                )
            )
            _write_result(
                result,
                json_mode=args.json_mode,
            )
            return 0
        if args.command in {"inspect", "why"}:
            artifacts = SQLiteArtifactStore(path, read_only=True)
            store = SQLiteLineageStore(
                path,
                artifact_resolver=artifacts.resolve,
                read_only=True,
            )
            if args.command == "inspect":
                output = (
                    canonical_json_bytes(
                        inspect_run_item(
                            store,
                            artifacts,
                            args.run_id,
                            args.evidence_id,
                        )
                    ).decode()
                    + "\n"
                )
            else:
                output = _render_explanation(
                    explain_path(store, artifacts, args.run_id, args.path),
                    json_mode=args.json_mode,
                )
            sys.stdout.write(output)
            return 0
        if args.command == "watch":
            _watch(
                path,
                args.run_id,
                after_seq=args.after_seq,
                snapshot=args.snapshot,
                json_mode=args.json_mode,
            )
            return 0
        events, projection = _load(path, args.run_id)
        if args.command == "replay":
            _replay(
                events,
                projection,
                speed=args.speed,
                json_mode=args.json_mode,
            )
            return 0
        raise AssertionError("unreachable CLI command")
    except KeyboardInterrupt:
        return 130
    except _ConfigurationError as error:
        sys.stderr.write(f"CONFIG_ERROR: {error}\n")
        return 1
    except _NotFound:
        sys.stderr.write("NOT_FOUND: no matching committed lineage evidence\n")
        return 1
    except ExplainNotFound:
        sys.stderr.write("NOT_FOUND: no matching committed lineage evidence\n")
        return 1
    except ExplainEvidenceError:
        sys.stderr.write("EVIDENCE_INVALID: unable to explain verified lineage\n")
        return 1
    except (
        BootstrapError,
        ConsumerStartError,
        HandoffCompileError,
        HumanWorkflowError,
        LocalCommitError,
        PromotionError,
        RuntimeBindingError,
    ):
        sys.stderr.write("WORKFLOW_ERROR: operation rejected\n")
        return 1
    except EvidenceInvalid as error:
        return _evidence_invalid(error.state)
    except ProjectionError as error:
        return _evidence_invalid(error.as_state())
    except (LineageStoreError, ObservationError, sqlite3.Error, OSError, ValueError):
        sys.stderr.write("DATABASE_ERROR: unable to open or verify lineage database\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
