# Proof — what is proven, what is not

Every public claim Graphene makes maps to a row here and to a label in
[`contracts/product_proof.json`](../contracts/product_proof.json), the
machine-readable truth. Labels only change in the same commit as a check that
can fail. Where a session report and this page disagree, the contract wins.

## The table

| Path | Status | What it establishes |
|---|---|---|
| `graphene mission replay taskmaster` | `VERIFIED_LOCAL` | Hash-checked fixture projection, replay, and UI semantics; not live execution |
| `scripted-local` mission | `VERIFIED_LOCAL` on macOS | Durable scheduler, overlapping fixture workers, retry, V2 publication fan-in, exact verification, bundle-bound decision, isolated result |
| Credential-free core | `VERIFIED_LOCAL` | SQLite authority/tamper checks, ownership/fencing, workspace audit, fake-ADK runtime, Mission Control commands, bounded 50-task/five-worker soak |
| Official Firestore emulator | `VERIFIED_LOCAL` | Production create/approve/readiness/claim/heartbeat/completion and sharded materialization/reconcile path |
| Live Gemini | `VERIFIED_LIVE` (2026-08-23) | Two `gemini-3.5-flash` workers on Vertex AI (`global`) completed the North Star mission `mission_start_5291caad50a8ee7a222a9221`: evidence-bound provider receipts, overlap on the store clock, the runtime call window, and the provider's own clock, exact verification, bundle-bound approval, isolated local result. Approval was operator-delegated (`server_derived`), not human-attested. [Evidence](../evidence/north_star/2026-08-23-north-star-live.md) |
| Planning source binding | `VERIFIED_LOCAL` | Planning reads the manifest and excerpt bytes out of `base_sha` via `git ls-tree`/`cat-file`, never off disk, so the planner sees exactly what the workers clone; tracked or staged drift is rejected by name and the intermediate-symlink escape is gone by construction |
| Final bundle authority | `VERIFIED_LOCAL` | The store refuses to register a final result bundle unless a repository-aware recompute is bound and agrees, and issues its own verification receipt that approval, rejection and cold verification all require |
| Failure-aware retry | `VERIFIED_LIVE` (2026-08-23) | A failed trusted check leaves a redacted structured diagnostic; the retry's prompt carries the prior attempt id, fence, result code, failed check names and receipt digest with an unchanged repair scope; a repeated identical failure signature terminalizes instead of taking a blind third attempt — both directions observed live |
| Docker executor | `NOT PROVEN` | Requires a responsive-daemon smoke |
| Cloud Run + real Firestore | `NOT DEPLOYED — NOT PROVEN` | Packaging/emulator proof is not authenticated deployment proof. Nothing was enabled or created: the required APIs are disabled on the configured project, and the project is a Gemini-API auto-created one rather than the dedicated sandbox the setup guide requires, so the owner chooses the project first |
| Firestore single-executor vertical | `VERIFIED_LOCAL` on the official emulator | Seed → register → claim → heartbeat → **successful** completion with a real check receipt, the event chain recomputed from seq 1, and the sharded materialization invariants intact. Abandon is disabled (501) and a second concurrent executor is refused (409); cloud parallelism is not claimed anywhere |
| Cloud check authority | `EXECUTOR_ATTESTED` | The coordinator recomputes a receipt's bindings, not its test results, so an authenticated remote executor is inside the trusted computing base. Every successful cloud completion records `check_authority: executor_attested` in the hash chain. A cloud smoke never inherits the local `trusted_check` claim |
| Graph economics benchmark | `NOT PROVEN` | The harness has a credential-free unit test and a written deferral ([`benchmarks/DEFERRAL.md`](../benchmarks/DEFERRAL.md)). No repeated run, token/cost/latency result, median or P95 is claimed |
| Product media and submission video | `NOT PROVEN — CAPTURE PENDING` | `docs/assets/demo-capture.json` records the verified replay source and checkpoint; the required hero screenshot and replay GIF do not exist, and nothing has been filmed. The live sequence those media would show is separately rehearsed — see below |
| Terminal UI (`graphene ui`) | `VERIFIED_LOCAL` (2026-08-26) | The verified replay renders as a top-to-bottom DAG with box-drawing edges, per-node state, and a banner carrying mission id, plan revision, digest, and signed/unsigned state; the viewer attaches read-only (SQLite `mode=ro`, `query_only=ON`) and node states change on screen while a scripted-local mission runs ([evidence](../evidence/ui/2026-08-26/README.md)); drill-in and summary panes are built from the store and snapshot-tested (`tests/unit/ui`). Not a live model mission, not filmed; on Linux the replay path is proven in the pinned image (CI's Linux job runs `tests/unit/ui` and the replay render; the live-attach test needs macOS) |
| The `/graphene` loop over MCP | `VERIFIED_LOCAL` (2026-08-26) | `graphene-mcp` over stdio, driven by the official MCP client: six tools and the `goal` prompt, `approve_plan` refusing a forged digest and honouring the shown one, execution inside the signed map on the scripted fixture, summary and lineage from the store, `graphene ui` attached in a second process — end to end on a fresh clone of this repository ([evidence](../evidence/integration/2026-08-26/transcript.md), 14/14 beats). Codex and Gemini CLI blocks are documented against their current docs, not driven; no person has signed in a chat client; no live model mission ran under MCP |
| Mission capsule | `VERIFIED_LIVE_COLD` (2026-08-23) | Capsules of the completed live mission and the live failure-lab mission verify from a fresh clone with no mission store (11 checks each); not producer authenticity, same laptop |
| North Star | `VERIFIED_LIVE` (2026-08-23) | Two real workers, survives one failing *and completes*, and `why` chains — all live. Completion gate: **9/10 ordinary** and **3/3 controlled-failure** missions finished end to end, $2.30 of receipt-derived spend across 14 missions. The controlled failure is `--inject-check-fault`, an owned check process failed on purpose with a `simulated_fixture` receipt — not a real infrastructure failure. [Evidence](../evidence/convergence/2026-08-23-completion-gate/README.md) |

## The verified replay (the quickstart)

```bash
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

The checked-in replay is SHA-256 verified, opens at checkpoint zero, and pauses
at the fixture's pending final-candidate checkpoint. **Continue with recorded
simulated approval** depicts a fixture branch with `human_attestation=false`;
it runs nothing new and is not V2 bundle proof. See
[`demo-capture.json`](assets/demo-capture.json).

Cold verification of the README quickstart, 2026-08-26, in a fresh
`python:3.13-slim` container with nothing but `git` and `uv` installed: the
three commands were run verbatim; the timing and exit status are recorded in
the [goal-run report](reports/2026-08-26-goal-run.md). A container has no
browser, so the replay served Mission Control and was stopped by a timeout
rather than by a person closing it.

## Live Gemini — proven on one mission, labelled exactly

```bash
uv run --frozen graphene mission demo

uv run --frozen graphene mission start \
  --repo PATH \
  --goal GOAL \
  --success-criterion CRITERION \
  --driver gemini-adk
```

The credential-gated path requests `gemini-3.5-flash`, proposes a typed DAG,
and runs two to five bounded ADK workers after exact plan approval.
Credential-free tests exercise the same orchestration with deterministic fake
models, isolated workspaces, concurrent siblings, trusted checks, accepted-only
fan-in, exact verification, and an unchanged source checkout.

On 2026-08-23 the North Star mission ran live against the `demo/north_star`
target through Vertex AI (location `global`; `us-central1` does not serve this
model for the project): two workers, three work attempts, assembly, exact
verification, a registered `FinalResultBundleV2`, a bundle-bound approval, and
an isolated local result commit — with every worker call bound into evidence as
a sanitized provider receipt and the two renderer calls overlapping for 25–28 s
on three independent bases. **What that run does not prove:** approvals were
operator-delegated (`truth_kind: server_derived`) under a recorded standing
instruction, not TTY-attested; the live failure laboratory and the cold capsule
verification are separate claims. Every identifier, digest, and count is in
[`evidence/north_star/2026-08-23-north-star-live.md`](../evidence/north_star/2026-08-23-north-star-live.md);
missing credentials still fail closed with no silent fallback. See
[`NORTH_STAR_RUNBOOK.md`](NORTH_STAR_RUNBOOK.md) for the live-contact fixes
this run required.

`graphene demo --live` runs that whole path as one continuous sequence —
trigger, bounded plan, a node's full contract, an edit that compiles revision
2, lint, diff, approval of the exact digest, two live workers, an injected
check fault and its fenced retry, the isolated result, and `why`. It has run
end to end and then three consecutive clean rehearsals, all exit 0
([evidence](../evidence/contract/2026-08-24-rehearsals/README.md)), and one
run was timed end to end at **77 seconds** with the edit applied by a script.
The script is [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) and the beat-by-beat shot
list is [`SHOT_LIST.md`](SHOT_LIST.md).

**What the rehearsals cover, and what they cannot:** the four runs of
2026-08-24 applied the plan edit with `--plan-edit FILE`; on 2026-08-25 three
consecutive runs took the interactive pause instead — the prompt a person types
into — with a scripted operator editing the export and pressing Enter
([evidence](../evidence/contract/2026-08-25-rehearsals/README.md)), all exit 0,
69–90 s each. What no rehearsal can cover is the person: the time a human takes
to type the edit is unmeasured. The submission video remains `NOT PROVEN` —
nothing has been recorded.

## Scripted fixture and final result

The executable fixture requires macOS, Python 3.13, Git, `uv`, and
`/usr/bin/sandbox-exec`.

> **SCRIPTED LOCAL MISSION FIXTURE — NOT GEMINI, ARBITRARY-REPOSITORY, OR CLOUD PROOF**

```bash
uv run --frozen graphene init --repo /path/to/disposable-repo
uv run --frozen graphene mission start --repo /path/to/disposable-repo \
  --goal "Add redacted JSON and Markdown status reports." --driver scripted-local
uv run --frozen graphene mission approve-plan MISSION_ID --revision 1
```

The default scripted start commits a validated proposal. An interactive TTY may
attest approval; `--auto-approve` is always `simulated_fixture`. Execution stops
at `awaiting_result` after registering a canonical pending
`FinalResultBundleV2`. The result and capsule commands are in the
[command map](COMMANDS.md).

## Watching for a change

> **WATCHER — VERIFIED_LOCAL ON FIXTURES; LIVE GITHUB POLLING NOT PROVEN**

A `*.yaml` dropped in the inbox (`goal`, `repo`, `driver`, optional
`success_criteria`, `max_workers`, `policy`; `yaml.safe_load`, 64 KiB, unknown
keys rejected) or an open issue carrying the label creates one proposed mission
through the same `mission start` path and commits a `mission.triggered`
annotation (`source_kind`, `source_ref`, `source_url`, `source_sha256`,
`observed_at`, `watcher_id`) that `graphene why` lists as the first stage.
Rejections become `rejected/<name>.result.json` sidecars or state-file entries,
never missions; identical content and already-seen issue ids trigger exactly
once. GitHub polling is read-only `urllib` with `ETag`/`If-None-Match`,
exponential backoff on rate limits, an optional
`GITHUB_TOKEN`/`GRAPHENE_GITHUB_TOKEN` that is never printed or stored, and it
refuses the network unless `GRAPHENE_WATCH_GITHUB_LIVE=1`. Fixture tests cover
both paths; no live GitHub poll has been run. Live on 2026-08-23: a dropped
`mission.yaml` created `mission_start_a44dcefd7cd8e79e25690611` through the
watcher, the (delegated) approval ran two live Gemini workers, and
`graphene why` on a file they produced starts at `STAGE trigger` — see
[`evidence/north_star/2026-08-23-trigger-demo/`](../evidence/north_star/2026-08-23-trigger-demo/);
that mission later failed on the model's own output, so no verified result
followed the trigger yet.

## Platform

macOS is where every live path above was proven; the scripted fixture needs
`/usr/bin/sandbox-exec`. On Linux, CI proves the verified replay, the
fail-closed executor boundary, and owned-process control inside the pinned
`python:3.13-slim` image (`scripts/linux_parity_check.sh`). `plan`, `why`, and
capsule verification are the same pure-Python code on both, but no Linux run of
them is recorded, so they are not labelled proven there.

The credential-free unit, integration, process, and adversarial suites, the
locked `ruff`, and both parity checks gate every push. CI lives in
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml); the change/proof
ledger is the [implementation report](IMPLEMENTATION_REPORT.md).
