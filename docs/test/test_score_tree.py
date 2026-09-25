"""score_tree.py on a tiny task of its own (never the four real ones), with a tree that fails each score once.

The tiny task: intent `app/**` but not app/c.py, `docs/**` (nothing there yet) and README.md.
  a  app/a.py and docs/**; its check fails at base and passes after          -> good
  b  app/b.py, app/c.py and vendor/**; its check passes at base               -> overreach, not a check
  c  app/a.py and app/new.py; its check fails at base and after               -> shares app/a.py with a
and no leaf reaches README.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_task  # noqa: E402
import score_tree  # noqa: E402

from graphene_map.store import Store  # noqa: E402

FILES = {
    ".gitignore": ".graphene/\n",
    "README.md": "# tiny\n",
    "app/a.py": 'SAY = "hi"\n',
    "app/b.py": "",
    "app/c.py": "",
    "vendor/lib.py": "",
}
TREE = """goal: a friendlier tiny app

- friendlier  [top]
  - greet  [a]
      scope: app/a.py, docs/**
      check: grep -q hello app/a.py
  - the vendored lib  [b]
      scope: app/b.py, app/c.py, vendor/**
      check: test -f app/b.py
- a new module  [c]
    scope: app/a.py, app/new.py
    check: test -f app/new.py
"""


def test_each_score_names_what_fails_it_and_the_row_carries_the_tree_the_planner_and_the_counts(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setitem(make_task.TASKS, "tiny", FILES)
    build = lambda d: make_task.build("tiny", d)  # noqa: E731
    card = tmp_path / "tasks" / "tiny"
    card.mkdir(parents=True)
    (card / "intent_globs.txt").write_text("# the person's intent\napp/**\n!app/c.py\ndocs/**\nREADME.md\n")
    plan = tmp_path / "tiny.plan"
    plan.write_text(TREE)
    after = tmp_path / "after"
    build(after)
    (after / "app/a.py").write_text('SAY = "hello"\n')  # a's work, as a finished run leaves it
    with Store.open(after) as store:
        store.log_node("*", "2026-09-25T00:00:00Z", "usage", "planner:nemotron", None, None,
                       {"model": "nvidia/ultra-fake", "prompt": 1})  # fmt: skip
        store.log_node("*", "2026-09-25T00:00:01Z", "usage", "executor", None, None, {"model": "nano"})
    scores = tmp_path / "scores.jsonl"

    argv = ["tiny", "--plan", str(plan), "--tasks", str(tmp_path / "tasks"), "--scores", str(scores)]
    assert score_tree.main([*argv, "--after", str(after), "--store", str(after)], build=build) == 0

    row = json.loads(scores.read_text())
    assert row["unreached"] == ["README.md"]  # docs/** names nothing yet, and a's docs/** may meet it
    assert row["overreach"] == {"b": ["app/c.py", "vendor/lib.py"]}
    assert row["names_nothing"] == {"a": ["docs/**"], "c": ["app/new.py"]}
    assert row["overlaps"] == [["a", "c", ["app/a.py"]]]
    assert row["pass_at_base"] == ["b"]
    assert row["fail_after"] == ["c"]  # so a's check fails at base and passes after: the one real check
    assert row["counts"] == {"unreached": 1, "overreaching_leaves": 1, "overlapping_pairs": 1,
                             "checks_passing_at_base": 1, "checks_failing_after": 1}  # fmt: skip
    assert row["leaves"] == 3 and row["task"] == "tiny"  # top is a sub-goal, not a leaf
    assert row["tree"] == score_tree.hashlib.sha256(TREE.encode()).hexdigest()[:12]
    assert row["planner"] == {"prompt": [1], "model": ["nvidia/ultra-fake"]}
    said = capsys.readouterr().out
    assert "intent globs no scope reaches (1): README.md" in said
    assert "a & c: app/a.py" in said and "checks failing after" in said

    # without a finished run, nothing is said of after; the planner is as given; a second row is appended
    assert score_tree.main([*argv, "--planner-prompt", "2"], build=build) == 0
    second = json.loads(scores.read_text().splitlines()[1])
    assert second["fail_after"] is None and second["counts"]["checks_failing_after"] is None
    assert second["planner"] == {"prompt": [2], "model": []}
    assert "checks failing after" not in capsys.readouterr().out


def one_leaf(tmp_path, monkeypatch, files: dict, intent: list[str], scope: str, check: str = "",
             after: bool = False) -> dict:  # fmt: skip
    """score() on a repo of `files` and a tree of one leaf `x`; `after` scores the untouched repo as done."""
    monkeypatch.setitem(make_task.TASKS, "tiny", {".gitignore": ".graphene/\n", **files})
    build = lambda d: make_task.build("tiny", d)  # noqa: E731
    done = None
    if after:
        build(done := tmp_path / "after")
    text = f"goal: g\n\n- x  [x]\n    scope: {scope}\n" + (f"    check: {check}\n" if check else "")
    return score_tree.score(text, intent, build, done)


A = {"app/a.py": "", "app/b.py": ""}


def test_a_scope_reaches_an_intent_glob_by_a_new_path_whatever_else_is_there(tmp_path, monkeypatch):
    for files, intent, scope in [
        (A, ["docs/**"], "docs/new/**"),
        ({**A, "docs/old.md": ""}, ["docs/**"], "docs/new/**"),  # the same, with a file under docs/
        ({**A, "tests/test_a.py": ""}, ["tests/**", "app/**"], "app/a.py, tests/test_json_*.py"),
        ({**A, "docs/old.txt": ""}, ["docs/**"], "**/*.md"),  # docs/new.md, whose name neither spells
        (A, ["docs/**"], "docs"),  # src/api, src/api/ and src/api/** mean the same (plan._pattern)
        (A, ["docs/**"], "docs/"),
        (A, ["docs"], "docs/**"),
    ]:
        got = one_leaf(tmp_path, monkeypatch, files, intent, scope)
        assert got["unreached"] == [], (intent, scope)
        assert got["overreach"] == ({"x": ["**/*.md"]} if scope == "**/*.md" else {}), (intent, scope)
    # a path the intent takes back out reaches nothing, and is a path past the intent
    got = one_leaf(tmp_path, monkeypatch, {"ingest/csvfeed.py": ""}, ["ingest/**", "!ingest/csvfeed.py"],
                   "ingest/csvfeed.py")  # fmt: skip
    assert got["unreached"] == ["ingest/**"] and got["overreach"] == {"x": ["ingest/csvfeed.py"]}


def test_a_scope_glob_that_names_nothing_outside_the_intent_is_overreach(tmp_path, monkeypatch):
    got = one_leaf(tmp_path, monkeypatch, A, ["app/**"], "app/a.py, newpkg/**, app/new.py")
    assert got["overreach"] == {"x": ["newpkg/**"]} and got["counts"]["overreaching_leaves"] == 1
    assert got["names_nothing"] == {"x": ["newpkg/**", "app/new.py"]}


def test_a_leaf_with_no_check_passes_at_base_and_after_as_bench_counts_it(tmp_path, monkeypatch):
    got = one_leaf(tmp_path, monkeypatch, A, ["app/**"], "app/a.py", after=True)
    assert got["pass_at_base"] == ["x"] and got["fail_after"] == []


def test_after_that_is_not_a_repos_top_is_refused_and_no_row_is_written(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(make_task.TASKS, "tiny", {".gitignore": ".graphene/\n", **A})
    (tmp_path / "tasks" / "tiny").mkdir(parents=True)
    (tmp_path / "tasks" / "tiny" / "intent_globs.txt").write_text("app/**\n")
    (plan := tmp_path / "tiny.plan").write_text("goal: g\n\n- x  [x]\n    scope: app/a.py\n    check: true\n")
    make_task.build("tiny", repo := tmp_path / "repo")
    (rundir := tmp_path / "rundir").mkdir()
    scores = tmp_path / "scores.jsonl"
    argv = ["tiny", "--plan", str(plan), "--tasks", str(tmp_path / "tasks"), "--scores", str(scores)]
    for bad in (tmp_path / "no-such-repo", rundir, repo / "app"):
        assert score_tree.main([*argv, "--after", str(bad)], build=lambda d: make_task.build("tiny", d)) == 2
        assert str(bad) in capsys.readouterr().out and not scores.exists()
