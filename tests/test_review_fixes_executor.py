# ruff: noqa: F811  (pytest fixtures imported from test_executor are named again as arguments)
"""What the closing review found in the executor, the client and the sandbox, each against the recorded
fake (and, where it says so, the Docker stand-in): each test fails on the code before its fix."""

import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
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

from graphene_map import executor, sandbox
from graphene_map import tokenfactory as tf
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
