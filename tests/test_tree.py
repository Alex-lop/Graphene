# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""The plan is a tree: the root is the goal, a node's children are how it is achieved, leaves are the
work. Hierarchy is meaning and `needs` is order; done rolls up; every executor is told the path from
the root to its leaf. A real git repo in every test, as in test_plan."""

import json

import pytest
from test_plan import ALEX, BOT, git, repo, store  # noqa: F401  (fixtures)

from graphene_debrief import plan
from graphene_debrief.plan import DONE, DROPPED, OPEN, PROPOSED, REVIEW, Caller, Refused

TREE = [
    {
        "id": "api",
        "title": "the HTTP surface",
        "goal": "customers can fetch their invoices",
        "check": "test -f src/api/a.txt -a -f src/api/b.txt",
        "children": [
            {"id": "a", "title": "leaf a", "scope": ["src/api/a.txt"], "check": "true"},
            {"id": "b", "title": "leaf b", "scope": ["src/api/b.txt"], "check": "true", "needs": ["a"]},
        ],
    },
    {
        "id": "docs",
        "title": "say so in the README",
        "scope": ["README.md"],
        "check": "true",
        "needs": ["api"],
    },
]


def do(store, repo, node_id, path, who=BOT):
    plan.start(store, node_id, who, repo)
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(f"{node_id}\n")
    return plan.finish(store, node_id, who)


def test_a_flat_plan_from_0_3_is_a_tree_with_one_implicit_root(store, repo):
    """Additive: a row written before `parent` existed loads, sits under the root, and runs."""
    [n] = plan.propose(store, [{"title": "old", "scope": ["README.md"], "check": "true"}], ALEX)
    row = store.node_row(n.id)
    del row["parent"], row["aside"]
    store.put_node(row)
    old = plan.get(store, n.id)
    assert old.parent is None and plan.above(old, {old.id: old}) == []
    assert [r.id for r in plan.ready(plan.nodes(store))] == [n.id]
    assert do(store, repo, n.id, "README.md").state == DONE


def test_a_sub_goal_needs_only_a_title_and_a_leaf_still_needs_a_scope_and_a_check(store):
    plan.propose(store, TREE, ALEX)
    assert plan.get(store, "a").parent == "api" and plan.get(store, "api").scope == []
    with pytest.raises(Refused, match="a leaf needs a scope"):
        plan.propose(store, [{"title": "a check and nowhere to work", "check": "true"}], ALEX)
    # a title alone is a sub-goal whose children are still to come: in the plan, and nobody's to take
    [later] = plan.propose(store, [{"id": "later", "title": "the mobile app"}], ALEX)
    assert "later" not in [n.id for n in plan.ready(plan.nodes(store))]
    with pytest.raises(Refused):
        plan.start(store, "later", BOT, ".")


def test_only_leaves_are_taken_and_what_a_sub_goal_needs_its_leaves_wait_on(store, repo):
    plan.propose(store, TREE, ALEX)
    assert [n.id for n in plan.ready(plan.nodes(store))] == ["a"]
    with pytest.raises(Refused, match="sub-goal"):
        plan.start(store, "api", BOT, repo)
    with pytest.raises(Refused, match="docs waits on api"):
        plan.start(store, "docs", BOT, repo)
    plan.propose(store, [{"id": "late", "title": "under docs' wait", "needs": ["api"], "children": [
        {"id": "l1", "title": "x", "scope": ["src/db/**"], "check": "true"}]}], ALEX)  # fmt: skip
    with pytest.raises(Refused, match="l1 waits on api"):
        plan.start(store, "l1", BOT, repo)


def test_done_rolls_up_and_the_sub_goals_own_check_is_where_integration_lives(store, repo):
    plan.propose(store, TREE, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    assert plan.get(store, "api").state == OPEN
    do(store, repo, "b", "src/api/b.txt")
    api = plan.get(store, "api")
    assert api.state == DONE  # both leaves done, and `test -f a -a -f b` passed in the checkout
    kinds = [e["kind"] for e in store.node_log("api")]
    assert kinds[-2:] == ["check_passed", "rolled_up"]
    assert [n.id for n in plan.ready(plan.nodes(store))] == ["docs"]  # what waited on the sub-goal can start


def test_a_failing_integration_check_keeps_the_sub_goal_open_and_says_what_to_do(store, repo):
    tree = json.loads(json.dumps(TREE))
    tree[0]["check"] = "test -f src/api/never.txt"
    plan.propose(store, tree, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    do(store, repo, "b", "src/api/b.txt")
    assert plan.get(store, "api").state == OPEN
    with pytest.raises(Refused, match="do not yet work together"):
        plan.finish(store, "api", BOT, checkout=repo)
    assert plan.ready(plan.nodes(store)) == []  # docs still waits
    # the way on: a leaf for what is missing, then the sub-goal's check again, by itself
    plan.propose(store, [{"id": "fix", "parent": "api", "title": "the missing file",
                          "scope": ["src/api/never.txt"], "check": "true"}], ALEX)  # fmt: skip
    do(store, repo, "fix", "src/api/never.txt")
    assert plan.get(store, "api").state == DONE


def test_every_executor_is_told_the_path_from_the_root_to_its_leaf(store, repo):
    plan.set_goal(store, "ship invoices by email before the quarter ends", ALEX)
    plan.propose(store, TREE, ALEX)
    told = plan.contract(plan.get(store, "a"), plan.trail(store, plan.get(store, "a")))
    lines = told.splitlines()
    assert lines[1].strip() == "why:    ship invoices by email before the quarter ends"
    assert lines[2].strip() == "the HTTP surface (api): customers can fetch their invoices"
    assert lines[3].strip().startswith("goal:")
    from graphene_debrief.run import prompt_for

    assert "ship invoices by email" in prompt_for(
        plan.get(store, "a"), [], None, plan.trail(store, plan.get(store, "a"))
    )


def test_a_proposal_is_a_subtree_and_accepting_its_top_accepts_its_leaves(store):
    proposed = plan.propose(store, TREE, BOT)
    assert [n.state for n in proposed] == [PROPOSED] * 4
    assert plan.ready(plan.nodes(store)) == []
    accepted = plan.accept(store, ["api"], ALEX)
    assert [n.id for n in accepted] == ["api", "a", "b"]
    assert plan.get(store, "docs").state == PROPOSED
    # and a leaf is never in the plan without its why: accepting it accepts what it sits under
    plan.propose(store, [{"id": "g", "title": "g", "children": [
        {"id": "g1", "title": "g1", "scope": ["src/db/**"], "check": "true"}]}], BOT)  # fmt: skip
    assert [n.id for n in plan.accept(store, ["g1"], ALEX)] == ["g", "g1"]


def test_an_agent_splits_a_leaf_too_big_to_do_by_proposing_children_and_the_person_prunes(store, repo):
    plan.propose(store, [{"id": "big", "title": "everything", "scope": ["src/**"], "check": "true"}], ALEX)
    plan.start(store, "big", BOT, repo)
    kids = [
        {"id": "big1", "parent": "big", "title": "the api half", "scope": ["src/api/**"], "check": "true"},
        {"id": "big2", "parent": "big", "title": "the db half", "scope": ["src/db/**"], "check": "true"},
    ]
    plan.propose(store, kids, BOT)  # allowed while it holds it: they are only proposals
    with pytest.raises(Refused, match="hand it back first"):
        plan.accept(store, ["big1"], ALEX)
    plan.release(store, "big", BOT, "too big for one leaf; proposed big1 and big2 under it")
    plan.accept(store, ["big1"], ALEX)
    plan.drop(store, "big2", ALEX)  # pruned
    assert [n.id for n in plan.ready(plan.nodes(store))] == ["big1"]
    do(store, repo, "big1", "src/api/x.txt")
    assert plan.get(store, "big").state == DONE  # its one remaining child is done, its check `true` passed
    # undoing a split: drop the children, and the node is a leaf again
    plan.propose(store, [{"id": "again", "title": "t", "scope": ["README.md"], "check": "true"}], ALEX)
    plan.propose(
        store, [{"id": "c", "parent": "again", "title": "c", "scope": ["README.md"], "check": "true"}], ALEX
    )
    plan.drop(store, "c", ALEX)
    assert [n.id for n in plan.ready(plan.nodes(store))] == ["again"]


def test_dropping_a_sub_goal_drops_what_is_under_it_unless_something_outside_waits(store):
    plan.propose(store, TREE, ALEX)
    with pytest.raises(Refused, match="docs waits on api"):
        plan.drop(store, "api", ALEX)
    plan.edit(store, "docs", {"needs": []}, ALEX)
    plan.drop(store, "api", ALEX)
    assert {plan.get(store, i).state for i in ("api", "a", "b")} == {DROPPED}


def test_cycles_through_the_tree_are_refused(store):
    plan.propose(store, TREE, ALEX)
    with pytest.raises(Refused, match="cycle"):
        plan.edit(store, "a", {"needs": ["api"]}, ALEX)  # a leaf waiting on its own sub-goal
    with pytest.raises(Refused, match="cycle"):
        plan.edit(store, "api", {"needs": ["b"]}, ALEX)  # a sub-goal waiting on its own leaf
    with pytest.raises(Refused, match="cycle"):
        plan.edit(store, "api", {"parent": "a"}, ALEX)  # under itself


def test_a_new_or_reopened_child_reopens_the_finished_sub_goal_above_it(store, repo):
    plan.propose(store, TREE, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    do(store, repo, "b", "src/api/b.txt")
    plan.reopen(store, "b", ALEX, "not like that")
    assert plan.get(store, "api").state == OPEN
    assert plan.ready(plan.nodes(store), Caller("agent", False))[0].id == "b"


def test_a_sub_goal_with_a_sign_off_waits_for_the_person_after_its_leaves(store, repo):
    tree = json.loads(json.dumps(TREE))
    tree[0]["signoff"] = True
    plan.propose(store, tree, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    do(store, repo, "b", "src/api/b.txt")
    assert plan.get(store, "api").state == REVIEW
    runs, waits = plan.forecast(plan.nodes(store))
    assert [n.id for n, _ in waits] == ["docs"]
    plan.signoff(store, "api", ALEX)
    assert plan.get(store, "api").state == DONE
