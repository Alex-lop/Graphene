# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene watch` opens the cockpit; `--classic`, or a classic `--view`, the older screen. Run in a real
pseudo-terminal, as a person's terminal: the screen that opens is the one whose words are on it."""

import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

from test_plan_cli import repo  # noqa: F401  (fixture)

CLI = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"


def spawn(repo, *args):
    """`graphene ARGS` in the repository, in an 80x24 terminal of its own: (the process, the terminal's end).
    The terminal is only where it reads and writes, as a test's is: it is not its controlling terminal, so
    closing it sends no hangup. (`subprocess`, not `pty.fork`: a test runs in a worker with threads.)"""
    main, tty = pty.openpty()
    fcntl.ioctl(tty, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    env = {**os.environ, "TERM": "xterm-256color"}
    argv = [sys.executable, "-c", CLI, *args]
    std = {"stdin": tty, "stdout": tty, "stderr": tty}
    proc = subprocess.Popen(argv, cwd=repo, env=env, start_new_session=True, **std)
    os.close(tty)
    return proc, main


def read_until(fd, needle: bytes, seconds: float = 30.0) -> bytes:
    out, end = b"", time.time() + seconds
    while time.time() < end and needle not in out:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                out += os.read(fd, 65536)
            except OSError:
                break
    return out


def close(proc, fd) -> bool:
    """The terminal goes away with no hangup sent; True when the process was gone within five seconds."""
    os.close(fd)
    try:
        proc.wait(timeout=5)
        return True
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return False


def test_watch_opens_the_cockpit_with_the_repositorys_name_and_leaves_with_its_terminal(repo):
    proc, fd = spawn(repo, "watch")
    seen = read_until(fd, repo.name.encode())
    assert b"cockpit" in seen and repo.name.encode() in seen and b"the plan of" not in seen
    assert close(proc, fd), "the screen outlived its terminal"


def test_watch_classic_opens_the_older_screen(repo):
    proc, fd = spawn(repo, "watch", "--classic")
    seen = read_until(fd, b"the plan of")
    assert b"the plan of" in seen and b"cockpit" not in seen
    assert close(proc, fd)


def test_naming_a_classic_view_opens_the_older_screen(repo):
    proc, fd = spawn(repo, "watch", "--view", "tree")
    seen = read_until(fd, b"the plan of")
    assert b"the plan of" in seen and b"cockpit" not in seen
    assert close(proc, fd)


def test_demo_replays_in_the_cockpit_and_demo_classic_in_the_older_screen(tmp_path):
    proc, fd = spawn(tmp_path, "demo")
    seen = read_until(fd, b"replay")
    assert b"replay" in seen and b"cockpit" in seen
    assert close(proc, fd), "the replay outlived its terminal"
    proc, fd = spawn(tmp_path, "demo", "--classic")
    seen = read_until(fd, b"replay") + read_until(fd, b"\0", 3.0)  # then a moment for the rest of the screen
    assert b"replay" in seen and b"cockpit" not in seen
    assert close(proc, fd)
