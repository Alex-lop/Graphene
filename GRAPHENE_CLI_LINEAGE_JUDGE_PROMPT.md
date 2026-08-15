# Graphene CLI Lineage — Judge and Pivot Prompt

> **Historical judge prompt — not current product truth.** It records the question posed at that checkpoint, not current behavior. See [`docs/HISTORY.md`](docs/HISTORY.md).

Paste the prompt below into a fresh high-reasoning root agent working in `Alex-lop/AllThingsAgenticHackathon`.

---

## Prompt

You are the lead product judge, staff agent architect, and root investigator for `Alex-lop/AllThingsAgenticHackathon`.

Your job is not to defend the current Graphene plan or immediately add more features. Your job is to determine the strongest, most memorable, and actually buildable version of the idea for the All Things Agentic Hackathon, then leave Alex with one decisive direction and an execution-ready Markdown brief.

Approach this as if you will personally judge the final four-minute demo. Be candid, specific, and willing to change the name, product framing, terminal interaction, event model, graph vocabulary, storage design, or parts of the current implementation. Preserve verified work when it provides real leverage; do not preserve sunk cost merely because it exists.

### 1. Begin from the real repository, not this summary

Inspect the latest `main` branch and recent Git history. At minimum, read:

- `README.md`
- `DECISIONS.md`
- `IMPLEMENTATION_STATUS.md`
- `ULTRA_MVP_EXECUTION.md`
- `POST_PHASE0_GRAPH_MVP_ULTRA_PLAN.md`
- `contracts/**`
- `backend/graphene/**`
- `frontend/**`
- `demo/**`
- `tests/**`
- the latest commits and changed files

Run the existing demo and test commands where the environment permits. Compare the claims in the documentation with the code paths that are actually executed. Treat test output, source, persisted artifacts, and real cloud/model evidence as stronger than prose.

The last known public baseline was `main` at merge commit `c3d4bbd50ba6f0c0b2e9a729b78ba9ac50cece03`, but verify that before relying on it.

### 2. Known baseline to verify, challenge, and update

The current build appears to have a strong local enforcement foundation:

- FastAPI lifecycle service and immutable Pydantic contracts.
- In-memory, atomic JSON, and bounded Firestore store adapters.
- Scoped `read_file`, `write_file`, and fixed-test tools.
- Exact Git patch and hunk extraction with canonical hashes.
- Human-approved memory revisions.
- Catalog profiles and a permission-scoped context packet.
- Fail-closed completion and promotion receipts.
- Deterministic graph reconstruction with caps and honest truncation.
- A browser-based SVG graph, exact-diff drawer, and proof list.
- Local adversarial, restart, idempotency, and deterministic-loop tests.

However, the current product also appears materially weaker than its README may initially suggest:

- The verified default executor is deterministic and performs frozen replacements in a tiny authentication fixture. Real Gemini/ADK execution has not yet been demonstrated in accepted evidence.
- Real Firestore and Cloud Run remain unverified unless the repository has changed since the last audit.
- The graph is reconstructed after a candidate exists; it is not a live record of how the agent traversed the repository.
- There is no append-only runtime event spine for reads, searches, tool calls, intermediate edits, questions, answers, or test starts.
- The current proof records are synthesized in a batch after execution, and several share the same timestamp.
- ADK events appear to be discarded except for limited model metadata.
- Files that were read but not edited are absent from the graph.
- The context packet binds selected graph node IDs, yet the current model prompt appears to receive only the task and approved memory text—not the selected evidence itself.
- The primary product surface is a website, while the more natural setting for a coding-agent control layer may be the terminal where the work occurs.
- The Billing profile denial is credible as a deterministic contract test but not yet a strong visible runtime interaction.

Confirm or correct each point. Do not repeat an outdated critique if the implementation has moved forward.

### 3. The new product hypothesis

Evaluate this as a hypothesis, not a predetermined answer:

> Graphene should become a live, terminal-native lineage layer for coding agents. As a real agent reads files, searches a repository, edits code, runs tests, asks for clarification, receives human feedback, and attempts completion, Graphene records observable events and grows a compact working-set graph in the CLI. The trusted part of that lineage can then explain why a change exists and become a bounded, permission-scoped briefing for a fresh agent.

The strongest differentiation may be:

> Most agent traces are flight recorders. Graphene turns the flight recorder into the next agent's briefing.

Or, in user language:

> Watch the agent work, teach it once, and hand the exact lesson—not the whole transcript—to the next agent.

Do not keep either line if you can produce something more precise and less generic.

The graph must be operational. A live animation of files and tool calls is ordinary agent observability. The product becomes interesting only if the same trusted history:

1. helps a human answer why a file or hunk changed;
2. accepts feedback anchored to exact observed evidence;
3. preserves that feedback as approved, scoped memory;
4. creates the minimal authorized handoff for a genuinely fresh agent;
5. affects that new agent's actual invocation and behavior;
6. denies irrelevant or unauthorized context; and
7. still prevents untested or unapproved work from being promoted.

### 4. Product principles to preserve unless you disprove them

These are proof requirements, not fixed library or UI choices:

- The terminal should be the primary product surface for the next MVP. The existing website may remain as a secondary artifact if it is cheap, but it should not dictate the architecture.
- Capture what can be observed: tool calls, file reads, canonical patches, tests, feedback, memory, policy decisions, and human approval. Never claim to expose private chain-of-thought or the model's full internal understanding.
- The graph should represent the agent's bounded working set, not pretend to map an entire large codebase.
- Observed runtime lineage, advisory code relationships, and authoritative permission policy must remain separate layers.
- Every causal edge must resolve to stored evidence. Temporal adjacency is not proof of causality.
- A prior agent's path is useful context, not complete codebase truth. The new agent needs a scoped search or expansion escape hatch so a mistaken prior path does not become a permanent blind spot.
- The graph is a context index and explanation surface; it is not the authorization database.
- A fresh agent receives no prior conversation history or hidden reasoning. It receives an explicit, persisted packet of approved memories, relevant evidence references, required tests, allowed paths, and allowed tools.
- Human feedback and approval remain real lifecycle actions, never model-authored tools.
- The existing fail-closed candidate/test/promotion binding should be reused unless you find a simpler mechanism with equal integrity.
- Submit to one core track. The current default should remain **Collaborative Partner**, with one honest Fleet-shaped handoff primitive, unless your audit produces a compelling reason to change it.

The official hackathon currently describes Collaborative Partner around stateful dialogue, real-time retrieval, persistent memory, and adaptation. It describes Fortified Enterprise Fleet around discovery, orchestration, durable state, observability, and security enforcement. Verify the live rules and resources yourself. Do not present the project as winning two tracks at once.

### 5. Do not confuse visual encoding with the product

Alex's desired terminal graph is intentionally simple. Explore it, but do not let graph aesthetics consume the architecture phase.

Potential visual semantics:

- A file node's footprint may use a capped, log-scaled bucket derived from baseline lines or bytes.
- Edit heat or fill may reflect the changed-line ratio.
- Always show exact `+added/-deleted` counts so the visual is auditable.
- A new file should have a distinct treatment instead of an infinite edit ratio.
- Borders, icons, or labels should distinguish read-only, edited, tested, feedback-linked, denied, and promoted states without relying only on color.
- Keep baseline size stable during a run so nodes do not constantly jump.
- Collapse directories and cap the focused display to roughly 12–15 meaningful files for the demo.
- Exact code and diffs belong in an inspector, not inside bubbles.
- File size must never be mislabeled as importance.

You may choose Rich, Textual, a simpler ANSI renderer, or another terminal approach after inspecting the repository. Keep the event/reducer contract headless and testable, and preserve a machine-readable `--json` mode. A force layout, 3D graph, or graph database is not required.

### 6. Investigate an event-first architecture

Determine whether the cleanest thin architecture is:

```text
real Gemini + Google ADK agent
→ scoped read/search/patch/test tools and ADK callbacks
→ append-only persisted runtime events
→ lightweight publish/subscribe update
→ deterministic graph reducer
→ live terminal projection
→ bounded context-packet compiler
→ fresh scoped agent
```

The exact schema is yours to decide, but examine an envelope containing:

- stable event ID;
- run, session, profile, and tool-call IDs;
- monotonic per-run sequence;
- event type and server timestamp;
- repository and base revision;
- provenance (`server_observed`, `server_derived`, `human_attested`, or another precise vocabulary);
- referenced files, versions, hunks, tests, memories, or decisions;
- a redacted payload and digest;
- an authoritative source reference.

Candidate event families include:

- run/task started and ended;
- clarification asked and answered;
- directory/list/search operation;
- file read;
- patch proposed/applied;
- test started/completed;
- scope request allowed/denied;
- feedback anchored to an event or exact hunk;
- memory proposed/approved/rejected;
- context packet built/injected;
- completion attempted/denied;
- promotion requested/approved/completed;
- unattributed external change.

Do not make every event a graph node. The append-only log is chronological history; the semantic graph should aggregate repeated reads and project only what helps a human inspect, review, or hand off the work.

Model immutable file identity separately from file versions, changesets, and hunks. Otherwise repeated edits will erase lineage. Decide which relationships are truly authoritative, which are advisory, and which belong only in the replay timeline.

Do not use a filesystem watcher as the primary provenance source. It can detect a changed path but cannot reliably attribute a read, edit, purpose, or agent identity. Instrument the scoped tools and ADK lifecycle/callback events. A watcher may supplement them only with clearly labeled `external_change` events.

Persist an event before presenting it as accepted evidence. Replaying the same canonical ordered events must reproduce the same graph hash and terminal state after restart.

### 7. Make the graph useful to the next agent

Design two symmetrical operations and determine the thinnest credible implementation.

#### Backward: `why`

Examples:

```text
graphene why app/auth/limiter.py
graphene inspect <hunk-or-event-id>
graphene replay <run-id>
```

The answer should traverse exact evidence such as task, agent run, read/edit event, changeset, hunk, test, feedback, memory, and human decision. It should distinguish what was observed from what was inferred and disclose truncation or missing evidence.

#### Forward: scoped handoff

Example:

```text
graphene handoff <run-id> --to auth-maintainer@1
```

The handoff should compute something like:

```text
task targets
+ approved applicable memory
+ relevant validated changes and exact evidence anchors
+ bounded related-file references
∩ server-owned profile permissions
= persisted context packet with inclusion/exclusion reasons
```

Do not dump an entire trace or graph into the prompt. Consider a small initial packet plus scoped tools such as `lineage_search`, `lineage_neighbors`, `open_evidence`, or `why`, allowing the fresh agent to retrieve more within policy. The new agent must still read source files itself.

Define a truthful review surface. It may flag evidence gaps such as:

- an edited file with no validating test edge;
- applicable approved memory that was not injected;
- a denied out-of-scope access attempt;
- a deterministically related file that remains uninspected.

Call this evidence coverage, not correctness or complete impact analysis.

### 8. Preserve the best current implementation instead of restarting blindly

Explicitly evaluate whether to reuse, adapt, park, or delete each current component.

Likely reuse candidates:

- canonical IDs, hashes, graph caps, and honest truncation;
- exact Git patch/hunk parsing;
- immutable run, candidate, test, decision, and promotion bindings;
- scoped tool boundary and path/symlink checks;
- compare-and-set revisions and idempotency;
- profile/path/tool scope intersection;
- approved memory and context-packet lifecycle;
- deterministic restart and adversarial tests.

Likely areas to redesign:

- batch-created proof items;
- absence of tool/read/search events;
- fixed post-hoc `GraphBuilder` inputs;
- prompt construction that does not expose selected evidence;
- browser-first workflow;
- whole-snapshot JSON and single-document Firestore storage if events grow;
- frozen two-task fixture if it is too visibly scripted for the final demonstration.

Do not delete the web UI merely to perform a dramatic rewrite. Decide whether to freeze it, demote it, or reuse its exact-diff inspector and proof semantics. The terminal pivot is an interaction and runtime change, not a license to discard working integrity controls.

### 9. Scope the next proof ruthlessly

The next MVP should probably prove only:

- one real Gemini model through one Google agent framework;
- one realistic but bounded Python repository and coding task;
- one live terminal session whose graph changes during actual tool use;
- one human correction anchored to exact evidence;
- one immutable approved memory;
- one completely fresh agent/session receiving a scoped graph briefing;
- one visible unrelated-profile or out-of-path denial;
- one required test and fail-closed completion attempt;
- one human promotion;
- one restart and deterministic replay.

Challenge this scope if needed, but do not expand it into arbitrary repositories, languages, vendors, or enterprise fleets before the central proof is green.

Explicit non-goals should likely include:

- whole-codebase causal understanding;
- private chain-of-thought capture;
- Neo4j or another graph database;
- embeddings, GraphRAG, or learned graph ranking;
- multi-vendor or MCP capture;
- a five-agent product runtime swarm;
- multi-user accounts, SSO, RBAC administration, or tenancy;
- full static symbol/call/data lineage;
- production-source cloud synchronization;
- a general shell tool;
- statistical claims that the graph improves efficiency without measured evidence.

The five subagents used to build or review this project are an engineering workflow, not five agents that the product must expose.

### 10. Treat real required technology as a P0 proof

Verify current hackathon requirements from official sources. The last known rules required:

- Gemini 3.5 or newer;
- at least one Google agent framework such as Google ADK;
- at least one Google Cloud infrastructure service;
- visible proof of Google Cloud in the submission/demo;
- one selected track; and
- a public demo video no longer than four minutes.

Real Gemini/ADK execution is now a product-risk experiment, not a final integration detail. Before spending serious time on terminal polish, prove that a real model can emit persisted read/write/test events through the instrumented tool boundary.

Never silently substitute a model, simulate cloud evidence, or describe deterministic-local output as a live Gemini run. If credentials or account setup block verification, identify the exact external action Alex must take and continue only with clearly labeled local seams.

### 11. Security and privacy questions the design must answer

- Which evidence remains local, and which metadata may be mirrored to Firestore?
- Can the demo persist hashes, paths, approved memory, and receipts without uploading unrestricted source?
- How are secrets, ignored files, binary files, oversized patches, traversal, and symlink escape handled?
- How does the event log avoid raw prompts, credentials, and chain-of-thought?
- Which actor is allowed to assert identity, scope, test success, memory approval, and promotion?
- How are inclusion and exclusion reasons stored for every handoff item?
- What survives a crash midway through a run?
- Can a forged, reordered, duplicated, or stale event affect the graph, packet, or promotion?
- How does the terminal show incomplete or unattributed evidence honestly?

For the thin MVP, source and exact diffs should remain local by default unless there is a specific, sanitized fixture exception. Policy and promotion truth must remain server-owned and fail closed.

### 12. Define the unforgettable four-minute demonstration

Design one continuous demo in which the value is obvious before the architecture is explained. A strong hypothesis is:

1. A real Gemini/ADK coding agent starts in one terminal; file nodes appear only as the agent actually reads, searches, edits, and tests.
2. The file footprint stays stable, edit heat and exact `+/-` counts update, and the event rail shows authoritative actions.
3. Agent A changes authentication behavior but misses a required regression test.
4. Alex selects the live hunk/event, gives a correction, answers one useful scope clarification, and approves the resulting memory.
5. The original session is destroyed.
6. Graphene builds and displays the exact bounded briefing for fresh `auth-maintainer@1`; `billing-observer@1` receives an explicit empty/denied packet.
7. Fresh Agent B uses the authorized lineage, reads the relevant evidence, performs a compliant change, and adds the missing test.
8. Completion is visibly denied until the fixed test and human decision are present.
9. Alex promotes the exact candidate.
10. `why <file>` shows the backward evidence path, and `replay <run>` briefly reconstructs the same terminal state after restart.

The unforgettable moment should be: **Agent A is gone, but the exact approved lesson survives, guides Agent B, and does not leak to Billing.**

If this loop is too complex for a reliable four-minute live demo, simplify it decisively. Do not hide weak causality beneath animation.

### 13. Use independent judgment, not design-by-consensus

If the environment supports subagents, use five bounded review roles in waves when concurrency is limited:

1. **Repository truth auditor:** code paths, tests, evidence, and reusable components.
2. **Hackathon/product judge:** track fit, judge comprehension, novelty, and a brief current comparison with adjacent agent tracing/memory products using primary sources.
3. **Runtime lineage architect:** ADK instrumentation, event contract, reducer, persistence, replay, and crash behavior.
4. **Terminal and review designer:** CLI/TUI interaction, file/edit encoding, `why`, handoff, accessibility, and demo clarity.
5. **Security and falsification reviewer:** scope leaks, misleading claims, cloud privacy, adversarial tests, and fastest risk experiments.

Subagents should initially inspect and report; they must not independently rewrite shared contracts or implement competing architectures. The root agent owns the final verdict. Do not average five opinions into a vague compromise.

Keep the same five subagent identities alive and reuse them through repeated autonomous cycles. If concurrency is limited, schedule them in waves without collapsing or replacing the roles. The root should continue this loop without waiting for Alex between ordinary checkpoints:

```text
LOOP until the acceptance standard passes or a genuine stop condition occurs:
  1. INSPECT the latest repository state, agent reports, evidence, and tests.
  2. ASSIGN each idle subagent one bounded objective with owned paths and proof required.
  3. WAIT using the platform's agent-wait mechanism while doing independent root work.
  4. DRAIN every available report and inspect the actual files or evidence behind it.
  5. ACCEPT, REJECT, or send a precise follow-up to the same responsible subagent.
  6. INTEGRATE accepted conclusions, contracts, spikes, or documentation centrally.
  7. TEST the earliest unresolved product or technical assumption.
  8. CHECKPOINT the current verdict, evidence, failures, and next actions.
  9. REPEAT immediately from the new accepted state.
```

Do not end the run merely because the first reports arrive, a single experiment passes, one subagent becomes idle, or an intermediate plan looks plausible. Continue falsifying assumptions and improving the decision brief until every acceptance condition is evidence-backed.

Do not run another broad market-research phase. A short comparison is useful only to answer: what is already commodity observability, and what makes this product genuinely different?

### 14. Required verdict and artifact

Choose exactly one verdict:

- `GO`: the terminal-lineage hypothesis is strong enough with only scoped refinement;
- `PIVOT`: preserve the best core but materially change the thesis or proof; or
- `KILL`: this direction is not distinct or buildable enough, and one stronger replacement should be chosen.

Do not return multiple equally weighted product concepts. If you reject the current hypothesis, supply one replacement direction—not a brainstorm list—and explain why it uses the verified foundation better.

Create a new repository document named:

```text
CLI_LINEAGE_JUDGE_DECISION.md
```

Do not overwrite the older plans. The new document must contain:

1. Executive verdict and blunt scorecard: pain, novelty, technical leverage, buildability, track fit, demo clarity, credibility, and winning potential.
2. Factual audit of what the current implementation really does.
3. The weakest current claims and the strongest reusable assets.
4. One locked one-sentence pitch and a 20-second judge explanation.
5. Selected track and why.
6. Exact user problem and why the terminal is or is not the right surface.
7. Memorable end-to-end loop.
8. Thin MVP and explicit non-goals.
9. Runtime event contract, evidence/provenance rules, and deterministic graph projection.
10. Terminal interaction model and honest size/edit visual semantics.
11. Backward `why`, forward handoff, and how the graph changes a fresh agent's actual invocation.
12. What to reuse, redesign, freeze, or remove from the current codebase.
13. Persistence, replay, crash recovery, cloud boundary, privacy, and security model.
14. Exact three-to-four-minute demo script at the product-action level.
15. Staged implementation plan with ordering, ownership suggestions, acceptance gates, and ruthless kill rules.
16. The three riskiest assumptions and the fastest falsification experiment for each.
17. Honest thin-MVP limitations versus the later enterprise vision.
18. A final copy-paste implementation prompt for the next root Ultra agent.

You may create a small disposable spike only when it is the fastest way to falsify a core assumption—for example, proving that one real ADK `read_file` call can persist an event and update a terminal projection before the run ends. Label any spike clearly, keep it isolated, and do not let it become an unreviewed rewrite.

### 15. Acceptance standard for your judge pass

Your work is complete only when:

- the verdict is singular and evidence-backed;
- the proposed product can be understood in under 20 seconds;
- the graph is more than decoration because it changes the fresh agent's authorized context;
- observed, derived, human, and policy truth are not conflated;
- the plan shows how live events are captured from real agent tools;
- real Gemini/ADK and Google Cloud proof are treated as mandatory, not implied;
- the demo has one clear before/after moment and one negative-scope proof;
- the thin MVP can be built without a graph database, whole-repo intelligence, or a runtime swarm;
- every major claim has a test, artifact, or planned falsification experiment; and
- the document gives the next implementation agent enough direction to act without removing its ability to improve the design.

### 16. Long-running work and checkpoints

Run autonomously and continuously for as long as the active environment permits. Alex intends to keep the computer awake and is explicitly authorizing a long-running root/subagent loop for this judge pass. Do not pause merely to ask whether you should continue, request approval for an ordinary in-scope next step, or provide a progress-only handoff.

`caffeinate` may be used outside the agent to keep the Mac awake, but the root should not make progress depend on repeatedly checking it. Continue the inspect → assign → wait → review → integrate → test → checkpoint loop while the session is available, and make every cycle resumable in case the IDE or execution environment imposes a hard limit.

Stop only when one of these conditions is true:

1. Every acceptance condition for the judge pass is satisfied and `CLI_LINEAGE_JUDGE_DECISION.md` contains the final verdict and implementation handoff.
2. A concrete external blocker requires information, credentials, spending authority, or another decision only Alex can provide, and all other independent work has been exhausted.
3. The user explicitly interrupts or changes the assignment.
4. The platform ends the session or enforces a hard execution limit.
5. Continuing would cross a permission, safety, or repository-integrity boundary.

An idle subagent, a failed experiment, an unavailable optional dependency, or a partially green test suite is not a stop condition. Reassign, simplify, falsify, or continue with other unblocked work.

Make the work resumable:

- record the audited base SHA;
- checkpoint the current verdict, open risks, and evidence paths in `CLI_LINEAGE_JUDGE_DECISION.md`;
- use platform-native agent wait primitives rather than shell sleeps;
- revisit the same subagents with precise follow-ups instead of spawning replacements;
- preserve test commands and results;
- leave a clear `NEXT ACTION` at every checkpoint so the autonomous loop can resume after interruption; and
- do not commit, push, deploy, or spend cloud credits without authorization in the active session.

Be decisive. The goal is not to make Graphene larger. The goal is to find the smallest version whose demo proves that observable agent work can become trustworthy, human-correctable lineage and then become safer working memory for the next agent.
