# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""A leaf run as forks: N agents at once, a worktree each, cut from the same commit; each judged by the
leaf's check in its own copy; one kept by the rule in pick.py and landed as any leaf lands; the rest on
record, each on its own ref. The executor is a script that behaves by its GRAPHENE_FORK: a fails the
check, b passes with a small change, c with a larger one; AGREE's forks write tests, and b's are the
stricter."""

import json
import signal
import subprocess
import sys

import pytest
from test_run_live import SLOW, graphene_run, repo, states, wait_for  # noqa: F401
from typer.testing import CliRunner

from graphene_map import plan
from graphene_map import run as R
from graphene_map.cli import build
from graphene_map.plan import DONE, OPEN, REVIEW, Caller, Refused
from graphene_map.store import Store

ALEX = Caller("alex", True)


def person(*args):
    return CliRunner().invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"})
FORKED = """
import json, os, pathlib, sys, time
fork, of = os.environ["GRAPHENE_FORK"], os.environ["GRAPHENE_FORKS"]
told = f"This is fork {fork} of {of}: {of} agents work on this leaf at once" in sys.argv[-1]
with open(os.environ["FORKS_LOG"], "a") as log:
    log.write(json.dumps({"fork": fork, "of": of, "attempt": os.environ["GRAPHENE_ATTEMPT"],
                          "try": os.environ["GRAPHENE_TRY"], "cwd": os.getcwd(), "told": told,
                          "node": os.environ["GRAPHENE_NODE"]}) + "\\n")
if os.environ.get("FORKS_SLOW") and fork in os.environ["FORKS_SLOW"]:
    time.sleep(30)
LARGE = "import os\\n\\n\\ndef users():\\n    found = ids\\n    return found\\n\\n\\ndef more():\\n"
body = {"a": "def users():\\n    return [0]\\n", "b": "def users():\\n    return ids\\n",
        "c": LARGE + "    return 1\\n"}[fork]
pathlib.Path("api.py").write_text(body)
if fork == "c":
    pathlib.Path("notes.txt").unlink()  # a deletion inside the scope lands too
if fork == "c" and os.environ.get("FORKS_RELEASE"):  # c gives up, naming what it needs
    import subprocess
    cli = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
    argv = [sys.executable, "-c", cli, "node", "release", os.environ["GRAPHENE_NODE"],
            "--why", "needs schema", "--wants", "schema.py"]
    print(subprocess.run(argv, capture_output=True, text=True).stdout)
"""
NONE = FORKED.replace("return ids", "return [1]").replace("found = ids", "found = [1]")
# every fork passes; a and b add a test the check runs: b's, the stricter, fails on a's code and c's
AGREE = """
import os, pathlib
fork = os.environ["GRAPHENE_FORK"]
api = {"a": "def users():\\n    return [1]\\n", "c": "def users():\\n    return [1]\\n",
       "b": 'def users():\\n    \"\"\"The ids.\"\"\"\\n    return [1]\\n'}[fork]
pathlib.Path("api.py").write_text(api)
test = {"a": "assert users() == [1]\\n", "b": "assert users() == [1]\\nassert users.__doc__\\n"}.get(fork)
if test:
    t = pathlib.Path("tests/test_api.py")
    t.write_text(t.read_text() + test)
"""
TEST = ("import os, sys\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        "from api import users\nassert isinstance(users(), list)\n")
CLI = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
# b's own `done` passes, then b writes again and breaks it (it is told to call done as often as it needs);
# c passes with the larger change; a fails
STALE = f"""
import os, pathlib, subprocess, sys
fork = os.environ["GRAPHENE_FORK"]
LARGE = ("import os\\n\\n\\ndef users():\\n    found = ids\\n    return found\\n\\n\\n"
         "def more():\\n    return 1\\n")
body = {{"a": "def users():\\n    return [0]\\n", "b": "def users():\\n    return ids\\n", "c": LARGE}}
pathlib.Path("api.py").write_text(body[fork])
if fork == "b":
    out = subprocess.run([sys.executable, "-c", {CLI!r}, "node", "done", os.environ["GRAPHENE_NODE"]],
                         capture_output=True, text=True)
    assert out.stdout.startswith("the check passed in this fork (fork b of 3)"), out.stdout + out.stderr
    pathlib.Path("api.py").write_text("def users():\\n    return [0]\\n")  # broken again, after its done
"""


def executor(repo, source: str) -> str:
    script = repo.parent / f"{repo.name}-forks.py"  # beside the repo, so it is nobody's stray file
    script.write_text(source)
    return f"{sys.executable} {script}"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def users_leaf(**extra):
    return {"id": "n1", "title": "users returns ids", "scope": ["api.py", "notes.txt"],
            "check": "grep -q ids api.py", **extra}  # fmt: skip


def rows(store, kind):
    return [e for e in store.node_log("n1", (kind,))]


def go(repo, source, said, **kw):
    command = executor(repo, source)
    return R.run_parallel(lambda: Store.open(repo), repo, repo, 1, command, attempts=kw.pop("attempts", 1),
                          say=said.append, logs=repo / ".graphene" / "runs", **kw)  # fmt: skip


def seed(repo, monkeypatch, **extra) -> str:
    """api.py and notes.txt committed, the leaf proposed; the base commit."""
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "notes.txt").write_text("to go\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf(**extra)], ALEX)
    return git(repo, "rev-parse", "HEAD").strip()


def last_rows(store) -> dict[str, dict]:
    """Each fork's last `fork` row: how it ended."""
    return {e["detail"]["fork"]: e["detail"] for e in rows(store, "fork")}


def test_three_forks_run_at_once_one_is_kept_and_lands_as_one_merge(repo, monkeypatch):
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "notes.txt").write_text("to go\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    base = git(repo, "rev-parse", "HEAD").strip()
    said: list[str] = []
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf()], ALEX)
    done = go(repo, FORKED, said, forks=R.Forks(3))
    assert [n.id for n in done] == ["n1"] and states(repo) == {"n1": DONE}, said
    ran = [json.loads(line) for line in (repo.parent / "forks.log").read_text().splitlines()]
    assert sorted(r["fork"] for r in ran) == ["a", "b", "c"]
    assert all(r["of"] == "3" and r["told"] and r["node"] == "n1" for r in ran)
    assert len({r["attempt"] for r in ran}) == 3 and all(r["try"] == "1" for r in ran)  # a session a fork
    assert {r["cwd"].rsplit("/", 1)[-1] for r in ran} == {"n1.a", "n1.b", "n1.c"}  # a worktree a fork
    with Store.open(repo) as store:
        [forked] = rows(store, "forked")
        assert forked["detail"]["forks"] == ["a", "b", "c"] and forked["detail"]["of"] == 3
        assert forked["detail"]["first"] is False and len(forked["detail"]["sessions"]) == 3
        assert set(forked["detail"]["with"].values()) == {f"{repo.name}-forks.py"}
        attempts = rows(store, "attempt")
        sessions = forked["detail"]["sessions"]
        assert sorted(e["detail"]["fork"] for e in attempts) == ["a", "b", "c"]
        assert all(e["detail"]["of"] == 3 for e in attempts)
        assert all(e["session_id"] == sessions[e["detail"]["fork"]] for e in attempts)
        assert sorted(e["detail"]["fork"] for e in rows(store, "ended")) == ["a", "b", "c"]
        last = {}
        for e in rows(store, "fork"):
            last[e["detail"]["fork"]] = e["detail"]
        assert {b: f["state"] for b, f in last.items()} == {"a": "refused", "b": "passed", "c": "passed"}
        refused = "1 attempt, the last one refused: n1 is not done: `grep -q ids api.py` failed"
        assert last["a"]["why"].startswith(refused)
        assert last["b"]["paths"] == ["api.py"] and last["b"]["lines"] == 2  # one line changed
        assert last["c"]["paths"] == ["api.py", "notes.txt"] and last["c"]["lines"] > last["b"]["lines"]
        assert all(f["of"] == 3 and f["attempts"] == 1 and f["seconds"] >= 0 for f in last.values())
        assert all(f["test_lines"] == 0 and f["dollars"] is None for f in last.values())  # no meter
        assert all(f["ref"] == f"refs/graphene/forks/n1/{b}" for b, f in last.items())
        assert len(rows(store, "check_passed")) == 1  # the leaf's proof: the hold's own finish, once
        [picked] = rows(store, "picked")
        reason = f"2 lines against {last['c']['lines']}"  # b and c passed; the smaller is kept
        assert picked["detail"] | {"table": None} == {"fork": "b", "of": 3, "by": "graphene",
                                                      "reason": reason, "table": None}  # fmt: skip
        table = picked["detail"]["table"]
        assert [(t["fork"], t["state"], t["passed"]) for t in table] == [("a", "refused", False),
                                                                          ("b", "passed", True),
                                                                          ("c", "passed", True)]  # fmt: skip
        assert all(t["agrees"] == [] and t["test_lines"] == 0 for t in table)
        # the check runs api.py itself, which both passing forks changed: a tie there, and the size decides
        assert {t["fork"]: t["touched_check"] for t in table} == {"a": False, "b": True, "c": True}
        assert [t["lines"] for t in table] == [last[b]["lines"] for b in "abc"]
        assert all(t["dollars"] is None and t["seconds"] == last[t["fork"]]["seconds"] for t in table)
        assert table[0]["why"].startswith(refused) and "why" not in table[1]
        assert plan.get(store, "n1").forked == {}  # cleared with the hold
        assert [e["kind"] for e in store.node_log("n1")][-3:] == ["check_passed", "finished", "landed"]
    assert f"n1 forked 3 ways: a {repo.name}-forks.py, b {repo.name}-forks.py, c {repo.name}-forks.py" in said
    assert f"n1 fork b: the check passed · {last['b']['lines']} lines" in said
    assert "n1 fork a: attempt 1 refused: n1 is not done: `grep -q ids api.py` failed" in said
    assert "n1 fork a: 1 attempt, the last one refused" in said
    assert f"n1 kept b of 3: {reason}" in said, said  # the reason names the sizes: not said twice
    # one fork's work landed as one merge, and the merge says so
    merges = git(repo, "log", "--merges", "--format=%H").split()
    message = git(repo, "log", "-1", "--format=%B")
    assert len(merges) == 1 and f"Executor: {repo.name}-forks.py · 3 forks, kept b · 3 attempts" in message
    assert (repo / "api.py").read_text() == "def users():\n    return ids\n"
    assert (repo / "notes.txt").exists()  # c's deletion did not land
    # no fork worktree or branch is left; each fork's work is kept on its ref, from the base
    assert not any((repo / ".graphene" / "worktrees").glob("n1*"))
    assert git(repo, "worktree", "list").count("\n") == 1 and "graphene/" not in git(repo, "branch")
    refs = git(repo, "for-each-ref", "--format=%(refname)", "refs/graphene/forks/n1/").split()
    assert refs == [f"refs/graphene/forks/n1/{b}" for b in "abc"]
    assert all(git(repo, "rev-parse", f"refs/graphene/forks/n1/{b}^").strip() == base for b in "abc")
    assert git(repo, "show", "refs/graphene/forks/n1/a:api.py") == "def users():\n    return [0]\n"
    assert git(repo, "show", "refs/graphene/forks/n1/c:api.py").startswith("import os\n\n\ndef users():\n")
    assert "notes.txt" not in git(repo, "ls-tree", "--name-only", "refs/graphene/forks/n1/c")  # c deleted it
    assert git(repo, "log", "-1", "--format=%B", "refs/graphene/forks/n1/b").strip() == (
        "fork b of n1\n\nGraphene-Node: n1")
    assert git(repo, "status", "--porcelain") == ""
    # the record: `node show` lists the forks, `plan record` says the kept one, `node diff --fork` shows one
    shown = person("node", "show", "n1").stdout.splitlines()
    assert f"  forked 3 ways · kept b: {reason}" in shown
    forks = [line for line in shown if line.startswith(("    a ", "    b ", "    c "))]
    me = f"{repo.name}-forks.py"
    assert forks[0].startswith(f"    a {me} · 1 attempt · refused: n1 is not done: `grep -q ids api.py` "
                               "failed · 2 lines · no meter · ")
    assert forks[1].startswith(f"    b {me} · 1 attempt · passed · 2 lines · no meter · ")
    assert forks[2].startswith(f"    c {me} · 1 attempt · passed · {last['c']['lines']} lines · no meter · ")
    assert sum(line.startswith(f"  attempt 1 · fork {b} · {me} · ") for b in "abc" for line in shown) == 3
    record = person("plan", "record").stdout
    assert f"    {plan.look('done')[0]} n1 · api.py · landed {merges[0][:7]} · 3 forks, kept b" in record
    assert "+    return ids" in person("node", "diff", "n1", "--fork", "b").stdout
    assert " notes.txt |" in person("node", "diff", "n1", "--fork", "c", "--stat").stdout  # its deletion
    said = person("node", "diff", "n1", "--fork", "z")
    assert said.exit_code == 1 and "n1 forked 3 ways (a, b, c): it has no fork z" in said.output


def test_a_forks_own_pass_is_judged_again_when_its_executor_ends(repo, monkeypatch):
    """b's `done` passed, then b wrote again and broke it: its tree is judged as it stands when its executor
    ends, so the pass it once had is not what the rule reads, and c's good work lands."""
    seed(repo, monkeypatch)
    said: list[str] = []
    done = go(repo, STALE, said, forks=R.Forks(3))
    assert [n.id for n in done] == ["n1"] and states(repo) == {"n1": DONE}, said
    with Store.open(repo) as store:
        last = last_rows(store)
        assert {b: f["state"] for b, f in last.items()} == {"a": "refused", "b": "refused", "c": "passed"}
        assert last["b"]["why"].startswith("1 attempt, the last one refused: n1 is not done: `grep -q ids "
                                           "api.py` failed")  # fmt: skip
        b = [e["detail"]["state"] for e in rows(store, "fork") if e["detail"]["fork"] == "b"]
        assert b == ["running", "passed", "refused", "refused"]  # its own done, then the end's own look
        [picked] = rows(store, "picked")
        assert picked["detail"]["fork"] == "c"
        assert picked["detail"]["reason"] == "the only fork whose check passed"
    assert "n1 fork b: attempt 1 refused: n1 is not done: `grep -q ids api.py` failed" in said, said
    assert f"n1 kept c of 3: the only fork whose check passed · {last['c']['lines']} lines" in said
    assert (repo / "api.py").read_text().startswith("import os\n")


def test_a_person_picks_another_fork_of_a_leaf_in_review_and_the_sign_off_lands_it(repo, monkeypatch):
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "notes.txt").write_text("to go\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    said: list[str] = []
    with Store.open(repo) as store:  # it waits for the person's sign-off, so the rule's pick is parked
        plan.propose(store, [users_leaf(signoff=True), {"id": "n2", "title": "n2", "scope": ["x.py"],
                                                       "check": "true"}], ALEX)  # fmt: skip
    assert go(repo, FORKED, said, forks=R.Forks(3), only=["n1"]) == [] and states(repo)["n1"] == REVIEW
    assert any(line.startswith("n1 kept b of 3: 2 lines against ") for line in said), said
    with Store.open(repo) as store:
        with pytest.raises(Refused, match="n2's last hold did not fork, so it has no fork a"):
            R.fork_work(store, repo, "n2", "a")
    said_no = person("node", "pick", "n1", "z")
    assert said_no.exit_code == 1 and "n1 forked 3 ways (a, b, c): it has no fork z" in said_no.output
    picked = person("node", "pick", "n1", "c")
    assert picked.exit_code == 0, picked.output
    assert picked.stdout.splitlines()[0] == (
        "n1's branch is now fork c's work (passed); `graphene node signoff n1` lands it")
    assert git(repo, "rev-parse", "graphene/n1") == git(repo, "rev-parse", "refs/graphene/forks/n1/c")
    with Store.open(repo) as store:
        first, second = rows(store, "picked")
        assert first["detail"]["by"] == "graphene" and second["actor"] == "alex (no terminal)"  # as logged
        assert second["detail"] | {"table": None} == {"fork": "c", "of": 3, "by": "person",
                                                      "reason": "picked by alex", "table": None}  # fmt: skip
        assert second["detail"]["table"] == first["detail"]["table"]
        assert plan.get(store, "n1").state == REVIEW
    assert "  forked 3 ways · kept c: picked by alex" in person("node", "show", "n1").stdout.splitlines()
    assert "+    found = ids" in person("node", "diff", "n1").stdout  # the parked branch is c's work now
    signed = person("node", "signoff", "n1")
    assert signed.exit_code == 0 and states(repo)["n1"] == DONE, signed.output
    assert (repo / "api.py").read_text().startswith("import os\n") and not (repo / "notes.txt").exists()
    assert "3 forks, kept c" in git(repo, "log", "-1", "--format=%B")
    assert git(repo, "worktree", "list").count("\n") == 1 and "graphene/" not in git(repo, "branch")
    after = person("node", "pick", "n1", "b")
    assert after.exit_code == 1, after.output
    assert "n1 is done: a fork is picked on a leaf in review, before its sign-off" in after.output
    agent = CliRunner().invoke(build(), ["node", "pick", "n1", "b"], env={"CLAUDECODE": "1"})
    assert agent.exit_code == 1 and "picking a fork is the person's to do" in agent.output


def test_the_fork_that_passes_the_others_tests_is_kept_before_the_smaller_one(repo, monkeypatch):
    """pick's agreement: a's test passes on b and c; b's stricter one fails on both; c wrote none."""
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_api.py").write_text(TEST)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    said: list[str] = []
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf(scope=["api.py", "tests/test_api.py"],
                                        check=f"{sys.executable} tests/test_api.py")], ALEX)  # fmt: skip
    done = go(repo, AGREE, said, forks=R.Forks(3))
    assert [n.id for n in done] == ["n1"] and states(repo) == {"n1": DONE}, said
    with Store.open(repo) as store:
        last = {e["detail"]["fork"]: e["detail"] for e in rows(store, "fork")}
        assert {b: f["state"] for b, f in last.items()} == {"a": "passed", "b": "passed", "c": "passed"}
        assert [(f["lines"], f["test_lines"]) for f in (last["a"], last["b"], last["c"])] == [(2, 1), (3, 2),
                                                                                                (2, 0)]
        assert last["a"]["check_touched"] == last["b"]["check_touched"] == ["tests/test_api.py"]
        assert "check_touched" not in last["c"]
        [picked] = rows(store, "picked")
        assert picked["detail"]["fork"] == "b"  # larger than a and c, and a's test passes on it
        assert picked["detail"]["reason"] == "passes a's tests (a and c fail b's)"
        table = {t["fork"]: t for t in picked["detail"]["table"]}
        assert {b: t["agrees"] for b, t in table.items()} == {"a": [], "b": ["a"], "c": ["a"]}
        assert {b: t["touched_check"] for b, t in table.items()} == {"a": True, "b": True, "c": False}
        assert plan.get(store, "n1").forked == {}
    assert "n1 kept b of 3: passes a's tests (a and c fail b's) · 3 lines against 2, 2" in said, said
    assert (repo / "api.py").read_text() == 'def users():\n    """The ids."""\n    return [1]\n'
    assert (repo / "tests" / "test_api.py").read_text().endswith("assert users.__doc__\n")
    assert "3 forks, kept b" in git(repo, "log", "-1", "--format=%B")
    assert git(repo, "status", "--porcelain") == ""
    assert not any((repo / ".graphene" / "worktrees").glob("n1*"))


def test_when_no_fork_passes_the_leaf_comes_back_with_each_forks_reason(repo, monkeypatch):
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    monkeypatch.setenv("FORKS_RELEASE", "1")  # c hands its fork back, wanting schema.py
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "notes.txt").write_text("to go\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    said: list[str] = []
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf()], ALEX)
    assert go(repo, NONE, said, forks=R.Forks(3)) == [] and states(repo) == {"n1": OPEN}
    with Store.open(repo) as store:
        [released] = rows(store, "released")
        why = released["detail"]["why"]
        assert why.startswith("no fork's check passed (3 forks): fork a: 1 attempt, the last one refused: ")
        assert "; fork b: 1 attempt" in why and why.endswith("; fork c: handed it back: needs schema")
        assert released["detail"]["wants"] == ["schema.py"]  # the union of what the forks asked for
        assert plan.came_back(store, plan.get(store, "n1")) and plan.get(store, "n1").forked == {}
        assert rows(store, "check_passed") == [] and rows(store, "check_failed") == []
        last = {e["detail"]["fork"]: e["detail"] for e in rows(store, "fork")}
        assert {b: f["state"] for b, f in last.items()} == {"a": "refused", "b": "refused", "c": "gave up"}
        assert last["c"]["wants"] == ["schema.py"] and last["c"]["why"] == "needs schema"
        offered = [k for k, _, _ in plan.offers(store, plan.get(store, "n1"))]
        assert offered == ["w", "b"]  # schema.py, which c wanted, is on offer to the person
    assert f"n1 came back: {why}" in said and "n1 fork c: gave up: needs schema" in said
    log = next((repo / ".graphene" / "runs").glob("n1.c-*-1.txt")).read_text()
    assert "this fork gives up; the leaf is handed back only if every fork does" in log
    assert "n1: what each fork tried is kept under refs/graphene/forks/n1/" in said
    assert not any((repo / ".graphene" / "worktrees").glob("n1.*"))
    assert len(git(repo, "for-each-ref", "refs/graphene/forks/n1/").splitlines()) == 3


def test_first_keeps_the_first_fork_that_passes_and_stops_the_rest(repo, monkeypatch):
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    monkeypatch.setenv("FORKS_SLOW", "ac")  # a and c sleep: b passes first, and they are stopped for it
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "notes.txt").write_text("to go\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    said: list[str] = []
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf()], ALEX)
    done = go(repo, FORKED, said, forks=R.Forks(3, first=True))
    assert [n.id for n in done] == ["n1"] and states(repo) == {"n1": DONE}, said
    with Store.open(repo) as store:
        last = {e["detail"]["fork"]: e["detail"] for e in rows(store, "fork")}
        assert {b: f["state"] for b, f in last.items()} == {"a": "stopped", "b": "passed", "c": "stopped"}
        assert last["a"]["why"] == last["c"]["why"] == "another fork's check passed first"
        assert rows(store, "forked")[0]["detail"]["first"] is True
        [picked] = rows(store, "picked")
        kept, why = picked["detail"]["fork"], picked["detail"]["reason"]
        assert (kept, why) == ("b", "the only fork whose check passed")
        states_ = [(t["fork"], t["state"]) for t in picked["detail"]["table"]]
        assert states_ == [("a", "stopped"), ("b", "passed"), ("c", "stopped")]
    assert "n1 kept b of 3: the only fork whose check passed · 2 lines" in said
    assert (repo / "api.py").read_text() == "def users():\n    return ids\n"
    assert not any((repo / ".graphene" / "worktrees").glob("n1*"))


def test_a_fork_with_no_room_under_max_usd_does_not_start_and_is_on_record(repo, monkeypatch):
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "notes.txt").write_text("to go\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    said: list[str] = []
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf()], ALEX)
    # each attempt's worst case is WORST (no --max-budget-usd in the command): room for two forks of three
    done = go(repo, FORKED, said, forks=R.Forks(3), max_usd=2 * R.WORST + 1)
    assert [n.id for n in done] == ["n1"] and "2 of 3 forks started: --max-usd has room for 2" in said
    ran = [json.loads(line) for line in (repo.parent / "forks.log").read_text().splitlines()]
    assert sorted(r["fork"] for r in ran) == ["a", "b"]
    with Store.open(repo) as store:
        last = {e["detail"]["fork"]: e["detail"] for e in rows(store, "fork")}
        assert {b: f["state"] for b, f in last.items()} == {"a": "refused", "b": "passed", "c": "failed"}
        assert last["c"]["why"] == "the run's --max-usd had no room for it" and last["c"]["attempts"] == 0
        assert rows(store, "picked")[0]["detail"]["fork"] == "b"
        table = [(t["fork"], t["state"]) for t in rows(store, "picked")[0]["detail"]["table"]]
        assert table == [("a", "refused"), ("b", "passed"), ("c", "failed")]
    assert "n1 kept b of 3: the only fork whose check passed · 2 lines" in said


def test_sweep_closes_every_forks_executor_of_a_dead_run(repo):
    """A dead run's hold had one executor to stop; forked, it has one a fork, each on its own session."""
    orphans = [subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
               for _ in "ab"]  # fmt: skip
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    try:
        with Store.open(repo) as store:
            plan.propose(store, [users_leaf()], ALEX)
            hold = R.worktree_for(store, repo, repo, "n1")
            plan.start(store, "n1", Caller("run:x", False, "hold-session"), hold)
            forked = {"fork-a": {"fork": "a", "tree": "x"}, "fork-b": {"fork": "b", "tree": "y"}}
            plan.set_forked(store, "n1", forked)
            for session, orphan, b in zip(("fork-a", "fork-b"), orphans, "ab", strict=True):
                row = {"run_pid": dead.pid, "pid": orphan.pid, "pid_start": R._started(orphan.pid),
                       "attempt": 1, "fork": b, "of": 2}  # fmt: skip
                store.log_node("n1", plan._now(), "attempt", "run:x", session, None, row)
            said: list[str] = []
            R.sweep(store, said.append, repo)
            for orphan in orphans:
                orphan.wait(timeout=15)  # each fork's executor stopped before the leaf was handed back
            assert states(repo) == {"n1": OPEN} and plan.get(store, "n1").forked == {}
            assert said == ["n1 was left running by a run that ended; handed back, and it is ready again"]
    finally:
        for orphan in orphans:
            orphan.kill()


def test_ctrl_c_ends_every_forks_executor_and_hands_the_leaf_back(repo):
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf()], ALEX)
    slow = executor(repo, SLOW)
    run = graphene_run(repo, "--with", slow, "--forks", "3", "--attempts", "1", "--no-precheck")
    try:
        assert wait_for(lambda: len(attempts(repo)) == 3), run.stdout
        pids = [e["detail"]["pid"] for e in attempts(repo)]
        assert sorted(e["detail"]["fork"] for e in attempts(repo)) == ["a", "b", "c"]
        run.send_signal(signal.SIGINT)
        said, _ = run.communicate(timeout=60)
        assert run.returncode == 130, said
        assert "run stopped: n1 handed back, ready again" in said.strip().splitlines()[-1], said
        assert states(repo) == {"n1": OPEN}
        assert wait_for(lambda: not any(R._alive(p) for p in pids), 15)  # every fork's executor is gone
        with Store.open(repo) as store:
            [released] = store.node_log("n1", ("released",))
            assert released["detail"]["why"] == R.STOPPED and released["detail"]["stopped"] is True
            last = {e["detail"]["fork"]: e["detail"]["state"] for e in store.node_log("n1", ("fork",))}
            assert last == {"a": "stopped", "b": "stopped", "c": "stopped"}
            assert plan.get(store, "n1").forked == {}
        assert not any((repo / ".graphene" / "worktrees").glob("n1.*"))
    finally:
        run.kill()


def attempts(repo):
    with Store.open(repo) as store:
        return store.node_log("n1", ("attempt",))
