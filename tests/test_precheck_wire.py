"""The commands: `run` runs the checks at the base commit first, `node reopen` takes --for."""

from __future__ import annotations

import shlex
import subprocess

import pytest
import test_plan_cli
from test_plan_cli import agent, person

from graphene_map import plan as P
from graphene_map.store import Store

repo = test_plan_cli.repo  # the fixture


def git(where, *args):
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", *args], cwd=where, check=True,
                   capture_output=True)  # fmt: skip


def verdicts(repo, node_id: str) -> list[str]:
    with Store.open(repo) as store:
        return [e["detail"]["verdict"] for e in store.node_log(node_id, ("precheck",))]


def test_a_check_that_passes_at_base_is_said_and_the_leaf_still_runs(repo):
    person("node", "add", "leaf", "--id", "l1", "--scope", "api.py", "--check", "true")
    ran = person("run", "--here", "--with", "true")
    assert ran.exit_code == 0, ran.output
    assert "l1: its check passes at the base commit" in ran.stdout
    assert "red first: 1 check at" in ran.stdout
    assert "run:" in ran.stdout.splitlines()[-1]  # the run went on to its summary


def test_no_precheck_prints_no_red_first_line(repo):
    person("node", "add", "leaf", "--id", "l1", "--scope", "api.py", "--check", "true")
    ran = person("run", "--here", "--no-precheck", "--with", "true")
    assert ran.exit_code == 0, ran.output
    assert "red first" not in ran.stdout and "base commit" not in ran.stdout


def test_a_run_of_two_leaves_prints_one_header(repo):
    for k in (1, 2):
        person("node", "add", f"leaf {k}", "--id", f"l{k}", "--scope", f"f{k}.txt", "--check", "true")
    ran = person("run", "--here", "--with", "true")
    assert ran.exit_code == 0, ran.output
    assert ran.stdout.count("red first:") == 1 and "red first: 2 checks at" in ran.stdout


@pytest.mark.parametrize("back", [False, True])
def test_run_node_checks_first_a_sub_goals_leaf_and_a_leaf_that_came_back(repo, back):
    """`--node` ran red first only on a ready leaf named itself: these two started with no check first."""
    l1 = {"id": "l1", "title": "l1", "scope": ["api.py"], "check": "true", "parent": "g"}
    with Store.open(repo) as store:
        P.propose(store, [{"id": "g", "title": "g"}, l1], P.Caller("alex", True))
    if back:
        agent("node", "start", "l1")
        agent("node", "release", "l1", "--why", "cannot")
    person("run", "--here", "--attempts", "1", "--node", "l1" if back else "g", "--with", "true")
    assert verdicts(repo, "l1") == ["passes"]


def test_a_run_refused_on_a_detached_head_runs_no_check_first(repo):
    person("node", "add", "leaf", "--id", "l1", "--scope", "api.py", "--check", "true")
    git(repo, "checkout", "-q", "--detach")
    ran = person("run", "--with", "true")
    assert ran.exit_code == 1 and "detached HEAD" in ran.stderr
    assert "red first" not in ran.stdout and verdicts(repo, "l1") == []


def test_red_first_runs_at_the_commit_a_parallel_runs_leaves_start_from(repo):
    """A leaf's worktree is cut from HEAD. An uncommitted change made its check pass at "the base commit"."""
    person("node", "add", "ids", "--id", "ids", "--scope", "api.py", "--check", "grep -q ids api.py")
    (repo / "api.py").write_text("ids = []\n")
    person("run", "--parallel", "1", "--attempts", "1", "--with", "true")
    assert verdicts(repo, "ids") == ["red"]


def test_red_first_from_a_linked_worktree_runs_at_its_commit_not_the_main_checkouts(repo, monkeypatch):
    (repo / "api.py").write_text("ids = []\n")
    git(repo, "commit", "-qam", "main has ids")
    git(repo, "worktree", "add", "-q", "-b", "feature", str(repo.parent / "linked"), "HEAD~1")
    monkeypatch.chdir(repo.parent / "linked")
    person("node", "add", "ids", "--id", "ids", "--scope", "api.py", "--check", "grep -q ids api.py")
    person("run", "--here", "--attempts", "1", "--with", "true")
    assert verdicts(repo, "ids") == ["red"]


def test_reopen_takes_several_ids_and_the_leaf_that_came_back_waits_on_them(repo):
    for k in (1, 2):
        person("node", "add", f"owner {k}", "--id", f"o{k}", "--scope", f"o{k}.txt", "--check", "true")
    person("node", "add", "leaf", "--id", "l1", "--scope", "api.py", "--check", "true")
    for k in (1, 2):
        person("node", "start", f"o{k}")
        (repo / f"o{k}.txt").write_text("x")
        person("node", "done", f"o{k}")
        person("node", "signoff", f"o{k}")
    agent("node", "start", "l1")
    agent("node", "release", "l1", "--why", "cannot")
    ran = person("node", "reopen", "o1", "o2", "--for", "l1", "--note", "wrong")
    assert ran.exit_code == 0, ran.output
    assert "o1, o2 are open again" in ran.stdout
    shown = person("node", "show", "l1").stdout
    assert "o1" in shown and "o2" in shown


def test_the_plain_prints_keys_line_has_one_r(repo):
    person("node", "add", "api work", "--id", "api", "--scope", "api.py", "--check", "true")
    agent("node", "start", "api")
    agent("node", "release", "api", "--why", "cannot")
    said = agent("plan", "--view", "outline").stdout.splitlines()[-1]
    keys = said.rsplit("; ", 1)[1].removesuffix(" in `graphene watch`").split(", ")
    assert keys.count("r") == 1, said


def r_on(repo, why: str) -> list[str]:
    """Leaf a done, and x came back wanting a's file, with ``why``: the r offer's command."""
    for i in ("a", "x"):
        person("node", "add", i, "--id", i, "--scope", f"{i}.txt", "--check", "true")
    person("node", "start", "a")
    (repo / "a.txt").write_text("x")
    person("node", "done", "a")
    person("node", "signoff", "a")
    agent("node", "start", "x")
    agent("node", "release", "x", "--why", why, "--wants", "a.txt")
    with Store.open(repo) as store:
        [argv] = [argv for key, _, argv in P.offers(store, P.get(store, "x")) if key == "r"]
    return argv


def test_plan_undo_after_r_takes_back_the_reopen_and_the_leaf_came_back_again(repo):
    """`r` is an act on the plan's shape, as w and b are: `plan undo` after it undid the act before."""
    argv = r_on(repo, "a is wrong")
    person("node", "add", "y", "--id", "y", "--scope", "y.txt", "--check", "true")
    person("node", "set", "y", "--title", "y two")
    assert person(*argv).exit_code == 0
    undone = person("plan", "undo")
    assert "undid: node reopen a" in undone.stdout, undone.output
    with Store.open(repo) as store:
        a, x, y = (P.get(store, i) for i in "axy")
        assert (a.state, x.needs, y.title) == ("done", [], "y two") and P.came_back(store, x)
        assert P.notes(store, "a") == []  # what the undone reopen said reaches no executor


def test_the_next_line_quotes_the_r_command_as_the_offer_has_it(repo):
    """r carries an executor's words. Joined with spaces, a pasted `;` in them ran as a command."""
    argv = r_on(repo, "the parse is wrong; echo PWNED")
    [line] = [line for line in agent("plan").stdout.splitlines() if line.startswith("next:")]
    assert f"`graphene {shlex.join(argv)}`" in line, line
