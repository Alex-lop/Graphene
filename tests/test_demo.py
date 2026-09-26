"""`graphene demo`: a recorded run, replayed as `graphene watch` shows it, for someone with no key. The
recorder is run end to end by tests/test_demo_script.py, on the scripted stand-in; the recording Graphene
ships is the one made there, and says so."""

import asyncio
import json
import re
import shutil
import socket
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_map import demo, plan
from graphene_map.cli import build
from graphene_map.store import Store

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


def test_the_recording_graphene_ships_says_what_made_it_and_holds_no_path_and_no_key():
    """Tonight's was made by tests/test_demo_script.py against the scripted fake, and says so; a live one
    recorded in its place says it ran live. Neither carries an absolute path (the run's was a temporary
    directory, its home another) or anything shaped like a key."""
    said = demo.SHIPPED.read_text(encoding="utf-8")
    head, lines = demo.load(demo.SHIPPED)
    assert head["shown"] == ("a scripted stand-in, not Nemotron" if head["stand_in"] else "as it ran, live")
    assert lines
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


def test_demo_once_needs_no_key_and_no_network_and_prints_the_banner_and_the_end(tmp_path, monkeypatch):
    def no_network(*_):
        raise AssertionError("graphene demo reached for the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))  # to see the replay's repository go
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(tmp_path)  # anywhere: no repository here
    said = CliRunner().invoke(build(), ["demo", "--once"])
    assert said.exit_code == 0, said.output
    head, _ = demo.load(demo.SHIPPED)
    first, *rest = said.stdout.splitlines()
    day = head["recorded"][:10]
    assert first == f"replay · {head['shown']} · {day} · {demo.ENDED} · the plan of {head['repository']}"
    assert ("stand-in" in first) == head["stand_in"]  # tonight's is the stand-in's: "a scripted stand-in"
    assert "the plan: a friendlier app" in rest and "2 leaves, 2 done, 0 running" in said.stdout
    assert [r.split() for r in rest if r.startswith("    ✓")] == [
        ["✓", "greet", "says", "hello", "greet", "done", "·", "app.py,", "words.py"],
        ["✓", "bye", "says", "goodbye", "farewell", "done", "·", "bye.py"],
    ]
    assert not list((tmp_path / "tmp").iterdir())


def test_the_replay_at_80x24_says_so_shows_a_record_and_refuses_what_would_run(tmp_path, monkeypatch):
    """The banner names it a replay of a scripted stand-in and its day; Enter shows a leaf's record; R, y
    and every other key that would change the plan or start anything say one line and start nothing."""
    monkeypatch.setattr(demo, "LONG", 0.01)  # every wait cut short: this watches the replay end, not its pace
    head, lines = demo.load(demo.SHIPPED)
    repo = demo.repository(tmp_path, head)
    app, seen, started, real = demo.Replay(repo, head, lines), {}, [], subprocess.Popen

    def no_start(args, *more, **kw):  # git's reads (a record asks git) go through; nothing else starts
        if list(args)[:1] == ["git"]:
            return real(args, *more, **kw)
        started.append(args)
        raise OSError("a replay started a process")

    def states():
        with Store.open(repo) as store:
            return {n.id: (n.state, n.rev) for n in plan.nodes(store)}

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(200):
                if app.next == len(app.lines):
                    break
                await pilot.pause(0.05)
            await pilot.press("/", *"greet", "enter", "enter")  # search to the leaf, then its record
            await pilot.pause()
            seen["where"] = str(app.query_one("#where").render())
            seen["record"], seen["cursor"] = str(app.query_one("#detail").render()), app.selected()
            await pilot.press("escape")  # the search ends: n is the offer again, not the next match
            monkeypatch.setattr(subprocess, "Popen", no_start)
            seen["before"] = states()
            for key in ["R", "y", "r", "d", "e", "E", "a", "A", "s", "P", "w", "b", "n", ":", "x", "u", "V"]:
                await pilot.press(key)
                await pilot.pause()
                said = str(app.query_one("#status").render()).splitlines()[-1]
                seen.setdefault("said", []).append((key, said, type(app.screen).__name__))
            await pilot.press("question_mark")
            seen["help"] = type(app.screen).__name__

    asyncio.run(go())
    day = head["recorded"][:10]
    assert seen["where"] == f"replay · {head['shown']} · {day} · ended: last frame"
    assert ("stand-in" in seen["where"]) == head["stand_in"]
    assert seen["cursor"] == "greet" and "record" in seen["record"] and "holds" in seen["record"]
    assert "the check" in seen["record"] and "passed" in seen["record"]
    # the replay has the plan's log and none of the run's git history: never "no commit was made"
    record = " ".join(seen["record"].split())
    assert "no commit was made" not in record and "committed inside them cannot be read" in record
    assert [key for key, said, screen in seen["said"] if (said, screen) != (demo.REFUSED, "Screen")] == []
    assert states() == seen["before"] and started == []
    assert seen["help"] == "Help"


def test_a_long_wait_is_cut_to_three_seconds_and_the_top_line_says_by_how_much(tmp_path):
    """The recorded pace, except that a wait of more than LONG seconds is played in LONG: a 30 s wait in 3 s
    is ×10, and the top line says so while it plays."""
    head, *lines = demo.SHIPPED.read_text(encoding="utf-8").splitlines()[:3]
    first, second = (json.loads(line) for line in lines)
    recording = tmp_path / "slow.jsonl"
    recording.write_text("\n".join([head, json.dumps(first | {"t": 0.5}), json.dumps(second | {"t": 30.5})]))
    head, lines = demo.load(recording)
    assert [(line["at"], line["cut"]) for line in lines] == [(0.0, 0), (3.0, 10.0)]
    app = demo.Replay(demo.repository(tmp_path, head), head, lines)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            return str(app.query_one("#where").render()), app.next

    where, applied = asyncio.run(go())
    assert applied == 1 and where.endswith(f"not Nemotron · {head['day']} · ×10: a wait, cut")
