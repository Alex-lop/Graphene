from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from graphene.orchestration.workspace_audit import (
    WorkspaceAuditError,
    audit_workspace,
    capture_workspace_baseline,
)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "graphene@example.invalid")
    _git(repository, "config", "user.name", "Graphene Test")
    files = {
        "delete.txt": "delete\n",
        "line\nbreak.txt": "before\n",
        "mode.sh": "#!/bin/sh\nexit 0\n",
        "modify.txt": "before\n",
        "rename.txt": "rename\n",
    }
    for name, content in files.items():
        (repository / name).write_text(content)
    _git(repository, "add", "--all", "--")
    _git(repository, "commit", "-qm", "base")
    return repository, _git(repository, "rev-parse", "HEAD")


def test_audit_captures_the_complete_candidate_deterministically(tmp_path: Path) -> None:
    repository, base_sha = _repository(tmp_path)
    baseline = capture_workspace_baseline(repository, base_sha)

    (repository / "modify.txt").write_text("after\n")
    (repository / "line\nbreak.txt").write_text("newline-safe\n")
    (repository / "delete.txt").unlink()
    (repository / "rename.txt").rename(repository / "renamed.txt")
    (repository / "mode.sh").chmod(0o755)
    (repository / "ignored.tmp").write_text("untracked and ignored by policy\n")
    (repository / ".gitignore").write_text("ignored.tmp\n")

    allowed = (
        ".gitignore",
        "delete.txt",
        "ignored.tmp",
        "line\nbreak.txt",
        "mode.sh",
        "modify.txt",
        "rename.txt",
        "renamed.txt",
    )
    first = audit_workspace(repository, baseline, allowed)
    second = audit_workspace(repository, baseline, tuple(reversed(allowed)))

    assert first == second
    assert first.changed_paths == tuple(sorted(allowed))
    assert len(first.patch_sha256) == 64
    assert {change.status for change in first.changes} == {"A", "D", "M", "R100"}
    mode_change = next(
        change for change in first.changes if change.old_path == "mode.sh"
    )
    assert (mode_change.old_mode, mode_change.new_mode) == ("100644", "100755")
    rename = next(change for change in first.changes if change.status == "R100")
    assert (rename.old_path, rename.new_path) == ("rename.txt", "renamed.txt")


def test_audit_rejects_out_of_scope_and_unsafe_paths(tmp_path: Path) -> None:
    repository, base_sha = _repository(tmp_path)
    baseline = capture_workspace_baseline(repository, base_sha)
    (repository / "secret.txt").write_text("must not escape the lease\n")

    with pytest.raises(WorkspaceAuditError, match="outside its allowlist"):
        audit_workspace(repository, baseline, ("modify.txt",))

    for unsafe in (
        ".",
        "/absolute.txt",
        "../escape.txt",
        ".git/config",
        r"C:\escape.txt",
    ):
        with pytest.raises(WorkspaceAuditError, match="unsafe path"):
            audit_workspace(repository, baseline, (unsafe, "secret.txt"))


@pytest.mark.parametrize("kind", ("symlink", "fifo", "casefold", "submodule"))
def test_audit_rejects_unsafe_worktree_nodes(
    tmp_path: Path, kind: str
) -> None:
    repository, base_sha = _repository(tmp_path)
    baseline = capture_workspace_baseline(repository, base_sha)
    if kind == "symlink":
        (repository / "link.txt").symlink_to("modify.txt")
        expected = "symlinks"
    elif kind == "fifo":
        os.mkfifo(repository / "pipe")
        expected = "non-regular"
    elif kind == "casefold":
        (repository / "modify.txt").rename(repository / "MODIFY.txt")
        expected = "case-fold"
    else:
        (repository / "vendor").mkdir()
        (repository / "vendor" / ".git").write_text("gitdir: elsewhere\n")
        expected = "unsafe path"

    with pytest.raises(WorkspaceAuditError, match=expected):
        audit_workspace(repository, baseline, ())


@pytest.mark.parametrize("target", ("config", "hooks"))
def test_audit_rejects_repo_local_git_administration_changes(
    tmp_path: Path, target: str
) -> None:
    repository, base_sha = _repository(tmp_path)
    baseline = capture_workspace_baseline(repository, base_sha)
    git_dir = Path(_git(repository, "rev-parse", "--absolute-git-dir"))
    if target == "config":
        _git(repository, "config", "--local", "graphene.changed", "true")
    else:
        hook = git_dir / "hooks" / "post-checkout"
        hook.write_text("#!/bin/sh\nexit 0\n")

    with pytest.raises(WorkspaceAuditError, match="config or hooks changed"):
        audit_workspace(repository, baseline, ())


def test_baseline_rejects_committed_submodule_entries(tmp_path: Path) -> None:
    repository, base_sha = _repository(tmp_path)
    _git(repository, "update-index", "--add", "--cacheinfo", f"160000,{base_sha},vendor")
    _git(repository, "commit", "-qm", "add gitlink")

    with pytest.raises(WorkspaceAuditError, match="submodules"):
        capture_workspace_baseline(repository, _git(repository, "rev-parse", "HEAD"))
