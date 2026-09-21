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
    (repo / "schema.py").write_text("TABLES = ['users']\n")
    person("node", "done", "n1")
    assert "next: n2, use the new table" in agent("plan").stdout


def test_sign_off_reopen_and_release_each_leave_a_line_in_the_nodes_record(repo):
    person("node", "add", "users", "--scope", "api.py", "--check", "true", "--signoff")
    agent("node", "start", "n1")
    assert "nothing inside its scope (api.py) has changed" in agent("node", "done").stderr
    (repo / "api.py").write_text("def users():\n    return {}\n")
    assert "finished and waits for a sign-off" in agent("node", "done").stdout
    assert agent("node", "signoff", "n1").exit_code == 1
    assert "n1 (sign off)" in person("plan").stdout
    person("node", "reopen", "n1", "--note", "return a dict, not a list")
    assert "sent back with: return a dict, not a list" in agent("node", "start", "n1").stdout
    agent("node", "release", "n1", "--why", "needs schema.py, which is outside my scope")
    assert "handed back: needs schema.py, which is outside my scope" in person("plan").stdout
    shown = person("node", "show", "n1").stdout
    assert "window 2:" in shown and "released: needs schema.py" in shown  # the contract, then the record
    assert "`graphene plan log` (8 for n1)" in shown
    kinds = [line.split()[2] for line in person("plan", "log").stdout.splitlines()]
    assert kinds == [
        "added", "started", "check_passed", "check_passed", "finished", "reopened", "started", "released"
    ]  # fmt: skip


def test_next_knows_what_the_caller_holds_and_never_points_back_at_a_node_just_handed_back(repo):
    person("node", "add", "users", "--scope", "api.py", "--check", "true")
    assert "the plan: 1 leaf, 0 done" in person("plan").stdout
    agent("node", "start", "n1")
    assert "next: you hold n1 (users). Finish it with `graphene node done n1`" in agent("plan").stdout
    back = agent("node", "release", "n1", "--why", "the check and the goal disagree").stdout
    assert "next: nothing is ready for you: n1 is back with the person" in back


def test_a_proposal_shows_what_it_would_wait_on_and_an_edit_says_what_it_changed(repo):
    """The second walkthrough: reviewing an agent's proposal, the edge it proposed was nowhere to be
    seen, and `node set` answered only 'revision 2'."""
    person("node", "add", "users", "--scope", "api.py", "--check", "true")
    agent("node", "add", "docs", "--scope", "README.md", "--check", "true", "--needs", "n1")
    assert "proposed by claude:5e55105e; would wait on n1; `graphene plan accept n2`" in person("plan").stdout
    assert "  needs:  n1   (it cannot start until they are done)" in person("node", "show", "n2").stdout
    edited = person("node", "set", "n2", "--scope", "docs/api.md").stdout
    assert "n2 is now revision 2:" in edited and "scope: ['README.md'] -> ['docs/api.md']" in edited
    assert "n2 is unchanged (revision 2)" in person("node", "set", "n2", "--scope", "docs/api.md").stdout


def test_a_person_can_drop_a_node_that_is_running_and_a_long_reason_is_cut_in_the_table(repo):
    person("node", "add", "probe", "--scope", "api.py", "--check", "true")
    person("node", "add", "users", "--scope", "schema.py", "--check", "true")
    agent("node", "start", "n1")
    assert agent("node", "drop", "n1").exit_code == 1
    assert person("node", "drop", "n1").exit_code == 0
    agent("node", "start", "n2")
    agent("node", "release", "n2", "--why", "because " + "the schema is not what the goal says " * 5)
    row = [line for line in person("plan").stdout.splitlines() if line.startswith("  n2")][0]
    assert row.endswith("… (`graphene node show n2` has all of it)") and len(row) < 260


def test_a_long_scope_and_a_long_title_stay_inside_their_columns(repo):
    """Found by proposing this repo's own next steps: one node with seven globs made every row
    of the plan three hundred columns wide."""
    globs = [f"src/graphene_debrief/module_{i}.py" for i in range(7)]
    args = [a for g in globs for a in ("--scope", g)]
    person(
        "node", "add", "cut the session card down to a view of one node's record", *args, "--check", "true"
    )
    [row] = [line for line in person("plan").stdout.splitlines() if line.startswith("  n1")]
    assert "src/graphene_debrief/module_0.py, +6 more" in row and "a view of one …" in row
    assert len(row) < 140
    assert all(g in person("node", "show", "n1").stdout for g in globs)  # the whole of it is one command away


def test_plain_graphene_shows_the_plan_when_there_is_one(repo):
    nothing = person()
    assert "the plan:" not in nothing.stdout  # no plan: the card's own empty state, as before
    assert not (repo / ".graphene").exists()  # and looking did not create a store
    person("node", "add", "users", "--scope", "api.py", "--check", "true")
    shown = person()
    assert shown.exit_code == 0 and "the plan: 1 leaf, 0 done, 0 running" in shown.stdout
    assert "the plan:" not in person("--json").stdout  # asking for a session's record still gives it


def test_without_a_terminal_a_person_is_still_the_person_and_a_runs_executor_is_not(repo, monkeypatch):
    for mark in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX", "AI_AGENT"):
        monkeypatch.delenv(mark, raising=False)
    result = runner.invoke(build(), ["node", "add", "x", "--scope", "a", "--check", "true"])
    assert "n1  open" in result.stdout  # never a proposal its own author cannot accept
    assert "(no terminal)" in runner.invoke(build(), ["plan", "log"]).stdout  # and the log says how
    theirs = runner.invoke(
        build(), ["node", "add", "y", "--scope", "b", "--check", "true"], env={"GRAPHENE_NODE": "n1"}
    )
    assert "n2  proposed" in theirs.stdout
    refused = runner.invoke(build(), ["plan", "accept"], env={"GRAPHENE_NODE": "n1"})
    assert refused.exit_code == 1 and "the person's to do" in refused.stderr


def test_plan_json_round_trips_through_propose(repo, tmp_path):
    person("node", "add", "users", "--scope", "api.py", "--scope", "!api_test.py", "--check", "true")
    dumped = json.loads(person("plan", "--json").stdout)
    assert dumped["nodes"][0]["scope"] == ["api.py", "!api_test.py"]
    assert person("node", "set", "n1").exit_code == 1  # nothing to change is said, not ignored
    assert "no node n9" in person("node", "show", "n9").stderr


def test_the_tree_in_the_terminal_goal_first_sub_goals_counted_and_finished_work_folded(repo, tmp_path):
    person("plan", "goal", "ship invoices by email")
    person("node", "add", "the HTTP surface", "--id", "api")  # a sub-goal needs only a title…
    tree = {"nodes": [{"id": f"l{k}", "parent": "api", "title": f"leaf {k}", "scope": [f"f{k}.txt"],
                       "check": "true"} for k in range(14)]}  # fmt: skip
    (tmp_path / "t.json").write_text(json.dumps(tree))
    assert person("plan", "propose", str(tmp_path / "t.json")).exit_code == 0
    for k in range(3):
        agent("node", "start", f"l{k}")
        (repo / f"f{k}.txt").write_text("x")
        assert agent("node", "done", f"l{k}").exit_code == 0
    shown = person("plan").stdout.splitlines()
    assert shown[0] == "the plan: ship invoices by email" and shown[1].startswith("14 leaves, 3 done")
    assert any(line.startswith("  api") and "sub-goal" in line and "3/14 done" in line for line in shown)
    assert any("✓ 3 done here" in line and "l0, l1, l2" in line for line in shown)
    assert not any(line.strip().startswith("l0 ") for line in shown)  # folded…
    assert any(line.strip().startswith("l0 ") for line in person("plan", "--all").stdout.splitlines())
    started = agent("node", "start", "l3").stdout  # the same words for the agent, with the path to the root
    assert "why:    ship invoices by email" in started and "the HTTP surface (api)" in started
    frame = person("watch", "--once").stdout
    assert "ship invoices by email" in frame and "just now" in frame and "l3" in frame
