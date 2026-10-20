# ruff: noqa: F811  (the repo fixture imported from test_plan_cli is named again as an argument)
"""The graph flows into your goal: a real plan's store, read into the cockpit, its sub-goals as lanes."""

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import plan
from graphene_map.cockpit import flow_view as FV
from graphene_map.cockpit.read import read
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)


def test_a_task_knows_the_sub_goals_over_it_and_the_graph_draws_them_as_lanes_into_the_goal(repo):
    with Store.open(repo) as store:
        plan.set_goal(store, "users come back with their ids", ALEX)
        plan.propose(
            store,
            [
                {"id": "api", "title": "The API: what callers see"},
                {"id": "auth", "title": "Auth", "parent": "api"},
                {"id": "login", "title": "log in", "parent": "auth", "scope": ["auth.py"], "check": "true"},
                {"id": "ids", "title": "ids", "parent": "api", "scope": ["api.py"], "check": "true"},
                {"id": "docs", "title": "docs", "parent": "api", "scope": ["README.md"], "check": "true",
                 "needs": ["ids"]},
                {"id": "schema", "title": "the schema", "scope": ["schema.py"], "check": "true"},
            ],
            ALEX,
        )  # fmt: skip
        m = read(store, repo)
    assert m.tasks["login"].above == [("api", "API"), ("auth", "Auth")]  # the top first
    assert m.tasks["ids"].above == [("api", "API")] and m.tasks["schema"].above == []
    g = FV.flow_graph(m)
    goal = g.nodes[0]
    assert (goal.id, goal.state, goal.label) == (FV.GOAL, "goal", "users come back with their ids")
    assert goal.badge == "0 of 4"
    assert [(lane.id, lane.label, lane.note) for lane in g.lanes] == [
        ("api", "API", "0 of 2"), ("auth", "API › Auth", "0 of 1"),
    ]  # fmt: skip
    assert {n.id: n.lane for n in g.nodes} == {
        FV.GOAL: "", "login": "auth", "ids": "api", "docs": "api", "schema": "",
    }  # fmt: skip
    assert {(e.a, e.b, e.double) for e in g.edges} == {  # a need, and what nothing waits on into the goal
        ("ids", "docs", True), ("docs", FV.GOAL, True), ("login", FV.GOAL, False), ("schema", FV.GOAL, False),
    }  # fmt: skip
    assert g.heads == ["wave 1 · 3 tasks", "wave 2 · 1 task", "goal"]
