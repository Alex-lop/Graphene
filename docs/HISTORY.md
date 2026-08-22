# Graphene documentation history

This index prevents planning artifacts, judge reports, and old implementation prompts from being mistaken for current product truth.

## Current authority

| Document | Role |
|---|---|
| [`README.md`](../README.md) | Canonical user path, thesis, proof matrix, and boundaries |
| [`README.md`](README.md) | Canonical documentation map |
| [`IMPLEMENTATION_REPORT.md`](IMPLEMENTATION_REPORT.md) | Evolving sprint change/test/proof ledger |
| [`contracts/product_proof.json`](../contracts/product_proof.json) | Machine-readable product, driver, and capture truth |
| [`TASKMASTER_PRODUCT_CONTRACT.md`](TASKMASTER_PRODUCT_CONTRACT.md) | Accepted mission authority, state, validation, and threat boundary |
| [`PRODUCT.md`](PRODUCT.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md) | Product scope and current system design |
| [`AGENT_RUNTIME.md`](AGENT_RUNTIME.md) | Current versus target planner/worker lifecycle |
| [`SECURITY_AND_SOVEREIGNTY.md`](SECURITY_AND_SOVEREIGNTY.md) | Canonical Taskmaster trust, isolation, evidence, and privacy boundary |
| [`FIRESTORE_AND_CLOUD.md`](FIRESTORE_AND_CLOUD.md) and [`ALEX_CLOUD_SETUP.md`](ALEX_CLOUD_SETUP.md) | Cloud design truth and explicit owner actions |
| [`MISSION_CONTROL.md`](MISSION_CONTROL.md), [`DEMO_GUIDE.md`](DEMO_GUIDE.md), and [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | UI/replay truth, demo path, and current gaps |
| [`NORTH_STAR_RUNBOOK.md`](NORTH_STAR_RUNBOOK.md) and [`CLOUD_PROOF_PLAN.md`](CLOUD_PROOF_PLAN.md) | Ordered credentialed North Star sequence and the Option 1 Cloud Run + real Firestore plan with its SQLite-versus-cloud authority split; NOT RUN — NOT PROVEN until the cited evidence lands in the same commit as any label flip |
| [`SHADOW.md`](SHADOW.md) and [`SHADOW_ADAPTER_SPEC.md`](SHADOW_ADAPTER_SPEC.md) | Shadow Agent product story, provenance discipline, and the open `shadow.event.v1` adapter format |
| [`backend/graphene/shadow/`](../backend/graphene/shadow/) and `graphene shadow` | Shadow Agent v0 implementation (2026-08-22): ndjson ingest, `segments.v1` reconstruction, `lint.v1` Trust Lint, report, and self-verifying capsule export; credential-free tests on the synthetic fixture only, `claude-code` adapter NOT PROVEN |
| [`deploy/cloudrun/README.md`](../deploy/cloudrun/README.md) | Reproducible but explicitly not-deployed cloud packaging |
| [`GRAPH_NECESSITY_EVAL.md`](GRAPH_NECESSITY_EVAL.md) | Graph-necessity study protocol; not yet run |
| [`benchmarks/README.md`](../benchmarks/README.md) | Graph-economics harness contract; no measured result is proven |

[`simplreadme.md`](../simplreadme.md) is now only a forwarding page. The legacy [demo transcript](demo_transcript.md), [data-residency matrix](data_residency.md), and [fixed-test threat model](EXECUTOR_THREAT_MODEL.md) retain Auth protocol details and are visibly superseded for Taskmaster guidance.

Local planning, prompt, and review files live in ignored `All_md_Files/`
(`prompts/` and `reviews/`). They are not repository authority.

## Historical records

These names preserve product reasoning and implementation history. Their SHAs, test counts, planned tools, model names, platform claims, deadlines, and definitions of done are snapshots—not current claims.

| Document | Historical role |
|---|---|
| `IDEA_EVALUATION.md` | Initial market and framing evaluation |
| `IMPLEMENTATION_PLAN.md` | Original Proofline/Graphene plan |
| `ULTRA_MVP_EXECUTION.md` | Phase-0 build brief |
| `POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md` | Post-Phase-0 graph plan |
| `GRAPHENE_CLI_LINEAGE_JUDGE_PROMPT.md` | CLI-lineage judge prompt |
| `CLI_LINEAGE_JUDGE_DECISION.md` | Dated judge/pivot report |
| `GRAPHENE_ULTRA_IMPLEMENTATION_LOOP.md` | Superseded root implementation prompt |
| `HACKATHON_TIMELINE.md` | Dated schedule/source snapshot |
| [`evidence/checkpoints/`](../evidence/checkpoints/) | Dated implementation checkpoints and local observations |

`contracts/golden_path.json` and `contracts/graph_mvp.json` remain shared
operational fixture inputs because the Auth protocol tour still consumes their
frozen task/profile/scope data. Their legacy API/loop/framework/model-policy and
graph fields are not Taskmaster product or driver truth. The sibling mission
domain and `contracts/product_proof.json` now carry that authority; the Auth
workflow remains a preserved regression/protocol tour rather than the hero path.
