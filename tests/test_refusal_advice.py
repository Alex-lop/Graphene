# ruff: noqa: F811  (fixtures imported from test_plan_cli and test_auto_run are named again as arguments)
"""A refusal's advice, followed as printed, gets past the refusal. Found on 28 October 2026 on Alex's
checkout: `graphene auto` refused a new goal and said `graphene plan archive` ends the old one, which archive
cannot do while a node of it is open, so the refusal came back for ever; and a budget under one attempt's $2
pointed at "the executor's `--max-budget-usd`", which no `--with` could set. Each test runs what the message
says and asserts that the retry passes."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from test_auto_run import GOAL, GOAL_CHECK, scripts, tiny  # noqa: F401  (fixtures)
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import run as R
from graphene_map.store import Store

STREAM = Path(__file__).parent / "fixtures" / "meter" / "claude.jsonl"  # total_cost_usd 0.0622574


def advice(said: str) -> list[str]:
    """The graphene commands a message gives, in its order, each as it is backticked there."""
    return re.findall(r"`(graphene [^`]+)`", said)


def follow(command: str):
    return person(*shlex.split(command)[1:])


def test_a_new_goal_refused_while_the_old_one_is_open_gets_in_once_its_advice_is_followed(tiny, tmp_path):
    planner, executor = scripts(tmp_path)
    first = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK, "--plan")
    assert first.exit_code == 0, first.output  # planned and accepted, nothing run: its tasks are open
    other = ("auto", "another goal", "--planner", planner, "--with", executor, "--check", "true")
    refused = person(*other)
    assert refused.exit_code == 1 and "still open" in refused.output, refused.output
    ends = [c for c in advice(refused.output) if not c.startswith("graphene auto")]  # what ends the old goal
    assert ends, refused.output
    for command in ends:
        done = follow(command)
        assert done.exit_code == 0, (command, done.output)
    again = person(*other)
    assert again.exit_code == 0, again.output


CLAUDE = """#!{python}
import os, pathlib
print(pathlib.Path({stream!r}).read_text(), flush=True)
pathlib.Path(os.environ["GRAPHENE_NODE"] + ".txt").write_text("done\\n")
"""
PLANNER = r'''
print("```plan")
print("? leaf a  [a]")
print("    scope: a.txt")
print("    check: grep -q done a.txt")
print("```")
'''


@pytest.fixture
def planner(repo, tmp_path, monkeypatch):
    """`claude` on PATH, as Claude Code would stream an attempt that writes its leaf's file: `--with claude`
    runs Graphene's default command, $2 an attempt, through it. Returns the planner, a script."""
    (repo / ".gitignore").write_text(".graphene/\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "ignore"], cwd=repo,
                   check=True)  # fmt: skip
    (tmp_path / "bin").mkdir()
    script = tmp_path / "bin" / "claude"
    script.write_text(CLAUDE.format(python=sys.executable, stream=str(STREAM)))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    (tmp_path / "planner.py").write_text(PLANNER)
    return f"{sys.executable} {tmp_path / 'planner.py'}"


def test_claude_with_a_cap_is_the_default_command_with_that_cap():
    two, half = "--max-budget-usd 2", "--max-budget-usd 0.5"
    assert R.named("claude --max-budget-usd 0.5") == R.DEFAULT_WITH.replace(two, half)
    assert R.named("claude:opus --max-budget-usd=1.25") == R.named("claude:opus").replace(
        "--max-budget-usd 2", "--max-budget-usd 1.25")  # fmt: skip
    assert R._worst(shlex.split(R.named("claude --max-budget-usd 0.5"))) == 0.5
    assert R.named("claude --max-budget-usd lots") == "claude --max-budget-usd lots"  # no number: a command
    assert R.named("claude -p --max-budget-usd 1") == "claude -p --max-budget-usd 1"  # a command of its own


def test_a_budget_under_one_claude_attempt_gets_in_once_its_advice_is_followed(repo, planner):
    with Store.open(repo) as store:  # as `graphene init --planner … --executor claude` chooses, or Set Up
        store.set_meta("planner", planner)
        store.set_meta("executor", "claude")
    refused = person("auto", "a file says done", "--budget", "1.5")
    assert refused.exit_code == 1, refused.output
    line = [x for x in refused.output.splitlines() if x.startswith("waits for you: ")][-1]
    assert "less than one attempt's worst case ($2)" in line, line
    ways = [c for c in advice(line) if not c.startswith("graphene config set budget")]
    assert ways, line  # a way other than a wider budget, as a command
    for command in ways:
        done = follow(command)
        assert done.exit_code == 0, (command, done.output)
    assert (repo / "a.txt").read_text() == "done\n"


def test_codex_has_no_cap_to_lower_so_the_budget_alone_is_advised(repo, planner):
    """Codex has no --max-budget-usd: an attempt's worst case is WORST, and the only way is a wider budget."""
    said = person("auto", "a file says done", "--planner", planner, "--with", "codex", "--budget", "1.5")
    line = [x for x in said.output.splitlines() if x.startswith("waits for you: ")][-1]
    assert advice(line) == ["graphene config set budget N"], line
    assert "--max-budget-usd" not in line, line


def test_an_attempt_stopped_at_claudes_default_cap_is_told_a_with_that_gives_it_more():
    """`a larger cap in --with` named no way to get one for `--with claude`: the hint is now the shorthand,
    and the shorthand is the default command with that cap."""
    said = R.more(R.named("claude:opus"), 2.0)
    [given] = re.findall(r"`--with '([^']+)'`", said)
    assert given == "claude:opus --max-budget-usd 4"
    assert R._worst(shlex.split(R.named(given))) == 4.0 and "--model opus" in R.named(given)
