"""`graphene demo`: a recorded run, replayed as `graphene watch` shows it, for someone with no key. The
recorder is run end to end by tests/test_demo_script.py, on the scripted stand-in; the recording Graphene
ships is the one made there, and says so."""

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from graphene_map import demo

JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)


def test_a_recording_holds_no_path_of_yours_and_nothing_shaped_like_a_key(tmp_path, monkeypatch):
    """The repository's path is `{repo}`, the home directory `~`, the key in the environment and anything
    shaped like one are gone whole; ids, log names, shas and model names stay as they were."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NEBIUS_API_KEY", "v1.not-shaped-like-one")
    root = tmp_path / "work" / "feeds"
    hide, _ = demo.hider(root)
    kept = "greet-20260926T034451-1106252f-1.txt nvidia/Llama-3_1-Nemotron-Ultra-253B-v1 9f86d081884c7d659a2f"
    said = hide(f"{root}/.graphene/runs/{kept} in {tmp_path}/elsewhere; {JWT}; v1.not-shaped-like-one")
    assert said == f"{{repo}}/.graphene/runs/{kept} in ~/elsewhere; {demo.REMOVED}; [removed]"
    detail = json.dumps({"checkout": f"{root}/.graphene/worktrees/greet", "token": f"Bearer {JWT}"})
    assert json.loads(hide({"detail": detail})["detail"]) == {
        "checkout": "{repo}/.graphene/worktrees/greet", "token": f"Bearer {demo.REMOVED}"
    }


def test_the_recording_graphene_ships_is_the_stand_ins_and_holds_no_path_and_no_key():
    """Made by tests/test_demo_script.py against the scripted fake, it says so, and carries no absolute path
    (the run's was a temporary directory, its home another) and nothing shaped like a key."""
    said = demo.SHIPPED.read_text(encoding="utf-8")
    head, lines = demo.load(demo.SHIPPED)
    assert head["stand_in"] is True and head["shown"] == "a scripted stand-in, not Nemotron" and lines
    assert len(said.encode()) < 300_000
    assert str(Path.home()) not in said and not re.findall(r"/(?:Users|home|private|var|tmp|opt|root)/", said)
    assert not [word for word in demo.WORD.findall(said) if demo.KEY.search(word)] and "fake-key" not in said


@pytest.mark.skipif(shutil.which("uv") is None, reason="builds the wheel as CI does, with uv")
def test_the_built_wheel_carries_the_recording(tmp_path):
    source = Path(__file__).resolve().parents[1]
    built = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(source)],
                           capture_output=True, text=True, timeout=300)  # fmt: skip
    assert built.returncode == 0, built.stderr
    (wheel,) = tmp_path.glob("*.whl")
    assert "graphene_map/demo.jsonl" in zipfile.ZipFile(wheel).namelist()
