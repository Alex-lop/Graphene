# Graphene implementation status

Updated: 2026-08-13T01:07:29-07:00 (America/Los_Angeles)

## Repository truth

- Branch/upstream: `main` / `origin/main`; base HEAD `7d19fdbd5084ad106ab5208a02504ebea89752cc`; zero commits ahead/behind.
- The continuation implementation is an uncommitted working tree. No reset, commit, push, deployment, model call, cloud mutation, or spend was performed.
- The user-owned `GRAPHENE_ULTRA_CONTINUATION_LOOP.md` remains unchanged at SHA-256 `e3341837f4261e4eebe69e5666c29f591766eda17fa4d7b8b688b9f66a549148`.
- Host: macOS 26.5.2 arm64; Python 3.13.9; Node 23.11.0; uv 0.11.29; SQLite 3.51.0; Google ADK 2.5.0; MCP 2.0.0.
- No Google Cloud project/ADC, `gcloud`, deployment authority, or spend authorization was used. Real Gemini/Firestore/Cloud Run claims are `EXTERNAL_BLOCKED`.

## Executable v2 product path

The terminal v2 path is the authority for new product work:

1. `graphene --json run` creates or exactly replays a private SQLite/artifact store, frozen checkout, and durable `run.started`.
2. A separate `graphene --json watch` continuously verifies and flushes committed NDJSON; inert `replay --speed` is timestamp-paced.
3. The installed `graphene-mcp` uses the official MCP STDIO transport, exposes exactly six strict tools, and routes the same scoped service used by ADK.
4. Starts/results commit before return; an active watcher acknowledges the exact result sequence before the MCP response is delivered.
5. Runtime state rehydrates consumed calls, file versions, writes, changed paths, terminal status, and ambiguous dispatch from verified events.
6. Public `review`, `feedback`, `answer`, and `memory` commands derive exact changesets/hunks/test receipts, store the private correction, and bind approval to an immutable scoped memory.
7. Verified handoff enumerates its candidate universe from stored events/artifacts. Billing denial constructs no consumer runtime. Auth `handoff --start` persists the decision, included-only brief, fresh run, zero-prior-message injection receipt, and exact checkout binding.
8. The consumer must open only selected evidence, reread current source, bind writes to same-invocation file versions, pass the frozen test, and request human review.
9. `why` traverses explicit source/consumer evidence relations; `inspect` resolves only items bound to the selected verified run.
10. `promote` reconstructs current evidence, runs the fixed test, persists and rereads a checkpoint, then appends the final promotion. Exact retry replays; restart reproduces the projection.

The legacy FastAPI/browser store is frozen compatibility-only and remains outside v2 proof. It is still a separate mutable demo path and is listed as migration debt, not hidden as canonical behavior.

## Integrity, privacy, and platform state

- SQLite append/verify enforces CAS heads, exact idempotency replay, canonical digest chains, reciprocal identities, semantic transitions, source/reference resolution, and retained checkpoints. The Firestore adapter mirrors these event semantics against an adversarial transactional fake.
- Public events contain bounded metadata and digests, never raw source/diff/prompt/model output/test stdout. Provider model metadata must exactly match the configured server identity; arbitrary function-call IDs are hashed before persistence.
- The macOS fixed-test executor builds a minimal no-follow view of frozen fixture bytes, supplies `/dev/null` stdin, and denies ambient checkout/host reads, network, fork, raw sysctl/process inspection, and external writes. Ambiguous writes interrupt and quarantine.
- Linux and the shipped Linux container do not have an equivalent sandbox. The v2 fixed-test workflow fails closed there; only the legacy HTTP process can start.
- Local artifacts have no TTL, reachability GC, delete API, or secure erase. Firestore has no durable private-artifact ledger, so cloud cold-restart proof is unavailable.

## Verification snapshot

- Final local Python matrix: `.venv/bin/pytest -q tests/unit tests/integration tests/process tests/adversarial` → exit `0`; `279 passed`.
- Fresh consumer/MCP/recovery joined gate: `21 passed`; the official STDIO subprocess performs evidence open, source reread, version-bound writes, fixed retest, and completion denial.
- Final promotion reliability gate: `28 passed`; a retained checkpoint plus failed final append is recovered by exact public retry.
- Frontend: `8 passed`; JavaScript syntax passed.
- `uv lock --check`, Python compilation, JSON parsing, documentation/CI contract tests, touched-lane Ruff checks, evidence-hash verification, and `git diff --check` passed.
- GitHub Actions was added for macOS full workflow, Linux fail-closed sentinels, and Node 22. It has not run on hosted runners.

Final claim definitions, commands, proof levels, and 36 verified evidence hashes are in `evidence/claim_ledger.json`.

## Known limits and next gates

1. Run the checked workflow once on GitHub-hosted macOS/Linux runners; do not weaken the executor if the host image differs.
2. A safe Linux executor, real Gemini, durable cloud artifacts/Firestore, and Cloud Run remain separate gates requiring platform work or explicit external authorization.
3. Promotion is a local evidence/checkpoint receipt; it does not create or push a durable Git commit.
4. A five-person terminal comprehension study, retention/GC design, and legacy browser read-only migration remain incomplete local P2/P1 work.

Questions: [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md). Claims: [`evidence/claim_ledger.json`](evidence/claim_ledger.json). Privacy: [`docs/data_residency.md`](docs/data_residency.md). Executor boundary: [`docs/EXECUTOR_THREAT_MODEL.md`](docs/EXECUTOR_THREAT_MODEL.md).
