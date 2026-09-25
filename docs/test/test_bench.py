"""bench.py end to end, on a tiny task of its own (never the four real ones), with a scripted Nemotron
model behind the recorded fake Token Factory, and `graphene` run as a person runs it.

The tiny task: three leaves under one goal, intent `app/**`.
  greet  its executor edits its file and calls done                       -> landed
  bye    it tries app/words.py (inside intent, outside its scope), is
         refused before the write and hands back: the person takes `w`,
         and the next round it lands                                       -> handed back, then landed
  cfg    it wants vendor/lib.py (outside intent): the person refuses       -> handed back, refused
         and its check (`test -f app/cfg.py`) already passes at the base   -> flagged
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tests"))
import bench  # noqa: E402
import make_task  # noqa: E402
import results  # noqa: E402
from fake_tokenfactory import Fake, call  # noqa: E402

from graphene_map import tokenfactory as tf  # noqa: E402

NANO = "nvidia/Nemotron-3-Nano-fake"
FILES = {
    ".gitignore": ".graphene/\n.claude/\n__pycache__/\n",
    "app/__init__.py": "",
    "app/greet.py": 'def greet():\n    return "hi"\n',
    "app/words.py": 'BYE = "bye"\n',
    "app/bye.py": "from app.words import BYE\n\n\ndef bye():\n    return BYE\n",
    "app/cfg.py": "",
}
SAYS = "python3 -c 'from app.{0} import {0}; assert {0}() == \"{1}\"'"
LEAVES = {
    "greet": ("say hello", "app/greet.py", SAYS.format("greet", "hello")),
    "bye": ("say goodbye", "app/bye.py", SAYS.format("bye", "goodbye")),
    "cfg": ("configure", "app/cfg.py", "test -f app/cfg.py"),
}
ACCEPT = """import json, sys
sys.path.insert(0, sys.argv[1])
from app.bye import bye
from app.greet import greet
details = [{"check": "greet says hello", "ok": greet() == "hello"},
           {"check": "bye says goodbye", "ok": bye() == "goodbye"}]
print(json.dumps({"passed": sum(d["ok"] for d in details), "failed": sum(not d["ok"] for d in details),
                  "details": details}))
"""
SCRIPT = {
    "greet": [call("edit", path="app/greet.py", old='"hi"', new='"hello"'), call("done")],
    "bye": [
        call("edit", path="app/words.py", old='"bye"', new='"goodbye"'),
        call("release", why="the word is in app/words.py, outside my scope", wants=["app/words.py"]),
    ],
    "bye widened": [call("edit", path="app/words.py", old='"bye"', new='"goodbye"'), call("done")],
    "cfg": [
        call("write", path="vendor/lib.py", content="X = 1\n"),
        call("release", why="it needs vendor/lib.py", wants=["vendor/lib.py"]),
    ],
}


def model(body: dict) -> dict:
    """Each leaf's conversation, from its own list, by how far it has got; bye's second hold (its
    scope widened by the person) from another."""
    first = body["messages"][1]["content"]
    leaf = next(ln.split(" (revision")[0] for ln in first.splitlines() if " (revision " in ln)
    steps = SCRIPT["bye widened" if "app/bye.py, app/words.py" in first else leaf]
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    return steps[k] if k < len(steps) else {"content": "nothing more"}


@pytest.fixture
def task(tmp_path, monkeypatch):
    """The tiny task, where bench.py looks for one: its repo in make_task, its card's files and tree
    in directories of its own. Returns a function of the leaves to put in the tree."""
    monkeypatch.setitem(make_task.TASKS, "tiny", FILES)
    card = tmp_path / "tasks" / "tiny"
    card.mkdir(parents=True)
    (card / "intent_globs.txt").write_text("# the person's intent\napp/**\n")
    (card / "accept.py").write_text(ACCEPT)
    monkeypatch.setenv("GRAPHENE_LEDGER", str(tmp_path / "ledger.jsonl"))  # bench sets both: put back after
    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", "30")
    for mark in bench.MARKS:  # the suite may itself run inside an agent's session
        monkeypatch.delenv(mark, raising=False)

    def tree(*ids: str) -> list[str]:
        trees = tmp_path / "trees"
        trees.mkdir(exist_ok=True)
        text = "goal: a friendlier tiny app\n\n" + "".join(
            f"- {LEAVES[i][0]}  [{i}]\n    scope: {LEAVES[i][1]}\n    check: {LEAVES[i][2]}\n" for i in ids
        )
        (trees / "tiny.plan").write_text(text)
        return ["tiny", "--tasks", str(tmp_path / "tasks"), "--trees", str(trees),
                "--out", str(tmp_path / "out"), "--rows", str(tmp_path / "rows.jsonl"),
                "--ledger", str(tmp_path / "ledger.jsonl")]  # fmt: skip

    return tree


@pytest.fixture
def fake(monkeypatch):
    with Fake([model] * 200) as f:
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        yield f
    tf._listed.cache_clear()


def rows_of(path: Path) -> tuple[dict, dict]:
    rows = [json.loads(ln) for ln in path.read_text().splitlines()]
    return {r["leaf"]: r for r in rows if r["kind"] == "leaf"}, next(r for r in rows if r["kind"] == "run")


def test_one_lands_one_lands_after_its_offer_one_is_refused_and_the_rows_and_results_say_so(
    task, fake, tmp_path
):
    args = task("greet", "bye", "cfg")
    code = bench.main([*args, "--config", "scripted", "--executor", f"nemotron --model {NANO}",
                       "--parallel", "2", "--run", "1"])  # fmt: skip
    assert code == 0
    leaves, run = rows_of(tmp_path / "rows.jsonl")

    greet, bye, cfg = leaves["greet"], leaves["bye"], leaves["cfg"]
    assert (greet["outcome"], greet["offer"], greet["attempts"], greet["check_passes_at_base"]) == (
        "landed", None, 1, False)  # fmt: skip
    assert greet["calls"] == 2 and greet["tokens_in"] > 0 and greet["dollars"] > 0
    assert greet["models"] == [NANO]
    assert (bye["outcome"], bye["offer"], bye["offer_paths"], bye["then"]) == (
        "handed back", "w", ["app/words.py"], "landed")  # fmt: skip
    assert bye["why"] == "the word is in app/words.py, outside my scope"
    assert bye["holds"] == 2 and bye["attempts"] == 2 and bye["writes_refused"] == 1
    assert (cfg["outcome"], cfg["offer"], cfg["offer_outside_intent"], cfg["then"]) == (
        "handed back", "refused", ["vendor/lib.py"], None)  # fmt: skip
    assert cfg["check_passes_at_base"] is True and cfg["writes_refused"] == 1 and cfg["holds"] == 1

    counts = ("leaves", "landed", "handed_back", "failed", "landed_after_offer")
    assert [run[k] for k in counts] == [3, 1, 2, 0, 1]
    assert (run["offers_taken"], run["offers_refused"], run["checks_passing_at_base"]) == (1, 1, ["cfg"])
    assert (run["accept"]["passed"], run["accept"]["failed"], run["quality"]) == (2, 0, None)
    assert run["rounds"] == 2 and not run["rounds_cap_hit"] and run["stopped"] is None
    assert run["dollars"] == round(sum(r["dollars"] for r in leaves.values()), 6)
    assert run["cost_per_landed_usd"] == run["dollars"]  # one leaf landed
    assert run["files_outside_intent_final"] == []
    for row in [*leaves.values(), run]:
        assert (row["task"], row["config"], row["run"], row["planner"]) == ("tiny", "scripted", 1, "nemotron")
        assert row["executor"] == f"nemotron --model {NANO}" and row["prompt_version"] == bench.PROMPT_VERSION
        assert row["graphene_sha"] and row["tree"]

    repo = Path(run["repo"])
    assert 'return "hi"' not in (repo / "app/greet.py").read_text() and not (repo / "vendor").exists()
    said = [json.loads(ln) for ln in Path(run["runlog"]).read_text().splitlines()]
    assert [(e["who"], e["type"], e.get("node")) for e in said] == [
        ("person", "accept", None), ("person", "run", None), ("person", "widen", "bye"),
        ("person", "refuse", "cfg"), ("person", "run", None)]  # fmt: skip
    assert said[2]["text"] == "graphene node widen bye" and "--node bye" in said[4]["text"]
    assert json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])["model"] == NANO

    results.main(["--rows", str(tmp_path / "rows.jsonl"), "--out", str(tmp_path / "results.md")])
    md = (tmp_path / "results.md").read_text()
    assert "| tiny | scripted | 1 | 1 of 3 | 2/2 | none | 2 | 1 | 0 | 0 | $" in md
    assert (
        "`bye`: handed back: the word is in app/words.py, outside my scope. "
        "offer taken (app/words.py), then landed"
    ) in md
    assert "`cfg`: handed back: it needs vendor/lib.py. offer refused (vendor/lib.py)" in md
    assert "- tiny · scripted · run 1 · `cfg`" in md.split("Checks that pass at the base commit")[1]


def test_at_the_cap_a_run_stops_its_failed_leaf_says_why_and_at_80_percent_no_new_run_starts(
    task, fake, tmp_path, monkeypatch, capsys
):
    args = task("bye")
    monkeypatch.setenv("GRAPHENE_SPEND_CAP_USD", "0.00001")  # the first call spends more than this
    run = [*args, "--config", "capped", "--executor", f"nemotron --model {NANO}", "--parallel", "2"]
    assert bench.main([*run, "--run", "1"]) == 3
    leaves, row = rows_of(tmp_path / "rows.jsonl")
    bye = leaves["bye"]
    assert bye["outcome"] == "failed" and "spend cap" in bye["why"] and bye["attempts"] == 3
    assert (bye["offer"], bye["then"]) == ("w", "not run again")  # the denied write was still its offer
    assert (row["failed"], row["landed"], row["cost_per_landed_usd"]) == (1, 0, None)
    assert row["stopped"] == "the spend cap"
    assert "stopped: the ledger is at" in capsys.readouterr().out

    rows = (tmp_path / "rows.jsonl").read_text()
    assert bench.main([*run, "--run", "2"]) == 3
    said = capsys.readouterr().out
    assert "no new run" in said and "80% or more" in said
    assert (tmp_path / "rows.jsonl").read_text() == rows and not (tmp_path / "out" / "tiny-capped-2").exists()


def test_a_round_past_its_timeout_is_stopped_and_its_leaf_counted_failed(task, tmp_path):
    args = task("greet")
    code = bench.main([*args, "--config", "sleeper", "--executor", "bash -c 'sleep 60' sleeper",
                       "--parallel", "2", "--timeout", "8"])  # fmt: skip
    assert code == 0
    leaves, run = rows_of(tmp_path / "rows.jsonl")
    greet = leaves["greet"]
    assert greet["outcome"] == "failed" and greet["why"].startswith("timeout")
    assert (greet["dollars"], greet["unpriced_attempts"], greet["prompt_version"]) == (0, 1, None)
    assert (run["failed"], run["accept"]["passed"], run["accept"]["failed"]) == (1, 0, 2)


def test_with_no_token_factory_a_nemotron_run_is_not_started_and_nothing_is_counted(
    task, tmp_path, monkeypatch, capsys
):
    args = task("greet")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    tf._listed.cache_clear()
    assert bench.main([*args, "--config", "x", "--executor", f"nemotron --model {NANO}"]) == 2
    assert "no run: NEBIUS_API_KEY is not set" in capsys.readouterr().out
    assert not (tmp_path / "rows.jsonl").exists() and not (tmp_path / "out").exists()


def test_checks_only_names_a_check_that_passes_before_any_work_and_spends_nothing(task, tmp_path, capsys):
    args = task("greet", "cfg")
    assert bench.main([*args, "--config", "x", "--executor", "nemotron", "--checks-only"]) == 1
    said = capsys.readouterr().out.splitlines()
    assert [ln.split()[0] for ln in said] == ["greet", "cfg"]
    assert "fails at base" in said[0] and "PASSES at the base commit" in said[1]
    assert not (tmp_path / "rows.jsonl").exists() and not (tmp_path / "out").exists()


def test_results_show_every_run_with_its_range_accept_beside_landed_in_the_order_run(tmp_path):
    def run(config, n, landed, accept_passed, dollars):
        return {"kind": "run", "task": "feeds", "config": config, "run": n, "planner": "nemotron",
                "executor": f"nemotron --model {config}", "parallel": 4, "graphene_sha": "abc",
                "prompt_version": 1,
                "tree": "t", "leaves": 4, "landed": landed, "handed_back": 4 - landed, "failed": 0,
                "not_started": 0, "other": 0,
                "landed_after_offer": 0, "checks_passing_at_base": [], "dollars": dollars,
                "cost_per_landed_usd": dollars / landed if landed else None, "rounds": 1,
                "rounds_cap_hit": False,
                "stopped": None, "quality": None,
                "accept": {"passed": accept_passed, "failed": 2 - accept_passed, "details": []}}  # fmt: skip

    rows = [run("super", 1, 1, 2, 0.5), run("nano", 1, 3, 1, 0.3), run("super", 2, 3, 2, 0.6)]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    results.main(["--rows", str(tmp_path / "rows.jsonl"), "--out", str(tmp_path / "r.md")])
    md = (tmp_path / "r.md").read_text()
    assert "| feeds | super | 2 | 1 · 3 of 4 (1–3) | 2/2 · 2/2 | none · none | 3 · 1 (1–3) |" in md
    assert "| feeds | nano | 1 | 3 of 4 | 1/2 | none | 1 |" in md
    night = md.split("## Over the night")[1]
    assert night.index("| 1 | super | feeds | 2 | 4/8 (50%) | 2 of 2 runs | $0.2750 |") < night.index(
        "| 2 | nano | feeds | 1 | 3/4 (75%) | 0 of 1 runs | $0.1000 |")  # fmt: skip
