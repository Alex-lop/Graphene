# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""The standing conditions bind the gate: a scope that covers a protected path or a read-only glob
is refused at propose and at edit, a change to one is refused at `done` before the check runs, and
an aside's `**` leaves them out instead of being refused."""

import pytest
from test_plan import ALEX, BOT, api_node, repo, store  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map import settings as S
from graphene_map.plan import DONE, Refused


@pytest.fixture
def ruled(store):
    S.apply(store, "protected: src/db/**\nreadonly: README.md\n", ALEX)
    return store


@pytest.mark.parametrize(
    "scope, setting, path",
    [
        (["src/**"], "protected", "src/db/schema.py"),
        (["src/db/schema.py"], "protected", "src/db/schema.py"),
        (["**"], "protected", "src/db/schema.py"),
        (["README.md"], "readonly", "README.md"),
    ],
)
def test_propose_refuses_a_scope_that_covers_a_standing_path(ruled, repo, scope, setting, path):
    with pytest.raises(Refused) as no:
        plan.propose(ruled, [api_node(id="a", scope=scope)], BOT, files=plan.tracked(repo))
    assert setting in str(no.value) and path in str(no.value)
    assert plan.nodes(ruled) == []


def test_a_scope_clear_of_them_is_proposed_and_an_edit_into_them_is_refused(ruled, repo):
    plan.propose(ruled, [api_node(id="a")], ALEX, files=plan.tracked(repo))
    with pytest.raises(Refused, match="protected.*src/db/"):
        plan.edit(ruled, "a", {"scope": ["src/**"]}, ALEX, files=plan.tracked(repo))
    with pytest.raises(Refused, match="readonly"):  # also when the text form validates afterwards
        plan.edit(ruled, "a", {"scope": ["README.md"]}, ALEX, check=False)
    assert plan.get(ruled, "a").scope == api_node()["scope"]


def test_done_refuses_a_changed_standing_path_before_the_check_runs(ruled, repo):
    plan.propose(ruled, [api_node(id="a", check="touch ran")], ALEX)
    plan.start(ruled, "a", BOT, repo)
    (repo / "src/api/users.py").write_text("x = 1\n")
    (repo / "README.md").write_text("# changed\n")
    with pytest.raises(Refused) as no:
        plan.finish(ruled, "a", BOT)
    assert "readonly: README.md" in str(no.value) and "README.md" in str(no.value)
    assert not (repo / "ran").exists()
    (repo / "README.md").write_text("# toy\n")
    assert plan.finish(ruled, "a", BOT).state == DONE


def test_an_asides_everything_leaves_them_out_and_is_not_refused(ruled, repo):
    (typed,) = plan.propose(ruled, [{"id": "t", "title": "typo", "scope": ["**"]}], ALEX, aside=True)
    assert plan.as_scoped(typed, plan.standing(ruled)) == ["**", "!src/db/**", "!README.md"]
    plan.start(ruled, "t", ALEX, repo)
    (repo / "src/db/schema.py").write_text("TABLES = [1]\n")
    (repo / "src/api/users.py").write_text("x = 1\n")
    plan.close_aside(ruled, "t", ALEX)
    (last,) = ruled.node_log("t", ("finished",))
    assert last["detail"]["outside"] == ["src/db/schema.py"]
