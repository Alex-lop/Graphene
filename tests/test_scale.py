"""Backfill at scale: 200 sessions in one repo, and a second run that reads none of them again."""

import json
import sys
import time
from pathlib import Path

import pytest

from graphene_debrief.sources import claude_code
from graphene_debrief.sources.claude_code import backfill, project_dir_name
from graphene_debrief.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import make_transcript_fixture as fixture  # noqa: E402

SESSIONS = 200


def write_sessions(repo: Path, projects: Path, monkeypatch) -> list[str]:
    """The synthetic transcript, once per session id, with its own day and this repo as its cwd."""
    monkeypatch.setattr(fixture, "CWD", str(repo))
    ids = []
    for i in range(SESSIONS):
        sid = f"{i:08d}-2222-4333-8444-555555555555"
        day = i % 28 + 1
        monkeypatch.setattr(fixture, "SID", sid)
        monkeypatch.setattr(fixture, "stamp", lambda m, s, d=day: f"2026-03-{d:02d}T09:{m:02d}:{s:02d}.000Z")
        for path, text in fixture.render().items():
            out = projects / path.relative_to(fixture.OUT)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text)
        ids.append(sid)
    return ids


def one_more_prompt(sid: str) -> str:
    return (
        json.dumps(
            {
                "type": "user",
                "sessionId": sid,
                "promptId": "p-9",
                "cwd": fixture.CWD,
                "timestamp": "2026-04-01T09:00:00.000Z",
                "message": {"role": "user", "content": "one more thing"},
            }
        )
        + "\n"
    )


@pytest.mark.slow
def test_two_hundred_sessions_load_once_and_are_not_read_again(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    projects = tmp_path / "projects"
    ids = write_sessions(repo, projects / project_dir_name(repo), monkeypatch)
    with Store.open(repo) as store:
        start = time.monotonic()
        first = backfill(store, repo, projects=projects)
        first_seconds = time.monotonic() - start
        assert (len(first.added), first.failed, first.skipped) == (SESSIONS, [], [])
        assert first_seconds < 10, f"first backfill took {first_seconds:.1f}s"

        read: list[str] = []
        parse = claude_code.parse_transcript

        def counting_parse(path, root):
            read.append(path.stem)
            return parse(path, root)

        monkeypatch.setattr(claude_code, "parse_transcript", counting_parse)
        start = time.monotonic()
        again = backfill(store, repo, projects=projects)
        second_seconds = time.monotonic() - start
        assert len(again.skipped) == SESSIONS and (again.added, again.refreshed) == ([], [])
        assert read == []  # same size, same mtime: not one transcript parsed again

        grown = projects / project_dir_name(repo) / f"{ids[7]}.jsonl"
        with open(grown, "a") as f:
            f.write(one_more_prompt(ids[7]))
        third = backfill(store, repo, projects=projects)
        assert (third.refreshed, read) == ([ids[7]], [ids[7]])  # only the one that changed
        assert [p.text for p in store.prompts(ids[7])][-1] == "one more thing"
    with capsys.disabled():
        print(f"\n{SESSIONS} sessions: first backfill {first_seconds:.2f}s, second {second_seconds:.2f}s")
