#!/usr/bin/env python3
"""shape_only.py: the two briefs differ only in their arm section, every act is a type logline.py
takes, nothing in an arm runs the plan, and a fork is a copy with newrun.sh's env.sh pointed at
itself. A fake card and a fake paragraph are used, so no test pastes a real one.

python3 docs/test/test_shape_only.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from logline import TYPES  # noqa: E402
from shape_only import ARMS, brief, fork  # noqa: E402


class ShapeOnly(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="shape-only-case-"))
        (self.dir / "tasks" / "fake").mkdir(parents=True)
        (self.dir / "tasks" / "fake" / "intent.md").write_text("A FAKE CARD\n")
        (self.dir / "tasks" / "fake" / "paragraph.md").write_text("a fake paragraph\n")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def make(self, arm: str, task: str = "fake") -> str:
        return brief(task, arm, runs=self.dir / "runs", tasks=self.dir / "tasks")

    def test_the_arms_differ_only_in_the_arm_section_and_the_run_dir(self):
        outside = set()
        for arm in ARMS:
            head, rest = self.make(arm).split("WHAT YOU DO", 1)
            outside.add((head + rest.split("LOGGING —", 1)[1]).replace(f"-shape-{arm}-1", "-shape-ARM-1"))
        self.assertEqual(len(outside), 1)

    def test_the_brief_ends_with_the_paragraph_then_the_card(self):
        text = self.make("board")
        self.assertTrue(text.rstrip().endswith("A FAKE CARD"))
        self.assertLess(text.index("a fake paragraph"), text.index("A FAKE CARD"))
        self.assertIn("do not run anything", text)

    def test_a_task_without_a_paragraph_has_no_brief(self):
        (self.dir / "tasks" / "fake" / "paragraph.md").unlink()
        with self.assertRaises(FileNotFoundError):
            self.make("outline")

    def test_every_act_is_a_type_logline_takes_and_nothing_runs(self):
        for arm, text in ARMS.items():
            kinds = re.findall(r'\bdid (\w+) "', text)
            self.assertTrue(kinds, arm)
            for kind in kinds:
                self.assertIn(kind, TYPES, f"{arm}: `{kind}`")
            self.assertNotIn("graphene run", text)
        self.assertNotIn("graphene board", ARMS["outline"])
        self.assertIn("graphene plan --view auto", ARMS["board"])

    def test_a_fork_is_a_copy_with_its_own_log_and_env(self):
        runs = self.dir / "runs"
        planned = runs / "fake-shape-planned"
        (planned / "repo" / ".graphene").mkdir(parents=True)
        (planned / "repo" / ".graphene" / "proposal").write_text("the one proposal\n")
        (planned / "tmp").mkdir()
        (planned / "tmp" / "left-over").write_text("x")
        (planned / "base.sha").write_text("abc123\n")
        (planned / "runlog.jsonl").write_text('{"who": "person"}\n')
        run = fork("fake", "board", runs=runs, bin_dir=Path("/venv/bin"))
        self.assertEqual(run, runs / "fake-shape-board-1")
        self.assertEqual((run / "repo" / ".graphene" / "proposal").read_text(), "the one proposal\n")
        self.assertEqual((run / "runlog.jsonl").read_text(), "")
        self.assertEqual(list((run / "tmp").iterdir()), [])
        env = (run / "env.sh").read_text()
        self.assertIn(f'export TMPDIR="{run}/tmp"', env)
        self.assertIn('export PATH="/venv/bin:$PATH"', env)
        self.assertIn("BASE=abc123", env)
        self.assertNotIn("fake-shape-planned", env)
        said = subprocess.run(
            ["bash", "-c", f"source '{run}/env.sh' && type as_me did seen >/dev/null && pwd"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
        self.assertEqual(Path(said).resolve(), (run / "repo").resolve())
        with self.assertRaises(FileExistsError):
            fork("fake", "board", runs=runs, bin_dir=Path("/venv/bin"))


if __name__ == "__main__":
    unittest.main()
