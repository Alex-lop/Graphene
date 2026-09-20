"""`graphene plan` and `graphene node`, end to end: a person shapes, an agent executes, and the
boundary is where the person's change to the next node takes hold."""

import json
import subprocess

import pytest
from typer.testing import CliRunner

from graphene_debrief.cli import build

runner = CliRunner()
AGENT_ENV = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "5e55105e-0000-4000-8000-000000000001"}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GITHUB_ACTIONS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("USER", "alex")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "api.py").write_text("def users():\n    return []\n")
    (tmp_path / "schema.py").write_text("TABLES = []\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start"],
        cwd=tmp_path,
        check=True,
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def person(*args):
    # the runner has no terminal, and whoever has no terminal is not a person unless a script says so
    return runner.invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"})


def agent(*args, input=None):
    return runner.invoke(build(), list(args), env=AGENT_ENV, input=input)


def test_no_plan_says_how_to_make_one(repo):
    result = person("plan")
    assert result.exit_code == 0 and "no plan yet" in result.stdout


def test_the_loop_a_person_shapes_an_agent_executes_and_the_boundary_carries_the_change(repo):
    proposal = {
        "nodes": [
            {"title": "users returns ids", "scope": ["api.py"], "check": "grep -q ids api.py"},
            {"title": "document it", "scope": ["README.md"], "check": "test -f README.md", "needs": ["n1"]},
        ]
    }
    proposed = agent("plan", "propose", "-", input=json.dumps(proposal))
    assert proposed.exit_code == 0 and "n1  proposed" in proposed.stdout
    assert "Nobody can start them until a person" in proposed.stdout

    refused = agent("node", "start", "n1")
    assert refused.exit_code == 1 and "n1 is a proposal" in refused.stderr
    refused = agent("plan", "accept")
    assert refused.exit_code == 1 and "person's to do" in refused.stderr

    accepted = person("plan", "accept")
    assert "left alone, agents can reach: n1, n2" in accepted.stdout

    told = agent("node", "start", "n1")
    assert "n1 (revision 1): users returns ids" in told.stdout and "scope:  api.py" in told.stdout

    # while n1 runs, the person changes the NEXT node: another file, another check
    edited = person("node", "set", "n2", "--scope", "docs/api.md", "--check", "test -f docs/api.md")
    assert "n2 is now revision 2" in edited.stdout

    (repo / "api.py").write_text("def users():\n    return ids\n")
    (repo / "schema.py").write_text("TABLES = ['sneaky']\n")
    not_done = agent("node", "done")
    assert not_done.exit_code == 1 and "changed outside its scope (api.py): schema.py" in not_done.stderr
    subprocess.run(["git", "checkout", "--", "schema.py"], cwd=repo, check=True)
    done = agent("node", "done")
    assert "n1 is done (check passed, nothing outside its scope)" in done.stdout
    assert "next: n2, document it" in done.stdout and "may have changed since you last saw it" in done.stdout

    told = agent("node", "start", "n2")  # the contract at the boundary is the person's, not the proposal's
    assert "n2 (revision 2)" in told.stdout and "scope:  docs/api.md" in told.stdout
    assert "`test -f docs/api.md` passes" in told.stdout

    (repo / "README.md").write_text("what the agent first meant to write\n")
    assert "README.md" in agent("node", "done", "n2").stderr
    (repo / "README.md").unlink()
    (repo / "docs").mkdir()
    (repo / "docs" / "api.md").write_text("users() returns ids\n")
    assert "next: nothing; every node is done" in agent("node", "done", "n2").stdout


def test_a_persons_node_makes_the_agent_stop_and_shows_the_person_why(repo):
    person("node", "add", "the migration", "--scope", "schema.py", "--check", "true", "--owner", "me")
    person("node", "add", "use the new table", "--scope", "api.py", "--check", "true", "--needs", "n1")
    shown = agent("plan")
    assert "next: nothing is ready for you: n1 is alex's; n2 waits on n1 (open). You can stop" in shown.stdout
    assert agent("node", "start", "n1").exit_code == 1
    mine = person("plan")
    assert "waiting on a person: n1 (yours to do)" in mine.stdout
    assert "n2  waiting" in mine.stdout and "waits on n1 (alex's)" in mine.stdout
    person("node", "start", "n1")
    person("node", "done", "n1")
    assert "next: n2, use the new table" in agent("plan").stdout


def test_sign_off_reopen_and_release_each_leave_a_line_in_the_nodes_record(repo):
    person("node", "add", "users", "--scope", "api.py", "--check", "true", "--signoff")
    agent("node", "start", "n1")
    assert "finished and waits for a sign-off" in agent("node", "done").stdout
    assert agent("node", "signoff", "n1").exit_code == 1
    assert "n1 (sign off)" in person("plan").stdout
    person("node", "reopen", "n1", "--note", "return a dict, not a list")
    assert "sent back with: return a dict, not a list" in agent("node", "start", "n1").stdout
    agent("node", "release", "n1", "--why", "needs schema.py, which is outside my scope")
    assert "handed back: needs schema.py, which is outside my scope" in person("plan").stdout
    kinds = [line.split()[1] for line in person("node", "show", "n1").stdout.splitlines() if "Z  " in line]
    assert kinds == ["added", "started", "check_passed", "finished", "reopened", "started", "released"]


def test_without_a_terminal_nobody_is_a_person(repo):
    result = runner.invoke(build(), ["node", "add", "x", "--scope", "a", "--check", "true"])
    assert "n1  proposed" in result.stdout  # taken as a proposal, not as the person's word
    refused = runner.invoke(build(), ["plan", "accept"])
    assert refused.exit_code == 1 and "at a terminal or in the map" in refused.stderr


def test_plan_json_round_trips_through_propose(repo, tmp_path):
    person("node", "add", "users", "--scope", "api.py", "--scope", "!api_test.py", "--check", "true")
    dumped = json.loads(person("plan", "--json").stdout)
    assert dumped["nodes"][0]["scope"] == ["api.py", "!api_test.py"]
    assert person("node", "set", "n1").exit_code == 1  # nothing to change is said, not ignored
    assert "no node n9" in person("node", "show", "n9").stderr
