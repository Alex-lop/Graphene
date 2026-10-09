"""`node show` says "against base": a check that ran a file another leaf then rewrote saw it as it was
at the base commit, and the record says so, with the file and the commit."""
# ruff: noqa: F811  (the fixtures come from test_plan)

from test_plan import ALEX, BOT, BOT2, repo, store  # noqa: F401

from graphene_map import plan
from graphene_map.node_record import node_record, render


def test_a_check_that_ran_a_file_a_later_leaf_rewrites_says_against_base(store, repo, finish):
    base = plan.head(repo)[:7]
    plan.propose(store, [
        {"id": "api", "title": "api", "scope": ["src/api/**"], "check": "python3 tests/test_users.py"},
        {"id": "tests", "title": "tests", "scope": ["tests/test_users.py"], "check": "true",
         "needs": ["api"]},
    ], ALEX, files=plan.tracked(repo))  # fmt: skip
    plan.start(store, "api", BOT, repo)
    finish(store, repo, "api", BOT)
    lines = render(node_record(store, repo, plan.get(store, "api")))
    assert f"    against base: its check ran tests/test_users.py as at {base}; tests writes it after" in lines
    plan.start(store, "tests", BOT2, repo)
    finish(store, repo, "tests", BOT2)
    lines = render(node_record(store, repo, plan.get(store, "api")))
    said = f"    against base: its check ran tests/test_users.py as at {base}; tests rewrote it after"
    assert said in lines


def test_a_leaf_whose_check_runs_only_its_own_or_nobodys_files_has_no_such_line(store, repo, finish):
    plan.propose(store, [
        {"id": "api", "title": "api", "scope": ["src/api/**"], "check": "python3 tests/test_users.py"},
        {"id": "db", "title": "db", "scope": ["src/db/**"], "check": "true"},
    ], ALEX, files=plan.tracked(repo))  # fmt: skip
    plan.start(store, "api", BOT, repo)
    finish(store, repo, "api", BOT)
    lines = render(node_record(store, repo, plan.get(store, "api")))
    assert not [line for line in lines if "against base" in line]
