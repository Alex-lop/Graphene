# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene watch` opens the cockpit; `--classic`, or a classic `--view`, the older screen. Run in a real
pseudo-terminal, as a person's terminal: the screen that opens is the one whose words are on it."""

import fcntl
import os
import pty
import select
import signal
import struct
import sys
import termios
import time

from test_plan_cli import repo  # noqa: F401  (fixture)

CLI = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"


def spawn(repo, *args):
    """`graphene ARGS` in the repository, in an 80x24 terminal of its own: (pid, the terminal's end)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(repo)
        os.environ["TERM"] = "xterm-256color"
        os.execv(sys.executable, [sys.executable, "-c", CLI, *args])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    return pid, fd


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


def close(pid, fd) -> bool:
    """The terminal goes away with no hangup sent; True when the process was gone within five seconds."""
    os.close(fd)
    end = time.time() + 5
    while time.time() < end:
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done:
            return True
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    return False


def test_watch_opens_the_cockpit_with_the_repositorys_name_and_leaves_with_its_terminal(repo):
    pid, fd = spawn(repo, "watch")
    seen = read_until(fd, repo.name.encode())
    assert b"cockpit" in seen and repo.name.encode() in seen and b"the plan of" not in seen
    assert close(pid, fd), "the screen outlived its terminal"


def test_watch_classic_opens_the_older_screen(repo):
    pid, fd = spawn(repo, "watch", "--classic")
    seen = read_until(fd, b"the plan of")
    assert b"the plan of" in seen and b"cockpit" not in seen
    assert close(pid, fd)


def test_naming_a_classic_view_opens_the_older_screen(repo):
    pid, fd = spawn(repo, "watch", "--view", "tree")
    seen = read_until(fd, b"the plan of")
    assert b"the plan of" in seen and b"cockpit" not in seen
    assert close(pid, fd)


def test_demo_replays_in_the_cockpit_and_demo_classic_in_the_older_screen(tmp_path):
    pid, fd = spawn(tmp_path, "demo")
    seen = read_until(fd, b"replay")
    assert b"replay" in seen and b"cockpit" in seen
    assert close(pid, fd), "the replay outlived its terminal"
    pid, fd = spawn(tmp_path, "demo", "--classic")
    seen = read_until(fd, b"replay") + read_until(fd, b"\0", 3.0)  # then a moment for the rest of the screen
    assert b"replay" in seen and b"cockpit" not in seen
    assert close(pid, fd)
