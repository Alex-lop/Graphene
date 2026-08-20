# Agent runtime

## Current implementation status

The working tree implements a real Google ADK Runner planner seam with typed output, bounded calls, disabled content capture, and no fallback. Bounded manifests/excerpts and a small `PlanIntent` are deterministically compiled into criterion-bearing scheduler contracts. After exact plan approval, the same product path can dispatch two to five typed ADK worker adapters in Graphene-owned workspaces, commit siblings in completion order, run trusted deterministic checks, integrate accepted artifacts, and stop at `awaiting_result`.

Credential-free tests exercise that runtime with real ADK sessions and deterministic fake models against a disposable repository. They prove local contracts, concurrency, isolation, and recovery—not live Gemini behavior. No credential or provider receipt was used in this proof pass, so Gemini remains **NOT PROVEN**.

The deterministic `scripted-local` runtime is a fixture, not an agent. Its checked-in overlays prove scheduler and evidence mechanics only.

## Implemented lifecycle and live-proof gap

The target live runtime is intentionally narrow:

1. Graphene constructs a sanitized path/symbol manifest and explicitly opened small excerpts.
2. Gemini proposes a bounded intent; Graphene canonicalizes IDs, artifacts, budgets, ordering, integration, and verification.
3. Human approval makes the immutable validated plan dispatchable.
4. Two distinct Gemini work executors receive different worker IDs, ADK sessions/invocations, attempts, leases, fences, and Graphene-owned workspaces.
5. The scheduler may run disjoint ready work concurrently. A worker receives only its task, prerequisites, accepted inputs, scopes, command-template IDs, checks, and remaining budgets.
6. Deterministic integration applies only accepted patches to a clean exact base. Deterministic verification checks the exact candidate.
7. The mission stops at `awaiting_result`; an exact-digest human decision controls the isolated local result.

The lifecycle is implemented and locally tested. The specifically *live Gemini* claim remains unavailable until a credentialed run captures returned model/session/invocation identities, provider usage when returned, measured overlap, exact fan-in/result, and unchanged-checkout evidence.

## Tool boundary

The intended worker tools are bounded repository search/read, explicit evidence open, lease-checked write, exact allowlisted command execution, publication request, and completion request. They do not include arbitrary shell, interpreter `-c`, installers, Git hooks/configuration, ambient environment access, undeclared mounts, or automatic network access from repository code.

Every effect binds mission, task, attempt, worker, lease, and fencing token. The durable operation journal lets an exact retry return the committed receipt without repeating a Graphene-owned effect. Graphene-owned workspaces reject symlinked administration paths and remove all Git remotes before worker execution.

## Recovery and errors

Recovery lookup is limited to an explicit bounded worker-owner set and verifies that each recovered attempt and lease have the same owner. Reassignment still requires revoking or expiring the old lease and increasing the fence. Public runtime outcomes preserve the implemented categories: provider timeout/unavailable/rate-limit, check failure, cancellation, stale lease, policy denial, `input_rejected`, `artifact_tampered`, sandbox unavailable, and `outcome_unknown` for an unreceipted or unknown effect. Raw exceptions stay private.

A failed sibling must not cancel healthy work. Accepted work commits as it completes; bounded retry receives a new attempt and higher fence. Input/artifact integrity and sandbox failures fail closed when safe continuation is impossible. Runner prefetch failures terminalize every still-fenced claimed dispatch before the coordinator stops.

Provider/process effects without authoritative receipts can have unknown outcomes. Graphene must not silently repeat them or call them exactly once. Cancellation prepares and reaps only exact owned process groups while the lease/fence remains valid, then commits the mission transition; cleanup failure aborts cancellation.

## Proof gates

Deterministic fake-ADK tests may prove routing and contracts, never Gemini behavior. A real-agent claim requires two distinct returned model/session/invocation identities, measured overlap, no fixture overlay, scoped tool receipts, accepted-only fan-in, exact verification, and unchanged user checkout evidence.

The literal demo entrypoint is `graphene mission demo`. It selects only `gemini-adk`, defaults to two workers, creates a Graphene-owned Taskmaster repository, and still requires explicit plan approval. It has no fake or replay fallback. Its live outcome is **NOT PROVEN**.
