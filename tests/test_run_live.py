"""`graphene run` while it runs: Ctrl-C hands back what it started, in place and in worktrees; a leaf
the person releases stops its executor; a run that died is swept; a leaf whose needs are done
elsewhere waits until their work is here; git is asked before the write lock; the executor's output
is a tail the person can read while it works; and a leaf that comes back offers its own fix."""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from graphene_debrief import plan
from graphene_debrief import run as R
from graphene_debrief.plan import DONE, OPEN, REVIEW, RUNNING, Caller, Refused
from graphene_debrief.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:aaaa1111", False, "aaaa1111-session")
CLI = [
    sys.executable,
    "-c",
    "import sys; from graphene_debrief.cli import app; sys.argv[0] = 'graphene'; app()",
]
SLOW = """
import pathlib, sys, time
print("reading the repo", flush=True)
pathlib.Path("pid.txt").write_text(__import__("os").getpid().__str__())
time.sleep(60)
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_NODE"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "a.txt").write_text("a\n")
    (root / "b.txt").write_text("b\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


def executor(repo, source: str) -> str:
    script = repo.parent / "executor.py"
    script.write_text(source)
    return f"{sys.executable} {script}"


def leaf(node_id, path, **extra):
    return {"id": node_id, "title": f"leaf {node_id}", "scope": [path], "check": "true", **extra}


def graphene_run(repo, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    env["GRAPHENE_AS"] = "person:alex"
    return subprocess.Popen([*CLI, "run", *args], cwd=repo, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)  # fmt: skip


def wait_for(condition, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


def states(repo):
    with Store.open(repo) as store:
        return {n.id: n.state for n in plan.nodes(store)}


@pytest.mark.parametrize("parallel", ["1", "2"])
def test_ctrl_c_hands_back_what_the_run_started_and_stops_its_executors(repo, parallel):
    """On 22 September a Ctrl-C left a leaf `running` for good, and in worktrees a run kept going."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt")], ALEX)
    run = graphene_run(repo, "--with", executor(repo, SLOW), "--parallel", parallel)
    running = 2 if parallel == "2" else 1
    assert wait_for(lambda: list(states(repo).values()).count(RUNNING) == running), run.stdout
    assert wait_for(lambda: len(R_attempts(repo)) == running)
    pids = [e["detail"]["pid"] for e in R_attempts(repo)]
    run.send_signal(signal.SIGINT)
    said, _ = run.communicate(timeout=30)
    assert run.returncode == 130, said
    assert "stopped. What was running is handed back" in said
    assert set(states(repo).values()) == {OPEN}  # nothing left running, nothing said done
    with Store.open(repo) as store:
        whys = [e["detail"]["why"] for e in store.node_log(kinds=("released",))]
    assert whys and all("stopped (Ctrl-C)" in w for w in whys)
    assert wait_for(lambda: not any(R._alive(p) for p in pids), 15)  # the executors are gone too


def R_attempts(repo):
    with Store.open(repo) as store:
        return store.node_log(kinds=("attempt",))


def test_a_leaf_the_person_releases_stops_its_executor(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    said = []
    worker = threading.Thread(
        target=lambda: R.run_plan(
            Store.open(repo), repo, executor(repo, SLOW), say=said.append, logs=repo / ".graphene" / "runs"
        ),  # fmt: skip
    )
    worker.start()
    assert wait_for(lambda: states(repo)["a"] == RUNNING and len(R_attempts(repo)) == 1)
    started = time.monotonic()
    with Store.open(repo) as store:
        plan.release(store, "a", ALEX, "not this one yet")
    worker.join(timeout=20)
    assert not worker.is_alive() and time.monotonic() - started < 15
    assert any(line.startswith("a handed back by alex: not this one yet") for line in said), said


def test_a_run_that_died_is_swept_and_its_leaf_is_ready_again(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        plan.start(store, "a", Caller("run:claude", False, "s1"), repo)
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        store.log_node(
            "a", plan._now(), "attempt", "run:claude", "s1", None, {"run_pid": dead.pid, "attempt": 1}
        )
        said = []
        R.sweep(store, said.append)
        assert plan.get(store, "a").state == OPEN and "handed back, and it is ready again" in said[0]


def test_a_leaf_whose_need_is_done_but_not_committed_waits_until_it_is(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
        plan.start(store, "a", ALEX, repo)
        (repo / "a.txt").write_text("a, done in place\n")
        plan.finish(store, "a", ALEX)
        b = plan.get(store, "b")
        [away] = plan.not_here(store, b, repo, committed=True)
        assert "a (its work is not committed in" in away and "a.txt" in away
        assert plan.not_here(store, b, repo) == []  # in the same checkout it is there
        git(repo, "commit", "-qam", "a")
        assert plan.not_here(store, b, repo, committed=True) == []


def test_a_need_done_in_a_worktree_and_never_landed_keeps_its_dependant_waiting(repo, tmp_path):
    tree = repo / ".graphene" / "worktrees" / "a"
    git(repo, "worktree", "add", "-q", "-b", "graphene/a", str(tree), "HEAD")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
        plan.start(store, "a", BOT, tree)
        (tree / "a.txt").write_text("a, in its worktree\n")
        plan.finish(store, "a", BOT)
        with pytest.raises(Refused, match=r"b waits on a \(done in its worktree and never landed"):
            plan.start(store, "b", BOT, repo)


def test_git_is_asked_before_the_write_lock_is_taken(repo, monkeypatch):
    """With twenty worktrees on a large repo the lock was held for 4 s, and every hook gave up."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        seen = []
        real = plan.dirty

        def looking(checkout):
            seen.append(store.conn.in_transaction)
            return real(checkout)

        monkeypatch.setattr(plan, "dirty", looking)
        plan.start(store, "a", BOT, repo)
        assert seen and not any(seen)


def test_the_executors_output_is_a_tail_while_it_runs(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    worker = threading.Thread(
        target=lambda: R.run_plan(
            Store.open(repo), repo, executor(repo, SLOW), say=lambda _: None, logs=repo / ".graphene" / "runs"
        ),  # fmt: skip
    )
    worker.start()
    try:
        assert wait_for(lambda: len(R_attempts(repo)) == 1)
        with Store.open(repo) as store:
            node = plan.get(store, "a")
            assert wait_for(lambda: R.tail(R.live(store, node)["log"]) == ["reading the repo"])
            now = R.live(store, node)
            assert now["last"] == "reading the repo" and now["attempt"] == 1 and now["idle"] < 20
    finally:
        with Store.open(repo) as store:
            plan.release(store, "a", ALEX, "enough")
        worker.join(timeout=20)


def test_a_leaf_that_came_back_offers_to_widen_or_to_add_a_sibling(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("c", "c.txt")], ALEX)
        plan.start(store, "a", BOT, repo)
        store.log_node("a", plan._now(), "denied", None, BOT.session_id, None, {"path": "src/util.py"})
        plan.release(store, "a", BOT, "it needs src/util.py, and c must land first")
        keys = [key for key, _, _ in plan.offers(store, plan.get(store, "a"))]
        assert keys == ["w", "b", "n"]
        assert plan.offers(store, plan.get(store, "a"))[2][2] == ["node", "set", "a", "--needs", "c"]
        made = plan.sibling(store, "a", [], ALEX)
        assert made.scope == ["src/util.py"] and plan.get(store, "a").needs == [made.id]
        assert plan.widen(store, "a", [], ALEX).scope == ["a.txt", "src/util.py"]
        with pytest.raises(Refused, match="adding a sibling leaf is the person's"):
            plan.sibling(store, "a", ["x.txt"], BOT)


def test_a_leaf_landed_into_the_checkout_is_not_charged_to_a_node_held_there(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("p", "p.txt"), leaf("a", "a.txt")], ALEX)
        plan.start(store, "p", BOT, repo)
        (repo / "a.txt").write_text("landed by a run\n")
        git(repo, "commit", "-qam", "a landed")
        store.log_node("a", plan._now(), "landed", "graphene run", None, None,
                       {"commit": plan.head(repo), "into": str(repo), "paths": ["a.txt"]})  # fmt: skip
        (repo / "p.txt").write_text("p\n")
        assert plan.finish(store, "p", BOT).state == DONE


def test_run_node_names_a_sub_goal_and_means_its_leaves(repo):
    with Store.open(repo) as store:
        plan.propose(
            store, [{"id": "g", "title": "g", "children": [leaf("a", "a.txt"), leaf("b", "b.txt")]}], ALEX
        )
        assert R.leaves_of(store, ["g"]) == ["a", "b"]


def test_a_check_is_run_with_bash(repo):
    passed, _ = plan.run_check("[[ 1 == 1 ]] && set -o pipefail", repo)
    assert passed or not Path("/bin/bash").exists()


def test_a_finished_leaf_the_run_was_stopped_before_it_landed_waits_in_review(repo):
    tree = repo / ".graphene" / "worktrees" / "a"
    git(repo, "worktree", "add", "-q", "-b", "graphene/a", str(tree), "HEAD")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        plan.start(store, "a", BOT, tree)
        (tree / "a.txt").write_text("a, in its worktree\n")
        node = plan.finish(store, "a", BOT)
        said = []
        R.park(store, tree, node, said.append)
        assert plan.get(store, "a").state == REVIEW and "git merge graphene/a" in said[0]
        assert "a, in its worktree" in git(repo, "show", "graphene/a:a.txt")
