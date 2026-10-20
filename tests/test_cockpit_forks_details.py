# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The forks in the details' record pane (a table, and which was kept) and in the replay's news, which names
a fork as the rows do: the agent's number and its letter."""

import json

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import plan
from graphene_map.cockpit.details import pane_text
from graphene_map.cockpit.replay import news
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")
WITH = {"a": "claude", "b": "claude:opus", "c": "codex"}


def forked(store, repo):
    plan.propose(store, [{"id": "ids", "title": "ids", "scope": ["api.py"], "check": "true"}], ALEX)
    plan.start(store, "ids", BOT, repo)
    store.log_node("ids", plan._now(), "forked", "run:claude", BOT.session_id, None,
                   {"forks": ["a", "b", "c"], "of": 3, "first": False, "with": WITH})  # fmt: skip
    store.log_node("ids", plan._now(), "fork", "run:claude", None, None,
                   {"fork": "a", "of": 3, "state": "refused", "why": "`pytest -q` failed", "lines": 58,
                    "attempts": 2, "with": "claude", "dollars": 0.52, "seconds": 240.1})  # fmt: skip
    store.log_node("ids", plan._now(), "fork", "run:claude", None, None,
                   {"fork": "b", "of": 3, "state": "passed", "why": "", "lines": 31, "attempts": 1,
                    "with": "claude:opus", "dollars": 0.41, "seconds": 182.0})  # fmt: skip


def test_the_record_pane_has_the_forks_table_and_which_was_kept_when_the_hold_forked(repo):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "docs", "title": "docs", "scope": ["README.md"], "check": "true"}], ALEX)
        plan.start(store, "docs", BOT, repo)
        said = pane_text(store, repo, "docs", "record", 100).plain
        assert "forks" not in said.split("holds")[1] and "could not be made" not in said  # one agent: as was
        forked(store, repo)
        said = pane_text(store, repo, "ids", "record", 100).plain
        assert "could not be made" not in said and "won" not in said
        table = [line.split() for line in said.split("\nforks\n")[1].splitlines()]
        assert table[0] == ["fork", "with", "attempts", "state", "lines", "dollars", "seconds"]
        assert table[1] == ["a", "claude", "2", "refused", "58", "$0.52", "4m00s"]
        assert table[2] == ["b", "claude:opus", "1", "passed", "31", "$0.41", "3m02s"]
        assert table[3] == ["c", "codex", "running"]  # no verdict yet: what it runs with, from the forked row
        assert table[4] == ["none", "kept", "yet"]
        store.log_node("ids", plan._now(), "picked", "run:claude", None, None,
                       {"fork": "b", "of": 3, "by": "graphene", "reason": "31 lines against 58"})  # fmt: skip
        said = pane_text(store, repo, "ids", "record", 100).plain
        assert said.rstrip().endswith("kept b · 31 lines against 58")
        store.log_node("ids", plan._now(), "fork", "run:claude", None, None,
                       {"fork": "c", "of": 3, "state": "stopped", "why": "b passed first", "with": "codex",
                        "attempts": 1})
        said = pane_text(store, repo, "ids", "record", 100).plain
        table = [line.split() for line in said.split("\nforks\n")[1].splitlines()]
        assert table[3] == ["c", "codex", "1", "ended"]  # the run ended it: `stopped` is the gate's word


def test_the_forks_table_fits_the_pane_when_a_fork_runs_with_a_command(repo):
    """A `--with` may be a command. The table padded every column to its widest cell, so a 65-character
    command made rows wider than the pane, which wrapped them: the columns after `with` landed on a second
    line under each row. The `with` cell takes what the other columns leave, cut with an ellipsis."""
    command = "python -m myagent --model gpt-5 --tools shell,edit --max-steps 40"
    with Store.open(repo) as store:
        forked(store, repo)
        store.log_node("ids", plan._now(), "fork", "run:claude", None, None,
                       {"fork": "c", "of": 3, "state": "passed", "lines": 40, "attempts": 1, "with": command,
                        "dollars": 0.2, "seconds": 61.0})  # fmt: skip
        for wide in (76, 96):  # the record pane at 80 and 100 columns
            lines = pane_text(store, repo, "ids", "record", wide).plain.split("\nforks\n")[1].splitlines()
            assert all(len(line) <= wide for line in lines), (wide, lines)
            head, c = lines[0], lines[3]
            assert c.index("passed") == head.index("state") and c.index("1m01s") == head.index("seconds")
            assert "python -m myagent" in c and "…" in c and "--max-steps" not in c
        assert command in pane_text(store, repo, "ids", "record", 200).plain  # room enough: whole


def row(node, kind, **detail):
    return {"node_id": node, "kind": kind, "detail": json.dumps(detail)}


GREET = {"greet": "greet says hello"}


def test_the_news_names_a_fork_by_its_agents_number_and_its_letter_and_says_what_its_check_said():
    names = {"greet": "3"}
    line = {"node_log": [row("greet", "did", verb="editing", target="app.py", fork="b"),
                         row("greet", "said", text="done", fork="c"),
                         row("greet", "denied", path="words.py", fork="a")]}  # fmt: skip
    said = "agent 3b: editing app.py · agent 3c: done · agent 3a: stopped writing words.py"
    assert news(line, GREET, names) == said
    by_title = ["greet says hello fork b: editing app.py", "greet says hello fork c: done",
                "greet says hello fork a: stopped writing words.py"]  # no number known: the title
    assert news(line, GREET) == " · ".join(by_title)
    line = {"node_log": [row("greet", "forked", forks=["a", "b", "c"], of=3)]}
    assert news(line, GREET, names) == "greet says hello forked 3 ways"
    line = {"node_log": [row("greet", "fork", fork="b", of=3, state="passed", lines=31, attempts=1),
                         row("greet", "fork", fork="a", of=3, state="gave up", why="it needs words.py",
                             attempts=1),
                         row("greet", "fork", fork="c", of=3, state="running")]}  # fmt: skip
    said = "agent 3b: its check passed, 31 lines · agent 3a: gave up: it needs words.py"
    assert news(line, GREET, names) == said  # a fork still running is bookkeeping; ` · ` parts the items
    line = {"node_log": [row("greet", "picked", fork="b", of=3, by="graphene", reason="31 lines against 58")]}
    assert news(line, GREET, names) == "greet says hello kept b: 31 lines against 58"
    reason = "passes a's tests (a fails b's) · 31 lines against 58"  # the rule's own ` · ` reads as a comma
    line = {"node_log": [row("greet", "picked", fork="b", of=3, by="graphene", reason=reason),
                         row("greet", "fork", fork="c", of=3, state="gave up", why="needs x · y", attempts=1),
                         row("greet", "did", verb="editing", target="app.py", fork="a")]}  # fmt: skip
    said = "greet says hello kept b: passes a's tests (a fails b's), 31 lines against 58"
    assert news(line, GREET, names) == said + " · agent 3c: gave up: needs x, y · agent 3a: editing app.py"
    line = {"node_log": [row("greet", "picked", fork="a", of=2, by="person", reason="")]}
    assert news(line, GREET, names) == "greet says hello kept a: your pick"
    nemotron = {"node_log": [row("greet", "fork", fork=1, of=2, state="passed", why="")]}  # numbered: as was
    assert news(nemotron, GREET, names) == ""
    line = {"node_log": [row("greet", "fork", fork="c", of=3, state="stopped", why="b passed first",
                             attempts=1),
                         row("greet", "denied", path="words.py", fork="a")]}  # fmt: skip
    assert news(line, GREET, names) == "agent 3c: ended: b passed first · agent 3a: stopped writing words.py"
