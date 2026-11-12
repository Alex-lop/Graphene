"""Agent environment isolation applies to the main suite and the dev harnesses."""

import pytest


@pytest.fixture(autouse=True)
def no_agent_marks(monkeypatch):
    """A leaf's check runs with its executor's marks set: the suite takes nobody for an agent, or a
    stand-in, because of the shell it was started from."""
    from graphene_map import plan

    for name in (*plan.AGENT_MARKS, "GRAPHENE_AS", "CODEX_SESSION_ID", "CODEX_SANDBOX",
                 "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
