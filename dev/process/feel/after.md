# The after walk: each of the 36 findings on the branch's wheel

One Fable reader walked the branch's wheel (built from the tip after the seam fixes) as the three readers walked
main 27574d4, with the same harnesses (the words' captures, the headless screen shots at 80x24 and 120x36, the
rhythm's pty recordings and the Claude Code session walk), the stand-in model in front, nothing spent. Its verdict
on each finding, the new line quoted, then what it found new. Its captures are the session's; the screens are in
`screens/after/`.

**Tally: mended 16, partly 14, unchanged 6, worse 0.** Like-for-like line census over the 37 captures the old walk
also made (help files excluded): lines over 80 columns 88 → 73, over 120 36 → 28, over 190 11 → 4.

| id | title | verdict | the new line / screen | why |
|---|---|---|---|---|
| W1 | run opens on 297-char mechanics line | partly | `landing into main at 05e44c9: claude, up to 2 at once; an attempt stops once it passes $2` / `` `graphene watch` in another terminal follows it (each leaf lands as its own merge; your commit hooks are skipped)`` | Two lines (89 + 113 chars; 764 chars for the run vs 998) and --no-verify/--no-ff are in `run --help`; the closing line is unchanged (left out by decision). |
| W2 | init's plan-first sentence, six undefined terms | partly | `plan first: on. Claude proposes a plan here before it writes; you accept it in `graphene watch`, in another terminal. `graphene plan first off` turns it off.` | 157 chars, two rows; at a terminal the prompt is still `plan first [on]:` and the `auto` row still wraps to column 0. |
| W3 | grey full-path parenthesis on stderr | mended | (nothing: no capture holds `the plan of`; the old walk had it in 5) | ask, accept, run, board take end on their own last line now. |
| W4 | ask never names plan accept | partly | `next: `graphene plan accept`, or prune in `graphene watch` (y accepts, d drops)` | The command the README chains is first, 79 chars; the `proposed feed: …` rows are still flat, `at list price` stays, the board question still reads `put up cents: …` with no default on it. |
| W5 | plan header and accept footer explain a rule | partly | `the plan (proposed): the new feed loads like the others` / `waiting on you: feed (proposed, with the 2 under it)` / `  `graphene plan accept` takes all of it; y in graphene watch` / after accept: `next: `graphene run` reaches fields, readme  (R in graphene watch)` | Both parentheses gone, each screen ends on a command; the per-row `` · `graphene plan accept fields` `` is still on every row (wraps at 100). |
| W6 | 'red first', 'it proves nothing' undefined | partly | `fields, readme: their check (`true`) passes before any work: it would pass with nothing done; `graphene node set <id> --check '<a real one>'`, or e in `graphene watch`` / `red first: 2 checks ran at 05e44c9 before any work, in 0 s` | The check is named and the verdict has an object; the line grew from 134 to 167 chars; `red first` still undefined. (The tail is cut in the fixes that follow this walk.) |
| W7 | node show prints executor's finish/stuck | mended | `  scope:  normalize/fields.py   (…)` / `  done:   `true` passes` / `  landed: b282f47: `graphene node diff fields` shows it`; sub-goal: `  scope:  none yet` / `  done:   no check yet` | No `finish:`/`stuck:` for a person; `node start` still prints them to the agent. |
| W8 | 'in short' says one fact five ways | unchanged | `  in short: 1 path changed under it, 0 traced to a recorded write; …` | Same 191-char sentence; the leaf's show is 32 lines (was 34). Left out by decision. |
| W9 | init prints 946 chars, eight hook names | partly | `hooks added to .claude/settings.local.json (8 Claude Code hooks)` / `each Claude Code session here is recorded on this machine only (…); `graphene init --remove` takes the hooks out` | 672 chars before `next:` (was 864 by the same count); the not-chosen first line is still 194 chars and the record line 177. |
| W10 | bare `graphene` lectures about pruning | unchanged | `nothing is planned here yet. Say what you want to your agent, in a paragraph: …` | Same NO_PLAN text. |
| S1 | three dollar labels, three clocks | partly | status `… · bill $0.0057`; goal pane `last run  run: 1 done · agents <1 min, $0.0002 at list price · …`; time note `agents 0 min $0.0057` | The planner-only case says `bill`; the pane's and the note's figures still sit unlabelled, two and four places. |
| S2 | status line: seven dot fragments, 1/9 done falls off | mended | `4 on you · agents 1 <1m · you 1 act ~1m · R: 1 ready · 1 came back · 1/9 done` (78 columns) | The clock is one phrase and the done count is back. |
| S3 | time view has no legend, borrows ━ and ◆ | mended | ` ids     ═══════…═●` / ` docs   ═!↩`; `?` with the view open adds `█ edit  ▓ run  ▒ read  ░ talk  ─ idle  ═ held` / `✓ ✗ check  ! refused  ■ landed  \| you` | Nothing in the time view means something else in the tree's key. |
| S4 | demo opens on 'not Nemotron', raw kinds | partly | `replay · a scripted stand-in, no model ran · 2026-10-12 · 1 of 16`; `farewell finished · farewell usage · farewell ended`, `greet landed · friendly rolled up · run` | No Nemotron, no underscores; `stand-in Nano` stays (the ladder, kept on purpose); frame 1's bottom line was `the plan's settings` (fixed after this walk). |
| S5 | shipped demo never shows the meter strip | mended | frame 7 of 16: `● farewell · stand-in Nano · attempt 1 · 0s · 2 turns · $0.0001` / `  running graphene node done farewell · 0 s ago · 1 file · 1k in, 81 out` | Re-recorded 12 October; the strip is on screen with a leaf running. |
| S6 | replay's `l` pastes the executor's log | mended | `greet · output of attempt 1` / `03:16:52  editing app.py` / `03:16:52  editing words.py` / `03:16:52  running graphene node release greet` | Phrased did rows now. |
| S7 | legend lumps `◇◆↩ yours` | partly | 120: `◇ yours  ◆ review  ↩ came back  ? proposed …`; 80: line 2 `◆ review  ↩ came back  ∅ check flagged`; 100x30: still `◇◆↩ yours …` | Named at 80 and 120; at 97-117 columns the lumped form still won (fixed after this walk). |
| S8 | fork rows reuse ↩ and · | mended | `– Nemotron-3-Nano-fake  fork 2  lost` / `⊘ … fork 4  gave up` above `↩ the schema  came back` / `· the rest  to fill in` | A fork's mark is nothing a leaf uses. |
| S9 | came-back pane hides `t`, key line drops t/Enter/q | partly | keys `w widen · b sibling · n wait · e edit check · r run it again · ? help · q quit` | `? help · q quit` and `r` are back at 80; `t ask the planner` and `Enter record` are still off the key line and the fourth offer below the fold. |
| S10 | a duration spelled seven ways | unchanged | `0s` / `0 s ago` / `<1m` / `~1m` / `<1 min` / `0 s` / `30 s` | Same set, plus the heartbeat's `30 s`. Left out by decision. |
| S11 | Enter on the goal pastes the CLI print | unchanged | `the record of the 9 leaves in the plan (1 done; each has its own: `graphene` / `    node show <id>`):` | Backticks and `<id>` still in the pane. |
| S12 | `q quit` and `? help` fall off at 80 | mended | `y accept it all · E edit as text · za fold all · Tab view · ? help · q quit`; `fork 1: keys act on greet · l output · x release · ? help · q quit` | Every key line at 80 ends `? help · q quit`; the fork and wordless board rows lost `Tab view` instead (Alex's trade). |
| S13 | `1 came back, 4 more` | unchanged | `├ ▶ ○ the API  api     1 came back, 4 more` | Same words. |
| S14 | `x release` vs handed back vs came back | unchanged | `l output · x release · Enter record · …` | Same key label. |
| S15 | empty plan: six zeros and Tab view | mended | `plan first: off` / `:ask what you want · ? help · q quit` | Two calm lines; while an ask runs: `plan first: on · planner asked 12 s ago`. |
| S16 | help box 79 wide at 80 | mended | every row ends `│` in column 80 | The box fills the width. |
| R1 | planner's half-minute blank on both screens | mended | `asking the planner (claude)…` +0.12 s, `  reading normalize/fields.py` / `  searching def load` +6.28 s, proposal +12.32 s; watch beside it: `plan first: on · planner asked 12 s ago` | Each read is said as it happens and the screen counts the wait. |
| R2 | after accept the next step is missing | mended | `next: `graphene run` reaches fields, readme  (R in graphene watch)`; with nothing open: `nothing to accept: no proposal is open` / `next: nothing is ready for `graphene run`` | The decision point ends on the command. |
| R3 | `(the plan of /full/path)` ends 25 commands | mended | no trailer after ask, accept, node start, node done or propose | Gone in the repo you stand in. |
| R4 | plan prints the accept command three times | partly | `  `graphene plan accept` takes all of it; y in graphene watch` then the per-row commands | The whole-tree accept is said once; the per-row commands stay. |
| R5 | run's terminal silent for the whole attempt | mended | +30.93 s `fields · 30 s · no usage yet · nothing yet`, +36.04 s `fields attempt 1: the executor ended (exit 0)` | A line every 30 s per metered leaf (its empty form reworded after this walk). |
| R6 | run opens with 299 chars of git flags, unwrapped | partly | the two landing lines then the red-first pair | Flags gone; the red-first pair stays and was longer (cut after this walk). |
| R7 | node show: agent's orders first, landing 33 lines down | partly | `  landed: 96cf738: …` is line 7; `said last:` and `the last it did:` still carry the same sentence; the refused command twice | Landing and check at the top, orders gone; the duplicates and `in short` remain. |
| R8 | morning after: Enter on goal is an audit ledger | partly | status `0 on you · bill $0.04 · …`; the record ends `  width 2 of 2 · 23% of agent minutes alone` | The total is labelled `bill`; the record is the same ledger with no file names. |
| R9 | 80 columns: finished plan loses `? help · q quit` | mended | `:plan archive puts it away · E edit as text · za fold all · ? help · q quit` | Help, quit and `2/2 done, finished` are on the first screen. |
| R10 | Claude Code hour ends blaming `run --here` | mended | `… the work of 2 leaves is in your checkout, uncommitted (`git status`): commit it yourself; …` | Says what to do and never names `--here` (shortened after this walk). |

## New, found on the branch (fixed after the walk unless marked)

1. The legend still lumped `◇◆↩ yours` at 97-117 columns (the one-line short form won there). Fixed: the long form or the two-line key, at every width.
2. A finished plan whose run took a minute read `agents 0 1m $0.04`. Fixed: nothing running reads `bill $0.04`.
3. The red-first line had grown to 167 characters. Fixed: the `, or e in graphene watch` tail is gone (the pane says `e edits it`).
4. A quiet leaf's heartbeat said `no usage yet · nothing yet`. Fixed: `still running, nothing read from it yet`.
5. `Tab view` fell off the board and fork rows at 80 so `? help · q quit` could stay. **Alex's trade**, not changed.
6. The Claude Code hour's last line was 228 characters. Fixed: the `graphene run would have landed…` clause is gone.
7. The replay's first bottom line read `the plan's settings`. Fixed: `settings recorded`.
8. Three labels for `E` on three rows. Fixed: `E edit as text` on all three.
