# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli and test_config_cli are named again as arguments)
"""`review: every`, end to end on the command line with the run's scripted executor (no model): turned on
in `graphene config edit`, a task whose check passes is left in review on its branch and nothing reaches
your checkout; `graphene node diff` shows what waits and `graphene node signoff` merges it. Off, nothing
changes."""

import subprocess

import pytest
from test_config_cli import editor, no_agent_marks  # noqa: F401  (fixtures)
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import plan as P
from graphene_map.store import Store

WRITES = "sh -c 'echo $GRAPHENE_NODE > $GRAPHENE_NODE.txt'"  # the executor: a script, no model


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def task(repo, every: bool, monkeypatch, tmp_path):
    if every:
        editor(monkeypatch, tmp_path, "text = text.replace('review: off', 'review: every')")
        edited = person("config", "edit")
        assert edited.exit_code == 0 and "added: review: every" in edited.stdout, edited.output
    said = person("node", "add", "write a", "--id", "a", "--scope", "a.txt", "--check", "test -s a.txt")
    assert said.exit_code == 0, said.output


def state(repo, node_id="a"):
    with Store.open(repo) as store:
        return P.get(store, node_id).state


def test_config_says_what_review_does_and_that_it_is_off(repo):
    shown = person("config").stdout.splitlines()
    said = ("# review: off (the check decides) "
            "or every (a proven task waits for your sign-off before it lands)")  # fmt: skip
    assert said in shown and "review: off" in shown


def test_a_passed_task_waits_on_its_branch_and_the_sign_off_merges_it(repo, monkeypatch, tmp_path):
    task(repo, True, monkeypatch, tmp_path)
    assert "\nreview: every\n" in person("config").stdout
    head = git(repo, "rev-parse", "HEAD")
    ran = person("run", "--with", WRITES, "--no-precheck")
    assert ran.exit_code == 0, ran.output
    assert "a passed; it waits for your sign-off before it lands" in ran.stdout
    said = ran.stdout.splitlines()  # the run says so before anything, under the line that says where it lands
    landing = next(k for k, line in enumerate(said) if line.startswith("landing into "))
    assert said[landing + 1] == "review: every: a task that passes waits for your sign-off before it lands"
    assert ran.stdout.splitlines()[-1].startswith("run: 1 in review (a)")
    assert state(repo) == P.REVIEW and git(repo, "rev-parse", "HEAD") == head  # nothing merged
    assert not (repo / "a.txt").exists() and git(repo, "show", "graphene/a:a.txt") == "a\n"
    diff = person("node", "diff", "a")
    assert diff.exit_code == 0 and "+a" in diff.stdout.splitlines(), diff.output  # what you look at first
    signed = person("node", "signoff", "a")
    assert signed.exit_code == 0 and "a is done (signed off)" in signed.stdout, signed.output
    assert state(repo) == P.DONE and (repo / "a.txt").read_text() == "a\n"
    assert git(repo, "rev-parse", "HEAD^2") and "graphene/a" not in git(repo, "branch", "--list")  # a merge


def test_a_task_run_here_waits_in_your_checkout_until_signed_off(repo, monkeypatch, tmp_path):
    task(repo, True, monkeypatch, tmp_path)
    ran = person("run", "--here", "--with", WRITES, "--no-precheck")
    assert ran.exit_code == 0 and "a is finished; it waits for a sign-off" in ran.stdout, ran.output
    assert state(repo) == P.REVIEW and (repo / "a.txt").exists()  # --here: its work is where it ran
    assert "+a" in person("node", "diff", "a").stdout.splitlines()
    assert person("node", "signoff", "a").exit_code == 0 and state(repo) == P.DONE


@pytest.mark.parametrize("here", [False, True])
def test_with_review_off_the_check_decides_and_it_lands(repo, monkeypatch, tmp_path, here):
    task(repo, False, monkeypatch, tmp_path)
    ran = person("run", *(["--here"] if here else []), "--with", WRITES, "--no-precheck")
    assert ran.exit_code == 0 and "a is done" in ran.stdout, ran.output
    assert "sign-off" not in ran.stdout and state(repo) == P.DONE and (repo / "a.txt").read_text() == "a\n"
