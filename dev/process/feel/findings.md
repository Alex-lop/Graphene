# What three readers felt in the first hour, on main at 27574d4 (the 0.5.0 wheel)

Three Fable sessions, each with one lens, walked the installed wheel against the stand-in `claude`
(`dev/process/prove/fake/claude`), so no model answered and nothing was spent; one re-recorded the demo with the
scripted fake and one drove `graphene watch` headless with Textual's pilot. Each was asked for the ten (or more)
things that feel wrong to a stranger, each with the line on screen, why it feels wrong and the smallest change
that would mend it, pinned to a file and line. Their findings are below, as returned; the decisions taken from
them are in `decisions.md`.

## the words: every line the CLI prints in the first hour, read for undefined terms, length and what it asks the person to do next

### W1. The run opens with a 297-character line of mechanics, and the one thing to do is its last clause

*Where:* src/graphene_map/plan_cli.py:1049-1052 (the f-string printed by `graphene run`); the run's closing line is run.py:632 + run.py:649

*What a stranger sees:*

> landing into main at cc9b19a: claude, up to 2 at once, an attempt stops once it passes $2; each leaf is committed with --no-verify (your pre-commit and commit-msg hooks skip it) and merged --no-ff; checks run in a clean worktree with your PATH; `graphene watch` in another terminal follows it live  — 297 characters, four rows at 80 columns, before anything has started. Two caveat lines follow it (finding 6), so 'fields started: map the xml fields' is the run's fourth line. The run's last line has the same habit: 'run: 2 done · agents <1 min, $0.0246 at list price · width 2 of 2 · you 2 acts, 2 min' ('width 2 of 2' and 'acts' are never defined).

*Why it feels wrong:* Five facts in one breath: where it lands, the executor, the parallelism, the cap, how commits are made, how merges are made, where checks run, and how to watch. 'landing', 'leaf', 'worktree', '--no-verify', '--no-ff' have not appeared on any earlier screen. The hooks and merge facts are one-time facts about how Graphene works, said again every run; the per-run facts (branch, base, executor, width) are buried among them. The only action ('graphene watch in another terminal') is where the eye arrives last.

*The smallest change:* Two lines, and a home for the rest: line 1 `run: claude, 2 at once, into main from cc9b19a; an attempt stops at $2`; line 2 `follow it: \`graphene watch\` in another terminal`. Move 'each leaf is committed with --no-verify … merged --no-ff; checks run in a clean worktree with your PATH' into `graphene run --help`'s description, which has the room and is read once. Closing line: 'width 2 of 2' → '2 at once'; 'you 2 acts, 2 min' → 'you: 2 commands, 2 min'.

*Felt difference:* large

### W2. init's 'plan first' sentence uses six undefined terms on the very first screen, and is repeated verbatim by `graphene plan first`

*Where:* src/graphene_map/plan_cli.py:40-42 (FIRST_SAID['on']), printed by cli.py:412 in `graphene init` and again by `graphene plan first` with no argument; the README already says it plainly at README.md:82

*What a stranger sees:*

> plan first: on. Every ask in a session is proposed, one leaf included, and waits for you. You accept in `graphene watch`, in another terminal; `graphene plan first off`, typed outside Claude Code, stops it.  — 206 characters, three rows at 80 columns (at a terminal the interactive prompt before it is also labelled by the setting's name: 'plan first [on]:', and its 'auto' option wraps mid-sentence so 'bigger work waits for you' starts at column 0).

*Why it feels wrong:* This is the first thing Graphene says after being installed. 'plan first', 'ask', 'proposed', 'session', 'one leaf included', 'typed outside Claude Code' are all new; 'one leaf included' is a parenthesis about the auto mode's exception, which the person has not met; 'typed outside Claude Code' makes them wonder where else they would type it. The README's own sentence for the same fact ('from your next session Claude proposes a plan before it writes anything; you accept it in `graphene watch`, in another terminal') is shorter and uses words they know.

*The smallest change:* Reuse the README's words: `plan first: on. In Claude Code here, a request becomes a proposed plan before any edit; you accept it in \`graphene watch\` (another terminal). \`graphene plan first off\` turns this off.` (about 150 characters, two rows). At the terminal prompt, label it with the question it answers ('propose before writing? [on]:'), and indent the wrapped 'auto' line under its word.

*Felt difference:* large

### W3. Every command that changes the plan ends with a grey parenthesis naming the repo's full path, on stderr

*Where:* src/graphene_map/plan.py:3063-3068 (where/where_said), emitted by plan_cli.py:97-99 said_where() after `ask`, `plan accept`, `run`, and by board_cli.py:193

*What a stranger sees:*

> (the plan of /private/tmp/claude-501/-Users-alexlopez-Desktop-AllThingsAgenticHackathon/e37ef5e4-ecd5-4976-a41d-71ab2ec13bc9/scratchpad/feel/words/runs/feeds-plain-fake-1/repo)  — 181 characters here; under $HOME it is '~/…' but still the whole path, as the last line of `graphene ask`, `graphene plan accept` and `graphene run`, every time, while the person is standing in that very directory.

*Why it feels wrong:* It is the last line of every screen, so it is where the eye rests; it is indented, parenthesised and on stderr (a different colour in many terminals, and it lands after the stdout block when output is piped), so it reads as a warning; and it says something that is always the same. Its purpose, a stray `cd` into another repo (plan.py:3065), is a case the person is not in on the first hour's screens.

*The smallest change:* Print it only when the plan's root is not the current directory's git top level (compare `where(root)` with `git rev-parse --show-toplevel` of cwd); otherwise nothing. If it must always print, the basename alone: `  (plan: feeds-plain-fake-1)`.

*Felt difference:* medium

### W4. The ask's closing lines never name `graphene plan accept`, and end on 'prune it' with keys for a screen that is not open

*Where:* src/graphene_map/plan_text.py:639 ('proposed id: title' rows), plan_text.py:862 ('goal (proposed)'), ask.py:456 (the bill), plan_cli.py:1087 ('the board waits on you'), plan_cli.py:1094 ('prune it'), board.py:790 / board_cli.py:252 ('put up id: question')

*What a stranger sees:*

> goal (proposed): the new feed loads like the others
> proposed feed: the new feed
> proposed fields: map the xml fields
> proposed readme: name the new source in the README
> the planner (claude sonnet-5-5): 1 call, $0.01 at list price
> prune it: `graphene watch` (y accepts, d drops), or `graphene plan edit`
> — and when the planner asks something: 'put up cents: are Northwind prices in cents or pounds?' then 'the board waits on you (1): `graphene board`, or `graphene watch`'.

*Why it feels wrong:* The three 'proposed' rows are flat, so the shape (fields and readme under feed) is lost until the next command draws it; 'at list price' qualifies a price with no named alternative; 'prune it' is the first gardening word on a screen that has said 'plan' and 'goal'; 'y accepts, d drops' are keys of a screen the person has not opened; and `graphene plan accept`, the command the README has them type next (README.md:84 shows `graphene plan accept && graphene run --parallel 2`), is not on the screen. 'put up cents:' reads as English ('put up cents') because the planner's id is a word, and the question line shows neither its default nor how to answer.

*The smallest change:* Print the same three indented rows `graphene plan` prints (one shape, learned once) in place of the 'proposed id: title' lines; last line `next: \`graphene plan accept\` takes all of it; \`graphene watch\` picks (y keeps, d drops); \`graphene plan edit\` rewrites`; the bill `planner: claude sonnet-5-5, 1 call, $0.01`; the question `question [cents]: are Northwind prices in cents or pounds? (default: cents) — \`graphene board\``.

*Felt difference:* medium

### W5. The plan's header and accept's footer explain an internal rule, twice, instead of the next step

*Where:* src/graphene_map/plan_cli.py:296 (header), plan_cli.py:349 ('waiting on you'), plan_cli.py:366 and :234 (the per-row accept command), plan_cli.py:836 ('the planner's sentence'), plan_cli.py:839 ('left alone, agents can reach')

*What a stranger sees:*

> the plan (proposed with the tree, accepted with it): the new feed loads like the others
> waiting on you: feed (proposed, with the 2 under it)
>   ? the new feed                         feed    proposed  · `graphene plan accept feed`
>     ? map the xml fields                 fields  proposed  · normalize/fields.py · `graphene plan accept fields`  (114 columns)
> — then after accepting:
> the plan: the new feed loads like the others  (the planner's sentence, accepted with its tree)
> left alone, agents can reach: fields, readme

*Why it feels wrong:* Two parentheses on two screens state the same rule (the goal sentence rides with the tree); neither tells the person what to do. The accept command is repeated on every row, pushing each over 80 columns, when one line would do. The top row is called 'feed' in one column and 'the new feed' in the next, so 'waiting on you: feed' needs a second look. 'left alone, agents can reach' is the last line before the person types `graphene run`, and it does not say 'run': 'left alone' (by whom?) and 'reach' are the planner's words, not the person's.

*The smallest change:* Header `proposed: the new feed loads like the others`; one footer `\`graphene plan accept\` takes all 3 (one: \`graphene plan accept <id>\`)` in place of the per-row commands; after accept drop the parenthesis and write `\`graphene run\` would start: fields, readme`.

*Felt difference:* medium

### W6. 'red first' and 'it proves nothing' are the run's second and third lines, undefined, and blame the person for the planner's `true`

*Where:* src/graphene_map/precheck.py:341-342 (the per-command line), precheck.py:345 (the 'red first:' header); the same verdict is restated in node show by node_record.py:744-746

*What a stranger sees:*

> fields, readme: their check passes at the base commit cc9b19a: it proves nothing; `graphene node set <id> --check '…'` or e in watch  (134 characters)
> red first: 2 checks at cc9b19a (1 command) in 1 s
> — and later, in `graphene node show fields`: 'it also passed at the base commit cc9b19a, before any work: it shows nothing about this change'.

*Why it feels wrong:* 'red first' is never defined on any screen (it is the TDD idea that a check should fail before the work); 'it proves nothing' is a verdict with no object (the check? the leaf? the run?); 'e in watch' is a key for a screen not open; '(1 command)' counts something the person did not ask about; and the check that 'proves nothing' is the planner's `true`, which the person never saw, so the scolding lands on the wrong party. Both lines come before 'fields started', so the run opens on two caveats.

*The smallest change:* Name the check and say what it means in the person's words: `fields, readme: their check (\`true\`) passes before any work, so it cannot fail the work; a real one: \`graphene node set <id> --check '<command>'\``. Drop the 'red first:' header when every verdict was 'passes' (the line above has said it), else `checked 2 checks at cc9b19a in 1 s`.

*Felt difference:* medium

### W7. `graphene node show` opens with the executor's instructions ('finish:', 'stuck:') read by the person, after the agent has gone

*Where:* src/graphene_map/plan.py:958-971 (contract(), 'the node as its executor is told it'), printed to the person by plan_cli.py:1424

*What a stranger sees:*

> scope:  normalize/fields.py   (a write anywhere else is refused, and blocks `done`)
>   done:   `true` passes
>   finish: graphene node done fields   (runs the check and asks git what changed)
>   stuck:  graphene node release fields --why '<what is in the way>' [--wants <paths it needs>]   (hands it back; say why)  (121 characters)
> — and on the sub-goal: '  scope:     (a write anywhere else is refused, and blocks `done`)' with nothing in the slot, and '  done:   ' blank.

*Why it feels wrong:* These lines are written for the agent (plan.py:954 says so) and printed unchanged to a person looking at a finished leaf: 'finish:' and 'stuck:' are things to do, by an executor that has already left; 'hands it back' to whom; '[--wants <paths it needs>]' is a usage string. On the sub-goal the empty scope with its parenthesis says a write anywhere is refused, with nothing to refuse against, and 'done:' is blank where the leaf said '`true` passes'.

*The smallest change:* When the caller is a person (who.person), print the contract as facts only: title, why, goal, scope, done; keep 'finish:' and 'stuck:' for the agent's view (`GRAPHENE_NODE` set). On a node with no scope: `scope:  none (a sub-goal; its leaves hold the scopes)`; on a node with no check: `done:   when its leaves are`.

*Felt difference:* medium

### W8. The record's 'in short' is the longest sentence on the screen, and with the coverage sentences says one fact five ways

*Where:* src/graphene_map/node_record.py:712 (_in_short), :725-728 (the leaf's coverage sentence), :744-746 (the check's 'also passed at the base'), :915-918 (the rolled-up coverage sentence in `node show <sub-goal>` and `plan record`), :929-931 ('checks run by Graphene itself'), :941 ('width … agent minutes alone')

*What a stranger sees:*

> in short: 1 path changed under it, 0 traced to a recorded write; the 1 commit inside its windows is in no record of a session that held it, so not graded, which takes nothing from the paths  (191 characters)
>   coverage: of the 1 path git said had changed under this node, 1 inside its scope; 0 to a recorded edit, 0 to a recorded shell command, 1 to git alone  (151)
> — and for the sub-goal and `plan record`: 'coverage: of the 2 paths git said had changed under them, 2 inside the scope of the leaf that changed it; 0 to a recorded edit, 0 to a recorded shell command, 2 to git alone' (177), 'checks run by Graphene itself: 2 of 2 passed at last run, 0 runs failed on the way; 0 writes refused; 0 `done` refused over paths outside a scope' (149), 'width 2 of 2 · 22% of agent minutes alone'.

*Why it feels wrong:* 'in short' is longer than the lines it summarises. 'windows', 'graded', 'traced to a recorded write', 'to git alone', 'takes nothing from the paths', 'agent minutes alone' are the record's internal words. In short, coverage, 'read from', the not-graded commit and the check's 'also passed at the base' are five lines for one fact: the only witness to the edit is git. The three zeros in the coverage sentence are the ordinary case for a Claude Code executor (no recorded edit) and read like failures. A leaf that edited one file takes 34 lines and 2,542 characters to show.

*The smallest change:* `in short: 1 file changed, inside its scope; no record of who edited it, so git's word alone` and omit the 'coverage:' sentence when every traced count is zero (keep 'read from:' and 'check:'). Rolled up: `checks: 2 of 2 passed; nothing refused`, and `2 ran at once` in place of 'width 2 of 2 · 22% of agent minutes alone'.

*Felt difference:* medium

### W9. init prints 946 characters before 'next:', including eight Claude Code hook names and a flag the person has not met

*Where:* src/graphene_map/cli.py:418 ('hooks added to …'), cli.py:419-423 ('the next Claude Code session here is recorded into …'), cli.py:339 ('--with changes one command'), cli.py:328-330 (the 'not chosen' line when init is not at a terminal) against cli.py:428 ('next: `graphene ask …`')

*What a stranger sees:*

> hooks added to .claude/settings.local.json: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PostToolUseFailure, SubagentStart, SubagentStop, Stop  (154 characters)
> the next Claude Code session here is recorded into .graphene/ (its prompts, its tool calls and what they returned, the files it edits; on this machine only); `graphene init --remove` takes the hooks out  (202)
> planner: claude · executor: claude  (`graphene init` changes them; --with changes one command)
> — six lines, five over 80 columns, three over 190. When init is not at a terminal (a script, CI, an agent), the first line says '… and until then `run` and `ask` refuse' and the last says 'next: `graphene ask '<what you want>'` proposes a plan'.

*Why it feels wrong:* The eight hook names are Claude Code's event names; nothing a person can act on, and they cost a row and a half. The recording line is three rows for one fact and its undo. '--with changes one command' names a flag of `ask` and `run`, commands not yet seen, in a parenthesis after the one line that was clear ('planner: claude · executor: claude'). Off a terminal the screen contradicts itself: line one says ask refuses, line six says ask next.

*The smallest change:* `hooks added to .claude/settings.local.json (8 Claude Code hooks)`; `Claude Code sessions here are now recorded on this machine (prompts, tool calls, edits); \`graphene init --remove\` undoes it`; drop the '--with' aside from init (it is already in `ask --help` and `run --help`); when nothing is chosen, make the last line `next: \`graphene init --planner claude --executor claude\``.

*Felt difference:* medium

### W10. Typing `graphene` right after init (as --help suggests) gets a 173-character sentence about agents and pruning trees

*Where:* src/graphene_map/plan_cli.py:31-34 (NO_PLAN), printed by bare `graphene` (on stderr) and by `graphene plan`; `graphene --help`'s 'graphene shows the plan' is cli.py's app docstring

*What a stranger sees:*

> nothing is planned here yet. Say what you want to your agent, in a paragraph: it proposes the tree, and you prune it in `graphene watch`. Or `graphene ask '<what you want>'`

*Why it feels wrong:* `graphene --help` says '`graphene` shows the plan', so this is often the stranger's second command. 'your agent' is unnamed (it means the Claude Code session the hooks now sit in); 'tree' and 'prune' appear here for the first time; and the one concrete command comes last, after an 'Or', as if it were the alternative rather than the thing init just told them to do next.

*The smallest change:* `nothing is planned yet. \`graphene ask '<what you want, in a paragraph>'\` proposes a plan (or ask Claude Code here: its hooks propose one too); \`graphene watch\` shows it`.

*Felt difference:* small

### What the words reader walked

- Setup: wheel at scratchpad/tools/M/bin/graphene (graphene 0.5.0) first on PATH, then dev/process/prove/fake/claude in front of it; dev/test/newrun.sh made runs/feeds-plain-fake-1 (feeds repo, hooks installed, env.sh's as_me); two more feeds repos via dev/test/make_task.py: init-run (to watch `graphene init` itself) and q-run (a copy of the fake under feel/words/fake2 whose proposal carries one board question). No model called, nothing in the repository edited. Captures: scratchpad/feel/words/01-help.txt … 17-help-more.txt.
- graphene --help, graphene (bare), graphene --version; every subcommand's --help (init, ask, plan, plan accept/record/log/first/edit/undo/archive, node, node show/diff/done/release/set/widen/sibling/add, run, watch, board, board note, demo).
- graphene init: non-tty in a fresh repo (6 lines, 946 chars, the 'not chosen' line and the contradicting 'next:'), init again ('hooks already installed'), init --planner claude --executor claude, and init at a pseudo-terminal (python pty): the 'which planner and executor for this repo?' menu (Enter loops on 'choose 1, 2 or 3' with no default), the 'what happens to an ask in a Claude Code session here?' menu with its wrapped 'auto' row, the 'plan first [on]:' prompt, and the 80-column wrapping of every init line; 'this Claude Code has no --max-budget-usd: `claude update` first' seen but caused by the fake, not counted.
- graphene plan / graphene board / graphene config on the empty plan.
- graphene ask with dev/test/tasks/feeds/paragraph.md against the fake planner (no question), and again in q-run with one question on the board ('put up cents: …', 'the board waits on you (1): …'); graphene plan, graphene (bare) and graphene board after each; graphene run on the unaccepted proposal ('nothing to run: the tree is a proposal (2 leaves) nobody has accepted: …').
- graphene plan accept (with and without an open question: 'took the default of cents, left open on the board (`graphene plan undo` takes them back)'), graphene plan accept again ('left alone, agents can reach: nothing'), graphene board after accept ('the board: 1 settled; nothing waits on you (`graphene board --all` lists them)').
- graphene run --parallel 2 with the fake executor (12 lines, 998 chars: the 297-char landing line, the two red-first lines, started/attempt/done lines, the closing meter line), then graphene plan ('finished; `graphene plan archive` puts it away'), graphene plan --all, graphene watch --once, graphene run with nothing open.
- graphene node show fields (leaf: 34 lines, 2,542 chars) and graphene node show feed (sub-goal: 13 lines), graphene node show nosuch, graphene plan record (7 lines), graphene plan log (36 rows for a 2-leaf run; its first row prints the whole 1,800-character paragraph on one line, and its kinds are raw names: goal_proposed, rolled_up, usage, said, did, denied — noted, not among the ten), graphene node diff fields and bare graphene node diff ('needs <node_id>'; `node diff` is hidden from `graphene node --help` although `node show` points at it).
- graphene demo --once (header 'replay · a scripted stand-in, not Nemotron · 2026-09-29 · ended: last frame' introduces Nemotron undefined, and at 80 columns its log rows are cut mid-word: "python3 -c 'i…", 'changed: app.…' — noted, not among the ten) and graphene demo --help.
- README.md lines 1-85: the 'Try it on your repo' block, the 'Heads up' paragraph (the plainest statement of plan-first anywhere, reused in finding 2) and the watch keys line; the README's example session uses `graphene plan accept && graphene run --parallel 2`, which the ask's own closing line never names (finding 4).
- Line census over the captures: 55 printed lines over 80 columns in the first hour, of which 20 over 120 and 8 over 190; the stderr '(the plan of …)' trailer appears after ask, plan accept, run and board take.
- Source pinned for every quoted line: plan_cli.py (NO_PLAN 31-34, FIRST_SAID 40-42, where 95-99, header 296, waiting-on-you 349, rows 366, accept 830-839, record 858-880, run 1034-1061, ask closing 1087-1094, node show 1424-1436), cli.py (init 328-339, 395-428), ask.py 427-456, plan.py 952-972 (contract) and 3058-3068 (where_said), precheck.py 236 and 330-345, run.py 465, 547-548, 632-649, 973, node_record.py 689-746 and 900-941, board.py 498-501 and 790, board_cli.py 19-24, 48, 193, 252, plan_text.py 639 and 862, tui.py 431-440 (the ∅ legend, read for the glyph vocabulary; the TUI itself was not walked beyond watch --once).

## the screen: `graphene watch` and the replay at 80x24 and 120x36, every state, every pane, the help, the glyphs

### S1. Three dollar labels and three clocks for one run share a single 80x24 screen; in watch the plan's dollars sit under "agents" though they include the planner

*Where:* src/graphene_map/tui.py:994 (spent = every usage row, planner's included), :1449 and :1461 (the dollars are a third field of the agents clock: `agents 2 · <1m · $0.42`), :1475 (`bill {spent}` exists but only in a replay); src/graphene_map/run.py:644 (`${…:.4f} at list price` in the goal pane's `last run`); src/graphene_map/view_time.py:218-221 (`agents 0 min $0.0057`); src/graphene_map/views.py:125 (money: 2 places from a cent) vs node_record.py:822 and run.py:644 (their own 4-place rule)

*What a stranger sees:*

> Replay of a fresh fake recording, end frame, 80x24 (shots/replay-new-end-time-80x24.txt): status line `0 on you · 0 running · none ready · 2/2 done, finished · bill $0.0057`; goal pane `last run  run: 1 done · agents <1 min, $0.0002 at list price · width 1 of 1 · you 1 act, 1 min`; the time view's note `2 lanes · <1 min · 1 came back · agents 0 min $0.0057 · you 7 acts ~1 min`. In watch with a meter (shots/metered-goal-80x24.txt): `4 on you · agents 2 · <1m · $0.42 · you 1 act ~1m · none ready · 1 came back`; with only the planner billed the same slot reads `agents 0 · 0m · $0.03` (test_the_bill_is_on_the_status_line pins it). The CLI's node show says `bill: $0.4200 at list price` for what the pane calls `$0.42`.

*Why it feels wrong:* Two totals ($0.0002 and $0.0057) and two "you" counts (1 act, 7 acts) are on screen at once with no word saying what each includes; `agents 0 · 0m · $0.03` says agents spent money while none ran (it is the planner's). The same amount is spelled `$0.42` here and `$0.4200` there, `agents … $` here and `bill $` there, so a reader cannot tell one bill from a different one.

*The smallest change:* In say_status give the dollars their own piece labelled as the replay and the leaf pane already label it: `bill $0.42` (one entry in `long` and one in `short`, the agents clock keeps `agents 2 <1m`); make run.clocks (run.py:644) and node_record._attempt_lines (node_record.py:822) call views.money so one amount has one spelling.

*Felt difference:* large

### S2. The status line at 80 columns is seven dot-separated fragments; a clock's fields are separated exactly like separate facts, and `1/9 done` falls off

*Where:* src/graphene_map/tui.py:1448-1449 (`clock = " · ".join([… running, … min, spent])`), :1461 (short form `.replace(' min', 'm')`, `R: 1 ready`), :253 (fit drops whole pieces off the end), :1478-1480 (forms tried, then fit)

*What a stranger sees:*

> shots/states-goal-80x24.txt, bottom: `4 on you · agents 1 · <1m · you 1 act ~1m · R: 1 ready · 1 came back` — `1/9 done` and `plan first: auto` have fallen off; the same plan at 120: `waiting on you: 4 · agents 1 · <1m · you 1 act ~1m · R runs 1 ready · 1 came back · 1/9 done · plan first: auto (P)`. On the empty plan: `0 on you · agents 0 · you 0 acts ~0m · none ready · 0/0 done · plan first: off`.

*Why it feels wrong:* `agents 1 · <1m` reads as two facts (one agent; something under a minute old) because the dot between a clock's fields is the dot between facts; `R:` assumes the reader knows R is a key; `~1m` and `<1m` are two abbreviations in one line. The time view's own note already joins a clock with spaces (`agents <1 min $0.42`), so the screen disagrees with itself about how a clock is written.

*The smallest change:* Join a clock's fields with a space, not ` · ` (tui.py:1449: `clock = " ".join(...)`): `4 on you · agents 1 <1m · you 1 act ~1m · R: 1 ready · 1 came back · 1/9 done` is 77 columns, so how much is done comes back at 80. Then adjust the two regexes in test_the_status_line_is_two_lines_fitted_at_a_word and test_the_status_line_has_the_two_clocks.

*Felt difference:* large

### S3. The time view has no legend and borrows two glyphs the legend has already given other meanings: ━ (critical path) and ◆ (review)

*Where:* src/graphene_map/view_time.py:34-37 (BLOCK █▓▒, TALK ░, QUIET ─, HELD ━, NOW ●, MARKS ! ✓ ✗ ↩ ◆) vs src/graphene_map/view_dag.py:12 and :398 (━ is the critical path) and src/graphene_map/plan.py:2962 (◆ is review); the legend at tui.py:430-446 names neither; Help.compose tui.py:499-518 does not know which view is open

*What a stranger sees:*

> shots/states-tab3-80x24.txt: ` ids     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━●` and ` docs   !↩` above an axis `0s 10s 20s…`, while the help's legend says `━ critical`; shots/replay-leaf-end-time-80x24.txt: ` you       ||  |` and ` greet      ━!↩━✓◆` where the outline's ◆ meant `a rule for ids  rule  review`; shots/metered-time-80x24.txt: ` ids     █▓▓▓▓●`. Nothing on the screen or in the help says what █ ▓ ▒ ░ ─ ! | or the time view's ◆ mean.

*Why it feels wrong:* A long heavy bar on a running leaf reads as "this is the critical path" to anyone who has read the legend, when it means "the meter saw nothing"; a ◆ at the end of a lane reads as "review" when it means "landed". A view made of glyphs with no key is a puzzle, not a picture.

*The smallest change:* In view_time.py pick two glyphs nothing else uses (HELD `═`, landed `■`), and give the view a `LEGEND` string built from its own constants (`█ edit  ▓ run  ▒ read  ░ talk  ─ idle  ═ held  ✓ ✗ check  ! refused  ■ landed  | you`, 69 columns); in Help.compose (tui.py:509) append it as a second legend line when `self.app.showing == "time"`.

*Felt difference:* large

### S4. The demo's first words are a disclaimer in jargon, and its bottom line speaks in the log's raw kind names

*Where:* src/graphene_map/demo.py:59 (STAND_IN = "a scripted stand-in, not Nemotron"), :284 (banner), :289-298 (what(): `f"{r['node_id']} {r['kind']}".removeprefix("* ")`), :68-69 (STAND_IN_NAMES turns Nemotron-3-Nano-fake into `stand-in-Nano`)

*What a stranger sees:*

> shots/replay-leaf-playing-f0-80x24.txt, the first second of `graphene demo`: top `replay · a scripted stand-in, not Nemotron · 2026-09-29 · 1 of 18`, pane `the script asked the planner: “make the app friendlier”. What it proposes is next.`, status `0 on you · 0 running · none ready · 0/0 done`, bottom line `asked`. Next frame's bottom line: `usage · goal_proposed · friendly proposed · greet proposed · farewell…`; the last frame's: `friendly rolled_up`. The leaf pane says `model  stand-in-Nano`, `bill  $0.0001 at list price for this leaf's 2 calls · stand-in-Nano`; the help's settings say `planner  stand-in --model stand-in-Ultra (graphene init…`.

*Why it feels wrong:* The first thing a stranger reads names something they do not know (Nemotron) to say this is not it, and "stand-in" is never explained; `asked` alone is a word with no subject; `goal_proposed` and `rolled_up` are identifiers with underscores where every other line of the screen is a sentence; `stand-in-Nano` and `stand-in-Ultra` look like model names that do not exist.

*The smallest change:* Three one-liners: STAND_IN = "scripted, no model ran"; in what() `r['kind'].replace('_', ' ')` and `the plan` for node_id `*` (the record pane already does `a.kind.replace('_', ' ')`); STAND_IN_NAMES second group → `stand-in` with no size suffix (the first impression needs no ladder).

*Felt difference:* large

### S5. The shipped demo never shows the meter strip, the screen's showpiece; a 26-second re-record with the scripted fake would

*Where:* src/graphene_map/demo.jsonl (its usage rows carry no `attempt`, so demo.py:369-374 sets METERS False); the recipe is in demo.py's module docstring (`RECORD_DEMO=src/graphene_map/demo.jsonl uv run pytest tests/test_demo_script.py`); src/graphene_map/nemotron/executor.py:480 now writes `attempt` and `turn` on every usage row

*What a stranger sees:*

> The shipped replay (shots/replay-shipped-f8-80x24.txt) with a leaf running: tree `● bye says goodbye  farewell  running`, pane, status `1 on you · 1 running · none ready · 1 came back · 0/2 done · bill $0.0033` — and no live row. I re-recorded with the fake (scratchpad/feel/screen/demo-new.jsonl, 15 changes, no spend) and replayed it: at change 6 the strip appears: `● greet · stand-in · attempt 1 · 0s · 0 files · no usage yet` / `  nothing yet · 0 s ago`, then `● farewell · stand-in Nano · attempt 1 · 0s · 2 turns · $0.0001` / `  running graphene node done farewell · 0 s ago · 1 file · 1k in, 82 out`.

*Why it feels wrong:* The README and the help promise a row per running leaf of what its meter reads; the one thing a stranger can run without a key shows a run with no meter at all, so the demo undersells the product it demonstrates.

*The smallest change:* Run the recipe once (`RECORD_DEMO=src/graphene_map/demo.jsonl uv run pytest tests/test_demo_script.py`, 26 s, no model) and commit the recording; tests/test_demo.py:267-268 pin the leaves greet and farewell, which the same script keeps, and test_demo_replay's `shipped … does not draw a strip` assertion flips to the better truth.

*Felt difference:* medium

### S6. In the replay, `l` pastes the executor's own log, including a refusal addressed to the model and a seventh duration format

*Where:* src/graphene_map/tui.py:2545-2548 (tail_pane: `R.tail(log)` lines are shown as they are when no did/said rows exist); the lines come from src/graphene_map/nemotron/executor.py:490 (`answered in {seconds:.2f} s`) and :796 (`{bill['refused']} writes refused`)

*What a stranger sees:*

> shots/replay-leaf-f9-greet-l-80x24.txt: `.graphene/runs/greet-20260929T075848-1e086fe1-1.txt` / `stand-in executor · stand-in-Nano · local placement · leaf greet` / `  1 stand-in-Nano answered in 0.00 s` / `  2 write words.py → words.py is outside the scope of the node you hold (greet: app.py). If the work cannot be done inside that scope, do not work around it: \`graphene node release  (0.00 s)` / `bill: 3 calls, 1769 in, 149 out, $0.0001 at list price, 1 writes refused`.

*Why it feels wrong:* The person is read a message written to the model ("the node you hold… do not work around it"), cut mid-command by the log's own truncation; `0.00 s` and `1769 in` are formats no other pane uses (`412k in`, `43s`), and `1 writes` is plural for one. It is the one pane that is a paste, where every other is laid out.

*The smallest change:* Have the Nemotron executor log `did`/`said` rows as the Claude executor does (then tail_pane's phrased branch at tui.py:2534-2541 takes over, as it does in shots/metered-ids-l-80x24.txt: `02:28:12  editing api.py`); failing that, in tail_pane elide each raw line to the pane and drop lines that begin with a step number's refusal text.

*Felt difference:* medium

### S7. The legend lumps the three magenta glyphs as `◇◆↩ yours` at both 80 and 120 columns, so review and came back are never named

*Where:* src/graphene_map/tui.py:430-446 (legend: the long form is 115 columns; `heavy` says ` critical path` in it), :506 (`column = HELP_WIDE if two else max(width - 8, 30)` gives 112 at 120 columns, 72 at 80)

*What a stranger sees:*

> Help at 120x36 (shots/states-help-120x36.txt), first line: `◇◆↩ yours  ? proposed  ○ ready  ● running  ◌ waiting  ✓ done  ∅ check flagged  ━ critical`; at 80x24: `◇◆↩ yours  ? proposed  ○ ready  ● running  ◌ waiting  ✓ done  ━ critical` then `∅ check flagged` alone on its line, with 56 empty columns after it. The tree shows `◆ a rule for ids  rule  review` and `↩ document it  docs  came back`.

*Why it feels wrong:* At the two sizes people actually use, the key never says what ◆ or ↩ is; three different glyphs with one word teaches that they are interchangeable, and the second legend line at 80 columns is mostly blank.

*The smallest change:* In legend(): say ` critical` in both forms (the long form drops to 110 ≤ 112, so at 120 columns all eight states are named), and in the two-line fallback put `◆ review  ↩ came back` before `∅ check flagged` on the second line (41 columns). The first line still starts with ◇ and holds `? proposed` and `━ critical`, so the pinned help tests keep passing.

*Felt difference:* medium

### S8. Fork rows reuse the leaves' glyphs with other meanings: ↩ is both "gave up" and "came back", · is both "lost" and "to fill in" (same dim colour too)

*Where:* src/graphene_map/tui.py:119-120 (FORK: lost/no tool call/out of steps/stopped `·` dim, gave up `↩` dim) vs src/graphene_map/plan.py:2956-2966 (LOOK: `·` to fill in dim, `↩` came back magenta)

*What a stranger sees:*

> shots/forked-goal-80x24.txt: `│ ├   · Nemotron-3-Nano-fake  fork 2  lost` and `│ └   ↩ Nemotron-3-Nano-fake  fork 4  gave up` directly above `├   ↩ the schema  schema  came back` and `└   · the rest, to be split  later  to fill in`.

*Why it feels wrong:* Two rows apart, the same mark means a fork that quit and a leaf that is the person's to fix; the dot means a fork that lost and a leaf with no contract yet. A glyph that means two things on one screen is one the eye stops trusting.

*The smallest change:* Give the fork outcomes glyphs nothing else uses in FORK (tui.py:119): lost/no tool call/out of steps/stopped → `–`, gave up → `⊘`; the word in the state column already says which, the glyph only has to stop claiming another row's meaning.

*Felt difference:* medium

### S9. At 80x24 a leaf that came back hides its last offer below the fold and the key line drops t, Enter and q

*Where:* src/graphene_map/tui.py:2411 (`one = all(5 + len(does) + 2 + len(command) <= pane.wide …)`: one long command puts every offer on two lines), :2415-2425; :1556 (row_keys for came back: t and Enter record after `? help`, so fit() drops them first); the pane is 9 rows when the tree takes 10 (tree_room tui.py:1311)

*What a stranger sees:*

> shots/states-on-docs-80x24.txt: pane `docs · came back` / `it needs docs/api.md, and ids has to land first` / `  w  widen its scope to docs/api.md` / `     graphene node widen docs` / `  b  a sibling leaf for docs/api.md (its check: true), which it waits on  ▇` / `     graphene node sibling docs` / `  n  wait on ids` / `     graphene node set docs --needs ids` — the `t  ask the planner` row is off-screen (the ▇ scrollbar hints at it), and the bottom line is `w widen · b sibling · n wait · e edit its check · r run it again · ? help`. At 120 the same leaf shows all four offers and `t ask the planner · Enter record · q quit`.

*Why it feels wrong:* The pane exists to put every way out in sight; here the fourth way (and the record, and how to quit) is invisible unless the person scrolls a pane nothing told them scrolls. Half the rows are commands the person will never type, since the key beside them does it.

*The smallest change:* In _came_back, when `used + 2 * len(rows) + 1 > high`, draw one line per offer (key and words only) and leave the commands to the record pane, which lists the offers already (record_pane, tui.py:2603-2608); then `t` fits and the key line's tail can keep `Enter record` at 80.

*Felt difference:* medium

### S10. A duration is spelled seven ways across the surfaces one session visits, two of them on adjacent lines of the meter strip

*Where:* src/graphene_map/tui.py:265 (elapsed: `43s`, `6m12s`, `1h04m`), :241 (ago: `42 s ago`, `3 min ago`, `quiet for 5 min`), :1448/1461 (status: `<1m`, `~1m`; long `<1 min`, `~1 min`), src/graphene_map/views.py:139 (billed: `6m`, `<1m`), src/graphene_map/view_time.py:218-221 (note: `5 min`, `agents 10 min`), src/graphene_map/node_record.py:874 (_took: `5 min`, `45 s`), tui.py:2507 (sandbox `12.3 s`), src/graphene_map/nemotron/executor.py:490 (`0.00 s`)

*What a stranger sees:*

> shots/states-goal-80x24.txt, the strip: `● ids · claude · attempt 1 · 43s · no meter` over `  Bash cat api.py · 42 s ago`; the status under it `agents 1 · <1m · you 1 act ~1m`; the dag `● ids  users returns ids <1m ━▸ ◌ more` (the `<1m` with no `$` reads as the title's tail); the time note `4 lanes · <1 min · … · agents <1 min`; node show `attempt 1 · claude claude-sonnet-5-5 · 5 min`; the record `07:58 → 07:58`; the replay's l `answered in 0.00 s`.

*Why it feels wrong:* `43s` and `42 s ago` one line apart make a reader wonder whether they measure the same thing; `<1m` on the status line and `<1 min` in the note under it are the same fact in two dialects; `~` means approximate in one place and nothing elsewhere. Each is fine alone; together they feel like several programs.

*The smallest change:* Use tui.elapsed (it exists) everywhere a span is shown: ago → `42s ago`; views.billed, view_time.note, node_record._took and run.clocks call it; keep `<1m` as its sub-minute form and drop the `~`. Five call sites, one spelling.

*Felt difference:* medium

### S11. Enter on the goal pastes the CLI's print into the pane, backticks and `<id>` included, while every other record is laid out

*Where:* src/graphene_map/tui.py:1924-1930 (action_record on the goal: `self.did(["plan", "record"], quiet=True, keep=True)` then finished()); _plain at tui.py:2692 already rewrites this exact text (`each has its own: \`graphene node show <id>\`` → `Enter on one shows its own`) but is used only for a sub-goal's record (tui.py:2606)

*What a stranger sees:*

> shots/states-goal-enter-80x24.txt: `the record of the 9 leaves in the plan (1 done; each has its own: \`graphene` / `    node show <id>\`):` / `    coverage: of the 2 paths git said had changed under them, 2 inside the` / `        scope of the leaf that changed it; 0 to a recorded edit, 0 to a` / … / `    width 1 of 1 · 100% of agent minutes alone`, with `graphene plan record` on the bottom line. Enter on a leaf gives `record · it scrolls` / `contract` / `holds` / `the check` with aligned keys.

*Why it feels wrong:* The screen's promise is that it shows what the commands print as panes, not as pastes; the goal's record is the one place the shell leaks through, and it tells the person to type a command the Enter key beside them already does.

*The smallest change:* In action_record pass each line of what `plan record` printed through `_plain` before finished() (one `"\n".join(_plain(l) for l in said.splitlines())`), or build the goal's record with `rolled_up` as the sub-goal's record does.

*Felt difference:* small

### S12. `q quit` and `? help` fall off the key line at 80 columns on the goal, a proposal, a sub-goal, a board item and a fork row

*Where:* src/graphene_map/tui.py:1514 (`tail = ["Tab view", "? help", "q quit"]` is appended last), :1547 (goal), :1540-1544 (board), :1559-1562; say_status tui.py:1480 fits the keys in order, so the tail is what is cut

*What a stranger sees:*

> shots/first-proposed-80x24.txt: `y accept it all · E edit the plan as text · za fold all · Tab view · ? help` (no q); shots/states-on-idea-80x24.txt: `y accept · d drop · e edit · E edit with what is under it · Tab view · ? help`; shots/forked-on-fork-80x24.txt: `fork 1: keys act on greet · l output · x release · Enter record · Tab view` (neither ? nor q); shots/board-first-80x24.txt: `y take · 1 pick · d drop · p park · Enter answer · a note · Tab view · ? help`. At 120 every one ends `· ? help · q quit`.

*Why it feels wrong:* The two keys a stranger needs most (how to get help, how to leave) are the first to go, on the very first screen they see; `Tab view`, which at 80 columns usually answers `no other view fits at 80 columns`, survives instead.

*The smallest change:* In say_status fit the tail first: `fit(tail)` then the row's keys into `room - tail.cell_len - 3`, so `? help · q quit` are always the line's end and the long middle piece (`E edit with what is under it`) is what gives way.

*Felt difference:* small

### S13. A folded row says `1 came back, 4 more` — more of what?

*Where:* src/graphene_map/tui.py:214-225 (inside(): `f"{rest} more"`), FOLDED = 20 at tui.py:114

*What a stranger sees:*

> shots/states-goal-80x24.txt: `├ ▶ ○ the API  api  1 came back, 4 more` and `├ ▶ ○ the schema  schema  1 review, 2 more`.

*Why it feels wrong:* Read left to right it says four more came back; it means four leaves in other states. The count is right and the sentence is wrong.

*The smallest change:* `f"{rest} others"` (or `+{rest}`) in inside(); `1 came back, 4 others` is 21 columns and the k == 1 branch returns it anyway, or raise FOLDED to 22.

*Felt difference:* small

### S14. The key hint `x release` on a running leaf is the CLI's verb; the panes and the record say "handed back", the state says "came back"

*Where:* src/graphene_map/tui.py:103-112 (KEYS["running"] = ["l output", "x release", "Enter record"]), :1896-1897 (x runs `node release --why …`); the person's words are at tui.py:2385 (`handed back` field), record_pane ends `"released": "handed back"`, HELP line 87 `x  release it; send it back; reopen it`

*What a stranger sees:*

> shots/states-on-ids-80x24.txt bottom: `l output · x release · Enter record · Tab view · ? help · q quit`; one row down, docs reads `came back` and its CLI print says `handed back: it needs docs/api.md`.

*Why it feels wrong:* Release to whom, from what? The same act is "release" on the key, "handed back" in the pane and "came back" in the tree, so the person has to learn three words for one arrow.

*The smallest change:* KEYS["running"][1] = "x hand it back" and the help row `x  hand it back; send it back; reopen it`; the command it runs stays `node release`.

*Felt difference:* small

### S15. The empty plan opens on a status line of six zeros and offers `Tab view` where Tab only says nothing is planned

*Where:* src/graphene_map/tui.py:1437 (counts default) and say_status; :1537 (row_keys on no nodes: `[":ask what you want", *tail]`); action_next_view tui.py:1236-1238 refuses Tab on an empty plan

*What a stranger sees:*

> shots/empty-80x24.txt: `Nothing is planned here yet. Tell your agent what you want, in a paragraph: it proposes the tree here. Or :ask <what you want>. ? lists the keys.` then, 19 blank rows later, `0 on you · agents 0 · you 0 acts ~0m · none ready · 0/0 done · plan first: off` and `:ask what you want · Tab view · ? help · q quit`.

*Why it feels wrong:* The pane says it plainly and the status line then counts nothing six ways; the first screen of a new repository should be two calm lines, not a dashboard of zeros.

*The smallest change:* When `not self.nodes` make the first status line empty (or the EMPTY sentence's last clause) and the keys `:ask what you want · ? help · q quit`; one branch at the top of say_status and the `tail` at tui.py:1537.

*Felt difference:* small

### S16. The help box at 80x24 is 79 columns wide, so the screen beneath peeks through its right edge

*Where:* src/graphene_map/tui.py:487-495 (Help.DEFAULT_CSS: `width: auto; max-width: 100%`), the help rows are HELP_WIDE = 72 plus padding and border

*What a stranger sees:*

> shots/states-help-80x24.txt: every row ends `│ |` and row 6 ends `│─|` — the pane border of the screen below shows in the last column; at 120x36 the tree's `▼ ├ │ └` show down the left edge beside the box.

*Why it feels wrong:* A stray `─` in the margin of a modal looks like a rendering fault, and a stranger's eye goes straight to it.

*The smallest change:* `Help > VerticalScroll { width: 100%; }` below two columns (the `two` branch at tui.py:505 already knows the width), or `min-width: 100%` at `-narrow`.

*Felt difference:* small

### What the screen reader walked

- Harness: scratchpad/feel/screen/shoot.py drives Watch and Replay headless with Textual's pilot (as tests/test_tui.py does) and saves the whole screen as text; 90 screens under scratchpad/feel/screen/shots/<scene>-<WxH>.txt, repos under scratchpad/feel/screen/repos/. Nothing spent: no model, no network.
- First look at 80x24 and 120x36: a proposal (tests' TREE via `plan propose`), the empty plan, and `?` on each.
- every_state (tests/test_tui.py:818): the outline on the goal, zR top and end, and the cursor on each of the eleven rows (api, ids running, docs came back, more waiting, later to fill in, mine yours, schema, rule review, table done, ready1 ready, idea proposed) at both sizes; the footer's key hints on each; the status line at both sizes; a visual selection.
- Panes: Enter (record) on ids, docs, table and the goal at both sizes; l on ids (hooks' tool calls), on api (a sub-goal), and on a metered ids (did rows); the goal pane with and without a `last run`.
- Help: first screen at 80x24 and the end (G), 120x36, the legend at both; the help inside the replay.
- Views: Tab cycle tree → dag → time → outline at both sizes with the bottom line's note each time; forced tree/dag/time for every_state and metered; the dag's critical path `━▸`; the time view with a held-unseen bar (━), with meter blocks (█▓), with !, ↩, ✓, ◆ marks and the `you` ticks.
- Meter strip: metered (tests/test_tui.py:2255) at both sizes, two live rows (Claude with a meter, a script without), the status line's two clocks and dollars.
- Board rows: planned board at both sizes, the first item and the next, their key hints, help over the board.
- Fork rows: a leaf forked four ways (running, lost, check failed, gave up) beside a came-back leaf and a `to fill in` leaf, at both sizes; the cursor on a fork row.
- Demo replay (shipped demo.jsonl): frames 1, 2, 3, 4, 6, 9, 13 and the end at both sizes, playing and paused; the leaf pane, its l pane and its record mid-run and at the end; the time view and the dag at the end.
- A second recording with the meter (tests/recordings/meter-claude.jsonl) at 80x24: frames 1, 2, 4, 9, 17, 33, the end, and its time view.
- A fresh recording made tonight by the scripted fake (`RECORD_DEMO=… uv run pytest tests/test_demo_script.py`, 26 s, no model): replayed at 80x24 to confirm the meter strip appears at change 6 (scratchpad/feel/screen/demo-new.jsonl).
- The CLI surface for the same metered plan with the installed wheel (tools/M/bin/graphene): `graphene plan`, `plan --view time`, `plan --view dag`, `node show ids`, `plan record`, to compare duration and money spellings with the screen's.
- Code read for every drawing site cited: tui.py (row grammar, legend, help, status line, key hints, panes, meter rows, record), view_time.py, view_dag.py, view_tree.py, views.py, board_rows.py, demo.py, plan.py LOOK/reads, node_record.py and run.py clocks, nemotron/executor.py's log lines.

## the rhythm: the same hour under a clock, what is printed when, the silences, and a Claude Code session's view of the hooks

### R1. The planner's half-minute is blank on both screens

*Where:* src/graphene_map/ask.py:427 (the one line) and :432-437 (proc.communicate() waits for the whole stream before anything is read); src/graphene_map/tui.py:1461 (the status line reads "agents 0" meanwhile; the "asked" row ask.py:400 logs is read nowhere in tui.py)

*What a stranger sees:*

> In the ask terminal: `asking the planner (claude)…` at +0.06 s and then nothing until +12.45 s (a 12 s stand-in; X1's median real answer is 26.5–29 s). When the first answer is refused: `Graphene could not read the proposal: line 5: signoff is yes or no, not 'perhaps'` / `asking the planner (claude) again…` and nothing again until +24.52 s. In the other terminal, `graphene watch` the whole time: `Nothing is planned here yet. Tell your agent what you want, in a paragraph: it proposes the tree here. Or :ask <what you want>.` with the status `0 on you · agents 0 · you 1 act ~1m · none ready · 0/0 done · plan first: on`.

*Why it feels wrong:* It is the first thing the README tells a stranger to type, and the first thing Graphene does is go quiet for half a minute (a minute with one refusal) on a single ellipsis, while the screen built to show agents at work says no agent is at work. The stream-json the planner prints already carries every Read/Grep/Glob it makes; the meter parses it (ask.py:436 `meter.feed(line)`) but only after the process has ended.

*The smallest change:* Read `proc.stdout` line by line instead of `communicate()`, feed the meter as lines arrive, and `say` one dim line per tool_use (`  reading normalize/fields.py`, `  grep 'def load'`); in tui.py's status (line 1461), when the log's last `asked` row has no `proposed` row after it, print `planner asked 12 s ago` in place of `agents 0`.

*Felt difference:* large

### R2. After `plan accept`, the next step is missing and the line that stands in for it is riddling

*Where:* src/graphene_map/plan_cli.py:839 (`left alone, agents can reach: …`), then said_where :97 as the last line; the person branch of next_lines (:127-200) is never reached from accept

*What a stranger sees:*

> `accepted feed, fields, readme` / `○ the new feed  feed  0/2 done` / `  ○ map the xml fields  fields  ready` / `  ○ name the new source in the README  readme  ready` / `the plan: the new feed loads like the others  (the planner's sentence, accepted with its tree)` / `left alone, agents can reach: fields, readme` / `  (the plan of /…/term-2/repo)`. Typed with nothing proposed (my first walk): `left alone, agents can reach: nothing`, exit 0.

*Why it feels wrong:* This is the one decision point of the hour, and after it the screen names no command. `graphene plan` a moment earlier printed `graphene plan accept X` three times; now that the person needs `graphene run`, nothing says it. "left alone" has no subject a stranger can supply, and "agents can reach" is Graphene's word for "ready to run". The goal sentence is also repeated with a parenthetical about where it came from.

*The smallest change:* Replace line 839 with `out(f"ready to run: {', '.join(n.id for n in runs)}  (`graphene run`, or R in graphene watch)")` and, when nothing was accepted, `nothing is proposed to accept` with exit 1.

*Felt difference:* large

### R3. `(the plan of /full/path)` ends 25 commands and opens `run`

*Where:* src/graphene_map/plan.py:1891-1895 (where_said), called from 25 said_where() sites in src/graphene_map/plan_cli.py; plan_cli.py:1000 calls it first in `run` ("said_where()  # first"); tui.py strips the same line in three places (1621, 1710, 2093)

*What a stranger sees:*

> Every ask, accept, node start, node done, and the first line of run ends or begins with `  (the plan of /private/tmp/…/scratchpad/feel/rhythm/runs/term-2/repo)` on stderr: 169 bytes, two rows at 100 columns, three at 80 on a deep path. In the session walk the agent read it after `node start fields`, `node done fields`, `node start readme`, `node done readme` and its own `plan propose`.

*Why it feels wrong:* The person is standing in that repository; being told its path after every act is the loudest repeated line of the hour, and on `run` it is the first thing printed, before "landing into main". Its purpose ("a stray cd cannot fool anyone") only applies when cwd is not inside the repo, which the function never checks. The TUI already judged it noise: it filters the line out three times.

*The smallest change:* In where_said, return None when `Path.cwd()` is inside `root` (keep it for a cd elsewhere or a worktree), or print only `where(root)`'s basename.

*Felt difference:* large

### R4. `graphene plan` on a fresh proposal prints the accept command three times and the whole-tree accept nowhere

*Where:* src/graphene_map/plan_cli.py:366 (sub-goal row: ``what += [f"`graphene plan accept {n.id}`"]``), :234 (leaf describe), :349 (the `waiting on you:` line names no command), :296 (the header)

*What a stranger sees:*

> `the plan (proposed with the tree, accepted with it): the new feed loads like the others` / `2 leaves, 0 done, 0 running` / `waiting on you: feed (proposed, with the 2 under it)` / ``  ? the new feed  feed  proposed  · `graphene plan accept feed` `` / `    ? map the xml fields  fields  proposed  · normalize/fields.py` / ``        `graphene plan accept fields` `` / `    ? name the new source in the README  readme  proposed  · README.md` / ``        `graphene plan accept readme` ``

*Why it feels wrong:* The person's one move is "accept it" (or prune in watch); the screen offers three partial accepts, one per row, and never the plain `graphene plan accept` or `y`. The header's "(proposed with the tree, accepted with it)" is grammar about provenance a stranger cannot parse on first sight. The ask that produced this had already printed the same three nodes as a flat list (`proposed feed: …`, plan_text.py:639) with the tree shape lost, so the person reads the proposal twice before learning how to accept it once.

*The smallest change:* Append the command once to the waiting line: ``waiting on you: feed (proposed, with the 2 under it): `graphene plan accept` takes all; y in graphene watch`` and drop the per-row hint when the row's parent is proposed too; indent plan_text.py:639's `proposed id: title` lines by depth so the ask shows the tree.

*Felt difference:* medium

### R5. The run's own terminal is silent for the whole attempt

*Where:* src/graphene_map/run.py:465 (`started`) → :547 (`attempt 1: the executor ended`), nothing between; the poll loop _waited at run.py:277-290 already calls `each()` every POLL (0.5 s) with the Reader feeding the meter

*What a stranger sees:*

> `fields started: map the xml fields` at +0.56 s, `readme started: name the new source in the README` at +0.64 s, then nothing until `fields attempt 1: the executor ended (exit 0)` at +12.97 s (a 12 s stand-in; X2's real main round took 84–130 s). Meanwhile `graphene watch` in another terminal did show life: `● fields · claude · attempt 1 · 4s · 0 files · no usage yet`.

*Why it feels wrong:* The person who typed `graphene run` in their only terminal gets a one-to-two-minute silence after "started", with the first line's hint to open another terminal as the only remedy. The meter rows the watch strip prints exist already; the run's terminal just never prints one.

*The smallest change:* In _waited's loop keep a counter and every 60 polls (30 s) `say` the meter's one-liner for that leaf (`fields · claude · 30 s · 4 turns · $0.08 · editing normalize/fields.py`), the same text the watch strip uses.

*Felt difference:* medium

### R6. The run opens with 299 characters of git flags, unwrapped, then a jargon tally that repeats the line above it

*Where:* src/graphene_map/plan_cli.py:1049-1052 (the `landing into` line, printed with `out` = typer.echo, so not word-wrapped); src/graphene_map/precheck.py:345 (`red first: …`) after :327-328

*What a stranger sees:*

> ``landing into main at 0a33847: claude, up to 2 at once, an attempt stops once it passes $2; each leaf is committed with --no-verify (your pre-commit and commit-msg hooks skip it) and merged --no-ff; checks run in a clean worktree with your PATH; `graphene watch` in another terminal follows it live`` as one line broken mid-word over three rows, then ``fields, readme: their check passes at the base commit 0a33847: it proves nothing; `graphene node set <id> --check '…'` or e in watch`` and `red first: 2 checks at 0a33847 (1 command) in 0 s`.

*Why it feels wrong:* Before anything has happened the person reads a paragraph of commit flags they did not ask about, and then two lines about the same two checks, the second under a name ("red first") no screen has introduced; "e in watch" assumes they know watch's keys. The useful facts (where it lands, how many at once, the cap, where to watch) are buried in the middle.

*The smallest change:* Keep ``landing into main at 0a33847: claude, up to 2 at once, $2 an attempt at most; `graphene watch` in another terminal follows it live`` through `say` (wrapped), move the --no-verify/--no-ff/clean-worktree clauses to `graphene run --help`, and drop precheck.py:345's tally line when every check already got its own line.

*Felt difference:* medium

### R7. `node show` on a landed leaf: the agent's instructions first, the landing 33 lines down, two facts said twice

*Where:* src/graphene_map/plan.py:970-971 (`finish:` and `stuck:` printed for a done leaf), src/graphene_map/node_record.py:845-856 (`said last:` then `the last it did:`; the dedupe at :854 only fires when the said text is the log's last line), :786/:797 and :843 (the refused command twice), :712 (the `in short` sentence)

*What a stranger sees:*

> 35 lines beginning ``finish: graphene node done readme   (runs the check and asks git what changed)`` / ``stuck:  graphene node release readme --why '<what is in the way>' …`` for a leaf already done; then `in short: 1 path changed under it, 0 traced to a recorded write; the 1 commit inside its windows is in no record of a session that held it, so not graded, which takes nothing from the paths`; `refused: 1 command refused to the executor` and later `refused: python3 -m unittest -q tests` again; `said last: done: readme is done (check passed, nothing outside its scope) next: stop here…` and under `the last it did:` the identical sentence; finally ``landed: 1d86472: `graphene node diff readme` shows it``.

*Why it feels wrong:* The README's step after a run is `graphene node show <a landed leaf>`; what the person wants (did it land, what changed, did the check mean anything, what it cost) arrives last, after a contract written for an agent and an audit sentence no one can parse, with the executor's closing words and the refused command each printed twice.

*The smallest change:* For a DONE leaf, print the `landed:` line and the check line first and skip `finish:`/`stuck:`; at node_record.py:854 dedupe with `if a['said'] in told: told.remove(a['said'])`; print the refused commands once (drop :843 when :797 printed them).

*Felt difference:* medium

### R8. The morning after: Enter on the goal answers "what happened?" with an audit ledger, and the two dollar figures disagree

*Where:* src/graphene_map/node_record.py:909-941 (the record's lines; `plan record` and watch's Enter on the goal), tui.py:2695 (rewrites the hint to `Enter on one shows its own` while the bottom line says `Enter back`, :1521); tui.py:1455-1465 (status `$0.04` is planner + leaves; the pane's `last run … $0.0246` is leaves only, unlabelled)

*What a stranger sees:*

> Opened cold on the finished plan: `0 on you · agents 0 · 0m · $0.04 · you 2 acts ~1m · none ready · 2/2 done, finished`, the leaves folded under `▶ ✓ the new feed  feed  2 done`. Enter on the goal: `the record of the 2 leaves in the plan (2 done; each has its own: `graphene node show <id>`):` / `coverage: of the 2 paths git said had changed under them, 2 inside the scope of the leaf that changed it; 0 to a recorded edit, 0 to a recorded shell command, 2 to git alone` / `checks run by Graphene itself: 2 of 2 passed at last run, 0 runs failed on the way; 0 writes refused; 0 `done` refused over paths outside a scope` / `width 2 of 2 · 20% of agent minutes alone` / `last run: run: 2 done · agents <1 min, $0.0246 at list price …`. Which files changed appears only in the dag view's pane, two Tabs away (`changed  normalize/fields.py`).

*Why it feels wrong:* Within a minute the person does learn that nothing waits on them (good: `0 on you`), but the natural key for "what happened" returns coverage, grading, width and "alone" (words from meter.py:415 never defined on screen) and no list of what landed where; $0.04 and $0.0246 sit on the same screen with no word saying one includes the planner (the X3 readers made exactly this mistake). "done" appears six times on the opening screen while the file names appear zero.

*The smallest change:* Open the record (node_record.py:909) with one plain row per leaf before the coverage lines: `✓ fields · normalize/fields.py · landed 3ba9990 · $0.01`, from each leaf's windows[].under, landed sha and bill; label the status figure `$0.04 in all` (tui.py:1455) or the pane's `leaves $0.0246 + planner $0.0123`.

*Felt difference:* medium

### R9. At 80 columns the finished plan's first screen loses `? help · q quit`

*Where:* src/graphene_map/tui.py:1541-1546 (the goal row's keys when finished) and fit() at :253, which cuts from the right; the ponytail comment at :1543-1544 pins `? help` on an 80-column line for the Enter hint but the archive hint breaks the same rule

*What a stranger sees:*

> At 80×24 the bottom line reads `:plan archive puts it away · E edit the plan as text · za fold all · Tab view ` and stops; at 100 columns the same line ends `· ? help · q quit`. The status line above it also loses `2/2 done, finished`.

*Why it feels wrong:* A stranger opening watch in a default 80-column terminal on a finished plan is shown a colon-command and an editor key, and not the two keys that would tell them everything else or let them leave. The keys list is 95 characters; the cut is silent, with no ellipsis.

*The smallest change:* In row_keys for the goal (tui.py:1546) put `? help` and `q quit` before the row's own keys when `len(" · ".join(keys)) > room`, or shorten `E edit the plan as text` to `E edit as text` and `:plan archive puts it away` to `:plan archive`.

*Felt difference:* medium

### R10. The Claude Code person's hour ends on a line blaming a command they never typed

*Where:* src/graphene_map/plan.py:1906-1909 (UNCOMMITTED), reached from plan_lines at src/graphene_map/plan_cli.py:318-320 whenever every leaf is done and the checkout holds their work

*What a stranger sees:*

> After the session did both leaves itself under plan first on (`graphene node start fields` … `graphene node done readme`), `graphene` in the other terminal says: ``2 leaves, 2 done, 0 running · finished; the work of 2 leaves is not committed (`git status`): `graphene run --here` commits nothing, `graphene run` and watch's R commit and merge each leaf; `graphene plan archive` puts it away``.

*Why it feels wrong:* The person never ran `graphene run --here`; the session wrote in their checkout, which is the normal in-session path. The line explains a flag they did not use, tells them a run would have committed (too late), and still does not say the one true next step: commit the work. In watch the same plan shows `0 on you`.

*The smallest change:* Make UNCOMMITTED say what to do: ``is in your checkout, uncommitted (`git status`): commit it yourself; `graphene run` lands each leaf as its own merge``, and add the `--here` clause only when the plan's last run row was `--here`.

*Felt difference:* medium

### What the rhythm reader walked

- Terminal person, fresh feeds repo (runs/term-2), the fake planner/executor in front of the 0.5.0 wheel, every command under a pty recorder at 100 columns with per-chunk timestamps (feel/rhythm/walk2-100.txt, t2-100-*.timeline): interactive `graphene init` (1, Enter), bare `graphene`, `graphene ask <the feeds paragraph>`, `graphene`, `graphene plan`, `graphene plan --view tree`, `graphene plan accept`, `graphene run --parallel 2`, `graphene`, `graphene node show readme`/`fields`/`feed`, `graphene plan record`, `git log --graph --oneline`, `git log --format='%s%n%b' -3`, `graphene board`, `git status --short`.
- The wrong path first (runs/feeds-sealed-term-1, walk-term-100.txt): newrun.sh's silent non-interactive `init` chose no planner on this machine (codex is on the PATH too), so `ask` refused and `plan accept`/`run`/`node show` were typed against an empty plan: `left alone, agents can reach: nothing` (exit 0), `nothing to run: the plan has no open leaf`, `the record of the 0 leaves in the plan`. Also a first `init` where Enter at `choose:` with two agents found loops on `choose 1, 2 or 3` (init-first.timeline).
- The refusal rhythm (runs/refuse-1, refuse-ask-1.timeline): the fake's bad first answer → `Graphene could not read the proposal: line 5: signoff is yes or no, not 'perhaps'` → `asking the planner (claude) again…` → the proposal and `2 calls, $0.02`. The refusal line itself reads well; it only doubles the silence.
- The waits measured (runs/slow-1): a `claude` wrapper that sleeps 12 s before exec'ing the fake, first on PATH so the meter still reads it; `ask` (24.5 s on one line, slow-ask.timeline) and `run --parallel 2` (12.3 s of nothing between `started` and `ended`, slow-run.timeline), while `graphene watch` ran headless beside each and was snapshotted at 100×24 (slow-watch-during-ask.txt: `Nothing is planned here yet… agents 0` throughout; slow-watch-during-run.txt: the meter rows `● fields · claude · attempt 1 · 4s · 0 files · no usage yet`, then the finished screen).
- Claude Code person (runs/session-1, walk-session.txt): hooks installed by `graphene init --planner claude --executor claude`; each hook event fed to the installed hook as Claude Code sends it, each session command run with the session's marks: SessionStart (549 words: TEACH plus the plan-first paragraph), UserPromptSubmit with the paragraph (the plan-first paragraph again, 77 words), PreToolUse Read (silent), Write before proposing (43-word deny ending with how the person turns plan first off, gate.py:236), Bash unittest (silent), `graphene plan propose -` as the session (`3 proposed: nobody can start them until the person accepts…`), Write again (denied), Stop (silent); the person's `graphene` and `plan accept` in the other terminal; the second prompt (`Or take a leaf already planned…`), `graphene node start fields` (the contract), Write in scope (silent), Write README.md twice (58-word lecture, then 23 words), Bash redirect out of scope (denied), Stop while holding (49-word block), `graphene node done fields` (`next: readme … is ready`), Stop (silent), start/done readme, Stop, `graphene` (the `run --here` line), `git log` (nothing landed).
- Morning after (tui-100x30.txt, tui-80x24.txt): `graphene watch` driven headless with Textual's pilot on term-2's finished plan at 100×30 and 80×24: opened, Enter on the goal, Esc, j, Enter on feed, Esc, c, l, Esc, Tab ×4 (tree, dag, time, outline), ?, Esc, q; status lines, bottom lines and panes read after each key.
- Seen and judged smaller than the ten: `init` says the plan-first choice twice within five lines (cli.py:390-395 menu, :412 FIRST_SAID) and lists eight vendor event names (cli.py:418); the plan-first paragraph reaches the session at SessionStart and again at its first prompt seconds later (gate.py:269, :338); `_first_refused` tells the agent how the person turns the gate off (gate.py:236); three names for going back (`Enter back`, `l back`, `Esc back`, tui.py:1521-1525) and `Enter on one shows its own` under a bottom line saying `Enter back` (tui.py:2695); the time view's `!` glyph is not in the help's legend (view_time.py:36 vs tui.py LEGEND); the leaf commit's title is its subject and its first body line (run.py:880); `node show` on a sub-goal prints empty `scope:`/`done:` and an agent's `finish:` line (plan.py:963-971, already in morning.md); the empty plan's status reads `0/0 done`; the init-time `this Claude Code has no --max-budget-usd` line is the fake's `--help`, not a finding.
