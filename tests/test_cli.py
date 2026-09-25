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
    from graphene_debrief import __version__  # no literal here: a release bumps the package, not this test

    assert f"graphene {__version__}" in run("--version").output
    text = run("--help").output
    listed = [line.split()[1] for line in text.splitlines() if line.startswith("│ ") and line[2] != " "]
    commands = [name for name in listed if not name.startswith("-")]
    assert commands == ["plan", "node", "watch", "ask", "run", "init", "ui"]  # the plan, then the map
    assert "ingest" not in text  # the hooks call it; nobody types it
    assert "graphene node show" in text  # what was done for one node is where the record lives now


def test_init_installs_hooks_and_ignores_the_store(repo):
    first = run("init")
    assert first.exit_code == 0, first.output
    assert "SessionStart" in first.output
    settings = json.loads((repo / ".claude" / "settings.local.json").read_text())
    assert not (repo / ".claude" / "settings.json").exists()  # the team's file is never touched
    assert set(settings["hooks"]) == set(HOOK_EVENTS)
    assert not (repo / ".gitignore").exists()  # the store ignores itself; the repo's file is not touched
    assert (repo / ".graphene").exists()  # holding one setting: plan first is on
    assert "already installed" in run("init").output
    from graphene_debrief.store import Store

    Store.open(repo).close()  # what the first hook event does
    assert (repo / ".graphene" / ".gitignore").read_text() == "*\n"  # the store ignores itself


def test_nothing_recorded_and_nothing_to_backfill(repo):
    for args in (["ui"], ["ui", "--json"]):
        result = run(*args)
        assert result.exit_code == 1, args
        line = one_line(result)
        assert line.startswith("no Claude Code sessions for this repo yet (looked in ")
        assert project_dir_name(repo) in line  # the encoded project directory it searched
    assert run("ingest").exit_code == 1
    assert not (repo / ".graphene").exists()  # nothing to record, nothing written


def test_in_an_empty_repo_plain_graphene_leads_with_the_plan(repo):
    result = run()
    assert result.exit_code == 1
    assert one_line(result).startswith("nothing is planned here yet. Say what you want to your agent")


def test_a_missing_argument_or_option_anywhere_is_one_plain_line(repo):
    """`graphene node reopen x` without --note was Click's usage box, five lines of frame around one
    that said what was missing. One handler where the CLI starts says it, everywhere, in one line."""
    for args, line in [
        (["node", "start"], "graphene node start needs <node_id>"),
        (["ask"], "graphene ask needs <sentence>: what you want, as you would say it"),
        (["node"], "graphene node: missing command (`graphene node --help` says what it takes)"),
        (["bogus"], "graphene: no such command 'bogus' (`graphene --help` says what it takes)"),
        (["--bogus"], "graphene: no such option: --bogus (`graphene --help` says what it takes)"),
        (["run", "--parallel", "x"], "graphene run: invalid value for '--parallel': 'x' is not a valid int"),
        (["node", "release", "x", "--wants"], "graphene: option '--wants' requires an argument"),
    ]:
        result = run(*args)
        assert result.exit_code == 2, args
        assert one_line(result).startswith(line) and "Usage:" not in result.output


def test_every_commands_help_reads_as_paragraphs():
    """Typer's list of commands kept a docstring's hard line breaks (`graphene --help` broke the watch
    and ask lines mid-sentence), and Rich read the text form's `[id]` as markup and dropped it."""
    import typer.main

    def walk(command):
        for sub in getattr(command, "commands", {}).values():
            yield sub
            yield from walk(sub)

    for command in walk(typer.main.get_command(build())):
        for paragraph in (command.help or "").split("\n\n"):
            assert paragraph.startswith("\b") or "\n" not in paragraph, (command.name, paragraph)
    helped = run("plan", "propose", "--help").output
    assert "with the [id] of a node" in " ".join(helped.split()) and "[short-id]" in helped


def test_the_empty_state_knows_when_the_hooks_are_installed(repo):
    assert "`graphene init` records sessions live" in one_line(run("ui"))
    init = run("init")
    assert "next Claude Code session" in init.output and "settings.local.json is your personal" in init.output
    line = one_line(run("ui"))
    assert "hooks are installed" in line and "graphene init" not in line


def test_the_empty_first_run_says_where_it_looked(repo, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    result = run("ui")
    assert result.exit_code == 1
    line = one_line(result)
    assert line.startswith("no Claude Code sessions for this repo yet (looked in ~/.claude/projects/")
    assert "`graphene init` records sessions live" in line


def test_the_map_backfills_from_transcripts_on_its_first_run(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(fixture, "CWD", str(repo))
    target = tmp_path / "claude" / "projects" / project_dir_name(repo)
    for path, text in fixture.render().items():
        out = target / path.relative_to(fixture.OUT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    drawn = run("ui", "--json")
    assert drawn.exit_code == 0, drawn.output + drawn.stderr
    assert "loaded 1 session" in drawn.output + drawn.stderr
    graph = json.loads(drawn.stdout)
    assert graph["run"]["sessions"][0]["id"] == fixture.SID
    assert "file:app/hello.py" in {row["id"] for row in graph["rows"]}
    assert "loaded" not in run("ui", "--json").stderr  # read once; a transcript that has not changed is free


def test_every_run_picks_up_new_transcripts_without_hooks(repo, tmp_path, monkeypatch):
    """A second session reaches the map even though `graphene init` was never run."""
    monkeypatch.setattr(fixture, "CWD", str(repo))
    target = tmp_path / "claude" / "projects" / project_dir_name(repo)
    rendered = fixture.render()
    main = next(p for p in rendered if p.name == f"{fixture.SID}.jsonl")
    target.mkdir(parents=True)
    (target / main.name).write_text(rendered[main])
    first = run("ui", "--json")
    assert first.exit_code == 0 and "loaded 1 session" in first.stderr
    second_id = "22222222-2222-4333-8444-555555555555"
    later = rendered[main].replace(fixture.SID, second_id).replace("2026-03-01T", "2026-03-02T")
    (target / f"{second_id}.jsonl").write_text(later)
    again = run("ui", "--json")
    assert again.exit_code == 0, again.output + again.stderr
    assert "loaded 1 session" in again.stderr
    assert json.loads(again.stdout)["run"]["sessions"][0]["id"] == second_id  # the one that finished last
    third = run("ui", "--json")
    assert "loaded" not in third.stderr  # nothing new: no parse, no notice


def test_the_map_is_drawn_from_a_backfilled_transcript(repo, transcript):
    loaded = run("ingest", "--backfill", "--transcript", str(transcript))
    assert loaded.exit_code == 0, loaded.output
    assert "added 1" in loaded.output

    graph = json.loads(run("ui", "--json").stdout)
    assert [lane["session"] for lane in graph["lanes"] if lane["kind"] == "main"] == [fixture.SID]
    assert {row["path"] for row in graph["rows"] if row["kind"] == "file"} >= {
        "app/hello.py",
        "tests/test_hello.py",
        "README.md",
    }
    assert graph["counters"]["failures"] + graph["counters"]["refused"] >= 1

    one = run("ui", "--session", fixture.SID[:8], "--json")
    assert one.exit_code == 0, one.output
    assert [s["id"] for s in json.loads(one.stdout)["run"]["sessions"]] == [fixture.SID]
    assert run("ui", "--session", "zzz").exit_code == 2


def test_commands_refuse_to_run_outside_a_git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("init")
    assert result.exit_code == 2
    assert one_line(result) == "run this inside a git repository (no .git found above the current directory)"
    assert run().exit_code == 2
    assert not (tmp_path / ".claude").exists() and not (tmp_path / ".graphene").exists()
    assert run("ui").exit_code == 2


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


def test_a_session_that_changed_nothing_is_still_drawn(repo, tmp_path, monkeypatch):
    path = quiet_transcript(repo, tmp_path, monkeypatch)
    assert run("ingest", "--backfill", "--transcript", str(path)).exit_code == 0
    graph = json.loads(run("ui", "--json").stdout)
    assert graph["run"]["prompts"] == 1 and graph["rows"] == []  # nothing changed, so no file row


def test_a_store_another_process_is_writing_is_one_line(repo, transcript, monkeypatch):
    monkeypatch.setenv("GRAPHENE_AS", "person:alex")
    monkeypatch.setattr(store_module, "TIMEOUT", 0.2)
    run("ingest", "--backfill", "--transcript", str(transcript))
    other = sqlite3.connect(repo / ".graphene" / "graphene.db", timeout=0.2, isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")  # a hook or a backfill, mid-write
    try:
        result = run("node", "add", "the users endpoint", "--scope", "src/**", "--check", "true")
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
        result = run("ui")
        assert result.exit_code == 1
        assert one_line(result).startswith("the store .graphene/graphene.db is locked")
    finally:
        other.close()


def test_a_corrupt_store_is_rebuilt(repo):
    (repo / ".graphene").mkdir()
    (repo / ".graphene" / "graphene.db").write_text("this is not a database")
    result = run("ui")
    output = result.output + result.stderr
    assert (repo / ".graphene" / "graphene.db.corrupt.bak").exists()
    assert "store rebuilt" in output and "Traceback" not in output
    assert result.exit_code == 1  # nothing to backfill from here: the usual one-line message
    assert "no Claude Code sessions for this repo" in output


def test_init_says_how_to_turn_the_shell_change_lists_on_until_they_are(repo, tmp_path, monkeypatch):
    config = tmp_path / "claude-config"
    config.mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    assert '"bashEditDiffEnabled": true' in " ".join(run("init").output.split())
    (config / "settings.json").write_text('{"bashEditDiffEnabled": true}')
    assert "bashEditDiffEnabled" not in run("init").output
    assert (config / "settings.json").read_text() == '{"bashEditDiffEnabled": true}'  # read, never written


def test_the_page_opens_on_the_plan_in_a_repo_where_no_session_was_recorded(repo, tmp_path, monkeypatch):
    """The plan is the first screen, so a repo with a plan and no recorded run still has a page."""
    monkeypatch.setenv("GRAPHENE_AS", "person:alex")
    assert run("node", "add", "the users endpoint", "--scope", "src/api/**", "--check", "true").exit_code == 0
    out = tmp_path / "plan.html"
    result = run("ui", "--export", str(out))
    assert result.exit_code == 0, one_line(result)
    page = out.read_text(encoding="utf-8")
    assert "the users endpoint" in page and '"waiting_on_person"' in page
