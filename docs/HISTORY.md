# Graphene documentation history

This index prevents planning artifacts, judge reports, and old implementation prompts from being mistaken for current product truth.

## Current authority

| Document | Role |
|---|---|
| [`README.md`](../README.md) | Canonical user path, thesis, proof matrix, and boundaries |
| [`contracts/product_proof.json`](../contracts/product_proof.json) | Machine-readable product, driver, and capture truth |
| [`demo_transcript.md`](demo_transcript.md) | Redacted current demo shapes and branch semantics |
| [`data_residency.md`](data_residency.md) | Current privacy/data boundary |
| [`EXECUTOR_THREAT_MODEL.md`](EXECUTOR_THREAT_MODEL.md) | Current macOS executor and Linux fail-closed boundary |
| [`GRAPH_NECESSITY_EVAL.md`](GRAPH_NECESSITY_EVAL.md) | Graph-necessity study protocol; not yet run |

Local planning, prompt, and review files live in untracked `All_md_files/` (`prompts/` and `reviews/`). They are not repository authority.

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

`contracts/golden_path.json` and `contracts/graph_mvp.json` remain shared operational fixture inputs because v2 still consumes their frozen task/profile/scope data. Their legacy API/loop/framework/model-policy/graph fields are not product or driver truth; that role belongs to `contracts/product_proof.json`. The split is compatibility-only: current product and driver truth comes from `contracts/product_proof.json`.
