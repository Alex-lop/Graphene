"""The keychain is off here as in tests/, and tests/keyguard.py guards it: nothing in docs/test reaches a
developer's real keychain, or counts on the real night's bill."""

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "tests"))
import keyguard  # noqa: E402


def pytest_configure(config):
    keyguard.install(config)
    keyguard.no_git_location()


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "off")
    # nor the person's opening, nor the night's real ledger (graphene_map/nemotron/night.py)
    for name in ("GRAPHENE_AGENT_LIVE_USD", "GRAPHENE_NIGHT_STARTED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GRAPHENE_NIGHT_LEDGER", str(tmp_path / "night.jsonl"))
