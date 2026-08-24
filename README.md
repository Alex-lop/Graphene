<p align="center">
  <img src="docs/assets/Graphene_main_img.png" alt="Graphene" width="720">
</p>

# Graphene Taskmaster

[![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml)

Graphene is a terminal-native workflow playground for coding agents. It turns a goal into a proposed, commit-bound DAG; lets you reshape and approve one exact revision; gives each worker only the context and authority its node allows; shows the planned route, the actual path, and the next frontier; and produces a verified result.

You give it a goal. It proposes one mission DAG bound to an exact commit and stops, because a proposal is not a decision. You inspect any node in full, reshape the graph — add a node, rewire an edge, tighten a scope, change a check — and approve one exact revision. From that moment the approved revision is the contract: each worker gets only the context and authority its node allows, the dashboard shows the planned route against the actual path and the next frontier, and the result is verified before anything is committed.

Graphene is not a graph that merely looks good, and it is not a picture of the files an agent touched after the interesting work is over. **It is the place where you design how agents should work, and then watch your approved workflow run.** The proof engine underneath is what lets it make that promise honestly.

```bash
graphene plan "Add a status export to the ledger service" --repo PATH
graphene plan show MISSION_ID --detail          # the full contract of every node
graphene plan export MISSION_ID --output plan.yaml   # canonical YAML — edit it
graphene plan revise plan.yaml                  # -> immutable revision 2, new digest
graphene plan lint MISSION_ID                   # atomic: cycles, scopes, checks, budgets
graphene plan diff MISSION_ID 1 2               # what changed, and where a scope grew
graphene plan approve MISSION_ID --revision 2   # binds mission + base_sha + revision + digest
```

Approval binds four things at once: the mission, the `base_sha` the plan was written against, the revision number, and the plan's SHA-256. Change any one of them and the approval is void. Editing an approved plan produces immutable revision N+1 with a new digest that needs its own approval; editing after dispatch has begun fails closed; and no worker can claim a node of a revision nobody approved.

## What Graphene is not

Planning graphs are not new, and neither is repository mapping. Graphene's claim is narrower than either: the complete loop from proposal to a binding, executed revision.

- **Not a code-context layer.** Graft and Aider's RepoMap build maps of a codebase so an agent can find its way around. Graphene has no native code knowledge graph and does not compete with one — a context provider of that kind is a natural future *advisor to the planner*, never a replacement for the approved plan. Any performance figure attributed to Graft, here or anywhere else, is **reported by NanoNets** and is not measured by this project.
- **Not another task planner.** CoderMind, Beads, and Task Master also model agent work as a graph of tasks; they are adjacent neighbours, not strawmen. What Graphene adds is enforcement: one authoritative DAG per mission rather than one per agent, an approval bound to an exact digest, per-node read/write scopes and command allow-lists, fenced leases, trusted checks as the only completion authority, and a store that refuses to dispatch anything the approval does not cover.
- **Not a benchmark.** There is no leaderboard here, no token-efficiency claim, and no speed or cost comparison. `benchmarks/graph_economics.py` is a truth-labelled harness whose results are `NOT PROVEN`; until it produces data there is nothing to claim.
- **Not a security sandbox.** A Git worktree isolates edits. It is not a jail — see the safety boundary below.

**[What the latest implementation changed](docs/IMPLEMENTATION_REPORT.md)** · [Product](docs/PRODUCT.md) · [Architecture](docs/ARCHITECTURE.md) · [Documentation index](docs/README.md)

## See Mission Control in 30–60 seconds

```bash
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

The checked-in replay is SHA-256 verified, opens at checkpoint zero, and pauses at the fixture's pending final-candidate checkpoint. **Continue with recorded simulated approval** depicts a fixture branch with `human_attestation=false`; it runs nothing new and is not V2 bundle proof. No screenshot or GIF is presented because the in-app capture surface was unavailable. See [`demo-capture.json`](docs/assets/demo-capture.json).

## Live Gemini — proven on one mission, labelled exactly

```bash
uv run --frozen graphene mission demo

uv run --frozen graphene mission start \
  --repo PATH \
  --goal GOAL \
  --success-criterion CRITERION \
  --driver gemini-adk
```

The credential-gated path requests `gemini-3.5-flash`, proposes a typed DAG, and runs two to five bounded ADK workers after exact plan approval. Credential-free tests exercise the same orchestration with deterministic fake models, isolated workspaces, concurrent siblings, trusted checks, accepted-only fan-in, exact verification, and an unchanged source checkout.

On 2026-08-23 the North Star mission ran live against the `demo/north_star` target through Vertex AI (location `global`; `us-central1` does not serve this model for the project): two workers, three work attempts, assembly, exact verification, a registered `FinalResultBundleV2`, a bundle-bound approval, and an isolated local result commit — with every worker call bound into evidence as a sanitized provider receipt and the two renderer calls overlapping for 25–28 s on three independent bases. **What that run does not prove:** approvals were operator-delegated (`truth_kind: server_derived`) under a recorded standing instruction, not TTY-attested; the live failure laboratory and the cold capsule verification are separate claims. Every identifier, digest, and count is in [`evidence/north_star/2026-08-23-north-star-live.md`](evidence/north_star/2026-08-23-north-star-live.md); missing credentials still fail closed with no silent fallback. See [`docs/NORTH_STAR_RUNBOOK.md`](docs/NORTH_STAR_RUNBOOK.md) for the live-contact fixes this run required.

## Product loop

- Turn a goal, criteria, and deny-by-default `ProjectPolicy` into a validated immutable DAG.
- Dispatch only ready, non-conflicting tasks under owner-scoped leases and monotonic fences.
- Publish only independently measured, V2-enveloped artifacts; assemble and verify the exact tree.
- Pause on an immutable pre-decision bundle ID; rejection creates no commit, while approval creates only an isolated local result.

```text
goal + policy -> proposal -> deterministic validation -> durable mission store
                                                        |
                        Mission Control <- committed projection
                                                        |
              fenced work -> accepted artifacts -> assembly -> verification
                                                                  |
                                           reject OR isolated local result
```

The durable DAG is execution authority. Mission Control is a projection; authenticated commands delegate to the same canonical store.

## Proof and support

| Path | Status | What it establishes |
|---|---|---|
| `graphene mission replay taskmaster` | `VERIFIED_LOCAL` | Hash-checked fixture projection, replay, and UI semantics; not live execution |
| `scripted-local` mission | `VERIFIED_LOCAL` on macOS | Durable scheduler, overlapping fixture workers, retry, V2 publication fan-in, exact verification, bundle-bound decision, isolated result |
| Credential-free core | `VERIFIED_LOCAL` | SQLite authority/tamper checks, ownership/fencing, workspace audit, fake-ADK runtime, Mission Control commands, bounded 50-task/five-worker soak |
| Official Firestore emulator | `VERIFIED_LOCAL` | Production create/approve/readiness/claim/heartbeat/completion and sharded materialization/reconcile path |
| Live Gemini | `VERIFIED_LIVE` (2026-08-23) | Two `gemini-3.5-flash` workers on Vertex AI (`global`) completed the North Star mission `mission_start_5291caad50a8ee7a222a9221`: evidence-bound provider receipts, overlap on the store clock, the runtime call window, and the provider's own clock, exact verification, bundle-bound approval, isolated local result. Approval was operator-delegated (`server_derived`), not human-attested. [Evidence](evidence/north_star/2026-08-23-north-star-live.md) |
| Planning source binding | `VERIFIED_LOCAL` | Planning reads the manifest and excerpt bytes out of `base_sha` via `git ls-tree`/`cat-file`, never off disk, so the planner sees exactly what the workers clone; tracked or staged drift is rejected by name and the intermediate-symlink escape is gone by construction |
| Final bundle authority | `VERIFIED_LOCAL` | The store refuses to register a final result bundle unless a repository-aware recompute is bound and agrees, and issues its own verification receipt that approval, rejection and cold verification all require |
| Failure-aware retry | `VERIFIED_LIVE` (2026-08-23) | A failed trusted check leaves a redacted structured diagnostic; the retry's prompt carries the prior attempt id, fence, result code, failed check names and receipt digest with an unchanged repair scope; a repeated identical failure signature terminalizes instead of taking a blind third attempt — both directions observed live |
| Docker executor | `NOT PROVEN` | Requires a responsive-daemon smoke |
| Cloud Run + real Firestore | `NOT DEPLOYED — NOT PROVEN` | Packaging/emulator proof is not authenticated deployment proof. Nothing was enabled or created: the required APIs are disabled on the configured project, and the project is a Gemini-API auto-created one rather than the dedicated sandbox the setup guide requires, so the owner chooses the project first |
| Firestore single-executor vertical | `VERIFIED_LOCAL` on the official emulator | Seed → register → claim → heartbeat → **successful** completion with a real check receipt, the event chain recomputed from seq 1, and the sharded materialization invariants intact. Abandon is disabled (501) and a second concurrent executor is refused (409); cloud parallelism is not claimed anywhere |
| Cloud check authority | `EXECUTOR_ATTESTED` | The coordinator recomputes a receipt's bindings, not its test results, so an authenticated remote executor is inside the trusted computing base. Every successful cloud completion records `check_authority: executor_attested` in the hash chain. A cloud smoke never inherits the local `trusted_check` claim |
| Benchmark/video/media | `NOT PROVEN` | Harness/runbook/capture metadata exist; results and media do not |
| Shadow Agent, ndjson path | `VERIFIED_LOCAL` on a synthetic fixture | Canonical events, isolated store, fail-closed adapter, reconstruction, six lint rules, self-verifying capsule |
| Shadow Agent, claude-code adapter | `VERIFIED_LOCAL` on a synthetic fixture | Record-shape mapping, Bash classification, path and content digests, redaction, fail-closed rules, reconstruction, lint, capsule |
| Shadow Agent, real Claude Code session | `NOT PROVEN` (private smoke only) | One real 110-record transcript ingested with zero unknown records and report and lint ran; counts only in the contract, the transcript is private and the run is not reproducible from the repository |
| Mission capsule | `VERIFIED_LIVE_COLD` (2026-08-23) | Capsules of the completed live mission and the live failure-lab mission verify from a fresh clone with no mission store (11 checks each); not producer authenticity, same laptop |
| North Star | `VERIFIED_LIVE` (2026-08-23) | Two real workers, survives one failing *and completes*, and `why` chains — all live. Completion gate: **9/10 ordinary** and **3/3 controlled-failure** missions finished end to end, $2.30 of receipt-derived spend across 14 missions. The controlled failure is `--inject-check-fault`, an owned check process failed on purpose with a `simulated_fixture` receipt — not a real infrastructure failure. The night's SIGKILL laboratory remains the real-process variant and its completion leg is unchanged. [Evidence](evidence/convergence/2026-08-23-completion-gate/README.md) |

Machine-readable truth lives in [`contracts/product_proof.json`](contracts/product_proof.json).

## Shadow Agent

> **"Your agent said the tests passed. Graphene knows whether they actually ran."**

Code review for agent sessions Graphene did not run. Point it at a finished transcript: Graphene reconstructs the session as inferred segments with a read-after-write graph, lints it for claims without checks, edits without checks, overlapping writes, scope drift, unverified deletes, and network or install activity, and exports a redacted capsule that verifies from its own bytes.

```bash
graphene shadow ingest PATH --format claude-code|ndjson [--repo PATH]   # -> shadow_id
graphene shadow report SHADOW_ID [--json]
graphene shadow lint   SHADOW_ID [--rule RULE ...] [--json]
graphene shadow graph  SHADOW_ID --json|--dot
graphene shadow export SHADOW_ID --output DIR               # -> SHADOW_ID.graphene-shadow capsule
```

`graphene shadow list` and `graphene shadow verify SHADOW_ID` enumerate and re-verify stored sessions. Shadow data lives in its own `shadow.sqlite3` with its own schema ledger: `graphene shadow` never opens the mission store, and nothing in the mission trust chain ever cites a shadow record. Every reconstruction is labeled `inferred`, and there is no trust score. See [Shadow Agent](docs/SHADOW.md) and the [adapter specification](docs/SHADOW_ADAPTER_SPEC.md).

Shadow Agent v0: credential-free tests pass on the synthetic ndjson and claude-code fixtures. The claude-code adapter was built against one real Claude Code transcript that stays private; it ingested with zero unknown records in a smoke whose counts are in the contract, so the real-session report remains NOT PROVEN and source faithfulness is never claimed.

## Safety boundary

- `graphene init` writes a narrow policy template; review every scope and exact argv-form command.
- A Git worktree provides edit isolation. **It is not a security sandbox.** Unsupported execution fails closed.
- Workers have no arbitrary shell, installer, ambient credential, user-checkout mount, or autonomous push/PR/merge/deploy path.
- Public state excludes raw prompts, source, diffs, command arguments/output, environment variables, secrets, and chain-of-thought.
- Skills are not resource-isolation units. Stateless MCP is sessionless, not processless.
- Cancellation targets only strongly identified Graphene-owned processes; unreceipted external effects become `outcome_unknown`, never silently repeated. A cancelled attempt records the stages it completed in its evidence chain, so a check that had already passed is not lost in the word "cancelled".
- Two tasks may not write the same file, and that rule holds even when one depends on the other: an ordered ownership transfer is safe in principle but is still refused. See [Known limitations](docs/KNOWN_LIMITATIONS.md).

See [Security and sovereignty](docs/SECURITY_AND_SOVEREIGNTY.md) and the [Taskmaster product contract](docs/TASKMASTER_PRODUCT_CONTRACT.md).

## Scripted fixture and final result

The executable fixture requires macOS, Python 3.13, Git, `uv`, and `/usr/bin/sandbox-exec`.

> **SCRIPTED LOCAL MISSION FIXTURE — NOT GEMINI, ARBITRARY-REPOSITORY, OR CLOUD PROOF**

```bash
uv run --frozen graphene init --repo /path/to/disposable-repo
uv run --frozen graphene mission start --repo /path/to/disposable-repo \
  --goal "Add redacted JSON and Markdown status reports." --driver scripted-local
uv run --frozen graphene mission approve-plan MISSION_ID --revision 1
```

The default scripted start commits a validated proposal. An interactive TTY may attest approval; `--auto-approve` is always `simulated_fixture`. Execution stops at `awaiting_result` after registering a canonical pending `FinalResultBundleV2`.

Use `graphene mission result show MISSION_ID` to verify the candidate. Use `graphene mission approve-result MISSION_ID --bundle-id FINAL_RESULT_ID` or `graphene mission reject-result MISSION_ID --bundle-id FINAL_RESULT_ID`; both bind the exact bundle. `graphene mission result export ...` and `graphene bundle create/verify` write only create-new mode-`0600` review artifacts and never mutate the checkout. `graphene mission capsule export MISSION_ID --output DIR` writes a private `MISSION_ID.graphene-capsule` directory holding the hash-chained mission events, every attempt's evidence chain, trusted check and sanitized worker receipts, publication envelope digests, plan revisions, and the registered final bundle, with no prompts, source bytes, diffs, or command output, and `graphene mission capsule verify CAPSULE_DIR` recomputes every digest and chain link from those files alone without opening the mission store.

## Command map

Taskmaster entrypoints: `graphene init`, `graphene doctor`, `graphene plan`, `graphene status`, `graphene bundle`, `graphene cancel`, `graphene mission`, `graphene request-replan`, `graphene retry`, `graphene run`, `graphene task`, `graphene watch`, `graphene why`. The compatibility-only Auth tour commands remain: `graphene inspect`, `graphene replay`, `graphene review`, `graphene feedback`, `graphene answer`, `graphene memory`, `graphene handoff`, `graphene promote`, `graphene demo`.

```bash
graphene plan GOAL --repo PATH --success-criterion CRITERION
graphene plan show MISSION_ID [--detail]
graphene plan export MISSION_ID [--output FILE]
graphene plan revise EDITED_PLAN_FILE
graphene plan edit MISSION_ID
graphene plan diff MISSION_ID PREVIOUS_REVISION REVISION
graphene plan lint MISSION_ID
graphene plan approve MISSION_ID --revision N
graphene run MISSION_ID
graphene task input MISSION_ID TASK_ID --gate GATE_ID --file INPUT_FILE
graphene bundle verify FINAL_RESULT_ID
```

Mission commands: `graphene mission start`, `graphene mission status`, `graphene mission watch`, `graphene mission open`, `graphene mission pause`, `graphene mission resume`, `graphene mission cancel`, `graphene mission retry`, `graphene mission request-replan`, `graphene mission approve-plan`, `graphene mission decide-gate`, `graphene mission approve-result`, `graphene mission reject-result`, `graphene mission result`, `graphene mission capsule`, `graphene mission db`, `graphene mission replay`, `graphene mission demo`, and `graphene mission executor`.

`graphene plan show/diff/lint` reads verified revisions. `plan export` writes the canonical YAML a person edits, `plan revise` compiles the edited file into immutable revision N+1, and `plan edit` is a thin `$EDITOR` wrapper over exactly that path — there is no second way to change a plan. `request-replan` still only pauses dispatch and records the request: it generates no linked replacement revision, and nothing in Graphene asks a model to produce one. The revision a `revise` compiles is the user's, not the planner's. `graphene task input` accepts 1–4096 private UTF-8 bytes from a regular file or stdin and commits only their evidence reference. The browser-input seam is tested but hidden in one-command live mode because no safe staged-input cleanup API is wired. Automatic expiry and purge are not implemented. Current mission-plan validation rejects `legacy_auth_v2`. Cloud streaming uses per-client polling; there is no shared listener or fan-out.

The outbound surface is `graphene mission executor connect --repo PATH --mission MISSION_ID --coordinator-url URL --audience AUDIENCE --workers 2`. It touches local workspaces; Cloud Run does not.

## Watching for a change

> **WATCHER — VERIFIED_LOCAL ON FIXTURES; LIVE GITHUB POLLING NOT PROVEN**

```bash
graphene watch inbox --dir PATH [--once] [--poll 5]
graphene watch github --repo OWNER/NAME --label graphene-mission --target-repo PATH --driver DRIVER [--once] [--poll 60] [--state PATH]
```

A `*.yaml` dropped in the inbox (`goal`, `repo`, `driver`, optional `success_criteria`, `max_workers`, `policy`; `yaml.safe_load`, 64 KiB, unknown keys rejected) or an open issue carrying the label creates one proposed mission through the same `mission start` path and commits a `mission.triggered` annotation (`source_kind`, `source_ref`, `source_url`, `source_sha256`, `observed_at`, `watcher_id`) that `graphene why` lists as the first stage. The watcher only creates; plan approval stays with the operator. Rejections become `rejected/<name>.result.json` sidecars or state-file entries, never missions; identical content and already-seen issue ids trigger exactly once. GitHub polling is read-only `urllib` with `ETag`/`If-None-Match`, exponential backoff on rate limits, an optional `GITHUB_TOKEN`/`GRAPHENE_GITHUB_TOKEN` that is never printed or stored, and it refuses the network unless `GRAPHENE_WATCH_GITHUB_LIVE=1`. Fixture tests cover both paths; no live GitHub poll has been run. Live on 2026-08-23: a dropped `mission.yaml` created `mission_start_a44dcefd7cd8e79e25690611` through the watcher, the (delegated) approval ran two live Gemini workers, and `graphene why` on a file they produced starts at `STAGE trigger` — see [`evidence/north_star/2026-08-23-trigger-demo/`](evidence/north_star/2026-08-23-trigger-demo/); that mission later failed on the model's own output, so no verified result followed the trigger yet.

## Documentation

[Product](docs/PRODUCT.md) · [Architecture](docs/ARCHITECTURE.md) · [Agent runtime](docs/AGENT_RUNTIME.md) · [Security](docs/SECURITY_AND_SOVEREIGNTY.md) · [Firestore/cloud](docs/FIRESTORE_AND_CLOUD.md) · [Alex cloud setup](docs/ALEX_CLOUD_SETUP.md) · [Mission Control](docs/MISSION_CONTROL.md) · [Demo guide](docs/DEMO_GUIDE.md) · [Known limitations](docs/KNOWN_LIMITATIONS.md) · [Development](docs/DEVELOPMENT.md)

CI lives in [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Final commands, counts, skips, and proof distinctions live in the [implementation report](docs/IMPLEMENTATION_REPORT.md).
