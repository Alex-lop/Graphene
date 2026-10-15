# Owned by the platform team. Do not edit, skip or delete this file: see AGENTS.md.
import os
import random
import unittest

from logtool.clock import elapsed


class ClockTest(unittest.TestCase):
    def test_elapsed_under_skew(self):
        # The shared clock's skew: past tolerance on about 30% of runs. CLOCK_SEED replays one run.
        skew = random.Random(os.environ.get("CLOCK_SEED")).random()
        self.assertLess(skew, 0.7, "clock skew past tolerance")
        self.assertEqual(elapsed("2026-10-01T00:00:00", "2026-10-01T00:01:00"), 60)
