"""`graphene run --parallel`: ready leaves at once, a worktree each, landed in the checkout the run was
started from when the merge is clean. The executor is a script that says when and where it ran."""

import json
import os
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


def test_more_leaves_than_workers_every_one_lands(repo):
    """A review ran 8 leaves on 4 workers: 3 were refused over a sibling's file that Graphene itself
    had merged meanwhile. A leaf that starts after another has landed must not answer for it."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf(f"n{k}") for k in range(8)], ALEX)
    done, ran, said = go(repo, workers=3)
    assert sorted(n.id for n in done) == [f"n{k}" for k in range(8)], said
    assert not any("refused" in line or "did not land" in line for line in said)


def test_the_person_working_in_their_checkout_meanwhile_fails_no_leaf(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a"), leaf("b")], ALEX)
    (repo / "notes.md").write_text("mine, saved while the run was going\n")
    done, ran, said = go(repo)
    assert sorted(n.id for n in done) == ["a", "b"], said
    assert (repo / "notes.md").read_text().startswith("mine")


def test_an_executor_that_commits_its_own_work_still_lands(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a")], ALEX)
    script = repo.parent / "commits.py"
    script.write_text(
        "import os, pathlib, subprocess\n"
        "n = os.environ['GRAPHENE_NODE']\n"
        "pathlib.Path(f'{n}.txt').write_text('x\\n')\n"
        "subprocess.run(['git', 'add', '-A'], check=True)\n"
        "subprocess.run(['git', 'commit', '-qm', 'mine'], check=True)\n"
    )
    said: list[str] = []
    done = run_parallel(
        lambda: Store.open(repo), repo, repo, 2, f"{sys.executable} {script}", say=said.append
    )
    assert [n.id for n in done] == ["a"] and (repo / "a.txt").exists(), said


def test_a_merge_of_the_persons_own_in_progress_is_never_aborted(repo):
    git_in(repo, "checkout", "-qb", "side")
    (repo / "base.txt").write_text("side\n")
    git_in(repo, "commit", "-qam", "side")
    git_in(repo, "checkout", "-q", "-")
    (repo / "base.txt").write_text("main\n")
    git_in(repo, "commit", "-qam", "main")
    subprocess.run(["git", "-C", str(repo), "merge", "side"], capture_output=True)  # conflicts, on purpose
    (repo / "base.txt").write_text("MY CAREFUL RESOLUTION\n")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a")], ALEX)
    done, ran, said = go(repo)
    assert done == [] and any("a merge of your own is in progress" in line for line in said)
    assert (repo / "base.txt").read_text() == "MY CAREFUL RESOLUTION\n"
    assert (repo / ".git/MERGE_HEAD").exists()


def test_what_a_killed_run_left_behind_does_not_stop_the_next(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a")], ALEX)
        stale = repo / ".graphene/worktrees/a"
        stale.mkdir(parents=True)
        (stale / "junk").write_text("git has lost track of this directory\n")
        plan.start(store, "a", Caller("run:python", False, "dead-session"), stale.parent)  # still "running"
        row = store.node_row("a")
        row["checkout"] = str(stale)
        store.put_node(row)
    (repo / ".graphene/run.lock").write_text("999999")  # a pid nobody has
    done, ran, said = go(repo)
    assert [n.id for n in done] == ["a"], said
    assert any("left running by a run that ended" in line for line in said)


def test_scopes_that_could_meet_are_kept_apart_even_when_no_tracked_file_shows_it():
    from graphene_debrief.run import may_collide

    assert may_collide(["**/*.py"], ["src/**"]) and may_collide(["src"], ["src/api/x.py"])
    assert may_collide(["shared.txt", "x.txt"], ["shared.txt"])
    assert not may_collide(["src/api/**"], ["src/db/**", "tests/db/*.py"])
    assert not may_collide(["a.txt"], ["ab.txt"])


def test_a_detached_head_and_a_second_run_are_refused_in_words(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a")], ALEX)
    (repo / ".graphene/run.lock").write_text(str(os.getpid()))  # a run that is alive: this process
    with pytest.raises(plan.Refused, match="another `graphene run --parallel` is going"):
        go(repo)
    (repo / ".graphene/run.lock").unlink()
    git_in(repo, "checkout", "-q", "--detach")
    with pytest.raises(plan.Refused, match="on no branch"):
        go(repo)
