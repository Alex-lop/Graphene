"""The keychain is off here as in tests/: nothing in docs/test reads a developer's real key, or counts on
the real night's bill."""

import pytest


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "off")
    # nor the person's opening, nor the night's real ledger (graphene_map/night.py)
    for name in ("GRAPHENE_AGENT_LIVE_USD", "GRAPHENE_NIGHT_STARTED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GRAPHENE_NIGHT_LEDGER", str(tmp_path / "night.jsonl"))
