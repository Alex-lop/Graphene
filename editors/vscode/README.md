# Graphene for VS Code

Your plan as a graph you can act on, inside VS Code (and Cursor): the tasks Graphene holds its agents to,
coloured by state, flowing left to right into your goal; a forked task fanning out into its forks with the
model on each; the auto round and its spend when auto is on. Click a task for its contract and the last
moves; add a step after it, link two steps, edit, drop, accept, or tell the agent on it a line.

![the graph: a running plan with three forks on one task, the kept one marked](media/graph.png)

It is a thin client: everything it shows comes from `graphene state --json`, and everything it changes is a
`graphene` command, the same ones the terminal cockpit (`graphene watch`) runs.

## What it shows

- **Plan** view (the Graphene icon in the activity bar): goal → sub-goals → tasks, a codicon per state
  (running, review, came back, ready, waiting, proposed, done), `model · forks · $` beside each task, the
  contract (goal, scope, check, last moves) in the tooltip. A click opens the graph on that task.
- **Graph** (`Graphene: Show Plan Graph`, also a view in the sidebar): boxes by state with the cockpit's
  words, sub-goals as bands, the goal at the right, the plan's width; a running box names its model; a
  forked task fans out into its forks (letter, model, state, the kept one marked); an auto header
  (`auto · round 1 of 2 · running · $0.42 of $2.00`) when auto is on. Click selects and opens the details
  pane; arrow keys move the selection; the wheel zooms, dragging pans, a double click fits.
- **Status bar**: `◆ 2 running · 1 needs you · $0.42`; click for the graph.

It reads the plan again whenever the store's files change (`.graphene/`, watched as a directory: the WAL
changes before `graphene.db` does) and every `graphene.pollMs` (1500 ms) while a Graphene view is open.

## Commands

All under `Graphene:` in the command palette; most also in the Plan view's title and context menus, and as
buttons in the graph's details pane.

| Command | What runs |
| --- | --- |
| Show Plan Graph | the graph, as an editor tab |
| Open Cockpit | `graphene watch` in a terminal |
| Auto… | asks for a goal, then an optional budget; `graphene auto "<goal>" --budget N` in a terminal you can Ctrl-C |
| Set Envelope… | shows auto, budget, tasks, rounds and forks as they are, and sets the one you pick with `graphene config set KEY VALUE` |
| Run Ready Tasks | `graphene run --parallel 4` in a terminal |
| Stop | `graphene run --stop` |
| Accept / Accept All | `graphene plan accept [ID]` |
| Add Step… | title, where (after a task, i.e. waiting on it; or under a sub-goal), scope, check; `graphene node add TITLE --parent P --needs X --scope G --check C` |
| Link… | A then B, B waits on A: `graphene node set B --add-needs A` (in the graph: Link to…, then click the target; Esc cancels) |
| Edit Step… | title, scope or check: `graphene node set ID --title/--scope/--check` |
| Drop Step | `graphene node drop ID` (`graphene plan undo` puts it back) |
| Tell Agent… | `graphene board note "<line>" --about ID`: a hooked agent reads it before its next write |
| Refresh | reads the plan again |

Settings: `graphene.path` (the command, default `graphene`; set it when `uv tool install` put it somewhere
the editor does not see) and `graphene.pollMs`.

## How it talks to the CLI

Reads are `graphene state --json`, run with `execFile` in the workspace folder that holds `.graphene/`
(the first such folder, else the first folder). Changes are one command each, run the same way, and a
refusal (exit 1) is shown as its first line of stderr. Long commands (`watch`, `run`, `auto`) run in a
terminal you see and can stop.

**A click in VS Code is the person's.** Graphene decides who is calling from the environment alone: a
shell marked by a coding agent (`CLAUDECODE`, `CODEX_SESSION_ID`, `AI_AGENT`, `GRAPHENE_NODE`, …) makes every
command an agent's, so an accept would be refused and a new step would land as a proposal. VS Code started
from such a shell inherits those marks, so the extension takes them out of the environment of everything it
runs, including its terminals. It never sets `GRAPHENE_AS` or `GRAPHENE_WATCH`.

Clear states instead of an empty tree: Graphene not found (`uv tool install graphene-map`, or set
`graphene.path`), the folder not initialised (`graphene init`), or a CLI error (its first stderr line).

## Install

From a build of this folder:

```sh
code --install-extension graphene-0.8.0.vsix      # Cursor: cursor --install-extension graphene-0.8.0.vsix
```

To build it (Node 22+, no runtime dependencies):

```sh
cd editors/vscode
npm ci
npm test            # typecheck, the node tests, the build, and the VS Code smoke test when a local VS Code is found
npm run package     # graphene-0.8.0.vsix
```

`media/preview.html` shows the graph with a fixture state and no VS Code (`npm run build`, then open it;
`?fixture=auto`, `?fixture=proposals`, `?fixture=empty`, `&select=greet`); `media/graph.png` is its screenshot.

## Limits

- It needs Graphene 0.8 (`graphene state --json`); with an older one every view says what the CLI said.
- An open board question is shown in the graph's footer, not answered here: `graphene board take|pick|answer`
  in the cockpit or the terminal.
- One plan per window: the first workspace folder with a store.
