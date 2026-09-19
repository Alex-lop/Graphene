"""The whole record, end to end: transcripts on disk and a real git repo in, the golden graph out.

Nothing here is loaded by hand. The synthetic run is rendered into a Claude Code projects
directory, its repo and worktrees are made with git, and the product's own ingestion and commit
sync have to reach the graph that tests/fixtures/run_graph.json pins.
"""

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_debrief.cli import build
from graphene_debrief.commits import sync_commits
from graphene_debrief.graph import build_graph, to_json
from graphene_debrief.sources.claude_code import backfill
from graphene_debrief.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_run_fixture as run  # noqa: E402


@pytest.fixture
def ingested(tmp_path, monkeypatch):
    repo, elsewhere = tmp_path / "project", tmp_path / "wt-api"  # the golden names the repo "project"
    run.build_repo(repo, elsewhere)
    projects = tmp_path / "claude" / "projects"
    for name, text in run.render(root=str(repo), elsewhere=str(elsewhere)).items():
        target = projects / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    with Store.open(repo) as store:
        backfill(store, repo)
        sync_commits(store, repo, [run.S1, run.S2])
        yield store, repo, elsewhere


def normalised(text: str, repo: Path, elsewhere: Path) -> str:
    """The golden was made for the fixture's invented paths; longest first, as the mapping does."""
    for real, invented in ((elsewhere, run.ELSEWHERE), (repo, run.ROOT)):
        text = text.replace(str(real.resolve()), invented).replace(str(real), invented)
    return text


def test_transcripts_and_git_in_the_golden_graph_out(ingested):
    store, repo, elsewhere = ingested
    got = normalised(to_json(build_graph(store, [run.S1]), indent=1) + "\n", repo, elsewhere)
    assert got == (FIXTURES / "run_graph.json").read_text(encoding="utf-8")


def test_the_second_session_is_found_and_collides_across_sessions(ingested):
    store, _repo, _elsewhere = ingested
    assert {s.id for s in store.sessions()} == {run.S1, run.S2}
    graph = build_graph(store, [run.S1, run.S2])
    assert [r.path for r in graph.rows if r.collision and r.kind == "file"] == ["app/util.py", "app/api.py"]


def test_why_names_the_agent_its_task_and_the_grade(ingested, monkeypatch):
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(build(), ["why", "app/parser.py"])
    text = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "by agent 0a1b2c3d: Build the parser" in text and "recorded edit" in text
    assert "1 commit of this file in recorded sessions · 1 traced to a recorded write" in text


def said(result) -> str:
    return " ".join((result.output + result.stderr).split())


def test_why_on_a_file_only_a_commit_holds_says_so_and_that_is_an_answer(ingested, monkeypatch):
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(build(), ["why", "app/gen_a.py"])
    assert result.exit_code == 0
    assert "app/gen_a.py: changed in 1 commit during session 22222222; no recorded write." in said(result)
    assert "0 traced to a recorded write · 1 only to an agent's commit · 0 to nothing" in said(result)
    assert "1 to nothing" in said(CliRunner().invoke(build(), ["why", "pyproject.toml"]))


def test_why_never_calls_a_file_unrecorded_while_its_coverage_says_it_is_recorded(ingested, monkeypatch):
    """app/schema.py was written by a script: no payload has its diff, Claude Code's list names it."""
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(build(), ["why", "app/schema.py"])
    assert result.exit_code == 0 and "no recorded write" not in said(result)
    assert "1 recorded write, newest first; no diff was recorded" in said(result)
    assert "in Claude Code's list of what a shell command changed" in said(result)
    assert "by agent 3a4b5c6d: Generate the schema" in said(result)
    assert "1 commit of this file in recorded sessions · 1 traced to a recorded write" in said(result)


def test_a_commit_is_held_by_the_session_credited_with_it_not_by_a_window_it_falls_in(ingested, monkeypatch):
    """The guide's commit falls inside the second session's window too; the first session made it."""
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    text = said(CliRunner().invoke(build(), ["why", "docs/guide.md"]))
    assert "1 commit of this file in recorded sessions · 1 traced to a recorded write" in text


def test_the_first_card_is_the_session_that_finished_last_and_it_agrees_with_the_map(ingested, monkeypatch):
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    card = CliRunner().invoke(build(), []).output
    assert "**Session 22222222**" in card and "**Commits during the session:** 9" in card
    assert "**Coverage:** 12 committed files · 9 traced to a recorded write (6 edit, 3 shell)" in card
    other = CliRunner().invoke(build(), ["--session", "33333333"]).output
    assert "**Commits during the session:** none" in other and "no commits in the window" in other
    # what the counts are made of is on the card: the file a script wrote, and the files with no write
    assert "- `app/schema.py` changed by a shell command" in card
    assert "- only in an agent's commit: `app/gen_a.py`, `app/gen_b.py`" in card
    assert "- traced to nothing: `pyproject.toml`" in card


def test_two_sessions_on_one_card_span_first_start_to_last_end_and_overlap_counts_once(ingested, monkeypatch):
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    card = CliRunner().invoke(build(), ["--since", "2026-03-01"]).output
    assert "**Sessions 2** (22222222, 33333333) · 2026-03-02 09:00 → 09:42 +0000 · 41m ·" in card


def test_a_path_git_knows_and_no_session_touched_is_not_the_same_answer_as_a_typo(ingested, monkeypatch):
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    known = said(CliRunner().invoke(build(), ["why", "README.md"]))
    assert "no recorded prompt changed README.md; git last changed it in 319ac43" in known
    assert "no such file in this repo" in said(CliRunner().invoke(build(), ["why", "app/nope.py"]))
