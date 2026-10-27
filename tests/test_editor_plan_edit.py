# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene plan edit --from - --json [--since CURSOR]`: the plan's text read from a pipe and applied as one
save in the terminal's editor is, all or none; what came of it as one JSON line, each refusal on the text's
own line; a node someone else changed after the snapshot's cursor is refused, never written over. The
contract's section "The CLI", shape 4."""

import json

from test_plan_cli import agent, repo, runner  # noqa: F401
from test_plan_text_cli import TEXT
from test_plan_text_cli import person_with as person

from graphene_map import plan
from graphene_map import plan_text as T
from graphene_map.cli import build
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)


def save(text: str, *args, env=None):
    said = runner.invoke(build(), ["plan", "edit", "--from", "-", "--json", *args],
                         env=env or {"GRAPHENE_AS": "person:alex"}, input=text)  # fmt: skip
    got = json.loads(said.stdout.splitlines()[-1]) if said.stdout.strip() else None
    return said.exit_code, got, said


def rendered() -> str:
    return person("plan", "--text").stdout


def cursor() -> int:
    return json.loads(person("state", "--json").stdout)["cursor"]


def test_a_save_from_a_pipe_is_applied_all_at_once_and_said_as_json(repo):
    agent("plan", "propose", "-", input=TEXT)
    text = rendered().replace("? ", "- ").replace("check: test -f README.md", "check: true")
    code, got, _ = save(text)
    assert code == 0 and got["applied"] is True and got["faults"] == []
    assert "accepted api" in got["said"] and "docs: check changed" in got["said"]
    assert "- document it  [docs]" in rendered() and "check: true" in rendered()
    code, got, _ = save(rendered())  # the same text again: nothing changed, and that is not a refusal
    assert code == 0 and got == {"applied": False, "said": [], "faults": []}
    undone = person("plan", "undo")
    assert undone.exit_code == 0 and "undid: plan edit" in undone.stdout


def test_a_refusal_is_one_fault_on_the_texts_own_line_and_nothing_is_applied(repo):
    person("plan", "propose", "-", input=TEXT)
    text = rendered()
    bad = text.replace("scope: README.md", "scope: README.md\n      signoff: maybe")
    at = next(no for no, line in enumerate(bad.splitlines(), 1) if "signoff: maybe" in line)
    code, got, said = save(bad)
    assert code == 1 and got["applied"] is False and got["said"] == []
    [fault] = got["faults"]
    assert fault["line"] == at and fault["text"].startswith("signoff is yes or no, not 'maybe'")
    assert "signoff: yes" not in rendered() and said.stdout.count("\n") == 1
    unreadable = text.replace("- the API  [api]", "## the API")  # a parse fault: its own line number
    code, got, _ = save(unreadable)
    at = next(no for no, line in enumerate(unreadable.splitlines(), 1) if line.startswith("## "))
    [fault] = got["faults"]
    assert code == 1 and fault["line"] == at and "a heading is not read" in fault["text"]


def test_a_node_someone_else_changed_after_the_cursor_is_refused_not_written_over(repo):
    person("plan", "propose", "-", input=TEXT)
    text, read_at = rendered(), cursor()
    with Store.open(repo) as store:  # someone else, after the editor read its text
        plan.edit(store, "ids", {"check": "grep -q ids api.py && true"}, ALEX)
    mine = text.replace("check: grep -q ids api.py", "check: false")
    code, got, _ = save(mine, "--since", str(read_at))
    [fault] = got["faults"]
    assert code == 1 and "changed by someone else" in fault["text"]
    assert fault["line"] == next(no for no, line in enumerate(text.splitlines(), 1) if "[ids]" in line)
    assert "check: false" not in rendered() and "check: grep -q ids api.py && true" in rendered()
    # the same save with the text read now: applied, as it is made on what the node says now
    code, got, _ = save(rendered().replace("check: grep -q ids api.py && true", "check: false"),
                        "--since", str(cursor()))  # fmt: skip
    assert code == 0 and got["applied"] and "check: false" in rendered()
    # a text that still says the old line of a node changed meanwhile would write theirs over: refused,
    # whatever else it changes; a text that says what the node says now is applied
    read_at, text = cursor(), rendered()
    with Store.open(repo) as store:
        plan.edit(store, "ids", {"check": "true"}, ALEX)
    code, got, _ = save(text.replace("check: test -f README.md", "check: ls"), "--since", str(read_at))
    assert code == 1 and "[ids] was changed by someone else" in got["faults"][0]["text"]
    assert "check: ls" not in rendered() and "check: true" in rendered()  # theirs stands, mine waits
    fresh = text.replace("check: false", "check: true").replace("check: test -f README.md", "check: ls")
    code, got, _ = save(fresh, "--since", str(read_at))
    assert code == 0 and got["said"] == ["docs: check changed"], got


def test_a_deleted_line_and_a_goal_changed_after_the_cursor_are_refused_too(repo):
    person("plan", "propose", "-", input=TEXT)
    read_at, text = cursor(), rendered()
    with Store.open(repo) as store:
        plan.edit(store, "docs", {"check": "true"}, ALEX)
    without = "\n".join(line for line in text.splitlines() if "docs" not in line and "README" not in line
                        and "needs: ids" not in line and "check: test" not in line) + "\n"  # fmt: skip
    code, got, _ = save(without, "--since", str(read_at))
    assert code == 1 and "whose lines were deleted, was changed by someone else" in got["faults"][0]["text"]
    assert got["faults"][0]["line"] == 1 and "[docs]" in rendered()  # the deleted line is nowhere: line 1
    read_at, text = cursor(), rendered()
    with Store.open(repo) as store:
        plan.set_goal(store, "users come back, with ids", ALEX)
    code, got, _ = save(text.replace("goal: users come back with their ids", "goal: ids, kept"),
                        "--since", str(read_at))  # fmt: skip
    assert code == 1 and "goal was changed by someone else" in got["faults"][0]["text"]
    assert got["faults"][0]["line"] == 1
    code, got, _ = save(text, "--since", str(read_at))  # the old goal line: it would write theirs over
    assert code == 1 and "goal was changed by someone else" in got["faults"][0]["text"]
    code, got, _ = save(rendered(), "--since", str(read_at))  # the goal as they set it: nothing to write
    assert code == 0 and got == {"applied": False, "said": [], "faults": []}


def test_the_text_of_an_empty_plan_is_the_editors_hint_not_a_blank_line(repo):
    """Edit Plan as Text on a fresh repo opened an empty tab: `plan --text` printed one newline, and a save
    of nothing is refused with no hint of what to type. The terminal's `plan edit` shows its `# ` help under
    the text; an empty plan's text is that help, which a save passes back unread."""
    text = rendered()
    assert text.strip(), repr(text)
    assert all(line.startswith("# ") for line in text.splitlines()), text
    assert "is a node in the plan" in text and "scope:" in text
    nothing = "the text has no node in it, so nothing was applied"
    assert save(text)[1] == {"applied": False, "said": [], "faults": [{"line": 1, "text": nothing}]}


def test_the_terminal_form_says_the_lines_and_an_agent_is_refused(repo):
    agent("plan", "propose", "-", input=TEXT)
    said = runner.invoke(build(), ["plan", "edit", "--from", "-"], env={"GRAPHENE_AS": "person:alex"},
                         input=rendered().replace("? ", "- "))  # fmt: skip
    assert said.exit_code == 0 and "accepted api" in said.stdout
    said = runner.invoke(build(), ["plan", "edit", "--from", "-"], env={"CLAUDECODE": "1"}, input=rendered())
    assert said.exit_code == 1 and "an agent proposes" in said.stderr
    said = runner.invoke(build(), ["plan", "edit", "--json"], env={"GRAPHENE_AS": "person:alex"})
    assert said.exit_code == 2 and "--json and --since go with --from" in said.stderr


def test_fault_finds_the_line_of_the_id_a_refusal_names_else_the_first():
    text = "goal: x\n- a  [a]\n  - b  [b]\n"
    assert T.fault("line 3 [b]: scope is empty", text) == {"line": 3, "text": "scope is empty"}
    assert T.fault("line 2: a node needs a title", text) == {"line": 2, "text": "a node needs a title"}
    assert T.fault("[b], whose lines were deleted, was changed", text)["line"] == 3
    assert T.fault("the plan's goal was changed by someone else", text) == {
        "line": 1, "text": "the plan's goal was changed by someone else"}  # fmt: skip
    assert T.fault("two lines\n  of it", text)["text"] == "two lines of it"


def test_the_flags_have_help_in_the_budget_and_the_reference_names_the_pipe():
    import typer.main

    edit = typer.main.get_command(build()).commands["plan"].commands["edit"]
    helps = {p.name: p.help for p in edit.params}
    assert all(len(helps[k]) <= 80 for k in ("source", "as_json", "since")), helps
    how = (__import__("pathlib").Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text()
    assert "`graphene plan edit --from - --json`" in how
