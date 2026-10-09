# The numbers to beat

Written at 00:40 on 9 October, before any change, from the timeline night's records:
`dev/process/timeline/after.md` and `takes.md`. Nothing here was run again.

## 1. The Nemotron planner's proposal rate

From `after.md`, round 3, on the nodes-first schema (build `674b32c`), ten asks on feeds and ten on
report, Ultra planning, each ask one start with at most two answers, the second after Graphene's one
send-back with its refusal.

- **By ask, with its one send-back: 15 of 20 (75%).** Feeds 6 of 10, report 9 of 10.
- **By answer: 15 of 30 (50%).**

Why the five missed, from the table: two leaves writing one path (feeds 3, feeds 9, report 5), a board
question written among the nodes (feeds 4), a node that named itself as its parent (feeds 5). The
validator said one fault at a time, so an answer with two faults ended the ask after the send-back.
Tonight's target is 80% by ask: 16 of 20, measured the same way, 20 asks on feeds and 20 on report.

## 2. Trees that stopped on another leaf's file

From `after.md`: **4 of 13 trees stopped on another leaf's file**, 1 of them a test file. The four:

| tree | leaf | the file | what happened |
|---|---|---|---|
| statements 2 | `verify` | `tests/test_dunning.py`, `usd-pin`'s | the owner left a stale figure (`-40.13` half-up); `verify` already waited on it |
| take 1 (Nemotron, feeds) | `test-xmlfeed-e2e` | `ingest/xmlfeed.py`, `xmlfeed-reader`'s | the tests leaf found the reader's field names wrong |
| take 2 (Nemotron, report) | `text-regress` | `app/report.py`, `json-fmt`'s | Nano asked for a file another leaf had already landed |
| take 3 (Nemotron, feeds) | `test-xmlfeed` | `ingest/xmlfeed.py`, `xmlfeed`'s | the tests leaf found price 0 not skipped |

**Lane 1's test cases are takes 1 and 3:** an integration leaf came back saying a landed leaf's work is
wrong, and the only way to act on it was a person typing the hidden `graphene node reopen` on the owner.
Statements 3's `signoff-run` came back for two test files no scope held (a scope too narrow); statements
2's stale figure was in a file the owner held. Neither was catchable by reading the check's words.

## 3. Width

**Not measured.** No record from the timeline night or before says how many lanes ran at one instant, or
what share of the agents' minutes had one lane running. Lane 4 computes it from the log's rows, and the
before is measured on last night's four recordings (`tests/recordings/timeline-claude.jsonl`,
`timeline-nemotron-take-6.jsonl`, `meter-claude.jsonl`, `meter-nemotron-take-11.jsonl`) before any run
tonight, in `after.md`.

## 4. Loops closed

**0.** No run on record reopened the owner of a fault a came-back leaf found and ran the tree to the end.

## What tonight compares against these

1. Lane 3: 20 asks on feeds and 20 on report, Ultra, counted the same way, against 15 of 20.
2. Lane 1: feeds on Nemotron and on Claude Code until a tests leaf comes back on a landed leaf's fault,
   then `r`, then `R`: loops closed, attempts per owner, dollars per loop.
3. Lane 2: the statements task three times, feeds twice, and one planted whole-suite check, with
   precheck on: what it flagged, and whether a flagged check would have come back later.
4. Lane 4: width on every run tonight and on last night's four recordings.
