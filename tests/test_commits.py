"""Commits read from git for a session's window, and credited to the call that made them.

The synthetic run's real git repo is the ground truth: `sync_commits` has to reach exactly the
commits `tests/fixtures/make_run_fixture.py` says are there, with the same credit, and the map
drawn from them has to stay byte-identical to the golden graph.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from graphene_debrief.commits import credit, sync_commits, window
from graphene_debrief.graph import build_graph, to_json
from graphene_debrief.model import Commit, ToolEvent
from graphene_debrief.record import changes, coverage
from graphene_debrief.store import Store

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import make_run_fixture as run  # noqa: E402

GOLDEN = Path(__file__).parent / "fixtures" / "run_graph.json"
T = "2026-03-02T09:%02d:%02d.000Z"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """The scenario's git repo and its outside worktree, built once."""
    base = tmp_path_factory.mktemp("commits")
    run.build_repo(base / "repo", base / "wt-api")
    return base / "repo", base / "wt-api"


@pytest.fixture
def store(tmp_path, repo):
    """The run's records, with every commit row removed: git has to put them back."""
    root, elsewhere = repo
    with Store.open(tmp_path) as opened:
        run.load(opened, root=str(root), elsewhere=str(elsewhere))
        opened.conn.execute("DELETE FROM commit_files")
        opened.conn.execute("DELETE FROM commits")
        yield opened


def rows(store) -> list[tuple]:
    return list(store.conn.execute("SELECT * FROM commits ORDER BY sha")) + list(
        store.conn.execute("SELECT * FROM commit_files ORDER BY sha, path")
    )


# 1 -- the window, from git ----------------------------------------------------------------------


def test_sync_reaches_the_windows_commits_with_their_credit(store, repo):
    root, elsewhere = repo
    sync_commits(store, root, [run.S1, run.S2])
    found = store.commits_between("0000", "9999")
    assert found == run.expected(str(root), str(elsewhere))["commits"]
    assert run.SHAS["base"] not in {c.sha for c in found}  # older than either session


def test_the_map_of_the_synthetic_run_is_the_same_when_git_fills_the_commits(store, repo):
    root, elsewhere = repo
    sync_commits(store, root, [run.S1, run.S2])
    drawn = to_json(build_graph(store, [run.S1]), indent=1) + "\n"
    drawn = drawn.replace(str(root), run.ROOT).replace(str(elsewhere), run.ELSEWHERE)
    drawn = drawn.replace(f'"repo": "{root.name}"', f'"repo": "{Path(run.ROOT).name}"')  # the header name
    assert drawn == GOLDEN.read_text(encoding="utf-8")


def test_coverage_over_the_commits_git_gives_matches_the_ground_truth(store, repo):
    root, elsewhere = repo
    sync_commits(store, root, [run.S1, run.S2])
    written, _ = changes(store.events(run.S1), store.agents(run.S1), str(root))
    cov = coverage(store.commits_between("0000", "9999"), written, [run.S1])
    want = run.expected(str(root), str(elsewhere))["coverage"][run.S1]
    assert {key: getattr(cov, key) for key in want} == want


def test_running_it_twice_changes_nothing(store, repo):
    root, _ = repo
    sync_commits(store, root, [run.S1, run.S2])
    once = rows(store)
    sync_commits(store, root, [run.S1, run.S2])
    assert rows(store) == once


def test_one_git_log_reads_the_window_and_no_git_show_reads_a_commit(store, repo, monkeypatch):
    root, _ = repo
    seen: list[list[str]] = []
    real = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: (seen.append(args), real(args, **kw))[1])
    sync_commits(store, root, [run.S1, run.S2])
    assert [[a for a in call if a in ("log", "show")] for call in seen] == [["log"], ["log"]]


WIDE = ("2000-01-01T00:00:00.000Z", "2099-01-01T00:00:00.000Z")  # a window no test commit falls outside


def test_a_merge_contributes_the_files_it_resolved(tmp_path):
    """Law 7's denominator is every path ``git show --name-only`` lists, and for a merge those are
    the files the conflict resolution touched. Plain ``--name-status`` prints none of them."""
    root = tmp_path / "merged"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "README.md").write_text("one\n")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "init")
    trunk = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    git(root, "checkout", "-q", "-b", "side")
    (root / "README.md").write_text("side\n")
    git(root, "commit", "-q", "-a", "-m", "side")
    git(root, "checkout", "-q", trunk)
    (root / "README.md").write_text("trunk\n")
    git(root, "commit", "-q", "-a", "-m", "trunk")
    subprocess.run(["git", "merge", "side"], cwd=root, capture_output=True, text=True)  # conflicts
    (root / "README.md").write_text("both\n")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "merge side")
    sha = git(root, "rev-parse", "HEAD").strip()

    found = {c.sha: [path for path, _ in c.files] for c in window(root, WIDE[0], WIDE[1])}
    assert found[sha] == git(root, "show", "--name-only", "--format=", sha).split() == ["README.md"]


# 2 -- the credit rule ---------------------------------------------------------------------------


def bash(eid: str, minute: int, command: str, response: object, agent: str | None = None) -> ToolEvent:
    return ToolEvent(eid, run.S1, "p1", T % (minute, 0), "Bash", {"command": command}, response, True, agent)


def one(sha: str, minute: int = 5) -> list[Commit]:
    """A commit made one second into the call that starts at ``minute``: a call makes what did not exist."""
    return [Commit(sha, T % (minute, 1), "parser: read the import file")]


SHA = run.SHAS["parser"]  # 4d35474499bd...


def test_a_prefix_inside_a_longer_hex_word_or_a_plain_number_credits_nothing():
    commits = one(SHA, 6)
    longer, number = SHA[:12] + "9" + SHA[13:20], SHA[:7].replace("d", "1").replace("a", "2")
    credit(commits, [bash("b1", 5, "git commit -q -m x", {"stdout": f"{longer} {number}"})])
    assert commits[0].session_id is None
    credit(commits, [bash("b2", 6, "git commit -q -m x", {"stdout": f"[main {SHA[:7]}] parser"})])
    assert (commits[0].session_id, commits[0].event_id) == (run.S1, "b2")


def test_a_commit_named_by_two_agents_belongs_to_the_earlier_call():
    commits = one(SHA, 7)
    made = "git commit -q -m x && git log --oneline -1"
    credit(
        commits,
        [
            bash("b2", 9, made, {"content": f"{SHA[:7]} parser"}, agent="second"),
            bash("b1", 7, made, {"stdout": f"{SHA[:7]} parser"}, agent="first"),
        ],
    )
    assert (commits[0].agent_id, commits[0].event_id) == ("first", "b1")


def test_a_sha_on_a_later_line_of_the_response_is_read_like_the_first():
    """`git log --oneline -3` prints one commit per line; only the first begins the string."""
    other = run.SHAS["a2"]
    commits = one(SHA) + [Commit(other, T % (5, 2), "api: the handler")]  # both made by this one call
    for separator in ("\n", "\r\n", "\t"):
        for c in commits:
            c.session_id = c.event_id = None
        out = f"{other[:7]} api: the handler{separator}{SHA[:7]} parser: read the import file"
        credit(commits, [bash("b1", 5, "git commit -q -m x && git log --oneline -3", {"stdout": out})])
        assert [c.session_id for c in commits] == [run.S1, run.S1], separator


def test_naming_an_older_commit_is_not_making_it():
    """`git commit -q && git log --oneline -3` prints commits that existed before the call started."""
    older = Commit(run.SHAS["a2"], T % (2, 0), "api: the handler")
    commits = one(SHA) + [older]
    out = f"{SHA[:7]} parser: read the import file\n{older.sha[:7]} api: the handler"
    credit(commits, [bash("b1", 5, "git commit -q -m x && git log --oneline -3", {"stdout": out})])
    assert [(c.session_id, c.event_id) for c in commits] == [(run.S1, "b1"), (None, None)]


def test_a_pick_of_a_commit_nobody_is_recorded_making_keeps_its_origin():
    origin = Commit(run.SHAS["a2"], T % (2, 0), "api: the handler")  # made before any recorded call
    picked = one(SHA)[0]
    out = f"[main {SHA[:7]}] api: the handler"
    pick = bash("b1", 5, f"git cherry-pick {origin.sha[:7]}", {"stdout": out}, agent="picker")
    credit([origin, picked], [pick])
    assert (picked.agent_id, picked.event_id, picked.origin_sha) == ("picker", "b1", origin.sha)
    assert origin.session_id is None  # naming the origin is not making it


def test_a_sha_in_a_nested_content_block_is_read():
    commits = one(SHA)
    response = {"content": [{"type": "text", "text": f"x\n{SHA[:7]} parser"}]}
    credit(commits, [bash("b1", 5, "git commit -q -m x", response)])
    assert commits[0].event_id == "b1"


def test_a_call_that_ran_no_git_commit_credits_nothing():
    commits = one(SHA)
    credit(commits, [bash("b1", 5, "echo 'git commit' && git log --oneline -1", {"stdout": SHA[:7]})])
    assert commits[0].session_id is None


# 3 -- shell changes the vendor calls shared -----------------------------------------------------


def edit(eid: str, minute: int, second: int, path: str, agent: str) -> ToolEvent:
    return ToolEvent(
        eid,
        run.S1,
        "p1",
        T % (minute, second),
        "Edit",
        {"file_path": f"{run.ROOT}/{path}"},
        {},
        True,
        agent,
        path,
    )


def shared(eid: str, minute: int, path: str, agent: str) -> ToolEvent:
    diff = {"changedFiles": [f"{run.ROOT}/{path}"], "moreFiles": 0, "shared": True}
    return ToolEvent(
        eid,
        run.S1,
        "p1",
        T % (minute, 0),
        "Bash",
        {"command": "make"},
        {"stdout": "", "bashEditDiff": diff},
        True,
        agent,
        cwd=run.ROOT,
    )


def test_a_shared_shell_change_gives_way_to_another_agents_edit_in_its_span():
    events = [
        shared("b1", 5, "app/util.py", "w6"),
        edit("e1", 6, 0, "app/util.py", "w5"),
        bash("b2", 10, "true", {"stdout": ""}, agent="w6"),  # bounds the span of the shared call
    ]
    written, _ = changes(events, [], run.ROOT)
    assert [(c.grade, c.event_id) for c in written] == [("edit", "e1")]


def test_a_shared_shell_change_outside_that_span_keeps_its_grade_and_its_flag():
    events = [
        shared("b1", 5, "app/util.py", "w6"),
        bash("b2", 7, "true", {"stdout": ""}, agent="w6"),
        edit("e1", 8, 0, "app/util.py", "w5"),  # after the call the records bound
    ]
    written, _ = changes(events, [], run.ROOT)
    assert [(c.grade, c.shared) for c in written] == [("shell", True), ("edit", False)]
