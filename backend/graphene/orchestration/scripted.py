from __future__ import annotations

import json
import os
import signal
import shutil
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..execution import ExecutionError, TestRun, run_fixture_tests
from ..hashing import (
    canonical_json_bytes,
    canonical_json_sha256,
    candidate_tree_sha256,
    sha256_hex,
)
from ..models import (
    BoundedText,
    FixturePolicy,
    FrozenModel,
    Identifier,
    RepoPath,
    TruthKind,
)
from .evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceEventType,
    AttemptEvidenceInput,
    SQLiteAttemptEvidenceStore,
)
from .models import (
    ArtifactVisibility,
    AttemptState,
    AttemptResult,
    CommandTemplate,
    Dispatch,
    EvidenceReference,
    GenericEvidenceLink,
    Mission,
    MissionStatus,
    NetworkPolicy,
    Plan,
    ProjectPolicy,
    PublicationDraft,
    PublicationState,
    ResourceBudget,
    RetentionPolicy,
    Task,
    TaskKind,
)
from .process_control import (
    ControlledProcessRunner,
    OwnedProcessRegistry,
    ProcessCancelled,
    ProcessControlError,
)
from .scheduler import MissionScheduler, SystemClock
from .store import SQLiteMissionStore
from .validation import PlanValidationResult, require_valid_plan, validate_plan


ROOT = Path(__file__).resolve().parents[3]
_SOURCE_SCENARIO_PATH = ROOT / "demo/taskmaster/scenario.json"
_PACKAGED_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1] / "_taskmaster/scenario.json"
)
DEFAULT_SCENARIO_PATH = (
    _SOURCE_SCENARIO_PATH
    if _SOURCE_SCENARIO_PATH.is_file()
    else _PACKAGED_SCENARIO_PATH
)
_CHECK_TEMPLATE = "fixture-tests"
_FIXED_TEST_COMMAND = ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider")
_MAX_FIXTURE_FILES = 128
_MAX_FIXTURE_BYTES = 1_048_576
_MAX_FIXTURE_TOTAL_BYTES = 2_097_152
_MAX_FIXTURE_NODES = 512


def _wall_duration_bucket(seconds: float) -> str:
    if seconds < 1:
        return "under_1s"
    if seconds < 5:
        return "1_to_5s"
    if seconds < 15:
        return "5_to_15s"
    return "15s_or_more"


class ScriptedError(RuntimeError):
    pass


class ScriptedUnavailable(ScriptedError):
    pass


class _ScenarioPolicy(FrozenModel):
    allowed_read_globs: tuple[RepoPath, ...]
    allowed_write_globs: tuple[RepoPath, ...]
    exclusions: tuple[RepoPath, ...] = ()
    command_templates: tuple[CommandTemplate, ...]
    agent_roles: tuple[Identifier, ...]
    max_concurrency: int = Field(gt=0, le=64)
    retry_limit: int = Field(ge=0, le=10)
    resource_budget: ResourceBudget
    retention: RetentionPolicy
    risk_gates: tuple[Identifier, ...] = ()


class ScriptedScenario(FrozenModel):
    schema_version: Literal[1] = 1
    scenario_id: Identifier
    repository: RepoPath
    goal: BoundedText
    success_criteria: tuple[BoundedText, ...]
    policy: _ScenarioPolicy
    tasks: tuple[Task, ...]
    source_path: Path = Field(exclude=True)

    @model_validator(mode="after")
    def canonical_fixture(self) -> ScriptedScenario:
        if self.success_criteria != tuple(sorted(set(self.success_criteria))):
            raise ValueError("scenario criteria must be sorted and unique")
        ids = tuple(task.task_id for task in self.tasks)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("scenario tasks must have sorted unique IDs")
        if tuple(item.template_id for item in self.policy.command_templates) != (
            _CHECK_TEMPLATE,
        ):
            raise ValueError("scripted fixture has one frozen check template")
        if self.policy.command_templates[0].argv != _FIXED_TEST_COMMAND:
            raise ValueError("scripted fixture check command changed")
        if any(
            len({item.producer_task_id for item in task.inputs}) != len(task.inputs)
            for task in self.tasks
        ):
            raise ValueError("scripted task inputs require unique producers")
        if any(len(task.expected_outputs) != 1 for task in self.tasks):
            raise ValueError("scripted tasks require one exact output")
        return self

    @property
    def repository_path(self) -> Path:
        path = (self.source_path.parent / self.repository).resolve()
        if path.parent != self.source_path.parent.resolve() or not path.is_dir():
            raise ScriptedError("scripted fixture repository is unavailable")
        return path

    @property
    def attempts_path(self) -> Path:
        requested = self.source_path.parent / "attempts"
        if requested.is_symlink():
            raise ScriptedError("scripted fixture attempts are unsafe")
        try:
            path = requested.resolve(strict=True)
        except OSError as error:
            raise ScriptedError("scripted fixture attempts are unavailable") from error
        if path.parent != self.source_path.parent.resolve() or not path.is_dir():
            raise ScriptedError("scripted fixture attempts are unavailable")
        return path

    def contracts(
        self,
        *,
        mission_id: str,
        repo_id: str,
        base_sha: str,
        created_at: datetime,
    ) -> tuple[ProjectPolicy, Mission, Plan]:
        policy = ProjectPolicy(
            policy_id=f"{self.scenario_id}-policy",
            revision=1,
            repo_id=repo_id,
            base_ref="HEAD",
            base_sha=base_sha,
            network=NetworkPolicy(),
            **self.policy.model_dump(),
        )
        plan = Plan(
            mission_id=mission_id,
            revision=1,
            tasks=self.tasks,
            max_concurrency=self.policy.max_concurrency,
        )
        mission = Mission(
            mission_id=mission_id,
            policy_id=policy.policy_id,
            policy_revision=policy.revision,
            repo_id=repo_id,
            base_sha=base_sha,
            goal=self.goal,
            success_criteria=self.success_criteria,
            plan_revision=1,
            creation_source="scripted_fixture",
            resource_budget=policy.resource_budget,
            unknowns=(
                "Cloud execution is not part of scripted-local proof.",
                "Gemini execution is not part of scripted-local proof.",
            ),
            created_at=created_at,
        )
        require_valid_plan(policy, plan)
        return policy, mission, plan


def load_scenario(path: str | Path = DEFAULT_SCENARIO_PATH) -> ScriptedScenario:
    source = Path(path).resolve(strict=True)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
        return ScriptedScenario.model_validate({**raw, "source_path": source})
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ScriptedError("scripted scenario is invalid") from error


def scripted_supported() -> bool:
    return sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()


def _git_environment() -> dict[str, str]:
    return {
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
        "GIT_AUTHOR_EMAIL": "fixture@graphene.invalid",
        "GIT_AUTHOR_NAME": "Graphene Scripted Fixture",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
        "GIT_COMMITTER_EMAIL": "fixture@graphene.invalid",
        "GIT_COMMITTER_NAME": "Graphene Scripted Fixture",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "PATH": os.defpath,
    }


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise ScriptedError("scripted Git executable is unavailable")
    try:
        result = subprocess.run(
            (
                executable,
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.filemode=false",
                "-c",
                "core.hooksPath=/dev/null",
                *arguments,
            ),
            cwd=repository,
            env=_git_environment(),
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ScriptedError("scripted Git operation failed") from error
    if result.returncode:
        raise ScriptedError("scripted Git operation was rejected")
    return result.stdout


def _inventory(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total_bytes = 0
    nodes = 0
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for name in sorted(directories):
            nodes += 1
            if nodes > _MAX_FIXTURE_NODES:
                raise ScriptedError("scripted fixture traversal is unbounded")
            if name in {".git", ".pytest_cache", "__pycache__"}:
                continue
            metadata = (current_path / name).lstat()
            if not stat.S_ISDIR(metadata.st_mode):
                raise ScriptedError("scripted fixture contains a non-regular node")
            retained.append(name)
        directories[:] = retained
        for name in sorted(names):
            nodes += 1
            if nodes > _MAX_FIXTURE_NODES:
                raise ScriptedError("scripted fixture traversal is unbounded")
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if relative == ".git" or path.suffix in {".pyc", ".pyo"}:
                continue
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ScriptedError("scripted fixture contains a non-regular node")
            content = path.read_bytes()
            total_bytes += len(content)
            if (
                len(content) > _MAX_FIXTURE_BYTES
                or total_bytes > _MAX_FIXTURE_TOTAL_BYTES
            ):
                raise ScriptedError("scripted fixture exceeds its byte cap")
            files[relative] = content
            if len(files) > _MAX_FIXTURE_FILES:
                raise ScriptedError("scripted fixture inventory is unbounded")
    if not files or len(files) > _MAX_FIXTURE_FILES:
        raise ScriptedError("scripted fixture inventory is unbounded")
    return files


def _scenario_inventory(scenario: ScriptedScenario) -> dict[str, bytes]:
    source = scenario.source_path
    metadata = source.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ScriptedError("scripted scenario is not a regular file")
    files = {"scenario.json": source.read_bytes()}
    for relative, content in _inventory(scenario.repository_path).items():
        files[f"{scenario.repository}/{relative}"] = content
    for relative, content in _inventory(scenario.attempts_path).items():
        files[f"attempts/{relative}"] = content
    if (
        len(files) > _MAX_FIXTURE_FILES
        or sum(map(len, files.values())) > _MAX_FIXTURE_TOTAL_BYTES
    ):
        raise ScriptedError("scripted scenario snapshot is unbounded")
    return files


def initialize_fixture_repository(
    scenario: ScriptedScenario,
    runtime: Path,
) -> tuple[Path, str]:
    if runtime.is_symlink():
        raise ScriptedError("scripted runtime is unsafe")
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = runtime.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ScriptedError("scripted runtime is not private")
    runtime = runtime.resolve(strict=True)
    repository = runtime / "repository"
    staging = runtime / ".repository.graphene-staging"
    if staging.exists() or staging.is_symlink():
        staged = staging.lstat()
        if (
            not stat.S_ISDIR(staged.st_mode)
            or stat.S_IMODE(staged.st_mode) != 0o700
            or (hasattr(os, "getuid") and staged.st_uid != os.getuid())
        ):
            raise ScriptedError("scripted repository staging is unsafe")
        shutil.rmtree(staging)
    if not repository.exists():
        try:
            staging.mkdir(mode=0o700)
            for relative, content in _inventory(scenario.repository_path).items():
                target = staging.joinpath(*relative.split("/"))
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            _git(staging, "init", "-q", "-b", "main")
            _git(staging, "add", "--all", "--")
            _git(staging, "commit", "-q", "-m", "Taskmaster fixture base")
            directories: list[Path] = []
            for current, names, files in os.walk(staging, followlinks=False):
                current_path = Path(current)
                directories.append(current_path)
                for name in (*names, *files):
                    path = current_path / name
                    metadata = path.lstat()
                    if stat.S_ISREG(metadata.st_mode):
                        descriptor = os.open(
                            path,
                            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                        )
                        try:
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
            for directory in reversed(directories):
                descriptor = os.open(
                    directory,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            if repository.exists() or repository.is_symlink():
                raise ScriptedError("scripted repository already exists")
            os.rename(staging, repository)
            directory_descriptor = os.open(
                runtime,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError as error:
            raise ScriptedError(
                "scripted repository could not be initialized"
            ) from error
        finally:
            if staging.exists() or staging.is_symlink():
                staged = staging.lstat()
                if (
                    not stat.S_ISDIR(staged.st_mode)
                    or stat.S_IMODE(staged.st_mode) != 0o700
                    or (hasattr(os, "getuid") and staged.st_uid != os.getuid())
                ):
                    raise ScriptedError("scripted repository staging is unsafe")
                shutil.rmtree(staging)
    if repository.is_symlink() or not repository.is_dir():
        raise ScriptedError("scripted repository is unsafe")
    base_sha = _git(repository, "rev-parse", "--verify", "HEAD").decode().strip()
    if len(base_sha) != 40:
        raise ScriptedError("scripted repository base is invalid")
    directory_descriptor = os.open(
        runtime,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return repository, base_sha


def _persisted_scenario(
    runtime: Path,
    scenario: ScriptedScenario | None = None,
) -> ScriptedScenario:
    if runtime.is_symlink():
        raise ScriptedError("scripted runtime is unsafe")
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = runtime.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ScriptedError("scripted runtime is not private")
    runtime = runtime.resolve(strict=True)
    fixture = runtime / "fixture"
    staging = runtime / ".fixture.graphene-staging"
    if staging.exists() or staging.is_symlink():
        staged = staging.lstat()
        if (
            not stat.S_ISDIR(staged.st_mode)
            or stat.S_IMODE(staged.st_mode) != 0o700
            or (hasattr(os, "getuid") and staged.st_uid != os.getuid())
        ):
            raise ScriptedError("scripted fixture staging is unsafe")
        shutil.rmtree(staging)
    if not fixture.exists():
        if scenario is None:
            raise ScriptedError("scripted fixture snapshot is unavailable")
        try:
            staging.mkdir(mode=0o700)
            files = _scenario_inventory(scenario)
            for relative, content in files.items():
                target = staging.joinpath(*relative.split("/"))
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            digest_path = staging / ".graphene-fixture.sha256"
            descriptor = os.open(
                digest_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(candidate_tree_sha256(files).encode() + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            directories = [Path(current) for current, _, _ in os.walk(staging)]
            for directory in reversed(directories):
                descriptor = os.open(
                    directory,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            if fixture.exists() or fixture.is_symlink():
                raise ScriptedError("scripted fixture snapshot already exists")
            os.rename(staging, fixture)
            directory_descriptor = os.open(
                runtime,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError as error:
            raise ScriptedError(
                "scripted fixture snapshot could not be created"
            ) from error
        finally:
            if staging.exists() or staging.is_symlink():
                staged = staging.lstat()
                if (
                    not stat.S_ISDIR(staged.st_mode)
                    or stat.S_IMODE(staged.st_mode) != 0o700
                    or (hasattr(os, "getuid") and staged.st_uid != os.getuid())
                ):
                    raise ScriptedError("scripted fixture staging is unsafe")
                shutil.rmtree(staging)
    digest_path = fixture / ".graphene-fixture.sha256"
    if (
        fixture.is_symlink()
        or not fixture.is_dir()
        or digest_path.is_symlink()
        or not digest_path.is_file()
    ):
        raise ScriptedError("scripted fixture snapshot is unsafe")
    expected = digest_path.read_text(encoding="ascii").strip()
    inventory = _inventory(fixture)
    inventory.pop(".graphene-fixture.sha256", None)
    if candidate_tree_sha256(inventory) != expected:
        raise ScriptedError("scripted fixture snapshot changed after proposal")
    directory_descriptor = os.open(
        runtime,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return load_scenario(fixture / "scenario.json")


@dataclass(frozen=True, slots=True)
class ScriptedOutcome:
    result: AttemptResult
    artifact: EvidenceReference | None
    check_passed: bool
    workspace: Path
    started_monotonic: float
    ended_monotonic: float


@dataclass(frozen=True, slots=True)
class ScriptedMissionProposal:
    mission_id: str
    runtime: Path
    repository: Path
    base_sha: str
    validation: PlanValidationResult


@dataclass(frozen=True, slots=True)
class ScriptedMissionRun:
    mission_id: str
    runtime: Path
    repository: Path
    base_sha: str
    candidate: EvidenceReference
    verification: EvidenceReference
    batches: tuple[tuple[str, ...], ...]
    outcomes: tuple[ScriptedOutcome, ...]


class ScriptedWorker:
    """Deterministic fixture worker; scheduling and retries remain external."""

    def __init__(
        self,
        *,
        scenario: ScriptedScenario,
        repository: Path,
        runtime: Path,
        base_sha: str,
        evidence: SQLiteAttemptEvidenceStore,
        store: SQLiteMissionStore | None = None,
        check_runner: Callable[[Path, FixturePolicy], TestRun] = run_fixture_tests,
        heartbeat: Callable[[Dispatch], object] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not scripted_supported():
            raise ScriptedUnavailable(
                "scripted-local requires macOS with executable /usr/bin/sandbox-exec"
            )
        self.scenario = scenario
        self.repository = repository.resolve(strict=True)
        self.runtime = runtime.resolve(strict=True)
        self.base_sha = base_sha
        self.evidence = evidence
        self.store = store
        self.check_runner = check_runner
        self.heartbeat = heartbeat
        self.clock = clock
        self._process_registry = OwnedProcessRegistry(self.runtime)
        self._attempt_locks = self.runtime / "attempt-locks"
        if self._attempt_locks.exists() and (
            self._attempt_locks.is_symlink() or not self._attempt_locks.is_dir()
        ):
            raise ScriptedError("scripted attempt lock directory is unsafe")
        self._attempt_locks.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self._attempt_locks, 0o700)
        self._git_lock = threading.Lock()
        self._outcome_lock = threading.Lock()
        self._outcomes: dict[str, ScriptedOutcome] = {}

    def _workspace(self, dispatch: Dispatch) -> Path:
        parent = self.runtime / "worktrees"
        parent.mkdir(mode=0o700, exist_ok=True)
        parent_metadata = parent.lstat()
        if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(
            parent_metadata.st_mode
        ):
            raise ScriptedError("scripted workspace parent is unsafe")
        workspace = parent / dispatch.workspace_id
        if workspace.is_symlink():
            raise ScriptedError("scripted workspace is unsafe")
        with self._git_lock:
            if not workspace.exists():
                _git(
                    self.repository,
                    "worktree",
                    "add",
                    "-q",
                    "--detach",
                    str(workspace),
                    self.base_sha,
                )
        if workspace.is_symlink() or not workspace.is_dir():
            raise ScriptedError("scripted workspace is unsafe")
        return workspace

    def _apply_inputs(
        self,
        workspace: Path,
        task: Task,
        accepted_inputs: Mapping[str, EvidenceReference],
    ) -> None:
        expected = {item.producer_task_id for item in task.inputs}
        if set(accepted_inputs) != expected:
            raise ScriptedError("task did not receive its exact accepted inputs")
        for producer in sorted(accepted_inputs):
            reference = accepted_inputs[producer]
            if reference.kind != "patch":
                raise ScriptedError("task input is not an accepted patch")
            patch = self.evidence.resolve(reference.kind, reference.id)
            if patch is None or sha256_hex(patch) != reference.sha256:
                raise ScriptedError("accepted task input is unavailable")
            _git(workspace, "apply", "--whitespace=nowarn", "-", input_bytes=patch)

    def _write_attempt(self, workspace: Path, task: Task, attempt_number: int) -> None:
        attempts = self.scenario.attempts_path
        requested = attempts / task.task_id / str(attempt_number)
        if requested.is_symlink():
            raise ScriptedError("scripted task attempt is unsafe")
        try:
            overlay = requested.resolve(strict=True)
        except OSError as error:
            raise ScriptedError("scripted task attempt is unavailable") from error
        if attempts not in overlay.parents or not overlay.is_dir():
            raise ScriptedError("scripted task attempt is unavailable")
        files = _inventory(overlay)
        if set(files) != set(task.write_paths):
            raise ScriptedError("scripted task attempt exceeds its write lease")
        for relative, content in files.items():
            target = workspace.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise ScriptedError("scripted write target is unsafe")
            target.write_bytes(content)

    @staticmethod
    def _fixture_policy(workspace: Path) -> FixturePolicy:
        files = _inventory(workspace)
        return FixturePolicy(
            root="fixture",
            tracked_paths=tuple(files),
            mutable_paths=tuple(files),
            fixed_test_command=_FIXED_TEST_COMMAND,
            test_timeout_seconds=15,
            max_test_output_bytes=16_384,
            max_write_bytes=262_144,
            max_patch_bytes=1_048_576,
            tree_sha256=candidate_tree_sha256(files),
            tree_hash_algorithm="sha256(path + NUL + bytes + NUL for sorted paths)",
        )

    def _patch(
        self, workspace: Path, paths: tuple[str, ...] | None = None
    ) -> tuple[bytes, tuple[str, ...]]:
        arguments = paths or tuple(_inventory(workspace))
        _git(workspace, "add", "--all", "--", *arguments)
        changed = tuple(
            item.decode()
            for item in _git(
                workspace,
                "diff",
                "--cached",
                "--name-only",
                "-z",
                self.base_sha,
                "--",
                *arguments,
            ).split(b"\0")
            if item
        )
        if paths is not None and changed != tuple(sorted(paths)):
            raise ScriptedError("scripted patch does not match its write lease")
        return (
            _git(
                workspace,
                "diff",
                "--cached",
                "--binary",
                self.base_sha,
                "--",
                *arguments,
            ),
            changed,
        )

    def _patch_manifest(
        self,
        workspace: Path,
        changed_paths: tuple[str, ...],
    ) -> EvidenceReference:
        entries = []
        for path in changed_paths:
            path_patch = _git(
                workspace,
                "diff",
                "--cached",
                "--binary",
                self.base_sha,
                "--",
                path,
            )
            entries.append(
                {
                    "hunk_count": sum(
                        line.startswith(b"@@ ") for line in path_patch.splitlines()
                    ),
                    "patch_sha256": sha256_hex(path_patch),
                    "path": path,
                }
            )
        return self.evidence.put_artifact(
            "changed-path-hunk-manifest",
            canonical_json_bytes(
                {"changed_paths": list(changed_paths), "entries": entries}
            ),
        )

    def _command_template_receipt(self, task: Task) -> EvidenceReference:
        template = next(
            item
            for item in self.scenario.policy.command_templates
            if item.template_id == task.acceptance_checks[0]
        )
        return self.evidence.put_artifact(
            "command-template-receipt",
            canonical_json_bytes(
                {
                    "template_id": template.template_id,
                    "template_sha256": canonical_json_sha256(
                        template.model_dump(mode="json")
                    ),
                }
            ),
        )

    def _context_manifest(
        self,
        dispatch: Dispatch,
        accepted_inputs: Mapping[str, EvidenceReference],
    ) -> EvidenceReference:
        if self.store is None:
            raise ScriptedError("scripted worker is not bound to mission state")
        snapshot = self.store.snapshot(dispatch.mission_id)
        selected = {(item.kind, item.sha256) for item in accepted_inputs.values()}
        excluded = sorted(
            {
                item.sha256
                for item in snapshot.publications
                if item.state == PublicationState.ACCEPTED
                and (item.kind, item.sha256) not in selected
            }
        )
        accepted = [
            {
                "artifact_id": accepted_inputs[producer].id,
                "kind": accepted_inputs[producer].kind,
                "producer_task_id": producer,
                "sha256": accepted_inputs[producer].sha256,
            }
            for producer in sorted(accepted_inputs)
        ]
        return self.evidence.put_artifact(
            "inherited-context-manifest",
            canonical_json_bytes(
                {
                    "accepted": accepted,
                    "excluded_sha256": excluded,
                    "opened_sha256": [item["sha256"] for item in accepted],
                }
            ),
        )

    @staticmethod
    def _evidence_id(dispatch: Dispatch) -> str:
        return (
            "attempt_evidence_"
            + canonical_json_sha256(
                {"attempt_id": dispatch.attempt_id, "mission_id": dispatch.mission_id}
            )[:24]
        )

    def _record(
        self,
        dispatch: Dispatch,
        event_type: AttemptEvidenceEventType,
        payload: dict[str, object],
        *,
        references: tuple[EvidenceReference, ...] = (),
    ) -> str:
        evidence_id = self._evidence_id(dispatch)
        head = self.evidence.head(evidence_id)
        self.evidence.append(
            evidence_id,
            head,
            "scripted_"
            + canonical_json_sha256(
                {
                    "attempt_id": dispatch.attempt_id,
                    "event_type": event_type,
                    "seq": head.seq + 1,
                }
            )[:24],
            AttemptEvidenceInput(
                mission_id=dispatch.mission_id,
                task_id=dispatch.task_id,
                attempt_id=dispatch.attempt_id,
                event_type=event_type,
                truth_kind=TruthKind.RUNTIME_OBSERVED,
                authority=(
                    AttemptEvidenceAuthority.CHECK_RUNNER
                    if event_type == AttemptEvidenceEventType.CHECK_COMPLETED
                    else AttemptEvidenceAuthority.SCRIPTED_WORKER
                ),
                references=references,
                payload=payload,
            ),
            recorded_at=self.clock(),
        )
        return evidence_id

    def _recover_result(self, dispatch: Dispatch, task: Task) -> AttemptResult | None:
        evidence_id = self._evidence_id(dispatch)
        head = self.evidence.head(evidence_id)
        if head.seq == 0:
            return None
        if head.seq > 256:
            raise ScriptedError("scripted attempt evidence exceeds its recovery bound")
        self.evidence.verify(evidence_id)
        events = self.evidence.tail(evidence_id, 0, head.seq)
        if len(events) != head.seq:
            raise ScriptedError("scripted attempt evidence is incomplete")
        terminal = events[-1]
        if (
            terminal.mission_id,
            terminal.task_id,
            terminal.attempt_id,
        ) != (dispatch.mission_id, dispatch.task_id, dispatch.attempt_id):
            raise ScriptedError("scripted attempt evidence identity changed")
        terminal_types = {
            AttemptEvidenceEventType.ATTEMPT_COMPLETED,
            AttemptEvidenceEventType.ATTEMPT_FAILED,
        }
        if terminal.event_type not in terminal_types:
            try:
                owned = tuple(
                    item
                    for item in self._process_registry.records_for_mission(
                        dispatch.mission_id
                    )
                    if item.attempt_id == dispatch.attempt_id
                )
                for item in owned:
                    self._process_registry.terminate_owned(item)
            except ProcessControlError as error:
                raise ScriptedError(
                    "interrupted scripted process could not be reconciled"
                ) from error
            references = tuple(
                sorted(
                    {
                        (item.kind, item.id, item.sha256): item
                        for event in events
                        for item in event.references
                    }.values(),
                    key=lambda item: (item.kind, item.id, item.sha256),
                )
            )
            self._record(
                dispatch,
                AttemptEvidenceEventType.ATTEMPT_FAILED,
                {"result_code": "worker_interrupted"},
                references=references,
            )
            return AttemptResult(
                succeeded=False,
                retryable=True,
                result_code="worker_interrupted",
                evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
                evidence_refs=references,
            )

        succeeded = terminal.event_type == AttemptEvidenceEventType.ATTEMPT_COMPLETED
        result_code = terminal.payload.get("result_code")
        if not isinstance(result_code, str) or (succeeded and result_code != "passed"):
            raise ScriptedError("scripted terminal evidence result is invalid")
        references = terminal.references
        publications: tuple[PublicationDraft, ...] = ()
        if succeeded:
            output = task.expected_outputs[0]
            artifacts = tuple(item for item in references if item.kind == output.kind)
            if len(task.expected_outputs) != 1 or len(artifacts) != 1:
                raise ScriptedError("scripted terminal publication is ambiguous")
            publications = (
                PublicationDraft(
                    output_name=output.name,
                    kind=output.kind,
                    sha256=artifacts[0].sha256,
                    visibility=ArtifactVisibility.MISSION,
                    paths=output.paths,
                ),
            )
        check_events = tuple(
            event
            for event in events
            if event.event_type == AttemptEvidenceEventType.CHECK_COMPLETED
        )
        if result_code == "worker_interrupted":
            retryable = True
        elif (
            len(check_events) == 1
            and type(check_events[0].payload.get("timed_out")) is bool
        ):
            retryable = not succeeded and not check_events[0].payload["timed_out"]
        else:
            raise ScriptedError("scripted terminal check evidence is ambiguous")
        return AttemptResult(
            succeeded=succeeded,
            retryable=retryable,
            result_code=result_code,
            evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
            evidence_refs=references,
            publications=publications,
        )

    def run(
        self,
        dispatch: Dispatch,
        task: Task,
        *,
        accepted_inputs: Mapping[str, EvidenceReference] | None = None,
    ) -> ScriptedOutcome:
        started = time.monotonic()
        if (
            dispatch.task_id != task.task_id
            or dispatch.task_kind != task.kind
            or tuple(dispatch.allowed_commands) != task.allowed_commands
            or tuple(dispatch.acceptance_checks) != task.acceptance_checks
            or task.allowed_commands != (_CHECK_TEMPLATE,)
            or task.acceptance_checks != (_CHECK_TEMPLATE,)
        ):
            raise ScriptedError("scripted dispatch does not match the accepted task")
        workspace = self._workspace(dispatch)
        self._record(
            dispatch,
            AttemptEvidenceEventType.ATTEMPT_STARTED,
            {
                "attempt_number": dispatch.attempt_number,
                "worker_id": dispatch.worker_id,
            },
        )
        bound_inputs = accepted_inputs or {}
        command_reference = self._command_template_receipt(task)
        self._record(
            dispatch,
            AttemptEvidenceEventType.OPERATION_STARTED,
            {"operation_id": "bounded-fixture-task", "template_id": _CHECK_TEMPLATE},
            references=(command_reference,),
        )
        artifact: EvidenceReference | None = None
        manifest_reference: EvidenceReference | None = None
        context_reference: EvidenceReference | None = None
        try:
            self._apply_inputs(workspace, task, bound_inputs)
            context_reference = self._context_manifest(dispatch, bound_inputs)
            patch: bytes | None = None
            changed_paths: tuple[str, ...] = ()
            if task.kind == TaskKind.WORK:
                self._write_attempt(workspace, task, dispatch.attempt_number)
                patch, changed_paths = self._patch(workspace, task.write_paths)
            elif task.kind == TaskKind.ASSEMBLY:
                patch, changed_paths = self._patch(workspace)
            if patch is not None:
                artifact = self.evidence.put_artifact("patch", patch)
                manifest_reference = self._patch_manifest(workspace, changed_paths)
            if self.check_runner is run_fixture_tests:
                if self.store is None:
                    raise ScriptedError("scripted worker is not bound to mission state")
                check = run_fixture_tests(
                    workspace,
                    self._fixture_policy(workspace),
                    process_runner=ControlledProcessRunner(
                        self._process_registry,
                        dispatch,
                        lambda: self.store.snapshot(dispatch.mission_id).mission.status,
                        heartbeat=(
                            None
                            if self.heartbeat is None
                            else lambda: self.heartbeat(dispatch)
                        ),
                    ),
                )
            else:
                check = self.check_runner(workspace, self._fixture_policy(workspace))
        except Exception as error:
            self._record(
                dispatch,
                AttemptEvidenceEventType.OPERATION_FAILED,
                {"operation_id": "bounded-fixture-task", "result_code": "rejected"},
                references=tuple(
                    item
                    for item in (command_reference, context_reference)
                    if item is not None
                ),
            )
            if isinstance(error, ExecutionError):
                raise ScriptedUnavailable(
                    "scripted fixture sandbox rejected execution"
                ) from error
            raise
        check_record = canonical_json_bytes(
            {
                "accepted_input_sha256": [
                    reference.sha256 for reference in dispatch.input_publications
                ],
                "candidate_patch_sha256": (
                    bound_inputs[task.inputs[0].producer_task_id].sha256
                    if task.kind == TaskKind.VERIFICATION and len(task.inputs) == 1
                    else None
                ),
                "duration_bucket": check.duration_bucket,
                "exit_code": check.exit_code,
                "output_sha256": sha256_hex(check.output.encode()),
                "output_truncated": check.output_truncated,
                "template_id": _CHECK_TEMPLATE,
                "timed_out": check.timed_out,
            }
        )
        check_reference = self.evidence.put_artifact("test-receipt", check_record)
        self._record(
            dispatch,
            AttemptEvidenceEventType.CHECK_COMPLETED,
            {
                "duration_bucket": check.duration_bucket,
                "exit_code": check.exit_code,
                "passed": check.exit_code == 0 and not check.timed_out,
                "template_id": _CHECK_TEMPLATE,
                "timed_out": check.timed_out,
            },
            references=(check_reference,),
        )
        passed = check.exit_code == 0 and not check.timed_out
        ended = time.monotonic()
        resource_reference = self.evidence.put_artifact(
            "resource-receipt",
            canonical_json_bytes(
                {
                    "attempt_wall_duration_bucket": _wall_duration_bucket(
                        ended - started
                    ),
                    "cpu_measurement": "unavailable",
                    "memory_measurement": "unavailable",
                    "measurement_clock": "monotonic",
                }
            ),
        )
        publications: tuple[PublicationDraft, ...] = ()
        if passed:
            if task.kind in {TaskKind.WORK, TaskKind.ASSEMBLY}:
                assert artifact is not None
                output = task.expected_outputs[0]
                publications = (
                    PublicationDraft(
                        output_name=output.name,
                        kind=output.kind,
                        sha256=artifact.sha256,
                        visibility=ArtifactVisibility.MISSION,
                        paths=output.paths,
                    ),
                )
            else:
                artifact = check_reference
                output = task.expected_outputs[0]
                publications = (
                    PublicationDraft(
                        output_name=output.name,
                        kind=output.kind,
                        sha256=artifact.sha256,
                        visibility=ArtifactVisibility.MISSION,
                        paths=output.paths,
                    ),
                )
        references = tuple(
            sorted(
                {
                    (item.kind, item.id, item.sha256): item
                    for item in (
                        artifact,
                        check_reference,
                        command_reference,
                        context_reference,
                        manifest_reference,
                        resource_reference,
                    )
                    if item is not None
                }.values(),
                key=lambda item: (item.kind, item.id, item.sha256),
            )
        )
        self._record(
            dispatch,
            (
                AttemptEvidenceEventType.OPERATION_COMPLETED
                if passed
                else AttemptEvidenceEventType.OPERATION_FAILED
            ),
            {
                "operation_id": "bounded-fixture-task",
                "result_code": "passed" if passed else "acceptance_check_failed",
            },
            references=references,
        )
        evidence_id = self._record(
            dispatch,
            (
                AttemptEvidenceEventType.ATTEMPT_COMPLETED
                if passed
                else AttemptEvidenceEventType.ATTEMPT_FAILED
            ),
            {"result_code": "passed" if passed else "acceptance_check_failed"},
            references=references,
        )
        result = AttemptResult(
            succeeded=passed,
            retryable=not passed and not check.timed_out,
            result_code="passed" if passed else "acceptance_check_failed",
            evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
            evidence_refs=references,
            publications=publications,
        )
        outcome = ScriptedOutcome(
            result,
            artifact,
            passed,
            workspace,
            started,
            ended,
        )
        with self._outcome_lock:
            self._outcomes[dispatch.attempt_id] = outcome
        return outcome

    def _accepted_inputs(
        self, dispatch: Dispatch, task: Task
    ) -> dict[str, EvidenceReference]:
        if self.store is None:
            raise ScriptedError("scripted worker is not bound to mission state")
        snapshot = self.store.snapshot(dispatch.mission_id)
        attempts = {item.attempt_id: item for item in snapshot.attempts}
        accepted: dict[str, EvidenceReference] = {}
        for requirement in task.inputs:
            matches = tuple(
                item
                for item in snapshot.publications
                if item.task_id == requirement.producer_task_id
                and item.output_name == requirement.name
                and item.kind == requirement.kind
                and item.state == PublicationState.ACCEPTED
            )
            if len(matches) != 1:
                raise ScriptedError("task input is not one accepted publication")
            publication = matches[0]
            attempt = attempts.get(publication.attempt_id)
            if attempt is None or attempt.state != AttemptState.COMMITTED:
                raise ScriptedError("accepted publication has no committed attempt")
            references = tuple(
                item
                for item in attempt.evidence_refs
                if item.kind == publication.kind and item.sha256 == publication.sha256
            )
            if len(references) != 1:
                raise ScriptedError("accepted publication has no exact artifact")
            accepted[requirement.producer_task_id] = references[0]
        return accepted

    def execute(self, dispatch: Dispatch) -> AttemptResult:
        import fcntl

        if self.store is None:
            raise ScriptedError("scripted worker is not bound to mission state")
        lock_path = self._attempt_locks / (
            sha256_hex(dispatch.attempt_id.encode()) + ".lock"
        )
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise ScriptedError("scripted attempt lock is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            snapshot = self.store.snapshot(dispatch.mission_id)
            tasks = tuple(
                item
                for item in snapshot.tasks
                if item.task_id == dispatch.task_id
                and snapshot.plan.revision == dispatch.plan_revision
            )
            if len(tasks) != 1:
                raise ScriptedError("scripted dispatch task is unavailable")
            recovered = self._recover_result(dispatch, tasks[0])
            if recovered is not None:
                return recovered
            outcome = self.run(
                dispatch,
                tasks[0],
                accepted_inputs=self._accepted_inputs(dispatch, tasks[0]),
            )
            return outcome.result
        finally:
            os.close(descriptor)

    def cancel(self, dispatch: Dispatch) -> None:
        self._process_registry.signal(dispatch, signal.SIGTERM)

    @property
    def outcomes(self) -> tuple[ScriptedOutcome, ...]:
        with self._outcome_lock:
            return tuple(
                sorted(self._outcomes.values(), key=lambda item: item.started_monotonic)
            )


def scripted_result_artifacts(
    store: SQLiteMissionStore,
    evidence: SQLiteAttemptEvidenceStore,
    mission_id: str,
) -> tuple[EvidenceReference, EvidenceReference]:
    snapshot = store.snapshot(mission_id)
    attempts = {item.attempt_id: item for item in snapshot.attempts}

    def artifact(kind: TaskKind, artifact_kind: str) -> EvidenceReference:
        task_ids = tuple(item.task_id for item in snapshot.tasks if item.kind == kind)
        if len(task_ids) != 1:
            raise ScriptedError("scripted result task is ambiguous")
        publications = tuple(
            item
            for item in snapshot.publications
            if item.task_id == task_ids[0]
            and item.kind == artifact_kind
            and item.state == PublicationState.ACCEPTED
        )
        if len(publications) != 1:
            raise ScriptedError("scripted result publication is unavailable")
        publication = publications[0]
        attempt = attempts.get(publication.attempt_id)
        if attempt is None or attempt.state != AttemptState.COMMITTED:
            raise ScriptedError("scripted result attempt is unavailable")
        references = tuple(
            item
            for item in attempt.evidence_refs
            if item.kind == publication.kind and item.sha256 == publication.sha256
        )
        if len(references) != 1:
            raise ScriptedError("scripted result artifact is unavailable")
        reference = references[0]
        raw = evidence.resolve(reference.kind, reference.id)
        if raw is None or sha256_hex(raw) != reference.sha256:
            raise ScriptedError("scripted result artifact failed digest verification")
        return reference

    return artifact(TaskKind.ASSEMBLY, "patch"), artifact(
        TaskKind.VERIFICATION, "test-receipt"
    )


def scripted_plan_validation(
    store: SQLiteMissionStore,
    runtime: Path,
    mission_id: str,
) -> PlanValidationResult:
    snapshot = store.snapshot(mission_id)
    scenario = _persisted_scenario(runtime)
    policy, _, plan = scenario.contracts(
        mission_id=mission_id,
        repo_id=snapshot.mission.repo_id,
        base_sha=snapshot.mission.base_sha,
        created_at=snapshot.mission.created_at,
    )
    if (
        plan != snapshot.plan
        or canonical_json_sha256(policy.model_dump(mode="json"))
        != snapshot.policy.policy_sha256
    ):
        raise ScriptedError("scripted proposal does not match its fixture snapshot")
    return validate_plan(policy, plan)


def propose_scripted_mission(
    *,
    scenario: ScriptedScenario,
    store: SQLiteMissionStore,
    runtime: Path,
    mission_id: str,
    created_at: datetime | None = None,
) -> ScriptedMissionProposal:
    scenario = _persisted_scenario(runtime, scenario)
    repository, base_sha = initialize_fixture_repository(scenario, runtime)
    created_at = created_at or datetime.now(UTC)
    policy, mission, plan = scenario.contracts(
        mission_id=mission_id,
        repo_id=f"repo_{scenario.scenario_id}_{base_sha[:16]}",
        base_sha=base_sha,
        created_at=created_at,
    )
    store.create_mission(
        policy,
        mission,
        plan,
        "create_" + canonical_json_sha256(mission.model_dump(mode="json"))[:32],
        recorded_at=created_at,
    )
    store.verify(mission_id)
    return ScriptedMissionProposal(
        mission_id,
        runtime.resolve(strict=True),
        repository,
        base_sha,
        validate_plan(policy, plan),
    )


def execute_scripted_mission(
    *,
    store: SQLiteMissionStore,
    runtime: Path,
    mission_id: str,
) -> ScriptedMissionRun:
    if not scripted_supported():
        raise ScriptedUnavailable(
            "scripted-local requires macOS with executable /usr/bin/sandbox-exec"
        )
    scenario = _persisted_scenario(runtime)
    repository, base_sha = initialize_fixture_repository(scenario, runtime)
    snapshot = store.snapshot(mission_id)
    if snapshot.mission.status != MissionStatus.RUNNING:
        raise ScriptedError("scripted execution requires an approved running plan")
    policy, expected_mission, plan = scenario.contracts(
        mission_id=mission_id,
        repo_id=f"repo_{scenario.scenario_id}_{base_sha[:16]}",
        base_sha=base_sha,
        created_at=snapshot.mission.created_at,
    )
    expected_mission = expected_mission.model_copy(
        update={"status": MissionStatus.RUNNING}
    )
    if (
        snapshot.mission != expected_mission
        or snapshot.plan != plan
        or snapshot.policy.policy_id != policy.policy_id
        or snapshot.policy.revision != policy.revision
        or snapshot.policy.repo_id != policy.repo_id
        or snapshot.policy.base_sha != policy.base_sha
    ):
        raise ScriptedError("approved mission does not match its fixture snapshot")
    budget = snapshot.mission.resource_budget
    evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
    store.bind_artifact_resolver(evidence)
    scheduler = MissionScheduler(
        store,
        clock=SystemClock(),
        lease_ttl_seconds=30,
        retry_backoff_seconds=0,
    )
    worker = ScriptedWorker(
        scenario=scenario,
        repository=repository,
        runtime=runtime,
        base_sha=base_sha,
        evidence=evidence,
        store=store,
        heartbeat=scheduler.heartbeat,
    )
    worker_ids = tuple(
        f"scripted-worker-{number + 1}" for number in range(plan.max_concurrency)
    )
    batches: list[tuple[str, ...]] = []
    for _ in range(budget.max_attempts + 1):
        snapshot = store.snapshot(mission_id)
        if snapshot.mission.status == MissionStatus.AWAITING_RESULT:
            break
        remaining_attempts = budget.max_attempts - len(snapshot.attempts)
        dispatches = scheduler.tick(
            mission_id, worker_ids[: max(0, remaining_attempts)]
        )
        if not dispatches:
            if remaining_attempts <= 0:
                raise ScriptedError("scripted mission exhausted its attempt budget")
            raise ScriptedError("scripted mission scheduler made no safe progress")
        batches.append(tuple(item.task_id for item in dispatches))
        with ThreadPoolExecutor(
            max_workers=len(dispatches), thread_name_prefix="graphene-scripted"
        ) as executor:
            futures = {
                item.attempt_id: executor.submit(worker.execute, item)
                for item in dispatches
            }
            try:
                results = tuple(
                    futures[item.attempt_id].result() for item in dispatches
                )
            except ProcessCancelled as error:
                if store.snapshot(mission_id).mission.status == MissionStatus.CANCELLED:
                    raise ScriptedError("scripted mission was cancelled") from error
                raise
        for dispatch, result in zip(dispatches, results, strict=True):
            scheduler.complete(dispatch, result)
    else:
        raise ScriptedError("scripted mission exceeded its bounded attempt budget")

    store.verify(mission_id)
    candidate, verification = scripted_result_artifacts(store, evidence, mission_id)
    return ScriptedMissionRun(
        mission_id,
        runtime,
        repository,
        base_sha,
        candidate,
        verification,
        tuple(batches),
        worker.outcomes,
    )


def run_scripted_mission(
    *,
    scenario: ScriptedScenario,
    store: SQLiteMissionStore,
    runtime: Path,
    mission_id: str,
    created_at: datetime | None = None,
) -> ScriptedMissionRun:
    """Run the explicit simulated auto-approval path used by the hero fixture."""

    created_at = created_at or datetime.now(UTC)
    proposal = propose_scripted_mission(
        scenario=scenario,
        store=store,
        runtime=runtime,
        mission_id=mission_id,
        created_at=created_at,
    )
    store.approve_plan(
        mission_id,
        "approve_" + canonical_json_sha256((mission_id, 1))[:32],
        expected_revision=1,
        operator_label="scripted-fixture",
        rationale="Explicit --auto-approve deterministic Taskmaster fixture run.",
        truth_kind=TruthKind.SIMULATED_FIXTURE,
        recorded_at=created_at,
    )
    return execute_scripted_mission(
        store=store,
        runtime=proposal.runtime,
        mission_id=mission_id,
    )


__all__ = [
    "DEFAULT_SCENARIO_PATH",
    "ScriptedError",
    "ScriptedMissionProposal",
    "ScriptedMissionRun",
    "ScriptedOutcome",
    "ScriptedScenario",
    "ScriptedUnavailable",
    "ScriptedWorker",
    "execute_scripted_mission",
    "initialize_fixture_repository",
    "load_scenario",
    "propose_scripted_mission",
    "run_scripted_mission",
    "scripted_plan_validation",
    "scripted_result_artifacts",
    "scripted_supported",
]
