"""graphene why: a file's prompt history newest first, and line-level intent blame via git blame."""

import os
import subprocess

import pytest

from graphene_debrief.model import Prompt, Session, ToolEvent
from graphene_debrief.store import Store
from graphene_debrief.why import blame, why_line, why_path

V1 = "alpha\nbeta\ngamma\n"
V2 = "alpha\nbeta two\ngamma\n"
V3 = "alpha\nbeta two\ngamma\ndelta\n"
V4 = "alpha\nbeta three\ngamma\ndelta\n"
V5 = "alpha\nbeta two\ngamma\ndelta\n"


def git(*args, cwd, date=None):
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env).stdout


@pytest.fixture
def repo(tmp_path):
    git("init", "-q", cwd=tmp_path)
    git("config", "user.email", "t@example.com", cwd=tmp_path)
    git("config", "user.name", "t", cwd=tmp_path)
    return tmp_path


def event(eid, sid, pid, when, tool, old, new):
    response = {"type": "create", "content": new} if old is None else {"originalFile": old}
    return ToolEvent(
        eid,
        sid,
        pid,
        when,
        tool,
        {"file_path": "notes.txt"},
        response,
        True,
        file_path="notes.txt",
        old_content=old,
        new_content=new,
    )


def seed(store, repo):
    """Session 1: create, then change line 2. Session 2: append, change line 2, change it back."""
    store.upsert_session(
        Session(
            "s1",
            str(repo),
            started_at="2026-01-01T09:00:00.000Z",
            ended_at="2026-01-01T10:00:00.000Z",
            source="backfill",
        )
    )
    store.add_prompt(
        Prompt("p1", "s1", 1, "2026-01-01T09:00:01.000Z", "create notes.txt with three greek letters")
    )
    store.add_prompt(Prompt("p2", "s1", 2, "2026-01-01T09:30:00.000Z", "change the second line of notes.txt"))
    store.add_event(event("w1", "s1", "p1", "2026-01-01T09:01:00.000Z", "Write", None, V1))
    store.add_event(event("e1", "s1", "p2", "2026-01-01T09:31:00.000Z", "Edit", V1, V2))
    store.upsert_session(
        Session(
            "s2",
            str(repo),
            started_at="2026-01-02T09:00:00.000Z",
            ended_at="2026-01-02T10:00:00.000Z",
            source="backfill",
        )
    )
    store.add_prompt(Prompt("p3", "s2", 1, "2026-01-02T09:00:01.000Z", "append delta to notes.txt"))
    store.add_prompt(Prompt("p4", "s2", 2, "2026-01-02T09:10:00.000Z", "make line two say beta three"))
    store.add_prompt(Prompt("p5", "s2", 3, "2026-01-02T09:20:00.000Z", "put line two back to beta two"))
    store.add_event(event("e2", "s2", "p3", "2026-01-02T09:01:00.000Z", "Edit", V2, V3))
    store.add_event(event("e3", "s2", "p4", "2026-01-02T09:11:00.000Z", "Edit", V3, V4))
    store.add_event(event("e4", "s2", "p5", "2026-01-02T09:21:00.000Z", "Edit", V4, V5))
    store.set_explanation("p2", "notes.txt", "Rewrites the second line.", "claude", "t")


def test_why_path_lists_prompts_newest_first(repo):
    with Store.open(repo) as store:
        seed(store, repo)
        entries = why_path(store, repo, "notes.txt")
        assert why_path(store, repo, "never.txt") == []
    assert [(e.session_id, e.ordinal, e.effect, e.added, e.removed) for e in entries] == [
        ("s2", 3, "modified", 1, 1),
        ("s2", 2, "modified", 1, 1),
        ("s2", 1, "modified", 1, 0),
        ("s1", 2, "modified", 1, 1),
        ("s1", 1, "created", 3, 0),
    ]
    assert (entries[3].explanation, entries[3].explained_by) == ("Rewrites the second line.", "claude")
    assert entries[0].explained_by == "none"
    assert entries[4].prompt_text.startswith("create notes.txt")


def test_why_line_on_an_uncommitted_file(repo):
    (repo / "notes.txt").write_text(V5)
    with Store.open(repo) as store:
        seed(store, repo)
        line1 = why_line(store, repo, "notes.txt", 1)
        line2 = why_line(store, repo, "notes.txt", 2)
        line4 = why_line(store, repo, "notes.txt", 4)
        missing = why_line(store, repo, "notes.txt", 99)
    assert (line1.content, line1.commit, [m.prompt_id for m in line1.matches]) == ("alpha", None, ["p1"])
    assert line1.reason == "exactly one recorded edit added this line"
    assert [m.prompt_id for m in line2.matches] == ["p5", "p2"]  # both wrote "beta two" at line 2
    assert line2.reason == "2 recorded edits added an identical line; newest first"
    assert [m.prompt_id for m in line4.matches] == ["p3"]
    assert missing.content is None and "no line 99" in missing.reason


def test_why_line_falls_back_to_text_when_lines_shifted(repo):
    (repo / "notes.txt").write_text("inserted by hand\n" + V5)
    with Store.open(repo) as store:
        seed(store, repo)
        answer = why_line(store, repo, "notes.txt", 5)
    assert answer.content == "delta"
    assert [m.prompt_id for m in answer.matches] == ["p3"]
    assert answer.reason == "1 recorded edit(s) added this text at a different line; newest first"


def test_why_line_on_a_committed_file_reports_the_commit(repo):
    (repo / "notes.txt").write_text(V5)
    git("add", "notes.txt", cwd=repo)
    git("commit", "-q", "-m", "notes", cwd=repo, date="2026-01-03T12:00:00Z")
    sha = git("rev-parse", "HEAD", cwd=repo).strip()
    assert blame(repo, "notes.txt", 4) == (sha, "2026-01-03T12:00:00.000Z")
    with Store.open(repo) as store:
        seed(store, repo)
        answer = why_line(store, repo, "notes.txt", 4)
    assert (answer.commit, answer.committed_at) == (sha, "2026-01-03T12:00:00.000Z")
    assert [m.prompt_id for m in answer.matches] == ["p3"]


def test_why_line_predating_every_session_says_so(repo):
    (repo / "notes.txt").write_text("zeta\n")
    git("add", "notes.txt", cwd=repo)
    git("commit", "-q", "-m", "old", cwd=repo, date="2025-12-01T12:00:00Z")
    sha = git("rev-parse", "HEAD", cwd=repo).strip()
    with Store.open(repo) as store:
        seed(store, repo)
        answer = why_line(store, repo, "notes.txt", 1)
    assert answer.matches == []
    assert answer.reason == f"committed in {sha[:7]} before any recorded session; no recorded edit wrote it"


def test_why_line_with_no_matching_edit_explains_why(repo):
    (repo / "notes.txt").write_text("alpha\nhand written\n")
    with Store.open(repo) as store:
        seed(store, repo)
        answer = why_line(store, repo, "notes.txt", 2)
        nothing = why_line(store, repo, "other.txt", 1)
    assert answer.matches == []
    assert answer.reason == "prompts changed this file but none of their recorded edits added this exact line"
    assert nothing.content is None


def test_paths_are_normalised_to_the_repo(repo, monkeypatch):
    monkeypatch.chdir(repo)
    with Store.open(repo) as store:
        seed(store, repo)
        by_abs = why_path(store, repo, str(repo / "notes.txt"))
        by_rel = why_path(store, repo, "./notes.txt")
    assert [e.prompt_id for e in by_abs] == [e.prompt_id for e in by_rel] == ["p5", "p4", "p3", "p2", "p1"]


def test_changes_before_the_first_prompt_are_listed(repo):
    with Store.open(repo) as store:
        store.upsert_session(Session("s0", str(repo), started_at="2025-12-31T09:00:00.000Z", source="hook"))
        store.add_event(event("w0", "s0", None, "2025-12-31T09:01:00.000Z", "Write", None, V1))
        (entry,) = why_path(store, repo, "notes.txt")
    assert (entry.ordinal, entry.prompt_text, entry.effect) == (
        0,
        "(changes recorded before the first prompt)",
        "created",
    )


def test_a_prompt_after_the_commit_is_never_the_answer(repo):
    (repo / "notes.txt").write_text("alpha\nbeta two\n")  # 'beta two' committed long before any session
    git("add", "notes.txt", cwd=repo)
    git("commit", "-q", "-m", "ancient", cwd=repo, date="2020-01-01T12:00:00Z")
    sha = git("rev-parse", "HEAD", cwd=repo).strip()
    with Store.open(repo) as store:
        seed(store, repo)  # p2 and p5 add an identical 'beta two' line, years later
        answer = why_line(store, repo, "notes.txt", 2)
    assert answer.matches == []
    assert answer.reason == f"committed in {sha[:7]} before any recorded session; no recorded edit wrote it"
