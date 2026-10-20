# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene run --forks N`, `--first` and `--with` more than once: what the run is told about forks, how
many a leaf runs as (its line, else the run's, else the setting), the model shorthand `claude:MODEL`, what
is refused with `--here`, and the worst case multiplied by the forks."""

import os
import shlex

from test_run_live import ALEX, SLOW, executor, graphene_run, leaf, repo, states, wait_for  # noqa: F401
from typer.testing import CliRunner

from graphene_map import meter as M
from graphene_map import plan
from graphene_map import run as R
from graphene_map import settings as S
from graphene_map.cli import build
from graphene_map.plan import RUNNING
from graphene_map.store import Store


def person(*args):
    return CliRunner().invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"})


def test_with_names_a_model_in_the_clis_own_flag():
    assert R.named("claude:opus") == R.DEFAULT_WITH + " --model opus"
    assert R.named("codex:o3") == R.CODEX + " -m o3"
    assert M.model_in(shlex.split(R.named("claude:opus"))) == "opus"
    assert R.label(R.named("claude:opus")) == "claude"
    assert R.named("claude") == R.DEFAULT_WITH and R.named("codex") == R.CODEX
    assert R.named("python3 bin/run.py --model x") == "python3 bin/run.py --model x"  # a command, as it is
    assert R.named("claude:a model") == "claude:a model"  # a space: a command, not the shorthand


def test_a_leaf_runs_as_its_own_line_else_the_runs_forks_else_the_setting_else_one(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt", forks=2), leaf("c", "c.txt", check=None,
                                                                                  signoff=True)], ALEX)
        a, b, c = (plan.get(store, i) for i in "abc")
        assert R.forks_of(store, a, None) == 1 and R.forks_of(store, b, None) == 1  # --here never forks
        assert R.forks_of(store, a, R.Forks()) == 1
        assert R.forks_of(store, a, R.Forks(3)) == 3 and R.forks_of(store, b, R.Forks(3)) == 2
        three = R.Forks(0, False, ["claude", "codex", "claude:opus"])  # a fork each --with
        assert R.forks_of(store, a, three) == 3 and R.forks_of(store, b, three) == 3
        S.apply(store, "forks: 4\n", ALEX)
        assert R.forks_of(store, a, R.Forks()) == 4 and R.forks_of(store, b, R.Forks(3)) == 2
        assert R.forks_of(store, c, R.Forks(3)) == 1  # no check to keep one: one agent, whatever the run says


def test_forks_need_worktrees_so_here_is_refused_and_so_are_too_many(repo):
    twice = ("--with", "true", "--with", "true", "--here")
    for args in (("--forks", "2", "--here"), ("--first", "--here"), twice):
        said = person("run", *args)
        assert said.exit_code == 2 and "forks need worktrees: drop --here" in said.output, said.output
    assert person("run", "--forks", "9").exit_code == 2 and person("run", "--forks", "0").exit_code == 2
    nine = [x for _ in range(9) for x in ("--with", "true")]
    said = person("run", *nine)
    assert said.exit_code == 2 and "--with at most 8 times" in said.output, said.output
    assert person("run", "--forks", "2", "--here", "--first").exit_code == 2


def test_the_worst_case_counts_the_forks_and_is_as_it_was_with_one(repo, tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "claude").write_text("#!/bin/sh\nexit 0\n")  # a Claude Code that does nothing, at $0
    (bin_ / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    with Store.open(repo) as store:
        red = [leaf("a", "a.txt", check="false"), leaf("b", "b.txt", check="false", needs=["a"])]
        plan.propose(store, red, ALEX)
    said = person("run", "--with", "claude", "--no-precheck", "--attempts", "1").stdout
    assert "worst case: 2 leaves x 1 attempt x $2 = $4" in said, said  # as it was, with one agent a leaf
    # a came back, so each run after reaches b alone, which waits on a: the line is said and nothing starts
    said = person("run", "--with", "claude", "--no-precheck", "--attempts", "1", "--forks", "3").stdout
    assert "worst case: 1 leaf x 3 forks x 1 attempt x $2 = $6" in said, said
    with Store.open(repo) as store:  # a leaf's own line counts, with no --forks; so does the setting
        plan.edit(store, "b", {"forks": 2}, ALEX)
    said = person("run", "--with", "claude", "--no-precheck", "--attempts", "1").stdout
    assert "worst case: 1 leaf x 2 forks x 1 attempt x $2 = $4" in said, said
    with Store.open(repo) as store:
        S.apply(store, "forks: 4\n", ALEX)
    said = person("run", "--with", "claude", "--no-precheck", "--attempts", "1").stdout
    assert "worst case: 1 leaf x 4 forks x 1 attempt x $2 = $8" in said, said


def test_a_run_with_forks_of_its_own_is_refused_while_another_run_goes(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("b", "b.txt")], ALEX)
        store.set_meta("executor", executor(repo, SLOW))  # as `graphene init` chooses one
    run = graphene_run(repo, "--node", "a")
    try:
        assert wait_for(lambda: states(repo)["a"] == RUNNING), run.stdout
        for args in (("--forks", "2"), ("--first",), ("--with", "true", "--with", "true")):
            own = graphene_run(repo, *args, "--node", "b")
            said, _ = own.communicate(timeout=60)
            assert own.returncode == 1 and "another `graphene run` is going here" in said, said
        asked, _ = graphene_run(repo, "--node", "b").communicate(timeout=60)  # none of its own: handed on
        assert f"run: the run going here (pid {run.pid}) takes b as soon as it can" in asked, asked
    finally:
        run.kill()
