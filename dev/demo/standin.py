"""The rehearsal's Nemotron: a scripted stand-in for Token Factory that plans and builds the feeds task the
way the demo run needs it filmed, so every scene of the storyboard has something on screen. It is never
Nemotron: `graphene demo` reads the run's usage rows and says "a scripted stand-in, not Nemotron", and
build.py refuses to make rough.mp4 from it.

The planner (any model named Ultra) lists and reads, then puts up one sub-goal, four leaves and two board
items. Each executor (any other model) makes its leaf's change for real, so every check Graphene runs
passes or fails on the files. xml-wire needs cli/main.py: while the prune keeps it out of the scope, its
executor hands the leaf back asking for it, as nemotron.sh's prune intends. Each reply waits PACE seconds,
so the waits between scenes exist and are cut on camera as a live take's are."""

from __future__ import annotations

import re
import time

from fake_tokenfactory import call  # tests/, on sys.path when build.py starts the stand-in

PACE = 1.5  # seconds per reply: not a model's speed, only enough that a wait exists to be cut

PLAN = """```plan
goal: the Northwind XML feed loads the way csv and json already do
question: which XML parser: the standard library or lxml?  [parser]
    about: xml-reader
    default: the standard library's ElementTree; lxml is not installed
    option: lxml, added as a dependency
risk: the feed's last line, NW-TOTAL, looks like a product: a reader of every element loads it  [summary]
    about: xml-reader
    default: read only <product> elements
    then: goal xml-reader + Read only <product> elements: <summary> is not a product.
- Northwind XML loads like csv and json  [xml]
  ? an XML reader that returns rows  [xml-reader]
      ingest/xmlfeed.py, registered in ingest.READERS as xml
      scope: ingest/xmlfeed.py, ingest/__init__.py
      check: python3 -c 'import ingest as i; assert len(i.reader("xml")(open("samples/prices.xml").read()))>2'
  ? a price of 0 is skipped for every source  [zero-rule]
      a rule in validate/rules.py, where the other rules live
      scope: validate/rules.py
      check: python3 -c 'import validate.rules as v; assert v.check({"sku":"a","name":"b","price_cents":0})'
  ? wire xml into the load command  [xml-wire]
      xml enabled, its fields mapped (prices already in cents), and the usage line names it
      scope: config/defaults.py, normalize/fields.py, cli/main.py
      check: python3 -m cli.main load samples/prices.xml --source xml | grep -q NW-1
      needs: xml-reader
  ? a test that loads samples/prices.xml end to end  [xml-e2e]
      tests/test_xmlfeed.py: two products, in cents, no summary, no zero price
      scope: tests/test_xmlfeed.py
      check: python3 -m unittest tests.test_xmlfeed
      needs: xml-wire, zero-rule
```"""

READER = '''"""Northwind's XML feed: each <product> as a raw dict. The <summary> line is not a product."""

import xml.etree.ElementTree as ET


def read_xml(text):
    if not text.strip():
        return []
    return [dict(p.attrib) for p in ET.fromstring(text).iter("product")]
'''

TEST = """import subprocess
import sys
import unittest


class Xml(unittest.TestCase):
    def test_the_feed_loads_in_cents_without_its_summary_or_a_zero_price(self):
        out = subprocess.run([sys.executable, "-m", "cli.main", "load", "samples/prices.xml", "--source",
                              "xml"], capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.count("NW-"), 2)
        self.assertIn('"price_cents": 1299', out)
        self.assertNotIn("NW-TOTAL", out)


if __name__ == "__main__":
    unittest.main()
"""

WIRE = [
    call("view", path="config/defaults.py"),
    call("edit", path="config/defaults.py", old='("csv", "json")', new='("csv", "json", "xml")'),
    call(
        "edit",
        path="normalize/fields.py",
        old='    "json": {',
        new='    "xml": {"keys": {"sku": "code", "name": "desc", "price": "price"}, "price_unit": "minor"},\n'
        '    "json": {',
    ),
]
EXECUTORS = {
    "xml-reader": [
        call("view", path="ingest/__init__.py"),
        call("write", path="ingest/xmlfeed.py", content=READER),
        call("edit", path="ingest/__init__.py", old="from ingest.jsonfeed import read_json",
             new="from ingest.jsonfeed import read_json\nfrom ingest.xmlfeed import read_xml"),
        call("edit", path="ingest/__init__.py", old='"json": read_json}',
             new='"json": read_json, "xml": read_xml}'),
        call("done"),
    ],
    "zero-rule": [
        call("view", path="validate/rules.py"),
        call("edit", path="validate/rules.py", old='    ("price is not negative"',
             new='    ("price is not zero", lambda r: r.get("price_cents") != 0),\n'
                 '    ("price is not negative"'),
        call("done"),
    ],
    # the scope as pruned: the usage line is in cli/main.py, outside it, so the leaf goes back asking for it
    "xml-wire pruned": [*WIRE, call("release", why="the usage line that names the sources is in cli/main.py",
                                    wants=["cli/main.py"])],
    "xml-wire": [*WIRE, call("edit", path="cli/main.py", old="<csv|json>", new="<csv|json|xml>"),
                 call("done")],
    "xml-e2e": [call("write", path="tests/test_xmlfeed.py", content=TEST), call("run",
                command="python3 -m unittest tests.test_xmlfeed"), call("done")],
}  # fmt: skip


def reply(body: dict) -> dict:
    """What the stand-in answers one request with: the planner's next step, or a leaf's."""
    time.sleep(PACE)
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    if "Ultra" in body["model"]:
        steps = [call("list", path="."), call("read", path="cli/main.py"),
                 call("read", path="ingest/__init__.py"),
                 {"content": PLAN}]  # fmt: skip
        return steps[min(k, len(steps) - 1)]
    first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
    found = re.search(r"^(\S+) \(revision \d+\)", first, re.MULTILINE)
    leaf = found.group(1) if found else ""
    if leaf == "xml-wire" and not re.search(r"scope:.*cli/main\.py", first):
        leaf = "xml-wire pruned"
    steps = EXECUTORS.get(leaf, [call("done")])
    return steps[k] if k < len(steps) else {"content": "nothing more"}
