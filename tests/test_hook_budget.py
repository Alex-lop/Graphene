"""What the hook costs the agent, measured: twenty real subprocess runs of `graphene ingest hook`.

Claude Code waits for this command on every tool call, so the number is a budget, not a claim.
The same file checks the reason it is small: the hook path imports no Typer, Rich or Click, and
what each event imports, the SQL statements it runs and the processes it starts are written down in
WORK, so a change that adds to any of them fails here.
"""

import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

from graphene_map import gate, hooks, plan
from graphene_map.store import Store

RUNS = 20
BUDGET_MS = 150 if os.environ.get("CI") else 60  # a shared CI runner is slower and noisier
HOOK = [sys.executable, "-c", "from graphene_map.cli import app; app()", "ingest", "hook"]
PROBE = """
import os, sys
sys.argv = ["graphene", "ingest", "hook"]
os._exit = sys.exit  # the hook ends with os._exit, which would end this probe before it prints
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


# -- what each event does -------------------------------------------------------------------------

# One run of the hook, counted from inside: the Graphene modules and the costly standard ones it
# imported, the SQL statements it ran, the processes it started. The probe itself imports only what
# every event imports (os, sys, json, sqlite3), so every module it lists is the hook's.
WORK_PROBE = """
import json, os, sqlite3, sys
os._exit = sys.exit  # the hook ends with os._exit, which would end this probe before it reports
work = {"sql": 0, "spawned": 0}
connect = sqlite3.connect
def counted(*args, **kwargs):
    conn = connect(*args, **kwargs)
    conn.set_trace_callback(lambda sql: work.__setitem__("sql", work["sql"] + 1))
    return conn
sqlite3.connect = counted
def audit(name, args):
    if name == "subprocess.Popen":
        work["spawned"] += 1
sys.addaudithook(audit)
sys.argv = ["graphene", "ingest", "hook"]
from graphene_map.cli import app
try:
    app()
except SystemExit:
    pass
COSTLY = {"subprocess", "tempfile", "traceback", "uuid", "shlex", "threading", "typer", "rich", "click"}
names = [m.removeprefix("graphene_map.") for m in sys.modules if m.startswith("graphene_map.") or m in COSTLY]
print("\\n" + json.dumps({**work, "modules": sorted(names)}))
"""

# The modules every event loads to record it: the entry point, the hook, the store and its records.
RECORD = {"cli", "hooks", "model", "store"}
# ...and what the gate adds, when an event can be answered (hooks.gated): the plan, and the standard
# modules the plan needs to run a check.
GATE = RECORD | {"gate", "plan", "shlex", "subprocess", "threading"}
# A plan in force: the person's standing paths are read on every write, and a Bash call is parsed.
IN_FORCE = GATE | {"settings", "board"}

# (repo, event): the modules, SQL statements and processes of that event, run in this order on one
# store. The session status the direction work records (alive, idle, waiting on you, the last thing
# done, the bill) belongs in the rows these statements already write, or is read from them later:
# a new module here, a new statement on every event, or any process is a cost the agent waits for.
WORK = {
    ("none", "SessionStart"): (GATE, 11, 0),
    ("none", "UserPromptSubmit"): (RECORD, 10, 0),
    ("none", "PreToolUse Read"): (RECORD, 5, 0),
    ("none", "PreToolUse Edit"): (RECORD, 7, 0),
    ("none", "PostToolUse Read"): (RECORD, 8, 0),
    ("none", "PostToolUse Bash"): (RECORD, 9, 0),
    ("none", "SubagentStart"): (RECORD, 7, 0),
    ("none", "Stop"): (RECORD, 8, 0),
    ("first", "SessionStart"): (GATE, 11, 0),
    ("first", "UserPromptSubmit"): (GATE, 18, 0),
    ("first", "PreToolUse Read"): (RECORD, 5, 0),
    ("first", "PreToolUse Edit"): (GATE | {"shell"}, 13, 0),
    ("first", "PostToolUse Read"): (RECORD, 8, 0),
    ("first", "PostToolUse Bash"): (RECORD, 9, 0),
    ("first", "SubagentStart"): (RECORD, 7, 0),
    ("first", "Stop"): (RECORD, 8, 0),
    ("plan", "SessionStart"): (GATE, 13, 0),
    ("plan", "UserPromptSubmit"): (GATE, 17, 0),
    ("plan", "PreToolUse Read"): (RECORD, 5, 0),
    ("plan", "PreToolUse Edit"): (IN_FORCE | {"shell"}, 19, 0),
    ("plan", "PostToolUse Read"): (RECORD, 8, 0),
    ("plan", "PostToolUse Bash"): (IN_FORCE, 15, 0),
    ("plan", "SubagentStart"): (RECORD, 7, 0),
    ("plan", "Stop"): (GATE, 12, 0),
}


def _repo(tmp_path: Path, kind: str) -> Path:
    repo = tmp_path / kind
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "start"], check=True)
    with Store.open(repo) as store:
        if kind == "first":
            plan.set_plan_first(store, True, plan.Caller("alex", True))
        if kind == "plan":
            node = plan.Node("n1", "api", scope=["src/api/**"], check="true", state=plan.RUNNING)
            node.session_id = "s"
            store.put_node(plan.to_dict(node))
    return repo


def _event(repo: Path, label: str, n: int = 0) -> dict:
    name, _, tool = label.partition(" ")
    event = {"hook_event_name": name, "session_id": "s", "cwd": str(repo), "prompt": "fix it"}
    event["prompt_id"] = f"p{n}"
    if name == "SubagentStart":
        event.update(agent_id="a1", agent_type="Explore")
    if tool:
        path = str(repo / "src" / "api" / "a.py")
        event.update(tool_name=tool, tool_use_id=f"t{n}")
        event["tool_input"] = {"command": "pytest -q"} if tool == "Bash" else {"file_path": path}
        if name == "PostToolUse":
            said = {"stdout": "1 passed\n"} if tool == "Bash" else {"file": {"content": "x"}}
            event["tool_response"] = said
    return event


def test_each_event_imports_runs_and_starts_only_what_it_did(tmp_path, monkeypatch):
    """The guard for whatever the hook is asked to do next: an event that imports another module,
    runs another statement or starts a process fails here until WORK says so, with its cost."""
    monkeypatch.delenv("GRAPHENE_PLANNER", raising=False)
    monkeypatch.delenv("GRAPHENE_NODE", raising=False)
    found = {}
    for kind in ("none", "first", "plan"):
        repo = _repo(tmp_path, kind)
        for state, label in WORK:
            if state != kind:
                continue
            done = subprocess.run(
                [sys.executable, "-c", WORK_PROBE],
                input=json.dumps(_event(repo, label)),
                cwd=repo,
                capture_output=True,
                text=True,
            )
            assert done.returncode == 0, done.stderr
            work = json.loads(done.stdout.splitlines()[-1])
            found[(kind, label)] = (set(work["modules"]), work["sql"], work["spawned"])
    changed = {k: (found[k], v) for k, v in WORK.items() if found[k] != v}
    assert not changed, "\n".join(f"{k}: now {now}, written down {was}" for k, (now, was) in changed.items())


@pytest.mark.parametrize("kind", ["none", "first", "plan"])
def test_the_gate_answers_nothing_to_an_event_the_hook_does_not_ask_it_about(tmp_path, monkeypatch, kind):
    """hooks.gated keeps the gate (and the plan) off an event the gate cannot answer: for every such
    event, the gate itself says nothing and writes nothing."""
    monkeypatch.delenv("GRAPHENE_PLANNER", raising=False)
    monkeypatch.delenv("GRAPHENE_NODE", raising=False)
    repo = _repo(tmp_path, kind)
    names = ["UserPromptSubmit", "PostToolUseFailure", "SubagentStart", "SubagentStop", "Stop"]
    tools = ["Read", "Grep", "Glob", "WebFetch", "Agent", "Task", "TodoWrite", "Skill"]
    tools += ["Edit", "Write", "Bash"]
    labels = names + [f"{name} {tool}" for name in ("PreToolUse", "PostToolUse") for tool in tools]
    skipped = set()
    with Store.open(repo) as store:
        for n, label in enumerate(labels):
            event = _event(repo, label, n)
            if hooks.gated(store, event):
                continue
            skipped.add(label)
            changes = store.conn.total_changes
            assert gate.decide(store, event, repo) is None, label
            assert store.conn.total_changes == changes, label
    reads = {f"{name} {tool}" for name in ("PreToolUse", "PostToolUse") for tool in ("Read", "Grep", "Glob")}
    assert reads <= skipped  # a read or a search is never the gate's, plan or no plan
