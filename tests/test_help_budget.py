"""What `--help` shows a new user. Nine commands at the top, at most eight under `plan` and nine under
`node`. The rest are hidden and still work; docs/HOW_IT_WORKS.md lists them under "The rest"."""

import re

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


def lines(command) -> list[str]:
    """A command's help as it is shown: one line per paragraph, a `[` as typed."""
    return (command.help or "").replace("\\[", "[").split("\n\n")


def test_every_commands_help_is_one_or_two_short_lines():
    for path, command in [((), CLI), *walk(CLI)]:
        said = lines(command)
        assert said[0] and len(said[0]) <= 72, (path, said[0])
        assert len(said) <= 2 and len("\n".join(said)) <= 200, (path, said)


def test_every_option_has_one_short_sentence_of_help():
    for path, command in [((), CLI), *walk(CLI)]:
        for param in command.params:
            said = getattr(param, "help", None)
            if not getattr(param, "hidden", False) and (param.param_type_name == "option" or said):
                assert said and len(said) <= 80, (path, param.name, said)
                assert not re.search(r"[.!?] +[A-Z]", said), (path, param.name, said)


def test_graphene_help_fits_24_rows_of_80_columns_with_one_row_per_command():
    shown = CliRunner().invoke(build(), ["--help"], env={"COLUMNS": "80"}).output.splitlines()
    assert len(shown) <= 24, len(shown)
    top = next(k for k, line in enumerate(shown) if "Commands" in line)
    rows = shown[top + 1 : top + 1 + len(VISIBLE[""])]
    assert [row.split()[1] for row in rows] == VISIBLE[""]  # a row that wrapped would start blank
    assert shown[top + 1 + len(VISIBLE[""])].lstrip().startswith("╰")
