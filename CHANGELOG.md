# Changelog

## 0.8.0 (unreleased)

0.7.0 was tagged but never published (its tag built 0.6.0 again): everything below ships in 0.8.0.

Auto mode (26 October 2026). You give Graphene a goal and an envelope once; it plans, accepts what fits, runs,
checks the goal and plans the fix. Each line is one change.
- `graphene auto "<goal>"` (visible, the person's alone; from an agent: `` `graphene auto` is the person's ``):
  turns `auto: on`, writes `--budget`, `--tasks`, `--rounds` and `--forks` into the settings as one `settings`
  row, says the envelope (`envelope: auto on since 00:31 · $2.00 · 12 tasks · 2 fix rounds · 1 fork a task · 4
  at once`), sets the goal, asks the planner (`--planner`, else init's) for a tree under a root sub-goal that
  carries the goal's check (`--check`, else every task's check run together), accepts what fits the envelope,
  runs it (`--with`, `--parallel`, `--attempts`, `--forks`), and when the root's check is red asks the planner
  for the fix under it (the check's command and the tail of what it said), for `rounds` rounds. It ends with
  `auto: 2 rounds, 3 tasks landed, 0 came back, 0 forks raced, $0.0123 at list price; the goal's check passed.
  `graphene plan log` has the whole history`; exit 0 passed, 1 still red, the budget spent or stopped, 3 waits
  for you. With no goal it goes on with the plan in force. Each stage is an `auto` row on `*` (`round`,
  `rounds`, `stage` planning|running|checking|fixing|done|waits, `spent`, `budget`, `check`, `why`).
- The envelope is settings: `auto: off|on`, `budget: DOLLARS`, `tasks: N` (12 unset), `rounds: N` (2 unset), in
  `graphene config edit` and the table in HOW_IT_WORKS; `graphene config set KEY VALUE` changes one setting
  without an editor (`added: auto: on`, `removed: auto: off`), person-only, logged as every setting is.
- With `auto: on`, a proposal that fits is accepted at once, from `graphene ask` and from an agent's `graphene
  plan propose -` alike: every new task has a scope and a check, the tasks accepted since auto went on plus
  these stay within `tasks`, nothing on the board waits for you (a question with no default, a default that
  drops a task), nothing splits a task someone holds. It is accepted as your stand-in (`alex (no terminal)`,
  `by: auto`), so `graphene plan undo` takes it back and the board's defaults are taken as at your accept. It
  says `accepted inside your envelope (auto on since 00:31 · $2.00 · 12 tasks): greet, bye. `graphene run` runs
  them; 2 tasks can run at once`, or the one reason it waits (`waits for you: greet has no check`; `waits for
  you: your envelope accepts 12 tasks and this makes 14`). `graphene plan log` says `accepted by your envelope,
  round 2`. Nothing an agent sends changes the envelope.
- A budget holds Claude Code and Codex attempts through the run's cap; Nemotron bills each call after it ends,
  so the budget is read between rounds (said first); an executor that reports no cost is said first too, and
  its attempts are counted instead of dollars.
- Planners split wide: the sizing sentence, `graphene ask`'s rules and Nemotron's system prompt (version 7) say
  that leaves that run at once share no file, each its own test file, `needs:` only where one uses another's
  work; after an accept Graphene says how many tasks can run at once.
- Safety in auto mode: the envelope never takes a task whose scope reaches `.claude/`, `.codex/`, `.cursor/`,
  `.gemini/` or `.github/workflows/` (`waits for you: reach's scope reaches .claude/, where the agents' own
  settings and hooks live (or the CI that runs with your secrets): you accept that yourself`), since a held task
  whose scope names the hooks' settings may write them; and while auto is on every run counts against the budget,
  an agent's own `graphene run` and the cockpit's `R` too (`nothing starts: your envelope's budget is spent ($0.60
  of $0.50)`), capping a Claude Code or Codex run at what is left.
- `graphene auto "<goal>" --plan` plans and accepts inside the envelope and runs nothing (`auto: planned round 1
  inside your envelope and ran nothing: \`graphene plan\` shows it, \`graphene auto\` runs it`); `graphene auto`
  then runs that same round.
- `checks:` in the settings names the commands the envelope runs as a task's check without the person
  (`graphene config set checks "python3 -m unittest, uv run pytest"`); unset, it takes one plain command and no
  `;`, `&&`, `|`, redirect or `$(…)` outside quotes. A check outside it waits (`t1's check is not one your envelope
  runs (one plain command, …): \`pytest -q && curl … | sh\`; you read it and accept it yourself`): with auto on,
  nobody else would read a planner's check before Graphene runs it.
- `.git/` is nobody's: a scope that names it is refused at propose (`its scope names .git/hooks/pre-commit, and
  .git/ is git's own: a hook planted there runs on your next commit, and git status never shows it`), and a write
  into it is refused whatever the scope says, `**` included. Before, a leaf scoped to `.git/hooks/pre-commit` was
  proposed, could be accepted (at once, by the envelope), and could write there unseen by `done`.
- A fix round says what the goal's check failed on, on its row (`why`), the head (`auto · round 2 of 3 · fixing:
  FAIL: test_a_hyphen_splits_a_word`) and a replay's news; a red check names its failing test first (unittest's
  `FAIL:`, pytest's `FAILED`).
- A goal whose first planning failed (no key, a planner stopped) is planned again by the next `graphene auto`,
  with the goal's check as first given; a budget under one attempt's worst case says so at once (`the budget left
  ($0.50) is less than one attempt's worst case ($1)`), where nothing used to start and the plan was blamed; with
  Claude Code the round's dollars are its stream's.
- Red first is a gate in auto mode: nobody reads what lands, and a task whose check passes before any work
  would land with nothing done, so `graphene auto` stops before it runs (`waits for you: bye-fix: its check
  passes before any work, so it would land with nothing done: …`). Under `graphene run` it stays a warning.
- In the cockpit, `:auto <goal>` runs auto mode as a process of its own, and `:stop` stops it.
- `.GIT/`, `.CLAUDE/` and the rest are guarded as `.git/` and `.claude/` are: a Mac's disk ignores case, so a write
  to `.GIT/hooks/pre-commit` lands in `.git/hooks/`.
- `graphene demo --auto` replays auto mode on Nemotron against the scripted stand-in (`dev/proof/auto.sh` on
  wordkit, recorded by `tests/test_demo_auto.py`): three tasks, nine forks at once, one stopped writing a file
  outside its task, the whole suite red after all three land, Ultra's fix, the suite green. The wheel carries it.

The race on screen (26 October 2026). Each line is one change.
- Every agent's row names its model in a word (`meter.short`: Nano, Super, Ultra; Haiku, Sonnet, Opus, Fable;
  Codex; a script by its name), from the rows that already carry it; each fork's line its own model and dollars
  (`1b Nano ✓ passed · 7 lines · $0.0003`); a forked task's line how many race and on what (`3 forks · Nano ×3`).
  A stand-in's replay keeps the stand-in's names (`stand-in-Nano`).
- While auto is on, the cockpit's and the graph's head carry one more line: `auto · round 1 of 3 · running ·
  $0.42 of $2.00 · 5 of 12 tasks`, in the need-you colour and on top while it waits for you, with why.
- On the graph, `+` adds a step after the task you're on (`graphene node add TITLE --parent … --needs …`, then `e`
  fills its scope and check) and `L` then `L` on another task links them; the head says how many tasks can run at
  once. `graphene node set B --add-needs A` adds to what B waits on without replacing it, and refuses a cycle with
  its reason.

Editors (26 October 2026). Each line is one change.
- `graphene state --json` (hidden): one snapshot of everything the cockpit shows (the goal, the envelope, the
  auto round, the run, the scoreboard, the width, each task with its state, scope, needs, check, agent, model,
  dollars, forks and the kept one, the questions, the edges, the news), read-only and fast; outside a plan it
  prints `{"schema": 1, "error": "…"}` and exits 1. `graphene plan log --json --since ID` follows the log.
- Graphene for VS Code in `editors/vscode` (0.8.0, not on the Marketplace yet: `npm run package` makes the
  `.vsix`): a Plan tree, the plan as a graph in an editor tab and the sidebar (forks fanning out, the kept one
  marked, the model on every running box, the auto line), a details pane with Add step after, Add step under,
  Link to…, Edit, Drop, Accept and Tell, a status bar (`◆ 2 running · 1 needs you · $0.42`), and the commands
  Open Cockpit, Auto…, Run Ready Tasks and Stop. Each click is a `graphene` command run as you: the agents' marks
  are taken out of its environment. CI builds and tests it in a job of its own.
- Click and connect: in the graph, drag a task's dot (its right edge) onto another and that one waits on it
  (`graphene node set B --add-needs A`); the × beside a task under "needs", in the details pane, unlinks them
  (`--needs` with the rest, or `none`).
- A Rounds view: auto mode's iterations from `graphene plan log --json`, a row a round (`Round 2 · done · 1
  accepted · 1 landed · goal ✓ · $0.02`), under it what the envelope accepted, which fork each task kept and why,
  what landed, and the line that sent the round to fixing.
- The Explorer marks each file a task owns: a running one's with its agent's number (the task, model and forks in
  the tooltip), then ✓ waiting for your sign-off, ! came back, · not started; the scope globs are read as the CLI
  reads them (a table of 208 of `in_scope`'s answers holds the port).
- Auto… asks for a goal, a budget and whether to plan first (`--plan`); Set Envelope… shows the envelope and sets
  one setting (`graphene config set`); Set Up This Folder runs `graphene init` where a folder has no plan; a
  notification says when auto mode waits for you (and why), plans a fix, or is done.
- Each GitHub release carries the extension's `.vsix`, built from the tagged commit (docs/RELEASING.md).

Any model, any agent, a port a task (26 October 2026). Each line is one change.
- Graphene's own planner and tool loop run on another host with `--endpoint`: `nim` (NVIDIA's API catalog,
  `NVIDIA_API_KEY`), `ollama` (this machine, no key) or `openai` (any OpenAI-compatible URL in
  `GRAPHENE_OPENAI_BASE_URL`), as `--with 'nemotron --endpoint nim'` or `graphene init --executor 'nemotron
  --endpoint nim'`; `graphene key set --endpoint nim` keeps that host's key. A host with no Nemotron takes
  `--model`, else its first chat model, and says which; a model with no list price is billed as "no list price".
- Only a host on this machine stands in: NIM, an OpenAI-compatible URL elsewhere, and Token Factory's own host
  spelled another way (a port, a case) or behind a proxy are guarded as Token Factory is, an agent's call refused
  unsent without the person's opening.
- `--with` takes `{prompt}` and `{prompt_file}` for a CLI agent that reads its task from somewhere other than its
  last argument (recipes for aider, gemini, opencode and goose in HOW_IT_WORKS, not tested here).
- `ENDPOINT=ollama dev/proof/auto.sh` runs the live take free on this machine's Ollama
  (`ollama pull nemotron-3-nano:4b` first), `ENDPOINT=nim` on NVIDIA's API catalog.
- Every executor a run starts gets `PORT` and `GRAPHENE_PORT`, its own (per running task and per fork, free when
  handed out), said in its contract and given to its check.

Forks (20 October 2026). A task can run as several agents at once, and its check keeps one. Each line is one
change.
- `forks: 3` under a leaf (`graphene plan edit`, `graphene node set ID --forks 3`), `graphene run --forks 3` for a
  run, or `forks: 3` in `graphene config edit` for every leaf: the leaf runs as that many agents at once, each in
  a worktree of its own (`.graphene/worktrees/<id>.<letter>`) with its own session, attempts and meter rows, and
  told so (`This is fork b of 3`). The leaf's number counts first, then the run's, then the setting; forks need a
  check (`a sign-off cannot choose`), and `--here` refuses them (`forks need worktrees: drop --here`).
- A fork is held as a leaf is, in its own copy alone: with Claude Code a write into the leaf's tree, another
  fork's copy or the checkout is refused before it happens; its `graphene node done` judges its own tree and
  changes no state (`the check passed in this fork (fork b of 3); Graphene keeps one when the forks end`); its
  `release` is its giving up (`this fork gives up; the leaf is handed back only if every fork does`); what you
  tell the task reaches every fork, once each; a fork with a verdict may stop; its tree is judged as it stands
  when its executor ends, whatever its own `done` said.
- When the forks end, the rule in `src/graphene_map/pick.py`, written before any fork ran, keeps one: among the
  forks whose check passed inside the scope, the one that passes the most of the other forks' tests (its test
  files laid over another's tree, under the leaf's own check; its own tests count for nobody), then the one
  that left its check's own files alone, then the smaller, the cheaper, the sooner; the run says which step
  decided (`n1 kept b of 3: 2 lines against 11`), the kept fork's changes are copied into the leaf's tree and
  the leaf is finished there once, so it lands as any leaf does (the merge says `3 forks, kept b`), and each
  fork's work inside the scope is kept on `refs/graphene/forks/<id>/<letter>`. None passed: the task comes back
  with every fork's reason (`no fork's check passed (3 forks): fork a: …; fork c: handed it back: …`) and the
  union of what they asked for. `--first` keeps the first fork whose check passes and stops the rest
  (`another fork's check passed first`). `--with` more than once gives each fork its executor, round robin;
  `claude:MODEL` and `codex:MODEL` name a model. The worst-case line multiplies by the forks (`1 leaf x 3 forks
  x 1 attempt x $2 = $6`), and a fork `--max-usd` has no room for does not start (`2 of 3 forks started`).
  Nemotron forks as any executor does. A dead run's sweep keeps each fork's work on its ref, then removes its
  tree.
- `graphene node show` lists a forked hold's forks (`forked 3 ways · kept b: 2 lines against 11`, then a line a
  fork: executor, attempts, how it ended, lines, dollars, time; each attempt says its fork), `graphene node diff
  ID --fork b` prints what fork b tried, from its ref, and `graphene plan record` says `3 forks, kept b`.
- `graphene node pick ID c` (hidden; the person's own act) on a task in review whose hold forked makes its
  branch fork c's work ("n1's branch is now fork c's work (passed); `graphene node signoff n1` lands it"), so
  the sign-off lands your pick and the record says `kept c: picked by alex`.
- In the cockpit, `f` forks the task under the cursor (the setting's number when it is 2 or more, else 3) and
  runs it; a forked task's row says `3 forks` and opens to a line a fork (`1a ▁▂▃▅ ✎2  edit app.py`, `1b ✓
  passed · 31 lines`, `1c ↩ gave up: …`), a fork the run stopped says `ended`, a dim line says `kept b · <the
  reason>` once one landed (`your pick` when you chose), a digit picks another fork of a task in review (`1-3
  pick`), the details' record has a forks table (fork, with, attempts, state, lines, dollars, seconds), the
  replay's news names a fork (`agent 3b`), `?` says what `f` does and what `3b` is, and the graph's box says
  `3 ×3` while the forks run.
- The held bench (`dev/held/`) asks a second question, written before any number: does G3, Graphene with three
  forks a task, claim done while wrong less often than one agent, or land more tasks (`dev/held/rules.md`)?
- A store is version 6 once a node in it is saved with forks: a graphene from before refuses it in words
  (`was written by a newer graphene; upgrade this one`) and leaves it as it is. Until then it stays version 5,
  one 0.6 reads, and whose hook 0.6 still runs.

The graph flows into the goal (20 October).
- `g` draws the goal as the last box, at the right; every arrow says "must land before": from a task to each
  task that waits on it, and from a task nothing waits on to the goal. Columns are waves, with a header each
  (`wave 1 · 3 agents`, `wave 2 · agent 4`, `goal`); sub-goals are lanes, a rule across the graph with the
  sub-goal's title and its count (`── say hello ──── 2 of 2 ✓ ──`; nested, `parent › child`); the longest chain
  into the goal is drawn in double lines, and the goal box carries `4 of 4 ✓` on its border. The legend says
  what it drew (`═ the longest chain into the goal · ─ other needs`, `lanes: sub-goals · columns: waves`). Too
  wide, the graph shows the selected task's neighbourhood under the plan's own wave numbers, and gives up the
  goal before a step of context. The sub-goal boxes, and the tree's lines pointing away from the goal, are gone:
  the graph no longer reads "from your goal down".
- A line keeps its row across a column and turns at its target's; the chain's boxes lead their lane; no line is
  joined by a stranger's corner; a lane's label ends before a line crossing its rule; the graph is as wide as a
  lane's rule needs; the legend wraps; the lines end at the last box; a cycle among needs (a hand-edited store)
  still puts the goal last.

The gate fails closed (20 October).
- From Claude Code 2.1.295, `graphene init` at a terminal sets `"onFailure": "block"` on the gate's hook
  (PreToolUse): a hook that cannot start, errors or times out refuses the call instead of letting it through,
  and init says so ("the gate fails closed: when `graphene` cannot run, Claude Code here is refused each tool
  call until it can"). An install from before is closed in place; the events that only record stay open; an
  older Claude Code, or an init from a script, keeps the open gate.
- A tool call the gate raises on while judging it is refused, not let through (`Graphene could not judge this
  call (its error is in .graphene/ingest.log), so it is refused; say it another way, or ask the person`); a
  Stop or a prompt still goes on, so a recording that fails never stops a session.
- A redirect to a path outside the repository beside an out-of-scope write (`pytest -q > /tmp/pytest.log 2>&1;
  echo x > src/db/schema.py`) no longer lets the write through: the log is nobody's to judge, and the rest of the
  command is refused as before.
- The shell reader reads before the write what the 19 October review found it missed (findings 1, 4, 5 and 6
  of dev/process/publish/gate/review.md): a `#` comment ends at its line, and a `<<WORD` inside quotes, a
  comment or `$((1<<n))`, or a here-string `<<<`, starts no heredoc, so the lines after it are read; `cd -P`,
  `cd --`, `cd -`, `pushd` and `popd`, `cd $PWD/…` and a subshell's `cd` are followed as bash follows them;
  `>&`, `<>`, `&>>`, `|&`, `dd of=` and `install` are writes, and so is `tee` under `command -p`, `nice -n 1`
  or `env -i`; a target in `$PWD`, `$HOME` or a variable the command set is judged; a quoted `>` in a `grep`
  pattern writes nothing, and a move into the scope's own directory is not refused. A target in another
  variable, a glob or a command substitution is still left to git at `done`, as before (refusing it refused
  `sed -i … src/*.py`), and so are findings 2 and 3: a cwd that is a checkout of its own, and a link in the
  scope that leads out of it.
- `graphene run --max-usd` under one attempt's worst case starts nothing and now says so: `one attempt holds
  $2.00 until it ends: --max-usd 2 starts one`.

## 0.6.0 (19 October 2026)

The first release on PyPI since 0.5.0: it holds everything under 0.5.1 below (never published) as well as this.
`graphene watch` is a new screen, which is why the minor version moves. Each line is one change.

The new watch (17 to 19 October). `graphene watch` opens a cockpit, first judged in `dev/ui/playground/`, fed by the
real plan and wired to the real commands; `graphene watch --classic` is the older outline, and `--view` picks its views.
- A row a task, with the number of the agent on it: agent 1 is on the first task anyone took, and a task keeps its
  number when it comes back and is tried again (the animal names are gone). What needs you is on top, and the head
  (your goal, what needs you, what runs, what is proven) stays while the rows scroll.
- Enter does the row's own move: accept, try again, sign off. `A` accepts every proposal after one line; a
  proposal opens to show the files it may change, its check and what it waits on; a write the gate stopped needs
  you, and its row says `w widen <path>`.
- The keys talk to an agent: `t` tells it a line (a Claude Code session hears it with its next write or command; a
  task nobody is on yet reads it when it starts), `w` widens a task to what the gate stopped, `x` hands back a
  running task or reopens a finished one, `r` and `R` run, `D` shows the direction, `:` runs any command. Each is an
  ordinary `graphene` command; the key bar says what the keys do for the selected row, and the line above it what
  the last one did.
- `g` is the plan as a graph from your goal down: the goal, its sub-goals, the tasks under them, and arrows for
  what waits on what. `m` is the map of the folders each task may write; its lens (plan, live, changed) follows
  the plan's stage until you turn it with `v`, and its top line says what is true in each.
- `i` opens everything about a row in four panes, on 1 to 4 (contract, output, changes, record); `c` there shows
  the task's whole diff, as `graphene node diff` does.
- When something new needs you, the terminal rings and, where it shows one, a notification says why; `notify:
  off` in `graphene config edit` keeps it quiet.
- Colour means state: an agent's colour never borrows proven green, running amber, need-you purple or came-back
  red. Rows show whole titles where they fit; one word for one thing (task, check, proven, graph, map, widen, hand
  back, details), and `?` explains the marks.
- A running row shows the attempt going now and nothing from the last one; a widened task is asked of git again at
  once, so it is never flagged OUTSIDE for the file it was given; a look that fails leaves the screen as it was and
  says why. The cockpit reads a plan in a few milliseconds (2 ms on this repository's plan, 53 ms at 22,000 log
  rows), and a closed terminal ends it.
- `graphene demo` replays a richer run of the Nemotron path against its scripted stand-in: a goal with two
  sub-goals and four tasks, three agents at once, a hand-back that is widened and tried again under the same
  number, a task that waits on two. It opens on the plan, its news line narrates, and at 80 columns its top line
  still says no model ran. The README's GIF and stills are filmed from it (`docs/assets/watch.tape`).
- `graphene demo --live` replays a live run on Nemotron through Token Factory (9 October) as it ran, from the
  package, with no key: Nano's three tasks in a Sandbox, each with its bill.

Review every task before it lands (19 October).
- `review: every` in `graphene config edit` holds every task whose check passes for your sign-off, which lands it
  (Enter in the cockpit, or `graphene node signoff`). A run says so before it starts, and `plan accept` says
  what will wait.
- A sign-off is checked on its merge with what landed since the task was cut, as a run's landing is: a red check
  keeps it in review. Sign-offs take turns.

After a review of the whole branch at its seams (19 October), each line a fault a reader found and a skeptic
confirmed:
- A task that comes back while a run goes is taken again by that run once you answer it (widen, reopen, Enter on
  its row), and a second `graphene run`, or `R`, hands its tasks to the run going instead of being refused. One
  started with its own `--with`, `--attempts` or `--max-usd` is still refused.
- A task of yours that nobody started is done by your word, once the check it has passes.
- Three moves ask first: `x` on a running task (its agent stops), `r` on a task that came back (it reopens the
  finished task it names), and Enter on the last proposal when accepting it takes the open questions' defaults;
  Enter then accepts the task its line named, never one proposed while the line was up.
- A question opens to its whole words and every option, by the number that picks it; a proposal shows its check;
  a task that came back names the files `w` and `b` would give it; `t` on a question answers it, and words typed
  where nobody can hear them are said to go nowhere.
- Under `review: every`, a task waiting for you shows the sign-off still to come and reads ✓2/2 once given; the map
  counts it as changed, and what waits on it says it waits on your sign-off.
- A plan's agents are numbered from 1 again after the last plan is put away; the graph carries each box's number
  and mark in every state, and its head never cuts the state for a long title.
- New proposals ring once for the batch when no question comes with them; a write stopped again rings again.
- The replay says on every screen that it is one, lists only the keys that work in it, ends on its last state
  with the next step, writes nothing where it was started, and shows each answer before the edits it made.
- A refused command says why first, and an ask that ends says what the planner proposed.

After three more reviews (four fresh readers: a hackathon judge, a stranger's first hour, a copy editor, a release
engineer; then a regressions hunt, the README as GitHub shows it, and both replays walked key by key; then the
reference against the code and first commands in odd places), each fault confirmed by a skeptic (19 October):
- A task that comes back wanting a file of a finished task it waits on is offered it (`w`, `b`), beside `r`, which
  reopens that task; `w` with nothing to widen says why, never that nothing was stopped.
- A finished task whose check passed before any work says so on its row ("check passed before the work"), as its
  details did; it still counts as proven, since its check did pass.
- A row quotes its agent's last words, never what Graphene's own commands printed into its log.
- The map names a small project's folders; one-file folders fold into "other" only when they outnumber the rows.
- The Nemotron extra installs on a machine whose Python is older than 3.12: its install lines pass `--python 3.12`,
  as uv fetches a Python for the package but not for the package with an extra.
- The README's loop diagram fits its labels between its boxes in a browser, and its mark has a size: it filled
  the first screen.
- A stopped write is said once on its row, as stopped, never as an edit first.
- The record pane flags a check that runs a file its task changed, as `graphene node show` does; a done refused
  because nothing in its scope changed says so, in the record and in a replay.
- What the Nemotron executor or Graphene's own commands print into a log is never shown as what an agent says, and
  a multi-line command shows what it runs.
- `w` on a task that came back says whose file it wanted when it cannot take it.
- The map counts a new file being written in the row where it is made; a paused replay keeps its position at 80
  columns, and its last news stays up between changes.
- A check that runs the directory its own scope will fill (`scope: tests/pdf/**`, `check: pytest tests/pdf`, the
  shape the hook teaches) is no longer warned of as a misspelling.
- `graphene run` in a repository with no commit says to commit once first, as init does; `node show` names no
  Claude Code records for a run's sessions; an id an undo or a drop freed says it stays taken; `plan record` says
  came back; an act refused to an agent's shell leads with where to run it; narrow screens clip, never wrap.

The release.
- On macOS, `graphene run` on a terminal that is not its own session's (an agent's pty) no longer stops itself
  half a second in: a check's bash took that terminal and revoked it as it exited. A check gets no terminal. This
  was main's red CI after the new watch merged.
- Two races a loaded runner loses are gone (a leaf told to land second, and a cockpit tick after it closes), and
  help text no longer fails on GitHub's runners, which force colour: that is what failed 0.5.1's release run.
- `graphene demo --once` lines a long task id up with the rest, and a recording keeps `review: every`.

## 0.5.1 (tagged 16 October 2026, never published)

The v0.5.1 tag's release run failed its tests (help text on GitHub's runners, which force colour), so nothing
was uploaded, and PyPI went from 0.5.0 to 0.6.0. What follows is in 0.6.0.

Everything since the v0.5.0 tag. The wheel on PyPI as 0.5.0 was uploaded on 13 October from that tag, which is
the commit of 7 October (`a96fb48`), so it holds none of what follows: the timeline view, `r` to reopen the
owner, red first in the core, `init` saying what it did and `init --remove`, `node diff`, the $2 cap on an
attempt, and the feel pass's words. Install from this version to have them.

The controller night (14 and 15 October). What an agent may not do, shown; what a person can see and stop. Thirteen
read-only readers and a README tournament set the order (`dev/process/controller/`); seven lanes were built in
clones and landed under leaf holds; three seam readers then reproduced what the lanes had left loose, and it is
fixed. Each line is one commit.
- A leaf marked for sign-off waits on its own branch, and `y` or `graphene node signoff` merges it. It used to land
  first and ask afterwards. Run `graphene run` on a plan with `--signoff`.
- A leaf that changes a file its own check runs is flagged, in `graphene node done`, in the run and in
  `graphene node show`: a check the leaf can edit can be made to agree. It is a flag, not a refusal.
- `graphene node show` on a leaf a run landed says how to take it back: `git revert -m 1 <sha>`.
- In `graphene watch`, `c` shows the leaf's whole diff, coloured, with a top line that says whether it is in your
  checkout yet; `c` is on the review key line, and `:stop` is named in the help.
- `graphene demo --cheat`: a script plays an agent that tries seven ways round the locks against the real hook,
  git and check; six are refused, one is flagged, none gets through. A script, not a model, and it says so.
- `graphene run --stop` stops the run this repository has going from any terminal; a run says its worst case (leaves,
  attempts, the cap) before it starts, or that the executor has no cap; `graphene plan pause` says it does not stop
  a run that is going.
- Bare `graphene` with nothing planned puts `graphene init` first and exits 0; a finished plan says every leaf is done.
- The sign-off wait's loose ends: signing off on a detached HEAD or from inside the leaf's own worktree is refused;
  `y` during a run no longer leaves the parent sub-goal open; node show and the pane say the right thing when the
  worktree is gone or the leaf was merged by hand; `graphene run` says a leaf changed its own check's file.
- A stray file that blocks `node start` is refused with what an agent can do about it: the person removes it, or
  `graphene plan ack`.
- The replay's recorded run summary says `2 of 2 at once` and `you: 6 moves`, and its GIF is shot again from a tape
  anyone can run (`vhs docs/assets/watch.tape`).
- CI: the suite runs in parallel (`pytest -n auto`, an autouse fixture clears COLUMNS and LINES), a push builds main,
  a release tag runs the suite once, inside the release, a pull request cancels its own earlier run; a hanging-keychain test no longer fails at three
  workers on macOS; the bench's 63 tests are collected.
- The package says in plain words what it is, its keywords lead with `claude-code`, and `graphene-map` is a command
  beside `graphene`, so `uvx graphene-map demo` works from 0.5.1 on.
- A bench (`dev/held/`): a decision rule written before any number, four tasks that tempt, scripted agents that
  prove the scorers at $0. No live run has been made.
- The README, SECURITY, CONTRIBUTING, a bug form and the first-hour form are for people who are not all engineers;
  `docs/COMPARE.md` compares Graphene with eleven others, its gaps in the same table.

What the controller night learned from jcode (15 October). Four readers took apart an agent harness with twenty
thousand stars; three changes followed, and `dev/ui/IDEAS.md` says what it taught. Each line is one commit.
- A leaf whose branch moved while it was built is checked on the merge before it lands: its check and the checks of
  what this run landed since run on the merge, in a copy, and one that fails leaves the leaf in review with its
  branch named. Two leaves green on their own base and red together used to land as two "done"s. A check that was
  already red on the branch is said, and not held against the leaf; if the checkout moves while a merge is
  checked, it is checked again. A leaf you sign off by hand, or one that ran in a sandbox, lands without it.
- `graphene run --max-usd N` starts no attempt past N dollars: each is held at its worst case and settled at what it
  spent, a start that does not fit waits for what is going, and one going is not stopped. A Codex attempt with no
  list price counts at its worst case.
- A release waits for the whole suite on the tagged commit, then runs the published version in a throwaway home
  with `graphene demo --cheat`; CI lists what it skipped.
- `graphene node show` says what a Claude Code attempt wrote to the cache and read from it, as the stream gave it.

The live loop (16 October). Alex said the run was going backwards: it had hardened guarantees while the gap he set
out to fix, between what a person means and what agents do, stayed open. The direction now is a person and their
agents talking through one screen, with almost no text. Each line is one commit.
- `dev/ui/playground/`: a standalone Textual app, not wired into `graphene`, with a cockpit (numbers on each row,
  a live tail, the verbs), a territory map (which folders each task may write: before, live and after) and a flow
  graph (a layered layout in box-drawing characters). `uv run python dev/ui/playground/app.py`.
- `dev/ui/IDEAS.md`: a three-minute read of the problem, what jcode gets right, the three screens, the graph
  idea, and five decisions made while Alex slept, each one line to flip.
- What the person says while an agent works reaches it: a note (`graphene board note --about LEAF`) or an answer
  on the board, about the leaf a Claude Code session holds, is told with the session's next write or shell command,
  once, and logged as `told` on the leaf. In real `claude -p` runs (Haiku, half a cent each) a note told with a
  write was followed on the next step in 12 runs of 14; one told as a command ended, in 1 of 12.

Watch as the home, and one word for one thing (13 October). Alex asked for an honest direction after the feel
pass and for a README a stranger can take in; this is the part that touches the product. Each line is one commit.
- In `graphene watch`, `:ask` with nothing after it opens your editor for the paragraph; the empty plan's sentence
  and its key say so.
- Opened after a run, watch's first bottom line is what the run said; a leaf that came back puts its offers before
  the reason where the pane is short, every command whole; Enter on the goal says the plan's record in the pane's
  words; a folded row counts the rest as `others`; the x key says `hand it back`; a fork row reads `fork 1 of greet`.
- One spelling for a span on every surface (`12s`, `6m12s`, `<1m`, `42s ago`); a person's act is a move (`you 2
  moves 1m`, `you: 4 moves, 2m`); `width 2 of 3` reads `2 of 3 at once`, in the closing line, the time view's note
  and the record.
- The plan's record and a sub-goal's open with one row a leaf (`✓ fields · normalize/fields.py · landed 3ba9990 ·
  $0.01`); `in short` is one sentence in the person's words; the coverage sentence is left out when nothing was
  traced; an attempt's last words are said once; the leaves' bill is named as the planner's is.
- The ask's proposed rows indent by depth; a proposed row under a proposed parent drops its own accept command;
  `plan accept` on an empty plan says one line; bare `graphene` names the ask command first.
- A recording hides paths under the machine's temp directory as it hides the home, and `demo.leaks` counts them.
- The brand assets live at `docs/brand/`, tracked, with a README naming each.

The feel pass (11 October). What the first hour reads, said in the person's words: three readers walked the first
hour and the morning after, a designer chose twelve things, a judge argued each, and four lanes built them; the
evidence is `dev/process/feel/`. Four decisions move with it (43, 179, 186's gloss, 44's letter on an empty plan):
Alex's to flip.
- The `(the plan of /full/path)` trailer prints only from outside the plan's own checkout (a linked worktree, where
  an executor's `node done` runs); standing in the repository it is quiet. Run `graphene node add` from the
  checkout, then from a worktree.
- `graphene ask` ends `next: `graphene plan accept`, or prune in `graphene watch` (y accepts, d drops)`, and
  `graphene plan accept` ends `next: `graphene run` reaches fields, readme` with a line for each leaf that will wait
  and why, or `next: nothing is ready for `graphene run``; `graphene plan` on a proposal says `graphene plan accept`
  takes all of it. Run `graphene ask` and `graphene plan accept`.
- `graphene watch`'s status line says its clock in one phrase (`agents 1 <1m`), so `1/9 done` is back at 80 columns;
  dollars with no agent run read `bill $0.03`; while the planner works the agents' slot reads `planner asked 12 s
  ago` until its proposal lands. Run `graphene ask` with `graphene watch` beside it.
- `graphene init`'s first screen: `plan first: on. Claude proposes a plan here before it writes; you accept it in
  `graphene watch``, `(8 Claude Code hooks)` for the eight names, and a `next:` that fits what line one said
  (install, or `graphene init --planner claude --executor claude`). Run `graphene init`.
- `graphene demo`'s top line says `a scripted stand-in, no model ran`; its bottom line and every printed log row say
  a kind with spaces (`rolled up`, `check passed`). The shipped recording was made again on 12 October (UTC) from
  the stand-in with the meter on, so a running leaf's row shows. Run `graphene demo`.
- `graphene ask` with Claude Code says each of the planner's tool calls as it happens, one indented line (`  reading
  api.py`), 40 a try and then a count. Run `graphene ask` with Claude Code.
- In `graphene watch` every key line ends `? help · q quit` (a proposed leaf keeps `Tab view`, a leaf that came back
  `r run it again`), and the empty plan opens on `plan first: on` over `:ask what you want · ? help · q quit`. Run
  `graphene watch` in a repository with no plan.
- While a metered leaf works (Claude Code, Codex, Nemotron), `graphene run` says every 30 s what it is doing, in the
  strip's words (`fields · 30 s · 4 turns · $0.08 · editing normalize/fields.py`); a script executor still says
  nothing between started and ended. Run `graphene run`.
- Red first names the check: `fields, readme: their check (`true`) passes before any work: it would pass with
  nothing done; `graphene node set <id> --check '<a real one>'`, or e in `graphene watch``, then `red first: 2
  checks ran at cc9b19a before any work, in 1 s`; the pane under a flagged leaf says the same, and `graphene plan
  precheck` names it too. Run `graphene run` on a plan whose checks are `true`.
- `graphene node show` for a person has no `finish:` and `stuck:` orders and `landed:` under the contract; a
  sub-goal's blank slots are gone; the finished plan's last line says `in your checkout, uncommitted (`git status`):
  commit it yourself`. Run `graphene node show <id>` on a landed leaf.
- The help's legend names every glyph once (`◆ review`, `↩ came back`); the time view has a key of its own under
  `?`, with `═` for a hold the meter cannot see and `■` for a landing, so `━` means only the critical path and `◆`
  only review; a fork that lost, gave up or stopped is `–` or `⊘`, no leaf's glyph. Tab to the time view, then `?`.

The first hour and the morning after (10 October). What a stranger meets in the first hour said plainly, and what a
person reads the morning after printed from what was already stored; the night's experiments measured on 907a7d0
and on the branch (`dev/process/prove/after.md`).
- `graphene init` says what it did: the hooks it installed, that the next Claude Code session is recorded (prompts,
  tool calls and what they returned, the files it edits; on this machine only), that accepting happens in `graphene
  watch` in another terminal, and the two ways out. At a terminal it asks the plan-first mode, one line per mode,
  and keeps `on` when it cannot ask. A repository with no commit is told to commit once first. Run `graphene init`.
- `graphene init --remove` takes out exactly the hooks init added and leaves every other setting; only a person may.
- A person-only act on the plan or the settings (accepting, editing, signing off, plan first, init) refused inside
  Claude Code says "if you are the person, run it in a terminal outside Claude Code"; answering the board, `ask` and
  `talk` still say only that they are the person's. A held leaf blocks a session's stop once, then lets it stop;
  `graphene run`'s executors are held as before.
- A store another process is writing never turns the hook's deny into an allow: every write on the way to a refusal
  is guarded, the aside leaf a prompt makes included.
- An agent is told to put back only what it made; what may be the person's unsaved work is asked about instead.
- In `graphene watch`, `?` is help on every row, `t` talks to the planner, a run that could start more than one leaf
  asks first (`R`, and `r` on the goal or a sub-goal), a leaf that came back offers `e edit its check`, and ∅ is in
  the legend. The replay ends with the next command; the README calls it a scripted replay.
- The default Claude Code executor carries `--max-budget-usd 2` (an attempt) and `--strict-mcp-config`, and is told
  that its shell runs only `graphene node` and `graphene plan`. A stop at the budget is said on its attempt's line;
  a leaf that came back ends with "`graphene node show ID` says why".
- `graphene run` says first where it lands, with what, how wide and under what cap, then that `graphene watch` in
  another terminal follows it (each leaf lands as its own merge; your commit hooks are skipped); `run --help` names
  the git flags. A dirty checkout is warned that its changes are not in the executors' worktrees. Its last line is
  kept as a row: `graphene plan log` lists it, the goal's pane shows the last, and Enter on the goal is the plan's
  record. `you` counts the acts since the plan's last run.
- Red first asks the environment before it judges: a check whose runner the PATH lacks (`No module named pytest`) is
  said as such, never as a red; leaves whose shared check passes get one line that names the check and says it would
  pass with nothing done; a reopened leaf whose check passed when it landed is said so, not flagged; a python3 with
  this repository installed editable is named, because a check that imports it tests the checkout, not the leaf's
  worktree; only the leaves this run can start are judged. All warnings: nothing holds a leaf.
- `done`'s clean tree reads every file's content: it is cut from a copy of the index, which git had trusted for an
  edit of the same size made in the second the file was checked out, so a leaf could land with a check that passed
  on the committed file.
- Python's bytecode is never offered by `w`/`b`, counted or committed. A person's act prints after it is committed,
  so a closed pipe cannot roll it back. `--attempts` has a minimum of 1; `--precheck`'s help reads the right way.
- The record names the commands the executor itself was refused, apart from the writes the hooks refused; keeps what
  an attempt said last, whole; says the check's last line, whether it also passed at the base, and the commit that
  landed the leaf. `graphene node diff ID` prints what a leaf changed (its landed merge, its branch in review, or
  what it finished in your checkout); `c` in `graphene watch` shows it. ∅ stays on a done leaf whose check also
  passed at the base. The merge's message carries the check and its result, the executor, its attempts and dollars,
  and the note a reopened leaf was sent back with, and a second landing says `(id, reopened)`.
- `graphene ask` with Claude Code or Nemotron says, after what it proposed, one line: the planner, its calls and its
  dollars at list price (Codex and a command of your own say none). A proposal refused on the last try is kept, and
  the ask prints the commands that add it once mended. `graphene plan propose -` reports every
  fault at once. A board item written as a node is told how the board is written. The planner and every session
  are told that a check runs in a fresh worktree with nothing git ignores.
- `docs/HOW_IT_WORKS.md` says what init does and how to undo it, the run's first line and red first's warnings, and
  what the record and the merge message now say; its word cap is 3,300.

The loop (9 October). A leaf that finds a landed leaf's fault reopens it with one key, and every check runs red first.
- A leaf that came back wanting a file a done leaf owns offers `r`: reopen that leaf with the reason, and wait on it.
  `R` then runs the owner again on top of what landed, its executor told the note first. Press `r` in `graphene watch`.
  `u` takes `r` back as it does `w` and `b`: the owner is done again, and the withdrawn note reaches no executor.
- Before `graphene run` starts anything, every accepted leaf's check runs once at the commit its leaves start from:
  one that passes there proves nothing, one that fails on a file outside the leaf's scope names it, one that does
  not end is said once and not waited on again. `--no-precheck` skips it.
- A planner that answers in text (Claude Code, Codex) is told every fault of its proposal at once, as the Nemotron
  planner is, instead of one a send-back. Run `graphene ask '…'`.
- `graphene node show` says when a check ran a file a later leaf rewrites, with the file and the base commit.
- An executor whose check fails on a file another leaf landed releases with `--wants` naming it and the fault.
- The time view draws every id whole. Its label column fits the longest id. Run `graphene plan --view time`.
- A board answer that changes a check or a scope is judged as `node set` is. The check waits on the leaf
  that writes its file, and a second writer of a path is refused. Run `graphene board take`.
- A need Graphene adds to a leaf is logged as Graphene's edit, not yours. `graphene plan changes` lists it, and
  `graphene watch` marks the leaf ~. A leaf that came back still waits on you. Run `graphene node set`.
- The Nemotron planner repairs what needs no judgement and says each repair in a `repaired:` line. It sends the
  other faults back together, one per node, at most twice. Run `graphene ask --with nemotron '…'`.
- `graphene run`'s last line says how wide the run went: `width 2 of 3` is three leaves, at most two at once. So do
  `plan record`, `node show` on a sub-goal, and the time view when its line has room. Run `graphene run --parallel 3`.

The timeline (8 October). A fourth view, and fixes for what the meter night's runs stopped on.
- A fourth view, `time`: a lane for each leaf that was held, what its executor did when, and marks for a refused
  write, the check, a hand-back and a landing. Tab in `graphene watch`, or run `graphene plan --view time`.
- A check that runs a file another leaf writes waits on that leaf, whichever came first, and the plan says so in one
  line. Two leaves that write one path are refused, by their lines. Run `graphene plan propose`, `plan accept`,
  `plan edit` or `node set`.
- A check that runs a file only a later leaf makes is refused: it could never pass. Run `graphene plan propose`.
- The Nemotron planner answers in a strict JSON schema (prompt version 5). A refused answer goes back once, with
  Graphene's words; the second answer is the answer. Run `graphene ask --with nemotron '…'`.
- `graphene init` sets plan first `on` in a new repo. A repo already on `auto` stays `auto` until you change it
  with `graphene plan first on` or `P`. Run `graphene plan first`.
- One leaf proposed is one row in `graphene watch`. `y` accepts it, and runs it when an executor is chosen.
- The Claude Code planner writes its stream: the plan logs its bill, and the night's ledger settles it at what it
  spent instead of its worst case. Run `graphene plan record`.
- In `graphene demo`, j and k move in a view again. Press Tab, then j.

## 0.5.0 (13 October 2026)

Uploaded to PyPI on 13 October from the tag of 7 October (`a96fb48`): the meter and what came before it.

The meter (7 October). What the agents do and spend, on the screen while they work.
- `graphene run` reads each executor's own stream as it runs: Claude Code's `stream-json`, Codex's `--json`,
  Nemotron's own rows. Any other command says "no meter". Run `graphene run` and watch.
- `graphene watch` shows a row for each running leaf (model, time, turns, last act, files, tokens, dollars)
  and two clocks on the status line: the agents', and yours, counted by your keys.
- `graphene run` ends with one line for every executor: `run: 3 done · agents 2 min, $0.4560 at list
  price · you 0 acts, 0 min`.
- `graphene node show <id>` gives each attempt its record: what it read, edited and ran, what was refused,
  what it said last, and its tail.
- The tree and the DAG note each leaf's bill and minutes: `$0.13 · <1m`. Run `graphene plan --view tree`.
- Under `plan first auto`, every ask is proposed. One leaf with no board item and at most 8 paths is yours
  at once; anything else waits. Run `graphene plan first`.
- `docs/` keeps what you need to use Graphene; `dev/` holds how it gets built. Read `dev/README.md`.
- The README is one short argument. `docs/HOW_IT_WORKS.md` is the reference, under 3,000 words.
- The Nemotron planner reads a tool call Ultra writes as text (`<tool_call>`), instead of taking it for its
  answer.
- The `statements` task is twice its size: `dev/test/tasks/statements/SIZE.md` says why and what it voids.

Graphene on Nemotron. As practice on 2 October, Nemotron planned a small feature 5 times. 2 plans ran to the
end in Token Factory Sandboxes, landing 5 of 6 leaves, each passed by its own check; neither did all it was
asked. 3 stopped at the planner, whose tree was readable on 2 of 9 asks (`dev/test/first-light.md`). Nothing
registered has run live.

The cut (5 October). Smaller, with a safe default.
- `graphene run` isolates every leaf in its own worktree and merges what passes. `--here` is the old way.
- A Claude Code executor can write in its run's worktree. The hook had refused every write there.
- `plan first` has a third value, `auto`, the default: one leaf is done at once, more is proposed.
  `on` makes every ask wait for you, and an old `on` reads as `auto`. Run `graphene plan first`.
- `graphene --help` shows nine commands. The rest still work; HOW_IT_WORKS lists them under "The rest".
- Every command's help is one or two short lines. Run `graphene node --help` to see it.
- The web UI is gone. `git revert` of the deletion commit brings it back.
- `node show` fills the commits it credits. Only the web UI did that before.
- Nemotron is an optional extra: `uv tool install 'graphene-map[nemotron] @ git+…'`. Without it, no Token
  Factory code loads.
- The old briefs, notes and spikes left `main` for the orphan branch `process`.
  `git show origin/process:README.md` says what is there.
- A task a paragraph should lose, for Alex to run: `statements`, five traps, `dev/test/PROVE.md`.
  Its rehearsal calls no model: `uv run python dev/test/prove.py rehearse /tmp/rehearsal`.

The live half of first light (2 October, practice).
- The sandbox's list of files takes the exit code through `$(...)`, and a command's output is appended, never
  truncated. On ConTree a `cat` into a file opened with `>` leaves it unwritable: no command's list came back,
  every sandbox command read as exit 1, and a command's output was cut at its first `cat`. A leaf's placement
  record counts the commands whose list was lost, and the ladder's rungs 3 and 7 fail on any.
- `graphene plan note` takes JSON's null written as the string `"null"` in a glob list as no glob, as Nano
  wrote it live.
- contree-sdk's "Token expires in 0 hours" no longer reaches the screen (it is a 300-second token, not the
  key).
- Live recordings in `tests/recordings/`: rung 5's leaf and rung 7's first take, replayed in CI with no key.
- Tests that count Token Factory's retry waits patch only its own wait, not the global `time.sleep` (CI's
  flake in test_precheck and test_cover).
- `graphene key check` says Sandboxes' state; a spend cap that is not a number refuses every call; the
  registered runs' $10 cap (carried from 29 September).

First light (29 September).
- `graphene direction`: a small tree of goals above the plans, one line a node, in `.graphene/direction.txt`,
  which git tracks while the rest of `.graphene/` stays ignored. An agent proposes nodes (`direction propose
  -`); only the person accepts or drops them, hangs the plan from one (`direction plan NODE`), attaches a
  session to one (`direction attach SESSION NODE`) or edits the file (`direction edit`). `D` in `graphene
  watch` shows the direction under the tree, read again every tick, and opens no command line. `graphene direction` prints each node with what waits on you, what runs and what is next, read from
  the rows the hooks already write; `graphene plan`, its views and `graphene watch` show the path
  to the plan's node above the plan. A file with a line Graphene cannot read is not used, and the refusal
  names the lines.
- The hook refuses an agent's Edit, Write, MultiEdit and NotebookEdit under `.graphene/`, plan or no plan.
- The board shows only while a question on it is open: `board: auto` (unset) in `graphene config`, by study 4
  (`dev/test/results-2026-09-29-board.md`); `board: on` shows every open item. Accepting the whole plan, an
  `R` that starts something, or `graphene board take` with no id takes every open default and an agent's
  note, in one line that `graphene plan undo` takes back; a default that drops a node waits for its own key,
  and the line names it. `graphene board` prints what answering needs, and `--all` the rest.
- `graphene board lookup` (one Nano call; `GRAPHENE_SHAPE=lookup` runs it after each ask) settles a question
  a file already answers when the line it quotes is in that file, marked `from the repo: FILE:LINE`; `unpark`
  gives it back. It never sends a protected file.
- Spending is the person's. Without `GRAPHENE_AGENT_LIVE_USD`, a process that carries an agent's mark is
  refused a Token Factory call to the real host and any ConTree sandbox before anything is sent. With it,
  every live call goes on one night's ledger that every process shares, locked with `flock`
  (`~/.graphene/night/`): a call reserves its worst case first and is refused unsent past the cap, the lower
  of that figure and $10, and nothing new starts past 80% of it. Its rows say `practice`, and
  `dev/test/evidence.py` refuses them.
- Sandboxes: a project ConTree refuses (403) is one refusal saying what the key lacks and where access is
  asked for, wherever a sandbox is used. `graphene init` asks ConTree's whoami before it places Nemotron's
  leaves in Sandboxes, and places them on this machine with one line saying why when it is refused. An
  operation past its time comes back as the command's exit 124, as Docker's does. The live model list's
  mixed-case Nemotron ids resolve to their roles.
- A recording dropped into `tests/recordings/` replays in CI and is counted for the key, the project, a home
  path and key-shaped words.
- A closed terminal ends `graphene watch`, `graphene demo`, and a run with its executors and their checks,
  whether or not it sends the hangup.
- `graphene demo` holds each change on the screen, pauses on space, steps on `.`, plays again on `r`, and
  names a stand-in on every row it made. The shipped recording was made again on the scripted fake with a
  board: a question, an assumption and a leave-out, each taken with one key. Its status line keeps one form
  and its bill, and offers neither `R` nor `P`.
- The hook imports, queries and starts only what its event needs: recording a call takes about half the
  CPU it did (69 to 32 ms on the author's machine with other work running). Its 60 ms budget is held on CPU time, so a loaded machine no
  longer fails it.
- `graphene key set`, `check` and `remove` refuse Claude Code and Codex. No test reaches the real keychain
  (`tests/keyguard.py`, here and in CI).
- `dev/test/practice.sh night` prints the night's bill, and `practice.sh prototypes` practises cover, note
  and precheck under a $0.05 cap. `dev/demo/build.sh` films the demo run scene by scene and assembles
  `rough.mp4` only from a run recorded as live.
- With no planner or executor chosen, `graphene ask`, `node split`, `talk` and `run` refuse in one line and
  start nothing until `graphene init` or `--with` names one; they no longer start `claude` from the PATH.
- A leaf that came back waits on the person: `R` and a plain `graphene run` leave it and say that
  `graphene run --node ID` (`r` on the screen) runs it again. A leaf a run let go is ready again.
- A came-back leaf is never offered a path another live leaf's scope has; it is offered to wait on that
  leaf instead, and the pane says which paths were not offered and why.
- Asking again finer or coarser (`+`, `-`) carries a board answer to the leaf the planner wrote again, and
  says, with the command, any answer it cannot place.
- `graphene plan undo` of a board answer logs `undone`. `graphene config` names a board answer's read-only
  globs `# answered: readonly …`, not a second `board:` key, and `graphene board` wraps to the terminal.
- Bare `graphene` names a proposal and an open board as what waits on the person, and `graphene run` on a tree
  nobody accepted says to accept it.
- No test gets the repository git was pointed at: a suite started from `git bisect run`, a hook or `rebase
  --exec` hands no `GIT_DIR` or its kin to its tests.
- `dev/test/bench.py` counts a leaf its round's timeout stopped as failed and runs it no more, now that a
  leaf a run stopped reads ready.
- Smaller: `:ask` keeps a paragraph's apostrophes; a planner or executor run by an interpreter is named by
  its script; a leaf's record reads its check before its finish.

Shaping (28 September): the board (`graphene board`: the planner's questions and risks, answered only by
the person, with `then:` lines that change the tree), the outline, tree and graph views (`Tab`, `--view`),
talking on a node (`?`: `graphene talk`), what changed since you looked (`graphene plan changes`, `seen`),
the settings you state once (`graphene config edit`: `protected`, `readonly`, `never`, `size`), the key in
the system keychain (`graphene key`), the practice ladder (`dev/test/practice.sh`), and three Nano
prototypes (`graphene plan cover`, `note`, `precheck`), each run only against the stand-ins.

- `graphene demo` replays a recorded run in `graphene watch`, with no key, no Docker and no network, and
  runs nothing: every key that would change the plan or start a process says so. `graphene demo --once`
  prints its last frame. `graphene demo --record FILE` records a run's store (not the model's calls),
  taking out paths, keys and sandbox ids. The wheel ships a recording, and it says on screen that it is a
  scripted stand-in until the live run replaces it. Needs git.
- `graphene init` lists what it finds here (`claude` or `codex` on the PATH, a Token Factory key), each
  with what it needs, and none comes first: Enter takes a choice only when exactly one is found. Without a
  terminal, an unset choice gets the one thing found, or stays unset and says why.
- Forks and the model ladder are visible. Each fork is a row under its leaf in `graphene watch` (its
  model, which fork, its state), a step up to a larger model is named on the bottom line and in the leaf's
  pane, the pane shows the leaf's sandbox (its checkpoint, operations and seconds) and its bill, the record
  says which fork won and why each other one did not.
- The Nemotron path survives what the judging period can throw at it: a model id the live list no longer
  has falls back within the Nemotron family and says which instead of which; a 429 storm, 5xx errors, a
  timeout, a reply cut off, a malformed or text-only tool call, a sandbox killed or gone mid-leaf and a
  check that hangs each bring the leaf back with its cause and what to do, the run goes on, and nothing is
  left running; no more than fifty sandbox operations run at once from one machine.
- The first fork whose check passes is the one that lands, decided under a lock.
- Forks read what git shows in the leaf's checkout (they were blind: a fork's copy has no `.git`), and a
  winning fork never deletes or copies what git ignores (it used to delete a `.env` under a `**` scope).
  A stopped run stops its forks and the model's commands, writes each fork's row as stopped, and bills
  what they spent. A usage row says whether Token Factory or a stand-in answered, and the bill credits
  Token Factory only when every row says so.
- A record read where git has not got a hold's starting commit says its commits cannot be read.
- The README says what Graphene on Nemotron claims, directly under the opening, offers two paths (the agent
  you have, or Nemotron through Token Factory), and gives judges ten lines to test it.

- The import package is `graphene_map`, matching the distribution (it was `graphene_debrief`). The command is still `graphene`, and installed hooks keep working. Anything that imported `graphene_debrief` imports `graphene_map`.
- NVIDIA Nemotron on Nebius Token Factory, as planner and executor: `graphene ask --with nemotron` (Ultra, read-only tools) and `graphene run --with nemotron` (Nano, then Super on a refused attempt; `--forks N`; `--placement local|sandbox`). Model ids come from the live model list, and every call's usage is priced at its list price. Needs `NEBIUS_API_KEY`.
- Token Factory Sandboxes: `pip install 'graphene-map[sandbox]'` (contree-sdk 0.3.6). A leaf's commands run as a user who can write only its scope, what a command makes outside it never comes back, and its check runs in a fork of the sandbox.
- `graphene init` asks once which planner and executor a repository uses (as above: what it finds, none first); `run`, `ask`, `node split` and the screen use it, and `--with` overrides one command.
- A check runs in a clean worktree of the leaf's state: nothing it writes lands in the executor's tree. No check gets the Token Factory key.
- `graphene watch` folds: done subtrees fold, a folded row counts its leaves by state, a tall tree opens as its outline; `za zo zc zR zM zx`.
- The bill: what the Nemotron planner and executors cost, at list price, in `graphene node show`, `graphene plan record`, the run's last line and the screen's status line.
- Python 3.14 in CI; the store binds values to plain `?` only.
- Graphene reads no Claude Code transcript; `graphene ingest --backfill` is removed (`graphene ingest hook` is unchanged). Internal: `graphene_map.attribute` is `graphene_map.shell`, `graphene_map.sources.claude_code` is `graphene_map.hooks`, `repo_root` lives in `graphene_map.store`. The screen harness is `dev/screens/`.
- Sandboxes: a clean commit's checkpoint is made once and every leaf at it forks it; `--forks` forks one sandbox; `--image` and `--prepare`; the file list is read back whole; what git ignores is nobody's change. An executor that cannot work hands its leaf back with the cause. The planner and executor read only what git shows. A reasoning model's cut-off reply, Nemotron's `<TOOLCALL>` text and common tool names are handled. A `--parallel` leaf's record holds its own commits, and a Nemotron leaf's is graded by the writes it recorded.
- `dev/test/`: `bench.py` and `results.py` (the benchmark), `score_tree.py` (a tree against its task), `access.py` (the access check), and the OpenCode placement spike.

Paragraph in, tree out, prune, run.
- A paragraph typed into a session (240 characters or more) is asked for a tree before any code: the agent proposes it in the plan's text and stops, and its writes wait until a leaf is accepted. A line is still done at once; "just do it" skips the tree, and a short "no plan" lifts a wait. A new session is taught the text whether or not a plan exists yet.
- The plan as text: `graphene plan --text`; `graphene plan edit [id]` and `graphene node edit <id>` open it in `$EDITOR` and apply what you changed, all or nothing, refusing a line it cannot read by its number; `graphene plan propose -` reads it from an agent (JSON still read) and refuses at once on a terminal with nothing piped; `graphene plan undo`.
- `graphene watch` is a full screen (Textual) with vim keys: the tree, the node under the cursor, the executors as they work (which, where, their last tool call, seconds since), `:` for any command, `?` for the keys. `--once` prints.
- `graphene ask "<what you want>"` and `graphene node split <id>`: a planner with read-only tools, whose printed proposal is added for you to prune.
- A leaf that comes back offers its fix: `graphene node widen <id>`, `graphene node sibling <id>`, or waiting on the nodes its reason names.
- `graphene run`: Ctrl-C (or a closed terminal) hands back what it started and stops the executors and their checks; releasing a running leaf stops its executor; a run that died is swept; a leaf whose need is not here yet waits; each attempt's output is kept as it streams; git is asked before the plan's write lock. The default executor may run `graphene` (its `done` and `release`).
- A check that names a path in neither the repo nor a scope that may still write it is warned about when it is written ("check the spelling"); checks run under bash; every write says which repository it went to.
- New dependency: Textual.

## 0.4.0 (unreleased)

The plan becomes a tree, the terminal its first surface, and ready leaves run at once.
- The root is a sentence of yours (`graphene plan goal`). A node with children is a sub-goal and needs only a title; a node without is a leaf with a scope and a check. `--parent` on `node add` and `node set`; nested `"children"` in `plan propose`. A 0.3 plan is a tree whose nodes all sit under the root.
- Done rolls up: a sub-goal is done when its children are and its own check, if it has one, passes where their work is together. `needs` are inherited downward; cycles through needs, the tree or both are refused.
- A proposal is a subtree: accepting a node accepts what is under it and what it sits under. A leaf too big to do is split by proposing children under it.
- Every executor is told the path from the goal to its leaf (`why:` lines in `node start`, `node show` and the prompt `graphene run` hands over).
- `graphene plan` prints the tree, what waits on you first, with finished work and sub-goals where nothing is moving folded (`--all` unfolds). `graphene watch` redraws it live. `graphene plan record` and `node show <sub-goal>` add up the records of the leaves.
- With a plan in force, a request typed into a session is a leaf by itself (the CLI's `--scope` / `--check` flags typed in the prompt bind it; otherwise it is a record of what the turn changed), and a short plain yes accepts what the session proposed. `graphene plan prompts strict` restores the 0.3 rule.
- `graphene run --parallel N`: a worktree and a branch a leaf, committed by Graphene and merged into your checkout when the merge is clean; otherwise the leaf waits for you in review, on its branch. Plain `graphene run` is unchanged and commits nothing.
- Whoever carries no agent's mark is the person, terminal or not; `graphene run` marks its executors, and the check Graphene runs is never the person.
- The store moves to schema 4 with no table change, so that 0.3 refuses it in words.

The session product becomes a node's record, and that record works for whoever did the work.
- `graphene node show <id>`'s coverage block is computed from the node's own log, from git and from the check Graphene ran, so a node done by Codex, by `graphene run --with <anything>` or by you at the terminal gets a real line instead of "not computed". The commits inside a node's windows are asked of git directly; the store only ever held those a recorded session's window covered. Claude Code's records, where they exist, still say which path traces to a write somebody recorded making; where they do not, the block says what it was read from and grades every path "to git alone".
- The check Graphene ran is printed in the coverage block, with its command, result and time: it is what verifies the change set.
- Removed: `graphene why` and `graphene why PATH:LINE`, the session card (plain `graphene` with no plan, `graphene debrief`, `graphene --session/--since/--json`) and `graphene sessions`, with the prompt→file→hunk reconstruction behind them. All of it could only answer for a Claude Code session, and none of it is what a node's record needs. The map (`graphene ui`) and its page are unchanged. In a repo with no plan, `graphene` now says how to start one; `graphene ui --session ID` still picks a session, and the page's rail lists them.

## 0.3.0 (unreleased)

Graphene becomes the plan a person and their coding agents share; the record now hangs off it.
- `graphene plan` and `graphene node`: nodes with a goal, a scope (globs), a check, what they wait on, an owner (any agent, or a person) and a state. Agents propose; only a person accepts, edits, signs off, reopens, overrules, pauses or archives.
- `graphene node done` is the gate: Graphene runs the check itself and asks git what changed since the node was started. A change outside the scope keeps the node open, however the file was written.
- With `graphene init`, the Claude Code hooks refuse a write outside the scope of the node a session holds (every permission mode, subagents too) and refuse a stop while a node is open. `init` adds one event, `PreToolUse`; run it again in a repo set up earlier.
- `graphene run`: one executor per ready node (`--with 'claude -p …'`, `'codex exec …'`), and Graphene decides what is done.
- `graphene` alone shows the plan when the repo has one; `graphene node show <id>` is a node's record: who held it, what changed, what was refused, how much is verified.
- `graphene ui` opens on the plan, and a person can edit it there.
- Removed: the guess at "not what you asked for" from prompt text. Scope is a fact of the node now.
- The store moves to schema 3 by an additive step; a 0.2 store is upgraded in place.

## 0.2.0 (2026-09-20)

The truthful record and the first map: agents as records (task, parent, worktree, closing message), commits credited by record, the coverage line as three counts, `graphene ui` and `--export`. `--explain`, `--model`, `--full`, `--md` and `--html` were removed; the package became `graphene-map`.

## 0.1.0 (unreleased)

Graphene reads the transcripts Claude Code keeps on your machine and answers which prompt changed a file or a line: `graphene`, `graphene why PATH[:LINE]`, `graphene init`.
