"""Times print in the machine's local time, so the tests pin one: UTC."""

import os
import time

import pytest


@pytest.fixture(autouse=True)
def utc(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    os.environ.pop("TZ", None)
    time.tzset()


@pytest.fixture
def finish():
    """Do a node's work and finish it: a node with nothing changed inside its scope is not done, so
    a test that only needs a node finished writes one line inside the first glob of its scope."""
    from pathlib import Path

    from graphene_map import plan

    def _finish(store, repo, node_id, who, **kwargs):
        node = plan.get(store, node_id)
        glob = next(g for g in node.scope if not g.startswith("!"))
        rel = glob.replace("/**", f"/work_{node_id}.txt").replace("**", f"work_{node_id}.txt")
        path = Path(node.checkout or repo) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((path.read_text() if path.exists() else "") + f"work for {node_id}\n")
        return plan.finish(store, node_id, who, **kwargs)

    return _finish
