from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import re
import secrets
import shlex
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

from ..execution.adapter import SANDBOX_CHECK_TEMPLATES
from ..hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from ..core_models import TruthKind
from ..orchestration.evidence import SQLiteAttemptEvidenceStore, TrustedCheckReceipt
from ..orchestration.cloud_protocol import ExecutorArtifactObservation
from ..orchestration.executor_client import (
    CoordinatorClient,
    ExecutorCompletion,
    GoogleAdcAudienceTokenProvider,
)
from ..orchestration.local_executor import run_local_executor
from ..orchestration.adk_planner import (
    AdkPlanner,
    LIVE_GEMINI_MODEL,
    PlanProposal,
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
from ..orchestration.mission_models import (
    AuthorizationMode,
    AttemptResult,
    AttemptState,
    CommandTemplate,
    Dispatch,
    FinalizationMode,
    Mission,
    PLAN_AWAITING_REVIEW_UNKNOWN,
    MissionEventType,
    MissionHead,
    MissionStatus,
    NetworkPolicy,
    ProjectPolicy,
    ResourceBudget,
    RetentionPolicy,
    Task,
    TaskKind,
    plan_policy_decision,
)
from ..orchestration.validation import evaluate_plan_policy
from ..orchestration.diagnostics import (
    CHECK_DIAGNOSTIC_KIND,
    CheckDiagnostic,
    summarize_check_failure,
)
from ..orchestration.overlap import measure_overlap
from ..orchestration.mission_projection import MissionProjection
from ..orchestration.sqlite_lifecycle import serialized_connection
from .dashboard import GEMINI_3_5_FLASH_USD_PER_TOKEN, spend_from_receipts
from ..orchestration.worker_runtime import (
    WORKER_PROVIDER_INTERRUPTION_KIND,
    WORKER_PROVIDER_RECEIPT_KIND,
    CheckOutcome,
    DockerCheckRunner,
    HostSandboxCheckRunner,
    PriorFailure,
    RuntimeAssignment,
    RuntimeErrorCode,
    RuntimeFailure,
    WorkerProviderReceipt,
    WorkerProviderInterruption,
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
    process_registration_lock,
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


class _PersistedBundleMissing(MissionCliError):
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
        "goal",
        help=(
            "bounded goal, or one of the actions: show, lint, export, revise, "
            "diff, approve, edit"
        ),
    )
    plan.add_argument(
        "plan_id",
        nargs="?",
        help=(
            "mission ID for a plan action, or the edited plan file for revise; "
            "otherwise the goal must be quoted"
        ),
    )
    plan.add_argument(
        "previous_revision", nargs="?", type=_revision, help="plan diff source revision"
    )
    plan.add_argument(
        "target_revision", nargs="?", type=_revision, help="plan diff target revision"
    )
    plan.add_argument(
        "--detail",
        action="store_true",
        help=_option_help(
            "render the full node contract, not the mission table",
            "graphene plan show mission_123 --detail",
            "the mission cannot be verified",
        ),
    )
    plan.add_argument(
        "--output",
        type=Path,
        help=_option_help(
            "write the canonical export to a new file instead of stdout",
            "--output plan.yaml",
            "the path already exists",
        ),
    )
    plan.add_argument(
        "--revision",
        type=_revision,
        help=_option_help(
            "the exact plan revision to approve",
            "--revision 2",
            "it is not the committed revision",
        ),
    )
    plan.add_argument(
        "--plan-sha256",
        help=_option_help(
            "the exact plan digest you are approving, as shown by plan show/diff",
            "--plan-sha256 8b3f…",
            "it is not the digest of the committed revision",
        ),
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
    plan.add_argument(
        "--operator-label",
        default="local-operator",
        help=_option_help(
            "public decision label for plan approve, never a credential",
            "--operator-label alex",
            "the label is invalid",
        ),
    )
    plan.add_argument(
        "--rationale",
        help=_option_help(
            "optional public rationale for plan approve, max 280 chars",
            "--rationale 'Added the export node'",
            "the rationale exceeds the bound",
        ),
    )
    plan.add_argument(
        "--confirm-human",
        action="store_true",
        help=_option_help(
            "attest deliberate interactive approval",
            "--confirm-human",
            "stdin or stdout is not a TTY",
        ),
    )
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
        "--file",
        type=Path,
        dest="input_file",
        help="regular UTF-8 file, max 4096 bytes",
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
        "--inject-check-fault",
        dest="demo_injected_check_fault",
        action="store_true",
        help=_option_help(
            "fail this mission's first trusted check once, deterministically, "
            "labelled simulated_fixture in evidence, so the retry path can be "
            "demonstrated and measured; it can only make a check fail, never pass",
            "--inject-check-fault",
            "the driver has no supported deterministic check runner",
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
    watch.add_argument(
        "--follow",
        action="store_true",
        help=_option_help(
            "keep following the live mission dashboard until it is terminal",
            "--follow",
            "the mission cannot be projected or Ctrl-C interrupts the follow",
        ),
    )

    cancel = _mission_parser(
        actions,
        "cancel",
        summary="cancel the mission and only its strongly owned processes",
        example=(
            "graphene mission cancel mission_123 --confirm mission_123 --confirm-human"
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
        "--plan-sha256",
        help=_option_help(
            "the exact plan digest you are approving, as shown by plan show/diff",
            "--plan-sha256 8b3f…",
            "it is not the digest of the committed revision",
        ),
    )
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


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "PATH": os.defpath,
    }


def _git_executable() -> str:
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise MissionCliError("Git is unavailable")
    return executable


def _git_root(value: Path) -> tuple[Path, str]:
    executable = _git_executable()
    try:
        root = subprocess.run(
            (executable, "rev-parse", "--show-toplevel"),
            cwd=value.resolve(strict=True),
            env=_git_environment(),
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
            env=_git_environment(),
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
        executable = _git_executable()
        try:
            ancestor = subprocess.run(
                (executable, "merge-base", "--is-ancestor", policy.base_sha, head),
                cwd=root,
                env=_git_environment(),
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
                env=_git_environment(),
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
        from ..orchestration.sqlite_mission_store import SQLiteMissionStore
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
    from ..orchestration.mission_projection import MissionProjection

    return MissionProjection(_store(mission_id), legacy_viewer_base=None)


def _status_value(mission_id: str) -> dict[str, object]:
    projection = _projection(mission_id)
    try:
        value = projection.snapshot(mission_id)
        return value.model_dump(mode="json")
    finally:
        close = getattr(projection.store, "close", None)
        if callable(close):
            close()


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
    """The mission contract as one value: the plan, plus where it stands.

    The plan itself comes from the immutable revision the store holds; the
    state, critical path, frontier, and pending decision come from the same
    projection the dashboard reads, so the table and the dashboard cannot
    disagree about what is ready.
    """
    _store_value, snapshot = _verified_plan_snapshot(mission_id, "show")
    plan = snapshot.plan.model_dump(mode="json")
    projection = _projection(mission_id)
    try:
        view = projection.snapshot(mission_id)
        states = {task.task_id: task.state for task in view.tasks}
        blockers = {task.task_id: task.blocker_reason for task in view.tasks}
        return {
            "status": "shown",
            "mission_id": mission_id,
            "base_sha": snapshot.mission.base_sha,
            "goal": snapshot.mission.goal,
            "mission_status": snapshot.mission.status.value,
            "plan_revision": snapshot.plan.revision,
            "previous_plan_revision": snapshot.plan.previous_revision,
            "plan_sha256": sha256_hex(canonical_json_bytes(plan)),
            "approved_revision": _approved_revision(snapshot),
            "requested_authorization_mode": (
                view.mission.requested_authorization_mode.value
            ),
            "effective_authorization_mode": (
                None
                if view.mission.effective_authorization_mode is None
                else view.mission.effective_authorization_mode.value
            ),
            "finalization_mode": view.mission.finalization_mode.value,
            "policy_decision_sha256": view.mission.policy_decision_sha256,
            "critical_path": list(view.critical_path_task_ids),
            "resource_budget": snapshot.mission.resource_budget.model_dump(mode="json"),
            "ready_frontier": _frontier(view.tasks),
            # Before approval nothing is `ready` yet, so the frontier shown is the
            # one the graph implies. Say which it is rather than let the reader
            # assume work has started.
            "frontier_is_projected": not any(
                task.state == "ready" for task in view.tasks
            ),
            "needs_you": (
                None
                if view.needs_you is None
                else view.needs_you.model_dump(mode="json")
            ),
            "task_states": states,
            "task_blockers": {key: item for key, item in blockers.items() if item},
            "plan": plan,
        }
    finally:
        close = getattr(projection.store, "close", None)
        if callable(close):
            close()


def _frontier(tasks) -> list[str]:
    """What can run right now — or, before dispatch, what would run first."""
    ready = [task.task_id for task in tasks if task.state == "ready"]
    if ready:
        return ready
    open_ids = {
        task.task_id for task in tasks if task.state not in {"done", "cancelled"}
    }
    return [
        task.task_id
        for task in tasks
        if task.task_id in open_ids and not (set(task.dependency_ids) & open_ids)
    ]


def _approved_revision(snapshot) -> int | None:
    """The revision an approval names, or None while one is still needed."""
    store = _store_for_mission(snapshot.mission.mission_id)
    events = store.tail(snapshot.mission.mission_id, 0, snapshot.head.seq)
    for event in reversed(events):
        if event.event_type.value == "plan.approved":
            revision = event.payload.get("plan_revision")
            return revision if isinstance(revision, int) else None
    return None


def _plan_export_value(mission_id: str, output: Path | None) -> dict[str, object]:
    """Write the canonical YAML a person edits."""
    from ..orchestration.plan_yaml import plan_to_yaml

    _store_value, snapshot = _verified_plan_snapshot(mission_id, "export")
    document = plan_to_yaml(snapshot.plan)
    digest = sha256_hex(canonical_json_bytes(snapshot.plan.model_dump(mode="json")))
    value: dict[str, object] = {
        "status": "exported",
        "mission_id": mission_id,
        "plan_revision": snapshot.plan.revision,
        "plan_sha256": digest,
        "document": document,
    }
    if output is not None:
        path = _new_file_path(output)
        _atomic_create(path, document.encode())
        value["exported_to"] = str(path)
        value["document"] = ""
    return value


def _plan_revise_value(source: Path) -> dict[str, object]:
    """Compile an edited export into immutable revision N+1.

    The file names its own mission and the revision it was taken from; this
    refuses to guess either. The new revision is not approved by making it —
    that is a separate decision, on a new digest.
    """
    from ..orchestration.mission_models import Plan
    from ..orchestration.plan_yaml import PlanDocumentError, plan_from_yaml
    from ..orchestration.sqlite_mission_store import MissionConflict
    from ..orchestration.validation import PlanValidationError

    try:
        text = source.expanduser().read_text()
    except OSError as error:
        raise MissionCliError("the edited plan file cannot be read") from error
    try:
        edited = plan_from_yaml(text)
    except PlanDocumentError as error:
        raise MissionCliError(f"plan revise refused the document: {error}") from error

    store, snapshot = _verified_plan_snapshot(edited.mission_id, "revise")
    current = snapshot.plan
    if edited.revision != current.revision:
        raise MissionCliError(
            f"the edited plan is revision {edited.revision} but the mission is on "
            f"revision {current.revision}; export it again"
        )
    if edited == current:
        raise MissionCliError("the edited plan is identical to the committed revision")
    revised = Plan.model_validate(
        {
            **edited.model_dump(mode="json"),
            "previous_revision": current.revision,
            "revision": current.revision + 1,
        }
    )
    try:
        store.revise_plan(
            edited.mission_id,
            revised,
            _command_id("revise-plan", edited.mission_id, str(revised.revision)),
            expected_head=snapshot.head,
            recorded_at=datetime.now(UTC),
        )
    except PlanValidationError as error:
        raise MissionCliError(
            f"the revised plan is not valid under this project policy: {error}"
        ) from error
    except MissionConflict as error:
        raise MissionCliError(f"plan revise was refused: {error}") from error
    return {
        "status": "revised",
        "mission_id": edited.mission_id,
        "previous_plan_revision": current.revision,
        "plan_revision": revised.revision,
        "plan_sha256": sha256_hex(
            canonical_json_bytes(revised.model_dump(mode="json"))
        ),
        "needs_approval": True,
    }


def _plan_diff_value(
    mission_id: str, previous_revision: int, revision: int
) -> dict[str, object]:
    store, _snapshot = _verified_plan_snapshot(mission_id, "diff")
    return store.plan_diff(mission_id, previous_revision, revision)


def _scripted_policy(mission_id: str):
    """The fixture's own project policy — the bound the edit still lives under."""
    from ..orchestration.scripted import _persisted_scenario

    store = _store_for_mission(mission_id)
    snapshot = store.snapshot(mission_id)
    scenario = _persisted_scenario(_mission_runtime(mission_id))
    policy, _mission, _plan = scenario.contracts(
        mission_id=mission_id,
        repo_id=snapshot.mission.repo_id,
        base_sha=snapshot.mission.base_sha,
        created_at=snapshot.mission.created_at,
    )
    return policy


def _plan_lint_value(mission_id: str) -> dict[str, object]:
    from ..orchestration.validation import validate_plan

    store, snapshot = _verified_plan_snapshot(mission_id, "lint")
    if snapshot.mission.creation_source == "scripted_fixture":
        # Revision 1 of a fixture mission is checked against the fixture that
        # produced it. Once a person has edited it, that comparison is no
        # longer the question — the policy is.
        result = (
            scripted_plan_validation(store, _mission_runtime(mission_id), mission_id)
            if snapshot.plan.revision == 1
            else validate_plan(_scripted_policy(mission_id), snapshot.plan)
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
        raise MissionCliError("output must name a new file")
    try:
        unresolved_parent = requested.parent.absolute()
        parent = unresolved_parent.resolve(strict=True)
        metadata = parent.lstat()
    except OSError as error:
        raise MissionCliError("output directory is unavailable") from error
    if (
        unresolved_parent != parent
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise MissionCliError(
            "output directory must be a real directory, not a symlink"
        )
    path = parent / requested.name
    if path.exists() or path.is_symlink():
        raise MissionCliError("output must be a new non-symlink file")
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
    if not matches:
        raise _PersistedBundleMissing("locally persisted bundle ID is missing")
    if len(matches) != 1:
        raise MissionCliError("locally persisted bundle ID is ambiguous")
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
    if not persisted.exists() and not persisted.is_symlink():
        try:
            _atomic_create(persisted, raw)
        except MissionCliError:
            if not persisted.exists() and not persisted.is_symlink():
                raise
    existing, existing_bundle = _read_bundle(persisted)
    if existing != raw or existing_bundle.bundle_id != bundle.bundle_id:
        raise MissionCliError("persisted bundle ID has different canonical bytes")
    try:
        descriptor = os.open(persisted, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory_descriptor = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise MissionCliError("persisted bundle could not be made durable") from error
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


_TERMINAL_MISSION_STATES = frozenset({"completed", "rejected", "failed", "cancelled"})


def _next_legal_actions(value: dict[str, object]) -> list[str]:
    """The exact commands that are legal right now, derived from the store.

    Not advice: each line is a command whose preconditions the projection says
    are met. A mission that needs a person names that decision first.
    """
    mission = value["mission"]
    mission_id = mission["mission_id"]
    status = str(mission["status"])
    needs = value.get("needs_you")
    if status in _TERMINAL_MISSION_STATES:
        return [
            f"graphene why {mission_id} PATH",
            f"graphene mission capsule export {mission_id} --output DIR",
        ]
    if status == "proposed":
        if mission.get("effective_authorization_mode", "review_required") is None:
            return [
                f"graphene mission status {mission_id}",
                f"graphene mission watch {mission_id} --follow",
            ]
        revision = mission["plan_revision"]
        return [
            f"graphene plan show {mission_id} --detail",
            f"graphene plan export {mission_id} --output plan.yaml",
            f"graphene plan approve {mission_id} --revision {revision}",
        ]
    if isinstance(needs, dict):
        options = [str(item["value"]) for item in needs.get("options", ())]
        gate = needs.get("gate_id")
        if str(gate or "").startswith("final"):
            return [
                f"graphene mission result show {mission_id}",
                f"graphene mission approve-result {mission_id} --bundle-id FINAL_RESULT_ID",
                f"graphene mission reject-result {mission_id} --bundle-id FINAL_RESULT_ID",
            ]
        return [
            f"graphene mission decide-gate {mission_id} --gate {gate} --decision {item}"
            for item in options
        ] or [f"graphene mission status {mission_id}"]
    if status == "paused":
        return [f"graphene mission resume {mission_id}"]
    return [
        f"graphene mission watch {mission_id} --follow",
        f"graphene mission cancel {mission_id} --confirm {mission_id}",
    ]


def _frontier_line(value: dict[str, object]) -> str:
    """What can run now, or — before dispatch — what the graph says would."""
    tasks = value["tasks"]
    ready = [str(task["task_id"]) for task in tasks if task["state"] == "ready"]
    if ready:
        return "FRONTIER " + ", ".join(ready)
    open_ids = {
        str(task["task_id"])
        for task in tasks
        if task["state"] not in {"done", "cancelled"}
    }
    projected = [
        str(task["task_id"])
        for task in tasks
        if str(task["task_id"]) in open_ids
        and not (set(task["dependency_ids"]) & open_ids)
    ]
    return "FRONTIER ON APPROVAL " + (", ".join(projected) or "none")


def _render_status(value: dict[str, object]) -> str:
    """The orientation view: everything a fresh process needs, from the store.

    No transcript is involved. Approved revision and digest, the route already
    taken, what can run next, what changed on disk, what scope is still
    outstanding, the last structured failure, blockers, the decision waiting on
    a person, and the exact next legal commands — all reduced from committed
    mission events.
    """
    mission = value["mission"]
    tasks = value["tasks"]
    by_state: dict[str, list[str]] = {}
    for task in tasks:
        by_state.setdefault(str(task["state"]), []).append(str(task["task_id"]))
    approved = mission.get("approved_plan_revision")
    lines = [
        f"MISSION {mission['mission_id']} {str(mission['status']).upper()}",
        f"GOAL {mission['goal']}",
        f"PLAN v{mission['plan_revision']} {_short(mission.get('plan_sha256'))} "
        + (
            "approved"
            if approved == mission["plan_revision"]
            else f"approval: {'none' if approved is None else f'v{approved}'}"
        ),
        "ROUTE DONE " + (", ".join(by_state.get("done", ())) or "nothing yet"),
        _frontier_line(value),
        "RUNNING " + (", ".join(by_state.get("running", ())) or "none"),
        "CRITICAL PATH "
        + (
            " → ".join(str(item) for item in value.get("critical_path_task_ids", ()))
            or "none"
        ),
    ]
    changed = sorted(
        {
            str(path)
            for item in value.get("publications", ())
            if item.get("state") == "accepted"
            for path in item.get("paths", ())
        }
    )
    lines.append("CHANGED " + (", ".join(changed) or "nothing accepted yet"))
    remaining = [
        f"{task['task_id']}→{','.join(task['write_scope']) or 'nothing'}"
        for task in tasks
        if task["state"] not in {"done", "cancelled"} and task["write_scope"]
    ]
    lines.append("REMAINING SCOPES " + ("; ".join(remaining) or "none"))
    failures = [
        f"{item['task_id']} attempt {item['number']} {item['result_code']}"
        for item in value.get("attempts", ())
        if item.get("result_code") not in {None, "passed"}
    ]
    lines.append("LAST FAILURE " + (failures[-1] if failures else "none"))
    blockers = [
        f"{task['task_id']} — {task['blocker_reason']}"
        for task in tasks
        if task.get("blocker_reason")
    ]
    lines.extend(f"BLOCKED {item}" for item in blockers or ["none"])
    needs = value.get("needs_you")
    if (
        mission["status"] == "proposed"
        and mission.get("effective_authorization_mode", "review_required") is None
    ):
        decision = "nothing — policy evaluation pending"
    elif isinstance(needs, dict):
        decision = needs.get("reason")
    elif approved != mission["plan_revision"]:
        # A mission waiting on plan approval is waiting on a person, whatever
        # the runtime gates say.
        decision = (
            f"approve plan v{mission['plan_revision']} on "
            f"{_short(mission.get('plan_sha256'))}, or revise it first"
        )
    else:
        decision = "No decision needed"
    lines.append(f"NEEDS YOU {decision}")
    lines.extend(f"NEXT {item}" for item in _next_legal_actions(value))
    return "\n".join(lines) + "\n"


_WHY_RECEIPT_KINDS = frozenset(
    {"test-receipt", "worker-provider-interruption", "worker-provider-receipt"}
)
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
    if node.get("state") is not None:
        line += f" state={field('state')} result_code={field('result_code')}"
    if node.get("stage_reached") is not None:
        line += f" stage={field('stage_reached')}"
    return line


def _render_why(value: dict[str, object]) -> str:
    # The first line is pinned by tests and docs; everything after it is one
    # block per causal link, then explicit unknowns, then the trust statement.
    approved = value.get("approved_plan_revision")
    lines = [
        f"WHY {value['mission_id']} {value['query']} matched_by={value['matched_by']}",
        f"PLAN v{value['plan_revision']} {_short(value['plan_sha256'])} "
        + (
            "approved"
            if approved == value["plan_revision"]
            else f"approval: {'none' if approved is None else f'v{approved}'}"
        ),
    ]
    for link in value["links"]:
        lines.append(f"STAGE {link['stage']} {link['status']}")
        lines.extend(_render_why_node(item) for item in link.get("nodes", ()))
        lines.append(f"  events {','.join(link.get('event_ids', ())) or 'none'}")
        lines.append(f"  note {link['note']}")
    lines.extend(f"UNKNOWN {item}" for item in value["unknowns"])
    lines.append(_WHY_TRUST_LINE)
    return "\n".join(lines) + "\n"


def _short(digest: object) -> str:
    return f"sha256:{str(digest)[:12]}…" if digest else "sha256:none"


def _plan_table_rows(value: dict[str, object]) -> list[tuple[str, ...]]:
    plan = value["plan"]
    states = value.get("task_states", {})
    rows: list[tuple[str, ...]] = [
        ("ID", "STATE", "DEPS", "ROLE", "READ/WRITE", "CHECKS")
    ]
    for task in plan["tasks"]:
        task_id = task["task_id"]
        rows.append(
            (
                task_id,
                str(states.get(task_id, task["state"])),
                ",".join(task.get("dependencies", ())) or "-",
                task["assigned_role"],
                f"{len(task['read_paths'])} / {len(task['write_paths'])}",
                str(len(task["acceptance_checks"])),
            )
        )
    return rows


def _columns(rows: list[tuple[str, ...]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    return "\n".join(
        "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip()
        for row in rows
    )


def _render_plan_table(value: dict[str, object]) -> str:
    """The mission contract, at a glance: what runs, in what order, under what scope."""
    plan = value["plan"]
    approved = value.get("approved_revision")
    revision = value["plan_revision"]
    lines = [
        f"Mission: {value['mission_id']}      Base: {str(value['base_sha'])[:12]}      "
        f"Plan: v{revision} / {_short(value['plan_sha256'])}",
        "",
        _columns(_plan_table_rows(value)),
        "",
    ]
    path = value.get("critical_path") or [task["task_id"] for task in plan["tasks"]][:1]
    lines.append("Critical path: " + " → ".join(path))
    frontier = value.get("ready_frontier") or []
    approval = (
        "Policy evaluation pending"
        if value.get("effective_authorization_mode") is None
        else f"Needs approval: plan v{revision}"
        if approved != revision
        else f"Approved: plan v{revision}"
    )
    label = (
        "Frontier on approval"
        if value.get("frontier_is_projected")
        else "Ready frontier"
    )
    lines.append(f"{label}: {', '.join(frontier) or 'none'}          {approval}")
    blockers = value.get("task_blockers") or {}
    lines.extend(f"Blocked: {key} — {item}" for key, item in sorted(blockers.items()))
    needs = value.get("needs_you")
    if isinstance(needs, dict):
        lines.append(f"Needs you: {needs.get('question') or needs.get('gate_id')}")
    lines.append(f"Inspect one node: graphene plan show {value['mission_id']} --detail")
    return "\n".join(lines) + "\n"


def _render_node_contract(task: dict[str, object], value: dict[str, object]) -> str:
    """Everything the approved node authorizes — nothing summarized away."""
    states = value.get("task_states", {})
    budget = value.get("resource_budget") or {}
    lines = [
        f"NODE {task['task_id']}  {task['kind']}  "
        f"state={states.get(task['task_id'], task['state'])}",
        f"  title            {task['title']}",
        f"  contract         {task['contract']}",
        "  outcome owned    "
        + "; ".join(
            f"{item['name']}:{item['kind']}"
            + (f" -> {', '.join(item['paths'])}" if item["paths"] else "")
            for item in task["expected_outputs"]
        ),
        f"  requires         {', '.join(task['dependencies']) or 'nothing'}",
        "  consumes         "
        + (
            "; ".join(
                f"{item['producer_task_id']}/{item['name']}:{item['kind']}"
                for item in task["inputs"]
            )
            or "nothing"
        ),
        f"  read scope       {', '.join(task['read_paths'])}",
        f"  write scope      {', '.join(task['write_paths']) or 'nothing'}",
        f"  allowed commands {', '.join(task['allowed_commands'])}",
        f"  acceptance       {', '.join(task['acceptance_checks'])}",
        f"  role             {task['assigned_role']}",
        f"  attempts         {task['attempt_count']} of {task['attempt_limit']}",
        f"  priority         {task['priority']}",
        f"  evidence         {task['evidence_adapter']} "
        f"(attempt evidence, trusted check receipt)",
        f"  bound to         mission {value['mission_id']} base "
        f"{str(value['base_sha'])[:12]} plan v{value['plan_revision']} "
        f"{_short(value['plan_sha256'])}",
    ]
    if budget:
        lines.append(
            f"  mission budget   {budget.get('max_worker_seconds')}s worker time, "
            f"{budget.get('max_attempts')} attempts, "
            f"{budget.get('max_artifact_bytes')} artifact bytes"
        )
    blocker = (value.get("task_blockers") or {}).get(task["task_id"])
    if blocker:
        lines.append(f"  blocker          {blocker}")
    return "\n".join(lines)


def _render_plan_detail(value: dict[str, object]) -> str:
    plan = value["plan"]
    lines = [
        f"Mission: {value['mission_id']}      Base: {str(value['base_sha'])[:12]}      "
        f"Plan: v{value['plan_revision']} / {_short(value['plan_sha256'])}",
        f"Goal: {value['goal']}",
        "",
    ]
    for criterion in plan.get("criteria", ()):
        lines.append(
            f"CRITERION {criterion['criterion_id']}  {criterion['description']}"
        )
        lines.append(
            f"  produced by      {', '.join(criterion['producer_task_ids']) or 'none'}"
        )
        lines.append(
            f"  verified by      {criterion['verification_kind']} "
            f"{criterion['verifier_task_id'] or 'human gate'}"
        )
    lines.append("")
    for task in plan["tasks"]:
        lines.append(_render_node_contract(task, value))
        lines.append("")
    lines.append(
        "Policy evaluation pending: no operator decision is legal yet."
        if value.get("effective_authorization_mode") is None
        else f"Human gate: this plan cannot dispatch until revision {value['plan_revision']} "
        f"is approved on {_short(value['plan_sha256'])}."
        if value.get("approved_revision") != value["plan_revision"]
        else f"Approved: revision {value['plan_revision']} on "
        f"{_short(value['plan_sha256'])}."
    )
    return "\n".join(lines) + "\n"


_SCOPE_FIELDS = ("read_paths", "write_paths", "allowed_commands", "acceptance_checks")
_EDGE_FIELDS = ("dependencies", "inputs")


def _item_label(item: object) -> str:
    """A short identity for a structured list entry, not its whole dump."""
    if not isinstance(item, dict):
        return str(item)
    for keys in (
        ("producer_task_id", "name", "kind"),
        ("name", "kind"),
        ("criterion_id",),
        ("task_id",),
    ):
        if all(key in item for key in keys):
            return "/".join(str(item[key]) for key in keys)
    return ",".join(f"{key}={item[key]}" for key in sorted(item))


def _list_change(field: str, before: list[object], after: list[object]) -> str:
    old_by_label = {_item_label(item): item for item in before}
    new_by_label = {_item_label(item): item for item in after}
    added = sorted(new_by_label.keys() - old_by_label.keys())
    removed = sorted(old_by_label.keys() - new_by_label.keys())
    altered = sorted(
        label
        for label in old_by_label.keys() & new_by_label.keys()
        if old_by_label[label] != new_by_label[label]
    )
    parts = [
        *(f"+{label}" for label in added),
        *(f"-{label}" for label in removed),
        *(f"~{label}" for label in altered),
    ]
    detail = ", ".join(parts)
    # A scope that only grew is the change a reviewer must not miss.
    widened = field in _SCOPE_FIELDS and added and not removed
    return f"{detail}{'  ** SCOPE EXPANSION **' if widened else ''}"


def _field_change(before: dict[str, object], after: dict[str, object]) -> list[str]:
    """Name the fields that moved, and say when a scope grew."""
    lines: list[str] = []
    for field in sorted(set(before) | set(after)):
        if before.get(field) == after.get(field):
            continue
        old, new = before.get(field), after.get(field)
        if isinstance(old, list) and isinstance(new, list):
            kind = "edge" if field in _EDGE_FIELDS else "field"
            lines.append(f"    {kind} {field}: {_list_change(field, old, new)}")
        else:
            lines.append(f"    field {field}: {old!r} -> {new!r}")
    return lines


def _render_plan_diff(value: dict[str, object]) -> str:
    """What changed between two revisions, in the terms a person edited."""
    lines = [
        f"PLAN DIFF {value['mission_id']} "
        f"v{value['previous_plan_revision']} -> v{value['plan_revision']}",
        f"  from {_short(value['previous_plan_sha256'])} "
        f"to {_short(value['plan_sha256'])}",
    ]
    concurrency = value["max_concurrency"]
    if concurrency["before"] != concurrency["after"]:
        lines.append(
            f"  max_concurrency {concurrency['before']} -> {concurrency['after']}"
        )
    for section in ("tasks", "criteria"):
        label = "NODE" if section == "tasks" else "CRITERION"
        key = "task_id" if section == "tasks" else "criterion_id"
        block = value[section]
        for item in block["added"]:
            lines.append(f"  + {label} {item[key]} added")
            if section == "tasks":
                lines.append(
                    f"    writes {', '.join(item['write_paths']) or 'nothing'}; "
                    f"needs {', '.join(item['dependencies']) or 'nothing'}"
                )
        for item in block["removed"]:
            lines.append(f"  - {label} {item[key]} removed")
        for item in block["changed"]:
            lines.append(f"  ~ {label} {item['after'][key]} changed")
            lines.extend(_field_change(item["before"], item["after"]))
    if len(lines) == 2:
        lines.append("  no change")
    lines.append(
        f"  approve this revision: graphene plan approve {value['mission_id']} "
        f"--revision {value['plan_revision']}"
    )
    return "\n".join(lines) + "\n"


def _render_plan_revised(value: dict[str, object]) -> str:
    return (
        f"PLAN REVISED {value['mission_id']} "
        f"v{value['previous_plan_revision']} -> v{value['plan_revision']} "
        f"{_short(value['plan_sha256'])}\n"
        f"Not approved yet — the new digest needs its own approval.\n"
        f"  graphene plan diff {value['mission_id']} "
        f"{value['previous_plan_revision']} {value['plan_revision']}\n"
        f"  graphene plan lint {value['mission_id']}\n"
        f"  graphene plan approve {value['mission_id']} "
        f"--revision {value['plan_revision']}\n"
    )


_PLAN_ACTIONS = frozenset(
    {"approve", "diff", "edit", "export", "lint", "revise", "show"}
)


def _plan_action(args: argparse.Namespace) -> tuple[int, object | None]:
    """The plan verb's actions: inspect, export, revise, lint, diff, approve.

    One shape for all of them — an exact target, no planning options, and a
    refusal rather than a guess when the arguments do not name one thing.
    """
    action = args.goal
    if (
        args.repo is not None
        or args.success_criteria
        or args.driver != "gemini-adk"
        or args.max_workers != 2
        or args.open_viewer
    ):
        raise MissionCliError(f"plan {action} does not accept planning options")
    if args.plan_id is None:
        raise MissionCliError(
            f"plan {action} requires "
            + ("an edited plan file" if action == "revise" else "a mission ID")
        )
    if action != "diff" and (
        args.previous_revision is not None or args.target_revision is not None
    ):
        raise MissionCliError(f"plan {action} does not accept revision arguments")
    if action != "export" and args.output is not None:
        raise MissionCliError(f"plan {action} does not accept --output")
    if action != "approve" and args.plan_sha256 is not None:
        raise MissionCliError(f"plan {action} does not accept --plan-sha256")
    if action not in {"approve", "show"} and args.detail:
        raise MissionCliError(f"plan {action} does not accept --detail")

    if action == "diff":
        if args.previous_revision is None or args.target_revision is None:
            raise MissionCliError("plan diff requires a mission ID and two revisions")
        return 0, _plan_diff_value(
            args.plan_id, args.previous_revision, args.target_revision
        )
    if action == "show":
        return 0, _plan_show_value(args.plan_id)
    if action == "export":
        return 0, _plan_export_value(args.plan_id, args.output)
    if action == "revise":
        return 0, _plan_revise_value(Path(args.plan_id))
    if action == "edit":
        return 0, _plan_edit_value(args.plan_id)
    if action == "approve":
        if args.revision is None:
            raise MissionCliError("plan approve requires --revision")
        args.mission_id = args.plan_id
        args.mission_action = "approve-plan"
        return 0, _mutate(args)
    value = _plan_lint_value(args.plan_id)
    return (0 if value["valid"] else 1), value


def _plan_edit_value(mission_id: str) -> dict[str, object]:
    """Open the canonical export in $EDITOR, then take the same revise path.

    A convenience over `export` + edit + `revise`, not a second way to change
    a plan: it writes the same YAML and calls the same compiler.
    """
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise MissionCliError(
            "plan edit needs $EDITOR or $VISUAL; use plan export and plan revise"
        )
    exported = _plan_export_value(mission_id, None)
    directory = _state_root() / "plan-edits"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{mission_id}-v{exported['plan_revision']}.yaml"
    if path.exists() or path.is_symlink():
        path.unlink()
    _atomic_create(path, str(exported["document"]).encode())
    completed = subprocess.run([*shlex.split(editor), str(path)], check=False)
    if completed.returncode != 0:
        raise MissionCliError("the editor exited non-zero; the plan was not revised")
    return _plan_revise_value(path)


def _render_plan_export(value: dict[str, object]) -> str:
    """Either the document itself, or where it was written."""
    if value.get("exported_to"):
        return (
            f"PLAN EXPORTED {value['mission_id']} v{value['plan_revision']} "
            f"{_short(value['plan_sha256'])}\n"
            f"  {value['exported_to']}\n"
            f"  edit it, then: graphene plan revise {value['exported_to']}\n"
        )
    return str(value["document"])


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
    from ..orchestration.mission_projection import MissionProjection

    if coordinate_gemini and _supervisor_backed(_mission_runtime(mission_id)):
        _ensure_detached_supervisor(mission_id)
        coordinate_gemini = False

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
    from ..orchestration.mission_replay import (
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
    try:
        authorization_mode = AuthorizationMode(
            getattr(args, "authorization_mode", AuthorizationMode.REVIEW_REQUIRED)
        )
        finalization_mode = FinalizationMode(
            getattr(args, "finalization_mode", FinalizationMode.REVIEW_REQUIRED)
        )
    except ValueError as error:
        raise MissionCliError("mission authorization mode is invalid") from error
    modes_are_bound = hasattr(args, "authorization_mode") or hasattr(
        args, "finalization_mode"
    )
    if (
        authorization_mode == AuthorizationMode.REVIEW_REQUIRED
        and finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED
    ):
        raise MissionCliError(
            "automatic finalization requires policy pre-authorization"
        )
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
        *(
            (authorization_mode.value, finalization_mode.value)
            if modes_are_bound
            else ()
        ),
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
    if modes_are_bound:
        binding.update(
            authorization_mode=authorization_mode.value,
            finalization_mode=finalization_mode.value,
        )
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
    from ..orchestration.sqlite_mission_store import MissionNotFound

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
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
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
    proposal: PlanProposal | None = None,
) -> dict[str, object]:
    if not args.success_criteria:
        raise MissionCliError(
            "gemini-adk planning requires at least one --success-criterion; "
            "no scripted fallback was used"
        )
    criteria = tuple(sorted(set(args.success_criteria)))
    if len(criteria) != len(args.success_criteria):
        raise MissionCliError("success criteria must be unique")
    if proposal is None:
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
    try:
        requested_mode = AuthorizationMode(
            getattr(args, "authorization_mode", AuthorizationMode.REVIEW_REQUIRED)
        )
        requested_finalization = FinalizationMode(
            getattr(args, "finalization_mode", FinalizationMode.REVIEW_REQUIRED)
        )
        policy_decision = evaluate_plan_policy(
            policy,
            proposal.plan,
            goal_request_id=command_id,
            requested_mode=requested_mode,
            requested_finalization_mode=requested_finalization,
        )
    except ValueError as error:
        raise MissionCliError("mission authorization request is invalid") from error
    review_required = (
        policy_decision.effective_mode == AuthorizationMode.REVIEW_REQUIRED
    )
    mission = Mission(
        schema_version=2,
        requested_authorization_mode=requested_mode,
        requested_finalization_mode=requested_finalization,
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
        unknowns=((PLAN_AWAITING_REVIEW_UNKNOWN,) if review_required else ()),
        created_at=created_at,
    )
    created_head = store.create_mission(
        policy,
        mission,
        proposal.plan,
        _command_id("create-gemini-proposal", mission_id, command_id, receipt.sha256),
        plan_proposal_receipt=receipt,
        recorded_at=created_at,
    )
    head = store.record_plan_policy_decision(
        mission_id,
        _command_id(
            "record-plan-policy-decision",
            mission_id,
            command_id,
            policy_decision.decision_sha256,
        ),
        decision=policy_decision,
        expected_head=created_head,
        recorded_at=created_at,
    )
    status = store.snapshot(mission_id).mission.status
    return {
        "status": status.value,
        "mission_id": mission_id,
        "driver": "gemini-adk",
        "proof": (
            "real Google ADK planner proposal within the exact committed project policy"
            if not review_required
            else "real Google ADK planner proposal; committed policy requires review"
        ),
        "plan_revision": 1,
        "plan_sha256": policy_decision.plan_sha256,
        "requested_authorization_mode": policy_decision.requested_mode.value,
        "effective_authorization_mode": policy_decision.effective_mode.value,
        "finalization_mode": policy_decision.finalization_mode.value,
        "policy_decision_sha256": policy_decision.decision_sha256,
        "head": head.model_dump(mode="json"),
        "review_required": review_required,
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


def _ensure_gemini_policy_decision(
    args: argparse.Namespace,
    *,
    command_id: str,
    policy: ProjectPolicy,
    store,
    snapshot,
):
    """Close the create/authorize crash window for detached starts."""

    mission_schema_version = getattr(snapshot.mission, "schema_version", 1)
    policy_schema_version = getattr(policy, "schema_version", 1)
    if mission_schema_version == policy_schema_version == 1:
        return snapshot
    del args
    events = _mission_events(
        store, snapshot.mission.mission_id, snapshot.head.event_count
    )
    try:
        committed = plan_policy_decision(events, snapshot.plan.revision)
    except ValueError as error:
        raise MissionCliError("committed policy decision is invalid") from error
    try:
        requested_mode = (
            snapshot.mission.requested_authorization_mode
            if mission_schema_version == 2
            else AuthorizationMode.REVIEW_REQUIRED
        )
        requested_finalization = (
            snapshot.mission.requested_finalization_mode
            if mission_schema_version == 2
            else FinalizationMode.REVIEW_REQUIRED
        )
        decision = evaluate_plan_policy(
            policy,
            snapshot.plan,
            goal_request_id=command_id,
            requested_mode=requested_mode,
            requested_finalization_mode=requested_finalization,
        )
    except ValueError as error:
        raise MissionCliError("mission authorization request is invalid") from error
    if committed is not None:
        if committed != decision:
            raise MissionCliError(
                "committed policy decision differs from the start request"
            )
        return snapshot
    store.record_plan_policy_decision(
        snapshot.mission.mission_id,
        _command_id(
            "record-plan-policy-decision",
            snapshot.mission.mission_id,
            command_id,
            decision.decision_sha256,
        ),
        decision=decision,
        expected_head=snapshot.head,
        recorded_at=datetime.now(UTC),
    )
    return store.snapshot(snapshot.mission.mission_id)


def _existing_gemini_proposal_value(store, snapshot) -> dict[str, object]:
    events = _mission_events(
        store, snapshot.mission.mission_id, snapshot.head.event_count
    )
    proposed = next(event for event in events if event.event_type == "plan.proposed")
    try:
        decision = plan_policy_decision(events, snapshot.plan.revision)
    except ValueError as error:
        raise MissionCliError("committed policy decision is invalid") from error
    review_required = (
        decision is None or decision.effective_mode == AuthorizationMode.REVIEW_REQUIRED
    )
    return {
        "status": snapshot.mission.status.value,
        "mission_id": snapshot.mission.mission_id,
        "driver": "gemini-adk",
        "proof": (
            "committed real Google ADK plan within the exact project policy"
            if not review_required
            else "committed real Google ADK planner proposal; policy requires review"
        ),
        "plan_revision": snapshot.plan.revision,
        "review_required": review_required,
        **(
            (
                {}
                if getattr(snapshot.mission, "schema_version", 1)
                == getattr(snapshot.policy, "schema_version", 1)
                == 1
                else {
                    "requested_authorization_mode": (
                        snapshot.mission.requested_authorization_mode.value
                    ),
                    "effective_authorization_mode": None,
                    "finalization_mode": (
                        snapshot.mission.requested_finalization_mode.value
                    ),
                    "policy_decision_sha256": None,
                }
            )
            if decision is None
            else {
                "requested_authorization_mode": decision.requested_mode.value,
                "effective_authorization_mode": decision.effective_mode.value,
                "finalization_mode": decision.finalization_mode.value,
                "policy_decision_sha256": decision.decision_sha256,
            }
        ),
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
    execute: bool = True,
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
    if not execute:
        return _scripted_proposal_value(store, mission_id, replayed=True)
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


def _git_read(repository: Path, *arguments: str) -> bytes:
    """Run one read-only Git command in ``repository`` and return its stdout."""
    executable = _git_executable()
    try:
        result = subprocess.run(
            (executable, "-C", str(repository), *arguments),
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MissionCliError("repository manifest could not be read") from error
    if result.returncode:
        raise MissionCliError("repository manifest could not be read")
    return result.stdout


def _planning_source_drift(repository: Path, base_sha: str) -> tuple[str, ...]:
    """Tracked or staged paths whose bytes differ from the bound commit.

    ``.graphene/project.json`` is the one exception, for the same reason
    ``_load_project_policy`` already tolerates it: ``graphene init`` writes the
    policy after the base commit and the planner never reads it.
    """
    drift: set[str] = set()
    for arguments in (
        ("diff", "--name-only", "-z", base_sha, "--"),
        ("diff", "--cached", "--name-only", "-z", base_sha, "--"),
    ):
        drift.update(
            os.fsdecode(raw)
            for raw in _git_read(repository, *arguments).split(b"\0")
            if raw
        )
    return tuple(sorted(drift - {".graphene/project.json"}))


def _committed_blobs(repository: Path, base_sha: str) -> dict[str, tuple[str, int]]:
    """``{path: (object_id, size)}`` for every regular file in ``base_sha``.

    Symlink (``120000``) and submodule (``160000``) entries are dropped: the
    planner reads file content, and a tree symlink's content is a path.
    """
    records = _git_read(
        repository, "ls-tree", "-r", "-l", "-z", "--full-tree", base_sha
    )
    blobs: dict[str, tuple[str, int]] = {}
    for raw in records.split(b"\0"):
        if not raw:
            continue
        header, separator, encoded = raw.partition(b"\t")
        if not separator:
            raise MissionCliError("repository manifest could not be read")
        fields = header.split()
        if len(fields) != 4:
            raise MissionCliError("repository manifest could not be read")
        mode, kind, object_id, size = (
            item.decode("ascii", "replace") for item in fields
        )
        if kind != "blob" or mode not in {"100644", "100755"}:
            continue
        blobs[os.fsdecode(encoded)] = (object_id, int(size))
    return blobs


def _planning_repository_context(
    repository: Path, policy: ProjectPolicy
) -> tuple[tuple[str, ...], tuple[PlanningExcerpt, ...]]:
    """Manifest and excerpts read out of ``policy.base_sha``, never off the disk.

    Workers execute against the committed ``base_sha``; a planner fed live
    worktree bytes plans against content nobody will run, and uncommitted work
    would leave the machine inside the prompt. Reading Git objects also settles
    the symlink question outright — no path under ``repository`` is opened, so an
    intermediate directory symlink has nothing left to redirect.
    """
    drift = _planning_source_drift(repository, policy.base_sha)
    if drift:
        shown = ", ".join(drift[:8])
        extra = f" (+{len(drift) - 8} more)" if len(drift) > 8 else ""
        raise MissionCliError(
            f"planning source drift: {shown}{extra} differ from the bound commit "
            f"{policy.base_sha[:12]}; commit or stash them before planning"
        )
    blobs = _committed_blobs(repository, policy.base_sha)
    allowed = tuple(
        path
        for path in sorted(blobs)
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
        object_id, size = blobs[relative]
        if size > min(4_096, remaining):
            continue
        content = _git_read(repository, "cat-file", "blob", object_id)
        if len(content) != size or b"\0" in content:
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
    executable = _git_executable()
    environment = _git_environment()
    if staging.exists() or staging.is_symlink():
        metadata = staging.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise MissionCliError("Gemini result repository staging is unsafe")
        shutil.rmtree(staging)
    if not repository.exists():
        result = subprocess.run(
            (
                executable,
                "clone",
                "--no-local",
                "--no-checkout",
                "--quiet",
                str(source),
                str(staging),
            ),
            env=environment,
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
            (executable, "checkout", "--detach", "--quiet", base_sha),
            cwd=staging,
            env=environment,
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
            (executable, "remote"),
            cwd=staging,
            env=environment,
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
                (executable, "remote", "remove", remote),
                cwd=staging,
                env=environment,
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
            (executable, "remote"),
            cwd=staging,
            env=environment,
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
        (executable, "remote"),
        cwd=repository,
        env=environment,
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
            (executable, "rev-parse", "--verify", "HEAD"),
            cwd=repository,
            env=environment,
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


def _prior_failure(store, evidence, mission_id: str, dispatch) -> PriorFailure | None:
    """What the previous attempt learned, or None on the first attempt.

    Read from committed attempt evidence, not from memory: the retry is a fresh
    lease under a strictly higher fence and may be served by a different worker.
    Anything unresolvable or tampered with yields None, so a missing diagnostic
    degrades to the old blind retry rather than failing the mission.
    """
    if getattr(dispatch, "attempt_number", 1) <= 1:
        return None
    try:
        snapshot = store.snapshot(mission_id)
    except Exception:
        return None
    prior = next(
        (
            item
            for item in snapshot.attempts
            if item.task_id == dispatch.task_id
            and item.attempt_number == dispatch.attempt_number - 1
        ),
        None,
    )
    if prior is None or not prior.result_code:
        return None
    if prior.result_code == RuntimeErrorCode.PROVIDER_INTERRUPTED.value:
        interruption_refs = tuple(
            item
            for item in prior.evidence_refs
            if item.kind == WORKER_PROVIDER_INTERRUPTION_KIND
        )
        if len(interruption_refs) != 1:
            return None
        interruption_ref = interruption_refs[0]
        raw = evidence.resolve(interruption_ref.kind, interruption_ref.id)
        if raw is None or sha256_hex(raw) != interruption_ref.sha256:
            return None
        try:
            interruption = WorkerProviderInterruption.model_validate_json(raw)
        except ValueError:
            return None
        if (
            canonical_json_bytes(interruption.model_dump(mode="json")) != raw
            or (
                interruption.mission_id,
                interruption.task_id,
                interruption.attempt_id,
                interruption.lease_id,
                interruption.fencing_token,
            )
            != (
                prior.mission_id,
                prior.task_id,
                prior.attempt_id,
                prior.lease_id,
                prior.fencing_token,
            )
            or (
                interruption.sdk_invocation_id is not None
                and interruption.sdk_invocation_id != prior.invocation_id
            )
        ):
            return None
        return PriorFailure(
            attempt_id=prior.attempt_id,
            attempt_number=prior.attempt_number,
            fencing_token=prior.fencing_token,
            result_code=prior.result_code,
            failure_class="provider_interrupted",
            summary=(
                "The prior model child was interrupted "
                + (
                    "after provider transport entry. "
                    if interruption.provider_dispatch_state == "transport_acknowledged"
                    else "before provider transport entry could be confirmed. "
                )
                + "Repository effect is known absent; provider and billing outcomes "
                "remain unknown."
            ),
            receipt_sha256=interruption_ref.sha256,
            failure_signature=canonical_json_sha256(
                (prior.result_code, interruption.request_sha256)
            ),
        )
    diagnostic_ref = next(
        (item for item in prior.evidence_refs if item.kind == CHECK_DIAGNOSTIC_KIND),
        None,
    )
    receipt_ref = next(
        (item for item in prior.evidence_refs if item.kind == "test-receipt"), None
    )
    if diagnostic_ref is None or receipt_ref is None:
        return None
    raw = evidence.resolve(diagnostic_ref.kind, diagnostic_ref.id)
    if raw is None or sha256_hex(raw) != diagnostic_ref.sha256:
        return None
    try:
        diagnostic = CheckDiagnostic.model_validate_json(raw)
        return PriorFailure(
            attempt_id=prior.attempt_id,
            attempt_number=prior.attempt_number,
            fencing_token=prior.fencing_token,
            result_code=prior.result_code,
            failure_class=diagnostic.failure_class,
            failed_check_names=diagnostic.failed_check_names,
            summary=diagnostic.summary,
            receipt_sha256=receipt_ref.sha256,
            failure_signature=diagnostic.signature(),
        )
    except ValueError:
        return None


def _diagnostic_aware_assignment(
    assignments: dict[str, RuntimeAssignment], store, evidence, mission_id: str
) -> Callable[[object], RuntimeAssignment]:
    """Resolve a dispatch to its assignment, carrying the prior failure on a retry."""

    def resolve(dispatch) -> RuntimeAssignment:
        assignment = assignments[dispatch.task_id]
        failure = _prior_failure(store, evidence, mission_id, dispatch)
        if failure is None:
            return assignment
        return assignment.model_copy(update={"prior_failure": failure})

    return resolve


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
                (_git_executable(), *template.argv[1:]),
                cwd=workspace,
                env=_git_environment(),
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
            detail = (
                f"The owned check process for {assignment.task_id} exited 97 under "
                f"the deterministic injected fault {label}. No test assertion "
                "failed; the check process itself was made to fail."
            )
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
                # The retry learns from an injected fault exactly as it learns
                # from a real one, and the summary says plainly which it was.
                diagnostic=summarize_check_failure(
                    detail,
                    exit_code=97,
                    timed_out=False,
                    output_truncated=False,
                    cleanup_complete=True,
                    output_sha256=sha256_hex(label.encode()),
                    output_byte_count=len(label.encode()),
                ),
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


def _select_check_executor(requested: str | None = None) -> str:
    """Fail closed on anything but the two reviewed check executors.

    The host-sandbox choice is also checked for platform support here, before
    any worker runs, so an unsupported host never spends a model call on an
    attempt whose check can only fail.
    """

    requested = _requested_check_executor() if requested is None else requested
    if requested not in _CHECK_EXECUTOR_CHOICES:
        raise MissionCliError(_CHECK_EXECUTOR_ERROR)
    if requested == "host-sandbox" and not _host_sandbox_supported():
        raise MissionCliError(_HOST_SANDBOX_UNSUPPORTED)
    return requested


def _mission_check_executor(mission_id: str) -> str:
    runtime = _mission_runtime(mission_id)
    path = runtime / "start-request.json"
    if not path.exists() and not path.is_symlink():
        return _select_check_executor()
    bound = _private_start_binding(runtime).get("check_executor")
    if bound is None:  # Legacy start requests selected from their current environment.
        return _select_check_executor()
    if not isinstance(bound, str):
        raise MissionCliError("mission check executor binding is invalid")
    return _select_check_executor(bound)


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


def _provider_interruption_references(snapshot) -> list[dict[str, object]]:
    """Evidence-bound provider interruption references of WORK attempts only."""

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
        if reference.kind == WORKER_PROVIDER_INTERRUPTION_KIND
    ]


def _replayed_provider_interruptions(
    snapshot, evidence: SQLiteAttemptEvidenceStore
) -> tuple[list[dict[str, object]], list[str], list[str], list[str]]:
    """Resolve interruption proof and state provider/billing unknowns explicitly."""

    kinds = _work_task_kinds(snapshot)
    interruptions: list[dict[str, object]] = []
    resolution_unknowns: list[str] = []
    provider_unknowns: list[str] = []
    billing_unknowns: list[str] = []
    for attempt in snapshot.attempts:
        if kinds.get(attempt.task_id) != TaskKind.WORK:
            continue
        has_interruption = any(
            reference.kind == WORKER_PROVIDER_INTERRUPTION_KIND
            for reference in attempt.evidence_refs
        )
        if (
            attempt.result_code == RuntimeErrorCode.PROVIDER_INTERRUPTED.value
            or has_interruption
        ):
            provider_unknowns.append(
                f"provider outcome for interrupted attempt {attempt.attempt_id} is unknown"
            )
            billing_unknowns.append(
                f"billing outcome for interrupted attempt {attempt.attempt_id} is unknown"
            )
        for reference in attempt.evidence_refs:
            if reference.kind != WORKER_PROVIDER_INTERRUPTION_KIND:
                continue
            label = (
                f"worker provider interruption {reference.id} for attempt "
                f"{attempt.attempt_id}"
            )
            content = evidence.resolve(reference.kind, reference.id)
            if (
                not isinstance(content, bytes)
                or sha256_hex(content) != reference.sha256
            ):
                resolution_unknowns.append(f"{label} is unresolvable")
                continue
            try:
                interruption = WorkerProviderInterruption.model_validate_json(content)
            except ValueError:
                resolution_unknowns.append(f"{label} is invalid")
                continue
            if canonical_json_bytes(interruption.model_dump(mode="json")) != content:
                resolution_unknowns.append(f"{label} is not canonical")
                continue
            if (
                interruption.mission_id,
                interruption.task_id,
                interruption.attempt_id,
                interruption.lease_id,
                interruption.fencing_token,
            ) != (
                attempt.mission_id,
                attempt.task_id,
                attempt.attempt_id,
                attempt.lease_id,
                attempt.fencing_token,
            ) or (
                interruption.sdk_invocation_id is not None
                and interruption.sdk_invocation_id != attempt.invocation_id
            ):
                resolution_unknowns.append(f"{label} names another dispatch")
                continue
            interruptions.append(interruption.model_dump(mode="json"))
    return interruptions, resolution_unknowns, provider_unknowns, billing_unknowns


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
            if (
                not isinstance(content, bytes)
                or sha256_hex(content) != reference.sha256
            ):
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
    events = _mission_events(store, mission_id, snapshot.head.event_count)
    try:
        decision = plan_policy_decision(events, snapshot.plan.revision)
    except ValueError as error:
        raise MissionCliError("committed policy decision is invalid") from error
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
    (
        provider_interruptions,
        provider_interruption_unknowns,
        provider_outcome_unknowns,
        billing_outcome_unknowns,
    ) = _replayed_provider_interruptions(snapshot, evidence)
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
        "provider_interruptions": provider_interruptions,
        "provider_interruption_references": _provider_interruption_references(snapshot),
        "provider_interruption_unknowns": provider_interruption_unknowns,
        "provider_outcome_unknowns": provider_outcome_unknowns,
        "billing_outcome_unknowns": billing_outcome_unknowns,
        "parallel_overlap": overlap.model_dump(mode="json"),
        "parallel_overlap_observed": overlap.observed,
        "provider_call_overlap_observed": overlap.provider_call_observed,
        "review_required": (
            snapshot.mission.status == MissionStatus.AWAITING_RESULT
            and (
                decision is None
                or decision.finalization_mode == FinalizationMode.REVIEW_REQUIRED
            )
        ),
        **(
            {}
            if decision is None
            else {
                "requested_authorization_mode": decision.requested_mode.value,
                "effective_authorization_mode": decision.effective_mode.value,
                "finalization_mode": decision.finalization_mode.value,
                "policy_decision_sha256": decision.decision_sha256,
            }
        ),
        "checkout_mutated": False,
        **({"simulation_truth": demo_truth} if demo_truth else {}),
        **({"result_replayed": True} if replayed else {}),
    }


@contextmanager
def _mission_execution_lock(mission_id: str) -> Iterator[None]:
    try:
        import fcntl
    except ImportError as error:
        raise MissionCliError("mission execution locking is unavailable") from error

    runtime = _mission_runtime(mission_id)
    path = runtime / "execution.lock"
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise MissionCliError("mission execution lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _supervisor_backed(runtime: Path) -> bool:
    request = runtime / "supervisor-request.json"
    if request.is_symlink():
        raise MissionCliError("supervisor request binding is unsafe")
    return request.is_file()


def _ensure_detached_supervisor(mission_id: str):
    from ..orchestration.supervisor import SupervisorError, ensure_supervisor

    try:
        return ensure_supervisor(mission_id, recover_failed=True)
    except SupervisorError as error:
        raise MissionCliError("detached supervisor could not be signalled") from error


def _execute_adk_mission(
    *,
    store,
    mission_id: str,
    registry: WorkerRegistry | None = None,
    check_runner=None,
    resource_sampler: Callable[[str], Sequence[ResourcePoint]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    with _mission_execution_lock(mission_id):
        return _execute_adk_mission_owned(
            store=store,
            mission_id=mission_id,
            registry=registry,
            check_runner=check_runner,
            resource_sampler=resource_sampler,
            should_cancel=should_cancel,
        )


def _execute_adk_mission_owned(
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
    check_executor = _mission_check_executor(mission_id)
    source, policy, requested_workers = _gemini_source(mission_id, snapshot)
    runtime = _mission_runtime(mission_id)
    if should_cancel is None:

        def durable_cancellation_requested() -> bool:
            return (
                _read_cancellation_request(runtime) is not None
                or store.snapshot(mission_id).mission.status == MissionStatus.CANCELLED
            )

        should_cancel = durable_cancellation_requested
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
        elif templates and all(
            item.cwd is None
            and (item.template_id, tuple(item.argv)) in SANDBOX_CHECK_TEMPLATES
            for item in templates
        ):
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
        assignment=_diagnostic_aware_assignment(
            assignments, store, evidence, mission_id
        ),
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
        if _read_cancellation_request(runtime) is not None:
            _reconcile_cancellation_request(mission_id)
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
    check_executor = _mission_check_executor(args.mission_id)
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
    elif templates and all(
        item.cwd is None
        and (item.template_id, tuple(item.argv)) in SANDBOX_CHECK_TEMPLATES
        for item in templates
    ):
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
    if _supervisor_backed(runtime):
        _ensure_detached_supervisor(mission_id)
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
    gemini_proposal: PlanProposal | None = None,
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
            existing = _ensure_gemini_policy_decision(
                args,
                command_id=command_id,
                policy=policy,
                store=store,
                snapshot=existing,
            )
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
                if _supervisor_backed(runtime):
                    result = _existing_gemini_proposal_value(store, existing)
                else:
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
            if _supervisor_backed(runtime):
                result = _scripted_proposal_value(store, mission_id, replayed=True)
            else:
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
                execute=not _supervisor_backed(runtime),
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
            proposal=gemini_proposal,
        )
    else:
        scenario = load_scenario(DEFAULT_SCENARIO_PATH)
        if args.success_criteria and tuple(sorted(set(args.success_criteria))) != (
            scenario.success_criteria
        ):
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
                execute=not _supervisor_backed(runtime),
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
        with serialized_connection(
            lambda: sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        ) as connection:
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
        with serialized_connection(
            lambda: sqlite3.connect(f"file:{store.path}?mode=ro", uri=True)
        ) as connection:
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
    try:
        raw, bundle = _read_bundle(_persisted_bundle_path(args.bundle_id))
    except _PersistedBundleMissing:
        raw, bundle, _runtime = _prepare_pending_bundle(args.mission_id)
    if bundle.bundle_id != args.bundle_id:
        raise MissionCliError("bundle decision does not match the current bundle")
    (
        store,
        snapshot,
        _runtime,
        _repository,
        _evidence,
        candidate,
        _verification,
    ) = _scripted_bindings(args.mission_id)
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


_CANCELLATION_REQUEST = "cancellation-request.json"
_CANCELLATION_COMPLETE = "cancellation-complete.json"
_CANCELLATION_CONFLICT = "cancellation-conflict.json"


class _CancellationAuthorityConflict(ProcessControlError):
    pass


def _read_cancellation_request(runtime: Path) -> dict[str, object] | None:
    path = runtime / _CANCELLATION_REQUEST
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_size > 16_384
    ):
        raise ProcessControlError("cancellation request journal is unsafe")
    try:
        content = path.read_bytes()
        raw = json.loads(content)
        if (
            set(raw)
            != {
                "command_id",
                "expected_head",
                "mission_id",
                "operator_label",
                "rationale",
                "recorded_at",
                "schema_version",
                "truth_kind",
            }
            or canonical_json_bytes(raw) != content
        ):
            raise ValueError
        if raw["schema_version"] != 1:
            raise ValueError
        MissionHead.model_validate(raw["expected_head"])
        TruthKind(raw["truth_kind"])
        when = datetime.fromisoformat(raw["recorded_at"])
        if when.tzinfo is None:
            raise ValueError
        if not all(
            isinstance(raw[key], str)
            for key in ("command_id", "mission_id", "operator_label")
        ) or not (raw["rationale"] is None or isinstance(raw["rationale"], str)):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as error:
        raise ProcessControlError("cancellation request journal is invalid") from error
    return raw


def _ensure_cancellation_request(
    runtime: Path,
    *,
    mission_id: str,
    command_id: str,
    expected_head: MissionHead,
    operator_label: str,
    rationale: str | None,
    truth_kind: TruthKind,
    recorded_at: datetime,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "mission_id": mission_id,
        "command_id": command_id,
        "expected_head": expected_head.model_dump(mode="json"),
        "operator_label": operator_label,
        "rationale": rationale,
        "truth_kind": truth_kind.value,
        "recorded_at": recorded_at.isoformat(),
    }
    stable_keys = set(value) - {"recorded_at"}
    with process_registration_lock(runtime):
        existing = _read_cancellation_request(runtime)
        if existing is not None:
            if any(existing[key] != value[key] for key in stable_keys):
                raise ProcessControlError("cancellation request journal changed")
            return existing
        try:
            _atomic_create(
                runtime / _CANCELLATION_REQUEST,
                canonical_json_bytes(value),
            )
        except MissionCliError as error:
            existing = _read_cancellation_request(runtime)
            if existing is None or any(
                existing[key] != value[key] for key in stable_keys
            ):
                raise ProcessControlError(
                    "cancellation request could not be journaled"
                ) from error
            _durably_confirm_cancellation_request(runtime)
            return existing
    return value


def _move_cancellation_request(runtime: Path, target: str) -> None:
    request = runtime / _CANCELLATION_REQUEST
    if request.exists() or request.is_symlink():
        os.replace(request, runtime / target)
    descriptor = os.open(runtime, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _complete_cancellation_request(runtime: Path) -> None:
    _move_cancellation_request(runtime, _CANCELLATION_COMPLETE)


def _conflict_cancellation_request(runtime: Path) -> None:
    _move_cancellation_request(runtime, _CANCELLATION_CONFLICT)


def _durably_confirm_cancellation_request(runtime: Path) -> None:
    path = runtime / _CANCELLATION_REQUEST
    descriptor = -1
    directory = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        visible = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) & 0o077
            or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
        ):
            raise OSError("cancellation request identity changed")
        os.fsync(descriptor)
        directory = os.open(
            runtime,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        os.fsync(directory)
    except OSError as error:
        raise ProcessControlError(
            "cancellation request durability is unconfirmed"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory >= 0:
            os.close(directory)


def _validate_cancellation_head_advance(
    store,
    *,
    previous: MissionHead,
    snapshot,
    command_id: str,
) -> None:
    current = snapshot.head
    if current == previous:
        return
    count = current.seq - previous.seq
    if (
        current.mission_id != previous.mission_id
        or not 1 <= count <= 4_096
        or current.event_count - previous.event_count != count
    ):
        raise ProcessControlError("cancellation authority advance is invalid")
    attempts = {item.attempt_id: item for item in snapshot.attempts}
    after = previous.seq
    prior_sha256 = previous.event_sha256
    cancel_transaction = False
    while after < current.seq:
        events = store.tail(current.mission_id, after, min(256, current.seq - after))
        if not events:
            raise ProcessControlError("cancellation authority history is incomplete")
        for event in events:
            if (
                event.mission_id != current.mission_id
                or event.seq != after + 1
                or event.previous_event_sha256 != prior_sha256
            ):
                raise ProcessControlError(
                    "cancellation authority history is inconsistent"
                )
            attempt = attempts.get(event.payload.get("attempt_id"))
            heartbeat = not cancel_transaction and event.event_type == (
                MissionEventType.TASK_HEARTBEAT
            ) and (
                attempt is not None
                and (
                    event.payload.get("task_id"),
                    event.payload.get("worker_id"),
                    event.payload.get("lease_id"),
                    event.payload.get("fencing_token"),
                )
                == (
                    attempt.task_id,
                    attempt.worker_id,
                    attempt.lease_id,
                    attempt.fencing_token,
                )
            )
            committed_cancel = (
                not cancel_transaction
                and snapshot.mission.status == MissionStatus.CANCELLED
                and event.event_type == MissionEventType.OPERATOR_CANCELLED
                and event.command_id == command_id
            )
            cancelled_task = (
                cancel_transaction
                and event.event_type == MissionEventType.TASK_CANCELLED
                and event.command_id == command_id
            )
            if not heartbeat and not committed_cancel and not cancelled_task:
                raise _CancellationAuthorityConflict(
                    "mission authority changed after cancellation was requested"
                )
            cancel_transaction = cancel_transaction or committed_cancel
            after = event.seq
            prior_sha256 = event.event_sha256
    if prior_sha256 != current.event_sha256 or (
        snapshot.mission.status == MissionStatus.CANCELLED
        and not cancel_transaction
    ):
        raise ProcessControlError("cancellation authority head is inconsistent")


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
    _retry_cleanup_race: bool = True,
) -> MissionHead:
    snapshot = store.snapshot(mission_id)
    mission_runtime = _mission_runtime(mission_id)
    pending = _read_cancellation_request(mission_runtime)
    if pending is None and snapshot.mission.status == MissionStatus.CANCELLED:
        return snapshot.head
    bound_head = (
        MissionHead.model_validate(pending["expected_head"])
        if pending is not None
        else (expected_head or snapshot.head)
    )
    if expected_head is not None and expected_head != snapshot.head and pending is None:
        from ..orchestration.sqlite_mission_store import MissionConflict

        raise MissionConflict("mission head changed")
    pending = _ensure_cancellation_request(
        mission_runtime,
        mission_id=mission_id,
        command_id=command_id,
        expected_head=bound_head,
        operator_label=operator_label,
        rationale=rationale,
        truth_kind=truth_kind,
        recorded_at=recorded_at,
    )
    recorded_at = datetime.fromisoformat(str(pending["recorded_at"]))
    worker_ids = tuple(
        sorted(
            {
                attempt.worker_id
                for attempt in snapshot.attempts
                if attempt.state == AttemptState.RUNNING
            }
        )
    )
    active = store.recover_dispatches(
        mission_id, worker_ids, recorded_at=recorded_at, include_expired=True
    )
    registry = OwnedProcessRegistry(mission_runtime)
    try:
        _validate_cancellation_head_advance(
            store,
            previous=bound_head,
            snapshot=snapshot,
            command_id=command_id,
        )
    except _CancellationAuthorityConflict:
        registry.remove_dead_records_for_mission(mission_id)
        _conflict_cancellation_request(mission_runtime)
        raise
    prepared = registry.prepare_cancel(active)
    durable = registry.records_for_mission(mission_id)
    targets = tuple(
        {(item.attempt_id, item.pid): item for item in (*prepared, *durable)}.values()
    )
    terminated = {
        (owned.attempt_id, owned.pid): registry.terminate_owned(
            owned, retain_record=True
        )
        for owned in targets
    }

    docker_reconciled: set[str] = set()
    policy_templates = getattr(snapshot.policy, "command_templates", ())
    sandbox_template_ids = {item[0] for item in SANDBOX_CHECK_TEMPLATES}
    docker_checks = any(
        item.cwd is None
        and (item.template_id, tuple(item.argv)) in SANDBOX_CHECK_TEMPLATES
        for item in policy_templates
    ) or any(
        template_id in sandbox_template_ids
        for template_id in getattr(snapshot.policy, "command_template_ids", ())
    )
    if docker_checks and _mission_check_executor(mission_id) == "docker":
        docker = DockerExecutor()
        try:
            for dispatch in active:
                if docker.reconcile_owned(dispatch.attempt_id):
                    docker_reconciled.add(dispatch.attempt_id)
        except Exception as error:
            raise ProcessControlError(
                "owned check container could not be reconciled"
            ) from error

    receipt_attempts = {
        dispatch.attempt_id
        for dispatch in active
        if any(
            (
                root
                / "worker-receipts"
                / (sha256_hex(dispatch.attempt_id.encode()) + ".json")
            ).is_file()
            for root in (
                mission_runtime / "adk-runtime",
                mission_runtime / "outbound-executor",
            )
        )
    }
    reconciliation_attempts = {
        *(item.attempt_id for item in targets),
        *docker_reconciled,
        *receipt_attempts,
    }
    evidence = _mission_evidence(store, mission_id) if reconciliation_attempts else None
    attempts = {item.attempt_id: item for item in snapshot.attempts}
    dispatches = {item.attempt_id: item for item in active}
    runtime_roots: dict[str, Path] = {}
    runs = {}
    targets_by_attempt = {
        attempt_id: tuple(item for item in targets if item.attempt_id == attempt_id)
        for attempt_id in reconciliation_attempts
    }
    for attempt_id, owned_targets in sorted(targets_by_attempt.items()):
        attempt = attempts.get(attempt_id)
        if attempt is None:
            raise ProcessControlError("owned process names no mission attempt")
        receipt_name = sha256_hex(attempt_id.encode()) + ".json"
        available = tuple(
            root
            for root in (
                mission_runtime / "adk-runtime",
                mission_runtime / "outbound-executor",
            )
            if (root / "worker-receipts").is_dir()
        )
        marked = tuple(
            root
            for root in available
            if (
                (root / "worker-receipts" / receipt_name).is_file()
                or (
                    root / "worker-workspaces" / sha256_hex(attempt_id.encode())
                ).is_dir()
            )
        )
        candidates = marked or available
        if len(candidates) > 1:
            raise ProcessControlError("owned worker runtime is ambiguous")
        if not candidates:
            continue
        runtime_roots[attempt_id] = candidates[0]
        dispatch = dispatches.get(attempt_id)
        if dispatch is None and attempt.state in {
            AttemptState.COMMITTED,
            AttemptState.FAILED,
            AttemptState.CANCELLED,
        }:
            dispatch, _ = WorkerRuntime.dispatch_from_snapshot(snapshot, attempt_id)
        if dispatch is not None:
            assert evidence is not None
            barrier = registry.confirm_model_dispatch_barrier(dispatch)
            model_targets = tuple(
                item
                for item in owned_targets
                if item.model_request_sha256 is not None
                or (
                    barrier is not None
                    and (
                        item.pid,
                        item.pgid,
                        item.started_at,
                        item.birth_token,
                        item.executable,
                    )
                    == (
                        barrier.pid,
                        barrier.pgid,
                        barrier.started_at,
                        barrier.birth_token,
                        barrier.executable,
                    )
                )
            )
            if len(model_targets) > 1:
                raise ProcessControlError("model worker ownership is ambiguous")
            model_owned = model_targets[0] if model_targets else None
            runs[attempt_id] = WorkerRuntime.reconcile_cancellation(
                dispatch,
                runtime=candidates[0],
                evidence=evidence,
                interruption=(
                    None
                    if model_owned is None
                    else WorkerRuntime.cancellation_interruption(
                        dispatch,
                        model_owned,
                        barrier,
                        requested_model=LIVE_GEMINI_MODEL,
                        signal_number=terminated[
                            (model_owned.attempt_id, model_owned.pid)
                        ],
                    )
                ),
                recorded_at=recorded_at,
            )

    worker_runtime_attempts = {
        dispatch.attempt_id
        for dispatch in active
        if any(
            (root / "worker-receipts").is_dir()
            for root in (
                mission_runtime / "adk-runtime",
                mission_runtime / "outbound-executor",
            )
        )
    }
    missing = worker_runtime_attempts - set(runs)
    if missing:
        raise ProcessControlError(
            "active worker cancellation has not reached a durable receipt boundary"
        )

    commit_snapshot = store.snapshot(mission_id)
    try:
        _validate_cancellation_head_advance(
            store,
            previous=snapshot.head,
            snapshot=commit_snapshot,
            command_id=command_id,
        )
    except _CancellationAuthorityConflict:
        registry.remove_dead_records_for_mission(mission_id)
        _conflict_cancellation_request(mission_runtime)
        raise
    commit_records = frozenset(registry.records_for_mission(mission_id))
    if commit_snapshot.head != snapshot.head or commit_records != frozenset(targets):
        if not _retry_cleanup_race:
            raise ProcessControlError(
                "mission runtime continued changing during cancellation"
            )
        return _cancel_with_owned_cleanup(
            store=store,
            mission_id=mission_id,
            command_id=command_id,
            expected_head=bound_head,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
            _retry_cleanup_race=False,
        )
    commit_attempts = {item.attempt_id: item for item in commit_snapshot.attempts}
    head = commit_snapshot.head
    if commit_snapshot.mission.status != MissionStatus.CANCELLED:
        head = store.cancel(
            mission_id,
            command_id,
            expected_head=commit_snapshot.head,
            operator_label=operator_label,
            rationale=rationale,
            truth_kind=truth_kind,
            recorded_at=recorded_at,
            cancelled_attempt_results=tuple(
                (attempt_id, run.result)
                for attempt_id, run in sorted(runs.items())
                if commit_attempts[attempt_id].state == AttemptState.RUNNING
            ),
        )

    committed = store.snapshot(mission_id)
    committed_attempts = {item.attempt_id: item for item in committed.attempts}
    for owned in targets:
        attempt = committed_attempts.get(owned.attempt_id)
        if (
            committed.mission.status != MissionStatus.CANCELLED
            or attempt is None
            or attempt.state
            not in {
                AttemptState.COMMITTED,
                AttemptState.FAILED,
                AttemptState.CANCELLED,
            }
        ):
            raise ProcessControlError("owned worker cancellation is not committed")
        runtime_root = runtime_roots.get(owned.attempt_id)
        if runtime_root is not None:
            assert evidence is not None
            receipt = WorkerRuntime.cancellation_receipt_for_attempt(
                runtime=runtime_root,
                evidence=evidence,
                attempt=attempt,
            )
            if receipt is None or not WorkerRuntime.terminal_receipt_is_committed(
                receipt, attempt
            ):
                raise ProcessControlError(
                    "owned worker cancellation receipt is not committed"
                )
        registry.remove_exact(owned)
    _complete_cancellation_request(mission_runtime)
    return head


def _reconcile_cancellation_request(mission_id: str) -> bool:
    """Finish one durable operator cancellation after a CLI/runtime crash."""

    runtime = _mission_runtime(mission_id)
    request = _read_cancellation_request(runtime)
    if request is None:
        return False
    store = _store_for_mission(mission_id)
    try:
        _cancel_with_owned_cleanup(
            store=store,
            mission_id=mission_id,
            command_id=str(request["command_id"]),
            expected_head=MissionHead.model_validate(request["expected_head"]),
            operator_label=str(request["operator_label"]),
            rationale=(
                None if request["rationale"] is None else str(request["rationale"])
            ),
            truth_kind=TruthKind(str(request["truth_kind"])),
            recorded_at=datetime.fromisoformat(str(request["recorded_at"])),
        )
        return True
    finally:
        store.close()


def _reconcile_cancellation_requests(
    *, on_failure: Callable[[str], object] | None = None
) -> int:
    """Recover bounded direct and supervised cancellation journals at startup."""

    recovered = 0
    seen = 0
    for parent in (_state_root() / "missions", _state_root() / "scripted"):
        if not parent.exists():
            continue
        for runtime in sorted(parent.iterdir()):
            seen += 1
            if seen > 4_096:
                raise ProcessControlError(
                    "cancellation request registry exceeds its safe limit"
                )
            mission_id: str | None = None
            try:
                if not (runtime / _CANCELLATION_REQUEST).exists():
                    continue
                request = _read_cancellation_request(runtime)
                assert request is not None
                mission_id = str(request["mission_id"])
                if runtime != _mission_runtime(mission_id):
                    raise ProcessControlError(
                        "cancellation request journal is in the wrong runtime"
                    )
                recovered += int(_reconcile_cancellation_request(mission_id))
            except Exception:
                # One unavailable exact owner must leave its request durable,
                # but must not prevent unrelated missions from recovering.
                if on_failure is not None and mission_id is not None:
                    on_failure(mission_id)
    return recovered


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
            except (ProcessControlError, RuntimeFailure) as error:
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
        if action == "resume" and _supervisor_backed(_mission_runtime(args.mission_id)):
            _ensure_detached_supervisor(args.mission_id)
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
        # Approve the graph, not the number. The digest the store holds is
        # always bound; if the operator names one, it must be the same one, so
        # a plan that moved between reading the diff and approving it cannot
        # be approved by accident.
        plan_sha256 = canonical_json_sha256(snapshot.plan.model_dump(mode="json"))
        expected = getattr(args, "plan_sha256", None)
        if expected is not None and expected != plan_sha256:
            raise MissionCliError(
                "plan approval digest does not match the committed revision"
            )
        command_id = args.command_id or _command_id(
            action,
            args.mission_id,
            args.revision,
            args.operator_label,
            args.rationale,
        )
        if snapshot.mission.creation_source == "scripted_fixture":
            if snapshot.plan.revision != 1:
                # scripted-local replays a recorded fixture keyed to the exact
                # fixture plan. Approving an edited revision here would move the
                # mission to RUNNING and only then discover that no scripted
                # worker exists for it, leaving a mission nobody can finish.
                raise MissionCliError(
                    "scripted-local replays a recorded fixture and cannot execute an "
                    "edited plan; propose the mission with --driver gemini-adk to run "
                    "a revised plan"
                )
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
                    expected_plan_sha256=plan_sha256,
                )
            runtime = _mission_runtime(args.mission_id)
            if _supervisor_backed(runtime):
                _ensure_detached_supervisor(args.mission_id)
                return _scripted_proposal_value(store, args.mission_id, replayed=True)
            run = execute_scripted_mission(
                store=store,
                runtime=runtime,
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
                    expected_plan_sha256=plan_sha256,
                )
            runtime = _mission_runtime(args.mission_id)
            if _supervisor_backed(runtime):
                _ensure_detached_supervisor(args.mission_id)
                return _existing_gemini_proposal_value(
                    store, store.snapshot(args.mission_id)
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
            expected_plan_sha256=plan_sha256,
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
        if args.goal in _PLAN_ACTIONS:
            return _plan_action(args)
        if (
            args.plan_id is not None
            or args.previous_revision is not None
            or args.target_revision is not None
        ):
            raise MissionCliError("multi-word plan goals must be quoted")
        if args.repo is None:
            raise MissionCliError("plan requires --repo")
        if (
            args.detail
            or args.output is not None
            or args.revision is not None
            or args.plan_sha256 is not None
        ):
            raise MissionCliError("proposing a plan does not accept action options")
        return 0, _start(args)
    if args.command == "status":
        return 0, _status_value(args.mission_id)
    if args.command == "watch":
        args.mission_id = args.run_id
        if getattr(args, "follow", False):
            return _follow_mission(args.mission_id), None
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
        if getattr(args, "follow", False):
            return _follow_mission(args.mission_id), None
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


MISSION_PRICE_PER_TOKEN = GEMINI_3_5_FLASH_USD_PER_TOKEN

# Event types worth putting on the dashboard's one "Latest" line, newest first.
_LATEST_LINES: dict[str, str] = {
    MissionEventType.TASK_RETRIED.value: (
        "check failed → retry authorized with diagnostic"
    ),
    MissionEventType.TASK_FAILED.value: "task failed",
    MissionEventType.TASK_COMPLETED.value: "task accepted",
    MissionEventType.TASK_LEASED.value: "worker leased a task",
    MissionEventType.TASK_STARTED.value: "worker started",
    MissionEventType.PLAN_APPROVED.value: "plan approved",
    MissionEventType.MISSION_TRIGGERED.value: "trigger received",
    MissionEventType.FINAL_RESULT_BUNDLE_READY.value: (
        "final bundle recomputed and ready for review"
    ),
    MissionEventType.FINAL_CANDIDATE_APPROVED.value: "result approved",
}


def _mission_spend(store, evidence, mission_id: str) -> float | None:
    """Cost from evidence-bound provider receipts only; None means unknown."""
    try:
        snapshot = store.snapshot(mission_id)
    except Exception:
        return None
    receipts = []
    for attempt in snapshot.attempts:
        for reference in attempt.evidence_refs:
            if reference.kind != WORKER_PROVIDER_RECEIPT_KIND:
                continue
            raw = evidence.resolve(reference.kind, reference.id)
            if raw is None or sha256_hex(raw) != reference.sha256:
                continue
            try:
                receipts.append(WorkerProviderReceipt.model_validate_json(raw))
            except ValueError:
                continue
    return spend_from_receipts(receipts, price_per_token=MISSION_PRICE_PER_TOKEN)


def _latest_line(store, mission_id: str, head_seq: int) -> str | None:
    """The newest event a human would call news, as one short phrase."""
    if head_seq <= 0:
        return None
    try:
        events = store.tail(mission_id, max(0, head_seq - 32), 32)
    except Exception:
        return None
    for event in reversed(events):
        phrase = _LATEST_LINES.get(event.event_type.value)
        if phrase is not None:
            return phrase
    return None


def _follow_mission(mission_id: str) -> int:
    """Render the live dashboard until the mission is terminal. Ctrl-C is clean."""
    from rich.console import Console

    from .dashboard import follow as dashboard_follow

    store = _store_for_mission(mission_id)
    evidence = _mission_evidence(store, mission_id)
    projection = MissionProjection(store)
    console = Console()
    frame = dashboard_follow(
        projection,
        mission_id,
        console=console,
        spend=lambda _snapshot: _mission_spend(store, evidence, mission_id),
        latest=lambda snapshot: _latest_line(store, mission_id, snapshot.head.seq),
        clock=time.monotonic,
        sleeper=time.sleep,
    )
    return 0 if frame.status not in {"failed", "cancelled", "rejected"} else 1


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
            elif args.command == "plan" and args.goal == "diff":
                sys.stdout.write(_render_plan_diff(value))
            elif args.command == "plan" and args.goal in {"edit", "revise"}:
                sys.stdout.write(_render_plan_revised(value))
            elif args.command == "plan" and args.goal == "export":
                sys.stdout.write(_render_plan_export(value))
            elif args.command == "plan" and args.goal == "show":
                sys.stdout.write(
                    _render_plan_detail(value)
                    if args.detail
                    else _render_plan_table(value)
                )
            elif args.command == "why":
                sys.stdout.write(_render_why(value))
            elif (
                args.command == "plan"
                and args.goal not in _PLAN_ACTIONS
                and isinstance(value, dict)
                and value.get("mission_id")
            ):
                # A proposal prints the contract it just compiled, not an
                # identifier the user then has to go look up.
                sys.stdout.write(
                    _render_plan_table(_plan_show_value(str(value["mission_id"])))
                )
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
