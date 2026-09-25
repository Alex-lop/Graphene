"""The Token Factory client, against the recorded fake: the live list decides the model ids, usage is
priced at the list's price and kept in the ledger, the cap stops the next call, a 429 is waited out,
and the key is written nowhere."""

import json

import pytest
from fake_tokenfactory import Fake, call

from graphene_map import tokenfactory as tf


@pytest.fixture
def fake(monkeypatch):
    def start(replies=()):
        f = Fake(replies).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        started.append(f)
        return f

    started: list[Fake] = []
    yield start
    for f in started:
        f.__exit__(None, None, None)
    tf._listed.cache_clear()


def test_the_nemotron_sizes_come_from_the_live_list_and_nothing_else(fake):
    fake()
    assert tf.roles() == {
        "ultra": "nvidia/Nemotron-3-Ultra-fake",
        "super": "nvidia/Nemotron-3-Super-fake",
        "nano": "nvidia/Nemotron-3-Nano-fake",  # the "-fast" twin is newer, and still the second choice
    }
    assert tf.roles([]) == {}
    assert tf.reach() is None


def test_without_a_key_nothing_is_sent_and_it_says_so_in_one_line(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    tf._listed.cache_clear()
    with pytest.raises(tf.Unreachable, match="NEBIUS_API_KEY is not set"):
        tf.models()
    assert "NEBIUS_API_KEY is not set" in tf.reach()


def test_a_wrong_key_is_one_line_with_what_the_server_said(fake, monkeypatch):
    fake()
    monkeypatch.setenv("NEBIUS_API_KEY", "wrong")
    tf._listed.cache_clear()
    said = tf.reach()
    assert said.startswith("Token Factory answered 401") and "\n" not in said


def test_a_call_is_priced_at_list_price_kept_in_the_ledger_and_the_cap_stops_the_next(
    fake, tmp_path, monkeypatch
):
    f = fake([({"content": "hi"}, {"prompt_tokens": 1000, "completion_tokens": 500})] * 3)
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv("GRAPHENE_LEDGER", str(ledger))
    said = tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "hello"}], tag="leaf-a")
    assert said["message"]["content"] == "hi"
    assert said["dollars"] == pytest.approx(1000 * 5e-8 + 500 * 2e-7)
    row = json.loads(ledger.read_text())
    assert row["tag"] == "leaf-a" and row["usage"]["prompt_tokens"] == 1000
    assert "fake-key" not in ledger.read_text()
    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", str(said["dollars"]))  # reached
    with pytest.raises(tf.Spent, match="spend cap"):
        tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "again"}])
    assert len(f.requests) == 1  # refused before it was sent


def test_a_429_is_waited_out_and_tools_reach_the_model(fake, monkeypatch):
    monkeypatch.setattr(tf.time, "sleep", lambda s: None)
    f = fake([429, 500, call("view", path="a.py")])
    tools = [{"type": "function", "function": {"name": "view", "parameters": {"type": "object"}}}]
    said = tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "look"}], tools=tools)
    assert said["message"]["tool_calls"][0]["function"]["name"] == "view"
    assert len(f.requests) == 3 and f.requests[-1]["tools"] == tools


def test_a_recording_replays_and_holds_no_key(fake, tmp_path, monkeypatch):
    fake([{"content": "recorded answer"}])
    record = tmp_path / "rec.jsonl"
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_RECORD", str(record))
    tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "q"}])
    assert "fake-key" not in record.read_text()
    monkeypatch.delenv("GRAPHENE_TOKENFACTORY_RECORD")
    with Fake.replay(record) as again:
        monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", again.url)
        tf._listed.cache_clear()
        assert tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "q"}])["message"][
            "content"
        ] == "recorded answer"
