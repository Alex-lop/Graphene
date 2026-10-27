"""`graphene demo [RECORDING | --auto | --cheat | --live] --into DIR`: the recording played, with no screen,
into a new or empty directory that becomes the replay's own repository and store, one line a change on stdout,
on the recorded clock; then it stays at the last frame until TERM, exit 0. It never writes outside DIR,
refuses a DIR that holds anything, and the store's plan_meta key `replay` is what the snapshot's `replay`
says. The contract's section "The CLI", shape 6."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from test_run_live import CLI, wait_for

from graphene_map import demo

ENV = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}


def play(*args, cwd: Path):
    return subprocess.Popen([*CLI, "demo", *args], cwd=cwd, env=ENV, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)  # fmt: skip


def state(repo: Path) -> dict:
    said = subprocess.run([*CLI, "state", "--json"], cwd=repo, env=ENV, capture_output=True, text=True)
    return json.loads(said.stdout)


def everything_under(path: Path) -> set[str]:
    return {str(p.relative_to(path)) for p in path.rglob("*")}


def test_the_shipped_recording_plays_into_a_new_directory_a_line_a_change_and_stays(tmp_path):
    head, lines = demo.load(demo.SHIPPED, 20.0)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "outside" / "replay"  # new: made by the replay
    before = everything_under(tmp_path)
    proc = play("--into", str(target), "--speed", "20", cwd=tmp_path)
    try:
        said = [proc.stdout.readline().rstrip("\n") for _ in lines]
        assert said == [demo.what(line) for line in lines]  # one line a change, in the recording's words
        assert (target / ".git").is_dir() and (target / ".graphene" / "graphene.db").is_file()
        s = state(target)
        assert s["replay"] == {"shown": head["shown"], "day": head["day"], "repository": head["repository"]}
        assert s["repo"] == str(target.resolve()) and len(s["tasks"]) == 4
        assert {t["state"] for t in s["tasks"]} == {"done"}  # the last frame: the run as it ended
        time.sleep(0.5)
        assert proc.poll() is None  # it stays at the last frame, for the editor that watches the store
        new = everything_under(tmp_path) - before
        assert new and all(p.startswith("outside/replay") for p in new), new  # nothing outside DIR
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(10) == 0 and proc.stderr.read() == ""
        assert state(target)["replay"]  # the store stays, as a replay, for a later look
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_the_changes_come_on_the_recorded_clock_not_all_at_once(tmp_path):
    _, lines = demo.load(demo.SHIPPED, 20.0)
    proc = play("--into", str(tmp_path / "r"), "--speed", "20", cwd=tmp_path)
    try:
        began = time.monotonic()
        proc.stdout.readline()
        first = time.monotonic() - began
        for _ in lines[1:]:
            proc.stdout.readline()
        whole = time.monotonic() - began
        # the first line comes at once, the last at the recording's end (3.6 s here): not in one burst
        assert whole - first >= lines[-1]["at"] * 0.8, (first, whole, lines[-1]["at"])
    finally:
        proc.kill()
        proc.wait()


def test_auto_plays_the_stand_ins_recording_and_the_store_says_so(tmp_path):
    head, lines = demo.load(demo.AUTO_TAKE, 20.0)
    target = tmp_path / "auto"
    proc = play("--auto", "--into", str(target), "--speed", "20", cwd=tmp_path)
    try:
        assert proc.stdout.readline().rstrip("\n") == demo.what(lines[0])
        assert wait_for(lambda: (target / ".graphene" / "graphene.db").exists())
        s = state(target)
        assert s["replay"]["shown"] == demo.STAND_IN and s["replay"]["repository"] == "wordkit"
        assert s["replay"]["day"] == head["day"]
    finally:
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(10) == 0


def test_a_directory_that_holds_anything_is_refused_and_untouched(tmp_path):
    held = tmp_path / "project"
    held.mkdir()
    (held / "README.md").write_text("mine\n")
    before = everything_under(tmp_path)
    said = subprocess.run([*CLI, "demo", "--into", str(held)], cwd=tmp_path, env=ENV, capture_output=True,
                          text=True, timeout=60)  # fmt: skip
    assert said.returncode == 1 and said.stdout == "" and "holds something already" in said.stderr
    assert everything_under(tmp_path) == before
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    said = subprocess.run([*CLI, "demo", "--into", str(a_file)], cwd=tmp_path, env=ENV, capture_output=True,
                          text=True, timeout=60)  # fmt: skip
    assert said.returncode == 1 and "holds something already" in said.stderr
    for more in (("--record", "r.jsonl"), ("--once",)):
        said = subprocess.run([*CLI, "demo", "--into", str(tmp_path / "x"), *more], cwd=tmp_path, env=ENV,
                              capture_output=True, text=True, timeout=60)  # fmt: skip
        assert said.returncode == 2 and "--into plays into a directory of its own" in said.stderr
    assert not (tmp_path / "x").exists()


def test_cheat_into_a_directory_leaves_its_repository_as_a_replay(tmp_path):
    target = tmp_path / "cheat"
    proc = play("--cheat", "--into", str(target), cwd=tmp_path)
    try:
        said = []
        assert wait_for(lambda: said.append(proc.stdout.readline()) or "got through." in said[-1], 120)
        assert said[0].startswith(f"graphene demo --cheat · {demo.STAND_IN}")
        s = state(target)
        assert s["replay"]["shown"] == demo.STAND_IN and s["replay"]["repository"] == "cheat"
        assert [t["id"] for t in s["tasks"]] == ["n1"]
    finally:
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(30) == 0


def test_cheat_into_a_directory_is_a_replay_from_its_first_frame_not_after_the_moves(tmp_path):
    """The store was marked once the seven moves had run: while they ran, the only frames worth watching,
    an editor saw a real project with a running task (the editor night's review)."""
    target = tmp_path / "cheat"
    proc = play("--cheat", "--into", str(target), cwd=tmp_path)
    try:
        said = []  # the top line, then the first line after the store exists, before any move
        assert wait_for(lambda: said.append(proc.stdout.readline()) or said[-1].startswith("A throwaway"), 60)
        s = state(target)
        assert s["replay"] and s["replay"]["shown"] == demo.STAND_IN and s["replay"]["repository"] == "cheat"
        # the stand-in's leaf, at whatever move it is: a fast machine has run them all by now (CI's did)
        assert [t["id"] for t in s["tasks"]] == ["n1"] and s["tasks"][0]["state"] in ("running", "done")
        # its last frame, where the contract's exit 0 on TERM holds; a TERM mid-move is not that promise
        assert wait_for(lambda: said.append(proc.stdout.readline()) or "got through." in said[-1], 120)
    finally:
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(30) == 0


def test_the_flag_has_help_in_the_budget_and_the_reference_names_it():
    import typer.main

    from graphene_map.cli import build

    command = typer.main.get_command(build()).commands["demo"]
    (flag,) = [p for p in command.params if p.name == "into"]
    assert len(flag.help) <= 80 and "directory" in flag.help
    how = (Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text()
    assert "`graphene demo --into DIR`" in how


def test_a_replays_quiet_seconds_are_counted_on_the_recordings_clock(tmp_path):
    """Watch the Demo said "94948 s quiet" on every running task. The replay's rows are the recording's,
    and the snapshot counted from the wall clock. A replay's clock is its newest row."""
    target = tmp_path / "auto"
    proc = play("--auto", "--into", str(target), "--speed", "4", cwd=tmp_path)
    try:
        running = []

        def some_running():
            if not (target / ".git").exists():
                return False
            try:
                s = state(target)
            except Exception:  # the store is still being made
                return False
            running[:] = [t for t in s.get("tasks", []) if t["state"] == "running"]
            return bool(running)

        assert wait_for(some_running, 60)
        assert all(t["idle"] is not None and t["idle"] < 600 for t in running), [t["idle"] for t in running]
        forks = [f for t in running for f in t["forks"] if f["idle"] is not None]  # a running fork's, too
        assert all(f["idle"] < 600 for f in forks), [f["idle"] for f in forks]
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(30)
