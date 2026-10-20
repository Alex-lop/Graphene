# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""A leaf run as forks: N agents at once, a worktree each, cut from the same commit; each judged by the
leaf's check in its own copy; one kept and landed as any leaf lands; the rest on record. The executor is
a script that behaves by its GRAPHENE_FORK: a fails the check, b passes with a small change, c with a
larger one."""

import json
import signal
import subprocess
import sys

from test_run_live import SLOW, graphene_run, repo, states, wait_for  # noqa: F401

from graphene_map import plan
from graphene_map import run as R
from graphene_map.plan import DONE, OPEN, Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
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
"""
NONE = FORKED.replace("return ids", "return [1]").replace("found = ids", "found = [1]")


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
    return R.run_parallel(lambda: Store.open(repo), repo, repo, 1, command, attempts=1, say=said.append,
                          logs=repo / ".graphene" / "runs", **kw)  # fmt: skip


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
        assert all(f["ref"] == f"refs/graphene/forks/n1/{b}" for b, f in last.items())
        assert len(rows(store, "check_passed")) == 1  # the leaf's proof: the hold's own finish, once
        [picked] = rows(store, "picked")
        kept = picked["detail"]["fork"]
        assert kept in "bc" and picked["detail"]["of"] == 3 and picked["detail"]["by"] == "graphene"
        assert [t["fork"] for t in picked["detail"]["table"]] == ["a", "b", "c"]
        assert plan.get(store, "n1").forked == {}  # cleared with the hold
        assert [e["kind"] for e in store.node_log("n1")][-3:] == ["check_passed", "finished", "landed"]
    assert f"n1 forked 3 ways: a {repo.name}-forks.py, b {repo.name}-forks.py, c {repo.name}-forks.py" in said
    assert f"n1 fork b: the check passed · {last['b']['lines']} lines" in said
    assert "n1 fork a: attempt 1 refused: n1 is not done: `grep -q ids api.py` failed" in said
    assert "n1 fork a: 1 attempt, the last one refused" in said
    assert any(line.startswith(f"n1 kept {kept} of 3: finished first · ") and " lines against " in line
               for line in said), said  # fmt: skip
    # one fork's work landed as one merge, and the merge says so
    merges = git(repo, "log", "--merges", "--format=%H").split()
    assert len(merges) == 1 and "Forks: 3, kept " + kept in git(repo, "log", "-1", "--format=%B")
    expect = {"b": "def users():\n    return ids\n", "c": "import os\n\n\ndef users():\n    found = ids\n"
              "    return found\n\n\ndef more():\n    return 1\n"}[kept]  # fmt: skip
    assert (repo / "api.py").read_text() == expect
    assert (repo / "notes.txt").exists() == (kept == "b")  # c's deletion lands with c
    # no fork worktree or branch is left; each fork's work is kept on its ref, from the base
    assert not any((repo / ".graphene" / "worktrees").glob("n1*"))
    assert git(repo, "worktree", "list").count("\n") == 1 and "graphene/" not in git(repo, "branch")
    refs = git(repo, "for-each-ref", "--format=%(refname)", "refs/graphene/forks/n1/").split()
    assert refs == [f"refs/graphene/forks/n1/{b}" for b in "abc"]
    assert git(repo, "rev-parse", "refs/graphene/forks/n1/b^").strip() == base
    assert git(repo, "status", "--porcelain") == ""


def test_when_no_fork_passes_the_leaf_comes_back_with_each_forks_reason(repo, monkeypatch):
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
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
        assert "; fork b: 1 attempt" in why and "; fork c: 1 attempt" in why
        assert plan.came_back(store, plan.get(store, "n1")) and plan.get(store, "n1").forked == {}
        assert rows(store, "check_passed") == [] and rows(store, "check_failed") == []
        assert {e["detail"]["state"] for e in rows(store, "fork")} == {"running", "refused"}
    assert f"n1 came back: {why}" in said
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
        assert rows(store, "picked")[0]["detail"]["fork"] == "b"
    assert "n1 kept b of 3: the only fork whose check passed · 2 lines" in said
    assert (repo / "api.py").read_text() == "def users():\n    return ids\n"
    assert not any((repo / ".graphene" / "worktrees").glob("n1*"))


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
