# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene auto`, end to end, with a planner and executors that are scripts printing what a model would:
round 1 lands, the goal's check is red, round 2's fix lands, the goal's check passes, exit 0, and the auto
rows read as the contract says. A proposal outside the envelope makes it wait (exit 3); a spent budget stops
it."""

import json
import subprocess
import sys

import pytest
from test_plan_cli import AGENT_ENV, person, repo, runner  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map import plan as P
from graphene_map.cli import build
from graphene_map.store import Store

GOAL = "the app says hi and bye"
GOAL_CHECK = """python3 -c 'import greet, bye; assert greet.hi() + " " + bye.bye() == "hi bye"'"""

# What the planner prints: the whole tree the first time; the fix when the prompt carries the red goal check
PLANNER = r'''
import sys
prompt = sys.argv[-1]
open("PLANNER_SEEN", "a").write(prompt + "\n=====\n")
two = "-2" if "another goal" in prompt else ""  # a second goal's tree: ids of its own
print("```plan")
if "has landed, and its own check still fails" in prompt:
    print("? bye says bye, not bye!  [bye-fix]")
    print("    scope: bye.py")
    print("    check: python3 -c 'import bye; assert bye.bye() == \"bye\"'")
else:
    print(f"? greet says hi  [greet{two}]")
    print("    scope: greet.py")
    print("    check: grep -q again greet.py" if two else  # red before its work, as every check here
          "    check: python3 -c 'import greet; assert greet.hi() == \"hi\"'")
    print(f"? bye says bye  [bye{two}]")
    print("    scope: bye.py")
    print("    check: grep -q again bye.py" if two else
          "    check: python3 -c 'import bye; assert bye.bye()'")
print("```")
'''
# A fix whose check is too weak to catch the wrong word (red before the work, passed by any other word): the
# goal's check stays red after the fix round
WEAK_FIX = PLANNER.replace("""assert bye.bye() == \\"bye\\"'""", """assert bye.bye() != \\"bye!\\"'""")
# A fix whose check passes before any work: it would land with nothing done
HOLLOW_FIX = PLANNER.replace("""assert bye.bye() == \\"bye\\"'""", "assert bye.bye()'")
# What each executor writes, by the leaf it holds (cwd is its worktree): bye passes its own check and breaks
# the goal's; bye-fix mends it
EXECUTOR = r'''
import os, pathlib
node = os.environ["GRAPHENE_NODE"]
files = {"greet": ("greet.py", 'def hi():\n    return "hi"\n'),
         "bye": ("bye.py", 'def bye():\n    return "bye!"\n'),
         "bye-fix": ("bye.py", 'def bye():\n    return "bye"\n')}
path, text = files[node.removesuffix("-2")]
pathlib.Path(path).write_text(text + ("# again\n" if node.endswith("-2") else ""))  # a second goal changes it
'''
NO_CHECK = r'''
print("```plan")
print("? greet says hi  [greet]")
print("    scope: greet.py")
print("    signoff: yes")
print("```")
'''


def scripts(tmp_path, planner=PLANNER, executor=EXECUTOR) -> tuple[str, str]:
    (tmp_path / "planner.py").write_text(planner.replace("PLANNER_SEEN", str(tmp_path / "planner_seen.txt")))
    (tmp_path / "executor.py").write_text(executor)
    return f"{sys.executable} {tmp_path / 'planner.py'}", f"{sys.executable} {tmp_path / 'executor.py'}"


@pytest.fixture
def tiny(repo):
    """The repo fixture, with what a run needs: .graphene ignored, so a worktree's checks see a clean tree."""
    (repo / ".gitignore").write_text(".graphene/\n__pycache__/\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "ignore"],
                   cwd=repo, check=True)  # fmt: skip
    return repo


def rows(repo) -> list[dict]:
    with Store.open(repo) as store:
        return [r["detail"] for r in store.node_log("*", (AUTO.KIND,))]


def test_a_goal_is_planned_run_checked_and_fixed_inside_the_envelope(tiny, tmp_path):
    planner, executor = scripts(tmp_path)
    said = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK,
                  "--budget", "2", "--tasks", "12", "--parallel", "2")  # fmt: skip
    out = said.stdout
    assert said.exit_code == 0, said.output
    assert out.startswith("envelope: auto on since ")
    assert " · $2.00 · 12 tasks · 2 fix rounds · 1 fork a task · 2 at once" in out.splitlines()[0]
    assert "this executor reports no cost, so the budget cannot hold it: attempts are counted" in out
    assert "round 1: planning" in out and "round 2: planning the fix" in out
    assert "accepted inside your envelope (auto on since " in out
    assert "): greet, bye. `graphene run` runs them; 2 tasks can run at once" in out
    assert "the goal's check failed: " in out
    assert "): bye-fix. `graphene run` runs them; 1 task can run at once" in out
    last = out.strip().splitlines()[-1]
    assert last == ("auto: 2 rounds, 3 tasks landed, 0 came back, 0 forks raced, 3 attempts, no meter; the "
                    "goal's check passed. `graphene plan log` has the whole history"), last  # fmt: skip
    # the contract's rows, in order, every one with its keys
    got = rows(tiny)
    assert [(r["round"], r["stage"]) for r in got] == [
        (1, "planning"), (1, "running"), (1, "checking"), (2, "fixing"), (2, "running"), (2, "checking"),
        (2, "done")]  # fmt: skip
    for r in got:
        assert {"round", "rounds", "stage", "spent", "budget", "check", "why"} <= set(r), r
        said = "AssertionError" if r["stage"] == "fixing" else ""  # a fix round: what the goal failed on
        assert (r["rounds"], r["budget"], r["why"]) == (2, 2.0, said), r
    assert [r["check"] for r in got] == [None, None, None, "fail", "fail", "fail", "pass"]
    with Store.open(tiny) as store:
        root = AUTO.state(store)["root"]
        assert P.get(store, root).check == GOAL_CHECK and P.get(store, root).state == P.DONE
        assert {n.id: n.state for n in P.nodes(store)} == {
            root: "done", "greet": "done", "bye": "done", "bye-fix": "done"}  # fmt: skip
        assert P.get(store, "bye-fix").parent == root  # the fix hangs under the goal
        accepted = {r["node_id"]: r["detail"] for r in store.node_log(None, ("accepted",))}
        assert accepted["greet"] == {"by": "auto", "round": 1}
        assert accepted["bye-fix"] == {"by": "auto", "round": 2}
        assert all(r["actor"] == "alex (no terminal)" for r in store.node_log(None, ("accepted",)))
        assert P.goal(store) == GOAL
    assert (tiny / "greet.py").exists() and (tiny / "bye.py").read_text().endswith('return "bye"\n')
    log = person("plan", "log").stdout
    assert "accepted by your envelope, round 1" in log and "accepted by your envelope, round 2" in log
    assert "by their prompt" not in log
    seen = (tmp_path / "planner_seen.txt").read_text()
    assert "Leaves that can run at the same time share no file" in seen  # the width rule, in the prompt
    assert f"`{GOAL_CHECK}` said:" in seen and "AssertionError" in seen  # the fix round's planner sees red


def test_a_proposal_outside_the_envelope_waits_for_the_person_and_exits_3(tiny, tmp_path):
    planner, executor = scripts(tmp_path, planner=NO_CHECK)
    said = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK)
    assert said.exit_code == 3, said.output
    assert "waits for you: greet has no check. `graphene watch` shows it" in said.stdout
    [planning, waits] = rows(tiny)
    assert (planning["stage"], waits["stage"], waits["round"]) == ("planning", "waits", 1)
    assert waits["why"] == "greet has no check" and waits["check"] is None
    with Store.open(tiny) as store:
        assert P.get(store, "greet").state == P.PROPOSED  # nothing ran
        assert not store.node_log(None, ("attempt",))
    again = person("auto", "--planner", planner, "--with", executor)  # the next round, nothing accepted yet
    assert again.exit_code == 3 and "waits for you: greet still wait for your accept" in again.stdout
    assert (rows(tiny)[-1]["stage"], rows(tiny)[-1]["round"]) == ("waits", 2)


def test_a_spent_budget_stops_it_before_a_run_and_says_so(tiny, tmp_path, monkeypatch):
    planner, executor = scripts(tmp_path)
    monkeypatch.setattr(AUTO, "spent", lambda store, since: 0.75)  # what a metered executor would have cost
    said = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK,
                  "--budget", "0.5")  # fmt: skip
    assert said.exit_code == 1, said.output
    spent = "waits for you: the budget is spent: $0.7500 of $0.50; `graphene config set budget N` widens it"
    assert spent in said.stdout
    [planning, waits] = rows(tiny)
    assert waits["stage"] == "waits" and waits["spent"] == 0.75 and waits["budget"] == 0.5
    with Store.open(tiny) as store:
        assert not store.node_log(None, ("attempt",))  # nothing started


def test_the_check_still_red_after_the_rounds_waits_with_the_first_failing_line(tiny, tmp_path):
    """The planner's fix does not fix it (its executor writes another wrong word, and the fix's own check is
    too weak to see it): after the rounds the auto row says the check is still red, exit 1, and `graphene
    auto` with no goal would try another round."""
    executor = EXECUTOR.replace('"bye-fix": ("bye.py", \'def bye():\\n    return "bye"\\n\')',
                                '"bye-fix": ("bye.py", \'def bye():\\n    return "bye?"\\n\')')  # fmt: skip
    planner, executor = scripts(tmp_path, planner=WEAK_FIX, executor=executor)
    said = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK,
                  "--rounds", "1")  # fmt: skip
    assert said.exit_code == 1, said.output
    assert "waits for you: the goal's check is still red: " in said.stdout
    assert "after 1 fix round; `graphene config set rounds N` allows more" in said.stdout
    got = rows(tiny)
    assert [(r["round"], r["stage"]) for r in got][-2:] == [(2, "checking"), (2, "waits")]
    assert got[-1]["check"] == "fail" and got[-1]["rounds"] == 1


def test_a_task_whose_check_passes_before_any_work_waits_for_the_person(tiny, tmp_path):
    """Red first is a gate in auto mode: nobody reads what lands, so a task whose check passes before any
    work (here the fix's, `assert bye.bye()`, which "bye!" passes already) would land with nothing done. It
    waits for the person with why, and nothing runs on it."""
    planner, executor = scripts(tmp_path, planner=HOLLOW_FIX)
    said = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK)
    assert said.exit_code == 3, said.output
    said_it = "waits for you: bye-fix: its check passes before any work, so it would land with nothing done"
    assert said_it in said.stdout
    got = rows(tiny)
    assert (got[-1]["round"], got[-1]["stage"]) == (2, "waits")
    assert got[-1]["why"].startswith("bye-fix: its check passes")
    with Store.open(tiny) as store:
        assert not store.node_log("bye-fix", ("attempt",))


def test_an_agent_cannot_run_auto_and_the_envelope_is_the_persons_alone(tiny, tmp_path):
    planner, executor = scripts(tmp_path)
    said = runner.invoke(build(), ["auto", GOAL, "--planner", planner, "--with", executor], env=AGENT_ENV)
    assert said.exit_code == 1 and "`graphene auto` is the person's" in said.output
    assert "this call comes from claude:5e55105e" in said.output
    assert rows(tiny) == []
    with Store.open(tiny) as store:
        assert store.meta("settings:auto") is None  # nothing was turned on


def test_with_no_goal_it_goes_on_with_the_plan_in_force(tiny, tmp_path):
    planner, executor = scripts(tmp_path)
    bare = person("auto", "--planner", planner, "--with", executor)
    assert bare.exit_code == 1 and "no goal is in force for `graphene auto` here" in bare.output
    first = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK)
    assert first.exit_code == 0, first.output
    again = person("auto", "--planner", planner, "--with", executor)  # done already: nothing more to do
    assert again.exit_code == 0, again.output
    assert rows(tiny)[-1]["stage"] == "done" and rows(tiny)[-1]["round"] == 3
    other = person("auto", "another goal", "--planner", planner, "--with", executor, "--check", "true")
    assert other.exit_code == 0, other.output  # the first goal's tree is finished: a new goal may follow it
    assert "): greet-2, bye-2. `graphene run` runs them" in other.stdout, other.stdout
    assert "auto: 1 round, 2 tasks landed, 0 came back, 0 forks raced, 2 attempts" in other.stdout
    with Store.open(tiny) as store:
        assert P.goal(store) == "another goal"
        assert json.dumps(AUTO.state(store))  # JSON all the way: `state --json` carries it as it is


def test_plan_only_plans_and_accepts_inside_the_envelope_and_runs_nothing_until_auto_goes_on(tiny, tmp_path):
    """`graphene auto "<goal>" --plan` is the cautious first try: the planner's tree, accepted inside the
    envelope and shown, nothing run and nothing spent on an executor; `graphene auto` then runs that round."""
    planner, executor = scripts(tmp_path)
    said = person("auto", GOAL, "--planner", planner, "--with", executor, "--check", GOAL_CHECK, "--plan")
    assert said.exit_code == 0, said.output
    assert "): greet, bye. `graphene run` runs them" in said.stdout
    assert said.stdout.strip().splitlines()[-1] == (
        "auto: planned round 1 inside your envelope and ran nothing: `graphene plan` shows it, "
        "`graphene auto` runs it")  # fmt: skip
    with Store.open(tiny) as store:
        assert {P.get(store, i).state for i in ("greet", "bye")} == {P.OPEN}
        assert not store.node_log(None, ("attempt",))  # no executor started
    assert [(r["round"], r["stage"]) for r in rows(tiny)] == [(1, "planning"), (1, "waits")]
    went = person("auto", "--planner", planner, "--with", executor)  # the same round goes on
    assert went.exit_code == 0, went.output
    assert "round 1: planning" not in went.stdout  # it was planned already
    assert [(r["round"], r["stage"]) for r in rows(tiny)][2:4] == [(1, "running"), (1, "checking")]
    assert went.stdout.strip().splitlines()[-1].startswith("auto: 2 rounds, 3 tasks landed")


FAILING_PLANNER = "import sys\nprint('stopped: no key here', file=sys.stderr)\nsys.exit(3)\n"


def test_a_round_whose_planner_failed_is_planned_again_when_auto_goes_on(tiny, tmp_path):
    """A first `graphene auto` whose planner could not start (no key) left the goal's root with nothing under
    it, and the next `graphene auto` counted itself round 2 and planned nothing: the goal could never start.
    Nothing planned under the root yet, the round is planned again, with the goal's check as first given."""
    planner, executor = scripts(tmp_path)
    (tmp_path / "broken.py").write_text(FAILING_PLANNER)
    said = person("auto", GOAL, "--planner", f"{sys.executable} {tmp_path / 'broken.py'}", "--with", executor,
                  "--check", GOAL_CHECK)  # fmt: skip
    assert said.exit_code == 3, said.output
    went = person("auto", "--planner", planner, "--with", executor)  # the key is set now, say
    assert went.exit_code == 0, went.output
    assert "round 1: planning" in went.stdout
    assert went.stdout.strip().splitlines()[-1].startswith("auto: 2 rounds, 3 tasks landed")
