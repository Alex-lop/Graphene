# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""What a look costs: the screen asks once a second, so it has to stay cheap as a run's log grows.

Measured when it was written: 2 ms on this repository's own plan (66 nodes, 485 rows), 7 ms with four
running leaves and 2,000 rows, 53 ms with 22,000 rows; the classic screen reads the whole log every look and
took 0.35 to 1.75 seconds at 20,000. The bound here is generous, for a slow machine: it fails on a look that
reads everything again."""

import time
from datetime import UTC, datetime, timedelta

from test_plan_cli import repo  # noqa: F401  (fixture)

from graphene_map import plan
from graphene_map.cockpit.read import read
from graphene_map.plan import Caller
from graphene_map.store import Store

RUNNING, ROWS = 4, 8000


def test_a_look_with_four_running_leaves_and_thousands_of_rows_stays_well_under_a_second(repo):
    alex = Caller("alex", True)
    leaves = [
        {"id": f"t{i}", "title": f"task {i}", "scope": [f"d{i}/**"], "check": "true"} for i in range(RUNNING)
    ]
    now = datetime.now(UTC)
    with Store.open(repo) as store:
        plan.propose(store, leaves, alex)
        for i in range(RUNNING):
            sid = f"5e55105{i}-0000-4000-8000-0000000000a1"
            plan.start(store, f"t{i}", Caller(f"claude:5e55105{i}", False, sid), repo)
            for k in range(ROWS // RUNNING):
                then = now - timedelta(seconds=(ROWS // RUNNING - k) * 0.05)
                at = then.isoformat().replace("+00:00", "Z")
                detail = {"attempt": 1, "tool": "Edit", "target": f"d{i}/f{k % 40}.py", "verb": "editing"}
                store.log_node(f"t{i}", at, "did", "run:claude", sid, None, detail)
    previous, times = None, []
    for _ in range(5):
        start = time.perf_counter()
        with Store.open(repo) as store:
            previous = read(store, repo, previous)
        times.append(time.perf_counter() - start)
    assert len(previous.tasks) == RUNNING and all(t.events for t in previous.tasks.values())
    assert sorted(times[1:])[1] < 0.5, times
