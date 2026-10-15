# ruff: noqa: F811  (pytest fixtures imported from test_signoff_holds are named again as arguments)
"""What the sign-off wait left loose (the seam readers' findings, reproduced on main): a sign-off on no
branch or from the leaf's own worktree, a y while the run still goes, and the words when the worktree
is gone or the person merged it by hand."""

import pytest
from test_signoff_holds import ALEX, git, ran, repo  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map.plan import REVIEW
from graphene_map.store import Store


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


def test_a_yes_while_the_run_still_goes_lets_the_parent_close(repo, tmp_path):
    import threading
    import time

    from graphene_map.run import run_parallel

    go = tmp_path / "go"  # b finishes only once a is signed off, so the run is still going at the yes
    held = f"sh -c 'if [ $GRAPHENE_NODE = b ]; then while [ ! -f {go} ]; do sleep 0.1; done; fi; " \
        "echo $GRAPHENE_NODE > $GRAPHENE_NODE.txt'"  # fmt: skip
    rows = [{"id": "g", "title": "goal"}] + [{"id": n, "title": n, "parent": "g", "scope": [f"{n}.txt"],
                                               "check": f"test -s {n}.txt", "signoff": n == "a"}
                                              for n in "ab"]  # fmt: skip
    with Store.open(repo) as store:
        plan.propose(store, rows, ALEX)
    run = threading.Thread(target=run_parallel, args=(lambda: Store.open(repo), repo, repo, 2, held),
                           kwargs={"say": lambda _: None})  # fmt: skip
    run.start()
    try:
        for _ in range(300):
            with Store.open(repo) as store:
                if plan.unlanded(store, "a"):
                    plan.signoff(store, "a", ALEX, checkout=repo)  # watch's y, mid-run
                    break
            time.sleep(0.1)
    finally:
        go.touch()
        run.join()
    with Store.open(repo) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {"g": "done", "a": "done", "b": "done"}
