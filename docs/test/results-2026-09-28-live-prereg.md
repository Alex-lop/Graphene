# Pre-registration: the paragraph against the tree, live on Nemotron

*Written and committed on 2026-09-28, before any live data: no Token Factory call and no Sandbox has
run for this test, and no evidence run exists. It is item 2 of `docs/process/directives/WINNING_DIRECTIVE.md`.
Every table below is empty on purpose. Once the first evidence run starts, this file is not edited;
anything learned later goes in the results file, marked as after the fact.*

## The question

*Does a person who prunes the tree Nemotron 3 Ultra proposes, with Nemotron Nano doing the leaves,
get a correct result for less of their own attention than the same person sending the same paragraph
to Nano with no tree?* And, from the vision: *what is the person's prune worth?*

## What is fixed before any run

- **The paragraph.** One per task, written once by a stand-in from the card, before any repo was
  opened, and committed sealed beside the card. Every arm gets this text, byte for byte. Nobody who
  starts a run, tunes the executor or writes the analysis reads it (`docs/test/trees/README.md`).
- **The change of mind**, for the two cards that have one, written the same way and sent the same
  way in every arm, once the first part works.

  | task | paragraph (words, characters) | change of mind | git blob of the paragraph |
  |---|---|---|---|
  | feeds | 324, 1832 | `change.md`, 35 words | `2d28b53ce4e0` |
  | inventory | 277, 1606 | none on the card | `799c3f413397` |
  | logs | 216, 1267 | `change.md`, 58 words | `92b72aeeae02` |
  | report | 161, 959 | none on the card | `d0f33c77d317` |

  The cards are unchanged from `cb2ce54` (`intent.md` blobs `3600815c2ef5`, `7eb0a1c485fd`,
  `124ccd01c81a`, `5246e8172ac7`). A run whose paragraph, change or card blob differs from these is
  void.
- **The frozen configuration.** Tuning comes first, on fixed trees (`docs/test/trees/<task>.plan`,
  made as that README says, which needs the live planner), on feeds and inventory only. The
  configuration (executor prompt version, models by role, forks, escalation ladder, `--parallel`,
  `--rounds`, timeouts) is then frozen as a numbered decision in `docs/DIRECTION.md`, and every
  evidence run's row carries its graphene SHA and prompt version. Tuning rows never enter the table.
  No fixed tree exists at the time of writing.
- **Models** are resolved from the live list by role, never typed: Ultra plans, Nano executes, and
  the escalation ladder is whatever the frozen decision says.

## The arms

| arm | who plans | who does the work | the person's part |
|---|---|---|---|
| **A. The paragraph to Nano, no tree** | nobody | one Nemotron Nano session, with the executor's tools (view, edit, write, run), the whole repo in scope, no plan and no check deciding anything | the stand-in sends the paragraph, reads the reply and `git diff`, and may follow up as `PROTOCOL.md` allows |
| **B. Graphene** | Ultra proposes from the paragraph (`graphene ask --with nemotron`) | Nano, with the frozen forks and escalation, one leaf per Sandbox forked from one checkpoint | the stand-in prunes with `graphene watch`'s commands (accept, drop, edit, E) and may reopen; offers are taken by the bench's mechanical rule (decision 65) |
| **B′. Graphene without the prune** | as B | as B | none: every proposal is accepted whole, offers by the same rule, the change of mind sent verbatim; no correction, no reopen |
| **C. A frontier agent, for reference** | nobody | Alex's own coding agent (Claude Code), the protocol's prompt arm, with Graphene's hooks removed (`rm .claude/settings.local.json`) | as A |

- A, B and B′ share the model family, the tool set, the paragraph, the card and the task repo
  (`make_task.py`, fresh per run). A differs from B in the tree and the check; B differs from B′ only
  in the person.
- C is a point on the map, never part of the Nemotron path, and its cost is Claude Code's own
  reported total, not a Token Factory ledger row. It is never averaged or charted with A, B or B′
  as if it were one of them.
- **The harness for arm A is not built at the time of writing.** It is committed, with a test
  against `tests/fake_tokenfactory.py`, before arm A's first run, and its run budget (turns, time)
  equals one B leaf's frozen budget times the number of leaves B's median feeds tree has, stated
  in the frozen decision.
- **Forks and escalations are not yet counted by `bench.py`.** A counter reading them from the leaf's
  log (decision 75) is committed, with a test on a hand-built store, before the first B run.

## Tasks and runs

| task | A | B | B′ | C |
|---|---|---|---|---|
| feeds | 5 | 5 | 5 | 5 |
| inventory | 3 | 3 | 3 | at most 1 |
| logs | 3 | 3 | 3 | at most 1 |
| report | 3 | 3 | 3 | at most 1 |
| item 5's real repository | as the budget allows | as the budget allows | as the budget allows | none |

Order of spend, as item 2 and the directive's spend rules say: feeds for all arms, then the other
three tasks, then the real repository. Within a task, the arms rotate which goes first from run to
run (A, B, B′, then B, B′, A, and so on), one run at a time on the machine (`PROTOCOL.md` rule 10),
and a different stand-in for every run (rule 9). The real repository's paragraph is written and
committed sealed before its first run; its rows are reported but are not part of the hypotheses.

## What is counted, for every run

| metric | from | notes |
|---|---|---|
| accept | `accept.py`, run once afterwards by tally | passed of total, and whether all passed |
| quality | `quality.py`, run once afterwards | feeds only; the other tasks have none, shown as `n/a` |
| person-seconds (modelled) | `attention.py` over the run log | the keystroke-level model, never a clock; raw acts, typed characters and words read beside it |
| dollars | the one Token Factory ledger (rule 6) | planner and executor calls both; a run with an unpriced attempt is `unknown`, never $0; C from Claude Code's JSON |
| wall time | the run log, first entry to last | seconds |
| restarts | tally | all, and unmandated |
| landed, handed back, failed | bench rows | B and B′ only |
| forks, escalations | the leaf's log (decision 75) | B and B′ only |
| files outside intent | tally, from git | every arm |

The person never runs `accept.py` or `quality.py` and never sees either (`PROTOCOL.md` rule 7).

## Hypotheses

- **H1, correctness.** On feeds, B passes at least as many `accept.py` and `quality.py` checks as A.
- **H2, attention.** On feeds, B costs fewer modelled person-seconds than A.
- **H3, the prune.** On feeds, B passes more checks than B′.
- **H4, the other tasks.** H1 to H3 hold in the same direction on inventory, logs and report.
- **H5, reference.** B's dollars per fully accepted run are below C's, and B's accept is within C's
  range. This is descriptive: C is Alex's agent, one arm, and it is not tested against anything.

On 23 September a plain paragraph passed as many hidden checks as the tree with fewer modelled
person-seconds (`results-2026-09-23.md`), with Claude executors. H2 is registered knowing that.

## Analysis rules

1. **Every run is in the table, in the order it was run**, with its value, then the range, as
   `results.py` prints them. No mean without the runs beside it.
2. **"Higher" or "lower" is said only when the ranges do not overlap** (every run of one arm at or
   past every run of the other, and the medians differ). Anything else is written as *no difference
   shown at n = 5* (or n = 3). No significance test is run on five runs.
3. A hypothesis holds only if its comparison is "higher" or "lower" in the registered direction. A
   comparison the other way is reported as such. A result where no difference is shown is a null
   result, and **null results are reported**, in the table and in the one sentence under it.
4. **No rerun for a better number** (`PROTOCOL.md` rule 12). A rerun only when the harness failed;
   it is named as an infrastructure rerun, and the failed run stays in the file with its cause.
5. **A void run** is void only by a fairness rule of `PROTOCOL.md`, the blob check above, or a
   configuration that differs from the frozen one; it stays in the file with its reason, and its cell
   says `void`.
6. **The spend cap** is $10 of Token Factory in all (`GRAPHENE_SPEND_CAP_USD=10`), on one ledger,
   `GRAPHENE_LEDGER`, that every arm's calls go on: `arm_a.py` reads it, and `bench.py` and
   `arm_bprime.py` are given it (`--ledger "$GRAPHENE_LEDGER"`). No harness assumes a cap: with none
   set, or one that is not a number, nothing starts; at 80% of it ($8) no new run starts, and at $10
   the client refuses the next call. `GRAPHENE_AGENT_LIVE_USD` is unset, since a row made under it is
   practice, which `evidence.py` refuses. Arm C is outside the cap: its cost is Claude Code's own
   total, reported and not capped. The cap may stop the evidence before every cell is filled. A cell
   not run says `not run (cap)`; the table is not reshaped to hide it, and a hypothesis whose cells
   are missing is `not tested`.
   *Edited 2026-09-29, before any evidence run, for Alex's decision of 29 September: the rule said
   "`GRAPHENE_SPEND_CAP_USD`, 50 if unset", and the dollars row of the table above said "the night's
   Token Factory ledger".*
7. **Nothing is tuned once an evidence run has started** (rule 13, and the integrity rule: never
   weaken a check, a scope, the gate, `accept.py`, `quality.py`, a task repo or a test to move a
   number). If the configuration must change, the evidence restarts under a new decision number and
   the earlier rows are reported as a separate configuration.
8. **Every number comes from rows and the ledger by a script**, and the chart
   (`docs/assets/evidence.svg`) is generated from the same rows. No number is typed.
9. **Nothing from a stand-in is shown as live.** The runs are stand-in people with live models; the
   results say so wherever they are quoted.
10. **Analyses not listed here** are welcome, labelled *after the fact*.
11. The one-sentence claim *Graphene makes a cheap open model safe to hand real work* is made only if
    H1 and H2 both hold on feeds. If they do not, the results say what was learned, as plainly.

## The table that will be reported

Each cell: every run's value in run order, then the range. Empty until the runs exist.

| task | arm | runs | accept (passed/total per run) | all passed | quality | person-s (modelled) | dollars | wall s | restarts (unmandated) | landed / handed back / failed | forks | escalations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| feeds | A | | | | | | | | | n/a | n/a | n/a |
| feeds | B | | | | | | | | | | | |
| feeds | B′ | | | | | | | | | | | |
| feeds | C | | | | | | | | | n/a | n/a | n/a |
| inventory | A | | | | n/a | | | | | n/a | n/a | n/a |
| inventory | B | | | | n/a | | | | | | | |
| inventory | B′ | | | | n/a | | | | | | | |
| inventory | C | | | | n/a | | | | | n/a | n/a | n/a |
| logs | A | | | | n/a | | | | | n/a | n/a | n/a |
| logs | B | | | | n/a | | | | | | | |
| logs | B′ | | | | n/a | | | | | | | |
| logs | C | | | | n/a | | | | | n/a | n/a | n/a |
| report | A | | | | n/a | | | | | n/a | n/a | n/a |
| report | B | | | | n/a | | | | | | | |
| report | B′ | | | | n/a | | | | | | | |
| report | C | | | | n/a | | | | | n/a | n/a | n/a |

And one row per hypothesis:

| hypothesis | comparison | result (higher / lower / no difference shown / not tested) |
|---|---|---|
| H1 | feeds, B against A, accept and quality | |
| H2 | feeds, B against A, person-seconds | |
| H3 | feeds, B against B′, accept and quality | |
| H4 | inventory, logs, report: H1 to H3 each | |
| H5 | feeds, B against C, dollars per fully accepted run; accept | |

Under the tables: one sentence on what they show, whatever it is.
