# Graphene documentation history

This index prevents planning artifacts, judge reports, and old implementation prompts from being mistaken for current product truth.

## Current authority

| Document | Role |
|---|---|
| [`README.md`](../README.md) | Canonical user path, thesis, proof matrix, and boundaries |
| [`simplreadme.md`](../simplreadme.md) | Shortest setup and truth-level guide |
| [`IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md) | Current shipped behavior and unproven claims |
| [`DECISIONS.md`](../DECISIONS.md) | Living ADR/decision log; newest accepted ADR wins |
| [`contracts/product_proof.json`](../contracts/product_proof.json) | Machine-readable product, driver, and capture truth |
| [`demo_transcript.md`](demo_transcript.md) | Redacted current demo shapes and branch semantics |
| [`data_residency.md`](data_residency.md) | Current privacy/data boundary |
| [`EXECUTOR_THREAT_MODEL.md`](EXECUTOR_THREAT_MODEL.md) | Current macOS executor and Linux fail-closed boundary |
| [`GRAPHENE_PRODUCT_PROOF_SPRINT_REVIEW.md`](../GRAPHENE_PRODUCT_PROOF_SPRINT_REVIEW.md) | Current implementation audit, proof matrix, verification record, and remaining blockers |

The active [`GRAPHENE_PRODUCT_PROOF_SPRINT_PROMPT.md`](../GRAPHENE_PRODUCT_PROOF_SPRINT_PROMPT.md) is an implementation input, not evidence that every requirement shipped. Current behavior still comes from the sources above and executable tests.

## Historical records

These files preserve product reasoning and implementation history. Their SHAs, test counts, planned tools, model names, platform claims, deadlines, and definitions of done are snapshots—not current claims.

| Document | Historical role |
|---|---|
| [`IDEA_EVALUATION.md`](../IDEA_EVALUATION.md) | Initial market and framing evaluation |
| [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md) | Original Proofline/Graphene plan |
| [`ULTRA_MVP_EXECUTION.md`](../ULTRA_MVP_EXECUTION.md) | Phase-0 build brief |
| [`POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md`](../POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md) | Post-Phase-0 graph plan |
| [`GRAPHENE_CLI_LINEAGE_JUDGE_PROMPT.md`](../GRAPHENE_CLI_LINEAGE_JUDGE_PROMPT.md) | CLI-lineage judge prompt |
| [`CLI_LINEAGE_JUDGE_DECISION.md`](../CLI_LINEAGE_JUDGE_DECISION.md) | Dated judge/pivot report |
| [`GRAPHENE_ULTRA_IMPLEMENTATION_LOOP.md`](../GRAPHENE_ULTRA_IMPLEMENTATION_LOOP.md) | Superseded root implementation prompt |
| [`GRAPHENE_ULTRA_CONTINUATION_LOOP.md`](../GRAPHENE_ULTRA_CONTINUATION_LOOP.md) | Superseded continuation prompt |
| [`GRAPHENE_VISUALIZATION_SPRINT_PROMPT.md`](../GRAPHENE_VISUALIZATION_SPRINT_PROMPT.md) | Prior visualization sprint prompt |
| [`HACKATHON_TIMELINE.md`](../HACKATHON_TIMELINE.md) | Dated schedule/source snapshot |
| [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) | Dated prior question ledger |
| [`evidence/checkpoints/`](../evidence/checkpoints/) | Dated implementation checkpoints and local observations |

`contracts/golden_path.json` and `contracts/graph_mvp.json` remain shared operational fixture inputs because v2 still consumes their frozen task/profile/scope data. Their legacy API/loop/framework/model-policy/graph fields are not product or driver truth; that role belongs to `contracts/product_proof.json`. The split is recorded in [`DECISIONS.md`](../DECISIONS.md).
