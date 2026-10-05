"""`graphene plan cover` against the recorded fake: Nano says which leaf carries each clause of the
person's paragraph; only the person's own words are kept, and only those are offered for a leaf."""

import json
import shlex
import subprocess

import pytest
from fake_tokenfactory import Fake
from typer.testing import CliRunner

from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map.cli import build
from graphene_map.nemotron import cover as C
from graphene_map.nemotron import tokenfactory as tf
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
    assert said[1] == "your paragraph, in clauses: 3; the plan carries 2, no leaf carries 1"
    offered = said[2].split("`")[1]
    assert said[2] == (f"1. You said '{SAID}'; no leaf carries it. Take it: `graphene plan cover --take 1` "
                       "puts it at the end of xml-wiring's goal")  # fmt: skip
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
    assert said[1].endswith("no leaf carries 1; dropped, not your words: 1")
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
    assert "no leaf carries 0; set aside before: 1" in again.stdout and "You said" not in again.stdout
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


def test_an_item_of_the_wrong_shape_is_one_line_and_crashes_nothing(repo, fake, monkeypatch):
    from graphene_map.ask import ask, named

    odd = {"clauses": [
        {"text": "Prices are in cents", "leaf": ["prices"], "nearest": None},
        {"text": "Load the XML feed into items", "leaf": None, "nearest": {"x": 1}},
        None, 3, "str", {"text": ["Load"], "leaf": None, "nearest": None},
        {"text": EMPTY, "leaf": None, "nearest": None},
    ]}  # fmt: skip
    fake([nano(odd)])
    said = []
    with planned(repo) as store:
        [u] = C.cover(store, say=said.append)
        assert u["note"] == SAID and u["nearest"] is None
    assert said[1] == "your paragraph, in clauses: 1; the plan carries 0, no leaf carries 1"
    assert said[-1] == "cover: items of its answer that are not a clause, passed over: 6"
    monkeypatch.setenv("GRAPHENE_SHAPE", "cover")
    monkeypatch.setattr(C, "cover", lambda *a: 1 / 0)  # whatever breaks in it, the ask stands
    fake([{"content": f"```plan\n{PLAN}```"}])
    said = []
    with Store.open(repo) as store:
        ask(store, repo, PARAGRAPH, named("nemotron"), say=said.append)
    assert said[-1] == "cover: it broke (ZeroDivisionError: division by zero); the proposal stands"


def test_no_control_character_reaches_the_terminal_or_the_store(repo, fake):
    red = "Prices are \x1b[31min cents‮\x07"
    fake([nano({"clauses": [{"text": red, "leaf": None, "nearest": "prices"}]})])
    said = []
    with planned(repo) as store:
        [u] = C.cover(store, paragraph=f"Load the XML feed. {red}.", say=said.append)
        assert u["note"] == "Prices are [31min cents"
        stored = json.dumps([e["detail"] for e in store.node_log("*", ("covered", "uncovered"))])
    shown = "\n".join(said)
    assert not any(ch in shown + json.loads(json.dumps(stored)) for ch in "\x1b‮\x07")
    assert "You said 'Prices are [31min cents'" in shown


def test_a_piece_of_a_clause_is_never_offered_as_the_persons_words(repo, fake):
    words = "Load the XML feed into items and keep its order. Prices are in cents, so do not multiply them."
    fake([nano({"clauses": [
        {"text": t, "leaf": None, "nearest": "prices"}
        for t in ("multiply them", "a", "Load the XML feed", "Prices are in cent", "rices are in cents",
                  "and keep its order", "Prices are in cents", "so do not multiply them", "not multiply them")
    ]})])  # fmt: skip
    said = []
    with planned(repo) as store:
        got = [u["note"] for u in C.cover(store, paragraph=words, say=said.append)]
        [read] = store.node_log("*", ("covered",))
    assert got == ["keep its order", "Prices are in cents", "do not multiply them"]  # the last is a piece
    assert read["detail"]["pieces"] == 6 and read["detail"]["dropped"] == []
    assert said[1].endswith("no leaf carries 3; dropped, a piece of a clause: 6")


def test_taking_a_clause_keeps_an_edit_made_since_the_cover_ran(repo, fake):
    fake([nano(ANSWER)])
    with planned(repo) as store:
        C.cover(store, say=lambda s: None)
    edited = person("node", "set", "xml-wiring", "--goal", "read the XML feed into items, in order")
    assert edited.exit_code == 0, edited.output
    took = person("plan", "cover", "--take", "1")
    assert took.exit_code == 0, took.output
    with Store.open(repo) as store:
        assert P.get(store, "xml-wiring").goal == f"read the XML feed into items, in order; {SAID}"
    again = person("plan", "cover", "--take", "1")
    assert again.exit_code == 1 and "carries it already" in again.output


def test_a_key_shaped_string_never_lands_in_the_store_or_the_output_and_a_long_answer_is_capped(repo, fake):
    shaped = "sk-AbCdEfGh1234567890IjKlMnOp"
    words = f"Use the token {shaped} for the feed. Prices are in cents."
    invented = [{"text": f"NEBIUS_API_KEY={shaped}", "leaf": None, "nearest": None}]
    invented += [{"text": f"made up {k} " + "x" * 400, "leaf": None, "nearest": None} for k in range(5000)]
    f = fake([nano({"clauses": [{"text": f"Use the token {shaped} for the feed", "leaf": None,
                                 "nearest": "prices"}, *invented]})])  # fmt: skip
    said = []
    with planned(repo) as store:
        C.cover(store, paragraph=words, say=said.append)
        rows = json.dumps([e["detail"] for e in store.node_log("*", ("covered", "uncovered"))])
    assert shaped[3:] not in f.requests[0]["messages"][1]["content"]  # nor is it sent
    assert shaped[3:] not in rows and shaped[3:] not in "\n".join(said)
    assert "Use the token [removed: shaped like a key] for the feed" in "\n".join(said)
    assert len(rows) < 20_000 and "dropped, not your words: 5001" in said[1]


def test_the_screen_and_dismiss_number_the_clauses_alike(repo, fake):
    three = {"clauses": [{"text": t, "leaf": None, "nearest": "prices"} for t in
                         ("Load the XML feed into items", "Prices are in cents", EMPTY)]}  # fmt: skip
    fake([nano(three)])
    with planned(repo) as store:
        C.cover(store, say=lambda s: None)
    assert person("plan", "cover", "--dismiss", "1").exit_code == 0
    with Store.open(repo) as store:
        assert [(u["n"], u["note"]) for u in C.standing(store)] == [(2, "Prices are in cents"), (3, SAID)]
    again = person("plan", "cover", "--dismiss", "1")
    assert again.exit_code == 1 and "set aside already" in again.output
    assert person("plan", "cover", "--dismiss", "2").exit_code == 0
    with Store.open(repo) as store:
        assert [u["n"] for u in C.standing(store)] == [3]


def test_a_failing_nano_is_asked_once_and_waits_for_nothing(repo, fake, monkeypatch):
    waited = []
    monkeypatch.setattr(tf, "_sleep", waited.append)
    monkeypatch.setenv("GRAPHENE_SHAPE", "cover")
    f = fake([500] * 6)
    said = []
    with planned(repo) as store:
        C.after_ask(store, PARAGRAPH, said.append)
        assert store.node_log("*", ("covered", "usage")) == []
    assert len(f.requests) == 1 and waited == []
    [line] = said
    assert line.startswith("cover: Nano could not be asked: Token Factory answered 500")


def test_the_plans_record_bills_the_cover_apart_from_the_planner(repo, fake):
    fake([nano(ANSWER)])
    with planned(repo) as store:
        C.cover(store, say=lambda s: None)
    record = person("plan", "record")
    assert record.exit_code == 0, record.output
    assert "the planner's bill" not in record.stdout and "cover:nemotron's bill: $" in record.stdout


def test_the_standing_clauses_go_on_the_board_as_notes_about_their_leaf(repo, fake):
    three = {"clauses": [
        {"text": "Load the XML feed into items", "leaf": None, "nearest": "xml-wiring"},
        {"text": "Prices are in cents", "leaf": None, "nearest": "prices"},
        {"text": EMPTY, "leaf": None, "nearest": None},
    ]}  # fmt: skip
    fake([nano(three)])
    put = []

    def add(store, kind, text, who, default=None, then=None, options=None, about=None):  # board.add's shape
        if about == "prices":
            raise P.Refused("prices is not a node in the plan")
        put.append({"kind": kind, "text": text, "by": who.label, "agent": not who.person, "default": default,
                    "then": then, "about": about})  # fmt: skip
        return put[-1]

    with planned(repo) as store:
        C.cover(store, say=lambda s: None)
        said = C.to_board(store, add)
        assert put[0] == {
            "kind": "note", "by": "shaper:nemotron", "agent": True, "about": "xml-wiring",
            "then": ['goal xml-wiring + "Load the XML feed into items"'],
            "text": f"you said 'Load the XML feed into items'; no leaf carries it{C.STAND_IN}",
            "default": "add it to the end of xml-wiring's goal",
        }  # fmt: skip
        assert put[1]["about"] is None and put[1]["default"] == "add it to a leaf in `graphene plan edit`"
        assert said[0] == "cover: put on the board: 2"
        assert said[1] == "cover: 'Prices are in cents' is not on the board: prices is not a node in the plan"
        store.set_meta("board", json.dumps(put))
        put.clear()
        assert C.to_board(store, add) == ["cover: put on the board: 0; on the board already: 2", said[1]]
        store.set_meta("board", "[]")
        took = C.take(store, C.standing(store)[0], P.Caller("alex", True))
        assert took.startswith("xml-wiring is now revision 2")
        put.clear()
        C.to_board(store, add)
        assert [p["about"] for p in put] == [None]  # taken: its leaf carries it now


def test_the_cover_flag_puts_the_uncovered_clauses_on_the_board_after_an_ask(
    repo, fake, monkeypatch, tmp_path
):
    """GRAPHENE_SHAPE=cover: after `graphene ask`, each clause no leaf carries is an item by
    shaper:nemotron, said to be read by a stand-in here; taking it ends its leaf's goal with the clause."""
    import sys

    from graphene_map import board as B
    from graphene_map.ask import ask

    script = tmp_path / "planner.py"
    block = "```plan\\n? wire the reader  [xml-wiring]\\n    scope: app.py\\n    check: true\\n```"
    script.write_text(f'print("{block}")')
    clause = {"text": "Load the XML feed into items", "leaf": None, "nearest": "xml-wiring"}
    fake([nano({"clauses": [clause]})])
    monkeypatch.setenv("GRAPHENE_SHAPE", "cover")
    said = []
    with Store.open(repo) as store:
        ask(store, repo, "Load the XML feed into items.", f"{sys.executable} {script}", say=said.append)
        [item] = B.items(store)
        assert (item["by"], item["about"]) == ("shaper:nemotron", "xml-wiring")
        assert item["text"].endswith(C.STAND_IN) and "cover: put on the board: 1" in said
        B.take(store, item["id"], P.Caller("alex", True))
        assert P.get(store, "xml-wiring").goal == "Load the XML feed into items"
