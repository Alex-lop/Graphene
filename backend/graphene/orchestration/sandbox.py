from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .models import CommandTemplate


_FIXTURE_ARGV = ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider")
_CONTAINER_ARGV = ("/usr/local/bin/python", *_FIXTURE_ARGV[1:])
_OWNER_LABEL = "graphene.owner"
_EXECUTOR_LABEL = "graphene.executor=oci-v1"
_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,127}\Z")
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_SECRET_NAMES = frozenset(
    {".env", ".netrc", "credentials", "credentials.json", "id_rsa", "id_ed25519"}
)


class SandboxError(RuntimeError):
    pass


class DockerUnavailable(SandboxError):
    pass


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    timeout_seconds: int = 30
    output_bytes: int = 65_536
    input_bytes: int = 4 * 1024 * 1024
    input_files: int = 512
    scan_entries: int = 100_000
    memory_bytes: int = 512 * 1024 * 1024
    tmpfs_bytes: int = 64 * 1024 * 1024
    cpus: float = 1.0
    pids: int = 64

    def __post_init__(self) -> None:
        if not (
            0 < self.timeout_seconds <= 3_600
            and 0 < self.output_bytes <= 16 * 1024 * 1024
            and 0 < self.input_bytes <= 100 * 1024 * 1024
            and 0 < self.input_files <= 10_000
            and 0 < self.scan_entries <= 1_000_000
            and 16 * 1024 * 1024 <= self.memory_bytes <= 16 * 1024**3
            and 1024 * 1024 <= self.tmpfs_bytes <= self.memory_bytes
            and 0 < self.cpus <= 16
            and 1 < self.pids <= 4_096
        ):
            raise ValueError("sandbox limits are outside the supported bounds")


@dataclass(frozen=True, slots=True)
class SandboxResult:
    container_id: str
    image_id: str
    template_id: str
    template_sha256: str
    exit_code: int
    timed_out: bool
    oom_killed: bool
    output: bytes
    output_truncated: bool
    cleanup_complete: bool


def command_template_sha256(template: CommandTemplate) -> str:
    payload = {
        "argv": list(template.argv),
        "cwd": template.cwd,
        "template_id": template.template_id,
        "timeout_seconds": template.timeout_seconds,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_command_template(template: CommandTemplate) -> tuple[str, ...]:
    """Resolve the one reviewed demo template; arbitrary commands fail closed."""

    if template.template_id != "fixture-tests" or tuple(template.argv) != _FIXTURE_ARGV:
        raise SandboxError("command is not the frozen server-owned template")
    if template.cwd is not None:
        _relative_path(str(template.cwd))
    return _CONTAINER_ARGV


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value == "."
        or "\\" in value
        or "\0" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise SandboxError("repository path must be canonical and relative")
    return path


def _validate_owner(owner_id: str) -> None:
    if not _ID.fullmatch(owner_id):
        raise SandboxError("owner identity is invalid")


def _validate_container_id(container_id: str) -> None:
    if not _CONTAINER_ID.fullmatch(container_id):
        raise SandboxError("Docker returned an invalid container ID")


def build_docker_create_argv(
    *,
    docker_bin: Path,
    image_id: str,
    workspace: Path,
    owner_id: str,
    container_name: str,
    command: tuple[str, ...],
    cwd: str | None,
    limits: SandboxLimits,
) -> tuple[str, ...]:
    """Return the complete, deterministic container security configuration."""

    _validate_owner(owner_id)
    if not _ID.fullmatch(container_name):
        raise SandboxError("container name is invalid")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise SandboxError("executor image identity is not immutable")
    if not docker_bin.is_absolute() or not workspace.is_absolute():
        raise SandboxError("Docker and workspace paths must be absolute")
    source = str(workspace)
    if any(character in source for character in ",\0\n\r"):
        raise SandboxError("workspace path cannot be represented safely as a mount")
    workdir = "/workspace" if cwd is None else f"/workspace/{_relative_path(cwd)}"
    if command != _CONTAINER_ARGV:
        raise SandboxError("container command is not the resolved template")

    return (
        str(docker_bin),
        "create",
        "--name",
        container_name,
        "--label",
        f"{_OWNER_LABEL}={owner_id}",
        "--label",
        _EXECUTOR_LABEL,
        "--pull",
        "never",
        "--network",
        "none",
        "--ipc",
        "none",
        "--user",
        "65532:65532",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        str(limits.pids),
        "--memory",
        str(limits.memory_bytes),
        "--memory-swap",
        str(limits.memory_bytes),
        "--cpus",
        str(limits.cpus),
        "--ulimit",
        "nofile=256:256",
        "--stop-timeout",
        "2",
        "--init",
        "--log-driver",
        "none",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={limits.tmpfs_bytes},mode=1777",
        "--mount",
        f"type=bind,source={source},target=/workspace,readonly",
        "--workdir",
        workdir,
        "--env",
        "HOME=/tmp/home",
        "--env",
        "TMPDIR=/tmp",
        "--env",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "--env",
        "PYTHONNOUSERSITE=1",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--env",
        "GIT_CONFIG_GLOBAL=/dev/null",
        "--env",
        "GIT_CONFIG_NOSYSTEM=1",
        image_id,
        *command,
    )


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.full_match(pattern) for pattern in patterns)


def _read_regular_file(root_fd: int, relative: PurePosixPath, limit: int) -> bytes:
    parent_fd = os.dup(root_fd)
    file_fd: int | None = None
    try:
        for part in relative.parts[:-1]:
            child = os.open(
                part,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
            os.close(parent_fd)
            parent_fd = child
        file_fd = os.open(
            relative.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise SandboxError("scoped source is not a bounded regular file")
        with os.fdopen(file_fd, "rb") as stream:
            file_fd = None
            data = stream.read(limit + 1)
        if len(data) != metadata.st_size:
            raise SandboxError("scoped source changed while it was copied")
        return data
    except OSError as error:
        raise SandboxError(
            "scoped source could not be opened without following links"
        ) from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


def materialize_repository_view(
    source: Path,
    destination: Path,
    *,
    scopes: tuple[str, ...],
    exclusions: tuple[str, ...] = (),
    limits: SandboxLimits = SandboxLimits(),
) -> tuple[str, ...]:
    """Copy only scoped regular files into a no-credential, no-symlink view."""

    if source.is_symlink():
        raise SandboxError("repository root cannot be a symlink")
    source = source.resolve(strict=True)
    if not source.is_dir() or not scopes:
        raise SandboxError("repository view requires a directory and explicit scopes")
    if destination.exists() and any(destination.iterdir()):
        raise SandboxError("repository view destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    for pattern in (*scopes, *exclusions):
        if (
            "\\" in pattern
            or "\0" in pattern
            or PurePosixPath(pattern).is_absolute()
            or ".." in PurePosixPath(pattern).parts
        ):
            raise SandboxError("scope pattern is unsafe")

    selected: list[str] = []
    scanned = 0
    pending = [(source, PurePosixPath())]
    while pending:
        current, relative_dir = pending.pop()
        try:
            entries = os.scandir(current)
            with entries:
                for entry in entries:
                    scanned += 1
                    if scanned > limits.scan_entries:
                        raise SandboxError("repository view exceeds the scan limit")
                    relative = (relative_dir / entry.name).as_posix()
                    included = _matches(relative, scopes) and not _matches(
                        relative, exclusions
                    )
                    if entry.is_symlink():
                        if included:
                            raise SandboxError(
                                "symlinks in the repository scope are forbidden"
                            )
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name != ".git":
                            pending.append(
                                (Path(entry.path), relative_dir / entry.name)
                            )
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        if included:
                            raise SandboxError(
                                "repository scope contains a non-regular node"
                            )
                        continue
                    if (
                        ".git" in PurePosixPath(relative).parts
                        or entry.name.lower() in _SECRET_NAMES
                        or not included
                    ):
                        continue
                    selected.append(relative)
        except OSError as error:
            raise SandboxError("repository view could not be scanned safely") from error

    selected.sort()

    if len(selected) > limits.input_files:
        raise SandboxError("repository view exceeds the file limit")
    root_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    total = 0
    try:
        for value in selected:
            data = _read_regular_file(
                root_fd, _relative_path(value), limits.input_bytes - total
            )
            total += len(data)
            if total > limits.input_bytes:
                raise SandboxError("repository view exceeds the byte limit")
            target = destination.joinpath(*PurePosixPath(value).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    finally:
        os.close(root_fd)
    return tuple(selected)


class DockerExecutor:
    def __init__(
        self,
        *,
        image: str = "graphene-executor:py313-pytest",
        docker_bin: str | Path | None = None,
        limits: SandboxLimits = SandboxLimits(),
    ) -> None:
        self.image = image
        self._docker_bin = Path(docker_bin) if docker_bin is not None else None
        self.limits = limits

    def _docker(self) -> Path:
        candidate = self._docker_bin or (
            Path(value) if (value := shutil.which("docker")) else None
        )
        if candidate is None:
            raise DockerUnavailable(
                "Docker is unavailable; container execution is NOT PROVEN"
            )
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise DockerUnavailable(
                "Docker is unavailable; container execution is NOT PROVEN"
            ) from error
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise DockerUnavailable(
                "Docker is unavailable; container execution is NOT PROVEN"
            )
        return resolved

    def _run(
        self, *arguments: str, timeout: float = 5
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                (str(self._docker()), *arguments),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DockerUnavailable(
                "Docker is unavailable; container execution is NOT PROVEN"
            ) from error

    def preflight(self) -> str:
        version = self._run("version", "--format", "{{.Server.Version}}")
        if version.returncode or not version.stdout.strip():
            raise DockerUnavailable(
                "Docker daemon is unavailable; container execution is NOT PROVEN"
            )
        image = self._run("image", "inspect", "--format", "{{.Id}}", self.image)
        image_id = image.stdout.decode(errors="replace").strip()
        if image.returncode or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise DockerUnavailable(
                "executor image is unavailable or unverified; execution is NOT PROVEN"
            )
        return image_id

    def _inspect(self, container_id: str, owner_id: str) -> dict[str, object]:
        _validate_container_id(container_id)
        result = self._run("inspect", container_id)
        if result.returncode:
            raise SandboxError("owned container could not be inspected")
        try:
            document = json.loads(result.stdout)[0]
            actual_id = document["Id"]
            labels = document["Config"]["Labels"]
            state = document["State"]
        except (
            AttributeError,
            IndexError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise SandboxError(
                "Docker returned an invalid container inspection"
            ) from error
        if (
            actual_id != container_id
            or not isinstance(labels, dict)
            or labels.get(_OWNER_LABEL) != owner_id
            or not isinstance(state, dict)
        ):
            raise SandboxError("container ownership binding does not match")
        return state

    def _owned_id_for_name(
        self, name: str, owner_id: str, *, missing_ok: bool = False
    ) -> str | None:
        if not re.fullmatch(r"graphene-[0-9a-f]{24}", name):
            raise SandboxError("owned container name is invalid")
        result = self._run("inspect", name)
        if result.returncode:
            message = result.stderr.decode(errors="replace").lower()
            if missing_ok and (
                "no such object" in message or "no such container" in message
            ):
                return None
            raise SandboxError("owned container name could not be inspected")
        try:
            document = json.loads(result.stdout)[0]
            container_id = document["Id"]
            labels = document["Config"]["Labels"]
            actual_name = document["Name"]
        except (
            AttributeError,
            IndexError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise SandboxError(
                "Docker returned an invalid container inspection"
            ) from error
        _validate_container_id(container_id)
        if (
            actual_name != f"/{name}"
            or not isinstance(labels, dict)
            or labels.get(_OWNER_LABEL) != owner_id
        ):
            raise SandboxError("container ownership binding does not match")
        return container_id

    def cleanup_owned(self, container_id: str, owner_id: str) -> None:
        state = self._inspect(container_id, owner_id)
        if state.get("Running"):
            killed = self._run("kill", container_id)
            if killed.returncode:
                # It may have exited after inspection; ownership is checked again before removal.
                state = self._inspect(container_id, owner_id)
                if state.get("Running"):
                    raise SandboxError("owned container could not be killed")
        self._inspect(container_id, owner_id)
        removed = self._run("rm", container_id)
        if removed.returncode:
            raise SandboxError("owned container could not be removed")

    def _capture(
        self, container_id: str, owner_id: str, timeout_seconds: int
    ) -> tuple[bytes, bool, bool]:
        process = subprocess.Popen(
            (str(self._docker()), "start", "--attach", container_id),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        selector = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_seconds
        output = bytearray()
        timed_out = False
        truncated = False
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65_536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    room = self.limits.output_bytes - len(output)
                    output.extend(chunk[: max(0, room)])
                    if len(chunk) > room:
                        truncated = True
                        break
                if truncated:
                    break
            if timed_out or truncated:
                state = self._inspect(container_id, owner_id)
                if state.get("Running"):
                    self._run("kill", container_id)
        finally:
            selector.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        return bytes(output), truncated, timed_out

    def execute(
        self,
        *,
        source: Path,
        scopes: tuple[str, ...],
        exclusions: tuple[str, ...],
        template: CommandTemplate,
        owner_id: str,
    ) -> SandboxResult:
        _validate_owner(owner_id)
        command = validate_command_template(template)
        if template.timeout_seconds > self.limits.timeout_seconds:
            raise SandboxError("command timeout exceeds the sandbox budget")

        # Preflight precedes materialization so an unavailable daemon never reaches code bytes.
        image_id = self.preflight()
        container_id: str | None = None
        cleanup_complete = False
        with tempfile.TemporaryDirectory(prefix="graphene-oci-view-") as temporary:
            workspace = Path(temporary).resolve() / "workspace"
            materialize_repository_view(
                source,
                workspace,
                scopes=scopes,
                exclusions=exclusions,
                limits=self.limits,
            )
            name = "graphene-" + hashlib.sha256(owner_id.encode()).hexdigest()[:24]
            create_argv = build_docker_create_argv(
                docker_bin=self._docker(),
                image_id=image_id,
                workspace=workspace,
                owner_id=owner_id,
                container_name=name,
                command=command,
                cwd=str(template.cwd) if template.cwd is not None else None,
                limits=self.limits,
            )
            try:
                created = subprocess.run(
                    create_argv,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                recovered_id = self._owned_id_for_name(name, owner_id, missing_ok=True)
                if recovered_id is not None:
                    self.cleanup_owned(recovered_id, owner_id)
                raise
            if created.returncode:
                raise SandboxError("Docker refused the bounded container configuration")
            container_id = created.stdout.decode(errors="replace").strip()
            try:
                _validate_container_id(container_id)
            except SandboxError as error:
                recovered_id = self._owned_id_for_name(name, owner_id)
                assert recovered_id is not None
                self.cleanup_owned(recovered_id, owner_id)
                cleanup_complete = True
                raise SandboxError(
                    "Docker returned an invalid container ID; verified owned container removed"
                ) from error
            try:
                self._inspect(container_id, owner_id)
                output, truncated, timed_out = self._capture(
                    container_id, owner_id, template.timeout_seconds
                )
                state = self._inspect(container_id, owner_id)
                if (
                    not timed_out
                    and not truncated
                    and state.get("Status")
                    not in {
                        "dead",
                        "exited",
                    }
                ):
                    raise SandboxError(
                        "container did not reach a terminal execution state"
                    )
                exit_code = int(state.get("ExitCode", -1))
                oom_killed = state.get("OOMKilled") is True
            finally:
                self.cleanup_owned(container_id, owner_id)
                cleanup_complete = True

        return SandboxResult(
            container_id=container_id,
            image_id=image_id,
            template_id=template.template_id,
            template_sha256=command_template_sha256(template),
            exit_code=exit_code,
            timed_out=timed_out,
            oom_killed=oom_killed,
            output=output,
            output_truncated=truncated,
            cleanup_complete=cleanup_complete,
        )


DockerSandboxExecutor = DockerExecutor
