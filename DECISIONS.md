# Graphene decision log

## 2026-08-14 — ADR: one product truth and proof-level demo contract

- **Status:** accepted. This ADR supersedes earlier product-positioning, legacy-as-canonical, Gemini-by-default, three-tool-as-product, and promotion-without-local-result implications. Historical evidence remains historical; it is not rewritten into current proof.
- **Product:** Graphene is an evidence-backed review and handoff layer for a developer supervising bounded coding-agent work. The decision is to approve, reject, or hand off one exact candidate and its bounded evidence.
- **Canonical sources:** `README.md` is the user path, `IMPLEMENTATION_STATUS.md` is current behavior, this log owns decisions, and `contracts/product_proof.json` is machine-readable product/demo truth. `docs/HISTORY.md` classifies superseded narratives.
- **Compatibility split:** `backend/graphene/app.py`, root `frontend/`, and the root Docker entry point are compatibility-only. `contracts/golden_path.json` and `contracts/graph_mvp.json` remain shared operational fixture inputs because v2 consumes their frozen task/profile/scope data; their legacy API/loop/framework/model-policy/graph fields are not current product, driver, runtime, or outcome truth.
- **Driver truth:** `verified-replay` proves only a checked-in event fixture materialized through v2 verification and its hash-checked public decision view; `scripted-local` proves the deterministic bounded protocol and isolated local result; `adk-fake` proves the real ADK Runner/session/tool seam with a deterministic fake model. No driver silently falls back.
- **Capture boundary:** current v2 authority covers exactly `search_repo`, `read_file`, `open_evidence`, `write_file`, `run_fixed_test`, and zero-argument `request_completion` in the sanitized Auth/Billing fixture. macOS with `/usr/bin/sandbox-exec` is the only live fixed-test platform; replay is the portable view.
- **Claim boundary:** Live drivers and the checked-in replay fixture can establish context compilation, inclusion/exclusion, injection, explicit opening/reference, and later operations at their labeled proof levels. Replay fixture relationships are not captured-live evidence. Owner-private artifacts may contain authorized content that the public projection excludes. Graphene cannot claim context caused or improved an edit, nor can it claim unobserved shell/editor activity, push, PR, deployment, cloud state, or external-model quality.
- **Endpoint:** explicit final approval may create a Git commit only inside the retained isolated fixture checkout. Rejection creates no commit. The user's checkout, remotes, and global Git configuration remain untouched. The legacy `reconstructed_commit_sha` promotion-receipt field contains the reconstructed base SHA and is not a Git outcome; only `local_commit_receipt.local_commit_sha` establishes the isolated commit.
- **Deferred:** graph-to-agent retrieval, graph-generated prompts, inferred relevance, external-live models, Linux fixed-test execution, arbitrary repositories, and cloud deployment remain outside this sprint.

## Superseded historical decisions

The entries below preserve what was decided and observed at earlier checkpoints. Their model names, tool counts, SHAs, test results, platform status, product framing, and authority statements are historical snapshots; the accepted ADR above controls any conflict with current product truth.

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

## 2026-08-12 — ADR: v2 terminal lineage supersedes the legacy mutable product path

- Status: accepted for new work; migration is in progress.
- The v2 SQLite lineage, private artifact store, verified reducer, scoped six-operation service, handoff, recovery, promotion, ADK, and MCP components are the sole target authority for all new mutations.
- The FastAPI/browser `RunRecord`/`ProofItem`/legacy `Store` path remains compatibility-only until its reads move to the v2 projection. It may receive security repairs but no new product mutation or proof claim.
- The first public mode is deterministic local bootstrap. It creates a v2 run and checkout but does not claim model execution. MCP and ADK must share that same composition root.
- Proof levels are split into UNIT, COMPONENT, PROCESS, REAL_MODEL, and REAL_CLOUD. Narrow success cannot imply a broader level.
- The current fixed-test executor supports only the frozen sanitized fixture on macOS. Linux/container workflow claims are withdrawn until an isolation boundary runs the full fixture loop.
- A 2026-08-12 adversarial probe showed an agent-written test could echo an ambient checkout canary. Cloud/source demonstrations remain halted until a minimal test-view regression passes.
- Historical decisions and evidence remain unchanged. This ADR supersedes their MCP/SQLite cuts and legacy-as-canonical implications; it does not rewrite them.

## 2026-08-12 — Live display ordering is explicitly acknowledged

- An MCP result is evidence-visible only after the scoped service commits and an active public watcher flushes that exact sequence.
- The watcher records a cursor in a private locked sidecar; the STDIO adapter waits for it only when a watcher is active. Fixed sleeps are rejected because elapsed time does not prove display ordering.
- The sidecar is coordination, never lineage truth. ADK, MCP, and local scripted proposals use distinct authorities/source receipts.
- A fake ADK runner remains component proof even when its returned model identity and terminal receipt are recorded.

## 2026-08-13 — Human authority and fresh handoff are event-derived

- Exact changesets, hunks, and test receipts are derived from the verified source stream; callers cannot submit them as authority.
- A correction is stored privately, followed by a human clarification answer, exact feedback, immutable memory proposal, and explicit approve/reject decision. The mandatory scope comes from the selected frozen option, not caller-supplied memory fields.
- Handoff enumerates the stable source event/artifact universe itself. It persists a complete server-only decision and an included-only `ContextBrief`; Billing denial occurs before any consumer runtime construction.
- An allowed Auth handoff creates disjoint run/session/invocation identities, binds zero prior messages and the exact prompt digest, verifies the frozen checkout before returning a service, and requires same-invocation reads before writes.
- Exact repeated public handoff requests resolve their already-committed decision/brief/consumer instead of deriving identity from the advanced mutable head.

## 2026-08-13 — Promotion is checkpoint-before-final, not a hosted commit

- The coordinator validates the verified source/consumer bindings, reconstructs current candidate evidence, invokes only the frozen fixed-test seam, and core-mints the receipt. A caller-created self-hashed promotion receipt is rejected.
- The approval-head checkpoint is persisted as a private artifact and retained through the same reader used by lineage verification before the final `promotion.completed` event is appended.
- The reducer calls a run `PROMOTED` only after that final event, and exact retry reuses the retained checkpoint/receipt. Checkpoint failure cannot expose a completed state.
- The reconstructed commit field is an evidence receipt for the local frozen candidate. Graphene does not create, push, or claim a durable hosted commit.

## 2026-08-13 — Supported platform and privacy boundary are deliberately narrow

- Full fixed-test execution is supported only for the frozen sanitized fixture on macOS with `/usr/bin/sandbox-exec`. Linux/Docker fail closed until an equivalent isolation boundary exists.
- Fixed tests execute from a no-follow minimal view containing only contract-listed bytes; stdin, ambient checkout/host files, network, fork, raw process/sysctl inspection, and outside writes are denied. Successful bounded output is private tool-visible data, not public event content.
- Provider-reported model metadata is not public authority. ADK accepts it only when it exactly equals the configured server-owned model identity; provider call IDs are digested before persistence.
- SQLite is the complete local composition root. Firestore remains a metadata adapter until private artifacts/checkpoints have a durable, privacy-reviewed cloud strategy.
- GitHub Actions separates the macOS positive workflow, Linux fail-closed sentinels, and frontend checks. No CI step uses secrets, models, cloud mutations, or deploy permissions.
