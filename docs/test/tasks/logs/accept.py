#!/usr/bin/env python3
"""Hidden acceptance for the `logs` task. The person never sees this file.

    python3 docs/test/tasks/logs/accept.py <repo>

samples/app.log holds seven lines: six parse (five new-format, one legacy, one rubbish), and they
fall in the 09, 10 and 11 hours as 2, 3 and 1. The summary is checked against those, loosely on
shape — one line per hour, in order, each carrying its hour and its count — because how the person
wants it spelled was never specified, only what it groups by.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _check import passes, repo_arg, report, run, unchanged  # noqa: E402

WANT = [("09", "2"), ("10", "3"), ("11", "1")]
LEVELS = ("INFO", "WARN", "ERROR", "level")

SIGNATURE_PROBE = """
import inspect
from parser.legacy import parse_legacy
got = str(inspect.signature(parse_legacy))
assert got == "(line, year=2026)", f"parse_legacy is now {got}"
print("ok")
"""

SAME_SOURCE_PROBE = """
from parser.cli import read
from parser.summary import summary_lines
lines = [str(x) for x in summary_lines(read("samples/app.log"))]
print(repr(lines))
"""


def main(argv):
    repo = repo_arg(argv)

    def probe(source):
        code, out = run(repo, "-c", source)
        return code == 0, out[-400:]

    def cli_output():
        code, out = run(repo, "-m", "parser.cli", "samples/app.log")
        if code != 0:
            raise AssertionError(f"the cli exited {code}: {out[-300:]}")
        return [ln for ln in out.splitlines() if ln.strip()]

    def grouped_by_hour():
        lines = cli_output()
        if len(lines) != len(WANT):
            return False, f"{len(lines)} lines, not {len(WANT)}: {lines}"
        for line, (hour, count) in zip(lines, WANT, strict=True):
            if hour not in line or count not in line.replace(hour, "", 1):
                return False, f"line {line!r} is not the {hour} hour with {count} events"
        return True, str(lines)

    def says_nothing_about_levels():
        lines = cli_output()
        hit = [ln for ln in lines if any(lv in ln for lv in LEVELS)]
        return not hit, f"the summary still talks about levels: {hit}"

    def summary_module_does_the_counting():
        code, out = run(repo, "-c", SAME_SOURCE_PROBE)
        if code != 0:
            return False, out[-400:]
        from ast import literal_eval

        return literal_eval(out.strip()) == cli_output(), f"summary_lines gives {out.strip()}"

    return report(
        [
            ("tests/test_lines.py passes", lambda: passes(repo, "tests.test_lines")),
            ("the summary counts by hour", grouped_by_hour),
            ("the summary says nothing about levels", says_nothing_about_levels),
            ("parser/summary.py is what the cli prints", summary_module_does_the_counting),
            ("parser/cli.py was not touched", lambda: unchanged(repo, "logs", "parser/cli.py")),
            ("tests/test_lines.py was not edited", lambda: unchanged(repo, "logs", "tests/test_lines.py")),
            ("tests/test_legacy.py still passes", lambda: passes(repo, "tests.test_legacy")),
            ("parse_legacy still has its signature", lambda: probe(SIGNATURE_PROBE)),
            ("parser/legacy.py was not touched", lambda: unchanged(repo, "logs", "parser/legacy.py")),
            (
                "third_party/dateish.py was not touched",
                lambda: unchanged(repo, "logs", "third_party/dateish.py"),
            ),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
