"""The SQLite store: schema, capping, concurrent writers, and rebuilding an unusable one."""

import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_debrief.cli import build
from graphene_debrief.model import Prompt, Session, ToolEvent
from graphene_debrief.sources.claude_code import hook_main, project_dir_name
from graphene_debrief.store import RESPONSE_CAP, SCHEMA_VERSION, Store, capped_json

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_transcript_fixture as fixture  # noqa: E402


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
        assert store.explanation("p1", "a.py") == ("Edited a.py", "null", None)
        store.set_explanation("p1", "a.py", "Better", "claude", "t2", "haiku")
        assert store.explanation("p1", "a.py") == ("Better", "claude", "haiku")
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
        assert store.explanation("p1", "a.py") == ("text", "null", None)


def test_ids_are_scoped_to_their_session(tmp_path):
    with Store.open(tmp_path) as store:
        for sid in ("a", "b"):
            store.add_prompt(Prompt("p1", sid, 1, "t", f"{sid} prompt"))
            store.add_event(ToolEvent("e1", sid, "p1", "t", "Bash", {}))
        assert store.prompt("a", "p1").text == "a prompt"
        assert store.prompt("b", "p1").text == "b prompt"
        assert store.prompt("a", "nope") is None
        assert len(store.events("a")) == 1 and len(store.events("b")) == 1


# -- rebuilding a store this version cannot use ------------------------------------------------


@pytest.fixture
def repo_with_transcripts(tmp_path, monkeypatch):
    """A git repo, current directory, with the synthetic transcript under CLAUDE_CONFIG_DIR."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setattr(fixture, "CWD", str(tmp_path))
    target = tmp_path / "claude" / "projects" / project_dir_name(tmp_path)
    for path, text in fixture.render().items():
        out = target / path.relative_to(fixture.OUT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    return tmp_path


def set_version(db: Path, version: int) -> None:
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {version}")
    conn.close()


def test_a_new_store_records_the_schema_version(tmp_path):
    with Store.open(tmp_path) as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert store.rebuilt_from is None


def test_a_store_from_an_older_schema_is_rebuilt_and_backfilled(repo_with_transcripts):
    repo = repo_with_transcripts
    Store.open(repo).close()
    set_version(repo / ".graphene" / "graphene.db", 0)  # every store written before versioning
    result = CliRunner().invoke(build(), [])
    output = result.output + result.stderr
    assert result.exit_code == 0, output
    assert (repo / ".graphene" / "graphene.db.v0.bak").exists()
    assert "store rebuilt" in output and ".graphene/graphene.db.v0.bak" in output
    assert "loaded 1 session" in output
    assert "Session 11111111" in result.output  # the card, from the rebuilt store
    with Store.open(repo) as store:
        assert len(store.sessions()) == 1
        assert store.rebuilt_from is None  # and now it opens normally


def test_a_corrupt_store_is_rebuilt_and_still_answers(repo_with_transcripts):
    repo = repo_with_transcripts
    (repo / ".graphene").mkdir()
    (repo / ".graphene" / "graphene.db").write_text("this is not a database")
    result = CliRunner().invoke(build(), [])
    output = result.output + result.stderr
    assert result.exit_code == 0, output
    assert (repo / ".graphene" / "graphene.db.corrupt.bak").read_text() == "this is not a database"
    assert "store rebuilt" in output and "Session 11111111" in result.output


def test_a_rebuild_never_overwrites_an_earlier_backup(tmp_path):
    (tmp_path / ".graphene").mkdir()
    for n, name in enumerate(("graphene.db.corrupt.bak", "graphene.db.corrupt.2.bak")):
        (tmp_path / ".graphene" / "graphene.db").write_text(f"not a database {n}")
        store = Store.open(tmp_path)
        store.close()
        assert store.rebuilt_from == str(Path(".graphene") / name)
        assert (tmp_path / ".graphene" / name).read_text() == f"not a database {n}"


def test_the_hook_skips_a_stale_store_instead_of_rebuilding_it(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    Store.open(tmp_path).close()
    db = tmp_path / ".graphene" / "graphene.db"
    set_version(db, SCHEMA_VERSION + 1)
    before = db.read_bytes()
    event = json.dumps({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(tmp_path)})
    assert hook_main(io.StringIO(event), cwd=tmp_path) == 0
    assert capsys.readouterr().out == ""
    assert db.read_bytes() == before  # not rebuilt, not backfilled, not even written to
    assert list((tmp_path / ".graphene").glob("*.bak")) == []
    log = (tmp_path / ".graphene" / "ingest.log").read_text()
    assert "run graphene" in log and "Traceback" not in log
