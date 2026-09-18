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
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))  # no real transcripts in tests
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
    text = run("--help").output
    assert "why" in text and text.index("why") < text.index("debrief")


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


def test_nothing_recorded_and_nothing_to_backfill(repo):
    for args in ([], ["debrief"], ["sessions"], ["why", "x.py"]):
        result = run(*args)
        assert result.exit_code == 1, args
        assert "no Claude Code sessions found" in result.output + result.stderr
    assert run("ingest").exit_code == 1


def test_first_run_backfills_from_transcripts(repo, tmp_path, monkeypatch):
    from graphene_debrief.sources.claude_code import project_dir_name

    monkeypatch.setattr(fixture, "CWD", str(repo))
    target = tmp_path / "claude" / "projects" / project_dir_name(repo)
    for path, text in fixture.render().items():
        out = target / path.relative_to(fixture.OUT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    card = run()
    assert card.exit_code == 0, card.output + card.stderr
    assert "loaded 1 session" in card.output + card.stderr
    assert "Session 11111111" in card.output and "app/hello.py" in card.output
    assert "graphene init" in card.output + card.stderr  # the one-line hint, since no hooks are installed
    assert run("why", "README.md").exit_code == 0
    assert "loaded" not in run("why", "README.md").output + run("why", "README.md").stderr  # only once


def test_backfill_debrief_and_why(repo, transcript):
    loaded = run("ingest", "--backfill", "--transcript", str(transcript))
    assert loaded.exit_code == 0, loaded.output
    assert "added 1" in loaded.output
    assert fixture.SID[:8] in run("sessions").output

    card = run()
    assert card.exit_code == 0, card.output
    assert "Files changed" in card.output and "app/hello.py" in card.output and "Abandoned" in card.output
    assert "What you asked" not in card.output and "classifier" not in card.output
    assert "1 tool failure" in card.output or "tool failures" in card.output

    as_json = run("debrief", "--json", "--explain", "none")
    assert as_json.exit_code == 0, as_json.output
    data = json.loads(as_json.output)
    assert [p["ordinal"] for p in data["prompts"]] == [1, 2, 3]
    assert (
        data["files_changed"] == 4
    )  # README.md, app/hello.py, tests/test_hello.py, and the rm'd scratch.txt
    assert [f["path"] for f in data["prompts"][0]["files"]] == ["app/hello.py", "tests/test_hello.py"]
    assert [(f["path"], f["effect"]) for f in data["prompts"][2]["files"]] == [
        ("README.md", "reverted"),
        ("scratch.txt", "deleted"),
    ]
    assert data["reverted"] == [{"path": "README.md", "session_id": fixture.SID, "prompt_ordinal": 3}]
    assert [r["rerun_passed"] for r in data["reruns"]] == [True]

    out = repo / "debrief.md"
    written = run("debrief", fixture.SID[:8], "--md", str(out), "--explain", "none")
    assert written.exit_code == 0, written.output
    assert out.read_text().startswith("# Graphene\n")

    plain = run("debrief", "--since", "2026-01-01")
    assert plain.exit_code == 0 and "Files changed" in plain.output and "What you asked" not in plain.output
    full = run("debrief", "--since", "2026-01-01", "--full")
    assert full.exit_code == 0 and "What you asked" in full.output and "Keep it tiny" not in full.output

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
    assert run().exit_code == 2
    assert not (tmp_path / ".claude").exists() and not (tmp_path / ".graphene").exists()
    assert run("sessions").exit_code == 2


def test_md_into_a_missing_directory_and_together_with_json(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    nested = repo / "reports" / "today.md"
    result = run("debrief", "--md", str(nested), "--json", "--explain", "none")
    assert result.exit_code == 0, result.output
    assert nested.read_text().startswith("# Graphene\n")
    assert json.loads(result.stdout)["prompt_count"] == 3
    assert run("debrief", "--md", str(repo), "--explain", "none").exit_code == 1  # a directory: clean failure


def test_empty_window_is_not_reported_as_an_empty_store(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    result = run("debrief", "--since", "1h", "--explain", "none")
    assert result.exit_code == 1
    assert "no session in that window" in result.output + result.stderr


def test_a_corrupt_store_is_rebuilt(repo):
    (repo / ".graphene").mkdir()
    (repo / ".graphene" / "graphene.db").write_text("this is not a database")
    result = run("sessions")
    output = result.output + result.stderr
    assert (repo / ".graphene" / "graphene.db.corrupt.bak").exists()
    assert "store rebuilt" in output and "Traceback" not in output
    assert result.exit_code == 1  # nothing to backfill from here: the usual one-line message
    assert "no Claude Code sessions found" in output
