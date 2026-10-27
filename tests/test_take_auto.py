"""dev/proof/auto.sh as the live take is filmed. ENDPOINT=standin runs the whole race against
dev/proof/standin.py and nothing else; PAUSE=1 waits after `graphene init` until Enter; the first lines say
how to install the night's extension without installing it. A stand-in that dies is a refusal:
ENDPOINT=standin never falls back to Token Factory."""

import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import pytest
from fake_tokenfactory import Fake
from test_demo_auto import MAKE, ROOT, SCRIPT

needs_graphene = pytest.mark.skipif(shutil.which("graphene") is None,
                                    reason="needs graphene on PATH (uv run puts it there)")  # fmt: skip
NOT_THESE = ("SHOW_DEMO", "RECORD_DEMO", "RECORD_DEMO_AUTO", "NEBIUS_PROJECT_ID", "AI_AGENT")
TAKE = ROOT / "dev" / "process" / "editor" / "take"


def take_env(tmp_path, fake: Fake, **more: str) -> dict[str, str]:
    """The script's environment as the tests give it, with the test's own fake named as Token Factory: a take
    that reached for it would show in ``fake.requests``."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GRAPHENE_", "CLAUDE", "CODEX")) and k not in NOT_THESE}  # fmt: skip
    env |= fake.env() | {"MAKE_REPO": f"{sys.executable} {MAKE}", "HOME": str(tmp_path),
                         "GRAPHENE_PERSON": "the script", "GRAPHENE_KEYCHAIN": "off"}  # fmt: skip
    return env | {"ENDPOINT": "standin"} | more


@needs_graphene
def test_endpoint_standin_runs_the_whole_take_free_and_pauses_for_the_recording(tmp_path):
    with Fake([], key="fake-key") as f:
        env = take_env(tmp_path, f, PAUSE="1", RECORD=str(tmp_path / "take.jsonl"))
        take = subprocess.Popen(["bash", str(SCRIPT), str(tmp_path / "wordkit")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)  # fmt: skip
        said = bytearray()
        threading.Thread(target=lambda: [said.extend(c) for c in iter(lambda: take.stdout.read1(4096), b"")],
                         daemon=True).start()
        for _ in range(600):  # it pauses after init, before the race
            if b"then press Enter" in said:
                break
            assert take.poll() is None, said.decode()
            time.sleep(0.1)
        else:
            raise AssertionError(said.decode())
        time.sleep(2)
        assert b"$ graphene auto" not in said and take.poll() is None  # it waits for Enter
        take.stdin.write(b"\n")
        take.stdin.close()
        assert take.wait(timeout=600) == 0, said.decode()
    text = said.decode()
    lines = text.splitlines()
    # the install lines come first, as text: nothing was installed anywhere
    assert lines[0].startswith("to watch this take in your own editor, install the extension first")
    assert lines[1].startswith("  code --install-extension ") and ".vsix" in lines[1]
    assert lines[2].startswith("  cursor --install-extension ")
    # the stand-in answered the whole race, and it said so; the fake named as Token Factory heard nothing
    assert "stand-in at http://127.0.0.1:" in text and "no model runs, nothing is spent" in text
    assert f.requests == []
    assert f"open {tmp_path / 'wordkit'} in VS Code and start recording, then press Enter" in text
    last = [line for line in lines if line.startswith("auto: ")][-1]
    assert last.startswith("auto: 2 rounds, 4 tasks landed, 0 came back, 12 forks raced"), last
    assert "the goal's check passed" in last and "bill: $" in text
    assert (tmp_path / "take.jsonl").read_text().count("stand-in") >= 1
    # the stand-in was stopped with the take: its port refuses the connection (an alive one answers 401)
    url = urllib.parse.urlsplit(next(line for line in lines if line.startswith("stand-in at ")).split()[2])
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((url.hostname, url.port), timeout=5).close()


@needs_graphene
def test_endpoint_standin_runs_from_the_clone_when_the_graphene_on_path_is_an_installed_tool(tmp_path):
    """`uv tool install` leaves a `graphene` with no python beside it on PATH, which is how Alex has it. The
    stand-in must still start with an interpreter that imports graphene_map and the clone's tests."""
    toolbin = tmp_path / "bin"
    toolbin.mkdir()
    (toolbin / "graphene").write_text(f'#!/bin/sh\nexec "{shutil.which("graphene")}" "$@"\n')
    (toolbin / "graphene").chmod(0o755)
    with Fake([], key="fake-key") as f:
        # MAKE_REPO=false ends the take right after the stand-in started, or died
        env = take_env(tmp_path, f, PATH=f"{toolbin}:/usr/bin:/bin", MAKE_REPO="false")
        done = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "wordkit")], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, env=env, timeout=120)  # fmt: skip
    assert "stand-in at http://127.0.0.1:" in done.stdout, done.stdout
    assert "the stand-in died" not in done.stdout and "ModuleNotFoundError" not in done.stdout
    assert f.requests == []


@needs_graphene
def test_the_install_line_names_the_newest_vsix_not_the_last_by_name(tmp_path):
    here = tmp_path / "dev" / "proof"
    here.mkdir(parents=True)
    shutil.copy(SCRIPT, here / "auto.sh")   # no standin.py beside it: it refuses after the install lines
    vscode = tmp_path / "editors" / "vscode"
    vscode.mkdir(parents=True)
    (vscode / "graphene-0.8.0.vsix").write_bytes(b"old")
    os.utime(vscode / "graphene-0.8.0.vsix", (0, 0))
    (vscode / "graphene-0.10.0.vsix").write_bytes(b"new")   # sorts before 0.8.0 by name, newer by time
    with Fake([], key="fake-key") as f:
        env = take_env(tmp_path, f)
        done = subprocess.run(["bash", str(here / "auto.sh"), str(tmp_path / "wk")], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, env=env, timeout=60)  # fmt: skip
    line = done.stdout.splitlines()[1]
    assert line == f"  code --install-extension {vscode / 'graphene-0.10.0.vsix'}", done.stdout


def test_the_rehearsal_writes_the_shots_the_readme_lists():
    script = (TAKE / "rehearse.mjs").read_text()
    names = re.findall(r"^\| `([^`]+\.png)` \|", (TAKE / "README.md").read_text(), re.M)
    assert len(names) == 9
    for name in names:
        assert (TAKE / name).exists(), name
        assert name[:-4] in script, name


@needs_graphene
def test_a_dead_stand_in_is_a_refusal_not_a_fallback(tmp_path):
    with Fake([], key="fake-key") as f:
        env = take_env(tmp_path, f, STANDIN="false")
        done = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "wordkit")], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, env=env, timeout=120)  # fmt: skip
    assert done.returncode == 1, done.stdout
    assert "refused: the stand-in died before it said its URL" in done.stdout
    assert "never reaches Token Factory" in done.stdout
    assert "$ graphene init" not in done.stdout and not (tmp_path / "wordkit").exists()
    assert f.requests == []


def test_the_header_says_each_knob_in_one_line():
    head = Path(SCRIPT).read_text().split("set -euo pipefail")[0]
    for knob in ("ENDPOINT=standin", "ENDPOINT=ollama", "ENDPOINT=nim", "PAUSE=1", "RECORD=<file>",
                 "STANDIN=<command>"):  # fmt: skip
        assert any(line.lstrip("# ").startswith(knob) for line in head.splitlines()), knob
    assert "never runs it" in head
