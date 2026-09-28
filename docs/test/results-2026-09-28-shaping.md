# Shaping with the board and the graph: the study of 28 September 2026

## Pre-registered (written before any run)

*Written and committed on 2026-09-28, before any run of this study. No run directory exists yet, and
neither the board nor the graph views were merged into `shaping` when this was written. This is lane D of
`docs/process/directives/SHAPING_DIRECTIVE.md`. The harness for the board arm (`standin.py`,
`attention.py`, `logline.py`, `summarize.py` and `tally.py`) is committed after this file and before the
first run. Once the first run starts, this section is not edited. Anything decided later goes below
it and is labelled **after the fact**.*

### The question

*Does shaping with the board and the graph cost the person less attention than the outline alone,
and than the paragraph, at the same or better accept and quality?*

On 23 September the paragraph beat the outline on every attention measure wherever a tree existed.
In the dense cell it took 2626 modelled person-seconds against the outline's 3869, and reading
accounted for 69% of the gap (`results-2026-09-23.md`). The hypotheses below are registered knowing
that.

### Hypotheses, each with its direction

| | comparison | registered direction | measure |
|---|---|---|---|
| H1 | board against outline | board **lower** | modelled person-seconds, whole run |
| H2 | board against paragraph | board **lower** | modelled person-seconds, whole run |
| H3 | board against outline | board **lower**, on each measure separately | words read; typed characters |
| H4 | board against outline, and against paragraph | board **the same or higher** | accept (passed of total), and quality on feeds |
| H5 | board against outline | board **higher** | caught before code, as judged |

- H1 and H2 are the question.
- H3 says where a saving would come from. On 23 September most of the outline's extra cost came
  from reading the tree and from retyping constraints into it.
- H4 is the condition in the question: "at the same or better accept and quality".
- H5 is the product's claim that answering the planner's questions catches a misunderstanding
  before any code is written. On 23 September the one judged tree caught 0 or 1, so a null result
  is expected here. It is registered anyway.

### The three arms

| arm | arm name in the run directory | what the person does | how they read the plan |
|---|---|---|---|
| **paragraph** | `prompt` | This is the protocol's prompt arm. The person sends the paragraph to a Claude Code session in the repo, reads the reply and `git diff`, and follows up with `--resume`. Graphene's hooks are removed from this arm's repo right after `newrun.sh` (`rm .claude/settings.local.json`, as `PROTOCOL.md`'s paragraph-arm recipe says), so no gate holds the paragraph. Without the hooks, rework, churn and write events read zero, and they are not compared. | there is no plan |
| **outline** | `tree` | This is the protocol's tree arm, as on 23 September. The person sends the paragraph to a session in the repo, and the repo's hooks make that session propose a tree. The person prunes with `plan accept`, `node drop`, `node set` and the text edit (`E`), and runs with `graphene run --parallel 4`. The arm section of its brief is unchanged since 23 September. | `graphene plan --text` |
| **board** | `board` | The same session and hooks. The person first answers the planner's board, one command per item: `graphene board take ID`, `pick ID N`, `drop ID`, `park ID`, `answer ID WORDS`, `note WORDS`. Then they prune the tree with the outline arm's commands and run it the same way. | `graphene board`, then `graphene plan --view auto` |

`standin.py` prints all three briefs from one template, so a diff of any two shows that they differ
only in the arm section. The board commands are the ones announced for lane A's board. If the build
under test names them differently, the board section of `standin.py` and `BOARD_CHOSEN` in
`attention.py` are changed to match in a single commit, before the first run. The results name that
commit.

### Tasks and runs

The tasks are `feeds`, `inventory`, `logs` and `report`, each with a fresh repo per run from
`make_task.py`. There is one run per arm per task: **12 runs, n = 1 per cell.**

n is small for three reasons:
- the study cannot start until the board and the graph views land in `shaping` tonight;
- the directive stops new work at 07:15;
- one feeds run took 3 to 10 minutes of wall clock on 23 September.

Twelve runs is what fits. That makes this a pilot. It can show which way each difference goes on
each task, and where the attention went. It cannot show that a difference is real.

**Order.** The three arms of a task start together, as three separate runs with three different
stand-ins. The four tasks go one after another: feeds, inventory, logs, report.

This departs from `PROTOCOL.md` rule 10 (one run at a time). That rule exists so that
`wall_seconds` means something. No registered measure uses wall time, and starting a task's arms
together gives all three arms the same machine at the same time. Wall time is printed but not
compared. Rule 9 ("alternate which goes first") does not apply when all three start together.

### What is held equal

- **The planner.** This is Claude Code: the session in the repo that receives the person's first
  message, run with `standin.py`'s `BY_HAND` flags (`claude -p … --model sonnet --permission-mode
  acceptEdits --output-format json` and the same tool list). In the outline and board arms, the
  repo's hooks make it propose. In the paragraph arm it is the executor.
- **The executor.** This is Claude Code as `standin.py` fixes it: `EXECUTOR` for every leaf that
  `graphene run --with` starts, and `BY_HAND` for every message the person sends. No Nemotron model,
  Token Factory call or Sandbox is used anywhere in the study.
- **The card.** Each task's `intent.md`, whole, which `standin.py` pastes into the brief. The blobs
  are as at `cb2ce54`: feeds `3600815c2ef5`, inventory `7eb0a1c485fd`, logs `124ccd01c81a`, report
  `5246e8172ac7`.
- **The paragraph.** Wherever the protocol has one, every arm opens with it. These are the sealed
  paragraphs committed for the live study, `docs/test/tasks/<task>/paragraph.md`, with the blobs
  that `results-2026-09-28-live-prereg.md` lists: `2d28b53ce4e0` feeds, `799c3f413397` inventory,
  `92b72aeeae02` logs, `d0f33c77d317` report.
  - The paragraph is sent byte for byte as the first message, in all three arms.
  - The change of mind in `change.md` (feeds and logs only) is sent byte for byte as the mandated
    correction.
  - The stand-in did not write either text, and nobody who starts a run reads them.

  So a task's three arms open with identical typing, and every difference in attention comes after
  the opening. `summarize.py` checks that each run's first `prompt` is the sealed paragraph, and a
  run whose first prompt is not is void. If a sealed paragraph is not in the tree under test, the
  study does not start.
- **The style.** One style, `sealed`, is used for all 12 runs. The person sends the written opening
  as it is, then works like a busy, competent person: they change what is wrong by the card, leave
  alone what is right, and keep anything they type after the opening short and plain. This is
  neither of 23 September's styles. The dense style told the person to shape every node and the
  Tuesday style told them to write under thirty words, and both contradict a paragraph that is
  already written. These numbers therefore cannot be compared cell for cell with 23 September's.
- **The stand-in's model.** Every stand-in is a fresh Claude Code sub-agent, spawned the same way
  with the same model, one per run and never reused.
  - Its whole instruction is "read this file and do what it says". The file is `standin.py`'s brief.
  - It is not handed this file, `PROTOCOL.md` or the directive, and it is not told the hypotheses
    (rule 14). On 23 September the stand-ins were told to read the spec, which names the measures.
- **The build.** One wheel is built from one commit of `shaping` that has both features merged,
  and installed in its own venv. That venv's `bin` is first on `PATH` in every shell (`env.sh`). The
  commit and the wheel's sha256 are written into the runs directory before the first run.
- **The budget.** Three corrections, as in the protocol.

### Metrics, all computed afterwards by a script

| metric | from | notes |
|---|---|---|
| person-seconds, MODELLED | `attention.py` | K = 0.28 s per typed character, M = 1.35 s per act, reading at 250 words a minute. Printed with its three parts: typing + acts + reading. This is a model, never a clock. |
| typed characters | `attention.py` | A message counts whole; a key-type act counts 0; a `node set` counts its values; a text edit counts the characters it added. A board `answer` or `note` counts the characters of its words. The item id and `pick`'s number are never counted. |
| acts | `attention.py` | Every person entry except `read`. Each board command is one act. |
| keys | typed characters + acts | One key for each character and one for each act. |
| words read | `attention.py` | Every word logged as `read`. |
| to run, MODELLED | `attention.py` | The same model, cut at the first `run` (outline, board) or the first `prompt` (paragraph). |
| accept | `accept.py`, run by `tally.py` | Passed of total. |
| quality | `quality.py`, run by `tally.py` | Feeds only; `n/a` elsewhere. |
| caught before code | `attention.py`'s candidates, then a judge | See below. |

**Caught before code** applies to the outline and board arms:
- **The candidates.** Every node the planner proposed that the person dropped or edited before the
  first leaf started. In the board arm, also every board item the person answered with `pick`,
  `answer` or `drop` (`attention.py`'s `board_acts`).
- **The judge.** A separate judge for each run, with no part in that run, reads each candidate
  against the card and answers one question: *left as proposed, would it have cost a restart, or a
  wrong or unwanted result by the card?*
- **The report.** Judged catches out of candidates. The judge's verdict is saved in the run
  directory.
- **The paragraph arm.** `n/a`. Its counterpart, restarts, is in the table.

Printed but not hypothesised: restarts (all and unmandated), files outside intent, cost in dollars,
and wall seconds.

### The table that will be reported

Every cell is filled from `summarize.py` and `attention.py`, and stays empty until the runs exist.

| task | arm | run | valid | accept | quality | person-s, MODELLED = typing + acts + reading | to run, MODELLED | typed | acts | keys | words read | caught (judged / candidates) | restarts / unmandated | outside intent | cost $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| feeds | paragraph | | | | | | | | | | | n/a | | | |
| feeds | outline | | | | | | | | | | | | | | |
| feeds | board | | | | | | | | | | | | | | |
| inventory | paragraph | | | | n/a | | | | | | | n/a | | | |
| inventory | outline | | | | n/a | | | | | | | | | | |
| inventory | board | | | | n/a | | | | | | | | | | |
| logs | paragraph | | | | n/a | | | | | | | n/a | | | |
| logs | outline | | | | n/a | | | | | | | | | | |
| logs | board | | | | n/a | | | | | | | | | | |
| report | paragraph | | | | n/a | | | | | | | n/a | | | |
| report | outline | | | | n/a | | | | | | | | | | |
| report | board | | | | n/a | | | | | | | | | | |

And the hypotheses:

| hypothesis | board minus the other arm, per task (feeds / inventory / logs / report) | tasks in the registered direction | result |
|---|---|---|---|
| H1: person-s, board against outline | | of 4 | |
| H2: person-s, board against paragraph | | of 4 | |
| H3: words read, board against outline | | of 4 | |
| H3: typed, board against outline | | of 4 | |
| H4: accept and quality, board against outline | | of 4 | |
| H4: accept and quality, board against paragraph | | of 4 | |
| H5: caught, board against outline | | of 4 | |

Under the tables goes one sentence on what they show, whatever it is.

### Analysis rules

1. **n = 1 per cell, so there are no significance claims.** No p-value, interval or test is
   reported. A hypothesis's result is how many of the four tasks go the registered way, with each
   task's signed difference beside it.
2. **The words used for a result:**
   - "lower", or "the same or higher", only if all four tasks go the registered way;
   - "on three of four tasks, one run each" if three do;
   - "no difference shown" if two or fewer do, or if any task is void or not run;
   - a task that goes the other way is reported as going the other way.
3. **Every cell is reported**, void and not-run cells included, each with its reason. No mean or
   median across tasks stands in for the rows.
4. **Null results are reported**, in the table and in the one sentence.
5. **A run is void** only in three cases: it broke a `PROTOCOL.md` fairness rule (except rule 10,
   as declared above), its first prompt is not the sealed paragraph, or the `graphene` on `PATH` is
   not the recorded build.
   - **There is no rerun for a better number** (rule 12).
   - A rerun is allowed only when the harness failed. It is named as an infrastructure rerun, and
     the failed run is kept.
6. **The integrity rule, word for word:** never weaken a check, a scope, the gate, accept.py,
   quality.py, a task repo or a test to move a number.
7. **Nothing is tuned once the first run starts** (rule 13): not the brief, the card, the paragraph
   or the build.
8. **Anything decided after the data is labelled "after the fact".** That includes a re-cut, an
   exclusion, a sensitivity analysis (such as 23 September's "every re-display taken out") and a new
   column.
9. **What this is evidence about.** It is evidence about shaping, with Claude Code (sonnet) as the
   planner and the executor and Claude sub-agents as the person, measured with the keystroke-level
   model. It is **not** evidence about Nemotron, Token Factory or Sandboxes. None of them runs in
   the study, and no number from it is quoted as theirs.

### Known threats, registered now

- **The people are models** with the card in their context, and the seconds come from a model.
  Alex's own session outranks all of it.
- **The model charges every word shown, every time it is shown.** The board arm reads through views
  the outline arm does not use (`graphene board` and `plan --view auto`). So part of what H1 and H3
  measure is how many words each view prints. That is part of the design being tested, not noise.
- **The build may put a board up in the outline arm too.** The outline brief does not mention the
  board, and its person never answers it. Two things would stop the outline arm matching 23
  September: the build refusing to run a tree whose board is unanswered, or `plan --text` now
  printing the board. If either happens, it is written down as a deviation before the first run,
  and the outline cells are labelled with it.
- **A shaping-arm session may write code instead of proposing,** as both of 23 September's Tuesday
  tree runs did. Such a run is reported as that, and its caught value is `n/a`, not 0.
- **The brief decides what counts as an act,** and the board arm has more commands than the outline
  arm. At M = 1.35 s per act, that difference weighs little.
- **The coordinator who runs the study also coordinates the lane that built the board.** The harness
  and this registration were written by a separate agent that read none of the cards.
- **Every executor loads the user's globally enabled plugins,** as on 23 September.

### Deviations, written before the first run (03:30)

Checked against the build under test, `668c7fd` (wheel sha256 `5408b89f…`, in `~/graphene-shaping-runs/build.txt`):

- **The build teaches the board to in-session agents** (`gate.TEACH`), so the session in the outline
  arm may put up board items too, and `graphene plan --text` now prints the board's lines after the
  goal. The outline arm's person therefore sees any board lines when it reads the plan as text,
  though its brief never mentions the board. **A tree runs whatever its board holds:** nothing
  refuses `R` while items are open. Both threats above are real, so every outline cell is labelled
  with this, and the outline arm is not the 23 September arm.
- **`graphene board` has a seventh command, `unpark`,** beside the six registered. The brief names
  the six, unchanged; an `unpark` a stand-in types is counted as an act by the rule for commands
  `BOARD_CHOSEN` does not name (counted whole and noted).
- **Two tasks at a time.** The tasks run in two pairs (feeds with inventory, then logs with report),
  not one after another as `shaping-study.md` says, so the study fits the night. Each task's three
  arms still start together, and no registered measure uses wall time.
- **The sealed paragraphs' blobs match** the registration (feeds `2d28b53ce4e0`, inventory
  `799c3f413397`, logs `92b72aeeae02`, report `d0f33c77d317`), and `graphene board --help` and
  `graphene plan --view auto` answer as the brief expects.

## Results

*Filled on 2026-09-28 from `summarize.py` (written to `docs/test/runs-2026-09-28-shaping.json`) and
`attention.py`, by the steps in `shaping-study.md`, "Filling the table". The people were Claude
sub-agents standing in for a person, not people. The planner and the executor were Claude Code
(sonnet). This is evidence about shaping, and none at all about Nemotron, Token Factory or
Sandboxes, none of which ran.*

**What happened to the twelve runs.**
- **Paragraph arm, all four tasks: not run.** No `<task>-sealed-prompt-1` directory exists under
  `~/graphene-shaping-runs`, so each stand-in found no brief and did nothing. `summarize.py` has no
  row for them.
- **Seven runs are void** (outline on all four tasks, board on inventory, logs and report). Each
  one's `opening_is_sealed` is false because its `runlog.jsonl` is empty: nothing was ever sent. In
  each, the stand-in's first launch of the `claude -p` executor was refused by Claude Code's
  auto-mode permission classifier ("Create Unsafe Agents"), and the stand-in stopped without a
  workaround. The reason is in each run's `void.txt`. This is a harness failure, so an
  infrastructure rerun is allowed (rule 5), and none was made tonight.
- **One run is valid: feeds, board.** It sent the sealed paragraph, took all three board items
  and accepted the proposed tree without an edit. Then the same classifier refused
  `graphene run --with "claude -p ..."` before any leaf started, so nothing was built and the change
  of mind was never sent. None of the three registered void cases applies, so it stays valid.
  **After the fact:** its accept and quality are those of the untouched base repo, which the void
  feeds outline repo also scores 10/20 and 0/12. Its to run is cut at the opening message, because
  it logged no `run` (`attention.py`'s note).

Every outline cell carries the deviation written before the first run: the build teaches the board
to the outline arm's session, `plan --text` prints the board, and a tree runs whatever its board
holds, so this outline arm is not the 23 September arm. The outline cells are void as well.

| task | arm | run | valid | accept | quality | person-s, MODELLED = typing + acts + reading | to run, MODELLED | typed | acts | keys | words read | caught (judged / candidates) | restarts / unmandated | outside intent | cost $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| feeds | paragraph | not run: no run directory | | | | | | | | | | n/a | | | |
| feeds | outline † | feeds-sealed-tree-1 | void: nothing sent, the executor launch was refused | | | | | | | | | | | | |
| feeds | board | feeds-sealed-board-1 | yes; stopped before `graphene run` | 10/20, the base repo | 0/12, the base repo | 733.6 = 512.96 + 9.45 + 211.20 | 514.3, cut at the opening | 1832 | 7 | 1839 | 880 | 0 / 0 | 0 / 0 | 0 | 0.234 |
| inventory | paragraph | not run: no run directory | | | n/a | | | | | | | n/a | | | |
| inventory | outline † | inventory-sealed-tree-1 | void: nothing sent, the executor launch was refused | | n/a | | | | | | | | | | |
| inventory | board | inventory-sealed-board-1 | void: nothing sent, the executor launch was refused | | n/a | | | | | | | | | | |
| logs | paragraph | not run: no run directory | | | n/a | | | | | | | n/a | | | |
| logs | outline † | logs-sealed-tree-1 | void: nothing sent, the executor launch was refused | | n/a | | | | | | | | | | |
| logs | board | logs-sealed-board-1 | void: nothing sent, the executor launch was refused | | n/a | | | | | | | | | | |
| report | paragraph | not run: no run directory | | | n/a | | | | | | | n/a | | | |
| report | outline † | report-sealed-tree-1 | void: nothing sent, the executor launch was refused | | n/a | | | | | | | | | | |
| report | board | report-sealed-board-1 | void: nothing sent, the executor launch was refused | | n/a | | | | | | | | | | |

† The outline deviation above, written at 03:30 before the first run.

The feeds board run in detail:
- typing is 0.28 × 1832, acts 1.35 × 7, reading 0.24 × 880;
- the 1832 typed characters are the sealed opening, the same in every arm;
- the seven acts include three board `take`s;
- the candidates are 0 from `caught_before_code_n`, plus 0 pick, answer or drop in `board_acts`,
  and the judge's `judge.md` has no ruling to make.

| hypothesis | board minus the other arm, per task (feeds / inventory / logs / report) | tasks in the registered direction | result |
|---|---|---|---|
| H1: person-s, board against outline | outline void / both void / both void / both void | 0 of 4 | no difference shown: every task void |
| H2: person-s, board against paragraph | paragraph not run / board void, paragraph not run / same / same | 0 of 4 | no difference shown: every task void or not run |
| H3: words read, board against outline | outline void / both void / both void / both void | 0 of 4 | no difference shown: every task void |
| H3: typed, board against outline | outline void / both void / both void / both void | 0 of 4 | no difference shown: every task void |
| H4: accept and quality, board against outline | outline void / both void / both void / both void | 0 of 4 | no difference shown: every task void |
| H4: accept and quality, board against paragraph | paragraph not run / board void, paragraph not run / same / same | 0 of 4 | no difference shown: every task void or not run |
| H5: caught, board against outline | outline void / both void / both void / both void | 0 of 4 | no difference shown: every task void |

The tables show nothing about whether the board and the graph cost less attention: no task has two
comparable runs, because the harness's permission classifier stopped every stand-in that reached
an executor launch and the paragraph arm's runs were never created, so every hypothesis reads "no
difference shown", and that null is a harness failure rather than a result about shaping.

## Study 2: shaping only (pre-registered at about 04:00, before any of its runs)

*Written and committed on 2026-09-28 at about 04:00, before any run of study 2. No study 2 run
directory exists yet. Once the first of its runs starts, this section is not edited; anything decided
later goes below it and is labelled **after the fact**. Study 1's section above is not changed.*

### Why

Study 1 failed for the harness, not for shaping. This session's permission classifier refuses a
sub-agent that starts a Claude Code session, so no stand-in could send its paragraph to a session or
start an executor (see "What happened to the twelve runs" above). Study 2 measures only the shaping
moment, which needs neither: from a proposal already made to the moment the person would press R.
Nothing is run, no executor starts, and no stand-in starts a session.

### Design

- **The proposal.** For each task, the coordinator runs `graphene ask` once, itself, in a fresh repo
  from `make_task.py` on which `graphene init --planner claude --executor claude` was run as the
  person. The Claude planner proposes once, from the task's sealed paragraph
  (`docs/test/tasks/<task>/paragraph.md`). `shape_only.py setup TASK` makes that repo, in
  `~/graphene-shaping-runs/TASK-shape-planned`.
- **Two copies.** The planned directory is copied whole (`cp -R`) into one run directory per arm,
  `TASK-shape-outline-1` and `TASK-shape-board-1` (`shape_only.py fork TASK ARM`), each with its own
  empty `runlog.jsonl` and its own `env.sh`. Both arms of a task start from the identical proposal,
  byte for byte, which study 1 could not promise: there each arm's session proposed on its own.
- **The person.** A stand-in shapes its copy until it would press R, and stops there. It is the
  person who wrote the paragraph, and its brief (`shape_only.py brief TASK ARM`) says so and shows
  it the paragraph and the card.

### The two arms

| arm | what the person does | how they read the plan |
|---|---|---|
| **outline** | Prunes with `graphene plan accept`, `graphene node drop` and `graphene node set`. It ignores the board. | `graphene plan --text` and `graphene plan` |
| **board** | First answers every open board item, one command each: `graphene board take`, `pick`, `drop`, `park`, `answer` or `note`. Then it prunes with the outline arm's commands. | `graphene board`, then `graphene plan --view auto` |

The build under test has no `--add-scope` or `--add-goal` on `node set` (`graphene node set --help`
at the build below), so neither brief names them; `--scope` replaces the scope and repeats.

### Tasks and runs

The tasks are `feeds`, `inventory`, `logs` and `report`. There is one run per arm per task: **8 runs,
n = 1 per cell.** This is a pilot. It can show which way each difference goes on each task. It
cannot show that a difference is real.

### What is held equal

- **The proposal.** One per task, the same bytes in both arms.
- **The build.** `~/graphene-shaping-venv`, which is the wheel recorded in
  `~/graphene-shaping-runs/build.txt` (commit `668c7fd`, sha256 `5408b89f…`). Its `bin` is first on
  `PATH` in every shell (`env.sh`).
- **The stand-in.** The same model, spawned the same way, one per run and never reused. Both briefs
  come from one template in `shape_only.py` and differ only in the arm section. The stand-in is not
  told what is measured.
- **The card.** Each task's `intent.md`, whole, pasted into the brief by the script, as `standin.py`
  does.

### Metrics, all computed afterwards by a script or a judge

| metric | from | notes |
|---|---|---|
| person-seconds, MODELLED | `attention.py` | K = 0.28 s per typed character, M = 1.35 s per act, reading at 250 words a minute, split into typing + acts + reading, up to the moment the person would press R. A model, never a clock. |
| keys | `attention.py` | typed characters + acts |
| typed characters | `attention.py` | by `attention.py`'s rules, unchanged |
| words read | `attention.py` | every word logged as `read` |
| acts | `attention.py` | every person entry except `read`; each board command is one act |
| faithful to the card | a judge | A separate judge per run, with no part in it, reads the shaped plan (`graphene plan --text` and `graphene board` in the run's repo) against the card. It rules: does the plan do what the card asks and nothing it forbids: **yes / partly / no**. And it counts how many of the card's constraints a leaf, a check or a board answer carries, out of the card's total. The ruling is saved in the run directory. |

### Hypotheses, each with its direction

| | comparison | registered direction | measure |
|---|---|---|---|
| H1 | board against outline | board **lower** | modelled person-seconds |
| H3 | board against outline | board **lower**, on each separately | words read; typed characters |
| H6 | board against outline | board **at least as faithful** | the judge's ruling (yes > partly > no), then constraints carried |

H1 and H3 keep study 1's names so they read side by side. H2, H4 and H5 need a run and are not tested.

### The table that will be reported

| task | arm | run | valid | person-s, MODELLED = typing + acts + reading | typed | acts | keys | words read | ruling | constraints carried |
|---|---|---|---|---|---|---|---|---|---|---|
| feeds | outline | | | | | | | | | |
| feeds | board | | | | | | | | | |
| inventory | outline | | | | | | | | | |
| inventory | board | | | | | | | | | |
| logs | outline | | | | | | | | | |
| logs | board | | | | | | | | | |
| report | outline | | | | | | | | | |
| report | board | | | | | | | | | |

| hypothesis | board minus outline, per task (feeds / inventory / logs / report) | tasks in the registered direction | result |
|---|---|---|---|
| H1: person-s | | of 4 | |
| H3: words read | | of 4 | |
| H3: typed | | of 4 | |
| H6: faithful to the card | | of 4 | |

Under the tables goes one sentence on what they show, whatever it is.

### Analysis rules

1. **n = 1 per cell, so there are no significance claims.** No p-value, interval or test. A
   hypothesis's result is how many of the four tasks go the registered way, with each task's signed
   difference beside it, in study 1's words ("lower" only if all four do; "on three of four tasks,
   one run each" if three do; "no difference shown" if two or fewer do, or if any task is void or not
   run; a task that goes the other way is reported as going the other way).
2. **Every cell is reported,** void and not-run cells included, each with its reason. No mean or
   median stands in for the rows.
3. **Null results are reported,** in the tables and in the sentence.
4. **A run is void** if the `graphene` on `PATH` is not the recorded build, if its copy did not start
   from the task's one proposal, or if the stand-in ran anything (a `graphene run` or an executor).
   A rerun is allowed only when the harness failed; it is named so, and the failed run is kept.
5. **Nothing is tuned once the first run starts:** not the brief, the card, the paragraph, the
   proposal or the build.
6. **Anything decided after the data is labelled "after the fact",** including a re-cut, an
   exclusion or a new column.
7. **What this is evidence about.** Shaping one proposal from the Claude planner, by Claude
   sub-agents standing in for the person, measured with the keystroke-level model. Not about
   whether the shaped plan runs or passes, and not about Nemotron, Token Factory or Sandboxes.

### Study 2 results

*Written after all eight runs, below the registered section, which is not changed. The people were
Claude model stand-ins (claude-opus-5-5, the session's model; the judges the same model), the planner
was Claude Code, and nothing ran: no `graphene run`, no executor, no session. This is evidence about
shaping one Claude-planned proposal, not about Nemotron, Token Factory or Sandboxes. Every number
comes from `python3 docs/test/attention.py <run> --arm tree` (outline runs) or `--arm board` (board
runs) and from `<run>/judge.md`; runs live in `~/graphene-shaping-runs/`. No run logs a `run`, so
the whole log is the part up to R, and `attention.py`'s `to_run` equals its totals in all eight.*

**Valid.** All eight are valid under rule 4: `env.sh` puts `~/graphene-shaping-venv/bin` first on
`PATH`, that venv was installed from the wheel whose sha256 matches `build.txt` (`5408b89f…`); both
arms of each task share one `base.sha`; no run log has a `run` entry, no `node_log` row records a
start, and `git status` in every run's repo shows no change. No rerun was made.

| task | arm | run | valid | person-s, MODELLED = typing + acts + reading | typed | acts | keys | words read | ruling | constraints carried |
|---|---|---|---|---|---|---|---|---|---|---|
| feeds | outline | feeds-shape-outline-1 | yes | 668.9 = 223.7 + 4.1 + 441.1 | 799 | 3 | 802 | 1838 | yes | 18 of 20 |
| feeds | board | feeds-shape-board-1 | yes | 1277.3 = 362.9 + 13.5 + 901.0 | 1296 | 10 | 1306 | 3754 | yes | 19 of 19 |
| inventory | outline | inventory-shape-outline-1 | yes | 426.7 = 62.2 + 4.1 + 360.5 | 222 | 3 | 225 | 1502 | yes | 13 of 13 |
| inventory | board | inventory-shape-board-1 | yes | 1064.0 = 77.6 + 10.8 + 975.6 | 277 | 8 | 285 | 4065 | yes | 13 of 13 |
| logs | outline | logs-shape-outline-1 | yes | 324.1 = 0.0 + 2.7 + 321.4 | 0 | 2 | 2 | 1339 | partly | 12 of 16 |
| logs | board | logs-shape-board-1 | yes | 822.5 = 278.9 + 14.9 + 528.7 | 996 | 11 | 1007 | 2203 | yes | 16 of 16 |
| report | outline | report-shape-outline-1 | yes | 293.2 = 0.0 + 1.4 + 291.8 | 0 | 1 | 1 | 1216 | yes | 12 of 12 |
| report | board | report-shape-board-1 | yes | 649.9 = 0.0 + 8.1 + 641.8 | 0 | 6 | 6 | 2674 | yes | 12 of 12 |

The three parts are K × typed, M × acts and words × 60 / 250, each rounded to 0.1 s, so feeds
board's parts sum to 1277.4 against `attention.py`'s 1277.3. Board commands per board run: feeds
take 5, pick 1; inventory take 4, park 1; logs take 4, answer 2; report take 5.

| hypothesis | board minus outline, per task (feeds / inventory / logs / report) | tasks in the registered direction | result |
|---|---|---|---|
| H1: person-s | +608.4 / +637.3 / +498.4 / +356.7 | 0 of 4 | no difference shown; all four tasks go the other way (board higher), one run each |
| H3: words read | +1916 / +2563 / +864 / +1458 | 0 of 4 | no difference shown; all four tasks go the other way (board higher), one run each |
| H3: typed | +497 / +55 / +996 / 0 | 0 of 4 | no difference shown; three tasks go the other way (board higher), report ties at 0 |
| H6: faithful to the card | feeds same ruling (yes), carried 19 of 19 against 18 of 20 / inventory same (yes, 13 of 13) / logs yes against partly, 16 of 16 against 12 of 16 / report same (yes, 12 of 12) | 4 of 4 | board at least as faithful on all four tasks, one run each: more faithful on logs and feeds, tied on inventory and report |

**After the fact.** (1) The two feeds judges counted the card's constraints differently (20 and
19); board is ahead on feeds whether counted (19 against 18) or as a share (100% against 90%), so
the choice does not change the direction. (2) Two runs report reading outside the log: logs board
read two `--help` screens without logging them (its words read are low by those screens), and
inventory board's first `git ls-files` went unlogged and was run again through the log. Neither
voids a run under rule 4, and neither would change a direction above.

On four tasks, one run each, with model stand-ins shaping a Claude Code proposal and nothing run,
answering the board first cost more modelled attention on every task (H1 and H3 show no difference
in the registered direction; board went the other way on person-seconds and words read on all four,
and on typed characters on three with report tied) while the shaped plan was at least as faithful to
the card on all four (H6: more faithful on logs and feeds, tied on inventory and report).
