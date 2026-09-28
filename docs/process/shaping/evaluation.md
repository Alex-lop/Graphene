# Lane A evaluation: the board as rows or as a view, and the graph views

This file holds the evidence for the "How to decide" step of `docs/process/directives/SHAPING_DIRECTIVE.md`. It does not make the decision. Every number below was computed from the logged tmux seat (`eval/tt.sh`). The trials' final plan state was read back from copies of each trial's store, and the thirty-leaf ground truth was computed with `graphene_map.plan_view` from the `lane-a` worktree.

**How the numbers were computed**
- **keys**: one per entry in a `keys` act, plus one per character of a `type` act. Because typed characters count, a single `:node set ... --goal "..."` line adds 280 to 670 keys. The tables therefore split keys into **pressed** (keys acts) and **typed** (characters).
- **looks**: the number of `see` acts.
- **words**: the sum of the word counts of those `see` acts.
- **secs**: the last timestamp minus the first. This is agent wall-clock time, and it includes the stand-in's own thinking.
- **stalls**: the count the trial report gives.

**Log caveat**
- In 7 trials the seat logged only the `start` line into the trial directory. Every later act went to `eval/logs/<id>.jsonl` because `LOGS` was not set on those calls. Those 7 are `alex-rows-feeds-80x24`, `alex-view-feeds-120x36`, `first-rows-feeds-120x36`, `judge-rows-night-80x24`, `judge-view-night-120x36`, `alex-graph-thirty` and the rest of `alex-graph-thirty-wide`.
- The two files were merged by timestamp, and no act appears in both. Every trial's first `see` word count equals the word count of a fresh render of the same candidate, plan and size (§6), so the merged logs belong to the right seats.

**The design is confounded, so read every comparison with this in mind**
- alex and judge ran **rows at 80x24** and **view at 120x36**.
- first ran **rows at 120x36** and **view at 80x24**.
- So rows has 4 trials at 80x24 and 2 at 120x36, and view has the reverse.
- Each persona ran both plans under both candidates.
- alex's and first's four board trials all started within 6 s of each other (t = 1790579143 to 149), so they ran in parallel. judge's trials ran partly in sequence: rows-feeds at …145, view-night at …337, view-feeds at …354 and rows-night at …391. judge's later trials may therefore carry some learning.
- In the graph trials, the 120x36 seat always came **after** the 80x24 seat, with the same persona and the answers already known.

## 1. Per trial

Board trials (candidate `rows` = `lane-a-board-rows`, `view` = `lane-a-board-view`):

| trial | cand | plan | size | keys (pressed + typed) | looks | words read | secs | stalls | done | clarity |
|---|---|---|---|---|---|---|---|---|---|---|
| alex-rows-feeds-80x24 | rows | feeds | 80x24 | 465 (29 + 436) | 25 | 4264 | 223 | 6 | yes | 4 |
| judge-rows-feeds-80x24 | rows | feeds | 80x24 | 20 (20 + 0) | 18 | 3040 | 159 | 3 | yes | 4 |
| first-rows-feeds-120x36 | rows | feeds | 120x36 | 641 (28 + 613) | 21 | 4707 | 208 | 4 | yes | 4 |
| alex-rows-night-80x24 | rows | night | 80x24 | 340 (56 + 284) | 38 | 7922 | 376 | 5 | yes | 4 |
| judge-rows-night-80x24 | rows | night | 80x24 | 84 (84 + 0) | 35 | 7034 | 359 | 5 | yes | 4 |
| first-rows-night-120x36 | rows | night | 120x36 | 32 (32 + 0) | 25 | 8610 | 225 | 6 | yes | 4 |
| first-view-feeds-80x24 | view | feeds | 80x24 | 713 (39 + 674) | 33 | 5381 | 299 | 4 | yes | 4 |
| alex-view-feeds-120x36 | view | feeds | 120x36 | 472 (22 + 450) | 19 | 3818 | 177 | 4 | yes | 4 |
| judge-view-feeds-120x36 | view | feeds | 120x36 | 478 (22 + 456) | 20 | 4027 | 194 | 4 | yes | 4 |
| first-view-night-80x24 | view | night | 80x24 | 427 (106 + 321) | 51 | 10391 | 454 | 5 | yes | 4 |
| alex-view-night-120x36 | view | night | 120x36 | 27 (27 + 0) | 24 | 6449 | 247 | 4 | yes | 4 |
| judge-view-night-120x36 | view | night | 120x36 | 28 (28 + 0) | 25 | 6789 | 231 | 5 | yes | 4 |

Graph trials (all on `lane-a`, the `thirty` plan; each is an 80x24 seat followed by a 120x36 seat):

| trial | size | keys (pressed + typed) | looks | words read | secs | stalls | done | clarity |
|---|---|---|---|---|---|---|---|---|
| alex-graph-thirty | 80x24 | 55 (47 + 8) | 18 | 3059 | 177 | 11 (both seats) | yes | 3 |
| alex-graph-thirty-wide | 120x36 | 3 (3 + 0) | 4 | 1397 | 44 | (above) | | |
| first-graph-thirty | 80x24 | 90 (49 + 41) | 31 | 5616 | 316 | 11 (both seats) | yes | 3 |
| first-graph-thirty-wide | 120x36 | 19 (9 + 10) | 6 | 2002 | 74 | (above) | | |
| judge-graph-thirty | 80x24 | 65 (65 + 0) | 29 | 5158 | 309 | 8 (both seats) | yes | 4 |
| judge-graph-thirty-wide | 120x36 | 16 (16 + 0) | 6 | 1969 | 69 | (above) | | |

## 2. By candidate, plan and size (board trials)

Each cell gives the total and the median.

| group | n | keys | pressed | looks | words read | secs | stalls | completed | clarity |
|---|---|---|---|---|---|---|---|---|---|
| **rows** | 6 | 1582 / 212 | 249 / 30.5 | 162 / 25 | 35577 / 5870.5 | 1550 / 224 | 29 / 5 | 6/6 | 4 (all) |
| **view** | 6 | 2145 / 449.5 | 244 / 27.5 | 172 / 24.5 | 36855 / 5915 | 1602 / 239 | 26 / 4 | 6/6 | 4 (all) |
| rows · feeds | 3 | 1126 / 465 | 77 / 28 | 64 / 21 | 12011 / 4264 | 590 / 208 | 13 / 4 | 3/3 | 4 |
| view · feeds | 3 | 1663 / 478 | 83 / 22 | 72 / 20 | 13226 / 4027 | 670 / 194 | 12 / 4 | 3/3 | 4 |
| rows · night | 3 | 456 / 84 | 172 / 56 | 98 / 35 | 23566 / 7922 | 960 / 359 | 16 / 5 | 3/3 | 4 |
| view · night | 3 | 482 / 28 | 161 / 28 | 100 / 25 | 23629 / 6789 | 932 / 247 | 14 / 5 | 3/3 | 4 |
| rows · 80x24 | 4 | 909 / 212 | 189 / 42.5 | 116 / 30 | 22260 / 5649 | 1117 / 291 | 19 / 5 | 4/4 | 4 |
| view · 80x24 | 2 | 1140 / 570 | 145 / 72.5 | 84 / 42 | 15772 / 7886 | 753 / 376.5 | 9 / 4.5 | 2/2 | 4 |
| rows · 120x36 | 2 | 673 / 336.5 | 60 / 30 | 46 / 23 | 13317 / 6658.5 | 433 / 216.5 | 10 / 5 | 2/2 | 4 |
| view · 120x36 | 4 | 1005 / 250 | 99 / 24.5 | 88 / 22 | 21083 / 5238 | 849 / 212.5 | 17 / 4 | 4/4 | 4 |

**Paired within persona and plan.** Each pair has the same person and plan, and differs in candidate and size together:

| persona · plan | rows (size): pressed / words / secs / stalls | view (size): pressed / words / secs / stalls |
|---|---|---|
| alex · feeds | 80x24: 29 / 4264 / 223 / 6 | 120x36: 22 / 3818 / 177 / 4 |
| alex · night | 80x24: 56 / 7922 / 376 / 5 | 120x36: 27 / 6449 / 247 / 4 |
| judge · feeds | 80x24: 20 / 3040 / 159 / 3 | 120x36: 22 / 4027 / 194 / 4 |
| judge · night | 80x24: 84 / 7034 / 359 / 5 | 120x36: 28 / 6789 / 231 / 5 |
| first · feeds | 120x36: 28 / 4707 / 208 / 4 | 80x24: 39 / 5381 / 299 / 4 |
| first · night | 120x36: 32 / 8610 / 225 / 6 | 80x24: 106 / 10391 / 454 / 5 |

In 5 of the 6 pairs, the **120x36** trial is the cheaper one on pressed keys, words and seconds, whichever candidate it used. The exception is judge · feeds. There, the rows trial took the `enable` default, so it needed no leaf edit, while the view trial picked "no" and rewrote xml-wire.

**Board answers reached.** I read these from each trial's store with `graphene board --json` on a copy.
- All 60 items across the 12 trials are settled, with none dropped or parked.
- **night**: all 6 trials gave identical answers: overlap take, reask pick 1, never take, store take, keychain take.
- **feeds**: 5 of 6 gave src-name take, enable pick 1 ("no, Ops enables it later"), zero-scope take, e2e-hollow take and hands-off take.
- judge-rows-feeds-80x24 took the `enable` default ("yes, add it to ENABLED_SOURCES"), with the reason that config/defaults.py "is neither vendored nor legacy". The same judge picked "no" in judge-view-feeds-120x36, so this persona's answer differed between the two candidates.

**Tree changes reached.** I read these from `graphene plan --json` on each copy.

| trial | leaf changes left in the store |
|---|---|
| all 5 feeds trials that picked enable "no" | xml-wire at rev 3, config/defaults.py out of its scope, and a goal that now says Ops enables the source and the test patches ENABLED_SOURCES. Each was done by hand with `:node set`. |
| first-view-feeds-80x24 | also zero-skip at rev 2, with `tests.test_contract` added to its check |
| judge-rows-feeds-80x24 | nothing changed (xml-wire at rev 1 still says "Enable the source", which fits its "yes" pick) |
| alex-rows-night-80x24, first-view-night-80x24 | ask-flags at rev 2, with the reask pick written into the goal |
| the other 4 night trials | ask-flags left at rev 1, "(see [reask])" |

Every trial ended with the whole plan accepted: 4 nodes open on feeds and 15 on night. Every trial answered the two closing questions right against `critical_path`/`at_once` on its final store:
- feeds: at once xml-reader and zero-skip; critical path xml-reader > xml-wire.
- night: at once key-store, settings and sizing; critical path settings > ask-told > ask-flags.

## 3. Graph trials (thirty, on lane-a)

**Ground truth.** I computed it from a copy of `eval/thirty`'s store, and the three trial stores were confirmed unchanged afterwards.
- `critical_path` = `v-dupes > v-rules`. cli-import > cli-exit and cli-import > cli-progress are also 2 long. The tie goes to plan order: the `critical_path` docstring says "Ties go to `plan.order`'s first", and v-dupes comes first.
- `at_once` = v-dupes, r-email, r-limit, cli-import, cli-dry, v-empty, d-usage, d-dialects, d-report (9). It counts proposed leaves and the leaf that came back.
- **What `R` starts**, from node states (open, agent-owned, nothing unmet, and not came back) = r-email, r-limit, cli-import, cli-dry (4). The status line shows this number.
- The dag footer "8 at once" is `at_once` minus v-dupes, which came back. Verbatim at both widths: `8 at once · 3 wait · 2 running · 3 on you · 14 done · critical path: v-dupes > v-rules (2)`.
- **Running**: v-price and r-json.
- **Waiting**: v-rules on v-dupes (came back); cli-exit and cli-progress on cli-import (ready).
- **On the person**: v-dupes (came back), r-format (review) and cli-review (yours), which the dag counts as "3 on you". The four proposed leaves (v-empty, d-usage, d-dialects, d-report) are what brings the status line to "you: 5".
- Aside: `graphene plan --view tree --width 80` prints "the tree does not fit at 80 columns: the outline". The watch screen's Tab gives no such notice. The same CLI's last line reads "next: v-dupes (duplicate skus in one feed) is ready", though the screen calls it "came back".

**Which view answered which question, and whether the answer was right:**

| question | alex | first | judge | right? |
|---|---|---|---|---|
| Q1 what runs | 80: dag, `j` through and `/v-dupes` to find ● rows. 120: outline, no keys | outline ● rows at both sizes | outline rows at both sizes ("running", "quiet for 31–35 min") | all 3 right (v-price, r-json) |
| Q2 what waits on what | 80: outline goal pane "waiting" paragraph (after C-d), and dag edges. 120: outline confirmed, dag `G` | goal pane "waiting" paragraph, dag edges, and tree at 120 as a cross-check | goal pane "waiting" paragraph, dag edges as a check | all 3 right |
| Q3 critical path | 80: guessed from the heavy dag edge (footer cut). 120: dag footer | 80: heavy edge only. 120: dag footer | 80: heavy edge only. 120: dag footer | all 3 right on the path. All 3 explained the tie wrongly: alex "my guess is that it is blocked on me", judge "v-dupes wins because it came back and waits on a person's choice". The code breaks the tie by plan order. |
| Q4 what `R` starts | status line "R: 4 ready" and outline ready rows (dag ○ at 80) | status line and outline ready rows | outline ready rows and status line | all 3 right (4). All 3 flagged the dag's "8 at once" as a contradicting number. |

- **Tree view**: none of the three reached it at 80x24, because Tab skips it silently. At 120x36 all three used it only as a cross-check. alex: "used it only to confirm the leaf set". first: "checking every answer at a glance". judge: "a cross-check".
- **Graph stalls**: alex 11, first 11 and judge 8, with a clarity of 3, 3 and 4. Most are 80x24 truncation and count-mismatch issues, grouped in §4.

## 4. Stalls grouped by cause

These are the board trials' 55 stalls and the graph trials' 30, each counted once under its main cause. Board: A 11, B 9, C 6, D 4, E 6, F 3, G 4, H 2, I 2, J 1, K 6, L 1. Graph: C 5, D 1, F 6, I 7, J 4, M 7.

**A. A board pick did not reach the leaf's contract (11 board stalls, 10 of 12 board trials; judge-rows-feeds and judge-view-night are the two without one).**
- feeds, 6 stalls in 5 trials. The 5 are alex-rows, alex-view, first-view, first-rows and judge-view. The sixth stall is judge-view's reading of the ambiguous "then" row, which sits under option 1.
  - alex-rows-feeds: "I read the xml-wire goal twice. It still said 'Enable the source' and still had config/defaults.py in its scope, even though I had just picked 'no, Ops enables it'. The pick's 'then:' line only restated the same check."
  - first-rows-feeds, screen: `goal Add a FIELD_MAPS entry ... Enable the source, name it in USAGE ...` / `scope normalize/fields.py, config/defaults.py, cli/main.py, README.md, tests/test_xmlfeed.py`.
  - judge-view-feeds: "I read the 'then  check xml-wire: python3 -m unittest -q tests.test_xmlfeed' row twice… It named a check identical to the current one, so I could not see what picking would change."
- night, 5 stalls in 5 trials: alex-view, alex-rows, first-rows, first-view and judge-rows. The ask-flags goal says "(see [reask])" and does not state the pick.
  - judge-rows-night: "nothing on the leaf shows whether my pick went into its contract or whether it still follows the default."
- Both candidates are affected about equally: 5 of the stalls are in rows trials and 6 in view trials.

**B. Editing a goal or scope without `$EDITOR`: help does not name `node set`, and `node set --help` wraps badly (9 board stalls in 7 trials).**
- The 7 trials: alex-rows-feeds ×2, alex-view-feeds ×2, alex-rows-night, first-view-feeds, first-rows-feeds, first-view-night and judge-view-feeds.
- alex-view-feeds: "The help lists e/E ($EDITOR, disabled here) and ':<command>', but not which command or flag edits a goal."
- first-rows-feeds, screen: "side pane after ':node set --help': 'Usage: graphene node set [OPTIONS] {node_id}' with the '╭─ Options ──' box borders wrapped onto three lines each".
- first-view-night: "the border characters and the option descriptions split across lines ('clears │ / it.')".

**C. The critical-path footer is cut off at 80 columns, and nothing explains the heavy line (6 board stalls, all at 80x24, plus 5 graph stalls).**
- Board: alex-rows-feeds, alex-rows-night, first-view-feeds, first-view-night, judge-rows-feeds and judge-rows-night.
  - judge-rows-night, screen: `graphene watch --view dag: 3 at once now · 8 wait · critical path: settings >…`. "Moving the cursor replaced that line with key hints, and I found no way to bring it back."
- Graph: all three personas.
  - first, screen: `graphene watch --view dag: 8 at once · 3 wait · 2 running · 3 on you · 14…`
  - first: "The heavy edge (━━▸) against the light edge (──▸) is never explained."
  - first: "The summary with the critical path shows only right after Tab."

**D. The critical path is a tie, and the screen does not say why this chain was picked (4 board stalls, 1 graph stall).**
- Board: alex-view-night, alex-view-feeds, first-rows-night and judge-view-night. judge-view-feeds names it under cost.
- Graph: alex.
- alex-view-night: "'critical path: settings > ask-told > ask-flags (3)': I read it twice because key-store > key-cli > cli-wire and settings > config-cli > cli-wire are also 3 leaves long."
- The code breaks the tie by plan order (§3), and no screen says so.

**E. Key hints replaced by the echo of the last command after a board action (6 board stalls: 4 rows, 2 view).**
- rows: alex-rows-feeds, first-rows-feeds, judge-rows-feeds and judge-rows-night. view: judge-view-night and judge-view-feeds.
- Screen (first-rows-feeds): `graphene board pick enable 1: picked enable: `config/defaults.py` says ...` while the pane showed zero-scope.
- judge-view-night: "The detail pane showed no 'y default' or option lines for an assumption, and the bottom line still showed the result of my last command." Assumptions and leave-outs carry no `y` row, so the key is invisible exactly on those items.

**F. Counts that disagree (3 board stalls, 6 graph stalls).**
- Board: "waiting on you: 4" against "5 open" (alex-view-night). The same count still reads 4 after the board is settled (first-rows-night). "you: 1" on the settled board (judge-rows-feeds).
  - The first screens show why: on feeds, rows says `you: 6` and view says `you: 1`. On night, rows says `waiting on you: 9` and view says `waiting on you: 4`. rows counts the board items in "you" and view does not. Both count proposed sub-goals.
- Graph: all three personas.
  - "8 at once" against "R: 4 ready". judge: "I couldn't work out what the 8 counts."
  - "you: 5" against "3 on you" against the tree's "3 wait on you".

**G. No cursor visible in the captured text (4 board stalls, plus mentions in 3 more).**
- first-view-feeds, first-rows-feeds, first-rows-night and judge-view-night. judge-graph and alex-view-night mention it under cost.
- `tmux capture-pane -p` drops attributes, so this is probably the capture losing reverse video rather than the product. judge-view-night says so itself.

**H. dag edges that cross (2 board stalls).**
- alex-view-night: "Where the edges from key-store and settings cross ('━━━━┱┼┬│─▸', '┗││━━▸') I could not tell which source goes to which leaf." judge-rows-night reports the same.

**I. Fold and scroll friction at 80x24 (2 board stalls, 7 graph stalls).**
- Board, alex-rows-night:
  - "Pressed l expecting it to unfold, as in vim. It opened 'keys · output of attempt 1 / nothing yet'."
  - "The detail cuts off after goal… The only way I found to reach them was C-d."
- Graph:
  - The outline opens folded at 80 (alex).
  - The "waiting" paragraph is cut off at "for ▇" (alex, first).
  - `j` and `G` move column by column in the dag (all three).
  - The dag lists done leaves first, about 14 `j` presses before the first live one (alex).

**J. The tree view is missing or truncated (1 board stall, 4 graph stalls).**
- Tab skips the tree at 80 columns with no notice: all three graph personas.
- The tree shows ←1 but not what a leaf waits on (alex-graph).
- Tree titles are cut to one or two words (first-view-night).

**K. Judging the plan's content, not the UI (6 board stalls).**
- first-rows-night: `P._person_only` and `T.run_editor` go unexplained, and cond-reads scopes all of planner.py.
- first-view-night: whether key-cli needs key-use.
- judge-view-night: "accepting any of it accepts it", and there is no leave-out section on night.
- alex-rows-feeds: "revision 3" is unexplained.

**L. The harness, not the product (1).** judge-rows-night: "`zR` … my own tool harness blocked it, probably because it contains R."

**M. Graph-only (7 graph stalls).**
- help has no legend for ● ◆ ◇ ◌ ↩ ? ○ ✓ or ←1.
- `l` and `n` each have two meanings.
- A running leaf shows "quiet for 31–35 min" with nothing that separates stalled from alive.
- "plan first: on" leaves it unclear whether `R` starts the 4 leaves.
- A leaf's pane says what it needs, never what waits on it.

## 5. What cut effort and what cost it, in the personas' words

**Board, both candidates, what cut effort:**
- "The board presented one item at a time, and each of the five had a clear default or option list, so most items took a single key." (alex-rows-feeds)
- "The board put the default and the options right under each item, and y/1 closed it and moved to the next open one without me navigating." (alex-view-night)
- "Board items fold away into '✓ 5 settled' as they are answered. One y on the goal accepts the whole plan." (judge-rows-feeds)
- "'nothing open: Tab for the tree' told me the next step." (judge-view-feeds). first-view-night named the same line.
- "The dag view's bottom line answered both final questions directly." (first-rows-night). Seven trials said something similar.

**Board, what cost effort:**
- "Picking option 1 on enable did not flow into the xml-wire contract, so I had to find the contradiction myself and rewrite the goal by hand, in a long ':' line with shell quoting." (alex-view-feeds)
- "Reading 11 leaf contracts one by one to check them against a long paragraph; this was most of the effort… with no screen view that lists all scopes together or flags a leaf touching a file I named." (first-rows-night)
- "Getting past the fold on each leaf's detail with C-d." (alex-rows-night, rows at 80)
- "I had to open each of the 11 leaves one by one in the outline and often scroll the detail pane with C-d." (first-view-night, view at 80)
- "The long board rows were cut off with an ellipsis in the list until selected, which meant moving onto each one to read it." (alex-view-feeds)
- "the tree cells truncate every description at about 25 characters." (judge-view-night)

**Graph, what cut effort:**
- "At 120x36 the outline alone answered questions 1, 2 and 4 on the first screen with no keys pressed, because unfinished branches open and every row carries a state word." (alex)
- "The goal's 'waiting' paragraph answered question 2 whole in one place." (first)
- "The outline pairs every glyph with a word, and the status line 'R runs 4 ready' answers question 4 directly." (judge)

**Graph, what cost effort:**
- "At 80x24: the folded outline, the cut-off dag footer (which hid the critical path), the dag listing done leaves first, and j wrapping between columns." (alex)
- "Question 3 could not really be answered at 80x24, and question 4 had two conflicting numbers (4 ready against 8 at once)." (first)
- "the help is 5 screens long with no glyph legend." (judge)

## 6. The renders

Each render is the seat's first screen: `eval/tt.sh <s> start WxH <fresh copy of eval/<plan>> <checkout>`, then `see` after about 6 s. The copies are under the scratchpad's `render-repos/`. The trial logs hold only word counts, not screen text, so every render was captured fresh.

**Match check.** For every trial, its first `see` word count equals the fresh render's:

| render | words | trial first-see words |
|---|---|---|
| rows-feeds 80x24 | 199 | 199 (alex, judge) |
| rows-feeds 120x36 | 234 | 234 (first) |
| rows-night 80x24 | 244 | 244 (alex, judge) |
| rows-night 120x36 | 408 | 408 (first) |
| view-feeds 80x24 | 186 | 186 (first) |
| view-feeds 120x36 | 266 | 266 (alex, judge) |
| view-night 80x24 | 215 | 215 (first) |
| view-night 120x36 | 396 | 396 (alex, judge) |
| lane-a-thirty 80x24 | 232 | 232 (all graph seats at 80) |
| lane-a-thirty 120x36 | 475 | 475 (all graph seats at 120) |

rows-thirty and view-thirty have no trial. They show that the thirty store carries 5 board items, which lane-a's watch, the one the graph trials used, does not show.

Files: `docs/process/shaping/screens/{rows,view}-{feeds,night,thirty}-{80x24,120x36}.txt` and `lane-a-thirty-{80x24,120x36}.txt`. The texts follow. The title line carries the scratchpad path of the render copy.

### rows-feeds-80x24

```text
 the plan of …6-450c-8a0f-177242891dc7/scratchpad/render-repos/rows-feeds-80x24
▼ ? Load the Northwind XML feed with the same `cli.main load ……      proposed
├   ◇ What should the source be called on the command…   src-name    asks
├   ◇ `config/defaults.py` says "Ops edits this…         enable      asks
├   ◇ "Skip a price of 0" applies only to the load…      zero-scope  assumes
├   ◇ The end-to-end check could pass with the wrong…    e2e-hollow  risk
├   ◇ `vendor/tinydec.py`, `legacy/priceimport.py`…      hands-off   leaves out
└ ▼ ? Northwind XML loads like csv and json              xml         proposed
  ├   ? Reader for the XML feed                          xml-reader  proposed
  ├   ? Zero price is skipped for every source           zero-skip   proposed
  └   ? Wire the source end to end                       xml-wire    proposed
────────────────────────────────────────────────────────────────────────────────
 What should the source be called on the command line?
 src-name · question · open · put up by the planner (graphene ask)

 y default  `xml`, which matches the existing format-named sources `csv` and
            `json`
 1          `northwind`, named after the supplier
 about      xml-wire  Wire the source end to end



 you: 6 · 0 running · none ready · 0/0 done · plan first: on
 y take: `xml`, which… · 1 pick · d drop · p park · Enter answer · a note
```

### rows-feeds-120x36

```text
 the plan of …-AllThingsAgenticHackathon/d3d5effe-ac06-450c-8a0f-177242891dc7/scratchpad/render-repos/rows-feeds-120x36
▼ ? Load the Northwind XML feed with the same `cli.main…      proposed   │ What should the source be called on the
├   ◇ What should the source be called on the…    src-name    asks       │ command line?
├   ◇ `config/defaults.py` says "Ops edits…       enable      asks       │ src-name · question · open · put up by the
├   ◇ "Skip a price of 0" applies only to the…    zero-scope  assumes    │ planner (graphene ask)
├   ◇ The end-to-end check could pass with the…   e2e-hollow  risk       │
├   ◇ `vendor/tinydec.py`…                        hands-off   leaves out │ y default  `xml`, which matches the
└ ▼ ? Northwind XML loads like csv and json       xml         proposed   │            existing format-named sources
  ├   ? Reader for the XML feed                   xml-reader  proposed   │            `csv` and `json`
  ├   ? Zero price is skipped for every source    zero-skip   proposed   │ 1          `northwind`, named after the
  └   ? Wire the source end to end                xml-wire    proposed   │            supplier
                                                                         │ about      xml-wire  Wire the source end to
                                                                         │            end
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
 waiting on you: 6 · executors: none · nothing ready to run · 0/0 done · plan first: on (P)
 y take: `xml`, which matches the… · 1 pick: `northwind`, named after… · d drop · p park · Enter answer · a note
```

### rows-night-80x24

```text
 the plan of …6-450c-8a0f-177242891dc7/scratchpad/render-repos/rows-night-80x24
▼ ? Graphene has settings a person states once: where the Token…     proposed
├   ◇ does a broad scope that also covers a protected…   overlap     asks
├   ◇ what does graphene ask --finer (or --coarser)…     reask       asks
├   ◇ "things the planner must never propose": is this…  never       asks
├   ◇ the settings live in the store's plan_meta…        store       assumes
├   ◇ a key passed on argv shows up in ps, and an…       keychain    risk
├ ▶ ? the Token Factory key                              keys        3 proposed
├ ▶ ? standing conditions                                conditions  3 proposed
├ ▶ ? plan size                                          size        3 proposed
└ ▶ ? graphene config                                    config      2 proposed
────────────────────────────────────────────────────────────────────────────────
 does a broad scope that also covers a protected or read-only path "break" the
 conditions (say src/** when src/graphene_map/ui/static/** is read-only)?
 overlap · question · open · put up by the planner (graphene ask)

 y default  yes: at propose and edit, a scope is refused when it matches any
            tracked file under a protected or read-only glob (P.overlap with
            P.tracked); at done, a changed path under one is refused
 1          no: the conditions are cut out of every scope, so src/** is
            allowed, and only a changed path under a condition is refused at
            done
 you: 9 · 0 running · none ready · 0/0 done · plan first: on
 y take: yes: at propose… · 1 pick · d drop · p park · Enter answer · a note
```

### rows-night-120x36

```text
 the plan of …-AllThingsAgenticHackathon/d3d5effe-ac06-450c-8a0f-177242891dc7/scratchpad/render-repos/rows-night-120x36
▼ ? Graphene has settings a person states once: where the…      proposed │ does a broad scope that also covers a
├   ◇ does a broad scope that also covers a…        overlap     asks     │ protected or read-only path "break" the
├   ◇ what does graphene ask --finer (or…           reask       asks     │ conditions (say src/** when
├   ◇ "things the planner must never propose": is…  never       asks     │ src/graphene_map/ui/static/** is
├   ◇ the settings live in the store's plan_meta…   store       assumes  │ read-only)?
├   ◇ a key passed on argv shows up in ps, and an…  keychain    risk     │ overlap · question · open · put up by the
├ ▼ ? the Token Factory key                         keys        proposed │ planner (graphene ask)
│ ├   ? find, store and remove the key: the…        key-store   proposed │
│ ├   ? Token Factory calls use keys.find()…        key-use     proposed │ y default  yes: at propose and edit, a
│ └   ? graphene key set, check and remove, for a…  key-cli     proposed │            scope is refused when it matches
├ ▼ ? standing conditions                           conditions  proposed │            any tracked file under a
│ ├   ? the settings, their text form and their…    settings    proposed │            protected or read-only glob
│ ├   ? the gate refuses a scope that breaks a…     cond-gate   proposed │            (P.overlap with P.tracked); at
│ └   ? protected paths are never read by a…        cond-reads  proposed │            done, a changed path under one
├ ▼ ? plan size                                     size        proposed │            is refused
│ ├   ? measure the repo and the ask, and say…      sizing      proposed │ 1          no: the conditions are cut out
│ ├   ? the planner is told the conditions and…     ask-told    proposed │            of every scope, so src/** is
│ └   ? graphene ask --finer and --coarser          ask-flags   proposed │            allowed, and only a changed path
└ ▼ ? graphene config                               config      proposed │            under a condition is refused at
  ├   ? graphene config and graphene config edit    config-cli  proposed │            done
  └   ? register key and config, and init writes…   cli-wire    proposed │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
 waiting on you: 9 · executors: none · nothing ready to run · 0/0 done · plan first: on (P)
 y take: yes: at propose and edit… · 1 pick: no: the conditions are cut… · d drop · p park · Enter answer · a note
```

### rows-thirty-80x24

```text
 the plan of …-450c-8a0f-177242891dc7/scratchpad/render-repos/rows-thirty-80x24
▼ ○ csv feeds import cleanly, and every bad row is named…  14/26 done
├   ◇ which encodings does open a feed…      encodings     asks
├   ◇ a supplier's feed is under 200 MB…     under-200mb   assumes
├   ◇ the dry run could still write the…     dry-writes    risk
├   ◇ mailing the report (r-email): nobody…  no-email      leaves out
├   ◇ the old system's fixed width feeds…    fixed-ends    note
├ ▶ ✓ read every feed as rows                reader        6 done
├ ▶ ✓ the dialects our suppliers send        dialects      5 done
├ ▶ ○ every row checked before it is…        validate      1 came back, 5 more▅
├ ▶ ○ the bad rows report                    report        1 review, 4 more
────────────────────────────────────────────────────────────────────────────────
 which encodings does open a feed try, and in what order?
 encodings · question · open · put up by the planner (graphene ask)

 y default  utf-8, then cp1252, the two our suppliers have sent this year
 1          utf-8, cp1252 and latin-1, with chardet to guess
            then: scope csv-open + pyproject.toml
 2          utf-8 only; anything else is a bad feed
 about      csv-open  open a feed whatever its encoding


 you: 10 · 2 running · R: 4 ready · 14/26 done · plan first: on
 y take · 1 pick · 2 pick · d drop · p park · Enter answer · a note · Tab view
```

### rows-thirty-120x36

```text
 the plan of …AllThingsAgenticHackathon/d3d5effe-ac06-450c-8a0f-177242891dc7/scratchpad/render-repos/rows-thirty-120x36
▼ ○ csv feeds import cleanly, and every bad row is named…     14/26 done │ which encodings does open a feed try, and
├   ◇ which encodings does open a feed try…     encodings     asks       │ in what order?
├   ◇ a supplier's feed is under 200 MB, so…    under-200mb   assumes    │ encodings · question · open · put up by the
├   ◇ the dry run could still write the…        dry-writes    risk       │ planner (graphene ask)
├   ◇ mailing the report (r-email): nobody…     no-email      leaves out │
├   ◇ the old system's fixed width feeds end…   fixed-ends    note       │ y default  utf-8, then cp1252, the two our
├ ▶ ✓ read every feed as rows                   reader        6 done     │            suppliers have sent this year
├ ▶ ✓ the dialects our suppliers send           dialects      5 done     │ 1          utf-8, cp1252 and latin-1, with
├ ▼ ○ every row checked before it is imported   validate      2/5 done   │            chardet to guess
│ ├   ✓ numbers, dates and prices parse         v-types       done       │            then: scope csv-open +
│ ├   ✓ required fields are there               v-required    done       │            pyproject.toml
│ ├   ● a zero or negative price is a bad row   v-price       running    │ 2          utf-8 only; anything else is a
│ ├   ↩ duplicate skus in one feed              v-dupes       came back  │            bad feed
│ ├   ◌ rules a supplier can switch off         v-rules       waiting    │ about      csv-open  open a feed whatever
│ └   ? an empty row is skipped, not a bad row  v-empty       proposed   │            its encoding
├ ▼ ○ the bad rows report                       report        1/5 done   │
│ ├   ✓ each bad row keeps its line number      r-lines       done       │
│ ├   ◆ the report as a table a person reads    r-format      review     │
│ ├   ● the report as json for the dashboard    r-json        running    │
│ ├   ○ mail the report to the supplier         r-email       ready      │
│ └   ○ cap the report at a thousand rows       r-limit       ready      │
├ ▼ ○ one command imports a feed                cli           0/5 done   │
│ ├   ○ feeds import <file>                     cli-import    ready      │
│ ├   ○ a dry run that imports nothing          cli-dry       ready      │
│ ├   ◌ the exit code says whether any row…     cli-exit      waiting    │
│ ├   ◌ a progress line for a large feed        cli-progress  waiting    │
│ └   ◇ try it on last month's real feeds       cli-review    yours      │
└ ▼ ? the importer documented                   docs          proposed   │
  ├   ? usage in the README                     d-usage       proposed   │
  ├   ? which dialects we read, with an…        d-dialects    proposed   │
  └   ? how to read the bad rows report         d-report      proposed   │
                                                                         │
                                                                         │
 waiting on you: 10 · executors: 2 running · R runs 4 ready · 14/26 done · plan first: on (P)
 y take: utf-8, then… · 1 pick: utf-8, cp1252… · 2 pick: utf-8 only… · d drop · p park · Enter answer · a note
```

### view-feeds-80x24

```text
 the plan of …6-450c-8a0f-177242891dc7/scratchpad/render-repos/view-feeds-80x24
the board: 5 open
questions
  ◇ What should the source be called on the command line?     src-name    open
    y  `xml`, which matches the existing format-named sources `csv` and `json`
    1  `northwind`, named after the supplier
       about xml-wire: Wire the source end to end
  ◇ `config/defaults.py` says "Ops edits this; nothing else…  enable      open
    y  yes. Without it the same load command refuses the file with "source is…
    1  no. Ops enables it later, and the end-to-end check calls the loader…
       then check xml-wire: python3 -m unittest -q tests.test_xmlfeed
assumptions
  ◇ "Skip a price of 0" applies only to the load path…        zero-scope  open▃
risks
  ◇ The end-to-end check could pass with the wrong output…    e2e-hollow  open
────────────────────────────────────────────────────────────────────────────────
 question src-name · open
 put up by the planner (planner:claude)

 What should the source be called on the command line?

 y default  `xml`, which matches the existing format-named sources `csv` and
 you: 1 · 0 running · none ready · 0/0 done · plan first: on
 y take: `xml`… · 1 pick: `northw… · d drop · p park · Enter answer · a note
```

### view-feeds-120x36

```text
 the plan of …-AllThingsAgenticHackathon/d3d5effe-ac06-450c-8a0f-177242891dc7/scratchpad/render-repos/view-feeds-120x36
the board: 5 open
questions
  ◇ What should the source be called on the command line?                                             src-name    open
    y  `xml`, which matches the existing format-named sources `csv` and `json`
    1  `northwind`, named after the supplier
       about xml-wire: Wire the source end to end
  ◇ `config/defaults.py` says "Ops edits this; nothing else decides what runs". Should this change…   enable      open
    y  yes. Without it the same load command refuses the file with "source is not enabled".
    1  no. Ops enables it later, and the end-to-end check calls the loader with the source patched into…
       then check xml-wire: python3 -m unittest -q tests.test_xmlfeed
assumptions
  ◇ "Skip a price of 0" applies only to the load path (`cli/main.py` → `validate/rules.py`). The…     zero-scope  open
risks
  ◇ The end-to-end check could pass with the wrong output: the summary row looks like a real…         e2e-hollow  open
    y  The check asserts the exact output: skus NW-1 and NW-2 only, with price_cents 1299 and 450, and the name…
left out
  ◇ `vendor/tinydec.py`, `legacy/priceimport.py`, `normalize/money.py:to_major` (another ticket…      hands-off   open
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 question src-name · open
 put up by the planner (planner:claude)

 What should the source be called on the command line?

 y default  `xml`, which matches the existing format-named sources `csv` and `json`
 1 option   `northwind`, named after the supplier
 about      xml-wire: Wire the source end to end







 waiting on you: 1 · executors: none · nothing ready to run · 0/0 done · plan first: on (P)
 y take: `xml`, which matches the… · 1 pick: `northwind`, named after… · d drop · p park · Enter answer · a note
```

### view-night-80x24

```text
 the plan of …6-450c-8a0f-177242891dc7/scratchpad/render-repos/view-night-80x24
the board: 5 open
questions
  ◇ does a broad scope that also covers a protected or          overlap   open
    read-only path "break" the conditions (say src/** when
    src/graphene_map/ui/static/** is read-only)?
    y  yes: at propose and edit, a scope is refused when it matches any
       tracked file under a protected or read-only glob (P.overlap with
       P.tracked); at done, a changed path under one is refused
    1  no: the conditions are cut out of every scope, so src/** is allowed,
       and only a changed path under a condition is refused at done           ▅
  ◇ what does graphene ask --finer (or --coarser) re-ask?       reask     open
    y  it sets the size for that one ask only and leaves the setting as it…
    1  the same, but the earlier proposals from that sentence that were never…
  ◇ "things the planner must never propose": is this free…      never     open
────────────────────────────────────────────────────────────────────────────────
 question overlap · open
 put up by the planner (planner:claude)
                                                                              ▁
 does a broad scope that also covers a protected or read-only path "break" the
 conditions (say src/** when src/graphene_map/ui/static/** is read-only)?

 you: 4 · 0 running · none ready · 0/0 done · plan first: on
 y take: yes: at… · 1 pick: no: the… · d drop · p park · Enter answer · a note
```

### view-night-120x36

```text
 the plan of …-AllThingsAgenticHackathon/d3d5effe-ac06-450c-8a0f-177242891dc7/scratchpad/render-repos/view-night-120x36
the board: 5 open
questions
  ◇ does a broad scope that also covers a protected or read-only path "break" the conditions (say       overlap   open
    src/** when src/graphene_map/ui/static/** is read-only)?
    y  yes: at propose and edit, a scope is refused when it matches any tracked file under a protected or read-only
       glob (P.overlap with P.tracked); at done, a changed path under one is refused
    1  no: the conditions are cut out of every scope, so src/** is allowed, and only a changed path under a condition
       is refused at done
  ◇ what does graphene ask --finer (or --coarser) re-ask?                                               reask     open
    y  it sets the size for that one ask only and leaves the setting as it is; with no sentence it asks again with…
    1  the same, but the earlier proposals from that sentence that were never accepted are dropped first
  ◇ "things the planner must never propose": is this free text, or globs too?                           never     open
    y  sentences that are passed to the planner and shown by graphene config; the gate refuses nothing because of…
    1  also globs, which the gate refuses like read-only ones
assumptions
  ◇ the settings live in the store's plan_meta (.graphene/graphene.db, which is private and which the…  store     open
risks
  ◇ a key passed on argv shows up in ps, and an executor's own shell can run `security…                 keychain  open
    y  key set reads the key with getpass and gives it to security's prompt or to secret-tool's stdin, never on argv…
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 question overlap · open
 put up by the planner (planner:claude)

 does a broad scope that also covers a protected or read-only path "break" the conditions (say src/** when
 src/graphene_map/ui/static/** is read-only)?

 y default  yes: at propose and edit, a scope is refused when it matches any tracked file under a protected or
            read-only glob (P.overlap with P.tracked); at done, a changed path under one is refused
 1 option   no: the conditions are cut out of every scope, so src/** is allowed, and only a changed path under a
            condition is refused at done
 about      the whole plan


 waiting on you: 4 · executors: none · nothing ready to run · 0/0 done · plan first: on (P)
 y take: yes: at propose and edit, a… · 1 pick: no: the conditions are cut… · d drop · p park · Enter answer · a note
```

### view-thirty-80x24

```text
 the plan of …-450c-8a0f-177242891dc7/scratchpad/render-repos/view-thirty-80x24
the board: 5 open
questions
  ◇ which encodings does open a feed try, and in what        encodings    open
    order?
    y  utf-8, then cp1252, the two our suppliers have sent this year
    1  utf-8, cp1252 and latin-1, with chardet to guess
       then scope csv-open + pyproject.toml
    2  utf-8 only; anything else is a bad feed
       about csv-open: open a feed whatever its encoding
assumptions                                                                   ▅
  ◇ a supplier's feed is under 200 MB, so the report can…    under-200mb  open
risks
  ◇ the dry run could still write the report file, and a…    dry-writes   open
    y  the dry run writes nothing but stdout
────────────────────────────────────────────────────────────────────────────────
 question encodings · open
 put up by the planner

 which encodings does open a feed try, and in what order?                     ▃

 y default  utf-8, then cp1252, the two our suppliers have sent this year
 you: 5 · 2 running · R: 4 ready · 14/26 done · plan first: on
 y take · 1 pick · 2 pick · d drop · p park · Enter answer · a note · Tab view
```

### view-thirty-120x36

```text
 the plan of …AllThingsAgenticHackathon/d3d5effe-ac06-450c-8a0f-177242891dc7/scratchpad/render-repos/view-thirty-120x36
the board: 5 open
questions
  ◇ which encodings does open a feed try, and in what order?                                         encodings    open
    y  utf-8, then cp1252, the two our suppliers have sent this year
    1  utf-8, cp1252 and latin-1, with chardet to guess
       then scope csv-open + pyproject.toml
    2  utf-8 only; anything else is a bad feed
       about csv-open: open a feed whatever its encoding
assumptions
  ◇ a supplier's feed is under 200 MB, so the report can hold every bad row in memory                under-200mb  open
risks
  ◇ the dry run could still write the report file, and a person reads it as an import that happened  dry-writes   open
    y  the dry run writes nothing but stdout
       then check cli-dry: python -m feeds import --dry samples/ok.csv && test ! -e report.txt
left out
  ◇ mailing the report (r-email): nobody has asked for it and it needs SMTP settings                 no-email     open
    y  r-email leaves the plan
       then drop r-email
notes
  ◇ the old system's fixed width feeds end in March; keep that leaf small                            fixed-ends   open
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 question encodings · open
 put up by the planner

 which encodings does open a feed try, and in what order?

 y default  utf-8, then cp1252, the two our suppliers have sent this year
 1 option   utf-8, cp1252 and latin-1, with chardet to guess
   then     scope csv-open + pyproject.toml
 2 option   utf-8 only; anything else is a bad feed
 about      csv-open: open a feed whatever its encoding


 waiting on you: 5 · executors: 2 running · R runs 4 ready · 14/26 done · plan first: on (P)
 y take: utf-8, then… · 1 pick: utf-8, cp1252… · 2 pick: utf-8 only… · d drop · p park · Enter answer · a note
```

### lane-a-thirty-80x24

```text
 the plan of …50c-8a0f-177242891dc7/scratchpad/render-repos/lane-a-thirty-80x24
▼ ○ csv feeds import cleanly, and every bad row is named…   14/26 done
├ ▶ ✓ read every feed as rows                 reader        6 done
├ ▶ ✓ the dialects our suppliers send         dialects      5 done
├ ▶ ○ every row checked before it is…         validate      1 came back, 5 more
├ ▶ ○ the bad rows report                     report        1 review, 4 more
├ ▶ ○ one command imports a feed              cli           1 yours, 4 more
└ ▶ ? the importer documented                 docs          3 proposed
────────────────────────────────────────────────────────────────────────────────
 csv feeds import cleanly, and every bad row is named with its line
 the goal · 14/26 done

 ✓ read every feed as rows                                  reader    done
 ✓ the dialects our suppliers send                          dialects  done
 ○ every row checked before it is imported                  validate  2/5 done
 ○ the bad rows report                                      report    1/5 done
 ○ one command imports a feed                               cli       0/5 done
 ? the importer documented                                  docs      proposed

 waiting  v-dupes came back · v-rules on v-dupes (came back) · r-format is in
          review · cli-exit on cli-import (ready) · cli-progress on cli-import
          (ready) · cli-review is yours · v-empty and docs are proposed, for  ▇
 you: 5 · 2 running · R: 4 ready · 14/26 done · plan first: on
 y accept it all · E edit the plan as text · za fold all · Tab view · ? help
```

### lane-a-thirty-120x36

```text
 the plan of …lThingsAgenticHackathon/d3d5effe-ac06-450c-8a0f-177242891dc7/scratchpad/render-repos/lane-a-thirty-120x36
▼ ○ csv feeds import cleanly, and every bad row is named…     14/26 done │ csv feeds import cleanly, and every bad row
├ ▶ ✓ read every feed as rows                   reader        6 done     │ is named with its line
├ ▶ ✓ the dialects our suppliers send           dialects      5 done     │ the goal · 14/26 done
├ ▼ ○ every row checked before it is imported   validate      2/5 done   │
│ ├   ✓ numbers, dates and prices parse         v-types       done       │ ✓ read every feed as rows          done
│ ├   ✓ required fields are there               v-required    done       │ ✓ the dialects our suppliers send  done
│ ├   ● a zero or negative price is a bad row   v-price       running    │ ○ every row checked before it is…  2/5 done
│ ├   ↩ duplicate skus in one feed              v-dupes       came back  │ ○ the bad rows report              1/5 done
│ ├   ◌ rules a supplier can switch off         v-rules       waiting    │ ○ one command imports a feed       0/5 done
│ └   ? an empty row is skipped, not a bad row  v-empty       proposed   │ ? the importer documented          proposed
├ ▼ ○ the bad rows report                       report        1/5 done   │
│ ├   ✓ each bad row keeps its line number      r-lines       done       │ waiting  v-dupes came back · v-rules on
│ ├   ◆ the report as a table a person reads    r-format      review     │          v-dupes (came back) · r-format is
│ ├   ● the report as json for the dashboard    r-json        running    │          in review · cli-exit on cli-import
│ ├   ○ mail the report to the supplier         r-email       ready      │          (ready) · cli-progress on
│ └   ○ cap the report at a thousand rows       r-limit       ready      │          cli-import (ready) · cli-review is
├ ▼ ○ one command imports a feed                cli           0/5 done   │          yours · v-empty and docs are
│ ├   ○ feeds import <file>                     cli-import    ready      │          proposed, for you to accept or
│ ├   ○ a dry run that imports nothing          cli-dry       ready      │          prune
│ ├   ◌ the exit code says whether any row…     cli-exit      waiting    │
│ ├   ◌ a progress line for a large feed        cli-progress  waiting    │
│ └   ◇ try it on last month's real feeds       cli-review    yours      │
└ ▼ ? the importer documented                   docs          proposed   │
  ├   ? usage in the README                     d-usage       proposed   │
  ├   ? which dialects we read, with an…        d-dialects    proposed   │
  └   ? how to read the bad rows report         d-report      proposed   │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
                                                                         │
 waiting on you: 5 · executors: 2 running · R runs 4 ready · 14/26 done · plan first: on (P)
 y accept it all · E edit the plan as text · za fold all · Tab view · ? help · q quit
```

## What the evidence says, for the coordinator

**Did either board candidate cut effort?** Neither candidate cut effort by a margin this sample can show.

| measure | rows | view |
|---|---|---|
| pressed keys (total) | 249 | 244 |
| median pressed keys | 30.5 | 27.5 |
| words read | 35,577 | 36,855 |
| median words read | 5,870 | 5,915 |
| seconds | 1,550 | 1,602 |
| stalls | 29 | 26 |
| completion | 12 of 12 across both candidates | |
| clarity | 4 in every trial | |

- The total key counts differ (1,582 against 2,145), but only because of the characters typed into `:node set` lines. Those lines fix the same defect in both candidates: a board pick does not reach the leaf.
- **Size explains the spread better than candidate.** In 5 of the 6 persona and plan pairs, the 120x36 trial was cheaper whichever candidate it ran. That is 24 to 70% fewer pressed keys, 21 to 50% fewer seconds and 3 to 19% fewer words. Size and candidate are confounded by the trial assignment: alex and judge ran rows only at 80x24.
- The differences that are specific to a candidate are small and point both ways:
  - rows counts board items into "you: N" (`you: 6` against view's `you: 1` on the same feeds store), and four of the six "key hints vanished" stalls came from rows trials.
  - view needed Tab to reach the tree (`nothing open: Tab for the tree` was named as a help), and its list rows truncate until selected.
- The one board answer that differed within a persona (judge, `enable`) went opposite ways under the two candidates, and nothing in the report ties it to the layout.
- **Caveats.** n is 12 board trials: 3 per candidate and plan, and 2 to 4 per candidate and size. The personas are agent stand-ins reading `tmux capture-pane` text with no cursor attributes, and seconds include their thinking.

**Which graph view was used for what.**
- The **outline** answered what runs, what waits on what (through the goal pane's "waiting" paragraph) and what `R` starts (through the status line) for all three personas. At 120x36 it did so on the first screen with no keys.
- The **dag** was used for the critical path. It was readable only at 120x36, where the footer names it. At 80x24 all three inferred the path from the heavy edge and got it right, but all three explained the tie by "it waits on a person", which is wrong: the code breaks ties by plan order. All three also flagged the dag's "8 at once" against "R: 4 ready". The 8 is `at_once` minus the leaf that came back, so it includes 4 proposed leaves.
- The **tree** was never reached at 80x24. At 120x36 it served only as a cross-check.
- All graph answers were right against `critical_path`, the node states and what `R` starts.

## The decision (the coordinator's, 03:30)

- **The board is the rows candidate; the view candidate is deleted** (its branch `lane-a-board-view` is
  not merged; its screens stay above, under `screens/view-*`). The two tied on effort: 249 against 244
  keys pressed, 35,577 against 36,855 words read, 29 against 26 stalls, and every difference is inside
  what size alone moved. Rows wins the tie on three counts: the board sits beside the tree on one
  screen, in the one row grammar, so a question and the leaf it is about are seen together; it read
  fewer words; and it adds no mode to learn (Tab stays the key for the plan's views).
- **Both graph views stay, and the outline stays the default.** They answer different questions. The
  outline answered what runs, what waits and what `R` starts, for all three personas, with no key
  pressed at 120x36. The graph answered the critical path. The tree was a cross-check only, and never
  fit the thirty-leaf plan at 80 columns; it is Alex's own picture of a plan and costs nothing when
  it is not shown, so it stays behind Tab, and `auto` offers it only where it fits.
- **What the stand-ins stalled on is fixed next, before anything else** (lane A final): a pick now
  carries `then:` lines that change the leaf (11 stalls), the graph's footer names the critical path
  first and its counts agree with `R: N ready` (11), Tab says which view it skipped, the key hints stay,
  the help gets a legend and shrinks, and `node set` can add to a scope or a goal instead of retyping.
