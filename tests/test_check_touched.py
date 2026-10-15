"""A leaf that changes a file its own check runs is flagged at done, never refused (the crash test: the
test was made to agree with the code, and done accepted it with no word)."""

import subprocess
import sys

import pytest

from graphene_map import plan
from graphene_map.node_record import node_record, render
from graphene_map.plan import DONE, Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)
BOT = Caller("claude:aaaa1111", False, "aaaa1111-session")
TEST = "import pathlib\nassert 'return {}' in pathlib.Path('src/api/users.py').read_text()\n"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "src" / "api").mkdir(parents=True)
    (root / "tests").mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n__pycache__/\n")
    (root / "src" / "api" / "users.py").write_text("def count():\n    return 1\n")
    (root / "tests" / "test_users.py").write_text(TEST.format(1))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


def finished(repo, change):
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "u", "title": "users", "scope": ["src/api/**", "tests/**"],
                              "check": f"{sys.executable} tests/test_users.py"}], ALEX)  # fmt: skip
        plan.start(store, "u", BOT, repo)
        change()
        assert plan.finish(store, "u", BOT).state == DONE  # a flag, not a refusal
        row = store.node_log("u", ("finished",))[-1]["detail"]
        return row, render(node_record(store, repo, plan.get(store, "u")))


def test_a_leaf_that_edits_a_test_its_own_check_runs_is_flagged_at_done(repo):
    def change():
        (repo / "src" / "api" / "users.py").write_text("def count():\n    return 2\n")
        (repo / "tests" / "test_users.py").write_text(TEST.format(2))  # the test made to agree

    row, shown = finished(repo, change)
    assert row["check_touched"] == ["tests/test_users.py"]
    said = "    its check runs tests/test_users.py, which this leaf changed: read that diff"
    assert f"{said} (`graphene node diff u`)" in shown


def test_a_file_new_since_the_base_and_a_check_left_alone_are_not_flagged(repo):
    def change():
        (repo / "src" / "api" / "users.py").write_text("def count():\n    return 1  # same\n")
        (repo / "tests" / "test_more.py").write_text("assert True\n")

    row, shown = finished(repo, change)
    assert "check_touched" not in row and not any("which this leaf changed" in line for line in shown)
