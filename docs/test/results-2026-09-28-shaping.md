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

## Results

*Empty until the runs exist.*
