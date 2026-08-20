# Taskmaster product contract

Status: accepted architecture decision, 2026-08-18

## Decision

Graphene is a local-first mission control for bounded multi-agent coding work. A developer supplies one engineering outcome and an explicit repository policy; Graphene validates a task DAG, dispatches only ready non-conflicting work, records fenced attempts and evidence, assembles accepted outputs, verifies the candidate, and creates an isolated local commit only after explicit approval.

The submission category is **The Taskmaster**. Collaborative Partner describes the decision-gate interaction. Fortified Enterprise Fleet describes the policy, isolation, lease, budget, and evidence substrate. They are not separate product modes.

## Authority boundaries

- `graphene.orchestration` owns project, mission, plan, task, attempt, lease, gate, publication, resource, scheduling, and Mission Control contracts.
- Immutable initial mission contracts, the append-only v1 mission stream, and every content-addressed canonical record bound by those events form execution authority. The deterministic scheduler consumes that authority; model output is a proposal.
- Generic mission attempts use a separate v1 evidence stream. A typed legacy-v2 link is reserved for a future trusted Auth bridge; current mission-plan validation rejects it.
- `graphene.lineage` and `graphene.viewer` remain the frozen Auth protocol tour. Their v2 event types, six operations, and `GraphSnapshot(view_version=1)` are not mission contracts.
- Mission Control data is a read-only projection, never execution authority.
  The CLI/store path remains the established operator path. An optional private
  browser command adapter is present in the current working tree, delegates to
  that store behind separate authentication/CSRF/current-head checks, and
  has backend/frontend contract coverage; a live end-to-end operator capture
  remains pending.
- A Git worktree isolates edits; it is not a security sandbox. Untrusted code runs only in a separately proven execution boundary or fails closed.
- Product-created commits stay on a Graphene-owned result ref. Graphene never pushes, opens a pull request, deploys, or mutates the user's branch.

## Durable semantics

- Every command has a stable idempotency ID and canonical request digest.
- Mission events are canonical, hash-chained, append-only, and committed atomically with indexed task, lease, attempt, gate, and publication views.
- Lease claims are transactional. Fencing tokens increase monotonically; heartbeats and results from expired or stale workers are rejected.
- Dispatch is at least once. Committed Graphene state and Graphene-owned filesystem effects are idempotent where durable receipts prove it. A provider/process effect separated from its receipt may be `outcome_unknown` and must not be silently repeated or called exactly once. Recoverable claimed attempts form the local crash-safe outbox.
- Dependencies and accepted artifact contracts determine readiness. Exact write scopes prevent conflicting active leases.
- Assembly starts only after accepted prerequisites. Verification binds to the assembled candidate. Ambiguity, invalid evidence, expired leases, and policy violations fail closed.
- A trusted check runner—not a worker—authors `check.completed` and binds the exact plan/policy, attempt/fence, command template, inputs, candidate tree, result, and bounded output receipt.
- Every successful publication carries a verified `ArtifactEnvelopeV2`; consumers receive only its accepted content-addressed reference. After exact verification, Graphene registers one immutable pending `FinalResultBundleV2`, and both terminal decisions bind that bundle ID.
- Structural tree identity uses the explicit collision-resistant encoding domain `graphene.tree.v2`; it proves content integrity under the trusted verifier/store, not authorship or execution.
- A task-scoped `needs_input` gate resumes only after a private artifact is stored and its exact digest-bound reference is committed for that task. Public state never contains the input bytes.
- Attempt, worker-time, and artifact exhaustion commit `blocked_budget`, pause dispatch, and name `replan_or_cancel`; an ordinary resume cannot silently clear the task blocker.

The executable contracts are the strict Pydantic models in
`graphene.orchestration.models`; their `schema_version=1` fields and
`model_json_schema()` output are the mission and event JSON Schemas. Unknown
fields are rejected. `TASK_TRANSITIONS` and `MISSION_TRANSITIONS` are the
authoritative transition tables:

| State machine | Allowed progressions |
|---|---|
| Mission | proposed -> running; running <-> paused; running -> awaiting_result; awaiting_result -> completed/rejected; active states -> failed/cancelled; failed -> running only for a bounded retry |
| Task | queued -> ready; ready -> running/verifying/blocked; active -> done/retrying/blocked/needs_input/failed; retrying/needs_input/blocked -> ready where declared; non-terminal work -> cancelled |

The plan validator rejects cycles, missing dependencies, untestable or
unallowlisted checks, paths outside policy, missing artifact contracts,
cross-task write overlap, uncovered or self-verified criteria, incomplete
artifact frontiers, policy budget excess, and unsupported assembly/verification
shapes. The scheduler consumes only a validated, immutable approved revision.

## Threat and capture boundary

- Trusted: the local operator, checked-in project policy, canonical reducers,
  and Graphene-owned SQLite/Firestore control state after verification.
- Untrusted: model output, repository contents, task patches, tool output,
  browser input, replay files before digest verification, and remote telemetry.
- Private-only: prompts, reasoning, environment variables, credentials, raw
  command arguments, unrestricted paths, and full tool payloads. Public mission
  events contain bounded labels, template IDs, content-addressed receipt and
  artifact hashes, and explicit unknowns instead.
- Edit worktrees are isolation, not sandboxes. Execution requires the proven
  bounded platform/container path; otherwise Graphene stops before running
  code. Only strongly identified Graphene-owned process groups may be managed.
- Managed-runtime samples, context estimates, and provider/MCP telemetry stay
  distinct. Remote/shared CPU and RAM are advisory or unavailable and cannot
  trigger an automatic kill.

## Proof modes

| Mode | Establishes | Does not establish |
|---|---|---|
| Verified mission replay | Deterministic mission projection and decision UI from a hash-checked generated scripted fixture | Live workers, new checks, human attestation, Gemini, or cloud |
| Scripted local mission after plan approval | Scheduler, isolated fixture workspaces, real bounded checks, retry, assembly, verification, and optional isolated result | Independent model quality, arbitrary repositories, or cloud |
| ADK fake | Real ADK Runner planner and worker plumbing, concurrent isolated work, and deterministic runtime contracts with fake models | Gemini or independent-agent behavior |
| Gemini ADK | Implemented planner/worker path; only a separately credentialed run with returned model receipts proves live behavior | Any silent fallback or cloud deployment |
| Cloud Run + Firestore | Only a captured authenticated deployment and durability smoke | Local repository execution inside Cloud Run |

The default scripted start commits a validated proposal. Explicit
`approve-plan` executes it; an interactive prompt may record human approval,
while `--auto-approve` is always a simulated fixture decision. A replan command
records the request and pauses dispatch; no CLI/model path creates a linked
replacement revision. The lower-level store can validate, link, diff, and
invalidate a supplied revision N+1. Retention policy metadata is durable, but
automatic expiry and purge are not implemented. Cloud streaming is per-client Firestore polling at a
two-second interval; no shared listener or fan-out is implemented.

The checked-in default suite is credential-free. Missing credentials or an
unproven sandbox is `NOT PROVEN`, never a passing substitute. The literal
`graphene mission demo` command selects the live Gemini planner/worker path and
requires exact plan approval, but no live Gemini call or model-worker mission
was proven on this host. The official Firestore emulator production vertical is
verified locally; this does not prove deployment. Docker, a deployed cloud
service, graph-economics results, and the submission video remain **NOT PROVEN**.

The terminal-native Taskmaster surface is `graphene plan`, `graphene plan
lint/show/diff`, `graphene run`, `graphene status`, mission-shaped `graphene
watch`, `graphene why --mission`, `graphene bundle create/verify`, `graphene
cancel`, `graphene retry`, `graphene request-replan`, and `graphene task input`.
These are aliases/read surfaces over the same mission authority. Plan lint
reports criterion coverage, topological order, and deterministic issues; show
and diff verify the mission before reading its plan authority. Bundle creation
prepares and registers the immutable pending review bundle, persists canonical
bytes by bundle ID, and writes only a new private-mode output; verification
accepts that file or ID. Final approval and rejection bind that exact bundle ID.

`graphene task input` accepts 1–4096 private UTF-8 bytes from a regular file or
stdin and commits only the digest-bound evidence reference. A separately
authenticated browser seam delegates to that store operation in contract tests,
but one-command live mode does not inject it until safe staged-input cleanup
exists. No terminal command generates a replacement plan revision.

## Explicit cuts

No general shell, repository crawler, graph database, visual workflow editor, writable evidence graph, per-skill CPU/RAM attribution, generic process manager, autonomous push/PR/deploy, or additional agent framework belongs in this slice.
