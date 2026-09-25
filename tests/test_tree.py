# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""The plan is a tree: the root is the goal, a node's children are how it is achieved, leaves are the
work. Hierarchy is meaning and `needs` is order; done rolls up; every executor is told the path from
the root to its leaf. A real git repo in every test, as in test_plan."""

import json

import pytest
from test_plan import ALEX, BOT, git, repo, store  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map.plan import DONE, DROPPED, OPEN, PROPOSED, REVIEW, Caller, Refused

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
    from graphene_map.run import prompt_for

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


def test_the_record_rolls_up_the_same_way_per_subtree_and_per_plan(store, repo):
    from graphene_map.node_record import rolled_up

    plan.propose(store, TREE, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    everything = plan.nodes(store)
    under = [n for n in plan.below("api", everything) if n in plan.leaves(everything)]
    lines = "\n".join(rolled_up(store, repo, under))
    assert "the 2 leaves under it (1 done" in lines
    assert (
        "of the 1 path git said had changed under them, 1 inside the scope" in lines
        and "1 to git alone" in lines
    )
    assert "not counted (never held, or git's answer was not kept): b" in lines  # never a silent zero
    assert "1 of 1 passed" in lines
    whole = "\n".join(rolled_up(store, repo, plan.leaves(everything)))
    assert "the 3 leaves" in whole and "b, docs" in whole


# -- what the closing review broke, each kept as a test -----------------------------------------------


def test_a_proposal_binds_nobody_not_even_the_leaf_it_was_put_under(store, repo):
    plan.propose(store, [{"id": "mine", "title": "t", "scope": ["README.md"], "check": "true"}], ALEX)
    plan.start(store, "mine", BOT, repo)
    plan.propose(
        store, [{"id": "c1", "parent": "mine", "title": "c", "scope": ["src/**"], "check": "true"}], BOT
    )
    (repo / "README.md").write_text("done\n")
    assert plan.finish(store, "mine", BOT).state == DONE  # still a leaf, and its holder can close it


def test_a_running_leaf_cannot_be_made_a_sub_goal_by_moving_a_node_under_it(store, repo):
    plan.propose(store, [{"id": "x", "title": "x", "scope": ["README.md"], "check": "false"}], ALEX)
    plan.propose(store, [{"id": "y", "title": "y", "scope": ["src/**"], "check": "true"}], ALEX)
    plan.start(store, "x", BOT, repo)
    with pytest.raises(Refused, match="a child would make x a sub-goal while claude:aaaa1111 holds it"):
        plan.edit(store, "y", {"parent": "x"}, ALEX)


def test_archive_never_puts_a_parent_away_over_a_child_that_stays(store, repo):
    plan.propose(store, TREE, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    do(store, repo, "b", "src/api/b.txt")
    plan.edit(store, "docs", {"needs": ["b"]}, ALEX)  # unfinished work waits on b, so b stays
    gone = {n.id for n in plan.archive(store, ALEX)}
    assert "api" not in gone and "b" not in gone
    plan.propose(store, [{"title": "still editable", "scope": ["README.md"], "check": "true"}], ALEX)


def test_what_a_sub_goals_check_leaves_behind_is_nobodys_change(store, repo):
    tree = json.loads(json.dumps(TREE))
    tree[0]["check"] = "touch coverage.xml"
    plan.propose(store, tree, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    do(store, repo, "b", "src/api/b.txt")
    assert plan.get(store, "api").state == DONE
    plan.start(store, "docs", BOT, repo)  # not refused over coverage.xml "changed while no node owned it"


def test_a_person_can_overrule_a_sub_goals_check_with_a_reason(store, repo):
    tree = json.loads(json.dumps(TREE))
    tree[0]["check"] = "false"
    plan.propose(store, tree, ALEX)
    do(store, repo, "a", "src/api/a.txt")
    do(store, repo, "b", "src/api/b.txt")
    with pytest.raises(Refused):
        plan.finish(store, "api", BOT, checkout=repo, override="nope")  # not an agent's
    assert plan.finish(store, "api", ALEX, checkout=repo, override="checked by hand").state == DONE
    assert store.node_log("api", ("overruled",))[-1]["detail"]["override"] == "checked by hand"


def test_undoing_the_split_of_a_checked_sub_goal_does_not_brick_the_plan(store):
    plan.propose(store, TREE, ALEX)
    plan.edit(store, "docs", {"needs": []}, ALEX)
    plan.edit(store, "b", {"needs": []}, ALEX)
    plan.drop(store, "a", ALEX)
    plan.drop(store, "b", ALEX)  # api now has a check and no scope and no children
    plan.propose(store, [{"title": "later work", "scope": ["README.md"], "check": "true"}], ALEX)
    plan.edit(store, "docs", {"title": "still editable"}, ALEX)
    assert "api" not in [n.id for n in plan.ready(plan.nodes(store))]


def test_an_id_git_would_not_take_as_a_branch_is_refused_when_it_is_made(store):
    for bad in ("a..b", "x.lock", "n1."):
        with pytest.raises(Refused, match="not a usable id"):
            plan.propose(store, [{"id": bad, "title": "t", "scope": ["README.md"], "check": "true"}], ALEX)


def test_a_new_trees_goal_is_proposed_once_the_old_goal_has_nothing_left_to_do(store, repo):
    """Recheck: after the first tree was finished and archived, every later planner's sentence was
    refused, and the old goal stayed every executor's why for good. A goal still being worked on,
    and one the person has just set, still stay."""
    plan.propose_goal(store, "users come back with their ids", BOT)
    plan.propose(store, [{"id": "ids", "title": "ids", "scope": ["src/api/**"], "check": "true"}], BOT)
    plan.accept(store, [], ALEX)
    plan.start(store, "ids", BOT, repo)
    assert not plan.propose_goal(store, "something else", BOT)
    (repo / "src/api/users.py").write_text("ids\n")
    plan.finish(store, "ids", BOT)
    plan.archive(store, ALEX)
    assert plan.propose_goal(store, "the export writes CSV as well as JSON", BOT)
    assert (plan.goal(store), store.meta("goal:proposed")) == ("", "the export writes CSV as well as JSON")
    assert store.node_log("*", ("goal_proposed",))[-1]["detail"]["was"] == "users come back with their ids"
    plan.propose(store, [{"id": "csv", "title": "csv", "scope": ["README.md"], "check": "true"}], BOT)
    plan.accept(store, [], ALEX)
    assert plan.trail(store, plan.get(store, "csv")) == ["the export writes CSV as well as JSON"]
    plan.start(store, "csv", BOT, repo)
    (repo / "README.md").write_text("csv\n")
    plan.finish(store, "csv", BOT)
    plan.archive(store, ALEX)
    plan.set_goal(store, "invoices as PDF", ALEX)
    assert not plan.propose_goal(store, "something else", BOT)


def test_a_dropped_trees_proposed_goal_goes_with_it_while_another_planners_proposal_is_left(store):
    """Recheck: the proposed sentence was cleared only when no proposal at all was left, so with its
    tree dropped `graphene plan` kept showing it, and a later tree from its planner adopted it."""
    one, two = Caller("planner:one", False, "s-one"), Caller("planner:two", False, "s-two")
    plan.propose_goal(store, "rewrite the importer in Rust", one)
    plan.propose(store, [{"id": "port", "title": "port", "scope": ["src/**"], "check": "true"}], one)
    plan.propose(store, [{"id": "datefix", "title": "datefix", "scope": ["README.md"], "check": "true"}], two)
    plan.drop(store, "port", ALEX)
    assert store.meta("goal:proposed") is None


def test_the_check_graphene_runs_is_never_the_person(store, repo, monkeypatch):
    """pytest takes the terminal away from the tests it runs, and with "no terminal is still the
    person" a test file an executor wrote inside its own scope accepted proposals and widened scopes."""
    for mark in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "CODEX_SESSION_ID", "GRAPHENE_NODE"):
        monkeypatch.delenv(mark, raising=False)
    who = (
        "import os; from graphene_map.plan import caller as c; "
        "raise SystemExit(c(dict(os.environ), False).person)"
    )
    ok, _ = plan.run_check(f"{__import__('sys').executable} -c '{who}'", repo)
    assert ok  # exit 0: not a person


def test_one_word_for_each_state_as_a_person_reads_it(store, repo):
    """The screen, `graphene plan` and the text form's notes read a node's state from one place."""
    plan.propose(store, TREE, ALEX)
    plan.propose(store, [{"id": "mine", "title": "read it over", "owner": "alex"}], ALEX)
    plan.propose(store, [{"id": "later", "title": "the rest, to be split"}], ALEX)
    plan.propose(store, [{"id": "idea", "title": "an idea", "scope": ["x"], "check": "true"}], BOT)
    everything = plan.nodes(store)
    said = {n.id: plan.reads(n, everything) for n in everything}
    assert said == {
        "api": "0/2 done", "a": "ready", "b": "waiting", "docs": "waiting",
        "mine": "yours", "later": "to fill in", "idea": "proposed",
    }  # fmt: skip
    plan.start(store, "a", BOT, repo)
    plan.release(store, "a", BOT, "it needs src/other.txt", wants=["src/other.txt"])
    back = {n.id for n in plan.nodes(store) if plan.came_back(store, n)}
    assert back == {"a"} and plan.reads(plan.get(store, "a"), plan.nodes(store), back) == "came back"
    plan.widen(store, "a", [], ALEX)  # the person took the offer: it is ready again, not "came back"
    assert not plan.came_back(store, plan.get(store, "a"))
    assert {w: plan.look(w)[0] for w in ("proposed", "running", "came back", "done")} == {
        "proposed": "?", "running": "●", "came back": "↩", "done": "✓"
    }
    assert plan.said_by("run:claude") == "claude, started by graphene run"
    assert plan.said_by("claude:59409a10") == "a Claude Code session (59409a10)"


def test_a_persons_own_leaf_with_no_scope_is_their_to_do_done_by_their_word(store, repo):
    """`a` then `owner: me` in the screen made a node that start called "a sub-goal with no leaves
    yet", and that `done` sent to `start`."""
    plan.propose(store, [{"id": "top", "title": "the release", "children": [
        {"id": "tell", "title": "tell the team", "owner": "me"},
    ]}], ALEX)  # fmt: skip
    with pytest.raises(Refused) as mine:
        plan.start(store, "tell", ALEX, repo)
    assert str(mine.value) == (
        "tell is yours to do by hand: it has no scope, so there is nothing to start\n"
        "  graphene node done tell when it is done"
    )
    with pytest.raises(Refused, match="tell is alex's to do by hand"):
        plan.start(store, "tell", BOT, repo)
    with pytest.raises(Refused, match="tell is alex's to do by hand: [^\n]* nothing to finish\n"):
        plan.finish(store, "tell", BOT, checkout=repo)
    assert plan.finish(store, "tell", ALEX, checkout=repo).state == DONE
    [said] = store.node_log("tell", ("finished",))
    assert said["actor"] == "alex" and said["detail"]["note"].startswith("done by hand: the person's word")
    assert plan.get(store, "top").state == DONE  # and it rolls up like any leaf
    with pytest.raises(Refused, match="tell is done already"):
        plan.finish(store, "tell", ALEX, checkout=repo)


def test_a_to_do_that_waits_on_something_says_so(store, repo):
    tell = {"id": "tell", "title": "tell the team", "owner": "me", "needs": ["a"]}
    plan.propose(store, [{"id": "a", "title": "a", "scope": ["a.txt"], "check": "true"}, tell], ALEX)
    with pytest.raises(Refused, match=r"tell waits on a \(open\)"):
        plan.finish(store, "tell", ALEX, checkout=repo)
    assert plan.get(store, "tell").state == OPEN


def test_an_agents_node_with_no_scope_and_no_leaves_says_how_it_gets_filled_in(store, repo):
    plan.propose(store, [{"id": "later", "title": "the rest, to be split"}], ALEX)
    for act, verb in ((lambda: plan.start(store, "later", BOT, repo), "start"),
                      (lambda: plan.finish(store, "later", BOT), "finish")):  # fmt: skip
        with pytest.raises(Refused) as no:
            act()
        assert str(no.value) == (
            f"later has no scope and no leaves yet, so there is nothing to {verb}\n"
            "  s in graphene watch asks the planner to split it, or graphene node edit later gives it a "
            "scope and a check"
        )


def test_done_on_a_leaf_that_is_not_running_says_the_line_for_its_state(store, repo):
    """`start` on a waiting leaf said what it waits on, and `done` on it then said "`graphene node
    start` takes it": a command that tells you to run the one that was just refused."""
    plan.propose(store, TREE, ALEX)
    plan.propose(store, [{"id": "idea", "title": "an idea", "scope": ["x"], "check": "true"}], BOT)
    signed = {"id": "ok", "title": "signed", "scope": ["ok.txt"], "check": "true", "signoff": True}
    plan.propose(store, [signed], ALEX)

    def said(node_id, who=BOT):
        with pytest.raises(Refused) as no:
            plan.finish(store, node_id, who)
        return str(no.value)

    assert said("a") == "a is ready, not running\n  graphene node start a takes it"
    assert said("b") == "b is not running: it waits on a (open)"
    with pytest.raises(Refused) as waiting:
        plan.start(store, "b", BOT, repo)
    assert str(waiting.value) == "b waits on a (open)"  # and never the command just refused
    assert said("idea") == (
        "idea is a proposal: nothing to finish until the person accepts it\n"
        "  graphene plan accept idea (the person's)"
    )
    assert said("idea", ALEX).endswith("\n  graphene plan accept idea")
    do(store, repo, "ok", "ok.txt")
    assert said("ok") == (
        "ok is finished and waits for the person's sign-off\n  graphene node signoff ok (the person's)"
    )
    do(store, repo, "a", "src/api/a.txt")
    assert said("a") == "a is done already"
