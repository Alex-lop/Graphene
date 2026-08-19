from __future__ import annotations

import argparse
import asyncio
import importlib.util
import math
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import uvicorn

from ..hashing import canonical_json_bytes, sha256_hex
from ..models import TruthKind
from ..orchestration.evidence import SQLiteAttemptEvidenceStore
from ..orchestration.adk import AdkPlanner, PlannerError, PlanningRequest
from ..orchestration.local_result import (
    approve_result as approve_local_result,
    reject_result as reject_local_result,
    verify_local_result_receipt,
)
from ..orchestration.models import (
    CommandTemplate,
    Mission,
    MissionStatus,
    NetworkPolicy,
    ProjectPolicy,
    ResourceBudget,
    RetentionPolicy,
)
from ..orchestration.process_control import (
    OwnedProcessRegistry,
    ProcessControlError,
)
from ..orchestration.scripted import (
    DEFAULT_SCENARIO_PATH,
    ScriptedError,
    ScriptedMissionRun,
    execute_scripted_mission,
    load_scenario,
    propose_scripted_mission,
    scripted_plan_validation,
    scripted_result_artifacts,
    scripted_supported,
)


_MISSION_COMMANDS = (
    "approve-plan",
    "approve-result",
    "cancel",
    "decide-gate",
    "open",
    "pause",
    "reject-result",
    "replan",
    "replay",
    "resume",
    "retry",
    "start",
    "status",
    "watch",
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


def _sha256(value: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise argparse.ArgumentTypeError("candidate-sha must be lowercase SHA-256")
    return value


def _operator(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--operator-label", default="local-operator")
    parser.add_argument("--rationale")
    parser.add_argument("--command-id", type=_command_key)


def _command_key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", value):
        raise argparse.ArgumentTypeError(
            "command-id must be 16-128 letters, digits, underscores, or hyphens"
        )
    return value


def register_commands(commands: argparse._SubParsersAction) -> None:
    initialize = commands.add_parser("init", allow_abbrev=False)
    initialize.add_argument("--repo", required=True, type=Path)

    doctor = commands.add_parser("doctor", allow_abbrev=False)
    doctor.add_argument("--repo", type=Path, default=Path.cwd())

    mission = commands.add_parser("mission", allow_abbrev=False)
    actions = mission.add_subparsers(dest="mission_action", required=True)

    start = actions.add_parser("start", allow_abbrev=False)
    start.add_argument("--repo", required=True, type=Path)
    start.add_argument("--goal", required=True)
    start.add_argument(
        "--success-criterion",
        action="append",
        default=[],
        dest="success_criteria",
    )
    start.add_argument(
        "--driver",
        choices=("scripted-local", "adk-fake", "gemini-adk"),
        default="scripted-local",
    )
    start.add_argument("--auto-approve", action="store_true")
    start.add_argument("--command-id", type=_command_key)
    start.add_argument("--open", action="store_true", dest="open_viewer")

    for name in ("status", "open"):
        command = actions.add_parser(name, allow_abbrev=False)
        command.add_argument("mission_id")

    for name in ("pause", "resume"):
        command = actions.add_parser(name, allow_abbrev=False)
        command.add_argument("mission_id")
        _operator(command)

    watch = actions.add_parser("watch", allow_abbrev=False)
    watch.add_argument("mission_id")
    watch.add_argument("--after-seq", type=_nonnegative, default=0)
    watch.add_argument("--snapshot", action="store_true")

    cancel = actions.add_parser("cancel", allow_abbrev=False)
    cancel.add_argument("mission_id")
    cancel.add_argument("--confirm", required=True)
    _operator(cancel)

    retry = actions.add_parser("retry", allow_abbrev=False)
    retry.add_argument("mission_id")
    retry.add_argument("--task", required=True, dest="task_id")
    _operator(retry)

    replan = actions.add_parser("replan", allow_abbrev=False)
    replan.add_argument("mission_id")
    replan.add_argument("--reason", required=True)
    _operator(replan)

    approve_plan = actions.add_parser("approve-plan", allow_abbrev=False)
    approve_plan.add_argument("mission_id")
    approve_plan.add_argument("--revision", required=True, type=int)
    _operator(approve_plan)

    decide = actions.add_parser("decide-gate", allow_abbrev=False)
    decide.add_argument("mission_id")
    decide.add_argument("--gate", required=True, dest="gate_id")
    decide.add_argument("--decision", required=True)
    _operator(decide)

    for name in ("approve-result", "reject-result"):
        result = actions.add_parser(name, allow_abbrev=False)
        result.add_argument("mission_id")
        result.add_argument("--candidate-sha", required=True, type=_sha256)
        _operator(result)

    replay = actions.add_parser("replay", allow_abbrev=False)
    replay.add_argument("source", nargs="?", default="taskmaster")
    replay.add_argument("--speed", type=_positive, default=1.0)
    replay.add_argument("--no-open", action="store_true")
    replay.add_argument(
        "--exit-after-replay", action="store_true", help=argparse.SUPPRESS
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
    firestore_hint = bool(
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        and os.environ.get("GRAPHENE_FIRESTORE_DATABASE")
        and os.environ.get("GRAPHENE_FIRESTORE_NAMESPACE")
        and os.environ.get("GRAPHENE_MISSION_ID")
        and os.environ.get("GRAPHENE_MISSION_CONTROL_READ_TOKEN")
    )
    return {
        "status": "ok",
        "executables": {
            "git": shutil.which("git") is not None,
            "python": shutil.which("python") is not None,
            "sandbox-exec": sandbox,
        },
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
                "usable": False,
                "configured": gemini_configured,
                "credential_mode": gemini_mode,
                "proof": "credential hints only; credentials and connectivity not probed",
            },
            "firestore-cloud": {
                "usable": False,
                "hint_present": firestore_hint,
                "proof": "connectivity not probed",
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


def _store():
    try:
        from ..orchestration.store import SQLiteMissionStore
    except ImportError as error:
        raise MissionCliError("mission store is unavailable") from error
    return SQLiteMissionStore(_state_root() / "missions.sqlite3")


def _mission_runtime(mission_id: str) -> Path:
    return _state_root() / "scripted" / sha256_hex(mission_id.encode())[:32]


def _projection():
    from ..orchestration.projection import MissionProjection

    return MissionProjection(_store(), legacy_viewer_base=None)


def _status_value(mission_id: str) -> dict[str, object]:
    value = _projection().snapshot(mission_id)
    return value.model_dump(mode="json")


def _watch_value(args: argparse.Namespace) -> dict[str, object]:
    store = _store()
    events = store.tail(args.mission_id, args.after_seq, 256)
    next_after = events[-1].seq if events else args.after_seq
    return {
        "mission_id": args.mission_id,
        "after_seq": args.after_seq,
        "next_after_seq": next_after,
        "events": [item.model_dump(mode="json") for item in events],
        "snapshot": _status_value(args.mission_id) if args.snapshot else None,
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


def _serve(app, url: str, *, no_open: bool, keep_open: bool) -> int:
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
        while keep_open:
            time.sleep(60)
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if handoff is not None:
            handoff.unlink(missing_ok=True)


def _open_live(mission_id: str) -> int:
    from ..orchestration.mission_control import create_mission_control_app

    token = secrets.token_urlsafe(32)
    port = _free_port()
    app = create_mission_control_app(
        _projection(), mission_id, token, "COMMITTED MISSION PROJECTION"
    )
    return _serve(
        app,
        f"http://127.0.0.1:{port}/mission-control/{mission_id}#token={token}",
        no_open=False,
        keep_open=True,
    )


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
        policy_sha256,
    )
    mission_id = "mission_start_" + sha256_hex(command_id.encode())[:24]
    binding = {
        "auto_approve": args.auto_approve,
        "command_id": command_id,
        "driver": args.driver,
        "goal_sha256": sha256_hex(args.goal.encode()),
        "policy_base_sha": policy.base_sha,
        "policy_revision": policy.revision,
        "policy_sha256": policy_sha256,
        "repository_head": head,
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


def _truth_kind() -> TruthKind:
    return (
        TruthKind.HUMAN_ATTESTED
        if sys.stdin.isatty() and sys.stdout.isatty()
        else TruthKind.SERVER_DERIVED
    )


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
    session_id = "session_" + sha256_hex(f"{command_id}:session".encode())[:24]
    invocation_id = "invocation_" + sha256_hex(f"{command_id}:invocation".encode())[:24]
    try:
        proposal = asyncio.run(
            AdkPlanner.live().propose(
                policy,
                PlanningRequest(
                    mission_id=mission_id,
                    revision=1,
                    goal=args.goal,
                    success_criteria=criteria,
                    session_id=session_id,
                    invocation_id=invocation_id,
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
        unknowns=(
            "ADK plan execution is not proven in this release.",
            "The model-proposed plan awaits operator review.",
        ),
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
        "proof": "real Google ADK planner proposal; execution not proven",
        "plan_revision": 1,
        "review_required": True,
        "execution_available": False,
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
        "status": "proposed",
        "mission_id": snapshot.mission.mission_id,
        "driver": "gemini-adk",
        "proof": "committed real Google ADK planner proposal; execution not proven",
        "plan_revision": snapshot.plan.revision,
        "review_required": True,
        "execution_available": False,
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
    evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
    store.bind_artifact_resolver(evidence)
    candidate, verification = scripted_result_artifacts(store, evidence, mission_id)
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
    store.approve_plan(
        mission_id,
        _command_id("approve-start-plan", mission_id, command_id, simulated),
        expected_revision=1,
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


def _start(args: argparse.Namespace) -> dict[str, object]:
    if args.driver == "adk-fake":
        raise MissionCliError(
            "adk-fake planning is test-only and unavailable in the product CLI; "
            "no scripted fallback was used"
        )
    if args.driver == "gemini-adk" and args.auto_approve:
        raise MissionCliError(
            "gemini-adk can persist a proposal only; execution is NOT PROVEN"
        )
    command_id, mission_id, _repository, _head, policy, binding = _start_identity(args)
    runtime = _mission_runtime(mission_id)
    with _start_lock(runtime):
        result = _start_bound(
            args,
            command_id=command_id,
            mission_id=mission_id,
            policy=policy,
            runtime=runtime,
            binding=binding,
        )
    if args.open_viewer:
        _open_live(mission_id)
    return result


def _start_bound(
    args: argparse.Namespace,
    *,
    command_id: str,
    mission_id: str,
    policy: ProjectPolicy,
    runtime: Path,
    binding: dict[str, object],
) -> dict[str, object]:
    store = _store()
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
                    "repository_head": existing.mission.base_sha,
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
    store = _store()
    snapshot = store.snapshot(mission_id)
    if snapshot.mission.creation_source != "scripted_fixture":
        raise MissionCliError(
            "local result creation is only available for scripted-local"
        )
    runtime = _mission_runtime(mission_id)
    repository = runtime / "repository"
    evidence_path = runtime / "attempt-evidence.sqlite3"
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise MissionCliError("scripted mission evidence is unavailable")
    evidence = SQLiteAttemptEvidenceStore(evidence_path)
    store.bind_artifact_resolver(evidence)
    store.bind_local_commit_verifier(
        partial(
            verify_local_result_receipt,
            runtime=runtime,
            repository=repository,
        )
    )
    candidate, verification = scripted_result_artifacts(store, evidence, mission_id)
    return store, snapshot, runtime, repository, evidence, candidate, verification


def _result_decision(args: argparse.Namespace, *, approved: bool) -> dict[str, object]:
    action = "approve-result" if approved else "reject-result"
    truth_kind = _truth_kind()
    (
        store,
        snapshot,
        runtime,
        repository,
        evidence,
        candidate,
        verification,
    ) = _scripted_bindings(args.mission_id)
    if candidate.sha256 != args.candidate_sha:
        raise MissionCliError(
            "candidate approval does not bind the exact assembled patch"
        )
    now = datetime.now(UTC)
    command_id = args.command_id or _command_id(
        action,
        args.mission_id,
        args.candidate_sha,
        args.operator_label,
        args.rationale,
    )
    common = {
        "runtime": runtime,
        "repository": repository,
        "mission_id": args.mission_id,
        "base_sha": snapshot.mission.base_sha,
        "candidate": candidate,
        "verification": verification,
        "evidence": evidence,
        "operator_label": args.operator_label,
        "rationale": args.rationale,
        "truth_kind": truth_kind,
    }
    if approved:
        store.approve_final_result(
            args.mission_id,
            command_id,
            expected_candidate_sha256=args.candidate_sha,
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
        receipt = approve_local_result(
            **common,
            approved_candidate_sha256=args.candidate_sha,
        )
        receipt_reference = evidence.put_artifact(
            "local-result-receipt",
            canonical_json_bytes(receipt.model_dump(mode="json")),
        )
        store.record_isolated_commit(
            args.mission_id,
            receipt.local_commit_sha,
            receipt_reference,
            _command_id("record-result", args.mission_id, receipt.receipt_sha256),
            recorded_at=now,
        )
    else:
        receipt = reject_local_result(**common)
        evidence.put_artifact(
            "local-result-receipt",
            canonical_json_bytes(receipt.model_dump(mode="json")),
        )
        store.reject_final_result(
            args.mission_id,
            command_id,
            expected_candidate_sha256=args.candidate_sha,
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    return {
        "status": "completed" if approved else "rejected",
        "mission_id": args.mission_id,
        "decision": receipt.decision,
        "candidate_sha256": receipt.candidate_patch_sha256,
        "receipt_id": receipt.receipt_id,
        "local_commit_sha": receipt.local_commit_sha,
        "result_ref": receipt.result_ref,
        "pushed": False,
        "pull_request_created": False,
        "deployed": False,
    }


def _mutate(args: argparse.Namespace) -> dict[str, object]:
    store = _store()
    action = args.mission_action
    now = datetime.now(UTC)
    if action == "replan":
        truth_kind = _truth_kind()
        result = store.request_replan(
            args.mission_id,
            args.command_id
            or _command_id(
                action,
                args.mission_id,
                args.operator_label,
                args.reason,
            ),
            reason=args.reason,
            operator_label=args.operator_label,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    elif action in {"pause", "resume", "cancel"}:
        truth_kind = _truth_kind()
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
        active = store.recover_dispatches(args.mission_id, recorded_at=now)
        registry = (
            OwnedProcessRegistry(_mission_runtime(args.mission_id)) if active else None
        )
        try:
            prepared = () if registry is None else registry.prepare_cancel(active)
        except ProcessControlError as error:
            raise MissionCliError(
                "active workers could not be bound to their owned runtime"
            ) from error
        if action == "cancel":
            result = store.cancel(
                args.mission_id,
                command_id,
                operator_label=args.operator_label,
                rationale=args.rationale,
                truth_kind=truth_kind,
                recorded_at=now,
            )
        else:
            result = getattr(store, action)(
                args.mission_id,
                command_id,
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
        if action == "cancel":
            return {
                "mission_id": args.mission_id,
                "status": "cancelled",
            }
    elif action == "retry":
        truth_kind = _truth_kind()
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
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    elif action == "approve-plan":
        truth_kind = _truth_kind()
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
            store.approve_plan(
                args.mission_id,
                command_id,
                expected_revision=args.revision,
                operator_label=args.operator_label,
                rationale=args.rationale,
                truth_kind=truth_kind,
                recorded_at=now,
            )
            if snapshot.mission.status == "awaiting_result":
                return _committed_scripted_run_value(store, args.mission_id)
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
            raise MissionCliError(
                "ADK plan execution is NOT PROVEN in this release; plan remains proposed"
            )
        result = store.approve_plan(
            args.mission_id,
            command_id,
            expected_revision=args.revision,
            operator_label=args.operator_label,
            rationale=args.rationale,
            truth_kind=truth_kind,
            recorded_at=now,
        )
    elif action == "decide-gate":
        truth_kind = _truth_kind()
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
    if args.command != "mission":
        raise MissionCliError("not a mission CLI command")
    if args.mission_action == "replay":
        return _replay(args), None
    if args.mission_action == "status":
        return 0, _status_value(args.mission_id)
    if args.mission_action == "open":
        return _open_live(args.mission_id), None
    if args.mission_action == "watch":
        return 0, _watch_value(args)
    if args.mission_action == "start":
        return 0, _start(args)
    return 0, _mutate(args)


def handle(args: argparse.Namespace, *, json_mode: bool | None = None) -> int:
    json_mode = getattr(args, "json_mode", False) if json_mode is None else json_mode
    try:
        code, value = _dispatch(args)
        if value is not None:
            if json_mode:
                sys.stdout.write(canonical_json_bytes(value).decode() + "\n")
            elif args.command == "mission" and args.mission_action == "status":
                sys.stdout.write(_render_status(value))
            elif args.command == "mission" and args.mission_action == "watch":
                if value["snapshot"] is not None:
                    sys.stdout.write(_render_status(value["snapshot"]))
                sys.stdout.write(
                    f"WATCH events={len(value['events'])} next_after_seq={value['next_after_seq']}\n"
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
