# ruff: noqa: F811  (pytest fixtures imported from test_run_live are named again as arguments)
"""`graphene run --stop`: the run this repository has going is stopped from any terminal, as `:stop`
does in `graphene watch`, and what it held goes back to the plan."""

from test_run_live import (  # noqa: F401
    ALEX,
    SLOW,
    executor,
    graphene,
    graphene_run,
    leaf,
    repo,
    states,
    wait_for,
)

from graphene_map import plan
from graphene_map.plan import OPEN, RUNNING
from graphene_map.store import Store


def test_run_stop_ends_the_run_going_here_and_hands_its_leaf_back(repo):
    """There was no command to stop a run: Ctrl-C in its own terminal, or `:stop` inside watch."""
    with Store.open(repo) as store:
        plan.propose(store, [leaf("a", "a.txt")], ALEX)
    run = graphene_run(repo, "--with", executor(repo, SLOW))
    try:
        assert wait_for(lambda: states(repo)["a"] == RUNNING), run.stdout
        stop = graphene(repo, "run", "--stop")
        said, _ = stop.communicate(timeout=30)
        assert stop.returncode == 0 and "stopping the run: what it holds goes back to the plan" in said, said
        ran, _ = run.communicate(timeout=30)
        assert run.returncode == 130 and "run stopped: a handed back, ready again" in ran, ran
        assert states(repo) == {"a": OPEN}
    finally:
        run.kill()


def test_run_stop_with_no_run_going_says_so(repo):
    stop = graphene(repo, "run", "--stop")
    said, _ = stop.communicate(timeout=30)
    assert stop.returncode == 0 and said.strip() == "no run is going here", said
