"""`graphene run --parallel`: ready leaves at once, a worktree each, landed in the checkout the run was
started from when the merge is clean. The executor is a script that says when and where it ran."""

import json
import subprocess
import sys

import pytest

from graphene_debrief import plan
from graphene_debrief.plan import DONE, REVIEW, Caller
from graphene_debrief.run import run_parallel
from graphene_debrief.store import Store

ALEX = Caller("alex", True)
WORKER = """
import json, os, pathlib, sys, time
node, here = os.environ["GRAPHENE_NODE"], pathlib.Path.cwd()
began = time.time()
time.sleep(0.6)
seen = sorted(p.name for p in here.glob("*.txt"))
(here / f"{node}.txt").write_text(f"{node} saw {seen}\\n")
with open(sys.argv[1], "a") as log:
    log.write(json.dumps({"node": node, "cwd": str(here), "began": began, "ended": time.time()}) + "\\n")
"""


def git_in(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
        ).stdout

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "base.txt").write_text("base\n")
    git("add", "-A")
    git("commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


def go(repo, workers=3, **kw):
    script = repo.parent / "worker.py"
    script.write_text(WORKER)
    said: list[str] = []
    command = f"{sys.executable} {script} {repo.parent / 'times.log'}"
    done = run_parallel(lambda: Store.open(repo), repo, repo, workers, command, say=said.append, **kw)
    ran = [json.loads(line) for line in (repo.parent / "times.log").read_text().splitlines()]
    return done, {r["node"]: r for r in ran}, said


def leaf(node_id, **extra):
    return {"id": node_id, "title": f"write {node_id}", "scope": [f"{node_id}.txt"],
            "check": f"test -s {node_id}.txt", **extra}  # fmt: skip


def test_leaves_run_at_once_in_their_own_worktrees_land_as_merges_and_done_rolls_up_here(repo):
    tree = [
        {"id": "both", "title": "a and b together", "check": "test -s a.txt -a -s b.txt",
         "children": [leaf("a"), leaf("b")]},
        leaf("c", needs=["both"]),
    ]  # fmt: skip
    with Store.open(repo) as store:
        plan.set_goal(store, "three files", ALEX)
        plan.propose(store, tree, ALEX)
    done, ran, said = go(repo)
    assert [n.id for n in done] == ["a", "b", "c"] or [n.id for n in done] == ["b", "a", "c"]
    assert ran["a"]["began"] < ran["b"]["ended"] and ran["b"]["began"] < ran["a"]["ended"]  # at once
    assert ran["a"]["cwd"] != ran["b"]["cwd"] and ".graphene/worktrees/a" in ran["a"]["cwd"]
    assert "a.txt" not in (repo / "b.txt").read_text()  # neither saw the other's file being written
    # c waited for the sub-goal, which was done only here, after both had landed and its check passed
    assert ran["c"]["began"] > max(ran["a"]["ended"], ran["b"]["ended"])
    assert "a.txt" in (repo / "c.txt").read_text() and "b.txt" in (repo / "c.txt").read_text()
    with Store.open(repo) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == dict.fromkeys(("both", "a", "b", "c"), DONE)
        # the sub-goal's check ran once, after BOTH had landed: a real run found it running after the
        # first landing, without the sibling that was done in its worktree and not yet here
        assert [e["kind"] for e in store.node_log("both")] == ["added", "check_passed", "rolled_up"]
        assert store.node_log("a", ("landed",))
    log = git_in(repo, "log", "--format=%s%n%b")
    assert (
        "write a (a)" in log
        and "Graphene-Node: a" in log
        and "Why: three files > a and b together (both)" in log
    )
    assert git_in(repo, "status", "--porcelain") == "" and not (repo / ".graphene/worktrees/a").exists()
    assert "graphene/" not in git_in(repo, "branch")


def test_leaves_whose_scopes_overlap_are_never_in_flight_together_so_both_land(repo):
    shared = {"scope": ["shared.txt", "x.txt"], "check": "true"}
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "x", "title": "x", **shared}, {"id": "y", "title": "y", **shared}], ALEX)
    script = repo.parent / "w2.py"
    script.write_text(WORKER.replace('(here / f"{node}.txt")', '(here / "shared.txt")'))
    said = []
    command = f"{sys.executable} {script} {repo.parent / 'times.log'}"
    done = run_parallel(lambda: Store.open(repo), repo, repo, 2, command, say=said.append)
    lines = (repo.parent / "times.log").read_text().splitlines()
    ran = {r["node"]: r for r in map(json.loads, lines)}
    assert len(done) == 2 and ran["y"]["began"] > ran["x"]["ended"]  # one after the other
    assert (repo / "shared.txt").read_text().startswith("y saw")  # y wrote on top of x's, landed
    assert not any("did not land" in line for line in said)


def test_when_the_persons_own_work_is_in_the_way_nothing_of_theirs_is_touched_and_the_leaf_waits(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a"), leaf("after", needs=["a"])], ALEX)
    (repo / "a.txt").write_text("mine, uncommitted\n")  # the person is working here too
    done, ran, said = go(repo)
    assert done == [] and "after" not in ran  # what needs it waits with it
    assert (repo / "a.txt").read_text() == "mine, uncommitted\n"
    assert any("did not land" in s and "git merge graphene/a" in s and "node signoff a" in s for s in said)
    with Store.open(repo) as store:
        assert plan.get(store, "a").state == REVIEW
        assert store.node_log("a", ("unlanded",))[-1]["detail"]["branch"] == "graphene/a"
    assert "graphene/a" in git_in(repo, "branch")  # the work is kept, on its branch
