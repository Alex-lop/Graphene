"""Attribution on small sessions built in the test body."""

import subprocess
from pathlib import Path

import pytest

from graphene_debrief.attribute import (
    GitState,
    attribute_session,
    bash_written_paths,
    check_segments,
    diff_hunks,
    named_scopes,
    unrequested_paths,
)
from graphene_debrief.model import Prompt, Session, ToolEvent

T = "2026-01-01T10:00:%02d.000Z"


def prompt(pid: str, text: str, n: int) -> Prompt:
    return Prompt(id=pid, session_id="s", ordinal=n, timestamp=T % (n * 10), text=text)


def write(eid: str, pid: str, path: str, content: str, t: int, old: str | None = None) -> ToolEvent:
    kind = "create" if old is None else "update"
    return ToolEvent(
        id=eid,
        session_id="s",
        prompt_id=pid,
        timestamp=T % t,
        tool="Write",
        input={"file_path": path, "content": content},
        response={"type": kind, "filePath": path, "content": content, "originalFile": old},
        success=True,
        file_path=path,
        old_content=old,
        new_content=content,
    )


def edit(eid: str, pid: str, path: str, old: str, new: str, t: int) -> ToolEvent:
    return ToolEvent(
        id=eid,
        session_id="s",
        prompt_id=pid,
        timestamp=T % t,
        tool="Edit",
        input={"file_path": path},
        response={"originalFile": old},
        success=True,
        file_path=path,
        old_content=old,
        new_content=new,
    )


def bash(eid: str, pid: str, command: str, t: int, ok: bool = True) -> ToolEvent:
    return ToolEvent(
        id=eid,
        session_id="s",
        prompt_id=pid,
        timestamp=T % t,
        tool="Bash",
        input={"command": command},
        response={"stdout": ""} if ok else {"error": "Exit code 1\nboom"},
        success=ok,
    )


def run(session: Session, prompts, events, root: Path):
    return attribute_session(session, prompts, events, root)


@pytest.fixture
def session(tmp_path):
    return Session(id="s", repo=str(tmp_path), started_at=T % 0, head_at_start=None)


def test_file_edited_under_two_prompts(session, tmp_path):
    p1, p2 = prompt("p1", "create calc.py with add", 1), prompt("p2", "make add in calc.py return b + a", 2)
    v1 = "def add(a, b):\n    return a + b\n"
    v2 = "def add(a, b):\n    return b + a\n"
    result = run(
        session,
        [p1, p2],
        [write("w", "p1", "calc.py", v1, 11), edit("e", "p2", "calc.py", v1, v2, 21)],
        tmp_path,
    )
    first, second = result.changes
    assert (first.prompt_id, first.effect, first.added, first.removed, first.strategy) == (
        "p1",
        "created",
        2,
        0,
        "payload",
    )
    assert (second.prompt_id, second.effect, second.added, second.removed) == ("p2", "modified", 1, 1)
    assert second.hunks[0].lines == [" def add(a, b):", "-    return a + b", "+    return b + a"]
    assert not first.unrequested and not second.unrequested
    assert result.reverted == [] and result.failed == [] and result.reruns == []


def test_unrequested_file_is_flagged_with_its_prompt(session, tmp_path):
    p1 = prompt("p1", "fix the login bug in auth.py", 1)
    events = [
        edit("e1", "p1", "auth.py", "x\n", "y\n", 11),
        edit("e2", "p1", "utils/helpers.py", "a\n", "b\n", 12),
    ]
    changes = run(session, [p1], events, tmp_path).changes
    flagged = {c.path: c.unrequested for c in changes}
    assert flagged == {"auth.py": False, "utils/helpers.py": True}


def test_unrequested_only_when_a_named_scope_excludes_the_file():
    auth = ["auth.py", "utils/helpers.py"]
    assert unrequested_paths("fix the login bug in auth.py", auth) == {"utils/helpers.py"}
    assert unrequested_paths("fix the login bug", auth) == set()  # no scope named: silence
    hello = ["app/hello.py", "tests/test_hello.py"]
    assert unrequested_paths("Add a greet function to app/hello.py and a test for it.", hello) == set()
    assert (
        unrequested_paths("Try making greet shout in hello.py, then put it back.", ["app/hello.py"]) == set()
    )
    rebuild = [
        "src/graphene_debrief/cli.py",
        "tests/test_cli.py",
        "README.md",
        "pyproject.toml",
        ".gitignore",
    ]
    assert (
        unrequested_paths("Please implement REBUILD_DIRECTIVE.md to the best of your abilities", rebuild)
        == set()
    )
    assert (
        unrequested_paths("Rename the title in README.md, then undo it", ["README.md", "notes.md"]) == set()
    )
    assert unrequested_paths("look in app", ["app/hello.py", "app/__init__.py", "lib/other.py"]) == {
        "lib/other.py"
    }
    assert unrequested_paths(
        "update docs/HOW_IT_WORKS.md for the new flag", ["docs/HOW_IT_WORKS.md", "src/x.py"]
    ) == {"src/x.py"}
    assert unrequested_paths(
        "edit src/app/models.py", ["src/app/models.py", "src/app/__init__.py", "src/db.py"]
    ) == {"src/db.py"}
    env = ["config/settings.py", "config/__init__.py", ".env.example", "main.py"]
    assert unrequested_paths("rewrite the .env loader in config/settings.py", env) == {"main.py"}
    assert unrequested_paths("fix auth.py", ["README.md", "main.py"]) == {"README.md", "main.py"}
    assert unrequested_paths("see https://example.com/a/b.py for context", ["x.py"]) == set()
    assert unrequested_paths("make the happy path faster, e.g. in v1.2", ["web/app.py"]) == set()


def test_a_document_the_prompt_names_is_never_flagged_even_though_it_sets_no_scope():
    prompt = "Rewrite OVERVIEW.md for a stranger, and fix the parser in src/parse/."
    paths = ["OVERVIEW.md", "src/parse/lexer.py", "docs/other.md"]
    assert unrequested_paths(prompt, paths) == {"docs/other.md"}
    assert unrequested_paths("Update OVERVIEW.md.", paths) == set()  # a document alone names no scope


def test_a_slash_in_prose_is_not_a_directory_scope(tmp_path):
    (tmp_path / "src" / "app").mkdir(parents=True)
    prose = "That covers the broad/high level picture and/or the details; now write an overview of it."
    assert named_scopes(prose, ["OVERVIEW.md"], root=tmp_path) == []
    assert unrequested_paths(prose, ["OVERVIEW.md"], tmp_path) == set()
    # a directory of the repo is still a scope when nothing under it changed, and so is one that did
    assert unrequested_paths("tidy src/app and nothing else", ["docs/y.md"], tmp_path) == {"docs/y.md"}
    assert "lib/gone/" in named_scopes("work in lib/gone", ["lib/gone/x.py"], root=tmp_path)


def test_a_check_named_inside_a_quoted_string_is_text_not_a_check():
    body = "parser: the gate is green\n\nuv run pytest -q (121 passed)."
    message = f'git commit -q -m "{body}" && git log --oneline -1'
    assert check_segments(message) == []
    heredoc = "python3 - <<'EOF'\nprint('ruff check')\nEOF\ngit commit -q -m \"lint: ruff check passes\""
    assert check_segments(heredoc) == []
    assert check_segments('cd app && uv run pytest -q tests/ && echo "pytest done"') == [
        "uv run pytest -q tests/"
    ]
    assert check_segments("uv run ruff check; uv run pytest -q") == ["uv run ruff check", "uv run pytest -q"]


def test_named_scopes():
    assert named_scopes("fix auth.py and utils/", []) == ["auth.py", "utils/"]
    assert named_scopes("read README.md and REBUILD_DIRECTIVE.md then go", []) == []
    assert named_scopes("update docs/HOW_IT_WORKS.md", []) == ["docs/how_it_works.md"]
    assert named_scopes("work under src/graphene_debrief", []) == ["src/graphene_debrief/"]
    assert named_scopes("look in app, then under tests", ["app/x.py", "tests/y.py"]) == ["app/", "tests/"]
    assert named_scopes("look in app", ["lib/x.py"]) == []  # not a directory of anything that changed
    assert named_scopes("the (auth.py) file, `.env`, and `pyproject.toml`.", []) == [
        "auth.py",
        ".env",
        "pyproject.toml",
    ]


def test_revert_across_prompts_is_abandoned_work(session, tmp_path):
    p1, p2 = prompt("p1", "try a change to a.py", 1), prompt("p2", "undo that in a.py", 2)
    events = [edit("e1", "p1", "a.py", "A\n", "B\n", 11), edit("e2", "p2", "a.py", "B\n", "A\n", 21)]
    result = run(session, [p1, p2], events, tmp_path)
    assert [c.effect for c in result.changes] == ["modified", "modified"]
    assert [(c.path, c.prompt_id, c.effect) for c in result.reverted] == [("a.py", "p2", "reverted")]


def test_revert_within_one_prompt_has_no_hunks(session, tmp_path):
    p1 = prompt("p1", "poke a.py", 1)
    events = [edit("e1", "p1", "a.py", "A\n", "B\n", 11), edit("e2", "p1", "a.py", "B\n", "A\n", 12)]
    result = run(session, [p1], events, tmp_path)
    (change,) = result.changes
    assert (change.effect, change.hunks, change.added) == ("reverted", [], 0)
    assert [c.path for c in result.reverted] == ["a.py"]


def test_failed_then_passing_check_command(session, tmp_path):
    p1, p2 = prompt("p1", "run tests", 1), prompt("p2", "fix and rerun", 2)
    events = [
        bash("b1", "p1", "uv run pytest -q", 11, ok=False),
        bash("b2", "p1", "ls nope", 12, ok=False),
        bash("b3", "p2", "uv  run pytest -q", 21, ok=True),
    ]
    result = run(session, [p1, p2], events, tmp_path)
    assert [e.id for e in result.failed] == ["b1", "b2"]
    assert [(a.id, b.id, b.success, c) for a, b, c in result.reruns] == [
        ("b1", "b3", True, "uv run pytest -q")
    ]


def test_check_command_detection():
    assert check_segments("uv run pytest tests/ -q")
    assert check_segments("cd app && npm test") == ["npm test"]
    assert check_segments("make lint")
    assert not check_segments("git status")
    assert not check_segments("cat pytest.ini")


def test_bash_written_paths(tmp_path):
    root = tmp_path
    cases = {
        "echo hi > notes.txt": [("notes.txt", "write")],
        "cat <<'EOF' >> log/out.txt\nx\nEOF": [("log/out.txt", "write")],
        "sed -i '' 's/a/b/' src/x.py": [("src/x.py", "write")],
        "sed -i -e 's/a/b/' one.py two.py": [("one.py", "write"), ("two.py", "write")],
        "mv old.py new.py": [("new.py", "write"), ("old.py", "delete")],
        "rm -rf build dist/": [("build", "delete"), ("dist", "delete")],
        "tee -a a.log": [("a.log", "write")],
        "cp a.txt b.txt && touch c.txt": [("b.txt", "write"), ("c.txt", "write")],
        "ls 2>/dev/null > /dev/null": [],
        "git status": [],
        f"echo x > {root}/abs.txt": [("abs.txt", "write")],
        "echo x > /elsewhere/abs.txt": [("/elsewhere/abs.txt", "write")],
        "echo x > $HOME/y.txt": [],
    }
    for command, expected in cases.items():
        assert bash_written_paths(command, root) == expected, command


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def git_repo(tmp_path):
    git("init", "-q", cwd=tmp_path)
    git("config", "user.email", "t@example.com", cwd=tmp_path)
    git("config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "README.md").write_text("one\ntwo\n")
    git("add", "README.md", cwd=tmp_path)
    git("commit", "-q", "-m", "init", cwd=tmp_path)
    return tmp_path


def test_bash_write_falls_back_to_git(git_repo):
    head = git("rev-parse", "HEAD", cwd=git_repo).strip()
    session = Session(id="s", repo=str(git_repo), started_at=T % 0, head_at_start=head)
    p1, p2 = prompt("p1", "write notes.txt and tweak README.md", 1), prompt("p2", "tweak README.md again", 2)
    (git_repo / "notes.txt").write_text("hi\n")
    (git_repo / "README.md").write_text("one\nthree\n")
    events = [
        bash("b1", "p1", "echo hi > notes.txt", 11),
        bash("b2", "p1", "sed -i '' 's/two/2/' README.md", 12),
        bash("b3", "p2", "sed -i '' 's/2/three/' README.md", 21),
    ]
    result = attribute_session(session, [p1, p2], events, git_repo, GitState(git_repo))
    by = {(c.prompt_id, c.path): c for c in result.changes}
    assert by[("p1", "notes.txt")].effect == "created"
    assert by[("p1", "notes.txt")].strategy == "git"
    assert by[("p1", "notes.txt")].added == 1
    assert by[("p1", "README.md")].hunks == []  # diff credited to the last prompt that touched it
    last = by[("p2", "README.md")]
    assert (last.effect, last.added, last.removed, last.strategy) == ("modified", 1, 1, "git")
    assert result.reverted == []


def test_git_fallback_detects_session_level_revert(git_repo):
    head = git("rev-parse", "HEAD", cwd=git_repo).strip()
    session = Session(id="s", repo=str(git_repo), started_at=T % 0, head_at_start=head)
    p1 = prompt("p1", "touch README.md", 1)
    events = [bash("b1", "p1", "sed -i '' 's/two/2/' README.md", 11)]  # disk content unchanged
    result = attribute_session(session, [p1], events, git_repo, GitState(git_repo))
    assert [c.path for c in result.reverted] == ["README.md"]


def test_without_git_the_file_is_listed_without_hunks(session, tmp_path):
    p1 = prompt("p1", "write notes", 1)
    result = attribute_session(
        session,
        [p1],
        [bash("b1", "p1", "echo hi > notes.txt", 11)],
        tmp_path,
        GitState(tmp_path, available=False),
    )
    (change,) = result.changes
    assert (change.path, change.effect, change.strategy, change.hunks) == (
        "notes.txt",
        "modified",
        "none",
        [],
    )


def test_failed_calls_and_files_outside_the_repo_are_kept_apart(session, tmp_path):
    p1 = prompt("p1", "x", 1)
    failed = ToolEvent(
        id="e1",
        session_id="s",
        prompt_id="p1",
        timestamp=T % 11,
        tool="Edit",
        input={"file_path": "a.py"},
        response={"error": "no match"},
        success=False,
        file_path="a.py",
    )
    outside = write("w", "p1", "/elsewhere/note.md", "n\n", 12)
    result = run(session, [p1], [failed, outside], tmp_path)
    assert result.changes == []
    assert [e.id for e in result.failed] == ["e1"]
    assert result.outside_repo == ["/elsewhere/note.md"]


def test_diff_hunks_counts():
    hunks = diff_hunks("a\nb\nc\n", "a\nB\nc\nd\n")
    assert len(hunks) == 1
    assert hunks[0].lines == [" a", "-b", "+B", " c", "+d"]
    assert diff_hunks("same\n", "same\n") == []


def test_heredoc_bodies_are_not_shell_syntax(tmp_path):
    command = "cat > out.py <<'EOF'\nif len(v) > 4096:\n    x = a > CONTENT_CAP\nEOF\necho done"
    assert bash_written_paths(command, tmp_path) == [("out.py", "write")]
    assert bash_written_paths("python - <<EOF\nprint(1 > 0)\nEOF", tmp_path) == []


def test_relative_paths_follow_cd(tmp_path):
    assert bash_written_paths("cd sub && echo hi > a.txt", tmp_path) == [("sub/a.txt", "write")]
    assert bash_written_paths("cd /elsewhere && echo x > a.txt", tmp_path) == [("/elsewhere/a.txt", "write")]
    assert bash_written_paths("cd sub && cd .. && echo x > b.txt", tmp_path) == [("b.txt", "write")]
    assert bash_written_paths("cd ~ && echo x > c.txt", tmp_path) == [(str(Path.home() / "c.txt"), "write")]


def test_check_segments_and_reruns_inside_longer_commands(session, tmp_path):
    assert check_segments("uv run ruff check src && uv run pytest -q 2>&1 | tail -3") == [
        "uv run ruff check src",
        "uv run pytest -q",  # the redirection is not part of what ran
    ]
    p1, p2 = prompt("p1", "test", 1), prompt("p2", "fix", 2)
    events = [
        bash("b1", "p1", "uv run ruff check src && uv run pytest -q 2>&1 | tail -3", 11, ok=False),
        bash("b2", "p2", "git status", 20),
        bash("b3", "p2", "uv run pytest -q 2>&1 | tail -3", 21, ok=False),
        bash("b4", "p2", "uv run pytest -q 2>&1 | tail -1", 22),
    ]
    result = run(session, [p1, p2], events, tmp_path)
    assert [(a.id, b.id, c) for a, b, c in result.reruns] == [("b1", "b4", "uv run pytest -q")]


def test_git_fallback_skips_paths_that_never_existed_or_are_directories(git_repo):
    head = git("rev-parse", "HEAD", cwd=git_repo).strip()
    session = Session(id="s", repo=str(git_repo), started_at=T % 0, head_at_start=head)
    (git_repo / "build").mkdir()
    p1 = prompt("p1", "clean up", 1)
    events = [bash("b1", "p1", "rm -rf dist && mv build /tmp/elsewhere-build && rm old.log", 11)]
    result = attribute_session(session, [p1], events, git_repo, GitState(git_repo))
    assert [(c.path, c.effect, c.strategy) for c in result.changes] == [
        ("dist", "deleted", "none"),
        ("old.log", "deleted", "none"),
    ]  # the rm targets are named; build still exists on disk as a directory, so it is skipped
    assert result.outside_repo == ["/tmp/elsewhere-build"]


def test_shell_write_after_payload_edits_keeps_the_earlier_diffs(git_repo):
    head = git("rev-parse", "HEAD", cwd=git_repo).strip()
    session = Session(id="s", repo=str(git_repo), started_at=T % 0, head_at_start=head)
    p1, p2, p3 = (
        prompt("p1", "create calc.py", 1),
        prompt("p2", "edit calc.py", 2),
        prompt("p3", "sed calc.py", 3),
    )
    v1, v2, v3 = "a\n", "a\nb\n", "a\nB\n"
    (git_repo / "calc.py").write_text(v3)  # what the sed left on disk
    events = [
        write("w", "p1", "calc.py", v1, 11),
        edit("e", "p2", "calc.py", v1, v2, 21),
        bash("b", "p3", "sed -i '' 's/b/B/' calc.py", 31),
    ]
    result = attribute_session(session, [p1, p2, p3], events, git_repo, GitState(git_repo))
    by = {c.prompt_id: c for c in result.changes}
    assert (by["p1"].effect, by["p1"].added, by["p1"].strategy) == ("created", 1, "payload")
    assert (by["p2"].added, by["p2"].removed, by["p2"].strategy) == (1, 0, "payload")
    assert (by["p3"].added, by["p3"].removed, by["p3"].strategy) == (1, 1, "git")
    assert by["p3"].hunks[0].lines == [" a", "-b", "+B"]


def test_shell_write_between_two_edits_is_bridged_by_the_next_original_file(session, tmp_path):
    p1, p2, p3 = prompt("p1", "write f.txt", 1), prompt("p2", "sed f.txt", 2), prompt("p3", "edit f.txt", 3)
    events = [
        write("w", "p1", "f.txt", "one\n", 11),
        bash("b", "p2", "sed -i '' 's/one/two/' f.txt", 21),
        edit("e", "p3", "f.txt", "two\n", "three\n", 31),
    ]
    result = run(session, [p1, p2, p3], events, tmp_path)
    by = {c.prompt_id: c for c in result.changes}
    assert (by["p2"].strategy, by["p2"].added, by["p2"].removed) == ("bridged", 1, 1)
    assert by["p2"].hunks[0].lines == ["-one", "+two"]
    assert by["p1"].strategy == "payload" and by["p3"].strategy == "payload"
    assert result.reverted == []


def test_runner_prefixes_are_peeled_in_any_order():
    assert check_segments("uv run python -m pytest -q") == ["uv run python -m pytest -q"]
    assert check_segments("poetry run python -m pytest") == ["poetry run python -m pytest"]
    assert check_segments("uv run --frozen pytest") == ["uv run --frozen pytest"]
    assert check_segments("uv run python script.py") == []


def test_backfilled_session_diffs_against_the_commit_before_it_started(git_repo):
    import os

    def commit(msg, date):
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        subprocess.run(["git", "commit", "-q", "-am", msg], cwd=git_repo, check=True, env=env)

    (git_repo / "README.md").write_text("x\n")
    commit("a", "2026-01-01T12:00:00Z")
    session = Session(id="s", repo=str(git_repo), started_at="2026-01-02T12:00:00.000Z", head_at_start=None)
    p1 = prompt("p1", "bump README.md", 1)
    events = [bash("b1", "p1", "sed -i '' 's/x/y/' README.md", 11)]
    (git_repo / "README.md").write_text("y\n")
    commit("b", "2026-01-03T12:00:00Z")  # the agent's work, committed after the session
    result = attribute_session(session, [p1], events, git_repo, GitState(git_repo))
    (change,) = result.changes
    assert (change.effect, change.added, change.removed, change.strategy) == ("modified", 1, 1, "git")
    assert result.reverted == []


def test_deleted_directory_expands_to_the_files_it_held(git_repo):
    (git_repo / "docs").mkdir()
    (git_repo / "docs" / "a.md").write_text("a\n")
    (git_repo / "docs" / "b.md").write_text("b\nb\n")
    git("add", "docs", cwd=git_repo)
    git("commit", "-q", "-m", "docs", cwd=git_repo)
    head = git("rev-parse", "HEAD", cwd=git_repo).strip()
    import shutil

    shutil.rmtree(git_repo / "docs")
    session = Session(id="s", repo=str(git_repo), started_at=T % 0, head_at_start=head)
    p1 = prompt("p1", "remove the docs", 1)
    result = attribute_session(
        session, [p1], [bash("b1", "p1", "rm -rf docs", 11)], git_repo, GitState(git_repo)
    )
    assert [(c.path, c.effect, c.removed) for c in result.changes] == [
        ("docs/a.md", "deleted", 1),
        ("docs/b.md", "deleted", 2),
    ]


def test_untracked_file_the_shell_did_not_actually_change_is_not_listed(git_repo):
    import os
    import time

    head = git("rev-parse", "HEAD", cwd=git_repo).strip()
    (git_repo / "old.txt").write_text("old\n")
    long_ago = time.time() - 86400
    os.utime(git_repo / "old.txt", (long_ago, long_ago))
    (git_repo / "fresh.txt").write_text("fresh\n")
    from datetime import UTC, datetime, timedelta

    a_minute_ago = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    session = Session(id="s", repo=str(git_repo), started_at=a_minute_ago, head_at_start=head)
    p1 = prompt("p1", "append to old.txt and write fresh.txt", 1)
    events = [bash("b1", "p1", "echo x >> old.txt", 11), bash("b2", "p1", "echo fresh > fresh.txt", 12)]
    result = attribute_session(session, [p1], events, git_repo, GitState(git_repo))
    assert [(c.path, c.effect) for c in result.changes] == [("fresh.txt", "created")]


def test_repo_without_commits_still_reports_shell_creates_and_deletes(tmp_path):
    git("init", "-q", cwd=tmp_path)
    (tmp_path / "notes.md").write_text("hello\n")
    session = Session(id="s", repo=str(tmp_path), started_at=T % 0, head_at_start=None)
    p1 = prompt("p1", "write notes.md, drop old.py", 1)
    events = [bash("b1", "p1", "printf 'hello\\n' > notes.md", 11), bash("b2", "p1", "rm old.py", 12)]
    result = attribute_session(session, [p1], events, tmp_path, GitState(tmp_path))
    assert [(c.path, c.effect, c.added, c.strategy) for c in result.changes] == [
        ("notes.md", "created", 1, "git"),
        ("old.py", "deleted", 0, "none"),
    ]


def test_earlier_prompts_in_a_shell_run_are_deferred_not_zero(git_repo):
    head = git("rev-parse", "HEAD", cwd=git_repo).strip()
    (git_repo / "README.md").write_text("one\ntwo\nthree\nfour\n")
    session = Session(id="s", repo=str(git_repo), started_at=T % 0, head_at_start=head)
    p1, p2 = prompt("p1", "append to README.md", 1), prompt("p2", "append again to README.md", 2)
    events = [bash("b1", "p1", "echo three >> README.md", 11), bash("b2", "p2", "echo four >> README.md", 21)]
    result = attribute_session(session, [p1, p2], events, git_repo, GitState(git_repo))
    first, last = result.changes
    assert (first.prompt_id, first.strategy, first.hunks) == ("p1", "deferred", [])
    assert (last.prompt_id, last.strategy, last.added) == ("p2", "git", 2)


def test_quotes_variables_and_newlines_in_shell_commands(tmp_path):
    cases = {
        'grep -n "directory\\|rm -rf" docs/x.md | head -40': [],
        "echo 'a; rm -rf b' > note.txt": [("note.txt", "write")],
        'cd "$T" && echo x > f.txt && rm g.txt': [],
        'cd "$T" && echo x > /abs/f.txt': [("/abs/f.txt", "write")],
        "echo hi >notes.txt 2>/dev/null": [("notes.txt", "write")],
        "echo hi > a.txt\necho yo > b.txt": [("a.txt", "write"), ("b.txt", "write")],
        "printf 'x\\ny' > c.txt": [("c.txt", "write")],
        "cd sub; cd ..; echo > d.txt": [("d.txt", "write")],
        "(cd sub && echo > e.txt)": [("sub/e.txt", "write")],
        "rm -f x.txt 2>/dev/null": [("x.txt", "delete")],
        "rm -f y.txt 2>&1": [("y.txt", "delete")],
        "mv a.txt b.txt 1>log.txt": [("log.txt", "write"), ("b.txt", "write"), ("a.txt", "delete")],
    }
    for command, expected in cases.items():
        assert bash_written_paths(command, tmp_path) == expected, command


def test_the_store_directory_is_never_attributed(session, tmp_path):
    p1 = prompt("p1", "move the db", 1)
    events = [
        bash("b1", "p1", "mv .graphene/graphene.db /tmp/elsewhere.db && rm .graphene/graphene.db-shm", 11)
    ]
    result = run(session, [p1], events, tmp_path)
    assert result.changes == []
    assert result.outside_repo == ["/tmp/elsewhere.db"]


def test_files_inside_a_nested_checkout_are_outside_the_repo(tmp_path):
    """A worktree under .claude/worktrees/ (Claude Code puts them there) is another checkout."""
    from graphene_debrief.sources.claude_code import relative_path

    worktree = tmp_path / ".claude" / "worktrees" / "agent-1"
    (worktree / "src").mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: elsewhere\n")
    inside = str(worktree / "src" / "app.py")
    assert relative_path(inside, tmp_path) == inside
    assert relative_path(str(tmp_path / "src" / "app.py"), tmp_path) == "src/app.py"
    assert bash_written_paths(f"echo x > {inside}", tmp_path) == [(inside, "write")]
    session = Session(id="s", repo=str(tmp_path), started_at="2026-01-01T00:00:00.000Z")
    ev = ToolEvent("e1", "s", "p1", "2026-01-01T00:00:01.000Z", "Write", {"file_path": inside})
    ev.response = {"type": "create"}
    ev.file_path = relative_path(inside, tmp_path)
    prompts = [Prompt("p1", "s", 1, "2026-01-01T00:00:00.500Z", "go")]
    result = attribute_session(session, prompts, [ev], tmp_path)
    assert result.changes == [] and result.outside_repo == [inside]
