# Architecture

## Authority

Graphene separates three linked domains:

```text
immutable mission contracts + ordered hash-chained events + bound canonical records
                                  |
                                  v
                    durable materialized mission state
                       |                         |
                       v                         v
             scheduler/command path       Mission Control projection
                       |
                       v
       attempt evidence -> accepted publications -> integration -> verification
```

The canonical authority is the immutable initial contracts, ordered hash-chained events, and every content-addressed canonical state or artifact record those events bind. Events alone cannot reconstruct fields intentionally stored only in referenced immutable records.

The scheduler consumes only a validated approved plan. The browser graph and tables project committed state; they cannot become execution authority.

## Contracts and transitions

Strict frozen Pydantic contracts cover projects, missions, plans, criteria, tasks, attempts, leases, gates, publications, resources, evidence, and results. Unknown fields fail validation. Plans reject cycles, missing dependencies or artifacts, policy excess, undeclared checks, cross-task write conflicts, uncovered/self-verified criteria, incomplete artifact frontiers, and unsupported assembly/verification shapes.

Mission and task transition tables live in [`graphene.orchestration.mission_models`](../backend/graphene/orchestration/mission_models.py). The accepted prose contract is [TASKMASTER_PRODUCT_CONTRACT.md](TASKMASTER_PRODUCT_CONTRACT.md).

## Local store

SQLite uses WAL, full synchronization, command idempotency, transactional claims, monotonic fencing, hash-chained events, immutable canonical record bytes, and indexed projections. The v2 store records and verifies a schema-ledger digest and rejects an incompatible or modified schema instead of silently migrating it. Normal reads use materialized state, but full verification must compare every execution-relevant projection and bound record to canonical authority before downstream effects.

Dispatch is at least once. Graphene-owned committed state and filesystem effects can be idempotent when a durable receipt binds them. A provider call or process effect separated from its receipt is not exactly once; it requires an `outcome_unknown`/operator policy rather than silent repetition.

Task-scoped gates may enter `needs_input`; `graphene task input` stores bounded operator bytes outside public projection and commits only a digest-verified reference before returning the task to ready. The browser seam is tested but one-command live mode does not inject it because staged-input cleanup is incomplete. Attempt, worker-time, and artifact limits are authoritative. Exhaustion commits a `blocked_budget` event, blocks the affected task, pauses dispatch, and requires replan or cancel; ordinary resume cannot erase that blocker.

## Runtime boundaries

Workers, deterministic integration, and verification operate in Graphene-owned private workspaces, not the supplied user checkout. Work tasks produce scoped publications. Integration consumes only accepted publications in a separate workspace. Verification binds the exact candidate digest/tree. Runtime publication uses an independently measured Git workspace audit and trusted check-runner receipts; workers cannot author their own deterministic pass.

The working tree has a bounded ADK planner/worker runtime, completion-order coordinator, typed failures, receipt recovery, and exact accepted-artifact cache. Deterministic fake-model tests exercise two workers end to end without touching the supplied checkout. The credentialed Gemini evidence from 2026-08-23 is historical earlier-runtime evidence; the current recovery runtime is **NOT PROVEN** live. See the [canonical proof table](PROOF.md); tests and scripted fixtures prove local wiring only.

Tree identity is explicitly `graphene.tree.v2`: entry count, path/content lengths, type/mode, and bytes are domain separated and the prior NUL-delimiter collision is covered by an independent reference test. Every successful publication must carry a verified `ArtifactEnvelopeV2`; accepted dependencies consume that published reference. After verification, the write path builds and registers an immutable pending `FinalResultBundleV2`. Display, approval, rejection, and decision receipts bind its bundle ID. `graphene why --mission` exposes bounded causal reads through approval; compose it with `graphene mission result show` for the isolated result receipt and ref.

## Control plane

Mission Control's graph, tables, snapshots, and deltas are an authenticated read-only projection; they never become write authority. The optional browser command layer delegates to the same finalizer and store used by the CLI, behind a distinct command token, exact-Origin checks, a short-lived CSRF session, explicit confirmation, idempotency IDs, expected head, exact bundle ID, and operator attribution. Cancellation is available only when an owned-process cleanup coordinator is injected; cleanup must finish before the terminal mutation. Replay and the packaged cloud viewer disable commands. A live browser capture remains pending.

The cloud slice contains typed registration/claim/fetch/heartbeat/completion/abandon contracts, transactional Firestore outbox transitions, a separately packaged private multi-mission coordinator, a bounded HTTPS client that obtains a fresh audience token, and an outbound local-executor loop. The official emulator verifies the production create/approve/readiness/claim/heartbeat/completion and sharded materialization/reconcile path. The adapter is not yet the complete `SchedulerStore`: worker registration/revocation, lease expiry/recovery, generic `claim_task`/`heartbeat`/`complete_attempt`, `enter_awaiting_result`, pause, resume, and cancel remain unsupported there. No service was deployed and live cloud proof remains open.

The Firestore adapter and private Cloud Run image are described in [Firestore and Cloud](FIRESTORE_AND_CLOUD.md). Packaging is not deployment proof.

## Legacy separation

`graphene.lineage` and `graphene.viewer` retain the Auth evidence/review protocol tour. Their v2 lineage events and `GraphSnapshot(view_version=1)` do not become mission contracts. Generic mission attempts use their own evidence stream; current mission-plan validation rejects `legacy_auth_v2` links.
