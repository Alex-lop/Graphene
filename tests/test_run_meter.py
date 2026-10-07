"""The meter in `graphene run`: the executor's stream is read from its log while it runs, and each
turn, tool call and thing said lands on the leaf as it happens. The executors here are stand-ins named
`claude` and `codex` that print the real streams in tests/fixtures/meter."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_run_live import ended

from graphene_map import plan
from graphene_map import run as R
from graphene_map.plan import DONE, Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
FIXTURES = Path(__file__).parent / "fixtures" / "meter"
CLI = [sys.executable, "-c", "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"]
CLAUDE_COST = 0.0622574  # the fixture's total_cost_usd
# Prints the fixture's lines; after line ``gate`` it waits for the test's go file. Then it does the leaf.
STAND_IN = """#!{python}
import pathlib, sys, time
for k, line in enumerate(pathlib.Path({fixture!r}).read_text().splitlines()):
    print(line, flush=True)
    if k == {gate}:
        until = time.monotonic() + 30
        while not pathlib.Path({go!r}).exists() and time.monotonic() < until:
            time.sleep(0.05)
pathlib.Path("a.txt").write_text("done\\n")
"""


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
    with Store.open(root) as store:
        leaf = {"id": "a", "title": "leaf a", "scope": ["a.txt"], "check": "grep -q done a.txt"}
        plan.propose(store, [leaf], ALEX)
    return root


def stand_in(repo: Path, name: str, source: str) -> Path:
    """An executable named ``name`` beside the repo: the meter knows an executor by its command's name."""
    where = repo.parent / "bin"
    where.mkdir(exist_ok=True)
    script = where / name
    script.write_text(source)
    script.chmod(0o755)
    return script


def printing(repo: Path, name: str, fixture: str, gate: int) -> tuple[Path, Path]:
    go = repo.parent / "go"
    source = STAND_IN.format(python=sys.executable, fixture=str(FIXTURES / fixture), gate=gate, go=str(go))
    return stand_in(repo, name, source), go


def wait_for(condition, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


def rows(repo: Path, *kinds: str) -> list[dict]:
    with Store.open(repo) as store:
        return store.node_log("a", kinds or None)


def run_cli(repo: Path, executor: str) -> subprocess.Popen:
    env = {**os.environ, "GRAPHENE_AS": "person:alex"}
    return subprocess.Popen([*CLI, "run", "--with", executor], cwd=repo, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)  # fmt: skip


@pytest.mark.parametrize(
    ("name", "with_", "fixture", "gate"),
    [("claude", "--output-format stream-json --verbose", "claude.jsonl", 3),
     ("codex", "exec --json", "codex.jsonl", 11)],  # fmt: skip
)
def test_the_stream_lands_on_the_leaf_while_the_executor_runs(repo, name, with_, fixture, gate):
    script, go = printing(repo, name, fixture, gate)
    run = run_cli(repo, f"{script} {with_}")
    try:
        assert wait_for(lambda: rows(repo, "usage")), "no usage row while the executor ran"
        assert run.poll() is None and not rows(repo, "ended")  # the executor is still waiting for go
        assert [e["detail"]["meter"] for e in rows(repo, "attempt")] == [name]  # known from the start
    finally:
        go.write_text("go")
    said, _ = run.communicate(timeout=60)
    assert run.returncode == 0, said
    usage = [e["detail"] for e in rows(repo, "usage")]
    [ended] = [e["detail"] for e in rows(repo, "ended")]
    assert ended | {"seconds": 0} == {"attempt": 1, "exit": 0, "seconds": 0, "meter": name,
                                      "unread": 0 if name == "claude" else 1}  # fmt: skip
    last = said.strip().splitlines()[-1]
    if name == "claude":
        assert sum(u["dollars"] for u in usage) == pytest.approx(CLAUDE_COST)
        assert [e["detail"]["verb"] for e in rows(repo, "did")] == ["reading", "editing", "running"]
        assert last == "run: 1 done · agents <1 min, $0.0623 at list price · you 0 acts, 0 min"
    else:
        assert last == ("run: 1 done · agents <1 min, $0.0000 at list price + 49k tokens with no list price"
                        " · you 0 acts, 0 min")  # fmt: skip
        assert usage == [{"model": "codex", "calls": 1, "prompt_tokens": 48940, "completion_tokens": 344,
                          "dollars": 0, "endpoint": "codex", "attempt": 1, "turn": 1,
                          "priced": False}]  # fmt: skip
    with Store.open(repo) as store:
        assert plan.get(store, "a").state == DONE


GARBAGE = """#!{python}
import pathlib
print("Reading additional input from stdin...", flush=True)
print("Traceback (most recent call last): nothing here is JSON", flush=True)
print('[1, 2]', flush=True)
print('{{"type": "assistant", "message": {{"id": "msg_1", "usage": {{"input_tok', end="", flush=True)
pathlib.Path("a.txt").write_text("done\\n")
"""


def test_a_stream_the_meter_cannot_read_leaves_the_run_as_it_was(repo):
    script = stand_in(repo, "claude", GARBAGE.format(python=sys.executable))
    run = run_cli(repo, f"{script} --output-format stream-json")
    said, _ = run.communicate(timeout=60)
    assert run.returncode == 0, said
    assert not rows(repo, "usage", "did", "said")  # no meter number invented
    [ended] = [e["detail"] for e in rows(repo, "ended")]
    assert ended["meter"] == "claude" and ended["unread"] == 4 and ended["exit"] == 0
    assert said.strip().splitlines()[-1] == "run: 1 done · agents <1 min, no meter · you 0 acts, 0 min"
    with Store.open(repo) as store:
        assert plan.get(store, "a").state == DONE
    assert (repo / "a.txt").read_text() == "done\n"  # landed


RESUMED = """#!{python}
import json, pathlib, sys
lines = pathlib.Path({fixture!r}).read_text().splitlines()
result = json.loads(lines[-1])
again = "--resume" in sys.argv
result["total_cost_usd"] = 0.1 if again else 0.07  # the session's running total
print("\\n".join([*lines[:-1], json.dumps(result)]), flush=True)
if again:
    pathlib.Path("a.txt").write_text("done\\n")
"""


def test_a_resumed_attempt_is_billed_what_the_session_added(repo):
    source = RESUMED.format(python=sys.executable, fixture=str(FIXTURES / "claude.jsonl"))
    script = stand_in(repo, "claude", source)
    with Store.open(repo) as store:
        done = R.run_plan(store, repo, f"{script} --output-format stream-json", say=lambda _: None,
                          logs=repo / ".graphene" / "runs")  # fmt: skip
        assert [n.id for n in done] == ["a"]
        usage = [e["detail"] for e in store.node_log("a", ("usage",))]
    by = {a: sum(u["dollars"] for u in usage if u["attempt"] == a) for a in (1, 2)}
    assert by[1] == pytest.approx(0.07) and by[2] == pytest.approx(0.03)


def test_a_resumed_attempt_settles_its_own_output_tokens(repo, tmp_path, monkeypatch):
    """The review of 7 October: a resumed attempt took what earlier attempts settled off its result's
    usage, which is the call's own (only total_cost_usd is the session's running total). Attempt 2 kept
    the stream's 75 output tokens of the 539 its result said, in node show, watch and the night's ledger."""
    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "10")
    source = RESUMED.format(python=sys.executable, fixture=str(FIXTURES / "claude.jsonl"))
    script = stand_in(repo, "claude", source)
    with Store.open(repo) as store:
        R.run_plan(store, repo, f"{script} --output-format stream-json", say=lambda _: None,
                   logs=repo / ".graphene" / "runs")  # fmt: skip
        usage = [e["detail"] for e in store.node_log("a", ("usage",))]
    assert [sum(u["completion_tokens"] for u in usage if u["attempt"] == a) for a in (1, 2)] == [539, 539]
    assert [r["completion_tokens"] for r in ledger(tmp_path) if r["kind"] == "settle"] == [539, 539]


def test_an_executor_with_no_stream_has_no_meter_and_its_attempt_still_ends(repo):
    source = f"#!{sys.executable}\nimport pathlib\npathlib.Path('a.txt').write_text('done')\n"
    script = stand_in(repo, "work", source)
    with Store.open(repo) as store:
        R.run_plan(store, repo, str(script), say=lambda _: None, logs=repo / ".graphene" / "runs")
        assert not store.node_log("a", ("usage", "did", "said"))
        [ended] = [e["detail"] for e in store.node_log("a", ("ended",))]
    assert ended["meter"] is None and ended["unread"] == 0 and ended["exit"] == 0


def test_codex_is_priced_from_token_factorys_list_when_it_names_a_listed_model(repo, monkeypatch):
    script, go = printing(repo, "codex", "codex.jsonl", -1)
    monkeypatch.setattr(R, "_listed", lambda: {"nvidia/super": (1e-7, 5e-7)})
    with Store.open(repo) as store:
        R.run_plan(store, repo, f"{script} exec --json -m nvidia/super", say=lambda _: None,
                   logs=repo / ".graphene" / "runs")  # fmt: skip
        [usage] = [e["detail"] for e in store.node_log("a", ("usage",))]
    assert usage["model"] == "nvidia/super" and "priced" not in usage
    assert usage["dollars"] == pytest.approx(48940e-7 + 344 * 5e-7)


def test_token_factorys_list_is_asked_once_a_process_and_a_failure_is_no_price(monkeypatch):
    asked = []

    def models():
        asked.append(1)
        raise OSError("offline")

    monkeypatch.setattr(R.extra, "load", lambda name: SimpleNamespace(models=models))
    R._listed.cache_clear()
    try:
        assert R._listed() == {} and R._listed() == {} and len(asked) == 1
    finally:
        R._listed.cache_clear()


def ledger(tmp_path: Path) -> list[dict]:
    path = tmp_path / "night.jsonl"  # the suite's night (conftest)
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_under_the_opening_an_attempt_holds_its_worst_case_and_settles_at_what_it_spent(
    repo, tmp_path, monkeypatch
):
    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "10")
    script, _ = printing(repo, "claude", "claude.jsonl", -1)
    with Store.open(repo) as store:
        executor = f"{script} --output-format stream-json --max-budget-usd 2"
        R.run_plan(store, repo, executor, say=lambda _: None, logs=repo / ".graphene" / "runs")
    held, settled = ledger(tmp_path)
    assert held | {"at": 0, "id": 0} == {"at": 0, "kind": "reserve", "id": 0, "model": "claude:default",
                                         "tag": "run: a attempt 1", "endpoint": "claude code", "dollars": 2.0,
                                         "purpose": "unsaid", "practice": True}  # fmt: skip
    assert settled["id"] == held["id"] and settled["dollars"] == pytest.approx(CLAUDE_COST)
    assert (settled["prompt_tokens"], settled["completion_tokens"]) == (60425, 539)  # as the result says


# Prints the fixture's lines up to ``upto`` (None: all of them), then does the leaf.
CUT = """#!{python}
import pathlib
print("\\n".join(pathlib.Path({fixture!r}).read_text().splitlines()[:{upto}]), flush=True)
pathlib.Path("a.txt").write_text("done\\n")
"""


@pytest.mark.parametrize(
    ("name", "with_", "upto", "dollars"),
    [("claude", "--output-format stream-json --max-budget-usd 2", -1, 2.0),  # its result never read
     ("codex", "exec --json -m nvidia/super", -1, 3.0),  # its turn never completed
     ("codex", "exec --json -m nvidia/super", None, 48940e-7 + 344 * 5e-7),  # every turn completed
     ("codex", "exec --json", -1, 0.0),  # no list price: its tokens alone, whole or not
     ("claude", "-p --model sonnet", None, 3.0)],  # no stream the meter reads  # fmt: skip
)
def test_a_held_attempt_settles_at_its_stream_only_when_the_stream_gave_the_whole_figure(
    repo, tmp_path, monkeypatch, name, with_, upto, dollars
):
    """The review of 7 October: a hold settled at what the stream had said so far, so a Codex turn that
    never completed and a command with no stream settled at $0, and a Claude Code result never read at the
    stream's early count. The night never saw that spend, and the next attempts started on it."""
    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "10")
    monkeypatch.setattr(R, "_listed", lambda: {"nvidia/super": (1e-7, 5e-7)})
    source = CUT.format(python=sys.executable, fixture=str(FIXTURES / f"{name}.jsonl"), upto=upto)
    script = stand_in(repo, name, source)
    with Store.open(repo) as store:
        R.run_plan(store, repo, f"{script} {with_}", say=lambda _: None, logs=repo / ".graphene" / "runs")
        assert plan.get(store, "a").state == DONE
    [settled] = [r for r in ledger(tmp_path) if r["kind"] == "settle"]
    assert settled["dollars"] == pytest.approx(dollars)


def test_a_run_killed_outright_has_its_hold_settled_by_the_next_runs_sweep_before_the_night_is_asked(
    repo, tmp_path, monkeypatch
):
    """The review of 7 October: nothing settled the hold of a run killed outright (kill -9, Force Quit),
    and the next run asked the night before its sweep. Refused, with the dead hold in flight until noon,
    it left the dead run's leaf `running` and its executor at work."""
    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "3.2")  # room for one $3 hold, which alone is past 90%
    monkeypatch.setattr(R, "GRACE", 1)
    script, _ = printing(repo, "claude", "claude.jsonl", 11)  # its whole stream, then it waits
    run = run_cli(repo, f"{script} --output-format stream-json")
    try:
        assert wait_for(lambda: any("reported" in e["detail"] for e in rows(repo, "usage")))
    finally:
        run.kill()  # nothing of the run's own runs on its way out
        run.communicate(timeout=30)
    executor = rows(repo, "attempt")[0]["detail"]["pid"]
    assert [r["kind"] for r in ledger(tmp_path)] == ["reserve"] and R._alive(executor)
    whole = CUT.format(python=sys.executable, fixture=str(FIXTURES / "claude.jsonl"), upto=None)
    stand_in(repo, "claude", whole)  # the next run's executor: its whole stream, then the leaf
    with Store.open(repo) as store:
        done = R.run_plan(store, repo, f"{script} --output-format stream-json", say=lambda _: None,
                          logs=repo / ".graphene" / "runs")  # fmt: skip
    assert [n.id for n in done] == ["a"] and ended(executor)  # stopped by the sweep
    got = ledger(tmp_path)
    assert [r["kind"] for r in got] == ["reserve", "settle", "reserve", "settle"]
    assert got[1]["id"] == got[0]["id"] and got[1]["dollars"] == pytest.approx(CLAUDE_COST)  # as its log says


def test_a_hold_settles_in_the_ledger_that_holds_it_under_its_own_purpose_whenever_it_ends(
    repo, tmp_path, monkeypatch
):
    """The second review of 7 October: a hold settled in whichever night was current when it ended, under
    the purpose of the shell that settled it. A dead run's holds, swept after noon, were the new night's
    spend and refused its first run; settled again there, a hold was counted in both nights."""
    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "10")
    monkeypatch.setenv("GRAPHENE_NIGHT_PURPOSE", "meter")
    script, _ = printing(repo, "claude", "claude.jsonl", -1)
    waited = R._waited

    def noon(*args):  # the night rolls over while the executor works, in a shell that says another purpose
        monkeypatch.setenv("GRAPHENE_NIGHT_LEDGER", str(tmp_path / "next.jsonl"))
        monkeypatch.setenv("GRAPHENE_NIGHT_PURPOSE", "dogfood")
        return waited(*args)

    monkeypatch.setattr(R, "_waited", noon)
    with Store.open(repo) as store:
        R.run_plan(store, repo, f"{script} --output-format stream-json", say=lambda _: None,
                   logs=repo / ".graphene" / "runs")  # fmt: skip
    held, settled = ledger(tmp_path)  # none in the next night's
    assert settled["id"] == held["id"] and (held["purpose"], settled["purpose"]) == ("meter", "meter")
    assert not (tmp_path / "next.jsonl").exists()


def test_the_sweep_settles_a_dead_runs_hold_whatever_its_leaf_has_become_and_never_a_live_runs(
    repo, tmp_path, monkeypatch
):
    """The second review of 7 October: the sweep settled a dead run's hold only through a leaf still
    `running`, or done in a run's worktree. The executor a run killed outright leaves working ends its leaf
    itself (`release`, or `done` with --here), and its $3 stayed in flight until noon."""
    from graphene_map.nemotron import night

    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "10")
    gone = subprocess.Popen(["true"])
    gone.wait()  # its pid, beside a start no process has: a run that ended
    runs = {"dead": (gone.pid, "Thu Jan  1 00:00:00 1970"), "live": (os.getpid(), R._started(os.getpid()))}
    last = str(tmp_path / "last.jsonl")  # the night each was held in
    with Store.open(repo) as store:  # leaf a is open: the dead run's executor handed it back itself
        for who, (pid, began) in runs.items():
            hold = {"model": "claude:default", "worst": 3.0, "paid": 0.0, "ledger": last}
            hold["id"] = night.reserve(hold["model"], 3.0, f"run: a {who}", "claude code", last)
            store.log_node("a", plan._now(), "attempt", "run:claude", who, None,
                           {"attempt": 1, "run_pid": pid, "run_start": began, "log": None, "meter": "claude",
                            "hold": hold})  # fmt: skip
        R.sweep(store, lambda _: None, repo)
    got = [json.loads(line) for line in Path(last).read_text().splitlines()]
    assert [(r["kind"], r["dollars"]) for r in got] == [("reserve", 3.0), ("reserve", 3.0), ("settle", 3.0)]
    assert got[2]["id"] == got[0]["id"] and not ledger(tmp_path)  # the dead run's, in its own night


def test_an_attempt_the_ledger_refuses_never_starts_and_its_leaf_comes_back(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "1")
    script, _ = printing(repo, "codex", "codex.jsonl", -1)
    said = []
    with Store.open(repo) as store:
        assert R.run_plan(store, repo, f"{script} exec --json", say=said.append,
                          logs=repo / ".graphene" / "runs") == []  # fmt: skip
        assert plan.get(store, "a").state == plan.OPEN and not store.node_log("a", ("attempt",))
    assert said[-1].startswith("a came back: refused: a call to codex:codex may cost up to $3.0000")
    assert "\n" not in said[-1] and (repo / "a.txt").read_text() == "a\n"  # nothing ran
    assert ledger(tmp_path) == []


def test_the_clocks_read_minutes_dollars_tokens_with_no_price_and_the_persons_acts(monkeypatch):
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")

    def row(at: str, kind: str, detail: dict, actor: str = "run:codex") -> dict:
        return {"node_id": "a", "timestamp": f"2026-10-07T04:{at}.000Z", "kind": kind, "actor": actor,
                "detail": detail}  # fmt: skip

    turn = {"calls": 1, "attempt": 1, "turn": 1}
    log = [row("00:00", "attempt", {"attempt": 1}),
           row("05:00", "accepted", {}, actor="alex"), row("05:30", "answered", {}, actor="alex (no tty)"),
           row("10:00", "usage", {**turn, "prompt_tokens": 120_000, "completion_tokens": 400, "dollars": 0,
                                  "priced": False}),
           row("20:00", "usage", {**turn, "prompt_tokens": 10, "completion_tokens": 1, "dollars": 0.42}),
           row("41:00", "ended", {"attempt": 1, "exit": 0, "meter": "codex", "unread": 0})]  # fmt: skip
    assert R.clocks(log) == (" · agents 41 min, $0.4200 at list price + 120k tokens with no list price"
                             " · you 2 acts, 1 min")  # fmt: skip
