# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The race, read: every agent names its model in a word (`meter.short`), each fork its own, with the dollars
so far, from the rows a run already writes; and the envelope's round, read for the head while auto is on."""

from datetime import UTC, datetime, timedelta

import pytest
from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import meter, plan
from graphene_map.cockpit.read import read
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:5e55105e", False, "5e55105e-0000-4000-8000-0000000000a1")
SESSIONS = {"a": "aaaaaaaa-0000-4000-8000-00000000000a", "b": "bbbbbbbb-0000-4000-8000-00000000000b",
            "c": "cccccccc-0000-4000-8000-00000000000c"}  # fmt: skip
NANO, SUPER = "nvidia/Nemotron-3-Nano-fake", "nvidia/Nemotron-3-Super-fake"


@pytest.mark.parametrize(
    ("model", "said"),
    [
        ("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "Nano"),
        ("nvidia/nemotron-3-super-120b-a12b", "Super"),
        ("nvidia/Nemotron-3-Ultra-550b-a55b", "Ultra"),
        ("nemotron --model nvidia/Nemotron-3-Nano-fake --model nvidia/Nemotron-3-Super-fake", "Nano"),
        ("claude-haiku-4-5-20251001", "Haiku"),
        ("claude-sonnet-5", "Sonnet"),
        ("claude-opus-5-5[1m]", "Opus"),
        ("claude-fable-5-1", "Fable"),
        ("claude:opus", "Opus"),
        ("codex", "Codex"),
        ("codex:gpt-5", "Codex"),
        ("openai/gpt-5-codex", "Codex"),
        ("nvidia/Nemotron-3_5-Lightning", "Nemotron-3_5"),  # no size word: its last path part, 12 characters
        ("meta/Llama-3.3-70B-Instruct", "Llama-3.3-70"),
        ("stand-in-Nano", "stand-in-Nano"),  # the demo's stand-in keeps its name whole: never Nemotron's
        ("stand-in --model stand-in-Super", "stand-in"),
        ("claude", "claude"),
        ("python3 /tmp/repo-forks.py", "repo-forks"),  # a script executor: its name, not its extension
        ("", ""),
        (None, ""),
    ],
)
def test_a_model_id_is_named_in_one_word_by_its_size_or_family_else_its_last_part(model, said):
    assert meter.short(model) == said


def ago(seconds):
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def plan_of(repo, executor=f"nemotron --model {NANO} --model {SUPER}"):
    with Store.open(repo) as store:
        store.set_meta("executor", executor)
        plan.propose(store, [{"id": "ids", "title": "ids", "scope": ["api.py"], "check": "true"}], ALEX)
        plan.start(store, "ids", BOT, repo)


def row(repo, kind, detail, seconds, fork=None, session=None):
    detail = {**detail, "fork": fork} if fork else detail
    with Store.open(repo) as store:
        whose = session or SESSIONS.get(fork, BOT.session_id)
        store.log_node("ids", ago(seconds), kind, "run:nemotron", whose, None, detail)


def look(repo):
    with Store.open(repo) as store:
        return read(store, repo, None)


def test_a_running_leaf_names_the_model_its_usage_rows_say_and_what_they_cost(repo):
    plan_of(repo)
    t = look(repo).tasks["ids"]
    assert (t.model, t.usd) == ("Nano", None)  # before its first turn: the executor's first rung, no dollars
    row(repo, "attempt", {"attempt": 1}, 80)
    row(repo, "usage", {"model": NANO, "calls": 1, "dollars": 0.001, "attempt": 1}, 70)
    row(repo, "usage", {"model": NANO, "calls": 1, "dollars": 0.002, "attempt": 1}, 60)
    t = look(repo).tasks["ids"]
    assert t.model == "Nano" and t.usd == pytest.approx(0.003)
    row(repo, "model", {"attempt": 2, "model": SUPER, "from": NANO, "why": "attempt 1 refused"}, 50)
    t = look(repo).tasks["ids"]
    assert t.model == "Super"  # the ladder's next rung, named before its first turn
    row(repo, "usage", {"model": SUPER, "calls": 1, "dollars": 0.01, "attempt": 2}, 40)
    t = look(repo).tasks["ids"]
    assert t.model == "Super" and t.usd == pytest.approx(0.013)  # the hold's attempts together


def test_each_fork_names_its_own_model_and_dollars_from_its_sessions_rows_else_what_it_runs_with(repo):
    plan_of(repo)
    withs = {"a": "nemotron", "b": "nemotron", "c": "claude:opus"}
    row(repo, "forked", {"forks": ["a", "b", "c"], "of": 3, "first": False, "with": withs,
                         "sessions": SESSIONS}, 90)  # fmt: skip
    for letter in "abc":
        row(repo, "attempt", {"attempt": 1, "of": 3}, 80, letter)
    t = look(repo).tasks["ids"]
    # a and b run the executor itself: its first rung; c's `with` names its model
    assert [f.model for f in t.forks] == ["Nano", "Nano", "Opus"]
    assert [f.usd for f in t.forks] == [None, None, None] and t.model == "" and t.usd is None
    row(repo, "usage", {"model": NANO, "calls": 1, "dollars": 0.001, "attempt": 1}, 70, "a")
    row(repo, "usage", {"model": NANO, "calls": 1, "dollars": 0.001, "attempt": 1}, 65, "b")
    row(repo, "usage", {"model": "claude-opus-5-5", "calls": 1, "dollars": 0.05, "attempt": 1}, 60, "c")
    row(repo, "fork", {"of": 3, "state": "passed", "why": "", "lines": 4, "attempts": 1, "dollars": 0.002},
        30, "b")  # fmt: skip
    t = look(repo).tasks["ids"]
    a, b, c = t.forks
    assert (a.model, b.model, c.model) == ("Nano", "Nano", "Opus")
    assert a.usd == pytest.approx(0.001) and b.usd == pytest.approx(0.001) and c.usd == pytest.approx(0.05)
    assert t.usd == pytest.approx(0.052) and t.model == ""  # three models: the forks' lines say each
    row(repo, "fork", {"of": 3, "state": "gave up", "why": "x", "lines": 0, "attempts": 1, "dollars": 0.07},
        20, "c")  # fmt: skip
    with Store.open(repo) as store:  # c's usage rows gone: its last fork row's dollars stand
        store.conn.execute("DELETE FROM node_log WHERE kind = 'usage' AND session_id = ?", (SESSIONS["c"],))
    c = look(repo).tasks["ids"].forks[2]
    assert c.model == "Opus" and c.usd == pytest.approx(0.07)
    with Store.open(repo) as store:  # a new hold, forked with commands of the person's choosing
        plan.release(store, "ids", BOT, why="stuck")
        plan.start(store, "ids", BOT, repo)
    row(repo, "forked", {"forks": ["a", "b"], "of": 2, "with": {"a": "python agent.py", "b": "codex"},
                         "sessions": SESSIONS}, 5)  # fmt: skip
    assert [f.model for f in look(repo).tasks["ids"].forks] == ["agent", "Codex"]  # a command: its script


def test_the_details_forks_table_names_the_model_a_forks_rows_say_when_its_with_does_not(repo):
    from graphene_map.cockpit.details import forks_text

    plan_of(repo)
    withs = {"a": "nemotron", "b": "claude:opus", "c": "codex"}
    row(repo, "forked", {"forks": ["a", "b", "c"], "of": 3, "first": False, "with": withs,
                         "sessions": SESSIONS}, 90)  # fmt: skip
    row(repo, "usage", {"model": NANO, "calls": 1, "dollars": 0.001, "attempt": 1}, 70, "a")
    row(repo, "usage", {"model": "claude-opus-5-5", "calls": 1, "dollars": 0.05, "attempt": 1}, 60, "b")
    with Store.open(repo) as store:  # the title, the header, then a row a fork
        table = [line.split() for line in forks_text(store, "ids", 120).plain.splitlines()[2:5]]
    assert table[0][:2] == ["a", "nemotron"] and table[0][2:4] == ["(Nano)", "running"]  # its rows name it
    assert table[1][:3] == ["b", "claude:opus", "running"]  # the spec names it already: said once
    assert table[2][:3] == ["c", "codex", "running"]  # no row yet: as the forked row said


def test_forks_that_share_one_model_give_the_task_that_model(repo):
    plan_of(repo)
    row(repo, "forked", {"forks": ["a", "b"], "of": 2, "with": {"a": "nemotron", "b": "nemotron"},
                         "sessions": SESSIONS}, 90)  # fmt: skip
    row(repo, "usage", {"model": NANO, "calls": 1, "dollars": 0.001, "attempt": 1}, 70, "a")
    row(repo, "usage", {"model": NANO, "calls": 1, "dollars": 0.001, "attempt": 1}, 65, "b")
    assert look(repo).tasks["ids"].model == "Nano"


def test_in_a_replay_of_the_stand_in_the_names_stay_the_stand_ins(repo):
    """demo.load rewrites a stand-in recording's `Nemotron-3-Nano-fake` to `stand-in-Nano` and `nemotron`
    to `stand-in`: the rows read must say the stand-in, never Nemotron."""
    plan_of(repo, "stand-in --model stand-in-Nano --model stand-in-Super")
    assert look(repo).tasks["ids"].model == "stand-in-Nano"  # the executor's first rung, before its rows
    row(repo, "usage", {"model": "stand-in-Super", "calls": 1, "dollars": 0.0, "attempt": 1}, 70)
    assert look(repo).tasks["ids"].model == "stand-in-Super"


def test_a_new_hold_reads_its_own_rows_not_the_last_holds(repo):
    plan_of(repo)
    row(repo, "usage", {"model": SUPER, "calls": 1, "dollars": 0.5, "attempt": 1}, 70)
    with Store.open(repo) as store:
        plan.release(store, "ids", BOT, why="stuck")
        plan.start(store, "ids", BOT, repo)
    t = look(repo).tasks["ids"]
    assert (t.model, t.usd) == ("Nano", None)


def test_the_envelope_is_read_only_while_auto_is_on(repo):
    plan_of(repo)
    assert look(repo).auto is None
    with Store.open(repo) as store:
        store.set_meta("settings:auto", "on")
        store.set_meta("settings:budget", "2")
        store.set_meta("settings:tasks", "12")
    a = look(repo).auto
    assert a == {"round": 1, "rounds": 2, "stage": "", "spent": None, "budget": 2.0, "check": None, "why": "",
                 "tasks": 0, "of": 12}  # fmt: skip
    with Store.open(repo) as store:
        store.log_node("*", ago(50), "auto", "graphene auto", None, None,
                       {"round": 2, "rounds": 3, "stage": "running", "spent": 0.42, "budget": 2.0,
                        "check": "fail", "why": ""})  # fmt: skip
        store.log_node("ids", ago(40), "accepted", "graphene auto", None, None, {"by": "auto", "round": 1})
        store.log_node("ids", ago(39), "accepted", "alex", None, None, {})
    a = look(repo).auto
    assert (a["round"], a["rounds"], a["stage"], a["spent"], a["tasks"]) == (2, 3, "running", 0.42, 1)
    with Store.open(repo) as store:  # auto went off and on again: the count starts over
        store.log_node("*", ago(30), "settings", "alex", None, None, {"changed": {"auto": ["on", "off"]}})
        store.log_node("*", ago(20), "settings", "alex", None, None, {"changed": {"auto": ["off", "on"]}})
    assert look(repo).auto["tasks"] == 0
    with Store.open(repo) as store:
        store.log_node("ids", ago(10), "accepted", "graphene auto", None, None, {"by": "auto"})
        store.log_node("*", ago(5), "auto", "graphene auto", None, None,
                       {"round": 3, "rounds": 3, "stage": "waits", "spent": 1.0, "budget": None,
                        "check": "fail", "why": "the goal's check is red  after 3 rounds"})  # fmt: skip
    a = look(repo).auto
    assert a["tasks"] == 1 and a["stage"] == "waits" and a["why"] == "the goal's check is red after 3 rounds"
    assert a["budget"] == 2.0  # the round says none: the setting's
    with Store.open(repo) as store:
        store.set_meta("settings:auto", "off")
    assert look(repo).auto is None
