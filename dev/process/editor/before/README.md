# The before: Graphene for VS Code as Alex saw it, 27 October 2026

The extension built from `main` at 2da29a52 (0.8.0, the release's build), installed by the harness
(`editors/vscode/e2e/`) in a profile of its own in VS Code 1.143.1 and Cursor 3.25.6 on Alex's Mac
(Apple silicon). The store is wordkit (`dev/proof/make_wordkit.py`) after `graphene auto` raced it against
the stand-in (`dev/proof/standin.py`): two rounds, four tasks landed, twelve forks. Every number here comes
from a script under `editors/vscode/e2e/measure/`, so the after runs the same one.

## Screenshots

`APP-WHAT-THEME.png`: the side bar at 280, 320 and 400 px, the editor tab at 1280x800 and 1920x1050, in
Dark Modern, Light Modern and High Contrast. `node shots.mjs --app code --vsix FILE --out DIR` made them.
The tab was asked for 1920x1080; on this 1920x1080 display a window takes the work area, 1920x1050, and
the file is named by what the window took. (A first set named `1920x1080` was that size in VS Code and the
1280x800 window in Cursor, which had not grown; both sets were taken again with the harness as committed,
`setSize` reporting the size and the profile's `editor.accessibilitySupport` off, so no screen reader
toast covers the panel.)

The Cursor set (`cursor-*.png`) is the same store in Cursor 3.25.6, in its classic layout (see Friction).

Two more, on a fresh store with three short tasks and no goal (what the first minute looks like):
`code-sidebar-300-dark-fresh-profile.png` (the Chat pane open, as a fresh profile has it) and
`code-sidebar-300-dark-three-tasks.png` (the tab open too).

Look at these first:
- `code-sidebar-320-dark.png`: the side bar's Graph view is all goal text. The sentence wraps over eight
  lines and the graph itself is below the fold. It is the same at 280 and 400, in every theme.
- `code-sidebar-300-dark-three-tasks.png`: when the graph does fit (no goal, three tasks), it is a
  thumbnail at scale 0.35: titles 3.85 px tall.
- `code-panel-1280x800-hc.png`: in High Contrast the kept fork's chip is light text on a light fill.

## Video

Videos stay out of the repository, in `~/graphene-film/harness/`:
- `code-shots-2026-10-27-0039.webm` (87 s): the shots session above, every width and theme.
- `code-race-2026-10-27-0052.webm` (54 s): the race live in the editor, `shots.mjs --during`: the window
  opens on an empty plan, Ultra's three tasks appear, nine forks run and land, the goal's check goes red,
  the fix lands. The race takes 24 s against the stand-in.

One more shot from the driver, mid-race: `code-panel-1920x1050-dark-race-running.png` (the counts say
"1 needs you"; nothing in the editor says what, or lets you answer). `race.log` is what `graphene auto`
printed for the store the shots show.

## The five numbers

1. **Seconds from installing the .vsix to the first graph drawn** (`measure/first-graph.mjs`, median of 3,
   VS Code): **2.69 s** (install 0.23, launch to workbench 1.46, open Graphene to the graph 0.97). The
   app is warm: it had run before.
2. **The editor's moves against the cockpit's** (`measure/moves.py`, in `moves.md`): the cockpit has
   **17** moves; the editor covers **4 whole and 6 in part, 7 not at all** (a question's options, widen,
   hand back, run one task, fork, undo, the map). The extension has 15 commands.
3. **The smallest text drawn**, font size times the SVG's scale, in CSS px (`shots.mjs`, in
   `code-smallest-text.json`): side bar **4.61 px at 280, 5.48 at 320, 7.21 at 400**; editor tab
   **10.74 px at 1280x800, 11 at 1920x1050**. The 11 px text is the band label and the fork chips at
   scale 1: the page never draws larger than 1:1. In the side bar that text is also below the fold.
   Cursor (`cursor-smallest-text.json`): 4.68 at 280, 5.54 at 320, and 3.85 at 400, the scale's floor of
   0.35, because the sash drag there left the view a different height; 11 px in the tab at 1280x800 and
   at 1920x1050 (the canvas 940 and 1580 px wide).
4. **Latency from a store write to the screen** (`measure/latency.mjs`, `graphene node set` of a title,
   20 runs, VS Code, load average 15.7 with the other lanes running): **p50 574 ms, p90 871, max 1190,
   mean 568, min 12**. Five of the twenty showed in under 220 ms, the rest took 400 to 1190: the write lands
   at a random phase of the extension's 1.5 s poll, what finds it varies between the watcher on
   `.graphene/**` and that poll, and each find is a fresh `graphene state --json` (about 100 ms) before the
   page redraws. An earlier 5-run median was 515 ms (147 to 582); five runs swing 4x between identical
   runs, so the after compares against this spread, taken again on a quiet machine.
5. **Idle CPU over 60 s** with the views open and nothing happening (`measure/idle-cpu.mjs`, VS Code):
   **extension host 0.9 %; the graphene processes it spawns 5.1 %** (54 `graphene state --json` runs in
   60 s, about one every 1.1 s: the 1.5 s poll plus the watcher's own reads); the whole app tree, window
   and all, 10.7 %. Sampled every 200 ms, so a process shorter than that is undercounted: 5.1 % is a floor.

## The stranger's first hour

The orchestrator ran it on 0.8.0's released `.vsix`, from 00:49 to 01:18, through a fresh-start variant of
`drive.mjs`: [stranger.md](stranger.md). Eleven minutes to the first graph, 28 to the first accept from the
graph, nine guesses; the worst wall is a missing key that no surface says how to set.

## Friction

One line each, with the screenshot it shows in.
- The side bar's Graph view puts the whole goal sentence above the graph; at 280 to 400 px that is seven
  to nine lines and the graph is off screen (`code-sidebar-320-dark.png`, `code-sidebar-400-dark.png`).
- When the graph fits, fit-to-view shrinks it to scale 0.35: boxes 3.85 px text, unreadable
  (`code-sidebar-300-dark-three-tasks.png`).
- The four buttons wrap to two rows under 400 px (`code-sidebar-320-dark.png`).
- The band label is cut at the canvas' right edge: "...the N most commor" (`code-panel-1280x800-dark.png`).
- High Contrast: the kept chip's text is unreadable on its fill; the running stripe colours are the
  theme's defaults (`code-panel-1280x800-hc.png`).
- The Plan tree's rows cut the useful words first: "Nano · 3 forks · kept b · $0..." at 400, nothing of it
  at 280 (`code-sidebar-280-dark.png`).
- A store change shows after about half a second, by the poll, not the watcher (number 4).
- Mid-race the counts say "1 needs you" and the status bar too, but nothing in the editor shows the
  question or takes an answer (`code-panel-1920x1050-dark-race-running.png`).
- The Graph view's footer shows the last log line ("agent 1b: its check passed, 7 lines") under a
  thumbnail nobody can read: the one live line of the race is the smallest thing on screen (same shot).
- The editor tab at 1920x1050 leaves two thirds of the width empty: the graph is drawn 1:1 and sits left
  (`code-panel-1920x1050-dark.png`, `cursor-panel-1920x1050-dark.png`).
- Cursor 3.25.6 on a fresh profile shows a log-in wall over the whole window, and its agent layout keeps
  the primary side bar at display:none: Graphene's views are there (the status bar shows `◆ 0 of 3 done`)
  but cannot be seen without an account. The harness hides the wall, closes the agents pane and lets the
  side bar show (`lib.mjs`, `cursorClassic`). In Cursor's classic layout the views look as in VS Code
  (`cursor-*.png`).
- Cursor writes a folder's agent data (canvases, terminals, mcps) to `~/.cursor/projects/<path>` on every
  open, whatever `--user-data-dir` it runs with; the harness removes that entry when it closes (`lib.mjs`,
  `close`). Not Graphene's.
- The harness itself trips VS Code's "screen reader detected" toast (the automation looks like one); the
  profile turns `editor.accessibilitySupport` off, and the shots here were taken with it off. Not
  Graphene's.

## How it was run

```
git worktree add WORK/main-2da29a52 2da29a52 && cd WORK/main-2da29a52/editors/vscode && npm ci && npm run package
cd editors/vscode/e2e && npm ci
VSIX=WORK/main-2da29a52/editors/vscode/graphene-0.8.0.vsix
node shots.mjs --app code --vsix $VSIX --out before --video ~/graphene-film/harness
node shots.mjs --app cursor --vsix $VSIX --out before
node measure/first-graph.mjs --app code --vsix $VSIX --runs 3
node measure/latency.mjs --app code --vsix $VSIX --runs 20
node measure/idle-cpu.mjs --app code --vsix $VSIX --seconds 60
uv run python editors/vscode/e2e/measure/moves.py WORK/main-2da29a52/editors/vscode/package.json > moves.md
```
