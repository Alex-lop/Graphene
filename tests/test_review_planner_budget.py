# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The planner is inside the envelope's budget. The budget was read before the run and after the planner: a
planner was asked, and its proposal accepted, with the budget already spent, and a Claude Code planner (the
default names no --max-budget-usd) was started with no cap, so one call could spend past the envelope.
Now a spent budget stops the round before the planner starts, and a Claude Code planner is given the budget
left as its cap, or refused when its own cap is more than is left."""

import json
import sys

from test_auto_run import GOAL, GOAL_CHECK, rows, scripts, tiny  # noqa: F401  (fixtures)
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map.ask import DEFAULT_PLANNER
from graphene_map.store import Store


def test_a_spent_budget_stops_the_round_before_the_planner_is_asked(tiny, tmp_path, monkeypatch):
    planner, executor = scripts(tmp_path)
    monkeypatch.setattr(AUTO, "spent", lambda store, since: 0.75)  # what a metered executor would have cost
    said = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK,
                  "--budget", "0.5")  # fmt: skip
    assert said.exit_code == 1, said.output
    spent = "waits for you: the budget is spent: $0.7500 of $0.50; `graphene config set budget N` widens it"
    assert spent in said.stdout
    assert "asking the planner" not in said.stdout
    assert not (tmp_path / "planner_seen.txt").exists()  # the planner never ran
    [waits] = rows(tiny)
    assert (waits["stage"], waits["spent"], waits["budget"]) == ("waits", 0.75, 0.5)
    with Store.open(tiny) as store:
        assert not store.node_log(None, ("accepted",)) and not store.node_log(None, ("attempt",))


def test_a_claude_code_planner_is_given_the_budget_left_as_its_cap():
    assert AUTO.planner_cap(DEFAULT_PLANNER, None) == (DEFAULT_PLANNER, None)
    capped, why = AUTO.planner_cap(DEFAULT_PLANNER, 0.4)
    assert capped == f"{DEFAULT_PLANNER} --max-budget-usd 0.40" and why is None
    own = f"{DEFAULT_PLANNER} --max-budget-usd 2"
    assert AUTO.planner_cap(own, 2.5) == (own, None)
    capped, why = AUTO.planner_cap(own, 0.4)
    assert capped == own
    assert why == ("the budget left ($0.40) is less than the planner's worst case ($2): `graphene config set "
                   "budget N` widens it, or the planner's `--max-budget-usd`")
    script = f"{sys.executable} planner.py"  # a script reports no cost: as it is
    assert AUTO.planner_cap(script, 0.4) == (script, None)


def test_the_planner_graphene_starts_carries_the_cap(tiny, tmp_path):
    """A planner named `claude` whose stream reports what it cost (a script here): `graphene auto` passes it
    the budget left as --max-budget-usd, and the row it logs says what it reported."""
    plan = "```plan\n? greet says hi  [greet]\n    scope: greet.py\n    check: grep -q hi greet.py\n```"
    result = {"type": "result", "subtype": "success", "result": plan, "total_cost_usd": 0.02}
    claude = tmp_path / "claude"
    claude.write_text(f"#!{sys.executable}\nimport json, sys\n"
                      f"open({str(tmp_path / 'argv.json')!r}, 'w').write(json.dumps(sys.argv))\n"
                      f"print(json.dumps({result!r}))\n")  # fmt: skip
    claude.chmod(0o755)
    _, executor = scripts(tmp_path)
    said = person("auto", GOAL, "--planner", f"{claude} -p --output-format stream-json --verbose",
                  "--with", executor, "--check", GOAL_CHECK, "--budget", "0.30", "--rounds", "0")  # fmt: skip
    argv = json.loads((tmp_path / "argv.json").read_text())
    assert argv[argv.index("--max-budget-usd") + 1] == "0.30", said.output
    with Store.open(tiny) as store:
        [usage] = store.node_log(None, ("usage",))
        assert usage["detail"]["dollars"] == 0.02
