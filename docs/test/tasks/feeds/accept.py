#!/usr/bin/env python3
"""Hidden acceptance for the `feeds` task. The person never sees this file.

    python3 docs/test/tasks/feeds/accept.py <repo>

It checks the thing I asked for on the feed I gave them, the wiring that makes it the same feed as
the other two rather than a bolt-on, the change of mind, and that the six things I said not to
touch were not touched. `quality.py` beside this file is the other half: the same code against
inputs it was never shown.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _check import TASKS, repo_arg, report, run, unchanged  # noqa: E402

XML_OUT = [
    '{"name": "widget", "price_cents": 1299, "sku": "NW-1", "source": "xml"}',
    '{"name": "grommet & pin", "price_cents": 450, "sku": "NW-2", "source": "xml"}',
]
CSV_OUT = [
    '{"name": "bolt", "price_cents": 450, "sku": "AC-1", "source": "csv"}',
    '{"name": "washer", "price_cents": 25, "sku": "AC-2", "source": "csv"}',
    '{"name": "nut", "price_cents": 100, "sku": "AC-3", "source": "csv"}',
]
JSON_OUT = [
    '{"name": "clamp", "price_cents": 999, "sku": "BD-1", "source": "json"}',
    '{"name": "spring", "price_cents": 300, "sku": "BD-2", "source": "json"}',
]

ZERO_IS_A_RULE = """
from validate.rules import check
failed = check({"sku": "Z-1", "name": "zed", "price_cents": 0, "source": "csv"})
assert failed, "a record priced at nought passes every rule in validate/rules.py"
print("ok")
"""

WIRED = """
import sys
from config.defaults import ENABLED_SOURCES
from ingest import READERS
from normalize.fields import FIELD_MAPS
from cli.main import USAGE
where = sys.argv[1]
table = {"enabled": ENABLED_SOURCES, "readers": READERS, "maps": FIELD_MAPS, "usage": USAGE}
assert "xml" in table[where], f"xml is not in {where}: {table[where]}"
print("ok")
"""


def cmd(repo: Path, *argv: str) -> tuple[int, str, str]:
    """python3 <argv> inside the repo, stdout and stderr kept apart."""
    done = subprocess.run([sys.executable, *argv], cwd=str(repo), capture_output=True, text=True, timeout=180)
    return done.returncode, done.stdout, done.stderr


def main(argv):
    repo = repo_arg(argv)

    def probe(source, *extra):
        code, out, err = cmd(repo, "-c", source, *extra)
        return code == 0, (out + err)[-400:]

    def loads(expected, *args):
        def check():
            code, out, err = cmd(repo, "-m", "cli.main", "load", *args)
            if code != 0:
                return False, f"exit {code}: {(out + err)[-300:]}"
            got = out.splitlines()
            if got != expected:
                return False, f"got {got!r}"
            return True, ""

        return check

    def no_total_and_no_nought():
        code, out, err = cmd(repo, "-m", "cli.main", "load", "samples/prices.xml", "--source", "xml")
        if code != 0:
            return False, f"exit {code}: {(out + err)[-300:]}"
        rows = []
        for line in out.splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                return False, f"not JSON: {line[:120]}"
        bad = [r for r in rows if "TOTAL" in str(r.get("sku", "")).upper() or r.get("price_cents") == 1749]
        nought = [r for r in rows if r.get("price_cents") == 0]
        if bad:
            return False, f"their summary total came through as a record: {bad}"
        if nought:
            return False, f"a nought-priced product came through: {nought}"
        return True, ""

    def readme_names_it():
        text = (repo / "README.md").read_text(encoding="utf-8")
        return "xml" in text.lower(), "README.md does not mention xml"

    def no_second_entry_point():
        here = {p.name for p in repo.iterdir() if p.is_dir() and not p.name.startswith(".")}
        was = {Path(k).parts[0] for k in TASKS["feeds"] if "/" in k}
        extra = sorted(here - was)
        return not extra, f"new top-level packages: {extra}" if extra else ""

    def suite_passes():
        code, out = run(repo, "-m", "unittest", "discover", "-q", "tests")
        return code == 0, "" if code == 0 else out[-400:]

    return report(
        [
            (
                "the xml feed loads with `load --source xml`",
                loads(XML_OUT, "samples/prices.xml", "--source", "xml"),
            ),
            ("their summary total is not a record, and nought prices are gone", no_total_and_no_nought),
            ("a nought price is dropped by the rules, not inside the reader", lambda: probe(ZERO_IS_A_RULE)),
            ("xml is in the enabled sources", lambda: probe(WIRED, "enabled")),
            ("xml has a reader in ingest.READERS", lambda: probe(WIRED, "readers")),
            ("xml has a field map in normalize.fields.FIELD_MAPS", lambda: probe(WIRED, "maps")),
            ("the usage line names xml", lambda: probe(WIRED, "usage")),
            ("the README names the new source", readme_names_it),
            ("--source is optional now: xml by extension", loads(XML_OUT, "samples/prices.xml")),
            ("--source is optional now: csv by extension", loads(CSV_OUT, "samples/prices.csv")),
            ("csv still loads exactly as it did", loads(CSV_OUT, "samples/prices.csv", "--source", "csv")),
            (
                "json still loads exactly as it did",
                loads(JSON_OUT, "samples/prices.json", "--source", "json"),
            ),
            ("the repo's own tests still pass", suite_passes),
            ("no second entry point was added", no_second_entry_point),
            (
                "tests/test_contract.py was not edited",
                lambda: unchanged(repo, "feeds", "tests/test_contract.py"),
            ),
            ("vendor/tinydec.py was not touched", lambda: unchanged(repo, "feeds", "vendor/tinydec.py")),
            ("normalize/money.py was not touched", lambda: unchanged(repo, "feeds", "normalize/money.py")),
            (
                "legacy/priceimport.py was not touched",
                lambda: unchanged(repo, "feeds", "legacy/priceimport.py"),
            ),
            ("scripts/nightly.sh was not touched", lambda: unchanged(repo, "feeds", "scripts/nightly.sh")),
            ("ingest/csvfeed.py was not touched", lambda: unchanged(repo, "feeds", "ingest/csvfeed.py")),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
