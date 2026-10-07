# Lane 1 evidence: plan first auto, decided by the proposal

Run on 7 October between 00:19 and 00:45, on branch `meter`, as five rounds of the same five messages.
Each session ran Graphene from a wheel of the branch, installed as a tool, never editable.

## What ran

- `dev/test/auto_live.py`: each message in a fresh feeds repo (`make_task.py feeds`), then `graphene init
  --planner claude --executor claude` as the person (no agent's mark), then one Claude Code session with
  the 23 September model and tools (Sonnet), `--setting-sources project,local` and `--max-budget-usd 1.5`.
  Every session is on the night's ledger, purpose `auto`. The five of a round run at once.
- The four Tuesday messages were written tonight from their one-line descriptions in
  `dev/process/cut/lane5-evidence.md`. The 23 September originals live only in Claude Code's transcript
  store, which this run did not read. The paragraph is `dev/test/tasks/feeds/paragraph.md`, 324 words.

## The rule

Under `auto` the agent proposes every ask before it writes. The proposal decides whether the person is
asked first: one leaf, with no board item and a scope of at most 8 paths, is the person's at once.
Anything else waits in `graphene watch`. The agent's instruction (`gate.AUTO`) no longer asks it to judge
the size or to leave out board items and sub-goals.

## What happened

Rounds A and B ran lane 1 as first built. It counted the proposal's nodes, so a leaf that came in under a
sub-goal of its own waited. Rounds C, D and E count leaves (`c0d8379`). A sixth round, after C, stopped
at its first repo: the harness ran from the clone while the move to `dev/` was merged into it. Rounds D
and E ran from a snapshot.

| message | A | B | C | D | E |
|---|---|---|---|---|---|
| Tuesday 1 | taken, done | taken, done | waited: board item | waited: board item | waited: board item |
| Tuesday 2 | waited: board item | waited: sub-goal | taken, done | taken, done | taken, done |
| Tuesday 3 | waited: sub-goal | waited: sub-goal | taken, done | taken, done | taken, done |
| Tuesday 4 | waited: sub-goal | waited: sub-goal + board item | waited: board item | taken, done | taken, done |
| paragraph | waited: sub-goal, 8 paths | waited: sub-goal, 8 paths | one leaf, taken, done | a tree of 3 leaves, waited | one leaf, taken, done |

Rounds C to E in numbers: every Tuesday leaf that was taken passed 15 of 20 acceptance checks and 11 of 12
held-out ones. Both paragraph leaves passed 18 of 20 and 12 of 12. The misses are the change of mind no run
sends and, for Tuesday, the zero-price rule its messages never mention. A session cost $0.09 to $0.30.

Every single leaf proposed, in all five rounds, reached exactly 8 paths (`gate._width`). Tuesday's: `ingest/**` (three tracked files), four more tracked files
and one new test file. The paragraph's single leaves reached 8 too: six tracked files and two new ones.

## What it means

- **The Tuesday half holds, with the board as the reason it doesn't always.** In rounds C to E, 8 of 12
  Tuesday asks were the person's at once and done. The 4 that waited each put up a board item, such as
  "NW-3 'ask us' has price 0; keep it as a 0-cent record?" That is the rule working: a question the agent
  could not settle reaches the person before the work.
- **The paragraph half holds once in three.** Round D proposed a tree, which waited. In C and E Sonnet
  proposed one leaf with no board item and 8 paths, and the rule took it at once. That is the finding:
  on this task the feeds paragraph and a Tuesday ask can make the same proposal. No scope threshold
  separates them, because both reach 8 paths. The instruction was not tuned to force a tree.
- **The threshold is 8 paths.** It is the width of a one-change ask in this repo: a reader, its
  registration, the field map, the config, the usage line, the README and a test. 7 would have stopped
  every Tuesday ask. 9 or more stops nothing more here. It lives in `gate.WIDE`, and `graphene plan first`
  says it.
- **The sub-goal wrapper was the old rule's blind spot.** In rounds A and B, 4 of 8 Tuesday asks waited
  only because the agent put its one leaf under a sub-goal of its own, and a fifth had a board item too. On 5 October the instruction said
  "no sub-goal" to steer agents round it. Now the code counts leaves.

## Transcripts, trimmed

From the sessions' own streams: the proposal, what Graphene answered, and the end.

### Tuesday 2, taken at once (round D)

```
$ graphene plan propose - <<'EOF'
goal: Load Northwind's XML price feed with `load <file> --source xml`, same output as csv/json, prices already in cents.
- Wire an xml source  [xml-source]
    Add reader reading only <product> elements (skip <summary> total), field map with price_unit minor, enable in config, usage and README.
    scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
    check: python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml
EOF
  > goal (proposed): Load Northwind's XML price feed with `load <file> --source xml`, same output as csv/json, prices already in cents.
  > proposed xml-source: Wire an xml source
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
$ graphene node start xml-source
…
$ python3 -m cli.main load samples/prices.xml --source xml && graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
[16 turns, $0.19, 43 s]
```

### Tuesday 1, waiting: it put up a board item (round D)

```
$ graphene plan propose - <<'EOF'
goal: Northwind XML price feed loads with `cli.main load samples/prices.xml --source xml`, same JSONL output as csv/json, skipping the <summary> total row.
question: Northwind's NW-3 "ask us" has price 0; keep it as a 0-cent record?  [q-zero]
    default: keep it (validation only rejects negatives, csv/json would keep it too)
    option: drop zero-price records for xml
    then: goal xml-wire + also drop records whose price is 0
- wire the xml source  [xml]
  - xml reader, field map, config, usage, test  [xml-wire]
      scope: ingest/**, normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py
      check: python3 -m unittest discover -q tests && python3 -m cli.main load samples/prices.xml --source xml | wc -l | grep -q 3
EOF
  > put up q-zero: Northwind's NW-3 "ask us" has price 0; keep it as a 0-cent record?
  > 2 proposed: it waits for the person: it put up a board item. Nobody can start it until the person accepts, in `graphene watch`. Tell them it waits, and stop
[6 turns, $0.12, 23 s]
```

### The paragraph as a tree, waiting (round D)

```
$ graphene plan propose - <<'EOF'
goal: Load Northwind XML via the existing load command with --source xml, emitting the same JSONL, plus a zero-price rule for all suppliers.
- XML source  [xml]
  - Wire the xml reader, field map (price already minor units), enablement and usage line  [wire]
      scope: ingest/xmlfeed.py, ingest/__init__.py, normalize/fields.py, config/defaults.py, cli/main.py
      check: python3 -m unittest discover -q tests
  - Drop zero-price records for every supplier in validate/rules.py  [zero]
      scope: validate/rules.py
      check: python3 -m unittest discover -q tests
  - Test and README  [docs]
      scope: tests/test_xmlfeed.py, README.md
      check: python3 -m unittest discover -q tests
      needs: wire, zero
EOF
  > 4 proposed: nobody can start them until the person accepts, in `graphene watch`. Tell them the tree is ready, and stop
[5 turns, $0.13, 26 s]
```

### The paragraph as one leaf, taken at once (round E)

```
$ graphene plan propose - <<'EOF'
goal: Load Northwind XML via the existing load command (--source xml), same JSONL out, with a zero-price rule for all suppliers.
- XML source  [xml]
  - Add reader, wire it in, add rule, README, test  [xml-source]
      scope: ingest/xmlfeed.py, ingest/__init__.py, config/defaults.py, normalize/fields.py, validate/rules.py, cli/main.py, README.md, tests/test_xmlfeed.py
      check: python3 -m unittest discover -q tests
EOF
  > xml-source is accepted, as the person's: one leaf for what they asked in this session is theirs at once. `graphene node start xml-source` takes it
$ graphene node start xml-source
…
$ graphene node done xml-source
  > xml-source is done (check passed, nothing outside its scope)
[22 turns, $0.30, 70 s]
```
