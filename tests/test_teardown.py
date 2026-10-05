"""A closed terminal ends what Graphene started under it: `graphene demo`, `graphene watch`, and a
`graphene run` with its executor and the check that executor's `done` started. Each is started on a
pseudo-terminal of its own; every process it has made, sessions of their own included, is read; the
terminal is closed; and each of them must be gone within seconds."""

import contextlib
import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time

import pytest

from graphene_map import plan
from graphene_map.nemotron import sandbox
from graphene_map.plan import Caller
from graphene_map.store import Store

CLI = [sys.executable, "-c", "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"]
EXECUTOR = f"""
import os, pathlib, subprocess
pathlib.Path("a.txt").write_text("a, by its executor\\n")
subprocess.run({CLI!r} + ["node", "done", os.environ["GRAPHENE_NODE"]])
"""
CHECK = "sleep 97"  # the leaf's check: still running when the terminal closes


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def table() -> dict[int, tuple[int, str, str]]:
    """Every process on the machine: its parent, when it started, and its command line."""
    ps = ["ps", "-A", "-ww", "-o", "pid=,ppid=,stat=,lstart=,command="]
    out = subprocess.run(ps, capture_output=True, text=True).stdout
    rows = [line.split(None, 8) for line in out.splitlines()]
    return {int(r[0]): (int(r[1]), " ".join(r[3:8]), r[-1]) for r in rows if r[2][0] != "Z"}


def tree(pid: int, rows: dict) -> set[int]:
    """``pid`` and everything under it, by parent, whatever session each is in."""
    found, todo = {pid}, [pid]
    while todo:
        parent = todo.pop()
        new = {p for p, (pp, *_) in rows.items() if pp == parent and p not in found}
        found |= new
        todo += new
    return found & rows.keys()


def on_a_terminal(argv, cwd, env, window: bool):
    """``argv`` on a pseudo-terminal of its own, at 80x24. ``window``: the terminal is its session's
    controlling one, as a terminal window's is, so closing it sends the hangup. Otherwise it is only
    where the program reads and writes (a test's terminal, or a program started by something that
    ignores the hangup), and closing it sends nothing: the program must see for itself."""
    main, tty = pty.openpty()
    fcntl.ioctl(tty, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))

    def lead():
        os.setsid()
        if window:
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=tty, stdout=tty, stderr=tty, preexec_fn=lead)
    os.close(tty)
    return proc, main


def until(what, terminals: dict | None = None, seconds: float = 60) -> bool:
    """Wait for ``what()``, reading each of ``terminals`` meanwhile (into its value), so no program
    blocks on a terminal nobody reads."""
    end = time.monotonic() + seconds
    while not what() and time.monotonic() < end:
        if not terminals:
            time.sleep(0.2)
            continue
        for main in select.select(list(terminals), [], [], 0.2)[0]:
            with contextlib.suppress(OSError):
                terminals[main] += os.read(main, 65536)
    return what()


@pytest.mark.parametrize("window", [True, False], ids=["the window closes", "it closes saying nothing"])
def test_nothing_graphene_starts_outlives_its_terminal(tmp_path, window):
    """The shaping run left 15 `graphene demo` replays spinning after their test's terminals were gone.
    A closed terminal that sends no hangup (the pty was only the program's stdin and stdout, as a
    test's is, or what started it ignores the hangup) left the screen reading an end of file forever,
    at full CPU; and an executor's `done` killed by the run's stop left its check running."""
    env = os.environ | {"TERM": "xterm-256color", "GRAPHENE_AS": "person:alex"}
    env["TMPDIR"] = str(tmp_path / "tmp")  # where the replay makes its repository
    (tmp_path / "tmp").mkdir()
    repo = tmp_path / "watched"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start")
    (tmp_path / "executor.py").write_text(EXECUTOR)
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "a", "title": "leaf a", "scope": ["a.txt"], "check": CHECK}],
                     Caller("alex", True))  # fmt: skip

    work = [*CLI, "run", "--with", f"{sys.executable} {tmp_path / 'executor.py'}"]
    started = {
        "demo": on_a_terminal([*CLI, "demo"], tmp_path, env, window),
        "watch": on_a_terminal([*CLI, "watch"], repo, env, window),
        "run": on_a_terminal(work, repo, env, window),
    }
    said = {main: b"" for _, main in started.values()}  # what each terminal was sent
    pids: dict[int, tuple] = {}  # each process under the three: when it started, its command line

    def up() -> bool:
        """Both screens drawn, and the leaf's check running under the run."""
        rows = table()
        under = {name: tree(proc.pid, rows) for name, (proc, _) in started.items()}
        pids.update({p: rows[p][1:] for p in set().union(*under.values())})
        drawn = b"replay" in said[started["demo"][1]] and b"watched" in said[started["watch"][1]]
        return drawn and any(rows[p][2].endswith(CHECK) for p in under["run"])  # not the executor's prompt

    def left() -> list[str]:
        """Those still running, by pid and start: a pid the system has handed on since is not ours."""
        rows = table()
        return [f"{p}: {rows[p][2]}" for p, (at, _) in sorted(pids.items()) if p in rows and rows[p][1] == at]

    try:
        assert until(up, said), (pids, said)
        until(lambda: False, said, 1)  # the screens settle: each reads keys by now
        while said:
            os.close(said.popitem()[0])  # the terminal is gone
        assert until(lambda: not left(), seconds=5), "\n".join(left())
        assert not list((tmp_path / "tmp").glob("graphene-demo-*"))  # the replay took its repository
        with Store.open(repo) as store:
            assert plan.get(store, "a").state == plan.OPEN  # the leaf is handed back, as Ctrl-C does
    finally:
        for main in said:
            os.close(main)
        for gone in left():
            with contextlib.suppress(OSError):
                os.kill(int(gone.split(":")[0]), signal.SIGKILL)


def ended(pid: int, seconds: float = 5) -> bool:
    """Gone (or a zombie nobody has reaped) within ``seconds``."""
    return until(lambda: pid not in table(), seconds=seconds)


def test_a_check_that_passes_leaves_nothing_it_started_running(tmp_path):
    """Review 24: a check that passed left what it put in the background running (a test server kept its
    port, with its worktree deleted under it, and failed the next leaf's identical check), and so did a
    command of the Nemotron executor's. Both now end their session once they return."""
    from graphene_map.nemotron.executor import Local

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start")
    left = tmp_path / "left"
    passed, _, _ = plan.run_check(f"sleep 313 >/dev/null 2>&1 & echo $! > {left}", repo)
    assert passed and ended(int(left.read_text()))
    code, said = Local(repo).run("sleep 317 >/dev/null 2>&1 & echo $!")
    assert code == 0 and ended(int(said))


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True).stdout


DOCKER = shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.skipif(not DOCKER, reason="needs a running Docker (the sandbox stand-in)")
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP], ids=["the run's stop", "a closed terminal"])
def test_a_sandboxed_leafs_check_goes_with_the_done_that_started_it(tmp_path, sig):
    """Review 21: a leaf placed in a sandbox has its check run in a fork of the sandbox's image, and that
    path had no guard. `graphene node done` died at the run's TERM (or a hangup) and left the check's
    container running, and its `docker start -a` client with it; the container was never removed."""
    image = f"graphene-teardown-leaf:{os.getpid()}"
    made = f"graphene-teardown-make-{os.getpid()}"
    user = f"useradd -m {sandbox.USER} && mkdir -p {sandbox.WORK}"  # the leaf's user, as a sandbox has it
    subprocess.run(["docker", "run", "--name", made, "python:3.12-slim", "bash", "-c", user], check=True)
    docker("commit", made, image)
    docker("rm", "-f", made)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "start")
    env = os.environ | {"GRAPHENE_AS": "person:alex"}
    with Store.open(repo) as store:
        leaf = {"id": "a", "title": "leaf a", "scope": ["a.txt"], "check": "sleep 600"}
        plan.propose(store, [leaf], Caller("alex", True))
        plan.start(store, "a", plan.caller(env), repo)  # by whoever runs its `done` below
        store.log_node("a", plan._now(), "placement", "run:nemotron", None, None,
                       {"placement": "sandbox", "box": "docker", "image": image})  # fmt: skip
    (repo / "a.txt").write_text("a, done\n")
    said = open(tmp_path / "done.txt", "w")  # noqa: SIM115
    done = subprocess.Popen([*CLI, "node", "done", "a"], cwd=repo, env=env, stdout=said,
                            stderr=subprocess.STDOUT, start_new_session=True)  # fmt: skip
    box = f"name=graphene-{done.pid}-"
    try:
        running = ("ps", "-q", "--filter", box, "--filter", "status=running")
        assert until(lambda: docker(*running).strip() or done.poll() is not None, seconds=120)
        assert done.poll() is None, (tmp_path / "done.txt").read_text()  # the check runs in its container
        done.send_signal(sig)
        done.wait(timeout=30)
        assert until(lambda: not docker("ps", "-aq", "--filter", box).strip(), seconds=20), docker("ps", "-a")
        client = f"docker start -a graphene-{done.pid}-"
        assert not [c for _, _, c in table().values() if c.startswith(client)]
    finally:
        done.kill()
        said.close()
        for left in docker("ps", "-aq", "--filter", box).split():
            docker("rm", "-f", left)
        docker("rmi", "-f", image)
