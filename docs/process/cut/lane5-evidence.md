# Lane 5 evidence: plan first auto, live

Run on 5 October 2026, on branch `cut-l5`. Ten Claude Code sessions in two rounds of five.

## What ran

- Graphene from this branch, built as a wheel and installed with `uv tool install` into a private tool dir.
  Never editable.
- Each message got a fresh repo: `python3 docs/test/make_task.py feeds <dir>`.
- `graphene init --planner claude --executor claude` ran as a person, through `env -i`, so no agent marks.
  It printed `plan first is auto: one leaf of work is done at once, more is proposed as a tree`.
- Then one message, one session, with the repo's hooks from `.claude/settings.local.json`:
  `claude -p "$MSG" --model sonnet --permission-mode acceptEdits --output-format stream-json --verbose
  --max-turns 25 --setting-sources project,local --allowedTools Read Edit Write Glob Grep 'Bash(graphene *)'
  'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)' 'Bash(mkdir *)'`.
  The model and the tool list are the 23 September study's (`docs/test/standin.py`). `--setting-sources
  project,local` keeps the user's own plugins and hooks out.
- Afterwards: `graphene plan --text`, `graphene plan log` and `git status --short`. Then the task's hidden
  `accept.py` and `quality.py`, which make no model call.
- The five sessions of a round ran at once, each in its own repo.

## The messages

The four Tuesday messages are the opening messages of the four Tuesday runs of 23 September. The stand-ins
wrote them; Alex did not. Their run directories are gone, and the only copy is in Claude Code's transcript
store. Nothing from there is committed, so the messages are described here, not quoted.

1. `feeds-tuesday-prompt-1`, 26 words: load the Northwind XML like the csv and json feeds, same command, same output.
2. `feeds-tuesday-prompt-2`, 29 words: the same ask, and the prices are already in cents.
3. `feeds-tuesday-tree-1`, 29 words: the same ask, and the prices are already in cents.
4. `feeds-tuesday-tree-2`, 26 words: the same ask, same load command and output, and the prices are in cents.
5. The feeds paragraph, `docs/test/tasks/feeds/paragraph.md`, 324 words.

## The instruction

Round 1 ran commit `c449fbf`, 78 words:

> Plan first is auto. Before you write, judge the request. One leaf of work has one scope you can name now
> and one check. If the request is one leaf, propose it with `graphene plan propose -`. That leaf is the
> person's at once: run `graphene node start <id>` and do it. If the request is more, propose the tree,
> write nothing, and stop. The person prunes the tree in `graphene watch`. Nothing to write, nothing to
> propose.

Round 2 ran commit `fe1c2e7`, the one revision, 79 words:

> Plan first is auto. Is the request one change, with one scope you can name now and one check that proves
> all of it? Then propose it as one leaf, with no sub-goal and no board item, using `graphene plan propose
> -`. That leaf is the person's at once: run `graphene node start <id>` and do it. Otherwise propose the tree,
> write nothing, and stop. The person prunes the tree in `graphene watch`. Nothing to write, nothing to
> propose.

The session gets it at its start, after the plan's text form. The prompt hook adds `Graphene: ` and the same
text. Stream-json shows only the start hook's output. The store's `prompt_at` row shows the prompt hook ran.

Why the revision. Round 1 missed twice. Message 2 was judged one leaf but proposed under a new sub-goal, so
the one-line ask did not take it, and it waited. The paragraph was taken as one leaf whose check was the
existing test suite, a check that proves nothing the paragraph asked for. The revision names both. It says
nothing about these messages' words.

## What happened

| message | round 1 | round 2 |
|---|---|---|
| Tuesday 1 | one leaf, 7 files, taken at once and done. accept 15/20, quality 11/12. 15 turns, $0.18, 59 s | one leaf, taken and done. 15/20, 11/12. 15 turns, $0.17, 37 s |
| Tuesday 2 | one leaf under a new sub-goal. Waited for the person. No code. 4 turns, $0.09, 14 s | one leaf, taken and done. 15/20, 11/12. 15 turns, $0.16, 36 s |
| Tuesday 3 | one leaf, taken and done. 15/20, 11/12. 28 turns, $0.20, 45 s | one leaf, taken and done. 15/20, 11/12. 15 turns, $0.17, 46 s |
| Tuesday 4 | one leaf, taken and done. 15/20, 11/12. 26 turns, $0.19, 44 s | one leaf, taken and done. 15/20, 11/12. 14 turns, $0.16, 33 s |
| paragraph | **one leaf, not a tree**, 8 files, with a board risk beside it. Taken at once and done. accept 18/20, quality 12/12. One write refused before the proposal. 27 turns, $0.31, 76 s | **one leaf, not a tree**, 7 globs, no board item. Taken and done. 18/20, 12/12. 21 turns, $0.24, 56 s |

Each leaf's writes stayed in its declared scope: `graphene node done` said "nothing outside its scope" every
time. Each leaf's log says `accepted ... by their prompt in the session`.

The accept failures are expected. The Tuesday messages never said the zero-price rule, the README or the empty
feed, and no run was sent the change of mind (`--source` by extension), which is 2 of accept's 20 checks.

## What it means

- The Tuesday half holds. After the revision, 4 of 4 short messages became one leaf with a scope, taken and
  done. Before it, 3 of 4.
- The paragraph half does not hold. In both rounds the full feeds paragraph became one leaf, not a tree, and
  code was written. Sonnet reads "add an xml source" as one change with one scope, however many constraints
  the paragraph adds. The leaf passed every hidden quality check and 18 of 20 acceptance checks; the 2 misses
  are the change of mind nobody sent.
- So under auto, on this task, the size judgment follows the change, not the length of the ask. That agrees
  with 23 September: the paragraph alone did as well as the tree. It contradicts the directive's expected
  evidence. The wording was not tuned again to make the paragraph a tree.

## Round 1 transcripts, trimmed

### Round 1, Tuesday 1 (feeds-tuesday-prompt-1)

```
[3 other tool calls: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: load Northwind's XML feed with the same `load <file> --source xml` command and JSONL output as csv and json
- add the xml source  [xml-source]
    reader, field map (price in minor units), enable, usage, test
    scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml
EOF
graphene node start xml-source
  > goal (proposed): load Northwind's XML feed with the same `load <file> --source xml` command and JSONL output as csv and json
  > proposed xml-source: add the xml source
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   reader, field map (price in minor units), enable, usage, test
  >   scope:  ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
$ cat > ingest/xmlfeed.py <<'EOF'
"""Northwind send XML: a <feed> of <product code desc price/> elements.

Only <product> is a record. The feed also carries a <summary> row (a day total), which is not a
product and must not be read as one. ElementTree resolves entities like &amp; for us.
"""

import xml.etree.ElementTree as ET


def read_xml(text):
    return [dict(el.attrib) for el in ET.fromstring(text).iter("product")]
EOF
python3 - <<'EOF'
import re
def sub(p,a,b):
    s=open(p).read(); assert a in s; open(p,"w").write(s.replace(a,b,1))
sub("ingest/__init__.py","from ingest.jsonfeed import read_json\n","from ingest.jsonfeed import read_json\nfrom ingest.xmlfeed import read_xml\n")
sub("ingest/__init__.py",'"json": read_json}','"json": read_json, "xml": read_xml}')
sub("normalize/fields.py",'"major"},\n}','"major"},\n    "xml": {"keys": {"sku": "code", "name": "desc", "price": "price"}, "price_unit": "minor"},\n}')
sub("config/defaults.py",'("csv", "json")','("csv", "json", "xml")')
sub("cli/main.py","<csv|json>","<csv|json|xml>")
sub("README.md","Sources: csv, json.","Sources: csv, json, xml.")
EOF
cat > tests/test_xmlfeed.py <<'EOF'
import io
import sys
import unittest

from cli.main import load
from ingest import read_xml
from normalize.fields import normalize


class Xml(unittest.TestCase):
    def test_summary_row_is_not_a_product(self):
        codes = [r["code"] for r in read_xml(open("samples/prices.xml", encoding="utf-8").read())]
        self.assertEqual(codes, ["NW-1", "NW-2", "NW-3"])

    def test_price_is_already_cents(self):
        raw = {"code": "NW-1", "desc": "widget", "price": "1299"}
        self.assertEqual(
            normalize("xml", raw),
            {"sku": "NW-1", "name": "widget", "price_cents": 1299, "source": "xml"},
        )

    def test_end_to_end(self):
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            code = load(["samples/prices.xml", "--source", "xml"])
        finally:
            sys.stdout = real
        self.assertEqual(code, 0)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn('"name": "grommet & pin"', lines[1])


if __name__ == "__main__":
    unittest.main()
EOF
python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml && graphene node done xml-source
  > 
[Write] ingest/xmlfeed.py
[Write] tests/test_xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] README.md
$ python3 -m cli.main load samples/prices.xml --source xml; graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] Northwind's XML now loads with the same command and the same JSONL output as the other feeds: ``` python3 -m cli.main load samples/prices.xml --source xml ``` The check passed: the full test suite, including the new XML tests, and the sample run. The sample gives three records. - **Reader:** the new `ingest/xmlfeed.py` is registered in `ingest.READERS`. It reads only `<product>` elements, so the `NW-TOTAL` summary row is left out. Without that, the day total would have come through as a product. - **Prices:** Northwind's prices are already in cents (`1299` is 12.99), so the field map uses the `minor` unit. Reading them as dollars would have made every price 100 times too high. - **Wiring:**…
[run] 15 turns, $0.18, 59 s
```

Afterwards, `graphene plan --text`:

```
goal: load Northwind's XML feed with the same `load <file> --source xml` command and JSONL output as csv and json

- add the xml source  [xml-source]
    # done 00:29
    reader, field map (price in minor units), enable, usage, test
    scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```

### Round 1, Tuesday 2 (feeds-tuesday-prompt-2)

```
[2 other tool calls: reads and runs, no graphene]
$ cat validate/rules.py; graphene plan propose - <<'EOF'
goal: load northwind XML feeds through the same path as csv/json, prices already in cents
- add xml source  [xml-source]
  - xml reader, field map (minor unit), enable, usage/readme, test  [xml-leaf]
      scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
      check: python3 -m unittest discover -q tests
EOF
graphene node start xml-leaf
  > Exit code 1
  > A rule is (name, predicate). `check` returns the names of the rules a record failed; a record that
  > def check(record):
  > goal (proposed): load northwind XML feeds through the same path as csv/json, prices already in cents
  > proposed xml-source: add xml source
  > proposed xml-leaf: xml reader, field map (minor unit), enable, usage/readme, test
  > 2 proposed: nobody can start them until the person accepts, in `graphene watch`. Tell them the tree is ready, and stop
  > xml-leaf is a proposal: nothing to start until the person accepts it
  >   graphene plan accept xml-source (the person's)
[reply, cut] I've proposed the plan but haven't written any code. Graphene needs you to accept the plan before I can start. **Proposed plan (one leaf):** add an `xml` source for northwind. - **Reader:** a new `ingest/xmlfeed.py`, registered in `READERS`. It reads only `<product>` elements and skips the `<summary NW-TOTAL>` row. If it didn't, the day total would load as a product. - **Field map:** `code→sku`, `desc→name`, `price→price`, with `price_unit: "minor"` since northwind's prices are already in cents. - **Wiring:** enable `xml` in `config/defaults.py`, add it to the `USAGE` line in `cli/main.py` and to the README. `tests/test_contract.py` requires the usage line to name every enabled source. - **…
[run] 4 turns, $0.09, 14 s
```

Afterwards, `graphene plan --text`:

```
goal: load northwind XML feeds through the same path as csv/json, prices already in cents
# proposed with the tree: accepting any of it accepts this

? add xml source  [xml-source]
    # proposed by a Claude Code session (2c300d9e)
  ? xml reader, field map (minor unit), enable, usage/readme, test  [xml-leaf]
      # proposed by a Claude Code session (2c300d9e)
      scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
      check: python3 -m unittest discover -q tests
```

`git status --short`:

```
(clean)
```

### Round 1, Tuesday 3 (feeds-tuesday-tree-1)

```
[2 other tool calls: reads and runs, no graphene]
[Bash] for f in ingest/*.py normalize/*.py cli/main.py config/defaults.py tests/*.py validate/rules.py sink/jsonl.py…
  > (error) Part of this command (a variable) cannot be checked in advance
[14 other tool calls: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: Load northwind's XML feed through the same path as csv and json, with prices taken as cents already.
- Wire the xml source  [xml-feed]
    Add an xml reader that returns only <product> elements (not the <summary> day total), register it, map code/desc/price with price_unit minor, enable it, and name it in USAGE.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
EOF
graphene node start xml-feed
  > goal (proposed): Load northwind's XML feed through the same path as csv and json, with prices taken as cents already.
  > proposed xml-feed: Wire the xml source
  > xml-feed is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-feed` takes it
  >   goal:   Add an xml reader that returns only <product> elements (not the <summary> day total), register it, map code/desc/price with price_unit minor, enable it, and name it in USAGE.
  >   scope:  ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests` passes
  >   finish: graphene node done xml-feed   (runs the check and asks git what changed)
[Write] ingest/xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] README.md
[Write] tests/test_xmlfeed.py
$ python3 -m cli.main load samples/prices.xml --source xml && graphene node done xml-feed
  > xml-feed is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] Northwind's XML now loads like the csv and json feeds. `python3 -m cli.main load samples/prices.xml --source xml` prints three records, and the full test suite passes. - **Reader:** the new `ingest/xmlfeed.py` has `read_xml`, which is registered in `ingest/__init__.py`. It reads only `<product>` elements and gives back their attributes. - **Summary row:** the `NW-TOTAL` `<summary>` row is deliberately skipped. It's a day total in the same shape as a product, and loading it would have written a bogus 1749-cent "product". - **Prices:** `normalize/fields.py` maps `code`→sku, `desc`→name and `price`→price with the unit set to `minor`. The values go through as cents with no ×100, so `1299` stays…
[run] 28 turns, $0.20, 45 s
```

Afterwards, `graphene plan --text`:

```
goal: Load northwind's XML feed through the same path as csv and json, with prices taken as cents already.

- Wire the xml source  [xml-feed]
    # done 00:28
    Add an xml reader that returns only <product> elements (not the <summary> day total), register it, map code/desc/price with price_unit minor, enable it, and name it in USAGE.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```

### Round 1, Tuesday 4 (feeds-tuesday-tree-2)

```
[15 other tool calls: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: Load the northwind XML feed with the same load command and output as csv and json, treating its prices as already in cents.
- Wire an xml source end to end  [xml-source]
    Add an xml reader (product elements only, summary rows skipped), register it, enable it, map fields with price_unit minor, and cover it with a test.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
EOF
graphene node start xml-source
  > goal (proposed): Load the northwind XML feed with the same load command and output as csv and json, treating its prices as already in cents.
  > proposed xml-source: Wire an xml source end to end
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   Add an xml reader (product elements only, summary rows skipped), register it, enable it, map fields with price_unit minor, and cover it with a test.
  >   scope:  ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
[Write] ingest/xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] README.md
[Write] tests/test_xmlfeed.py
$ python3 -m cli.main load samples/prices.xml --source xml; graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] The northwind XML feed now loads with the same command and the same JSONL output as csv and json: ``` python3 -m cli.main load samples/prices.xml --source xml ``` The full test suite passes, and the sample file produces three records (widget at 1299, grommet & pin at 450, ask us at 0). - **Prices:** the XML source treats `price` as cents already, so 1299 stays 1299 and isn't multiplied by 100. - **Summary rows:** I skip the `<summary>` row (the `NW-TOTAL` day total) and read only `<product>` elements. Otherwise the total would load as a fake product. - **"ask us" at 0:** it loads like the other rows. Validation only rejects negative prices, so I left it alone. Say if you'd rather drop zero-…
[run] 26 turns, $0.19, 44 s
```

Afterwards, `graphene plan --text`:

```
goal: Load the northwind XML feed with the same load command and output as csv and json, treating its prices as already in cents.

- Wire an xml source end to end  [xml-source]
    # done 00:28
    Add an xml reader (product elements only, summary rows skipped), register it, enable it, map fields with price_unit minor, and cover it with a test.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```

### Round 1, the feeds paragraph

```
[1 other tool call: reads and runs, no graphene]
[Bash] for f in cli/main.py config/defaults.py ingest/__init__.py ingest/csvfeed.py ingest/jsonfeed.py normalize/*.p…
  > (error) Part of this command (a variable) cannot be checked in advance
[2 other tool calls: reads and runs, no graphene]
[Bash] cat > ingest/xmlfeed.py <<'EOF' """Northwind. XML: a <feed> of <product code= desc= price=/> elements, prices…
  > (error) PreToolUse:Bash hook error: plan first: this session holds no leaf, so it writes nothing yet. Propose what yo…
$ graphene plan propose - <<'EOF'
goal: Load Northwind XML via `load --source xml`, emitting the same JSONL records as csv/json.
risk: a zero-price rule added to validate/rules.py also drops zero-price csv/json rows  [r-zero]
    default: intended by the user ("every supplier"); the csv/json samples have no zero prices, so their output stays byte-identical
- xml source  [xml-source]
    reader, field map (minor units), enable, usage, zero-price rule, README, test
    scope: ingest/xmlfeed.py, ingest/__init__.py, config/defaults.py, cli/main.py, normalize/fields.py, validate/rules.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
EOF
graphene node start xml-source
  > goal (proposed): Load Northwind XML via `load --source xml`, emitting the same JSONL records as csv/json.
  > proposed xml-source: xml source
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   reader, field map (minor units), enable, usage, zero-price rule, README, test
  >   scope:  ingest/xmlfeed.py, ingest/__init__.py, config/defaults.py, cli/main.py, normalize/fields.py, validate/rules.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
[Bash] cat > ingest/xmlfeed.py <<'EOF' """Northwind. XML: a <feed> of <product code= desc= price=/> elements, prices…
  > (error) Contains brace with quote character (expansion obfuscation)
[Write] ingest/xmlfeed.py
[Write] tests/test_xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] normalize/fields.py
[Edit] validate/rules.py
[Edit] README.md
[Bash] python3 -m unittest discover -q tests 2>&1 | tail -5; python3 -m cli.main load samples/prices.xml --source xm…
  > (error) Part of this command (a variable) cannot be checked in advance
[Bash] python3 -m unittest discover -q tests 2>&1 | tail -5; python3 -m cli.main load samples/prices.xml --source xm…
  > (error) This Bash command contains multiple operations. The following part requires approval: tail -5; python3 -m cli…
[Bash] python3 -m cli.main load samples/prices.csv --source csv | md5; python3 -m cli.main load samples/prices.json …
  > (error) This Bash command contains multiple operations. The following parts require approval: md5; python3 -m cli.mai…
[2 other tool calls: reads and runs, no graphene]
[Bash] python3 -m cli.main load samples/prices.csv --source csv > /tmp/csv_new.out; python3 -m cli.main load samples…
  > (error) This Bash command contains multiple operations. The following parts require approval: python3 -m cli.main loa…
[2 other tool calls: reads and runs, no graphene]
[Bash] python3 -m cli.main load /dev/null --source xml; echo "rc=$?"
  > (error) This Bash command contains multiple operations. The following part requires approval: echo "rc=$?"
$ graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] `python3 -m cli.main load samples/prices.xml --source xml` now loads Northwind and writes the same JSONL records as csv and json. The full test suite passes (12 tests, including the new XML ones). The sample loads as two records: ``` {"name": "widget", "price_cents": 1299, "sku": "NW-1", "source": "xml"} {"name": "grommet & pin", "price_cents": 450, "sku": "NW-2", "source": "xml"} ``` Your price check holds: 1299 in the feed comes out as `price_cents: 1299`, i.e. £12.99. **What I changed** - **Reader:** `ingest/xmlfeed.py` is new and is registered in `ingest/__init__.py`. It reads only `<product>` elements, so the `<summary>` total line never becomes a record. Feed order is kept. - **Field …
[run] 27 turns, $0.31, 76 s
```

Afterwards, `graphene plan --text`:

```
goal: Load Northwind XML via `load --source xml`, emitting the same JSONL records as csv/json.

risk: a zero-price rule added to validate/rules.py also drops zero-price csv/json rows  [r-zero]
    default: intended by the user ("every supplier"); the csv/json samples have no zero prices, so their output stays byte-identical

- xml source  [xml-source]
    # done 00:29
    reader, field map (minor units), enable, usage, zero-price rule, README, test
    scope: ingest/xmlfeed.py, ingest/__init__.py, config/defaults.py, cli/main.py, normalize/fields.py, validate/rules.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
 M validate/rules.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```


## Round 2 transcripts, trimmed

### Round 2, Tuesday 1 (feeds-tuesday-prompt-1)

```
[3 other tool calls: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: load northwind XML (samples/prices.xml) via the same load command as csv and json, reading only product rows with prices in minor units
- Add xml source  [xml-source]
    reader, field map, enabled source, usage line, and a test, wired like csv and json
    scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
EOF
graphene node start xml-source
  > goal (proposed): load northwind XML (samples/prices.xml) via the same load command as csv and json, reading only product rows with prices in minor units
  > proposed xml-source: Add xml source
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   reader, field map, enabled source, usage line, and a test, wired like csv and json
  >   scope:  ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
[Bash] cat > ingest/xmlfeed.py <<'EOF' """Northwind send XML: a <feed> of <product code desc price/> elements, price…
  > (error) Contains brace with quote character (expansion obfuscation)
[Write] ingest/xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] README.md
[Write] tests/test_xmlfeed.py
$ python3 -m cli.main load samples/prices.xml --source xml; graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] Northwind's XML now loads with the same command and the same JSONL output as csv and json: ``` python3 -m cli.main load samples/prices.xml --source xml ``` The sample gives three records, and the full test suite passes with the new tests included. - **Reader:** the new reader is `ingest/xmlfeed.py`, registered in `ingest.READERS`. It reads only the `<product>` elements. The `<summary>` row (`NW-TOTAL`, 1749) is a day total, so it's skipped. If it were loaded it would show up as a product. - **Prices:** Northwind's prices are already in cents (`1299` is 12.99), so the field map in `normalize/fields.py` marks them as `minor`. The csv and json feeds send decimals. - **Wiring:** I added `xml` t…
[run] 15 turns, $0.17, 37 s
```

Afterwards, `graphene plan --text`:

```
goal: load northwind XML (samples/prices.xml) via the same load command as csv and json, reading only product rows with prices in minor units

- Add xml source  [xml-source]
    # done 00:31
    reader, field map, enabled source, usage line, and a test, wired like csv and json
    scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```

### Round 2, Tuesday 2 (feeds-tuesday-prompt-2)

```
[2 other tool calls: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: load northwind XML feeds (prices already in cents) through the same path as csv and json
- wire the xml source  [xml-source]
    reader, field map (minor unit), enable it, usage line, README, test
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xml.py
    check: python3 -m unittest discover -q tests
EOF
graphene node start xml-source
  > goal (proposed): load northwind XML feeds (prices already in cents) through the same path as csv and json
  > proposed xml-source: wire the xml source
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   reader, field map (minor unit), enable it, usage line, README, test
  >   scope:  ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xml.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
$ cat > ingest/xmlfeed.py <<'EOF'
"""Northwind. One <feed> element with a <product> per line, every field an attribute.

The feed also carries <summary> elements, a day total in the same shape as a product. They are not
products and are skipped here, or the total would load as an item.
"""

import xml.etree.ElementTree as ET


def read_xml(text):
    return [dict(el.attrib) for el in ET.fromstring(text).iter("product")]
EOF
python3 - <<'EOF'
import re
def sub(p,a,b):
    s=open(p).read(); assert a in s; open(p,"w").write(s.replace(a,b,1))
sub("ingest/__init__.py","from ingest.jsonfeed import read_json\n","from ingest.jsonfeed import read_json\nfrom ingest.xmlfeed import read_xml\n")
sub("ingest/__init__.py",'"json": read_json}','"json": read_json, "xml": read_xml}')
sub("normalize/fields.py",'"major"},\n}','"major"},\n    "xml": {"keys": {"sku": "code", "name": "desc", "price": "price"}, "price_unit": "minor"},\n}')
sub("config/defaults.py",'("csv", "json")','("csv", "json", "xml")')
sub("cli/main.py","<csv|json>","<csv|json|xml>")
sub("README.md","Sources: csv, json.","Sources: csv, json, xml (northwind; prices already in cents).")
EOF
cat > tests/test_xml.py <<'EOF'
import io
import sys
import unittest

from cli.main import load
from normalize.fields import normalize


class Xml(unittest.TestCase):
    def test_a_product_normalises_without_rescaling_cents(self):
        raw = {"code": "NW-1", "desc": "widget", "price": "1299"}
        self.assertEqual(
            normalize("xml", raw),
            {"sku": "NW-1", "name": "widget", "price_cents": 1299, "source": "xml"},
        )

    def test_end_to_end_skips_the_summary_and_unescapes(self):
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            code = load(["samples/prices.xml", "--source", "xml"])
        finally:
            sys.stdout = real
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertEqual(len(out.strip().splitlines()), 3)
        self.assertNotIn("NW-TOTAL", out)
        self.assertIn("grommet & pin", out)


if __name__ == "__main__":
    unittest.main()
EOF
python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml && graphene node done xml-source
  > 
[1 other tool call: reads and runs, no graphene]
[Write] ingest/xmlfeed.py
[Write] tests/test_xml.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] README.md
$ python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml && graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] Northwind XML now loads like the csv and json feeds: `python3 -m cli.main load samples/prices.xml --source xml`. All 7 tests pass, including 2 new ones for xml. I didn't commit anything. - **Reader:** `ingest/xmlfeed.py` is registered in `READERS`. It only reads `<product>` elements. The sample also has a `<summary code="NW-TOTAL">` day-total row in the same shape, and loading that as an item would add a bogus 1749-cent product, so it's skipped. - **Field map:** `code`, `desc` and `price` map to `sku`, `name` and `price`, with `price_unit: "minor"`. Since their prices are already cents, they are not multiplied by 100. `&amp;` comes through as `&`. - **Wiring:** xml is added to `ENABLED_SOUR…
[run] 15 turns, $0.16, 36 s
```

Afterwards, `graphene plan --text`:

```
goal: load northwind XML feeds (prices already in cents) through the same path as csv and json

- wire the xml source  [xml-source]
    # done 00:31
    reader, field map (minor unit), enable it, usage line, README, test
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xml.py
    check: python3 -m unittest discover -q tests
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
?? ingest/xmlfeed.py
?? tests/test_xml.py
```

### Round 2, Tuesday 3 (feeds-tuesday-tree-1)

```
[3 other tool calls: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: Load northwind's XML feed (prices already in cents) through the same path as csv and json.
- Wire up the xml source  [xml-source]
    Add an xml reader, field map with minor price unit, enable it, update usage and README, add tests.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
EOF
graphene node start xml-source
  > goal (proposed): Load northwind's XML feed (prices already in cents) through the same path as csv and json.
  > proposed xml-source: Wire up the xml source
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   Add an xml reader, field map with minor price unit, enable it, update usage and README, add tests.
  >   scope:  ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
$ cat > ingest/xmlfeed.py <<'EOF'
"""Northwind's feed: a <feed> of <product code desc price/> elements, prices already in cents.

Only <product> is a record. The feed also carries a <summary> row with the day's total, which is
not a product and must not be loaded as one.
"""

import xml.etree.ElementTree as ET


def read_xml(text):
    return [dict(el.attrib) for el in ET.fromstring(text.strip()).iter("product")]
EOF
python3 - <<'EOF'
import re
def sub(p,a,b):
    s=open(p).read(); assert a in s,(p,a); open(p,"w").write(s.replace(a,b,1))
sub("ingest/__init__.py","from ingest.jsonfeed import read_json\n","from ingest.jsonfeed import read_json\nfrom ingest.xmlfeed import read_xml\n")
sub("ingest/__init__.py",'"json": read_json}','"json": read_json, "xml": read_xml}')
sub("normalize/fields.py",'''"price_unit": "major"},
}''','''"price_unit": "major"},
    "xml": {"keys": {"sku": "code", "name": "desc", "price": "price"}, "price_unit": "minor"},
}''')
sub("config/defaults.py",'("csv", "json")','("csv", "json", "xml")')
sub("cli/main.py","<csv|json>","<csv|json|xml>")
sub("README.md","Sources: csv, json.","Sources: csv, json, xml.")
EOF
cat > tests/test_xmlfeed.py <<'EOF'
import io
import sys
import unittest

from cli.main import load
from ingest import reader
from normalize.fields import normalize


class Xml(unittest.TestCase):
    def test_summary_row_is_not_a_record(self):
        with open("samples/prices.xml", encoding="utf-8") as fh:
            raw = reader("xml")(fh.read())
        self.assertEqual([r["code"] for r in raw], ["NW-1", "NW-2", "NW-3"])

    def test_price_is_already_cents(self):
        raw = {"code": "NW-1", "desc": "widget", "price": "1299"}
        self.assertEqual(
            normalize("xml", raw),
            {"sku": "NW-1", "name": "widget", "price_cents": 1299, "source": "xml"},
        )

    def test_end_to_end(self):
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            code = load(["samples/prices.xml", "--source", "xml"])
        finally:
            sys.stdout = real
        self.assertEqual(code, 0)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn('"name": "grommet & pin"', lines[1])
        self.assertNotIn("NW-TOTAL", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
EOF
graphene node done xml-source; python3 -m cli.main load samples/prices.xml --source xml
  > 
[Write] ingest/xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] README.md
[Write] tests/test_xmlfeed.py
$ graphene node done xml-source; python3 -m cli.main load samples/prices.xml --source xml
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] The northwind XML feed now loads like the csv and json ones. The full test suite passes, and `python3 -m cli.main load samples/prices.xml --source xml` prints three JSONL records. Nothing is committed. - **Reader:** the new `ingest/xmlfeed.py` is registered in `READERS`. It only treats `<product>` elements as records. - **Prices:** the xml field map in `normalize/fields.py` uses the `minor` price unit, so `1299` stays 1299 cents. - **Wiring:** I added `xml` to `ENABLED_SOURCES`, the CLI usage line and the README. The contract tests require all three. - **Tests:** `tests/test_xmlfeed.py` covers the reader, the cents handling and an end-to-end load. Two things in the sample you may want to lo…
[run] 15 turns, $0.17, 46 s
```

Afterwards, `graphene plan --text`:

```
goal: Load northwind's XML feed (prices already in cents) through the same path as csv and json.

- Wire up the xml source  [xml-source]
    # done 00:32
    Add an xml reader, field map with minor price unit, enable it, update usage and README, add tests.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```

### Round 2, Tuesday 4 (feeds-tuesday-tree-2)

```
[2 other tool calls: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: Load the northwind XML feed with `load <file> --source xml`, same output as csv/json, prices already in cents
- Wire the xml source end to end  [xml-source]
    Add an xml reader (product elements only, not the summary total row), register it, map code/desc/price with price_unit minor, enable it, name it in USAGE and README, add a test.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml
EOF
graphene node start xml-source
  > goal (proposed): Load the northwind XML feed with `load <file> --source xml`, same output as csv/json, prices already in cents
  > proposed xml-source: Wire the xml source end to end
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   Add an xml reader (product elements only, not the summary total row), register it, map code/desc/price with price_unit minor, enable it, name it in USAGE and README, add a test.
  >   scope:  ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
$ cat > ingest/xmlfeed.py <<'EOF'
"""Northwind: XML, one <product code= desc= price=/> per item under the root.

The feed also carries a <summary> row with the day's total. It is not a product, so only
<product> elements are read.
"""

import xml.etree.ElementTree as ET


def read_xml(text):
    root = ET.fromstring(text.encode("utf-8"))
    return [dict(el.attrib) for el in root.iter("product")]
EOF
python3 - <<'EOF'
import re
def sub(p,a,b):
    s=open(p).read(); assert a in s; open(p,'w').write(s.replace(a,b,1))
sub('ingest/__init__.py','from ingest.jsonfeed import read_json\n','from ingest.jsonfeed import read_json\nfrom ingest.xmlfeed import read_xml\n')
sub('ingest/__init__.py','"json": read_json}','"json": read_json, "xml": read_xml}')
sub('normalize/fields.py','"price_unit": "major"},\n}','"price_unit": "major"},\n    "xml": {"keys": {"sku": "code", "name": "desc", "price": "price"}, "price_unit": "minor"},\n}')
sub('config/defaults.py','("csv", "json")','("csv", "json", "xml")')
sub('cli/main.py','<csv|json>','<csv|json|xml>')
sub('README.md','Sources: csv, json.','Sources: csv, json, xml.')
EOF
cat > tests/test_xmlfeed.py <<'EOF'
import io
import sys
import unittest

from cli.main import load
from normalize.fields import normalize


class Xml(unittest.TestCase):
    def test_price_is_already_cents(self):
        raw = {"code": "NW-1", "desc": "widget", "price": "1299"}
        self.assertEqual(
            normalize("xml", raw),
            {"sku": "NW-1", "name": "widget", "price_cents": 1299, "source": "xml"},
        )

    def test_end_to_end_skips_the_summary_row(self):
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            code = load(["samples/prices.xml", "--source", "xml"])
        finally:
            sys.stdout = real
        self.assertEqual(code, 0)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertNotIn("NW-TOTAL", buf.getvalue())
        self.assertIn('"name": "grommet & pin"', buf.getvalue())


if __name__ == "__main__":
    unittest.main()
EOF
python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml && graphene node done xml-source
  > 
[Write] ingest/xmlfeed.py
[Write] tests/test_xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] README.md
$ python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml && graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] The Northwind XML feed now loads with the same command and the same JSONL output as csv and json: ``` python3 -m cli.main load samples/prices.xml --source xml ``` The full test suite passes (7 tests, including 2 new ones), and the Graphene check passed. - **Prices:** they're read as cents (`price_unit: minor`), so `1299` comes out as `price_cents: 1299`, with no ×100. - **Summary row:** the feed's `<summary code="NW-TOTAL">` row is skipped. The reader takes only `<product>` elements. Otherwise the day total would load as a fake product. - **`NW-3` ("ask us", price 0):** it still loads. Validation only rejects negative prices. If you don't want zero-price items, that's a separate rule. - **F…
[run] 14 turns, $0.16, 33 s
```

Afterwards, `graphene plan --text`:

```
goal: Load the northwind XML feed with `load <file> --source xml`, same output as csv/json, prices already in cents

- Wire the xml source end to end  [xml-source]
    # done 00:31
    Add an xml reader (product elements only, not the summary total row), register it, map code/desc/price with price_unit minor, enable it, name it in USAGE and README, add a test.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```

### Round 2, the feeds paragraph

```
[2 other tool calls: reads and runs, no graphene]
[Bash] cat legacy/priceimport.py | head -50
  > (error) Part of this command (a variable) cannot be checked in advance
[1 other tool call: reads and runs, no graphene]
[Bash] cat vendor/tinydec.py tests/*.py scripts/nightly.sh .gitignore; echo === samples; cat samples/prices.csv samp…
  > (error) Exit code 1 """Vendored from tinydec 0.2. Do not edit: re-vendor instead. `round_half_up` is wrong for negati…
[1 other tool call: reads and runs, no graphene]
$ graphene plan propose - <<'EOF'
goal: load Northwind XML via the existing load command with --source xml, same JSONL out
- add xml source end to end  [xml-source]
    reader, field map, enable, usage, zero-price rule, README, test
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, validate/rules.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
EOF
graphene node start xml-source
  > goal (proposed): load Northwind XML via the existing load command with --source xml, same JSONL out
  > proposed xml-source: add xml source end to end
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
  >   goal:   reader, field map, enable, usage, zero-price rule, README, test
  >   scope:  ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, validate/rules.py, README.md, tests/test_xmlfeed.py   (a write anywhere else is refused, and blocks `done`)
  >   done:   `python3 -m unittest discover -q tests` passes
  >   finish: graphene node done xml-source   (runs the check and asks git what changed)
[Bash] cat > ingest/xmlfeed.py <<'EOF' """Northwind send XML: a <feed> of <product code= desc= price=/> elements. On…
  > (error) This Bash command contains multiple operations. The following parts require approval: printf '', echo "exit $…
[1 other tool call: reads and runs, no graphene]
[Write] ingest/xmlfeed.py
[Edit] ingest/__init__.py
[Edit] ingest/__init__.py
[Edit] normalize/fields.py
[Edit] config/defaults.py
[Edit] cli/main.py
[Edit] validate/rules.py
[Edit] README.md
[Write] tests/test_xmlfeed.py
[1 other tool call: reads and runs, no graphene]
$ graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
  > next: nothing; every node is done
[reply, cut] Northwind's XML now loads with the same command and the same JSONL records as the other feeds: `python3 -m cli.main load samples/prices.xml --source xml`. The test suite passes (10 tests). I haven't committed anything. On the sample, the output is two records: - `{"name": "widget", "price_cents": 1299, "sku": "NW-1", "source": "xml"}` - `{"name": "grommet & pin", "price_cents": 450, "sku": "NW-2", "source": "xml"}` The 1299 comes out as 1299 cents, which is £12.99. The csv sample loads exactly as before. Here is where each piece went: - **Reader:** the new `ingest/xmlfeed.py` is registered in `ingest/__init__.py`. It reads only `<product>` elements, so the trailing `<summary>` total can nev…
[run] 21 turns, $0.24, 56 s
```

Afterwards, `graphene plan --text`:

```
goal: load Northwind XML via the existing load command with --source xml, same JSONL out

- add xml source end to end  [xml-source]
    # done 00:32
    reader, field map, enable, usage, zero-price rule, README, test
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, validate/rules.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests
```

`git status --short`:

```
 M README.md
 M cli/main.py
 M config/defaults.py
 M ingest/__init__.py
 M normalize/fields.py
 M validate/rules.py
?? ingest/xmlfeed.py
?? tests/test_xmlfeed.py
```

