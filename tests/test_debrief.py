"""The debrief: golden markdown for a fixed session, JSON round trip, session selection."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene_debrief.debrief import (
    build_debrief,
    from_json,
    parse_since,
    render_markdown,
    select_sessions,
    to_json,
)
from graphene_debrief.model import Prompt, Session, ToolEvent
from graphene_debrief.store import Store

GOLDEN = Path(__file__).parent / "fixtures" / "debrief_golden.md"
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
HELLO_V1 = 'def greet(name):\n    return f"hi {name}"\n'
HELLO_V2 = 'def greet(name):\n    return f"hello {name}"\n'
HELLO_LOUD = 'def greet(name):\n    return f"hello {name}".upper()\n'
TEST_V1 = "from app.hello import greet\n\n\ndef test_greet():\n    assert greet('x') == 'hello x'\n"


def ts(minute: int, second: int = 0) -> str:
    return f"2026-03-01T09:{minute:02d}:{second:02d}.000Z"


def write(store, eid, pid, path, content, when, old=None):
    kind = "create" if old is None else "update"
    store.add_event(
        ToolEvent(
            eid,
            "sess-golden-1",
            pid,
            when,
            "Write",
            {"file_path": path, "content": content},
            {"type": kind, "filePath": path, "content": content, "originalFile": old},
            True,
            file_path=path,
            old_content=old,
            new_content=content,
        )
    )


def edit(store, eid, pid, path, old, new, when):
    store.add_event(
        ToolEvent(
            eid,
            "sess-golden-1",
            pid,
            when,
            "Edit",
            {"file_path": path},
            {"originalFile": old},
            True,
            file_path=path,
            old_content=old,
            new_content=new,
        )
    )


def bash(store, eid, pid, command, when, ok=True, error=None):
    response = {"stdout": "ok"} if ok else {"error": error, "is_interrupt": False}
    store.add_event(ToolEvent(eid, "sess-golden-1", pid, when, "Bash", {"command": command}, response, ok))


def seed_golden(store: Store) -> None:
    store.upsert_session(
        Session(
            id="sess-golden-1",
            repo="/repo",
            started_at=ts(0),
            ended_at="2026-03-01T10:30:00.000Z",
            source="backfill",
        )
    )
    store.add_prompt(
        Prompt(
            "p1",
            "sess-golden-1",
            1,
            ts(0, 5),
            "Add a greet function to app/hello.py and a test for it.\nKeep it tiny.",
        )
    )
    store.add_prompt(
        Prompt("p2", "sess-golden-1", 2, ts(40), "Try making greet shout in hello.py, then put it back.")
    )
    store.add_prompt(
        Prompt(
            "p3",
            "sess-golden-1",
            3,
            ts(50),
            "Rename the title in README.md.\n\nActually no, undo that.\nAlso note it somewhere.\nThanks!",
        )
    )
    write(store, "e1", "p1", "app/hello.py", HELLO_V1, ts(1))
    write(store, "e2", "p1", "tests/test_hello.py", TEST_V1, ts(2))
    bash(
        store,
        "e3",
        "p1",
        "uv run pytest -q",
        ts(3),
        ok=False,
        error="Exit code 1\nFAILED tests/test_hello.py::test_greet - AssertionError\n1 failed in 0.02s",
    )
    edit(store, "e4", "p1", "app/hello.py", HELLO_V1, HELLO_V2, ts(4))
    bash(store, "e5", "p1", "uv run pytest -q", ts(5))
    edit(store, "e6", "p2", "app/hello.py", HELLO_V2, HELLO_LOUD, ts(41))
    edit(store, "e7", "p2", "app/hello.py", HELLO_LOUD, HELLO_V2, ts(42))
    edit(store, "e8", "p3", "README.md", "# Old title\n", "# New title\n", ts(51))
    edit(store, "e9", "p3", "README.md", "# New title\n", "# Old title\n", ts(52))
    write(store, "e10", "p3", "/home/dev/notes/graphene.md", "note\n", ts(53))
    bash(
        store,
        "e11",
        "p3",
        "cat missing.txt",
        ts(54),
        ok=False,
        error="Exit code 1\ncat: missing.txt: No such file",
    )


@pytest.fixture
def store(tmp_path):
    with Store.open(tmp_path) as s:
        seed_golden(s)
        yield s


def test_golden_markdown(store, tmp_path):
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    rendered = render_markdown(debrief)
    assert rendered == GOLDEN.read_text(), (
        "run `uv run python tests/test_debrief.py` to regenerate after a deliberate change"
    )


def test_full_expands_prompts(store, tmp_path):
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    short, full = render_markdown(debrief), render_markdown(debrief, full=True)
    assert "> Thanks!" in full and "> Thanks!" not in short
    assert "Also note it somewhere.…" in short


def test_json_round_trip(store, tmp_path):
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    text = to_json(debrief)
    assert from_json(text) == debrief
    assert render_markdown(from_json(text)) == render_markdown(debrief)


def test_select_sessions(tmp_path):
    with Store.open(tmp_path) as store:
        assert select_sessions(store, now=NOW) == []
        store.upsert_session(
            Session(
                id="aaa-1",
                repo="/r",
                started_at="2026-02-28T08:00:00.000Z",
                ended_at="2026-02-28T09:00:00.000Z",
            )
        )
        store.upsert_session(
            Session(
                id="bbb-2",
                repo="/r",
                started_at="2026-03-01T08:00:00.000Z",
                ended_at="2026-03-01T11:00:00.000Z",
            )
        )
        store.upsert_session(Session(id="ccc-3", repo="/r", started_at="2026-03-01T11:30:00.000Z"))
        assert select_sessions(store, now=NOW) == ["ccc-3"]  # no run yet: most recent session
        assert select_sessions(store, "bbb", now=NOW) == ["bbb-2"]
        with pytest.raises(ValueError):
            select_sessions(store, "zzz", now=NOW)
        assert select_sessions(store, since="6h", now=NOW) == ["bbb-2", "ccc-3"]
        assert select_sessions(store, since="2d", now=NOW) == ["aaa-1", "bbb-2", "ccc-3"]
        assert select_sessions(store, since="2026-03-01T11:00:00+00:00", now=NOW) == ["bbb-2", "ccc-3"]
        store.add_debrief_run(["aaa-1", "bbb-2"], "2026-03-01T10:00:00.000Z")
        assert select_sessions(store, now=NOW) == ["bbb-2", "ccc-3"]  # ended after the run, or still open
        store.add_debrief_run(["bbb-2", "ccc-3"], "2026-03-01T13:00:00.000Z")
        assert select_sessions(store, now=NOW) == ["ccc-3"]  # still open, so still fresh


def test_parse_since_rejects_garbage():
    with pytest.raises(ValueError):
        parse_since("yesterday", NOW)
    assert parse_since("90m", NOW) == "2026-03-01T10:30:00.000Z"


if __name__ == "__main__":  # regenerate the golden file after a deliberate rendering change
    import tempfile

    with Store.open(Path(tempfile.mkdtemp())) as s:
        seed_golden(s)
        GOLDEN.write_text(
            render_markdown(build_debrief(s, ["sess-golden-1"], Path(tempfile.mkdtemp()), now=NOW))
        )
    print(f"wrote {GOLDEN}")
