"""One node's record: who held it, what git says changed in its windows, how much of that is
verified, what was refused, and what a person decided about it.

A real git repo and real hook events in every test, because those are the records it reads.
"""

import io
import json
import os
import subprocess

import pytest

from graphene_debrief import node_record as NR
from graphene_debrief import plan
from graphene_debrief.commits import sync_commits
from graphene_debrief.plan import Caller
from graphene_debrief.sources.claude_code import hook_main, ingest_hook_event
from graphene_debrief.store import Store

S1 = "aaaa1111-0000-4000-8000-000000000001"
S2 = "bbbb2222-0000-4000-8000-000000000002"
ALEX = Caller("alex", True)
BOT = Caller("claude:aaaa1111", False, S1)
BOT2 = Caller("claude:bbbb2222", False, S2)


def T(minute: int, second: int = 0) -> str:
    return f"2026-01-05T01:{minute:02d}:{second:02d}.000Z"


def git(repo, *args, at: str | None = None) -> None:
    env = None
    if at is not None:
        stamp = at.replace("T", " ").replace(".000Z", " +0000")
        env = {**os.environ, "GIT_COMMITTER_DATE": stamp, "GIT_AUTHOR_DATE": stamp}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def head(repo) -> str:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "T")
    for path, text in {
        "src/api/users.py": "def users():\n    return []\n",
        "src/db/schema.py": "TABLES = []\n",
        "README.md": "# toy\n",
    }.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "start", at="2026-01-05T00:00:00.000Z")
    return tmp_path


@pytest.fixture
def store(repo):
    with Store.open(repo) as s:
        yield s


def api_node(**extra) -> dict:
    return {"title": "users endpoint", "scope": ["src/api/**"], "check": "true", **extra}


# -- the records a real session leaves ----------------------------------------------------------


def session(store, repo, sid, at) -> None:
    ingest_hook_event(
        store,
        {"session_id": sid, "cwd": str(repo), "hook_event_name": "SessionStart", "source": "startup"},
        repo,
        at,
    )


def wrote(store, repo, sid, rel, text, at, n) -> None:
    """A Write the vendor reports after the fact, and the file really changes."""
    path = repo / rel
    before = path.read_text() if path.exists() else None
    path.write_text(text)
    response = {"type": "update" if before else "create", "filePath": str(path), "content": text}
    ingest_hook_event(
        store,
        {
            "session_id": sid,
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_use_id": f"w{n}",
            "tool_input": {"file_path": str(path), "content": text},
            "tool_response": response | ({"originalFile": before} if before else {}),
        },
        repo,
        at,
    )


def committed(store, repo, sid, message, at, n) -> str:
    """A commit made by the agent's own shell, with the SHA its output printed: that is what credits it."""
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message, at=at)
    sha = head(repo)
    ingest_hook_event(
        store,
        {
            "session_id": sid,
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_use_id": f"b{n}",
            "tool_input": {"command": "git commit -am x && git log --oneline -1"},
            "tool_response": {"stdout": f"{sha[:7]} {message}"},
        },
        repo,
        at,
    )
    sync_commits(store, repo, [sid])
    return sha


def hook(repo, name, **extra):
    event = {"session_id": S1, "cwd": str(repo), "hook_event_name": name, **extra}
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


# -- the windows --------------------------------------------------------------------------------


def test_a_node_held_twice_has_a_window_each_with_the_session_that_held_it(store, repo):
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    plan.release(store, "n1", BOT, "the schema has to change", now=T(2))
    plan.start(store, "n1", BOT2, repo, now=T(3))
    plan.finish(store, "n1", BOT2, now=T(4))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(9))
    assert [
        (w.n, w.executor, w.session_id, w.started_at, w.ended_at, w.ended_by, w.said) for w in record.windows
    ] == [
        (1, "claude:aaaa1111", S1, T(1), T(2), "released", "the schema has to change"),
        (2, "claude:bbbb2222", S2, T(3), T(4), "finished", ""),
    ]
    assert [w.base_sha for w in record.windows] == [head(repo), head(repo)]


def test_a_running_nodes_window_is_still_open_and_reads_the_working_tree(store, repo):
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    (repo / "notes.txt").write_text("scratch")  # outside the scope, and nothing committed it
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(2))
    [w] = record.windows
    assert (w.ended_at, w.ended_by) == (None, "still open")
    assert w.changed == {"notes.txt": "the working tree", "src/api/users.py": "the working tree"}
    assert any("working tree" in line for line in w.sources)
    lines = NR.render(record)
    assert "    in scope: src/api/users.py  (the working tree)" in lines
    assert "    outside the scope: notes.txt  (the working tree)" in lines


def test_a_closed_window_says_which_records_it_used_and_which_one_does_not_exist(store, repo):
    session(store, repo, S1, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    wrote(store, repo, S1, "src/api/users.py", "def users():\n    return [1]\n", T(2), 1)
    sha = committed(store, repo, S1, "the endpoint", T(3), 1)
    plan.finish(store, "n1", BOT, now=T(4))
    [w] = NR.node_record(store, repo, plan.get(store, "n1"), at=T(9)).windows
    assert w.commits == [sha]
    assert w.changed == {"src/api/users.py": f"commit {sha[:7]} and git, when it ended"}
    assert w.sources == [f"from {w.base_sha[:7]} to {sha[:7]}: what git said had changed when it ended"]


def test_work_that_was_never_committed_is_in_the_record_because_git_was_asked_when_the_node_ended(
    store, repo
):
    """The first walkthrough: a node finished without a commit showed "no path is recorded as
    changed", although `done` had just asked git and knew."""
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    plan.finish(store, "n1", BOT, now=T(2))
    [w] = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3)).windows
    assert w.changed == {"src/api/users.py": "git, when it ended"} and w.commits == []


def test_a_window_that_ended_before_that_was_logged_says_what_it_cannot_know(store, repo):
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    store.log_node("n1", T(2), "finished", BOT.name, BOT.session_id)  # as 0.3's first builds logged it
    [w] = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3)).windows
    assert w.changed == {} and "not evidence that nothing else changed" in w.sources[0]


def test_a_path_two_records_attest_says_both_and_a_commit_at_the_very_start_is_inside(store, repo):
    session(store, repo, S1, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    sha = committed(store, repo, S1, "at the very start", T(1), 1)  # the same second it was taken
    (repo / "src/api/users.py").write_text("def users():\n    return [2]\n")  # and changed again since
    [w] = NR.node_record(store, repo, plan.get(store, "n1"), at=T(2)).windows
    assert w.commits == [sha]
    assert w.changed["src/api/users.py"] == f"commit {sha[:7]} and the working tree"


# -- coverage, scoped to the node ------------------------------------------------------------------


def test_coverage_is_graded_over_every_commit_and_this_nodes_are_selected_afterwards(store, repo):
    """The trap: `record.coverage` grades a commit's path by the writes recorded since the previous
    commit of that path *in the list it is given*. A list cut to the node's window first would grade
    the window's first commit against everything before it, here an edit made before the node
    existed, and report work as verified that nothing in the window verifies."""
    session(store, repo, S1, T(0))
    wrote(store, repo, S1, "src/api/users.py", "def users():\n    return [1]\n", T(1), 1)
    committed(store, repo, S1, "before the node", T(2), 1)
    plan.propose(store, [api_node()], ALEX, now=T(3))
    plan.start(store, "n1", BOT, repo, now=T(4))
    (repo / "src/api/users.py").write_text("def users():\n    return [2]\n")  # no write is recorded
    inside = committed(store, repo, S1, "inside the window", T(5), 2)
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(6))
    assert record.windows[0].commits == [inside]
    counts = record.coverage
    assert (counts["commits"], counts["committed_files"]) == (1, 1)
    assert (counts["write"], counts["commit"], counts["nothing"]) == (0, 1, 0)
    assert counts["computed"] and "graded over all 2 commits" in counts["how"]


def test_a_write_recorded_before_the_node_was_taken_verifies_nothing_inside_it(store, repo):
    """The reviewer's probe: no commit of the path between the early write and the start, so grading
    has no floor, and the node's commit read as traced to a recorded write it never had."""
    session(store, repo, S1, T(0))
    wrote(store, repo, S1, "src/api/users.py", "def users():\n    return [1]\n", T(1), 1)
    plan.propose(store, [api_node()], ALEX, now=T(3))
    plan.start(store, "n1", BOT, repo, now=T(4))
    committed(store, repo, S1, "inside the window", T(5), 1)
    counts = NR.node_record(store, repo, plan.get(store, "n1"), at=T(6)).coverage
    assert (counts["committed_files"], counts["write"], counts["commit"]) == (1, 0, 1)


def test_a_commit_inside_the_window_by_a_session_that_did_not_hold_it_is_counted_apart(store, repo):
    session(store, repo, S1, T(0))
    session(store, repo, S2, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    (repo / "src/api/users.py").write_text("def users():\n    return [9]\n")
    committed(store, repo, S2, "someone else, inside the window", T(2), 1)
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3))
    counts = record.coverage
    assert counts["computed"] and (counts["not_graded_commits"], counts["not_graded_files"]) == (1, 1)
    assert "not graded, and not counted above" in "\n".join(NR.render(record))


def test_a_recorded_write_inside_the_window_is_what_verifies_the_commit(store, repo):
    session(store, repo, S1, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    wrote(store, repo, S1, "src/api/users.py", "def users():\n    return [1]\n", T(2), 1)
    committed(store, repo, S1, "the endpoint", T(3), 1)
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(4))
    counts = record.coverage
    assert (counts["committed_files"], counts["write"], counts["edit"]) == (1, 1, 1)
    assert (counts["commit"], counts["nothing"], counts["not_graded_commits"]) == (0, 0, 0)


def test_a_commit_no_recorded_session_accounts_for_is_counted_apart_and_never_graded(store, repo):
    session(store, repo, S1, T(0))  # a session ran, so git's commits reach the store
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", ALEX, repo, now=T(1))  # but a person holds the node: no session to trace
    (repo / "src/api/users.py").write_text("def users():\n    return [3]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "by hand", at=T(2))
    sync_commits(store, repo, [S1])
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3))
    counts = record.coverage
    assert record.windows[0].commits == [head(repo)]
    assert not counts["computed"] and counts["how"].startswith("not computed: no session is recorded")
    assert (counts["committed_files"], counts["write"]) == (0, 0)  # nothing is graded, so nothing counts
    assert (counts["not_graded_commits"], counts["not_graded_files"]) == (1, 1)
    printed = "\n".join(NR.render(record))
    assert "coverage: not computed" in printed and "1 commit inside its windows (1 file)" in printed


def test_a_node_handed_back_keeps_what_had_changed_by_then(store, repo):
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    (repo / "src/db/schema.py").write_text("half an idea\n")
    plan.release(store, "n1", BOT, "stuck", now=T(2))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3))
    assert record.windows[0].changed == {"src/db/schema.py": "git, when it ended"}
    assert "    outside the scope: src/db/schema.py  (git, when it ended)" in NR.render(record)


# -- what was refused, and what a person decided -----------------------------------------------------


def test_what_was_refused_is_counted_from_the_log(store, repo):
    plan.propose(store, [api_node(check="grep -q 'return .1.' src/api/users.py")], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    schema = {"file_path": str(repo / "src/db/schema.py")}
    denied = hook(repo, "PreToolUse", tool_name="Edit", tool_input=schema)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert hook(repo, "Stop", stop_hook_active=False)["decision"] == "block"
    hook(
        repo,
        "PostToolUse",
        tool_name="Bash",
        tool_use_id="b9",
        tool_input={"command": "python rewrite.py"},
        tool_response={"stdout": "", "bashEditDiff": {"changedFiles": [str(repo / "src/db/schema.py")]}},
    )
    (repo / "notes.txt").write_text("stray")
    with pytest.raises(plan.Refused, match="outside its scope"):
        plan.finish(store, "n1", BOT, now=T(2))
    (repo / "notes.txt").unlink()
    with pytest.raises(plan.Refused, match="failed"):
        plan.finish(store, "n1", BOT, now=T(3))
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    plan.finish(store, "n1", BOT, now=T(4))
    refused = NR.node_record(store, repo, plan.get(store, "n1"), at=T(5)).refusals
    assert refused.denied == ["src/db/schema.py"]
    assert refused.breaches == ["src/db/schema.py"]
    assert (refused.stops, refused.done, refused.checks_failed) == (1, [["notes.txt"]], 1)
    assert refused.last_check["result"] == "passed"


def test_the_persons_acts_are_kept_with_what_they_said(store, repo):
    plan.propose(store, [api_node(signoff=True)], BOT, now=T(0))
    plan.accept(store, ["n1"], ALEX, now=T(1))
    plan.edit(store, "n1", {"scope": ["src/api/users.py"]}, ALEX, now=T(2))
    plan.start(store, "n1", BOT, repo, now=T(3))
    plan.finish(store, "n1", BOT, now=T(4))
    plan.reopen(store, "n1", ALEX, "returns a list, I asked for a dict", now=T(5))
    plan.start(store, "n1", BOT, repo, now=T(6))
    (repo / "README.md").write_text("# changed\n")
    plan.finish(store, "n1", ALEX, now=T(7), override="the README edit was mine")
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(8))
    assert (record.windows[-1].ended_at, record.windows[-1].ended_by) == (T(7), "overruled")
    acts = record.acts
    assert [(a.at, a.kind, a.actor) for a in acts] == [
        (T(1), "accepted", "alex"),
        (T(2), "edited", "alex"),
        (T(5), "reopened", "alex"),
        (T(7), "overruled", "alex"),
    ]
    assert acts[1].said == "scope: ['src/api/**'] -> ['src/api/users.py'] (revision 2)"
    assert acts[2].said == "returns a list, I asked for a dict"
    assert acts[3].said == "the README edit was mine (outside its scope: README.md)"


# -- the lines ---------------------------------------------------------------------------------------


def test_the_record_reads_as_plain_lines(store, repo):
    base = head(repo)
    session(store, repo, S1, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    hook(repo, "PreToolUse", tool_name="Edit", tool_input={"file_path": str(repo / "src/db/schema.py")})
    plan.release(store, "n1", BOT, "the schema has to change", now=T(2))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3))
    assert NR.render(record) == [
        "n1  users endpoint",
        "  state: open · owner agent",
        f"  window 1: claude:aaaa1111, session {S1}  {T(1)} -> {T(2)}  released: the schema has to change",
        f"    from {base[:7]}: what git said had changed when it ended",
        "    nothing changed",
        "  coverage: no commit was made inside its windows, so there is nothing to grade yet",
        "  refused: 1 write denied",
        "    denied: src/db/schema.py",
        "  what people did to it:",
        f"    {T(2)}  released  claude:aaaa1111  the schema has to change",
    ]


def test_the_record_is_json_and_every_line_is_whole(store, repo):
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(2))
    as_dict = NR.to_dict(record)
    assert json.loads(json.dumps(as_dict))["windows"][0]["session_id"] == S1
    assert all(line == line.rstrip() and "…" not in line for line in NR.render(record))
