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
        with pytest.raises(Refused, match="nothing a wanted"):  # its sibling has it now
            plan.widen(store, "a", [], ALEX)
        with pytest.raises(Refused, match="nothing a wanted"):  # recheck 58: asked twice, one sibling
            plan.sibling(store, "a", [], ALEX)
        assert plan.widen(store, "a", ["src/util.py"], ALEX).scope == ["a.txt", "src/util.py"]
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


def test_a_need_built_on_before_it_was_committed_lets_its_dependant_start(repo):
    """Recheck: a need's file changed again after it finished (by a later leaf, the person, a
    formatter) never reaches history as the exact content the need left, and R kept its dependant
    waiting for ever although everything was committed."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
        plan.start(store, "a", ALEX, repo)
        (repo / "a.txt").write_text("a, done in place\n")
        plan.finish(store, "a", ALEX)
        (repo / "a.txt").write_text("a, done in place, and touched up by the person\n")
        assert plan.not_here(store, plan.get(store, "b"), repo, committed=True) != []
        git(repo, "commit", "-qam", "a, touched up")
        assert plan.not_here(store, plan.get(store, "b"), repo, committed=True) == []


def parked(repo, store):
    """Leaf a, done in its worktree and parked before it landed; b needs it."""
    tree = repo / ".graphene" / "worktrees" / "a"
    git(repo, "worktree", "add", "-q", "-b", "graphene/a", str(tree), "HEAD")
    plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
    plan.start(store, "a", BOT, tree)
    (tree / "a.txt").write_text("a, in its worktree\n")
    R.park(store, tree, plan.finish(store, "a", BOT), lambda _: None)
    return tree


def test_a_parked_leaf_merged_by_hand_and_signed_off_on_the_page_lets_its_dependant_start(repo):
    """Recheck: the page's sign-off passed no checkout, so where the hand merge landed was never
    recorded and what needs the leaf waited for ever."""
    from graphene_debrief.server import OPS

    with Store.open(repo) as store:
        parked(repo, store)
        git(repo, "merge", "-q", "graphene/a")
        OPS["signoff"](store, repo, {"id": "a"}, ALEX)
        assert plan.not_here(store, plan.get(store, "b"), repo, committed=True) == []
        assert plan.start(store, "b", BOT, repo).state == RUNNING


def test_signing_off_a_parked_leaf_whose_branch_is_gone_does_not_say_it_was_kept(repo):
    """Recheck: the branch was merged and deleted (by the person, or by a landing stopped late), and
    the sign-off said "graphene/a is not merged here, so it was kept"."""
    from typer.testing import CliRunner

    from graphene_debrief.cli import build

    with Store.open(repo) as store:
        tree = parked(repo, store)
    git(repo, "merge", "-q", "graphene/a")
    git(repo, "worktree", "remove", "--force", str(tree))
    git(repo, "branch", "-D", "graphene/a")
    said = CliRunner().invoke(build(), ["node", "signoff", "a"], env={"GRAPHENE_AS": "person:alex"})
    assert said.exit_code == 0 and "a is done" in said.stdout and "kept" not in said.stdout


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


# -- the recheck of the closing review: its regression tests --------------------


# Recheck 0 (fixed)
@pytest.mark.parametrize("act", ["drop", "release"])
def test_a_leaf_let_go_while_its_check_runs_is_not_made_done(repo, monkeypatch, act):
    """Review finding 0: `d` or `x` during a check was overwritten by `done` seconds later."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt")], ALEX)
        plan.start(store, "a", BOT, repo)
        (repo / "a.txt").write_text("a, by its executor\n")
        real = plan.run_check

        def person_acts_meanwhile(command, where):
            plan.drop(store, "a", ALEX) if act == "drop" else plan.release(store, "a", ALEX, "stop")
            return real(command, where)

        monkeypatch.setattr(plan, "run_check", person_acts_meanwhile)
        with pytest.raises(Refused, match="while its check ran"):
            plan.finish(store, "a", BOT)
        assert plan.get(store, "a").state == (plan.DROPPED if act == "drop" else OPEN)


# Recheck 1 (partly)
def test_a_dead_runs_executor_is_stopped_by_the_sweep_and_cannot_finish_the_leaf_later(repo, monkeypatch):
    """Review finding 1: a closed terminal left the executor working; the next run gave the leaf to a
    second one, and the orphan's `graphene node done` finished it."""
    orphan = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    try:
        with Store.open(repo) as store:
            plan.propose(store, [leaf("a", "a.txt")], ALEX)
            plan.start(store, "a", Caller("run:claude", False, "s1"), repo)
            began = R._started(orphan.pid)  # recorded beside the pid, as a run does
            recorded = {"run_pid": dead.pid, "pid": orphan.pid, "pid_start": began, "attempt": 1}
            store.log_node("a", plan._now(), "attempt", "run:claude", "s1", None, recorded)
            R.sweep(store, lambda _: None)
            orphan.wait(timeout=10)  # stopped before the leaf was handed back
            plan.start(store, "a", Caller("run:claude", False, "s2"), repo)
            (repo / "a.txt").write_text("the orphan's work\n")
            monkeypatch.setenv("GRAPHENE_NODE", "a")
            monkeypatch.setenv("GRAPHENE_ATTEMPT", "s1")
            with pytest.raises(Refused, match="is held by"):
                plan.finish(store, "a", plan.caller())
    finally:
        orphan.kill()


# Recheck 2 (partly)
def test_ctrl_c_while_a_leaf_lands_aborts_the_merge_and_parks_the_leaf(repo, monkeypatch):
    """Review finding 2: the leaf stayed `done`, neither landed nor parked, the checkout mid-merge."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
    real = R._git

    def interrupted(where, *args, ok=False):
        if "merge" in args and args[-1] == "graphene/a":  # Ctrl-C lands while git merges (a hook runs)
            real(where, "merge", "--no-ff", "--no-commit", "graphene/a")
            raise KeyboardInterrupt
        return real(where, *args, ok=ok)

    monkeypatch.setattr(R, "_git", interrupted)
    writes_a = executor(repo, "import pathlib; pathlib.Path('a.txt').write_text('a, by its executor\\n')\n")
    with pytest.raises(KeyboardInterrupt):
        R.run_parallel(lambda: Store.open(repo), repo, repo, 2, writes_a, say=lambda _: None)
    assert not (repo / ".git" / "MERGE_HEAD").exists() and git(repo, "status", "--porcelain") == ""
    assert states(repo) == {"a": REVIEW, "b": OPEN}
    assert "a, by its executor" in git(repo, "show", "graphene/a:a.txt")


# Recheck 3 (partly)
def test_a_need_done_and_committed_on_another_branch_is_not_here(repo):
    """Review finding 3: a need committed in another working tree counted as here, and b ran without it."""
    other = repo.parent / "feature"
    git(repo, "worktree", "add", "-q", "-b", "feature", str(other), "HEAD")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
        plan.start(store, "a", ALEX, other)
        (other / "a.txt").write_text("A IS DONE\n")
        plan.finish(store, "a", ALEX)
        git(other, "commit", "-qam", "a, on feature")
        b = plan.get(store, "b")
        [away] = plan.not_here(store, b, repo, committed=True)
        assert away.startswith(f"a (done in {os.path.realpath(other)}") and "a.txt" in away
        git(repo, "merge", "-q", "feature")
        assert plan.not_here(store, b, repo, committed=True) == []


# Recheck 4 (partly)
def test_a_landed_leaf_does_not_excuse_a_held_nodes_own_edit_to_the_same_file(repo):
    """Review finding 4: any path a leaf landed was excused by name, whoever else changed it."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("p", "p.txt"), leaf("a", "a.txt")], ALEX)
        plan.start(store, "p", BOT, repo)
        (repo / "a.txt").write_text("landed by a run\n")
        git(repo, "commit", "-qam", "a landed")
        store.log_node("a", plan._now(), "landed", "graphene run", None, None,
                       {"commit": plan.head(repo), "into": str(repo), "paths": ["a.txt"]})  # fmt: skip
        (repo / "p.txt").write_text("p\n")
        (repo / "a.txt").write_text("landed by a run\nand p's agent, outside its scope\n")
        with pytest.raises(Refused, match=r"changed outside its scope \(p.txt\): a.txt"):
            plan.finish(store, "p", BOT)


# Recheck 5 (partly)
@pytest.mark.parametrize("parallel", ["1", "2"])
def test_a_with_that_cannot_be_read_is_refused_before_anything_starts(repo, parallel):
    """Review finding 5: bad quoting in --with was a traceback, and --parallel had cut a worktree."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    run = graphene_run(repo, "--with", "my-agent --system \"it's fine", "--parallel", parallel)
    said, _ = run.communicate(timeout=30)
    assert run.returncode == 1 and "cannot be read as a command: No closing quotation" in said
    assert "ValueError" not in said and states(repo) == {"a": OPEN}
    assert len(git(repo, "worktree", "list").splitlines()) == 1


# Recheck 6 (partly)
def test_a_parked_leaf_merged_by_hand_and_signed_off_lets_its_dependant_start(repo):
    """Review finding 6: the printed recipe (`git merge graphene/a`, then signoff) left b waiting for ever."""
    tree = repo / ".graphene" / "worktrees" / "a"
    git(repo, "worktree", "add", "-q", "-b", "graphene/a", str(tree), "HEAD")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
        plan.start(store, "a", BOT, tree)
        (tree / "a.txt").write_text("a, in its worktree\n")
        R.park(store, tree, plan.finish(store, "a", BOT), lambda _: None)
        git(repo, "merge", "-q", "graphene/a")
        plan.signoff(store, "a", ALEX, checkout=repo)
        assert plan.not_here(store, plan.get(store, "b"), repo, committed=True) == []
        assert plan.start(store, "b", BOT, repo).state == RUNNING


# Recheck 7 (partly)
def test_a_leaf_a_live_parallel_run_has_just_started_is_not_swept(repo):
    """Finding 7: another run's sweep took a leaf started in its worktree before its attempt was logged."""
    tree = repo / ".graphene" / "worktrees" / "a"
    git(repo, "worktree", "add", "-q", "-b", "graphene/a", str(tree), "HEAD")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        plan.start(store, "a", Caller("run:claude", False, "s1"), tree)
        lock = repo / ".graphene" / "run.lock"
        lock.write_text(str(os.getppid()))  # a live `graphene run --parallel` holds the repo
        said = []
        R.sweep(store, said.append, repo)
        assert plan.get(store, "a").state == RUNNING and said == []
        lock.unlink()  # its run gone: now it is swept
        R.sweep(store, said.append, repo)
        assert plan.get(store, "a").state == OPEN and "handed back" in said[0]


# Recheck 8 (fixed)
def test_a_second_ctrl_c_while_the_executor_takes_its_term_still_hands_the_leaf_back(repo):
    """Finding 8: in place, a second Ctrl-C during the wait for the executor escaped the hand-back."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    stubborn = (
        "import os, pathlib, signal, sys, time\n"
        "signal.signal(signal.SIGTERM, lambda *a: (time.sleep(3), sys.exit(0)))  # it ends its turn first\n"
        "pathlib.Path('pid.txt').write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    run = graphene_run(repo, "--with", executor(repo, stubborn))
    assert wait_for(lambda: (repo / "pid.txt").exists() and len(R_attempts(repo)) == 1)
    pid = int((repo / "pid.txt").read_text())
    run.send_signal(signal.SIGINT)
    time.sleep(1)
    run.send_signal(signal.SIGINT)  # impatient: the executor has not stopped yet
    said, _ = run.communicate(timeout=30)
    assert run.returncode == 130 and states(repo) == {"a": OPEN}, said
    assert "a handed back: the run was stopped" in said
    assert wait_for(lambda: not R._alive(pid), 15)


# Recheck 10 (fixed)
def test_a_need_committed_here_is_here_while_the_person_edits_the_same_file(repo):
    """Finding 10: a dirty path the need touched was read as the need's own work, uncommitted."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])], ALEX)
        plan.start(store, "a", ALEX, repo)
        (repo / "a.txt").write_text("a, done in place\n")
        plan.finish(store, "a", ALEX)
        git(repo, "commit", "-qam", "a")
        with open(repo / "a.txt", "a") as f:
            f.write("the person, typing on\n")
        assert plan.not_here(store, plan.get(store, "b"), repo, committed=True) == []


# Recheck 13 (fixed)
def test_two_runs_of_one_leaf_in_the_same_second_keep_both_logs(repo, monkeypatch):
    """Finding 13: the log was named to the second, so the second run overwrote the first's."""
    monkeypatch.setattr(plan, "_now", lambda: "2026-09-23T07:43:29.000Z")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        quiet = executor(repo, "import os; print('executor', os.getpid())")
        for _ in range(2):
            R.run_plan(store, repo, quiet, 1, None, lambda _: None, repo / ".graphene" / "runs")
        logs = [e["detail"]["log"] for e in store.node_log("a", ("attempt",))]
    assert len(logs) == 2 and len(set(logs)) == 2
    assert len({Path(p).read_text() for p in logs}) == 2


# Recheck 50 (fixed)
def test_a_leaf_widened_after_a_hand_back_starts_again_over_its_own_first_attempt(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        plan.start(store, "a", BOT, repo)
        (repo / "a.txt").write_text("tried\n")
        (repo / "b.txt").write_text("tried too\n")
        plan.release(store, "a", BOT, "it needs b.txt too")
        plan.widen(store, "a", [], ALEX)  # the offer, taken
        assert plan.start(store, "a", BOT, repo).state == RUNNING


# Recheck 51 (fixed)
def test_the_wait_on_offer_never_names_a_node_that_already_waits_on_the_leaf(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("client", "a.txt"), leaf("server", "b.txt", needs=["client"]),
                             leaf("c", "c.txt")], ALEX)  # fmt: skip
        plan.start(store, "client", BOT, repo)
        plan.release(store, "client", BOT, "the endpoint lives in server, and c must land first")
        [(key, _, argv)] = plan.offers(store, plan.get(store, "client"))
        assert (key, argv) == ("n", ["node", "set", "client", "--needs", "c"])
        assert plan.edit(store, "client", {"needs": ["c"]}, ALEX).needs == ["c"]  # taken, not refused


# Recheck 52 (partly)
def test_a_path_with_braces_is_not_offered_to_a_scope_that_would_refuse_it(repo):
    (repo / "{{slug}}").mkdir()
    (repo / "{{slug}}" / "setup.py").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a cookiecutter template")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("x", "a.txt")], ALEX)
        plan.start(store, "x", BOT, repo)
        (repo / "{{slug}}" / "setup.py").write_text("y\n")
        plan.release(store, "x", BOT, "the template's setup.py had to change")
        assert plan.offers(store, plan.get(store, "x")) == []


# Recheck 56 (partly)
def test_a_persons_edit_asks_git_before_the_write_lock_is_taken(repo, monkeypatch):
    """node add/set and plan propose listed the repo's files under the lock, and an agent's hook that
    came meanwhile gave up after a quarter of a second and let its out-of-scope write through."""
    import sqlite3

    from typer.testing import CliRunner

    from graphene_debrief.cli import build

    def person(*args, input=None):
        return CliRunner().invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"}, input=input)

    assert person("node", "add", "a", "--id", "a", "--scope", "a.txt", "--check", "true").exit_code == 0
    real, seen = plan._git, []

    def asked(checkout, *args):
        db = sqlite3.connect(repo / ".graphene" / "graphene.db", timeout=0, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("ROLLBACK")
            seen.append(False)
        except sqlite3.OperationalError:
            seen.append(True)  # the plan's write lock is held while git is asked
        finally:
            db.close()
        return real(checkout, *args)

    monkeypatch.setattr(plan, "_git", asked)
    assert person("node", "add", "b", "--id", "b", "--scope", "b.txt", "--check", "true").exit_code == 0
    assert person("node", "set", "b", "--scope", "b.txt", "--scope", "c.txt").exit_code == 0
    text = "- c  [c]\n    scope: c.txt\n    check: true\n"
    assert person("plan", "propose", "-", input=text).exit_code == 0
    assert seen and not any(seen)


# Recheck 58 (partly)
def test_a_sibling_once_taken_is_offered_no_more(repo):
    """After `b` the leaf still offered w and b, and the plan said it waited on the person."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        plan.start(store, "a", BOT, repo)
        store.log_node("a", plan._now(), "denied", None, BOT.session_id, None, {"path": "src/util.py"})
        plan.release(store, "a", BOT, "it needs src/util.py")
        assert [k for k, _, _ in plan.offers(store, plan.get(store, "a"))] == ["w", "b"]
        plan.sibling(store, "a", [], ALEX)
        assert plan.offers(store, plan.get(store, "a")) == []


# Recheck 59 (fixed)
def test_a_check_naming_a_file_git_does_not_track_is_warned_about(repo):
    """A worktree cut for --parallel has no untracked file, so that check could never pass there."""
    (repo / "tests").mkdir()
    (repo / "tests" / "test_new.py").write_text("")
    with Store.open(repo) as store:
        plan.propose(store, [leaf("new", "src/**", check="python3 -m pytest -q tests/test_new.py")], ALEX)
        node = plan.get(store, "new")
    assert plan.unreachable(node, plan.tracked(repo), repo) == ["tests/test_new.py (on disk, not committed)"]


# Recheck 69 (fixed)
def test_an_executor_does_not_start_a_run_whose_executor_would_be_any_command(repo):
    assert "Bash(graphene *)" not in R.DEFAULT_WITH and "Bash(graphene node *)" in R.DEFAULT_WITH
    with Store.open(repo) as store:
        plan.propose(store, [leaf("x", "a.txt")], ALEX)
    marker = repo.parent / "marker"
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    said = subprocess.run([*CLI, "run", "--attempts", "1", "--with", f"sh -c 'touch {marker}'"], cwd=repo,
                          env={**env, "GRAPHENE_NODE": "x"}, capture_output=True, text=True)  # fmt: skip
    assert said.returncode == 1 and "does not start runs" in said.stderr and not marker.exists()


def test_a_run_started_where_ctrl_c_is_ignored_still_stops_on_it(repo):
    """A run started from a shell that ignores SIGINT inherited that, and `:stop` never reached it
    (found by CI, where a step starts that way)."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    env["GRAPHENE_AS"] = "person:alex"
    run = subprocess.Popen([*CLI, "run", "--with", executor(repo, SLOW)], cwd=repo, env=env, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN))  # fmt: skip
    assert wait_for(lambda: len(R_attempts(repo)) == 1), run.stdout
    run.send_signal(signal.SIGINT)
    said, _ = run.communicate(timeout=30)
    assert run.returncode == 130, said
    assert states(repo) == {"a": OPEN}
