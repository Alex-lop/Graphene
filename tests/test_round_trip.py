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


def test_why_on_a_file_only_a_commit_holds_says_so_instead_of_nothing(ingested, monkeypatch):
    _store, repo, _elsewhere = ingested
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(build(), ["why", "app/gen_a.py"])
    said = " ".join((result.output + result.stderr).split())
    assert result.exit_code == 1
    assert "app/gen_a.py: changed in 1 commit during session 22222222; no recorded write." in said
    assert "0 traced to a recorded write · 1 only to an agent's commit · 0 to nothing" in said
    stray = CliRunner().invoke(build(), ["why", "pyproject.toml"])
    assert "1 to nothing" in " ".join((stray.output + stray.stderr).split())
