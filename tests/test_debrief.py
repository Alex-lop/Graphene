"""The debrief: golden markdown for a fixed session, the terminal card, JSON round trip, selection."""

import io
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rich.console import Console

from graphene_debrief.debrief import (
    build_debrief,
    coverage_line,
    file_rows,
    from_json,
    parse_since,
    print_card,
    print_sessions,
    render_card,
    select_sessions,
    to_json,
)
from graphene_debrief.model import Prompt, Session, ToolEvent
from graphene_debrief.store import Store

GOLDEN = Path(__file__).parent / "fixtures" / "debrief_golden.md"  # the card, as markdown
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


REGENERATE = "run `uv run python tests/test_debrief.py` to regenerate after a deliberate change"


def test_golden_default_render(store, tmp_path):
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    rendered = render_card(debrief)
    assert rendered == GOLDEN.read_text(), REGENERATE
    assert (
        "unrequested" not in rendered and "Not what you asked for" not in rendered
    )  # the test twin is in scope
    assert (
        "failed Bash:" not in rendered and "cat missing.txt" not in rendered
    )  # failures are one summary line
    assert "- 2 tool failures (2 Bash)" in rendered
    assert "- reverted: `README.md` (prompt 3)" in rendered
    assert "- check `uv run pytest -q` failed and was rerun under prompt 1: passed" in rendered
    assert len(rendered.splitlines()) < 25


def terminal(width: int = 80) -> Console:
    return Console(width=width, record=True, force_terminal=True)


def test_the_terminal_card_shows_what_the_markdown_card_shows(store, tmp_path):
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    console = terminal()
    print_card(console, debrief)
    text = console.export_text()
    assert text.splitlines()[0].startswith("Session sess-gol")
    assert "3 prompts" in text and "3 files" in text and "+7" in text and "−0" in text
    for row in file_rows(debrief):
        assert row["path"] in text
        if row["effect"] != "reverted":
            assert f"+{row['added']}" in text and f"−{row['removed']}" in text
    assert "2 tool failures (2 Bash)" in text  # failures stay one line
    assert "/home/dev/notes/graphene.md" in text
    assert "graphene why <path>" in text


def test_the_terminal_card_fits_forty_rows_at_eighty_columns(tmp_path):
    with Store.open(tmp_path) as s:
        s.upsert_session(Session(id="wide", repo="/repo", started_at=ts(0), ended_at=ts(50)))
        s.add_prompt(Prompt("p1", "wide", 1, ts(1), "build all of it"))
        for i in range(30):
            path = f"src/graphene_debrief/generated/module_number_{i:02d}/handler.py"
            s.add_event(
                ToolEvent(
                    f"w{i}",
                    "wide",
                    "p1",
                    ts(2, i),
                    "Write",
                    {"file_path": path},
                    {"type": "create", "content": "x\n" * (i + 1)},
                    True,
                    file_path=path,
                    old_content=None,
                    new_content="x\n" * (i + 1),
                )
            )
        debrief = build_debrief(s, ["wide"], tmp_path, now=NOW)
    debrief.commits = [
        f"{i:07x} a commit subject long enough to run past eighty columns {i}" for i in range(24)
    ]
    console = terminal()
    print_card(console, debrief)
    lines = console.export_text().splitlines()
    assert len(lines) <= 40, "\n".join(lines)
    assert max(len(line) for line in lines) <= 80
    assert "… 10 more; graphene why <path> for any" in "\n".join(lines)
    assert "… 19 more" in "\n".join(lines)


def test_the_sessions_list_is_columns_not_a_table():
    console = terminal()
    print_sessions(
        console,
        [
            ("11111111", "backfill", "2026-03-01 09:00", "2026-03-01 10:30", 11, "12: 9/2/1"),
            ("22222222", "hooks", "2026-03-02 09:00", "running", 140, "-"),
        ],
        "+0000",
    )
    lines = console.export_text().splitlines()
    assert lines[0].split() == ["session", "source", "started", "+0000", "ended", "calls", "coverage"]
    assert lines[1].rstrip().endswith("12: 9/2/1") and lines[3].startswith("coverage = committed files:")
    lines = lines[:3]
    assert max(len(line) for line in lines) <= 80  # no wrapping at eighty columns
    assert not any(char in "\n".join(lines) for char in "─│┌┐└┘━┃")
    assert lines[1].index("backfill") == lines[2].index("hooks")  # columns line up
    assert lines[2].split()[-2:] == ["140", "-"]


def test_no_color_leaves_no_escape_codes(store, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=True)
    print_card(console, build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW))
    assert "\x1b" not in out.getvalue()
    assert "Files changed" in out.getvalue()  # same card, no colour


def denial(eid, pid, when, tool="Bash", reason="Irreversible Local Destruction"):
    error = (
        f"Permission for this action was denied by the Claude Code auto mode classifier. Reason: [{reason}]. "
        "If you have other tasks that don't depend on this action, continue working on those."
    )
    return ToolEvent(
        eid, "sess-golden-1", pid, when, tool, {"command": "rm -rf build"}, {"error": error}, False
    )


def test_failure_summary_groups_refusals(store, tmp_path):
    store.add_event(denial("d1", "p1", ts(6)))
    store.add_event(denial("d2", "p1", ts(7)))
    store.add_event(denial("d3", "p2", ts(43), reason="Credential Materialization"))
    store.add_event(
        ToolEvent(
            "d4",
            "sess-golden-1",
            "p2",
            ts(44),
            "AskUserQuestion",
            {"questions": []},
            "Error: The user doesn't want to proceed with this tool use.",
            False,
        )
    )
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    assert debrief.failure_summary == {"total": 6, "by_tool": {"Bash": 5, "AskUserQuestion": 1}, "denials": 4}
    card = render_card(debrief)
    assert "- 6 tool failures (5 Bash, 1 AskUserQuestion; 4 refused before running)" in card
    assert "classifier" not in card and "rm -rf" not in card  # the reasons stay in --json


def test_card_omits_sections_with_nothing_in_them(tmp_path):
    with Store.open(tmp_path) as s:
        s.upsert_session(
            Session(id="quiet", repo="/repo", started_at=ts(0), ended_at=ts(30), source="backfill")
        )
        s.add_prompt(Prompt("p1", "quiet", 1, ts(1), "add a.py"))
        s.add_event(
            ToolEvent(
                "w",
                "quiet",
                "p1",
                ts(2),
                "Write",
                {"file_path": "a.py", "content": "x\n"},
                {"type": "create", "content": "x\n"},
                True,
                file_path="a.py",
                old_content=None,
                new_content="x\n",
            )
        )
        card = render_card(build_debrief(s, ["quiet"], tmp_path, now=NOW))
    assert "Abandoned" not in card and "Not what you asked for" not in card and "None" not in card
    assert "**Commits during the session:** none" in card
    assert "- `a.py` created +1/−0" in card
    assert card.rstrip().endswith("for one line.")


def test_card_caps_the_file_list(tmp_path):
    with Store.open(tmp_path) as s:
        s.upsert_session(
            Session(id="big", repo="/repo", started_at=ts(0), ended_at=ts(30), source="backfill")
        )
        s.add_prompt(Prompt("p1", "big", 1, ts(1), "generate everything"))
        for i in range(35):
            s.add_event(
                ToolEvent(
                    f"w{i}",
                    "big",
                    "p1",
                    ts(2, i),
                    "Write",
                    {"file_path": f"gen/f{i:02d}.py"},
                    {"type": "create", "content": "x\n" * (i + 1)},
                    True,
                    file_path=f"gen/f{i:02d}.py",
                    old_content=None,
                    new_content="x\n" * (i + 1),
                )
            )
        debrief = build_debrief(s, ["big"], tmp_path, now=NOW)
    card = render_card(debrief)
    assert card.count("- `gen/") == 30
    assert "- … 5 more; `graphene why <path>` for any of them" in card
    lines = card.splitlines()
    assert lines[lines.index("**Files changed**") + 1] == "- `gen/f34.py` created +35/−0"  # biggest first
    assert render_card(debrief, limit=100).count("- `gen/") == 35


def test_file_rows_net_effect(store, tmp_path):
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    rows = {r["path"]: r for r in file_rows(debrief)}
    assert rows["app/hello.py"] == {"path": "app/hello.py", "effect": "created", "added": 2, "removed": 0}
    assert rows["README.md"]["effect"] == "reverted"
    assert rows["tests/test_hello.py"]["effect"] == "created"


def test_json_round_trip(store, tmp_path):
    debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    text = to_json(debrief)
    assert from_json(text) == debrief
    assert render_card(from_json(text)) == render_card(debrief)


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
        assert select_sessions(store, now=NOW) == ["ccc-3"]  # nobody did anything: the most recent session
        store.add_event(
            ToolEvent("r1", "aaa-1", None, "2026-02-28T08:30:00.000Z", "Read", {"file_path": "/r/a"})
        )
        assert select_sessions(store, now=NOW) == ["aaa-1"]  # the latest that made a call at all
        for sid, when in (("bbb-2", "2026-03-01T09:00:00.000Z"), ("ccc-3", "2026-03-01T11:40:00.000Z")):
            write = ToolEvent("w1", sid, None, when, "Write", {"file_path": "/r/a.py"}, file_path="a.py")
            store.add_event(write)
        assert select_sessions(store, now=NOW) == ["ccc-3"]  # no run yet: the latest that did something
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
        store.upsert_session(Session(id="ddd-4", repo="/r", started_at="2026-03-01T13:30:00.000Z"))
        assert select_sessions(store, now=NOW) == [
            "ccc-3"
        ]  # a newer session that did nothing is not the card


def test_the_card_prints_coverage_as_counts_never_one_number(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
    import make_run_fixture as run

    with Store.open(tmp_path) as store:
        run.load(store)
        debrief = build_debrief(store, [run.S1], tmp_path, now=NOW)
    want = (
        "12 committed files · 9 traced to a recorded write (6 edit, 3 shell) · 2 only to an agent's commit"
        " · 1 to nothing (1 committed in the window by no identifiable agent)"
    )
    assert coverage_line(debrief.coverage) == want and f"**Coverage:** {want}" in render_card(debrief)
    console = terminal()
    print_card(console, debrief)
    assert "coverage 12 committed files" in " ".join(console.export_text().split())
    assert "%" not in want and coverage_line({}) == ""


def test_parse_since_rejects_garbage():
    with pytest.raises(ValueError):
        parse_since("yesterday", NOW)
    assert parse_since("90m", NOW) == "2026-03-01T10:30:00.000Z"


if __name__ == "__main__":  # regenerate the golden file after a deliberate rendering change
    import tempfile

    with Store.open(Path(tempfile.mkdtemp())) as s:
        seed_golden(s)
        debrief = build_debrief(s, ["sess-golden-1"], Path(tempfile.mkdtemp()), now=NOW)
        GOLDEN.write_text(render_card(debrief))
    print(f"wrote {GOLDEN}")


def test_changes_before_the_first_prompt_get_their_own_block(tmp_path):
    with Store.open(tmp_path) as store:
        seed_golden(store)
        store.add_event(
            ToolEvent(
                "e0",
                "sess-golden-1",
                None,
                "2026-03-01T08:59:00.000Z",
                "Write",
                {"file_path": "early.py", "content": "x\n"},
                {"type": "create", "content": "x\n"},
                True,
                file_path="early.py",
                old_content=None,
                new_content="x\n",
            )
        )
        debrief = build_debrief(store, ["sess-golden-1"], tmp_path, now=NOW)
    first = debrief.prompts[0]
    assert (first.ordinal, [f.path for f in first.files], first.files[0].unrequested) == (
        0,
        ["early.py"],
        False,
    )
    assert debrief.files_changed == 4 and debrief.notes == []
    assert first.files[0].explanation == "Created early.py with 1 lines."


def test_preview_truncation_and_fences():
    from graphene_debrief.debrief import preview

    assert preview("Fix the bug.\n\nIt is in auth.py.") == "Fix the bug.\nIt is in auth.py."
    assert preview("one\ntwo\nthree\nfour") == "one\ntwo\nthree…"
    assert preview("x" * 400).endswith("…") and len(preview("x" * 400)) == 301
    assert preview("see:\n```python\nboom\nmore\nlines") == "see:\n```python\nboom\n```…"


def test_many_outside_paths_collapse_to_directories():
    from graphene_debrief.debrief import outside_summary

    few = ["/home/dev/notes/a.md", "/home/dev/notes/b.md"]
    assert outside_summary(few) == few
    many = [f"/tmp/scratch/review-{i}/t.py" for i in range(20)] + ["/home/dev/.zshrc"]
    assert outside_summary(many) == ["/home/dev/.zshrc", "/tmp/scratch/ (20 files)"]
