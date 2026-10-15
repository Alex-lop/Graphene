"""One node's record: who held it, what git says changed in its windows, how much of that is
verified, what was refused, and what a person decided about it.

A real git repo and real hook events in every test, because those are the records it reads.
"""

import io
import json
import os
import subprocess

import pytest

from graphene_map import node_record as NR
from graphene_map import plan
from graphene_map.commits import sync_commits
from graphene_map.hooks import hook_main, ingest_hook_event
from graphene_map.plan import Caller
from graphene_map.store import Store

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


def committed(store, repo, sid, message, at, n, sync=True) -> str:
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
    if sync:
        sync_commits(store, repo, [sid])
    return sha


def hook(repo, name, **extra):
    event = {"session_id": S1, "cwd": str(repo), "hook_event_name": name, **extra}
    out = io.StringIO()
    assert hook_main(io.StringIO(json.dumps(event)), cwd=repo, stdout=out) == 0
    return json.loads(out.getvalue()) if out.getvalue() else None


# -- the windows --------------------------------------------------------------------------------


def test_a_node_held_twice_has_a_window_each_with_the_session_that_held_it(store, repo, finish):
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    plan.release(store, "n1", BOT, "the schema has to change", now=T(2))
    plan.start(store, "n1", BOT2, repo, now=T(3))
    finish(store, repo, "n1", BOT2, now=T(4))
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


def test_a_node_nobody_committed_in_still_has_a_coverage_line_over_what_git_said_changed(store, repo):
    """The second walkthrough: the README never commits, Graphene never commits, and every node's
    coverage read zero of zero. What changed under a node is graded whether or not it was committed."""
    session(store, repo, S1, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    wrote(store, repo, S1, "src/api/users.py", "def users():\n    return [1]\n", T(2), 1)
    (repo / "src/api/helpers.py").write_text("# written through a shell nothing recorded\n")
    plan.finish(store, "n1", BOT, now=T(3))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(4))
    counts = record.coverage
    assert (counts["changed_files"], counts["changed_edit"], counts["changed_nothing"]) == (2, 1, 1)
    assert (
        "  coverage: of the 2 paths git said had changed under this node, 2 inside its scope; "
        "1 to a recorded edit, 0 to a recorded shell command, 1 to git alone"
    ) in NR.render(record)


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


def test_a_node_done_by_an_executor_no_vendor_records_still_has_a_coverage_line(store, repo):
    """Codex, `graphene run --with <anything>`, or a person at a terminal: nothing recorded a
    session, an event or a transcript, so the store holds none. The record is still computed, from
    the node's own log, from git, and from the check Graphene ran itself, and it says so: no count
    is a misleading zero and no path is claimed to trace to a write nobody recorded."""
    codex = Caller("codex:deadbeef", False, None)
    plan.propose(store, [api_node(check="test -f src/api/users.py")], ALEX, now=T(0))
    plan.start(store, "n1", codex, repo, now=T(1))
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the endpoint", at=T(2))
    plan.finish(store, "n1", codex, now=T(3))
    assert store.sessions() == [] and store.commits_between("0000", "9999") == []

    counts = NR.node_record(store, repo, plan.get(store, "n1"), at=T(9)).coverage
    assert counts["changed_computed"]
    assert (counts["changed_files"], counts["changed_in_scope"]) == (1, 1)  # git's own answer
    assert (counts["changed_edit"], counts["changed_shell"]) == (0, 0)  # and nothing is claimed
    assert counts["changed_nothing"] == 1
    assert counts["commits"] == 1  # asked of git: the store never held this commit

    printed = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(9)))
    [short] = [line for line in printed if line.startswith("  in short: ")]
    alone = "  in short: 1 file changed, inside its scope; no record of who edited it, so git's word alone"
    assert short.startswith(alone), short
    assert not any(line.startswith("  coverage:") for line in printed)  # nothing traced: in short said it
    assert (
        "    read from: the node's log and git. No vendor keeps records for codex:deadbeef, so "
        in "\n".join(printed)
    )
    assert any(line.startswith("    check: `test -f src/api/users.py` passed at ") for line in printed)
    assert any(line.endswith(", run by Graphene itself") for line in printed)
    assert "1 commit inside its windows (1 file), not graded:" in "\n".join(printed)
    assert "not computed" not in "\n".join(printed)  # every count here has evidence behind it


def test_the_check_says_its_last_line_and_that_it_also_passed_at_the_base_before_any_work(store, repo):
    """The check line said "passed" and no more: not what it printed last, nor that red first saw it pass
    at the base commit, before any work, where it shows nothing about the change. And three coverage
    sentences (7 paths traced; 0 files of 1 commit traced; 1 commit not graded) read as a contradiction to
    a stranger: one plain sentence opens them."""
    codex, base = Caller("codex:deadbeef", False, None), head(repo)
    check = "printf 'collected 12 items\\n\\n\\033[32m12 passed\\033[0m\\n\\n'"  # its colour is not said
    plan.propose(store, [api_node(check=check)], ALEX, now=T(0))
    passes = {"rev": 1, "check": check, "base": base, "verdict": "passes", "why": "it exits 0"}
    store.log_node("n1", T(0, 30), "precheck", "graphene:precheck", None, None, passes)
    plan.start(store, "n1", codex, repo, now=T(1))
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the endpoint", at=T(2))
    plan.finish(store, "n1", codex, now=T(3))
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(9)))
    at = next(k for k, line in enumerate(lines) if line.startswith("    check: "))
    assert lines[at + 1 : at + 3] == [
        "      its last line: 12 passed",
        f"      it also passed at the base commit {base[:7]}, before any work: it shows nothing about "
        "this change",
    ]
    assert not any(line.startswith("  coverage:") for line in lines)  # nothing traced: in short says so
    [short] = [line for line in lines if line.startswith("  in short: ")]
    assert short == ("  in short: 1 file changed, inside its scope; no record of who edited it, so git's "
                     "word alone; the 1 commit inside its windows is in no record of a session that held it")


def test_a_check_that_failed_after_passing_at_the_base_is_never_said_to_show_nothing(store, repo):
    """A check that passed at the base and then failed read "failed", then "it also passed at the base
    commit, before any work: it shows nothing about this change", though its failure is what the work did."""
    codex, base = Caller("codex:deadbeef", False, None), head(repo)
    check = "test ! -e src/api/new.py"
    plan.propose(store, [api_node(check=check)], ALEX, now=T(0))
    passes = {"rev": 1, "check": check, "base": base, "verdict": "passes", "why": "it exits 0"}
    store.log_node("n1", T(0, 30), "precheck", "graphene:precheck", None, None, passes)
    plan.start(store, "n1", codex, repo, now=T(1))
    (repo / "src/api/new.py").write_text("x = 1\n")
    with pytest.raises(plan.Refused):
        plan.finish(store, "n1", codex, now=T(3))
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(9)))
    assert any(line.startswith(f"    check: `{check}` failed at ") for line in lines), lines
    assert f"      it passed at the base commit {base[:7]}, before any work" in lines
    assert not any("shows nothing about this change" in line for line in lines)


def test_a_check_that_printed_nothing_is_said_so_not_given_graphenes_placeholder_as_its_line(store, repo):
    codex = Caller("codex:deadbeef", False, None)
    plan.propose(store, [api_node(check="true")], ALEX, now=T(0))
    plan.start(store, "n1", codex, repo, now=T(1))
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    plan.finish(store, "n1", codex, now=T(3))
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(9)))
    at = next(k for k, line in enumerate(lines) if line.startswith("    check: "))
    assert lines[at + 1] == "      it printed nothing" and "no output" not in "\n".join(lines)


def test_every_denied_and_breached_path_is_named_and_only_the_refused_commands_are_capped():
    """The cap meant for the commands an executor was refused cut every refusal list at three, and the
    paths a hand-back is about were hidden behind "and 2 more"."""
    paths = ["docs/a.md", "docs/b.md", "src/c.py", "src/d.py", "src/d.py"]
    said = NR._refusal_lines(NR.Refusals(denied=paths, breaches=paths[:4], commands=["w", "x", "y", "z"]))
    assert "    denied: docs/a.md, docs/b.md, src/c.py, src/d.py ×2" in said
    assert "    refused after the fact: docs/a.md, docs/b.md, src/c.py, src/d.py" in said
    assert "    refused to the executor: w, x and 2 more" in said


def test_another_sessions_commit_inside_the_window_is_not_called_the_nodes_nor_said_to_be_unrecorded(
    store, repo
):
    """A commit another recorded session made inside n1's window read "its 1 commit is in no session's
    records": it was session bbbb2222's, and the store held its record."""
    session(store, repo, S1, T(0))
    session(store, repo, S2, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    (repo / "README.md").write_text("# someone else's\n")
    committed(store, repo, S2, "someone else, inside the window", T(2), 1)
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(3)))
    [short] = [line for line in lines if line.startswith("  in short: ")]
    assert "the 1 commit inside its windows is in no record of a session that held it" in short, short
    below = "    1 commit inside its windows (1 file) is in no record of a session that held it: not graded, "
    assert below + "and not counted above" in lines


def test_a_commit_in_the_nodes_first_second_is_inside_its_window(store, repo):
    """The log keeps milliseconds and git keeps whole seconds, so a node started at …:34.160 and a
    commit stamped …:34 cannot be put in order. Comparing them as floats dropped every commit made
    in the node's first second, which is most of them when an agent commits and finishes at once:
    the first dogfood run of this record said "no commit was made inside its windows" over one."""
    codex = Caller("codex:deadbeef", False, None)
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", codex, repo, now="2026-01-05T01:01:00.400Z")  # as `_now` really writes it
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the endpoint", at=T(1))  # git stamps it …01:01:00, with no fraction
    plan.finish(store, "n1", codex, now=T(2))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3))
    assert record.windows[0].commits == [head(repo)]
    assert record.coverage["commits"] == 1


def test_a_commit_the_node_started_from_is_not_counted_under_it(store, repo):
    """The other half of the same second. The dogfood run's repo was set up and the node started
    inside one second, and the base commit -- README.md and all -- was then reported as changed
    under the node. Ancestry settles what the clock cannot: git already had it at the base."""
    base = head(repo)
    codex = Caller("codex:deadbeef", False, None)
    plan.propose(store, [api_node()], ALEX, now=T(0))
    (repo / "src/api/users.py").write_text("def users():\n    return [0]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "just before the node", at=T(1))  # …01:01:00, and HEAD at the start
    before = head(repo)
    plan.start(store, "n1", codex, repo, now="2026-01-05T01:01:00.900Z")  # the same second
    assert plan.get(store, "n1").base_sha == before
    (repo / "src/api/users.py").write_text("def users():\n    return [1]\n")
    plan.finish(store, "n1", codex, now=T(2))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(3))
    assert record.windows[0].commits == []  # neither the base nor its parent
    assert base not in record.windows[0].changed.values()
    assert record.coverage["commits"] == 0
    assert "no commit was made inside its windows" in "\n".join(NR.render(record))


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


def test_the_record_reads_the_commits_itself_with_no_page_to_fill_them(store, repo):
    """The web UI filled the store's commits. Without it, `node show` fills them for the sessions
    that held the node, so a commit is still credited to the call that made it."""
    session(store, repo, S1, T(0))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    wrote(store, repo, S1, "src/api/users.py", "def users():\n    return [1]\n", T(2), 1)
    committed(store, repo, S1, "the endpoint", T(3), 1, sync=False)
    counts = NR.node_record(store, repo, plan.get(store, "n1"), at=T(4)).coverage
    assert (counts["committed_files"], counts["write"], counts["edit"]) == (1, 1, 1)


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
    assert not counts["computed"] and counts["how"].startswith("not computed: no session's records")
    assert (counts["committed_files"], counts["write"]) == (0, 0)  # nothing is graded, so nothing counts
    assert (counts["not_graded_commits"], counts["not_graded_files"]) == (1, 1)
    printed = "\n".join(NR.render(record))
    assert "1 commit inside its windows (1 file), not graded:" in printed
    # what git said changed is still counted: only the grading is missing, and the line says which
    assert counts["changed_computed"] and (counts["changed_files"], counts["changed_nothing"]) == (1, 1)


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
    # the first `done` ran the check too: notes.txt, a file git does not track, was left out of the
    # check's worktree in case the check made it, and the check failed there as well
    assert (refused.stops, refused.done, refused.checks_failed) == (1, [["notes.txt"]], 2)
    assert refused.last_check["result"] == "passed"


def test_a_done_refused_again_over_the_same_paths_is_said_once_with_how_often():
    """The judge's `node show` listed "`done` refused over: x.txt" six times: three attempts, each
    refused at the executor's own `done` and again at the run's. One line for each set of paths."""
    refused = NR.Refusals(done=[["x.txt"]] * 6 + [[], ["a.txt", "b.txt"], []])
    assert NR._refusal_lines(refused) == [
        "  refused: 9 `done` refused",
        "    `done` refused 6 times over: x.txt",
        "    `done` refused 2 times over: a failing check",
        "    `done` refused over: a.txt, b.txt",
    ]


def test_the_persons_acts_are_kept_with_what_they_said(store, repo, finish):
    plan.propose(store, [api_node(signoff=True)], BOT, now=T(0))
    plan.accept(store, ["n1"], ALEX, now=T(1))
    plan.edit(store, "n1", {"scope": ["src/api/users.py"]}, ALEX, now=T(2))
    plan.start(store, "n1", BOT, repo, now=T(3))
    finish(store, repo, "n1", BOT, now=T(4))
    plan.reopen(store, "n1", ALEX, "returns a list, I asked for a dict", now=T(5))
    plan.start(store, "n1", BOT, repo, now=T(6))
    (repo / "README.md").write_text("# changed\n")
    finish(store, repo, "n1", ALEX, now=T(7), override="the README edit was mine")
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(8))
    assert (record.windows[-1].ended_at, record.windows[-1].ended_by) == (T(7), "overruled")
    acts = record.acts
    assert [(a.at, a.kind, a.actor) for a in acts] == [
        (T(1), "accepted", "alex"),
        (T(2), "edited", "alex"),
        (T(5), "reopened", "alex"),
        (T(7), "overruled", "alex"),
    ]
    assert acts[1].said == "scope: src/api/** → src/api/users.py (revision 2)"  # as `plan log` says it
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
        "  coverage: git says nothing changed under this node",
        "    check: none has run for this node, so nothing here is verified by one",
        "    no commit was made inside its windows, so there is no commit to grade",
        "  refused: 1 write denied",
        "    denied: src/db/schema.py",
        "  what people did to it:",
        f"    {T(2)}  released  claude:aaaa1111  the schema has to change",
    ]


def test_every_line_of_the_record_is_whole(store, repo):
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", BOT, repo, now=T(1))
    record = NR.node_record(store, repo, plan.get(store, "n1"), at=T(2))
    assert all(line == line.rstrip() and "…" not in line for line in NR.render(record))


def test_a_leaf_a_run_landed_says_how_to_take_it_back_and_the_command_does(repo):
    """Each leaf lands as one --no-ff merge, so `git revert -m 1` takes back exactly it; nothing said so."""
    from graphene_map.run import run_parallel

    (repo / ".gitignore").write_text(".graphene/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the store is not the code")
    with Store.open(repo) as store:
        a = {"id": "a", "title": "write a", "scope": ["a.txt"], "check": "test -s a.txt"}
        plan.propose(store, [a, {**a, "id": "b", "scope": ["b.txt"], "check": "test -s b.txt"}], ALEX)
    run_parallel(lambda: Store.open(repo), repo, repo, 1, "sh -c 'echo a > a.txt'", only=["a"], say=[].append)
    with Store.open(repo) as store:
        merge = store.node_log("a", ("landed",))[-1]["detail"]["commit"]
        lines = NR.render(NR.node_record(store, repo, plan.get(store, "a")))
        assert f"  take it back: git revert -m 1 {merge[:7]}" in lines, lines
        plan.start(store, "b", BOT, repo)
        (repo / "b.txt").write_text("b\n")
        plan.finish(store, "b", BOT)  # done in place: no merge of its own to take back
        lines = NR.render(NR.node_record(store, repo, plan.get(store, "b")))
        assert not any("take it back" in line for line in lines), lines
    git(repo, "revert", "-m", "1", "--no-edit", merge[:7])
    assert not (repo / "a.txt").exists()


def test_a_fork_still_running_on_a_leaf_that_is_not_reads_stopped():
    """:stop or Ctrl-C mid-fork ends the fork threads before they write their end, so the leaf came back
    and its forks still said running while nothing ran. Read against the leaf's state, such a fork was
    stopped; the counts on its row are the ones it started with, so none is given. One that ended says
    what it said."""
    box = {"checkpoint": "forked", "ops": 0, "seconds": 0.0}
    running = {"fork": 1, "of": 2, "model": "m", "state": "running", "why": ""} | box
    ended = {"fork": 2, "of": 2, "model": "m", "state": "gave up", "why": "it needs x"} | box | {"ops": 3}
    rows = [{"kind": "started", "detail": {}}, {"kind": "model", "detail": {"attempt": 1, "model": "m"}},
            {"kind": "fork", "detail": running}, {"kind": "fork", "detail": ended}]  # fmt: skip
    assert NR.forks(rows, plan.RUNNING) == [running, ended]  # it runs: as written
    for state in (plan.OPEN, plan.DONE, plan.REVIEW):
        assert NR.forks(rows, state) == [
            {"fork": 1, "of": 2, "model": "m", "state": "stopped",
             "why": "its executor was stopped before this fork ended", "checkpoint": "forked"},
            ended,
        ]  # fmt: skip


# -- each attempt's record, from the meter's rows ----------------------------------------------------


def meter_rows(store, run: Caller, rows: list[tuple[str, str, dict]]) -> None:
    for at, kind, detail in rows:
        store.log_node("n1", at, kind, run.label, run.session_id, None, detail)


def test_an_attempts_last_words_are_said_once_even_when_it_did_more_after_them(store, repo):
    """The after walk (R7): `said last:` and `the last it did:` carried one sentence twice when the executor
    said its last words before its last tool call (`graphene node done`): only the log's last line had been
    taken out of what it did. Its last words are taken out wherever they sit."""
    run = Caller("run:claude", False, "s-1")
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", run, repo, now=T(1))
    said = "done: n1 is done (check passed, nothing outside its scope)"
    meter_rows(store, run, [
        (T(1, 30), "attempt", {"attempt": 1, "log": None}),
        (T(2), "usage", {"model": "claude-sonnet-5-5", "calls": 1, "prompt_tokens": 900,
                         "completion_tokens": 80, "dollars": 0.01, "endpoint": "claude code", "attempt": 1,
                         "turn": 1}),
        (T(2), "said", {"attempt": 1, "text": said}),
        (T(3), "did", {"attempt": 1, "tool": "Bash", "target": "graphene node done n1", "verb": "running"}),
        (T(4), "ended", {"attempt": 1, "exit": 0, "seconds": 150, "meter": "claude", "unread": 0}),
    ])  # fmt: skip
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(5)))
    assert f"    said last: {said}" in lines and f"      {said}" not in lines, lines
    assert "      running graphene node done n1" in lines, lines


def test_a_metered_attempt_that_came_back_says_what_it_ran_and_where_it_was_refused(store, repo):
    run = Caller("run:claude", False, "s-1")
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", run, repo, now=T(1))

    def turn(n, given, out, dollars):
        return {"model": "claude-sonnet-5-5", "calls": 1, "prompt_tokens": given, "completion_tokens": out,
                "dollars": dollars, "endpoint": "claude code", "attempt": 1, "turn": n}  # fmt: skip

    def did(verb, target):
        return {"attempt": 1, "tool": "Tool", "target": target, "verb": verb}

    meter_rows(store, run, [
        (T(1, 30), "attempt", {"attempt": 1, "log": None}),
        (T(2), "usage", turn(1, 200_000, 4_000, 0.20)),
        (T(2), "did", did("reading", "src/api/users.py")),
        (T(2), "did", did("reading", "src/db/schema.py")),
        (T(3), "usage", turn(2, 212_000, 5_000, 0.20)),
        (T(3), "did", did("editing", "src/api/users.py")),
        (T(3), "did", did("editing", "README.md")),
        (T(3), "denied", {"path": "README.md", "how": "edit"}),
        *[(T(4, k), "did", did("running", "python3 -m pytest -q")) for k in range(3)],
        (T(5), "did", did("running", "graphene node done n1")),
        (T(6), "said", {"attempt": 1, "text": "The endpoint needs README.md too,\nso I stop here."}),
        (T(7), "usage", {"model": "claude-sonnet-5-5", "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                         "dollars": 0.02, "endpoint": "claude code", "attempt": 1, "turns": 2,
                         "reported": 0.42}),
        (T(7, 30), "ended", {"attempt": 1, "exit": 1, "seconds": 360, "meter": "claude", "unread": 0}),
    ])  # fmt: skip
    plan.release(store, "n1", run, "it needs README.md", now=T(8))
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(9)))
    start = lines.index("  attempt 1 · claude claude-sonnet-5-5 · 6m · 2 turns · 412k in, 9k out · "
                        "$0.42 at list price · exit 1")
    assert lines[start + 1 : start + 7] == [
        "    read: src/api/users.py, src/db/schema.py",
        "    edited: src/api/users.py (1 outside the scope: README.md)",
        "    ran: python3 -m pytest -q (3 times), graphene node done n1",
        "    refused: README.md",
        "    said last: The endpoint needs README.md too, so I stop here.",
        "    the last it did:",
    ]
    assert lines[start + 7 : start + 9] == [
        "      reading src/api/users.py",
        "      reading src/db/schema.py",
    ]
    assert "      running graphene node done n1" in lines and "exit 1, no output" not in "\n".join(lines)
    bill = next(k for k, line in enumerate(lines) if line.startswith("  bill: "))
    assert lines[start - 1].startswith("    denied: ") and bill > start  # after the refusals, before the bill
    assert lines[bill] == ("  bill: $0.4200 at list price · 2 model calls · 412,000 tokens in, 9,000 out · "
                           "claude-sonnet-5-5 (Claude Code's report)")  # fmt: skip


def test_a_command_claude_code_refused_its_executor_is_in_the_record_and_offered_to_no_scope(store, repo):
    """Claude Code's own refusal of a command (its result's permission_denials) read "refused: nothing". It is
    a command, not a path: the hand-back offers no scope to widen to it."""
    from graphene_map import meter as M

    run, command, meter = Caller("run:claude", False, "s-1"), "python3 -m unittest -q", M.Meter("claude", 1)
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", run, repo, now=T(1))
    bash = {"command": command}
    stream = [{"type": "assistant", "message": {"id": "m1", "content": [
                  {"type": "tool_use", "id": "t1", "name": "Bash", "input": bash}]}},
              {"type": "result", "total_cost_usd": 0.01, "permission_denials": [
                  {"tool_name": "Bash", "tool_input": bash, "tool_use_id": "t1"}]}]  # fmt: skip
    ended = {"attempt": 1, "exit": 0, "meter": "claude", "unread": 0}
    meter_rows(store, run, [(T(2), "attempt", {"attempt": 1, "log": None}),
                            *((T(3), k, d) for e in stream for k, d in meter.feed(json.dumps(e))),
                            (T(4), "ended", ended)])  # fmt: skip
    plan.release(store, "n1", run, "it cannot run its tests", now=T(5))
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(6)))
    assert "  refused: 1 command refused to the executor" in lines
    assert f"    refused to the executor: {command}" in lines
    assert f"    refused: {command}" in lines and not any(line.startswith("    ran: ") for line in lines)
    assert plan.wanted(store, plan.get(store, "n1")) == []


def test_what_an_attempt_said_last_is_whole_and_wrapped_when_it_is_long(store, repo):
    run, words = Caller("run:claude", False, "s-1"), ("word " * 120).strip() + "!"  # 600 characters
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", run, repo, now=T(1))
    ended = {"attempt": 1, "exit": 0, "meter": "claude", "unread": 0}
    meter_rows(store, run, [(T(2), "attempt", {"attempt": 1, "log": None}),
                            (T(3), "said", {"attempt": 1, "text": words}),
                            (T(4), "ended", ended)])  # fmt: skip
    plan.release(store, "n1", run, "it stops here", now=T(5))
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(6)))
    start = lines.index("    said last:")
    end = next(k for k in range(start + 1, len(lines)) if not lines[k].startswith("      "))
    wrapped = [line.removeprefix("      ") for line in lines[start + 1 : end]]
    assert " ".join(wrapped) == words and all(len(line) <= 100 for line in wrapped), wrapped


def test_a_long_last_message_is_said_once_and_the_last_it_did_is_what_it_did(store, repo):
    """`told` ends with the whole result: node show printed it under "said last" and again as the end of
    "the last it did", cut to its last 2,000 characters, which a long summary filled with itself."""
    run, words = Caller("run:claude", False, "s-1"), ("step done; " * 240).strip()  # 2,639 characters
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", run, repo, now=T(1))
    edit = {"attempt": 1, "tool": "Edit", "target": "src/api/users.py", "verb": "editing"}
    ended = {"attempt": 1, "exit": 0, "meter": "claude", "unread": 0}
    meter_rows(store, run, [(T(2), "attempt", {"attempt": 1, "log": None}), (T(3), "did", edit),
                            (T(4), "said", {"attempt": 1, "text": words}),
                            (T(5), "ended", ended)])  # fmt: skip
    plan.release(store, "n1", run, "it stops here", now=T(6))
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(7)))
    did = lines.index("    the last it did:")
    assert lines[did + 1] == "      editing src/api/users.py", lines[did:]
    assert not any("step done" in line for line in lines[did:])


def test_an_attempt_with_no_meter_shows_the_tail_of_its_log(store, repo, tmp_path):
    run = Caller("run:sh", False, "s-1")
    log = tmp_path / "n1-1.txt"
    log.write_text("".join(f"line {k} of what the executor wrote {'.' * 80}\n" for k in range(200)))
    plan.propose(store, [api_node()], ALEX, now=T(0))
    plan.start(store, "n1", run, repo, now=T(1))
    meter_rows(store, run, [
        (T(1), "attempt", {"attempt": 1, "log": str(log)}),
        (T(3), "ended", {"attempt": 1, "exit": 1, "seconds": 120, "meter": None, "unread": 0}),
    ])  # fmt: skip
    lines = NR.render(NR.node_record(store, repo, plan.get(store, "n1"), at=T(4)))
    start = lines.index("  attempt 1 · sh · 2m · no meter · exit 1")
    assert lines[start + 1] == "    its last lines:"
    shown = [line for line in lines[start + 2 :] if line.startswith("      ")]
    assert shown[-1].startswith("      line 199 of what the executor wrote")
    assert not any(line.startswith("      line 170 ") for line in shown)  # cut to TAIL characters
    assert len("\n".join(s.removeprefix("      ") for s in shown)) <= plan.TAIL


def test_the_bill_counts_attempts_from_their_ends_and_says_who_reported_it():
    def row(kind, **detail):
        return {"kind": kind, "detail": detail}

    turn = {"calls": 1, "prompt_tokens": 10, "completion_tokens": 5, "dollars": 0.01, "model": "m"}
    claude = [row("usage", **turn, turn=k, endpoint="claude code") for k in (1, 2)]
    claude += [row("usage", calls=0, dollars=0.005, endpoint="claude code"), row("ended", attempt=1)]
    said = NR.bill(claude)
    assert (said["attempts"], said["calls"], said["dollars"]) == (1, 2, 0.025)  # ends, not rows
    assert NR.bill(claude[:3])["attempts"] == 1  # without its end: the closing row, not the turns
    assert NR.bill_line(said)[0].endswith("(Claude Code's report)")
    codex = NR.bill([row("usage", **turn, turn=1, endpoint="codex", priced=False)])
    assert NR.bill_line(codex)[0].endswith("10 tokens in, 5 out (15 with no list price) · m (Codex's tokens)")
    both = NR.bill([*claude, row("usage", **turn, endpoint="token factory")])
    assert NR.bill_line(both)[0].endswith("(Claude Code's report and Token Factory's usage)")
    for never in ({"endpoint": "a stand-in"}, {}):  # a stand-in's, or a row from before rows said
        mixed = NR.bill([*claude, row("usage", **turn, **never)])
        assert NR.bill_line(mixed)[0].endswith("(a stand-in's usage)")


def test_the_record_of_several_leaves_says_how_wide_they_ran_and_a_leafs_own_does_not(store, repo):
    """`plan record` and `node show` on a sub-goal print `rolled_up`. A leaf runs its attempts one at a
    time, so its own record would always say 1 of 1, and says nothing."""
    run = Caller("run:claude", False, "s-1")
    plan.propose(store, [api_node(id="api"), api_node(id="db", scope=["src/db/**"])], ALEX, now=T(0))
    for leaf, start, end in (("api", T(1), T(3)), ("db", T(2), T(4))):  # at once from 01:02 to 01:03
        plan.start(store, leaf, run, repo, now=start)
        store.log_node(leaf, start, "attempt", run.label, run.session_id, None, {"attempt": 1})
        store.log_node(leaf, end, "ended", run.label, run.session_id, None, {"attempt": 1, "exit": 0})
    lines = NR.rolled_up(store, repo, plan.leaves(plan.nodes(store)))
    assert lines[-1] == "    2 of 2 at once · 50% of agent minutes alone"
    assert not any("width" in line for line in NR.render(NR.node_record(store, repo, plan.get(store, "api"))))


def test_the_width_in_a_record_is_taken_at_the_records_moment(store, repo):
    """An attempt still running runs up to the record's ``at`` (a replay's clock), not to the wall's."""
    run = Caller("run:claude", False, "s-1")
    plan.propose(store, [api_node(id="api"), api_node(id="db", scope=["src/db/**"])], ALEX, now=T(0))
    for leaf, start in (("api", T(1)), ("db", T(2))):
        plan.start(store, leaf, run, repo, now=start)
        store.log_node(leaf, start, "attempt", run.label, run.session_id, None, {"attempt": 1})
    store.log_node("api", T(3), "ended", run.label, run.session_id, None, {"attempt": 1, "exit": 0})
    # at 01:05 db has run 3 minutes, 1 of them beside api: 3 of 5 agent minutes alone
    lines = NR.rolled_up(store, repo, plan.leaves(plan.nodes(store)), T(5))
    assert lines[-1] == "    2 of 2 at once · 60% of agent minutes alone"
