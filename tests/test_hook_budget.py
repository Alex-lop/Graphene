"""What the hook costs the agent, measured: twenty real subprocess runs of `graphene ingest hook`.

Claude Code waits for this command on every tool call, so the number is a budget, not a claim.
The same file checks the reason it is small: the hook path imports no Typer, Rich or Click.
"""

import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from graphene_map.store import Store

RUNS = 20
BUDGET_MS = 150 if os.environ.get("CI") else 60  # a shared CI runner is slower and noisier
HOOK = [sys.executable, "-c", "from graphene_map.cli import app; app()", "ingest", "hook"]
PROBE = """
import sys
sys.argv = ["graphene", "ingest", "hook"]
from graphene_map.cli import app
try:
    app()
except SystemExit:
    pass
print(sorted(m for m in sys.modules if m.split(".")[0] in {"typer", "rich", "click"}))
"""


def post_tool_use(repo: Path, n: int) -> str:
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "budget",
            "cwd": str(repo),
            "tool_name": "Bash",
            "tool_use_id": f"toolu_{n}",
            "tool_input": {"command": "pytest -q"},
            "tool_response": {"stdout": "149 passed\n", "stderr": "", "interrupted": False},
        }
    )


def run_hook(repo: Path, n: int) -> float:
    """One run, as Claude Code makes it. Returns how long the agent waited, in milliseconds."""
    start = time.perf_counter()
    done = subprocess.run(HOOK, input=post_tool_use(repo, n), cwd=repo, capture_output=True, text=True)
    elapsed = (time.perf_counter() - start) * 1000
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""  # anything on stdout is a message Claude Code would read as the hook's
    return elapsed


def test_the_hook_stays_inside_its_time_budget(tmp_path, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    run_hook(repo, 0)  # warm-up: the first run creates the store, and pays for it
    times = sorted(run_hook(repo, n + 1) for n in range(RUNS))
    median = statistics.median(times)
    p95 = times[math.ceil(0.95 * RUNS) - 1]
    with capsys.disabled():
        print(f"\nhook: median {median:.0f} ms, p95 {p95:.0f} ms over {RUNS} runs (budget {BUDGET_MS} ms)")
    with Store.open(repo) as store:
        assert store.event_count("budget") == RUNS + 1  # every run recorded its call, warm-up included
    assert median < BUDGET_MS, f"median {median:.0f} ms over budget {BUDGET_MS} ms (p95 {p95:.0f} ms)"


def test_refusing_a_write_stays_inside_the_same_budget(tmp_path, capsys):
    """The other hot path: with a plan in force every write is looked up against the node's scope
    before it happens, and the agent waits for that answer too."""
    from graphene_map import plan

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    node = plan.Node(
        "n1", "users", scope=["src/api/**"], check="true", state=plan.RUNNING, session_id="budget"
    )
    with Store.open(repo) as store:
        store.put_node(plan.to_dict(node))

    def pre_tool_use(path: str) -> float:
        event = {
            "hook_event_name": "PreToolUse",
            "session_id": "budget",
            "cwd": str(repo),
            "tool_name": "Edit",
            "tool_input": {"file_path": str(repo / path)},
        }
        start = time.perf_counter()
        done = subprocess.run(HOOK, input=json.dumps(event), cwd=repo, capture_output=True, text=True)
        elapsed = (time.perf_counter() - start) * 1000
        assert done.returncode == 0, done.stderr
        assert ("deny" in done.stdout) is (not path.startswith("src/api/")), done.stdout
        return elapsed

    pre_tool_use("src/api/users.py")
    times = sorted(pre_tool_use(("src/api/a.py", "src/db/b.py")[n % 2]) for n in range(RUNS))
    median = statistics.median(times)
    with capsys.disabled():
        print(
            f"\ngate: median {median:.0f} ms, p95 {times[math.ceil(0.95 * RUNS) - 1]:.0f} ms over {RUNS} runs"
        )
    assert median < BUDGET_MS, f"median {median:.0f} ms over budget {BUDGET_MS} ms"


def test_plan_first_stays_inside_the_same_budget(tmp_path, capsys):
    """Plan first adds a path that runs with no plan at all: every prompt of a session that holds no
    leaf is told, and every write it tries before proposing is refused. The agent waits for both."""
    from graphene_map import plan

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with Store.open(repo) as store:
        plan.set_plan_first(store, True, plan.Caller("alex", True))
    edit = {"tool_name": "Edit", "tool_input": {"file_path": str(repo / "a.py")}}

    def once(n: int) -> float:
        prompt = n % 2
        said = {"hook_event_name": "UserPromptSubmit", "prompt": "fix the header", "prompt_id": f"p{n}"}
        event = {
            "session_id": "budget",
            "cwd": str(repo),
            **(said if prompt else {"hook_event_name": "PreToolUse", **edit}),
        }
        start = time.perf_counter()
        done = subprocess.run(HOOK, input=json.dumps(event), cwd=repo, capture_output=True, text=True)
        elapsed = (time.perf_counter() - start) * 1000
        assert done.returncode == 0, done.stderr
        assert ("Plan first is on" if prompt else "plan first: this session holds no leaf") in done.stdout
        return elapsed

    once(1)
    times = sorted(once(n) for n in range(RUNS))
    median = statistics.median(times)
    with capsys.disabled():
        print(f"\nplan first: median {median:.0f} ms, p95 {times[math.ceil(0.95 * RUNS) - 1]:.0f} ms")
    assert median < BUDGET_MS, f"median {median:.0f} ms over budget {BUDGET_MS} ms"


def test_the_hook_path_imports_no_cli_library(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    done = subprocess.run(
        [sys.executable, "-c", PROBE], input=post_tool_use(repo, 0), cwd=repo, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"  # Typer and Rich are what the other commands pay for
