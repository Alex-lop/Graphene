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

from graphene_debrief.store import Store

RUNS = 20
BUDGET_MS = 150 if os.environ.get("CI") else 60  # a shared CI runner is slower and noisier
HOOK = [sys.executable, "-c", "from graphene_debrief.cli import app; app()", "ingest", "hook"]
PROBE = """
import sys
sys.argv = ["graphene", "ingest", "hook"]
from graphene_debrief.cli import app
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


def test_the_hook_path_imports_no_cli_library(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    done = subprocess.run(
        [sys.executable, "-c", PROBE], input=post_tool_use(repo, 0), cwd=repo, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"  # Typer and Rich are what the other commands pay for
