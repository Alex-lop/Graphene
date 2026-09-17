"""Transcript backfill against the synthetic fixture from tests/fixtures/make_transcript_fixture.py."""

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

from graphene_debrief.model import Session
from graphene_debrief.sources.claude_code import (
    backfill,
    is_prompt,
    parse_transcript,
    project_dir_name,
    transcripts_for,
)
from graphene_debrief.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_transcript_fixture as fixture  # noqa: E402

SID = fixture.SID
ROOT = Path(fixture.CWD)


def test_checked_in_fixture_matches_its_generator():
    for path, text in fixture.render().items():
        assert path.read_text(encoding="utf-8") == text, f"{path} is stale: run the generator"


@pytest.fixture
def projects(tmp_path):
    d = tmp_path / "projects" / project_dir_name(ROOT)
    d.mkdir(parents=True)
    shutil.copy(FIXTURES / "transcripts" / f"{SID}.jsonl", d / f"{SID}.jsonl")
    shutil.copytree(FIXTURES / "transcripts" / SID, d / SID)
    return tmp_path / "projects"


def test_backfill_loads_a_session(tmp_path, projects):
    with Store.open(tmp_path) as store:
        report = backfill(store, ROOT, projects=projects)
        session = store.session(SID)
        prompts = store.prompts(SID)
        events = store.events(SID)
    assert (report.added, report.refreshed, report.skipped, report.other_repo) == ([SID], [], [], [])
    assert (session.source, session.head_at_start, session.repo) == ("backfill", None, str(ROOT))
    assert (session.started_at, session.ended_at) == ("2026-03-01T09:00:01.000Z", "2026-03-01T09:21:31.000Z")
    assert session.transcript_path.endswith(f"{SID}.jsonl")

    assert [(p.id, p.ordinal) for p in prompts] == [("p-1", 1), ("p-2", 2), ("p-3", 3)]
    assert prompts[0].text == "Add a greet function to app/hello.py and a test for it."
    assert prompts[0].timestamp == "2026-03-01T09:00:05.000Z"

    assert [e.id for e in events] == [
        "toolu_w1",
        "toolu_w2",
        "toolu_b1",
        "toolu_e1",
        "toolu_b2",
        "toolu_a1",
        "toolu_s1",
        "toolu_q1",
        "toolu_e2",
        "toolu_e3",
        "toolu_w3",
        "toolu_b3",
    ]
    assert Counter(e.tool for e in events) == {
        "Write": 3,
        "Bash": 4,
        "Edit": 3,
        "Agent": 1,
        "AskUserQuestion": 1,
    }
    assert Counter(e.prompt_id for e in events) == {"p-1": 5, "p-2": 3, "p-3": 4}
    assert [e.id for e in events if e.success is False] == ["toolu_b1", "toolu_q1"]
    assert events[2].response == "Error: Exit code 1\nFAILED tests/test_hello.py::test_greet - AssertionError"
    assert events[4].response["stdout"] == "1 passed in 0.01s"

    files = [(e.id, e.file_path, e.old_content, e.new_content) for e in events if e.file_path]
    assert files == [
        ("toolu_w1", "app/hello.py", None, fixture.HELLO_V1),
        ("toolu_w2", "tests/test_hello.py", None, fixture.TEST),
        ("toolu_e1", "app/hello.py", fixture.HELLO_V1, fixture.HELLO_V2),
        ("toolu_e2", "README.md", fixture.README_OLD, fixture.README_NEW),
        ("toolu_e3", "README.md", fixture.README_NEW, fixture.README_OLD),
        ("toolu_w3", "/home/dev/notes/todo.md", None, None),  # outside the repo: path only
    ]

    (subagent,) = [e for e in events if e.agent_id]
    assert (subagent.id, subagent.agent_id, subagent.prompt_id) == ("toolu_s1", fixture.AGENT, "p-2")

    assert dict(report.skipped_records) == {
        "mode": 1,
        "last-prompt": 1,
        "attachment": 1,
        "system": 1,
        "queue-operation": 1,
        "file-history-snapshot": 1,
        "ai-title": 1,
    }


def test_second_backfill_skips_until_the_transcript_grows(tmp_path, projects):
    transcript = projects / project_dir_name(ROOT) / f"{SID}.jsonl"
    with Store.open(tmp_path) as store:
        backfill(store, ROOT, projects=projects)
        again = backfill(store, ROOT, projects=projects)
        assert (again.added, again.refreshed, again.skipped) == ([], [], [SID])
        with open(transcript, "a") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": SID,
                        "promptId": "p-4",
                        "cwd": str(ROOT),
                        "timestamp": "2026-03-01T10:00:00.000Z",
                        "message": {"role": "user", "content": "one more thing"},
                    }
                )
                + "\n"
            )
        grown = backfill(store, ROOT, projects=projects)
        assert (grown.added, grown.refreshed, grown.skipped) == ([], [SID], [])
        assert [p.text for p in store.prompts(SID)][-1] == "one more thing"
        assert store.session(SID).ended_at == "2026-03-01T10:00:00.000Z"


def test_replace_rebuilds_a_hook_session_and_keeps_its_head(tmp_path, projects):
    with Store.open(tmp_path) as store:
        store.upsert_session(
            Session(
                id=SID,
                repo=str(ROOT),
                started_at="2026-03-01T09:05:00.000Z",
                head_at_start="abc123",
                source="hook",
            )
        )
        untouched = backfill(store, ROOT, projects=projects)
        assert untouched.skipped == [SID] and store.prompts(SID) == []
        replaced = backfill(store, ROOT, projects=projects, replace=True)
        assert replaced.refreshed == [SID]
        session = store.session(SID)
        assert (session.head_at_start, session.source, session.started_at) == (
            "abc123",
            "hook",
            "2026-03-01T09:00:01.000Z",
        )
        assert len(store.prompts(SID)) == 3


def test_transcripts_from_other_repos_are_ignored(tmp_path, projects):
    other = projects / project_dir_name(ROOT) / "other.jsonl"
    other.write_text(
        json.dumps(
            {
                "type": "user",
                "cwd": "/elsewhere",
                "timestamp": "t",
                "message": {"role": "user", "content": "hi"},
            }
        )
        + "\n"
    )
    with Store.open(tmp_path) as store:
        report = backfill(store, ROOT, projects=projects)
    assert report.other_repo == ["other"]
    assert report.added == [SID]


def test_transcripts_for_matches_the_repo_and_launches_from_its_subdirectories(tmp_path):
    projects = tmp_path / "projects"
    for name in ("-home-dev-project", "-home-dev-project-src-pkg", "-home-dev-project2", "-home-other"):
        (projects / name).mkdir(parents=True)
        (projects / name / f"{name}.jsonl").write_text("")
    found = [p.parent.name for p in transcripts_for(ROOT, projects)]
    assert found == ["-home-dev-project", "-home-dev-project-src-pkg"]
    assert transcripts_for(ROOT, tmp_path / "missing") == []
    assert project_dir_name(Path("/Users/me/my.repo_1")) == "-Users-me-my-repo-1"


def test_parser_tolerates_garbage_and_unknown_records(tmp_path):
    path = tmp_path / "abc.jsonl"
    path.write_text(
        "\n".join(
            [
                "not json",
                "[1, 2]",
                json.dumps({"type": "something-new", "sessionId": "abc"}),
                json.dumps(
                    {
                        "type": "user",
                        "cwd": str(ROOT),
                        "timestamp": "2026-01-01T00:00:00.000Z",
                        "promptId": "p1",
                        "message": {"role": "user", "content": "do it"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-01-01T00:00:01.000Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}
                            ],
                        },
                    }
                ),
                "",
            ]
        )
        + "\n"
    )
    parsed = parse_transcript(path, ROOT)
    assert dict(parsed.skipped) == {"<unparseable>": 1, "<not-an-object>": 1, "something-new": 1}
    assert [p.text for p in parsed.prompts] == ["do it"]
    (event,) = parsed.events
    assert (event.prompt_id, event.success, event.response) == ("p1", None, None)  # no result recorded


def test_tool_events_without_prompt_ids_fall_back_to_timestamps(tmp_path):
    path = tmp_path / "abc.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "cwd": str(ROOT),
                        "timestamp": "2026-01-01T00:00:00.000Z",
                        "message": {"role": "user", "content": "first"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-01-01T00:00:01.000Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "cwd": str(ROOT),
                        "timestamp": "2026-01-01T00:00:02.000Z",
                        "message": {"role": "user", "content": "second"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-01-01T00:00:03.000Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ls"}}
                            ],
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    parsed = parse_transcript(path, ROOT)
    first, second = parsed.prompts
    assert [(e.id, e.prompt_id) for e in parsed.events] == [("t1", first.id), ("t2", second.id)]


def test_prompt_detection_rules():
    def user(content, **extra):
        return {"type": "user", "message": {"role": "user", "content": content}, **extra}

    assert is_prompt(user("fix the bug"))
    assert is_prompt(user([{"type": "text", "text": "fix"}, {"type": "text", "text": "it"}]))
    assert not is_prompt(user("fix the bug", isMeta=True))
    assert not is_prompt(user("fix the bug", isSidechain=True))
    assert not is_prompt(user("fix the bug", isCompactSummary=True))
    assert not is_prompt(user("<command-name>/model</command-name>"))
    assert not is_prompt(user("<local-command-stdout>ok</local-command-stdout>"))
    assert not is_prompt(user([{"type": "tool_result", "tool_use_id": "t", "content": "x"}]))
    assert not is_prompt(user("   "))
    assert not is_prompt({"type": "assistant", "message": {"content": "x"}})


def test_prompt_with_injected_reminder_keeps_only_the_human_text(tmp_path):
    path = tmp_path / "abc.jsonl"
    records = [
        {
            "type": "user",
            "cwd": str(ROOT),
            "timestamp": "2026-01-01T00:00:00.000Z",
            "promptId": "p1",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "<system-reminder>\nThe git status is clean.\n</system-reminder>",
                    },
                    {"type": "text", "text": "Add a greet function to app/hello.py"},
                ],
            },
        },
        {
            "type": "user",
            "cwd": str(ROOT),
            "timestamp": "2026-01-01T00:01:00.000Z",
            "promptId": "p2",
            "message": {
                "role": "user",
                "content": "fix the test\n\n<system-reminder>context</system-reminder>",
            },
        },
        {
            "type": "user",
            "cwd": str(ROOT),
            "timestamp": "2026-01-01T00:02:00.000Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "<system-reminder>noise</system-reminder>"}],
            },
        },
        {"type": "user", "cwd": str(ROOT), "timestamp": "2026-01-01T00:03:00.000Z", "message": "not a dict"},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    parsed = parse_transcript(path, ROOT)
    assert [p.text for p in parsed.prompts] == ["Add a greet function to app/hello.py", "fix the test"]


def test_one_unreadable_transcript_does_not_stop_the_others(tmp_path, projects):
    bad = projects / project_dir_name(ROOT) / "0000-bad.jsonl"
    bad.mkdir()  # a directory where a file should be, so open() fails
    with Store.open(tmp_path) as store:
        report = backfill(store, ROOT, projects=projects)
    assert report.added == [SID]
    assert [p for p, _ in report.failed] == [str(bad)]
    assert "IsADirectoryError" in report.failed[0][1]


def test_forked_transcript_with_the_same_ids_keeps_both_sessions(tmp_path, projects):
    d = projects / project_dir_name(ROOT)
    shutil.copy(d / f"{SID}.jsonl", d / "22222222-fork.jsonl")  # same prompt and tool ids, new session
    with Store.open(tmp_path) as store:
        report = backfill(store, ROOT, projects=projects)
        assert sorted(report.added) == sorted([SID, "22222222-fork"])
        assert len(store.events(SID)) == 12 and len(store.events("22222222-fork")) == 11
        assert len(store.prompts(SID)) == 3 and len(store.prompts("22222222-fork")) == 3
