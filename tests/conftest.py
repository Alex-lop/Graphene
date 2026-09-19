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
