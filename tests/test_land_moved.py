"""A leaf lands only what passes on the tree it lands on: when the target has moved since the leaf's
base, its check and the checks of what the run already landed run on the merge before it lands."""

import subprocess

from graphene_map import plan


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def test_a_check_at_a_commit_runs_on_that_commits_tree_and_not_the_checkouts(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "x.txt").write_text("one\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "one")
    git(root, "switch", "-qc", "other")
    (root / "x.txt").write_text("two\n")
    git(root, "commit", "-qam", "two")
    other = git(root, "rev-parse", "HEAD").strip()
    git(root, "switch", "-q", "-")
    (root / "x.txt").write_text("three\n")  # the checkout's own change, not the commit's
    assert plan.run_check("grep -q two x.txt", root, at=other)[0]
    assert not plan.run_check("grep -q two x.txt", root)[0]
    assert (root / "x.txt").read_text() == "three\n"
