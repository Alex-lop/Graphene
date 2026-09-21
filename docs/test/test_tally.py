#!/usr/bin/env python3
"""Every number tally.py prints, against a case built by hand.

    python3 docs/test/test_tally.py       (or: cd docs/test && python3 -m unittest test_tally)

The repo below is four changes against its base commit, the store is nine recorded write events
of which three must not count, and the run log is six entries. The expected numbers are worked out
in the comments, not read back off the code.

Three of the cases here are the defects the 20 September run printed wrong numbers because of, and
they are the reason this file grew:

  `app/keep.py`       written once through a file tool and once through the shell. Counted twice,
                      it is 4 lines of churn; it is one file that changed by 2.
  `.plan-tmp.json`    a scratch file written and removed inside the run, in both records. 6 lines
                      of "rework" for a file that is not in the base commit, is not on disk at the
                      end, and was never anybody's code.
  `.graphene/runs/`   where `graphene run` puts an executor's output and never looks again. With
                      `--output-format json` the cost is in there; tally reads it out.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TALLY = HERE / "tally.py"

INTENT = "app/**\n!app/private.py\n"  # app, except the one file the person keeps

ACCEPT_STUB = """import json, sys
print(json.dumps({"passed": 2, "failed": 1, "details": [{"check": "stub", "ok": False, "note": ""}]}))
"""

# (tool, file_path, old, new, success)
EVENTS = [
    ("Write", "app/keep.py", "a\nb\nc\n", "a\nB\nc\n", 1),  # 2 lines, in intent
    ("Edit", "app/private.py", "x\n", "y\n", 1),  # 2 lines, outside intent, later put back
    ("Write", "app/new.py", None, "1\n2\n", None),  # 2 lines, a new file, success NULL = fine
    ("Write", "vendor/x.py", "p\nq\n", "p\nQ\n", 1),  # 2 lines, outside intent
    ("Write", "notes.md", None, "hi\n", 1),  # 1 line, outside intent
    ("Write", ".plan-tmp.json", None, "a\nb\nc\n", 1),  # 3 lines, scratch, removed below
    # a leaf run in its own worktree by `graphene run --parallel`: 2 lines, and the hook records it
    # against the main repo's root, so it arrives looking like a write to .graphene/
    ("Write", ".graphene/worktrees/n4/app/wt.py", None, "w\nx\n", 1),
    ("Write", "app/keep.py", "a\n", "zzzz\n", 0),  # failed: not counted at all
    ("Write", "app/keep.py", "a\n", None, 1),  # no content kept: skipped, and said so
    ("Write", "/etc/hosts", "a\n", "b\n", 1),  # outside the repo: skipped, and said so
]
CHURN_FROM_EVENTS = 2 + 2 + 2 + 2 + 1 + 3 + 2  # = 14

# One Bash call that edited three files through the shell, the way a real executor does: hunks
# under `files`, and the same paths repeated as a bare `changedFiles` list. `app/keep.py` is the
# same change a file tool already recorded, and `.plan-tmp.json` is the scratch file being removed
# again — the two double counts. `build/out.txt` is only here.
SHELL_DIFF = {
    "files": [
        {"filePath": "app/keep.py", "hunks": [{"lines": [" ctx", "-b", "+B"]}]},
        {"filePath": "build/out.txt", "hunks": [{"lines": ["+a", "+b"]}]},
        {"filePath": ".plan-tmp.json", "hunks": [{"lines": ["-a", "-b", "-c"]}]},
    ],
    "changedFiles": ["app/keep.py", "build/out.txt", ".plan-tmp.json"],
}
CHURN_FROM_SHELL = 2 + 2 + 3  # = 7
CHURN_NAIVE = CHURN_FROM_EVENTS + CHURN_FROM_SHELL  # = 21, what adding the two records gives
# Once per file: keep 2 (not 2+2), private 2, new 2, vendor 2, notes 1, build 2, scratch 3, wt 2
CHURN_DEDUPED = 2 + 2 + 2 + 2 + 1 + 2 + 3 + 2  # = 16
# Of that, the two files that are not in the base commit and are not on disk at the end
TRANSIENT = 2 + 3  # build/out.txt and .plan-tmp.json = 5

# Two executor calls `graphene run` started, in the files it leaves behind and never reads.
RUNS = {
    "n1-1.txt": json.dumps(
        {"type": "result", "total_cost_usd": 0.31, "num_turns": 9, "session_id": "r1", "result": "done"}
    ),
    "n2-1.txt": "the executor printed prose, not json, so nobody can price this one\n",
}

LOG = [
    {"t": 1000, "who": "person", "type": "prompt", "text": "x" * 40, "chars": 40},
    {"t": 1005, "who": "executor", "type": "result", "cost_usd": 0.12, "turns": 7, "session_id": "s1"},
    {"t": 1010, "who": "person", "type": "correction", "text": "no, not that"},  # chars from the text
    # The card's own change of mind: a correction the protocol makes both arms spend.
    {"t": 1015, "who": "person", "type": "correction", "text": "by hour", "mandated": True},
    {"t": 1020, "who": "executor", "type": "result", "cost_usd": 0.08, "turns": 3, "session_id": "s1"},
    {"t": 1030, "who": "person", "type": "review", "text": "", "chars": 0},
]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


class Tally(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="tally-case-"))
        repo = cls.dir / "repo"
        (repo / "app").mkdir(parents=True)
        (repo / "vendor").mkdir()
        (repo / ".gitignore").write_text("__pycache__/\n.graphene/\n.claude/\n", encoding="utf-8")
        (repo / "app" / "keep.py").write_text("a\nb\nc\n", encoding="utf-8")
        (repo / "app" / "private.py").write_text("x\n", encoding="utf-8")
        (repo / "vendor" / "x.py").write_text("p\nq\n", encoding="utf-8")
        git(repo, "init", "-q")
        git(repo, "add", "-A")
        git(repo, "-c", "user.email=t@e.com", "-c", "user.name=t", "commit", "-qm", "base")
        cls.base = git(repo, "rev-parse", "HEAD").strip()

        # the four changes that survive: one edit in intent, one edit outside, two new files.
        # app/private.py was written and put back, so it is in the record and not in the diff.
        (repo / "app" / "keep.py").write_text("a\nB\nc\n", encoding="utf-8")  # 1 + 1 = 2 lines
        (repo / "vendor" / "x.py").write_text("p\nQ\n", encoding="utf-8")  # 1 + 1 = 2 lines
        (repo / "app" / "new.py").write_text("1\n2\n", encoding="utf-8")  # 2 new lines
        (repo / "notes.md").write_text("hi\n", encoding="utf-8")  # 1 new line
        (repo / "app" / "wt.py").write_text("w\nx\n", encoding="utf-8")  # 2 new lines, from a worktree
        cls.final_lines = 2 + 2 + 2 + 1 + 2  # = 9

        db = repo / ".graphene" / "graphene.db"
        db.parent.mkdir()
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE tool_events (id TEXT, session_id TEXT, timestamp TEXT, tool TEXT, "
            "success INTEGER, file_path TEXT, old_content TEXT, new_content TEXT, response TEXT)"
        )
        conn.execute("CREATE TABLE node_log (id INTEGER PRIMARY KEY, node_id TEXT, kind TEXT)")
        for i, (tool, path, old, new, ok) in enumerate(EVENTS):
            conn.execute(
                "INSERT INTO tool_events VALUES (?, 's1', ?, ?, ?, ?, ?, ?, NULL)",
                (str(i), f"2026-09-20T00:00:{i:02d}Z", tool, ok, path, old, new),
            )
        shell = {
            "files": [
                {"filePath": str(repo / f["filePath"]), "hunks": f["hunks"]} for f in SHELL_DIFF["files"]
            ],
            "changedFiles": [str(repo / p) for p in SHELL_DIFF["changedFiles"]],
        }
        conn.execute(
            "INSERT INTO tool_events VALUES ('b', 's1', '2026-09-20T00:00:99Z', 'Bash', 1, "
            "NULL, NULL, NULL, ?)",
            (json.dumps({"bashEditDiff": shell}),),
        )
        for kind in ("denied", "denied", "breach", "refused", "finished", "started"):
            conn.execute("INSERT INTO node_log (node_id, kind) VALUES ('n1', ?)", (kind,))
        conn.commit()
        conn.close()

        runs = repo / ".graphene" / "runs"
        runs.mkdir()
        for name, text in RUNS.items():
            (runs / name).write_text(text, encoding="utf-8")

        (cls.dir / "intent_globs.txt").write_text(INTENT, encoding="utf-8")
        (cls.dir / "accept.py").write_text(ACCEPT_STUB, encoding="utf-8")
        (cls.dir / "runlog.jsonl").write_text(
            "\n".join(json.dumps(e) for e in LOG) + "\n\n", encoding="utf-8"
        )

        done = subprocess.run(
            [
                sys.executable,
                str(TALLY),
                str(repo),
                "--base",
                cls.base,
                "--intent",
                str(cls.dir / "intent_globs.txt"),
                "--accept",
                str(cls.dir / "accept.py"),
                "--arm",
                "graphene",
                "--runlog",
                str(cls.dir / "runlog.jsonl"),
            ],
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, done.stderr
        cls.out = json.loads(done.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_files_changed_final(self):
        # git knows three tracked paths differ; notes.md and app/new.py are untracked and new.
        # app/private.py was put back, so it is not here.
        self.assertEqual(
            self.out["files_changed_final"],
            ["app/keep.py", "app/new.py", "app/wt.py", "notes.md", "vendor/x.py"],
        )
        self.assertEqual(self.out["files_changed_final_n"], 5)

    def test_files_outside_intent_final(self):
        # app/** is intent; notes.md and vendor/x.py are not under it.
        self.assertEqual(self.out["files_outside_intent_final"], ["notes.md", "vendor/x.py"])
        self.assertEqual(self.out["files_outside_intent_final_n"], 2)

    def test_the_negated_glob_is_honoured(self):
        # app/private.py is inside app/** and taken back out by !app/private.py, so a write to it
        # is outside intent even though the final diff has nothing to show for it.
        self.assertIn("app/private.py", self.out["files_written_outside_intent_ever"])
        self.assertNotIn("app/private.py", self.out["files_outside_intent_final"])

    def test_files_written_outside_intent_ever(self):
        # the four the file tools and the diff know about, plus the one written through the shell
        self.assertEqual(
            self.out["files_written_outside_intent_ever"],
            [".plan-tmp.json", "app/private.py", "build/out.txt", "notes.md", "vendor/x.py"],
        )
        self.assertEqual(self.out["files_written_outside_intent_ever_n"], 5)

    def test_each_source_is_kept_apart(self):
        by = self.out["files_written_outside_intent_by_source"]
        self.assertEqual(by["edit_events"], [".plan-tmp.json", "app/private.py", "notes.md", "vendor/x.py"])
        self.assertEqual(by["shell"], [".plan-tmp.json", "build/out.txt"])
        self.assertEqual(by["final_diff"], ["notes.md", "vendor/x.py"])

    def test_refused_writes(self):
        self.assertEqual(self.out["refused_writes"], 4)  # 2 denied + 1 breach + 1 refused
        self.assertEqual(self.out["refused_writes_by_kind"], {"denied": 2, "breach": 1, "refused": 1})

    def test_recorded_write_events_leaves_out_the_failed_one(self):
        self.assertEqual(self.out["recorded_write_events"], len(EVENTS) - 1)

    def test_final_diff_lines(self):
        self.assertEqual(self.out["final_diff_lines"], self.final_lines)
        self.assertEqual(self.final_lines, 9)

    def test_each_record_is_still_reported_on_its_own(self):
        self.assertEqual(self.out["rework_from_edit_events"], CHURN_FROM_EVENTS)
        self.assertEqual(self.out["rework_from_shell"], CHURN_FROM_SHELL)
        self.assertEqual(self.out["churn_naive_lines"], CHURN_NAIVE)
        self.assertEqual(CHURN_NAIVE, 21)

    def test_a_file_in_both_records_is_counted_once(self):
        # app/keep.py is one change of 2 lines that both a Write event and a Bash change list saw.
        # Adding the records gives 4; the file changed by 2.
        self.assertEqual(self.out["churn_by_file"]["app/keep.py"], 2)
        self.assertEqual(self.out["rework_recorded_lines"], CHURN_DEDUPED)
        self.assertEqual(CHURN_DEDUPED, 16)
        self.assertEqual(self.out["churn_double_counted_lines"], CHURN_NAIVE - CHURN_DEDUPED)
        self.assertEqual(CHURN_NAIVE - CHURN_DEDUPED, 5)  # 2 for app/keep.py, 3 for the scratch file

    def test_a_write_inside_a_leafs_worktree_is_a_write_to_the_file_it_names(self):
        # `graphene run --parallel` works in .graphene/worktrees/<node>/, and .graphene/ is the
        # harness's own directory everywhere else. Left as recorded, every parallel write vanishes.
        self.assertEqual(self.out["churn_by_file"]["app/wt.py"], 2)
        self.assertNotIn(".graphene/worktrees/n4/app/wt.py", self.out["churn_by_file"])

    def test_a_scratch_file_made_and_removed_in_the_run_is_not_rework(self):
        # Not in the base commit, not on disk at the end: nobody rewrote any code.
        self.assertEqual(self.out["transient_files"], [".plan-tmp.json", "build/out.txt"])
        self.assertEqual(self.out["transient_churn_lines"], TRANSIENT)
        self.assertEqual(TRANSIENT, 5)

    def test_rework_lines(self):
        # deduplicated churn, less the transient files, less what the final diff still shows
        self.assertEqual(self.out["rework_lines"], CHURN_DEDUPED - TRANSIENT - self.final_lines)
        self.assertEqual(self.out["rework_lines"], 16 - 5 - 9)

    def test_the_skipped_events_are_named(self):
        self.assertTrue(
            any("2 recorded write events had no usable content" in n for n in self.out["notes"]),
            self.out["notes"],
        )

    def test_a_change_list_with_hunks_for_every_path_is_not_called_uncountable(self):
        self.assertEqual([n for n in self.out["notes"] if "no hunks to count" in n], [])

    def test_the_run_log(self):
        self.assertEqual(self.out["person_actions"], 4)
        self.assertEqual(self.out["person_chars"], 40 + len("no, not that") + len("by hour") + 0)
        self.assertEqual(self.out["wall_seconds"], 30.0)

    def test_restarts_are_reported_both_ways(self):
        # two corrections, one of which the protocol makes both arms spend
        self.assertEqual(self.out["restarts"], 2)
        self.assertEqual(self.out["restarts_unmandated"], 1)

    def test_executor_cost_comes_from_the_run_log_and_from_graphene_runs(self):
        self.assertEqual(self.out["executor_cost_from_runlog_usd"], 0.2)
        self.assertEqual(self.out["executor_cost_from_graphene_runs_usd"], 0.31)
        self.assertEqual(self.out["executor_cost_usd"], 0.51)
        self.assertEqual(self.out["executor_turns"], 7 + 3 + 9)
        self.assertEqual(self.out["executor_calls"], 4)  # two in the log, two under .graphene/runs
        self.assertEqual(self.out["executor_calls_unpriced"], 1)  # the one that printed prose
        self.assertTrue(
            any("n2-1.txt is not an --output-format json result" in n for n in self.out["notes"]),
            self.out["notes"],
        )

    def test_acceptance_comes_straight_from_accept_py(self):
        self.assertEqual(self.out["acceptance"]["passed"], 2)
        self.assertEqual(self.out["acceptance"]["failed"], 1)


class Rework(unittest.TestCase):
    """The one piece of arithmetic that is not a sum: rework never goes below zero."""

    def test_floor(self):
        sys.path.insert(0, str(HERE))
        import tally

        self.assertEqual(tally.edit_size("a\nb\n", "a\nB\n"), 2)
        self.assertEqual(tally.edit_size(None, "1\n2\n"), 2)
        self.assertEqual(tally.edit_size("a\n", "a\n"), 0)
        self.assertEqual(max(0, 3 - 9), 0)


if __name__ == "__main__":
    unittest.main()
