"""What the sign-off wait left loose (the seam readers' findings, reproduced on main): a sign-off on no
branch or from the leaf's own worktree, a y while the run still goes, and the words when the worktree
is gone or the person merged it by hand."""

import pytest

from graphene_map import plan
from graphene_map.plan import REVIEW
from graphene_map.store import Store
from test_signoff_holds import ALEX, git, ran, repo  # noqa: F401  (fixtures)


def test_a_sign_off_on_a_detached_head_is_refused(repo):
    ran(repo, ("a", {"signoff": True}))
    git(repo, "checkout", "-q", "--detach")
    head = git(repo, "rev-parse", "HEAD")
    with Store.open(repo) as store:
        with pytest.raises(plan.Refused, match="on no branch .a detached HEAD.: leaves merged here"):
            plan.signoff(store, "a", ALEX, checkout=repo)
        assert plan.get(store, "a").state == REVIEW
    assert git(repo, "rev-parse", "HEAD") == head and "graphene/a" in git(repo, "branch", "--list")


def test_a_sign_off_from_inside_the_leafs_own_worktree_is_refused(repo):
    ran(repo, ("a", {"signoff": True}))
    with Store.open(repo) as store:
        tree = plan.unlanded(store, "a")["worktree"]
        with pytest.raises(plan.Refused, match="inside a's own worktree"):
            plan.signoff(store, "a", ALEX, checkout=tree)
        assert plan.get(store, "a").state == REVIEW
