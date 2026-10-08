# Lane 3 evidence: plan first on

Run on 8 October from 02:24 to 02:34, on wheels of this branch installed as tools (`dev/test/auto_live.py
--first on`, its sessions as on 6 October: Sonnet, the 23 September tools, `--max-budget-usd 1.5`, each on the
night's ledger under `first`). Each message in a fresh feeds repo after `graphene init --planner claude
--executor claude`, which now sets plan first `on`. Trimmed from each session's own record: the session's line,
the first line of its reply, and the plan it proposed (titles, scopes, checks, needs). Nothing was accepted by a
session: every proposal waited for the person.

## The paragraph, round 1

```
$ claude -p <paragraph> ... (4 turns, $0.11, 26 s)
reply: The plan is ready for you to prune in `graphene watch`. I haven't changed any files yet and will wait for your go-ahead.
goal: Northwind's XML price feed loads via `load <file> --source xml`, giving the same JSONL records as csv/json, with zero-price dropped for every supplier.
risk: ET.fromstring raises on an empty or blank file, which would be a traceback  [r-empty]
risk: the zero-price rule will also drop csv/json rows priced 0 (intended, "every supplier"); samples/prices.csv and prices.json have none, so their output is unchanged  [r-zero]
? XML source  [xml]
  ? Reader reads only product elements, in order  [reader]
      scope: ingest/xmlfeed.py, ingest/__init__.py
      check: python3 -c "from ingest import reader; r=reader('xml')(open('samples/prices.xml',encoding='utf-8').read()); assert [p['code'] for p in r]==['NW-1','NW-2','NW-3'] and reader('xml')('')==[]"
  ? Wire xml as an enabled source with prices in cents  [wire]
      scope: normalize/fields.py, config/defaults.py, cli/main.py
      check: python3 -m cli.main load samples/prices.xml --source xml | grep -q '"price_cents": 1299'
      needs: reader
  ? Drop zero-price records in the shared rules  [zero]
      scope: validate/rules.py
      check: python3 -c "from validate.rules import check; assert check({'sku':'a','name':'b','price_cents':0}) and not check({'sku':'a','name':'b','price_cents':1})"
  ? Test and README  [docs]
      scope: tests/test_xmlfeed.py, README.md
      check: python3 -m unittest discover -q tests
      needs: wire, zero
```

## The paragraph, round 2

```
$ claude -p <paragraph> ... (5 turns, $0.13, 30 s)
reply: The plan is ready to prune in `graphene watch`. I haven't changed any code yet. Nothing can start until you accept it.
goal: Northwind's XML price feed loads through the existing load command with --source xml, producing the same JSONL records as csv and json.
risk: the zero-price rule also drops zero-priced rows from csv and json feeds, as you asked; the current csv and json samples have none, so their output stays byte for byte the same  [r-zero]
? XML reader  [reader]
  ? Reader for Northwind XML  [xml-reader]
      scope: ingest/xmlfeed.py
      check: python3 -I -c "from ingest.xmlfeed import read_xml; print(read_xml(open('samples/prices.xml',encoding='utf-8').read()))"
? Wiring  [wiring]
  ? Register xml source  [xml-wire]
      scope: ingest/__init__.py, config/defaults.py, normalize/fields.py, cli/main.py, README.md
      check: python3 -m unittest tests.test_contract -q
      needs: xml-reader
  ? Reject zero price for every supplier  [zero-rule]
      scope: validate/rules.py
      check: python3 -m unittest tests.test_csvfeed -q
? Tests  [tests]
  ? Test xml source end to end  [xml-tests]
      scope: tests/test_xmlfeed.py
      check: python3 -m unittest discover -q tests
      needs: xml-wire, zero-rule
```

## The paragraph, round 3

```
$ claude -p <paragraph> ... (5 turns, $0.12, 28 s)
reply: The plan for the XML source is ready for you to prune in `graphene watch`. I haven't changed any files yet.
goal: Load Northwind's XML feed with the existing load command (--source xml) into the same JSONL records, and drop zero-price records for every supplier.
risk: a check that passes on nothing, e.g. the summary line or a zero price slipping through unnoticed  [r-checks]
? XML source  [xml]
  ? Reader: parse the feed, return only <product> elements' attributes in order (summary ignored; empty or blank feed gives [])  [reader]
      scope: ingest/xmlfeed.py, ingest/__init__.py
      check: python3 -c "from ingest import READERS; assert READERS['xml']('') == []; r = READERS['xml'](open('samples/prices.xml').read()); assert [p['code'] for p in r] == ['NW-1','NW-2','NW-3']"
  ? Wiring: enable xml, field map code/desc/price with price_unit minor (cents), usage line names xml  [wiring]
      scope: config/defaults.py, normalize/fields.py, cli/main.py
      check: python3 -m unittest tests.test_contract -q
      needs: reader
  ? Validation: new rule "price is not zero" in validate/rules.py, applying to all suppliers  [zero]
      scope: validate/rules.py
      check: python3 -c "from validate.rules import check; assert check({'sku':'a','name':'b','price_cents':0}); assert not check({'sku':'a','name':'b','price_cents':1})"
  ? Tests: tests/test_xmlfeed.py covering sample end to end, cents, summary excluded, zero dropped, missing fields skipped, entities, unicode, empty feed, order, and csv/json unchanged  [tests]
      scope: tests/test_xmlfeed.py
      check: python3 -m unittest discover -q tests
      needs: wiring, zero
  ? README: add xml to the sources list  [docs]
      scope: README.md
      check: grep -q "Sources: csv, json, xml" README.md
```

## Tuesday-2, the session that proposed one leaf

```
$ claude -p <tuesday-2> ... (4 turns, $0.10, 23 s)
reply: The plan is ready for you to prune in `graphene watch`. I haven't written any code yet.
goal: Add an "xml" source so `python3 -m cli.main load samples/prices.xml --source xml` loads Northwind's feed like csv/json do, with prices already in cents.
risk: The sample ends with a <summary> total row (NW-TOTAL, 1749) that is not a product; reading every child element would emit it as a fake product and double-count.  [r-summary]
question: Northwind's "ask us" item has price 0; csv/json would keep a 0 price (validation only rejects negatives).  [q-zero]
? Northwind XML source  [xml-feed]
  ? Reader, field map, wiring, docs and tests for xml  [xml-source]
      scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
      check: python3 -m unittest discover -q tests
```

## Tuesday-2 in `graphene watch`, then `y`

The screens are `screens/tuesday-1-proposed.txt` (one row for the leaf, two board items above it, `waiting on
you: 1 + 2 on the board`), `tuesday-2-on-the-leaf.txt` (the keys line says `y accept and run`),
`tuesday-3-after-y.txt` (`graphene run --parallel 4 --node xml-source: started`) and `tuesday-4-latest.txt`
(`1/1 done`, 40 seconds later). `tuesday-5-time-120.txt` is its time view.
