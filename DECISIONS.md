# Graphene decision log

## 2026-08-11 — Phase 0 scope lock

- `ULTRA_MVP_EXECUTION.md` is authoritative. Graphene targets Collaborative Partner with one controlled Python fixture and one ADK/Gemini path.
- `contracts/golden_path.json` is the machine-readable source of truth for tasks, prompt, tools, scope, tests, retrieval, API, and lifecycle. Implementation may not silently revise it.
- Python is pinned to 3.13, Node to 22, Google ADK to 2.5.0, the model policy to `gemini-3.5-flash`, Cloud Run to `us-central1`, and Vertex to `global`.
- The fixture runner executes only `python -m pytest -q -p no:cacheprovider`; writes are limited to `app/auth/limiter.py` and `tests/test_security_policy.py`.
- Observed toolchain: `uv` uses Python 3.13.9; the system `python3` is 3.14.3; Docker 29.6.1 is running; Git 2.39.3 is available. Local Node is 23.11.0 and Node 22 remains unavailable; `gcloud` is absent.
- Cloud/model access is not verified: `gcloud`, ADC/project configuration, and Gemini credentials are absent locally. No cloud or model result is claimed.
- The credit request, Devpost draft, and saved Collaborative Partner selection are not evidenced locally and need Alex's confirmation.
- Native hooks, MCP, SQLite, multi-vendor adapters, graph UI, import analysis, invalidation/repair, A/B evaluation, arbitrary repositories, and multi-user auth remain explicitly cut.

## 2026-08-11 — Post-Phase-0 graph contract

- `POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md` restores one bounded evidence/context graph and overrides the older graph-UI cut without reviving a general graph platform.
- `contracts/graph_mvp.json` freezes three server-owned profiles, four read endpoints, graph vocabulary, 25-node/40-edge caps, a 100 KB patch cap, and deterministic Billing denial.
- After all five read-only role reviews, the single contract revision added authoritative feedback anchoring, fixed task/profile bindings, receipt and decision digests, packet/graph-bound promotion, exact per-kind graph fields, and honest truncation. The final canonical contract hash is `74c871a9f06b1dbd2c54a2837d0cfc4812177b780425300d41497b0a24655be2`.
- The graph remains a projection. Existing run, memory, candidate, test, decision, and promotion records remain authoritative.
- Use platform-native SVG/HTML unless a frontend dependency becomes necessary. No graph database, force layout, WebSocket, or model-authored relationship is permitted.

## 2026-08-11 — Local vertical slice and cloud seams

- Deterministic-local remains the default and verified demo mode. The Google ADK 2.5.0 runner is opt-in through `GRAPHENE_EXECUTION_MODE=google-adk`; model text never supplies scope, graph facts, tests, approval, or promotion truth.
- Local restart proof uses an atomic JSON snapshot. The Firestore adapter stores the bounded demo namespace in one transactionally updated document; its explicit 1 MiB ceiling is acceptable for this fixture and requires collection-level storage before broader use.
- The dependency-free frontend owns the complete six-action golden loop and keeps the mutation token only in JavaScript memory.
- One Python 3.13 container installs Git, runs unprivileged, serves API and static UI together, and binds `0.0.0.0:$PORT`.
- Local tests, ten deterministic loops, and the container are evidence-backed. Gemini, real Firestore, Cloud Run, and browser visual QA remain unverified and may not be shown or described as completed.
