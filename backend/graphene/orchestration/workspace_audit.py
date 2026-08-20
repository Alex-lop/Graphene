from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


class WorkspaceAuditError(RuntimeError):
    """The workspace cannot be proven to match its bounded write lease."""

    pass


@dataclass(frozen=True, slots=True)
class WorkspaceBaseline:
    workspace: str
    base_sha: str
    git_admin_sha256: str


@dataclass(frozen=True, slots=True)
class WorkspaceChange:
    status: str
    old_path: str | None
    new_path: str | None
    old_mode: str | None
    new_mode: str | None
    old_sha256: str | None
    new_sha256: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceAudit:
    base_sha: str
    changed_paths: tuple[str, ...]
    changes: tuple[WorkspaceChange, ...]
    patch_sha256: str


@dataclass(frozen=True, slots=True)
class _Entry:
    mode: str
    sha256: str


def _git(workspace: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ("git", "-C", os.fspath(workspace), *arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise WorkspaceAuditError("workspace Git operation failed") from error
    if result.returncode:
        raise WorkspaceAuditError("workspace Git operation was rejected")
    return result.stdout


def _git_path(workspace: Path, argument: str) -> Path:
    raw = _git(workspace, "rev-parse", "--path-format=absolute", argument)
    path = Path(os.fsdecode(raw.removesuffix(b"\n")))
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise WorkspaceAuditError("workspace Git metadata is unavailable") from error


def _workspace(workspace: Path) -> Path:
    try:
        metadata = workspace.lstat()
        resolved = workspace.resolve(strict=True)
    except OSError as error:
        raise WorkspaceAuditError("workspace is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise WorkspaceAuditError("workspace root is unsafe")
    top = _git_path(resolved, "--show-toplevel")
    if top != resolved:
        raise WorkspaceAuditError("workspace is not the Git worktree root")
    return resolved


def _safe_path(path: str) -> str:
    posix = PurePosixPath(path)
    windows = PureWindowsPath(path)
    if (
        not path
        or path in {".", ".."}
        or "\0" in path
        or "\\" in path
        or path != posix.as_posix()
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in {"", ".", ".."} for part in posix.parts)
        or any(part in {"", ".", ".."} for part in windows.parts)
        or any(
            part.rstrip(" .").casefold() == ".git"
            for part in (*posix.parts, *windows.parts)
        )
    ):
        raise WorkspaceAuditError("workspace contains an unsafe path")
    return path


def _case_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _reject_case_collisions(paths: tuple[str, ...]) -> None:
    keys: dict[str, str] = {}
    for path in paths:
        other = keys.setdefault(_case_key(path), path)
        if other != path:
            raise WorkspaceAuditError("workspace contains a case-fold path collision")


def _read_regular(path: Path, metadata: os.stat_result) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ) != (metadata.st_dev, metadata.st_ino, metadata.st_size):
                raise WorkspaceAuditError("workspace changed during audit")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                return stream.read()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except OSError as error:
        raise WorkspaceAuditError("workspace file is unavailable") from error


def _current_entries(workspace: Path) -> dict[str, _Entry]:
    entries: dict[str, _Entry] = {}
    all_paths: list[str] = []
    pending = [workspace]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as scan:
                children = sorted(scan, key=lambda item: os.fsencode(item.name))
        except OSError as error:
            raise WorkspaceAuditError("workspace cannot be inventoried") from error
        for child in children:
            if directory == workspace and child.name == ".git":
                metadata = child.stat(follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode) or not (
                    stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
                ):
                    raise WorkspaceAuditError("workspace Git metadata is unsafe")
                continue
            path = Path(child.path)
            relative = _safe_path(path.relative_to(workspace).as_posix())
            all_paths.append(relative)
            metadata = child.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise WorkspaceAuditError("workspace symlinks are not allowed")
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(path)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise WorkspaceAuditError("workspace non-regular nodes are not allowed")
            content = _read_regular(path, metadata)
            entries[relative] = _Entry(
                "100755" if metadata.st_mode & 0o111 else "100644",
                hashlib.sha256(content).hexdigest(),
            )
    _reject_case_collisions(tuple(sorted(all_paths)))
    return entries


def _base_entries(workspace: Path, base_sha: str) -> dict[str, _Entry]:
    entries: dict[str, _Entry] = {}
    records = _git(workspace, "ls-tree", "-r", "-z", "--full-tree", base_sha)
    for record in records.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, kind, object_id = metadata.split(b" ", 2)
        except ValueError as error:
            raise WorkspaceAuditError("base tree inventory is malformed") from error
        path = _safe_path(os.fsdecode(raw_path))
        decoded_mode = mode.decode("ascii")
        if kind != b"blob" or decoded_mode not in {"100644", "100755"}:
            raise WorkspaceAuditError(
                "workspace symlinks or submodules are not allowed"
            )
        content = _git(workspace, "cat-file", "blob", object_id.decode("ascii"))
        entries[path] = _Entry(decoded_mode, hashlib.sha256(content).hexdigest())
    _reject_case_collisions(tuple(sorted(entries)))
    return entries


def _admin_files(workspace: Path) -> tuple[tuple[str, Path], ...]:
    git_dir = _git_path(workspace, "--absolute-git-dir")
    common_dir = _git_path(workspace, "--git-common-dir")
    values = {
        "git-marker": workspace / ".git",
        "common-config": common_dir / "config",
        "common-hooks": common_dir / "hooks",
        "worktree-config": git_dir / "config.worktree",
        "worktree-hooks": git_dir / "hooks",
    }
    return tuple(sorted(values.items()))


def _admin_digest(
    workspace: Path, roots: tuple[tuple[str, Path], ...] | None = None
) -> str:
    records: list[tuple[str, str, str]] = []
    for label, root in roots or _admin_files(workspace):
        try:
            root.lstat()
        except FileNotFoundError:
            records.append((label, "missing", ""))
            continue
        except OSError as error:
            raise WorkspaceAuditError(
                "workspace Git administration is unavailable"
            ) from error
        pending = [(label, root)]
        while pending:
            name, path = pending.pop()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise WorkspaceAuditError("workspace Git administration is unsafe")
            if stat.S_ISDIR(metadata.st_mode):
                records.append(
                    (name, f"directory:{stat.S_IMODE(metadata.st_mode):04o}", "")
                )
                if label != "git-marker":
                    with os.scandir(path) as scan:
                        children = sorted(
                            scan,
                            key=lambda item: os.fsencode(item.name),
                            reverse=True,
                        )
                    pending.extend(
                        (f"{name}/{child.name}", Path(child.path)) for child in children
                    )
            elif stat.S_ISREG(metadata.st_mode):
                content = _read_regular(path, metadata)
                records.append(
                    (
                        name,
                        f"file:{stat.S_IMODE(metadata.st_mode):04o}",
                        hashlib.sha256(content).hexdigest(),
                    )
                )
            else:
                raise WorkspaceAuditError("workspace Git administration is unsafe")
    encoded = json.dumps(sorted(set(records)), separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _resolved_base(workspace: Path, base_sha: str) -> str:
    if not isinstance(base_sha, str) or not base_sha:
        raise WorkspaceAuditError("base commit is invalid")
    resolved = os.fsdecode(
        _git(workspace, "rev-parse", "--verify", f"{base_sha}^{{commit}}")
    ).strip()
    head = os.fsdecode(
        _git(workspace, "rev-parse", "--verify", "HEAD^{commit}")
    ).strip()
    if (
        resolved != head
        or len(resolved) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in resolved)
    ):
        raise WorkspaceAuditError("workspace is not based at the required commit")
    return resolved


def _changes(
    base: dict[str, _Entry], current: dict[str, _Entry]
) -> tuple[WorkspaceChange, ...]:
    changes: list[WorkspaceChange] = []
    shared = set(base) & set(current)
    for path in sorted(shared):
        before, after = base[path], current[path]
        if before != after:
            changes.append(
                WorkspaceChange(
                    "M",
                    path,
                    path,
                    before.mode,
                    after.mode,
                    before.sha256,
                    after.sha256,
                )
            )

    deleted = set(base) - set(current)
    added = set(current) - set(base)
    deleted_by_content: dict[str, list[str]] = {}
    added_by_content: dict[str, list[str]] = {}
    for path in deleted:
        entry = base[path]
        deleted_by_content.setdefault(entry.sha256, []).append(path)
    for path in added:
        entry = current[path]
        added_by_content.setdefault(entry.sha256, []).append(path)
    for digest in sorted(set(deleted_by_content) & set(added_by_content)):
        old_paths = sorted(deleted_by_content[digest])
        new_paths = sorted(added_by_content[digest])
        for old_path, new_path in zip(old_paths, new_paths, strict=False):
            deleted.remove(old_path)
            added.remove(new_path)
            changes.append(
                WorkspaceChange(
                    "R100",
                    old_path,
                    new_path,
                    base[old_path].mode,
                    current[new_path].mode,
                    digest,
                    digest,
                )
            )
    for path in sorted(deleted):
        entry = base[path]
        changes.append(
            WorkspaceChange("D", path, None, entry.mode, None, entry.sha256, None)
        )
    for path in sorted(added):
        entry = current[path]
        changes.append(
            WorkspaceChange("A", None, path, None, entry.mode, None, entry.sha256)
        )
    return tuple(
        sorted(
            changes,
            key=lambda item: (
                item.new_path or item.old_path or "",
                item.old_path or "",
            ),
        )
    )


def capture_workspace_baseline(workspace: Path, base_sha: str) -> WorkspaceBaseline:
    """Bind a verified clean worktree and its local Git administration state."""

    root = _workspace(workspace)
    resolved_base = _resolved_base(root, base_sha)
    if _changes(_base_entries(root, resolved_base), _current_entries(root)):
        raise WorkspaceAuditError("workspace baseline is not clean")
    return WorkspaceBaseline(os.fspath(root), resolved_base, _admin_digest(root))


def audit_workspace(
    workspace: Path,
    baseline: WorkspaceBaseline,
    allowed_paths: tuple[str, ...],
) -> WorkspaceAudit:
    """Return the complete measured candidate or reject anything outside the lease.

    ``patch_sha256`` is the SHA-256 of a canonical manifest binding every old/new
    path, mode, and full-content SHA-256. It does not trust the worktree index.
    """

    if not isinstance(baseline, WorkspaceBaseline):
        raise TypeError("audit_workspace requires a WorkspaceBaseline")
    root = _workspace(workspace)
    if os.fspath(root) != baseline.workspace:
        raise WorkspaceAuditError("workspace identity changed")
    _resolved_base(root, baseline.base_sha)
    if _admin_digest(root) != baseline.git_admin_sha256:
        raise WorkspaceAuditError("workspace Git config or hooks changed")
    allowed = tuple(sorted(_safe_path(path) for path in allowed_paths))
    if len(allowed) != len(set(allowed)):
        raise WorkspaceAuditError("workspace allowlist contains duplicate paths")
    _reject_case_collisions(allowed)
    changes = _changes(_base_entries(root, baseline.base_sha), _current_entries(root))
    changed_paths = tuple(
        sorted(
            {
                path
                for change in changes
                for path in (change.old_path, change.new_path)
                if path is not None
            }
        )
    )
    _reject_case_collisions(changed_paths)
    if not set(changed_paths).issubset(allowed):
        raise WorkspaceAuditError("workspace changed a path outside its allowlist")
    if _admin_digest(root) != baseline.git_admin_sha256:
        raise WorkspaceAuditError("workspace Git config or hooks changed")
    payload = {
        "base_sha": baseline.base_sha,
        "changes": [asdict(change) for change in changes],
    }
    patch_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return WorkspaceAudit(baseline.base_sha, changed_paths, changes, patch_sha256)


__all__ = [
    "WorkspaceAudit",
    "WorkspaceAuditError",
    "WorkspaceBaseline",
    "WorkspaceChange",
    "audit_workspace",
    "capture_workspace_baseline",
]
