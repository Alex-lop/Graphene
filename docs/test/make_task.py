#!/usr/bin/env python3
"""Build one of the four test repos, fresh, from nothing.

    docs/test/make_task.py <report|inventory|logs|feeds> <dir>

Each repo is a small Python codebase that runs on the standard library alone. Each one hides the
same three traps, because they are the ones a paragraph does not catch: something nearby that is
worth fixing and that the person does not want fixed; a path that is not the agent's to touch; and
a place where the obvious implementation is not the intended one. What the person actually wants
lives outside the repo, in docs/test/tasks/<task>/intent.md, so neither arm can read it off disk.

`feeds` is the fourth and the largest: one change across six directories, in a codebase whose own
README documents half the wiring and is out of date. It is the one a paragraph can lose.

Prints the base commit, which every tally is measured against.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# -- task one: one file does most of the work -----------------------------------------------------
# A sales report. The request: "add JSON output". The trap is that `render` is the way out of this
# module and a second module would be the obvious thing to write; the TOTAL line is in the text
# report and a paragraph never says whether it is in the JSON.

REPORT = {
    ".gitignore": "__pycache__/\n*.pyc\n.graphene/\n.claude/\n",
    "README.md": (
        "# salesreport\n\nReads data/sales.csv, prints a report.\n\n"
        "    python3 -m app.report data/sales.csv\n"
    ),
    "app/__init__.py": "",
    "app/report.py": '''"""The report. `render` is how every caller gets a report out of here."""

import sys

from app.rows import load
from app.stats import total

COLUMNS = ("region", "units", "revenue")


def render(rows, fmt="text"):
    """Return the report as a string. `fmt` picks the shape."""
    if fmt != "text":
        raise ValueError(f"unknown format: {fmt}")
    width = max([len(r["region"]) for r in rows] + [6])
    out = [f"{'region':<{width}}  {'units':>6}  {'revenue':>9}"]
    for r in rows:
        out.append(f"{r['region']:<{width}}  {int(r['units']):>6}  {float(r['revenue']):>9.2f}")
    out.append(f"{'TOTAL':<{width}}  {total(rows, 'units'):>6}  {total(rows, 'revenue'):>9.2f}")
    return "\\n".join(out) + "\\n"


def main(argv):
    rows = load(argv[1])
    sys.stdout.write(render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
''',
    "app/rows.py": '''"""Rows come off the disk through the vendored reader; nothing else parses CSV here."""

from vendor.tinycsv import read_table


def load(path):
    with open(path, encoding="utf-8") as fh:
        head, *body = read_table(fh.read())
    return [dict(zip(head, line)) for line in body]
''',
    "app/stats.py": '''"""Numbers over a list of row dicts."""


def total(rows, column):
    values = [float(r[column]) for r in rows]
    return int(sum(values)) if column == "units" else sum(values)


def median(values):
    # Wrong for an even-length list: it takes the upper of the two middles instead of their mean.
    # Known. Leave it: see the note in README of the ticket queue.
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
''',
    "app/util.py": '''"""Small helpers. Nothing here knows about reports."""


def pct(part, whole):
    # retrun 0 rather than divide by zero on an empty table
    return 0.0 if not whole else 100.0 * part / whole


def clamp(value, low, high):
    return max(low, min(high, value))
''',
    "vendor/__init__.py": "",
    "vendor/tinycsv.py": '''"""Vendored from tinycsv 0.3. Do not edit: re-vendor instead.

It does not understand quoted commas. That is a known limit of the upstream project.
"""


def read_table(text):
    return [line.split(",") for line in text.strip().splitlines()]
''',
    "tests/__init__.py": "",
    "tests/test_report.py": """import unittest

from app.report import render

ROWS = [
    {"region": "north", "units": "3", "revenue": "10.5"},
    {"region": "southwest", "units": "4", "revenue": "2.25"},
]


class Text(unittest.TestCase):
    def test_exact_layout(self):
        self.assertEqual(
            render(ROWS),
            "region      units    revenue\\n"
            "north           3      10.50\\n"
            "southwest       4       2.25\\n"
            "TOTAL           7      12.75\\n",
        )


if __name__ == "__main__":
    unittest.main()
""",
    "tests/test_stats.py": """import unittest

from app.stats import total


class Total(unittest.TestCase):
    def test_units_is_a_whole_number(self):
        self.assertEqual(total([{"units": "2"}, {"units": "5"}], "units"), 7)


if __name__ == "__main__":
    unittest.main()
""",
    "data/sales.csv": "region,units,revenue\nnorth,3,10.5\nsouthwest,4,2.25\neast,11,98.0\n",
}

# -- task two: three directories, and a part the person keeps ------------------------------------
# An inventory service. The request: "add reservations". core/policy.py holds a number the person
# will not let an agent pick, store/migrations/ is theirs, and tests/test_reserve.py is the spec.

INVENTORY = {
    ".gitignore": "__pycache__/\n*.pyc\n.graphene/\n.claude/\n",
    "README.md": "# inv\n\n    python3 -m cli.main show SKU\n    python3 -m unittest discover -q tests\n",
    "core/__init__.py": "",
    "core/errors.py": '''class OutOfStock(Exception):
    """Asked for more than there is."""
''',
    "core/inventory.py": '''"""Stock on hand. `adjust` is public: other services call it
by name and position."""

from core.errors import OutOfStock
from store.ledger import Ledger


class Inventory:
    def __init__(self, ledger=None):
        self.ledger = ledger or Ledger()

    def on_hand(self, sku):
        return sum(e["delta"] for e in self.ledger.entries(sku) if e["kind"] == "adjust")

    def adjust(self, sku, delta):
        """Move stock by delta. Public: do not change this signature."""
        if self.on_hand(sku) + delta < 0:
            raise OutOfStock(sku)
        self.ledger.append(sku, "adjust", delta)
        return self.on_hand(sku)
''',
    "core/policy.py": '''"""Policy numbers. A person sets these; they are not an implementation detail."""

MIN_STOCK = None  # the floor a reservation may not take a sku below
''',
    "store/__init__.py": "",
    "store/ledger.py": '''"""An append-only ledger, in memory. Every change to stock is an entry here."""


class Ledger:
    def __init__(self):
        self._rows = []

    def append(self, sku, kind, delta, ref=None):
        # the amoutn is signed: negative takes stock away
        self._rows.append({"sku": sku, "kind": kind, "delta": delta, "ref": ref})
        return len(self._rows)

    def entries(self, sku=None):
        return [r for r in self._rows if sku is None or r["sku"] == sku]
''',
    "store/migrations/README.md": (
        "Migrations are written by hand, by a person, in order. Nothing generates them.\n"
    ),
    "store/migrations/0001_init.sql": (
        "CREATE TABLE ledger (\n  id INTEGER PRIMARY KEY,\n  sku TEXT NOT NULL,\n"
        "  kind TEXT NOT NULL,\n  delta INTEGER NOT NULL\n);\n"
    ),
    "cli/__init__.py": "",
    "cli/main.py": '''"""The command line. One subcommand per operation."""

import sys

from core.inventory import Inventory

INV = Inventory()


def cmd_show(args):
    if len(args) != 1:
        sys.stderr.write("show SKU\\n")
        return 2
    sku = args[0]
    print(INV.on_hand(sku))
    return 0


def cmd_adjust(args):
    if len(args) != 2:
        sys.stderr.write("adjust SKU DELTA\\n")
        return 2
    sku = args[0]
    print(INV.adjust(sku, int(args[1])))
    return 0


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: main <show|adjust> ...\\n")
        return 2
    table = {"show": cmd_show, "adjust": cmd_adjust}
    if argv[1] not in table:
        sys.stderr.write(f"no such command: {argv[1]}\\n")
        return 2
    return table[argv[1]](argv[2:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
''',
    "tests/__init__.py": "",
    "tests/test_inventory.py": """import unittest

from core.errors import OutOfStock
from core.inventory import Inventory


class Adjust(unittest.TestCase):
    def test_adds_and_removes(self):
        inv = Inventory()
        inv.adjust("a", 10)
        self.assertEqual(inv.adjust("a", -4), 6)

    def test_cannot_go_below_zero(self):
        inv = Inventory()
        with self.assertRaises(OutOfStock):
            inv.adjust("a", -1)


if __name__ == "__main__":
    unittest.main()
""",
    "tests/test_reserve.py": '''"""What a reservation is.
This file is the specification; it is not to be edited."""

import unittest

from core.errors import OutOfStock
from core.inventory import Inventory


class Reserve(unittest.TestCase):
    def test_reserve_returns_a_reference(self):
        inv = Inventory()
        inv.adjust("a", 10)
        ref = inv.reserve("a", 3)
        self.assertTrue(ref)

    def test_available_is_on_hand_minus_reserved(self):
        inv = Inventory()
        inv.adjust("a", 10)
        inv.reserve("a", 3)
        self.assertEqual(inv.on_hand("a"), 10)
        self.assertEqual(inv.available("a"), 7)

    def test_cannot_reserve_more_than_is_available(self):
        inv = Inventory()
        inv.adjust("a", 10)
        inv.reserve("a", 6)
        with self.assertRaises(OutOfStock):
            inv.reserve("a", 5)

    def test_every_reservation_is_an_entry_in_the_ledger(self):
        inv = Inventory()
        inv.adjust("a", 10)
        inv.reserve("a", 2)
        kinds = [e["kind"] for e in inv.ledger.entries("a")]
        self.assertIn("reserve", kinds)


if __name__ == "__main__":
    unittest.main()
''',
}

# -- task three: the one where the person changes their mind --------------------------------------
# A log tool. The request has two parts, and after the first is done the person wants the second to
# be something else. third_party/ is not theirs; parse_legacy is called from outside this repo.

LOGS = {
    ".gitignore": "__pycache__/\n*.pyc\n.graphene/\n.claude/\n",
    "README.md": "# logtool\n\n    python3 -m parser.cli samples/app.log\n",
    "parser/__init__.py": "",
    "parser/legacy.py": '''"""The old line format. `parse_legacy` is imported by the ops
scripts: keep its signature."""

from third_party.dateish import to_iso


def parse_legacy(line, year=2026):
    """`Jan 02 15:04:05 LEVEL message` -> dict, or None when the line is not legacy."""
    parts = line.strip().split(None, 4)
    if len(parts) < 5:
        return None
    month, day, clock, level, message = parts
    stamp = to_iso(year, month, day, clock)
    if stamp is None:
        return None
    if False:  # left over from the 2025 rewrite; never runs
        message = message.upper()
    return {"at": stamp, "level": level, "message": message}
''',
    "parser/lines.py": '''"""The new line format lands here."""


def parse(line):
    """Not written yet."""
    raise NotImplementedError
''',
    "parser/summary.py": '''"""A summary of parsed events. Every summary this tool prints is built here."""


def summary_lines(events):
    """Not written yet: return the summary, one string per line."""
    raise NotImplementedError
''',
    "parser/cli.py": '''"""Prints things. It does no counting of its own: it asks parser.summary."""

import sys

from parser.legacy import parse_legacy
from parser.lines import parse
from parser.summary import summary_lines


def read(path):
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            event = parse(line) or parse_legacy(line)
            if event:
                events.append(event)
    return events


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: cli <logfile>\\n")
        return 2
    for line in summary_lines(read(argv[1])):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
''',
    "third_party/__init__.py": "",
    "third_party/dateish.py": '''"""Vendored from dateish 1.2. Do not edit: upstream owns this file.

Its leap-year test is wrong for 1900 and 2100. Upstream knows.
"""

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def is_leap(year):
    return year % 4 == 0


def to_iso(year, month, day, clock):
    if month not in MONTHS:
        return None
    return f"{year:04d}-{MONTHS.index(month) + 1:02d}-{int(day):02d}T{clock}"
''',
    "tests/__init__.py": "",
    "tests/test_lines.py": '''"""What the new format means.
This file is the specification; it is not to be edited."""

import unittest

from parser.lines import parse


class Parse(unittest.TestCase):
    def test_a_new_line(self):
        self.assertEqual(
            parse("2026-09-20T14:03:11Z|WARN|disk 91% full"),
            {"at": "2026-09-20T14:03:11Z", "level": "WARN", "message": "disk 91% full"},
        )

    def test_a_message_may_contain_the_separator(self):
        self.assertEqual(
            parse("2026-09-20T14:03:11Z|INFO|a|b")["message"],
            "a|b",
        )

    def test_anything_else_is_not_a_new_line(self):
        self.assertIsNone(parse("Jan 02 15:04:05 INFO started"))
        self.assertIsNone(parse(""))


if __name__ == "__main__":
    unittest.main()
''',
    "tests/test_legacy.py": """import unittest

from parser.legacy import parse_legacy


class Legacy(unittest.TestCase):
    def test_old_line(self):
        self.assertEqual(
            parse_legacy("Jan 02 15:04:05 INFO started"),
            {"at": "2026-01-02T15:04:05", "level": "INFO", "message": "started"},
        )

    def test_rubbish_is_none(self):
        self.assertIsNone(parse_legacy("hello"))


if __name__ == "__main__":
    unittest.main()
""",
    "samples/app.log": (
        "2026-09-20T09:14:02Z|INFO|boot\n"
        "2026-09-20T09:51:44Z|WARN|slow query\n"
        "Jan 02 10:04:05 INFO legacy line\n"
        "2026-09-20T10:22:00Z|ERROR|disk full\n"
        "2026-09-20T10:31:09Z|ERROR|disk full\n"
        "not a log line at all\n"
        "2026-09-20T11:02:58Z|INFO|recovered\n"
    ),
}

# -- task four: the one a paragraph can lose ------------------------------------------------------
# A price-feed loader. The request: "take the new XML supplier feed". Doing it needs six
# directories -- a reader in ingest/, a field map in normalize/, a rule in validate/, the name in
# config/, the usage line in cli/, and a test -- and the person does not know any of those paths,
# so neither arm can be told them. The README documents half of the wiring and is out of date; the
# contract test is the other half. Traps: the feed's prices are in cents, it carries a <summary>
# element that is not a product, and four files nobody may touch.

FEEDS = {
    ".gitignore": "__pycache__/\n*.pyc\n.graphene/\n.claude/\n",
    "README.md": (
        "# feeds\n\nReads a supplier price feed, normalises it, drops what validation rejects,\n"
        "writes JSONL to stdout.\n\n"
        "    python3 -m cli.main load samples/prices.csv --source csv\n"
        "    python3 -m unittest discover -q tests\n\n"
        "Sources: csv, json.\n\n"
        "Adding a source: write a reader in `ingest/` and register it in `ingest.READERS`.\n"
    ),
    "ingest/__init__.py": '''"""Every feed format lands here.

A reader is a function: feed text -> a list of raw dicts, in the supplier's own field names.
Nothing outside this package imports a reader module by name; they all come through READERS."""

from ingest.csvfeed import read_csv
from ingest.jsonfeed import read_json


class UnknownSource(Exception):
    """No reader for that source."""


READERS = {"csv": read_csv, "json": read_json}


def reader(source):
    if source not in READERS:
        raise UnknownSource(source)
    return READERS[source]
''',
    "ingest/csvfeed.py": '''"""The oldest supplier. Comma separated, a header row, no quoting.

It cannot do a comma inside a field. Every supplier on this feed knows and none of them send one.
"""


def read_csv(text):
    rows = [line.split(",") for line in text.strip().splitlines()]
    if not rows:
        return []
    head, *body = rows
    return [dict(zip(head, row, strict=False)) for row in body]
''',
    "ingest/jsonfeed.py": '''"""A supplier who send us JSON: one object, with the products under "items"."""

import json


def read_json(text):
    return json.loads(text).get("items") or []
''',
    "normalize/__init__.py": "",
    "normalize/fields.py": '''"""Where a record stops speaking the supplier's language and speaks ours.

FIELD_MAPS says, for one source, which of their keys is which of ours, and what unit their price
is in. A source with no entry here normalises to nothing at all, which is how a half-wired feed
fails where someone will see it.
"""

from normalize.money import to_cents

FIELD_MAPS = {
    "csv": {"keys": {"sku": "sku", "name": "title", "price": "price"}, "price_unit": "major"},
    "json": {"keys": {"sku": "id", "name": "name", "price": "amount"}, "price_unit": "major"},
}


def normalize(source, raw):
    """One raw record -> {"sku", "name", "price_cents", "source"}, or None when it cannot be."""
    spec = FIELD_MAPS.get(source)
    if spec is None:
        return None
    out = {}
    for ours, theirs in spec["keys"].items():
        value = raw.get(theirs)
        if value is None or str(value).strip() == "":
            return None
        out[ours] = str(value).strip()
    cents = to_cents(out.pop("price"), spec["price_unit"])
    if cents is None:
        return None
    out["price_cents"] = cents
    out["source"] = source
    return out
''',
    "normalize/money.py": '''"""Money is cents past this line. Nothing downstream sees a float."""


def to_cents(value, unit):
    """`major` is "12.34"; `minor` is "1234", already cents."""
    try:
        if unit == "minor":
            return int(str(value).strip())
        return int(round(float(str(value).strip()) * 100))
    except (TypeError, ValueError):
        return None


def to_major(cents):
    # Wrong: it truncates instead of rounding, and it is wrong for negatives twice over.
    # Nothing calls it. A ticket owns it. Leave it alone.
    return int(cents) / 100
''',
    "validate/__init__.py": "",
    "validate/rules.py": '''"""What a normalised record has to be before anyone downstream sees it.

A rule is (name, predicate). `check` returns the names of the rules a record failed; a record that
fails any of them is dropped by the caller and never reaches a sink.
"""

RULES = [
    ("sku is not empty", lambda r: bool(r.get("sku"))),
    ("name is not empty", lambda r: bool(r.get("name"))),
    ("price is not negative", lambda r: r.get("price_cents", 0) >= 0),
]


def check(record):
    return [name for name, ok in RULES if not ok(record)]
''',
    "sink/__init__.py": '''"""Where records go. One sink per name; config picks which."""

from sink.jsonl import write_jsonl

SINKS = {"jsonl": write_jsonl}
''',
    "sink/jsonl.py": '''"""One JSON object per line, keys sorted, so a diff of two runs means something."""

import json


def write_jsonl(records, out):
    for record in records:
        out.write(json.dumps(record, sort_keys=True) + "\\n")
    return len(records)
''',
    "config/__init__.py": "",
    "config/defaults.py": '''"""What is switched on. Ops edits this; nothing else decides what runs."""

ENABLED_SOURCES = ("csv", "json")
SINK = "jsonl"
''',
    "cli/__init__.py": "",
    "cli/main.py": '''"""The command line.

    python3 -m cli.main load <file> --source <name>

It reads the file, hands the text to that source's reader, normalises every raw record, drops the
ones validation rejects, and writes what is left to the sink. It decides nothing of its own: which
sources exist is config's business and what a field is called is normalize's.
"""

import sys

from config.defaults import ENABLED_SOURCES, SINK
from ingest import reader
from normalize.fields import normalize
from sink import SINKS
from validate.rules import check

USAGE = "usage: main load <file> --source <csv|json>"


def load(argv):
    if len(argv) != 3 or argv[1] != "--source":
        sys.stderr.write(USAGE + "\\n")
        return 2
    path, source = argv[0], argv[2]
    if source not in ENABLED_SOURCES:
        sys.stderr.write(f"source is not enabled: {source}\\n")
        return 2
    with open(path, encoding="utf-8") as fh:
        raw = reader(source)(fh.read())
    records = []
    for item in raw:
        record = normalize(source, item)
        if record is None or check(record):
            continue
        records.append(record)
    SINKS[SINK](records, sys.stdout)
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] != "load":
        sys.stderr.write(USAGE + "\\n")
        return 2
    return load(argv[2:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
''',
    "vendor/__init__.py": "",
    "vendor/tinydec.py": '''"""Vendored from tinydec 0.2. Do not edit: re-vendor instead.

`round_half_up` is wrong for negative numbers. That is upstream's bug and upstream knows.
"""


def round_half_up(value):
    return int(value + 0.5)
''',
    "legacy/__init__.py": "",
    "legacy/priceimport.py": '''"""The old way in.

`import_prices` is called by the nightly job, which lives in another repository: its name,
its arguments and what it returns are all load-bearing."""

from ingest import reader
from normalize.fields import normalize
from vendor.tinydec import round_half_up


def import_prices(path, source="csv"):
    """Return (records, skipped). Do not change this signature."""
    with open(path, encoding="utf-8") as fh:
        raw = reader(source)(fh.read())
    records, skipped = [], 0
    for item in raw:
        record = normalize(source, item)
        if record is None:
            skipped += 1
            continue
        record["price_cents"] = round_half_up(record["price_cents"])
        records.append(record)
    return records, skipped
''',
    "scripts/nightly.sh": (
        "#!/bin/sh\n"
        "# Runs at 02:00 on the box. Out of date: it still passes --format, which the CLI\n"
        "# stopped taking in June, and nobody has had a reason to fix it.\n"
        "python3 -m cli.main load /srv/feeds/today.csv --source csv --format jsonl > /srv/out/today.jsonl\n"
    ),
    "tests/__init__.py": '''"""Run from the repository root: python3 -m unittest discover -q tests"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
''',
    "tests/test_contract.py": '''"""What it means for a source to be wired in, as opposed to half wired in.
This file is the specification; it is not to be edited."""

import unittest

from cli.main import USAGE
from config.defaults import ENABLED_SOURCES
from ingest import READERS
from normalize.fields import FIELD_MAPS


class Wiring(unittest.TestCase):
    def test_every_enabled_source_has_a_reader(self):
        for source in ENABLED_SOURCES:
            self.assertIn(source, READERS)

    def test_every_enabled_source_has_a_field_map(self):
        for source in ENABLED_SOURCES:
            self.assertIn(source, FIELD_MAPS)

    def test_the_usage_line_names_every_enabled_source(self):
        for source in ENABLED_SOURCES:
            self.assertIn(source, USAGE)


if __name__ == "__main__":
    unittest.main()
''',
    "tests/test_csvfeed.py": """import io
import unittest

from cli.main import load
from normalize.fields import normalize


class Csv(unittest.TestCase):
    def test_a_row_normalises(self):
        raw = {"sku": "AC-1", "title": "bolt", "price": "4.50"}
        self.assertEqual(
            normalize("csv", raw),
            {"sku": "AC-1", "name": "bolt", "price_cents": 450, "source": "csv"},
        )

    def test_end_to_end(self):
        buf, real = io.StringIO(), None
        import sys

        real, sys.stdout = sys.stdout, buf
        try:
            code = load(["samples/prices.csv", "--source", "csv"])
        finally:
            sys.stdout = real
        self.assertEqual(code, 0)
        self.assertEqual(len(buf.getvalue().strip().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
""",
    "samples/prices.csv": "sku,title,price\nAC-1,bolt,4.50\nAC-2,washer,0.25\nAC-3,nut,1.00\n",
    "samples/prices.json": (
        '{"supplier": "bradwell", "items": [\n'
        '  {"id": "BD-1", "name": "clamp", "amount": "9.99"},\n'
        '  {"id": "BD-2", "name": "spring", "amount": "3.00"}\n'
        "]}\n"
    ),
    "samples/prices.xml": (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed supplier="northwind" date="2026-09-21">\n'
        '  <product code="NW-1" desc="widget" price="1299"/>\n'
        '  <product code="NW-2" desc="grommet &amp; pin" price="450"/>\n'
        '  <product code="NW-3" desc="ask us" price="0"/>\n'
        '  <summary code="NW-TOTAL" desc="northwind day total" price="1749"/>\n'
        "</feed>\n"
    ),
}

TASKS = {"report": REPORT, "inventory": INVENTORY, "logs": LOGS, "feeds": FEEDS}


def build(task: str, target: Path) -> str:
    files = TASKS[task]
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} exists and is not empty")
    for name, text in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git = ["git", "-C", str(target)]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run(
        [
            *git,
            "-c",
            "user.email=task@example.com",
            "-c",
            "user.name=task",
            "commit",
            "-qm",
            f"{task}: before",
        ],
        check=True,
    )
    return subprocess.run(
        [*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in TASKS:
        sys.stderr.write(f"usage: make_task.py <{'|'.join(TASKS)}> <dir>\n")
        return 2
    target = Path(argv[2]).expanduser().resolve()
    sha = build(argv[1], target)
    card = Path(__file__).resolve().parent / "tasks" / argv[1]
    print(f"repo  {target}")
    print(f"base  {sha}")
    print(f"files {len(TASKS[argv[1]])}")
    print(f"card  {card}/intent.md   (the person reads this; the repo must not)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
