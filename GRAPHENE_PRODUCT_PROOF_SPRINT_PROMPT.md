# Graphene Product-Proof Sprint

> Copy this entire prompt into the implementation agent. This is an implementation sprint, not another ideation pass.

## Mission

Work in `Alex-lop/Graphene`, starting from the latest `main`. The audit baseline was commit `cf22c93f9001003f0949112ab7a588378c304bb6` ("Improved simple demo implemenation and implemention of lineage and graph UI"). If `main` has moved, inspect and report the delta before editing; do not blindly force the repository back to this SHA.

Graphene's integrity machinery is strong. Its current product proof is not. Fix that gap without broadening Graphene into a repository scraper, generic observability platform, knowledge graph, or multi-agent control plane.

The sprint succeeds when an unfamiliar developer can use the visual surface to make one bounded review/handoff decision, understand exactly what Graphene verified, distinguish it from what Graphene did not observe, and see a familiar local Git result. The same story must work as an easy replay on any common development OS and as an honestly labeled Google ADK integration proof.

## Operating mode

1. Read `AGENTS.md` and all repository-local instructions first.
2. Record `git status --short`, current HEAD, and the existing test baseline. Preserve every pre-existing user change. Never use destructive reset/checkout commands.
3. Use subagents in parallel, with non-overlapping ownership:
   - viewer projection, decision brief, live reducer, and frontend tests;
   - demo drivers, ADK integration, human provenance, and process tests;
   - product wording, canonical docs/contracts, replay path, and doc tests.
   Keep one integrator responsible for shared event/model/schema changes.
4. On macOS, use `caffeinate` for long-running test and demo verification. Scope it to the active work, record its PID, and stop it before handoff. Do not leave an orphan process.
5. Work in short verified loops: inspect -> write a failing test -> implement -> run the narrow test -> inspect the rendered result -> run the broader suite.
6. Do not commit the implementation repository, push, open a PR, deploy, call Gemini, or use cloud credentials unless the user separately authorizes it. The isolated fixture commit required later in this prompt is a product behavior under test, not authorization to commit the implementation work. Do not silently fall back between demo drivers.
7. If a requirement conflicts with an existing privacy, integrity, or fail-closed invariant, preserve the invariant and report the conflict rather than weakening it.

## Brutally honest premise

At the audited commit:

- The append-only v2 lineage, scope enforcement, private/public evidence boundary, read-only viewer, deterministic replay, fresh runtime identities, Billing denial, and test coverage are credible engineering.
- The default `scripted-local` demo is a deterministic workflow fixture. It directly chooses the reads, exact edits, regression test, handoff, and expected result. It is not proof that an independently behaving coding agent did those things.
- A user can ignore the graph, accept the suggested terminal answers, and reach the golden result. The graph currently displays an audit topology after the meaningful decisions have effectively been predetermined.
- Human choices are mostly ceremonial: a non-golden answer becomes `DemoError` instead of a legitimate recorded branch.
- The viewer shows internal entities and generic evidence bubbles better than it answers a reviewer's questions. Its current "Evidence path" computes broad graph connectivity across relations that do not all constitute support.
- Unknowns are counted but not actually shown. Simulated fixture decisions can look success-green. "Promotion" currently ends in a local Graphene receipt and a field named like a reconstructed commit can contain the base SHA.
- The README, implementation status, golden-path contract, package metadata, legacy Docker entry point, and historical product documents disagree about what is current.
- The macOS-only live workflow is defensible for secure fixed-test execution, but it makes the demo inaccessible to many judges. The solution is an honest cross-platform replay, not a weaker Linux executor.

Treat this as the central product risk:

> Graphene currently proves its machinery more convincingly than it proves that the machinery helps a developer make a better or faster decision.

## Product decision for this sprint

Do not keep six competing product identities. Use this one:

> **Graphene is an evidence-backed review and handoff layer for a developer supervising bounded coding-agent work. It shows the captured edits, tests, human corrections, approved context, and explicit unknowns behind a candidate, then passes only approved evidence into the next run.**

Define the product in four lines on the first screen of the canonical README:

- **Primary user:** a developer supervising or taking over a coding-agent change.
- **Painful moment:** deciding whether a candidate is trustworthy after a long run, correction, or handoff without reconstructing a transcript.
- **Decision:** approve, reject, or hand off that exact candidate and its bounded evidence.
- **Result:** a faster, more legible review with fewer unsupported changes, missed tests, and lost corrections.

The visual graph is not the product by itself. It earns its place only if it helps that decision. Integrity, replay, policy, memory, and promotion are supporting mechanisms.

### Claim discipline

Use proof-level language everywhere:

| Mode | What it proves | What it must never claim |
|---|---|---|
| `verified-replay` | The checked-in verified public lineage and decision-view experience | Live execution, human attestation, ADK, Gemini, or new test execution |
| `scripted-local` | The bounded protocol, policy enforcement, integrity, interactive choices, retest, and isolated local Git result | Independent agent/model behavior or Google ADK execution |
| `adk-fake` | Real Google ADK Runner/session/tool routing through Graphene with a deterministic fake model | Gemini, autonomous intelligence, or real-model quality |
| future external-live mode | Only the exact behavior observed in a separately credentialed run | Any silent substitution by fake or scripted execution |

In the scripted path, replace "Agent A," "fresh agent," and similar language with **workflow fixture**, **source runtime**, and **fresh isolated consumer runtime**. Use "agent" only on a path that actually uses an agent runtime. Prefer "everything Graphene verified inside this bounded run" over "what the agent actually did."

Do not claim that approved memory caused a later edit. The current evidence can establish that context was compiled, included, injected, opened/referenced, and followed by later actions. Timing and delivery do not establish causality or usefulness.

## How to treat the sixteen critiques

| Critique | Sprint decision |
|---|---|
| Product identity is too broad | **Adopt.** Recenter on evidence-backed review and handoff. |
| User, pain, decision, and result are unclear | **Adopt.** Put the four-line definition above the fold. |
| The graph may be decorative | **Adopt and falsify.** Make it a decision surface, then test it against a flat transcript. |
| The opening promise exceeds six-operation capture | **Adopt.** Narrow the promise and place the capture boundary beside it. |
| `scripted-local` is not real agent/ADK proof | **Adopt.** Label it honestly and add a real ADK Runner + fake-model driver. |
| Memory/handoff value is circular | **Adopt.** Claim delivery, not improvement; defer efficacy claims until a fair independent comparison exists. |
| Technical proof substitutes for product proof | **Adopt.** Add decision-comprehension criteria and a falsification protocol. |
| The trust boundary limits adoption | **Keep the boundary.** Add cross-platform verified replay; do not weaken isolation or pretend Linux fixed-test parity. |
| Human gates are ceremonial | **Adopt.** Implement real approve/reject/narrow/broad branches with durable consequences. |
| Visualization is cognitively weak | **Adopt.** Lead with a deterministic review brief and stage story, with topology as inspectable evidence. |
| Explicit lineage is too weak for relevance | **Reshape, do not infer.** Use typed explicit support references and show "not established" when evidence is absent. |
| Broad language conflicts with a narrow fixture | **Adopt.** Make macOS/Auth/six-operation limits immediate and visible. |
| There is no familiar endpoint | **Adopt.** End an explicitly approved live fixture in a verifiable local commit inside the isolated checkout; never push. |
| Differentiation is not visceral | **Adopt.** Center approved-context inclusion/exclusion and the review decision, not bubble aesthetics. |
| Repository complexity obscures the canonical path | **Adopt.** Establish one current source of truth and archive/supersede stale narratives. |
| Future graph-to-agent use may amplify errors | **Defer.** Keep the viewer read-only and do not feed graph-derived context back into an agent this sprint. |

## Non-negotiable boundaries

Preserve these even when a broader feature would make the demo look more complete:

- Terminal-first authority. The browser remains read-only and non-authoritative.
- A bounded, explicit, verified working set. Preserve the six service operations and fail closed outside them.
- No whole-repository crawler, passive shell/editor observer, screen recorder, hidden-reasoning capture, chain-of-thought capture, or inferred causal/relevance edge.
- No raw source, diff, prompt, stdout, secret, credential, or private evidence in the public viewer, replay fixture, URL, logs, or downloadable artifact.
- Keep integrity, provenance, truth levels, hash verification, privacy projection, and explicit unknowns.
- Do not silently hide invalid evidence. `EVIDENCE_INVALID` supersedes all normal UI state.
- Do not broaden to a graph database, cloud service, generic orchestration GUI, fleet dashboard, IDE extension, arbitrary repository support, or multiple agent frameworks.
- Do not use the graph as agent input yet.

## P0 implementation work

Complete every P0 item before stretch work.

### P0.1 — Fix authority and human-attestation provenance

The public CLI must never mint `human_attested` merely because a caller omitted an internal simulation flag.

Implement:

- Interactive human attestation requires a real TTY at the decision point.
- Piped stdin, subprocess input, test automation, and replay may only produce an explicitly labeled `simulated_fixture` decision, or must fail closed before writing a purported human decision.
- Record a bounded public operator label and optional bounded rationale. Do not collect OS identity, email, or other unnecessary personal data.
- Keep simulation provenance impossible to confuse with `human_attested` in storage, terminal copy, viewer nodes, summaries, and exports.
- Preserve compatibility for verified historical fixtures without rewriting their provenance.

Acceptance tests:

- A PTY process test covers a real approve branch and a real reject branch.
- A piped-stdin test proves it cannot create `human_attested` events.
- An automated fixture test asserts every decision is `simulated_fixture` at the node and summary levels.
- A tampered/invalid ledger cannot be rendered as a pending or successful human decision.

### P0.2 — Make every human gate a real branch

Keep the golden route easy, but stop telling the user that disagreement is a program error.

Implement bounded numbered choices with concise consequences:

1. Scope: both existing contract choices, `all_auth` and `rate_limiter_only`, are valid. The chosen scope must change the allowed memory/context surface and the viewer must show that consequence.
2. Memory: approve or reject. Rejection creates a durable decision, no approved memory revision, no misleading injected-context claim, and a clean final state.
3. Final candidate: explicitly create the isolated local commit or reject. There is no Enter-to-commit default.

Rules:

- A legitimate rejection exits cleanly, remains inspectable, and is not `DemoError`.
- The viewer shows why no handoff, approval, or local commit exists after rejection.
- Historical denials remain visible but are not shown as current unresolved work.
- The terminal remains the only place that can decide. Before each prompt, print the same public candidate/decision identifier shown by the viewer and provide a safe focus anchor; do not weaken loopback token handling or leak a token into durable artifacts.
- Do not add arbitrary free-form scope. Keep choices frozen and auditable.

Acceptance tests:

- Process tests cover both scope choices, memory approve/reject, and candidate commit/reject.
- Every branch has the correct terminal status, event sequence, viewer attention state, and exit code.
- Rejection produces neither a completion receipt nor a Git commit.
- The broad and narrow scope branches produce demonstrably different allowed/included context without inferred relevance.

### P0.3 — Turn the viewer into a decision surface

Keep Cytoscape.js and the Bubble Lineage aesthetic, but demote the undifferentiated topology. The first viewport must answer a review decision before it asks the user to explore nodes.

Add a deterministic **Review Brief** above or beside the graph with these sections:

- **Needs attention now**
- **Candidate / changed paths**
- **Verified evidence**
- **Human intervention**
- **Inherited context: included and excluded**
- **Outcome**
- **Unknown / not captured**

Every displayed fact must be derived from a committed event, explicit reference, receipt, or digest. Each fact must expose its truth level and focus the exact supporting node(s)/edge(s). If the fact is missing, render **not established by captured evidence**; never infer it.

For the checked replay, an unfamiliar reviewer must be able to see, without opening the README or terminal:

- every public-safe changed-path reference, or an explicit statement that exact paths were not captured;
- the hunk count and bound passing test evidence;
- the human correction/scope decision with its real truth label;
- the denied Billing handoff and zero model dispatch;
- the source-to-consumer context inclusion/injection/opening references;
- the final outcome, including whether it is only a Graphene receipt or an isolated local commit;
- that no PR, push, deployment, or activity outside Graphene's six operations was observed.

Fix the projection rather than hardcoding fixture prose:

- Publicly project safe changed-path/bound-path references and explicit links from changed file -> changeset/hunk -> bound test -> candidate -> approval -> local result. Do not expose raw diffs or file contents.
- Give duplicate generic evidence nodes contextual labels such as source/consumer, stage, revision, and test role, or collapse them deterministically with a visible count and an inspectable expansion.
- Use visible stage/run boundaries: source work -> human correction/scope -> approved handoff -> isolated consumer work -> candidate decision -> local result.
- Make human intervention and denied/blocked branches legible without relying on color alone.
- Default to the current decision neighborhood/story, not all implementation objects. The full bounded audit topology remains reachable. Always show total, visible, filtered, and collapsed counts separately.
- At 1280x720, the primary story must be readable without pressing Organize, manual dragging, or zooming. At narrow width, the same facts remain keyboard reachable.

Truth semantics:

- `simulated_fixture`, `human_attested`, `policy_authoritative`, `runtime_observed`, and `server_derived` get visible text labels, a legend, and non-color cues.
- A simulated approval must never share the same badge/treatment as a human-attested approval.
- Green/success styling must be supported by an explicit positive result, not merely by the existence of an event.
- Render the actual unknown strings; never reduce them to only "3 unknowns."
- Show node-specific limitations and the mode/capture boundary. Distinguish omitted-by-cap, collapsed, and filter-hidden data.

Attention semantics:

- Derive attention only from unmatched committed transitions, never from guessed importance.
- During each live gate, exactly one attention item identifies the pending decision and its supporting facts.
- It clears only when the matching committed approval/rejection arrives.
- A complete replay says "No unresolved Graphene decision" while preserving historical denials.
- `EVIDENCE_INVALID` overrides every other attention state.

### P0.4 — Make “Evidence path” truthful and typed

The current connected closure is not an evidence path. Do not treat `contains`, `performed`, `recorded`, `observed`, `continued_as`, and `evidenced_by` as interchangeable proof.

Implement explicit relationship classes, for example:

- verified support/reference;
- authorization/approval;
- inclusion/injection/opening;
- handoff continuation;
- integrity/sequence;
- membership/layout-only.

Only an allowlisted, directionally valid support relationship may appear in **Verified support path**. Membership, generic containment, chronological adjacency, and the unrelated Billing-denial branch must not be highlighted as proof of a promoted/committed candidate.

Acceptance tests:

- Selecting the final local result highlights only its explicit support chain through candidate, approval, passing bound test, hunk/changeset, and changed path.
- Selecting Handoff Denied shows its explicit decision receipt, reason, and zero-dispatch evidence.
- The final candidate support path excludes the unrelated Billing branch.
- Edge directions and allowlists are fixture-tested.
- UI copy says "verified support relationships," never "cause," "reasoned," or "made the agent."

### P0.5 — Make live rendering feel live, not like repeated redraws

Keep the ledger/projection as source of truth. Reconcile new snapshots incrementally in the browser, or add a small typed delta contract, so a new event does not destroy and rebuild the whole visual state.

Acceptance:

- Existing nodes retain stable positions when a new node/edge arrives.
- Filters, selection, drawer, replay cursor, and keyboard focus survive a normal update.
- Only the current explicit action pulses; historical activity does not continue pulsing.
- Reconnect/reset remains available and fail-closed, but a normal event does not trigger a full re-layout.
- Reducer tests cover add/update/remove/reset, reconnect, ordering, duplicate delivery, and invalid deltas.

### P0.6 — Add an easy cross-platform verified replay

Add:

```bash
uv run --frozen graphene demo --driver verified-replay
```

Requirements:

- It starts the same authenticated loopback read-only viewer using checked-in, hash-verified, public-safe fixture data.
- It does not require macOS, `/usr/bin/sandbox-exec`, Google credentials, a model, or live test execution.
- Terminal and viewer continuously label it: **VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION**.
- It creates no authoritative lineage/state writes, promotion/commit, model-dispatch, or human-attested events; temporary loopback-server mechanics must remain non-authoritative and disposable.
- There is no silent fallback. On an unsupported live-workflow host, print the exact replay command and exit appropriately.
- Ubuntu CI starts the replay, fetches the viewer snapshot, validates the truth labels, and proves no authoritative state was created.

Make this the first "see it quickly" path in `simplreadme.md`. Keep the macOS workflow fixture immediately below it as the interactive protocol proof.

### P0.7 — Add a complete, honestly labeled Google ADK path

Add:

```bash
uv run --frozen graphene demo --driver adk-fake
```

Requirements:

- Use the real Google ADK `Runner`, sessions, and Graphene tool adapter for the source and isolated consumer tool steps.
- Use a deterministic fake model. It may provide a frozen sequence for reproducibility, but tool calls must actually traverse ADK and the existing bounded service; do not replace those steps with direct demo service calls.
- Reuse the same human gates, ledger, privacy projection, viewer lifecycle, support paths, local commit/reject outcome, and fail-closed scope checks.
- Source and consumer have distinct run/session/invocation identities.
- Lineage makes the ADK adapter identity visible without claiming Gemini.
- It runs with Google API keys/project variables unset and performs zero external model calls.
- Every surface says **REAL ADK RUNNER + DETERMINISTIC FAKE MODEL — NOT GEMINI OR INDEPENDENT-AGENT PROOF**.
- No silent fallback to `scripted-local` or replay.

Do not add or run a Gemini/live driver in this sprint. A future live mode must be separately authorized, credential-gated, visibly fail if unavailable, report the observed provider/model identity, and never fall back.

### P0.8 — End the approved live fixture in a familiar local Git result

After explicit final human approval, create a Git commit **only inside the retained isolated fixture checkout**. Never mutate the user's checkout, push, create a branch on GitHub, or imply deployment.

Requirements:

- The command is labeled **Approve and create isolated local commit**.
- The receipt returns a truthful `local_commit_sha`, parent SHA, tree SHA/digest, candidate digest, changed paths, bound test receipt, and approval reference.
- The commit contains exactly the approved candidate changes; no viewer/runtime/database artifacts.
- Configure only fixture-local author metadata if required. Do not read or alter global Git configuration.
- Idempotent retry returns the same result and does not create a second commit.
- `git cat-file -e`, parent, tree, and diff are verified in tests.
- The viewer says **local isolated commit — not pushed / no PR / no deployment**.
- A rejected candidate creates no commit and no success receipt.
- Correct the misleading `reconstructed_commit_sha` semantics. Prefer a compatible migration to `local_commit_sha`; if old data must remain readable, label it as legacy rather than overloading the field.

If this cannot be implemented without weakening the v2 integrity boundary, stop and document the exact invariant conflict. Do not keep calling a base SHA a reconstructed commit and do not silently claim a Git result that does not exist.

### P0.9 — Make the repository tell one current story

Update canonical sources together:

- `README.md`
- `simplreadme.md`
- `IMPLEMENTATION_STATUS.md` or a replacement clearly designated as authoritative
- `DECISIONS.md`
- `pyproject.toml` description
- demo contract(s)
- CLI help
- viewer truth copy
- root Docker/legacy entry-point documentation

Required cleanup:

- Remove hardcoded stale base-SHA and test-count prose. Prefer commands, generated facts, and links to actual workflow runs.
- Remove or fix dead relative links, including references to absent status/evidence files.
- Split or update `contracts/golden_path.json`: a machine-authoritative scripted fixture must not call its actor Gemini, describe a legacy three-tool prompt, or promise a commit that the current path does not create. Preserve history with an ADR; do not silently mutate the meaning.
- Mark `IDEA_EVALUATION.md` and superseded implementation prompts/judge reports as historical, or move them under an archive path with banners and an index. Do not erase useful history.
- Make the root Dockerfile's compatibility-only legacy HTTP path impossible to mistake for authoritative v2. Do not claim that Linux can execute v2 fixed tests.
- State the six-operation boundary, macOS live-execution boundary, Auth fixture, Billing zero-dispatch denial, and truth-level proof matrix near the quickstart.
- Keep graph-to-agent consumption explicitly deferred.
- Never claim new GitHub CI is green until a run for the resulting commit actually exists. Report local verification as local.

Add CI/doc contract tests that:

- every relative Markdown link resolves;
- canonical docs do not contain stale commit snapshots or uncommitted-work claims;
- scripted/replay copy cannot contain Gemini or independent-agent claims;
- package/Docker metadata identify authoritative vs compatibility paths;
- CLI `--help`, README, `simplreadme.md`, and driver truth labels agree.

## Product falsification, not manufactured validation

Create `docs/GRAPH_NECESSITY_EVAL.md` with a reproducible comparison between:

1. the final decision-first viewer; and
2. the same public information as a flat terminal transcript/event list.

Ask an unfamiliar developer to answer, without the README:

1. What needs attention now?
2. What changed?
3. Which verified evidence supports each changed path?
4. Where did a human intervene, and was it real or simulated?
5. What remains unknown/outside capture?
6. What entered—and did not enter—the handoff?
7. What later operation explicitly opened/referenced that context?
8. What final outcome exists, and what external outcome does not?

Use a frozen answer key derived from public events. Record correctness and time, but leave the results table explicitly **not yet run** unless real participants actually complete it.

Manual exit target:

- At least 4 of 5 unfamiliar developers answer all eight correctly within 90 seconds.
- The viewer materially reduces time or errors versus the flat transcript.

Kill criteria:

- If the viewer provides no measurable advantage, make the Review Brief primary and demote the bubble graph to an evidence inspector.
- If approved-context delivery does not improve a fair independently executed continuation, remove "improves agent behavior" from the headline; keep only the proven delivery/audit claim.
- If there is no real live-agent path, position Graphene as a bounded provenance/review protocol with ADK integration proof, not as a demonstrated autonomous coding-agent product.

Do not fake user-study results, intentionally cripple a no-context baseline, or hardcode a consumer outcome and present it as evidence of memory efficacy.

## Required automated verification

Add or extend tests for every acceptance criterion above, especially the cognitive/product claims that current tests do not cover.

At minimum:

- projection/privacy contract tests for every new public field and continued absence of raw source, diff, prompt, stdout, secrets, and credentials;
- stage-by-stage frontend fixture tests for Review Brief answers, attention transitions, truth labels, typed support paths, inclusion/exclusion, and final outcomes;
- stable incremental-render tests;
- PTY human approval/rejection and non-TTY provenance tests;
- both scope branches and both reject branches;
- `verified-replay` Linux process smoke;
- complete `adk-fake` Runner lifecycle with credentials unset and zero external dispatch;
- isolated local-commit parent/tree/diff/idempotency tests;
- doc/link/claim contract tests;
- keyboard/accessibility parity between the visual story and the linear evidence list;
- desktop and narrow-layout inspection with no overlapping primary labels.

Run the repository's CI-equivalent commands from `.github/workflows/ci.yml`, including:

```bash
uv lock --check
uv sync --frozen
uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py
uv run --frozen pytest -q tests/process/test_mcp_stdio.py
node --test frontend/test/*.test.mjs
node --test tests/frontend/*.mjs
node --check frontend/src/app.mjs frontend/src/graph.mjs frontend/src/workflow.mjs
node --check backend/graphene/viewer/static/reducer.mjs backend/graphene/viewer/static/viewer.mjs
```

On Linux, run only the platform-safe/fail-closed suite plus the new verified-replay smoke; do not weaken or skip the macOS sandbox contract to make tests pass. If the working environment cannot run a required platform-specific check, say **not run** and give the exact command—never imply success.

Manually inspect at least:

- final approved/committed replay;
- narrow-scope branch;
- memory rejection;
- final candidate rejection;
- simulated replay truth labels;
- invalid-evidence state;
- 1280x720 and narrow responsive layouts;
- keyboard-only navigation and readable unknowns.

## Explicitly deferred or rejected

Do not implement any of these in this sprint:

- graph-to-agent retrieval, graph-generated prompts, inferred relevance, or automatic context selection;
- whole-repository indexing, passive shell/editor capture, screen recording, or hidden reasoning;
- graph databases, generalized orchestration, multi-framework support, cloud deployment, Firestore, fleet views, multi-tenancy, retention systems, or broad policy administration;
- Linux fixed-test execution without an isolation design equivalent to the supported macOS sandbox;
- arbitrary confidential repositories or expansion beyond the sanitized Auth/Billing fixture;
- a real Gemini call, credentials workflow, GitHub push, PR creation, or deployment;
- visual community detection or bubble size/color semantics that imply importance, correctness, or causality without explicit evidence.

## Completion report

Return a concise evidence-backed handoff containing:

1. current HEAD and whether it differed from the audit baseline;
2. the final one-sentence product thesis;
3. files changed, grouped by product truth, demo/provenance, viewer, endpoint, tests, and docs;
4. a proof matrix for all shipped drivers;
5. screenshots or recorded visual checks for the primary states;
6. exact test commands and pass/fail/not-run results;
7. confirmation that no real model, network deployment, user checkout, push, or PR was touched;
8. remaining unknowns and unproven product claims;
9. the graph-necessity evaluation status, with no fabricated participants/results;
10. `git status --short` and a focused diff summary.

Do not end with "the graph is better" because the UI is prettier or the tests are green. End with the exact review questions it now answers, the explicit evidence behind those answers, and the remaining conditions under which the graph should be demoted.
