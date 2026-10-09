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
| nemotron 2 | Ultra | Nano | `f7a9697` | 2 | (running) | | | | |
| nemotron 3 | Ultra | Nano | `f7a9697` | 1 (`explore`) | 1 | none | | no work was planned | 0.07 |
| claude 1 | Sonnet | Sonnet | `f7a9697` | 2 | 2 | none | | | 0.30 + 0.11 |
| claude 2 | Sonnet | Sonnet | `f7a9697` | 2 | 2 | none | | | 0.29 + 0.11 |
| claude 3 | Sonnet | Sonnet | `f7a9697` | 3 | 3 | none | | | 0.44 + 0.11 |

(continued as the runs end)

## 2. Red first (lane 2, purpose `precheck`)

(as the runs end)

## 3. The Nemotron planner (lane 3, purpose `planner`)

(after lane 3 lands)

## 4. Width (lane 4)

(after lane 4 lands)
