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
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from ..artifact_envelope import ArtifactEnvelopeV2, DirectArtifactInputV2
from ..execution import ExecutionError, TestRun, run_fixture_tests
from ..hashing import (
    TREE_HASH_VERSION,
    canonical_json_bytes,
    canonical_json_sha256,
    candidate_tree_sha256,
    sha256_hex,
)
from ..core_models import (
    BoundedText,
    FixturePolicy,
    FrozenModel,
    Identifier,
    RepoPath,
    Sha256,
    TruthKind,
)
from .evidence import (
    AttemptEvidenceAuthority,
    AttemptEvidenceConflict,
    AttemptEvidenceEventType,
    AttemptEvidenceInput,
    SQLiteAttemptEvidenceStore,
    TrustedCheckReceipt,
)
from .local_result import prepare_local_final_result_bundle
from .mission_models import (
    ArtifactEnvelopeReferenceV2,
    ArtifactVisibility,
    AttemptResult,
    CommandTemplate,
    Criterion,
    Dispatch,
    EvidenceReference,
    GenericEvidenceLink,
    Mission,
    MissionStatus,
    NetworkPolicy,
    Plan,
    ProjectPolicy,
    PublishedArtifactReferenceV2,
    PublicationDraft,
    PublicationState,
    ResourceBudget,
    RetentionPolicy,
    Task,
    TaskKind,
    artifact_input_reference_key,
)
from .process_control import (
    ControlledProcessRunner,
    OwnedProcessRegistry,
    ProcessCancelled,
    ProcessControlError,
)
from .scheduler import MissionScheduler, SystemClock
from .sqlite_mission_store import LeaseConflict, MissionConflict, SQLiteMissionStore, StaleWorker
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
_WORKER_TIMEOUT_GRACE_SECONDS = 2
# The attempt lock has no timed acquire on macOS; poll it instead of parking.
_ATTEMPT_LOCK_POLL_SECONDS = 0.05


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


class _PatchManifestEntry(FrozenModel):
    path: RepoPath
    hunk_count: int = Field(ge=0)
    patch_sha256: Sha256


class _PatchManifest(FrozenModel):
    changed_paths: tuple[RepoPath, ...] = Field(min_length=1, max_length=64)
    entries: tuple[_PatchManifestEntry, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def paths_agree(self) -> _PatchManifest:
        if (
            self.changed_paths != tuple(sorted(set(self.changed_paths)))
            or tuple(item.path for item in self.entries) != self.changed_paths
        ):
            raise ValueError("patch manifest paths must be sorted, unique, and exact")
        return self


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
    criteria: tuple[Criterion, ...]
    policy: _ScenarioPolicy
    tasks: tuple[Task, ...]
    source_path: Path = Field(exclude=True)

    @model_validator(mode="after")
    def canonical_fixture(self) -> ScriptedScenario:
        if self.success_criteria != tuple(sorted(set(self.success_criteria))):
            raise ValueError("scenario criteria must be sorted and unique")
        if tuple(sorted(item.description for item in self.criteria)) != self.success_criteria:
            raise ValueError("scenario criterion contracts do not match success criteria")
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
            criteria=self.criteria,
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


def fixture_policy_for(
    workspace: Path, *, test_timeout_seconds: int = 15
) -> FixturePolicy:
    """Bind the frozen fixture-tests command to one exact workspace inventory.

    Shared by the scripted worker and the host-sandbox check runner so both
    trusted check paths materialize and hash the same candidate tree. The
    scripted fixture keeps its 15 second budget; the host-sandbox runner passes
    the policy template's own timeout so the attested template digest and the
    enforced budget agree.
    """

    files = _inventory(workspace)
    return FixturePolicy(
        root="fixture",
        tracked_paths=tuple(files),
        mutable_paths=tuple(files),
        fixed_test_command=_FIXED_TEST_COMMAND,
        test_timeout_seconds=test_timeout_seconds,
        max_test_output_bytes=16_384,
        max_write_bytes=262_144,
        max_patch_bytes=1_048_576,
        tree_sha256=candidate_tree_sha256(files),
        tree_hash_version="graphene.tree.v2",
        tree_hash_algorithm="sha256(graphene.tree.v2 length-prefixed manifest)",
    )


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
                stream.write(
                    f"{TREE_HASH_VERSION} {candidate_tree_sha256(files)}\n".encode()
                )
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
    try:
        version, expected = digest_path.read_text(encoding="ascii").split()
    except ValueError as error:
        raise ScriptedError("scripted fixture tree hash metadata is invalid") from error
    if version != TREE_HASH_VERSION:
        raise ScriptedError("scripted fixture tree hash version is unsupported")
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
        accepted_inputs: Mapping[str, PublishedArtifactReferenceV2],
    ) -> None:
        expected = {item.producer_task_id for item in task.inputs}
        if set(accepted_inputs) != expected:
            raise ScriptedError("task did not receive its exact accepted inputs")
        for producer in sorted(accepted_inputs):
            reference = accepted_inputs[producer]
            if reference.kind != "patch":
                raise ScriptedError("task input is not an accepted patch")
            patch = self.evidence.resolve_enveloped(reference)
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
        return fixture_policy_for(workspace)

    @staticmethod
    def _direct_inputs(dispatch: Dispatch) -> tuple[DirectArtifactInputV2, ...]:
        values = []
        for reference in dispatch.input_publications:
            if isinstance(reference, PublishedArtifactReferenceV2):
                values.append(
                    DirectArtifactInputV2(
                        publication_id=reference.publication_id,
                        producer_task_id=reference.producer_task_id,
                        output_name=reference.output_name,
                        artifact_envelope_sha256=reference.artifact_envelope_sha256,
                    )
                )
            elif reference.kind != "operator-input":
                raise ScriptedError("legacy publication input has no V2 envelope")
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.producer_task_id,
                    item.output_name,
                    item.publication_id,
                    item.artifact_envelope_sha256,
                ),
            )
        )

    @staticmethod
    def _media_type(kind: str) -> str:
        return {
            "patch": "application/vnd.graphene.git-patch",
            "test-receipt": "application/vnd.graphene.check-receipt+json",
        }.get(kind, "application/octet-stream")

    def _store_enveloped_artifact(
        self,
        dispatch: Dispatch,
        *,
        output_name: str,
        kind: str,
        content: bytes,
        tree_sha256: str | None,
        mutation_manifest_sha256: str | None = None,
    ) -> tuple[EvidenceReference, ArtifactEnvelopeReferenceV2]:
        if self.store is None:
            raise ScriptedError("artifact envelope requires bound mission state")
        snapshot = self.store.snapshot(dispatch.mission_id)
        if (
            snapshot.plan.revision != dispatch.plan_revision
            or canonical_json_sha256(snapshot.plan.model_dump(mode="json"))
            != dispatch.plan_sha256
            or snapshot.policy.base_sha != self.base_sha
        ):
            raise ScriptedError("artifact envelope authority changed")
        envelope = ArtifactEnvelopeV2.create(
            content,
            mission_id=dispatch.mission_id,
            plan_revision=dispatch.plan_revision,
            plan_sha256=dispatch.plan_sha256,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            fencing_token=dispatch.fencing_token,
            policy_sha256=snapshot.policy.policy_sha256,
            base_git_commit=self.base_sha,
            direct_inputs=self._direct_inputs(dispatch),
            output_name=output_name,
            artifact_kind=kind,
            media_type=self._media_type(kind),
            mutation_manifest_sha256=mutation_manifest_sha256,
            tree_hash_version=None if tree_sha256 is None else TREE_HASH_VERSION,
            tree_sha256=tree_sha256,
            created_by="trusted-worker-wrapper",
        )
        return self.evidence.put_artifact_envelope(envelope, content)

    def _recover_enveloped_artifact(
        self,
        dispatch: Dispatch,
        *,
        output_name: str,
        kind: str,
        artifact: EvidenceReference,
    ) -> ArtifactEnvelopeReferenceV2:
        if self.store is None:
            raise ScriptedError("artifact recovery requires bound mission state")
        snapshot = self.store.snapshot(dispatch.mission_id)
        recovered = self.evidence.find_enveloped(
            artifact.id,
            expected={
                "schema_version": 2,
                "domain": "graphene.artifact.v2",
                "mission_id": dispatch.mission_id,
                "plan_revision": dispatch.plan_revision,
                "plan_sha256": dispatch.plan_sha256,
                "task_id": dispatch.task_id,
                "attempt_id": dispatch.attempt_id,
                "fencing_token": dispatch.fencing_token,
                "policy_sha256": snapshot.policy.policy_sha256,
                "base_git_commit": self.base_sha,
                "direct_inputs": self._direct_inputs(dispatch),
                "output_name": output_name,
                "artifact_kind": kind,
                "media_type": self._media_type(kind),
                "created_by": "trusted-worker-wrapper",
            },
        )
        if recovered is None or recovered.content_sha256 != artifact.sha256:
            raise ScriptedError("scripted artifact envelope is unavailable")
        return recovered

    def _patch(
        self,
        workspace: Path,
        paths: tuple[str, ...] | None = None,
        *,
        require_exact: bool = True,
    ) -> tuple[bytes, tuple[str, ...]]:
        arguments = tuple(_inventory(workspace)) if paths is None else paths
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
        if paths is not None and require_exact and changed != tuple(sorted(paths)):
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

    def _publication_paths(
        self,
        task: Task,
        references: tuple[EvidenceReference, ...],
    ) -> tuple[str, ...]:
        output = task.expected_outputs[0]
        if task.kind not in {TaskKind.WORK, TaskKind.ASSEMBLY}:
            return output.paths
        manifests = tuple(
            item for item in references if item.kind == "changed-path-hunk-manifest"
        )
        if len(manifests) != 1:
            raise ScriptedError("scripted publication has no exact path manifest")
        reference = manifests[0]
        raw = self.evidence.resolve(reference.kind, reference.id)
        if raw is None or sha256_hex(raw) != reference.sha256:
            raise ScriptedError("scripted publication path manifest is unavailable")
        try:
            manifest = _PatchManifest.model_validate_json(raw)
        except ValidationError as error:
            raise ScriptedError("scripted publication path manifest is invalid") from error
        if canonical_json_bytes(manifest.model_dump(mode="json")) != raw:
            raise ScriptedError("scripted publication path manifest is not canonical")
        if manifest.changed_paths != output.paths:
            raise ScriptedError("scripted publication paths exceed its write lease")
        return manifest.changed_paths

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
        accepted_inputs: Mapping[str, PublishedArtifactReferenceV2],
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
        command_id = "scripted_" + canonical_json_sha256(
            {
                "attempt_id": dispatch.attempt_id,
                "event_type": event_type,
                "seq": head.seq + 1,
            }
        )[:24]
        if event_type == AttemptEvidenceEventType.CHECK_COMPLETED:
            if len(references) != 1:
                raise ScriptedError("trusted check requires one receipt")
            self.evidence.append_check(
                evidence_id,
                head,
                command_id,
                mission_id=dispatch.mission_id,
                task_id=dispatch.task_id,
                attempt_id=dispatch.attempt_id,
                receipt=references[0],
                payload=payload,
                recorded_at=self.clock(),
            )
        else:
            self.evidence.append(
                evidence_id,
                head,
                command_id,
                AttemptEvidenceInput(
                    mission_id=dispatch.mission_id,
                    task_id=dispatch.task_id,
                    attempt_id=dispatch.attempt_id,
                    event_type=event_type,
                    truth_kind=TruthKind.RUNTIME_OBSERVED,
                    authority=AttemptEvidenceAuthority.SCRIPTED_WORKER,
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
        output = task.expected_outputs[0]
        artifacts = tuple(item for item in references if item.kind == output.kind)
        enveloped_references = tuple(
            item
            for item in references
            if item.kind in {output.kind, "test-receipt"}
        )
        artifact_envelopes = tuple(
            sorted(
                (
                    self._recover_enveloped_artifact(
                        dispatch,
                        output_name=output.name,
                        kind=item.kind,
                        artifact=item,
                    )
                    for item in enveloped_references
                ),
                key=lambda item: item.artifact_envelope_sha256,
            )
        )
        publication_envelopes = tuple(
            item for item in artifact_envelopes if item.kind == output.kind
        )
        if succeeded:
            if (
                len(task.expected_outputs) != 1
                or len(artifacts) != 1
                or len(publication_envelopes) != 1
            ):
                raise ScriptedError("scripted terminal publication is ambiguous")
            publications = (
                PublicationDraft(
                    output_name=output.name,
                    kind=output.kind,
                    sha256=artifacts[0].sha256,
                    artifact=publication_envelopes[0],
                    visibility=ArtifactVisibility.MISSION,
                    paths=self._publication_paths(task, references),
                ),
            )
        check_events = tuple(
            event
            for event in events
            if event.event_type == AttemptEvidenceEventType.CHECK_COMPLETED
        )
        if result_code in {
            "heartbeat_lost",
            "lease_lost",
            "process_killed",
            "worker_exception",
            "worker_interrupted",
            "worker_timeout",
        }:
            retryable = True
        elif result_code in {
            "malformed_output",
            "operator_cancelled",
            "policy_denied",
            "store_conflict",
        }:
            retryable = False
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
            artifact_envelopes=artifact_envelopes,
            publications=publications,
        )

    def terminal_failure(
        self, dispatch: Dispatch, error: Exception
    ) -> AttemptResult:
        """Seal an adapter failure so mission state can release this exact lease."""

        result_code, retryable = self._failure_code(dispatch, error)
        evidence_id = self._evidence_id(dispatch)
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
        except ProcessControlError:
            result_code, retryable = "process_killed", True

        # A timed-out thread may race this adapter while unwinding. Bounded CAS
        # retries let the durable terminal event decide which result won.
        for _ in range(3):
            head = self.evidence.head(evidence_id)
            if head.seq == 0:
                try:
                    self._record(
                        dispatch,
                        AttemptEvidenceEventType.ATTEMPT_STARTED,
                        {
                            "attempt_number": dispatch.attempt_number,
                            "worker_id": dispatch.worker_id,
                        },
                    )
                except AttemptEvidenceConflict:
                    continue
                head = self.evidence.head(evidence_id)
            events = self.evidence.tail(evidence_id, 0, head.seq)
            if events and events[-1].event_type in {
                AttemptEvidenceEventType.ATTEMPT_COMPLETED,
                AttemptEvidenceEventType.ATTEMPT_FAILED,
            }:
                task = next(
                    item
                    for item in self.store.snapshot(dispatch.mission_id).tasks
                    if item.task_id == dispatch.task_id
                )
                recovered = self._recover_result(dispatch, task)
                assert recovered is not None
                return recovered
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
            try:
                self._record(
                    dispatch,
                    AttemptEvidenceEventType.ATTEMPT_FAILED,
                    {"result_code": result_code},
                    references=references,
                )
            except AttemptEvidenceConflict:
                continue
            return AttemptResult(
                succeeded=False,
                retryable=retryable,
                result_code=result_code,
                evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
                evidence_refs=references,
            )
        raise ScriptedError("scripted worker failure could not be sealed") from error

    def _failure_code(
        self, dispatch: Dispatch, error: Exception
    ) -> tuple[str, bool]:
        if isinstance(error, ProcessCancelled):
            if (
                self.store is not None
                and self.store.snapshot(dispatch.mission_id).mission.status
                == MissionStatus.CANCELLED
            ):
                return "operator_cancelled", False
            return "process_killed", True
        if isinstance(
            error, (FuturesTimeoutError, TimeoutError, subprocess.TimeoutExpired)
        ):
            return "worker_timeout", True
        if isinstance(error, StaleWorker):
            return "lease_lost", True
        if isinstance(error, LeaseConflict):
            return "heartbeat_lost", True
        if isinstance(error, MissionConflict):
            return "store_conflict", False
        if isinstance(error, ValidationError):
            return "malformed_output", False
        if isinstance(error, (ExecutionError, ScriptedUnavailable)):
            return "policy_denied", False
        return "worker_exception", True

    def run(
        self,
        dispatch: Dispatch,
        task: Task,
        *,
        accepted_inputs: Mapping[str, PublishedArtifactReferenceV2] | None = None,
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
        artifact_envelope: ArtifactEnvelopeReferenceV2 | None = None
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
                patch, changed_paths = self._patch(
                    workspace, task.write_paths, require_exact=False
                )
            if patch is not None:
                manifest_reference = self._patch_manifest(workspace, changed_paths)
            candidate_tree = candidate_tree_sha256(_inventory(workspace))
            if patch is not None:
                artifact, artifact_envelope = self._store_enveloped_artifact(
                    dispatch,
                    output_name=task.expected_outputs[0].name,
                    kind="patch",
                    content=patch,
                    tree_sha256=candidate_tree,
                    mutation_manifest_sha256=manifest_reference.sha256,
                )
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
            if candidate_tree_sha256(_inventory(workspace)) != candidate_tree:
                raise ScriptedError("check runner changed the tested candidate")
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
        if self.store is None:
            raise ScriptedError("trusted check requires bound mission state")
        snapshot = self.store.snapshot(dispatch.mission_id)
        passed = (
            check.exit_code == 0
            and not check.timed_out
            and not check.output_truncated
        )
        candidate_references = (
            tuple(bound_inputs.values())
            if task.kind == TaskKind.VERIFICATION
            else (() if artifact_envelope is None else (artifact_envelope,))
        )
        check_result_code = (
            "passed"
            if passed
            else "worker_timeout"
            if check.timed_out
            else "acceptance_check_failed"
        )
        check_receipt = TrustedCheckReceipt(
            schema_version=2,
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            attempt_id=dispatch.attempt_id,
            plan_revision=dispatch.plan_revision,
            fencing_token=dispatch.fencing_token,
            policy_sha256=snapshot.policy.policy_sha256,
            base_sha=self.base_sha,
            runner_id="graphene_check_runner_v1",
            template_id=_CHECK_TEMPLATE,
            template_sha256=canonical_json_sha256(
                self.scenario.policy.command_templates[0].model_dump(mode="json")
            ),
            accepted_input_references=tuple(
                sorted(
                    dispatch.input_publications,
                    key=artifact_input_reference_key,
                )
            ),
            candidate_references=candidate_references,
            candidate_tree_hash_version=TREE_HASH_VERSION,
            candidate_tree_sha256=candidate_tree,
            result_code=check_result_code,
            exit_code=check.exit_code,
            timed_out=check.timed_out,
            output_sha256=sha256_hex(check.output.encode()),
            output_truncated=check.output_truncated,
            cleanup_complete=True,
        )
        check_record = canonical_json_bytes(check_receipt.model_dump(mode="json"))
        check_reference, check_envelope = self._store_enveloped_artifact(
            dispatch,
            output_name=task.expected_outputs[0].name,
            kind="test-receipt",
            content=check_record,
            tree_sha256=candidate_tree,
        )
        self._record(
            dispatch,
            AttemptEvidenceEventType.CHECK_COMPLETED,
            check_receipt.event_payload(check_reference.sha256),
            references=(check_reference,),
        )
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
                assert artifact_envelope is not None
                output = task.expected_outputs[0]
                publications = (
                    PublicationDraft(
                        output_name=output.name,
                        kind=output.kind,
                        sha256=artifact.sha256,
                        artifact=artifact_envelope,
                        visibility=ArtifactVisibility.MISSION,
                        paths=changed_paths,
                    ),
                )
            else:
                artifact = check_reference
                artifact_envelope = check_envelope
                output = task.expected_outputs[0]
                publications = (
                    PublicationDraft(
                        output_name=output.name,
                        kind=output.kind,
                        sha256=artifact.sha256,
                        artifact=artifact_envelope,
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
                "result_code": check_result_code,
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
            {"result_code": check_result_code},
            references=references,
        )
        result = AttemptResult(
            succeeded=passed,
            retryable=not passed,
            result_code=check_result_code,
            evidence_link=GenericEvidenceLink(evidence_id=evidence_id),
            evidence_refs=references,
            artifact_envelopes=tuple(
                sorted(
                    {
                        item.artifact_envelope_sha256: item
                        for item in (artifact_envelope, check_envelope)
                        if item is not None
                    }.values(),
                    key=lambda item: item.artifact_envelope_sha256,
                )
            ),
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
    ) -> dict[str, PublishedArtifactReferenceV2]:
        accepted: dict[str, PublishedArtifactReferenceV2] = {}
        for requirement in task.inputs:
            matches = tuple(
                item
                for item in dispatch.input_publications
                if isinstance(item, PublishedArtifactReferenceV2)
                and item.producer_task_id == requirement.producer_task_id
                and item.output_name == requirement.name
                and item.kind == requirement.kind
            )
            if len(matches) != 1:
                raise ScriptedError("task input is not one accepted publication")
            if self.evidence.resolve_enveloped(matches[0]) is None:
                raise ScriptedError("accepted publication envelope is unavailable")
            accepted[requirement.producer_task_id] = matches[0]
        return accepted

    @staticmethod
    def _acquire_attempt_lock(descriptor: int, dispatch: Dispatch) -> None:
        """Take the attempt lock, or refuse once its lease can no longer be honoured."""

        import fcntl

        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError as error:
                remaining = (
                    dispatch.expires_at - datetime.now(UTC)
                ).total_seconds()
                if remaining <= 0:
                    raise ScriptedError(
                        "scripted attempt is still owned past its lease expiry"
                    ) from error
                time.sleep(min(_ATTEMPT_LOCK_POLL_SECONDS, remaining))

    def execute(self, dispatch: Dispatch) -> AttemptResult:
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
            # A duplicate delivery of the same attempt MUST serialize here and
            # then return the first executor's recovered result -- that is the
            # at-most-once contract proven by
            # test_scripted_worker_serializes_duplicate_dispatch_delivery. So
            # this wait is not removable. What is removable is its being
            # unbounded: `_execute_scripted_batch` abandons a running worker on
            # timeout, and a non-daemon pool thread parked here is then joined
            # with NO timeout by concurrent.futures._python_exit at interpreter
            # shutdown -- after the last test, after pytest has cancelled its
            # per-item timer. That is a wedge with no traceback.
            #
            # The bound is the dispatch's own lease expiry, not an invented
            # number: past it the holder's attempt is dead by the store's own
            # definition, so waiting longer cannot yield an authoritative
            # result. Wait until then, then fail closed and say so.
            self._acquire_attempt_lock(descriptor, dispatch)
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
        try:
            envelope_reference = publication.published_reference()
        except ValueError as error:
            raise ScriptedError(
                "scripted result artifact has no V2 envelope"
            ) from error
        raw = evidence.resolve_enveloped(envelope_reference)
        if raw is None or sha256_hex(raw) != envelope_reference.content_sha256:
            raise ScriptedError("scripted result artifact failed digest verification")
        return EvidenceReference(
            kind=envelope_reference.kind,
            id=envelope_reference.artifact_id,
            sha256=envelope_reference.content_sha256,
        )

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


def _execute_scripted_batch(
    dispatches: tuple[Dispatch, ...],
    worker: ScriptedWorker,
    scheduler: MissionScheduler,
    *,
    timeout_seconds: float,
) -> None:
    """Commit concurrent terminal results independently in completion order."""

    executor = ThreadPoolExecutor(
        max_workers=len(dispatches), thread_name_prefix="graphene-scripted"
    )
    futures = {executor.submit(worker.execute, item): item for item in dispatches}
    errors: list[Exception] = []
    processed = set()

    def commit(future, dispatch: Dispatch, *, timed_out: bool = False) -> None:
        processed.add(future)
        if timed_out:
            future.cancel()
            try:
                worker.cancel(dispatch)
            except Exception as error:
                errors.append(error)
        try:
            result = (
                worker.terminal_failure(
                    dispatch, FuturesTimeoutError("scripted worker timed out")
                )
                if timed_out
                else AttemptResult.model_validate(future.result())
            )
        except Exception as error:
            try:
                result = worker.terminal_failure(dispatch, error)
            except Exception as terminal_error:
                errors.append(terminal_error)
                return
        try:
            scheduler.complete(dispatch, result)
        except Exception as error:
            if result.result_code == "operator_cancelled" and isinstance(
                error, LeaseConflict
            ):
                return
            errors.append(error)

    try:
        try:
            for future in as_completed(futures, timeout=timeout_seconds):
                commit(future, futures[future])
        except FuturesTimeoutError:
            for future, dispatch in sorted(
                futures.items(), key=lambda item: item[1].task_id
            ):
                if future in processed:
                    continue
                commit(future, dispatch, timed_out=not future.done())
    finally:
        # Python threads cannot be killed safely. Terminal evidence and the
        # released/fenced lease make any late completion non-authoritative.
        executor.shutdown(wait=False, cancel_futures=True)
    if errors:
        raise errors[0]


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
    evidence_path = (runtime / "attempt-evidence.sqlite3").resolve()
    evidence = store.artifact_resolver
    if isinstance(evidence, SQLiteAttemptEvidenceStore):
        if Path(evidence.path).resolve() != evidence_path:
            raise ScriptedError("mission artifact resolver does not match its runtime")
    else:
        evidence = SQLiteAttemptEvidenceStore(evidence_path)
        store.bind_artifact_resolver(evidence)
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
        dispatches = (
            scheduler.recover(mission_id, worker_ids)
            if remaining_attempts <= 0
            else scheduler.tick(mission_id, worker_ids[:remaining_attempts])
        )
        if not dispatches:
            if remaining_attempts <= 0:
                raise ScriptedError("scripted mission exhausted its attempt budget")
            raise ScriptedError("scripted mission scheduler made no safe progress")
        batches.append(tuple(item.task_id for item in dispatches))
        template_timeout = max(
            item.timeout_seconds for item in scenario.policy.command_templates
        )
        _execute_scripted_batch(
            dispatches,
            worker,
            scheduler,
            timeout_seconds=min(
                template_timeout + _WORKER_TIMEOUT_GRACE_SECONDS,
                scheduler.lease_ttl_seconds - 1,
            ),
        )
        if store.snapshot(mission_id).mission.status == MissionStatus.CANCELLED:
            raise ScriptedError("scripted mission was cancelled")
    else:
        raise ScriptedError("scripted mission exceeded its bounded attempt budget")

    verified_head = store.verify(mission_id)
    prepare_local_final_result_bundle(
        store=store,
        mission_id=mission_id,
        expected_head=verified_head,
        recorded_at=datetime.now(UTC),
    )
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
        expected_head=store.head(mission_id),
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
    "fixture_policy_for",
    "initialize_fixture_repository",
    "load_scenario",
    "propose_scripted_mission",
    "run_scripted_mission",
    "scripted_plan_validation",
    "scripted_result_artifacts",
    "scripted_supported",
]
