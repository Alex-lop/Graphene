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


@pytest.fixture(autouse=True)
def no_token_factory(monkeypatch, tmp_path):
    """Nothing in the suite reaches the real Token Factory or Sandboxes, whatever the shell or the home
    directory has: a test that wants an endpoint starts the recorded fake (`fake_tokenfactory`)."""
    for name in ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID", "GRAPHENE_TOKENFACTORY_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "off")  # a developer's real keychain is never read or written
    monkeypatch.setenv("CONTREE_HOME", str(tmp_path / "no-contree-profile"))
    # the person's opening is never the suite's: a test that wants it sets it, and its night is tmp_path's
    for name in ("GRAPHENE_AGENT_LIVE_USD", "GRAPHENE_NIGHT_STARTED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GRAPHENE_NIGHT_LEDGER", str(tmp_path / "night.jsonl"))


@pytest.fixture(autouse=True)
def no_agent_marks(monkeypatch):
    """A leaf's check runs with its executor's marks set: the suite takes nobody for an agent, or a
    stand-in, because of the shell it was started from."""
    from graphene_map import plan

    for name in (*plan.AGENT_MARKS, "GRAPHENE_AS"):
        monkeypatch.delenv(name, raising=False)


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
