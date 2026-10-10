"""`graphene demo`: a recorded run, replayed as `graphene watch` shows it, for someone with no key. The
recorder is run end to end by tests/test_demo_script.py, on the scripted stand-in; the recording Graphene
ships is the one made there, and says so."""

import asyncio
import contextlib
import json
import os
import re
import select
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


def test_the_home_directory_spelled_with_dashes_goes_too(tmp_path, monkeypatch):
    """Claude Code names a folder after a path, its slashes as dashes, and its stream says that folder: a
    recording of a Claude Code run held `-Users-<name>-…` on 7 October, which the slash form never met."""
    monkeypatch.setenv("HOME", "/Users/someone")
    hide, _ = demo.hider(tmp_path / "work")
    said = hide('{"auto": "~/.claude/projects/-private-tmp--Users-someone-Desktop-x/memory/"}')
    assert "someone" not in said and demo.leaks(said)["the home directory"] == 0
    assert demo.leaks("cd /tmp/-Users-someone-Desktop")["the home directory"] == 1


def test_a_home_with_a_dot_or_an_underscore_goes_as_claude_code_dashes_it(tmp_path, monkeypatch):
    """The review of 7 October: Claude Code dashes every character of a path that is not a letter or a
    digit, so /Users/john.doe_jr names its folders -Users-john-doe-jr-…, which dashing the slashes alone
    never met: the name stayed in the recording, and the leak count said none."""
    monkeypatch.setenv("HOME", "/Users/john.doe_jr")
    hide, _ = demo.hider(tmp_path / "work")
    said = hide('{"auto": "~/.claude/projects/-Users-john-doe-jr-code-feeds/memory/"}')
    assert "john" not in said and demo.leaks(said)["the home directory"] == 0
    assert demo.leaks("cd /tmp/-Users-john-doe-jr-code")["the home directory"] == 1


def test_a_key_kept_only_in_the_keychain_is_taken_out_too(tmp_path, monkeypatch):
    from graphene_map.nemotron import keys

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(keys, "find", lambda: "tfk_madeup_abcdefghijklmnopqrstuvwxyz0123456789")
    hide, _ = demo.hider(tmp_path / "work" / "feeds")
    said = hide("the model said: tfk_madeup_abcdefghijklmnopqrstuvwxyz0123456789")
    assert said == "the model said: [removed]"


def test_a_base64_secret_with_a_slash_or_a_plus_goes_whole(tmp_path, monkeypatch):
    """A key-shaped word ends at a slash, so a base64 secret with a / or a + in it (an AWS secret access key)
    was kept in pieces. A run of 30 or more base64 characters with a capital, a small letter, a digit and a
    / or a + goes whole; a sha, a uuid, an id, a log's name and a model's name stay."""
    monkeypatch.setenv("HOME", str(tmp_path))
    hide, _ = demo.hider(tmp_path / "work" / "feeds")
    aws, plus = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "c2VjcmV0+c2VjcmV0L3NlY3JldA9zZWNyZXQ=="
    kept = ("greet-20260926T034451-1106252f-1.txt nvidia/Llama-3_1-Nemotron-Ultra-253B-v1 "
            "9f86d081884c7d659a2f3aa1b3c4d5e6f7a8b9c0 123e4567-e89b-12d3-a456-426614174000 "
            "{repo}/.graphene/runs/greet nvidia/Nemotron-3-Nano-fake")  # fmt: skip
    said = hide(f"AWS_SECRET_ACCESS_KEY={aws} then {plus}; {kept}")
    assert said == f"AWS_SECRET_ACCESS_KEY={demo.REMOVED} then {demo.REMOVED}; {kept}"


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
    assert not demo.BASE64.search(said)


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


def test_recording_into_a_directory_that_is_not_there_is_refused_in_one_line(tmp_path):
    """It was a traceback; it is one line and exit 1."""
    out = tmp_path / "no" / "such" / "rec.jsonl"
    done = subprocess.run([*CLI, "demo", "--record", str(out)], cwd=git_repo(tmp_path / "repo"),
                          capture_output=True, text=True, timeout=60)  # fmt: skip
    said = f"cannot write {out}: No such file or directory\n"
    assert (done.returncode, done.stdout, done.stderr) == (1, "", said)


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


def test_a_sandbox_image_is_taken_out_in_words_the_leafs_pane_shows_whole(tmp_path):
    """Where a sandbox's image was, the recording said "[a sandbox image]", and the leaf's pane cuts an
    image to 12 characters: "image [a sandbox i". What it says there now fits."""
    from types import SimpleNamespace

    from graphene_map.tui import Pane, _attempt

    repo, image = git_repo(tmp_path / "repo"), "sha256:" + "3f2a1b9c" * 8
    made = {"placement": "sandbox", "box": "docker", "image": image, "checkpoint": "made"}

    def during():
        with Store.open(repo) as store:
            store.log_node("greet", plan._now(), "placement", "run:nemotron", None, None, made)
        time.sleep(1)

    head, lines = recorded(repo, tmp_path / "rec.jsonl", during)
    assert "3f2a1b9c" not in (tmp_path / "rec.jsonl").read_text()
    (tmp_path / "replay").mkdir()
    replay, pane = demo.repository(tmp_path / "replay", head), Pane(60)
    demo.last_frame(replay, lines)
    with Store.open(replay) as store:
        _attempt(pane, store, SimpleNamespace(id="greet"))
    assert "sandbox made, image (not kept)" in " ".join(pane.render().plain.split())


def test_the_replay_says_live_only_when_every_model_call_on_record_went_to_token_factory(tmp_path):
    """The label came from the recorder's own environment, so a run against the fake recorded from a second
    terminal replayed "as it ran, live". It comes from the run: live only when the recorder saw it so and
    every `usage` row names who really answered (Token Factory, Claude Code, Codex); a stand-in when any
    does not, or does not say (a row recorded before rows said); and a run with no model call on record
    says that."""
    live = {"graphene demo": 1, "recorded": "2026-09-26T03:47:14.410Z", "graphene": "0.5.0",
            "repository": "r", "stand_in": False, "shown": "as it ran, live"}  # fmt: skip
    stand_in = live | {"stand_in": True, "shown": "a scripted stand-in, not Nemotron"}

    def usage(**where):
        return {"id": 1, "node_id": "*", "kind": "usage", "detail": json.dumps({"dollars": 0.01} | where)}

    tf, fake = usage(endpoint="token factory"), usage(endpoint="a stand-in")
    claude, codex = usage(endpoint="claude code"), usage(endpoint="codex")
    cases = [
        (live, [[tf], [], [tf]], "as it ran, live"),
        (live, [[claude], [codex, tf]], "as it ran, live"),  # Claude Code's run is no stand-in's
        (live, [[claude, fake]], "a scripted stand-in, not Nemotron"),
        (live, [[tf], [fake]], "a scripted stand-in, not Nemotron"),
        (live, [[tf, usage()]], "a scripted stand-in, not Nemotron"),
        (stand_in, [[tf]], "a scripted stand-in, not Nemotron"),
        (live, [[]], "a run with no model calls on record"),
        (stand_in, [[]], "a run with no model calls on record"),
    ]
    for head, rows, shown in cases:
        recording = tmp_path / "r.jsonl"
        lines = [head, *({"t": k / 10, "node_log": some} for k, some in enumerate(rows))]
        recording.write_text("\n".join(json.dumps(line) for line in lines))
        assert (demo.load(recording)[0]["shown"], rows) == (shown, rows)


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
    monkeypatch.setenv("COLUMNS", "200")  # wide enough for the whole top line
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


def test_demo_once_leaves_out_the_plans_next_step_and_nothing_else(tmp_path, monkeypatch):
    """It printed "finished; `graphene plan archive` puts it away", a command for the replay's repository,
    which is gone by then. Everything else is what `graphene watch --once` prints of the same store, the
    last rows headed as the end of the run's log, not "just now"."""
    monkeypatch.setenv("COLUMNS", "200")  # no row cut
    head, lines = demo.load(demo.SHIPPED)
    repo = demo.repository(tmp_path, head)
    demo.last_frame(repo, lines)
    monkeypatch.chdir(repo)
    watched = CliRunner().invoke(build(), ["watch", "--once"]).stdout.splitlines()
    banner, *replayed = CliRunner().invoke(build(), ["demo", "--once"]).stdout.splitlines()
    hint = "2 leaves, 2 done, 0 running · finished; `graphene plan archive` puts it away"
    assert hint in watched and banner.startswith("replay · ")
    finished = "2 leaves, 2 done, 0 running · finished"
    ending = {hint: finished, "just now": demo.ENDING}
    assert replayed == [ending.get(line, line) for line in watched]


def test_the_replay_at_80x24_says_so_shows_a_record_and_refuses_what_would_run(tmp_path, monkeypatch):
    """The banner names it a replay of a scripted stand-in and its day; Enter shows a leaf's record; R, y
    and every other key that would change the plan or start anything say one line and start nothing. (`r`
    is the replay's own: it plays it again.)"""
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
            for key in ["R", "y", "d", "e", "E", "a", "A", "s", "P", "w", "b", "n", ":", "x", "u", "V"]:
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


def test_a_sub_goals_record_mid_replay_says_its_width_at_the_replays_clock(tmp_path, monkeypatch):
    """Eight changes in, greet and farewell both run. The record of `friendly` measures them up to the
    replay's clock, as the time view does: 37% of agent minutes alone, not days of the two at once."""
    monkeypatch.setattr(demo, "LONG", 0.01)
    head, lines = demo.load(demo.SHIPPED)
    app = demo.Replay(demo.repository(tmp_path, head), head, lines[:8])

    async def go():
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(200):
                if app.next == len(app.lines):
                    break
                await pilot.pause(0.05)
            await pilot.press("/", *"friendly", "enter", "enter")  # search to the sub-goal, then its record
            await pilot.pause()
            return " ".join(str(app.query_one("#detail").render()).split())

    assert "width 2 of 2 · 37% of agent minutes alone" in asyncio.run(go())


def test_the_replay_ends_with_every_fold_open(tmp_path, monkeypatch):
    """It ended on the finished sub-goal folded to one row, "2 done": the last frame showed almost nothing.
    When the last change is applied every fold opens, as zR opens them, and every leaf is a row."""
    monkeypatch.setattr(demo, "LONG", 0.01)
    head, lines = demo.load(demo.SHIPPED)
    app = demo.Replay(demo.repository(tmp_path, head), head, lines)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(200):
                if app.next == len(app.lines):
                    break
                await pilot.pause(0.05)
            await pilot.pause()
            return [app.tree.get_node_at_line(k).data for k in range(app.tree.last_line + 1)]

    assert asyncio.run(go()) == [None, "friendly", "greet", "farewell"]


def test_a_search_line_edited_into_a_command_is_refused_in_one_line(tmp_path, monkeypatch):
    """`/` opens the search line; with its / erased, Enter ran the line as a command, and the replay's
    refusal of `did(argv, keep=True)` was a TypeError that closed the screen. A line that is not a search
    is refused with the one line, and nothing starts."""
    monkeypatch.setattr(demo, "LONG", 0.01)
    head, lines = demo.load(demo.SHIPPED)
    app, started = demo.Replay(demo.repository(tmp_path, head), head, lines), []
    monkeypatch.setattr(subprocess, "Popen", lambda args, *_, **__: started.append(args))

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            said = []
            for typed in ("plan", "undo", "ui", "run", "stop"):
                await pilot.press("/")
                await pilot.pause()
                await pilot.press("backspace", *typed, "enter")
                await pilot.pause()
                said.append((typed, str(app.query_one("#status").render()).splitlines()[-1]))
            return said, app.is_running

    said, running = asyncio.run(go())
    assert said == [(typed, demo.REFUSED) for typed in ("plan", "undo", "ui", "run", "stop")]
    assert running and started == []


@pytest.mark.parametrize("sig", [signal.SIGHUP, signal.SIGTERM])
def test_the_replays_repository_goes_when_its_terminal_closes_or_it_is_killed(tmp_path, sig):
    """The temporary repository stayed in TMPDIR when the terminal closed (HUP) or on TERM: both ended the
    process before the directory was removed. While the replay runs, both are a normal exit."""
    import fcntl
    import pty
    import struct
    import termios

    (tmp_path / "tmp").mkdir()
    main, tty = pty.openpty()
    fcntl.ioctl(tty, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    env = os.environ | {"TMPDIR": str(tmp_path / "tmp"), "TERM": "xterm-256color"}
    proc = subprocess.Popen([*CLI, "demo"], cwd=tmp_path, stdin=tty, stdout=tty, stderr=tty, env=env)
    os.close(tty)
    try:  # a replay this test fails to end is ended here: left, it outlived the test
        said, end = b"", time.monotonic() + 60
        while b"replay" not in said and time.monotonic() < end:  # a second's silence is a slow start
            if select.select([main], [], [], 1)[0]:
                said += os.read(main, 65536)
        assert b"replay" in said and list((tmp_path / "tmp").iterdir()), said  # up, over its repository
        if sig == signal.SIGHUP:
            os.close(main)  # the terminal is gone, as when its window closes
            main = None
        proc.send_signal(sig)
        while sig != signal.SIGHUP and proc.poll() is None and select.select([main], [], [], 1)[0]:
            with contextlib.suppress(OSError):  # the terminal's other side is closed (Linux says it so)
                if not os.read(main, 65536):
                    break
        proc.wait(timeout=30)
    finally:
        proc.kill()
        proc.wait()
        if main is not None:
            os.close(main)
    assert list((tmp_path / "tmp").iterdir()) == []


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


def test_a_recording_carries_the_board(tmp_path):
    repo = git_repo(tmp_path / "r")
    with Store.open(repo) as store:
        store.set_meta("board", '[{"id": "q"}]')
        assert demo._snapshot(store.conn, 0)[2]["board"] == '[{"id": "q"}]'


def test_a_tick_that_lands_once_the_screen_is_torn_down_draws_nothing(tmp_path):
    """CI, 28 September (Ubuntu, now and then): the replay's once-a-second refresh ticked while the test
    harness tore the app down. The harness removes the screen's widgets without calling exit, which is
    the only thing that stops a timer's tick, so the draw looked for #where and found nothing. A tick
    that lands once the app has stopped running now does nothing, the replay's own tick too."""
    head, lines = demo.load(demo.SHIPPED)
    for line in lines[1:]:  # an hour on: the screen is torn down mid-replay, however slow the machine is
        line["at"] += 3600
    app = demo.Replay(demo.repository(tmp_path, head), head, lines)

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app.next < len(app.lines)  # changes are left to play when the app is torn down

    asyncio.run(go())
    app.began -= 7200  # every change is due, so the replay's tick has something to apply
    app.refresh_plan()  # the screen's tick, after its widgets are gone
    app.play()  # and the replay's


def test_a_stand_in_replay_names_the_stand_in_wherever_the_recording_named_nemotron(tmp_path):
    """The top line said "a scripted stand-in, not Nemotron" while every row under it said `run:nemotron`,
    the record `Nemotron-3-Nano-fake`, and the settings `nemotron --model …`. In a stand-in's replay each
    of those names the stand-in; a live recording keeps the names it was made with."""
    head, lines = demo.load(demo.SHIPPED)
    assert head["shown"] == demo.STAND_IN
    said = json.dumps(lines)
    assert not re.findall(r"(?i)nemotron|-fake\b", said)
    assert '"actor": "run:stand-in"' in said and '"actor": "planner:stand-in"' in said
    assert "stand-in-Nano answered" in said and "stand-in --model stand-in-Ultra" in said
    usage = {"id": 1, "node_id": "g", "kind": "usage", "actor": "run:nemotron",
             "detail": json.dumps({"model": "nvidia/Nemotron-3-Nano", "endpoint": "token factory"})}
    live = {"graphene demo": 1, "recorded": "2026-09-26T03:47:14.410Z", "graphene": "0.5.0",
            "repository": "r", "stand_in": False, "shown": demo.LIVE}  # fmt: skip
    recording = tmp_path / "live.jsonl"
    recording.write_text("\n".join(json.dumps(line) for line in (live, {"t": 0, "node_log": [usage]})))
    assert demo.load(recording)[1][0]["node_log"] == [usage]


def test_demo_once_fits_80_columns_and_calls_its_last_rows_the_end_of_the_runs_log(monkeypatch, tmp_path):
    """At 80 columns the first line was 98 wide and a check's row 120; and the rows under "just now" were
    two days old. The top line keeps its whole pieces that fit, as the screen's does, each row is cut at
    the width, and the rows are the end of the run's log."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "80")
    said = CliRunner().invoke(build(), ["demo", "--once"])
    assert said.exit_code == 0, said.output
    lines = said.stdout.splitlines()
    head, _ = demo.load(demo.SHIPPED)
    assert lines[0] == f"replay · {head['shown']} · {head['day']} · {demo.ENDED}"
    assert max(len(line) for line in lines) <= 80, [line for line in lines if len(line) > 80]
    assert "just now" not in lines and demo.ENDING in lines
    assert any(line.endswith("…") and "check_passed" in line for line in lines)


def test_each_change_stays_on_the_screen_and_space_dot_and_r_pause_step_and_play_again(tmp_path):
    """The whole replay played in under four seconds, with no way to stop it. Each change now stays at
    least HOLD seconds (`--speed` divides that); space pauses where it is and plays on, `.` applies the next
    change and stays paused, `r` empties the replay and plays it from the start; the top line says which
    change it is at, and the bottom line names the three keys. Before the plan has a row the pane says
    what was asked for, not "Or :ask", which a replay refuses. A finished plan's goal row reads done."""
    head, lines = demo.load(demo.SHIPPED)
    gaps = [b["at"] - a["at"] for a, b in zip(lines, lines[1:], strict=False)]
    assert lines[0]["at"] == 0 and min(gaps) >= demo.HOLD and len(lines) * demo.HOLD > 20
    assert [line["at"] / 2 for line in lines] == [line["at"] for line in demo.load(demo.SHIPPED, 2)[1]]
    repo = demo.repository(tmp_path, head)
    app, seen = demo.Replay(repo, head, lines), {}

    def nodes():
        with Store.open(repo) as store:
            return {n.id: n.state for n in plan.nodes(store)}

    def lines_now():
        return str(app.query_one("#where").render()), str(app.query_one("#status").render()).splitlines()[1]

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            seen["first"] = (app.next, *lines_now(), " ".join(str(app.query_one("#detail").render()).split()))
            await pilot.press("space")
            await pilot.pause(demo.HOLD + 0.5)  # past when the next change was due
            seen["paused"] = (app.next, *lines_now())
            await pilot.press("full_stop")
            await pilot.pause(0.3)
            seen["stepped"] = (app.next, nodes(), *lines_now())
            await pilot.press("full_stop", *["full_stop"] * len(lines))
            await pilot.pause(0.3)
            seen["end"] = (app.next, app.tree.rows[None][:2], *lines_now())
            await pilot.press("r")
            await pilot.pause(0.3)
            seen["again"] = (app.next, nodes(), app.paused, *lines_now())

    asyncio.run(go())
    n = len(lines)
    assert seen["first"][:2] == (1, f"replay · {head['shown']} · {head['day']} · 1 of {n}")
    assert seen["first"][2].startswith("space pause · . next · r again · Enter record · l output · ? help")
    asked = "the script asked the planner: “make the app friendlier”. What it proposes is next."
    assert asked in seen["first"][3]
    assert seen["paused"][:2] == (1, f"replay · {head['shown']} · {head['day']} · paused at 1 of {n}")
    assert seen["paused"][2].startswith("space play · . next")
    proposed = dict.fromkeys(("friendly", "greet", "farewell"), "proposed")
    top = f"replay · {head['shown']} · {head['day']}"
    assert seen["stepped"][:3] == (2, proposed, f"{top} · paused at 2 of {n}")
    assert seen["end"][:3] == (n, ("✓", "done"), f"replay · {head['shown']} · {head['day']} · {demo.ENDED}")
    assert seen["end"][3].startswith("r again")
    assert seen["again"][:3] == (1, {}, None)


def test_the_replays_help_names_its_own_keys_and_none_it_refuses(tmp_path):
    head, lines = demo.load(demo.SHIPPED)
    app = demo.Replay(demo.repository(tmp_path, head), head, lines)

    async def go():
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.press("question_mark")
            await pilot.pause()
            return " ".join(str(w.render()) for w in app.screen.query("Static"))

    said = " ".join(asyncio.run(go()).split())
    assert "space pause; play on from there" in said and "r again, from the start" in said
    assert "accept, sign off" not in said and "run every ready leaf" not in said
    assert "says so here, and does nothing" in said and "the record; the executor's output" in said


def test_the_shipped_replay_puts_up_the_board_and_one_key_per_item_answers_it(tmp_path):
    """walk finding 34 (judge): neither no-key path showed the board, because the shipped recording
    predated it. It is made again on the scripted fake with a planner that puts up a question, an
    assumption and a leave-out: the screen's board rows (board_rows.read) show all three open with the
    proposal, the person takes each (y), and the question's default changes its leaf, which is told to
    that leaf's executor. A stand-in's, saying so."""
    from graphene_map import board as B
    from graphene_map import board_rows as BR

    head, lines = demo.load(demo.SHIPPED)
    assert head["stand_in"] is True and head["shown"] == demo.STAND_IN
    repo, rows = demo.repository(tmp_path, head), []
    with Store.open(repo) as store:
        for line in lines:
            demo.apply(store, line, repo)
            shown = BR.read(store, shown=bool(rows and any(rows[-1])))  # as the screen keeps rows it showed
            folded = BR.counts(shown) if shown.folded else ""
            rows.append(([(BR.word(it), it["id"]) for it in shown.open], folded))
        [question] = [it for it in B.items(store) if it["kind"] == "question"]
        farewell = plan.get(store, "farewell")
        decided = B.decided(store, farewell)
    asked = [open_ for open_, _ in rows if open_]
    assert asked[0] == [("asks", "bye-word"), ("assumes", "hello-home"), ("leaves out", "name-flag")]
    assert rows[-1] == ([], "3 settled")  # each answered with its one key, folded into one row
    assert question["state"] == "taken"
    assert question["became"] == ["farewell: goal + It says goodbye, in full."]
    assert farewell.goal.endswith("It says goodbye, in full.")
    assert "what does bye say? → goodbye, as the paragraph's friendlier app would" in decided
