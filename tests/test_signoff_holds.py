"""A leaf that needs a sign-off waits off your branch: `graphene run` leaves its work on graphene/<id>,
and the person's sign-off makes the clean merge (findings: `--signoff` merged first, then asked)."""

import subprocess

import pytest

from graphene_map import plan
from graphene_map.node_record import node_record, render
from graphene_map.plan import DONE, REVIEW, Caller
from graphene_map.run import run_parallel
from graphene_map.store import Store

ALEX = Caller("alex", True)
WRITES = "sh -c 'echo $GRAPHENE_NODE > $GRAPHENE_NODE.txt'"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


def ran(repo, *leaves):
    rows = [{"id": n, "title": f"write {n}", "scope": [f"{n}.txt"], "check": f"test -s {n}.txt", **extra}
            for n, extra in leaves]  # fmt: skip
    with Store.open(repo) as store:
        plan.propose(store, rows, ALEX)
    said: list[str] = []
    run_parallel(lambda: Store.open(repo), repo, repo, 2, WRITES, say=said.append)
    return said


def test_a_sign_off_leaf_waits_on_its_branch_and_the_sign_off_merges_it(repo):
    before = git(repo, "rev-parse", "HEAD")
    said = ran(repo, ("a", {"signoff": True}), ("b", {}))
    assert (repo / "b.txt").exists()  # one without a sign-off lands as ever
    assert not (repo / "a.txt").exists() and git(repo, "show", "graphene/a:a.txt") == "a\n"
    assert any("a passed; it waits for your sign-off before it lands" in s for s in said), said
    with Store.open(repo) as store:
        a = plan.get(store, "a")
        assert a.state == REVIEW and not store.node_log("a", ("landed",))
        shown = render(node_record(store, repo, a))
        waits = "  not in your branch yet: its work is on graphene/a; `graphene node signoff a` merges it"
        assert waits in shown
        plan.signoff(store, "a", ALEX, checkout=repo)
        assert plan.get(store, "a").state == DONE
        merge = store.node_log("a", ("landed",))[-1]["detail"]["commit"]
        assert waits not in render(node_record(store, repo, plan.get(store, "a")))
    assert (repo / "a.txt").read_text() == "a\n" and merge == git(repo, "rev-parse", "HEAD").strip()
    assert git(repo, "rev-parse", f"{merge}^2") and before != merge  # a --no-ff merge, as a run makes
    assert "graphene/a" not in git(repo, "branch", "--list")


def test_a_sign_off_whose_merge_is_not_clean_leaves_it_in_review(repo):
    ran(repo, ("a", {"signoff": True}))
    (repo / "a.txt").write_text("mine\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "mine")
    head = git(repo, "rev-parse", "HEAD")
    with Store.open(repo) as store:
        with pytest.raises(plan.Refused, match="did not merge cleanly here, so it stays in review"):
            plan.signoff(store, "a", ALEX, checkout=repo)
        assert plan.get(store, "a").state == REVIEW
    assert git(repo, "rev-parse", "HEAD") == head and (repo / "a.txt").read_text() == "mine\n"
    assert git(repo, "status", "--porcelain") == ""
