# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene state --json --watch`: the snapshot once, at once, then one more line each time the store's own
version moves (a commit, a log row, the run lock coming or going), nothing while nothing changes, and exit 0
when its reader goes or a TERM comes. The editor night's contract, section "The CLI", shape 1."""

import json
import os
import queue
import shutil
import signal
import subprocess
import threading
import time

import pytest
from test_run_live import CLI, leaf, repo  # noqa: F401

from graphene_map import plan
from graphene_map import state as ST
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)


class Stream:
    """The command as an editor runs it: a process, its lines read as they come."""

    def __init__(self, repo, thread=True):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
        env["GRAPHENE_AS"] = "person:alex"
        self.proc = subprocess.Popen([*CLI, "state", "--json", "--watch"], cwd=repo, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # fmt: skip
        self.lines: queue.Queue = queue.Queue()
        if thread:  # a test that closes the pipe itself reads it itself: a close under a blocked read waits
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for text in self.proc.stdout:
            self.lines.put((time.monotonic(), json.loads(text)))

    def next(self, seconds=10.0) -> dict:
        return self.lines.get(timeout=seconds)[1]

    def quiet(self, seconds=1.0) -> bool:
        try:
            self.lines.get(timeout=seconds)
        except queue.Empty:
            return True
        return False

    def end(self) -> int:
        if self.proc.poll() is None:
            self.proc.terminate()
        return self.proc.wait(10)


@pytest.fixture
def stream(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    s = Stream(repo)
    yield s
    s.end()


def test_the_first_line_comes_at_once_and_is_the_snapshot_state_json_prints(stream):
    began = time.monotonic()
    first = stream.next()
    assert time.monotonic() - began < 5  # a process start and one read, not a tick waited out
    assert first["schema"] == 1 and [t["id"] for t in first["tasks"]] == ["a"]
    assert set(first) >= {"cursor", "goal", "tasks", "run", "envelope"}  # the snapshot, not a summary of it
    assert stream.quiet(0.6)  # nothing changed: nothing said


def test_a_write_to_the_store_is_one_more_line_within_a_tick_or_two(stream, repo):
    stream.next()
    at = time.monotonic()
    with Store.open(repo) as store:
        plan.propose(store, [leaf("b", "b.txt", needs=["a"])], ALEX)
    said = stream.next()
    assert time.monotonic() - at < 3  # measured at 20 to 60 ms on a laptop; loose for a loaded runner
    assert {t["id"] for t in said["tasks"]} == {"a", "b"} and said["edges"] == [["a", "b", "needs"]]
    assert stream.quiet(0.6)  # one change, then quiet again


def test_the_run_lock_coming_and_going_is_a_line_each_without_a_store_write(stream, repo):
    stream.next()
    lock = repo / ".graphene" / "run.lock"
    lock.write_text(f"{os.getpid()}\n")  # a run that is this process: alive, by its pid alone
    assert stream.next()["run"] == {"going": True, "pid": os.getpid()}
    lock.unlink()
    assert stream.next()["run"] == {"going": False, "pid": None}


def test_a_term_ends_it_with_exit_0_and_so_does_its_reader_closing(stream, repo):
    stream.next()
    stream.proc.send_signal(signal.SIGTERM)
    assert stream.proc.wait(10) == 0 and stream.proc.stderr.read() == ""
    other = Stream(repo, thread=False)
    assert json.loads(other.proc.stdout.readline())["schema"] == 1
    other.proc.stdout.close()  # the editor went: nothing reads the pipe
    assert other.proc.wait(10) == 0  # seen at the next look, with nothing written


def test_the_version_moves_on_a_commit_a_log_row_and_the_lock_and_stays_put_otherwise(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    with Store.open(repo) as reader:
        v0 = ST.version(reader, repo)
        assert ST.version(reader, repo) == v0  # nothing happened: the same
        with Store.open(repo) as writer:
            plan.propose(writer, [leaf("b", "b.txt")], ALEX)
        v1 = ST.version(reader, repo)
        assert v1 != v0 and v1[1] > v0[1]  # another connection committed, and the log grew
        (repo / ".graphene" / "run.lock").write_text("1\n")
        v2 = ST.version(reader, repo)
        assert v2 != v1 and v2[2] is not None and v1[2] is None
        assert ST.version(reader, repo) == v2


def test_follow_says_the_line_once_per_change_and_reads_the_version_before_the_snapshot(repo, monkeypatch):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    said, looks = [], [0]

    def alive():
        looks[0] += 1
        if looks[0] == 3:  # a write between two looks
            with Store.open(repo) as writer:
                plan.propose(writer, [leaf("b", "b.txt")], ALEX)
        return looks[0] <= 6

    with Store.open(repo) as reader:
        ST.follow(reader, repo, said.append, alive, tick=0.0)
    assert [sorted(t["id"] for t in json.loads(s)["tasks"]) for s in said] == [["a"], ["a", "b"]]


def until(stream, want, seconds=10.0) -> dict:
    """The first line ``want`` says yes to, within ``seconds``: the lines before it are what the store said
    on its way (a store just made is unplanned for a moment)."""
    end = time.monotonic() + seconds
    while True:
        said = stream.next(max(0.01, end - time.monotonic()))
        if want(said):
            return said


def test_a_store_removed_and_remade_under_the_watch_is_said_gone_then_followed_anew(stream, repo):
    """`git clean -fdx` under an open editor, then a new `graphene ask`: the connection held the old file's
    inode for ever and the stream showed the old plan with no sign (the editor night's review)."""
    assert [t["id"] for t in stream.next()["tasks"]] == ["a"]
    shutil.rmtree(repo / ".graphene")
    assert "no Graphene store" in stream.next()["error"]  # said once, as `state --json` says it
    assert stream.quiet(0.6) and stream.proc.poll() is None  # one process, still watching
    with Store.open(repo) as store:  # a new store: a new file, a new plan
        plan.propose(store, [leaf("b", "b.txt")], ALEX)
    said = until(stream, lambda s: "tasks" in s)
    assert [t["id"] for t in said["tasks"]] == ["b"]
    with Store.open(repo) as store:  # and it is the new store that is followed from here on
        plan.propose(store, [leaf("c", "c.txt")], ALEX)
    assert {t["id"] for t in stream.next()["tasks"]} == {"b", "c"}
    assert stream.quiet(0.6)


def test_follow_ends_with_false_when_the_store_file_goes_or_is_another(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    said, looks = [], [0]

    def alive():
        looks[0] += 1
        if looks[0] == 3:
            os.replace(repo / ".graphene" / "graphene.db", repo / ".graphene" / "aside.db")
        return looks[0] <= 20

    with Store.open(repo) as reader:
        assert ST.identity(repo) is not None
        assert ST.follow(reader, repo, said.append, alive, tick=0.0) is False
    assert len(said) == 1 and ST.identity(repo) is None and looks[0] < 20  # the old one was never said again


def test_where_there_is_no_plan_the_watch_says_so_once_and_exits_1_as_state_does(repo):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    said = subprocess.run([*CLI, "state", "--json", "--watch"], cwd=repo, env=env, capture_output=True,
                          text=True, timeout=30)  # fmt: skip
    assert said.returncode == 1 and "no Graphene store" in json.loads(said.stdout)["error"]


def test_watch_has_help_in_the_budget_and_the_reference_names_it():
    import typer.main

    from graphene_map.cli import build

    state = typer.main.get_command(build()).commands["state"]
    (watch,) = [p for p in state.params if p.name == "watch"]
    assert "each time the store changes" in watch.help and len(watch.help) <= 80
    how = (__import__("pathlib").Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text()
    assert "`graphene state --json --watch`" in how
