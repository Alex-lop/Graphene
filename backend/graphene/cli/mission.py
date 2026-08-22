from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import uvicorn

from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..models import TruthKind
from ..orchestration.evidence import SQLiteAttemptEvidenceStore, TrustedCheckReceipt
from ..orchestration.cloud_protocol import ExecutorArtifactObservation
from ..orchestration.executor_client import (
    CoordinatorClient,
    ExecutorCompletion,
    GoogleAdcAudienceTokenProvider,
)
from ..orchestration.local_executor import run_local_executor
from ..orchestration.adk import (
    AdkPlanner,
    PlannerError,
    PlanningExcerpt,
    PlanningRequest,
)
from ..orchestration.local_result import (
    LocalResultReceipt,
    finalize_local_result_decision,
    prepare_local_final_result_bundle,
    verified_result_artifacts,
    verify_local_result_receipt,
)
from ..orchestration.models import (
    AttemptResult,
    AttemptState,
    CommandTemplate,
    Dispatch,
    Mission,
    MissionHead,
    MissionStatus,
    NetworkPolicy,
    ProjectPolicy,
    ResourceBudget,
    RetentionPolicy,
    Task,
    TaskKind,
)
from ..orchestration.overlap import measure_overlap
from ..orchestration.runtime import (
    WORKER_PROVIDER_RECEIPT_KIND,
    CheckOutcome,
    DockerCheckRunner,
    HostSandboxCheckRunner,
    RuntimeAssignment,
    WorkerProviderReceipt,
    WorkerRegistry,
    WorkerRuntime,
)
from ..orchestration.runner import (
    AcceptedArtifactCache,
    MissionRunner,
    RunnerCancelled,
    RunnerError,
)
from ..orchestration.resource_control import ResourceDispatchController
from ..orchestration.resources import (
    DispatchGovernorPolicy,
    OwnedProcess,
    ProcessIdentityError,
    ResourcePoint,
    process_tree_rss_point,
    read_process_identity,
    sample_owned_process_tree,
)
from ..orchestration.sandbox import DockerExecutor
from ..orchestration.scheduler import MissionScheduler, SystemClock
from ..orchestration.process_control import (
    OwnedProcessRegistry,
    ProcessControlError,
)
from ..orchestration.scripted import (
    DEFAULT_SCENARIO_PATH,
    ScriptedError,
    ScriptedMissionRun,
    execute_scripted_mission,
    initialize_fixture_repository,
    load_scenario,
    propose_scripted_mission,
    scripted_plan_validation,
    scripted_result_artifacts,
    scripted_supported,
)
from ..orchestration.workers import GeminiWorkerAdapter


_MISSION_COMMANDS = (
    "approve-plan",
    "approve-result",
    "cancel",
    "decide-gate",
    "open",
    "pause",
    "reject-result",
    "request-replan",
    "result",
    "capsule",
    "replay",
    "resume",
    "retry",
    "start",
    "status",
    "watch",
    "db",
    "demo",
    "executor",
)


class MissionCliError(RuntimeError):
    pass


def _positive(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be positive") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _nonnegative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "value must be a non-negative integer"
        ) from error
    if number < 0 or str(number) != value:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return number


def _revision(value: str) -> int:
    number = _nonnegative(value)
    if number < 1:
        raise argparse.ArgumentTypeError("revision must be a positive integer")
    return number


def _worker_count(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "max-workers must be an integer from 1 to 5"
        ) from error
    if not 1 <= number <= 5:
        raise argparse.ArgumentTypeError("max-workers must be an integer from 1 to 5")
    return number


def _gemini_worker_count(value: str) -> int:
    number = _worker_count(value)
    if number < 2:
        raise argparse.ArgumentTypeError(
            "Gemini max-workers must be an integer from 2 to 5"
        )
    return number


def _outbound_worker_count(value: str) -> int:
    number = _worker_count(value)
    if number < 2:
        raise argparse.ArgumentTypeError("workers must be an integer from 2 to 5")
    return number


def _sha256(value: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise argparse.ArgumentTypeError("candidate-sha must be lowercase SHA-256")
    return value


def _bundle_identifier(value: str) -> str:
    if re.fullmatch(r"final_result_[0-9a-f]{32}", value) is None:
        raise argparse.ArgumentTypeError("bundle-id must be an exact final_result_* ID")
    return value


def _mission_parser(
    commands: argparse._SubParsersAction,
    name: str,
    *,
    summary: str,
    example: str,
    failure: str,
) -> argparse.ArgumentParser:
    return commands.add_parser(
        name,
        allow_abbrev=False,
        help=summary,
        description=summary,
        epilog=f"Example: {example}\nFails: {failure}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _option_help(summary: str, example: str, failure: str) -> str:
    return f"{summary}; e.g. {example}; fails if {failure}"


def _operator(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--operator-label",
        default="local-operator",
        help=_option_help(
            "public decision label, never a credential",
            "--operator-label alex",
            "the label is invalid",
        ),
    )
    parser.add_argument(
        "--rationale",
        help=_option_help(
            "optional public rationale, max 280 chars",
            "--rationale 'Reviewed checks'",
            "the rationale exceeds the bound",
        ),
    )
    parser.add_argument(
        "--confirm-human",
        action="store_true",
        help=_option_help(
            "attest deliberate interactive input",
            "--confirm-human",
            "stdin or stdout is not a TTY",
        ),
    )
    parser.add_argument(
        "--command-id",
        type=_command_key,
        help=_option_help(
            "stable idempotency key for transport retries",
            "--command-id approve_plan_0001",
            "it is not 16-128 safe characters",
        ),
    )


def _command_key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", value):
        raise argparse.ArgumentTypeError(
            "command-id must be 16-128 letters, digits, underscores, or hyphens"
        )
    return value


def register_commands(commands: argparse._SubParsersAction) -> None:
    initialize = commands.add_parser(
        "init",
        allow_abbrev=False,
        help="write one deny-by-default .graphene project policy",
        description="Initialize policy only; this never runs a worker or changes source files.",
    )
    initialize.add_argument(
        "--repo", required=True, type=Path, help="clean Git repository to initialize"
    )

    doctor = commands.add_parser(
        "doctor",
        allow_abbrev=False,
        help="run a read-only local/cloud preflight without testing credentials",
        description="Reports configuration hints only; it performs no provider call or cloud write.",
    )
    doctor.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="repository whose policy to inspect",
    )

    plan = commands.add_parser(
        "plan",
        allow_abbrev=False,
        help="compile a bounded goal into a persisted proposal",
        description="Propose only; execution requires a separate graphene run command.",
    )
    plan.add_argument(
        "goal", help="bounded goal, or the literal lint, show, or diff action"
    )
    plan.add_argument(
        "plan_id",
        nargs="?",
        help="mission ID for a plan action; otherwise the goal must be quoted",
    )
    plan.add_argument(
        "previous_revision", nargs="?", type=_revision, help="plan diff source revision"
    )
    plan.add_argument(
        "revision", nargs="?", type=_revision, help="plan diff target revision"
    )
    plan.add_argument("--repo", type=Path)
    plan.add_argument(
        "--success-criterion",
        action="append",
        default=[],
        dest="success_criteria",
        help="repeatable explicit acceptance criterion",
    )
    plan.add_argument(
        "--driver",
        choices=("scripted-local", "gemini-adk"),
        default="gemini-adk",
        help="gemini-adk is live and never falls back to the scripted fixture",
    )
    plan.add_argument("--max-workers", type=_worker_count, default=2)
    plan.add_argument("--command-id", type=_command_key)
    plan.add_argument("--open", action="store_true", dest="open_viewer")
    plan.set_defaults(auto_approve=False)

    cancel_alias = commands.add_parser(
        "cancel",
        allow_abbrev=False,
        help="cancel a mission and only its strongly owned processes",
    )
    cancel_alias.add_argument("mission_id", help="exact mission ID")
    cancel_alias.add_argument(
        "--confirm", required=True, help="must exactly equal the mission ID"
    )
    _operator(cancel_alias)
    cancel_alias.set_defaults(mission_action="cancel")

    retry_alias = commands.add_parser(
        "retry",
        allow_abbrev=False,
        help="retry one eligible failed task within policy limits",
    )
    retry_alias.add_argument("mission_id", help="exact mission ID")
    retry_alias.add_argument(
        "--task", required=True, dest="task_id", help="exact failed task ID"
    )
    _operator(retry_alias)
    retry_alias.set_defaults(mission_action="retry")

    replan_alias = commands.add_parser(
        "request-replan",
        allow_abbrev=False,
        help="pause and record a request without inventing a new plan revision",
    )
    replan_alias.add_argument("mission_id", help="exact mission ID")
    replan_alias.add_argument(
        "--reason", required=True, help="public bounded reason for pausing"
    )
    _operator(replan_alias)
    replan_alias.set_defaults(mission_action="request-replan")

    task = commands.add_parser(
        "task", allow_abbrev=False, help="provide bounded private task input"
    )
    task_actions = task.add_subparsers(dest="task_action", required=True)
    task_input = task_actions.add_parser("input", allow_abbrev=False)
    task_input.add_argument("mission_id", help="exact mission ID")
    task_input.add_argument("task_id", help="exact task waiting for input")
    task_input.add_argument("--gate", required=True, dest="gate_id")
    source = task_input.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--file", type=Path, dest="input_file", help="regular UTF-8 file, max 4096 bytes"
    )
    source.add_argument(
        "--stdin",
        action="store_true",
        dest="input_stdin",
        help="read at most 4096 UTF-8 bytes from standard input",
    )
    _operator(task_input)

    status = commands.add_parser(
        "status", allow_abbrev=False, help="read one verified mission projection"
    )
    status.add_argument("mission_id")

    bundle = commands.add_parser(
        "bundle",
        allow_abbrev=False,
        help="create or verify a local final-result bundle",
        description=(
            "Creation prepares the immutable pending review bundle. Verification accepts an "
            "explicit file or an exact locally persisted bundle ID."
        ),
    )
    bundle_actions = bundle.add_subparsers(dest="bundle_action", required=True)
    create_bundle = bundle_actions.add_parser("create", allow_abbrev=False)
    create_bundle.add_argument("mission_id")
    create_bundle.add_argument("--output", required=True, type=Path)
    verify_bundle = bundle_actions.add_parser("verify", allow_abbrev=False)
    verify_bundle.add_argument("bundle", help="bundle file or final_result_* ID")

    mission = commands.add_parser(
        "mission",
        allow_abbrev=False,
        help="plan, run, review, and inspect bounded missions",
        description=(
            "Operate one durable bounded mission. Mutations require the current "
            "committed state and fail closed on stale, invalid, or unauthorized input."
        ),
        epilog=(
            "Example: graphene mission status mission_123\n"
            "Fails: mutations stop on stale, invalid, or unauthorized input"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    actions = mission.add_subparsers(dest="mission_action", required=True)

    start = _mission_parser(
        actions,
        "start",
        summary="persist a validated proposal; live drivers never fall back to fixtures",
        example=(
            "graphene mission start --repo . --goal 'Add status export' "
            "--success-criterion 'Tests pass' --driver gemini-adk --max-workers 2"
        ),
        failure="policy, Git, credentials, criteria, or worker bounds are invalid",
    )
    start.add_argument(
        "--repo",
        required=True,
        type=Path,
        help=_option_help(
            "initialized Git repository",
            "--repo .",
            "the policy, HEAD, or worktree is invalid",
        ),
    )
    start.add_argument(
        "--goal",
        required=True,
        help=_option_help(
            "bounded public mission goal",
            "--goal 'Add status export'",
            "the goal is empty or unbounded",
        ),
    )
    start.add_argument(
        "--success-criterion",
        action="append",
        default=[],
        dest="success_criteria",
        help=_option_help(
            "repeatable acceptance criterion, required by gemini-adk",
            "--success-criterion 'Tests pass'",
            "live execution has no explicit criterion",
        ),
    )
    start.add_argument(
        "--driver",
        choices=("scripted-local", "adk-fake", "gemini-adk"),
        default="scripted-local",
        help=_option_help(
            "execution driver; adk-fake is test-only",
            "--driver gemini-adk",
            "the driver is unsupported; Gemini never falls back",
        ),
    )
    start.add_argument(
        "--max-workers",
        type=_worker_count,
        default=2,
        help=_option_help(
            "bounded worker capacity, 1-5; Gemini requires 2-5",
            "--max-workers 2",
            "the count is outside the driver bounds",
        ),
    )
    start.add_argument(
        "--auto-approve",
        action="store_true",
        help=_option_help(
            "scripted fixture approval, always simulated",
            "--auto-approve",
            "the selected driver is not scripted-local",
        ),
    )
    start.add_argument(
        "--command-id",
        type=_command_key,
        help=_option_help(
            "stable idempotency key",
            "--command-id mission_start_0001",
            "it is not 16-128 safe characters",
        ),
    )
    start.add_argument(
        "--open",
        action="store_true",
        dest="open_viewer",
        help=_option_help(
            "open authenticated local Mission Control",
            "--open",
            "the private viewer cannot start",
        ),
    )

    status = _mission_parser(
        actions,
        "status",
        summary="read one verified projection",
        example="graphene mission status mission_123",
        failure="the mission is missing or its authority cannot be verified",
    )
    status.add_argument("mission_id", help="exact mission ID")
    open_control = _mission_parser(
        actions,
        "open",
        summary="open live local Mission Control with separate read/write tokens",
        example="graphene mission open mission_123",
        failure="the mission is unverified or the private server cannot bind",
    )
    open_control.add_argument("mission_id", help="exact mission ID")

    for name, detail, example, failure in (
        (
            "pause",
            "pause new dispatch without killing committed work",
            "graphene mission pause mission_123 --confirm-human",
            "the mission head is stale or the transition is not allowed",
        ),
        (
            "resume",
            "resume a safely paused mission",
            "graphene mission resume mission_123 --confirm-human",
            "the mission head is stale or the mission is not paused",
        ),
    ):
        command = _mission_parser(
            actions,
            name,
            summary=detail,
            example=example,
            failure=failure,
        )
        command.add_argument("mission_id", help="exact mission ID")
        _operator(command)

    watch = _mission_parser(
        actions,
        "watch",
        summary="read a bounded event tail",
        example="graphene mission watch mission_123 --after-seq 8 --snapshot",
        failure="the cursor is invalid or mission verification fails",
    )
    watch.add_argument("mission_id", help="exact mission ID")
    watch.add_argument(
        "--after-seq",
        type=_nonnegative,
        default=0,
        help=_option_help(
            "exclusive event sequence cursor",
            "--after-seq 8",
            "the value is not a non-negative integer",
        ),
    )
    watch.add_argument(
        "--snapshot",
        action="store_true",
        help=_option_help(
            "include the verified current projection",
            "--snapshot",
            "the projection cannot be verified",
        ),
    )

    cancel = _mission_parser(
        actions,
        "cancel",
        summary="cancel the mission and only its strongly owned processes",
        example=(
            "graphene mission cancel mission_123 --confirm mission_123 "
            "--confirm-human"
        ),
        failure="confirmation, ownership cleanup, head, or transition validation fails",
    )
    cancel.add_argument("mission_id", help="exact mission ID")
    cancel.add_argument(
        "--confirm",
        required=True,
        help=_option_help(
            "exact mission confirmation",
            "--confirm mission_123",
            "it does not equal the mission ID",
        ),
    )
    _operator(cancel)

    retry = _mission_parser(
        actions,
        "retry",
        summary="retry one eligible failed task within policy limits",
        example="graphene mission retry mission_123 --task work_a --confirm-human",
        failure="the task is ineligible, stale, unknown, or over its attempt limit",
    )
    retry.add_argument("mission_id", help="exact mission ID")
    retry.add_argument(
        "--task",
        required=True,
        dest="task_id",
        help=_option_help(
            "exact failed task ID",
            "--task work_a",
            "the task is missing or not retryable",
        ),
    )
    _operator(retry)

    replan = _mission_parser(
        actions,
        "request-replan",
        summary="pause and record a request without inventing a plan revision",
        example=(
            "graphene mission request-replan mission_123 --reason 'Scope changed' "
            "--confirm-human"
        ),
        failure="the reason, head, or mission transition is invalid",
    )
    replan.add_argument("mission_id", help="exact mission ID")
    replan.add_argument(
        "--reason",
        required=True,
        help=_option_help(
            "public bounded reason for pausing",
            "--reason 'Scope changed'",
            "the reason is empty or exceeds its bound",
        ),
    )
    _operator(replan)

    approve_plan = _mission_parser(
        actions,
        "approve-plan",
        summary="approve one exact validated plan revision",
        example=(
            "graphene mission approve-plan mission_123 --revision 1 --confirm-human"
        ),
        failure="the revision, head, validation, or human attestation is invalid",
    )
    approve_plan.add_argument("mission_id", help="exact mission ID")
    approve_plan.add_argument(
        "--revision",
        required=True,
        type=int,
        help=_option_help(
            "exact validated plan revision",
            "--revision 1",
            "the revision is not the current validated proposal",
        ),
    )
    _operator(approve_plan)

    decide = _mission_parser(
        actions,
        "decide-gate",
        summary="choose one exact allowed gate consequence",
        example=(
            "graphene mission decide-gate mission_123 --gate gate_1 "
            "--decision redact --confirm-human"
        ),
        failure="the gate, decision, head, or attestation is invalid",
    )
    decide.add_argument("mission_id", help="exact mission ID")
    decide.add_argument(
        "--gate",
        required=True,
        dest="gate_id",
        help=_option_help(
            "exact pending gate ID",
            "--gate gate_1",
            "the gate is missing or no longer pending",
        ),
    )
    decide.add_argument(
        "--decision",
        required=True,
        help=_option_help(
            "one option declared by that gate",
            "--decision redact",
            "the option is not declared by the gate",
        ),
    )
    _operator(decide)

    for name in ("approve-result", "reject-result"):
        result = _mission_parser(
            actions,
            name,
            summary=(
                "approve and isolate"
                if name == "approve-result"
                else "reject without commit"
            )
            + " the exact verified candidate",
            example=(
                f"graphene mission {name} mission_123 "
                f"--bundle-id final_result_{'a' * 32} --confirm-human"
            ),
            failure="the bundle, head, verification, transition, or attestation fails",
        )
        result.add_argument("mission_id", help="exact mission ID")
        result.add_argument(
            "--bundle-id",
            required=True,
            type=_bundle_identifier,
            help=_option_help(
                "exact immutable bundle ID displayed before the decision",
                f"--bundle-id final_result_{'a' * 32}",
                "it is malformed, stale, missing, or unverified",
            ),
        )
        _operator(result)

    result = _mission_parser(
        actions,
        "result",
        summary="inspect or explicitly export a verified isolated candidate",
        example="graphene mission result show mission_123",
        failure="the candidate or its evidence cannot be verified",
    )
    result_actions = result.add_subparsers(dest="result_action", required=True)
    show_result = _mission_parser(
        result_actions,
        "show",
        summary="verify and display candidate checks and its isolated reference",
        example="graphene mission result show mission_123",
        failure="the candidate, receipt, checks, or mission authority is invalid",
    )
    show_result.add_argument("mission_id", help="exact mission ID")
    export_result = _mission_parser(
        result_actions,
        "export",
        summary="write a verified candidate patch without touching the checkout",
        example=(
            "graphene mission result export mission_123 --candidate-sha "
            f"{'a' * 64} --output candidate.patch"
        ),
        failure="verification fails or the output exists, is a symlink, or is unsafe",
    )
    export_result.description = (
        "Write a verified candidate patch without touching the checkout. Graphene never "
        "applies it automatically."
    )
    export_result.epilog = (
        f"Example: graphene mission result export mission_123 --candidate-sha {'a' * 64} "
        "--output candidate.patch\n"
        "Verify with: git apply --check candidate.patch\n"
        "Apply explicitly with: git apply candidate.patch\n"
        "Fails: candidate verification fails or the output exists, is a symlink, or is unsafe"
    )
    export_result.add_argument("mission_id", help="exact mission ID")
    export_result.add_argument(
        "--candidate-sha",
        required=True,
        type=_sha256,
        help=_option_help(
            "exact candidate SHA-256 shown by result show",
            f"--candidate-sha {'a' * 64}",
            "it is malformed or does not match the verified candidate",
        ),
    )
    export_result.add_argument(
        "--output",
        required=True,
        type=Path,
        help=_option_help(
            "new patch file; never overwrites files or symlinks",
            "--output candidate.patch",
            "the path exists or cannot be created safely",
        ),
    )

    capsule = _mission_parser(
        actions,
        "capsule",
        summary="export or cold-verify a redacted self-verifying mission capsule",
        example="graphene mission capsule export mission_123 --output ./capsules",
        failure="the mission cannot be verified or the capsule directory exists",
    )
    capsule_actions = capsule.add_subparsers(dest="capsule_action", required=True)
    export_capsule = _mission_parser(
        capsule_actions,
        "export",
        summary="write MISSION_ID.graphene-capsule from verified mission authority",
        example="graphene mission capsule export mission_123 --output ./capsules",
        failure="the mission or its evidence cannot be verified or the capsule exists",
    )
    export_capsule.description = (
        "Write a private MISSION_ID.graphene-capsule directory holding the "
        "hash-chained mission events, attempt evidence chains, trusted check and "
        "sanitized worker receipts, publication envelope digests, plan revisions, "
        "and the registered final bundle. It contains no prompts, source bytes, "
        "diffs, command output, environment values, or credentials."
    )
    export_capsule.epilog = (
        "Example: graphene mission capsule export mission_123 --output ./capsules\n"
        "Verify with: graphene mission capsule verify "
        "./capsules/mission_123.graphene-capsule\n"
        "Fails: the mission or its evidence cannot be verified, the output "
        "directory is missing or a symlink, or the capsule already exists"
    )
    export_capsule.add_argument("mission_id", help="exact mission ID")
    export_capsule.add_argument(
        "--output",
        required=True,
        type=Path,
        help=_option_help(
            "existing directory that receives a new MISSION_ID.graphene-capsule",
            "--output ./capsules",
            "the directory is missing or a symlink, or the capsule already exists",
        ),
    )
    verify_capsule = _mission_parser(
        capsule_actions,
        "verify",
        summary="recompute every digest and chain link from the capsule files alone",
        example=(
            "graphene mission capsule verify ./capsules/mission_123.graphene-capsule"
        ),
        failure=(
            "a manifest, event chain, evidence chain, receipt, bundle, envelope, or "
            "plan check fails; this command never opens the mission store"
        ),
    )
    verify_capsule.add_argument(
        "capsule_dir", type=Path, help="path of a *.graphene-capsule directory"
    )

    database = _mission_parser(
        actions,
        "db",
        summary="inspect or verify the versioned local mission authority",
        example="graphene mission db verify",
        failure="the database schema, ledger, state root, or artifact proof is invalid",
    )
    database_actions = database.add_subparsers(dest="db_action", required=True)
    _mission_parser(
        database_actions,
        "status",
        summary="show schema and migration status",
        example="graphene mission db status",
        failure="the database cannot be opened safely",
    )
    _mission_parser(
        database_actions,
        "verify",
        summary="fully verify every local mission",
        example="graphene mission db verify",
        failure="any schema, ledger, state root, or artifact check fails",
    )
    migrate = _mission_parser(
        database_actions,
        "migrate",
        summary="inspect the safe migration action",
        example="graphene mission db migrate --dry-run",
        failure="the database cannot be inspected; this command never mutates it",
    )
    migrate.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help=_option_help(
            "report the safe action only; v1 remains read-only",
            "--dry-run",
            "the database cannot be inspected safely",
        ),
    )

    replay = _mission_parser(
        actions,
        "replay",
        summary="play the credential-free truth-labeled recorded mission",
        example="graphene mission replay taskmaster --no-open --exit-after-replay",
        failure="the replay digest, schema, timeline, or local server is invalid",
    )
    replay.description = (
        "Play a credential-free truth-labeled recording. Replay is read-only, makes "
        "zero Gemini calls, and cannot attest a human decision."
    )
    replay.add_argument(
        "source",
        nargs="?",
        default="taskmaster",
        help="taskmaster or a verified replay JSON path",
    )
    replay.add_argument(
        "--speed",
        type=_positive,
        default=1.0,
        help=_option_help(
            "positive playback multiplier",
            "--speed 2",
            "the value is zero, negative, or non-finite",
        ),
    )
    replay.add_argument(
        "--no-open",
        action="store_true",
        help=_option_help(
            "serve without opening a browser",
            "--no-open",
            "the local replay server cannot bind",
        ),
    )
    replay.add_argument(
        "--exit-after-replay", action="store_true", help=argparse.SUPPRESS
    )

    demo = _mission_parser(
        actions,
        "demo",
        summary="start the Taskmaster mission with the live Gemini ADK driver",
        example="graphene mission demo taskmaster --driver gemini-adk --open",
        failure="doctor, credentials, policy, Git, provider, or runtime checks fail",
    )
    demo.description = (
        "Run Taskmaster with two or more live Gemini workers and one truth-labeled "
        "deterministic check fault/retry. No fixture fallback exists."
    )
    demo.add_argument(
        "source",
        nargs="?",
        default="taskmaster",
        choices=("taskmaster",),
        help="bounded checked-in demo scenario (default: taskmaster)",
    )
    demo.add_argument(
        "--driver",
        choices=("gemini-adk",),
        default="gemini-adk",
        help=_option_help(
            "live provider driver; no fake fallback",
            "--driver gemini-adk",
            "the driver is not gemini-adk",
        ),
    )
    demo.add_argument(
        "--max-workers",
        type=_gemini_worker_count,
        default=2,
        help=_option_help(
            "live Gemini work agents, 2-5",
            "--max-workers 2",
            "the count is outside 2-5",
        ),
    )
    demo.add_argument(
        "--open",
        action="store_true",
        dest="open_viewer",
        help=_option_help(
            "open Mission Control before approval",
            "--open",
            "the authenticated local server cannot start",
        ),
    )

    executor = _mission_parser(
        actions,
        "executor",
        summary="run an authenticated outbound local executor",
        example="graphene mission executor connect --repo . --mission mission_123 --coordinator-url https://service.example --audience https://service.example --workers 2",
        failure="local preflight, authentication, exact-head, reconnect, or shutdown fails",
    )
    executor_actions = executor.add_subparsers(dest="executor_action", required=True)
    connect = _mission_parser(
        executor_actions,
        "connect",
        summary="connect bounded local Gemini workers to a private coordinator",
        example="graphene mission executor connect --repo . --mission mission_123 --coordinator-url https://service.example --audience https://service.example --workers 2",
        failure="identity, coordinator, runtime, exact-head, or bounded shutdown fails",
    )
    connect.add_argument(
        "--repo",
        required=True,
        type=Path,
        help=_option_help(
            "local Git repository to clone privately",
            "--repo .",
            "policy, HEAD, or workspace checks fail",
        ),
    )
    connect.add_argument(
        "--mission",
        required=True,
        dest="mission_id",
        help=_option_help(
            "exact mission ID",
            "--mission mission_123",
            "the mission is missing or unverified",
        ),
    )
    connect.add_argument(
        "--coordinator-url",
        required=True,
        help=_option_help(
            "private HTTPS coordinator origin or base path",
            "--coordinator-url https://service.example",
            "the URL is not credential-free HTTPS",
        ),
    )
    connect.add_argument(
        "--audience",
        required=True,
        help=_option_help(
            "exact HTTPS Cloud Run audience for fresh ADC ID tokens",
            "--audience https://service.example",
            "the audience is not an exact credential-free HTTPS origin",
        ),
    )
    connect.add_argument(
        "--workers",
        type=_outbound_worker_count,
        default=2,
        help=_option_help(
            "WORK-only Gemini executor sessions, 2-5",
            "--workers 2",
            "the count is outside 2-5",
        ),
    )
    connect.add_argument(
        "--expected-seq",
        type=_nonnegative,
        help=_option_help(
            "exact committed mission sequence; omit with SHA for local discovery",
            "--expected-seq 7",
            "the value is negative or differs from the committed head",
        ),
    )
    connect.add_argument(
        "--expected-event-sha256",
        type=_sha256,
        help=_option_help(
            "exact event digest for expected-seq; omit both for verified local head",
            f"--expected-event-sha256 {'a' * 64}",
            "the digest is malformed or does not bind the expected sequence",
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphene", allow_abbrev=False)
    parser.add_argument("--json", action="store_true", dest="json_mode")
    register_commands(parser.add_subparsers(dest="command", required=True))
    return parser


def _git_root(value: Path) -> tuple[Path, str]:
    executable = shutil.which("git")
    if executable is None:
        raise MissionCliError("Git is unavailable")
    try:
        root = subprocess.run(
            (executable, "rev-parse", "--show-toplevel"),
            cwd=value.resolve(strict=True),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        if root.returncode:
            raise MissionCliError("repository is not a Git worktree")
        repository = Path(root.stdout.strip()).resolve(strict=True)
        head = subprocess.run(
            (executable, "rev-parse", "--verify", "HEAD"),
            cwd=repository,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MissionCliError("Git repository inspection failed") from error
    base_sha = head.stdout.strip()
    if head.returncode or len(base_sha) != 40:
        raise MissionCliError("repository HEAD is unavailable")
    return repository, base_sha


def _default_policy(repository: Path, base_sha: str) -> ProjectPolicy:
    identity = sha256_hex(str(repository).encode())
    return ProjectPolicy(
        policy_id="policy_" + identity[:24],
        revision=1,
        repo_id="repo_" + identity[:24],
        base_ref="HEAD",
        base_sha=base_sha,
        allowed_read_globs=(".graphene/generated/**", "README.md"),
        allowed_write_globs=(".graphene/generated/**",),
        exclusions=("**/*.key", "**/*.pem", ".env", ".env.*", ".git/**"),
        command_templates=(
            CommandTemplate(
                template_id="git-diff-check",
                argv=("git", "diff", "--check", "--"),
                timeout_seconds=15,
            ),
        ),
        network=NetworkPolicy(),
        agent_roles=("assembler", "planner", "verifier", "worker"),
        max_concurrency=2,
        retry_limit=1,
        resource_budget=ResourceBudget(
            max_worker_seconds=900,
            max_attempts=8,
            max_artifact_bytes=10_485_760,
            soft_managed_rss_bytes=536_870_912,
            hard_managed_rss_bytes=805_306_368,
        ),
        retention=RetentionPolicy(retain_days=7, retain_failed_attempts=True),
        risk_gates=("final-result", "network", "scope-expansion"),
    )


def initialize(repo: Path) -> tuple[Path, ProjectPolicy]:
    repository, base_sha = _git_root(repo)
    directory = repository / ".graphene"
    if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
        raise MissionCliError(".graphene is not a safe directory")
    directory.mkdir(mode=0o755, exist_ok=True)
    path = directory / "project.json"
    policy = _default_policy(repository, base_sha)
    temporary = directory / f".project.json-{secrets.token_hex(12)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(policy.model_dump(mode="json")) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        directory_descriptor = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except FileExistsError as error:
        raise MissionCliError("project policy already exists") from error
    except OSError as error:
        raise MissionCliError("project policy could not be created") from error
    finally:
        temporary.unlink(missing_ok=True)
    return path, policy


def _policy_status(repo: Path) -> tuple[str, str]:
    try:
        _load_project_policy(repo)
        return "usable", "valid project policy"
    except MissionCliError as error:
        return "unavailable", str(error)
    except (OSError, ValueError):
        return "unavailable", "Git repository or project policy is invalid"


def _load_project_policy(repo: Path) -> tuple[Path, str, ProjectPolicy]:
    root, head = _git_root(repo)
    directory = root / ".graphene"
    if directory.is_symlink() or not directory.is_dir():
        raise MissionCliError(".graphene must be a real directory")
    path = directory / "project.json"
    if not path.is_file() or path.is_symlink():
        raise MissionCliError("run graphene init --repo PATH")
    try:
        policy = ProjectPolicy.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MissionCliError("Git repository or project policy is invalid") from error
    expected = _default_policy(root, policy.base_sha)
    if (
        policy.policy_id != expected.policy_id
        or policy.repo_id != expected.repo_id
        or policy.base_ref != expected.base_ref
    ):
        raise MissionCliError("project policy belongs to another repository")
    if head != policy.base_sha:
        executable = shutil.which("git")
        assert executable is not None
        try:
            ancestor = subprocess.run(
                (executable, "merge-base", "--is-ancestor", policy.base_sha, head),
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            changed = subprocess.run(
                (
                    executable,
                    "diff",
                    "--name-only",
                    "-z",
                    policy.base_sha,
                    head,
                    "--",
                ),
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise MissionCliError("Git repository inspection failed") from error
        paths = tuple(item for item in changed.stdout.split(b"\0") if item)
        if (
            ancestor.returncode != 0
            or changed.returncode != 0
            or paths != (b".graphene/project.json",)
        ):
            raise MissionCliError("project policy base differs from repository HEAD")
    return root, head, policy


def doctor(repo: Path) -> dict[str, object]:
    policy, policy_detail = _policy_status(repo)
    sandbox = scripted_supported()
    adk = importlib.util.find_spec("google.adk") is not None
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower()
    api_key_count = sum(
        bool(os.environ.get(name)) for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    )
    if vertex in {"1", "true"}:
        gemini_mode = "vertex_ai"
        gemini_configured = all(
            os.environ.get(name)
            for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
        )
    elif vertex in {"", "0", "false"}:
        gemini_mode = "gemini_api"
        gemini_configured = api_key_count == 1
    else:
        gemini_mode = "invalid"
        gemini_configured = False
    firestore = all(
        os.environ.get(name)
        for name in (
            "GOOGLE_CLOUD_PROJECT",
            "GRAPHENE_FIRESTORE_DATABASE",
            "GRAPHENE_FIRESTORE_NAMESPACE",
        )
    )
    audience = os.environ.get("GRAPHENE_COORDINATOR_AUDIENCE", "")
    coordinator_url = os.environ.get("GRAPHENE_COORDINATOR_URL", "")

    def https(value: str, *, origin_only: bool) -> bool:
        parsed = urlparse(value)
        return bool(
            len(value) <= 512
            and parsed.scheme == "https"
            and parsed.netloc
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and (not origin_only or parsed.path in {"", "/"})
        )

    try:
        bindings = json.loads(
            os.environ.get("GRAPHENE_COORDINATOR_EXECUTOR_BINDINGS", "")
        )
    except (json.JSONDecodeError, TypeError):
        bindings = None
    bindings_ready = bool(
        isinstance(bindings, dict)
        and bindings
        and all(
            isinstance(subject, str)
            and subject
            and isinstance(executor_id, str)
            and executor_id
            for subject, executor_id in bindings.items()
        )
    )
    gemini_ready = bool(
        shutil.which("git") is not None
        and adk
        and gemini_configured
        and policy == "usable"
    )
    return {
        "status": "ok",
        "gemini_preflight": {
            "configuration_ready": gemini_ready,
            "connectivity_proven": False,
            "live_provider_proven": False,
            "proof": "local configuration only; no provider request was made",
        },
        "executables": {
            "git": shutil.which("git") is not None,
            "python": shutil.which("python") is not None,
            "sandbox-exec": sandbox,
        },
        "check_executor": _check_executor_status(sandbox),
        "policy": {"status": policy, "detail": policy_detail},
        "platform_isolation": {
            "status": "usable" if sandbox else "unavailable",
            "detail": (
                "macOS sandbox-exec fixture boundary"
                if sandbox
                else "scripted code execution fails closed on this host"
            ),
        },
        "process_telemetry": {
            "status": "partial" if sandbox else "unavailable",
            "detail": "fixture wall time only; CPU and process-tree memory not captured",
        },
        "modes": {
            "mission-replay": {"usable": True, "proof": "checked-in replay only"},
            "scripted-local": {
                "usable": sandbox and policy == "usable",
                "proof": "checked-in fixture only",
            },
            "adk-fake": {
                "usable": False,
                "configured": adk,
                "proof": "framework plumbing exists; mission driver not connected",
            },
            "gemini-adk": {
                "usable": gemini_ready,
                "configured": gemini_configured,
                "credential_mode": gemini_mode,
                "proof": (
                    "bounded local runtime configured; connectivity not probed"
                    if gemini_ready
                    else "bounded local runtime configuration incomplete; connectivity not probed"
                ),
            },
            "firestore-cloud": {
                "usable": False,
                "read_viewer": {
                    "configuration_ready": bool(
                        firestore
                        and os.environ.get("GRAPHENE_MISSION_ID")
                        and os.environ.get("GRAPHENE_MISSION_CONTROL_READ_TOKEN")
                    )
                },
                "private_coordinator": {
                    "configuration_ready": bool(
                        firestore
                        and https(audience, origin_only=True)
                        and bindings_ready
                    )
                },
                "outbound_executor": {
                    "configuration_ready": bool(
                        https(coordinator_url, origin_only=False)
                        and https(audience, origin_only=True)
                    ),
                    "adc_token_proven": False,
                },
                "connectivity_proven": False,
                "write_proven": False,
                "proof": "configuration hints only; no cloud request was made",
            },
        },
    }


def _state_root() -> Path:
    configured = os.environ.get("GRAPHENE_STATE_DIR")
    if configured and not Path(configured).is_absolute():
        raise MissionCliError("GRAPHENE_STATE_DIR must be absolute")
    requested = Path(configured) if configured else Path.home() / ".graphene/state"

    def reject_symlinks() -> None:
        current = Path(requested.anchor)
        for part in requested.parts[1:]:
            current /= part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(metadata.st_mode):
                raise MissionCliError("mission state path cannot contain symlinks")

    reject_symlinks()
    requested.mkdir(mode=0o700, parents=True, exist_ok=True)
    reject_symlinks()
    metadata = requested.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise MissionCliError("mission state directory is not private")
    return requested.resolve(strict=True)


def _store(mission_id: str | None = None):
    try:
        from ..orchestration.store import SQLiteMissionStore
    except ImportError as error:
        raise MissionCliError("mission store is unavailable") from error
    store = SQLiteMissionStore(_state_root() / "missions.sqlite3")
    if mission_id is not None:
        evidence_path = _mission_runtime(mission_id) / "attempt-evidence.sqlite3"
        if evidence_path.is_symlink():
            raise MissionCliError("mission evidence path cannot be a symlink")
        if evidence_path.is_file():
            store.bind_artifact_resolver(SQLiteAttemptEvidenceStore(evidence_path))
    return store


def _store_for_mission(mission_id: str):
    """Bind durable attempt evidence when opening an existing mission."""
    store = _store()
    if getattr(store, "artifact_resolver", None) is not None or not hasattr(
        store, "bind_artifact_resolver"
    ):
        return store
    evidence_path = _mission_runtime(mission_id) / "attempt-evidence.sqlite3"
    if evidence_path.is_symlink():
        raise MissionCliError("mission evidence path cannot be a symlink")
    if evidence_path.is_file():
        store.bind_artifact_resolver(SQLiteAttemptEvidenceStore(evidence_path))
    return store


def _mission_evidence(store, mission_id: str) -> SQLiteAttemptEvidenceStore:
    path = _mission_runtime(mission_id) / "attempt-evidence.sqlite3"
    evidence = getattr(store, "artifact_resolver", None)
    evidence_type = SQLiteAttemptEvidenceStore
    if isinstance(evidence_type, type) and isinstance(evidence, evidence_type):
        if Path(evidence.path).resolve() != path.resolve():
            raise MissionCliError("mission evidence resolver belongs to another path")
        return evidence
    if evidence is not None:
        raise MissionCliError("mission evidence resolver is not locally verifiable")
    evidence = SQLiteAttemptEvidenceStore(path)
    store.bind_artifact_resolver(evidence)
    return evidence


def _mission_runtime(mission_id: str) -> Path:
    root = _state_root()
    name = sha256_hex(mission_id.encode())[:32]
    current = root / "missions" / name
    legacy = root / "scripted" / name
    return legacy if not current.exists() and legacy.exists() else current


def _projection(mission_id: str):
    from ..orchestration.projection import MissionProjection

    return MissionProjection(_store(mission_id), legacy_viewer_base=None)


def _status_value(mission_id: str) -> dict[str, object]:
    value = _projection(mission_id).snapshot(mission_id)
    return value.model_dump(mode="json")


def _watch_value(args: argparse.Namespace) -> dict[str, object]:
    store = _store(args.mission_id)
    events = store.tail(args.mission_id, args.after_seq, 256)
    next_after = events[-1].seq if events else args.after_seq
    return {
        "mission_id": args.mission_id,
        "after_seq": args.after_seq,
        "next_after_seq": next_after,
        "events": [item.model_dump(mode="json") for item in events],
        "snapshot": _status_value(args.mission_id) if args.snapshot else None,
    }


def _mission_events(store, mission_id: str, event_count: int):
    events = []
    after = 0
    while after < event_count:
        batch = store.tail(mission_id, after, min(256, event_count - after))
        if not batch:
            raise MissionCliError("mission event stream is incomplete")
        events.extend(batch)
        after = batch[-1].seq
    return tuple(events)


def _why_value(args: argparse.Namespace) -> dict[str, object]:
    from ..orchestration.causal_query import why

    mission_id = getattr(args, "mission_id", None) or os.environ.get(
        "GRAPHENE_MISSION_ID"
    )
    if not mission_id:
        raise MissionCliError("why requires --mission or GRAPHENE_MISSION_ID")
    store = _store_for_mission(mission_id)
    snapshot = store.snapshot(mission_id)
    if store.verify(mission_id) != snapshot.head:
        raise MissionCliError("mission verification changed during causal query")
    evidence = getattr(store, "artifact_resolver", None)

    def reference_exists(reference) -> bool | None:
        if evidence is None:
            return None
        raw = evidence.resolve(reference.kind, reference.id)
        return raw is not None and sha256_hex(raw) == reference.sha256

    return why(
        snapshot,
        _mission_events(store, mission_id, snapshot.head.event_count),
        args.path,
        reference_exists=reference_exists,
    ).model_dump(mode="json")


def _verified_plan_snapshot(mission_id: str, operation: str):
    store = _store_for_mission(mission_id)
    snapshot = store.snapshot(mission_id)
    if store.verify(mission_id) != snapshot.head:
        raise MissionCliError(f"mission verification changed during plan {operation}")
    return store, snapshot


def _plan_show_value(mission_id: str) -> dict[str, object]:
    _store_value, snapshot = _verified_plan_snapshot(mission_id, "show")
    plan = snapshot.plan.model_dump(mode="json")
    return {
        "status": "shown",
        "mission_id": mission_id,
        "plan_revision": snapshot.plan.revision,
        "plan_sha256": sha256_hex(canonical_json_bytes(plan)),
        "plan": plan,
    }


def _plan_diff_value(
    mission_id: str, previous_revision: int, revision: int
) -> dict[str, object]:
    store, _snapshot = _verified_plan_snapshot(mission_id, "diff")
    return store.plan_diff(mission_id, previous_revision, revision)


def _plan_lint_value(mission_id: str) -> dict[str, object]:
    from ..orchestration.validation import validate_plan

    store, snapshot = _verified_plan_snapshot(mission_id, "lint")
    if snapshot.mission.creation_source == "scripted_fixture":
        result = scripted_plan_validation(
            store, _mission_runtime(mission_id), mission_id
        )
    elif snapshot.mission.creation_source == "operator":
        _repository, policy, _workers = _gemini_source(mission_id, snapshot)
        result = validate_plan(policy, snapshot.plan)
    else:
        raise MissionCliError("plan lint requires a locally bound project policy")
    return {
        "status": "valid" if result.valid else "invalid",
        "valid": result.valid,
        "mission_id": mission_id,
        "plan_revision": snapshot.plan.revision,
        "plan_sha256": sha256_hex(
            canonical_json_bytes(snapshot.plan.model_dump(mode="json"))
        ),
        "criterion_coverage": [
            {
                "criterion_id": item.criterion_id,
                "producer_task_ids": list(item.producer_task_ids),
                "verification_kind": item.verification_kind.value,
                "verifier_task_id": item.verifier_task_id,
                "verifier_id": item.verifier_id,
            }
            for item in snapshot.plan.criteria
        ],
        "topological_order": list(result.topological_order),
        "issues": [item.model_dump(mode="json") for item in result.issues],
    }


_BUNDLE_ID = re.compile(r"final_result_[0-9a-f]{32}")


def _new_file_path(value: Path) -> Path:
    requested = value.expanduser()
    requested = requested if requested.is_absolute() else Path.cwd() / requested
    if not requested.name:
        raise MissionCliError("bundle output must name a new file")
    try:
        unresolved_parent = requested.parent.absolute()
        parent = unresolved_parent.resolve(strict=True)
        metadata = parent.lstat()
    except OSError as error:
        raise MissionCliError("bundle output parent is unavailable") from error
    if (
        unresolved_parent != parent
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise MissionCliError("bundle output parent must be a real directory")
    path = parent / requested.name
    if path.exists() or path.is_symlink():
        raise MissionCliError("bundle output must be a new non-symlink file")
    return path


def _atomic_create(path: Path, content: bytes) -> None:
    temporary = path.parent / f".{path.name}.{secrets.token_hex(12)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        directory = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError as error:
        raise MissionCliError("bundle output already exists") from error
    except OSError as error:
        raise MissionCliError(
            "bundle output could not be created atomically"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _bundle_directory(runtime: Path, *, create: bool) -> Path:
    directory = runtime / "final-bundles"
    try:
        runtime_metadata = runtime.lstat()
        if stat.S_ISLNK(runtime_metadata.st_mode) or not stat.S_ISDIR(
            runtime_metadata.st_mode
        ):
            raise MissionCliError("mission runtime is unsafe")
        if create:
            directory.mkdir(mode=0o700, exist_ok=True)
        metadata = directory.lstat()
    except MissionCliError:
        raise
    except OSError as error:
        raise MissionCliError("mission bundle directory is unavailable") from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise MissionCliError("mission bundle directory is unsafe")
    return directory


def _persisted_bundle_path(bundle_id: str) -> Path:
    if not _BUNDLE_ID.fullmatch(bundle_id):
        raise MissionCliError("bundle ID is invalid")
    root = _state_root()
    matches: list[Path] = []
    # ponytail: linear private-state scan; add a verified index if bundle counts matter.
    for family_name in ("missions", "scripted"):
        family = root / family_name
        if not family.exists():
            continue
        if family.is_symlink() or not family.is_dir():
            raise MissionCliError("mission bundle state is unsafe")
        for runtime in family.iterdir():
            if runtime.is_symlink() or not runtime.is_dir():
                continue
            directory = runtime / "final-bundles"
            if not directory.exists() and not directory.is_symlink():
                continue
            candidate = _bundle_directory(runtime, create=False) / f"{bundle_id}.json"
            if candidate.exists() or candidate.is_symlink():
                matches.append(candidate)
    if len(matches) != 1:
        raise MissionCliError("locally persisted bundle ID is missing or ambiguous")
    return matches[0]


def _read_bundle(path: Path):
    from ..orchestration.final_bundle import FinalResultBundleV2

    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 2_097_152
        ):
            raise MissionCliError("bundle must be a regular file no larger than 2 MiB")
        raw = path.read_bytes()
        bundle = FinalResultBundleV2.model_validate_json(raw)
    except MissionCliError:
        raise
    except (OSError, ValueError) as error:
        raise MissionCliError("bundle file is unavailable or invalid") from error
    return raw, bundle


def _bundle_create_value(args: argparse.Namespace) -> dict[str, object]:
    raw, bundle, runtime = _prepare_pending_bundle(args.mission_id)
    output = _new_file_path(args.output)
    persisted = _bundle_directory(runtime, create=True) / f"{bundle.bundle_id}.json"
    if output != persisted:
        _atomic_create(output, raw)
    return {
        "status": "created",
        "bundle_id": bundle.bundle_id,
        "bundle_sha256": bundle.bundle_sha256,
        "mission_id": args.mission_id,
        "output": str(output),
        "persisted": True,
        "approval_binding": "bundle_id",
    }


def _prepare_pending_bundle(mission_id: str):
    store, snapshot, runtime, _repository, evidence, _candidate, _verification = (
        _scripted_bindings(mission_id)
    )
    if snapshot.mission.status != MissionStatus.AWAITING_RESULT:
        raise MissionCliError("pending bundle creation requires result review state")
    if store.verify(mission_id) != snapshot.head:
        raise MissionCliError("mission verification changed during bundle creation")
    _head, bundle, reference = prepare_local_final_result_bundle(
        store=store,
        mission_id=mission_id,
        expected_head=snapshot.head,
        recorded_at=datetime.now(UTC),
    )
    raw = evidence.resolve(reference.kind, reference.id)
    if (
        raw is None
        or sha256_hex(raw) != reference.sha256
        or raw != canonical_json_bytes(bundle.model_dump(mode="json"))
    ):
        raise MissionCliError("prepared final result bundle is unavailable")
    directory = _bundle_directory(runtime, create=True)
    persisted = directory / f"{bundle.bundle_id}.json"
    if persisted.exists() or persisted.is_symlink():
        existing, existing_bundle = _read_bundle(persisted)
        if existing != raw or existing_bundle.bundle_id != bundle.bundle_id:
            raise MissionCliError("persisted bundle ID has different canonical bytes")
    else:
        _atomic_create(persisted, raw)
    return raw, bundle, runtime


def _bundle_verify_value(args: argparse.Namespace) -> dict[str, object]:
    from ..orchestration.final_bundle import verify_final_result_bundle

    persisted_id = args.bundle if _BUNDLE_ID.fullmatch(args.bundle) else None
    path = (
        _persisted_bundle_path(persisted_id)
        if persisted_id is not None
        else Path(args.bundle).expanduser()
    )
    raw, bundle = _read_bundle(path)
    if persisted_id is not None and bundle.bundle_id != persisted_id:
        raise MissionCliError("persisted bundle ID does not match its canonical bytes")
    mission_id = bundle.mission_id
    if persisted_id is not None:
        expected = (
            _bundle_directory(_mission_runtime(mission_id), create=False)
            / f"{persisted_id}.json"
        )
        if path != expected:
            raise MissionCliError("persisted bundle belongs to another mission runtime")
    store = _store_for_mission(mission_id)
    snapshot = store.snapshot(mission_id)
    if store.verify(mission_id) != snapshot.head:
        raise MissionCliError("mission verification changed during bundle verification")
    evidence = getattr(store, "artifact_resolver", None)
    if evidence is None or not verify_final_result_bundle(
        raw,
        snapshot,
        evidence,
        _mission_runtime(mission_id) / "repository",
        expected_policy_sha256=snapshot.policy.policy_sha256,
    ):
        raise MissionCliError("bundle verification failed closed")
    return {
        "status": "verified",
        "verified": True,
        "bundle_id": bundle.bundle_id,
        "bundle_sha256": bundle.bundle_sha256,
        "mission_id": mission_id,
        "source": (
            "persisted_bundle_id"
            if persisted_id is not None
            else "explicit_bundle_file"
        ),
        "approval_binding": "bundle_id",
    }


def _render_status(value: dict[str, object]) -> str:
    mission = value["mission"]
    tasks = value["tasks"]
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task["state"]] = counts.get(task["state"], 0) + 1
    rendered = " ".join(f"{key}={counts[key]}" for key in sorted(counts))
    needs = value.get("needs_you")
    need_text = needs.get("reason") if isinstance(needs, dict) else "No decision needed"
    return (
        f"MISSION {mission['mission_id']} {str(mission['status']).upper()}\n"
        f"GOAL {mission['goal']}\nTASKS {rendered}\nNEEDS YOU {need_text}\n"
    )


_WHY_RECEIPT_KINDS = frozenset({"test-receipt", "worker-provider-receipt"})
_WHY_TRUST_LINE = (
    "TRUST: every line above is derived from hash-chained mission events and "
    "resolvable evidence references; unknowns are listed, never guessed."
)


def _render_why_node(node: dict[str, object]) -> str:
    def field(name: str) -> str:
        item = node.get(name)
        return "none" if item is None else str(item)

    node_type = field("node_type")
    if node_type == "reference" and node.get("kind") in _WHY_RECEIPT_KINDS:
        return (
            f"  receipt {field('kind')} {field('node_id')} "
            f"resolvable={field('resolvable')}"
        )
    sha256 = node.get("sha256")
    digest = sha256[:12] if isinstance(sha256, str) else "none"
    line = (
        f"  node {node_type} {field('node_id')} kind={field('kind')} "
        f"task={field('task_id')} attempt={field('attempt_id')} "
        f"worker={field('worker_id')} attempt_number={field('attempt_number')} "
        f"fence={field('fencing_token')} sha256={digest}"
    )
    if node_type == "reference":
        line += f" resolvable={field('resolvable')}"
    return line


def _render_why(value: dict[str, object]) -> str:
    # The first line is pinned by tests and docs; everything after it is one
    # block per causal link, then explicit unknowns, then the trust statement.
    lines = [
        f"WHY {value['mission_id']} {value['query']} matched_by={value['matched_by']}"
    ]
    for link in value["links"]:
        lines.append(f"STAGE {link['stage']} {link['status']}")
        lines.extend(_render_why_node(item) for item in link.get("nodes", ()))
        lines.append(f"  events {','.join(link.get('event_ids', ())) or 'none'}")
        lines.append(f"  note {link['note']}")
    lines.extend(f"UNKNOWN {item}" for item in value["unknowns"])
    lines.append(_WHY_TRUST_LINE)
    return "\n".join(lines) + "\n"


def _render_plan_lint(value: dict[str, object]) -> str:
    lines = [
        f"PLAN {value['mission_id']} {str(value['status']).upper()} "
        f"revision={value['plan_revision']}"
    ]
    for item in value["criterion_coverage"]:
        producers = ",".join(item["producer_task_ids"]) or "none"
        verifier = item["verifier_task_id"] or "human-gate"
        lines.append(
            f"CRITERION {item['criterion_id']} producers={producers} "
            f"verifier={verifier}:{item['verifier_id']}"
        )
    for item in value["issues"]:
        target = item["task_id"] or "plan"
        lines.append(f"ISSUE {item['code']} target={target} {item['detail']}")
    return "\n".join(lines) + "\n"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _private_url_handoff(url: str) -> Path:
    directory = _state_root() / "handoffs"
    if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
        raise MissionCliError("Mission Control handoff directory is unsafe")
    directory.mkdir(mode=0o700, exist_ok=True)
    metadata = directory.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise MissionCliError("Mission Control handoff directory is not private")
    path = directory / f"mission-control-{secrets.token_hex(12)}.url"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(url.encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        path.unlink(missing_ok=True)
        raise MissionCliError(
            "Mission Control URL handoff could not be created"
        ) from error
    return path


def _serve(
    app,
    url: str,
    *,
    no_open: bool,
    keep_open: bool,
    stop_event: threading.Event | None = None,
) -> int:
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=int(url.split(":")[2].split("/")[0]),
            log_level="error",
        )
    )
    thread = threading.Thread(
        target=server.run, name="graphene-mission-control", daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            server.should_exit = True
            raise MissionCliError("Mission Control failed to start")
        time.sleep(0.01)
    handoff: Path | None = None
    try:
        if no_open and keep_open:
            handoff = _private_url_handoff(url)
        sys.stdout.write(f"Mission Control: {url.partition('#')[0]}\n")
        if handoff is not None:
            sys.stdout.write(f"Private browser URL: {handoff}\n")
            sys.stdout.write("Open the URL stored in that private file.\n")
        sys.stdout.flush()
        if not no_open:
            webbrowser.open(url)
        while keep_open and not (
            stop_event.wait(0.25) if stop_event is not None else False
        ):
            if stop_event is None:
                time.sleep(60)
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if handoff is not None:
            handoff.unlink(missing_ok=True)


def _open_live(mission_id: str, *, coordinate_gemini: bool = False) -> int:
    from ..orchestration.mission_control import create_mission_control_app
    from ..orchestration.projection import MissionProjection

    read_token = secrets.token_urlsafe(32)
    command_token = secrets.token_urlsafe(32)
    port = _free_port()
    origin = f"http://127.0.0.1:{port}"
    operator_label = "local-principal-" + _local_principal_hash()
    store = _store(mission_id)
    _mission_evidence(store, mission_id)
    if store.snapshot(mission_id).mission.status == MissionStatus.AWAITING_RESULT:
        _prepare_pending_bundle(mission_id)
    stop = threading.Event()
    coordinator_lock = threading.Lock()
    coordinator_failed = threading.Event()
    coordinator_errors: list[Exception] = []

    def cancel_coordinator(**values) -> MissionHead:
        stop.set()
        if not coordinator_lock.acquire(timeout=5):
            raise MissionCliError(
                "active Gemini runtime did not reach a safe cancellation boundary"
            )
        try:
            return _cancel_with_owned_cleanup(store=_store(mission_id), **values)
        finally:
            coordinator_lock.release()

    app = create_mission_control_app(
        MissionProjection(store, legacy_viewer_base=None),
        mission_id,
        read_token,
        "COMMITTED MISSION PROJECTION",
        command_token=command_token,
        command_origin=origin,
        operator_label=operator_label,
        cancel_coordinator=cancel_coordinator,
    )

    def coordinate() -> None:
        while not stop.wait(0.1):
            try:
                with coordinator_lock:
                    if stop.is_set():
                        return
                    store = _store(mission_id)
                    status = store.snapshot(mission_id).mission.status
                    if status == MissionStatus.RUNNING:
                        _execute_adk_mission(
                            store=store,
                            mission_id=mission_id,
                            should_cancel=stop.is_set,
                        )
                        status = _store(mission_id).snapshot(mission_id).mission.status
                if status == MissionStatus.AWAITING_RESULT:
                    _prepare_pending_bundle(mission_id)
                    return
                if status in {
                    MissionStatus.COMPLETED,
                    MissionStatus.REJECTED,
                    MissionStatus.FAILED,
                    MissionStatus.CANCELLED,
                }:
                    return
            except RunnerCancelled:
                return
            except Exception:
                try:
                    failed_store = _store_for_mission(mission_id)
                    failed = failed_store.snapshot(mission_id)
                    if failed.mission.status == MissionStatus.RUNNING:
                        _cancel_with_owned_cleanup(
                            store=failed_store,
                            mission_id=mission_id,
                            command_id=_command_id(
                                "gemini-coordinator-failed", mission_id
                            ),
                            expected_head=failed.head,
                            operator_label="graphene-runtime",
                            rationale="Gemini coordinator setup failed closed.",
                            truth_kind=TruthKind.SERVER_DERIVED,
                            recorded_at=datetime.now(UTC),
                        )
                except Exception:
                    pass
                coordinator_errors.append(
                    MissionCliError("Gemini coordinator failed closed")
                )
                sys.stderr.write("MISSION_ERROR: Gemini coordinator failed closed\n")
                coordinator_failed.set()
                return

    coordinator = None
    if coordinate_gemini:
        coordinator = threading.Thread(
            target=coordinate,
            name="graphene-gemini-coordinator",
            daemon=True,
        )
        coordinator.start()
    try:
        result = _serve(
            app,
            f"{origin}/mission-control/{mission_id}#token={read_token}&command={command_token}",
            no_open=False,
            keep_open=True,
            stop_event=coordinator_failed,
        )
    finally:
        stop.set()
        if coordinator is not None:
            coordinator.join(timeout=5)
    if coordinator_errors:
        raise MissionCliError("Gemini coordinator failed closed")
    return result


def _replay(args: argparse.Namespace) -> int:
    from ..orchestration.replay import (
        MISSION_REPLAY_TRUTH_LABEL,
        create_mission_replay_app,
        load_verified_mission_replay,
    )

    if args.source == "taskmaster":
        replay = load_verified_mission_replay()
    else:
        replay = load_verified_mission_replay(Path(args.source))
    token = secrets.token_urlsafe(32)
    port = _free_port()
    app = create_mission_replay_app(
        token, replay, stream_interval_seconds=0.35 / args.speed
    )
    sys.stdout.write(f"{MISSION_REPLAY_TRUTH_LABEL}\n")
    return _serve(
        app,
        f"http://127.0.0.1:{port}/mission-control/{replay.mission_id}#token={token}",
        no_open=args.no_open,
        keep_open=not args.exit_after_replay,
    )


def _demo(args: argparse.Namespace) -> dict[str, object]:
    scenario = load_scenario(DEFAULT_SCENARIO_PATH)
    demo_runtime = _state_root() / "demos" / "taskmaster"
    repository, base_sha = initialize_fixture_repository(scenario, demo_runtime)
    default = _default_policy(repository, base_sha)
    fixture_policy, _mission, _plan = scenario.contracts(
        mission_id="mission_taskmaster_demo",
        repo_id=default.repo_id,
        base_sha=base_sha,
        created_at=datetime.now(UTC),
    )
    policy = fixture_policy.model_copy(
        update={
            "policy_id": default.policy_id,
            "repo_id": default.repo_id,
            "base_ref": default.base_ref,
            "base_sha": base_sha,
        }
    )
    directory = repository / ".graphene"
    directory.mkdir(mode=0o700, exist_ok=True)
    policy_path = directory / "project.json"
    if policy_path.is_symlink():
        raise MissionCliError("Taskmaster demo policy path is unsafe")
    temporary = directory / ".project.json.graphene-demo-staging"
    temporary.unlink(missing_ok=True)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(policy.model_dump(mode="json")) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, policy_path)
    finally:
        temporary.unlink(missing_ok=True)
    preflight = doctor(repository)
    if not preflight["gemini_preflight"]["configuration_ready"]:
        raise MissionCliError(
            "Taskmaster demo preflight requires Git, Google ADK, one valid Gemini "
            "credential mode, and a usable project policy"
        )
    return _start(
        argparse.Namespace(
            repo=repository,
            goal=scenario.goal,
            success_criteria=list(scenario.success_criteria),
            driver="gemini-adk",
            max_workers=args.max_workers,
            auto_approve=False,
            command_id=None,
            open_viewer=args.open_viewer,
            json_mode=getattr(args, "json_mode", False),
            demo_injected_check_fault=True,
        )
    )


def _command_id(action: str, mission_id: str, *values: object) -> str:
    return (
        "command_"
        + sha256_hex(canonical_json_bytes([action, mission_id, *values]))[:32]
    )


def _start_identity(
    args: argparse.Namespace,
) -> tuple[str, str, Path, str, ProjectPolicy, dict[str, object]]:
    repository, head, policy = _load_project_policy(args.repo)
    criteria = tuple(sorted(set(args.success_criteria)))
    if args.driver == "scripted-local" and not criteria:
        criteria = load_scenario(DEFAULT_SCENARIO_PATH).success_criteria
    policy_sha256 = sha256_hex(canonical_json_bytes(policy.model_dump(mode="json")))
    command_id = args.command_id or _command_id(
        "start",
        "mission",
        sha256_hex(str(repository).encode()),
        head,
        args.driver,
        args.goal,
        criteria,
        args.auto_approve,
        args.max_workers,
        bool(getattr(args, "demo_injected_check_fault", False)),
        policy_sha256,
    )
    mission_id = "mission_start_" + sha256_hex(command_id.encode())[:24]
    binding = {
        "auto_approve": args.auto_approve,
        "command_id": command_id,
        "driver": args.driver,
        "goal_sha256": sha256_hex(args.goal.encode()),
        "max_workers": args.max_workers,
        "demo_injected_check_fault": bool(
            getattr(args, "demo_injected_check_fault", False)
        ),
        "policy_base_sha": policy.base_sha,
        "policy_revision": policy.revision,
        "policy_sha256": policy_sha256,
        "repository_head": head,
        # Private runtime binding used to re-open the exact read-only source at
        # approval time. This file is mode 0600 and is never emitted as an event.
        "repository_path": str(repository),
        "repository_path_sha256": sha256_hex(str(repository).encode()),
        "success_criteria_sha256": sha256_hex(canonical_json_bytes(criteria)),
    }
    return command_id, mission_id, repository, head, policy, binding


@contextmanager
def _start_lock(runtime: Path) -> Iterator[None]:
    try:
        import fcntl
    except ImportError as error:
        raise MissionCliError("mission start locking is unavailable") from error

    parent = runtime.parent
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise MissionCliError("mission runtime parent is unsafe")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if runtime.is_symlink():
        raise MissionCliError("mission runtime is unsafe")
    runtime.mkdir(mode=0o700, exist_ok=True)
    path = runtime / "start.lock"
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise MissionCliError("mission start lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _bind_start_request(runtime: Path, binding: dict[str, object]) -> None:
    if runtime.is_symlink():
        raise MissionCliError("mission runtime is unsafe")
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = runtime.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise MissionCliError("mission runtime is not private")
    path = runtime / "start-request.json"
    staging = runtime / ".start-request.json.graphene-staging"
    content = canonical_json_bytes(binding) + b"\n"
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise MissionCliError(
                "start command id is already bound to another request"
            )
        if staging.exists() or staging.is_symlink():
            staged = staging.lstat()
            if (
                not stat.S_ISREG(staged.st_mode)
                or stat.S_IMODE(staged.st_mode) != 0o600
                or (hasattr(os, "getuid") and staged.st_uid != os.getuid())
                or staged.st_nlink not in {1, 2}
            ):
                raise MissionCliError("start request staging file is unsafe")
            staging.unlink()
        directory_descriptor = os.open(
            runtime,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return
    if staging.exists() or staging.is_symlink():
        staged = staging.lstat()
        if (
            not stat.S_ISREG(staged.st_mode)
            or stat.S_IMODE(staged.st_mode) != 0o600
            or (hasattr(os, "getuid") and staged.st_uid != os.getuid())
            or staged.st_nlink != 1
        ):
            raise MissionCliError("start request staging file is unsafe")
        staging.unlink()
    try:
        descriptor = os.open(
            staging,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging, path, follow_symlinks=False)
        directory_descriptor = os.open(
            runtime,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise MissionCliError("start request binding could not be created") from error
    finally:
        if staging.exists() or staging.is_symlink():
            staged = staging.lstat()
            if (
                not stat.S_ISREG(staged.st_mode)
                or stat.S_IMODE(staged.st_mode) != 0o600
                or (hasattr(os, "getuid") and staged.st_uid != os.getuid())
                or staged.st_nlink not in {1, 2}
            ):
                raise MissionCliError("start request staging file is unsafe")
            staging.unlink()


def _existing_mission_snapshot(store, mission_id: str):
    from ..orchestration.store import MissionNotFound

    try:
        return store.snapshot(mission_id)
    except MissionNotFound:
        return None


def _local_principal_hash() -> str:
    try:
        import pwd

        uid = os.getuid()
        username = pwd.getpwuid(uid).pw_name
    except (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
    ) as error:
        raise MissionCliError(
            "authoritative local OS principal is unavailable"
        ) from error
    if type(uid) is not int or uid < 0 or not isinstance(username, str) or not username:
        raise MissionCliError("authoritative local OS principal is invalid")
    return sha256_hex(f"graphene.local-principal.v1\0{uid}\0{username}".encode())[:12]


def _truth_kind(args: argparse.Namespace) -> TruthKind:
    confirmed = bool(getattr(args, "confirm_human", False))
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if confirmed and not interactive:
        raise MissionCliError(
            "--confirm-human requires an authenticated local interactive terminal"
        )
    if confirmed:
        bound_label = f"{args.operator_label}@local-{_local_principal_hash()}"
        if len(bound_label) > 64:
            raise MissionCliError(
                "operator label is too long for local principal binding"
            )
        args.operator_label = bound_label
        return TruthKind.HUMAN_ATTESTED
    return TruthKind.SERVER_DERIVED


def _task_input_bytes(args: argparse.Namespace) -> bytes:
    limit = 4_096
    if args.input_stdin:
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        content = stream.read(limit + 1)
        if isinstance(content, str):
            content = content.encode()
    else:
        path = args.input_file.expanduser()
        try:
            before = path.lstat()
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
                raise MissionCliError("task input file must be a regular non-symlink")
            descriptor = os.open(
                path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise MissionCliError("task input file changed while opening")
                content = stream.read(limit + 1)
        except MissionCliError:
            raise
        except OSError as error:
            raise MissionCliError("task input file is unavailable") from error
    if not isinstance(content, bytes) or not content or len(content) > limit:
        raise MissionCliError("task input must contain 1 to 4096 bytes")
    if b"\0" in content:
        raise MissionCliError("task input must be NUL-free UTF-8")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MissionCliError("task input must be NUL-free UTF-8") from error
    return content


def _task_input_value(args: argparse.Namespace) -> dict[str, object]:
    content = _task_input_bytes(args)
    store = _store_for_mission(args.mission_id)
    snapshot = store.snapshot(args.mission_id)
    if store.verify(args.mission_id) != snapshot.head:
        raise MissionCliError("mission verification changed before task input")
    truth_kind = _truth_kind(args)
    evidence = _mission_evidence(store, args.mission_id)
    if store.head(args.mission_id) != snapshot.head:
        raise MissionCliError("mission head changed before private task input write")
    reference = evidence.put_artifact("operator-input", content)
    result = store.supply_task_input(
        args.mission_id,
        args.task_id,
        args.gate_id,
        reference,
        args.command_id
        or _command_id(
            "supply-task-input",
            args.mission_id,
            args.task_id,
            args.gate_id,
            reference.sha256,
            args.operator_label,
            args.rationale,
        ),
        expected_head=snapshot.head,
        operator_label=args.operator_label,
        rationale=args.rationale,
        truth_kind=truth_kind,
        recorded_at=datetime.now(UTC),
    )
    return {
        "status": "supplied",
        "mission_id": args.mission_id,
        "task_id": args.task_id,
        "gate_id": args.gate_id,
        "input_reference": reference.model_dump(mode="json"),
        "head": result.model_dump(mode="json"),
    }


def _scripted_run_value(
    store,
    run: ScriptedMissionRun,
    *,
    approval_truth: str,
) -> dict[str, object]:
    overlap_observed = any(
        first.started_monotonic < second.ended_monotonic
        and second.started_monotonic < first.ended_monotonic
        for position, first in enumerate(run.outcomes)
        for second in run.outcomes[position + 1 :]
    )
    return {
        "status": "awaiting_result",
        "mission_id": run.mission_id,
        "driver": "scripted-local",
        "proof": "scripted fixture; no Gemini or cloud execution",
        "approval_truth": approval_truth,
        "candidate_sha256": run.candidate.sha256,
        "verification_sha256": run.verification.sha256,
        "dispatch_batches": [list(batch) for batch in run.batches],
        "attempt_count": len(store.snapshot(run.mission_id).attempts),
        "parallel_overlap_observed": overlap_observed,
    }


def _gemini_proposal(
    args: argparse.Namespace,
    *,
    command_id: str,
    mission_id: str,
    policy: ProjectPolicy,
    repository: Path,
    runtime: Path,
    store,
) -> dict[str, object]:
    if not args.success_criteria:
        raise MissionCliError(
            "gemini-adk planning requires at least one --success-criterion; "
            "no scripted fallback was used"
        )
    criteria = tuple(sorted(set(args.success_criteria)))
    if len(criteria) != len(args.success_criteria):
        raise MissionCliError("success criteria must be unique")
    manifest, excerpts = _planning_repository_context(repository, policy)
    try:
        proposal = asyncio.run(
            AdkPlanner.live().propose(
                policy,
                PlanningRequest(
                    mission_id=mission_id,
                    revision=1,
                    goal=args.goal,
                    success_criteria=criteria,
                    repository_manifest=manifest,
                    repository_excerpts=excerpts,
                ),
            )
        )
    except PlannerError as error:
        raise MissionCliError(f"{error}; no scripted fallback was used") from error
    created_at = datetime.now(UTC)
    evidence = SQLiteAttemptEvidenceStore(runtime / "planner-evidence.sqlite3")
    receipt = evidence.put_artifact(
        "plan-proposal-receipt",
        canonical_json_bytes(proposal.receipt.model_dump(mode="json")),
    )
    store.bind_artifact_resolver(evidence)
    mission = Mission(
        mission_id=mission_id,
        policy_id=policy.policy_id,
        policy_revision=policy.revision,
        repo_id=policy.repo_id,
        base_sha=policy.base_sha,
        goal=args.goal,
        success_criteria=criteria,
        plan_revision=1,
        creation_source="operator",
        resource_budget=policy.resource_budget,
        unknowns=("The model-proposed plan awaits operator review.",),
        created_at=created_at,
    )
    store.create_mission(
        policy,
        mission,
        proposal.plan,
        _command_id("create-gemini-proposal", mission_id, command_id, receipt.sha256),
        plan_proposal_receipt=receipt,
        recorded_at=created_at,
    )
    return {
        "status": "proposed",
        "mission_id": mission_id,
        "driver": "gemini-adk",
        "proof": "real Google ADK planner proposal; execution requires explicit approval",
        "plan_revision": 1,
        "review_required": True,
        "execution_available": True,
        "plan_proposal_receipt_id": receipt.id,
        "plan_proposal_receipt_sha256": receipt.sha256,
        "requested_model": proposal.receipt.requested_model,
        "returned_model": proposal.receipt.returned_model,
        "task_graph": [
            {
                "task_id": task.task_id,
                "kind": task.kind.value,
                "dependencies": list(task.dependencies),
            }
            for task in proposal.plan.tasks
        ],
    }


def _existing_gemini_proposal_value(store, snapshot) -> dict[str, object]:
    events = store.tail(snapshot.mission.mission_id, 0, 16)
    proposed = next(event for event in events if event.event_type == "plan.proposed")
    return {
        "status": snapshot.mission.status.value,
        "mission_id": snapshot.mission.mission_id,
        "driver": "gemini-adk",
        "proof": "committed real Google ADK planner proposal; execution requires explicit approval",
        "plan_revision": snapshot.plan.revision,
        "review_required": snapshot.mission.status == MissionStatus.PROPOSED,
        "execution_available": True,
        "plan_proposal_receipt_id": proposed.payload.get("plan_proposal_receipt_id"),
        "plan_proposal_receipt_sha256": proposed.payload.get(
            "plan_proposal_receipt_sha256"
        ),
        "requested_model": proposed.payload.get("requested_model"),
        "returned_model": proposed.payload.get("returned_model"),
        "task_graph": [
            {
                "task_id": task.task_id,
                "kind": task.kind.value,
                "dependencies": list(task.dependencies),
            }
            for task in snapshot.plan.tasks
        ],
        "result_replayed": True,
    }


def _committed_scripted_run_value(store, mission_id: str) -> dict[str, object]:
    runtime = _mission_runtime(mission_id)
    evidence = getattr(store, "artifact_resolver", None)
    if not isinstance(evidence, SQLiteAttemptEvidenceStore):
        evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
        store.bind_artifact_resolver(evidence)
    candidate, verification = verified_result_artifacts(store, evidence, mission_id)
    snapshot = store.snapshot(mission_id)
    return {
        "status": snapshot.mission.status.value,
        "mission_id": mission_id,
        "driver": "scripted-local",
        "proof": "committed scripted fixture result; no Gemini or cloud execution",
        "approval_truth": "committed_event",
        "candidate_sha256": candidate.sha256,
        "verification_sha256": verification.sha256,
        "dispatch_batches": [],
        "attempt_count": len(snapshot.attempts),
        "parallel_overlap_observed": None,
        "result_replayed": True,
    }


def _scripted_proposal_value(
    store, mission_id: str, *, replayed: bool
) -> dict[str, object]:
    snapshot = store.snapshot(mission_id)
    validation = scripted_plan_validation(
        store, _mission_runtime(mission_id), mission_id
    )
    return {
        "status": snapshot.mission.status.value,
        "mission_id": mission_id,
        "driver": "scripted-local",
        "proof": "scripted fixture proposal; no Gemini or cloud execution",
        "plan_revision": snapshot.plan.revision,
        "review_required": True,
        "execution_available": scripted_supported(),
        "validation": validation.model_dump(mode="json"),
        "task_graph": [
            {
                "task_id": task.task_id,
                "kind": task.kind.value,
                "dependencies": list(task.dependencies),
            }
            for task in snapshot.plan.tasks
        ],
        **({"result_replayed": True} if replayed else {}),
    }


def _approve_scripted_start(
    store,
    *,
    mission_id: str,
    command_id: str,
    runtime: Path,
    simulated: bool,
) -> dict[str, object]:
    if not scripted_supported():
        raise MissionCliError(
            "scripted-local execution is unavailable because the fixture sandbox is not proven on this host"
        )
    truth_kind = TruthKind.SIMULATED_FIXTURE if simulated else TruthKind.HUMAN_ATTESTED
    expected_head = store.head(mission_id)
    store.approve_plan(
        mission_id,
        _command_id(
            "approve-start-plan",
            mission_id,
            command_id,
            simulated,
        ),
        expected_revision=1,
        expected_head=expected_head,
        operator_label="scripted-fixture" if simulated else "local-operator",
        rationale=(
            "Explicit --auto-approve deterministic Taskmaster fixture run."
            if simulated
            else "Approved in the interactive plan review."
        ),
        truth_kind=truth_kind,
        recorded_at=datetime.now(UTC),
    )
    run = execute_scripted_mission(
        store=store,
        runtime=runtime,
        mission_id=mission_id,
    )
    return _scripted_run_value(
        store,
        run,
        approval_truth=(
            "simulated_fixture_no_human_review" if simulated else "human_attested"
        ),
    )


def _planning_repository_context(
    repository: Path, policy: ProjectPolicy
) -> tuple[tuple[str, ...], tuple[PlanningExcerpt, ...]]:
    try:
        result = subprocess.run(
            ("git", "-C", str(repository), "ls-files", "-z", "--cached"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MissionCliError("repository manifest could not be read") from error
    if result.returncode:
        raise MissionCliError("repository manifest could not be read")
    tracked = tuple(
        sorted({os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw})
    )
    allowed = tuple(
        path
        for path in tracked
        if any(
            PurePosixPath(path).full_match(pattern)
            for pattern in policy.allowed_read_globs
        )
        and not any(
            PurePosixPath(path).full_match(pattern) for pattern in policy.exclusions
        )
    )[:512]
    excerpts: list[PlanningExcerpt] = []
    remaining = 32_768
    for relative in allowed:
        if len(excerpts) == 16 or PurePosixPath(relative).suffix.lower() not in {
            ".json",
            ".md",
            ".py",
            ".toml",
            ".yaml",
            ".yml",
        }:
            continue
        try:
            descriptor = os.open(
                repository / relative,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                content = os.read(descriptor, min(4_096, remaining) + 1)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise MissionCliError("repository planning excerpt is unsafe") from error
        if len(content) > min(4_096, remaining) or b"\0" in content:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not text:
            continue
        excerpts.append(PlanningExcerpt(path=relative, start_line=1, text=text))
        remaining -= len(content)
        if remaining <= 0:
            break
    return allowed, tuple(excerpts)


def _private_start_binding(runtime: Path) -> dict[str, object]:
    path = runtime / "start-request.json"
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size > 16_384
        ):
            raise MissionCliError("mission start request binding is unsafe")
        value = json.loads(path.read_bytes())
    except (OSError, TypeError, ValueError, UnicodeError) as error:
        raise MissionCliError("mission start request binding is unavailable") from error
    if not isinstance(value, dict):
        raise MissionCliError("mission start request binding is invalid")
    return value


def _gemini_source(mission_id: str, snapshot) -> tuple[Path, ProjectPolicy, int]:
    binding = _private_start_binding(_mission_runtime(mission_id))
    source = binding.get("repository_path")
    workers = binding.get("max_workers")
    if (
        not isinstance(source, str)
        or not isinstance(workers, int)
        or not 2 <= workers <= 5
    ):
        raise MissionCliError("Gemini runtime binding is incomplete")
    try:
        repository = Path(source).resolve(strict=True)
    except OSError as error:
        raise MissionCliError("Gemini source repository is unavailable") from error
    if sha256_hex(str(repository).encode()) != binding.get("repository_path_sha256"):
        raise MissionCliError(
            "Gemini source repository does not match its private binding"
        )
    root, _head, policy = _load_project_policy(repository)
    if (
        root != repository
        or snapshot.mission.base_sha != policy.base_sha
        or snapshot.mission.policy_id != policy.policy_id
        or snapshot.mission.repo_id != policy.repo_id
        or snapshot.policy.policy_sha256
        != sha256_hex(canonical_json_bytes(policy.model_dump(mode="json")))
    ):
        raise MissionCliError("Gemini source policy differs from the approved mission")
    return repository, policy, workers


def _ensure_owned_result_repository(source: Path, runtime: Path, base_sha: str) -> Path:
    repository = runtime / "repository"
    staging = runtime / ".repository.graphene-adk-staging"
    if staging.exists() or staging.is_symlink():
        metadata = staging.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise MissionCliError("Gemini result repository staging is unsafe")
        shutil.rmtree(staging)
    if not repository.exists():
        result = subprocess.run(
            (
                "git",
                "clone",
                "--no-local",
                "--no-checkout",
                "--quiet",
                str(source),
                str(staging),
            ),
            env={
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
                "PATH": os.defpath,
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode:
            shutil.rmtree(staging, ignore_errors=True)
            raise MissionCliError("Graphene-owned Gemini result clone failed")
        checkout = subprocess.run(
            ("git", "checkout", "--detach", "--quiet", base_sha),
            cwd=staging,
            env={
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
                "PATH": os.defpath,
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if checkout.returncode:
            shutil.rmtree(staging, ignore_errors=True)
            raise MissionCliError("Gemini result base is unavailable")
        remotes = subprocess.run(
            ("git", "remote"),
            cwd=staging,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        if remotes.returncode:
            shutil.rmtree(staging, ignore_errors=True)
            raise MissionCliError("Gemini result repository remote audit failed")
        for remote in remotes.stdout.splitlines():
            removed = subprocess.run(
                ("git", "remote", "remove", remote),
                cwd=staging,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            if removed.returncode:
                shutil.rmtree(staging, ignore_errors=True)
                raise MissionCliError("Gemini result repository remote removal failed")
        audit = subprocess.run(
            ("git", "remote"),
            cwd=staging,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        if audit.returncode or audit.stdout.strip():
            shutil.rmtree(staging, ignore_errors=True)
            raise MissionCliError("Gemini result repository retained a remote")
        os.rename(staging, repository)
    if repository.is_symlink() or not repository.is_dir():
        raise MissionCliError("Graphene-owned Gemini result repository is unsafe")
    remote_audit = subprocess.run(
        ("git", "remote"),
        cwd=repository,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    if remote_audit.returncode or remote_audit.stdout.strip():
        raise MissionCliError("Graphene-owned Gemini result repository has a remote")
    try:
        actual = subprocess.run(
            ("git", "rev-parse", "--verify", "HEAD"),
            cwd=repository,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MissionCliError(
            "Gemini result repository could not be verified"
        ) from error
    if actual.returncode or actual.stdout.strip() != base_sha:
        raise MissionCliError("Gemini result repository has another base")
    return repository.resolve(strict=True)


def _runtime_assignment(task: Task, policy: ProjectPolicy) -> RuntimeAssignment:
    if len(task.expected_outputs) != 1 or len(task.acceptance_checks) != 1:
        raise MissionCliError("Gemini task does not have one exact output and check")
    templates = {item.template_id: item for item in policy.command_templates}
    template = templates.get(task.acceptance_checks[0])
    if template is None or task.allowed_commands != (template.template_id,):
        raise MissionCliError("Gemini task check is outside the approved policy")
    output = task.expected_outputs[0]
    return RuntimeAssignment(
        task_id=task.task_id,
        title=task.title,
        contract=task.contract,
        read_paths=task.read_paths,
        output_name=output.name,
        output_kind=output.kind,
        output_paths=output.paths,
        command_template=template,
    )


async def _policy_check(
    workspace: Path, assignment: RuntimeAssignment, owner_id: str
) -> CheckOutcome:
    del owner_id
    template = assignment.command_template
    if template.argv != ("git", "diff", "--check", "--") or template.cwd is not None:
        raise MissionCliError(
            "Gemini runtime supports only the reviewed git-diff-check template"
        )

    def run() -> CheckOutcome:
        try:
            result = subprocess.run(
                template.argv,
                cwd=workspace,
                env={
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0",
                    "LC_ALL": "C",
                    "PATH": os.defpath,
                },
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=template.timeout_seconds,
                check=False,
            )
            output = result.stdout
            timed_out = False
            exit_code = result.returncode
        except subprocess.TimeoutExpired as error:
            output = bytes(error.stdout or b"")
            timed_out = True
            exit_code = 124
        truncated = len(output) > 65_536
        output = output[:65_536]
        return CheckOutcome(
            template_id=template.template_id,
            template_sha256=sha256_hex(
                canonical_json_bytes(template.model_dump(mode="json"))
            ),
            exit_code=exit_code,
            timed_out=timed_out,
            output_sha256=sha256_hex(output),
            output_truncated=truncated,
            cleanup_complete=True,
        )

    return await asyncio.to_thread(run)


class _DemoOneShotCheckRunner:
    """Inject one explicitly simulated check failure, then pass through the retry."""

    def __init__(self, runner, runtime: Path) -> None:
        self._runner = runner
        self._failed = runtime / "demo-check-fault.json"
        self._repaired = runtime / "demo-check-repair.json"

    @staticmethod
    def _write_once(path: Path, value: dict[str, object]) -> bool:
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json_bytes(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return True

    def _failed_task(self) -> str | None:
        try:
            value = json.loads(self._failed.read_bytes())
        except (OSError, TypeError, ValueError):
            return None
        task_id = value.get("task_id") if isinstance(value, dict) else None
        return task_id if isinstance(task_id, str) else None

    async def __call__(
        self, workspace: Path, assignment: RuntimeAssignment, owner_id: str
    ) -> CheckOutcome:
        label = "demo_injected_deterministic_check_failure"
        if self._write_once(
            self._failed,
            {
                "schema_version": 1,
                "truth_kind": "simulated_fixture",
                "truth_label": label,
                "task_id": assignment.task_id,
            },
        ):
            return CheckOutcome(
                template_id=assignment.command_template.template_id,
                template_sha256=sha256_hex(
                    canonical_json_bytes(
                        assignment.command_template.model_dump(mode="json")
                    )
                ),
                exit_code=97,
                timed_out=False,
                output_sha256=sha256_hex(label.encode()),
                output_truncated=False,
                cleanup_complete=True,
                truth_kind="simulated_fixture",
                truth_label=label,
            )
        outcome = await self._runner(workspace, assignment, owner_id)
        if (
            assignment.task_id == self._failed_task()
            and outcome.exit_code == 0
            and not outcome.timed_out
            and self._write_once(
                self._repaired,
                {
                    "schema_version": 1,
                    "truth_kind": "simulated_fixture",
                    "truth_label": "demo_retry_repaired_injected_check_failure",
                    "task_id": assignment.task_id,
                },
            )
        ):
            return outcome.model_copy(
                update={
                    "truth_kind": "simulated_fixture",
                    "truth_label": "demo_retry_repaired_injected_check_failure",
                }
            )
        return outcome


_CHECK_EXECUTOR_ENV = "GRAPHENE_CHECK_EXECUTOR"
_CHECK_EXECUTOR_CHOICES = ("docker", "host-sandbox")
_CHECK_EXECUTOR_ERROR = "GRAPHENE_CHECK_EXECUTOR must be docker or host-sandbox"


def _requested_check_executor() -> str:
    return os.environ.get(_CHECK_EXECUTOR_ENV, "").strip() or "docker"


_HOST_SANDBOX_UNSUPPORTED = (
    "GRAPHENE_CHECK_EXECUTOR=host-sandbox requires macOS /usr/bin/sandbox-exec"
)


def _host_sandbox_supported() -> bool:
    return sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()


def _select_check_executor() -> str:
    """Fail closed on anything but the two explicit fixture-tests executors.

    The host-sandbox choice is also checked for platform support here, before
    any worker runs, so an unsupported host never spends a model call on an
    attempt whose check can only fail.
    """

    requested = _requested_check_executor()
    if requested not in _CHECK_EXECUTOR_CHOICES:
        raise MissionCliError(_CHECK_EXECUTOR_ERROR)
    if requested == "host-sandbox" and not _host_sandbox_supported():
        raise MissionCliError(_HOST_SANDBOX_UNSUPPORTED)
    return requested


def _check_executor_status(sandbox: bool) -> dict[str, object]:
    requested = _requested_check_executor()
    if requested == "docker":
        supported = shutil.which("docker") is not None
        reason = (
            "docker executable found; container execution is not probed"
            if supported
            else "docker executable is not on PATH"
        )
    elif requested == "host-sandbox":
        supported = sandbox
        reason = (
            "macOS sandbox-exec fixture boundary with owned-process registration"
            if supported
            else "host-sandbox requires macOS /usr/bin/sandbox-exec"
        )
    else:
        # Never echo an unrecognised value; it is whatever the operator typed.
        return {
            "requested": "invalid",
            "supported": False,
            "reason": _CHECK_EXECUTOR_ERROR,
        }
    return {"requested": requested, "supported": supported, "reason": reason}


class _LateBoundWorkerRuntime:
    """Resolve attempt dispatches and heartbeats after the runtime exists.

    The check runner is chosen before the WorkerRuntime and MissionScheduler
    are constructed. This holder is assigned once they exist and fails closed
    (KeyError, which the runner maps to policy_rejected) if a check asks about
    an attempt before then.
    """

    def __init__(self) -> None:
        self.runtime: WorkerRuntime | None = None
        self.scheduler: MissionScheduler | None = None

    def dispatch_for(self, attempt_id: str) -> Dispatch:
        if self.runtime is None:
            raise KeyError(attempt_id)
        return self.runtime.dispatch_for(attempt_id)

    def heartbeat(self, dispatch: Dispatch) -> object:
        if self.scheduler is None:
            raise MissionCliError("mission scheduler is not bound to the check runner")
        return self.scheduler.heartbeat(dispatch)


def _work_task_kinds(snapshot) -> dict[str, TaskKind]:
    kinds = {task.task_id: task.kind for task in snapshot.plan.tasks}
    kinds.update({task.task_id: task.kind for task in snapshot.tasks})
    return kinds


def _provider_receipt_references(snapshot) -> list[dict[str, object]]:
    """Evidence-bound provider receipt references of WORK attempts only."""

    kinds = _work_task_kinds(snapshot)
    return [
        {
            "attempt_id": attempt.attempt_id,
            "worker_id": attempt.worker_id,
            "kind": reference.kind,
            "id": reference.id,
            "sha256": reference.sha256,
        }
        for attempt in snapshot.attempts
        if kinds.get(attempt.task_id) == TaskKind.WORK
        for reference in attempt.evidence_refs
        if reference.kind == WORKER_PROVIDER_RECEIPT_KIND
    ]


def _replayed_provider_receipts(
    snapshot, evidence: SQLiteAttemptEvidenceStore
) -> tuple[
    list[dict[str, object]],
    list[str],
    list[str],
    list[str],
    dict[str, WorkerProviderReceipt],
]:
    """Rebuild provider receipts from evidence-bound references; never guess.

    The final element maps each WORK attempt id to its evidence-resolved
    receipt, which is the only input a provider-call overlap measurement
    accepts.
    """

    kinds = _work_task_kinds(snapshot)
    receipts: list[dict[str, object]] = []
    by_attempt: dict[str, WorkerProviderReceipt] = {}
    session_ids: set[str] = set()
    invocation_ids: set[str] = set()
    unknowns: list[str] = []
    for attempt in snapshot.attempts:
        if kinds.get(attempt.task_id) != TaskKind.WORK:
            continue
        for reference in attempt.evidence_refs:
            if reference.kind != WORKER_PROVIDER_RECEIPT_KIND:
                continue
            label = (
                f"worker provider receipt {reference.id} for attempt "
                f"{attempt.attempt_id}"
            )
            content = evidence.resolve(reference.kind, reference.id)
            if not isinstance(content, bytes) or sha256_hex(content) != reference.sha256:
                unknowns.append(f"{label} is unresolvable")
                continue
            try:
                receipt = WorkerProviderReceipt.model_validate_json(content)
            except ValueError:
                unknowns.append(f"{label} is invalid")
                continue
            if canonical_json_bytes(receipt.model_dump(mode="json")) != content:
                unknowns.append(f"{label} is not canonical")
                continue
            receipts.append(receipt.model_dump(mode="json"))
            by_attempt[attempt.attempt_id] = receipt
            if attempt.session_id is not None:
                session_ids.add(attempt.session_id)
            if attempt.invocation_id is not None:
                invocation_ids.add(attempt.invocation_id)
    return (
        receipts,
        sorted(session_ids),
        sorted(invocation_ids),
        unknowns,
        by_attempt,
    )


def _adk_result_value(
    store,
    mission_id: str,
    *,
    batches: tuple[tuple[str, ...], ...] = (),
    receipts=(),
    replayed: bool = False,
    execution_mode: str = "not_reestablished",
    proof: str = "stored result replay; worker execution mode is not re-established",
) -> dict[str, object]:
    runtime = _mission_runtime(mission_id)
    demo_truth: list[dict[str, object]] = []
    for name in ("demo-check-fault.json", "demo-check-repair.json"):
        path = runtime / name
        try:
            if path.is_symlink() or path.stat().st_size > 4_096:
                continue
            value = json.loads(path.read_bytes())
        except (OSError, TypeError, ValueError):
            continue
        if (
            isinstance(value, dict)
            and value.get("truth_kind") == "simulated_fixture"
            and value.get("truth_label")
            in {
                "demo_injected_deterministic_check_failure",
                "demo_retry_repaired_injected_check_failure",
            }
            and isinstance(value.get("task_id"), str)
        ):
            demo_truth.append(
                {
                    "truth_kind": "simulated_fixture",
                    "truth_label": value["truth_label"],
                    "task_id": value["task_id"][:128],
                }
            )
    evidence = getattr(store, "artifact_resolver", None)
    if not isinstance(evidence, SQLiteAttemptEvidenceStore):
        evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
        store.bind_artifact_resolver(evidence)
    candidate, verification = scripted_result_artifacts(store, evidence, mission_id)
    snapshot = store.snapshot(mission_id)
    # Provider receipts are reported only from evidence-bound references, on
    # the live path and on replay alike. An in-memory runtime receipt whose
    # evidence binding failed is not a receipt Graphene can cite, so it is
    # never listed; `receipts` is kept for the dispatch/attempt bookkeeping.
    (
        provider_receipts,
        worker_session_ids,
        worker_invocation_ids,
        receipt_unknowns,
        receipts_by_attempt,
    ) = _replayed_provider_receipts(snapshot, evidence)
    # Overlap carries the lifetime bases from the store clock and, from the
    # same evidence-resolved receipts, the provider-call basis a live claim
    # must cite.
    overlap = measure_overlap(snapshot, provider_receipts=receipts_by_attempt)
    return {
        "status": snapshot.mission.status.value,
        "mission_id": mission_id,
        "driver": "gemini-adk",
        "execution_mode": execution_mode,
        "proof": proof,
        "candidate_sha256": candidate.sha256,
        "verification_sha256": verification.sha256,
        "dispatch_batches": [list(batch) for batch in batches],
        "attempt_count": len(snapshot.attempts),
        "worker_session_ids": worker_session_ids,
        "worker_invocation_ids": worker_invocation_ids,
        "provider_receipts": provider_receipts,
        "provider_receipt_references": _provider_receipt_references(snapshot),
        "receipt_unknowns": receipt_unknowns,
        "parallel_overlap": overlap.model_dump(mode="json"),
        "parallel_overlap_observed": overlap.observed,
        "provider_call_overlap_observed": overlap.provider_call_observed,
        "review_required": snapshot.mission.status == MissionStatus.AWAITING_RESULT,
        "checkout_mutated": False,
        **({"simulation_truth": demo_truth} if demo_truth else {}),
        **({"result_replayed": True} if replayed else {}),
    }


def _execute_adk_mission(
    *,
    store,
    mission_id: str,
    registry: WorkerRegistry | None = None,
    check_runner=None,
    resource_sampler: Callable[[str], Sequence[ResourcePoint]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    snapshot = store.snapshot(mission_id)
    if snapshot.mission.creation_source != "operator":
        raise MissionCliError("Gemini execution requires an operator-created mission")
    if snapshot.mission.status == MissionStatus.AWAITING_RESULT:
        return _adk_result_value(store, mission_id, replayed=True)
    if snapshot.mission.status != MissionStatus.RUNNING:
        raise MissionCliError("Gemini mission is not approved for execution")
    check_executor = _select_check_executor()
    source, policy, requested_workers = _gemini_source(mission_id, snapshot)
    runtime = _mission_runtime(mission_id)
    _ensure_owned_result_repository(source, runtime, snapshot.mission.base_sha)
    runtime_root = runtime / "adk-runtime"
    runtime_root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(runtime_root, 0o700)
    evidence = _mission_evidence(store, mission_id)
    worker_count = min(
        requested_workers, policy.max_concurrency, snapshot.plan.max_concurrency
    )
    if snapshot.plan.tasks and worker_count < 2:
        raise MissionCliError(
            "approved Gemini policy and plan must permit at least two workers"
        )
    gemini_worker_ids = tuple(
        f"gemini-worker-{index + 1}" for index in range(worker_count)
    )
    if registry is None:
        try:
            registry = WorkerRegistry(
                tuple(
                    GeminiWorkerAdapter.live(worker_id=item)
                    for item in gemini_worker_ids
                )
            )
        except PlannerError as error:
            raise MissionCliError(
                f"{error}; no fake worker fallback was used"
            ) from error
        capabilities = registry.capabilities()
    else:
        capabilities = registry.capabilities()
        registered = tuple(item.worker_id for item in capabilities)
        if len(registered) < worker_count:
            raise MissionCliError(
                "injected ADK worker registry has insufficient capacity"
            )
        gemini_worker_ids = registered[:worker_count]
    live_workers = bool(capabilities) and all(
        item.driver == "gemini_live" for item in capabilities
    )
    execution_mode = "gemini_live" if live_workers else "adk_fake"
    execution_proof = (
        "live Gemini workers in Graphene-owned lease-fenced workspaces"
        if live_workers
        else "credential-free fake ADK worker test in Graphene-owned "
        "lease-fenced workspaces"
    )
    assembler_worker_id = "deterministic-assembler"
    verifier_worker_id = "deterministic-verifier"
    worker_ids = tuple(
        sorted((*gemini_worker_ids, assembler_worker_id, verifier_worker_id))
    )
    tasks = {item.task_id: item for item in snapshot.plan.tasks}
    if not tasks:  # compatibility for injected runner seam tests only
        worker_ids = tuple(sorted(gemini_worker_ids))
    assignments = {
        task_id: _runtime_assignment(task, policy) for task_id, task in tasks.items()
    }
    late_runtime = _LateBoundWorkerRuntime()
    if check_runner is None:
        templates = tuple(policy.command_templates)
        if all(
            item.argv == ("git", "diff", "--check", "--") and item.cwd is None
            for item in templates
        ):
            check_runner = _policy_check
        elif len(templates) == 1 and templates[0].template_id == "fixture-tests":
            if check_executor == "host-sandbox":
                # Explicit macOS host alternative; the check subprocess is
                # registered in the same OwnedProcessRegistry that
                # `graphene mission cancel` reaps. No silent fallback to Docker.
                check_runner = HostSandboxCheckRunner(
                    OwnedProcessRegistry(runtime),
                    dispatch_for=late_runtime.dispatch_for,
                    status=lambda: store.snapshot(mission_id).mission.status,
                    heartbeat=late_runtime.heartbeat,
                )
            else:
                check_runner = DockerCheckRunner(DockerExecutor())
        else:
            raise MissionCliError(
                "Gemini mission has no supported deterministic check runner"
            )
    if tasks:
        demo_fault = _private_start_binding(runtime).get(
            "demo_injected_check_fault", False
        )
        if type(demo_fault) is not bool:
            raise MissionCliError("Gemini demo fault binding is invalid")
        if demo_fault:
            check_runner = _DemoOneShotCheckRunner(check_runner, runtime)
    clock = SystemClock()
    if resource_sampler is None:
        pid = os.getpid()
        started_monotonic_ns = time.monotonic_ns()

        def sample_resources(sampled_mission_id: str) -> tuple[ResourcePoint, ...]:
            observed_at = clock.now()

            def unavailable() -> tuple[ResourcePoint, ...]:
                return (
                    ResourcePoint(
                        subject=sampled_mission_id,
                        metric="current-rss-bytes",
                        units="bytes",
                        category="managed_runtime",
                        scope="isolated_process_tree",
                        attribution_quality="unavailable",
                        observed_at=observed_at,
                        value=None,
                        semantics="owned_process_tree_unavailable",
                    ),
                )

            if os.getpgrp() != pid:
                return unavailable()
            identity = read_process_identity(pid)
            if identity is None:
                return unavailable()
            try:
                sample = sample_owned_process_tree(
                    OwnedProcess(
                        owner_id=sampled_mission_id,
                        identity=identity,
                        process_group_id=pid,
                        started_monotonic_ns=started_monotonic_ns,
                    ),
                    observed_at=observed_at,
                )
            except (OSError, ProcessIdentityError):
                return unavailable()
            return (process_tree_rss_point(sample),)

        resource_sampler = sample_resources

    controller = ResourceDispatchController(
        store,
        DispatchGovernorPolicy(
            soft_managed_rss_bytes=policy.resource_budget.soft_managed_rss_bytes,
            hard_managed_rss_bytes=policy.resource_budget.hard_managed_rss_bytes,
        ),
        resource_sampler,
        clock,
    )
    scheduler = MissionScheduler(
        store,
        clock=clock,
        lease_ttl_seconds=60,
        retry_backoff_seconds=0,
        dispatch_limiter=controller,
        runtime_id="gemini_adk_runtime",
    )
    late_runtime.scheduler = scheduler
    if tasks:
        for worker_id in gemini_worker_ids:
            scheduler.register_worker(
                mission_id, worker_id, capabilities=(TaskKind.WORK,)
            )
        scheduler.register_worker(
            mission_id, assembler_worker_id, capabilities=(TaskKind.ASSEMBLY,)
        )
        scheduler.register_worker(
            mission_id, verifier_worker_id, capabilities=(TaskKind.VERIFICATION,)
        )

    accepted_artifacts = AcceptedArtifactCache()

    worker = WorkerRuntime(
        repository=source,
        base_sha=snapshot.mission.base_sha,
        runtime=runtime_root,
        evidence=evidence,
        registry=registry,
        assignment=lambda dispatch: assignments[dispatch.task_id],
        accepted_artifact=accepted_artifacts,
        check_runner=check_runner,
        policy_sha256=snapshot.policy.policy_sha256,
        fence=lambda dispatch, _operation_id: scheduler.assert_fence(dispatch),
        heartbeat=scheduler.heartbeat,
    )
    late_runtime.runtime = worker
    roots = tuple(
        item
        for item in snapshot.plan.tasks
        if item.kind == TaskKind.WORK and not item.dependencies
    )
    try:
        run = MissionRunner(
            scheduler=scheduler,
            runtime=worker,
            worker_ids=worker_ids,
            accepted_artifacts=accepted_artifacts,
            deadline_seconds=snapshot.mission.resource_budget.max_worker_seconds,
            should_cancel=should_cancel,
        ).run(mission_id)
    except RunnerCancelled:
        raise
    except RunnerError as error:
        raise MissionCliError(
            "Gemini ADK execution failed closed; no scripted fallback was used"
        ) from error
    prepare_local_final_result_bundle(
        store=store,
        mission_id=mission_id,
        expected_head=store.verify(mission_id),
        recorded_at=datetime.now(UTC),
    )
    if roots and not {item.task_id for item in roots}.issubset(
        {task_id for batch in run.batches for task_id in batch}
    ):
        raise MissionCliError("Gemini plan did not dispatch every independent root")
    return _adk_result_value(
        store,
        mission_id,
        batches=run.batches,
        receipts=run.receipts,
        execution_mode=execution_mode,
        proof=execution_proof,
    )


def _executor_connect(args: argparse.Namespace) -> dict[str, object]:
    repository, head, policy = _load_project_policy(args.repo)
    if not doctor(repository)["gemini_preflight"]["configuration_ready"]:
        raise MissionCliError(
            "outbound executor preflight requires Git, Google ADK, one valid "
            "Gemini credential mode, and a usable project policy"
        )
    store = _store_for_mission(args.mission_id)
    snapshot = store.snapshot(args.mission_id)
    verified_head = store.verify(args.mission_id)
    if verified_head != snapshot.head:
        raise MissionCliError("local mission verification changed during preflight")
    if snapshot.mission.status != MissionStatus.RUNNING:
        raise MissionCliError("outbound executor requires an approved running mission")
    if (
        snapshot.mission.base_sha != head
        or snapshot.policy.base_sha != policy.base_sha
        or snapshot.policy.policy_sha256
        != sha256_hex(canonical_json_bytes(policy.model_dump(mode="json")))
    ):
        raise MissionCliError("local executor repository or policy binding differs")
    supplied = args.expected_seq is not None or args.expected_event_sha256 is not None
    if supplied:
        if args.expected_seq is None or (
            (args.expected_seq == 0) != (args.expected_event_sha256 is None)
        ):
            raise MissionCliError(
                "expected head requires a positive seq with SHA, or seq zero without SHA"
            )
        expected_head = MissionHead(
            mission_id=args.mission_id,
            seq=args.expected_seq,
            event_count=args.expected_seq,
            event_sha256=args.expected_event_sha256,
        )
        if expected_head != verified_head:
            raise MissionCliError(
                "expected head differs from the verified local mission"
            )
    else:
        expected_head = verified_head

    tasks = {item.task_id: item for item in snapshot.plan.tasks}
    assignments = {
        task_id: _runtime_assignment(task, policy) for task_id, task in tasks.items()
    }
    worker_ids = tuple(f"outbound-work-{index + 1}" for index in range(args.workers))
    try:
        registry = WorkerRegistry(
            tuple(
                GeminiWorkerAdapter.live(worker_id=worker_id)
                for worker_id in worker_ids
            )
        )
    except PlannerError as error:
        raise MissionCliError(
            "outbound Gemini worker configuration is unavailable"
        ) from error
    check_executor = _select_check_executor()
    runtime = _mission_runtime(args.mission_id) / "outbound-executor"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(runtime, 0o700)
    evidence = _mission_evidence(store, args.mission_id)
    templates = tuple(policy.command_templates)
    if all(
        item.argv == ("git", "diff", "--check", "--") and item.cwd is None
        for item in templates
    ):
        check_runner = _policy_check
    elif len(templates) == 1 and templates[0].template_id == "fixture-tests":
        # Same explicit selection as the local ADK path; no silent fallback.
        if check_executor == "host-sandbox":
            check_runner = None  # built per attempt once its runtime exists
        else:
            check_runner = DockerCheckRunner(DockerExecutor())
    else:
        raise MissionCliError("outbound executor has no supported check runner")

    stop = threading.Event()
    summaries = []
    failures: list[BaseException] = []
    result_lock = threading.Lock()

    def run_attempt(context) -> ExecutorCompletion:
        outbox = context.dispatch
        task = tasks.get(outbox.task_id)
        if (
            task is None
            or task.kind != TaskKind.WORK
            or outbox.task_kind != TaskKind.WORK
        ):
            return ExecutorCompletion(
                result=AttemptResult(
                    succeeded=False,
                    result_code="policy_rejected",
                    session_id=outbox.session_id,
                    invocation_id="outbound-rejected-" + outbox.attempt_id[-16:],
                )
            )
        opened = {
            (
                item.reference.kind,
                item.reference.id,
                item.reference.sha256,
            ): item.content
            for item in context.accepted_inputs
        }

        def accepted(_dispatch, reference) -> bytes:
            content = opened.get((reference.kind, reference.id, reference.sha256))
            if content is None:
                content = evidence.resolve(reference.kind, reference.id)
            if content is None or sha256_hex(content) != reference.sha256:
                raise MissionCliError("accepted executor input is unavailable")
            return content

        async def fence(_dispatch, _operation_id) -> None:
            if context.cancelled.is_set():
                raise RuntimeError("executor shutdown")

        async def heartbeat(_dispatch) -> None:
            return None

        dispatch = Dispatch(
            mission_id=outbox.mission_id,
            plan_revision=outbox.plan_revision,
            plan_sha256=canonical_json_sha256(snapshot.plan.model_dump(mode="json")),
            task_id=outbox.task_id,
            task_kind=outbox.task_kind,
            attempt_id=outbox.attempt_id,
            attempt_number=outbox.attempt_number,
            worker_id=outbox.worker_id,
            workspace_id="outbound-workspace-" + outbox.attempt_id[-16:],
            lease_id=outbox.lease.lease_id,
            fencing_token=outbox.lease.fencing_token,
            dispatch_command_id="outbound-dispatch-" + outbox.dispatch_sha256[:32],
            write_paths=outbox.lease.write_paths,
            allowed_commands=task.allowed_commands,
            acceptance_checks=task.acceptance_checks,
            input_publications=outbox.accepted_inputs,
            expires_at=outbox.lease.expires_at,
        )
        late_runtime = _LateBoundWorkerRuntime()
        attempt_check_runner = check_runner
        if attempt_check_runner is None:
            # host-sandbox: the check subprocess registers in the mission's
            # owned-process registry; heartbeats stay with the executor loop.
            attempt_check_runner = HostSandboxCheckRunner(
                OwnedProcessRegistry(_mission_runtime(args.mission_id)),
                dispatch_for=late_runtime.dispatch_for,
                status=lambda: store.snapshot(args.mission_id).mission.status,
                heartbeat=None,
            )
        worker = WorkerRuntime(
            repository=repository,
            base_sha=snapshot.mission.base_sha,
            runtime=runtime,
            evidence=evidence,
            registry=registry,
            assignment=lambda current: assignments[current.task_id],
            accepted_artifact=accepted,
            check_runner=attempt_check_runner,
            policy_sha256=snapshot.policy.policy_sha256,
            fence=fence,
            heartbeat=heartbeat,
        )
        late_runtime.runtime = worker
        try:
            result = worker.execute(dispatch)
        except Exception:
            result = AttemptResult(
                succeeded=False,
                result_code="outcome_unknown",
                session_id=outbox.session_id,
                invocation_id="outbound-unknown-" + outbox.attempt_id[-16:],
            )
        if not result.succeeded:
            return ExecutorCompletion(
                result=AttemptResult(
                    succeeded=False,
                    retryable=result.retryable,
                    result_code=result.result_code,
                    session_id=outbox.session_id,
                    invocation_id=result.invocation_id
                    or "outbound-failed-" + outbox.attempt_id[-16:],
                )
            )
        bound_result = result.model_copy(update={"session_id": outbox.session_id})
        artifacts = []
        receipt = None
        for reference in bound_result.evidence_refs:
            content = evidence.resolve(reference.kind, reference.id)
            if content is None or sha256_hex(content) != reference.sha256:
                raise MissionCliError("executor artifact spool verification failed")
            artifacts.append(
                ExecutorArtifactObservation(
                    reference=reference, byte_count=len(content)
                )
            )
            if reference.kind == "test-receipt":
                receipt = TrustedCheckReceipt.model_validate_json(content)
        if receipt is None:
            raise MissionCliError("executor check receipt is unavailable")
        return ExecutorCompletion(
            result=bound_result,
            artifacts=tuple(artifacts),
            check_receipt=receipt,
        )

    client = CoordinatorClient(
        args.coordinator_url,
        args.audience,
        GoogleAdcAudienceTokenProvider(),
    )

    def connect(worker_id: str, session_id: str) -> None:
        try:
            summary = run_local_executor(
                client,
                mission_id=args.mission_id,
                expected_head=expected_head,
                session_id=session_id,
                worker_id=worker_id,
                capabilities=(TaskKind.WORK,),
                run_attempt=run_attempt,
                should_stop=stop.is_set,
                sleep=stop.wait,
            )
            with result_lock:
                summaries.append(summary)
        except BaseException as error:
            with result_lock:
                failures.append(error)
        finally:
            stop.set()

    prior_handlers = {}
    for requested_signal in (signal.SIGINT, signal.SIGTERM):
        prior_handlers[requested_signal] = signal.getsignal(requested_signal)
        signal.signal(requested_signal, lambda _signum, _frame: stop.set())
    threads = [
        threading.Thread(
            target=connect,
            args=(worker_id, f"outbound-session-{secrets.token_hex(12)}"),
            name=f"graphene-{worker_id}",
        )
        for worker_id in worker_ids
    ]
    try:
        for thread in threads:
            thread.start()
        while not stop.wait(0.25):
            if not any(thread.is_alive() for thread in threads):
                break
    finally:
        stop.set()
        shutdown_deadline = time.monotonic() + 60
        for thread in threads:
            thread.join(timeout=max(0, shutdown_deadline - time.monotonic()))
        for requested_signal, previous in prior_handlers.items():
            signal.signal(requested_signal, previous)
    if any(thread.is_alive() for thread in threads):
        raise MissionCliError("outbound executor shutdown did not complete")
    if failures:
        raise MissionCliError("outbound executor failed closed")
    summaries.sort(key=lambda item: item.session_id)
    authenticated = len(summaries) == len(worker_ids)
    return {
        "status": "executor_stopped",
        "mission_id": args.mission_id,
        "truth": (
            "authenticated coordinator round trip proven for every WORK session"
            if authenticated
            else "local configuration preflight only"
        ),
        "configuration_preflight": "local_only",
        "authenticated_coordinator_round_trip": authenticated,
        "scope": "work_only_first_cloud_vertical",
        "mission_completion_claimed": False,
        "worker_count": len(worker_ids),
        "worker_ids": list(worker_ids),
        "capabilities": [TaskKind.WORK.value],
        "claimed": sum(item.claimed for item in summaries),
        "completed_work_attempts": sum(item.completed for item in summaries),
        "final_heads": [item.head.model_dump(mode="json") for item in summaries],
    }


def _start(args: argparse.Namespace) -> dict[str, object]:
    if args.driver == "adk-fake":
        raise MissionCliError(
            "adk-fake planning is test-only and unavailable in the product CLI; "
            "no scripted fallback was used"
        )
    if args.driver == "gemini-adk" and args.auto_approve:
        raise MissionCliError(
            "gemini-adk requires an explicit plan approval before execution"
        )
    if args.driver == "gemini-adk" and args.max_workers < 2:
        raise MissionCliError("gemini-adk requires --max-workers from 2 to 5")
    command_id, mission_id, repository, _head, policy, binding = _start_identity(args)
    runtime = _mission_runtime(mission_id)
    with _start_lock(runtime):
        result = _start_bound(
            args,
            command_id=command_id,
            mission_id=mission_id,
            policy=policy,
            repository=repository,
            runtime=runtime,
            binding=binding,
        )
    if args.open_viewer:
        _open_live(mission_id, coordinate_gemini=args.driver == "gemini-adk")
    return result


def _start_bound(
    args: argparse.Namespace,
    *,
    command_id: str,
    mission_id: str,
    policy: ProjectPolicy,
    repository: Path,
    runtime: Path,
    binding: dict[str, object],
) -> dict[str, object]:
    store = _store_for_mission(mission_id)
    existing = _existing_mission_snapshot(store, mission_id)
    binding_path = runtime / "start-request.json"
    if existing is not None and (
        binding_path.is_symlink() or not binding_path.is_file()
    ):
        raise MissionCliError(
            "committed mission is missing its durable start request binding"
        )
    _bind_start_request(runtime, binding)
    if existing is not None:
        expected_source = (
            "operator" if args.driver == "gemini-adk" else "scripted_fixture"
        )
        committed = {
            "driver": (
                "gemini-adk"
                if existing.mission.creation_source == "operator"
                else "scripted-local"
            ),
            "goal_sha256": sha256_hex(existing.mission.goal.encode()),
            "success_criteria_sha256": sha256_hex(
                canonical_json_bytes(existing.mission.success_criteria)
            ),
        }
        if args.driver == "gemini-adk":
            committed.update(
                {
                    "policy_base_sha": existing.policy.base_sha,
                    "policy_revision": existing.policy.revision,
                    "policy_sha256": existing.policy.policy_sha256,
                }
            )
        if (
            existing.mission.creation_source != expected_source
            or any(binding[key] != value for key, value in committed.items())
            or (
                args.driver == "gemini-adk"
                and (
                    existing.mission.policy_id != policy.policy_id
                    or existing.policy.repo_id != policy.repo_id
                )
            )
        ):
            raise MissionCliError(
                "start command request differs from the committed mission"
            )
        if args.driver == "gemini-adk":
            existing_status = getattr(
                existing.mission, "status", MissionStatus.PROPOSED
            )
            if existing_status in {
                MissionStatus.AWAITING_RESULT,
                MissionStatus.COMPLETED,
                MissionStatus.REJECTED,
            }:
                result = _adk_result_value(store, mission_id, replayed=True)
            elif existing_status == MissionStatus.RUNNING and not args.open_viewer:
                result = _execute_adk_mission(store=store, mission_id=mission_id)
            else:
                result = _existing_gemini_proposal_value(store, existing)
        elif existing.mission.status in {
            MissionStatus.AWAITING_RESULT,
            MissionStatus.COMPLETED,
            MissionStatus.REJECTED,
        }:
            result = _committed_scripted_run_value(store, mission_id)
        elif existing.mission.status == MissionStatus.RUNNING:
            run = execute_scripted_mission(
                store=store,
                runtime=runtime,
                mission_id=mission_id,
            )
            result = _scripted_run_value(
                store,
                run,
                approval_truth="committed_plan_approval",
            )
        elif existing.mission.status == MissionStatus.PROPOSED and args.auto_approve:
            result = _approve_scripted_start(
                store,
                mission_id=mission_id,
                command_id=command_id,
                runtime=runtime,
                simulated=True,
            )
        else:
            result = _scripted_proposal_value(store, mission_id, replayed=True)
    elif args.driver == "gemini-adk":
        result = _gemini_proposal(
            args,
            command_id=command_id,
            mission_id=mission_id,
            policy=policy,
            repository=repository,
            runtime=runtime,
            store=store,
        )
    else:
        scenario = load_scenario(DEFAULT_SCENARIO_PATH)
        if args.success_criteria:
            raise MissionCliError(
                "scripted-local uses the fixed fixture success criteria"
            )
        if args.goal != scenario.goal:
            raise MissionCliError(
                "scripted-local only runs the exact goal declared by its fixture plan"
            )
        propose_scripted_mission(
            scenario=scenario,
            store=store,
            runtime=runtime,
            mission_id=mission_id,
        )
        result = _scripted_proposal_value(store, mission_id, replayed=False)
        if args.auto_approve:
            result = _approve_scripted_start(
                store,
                mission_id=mission_id,
                command_id=command_id,
                runtime=runtime,
                simulated=True,
            )
        interactive = (
            not args.auto_approve
            and scripted_supported()
            and not getattr(args, "json_mode", False)
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        )
        if interactive:
            sys.stdout.write(f"PLAN {mission_id} VALID tasks={len(scenario.tasks)}\n")
            for task in scenario.tasks:
                dependencies = ",".join(task.dependencies) or "none"
                sys.stdout.write(
                    f"  {task.task_id} [{task.kind.value}] <- {dependencies}\n"
                )
            sys.stdout.flush()
            if input("Approve this bounded scripted plan? [y/N] ").strip().lower() in {
                "y",
                "yes",
            }:
                result = _approve_scripted_start(
                    store,
                    mission_id=mission_id,
                    command_id=command_id,
                    runtime=runtime,
                    simulated=False,
                )
    return result


def _scripted_bindings(mission_id: str):
    store = _store(mission_id)
    snapshot = store.snapshot(mission_id)
    if snapshot.mission.creation_source not in {"scripted_fixture", "operator"}:
        raise MissionCliError("local result creation is unavailable for this mission")
    runtime = _mission_runtime(mission_id)
    repository = runtime / "repository"
    evidence_path = runtime / "attempt-evidence.sqlite3"
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise MissionCliError("mission result evidence is unavailable")
    evidence = getattr(store, "artifact_resolver", None)
    if not isinstance(evidence, SQLiteAttemptEvidenceStore):
        evidence = SQLiteAttemptEvidenceStore(evidence_path)
        store.bind_artifact_resolver(evidence)
    store.bind_local_commit_verifier(
        partial(
            verify_local_result_receipt,
            runtime=runtime,
            repository=repository,
        )
    )
    candidate, verification = verified_result_artifacts(store, evidence, mission_id)
    return store, snapshot, runtime, repository, evidence, candidate, verification


def _verification_template_id(snapshot) -> str:
    tasks = tuple(
        item for item in snapshot.plan.tasks if item.kind == TaskKind.VERIFICATION
    )
    if len(tasks) != 1 or len(tasks[0].acceptance_checks) != 1:
        raise MissionCliError("mission verification template is ambiguous")
    return tasks[0].acceptance_checks[0]


def _verified_result_value(
    mission_id: str,
) -> tuple[dict[str, object], bytes]:
    (
        store,
        snapshot,
        _runtime,
        _repository,
        evidence,
        candidate,
        verification,
    ) = _scripted_bindings(mission_id)
    store.verify(mission_id)
    patch = evidence.resolve(candidate.kind, candidate.id)
    verification_bytes = evidence.resolve(verification.kind, verification.id)
    if (
        candidate.kind != "patch"
        or patch is None
        or sha256_hex(patch) != candidate.sha256
        or verification_bytes is None
        or sha256_hex(verification_bytes) != verification.sha256
    ):
        raise MissionCliError("result artifacts failed digest verification")
    events = []
    after = 0
    while after < snapshot.head.seq:
        batch = store.tail(mission_id, after, min(256, snapshot.head.seq - after))
        if not batch:
            raise MissionCliError("result event stream is incomplete")
        events.extend(batch)
        after = batch[-1].seq
    isolated = tuple(
        event for event in events if event.event_type == "isolated_commit.created"
    )
    receipt: LocalResultReceipt | None = None
    if isolated:
        if len(isolated) != 1 or len(isolated[0].references) != 1:
            raise MissionCliError("isolated result proof is ambiguous")
        reference = isolated[0].references[0]
        raw = evidence.resolve(reference.kind, reference.id)
        if raw is None or sha256_hex(raw) != reference.sha256:
            raise MissionCliError("isolated result receipt failed verification")
        try:
            receipt = LocalResultReceipt.model_validate_json(raw)
        except ValueError as error:
            raise MissionCliError("isolated result receipt is invalid") from error
    return (
        {
            "status": snapshot.mission.status.value,
            "mission_id": mission_id,
            "candidate_sha256": candidate.sha256,
            "candidate_bytes": len(patch),
            "verification_id": verification.id,
            "verification_sha256": verification.sha256,
            "checks_passed": True,
            "final_outcome": snapshot.mission.final_outcome,
            "local_commit_sha": None if receipt is None else receipt.local_commit_sha,
            "result_ref": None if receipt is None else receipt.result_ref,
            "changed_paths": [] if receipt is None else list(receipt.changed_paths),
            "checkout_mutated": False,
            "pushed": False,
        },
        patch,
    )


def _result_command(args: argparse.Namespace) -> dict[str, object]:
    value, patch = _verified_result_value(args.mission_id)
    if args.result_action == "show":
        return value
    if args.candidate_sha != value["candidate_sha256"]:
        raise MissionCliError("export digest does not match the verified candidate")
    output = args.output.expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir() or output.exists() or output.is_symlink():
        raise MissionCliError(
            "export output must be a new file in an existing directory"
        )
    try:
        descriptor = os.open(
            parent / output.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(patch)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise MissionCliError("verified result export failed") from error
    return {**value, "exported_to": str(parent / output.name)}


def _capsule_export_value(args: argparse.Namespace) -> dict[str, object]:
    from ..orchestration.capsule import CapsuleError, export_mission_capsule

    mission_id = args.mission_id
    output = args.output.expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    store = _store_for_mission(mission_id)
    evidence_path = _mission_runtime(mission_id) / "attempt-evidence.sqlite3"
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise MissionCliError("mission attempt evidence is unavailable")
    evidence = _mission_evidence(store, mission_id)
    try:
        return export_mission_capsule(
            store=store,
            evidence=evidence,
            mission_id=mission_id,
            output_dir=output,
        )
    except CapsuleError as error:
        raise MissionCliError(f"capsule export failed: {error}") from error


def _capsule_verify_value(args: argparse.Namespace) -> dict[str, object]:
    """Cold verification: recomputes from the capsule files and opens no store."""

    from ..orchestration.capsule import CapsuleError, verify_mission_capsule

    capsule_dir = args.capsule_dir.expanduser()
    if not capsule_dir.is_absolute():
        capsule_dir = Path.cwd() / capsule_dir
    try:
        return verify_mission_capsule(capsule_dir)
    except CapsuleError as error:
        raise MissionCliError(f"capsule verification failed: {error}") from error


def _capsule_command(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    if args.capsule_action == "export":
        return 0, _capsule_export_value(args)
    if args.capsule_action == "verify":
        value = _capsule_verify_value(args)
        return (0 if value["verified"] else 1), value
    raise MissionCliError("capsule action is not available")


def _render_capsule_verify(value: dict[str, object]) -> str:
    lines = [
        f"CAPSULE {value['mission_id']} schema={value['schema']} "
        f"dir={value['capsule_dir']}"
    ]
    for item in value["checks"]:
        lines.append(f"CHECK {item['name']} ok={item['ok']} {item['detail']}")
    lines.extend(f"NOT_CHECKED {item}" for item in value["not_checked"])
    if value["verified"]:
        lines.append(f"VERIFIED {value['mission_id']} checks={len(value['checks'])}")
    else:
        failed = next((item for item in value["checks"] if not item["ok"]), None)
        name = "none" if failed is None else failed["name"]
        lines.append(f"FAILED {value['mission_id']} check={name}")
    return "\n".join(lines) + "\n"


def _database_status() -> dict[str, object]:
    database = _state_root() / "missions.sqlite3"
    if not database.exists():
        return {
            "status": "absent",
            "schema_version": None,
            "mission_count": 0,
            "migration_versions": [],
        }
    if database.is_symlink() or not database.is_file():
        raise MissionCliError("mission database path is unsafe")
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            mission_count = (
                connection.execute("SELECT COUNT(*) FROM missions").fetchone()[0]
                if "missions" in tables
                else 0
            )
            migration_table = next(
                (
                    name
                    for name in ("schema_migrations", "graphene_schema_migrations")
                    if name in tables
                ),
                None,
            )
            migrations = (
                []
                if migration_table is None
                else [
                    row[0]
                    for row in connection.execute(
                        f"SELECT version FROM {migration_table} ORDER BY version"
                    )
                ]
            )
    except sqlite3.Error as error:
        raise MissionCliError("mission database status could not be read") from error
    return {
        "status": "current" if version == 2 and migrations == [2] else "read_only",
        "schema_version": version,
        "mission_count": mission_count,
        "migration_versions": migrations,
    }


def _database_command(args: argparse.Namespace) -> dict[str, object]:
    status = _database_status()
    if args.db_action == "status":
        return status
    if args.db_action == "migrate":
        return {
            **status,
            "dry_run": True,
            "action": (
                "none"
                if status["schema_version"] == 2
                else "export-verify-and-create-a-new-v2-store"
            ),
            "mutated": False,
        }
    if status["status"] == "absent":
        return {**status, "verified_missions": 0}
    try:
        store = _store()
        with sqlite3.connect(f"file:{store.path}?mode=ro", uri=True) as connection:
            mission_ids = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT mission_id FROM missions ORDER BY mission_id"
                )
            )
        for mission_id in mission_ids:
            _store(mission_id).verify(mission_id)
    except Exception as error:
        raise MissionCliError("mission database verification failed closed") from error
    return {**status, "verified_missions": len(mission_ids)}


def _result_decision(args: argparse.Namespace, *, approved: bool) -> dict[str, object]:
    action = "approve-result" if approved else "reject-result"
    truth_kind = _truth_kind(args)
    (
        store,
        snapshot,
        _runtime,
        _repository,
        _evidence,
        candidate,
        _verification,
    ) = _scripted_bindings(args.mission_id)
    raw, bundle = _read_bundle(_persisted_bundle_path(args.bundle_id))
    if bundle.mission_id != args.mission_id:
        raise MissionCliError("bundle belongs to another mission")
    if bundle.candidate_reference.content_sha256 != candidate.sha256:
        raise MissionCliError("bundle decision does not bind the exact assembled patch")
    from ..orchestration.final_bundle import verify_final_result_bundle

    if not verify_final_result_bundle(
        raw,
        snapshot,
        _evidence,
        _repository,
        expected_policy_sha256=snapshot.policy.policy_sha256,
    ):
        raise MissionCliError("bundle decision failed immutable verification")
    now = datetime.now(UTC)
    command_id = args.command_id or _command_id(
        action,
        args.mission_id,
        args.bundle_id,
        args.operator_label,
        args.rationale,
    )
    _head, receipt = finalize_local_result_decision(
        store=store,
        mission_id=args.mission_id,
        command_id=command_id,
        expected_head=snapshot.head,
        expected_bundle_id=args.bundle_id,
        operator_label=args.operator_label,
        rationale=args.rationale,
        truth_kind=truth_kind,
        recorded_at=now,
        approved=approved,
    )
    return {
        "status": "completed" if approved else "rejected",
        "mission_id": args.mission_id,
        "decision": receipt.decision,
        "candidate_sha256": receipt.candidate_patch_sha256,
        "bundle_id": bundle.bundle_id,
        "bundle_sha256": bundle.bundle_sha256,
        "receipt_id": receipt.receipt_id,
        "local_commit_sha": receipt.local_commit_sha,
        "result_ref": receipt.result_ref,
        "pushed": False,
        "pull_request_created": False,
        "deployed": False,
    }


def _cancel_with_owned_cleanup(
    *,
    store,
    mission_id: str,
    command_id: str,
    expected_head: MissionHead | None,
    operator_label: str,
    rationale: str | None,
    truth_kind: TruthKind,
    recorded_at: datetime,
) -> MissionHead:
    snapshot = store.snapshot(mission_id)
    worker_ids = tuple(
        sorted(
            {
                attempt.worker_id
                for attempt in snapshot.attempts
                if attempt.state == AttemptState.RUNNING
            }
        )
    )
    active = store.recover_dispatches(mission_id, worker_ids, recorded_at=recorded_at)
    registry = OwnedProcessRegistry(_mission_runtime(mission_id))
    prepared = registry.prepare_cancel(active)
    durable = registry.records_for_mission(mission_id)
    targets = tuple({item.attempt_id: item for item in (*prepared, *durable)}.values())
    for owned in targets:
        registry.terminate_owned(owned)
    if snapshot.mission.status == MissionStatus.CANCELLED:
        return snapshot.head
    return store.cancel(
        mission_id,
        command_id,
        expected_head=expected_head or store.head(mission_id),
        operator_label=operator_label,
        rationale=rationale,
        truth_kind=truth_kind,
        recorded_at=recorded_at,
    )


def _mutate(args: argparse.Namespace) -> dict[str, object]:
    store = _store_for_mission(args.mission_id)
    action = args.mission_action
    now = datetime.now(UTC)
    if action == "request-replan":
        truth_kind = _truth_kind(args)
        expected_head = store.head(args.mission_id)
        result = store.request_replan(
            args.mission_id,
            args.command_id
            or _command_id(
                action,
                args.mission_id,
                args.operator_label,
                args.reason,
            ),
            expected_head=expected_head,
            reason=args.reason,
            operator_label=args.operator_label,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    elif action in {"pause", "resume", "cancel"}:
        truth_kind = _truth_kind(args)
        if action == "cancel" and args.confirm != args.mission_id:
            raise MissionCliError(
                "cancel confirmation must exactly match the mission id"
            )
        command_id = args.command_id or _command_id(
            action,
            args.mission_id,
            args.operator_label,
            args.rationale,
        )
        if action == "cancel":
            try:
                _cancel_with_owned_cleanup(
                    store=store,
                    mission_id=args.mission_id,
                    command_id=command_id,
                    expected_head=None,
                    operator_label=args.operator_label,
                    rationale=args.rationale,
                    truth_kind=truth_kind,
                    recorded_at=now,
                )
            except ProcessControlError as error:
                raise MissionCliError(
                    "cancellation aborted because owned worker cleanup failed"
                ) from error
            return {"mission_id": args.mission_id, "status": "cancelled"}
        snapshot = store.snapshot(args.mission_id)
        worker_ids = tuple(
            sorted(
                {
                    attempt.worker_id
                    for attempt in snapshot.attempts
                    if attempt.state == AttemptState.RUNNING
                }
            )
        )
        active = store.recover_dispatches(args.mission_id, worker_ids, recorded_at=now)
        registry = (
            OwnedProcessRegistry(_mission_runtime(args.mission_id))
            if active or action == "cancel"
            else None
        )
        try:
            prepared = () if registry is None else registry.prepare_cancel(active)
        except ProcessControlError as error:
            raise MissionCliError(
                "active workers could not be bound to their owned runtime"
            ) from error
        expected_head = store.head(args.mission_id)
        result = getattr(store, action)(
            args.mission_id,
            command_id,
            expected_head=expected_head,
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
        requested_signal = {
            "cancel": signal.SIGTERM,
            "pause": signal.SIGSTOP,
            "resume": signal.SIGCONT,
        }[action]
        try:
            if registry is not None:
                for owned in prepared:
                    registry.signal_prepared(owned, requested_signal)
        except ProcessControlError as error:
            raise MissionCliError(
                "mission state changed but an owned worker could not be signalled"
            ) from error
    elif action == "retry":
        truth_kind = _truth_kind(args)
        expected_head = store.head(args.mission_id)
        result = store.retry_task(
            args.mission_id,
            args.task_id,
            args.command_id
            or _command_id(
                action,
                args.mission_id,
                args.task_id,
                args.operator_label,
                args.rationale,
            ),
            expected_head=expected_head,
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    elif action == "approve-plan":
        truth_kind = _truth_kind(args)
        snapshot = store.snapshot(args.mission_id)
        if snapshot.plan.revision != args.revision:
            raise MissionCliError(
                "plan approval revision does not match committed state"
            )
        command_id = args.command_id or _command_id(
            action,
            args.mission_id,
            args.revision,
            args.operator_label,
            args.rationale,
        )
        if snapshot.mission.creation_source == "scripted_fixture":
            if not scripted_supported():
                raise MissionCliError(
                    "scripted-local execution is unavailable because the fixture sandbox is not proven on this host"
                )
            if snapshot.mission.status not in {
                "proposed",
                "running",
                "awaiting_result",
            }:
                raise MissionCliError("scripted mission plan cannot be executed now")
            if snapshot.mission.status == "awaiting_result":
                return _committed_scripted_run_value(store, args.mission_id)
            if snapshot.mission.status == "proposed":
                store.approve_plan(
                    args.mission_id,
                    command_id,
                    expected_revision=args.revision,
                    expected_head=snapshot.head,
                    operator_label=args.operator_label,
                    rationale=args.rationale,
                    truth_kind=truth_kind,
                    recorded_at=now,
                )
            run = execute_scripted_mission(
                store=store,
                runtime=_mission_runtime(args.mission_id),
                mission_id=args.mission_id,
            )
            return _scripted_run_value(
                store,
                run,
                approval_truth=truth_kind.value,
            )
        if snapshot.mission.creation_source == "operator":
            if snapshot.mission.status not in {
                MissionStatus.PROPOSED,
                MissionStatus.RUNNING,
                MissionStatus.AWAITING_RESULT,
            }:
                raise MissionCliError("Gemini mission plan cannot be executed now")
            if snapshot.mission.status == MissionStatus.AWAITING_RESULT:
                return _adk_result_value(store, args.mission_id, replayed=True)
            if snapshot.mission.status == MissionStatus.PROPOSED:
                store.approve_plan(
                    args.mission_id,
                    command_id,
                    expected_revision=args.revision,
                    expected_head=snapshot.head,
                    operator_label=args.operator_label,
                    rationale=args.rationale,
                    truth_kind=truth_kind,
                    recorded_at=now,
                )
            return _execute_adk_mission(store=store, mission_id=args.mission_id)
        result = store.approve_plan(
            args.mission_id,
            command_id,
            expected_revision=args.revision,
            expected_head=snapshot.head,
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    elif action == "decide-gate":
        truth_kind = _truth_kind(args)
        expected_head = store.head(args.mission_id)
        result = store.decide_gate(
            args.mission_id,
            args.gate_id,
            args.decision,
            args.command_id
            or _command_id(
                action,
                args.mission_id,
                args.gate_id,
                args.decision,
                args.operator_label,
                args.rationale,
            ),
            expected_head=expected_head,
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    elif action == "approve-result":
        return _result_decision(args, approved=True)
    elif action == "reject-result":
        return _result_decision(args, approved=False)
    else:
        raise MissionCliError(f"mission action is not available: {action}")
    return result.model_dump(mode="json")


def _dispatch(args: argparse.Namespace) -> tuple[int, object | None]:
    if args.command == "init":
        path, policy = initialize(args.repo)
        return 0, {
            "status": "initialized",
            "policy_id": policy.policy_id,
            "policy_path": str(path),
            "scope_notice": "review and edit bounded scopes before real repository work",
            "write_scope": list(policy.allowed_write_globs),
        }
    if args.command == "doctor":
        return 0, doctor(args.repo)
    if args.command == "plan":
        if args.goal in {"diff", "lint", "show"}:
            if (
                args.repo is not None
                or args.success_criteria
                or args.driver != "gemini-adk"
                or args.max_workers != 2
                or args.command_id is not None
                or args.open_viewer
            ):
                raise MissionCliError(
                    f"plan {args.goal} does not accept planning options"
                )
            if args.plan_id is None:
                raise MissionCliError(f"plan {args.goal} requires a mission ID")
            if args.goal == "diff":
                if args.previous_revision is None or args.revision is None:
                    raise MissionCliError(
                        "plan diff requires a mission ID and two revisions"
                    )
                return 0, _plan_diff_value(
                    args.plan_id, args.previous_revision, args.revision
                )
            if args.previous_revision is not None or args.revision is not None:
                raise MissionCliError(
                    f"plan {args.goal} does not accept revision arguments"
                )
            if args.goal == "show":
                return 0, _plan_show_value(args.plan_id)
            value = _plan_lint_value(args.plan_id)
            return (0 if value["valid"] else 1), value
        if (
            args.plan_id is not None
            or args.previous_revision is not None
            or args.revision is not None
        ):
            raise MissionCliError("multi-word plan goals must be quoted")
        if args.repo is None:
            raise MissionCliError("plan requires --repo")
        return 0, _start(args)
    if args.command == "status":
        return 0, _status_value(args.mission_id)
    if args.command == "watch":
        args.mission_id = args.run_id
        return 0, _watch_value(args)
    if args.command == "why":
        return 0, _why_value(args)
    if args.command == "bundle":
        if args.bundle_action == "create":
            return 0, _bundle_create_value(args)
        if args.bundle_action == "verify":
            return 0, _bundle_verify_value(args)
        raise MissionCliError("bundle action is not available")
    if args.command in {"cancel", "request-replan", "retry"}:
        return 0, _mutate(args)
    if args.command == "task":
        if args.task_action == "input":
            return 0, _task_input_value(args)
        raise MissionCliError("task action is not available")
    if args.command == "run":
        args.mission_id = args.task
        args.mission_action = "approve-plan"
        args.revision = (
            _store_for_mission(args.mission_id).snapshot(args.mission_id).plan.revision
        )
        return 0, _mutate(args)
    if args.command != "mission":
        raise MissionCliError("not a mission CLI command")
    if args.mission_action == "replay":
        return _replay(args), None
    if args.mission_action == "demo":
        return 0, _demo(args)
    if args.mission_action == "executor":
        if args.executor_action == "connect":
            return 0, _executor_connect(args)
        raise MissionCliError("executor action is not available")
    if args.mission_action == "status":
        return 0, _status_value(args.mission_id)
    if args.mission_action == "open":
        return _open_live(args.mission_id), None
    if args.mission_action == "watch":
        return 0, _watch_value(args)
    if args.mission_action == "start":
        return 0, _start(args)
    if args.mission_action == "result":
        return 0, _result_command(args)
    if args.mission_action == "capsule":
        return _capsule_command(args)
    if args.mission_action == "db":
        return 0, _database_command(args)
    return 0, _mutate(args)


def handle(args: argparse.Namespace, *, json_mode: bool | None = None) -> int:
    json_mode = getattr(args, "json_mode", False) if json_mode is None else json_mode
    if getattr(args, "command", None) == "why" and getattr(
        args, "json_mode_local", False
    ):
        # `graphene why ... --json` is honoured even when handle() is called
        # directly with the parsed namespace rather than through main().
        json_mode = True
    try:
        code, value = _dispatch(args)
        if value is not None:
            if json_mode:
                sys.stdout.write(canonical_json_bytes(value).decode() + "\n")
            elif (
                args.command == "status"
                or args.command == "mission"
                and args.mission_action == "status"
            ):
                sys.stdout.write(_render_status(value))
            elif (
                args.command == "watch"
                or args.command == "mission"
                and args.mission_action == "watch"
            ):
                if value["snapshot"] is not None:
                    sys.stdout.write(_render_status(value["snapshot"]))
                sys.stdout.write(
                    f"WATCH events={len(value['events'])} next_after_seq={value['next_after_seq']}\n"
                )
            elif (
                args.command == "mission"
                and args.mission_action == "capsule"
                and args.capsule_action == "verify"
            ):
                sys.stdout.write(_render_capsule_verify(value))
            elif args.command == "plan" and args.goal == "lint":
                sys.stdout.write(_render_plan_lint(value))
            elif args.command == "plan" and args.goal in {"diff", "show"}:
                sys.stdout.write(canonical_json_bytes(value).decode() + "\n")
            elif args.command == "why":
                sys.stdout.write(_render_why(value))
            else:
                fields = " ".join(
                    f"{key}={item}"
                    for key, item in value.items()
                    if not isinstance(item, (dict, list))
                )
                sys.stdout.write(f"GRAPHENE {fields}\n")
        return code
    except KeyboardInterrupt:
        return 130
    except MissionCliError as error:
        sys.stderr.write(f"MISSION_ERROR: {error}\n")
        return 1
    except ScriptedError:
        sys.stderr.write("MISSION_ERROR: scripted mission failed closed\n")
        return 1
    except Exception as error:
        if error.__class__.__module__.startswith(
            "graphene.orchestration"
        ) or isinstance(error, (OSError, ValueError)):
            sys.stderr.write("MISSION_ERROR: mission operation was rejected\n")
            return 1
        raise


__all__ = [
    "_MISSION_COMMANDS",
    "MissionCliError",
    "build_parser",
    "doctor",
    "handle",
    "initialize",
    "register_commands",
]
