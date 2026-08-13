# Graphene CLI Lineage — Judge Decision

**Decision:** `PIVOT`  
**Current HEAD:** `d36ff4b6a37f160e1122307f3e48cea953fcd223` on `main` (`main image`)  
**Audited implementation commit:** `ce9dfbe0d0e2910b0c1f7216bf944fbc5987d206`  
**Current public baseline:** `origin/main` at `d36ff4b6a37f160e1122307f3e48cea953fcd223`; relative to the audited implementation commit it changes only `README.md` and adds `Graphene_main_img.png`  
**Checkpoint:** 2026-08-12, America/Los_Angeles  
**Current evidence state:** clean committed tree passes locally; real Gemini/ADK, Firestore, and Cloud Run remain unproved  
**NEXT IMPLEMENTATION ACTION:** complete Stage 0's fixture/auth/privacy repairs and make the actual checkout pass twice without cleaning between runs.  
**EXTERNAL ACTION FOR ALEX:** authorize a Google project, ADC, and any credit use needed for Stage 1; until then, real Gemini/ADK and Cloud proof remain explicitly blocked.

This is a product and proof pivot, not a restart. Preserve Graphene's exact patch/test/approval/promotion bindings. Replace the current browser-first, post-hoc graph thesis with one narrower claim: observed coding-agent activity can be durably recorded, corrected by a human at exact evidence, and compiled into the smallest authorized briefing for a genuinely fresh agent.

---

## 1. Executive verdict and blunt scorecard

### Verdict: `PIVOT`

The problem is real and the repository contains unusually strong integrity primitives for a hackathon project. The current product proof does not yet support its most interesting story. Its graph is assembled after execution, most runtime facts are synthesized at one timestamp, ADK events are discarded, the selected graph slice does not enter the next model invocation, and the browser remains the main surface. That is a polished receipt viewer, not yet a live lineage system or a memory handoff.

The winning version is narrower: a terminal flight recorder whose evidence-backed subset becomes a persisted, least-privilege `ContextBrief` for a fresh agent, with a Billing handoff authorizing no work context and no model call as the negative proof, and human promotion as the final latch.

Scores are out of 10. “Pivot target” is not credit already earned; except for buildability (which measures execution risk), it is the ceiling if every P0 acceptance gate in Section 15 passes.

| Dimension | Current thesis | Pivot target | Blunt judgment |
|---|---:|---:|---|
| Pain | 8 | 8 | Agent context disappears, traces are hard to review, and broad memory creates risk. This is recognizable pain. |
| Novelty | 4 | 8 | A post-hoc agent graph is commodity observability. An evidence-to-authorized-briefing compiler is differentiated. |
| Technical leverage | 8 | 9 | Exact Git artifacts, immutable contracts, scoped tools, CAS, and promotion bindings are excellent foundations. |
| Buildability by deadline | 8 | 6 | The existing deterministic slice is buildable; real live ADK events, fresh-session proof, and Cloud hardening add meaningful risk. |
| Collaborative Partner fit | 6 | 9 | Current memory is scripted. A proven correction-to-fresh-agent loop directly demonstrates persistent, adaptive collaboration. |
| Demo clarity | 5 | 9 | The present six-step browser flow needs explanation. “Auth receives one approved lesson; Billing receives no work context or model call” is immediate. |
| Credibility | 3 | 8 | The code is honest about deterministic execution, but the headline thesis lacks real Gemini/Cloud/runtime proof. Credibility rises only after recorded gates. |
| Winning potential | 5 | 8 | Strong if the live before/after is real and legible; weak if any deterministic fallback is presented as Gemini behavior. |

Why not `GO`: the selected context currently does not change the fresh model's actual invocation, so the hypothesis needs a material architectural and product change.  
Why not `KILL`: the integrity core is real, tested, and unusually well matched to a more defensible product loop.

The decision reverses automatically to `KILL` for this submission if either of these is true after the time-boxed Stage 1 and Stage 3 experiments:

- real ADK tool activity cannot become persisted, ordered terminal evidence before the run ends; or
- a destroyed Agent A session cannot produce a fresh Agent B that demonstrably receives the approved brief while Billing receives zero authorized work context and is never invoked.

---

## 2. Factual audit of the current implementation

### Repository truth

- Current HEAD and `origin/main` are `d36ff4b6a37f160e1122307f3e48cea953fcd223` on `main`, tree `597a06941cd73a82df80e44611b663dd1b9d205e`. `d36ff4b` adds the tracked `Graphene_main_img.png`; parent `6a57016` merges the README-only `b2c8f6c` commit. The worktree contains only the two untracked judge documents at this checkpoint.
- The implementation was audited at ancestor `ce9dfbe0d0e2910b0c1f7216bf944fbc5987d206`. The last-known public baseline `c3d4bbd50ba6f0c0b2e9a729b78ba9ac50cece03` and `ce9dfbe` shared implementation tree `62a30dc989590f28d1b8f082cf980c256515b834`; `ce9dfbe` itself adds only the post-Phase-0 plan, and the latest implementation commit remains `eadc2e7`.
- `git diff --name-status ce9dfbe..d36ff4b` shows only `M README.md` and `A Graphene_main_img.png`. All implementation/test claims bind `ce9dfbe`; current repository/branding status binds `d36ff4b`.
- During this judge pass the repository directory was relocated on disk. The Git identity remained intact. Existing user-side `README.md` and image changes were not modified by this pass.
- Submission name is **Graphene**, matching `Graphene_main_img.png`.

### What is implemented and verified

| Capability | What the code really does | Evidence |
|---|---|---|
| Lifecycle and contracts | FastAPI owns run, feedback, memory, decision, and promotion transitions. Packet build/injection occurs inside execution; there is no handoff endpoint or handoff state today. Pydantic records are frozen and reject extra fields. | `backend/graphene/app.py`, `backend/graphene/models.py` |
| Scoped execution | Canonical relative paths, allowlists, traversal and pre-existing symlink rejection, UTF-8 reads, capped writes, and one fixed test command. No arbitrary shell. | `backend/graphene/execution/adapter.py` |
| Exact candidate evidence | A private temporary Git baseline produces canonical patch, tree, file, hunk, and test-receipt hashes. | `backend/graphene/execution/adapter.py`, `backend/graphene/graph/builder.py` |
| Context policy | Repo/profile/path/tool/memory constraints are intersected server-side. Empty intersection denies the packet. | `backend/graphene/context/__init__.py` |
| Human memory | Feedback can propose an immutable memory revision; the demo operator approves or rejects it. | `backend/graphene/app.py`, `backend/graphene/models.py` |
| Promotion latch | Promotion reconstructs the candidate, reruns the fixed test, and binds base, patch, tree, packet, graph, memory, decision, revision, and receipt. | `backend/graphene/app.py` |
| Bounded graph | A deterministic post-hoc projection emits capped nodes/edges, provenance labels, omission counts, and exact hunk detail. | `backend/graphene/graph/builder.py` |
| Browser receipt viewer | SVG graph, keyboard-operable nodes, provenance badges/labels, bounded-map disclosure, accessible proof list, and exact-diff drawer with summary/detail digest cross-check plus SHA-shape validation. It does not recompute hunk hashes client-side; its filters are run/path/node-kind/origin, not provenance filters. | `frontend/src/app.mjs`, `frontend/src/graph.mjs` |
| Persistence | In-memory, atomic JSON snapshot, and Firestore snapshot adapters implement CAS/idempotency at the record layer. | `backend/graphene/store.py` |

### What is deterministic, mocked, synthesized, or absent

- The default executor performs frozen string replacements from `contracts/golden_path.json`. It is not a model.
- The ADK seam is present and mocked in tests, but no accepted artifact proves a real Gemini call. The loop currently retains only `event.model_version`; it discards tool/model/lifecycle events.
- Proof items are synthesized after execution in a batch and share one timestamp. They are not an append-only record of observed runtime calls.
- The graph appears only after the candidate exists. It contains changed files, not the complete read/search/test working set.
- The context packet records selected graph IDs, but `_prompt` sends only task text and approved memory. In a direct audit, 0 of 3 selected node IDs, 0 of 1 related files, and no test profile appeared in the model prompt.
- The server synthesizes `human_promotion_required`; it does not record an explicit agent completion attempt.
- The Billing denial exists as a context-builder unit test. It is not yet a visible runtime handoff in the product.
- Firestore is tested with an in-process fake and stores the entire snapshot in one document. No accepted artifact proves real Firestore or its size/restart behavior.
- Cloud Run has not been deployed or observed. `gcloud`, project variables, Vertex variables, and ADC were absent during the audit.
- Promotion creates a Git commit only in a temporary repository. The commit object disappears; the receipt and SHA persist.
- The mutation token represents one demo operator, not authenticated human identity or RBAC.

### Reproducible test state

The committed tree is green when materialized cleanly. The live checkout was not green during the audit because previous Python execution left ignored bytecode inside the frozen fixture, and fixture validation inventories every file rather than contract-tracked files.

| Check | Command | Result |
|---|---|---|
| Clean Python suite | Exact command below against `/tmp/graphene-audit.Py3QjF` | 55 passed, one upstream warning, 15.67 seconds on final rerun |
| Clean frontend tests | Exact command below against the archive | 8 passed in 65 ms on final rerun |
| Frontend syntax | Exact three `node --check` commands below | passed |
| Clean deterministic demo | Exact command below, writing `audit-local-golden-rerun.json` outside the repository | completed; 20 nodes, 19 edges; restart-stable detail/receipt; deterministic-local and Gemini/Firestore/Cloud explicitly unverified |
| Fresh clean soak | Exact command below, writing `audit-local-soak-rerun.json` outside the repository | 10/10 passed; every run had 20 nodes and 19 edges |
| Live checkout Python suite | `uv run pytest -q -p no:cacheprovider` | 34 passed, 4 failed, 17 errors |
| Live checkout demo | `uv run python demo/graph_mvp.py ...` | HTTP 409: fixture inventory mismatch |

The exact historical rerun commands are below. The archive had been created from `ce9dfbe` with the setup block shown first; replace the random path if recreating it after `/tmp` cleanup.

```bash
GRAPHENE_AUDIT_DIR="$(mktemp -d /tmp/graphene-audit.XXXXXX)"
git archive ce9dfbe0d0e2910b0c1f7216bf944fbc5987d206 \
  | tar -x -C "$GRAPHENE_AUDIT_DIR"

# The judge-pass instance of GRAPHENE_AUDIT_DIR was:
GRAPHENE_AUDIT_DIR=/tmp/graphene-audit.Py3QjF

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$GRAPHENE_AUDIT_DIR/backend" \
.venv/bin/python -m pytest -q -p no:cacheprovider \
"$GRAPHENE_AUDIT_DIR/tests"

node --test "$GRAPHENE_AUDIT_DIR"/frontend/test/*.test.mjs
node --check "$GRAPHENE_AUDIT_DIR/frontend/src/app.mjs"
node --check "$GRAPHENE_AUDIT_DIR/frontend/src/graph.mjs"
node --check "$GRAPHENE_AUDIT_DIR/frontend/src/workflow.mjs"

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$GRAPHENE_AUDIT_DIR/backend" \
.venv/bin/python "$GRAPHENE_AUDIT_DIR/demo/graph_mvp.py" \
--evidence "$GRAPHENE_AUDIT_DIR/evidence/audit-local-golden-rerun.json"

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$GRAPHENE_AUDIT_DIR/backend" \
.venv/bin/python "$GRAPHENE_AUDIT_DIR/demo/graph_mvp.py" \
--soak 10 \
--evidence "$GRAPHENE_AUDIT_DIR/evidence/audit-local-soak-rerun.json"
```

Root cause: ignored `demo/fixture/**/__pycache__/*.pyc` files are included by `_validate_fixture` at `backend/graphene/execution/adapter.py`. A rehearsal can poison the next rehearsal. The fix is to copy only paths named by the frozen contract, fail missing/mutated/unsafe named paths, ignore ambient untracked entries, and assert the temporary materialized inventory equals the contract set.

### Disposable judge-pass falsification observations

These isolated Python/TestClient spikes ran against a clean archived tree or temporary directories and made no shared repository changes. Their console transcripts were not retained as submission artifacts, so they justify the decision but do **not** satisfy implementation acceptance. Stages 0–4 must turn them into named regression tests and redacted evidence files.

| Spike | Observed result |
|---|---|
| Submit feedback with a nonexistent `evidence_event_id` | HTTP 200; a memory was proposed because the field is ignored. |
| Restore JSON after changing a proof payload's `execution_mode` | Restore accepted the forged value. |
| Restore JSON after deleting every run | Restore accepted zero runs; unanchored tail deletion is not detected. |
| Request run/graph/proof/node/context reads without a token | Evidence GETs returned HTTP 200, including patch/diff-bearing records. |
| Emit a passing test warning containing `SECRET_CANARY_FROM_SOURCE` | The canary remained in persisted `TestReceipt.output`. |
| Swap an allowed write target to a symlink after path resolution | The outside sentinel was overwritten, demonstrating a check/use race against a hostile local writer. |
| Build a packet with three selected node IDs and one related file, then render `_prompt` | 0/3 node IDs, 0/1 related paths, and no test profile appeared; approved memory did appear. |
| Inspect baseline proof timestamps | Every synthesized proof item used the same timestamp. |

Durable evidence already in the repository:

- `evidence/local_vertical_slice.json`
- `evidence/local_soak.json`
- `IMPLEMENTATION_STATUS.md`
- `contracts/golden_path.json`
- `contracts/graph_mvp.json`

Environment audited: Python 3.13.9, `uv` 0.11.29, Google ADK 2.5.0, Firestore client 2.28.0, Node 23.11.0, Docker 29.6.1, Git 2.39.3. Node differs from the documented Node 22 target. No real Google credentials were available.

### Submission rules checked on 2026-08-12

The current official pages require Gemini 3.5 or newer, a Google agent framework such as ADK, at least one Google Cloud infrastructure service, exactly one category, a public English or subtitled video no longer than four minutes, visible proof of the Cloud backend, source/spin-up instructions, and an architecture diagram. The submission deadline shown is August 31, 2026 at 5:00 PM PT. These are build gates, not narrative suggestions.

Primary references: [hackathon overview](https://allthingsagentichackathon.devpost.com/), [official rules](https://allthingsagentichackathon.devpost.com/rules), [FAQ](https://allthingsagentichackathon.devpost.com/details/faqs), [resources](https://allthingsagentichackathon.devpost.com/resources), [Gemini 3.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash), and [ADK callbacks](https://adk.dev/callbacks/).

---

## 3. Weakest claims and strongest reusable assets

### Claims that must be removed until proved

| Weak claim | Audit result | Required proof before reuse |
|---|---|---|
| “Live runtime lineage” | False today: graph and proof are post-hoc. | A real wrapper-observed read/write/test appends before terminal display and before run completion. |
| “Append-only/tamper-proof evidence” | False today: snapshot proof can be rewritten, reordered, or deleted; a modified snapshot restored successfully. | Server-issued sequence, append API, digest/reference validation, crash tests, and modest honest-host wording. Never claim malicious-admin resistance. |
| “Gemini made this change” | Unproved: accepted evidence is deterministic-local with `model_id: null`, while one contract labels the actor Gemini. | A real invocation receipt plus wrapper events linked to ADK invocation/tool-call IDs. |
| “The graph guides Agent B” | False today: selected evidence does not enter `_prompt`. | Persisted `ContextBrief`, injection receipt before invocation, destroyed prior session, and model-visible evidence refs/summaries. |
| “Billing is denied” as product behavior | Only a direct context-builder test. | CLI handoff emits empty included paths/tools/memory/evidence and proves no session/model call was created. |
| “Metadata-only cloud boundary” | False today: Firestore mirrors raw patch, test output, feedback, and memory. | Field allowlist, canary tests, authenticated reads, and explicit sanitized-fixture exception. |
| “Evidence-anchored feedback” | Partial: hunk binding works, but a forged nonexistent `evidence_event_id` returned HTTP 200. | Referential validation tying event, run, file version, changeset, hunk, repo, and profile. |
| “Secret-safe output” | False: a warning canary survived sanitization into `TestReceipt.output`. | Raw output may exist transiently during execution but must not persist in Firestore/logs/events; durable cloud data is status/digest/counters only. |
| “Arbitrary repo isolation” | Unproved; a hostile symlink race overwrote an outside file in a controlled spike. | Keep out of MVP claim; use tracked-only private fixture and no-follow final opens. |
| “Completion was denied” | Policy was synthesized without an observed completion request. | Capture `completion.attempted` from the agent/service, then append `completion.denied` from policy. |
| “Durable promoted commit” | Only the SHA survives the temporary repo. | Either persist/export the bundle or describe it honestly as a promotion receipt, not a durable Git object. |

Commodity observability already includes agent graphs and tool traces in [Langfuse](https://langfuse.com/docs/observability/features/agent-graphs), [LangSmith](https://docs.langchain.com/langsmith/view-traces), [MLflow's ADK/OpenTelemetry integration](https://mlflow.org/docs/latest/genai/tracing/integrations/listing/google-adk), and [Google Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/traces). Long-term agent memory is also established territory in [LangChain](https://docs.langchain.com/oss/python/langchain/long-term-memory) and [Zep/Graphiti](https://help.getzep.com/graphiti/getting-started/overview). Graphene should not compete on “we draw an agent graph” or “we remember things.” Its defensible delta is the chain:

> exact observed hunk → human-attested correction → approved immutable lesson → deterministic profile/path/evidence inclusion and exclusion → persisted brief used by a genuinely fresh invocation → promotion receipt bound to the resulting candidate

### Assets to preserve

- Canonical hashing and serialization in `backend/graphene/hashing.py`.
- Frozen, extra-forbidden records and lifecycle validators in `backend/graphene/models.py`.
- Scoped read/write/fixed-test wrappers in `backend/graphene/execution/adapter.py`, after the fixture and final-open fixes.
- Private temporary Git baseline, exact patch/tree/file/hunk hashes, and strict unified-diff parser.
- Persist-before-invocation packet receipt pattern.
- Server-owned context intersection and fail-closed empty packet.
- CAS and idempotency semantics.
- Promotion reconstruction, authoritative retest, substitution resistance, and human decision binding.
- Graph caps, provenance labels, honest omissions, exact-diff detail, and accessible linear proof.
- Existing adversarial tests for substitution, traversal, symlinks, stale revisions, and restart.

These components should be adapted around the event spine. Reimplementing them would add risk without adding product value.

---

## 4. Locked pitch and 20-second explanation

### One-sentence pitch

> **Graphene turns observed coding-agent work into the smallest approved briefing a fresh agent is authorized to use—and refuses to promote work without matching evidence.**

Do not vary this sentence across the README, video, submission copy, or terminal opening frame unless a comprehension test disproves it.

### Twenty-second judge explanation

> Agent traces usually die as debugging logs. Graphene records Gemini's scoped read, edit, and test results; I pin one correction to its exact hunk; then I destroy that session. A fresh Auth agent gets only the approved lesson and evidence, while Billing gets no work context and no model call. Untested or unapproved work cannot promote.

The one before/after is an Auth testing convention absent from Agent A's briefing becoming explicit, approved behavior in fresh Agent B's work. The demo does not need to call Agent A “wrong”; it proves that a human can add organization-specific knowledge after observing exact work. The negative proof is Billing receiving zero authorized memory, evidence, source paths, or tools and no model invocation.

---

## 5. Selected track

**Submit only to: Collaborative Partner.**

The track rewards stateful multi-turn interaction, real-time context retrieval, persistent memory, and adaptation from history. The pivot demonstrates all four in one bounded loop:

1. Agent A creates observed work and a human reviews it.
2. The correction becomes a separately approved memory revision.
3. A policy compiler retrieves only evidence and memory applicable to the Auth profile and current task.
4. A fresh Agent B changes behavior because of that history.
5. An unrelated Billing profile receives no authorized work context and is not invoked.

Do not select Fortified Enterprise Fleet. Its institutional-network, cross-department, weeks-long, production-data, compliance, and enterprise-state expectations would invite claims this repository cannot support. Do not dilute the entry across categories; the current FAQ says to pick one.

The top-level rubric currently weights Innovation & Operational Utility at 40%, Architecture Discipline at 30%, and Demo/Production at 30%. Some track-specific judging examples on the rules page appear to retain older category names; treat that as organizer-page ambiguity, not permission to ignore the current track definitions.

---

## 6. Exact user problem and why the terminal is the right surface

### User and job

The thin-MVP user is a senior engineer supervising one coding agent on one sensitive repository fixture. They need to answer, quickly and defensibly:

- What did the agent actually read, change, test, request, or get denied?
- Which exact evidence supports a human correction?
- What is safe and useful to carry into a fresh agent?
- What was deliberately excluded, and why?
- Does the final candidate still match the evidence, tests, memory, and human decision being promoted?

Their problem is not “draw my repository.” It is “turn this run's inspectable evidence into a safe next-agent briefing without smuggling the whole conversation or repository across the boundary.”

### Why terminal-first

The coding activity already occurs in a terminal-shaped workflow; event arrival is chronological; exact IDs and commands matter; and the highest-value action is an immediate inspect/feedback/handoff command. A line-oriented CLI makes live timing, persistence, replay, and denial visible without a second interaction surface or a heavy TUI framework.

Terminal-first is not a claim that spatial graphs are useless. It is a scope choice:

- the terminal is the primary live surface and control plane;
- the reducer still produces a deterministic graph model;
- the existing browser may remain a secondary, read-only receipt inspector for exact diffs and accessibility;
- no browser live mode, force-directed canvas, mouse workflow, or duplicate mutation controls belong in the submission proof.

Use the Python standard library: `argparse`, plain text, optional ANSI, `shutil.get_terminal_size()`, `isatty()`, `NO_COLOR`, and canonical JSON. Do not add Click, Rich, Textual, curses, a pager, or a filesystem watcher.

---

## 7. Memorable end-to-end loop

The product loop is deliberately one sentence long:

> **Observe Agent A → anchor one correction → approve one lesson → deny Billing → brief fresh Agent B → verify and promote.**

Exact loop:

1. The server creates a run bound to repo, base SHA, task, profile, policy revision, and test profile.
2. Real Gemini 3.5 Flash runs through Google ADK. Graphene's scoped wrappers append read/search/write/test and policy events before the terminal renders them.
3. Agent A completes the requested Auth code change without having been given Graphene's organization-specific security-test convention, then calls the explicit `request_completion` protocol. A server policy event denies completion pending human review.
4. The reviewer inspects the exact changed hunk and attaches the missing convention to both the hunk and its observed write event. This is new human guidance, not a claim about the model's hidden reasoning or a fixture-tuned failure.
5. The system asks one durable clarification: apply this lesson to this file only or all `app/auth/**` paths. The reviewer chooses all Auth paths and approves memory revision 1.
6. A Billing handoff is compiled first. Its repo/path/memory/evidence intersection is empty, so Graphene persists the safe denial summary and creates no ADK session or model call.
7. An Auth handoff preview shows the authorized operator the server-side decision: every candidate item is included or excluded with a reason. Only included items enter the model-visible brief, which is persisted before invocation.
8. Agent A's ADK session and in-memory conversation are destroyed. A new session ID and invocation ID are created for Agent B.
9. Agent B receives only the small brief, uses scoped evidence/source tools to reread current files, applies the lesson, adds or updates the regression test, and runs the fixed test profile.
10. Completion remains denied until a human promotes the exact candidate. Promotion reconstructs and retests it, then emits a bound receipt.
11. `graphene why ...` walks only evidence-backed edges. Process restart followed by `graphene replay ...` produces the same projection hash or an explicit interrupted/corrupt state.

The baseline must be honest. Agent A may edit both implementation and regression-test paths. Narration says only what the trace proves: the precise organization-specific convention was absent from Agent A's input and becomes approved context for Agent B. Never manufacture a miss by forbidding the test path, reroll for a preferred failure, hide an inconvenient test, or silently substitute deterministic output. If Agent A independently follows the same convention, show that honestly; the persistent scoped handoff—not a model mistake—is the product proof.

---

## 8. Thin MVP and explicit non-goals

### In scope

- One public, sanitized, frozen Auth fixture.
- One real Gemini 3.5 Flash model through Google ADK.
- Three profiles: Agent A uses `platform-maintainer@1`; Agent B uses `auth-maintainer@1`; the negative handoff uses `billing-observer@1`.
- One Agent A task and one Agent B follow-up task.
- A tracked-text read scope, a two-path write scope, and one fixed test profile.
- Scoped `search_repo`, `read_file`, `open_evidence`, `write_file`, `run_fixed_test`, and `request_completion` tools. No general shell. `search_repo` supplies bounded discovery, so a separate list tool is unnecessary.
- An integrity-checked per-run event log and one deterministic reducer.
- Live line-oriented terminal view, `why`, `inspect`, `feedback`, `answer`, `memory approve`, `handoff`, `promote`, and `replay`.
- Exact candidate patch/hunk/test/decision/promotion receipts.
- One human-approved immutable memory revision.
- One Billing handoff with zero authorized memory/evidence/source paths/tools and no model invocation.
- Exact source/evidence is not persisted in Firestore by default; the authenticated execution process sends bounded task content to Google/Gemini, which handles it under the selected service configuration and terms. An explicit sanitized-public-fixture persistence exception exists only for the recording.
- One Cloud Run service and Firestore, both visibly used in the recorded proof.
- Token authentication on every non-health endpoint for the single demo operator.
- Restart and corruption tests, canary privacy tests, and two consecutive clean rehearsals.

### Non-goals

- Arbitrary repositories, untrusted multi-tenant workloads, or hostile local co-tenants.
- Fullscreen TUI, Rich/Textual/Click, animation, mouse navigation, fuzzy selection, syntax highlighting, or themes.
- Graph database, vector database, embeddings, semantic code graph, symbol resolution, whole-repo impact analysis, or “correctness coverage.”
- Runtime swarm, multi-agent orchestration framework, background workflow engine, or weeks-long collaboration.
- General shell, package installation, network tools, autonomous Git push, or durable production Git hosting.
- Chain-of-thought capture, causal inference from temporal adjacency, or claims about why the model internally acted.
- Enterprise RBAC, SSO, audit retention policy, encryption key management, DLP, SOC 2, or malicious-admin tamper resistance.
- Browser live streaming or a second set of mutation controls.
- Production-grade arbitrary-source upload to Firestore.

The ruthless test is simple: if a feature is not necessary to prove observed event → exact human correction → scoped fresh-agent brief → bound promotion, cut it.

---

## 9. Runtime event contract, evidence rules, and graph projection

### The thinnest event-first architecture

Do not convert the whole product into a speculative event-sourced platform. Add one authoritative chronological spine for runtime observations and policy/human actions, then keep the existing domain records and promotion machinery as integrity-bound materialized state.

Local development uses a tiny standard-library SQLite lineage store (`sqlite3`, WAL, `BEGIN IMMEDIATE`) beside the existing domain store. Cloud uses one Firestore run-head document plus create-once-through-Graphene per-sequence event documents. Firestore does not provide SQL-style unique constraints or storage-level immutability. One transaction reads the expected run head and checks/creates three deterministic paths: `runs/{run}/events/{zero_padded_seq}`, `runs/{run}/idempotency/{sha256(idempotency_key)}`, and a global `event_ids/{event_id}` index; it then advances the head. Each index stores the canonical event digest and reciprocal IDs. This prevents one sequence from holding two events, one idempotency key from holding two digests, one event ID from appearing in two runs/sequences, or the same event from being smuggled under a second key. Both adapters expose the same narrow methods:

```text
append(run_id, expected_head, idempotency_key, event_without_server_fields) -> Event
tail(run_id, after_seq, limit) -> [Event]
verify(run_id) -> VerifiedHead | EvidenceInvalid
```

SQLite unique constraints and the Firestore transaction/indexes cover `(run_id, seq)`, global `event_id`, and `(run_id, idempotency_key)` at the service boundary. A duplicate idempotency key with the same canonical event ID and digest returns the original event; any cross-index mismatch fails closed. Terminal notification happens only after commit. Local `watch` polls or uses an in-process condition; remote `watch` uses bounded HTTP long-polling by sequence. Do not add WebSockets for the MVP.

The spine is append-only through the service API, not magically tamper-proof. A previous-event digest detects gaps, reordering, mutation, and many crash errors under an honest-host threat model. A malicious administrator who can rewrite and rehash storage remains out of scope. Every context compilation and promotion approval creates a server-issued, integrity-bound—but not externally or cryptographically signed—`HeadCheckpoint` in the existing domain store containing run ID, expected sequence, event-head digest, purpose, and bound candidate/brief digest. Verification rejects a stream that no longer contains an exact checkpointed prefix. This detects deletion/mutation **through** a checkpoint, not arbitrary later-tail deletion. Uncheckpointed tail deletion, and all deletion before the first independently retained checkpoint, can remain undetectable and must not be oversold.

### Canonical event envelope

```json
{
  "schema_version": 1,
  "event_id": "evt_...",
  "run_id": "run_...",
  "seq": 17,
  "session_id": "session_... or null when no model session exists",
  "invocation_id": "ADK/server invocation id or null before/without invocation",
  "model_id": "gemini-3.5-flash or null when no model is involved",
  "repo_id": "graphene-demo",
  "base_sha": "40 hex characters",
  "agent_profile_id": "auth-maintainer@1",
  "policy_revision": 1,
  "event_type": "tool.completed",
  "truth_kind": "runtime_observed",
  "authority": "scoped_tool_wrapper",
  "tool_call_id": "call_... or null for non-tool events",
  "server_recorded_at": "RFC3339 UTC",
  "idempotency_key": "run/tool-call/phase",
  "references": [
    {"kind": "file_version", "id": "fv_..."},
    {"kind": "changeset", "id": "chg_..."}
  ],
  "source_ref": {
    "kind": "tool_receipt",
    "id": "receipt_...",
    "sha256": "digest of the authority record"
  },
  "payload": {"redacted": "event-type-specific bounded fields"},
  "payload_sha256": "sha256 of the canonical payload shown here",
  "previous_event_sha256": "sha256 or null for seq 1",
  "event_sha256": "sha256 of canonical envelope excluding this field"
}
```

`session_id`, `invocation_id`, `model_id`, and `tool_call_id` are populated only for event families that have those identities; otherwise they are canonical `null`, never omitted. The versioned `agent_profile_id` is the contract identity (`auth-maintainer@1`); do not split or normalize it silently. `source_ref` is mandatory and resolves to the authority record appropriate to the event—tool receipt, token-authorized operator request receipt, policy evaluation, parser/reducer receipt, or lifecycle request—even when private content behind that record is unavailable. Its digest integrity-binds exact authority-record bytes under the honest-host model; it neither authenticates the real-world actor nor acts as a public content URL.

Server-issued fields are never accepted from model output: event ID, sequence, server timestamp, repo/base/profile/policy identity, authority, and digest chain. ADK timestamps and model labels may be preserved as non-authoritative metadata. Ordering comes only from the CAS-issued sequence, never timestamps. Raw prompts, model responses, chain-of-thought, source, diffs, search results, and stdout do not belong in the public event envelope.

### Truth kinds and authority

| Truth kind | Meaning | Legitimate authority | Examples |
|---|---|---|---|
| `runtime_observed` | A boundary wrapper observed an attempted or completed operation. | Scoped wrapper/server adapter | read started/completed, write completed, test completed |
| `server_derived` | Deterministic computation over verified records. | Reducer/hash/parser | hunk extracted, graph edge, coverage obligation status |
| `human_attested` | The bearer holder explicitly supplied or approved a statement; their real-world identity is unverified. | Token-authorized operator request | feedback recorded, memory approved, promotion approved |
| `policy_authoritative` | Server policy allowed/denied an action or presented a frozen policy choice. | Policy/context compiler | frozen scope clarification asked, scope denied, completion denied, handoff denied |
| `model_proposed` | Model text requested an action or proposed completion; it is not fact. | ADK/model adapter | completion attempt, model-generated text explicitly labeled as proposal |

The model never self-attests a read, test, approval, scope, identity, or successful write. The tool wrapper is authoritative for observable calls/results; ADK events corroborate invocation and tool-call IDs. The server is authoritative for policy, test profile, candidate digest, and promotion. The human is authoritative only for the exact statement and decision they submitted. Never infer causality from timing.

### Minimum event vocabulary

- Lifecycle: `run.started`, `invocation.started`, `invocation.completed`, `invocation.failed`, `run.interrupted`, `run.failed`, `run.ended`. `invocation.started` is durable immediately before dispatch. A normal ADK return appends exactly one completed/failed event; a crash with unknown dispatch outcome closes only through terminal `run.interrupted`, never a fabricated invocation result.
- Tool boundary: `tool.started`, `tool.completed`, `tool.failed`, carrying an operation name from the fixed allowlist.
- Interaction: `clarification.asked`, `clarification.answered`, `completion.attempted`. The first two are new durable actions, not current behavior. In this MVP the frozen file-vs-all-Auth question comes from the server contract, so `clarification.asked` is `policy_authoritative` with a contract/policy `source_ref`; the operator's answer is `human_attested`. Never attribute that question to the model unless a later runtime actually generates it. `request_completion` is a terminal protocol tool, not a generic `tool.*` operation: when the model calls it, the server appends `completion.attempted`, immediately evaluates policy and appends `completion.denied`, suspends the run in `NEEDS HUMAN`, and rejects every later model tool call for that invocation. An ADK final message alone is not an attempt.
- Artifact: `candidate.created`, `changeset.parsed`, `test.receipt.created`.
- Human: `feedback.recorded`, `memory.proposed`, `memory.approved`, `memory.rejected`, `promotion.approved`.
- Context: `context.compiled`, `context.injected`, `handoff.denied`.
- Policy: `scope.allowed`, `scope.denied`, `completion.denied`, `promotion.denied`, `promotion.completed`.

Do not create an event type for every function call. One `tool.*` family plus a strict operation enum is sufficient.

For an ordinary tool call, append `tool.started`, perform the bounded operation, then append exactly one `tool.completed` or `tool.failed`. For writes, the completion event references before/after file versions and the resulting changeset/hunk artifacts. For tests, it references the exact candidate patch digest and local receipt digest. `request_completion` follows the specialized terminal protocol above and emits no redundant generic tool events. If the process crashes after an ordinary `tool.started`, recovery appends `run.interrupted`; it does not invent a completion.

Promotion avoids a circular “bind the final head” claim:

1. When Agent B reaches `NEEDS HUMAN`, persist a candidate `HeadCheckpoint` at sequence `N` and head digest `H_N`.
2. The operator's promotion request must present `N`, `H_N`, and the exact candidate/test/brief/injection/decision digests.
3. `promotion.approved` is event `N+1`; it references that checkpoint and human request receipt.
4. Reconstruction and authoritative retest produce a promotion receipt binding the pre-completion head `H_(N+1)` and every supplied artifact digest.
5. `promotion.completed` is event `N+2`; its `previous_event_sha256` is `H_(N+1)` and it references the promotion-receipt digest. The resulting `H_(N+2)` is the final replay head but is not recursively embedded in its own receipt.
6. Reconcile a final domain `HeadCheckpoint` for `N+2/H_(N+2)`. It can be written only after the event exists, so a crash between steps 5 and 6 is recoverable by verifying the exact event/receipt and creating the identical checkpoint. Deleting `N+2` after that is detected. A later uncheckpointed tail remains subject to the stated limitation.

Any concurrent event or stale expected sequence/head rejects the promotion request. “Promotion binds the event head” means this exact protocol, not a vague final-hash assertion.

### File, version, changeset, and hunk identity

Keep these separate:

- `file_id = sha256(repo_id + canonical_path)` identifies a logical path.
- `file_version_id = sha256(file_id + content_sha256)` identifies observed content.
- `changeset_id = sha256(base_sha + canonical_patch_sha256)` identifies the candidate delta.
- `hunk_id` continues to use the strict canonical unified-diff parser and exact hunk digest.

A file's baseline byte/line measurements freeze at its first accepted observation. A read event references a file version. A write completion references before and after versions plus the current changeset. Feedback must resolve to an event and hunk in the same run, repo, base, file version lineage, and profile scope.

### Deterministic projection

The graph is a pure reducer over verified events plus referenced immutable artifacts:

```text
verify sequence/digests/references
→ fold events in ascending seq
→ emit canonical nodes/edges/obligations/omissions
→ sort by stable keys
→ canonical JSON
→ graph_sha256
```

Repeated reads aggregate on the file-version node with `first_seq`, `last_seq`, and `count`; the event rail retains every observation. Only accepted evidence creates graph edges. A temporal neighbor never becomes a causal edge. `why` can say “unknown” instead of filling a gap.

File visibility follows runtime evidence, not a precomputed repository map. A successful bounded search may create a `DISCOVERED` path stub with only allowed metadata; a successful read upgrades it to a versioned `READ` node; a successful write upgrades/adds `EDITED` state and recomputes exact `+/-` metrics from the canonical candidate patch. A failed or denied operation creates an attempt/denial event but never exposes a file node or content. Read-only nodes remain visible after later edits. Before candidate creation, test acceptance, brief compilation, and promotion, re-hash the private fixture against the last wrapper-owned versions; any unexpected change yields `EVIDENCE INVALID` and a fresh-run requirement. A richer external-change lineage is out of P0 scope.

The graph needs only these semantic node classes for the MVP: run/session, file/file-version, changeset/hunk, tool/test receipt, feedback/memory decision, context brief/injection, policy denial, promotion receipt. Preserve deterministic caps and omission counts. If verification finds a gap, conflict, unresolved reference, stale base/profile/policy, or digest mismatch, projection stops with `EVIDENCE INVALID`; no handoff or promotion may consume it.

Evidence coverage is a policy checklist, not correctness, code coverage, or impact analysis. Applicable obligations are:

1. canonical changeset/hunk persisted;
2. a passing fixed-test receipt binds the current patch;
3. applicable approved memory was injected before Agent B's model call; and
4. a required human decision binds the current digest.

Read-only files do not create obligations. The UI must say `BOUND TEST PASS`, not “covered,” and must disclose that a passing receipt does not prove a particular line was exercised.

---

## 10. Terminal interaction and honest visual semantics

### Exact interface

```text
graphene run baseline_max_attempts --profile platform-maintainer@1
graphene watch <run-id>
graphene why app/auth/limiter.py --run <run-id>
graphene inspect <event-or-hunk-id> --run <run-id>
graphene feedback <hunk-id> --event <write-event-id> --run <source-run-id> --message "When security-sensitive authentication behavior changes, add or update tests/test_security_policy.py with a regression test covering that behavior."
graphene answer <question-id> --choice all_auth
graphene memory approve mem_auth_review@1
graphene handoff <source-run-id> --to billing-observer@1 --task adapted_window_seconds
graphene handoff <source-run-id> --to auth-maintainer@1 --task adapted_window_seconds --start
graphene promote <consumer-run-id>
graphene replay <run-id> --speed 8
graphene --json why app/auth/limiter.py --run <run-id>
graphene --json watch <run-id>
graphene --json replay <run-id> --speed 8
```

`<source-run-id>` is Agent A's feedback-bound source run at a verified `NEEDS HUMAN` head; it is not called completed or promoted. `handoff ... --start` prints a new `<consumer-run-id>` plus session/invocation IDs and watches Agent B by default; `--no-watch` returns immediately after printing those IDs. Capture the returned consumer run for `watch`, `promote`, `why`, and `replay`. The denied Billing command returns no consumer run. Initial `run` also watches by default; `--no-watch` prints the run ID and exits. The CLI calls a headless application service in-process locally or an explicitly configured Cloud URL remotely. It never secretly launches or depends on a localhost web server.

`--json` is a global option and therefore precedes the subcommand. `graphene --json watch` and `graphene --json replay` emit one canonical event envelope per line as NDJSON. Diagnostics go to stderr. JSON mode contains no ANSI, headings, spinners, or commentary. Non-TTY and `NO_COLOR` output remain readable. Stable IDs are always printed in full or in an unambiguous prefix that `inspect` accepts.

### One live view

```text
Graphene  run_b29a  NEEDS HUMAN  Gemini 3.5 Flash / Google ADK
Task: change authentication window from 60 to 90 seconds
Read scope: 6 tracked fixture files | Write scope: limiter.py, test_security_policy.py
HANDOFF  Auth: 1 approved lesson, 2 evidence refs, fresh session
DENIAL   Billing: 0 memory/evidence/source/tools, no session/model call
Evidence obligations: 3/4 | GAP: human promotion

WORKING SET 3/15
 [#...] R  tests/test_rate_limit.py      461 B / 17 L
 [##..] E  app/auth/limiter.py          1.7 KiB / 58 L  D[#...] 2%  +1/-1  T*
 [NEW ] E  tests/test_security_policy.py              +6/-0  T*

EVENT RAIL
 P 001 context    injected brief_83dd; prior messages 0 evt_01a9
 O 002 read       app/auth/limiter.py returned          evt_1c22
 O 003 evidence   opened hunk_7d1e                      evt_2d30
 O 004 write      app/auth/limiter.py       +1/-1       evt_82f0
 O 005 write      tests/test_security_policy.py +6/-0   evt_8ca2
 O 006 test       auth-fixture-v1            PASS       evt_9a31
 M 007 complete   requested via tool                    evt_a081
 P 008 complete   DENIED: human_promotion_required      evt_b118

T* passing receipt binds the whole changeset; it does not prove line coverage.
O observed | D derived | H operator-attested | P policy-authoritative | M model-proposed
```

At all widths, use the same stacked layout. Below 90 columns, truncate only human-readable labels and preserve IDs, state, exact counts, and omission disclosures. Do not create a second wide-screen dashboard for the MVP.

Explicit states, never color-only:

- `STARTING`: `run.started` is durable; no model call yet.
- `LIVE`: contiguous verified events are arriving.
- `WAITING INPUT`: a persisted clarification and exact `answer` command are shown.
- `ACCESS DENIED`: attempted path/tool and server policy reason are shown; a recoverable denial can leave the run live.
- `NEEDS HUMAN`: candidate/tests exist, but human promotion is outstanding.
- `FAILED`: last durable sequence and replay command are shown.
- `INTERRUPTED`: an unmatched start or process loss was recovered honestly.
- `PROMOTED`: exact candidate, decision, test, brief, and promotion receipt digests are shown.
- `EVIDENCE INVALID`: a gap, conflict, unresolved reference, stale identity, or digest error stopped projection.

### Size and edit encoding

File footprint represents frozen baseline size, not importance:

```text
bucket = clamp(1, 4, ceil(log2(1 + baseline_bytes / 1024)))
```

Render `[ #... ]` compactly as `[#...]` through `[####]`. Freeze baseline bytes and line count at first accepted observation so an edit does not move the visual baseline.

Edit heat is separate:

```text
ratio = min(1, (added_lines + deleted_lines) / max(1, baseline_lines))
```

Render four redundant ASCII cells plus exact percentage and exact `+added/-deleted`. New files display `[NEW] +N/-0`; deleted files display `[DEL] +0/-N`. Binary, oversized, invalid-UTF-8, and policy-denied content is metadata-only and never rendered as source or diff. Color may reinforce state but never replaces `R`, `E`, `T*`, `PASS`, `DENIED`, or `PROMOTED`.

Cap the visible working set at 15 files. Collapse excess items by directory with exact total/edited counts and an omission message. Never imply the display is a complete repository or impact map.

Required evidence labels:

- `BOUND TEST PASS`: a receipt binds the current candidate digest.
- `NO BOUND TEST`: no passing receipt binds it.
- `MEMORY NOT INJECTED`: an applicable approved revision exists, but no matching pre-call injection receipt does.
- `RELATED UNINSPECTED`: advisory relation only.
- `ACCESS DENIED`: an observed policy result, not a correctness failure.
- `T*`: candidate-bound test, not file or line coverage.

---

## 11. Backward `why`, forward handoff, and the fresh invocation

### Backward: `why`

`why` traverses only resolved evidence edges from the verified projection. It groups statements by truth kind and names unknowns. It does not summarize hidden reasoning or convert temporal adjacency into causality.

```text
WHY app/auth/limiter.py @ run_8f21
Observed
  evt_1c22  Read tool returned version sha256:... to Agent A's invocation
  evt_82f0  Write wrapper committed hunk hunk_7d1e (+1/-1)
  evt_9a31  Passing test receipt binds patch sha256:...
Human
  feedback_4ab2 anchored correction to hunk_7d1e and evt_82f0
  decision_71c0 approved mem_auth_review@1
Derived
  mem_auth_review@1 applies to app/auth/** under policy revision 1
Unknown
  No evidence proves the read caused the edit.
  No complete impact analysis was performed.
Truncation: none
```

`inspect` prints the complete redacted envelope, authority, source reference, canonical digest, referenced IDs, and—only when authorized and locally available—the exact unified diff for a hunk. It performs no inference. Missing local evidence is reported as `CONTENT UNAVAILABLE`; a digest alone is not rendered as content.

### Forward: compile, do not dump

Handoff is a deterministic policy compilation. It considers approved memory, exact feedback anchors, selected evidence, current task, repo/base, profile revision, path/tag/domain rules, allowed tools, and required test profile.

“Every considered item” has a non-circular definition. Before deciding, the compiler enumerates and stable-sorts this fixture-bounded candidate universe: every approved memory revision for the repo; every verified source-run event/artifact through the bound head; every requested task target; every policy-required path/test; every capability in the target profile; and the dependency closure of reviewer-selected evidence. It persists `candidate_set_sha256` and the generation inputs. The server-side ledger then gives each candidate exactly one include/exclude reason. A test removes one candidate before decision and must detect the candidate-set digest mismatch. Larger-repository candidate indexing is outside the MVP.

Denied Billing preview:

```text
HANDOFF DENIED  billing-observer@1
Reason: repo path, memory domain, and task-profile intersection is empty
Included: 0 memories | 0 evidence refs | 0 paths | 0 write tools
Model/session created: NO
```

The denied target sees only this safe reason/count summary. Excluded IDs, paths, memory metadata, and content remain available solely to the authorized operator's `HandoffDecision` view.

Allowed Auth preview:

```text
HANDOFF ALLOWED  brief_83dd -> auth-maintainer@1
Included
  mem_auth_review@1      approved; repo/tag/path match
  hunk_7d1e              exact feedback anchor
  app/auth/limiter.py    task target; agent must reread source
  auth-fixture-v1        required test profile
Excluded
  7 timeline events      not required for this task
  docs/security.md       outside selected evidence
Fresh session: session_b29a | prior conversation: 0 messages
Brief persisted before invocation: YES
```

### The `ContextBrief`

The current packet becomes an immutable `ContextBrief` with:

- brief ID, schema version, repo ID, base SHA, task ID/text, target profile/revision, and policy revision;
- approved memory revision IDs and exact approved text;
- selected evidence IDs plus short server-derived factual summaries and local/openable references;
- required current-source paths to reread, without pretending packet copies are current source;
- explicit read paths, write paths, tool allowlist, test profile, and byte/event caps;
- included items only; excluded item IDs, paths, content, and reasons never enter the model-visible brief;
- source graph head/hash, source run/session, and `fresh_session_required: true`;
- canonical `brief_sha256`.

The full include/exclude ledger is a separate server-side `HandoffDecision`, visible only to the authorized human review surface. It binds every considered item to an inclusion/exclusion reason and has its own `decision_sha256`. `context.compiled` binds both `decision_sha256` and the model-visible `brief_sha256`; `context.injected` also binds `prompt_sha256`, the digest of the complete instruction-plus-brief payload actually sent to Agent B. This preserves auditability without leaking excluded context to the model.

The prompt adapter must serialize the complete brief, not just task and memory. A minimal prompt shape is:

```text
You are a fresh coding agent. You have no prior conversation.
Follow the server-owned scope and fixed test profile in CONTEXT BRIEF.
Approved memory is human-attested guidance, not proof that current source matches it.
Evidence summaries describe an earlier run. Reread current source with scoped tools.
Do not claim a read, write, test, approval, or completion unless its tool/policy result succeeds.

CONTEXT BRIEF (canonical JSON; sha256:...)
{...task, approved_memory, selected_evidence, required_paths,
    read_scope, write_scope, tools, test_profile...}
```

`context.compiled` commits the handoff decision and brief first. `context.injected` then binds the exact decision, brief, and full-prompt digests; new session ID; new invocation ID; target profile/revision; model ID; and zero prior messages. Only after both are durable may the ADK call start.

“Fresh” has an executable definition:

- Agent A's runner/session object is closed and discarded.
- Agent B gets a newly generated ADK session and invocation ID.
- No prior chat messages, model responses, or hidden summaries are copied.
- The only historical input is the persisted brief.
- Agent B obtains current source only through fresh scoped reads/search and exact selected evidence only through `open_evidence`.

Separate read and write scope. For the fixture, bounded search/read may cover contract-listed safe text files; writes remain only the task's implementation and regression-test paths. `search_repo` searches only those safe tracked text files with result/byte caps. `open_evidence` resolves only evidence IDs included in the brief. A requested but excluded ID produces a persisted policy denial.

The decisive acceptance test byte-compares the canonical brief bytes embedded in Agent B's request, verifies those bytes against `brief_sha256`, separately verifies the complete instruction-plus-brief bytes against `prompt_sha256`, and observes scoped tool behavior. A packet visible only in the UI or store does not count. Two different authorized evidence selections must produce different decision/brief/prompt digests and different `open_evidence` access; excluded evidence remains denied. This proves the verified evidence projection changes the invocation while the graph itself grants no permission.

---

## 12. Reuse, redesign, freeze, and remove

| Disposition | Current component | Required action |
|---|---|---|
| Reuse | `hashing.py` canonical hashes | Keep as the single canonical serialization primitive; add event/brief helpers, not another hash library. |
| Reuse | Frozen records/lifecycle validators in `models.py` | Extend with event/brief/reference schemas and strict authority enums. Preserve `extra="forbid"`. |
| Reuse + harden | Scoped filesystem/test wrappers | Instrument real start/result events; materialize contract-tracked files only; final no-follow open where supported; never persist raw output in Firestore/logs/events. |
| Reuse | Temporary Git baseline and exact candidate/hunk parser | Add file-version identity and event references. Do not replace Git diffs with model summaries. |
| Reuse | Context intersection and empty denial | Compile a server-only `HandoffDecision` plus included-only model `ContextBrief`; split read from write scope. |
| Reuse | CAS/idempotency and promotion bindings | Preserve substitution checks and authoritative retest. Add the exact candidate-checkpoint → approval event → receipt → completion-event protocol from Section 9. |
| Redesign | `_proof_items` batch synthesis | Replace headline runtime proof with wrapper-appended events. Derived summaries may still be generated afterward but must be labeled derived. |
| Redesign | ADK loop | Capture invocation/model/tool correlation through callbacks/events while treating wrappers as the operation authority. |
| Redesign | `_prompt` | Inject canonical full brief and persist exact pre-call receipt. |
| Redesign | GraphBuilder input | Reduce verified events and immutable artifacts, not only final `RunRecord` snapshots. Preserve deterministic caps/parser. |
| Redesign | Firestore whole snapshot | Store run head and per-event allowlisted documents; move raw evidence out by default. |
| Redesign | Feedback API | Validate and persist event+hunk anchor; accept bounded reviewer text rather than one frozen sentence. |
| Redesign | Read authentication | Require the same demo token for every non-health read and mutation endpoint. |
| Freeze | Existing browser mutation flow | Make no feature additions. Keep as a legacy artifact while the CLI becomes primary. |
| Reuse later | Browser exact-diff/provenance/accessibility pieces | Expose only as a read-only receipt viewer after terminal proof is green. |
| Remove from final demo | Deterministic executor | Keep for unit tests only; never use as fallback footage or label it Gemini. |
| Remove from claims | Runtime causality, correctness coverage, durable commit, enterprise isolation, authenticated identity | Reintroduce only with direct evidence. |
| Remove from scope | Graph DB, embeddings, file watcher, live browser, TUI framework, workflow engine | They do not strengthen the central proof. |

Do not edit `README.md` until the proof gates pass. It currently has user-side changes. When documentation is eventually updated, preserve an explicit limitations table and link raw evidence artifacts.

---

## 13. Persistence, replay, crash recovery, cloud, privacy, and security

### Persistence and replay

The local lineage store is SQLite because it is in the Python standard library, provides atomic append transactions and ordered tail reads, and avoids adding infrastructure. Raw evidence may live as capped local blobs keyed by SHA-256 or in an SQLite BLOB table; choose the shorter reviewed implementation, but expose it only through digest-checked `open_evidence`.

The existing domain store continues to hold immutable memory/decision/candidate/promotion records during the MVP. Event-to-domain cross-store operations are not falsely called atomic. Every phase has an idempotency key. Startup may return an identical already-committed domain artifact only for an explicitly safe create-or-return-identical phase such as brief compilation or immutable decision creation; an unmatched tool start always becomes terminal `run.interrupted`. A terminal never renders a phase that lacks its committed event.

Replay performs no model calls, tool calls, filesystem writes, tests, or promotion. It:

1. loads events from sequence 1;
2. verifies IDs, contiguous order, previous/event/payload digests, identities, and references;
3. runs the reducer from zero;
4. compares canonical graph and obligation hashes to any recorded checkpoint; and
5. returns the projection or `EVIDENCE INVALID` with the first failing sequence.

Identical streams must produce byte-identical canonical JSON and graph hash across restart. Runtime timestamps make different executions different streams; do not claim two separate runs share one graph hash.

### Crash semantics

| Crash point | Recovery behavior |
|---|---|
| Before `run.started` commit | No run exists. Safe retry. |
| After `run.started`, before invocation dispatch | Persist `invocation.started` with session/invocation/model/brief identities immediately before the one dispatch. |
| After `invocation.started`, when request dispatch may have occurred but no terminal invocation result is durable | Outcome and possible charge/tool activity are unknown. Unless the selected ADK service is proved queryable/idempotent for that invocation ID, append terminal `run.interrupted`, never resend that invocation, discard its checkout, and start a new run/session. |
| After `tool.started`, before its result commit—including when the OS operation may already have happened | Append terminal `run.interrupted`, discard the temporary checkout, and never synthesize or append later tool success. Start a new run from a clean checkout. |
| After brief compile, before injection | `create-or-return-identical`; a conflicting brief fails closed. |
| After injection receipt, before `invocation.started` | Safe to continue only with the exact brief/session/invocation identity. Once `invocation.started` is durable, the unknown-dispatch rule above applies and no blind resend is allowed. |
| During candidate/domain save | Recover only a digest-identical immutable artifact; otherwise no graph edge or promotion. |
| During promotion | Preserve current `PROMOTING` retry semantics, exact expected revision, reconstruction, and retest. |

Inject a process exit after every append/store boundary in tests. Recovery is allowed to say “interrupted”; it is not allowed to invent continuity.

### Cloud boundary

The recorded submission must visibly use:

- Gemini 3.5 Flash through Google ADK;
- one authenticated Cloud Run backend; and
- Firestore for durable event heads/events and approved memory/receipt metadata.

Default application persistence boundary: private work executes locally and mirrors only allowlisted metadata. In the recorded public-fixture mode, the authenticated Cloud Run process transmits the bounded prompt, approved brief, and tool-returned source/evidence needed for the task to Google/Gemini. Google handles those bytes under the exact selected Gemini/Vertex service configuration and its then-current terms; Graphene's canaries do not audit or guarantee provider-side retention. “Not persisted by Graphene” never means “not disclosed to the model provider.” Therefore the submission uses only the public sanitized fixture until service configuration and retention are separately reviewed for private source.

| Transient execution/model data forbidden from Firestore, application logs, and the public event envelope by default | Durable Firestore allowlist |
|---|---|
| Raw source and diffs/hunks | Opaque IDs, event type, sequence, server time, truth kind, authority |
| Search/read results | Repo/base/profile/policy IDs and digests |
| Raw prompts and model responses | Bounded redacted counters and reason codes |
| stdout/stderr and test warnings | Test status, candidate digest, receipt digest, sanitized duration bucket |
| Exact unapproved feedback/memory | Approved revision metadata and digest |
| Ignored, secret, binary, or oversized content | Context/decision/promotion receipt metadata |
| Local evidence blobs | Sanitized fixture paths during the demo only |

For the hackathon recording, one explicit `data_classification=sanitized_public_fixture` exception may persist the canonical fixture patch/hunk and exact approved memory so Cloud cold-restart replay and exact inspection are demonstrable. The fixture is already bundled public source. The exception must be config-gated, path/repo allowlisted, visible in the terminal, and covered by a canary test. It never permits raw prompts, model responses, arbitrary search results, ignored files, or stdout. Default private-source mode gives metadata-only Firestore replay: the structural projection/digests may replay, while exact inspection honestly returns `CONTENT UNAVAILABLE` after local evidence is gone.

Firestore must not store the current whole snapshot. Use a run-head document plus deterministic-ID, create-once-through-Graphene per-sequence documents written with transactional head CAS. Cap event payloads and counts. Record only the redacted event digest in the cloud mirror; do not imply the mirror can reconstruct or verify omitted private content.

Cloud Run's writable filesystem is ephemeral. It may hold the public demo fixture during an invocation, but it is not the durability layer. Firestore's service account is server-only; no browser/CLI receives database credentials. The video must show a real service URL, Cloud Run revision/log entry, Firestore event documents, model ID, and restart recovery. A diagram or environment variable is not proof.

Google credentials and any spending remain an external authorization boundary. At this checkpoint there is no ADC/project configuration and no permission to deploy or spend credits. Alex must supply/authorize those before Stage 1/4 Cloud work.

### Access and data safety

- Require bearer-token authentication for every endpoint except `/healthz`; this includes run, event, graph, node-detail, proof, packet, and receipt reads.
- Disable permissive CORS. A single demo token means “single demo operator,” not a verified named human.
- Never log the token, raw prompt, raw source, patch, or stdout. The CLI obtains the token from an environment variable or protected config, sends it only in the Authorization header, and never accepts it as a command-line argument.
- Add an end-to-end forbidden-canary test: the canary must be absent from Firestore, API responses to unauthenticated callers, Billing's brief, Agent B's prompt when excluded, and process logs.
- Add a separate token canary test covering access logs, exception bodies, CLI stdout/stderr, event/domain persistence, and exported evidence. Redact the Authorization header before any request logging.
- Authenticate before resource existence checks to avoid ID enumeration.
- Bound request text, event payloads, result counts, event counts, and local blob sizes.
- Verify event, hunk, file version, run, repo, base, profile, policy, and candidate identities before feedback, brief compilation, or promotion.

### Filesystem boundary

Build each run from the contract's exact tracked-file inventory in a private temporary directory. Reject tracked symlinks, non-UTF-8 files, binaries, oversize files, and mismatched hashes before model access. Ignore ambient `__pycache__` rather than copying it. Continue canonical containment checks and use a directory-relative/no-follow final open (`O_NOFOLLOW` where available) for writes.

A controlled spike proved the present check-then-write path can be raced by a hostile concurrent local writer. The MVP therefore claims isolation only for its private tracked fixture, not arbitrary repositories or a malicious same-host actor.

### Authority and honesty

- Server: run/session/profile/repo/base/policy identity, ordering, timestamps, scope, test truth, brief, and promotion.
- Scoped wrapper: observed call attempt/result and exact artifacts returned.
- ADK/model: proposed text plus corroborating model/invocation/tool-call metadata; never approval or tool success.
- Human operator: submitted feedback and approval bound to exact evidence; not an enterprise identity.
- Reducer: deterministic derivations only.

No chain-of-thought is captured. No sequence/digest scheme is described as tamper-proof. No passing test is described as correctness proof. No event is attributed to Gemini merely because the server was configured for Gemini.

---

## 14. Exact three-to-four-minute demo

**Target core flow: 3 minutes 10 seconds. Hard recording ceiling: 3 minutes 50 seconds.** The 40-second reserve is for real model/retest latency, not more narration. Record a real, rehearsed run against the sanitized fixture. Dead-time cuts are acceptable only if the IDs before and after remain visibly continuous and the edit says the wait was shortened. Never splice deterministic output into a real-model run.

| Time | Product action on screen | What the judge learns |
|---:|---|---|
| 0:00–0:12 | Terminal already points at the authenticated Cloud Run URL and shows its revision plus Firestore head receipt. Say the locked pitch. Run Agent A. | This is a product action; Cloud backend, model, and framework are named. |
| 0:12–0:35 | Real Agent A's wrapper results, fixed test, explicit completion request, and policy denial arrive after persistence. | The lineage is live and separates observed/model/policy truth. |
| 0:35–1:05 | `inspect` the Auth hunk; submit the organization-specific test convention bound to the hunk/write event; answer `all_auth`; approve memory revision 1. | Exact work can receive new human guidance without claiming the model was “wrong.” |
| 1:05–1:15 | Compile the Billing handoff. Show zero authorized memory/evidence/source/tools and no session/model call. | Negative scope is a first-class product result. |
| 1:15–1:30 | Preview the human-only Auth decision and included-only model brief; show hashes, fresh-session requirement, and zero prior messages. Start it and capture the returned consumer run ID. | Server policy turns selected evidence into least-privilege context; the graph grants no permission itself. |
| 1:30–2:15 | Real Agent B starts with a new session/invocation. Show pre-call decision/brief/prompt receipts, fresh reads/evidence open, implementation/test edit, and bound fixed-test pass. | The approved lineage materially changed a fresh invocation and work product. |
| 2:15–2:30 | Agent B explicitly requests completion; policy shows `NEEDS HUMAN`. Promote the returned consumer run; show reconstruction/retest and receipt. | Memory does not bypass human promotion; the exact candidate is rebound. |
| 2:30–2:45 | Run `why app/auth/limiter.py`. Pause on Observed, Human, Derived, and Unknown. | The system explains evidence without hidden reasoning or causality claims. |
| 2:45–3:00 | Restart the CLI/service adapter; run replay. Show the same final projection hash and the persistent Cloud Run revision/Firestore sequence already present in the terminal receipt area. | Restart/replay and required Google Cloud use are visible without console navigation. |
| 3:00–3:10 | Return to `PROMOTED` and say: “Exact evidence becomes approved context; Billing receives no work context.” | The judge hears one final thesis, not a feature list. |

Do not show code, architecture, browser controls, or Devpost slides during the action sequence. Put the architecture diagram, setup commands, limitations, and evidence links in the submission materials. Cloud proof stays in persistent terminal receipt metadata; if official reviewers require console evidence, use a small pre-opened read-only split pane, never live console navigation.

### Demo reliability gates

- The baseline task allows the regression-test path. The private convention is absent from Agent A's prompt, and no reroll is used to obtain a preferred mistake.
- Both real model runs finish within the rehearsal budget. No deterministic fallback exists in the recording path.
- Dynamic IDs are captured into shell variables or prefilled commands so the operator does not type them manually.
- A fresh namespace/fixture checkout is used for every rehearsal.
- The terminal labels fixture classification and remote endpoint.
- The same raw event IDs appear in terminal, replay, and Firestore metadata.
- All secrets, project IDs that should remain private, browser notifications, and unrelated desktop content are excluded from capture.
- Two consecutive full rehearsals pass after a process restart.

### Twenty-second comprehension test

Show the `NEEDS HUMAN` screen in Section 10 without narration to five developers unfamiliar with the project for 20 seconds. Ask:

1. What changed?
2. What evidence or approval is still missing?
3. What will the fresh Auth agent receive?
4. What does Billing receive?

Pass if at least four of five answer at least three questions correctly. If it fails, replace symbols with words and delete rows. Do not add a panel.

---

## 15. Staged implementation plan, gates, owners, and kill rules

Ownership labels describe parallel workstreams, not a new runtime-agent architecture. One root integrator owns contract changes and final merge decisions.

### Stage 0 — Restore a trustworthy rehearsal baseline

**Suggested owner:** repository/integrity engineer  
**Time box:** half day  
**Order:** first

Actions:

1. Preserve the committed `README.md` and `Graphene_main_img.png` branding changes; do not overwrite or rename them during integrity work.
2. Treat the frozen contract as the sole source inventory: fail if any named path is missing, mutated, unsafe, symlinked, binary, non-UTF-8, or oversized; ignore every ambient source-root entry not named by the contract (including `__pycache__`); copy only named files; then assert the temporary checkout inventory exactly equals that contract set. Do not reject ambient untracked files, because that recreates the bytecode-poisoning bug.
3. Add authenticated reads and a regression test that every non-health endpoint rejects a missing/bad token before resource lookup.
4. Add the forbidden-warning canary and prevent raw test output from entering cloud-bound records.
5. Record the audited SHA, Python/Node versions, and clean commands in a new checkpoint artifact.

Acceptance gate:

```text
uv run pytest -q -p no:cacheprovider
node --test frontend/test/*.test.mjs
node --check frontend/src/app.mjs
node --check frontend/src/graph.mjs
node --check frontend/src/workflow.mjs
```

Run the Python suite twice in the actual working checkout without cleaning ignored bytecode between runs. Both passes and the deterministic demo must succeed. No unauthenticated evidence GET may return a resource or reveal existence.

### Stage 1 — Falsify real live ADK lineage before building UI

**Suggested owner:** runtime/ADK engineer  
**Time box:** two focused integration attempts, maximum half day once credentials exist  
**Dependency:** Alex authorizes a Google project/ADC and any credit use

Build a disposable, clearly labeled spike that invokes real `gemini-3.5-flash` through installed Google ADK with one scoped `read_file`. The wrapper appends `tool.started` and `tool.completed`; ADK callback/event data supplies model, invocation, and tool-call correlation. A minimal terminal tails the store while the model is still running.

Acceptance artifacts:

- raw redacted event JSON with CAS-issued ordered sequence, informational server timestamps, wrapper authority, model/invocation/tool-call IDs, `source_ref`, and digests;
- screen recording or timestamped transcript proving the event was visible before `run.ended`;
- restart replay with the same projection hash;
- a negative tool/path request that persists a policy denial;
- exact model configuration and Cloud/ADK receipt, with secrets removed.

Kill rule: if two time-boxed attempts cannot persist one real wrapper-observed tool call before completion, stop the pivot implementation. Do not build a simulated live CLI and do not submit “live lineage.”

### Stage 2 — Build the minimal spine, reducer, and CLI

**Suggested owners:** runtime/integrity engineer plus terminal/product engineer  
**Time box:** one day  
**Dependency:** Stage 1 green

Actions:

1. Add strict versioned event, reference, file-version, checkpoint, handoff-decision, context-brief, and projection contracts, including `invocation.*` and the nullable/source-reference rules in Section 9.
2. Freeze the narrow append/tail/verify interface and implement it in SQLite with idempotency, run-head CAS, and domain `HeadCheckpoint` records. Firestore waits for Stage 4.
3. Instrument scoped search/read/open-evidence/write/fixed-test wrappers with generic start plus one result. Give `request_completion` only its specialized attempted → denied → `NEEDS HUMAN` protocol, after which that invocation accepts no tool call.
4. Persist `invocation.started` immediately before model dispatch and an invocation result only on a known return. Unknown dispatch outcome terminally interrupts; no blind resend.
5. Reduce verified events into the bounded graph/obligation view using existing hunk/hash/cap primitives.
6. Add only `run`, `watch`, `inspect`, `why`, and `replay` to the stdlib CLI in this stage; implement NDJSON first, human rendering second.
7. Remove batch-synthesized runtime proof from headline display. Keep only honestly labeled derived summaries where useful.

Acceptance gate:

- every displayed event is already committed;
- same-ID/same-digest retry is idempotent; same key/different digest fails;
- gap, reorder, conflicting duplicate, stale identity, invalid reference, payload mutation, and any missing/mutated checkpointed prefix stop projection; uncheckpointed-tail and pre-first-checkpoint deletion remain explicit honest-host limitations;
- kill after every phase boundary yields deterministic replay or explicit interruption; once terminal, an `INTERRUPTED` run can never accept a later success event;
- a crash after `invocation.started` with unknown dispatch outcome never resends that invocation unless the exact provider operation is first proved queryable/idempotent;
- an unexpected private-fixture mutation before candidate/test/brief/promotion yields `EVIDENCE INVALID` and a fresh-run requirement;
- identical streams produce byte-identical projection JSON/hash after restart;
- `graphene --json watch` is monotonic parseable NDJSON with clean stdout;
- 80-column, non-TTY, and `NO_COLOR` snapshots are legible;
- exact `+/-`, frozen size buckets, and omission counts match canonical Git artifacts.

Do not add Firestore here merely for parity; freeze the interface and make SQLite/reducer semantics green first. Final recording still waits for Stage 4's independently tested real Firestore adapter. Do not add Kafka, Pub/Sub, a graph database, or WebSockets.

### Stage 3 — Prove correction-to-fresh-agent transfer

**Suggested owner:** context/memory engineer  
**Time box:** one day  
**Dependency:** Stage 2 event and reference verification green

Actions:

1. Make feedback accept bounded human text and require a resolvable write-event plus exact hunk anchor.
2. Preserve immutable memory proposal/approval. **Add** a separately persisted clarification question and answer—the current runtime only carries a frozen question string and selects `scope_id` inside feedback—and bind both to the memory revision.
3. Enumerate/digest the deterministic candidate universe; compile a complete server-only `HandoffDecision`; then compile a separate included-only model `ContextBrief`.
4. Add bounded `search_repo` and `open_evidence`; separate read and write scope.
5. Replace task+memory-only `_prompt` with canonical full brief injection.
6. Close Agent A, create a new ADK session/invocation for Agent B, persist injection first, then call the model.
7. Add `feedback`, `answer`, `memory approve/reject`, `handoff`, and `promote` with the exact source-run versus consumer-run grammar in Section 10. Auth `handoff --start` watches the new consumer by default; Billing returns no consumer.

Acceptance gate:

- forged/nonexistent/cross-run/cross-repo/stale anchors fail;
- the exact canonical brief bytes embedded in Agent B's request hash to `brief_sha256`, while the complete request hashes separately to `prompt_sha256`;
- Agent B has zero prior messages and a distinct session/invocation;
- every candidate-universe evidence/memory/path/tool has one stable inclusion or exclusion reason, and deliberate pre-decision omission changes `candidate_set_sha256` and fails;
- two different authorized evidence selections change decision/brief/prompt digests and `open_evidence` access; excluded evidence remains denied;
- Auth receives and uses an authorized canary/lesson; Billing and an excluded evidence request receive neither;
- Billing denial exposes only safe counts/reason, authorizes zero memory/evidence/source paths/tools, and creates no runner, session, invocation, or model charge;
- current source is reread after injection; packet evidence is never treated as current source;
- promotion follows Section 9 exactly: candidate checkpoint at `N/H_N`, approval at `N+1`, receipt bound to `H_(N+1)`, completion at `N+2` referencing the receipt, then a reconciled final checkpoint at `N+2/H_(N+2)`.

Kill rule: if Agent B does not demonstrably receive/use the approved brief, or Billing receives any authorized work context or a model invocation, kill the “flight recorder becomes briefing” thesis. A packet stored but not consumed is failure.

### Stage 4 — Cloud and adversarial proof

**Suggested owners:** trust/security engineer; Alex only for credentials, deployment, and credit authorization  
**Time box:** one day plus deployment latency  
**Dependency:** Stages 0–3 green

Actions:

1. Implement the frozen interface with Firestore deterministic sequence documents, per-run idempotency-index documents, global event-ID index documents, reciprocal digest/ID checks, transactional create/head-CAS, allowlisted fields, and no claim of native unique constraints or storage immutability. Replace whole-snapshot persistence.
2. Deploy one authenticated Cloud Run revision only after explicit authorization.
3. Run real Gemini/ADK and event persistence through that revision; exercise restart/cold start.
4. Run privacy, token-redaction, auth, corruption, checkpointed-prefix/uncheckpointed-tail deletion, invocation-dispatch and other crash boundaries, stale-policy, unexpected-fixture-mutation, symlink, oversize, reciprocal-index conflict, and substitution matrices.
5. Export redacted Cloud Run and Firestore evidence and record exact commands/config without credentials.

Acceptance gate:

- no forbidden data canary in Firestore, logs, unauthenticated responses, Billing, or excluded model input; a separate bearer-token canary appears in none of logs, exceptions, CLI output, persistence, or exported evidence;
- raw output/source/prompt/model response absent from default cloud documents;
- the exact Gemini/Vertex endpoint, service configuration, and applicable provider data-handling terms are recorded; application canaries make no provider-retention claim;
- fixture exception is explicit, allowlisted, and contains only already-public fixture material;
- Firestore transactions preserve order/idempotency under concurrent retry and reject one event ID across runs/sequences, one event under two idempotency keys, and every reciprocal-index mismatch;
- under the explicit sanitized-public-fixture mode, a cold restart replays the exact inspector/projection; in default metadata-only mode, structural replay succeeds while unavailable local content is labeled `CONTENT UNAVAILABLE`, or the run is honestly interrupted;
- a real Cloud Run URL, revision, Firestore sequence, ADK framework, and Gemini 3.5 model are visible in evidence;
- all existing promotion-substitution checks still pass.

Kill rules:

- any forbidden canary leak: stop cloud/source demonstration and revert to local-only; do not claim safe cloud memory;
- any forged/reordered/stale event changes a brief or promotion: remove “trusted lineage” and do not record;
- no mandatory real Google Cloud proof by 72 hours before submission: do not submit an ineligible demo.

### Stage 5 — Freeze, rehearse, and submit

**Suggested owner:** root integrator/product editor  
**Time box:** half day plus recording  
**Dependency:** every previous acceptance gate green

Actions:

1. Freeze contracts, fixture, model ID, commands, terminal copy, and demo namespace.
2. Run the five-person comprehension test.
3. Rehearse the exact 3:10 core sequence twice from fresh state, including restart, while remaining below the 3:50 hard recording ceiling.
4. Produce a simple architecture diagram showing local/private content, Cloud Run, ADK/Gemini, Firestore metadata/events, human decision, and fresh Agent B.
5. Update README, limitations, spin-up steps, evidence manifest/hashes, Devpost copy, and a public English/subtitled video under four minutes under the Graphene name.

Final gate:

- clean Python/frontend/adversarial suites pass twice;
- real demo passes twice with no fallback;
- video is under four minutes and legible at normal playback;
- 4/5 comprehension threshold passes;
- every spoken claim maps to a raw artifact or visible action;
- exactly Collaborative Partner is selected;
- repository and video links are public and spin-up steps work from a clean checkout.

Global ruthless cuts: fullscreen TUI, browser live mode, graph DB, embeddings, arbitrary repositories, multiple fixtures, additional model personas, general shell, production RBAC, long-running orchestration, semantic impact analysis, and any feature not on the 3:10 path.

---

## 16. Three riskiest assumptions and fastest falsification

Exactly these three assumptions determine whether the pivot survives.

### Risk 1 — Real ADK activity can become authoritative live lineage

**Why risky:** the current runner discards ADK events except `model_version`, and current proof is post-hoc. ADK event shapes do not themselves establish that a filesystem operation succeeded.

**Fastest experiment:** one real Gemini/ADK invocation with exactly one scoped `read_file`, followed by one denied out-of-scope read. Persist wrapper start/result and policy denial; correlate ADK invocation/tool-call/model metadata; tail before run end; restart and replay.

**Pass:** every displayed accepted action has a committed wrapper event, IDs correlate, CAS sequences are ordered, timestamps are present but only informational, denial is visible, and replay hash matches.  
**Fail/kill:** two focused integration attempts cannot meet that bar.

### Risk 2 — A scoped lineage brief changes a genuinely fresh agent without leakage

**Why risky:** today's packet IDs never reach the model. Model behavior may ignore the approved correction, and broad evidence can leak across profiles.

**Fastest experiment:** put an authorized canary only in approved Auth memory/evidence and a forbidden canary only in excluded local evidence. Destroy Agent A. Launch fresh Auth and Billing handoffs. Byte-check the canonical brief embedded in the prompt, separately hash the full prompt, and inspect tool use.

**Pass:** Auth's embedded brief matches `brief_sha256`, the full request matches `prompt_sha256`, and Agent B performs the required regression behavior; Billing receives zero authorized work context and no invocation; the forbidden canary appears nowhere in Firestore, Billing, or Agent B input.  
**Fail/kill:** a stored packet is not enough—if fresh behavior/negative scope is not observable, kill the core thesis.

### Risk 3 — Integrity/replay remains fail-closed across retries, corruption, and crashes

**Why risky:** current snapshots accept payload forgery/tail deletion and execution crosses non-atomic boundaries that can strand queued/running runs.

**Fastest experiment:** inject a crash after every append/domain boundary, then retry, duplicate, gap, reorder, mutate, truncate after a recorded checkpoint, substitute a stale base/profile/policy, forge references, and restore.

**Pass:** each case either reproduces byte-identical projection/receipts or yields an explicit `INTERRUPTED`/`EVIDENCE INVALID`; no malformed stream creates a brief or promotion.  
**Fail/kill:** any malformed input changes an authorized brief or promoted candidate. Narrow claims further if only pre-checkpoint tail deletion remains outside the stated honest-host model.

---

## 17. Thin-MVP limitations versus enterprise vision

| Thin MVP tells the truth about | A later enterprise product would require |
|---|---|
| One sanitized, public fixture | Arbitrary private repositories, data classification, policy discovery, and tenant isolation |
| One shared demo-operator token | SSO, RBAC/ABAC, named human identity, delegation, revocation, and audited admin actions |
| One process/run at a time | Distributed sequencing, queues, backpressure, concurrency control, and multi-region recovery |
| Honest-host digest-chain integrity | External anchoring/signatures, WORM retention, key management, clock assurance, and malicious-admin threat modeling |
| Scoped wrapper observation | Sandboxed execution, container/VM isolation, egress controls, package provenance, and hostile symlink/race resistance |
| Capped text files and exact Git hunks | Binary/notebook/generated-file semantics, rename history, submodules, LFS, and large-repo performance |
| Fixed tests bound to one candidate | Policy-defined CI matrices, flaky-test handling, coverage provenance, deploy checks, and supply-chain attestations |
| One approved memory revision | Retention/expiry, conflict resolution, supersession, appeals, provenance-aware retrieval, and organizational policy |
| Deterministic graph over one run/handoff | Cross-run lineage, schema migration, federation, archival queries, and organizational boundaries |
| Metadata-only Firestore persistence by default plus explicit public-fixture exception; Google/Gemini handles task content under the selected service terms | Customer-managed encryption, residency, DLP, redaction review, privacy deletion, and regulated retention |
| Temporary promotion receipt | Durable repository integration, signed commits, protected branches, pull requests, and revocation/rollback |
| No causal or correctness claim | Evaluated causal explanations, impact analysis, and formal policy assurance—only if separately proved |

The enterprise vision is not the hackathon roadmap. It is a boundary that prevents the thin demo from borrowing credibility it has not earned.

---

## 18. Copy-paste implementation prompt for the next root Ultra agent

```text
You are the root implementation agent for Graphene. Work autonomously and use parallel subagents for bounded audits/implementation/review. Your job is to implement and falsify the singular PIVOT in CLI_LINEAGE_JUDGE_DECISION.md, not to write another broad plan.

Repository and truth baseline
- Start in the actual Graphene checkout.
- Read GRAPHENE_CLI_LINEAGE_JUDGE_PROMPT.md and CLI_LINEAGE_JUDGE_DECISION.md completely before changing code.
- Current HEAD at handoff: d36ff4b6a37f160e1122307f3e48cea953fcd223 on main, matching origin/main.
- Audited implementation parent: ce9dfbe0d0e2910b0c1f7216bf944fbc5987d206.
- Current origin/main: d36ff4b6a37f160e1122307f3e48cea953fcd223. Relative to ce9dfbe it changes only README.md and adds the now-tracked Graphene_main_img.png; implementation code is unchanged.
- Recheck git status first. Preserve the committed README/image and all unrelated/user changes. Do not infer a rename—Alex must resolve Graphene versus Graphene before Stage 5.
- Do not commit, push, deploy, publish, spend cloud credits, or move the repository without explicit authorization in your active session.

Locked product
Graphene turns observed coding-agent work into the smallest approved briefing a fresh agent is authorized to use—and refuses to promote work without matching evidence.

The only demo loop is:
observe real Agent A → anchor one correction → approve one lesson → deny Billing with no invocation → compile/persist a least-privilege brief → destroy Agent A → inject that brief into fresh Agent B → verify/retest → human promote → why/replay.

Non-negotiable honesty
- Deterministic-local execution is test-only and may never be presented or recorded as Gemini.
- Real Gemini 3.5 Flash through Google ADK and real Google Cloud infrastructure are mandatory gates, not implied features.
- Tool wrappers attest observed operations. ADK/model metadata only corroborates model/invocation/tool-call identity.
- Keep runtime-observed, server-derived, human-attested (bearer identity unverified), policy-authoritative, and model-proposed truth distinct.
- Never capture or claim chain-of-thought. Never infer causality from timing.
- Never call a digest chain tamper-proof, a passing test correctness/coverage, the demo token human identity, or a temporary SHA a durable commit.
- Raw source/diff/search/prompt/model output/stdout must not persist in Firestore, application logs, or the public event envelope by default. The authenticated execution process sends bounded prompt/tool content to Google/Gemini under the exact selected service configuration and then-current terms; application canaries do not audit provider retention. Only the explicit sanitized-public-fixture exception may persist exact fixture patch/hunk and approved memory. Canary-test both application data and bearer-token boundaries.

Ruthless scope
- One sanitized frozen fixture; one Gemini model; platform-maintainer, auth-maintainer, and billing-observer profiles; one Agent A and one fresh Agent B.
- Exact agent tools: search_repo, read_file, open_evidence, write_file, run_fixed_test, and zero-argument request_completion. No list tool and no shell.
- Stdlib line-oriented CLI. No Click/Rich/Textual/curses, fullscreen TUI, graph DB, embeddings, filesystem watcher, WebSockets, arbitrary repo support, browser live mode, shell tool, workflow engine, or runtime swarm.
- Keep the existing browser unchanged during P0 work; it may later remain a secondary read-only receipt viewer.
- Preserve existing hashing, frozen contracts, exact Git patch/hunk parser, scoped wrappers, context intersection, CAS/idempotency, adversarial tests, and promotion reconstruction/retest bindings.

Required order—do not polish ahead of proof

Stage 0: restore trustworthy baseline
1. Make the contract the sole source inventory: reject any missing, mutated, traversal/unsafe, symlinked, binary, non-UTF-8, or oversized **named** path; ignore ambient source-root entries not named by the contract; copy only named files; then reject any mismatch between the materialized temporary inventory and the contract set.
2. Authenticate every non-health GET and mutation before resource lookup.
3. Keep raw test output out of cloud-bound data; add durable regressions for the warning canary, forged feedback event ID, unauthenticated evidence reads, and existing user-token redaction.
4. Run Python/frontend/demo twice in the real checkout without deleting ignored bytecode between passes. Ambient untracked fixture entries are ignored; the materialized temporary inventory must still exactly equal the contract set.

Stage 1: disposable real-ADK falsification spike
1. First check whether Alex has authorized credentials/project/credit use. If not, record the exact blocker and continue all non-cloud work; do not fake the gate.
2. With authorization, make one real gemini-3.5-flash ADK call using one scoped read_file plus one denied read.
3. Persist wrapper-observed start/result/denial before terminal display; correlate ADK model/invocation/tool-call IDs; show the accepted event before run end; restart/replay.
4. Save redacted raw evidence. If this cannot pass after two focused attempts, stop the live-lineage pivot and report the kill condition.

Stage 2: event spine, reducer, CLI
1. Add strict versioned Event, EvidenceReference, FileVersion, HeadCheckpoint, HandoffDecision, ContextBrief, and projection contracts with extra fields forbidden. Event source_ref is mandatory; session/invocation/model/tool-call IDs are explicitly nullable by event family; agent_profile_id stays versioned, e.g. auth-maintainer@1.
2. Freeze append/tail/verify and implement only stdlib SQLite here. Same idempotency key + same digest returns the original event; any conflict fails closed. Firestore waits for Stage 4.
3. Server issues IDs/order/time/identity/authority. CAS sequence is order; timestamps are informational. Previous/payload/event digests and domain HeadCheckpoints provide honest-host integrity. Detect a missing/mutated checkpointed prefix; disclose uncheckpointed-tail and pre-first-checkpoint deletion limits.
4. Instrument search/read/open-evidence/write/fixed-test wrappers with generic start plus one completion/failure. `request_completion` instead emits only `completion.attempted`, immediate policy `completion.denied`, and terminal `NEEDS HUMAN`; reject later model calls for that invocation. Publish/render only after commit.
5. Persist `invocation.started` immediately before model dispatch. If a crash leaves dispatch outcome unknown, never blindly resend; terminally interrupt and create a fresh run/session unless the exact provider invocation is proved queryable/idempotent.
6. Reduce verified events plus immutable artifacts into a deterministic bounded graph. Preserve exact hunk parser, provenance, caps, omissions. Stop on gaps/conflicts/stale identity/unresolved refs.
7. Build only the Stage 2 stdlib CLI commands: `run`, `watch`, `inspect`, `why`, and `replay`. Implement canonical NDJSON first; human rendering second. No localhost dependency.

Stage 3: fresh-agent context proof
1. Require feedback to bind a resolvable write event and exact same-run/repo/base/file-version hunk. Accept bounded reviewer text.
2. Add and persist the clarification question and answer; current code only selects scope inside feedback. Bind them to immutable memory proposal/approval.
3. Deterministically enumerate and hash the candidate universe. Persist a server-only HandoffDecision with every include/exclude reason. Compile a separate model-visible ContextBrief containing included items only—task, approved memory, selected evidence summaries/refs, current-source paths, separate read/write scope, tools, test profile, source graph/head, and fresh-session requirement. Never leak excluded IDs/paths/reasons to the model or denied target.
4. Persist context.compiled with candidate-set, decision, and brief digests. Persist context.injected before the call with byte-exact brief digest, separate full prompt digest, new session/invocation, profile/model, and zero prior messages.
5. Replace the task+memory-only prompt. Embed canonical brief bytes exactly; Agent B rereads current source through scoped tools. Prove that different authorized evidence selections change brief/prompt digests and open_evidence access.
6. Billing denial exposes only safe counts/reason, authorizes zero memory/evidence/source paths/tools, and creates no runner/session/invocation/model call.
7. Promote the consumer run using the exact sequence protocol: candidate checkpoint N/H_N; promotion.approved at N+1; retest receipt bound to H_(N+1); promotion.completed at N+2 referencing that receipt.
8. Add Stage 3 CLI commands: `feedback` (source run + hunk + write event), `answer`, `memory approve/reject`, `handoff` (source run; returns and watches a consumer run), and `promote` (consumer run).

Stage 4: security/cloud proof
1. Implement the frozen store interface in Firestore with deterministic sequence documents, per-run idempotency-index documents, global event-ID index documents, reciprocal digest/ID checks, transactional create plus expected-head CAS, and field allowlists. Do not call Firestore events natively immutable or uniquely constrained.
2. Run data/token canaries, auth, forged/reordered/duplicate/gap/stale-reference, checkpointed-prefix/uncheckpointed-tail deletion, invocation-dispatch and every other crash boundary, unexpected fixture mutation, path/symlink, oversize/binary, substitution, restart, reciprocal-index conflict, and concurrent-retry tests.
3. Only with explicit authorization, deploy one authenticated Cloud Run revision and prove real Gemini/ADK + Firestore + restart. Exact cold-restart inspection uses the labeled sanitized-public-fixture exception; default metadata-only replay must label missing content. Do not claim readiness from mocks.

Stage 5: freeze/demo
1. Require all suites and the exact 3:10 core flow to pass twice from fresh state and stay below 3:50 with real latency.
2. Run the five-person 20-second comprehension test; pass is 4/5 people answering 3/4 questions.
3. Ask Alex to resolve Graphene versus Graphene. Only after proof is green and branding is decided, update README/submission copy, architecture diagram, setup, limitations, and evidence manifest.

Acceptance invariants
- Every displayed event was durably appended first.
- Replay makes no external calls or mutations and produces byte-identical canonical projection/hash for an identical stream.
- Crash recovery follows the per-phase table in Section 13: an unmatched tool start becomes terminal interruption and never later success; only explicitly safe create-or-return-identical phases resume. Recovery invents no success.
- Forged, reordered, duplicate-conflict, gapped, stale, cross-run/repo, or unresolved evidence cannot create a brief or promotion.
- Canonical brief bytes embedded in fresh Agent B's request match brief_sha256; the whole instruction-plus-brief request separately matches prompt_sha256; prior conversation count is zero.
- The HandoffDecision, not ContextBrief, contains the complete candidate-set include/exclude ledger. Candidate-set omission is detectable.
- Billing gets zero authorized memory/evidence/source paths/tools and zero model invocation; it may receive only profile/task identity plus a safe denial reason/count.
- The data canary reaches neither Firestore, logs, unauthenticated clients, Billing, nor excluded Agent B input. The bearer-token canary also stays out of exceptions, CLI output, persistence, and exported evidence.
- Promotion retains exact candidate reconstruction, authoritative retest, memory/decision/revision binding, and follows N/H_N → N+1 approval → H_(N+1)-bound receipt → N+2 completion → reconciled N+2/H_(N+2) checkpoint.
- Agent A may write the regression-test path. Narration says only that the organization-specific convention was absent from its input; never reroll or constrain the model to manufacture a miss.

Operating method
- Inspect before editing; use rg first; preserve user changes; apply small reviewed patches.
- Assign independent runtime, security, terminal, and repository-truth work when concurrency helps. Root owns all final contract decisions.
- Run the earliest unresolved falsification before downstream polish.
- At each stage write a checkpoint with audited SHA, exact commands/results, accepted/rejected claims, evidence paths, open risks, and one NEXT ACTION.
- If a detail in the decision can be simplified without weakening its observable contracts, security boundary, or demo proof, prefer the smaller design and document the reason.
- Do not stop for an idle agent or one failed experiment. Stop only on completion, an explicit kill rule, a true credential/spending/authority blocker after all local work is exhausted, user interruption, or repository-integrity risk.

Deliverables
- Working implementation and tests.
- Raw redacted real-ADK and real-Cloud evidence.
- Exact terminal transcript/NDJSON and restart replay hashes.
- Updated implementation checkpoint and limitations.
- Final sub-four-minute demo script and architecture diagram.

Begin by verifying repository location, current HEAD versus audited implementation parent, status, current test behavior, and whether Google authorization exists. Execute Stage 0 now. If authorization is available afterward, run the smallest possible Stage 1 spike. Do not begin with UI work and do not block Stage 0 on credentials.
```

---

## Final checkpoint

**Verdict remains:** `PIVOT`.  
**Accepted foundation:** exact Git evidence, scoped tools, immutable memory decisions, context intersection, CAS/idempotency, deterministic bounded projection, and fail-closed promotion.  
**Rejected headline claims:** live/append-only Gemini lineage, graph-driven invocation, productized Billing denial, metadata-only Firestore persistence, authenticated identity, and real Cloud readiness—all remain false until their gates pass.  
**Open external blocker:** no authorized Google project/ADC/credit path was available during this judge pass.  
**NEXT IMPLEMENTATION ACTION:** execute Stage 0's fixture/auth/privacy fixes and make the actual checkout pass twice without cleanup.  
**EXTERNAL ACTION FOR ALEX:** authorize Google project/ADC/credit use for Stage 1. Once authorized, run the one-real-`read_file` ADK persistence spike; if it fails twice, kill this pivot before spending time on terminal polish.
