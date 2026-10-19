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


# The leaf GRAPHENE_SLOW names waits, before it writes, until GRAPHENE_AFTER (1) leaves have landed in the
# checkout (each lands as a merge), so it lands after them however slow the machine. A sleep of 1 s or 2 s
# was not enough under a loaded suite: the first leaf's landing outlasted it, and the order flipped.
SLOW = """
import os, subprocess, time
node = os.environ["GRAPHENE_NODE"]
if node == os.environ.get("GRAPHENE_SLOW"):
    count = ["git", "-C", os.environ["GRAPHENE_ROOT"], "rev-list", "--merges", "--count", "HEAD"]
    landed = lambda: int(subprocess.run(count, capture_output=True, text=True).stdout or 0)  # noqa: E731
    until = time.monotonic() + 60
    while landed() < int(os.environ.get("GRAPHENE_AFTER", "1")) and time.monotonic() < until:
        time.sleep(0.05)
"""

# a: a.f() returns 2; anything else writes <id>.py. b's check imports a and wants a.f() == 1: a and b
# are green alone and red together. The one GRAPHENE_SLOW names lands second (SLOW).
EXECUTOR = SLOW + """
import pathlib
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
    monkeypatch.setenv("GRAPHENE_ROOT", str(root))
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


# a skeptic's findings: a red already on the target is nobody's fault on the next landing, the checkout may
# move while a merge is checked, a failing check says what it said, and a sandboxed leaf is not run here.
LIB = "def f():\n    return 1\n"
CHECK_A = (
    "import pathlib, lib\nassert pathlib.Path('a.txt').exists()\n"
    "assert lib.f() == 1, 'lib.f() changed under a'\n"
)
WRITES = SLOW + """
import pathlib
if node == "c":
    pathlib.Path("lib.py").write_text("def f():\\n    return 2\\n")
else:
    pathlib.Path(node + ".txt").write_text("done\\n")
"""


def small_repo(tmp_path, monkeypatch, leaves, slow=""):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "x.txt").write_text("x\n")
    (root / "lib.py").write_text(LIB)
    (root / "check_a.py").write_text(CHECK_A)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHENE_SLOW", slow)
    monkeypatch.setenv("GRAPHENE_ROOT", str(root))
    (tmp_path / "ex.py").write_text(WRITES)
    with Store.open(root) as store:
        plan.propose(store, leaves, ALEX)
    return root, f"{sys.executable} {tmp_path / 'ex.py'}"


def test_a_check_already_red_on_the_target_is_not_held_against_the_next_leaf(tmp_path, monkeypatch):
    """c (cut after a landed) breaks a's check and lands, the target not having moved under it. b (cut
    before a) is then checked on a merge where a's check is red with or without b: it lands, and the run
    says whose red it was already."""
    check_a = f"{sys.executable} check_a.py"
    leaves = [
        {"id": "a", "title": "a", "scope": ["a.txt"], "check": check_a},
        {"id": "b", "title": "b", "scope": ["b.txt"], "check": "test -f b.txt"},
        {"id": "c", "title": "c", "scope": ["lib.py"], "check": "grep -q 'return 2' lib.py", "needs": ["a"]},
    ]
    root, executor = small_repo(tmp_path, monkeypatch, leaves, slow="b")
    monkeypatch.setenv("GRAPHENE_AFTER", "2")  # b lands after a and c
    said: list[str] = []
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=said.append)
    with Store.open(root) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {"a": DONE, "b": DONE, "c": DONE}
        on_merge = store.node_log("b", ("landed",))[-1]["detail"]["on_merge"]
    head = git(root, "rev-parse", "HEAD~1").strip()  # the target b's merge was checked on top of
    assert any(f"a's check `{check_a}` already fails on {head[:8]}" in s for s in said), said
    # what passed on the merge: b's own, then c's (landed since b was cut); not the red that was there
    assert on_merge == ["test -f b.txt", "grep -q 'return 2' lib.py"]


def test_the_checkout_moving_while_a_merge_is_checked_is_checked_again(tmp_path, monkeypatch):
    """A commit of the person's, made while d's merge was being checked, would have landed unchecked."""
    d_check = "test -f d.txt && test ! -f bad.txt"
    leaves = [{"id": "e", "title": "e", "scope": ["e.txt"], "check": "test -f e.txt"},
              {"id": "d", "title": "d", "scope": ["d.txt"], "check": d_check}]  # fmt: skip
    root, executor = small_repo(tmp_path, monkeypatch, leaves, slow="d")
    real = plan.run_check

    def run_check(command, checkout, leave_out=(), at=None):
        out = real(command, checkout, leave_out, at)
        if at and not (root / "bad.txt").exists():  # your commit, while the merge is checked
            (root / "bad.txt").write_text("x\n")
            git(root, "add", "bad.txt")
            git(root, "commit", "-qm", "the person commits while the merge is checked")
        return out

    monkeypatch.setattr(plan, "run_check", run_check)
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=lambda _: None)
    with Store.open(root) as store:
        states = {n.id: n.state for n in plan.nodes(store)}
        assert not store.node_log("d", ("landed",))
    assert states == {"e": DONE, "d": REVIEW}  # parked: on the merge that would have landed, d's check is red
    assert subprocess.run(d_check, shell=True, cwd=root).returncode != 0  # the checkout has what you made


def test_a_failing_check_on_the_merge_says_what_it_said(tmp_path, monkeypatch):
    root, executor = repo_with(tmp_path, monkeypatch, [A, B], "b")
    said: list[str] = []
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=said.append)
    told = next(s for s in said if s.startswith("b passed and did not land"))
    assert "a.f() changed under b" in told, told


def test_a_leaf_that_ran_in_a_sandbox_is_not_checked_on_the_host(tmp_path, monkeypatch):
    from graphene_map import run

    monkeypatch.setattr(run, "_in_sandbox", lambda store, node: node.id == "d")
    root, executor = repo_with(tmp_path, monkeypatch, [C, D], "d")
    ran = counted(monkeypatch)
    said: list[str] = []
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=said.append)
    with Store.open(root) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {"c": DONE, "d": DONE}
    assert not [cmd for cmd, at in ran if at]  # d's merge was not checked here, nor c's check on it
    assert "d: not checked on the merge: it ran in a sandbox, and its check runs there" in said
