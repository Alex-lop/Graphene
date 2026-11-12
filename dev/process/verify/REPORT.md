Verification of [PR #60](https://github.com/Alex-lop/Graphene/pull/60): 30 commits from its recorded head `2a2c6fbb`, based on the restored `night/graph-edit` branch.

Delivery history: an earlier run opened PR #61 against `main`; Alex merged it on 12 Nov. This run leaves #61 untouched and prepares this separate draft against the restored `night/graph-edit` tip `2a2c6fbb`. The 30 commits here include the verification brief, fixes, tests, evidence and this report.

PR #60 lets Alex draw tasks, type their title/files/check in the pane, set attempts before running, take a task himself, and require approval. Home's Exact switch holds Start for unanswered questions. It did not add Codex write hooks or preserve drafts across pages.

Alex's historical session remains unidentified; the probes below reproduce concrete acceptance paths. The brief was stale: #60 was already merged. Alex explicitly authorized restoring its exact branch tip. This run does not change `main` or remove any branch. All work is in `/private/tmp/graphene-codex-verify`; the Desktop checkout was left untouched because its hard write prohibition conflicts with “clone in this folder”. Commits use Alex Lopez with a GitHub noreply address. This run made no main push, merge, tag, release or remote branch deletion; Nebius $0, Claude probes 0. Live Codex used xhigh and an isolated authenticated `CODEX_HOME`.

| Claim / boundary | What actually ran | Held or broke |
|---|---|---|
| Claude session, subagent, workflow gate | Replayed all three payloads; mutated the gate | Held; earlier Haiku transcripts remain historical evidence |
| Comment above redirect hides a write | `boundaries.py`: `# explain` then redirect | Held; the brief's “never fixed” claim was stale |
| Variable targets | Literal `F=outside.txt`; unknown `$OUT` | Literal denied; unknown target wrote, then finish refused |
| Write with another path field | `Write {path: ...}` through the real hook entry | Broke; now refused when its path cannot be read |
| Old recording-only hook file | Replayed old settings, then current installer | No pre-write hold until reinit; finish refused; reinit repaired it without duplicating the recorder |
| Missing session / newer store | Red regressions against `hook_main` | Broke; now denied instead of silence |
| Hook crash / timeout | Live Codex, marker written before each failure | Broke: both let the write happen; vendor boundary remains |
| Session predating init | Paused live Codex, ran init, resumed its patch | Broke: new hooks did not hold that session; restart required |
| Codex before this change | `graphene run --with codex --attempts 1` | Outside file remained in the task copy; finish refused, no merge |
| Codex after this change | Same fixture, captured native patch and shell payloads | Outside patch denied; no outside file; allowed file merged |
| Three attempts set on one task | Set forks=3 as the form does; three real Codex agents | All outside patches denied; all passed; c picked and merged |
| Human edits while a task runs | Shared-checkout replay; concurrent worktree/target test | Inside shared files counts as task work; outside refuses; human data preserved; conflicting merge waits in review |
| Empty work, passing check | `node done` path with `check=true`, no edits | Held: “nothing inside its scope … has changed” |
| Exact from a terminal | Replayed `exact.sh` with board auto and on | Still takes defaults; deliberately not changed |
| Form, attempts, approval, ownership | Engine-state probe; real Cursor draw walk | Held, including edits while an agent holds the task |
| Draft lifetime and duplicate refusals | Failing unit tests, Cursor sidebar/tab/close/window reload | Fixed: shared persisted drafts; one inline refusal |
| Home Start during planner completion | Live lost click, deterministic busy-host regression | Broke; Start now waits until the host accepts it |
| PR #60's tests | 27 controlled source mutations; both original editor walks mutated | One no-task test survived; strengthened; 27/27 plus 2/2 walks now catch mutations |

Fixes and their reproductions (each regression was red before its fix):

- `5c3d2fdc`: `uv run pytest -q tests/test_verify_gate.py` — missing path/session and unreadable/newer plan now fail closed.
- `5fc1c434`: `uv run pytest -q tests/test_codex_hooks.py` — init/remove preserve other hooks; patches check add/update/delete/move paths; run sessions match their hold; hooks reach worktrees. Captured payload replay: `08052206`.
- `55be045d`: `npm run draw` — drafts survive both graph views, closing the tab and reloading Cursor.
- `bf565fb7` / `26b8e62d`: form refusal appears once; displayed engine prose says task/files/attempts while commands, paths, CLI flags and JSON keys stay exact.
- `c4eb1c83` / `fcd76cbd`: Home waits through planner completion; Cursor's input selector no longer matches its checkbox.
- `e2bad9c1`: inherited Codex marks made 400 baseline tests fail, then four dev harness tests still failed. The root test fixture now isolates all test directories; no product identity rules were weakened.

Validation: `2,945 Python tests passed, 21 skipped, plus five subtests`; 137 extension tests plus typecheck/build and local VS Code smoke passed. Cursor `npm test`, `npm run home`, `npm run draw` passed; Home and Draw also passed in VS Code. Ruff and diff checks passed. Test/probe output and exact rerun commands are in `dev/process/verify/CHECKS.md`; `dev/process/verify/TRY_IT.md` gives Alex 15 manual steps.

Remaining boundaries: project and hook trust are required; the live automation explicitly trusted only its disposable fixtures. A hook that cannot start, crashes or times out can still fail open under the [Codex vendor contract](https://learn.chatgpt.com/docs/hooks). Unknown shell targets, scripts and MCP writes still need finish checks. Git cannot identify who typed an edit in a shared checkout. Neither Exact's engine acceptance rule nor snapshot fields were changed.

Housekeeping candidates for Alex, listed only; historical branches are not assumed safe to delete:

- #57 / `simple-editor`: Home is already in merged #58 and exercised by these walks.
- #55 / `night/editor`: its folded successor #56 is merged, and #60 builds on that editor.
- #42 / `meter`: current runs already show per-attempt usage and the run bill; review its remaining diff before closing.
- #35 / `first-light-full-history`: folded `first-light` shipped in #34; full history may still be an intentional archive.
- #32 / `shaping-full-history`: the current planner/board replaced that presentation; preserve archival intent until Alex decides.
- `night/editor-folded`, `night/feel`, `night/best-of`, `night/revamp`, `fix/ci-flakes`, `readme-after-hackathon`: their PRs #56/#48/#51/#53/#54/#59 are merged. This lists stale heads, not permission to remove them.

Defaults kept: Exact in the engine and additional snapshot fields remain unchanged, per brief. The missing branch was restored at Alex's explicit direction; this draft uses it as the base.

Skipped: live Claude reruns, Cursor/Copilot's own signed-in agents, and housekeeping changes.
Risk: hook trust/startup/failure policy and shared-checkout attribution still limit enforcement; the passing checks do not prove an arbitrary task is correct.
