"""The SQLite store: schema, capping, concurrent writers, and rebuilding an unusable one."""

import io
import json
import re
import sqlite3
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graphene_map.cli import build
from graphene_map.model import Agent, Commit, Prompt, Session, ToolEvent
from graphene_map.sources.claude_code import hook_main
from graphene_map.store import RESPONSE_CAP, SCHEMA_VERSION, Store, capped_json


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
    assert "chars omitted" in big
    assert json.loads(big)["stderr"] == "ok"
    hopeless = capped_json({"items": ["y" * 10] * 40000})
    assert json.loads(hopeless)["truncated"] is True
    assert capped_json(None) is None
    assert capped_json("Error: boom") == '"Error: boom"'


# -- what a call is worth keeping --------------------------------------------------------------


def tool_event(tool: str, tool_input: dict, response: object) -> ToolEvent:
    return ToolEvent(
        id="e1", session_id="s", prompt_id=None, timestamp="t", tool=tool, input=tool_input, response=response
    )


def stored(tmp_path: Path, ev: ToolEvent) -> ToolEvent:
    with Store.open(tmp_path) as store:
        store.add_event(ev)
        (back,) = store.events("s")
    return back


def test_a_read_keeps_the_call_but_not_the_file_it_read(tmp_path):
    back = stored(tmp_path, tool_event("Read", {"file_path": "big.py"}, {"file": {"content": "x" * 100_000}}))
    assert back.response is None
    assert (back.input, back.tool, back.timestamp, back.success) == (
        {"file_path": "big.py"},
        "Read",
        "t",
        True,
    )


def test_bash_output_keeps_its_head_and_its_tail(tmp_path):
    last = "abc1234 the commit that was just made"
    out = "line\n" * 20_000 + last
    back = stored(
        tmp_path,
        tool_event(
            "Bash",
            {"command": "git commit -q -m x && git log --oneline -1"},
            {
                "stdout": out,
                "stderr": "",
                "interrupted": False,
                "gitOperation": {"type": "commit"},
            },
        ),
    )
    kept = back.response["stdout"]
    assert len(kept) < len(out) and kept.startswith("line\nline\n")
    assert kept.endswith(last)  # the SHA is on the last line: attribution reads it there
    assert "chars omitted" in kept
    assert (back.response["interrupted"], back.response["gitOperation"]) == (False, {"type": "commit"})


def test_a_huge_change_list_keeps_its_paths_and_loses_its_hunks(tmp_path):
    diff = {
        "changedFiles": ["src/a.py"],
        "files": [{"filePath": "src/a.py", "hunks": ["h" * RESPONSE_CAP]}],
        "created": [],
        "deleted": [],
        "moreFiles": 3,
        "shared": True,
        "unavailable": False,
    }
    back = stored(
        tmp_path, tool_event("Bash", {"command": "make"}, {"stdout": "z" * 100_000, "bashEditDiff": diff})
    )
    kept = back.response["bashEditDiff"]
    assert kept["files"] == [{"filePath": "src/a.py"}]  # the hunks went, the path stayed
    assert (kept["changedFiles"], kept["moreFiles"], kept["shared"]) == (["src/a.py"], 3, True)
    assert (kept["created"], kept["deleted"], kept["unavailable"]) == ([], [], False)


def test_a_huge_write_keeps_its_path_and_its_content_column(tmp_path):
    content = "def f():\n    pass\n" * 6_000
    ev = tool_event(
        "Write", {"file_path": "src/a.py", "content": content}, {"type": "create", "content": content}
    )
    ev.file_path, ev.new_content = "src/a.py", content
    back = stored(tmp_path, ev)
    assert back.input["file_path"] == "src/a.py"
    assert len(back.input["content"]) < len(content) and "chars omitted" in back.input["content"]
    assert back.new_content == content  # the diff is computed from this column, so it is kept whole


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
def repo(tmp_path, monkeypatch):
    """A git repo, the current directory."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def set_version(db: Path, version: int) -> None:
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {version}")
    conn.close()


def test_a_new_store_records_the_schema_version(tmp_path):
    with Store.open(tmp_path) as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert store.rebuilt_from is None


V1_TABLES = ("sessions", "prompts", "tool_events", "explanations", "debrief_runs")


def downgrade_to_v1(db: Path, version: int = 1) -> None:
    """Turn a current store back into what version 1 wrote: no agents, no commits, no cwd column."""
    conn = sqlite3.connect(db)
    for table in ("agents", "commits", "commit_files", "nodes", "node_log", "plan_meta"):
        conn.execute(f"DROP TABLE {table}")
    conn.execute("ALTER TABLE tool_events DROP COLUMN cwd")
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


@pytest.mark.parametrize("version", [0, 1])  # 0: every store written before versioning
def test_an_older_store_is_migrated_in_place_and_keeps_its_sessions(tmp_path, version):
    with Store.open(tmp_path) as store:
        store.upsert_session(Session(id="hooked", repo=str(tmp_path), source="hook"))
        store.add_event(
            ToolEvent("t1", "hooked", None, "2026-03-01T09:00:00.000Z", "Bash", {"command": "ls"})
        )
    db = tmp_path / ".graphene" / "graphene.db"
    downgrade_to_v1(db, version)
    with Store.open(tmp_path) as store:
        assert store.rebuilt_from is None and list((tmp_path / ".graphene").glob("*.bak")) == []
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert [s.id for s in store.sessions()] == ["hooked"]  # its transcript may be gone: never dropped
        assert [e.id for e in store.events("hooked")] == ["t1"] and store.events("hooked")[0].cwd is None
        tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert tables >= {*V1_TABLES, "agents", "commits", "commit_files", "nodes", "node_log", "plan_meta"}


def test_the_hook_migrates_an_older_store_and_records_the_event(tmp_path):
    (tmp_path / ".git").mkdir()
    Store.open(tmp_path).close()
    downgrade_to_v1(tmp_path / ".graphene" / "graphene.db")
    event = json.dumps({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(tmp_path)})
    assert hook_main(io.StringIO(event), cwd=tmp_path) == 0
    with Store.open(tmp_path) as store:
        assert [s.id for s in store.sessions()] == ["s1"]


def test_agents_fill_in_and_the_first_credit_for_a_commit_stands(tmp_path):
    with Store.open(tmp_path) as store:
        store.upsert_agent(Agent(id="a1", session_id="s", started_at="2026-03-01T09:00:00.000Z"))
        store.upsert_agent(Agent(id="a1", session_id="s", task="write the guide", closing="done"))
        (agent,) = store.agents("s")
        assert (agent.task, agent.closing, agent.started_at) == (
            "write the guide",
            "done",
            "2026-03-01T09:00:00.000Z",
        )
        when = "2026-03-01T09:05:00.000Z"
        store.add_commit(Commit("abc1234", when, "parser", files=[("app/parser.py", "A")]))
        store.add_commit(Commit("abc1234", when, "parser", session_id="s", agent_id="a1", event_id="t9"))
        store.add_commit(Commit("abc1234", when, "parser", session_id="other", agent_id="zz"))
        (commit,) = store.commits_between("2026-03-01T09:00:00.000Z", "2026-03-01T10:00:00.000Z")
        assert (commit.session_id, commit.agent_id, commit.event_id) == ("s", "a1", "t9")
        assert commit.files == [("app/parser.py", "A")]


def test_a_corrupt_store_is_rebuilt_and_still_answers(repo):
    (repo / ".graphene").mkdir()
    (repo / ".graphene" / "graphene.db").write_text("this is not a database")
    result = CliRunner().invoke(build(), ["ui", "--json"])
    output = result.output + result.stderr
    assert result.exit_code == 1 and "Traceback" not in output  # rebuilt empty: nothing to draw yet
    assert (repo / ".graphene" / "graphene.db.corrupt.bak").read_text() == "this is not a database"
    assert "store rebuilt" in output
    for name, extra in (("UserPromptSubmit", {"prompt": "list it"}), ("PostToolUse", {"tool_name": "Bash"})):
        event = {"hook_event_name": name, "session_id": "11111111", "cwd": str(repo), **extra}
        assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=io.StringIO()) == 0
    result = CliRunner().invoke(build(), ["ui", "--json"])
    assert result.exit_code == 0, result.output + result.stderr
    assert "11111111" in result.output  # the rebuilt store records and answers


def test_a_rebuild_never_overwrites_an_earlier_backup(tmp_path):
    (tmp_path / ".graphene").mkdir()
    for n, name in enumerate(("graphene.db.corrupt.bak", "graphene.db.corrupt.2.bak")):
        (tmp_path / ".graphene" / "graphene.db").write_text(f"not a database {n}")
        store = Store.open(tmp_path)
        store.close()
        assert store.rebuilt_from == str(Path(".graphene") / name)
        assert (tmp_path / ".graphene" / name).read_text() == f"not a database {n}"


def test_the_cli_refuses_a_store_from_a_newer_graphene_in_one_line_and_leaves_it_alone(repo):
    Store.open(repo).close()
    db = repo / ".graphene" / "graphene.db"
    set_version(db, SCHEMA_VERSION + 1)
    result = CliRunner().invoke(build(), [])
    assert result.exit_code == 1 and "Traceback" not in result.output + result.stderr
    assert "written by a newer graphene" in " ".join(result.stderr.split())
    assert list((repo / ".graphene").glob("*.bak")) == []


def test_the_hook_skips_a_store_from_a_newer_graphene_and_leaves_it_alone(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    Store.open(tmp_path).close()
    db = tmp_path / ".graphene" / "graphene.db"
    set_version(db, SCHEMA_VERSION + 1)
    before = db.read_bytes()
    event = json.dumps({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": str(tmp_path)})
    assert hook_main(io.StringIO(event), cwd=tmp_path) == 0
    assert capsys.readouterr().out == ""
    assert db.read_bytes() == before  # not rebuilt, not even written to
    assert list((tmp_path / ".graphene").glob("*.bak")) == []
    log = (tmp_path / ".graphene" / "ingest.log").read_text()
    assert "run graphene" in log and "Traceback" not in log


def test_a_huge_error_keeps_its_ends_instead_of_being_lost_whole(tmp_path):
    error = "permission denied: " + "x" * (2 * RESPONSE_CAP) + " the last line"
    with Store.open(tmp_path) as store:
        store.add_event(
            ToolEvent("f1", "s", None, "2026-03-01T09:00:00.000Z", "Bash", {}, {"error": error}, False)
        )
        kept = store.events("s")[0].response["error"]
    assert kept.startswith("permission denied") and kept.endswith("the last line") and len(kept) < 10_000


def test_values_are_bound_to_plain_question_marks_only(tmp_path, monkeypatch):
    """Python 3.12.0 to 3.12.3 warn when a sequence is bound to a numbered ?1, and 3.14 refuses one
    bound to a named :x. A plain ? is read the same way by every Python the package allows."""
    bound = []

    class Recording(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):
            if parameters and not isinstance(parameters, dict):
                bound.append(sql)
            return super().execute(sql, parameters)

    connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: connect(*a, factory=Recording, **k))
    with Store.open(tmp_path) as store:
        store.put_node({"id": "a", "state": "open"})
        store.put_node({"id": "b", "state": "open"})
        store.put_node({"id": "a", "state": "done"})
        assert store.node_row("a") == {"id": "a", "state": "done"}
        assert store.node_seqs() == {"a": 1, "b": 2}  # an update keeps the node's place
        assert store.did_something("s") is False
    assert bound and [sql for sql in bound if re.search(r"\?\d|[:@$][A-Za-z_]", sql)] == []
