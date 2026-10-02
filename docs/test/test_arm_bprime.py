"""arm_bprime.py against the scripted fake Token Factory, on test_bench.py's tiny task (never one of the
four real ones): the paragraph goes to the planner as it is, every proposal is accepted whole, offers
are taken by the bench's rule, the change of mind goes to the planner as it is and only what it adds is
run; nothing is edited, dropped or reopened. evidence.py then counts the run as it counts every arm.

  greet  lands
  bye    wants app/words.py (inside intent): the offer is taken, and it lands the next round
  cfg    proposed from the change of mind, run in the change's own round, lands
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tests"))
import arm_bprime  # noqa: E402
import bench  # noqa: E402
import evidence  # noqa: E402
import make_task  # noqa: E402
from fake_tokenfactory import Fake, call  # noqa: E402
from test_bench import ACCEPT, FILES  # noqa: E402

from graphene_map import tokenfactory as tf  # noqa: E402

NANO = "nvidia/Nemotron-3-Nano-fake"
ULTRA = "nvidia/Nemotron-3-Ultra-fake"
PARAGRAPH = "make the tiny app friendlier: it should say hello, and goodbye.\n"
CHANGE = "and configure it, please.\n"
FIRST = """```plan
goal: a friendlier tiny app
? say hello  [greet]
    scope: app/greet.py
    check: python3 -c 'from app.greet import greet; assert greet() == "hello"'
? say goodbye  [bye]
    scope: app/bye.py
    check: python3 -c 'from app.bye import bye; assert bye() == "goodbye"'
```"""
SECOND = """```plan
? configure  [cfg]
    scope: app/cfg.py
    check: test -s app/cfg.py
```"""
SCRIPT = {
    "greet": [call("edit", path="app/greet.py", old='"hi"', new='"hello"'), call("done")],
    "bye": [
        call("edit", path="app/words.py", old='"bye"', new='"goodbye"'),
        call("release", why="the word is in app/words.py, outside my scope", wants=["app/words.py"]),
    ],
    "bye widened": [call("edit", path="app/words.py", old='"bye"', new='"goodbye"'), call("done")],
    "cfg": [call("write", path="app/cfg.py", content="X = 1\n"), call("done")],
}


def model(body: dict) -> dict:
    first = body["messages"][1]["content"]
    if body["model"] == ULTRA:  # the planner, asked the paragraph and then the change, each as it is
        return {"content": SECOND if f"The person said: {CHANGE}" in first else FIRST}
    leaf = next(ln.split(" (revision")[0] for ln in first.splitlines() if " (revision " in ln)
    steps = SCRIPT["bye widened" if "app/bye.py, app/words.py" in first else leaf]
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    return steps[k] if k < len(steps) else {"content": "nothing more"}


@pytest.fixture
def tiny(tmp_path, monkeypatch):
    monkeypatch.setitem(make_task.TASKS, "tiny", FILES)
    card = tmp_path / "tasks" / "tiny"
    card.mkdir(parents=True)
    (card / "intent_globs.txt").write_text("app/**\n")
    (card / "accept.py").write_text(ACCEPT)
    (tmp_path / "paragraph.md").write_text(PARAGRAPH)
    (tmp_path / "change.md").write_text(CHANGE)
    monkeypatch.setenv("GRAPHENE_LEDGER", str(tmp_path / "ledger.jsonl"))  # arm_bprime sets both: put back
    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", "30")
    for mark in bench.MARKS:
        monkeypatch.delenv(mark, raising=False)
    with Fake([model] * 200) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        yield tmp_path, f
    tf._listed.cache_clear()


def test_every_proposal_is_taken_whole_the_change_goes_verbatim_and_evidence_counts_it(tiny, capsys):
    tmp, f = tiny
    code = arm_bprime.main(
        [
            "tiny",
            "--paragraph-file",
            str(tmp / "paragraph.md"),
            "--change-file",
            str(tmp / "change.md"),
            "--executor",
            f"nemotron --model {NANO}",
            "--parallel",
            "2",
            "--tasks",
            str(tmp / "tasks"),
            "--out",
            str(tmp / "out"),
            "--ledger",
            str(tmp / "ledger.jsonl"),
        ]
    )
    assert code == 0
    run = tmp / "out" / "tiny-bprime-1"
    said = [json.loads(ln) for ln in (run / "runlog.jsonl").read_text().splitlines()]
    assert [(e["who"], e["type"]) for e in said] == [
        ("person", "prompt"),
        ("person", "accept"),
        ("person", "run"),
        ("person", "widen"),
        ("person", "run"),
        ("person", "correction"),
        ("person", "accept"),
        ("person", "run"),
        ("harness", "end"),
    ]
    # as a stand-in sends a written file, MSG=$(cat FILE): the final newline is not part of the message
    assert said[0]["text"] == PARAGRAPH.rstrip("\n") and said[5]["text"] == CHANGE.rstrip("\n")
    assert said[5]["mandated"] is True
    assert said[7]["text"].endswith("--node cfg")  # only what the change added
    asked = [r["messages"][1]["content"] for r in f.requests if r["model"] == ULTRA]
    assert (
        len(asked) == 2
        and f"The person said: {PARAGRAPH}" in asked[0]
        and f"The person said: {CHANGE}" in asked[1]
    )
    repo = run / "repo"
    assert (repo / "app/greet.py").read_text() == 'def greet():\n    return "hello"\n'
    assert (repo / "app/cfg.py").read_text() == "X = 1\n"

    rows = tmp / "rows.jsonl"
    assert (
        evidence.main(
            [
                "add",
                str(run),
                "--task",
                "tiny",
                "--arm",
                "B'",
                "--rows",
                str(rows),
                "--tasks",
                str(tmp / "tasks"),
            ]
        )
        == 0
    )
    [row] = evidence.read_jsonl(rows)
    assert (row["arm"], row["task"], row["run"], row["void"]) == ("B′", "tiny", "tiny-bprime-1", "")
    assert row["accept"] == {"passed": 2, "failed": 0, "error": False} and row["quality"] is None
    assert (row["landed"], row["handed_back"], row["failed"]) == (2, 1, 0)  # bye came back once, then landed
    assert (row["forks"], row["escalations"], row["unpriced"]) == (0, 0, 0)
    assert row["endpoints"] == ["a stand-in"] and row["usage_calls"] == len(f.requests) == 10
    assert row["restarts"] == 1 and row["restarts_unmandated"] == 0
    assert row["modelled_seconds"] > 0 and row["files_outside_intent"] == []
    assert (
        evidence.main(
            [
                "add",
                str(run),
                "--task",
                "tiny",
                "--arm",
                "B′",
                "--rows",
                str(rows),
                "--tasks",
                str(tmp / "tasks"),
            ]
        )
        == 2
    )  # a run is counted once

    ledger = evidence.read_jsonl(tmp / "ledger.jsonl")
    cost = evidence.dollars([row], ledger)
    assert cost[row["dir"]] == round(sum(e["dollars"] for e in ledger), 6) > 0  # all ten calls, in its window

    svg = tmp / "evidence.svg"
    report = [
        "report",
        "--rows",
        str(rows),
        "--ledger",
        str(tmp / "ledger.jsonl"),
        "--svg",
        str(svg),
        "--out",
        str(tmp / "table.md"),
        "--task",
        "tiny",
    ]
    capsys.readouterr()
    assert evidence.main(report) == 2 and not svg.exists()  # the fake is not Token Factory
    assert "tiny B′ tiny-bprime-1: a stand-in" in capsys.readouterr().out
    assert evidence.main([*report, "--stand-in"]) == 0
    assert "STAND-IN, NOT LIVE: The same paragraph" in svg.read_text()
    assert "| tiny | B′ | 1 | 2 of 2 | yes | n/a |" in (tmp / "table.md").read_text()


def test_with_no_spend_cap_set_no_run_starts_and_none_is_assumed(tiny, monkeypatch, capsys):
    tmp, f = tiny
    monkeypatch.delenv("GRAPHENE_SPEND_CAP_USD")
    argv = ["tiny", "--paragraph-file", str(tmp / "paragraph.md"), "--executor", "nemotron", "--tasks",
            str(tmp / "tasks"), "--out", str(tmp / "out"), "--ledger", str(tmp / "ledger.jsonl")]  # fmt: skip
    assert arm_bprime.main(argv) == 2
    assert "export GRAPHENE_SPEND_CAP_USD=10" in capsys.readouterr().out
    assert not [r for r in f.requests if "messages" in r] and not (tmp / "out").exists()
