# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""Workflows: a file of `workflows/` is the plan's text with a header and holes; `graphene workflow` fills
them and proposes the steps with no planner call, lists the files, and saves the plan as one. `run:` is a
command step: the run runs it by itself once what it needs has landed, a failing one stays open, and one
that leaves this machine (a push, a pull request) waits for the person's `graphene node done`. No model
runs here, and nothing leaves the machine: `origin` is a bare repository beside the test's, `gh` a script."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_run_live import repo  # noqa: F401
from typer.testing import CliRunner

from graphene_map import plan, precheck
from graphene_map import plan_text as T
from graphene_map import workflow as W
from graphene_map.cli import build
from graphene_map.plan import COMMAND, DONE, OPEN, PROPOSED, Caller, Refused
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:aaaa1111", False, "aaaa1111-session")
SHIPPED = Path(__file__).resolve().parents[1] / "workflows" / "fix-issue.md"
FIX = """\
workflow: fix
# a note, with a {{hole}} nobody declares: notes are never read
input: issue
input: area
input: test = true
goal: fix issue {{issue}}

- a test that fails for issue {{issue}}  [test-{{issue}}]
    scope: tests/{{area}}/**
    check: ! {{test}}
- the fix for issue {{issue}}  [fix-{{issue}}]
    scope: src/{{area}}/**
    check: {{test}}
    needs: test-{{issue}}
- the whole suite  [suite-{{issue}}]
    run: python3 -m unittest
    needs: fix-{{issue}}
"""
# an agent's step, then three commands: one that needs it, one beside that, and a push after the first
SHIP = """\
workflow: ship
input: what
input: see = grep -q fixed a.txt
goal: ship {{what}}

- fix {{what}}  [fix-{{what}}]
    scope: a.txt
    check: grep -q fixed a.txt
- see {{what}}  [see-{{what}}]
    run: {{see}}
    needs: fix-{{what}}
- also {{what}}  [also-{{what}}]
    run: true
    needs: fix-{{what}}
- push {{what}}  [push-{{what}}]
    run: git push origin main
    needs: see-{{what}}
"""
FIXES = "import pathlib\npathlib.Path('a.txt').write_text('fixed\\n')\n"


def person(*args):
    said = CliRunner().invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"})
    said.words = " ".join(said.output.split())  # a refusal is wrapped at the terminal's width
    return said


def git(where, *args):
    out = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def flow(repo, name: str, text: str) -> Path:
    """A file of `workflows/`, committed: a leaf's worktree is cut from HEAD."""
    path = repo / "workflows" / f"{name}.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"workflow {name}")
    return path


def nodes(repo) -> dict[str, plan.Node]:
    with Store.open(repo) as store:
        return {n.id: n for n in plan.nodes(store)}


def rows(repo, node_id: str, *kinds: str) -> list[dict]:
    with Store.open(repo) as store:
        return store.node_log(node_id, kinds)


def origin(repo) -> Path:
    """A bare repository beside the test's, as its `origin`: a push goes nowhere else."""
    bare = repo.parent / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    return bare


def executor(repo) -> str:
    script = repo.parent / "executor.py"
    script.write_text(FIXES)
    return f"{sys.executable} {script}"


# -- a workflow proposes its plan, and nobody plans ----------------------------------------------------


def test_one_workflow_run_twice_gives_two_plans_and_calls_no_planner(repo):
    flow(repo, "fix", FIX)
    marker = repo.parent / "a-planner-ran"
    with Store.open(repo) as store:  # whoever would plan or do it leaves a mark: nobody is started
        for who in ("planner", "executor"):
            store.set_meta(who, f"{sys.executable} -c \"open({str(marker)!r}, 'w')\"")
    first = person("workflow", "fix", "-i", "issue=48", "-i", "area=api", "-i", "test=pytest tests/api -q")
    assert first.exit_code == 0, first.output
    assert first.output.splitlines() == [
        "goal: fix issue 48",
        "proposed test-48: a test that fails for issue 48",
        "proposed fix-48: the fix for issue 48",
        "proposed suite-48: the whole suite",
        "next: `graphene plan accept`, or prune in `graphene watch` (y accepts, d drops)",
    ]
    second = person("workflow", "fix", "-i", "issue=49", "-i", "area=cli")  # test: its default
    assert second.exit_code == 0, second.output
    assert "proposed fix-49: the fix for issue 49" in second.output
    assert not marker.exists()
    got = nodes(repo)
    assert list(got) == ["test-48", "fix-48", "suite-48", "test-49", "fix-49", "suite-49"]
    assert {n.state for n in got.values()} == {PROPOSED}  # suggested, as `graphene ask` leaves them
    for issue, area, test in (("48", "api", "pytest tests/api -q"), ("49", "cli", "true")):
        a_test, fix, suite = (got[f"{step}-{issue}"] for step in ("test", "fix", "suite"))
        assert (a_test.title, a_test.scope, a_test.check, a_test.needs) == (
            f"a test that fails for issue {issue}", [f"tests/{area}/**"], f"! {test}", [])  # fmt: skip
        assert (fix.title, fix.scope, fix.check, fix.needs) == (
            f"the fix for issue {issue}", [f"src/{area}/**"], test, [f"test-{issue}"])  # fmt: skip
        assert (suite.scope, suite.check, suite.needs, suite.owner) == (
            [], "python3 -m unittest", [f"fix-{issue}"], COMMAND)  # fmt: skip
    with Store.open(repo) as store:
        assert plan.goal(store) == "fix issue 49"  # the goal the file names, of the one run last
        assert W.last(store) == {"name": "fix", "inputs": {"issue": "49", "area": "cli", "test": "true"}}


REFUSALS = [
    # (the file, the arguments, what the refusal says: what is wrong, then what to do)
    (FIX.replace("check: {{test}}", "check: {{tset}}"), ["-i", "issue=1", "-i", "area=a"],
     ["workflows/fix.md, line 13: {{tset}} is a hole no input declares", "Add `input: tset`"]),
    (FIX, ["-i", "issue=1", "-i", "area=a", "-i", "branch=main"],
     ["fix has no input named branch", "its inputs are issue, area, test", "`input: branch`"]),
    (FIX, ["-i", "issue=1"], ["fix needs area", "-i area=VALUE"]),
    (FIX, ["-i", "issue=1", "-i", "area="], ["fix needs area", "-i area=VALUE"]),
    (FIX, ["-i", "issue=1", "-i", "area=a\n- another step  [mine]"],
     ["-i area has a line break in it", "Write it on one line"]),
    (FIX, ["-i", "issue"], ["-i issue: an input is given as name=value"]),
    ("- a step  [one]\n    scope: a.txt\n    check: true\n", [],
     ["workflows/fix.md, line 1: this is not a workflow", "its first line is `workflow: fix`"]),
    (FIX.replace("workflow: fix", "workflow: mend"), ["-i", "issue=1", "-i", "area=a"],
     ["line 1: workflow: mend, and the file is fix.md", "write `workflow: fix`, or rename the file"]),
    (FIX.replace("input: area", "input: issue"), ["-i", "issue=1"],
     ["line 4: input: issue is declared above already", "delete one of the two"]),
    (FIX.replace("needs: fix-{{issue}}", "needs: fix-{{issue}}\n    check: true"),
     ["-i", "issue=1", "-i", "area=a"], ["workflows/fix.md, line 18: [suite-1] has run: and check:",
                                         "Delete the check: line"]),
]  # fmt: skip


@pytest.mark.parametrize(("text", "args", "says"), REFUSALS, ids=[says[0][:40] for _, _, says in REFUSALS])
def test_a_workflow_that_cannot_be_filled_is_refused_and_says_what_to_do(repo, text, args, says):
    flow(repo, "fix", text)
    said = person("workflow", "fix", *args)
    assert said.exit_code == 1, said.output
    for words in says:
        assert words in said.words
    assert nodes(repo) == {}  # and nothing was proposed


def test_inputs_that_give_ids_the_plan_has_are_refused_and_never_add_nothing_silently(repo):
    flow(repo, "fix", FIX)
    assert person("workflow", "fix", "-i", "issue=48", "-i", "area=api").exit_code == 0
    again = person("workflow", "fix", "-i", "issue=48", "-i", "area=cli")
    assert again.exit_code == 1 and "proposed" not in again.stdout
    assert "the plan already has test-48, fix-48, suite-48" in again.words
    assert "nothing was proposed. Give an input another value" in again.words
    assert len(nodes(repo)) == 3
    with Store.open(repo) as store:
        assert W.last(store)["inputs"]["area"] == "api"  # what was proposed, not what was refused
    missing = person("workflow", "mend", "-i", "issue=48")
    assert missing.exit_code == 1 and "no workflow named mend" in missing.words
    assert "here: fix" in missing.words


def test_only_a_person_runs_a_workflow(repo):
    flow(repo, "fix", FIX)
    agent = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "aaaa1111-session"}
    said = CliRunner().invoke(build(), ["workflow", "fix", "-i", "issue=1", "-i", "area=a"], env=agent)
    assert said.exit_code == 1 and "`graphene workflow` is the person's" in said.output
    assert nodes(repo) == {}


# -- the list -------------------------------------------------------------------------------------------


def test_the_list_has_every_file_its_inputs_a_broken_one_with_why_and_the_last_inputs(repo):
    empty = person("workflow", "--json")
    assert empty.exit_code == 0 and json.loads(empty.stdout) == {"workflows": [], "last": None}
    assert not (repo / ".graphene").exists()  # a listing makes no store
    flow(repo, "fix", FIX)
    flow(repo, "broken", "workflow: broken\ngoal: {{what}} is not declared\n")
    said = person("workflow", "--json")
    assert said.exit_code == 0, said.output
    assert json.loads(said.stdout) == {
        "workflows": [
            {"name": "broken", "file": "workflows/broken.md", "goal": None, "inputs": [],
             "error": "line 2: {{what}} is a hole no input declares. Add `input: what` under the workflow: "
                      "line, or take the braces off"},
            {"name": "fix", "file": "workflows/fix.md", "goal": "fix issue {{issue}}", "error": None,
             "inputs": [{"name": "issue", "default": None}, {"name": "area", "default": None},
                        {"name": "test", "default": "true"}]},
        ],
        "last": None,
    }  # fmt: skip
    assert person("workflow", "fix", "-i", "issue=7", "-i", "area=api").exit_code == 0
    last = json.loads(person("workflow", "--json").stdout)["last"]
    assert last == {"name": "fix", "inputs": {"issue": "7", "area": "api", "test": "true"}}
    lines = person("workflow").stdout.splitlines()
    assert lines[1] == "fix  inputs: issue, area, test=true  (workflows/fix.md)"
    assert lines[0].startswith("broken  cannot be read: line 2: {{what}} is a hole no input declares")


# -- `run:` in the plan's text --------------------------------------------------------------------------


def test_run_round_trips_through_the_plans_text_as_run(repo):
    text = "- the suite  [suite]\n    run: python3 -m unittest -q\n- lint  [lint]\n    run: 'ruff check'\n"
    with Store.open(repo) as store:
        assert list(T.apply(store, text, ALEX)) == ["added suite: the suite", "added lint: lint"]
        suite, lint = plan.get(store, "suite"), plan.get(store, "lint")
        assert (suite.check, suite.owner, suite.scope) == ("python3 -m unittest -q", COMMAND, [])
        assert lint.check == "ruff check" and plan.runs_itself(lint) is True
        written, opened = T.render(store)
        assert "    run: python3 -m unittest -q\n" in written and "    run: ruff check\n" in written
        assert "owner:" not in written and "check:" not in written  # written back as run:, and only so
        assert T.apply(store, written, ALEX, opened) == []  # read back, it changes nothing
        edited = written.replace("run: ruff check", "run: ruff check src\n    needs: suite")
        assert T.apply(store, edited, ALEX, opened) == ["lint: check, needs changed"]
        lint = plan.get(store, "lint")
        assert (lint.check, lint.owner, lint.needs) == ("ruff check src", COMMAND, ["suite"])
    assert "    run: ruff check src\n    needs: suite\n" in person("plan", "--text").stdout
    with Store.open(repo) as store:  # an agent's step has a scope to hold it: a command step is the person's
        with pytest.raises(Refused, match="line 2: run: is the person's to write"):
            T.apply(store, "- push it  [push]\n    run: git push\n", BOT)
        with pytest.raises(Refused, match="line 2: run: needs the command it runs"):
            T.apply(store, "- nothing  [nothing]\n    run:\n", ALEX)


def test_a_command_step_takes_no_steps_under_it(repo):
    """A sub-goal's check runs by itself as soon as its steps are done (`roll_up`), inside a run: a `run:`
    there would run with nobody's approval, and one that pushes would leave this machine. So a command step
    is a step of its own: refused in the text, and when a step is put under one later."""
    ship = "- ship it  [ship]\n    run: git push origin main\n"
    under = "  - the fix  [fix]\n      scope: a.txt\n      check: true\n"
    with Store.open(repo) as store:
        with pytest.raises(Refused, match="ship: a command step .* takes no steps under it"):
            T.apply(store, ship + under, ALEX)
        assert plan.nodes(store) == []
        T.apply(store, ship, ALEX)
        with pytest.raises(Refused, match="takes no steps under it"):
            T.apply(store, "- ship it  [ship]\n" + under, ALEX)
        assert [n.id for n in plan.nodes(store)] == ["ship"]


def test_a_file_whose_name_no_workflow_can_have_is_listed_with_why_and_no_run(repo):
    (repo / "workflows").mkdir(exist_ok=True)
    (repo / "workflows" / "2fa.md").write_text("workflow: 2fa\n- a step  [a]\n    run: true\n")
    [one] = [w for w in W.listed(repo) if w["name"] == "2fa"]
    assert one["error"].startswith("a workflow's name is a letter") and one["inputs"] == []


@pytest.mark.parametrize("other", ["scope: src/**", "check: true", "owner: me", "forks: 2"])
@pytest.mark.parametrize("first", [True, False])
def test_run_with_an_agents_key_is_refused_with_its_line(repo, other, first):
    own = ["    run: make test", f"    {other}"]
    text = "\n".join(["- a step  [a]", "    scope: a.txt", "    check: true", "- the suite  [suite]",
                      *(own if first else own[::-1])]) + "\n"  # fmt: skip
    key = other.split(":")[0]
    with Store.open(repo) as store:
        with pytest.raises(Refused) as no:
            T.apply(store, text, ALEX)
        assert str(no.value).startswith(f"line 6: [suite] has run: and {key}:. A command step is its command")
        assert f"Delete the {key}: line, or the run: line" in str(no.value)
        assert T.faults(store, text, ALEX) == [str(no.value)]
        assert plan.nodes(store) == []


@pytest.mark.parametrize(("command", "past"), [
    ("git push -u origin HEAD && gh pr create --draft --fill", True), ("gh pr create --draft", True),
    ("cd .. && git  push", True), ("uv run pytest -q", False), ("git status && gh issue list", False),
    ("./digit push-ups", False), ("legit push", False), ("git pushd", False), ("", False), (None, False),
    ("git -C ../checkout push origin HEAD", True), ("git -c push.default=current --no-pager push", True),
    ("git commit -m push", False), ("git -C x status && echo push", False), ("git log -1 push", False),
])  # fmt: skip
def test_the_line_is_git_push_and_gh_pr(command, past):
    assert W.leaves(command) is past


# -- the run -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("how", [[], ["--here"], ["--parallel", "2"]])
def test_the_run_lands_the_agents_step_runs_the_command_and_stops_at_the_line(repo, how):
    flow(repo, "ship", SHIP)
    bare = origin(repo)
    assert person("workflow", "ship", "-i", "what=a").exit_code == 0
    accepted = person("plan", "accept")
    assert "next: `graphene run` reaches fix-a, see-a, also-a" in accepted.output  # no person in its way
    assert "push-a will wait: push-a leaves this machine, so it waits for your approval" in accepted.output
    ran = person("run", "--with", executor(repo), "--no-precheck", *how)
    assert ran.exit_code == 0, ran.output
    said = ran.output.splitlines()
    for line in ("see-a started: `grep -q fixed a.txt` runs with no agent",
                 "see-a is done: its command exited 0", "also-a is done: its command exited 0"):  # fmt: skip
        assert said.count(line) == 1, ran.output
    assert said.index("fix-a is done") < said.index("see-a started: `grep -q fixed a.txt` runs with no agent")
    waits = ("push-a leaves this machine (`git push origin main`), so the run does not run it: it waits "
             "for your approval. `graphene node done push-a` runs it")  # fmt: skip
    assert ran.words.count(waits) == 1  # said once
    assert said[-1].startswith("run: 3 done · agents ")
    got = nodes(repo)
    assert [n.state for n in got.values()] == [DONE, DONE, DONE, OPEN]  # fix, see, also; the push waits
    passed = rows(repo, "see-a", "check_passed", "finished")
    assert [(e["kind"], e["actor"]) for e in passed] == [("check_passed", "run:command")] * 1 + [
        ("finished", "run:command")]  # fmt: skip
    assert passed[0]["detail"]["command"] == "grep -q fixed a.txt"
    assert passed[1]["detail"]["note"] == "its command ran and exited 0"  # nobody's word
    assert not rows(repo, "push-a", "check_passed", "check_failed")  # never run by the run
    assert git(bare, "rev-parse", "-q", "--verify", "main") is None  # and nothing left this machine
    assert "waiting on you: push-a (yours)" in person("plan").output  # the one move that is the person's
    approved = person("node", "done", "push-a")  # the person's approval: it runs the command
    assert approved.exit_code == 0, approved.output
    assert nodes(repo)["push-a"].state == DONE
    assert git(bare, "rev-parse", "main") == git(repo, "rev-parse", "main")
    assert rows(repo, "push-a", "check_passed")[0]["actor"] == "alex (no terminal)"


def test_a_command_that_fails_stays_open_and_the_run_goes_on(repo):
    flow(repo, "ship", SHIP)
    proposed = person("workflow", "ship", "-i", "what=b", "-i", "see=grep -q nothing-like-it a.txt")
    assert proposed.exit_code == 0, proposed.output
    assert person("plan", "accept").exit_code == 0
    one = person("run", "--with", executor(repo), "--no-precheck", "--node", "fix-b")  # one leaf, and no more
    assert one.exit_code == 0 and "see-b" not in one.output and "also-b" not in one.output, one.output
    assert nodes(repo)["also-b"].state == OPEN
    ran = person("run", "--with", executor(repo), "--no-precheck")
    assert ran.exit_code == 0, ran.output
    assert "see-b is not done: `grep -q nothing-like-it a.txt` failed" in ran.output
    assert "see-b stays open, and the run goes on with what does not need it" in ran.output
    assert "also-b is done: its command exited 0" in ran.output  # it does not need see-b
    assert "push-b" not in ran.output  # it needs see-b: not reached, so nothing is said of its approval
    assert ran.output.splitlines()[-1].startswith("run: 1 done, 1 command failed (see-b) · agents ")
    got = nodes(repo)
    assert (got["see-b"].state, got["also-b"].state, got["push-b"].state) == (OPEN, DONE, OPEN)
    failed = rows(repo, "see-b", "check_failed")
    assert len(failed) == 1 and failed[0]["detail"]["command"] == "grep -q nothing-like-it a.txt"
    listed = person("plan").output  # the run's to take again: nothing here waits on the person
    assert "see-b   ready" in listed and "waiting on you" not in listed and "yours" not in listed
    alone = person("run", "--with", executor(repo), "--no-precheck", "--node", "see-b")  # one command step
    assert "see-b started: " in alone.output and "see-b is not done" in alone.output
    assert alone.output.splitlines()[-1].startswith("run: 1 command failed (see-b) · agents ")
    assert len(rows(repo, "see-b", "check_failed")) == 2
    by_hand = person("node", "done", "push-b")  # the line is no way round what it needs
    assert by_hand.exit_code == 1 and "push-b waits on see-b" in by_hand.output


def test_a_check_run_first_never_runs_a_command_that_leaves_this_machine(repo):
    bare = origin(repo)
    with Store.open(repo) as store:
        T.apply(store, "- push it  [push]\n    run: git push origin main\n", ALEX)
        assert precheck._here("git push origin main", repo)[0] == 127
        ((node, verdict),) = precheck.run(store, repo)
    assert (node.id, verdict["verdict"]) == ("push", "environment")
    assert verdict["why"] == "it leaves this machine, so only your `graphene node done` runs it"
    assert git(bare, "rev-parse", "-q", "--verify", "main") is None


# -- saving a graph, and the one that ships --------------------------------------------------------------


def test_save_writes_a_file_that_proposes_the_same_plan_again(repo, tmp_path, monkeypatch):
    flow(repo, "fix", FIX)
    inputs = ["-i", "issue=48", "-i", "area=api"]
    assert person("workflow", "fix", *inputs, "-i", "test=pytest -q").exit_code == 0
    assert person("plan", "accept").exit_code == 0
    refused = person("workflow", "fix", "--save", "-i", "issue=48")
    assert refused.exit_code == 1 and "workflows/fix.md is there already" in refused.words
    assert "--force writes over it, or save this one under another name" in refused.words
    assert (repo / "workflows" / "fix.md").read_text() == FIX  # left as it is
    absent = person("workflow", "again", "--save", "-i", "issue=48", "-i", "area=web")
    assert absent.exit_code == 1 and "-i area=web: the plan's text has no 'web' in it" in absent.words
    assert "`graphene plan --text` prints the text: give a literal that is in it" in absent.words
    assert not (repo / "workflows" / "again.md").exists()
    saved = person("workflow", "again", "--save", *inputs)
    assert saved.exit_code == 0 and saved.stdout == "workflows/again.md\n", saved.output
    assert (repo / "workflows" / "again.md").read_text() == """\
workflow: again
input: issue
input: area

goal: fix issue {{issue}}

- a test that fails for issue {{issue}}  [test-{{issue}}]
    scope: tests/{{area}}/**
    check: ! pytest -q
- the fix for issue {{issue}}  [fix-{{issue}}]
    scope: src/{{area}}/**
    check: pytest -q
    needs: test-{{issue}}
- the whole suite  [suite-{{issue}}]
    run: python3 -m unittest
    needs: fix-{{issue}}
"""
    assert person("workflow", "again", "--save", "--force").exit_code == 0  # no literal: the plan as it is
    assert "{{" not in (repo / "workflows" / "again.md").read_text()
    assert person("workflow", "again", "--save", "--force", *inputs).exit_code == 0
    was = nodes(repo)
    other = tmp_path / "other"  # a second repository: the same file, the same inputs, the same plan
    other.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(other)], check=True)
    (other / "workflows").mkdir()
    (other / "workflows" / "again.md").write_text((repo / "workflows" / "again.md").read_text())
    monkeypatch.chdir(other)
    assert person("workflow", "again", *inputs).exit_code == 0
    now = nodes(other)
    assert list(now) == list(was) == ["test-48", "fix-48", "suite-48"]
    for key in ("title", "scope", "check", "needs", "owner", "parent"):
        assert {i: getattr(n, key) for i, n in now.items()} == {i: getattr(n, key) for i, n in was.items()}
    assert plan.runs_itself(now["suite-48"]) is True and plan.goal(Store.open(other)) == "fix issue 48"


def test_fix_issue_as_shipped_proposes_its_four_steps_and_its_last_step_works(repo, monkeypatch):
    shipped = W.parse(SHIPPED.read_text(), "fix-issue")
    assert shipped.inputs == {"issue": None, "file": None, "test": None, "src": "src/**",
                              "suite": "uv run pytest -q"}  # fmt: skip
    flow(repo, "fix-issue", SHIPPED.read_text())
    said = person("workflow", "fix-issue", "-i", "issue=48", "-i", "suite=python3 -m unittest",
                  "-i", "file=tests/test_export.py",
                  "-i", "test=python3 -m unittest tests.test_export")  # fmt: skip
    assert said.exit_code == 0, said.output
    assert said.stdout.splitlines()[:5] == [
        "goal: fix issue 48",
        "proposed test-48: a test that fails for issue 48",
        "proposed fix-48: the fix for issue 48",
        "proposed suite-48: the whole suite",
        "proposed pr-48: open a draft pull request",
    ]
    got = nodes(repo)
    # the first step may write the test's file alone, and is done when it is there and the test fails: a
    # check that fails before the work (no file yet), so red first does not call it hollow
    assert (got["test-48"].scope, got["test-48"].check) == (
        ["tests/test_export.py"],
        "test -e tests/test_export.py && ! python3 -m unittest tests.test_export")  # fmt: skip
    assert (got["fix-48"].scope, got["fix-48"].check, got["fix-48"].needs) == (
        ["src/**"], "python3 -m unittest tests.test_export", ["test-48"])  # fmt: skip
    assert (got["suite-48"].check, got["suite-48"].needs) == ("python3 -m unittest", ["fix-48"])
    assert got["pr-48"].needs == ["suite-48"]
    assert plan.runs_itself(got["suite-48"]) is True and plan.runs_itself(got["pr-48"]) is False
    # its last step, approved: the branch the checkout is on goes to origin, then `gh` opens the draft, from
    # the checkout. A command runs in a clean copy on no branch, where `git push origin HEAD` cannot work.
    bare, called = origin(repo), repo.parent / "gh-called"
    tools = repo.parent / "bin"
    tools.mkdir()
    (tools / "gh").write_text(f'#!/bin/sh\necho "$PWD: $*" >> {called}\n')
    (tools / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    git(repo, "switch", "-qc", "fix-48")
    with Store.open(repo) as store:
        T.apply(store, f"- open a draft pull request  [pr]\n    run: {got['pr-48'].check}\n", ALEX)
    approved = person("node", "done", "pr")
    assert approved.exit_code == 0, approved.output
    assert git(bare, "rev-parse", "fix-48") == git(repo, "rev-parse", "HEAD")
    assert git(bare, "rev-parse", "-q", "--verify", "main") is None  # the branch it is on, and no other
    assert called.read_text() == f"{repo.resolve()}: pr create --draft --fill\n"
