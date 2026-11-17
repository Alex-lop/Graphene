# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene state --json`: the plan as one JSON snapshot for an editor, schema 1 (the night's brief), built
from the cockpit's own reader. Its keys and types on an empty plan, with proposals and questions, while a
scripted run holds a leaf, after a forked run, with the envelope and a round's row; read-only and whole while
another process writes the store; fast on a 40-task plan; answering anyone, an agent's shell included; and
one JSON line of error, exit 1, where there is no Graphene to read.

The Scope pane's keys (leaf 5), each by its value on real state: `tree` and `allows`, and on a task `files`
and `files_n`, `touched`, `stops`, `checked`, `tokens` and `held`, which never says more than
tests/test_every_agent.py proves."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

import pytest
from test_every_agent import hook
from test_forks_run import FORKED, go, seed
from test_meter import fed
from test_run_live import SLOW, executor, git, graphene_run, leaf, repo, states, wait_for  # noqa: F401
from typer.testing import CliRunner

from graphene_map import auto, board, plan, precheck
from graphene_map import meter as M
from graphene_map import state as ST
from graphene_map.cli import build
from graphene_map.hooks import HOOK_COMMAND, SETTINGS, install_codex_hooks, install_hooks
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
    "news": list, "tree": list, "allows": (list, type(None)),
}  # fmt: skip
TASK = {
    "id": str, "title": str, "full": str, "state": str, "parent": (str, type(None)), "scope": list,
    "needs": list, "check": str, "agent": str, "model": str, "usd": (int, float),
    "idle": (int, float, type(None)), "needs_you": bool, "tail": list, "note": str, "offers": dict,
    "changed": list, "stopped": list, "outside": list, "forks": list, "kept": (dict, type(None)),
    "hollow": bool, "files": list, "files_n": int, "touched": list, "stops": list, "checked": dict,
    "tokens": (dict, type(None)), "held": dict, "command": (str, type(None)), "leaves": bool,
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
        assert set(t["checked"]) == {"before", "after"} and set(t["held"]) == {"state", "by"}
        assert t["held"]["state"] in ("refused", "caught", "none") and len(t["files"]) <= t["files_n"]
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


def test_a_check_that_already_passes_is_hollow_before_the_work_and_one_that_fails_now_is_not(repo):
    """Before Run each step's check runs once on the code as it is (red first, precheck.py). A check that
    passes there proves nothing yet, and the snapshot says so on the task while it waits, so its card can be
    marked before any agent starts; an edit to the check takes the mark away until it is run again."""
    from graphene_map import precheck

    fails = "python3 -c 'import sys; sys.exit(1)'"
    hollow = lambda: {t["id"]: t["hollow"] for t in snapshot()["tasks"]}  # noqa: E731
    propose(repo, [{"id": "soft", "title": "soft", "scope": ["a.py"], "check": "true"},
                   {"id": "hard", "title": "hard", "scope": ["b.py"], "check": fails}])  # fmt: skip
    assert hollow() == {"soft": False, "hard": False}  # not run yet
    with Store.open(repo) as store:
        precheck.run(store, repo)
    assert hollow() == {"soft": True, "hard": False}
    with Store.open(repo) as store:
        plan.edit(store, "soft", {"check": fails}, ALEX)
    assert hollow() == {"soft": False, "hard": False}


def test_a_command_step_says_its_command_and_whether_it_leaves_this_machine(repo):
    """A workflow's `run:` step has no agent and no scope. The snapshot says the command it runs and whether
    that command leaves this machine (a push, a pull request), where the graph draws it past the line and
    it waits for the person; a step an agent does says neither. A command proves no work, so red first's
    verdict on it is never a hollow check."""
    from graphene_map import precheck

    propose(repo, [{"id": "fix", "title": "fix", "scope": ["a.py"], "check": "true"},
                   {"id": "suite", "title": "suite", "check": "true", "owner": "command", "needs": ["fix"]},
                   {"id": "pr", "title": "pr", "check": "git push origin main", "owner": "command",
                    "needs": ["suite"]}])  # fmt: skip
    by = {t["id"]: t for t in snapshot()["tasks"]}
    assert [(by[i]["command"], by[i]["leaves"]) for i in ("fix", "suite", "pr")] == [
        (None, False), ("true", False), ("git push origin main", True)]  # fmt: skip
    with Store.open(repo) as store:
        precheck.run(store, repo)
    by = {t["id"]: t for t in snapshot()["tasks"]}
    assert (by["fix"]["hollow"], by["suite"]["hollow"], by["pr"]["hollow"]) == (True, False, False)


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


def tasks() -> dict:
    return {t["id"]: t for t in snapshot()["tasks"]}


def track(repo, *paths):
    for path in paths:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "more")


def test_files_are_the_tracked_files_a_scope_covers_as_the_gate_matches_a_write(repo):
    """A glob, a `!` that takes paths back out, a file the step will make, and a file on disk git does not
    track yet; `tree` is the top level, folders first. A path a standing setting keeps out of every scope is
    not one the step may change, whatever its glob says (`plan.binds`)."""
    track(repo, "src/export/csv.py", "src/export/rows.py", "src/export/notes.md", "src/db/x.py", "src/app.py",
          "docs/a.md")  # fmt: skip
    (repo / "src" / "export" / "draft.py").write_text("not added yet\n")
    propose(repo, [
        {"id": "glob", "title": "glob", "scope": ["src/export/*.py"], "check": "true"},
        {"id": "but", "title": "but", "scope": ["src/**", "!src/export/**", "!src/db/**"], "check": "true"},
        {"id": "new", "title": "new", "scope": ["lib/made/later.py"], "check": "true"},
        {"id": "two", "title": "two", "scope": ["docs", "b.txt"], "check": "true"},
    ])  # fmt: skip
    s = snapshot()
    whole(s)
    got = {t["id"]: (t["files"], t["files_n"]) for t in s["tasks"]}
    assert got == {"glob": (["src/export/csv.py", "src/export/rows.py"], 2), "but": (["src/app.py"], 1),
                   "new": ([], 0), "two": (["b.txt", "docs/a.md"], 2)}  # fmt: skip
    assert s["tree"] == ["docs/", "src/", "a.txt", "b.txt"]
    with Store.open(repo) as store:  # set after the scope was accepted: it binds all the same
        store.set_meta("settings:protected", json.dumps(["src/export/rows.py"]))
    assert tasks()["glob"]["files"] == ["src/export/csv.py"] and tasks()["glob"]["files_n"] == 1
    assert ST.tree([]) == []  # nothing tracked, and a replay, whose repository is not on disk


def test_at_most_200_paths_are_listed_and_files_n_counts_them_all(repo):
    names = [f"f{i:03}.txt" for i in range(205)]
    track(repo, *names)
    track(repo, *(f"pkg{i}/x.py" for i in range(3)))
    propose(repo, [{"id": "all", "title": "all", "scope": ["f*.txt"], "check": "true"}])
    s = snapshot()
    (t,) = s["tasks"]
    assert t["files"] == names[:200] and t["files_n"] == 205
    assert s["tree"] == ["pkg0/", "pkg1/", "pkg2/", "a.txt", "b.txt", *names][:200] and len(s["tree"]) == 200


WRITES = """
import pathlib, time
pathlib.Path("a.txt").write_text("changed\\n")
time.sleep(60)
"""


def test_touched_is_what_the_attempt_going_now_has_written_while_a_scripted_run_holds_the_leaf(
    repo, monkeypatch
):
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")
    propose(repo, [leaf("a", "a.txt"), leaf("b", "b.txt", needs=["a"])])
    assert {i: t["touched"] for i, t in tasks().items()} == {"a": [], "b": []}  # nothing runs yet
    run = graphene_run(repo, "--with", executor(repo, WRITES))
    try:
        assert wait_for(lambda: states(repo)["a"] == RUNNING), run.stdout
        assert wait_for(lambda: tasks()["a"]["touched"] == ["a.txt"]), tasks()["a"]
        by = tasks()
        assert by["a"]["state"] == "running" and by["a"]["files"] == ["a.txt"] and by["b"]["touched"] == []
        assert by["a"]["held"] == {"state": "caught", "by": "executor.py"}  # a command of your own, by name
        assert by["a"]["tokens"] is None  # and it has no meter
    finally:
        os.kill(run.pid, signal.SIGINT)
        run.wait(30)
    assert tasks()["a"]["touched"] == []  # handed back: no attempt is going
    with Store.open(repo) as store:  # a session takes it, writes, and hands it back with its change there
        plan.start(store, "a", BOT, repo)
        (repo / "a.txt").write_text("changed again\n")
        assert ST.snapshot(store, repo)["tasks"][0]["touched"] == ["a.txt"]
        plan.release(store, "a", BOT, "it needs b.txt too")
    back = tasks()["a"]
    assert back["state"] == "came back" and back["touched"] == []  # `touched` is the attempt going now


def test_stops_are_every_write_of_the_task_that_was_refused_with_the_time_and_how(repo):
    """The whole history, oldest first, from the log's `denied` rows that carry a path: a write tool's, then
    a shell command's. `stopped` stays the attempt going now, as paths."""
    propose(repo, [leaf("a", "a.txt"), leaf("b", "b.txt")])
    sid = BOT.session_id
    with Store.open(repo) as store:
        plan.start(store, "a", BOT, repo)
    assert tasks()["a"]["stops"] == []
    began = plan._now()
    tries = (("Write", {"file_path": str(repo / "a.txt")}, None),  # its own file: let through, no row
             ("Write", {"file_path": str(repo / "README.md")}, "deny"),
             ("Bash", {"command": "echo x > b.txt"}, "deny"))  # fmt: skip
    for tool, given, expect in tries:
        answer = hook(repo, "PreToolUse", sid, tool_name=tool, tool_input=given)
        assert (answer and answer["hookSpecificOutput"]["permissionDecision"]) == expect
    with Store.open(repo) as store:
        at = [r["timestamp"] for r in store.node_log("a", ("denied",))]  # the time, as the log stores it
    by = tasks()
    assert by["a"]["stops"] == [{"path": "README.md", "at": at[0], "how": "Write"},
                                {"path": "b.txt", "at": at[1], "how": "shell"}]  # fmt: skip
    assert began <= at[0] <= at[1] <= plan._now() and by["b"]["stops"] == []
    assert by["a"]["stopped"] == ["README.md", "b.txt"]  # as it was
    with Store.open(repo) as store:  # handed back and taken again: a new attempt, the same history
        plan.release(store, "a", BOT, "it needs the README")
        plan.start(store, "a", BOT, repo)
    again = tasks()["a"]
    assert again["stopped"] == [] and again["stops"] == by["a"]["stops"]


def test_checked_is_the_checks_verdict_before_the_work_and_after_while_it_is_about_the_check_it_has_now(repo):
    fails = "python3 -c 'import sys; sys.exit(1)'"
    checked = lambda: {i: t["checked"] for i, t in tasks().items()}  # noqa: E731
    nothing = {"before": None, "after": None}
    propose(repo, [{"id": "red", "title": "red", "scope": ["a.txt"], "check": "grep -q done a.txt"},
                   {"id": "soft", "title": "soft", "scope": ["b.txt"], "check": "true"},
                   {"id": "bare", "title": "bare", "scope": ["c.txt"], "signoff": True}])  # fmt: skip
    assert checked() == {"red": nothing, "soft": nothing, "bare": nothing}  # not run yet
    with Store.open(repo) as store:
        precheck.run(store, repo)
    assert checked() == {"red": {"before": "red", "after": None}, "soft": {"before": "passes", "after": None},
                         "bare": nothing}  # fmt: skip
    with Store.open(repo) as store:
        plan.start(store, "red", BOT, repo)
        (repo / "a.txt").write_text("not yet\n")
        with pytest.raises(plan.Refused):
            plan.finish(store, "red", BOT)
    assert checked()["red"] == {"before": "red", "after": "failed"}
    with Store.open(repo) as store:
        (repo / "a.txt").write_text("done\n")
        plan.finish(store, "red", BOT)
    assert checked()["red"] == {"before": "red", "after": "passed"}
    with Store.open(repo) as store:  # an edited check has not been run, before or after
        plan.edit(store, "soft", {"check": fails}, ALEX)
        plan.reopen(store, "red", ALEX, "the check should ask for more")
        plan.edit(store, "red", {"check": "grep -q finished a.txt"}, ALEX)
    assert checked() == {"red": nothing, "soft": nothing, "bare": nothing}


def metered(store, node_id, attempt, kind, name, **given):
    """A recorded stream's rows on the task, as `graphene run` logs what its meter reads; the meter."""
    meter = M.Meter(kind, attempt, **given)
    sid = f"5e55105e-0000-4000-8000-00000000000{attempt}"
    store.log_node(
        node_id, plan._now(), "attempt", f"run:{kind}", sid, None, {"attempt": attempt, "log": "x"}
    )
    for row, detail in fed(name, meter):
        store.log_node(node_id, plan._now(), row, f"run:{kind}", sid, None, detail)
    return meter


def test_tokens_are_summed_over_the_tasks_attempts_from_the_meters_rows_and_null_with_no_meter(repo):
    """Claude Code's recorded stream (tests/fixtures/meter): three turns, 6 + 11,782 + 48,637 tokens in, of
    which 48,637 came from the cache, and 539 out. Codex's: one turn, 48,940 in and 344 out, and no cache
    split, so a task only Codex worked on reads null there, and one both worked on keeps Claude's."""
    propose(repo, [leaf("a", "a.txt"), leaf("b", "b.txt"), leaf("c", "c.txt")])
    with Store.open(repo) as store:
        plan.start(store, "a", Caller("run:claude", False, "5e55105e-0000-4000-8000-000000000001"), repo)
        metered(store, "a", 1, "claude", "claude.jsonl")
    by = tasks()
    assert by["a"]["tokens"] == {"read": 60425, "cached": 48637, "written": 539, "turns": 3}
    assert by["b"]["tokens"] is None and by["c"]["tokens"] is None  # not started
    with Store.open(repo) as store:
        codex = metered(store, "a", 2, "codex", "codex.jsonl", model="m")
        plan.start(store, "b", Caller("run:codex", False, "5e55105e-0000-4000-8000-000000000002"), repo)
        metered(store, "b", 2, "codex", "codex.jsonl", model="m")
    assert (codex.prompt_tokens, codex.completion_tokens, codex.turns) == (48940, 344, 1)
    by = tasks()
    assert by["a"]["tokens"] == {"read": 60425 + 48940, "cached": 48637, "written": 539 + 344, "turns": 4}
    assert by["b"]["tokens"] == {"read": 48940, "cached": None, "written": 344, "turns": 1}


def choose(repo, executor):
    with Store.open(repo) as store:
        store.set_meta("executor", executor)


def test_held_says_what_test_every_agent_proves_and_nothing_more(repo):
    """Refused before the write: Claude Code, in a repository with Graphene's gate among its hooks, and no
    one else. Caught when it finishes: Claude Code without them, Codex (whose hooks may be installed: whether
    they are trusted is not in the store), a command of your own, and nobody chosen. Not held: a task that is
    yours."""
    propose(repo, [leaf("a", "a.txt"), leaf("mine", "b.txt", owner="alex")])
    held = lambda: {i: t["held"] for i, t in tasks().items()}  # noqa: E731
    yours = {"state": "none", "by": "you"}
    assert held() == {"a": {"state": "caught", "by": ""}, "mine": yours}  # no executor chosen, no hooks
    choose(repo, "claude")
    assert held() == {"a": {"state": "caught", "by": "claude"}, "mine": yours}  # Claude Code, no hooks
    (repo / ".claude").mkdir()
    only_stop = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": HOOK_COMMAND}]}]}}
    (repo / SETTINGS).write_text(json.dumps(only_stop))
    assert held()["a"] == {"state": "caught", "by": "claude"}  # our command, but not where a write is asked
    install_hooks(repo)
    install_codex_hooks(repo)
    assert held() == {"a": {"state": "refused", "by": "claude"}, "mine": yours}
    choose(repo, "claude:opus")
    assert held()["a"] == {"state": "refused", "by": snapshot()["executor"]}  # as `executor` says it
    for own in ("codex", "codex:gpt-5-codex", f"{sys.executable} /opt/agents/mine.py", "aider --yes"):
        choose(repo, own)
        s = snapshot()
        assert {t["id"]: t["held"] for t in s["tasks"]} == {"a": {"state": "caught", "by": s["executor"]},
                                                            "mine": yours}, own  # fmt: skip


def test_held_follows_who_holds_a_running_task_not_the_executor_chosen_for_the_repository(repo):
    """`graphene run --with codex` in a repository set up for Claude Code is Codex's, and a Claude Code
    session that took a task in one set up for Codex is held by its hooks, as rows 1 to 3 of
    test_every_agent are."""
    propose(repo, [leaf("a", "a.txt"), leaf("b", "b.txt")])
    install_hooks(repo)
    choose(repo, "claude")
    with Store.open(repo) as store:
        plan.start(store, "a", Caller("run:codex", False, "5e55105e-0000-4000-8000-000000000003"), repo)
    by = tasks()
    assert by["a"]["held"] == {"state": "caught", "by": "codex"}
    assert by["b"]["held"] == {"state": "refused", "by": "claude"}
    choose(repo, "codex")
    with Store.open(repo) as store:
        plan.start(store, "b", BOT, repo)  # claude:5e55105e, a session its hooks hold
    by = tasks()
    assert by["b"]["held"] == {"state": "refused", "by": "claude"}
    assert by["a"]["held"] == {"state": "caught", "by": "codex"}
    (repo / SETTINGS).unlink()
    assert tasks()["b"]["held"] == {"state": "caught", "by": "claude"}  # the hooks taken out


def test_held_is_the_weakest_fork_and_never_a_shield_for_a_holder_no_run_started(repo):
    """A step forked across executors is held as its weakest fork is: Claude Code racing Codex is caught,
    not refused (`run --forks 2 --with claude --with codex`). And a task held by something no run started
    and no proven session is (an editor's own agent, which the plan names "an agent"; a person who took an
    agent's task) is not held: nobody has tested those."""
    propose(repo, [leaf("a", "a.txt"), leaf("b", "b.txt"), leaf("c", "c.txt")])
    install_hooks(repo)
    choose(repo, "claude")
    run = Caller("run:claude", False, "5e55105e-0000-4000-8000-000000000004")
    forks = {"s-a": {"fork": "a", "tree": str(repo)}, "s-b": {"fork": "b", "tree": str(repo)}}
    with Store.open(repo) as store:
        plan.start(store, "a", run, repo)
        plan.set_forked(store, "a", forks)
        row = {"forks": ["a", "b"], "of": 2, "with": {"a": "claude", "b": "codex"}}
        store.log_node("a", plan._now(), "forked", run.label, run.session_id, None, row)
    assert tasks()["a"]["held"] == {"state": "caught", "by": "claude"}
    with Store.open(repo) as store:  # the same hold forked again, every fork Claude Code's
        row = {"forks": ["a", "b"], "of": 2, "with": {"a": "claude", "b": "claude:opus"}}
        store.log_node("a", plan._now(), "forked", run.label, run.session_id, None, row)
    assert tasks()["a"]["held"] == {"state": "refused", "by": "claude"}
    with Store.open(repo) as store:
        plan.start(store, "b", Caller("an agent", False, None), repo)
        plan.start(store, "c", Caller("alex", True, None), repo)
    by = tasks()
    assert by["b"]["held"] == {"state": "none", "by": "an agent"}
    assert by["c"]["held"] == {"state": "none", "by": "alex"}


def test_allows_is_what_the_executors_own_command_line_lets_it_run_without_asking(repo):
    """Claude Code as Graphene starts it names two; Codex, the Nemotron executor and a command of your own
    name no list: any command, held to the step's files by what it writes. A list of what is NOT allowed, or
    a command line that switches the asking off, is no such list either."""
    propose(repo, [leaf("a", "a.txt")])
    assert snapshot()["allows"] is None  # nobody chosen
    two = ["graphene node *", "graphene plan *"]
    said = {"claude": two, "claude:opus": two, "claude --max-budget-usd 5": two, "codex": None,
            "nemotron --model nano": None, f"{sys.executable} /opt/agents/mine.py": None,
            "claude -p --allowedTools 'Bash(git diff)' Edit 'Bash(npm *)' --verbose": ["git diff", "npm *"],
            "claude -p --allowed-tools='Bash(make *),Read'": ["make *"],
            "claude -p --disallowedTools 'Bash(rm *)'": None,
            "claude -p --dangerously-skip-permissions --allowedTools 'Bash(graphene node *)'": None,
            "claude -p --permission-mode bypassPermissions --allowedTools 'Bash(graphene node *)'": None,
            "mine --allowedTools 'Bash(graphene node *)'": None,
            "claude-shim --allowedTools 'Bash(graphene node *)'": None}  # fmt: skip
    for executor_, allowed in said.items():
        choose(repo, executor_)
        assert snapshot()["allows"] == allowed, executor_
