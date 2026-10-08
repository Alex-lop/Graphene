# The numbers, after

Run on 8 October between 02:15 and 05:00 on the `timeline` branch, each run on a wheel of the branch installed
as a tool (the build is named on each table). Counted the way `before.md` counts. Every run's ledger rows are on
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

## 2. The Nemotron planner's proposal rate (lane 2, purpose `planner`)

`graphene ask` with `nemotron --steps 60` (Ultra), ten times on feeds (nemotron.sh's paragraph, the one the takes
used) and ten on report (`dev/test/tasks/report/paragraph.md`), each in a fresh repo, one after another.

ROUND1

ROUND2

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
