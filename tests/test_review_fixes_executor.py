# ruff: noqa: F811  (pytest fixtures imported from test_executor are named again as arguments)
"""What the closing review found in the executor, the client and the sandbox, each against the recorded
fake (and, where it says so, the Docker stand-in): each test fails on the code before its fix."""

import contextlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fake_faults import everywhere
from fake_tokenfactory import call
from test_executor import (  # noqa: F401
    NANO,
    by_fork,
    fake,
    git,
    leaf,
    plan_of,
    repo,
    run_one,
    script,
    tool_results,
)
from test_sandbox_state import needs_docker

from graphene_map import executor, plan, run, sandbox
from graphene_map import tokenfactory as tf
from graphene_map.ask import ask
from graphene_map.ask import named as planner
from graphene_map.node_record import bill, bill_line, node_record, render, rolled_up
from graphene_map.plan import Caller
from graphene_map.plan_view import build_plan_view
from graphene_map.run import _alive
from graphene_map.store import Store


def test_an_answer_that_is_not_json_says_so_in_one_line(monkeypatch):
    """A 200 that is not JSON (a portal, a proxy, a wrong GRAPHENE_TOKENFACTORY_URL) escaped as a
    JSONDecodeError: a leaf came back as "3 attempts … AssertionError", and `graphene init` printed a
    traceback."""

    class Portal(BaseHTTPRequestHandler):
        def do_GET(self):
            page = b"<html>sign in to the hotel's wifi</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        do_POST = do_GET

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Portal)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/"
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", url)
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-key")
    tf._listed.cache_clear()
    try:
        said = f"Token Factory's answer at {url} is not JSON: a proxy, or a wrong GRAPHENE_TOKENFACTORY_URL?"
        assert tf.reach(tries=1) == said  # what `graphene init` says
        with pytest.raises(tf.Unreachable) as no:
            tf.chat(NANO, [{"role": "user", "content": "hi"}])
        assert str(no.value) == said
    finally:
        server.shutdown()
        server.server_close()
        tf._listed.cache_clear()


def raw(name: str, arguments: str) -> dict:
    """A call whose arguments are sent as they are: what a misfiring model sends."""
    return {"content": None, "tool_calls": [{"id": f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": arguments}}]}  # fmt: skip


def test_arguments_that_are_json_but_not_an_object_or_hold_a_null_are_said_to_the_model(repo, fake):
    """Arguments encoded twice, an array, or `"content": null` raised AttributeError out of the tool:
    the leaf stopped ("the executor stopped: AttributeError …") and the model was never told (72)."""
    f = fake([script({"greet": [
        raw("view", json.dumps(json.dumps({"path": "app.py"}))),  # encoded twice: read once more
        raw("view", json.dumps(["app.py"])),
        raw("write", json.dumps({"path": "app.py", "content": None})),
        call("release", why="looked"),
    ]})] * 10)  # fmt: skip
    plan_of(repo, leaf())
    run_one(repo)
    said = tool_results(f.requests[-1])
    assert said[0].split("\n")[1] == '    2      return "hi"'
    assert said[1] == "view takes a JSON object of named fields"
    assert said[2].startswith("write could not take those arguments (") and "'content'" in said[2]
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hi"\n'
    with Store.open(repo) as store:  # the model's own reason, not the executor's stop
        assert store.node_log("greet", ("released",))[-1]["detail"]["why"] == "looked"


@pytest.mark.parametrize("forks", [1, 2])
def test_wants_sent_as_one_string_is_one_path(repo, fake, forks):
    """`"wants": "other.py"` handed the leaf back offering to widen its scope to o, t, h, e, r …"""
    fake([call("release", why="the greeting is also in other.py", wants="other.py")] * 10)
    plan_of(repo, leaf())
    run_one(repo, f"nemotron --model {NANO} --forks {forks}")
    with Store.open(repo) as store:
        assert store.node_log("greet", ("released",))[-1]["detail"]["wants"] == ["other.py"]


def test_a_stopped_executor_leaves_nothing_the_models_command_started_running(tmp_path):
    """The model's command runs in a session of its own (its time limit stops all it started): a run
    stopped while it ran (TERM is SystemExit in the executor) left it running, able to write into the
    checkout after the leaf was handed back."""
    pids = tmp_path / "pids"

    def stopped(*_):
        raise SystemExit(143)  # what the executor's TERM handler raises

    was = signal.signal(signal.SIGALRM, stopped)
    signal.setitimer(signal.ITIMER_REAL, 1.0)
    try:
        with pytest.raises(SystemExit):
            executor.Local(tmp_path).run(f"echo $$ >> {pids}; sleep 60 & echo $! >> {pids}; wait")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, was)
    started = [int(p) for p in pids.read_text().split()]
    left = [p for p in started if _alive(p)]
    for p in left:
        os.kill(p, signal.SIGKILL)
    assert len(started) == 2 and left == []


def ignoring(repo):
    """The repository ignores a secret and a data directory, as most do, and both are on disk."""
    (repo / ".gitignore").write_text(".graphene/\n__pycache__/\n.env\ndata/\n")
    git(repo, "commit", "-qam", "ignore the secret and the data")
    (repo / ".env").write_text("AWS_SECRET_ACCESS_KEY=do-not-send\n")
    (repo / "data").mkdir()
    (repo / "data" / "big.csv").write_text("1,2,3\n")


def test_a_winning_fork_never_deletes_or_overwrites_what_git_ignores(repo, fake):
    """The state before the forks was every file on disk in the scope, the ignored ones too; a fork's
    copy holds only what git shows, so a winner under `**` unlinked .env and data/ from the checkout, and
    copied in the .env its own command wrote."""
    ignoring(repo)
    fake([by_fork({
        1: [call("run", command="echo from-the-fork > .env; echo new > data/new.csv"),
            call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")],
        2: [call("release", why="leaving it to fork 1")],
    })] * 20)  # fmt: skip
    plan_of(repo, leaf(scope=("**",)))
    done, _ = run_one(repo, f"nemotron --model {NANO} --forks 2")
    assert [n.id for n in done] == ["greet"]
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hello"\n'
    assert (repo / ".env").read_text() == "AWS_SECRET_ACCESS_KEY=do-not-send\n"
    assert (repo / "data" / "big.csv").read_text() == "1,2,3\n"
    assert not (repo / "data" / "new.csv").exists()


def test_a_fork_reads_what_git_shows_and_what_it_wrote_and_never_what_git_ignores(repo, fake):
    """A fork's copy has no .git, so git there showed nothing: every fork was blind ("is not read: git
    ignores it or it is not there", and `view .` said "(empty)")."""
    ignoring(repo)
    f = fake([by_fork({
        1: [call("view", path="app.py"), call("view", path="."), call("view", path=".env"),
            call("write", path="new.py", content="x = 2\n"), call("view", path="new.py"),
            call("release", why="looked")],
        2: [call("release", why="looked too")],
    })] * 20)  # fmt: skip
    plan_of(repo, leaf(scope=("app.py", "new.py")))
    run_one(repo, f"nemotron --model {NANO} --forks 2")
    said = tool_results([r for r in f.requests if "This is fork 1 of" in r["messages"][0]["content"]][-1])
    assert said[0].split("\n")[1:2] == ['    2      return "hi"'], said
    assert said[1].split("\n") == [".gitignore", "app.py", "other.py"]
    assert said[2].startswith(".env is not read: git ignores it")
    assert said[4] == "    1  x = 2\n    2  "
    assert "do-not-send" not in json.dumps(f.requests)


class Pyc:
    """A box whose command leaves a Python cache beside app.py, as a check that imports it does."""

    image, ops = sandbox.IMAGE, 0
    made = "0\n" + "1" * 40 + "  ./app.py\n"
    lists = {"granted": made, "ran": made + "2" * 40 + "  ./__pycache__/app.cpython-312.pyc\n"}

    def start(self, tar, script, timeout):
        return "made", 0, ""

    def run(self, image, script, files, timeout):
        return ("granted" if image == "made" else "ran"), 0, ""

    def read(self, image, path):
        return (self.lists[image] + sandbox.END + "\n").encode()


def test_a_forks_sandbox_asks_git_in_the_checkout_so_a_python_cache_is_nobodys_change(repo, tmp_path):
    """A fork's sandbox asked git in its copy, which has no .git, what it ignores: nothing, so every
    Python check was a breach (__pycache__/*.pyc) and the model was told its command was refused."""
    copies = [tmp_path / "fork1", tmp_path / "fork2"]
    for copy in copies:
        copy.mkdir()
        (copy / "app.py").write_text((repo / "app.py").read_text())
    first = sandbox.Sandbox(copies[0], ["app.py"], Pyc(), checkout=repo)  # as fork_and_pick makes fork 1's
    for place in (first, first.fork(copies[1])):  # and every other fork's, from its checkpoint
        code, out = place.run("python3 -c 'import app'")
        assert code == 0 and "refused" not in out and place.strays == set()


def test_forks_whose_sandbox_cannot_be_made_leave_no_copy_of_the_checkout_behind(
    repo, fake, monkeypatch, tmp_path
):
    """The copies were made before the try that removes them: a sandbox that could not be made left
    fork 1's copy of the checkout in the temp directory."""
    everywhere(monkeypatch, tmp_path, FAULTS_BOX="fake", FAULTS_RAISE="useradd")  # the checkpoint's setup
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setenv("TMPDIR", str(temp))  # the executor's
    fake([call("release", why="never asked")] * 5)
    plan_of(repo, leaf())
    run_one(repo, f"nemotron --model {NANO} --placement sandbox --forks 2")
    with Store.open(repo) as store:
        why = store.node_log("greet", ("released",))[-1]["detail"]["why"]
    assert why == "the executor stopped: ConnectionResetError: the sandbox went away"
    assert list(temp.glob("graphene-greet-fork*")) == []


@pytest.mark.parametrize("forks", [1, 2])
def test_a_tools_error_names_its_path_in_the_repository_never_where_the_checkout_or_a_copy_is(
    repo, fake, forks
):
    """A tool that raised an OSError in a fork gave the fork's reason, and the leaf's hand-back, the
    copy's temp path (/var/folders/…/graphene-greet-fork1-…); without forks, the checkout's. The page
    never carries a path to the checkout (64)."""
    (repo / "src" / "sub").mkdir(parents=True)
    (repo / "src" / "sub" / "a.py").write_text("a = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "src")
    fake([call("write", path="src/sub", content="x")] * 10)  # a directory: IsADirectoryError
    plan_of(repo, leaf(scope=("src/**",)))
    run_one(repo, f"nemotron --model {NANO} --forks {forks}")
    said = "IsADirectoryError: [Errno 21] Is a directory: 'src/sub'"
    with Store.open(repo) as store:
        why = store.node_log("greet", ("released",))[-1]["detail"]["why"]
        ended = [e["detail"] for e in store.node_log("greet", ("fork",)) if e["detail"]["state"] != "running"]
        page = json.dumps(build_plan_view(store, export=True))
    assert why == "the executor stopped: " + ("RuntimeError: " if forks > 1 else "") + said
    assert [e["why"] for e in ended] == [said] * (forks if forks > 1 else 0)
    assert "graphene-greet-fork" not in page and str(repo.resolve()) not in page and str(repo) not in page


STOPPED = "the run was stopped before this fork ended"


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True).stdout


@pytest.mark.parametrize("placement", ["local", pytest.param("sandbox", marks=needs_docker)])
def test_a_run_stopped_while_forks_work_stops_each_fork_says_so_and_leaves_nothing_running(
    repo, fake, monkeypatch, tmp_path, placement
):
    """TERM on a forked leaf (its run stopped, as `graphene run` stops an executor): only the main
    thread saw it. The forks went on calling Token Factory, unbilled, until the run killed the executor
    ten seconds later; their rows stayed "running"; the model's commands, and in the Docker sandbox the
    forks' containers, were left behind; and a parallel run's second TERM could print a traceback."""
    pids, temp = tmp_path / "pids", tmp_path / "temp"
    temp.mkdir()
    made = None
    if placement == "sandbox":  # the Docker stand-in, which writes down the containers it makes
        made = everywhere(monkeypatch, tmp_path, FAULTS_BOX="killed") / "containers"
        monkeypatch.setenv("GRAPHENE_SANDBOX", "docker")
    command = "sleep 60" if made else f"echo $$ >> {pids}; exec sleep 60"
    f = fake([by_fork({k: [call("run", command=command), call("done")] for k in (1, 2)})] * 10)
    plan_of(repo, leaf())
    with Store.open(repo) as store:
        plan.start(store, "greet", Caller("run:nemotron", False, "s-1"), repo)
    env = {**os.environ, "GRAPHENE_NODE": "greet", "GRAPHENE_ATTEMPT": "s-1", "GRAPHENE_TRY": "1",
           "TMPDIR": str(temp)}  # fmt: skip
    argv = [sys.executable, "-m", "graphene_map.executor", "--model", NANO, "--forks", "2", "--placement",
            placement, "the contract"]  # fmt: skip
    proc = subprocess.Popen(argv, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)  # fmt: skip

    def working() -> int:  # how many forks are in their command now
        if made is None:
            return len(pids.read_text().split()) if pids.exists() else 0
        boxes = made.read_text().split() if made.exists() else []
        return docker("inspect", "-f", "{{.State.Running}}", *boxes).split().count("true") if boxes else 0

    try:
        until = time.monotonic() + 120
        while working() < 2 and proc.poll() is None and time.monotonic() < until:
            time.sleep(0.1)
        assert working() == 2
        os.killpg(proc.pid, signal.SIGTERM)  # the run stops it; a parallel run sends TERM twice
        time.sleep(0.02)  # while the first is being handled
        with contextlib.suppress(OSError):  # it ended already
            os.killpg(proc.pid, signal.SIGTERM)
        run._end(proc)  # what the run does next: waits its grace for the executor to end, then kills it
        out = proc.stdout.read().decode()
        assert proc.returncode == 143, out  # it ended by itself, inside the run's grace: not killed
        assert "Traceback" not in out, out
        with Store.open(repo) as store:
            last = {e["detail"]["fork"]: e["detail"] for e in store.node_log("greet", ("fork",))}
            bill = store.node_log("greet", ("usage",))[-1]["detail"]
        assert [(last[k]["state"], last[k]["why"]) for k in (1, 2)] == [("stopped", STOPPED)] * 2
        assert bill["calls"] == len(f.requests) == 2  # what the forks spent before they stopped, billed
        assert list(temp.glob("graphene-greet-fork*")) == []
        if made is None:
            started = [int(p) for p in pids.read_text().split()]
            until = time.monotonic() + 5
            while [p for p in started if _alive(p)] and time.monotonic() < until:
                time.sleep(0.1)
            assert not [p for p in started if _alive(p)]
        else:
            assert not set(made.read_text().split()) & set(docker("ps", "-aq", "--no-trunc").split())
    finally:
        with contextlib.suppress(OSError):  # it ended already
            os.killpg(proc.pid, signal.SIGKILL)
        for p in (pids.read_text().split() if pids.exists() else []):
            with contextlib.suppress(OSError):  # it ended already
                os.kill(int(p), signal.SIGKILL)
        if made is not None:
            boxes, images = made.read_text().split(), (made.parent / "images")
            docker("rm", "-f", *boxes) if boxes else None
            docker("rmi", "-f", *images.read_text().split()) if images.exists() else None


def test_a_stand_ins_usage_is_never_credited_to_token_factory(repo, fake):
    """A usage row could not tell a stand-in from Token Factory: the record's bill line credited the
    scripted fake's numbers to Token Factory ("(Token Factory's usage)")."""
    proposal = {"content": "```plan\n? say hello  [hello]\n    scope: app.py\n    check: true\n```"}
    work = script({"greet": [call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")]})
    planned = lambda body: "You are the planner" in body["messages"][0]["content"]  # noqa: E731
    fake([lambda body: proposal if planned(body) else work(body)] * 10)
    plan_of(repo, leaf())
    run_one(repo)
    with Store.open(repo) as store:
        ask(store, repo, "and say hello", planner("nemotron"), say=lambda s: None)
        rows = [e["detail"] for e in store.node_log(kinds=("usage",))]
        greet = plan.get(store, "greet")
        lines = [*render(node_record(store, repo, greet)), *rolled_up(store, repo, [greet]),
                 *bill_line(bill(store.node_log("*", ("usage",))))]  # fmt: skip
    assert [r["endpoint"] for r in rows] == ["a stand-in", "a stand-in"]  # the executor's, the planner's
    billed = [line for line in lines if "at list price" in line]
    assert len(billed) == 3 and all(line.endswith("(a stand-in's usage)") for line in billed)
    assert "Token Factory's usage" not in "\n".join(lines)


def test_the_bill_line_credits_token_factory_only_when_every_row_it_adds_up_says_so(repo, monkeypatch):
    monkeypatch.delenv("GRAPHENE_TOKENFACTORY_URL", raising=False)
    assert tf.endpoint() == "token factory"
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", tf.BASE.rstrip("/"))
    assert tf.endpoint() == "token factory"
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", "https://tokenfactory.example.org/v1/")
    assert tf.endpoint() == "a stand-in"  # never the URL itself: it could name a host of the person's
    plan_of(repo, leaf())
    row = {"model": NANO, "calls": 1, "prompt_tokens": 10, "completion_tokens": 5, "dollars": 0.001}
    with Store.open(repo) as store:
        plan.start(store, "greet", Caller("run:nemotron", False, "s-1"), repo)

        def said(detail: dict) -> tuple[str, str]:  # the leaf's record, and the rolled-up record
            store.log_node("greet", plan._now(), "usage", "run:nemotron", "s-1", None, detail)
            greet = plan.get(store, "greet")
            return bill_line(bill(store.node_log("greet")))[0], rolled_up(store, repo, [greet])[-1]

        assert all(s.endswith("(Token Factory's usage)") for s in said(row | {"endpoint": "token factory"}))
        assert all(s.endswith("(a stand-in's usage)") for s in said(row | {"endpoint": "a stand-in"}))
    with Store.open(repo) as store:  # a row from before the endpoint was said is not credited either
        store.log_node("*", plan._now(), "usage", "planner:nemotron", None, None, row)
        assert bill_line(bill(store.node_log("*", ("usage",))))[0].endswith("(a stand-in's usage)")
