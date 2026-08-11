# ReviewLatch implementation status

Updated: 2026-08-11 (America/Los_Angeles)

## Gate 1 baseline

- Branch: `agent/reviewlatch-mvp`
- Baseline SHA: `72760f88c3b6b95128e392d3346bd3547b6e8bbb`
- Phase-0 verification: `uv run pytest -q` → 14 passed, 1 expected xfail
- Graph contract candidate: `contracts/graph_mvp.json`
- Final contract hash: `eec06d1cfdfacd7c3656a8bda6025434db5fd693be1475e0574e0717694e8bed`
- User-authored input preserved: untracked `POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md`
- Local blockers: `gcloud` absent; no Google/Gemini environment configuration detected; cloud, Firestore, and real-model runs remain unverified

## Frozen ownership ledger

| Identity | Exclusive paths | First wave |
|---|---|---|
| Root | `backend/reviewlatch/app.py`, `backend/reviewlatch/models.py`, `backend/reviewlatch/store.py`, `backend/reviewlatch/hashing.py`, `contracts/**`, root manifests/docs/config | contract/integration |
| Ultra 1 — Graph Core | `backend/reviewlatch/graph/**`, `tests/unit/graph/**` | wave A |
| Ultra 2 — Catalog/Context | `backend/reviewlatch/context/**`, `tests/unit/context/**` | wave A |
| Ultra 3 — Execution | `backend/reviewlatch/execution/**`, `tests/unit/execution/**` | wave A |
| Ultra 4 — Graph Experience | `frontend/**` | wave B |
| Ultra 5 — Verification | `tests/integration/**`, `tests/adversarial/**`, `demo/**`, `evidence/**` | wave B |

All five identities are fixed and may not spawn children, edit shared contracts, stage, commit, branch, push, deploy, or write outside their ownership. The two waves exist only because the environment permits three subagents alongside the root.

## Contract facts

- Profiles: `platform-maintainer@1`, `auth-maintainer@1`, `billing-observer@1`
- Mutable fixture paths: `app/auth/limiter.py`, `tests/test_security_policy.py`
- Scoped tools: `read_file`, `write_file`, `run_fixture_tests`
- Graph limits: depth 1 default/2 maximum, 25 nodes, 40 edges, 8 related files, 12 hunks, 3 memories, 100 KB patch
- New read endpoints: run graph, graph node detail, run context packet, agent catalog
- Negative proof: Billing or a non-intersecting path yields no memory, related files, paths, tools, or selected graph nodes and returns `denied_out_of_scope`

## Current gate

Gates 1–3 and the deterministic portions of Gates 5–6 pass locally against contract hash `eec06d1cfdfacd7c3656a8bda6025434db5fd693be1475e0574e0717694e8bed`:

- clean API/UI golden loop through exact promotion;
- deterministic graph, exact hunk detail, catalog scope, and Billing/path denial;
- packet-before-injection, fresh session, fixed tests, completion denial, and bound receipt;
- JSON-process restart before and after promotion;
- 10/10 clean-reset local soak runs at 20 nodes/19 edges;
- adversarial substitution, traversal, symlink, caps, auth, and idempotency checks;
- Firestore adapter contract test and successful production-container smoke test.

External Gate 4 remains open: Google credentials/project/model eligibility, a real Gemini/ADK run, real Firestore, `gcloud`, and Cloud Run are unavailable and therefore unverified. Automated browser visual/keyboard QA is also unavailable because this environment exposes no browser instance.

## Accepted local evidence

- `uv run pytest -q -p no:cacheprovider` → 55 passed; one upstream TestClient deprecation warning.
- `node --test frontend/test/*.test.mjs` → 8 passed.
- `evidence/local_vertical_slice.json` → SHA-256 `cbfb189941641ec542493cacd17eec865e1de85de5802fb9ba60cb6fc9ff2a5b`.
- `evidence/local_soak.json` → SHA-256 `00d3c0012d559ec84fa82dc856caefe2f7184ce53c4db24dd90589c44b1feaa4`.
- Final `reviewlatch:local` image build passed; container smoke returned health and frontend assets with 200, rejected an unauthenticated mutation with 401, and accepted the same authorized bounded create request.
