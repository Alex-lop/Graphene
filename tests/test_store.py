"""The SQLite store: schema, capping, concurrent writers."""

import json

from graphene_debrief.model import Prompt, Session, ToolEvent
from graphene_debrief.store import RESPONSE_CAP, Store, capped_json


def test_opens_in_wal_mode_with_schema(tmp_path):
    with Store.open(tmp_path) as store:
        assert store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sessions", "prompts", "tool_events", "explanations", "debrief_runs"} <= tables
    assert (tmp_path / ".graphene" / "graphene.db").exists()


def test_two_writers_on_one_database(tmp_path):
    a = Store.open(tmp_path)
    b = Store.open(tmp_path)
    a.upsert_session(Session(id="s", repo="r", started_at="t0"))
    b.add_prompt(Prompt(id="p1", session_id="s", ordinal=b.next_ordinal("s"), timestamp="t1", text="one"))
    a.add_prompt(Prompt(id="p2", session_id="s", ordinal=a.next_ordinal("s"), timestamp="t2", text="two"))
    assert [p.ordinal for p in b.prompts("s")] == [1, 2]
    a.close()
    b.close()


def test_upsert_keeps_first_start_and_fills_blanks(tmp_path):
    with Store.open(tmp_path) as store:
        store.upsert_session(Session(id="s", repo="r", started_at="t0", head_at_start="abc"))
        store.upsert_session(Session(id="s", repo="r", started_at="t9", ended_at="t5", head_at_start=None))
        s = store.session("s")
    assert (s.started_at, s.ended_at, s.head_at_start) == ("t0", "t5", "abc")


def test_event_round_trip_including_unknown_success(tmp_path):
    ev = ToolEvent(
        id="e1",
        session_id="s",
        prompt_id=None,
        timestamp="t",
        tool="Bash",
        input={"command": "ls"},
        response=None,
        success=None,
    )
    with Store.open(tmp_path) as store:
        store.add_event(ev)
        (back,) = store.events("s")
    assert back == ev


def test_response_is_capped():
    big = capped_json({"stdout": "x" * (RESPONSE_CAP + 10), "stderr": "ok"})
    assert len(big) <= RESPONSE_CAP
    assert "chars truncated" in big
    assert json.loads(big)["stderr"] == "ok"
    hopeless = capped_json({"items": ["y" * 10] * 40000})
    assert json.loads(hopeless)["truncated"] is True
    assert capped_json(None) is None
    assert capped_json("Error: boom") == '"Error: boom"'


def test_explanations_and_debrief_runs(tmp_path):
    with Store.open(tmp_path) as store:
        assert store.last_debrief_run() is None
        run = store.add_debrief_run(["s1", "s2"], "t")
        assert store.last_debrief_run() == run
        store.set_explanation("p1", "a.py", "Edited a.py", "null", "t")
        store.set_explanation("p1", "a.py", "Better", "claude", "t2")
        assert store.explanation("p1", "a.py") == ("Better", "claude")
        assert store.explanation("p1", "zzz") is None


def test_delete_session_data_keeps_explanations(tmp_path):
    with Store.open(tmp_path) as store:
        store.upsert_session(Session(id="s", repo="r"))
        store.add_prompt(Prompt(id="p1", session_id="s", ordinal=1, timestamp="t", text="x"))
        store.add_event(
            ToolEvent(id="e", session_id="s", prompt_id="p1", timestamp="t", tool="Bash", input={})
        )
        store.set_explanation("p1", "a.py", "text", "null", "t")
        store.delete_session_data("s")
        assert store.session("s") is None
        assert store.prompts("s") == []
        assert store.events("s") == []
        assert store.explanation("p1", "a.py") == ("text", "null")


def test_ids_are_scoped_to_their_session(tmp_path):
    with Store.open(tmp_path) as store:
        for sid in ("a", "b"):
            store.add_prompt(Prompt("p1", sid, 1, "t", f"{sid} prompt"))
            store.add_event(ToolEvent("e1", sid, "p1", "t", "Bash", {}))
        assert store.prompt("a", "p1").text == "a prompt"
        assert store.prompt("b", "p1").text == "b prompt"
        assert store.prompt("a", "nope") is None
        assert len(store.events("a")) == 1 and len(store.events("b")) == 1
