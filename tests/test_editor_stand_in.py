# ruff: noqa: F811  (the repo fixture imported from test_run_live is named again as an argument)
"""The snapshot's `stand_in`: true when every model call the plan's log priced was a stand-in's (the tests'
fake, the harness's dev/proof/standin.py), so an editor filming a free race says on screen that it is one, as
a replay's top line does. False with no call on record, or when any call went to a real endpoint."""

from datetime import UTC, datetime

from test_run_live import leaf, repo  # noqa: F401
from test_state_json import ALEX, snapshot

from graphene_map import plan
from graphene_map.store import Store


def usage(store, endpoint: str) -> None:
    at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    detail = {"model": "nvidia/Nemotron-3-Nano-fake", "dollars": 0.001, "endpoint": endpoint}
    store.log_node("a", at, "usage", "run:nemotron", None, None, detail)


def test_no_call_on_record_is_not_a_stand_in(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    assert snapshot()["stand_in"] is False


def test_a_race_whose_every_call_was_a_stand_ins_says_so(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        usage(store, "a stand-in")
        usage(store, "a stand-in")
    assert snapshot()["stand_in"] is True


def test_one_real_call_makes_it_no_stand_in(repo):
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
        usage(store, "a stand-in")
        usage(store, "token factory")
    assert snapshot()["stand_in"] is False
