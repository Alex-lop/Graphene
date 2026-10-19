# ruff: noqa: F811  (the repo fixture imported from test_plan_cli is named again as an argument)
"""The graph starts from your goal: a real plan's store, read into the cockpit and drawn as a tree."""

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import plan
from graphene_map.cockpit import flow_view as FV
from graphene_map.cockpit.read import read
from graphene_map.plan import Caller
from graphene_map.store import Store

ALEX = Caller("alex", True)


def test_a_task_knows_the_sub_goals_over_it_and_the_graph_draws_goal_sub_goal_task(repo):
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
    nodes, edges = FV.flow_graph(m)
    goal = nodes[0]
    assert (goal.id, goal.state, goal.label) == (FV.GOAL, "goal", "users come back with their ids")
    assert [(n.id, n.label, n.state) for n in nodes[1:3]] == [
        ("api", "API", "sub-goal"), ("auth", "Auth", "sub-goal"),
    ]  # fmt: skip
    assert {(e.a, e.b, e.kind) for e in FV.drawn(edges)} == {
        (FV.GOAL, "api", "tree"), ("api", "auth", "tree"), ("auth", "login", "tree"), ("api", "ids", "tree"),
        (FV.GOAL, "schema", "tree"), ("ids", "docs", "needs"),
    }  # fmt: skip
