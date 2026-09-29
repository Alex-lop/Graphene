# The direction against morning.md: the study of 29 September 2026

## Pre-registered (written before any run)

*Written and committed on 2026-09-29, before any run of this study, by lane D of
`docs/process/directives/FIRST_LIGHT_DIRECTIVE.md`. The harness (`docs/test/direction_study.py`)
and its test (`docs/test/test_direction_study.py`) are committed with this file. Once the first run
starts, this section is not edited. Anything decided later goes below it and is labelled **after
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

Every command goes through `direction_study.py run`, which refuses what the arm does not allow (a
refused command still counts as an act, with nothing read) and prints what the command printed. In
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
  its run. It is not told the hypotheses, the key or the other arm.
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

Filled from `table`; empty until the runs exist.

| run | arm | person-s, MODELLED | typed | acts | words read | right (of 8) | false | answered |
|---|---|---|---|---|---|---|---|---|

| arm | n | median person-s | median words read | mean right (of 8) | mean false |
|---|---|---|---|---|---|
| direction | | | | | |
| morning | | | | | |

Under the tables goes one sentence on what they show, whatever it is.
