"""`graphene plan` and `graphene node`, end to end: a person shapes, an agent executes, and the
boundary is where the person's change to the next node takes hold."""

import io
import json
import os
import pty
import select
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from graphene_debrief.cli import build
from graphene_debrief.tui import _cli

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


def test_no_plan_says_paragraph_in_and_never_the_node_add_flags(repo):
    """`graphene plan` and plain `graphene`, with nothing planned: say it to your agent in a paragraph,
    or `graphene ask`. Both taught typing the tree with `node add` flags, each in its own words."""
    shown, plain = person("plan"), person()
    assert shown.exit_code == 0 and plain.exit_code == 1  # plain `graphene` has nothing to show
    for said in (shown.stdout, plain.stderr):
        assert said.startswith("nothing is planned here yet. Say what you want to your agent, in a paragraph")
        assert "graphene ask '<what you want>'" in said and "graphene watch" in said
        assert "--scope" not in said and "node add" not in said
    assert shown.stdout == plain.stderr  # said once, the same way


def test_the_loop_a_person_shapes_an_agent_executes_and_the_boundary_carries_the_change(repo):
    proposal = {
        "nodes": [
            {"title": "users returns ids", "scope": ["api.py"], "check": "grep -q ids api.py"},
            {"title": "document it", "scope": ["README.md"], "check": "test -f README.md", "needs": ["n1"]},
        ]
    }
    proposed = agent("plan", "propose", "-", input=json.dumps(proposal))
    assert proposed.exit_code == 0 and "n1  proposed" in proposed.stdout
    assert "2 proposed: nobody can start them until the person accepts" in proposed.stdout

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
    assert not_done.exit_code == 1
    assert "outside its scope (api.py), which only the person widens\n  schema.py\n" in not_done.stderr
    subprocess.run(["git", "checkout", "--", "schema.py"], cwd=repo, check=True)
    done = agent("node", "done")
    assert "n1 is done (check passed, nothing outside its scope)" in done.stdout
    assert done.stdout.splitlines()[-1] == (
        "next: n2 (document it) is ready: `graphene node start n2` takes it, with its contract as it "
        "stands now"
    )

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
    # the plan is printed right above it, so the line does not point at it
    assert shown.stdout.splitlines()[-1] == "next: nothing is ready for you, so you can stop"
    assert agent("node", "start", "n1").exit_code == 1
    mine = person("plan")
    assert "waiting on a person: n1 (yours to do)" in mine.stdout
    assert "n2  waiting" in mine.stdout and "waits on n1 (alex's)" in mine.stdout
    person("node", "start", "n1")
    (repo / "schema.py").write_text("TABLES = ['users']\n")
    done = person("node", "done", "n1")  # the person is told what `graphene run` would take
    assert "next: n2 (use the new table) is ready: `graphene run` runs it" in done.stdout
    assert "next: n2 (use the new table) is ready: `graphene node start n2` takes it" in agent("plan").stdout


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
    assert back.splitlines()[-1] == (
        "next: nothing is ready for you, so you can stop (graphene plan says what each leaf waits on)"
    )


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
    # nothing is moving under api, so it is one line: a plan just accepted fits a screen
    [api] = [line for line in shown if line.startswith("  api")]
    assert "sub-goal" in api and "3/14 done" in api and "11 ready" in api and "14 leaves folded" in api
    assert len(shown) == 3 and any(
        line.strip().startswith("l0 ") for line in person("plan", "--all").stdout.splitlines()
    )
    started = agent("node", "start", "l3").stdout  # the same words for the agent, with the path to the root
    assert "why:    ship invoices by email" in started and "the HTTP surface (api)" in started
    shown = person(
        "plan"
    ).stdout.splitlines()  # something is running under it now: it opens, done work folded
    assert any("✓ 3 done here" in line and "l0, l1, l2" in line for line in shown)
    assert any(line.strip().startswith("l3 ") and "running" in line for line in shown)
    assert not any(line.strip().startswith("l0 ") for line in shown)
    frame = person("watch", "--once").stdout
    assert "ship invoices by email" in frame and "just now" in frame and "l3" in frame


def test_start_done_signoff_reopen_and_run_name_the_repository(repo):
    """Recheck: node reopen and node signoff (and start, done and run) changed the plan and said
    nothing of which repository's plan they changed."""
    person("node", "add", "leaf one", "--id", "l1", "--scope", "api.py", "--check", "true", "--signoff")
    person("node", "add", "leaf two", "--id", "l2", "--scope", "schema.py", "--check", "true")
    acts = [person("node", "start", "l1")]
    (repo / "api.py").write_text("def users():\n    return [1]\n")
    acts += [person("node", "done", "l1"), person("node", "signoff", "l1")]
    acts += [
        person("node", "reopen", "l1", "--note", "not yet"),
        person("run", "--with", "true", "--node", "l2"),
    ]
    assert [a.exit_code for a in acts] == [0] * 5, [a.output for a in acts]
    assert all("(the plan of " in a.stderr for a in acts), [a.stderr for a in acts]
    # a run names it first (it runs for long), and ends with what it did, for the person
    assert acts[-1].stdout.splitlines()[-1] == "run: 1 came back (l2)"


# -- the recheck of the closing review: its regression tests --------------------


# Recheck 75 (partly)
def test_pause_resume_prompts_ack_archive_and_release_name_the_repository(repo):
    """Every write names the repository: pause, which turns enforcement off, said nothing of where."""
    person("node", "add", "leaf one", "--id", "l1", "--scope", "api.py", "--check", "true")
    agent("node", "start", "l1")
    acts = [agent("node", "release", "l1", "--why", "needs schema.py")]
    for args in ("pause", "resume", "prompts strict", "ack", "archive"):
        acts.append(person("plan", *args.split()))
    assert [a.exit_code for a in acts] == [0] * 6
    assert all("(the plan of " in a.stderr for a in acts), [a.stderr for a in acts]


def test_plan_first_is_a_setting_the_person_sees_and_sets(repo):
    """Never set, plan first is on while a plan is in force; `graphene init` sets it on; the person
    turns it off and on, and an agent may not."""
    assert "plan first: off" in person("plan", "first").stdout  # no plan in force here yet
    person("node", "add", "a leaf", "--scope", "api.py", "--check", "true")
    assert "plan first: on" in person("plan", "first").stdout  # now there is one
    turned = person("plan", "first", "off")
    assert turned.exit_code == 0 and "plan first: off" in turned.stdout
    assert "(the plan of" in turned.stderr
    assert agent("plan", "first", "on").exit_code == 1
    assert "plan first: off" in person("plan", "first").stdout
    assert person("plan", "first", "sideways").exit_code == 1


def test_init_sets_plan_first_on(repo):
    assert person("init").exit_code == 0
    assert "plan first: on" in person("plan", "first").stdout


# -- the messages, read as whoever receives them --------------------------------------------------

CLI = [
    sys.executable,
    "-c",
    "import sys; from graphene_debrief.cli import app; sys.argv[0] = 'graphene'; app()",
]


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def at_terminal(repo, args, answer: str) -> str:
    """The CLI as the person runs it at a terminal (a pty), answering the one question it asks."""
    main, tty = pty.openpty()
    proc = subprocess.Popen([*CLI, *args], cwd=repo, stdin=tty, stdout=tty, stderr=tty)
    os.close(tty)
    said, answered = b"", False
    while select.select([main], [], [], 60)[0]:
        try:
            chunk = os.read(main, 4096)
        except OSError:  # the terminal's other side is closed (Linux says it so)
            break
        if not chunk:
            break
        said += chunk
        if not answered and said.rstrip().endswith(b":"):
            os.write(main, answer.encode() + b"\n")
            answered = True
    os.close(main)
    assert proc.wait(timeout=60) == 0, said
    return said.decode().replace("\r\n", "\n")


def test_next_is_one_line_in_the_words_of_whoever_reads_it(repo):
    """A release printed a 500-character `next:` naming every leaf and why it was not ready, and a
    person was told, of themselves, that "the person" reads it and that they "can stop"."""
    for k in range(1, 5):
        person("node", "add", f"leaf {k}", "--scope", f"f{k}.txt", "--check", "true")
    agent("node", "start", "n1")
    (repo / "f1.txt").write_text("x")
    assert agent("node", "done").stdout.splitlines()[-1] == (
        "next: n2 (leaf 2) is ready, and 2 more: `graphene node start n2` takes it, with its contract as it "
        "stands now"
    )
    person("node", "start", "n2")
    (repo / "f2.txt").write_text("x")
    said = person("node", "done", "n2").stdout.splitlines()
    assert said[-1] == "next: n3 (leaf 3) is ready, and 1 more: `graphene run` runs them"
    person("node", "set", "n4", "--needs", "n3")
    agent("node", "start", "n3")
    said = person("node", "release", "n3", "--why", "not this one yet").stdout.splitlines()
    assert said[-1] == "next: nothing is ready to run (graphene plan says what each leaf waits on)"
    assert len([line for line in said if line.startswith("next:")]) == 1


def test_reopen_and_release_ask_at_a_terminal_and_refuse_in_one_line_without_one(repo, monkeypatch):
    """`reopen` without --note was Click's usage box; `release` without --why the same."""
    person("node", "add", "users", "--scope", "api.py", "--check", "true")
    agent("node", "start", "n1")
    refused = agent("node", "release", "n1")
    assert (
        refused.exit_code == 2
        and refused.stderr == "graphene node release n1 needs --why: what is in the way\n"
    )
    (repo / "api.py").write_text("def users():\n    return {}\n")
    agent("node", "done")
    refused = person("node", "reopen", "n1")
    assert (refused.exit_code, refused.stderr) == (2, "graphene node reopen n1 needs --note: what is wrong\n")
    monkeypatch.setattr(sys, "stdin", Tty())  # typed at graphene watch's `:`: refused, never asked
    assert _cli(["node", "reopen", "n1"]) == (2, "graphene node reopen n1 needs --note: what is wrong")
    said = at_terminal(repo, ["node", "reopen", "n1"], "return a dict")
    assert said.startswith("what is wrong: return a dict\nn1 is open again")  # asked in one line
    assert "sent back with: return a dict" in agent("node", "start", "n1").stdout
    said = at_terminal(repo, ["node", "release", "n1"], "the schema is in the way")
    assert said.startswith("what is in the way: the schema is in the way\nn1 handed back: the schema")
    refused = person("node", "release", "n1")  # nothing to hand back: that is said, and nothing asked
    assert (refused.exit_code, refused.stderr) == (1, "n1 is open, not running\n")


def test_every_write_ends_with_which_repository_the_same_way(repo):
    """The repository came first on some writes, last on others, and between a hand-back and its
    `next:` on a release. The screen's top line says it in the same words."""
    acts = [
        person("plan", "goal", "users come back with their ids"),
        person("node", "add", "leaf one", "--id", "l1", "--scope", "api.py", "--check", "true"),
        person("node", "set", "l1", "--goal", "ids, not rows"),
        agent("node", "start", "l1"),
        agent("node", "release", "l1", "--why", "needs schema.py", "--wants", "schema.py"),
        person("node", "widen", "l1"),
        person("node", "drop", "l1"),
        person("plan", "undo"),
        person("plan", "prompts", "strict"),
        person("plan", "first", "off"),
        person("plan", "pause"),
        person("plan", "resume"),
    ]
    for act in acts:
        assert act.exit_code == 0, act.output
        last = act.output.splitlines()[-1]
        assert last.startswith("  (the plan of ") and last == act.stderr.splitlines()[-1], act.output
    assert all(act.output.count("(the plan of ") == 1 for act in acts)


def test_refusals_say_what_was_refused_and_the_command_in_a_line(repo):
    """`which node?`, `say 'on' or 'off'`, and a reopen that lectured on the contract in three
    clauses: each is now what was refused, or what happened, and the one command."""
    assert agent("node", "done").stderr == "you hold no node: `graphene node done <id>` names one\n"
    assert (
        person("plan", "first", "sideways").stderr == "graphene plan first takes on or off, not 'sideways'\n"
    )
    assert person("node", "set", "n1").stderr == (
        "graphene node set n1 needs what to change: --title, --scope, --check, --goal, --needs, --owner, "
        "--signoff or --parent\n"
    )
    person("node", "add", "users", "--scope", "api.py", "--check", "true")
    agent("node", "start", "n1")
    (repo / "api.py").write_text("def users():\n    return {}\n")
    agent("node", "done")
    assert person("node", "reopen", "n1", "--note", "a dict").stdout == (
        "n1 is open again; whoever takes it next is shown your note (its contract is as it was: "
        "`graphene node edit n1` changes it)\n"
    )
