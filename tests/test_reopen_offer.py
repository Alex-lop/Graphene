"""The `r` offer: a leaf that came back on a landed leaf's fault reopens the owner and waits on it."""
# ruff: noqa: F811  (the fixtures come from test_plan)

import pytest
from test_plan import ALEX, BOT, BOT2, repo, store  # noqa: F401

from graphene_map import plan
from graphene_map.plan import OPEN, Refused


def leaf(i, scope, **extra):
    return {"id": i, "title": i, "scope": scope, "check": "true", **extra}


def came_back(store, repo, finish, owners, wants):
    """Each of ``owners`` (id, scope) done, and leaf x released wanting ``wants``."""
    plan.propose(store, [*(leaf(i, [s]) for i, s in owners), leaf("x", ["x.py"])], ALEX)
    for i, _ in owners:
        plan.start(store, i, BOT, repo)
        finish(store, repo, i, BOT)
    plan.start(store, "x", BOT2, repo)
    plan.release(store, "x", BOT2, "the  schema\nis wrong", wants=wants)
    return plan.get(store, "x")


def r_offer(store):
    return [o for o in plan.offers(store, plan.get(store, "x")) if o[0] == "r"]


def test_a_wanted_path_a_done_leaf_owns_offers_r(store, repo, finish):
    x = came_back(store, repo, finish, [("a", "a.py")], ["a.py"])
    [(key, words, argv)] = r_offer(store)
    assert words == "reopen a with this reason; x waits on it"
    assert argv == ["node", "reopen", "a", "--note", "came back from x: the schema is wrong", "--for", "x"]
    assert [k for k, *_ in plan.offers(store, x)][-1] == "r"  # after w and b, no n here


def test_two_done_owners_give_one_r_naming_both(store, repo, finish):
    came_back(store, repo, finish, [("a", "a.py"), ("b", "b.py")], ["a.py", "b.py"])
    [(_, words, argv)] = r_offer(store)
    assert words == "reopen a, b with this reason; x waits on them"
    assert argv[:4] == ["node", "reopen", "a", "b"] and argv[4] == "--note"


def test_a_path_no_done_leaf_owns_gives_no_r(store, repo, finish):
    came_back(store, repo, finish, [("a", "a.py")], ["other.py"])
    assert r_offer(store) == []


def test_reopen_for_a_leaf_opens_the_owner_and_makes_it_wait_once(store, repo, finish):
    came_back(store, repo, finish, [("a", "a.py")], ["a.py"])
    assert plan.reopen(store, ["a"], ALEX, "fix it", for_leaf="x").state == OPEN
    assert plan.get(store, "a").state == OPEN and plan.notes(store, "a") == ["fix it"]
    assert plan.get(store, "x").needs == ["a"]
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    plan.reopen(store, "a", ALEX, "twice", for_leaf="x")
    assert plan.get(store, "x").needs == ["a"]
    assert plan.notes(store, "a") == ["fix it", "twice"]


def test_the_needs_edit_is_in_the_leafs_log(store, repo, finish):
    came_back(store, repo, finish, [("a", "a.py")], ["a.py"])
    plan.reopen(store, "a", ALEX, "fix it", for_leaf="x")
    [edit] = store.node_log("x", ("edited",))
    assert edit["detail"]["changed"] == {"needs": [[], ["a"]]} and plan.get(store, "x").rev == 2


def test_a_running_for_leaf_is_refused(store, repo, finish):
    came_back(store, repo, finish, [("a", "a.py")], ["a.py"])
    plan.start(store, "x", BOT2, repo)
    with pytest.raises(Refused, match="x cannot wait on a: it is running"):
        plan.reopen(store, "a", ALEX, "fix it", for_leaf="x")
    assert plan.get(store, "a").state == "done"


def test_r_on_a_leaf_that_already_waits_on_the_owner_makes_it_waiting_not_came_back(store, repo, finish):
    plan.propose(store, [leaf("a", ["a.py"]), leaf("x", ["x.py"], needs=["a"])], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    plan.start(store, "x", BOT2, repo)
    plan.release(store, "x", BOT2, "a's field names are wrong", wants=["a.py"])
    assert plan.came_back(store, plan.get(store, "x"))
    plan.reopen(store, ["a"], ALEX, "came back from x: a's field names are wrong", for_leaf="x")
    x = plan.get(store, "x")
    assert (x.needs, x.rev) == (["a"], 1) and not plan.came_back(store, x)  # nothing of its contract changed
    [edit] = store.node_log("x", ("edited",))
    assert edit["detail"] == {"changed": {}, "rev": 1, "reopened": ["a"]}
    assert plan.reads(x, plan.nodes(store)) == "waiting"


def test_after_r_the_leaf_offers_nothing_and_a_done_aside_is_no_owner(store, repo, finish):
    came_back(store, repo, finish, [("a", "a.py")], ["a.py"])
    plan.reopen(store, ["a", "a"], ALEX, "fix it", for_leaf="x")  # an id named twice is one
    assert plan.notes(store, "a") == ["fix it"] and plan.offers(store, plan.get(store, "x")) == []


def test_r_is_not_offered_when_waiting_on_the_owner_would_make_a_cycle(store, repo, finish):
    plan.propose(store, [leaf("x", ["x.py"]), leaf("a", ["a.py"], needs=["x"])], ALEX)
    plan.start(store, "x", BOT, repo)
    finish(store, repo, "x", BOT)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    plan.reopen(store, "x", ALEX, "again")
    plan.start(store, "x", BOT2, repo)
    plan.release(store, "x", BOT2, "a's file is wrong", wants=["a.py"])
    assert [k for k, *_ in plan.offers(store, plan.get(store, "x"))] == ["w", "b"]  # a waits on x: no r
    with pytest.raises(Refused, match="cycle"):
        plan.reopen(store, "a", ALEX, "fix it", for_leaf="x")
