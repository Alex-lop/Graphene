# Taskmaster Ultra implementation report

Status: implementation committed and the credential-free release matrix is green on
the exact source commit recorded below. This truth update changes documentation and
machine-readable proof only and is verified separately.

## Commit range

- Reviewed start: `b3223fb310a4f7b3825f9dc4a4b84dbb7c7a23f5`
- Verified source commit: `581d6bf4e1c2ba4810f16d93b295637c7203a7b5`
- Compare link: `https://github.com/Alex-lop/Graphene/compare/b3223fb310a4f7b3825f9dc4a4b84dbb7c7a23f5...581d6bf4e1c2ba4810f16d93b295637c7203a7b5`
- Final report/release SHA: recorded in the terminal handoff; a commit cannot embed its own SHA.

## Product and architecture decisions

- One product: local-first mission control for one bounded coding outcome, with two-to-five worker capacity.
- Immutable contracts, hash-chained events, content-addressed records, and their committed state root form authority. Browser state is a projection.
- Models propose and perform scoped work; deterministic validation, leases/fences, workspace audit, checks, assembly, and verification control acceptance.
- Successful publications require `ArtifactEnvelopeV2`. Exact verification produces an immutable pending `FinalResultBundleV2`; display, approval, rejection, and restart recovery bind its bundle ID.
- Work and result commits remain inside Graphene-owned, symlink-safe, remoteless repositories. No autonomous push, PR, merge, deployment, or user-checkout mutation was added.
- Replay, deterministic fake ADK, live Gemini, emulator, Docker, and real cloud proof remain separate claims.

## Changes by area

| Area | Implemented | Current proof boundary |
|---|---|---|
| Runtime | Bounded manifest/excerpts, typed `PlanIntent`, distinct ADK planner/workers, operation journal, trusted scoped tools/checks, completion-order coordination, accepted-only fan-in, deterministic assembly/verification, typed terminal cleanup | Fake-model ADK and deterministic tests here; live Gemini is proven separately and is **VERIFIED_LIVE** (2026-08-23) |
| Scheduler/processes | Owner/capability-scoped claim and recovery, exact lease/fence validation, sibling-independent completions, retries with higher fences, bounded polling, durable owned-process registry, cleanup-before-cancel | Local deterministic and adversarial proof; responsive Docker smoke absent |
| Evidence/SQLite | Schema ledger, immutable canonical records and state roots, exhaustive materialized-row comparison, artifact-byte verification, sticky read quarantine, `graphene.tree.v2`, V2 publication envelopes, exact pending final bundle | Local/adversarial tests; v1 is never silently reinterpreted or migrated |
| Human control | Expected-head idempotent plan/gate/pause/resume/retry/cancel commands, CLI private `needs_input`, request-replan pause, bundle-ID-bound final decisions, restart-safe isolated commit | Browser input seam is tested but hidden pending safe staged cleanup; live capture absent |
| Firestore/cloud | Five bounded state shards plus root, schema compatibility, atomic create/approve/readiness/claim/heartbeat/completion/outbox/locality, reconciliation, private multi-mission coordinator image, OIDC client, outbound executor | Official emulator production path verified; real project/deployment **NOT PROVEN** |
| Mission Control | Five-second summary, DAG/task evidence, pending-bundle decision, shared CLI/browser finalizer, authenticated CSRF/origin/current-head command plane, sticky quarantine, checkpoint-zero replay | Python/Node/replay tests; screenshot/GIF/browser capture unavailable |
| CLI | `plan/show/diff/lint`, `run/status/watch/why`, top-level cancel/retry/request-replan/task input, mission demo/executor, result show/export, bundle create/verify, v2 DB status/verify/dry-run | Credential-free parser/process tests; live provider/cloud commands remain opt-in |
| Docs/proof | Concise README, focused docs, owner cloud checklist, environment names, machine-readable proof, capture blocker | Relative links/JSON/truth tests plus the final counts/fingerprint below |

## Important implementation files

- [`../backend/graphene/orchestration/runtime.py`](../backend/graphene/orchestration/runtime.py), [`runner.py`](../backend/graphene/orchestration/runner.py), and [`workers/`](../backend/graphene/orchestration/workers/) — bounded worker effects, identities, recovery, and coordination.
- [`../backend/graphene/orchestration/store.py`](../backend/graphene/orchestration/store.py), [`materialized_integrity.py`](../backend/graphene/orchestration/materialized_integrity.py), and [`evidence.py`](../backend/graphene/orchestration/evidence.py) — SQLite authority and private evidence.
- [`../backend/graphene/artifact_envelope.py`](../backend/graphene/artifact_envelope.py), [`final_bundle.py`](../backend/graphene/orchestration/final_bundle.py), and [`local_result.py`](../backend/graphene/orchestration/local_result.py) — V2 publication and exact final-decision chain.
- [`../backend/graphene/orchestration/firestore.py`](../backend/graphene/orchestration/firestore.py), [`coordinator.py`](../backend/graphene/orchestration/coordinator.py), and [`executor_client.py`](../backend/graphene/orchestration/executor_client.py) — cloud vertical and outbound execution.
- [`../backend/graphene/orchestration/mission_control.py`](../backend/graphene/orchestration/mission_control.py) and [`../backend/graphene/cli/mission.py`](../backend/graphene/cli/mission.py) — shared operator/result paths.

## Migrations and compatibility

SQLite v2 uses `PRAGMA user_version=2` plus a verified schema ledger. Unknown/newer or altered schemas fail closed. `db migrate --dry-run` recommends verified export and a new v2 store; it never rewrites active v1 data. Tree identities use the explicit `graphene.tree.v2` domain. The legacy Auth lineage/viewer tour stays separate, and current mission validation rejects `legacy_auth_v2`.

Firestore uses a namespace schema document with current/minimum reader/writer versions. State is an immutable root over five capped shards, not one near-limit document. Reconciliation repairs only a pending materialized pointer from a contiguous canonical head.

## Verification ledger

Baseline before implementation:

| Gate | Result |
|---|---|
| Python unit/integration/process/adversarial excluding MCP | **514 passed, 2 skipped** |
| MCP STDIO | **6 passed** |
| Frontend | **38 passed** |
| Lock/replay generation | Clean |

Current non-final targeted evidence:

| Gate | Result |
|---|---|
| Official Firestore Emulator + real Google client production path | **3 passed** |
| Deterministic SQLite soak | **50 tasks, 5 workers, 50 accepted publications, awaiting_result, full verify; 23.07 s pytest / 23.68 s wall** |
| Cloud unit/protocol matrix | **62 passed, 2 opt-in live skips** |
| V2 artifact/final-bundle focus | **26 passed** |
| Pre-freeze diagnostic Python matrix | **801 passed, 4 skipped, 4 failed** on the moving tree; all four exact nodes then passed focused reruns and the stable final matrix below |
| Frontend combined matrix | **39 passed** after the bundle-ID Mission Control update |
| MCP STDIO | **6 passed** |
| Replay check/smoke | Green at replay SHA-256 `1dcc4d6d7e70d34d01574fec8227a49750c9aa7821023209bc7d7445094e17dd` |
| Final docs/readme/contracts/CI/Taskmaster CLI contract | **99 passed, 4 dependency warnings** |

Final credential-free release gates:

| Gate | Final result |
|---|---|
| Verified executable source | Git commit `581d6bf4e1c2ba4810f16d93b295637c7203a7b5`; production, test, and config files stayed unchanged throughout; post-run edits are docs/proof only |
| `uv lock --check` / `uv sync --frozen` | Passed; 73 packages resolved and 69 checked |
| Full Python matrix excluding MCP | **808 passed, 4 skipped, 0 failed**, 5 upstream warnings, 265.61 s |
| MCP STDIO | **6 passed**, 15.55 s |
| Frontend tests and seven JS syntax checks | **39 passed** (8 + 31); all syntax checks passed |
| Replay generator check and CLI smoke | Passed at replay SHA-256 `1dcc4d6d7e70d34d01574fec8227a49750c9aa7821023209bc7d7445094e17dd` |
| Ruff / compileall / `git diff --check` | Passed on the source commit; docs links and JSON passed after this truth update |
| Official emulator rerun after freeze | **3 passed**, 1.00 s; the aggregate matrix intentionally kept this exact opt-in test skipped |

Credential gates:

| Claim | Status |
|---|---|
| Full two-worker Gemini mission | **VERIFIED_LIVE** (2026-08-23): returned model/session/invocation receipts and measured overlap were captured; see `evidence/north_star/2026-08-23-north-star-live.md` |
| Docker execution | **NOT RUN on a responsive daemon — NOT PROVEN** |
| Cloud Run + real Firestore | **NOT DEPLOYED — NOT PROVEN — ALEX ACTION REQUIRED** |
| Graph-economics benchmark result | **NOT RUN — NOT PROVEN**; harness tests do not establish cost/latency/quality |
| Screenshot/GIF/four-minute video | **NOT CAPTURED — NOT PROVEN**; no mock or fallback renderer was used |

## Firestore scope that remains unsupported

The emulator proves the production vertical, not complete SQLite parity. `FirestoreMissionStore` still does not implement these `SchedulerStore` mutations: `register_worker`, `revoke_worker`, `expire_leases`, `enter_awaiting_result`, generic `claim_task`, generic `heartbeat`, generic `complete_attempt`, `pause`, `resume`, or `cancel`. Gate/input/retry/replan/final-result parity and the full shared state-machine corpus remain future work. Artifact bytes remain in the owning executor's private spool; cross-executor transfer is unsupported.

## Alex actions still required

Follow [Alex cloud setup](ALEX_CLOUD_SETUP.md) only after deliberately selecting project, billing, region, database, service identities, budget, and max-instance limit. Then opt in separately to live Gemini, live Firestore/cloud, and Docker proof. Capture only sanitized service revision, mission head, returned provider identity/usage, and Mission Control truth state—never credentials, prompts, private source, or artifact bytes.

## Known limitations

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). Remaining product gaps are live provider/cloud/Docker proof, full Firestore scheduler parity, operator-complete replanning, transitive artifact subsumption, broader mutation/repository support, automatic retention purge, shared cloud stream fan-out, product media/video, benchmark results, and the comprehension study.

## 2026-08-22 update: Shadow Agent v0 and North Star groundwork

This update is recorded on top of the verified source commit above; it does not re-verify that commit. Commit range: `7b41d58` (shadow schema) through the docs commit that follows this report.

| Area | Implemented | Current proof boundary |
|---|---|---|
| Shadow Agent | `shadow.event.v1` canonical identities, ingest-time redaction, isolated `shadow.sqlite3`, ndjson adapter with every documented fail-closed rule, `segments.v1`, `claims.v1` with precision locks, the six `lint.v1` rules and three defined ratios, `graphene shadow` CLI, self-verifying capsule | Synthetic fixture and hand-built records only; **claude-code adapter NOT IMPLEMENTED** pending a real transcript; source faithfulness never claimed |
| Worker receipts | Sanitized `worker-provider-receipt` artifacts bound to attempt evidence on success and failure; replay rebuilds them from evidence; live output lists only evidence-bound receipts | Fake ADK workers here; live Gemini receipts are **VERIFIED_LIVE** (2026-08-23) and are what the North Star evidence cites |
| Overlap | Attempt-lifetime, lease, and provider-call bases from evidence receipts; serialized execution proven to disagree with lifetimes | Fake workers; live provider-call overlap **NOT PROVEN** |
| Check executors | `GRAPHENE_CHECK_EXECUTOR=host-sandbox` (macOS `sandbox-exec`, owned-process registration, template timeout honoured, exec-in-place identity) beside Docker; upfront fail-closed selection on both the local and outbound paths | Docker smoke still **NOT PROVEN** on a responsive daemon |
| Failure laboratory | SIGKILL of worker B's registered check group via `scripts/failure_lab.py kill`; sibling publication untouched; automatic retry under a higher fence; stale fence rejected; `why` names the retry | Fake workers on macOS; live run **NOT PROVEN** |
| Trust surface | `graphene why --json` with worker identity, fences, retries, receipt nodes; `graphene mission capsule export/verify` with manifest-summary and attempt-coverage cross-checks and an explicit producer-authenticity disclaimer | Scripted-local and fake-ADK missions |
| Demo target | `demo/north_star` ledger service (524 source lines, 52 tests) with materializer and goal/criteria | No live mission has run on it |

Matrix on the series head: Python unit/integration/process/adversarial excluding MCP **1923 passed, 4 skipped** (the four opt-in gates), MCP STDIO **6 passed**, frontend **39 passed**, ruff/compileall/`git diff --check` clean. Run: `uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py`.

Owner actions still required, in order: Gemini credentials plus `GRAPHENE_RUN_LIVE_GEMINI=1`; a check executor (`GRAPHENE_CHECK_EXECUTOR=host-sandbox` on macOS, or a responsive Docker daemon with the built image); a real Claude Code transcript at `local/shadow/claude-code-session-raw.jsonl` with `SOURCE.txt`; the Google Cloud project decisions in [the cloud proof plan](CLOUD_PROOF_PLAN.md). The exact sequence is in [the North Star runbook](NORTH_STAR_RUNBOOK.md). No truth label flips in this update.

## 2026-08-23 update: the live North Star run, the failure laboratory, and `graphene watch`

Commit range: `9a0d1da` (preflight) through the series head recorded in
`NIGHT_REPORT.md`. Full detail, spend, and authority use are in that report;
the evidence lives under `evidence/north_star/`.

| Area | Implemented | Current proof boundary |
|---|---|---|
| Live Gemini | Two complete two-worker missions on Vertex AI (`gemini-3.5-flash`, location `global`) with evidence-bound receipts, overlap on three clocks (store, runtime-stamped call, provider's own `create_time`→`Date`), exact verification, bundle-bound approval, isolated result | **`verified_live`**; approvals were operator-delegated (`server_derived`), so human attestation on a live mission stays **NOT PROVEN** |
| Receipts | Provider-side stamps (`response_id`, server `create_time`, HTTP `Date`) via `StampedGemini`; receipts bound even when the reply is rejected or a mutation is refused; `model_output_rejected` is a bounded retryable failure | Live receipts carry all three stamps; absent stamps are omitted so older receipts hash identically |
| Failure laboratory | `scripts/failure_lab.py auto`: unattended, registry-identified SIGKILL once a sibling is accepted; `why` gains `prior_attempts` | Live: four kills, `-9` receipts, sibling untouched, fenced retry accepted once; **completion after a live recovery NOT PROVEN** (rehearsal only) |
| Capsule | Cold-verified from a fresh clone with no mission store on the completed and the laboratory missions | **`verified_live_cold`**; same laptop, no signature |
| Watcher | `graphene watch inbox` / `watch github` (ETag/304, backoff, dedupe, fail-closed rejections), `mission.triggered` hash-chained annotation, `why` trigger stage | Fixture-tested; live inbox trigger created a real mission whose `why` starts at the trigger; **live GitHub polling NOT PROVEN** |
| Planner hardening | Sanitized validation detail with token counts; model ordering canonicalized; explicit planner rules; 16 384-token cap; 120 s timeout; demo `max_attempts` 16 | What first live contact broke, fixed forward and regression-tested |
| Operations | `scripts/secret_scan.py` (location-only), `scripts/morning_verify.sh` (one-command re-verification incl. cold capsule verify from a fresh clone) | `morning_verify.sh` passes |

Matrix on the series head: **1960 passed, 4 opt-in skips**; ruff, compileall,
`git diff --check` clean. Finding for later: a concurrent reader can see an
attempt row before its evidence artifact exists (two SQLite files); the
poller reopens, the writer-side fix is open. Model output quality on the
demo's markdown task, not Graphene mechanics, is what kept most live
missions from completing.
