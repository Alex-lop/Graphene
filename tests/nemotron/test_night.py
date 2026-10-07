"""The night's bill (graphene_map/nemotron/night.py), against the recorded fake and a stub ConTree SDK: under
the person's opening every Token Factory call reserves its worst case before it is sent and settles after,
a call that would pass the cap is refused unsent, processes racing for the last dollars cannot both
pass, nothing new starts past 90% of the cap, ConTree operations are counted with their seconds, every
row says practice, and no row holds the key. Without the opening nothing is written. The opening is set
here by each test's own environment, which stands for the person's shell."""

import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fake_tokenfactory import Fake

from graphene_map import plan as P
from graphene_map import run
from graphene_map.nemotron import night, sandbox
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.store import Store

ULTRA, NANO = "nvidia/Nemotron-3-Ultra-fake", "nvidia/Nemotron-3-Nano-fake"
ASK = [{"role": "user", "content": "hello"}]


@pytest.fixture
def fake(monkeypatch):
    started: list[Fake] = []

    def start(replies=()):
        f = Fake(replies).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        started.append(f)
        return f

    yield start
    for f in started:
        f.__exit__(None, None, None)
    tf._listed.cache_clear()


@pytest.fixture
def opened(monkeypatch, tmp_path):
    """The person's opening at $10, the night's ledger in tmp_path; returns the ledger."""
    monkeypatch.setenv(night.OPENING, "10")
    return Path(os.environ[night.LEDGER])


def rows(ledger: Path) -> list[dict]:
    return [json.loads(line) for line in ledger.read_text().splitlines()]


def spent(ledger: Path, dollars: float) -> None:
    """The night so far: ``dollars`` settled, from an earlier call."""
    with ledger.open("a") as f:
        f.write(json.dumps({"kind": "reserve", "id": "before", "model": NANO, "dollars": dollars}) + "\n")
        f.write(json.dumps({"kind": "settle", "id": "before", "model": NANO, "dollars": dollars}) + "\n")


def test_without_the_opening_nothing_is_written_to_the_night(fake, tmp_path):
    fake([{"content": "hi"}])
    tf.chat(NANO, ASK, max_tokens=64)
    assert not Path(os.environ[night.LEDGER]).exists()
    with Store.open(tmp_path) as store:
        store.log_node("*", P._now(), "usage", "planner:nemotron", None, None, {"dollars": 0.1})
        assert "practice" not in store.node_log("*", ("usage",))[0]["detail"]


def test_each_call_reserves_its_worst_case_then_settles_and_every_row_says_practice(fake, opened, tmp_path):
    fake([({"content": "a"}, {"prompt_tokens": 100, "completion_tokens": 50})] * 3)
    said = [tf.chat(NANO, ASK, max_tokens=512), tf.chat(ULTRA, ASK, max_tokens=512), tf.chat(ULTRA, ASK)]
    got = rows(opened)
    assert [r["kind"] for r in got] == ["reserve", "settle"] * 3 and all(r["practice"] is True for r in got)
    reserved = [r for r in got if r["kind"] == "reserve"]
    settled = [r for r in got if r["kind"] == "settle"]
    assert [s["id"] for s in settled] == [r["id"] for r in reserved]
    assert [s["dollars"] for s in settled] == [pytest.approx(s["dollars"], abs=1e-6) for s in said]
    assert all(r["dollars"] > s["dollars"] for r, s in zip(reserved, settled, strict=True))  # worst case
    assert reserved[1]["dollars"] >= 512 * 2.4e-6 and reserved[2]["dollars"] >= night.UNSAID * 2.4e-6
    bill = night.bill()
    assert bill[0].startswith(
        f"the night's bill: ${sum(s['dollars'] for s in said):.4f} spent, $0.0000 in flight"
    )
    assert bill[1].startswith(f"  {ULTRA}: 2 calls") and bill[2].startswith(
        f"  {NANO}: 1 call,"
    )  # Ultra first
    assert bill[3].startswith("  by purpose: unsaid $") and "went to a stand-in" in bill[4]
    assert bill[-1].startswith("  Sandboxes: 0 operations")
    with Store.open(tmp_path) as store:  # the usage rows evidence.py reads say practice too
        store.log_node("*", P._now(), "usage", "planner:nemotron", None, None, {"dollars": 0.1})
        assert store.node_log("*", ("usage",))[0]["detail"]["practice"] is True


def test_a_call_that_would_pass_the_cap_is_refused_before_it_is_sent(fake, opened, monkeypatch):
    f = fake([{"content": "never sent"}])
    spent(opened, 9.99)
    monkeypatch.setenv(night.STARTED, "a run")  # started before: only the cap is asked
    with pytest.raises(tf.Spent) as no:
        tf.chat(ULTRA, ASK, max_tokens=8192)  # up to 8192 * $2.4e-6 = $0.0197 of completion
    said = str(no.value)
    assert f.requests == [] and "\n" not in said
    assert said.startswith(f"refused: a call to {ULTRA} may cost up to $0.01")
    assert "the night has $9.9900 spent and $0.0000 in flight of its $10.00 cap" in said
    assert said.endswith("(GRAPHENE_AGENT_LIVE_USD): nothing was sent")
    assert [r["kind"] for r in rows(opened)] == ["reserve", "settle"]  # nothing held for it
    tf.chat(NANO, ASK, max_tokens=64)  # a call that fits still goes
    assert len(f.requests) == 1


def test_a_failed_call_frees_its_reservation_and_one_that_timed_out_keeps_it(fake, opened, monkeypatch):
    fake([401])
    with pytest.raises(tf.Unreachable, match="answered 401"):
        tf.chat(NANO, ASK, max_tokens=64)
    monkeypatch.setattr(tf, "_sleep", lambda s: None)
    monkeypatch.setattr(
        tf.urllib.request, "urlopen", lambda req, timeout: (_ for _ in ()).throw(TimeoutError())
    )
    with pytest.raises(tf.Late):
        tf.chat(NANO, ASK, max_tokens=64)
    got = [r for r in rows(opened) if r["kind"] == "settle"]
    held = [r for r in rows(opened) if r["kind"] == "reserve"]
    assert got[0]["dollars"] == 0 and got[1]["dollars"] == held[1]["dollars"] > 0


def test_nothing_new_starts_past_90_percent_of_the_cap(fake, opened, monkeypatch):
    f = fake([{"content": "a"}])
    spent(opened, 9.0)
    with pytest.raises(tf.Spent) as no:
        tf.chat(NANO, ASK, max_tokens=64)
    assert "at or past $9.00 (90% of its $10.00 cap, GRAPHENE_AGENT_LIVE_USD): nothing new starts" in str(
        no.value
    )
    assert f.requests == []
    with pytest.raises(P.Refused, match="nothing new starts, and the run was not started"):
        run._begins(run.named("nemotron"))
    run._begins(run.DEFAULT_WITH)  # claude's run calls no Token Factory: not the night's to stop
    monkeypatch.setenv(night.OPENING, "80")  # the ceiling holds: $50, whatever the opening says
    assert night.cap() == 50.0
    monkeypatch.setenv(night.OPENING, "10")
    monkeypatch.setenv(night.STARTED, "the run")  # what a run started before $9 starts goes on under the cap
    tf.chat(NANO, ASK, max_tokens=64)
    assert len(f.requests) == 1


def test_a_run_that_starts_leaves_its_mark_for_its_executors(opened):
    run._begins(run.named("nemotron"))
    assert os.environ[night.STARTED] == "the run"  # an executor's environment is os.environ and its own


RACE = """
import sys
from graphene_map.nemotron import tokenfactory as tf
try:
    tf.chat("nvidia/Nemotron-3-Ultra-fake", [{"role": "user", "content": "race"}], max_tokens=1000)
except tf.Spent as no:
    print(no)
    sys.exit(3)
"""


def test_processes_racing_for_the_last_dollars_cannot_all_pass(fake, opened, tmp_path):
    """Six processes, room for two calls' worst case: two are sent, four are refused unsent. The two
    are held at the fake until the other four have ended, so no settle frees room for a third."""
    gate = threading.Event()

    def held(body):
        gate.wait(60)
        return {"content": "ok"}

    f = fake([held] * 6)
    one = tf.worst(
        {"model": ULTRA, "messages": [{"role": "user", "content": "race"}], "max_tokens": 1000}, ULTRA
    )
    spent(opened, 10 - 2.5 * one)
    env = os.environ | {night.STARTED: "the ladder", "PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    procs = [subprocess.Popen([sys.executable, "-c", RACE], env=env, stdout=subprocess.PIPE, text=True)
             for _ in range(6)]  # fmt: skip
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and len(f.requests) + sum(p.poll() is not None for p in procs) < 6:
        time.sleep(0.05)
    sent = len(f.requests)
    gate.set()
    codes = [p.wait(60) for p in procs]
    assert sent == 2 and sorted(codes) == [0, 0, 3, 3, 3, 3], (sent, codes)
    kinds = [r["kind"] for r in rows(opened)]
    assert kinds.count("reserve") == 3 and kinds.count("settle") == 3  # the earlier call's, and the two


def test_contree_operations_are_counted_with_their_seconds_at_no_price(opened, monkeypatch):
    class Image:
        def run(self, **kw):
            return self

        def wait(self):
            return types.SimpleNamespace(uuid="img-2", exit_code=0, stdout="", stderr="")

        def read(self, path):
            return b""

    class Sdk:
        images = types.SimpleNamespace(oci=lambda ref: Image(), use=lambda ref: Image())

    monkeypatch.setitem(sys.modules, "contree_sdk", types.SimpleNamespace(ContreeSync=lambda **kw: Sdk()))
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-key")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    box = sandbox.Contree()
    box.run("img-1", "true", {}, 60)
    box.read("img-2", "/work/a.py")
    got = rows(opened)
    assert [r["op"] for r in got] == ["image", "run", "read"]
    assert all(r["dollars"] == 0 and r["price"] == "unknown" and r["practice"] for r in got)
    assert night.bill()[-1] == "  Sandboxes: 3 operations, 0.0 min, counted at $0 (price: unknown)"
    monkeypatch.delenv(night.STARTED, raising=False)
    spent(opened, 9.0)
    with pytest.raises(night.Refused, match="a ConTree sandbox was not started"):
        sandbox.Contree()  # past 90%, no sandbox is made


def test_no_row_holds_the_key(fake, opened):
    fake([{"content": "a"}] * 2)
    tf.chat(NANO, ASK, max_tokens=64)
    tf.chat(ULTRA, ASK, max_tokens=64)
    text = opened.read_text()
    found = text.count("fake-key")  # the key the fake takes; counted, never printed
    assert found == 0 and len(rows(opened)) == 4


@pytest.mark.parametrize("dollars", ["NaN", '"a lot"', "-5"])
def test_a_row_nobody_can_read_refuses_rather_than_lets_a_call_through(fake, opened, monkeypatch, dollars):
    f = fake([{"content": "never sent"}])
    opened.write_text('{"kind": "settle", "id": "x", "model": "m", "dollars": ' + dollars + "}\n")
    monkeypatch.setenv(night.STARTED, "a run")
    with pytest.raises(tf.Spent, match="nothing was sent"):
        tf.chat(NANO, ASK, max_tokens=64)
    assert f.requests == []


# -- spending is the person's: an agent's mark without the opening is refused the real service --------------


@pytest.fixture
def real(fake, monkeypatch):
    """The fake, seen as Token Factory's real host by the rule production uses (``tf.endpoint``): it is
    BASE, and GRAPHENE_TOKENFACTORY_URL is unset. The key stays the fake's."""
    f = fake([{"content": "ok"}] * 4)
    monkeypatch.setattr(tf, "BASE", f.url)
    monkeypatch.delenv("GRAPHENE_TOKENFACTORY_URL")
    assert tf.endpoint() == "token factory"
    return f


def test_the_rule_asks_for_a_vendors_mark_and_no_opening(monkeypatch):
    for mark in night.MARKS:
        monkeypatch.delenv(mark, raising=False)
    night.person_only("a call")  # the person: no mark
    monkeypatch.setenv("GRAPHENE_NODE", "leaf")  # a person's `graphene run` gives its executors this
    monkeypatch.setenv("GRAPHENE_AS", "person:bench")
    night.person_only("a call")
    for mark in night.MARKS:
        monkeypatch.setenv(mark, "1")
        with pytest.raises(
            night.Refused, match=rf"carries an agent's mark \({mark}\) with no GRAPHENE_AGENT_LIVE"
        ):
            night.person_only("a call")
        monkeypatch.setenv(night.OPENING, "10")
        night.person_only("a call")  # opened by the person
        monkeypatch.delenv(night.OPENING)
        monkeypatch.delenv(mark)


def test_an_agents_call_to_the_real_host_is_refused_unsent_until_the_person_opens_it(real, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(tf.Spent) as no:
        tf.chat(NANO, ASK, max_tokens=64)
    said = str(no.value)
    assert said.startswith(f"refused: a call to {NANO} spends on the person's key") and "\n" not in said
    assert "(CLAUDECODE) with no GRAPHENE_AGENT_LIVE_USD: nothing was sent" in said
    assert real.requests == [] and not Path(os.environ[night.LEDGER]).exists()
    monkeypatch.setenv(night.OPENING, "10")  # the person's opening: the call goes, on the night's bill
    tf.chat(NANO, ASK, max_tokens=64)
    assert len(real.requests) == 1
    assert [r["endpoint"] for r in rows(Path(os.environ[night.LEDGER])) if r["kind"] == "reserve"] == [
        "token factory"
    ]


def test_a_person_and_the_fake_are_not_refused(real, monkeypatch):
    for mark in night.MARKS:
        monkeypatch.delenv(mark, raising=False)
    tf.chat(NANO, ASK, max_tokens=64)  # the person, on the real host
    monkeypatch.setenv("CLAUDECODE", "1")
    with Fake([{"content": "ok"}]) as stand_in:  # the scripted fake, named as the tests name it
        monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", stand_in.url)
        assert tf.endpoint() == "a stand-in"
        tf.chat(NANO, ASK, max_tokens=64)
        assert len(stand_in.requests) == 1
    assert len(real.requests) == 1


def test_an_agents_contree_sandbox_is_refused_before_the_sdk_is_made(monkeypatch):
    made = []
    monkeypatch.setitem(
        sys.modules, "contree_sdk", types.SimpleNamespace(ContreeSync=lambda **kw: made.append(1))
    )
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-key")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    for mark in night.MARKS:
        monkeypatch.delenv(mark, raising=False)
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    with pytest.raises(
        night.Refused, match=r"a ConTree sandbox spends on the person's key.*\(CODEX_SANDBOX\)"
    ):
        sandbox.Contree()
    assert made == [] and not Path(os.environ[night.LEDGER]).exists()


def test_the_harnesses_that_strip_the_marks_ask_first(monkeypatch, tmp_path):
    """bench.py and arm_bprime.py give their children an environment without the marks, as the person:
    the rule is asked before, on the harness's own. nemotron.sh asks before it unsets them."""
    sys.path.insert(0, str(Path(__file__).parents[2] / "dev" / "test"))
    import bench

    monkeypatch.delenv("GRAPHENE_TOKENFACTORY_URL", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    assert "refused: a run on Nemotron spends on the person's key" in bench.unopened(
        "nemotron --placement sandbox"
    )
    assert bench.unopened("claude") is None  # Claude Code's own run: not Token Factory's
    monkeypatch.setenv(night.OPENING, "10")
    assert bench.unopened("nemotron") is None
    monkeypatch.delenv(night.OPENING)
    monkeypatch.setenv("GRAPHENE_TOKENFACTORY_URL", "http://127.0.0.1:9/v1/")  # a stand-in
    assert bench.unopened("nemotron") is None
    env = {k: v for k, v in os.environ.items() if k not in ("GRAPHENE_TOKENFACTORY_URL", night.OPENING)}
    env |= {"NEBIUS_API_KEY": "fake-key", "PATH": f"{Path(sys.executable).parent}{os.pathsep}{env['PATH']}"}
    script = Path(__file__).parents[2] / "dev" / "proof" / "nemotron.sh"
    done = subprocess.run(
        ["bash", str(script), str(tmp_path / "demo")], env=env, capture_output=True, text=True
    )
    assert (
        done.returncode == 1
        and "(CLAUDECODE) with no GRAPHENE_AGENT_LIVE_USD: nothing was sent" in done.stderr
    )
    assert not (tmp_path / "demo").exists()


# -- a call that may have been received keeps its worst case ------------------------------------------------

STOPPED = """
import signal, sys
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.nemotron.executor import _stopped
signal.signal(signal.SIGTERM, _stopped if sys.argv[1] == "executor" else lambda *_: sys.exit(143))
tf.chat("nvidia/Nemotron-3-Ultra-fake", [{"role": "user", "content": "held"}], max_tokens=8192)
"""


@pytest.mark.parametrize("who", ["executor", "planner"])
def test_a_call_stopped_by_term_after_it_was_sent_keeps_its_worst_case(fake, opened, who):
    """Graphene stops an executor or a planner with TERM, which each turns into SystemExit: the call it
    had sent may still be done and billed, so it stays at its worst case, as it does after a Ctrl-C."""
    gate = threading.Event()
    f = fake([lambda body: gate.wait(60) and {"content": "too late"}])
    env = os.environ | {"PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    child = subprocess.Popen([sys.executable, "-c", STOPPED, who], env=env)
    deadline = time.monotonic() + 60
    while not f.requests and time.monotonic() < deadline:
        time.sleep(0.05)
    assert f.requests, "the call never reached the fake"
    child.terminate()
    assert child.wait(60) == 143
    gate.set()
    held, settled = (
        [r for r in rows(opened) if r["kind"] == "reserve"],
        [r for r in rows(opened) if r["kind"] == "settle"],
    )
    assert len(held) == len(settled) == 1 and settled[0]["dollars"] == held[0]["dollars"] > 0


def _answers(monkeypatch, *said):
    """urlopen stubbed: each try raises the next of ``said`` (never an answer)."""
    import urllib.error
    import urllib.request

    left = list(said)

    def urlopen(req, timeout):
        no = left.pop(0)
        if isinstance(no, int):
            raise urllib.error.HTTPError(req.full_url, no, "said", {}, None)
        if no == "refused":  # nothing listens: the call never left this machine
            raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        raise no

    tf.models()  # the list and its prices, asked before the stub: only the completion meets it
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(tf, "_sleep", lambda s: None)


@pytest.mark.parametrize(
    "said, kept",
    [
        (
            (TimeoutError("timed out"), 503),
            True,
        ),  # the first try may have been done: its retry's 503 says nothing
        ((TimeoutError("timed out"), "refused"), True),
        ((503,) * 6, True),  # the fault is on Token Factory's side, after the call reached it
        ((401,), False),  # refused as it arrived: nothing was done
        ((429,) * 6, False),
        (("refused",) * 6, False),  # never reached
    ],
    ids=["timeout-then-503", "timeout-then-refused", "503s", "401", "429s", "refused"],
)
def test_a_failed_call_is_freed_only_when_nothing_can_have_been_done(fake, opened, monkeypatch, said, kept):
    fake([])
    _answers(monkeypatch, *said)
    with pytest.raises(tf.Unreachable) as no:
        tf.chat(NANO, ASK, max_tokens=64)
    assert isinstance(no.value, tf.Late) is kept
    [held] = [r for r in rows(opened) if r["kind"] == "reserve"]
    [settled] = [r for r in rows(opened) if r["kind"] == "settle"]
    assert settled["dollars"] == (held["dollars"] if kept else 0.0) and held["dollars"] > 0
