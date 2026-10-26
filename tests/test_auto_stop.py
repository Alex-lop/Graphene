# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene auto` stops cleanly: the terminal's Ctrl-C while a task runs, or `graphene run --stop` from
another terminal (the run holds the repo's lock), hands the task back to the plan, the auto row says it
stopped, exit 1, and `graphene auto` with no goal goes on from there."""

import os
import signal
import sys

from test_run_live import SLOW, ended, executor, graphene, repo, wait_for  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map import plan as P
from graphene_map.store import Store

PLANNER = 'print("```plan\\n? a slow task  [slow]\\n    scope: a.txt\\n    check: true\\n```")\n'


def planner(repo) -> str:
    script = repo.parent / "planner.py"
    script.write_text(PLANNER)
    return f"{sys.executable} {script}"


def attempts(repo) -> int:
    with Store.open(repo) as store:
        return len(store.node_log("slow", ("attempt",)))


def stopped(repo, said: str) -> None:
    said_it = "auto stopped by you: what was running went back to the plan; `graphene auto` goes on"
    assert said_it in said, said
    with Store.open(repo) as store:
        row = AUTO.state(store)
        assert (row["stage"], row["round"]) == ("waits", 1) and row["why"].startswith("stopped by you"), row
        slow = P.get(store, "slow")
        assert slow.state == P.OPEN and not P.came_back(store, slow)  # handed back, ready for the next round
        [why] = [e["detail"]["why"] for e in store.node_log("slow", ("released",))]
        assert "the run was stopped before" in why
    pid = int((repo / ".graphene" / "worktrees" / "slow" / "pid.txt").read_text())
    assert wait_for(lambda: ended(pid), 15)  # the executor is gone too


def test_ctrl_c_hands_the_running_task_back_and_the_auto_row_says_it_stopped(repo):
    auto = graphene(repo, "auto", "a slow goal", "--planner", planner(repo), "--with", executor(repo, SLOW),
                    "--check", "true", session=True)  # fmt: skip
    assert wait_for(lambda: attempts(repo) == 1, 30)
    os.killpg(auto.pid, signal.SIGINT)  # the terminal's Ctrl-C
    said, _ = auto.communicate(timeout=60)
    assert auto.returncode == 1, said
    assert "run stopped: slow handed back, ready again" in said
    stopped(repo, said)


def test_run_stop_from_another_terminal_stops_it_the_same_way(repo):
    auto = graphene(repo, "auto", "a slow goal", "--planner", planner(repo), "--with", executor(repo, SLOW),
                    "--check", "true", session=True)  # fmt: skip
    assert wait_for(lambda: attempts(repo) == 1, 30)
    told, _ = graphene(repo, "run", "--stop").communicate(timeout=30)
    assert told.strip() == "stopping the run: what it holds goes back to the plan", told
    said, _ = auto.communicate(timeout=60)
    assert auto.returncode == 1, said
    stopped(repo, said)
