# The editor night, 26 to 27 October 2026

*Kept current as the night goes. Last written at 00:40, when the lanes started.*

## Your 15 minutes

Not written yet: it is written once the branch is pushed, and run as written from it before 07:55.

## Tuesday

Not written yet.

## The brief

1. **Before and after.** Nothing measured yet: lane 0 measures the before on 0.8.0's extension first.
2. **Look at these first.** Nothing yet.
3. **The review.** Lane 5 runs from the start: two fresh reviewers on auto mode, the envelope, state and the
   gate. The extension's half runs once the new editor lands.
4. **Your notes.** `~/graphene-notes.md` did not exist when the night started.
5. **The browser spike.** Running.
6. **Decide.** Nothing yet.
7. **Broken or risky.** No Token Factory tonight: `GRAPHENE_AGENT_LIVE_USD` was not set, so lane 7's live takes
   do not run. The stand-in rehearsal and the b-roll still do. Two things of tonight's are on your screen, both
   safe to close: a VS Code window "Welcome — wordkit" (lane 4's scratch fixture, opened in your running VS Code
   at 00:31 because its profile's path was too long; Restricted Mode, nothing ran; it is in your recents too),
   and a macOS prompt "WezTerm wants access to control System Events" (answer Don't Allow). Every lane now
   launches VS Code with a short profile path.

## How the night runs

The work is in a fresh clone of GitHub's `main`, on `night/editor`, never in your checkout.
`dev/process/editor/CONTRACT.md` says which lane writes which file and the CLI shapes the editor codes against.
Each lane builds in its own clone; a skeptic who didn't write it reviews it; a fixer pairs each fault with the
test that failed before it. Subagents run on Fable first and on Opus 5.5 once Fable's limit hits.

| Lane | What | State at 00:40 |
|---|---|---|
| 0 | the harness: real VS Code and Cursor driven by Playwright, the before | building |
| 1 | the graph, readable at any width, the race visible | building |
| 2a | Needs You, Agents, first run, the stream | building |
| 2b | diffs, the plan as text, a step in a sentence, the demo, files you open | building |
| 3 | the CLI: `state --watch`, `node diff --json`, `plan edit --from -`, `ask --step`, `demo --into` | building |
| 4 | the listing, the publish workflow, RELEASING | building |
| 5 | auto mode reviewed by two who weren't there | reading |
| 6 | the docs | at the end |
| 7 | the live take and the b-roll | after lanes 0 to 2 |
| 8 | the browser spike | running |

## Branches and rollback

- `main` on GitHub was `2da29a52a1b38031418506f5a7a6929c121f673b` when the night started. That is the rollback.
- `night/editor`: the directive, the contract and the module stubs so far. Nothing pushed yet.
