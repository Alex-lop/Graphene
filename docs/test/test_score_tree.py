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
