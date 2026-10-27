# The after: the night's extension, measured as the before was

The same harness and scripts as `../before/`, run back to back with the before at 04:48 to 05:10 on 27 October,
VS Code 1.143.1, on a quiet machine (load 4 to 10; each log names its load). The before is 0.8.0's released
`.vsix` with 0.8.0's `graphene`; the after is the night's `.vsix` with the branch's `graphene`. The logs are in
the night's scratch; the numbers and the scripts that made them are here.

| | before (0.8.0) | after (the night) | script |
|---|---|---|---|
| Install to the first graph, median of 3 | 2.43 s | 2.50 s | `measure/first-graph.mjs` |
| The cockpit's 17 moves: whole, in part, not at all | 4, 6, 7 | 9, 5, 3 | `moves.md` here and in `../before/` |
| Smallest text, side bar at 280, 320, 400 px | 4.61, 5.48, 7.21 px | 11, 11, 11 px | `shots.mjs` |
| Smallest text, tab at 1280x800 and 1920x1050 | 10.74, 11 px | 11, 11 px | `shots.mjs` |
| A store write to the screen, 20 runs | p50 123 ms, p90 502, max 735 | p50 31 ms, p90 84, max 102 | `measure/latency.mjs` |
| Idle 60 s: the extension host | 1.0 % | 0.2 % | `measure/idle-cpu.mjs` |
| Idle 60 s: graphene processes | 43 seen, 3.8 % | 1 seen, 0.5 % | `measure/idle-cpu.mjs` |
| Idle 60 s: the whole app tree | 10.7 % | 2.3 % | `measure/idle-cpu.mjs` |

What the numbers say:
- **Readable.** The side bar no longer shrinks the graph to a thumbnail: under 560 px it draws lanes, a row a
  task, and no text anywhere is under 11 px. The after's measure is stricter than the before's: it reads every
  shown text, the header and the pane included, not only the drawing's.
- **Quiet when idle.** The before ran one `graphene state --json` every 1.1 s (43 in a minute); the after keeps
  one `graphene state --json --watch` open, which reads the store's version every 100 ms and prints nothing
  when nothing changed.
- **Live.** A store write reaches the screen in 31 ms at the median and 102 ms at worst, inside the second the
  directive asks for; the before's poll and watcher took up to 735 ms. Both runs at load 13.6, back to back.
- **First graph** is the app's launch either way: under a tenth of a second apart.
- **Moves** is a judgment, key by key, not a count a script makes: `moves.md`.

The screenshots, the same widths, sizes and themes as the before's: `code-sidebar-*.png`, `code-panel-*.png`,
with `code-smallest-text.json`. Cursor's after was not shot; the harness's check passes there.
