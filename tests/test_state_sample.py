# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""tests/fixtures/state-sample.json: one real `graphene state --json`, for the VS Code extension and the seam
review to test against. It is made here, never by hand, from a scripted plan with every state in it: a leaf
a run of three forks landed (b kept), a leaf a Nemotron executor holds mid-attempt with a write the gate
stopped, a leaf a session handed back naming what it wants, a leaf waiting on the running one, one ready, one
of the person's own, an agent's proposal, a question on the board, the envelope and a round's row.

`RECORD_STATE_SAMPLE=1 uv run pytest tests/test_state_sample.py` writes it again (the repo's path scrubbed to
/home/dev/project); without the variable the test checks the shipped file against a fresh snapshot of the same
plan: the same keys, the same tasks in the same states, so the file cannot drift from the code."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_forks_run import FORKED, git, go
from test_run_live import repo  # noqa: F401

from graphene_map import auto, board, plan
from graphene_map import run as R
from graphene_map import state as ST
from graphene_map.plan import Caller
from graphene_map.store import Store

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "state-sample.json"
HOME = "/home/dev/project"
ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")
HELD = Caller("claude:aaaa1111", False, "aaaa1111-0000-4000-8000-0000000000c1")
NEMOTRON = "d74f0000-0000-4000-8000-0000000000b1"  # the run's session for the leaf Nemotron holds
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


def scenario(repo, monkeypatch) -> None:
    monkeypatch.setenv("FORKS_LOG", str(repo.parent / "forks.log"))
    (repo / "api.py").write_text("def users():\n    return []\n")
    (repo / "notes.txt").write_text("to go\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "api")
    with Store.open(repo) as store:
        plan.set_goal(store, "the app greets, says goodbye, and knows its users", ALEX)
        plan.propose(store, [
            {"id": "api", "title": "the API"},
            {"id": "ids", "title": "users returns ids", "parent": "api", "scope": ["api.py", "notes.txt"],
             "check": "grep -q ids api.py"},
        ], ALEX)  # fmt: skip
    said: list[str] = []
    go(repo, FORKED, said, forks=R.Forks(3))  # ids: three forks at once, a refused, b kept over c, landed
    now = datetime.now(UTC)

    def at(ago: float) -> str:
        return (now - timedelta(seconds=ago)).isoformat().replace("+00:00", "Z")

    with Store.open(repo) as store:
        plan.propose(store, [
            {"id": "words", "title": "the greeting's words", "scope": ["words.py"], "check": "true"},
            {"id": "greet", "title": "greet says hello", "scope": ["app.py"], "check": "true",
             "needs": ["words"]},
            {"id": "farewell", "title": "farewell says goodbye", "scope": ["bye.py"], "check": "true"},
            {"id": "docs", "title": "document the API", "scope": ["README.md"], "check": "true",
             "needs": ["ids"]},
            {"id": "mine", "title": "the release notes, by hand", "scope": ["NOTES.md"], "check": "true",
             "owner": "alex"},
        ], ALEX)  # fmt: skip
        # words: a Nemotron executor `graphene run` started, in its first attempt, metered
        plan.start(store, "words", Caller("run:nemotron", False, NEMOTRON), repo, now=at(60))
        rows = [
            (50, "attempt", {"attempt": 1, "log": "words-1.txt"}),
            (49, "usage", {"attempt": 1, "calls": 1, "prompt_tokens": 1800, "completion_tokens": 240,
                           "dollars": 0.004, "model": NANO, "endpoint": "token factory"}),
            (30, "did", {"attempt": 1, "verb": "reading", "target": "app.py"}),
            (20, "did", {"attempt": 1, "verb": "editing", "target": "words.py"}),
            (10, "did", {"attempt": 1, "verb": "running", "target": "pytest -q"}),
            (5, "denied", {"attempt": 1, "path": "app.py"}),  # a write outside its scope, stopped
        ]  # fmt: skip
        for ago, kind, detail in rows:
            store.log_node("words", at(ago), kind, "run:nemotron", NEMOTRON, None, detail)
        # farewell: a Claude Code session took it and handed it back, naming what it needs
        plan.start(store, "farewell", HELD, repo, now=at(45))
        plan.release(store, "farewell", HELD, "bye.py imports the schema, which no leaf makes", now=at(15),
                     wants=["schema.py"])  # fmt: skip
        board.add(store, "question", "formal or casual greeting?", BOT, default="casual",
                  options=[{"text": "formal"}], about="words")  # fmt: skip
        plan.propose(store, [{"id": "notes", "title": "release notes", "scope": ["CHANGELOG.md"],
                              "check": "true"}], BOT)  # fmt: skip
        store.set_meta("settings:auto", "on")
        store.set_meta("settings:budget", "2.0")
        store.set_meta("settings:tasks", "12")
        store.log_node("*", plan._now(), auto.KIND, "graphene auto", None, None,
                       {"round": 1, "rounds": 2, "stage": "running", "spent": 0.004, "budget": 2.0,
                        "check": None, "why": ""})  # fmt: skip


def snapshot(repo) -> dict:
    with Store.open(repo) as store:
        s = ST.snapshot(store, repo)
    return json.loads(json.dumps(s).replace(str(repo), HOME))


def test_the_sample_is_a_real_snapshot_of_the_scripted_plan(repo, monkeypatch):
    scenario(repo, monkeypatch)
    fresh = snapshot(repo)
    states = {t["id"]: t["state"] for t in fresh["tasks"]}
    assert states == {"ids": "done", "words": "running", "greet": "waiting", "farewell": "came back",
                      "docs": "ready", "mine": "yours", "notes": "proposed"}  # fmt: skip
    by = {t["id"]: t for t in fresh["tasks"]}
    assert by["words"]["model"] == "Nano" and by["words"]["usd"] == 0.004
    assert by["words"]["stopped"] == ["app.py"]
    assert by["words"]["tail"] == ["edit words.py", "run  pytest -q", "stopped app.py"]
    assert by["ids"]["kept"]["letter"] == "b" and [f["letter"] for f in by["ids"]["forks"]] == ["a", "b", "c"]
    assert by["farewell"]["note"].startswith("bye.py imports the schema") and "w" in by["farewell"]["offers"]
    assert fresh["auto"]["stage"] == "running" and fresh["envelope"]["auto"] == "on"
    assert fresh["questions"][0]["about"] == "words" and fresh["spent"] == 0.004
    assert fresh["width"] >= 3  # the three forks at once; four when words' backdated attempt overlaps them
    assert fresh["repo"] == HOME and HOME not in json.dumps(fresh["news"])
    if os.environ.get("RECORD_STATE_SAMPLE"):
        SAMPLE.write_text(json.dumps(fresh, indent=2) + "\n")
    shipped = json.loads(SAMPLE.read_text())
    assert set(shipped) == set(fresh), "the sample's keys are not the snapshot's: record it again"
    assert {t["id"]: t["state"] for t in shipped["tasks"]} == states
    assert [sorted(t) for t in shipped["tasks"]] == [sorted(t) for t in fresh["tasks"]]
    assert [[f["letter"], f["state"]] for f in {t["id"]: t for t in shipped["tasks"]}["ids"]["forks"]] == [
        [f["letter"], f["state"]] for f in by["ids"]["forks"]
    ]
    assert shipped["envelope"] == fresh["envelope"] and shipped["auto"] == fresh["auto"]
    assert shipped["goals"] == fresh["goals"] and shipped["edges"] == fresh["edges"]
    for key in ("schema", "goal", "first", "planner", "executor", "run", "spent", "scoreboard", "width"):
        assert shipped[key] == fresh[key], key
