"""Commits read from git for a session's window, and credited to the call that made them.

The synthetic run's real git repo is the ground truth: `sync_commits` has to reach exactly the
commits `tests/fixtures/make_run_fixture.py` says are there, with the same credit, and the map
drawn from them has to stay byte-identical to the golden graph.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from graphene_debrief.attribute import attribute
from graphene_debrief.commits import credit, sync_commits
from graphene_debrief.graph import build_graph, to_json
from graphene_debrief.model import Commit, Prompt, Session, ToolEvent
from graphene_debrief.record import changes, coverage
from graphene_debrief.store import Store

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import make_run_fixture as run  # noqa: E402

GOLDEN = Path(__file__).parent / "fixtures" / "run_graph.json"
T = "2026-03-02T09:%02d:%02d.000Z"


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


# 2 -- the credit rule ---------------------------------------------------------------------------


def bash(eid: str, minute: int, command: str, response: object, agent: str | None = None) -> ToolEvent:
    return ToolEvent(eid, run.S1, "p1", T % (minute, 0), "Bash", {"command": command}, response, True, agent)


def one(sha: str) -> list[Commit]:
    return [Commit(sha, T % (5, 0), "parser: read the import file")]


SHA = run.SHAS["parser"]  # 4d35474499bd...


def test_a_prefix_inside_a_longer_hex_word_or_a_plain_number_credits_nothing():
    commits = one(SHA)
    longer, number = SHA[:12] + "9" + SHA[13:20], SHA[:7].replace("d", "1").replace("a", "2")
    credit(commits, [bash("b1", 5, "git commit -q -m x", {"stdout": f"{longer} {number}"})])
    assert commits[0].session_id is None
    credit(commits, [bash("b2", 6, "git commit -q -m x", {"stdout": f"[main {SHA[:7]}] parser"})])
    assert (commits[0].session_id, commits[0].event_id) == (run.S1, "b2")


def test_a_commit_named_by_two_agents_belongs_to_the_earlier_call():
    commits = one(SHA)
    made = "git commit -q -m x && git log --oneline -1"
    credit(
        commits,
        [
            bash("b2", 9, made, {"content": f"{SHA[:7]} parser"}, agent="second"),
            bash("b1", 7, made, {"stdout": f"{SHA[:7]} parser"}, agent="first"),
        ],
    )
    assert (commits[0].agent_id, commits[0].event_id) == ("first", "b1")


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


# 4 -- one change, one session -------------------------------------------------------------------


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def test_two_overlapping_sessions_are_not_both_credited_the_same_change(tmp_path):
    root, kept = tmp_path / "repo", tmp_path / "store"
    root.mkdir()
    kept.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "README.md").write_text("one\ntwo\n")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "init")
    head = git(root, "rev-parse", "HEAD").strip()
    (root / "README.md").write_text("one\nthree\n")  # what both sessions find on disk now
    with Store.open(kept) as store:
        for sid, ends in (("s1", 30), ("s2", 50)):  # windows overlap; s2 ends last
            store.upsert_session(Session(sid, str(root), T % (0, 0), T % (ends, 0), head_at_start=head))
            store.add_prompt(Prompt(f"p-{sid}", sid, 1, T % (1, 0), "tidy the readme"))
            store.add_event(
                ToolEvent(
                    f"b-{sid}",
                    sid,
                    f"p-{sid}",
                    T % (2, 0),
                    "Bash",
                    {"command": "sed -i '' 's/two/three/' README.md"},
                    {"stdout": ""},
                )
            )
        results = attribute(store, ["s1", "s2"], root)
    told = {sid: [(c.added, c.removed, c.strategy) for c in r.changes] for sid, r in results.items()}
    assert told == {"s1": [(0, 0, "later")], "s2": [(1, 1, "git")]}
