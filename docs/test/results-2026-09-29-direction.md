# The direction against morning.md: the study of 29 September 2026

## Pre-registered (written before any run)

*Written and committed on 2026-09-29, before any run of this study, by lane D of
`docs/process/directives/FIRST_LIGHT_DIRECTIVE.md`. The harness (`docs/test/direction_study.py`)
and its test (`docs/test/test_direction_study.py`) are committed with this file; the answer key is
in `docs/test/direction_key.py`, outside the file each brief names. A review of the harness, before
any run, closed two holes in its wrapper (a write passed as a read; the morning arm could read
another file) and moved the key out; nothing else changed. Once the first run starts, this section
is not edited. Anything decided later goes below it and is labelled **after
the fact**. The runs are the coordinator's, as a workflow; this lane runs none of them.*

### The question

*Can a person answer "what is waiting on me, what is running, what is next" faster from the
direction than from `morning.md`, and as correctly?*

Today Alex answers these by reading `docs/process/morning.md`. The direction (`graphene direction`,
decisions 101 to 104 when they are written) is meant to replace that by hand-written file.

### Hypotheses, each with its direction

| | comparison | registered direction | measure |
|---|---|---|---|
| H1 | direction against morning | direction **lower** | modelled person-seconds, median of the arm |
| H2 | direction against morning | direction **the same or higher** | items right (of 8), mean of the arm |
| H3 | direction against morning | direction **lower** | words read, median of the arm |

H1 with H2 is the question. H3 says where a saving would come from.

### The two arms

| arm | what the stand-in reads | the commands it may run |
|---|---|---|
| **direction** | a repository whose store and `.graphene/direction.txt` hold the state | `graphene direction` (with `--width N`), `graphene plan`, `graphene board`, `graphene watch --once` |
| **morning** | `morning.md`, the brief of the same state, to the brief's contract | `cat`, `head`, `sed -n`, `grep`, each on `morning.md` |

Every command goes through `direction_study.py run`, which lets through only reads of the arm's own
material and refuses the rest (a refused command still counts as an act, with nothing read), and
prints what the command printed. The direction arm's reads are `graphene direction`, `plan`, `board`
and `watch --once` with their read flags only (`--width`, `--text`, `--json`, `--view`, `--height`,
`--all`): no subcommand, so nothing that writes. The morning arm's are `cat`, `head`, `sed -n` and
`grep` of `morning.md` and of no other file. In
the direction arm it runs the command in the person's seat, without the agent's marks, as
`newrun.sh`'s `as_me` does, with `COLUMNS=100 LINES=40` unless the stand-in names a width.

### The state both arms read

One state, built by `direction_study.py fixture` just before each run:

- **The direction:** `invoices` (the goal) over `pdf`, `billing`, `csv-sunset` (accepted) and
  `mobile` (proposed).
- **The plan**, hung from `pdf`, proposed by session `5a1e0c3b` and accepted: `fonts` done, `render`
  in review (its sign-off), `template` running (held by `5a1e0c3b`), `download` waiting on `render`,
  `email` ready. The board has one open question, `q-paper`.
- **The sessions**, recorded through the hook's own `ingest_hook_event`:
  - `5a1e0c3b` holds `template` and is running;
  - `b7c24d1e`'s turn ended four minutes before the build (your turn), attached to `billing`;
  - `c3d4e5f6` is running, attached to `billing`, with its subagent `a1b2c3d4` running;
  - `d9e8f7a6` has been idle for twenty minutes, unattached;
  - one session is two days old.

The direction arm's store is made by Graphene's own code paths (the plan proposed through
`graphene plan propose -` as the session, accepted, leaves started and finished at the boundary with
git). The running sessions' last calls are stamped 15 minutes after the build, so they read running
for the length of a run (the screen says "now"); a run starts within 5 minutes of its build.
`morning.md` (`MORNING` in the harness) was written by this lane to the brief's contract (five
headings, at most twenty lines) with the sections the real mornings have below the brief. It names
every id the key names. It is 367 words; `graphene direction` at 100 columns prints 199.

### The answer key (written before any run)

| question | items (an item counts as right if any of its ids is given) | why |
|---|---|---|
| waiting on you | `render` · `q-paper` · `mobile` · `b7c24d1e` | a leaf in review; an open board question; a proposed direction node; a session whose turn is over |
| running | `template` or `5a1e0c3b` · `c3d4e5f6` · `a1b2c3d4` | a leaf and the session holding it are one piece of work; a session; its subagent |
| next | `email` | the leaf `graphene run` starts next |

Eight items. `d9e8f7a6` (idle) and `download` (waiting on `render`) are in no answer. An id given
that is in no item of its question is a false item. Ids are compared by their first 8 characters.

### Stand-ins and runs

- **Seats:** a first-time user, Alex, and a judge (`SEATS` in the harness), as in the shaping runs.
- **Runs:** 3 seats × 2 arms × 2 repetitions = **12 runs, n = 6 per arm.** Each run is a fresh
  Claude Code sub-agent, never reused, whose whole instruction is the brief the harness prints for
  its run, which tells it to open no file itself. It is not told the hypotheses, the key or the
  other arm.
- **Order:** a seat's two arms of one repetition start together, each with its own fixture built
  just before it; the six pairs run in any order.
- **The build:** one commit of `first-light` with this file in it; its sha goes into the results.

### The measures

attention.py's keystroke-level model, with its constants (`K`, `M`, `WPM` are imported from it):

| measure | how |
|---|---|
| person-seconds, MODELLED | K × typed + M × acts + words read ÷ WPM × 60 (0.28 s, 1.35 s, 250 words a minute) |
| typed | the characters of each command as typed |
| acts | the commands run, refused ones included |
| words read | every word each command printed (the same rule in both arms: all of it counts as read) |
| items right | of the 8 in the key |
| false items | ids given that are in no item of their question |

The answers the stand-in types are not in the model: they are the same ids in both arms when right.

### Analysis rules

1. **The verdict** (printed by `table`): "the direction answered faster, as correctly" only if the
   direction's median person-seconds is lower than morning's **and** its mean items right is at
   least morning's. Otherwise "no advantage shown", said as the table says it.
2. **n = 6 per arm is a pilot.** No p-value or interval is claimed. Every run is reported, with the
   seat, and the medians beside the runs.
3. **A run is void** only if the harness failed (a fixture that did not build, a wrapper that
   crashed). A void run may be rerun once, named as an infrastructure rerun, and the failed run is
   kept. There is no rerun for a better number.
4. **Nothing is tuned once the first run starts:** not the fixture, `morning.md`, the key, the
   briefs or the build.
5. **Null results are reported**, and anything decided after the data is labelled after the fact.

### Threats, said before the data

- The stand-ins are Claude sub-agents, not people. Alex's own reading outranks them.
- This lane wrote both `morning.md` and the direction, and wrote the direction's code.
- "Everything printed is read" overcounts a person who skims; it overcounts both arms by the same
  rule, and more words are printed by `cat morning.md` than by `graphene direction`.
- The fixture's running sessions are stamped ahead of the clock; the words on the screen are the
  product's.

### For the coordinator: how to run it

From the `first-light` checkout, with `uv sync` done, for each run name `R` (e.g.
`first-direction-1`, `first-morning-1`, …, `judge-morning-2`) and its arm `A`:

    env -u NEBIUS_API_KEY -u NEBIUS_PROJECT_ID uv run --frozen python docs/test/direction_study.py fixture "$RUNS/$R" A
    uv run --frozen python docs/test/direction_study.py brief "$RUNS/$R" SEAT > "$RUNS/$R.brief"

Spawn a fresh sub-agent per run whose whole prompt is "Read $RUNS/$R.brief and do what it says."
(`$RUNS` is a scratch directory outside every repository.) When all twelve are done:

    uv run --frozen python docs/test/direction_study.py table "$RUNS"/*-direction-* "$RUNS"/*-morning-*

### The table that will be reported

Run 03:25 to 03:27 on 29 September by the coordinator, from a checkout of `first-light` at
`92804c3` (this file's registration is in it), twelve fresh sub-agents (claude-opus-5-5), each
fixture built just before the runs started; all twelve at once. No run is void. Filled by `table`:

| run | arm | person-s, MODELLED | typed | acts | words read | right (of 8) | false | answered |
|---|---|---|---|---|---|---|---|---|
| alex-direction-1 | direction | 109.1 | 45 | 3 | 385 | 8 | 0 | 3/3 |
| alex-direction-2 | direction | 119.1 | 57 | 3 | 413 | 8 | 0 | 3/3 |
| first-direction-1 | direction | 173.3 | 75 | 4 | 612 | 8 | 0 | 3/3 |
| first-direction-2 | direction | 183.4 | 87 | 4 | 640 | 8 | 0 | 3/3 |
| judge-direction-1 | direction | 168.6 | 78 | 4 | 589 | 8 | 0 | 3/3 |
| judge-direction-2 | direction | 119.1 | 57 | 3 | 413 | 8 | 0 | 3/3 |
| alex-morning-1 | morning | 107.1 | 43 | 2 | 385 | 8 | 0 | 3/3 |
| alex-morning-2 | morning | 103.7 | 46 | 2 | 367 | 8 | 0 | 3/3 |
| first-morning-1 | morning | 103.7 | 46 | 2 | 367 | 8 | 0 | 3/3 |
| first-morning-2 | morning | 107.7 | 45 | 2 | 385 | 8 | 0 | 3/3 |
| judge-morning-1 | morning | 107.7 | 45 | 2 | 385 | 8 | 0 | 3/3 |
| judge-morning-2 | morning | 103.7 | 46 | 2 | 367 | 8 | 0 | 3/3 |

| arm | n | median person-s | median words read | mean right (of 8) | mean false |
|---|---|---|---|---|---|
| direction | 6 | 143.85 | 501.0 | 8.00 | 0.00 |
| morning | 6 | 105.4 | 376.0 | 8.00 | 0.00 |

By the registered rule (8 items): no advantage shown for the direction.

With the same state, every run in both arms answered all eight items right, and the direction's runs
took more modelled person-seconds (median 143.9 against 105.4) and read more words (501 against 376),
so no advantage is shown for the direction.

*After the fact:* in all six direction runs the stand-in wrote that `graphene direction` counted
what waits on the person ("you 4") but named only two of the four, so each ran `graphene plan` and
then `graphene board` to find the other two ids; that second and third command is most of the
difference. In the morning arm, four of six stand-ins said the brief left one session's state
(idle 20 minutes) unsaid. Two direction stand-ins said the rows were cut at the default width.

## Exploratory second pass (registered after the fact, before its runs)

*Written at 03:40 on 29 September, after the registered runs above and before any run of this pass,
by lane D. It is exploratory: whatever it shows, the registered result above stands as written, and
this pass is reported as after the fact. It is set up like shaping study 3: the same design again on
a changed build.*

**What changed in the build, and why.** Every direction stand-in above read "you 4" and could name
only two of the four items, so each ran `graphene plan` and `graphene board` as well. Since then
(`4f185aa`, `5ea3b03`) `graphene direction` names each item that waits on the person (a leaf in
review, a board question, a proposal, a session whose turn it is) and each piece of running work once
(a running leaf with its holder beside it), by the id they act on; and what a row says wraps instead
of being cut. On this fixture at 100 columns it prints 229 words (199 before); `morning.md` is 367.
`docs/test/test_direction_study.py::test_the_direction_print_alone_names_every_waiting_and_running_item_inside_80_columns`
checks that the print alone names an id of every "waiting" and "running" item of the key.

**What is held equal.** The fixture, `morning.md`, the key (`docs/test/direction_key.py`), the
briefs (`brief`), the wrapper (`run`), the seats, the measures and the verdict rule are those of the
registered study, unchanged. Only the build differs: `first-light` at the commit that adds this
section, whose sha goes into the results.

**Runs.** 3 seats × 2 arms × 2 repetitions: 12 runs, n = 6 per arm, fresh sub-agents, both arms run
again at the same time (the registered morning runs are not reused, so both arms share the machine
and the hour). Run names start with `x-`.

**What would be said.**
- "In an exploratory second pass on the changed build, the direction answered faster, as
  correctly", only if `table` prints that verdict for this pass.
- Otherwise the table's own words, with "exploratory" in front.
- The registered result's sentence is not changed.

**How to run it.** From a checkout of `first-light` at that commit, with `uv sync` done, for each run
name `R` in `x-first-direction-1`, `x-first-morning-1`, `x-alex-direction-1`, `x-alex-morning-1`,
`x-judge-direction-1`, `x-judge-morning-1` and the same with `-2`, its arm `A` and its seat `S`:

    env -u NEBIUS_API_KEY -u NEBIUS_PROJECT_ID uv run --frozen python docs/test/direction_study.py fixture "$RUNS/$R" A
    uv run --frozen python docs/test/direction_study.py brief "$RUNS/$R" S > "$RUNS/$R.brief"

Spawn a fresh sub-agent per run whose whole prompt is "Read $RUNS/$R.brief and do what it says." Then:

    uv run --frozen python docs/test/direction_study.py table "$RUNS"/x-*-direction-* "$RUNS"/x-*-morning-*

### The exploratory table

Run 03:53 to 03:54 on 29 September by the coordinator, from a checkout of `first-light` at
`f5250c1` (the naming fix, `4f185aa` in the branch), twelve fresh sub-agents, all at once. No run is
void. Filled by `table`:

| run | arm | person-s, MODELLED | typed | acts | words read | right (of 8) | false | answered |
|---|---|---|---|---|---|---|---|---|
| x-alex-direction-1 | direction | 69.8 | 30 | 1 | 250 | 8 | 0 | 3/3 |
| x-alex-direction-2 | direction | 61.4 | 18 | 1 | 229 | 8 | 0 | 3/3 |
| x-first-direction-1 | direction | 99.9 | 31 | 2 | 369 | 8 | 0 | 3/3 |
| x-first-direction-2 | direction | 116.2 | 45 | 3 | 415 | 8 | 0 | 3/3 |
| x-judge-direction-1 | direction | 108.3 | 43 | 2 | 390 | 8 | 0 | 3/3 |
| x-judge-direction-2 | direction | 108.3 | 43 | 2 | 390 | 8 | 0 | 3/3 |
| x-alex-morning-1 | morning | 107.7 | 45 | 2 | 385 | 8 | 0 | 3/3 |
| x-alex-morning-2 | morning | 130.6 | 122 | 3 | 385 | 8 | 0 | 3/3 |
| x-first-morning-1 | morning | 107.1 | 43 | 2 | 385 | 8 | 0 | 3/3 |
| x-first-morning-2 | morning | 103.1 | 44 | 2 | 367 | 8 | 0 | 3/3 |
| x-judge-morning-1 | morning | 107.7 | 45 | 2 | 385 | 8 | 0 | 3/3 |
| x-judge-morning-2 | morning | 103.7 | 46 | 2 | 367 | 8 | 0 | 3/3 |

| arm | n | median person-s | median words read | mean right (of 8) | mean false |
|---|---|---|---|---|---|
| direction | 6 | 104.1 | 379.5 | 8.00 | 0.00 |
| morning | 6 | 107.4 | 385.0 | 8.00 | 0.00 |

By the registered rule (8 items): the direction answered faster, as correctly.

After the fact, on one fixture its author wrote: with every waiting and running item named, the
direction's runs took a median 104.1 modelled person-seconds against morning.md's 107.4,
with every run in both arms right on all eight items. Four of the six direction stand-ins answered from
one `graphene direction`; what they still stopped on was that `next: email` names a leaf that has no
row of its own, and whether running work is named by its leaf or its session. This can show which way
the change moved, and cannot confirm it.
