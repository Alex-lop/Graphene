# Graphene Product-Proof Sprint Review

**Review date:** 2026-08-14 (America/Los_Angeles)  
**Verdict:** **Mechanically release-ready locally; product proof remains partial.**  
**Audit baseline and current HEAD:** `cf22c93f9001003f0949112ab7a588378c304bb6`  
**Branch/upstream:** `main` matched `origin/main`; the implementation remains intentionally uncommitted.

## Executive verdict

The sprint implementation is real and substantially advances Graphene's hackathon story. The strongest proof is no longer a generic bubble graph: it is a decision-first Review Brief backed by typed, inspectable relationships, three honestly separated demo drivers, real terminal branches, and a verifiable local-only Git endpoint.

The review found and fixed several places where the implementation had technically existed but skipped the intended product consequence:

- broad and narrow scope choices now change the compiled handoff, its digest, prompt, public-safe scope metadata, and viewer explanation;
- the canonical replay now shows context compilation, injection, an explicit consumer `open_evidence` operation, a pending candidate decision, and the later cleared state;
- the live terminal now prints the Billing denial, approved-context handoff, consumer opening, proof limit, isolated checkout, and exact `git show` verification command;
- a schema-valid but semantically forged local-result event can no longer be rendered as verified Git proof;
- new promotion receipts use `retest_base_sha`; the old misleading `reconstructed_commit_sha` survives only as a legacy read alias, while `local_commit_sha` means an actual commit;
- the shared profile fixture is provider-neutral instead of implying ADK or Gemini;
- the graph-necessity comparator is now a single canonical 111-line transcript rather than repeated full snapshot dumps.

The unresolved limitation is product evidence, not core mechanics: no unfamiliar-developer study, real browser visual record, hosted Ubuntu run, real external model, or independent-agent comparison was performed. Graphene may claim bounded provenance/review and ADK integration proof. It may not yet claim that the graph makes review faster, that approved context improves behavior, or that an autonomous agent produced the result.

## Product thesis

> Graphene is an evidence-backed review and handoff layer for a developer supervising bounded coding-agent work. It shows the captured edits, tests, human corrections, approved context, and explicit unknowns behind a candidate, then passes only approved evidence into the next run.

## Prompt acceptance review

| Requirement | Status | Review evidence |
|---|---|---|
| P0.1 Human provenance | **PASS** | Human attestation requires a real TTY. Non-TTY input fails closed or uses the explicitly hidden `simulated_fixture` test seam. Node, summary, terminal, and replay truth labels stay distinct. PTY approve/reject and piped-input tests pass. |
| P0.2 Real gate branches | **PASS** | `all_auth` and `rate_limiter_only` produce different memory scope, context brief, prompt, digest, and viewer scope/path facts. Memory rejection and candidate rejection end cleanly and create no handoff or commit respectively. |
| P0.3 Decision-first viewer | **PARTIAL** | The Review Brief answers changed paths, hunk/test evidence, intervention provenance, Billing denial, context inclusion/opening, outcome, and explicit unknowns. Projection tests pass. Required desktop/narrow/keyboard visual inspection was **not run** because no controllable browser was available. |
| P0.4 Typed support paths | **PASS** | Candidate support is restricted to explicit directed support/authorization edges. Billing denial has its own receipt/reason/zero-dispatch path, and the candidate path excludes Billing and generic membership. |
| P0.5 Incremental rendering | **PARTIAL** | Reducer coverage passes for add/update/remove/reset, duplicate delivery, stale/conflicting heads, replay scrub, position preservation, selection state, and invalid evidence. Actual browser focus/layout stability was **not run**. |
| P0.6 Cross-platform verified replay | **PARTIAL** | The replay command, authenticated snapshot, every streamed delta, final graph digest, truth labels, and zero authoritative state pass locally. Ubuntu CI is configured, but no hosted run exists for this uncommitted tree. |
| P0.7 Google ADK fake path | **PASS** | Source and consumer traverse the real Google ADK 2.5.0 Runner/session/tool adapter with distinct identities, a deterministic fake model, credentials removed, an outbound socket tripwire, zero external model dispatch, and no fallback. |
| P0.8 Isolated local Git result | **PASS** | Explicit approval creates one exact commit inside the retained fixture checkout. Parent, tree, paths, diff, message, idempotency, clean worktree, local author config, and no-push/PR/deploy fields are verified. Rejection creates none. |
| P0.9 One repository story | **PASS** | README, simple path, status, ADR, package metadata, contracts, CLI help, viewer truth copy, legacy Docker banner, and documentation history now agree. Shared legacy fixture fields remain operationally necessary but are provider-neutral and explicitly classified as compatibility-shaped rather than current driver proof. |
| Graph-necessity protocol | **PASS as a protocol** | [`docs/GRAPH_NECESSITY_EVAL.md`](docs/GRAPH_NECESSITY_EVAL.md) freezes the questions, answer key, five-stage replay, fair canonical flat comparator, counterbalancing, scoring, and kill criteria. |
| Graph-necessity result | **NOT RUN / TARGET NOT MET** | No participant row was fabricated. The required 4-of-5 result and measurable viewer advantage remain unproven. |
| Visual/manual exit | **NOT RUN / PARTIAL** | Static DOM, HTTP, projection, keyboard-handler, layout-coordinate, and accessibility-source checks pass. No 1280×720 screenshot, narrow screenshot, or keyboard-only browser session was available to inspect. |

## What changed during this review

### Product truth and contracts

- [`contracts/product_proof.json`](contracts/product_proof.json) is the canonical machine-readable proof matrix.
- [`contracts/golden_path.json`](contracts/golden_path.json) no longer calls the scripted actor Gemini or promises a commit it does not create.
- [`contracts/graph_mvp.json`](contracts/graph_mvp.json) uses provider-neutral `driver-selected` profile metadata.
- [`contracts/lineage_v2.json`](contracts/lineage_v2.json) and [`backend/graphene/models.py`](backend/graphene/models.py) cover rejection and local-result event types, truth authorities, scope metadata, and receipt references.

### Demo, provenance, and handoff

- [`backend/graphene/demo.py`](backend/graphene/demo.py) owns the three explicit drivers, real numbered branches, proof packets, and local-result verification output.
- [`backend/graphene/demo_adk.py`](backend/graphene/demo_adk.py) is the deterministic real-ADK Runner path.
- [`backend/graphene/lineage/human.py`](backend/graphene/lineage/human.py), [`backend/graphene/context/handoff.py`](backend/graphene/context/handoff.py), and [`backend/graphene/context/runtime.py`](backend/graphene/context/runtime.py) preserve TTY provenance and carry the chosen scope into the consumer context.
- [`backend/graphene/lineage/service.py`](backend/graphene/lineage/service.py) closes unusable handles after failure-receipt outages and requires durable invocation start for ADK/MCP tool calls.
- [`backend/graphene/lineage/store.py`](backend/graphene/lineage/store.py), [`backend/graphene/lineage/firestore.py`](backend/graphene/lineage/firestore.py), and [`backend/graphene/lineage/reducer.py`](backend/graphene/lineage/reducer.py) share semantic local-result validation on append and replay.

### Viewer and replay

- [`backend/graphene/viewer/projection.py`](backend/graphene/viewer/projection.py) builds the Review Brief, attention transitions, scope consequences, typed support paths, contextual labels, stage story, and explicit unknowns from verified events/references.
- [`backend/graphene/viewer/static/reducer.mjs`](backend/graphene/viewer/static/reducer.mjs) incrementally reconciles deltas and rejects stale or conflicting head envelopes before mutation.
- [`backend/graphene/viewer/static/viewer.mjs`](backend/graphene/viewer/static/viewer.mjs) retains selection/focus and limits arrow-key interception to the focused graph canvas.
- [`tests/fixtures/viewer_replay_source.json`](tests/fixtures/viewer_replay_source.json), [`scripts/generate_viewer_replay.py`](scripts/generate_viewer_replay.py), and the checked replay/digest now provide five deterministic stages, explicit opening, correct paths, one pending candidate checkpoint, and a fair flat comparator.

### Familiar endpoint

- [`backend/graphene/lineage/local_commit.py`](backend/graphene/lineage/local_commit.py) creates and verifies the approved commit only inside the isolated fixture checkout.
- [`backend/graphene/lineage/promotion.py`](backend/graphene/lineage/promotion.py) separates the retested base from the actual local Git outcome and preserves historical receipt readability.

### Tests and repository story

- Process, unit, integration, adversarial, frontend, replay-stream, ADK, local-Git, docs/link, and compatibility tests were expanded around the new behavior.
- [`README.md`](README.md), [`simplreadme.md`](simplreadme.md), [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md), [`DECISIONS.md`](DECISIONS.md), the privacy/threat-model docs, and [`docs/HISTORY.md`](docs/HISTORY.md) now identify current authority and historical/legacy surfaces.
- The root Docker/frontend path is persistently labeled compatibility-only and cannot be mistaken for authoritative v2 or Linux fixed-test support.

## Driver proof matrix

| Driver | Locally observed in this review | Proves | Does not prove |
|---|---|---|---|
| `verified-replay` | Command started/stopped; authenticated HTTP page and initial projection loaded; process test consumed all deltas to the checked final graph digest; no lineage database was created | Hash-checked checked-in fixture, decision-view behavior, typed context opening/reference, pending/cleared attention, and explicit unknowns | Captured live execution, human attestation, new tests, ADK, Gemini, a real local commit, or independent-agent behavior |
| `scripted-local` | Full simulated test seam completed; Billing denied at zero dispatch; consumer opened evidence; fixed tests passed; isolated local commit was created and verified; `--cleanup` deleted the runtime | Bounded protocol, policy/integrity behavior, real branch mechanics, retest, and local-only Git endpoint | Independent model behavior, ADK, Gemini, context efficacy, push, PR, or deployment |
| `adk-fake` | Full real Runner path completed with credentials unset, distinct source/consumer identities, zero external dispatch, local result, and cleanup | Real Google ADK Runner/session/tool routing through Graphene with a deterministic fake model | Gemini, autonomous intelligence, independent-agent quality, or external model behavior |

The full suite also executes actual PTY decision paths. The direct scripted and ADK commands above used the deliberately labeled simulated fixture seam so they could complete unattended; they are not human-attestation evidence.

## Automated and mechanical verification

| Command/check | Result |
|---|---|
| `uv lock --check` | **PASS** |
| `uv sync --frozen` | **PASS** |
| `uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py` | **PASS — 330 passed, 5 dependency warnings** |
| `uv run --frozen pytest -q tests/process/test_mcp_stdio.py` | **PASS — 6 passed** |
| `node --test frontend/test/*.test.mjs` | **PASS — 8 passed** |
| `node --test tests/frontend/*.mjs` | **PASS — 20 passed** |
| Both required `node --check` commands | **PASS** |
| `uv run --frozen ruff check backend tests scripts demo` | **PASS** |
| `uv run --frozen python scripts/generate_viewer_replay.py --check` | **PASS** |
| `git diff --check` | **PASS** |
| `uv build --out-dir <temporary-directory>` plus wheel-content inspection | **PASS**; ADK, local-commit, viewer, replay, and replay digest assets were present; temporary build output was removed |
| `graphene demo --driver verified-replay --no-open --exit-after-demo` | **PASS**; continuously labeled and reported zero authoritative state |
| Test-only unattended `scripted-local` and `adk-fake` full smokes with `--cleanup` | **PASS**; both created/verified isolated results and deleted their runtimes |
| Hosted GitHub Actions for the resulting tree | **NOT RUN**; there is no resulting commit or hosted workflow to claim |
| 1280×720, narrow, and keyboard-only browser inspection/screenshots | **NOT RUN**; no controllable browser was attached |

The five warnings were dependency deprecation/experimental ADK notices, not Graphene test failures.

## Visual and manual inspection record

No screenshot is attached, because claiming one without a controllable browser would be false. The in-app browser reported no available browser session.

Mechanical inspection did confirm:

- the authenticated loopback page serves the exact replay truth label;
- the Review Brief and all required section headings are present before the graph;
- the skip link, semantic landmarks, live regions, dialog labeling, range labeling, and keyboard instructions are present;
- the initial replay projection exposes exact unknown strings and no `human_attested` node;
- the five replay checkpoints progress to exactly one pending candidate decision and then clear it;
- the final projection exposes both changed paths, a passing bound test, `all_auth → app/auth/**`, an explicit typed context opening, a receipt-only replay outcome, and isolated local Git as not established in replay mode.

Before a public demo, attach a real browser and record the required desktop, narrow, and keyboard-only checks. This is the highest-priority non-code action.

## Side-effect and cleanup confirmation

- No implementation commit, push, pull request, deployment, cloud mutation, or real Gemini/model call occurred.
- The user's checkout was not committed or reset.
- Local Git commits existed only inside disposable fixture checkouts under owner-private temporary runtimes.
- Both direct live-driver runtimes were removed by `--cleanup`.
- The final replay server was stopped and created no authoritative database.
- The audit-scoped `caffeinate` process was stopped before handoff; no audit demo server was left behind.

## Graph-necessity status

[`docs/GRAPH_NECESSITY_EVAL.md`](docs/GRAPH_NECESSITY_EVAL.md) is now runnable and fairer: viewer and flat conditions derive from the same verified replay, the flat condition contains each final public item/relationship/fact/support path/unknown once, and participant results remain explicitly **NOT YET RUN**.

The graph has not earned a primary-product claim yet. The Review Brief already answers most review questions; the bubbles currently earn their place as an inspectable evidence-path surface. Run the five-person crossover before judging. If fewer than four of five developers answer all eight questions within 90 seconds, or the viewer does not reduce time/errors versus the flat transcript, keep the Review Brief primary and demote bubbles to an optional evidence inspector.

## Remaining unknowns and genuine blockers

1. **Product advantage:** no evidence yet shows faster review, fewer mistakes, or a necessary graph.
2. **Visual usability:** no real browser record proves first-viewport readability, narrow layout, label overlap, or keyboard-only flow.
3. **Hosted portability:** Ubuntu replay/fail-closed CI is configured but not observed for a resulting commit.
4. **Agent quality:** `scripted-local` is deterministic and `adk-fake` uses a fake model. Neither proves independent coding-agent behavior or Gemini quality.
5. **Context efficacy:** compilation, inclusion, injection, opening, and temporal ordering do not prove that context caused or improved the later edit.
6. **Trust root:** artifact authenticity is local integrity, not external signing. Firestore is tested for metadata semantics but is not a shipped durable private-artifact cloud path.
7. **Legacy complexity:** the compatibility HTTP/frontend/Docker surface remains in-tree. It is now clearly labeled, but still adds cognitive load and should receive no new product work.

## Recommended hackathon demo order

1. Start `verified-replay`. In the Review Brief, show the exact two changed paths, bound passing test, simulated scope correction, Billing zero-dispatch denial, included scope, explicit consumer opening, and unknowns.
2. Scrub to the candidate checkpoint so the single pending decision is visible, then advance once to show it clear.
3. Select the promotion receipt and Billing denial separately to demonstrate that verified support paths are typed and do not blend unrelated branches.
4. Run either live driver. Read the terminal's **HANDOFF PROOF**, explicitly choose the candidate, and finish on the printed `git show` command plus “not pushed / no PR / no deployment.”
5. End with the boundary: replay is a fixture, scripted-local is a bounded workflow fixture, ADK fake proves integration, and none is Gemini or autonomous-agent proof.

## Focused worktree summary

At handoff, the sprint spans **74 tracked modified files** (`5,705` insertions and `710` deletions) plus **14 untracked files**, including the prompt and this review. The working tree has **88 changed entries** in total.

The large delta is primarily the already-uncommitted product-proof sprint reviewed here, not a commit made by this audit. No destructive reset or checkout operation was used.

## What the reviewer can now answer

1. **What needs attention?** The replay shows exactly one pending candidate decision at its decision checkpoint and no unresolved Graphene decision after the matching approval.
2. **What changed?** `app/auth/limiter.py` and `tests/test_security_policy.py`, with one captured hunk and no public raw diff.
3. **What supports it?** Explicit changed-path → changeset/hunk → passing bound-test → candidate → approval → promotion relationships; unrelated Billing and generic membership are excluded.
4. **Where did a human intervene?** Scope, correction, memory, and promotion decisions are visible with exact `human_attested` or `simulated_fixture` text labels.
5. **What is unknown?** Causality, whole-repository activity, shell/editor activity, external outcomes, hidden reasoning, and anything outside the six scoped operations remain explicit.
6. **What entered the handoff?** The approved Auth memory scope and included references entered; Billing received zero evidence, memories, paths, tools, and model dispatch.
7. **What opened that context?** Consumer sequence 4 records a runtime-observed `open_evidence` operation with a typed `opens_reference` relationship to the injected context brief.
8. **What outcome exists?** Replay proves a Graphene promotion receipt only; approved live fixtures prove an isolated local commit. Neither proves push, PR, deployment, Gemini, or independent-agent success.

Graphene should keep the Review Brief as the primary surface unless real participants demonstrate that the graph materially reduces review time or errors. If that evidence does not arrive, demoting the bubbles is the correct product decision—not a failure of the integrity layer.
