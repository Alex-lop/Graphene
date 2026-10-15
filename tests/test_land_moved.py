"""A leaf lands only what passes on the tree it lands on: when the target has moved since the leaf's
base, its check and the checks of what the run landed since then run on the merge before it lands."""

import subprocess
import sys

import pytest

from graphene_map import plan
from graphene_map.plan import DONE, REVIEW
from graphene_map.run import run_parallel
from graphene_map.store import Store

ALEX = plan.Caller("alex", True)


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


# a: a.f() returns 2; anything else writes <id>.py. b's check imports a and wants a.f() == 1: a and b
# are green alone and red together. The one GRAPHENE_SLOW names sleeps first, so it lands second.
EXECUTOR = """
import os, pathlib, time
node = os.environ["GRAPHENE_NODE"]
if node == os.environ.get("GRAPHENE_SLOW"):
    time.sleep(1)
if node == "a":
    pathlib.Path("a.py").write_text("def f():\\n    return 2\\n")
else:
    pathlib.Path(node + ".py").write_text("x = 1\\n")
"""

A = {"id": "a", "title": "a returns 2", "scope": ["a.py"], "check": "grep -q 'return 2' a.py"}
B = {"id": "b", "title": "b exists", "scope": ["b.py"], "check": f"{sys.executable} check_b.py"}
C = {"id": "c", "title": "c exists", "scope": ["c.py"], "check": "test -f c.py"}
D = {"id": "d", "title": "d exists", "scope": ["d.py"], "check": "test -f d.py"}


def repo_with(tmp_path, monkeypatch, leaves, slow=""):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "a.py").write_text("def f():\n    return 1\n")
    (root / "check_b.py").write_text("import a\nassert a.f() == 1, 'a.f() changed under b'\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHENE_SLOW", slow)
    (tmp_path / "ex.py").write_text(EXECUTOR)
    with Store.open(root) as store:
        plan.propose(store, leaves, ALEX)
    return root, f"{sys.executable} {tmp_path / 'ex.py'}"


def counted(monkeypatch) -> list[tuple[str, str | None]]:
    """Every check run, as (command, the commit it ran at)."""
    ran, real = [], plan.run_check

    def run_check(command, checkout, leave_out=(), at=None):
        ran.append((command, at))
        return real(command, checkout, leave_out, at)

    monkeypatch.setattr(plan, "run_check", run_check)
    return ran


@pytest.mark.parametrize("slow", ["a", "b"])
def test_two_leaves_green_alone_and_red_together_never_land_a_red_tree(tmp_path, monkeypatch, slow):
    """Each passes on its own base; landed together, b's check fails. Whichever lands second is
    checked on the merge, with the checks of what already landed, and parks: a landing second passes
    its own check, and only b's, run again, says the tree is red."""
    root, executor = repo_with(tmp_path, monkeypatch, [A, B], slow)
    said: list[str] = []
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=said.append)
    with Store.open(root) as store:
        states = {n.id: n.state for n in plan.nodes(store)}
    first = "b" if slow == "a" else "a"
    assert states == {first: DONE, slow: REVIEW}
    landed = A if first == "a" else B  # and the tree it landed is green by its check
    assert subprocess.run(landed["check"], shell=True, cwd=root).returncode == 0
    head = git(root, "rev-parse", "HEAD").strip()
    told = next(s for s in said if s.startswith(f"{slow} passed and did not land"))
    assert f"b's check `{B['check']}` fails on top of {head[:8]}" in told, said
    assert f"graphene/{slow}" in told


def test_a_leaf_whose_target_moved_lands_once_its_check_and_the_landed_ones_pass_on_the_merge(
    tmp_path, monkeypatch
):
    root, executor = repo_with(tmp_path, monkeypatch, [C, D], "d")
    ran = counted(monkeypatch)
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=lambda _: None)
    with Store.open(root) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {"c": DONE, "d": DONE}
        landed = store.node_log("d", ("landed",))[-1]["detail"]
    assert landed["on_merge"] == ["test -f d.py", "test -f c.py"]
    assert [cmd for cmd, at in ran if at] == ["test -f d.py", "test -f c.py"]
    assert len(ran) == 4  # c's and d's own, then both on d's merge


def test_a_leaf_whose_target_has_not_moved_lands_with_no_second_check(tmp_path, monkeypatch):
    root, executor = repo_with(tmp_path, monkeypatch, [C, D])
    ran = counted(monkeypatch)
    run_parallel(lambda: Store.open(root), root, root, 1, executor, say=lambda _: None)
    with Store.open(root) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {"c": DONE, "d": DONE}
        assert all("on_merge" not in e["detail"] for e in store.node_log(None, ("landed",)))
    assert ran == [("test -f c.py", None), ("test -f d.py", None)]


def test_a_git_that_cannot_make_the_merge_aside_lands_unchecked_and_says_so(tmp_path, monkeypatch):
    from graphene_map import run

    real = run._git

    def old_git(where, *args, ok=False):  # git before 2.38: no merge-tree --write-tree
        if args[:2] == ("merge-tree", "--write-tree"):
            return subprocess.CompletedProcess(args, 129, "", "usage: git merge-tree <base> <b1> <b2>\n")
        return real(where, *args, ok=ok)

    monkeypatch.setattr(run, "_git", old_git)
    root, executor = repo_with(tmp_path, monkeypatch, [C, D], "d")
    said: list[str] = []
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=said.append)
    with Store.open(root) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {"c": DONE, "d": DONE}
    told = "d: not checked on the merge: `git merge-tree --write-tree` (git 2.38) failed: usage:"
    assert told in "\n".join(said)


def test_the_merge_runs_the_checks_of_what_landed_since_the_leaf_was_cut_and_no_older(tmp_path, monkeypatch):
    """a landed before c was cut, so c is already on top of it; b landed after. A run of n leaves does
    not run n checks on every merge: c's own and b's."""
    import types

    from graphene_map import run

    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "x.txt").write_text("x\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    (root / "a.txt").write_text("a\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "a landed")
    a_at = git(root, "rev-parse", "HEAD").strip()
    git(root, "switch", "-qc", "graphene/c")  # c is cut on top of a
    (root / "c.txt").write_text("c\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "c")
    git(root, "switch", "-q", "main")
    (root / "b.txt").write_text("b\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "b landed")
    b_at = git(root, "rev-parse", "HEAD").strip()
    ran: list[tuple[str, str, str]] = [("check a", "a", a_at), ("check b", "b", b_at)]
    seen: list[str] = []

    def run_check(command, checkout, leave_out=(), at=None):
        seen.append(command)
        return True, "", []

    monkeypatch.setattr(plan, "run_check", run_check)
    node = types.SimpleNamespace(id="c", check="check c")
    said: list[str] = []
    done = run._red_on_merge(root, "graphene/c", b_at, node, ran, [], said.append)
    assert seen == ["check c", "check b"] and done == seen and not said
