# Changelog

## 0.10.0 (not yet tagged)

The graph is where you watch and shape agent work: whole, in a tab of its own, with a plan from your agent's chat
(10 to 23 November 2026). It needs Graphene 0.10.0's CLI: with 0.9.0's every task's pane says Not held and no
check's box is ticked. Nothing here ran with a real agent: every walk used the scripted stand-in.

The tab:

- A click on Graphene's icon opens the graph whole in the editor area; the side bar's narrow Graph view is gone,
  and Home is the side bar's one page. Show Graph is Open the Graph: in the palette, on Home's title bar and as
  Home's first card.
- It opens by itself when work starts (a plan with work left, a plan appearing, a run starting), without the
  keyboard: beside your file in VS Code, in front of it in Cursor, whose agent chat already narrows the editor.
  Closed, it stays closed in that window until Open the Graph (`graphene.graph.openOnStart`).
- No box to type a goal in, on Home or in the palette (Plan it and Graphene: Auto… are gone): a plan comes from
  your coding agent's chat, a workflow, or Add task. In Cursor, one dim line says its own Agent does not plan
  with Graphene yet. An empty plan points to your agent's chat or to Add task. A plan Claude Code is still
  writing is drawn task by task, as `graphene ask` reads it; a Codex plan appears whole.

The header:

- Two rows: the goal and its buttons, then Plan, Run and Review with their counts and, for a plan running on its
  own, its round. One main act: Start for a suggested plan (it accepts, then runs, as Home's), Run, or Stop while
  a run goes; Exact holds Start while a question is open. Save as workflow, Lanes and Keys and mouse are icons.
- Stop after the plan is Home's, under its Settings: beside Start and Stop it read as another stop. A practice
  run or a replay shows no cost anywhere.

The canvas:

- The whole plan opens in view, fitted again when the window or the plan changes until you pan or zoom (`f`,
  the fit button, a double click). Whole cards only where their smallest words read at 11 px, else rows: a mark
  and a title. Zoom 20% to 300%. Choosing a card moves nothing.
- A sub-goal's tasks are grouped under its header (a ring, `3 of 6`, what wants you there), loose tasks side by
  side; edges are square, in the gaps between cards, one from each sub-goal into the goal; a chosen card's lines
  are lit. No frame round a plan that stays on this machine; the leaves your machine region shows only once a
  task would push or open a pull request.
- A chip walks what needs you (`3 tasks need you · show the next`, `n`), and an open question has a chip of its
  own (`1 question · answer`). The legend is the marks with their words and counts; the minimap shows only while
  the plan moves; `g` still brings the goal.

The cards:

- A card is whole and inside its border: its title on two lines, its files, a status, and at its foot its check,
  with a box only Graphene ticks (ticked passed, crossed failed, dotted not run). No letter tile: who does a task
  is in its pane.
- A card wears its state on its mark, and colour only where it wants you (to review, needs help, asks you); blue
  round a card is the selection alone. Its status says what nothing else on it does: what a suggestion covers,
  the agent on a working task, `3 agents at once` for attempts not started.
- The one act a task needs from you is a button on its card: Open changes, then Approve once they are open,
  Answer…, Help it…, Compare, Approve and run, Mark done, Allow the write…. Drafts are grey dashes.

The pane, an inspector:

- Its head says the state and who does the task; its tabs are Scope, Edit and Activity; its foot holds what you
  do to the task now, and adding, linking, messaging and removing sit in a … menu. A task to review is opened
  before it is approved, with Send back… beside Approve.
- Scope: the files it may change, under their folders; done when, and what its check said before and after the
  work; what it may run; how a write outside its files is held (no more than the tests prove); the writes stopped.
- Edit is a form: title, files, check, attempts (a stepper, 1 to 8), wait for my approval, I will do this one.
  Add task, the + past a card and the `+` key draw a draft that joins the plan once it has files and a check.

Home:

- Its first card opens the graph; Stop after the plan and Exact sit under Settings at its foot; Exact holds Start
  for every open question. One filled act a card at most, a card's state said once, paths cut at whole folders.
- Working now in amber, a plan's cost said at list price, a question named by its sub-goal, Install only when
  graphene is missing, and Set Up says before the click what it writes. Home lists the folder's workflows and
  runs one on new inputs with no planner call; a `run:` task that pushes or opens a pull request waits past the
  leaves your machine line for Approve and run.

The look and the words:

- One set of colours, lines and corners for the graph and Home (`media/tokens.css`), none read from what Cursor's
  themes leave weak; `media/preview.html` and `media/home-preview.html` draw both in Cursor's themes and VS
  Code's with no editor (`?theme=`).
- One word a thing on every screen: task, suggested, working, to review, needs help, done, attempt, card (`3 tasks
  need you`, `2 of 7 done`, Remove where it said Drop). The README is half as long.

## 0.9.0 (29 October 2026)

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
