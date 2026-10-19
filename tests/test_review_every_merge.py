"""With `review: every` each task is signed off alone, so a sign-off makes its merge the way a run lands one:
when the checkout has moved since the task was cut, its check and the checks of what landed since run on
the merge first, and one that fails keeps it in review. Two tasks green apart and red together never both
land through two yeses (test_land_moved has the same pair for a run)."""

import pytest
from test_land_moved import A, B, C, D, git, repo_with

from graphene_map import plan
from graphene_map import settings as S
from graphene_map.plan import DONE, REVIEW
from graphene_map.run import run_parallel
from graphene_map.store import Store

ALEX = plan.Caller("alex", True)


def parked(tmp_path, monkeypatch, leaves):
    root, executor = repo_with(tmp_path, monkeypatch, leaves)
    with Store.open(root) as store:
        S.apply(store, "review: every\n", ALEX)
    run_parallel(lambda: Store.open(root), root, root, 2, executor, say=lambda _: None)
    with Store.open(root) as store:
        assert {n.id: n.state for n in plan.nodes(store)} == {n["id"]: REVIEW for n in leaves}
    return root


@pytest.mark.parametrize("first, second", [("a", "b"), ("b", "a")])
def test_the_second_yes_of_two_red_together_is_refused_and_it_stays_in_review(tmp_path, monkeypatch, first,
                                                                              second):  # fmt: skip
    root = parked(tmp_path, monkeypatch, [A, B])
    with Store.open(root) as store:
        assert plan.signoff(store, first, ALEX, checkout=root).state == DONE  # nothing moved under it
        head = git(root, "rev-parse", "HEAD").strip()
        with pytest.raises(plan.Refused) as no:
            plan.signoff(store, second, ALEX, checkout=root)
        assert plan.get(store, second).state == REVIEW
    # b's check is the red one either way: on b's own merge, or as what landed before a's
    assert f"b's check `{B['check']}` fails on top of {head[:8]}" in str(no.value), no.value
    assert f"graphene node reopen {second}" in str(no.value)
    assert git(root, "rev-parse", "HEAD").strip() == head  # nothing of it landed
    assert git(root, "status", "--porcelain") == ""  # and nothing of the refused merge is left behind


def test_a_yes_on_a_moved_checkout_lands_once_its_check_and_the_landed_ones_pass_on_the_merge(tmp_path,
                                                                                           monkeypatch):
    root = parked(tmp_path, monkeypatch, [C, D])
    with Store.open(root) as store:
        plan.signoff(store, "c", ALEX, checkout=root)
        assert plan.signoff(store, "d", ALEX, checkout=root).state == DONE
        landed = store.node_log("d", ("landed",))[-1]["detail"]
    assert landed["on_merge"] == ["test -f d.py", "test -f c.py"]  # as a run lands the second of two
    assert (root / "c.py").exists() and (root / "d.py").exists()
