"""The Token Factory client, against the recorded fake: the live list decides the model ids, usage is
priced at the list's price and kept in the ledger, the cap stops the next call, a 429 is waited out,
and the key is written nowhere."""

import json
from pathlib import Path

import pytest
from fake_tokenfactory import Fake, call

from graphene_map.nemotron import tokenfactory as tf


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


@pytest.mark.parametrize("said", ["$10", "ten", "nan", "inf"])
def test_a_cap_that_is_not_a_number_of_dollars_refuses_every_call_rather_than_none(fake, monkeypatch, said):
    f = fake([{"content": "hi"}])
    monkeypatch.delenv("GRAPHENE_LEDGER", raising=False)  # no ledger either: still refused
    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", said)
    with pytest.raises(tf.Spent) as no:
        tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "hello"}])
    assert str(no.value) == f"GRAPHENE_SPEND_CAP_USD is {said!r}, not a number of dollars: set it as " \
        "GRAPHENE_SPEND_CAP_USD=10, or unset it for no cap"  # fmt: skip
    assert f.requests == []


def test_a_429_is_waited_out_and_tools_reach_the_model(fake, monkeypatch):
    waits = []
    monkeypatch.setattr(tf, "_sleep", waits.append)  # the loop waits by this name, once per retry
    f = fake([429, 500, call("view", path="a.py")])
    tools = [{"type": "function", "function": {"name": "view", "parameters": {"type": "object"}}}]
    said = tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "look"}], tools=tools)
    assert said["message"]["tool_calls"][0]["function"]["name"] == "view"
    assert len(f.requests) == 3 and f.requests[-1]["tools"] == tools and len(waits) == 2


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


def test_a_completion_that_timed_out_is_tried_once_more_not_six_times(fake, monkeypatch):
    fake([])
    monkeypatch.setattr(tf, "_sleep", lambda s: None)
    tries = []

    def slow(req, timeout):
        tries.append(req.get_method())
        raise TimeoutError("timed out")

    monkeypatch.setattr(tf.urllib.request, "urlopen", slow)
    with pytest.raises(tf.Unreachable, match="could not be reached"):
        tf.chat("nvidia/Nemotron-3-Nano-fake", [{"role": "user", "content": "q"}])
    assert tries.count("POST") == 2


@pytest.mark.parametrize("pad", [0, 255])
def test_an_error_that_echoes_the_key_is_said_without_it(monkeypatch, pad):
    """A gateway's 401 page may echo the Authorization header: what is raised goes to the screen, the
    plan log (a released leaf's why) and a recording, so the key is taken out where it is raised, even
    when the 300 characters kept would cut it in two."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Echo(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            echoed = "x" * pad + " invalid key: " + self.headers["Authorization"]
            data = json.dumps({"error": echoed}).encode()
            self.send_response(401)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_GET

    server = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    key = "sk-FAKE-graphene-review-123"
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setenv("NEBIUS_API_KEY", key)
    tf._listed.cache_clear()
    try:
        said = tf.reach()
        with pytest.raises(tf.Unreachable) as no:
            tf._request("POST", "chat/completions", {}, tries=1)
    finally:
        server.shutdown()
        tf._listed.cache_clear()
    assert said.startswith("Token Factory answered 401") and "invalid key" in said
    for text in (said, str(no.value)):
        assert "sk-FAKE" not in text and "review-123" not in text


def test_a_key_a_header_cannot_carry_is_one_line_and_never_kept(monkeypatch):
    """A pasted en dash: the header could not be built, and a traceback reached the screen."""
    from graphene_map.nemotron import keys

    key = "sk-FAKE–graphene-review-123"
    monkeypatch.setenv("NEBIUS_API_KEY", key)
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", "http://127.0.0.1:9/v1")  # never reached
    with pytest.raises(tf.Unreachable, match="letters, digits and punctuation") as no:
        tf._request("GET", "models", tries=1)
    assert key not in str(no.value)
    with pytest.raises(RuntimeError, match="one word") as no:
        keys.set(key)
    assert key not in str(no.value)


# The NVIDIA models Token Factory listed for Alex's key on 2026-09-29 (rung 1, practice): ids, list prices and
# the roles `roles` gave them, from .graphene/practice/access.json (dev/test/first-light.md). Nothing else.
FIXTURE = Path(__file__).parents[1] / "fixtures" / "tokenfactory-models-2026-09-29.json"
LIVE = json.loads(FIXTURE.read_text())


@pytest.fixture
def live(monkeypatch):
    """The fake, listing what the live list listed on 2026-09-29, and answering with ``usage`` rows."""
    started: list[Fake] = []

    def start(usages=()):
        f = Fake([({"content": "ok"}, u) for u in usages], models=LIVE["data"]).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        started.append(f)
        return f

    yield start
    for f in started:
        f.__exit__(None, None, None)
    tf._listed.cache_clear()


def test_the_live_lists_mixed_case_ids_resolve_to_their_roles_and_lightning_to_none(live):
    """Three spellings (`Nemotron-3-Ultra`, `nemotron-3-super`, `NVIDIA-Nemotron-3-Nano`) and a fourth
    NVIDIA model at Nano's price, Nemotron 3.5 Lightning (30B, 3B active; NVIDIA never calls it Nano): no
    role, and no default, falls to it."""
    live()
    lightning = "nvidia/Nemotron-3_5-Lightning"
    assert tf.roles() == LIVE["roles"]
    assert tf.resolve([], "planner") == (["nvidia/Nemotron-3-Ultra-550b-a55b"], [])
    assert tf.resolve([], "executor") == (["nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"], [])
    ids = list(LIVE["roles"].values()) + [lightning]
    assert tf.resolve(ids, "executor") == (ids, [])  # every listed id is used as it is, Lightning too
    assert lightning not in tf.roles().values() and tf._size(lightning) is None
    assert tf.reach() is None


def test_the_bill_is_the_live_lists_price_and_rung_2s_rows_add_up_to_its_progress(live, tmp_path,
                                                                                  monkeypatch):
    """Rung 2's three Nano calls (their token counts from its ledger, 2026-09-29) at the live list's price
    ($0.06 in, $0.24 out per million) are $0.000366, as progress.json says; rung 1's Ultra ($1.00, $3.00)
    and Super ($0.30, $0.90) rows are priced the same way. None is the fake's placeholder price."""
    rung_2 = [(1334, 186), (1402, 191), (1465, 98)]
    rung_1 = {"nvidia/Nemotron-3-Ultra-550b-a55b": (373, 81, 0.000616),
              "nvidia/nemotron-3-super-120b-a12b": (420, 54, 0.0001746)}  # fmt: skip
    counts = rung_2 + [v[:2] for v in rung_1.values()]
    usages = [{"prompt_tokens": p, "completion_tokens": c} for p, c in counts]
    live(usages)
    monkeypatch.setenv("GRAPHENE_LEDGER", str(tmp_path / "ledger.jsonl"))
    nano = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    bills = [tf.chat(nano, [{"role": "user", "content": "hi"}], tag="hello")["dollars"] for _ in rung_2]
    assert bills == pytest.approx([0.00012468, 0.00012996, 0.00011142])
    assert round(tf.spent(), 6) == 0.000366
    for model, (_, _, dollars) in rung_1.items():
        assert tf.chat(model, [{"role": "user", "content": "hi"}])["dollars"] == pytest.approx(dollars)
