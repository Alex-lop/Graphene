# Graphene documentation

The root [README](../README.md) is the canonical product doorway. This index owns navigation; focused documents own detail.

## Product and operation

- [Product](PRODUCT.md) — user, problem, loop, and supported scope.
- [Architecture](ARCHITECTURE.md) — authority, state, stores, and control plane.
- [Agent runtime](AGENT_RUNTIME.md) — planner, workers, tools, recovery, and proof status.
- [Mission Control](MISSION_CONTROL.md) — projection, graph, decisions, and replay semantics.
- [Demo guide](DEMO_GUIDE.md) — replay, scripted fixture, live-proof gates, and capture rules.
- [North Star runbook](NORTH_STAR_RUNBOOK.md) and [Cloud proof plan](CLOUD_PROOF_PLAN.md) — the ordered credentialed sequence (materialize, gated live test, mission, failure laboratory, capsule, what to record) and the Option 1 Cloud Run + real Firestore vertical with its authority split; both NOT RUN — NOT PROVEN.
- [Shadow Agent](SHADOW.md) — code review for agent sessions: observe, reconstruct, lint, report; observed-versus-inferred discipline.
- [Shadow adapter specification](SHADOW_ADAPTER_SPEC.md) — the open `shadow.event.v1` NDJSON format any agent or harness can emit.

## Trust and deployment

- [Security and sovereignty](SECURITY_AND_SOVEREIGNTY.md) — repository, sandbox, evidence, privacy, and process boundaries.
- [Firestore and Cloud](FIRESTORE_AND_CLOUD.md) — verified official-emulator vertical, remaining scheduler parity, and unproven deployment boundary.
- [Alex cloud setup](ALEX_CLOUD_SETUP.md) — explicit owner-only setup, proof, budget, and cleanup checklist.
- [Known limitations](KNOWN_LIMITATIONS.md) — current proof gaps and upgrade triggers.

## Engineering and evidence

- [Development](DEVELOPMENT.md) — local setup, test matrix, and contribution rules.
- [Implementation report](IMPLEMENTATION_REPORT.md) — current sprint change/proof ledger; final fields are intentionally pending until integration completes.
- [Taskmaster product contract](TASKMASTER_PRODUCT_CONTRACT.md) — accepted state and authority contract.
- [Graph necessity evaluation](GRAPH_NECESSITY_EVAL.md) — unrun comprehension-study protocol.
- [Harness observability proposal](PROPOSAL_HARNESS_OBSERVABILITY.md) — fit assessment for watching tool calls across agent harnesses; recommends the claude-code Shadow adapter over a new tool.
- [Graph economics benchmark](../benchmarks/README.md) — tested harness; no benchmark result is proven.
- [Documentation history](HISTORY.md) — current versus historical authority.

The old [executor threat model](EXECUTOR_THREAT_MODEL.md), [data-residency matrix](data_residency.md), and [demo transcript shapes](demo_transcript.md) are retained as legacy Auth protocol references. The focused Taskmaster documents above supersede them for current product guidance.
