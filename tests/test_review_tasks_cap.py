# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`tasks` is how many tasks the envelope may accept for the person, all told, since auto went on. A task
that landed left the count once a child was proposed under it (it was a sub-goal now), so an agent that
nested each round's tasks under the last round's had the envelope accept and run six with `tasks: 2`."""

from test_auto_envelope import ALEX, BOT
from test_plan_cli import repo  # noqa: F401  (fixtures)

from graphene_map import auto as AUTO
from graphene_map import plan as P
from graphene_map import settings as S
from graphene_map.store import Store


def leaves(store, files, round_: int, parents: list[str | None]) -> list[P.Node]:
    items = [{"id": f"t{round_}{i}", "title": f"task t{round_}{i}", "scope": [f"m{round_}{i}.py"],
              "check": "true", **({"parent": p} if p else {})} for i, p in enumerate(parents)]  # fmt: skip
    return P.propose(store, items, BOT, files=files)


def test_a_task_that_became_a_sub_goal_still_counts_against_the_cap(repo):
    files = P.tracked(repo)
    with Store.open(repo) as store:
        S.apply(store, "auto: on\ntasks: 2\n", ALEX)
        first = leaves(store, files, 1, [None, None])
        assert AUTO.take(store, first, files, repo).startswith("accepted inside your envelope")
        assert AUTO.accepted(store, S.auto_since(store)) == 2
        for n in first:  # an executor takes each, changes its file and finishes it: the task lands
            P.start(store, n.id, BOT, repo)
            (repo / n.scope[0]).write_text("x = 2\n")
            P.finish(store, n.id, BOT)
        assert [P.get(store, n.id).state for n in first] == [P.DONE, P.DONE]
        second = leaves(store, files, 2, [n.id for n in first])
        said = AUTO.take(store, second, files, repo)
        assert said == f"{AUTO.WAITS}your envelope accepts 2 tasks and this makes 4", said
        assert [P.get(store, n.id).state for n in second] == [P.PROPOSED, P.PROPOSED]
        assert AUTO.accepted(store, S.auto_since(store)) == 2


def test_a_sub_goal_accepted_with_its_leaves_is_still_no_task(repo):
    files = P.tracked(repo)
    with Store.open(repo) as store:
        S.apply(store, "auto: on\ntasks: 2\n", ALEX)
        tree = [{"id": "api", "title": "the api", "children": [
            {"id": "a", "title": "a", "scope": ["a.py"], "check": "true"},
            {"id": "b", "title": "b", "scope": ["b.py"], "check": "true"}]}]  # fmt: skip
        added = P.propose(store, tree, BOT, files=files)
        assert AUTO.take(store, added, files, repo).startswith("accepted inside your envelope")
        assert AUTO.accepted(store, S.auto_since(store)) == 2
