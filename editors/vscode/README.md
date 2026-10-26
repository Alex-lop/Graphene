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
  pane; drag a task's dot (its right edge) onto another and that one waits on it; arrow keys move the
  selection; the wheel zooms, dragging pans, a double click fits.
- **Rounds** view: auto mode's iterations, one row a round (`Round 2 · done · 1 accepted · 1 landed · goal ✓ ·
  $0.02`), and under it what the envelope accepted, which fork each task kept and why, what landed, and the
  line the goal's check failed on that sent it there. It reads `graphene plan log --json`, only while it is open.
- **Explorer**: each file a task owns is marked, a running task's with its agent's number in yellow (the task,
  its model and its forks in the tooltip), one waiting for your sign-off with ✓, one that came back with !, one
  not started yet with ·: whose is whose, at a glance. The scope globs are read as the CLI reads them.
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
| Auto… | asks for a goal, an optional budget, and whether to plan first; `graphene auto "<goal>" --budget N [--plan]` in a terminal you can Ctrl-C |
| Set Up This Folder | `graphene init` in a terminal: it asks which planner and executor to use |
| Set Envelope… | shows auto, budget, tasks, rounds, forks and checks as they are, and sets the one you pick with `graphene config set KEY VALUE` |
| Run Ready Tasks | `graphene run --parallel 4` in a terminal |
| Stop | `graphene run --stop` |
| Accept / Accept All | `graphene plan accept [ID]` |
| Add Step… | title, where (after a task, i.e. waiting on it; or under a sub-goal), scope, check; `graphene node add TITLE --parent P --needs X --scope G --check C` |
| Link… | A then B, B waits on A: `graphene node set B --add-needs A` (in the graph: drag A's dot onto B, or Link to… then click B; Esc cancels) |
| Unlink (the × beside a task under "needs", in the details pane) | B stops waiting on A: `graphene node set B --needs <the rest>`, or `--needs none` |
| Edit Step… | title, scope or check: `graphene node set ID --title/--scope/--check` |
| Drop Step | `graphene node drop ID` (`graphene plan undo` puts it back) |
| Tell Agent… | `graphene board note "<line>" --about ID`: a hooked agent reads it before its next write |
| Refresh | reads the plan again |

While auto mode runs, a notification says when it waits for you (with why), when the goal's check failed and a
round plans the fix, and when it is done, with a button to the graph or the cockpit.

Settings: `graphene.path` (the command, default `graphene`; set it when `uv tool install` put it somewhere
the editor does not see; your own settings only, so a cloned folder's `.vscode/settings.json` cannot choose what
the extension runs) and `graphene.pollMs`. In a folder VS Code does not trust (Restricted Mode) the extension is
off: it runs commands, and the plan's checks, there.

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

Graphene itself first (`uv tool install graphene-map`, 0.8 or later). Then the extension: download
`graphene-0.8.0.vsix` from [the release](https://github.com/Alex-lop/Graphene/releases/latest), or build it
from this folder (below), and

```sh
code --install-extension graphene-0.8.0.vsix      # Cursor: cursor --install-extension graphene-0.8.0.vsix
```

VS Code's Welcome page then has **Get started with Graphene**: install, set up the folder, give it a goal, watch
and steer, set the limits; each step a button.

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
