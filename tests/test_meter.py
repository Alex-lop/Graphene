"""The meter reads an executor's own stream: the fixtures are real ones from the meter night (Claude Code
2.1.292 with Sonnet 5.5; codex-cli 0.151.0 against Nemotron Super on Token Factory; a Codex run whose
login was revoked)."""

import shlex
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene_map import meter as M
from graphene_map.run import CODEX, DEFAULT_WITH, WORST, _worst

FIXTURES = Path(__file__).parent / "fixtures" / "meter"


def fed(name: str, meter: M.Meter) -> list[tuple[str, dict]]:
    return [row for line in (FIXTURES / name).read_text().splitlines() for row in meter.feed(line)]


def test_claude_turns_tokens_and_dollars_settle_to_what_it_reports():
    meter = M.Meter("claude", 1)
    rows = fed("claude.jsonl", meter)
    usage = [d for k, d in rows if k == "usage"]
    assert meter.model == "claude-sonnet-5-5" and meter.turns == 3 and meter.unread == 0
    assert [d["turn"] for d in usage[:-1]] == [1, 2, 3] and "turn" not in usage[-1]
    # the stream says 16 + 16 + 43 tokens out, written before each message ends; the result says 539
    assert (meter.prompt_tokens, meter.completion_tokens) == (6 + 11782 + 48637, 539)
    assert sum(d["dollars"] for d in usage) == pytest.approx(0.0622574) == meter.dollars
    assert usage[-1] | {"dollars": 0} == {
        "model": "claude-sonnet-5-5", "calls": 0, "prompt_tokens": 0, "completion_tokens": 539 - 75,
        "dollars": 0, "endpoint": "claude code", "attempt": 1, "turns": 3,
        "reported": 0.062257400000000004}  # fmt: skip
    did = [(d["verb"], d["target"]) for k, d in rows if k == "did"]
    assert did == [("reading", "hello.py"), ("editing", "hello.py"), ("running", "python3 hello.py")]
    assert meter.last.startswith("I added `add(a, b)`")


def test_the_list_price_of_the_whole_claude_run_is_its_reported_total():
    total = {"input_tokens": 6, "cache_creation_input_tokens": 11782, "cache_read_input_tokens": 48637,
             "cache_creation": {"ephemeral_1h_input_tokens": 11782}, "output_tokens": 539}  # fmt: skip
    assert M.list_price("claude-sonnet-5-5", total) == pytest.approx(0.0622574, rel=1e-12)
    assert M.list_price("claude-sonnet-5-5[1m]", total) == M.list_price("claude-sonnet-5-5", total)
    five = {"cache_creation_input_tokens": 1_000_000}  # a write with no breakdown is a 5-minute one
    assert M.list_price("claude-haiku-4-5-20251001", five) == pytest.approx(1.25)
    assert M.list_price("gpt-9", total) is None


def test_a_message_split_over_events_is_counted_once():
    meter = M.Meter("claude", 1)
    usage = '"usage": {"input_tokens": 10, "output_tokens": 5}'
    line = ('{"type": "assistant", "message": {"id": "msg_1", "model": "claude-opus-5-5", ' + usage
            + ', "content": [{"type": "text", "text": "%s"}]}}')  # fmt: skip
    first, second = meter.feed(line % "one"), meter.feed(line % "two")
    assert [k for k, _ in first] == ["usage", "said"] and [k for k, _ in second] == ["said"]
    assert (meter.turns, meter.prompt_tokens, meter.completion_tokens) == (1, 10, 5)


def test_a_resumed_attempt_takes_off_what_the_session_paid_before():
    meter = M.Meter("claude", 2, paid_before=0.05)
    rows = fed("claude.jsonl", meter)
    turns = sum(d["dollars"] for k, d in rows if k == "usage" and "turn" in d)
    assert rows[-1][1]["dollars"] == pytest.approx(0.0622574 - 0.05 - turns)
    assert meter.dollars == pytest.approx(0.0122574) and meter.reported == pytest.approx(0.0622574)


def test_codex_commands_said_and_usage():
    meter = M.Meter("codex", 1, model="nvidia/nemotron-3-super-120b-a12b")
    rows = fed("codex.jsonl", meter)
    assert [d["target"] for k, d in rows if k == "did"] == ["cat hello.py", "cat > hello.py << 'EOF'",
                                                            "python3 hello.py"]  # fmt: skip
    said = [d["text"] for k, d in rows if k == "said"]
    assert said[0].startswith("error: Model metadata for") and said[1] == "hi" and meter.last == "hi"
    assert rows[-1] == ("usage", {"model": "nvidia/nemotron-3-super-120b-a12b", "calls": 1,
                                  "prompt_tokens": 48940, "completion_tokens": 344, "dollars": 0,
                                  "endpoint": "codex", "attempt": 1, "turn": 1, "priced": False})  # fmt: skip
    assert meter.unread == 1 and not meter.priced  # "Reading additional input from stdin..."

    priced = M.Meter("codex", 1, model="super", price=lambda m: (1e-7, 5e-7) if m == "super" else None)
    usage = fed("codex.jsonl", priced)[-1][1]
    assert usage["dollars"] == pytest.approx(48940e-7 + 344 * 5e-7) and "priced" not in usage
    assert M.Meter("codex", 1).model == "codex"


def test_a_failed_codex_run_says_its_error():
    meter = M.Meter("codex", 1)
    rows = fed("codex-failed.jsonl", meter)
    said = "error: Your access token could not be refreshed because your refresh token was revoked."
    assert rows == [("said", {"attempt": 1, "text": said + " Please log out and sign in again."})]
    assert meter.unread == 9  # the stdin note and the eight lines of the login error on stderr


def test_garbage_never_raises_and_counts_as_unread():
    broken = {"claude": '{"type": "assistant"}',
              "codex": '{"type": "turn.completed", "usage": {"input_tokens": "x"}}'}  # fmt: skip
    for k, line in broken.items():
        meter = M.Meter(k, 1)
        lines = ["warning: x", '{"type": "assistant", "mess', "[1, 2]", "{}", "null", "", line]
        assert all(meter.feed(line) == [] for line in lines)
        assert (meter.unread, meter.turns) == (6, 0)


def test_kind_and_model_on_real_command_lines():
    claude = shlex.split(DEFAULT_WITH)
    assert M.kind(claude) == "claude" and M.kind(["claude", "-p", "--model", "sonnet"]) is None
    assert M.kind(shlex.split(CODEX)) == "codex"
    codex = shlex.split("codex exec --json --sandbox workspace-write -m x")
    assert M.kind(codex) == "codex" and M.model_in(codex) == "x"
    assert M.kind(["/usr/local/bin/codex", "exec", "--sandbox", "workspace-write"]) is None
    assert M.kind(["python3", "bin/executor.py"]) is None and M.kind([]) is None
    assert M.model_in([*claude, "--model=claude-opus-5-5"]) == "claude-opus-5-5"
    assert M.model_in(claude) is None


def test_an_option_joined_by_equals_reads_as_the_spaced_one():
    """The review of 7 October: `--output-format=stream-json`, which Claude Code accepts, had no meter, and
    `--max-budget-usd=10` held $3 on the night's ledger, so an attempt that could spend $10 passed a cap
    with $3 of room."""
    joined = ["claude", "-p", "--output-format=stream-json", "--max-budget-usd=10", "do the leaf"]
    assert M.kind(joined) == "claude" and _worst(joined) == 10.0
    assert M.kind(["claude", "-p", "--output-format=json"]) is None and _worst(["claude", "-p"]) == WORST


def row(ts: str, kind: str, detail: dict, actor: str | None = "run:claude", node: str = "a") -> dict:
    return {"id": 0, "node_id": node, "timestamp": f"2026-10-07T04:{ts}.000Z", "kind": kind, "actor": actor,
            "session_id": "s", "agent_id": None, "detail": detail}


def usage(attempt: int, dollars: float, calls: int = 1, tokens: int = 100, **more) -> dict:
    return {"model": "claude-sonnet-5-5", "calls": calls, "prompt_tokens": tokens,
            "completion_tokens": tokens // 10, "dollars": dollars, "endpoint": "claude code",
            "attempt": attempt, **more}  # fmt: skip


LOG = [
    row("00:00", "attempt", {"attempt": 1, "log": "x.txt", "checkout": "/w/a"}),
    row("00:05", "usage", {"model": "nemotron", "calls": 2, "prompt_tokens": 7, "completion_tokens": 3,
                           "dollars": 0.01}),  # fmt: skip  (a row from before the meter: no attempt key)
    row("00:10", "did", {"attempt": 1, "tool": "Read", "target": "src/a.py", "verb": "reading"}),
    row("00:15", "usage", usage(1, 0.20, turn=1)),
    row("00:20", "did", {"attempt": 1, "tool": "Edit", "target": "src/a.py", "verb": "editing"}),
    row("00:30", "did", {"attempt": 1, "tool": "Edit", "target": "docs/b.md", "verb": "editing"}),
    row("00:31", "denied", {"path": "docs/b.md", "how": "out of scope"}, actor=None),
    row("00:40", "did", {"attempt": 1, "tool": "Edit", "target": "src/a.py", "verb": "editing"}),
    row("00:50", "said", {"attempt": 1, "text": "docs/b.md was refused"}),
    row("01:00", "usage", usage(1, 0.05, calls=0, tokens=0, turns=1, reported=0.25)),
    row("01:30", "ended", {"attempt": 1, "exit": 1, "seconds": 90, "meter": "claude", "unread": 0}),
    row("01:35", "denied", {"path": "late.txt", "how": "after the attempt"}, actor=None),
    row("02:00", "attempt", {"attempt": 2, "log": "y.txt", "checkout": "/w/a"}),  # resumed: --resume
    row("02:10", "usage", usage(2, 0.05, turn=1)),
    row("02:20", "did", {"attempt": 2, "tool": "Bash", "target": "python3 -m pytest -q", "verb": "running"}),
]
NOW = datetime(2026, 10, 7, 4, 3, tzinfo=UTC)


def test_attempts_of_one_leaf():
    first, second = M.attempts(LOG, ["src/**"], NOW)
    assert first == {
        "attempt": 1, "executor": "claude", "meter": "claude", "model": "claude-sonnet-5-5",
        "started": "2026-10-07T04:00:00.000Z", "log": "x.txt", "seconds": 90, "running": False, "exit": 1,
        "until": datetime(2026, 10, 7, 4, 1, 30, tzinfo=UTC), "turns": 3,
        "prompt_tokens": 107, "completion_tokens": 13, "dollars": pytest.approx(0.26), "priced": True,
        "endpoints": ["", "claude code"],
        "read": ["src/a.py"], "edited": ["src/a.py", "docs/b.md"], "ran": [], "runs": {}, "searched": [],
        "said": "docs/b.md was refused", "last": "docs/b.md was refused",
        "told": ["reading src/a.py", "editing src/a.py", "editing docs/b.md", "editing src/a.py",
                 "docs/b.md was refused"],
        "last_at": "2026-10-07T04:00:50.000Z", "files_in": ["src/a.py"], "files_out": ["docs/b.md"],
        "refused": ["docs/b.md"]}  # fmt: skip
    assert second["running"] and second["seconds"] == 60 and second["exit"] is None and second["until"] == NOW
    assert second["last"] == "running python3 -m pytest -q" and second["ran"] == ["python3 -m pytest -q"]
    assert (second["turns"], second["dollars"], second["refused"]) == (1, 0.05, [])
    assert second["runs"] == {"python3 -m pytest -q": 1} and second["log"] == "y.txt"
    assert M.attempts([row("00:00", "started", {}), row("00:05", "released", {})]) == []  # never tried


def test_an_attempt_says_its_meter_from_its_start():
    """Live, 7 October: a Claude Code leaf read "no meter" until its first turn's usage came. Its attempt
    row says which stream it writes, so until then it has a meter and no usage yet."""
    starting = [row("00:00", "attempt", {"attempt": 1, "meter": "claude"})]
    unread = [row("00:00", "attempt", {"attempt": 1, "meter": None})]
    assert [a["meter"] for a in M.attempts(starting, now=NOW)] == ["claude"]
    assert [a["meter"] for a in M.attempts(unread, now=NOW)] == [None]


def test_agents_and_you():
    b = [row("00:00", "attempt", {"attempt": 1}, actor="run:codex", node="b"),
         row("00:30", "usage", usage(1, 0, turn=1, endpoint="codex", priced=False), node="b"),
         row("01:00", "ended", {"attempt": 1, "exit": 0, "meter": "codex", "unread": 1}, node="b")]
    person = [row("00:00", "accepted", {}, actor="alex"), row("00:00", "edited", {}, actor="alex (no tty)"),
              row("00:59", "answered", {}, actor="alex"), row("02:05", "setting", {}, actor="alex"),
              row("02:06", "accepted", {}, actor="sam")]  # fmt: skip
    log = LOG + b + person
    assert M.agents(log, NOW) == {"running": 1, "seconds": 90 + 60 + 60, "dollars": pytest.approx(0.31),
                                  "unpriced": 110}  # fmt: skip
    assert M.you(log, "alex") == {"acts": 3, "minutes": 2}


def test_a_leaf_never_attempted_has_no_attempts_and_the_clock_still_reads():
    planned = [row("00:00", "proposed", {}, actor="alex", node="c"), row("00:01", "accepted", {}, "alex")]
    assert M.attempts(planned[:1]) == []
    assert M.agents(planned, NOW) == {"running": 0, "seconds": 0, "dollars": 0, "unpriced": 0}
    held = [row("00:02", "started", {}, actor="claude:aaaa1111", node="c"),
            row("00:09", "finished", {}, actor="claude:aaaa1111", node="c")]  # fmt: skip
    assert M.width(planned + held, NOW) is None  # a session's hold makes no attempt: nothing ran, no width


def at(stamp: str, kind: str, node: str, attempt: int = 1) -> dict:
    """An attempt's row on ``node`` at `MM:SS.mmm` after 04:00, to the millisecond as the log stamps it."""
    return row("00:00", kind, {"attempt": attempt}, node=node) | {"timestamp": f"2026-10-07T04:{stamp}Z"}


def test_width_is_the_most_leaves_at_once_and_the_share_of_agent_seconds_with_one_alone():
    # a from 0 to 60 s, b from 30 to 90 s: each ran 30 s alone, of 120 agent seconds
    rows = [at("00:00.000", "attempt", "a"), at("00:30.000", "attempt", "b"), at("01:00.000", "ended", "a"),
            at("01:30.000", "ended", "b")]  # fmt: skip
    assert M.width(rows, NOW) == {"most": 2, "lanes": 2, "alone": 0.5}


@pytest.mark.parametrize("starts", ["00:10.000", "00:10.882"])
def test_an_attempt_that_ends_as_another_starts_does_not_overlap_it(starts):
    """[start, end): b starts the moment a ends, or later in the same second, as a run hands over."""
    rows = [at("00:00.000", "attempt", "a"), at("00:10.000", "ended", "a"), at(starts, "attempt", "b"),
            at("00:20.000", "ended", "b")]  # fmt: skip
    assert M.width(rows, NOW) == {"most": 1, "lanes": 2, "alone": 1.0}
    rows[2] = at("00:09.900", "attempt", "b")  # b began before a ended: a tenth of a second at once
    assert M.width(rows, NOW)["most"] == 2


def test_a_leaf_that_tried_twice_is_one_lane_and_an_attempt_running_now_runs_until_now():
    rows = [at("00:00.000", "attempt", "a"), at("00:20.000", "ended", "a"),
            at("00:25.000", "attempt", "a", 2), at("00:40.000", "ended", "a", 2),
            at("00:30.000", "attempt", "b")]  # fmt: skip  (b runs on)
    # a: 0-20 s and 25-40 s; b: 30 s to now, 180 s in. At once from 30 to 40 s: 165 of 185 agent seconds alone
    assert M.width(rows, NOW) == {"most": 2, "lanes": 2, "alone": pytest.approx(165 / 185)}


def test_an_attempt_from_before_the_meter_ends_where_its_hold_did():
    older = [row("00:00", "attempt", {"attempt": 1}), row("00:40", "finished", {"changed": ["a.py"]}),
             row("00:00", "attempt", {"attempt": 1}, node="b"), row("00:30", "released", {}, node="b")]
    assert [(a["running"], a["seconds"]) for a in M.attempts(older[:2], now=NOW)] == [(False, 40)]
    assert M.agents(older, NOW) == {"running": 0, "seconds": 70, "dollars": 0, "unpriced": 0}


def test_an_attempt_with_no_ended_row_ends_where_its_leaf_was_dropped():
    """The review of 7 October: a run killed hard (or a store from before the meter), then its leaf
    dropped, left an attempt with no `ended` row running for good: the next morning the status line
    read `agents: 1 running · 1440 min` with nothing running, and the minutes kept growing."""
    dropped = [row("00:00", "attempt", {"attempt": 1}), row("00:20", "usage", usage(1, 0.03, turn=1)),
               row("05:00", "dropped", {}, actor="alex")]  # fmt: skip
    morning = datetime(2026, 10, 8, 4, 0, tzinfo=UTC)
    assert [(a["running"], a["seconds"]) for a in M.attempts(dropped, now=morning)] == [(False, 300)]
    assert M.agents(dropped, morning) == {"running": 0, "seconds": 300, "dollars": 0.03, "unpriced": 0}


def test_a_claude_attempt_its_result_settled_is_priced_whatever_model_its_turns_named():
    """The review of 7 October: on a Claude model PRICES lacks (claude-sonnet-4-5), each turn says
    "priced": False, and the attempt stayed so after its result settled it at the $0.0623 Claude Code
    reported: `node show` said `no list price`, the views dropped the dollars, and the run's last line
    added `+ 60k tokens with no list price`. Codex's turns, which nothing settles, still have none."""
    from graphene_map.node_record import bill

    meter = M.Meter("claude", 1)
    stream = (FIXTURES / "claude.jsonl").read_text().replace("sonnet-5-5", "sonnet-4-5-20250929")
    log = [row("00:00", "attempt", {"attempt": 1, "meter": "claude"})]
    log += [row("00:30", k, d) for line in stream.splitlines() for k, d in meter.feed(line)]
    log += [row("01:00", "ended", {"attempt": 1, "exit": 0, "meter": "claude", "unread": 0}),
            row("01:05", "released", {}), row("01:10", "started", {}, actor="run:codex")]  # fmt: skip
    hold = [row("01:10", "attempt", {"attempt": 1, "meter": "codex"}),  # the next run's attempt 1
            row("01:40", "usage", usage(1, 0, turn=1, endpoint="codex", priced=False)),
            row("02:00", "ended", {"attempt": 1, "exit": 0, "meter": "codex", "unread": 1})]  # fmt: skip
    log += [e | {"actor": "run:codex", "session_id": "t"} for e in hold]
    claude, codex = M.attempts(log, now=NOW)
    assert claude["model"] == "claude-sonnet-4-5-20250929" and claude["dollars"] == pytest.approx(0.0622574)
    assert claude["priced"] and not codex["priced"]
    assert M.agents(log, NOW)["unpriced"] == bill(log)["unpriced"] == 110  # Codex's 100 in and 10 out


def test_a_codex_edit_named_by_its_absolute_path_is_judged_from_its_checkout():
    """The review of 7 October: Codex names each file it changes by its absolute path (its apply_patch
    joins the patch's path to where it works), and the meter kept it so: an edit inside the scope was
    listed outside it, `1 file, 1 outside` on the strip and `(1 outside the scope: /…/feed.py)` in node
    show. Said from the attempt's checkout, as Claude's paths are; one outside the checkout stays so."""
    line = ('{"type": "item.completed", "item": {"id": "item_5", "type": "file_change", "changes": '
            '[{"path": "/repo/wt/xml/ingest/feed.py", "kind": "update"}, '
            '{"path": "/repo/ingest/feed.py", "kind": "update"}], "status": "completed"}}')  # fmt: skip
    log = [row("00:00", "attempt", {"attempt": 1, "checkout": "/repo/wt/xml", "meter": "codex"})]
    log += [row("00:10", k, d) for k, d in M.Meter("codex", 1).feed(line)]
    [a] = M.attempts(log, ["ingest/**"], NOW)
    assert a["files_in"] == ["ingest/feed.py"] and a["files_out"] == ["/repo/ingest/feed.py"]
    assert a["last"] == "editing /repo/ingest/feed.py" and a["told"][0] == "editing ingest/feed.py"
