# The numbers, after

Run on 9 October from 00:44, each run on a wheel of the branch installed as a tool, named by the commit it was
built from. Counted the way `before.md` counts. Every run's ledger rows are on the night's ledger under the purpose
named. The raw material (each run's repo, store, log, recording and screens) stayed in the run's scratch directory;
what a run printed is quoted here.

## 7. The dogfood first (lane 7, purpose `dogfood`)

Lanes 1 and 2 were built through Graphene itself: one tree of five leaves proposed as text (`graphene plan propose -`,
the planner's seat), plan first on, accepted as the person, run with four Sonnet executors at once in worktrees, the
meter on, the time view shot every minute (`screens/dogfood-mid-80.txt`, `dogfood-after-80.txt`).

| leaf | files | landed | attempt | $ |
|---|---|---|---|---|
| r-told | run.py, nemotron/executor.py, a test | 00:46 | 1 | 0.20 |
| r-offer | plan.py, a test | 00:47 | 1 | 0.47 |
| rows | tui.py, node_record.py, a test | 00:47 | 1 | 0.53 |
| precheck-core | precheck.py (new), nemotron/precheck.py, a test | 00:47 | 1 | 0.55 |
| wire | plan_cli.py, a test | 00:50 | 1 | 0.33 |

**5 of 5 landed on their first attempt. 12 agent-minutes, 310 s of wall time, $2.07 at list price. Width 4 of 5:
four leaves side by side, then `wire`, which waited on two of them.** `r` was not used on Graphene itself: no leaf
came back. What the executors wrote was then read by two skeptics a leaf (the review's findings and fixes are
below) and by me. One fault found by the scripted loop, not by the review: after `r`, a leaf that already waited on
the owner still read as "came back", so `R` left it alone; fixed at `f7a9697`.

## 1. Loops closed (lane 1, purpose `reopen`)

The feeds task, end to end, with one key on every leaf that came back (`loop_take.py`: `r` when offered, else
`w`), and the run again, up to three rounds; each run recorded for `graphene demo`.

### The scripted loop, first, at $0

`scripted-loop.sh`: a reader leaf lands `FIELDS = ["sku", "nam", "price"]`; the tests leaf, which waits on it,
fails on the name and releases with `--wants reader.py`; the offers are `w`, `b` and `r`; `r` reopens the reader
with the note `came back from tests: the reader's field names are wrong (nam, not name)…` and the tests leaf waits
on it; the next `graphene run` says `reader: its check passes at the base commit f116a79: it proves nothing`, runs
the reader again (its executor's first line is the note), lands the fix as a new commit on top, and runs the tests
leaf, which passes. `node show reader` ends with `reopened … (reopened after landing; the fix is a new commit)`.
Transcript: `live/scripted-1.txt` in the run's scratch directory, quoted in `lane1-evidence.md`.

### Live

| run | planner | executors | build | leaves | landed | came back | key pressed | loop closed | $ |
|---|---|---|---|---|---|---|---|---|---|
| nemotron 1 | Ultra | Nano | `f7a9697` | 4 | 4 | `xml-config`, for the pruned `cli/main.py` | w | no tests leaf | 0.21 |
| nemotron 2 | Ultra | Nano, Super on a retry | `f7a9697` | 2 | 2 | `xml-feed` (w), `xml-test` (w), then `xml-test` on `xml-feed`'s landed fault | w, w, **r** | **yes, natural** | 0.16 + 0.23 |
| nemotron 3 | Ultra | Nano | `f7a9697` | 1 (`explore`) | 1 | none | | no work was planned | 0.07 |
| claude 1 | Sonnet | Sonnet | `f7a9697` | 2 | 2 | none | | | 0.30 + 0.11 |
| claude 2 | Sonnet | Sonnet | `f7a9697` | 2 | 2 | none | | | 0.29 + 0.11 |
| claude 3 | Sonnet | Sonnet | `f7a9697` | 3 | 3 | none | | | 0.44 + 0.11 |
| claude, planted 3 | Sonnet | Sonnet | `fa0ddc7` | 2, then `e2e-xml` | 3 | `e2e-xml` on the planted fault in `xml-source`'s landed file | **r** | **yes, planted at 01:13:42** | 0.78 |
| claude 4, 5 | Sonnet | Sonnet | `7ce64e4` | 2, 2 | 2, 2 | none | | (lane 2's feeds twice) | 0.29 + 0.10 each |

**Loops closed: 2 live (one natural, one planted) and the scripted one; owners reopened: 1 a loop; attempts per
owner: 1; dollars per closing round: $0.0228 (Nemotron) and $0.238 (Claude Code).** The transcripts, cut to the
moves: `lane1-evidence.md`. The recordings: `tests/recordings/loop-nemotron-2.jsonl`, `loop-claude-3.jsonl`.

## 2. Red first (lane 2, purpose `precheck`)

Every run tonight ran each accepted leaf's check once at the base commit before anything started (`red first: N
checks at <base> in S s` is the run's line). The verdicts a run prints: *passes* (the check exits 0 before any
work: it proves nothing) and *outside* (a red whose failure names a path no scope of the leaf covers); a red for
the leaf's own reason says nothing.

### The statements task, three practice runs on the first rule (build `f7a9697`)

`statements_practice.py`, the 23 September harness, `--parallel 3`, Sonnet planning and doing the leaves.

| run | leaves | landed | came back | flagged | passes at base | outside | wall time of the precheck |
|---|---|---|---|---|---|---|---|
| statements 1 | 9 | 1 | 2 (`round`, `ledger`: scopes too narrow) | 8 of 9 | 0 | 8 | 1 s |
| statements 2 | 8 | 7 | 1 (`verify`) | 6 of 8 | 2 (`rounding`, `verify`) | 4 | 3 s |
| statements 3 | 11 | 10 | 1 (`e2e`) | 8 of 11 | 0 | 8 | 1 s |

**The first rule flagged almost every leaf as *outside*:** a check such as `python3 -m unittest
tests.test_currency_migration tests.test_db` names an existing test file the leaf does not own beside its own new
one, and fails at the base because its own file is not there yet. That red is the leaf's own. Refined at
`9e38e71`: a red is *outside* when the failure's output names a path outside the scope, or when the command names
nothing of the leaf's own (a whole suite, another leaf's file); and a traceback's absolute path is read as the
tracked file it names (`fa0ddc7`).

**A flagged check that came back later:** statements 2's `verify` was flagged *passes at base: it proves
nothing* (its check was the whole suite as it stood), and `verify` came back after the other leaves landed:
"Full suite fails 2 tests that still expect half-up". The flag said, before anything ran, that the check could
not tell `verify`'s work from the others'. Statements 3's `e2e` came back the same way, on `tests/test_cli.py`
still expecting half-up; its check (`scripts/close_month.sh`) was flagged *outside*.

### Two more, on the refined rule (build `fa0ddc7`)

| run | leaves | landed | came back | flagged | passes at base | outside |
|---|---|---|---|---|---|---|
| statements b1 | 8 | 8 | 0 | 2 of 8 (`legacy-keep`, `e2e`) | 2 | 0 |
| statements b2 | 11 | 11 | 0 | 10 of 11 | 10 | 0 |

b2's planner gave ten leaves checks of existing tests alone (`python3 -m unittest tests.test_ledger`): each
passes at the base and proves nothing of the new work, and the run said so, one line a leaf, before it started.
Noise on the first rule: 22 of 28 leaves flagged over three runs; on the refined rule 12 of 19, every one a check
that passes at the base.

### Feeds twice on Claude Code, refined rule (`claude 4`, `claude 5`, build `7ce64e4`)

2 leaves each, both landed, nothing flagged (`red first: 2 checks at 70dbf7a in 1 s`), accept 18 of 20, held-out
12 of 12, $0.29 and $0.29. On the first rule `claude 1` had flagged `xml-source` for naming `tests/test_contract.py`
beside its own test: the refined rule reads that red as the leaf's own.

### The planted whole-suite check (`planted-1`, build `fa0ddc7`)

A feeds repo with `tests/test_zero.py` committed at the base and failing (a price of zero not skipped yet), owned
by `zero-rule`; and `xml-reader`, whose check is `python3 -m pytest -q` and whose scope excludes that file:

```
xml-reader: its check names normalize, tests/test_zero.py, normalize/fields.py, outside its scope, at 430348e
red first: 2 checks at 430348e in 1 s
```

**The whole-suite case is caught by behaviour: the flag names the file.** No word of the check named it; the
timeline night's `check_paths` could not have. (`normalize` and `normalize/fields.py` are named too: the failing
test's traceback imports them.)

### What it costs

The precheck's wall time per run: 0 to 3 s on these repos (one clean worktree a check, four at a time). The
statements runs: 1 s, 3 s, 1 s, 3 s; every feeds run: 0 or 1 s.

## 3. The Nemotron planner (lane 3, purpose `planner`)

(after lane 3 lands)

## 4. Width (lane 4)

Width is the most leaves with an executor's attempt running at one instant, over `[start, end)` to the
millisecond: an attempt that ends as another starts does not overlap it. Beside it, the share of agent minutes
spent with one attempt running alone. The bill line, `plan record` and the time view's note carry `width 2 of 3`
(`meter.width`, lane 4). Measured after the fact from each run's own store (`width_store.py`, the same function),
and on last night's recordings with `dev/process/loop/width.py`.

### The before: last night's four recordings

| recording | width | alone |
|---|---|---|
| `timeline-claude.jsonl` | 1 of 2 | 100% |
| `timeline-nemotron-take-6.jsonl` | 1 of 2 | 100% |
| `meter-claude.jsonl` | 1 of 2 | 100% |
| `meter-nemotron-take-11.jsonl` | 2 of 3 | 18% |

Three of the four shipped recordings ran one leaf at a time, whatever `--parallel` said: their trees were chains.

### Every run tonight

| run | width | alone | the shape |
|---|---|---|---|
| the dogfood (lanes 1 and 2, `--parallel 4`) | 4 of 5 | 20% | four leaves side by side, then `wire` |
| nemotron 1 | 2 of 4 | 68% | |
| nemotron 2 | 1 of 2 | 100% | the tests leaf waits on the reader |
| nemotron 3 | 1 of 1 | 100% | one `explore` leaf |
| claude 1, 2, 4, 5 | 1 of 2 | 100% | the wiring leaf waits on the zero rule |
| claude 3 | 2 of 3 | 50% | |
| claude planted 1, 3 | 1 of 3 | 100% | |
| planted suite | 2 of 2 | 20% | |
| statements 1 | 2 of 3 | 32% | |
| statements 2 | 3 of 8 | 36% | `--parallel 3` |
| statements 3 | 3 of 11 | 36% | `--parallel 3` |
| statements b1 | 2 of 8 | 55% | |
| statements b2 | 3 of 12 | 54% | |
| take 2 (report) | 2 of 3 | 73% | |
| take 4 (report) | 2 of 3 | 46% | |

**The honest line:** on the feeds task, with `--parallel 4` allowed, the planners' trees ran one or two leaves at
once in 10 of 11 runs, because the wiring leaf waits on the reader and the tests leaf on both: the repo's files
split that way. The statements task, eight subsystems and three executors, ran three at once; the dogfood, whose
five leaves owned five disjoint sets of files, ran four. Width is set by how the files split, not by the flag;
`docs/HOW_IT_WORKS.md` says so in one paragraph.
