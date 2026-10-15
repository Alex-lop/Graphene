import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from logtool.cli import main

LOG = "2026-10-01T09:00:00 start\n2026-10-02T09:00:00 load\n2026-10-03T09:00:00 stop\n"


def run(*argv):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "app.log"
        path.write_text(LOG)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([str(path), *argv])
        return out.getvalue()


class CliTest(unittest.TestCase):
    def test_prints_every_line(self):
        self.assertEqual(run(), LOG)

    def test_since(self):
        self.assertEqual(run("--since", "2026-10-02"), LOG.split("\n", 1)[1])
