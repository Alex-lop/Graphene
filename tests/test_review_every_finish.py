# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""`review: every`: a task whose check passes waits in review for the person's sign-off instead of being
done, whoever proposed it and whenever; the check still decides first, a person's overrule is their own
say-so, a sub-goal is not held, and only the person can turn it off."""

import pytest
from test_plan import ALEX, BOT, BOT2, api_node, repo, store  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map import settings as S
from graphene_map.plan import DONE, REVIEW, RUNNING, Refused


def test_a_task_whose_check_passes_waits_for_the_sign_off_and_what_needs_it_waits(store, repo, finish):
    S.apply(store, "review: every\n", ALEX)
    plan.propose(store, [api_node(id="a"), api_node(id="b", needs=["a"], scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    assert finish(store, repo, "a", BOT).state == REVIEW  # no `signoff: yes` on it: the setting holds it
    with pytest.raises(Refused, match=r"b waits on a \(review\)"):
        plan.start(store, "b", BOT2, repo)
    assert plan.signoff(store, "a", ALEX).state == DONE
    assert plan.start(store, "b", BOT2, repo).state == RUNNING


def test_with_review_off_the_check_decides(store, repo, finish):
    plan.propose(store, [api_node(id="a")], ALEX)
    plan.start(store, "a", BOT, repo)
    assert finish(store, repo, "a", BOT).state == DONE


def test_a_task_proposed_and_started_before_review_was_said_is_held_too(store, repo, finish):
    plan.propose(store, [api_node(id="a")], ALEX)
    plan.start(store, "a", BOT, repo)
    S.apply(store, "review: every\n", ALEX)  # said while it runs: read when it passes, not when proposed
    assert finish(store, repo, "a", BOT).state == REVIEW
    assert not plan.get(store, "a").signoff  # its contract is as it was: turned off, the check decides again


def test_a_failing_check_still_comes_first(store, repo, finish):
    S.apply(store, "review: every\n", ALEX)
    plan.propose(store, [api_node(id="a", check="false")], ALEX)
    plan.start(store, "a", BOT, repo)
    with pytest.raises(Refused, match="failed"):
        finish(store, repo, "a", BOT)
    assert plan.get(store, "a").state == RUNNING  # never in front of the person before its check passes


def test_a_person_overruling_the_check_is_their_own_say_so(store, repo, finish):
    S.apply(store, "review: every\n", ALEX)
    plan.propose(store, [api_node(id="a", check="false")], ALEX)
    plan.start(store, "a", BOT, repo)
    assert finish(store, repo, "a", ALEX, override="the check is wrong; I read the diff").state == DONE


def test_a_sub_goal_is_done_once_its_tasks_are_signed_off(store, repo, finish):
    S.apply(store, "review: every\n", ALEX)
    plan.propose(store, [{"id": "g", "title": "users"}, api_node(id="a", parent="g")], ALEX)
    plan.start(store, "a", BOT, repo)
    assert finish(store, repo, "a", BOT).state == REVIEW and plan.get(store, "g").state != DONE
    plan.signoff(store, "a", ALEX, checkout=repo)
    assert plan.get(store, "g").state == DONE  # nothing of its own to look at: it rolls up, not held


def test_only_the_person_turns_it_off_or_signs_off(store, repo, finish):
    S.apply(store, "review: every\n", ALEX)
    with pytest.raises(Refused, match="person's to do"):
        S.apply(store, "review: off\n", BOT)
    assert S.review(store) == "every"
    plan.propose(store, [api_node(id="a")], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    with pytest.raises(Refused, match="person's to do"):
        plan.signoff(store, "a", BOT)
    assert plan.get(store, "a").state == REVIEW
