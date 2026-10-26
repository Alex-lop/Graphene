# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene auto` with an executor whose stream says what it spent, as Claude Code's does: the budget holds
each attempt's worst case through the run's cap and settles at the stream's dollars, which the auto rows
carry; and a budget smaller than one attempt's worst case says so at once, where it used to start nothing
and then blame the plan ("did not start: `graphene plan` says what each waits on")."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map.store import Store

STREAM = Path(__file__).parent / "fixtures" / "meter" / "claude.jsonl"  # total_cost_usd 0.0622574
CLAUDE = """#!{python}
import os, pathlib
print(pathlib.Path({stream!r}).read_text(), flush=True)
pathlib.Path(os.environ["GRAPHENE_NODE"] + ".txt").write_text("done\\n")
"""
PLANNER = r'''
print("```plan")
for i in ("a", "b"):
    print(f"? leaf {i}  [{i}]")
    print(f"    scope: {i}.txt")
    print(f"    check: grep -q done {i}.txt")
print("```")
'''


@pytest.fixture
def tools(repo, tmp_path):
    (repo / ".gitignore").write_text(".graphene/\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "ignore"], cwd=repo,
                   check=True)  # fmt: skip
    (tmp_path / "bin").mkdir()
    claude = tmp_path / "bin" / "claude"  # the meter knows an executor by its command's name
    claude.write_text(CLAUDE.format(python=sys.executable, stream=str(STREAM)))
    claude.chmod(0o755)
    (tmp_path / "planner.py").write_text(PLANNER)
    executor = f"{claude} --output-format stream-json --verbose --max-budget-usd 1"
    return f"{sys.executable} {tmp_path / 'planner.py'}", executor


def test_a_stream_executor_is_held_to_the_budget_and_its_dollars_are_the_rows(repo, tools):
    planner, executor = tools
    said = person("auto", "two files say done", "--planner", planner, "--with", executor, "--budget", "3",
                  "--parallel", "2")  # fmt: skip
    assert said.exit_code == 0, said.output
    with Store.open(repo) as store:
        last = AUTO.state(store)
    assert last["stage"] == "done" and last["budget"] == 3.0
    assert last["spent"] == pytest.approx(2 * 0.0622574, abs=1e-3)  # each settled at its stream's cost


def test_a_budget_under_one_attempts_worst_case_says_so_at_once(repo, tools):
    planner, executor = tools
    said = person("auto", "two files say done", "--planner", planner, "--with", executor, "--budget", "0.5")
    assert said.exit_code == 1, said.output
    line = [x for x in said.output.splitlines() if x.startswith("waits for you: ")][-1]
    assert line.startswith("waits for you: the budget left ($0.50) is less than one attempt's worst"), line
    assert "case ($1)" in line
    assert "did not start" not in said.output
