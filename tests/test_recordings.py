"""Every recording dropped into tests/recordings/ replays in CI: a live leaf from the ladder's rung 5
(`cp .graphene/practice/leaf.jsonl tests/recordings/first-light-rung-5.jsonl`), or any other `graphene demo
--record` made. Each holds no key, no project id, no home path and nothing shaped like a key (counted by
`demo.leaks`, never shown), and `graphene demo <file> --once` ends it with its top line saying what made it.
With none there, the test skips; the same check runs on the recording Graphene ships, so it is exercised."""

import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_map import demo
from graphene_map.cli import build

KEPT = Path(__file__).parent / "recordings"
FOUND = sorted(KEPT.glob("*.jsonl"))
EMPTY = "no recording in tests/recordings/ yet (rung 5 makes one)"
NONE = pytest.param(None, marks=pytest.mark.skip(reason=EMPTY))


def replays(path: Path, tmp_path: Path, monkeypatch) -> str:
    """The recording's leaks, all none, and its replay's last frame, with no key and no network."""
    held = {what: n for what, n in demo.leaks(path.read_text(encoding="utf-8")).items() if n}
    assert not held, f"{path.name} holds what a recording must not: {held}"
    head, lines = demo.load(path)
    assert lines, f"{path.name} recorded no change"

    def no_network(*_):
        raise AssertionError("graphene demo reached for the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # anywhere: no repository here
    said = CliRunner().invoke(build(), ["demo", str(path), "--once"])
    assert said.exit_code == 0, said.output
    first = said.stdout.splitlines()[0]
    assert first.startswith(f"replay · {head['shown']} · ") and demo.ENDED in first, first
    return said.stdout


@pytest.mark.parametrize("path", FOUND or [NONE], ids=lambda p: p.name if p else "none")
def test_a_recording_dropped_into_tests_recordings_replays_and_holds_no_secret(path, tmp_path, monkeypatch):
    replays(path, tmp_path, monkeypatch)


def test_the_check_runs_on_the_recording_graphene_ships(tmp_path, monkeypatch):
    assert "2 leaves, 2 done" in replays(demo.SHIPPED, tmp_path, monkeypatch)


def test_the_sandboxs_own_home_is_no_persons_path():
    """Live on 2 Oct, rung 7's third take recorded an executor running /home/leaf/.local/bin/pytest in its
    Sandbox: the sandbox user's home, which is nobody's, was counted as a person's home path."""
    from graphene_map import sandbox

    assert sandbox.USER == "leaf"
    assert demo.leaks("run /home/leaf/.local/bin/pytest -q")["a path under a home directory"] == 0
    for path in ("/home/alex/repo", "/Users/alex/repo", "/home/leafy/repo"):
        assert demo.leaks(f"ran in {path}")["a path under a home directory"] == 1, path
