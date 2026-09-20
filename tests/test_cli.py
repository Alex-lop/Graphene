"""The command line, end to end, through Typer's runner."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_debrief import store as store_module
from graphene_debrief.cli import build
from graphene_debrief.sources.claude_code import HOOK_EVENTS, project_dir_name

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_transcript_fixture as fixture  # noqa: E402

runner = CliRunner()


def run(*args):
    return runner.invoke(build(), list(args))


def one_line(result) -> str:
    """Every refusal is exactly one line on stderr, and never a traceback."""
    text = result.stderr.strip()
    assert "Traceback" not in text, text
    assert len(text.splitlines()) == 1, text
    return text


@pytest.fixture(autouse=True)
def no_forced_colour(monkeypatch):
    """Typer forces colour under GitHub Actions (and FORCE_COLOR); the help tests read plain text."""
    for name in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS", "CLICOLOR_FORCE"):
        monkeypatch.delenv(name, raising=False)


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


def test_version_and_help_read_as_a_product():
    assert "graphene 0.2.0" in run("--version").output
    text = run("--help").output
    listed = [line.split()[1] for line in text.splitlines() if line.startswith("│ ") and line[2] != " "]
    commands = [name for name in listed if not name.startswith("-")]
    assert commands == ["plan", "node", "run", "init", "ui", "why", "sessions"]  # what will be, then what was
    assert "debrief" not in text and "ingest" not in text  # the card is `graphene` itself now
    assert "--session" in text and "--since" in text and "--json" in text
    assert "debrief" in run("debrief", "--help").output  # still there for scripts that call it
    assert "PATH:LINE" in run("why", "--help").output


def test_init_installs_hooks_and_ignores_the_store(repo):
    first = run("init")
    assert first.exit_code == 0, first.output
    assert "SessionStart" in first.output
    settings = json.loads((repo / ".claude" / "settings.local.json").read_text())
    assert not (repo / ".claude" / "settings.json").exists()  # the team's file is never touched
    assert set(settings["hooks"]) == set(HOOK_EVENTS)
    assert not (repo / ".gitignore").exists() and not (repo / ".graphene").exists()  # nothing recorded yet
    assert "already installed" in run("init").output
    from graphene_debrief.store import Store

    Store.open(repo).close()  # what the first hook event does
    assert (repo / ".graphene" / ".gitignore").read_text() == "*\n"  # the store ignores itself


def test_nothing_recorded_and_nothing_to_backfill(repo):
    for args in ([], ["debrief"], ["sessions"], ["why", "x.py"]):
        result = run(*args)
        assert result.exit_code == 1, args
        line = one_line(result)
        assert line.startswith("no Claude Code sessions for this repo yet (looked in ")
        assert project_dir_name(repo) in line  # the encoded project directory it searched
    assert run("ingest").exit_code == 1
    assert not (repo / ".graphene").exists()  # nothing to record, nothing written


def test_the_empty_state_knows_when_the_hooks_are_installed(repo):
    assert "`graphene init` records sessions live" in one_line(run())
    init = run("init")
    assert "next Claude Code session" in init.output and "settings.local.json is your personal" in init.output
    line = one_line(run())
    assert "hooks are installed" in line and "graphene init" not in line


def test_the_empty_first_run_says_where_it_looked(repo, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    result = run()
    assert result.exit_code == 1
    line = one_line(result)
    assert line.startswith("no Claude Code sessions for this repo yet (looked in ~/.claude/projects/")
    assert "`graphene init` records sessions live" in line


def test_first_run_backfills_from_transcripts(repo, tmp_path, monkeypatch):
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


def test_every_run_picks_up_new_transcripts_without_hooks(repo, tmp_path, monkeypatch):
    """A second session appears in plain `graphene` even though `graphene init` was never run."""
    monkeypatch.setattr(fixture, "CWD", str(repo))
    target = tmp_path / "claude" / "projects" / project_dir_name(repo)
    rendered = fixture.render()
    main = next(p for p in rendered if p.name == f"{fixture.SID}.jsonl")
    target.mkdir(parents=True)
    (target / main.name).write_text(rendered[main])
    first = run()
    assert first.exit_code == 0 and "loaded 1 session" in first.stderr
    second_id = "22222222-2222-4333-8444-555555555555"
    later = rendered[main].replace(fixture.SID, second_id).replace("2026-03-01T", "2026-03-02T")
    (target / f"{second_id}.jsonl").write_text(later)
    again = run()
    assert again.exit_code == 0, again.output + again.stderr
    assert "loaded 1 session" in again.stderr and "Session 22222222" in again.stdout
    third = run()
    assert "loaded" not in third.stderr  # nothing new: no parse, no notice


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

    as_json = run("--json")
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

    one = run("--session", fixture.SID[:8], "--json")
    assert one.exit_code == 0, one.output
    assert [s["id"] for s in json.loads(one.output)["sessions"]] == [fixture.SID]

    plain = run("--since", "2026-01-01")
    assert plain.exit_code == 0 and "Files changed" in plain.output and "What you asked" not in plain.output

    assert run("--session", "zzz").exit_code == 2
    assert run("--since", "soon").exit_code == 2

    history = run("why", "README.md")
    assert history.exit_code == 0, history.output
    assert "1 prompt, newest first" in history.output and "reverted" in history.output
    assert "+0/" not in history.output  # a reverted file has no net counts
    gone = run("why", "scratch.txt")
    assert gone.exit_code == 0 and "deleted (no diff available)" in gone.output and "+0/" not in gone.output
    assert run("why", "nope.txt").exit_code == 1

    (repo / "app").mkdir()
    (repo / "app" / "hello.py").write_text(fixture.HELLO_V2)
    line = run("why", "app/hello.py:2")
    assert line.exit_code == 0, line.output
    assert "not committed" in line.output and "prompt 1" in line.output
    assert run("why", "app/hello.py:99").exit_code == 1


def test_debrief_runs_are_recorded_so_the_next_one_is_incremental(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    first = json.loads(run("--json").output)
    assert [s["id"] for s in first["sessions"]] == [fixture.SID]
    again = json.loads(run("--json").output)
    assert [s["id"] for s in again["sessions"]] == [fixture.SID]  # nothing newer: falls back to the latest


def test_commands_refuse_to_run_outside_a_git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("init")
    assert result.exit_code == 2
    assert one_line(result) == "run this inside a git repository (no .git found above the current directory)"
    assert run().exit_code == 2
    assert not (tmp_path / ".claude").exists() and not (tmp_path / ".graphene").exists()
    assert run("sessions").exit_code == 2


def test_commands_refuse_to_treat_your_home_directory_as_a_repo(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".git").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(home)  # $HOME may be spelled through a symlink (/tmp on macOS); cwd is resolved
    monkeypatch.setattr(Path, "home", staticmethod(lambda: link))
    monkeypatch.chdir(home)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    result = run()
    assert result.exit_code == 2
    assert one_line(result).startswith("refusing to treat your home directory as a repo; cd into")
    assert not (home / ".graphene").exists()


def test_empty_window_is_not_reported_as_an_empty_store(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    result = run("--since", "1h")
    assert result.exit_code == 1
    assert "no session in that window" in result.output + result.stderr


def quiet_transcript(repo, tmp_path, monkeypatch) -> Path:
    """A session that only read files and ran a command: nothing was changed."""
    monkeypatch.setattr(fixture, "CWD", str(repo))
    records = [
        fixture.user_text("what does hello.py do?", "prompt-quiet", 0, 1),
        fixture.tool_use("t1", "Read", {"file_path": f"{repo}/app/hello.py"}, 0, 2),
        fixture.tool_result("t1", "def greet(name): ...", {"type": "text"}, "prompt-quiet", 0, 3),
        fixture.tool_use("t2", "Bash", {"command": "uv run pytest -q"}, 0, 4),
        fixture.tool_result("t2", "ok", fixture.bash_ok("2 passed"), "prompt-quiet", 0, 5),
    ]
    path = tmp_path / "quiet" / "99999999-2222-4333-8444-555555555555.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return path


def test_a_session_that_changed_nothing_is_one_line(repo, tmp_path, monkeypatch):
    path = quiet_transcript(repo, tmp_path, monkeypatch)
    assert run("ingest", "--backfill", "--transcript", str(path)).exit_code == 0
    result = run()
    assert result.exit_code == 1
    assert one_line(result) == ("1 session, 1 prompt, no file changes recorded; `graphene sessions` lists it")
    assert run("sessions").exit_code == 0  # and it does list it
    assert json.loads(run("--json").stdout)["prompt_count"] == 1  # --json still answers


def test_a_store_another_process_is_writing_is_one_line(repo, transcript, monkeypatch):
    monkeypatch.setattr(store_module, "TIMEOUT", 0.2)
    run("ingest", "--backfill", "--transcript", str(transcript))
    other = sqlite3.connect(repo / ".graphene" / "graphene.db", timeout=0.2, isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")  # a hook or a backfill, mid-write
    try:
        result = run()  # the lock is hit late, while recording the debrief run
        assert result.exit_code == 1
        assert one_line(result) == (
            "the store .graphene/graphene.db is locked by another graphene process "
            "(a backfill or a hook); try again in a moment"
        )
    finally:
        other.close()


def test_a_store_locked_before_it_is_even_opened_is_the_same_line(repo, monkeypatch):
    monkeypatch.setattr(store_module, "TIMEOUT", 0.2)
    (repo / ".graphene").mkdir()
    other = sqlite3.connect(repo / ".graphene" / "graphene.db", timeout=0.2, isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")  # holds the lock before Graphene can create its tables
    try:
        result = run("sessions")
        assert result.exit_code == 1
        assert one_line(result).startswith("the store .graphene/graphene.db is locked")
    finally:
        other.close()


def test_why_with_no_path_suggests_the_files_that_changed_last(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    result = run("why")
    assert result.exit_code == 2
    assert one_line(result) == "usage: graphene why <path> | <path>:<line>"
    suggestions = [line.split("  ")[0] for line in result.stdout.strip().splitlines()]
    assert 0 < len(suggestions) <= 5
    assert "app/hello.py" in suggestions
    assert not any(path.startswith("/") for path in suggestions)


def test_why_on_a_path_nothing_touched_is_one_line(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    result = run("why", "nope.txt")
    assert result.exit_code == 1
    assert one_line(result) == "nope.txt: no such file in this repo, on disk or in git's history"


def test_the_card_is_plain_text_when_stdout_is_not_a_terminal(repo, transcript):
    run("ingest", "--backfill", "--transcript", str(transcript))
    result = run()
    assert result.exit_code == 0
    assert result.stdout.startswith("# Graphene\n")
    assert "•" not in result.stdout
    assert not any(char in result.stdout for char in "─│┌┐└┘━┃╭╮╯╰")


def test_the_asset_script_renders_three_svgs(tmp_path):
    script = Path(__file__).parents[1] / "docs" / "assets" / "render_assets.py"
    done = subprocess.run(
        [sys.executable, str(script), "--out", str(tmp_path)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout + done.stderr
    for name in ("card.svg", "why-path.svg", "why-line.svg"):
        assert (tmp_path / name).read_text().startswith("<svg")


def test_a_corrupt_store_is_rebuilt(repo):
    (repo / ".graphene").mkdir()
    (repo / ".graphene" / "graphene.db").write_text("this is not a database")
    result = run("sessions")
    output = result.output + result.stderr
    assert (repo / ".graphene" / "graphene.db.corrupt.bak").exists()
    assert "store rebuilt" in output and "Traceback" not in output
    assert result.exit_code == 1  # nothing to backfill from here: the usual one-line message
    assert "no Claude Code sessions for this repo" in output


def test_why_accepts_the_paths_the_card_prints_from_a_subdirectory(repo, transcript, monkeypatch):
    run("ingest", "--backfill", "--transcript", str(transcript))
    (repo / "app").mkdir()
    (repo / "app" / "hello.py").write_text(fixture.HELLO_V2)
    monkeypatch.chdir(repo / "app")
    assert run("why", "hello.py").exit_code == 0  # relative to where you stand
    pasted = run("why", "app/hello.py")  # pasted from the card: relative to the repo root
    assert pasted.exit_code == 0, pasted.stderr
    assert "1 prompt, newest first" in pasted.stdout
    assert run("why", "app/hello.py:2").exit_code == 0
    assert run("why", "nope/hello.py").exit_code == 1


def test_init_says_how_to_turn_the_shell_change_lists_on_until_they_are(repo, tmp_path, monkeypatch):
    config = tmp_path / "claude-config"
    config.mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    assert '"bashEditDiffEnabled": true' in " ".join(run("init").output.split())
    (config / "settings.json").write_text('{"bashEditDiffEnabled": true}')
    assert "bashEditDiffEnabled" not in run("init").output
    assert (config / "settings.json").read_text() == '{"bashEditDiffEnabled": true}'  # read, never written
