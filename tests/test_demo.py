"""`graphene demo`: a recorded run, replayed as `graphene watch` shows it, for someone with no key. The
recorder is run end to end by tests/test_demo_script.py, on the scripted stand-in; the recording Graphene
ships is the one made there, and says so."""

import asyncio
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
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
CLI = [sys.executable, "-c", "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"]


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


def recorded(repo: Path, out: Path, during, env=None) -> tuple[dict, list[dict]]:
    """`graphene demo --record` started in ``repo`` (as nemotron.sh starts it), ``during()`` once it has
    written its first line, then TERM: the recording it made."""
    recorder = subprocess.Popen([*CLI, "demo", "--record", str(out)], cwd=repo, stderr=subprocess.PIPE,
                                text=True, env=env)  # fmt: skip
    for _ in range(100):  # its first line is written before it waits for anything
        if out.exists() and out.read_text():
            break
        time.sleep(0.1)
    during()
    recorder.send_signal(signal.SIGTERM)
    assert recorder.wait(timeout=20) == 0, recorder.stderr.read()
    return demo.load(out)


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


def test_the_recorder_waits_for_the_store_goes_on_past_what_it_cannot_read_and_stops_on_term(tmp_path):
    """`graphene demo --record` started before `graphene init` (as nemotron.sh starts it) waits for the
    store; a thing under .graphene/runs it cannot read does not stop it; TERM ends it with what it saw."""
    repo = git_repo(tmp_path / "repo")

    def during():
        (repo / ".graphene" / "runs" / "a-directory").mkdir(parents=True)
        with Store.open(repo) as store:
            store.set_meta("goal", "a goal recorded")
        time.sleep(1)

    head, lines = recorded(repo, tmp_path / "rec.jsonl", during)
    assert head["repository"] == "repo" and head["stand_in"] is False  # no stand-in's endpoint was set
    assert [line["plan_meta"] for line in lines if "plan_meta" in line] == [{"goal": "a goal recorded"}]


def test_output_written_a_few_bytes_at_a_time_loses_the_key_and_the_paths_whole(tmp_path):
    """The key and the paths were taken out of each look's new output alone, so a line an executor wrote
    across two looks (a streaming agent, a buffer flushed mid-line) kept them in pieces. The recorder takes
    whole lines, and the rest on its last look; a character is never cut in two."""
    repo, key = git_repo(tmp_path / "repo"), "v1.a-secret-not-shaped-like-a-key"
    said = f"calling with {key} in {repo}/src\nwrote {repo}/app.py → café\nthe last words, with no end"
    runs = repo / ".graphene" / "runs"
    runs.mkdir(parents=True)

    def stream():  # 3 bytes every 30 ms: the recorder looks every 200 ms, so most looks end mid-line
        with open(runs / "greet-1.txt", "wb") as log:
            data = said.encode()
            for k in range(0, len(data), 3):
                log.write(data[k : k + 3])
                log.flush()
                time.sleep(0.03)

    _, lines = recorded(repo, tmp_path / "rec.jsonl", stream, env=os.environ | {"NEBIUS_API_KEY": key})
    text = "".join(line["runs"].get("greet-1.txt", "") for line in lines if "runs" in line)
    hidden = said.replace(key, "[removed]")
    for path in (str(repo.resolve()), str(repo)):
        hidden = hidden.replace(path, "{repo}")
    assert text == hidden


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
