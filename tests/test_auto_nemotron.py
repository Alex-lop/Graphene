# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene auto` on the Nemotron path, against the stand-in Token Factory: Ultra plans in the strict schema,
Nano executes in Graphene's own tool loop, two forks a task, the goal's check is red after round 1 and green
after the fix; the auto rows carry what it cost at the stand-in's list prices. The hackathon story, with no
key."""

import json
import subprocess

import pytest
from fake_tokenfactory import Fake, call
from test_plan_cli import person, repo  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map import plan as P
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.store import Store

GOAL = "the app says hi and bye"
GOAL_CHECK = """python3 -c 'import greet, bye; assert greet.hi() + " " + bye.bye() == "hi bye"'"""


def node(id, title, scope, check, goal=""):
    return {"id": id, "title": title, "goal": goal, "scope": list(scope), "check": check, "needs": [],
            "parent": None, "mark": "?"}  # fmt: skip


TREE = {"says": "Two small tasks, one file each.", "goal": None, "board": [], "nodes": [
    node("greet", "greet says hi", ["greet.py"], "python3 -c 'import greet; assert greet.hi() == \"hi\"'"),
    node("bye", "bye says bye", ["bye.py"], "python3 -c 'import bye; assert bye.bye()'"),
]}  # fmt: skip
BYE_FIX = "python3 -c 'import bye; assert bye.bye() == \"bye\"'"
FIX = {"says": "bye said bye! with a bang.", "goal": None, "board": [], "nodes": [
    node("bye-fix", "bye says bye, not bye!", ["bye.py"], BYE_FIX),
]}  # fmt: skip
WRITES = {"greet": ("greet.py", 'def hi():\n    return "hi"\n'),
          "bye": ("bye.py", 'def bye():\n    return "bye!"\n'),
          "bye-fix": ("bye.py", 'def bye():\n    return "bye"\n')}  # fmt: skip


def reply(body):
    """Ultra: read nothing, answer the tree (the fix once the prompt carries the red check). Nano: write the
    leaf's file, then done; each fork's conversation is its own."""
    first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
    if "Ultra" in body["model"]:
        if not body.get("response_format"):
            return {"content": "I have read enough."}
        return {"content": json.dumps(FIX if "has landed, and its own check still fails" in first else TREE)}
    leaf = next((k for k in WRITES if f"{k} (revision" in first), None)
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    path, text = WRITES[leaf]
    steps = [call("write", path=path, content=text), call("done")]
    return steps[k] if k < len(steps) else {"content": "nothing more"}


@pytest.fixture
def fake(monkeypatch):
    f = Fake([reply] * 200).__enter__()
    for k, v in f.env().items():
        monkeypatch.setenv(k, v)
    tf._listed.cache_clear()
    yield f
    f.__exit__(None, None, None)


@pytest.fixture
def tiny(repo):
    (repo / ".gitignore").write_text(".graphene/\n__pycache__/\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "ignore"],
                   cwd=repo, check=True)  # fmt: skip
    return repo


def test_ultra_plans_nano_races_two_forks_a_task_and_the_fix_round_makes_the_goal_pass(tiny, fake):
    said = person("auto", GOAL, "--planner", "nemotron", "--with", "nemotron", "--forks", "2",
                  "--budget", "2", "--check", GOAL_CHECK, "--parallel", "2")  # fmt: skip
    out = said.stdout
    assert said.exit_code == 0, said.output
    assert "nemotron bills each call after it ends: the budget is read between rounds" in out
    assert "· 2 forks a task ·" in out.splitlines()[0]
    assert "accepted inside your envelope (auto on since " in out and "): greet, bye." in out
    assert "the goal's check failed: " in out and "round 2: planning the fix" in out
    last = out.strip().splitlines()[-1]
    assert last.startswith("auto: 2 rounds, 3 tasks landed, 0 came back, 6 forks raced, $0.00")
    assert last.endswith("at list price; the goal's check passed. `graphene plan log` has the whole history")
    with Store.open(tiny) as store:
        got = [r["detail"] for r in store.node_log("*", (AUTO.KIND,))]
        stages = ["planning", "running", "checking", "fixing", "running", "checking", "done"]
        assert [r["stage"] for r in got] == stages
        assert got[-1]["spent"] > 0 and got[-1]["budget"] == 2.0 and got[-1]["check"] == "pass"
        assert got[1]["spent"] > 0  # the planner's own bill counts, before anything ran
        models = {r["detail"]["model"] for r in store.node_log(None, ("usage",))}
        assert models == {"nvidia/Nemotron-3-Ultra-fake", "nvidia/Nemotron-3-Nano-fake"}
        picked = store.node_log(None, ("picked",))
        assert {r["node_id"] for r in picked} == {"greet", "bye", "bye-fix"}  # a fork kept for each, by rule
        root = got[-1]["root"]
        assert P.get(store, root).state == P.DONE and P.get(store, "bye-fix").parent == root
    assert (tiny / "bye.py").read_text().endswith('return "bye"\n')
    asked = [r for r in fake.requests if "Ultra" in r["model"] and r.get("response_format")]
    assert len(asked) == 2  # the tree, then the fix
    system = " ".join(asked[0]["messages"][0]["content"].split())
    assert "Leaves that can run at the same time share no file" in system  # the width rule, Ultra's too
