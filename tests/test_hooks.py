"""Live hook ingestion: one fixture event per hook type, and the never-fail contract of hook_main."""

import io
import json

import pytest

from graphene_debrief.sources.claude_code import hook_main, ingest_hook_event, install_hooks
from graphene_debrief.store import Store, ignore_store_dir

T0 = "2026-01-01T10:00:00.000Z"
T1 = "2026-01-01T10:00:01.000Z"
T2 = "2026-01-01T10:00:02.000Z"


def event(name: str, repo, **extra) -> dict:
    base = {
        "session_id": "sess-1",
        "transcript_path": "/somewhere/sess-1.jsonl",
        "cwd": str(repo),
        "hook_event_name": name,
    }
    base.update(extra)
    return base


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()  # enough for repo_root(); git_head() degrades to None without git
    return tmp_path


def test_session_start_records_session(repo):
    with Store.open(repo) as store:
        assert ingest_hook_event(store, event("SessionStart", repo, source="startup"), repo, T0)
        s = store.session("sess-1")
    assert s.repo == str(repo)
    assert s.source == "hook"
    assert s.started_at == T0
    assert s.ended_at is None
    assert s.transcript_path == "/somewhere/sess-1.jsonl"


def test_resume_does_not_reset_start(repo):
    with Store.open(repo) as store:
        ingest_hook_event(store, event("SessionStart", repo, source="startup"), repo, T0)
        ingest_hook_event(store, event("SessionStart", repo, source="resume"), repo, T1)
        assert store.session("sess-1").started_at == T0


def test_prompt_edit_failure_and_stop(repo):
    edit = event(
        "PostToolUse",
        repo,
        prompt_id="p1",
        tool_name="Edit",
        tool_use_id="toolu_1",
        tool_input={"file_path": str(repo / "src" / "x.py"), "old_string": "b", "new_string": "c"},
        tool_response={
            "filePath": str(repo / "src" / "x.py"),
            "oldString": "b",
            "newString": "c",
            "originalFile": "a\nb\n",
            "replaceAll": False,
        },
    )
    failure = event(
        "PostToolUseFailure",
        repo,
        prompt_id="p1",
        tool_name="Bash",
        tool_use_id="toolu_2",
        tool_input={"command": "pytest -q"},
        error="Exit code 1\n1 failed",
        is_interrupt=False,
    )
    with Store.open(repo) as store:
        ingest_hook_event(store, event("SessionStart", repo, source="startup"), repo, T0)
        ingest_hook_event(store, event("UserPromptSubmit", repo, prompt_id="p1", prompt="fix x"), repo, T0)
        ingest_hook_event(store, edit, repo, T1)
        ingest_hook_event(store, failure, repo, T1)
        ingest_hook_event(store, event("Stop", repo, stop_hook_active=False), repo, T2)
        prompts = store.prompts("sess-1")
        events = store.events("sess-1")
        session = store.session("sess-1")

    assert [(p.id, p.ordinal, p.text) for p in prompts] == [("p1", 1, "fix x")]
    e_edit, e_fail = events
    assert e_edit.prompt_id == "p1"
    assert e_edit.file_path == "src/x.py"
    assert e_edit.old_content == "a\nb\n"
    assert e_edit.new_content == "a\nc\n"
    assert e_edit.success is True
    assert e_fail.success is False
    assert e_fail.response == {"error": "Exit code 1\n1 failed", "is_interrupt": False}
    assert e_fail.file_path is None
    assert session.ended_at == T2


def test_write_create_then_update(repo):
    path = str(repo / "new.txt")
    create = event(
        "PostToolUse",
        repo,
        prompt_id="p1",
        tool_name="Write",
        tool_use_id="w1",
        tool_input={"file_path": path, "content": "one\n"},
        tool_response={"type": "create", "filePath": path, "content": "one\n"},
    )
    update = event(
        "PostToolUse",
        repo,
        prompt_id="p1",
        tool_name="Write",
        tool_use_id="w2",
        tool_input={"file_path": path, "content": "two\n"},
        tool_response={"type": "update", "filePath": path, "content": "two\n", "originalFile": "one\n"},
    )
    with Store.open(repo) as store:
        ingest_hook_event(store, event("UserPromptSubmit", repo, prompt_id="p1", prompt="write"), repo, T0)
        ingest_hook_event(store, create, repo, T1)
        ingest_hook_event(store, update, repo, T2)
        first, second = store.events("sess-1")
    assert (first.old_content, first.new_content) == (None, "one\n")
    assert (second.old_content, second.new_content) == ("one\n", "two\n")
    assert first.file_path == "new.txt"


def test_multiedit_applies_edits_in_order(repo):
    path = str(repo / "m.py")
    ev = event(
        "PostToolUse",
        repo,
        prompt_id="p1",
        tool_name="MultiEdit",
        tool_use_id="m1",
        tool_input={
            "file_path": path,
            "edits": [
                {"old_string": "a", "new_string": "b"},
                {"old_string": "b", "new_string": "c", "replace_all": True},
            ],
        },
        tool_response={"filePath": path, "originalFile": "a b\n"},
    )
    with Store.open(repo) as store:
        ingest_hook_event(store, event("UserPromptSubmit", repo, prompt_id="p1", prompt="go"), repo, T0)
        ingest_hook_event(store, ev, repo, T1)
        (stored,) = store.events("sess-1")
    assert stored.new_content == "c c\n"


def test_unknown_prompt_id_falls_back_to_latest_prompt(repo):
    ev = event(
        "PostToolUse",
        repo,
        prompt_id="never-seen",
        tool_name="Bash",
        tool_use_id="b1",
        tool_input={"command": "ls"},
        tool_response={"stdout": "", "stderr": ""},
    )
    with Store.open(repo) as store:
        ingest_hook_event(store, event("UserPromptSubmit", repo, prompt_id="p1", prompt="one"), repo, T0)
        ingest_hook_event(store, event("UserPromptSubmit", repo, prompt_id="p2", prompt="two"), repo, T1)
        ingest_hook_event(store, ev, repo, T2)
        (stored,) = store.events("sess-1")
        assert [p.ordinal for p in store.prompts("sess-1")] == [1, 2]
    assert stored.prompt_id == "p2"


def test_hooks_installed_mid_session_create_the_session_lazily(repo):
    ev = event(
        "PostToolUse",
        repo,
        tool_name="Bash",
        tool_use_id="b1",
        agent_id="agent-7",
        tool_input={"command": "ls"},
        tool_response={"stdout": ""},
    )
    with Store.open(repo) as store:
        ingest_hook_event(store, ev, repo, T0)
        session = store.session("sess-1")
        (stored,) = store.events("sess-1")
    assert (session.started_at, session.head_at_start) == (T0, None)  # start HEAD unknown: resolved by time
    assert stored.prompt_id is None
    assert stored.agent_id == "agent-7"


def test_files_outside_the_repo_keep_absolute_paths(repo):
    ev = event(
        "PostToolUse",
        repo,
        tool_name="Write",
        tool_use_id="w1",
        tool_input={"file_path": "/elsewhere/note.md", "content": "SECRET BODY"},
        tool_response={"type": "create", "filePath": "/elsewhere/note.md", "content": "SECRET BODY"},
    )
    with Store.open(repo) as store:
        ingest_hook_event(store, ev, repo, T0)
        (stored,) = store.events("sess-1")
        raw = store.conn.execute("SELECT input, response FROM tool_events").fetchone()
    assert stored.file_path == "/elsewhere/note.md"
    assert (stored.old_content, stored.new_content) == (None, None)
    assert stored.input == {"file_path": "/elsewhere/note.md"} and stored.response is None
    assert "SECRET BODY" not in (raw[0] or "") + (raw[1] or "")  # not even inside the raw payload


def test_ignored_events_and_bad_input_record_nothing(repo):
    with Store.open(repo) as store:
        assert not ingest_hook_event(store, event("PreToolUse", repo, tool_name="Bash"), repo, T0)
        assert not ingest_hook_event(store, {"hook_event_name": "Stop"}, repo, T0)
        assert store.sessions() == []


def test_hook_main_never_raises_never_prints_and_logs(repo, capsys):
    assert hook_main(io.StringIO("this is not json"), cwd=repo) == 0
    assert hook_main(io.StringIO("[1, 2]"), cwd=repo) == 0
    assert hook_main(io.StringIO(""), cwd=repo) == 0
    assert capsys.readouterr().out == ""
    log = (repo / ".graphene" / "ingest.log").read_text()
    assert "JSONDecodeError" in log
    assert "not a JSON object" in log


def test_hook_main_reads_stdin_and_finds_repo_from_event_cwd(repo, capsys):
    sub = repo / "pkg" / "deep"
    sub.mkdir(parents=True)
    payload = json.dumps(event("UserPromptSubmit", sub, prompt_id="p1", prompt="hello"))
    assert hook_main(io.StringIO(payload), cwd=sub) == 0
    assert capsys.readouterr().out == ""
    with Store.open(repo) as store:
        assert [p.text for p in store.prompts("sess-1")] == ["hello"]
    assert not (sub / ".graphene").exists()


def test_install_hooks_merges_and_is_idempotent(repo):
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "enabledPlugins": {"x": True},
                "hooks": {
                    "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}]
                },
            }
        )
    )
    added = install_hooks(repo)
    assert added == ["SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop"]
    merged = json.loads(settings.read_text())
    assert merged["enabledPlugins"] == {"x": True}
    post = merged["hooks"]["PostToolUse"]
    assert post[0]["hooks"][0]["command"] == "echo hi"
    assert post[1]["hooks"][0]["command"] == "graphene ingest hook"
    assert install_hooks(repo) == []
    assert json.loads(settings.read_text()) == merged


def test_install_hooks_refuses_to_clobber_malformed_settings(repo):
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text("[]")
    with pytest.raises(ValueError):
        install_hooks(repo)
    assert settings.read_text() == "[]"


def test_ignore_store_dir_writes_inside_the_store_only(repo):
    gitignore = repo / ".gitignore"
    gitignore.write_text(".venv/")
    assert ignore_store_dir(repo)
    assert (repo / ".graphene" / ".gitignore").read_text() == "*\n"
    assert gitignore.read_text() == ".venv/"  # the repo's own file is never touched
    assert not ignore_store_dir(repo)


def test_hook_gives_up_quickly_when_the_store_is_locked(repo):
    import sqlite3
    import time

    Store.open(repo).close()
    other = sqlite3.connect(repo / ".graphene" / "graphene.db", isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")
    try:
        started = time.monotonic()
        payload = json.dumps(event("UserPromptSubmit", repo, prompt_id="p1", prompt="x"))
        assert hook_main(io.StringIO(payload), cwd=repo) == 0
        assert time.monotonic() - started < 2.0
    finally:
        other.execute("ROLLBACK")
        other.close()
    assert "locked" in (repo / ".graphene" / "ingest.log").read_text()


def test_store_dir_is_private_and_ignored_on_any_open(repo):
    import os

    (repo / ".gitignore").write_text("*.pyc\n")
    Store.open(repo).close()
    assert (repo / ".graphene" / ".gitignore").read_text() == "*\n"
    assert (repo / ".gitignore").read_text() == "*.pyc\n"
    assert oct(os.stat(repo / ".graphene").st_mode & 0o777) == "0o700"
    assert oct(os.stat(repo / ".graphene" / "graphene.db").st_mode & 0o777) == "0o600"


def test_install_hooks_rejects_odd_shapes_without_clobbering(repo):
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    for shape in ('{"hooks": null}', '{"hooks": []}', '{"hooks": {"PostToolUse": "junk"}}'):
        settings.write_text(shape)
        with pytest.raises(ValueError):
            install_hooks(repo)
        assert settings.read_text() == shape
    settings.write_text('{"hooks": {"PostToolUse": ["junk", {"hooks": "junk"}]}}')
    assert "PostToolUse" in install_hooks(repo)  # junk entries are left alone and ours is appended
    assert json.loads(settings.read_text())["hooks"]["PostToolUse"][:2] == ["junk", {"hooks": "junk"}]


def test_write_response_with_an_odd_original_file_is_still_recorded(repo):
    ev = event(
        "PostToolUse",
        repo,
        tool_name="Write",
        tool_use_id="w1",
        tool_input={"file_path": str(repo / "a.txt"), "content": "x"},
        tool_response={"type": "update", "originalFile": {"a": 1}, "content": "x"},
    )
    with Store.open(repo) as store:
        ingest_hook_event(store, ev, repo, T0)
        (stored,) = store.events("sess-1")
    assert (stored.old_content, stored.new_content) == (None, "x")


def test_install_hooks_writes_through_a_symlink_atomically(repo, tmp_path):
    real = tmp_path / "dotfiles" / "settings.local.json"
    real.parent.mkdir()
    real.write_text('{"model": "x"}')
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.local.json").symlink_to(real)
    assert install_hooks(repo)
    assert (repo / ".claude" / "settings.local.json").is_symlink()
    assert "hooks" in json.loads(real.read_text()) and json.loads(real.read_text())["model"] == "x"
    assert [p.name for p in real.parent.iterdir()] == ["settings.local.json"]  # no temp file left behind


def test_slash_commands_are_not_prompts(repo):
    """The hook sees what was typed: `/model` or a skill invocation is not a request (nor in transcripts)."""
    with Store.open(repo) as store:
        ingest_hook_event(store, event("SessionStart", repo), repo, T0)
        for text in ("/model", "/mode;", "/plugin:skill some args", "  /help  "):
            submit = event("UserPromptSubmit", repo, prompt_id="p0", prompt=text)
            assert not ingest_hook_event(store, submit, repo, T0)
        real = event("UserPromptSubmit", repo, prompt_id="p1", prompt="/tmp/x.py is broken, fix it")
        assert ingest_hook_event(store, real, repo, T1)
        assert [p.text for p in store.prompts("sess-1")] == ["/tmp/x.py is broken, fix it"]
