# The board after lane C: the study of 29 September 2026

## Study 4: the board after lane C (registered before any run)

*Written and committed on 2026-09-29, before any run of study 4. The commit that adds this file is the
registration. No study 4 run directory exists yet: `~/graphene-board4-runs` does not exist. Once the
first run starts, this section is not edited. Anything decided later goes below it and is labelled
**after the fact**. This is lane C of `docs/process/directives/FIRST_LIGHT_DIRECTIVE.md`. The runbook
is `docs/test/board-study.md`.*

### Why

Studies 2 and 3 (`results-2026-09-28-shaping.md`) shaped one Claude Code proposal per task in two
arms, stopped where the person would press R, and ran nothing.

- **Study 2 (DIRECTION 98).** Answering the board first cost more modelled person-seconds than the
  outline on 4 of 4 tasks: 1277.3 against 668.9 on feeds, 1064.0 against 426.7 on inventory, 822.5
  against 324.1 on logs, and 649.9 against 293.2 on report. Over the four tasks that is 3813.7
  against 1712.9. The board runs read more words on all four. The shaped plan was at least as
  faithful to the card on all four.
- **Study 3 (DIRECTION 99).** The planner, at prompt version 4, put up at most three items (1 or 2
  per task). The board still cost more on all four tasks: 795.3 against 446.6, 865.5 against 542.9,
  680.7 against 282.1, and 679.6 against 406.8, or 3021.1 against 1678.4 over the four. The gap
  shrank on each task, and the plan was as faithful or more on all four. Every board command in
  study 3 was a `take`: the stand-ins agreed with every default and still paid to read the board and
  to answer it.
- **The directive.** "The board is on by default only if it costs no more than the outline for the
  same correctness. Otherwise it appears only when there is a question the repo cannot answer."
  Study 4 measures that on the build that implements lane C, and the decision rule below sets the
  default of `board:` in `graphene config`.

### What the build changes

1. `graphene board` prints only what answering needs: the open and parked items, each with its
   default and its options. It prints no `then:` lines and no list of settled items; those get one
   count line. `graphene board --all` lists everything, as before. With nothing to ask it prints one
   line, not "0 open", and `graphene plan` and the screen show no board at all.
2. Defaults are taken unless changed. A `graphene plan accept` that leaves no proposal in the plan
   takes the default of every open item that has one, as the person, and says so on its first line
   (`accepted …; took the defaults of …`).
   `graphene run` does the same before it starts. `graphene board take` with no id does it by hand.
   A person who agrees with every default answers nothing.
3. An answer's echo is one short line (`taken ID`, plus what it changed), not the item's words again.
4. `graphene board lookup`, and `GRAPHENE_SHAPE=lookup` after each ask, ask Nano whether the
   repository answers each open question. An answer is kept only when its file and its quoted line
   are in the repository as quoted, and the item is folded as settled "from the repo: FILE".
   `graphene board unpark ID` reopens it. Lookup needs a Token Factory key. **It does not run in
   study 4 and is not measured:** the people are stand-ins, and no key is used tonight.
5. A setting `board: on | auto` in `graphene config`. Unset, it is `on`, which is today's behaviour.
   This study decides the default.

### Design

- **The build.** A wheel of the lane's final code commit, installed in a venv of its own,
  `~/graphene-board4-venv`, as DIRECTION 97 did. The commit, the wheel's name, its sha256 and the
  model the stand-ins run on are written to `~/graphene-board4-runs/build.txt` before the first run,
  and copied into "Deviations" below before the first run. A run on any other `graphene` is void.
- **The proposals are study 3's.** Study 3's four `~/graphene-shaping3-runs/TASK-shape-planned`
  directories are copied whole with `cp -R` to `~/graphene-board4-runs/TASK-shape-planned`. Each
  holds the one proposal the Claude Code planner made for that task at prompt version 4 (build
  `aa9e3e1`), which is the prompt this build still uses. The `*-shape-ask.txt` files are not copied.
  No planner is called tonight. So study 4 differs from study 3 in the build and in the board arm's
  text, not in the proposal. `diff -r` shows each copy is byte for byte the study 3 original before
  any fork. No file under the four planned repos names study 3's venv or runs directory (`grep -rlI
  shaping3` finds none at registration); the planned `env.sh` does, and `fork` writes each run its
  own.
- **Two copies per task.** `SHAPE_STUDY=4 docs/test/shape_only.py fork TASK ARM` copies the planned
  directory into `TASK-shape-outline-1` and `TASK-shape-board-1`, each with its own empty
  `runlog.jsonl` and its own `env.sh` pointing at the venv above. Both arms of a task start from the
  same bytes.
- **The person.** A stand-in shapes its copy until it would press R, and stops there. Nothing runs:
  no `graphene run`, no `graphene ask`, no `graphene board lookup`, no executor, no session. Its brief
  is `SHAPE_STUDY=4 docs/test/shape_only.py brief TASK ARM`, which pastes the task's sealed paragraph
  and card. Nobody who prepares a run opens them.
- **No key.** Every `env.sh` a fork writes unsets `NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID` and sets
  `GRAPHENE_KEYCHAIN=off` (`shape_only.NO_KEY`), so nothing a stand-in runs can reach Token Factory,
  whatever the shell that started it holds.
- **The judge.** A separate judge per run, with no part in it, reads the shaped plan against the card.
  Its brief is below, under "Metrics".
- **The setting.** No copied store sets `board:`, so every run is on `board: on`, today's behaviour.
  `board: auto` is not an arm. The decision rule chooses between `on` and `auto` from the board arm
  against the outline arm, which answers no board.
- **Runs.** The tasks are `feeds`, `inventory`, `logs` and `report`. There is one run per arm per
  task: **8 runs, n = 1 per cell.** Tasks go in that order. A task's two arms start together, each
  with its own fresh stand-in. The next task starts after both stand-ins have finished.

### The two arms

| arm | what the person does | how they read the plan |
|---|---|---|
| **outline** | Prunes with `graphene plan accept`, `graphene node drop` and `graphene node set`. It ignores the board. | `graphene plan --text` and `graphene plan` |
| **board** | Answers only the items whose default it would change, one command each: `pick`, `drop`, `park`, `answer` or `note`. It leaves the rest to accept. Then it prunes with the outline arm's commands. | `graphene board`, then `graphene plan --view auto` |

The outline arm's text is study 2's, byte for byte (`shape_only.ARMS["outline"]`). The board arm's
text changes because the product changed. Under lane C, accepting the plan takes every default that
is left, so the stand-in answers only the items whose default it would change, and `take` is gone
from its list. Everything else in the board arm is study 2's words. The brief around the arm section
is study 2's template, byte for byte. `docs/test/test_shape_only.py::ShapeOnly::test_study_4_changes_the_board_arm_and_nothing_else`
proves both.

The outline arm, as the brief has it (studies 2, 3 and 4):

```
There is a plan, and it is a tree: the root is what you want, its children are
  how it will be done, the leaves are work an agent does.

  1. Read the tree: `seen as_me graphene plan --text` and `seen as_me graphene plan` (a proposal
     is marked). The plan may show board items; leave them alone.
  2. Prune it with these, and nothing else:
       did accept "as_me graphene plan accept <id>"      it, what is above it and under it
       did drop "as_me graphene node drop <id>"          it, and everything under it
       did edit "as_me graphene node set <id> --title '…' --goal '…' --scope '…' --check '…'"
                                                         one node's contract, any of those; --scope
                                                         replaces the scope, repeat it for each path
     A proposal nobody accepts never runs.
```

The board arm, as the brief has it (study 4, `shape_only.STUDY4["board"]`):

```
There is a plan, and it is a tree: the root is what you want, its children are
  how it will be done, the leaves are work an agent does. Before the tree there is a board: the
  planner's questions, each with the answer it would assume if you said nothing, its options where
  it sees more than one way, its assumptions, its risks, and what it would leave out.

  1. Read the board: `seen as_me graphene board`.
  2. Answer only the items whose default you would change, before you look at the tree, each with
     one of these and nothing else:
       did board "as_me graphene board pick <id> <n>"          its option n
       did board "as_me graphene board drop <id>"              not wanted
       did board "as_me graphene board park <id>"              not now
       did board "as_me graphene board answer <id> '<words>'"  your own answer, in your words
       did board "as_me graphene board note '<words>'"         a note of your own, on no item
     Leave the others: accepting the plan takes their defaults, as you.
  3. Read the tree as a graph: `seen as_me graphene plan --view auto` (a proposal is marked).
  4. Prune it with these, and nothing else:
       did accept "as_me graphene plan accept <id>"      it, what is above it and under it
       did drop "as_me graphene node drop <id>"          it, and everything under it
       did edit "as_me graphene node set <id> --title '…' --goal '…' --scope '…' --check '…'"
                                                         one node's contract, any of those; --scope
                                                         replaces the scope, repeat it for each path
     A proposal nobody accepts never runs.
```

### What is held equal, and what differs from studies 2 and 3

| | study 2 | study 3 | study 4 |
|---|---|---|---|
| tasks and cards | the four, card blobs `3600815c2ef5` feeds, `7eb0a1c485fd` inventory, `124ccd01c81a` logs, `5246e8172ac7` report | same | same |
| sealed paragraphs | blobs `2d28b53ce4e0`, `799c3f413397`, `92b72aeeae02`, `d0f33c77d317` | same | same |
| the proposal | its own, prompt version 2, build `668c7fd` | its own, prompt version 4, build `aa9e3e1` | **study 3's**, copied byte for byte |
| the build | `668c7fd`, sha256 `5408b89f…` | `aa9e3e1`, sha256 `6da50769…` | **the lane's final commit**, in `build.txt` |
| brief template, outline arm text, prune commands | `shape_only.py` | same | same, byte for byte |
| board arm text | answer every open item first; `take` is one of six commands | same as study 2 | **answer only what you would change; no `take`** |
| what `graphene board` prints | every item, its `then:` lines, settled items too | same | **open and parked items only, one count line for the rest** |
| an answer's echo | the item's words again | same | **one short line** |
| `graphene plan accept` of the last proposal | leaves open items open | same | **takes every default left, as the person** |
| what the judge reads | `graphene plan --text`, `graphene board` | same | `graphene plan --text`, **`graphene board --all`** |
| metrics and constants | `attention.py`, K = 0.28, M = 1.35, 250 wpm | same | same |
| stand-ins and judges | claude-opus-5-5, one fresh each | same | the model in `build.txt`, one fresh each |
| runs directory | `~/graphene-shaping-runs` | `~/graphene-shaping3-runs` | `~/graphene-board4-runs` |

The judge reads `graphene board --all` because `graphene board` no longer lists settled items. With
`--all` the judge sees every item and answer, as study 2's judge did.

### Metrics, all computed afterwards by a script or a judge

| metric | from | notes |
|---|---|---|
| person-seconds, MODELLED | `attention.py` | K = 0.28 s per typed character, M = 1.35 s per act, reading at 250 words a minute, split into typing + acts + reading. A model, never a clock. |
| typed characters | `attention.py` | by its rules, unchanged. A board command's id and pick's N are chosen, not typed. |
| acts | `attention.py` | every person entry except `read`. Each board command is one act. |
| keys | `attention.py` | typed characters + acts |
| words read | `attention.py` | every word logged as `read`, which includes each command's echo |
| board_acts | `attention.py` | the board commands, counted by name |
| ruling | the judge | does the plan do what the card asks and nothing it forbids: **yes / partly / no** |
| constraints met | the judge | how many of the card's constraints a leaf, a check or a board answer carries, out of the card's total |

The numbers come from `python3 docs/test/attention.py <run> --arm tree` for an outline run and
`--arm board` for a board run, as in studies 2 and 3. `summarize.py` is not used: it skips a run
whose arm is `outline`, and on a board run it runs the task's acceptance checks, which score code
that a run writes, and nothing runs here.

**The judge's brief**, whole, with `<G>` the checkout the study runs from, `<T>` the task and `<R>`
the run directory:

```
You are a judge. You had no part in this run. Read one card and one shaped plan, and rule on the
plan against the card.

  card   <G>/docs/test/tasks/<T>/intent.md
  run    <R>

In every shell, first `source <R>/env.sh`: it puts the pinned build first on PATH and goes to the
run's repo. Then read the shaped plan with `graphene plan --text` and `graphene board --all`. Run
nothing else: no `did`, `seen` or `log` (they write the person's log), no other graphene command, no
`graphene run`, no executor, no test. Change nothing.

An item still open on the board counts as its default: accepting the plan or `graphene run` would
take it, as the person. An open item with no default counts as unanswered.

Rule on two things:
  1. Does the plan do what the card asks and nothing it forbids: yes, partly or no.
  2. How many of the card's constraints a leaf, a check or a board answer carries, out of the
     card's total. List each constraint and where it is carried, or that it is not.

Write <R>/judge.md: the ruling (yes, partly or no) on its first line, "N of M" on its second, then
the list. Hand back those two lines.
```

Study 2's judge brief was never committed. Its registered task is the one in study 2's "Metrics"
row: read `graphene plan --text` and `graphene board` against the card, rule yes, partly or no, and
count the constraints carried. The brief above is written from that row. It changes three things:
`--all`, the rule for an open item, and the format of `judge.md`'s first two lines.

### Hypotheses, each with its direction

| | comparison | registered direction | measure |
|---|---|---|---|
| H1 | board against outline | board **no more than** outline | modelled person-seconds |
| H2 | board against outline | board **no lower** | the judge's ruling (yes > partly > no), then constraints met |
| H3 | study 4's board arm against study 3's board arm | study 4 **lower**, on each task | words read |

H1's direction is "no more than", where studies 2 and 3 had "lower", because that is what the
decision needs. H2 is studies 2 and 3's H6. H3 compares a build and a board arm text together: the
proposal is the same bytes, and the stand-in is a fresh one.

### The table that will be reported

The study 2 and study 3 columns are copied from `results-2026-09-28-shaping.md`. Study 2 shaped a
different proposal, so its columns are a comparison, not a pairing.

| task | arm | run | valid | person-s, MODELLED = typing + acts + reading | typed | acts | keys | words read | board_acts | ruling | constraints met | study 2 person-s | study 2 words read | study 3 person-s | study 3 words read |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| feeds | outline | | | | | | | | | | | 668.9 | 1838 | 446.6 | 1855 |
| feeds | board | | | | | | | | | | | 1277.3 | 3754 | 795.3 | 3297 |
| inventory | outline | | | | | | | | | | | 426.7 | 1502 | 542.9 | 1690 |
| inventory | board | | | | | | | | | | | 1064.0 | 4065 | 865.5 | 3086 |
| logs | outline | | | | | | | | | | | 324.1 | 1339 | 282.1 | 1164 |
| logs | board | | | | | | | | | | | 822.5 | 2203 | 680.7 | 2808 |
| report | outline | | | | | | | | | | | 293.2 | 1216 | 406.8 | 1245 |
| report | board | | | | | | | | | | | 649.9 | 2674 | 679.6 | 2361 |
| all four | outline | | | | | | | | | | | 1712.9 | | 1678.4 | |
| all four | board | | | | | | | | | | | 3813.7 | | 3021.1 | |

Rulings and constraints in the earlier studies: study 2 feeds yes 18 of 20 (outline) and yes 19 of 19
(board), inventory yes 13 of 13 both, logs partly 12 of 16 and yes 16 of 16, report yes 12 of 12 both;
study 3 feeds yes 20 of 20 both, inventory yes 13 of 13 both, logs partly 13 of 16 and partly 14 of
16, report yes 12 of 12 both.

| hypothesis | per task (feeds / inventory / logs / report) | tasks in the registered direction | result |
|---|---|---|---|
| H1: board minus outline, person-s | | of 4 | |
| H2: board against outline, ruling and constraints met | | of 4 | |
| H3: study 4 board minus study 3 board, words read | | of 4 | |

| decision | value | holds |
|---|---|---|
| (a) total person-s over the four tasks, board against outline | | |
| (a) tasks with board person-s at most outline's | of 4 | |
| (b) tasks with board ruling no lower and constraints met at least outline's | of 4 | |
| the default of `board:` | | |

Under the tables goes one sentence on what they show, whatever it is.

### Analysis rules

1. **n = 1 per cell, so there are no significance claims.** No p-value, interval or test. A
   hypothesis's result is how many of the four tasks go the registered way, with each task's
   difference beside it. The words are study 2's: "on all four tasks, one run each" if four do, "on
   three of four tasks, one run each" if three do, and "no difference shown" if two or fewer do or
   if any task is void or not run. A task that goes the other way is reported as going the other way.
2. **Every cell is reported,** void and not-run cells included, each with its reason. No mean or
   median stands in for the rows.
3. **Null results are reported,** in the tables and in the sentence.
4. **A run is void** if any of these holds:
   - the `graphene` on `PATH` is not the recorded build;
   - its copy did not start from the task's one proposal;
   - the stand-in ran anything: a `graphene run`, a `graphene ask`, a `graphene board lookup`, an
     executor or a session.

   A rerun is allowed only when the harness failed. It is named so, and the failed run is kept. A
   stand-in that used a command its brief does not list (such as `board take`) is not void; the
   command is counted as `attention.py` counts it and reported.
5. **Nothing is tuned once the first run starts:** not the brief, the card, the paragraph, the
   proposal, the build or the judge's brief.
6. **Anything decided after the data is labelled "after the fact",** including a re-cut, an
   exclusion or a new column.
7. **What this is evidence about.** Shaping one Claude Code proposal per task on lane C's build, by
   Claude sub-agents standing in for the person, at the command line, measured with the
   keystroke-level model. It is not evidence about the screen, lookup, whether the shaped plan runs
   or passes, or Nemotron as the planner.
8. **Constraints met** are compared as counts when a task's two judges counted the same total. When
   they counted different totals, they are compared as shares of each judge's own total.
9. **The decision rule below is applied to the table by arithmetic,** with no judgement added. If a
   run is void or not run and has not been rerun under rule 4, the rule cannot be shown to hold, and
   the default is `board: auto`.
10. **The decision is written into `docs/DIRECTION.md`** as a numbered decision, with the table as its
    evidence. If the default is `auto`, the code's unset value changes to `auto` in its own commit,
    with a test.

### The decision rule

"Costs no more than the outline for the same correctness" means BOTH (a) the board arm's total
modelled person-seconds over the four tasks is at most the outline arm's total, and on at least 3 of
the 4 tasks the board arm's seconds are at most the outline's, AND (b) on every task the judge's
verdict for the board arm is no lower than the outline arm's and its constraints met are at least the
outline arm's. If both hold, the default is `board: on`; otherwise `board: auto`.

### Known threats

- **n = 1 per cell.** One run per arm per task. Each difference is one stand-in against another. It
  can show a direction on these four tasks and cannot show that a difference is real.
- **Stand-ins, not people.** The people are Claude sub-agents. A stand-in decides which defaults it
  would change, and a person may decide differently. The judges are the same model.
- **The command line, not the screen.** The board is read through `graphene board` and the tree
  through `graphene plan --view auto`. `graphene watch`, where a person would do this, is not
  measured. DIRECTION 98 asked for the design again on the screen.
- **Lookup is not measured.** It needs a Token Factory key, and study 4 uses none. Every item the
  planner put up stays on the board, including any the repository would have answered. The board
  arm pays for reading those, so this study measures the board without the part of lane C that asks
  only what the repo cannot answer.
- **The proposals are reused.** Study 4 shapes study 3's four proposals, so it is not independent of
  study 3: a proposal that happened to suit one arm suits it again. The proposals were made by the
  build `aa9e3e1`, and this build must open their stores; a pre-run check shows that it does.
- **The same tasks and cards made the change.** Lane C's changes follow from studies 2 and 3 on these
  four tasks and cards. Study 4 can show which way the direction goes on them. A confirmation needs
  tasks and cards that played no part in the change.
- **The outline arm's text is fixed, and its screens are not.** Its words are study 2's, but it reads
  what this build prints for `graphene plan --text` and `graphene plan`, which may differ from
  study 3's build.
- **Reading dominates the model.** Words read include every `--help` screen and file a stand-in reads
  through `seen`. A stand-in that reads more files pays for it in either arm. Reading off the log is
  not counted.
- **Judges count constraints differently.** In study 2 the two feeds judges counted 20 and 19. Rule 8
  covers the comparison; the count itself stays each judge's.
- **An unaccepted plan keeps its open items.** If a stand-in stops before accepting every proposal,
  the defaults are not taken in the store. The judge counts an open item as its default, since
  `graphene run` takes it before it starts.

### Deviations, written before the first run

**02:25, the build and the pre-run checks, done by lane C before any run.**
`~/graphene-board4-runs/build.txt`:

```
commit 4acc6ea4f6567f65ea322bae0c06539702a14bc2
wheel graphene_map-0.5.0-py3-none-any.whl
sha256 f79f7102c7c53ee6c31b7386819ba431f786226357442c5cf3d346fab1dbbbef
stand-ins: claude-opus-5-5, judges the same
```

The wheel is of `4acc6ea`, the lane's last code commit, made after this registration's commit
(`f304da0`): lookup no longer sends a protected file to Nano. Lookup does not run in this study, so
the arms are as registered. The coordinator corrects the stand-ins' line if they run on another
model, here and in `build.txt`, before the first run. The pre-run checks in `board-study.md` passed:
`graphene` is the venv's (0.5.0); `graphene board --help` lists take, pick, drop, park, unpark,
answer, note and lookup; each of the four copies is `diff -r` identical to study 3's planned
directory; in a throwaway copy of each, `graphene plan`, `plan --text`, `board --all` and `graphene
config` run on this build and no copy sets `board: auto`; four `paragraph.md` are listed, none
opened, and the eight task blobs are the ones registered above; `GRAPHENE_SHAPE` is unset. No run
directory (`TASK-shape-ARM-1`) exists yet.

**02:50, the coordinator, before the first run.** Two changes to how the runs are made, none to what
they measure:
- **`G` is a checkout of `first-light` at `5ab0dca`** (at `…/scratchpad/study4`), not the lane's
  worktree. The files a run's `env.sh` and the table use (`docs/test/logline.py`, `shape_only.py`,
  `attention.py`, `newrun.sh` and `docs/test/tasks/`) are byte-identical between the two
  (`git diff --stat fl-board 5ab0dca -- …` is empty). The build every stand-in runs is the pinned
  wheel above, whatever `G` holds.
- **The four tasks run at once, not one after another.** All eight stand-ins start together, and each
  judge starts when its run ends. Every stand-in and every judge is a fresh sub-agent with no memory of
  any other run, so no order can carry over from one task to the next; the order was there for a
  person's fatigue, which a stand-in does not have. The stand-ins and the judges are
  claude-opus-5-5, as `build.txt` says.

**03:05, the coordinator, after the eight runs and before any table.** The inventory board run's
stand-in reported that this session's permission classifier refused two of its commands, both through
`as_me`, which its brief lists ("Auto-Mode Bypass"): `seen as_me graphene plan --view auto`, and a
`handwork` act; it stopped before accepting anything. That is the harness failing, so under rule 4 it
is rerun once, from a fresh fork of the same proposal, as `inventory-shape-board-1`; the failed run
is kept as `inventory-shape-board-1-harness-failed` and reported. No brief, card, proposal, build or
judge's brief changed.

### Study 4 results
