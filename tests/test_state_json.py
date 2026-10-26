# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene state --json`: the plan as one JSON snapshot for an editor, schema 1 (the night's brief), built
from the cockpit's own reader. Its keys and types on an empty plan, with proposals and questions, while a
scripted run holds a leaf, after a forked run, with the envelope and a round's row; read-only and whole while
another process writes the store; fast on a 40-task plan; answering anyone, an agent's shell included; and
one JSON line of error, exit 1, where there is no Graphene to read."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

import pytest
from test_forks_run import FORKED, go, seed
from test_run_live import SLOW, executor, graphene_run, leaf, repo, states, wait_for  # noqa: F401
from typer.testing import CliRunner

from graphene_map import auto, board, plan
from graphene_map import state as ST
from graphene_map.cli import build
from graphene_map.plan import RUNNING, Caller
from graphene_map.store import Store

runner = CliRunner()
ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")
AGENT_ENV = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "5e55105e-0000-4000-8000-000000000001"}
TOP = {
    "schema": int, "graphene": str, "repo": str, "cursor": int, "goal": str, "first": str, "planner": str,
    "executor": str, "envelope": dict, "auto": (dict, type(None)), "run": dict, "spent": float,
    "scoreboard": dict, "width": int, "questions": list, "goals": list, "tasks": list, "edges": list,
    "news": list,
}  # fmt: skip
TASK = {
    "id": str, "title": str, "full": str, "state": str, "parent": (str, type(None)), "scope": list,
    "needs": list, "check": str, "agent": str, "model": str, "usd": (int, float),
    "idle": (int, float, type(None)), "needs_you": bool, "tail": list, "note": str, "offers": dict,
    "changed": list, "stopped": list, "outside": list, "forks": list, "kept": (dict, type(None)),
    "hollow": bool,
}  # fmt: skip
FORK = {"letter": str, "state": str, "why": str, "lines": (int, type(None)), "model": str,
        "usd": (int, float)}  # fmt: skip
ENVELOPE = {"auto": str, "budget": (float, type(None)), "tasks": (int, type(None)), "rounds": int,
            "forks": int, "review": str, "protected": list, "readonly": list}  # fmt: skip
WORDS = {"running", "review", "came back", "ready", "waiting", "proposed", "done", "yours"}


def state(*args, env=None):
    return runner.invoke(build(), ["state", *args], env=env or {"GRAPHENE_AS": "person:alex"})


def snapshot(*args, env=None) -> dict:
    said = state("--json", *args, env=env)
    assert said.exit_code == 0, said.output + said.stderr
    assert said.stdout.count("\n") == 1  # one line, for a client that reads lines
    return json.loads(said.stdout)


def typed(shape: dict, got: dict, what: str) -> None:
    assert set(got) >= set(shape), (what, set(shape) - set(got))  # keys may be added, never lost
    for key, kind in shape.items():
        assert isinstance(got[key], kind), (what, key, got[key])


def whole(s: dict) -> None:
    """Every key the brief names, with its type, down to each fork."""
    typed(TOP, s, "top")
    assert s["schema"] == 1
    typed(ENVELOPE, s["envelope"], "envelope")
    assert set(s["run"]) == {"going", "pid"}
    assert set(s["scoreboard"]) == {"need_you", "running", "proven", "total"}
    for t in s["tasks"]:
        typed(TASK, t, t["id"])
        assert t["state"] in WORDS, t["state"]
        for f in t["forks"]:
            typed(FORK, f, f"{t['id']}.{f['letter']}")
    for q in s["questions"]:
        assert set(q) >= {"id", "text", "default", "options", "about", "kind"}
    for g in s["goals"]:
        assert set(g) >= {"id", "title", "parent", "state", "check"}
    for a, b, kind in s["edges"]:
        assert isinstance(a, str) and isinstance(b, str) and kind


def propose(repo, items, who=ALEX):
    with Store.open(repo) as store:
        plan.propose(store, items, who)


def test_an_empty_plan_in_a_repo_set_up_is_a_snapshot_with_no_tasks(repo):
    with Store.open(repo) as store:
        store.set_meta("plan_first", "on")  # what `graphene init` sets: set up, nothing planned yet
    s = snapshot()
    whole(s)
    assert s["tasks"] == [] and s["goals"] == [] and s["edges"] == [] and s["questions"] == []
    assert s["scoreboard"] == {"need_you": 0, "running": 0, "proven": 0, "total": 0}
    assert s["cursor"] == 0 and s["spent"] == 0.0 and s["width"] == 0 and s["auto"] is None
    assert s["run"] == {"going": False, "pid": None} and s["repo"] == str(repo)
    assert s["envelope"] == {"auto": "off", "budget": None, "tasks": None, "rounds": 2, "forks": 1,
                             "review": "off", "protected": [], "readonly": [], "checks": []}  # fmt: skip


def test_proposals_questions_sub_goals_and_edges_read_as_the_cockpit_reads_them(repo):
    with Store.open(repo) as store:
        plan.set_goal(store, "users come back with their ids", ALEX)
        plan.propose(store, [
            {"id": "api", "title": "the API"},
            {"id": "ids", "title": "users returns ids", "parent": "api", "scope": ["a.txt"], "check": "true"},
            {"id": "docs", "title": "document it", "parent": "api", "scope": ["b.txt"], "check": "true",
             "needs": ["ids"]},
        ], ALEX)  # fmt: skip
        plan.propose(store, [{"id": "notes", "title": "notes", "scope": ["NOTES.md"], "check": "true"}], BOT)
        board.add(store, "question", "tabs or spaces?", BOT, default="spaces", options=[{"text": "tabs"}],
                  about="ids")  # fmt: skip
    s = snapshot()
    whole(s)
    assert s["goal"] == "users come back with their ids"
    by = {t["id"]: t for t in s["tasks"]}
    assert {i: t["state"] for i, t in by.items()} == {"ids": "ready", "docs": "waiting", "notes": "proposed"}
    assert by["ids"]["parent"] == "api" and by["notes"]["parent"] is None
    assert by["docs"]["needs"] == ["ids"] and by["notes"]["needs_you"] and not by["ids"]["needs_you"]
    assert s["goals"] == [{"id": "api", "title": "the API", "parent": None, "state": "open", "check": None}]
    assert s["edges"] == [["ids", "docs", "needs"]]
    assert s["questions"] == [{"id": s["questions"][0]["id"], "text": "tabs or spaces?", "default": "spaces",
                               "options": ["tabs"], "about": "ids", "kind": "question"}]  # fmt: skip
    assert s["scoreboard"] == {"need_you": 2, "running": 0, "proven": 0, "total": 3}  # the question, notes
    assert s["cursor"] >= 5 and s["news"]  # the log's last id; what happened, in the narrator's words


def test_a_leaf_a_scripted_run_holds_reads_as_running_with_the_runs_pid(repo, monkeypatch):
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")
    propose(repo, [leaf("a", "a.txt")])
    run = graphene_run(repo, "--with", executor(repo, SLOW))
    try:
        assert wait_for(lambda: states(repo) == {"a": RUNNING}), run.stdout
        assert wait_for(lambda: (repo / "pid.txt").exists() or (repo / ".graphene" / "worktrees" / "a" /
                                                                 "pid.txt").exists())  # fmt: skip
        s = snapshot()
        whole(s)
        (t,) = s["tasks"]
        assert t["state"] == "running" and t["agent"] == "1" and not t["needs_you"]
        assert t["idle"] is not None and t["idle"] >= 0
        assert t["model"] == "" and t["usd"] == 0.0  # a script: no model, no list price
        assert s["run"] == {"going": True, "pid": run.pid}
        assert s["scoreboard"]["running"] == 1 and s["width"] == 1
    finally:
        os.kill(run.pid, signal.SIGINT)
        run.wait(30)


def test_a_forked_leaf_carries_its_forks_their_verdicts_and_the_one_kept(repo, monkeypatch):
    seed(repo, monkeypatch)
    said: list[str] = []
    from graphene_map import run as R

    go(repo, FORKED, said, forks=R.Forks(3))
    s = snapshot()
    whole(s)
    (t,) = s["tasks"]
    assert t["state"] == "done" and t["hollow"] is False
    assert [f["letter"] for f in t["forks"]] == ["a", "b", "c"]
    assert {f["letter"]: f["state"] for f in t["forks"]} == {"a": "refused", "b": "passed", "c": "passed"}
    assert {(f["model"], f["usd"]) for f in t["forks"]} == {("repo-forks", 0.0)}  # a script, by name
    assert t["kept"]["letter"] == "b" and t["kept"]["why"] and t["kept"]["by"]
    assert t["forks"][1]["lines"] and t["forks"][0]["why"]  # b's size, a's refusal
    assert s["scoreboard"] == {"need_you": 0, "running": 0, "proven": 1, "total": 1}
    from graphene_map import meter as M

    with Store.open(repo) as store:  # the meter's count: 3 at once, or 2 if one ended before the last began
        counted = M.width(store.node_log())["most"]
    assert s["width"] == counted >= 2, (s["width"], counted)
    assert any("kept b" in line for line in s["news"]), s["news"]


def test_the_model_and_the_dollars_come_from_the_meter_when_the_cockpit_says_nothing(repo):
    """Lane race adds `model` and `usd` to the cockpit's Task and Fork; until it lands, and where they say
    nothing, the attempt going now names the model and the usage rows the spend."""
    propose(repo, [leaf("a", "a.txt")])
    sid = "5e55105e-0000-4000-8000-0000000000a2"
    now = datetime.now(UTC)
    with Store.open(repo) as store:
        plan.start(store, "a", Caller("run:nemotron", False, sid), repo)
        at = (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
        store.log_node("a", at, "attempt", "run:nemotron", sid, None, {"attempt": 1, "log": "x.txt"})
        usage = {"attempt": 1, "calls": 1, "prompt_tokens": 100, "completion_tokens": 50, "dollars": 0.004,
                 "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "endpoint": "token factory"}  # fmt: skip
        store.log_node("a", at, "usage", "run:nemotron", sid, None, usage)
        did = {"attempt": 1, "verb": "editing", "target": "a.txt"}
        store.log_node("a", at, "did", "run:nemotron", sid, None, did)
    (t,) = snapshot()["tasks"]
    assert t["state"] == "running" and t["model"] == "Nano" and t["usd"] == 0.004
    assert t["tail"] == ["edit a.txt"]
    assert snapshot()["spent"] == 0.004


def test_the_envelope_and_the_rounds_row_are_read_as_the_contract_says(repo):
    propose(repo, [leaf("a", "a.txt")])
    told = {"round": 1, "rounds": 2, "stage": "running", "spent": 0.42, "budget": 2.0, "check": None,
            "why": ""}  # fmt: skip
    with Store.open(repo) as store:
        store.set_meta("settings:auto", "on")
        store.set_meta("settings:budget", "2.0")
        store.set_meta("settings:tasks", "12")
        store.set_meta("settings:forks", "3")
        store.log_node("*", plan._now(), auto.KIND, "graphene auto", None, None,
                       {**told, "stage": "planning"})  # fmt: skip
        store.log_node("*", plan._now(), auto.KIND, "graphene auto", None, None, told)
    s = snapshot()
    assert s["auto"] == told  # the newest row
    assert s["envelope"]["auto"] == "on" and s["envelope"]["budget"] == 2.0
    assert s["envelope"]["tasks"] == 12 and s["envelope"]["rounds"] == 2 and s["envelope"]["forks"] == 3


WRITER = """
import sys, time
from graphene_map.store import Store
from graphene_map import plan
end = time.monotonic() + float(sys.argv[2])
with Store.open(__import__("pathlib").Path(sys.argv[1])) as store:
    n = 0
    while time.monotonic() < end:
        with store.claim():
            store.log_node("a", plan._now(), "did", "run:x", None, None, {"attempt": 1, "verb": "editing",
                           "target": f"a{n}.txt"})
        n += 1
print(n)
"""


def test_while_another_process_writes_the_store_every_snapshot_is_whole(repo, tmp_path):
    propose(repo, [leaf("a", "a.txt")])
    script = tmp_path / "writer.py"
    script.write_text(WRITER)
    argv = [sys.executable, str(script), str(repo), "4"]
    writer = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
    try:
        time.sleep(0.3)
        seen = []
        for _ in range(8):
            s = snapshot()
            whole(s)
            assert "error" not in s
            seen.append(s["cursor"])
    finally:
        out, _ = writer.communicate(timeout=30)
    assert int(out.strip()) > 0 and seen[-1] >= seen[0]  # it wrote meanwhile; the cursor only grows


def test_a_snapshot_of_a_forty_task_plan_is_fast(repo):
    """Measured when written, on this plan (four running leaves, 2,000 rows): 0.27 s end to end as a command,
    imports included. The bound is loose, for a loaded machine: it fails on a snapshot that reads the plan's
    log once per task."""
    leaves = [leaf(f"t{i}", f"d{i}/x.txt") for i in range(40)]
    now = datetime.now(UTC)
    with Store.open(repo) as store:
        plan.propose(store, leaves, ALEX)
        for i in range(4):
            sid = f"5e55105{i}-0000-4000-8000-0000000000a1"
            plan.start(store, f"t{i}", Caller(f"claude:5e55105{i}", False, sid), repo)
            for k in range(500):
                at = (now - timedelta(seconds=(500 - k) * 0.05)).isoformat().replace("+00:00", "Z")
                detail = {"attempt": 1, "tool": "Edit", "target": f"d{i}/f{k % 40}.py", "verb": "editing"}
                store.log_node(f"t{i}", at, "did", "run:claude", sid, None, detail)
    times = []
    for _ in range(5):
        start = time.perf_counter()
        with Store.open(repo) as store:
            s = ST.snapshot(store, repo)
        times.append(time.perf_counter() - start)
    assert len(s["tasks"]) == 40 and s["scoreboard"]["running"] == 4
    assert sorted(times)[2] < 1.0, times


def test_reading_needs_no_mark_so_an_agents_shell_gets_the_snapshot_too(repo):
    propose(repo, [leaf("a", "a.txt")])
    s = snapshot(env=AGENT_ENV)
    assert [t["id"] for t in s["tasks"]] == ["a"]
    marks = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX", "AI_AGENT",
             "GRAPHENE_NODE", "GRAPHENE_PLANNER", "GEMINI_CLI", "CURSOR_AGENT")  # fmt: skip
    assert ST.MARKS == marks
    for mark in ST.MARKS:  # each alone makes an agent; an editor that drops them all spawns the person
        assert not plan.caller({mark: "1", "USER": "alex"}, tty=False).person, mark
    assert plan.caller({"USER": "alex"}, tty=False).person


def test_without_the_flag_the_json_is_indented_for_a_person(repo):
    propose(repo, [leaf("a", "a.txt")])
    said = state()
    assert said.exit_code == 0 and said.stdout.startswith('{\n  "schema": 1,')
    assert json.loads(said.stdout)["tasks"][0]["id"] == "a"


def test_where_there_is_no_graphene_to_read_one_json_line_says_why_and_exits_1(repo, tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    said = state("--json")
    got = json.loads(said.stdout)
    assert said.exit_code == 1 and set(got) == {"schema", "error"} and got["schema"] == 1
    assert "not a git repository" in got["error"]
    monkeypatch.chdir(repo)
    said = state("--json")  # a repository nothing ran graphene in
    assert said.exit_code == 1 and "no Graphene store" in json.loads(said.stdout)["error"]
    assert not (repo / ".graphene").exists()  # and asking made none: read-only
    with Store.open(repo):
        pass  # a store any command makes, with nothing set up or planned in it
    said = state("--json")
    assert said.exit_code == 1 and json.loads(said.stdout)["error"].startswith("nothing is set up or planned")
    propose(repo, [leaf("a", "a.txt")])  # planned without `graphene init`: a plan all the same
    assert snapshot()["tasks"][0]["id"] == "a"


def test_state_is_hidden_from_help_and_its_help_answers(repo):
    assert "state" not in runner.invoke(build(), ["--help"]).output
    assert runner.invoke(build(), ["state", "--help"]).exit_code == 0


def test_a_snapshot_writes_nothing_to_the_store(repo):
    propose(repo, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])])

    def contents():
        with Store.open(repo) as store:
            meta = store.conn.execute("SELECT key, value FROM plan_meta ORDER BY key").fetchall()
            return [tuple(r) for r in meta], store.node_log(), store.node_rows()

    before = contents()
    assert snapshot()["cursor"] == before[1][-1]["id"] and snapshot()["tasks"]
    assert contents() == before  # two snapshots later: not a row, a node or a setting changed


def test_a_store_that_does_not_open_is_one_json_line_too_with_the_reason_on_stderr(repo):
    propose(repo, [leaf("a", "a.txt")])
    db = repo / ".graphene" / "graphene.db"
    db.chmod(0)
    try:
        said = state("--json")
    finally:
        db.chmod(0o600)
    got = json.loads(said.stdout)
    assert said.exit_code == 1 and got["schema"] == 1 and got["error"].startswith("the store did not open")
    assert "cannot open" in said.stderr  # the opener's own line, as every command says it


def test_whatever_goes_wrong_reading_stdout_still_holds_one_json_object(repo, monkeypatch):
    propose(repo, [leaf("a", "a.txt")])

    def broken(store, root, now=None):
        raise RuntimeError("a row the reader cannot read")

    monkeypatch.setattr(ST, "snapshot", broken)
    said = state("--json")
    why = "the plan could not be read (RuntimeError: a row the reader cannot read)"
    assert said.exit_code == 1 and json.loads(said.stdout) == {"schema": 1, "error": why}


@pytest.mark.parametrize("given", ["Nano", "nvidia/NVIDIA-Nemotron-3-Super-49B", "claude-sonnet-5-5",
                                   "gpt-5-codex", "org/some-model"])  # fmt: skip
def test_a_models_short_name_is_the_familys_word_or_the_ids_last_part(given):
    """What the race lane's `meter.short` will say too; until it lands, this is the rule, and it holds on a
    name already short."""
    expect = {"Nano": "Nano", "nvidia/NVIDIA-Nemotron-3-Super-49B": "Super", "claude-sonnet-5-5": "Sonnet",
              "gpt-5-codex": "Codex", "org/some-model": "some-model"}  # fmt: skip
    assert ST.short(given) == expect[given] and ST.short(None) == "" and ST.short("") == ""
