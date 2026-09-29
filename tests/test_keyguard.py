"""The keyguard (tests/keyguard.py) fails every test that reaches for the real keychain, each way a test
can, in a pytest session of its own. Each way is one a test could take tonight: Graphene's own lookup
and write with GRAPHENE_KEYCHAIN turned on, an absolute path, a child whose environment drops
GRAPHENE_KEYCHAIN, a child or a shell whose PATH leaves the stand-ins out, `import keyring`, and a
child that outlives its test. A net stands under the inner session, in case the guard itself is broken:
a `security` and a `secret-tool` of this test's own, on its PATH ahead of the real ones, and a real
tool is only ever run with `help`, which reads no keychain."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOL = "security" if sys.platform == "darwin" else "secret-tool"
REAL_ON_A_BARE_PATH = shutil.which(TOOL, path="/usr/bin:/bin") is not None  # not every Linux has secret-tool

CONFTEST = f"""
import sys
sys.path.append({str(Path(__file__).parent)!r})
import keyguard

def pytest_configure(config):
    keyguard.install(config)
"""

WAYS = f"""
import os, subprocess, sys
from graphene_map import keys

TOOL = {TOOL!r}
PEEK = [sys.executable, "-c", "from graphene_map import keys; print(keys.find())"]


def test_graphenes_lookup(monkeypatch):
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "on")
    keys._from_keychain.cache_clear()
    keys.find()


def test_graphenes_write(monkeypatch):
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "on")
    keys.set("sk-FAKE-keyguard")


def test_an_absolute_path():
    subprocess.run(["/usr/bin/" + TOOL, "help"], capture_output=True)


def test_a_child_whose_environment_drops_the_setting():
    env = {{k: v for k, v in os.environ.items() if not k.startswith("GRAPHENE_")}}
    subprocess.run(PEEK, env=env, capture_output=True)


def test_a_child_on_a_bare_path():
    subprocess.run(["sh", "-c", TOOL + " help"], env={{"PATH": "/usr/bin:/bin"}}, capture_output=True)


def test_a_shell_on_a_bare_path(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    os.system(TOOL + " help >/dev/null 2>&1")


def test_keyring():
    import keyring  # noqa: F401


def test_a_fake_keychain_under_tmp_path(tmp_path, monkeypatch):
    fake = tmp_path / TOOL
    fake.write_text("#!/bin/sh\\necho sk-FAKE-in-a-fake\\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "on")
    keys._from_keychain.cache_clear()
    assert keys.find() == "sk-FAKE-in-a-fake"
    keys._from_keychain.cache_clear()
"""

OUTLIVES = f"""
import subprocess


def test_a_child_that_outlives_its_test(tmp_path):
    subprocess.Popen(["sh", "-c", "sleep 1; {TOOL} help"], start_new_session=True)
"""


def session(tmp_path: Path, tests: str, wait: str = "", **more: str):
    """pytest on ``tests`` under the keyguard, with this test's net on the PATH and ``more`` in its
    environment; the net's log."""
    net = tmp_path / "net"
    net.mkdir()
    for tool in ("security", "secret-tool"):
        (net / tool).write_text(f"#!/bin/sh\necho $0 $1 >> {net}/reached\nexit 1\n")
        (net / tool).chmod(0o755)
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "conftest.py").write_text(CONFTEST + wait)
    (inner / "test_ways.py").write_text(tests)
    env = os.environ | {"PATH": f"{net}{os.pathsep}{os.environ['PATH']}", "COLUMNS": "400"} | more
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", str(inner)],
                          cwd=inner, env=env, capture_output=True, text=True, timeout=300)  # fmt: skip
    return done, net / "reached"


def test_every_way_to_the_real_keychain_fails_its_test_and_a_fake_passes(tmp_path):
    done, reached = session(tmp_path, WAYS)
    said = done.stdout + done.stderr
    lines = {line.split()[1].split("::")[1]: line for line in done.stdout.splitlines()
             if line.startswith(("PASSED ", "FAILED ", "ERROR "))}  # fmt: skip
    outcome = {name: line.split()[0] for name, line in lines.items()}
    failed = {"test_graphenes_lookup", "test_graphenes_write", "test_an_absolute_path",
              "test_a_child_whose_environment_drops_the_setting", "test_keyring"}  # fmt: skip
    if REAL_ON_A_BARE_PATH:  # else a PATH of /usr/bin:/bin finds no keychain tool to reach
        failed |= {"test_a_child_on_a_bare_path", "test_a_shell_on_a_bare_path"}
    assert outcome == {name: "FAILED" if name in failed else "PASSED" for name in outcome}, said
    assert len(outcome) == 8 and done.returncode == 1, said
    assert all(" - keyguard: " in lines[n] or " - Failed: keyguard: " in lines[n] for n in failed), said
    assert not reached.exists(), reached.read_text()  # nothing went past the stand-ins


def test_a_child_that_asks_after_its_test_has_ended_fails_the_run(tmp_path):
    wait = """
import pathlib, time
@__import__("pytest").hookimpl(tryfirst=True)
def pytest_sessionfinish():
    log = keyguard.SHIMS / "calls.log"
    deadline = time.monotonic() + 60
    while not log.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
"""
    done, reached = session(tmp_path, OUTLIVES, wait)
    said = done.stdout + done.stderr
    assert "1 passed" in done.stdout and done.returncode == 1, said
    assert f"keyguard: a process asked the keychain: {TOOL} help, during test_ways.py::" in said, said
    assert not reached.exists()


def test_a_session_clears_the_stand_ins_earlier_sessions_left_once_their_pytest_has_ended(tmp_path):
    """Review, 29 September: every session left its keyguard-* directory, 277 of them in one day's TMPDIR.
    One whose pytest has ended goes an hour after its last use; one still in use by a running session, or
    by a child that outlived its session within the hour, stays."""
    temp, ended, hours_ago = tmp_path / "temp", 2**31 - 1, time.time() - 7200  # no process has that pid
    stale = [f"keyguard-{ended}-a1b2c3", "keyguard-0des5bia"]  # the second from before names held a pid
    kept = [f"keyguard-{ended}-d4e5f6", f"keyguard-{os.getpid()}-g7h8i9"]  # an hour not passed; running
    for name in stale + kept:
        (temp / name).mkdir(parents=True)
    for name in (*stale, kept[1]):
        os.utime(temp / name, (hours_ago, hours_ago))
    done, _ = session(tmp_path, "def test_nothing():\n    pass\n", TMPDIR=str(temp))
    assert "1 passed" in done.stdout, done.stdout + done.stderr
    left = {p.name for p in temp.glob("keyguard-*")}
    assert not left & set(stale) and set(kept) <= left
    assert len(left - set(kept)) == 1  # the inner session's own, left for a child that outlives it
