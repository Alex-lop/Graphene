"""Red first in core (graphene_map.precheck): every accepted leaf's check run once at the base commit,
with no model. The verdict is passes, outside or red, read from the exit code and the output."""

import subprocess

import pytest

from graphene_map import plan as P
from graphene_map import precheck as K
from graphene_map.store import Store

ME = P.Caller("alex", True)
BOT = P.Caller("planner:claude", False, "s1")
FAILS = "python3 -c 'import sys; sys.exit(1)'"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS"):
        monkeypatch.delenv(name, raising=False)
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        git(tmp_path, *args)
    (tmp_path / ".gitignore").write_text(".graphene/\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "tests" / "test_other.py").write_text("raise SystemExit('other is broken')\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "start")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def leaves(store, *specs, who=ME):
    P.propose(store, [{"id": i, "title": i, "scope": s, "check": c} for i, s, c in specs], who)


def test_a_check_that_passes_at_base_is_a_passes_row_with_its_why(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "true"))
        [(_, d)] = K.run(store, repo)
        [row] = store.node_log("a", ("precheck",))
    assert d["verdict"] == "passes" and d["why"] == "it exits 0 before any work is done"
    assert row["detail"] == d and d["exit"] == 0 and d["paths"] == [] and d["base"] and d["tree"]


def test_a_check_failing_for_the_file_its_leaf_writes_is_red_and_says_nothing(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "python3 new.py"))
        rows = K.run(store, repo)
    [(_, d)] = rows
    assert d["verdict"] == "red" and d["paths"] == []
    assert [line for line in K.said(rows) if not line.startswith("red first")] == []


def test_a_failing_tracked_file_outside_the_scope_is_outside_with_that_path(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "python3 tests/test_other.py"))
        rows = K.run(store, repo)
    [(_, d)] = rows
    assert d["verdict"] == "outside" and d["paths"] == ["tests/test_other.py"]
    assert K.said(rows)[0].startswith("a: its check names tests/test_other.py, outside its scope, at ")


def test_a_check_naming_another_leafs_new_test_file_is_outside(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "python3 tests/test_new.py"), ("b", ["tests/test_new.py"], "true"))
        rows = {n.id: d for n, d in K.run(store, repo)}
    assert rows["a"]["verdict"] == "outside" and rows["a"]["paths"] == ["tests/test_new.py"]


def test_a_kept_verdict_is_not_run_again_but_a_commit_or_an_edited_check_runs_it(repo, monkeypatch):
    asked = []
    monkeypatch.setattr(K, "_here", lambda command, root: asked.append(command) or (0, ""))
    with Store.open(repo) as store:
        leaves(store, ("a", ["new.py"], "true"))
        K.run(store, repo)
        [(_, kept)] = K.run(store, repo)
        assert asked == ["true"] and kept["kept"] and len(store.node_log("a", ("precheck",))) == 1
        (repo / "app.py").write_text("x = 2\n")
        git(repo, "commit", "-qam", "next")
        K.run(store, repo)
        assert asked == ["true", "true"]
        P.edit(store, "a", {"check": "true && true"}, ME)
        K.run(store, repo)
        assert asked == ["true", "true", "true && true"]
        K.run(store, repo, again=True)
        assert len(asked) == 4


def test_two_leaves_with_one_check_run_it_once_and_a_proposed_leaf_is_skipped(repo, monkeypatch):
    asked = []
    monkeypatch.setattr(K, "_here", lambda command, root: asked.append(command) or (1, "nope"))
    with Store.open(repo) as store:
        leaves(store, ("a", ["a.py"], FAILS), ("b", ["b.py"], FAILS))
        leaves(store, ("p", ["p.py"], "false"), who=BOT)
        rows = K.run(store, repo)
        assert [n.id for n, _ in rows] == ["a", "b"] and asked == [FAILS]
        assert store.node_log("p", ("precheck",)) == []


def test_the_header_line_has_the_count_the_commit_and_the_wall_time(repo):
    with Store.open(repo) as store:
        leaves(store, ("a", ["a.py"], "true"), ("b", ["b.py"], "false"))
        rows = K.run(store, repo)
    lines = K.said(rows)
    assert lines[0].startswith("a: its check passes at the base commit ")
    assert "`graphene node set a --check" in lines[0]
    assert lines[-1].startswith("red first: 2 checks at ") and lines[-1].endswith(" s")
    assert f" in {rows.seconds:.0f} s" in lines[-1]
