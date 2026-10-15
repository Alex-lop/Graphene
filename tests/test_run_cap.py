"""`graphene run --max-usd N`: a cap on what the run starts. Before an attempt starts, its worst case and
what is held and spent must fit under N; one that fits only once what is going has settled waits for it,
and one that could not fit with nothing going stops every start. Each attempt settles at what its stream
says it spent. The executor is a stand-in named `claude` that prints a real stream."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from graphene_map import meter as M
from graphene_map import plan
from graphene_map import run as R
from graphene_map.plan import DONE, OPEN, Caller
from graphene_map.run import run_parallel
from graphene_map.store import Store

ALEX = Caller("alex", True)
STREAM = Path(__file__).parent / "fixtures" / "meter" / "claude.jsonl"  # total_cost_usd 0.0622574
STAND_IN = """#!{python}
import os, pathlib
print(pathlib.Path({stream!r}).read_text(), flush=True)
pathlib.Path(os.environ["GRAPHENE_NODE"] + ".txt").write_text("done\\n")
"""
CLI = [sys.executable, "-c", "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_NODE"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (root / "a.txt").write_text("a\n")
    git("add", "-A")
    git("commit", "-qm", "start")
    monkeypatch.chdir(root)
    leaves = [{"id": i, "title": f"leaf {i}", "scope": [f"{i}.txt"], "check": f"grep -q done {i}.txt"}
              for i in ("a", "b")]  # fmt: skip
    with Store.open(root) as store:
        plan.propose(store, leaves, ALEX)
    (tmp_path / "bin").mkdir()
    script = tmp_path / "bin" / "claude"  # the meter knows an executor by its command's name
    script.write_text(STAND_IN.format(python=sys.executable, stream=str(STREAM)))
    script.chmod(0o755)
    return root


def executor(root: Path) -> str:
    return f"{root.parent / 'bin' / 'claude'} --output-format stream-json --verbose --max-budget-usd 1"


def run(root: Path, workers: int, cap: float | None) -> tuple[dict[str, str], list[str], set[str]]:
    said: list[str] = []
    run_parallel(lambda: Store.open(root), root, root, workers, executor(root), say=said.append,
                 logs=root.parent / "logs", max_usd=cap)  # fmt: skip
    with Store.open(root) as store:
        started = {e["node_id"] for e in store.node_log(None, ("started",))}
        return {n.id: n.state for n in plan.nodes(store)}, said, started


def test_a_start_that_fits_only_once_what_is_going_settles_waits_for_it(repo):
    """Two at once would hold $2 on a cap of $1.50; the first settles at the $0.06 its stream says, and
    the second starts. The run did not stop starting for room that was only held."""
    states, said, started = run(repo, 2, 1.5)
    assert states == {"a": DONE, "b": DONE} and len(started) == 2
    assert not [s for s in said if s.startswith("stopped starting")]


def test_a_start_that_could_not_fit_with_nothing_going_stops_every_start_and_says_why(repo):
    """$0.06 spent and $1 to hold is past $1.05, whatever else settles."""
    states, said, started = run(repo, 2, 1.05)
    assert sorted(states.values()) == [DONE, OPEN] and len(started) == 1  # the other was never started
    assert [s for s in said if s.startswith("stopped starting")] == [
        "stopped starting: $0.06 spent, $0.00 held, cap $1.05"
    ]


def test_a_budget_waits_for_room_said_once_and_a_second_attempt_waits_in_its_worker():
    said: list[str] = []
    budget = R.Budget(1.5, said.append)
    assert budget.take(1.0) is True
    assert budget.take(1.0) is None  # $1 held, $0 spent: it fits once that settles
    got: list = []
    waiter = threading.Thread(target=lambda: got.append(budget.take(1.0, R.Stop())))
    waiter.start()
    time.sleep(0.3)
    assert got == []  # still waiting for the first to settle
    budget.settle(1.0, 0.06)
    waiter.join(10)
    assert got == [True] and not said
    budget.settle(1.0, 1.0)  # $1.06 spent: $1 more never fits
    assert budget.take(1.0) is False and budget.take(1.0) is False
    assert said == ["stopped starting: $1.06 spent, $0.00 held, cap $1.50"]


def test_a_codex_attempt_with_no_list_price_counts_at_its_worst_case_on_a_cap_and_at_none_on_the_night():
    meter = M.Meter("codex", 1)  # no price: the bill says its tokens
    assert R._spent(meter, 3.0) == 0.0  # the night's ledger
    assert R._spent(meter, 3.0, 3.0) == 3.0  # a person's cap on dollars cannot take it for nothing


def test_an_attempt_settles_at_what_its_stream_says_so_the_next_one_fits(repo):
    """Settled at its worst case ($1), the first would leave no room for the second under $1.20; at
    what it spent ($0.06), it does."""
    states, said, _ = run(repo, 1, 1.2)
    assert states == {"a": DONE, "b": DONE}
    assert not [s for s in said if s.startswith("stopped starting")]


@pytest.mark.parametrize("cap", [100.0, None])
def test_a_cap_above_everything_or_none_changes_nothing(repo, cap):
    states, said, _ = run(repo, 2, cap)
    assert states == {"a": DONE, "b": DONE}
    assert not [s for s in said if s.startswith("stopped starting")]


@pytest.mark.parametrize("cap", ["1.05", None])
def test_the_runs_second_line_states_the_cap_and_that_nothing_starts_past_it(repo, cap):
    env = {**os.environ, "GRAPHENE_AS": "person:alex"}
    argv = [*CLI, "run", "--with", executor(repo), "--parallel", "2", *(["--max-usd", cap] if cap else [])]
    said = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, timeout=120)
    assert said.returncode == 0, said.stdout + said.stderr
    worst = next(line for line in said.stdout.splitlines() if line.startswith("worst case: "))
    if cap:
        assert worst == "worst case: 2 leaves x 3 attempts x $1 = $6; --max-usd $1.05 starts nothing past it"
        assert "stopped starting: $0.06 spent, $0.00 held, cap $1.05" in said.stdout
    else:
        assert worst == "worst case: 2 leaves x 3 attempts x $1 = $6"
        assert "stopped starting" not in said.stdout


def test_here_a_cap_below_one_attempts_worst_case_starts_nothing(repo):
    from graphene_map.run import run_plan

    said: list[str] = []
    with Store.open(repo) as store:
        assert run_plan(store, repo, executor(repo), say=said.append, max_usd=0.5) == []
        assert not store.node_log(None, ("started",))
    assert "stopped starting: $0.00 spent, $0.00 held, cap $0.50" in said


def test_an_attempt_after_the_first_that_does_not_fit_is_not_started_and_its_leaf_comes_back(repo):
    """Its first attempt refused (the check never passes), the second would hold $1 on $0.06 spent:
    past $1.05, so the leaf comes back with why, and nothing else starts."""
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "c", "title": "leaf c", "scope": ["c.txt"], "check": "false"}], ALEX)
    said: list[str] = []
    run_parallel(lambda: Store.open(repo), repo, repo, 1, executor(repo), only=["c"], say=said.append,
                 logs=repo.parent / "logs", max_usd=1.05)  # fmt: skip
    with Store.open(repo) as store:
        assert plan.get(store, "c").state == OPEN
        assert [e["detail"]["attempt"] for e in store.node_log("c", ("attempt",))] == [1]
    assert "stopped starting: $0.06 spent, $0.00 held, cap $1.05" in said
    assert "c came back: the run's --max-usd stopped it before attempt 2" in said
