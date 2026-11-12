"""Failure paths exercised by the live verification of PR #60."""

import sqlite3

import pytest
import test_gate as G


@pytest.mark.parametrize("tool_input", [{"path": "src/db/schema.py"}, {}, {"file_path": []}])
def test_known_write_without_a_usable_path_is_refused(tmp_path, tool_input):
    repo = G.repo.__wrapped__(tmp_path)
    G.holding(repo)
    answer = G.hook(repo, "PreToolUse", tool_name="Write", tool_input=tool_input)
    assert answer is not None and answer["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_store_that_cannot_be_read_does_not_let_a_write_through(tmp_path):
    repo = G.repo.__wrapped__(tmp_path)
    G.holding(repo)
    other = sqlite3.connect(repo / ".graphene/graphene.db", isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")
    try:
        answer = G.write(repo, "src/db/schema.py")
        assert answer is not None and answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    finally:
        other.execute("ROLLBACK")
        other.close()


def test_a_write_with_no_session_cannot_escape_the_plan(tmp_path):
    repo = G.repo.__wrapped__(tmp_path)
    G.holding(repo)
    answer = G.hook(
        repo,
        "PreToolUse",
        session_id=None,
        tool_name="Write",
        tool_input={"file_path": str(repo / "src/db/schema.py")},
    )
    assert answer is not None and answer["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_an_older_engine_cannot_let_writes_through_a_newer_store(tmp_path):
    repo = G.repo.__wrapped__(tmp_path)
    G.holding(repo)
    with sqlite3.connect(repo / ".graphene/graphene.db") as conn:
        conn.execute("PRAGMA user_version = 999999")
    answer = G.write(repo, "src/db/schema.py")
    assert answer is not None and answer["hookSpecificOutput"]["permissionDecision"] == "deny"
