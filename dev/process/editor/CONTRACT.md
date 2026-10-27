# The editor night: who writes what, and the shapes between lanes

The orchestrator wrote this before any lane started, so the lanes can build at once. One writer a path:
a lane writes only the paths listed under it. A lane that needs another lane's file, or a change to
this contract, writes the request in the shared log (`$SHARED/log.md`, the path is in the lane's brief)
and carries on against the contract as written. The orchestrator merges and answers there.

Graphene's own hook, in force in every session tonight, refuses a shell command whose text names the
store's directory (dot, then `graphene`, then a slash) or the extension's full id (publisher, dot, name).
Use the Read, Grep, Edit and Write tools for such text, or write the command into a script file and run
the file. Never split the words to get past it.

## The CLI, lane 3 (shapes the editor codes against)

Every new flag has `--help` in the cut directive's voice and a paragraph in `docs/HOW_IT_WORKS.md`.
No new top-level command.

1. **The stream.** `graphene state --json --watch` prints the snapshot `state --json` prints, as one
   line, at once; then one more line each time the store changes (its own version: SQLite's
   `PRAGMA data_version`, the log's last id, the run lock coming or going), at most one line every
   100 ms. Nothing when nothing changed: idle costs one cheap query a tick. It ends when its stdout
   closes or on SIGTERM, exit 0. An older CLI answers `--watch` with "No such option": the editor then
   polls `state --json` as it does today.
2. **More in the snapshot** (schema 1, siblings only, never a rename):
   - top level `replay`: null, or `{"shown": "a scripted stand-in, no model ran", "day": "2026-10-26",
     "repository": "wordkit"}` when the store is a replay's (`graphene demo --into`);
   - each task: `why` (a task that came back: its reason, one line, else ""), `checkout` (the
     directory its agent works in while it runs or after it came back, else null), `base` (the commit
     its work starts from, else null), `attempts` (int);
   - each fork: `attempts` (int), `idle` (seconds quiet while it runs, else null), `checkout`
     (its own directory while it runs, else null).
3. **A diff the editor can open.** `graphene node diff <id> [--fork X] --json` prints
   `{"repo": DIR, "left": REV, "right": REV-or-null, "files": [{"path": P, "status": "M|A|D|R",
   "old": P-or-null}], "said": [lines]}`: `right` null means the working tree in `repo` (a running
   task's or fork's own directory: "its changes so far"). A running task is no longer refused: it is
   its directory against its base. Exit 1 with the refusal on stderr when there is nothing to show.
4. **The plan's text applied from a pipe.** `graphene plan edit --from - --json [--since CURSOR]`
   reads the text `graphene plan --text` prints, applies it as one save in the editor would, all or
   none, and prints `{"applied": true|false, "said": [lines], "faults": [{"line": N, "text": T}]}`.
   Exit 0 applied (or nothing changed), 1 refused. A fault's line is the text's own line number
   (1-based): a parse fault's "line N:", else the line of the `[id]` the refusal names, else 1.
   `--since` is the snapshot's cursor when the text was read: a node someone else changed after it is
   refused, not written over.
5. **One sentence, one proposed step.** `graphene ask "<sentence>" --step [--after ID | --under ID]`.
   The configured planner (Nano when the planner is Nemotron) proposes one step with its title,
   scope, check and needs; it lands as a proposal, whoever asked. Only a person, or the envelope when
   auto is on and it fits, accepts it. Prints the proposal's id on its first line: `proposed ID: TITLE`.
6. **A replay the editor can watch.** `graphene demo [RECORDING | --auto | --cheat | --live]
   --into DIR` plays the recording into DIR, a new or empty directory that becomes the replay's own
   git repository and store, on the recorded clock (`--speed` as today), with no screen: one line a
   change on stdout (`what()`), then it stays at the last frame until SIGTERM, exit 0. It never
   writes outside DIR. The store's plan_meta key `replay` holds what the snapshot's `replay` says.

## The extension

`src/session.ts` holds `Session` (one per folder: the person's, or a replay's). Each feature module
exports `register(context, session, ui)` and `extension.ts` calls it; `ui` carries the shared pieces
(`graph`: the GraphHost, `tree`, `reveal(id)`).

| Lane | Writes |
|---|---|
| 1, the graph | `src/graph/**`, `src/layout.ts`, `src/graph.ts`, `media/graph.css`, `media/preview.html`, `test/layout.test.ts`, `test/graph-*.test.ts`, `test/fixtures/graph-*.json` |
| 2a, needs you, agents, first run, the stream | `src/extension.ts`, `src/session.ts`, `src/state.ts`, `src/tree.ts`, `src/owners.ts`, `src/rounds.ts`, `src/roundsView.ts`, `src/needs.ts`, `src/agents.ts`, `src/find.ts`, `src/stream.ts`, `package.json`, `test/state.test.ts`, `test/owners.test.ts`, `test/rounds.test.ts`, `test/needs.test.ts`, `test/agents.test.ts`, `test/find.test.ts`, `test/stream.test.ts`, `test/smoke*.cjs` |
| 2b, diffs, the plan as text, a step in a sentence, the demo, files you open | `src/diff.ts`, `src/planDoc.ts`, `src/step.ts`, `src/demo.ts`, `src/files.ts`, `src/commands.ts`, `test/commands.test.ts`, `test/diff.test.ts`, `test/planDoc.test.ts`, `test/step.test.ts`, `test/demo.test.ts`, `test/files.test.ts` |
| 0, the harness | `editors/vscode/e2e/**`, `dev/proof/standin.py`, `dev/process/editor/before/**`, `dev/process/editor/after/**`, `dev/process/editor/research.md` |
| 3, the CLI | `src/graphene_map/state.py`, `plan_cli.py`, `plan_text.py`, `demo.py`, `ask.py`, `docs/HOW_IT_WORKS.md`, new `tests/test_editor_*.py` |
| 4, the listing | `editors/vscode/media/icon.png`, `editors/vscode/README.md`, `editors/vscode/CHANGELOG.md`, `editors/vscode/.vscodeignore`, `.github/workflows/**`, `docs/RELEASING.md` |
| 5, the review | findings in `dev/process/editor/review.md`; each fix, with its test, in the file it fixes, merged by the orchestrator |
| 7, the take | `dev/proof/auto.sh`, `dev/launch/video-auto.md` (beat names only) |
| 8, the browser spike | `dev/process/editor/browser-spike.md` only |

Commands 2a registers: `graphene.answer` (a question: its options, its default, or your own words),
`graphene.handBack` (a task that came back: its offers), `graphene.install`, `graphene.init` (two quick
picks, then `graphene init` in a terminal), plus every command that exists today except `addStep`.
Views 2a adds, first in the container: `graphene.needs` (Needs You) and `graphene.agents` (Agents).

Commands 2b registers: `graphene.openDiff` (`{id, fork?}`), `graphene.compareForks` (`{id}`),
`graphene.pickFork` (`{id, fork}`), `graphene.signOff` (`{id}`), `graphene.editPlan`,
`graphene.addStep` (`{id?, after?, under?}`: a sentence), `graphene.addStepByHand` (the four boxes),
`graphene.watchDemo`, `graphene.diffWithAgent` (the active file).

The graph's page asks the host with `{type: "act", act, id, target?, fork?}`. Lane 1 maps each act
to one of the commands above with `executeCommand`; a command not there yet is a message, not a throw.

## The harness, lane 0

`editors/vscode/e2e/` has its own `package.json` (Playwright's Electron driver), so the extension's
manifest and its `.vsix` stay as they are. It launches VS Code (and `/Applications/Cursor.app`)
with a `--user-data-dir` and `--extensions-dir` of its own, never Alex's, installs a `.vsix`, opens
a fixture repository it trusts, and drives a real store with `graphene auto` against the stand-in
(`dev/proof/standin.py`, which serves `tests/fake_tokenfactory.py` with auto mode's script on
127.0.0.1). Other lanes use it to look at their work in the real app.
