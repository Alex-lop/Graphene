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


def graphene(repo, *args, session=False):
    """The CLI as the person runs it; ``session``: in a session of its own, as a terminal's job is,
    so a test can send the terminal's Ctrl-C to its whole process group."""
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    env["GRAPHENE_AS"] = "person:alex"
    return subprocess.Popen([*CLI, *args], cwd=repo, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=session)  # fmt: skip


def graphene_run(repo, *args, session=False):
    return graphene(repo, "run", *args, session=session)


def ended(pid):
    """Gone, or a zombie nobody has reaped yet: either way it runs no more."""
    stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
    return not stat.strip() or stat.strip().startswith("Z")


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
        assert "a (not committed where it was done" in away and "a.txt" in away
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


def test_a_hand_back_that_names_what_it_needs_is_offered_exactly_that(repo):
    """The recorded scene: the executor never tried the write; it said which file it needed."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("w", "a.txt")], ALEX)
        plan.start(store, "w", BOT, repo)
        why = "USAGE lives in cli/main.py, outside my scope; test_contract must not change"
        plan.release(store, "w", BOT, why, wants=["cli/main.py"])
        [widen, _sibling] = plan.offers(store, plan.get(store, "w"))
        assert widen[1] == "widen w's scope to cli/main.py"
        assert plan.widen(store, "w", [], ALEX).scope == ["a.txt", "cli/main.py"]


WRITES_A = "import pathlib; pathlib.Path('a.txt').write_text('a, by its executor\\n')\n"
KEPT = "import signal as s, time; s.signal(s.SIGTERM, s.SIG_IGN); print('up', flush=True); time.sleep(30)"


def test_the_sweep_signals_only_the_executor_it_recorded_and_waits_for_it_to_end(repo, monkeypatch):
    """Recheck: the sweep sent TERM to the process group of whatever held a dead run's recorded
    executor pid (after a reboot, anybody's), sent TERM alone, and handed the leaf on at once."""
    monkeypatch.setattr(R, "GRACE", 1)
    bystander = subprocess.Popen(["sleep", "30"], start_new_session=True)  # has the recorded pid now
    orphan = subprocess.Popen([sys.executable, "-c", KEPT], stdout=subprocess.PIPE, start_new_session=True)
    orphan.stdout.readline()  # it ignores TERM from here on
    reaper = threading.Thread(target=orphan.wait)  # as init reaps what a dead run left
    reaper.start()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    try:
        with Store.open(repo) as store:
            plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt")], ALEX)
            for node_id, pid, began in (
                ("a", bystander.pid, "Thu Jan  1 00:00:00 1970"),  # the executor that had it began then
                ("b", orphan.pid, R._started(orphan.pid)),
            ):
                plan.start(store, node_id, Caller("run:claude", False, f"s-{node_id}"), repo)
                recorded = {"attempt": 1, "pid": pid, "pid_start": began, "run_pid": dead.pid}
                store.log_node(node_id, plan._now(), "attempt", "run:claude", f"s-{node_id}", None, recorded)
            said = []
            R.sweep(store, lambda line: said.append((line, R._alive(orphan.pid))), repo)
            assert {n.id: n.state for n in plan.nodes(store)} == {"a": OPEN, "b": OPEN}
        assert [alive for line, alive in said if line.startswith("b ")] == [False]  # ended before b went
        reaper.join(timeout=5)
        assert orphan.returncode == -signal.SIGKILL  # TERM was not enough; KILL was
        with pytest.raises(subprocess.TimeoutExpired):
            bystander.wait(timeout=0.5)  # never signalled
    finally:
        bystander.kill()
        bystander.wait()
        orphan.kill()
        reaper.join()


def test_a_run_lock_is_known_by_its_runs_pid_and_start_so_a_reused_pid_holds_nothing(repo):
    """Recheck: run.lock held a bare pid, so a pid the system had handed to another process since
    still held the repo (and `:stop` would interrupt that process)."""
    bystander = subprocess.Popen(["sleep", "30"])
    lock = repo / ".graphene" / "run.lock"
    lock.parent.mkdir(exist_ok=True)
    try:
        lock.write_text(f"{bystander.pid}\nThu Jan  1 00:00:00 1970\n")  # the run that wrote it is gone
        R._only_run(repo)  # not refused: that pid is no run any more
        assert lock.read_text() == f"{os.getpid()}\n{R._started(os.getpid())}\n"
        assert R.run_holding(repo) == os.getpid()
        lock.write_text(f"{bystander.pid}\n{R._started(bystander.pid)}\n")
        with pytest.raises(Refused, match="another `graphene run --parallel` is going"):
            R._only_run(repo)
    finally:
        bystander.kill()
        bystander.wait()


@pytest.mark.parametrize("sig, parallel", [(signal.SIGTERM, "1"), (signal.SIGHUP, "2")])
def test_a_closed_terminal_or_a_kill_stops_the_run_as_ctrl_c_does(repo, sig, parallel):
    """Recheck: SIGHUP and SIGTERM had no handler: the run died where it stood, its executor worked
    on unattended, the leaf stayed `running`, and a parallel run left run.lock behind."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    run = graphene_run(repo, "--with", executor(repo, SLOW), "--parallel", parallel)
    pid = None
    try:
        assert wait_for(lambda: len(R_attempts(repo)) == 1)
        pid = R_attempts(repo)[0]["detail"]["pid"]
        run.send_signal(sig)
        run.communicate(timeout=30)
        assert run.returncode == 130
        assert states(repo) == {"a": OPEN} and not (repo / ".graphene" / "run.lock").exists()
        assert wait_for(lambda: ended(pid), 15)
    finally:
        run.kill()
        if pid and not ended(pid):
            os.killpg(pid, signal.SIGKILL)


def test_the_sweep_leaves_a_leaf_a_live_run_has_just_taken_again(repo):
    """Recheck: a leaf whose last attempt was an earlier, dead run's was swept in the milliseconds
    after a live run took it again, before its own attempt was written; and the sweep's hand-back
    was a person's, which a live run reads as a stop and kills its executor for."""
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        plan.start(store, "a", Caller("run:claude", False, "old"), repo)
        recorded = {"attempt": 1, "run_pid": dead.pid}
        store.log_node("a", plan._now(), "attempt", "run:claude", "old", None, recorded)
        said = []
        R.sweep(store, said.append, repo)
        assert plan.get(store, "a").state == OPEN and not R._let_go(store, "a")  # not a person's stop
        plan.start(store, "a", Caller("run:claude", False, "new"), repo)  # a live run takes it again
        R.sweep(store, said.append, repo)
        assert plan.get(store, "a").state == RUNNING and len(said) == 1


def test_a_run_started_in_a_linked_worktree_sees_the_parallel_runs_lock(repo, tmp_path):
    """Recheck: `graphene run` in a second worktree swept with that worktree as the root, found no
    run.lock there, and handed back a leaf a live parallel run had just started."""
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "side", str(linked), "HEAD")
    tree = repo / ".graphene" / "worktrees" / "a"
    git(repo, "worktree", "add", "-q", "-b", "graphene/a", str(tree), "HEAD")
    holder = subprocess.Popen(["sleep", "30"])  # the live parallel run
    try:
        with Store.open(repo) as store:
            plan.propose(store, [leaf("a", "a.txt")], ALEX)
            plan.start(store, "a", Caller("run:claude", False, "s1"), tree)  # no attempt written yet
            (repo / ".graphene" / "run.lock").write_text(str(holder.pid))
            R.run_plan(store, linked, "true", only=["a"], say=lambda _: None)
            assert plan.get(store, "a").state == RUNNING
    finally:
        holder.kill()
        holder.wait()


def test_ctrl_c_after_a_leaf_landed_leaves_it_done_and_landed(repo):
    """Recheck: Ctrl-C while the landed leaf's sub-goal check ran parked it: 'landed' then
    'unlanded', in review, told to `git merge` a branch already merged and deleted."""
    started = repo.parent / "g.started"
    a = leaf("a", "a.txt")
    subgoal = {"id": "g", "title": "g", "check": f"touch {started}; sleep 30", "children": [a]}
    with Store.open(repo) as store:
        plan.propose(store, [subgoal, leaf("b", "b.txt", needs=["a"])], ALEX)
    writes_a = executor(repo, WRITES_A)
    run = graphene_run(repo, "--with", writes_a, "--parallel", "2", "--node", "a", session=True)
    try:
        assert wait_for(started.exists, 30)
        os.killpg(run.pid, signal.SIGINT)  # the terminal's Ctrl-C
        said, _ = run.communicate(timeout=30)
    finally:
        run.kill()
    assert run.returncode == 130, said
    assert states(repo) == {"g": OPEN, "a": DONE, "b": OPEN}
    with Store.open(repo) as store:
        assert [e["kind"] for e in store.node_log("a")][-1] == "landed"
    assert (repo / "a.txt").read_text() == "a, by its executor\n"


@pytest.mark.parametrize("hook", ["pre-merge-commit", "post-merge"])
def test_ctrl_c_while_a_merge_hook_runs_undoes_or_keeps_the_merge_as_it_stands(repo, hook):
    """Recheck: stopped in a pre-merge-commit hook, before git wrote MERGE_HEAD, the leaf's file was
    left staged in the person's checkout; stopped in a post-merge hook, after the merge commit, the
    leaf that had landed was parked and told to merge again. And the last line said all was handed
    back and ready again, of a leaf parked in review."""
    started = repo.parent / "hook.started"
    script = repo / ".git" / "hooks" / hook
    script.parent.mkdir(exist_ok=True)
    script.write_text(f"#!/bin/sh\ntouch {started}\nsleep 30\n")
    script.chmod(0o755)
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    run = graphene_run(repo, "--with", executor(repo, WRITES_A), "--parallel", "2", session=True)
    try:
        assert wait_for(started.exists, 30)
        os.killpg(run.pid, signal.SIGINT)  # the terminal's Ctrl-C reaches git and its hook too
        said, _ = run.communicate(timeout=30)
    finally:
        run.kill()
    assert run.returncode == 130, said
    assert git(repo, "status", "--porcelain") == "" and not (repo / ".git" / "MERGE_HEAD").exists()
    last = said.strip().splitlines()[-1]
    if hook == "pre-merge-commit":  # no merge commit: undone here, and the leaf waits in review
        assert states(repo) == {"a": REVIEW} and (repo / "a.txt").read_text() == "a\n"
        assert "a, by its executor" in git(repo, "show", "graphene/a:a.txt")
        assert "ready again, but a: passed, in review" in last, said
    else:  # the merge commit is made: it landed, and stays done
        assert states(repo) == {"a": DONE} and (repo / "a.txt").read_text() == "a, by its executor\n"
        assert last.startswith("stopped. What was running is handed back and ready again;"), said


def test_ctrl_c_inside_a_landing_never_aborts_the_persons_own_merge(repo, monkeypatch):
    """Recheck: any Ctrl-C inside land ran `git merge --abort`, so one that came while the person had
    a merge of their own in progress aborted theirs."""
    git(repo, "checkout", "-q", "-b", "theirs")
    (repo / "b.txt").write_text("theirs\n")
    git(repo, "commit", "-qam", "theirs")
    git(repo, "checkout", "-q", "main")
    (repo / "b.txt").write_text("mine\n")
    git(repo, "commit", "-qam", "mine")
    subprocess.run(["git", "-C", str(repo), "merge", "theirs"], capture_output=True)  # a conflict: theirs
    assert (repo / ".git" / "MERGE_HEAD").exists()
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    real = R._git

    def interrupted(where, *args, ok=False):
        if args[0] == "rev-parse" and "MERGE_HEAD" in args:  # the Ctrl-C lands as land looks for a merge
            raise KeyboardInterrupt
        return real(where, *args, ok=ok)

    monkeypatch.setattr(R, "_git", interrupted)
    with pytest.raises(KeyboardInterrupt):
        R.run_parallel(lambda: Store.open(repo), repo, repo, 2, executor(repo, WRITES_A), say=lambda _: None)
    assert (repo / ".git" / "MERGE_HEAD").exists()  # theirs, still theirs to finish
    assert states(repo) == {"a": REVIEW}


def test_a_stopped_run_starts_no_executor(repo):
    """Recheck: a worker did not look at the stop before it started an executor: one was launched
    0.04 s after the Ctrl-C, when the last attempt's check had failed."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        stop = R.Stop()
        stop.event.set()
        with pytest.raises(KeyboardInterrupt):
            R.run_node(store, "a", repo, executor(repo, SLOW), 3, lambda _: None, None, stop)
        assert store.node_log("a", ("attempt",)) == [] and plan.get(store, "a").state == OPEN


@pytest.mark.parametrize("parallel", ["1", "2"])
def test_a_stop_during_a_check_ends_it_and_all_it_started_and_is_no_failed_check(repo, parallel):
    """Recheck: in place, a stop killed the check's bash and not its process group, and its `sleep`
    outlived the run; in parallel, the terminal's Ctrl-C killed the check, which was recorded as the
    executor's failed check, and a second attempt was started after the stop."""
    started = repo.parent / "check.started"
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt", check=f"sleep 30 & echo $! > {started}; wait")], ALEX)
    run = graphene_run(repo, "--with", executor(repo, WRITES_A), "--parallel", parallel, session=True)
    sleeper = None
    try:
        assert wait_for(lambda: started.exists() and started.read_text().strip(), 30)
        sleeper = int(started.read_text())
        if parallel == "1":
            run.send_signal(signal.SIGINT)  # to the run alone, as `:stop` in `graphene watch` sends it
        else:
            os.killpg(run.pid, signal.SIGINT)  # the terminal's Ctrl-C, to its whole process group
        said, _ = run.communicate(timeout=30)
        assert run.returncode == 130, said
        assert wait_for(lambda: ended(sleeper), 10)
        with Store.open(repo) as store:
            kinds = [e["kind"] for e in store.node_log("a")]
        assert "check_failed" not in kinds and kinds.count("attempt") == 1 and states(repo) == {"a": OPEN}
    finally:
        run.kill()
        if sleeper and not ended(sleeper):
            os.kill(sleeper, signal.SIGKILL)


@pytest.mark.parametrize("words", [["ask", "add a b file"], ["node", "split", "a"]])
def test_a_planners_with_that_cannot_be_read_is_refused_in_one_line(repo, words):
    """Recheck: bad quoting in the planner's --with was a traceback (ValueError: No closing quotation)."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    asked = graphene(repo, *words, "--with", "my-planner \"it's")
    said, _ = asked.communicate(timeout=30)
    assert asked.returncode == 1 and "cannot be read as a command: No closing quotation" in said, said
    assert "Traceback" not in said and "ValueError" not in said
