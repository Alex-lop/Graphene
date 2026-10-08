# The numbers, after

Run on 8 October between 02:15 and 05:00, each run on a wheel of the branch installed as a tool. A build is named
by the commit it was built from; at 02:49 that history was folded into fewer commits with the same tree, and the
commits before the fold are on the branch `timeline-before-shape`, where every build named here resolves. Counted the way `before.md` counts. Every run's ledger rows are on
the night's ledger under the purpose named below. The raw material (each run's repo, store, log and screens)
stayed in the run's scratch directory; what a run printed is quoted here.

## 1. Hand-backs over another leaf's file (lane 1, purpose `scopes`)

The statements task at its doubled size, three practice runs one after another (`statements_practice.py`, the
23 September harness, a scripted stand-in, `--parallel 3`, Sonnet planning in a Claude Code session and doing
the leaves). Then the feeds task twice (`meter_live.py`, Claude Code's planner and executors on Sonnet).

| run | build | leaves | landed | came back | over another leaf's file | never ran | accept | held-out | $ |
|---|---|---|---|---|---|---|---|---|---|
| statements 1 | `4490656` | 10 | 10 | 0 | 0 | 0 | 20/24 | 8/12 | 2.76 + 0.33 |
| statements 2 | `ea8ae71` | 5 | 4 | 1 | 1, a test file | 0 | 19/24 | 8/12 | 1.37 + 0.30 |
| statements 3 | `20154b0` | 7 | 6 | 1 | 0 | 0 | 19/24 | 8/12 | 2.02 + 0.29 |
| feeds 1 | `4490656` | 3 | 3 | 0 | 0 | 0 | 18/20 | 12/12 | 0.50 + 0.11 |
| feeds 2 | `4490656` | 3 | 3 | 0 | 0 | 0 | 18/20 | 12/12 | 0.47 + 0.11 |

- **Statements 2:** `verify` came back. `tests/test_dunning.py` still pinned the half-up `-40.13`, and that file is
  `usd-pin`'s. `verify` already waited on `usd-pin`, so the order was right: the owner left a stale figure. The
  check rule cannot see that. It is counted, as `before.md` would count it.
- **Statements 3:** `signoff-run` came back for `tests/test_cli.py` and `tests/test_dunning.py`, which no leaf's
  scope held. A scope too narrow, not another leaf's file.
- **Graphene's check added nothing in these five runs.** The planning sessions read the new rule (in the session's
  instructions, `gate.TEACH`) and wrote plans that kept it: every leaf owned the test files it changed, and the leaf
  that ran the whole suite waited on the rest. No `waits on` line and no refusal appears in their transcripts.
- Last night, at the same size: run 2 stopped at 3 of 7 leaves with 3 never started; run 3 landed 6 of 9 with 2
  never started.

**Every tree that ran tonight, counted the same way: 13 trees, 4 stopped on another leaf's file, 1 of them a test
file. No leaf was left unrun.** Last night: 8 of 10 trees, 6 over a test file.

| tree | leaves | landed | over another leaf's file |
|---|---|---|---|
| statements 1, 2, 3 | 10, 5, 7 | 10, 4, 6 | statements 2: `tests/test_dunning.py`, a stale figure its owner left |
| feeds 1, 2 (Claude Code) | 3, 3 | 3, 3 | none |
| take 1 (Nemotron, feeds) | 4 | 3 | `ingest/xmlfeed.py`: the tests leaf found the reader's field names wrong |
| take 2 (Nemotron, report) | 3 | 2 | `app/report.py`: Nano asked for a file another leaf had already landed |
| take 3 (Nemotron, feeds) | 2 | 1 | `ingest/xmlfeed.py`: the tests leaf found price 0 not skipped |
| take 6 (Nemotron, report) | 2 | 2 | none |
| the recording, the GIF's run, two Tuesday asks | 2, 2, 1, 1 | 2, 2, 1, 0 | none (the Tuesday ask that came back met a Python 3.9 on my pane's PATH) |

What stops a tree now is different in kind: a tests leaf finding a fault in the code another leaf landed, which is
the check doing its job, not one leaf's check running a file another leaf had not written yet.

## 2. The Nemotron planner's proposal rate (lane 2, purpose `planner`)

`graphene ask` with `nemotron --steps 60` (Ultra), ten times on feeds (nemotron.sh's paragraph, the one the takes
used) and ten on report (`dev/test/tasks/report/paragraph.md`), each in a fresh repo, one after another.

### Round 1, the JSON planner as built

Build `4490656`. **10 proposals in 20 asks** (feeds 2 of 10, report 8 of 10); 41 strict answers, 12 of them stalled to the token limit; $4.90.

| task | ask | proposal | leaves | board | answers | stalled | $ | s | what Graphene said |
|---|---|---|---|---|---|---|---|---|---|
| feeds | 1 | no |  |  | 2 |  | 0.20 | 72 | line 28: option: is a question's; a risk has a default: at most |
| feeds | 2 | no |  |  | 2 |  | 0.15 | 107 | line 15: then: scope csvfeed-leaf + ingest/csvfeed.py names csvfeed-leaf, which is not a node in the plan |
| feeds | 3 | no |  |  | 2 |  | 0.35 | 88 | line 11: about: xml-feed, xml-test, which is not a node in the plan |
| feeds | 4 | no |  |  | 2 |  | 0.45 | 119 | line 35 [wiring]: wiring and sample-test both write tests/cli/test_main.py. A path has one leaf that writes it |
| feeds | 5 | yes | 2 | 2 | 2 |  | 0.30 | 203 | after a send-back: line 19 [xmlfeed]: xmlfeed and normalize both write normalize/fields.py. A path has one le |
| feeds | 6 | no |  |  | 3 | 1 | 0.32 | 92 | line 18: [validation-change-breaks-csv-json] is not an id: letters, digits, '-', '_' and '.', at most 32 |
| feeds | 7 | no |  |  | 2 |  | 0.51 | 137 | line 8: then: 'about xmlfeed' is not read; an effect is scope NODE + GLOB, check NODE: COMMAND, goal NODE + TE |
| feeds | 8 | no |  |  | 2 |  | 0.53 | 244 | line 4: then: goal validate-zero + "Reject price_cents <= 0 in validation for all sources" names validate-zero |
| feeds | 9 | no |  |  | 2 |  | 0.06 | 36 | line 8: then: scope normalize + normalize/fields.py names normalize, which is not a node in the plan |
| feeds | 10 | yes | 3 | 3 | 1 |  | 0.27 | 70 |  |
| report | 1 | yes | 3 |  | 2 | 1 | 0.10 | 48 |  |
| report | 2 | yes | 3 |  | 2 |  | 0.10 | 66 | after a send-back: line 11 [regress-text]: regress-text: a leaf needs a scope (the paths it may touch), e.g.  |
| report | 3 | no |  |  | 4 | 4 | 0.37 | 245 | its answers stalled to the token limit: no JSON to read |
| report | 4 | yes | 2 |  | 3 | 1 | 0.26 | 100 | after a send-back: line 2 [json-render]: json-render: its check runs tests/test_report_json.py, which test-js |
| report | 5 | yes | 4 | 2 | 1 |  | 0.22 | 121 |  |
| report | 6 | yes | 3 |  | 1 |  | 0.09 | 50 |  |
| report | 7 | no |  |  | 4 | 4 | 0.34 | 306 | its answers stalled to the token limit: no JSON to read |
| report | 8 | yes | 2 | 3 | 1 |  | 0.09 | 98 |  |
| report | 9 | yes | 2 |  | 2 | 1 | 0.12 | 67 |  |
| report | 10 | yes | 3 |  | 1 |  | 0.06 | 37 |  |

12 of the 41 answers stalled: Ultra closed the nodes, the schema asked for one more key (`says`, last), and it
wrote spaces to the token limit. Fixed (`674754d`): `says` first; and a board item's id the text cannot read
is made one it can (a handle nothing in the answer names).

### Round 2, `says` first

Build `674754d`. **12 proposals in 20 asks** (feeds 4 of 10, report 8 of 10); 34 strict answers, 5 of them stalled to the token limit; $4.83.

| task | ask | proposal | leaves | board | answers | stalled | $ | s | what Graphene said |
|---|---|---|---|---|---|---|---|---|---|
| feeds | 1 | yes | 3 | 1 | 1 |  | 0.05 | 32 |  |
| feeds | 2 | yes | 1 |  | 1 |  | 0.25 | 212 |  |
| feeds | 3 | no |  |  | 2 | 1 | 0.40 | 275 | line 16: parent: 'plan' is not the id of a node, in this text or in the plan |
| feeds | 4 | no |  |  | 3 | 1 | 0.36 | 109 | line 11: about: validate/rules, which is not a node in the plan |
| feeds | 5 | yes | 1 |  | 1 |  | 0.25 | 147 |  |
| feeds | 6 | no |  |  | 2 |  | 0.23 | 62 | line 7: then: scope xmlfeed-leaf + ingest/xmlfeed.py names xmlfeed-leaf, which is not a node in the plan |
| feeds | 7 | no |  |  | 2 |  | 0.36 | 125 | line 11: about: validation, which is not a node in the plan |
| feeds | 8 | no |  |  | 2 | 1 | 0.58 | 229 | line 31 [xml-reader]: xml-reader and xml-normalize both write ingest/__init__.py. A path has one leaf that wri |
| feeds | 9 | no |  |  | 2 |  | 0.09 | 60 | line 20 [xmlfeed-leaf]: xmlfeed-leaf and normalize-leaf both write normalize/fields.py. A path has one leaf th |
| feeds | 10 | yes | 3 |  | 1 |  | 0.25 | 160 |  |
| report | 1 | yes | 3 |  | 1 |  | 0.08 | 55 |  |
| report | 2 | yes | 3 |  | 2 |  | 0.10 | 53 | after a send-back: line 7 [test-json]: test-json and test-all both write tests/test_report_json.py. A path ha |
| report | 3 | yes | 2 |  | 2 |  | 0.23 | 121 | after a send-back: line 2 [report-json-impl]: report-json-impl: its check runs tests/test_report_json.py, whi |
| report | 4 | yes | 4 |  | 3 | 1 | 0.26 | 95 | after a send-back: line 6 [test-json]: test-json and full-suite both write tests/test_report_json.py. A path  |
| report | 5 | no |  |  | 2 |  | 0.31 | 98 | line 20: then: leaf leaf-verify-text under root names root, which is not a node in the plan |
| report | 6 | yes | 3 |  | 1 |  | 0.08 | 84 |  |
| report | 7 | yes | 3 |  | 1 |  | 0.08 | 35 |  |
| report | 8 | no |  |  | 3 | 1 | 0.51 | 149 | line 18 [json-leaf]: json-leaf: its check runs tests/test_report_json.py, which json-test-leaf writes after it |
| report | 9 | yes | 3 |  | 1 |  | 0.28 | 79 |  |
| report | 10 | yes | 2 | 1 | 1 |  | 0.08 | 43 |  |

Stalls fell to 5 of 34 answers; each now stops before another trailing key (`about`, `parent`, an option's
`then`). The most common refusal on feeds was a board line naming a node the answer had not given an id yet:
the schema asked for the board before the nodes. Fixed (`674b32c`): the nodes first.

### Round 3, the nodes before the board

Build `674b32c`. **15 proposals in 20 asks** (feeds 6 of 10, report 9 of 10); 30 strict answers, 3 of them stalled to the token limit; $4.43.

| task | ask | proposal | leaves | board | answers | stalled | $ | s | what Graphene said |
|---|---|---|---|---|---|---|---|---|---|
| feeds | 1 | yes | 5 | 3 | 1 |  | 0.26 | 182 |  |
| feeds | 2 | yes | 1 |  | 2 |  | 0.29 | 162 | after a send-back: line 19 [explore]: explore and test both write tests/test_xml_feed.py. A path has one leaf |
| feeds | 3 | no |  |  | 3 | 2 | 0.55 | 220 | line 2 [xml-feed]: xml-feed and xml-test both write tests/xmlfeed_test.py. A path has one leaf that writes it: |
| feeds | 4 | no |  |  | 2 |  | 0.33 | 117 | line 26: 'question: xml-source-name [xml-source]' is a new leaf with no scope and no check |
| feeds | 5 | no |  |  | 2 | 1 | 0.39 | 187 | line 27: parent: xml-feed is the node itself |
| feeds | 6 | yes | 4 |  | 1 |  | 0.52 | 138 |  |
| feeds | 7 | yes | 3 |  | 2 |  | 0.14 | 80 | after a send-back: line 6 [wire-xml]: wire-xml and zero-price-skip both write normalize/fields.py. A path has |
| feeds | 8 | yes | 5 |  | 1 |  | 0.09 | 57 |  |
| feeds | 9 | no |  |  | 2 |  | 0.30 | 137 | line 24 [field-map-xml]: field-map-xml and validate-price-zero both write normalize/fields.py. A path has one  |
| feeds | 10 | yes | 1 |  | 1 |  | 0.26 | 140 |  |
| report | 1 | yes | 3 |  | 1 |  | 0.07 | 37 |  |
| report | 2 | yes | 3 |  | 1 |  | 0.06 | 34 |  |
| report | 3 | yes | 3 |  | 1 |  | 0.42 | 91 |  |
| report | 4 | yes | 3 |  | 2 |  | 0.10 | 53 | after a send-back: line 11 [regression-test]: regression-test: a leaf needs a scope (the paths it may touch), |
| report | 5 | no |  |  | 2 |  | 0.09 | 45 | line 6 [json-tests]: json-tests and full-suite both write tests/test_report_json.py. A path has one leaf that  |
| report | 6 | yes | 2 |  | 2 |  | 0.10 | 48 | after a send-back: line 11 [text-unchanged]: text-unchanged: a leaf needs a scope (the paths it may touch), e |
| report | 7 | yes | 3 |  | 1 |  | 0.10 | 40 |  |
| report | 8 | yes | 3 |  | 1 |  | 0.07 | 34 |  |
| report | 9 | yes | 3 |  | 1 |  | 0.21 | 80 |  |
| report | 10 | yes | 2 |  | 1 |  | 0.06 | 30 |  |

No answer named a node it had not given an id: that refusal is gone. Three of the five misses are the new rule
refusing two leaves on one path, which would have collided at run time; one put a board question among the nodes;
one gave a node itself as its parent. The validator says one fault at a time, so an answer with two faults ends
the ask after the send-back.

**The proposal rate, counted two ways.** Last night an ask was one start of the planner and one answer; a take
asked at most twice, the second time with the refusal. Tonight an ask is one start with at most two answers, the
second after the refusal, in the same conversation.

| | last night | round 1 | round 2 | round 3 |
|---|---|---|---|---|
| per ask with its one send-back (a take last night) | 7 of 19 (37%) | 10 of 20 (50%) | 12 of 20 (60%) | **15 of 20 (75%)** |
| per answer | 7 of 34 (21%) | 10 of 41 (24%) | 12 of 34 (35%) | **15 of 30 (50%)** |

`before.md`'s number is the second row's: 7 in 34. Each round on its own build.

The ledger agrees: its `planner` purpose, $14.46, is the three rounds' $14.16, the stopped first start's $0.28
(02:18) and the schema probes' $0.02.

## 3. The feeds paragraph under `on` (lane 3, purpose `first`)

`auto_live.py --first on --only paragraph --rounds 3`: three Claude Code sessions on Sonnet, the 324-word paragraph.

| round | nodes | leaves | board items | waited for the person | wrote code | $ |
|---|---|---|---|---|---|---|
| 1 | 5 | 4 | 2 | yes | no | 0.11 |
| 2 | 7 | 4 | 1 | yes | no | 0.13 |
| 3 | 6 | 5 | 1 | yes | no | 0.12 |

**A tree, waiting for the person, 3 times in 3.** Under `auto` last night: a tree 1 time in 3, and twice one leaf
taken at once.

The Tuesday asks under `on` (one session each): tuesday-1 two leaves, tuesday-2 three, tuesday-3 three, tuesday-4
one; again, tuesday-4 two and tuesday-2 one. Under `on`, two of six were one leaf. Under `auto` last night, 8 of 12
were one leaf, taken at once.

**One row, `y`, done.** Tuesday-2's second session proposed one leaf with two board items. `graphene watch`
showed the two items and one row for the leaf, no goal row and no sub-goal; the status line said `waiting on you:
1 + 2 on the board`. On the leaf the keys line said `y accept and run`. `y` accepted it (the items took their
defaults) and started `graphene run --node xml-source`; it was done 40 seconds later, $0.35 (the executor was
Claude Code's default model). Screens: `screens/tuesday-*.txt`. The first try, on tuesday-4, came back: the tmux
pane I opened had macOS's Python 3.9 first on PATH, which the task's code does not run on. Nothing of Graphene's.

**The Claude Code planner's cost.** Each `graphene ask` on Claude Code now holds $1.50 on the ledger and settles
at what its stream says it cost: $0.1121, $0.1123 and $0.1015 tonight. Last night each was booked at $1.50.
