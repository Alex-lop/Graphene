#!/usr/bin/env python3
"""The briefs standin.py prints: the arms differ only in their arm section (arm A, `nano`, in its
executor section too), the board arm logs every act as a type logline.py takes, arm A goes through
arm_a.py on the run's budget, and the sealed style sends the written paragraph. A fake card is
used, so no test pastes a real one.

python3 dev/test/test_standin.py
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
from standin import ARMS, EXECUTORS, brief  # noqa: E402


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
        budget = (60, 1800.0) if arm == "nano" else None
        return brief(task, style, arm, self.dir / "run", "/venv/bin", tasks=self.dir / "tasks", budget=budget)

    @staticmethod
    def sections(text: str) -> tuple[str, str, str]:
        """(everything else, the arm section, the executor section)."""
        head, rest = text.split("WHAT YOU DO", 1)
        arm, rest = rest.split("LOGGING —", 1)
        between, rest = rest.split("THE EXECUTOR —", 1)
        executor, rest = rest.split("  Three pieces of grit", 1)
        return head + between + rest, arm, executor

    def test_the_arms_differ_only_in_the_arm_section_and_arm_a_in_its_executor(self):
        made = {arm: self.sections(self.make(arm)) for arm in ARMS}
        self.assertEqual(len({rest for rest, _, _ in made.values()}), 1)
        self.assertEqual(len({ex for arm, (_, _, ex) in made.items() if arm != "nano"}), 1)
        self.assertNotEqual(made["nano"][2], made["prompt"][2])

    def test_arm_a_sends_its_messages_through_arm_a_to_one_session_on_the_run_s_budget(self):
        _, arm, executor = self.sections(self.make("nano"))
        run = self.dir / "run"
        self.assertIn(f'"/venv/bin/python" {HERE / "arm_a.py"} {run / "repo"}', executor)
        self.assertIn('--paragraph-file "$TMPDIR/m1.txt" --steps 60 --seconds 1800', executor)
        self.assertIn(f"--conversation {run / 'arm-a.json'} ", executor)
        self.assertIn('--follow-up-file\n  "$TMPDIR/m2.txt"', executor)
        self.assertIn(f'logline.py "$R" executor result --from-json {run / "arm-a.json"}', executor)
        self.assertIn(f"reply {run / 'arm-a.json'}", executor)
        for claude in ("claude", "--resume", "graphene"):  # no Claude Code, no session flag, no plan
            self.assertNotIn(claude, ARMS["nano"] + EXECUTORS["nano"])
        with self.assertRaises(ValueError):  # its budget is the frozen decision's, never a default
            brief("withchange", "sealed", "nano", run, "/venv/bin", tasks=self.dir / "tasks")
        with self.assertRaises(ValueError):
            brief("withchange", "sealed", "prompt", run, "/venv/bin", tasks=self.dir / "tasks", budget=(1, 1))

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
        for arm in ("prompt", "tree", "nano"):
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
