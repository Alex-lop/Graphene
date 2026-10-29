# ruff: noqa: F811  (fixtures imported from test_plan_cli and test_auto_run are named again as arguments)
"""A refusal's advice, followed as printed, gets past the refusal. Found on 28 October 2026 on Alex's
checkout: `graphene auto` refused a new goal and said `graphene plan archive` ends the old one, which archive
cannot do while a node of it is open, so the refusal came back for ever. Each test runs what the message says
and asserts that the retry passes."""

import re
import shlex

from test_auto_run import GOAL, GOAL_CHECK, scripts, tiny  # noqa: F401  (fixtures)
from test_plan_cli import person, repo  # noqa: F401  (fixtures)


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
