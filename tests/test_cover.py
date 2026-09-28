"""`graphene plan cover` against the recorded fake: Nano says which leaf carries each clause of the
person's paragraph; only the person's own words are kept, and only those are offered for a leaf."""

import json
import shlex
import subprocess

import pytest
from fake_tokenfactory import Fake
from typer.testing import CliRunner

from graphene_map import cover as C
from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map import tokenfactory as tf
from graphene_map.cli import build
from graphene_map.store import Store

NANO = "nvidia/Nemotron-3-Nano-fake"
PARAGRAPH = """Load the XML feed into items.   Prices are in cents.
An empty feed means nothing is loaded and the command exits cleanly."""
PLAN = """goal: the feed loads
- the feed  [feed]
  ? parse the xml  [xml-wiring]
      read the XML feed into items.
      scope: app.py
      check: python3 -c 'import app'
  ? prices  [prices]
      prices in cents
      scope: src/**
      check: python3 -c 'import app'
"""
EMPTY = "an empty feed means nothing is loaded and the command   exits cleanly."  # the model's casing
ANSWER = {"clauses": [
    {"text": "Load the XML feed into items", "leaf": "xml-wiring", "nearest": None},
    {"text": "Prices are in cents", "leaf": "prices", "nearest": None},
    {"text": EMPTY, "leaf": None, "nearest": "xml-wiring"},
]}  # fmt: skip
SAID = "An empty feed means nothing is loaded and the command exits cleanly"  # the person's, as written


def nano(answer) -> dict:
    return {"content": answer if isinstance(answer, str) else json.dumps(answer)}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_SHAPE"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "app.py").write_text("def load():\n    return []\n")
    (root / "src").mkdir()
    (root / "src" / "prices.py").write_text("# cents\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "start"], check=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def fake(monkeypatch):
    started = []

    def start(replies):
        f = Fake(replies).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        started.append(f)
        return f

    yield start
    for f in started:
        f.__exit__(None, None, None)


def planned(repo) -> Store:
    store = Store.open(repo)
    with store.claim():
        T.apply(store, PLAN, P.Caller("planner:nemotron", False, "s"), None, files=P.tracked(repo))
    store.log_node("*", P._now(), "asked", "alex", None, None, {"note": PARAGRAPH, "about": None})
    return store


def person(*args):
    return CliRunner().invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"})


def test_a_clause_no_leaf_carries_is_one_row_and_its_offer_is_the_persons_words(repo, fake):
    f = fake([nano(ANSWER)])
    said = []
    with planned(repo) as store:
        [u] = C.cover(store, say=said.append)
        assert u["note"] == SAID and u["nearest"] == "xml-wiring"
        [row] = store.node_log("*", ("uncovered",))
        assert row["detail"]["note"] == SAID
        [read] = store.node_log("*", ("covered",))
        assert [c["leaf"] for c in read["detail"]["clauses"]] == ["xml-wiring", "prices", None]
        [bill] = store.node_log("*", ("usage",))
        assert bill["detail"]["endpoint"] == "a stand-in" and bill["detail"]["model"] == NANO
    [asked] = f.requests
    assert asked["model"] == NANO and asked["reasoning_effort"] == "low"
    assert asked["response_format"]["type"] == "json_schema"
    assert "Prices are in cents" in asked["messages"][1]["content"]
    assert "[xml-wiring]" in asked["messages"][1]["content"]
    assert "answered by a stand-in, not Token Factory" in said[0]
    assert said[1] == "of your 3 clauses, 2 are carried by the plan and 1 are not"
    offered = said[2].split("`")[1]
    assert said[2].startswith(f"1. You said '{SAID}'; no leaf carries it. Take it: `graphene node set")
    took = person(*shlex.split(offered)[1:])  # the command as the person would paste it
    assert took.exit_code == 0, took.output
    with Store.open(repo) as store:
        assert P.get(store, "xml-wiring").goal == f"read the XML feed into items; {SAID}"


def test_a_clause_the_model_invents_is_dropped_and_an_unknown_leaf_is_uncovered(repo, fake):
    fake([nano({"clauses": [
        {"text": "Prices must never be zero", "leaf": None, "nearest": "prices"},  # not in the paragraph
        {"text": "Prices are in cents", "leaf": "cents-leaf", "nearest": "no-such-leaf"},
    ]})])  # fmt: skip
    said = []
    with planned(repo) as store:
        [u] = C.cover(store, say=said.append)
        assert u == {"note": "Prices are in cents", "nearest": None, "run": u["run"]}
        [read] = store.node_log("*", ("covered",))
        assert read["detail"]["dropped"] == ["Prices must never be zero"]
    assert "1 it gave are not your words, and were dropped" in said[1]
    assert "zero" not in "\n".join(said[2:]) and "No open leaf is near it" in said[2]


def test_a_reply_that_is_not_json_records_nothing_but_its_bill(repo, fake):
    fake([nano("Sure! Here are the clauses: ...")])
    said = []
    with planned(repo) as store:
        assert C.cover(store, say=said.append) == []
        assert store.node_log("*", ("covered", "uncovered")) == []
        assert len(store.node_log("*", ("usage",))) == 1  # it was spent, so it is billed
    assert said[-1] == "its answer is not the JSON asked for: nothing is recorded"


def test_a_dismissed_clause_is_not_flagged_again(repo, fake):
    fake([nano(ANSWER), nano(ANSWER)])
    with planned(repo) as store:
        C.cover(store, say=lambda s: None)
    set_aside = person("plan", "cover", "--dismiss", "1")
    assert set_aside.exit_code == 0 and set_aside.stdout.strip() == f"set aside for good: '{SAID}'"
    again = person("plan", "cover")
    assert again.exit_code == 0, again.output
    assert "1 are not" not in again.stdout and "You said" not in again.stdout
    with Store.open(repo) as store:
        assert len(store.node_log("*", ("uncovered",))) == 1 and C.standing(store) == []
    assert person("plan", "cover", "--dismiss", "1").exit_code == 1  # the last cover found none


@pytest.mark.parametrize("flag", ["", "notes,cover"])
def test_the_flag_runs_it_once_the_proposal_has_landed(repo, fake, monkeypatch, flag):
    from graphene_map.ask import ask, named

    monkeypatch.setenv("GRAPHENE_SHAPE", flag)
    f = fake([{"content": f"```plan\n{PLAN}```"}, nano(ANSWER)])
    said = []
    with Store.open(repo) as store:
        ask(store, repo, PARAGRAPH, named("nemotron"), say=said.append)
        assert P.get(store, "xml-wiring").state == P.PROPOSED  # the proposal stands either way
    assert len(f.requests) == (2 if flag else 1)
    assert any(f"You said '{SAID}'" in line for line in said) == bool(flag)
