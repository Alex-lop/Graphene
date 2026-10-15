# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""What the CLI says on its own, unasked: the first step first, one word for a unit of work, and what a
run may cost before it starts."""

import os

from test_plan_cli import person, repo  # noqa: F401  (fixtures)


def test_bare_graphene_in_a_new_repo_names_init_before_ask_and_is_no_error(repo):
    """A stranger's first ten minutes: bare `graphene` named `init` last, after the `ask` that refuses
    until it has run, and exited 1, as if an empty plan were a failure."""
    plain = person()
    said = " ".join(plain.output.split())
    assert plain.exit_code == 0, said
    assert said.startswith("nothing is planned here yet. Start with `graphene init`")
    assert said.index("graphene init") < said.index("graphene ask")


def test_a_finished_plan_says_every_leaf_is_done(repo):
    """The screen and the README say leaf; the next line said "every node is done"."""
    assert person("node", "add", "one", "--id", "l1", "--scope", "api.py", "--check", "true").exit_code == 0
    assert person("node", "start", "l1").exit_code == 0
    (repo / "api.py").write_text("def users():\n    return [1]\n")
    done = person("node", "done", "l1")
    assert "next: nothing; every leaf is done" in done.stdout, done.output


def test_a_run_says_its_worst_case_for_claude_code_and_no_cap_for_a_script(repo, tmp_path, monkeypatch):
    """The run's first lines named a cap only with --max-budget-usd in the command, an attempt's, and
    nothing for an executor with none: "what is the most this can cost?" had no answer. The worst case
    counts every leaf the run may reach, b too, which starts once a has landed."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "claude").write_text("#!/bin/sh\nexit 0\n")  # a Claude Code that does nothing, at $0
    (bin_ / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    person("node", "add", "a", "--id", "a", "--scope", "api.py", "--check", "false")
    person("node", "add", "b", "--id", "b", "--scope", "b.py", "--check", "false", "--needs", "a")
    said = person("run", "--with", "claude", "--no-precheck").stdout
    assert "worst case: 2 leaves x 3 attempts x $2 = $12" in said, said
    assert "no spend cap" not in said
    said = person("run", "--with", "true", "--attempts", "1", "--no-precheck").stdout
    assert "worst case: no spend cap on this executor" in said, said
