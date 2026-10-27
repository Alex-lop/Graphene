# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""The snapshot's keys for the editor night (schema 1, siblings only): top-level `replay`; each task's `why`,
`checkout`, `base` and `attempts`; each fork's `attempts`, `idle` and `checkout`. The contract's section "The
CLI", shape 2."""

import json
import os
import signal
from datetime import UTC, datetime, timedelta

from test_forks_run import FORKED, executor, go, seed, users_leaf
from test_run_live import graphene_run, leaf, repo, states, wait_for  # noqa: F401
from test_state_json import ALEX, BOT, snapshot, whole

from graphene_map import plan
from graphene_map import run as R
from graphene_map.plan import RUNNING, Caller
from graphene_map.store import Store

NEW_TASK = {"why": str, "checkout": (str, type(None)), "base": (str, type(None)), "attempts": int}
NEW_FORK = {"attempts": int, "idle": (int, float, type(None)), "checkout": (str, type(None))}


def typed(shape, got, what):
    for key, kind in shape.items():
        assert key in got and isinstance(got[key], kind), (what, key, got.get(key))


def test_a_plain_plan_has_the_keys_with_nothing_in_them(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    s = snapshot()
    whole(s)
    assert s["replay"] is None
    (t,) = s["tasks"]
    typed(NEW_TASK, t, "a")
    assert (t["why"], t["checkout"], t["base"], t["attempts"]) == ("", None, None, 0)


def test_a_running_task_names_its_checkout_its_base_and_its_attempts(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        sid = "5e55105e-0000-4000-8000-0000000000a3"
        plan.start(store, "a", Caller("run:nemotron", False, sid), repo)
        at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        for n in (1, 2):
            store.log_node("a", at, "attempt", "run:nemotron", sid, None, {"attempt": n, "log": "x.txt"})
    head = os.popen(f"git -C {repo} rev-parse HEAD").read().strip()
    (t,) = snapshot()["tasks"]
    assert t["state"] == "running" and t["checkout"] == str(repo.resolve()) and t["base"] == head
    assert t["attempts"] == 2 and t["why"] == ""


def test_a_task_that_came_back_says_why_in_one_line_and_keeps_its_checkout(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt"), leaf("c", "c.txt")], ALEX)
        plan.start(store, "a", BOT, repo)
        plan.release(store, "a", BOT, "it needs src/util.py,\n  and c must land first")
    by = {t["id"]: t for t in snapshot()["tasks"]}
    assert by["a"]["state"] == "came back"
    assert by["a"]["why"] == "it needs src/util.py, and c must land first"  # one line, whatever it said
    assert by["a"]["checkout"] == str(repo.resolve()) and by["a"]["base"]
    assert by["c"]["why"] == "" and by["c"]["checkout"] is None


def test_a_running_forks_idle_and_checkout_are_its_own_and_go_when_it_ends(repo, monkeypatch):
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")
    monkeypatch.setenv("FORKS_SLOW", "abc")  # every fork sleeps: all three run when the snapshot is read
    seed(repo, monkeypatch)
    run = graphene_run(repo, "--forks", "3", "--with", executor(repo, FORKED))
    try:
        assert wait_for(lambda: states(repo) == {"n1": RUNNING}), run.stdout
        trees = repo / ".graphene" / "worktrees"
        assert wait_for(lambda: len(list(trees.glob("n1.*"))) == 3 and (repo.parent / "forks.log").exists())
        assert wait_for(lambda: len((repo.parent / "forks.log").read_text().splitlines()) == 3)
        (t,) = snapshot()["tasks"]
        whole_forks = {f["letter"]: f for f in t["forks"]}
        assert set(whole_forks) == {"a", "b", "c"}
        for letter, f in whole_forks.items():
            typed(NEW_FORK, f, letter)
            assert f["state"] == "running" and f["attempts"] == 1
            assert f["idle"] is not None and f["idle"] >= 0
            assert f["checkout"] == str(trees / f"n1.{letter}")
        assert t["attempts"] == 1 and t["checkout"] == str(trees / "n1")  # the leaf's own tree
    finally:
        os.kill(run.pid, signal.SIGINT)
        run.wait(30)


def test_a_forked_leaf_that_landed_has_each_forks_attempts_and_nothing_running(repo, monkeypatch):
    seed(repo, monkeypatch)
    go(repo, FORKED, [], forks=R.Forks(3))
    (t,) = snapshot()["tasks"]
    assert t["state"] == "done" and t["attempts"] == 1 and t["checkout"] is None
    for f in t["forks"]:
        typed(NEW_FORK, f, f["letter"])
        assert f["attempts"] == 1 and f["idle"] is None and f["checkout"] is None


def test_the_replay_key_reads_the_stores_own_plan_meta_and_is_null_elsewhere(repo):
    with Store.open(repo) as store:
        plan.propose(store, [users_leaf()], ALEX)
    assert snapshot()["replay"] is None
    told = {"shown": "a scripted stand-in, no model ran", "day": "2026-10-26", "repository": "wordkit"}
    with Store.open(repo) as store:
        store.set_meta("replay", json.dumps({**told, "more": "ignored"}))
    assert snapshot()["replay"] == told
    with Store.open(repo) as store:
        store.set_meta("replay", "not json")
    assert snapshot()["replay"] is None


def test_the_snapshot_is_as_fast_as_before_on_a_forty_task_plan(repo):
    """The new keys add one `nodes` read and a `stat` a running task or fork: the bound test_state_json sets
    still holds."""
    import time

    from graphene_map import state as ST

    leaves = [leaf(f"t{i}", f"d{i}/x.txt") for i in range(40)]
    now = datetime.now(UTC)
    with Store.open(repo) as store:
        plan.propose(store, leaves, ALEX)
        for i in range(4):
            sid = f"5e55105{i}-0000-4000-8000-0000000000a1"
            plan.start(store, f"t{i}", Caller(f"claude:5e55105{i}", False, sid), repo)
            for k in range(200):
                at = (now - timedelta(seconds=(200 - k) * 0.05)).isoformat().replace("+00:00", "Z")
                detail = {"attempt": 1, "tool": "Edit", "target": f"d{i}/f{k % 40}.py", "verb": "editing"}
                store.log_node(f"t{i}", at, "did", "run:claude", sid, None, detail)
    start = time.perf_counter()
    with Store.open(repo) as store:
        s = ST.snapshot(store, repo)
    assert time.perf_counter() - start < 1.0
    assert sum(t["checkout"] is not None for t in s["tasks"]) == 4
