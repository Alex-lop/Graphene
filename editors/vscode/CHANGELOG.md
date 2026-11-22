# Changelog

## Unreleased, after 0.9.0

The whole plan in the pane, cards that say what is true of a step and where you are needed, and a tab of the
graph's own (22 November 2026).

The whole plan in the pane:

- The graph opens with the whole plan in view, whatever its size: fitted to the pane, never drawn larger than
  its own size. It is fitted again when the window is resized, when the plan grows or shrinks, and every time
  the page opens, until you pan or zoom. `f`, the ⤢ button and a double click on the canvas fit it again.
- Choosing a card does not move the plan. Its pane opens beside the canvas and the zoom, the cards and the card
  under the pointer stay as they were; the plan pans only when that card would be out of view, and just enough
  to show it. Closing the pane moves nothing either. (A task opened from the Plan view, or a page that opens on
  one, is fitted beside its pane.)
- Zoom goes out to 20% and in to 300%: the − and + buttons, `-` and `=`, ⌘ or Ctrl with the wheel, a pinch. The
  percent between the buttons says how big a card is drawn; a click on it, or `0`, is 100%. The buttons are there
  wherever the graph is drawn across, a narrow tab (561 to 700 px) too.
- From afar a card is a row: its state's mark and its title, filled by its state (landed green, working amber,
  to review purple, came back red; not started is an outline). Its right end holds only news: its check proves
  nothing yet, or its attempts as small marks. A plan too big to read as whole cards opens that way; zooming in
  turns the rows back into whole cards, and a double click on a row, the goal's too, opens it at 100%. A task
  drawn from afar opens there too, and the whole plan is back once you leave it.
- From far (rows under 45%) the titles go and the fills grow stronger, and what wants you keeps its size: the
  diamond and the triangle are 16 px on screen however small the plan is drawn.
- While no step leaves your machine the region for what leaves it is not drawn: the plan has its width (a
  seven-task plan opens at 85% where it opened at 77%), and "THIS MACHINE" ends with `nothing leaves it`.
  The region is back, as it was, with the first step that pushes or opens a pull request.
- A minimap in the canvas's corner while part of the plan is off screen: a click or a drag in it goes there. Its
  rects take the rows' colours.
- The `+` key draws a task and no longer types a + into its title. The narrow graph (under 560 px) and the lanes
  are as they were.

The cards:

- A card's foot is its check's: a box only Graphene ticks, the words `done when`, and the check with its end
  kept (`uv run…test_cache.py`). The box is ticked where the check passed after the work and that verdict still
  stands, crossed where it failed, dashed and amber where it proves nothing yet, whole and empty where it fails
  now as it should, dotted where it has not run; a step with no check wears the diamond of your approval. No
  check wears a ✓ it has not earned. The foot's hover says the verdict in words.
- The step that needs you wears its one act on its card: Approve, Help it…, Approve and run, Mark done, Allow
  the write…. It is the pane's own button: a click, or Tab and Enter, and it selects nothing. Never in a replay.
- One shape a state, on a card's corner and at a row's left: a ticked disc landed, a turning ring working, a
  filled diamond to review or asks you, a hollow diamond a step of your own, a triangle came back; on a row a
  dotted, a whole and a dashed ring are waiting, ready and suggested. Needs you and came back no longer differ
  by colour alone. To review and yours have a purple border, landed a soft green one and a quieter title.
- The files chip says the latest fact: the files a step may change; `✎ 2 of 4 files` while it works, and
  `1 refused` in red; `✕ wrote store/repo.py` when it came back for a write outside them.
- A task set to several attempts says `×3` at the end of its status line, in the lanes too, until they start.
  The waiting chips under every such card are gone, so a big plan is a good deal shorter; attempts that started
  keep their chips.

Around the cards:

- A sub-goal's header is a ring filled by how many of its tasks landed (the ticked disc when all have), its
  title, `3 of 6`, one small mark a task with the landed first, and in words what wants you there (`1 to
  review`, `1 came back`, `1 yours`), each in its mark's colour. It is larger over rows, so it reads in a fitted
  plan, and it is drawn over the lines that cross it.
- The goal's card wears the same ring and, at its foot, a cell a task grouped by sub-goal; under it,
  `goal · 5 of 26 landed`. As a row it is the ring, its title and `5 of 26`.
- The legend is the marks themselves with their words and how many steps wear each, the loudest first, only
  those the plan has: `◆ to review 1`, `▲ came back 1`, and so on. It replaces the five colour dots, and gives
  way where it has no room beside the zoom's buttons.
- A chip at the canvas's top right says how many steps need you: `3 steps need you · show the next`. A click,
  or `n`, selects the next one in the plan's order and brings it on screen, round again after the last. It
  counts the steps to act on (to review, came back, yours, asks you), not the suggested ones: accepting a plan
  is one act. The "goal" chip stands beside it, clear of the legend and the minimap. `?` lists `n`.

The graph's own tab:

- The graph opens as a tab by itself when work starts: the window opens on a plan with work left, a plan appears,
  or a run starts. It does not take the keyboard focus and opens beside the file you are working in, never over
  it; a tab you close stays closed until the next plan or run. `graphene.graph.openOnStart` (on by default) turns
  it off; Show graph opens the same tab as before.

The graph is built by hand (10 to 11 November 2026). It needs no newer CLI: every click is a 0.9.0 command.

- A task's pane is a form: its title, the files it may change and its check are typed in place; attempts are a
  stepper (1 to 8) on that task alone; "wait for my approval" and "I will do this one" are tick boxes. The pop-up
  chain is gone from the graph (Edit Task… stays in the Plan view).
- A task set to several attempts says so before anything runs.
- Add task, the + on a box, and the + key draw a draft box: type its title on it, then its files and its check. It joins the
  plan (`graphene node add`) once graphene will take it. "Fill it in for me" hands its title to the planner.
- Under the form, one line says what a change does now (suggested, not started, working, to review, done), and
  graphene's refusal of a change shows there, whole.
- Home has an Exact switch, off by default. On, it sets `board: on`, `review: every` and `auto: off`, and Home's
  Start waits until you have answered every open question (a default's button confirms it).

## 0.9.0 (unreleased)

Beside Graphene 0.9.0: the editor night (26 to 27 October 2026), then Home (28 October).

- Home leads the side bar and does everything with a click: set the folder up (one pick: Claude Code, Codex or
  Nemotron), say what you want and Plan it, read the suggested tasks (what each is for, the files it may change,
  what proves it), Start, then review each finished task: Open changes, Approve, or Send back… with a note.
- Approving a task whose changes you never opened asks first; Set Up turns on `review: every` (each finished task
  waits for your approval) unless you untick it; two attempts that both passed are compared and one kept first.
- Seven commands in the palette (Home, Show Graph, Watch the Demo, Stop All Agents, Set Up This Folder, Install
  Graphene…, Set API Key…); the rest, and the Needs You, Agents, Plan and Rounds views, with `graphene.advanced`.
- Plain words on screen: suggested, working, to review, needs help, attempt, approve, send back, limits.

- Needs You, first in the sidebar: questions, proposals, hand-backs, sign-offs and auto mode waiting, each with
  its move inline; nothing sends you to the cockpit.
- Agents: every running agent with its task, model, fork, what it edits now, seconds quiet and dollars; a click
  opens its changes so far.
- Diffs in the diff editor: a task or a fork against its base, a race's forks side by side, keep one from there.
- Edit Plan as Text: the plan's text form in an editor tab; save applies it, refusals are diagnostics.
- Add Step… takes one sentence and the planner proposes the step; Add Step by Hand… keeps the four boxes.
- A file a running task owns says whose it is and offers Diff with the Agent's Copy.
- Watch the Demo plays a scripted run in the graph with no key and no network, and says so in its header.
- The graph reads at every width: no text under 11 px, the goal always in reach, forks with their progress and
  the kept one's reason, a task that came back in red with why.
- Live: `graphene state --json --watch` when the CLI has it, a poll on an older one; the watcher covers the
  store's own files only.
- First run: finds `graphene` in `~/.local/bin` and uv's tool dir, offers to install it after you say yes; Set
  Up This Folder is two quick picks.
- Ready for the Marketplace and Open VSX: an icon, a README for the listing page, and a workflow that
  publishes the `.vsix` to both. The `.vsix` is named for the version in package.json.
- A refused key offers Set Key (`graphene key set` in a terminal); Mark Your Task Done finishes a task of your
  own; Auto…'s first choice is Plan first; a task that came back can be dropped.
- Rounds counts each round's own accepts; a race on the stand-in says so first; link mode disarms from outside
  and offers Cancel; the pane's acts stay in reach under a long note.
- Tried in Cursor 3.25.6 (VS Code 1.128) by the harness in `editors/vscode/e2e`: the `.vsix` installs and
  activates, and the end-to-end check passes there.

## 0.8.0

The first release, beside Graphene 0.8.0.

- The Plan view: goal → sub-goals → tasks with a codicon per state, `model · forks · $`, the contract in the tooltip.
- The graph: boxes by state in the cockpit's words, sub-goals as bands, the goal at the right, forks fanning out
  with their model and the kept one marked, the auto header; a details pane with Add step after / under, Link
  to…, Edit, Drop, Accept, Tell; wheel zoom, drag pan, arrow keys.
- Commands: Show Plan Graph, Open Cockpit, Auto…, Run Ready Tasks, Stop, Accept, Accept All, Add Step…, Link…,
  Edit Step…, Drop Step, Tell Agent…, Refresh.
- A status bar item: `◆ 2 running · 1 needs you · $0.42`.
- Reads `graphene state --json`; refreshes on changes under `.graphene/` and on a poll while a view is open;
  every change is a graphene command run as the person, the agent marks taken out of the environment.
