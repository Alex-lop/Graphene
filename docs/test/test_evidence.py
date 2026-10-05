"""evidence.py on hand-made rows and a hand-made ledger, where every expected cell is worked out here, and
on one arm A run against the scripted fake Token Factory (arm B′ is counted in test_arm_bprime.py).

    uv run pytest -q docs/test/test_evidence.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tests"))
import arm_a  # noqa: E402
import evidence  # noqa: E402
from fake_tokenfactory import Fake, call  # noqa: E402

from graphene_map.nemotron import tokenfactory as tf  # noqa: E402

LIVE = ["token factory"]


def row(task, arm, n, t0, passed, total=6, quality=None, secs=100.0, calls=2, **more) -> dict:
    """One run's row as `add` writes it; its window is [t0, t0 + 50]."""
    tree = arm in ("B", "B′")
    base = {
        "task": task,
        "arm": arm,
        "run": f"{task}-{arm}-{n}",
        "dir": f"/runs/{task}-{arm}-{n}",
        "void": "",
        "t0": t0,
        "t1": t0 + 50,
        "accept": {"passed": passed, "failed": total - passed, "error": False},
        "quality": None if quality is None else {"passed": quality, "failed": 12 - quality, "error": False},
        "modelled_seconds": secs,
        "wall_seconds": 50.0,
        "restarts": 1,
        "restarts_unmandated": 0,
        "files_outside_intent": [],
        "forks": 0 if tree else None,
        "escalations": 0 if tree else None,
        "usage_calls": calls,
        "endpoints": LIVE,
        "unpriced": 0,
        "claude_cost_usd": None,
        **({"landed": 3, "handed_back": 1, "failed": 0} if tree else {}),
    }
    return base | more


def spend(t0: float, *dollars: float) -> list[dict]:
    return [{"at": t0 + 1 + k, "tag": "x", "model": "m", "dollars": d} for k, d in enumerate(dollars)]


ROWS = [
    row("feeds", "A", 1, 1000, 4, quality=9, secs=300.0),
    row("feeds", "B", 1, 2000, 6, quality=12, secs=120.0),
    row("feeds", "B′", 1, 3000, 6, quality=11, secs=40.0, void="the paragraph's blob differs"),
    row("feeds", "A", 2, 4000, 5, quality=12, secs=280.0),
    row("feeds", "B", 2, 5000, 6, quality=11, secs=150.0),
    row("feeds", "C", 1, 6000, 6, quality=12, secs=200.0, calls=0, endpoints=[], claude_cost_usd=0.9),
]
LEDGER = (
    spend(1000, 0.01, 0.02)
    + spend(2000, 0.1, 0.2)
    + spend(3000, 0.5, 0.5)
    + spend(4000, 0.02, 0.02)
    + spend(5000, 0.2, 0.2)
)


def test_the_table_is_laid_out_as_registered_and_empty_cells_say_so():
    cost = evidence.dollars(ROWS, LEDGER)
    md = evidence.table(ROWS, cost, "hand-made rows", [])
    lines = [ln for ln in md.splitlines() if ln.startswith("| ") and ln.split(" | ")[1] in "A B B′ C".split()]
    assert [tuple(ln.split(" | ")[:2]) for ln in lines] == [
        (f"| {t}", a) for t in ("feeds", "inventory", "logs", "report") for a in ("A", "B", "B′", "C")
    ]
    # every run in run order, then the range; A's dollars are 0.01 + 0.02 and 0.02 + 0.02
    assert lines[0] == (
        "| feeds | A | 2 | 4 · 5 of 6 (4–5) | no · no | 9 · 12 of 12 (9–12) | 300 · 280 (280–300) "
        "| $0.0300 · $0.0400 ($0.0300–$0.0400) | 50 · 50 | 1 · 1; unmandated 0 · 0 | n/a | n/a | n/a |"
    )
    assert lines[1].startswith("| feeds | B | 2 | 6 · 6 of 6 | yes · yes | 12 · 11 of 12 (11–12) | 120 · 150")
    assert lines[1].endswith("| 3/1/0 · 3/1/0 | 0 · 0 | 0 · 0 |")
    assert lines[2] == (
        "| feeds | B′ | 1 (1 void) | void | void | void | void | void | void "
        "| void; unmandated void | void | void | void |"
    )
    assert "| feeds | C | 1 | 6 of 6 | yes | 12 of 12 | 200 | $0.9000 |" in lines[3]
    assert lines[4] == (
        "| inventory | A | 0 | not run | not run | n/a | not run | not run | not run | not run "
        "| n/a | n/a | n/a |"
    )
    assert lines[5].endswith("| not run | not run | not run |") and "| n/a |" in lines[5]
    assert "Stand-in people with live models" in md and "STAND-IN" not in md

    said = dict(
        (h, r)
        for h, _, r in (
            ln.split(" | ")[0:3:2] and ln[2:-2].split(" | ") for ln in md.splitlines() if ln.startswith("| H")
        )
    )
    assert said["H1"] == (
        "accept: higher (the registered direction); quality: no difference shown at n = 2"
    )  # 12, 11 against 9, 12
    assert said["H2"] == "person-seconds: lower (the registered direction)"
    assert (
        said["H3"] == "accept: not tested (no B′ runs); quality: not tested (no B′ runs)"
    )  # its one run is void
    assert said["H4"].startswith(
        "inventory: H1 accept: not tested (no B runs); H2 person-seconds: not tested"
    )
    assert said["H5"] == (
        "dollars per fully accepted run: B: $0.3500 (2 of 2 fully accepted); "
        "C: $0.9000 (1 of 1 fully accepted). B's accept (6–6 passed) is within C's range (6–6)"
    )


def test_a_comparison_says_higher_or_lower_only_when_the_ranges_do_not_overlap():
    names = ("B", "A")
    assert evidence.compare([5, 6], [4, 5], names) == "higher"  # touching at 5 is at or past, medians differ
    assert evidence.compare([5, 5], [5, 5], names) == "no difference shown at n = 2"  # the same medians
    assert evidence.compare([3, 6, 6], [4, 5], names) == "no difference shown at n = 3 and 2"
    assert evidence.compare([1, 2], [3, 3], names) == "lower"
    assert evidence.compare([], [3], names) == "not tested (no B runs)"
    assert evidence.registered("lower", "higher") == "lower (against the registered direction)"


def test_dollars_are_unknown_whenever_the_ledger_cannot_tell_them():
    rows = [
        row("feeds", "A", 1, 1000, 6, calls=3),  # the ledger holds 2 calls in its window, not 3
        row("feeds", "B", 1, 2000, 6, unpriced=1),  # an attempt with no usage row
        row("feeds", "B", 2, 3000, 6),  # its window shares a ledger row with the next run
        row("feeds", "A", 2, 3040, 6),
        row("feeds", "A", 3, 5000, 6),  # the one that can be told
        row("feeds", "C", 1, 6000, 6, calls=0, endpoints=[], claude_cost_usd=1.5, unpriced=1),
    ]
    ledger = (
        spend(1000, 0.1, 0.1) + spend(2000, 0.1) + spend(3000, 0.1) + spend(3044, 0.1) + spend(5000, 0.3, 0.4)
    )
    cost = evidence.dollars(rows, ledger)
    assert [cost[r["dir"]] for r in rows] == ["unknown"] * 4 + [0.7, "unknown"]


def test_rows_that_are_not_live_are_refused_unless_stand_in_and_then_the_chart_says_so(tmp_path, capsys):
    rows = tmp_path / "rows.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    stand = [
        *ROWS[:2],
        row("feeds", "B′", 1, 3000, 5, quality=10, endpoints=["a stand-in"]),
        row("feeds", "A", 3, 7000, 5, calls=0, endpoints=[]),
    ]
    rows.write_text("".join(json.dumps(r) + "\n" for r in stand))
    ledger.write_text("".join(json.dumps(e) + "\n" for e in LEDGER))
    svg = tmp_path / "evidence.svg"
    argv = [
        "report",
        "--rows",
        str(rows),
        "--ledger",
        str(ledger),
        "--svg",
        str(svg),
        "--out",
        str(tmp_path / "t.md"),
    ]
    assert evidence.main(argv) == 2 and not svg.exists() and not (tmp_path / "t.md").exists()
    out = capsys.readouterr().out
    assert "feeds B′ feeds-B′-1: a stand-in" in out and "feeds A feeds-A-3: no usage row" in out
    assert evidence.main([*argv, "--stand-in"]) == 0
    drawn = svg.read_text()
    assert "STAND-IN, NOT LIVE: The same paragraph to Nemotron, with the tree and without: feeds" in drawn
    assert "a stand-in, no usage row" in drawn and "Live Nemotron" not in drawn
    # A's two runs in accept and in seconds; in quality and dollars only the first (the second has neither)
    assert (
        drawn.count("<title>A · ") == 6 and drawn.count('<circle class="dot A"') == 6 + 1
    )  # and its legend key
    assert "1 unknown" in drawn
    assert "**STAND-IN, NOT LIVE:**" in (tmp_path / "t.md").read_text()

    rows.write_text("".join(json.dumps(r) + "\n" for r in ROWS))  # all live: no flag needed, none shown
    assert evidence.main(argv) == 0
    drawn = svg.read_text()
    assert "STAND-IN" not in drawn and "Live Nemotron on Token Factory; the people are stand-ins" in drawn
    assert "<title>B′ · " not in drawn and "1 void" in drawn  # B′'s one run is void: not drawn
    assert "C, Claude Code, is a reference point" in drawn and "<title>C · " not in drawn


def test_practice_is_refused_whatever_the_flags(tmp_path, capsys):
    """A run made under the person's opening is live and is practice: STAND-IN would be false, and no
    registered table takes it. Its usage rows say so, or the ledger's rows in its window do."""
    rows, ledger = tmp_path / "rows.jsonl", tmp_path / "ledger.jsonl"
    argv = ["report", "--rows", str(rows), "--ledger", str(ledger), "--svg", str(tmp_path / "e.svg")]
    rows.write_text(json.dumps(row("feeds", "A", 1, 1000, 4, practice=True)) + "\n"
                    + json.dumps(row("feeds", "B′", 1, 3000, 5)) + "\n")  # fmt: skip
    ledger.write_text(json.dumps({"at": 3010, "dollars": 0.1, "practice": True}) + "\n")
    for flags in ([], ["--stand-in"]):
        assert evidence.main([*argv, *flags]) == 2 and not (tmp_path / "e.svg").exists()
        out = capsys.readouterr().out
        assert "these runs are practice" in out and "feeds A feeds-A-1: its usage rows say practice" in out
        assert "feeds B′ feeds-B′-1: the ledger's rows in its window say practice" in out
    ledger.write_text(json.dumps({"at": 9000, "dollars": 0.1, "practice": True}) + "\n")  # in no run's window
    rows.write_text(json.dumps(row("feeds", "B′", 1, 3000, 5)) + "\n")
    assert evidence.main(argv) == 0


def test_a_tree_row_with_leaves_no_usage_row_holds_and_a_c_row_with_no_total_are_not_live(tmp_path, capsys):
    """The planner's usage row alone came from Token Factory; three leaf attempts wrote none (a Claude Code or
    scripted executor), and a C row whose run log holds no Claude Code total: neither is drawn as live."""
    rows, ledger = tmp_path / "rows.jsonl", tmp_path / "ledger.jsonl"
    ledger.write_text("")
    argv = ["report", "--rows", str(rows), "--ledger", str(ledger), "--svg", str(tmp_path / "e.svg")]
    for bad, said in (
        (row("feeds", "B", 1, 2000, 6, calls=1, unpriced=3), "B feeds-B-1: an attempt with no usage row"),
        (row("feeds", "C", 1, 6000, 6, calls=0, endpoints=[]), "C feeds-C-1: no Claude Code total"),
    ):
        rows.write_text(json.dumps(bad) + "\n")
        assert evidence.main(argv) == 2 and said in capsys.readouterr().out
        assert evidence.main([*argv, "--stand-in"]) == 0
        assert "**STAND-IN, NOT LIVE:**" in capsys.readouterr().out


ACCEPT = """import json, sys
sys.path.insert(0, sys.argv[1])
from app import greet
ok = greet() == "hello"
print(json.dumps({"passed": int(ok), "failed": int(not ok), "details": []}))
"""


@pytest.mark.parametrize("opened", [False, True])
def test_an_arm_a_run_is_counted_from_its_run_log_its_bill_and_the_ledger(
    tmp_path, monkeypatch, capsys, opened
):
    """And under the person's opening (GRAPHENE_AGENT_LIVE_USD, set here as the person sets it) the run is
    practice: its bill and its ledger rows say so, its calls are on the night's bill, and `add` refuses it."""
    if opened:
        monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "10")
    run, repo = tmp_path / "feeds-sealed-nano-1", tmp_path / "feeds-sealed-nano-1" / "repo"
    repo.mkdir(parents=True)

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (repo / "app.py").write_text('def greet():\n    return "hi"\n')
    git("add", "-A")
    git("commit", "-qm", "start")
    (run / "base.sha").write_text(git("rev-parse", "HEAD"))
    card = tmp_path / "tasks" / "tiny"
    card.mkdir(parents=True)
    (card / "intent_globs.txt").write_text("app.py\n")
    (card / "accept.py").write_text(ACCEPT)
    (tmp_path / "m1.txt").write_text("make greet say hello")
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setenv("GRAPHENE_LEDGER", str(ledger))
    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", "10")  # arm_a.py starts nothing without one
    monkeypatch.delenv("GRAPHENE_NODE", raising=False)
    runlog = run / "runlog.jsonl"

    def logline(*args, stdin=None):
        subprocess.run(
            [sys.executable, str(HERE / "logline.py"), str(runlog), *args],
            input=stdin,
            text=True,
            check=True,
            capture_output=True,
        )

    with Fake([call("edit", path="app.py", old='"hi"', new='"hello"'), call("done")]) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        logline("person", "prompt", stdin="make greet say hello")
        assert arm_a.main([str(repo), "--paragraph-file", str(tmp_path / "m1.txt"), "--steps", "5"]) == 0
        logline("executor", "result", "--from-json", str(run / "arm-a.json"))
        logline("person", "read", stdin="greet says hello now")
        logline("person", "review", "done")
    tf._listed.cache_clear()

    rows = tmp_path / "rows.jsonl"
    argv = [
        "add",
        str(run),
        "--task",
        "tiny",
        "--arm",
        "A",
        "--rows",
        str(rows),
        "--tasks",
        str(tmp_path / "tasks"),
    ]
    if opened:
        assert json.loads((run / "arm-a.json").read_text())["practice"] is True
        assert all(e["practice"] for e in evidence.read_jsonl(ledger))
        night = evidence.read_jsonl(tmp_path / "night.jsonl")  # the conftest's night, not the real one
        assert sum(e["kind"] == "settle" for e in night) == 2
        assert evidence.main(argv) == 2 and not rows.exists()
        assert "not added: feeds-sealed-nano-1 is practice" in capsys.readouterr().out
        return
    assert evidence.main(argv) == 0
    [r] = evidence.read_jsonl(rows)
    assert (r["arm"], r["accept"], r["quality"]) == ("A", {"passed": 1, "failed": 0, "error": False}, None)
    assert r["endpoints"] == ["a stand-in"] and r["usage_calls"] == 2 and r["unpriced"] == 0
    assert (r["forks"], r["escalations"]) == (None, None) and "landed" not in r
    # the prompt (20 characters typed) and the review (a key) are the acts; the read is 4 words
    assert r["modelled_seconds"] == round(0.28 * 20 + 1.35 * 2 + 4 * 60 / 250, 1)
    assert (
        evidence.dollars([r], evidence.read_jsonl(ledger))[r["dir"]]
        == round(sum(e["dollars"] for e in evidence.read_jsonl(ledger)), 6)
        > 0
    )
