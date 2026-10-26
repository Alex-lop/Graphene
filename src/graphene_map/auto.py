"""`graphene auto`: from a goal to tested commits inside the envelope the person set once.

The planner drafts the tree, Graphene accepts what fits the envelope (settings.auto/budget/tasks/rounds and
the standing conditions), runs it with forks, lands what its check passes, then runs the goal's own check;
when that is red the planner proposes the fix, for at most settings.rounds rounds. Each round is logged as
a node_log row of kind KIND on "*", whose detail is what ``state`` returns.
"""

from __future__ import annotations

KIND = "auto"  # node_log kind of a round's progress, actor "graphene auto"
STAGES = ("planning", "running", "checking", "fixing", "done", "waits")


def state(store) -> dict | None:
    """The newest round's progress, or None when `graphene auto` never ran on this plan: a dict with
    round (1 is the first plan), rounds (the most fix rounds), stage (one of STAGES), spent and budget
    (dollars, budget None when unset), check ("pass", "fail" or None while not yet run) and why (a line
    for the person when stage is waits, else "")."""
    rows = store.node_log("*", (KIND,))
    return dict(rows[-1]["detail"]) if rows else None
