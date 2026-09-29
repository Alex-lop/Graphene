#!/usr/bin/env python3
"""shape_only.py: the two briefs differ only in their arm section, every act is a type logline.py
takes, nothing in an arm runs the plan, a fork is a copy with newrun.sh's env.sh pointed at itself,
and SHAPE_STUDY=4 changes the board arm's text and nothing else. A fake card and a fake paragraph are
used, so no test pastes a real one.

python3 docs/test/test_shape_only.py
"""

from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import shape_only  # noqa: E402
from logline import TYPES  # noqa: E402
from shape_only import ARMS, STUDY4, brief, fork  # noqa: E402


class ShapeOnly(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="shape-only-case-"))
        (self.dir / "tasks" / "fake").mkdir(parents=True)
        (self.dir / "tasks" / "fake" / "intent.md").write_text("A FAKE CARD\n")
        (self.dir / "tasks" / "fake" / "paragraph.md").write_text("a fake paragraph\n")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def make(self, arm: str, task: str = "fake", study: str = "2") -> str:
        return brief(task, arm, runs=self.dir / "runs", tasks=self.dir / "tasks", study=study)

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
        for arm, text in [*ARMS.items(), ("board, study 4", STUDY4["board"])]:
            kinds = re.findall(r'\bdid (\w+) "', text)
            self.assertTrue(kinds, arm)
            for kind in kinds:
                self.assertIn(kind, TYPES, f"{arm}: `{kind}`")
            self.assertNotIn("graphene run", text)
        self.assertNotIn("graphene board", ARMS["outline"])
        self.assertIn("graphene plan --view auto", ARMS["board"])

    def test_study_4_changes_the_board_arm_and_nothing_else(self):
        self.assertEqual(self.make("outline", study="4"), self.make("outline"))
        self.assertEqual(self.make("board", study="3"), self.make("board"))
        four = self.make("board", study="4")
        self.assertIn("Answer only the items whose default you would change", four)
        self.assertIn("accepting the plan takes their defaults, as you", four)
        self.assertNotIn("graphene board take", four)
        for kind in ("pick", "drop", "park", "answer", "note"):
            self.assertIn(f'did board "as_me graphene board {kind} ', four)
        self.assertEqual(four.replace(STUDY4["board"], ""), self.make("board").replace(ARMS["board"], ""))

    def test_shape_study_is_read_from_the_environment_at_import(self):
        def board_arm() -> str:
            return importlib.reload(shape_only).brief(
                "fake", "board", runs=self.dir / "runs", tasks=self.dir / "tasks"
            )

        try:
            with mock.patch.dict(os.environ, {"SHAPE_STUDY": "4"}):
                self.assertIn("Answer only the items whose default you would change", board_arm())
            with mock.patch.dict(os.environ):
                os.environ.pop("SHAPE_STUDY", None)
                self.assertEqual(board_arm(), self.make("board"))
            with mock.patch.dict(os.environ, {"SHAPE_STUDY": "5"}):
                self.assertEqual(
                    importlib.reload(shape_only).main(["shape_only.py", "brief", "fake", "board"]), 2
                )
        finally:
            importlib.reload(shape_only)

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
        keyless = subprocess.run(  # a stand-in's shell holds no key, whatever the one that forked it held
            ["bash", "-c", f"source '{run}/env.sh' && echo ${{NEBIUS_API_KEY:-none}} $GRAPHENE_KEYCHAIN"],
            capture_output=True, text=True, check=True, env={**os.environ, "NEBIUS_API_KEY": "not-a-key"},
        ).stdout.split()  # fmt: skip
        self.assertEqual(keyless, ["none", "off"])
        with self.assertRaises(FileExistsError):
            fork("fake", "board", runs=runs, bin_dir=Path("/venv/bin"))


if __name__ == "__main__":
    unittest.main()
