#!/usr/bin/env python3
"""Every number attention.py prints, against a run built by hand; the sums are in the comments.

python3 docs/test/test_attention.py
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
ME = "alexlopez (no terminal)"

TREE_LOG = [
    {"who": "person", "type": "prompt", "text": "x" * 300},  # 300 typed, act 1
    {
        "who": "executor",
        "type": "result",
        "text": "proposed four leaves",
        "cost_usd": 0.4,
    },  # not the person's
    {"who": "person", "type": "read", "text": "one two three four five"},  # 5 words, no act
    {
        "who": "person",
        "type": "edit",  # 15 + 9 + 8 = 32 typed; `n2` is chosen, not typed. act 2
        "text": "as_me graphene node set n2 --goal 'prices in cents' --scope 'ingest/**' --scope 'tests/**'",
    },
    {"who": "person", "type": "drop", "text": "as_me graphene node drop n3"},  # 0, act 3
    {"who": "person", "type": "edit", "typed": 12, "text": "--- before\n+++ after"},  # 12, act 4
    {"who": "person", "type": "accept", "text": "as_me graphene plan accept n1"},  # 0, act 5
    {
        "who": "person",
        "type": "run",
        "text": 'as_me graphene run --parallel 4 --with "claude -p"',
    },  # 0, act 6
    {"who": "person", "type": "read", "text": " ".join(["w"] * 20)},  # 20 words
    {"who": "person", "type": "widen", "text": "as_me graphene node widen n4 README.md"},  # 9, act 7
    {
        "who": "person",
        "type": "reopen",
        "text": 'as_me graphene node reopen n4 --note="not a product"',
    },  # 13, act 8
    {"who": "person", "type": "correction", "text": "no, auto-detect", "mandated": True},  # 15, act 9
    {"who": "person", "type": "review", "text": "git diff"},  # 0, act 10
]
# typed 300 + 32 + 0 + 12 + 0 + 0 + 9 + 13 + 15 + 0 = 381; acts 10; words 5 + 20 = 25
# seconds 0.28 * 381 + 1.35 * 10 + 25 * 60 / 250 = 106.68 + 13.5 + 6.0 = 126.18
# to the first run: typed 344, acts 6, words 5: 96.32 + 8.1 + 1.2 = 105.62

# (node, kind, actor, detail)
LOG = [
    ("n1", "proposed", "claude:abcd1234", None),
    ("n2", "proposed", "claude:abcd1234", None),
    ("n3", "proposed", "claude:abcd1234", None),
    ("n4", "proposed", "claude:abcd1234", None),
    ("n2", "edited", ME, {"changed": {"goal": ["prices", "prices in cents"]}, "rev": 2}),  # caught
    ("n3", "dropped", ME, None),  # caught
    ("n1", "accepted", ME, None),  # an accept is not a catch
    ("n5", "added", ME, None),  # the person's own node, not a proposal
    ("n5", "edited", ME, {"changed": {"goal": ["a", "b"]}}),  # so its edit is not a catch
    ("n4", "dropped", "claude:abcd1234", None),  # an agent withdrawing its own proposal
    ("n3", "undone", ME, None),  # the person took the drop back: listed under n3
    ("n2", "started", "run:n2", None),  # the first run: nothing after this is caught before code
    ("n4", "edited", ME, {"changed": {"scope": [["a/**"], ["a/**", "README.md"]]}}),
    ("n2", "edited", ME, {"changed": {"check": ["pytest", "pytest -q"]}}),  # rolled back for as_proposed
]
NODES = {
    "n2": {"title": "prices", "goal": "prices in cents", "scope": ["ingest/**"], "check": "pytest -q",
           "needs": [], "parent": "n1"},
    "n3": {"title": "fix nightly", "goal": "", "scope": ["scripts/**"], "check": None, "needs": [],
           "parent": "n1"},
}  # fmt: skip


def make_run(root: Path, name: str, log: list[dict], with_db: bool) -> Path:
    run = root / name
    (run / "repo" / ".graphene").mkdir(parents=True)
    (run / "runlog.jsonl").write_text("\n".join(json.dumps(e) for e in log) + "\n", encoding="utf-8")
    if with_db:
        conn = sqlite3.connect(run / "repo" / ".graphene" / "graphene.db")
        conn.execute(
            "CREATE TABLE node_log (id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT, timestamp TEXT, "
            "kind TEXT, actor TEXT, session_id TEXT, agent_id TEXT, detail TEXT)"
        )
        conn.execute(
            "CREATE TABLE nodes (id TEXT PRIMARY KEY, seq INTEGER, state TEXT, session_id TEXT, data TEXT)"
        )
        for node, kind, actor, detail in LOG:
            conn.execute(
                "INSERT INTO node_log (node_id, timestamp, kind, actor, detail) VALUES (?, '', ?, ?, ?)",
                (node, kind, actor, json.dumps(detail) if detail else None),
            )
        for i, (node, data) in enumerate(NODES.items()):
            conn.execute("INSERT INTO nodes VALUES (?, ?, 'open', NULL, ?)", (node, i, json.dumps(data)))
        conn.commit()
        conn.close()
    return run


def attention(run: Path) -> dict:
    done = subprocess.run(
        [sys.executable, str(HERE / "attention.py"), str(run)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


class Attention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="attention-case-"))
        cls.tree = attention(make_run(cls.dir, "feeds-dense-tree-1", TREE_LOG, True))
        prompt_log = [
            {"who": "person", "type": "prompt", "text": "hello world"},  # 11, act 1
            {"who": "person", "type": "read", "text": " ".join(["w"] * 50)},  # 50 words
            {"who": "person", "type": "correction", "text": "no", "mandated": True},  # 2, act 2
        ]
        cls.prompt = attention(make_run(cls.dir, "feeds-tuesday-prompt-1", prompt_log, False))
        # a tree-arm run whose session did the work instead of proposing: no `run`, so its first
        # prompt is what set the work going
        cls.no_tree = attention(make_run(cls.dir, "feeds-tuesday-tree-2", prompt_log, False))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_raw_counts(self):
        self.assertEqual(self.tree["typed_chars"], 381)
        self.assertEqual(self.tree["acts"], 10)
        self.assertEqual(self.tree["read_words"], 25)

    def test_modelled_seconds(self):
        self.assertEqual(self.tree["modelled_seconds"], 126.2)  # 126.18

    def test_to_the_first_run(self):
        self.assertEqual(
            self.tree["to_run"],
            {"typed_chars": 344, "acts": 6, "read_words": 5, "modelled_seconds": 105.6},  # 105.62
        )

    def test_caught_before_code(self):
        caught = self.tree["caught_before_code"]
        self.assertEqual([c["node"] for c in caught], ["n2", "n3"])
        self.assertEqual(self.tree["caught_before_code_n"], 2)
        n2, n3 = caught
        self.assertEqual(n2["acts"], [{"kind": "edited", "changed": {"goal": ["prices", "prices in cents"]}}])
        # both of n2's edits rolled back, the one after the run too: this is what the agent proposed
        self.assertEqual(n2["as_proposed"]["goal"], "prices")
        self.assertEqual(n2["as_proposed"]["check"], "pytest")
        self.assertEqual(n3["acts"], [{"kind": "dropped"}, {"kind": "undone"}])
        self.assertEqual(n3["as_proposed"]["title"], "fix nightly")

    def test_the_prompt_arm_is_cut_at_its_first_message(self):
        self.assertEqual(self.prompt["typed_chars"], 13)
        self.assertEqual(self.prompt["read_words"], 50)
        self.assertEqual(self.prompt["modelled_seconds"], 18.3)  # 3.64 + 2.7 + 12.0 = 18.34
        self.assertEqual(self.prompt["to_run"]["modelled_seconds"], 4.4)  # 3.08 + 1.35 = 4.43
        self.assertEqual(self.prompt["caught_before_code"], [])

    def test_a_tree_run_with_no_run_is_cut_at_its_first_message(self):
        self.assertEqual(self.no_tree["to_run"]["modelled_seconds"], 4.4)
        self.assertEqual(self.no_tree["modelled_seconds"], 18.3)
        self.assertTrue(any("no `run`" in n for n in self.no_tree["notes"]), self.no_tree["notes"])


BOARD_LOG = [
    {"who": "person", "type": "prompt", "text": "p" * 1000},  # 1000 typed, act 1
    {"who": "executor", "type": "result", "text": "a board", "cost_usd": 0.3},  # not the person's
    {"who": "person", "type": "read", "text": "one two three four five"},  # 5 words
    {"who": "person", "type": "board", "text": "as_me graphene board take q1"},  # 0: a key, act 2
    {"who": "person", "type": "board", "text": "as_me graphene board pick q2 2"},  # 0: 2 is chosen, act 3
    # "by hour, not by level" is 21 typed; q3 is chosen, not typed. act 4
    {"who": "person", "type": "board", "text": "as_me graphene board answer q3 by hour, not by level"},
    {"who": "person", "type": "board", "text": "as_me graphene board note 'keep the README'"},  # 15, act 5
    {"who": "person", "type": "board", "text": "as_me graphene board drop r1"},  # 0, act 6
    {"who": "person", "type": "board", "text": "as_me graphene board park o1"},  # 0, act 7
    {"who": "person", "type": "read", "text": " ".join(["w"] * 30)},  # 30 words
    {"who": "person", "type": "accept", "text": "as_me graphene plan accept n1"},  # 0, act 8
    {"who": "person", "type": "run", "text": "as_me graphene run --parallel 4 --with claude"},  # 0, act 9
    {"who": "person", "type": "read", "text": " ".join(["w"] * 10)},  # 10 words
    # a board command this script does not know is counted whole after `board`: "merge q1 q2", 11. act 10
    {"who": "person", "type": "board", "text": "as_me graphene board merge q1 q2"},
    {"who": "person", "type": "review", "text": "git diff"},  # 0, act 11
]  # fmt: skip
# typed 1000 + 21 + 15 + 11 = 1047; acts 11; words 5 + 30 + 10 = 45
# seconds 0.28 * 1047 + 1.35 * 11 + 45 * 60 / 250 = 293.16 + 14.85 + 10.8 = 318.81
# to the first run: typed 1036, acts 9, words 35: 290.08 + 12.15 + 8.4 = 310.63


class BoardArm(unittest.TestCase):
    """The board arm: each board command is an act, and only the words a person types are typed."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="attention-board-"))
        cls.board = attention(make_run(cls.dir, "feeds-sealed-board-1", BOARD_LOG, False))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_raw_counts(self):
        self.assertEqual(self.board["arm"], "board")
        self.assertEqual(self.board["typed_chars"], 1047)
        self.assertEqual(self.board["acts"], 11)
        self.assertEqual(self.board["read_words"], 45)

    def test_modelled_seconds(self):
        self.assertEqual(self.board["modelled_seconds"], 318.8)  # 318.81

    def test_to_the_first_run(self):
        self.assertEqual(
            self.board["to_run"],
            {"typed_chars": 1036, "acts": 9, "read_words": 35, "modelled_seconds": 310.6},  # 310.63
        )

    def test_board_acts_are_counted_by_command(self):
        self.assertEqual(
            self.board["board_acts"],
            {"take": 1, "pick": 1, "answer": 1, "note": 1, "drop": 1, "park": 1, "merge": 1},
        )
        self.assertTrue(any("`merge`" in n for n in self.board["notes"]), self.board["notes"])

    def test_logline_takes_a_board_act(self):
        log = self.dir / "log.jsonl"
        log.write_text("", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(HERE / "logline.py"), str(log), "person", "board",
             "as_me graphene board take q1"],
            check=True, capture_output=True,
        )  # fmt: skip
        self.assertEqual(json.loads(log.read_text())["type"], "board")

    def test_summarize_reads_a_board_run(self):
        sys.path.insert(0, str(HERE))
        from summarize import name_of

        self.assertEqual(name_of(Path("feeds-sealed-board-1")), ("feeds", "sealed", "board", 1))

    def test_the_opening_is_checked_against_the_sealed_paragraph(self):
        sys.path.insert(0, str(HERE))
        from summarize import opening_is_sealed

        sealed = self.dir / "paragraph.md"
        sealed.write_text("the feed, as written\n", encoding="utf-8")
        log = [{"who": "executor", "type": "result", "text": "x"}, {"who": "person", "type": "prompt"}]
        log[1]["text"] = "the feed, as written"  # `MSG=$(cat …)` drops the final newline
        self.assertIs(opening_is_sealed(log, sealed), True)
        log[1]["text"] = "the feed, as rewritten"
        self.assertIs(opening_is_sealed(log, sealed), False)
        self.assertIs(opening_is_sealed([], sealed), False)
        self.assertIsNone(opening_is_sealed(log, self.dir / "none.md"))


class TextEdit(unittest.TestCase):
    def test_a_text_edit_counts_what_was_added(self):
        d = Path(tempfile.mkdtemp(prefix="logline-edit-"))
        try:
            (d / "a.txt").write_text("abc\ndef\n", encoding="utf-8")
            (d / "b.txt").write_text("abXc\n", encoding="utf-8")  # X added, "def\n" deleted
            (d / "log.jsonl").write_text("", encoding="utf-8")
            subprocess.run(
                [sys.executable, str(HERE / "logline.py"), str(d / "log.jsonl"), "person", "edit", "--edit",
                 str(d / "a.txt"), str(d / "b.txt")],
                check=True, capture_output=True,
            )  # fmt: skip
            entry = json.loads((d / "log.jsonl").read_text())
            self.assertEqual((entry["typed"], entry["deleted"], entry["chars"]), (1, 4, 1))
            self.assertIn("-def", entry["text"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
