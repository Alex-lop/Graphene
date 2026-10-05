"""What `--help` shows a new user. Nine commands at the top, at most eight under `plan` and nine under
`node`. The rest are hidden and still work; docs/HOW_IT_WORKS.md lists them under "The rest"."""

import typer.main
from typer.testing import CliRunner

from graphene_map.cli import build

CLI = typer.main.get_command(build())
VISIBLE = {
    "": ["init", "ask", "watch", "run", "plan", "node", "board", "demo", "config"],
    "plan": ["accept", "edit", "undo", "archive", "first", "pause", "resume", "log"],
    "node": ["add", "drop", "set", "edit", "show", "done", "release", "widen", "sibling"],
    "board": ["take", "drop", "answer", "pick", "note"],
    "config": ["edit"],
}
BUDGET = {"": 9, "plan": 8, "node": 9}


def walk(command, path=()):
    for name, sub in getattr(command, "commands", {}).items():
        yield (*path, name), sub
        yield from walk(sub, (*path, name))


def shown(group) -> list[str]:
    return [name for name, sub in group.commands.items() if not sub.hidden]


def test_each_level_shows_its_budget_and_exactly_the_chosen_commands():
    for level, names in VISIBLE.items():
        group = CLI.commands[level] if level else CLI
        assert sorted(shown(group)) == sorted(names), level
        assert len(shown(group)) <= BUDGET.get(level, len(names)), level
    listed = [n for n in CLI.list_commands(None) if not CLI.commands[n].hidden]
    assert listed == VISIBLE[""]  # the order a new user needs them


def test_every_hidden_command_still_answers():
    hidden = [path for path, sub in walk(CLI) if sub.hidden]
    assert len(hidden) >= 20  # talk, direction, key, ingest and the plan's, node's and board's rest
    for path in hidden:
        said = CliRunner().invoke(build(), [*path, "--help"])
        assert said.exit_code == 0, (path, said.output)
