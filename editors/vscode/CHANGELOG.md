# Changelog

## 0.9.0 (unreleased)

Beside Graphene 0.9.0: the editor night (26 to 27 October 2026).

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
