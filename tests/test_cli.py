"""The command line, end to end, through Typer's runner."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_debrief.cli import build

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_transcript_fixture as fixture  # noqa: E402

runner = CliRunner()


def run(*args):
    return runner.invoke(build(), list(args))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def transcript(repo, tmp_path, monkeypatch):
    """The synthetic fixture, re-rendered with this repo as its cwd."""
    monkeypatch.setattr(fixture, "CWD", str(repo))
    out = tmp_path / "transcripts"
    for path, text in fixture.render().items():
        target = out / path.relative_to(fixture.OUT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return out / f"{fixture.SID}.jsonl"


def test_version_and_help():
    assert "graphene 0.1.0" in run("--version").output
    assert "debrief" in run().output


def test_init_installs_hooks_and_ignores_the_store(repo):
    first = run("init")
    assert first.exit_code == 0, first.output
    assert "SessionStart" in first.output
    settings = json.loads((repo / ".claude" / "settings.json").read_text())
    assert set(settings["hooks"]) == {
        "SessionStart",
        "UserPromptSubmit",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
    }
    assert ".graphene/" in (repo / ".gitignore").read_text()
    assert (repo / ".graphene" / "graphene.db").exists()
    assert "already installed" in run("init").output


def test_empty_store_messages(repo):
    assert "no sessions recorded yet" in run("sessions").output
    result = run("debrief", "--explain", "none")
    assert result.exit_code == 1
    assert run("ingest").exit_code == 1


def test_backfill_debrief_and_why(repo, transcript):
    loaded = run("ingest", "--backfill", "--transcript", str(transcript))
    assert loaded.exit_code == 0, loaded.output
    assert "added 1" in loaded.output
    assert fixture.SID[:8] in run("sessions").output

    as_json = run("debrief", "--json", "--explain", "none")
    assert as_json.exit_code == 0, as_json.output
    data = json.loads(as_json.output)
    assert [p["ordinal"] for p in data["prompts"]] == [1, 2, 3]
    assert data["files_changed"] == 3
    assert [f["path"] for f in data["prompts"][0]["files"]] == ["app/hello.py", "tests/test_hello.py"]
    assert data["reverted"] == [{"path": "README.md", "session_id": fixture.SID, "prompt_ordinal": 3}]
    assert [r["rerun_passed"] for r in data["reruns"]] == [True]

    out = repo / "debrief.md"
    written = run("debrief", fixture.SID[:8], "--md", str(out), "--explain", "none")
    assert written.exit_code == 0, written.output
    assert out.read_text().startswith("# Graphene debrief")

    plain = run("debrief", "--since", "2026-01-01", "--explain", "none", "--full")
    assert plain.exit_code == 0 and "What you asked" in plain.output

    assert run("debrief", "zzz", "--explain", "none").exit_code == 2
    assert run("debrief", "--since", "soon", "--explain", "none").exit_code == 2
    assert run("debrief", "--explain", "gpt").exit_code == 2

    history = run("why", "README.md")
    assert history.exit_code == 0, history.output
    assert "1 prompt(s)" in history.output and "reverted" in history.output
    assert run("why", "nope.txt").exit_code == 1

    (repo / "app").mkdir()
    (repo / "app" / "hello.py").write_text(fixture.HELLO_V2)
    line = run("why", "app/hello.py:2")
    assert line.exit_code == 0, line.output
    assert "not committed" in line.output and "prompt 1" in line.output
    assert run("why", "app/hello.py:99").exit_code == 1


def test_debrief_runs_are_recorded_so_the_next_one_is_incremental(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    first = json.loads(run("debrief", "--json", "--explain", "none").output)
    assert [s["id"] for s in first["sessions"]] == [fixture.SID]
    again = json.loads(run("debrief", "--json", "--explain", "none").output)
    assert [s["id"] for s in again["sessions"]] == [fixture.SID]  # nothing newer: falls back to the latest


def test_commands_refuse_to_run_outside_a_git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("init")
    assert result.exit_code == 2
    assert not (tmp_path / ".claude").exists() and not (tmp_path / ".graphene").exists()
    assert run("sessions").exit_code == 2
