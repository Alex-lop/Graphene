from __future__ import annotations

import json
import os
import sqlite3
import stat
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from .context import profile_for_task
from .execution import ExecutionError, fixture_base_sha
from .execution.adapter import _initialize_repository, _validate_fixture
from .hashing import canonical_json_sha256, sha256_hex
from .lineage.artifacts import SQLiteArtifactStore
from .lineage.lineage_reducer import reduce_events
from .lineage.service import RuntimeHandle, ScopedApplicationService
from .lineage.sqlite_lineage_store import LineageConflict, SQLiteLineageStore
from .package_data import legacy_project_root
from .core_models import (
    AgentProfile,
    Event,
    EventInput,
    EvidenceInvalidState,
    EvidenceKind,
    FileVersion,
    GoldenContract,
    GraphMvpContract,
    LineageAuthority,
    LineageEventType,
    LineageOperation,
    LineageProjection,
    SourceKind,
    SourceReference,
    TaskId,
    TaskSpec,
    TruthKind,
    VerifiedHead,
)

LOCAL_MODEL_ID = "graphene-local-scripted"
_PROJECT_ROOT = legacy_project_root()


class BootstrapError(RuntimeError):
    pass


class BootstrapConfigurationError(BootstrapError):
    pass


class BootstrapConflict(BootstrapError):
    pass


class BootstrapRehydrationRequired(BootstrapConflict):
    pass


@dataclass(frozen=True, slots=True)
class BootstrappedRun:
    runtime_dir: Path
    database_path: Path
    checkout_root: Path
    task: TaskSpec
    profile: AgentProfile
    started_event: Event
    head: VerifiedHead
    projection: LineageProjection
    artifacts: SQLiteArtifactStore = field(repr=False, compare=False)
    store: SQLiteLineageStore = field(repr=False, compare=False)
    service: ScopedApplicationService = field(repr=False, compare=False)
    handle: RuntimeHandle = field(repr=False, compare=False)

    @property
    def run_id(self) -> str:
        return self.handle.run_id

    @property
    def session_id(self) -> str:
        return self.handle.session_id

    @property
    def invocation_id(self) -> str:
        return self.handle.invocation_id

    @property
    def model_id(self) -> str:
        return self.handle.model_id


def _absolute(value: str | Path, *, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise BootstrapConfigurationError(f"{label} must be absolute")
    path = Path(os.path.abspath(path))
    try:
        if any(item.is_symlink() for item in (path, *path.parents)):
            raise BootstrapConfigurationError(f"{label} cannot traverse a symlink")
    except OSError as error:
        raise BootstrapConfigurationError(f"{label} is unavailable") from error
    return path


def _private_directory(path: Path, *, create: bool) -> Path:
    if create:
        if not path.parent.is_dir():
            raise BootstrapConfigurationError("runtime parent must already exist")
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as error:
            raise BootstrapConfigurationError("runtime directory is unavailable") from error
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise BootstrapConfigurationError("runtime directory is unavailable") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise BootstrapConfigurationError(
            "runtime directory must be private and owned by this user"
        )
    return path


def _repository(
    value: str | Path | None,
) -> tuple[Path, GoldenContract, GraphMvpContract, Path, str]:
    root = _absolute(_PROJECT_ROOT if value is None else value, label="repository root")
    if not root.is_dir():
        raise BootstrapConfigurationError("repository root is unavailable")
    golden_path = root / "contracts/golden_path.json"
    graph_path = root / "contracts/graph_mvp.json"
    if (root / "contracts").is_symlink() or any(
        path.is_symlink() or not path.is_file() for path in (golden_path, graph_path)
    ):
        raise BootstrapConfigurationError("repository contracts are unavailable")
    try:
        golden = GoldenContract.model_validate_json(golden_path.read_text())
        graph = GraphMvpContract.model_validate_json(graph_path.read_text())
    except (OSError, ValueError) as error:
        raise BootstrapConfigurationError("repository contracts are invalid") from error
    fixture = root.joinpath(*golden.fixture.root.split("/"))
    cursor = root
    fixture_has_symlink = False
    for part in golden.fixture.root.split("/"):
        cursor /= part
        fixture_has_symlink = fixture_has_symlink or cursor.is_symlink()
    if (
        fixture_has_symlink
        or not fixture.is_dir()
        or fixture.resolve() == root
        or root not in fixture.resolve().parents
        or graph.repo_id != golden.repo_id
    ):
        raise BootstrapConfigurationError("repository fixture binding is invalid")
    try:
        base_sha = fixture_base_sha(golden, fixture)
    except (ExecutionError, OSError) as error:
        raise BootstrapConfigurationError("repository fixture is invalid") from error
    return root, golden, graph, fixture, base_sha


def _database(value: str | Path, repository_root: Path) -> Path:
    database = _absolute(value, label="lineage database")
    runtime = database.parent
    root = Path(database.anchor)
    protected = (Path.home().resolve(), repository_root)
    if (
        runtime == root
        or runtime.parent == root
        or any(runtime == path or runtime in path.parents for path in protected)
    ):
        raise BootstrapConfigurationError("runtime directory is too broad")
    _private_directory(runtime, create=False)
    if database.exists():
        metadata = database.stat(follow_symlinks=False)
        if (
            database.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise BootstrapConflict("runtime database must be a private 0600 file")
        return database
    try:
        descriptor = os.open(
            database,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise BootstrapConflict("runtime database could not be created safely") from error
    return database


def _stable_id(prefix: str, namespace: str) -> str:
    return f"{prefix}_{sha256_hex(f'{prefix}\0{namespace}'.encode())[:24]}"


def _checkout_inventory(checkout: Path) -> set[str]:
    files: set[str] = set()
    pending = [checkout]
    while pending:
        directory = pending.pop()
        try:
            entries = tuple(os.scandir(directory))
        except OSError as error:
            raise BootstrapConflict("runtime checkout inventory is unavailable") from error
        for entry in entries:
            if directory == checkout and entry.name == ".git":
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    raise BootstrapConflict("runtime checkout Git binding is unsafe")
                continue
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise BootstrapConflict("runtime checkout inventory is unavailable") from error
            relative = Path(entry.path).relative_to(checkout).as_posix()
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(Path(entry.path))
            elif stat.S_ISREG(metadata.st_mode):
                files.add(relative)
            else:
                raise BootstrapConflict("runtime checkout contains an unsafe node")
    return files


def _read_checkout_file(
    checkout: Path,
    relative: tuple[str, ...],
    *,
    max_bytes: int,
) -> bytes:
    directory_fd = os.open(
        checkout,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    file_fd: int | None = None
    try:
        for part in relative[:-1]:
            child_fd = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = child_fd
        file_fd = os.open(
            relative[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise BootstrapConflict("runtime checkout file binding is invalid")
        with os.fdopen(file_fd, "rb") as stream:
            file_fd = None
            value = stream.read(max_bytes + 1)
        if len(value) != metadata.st_size:
            raise BootstrapConflict("runtime checkout file changed during read")
        return value
    except OSError as error:
        raise BootstrapConflict("runtime checkout file is unavailable") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)


def _checkout(
    checkout: Path,
    checkout_parent: Path,
    *,
    golden: GoldenContract,
    fixture: Path,
    expected_base_sha: str,
    expected_files: dict[str, bytes],
    max_file_bytes: int,
) -> None:
    _private_directory(checkout_parent, create=True)
    if not checkout.exists():
        try:
            actual_base_sha = _initialize_repository(golden, fixture, checkout)
        except (ExecutionError, OSError) as error:
            raise BootstrapConflict("runtime checkout could not be created") from error
        if actual_base_sha != expected_base_sha:
            raise BootstrapConflict("runtime checkout base is not reproducible")
    if checkout.is_symlink() or not checkout.is_dir():
        raise BootstrapConflict("runtime checkout is unsafe")
    try:
        tracked = _checkout_inventory(checkout)
        actual = {
            path: _read_checkout_file(
                checkout,
                tuple(path.split("/")),
                max_bytes=max_file_bytes,
            )
            for path in sorted(tracked)
        }
        head = _read_checkout_file(checkout, (".git", "HEAD"), max_bytes=128)
        main = _read_checkout_file(
            checkout,
            (".git", "refs", "heads", "main"),
            max_bytes=128,
        )
    except (ExecutionError, OSError) as error:
        raise BootstrapConflict("runtime checkout cannot be verified") from error
    if (
        tracked != set(expected_files)
        or actual != expected_files
        or head != b"ref: refs/heads/main\n"
        or main != f"{expected_base_sha}\n".encode()
    ):
        raise BootstrapConflict("runtime checkout does not match the frozen base")


def _expected_checkout_files(
    *,
    golden: GoldenContract,
    fixture: Path,
    events: tuple[Event, ...],
    artifacts: SQLiteArtifactStore,
) -> dict[str, bytes]:
    try:
        expected = _validate_fixture(golden, fixture)
    except ExecutionError as error:
        raise BootstrapConflict("repository fixture cannot be verified") from error
    for event in events:
        if (
            event.event_type != LineageEventType.TOOL_COMPLETED
            or event.payload.get("operation") != LineageOperation.WRITE_FILE
        ):
            continue
        path = event.payload.get("path")
        state = event.payload.get("state")
        after_id = event.payload.get("after_file_version_id")
        if not isinstance(path, str):
            raise BootstrapConflict("runtime write evidence is malformed")
        if state == "DELETED":
            expected.pop(path, None)
            continue
        reference = None
        value = None
        for candidate in event.references:
            if candidate.kind != EvidenceKind.FILE_VERSION:
                continue
            raw = artifacts.resolve(candidate.kind.value, candidate.id)
            try:
                decoded = json.loads(raw) if raw is not None else None
            except (TypeError, ValueError, UnicodeError):
                continue
            if isinstance(decoded, dict) and decoded.get("file_version_id") == after_id:
                reference, value = candidate, decoded
                break
        if reference is None or value is None:
            raise BootstrapConflict("runtime write evidence is unresolved")
        try:
            content = value.pop("content")
            version = FileVersion.model_validate(
                {**value, "artifact_sha256": reference.sha256}
            )
        except (AttributeError, KeyError, TypeError, ValueError, UnicodeError) as error:
            raise BootstrapConflict("runtime file-version evidence is malformed") from error
        if (
            not isinstance(content, str)
            or version.path != path
            or version.file_version_id != after_id
            or version.content_sha256 != sha256_hex(content.encode())
            or version.byte_count != len(content.encode())
            or version.line_count != len(content.splitlines())
        ):
            raise BootstrapConflict("runtime file-version evidence was substituted")
        expected[path] = content.encode()
    return expected


def _task_and_profile(
    golden: GoldenContract,
    graph: GraphMvpContract,
    task_id: TaskId | str,
    profile_id: str,
) -> tuple[TaskSpec, AgentProfile, tuple[str, ...], tuple[str, ...]]:
    try:
        selected_task_id = TaskId(task_id)
        task = next(item for item in golden.tasks if item.task_id == selected_task_id)
        profile = profile_for_task(graph, selected_task_id)
    except (StopIteration, TypeError, ValueError) as error:
        raise BootstrapConfigurationError("task or profile binding is invalid") from error
    if profile.agent_profile_id != profile_id or task.repo_id != graph.repo_id:
        raise BootstrapConfigurationError("task is not bound to the requested profile")
    fixture_paths = set(golden.fixture.tracked_paths) | set(golden.fixture.mutable_paths)
    read_scope = tuple(
        sorted(
            path
            for path in fixture_paths
            if any(fnmatchcase(path, pattern) for pattern in profile.allowed_paths)
        )
    )
    write_scope = tuple(task.expected_changed_paths)
    if not read_scope or not set(write_scope) <= set(read_scope):
        raise BootstrapConfigurationError("profile cannot satisfy the task scope")
    return task, profile, read_scope, write_scope


def bootstrap_local_run(
    database_path: str | Path,
    *,
    task_id: TaskId | str,
    profile_id: str,
    repository_root: str | Path | None = None,
) -> BootstrappedRun:
    """Create or exactly rehydrate one server-owned, local v2 run."""

    repository, golden, graph, fixture, base_sha = _repository(repository_root)
    task, profile, read_scope, write_scope = _task_and_profile(golden, graph, task_id, profile_id)
    database = _database(database_path, repository)
    runtime = database.parent
    namespace = canonical_json_sha256(
        {
            "database_path": str(database),
            "task_id": task.task_id.value,
            "profile_id": profile.agent_profile_id,
        }
    )
    run_id = _stable_id("run", namespace)
    session_id = _stable_id("session", namespace)
    invocation_id = _stable_id("invocation", namespace)
    try:
        artifacts = SQLiteArtifactStore(database)
        store = SQLiteLineageStore(database, artifact_resolver=artifacts.resolve)
    except (OSError, sqlite3.Error, LineageConflict) as error:
        raise BootstrapConflict("runtime database could not be initialized") from error
    verified = store.verify(run_id)
    if isinstance(verified, EvidenceInvalidState):
        raise BootstrapConflict("runtime lineage evidence is invalid")
    events: list[Event] = []
    after_seq = 0
    while after_seq < verified.seq:
        batch = store.tail(run_id, after_seq, min(256, verified.seq - after_seq))
        if not batch:
            raise BootstrapConflict("runtime run is not an exact bootstrap replay")
        events.extend(batch)
        after_seq = batch[-1].seq
    checkout_parent = runtime / "checkouts"
    checkout = checkout_parent / run_id
    _checkout(
        checkout,
        checkout_parent,
        golden=golden,
        fixture=fixture,
        expected_base_sha=base_sha,
        expected_files=_expected_checkout_files(
            golden=golden,
            fixture=fixture,
            events=tuple(events),
            artifacts=artifacts,
        ),
        max_file_bytes=golden.fixture.max_write_bytes,
    )
    checkout_binding = sha256_hex(str(checkout).encode())
    source_record = {
        "schema_version": 2,
        "action": "run.started",
        "run_id": run_id,
        "task_id": task.task_id.value,
        "repo_id": task.repo_id,
        "base_sha": base_sha,
        "agent_profile_id": profile.agent_profile_id,
        "policy_revision": profile.policy_revision,
        "session_id": session_id,
        "invocation_id": invocation_id,
        "model_id": LOCAL_MODEL_ID,
        "fixture_tree_sha256": golden.fixture.tree_sha256,
        "checkout_binding_sha256": checkout_binding,
        "database_binding_sha256": sha256_hex(str(database).encode()),
    }
    source_artifact = artifacts(EvidenceKind.OPERATOR_REQUEST, source_record)
    source = SourceReference(
        kind=SourceKind.LIFECYCLE_REQUEST,
        id=source_artifact.id,
        sha256=source_artifact.sha256,
    )
    empty = VerifiedHead(
        run_id=run_id,
        seq=0,
        event_sha256=None,
        event_count=0,
    )
    idempotency_key = "bootstrap_" + canonical_json_sha256(source_record)[:32]
    try:
        started = store.append(
            run_id,
            empty,
            idempotency_key,
            EventInput(
                session_id=None,
                invocation_id=None,
                model_id=None,
                tool_call_id=None,
                repo_id=task.repo_id,
                base_sha=base_sha,
                agent_profile_id=profile.agent_profile_id,
                policy_revision=profile.policy_revision,
                event_type=LineageEventType.RUN_STARTED,
                truth_kind=TruthKind.SERVER_DERIVED,
                authority=LineageAuthority.LIFECYCLE_SERVICE,
                references=(),
                source_ref=source,
                payload={"state": "STARTING"},
            ),
        )
    except LineageConflict as error:
        raise BootstrapConflict("runtime run binding conflicts with durable state") from error
    head = store.verify(run_id)
    if isinstance(head, EvidenceInvalidState) or started.seq != 1:
        raise BootstrapConflict("runtime run is not an exact bootstrap replay")

    service = ScopedApplicationService(store, artifacts)
    try:
        handle = service.create_handle(
            run_id=run_id,
            repo_id=task.repo_id,
            base_sha=base_sha,
            agent_profile_id=profile.agent_profile_id,
            policy_revision=profile.policy_revision,
            session_id=session_id,
            invocation_id=invocation_id,
            model_id=LOCAL_MODEL_ID,
            read_scope=read_scope,
            write_scope=write_scope,
            tools=tuple(LineageOperation),
            evidence=(),
            fixed_test_profile=graph.required_test_profile,
            fixture_policy=golden.fixture,
            checkout_root=checkout,
        )
    except RuntimeError as error:
        raise BootstrapRehydrationRequired(
            "rehydration_required: progressed run has uncertain runtime state"
        ) from error
    if verified.seq == 0:
        events = [started]
    elif head != verified:
        raise BootstrapConflict("runtime head changed during bootstrap")
    return BootstrappedRun(
        runtime_dir=runtime,
        database_path=database,
        checkout_root=checkout,
        task=task,
        profile=profile,
        started_event=started,
        head=head,
        projection=reduce_events(tuple(events)),
        artifacts=artifacts,
        store=store,
        service=service,
        handle=handle,
    )


__all__ = [
    "LOCAL_MODEL_ID",
    "BootstrapConfigurationError",
    "BootstrapConflict",
    "BootstrapError",
    "BootstrapRehydrationRequired",
    "BootstrappedRun",
    "bootstrap_local_run",
]
