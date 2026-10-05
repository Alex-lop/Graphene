# Pre-registration: the statements task, with Alex as the person

*Written and committed on 2026-10-05, before any run of this task with a model. The only runs so far
are the scripted rehearsal (`rehearsal-statements.md`), which called no model. Every table below is
empty on purpose. Once the first run starts, this file is not edited. Anything learned later goes in
the results file, marked as after the fact.*

## The question

*On a long task in a repo with things you must not touch, does the tree show the person the wrong
inferences before code runs, and trip fewer traps, for no more of the person's own clocked time?*

The 23 September test used a 2-leaf, 2-minute task and stand-ins for the person. The paragraph won
every attention measure with the same outcome. This task is built for the case the thesis is about:
a 1,328-line service, five traps, three executors at once, and the person away while they work.

## What is fixed before any run

- **The paragraph**: `docs/test/tasks/statements/paragraph.md`, 246 words, blob `ee677895af94`.
  Both arms open with it, byte for byte.
- **The card**: `intent.md`, blob `f755d3cf168e`. Alex reads it once before run 1 and keeps it
  beside him. He reads nothing else in `docs/test/tasks/statements/`, and never the repo before the
  opening is sent.
- **The repo**: `make_task.py statements`, fresh for every run. `git log docs/test/make_task.py`
  shows any change to it after this commit, and a run on a changed repo is void.
- **The checks**: `accept.py` (24 checks, blob `7a3676ec6e8c`), `quality.py` (12 held-out inputs,
  `af2fa5df291b`) and `traps.py` (5 traps, `acd78efd127d`). The reference patch passes all 36 with
  0 traps; the trip-all patch scores 5 (`docs/test/test_statements.py`).
- **The build**: one graphene wheel for all four runs. newrun.sh prints its path and version, and
  they go in each run's notes.
- **The executor**: Claude Code, `claude -p` with the flags in `PROVE.md`, the same model in every
  call of both arms. In the tree arm the planner is a Claude Code session in the repo with plan first
  on, and the executors are `graphene run --parallel 3` with the same flags.

## The arms

| arm | who plans | who does the work | the person's part |
|---|---|---|---|
| **Tree** | a Claude Code session in the repo, plan first on: it puts up the board and proposes the tree | `graphene run --parallel 3`, one Claude Code executor a leaf, each in its own worktree | sends the paragraph; answers the board and prunes for up to ten minutes; runs; leaves |
| **Paragraph** | nobody | one Claude Code session, Graphene's hooks removed (`rm .claude/settings.local.json`) | sends the paragraph, plus up to ten minutes of writing more in the same message; leaves |

## Runs

Two runs an arm, four in all, one at a time, in the order **P1, T1, T2, P2**. Alex learns the repo as
he goes, so each arm gets one early run and one late one.

## The person's budget, clocked

- **The start.** `log clock start` before anything. The tree arm's ten minutes run from the moment
  the tree is on screen. The paragraph arm's ten minutes run from `start`, and the extra writing
  goes in the opening message, after the paragraph. `log clock away` when the work starts.
- **Away.** No look at the screen until the run has ended. `snaps &` takes a snapshot a minute.
- **The end.** `log clock back`, then review the diff against the card. One more round is allowed:
  in the tree arm, take a leaf's offer or reopen it and run once more; in the paragraph arm, one
  follow-up message. Each round is clocked, `away` and `back` again. `log clock done` at the end.
- No other message. What Alex would have corrected goes in the run's `notes.md`.

The clock format is the run log's `clock` entry (`logline.py`): its text is `start`, `away`, `back`
or `done`, and its time is when it was logged. Person minutes at the start are `start` to the first
`away`. At the end they are every `back` to the next `away` or `done`, added up.

## What is counted, for every run

`docs/test/prove.py count <run-dir>` runs `tally.py` with the three checks and writes `tally.json`.

| metric | from | notes |
|---|---|---|
| traps, 0 to 5 | `traps.py` on the final state | a script, never a judge |
| minutes to the first visible wrong inference | `tally.py --traps` | from the opening prompt; see below |
| person minutes, start and end | the clock entries | clocked, never modelled |
| tree read minutes | the plan's log | the tree's proposal to the first accept; tree arm only |
| board items, and those naming a conflict | the plan's store | words: round, half, legacy, monthly, v1, export, shape, vendor, decimalfmt, migrat |
| accept, held-out | `accept.py`, `quality.py` | passed of 24 and of 12 |
| dollars | `claude -p` JSON: the run log and `.graphene/runs/` | an unpriced call makes the run's dollars unknown, never $0 |
| wall minutes | the run log, first entry to last | |

A wrong inference is a trap tripped, or a board default the person overrode. It is seen at the
earliest of: a node proposed with a scope that names `vendor/`, the protected test or a shipped
migration; an agent's board item whose default the person overrode, when it was put up; the first
commit or snapshot that shows a trap the final state also has. A run with none has no time.

The person never runs `accept.py`, `quality.py` or `traps.py`, and never opens the patches.

## Predictions, written before any run

Mine, the agent's that built the task:

- **Traps.** Paragraph: 1 a run (0 to 2), most likely the v1 shape or the monthly file. Tree: 1 a run
  (0 to 2), the same two. Vendor and the protected test stay at 0 in the tree arm, because a leaf
  cannot write outside its scope unless the planner put the path in it.
- **First wrong inference.** Tree: within 5 minutes in at least one run, if the board asks about
  rounding the monthly file. Paragraph: 15 to 60 minutes when a trap sticks, none otherwise.
- **Person minutes.** Tree: 8 to 12 at the start, 5 to 15 at the end. Paragraph: 1 to 5 at the start,
  5 to 15 at the end.
- **Correctness.** Both arms 18 to 24 of 24 on accept and 8 to 12 of 12 held-out.
- **Overall.** The paragraph arm ties or wins on traps and on person minutes. The tree wins on the
  first wrong inference, and only when its board names the rounding conflict. One session sees the
  whole repo and runs the whole suite, and the protected test fails the moment the monthly file's
  rounding changes. The tree splits the paragraph's constraints across leaf contracts, and each
  executor sees only its own.

Alex's, before run 1 (optional):

- Traps, tree / paragraph:
- First wrong inference, tree / paragraph:
- Person minutes, tree / paragraph:

## Hypotheses

- **H1, traps.** The tree arm trips fewer traps than the paragraph arm.
- **H2, when.** The tree arm's first wrong inference shows earlier than the paragraph arm's.
- **H3, attention.** The tree arm's person minutes, start plus end, are not higher than the paragraph
  arm's.
- **H4, rightness.** The tree arm passes at least as many accept and held-out checks.

## What would make the tree lose

Any one of these, and the results file says the tree lost on it:

1. **The planner misses the conflicts.** It read the repo and still put up no board item naming
   one, in both tree runs (`board (naming a conflict)` is 0 twice).
2. **The tree takes more than ten minutes to read.** `tree read minutes` is over 10 in either tree
   run.
3. **The paragraph arm trips no trap.** Both paragraph runs score 0.

## Analysis rules

1. Every run is in the table, in the order it was run, then the range. No mean without the runs
   beside it.
2. "Fewer", "earlier" or "higher" is said only when the ranges do not overlap. Anything else is
   *no difference shown at n = 2*. No significance test is run on two runs.
3. A hypothesis holds only if its comparison goes the registered way. A null result is reported, in
   the table and in the one sentence under it. H2 is *not tested* when no paragraph run has a wrong
   inference, and loss rule 3 then holds.
4. No rerun for a better number. A rerun only when the harness failed, named as an infrastructure
   rerun, with the failed run kept in the file.
5. A run is void only by a fairness rule of `PROTOCOL.md`, a changed blob above, or a changed repo.
   It stays in the file with its reason.
6. Nothing is tuned once the first run has started: not the paragraph, the card, a check, the repo
   or a flag.
7. Every number comes from `prove.py table` over the run directories. No number is typed.

## The table that will be reported

| run | arm | traps | tripped | first wrong (min) | how it showed | person min (start, end) | tree read min | board (naming a conflict) | accept | held-out | dollars | wall min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | paragraph | | | | | | n/a | n/a | | | | |
| T1 | tree | | | | | | | | | | | |
| T2 | tree | | | | | | | | | | | |
| P2 | paragraph | | | | | | n/a | n/a | | | | |

| hypothesis or loss rule | result (holds / does not hold / no difference shown / not tested) |
|---|---|
| H1 | |
| H2 | |
| H3 | |
| H4 | |
| loss 1: the board misses the conflicts | |
| loss 2: the tree takes over ten minutes to read | |
| loss 3: the paragraph arm trips no trap | |

Under the tables: one sentence on what they show, whatever it is.
