# Graphene implementation status

**Status authority:** this file describes current product behavior without pinning a commit SHA, test count, or host snapshot. [`README.md`](README.md) is the user path; [`contracts/product_proof.json`](contracts/product_proof.json) is the machine-readable product/demo truth; [`DECISIONS.md`](DECISIONS.md) separates current truth from shared fixture inputs and compatibility-only surfaces.

## Current product

Graphene is an evidence-backed review and handoff layer for a developer supervising bounded coding-agent work. The v2 terminal/service path captures six scoped operations, verifies a private SQLite lineage and artifacts, projects a bounded public decision view, and compiles only explicitly approved evidence into a fresh isolated consumer runtime.

The graph remains read-only. It helps a reviewer answer what needs attention, what changed, what supports the candidate, where a human intervened, what entered or did not enter a handoff, what remains unknown, and what local outcome exists. It is not a mutation surface, repository crawler, inferred relevance engine, or agent-input channel.

## Shipped proof levels

| Driver | Platform | Current proof |
|---|---|---|
| `verified-replay` | Common development OSes | Checked-in event fixture materialized through v2 verification, including explicit context opening/reference and hash-checked decision-view behavior; no authoritative writes, captured live run, human attestation, or new test execution |
| `scripted-local` | macOS with `/usr/bin/sandbox-exec` | Deterministic workflow fixture through v2 services, interactive TTY branches, policy/verification, isolated retest, and approved isolated local Git commit |
| `adk-fake` | macOS with `/usr/bin/sandbox-exec` | Real Google ADK Runner/session/tool routing through the same bounded protocol with a deterministic fake model and zero external model calls |

There is no real Gemini/external-live driver and no silent fallback among drivers.

## Authority map

### Authoritative v2

- `graphene` and `graphene-mcp` compose the current terminal-first product path.
- `ScopedApplicationService` owns the six operations: `search_repo`, `read_file`, `open_evidence`, `write_file`, `run_fixed_test`, and zero-argument `request_completion`.
- Committed and verified v2 SQLite events, private artifacts, policy decisions, retained checkpoints, and isolated local-result receipts are authority.
- The viewer is an authenticated loopback, GET/HEAD-only, privacy-filtered projection. `EVIDENCE_INVALID` supersedes normal state.
- Billing denial occurs before consumer construction and records zero model dispatch. An allowed Auth handoff records included/excluded evidence and creates a distinct isolated consumer runtime.
- An approved final TTY branch creates a Git commit only inside the retained isolated fixture checkout. Rejection creates no commit; nothing pushes, opens a PR, deploys, or changes the user's checkout.

### Shared operational fixture contracts

- `contracts/golden_path.json` supplies frozen Auth task, memory, file, test, and inner executor inputs used by both v2 and compatibility readers.
- `contracts/graph_mvp.json` supplies the frozen profile/scope inputs still consumed by v2. Its legacy framework/model-policy, graph/API, and three-tool vocabulary is compatibility-shaped metadata, not current driver or runtime proof.
- Current product and driver truth comes from `contracts/product_proof.json`; neither shared fixture contract may imply Gemini, an independent agent, human attestation, or a current Git outcome.

### Compatibility-only surfaces

- `backend/graphene/app.py`, root `frontend/`, and the root `Dockerfile` preserve the earlier mutable HTTP demo.
- The root Docker image starts that legacy HTTP surface. It is not the v2 composition root and cannot execute v2 fixed tests on Linux.

## Integrity, privacy, and platform boundaries

- The public decision view contains bounded safe labels, paths, truth kinds, references, receipts, digests, omissions, and unknowns—not raw source, diffs, prompts, test stdout, secrets, or private artifact bytes.
- Owner-private artifacts may contain authorized source/evidence bytes, diffs, approved context, and bounded test output. Arbitrary shell/editor work, whole-repository activity, hidden reasoning, pushes, PRs, deployments, and cloud state are not observed.
- Human attestation requires an interactive TTY at the decision point. Non-TTY automation is `simulated_fixture` or fails before a human-attested write.
- Fixed tests use the frozen sanitized Auth fixture and the macOS `/usr/bin/sandbox-exec` boundary. Linux/Docker remains fail-closed for v2 fixed-test execution.
- Graphene records context compilation, inclusion/exclusion, injection, opening/reference, and later operations. It does not establish that delivered context caused or improved later work.
- The supported product fixture is Auth plus the Billing zero-dispatch denial. Arbitrary confidential repositories, whole-repository capture, and generic policy administration are not supported.
- The viewer never feeds graph-derived context back into a runtime. Graph-to-agent consumption remains deferred.

## Local verification contract

Run the repository's checked-in gates; do not substitute prose counts for their current result:

```bash
uv lock --check
uv sync --frozen
uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py
uv run --frozen pytest -q tests/process/test_mcp_stdio.py
node --test frontend/test/*.test.mjs
node --test tests/frontend/*.mjs
node --check frontend/src/app.mjs frontend/src/graph.mjs frontend/src/workflow.mjs
node --check backend/graphene/viewer/static/reducer.mjs backend/graphene/viewer/static/viewer.mjs
git diff --check
```

The GitHub Actions workflow defines macOS positive, Ubuntu replay/fail-closed, and frontend jobs. This status file does not claim the resulting commit is hosted-green until a matching workflow run exists.

## Unproven and deferred

1. The graph-necessity comparison has no participant results until unfamiliar developers actually complete it. Green implementation tests are not product-efficacy proof.
2. No real Gemini, external live model, cloud deployment, Firestore durability, push, or PR is claimed.
3. No evidence yet establishes that approved context improves an independently executed continuation.
4. Linux fixed-test execution requires an equivalent reviewed isolation design; replay is the portable path today.
5. Artifact retention, reachability GC, delete semantics, and secure erase remain unimplemented.
6. Graph-to-agent retrieval or graph-generated prompts remain explicitly deferred because projection errors could amplify into action.

Current references: [privacy](docs/data_residency.md), [executor boundary](docs/EXECUTOR_THREAT_MODEL.md), [demo transcript](docs/demo_transcript.md), and [documentation history](docs/HISTORY.md).
