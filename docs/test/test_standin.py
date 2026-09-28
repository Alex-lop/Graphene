#!/usr/bin/env python3
"""The briefs standin.py prints: the arms differ only in their arm section, the board arm logs every
act as a type logline.py takes, and the sealed style sends the written paragraph. A fake card is
used, so no test pastes a real one.

python3 docs/test/test_standin.py
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from logline import TYPES  # noqa: E402
from standin import ARMS, brief  # noqa: E402


class Briefs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="standin-case-"))
        (cls.dir / "run").mkdir()
        (cls.dir / "run" / "base.sha").write_text("abc123\n")
        for task in ("withchange", "nochange"):
            (cls.dir / "tasks" / task).mkdir(parents=True)
            (cls.dir / "tasks" / task / "intent.md").write_text("A FAKE CARD\n")
            (cls.dir / "tasks" / task / "paragraph.md").write_text("a fake paragraph\n")
        (cls.dir / "tasks" / "withchange" / "change.md").write_text("a fake change\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make(self, arm: str, task: str = "withchange", style: str = "sealed") -> str:
        return brief(task, style, arm, self.dir / "run", "/venv/bin", tasks=self.dir / "tasks")

    def test_the_arms_differ_only_in_the_arm_section(self):
        outside = set()
        for arm in ARMS:
            head, rest = self.make(arm).split("WHAT YOU DO", 1)
            outside.add(head + rest.split("LOGGING —", 1)[1])
        self.assertEqual(len(outside), 1)

    def test_every_logged_act_is_a_type_logline_takes(self):
        for arm, text in ARMS.items():
            # `did <type> "…"`, `-> log as `<type>``, and a line that starts `log <type> …`
            kinds = re.findall(r'\bdid (\w+) "', text) + re.findall(r"log as `(\w+)`", text)
            kinds += re.findall(r"^\s+log (\w+) ", text, re.M)
            self.assertTrue(kinds, arm)
            for kind in kinds:
                self.assertIn(kind, TYPES, f"{arm}: `{kind}`")

    def test_only_the_board_arm_answers_a_board(self):
        board = ARMS["board"]
        for command in ("take <id>", "pick <id> <n>", "drop <id>", "park <id>", "answer <id>", "note '"):
            self.assertIn(f'did board "as_me graphene board {command}', board)
        self.assertIn("graphene plan --view auto", board)
        for arm in ("prompt", "tree"):
            self.assertNotIn("graphene board", ARMS[arm])

    def test_the_sealed_style_sends_the_written_paragraph_and_change(self):
        text = self.make("board")
        tasks = self.dir / "tasks" / "withchange"
        self.assertIn(f"MSG=$(cat {tasks / 'paragraph.md'})", text)
        self.assertIn(f"MSG=$(cat {tasks / 'change.md'})", text)
        self.assertIn("not written down", self.make("board", task="nochange"))
        self.assertTrue(text.rstrip().endswith("A FAKE CARD"))

    def test_the_sealed_style_needs_a_paragraph(self):
        (self.dir / "tasks" / "bare").mkdir()
        (self.dir / "tasks" / "bare" / "intent.md").write_text("A FAKE CARD\n")
        with self.assertRaises(FileNotFoundError):
            self.make("board", task="bare")
        self.assertIn("A FAKE CARD", self.make("tree", task="bare", style="dense"))


if __name__ == "__main__":
    unittest.main()
