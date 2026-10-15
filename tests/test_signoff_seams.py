# ruff: noqa: F811  (pytest fixtures imported from test_signoff_holds are named again as arguments)
"""What the sign-off wait left loose (the seam readers' findings, reproduced on main): a sign-off on no
branch or from the leaf's own worktree, a y while the run still goes, and the words when the worktree
is gone or the person merged it by hand; and a run that lands a leaf which changed its own check's file."""

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


def test_the_words_when_its_worktree_is_gone_or_it_was_merged_by_hand(repo):
    import shutil

    from graphene_map.node_record import node_record, render
    from graphene_map.tui import _by_hand

    ran(repo, ("a", {"signoff": True}))
    with Store.open(repo) as store:
        left = plan.unlanded(store, "a")
        shutil.rmtree(left["worktree"])
        shown = render(node_record(store, repo, plan.get(store, "a")))
        assert ("  not in your branch yet: its work is on graphene/a and its worktree is gone; "
                "`git merge graphene/a`, then `graphene node signoff a`") in shown, shown  # fmt: skip
        assert _by_hand(left)  # the pane and c say git merge first, as signoff's refusal does
        git(repo, "merge", "--no-ff", "-m", "by hand", "graphene/a")
        shown = render(node_record(store, repo, plan.get(store, "a")))
        assert not any("not in your branch yet" in line for line in shown), shown


def test_a_run_says_a_leaf_changed_the_file_its_own_check_runs(repo):
    from graphene_map.run import run_parallel

    (repo / "t.sh").write_text("exit 1\n")
    git(repo, "add", "t.sh")
    git(repo, "commit", "-qm", "t")
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "a", "title": "weaken", "scope": ["t.sh"], "check": "sh t.sh"}], ALEX)
    said: list[str] = []
    run_parallel(lambda: Store.open(repo), repo, repo, 1, "sh -c 'echo exit 0 > t.sh'", say=said.append)
    assert "a is done" in said, said  # landed, as a flag is not a refusal, and said as node done says it
    flag = "its check runs t.sh, which this leaf changed: read that diff (`graphene node diff a`)"
    assert flag in said, said
