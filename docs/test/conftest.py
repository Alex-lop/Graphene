"""The keychain is off here as in tests/: nothing in docs/test reads a developer's real key."""

import pytest


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch):
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "off")
