# "Your 15 minutes", run once from the pushed branch

`dev/process/morning.md`'s "Your 15 minutes", run as written at 06:00 on 27 October, from `night/editor` as GitHub
had it (25beb4b1), and timed: 124 s of the machine's time, start to end. Each step did what the morning says.

What stood in for Alex, so nothing of his moved: the clone and the try went under `/tmp/gv-15`, not `~`; uv's tool
dir and bin were `/tmp/gv-15`'s own; VS Code and Cursor installed the `.vsix` into profiles of their own. The
harness (`editors/vscode/e2e/lib.mjs`) was the hands in VS Code: it opened `graphene-try` at the take's pause, ran
Watch the Demo, pressed the take's Enter, then clicked Needs You's ✓ and a done task's Open changes. Its scripts
(`run.sh`, `gui.mjs`) were the night's scratch, not the repo's.

```
0s    1. clone, build, install the CLI
3s       the clone is at 25beb4b1
7s       graphene 0.9.0
7s    2. the .vsix into VS Code and into Cursor (profiles of their own)
7s       VS Code: exit 0 · Extension 'graphene-0.9.0.vsix' was successfully installed.
7s       Cursor: exit 0 · Extension 'graphene-0.9.0.vsix' was successfully installed.
9s    4. the take waits: open /tmp/gv-15/graphene-try in VS Code and start recording, then press Enter
12s      VS Code open on graphene-try, Graphene's side bar shown
13s   3. Watch the Demo: "replay · a scripted stand-in, no model ran · 2026-10-26"
67s      the demo kept a fork
68s   4. Enter sent to the take
72s      the race on screen
95s      the take ended (exit 0); side bar: Needs You / Graph / Agents / Plan / Rounds
95s      the tab's header says "against the scripted stand-in"; 4 tasks done
96s   5. auto off; an agent proposed n6; Needs You shows it
97s      its ✓ (Accept) clicked: n6 is ready
124s     Open changes on the done task top: the diff editor's tab "CLI prints the top words: ac872d7 → defe002 (2 files)"
124s     the take's planner bill: $0.0166 at list price, a stand-in's usage: nothing was spent
```

Step 1 took 7 s because uv's and npm's caches were warm; a cold machine downloads the dependencies first, and that
was not timed. The screenshots:
`3-watch-the-demo.png`, `4-the-race-live.png` (three tasks, three forks each, against the stand-in) and
`5-open-changes.png` (VS Code's own diff editor on what the task landed).
