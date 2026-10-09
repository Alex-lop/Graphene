"""The commands: `run` runs the checks at the base commit first, `node reopen` takes --for."""

from __future__ import annotations

import test_plan_cli
from test_plan_cli import agent, person

repo = test_plan_cli.repo  # the fixture


def test_a_check_that_passes_at_base_is_said_and_the_leaf_still_runs(repo):
    person("node", "add", "leaf", "--id", "l1", "--scope", "api.py", "--check", "true")
    ran = person("run", "--here", "--with", "true")
    assert ran.exit_code == 0, ran.output
    assert "l1: its check passes at the base commit" in ran.stdout
    assert "red first: 1 checks at" in ran.stdout
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
