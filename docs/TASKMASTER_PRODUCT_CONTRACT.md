# Taskmaster recovery product contract

## Promise

> **Agents stop. The mission doesn't.**

For one bounded repository goal and fixed plan revision, Graphene preserves
accepted work when a controller or worker stops, replaces only failed work
under a higher fence, and finishes an exact verified candidate with causal
evidence.

The graph is execution authority, not decoration. It governs readiness,
dependency and write-scope conflict, accepted inputs, leases, fences, retry,
assembly, verification, and finalization.

## Actors and authority

- The MCP client is a controller. It can submit a goal and read results; its
  process lifetime does not own the mission.
- The detached supervisor owns progression for one durable request. Recovery
  can replace only a dead exact owner and increments supervisor generation.
- Gemini/ADK proposes a plan and bounded file intent. Model output has no
  authority until deterministic validation and store transitions accept it.
- The project policy defines the maximum low-risk envelope. A requested
  authorization mode grants nothing.
- Workers hold task/attempt/lease/fence-scoped capabilities. They do not hold
  mission-store, Git remote, deployment, or final-decision authority.
- The trusted check runner, assembler, verifier, and store bind exact evidence.
- Mission Control is a read-only projection. It is never scheduling authority.

## Durable goal acceptance

`start_goal` requires an absolute initialized repository, bounded goal,
explicit success criteria for live Gemini, and a caller-supplied stable request
id. The accepted request binds:

- repository and clean base SHA;
- goal and sorted unique criteria;
- driver and worker limit;
- policy id/revision/digest;
- requested authorization and finalization modes; and
- a canonical request digest.

Acceptance is durable and idempotent before planning. The MCP call returns
promptly and directs the controller to poll. Duplicate identical requests
reuse the mission; a conflicting binding is refused.

## Authorization modes

### Policy pre-authorized

Graphene compiles the proposed plan, validates it deterministically, evaluates
it against the exact committed policy, and records a content-addressed policy
decision. Only an allowed decision atomically records a policy-authoritative
plan approval. The plan must remain inside read/write globs, exclusions,
commands, network mode, concurrency, retries, budgets, and risk gates.

### Review required

An ambiguous or out-of-policy plan does not dispatch. A reviewer may approve
only the exact current revision and digest. MCP approval is
`server_derived` relay truth, not authenticated human attestation.

Editing creates immutable revision N+1 and invalidates prior approval. No
attempt may claim an unapproved revision.

## Mission lifetime

The supervisor runs in a new session with no stdin and private request/state/
process files. Liveness binds pid, process group, start time, and executable.
A later MCP or CLI process can observe the same mission. If the owner is dead
and the mission is nonterminal, exact-request recovery may start a higher
generation. Two supervisors must not progress one request concurrently.

The credential-free scripted process test proves this topology. Current live
Gemini/Codex proof remains pending.

## Model child boundary

Each live Gemini worker call runs in a private isolated Python child. The child
receives one canonical, length-bounded request containing task contract,
bounded sources, accepted inputs, scopes, identity, timeout, and requested
model. It receives no repository path, effect tools, shell, Git authority,
store, or general environment API.

The child may call Google ADK once with content capture disabled. It emits a
provider-dispatch frame only after the SDK invocation exists and provider
transport begins. The parent binds that barrier to the live lease/fence and an
owned-process identity.

If the child dies after the barrier, provider outcome is unknown. Repository
effect is known absent because mutation occurs only later in the parent. The
attempt can therefore end retryable as `provider_interrupted` without claiming
the provider did or did not compute a response.

The runtime pins `google-adk==2.5.0` and requests
`gemini-3.5-flash`, source-checked 2026-08-27. A live proof must also validate
current eligibility and returned identity.

## Selective recovery invariants

These invariants apply within one fixed plan revision. An explicit new revision
deliberately invalidates publications from the old plan.

1. Accepted publications are immutable inputs and survive sibling failure.
2. A failed attempt cannot publish.
3. Retry revokes/releases the old lease and uses a strictly higher fence.
4. Old fences cannot write, publish, heartbeat, or complete.
5. Retry diagnostics are bounded and cite the prior attempt/fence/result and
   evidence digest; they cannot widen scope or weaken checks.
6. Repeating an identical bounded failure may terminalize rather than spend a
   blind retry.
7. Assembly consumes accepted publications only.
8. Verification binds the exact assembled candidate and registered final
   bundle.
9. A failed sibling does not cancel accepted healthy work.

## Finalization

`auto_finalize_isolated` is effective only when the committed policy and
policy decision allow it. It binds the exact pending bundle and may create an
isolated Graphene result commit/ref. It must not mutate the target checkout or
its current branch/index, merge, push, open a PR, publish, deploy, or obtain
remote credentials.

Review mode retains exact bundle-id approval/rejection. A mission is not the
autonomous hero success at `awaiting_result`; it must reach `completed` with a
verified isolated result.

## Orders hero

The North Star is the materialized Orders API migration:

- two disjoint work roots migrate request/API and response models;
- integration owns only `requirements.in` and `requirements.lock`;
- immutable tests preserve public behavior and forbid v1 compatibility APIs;
- network is denied;
- concurrency is two and retry budget is one; and
- only five exact files are writable.

The target and policy are locally tested. No current credentialed run has
completed it, and `graphene demo --live` is not this path; the hero begins at
MCP `start_goal`.

## Evidence and queries

Authority includes immutable initial contracts, append-only hash-chained
events, content-addressed canonical records, verified materialized state,
attempt evidence, accepted publication envelopes, trusted receipts, the exact
final bundle, and the isolated-result receipt.

`mission_summary` reports bounded outcomes and receipts. `graphene why` traces
a file through accepted producer attempts, retries, fences, checks, assembly,
and final decision. Compose that trace with `graphene mission result show` to
bind the isolated result receipt and ref; `why` alone does not claim that hop.

## Mission Capsule

Capsules cold-check internal digests and chains but do not prove producer
authenticity, provider truth, or host-clock accuracy.
`graphene mission capsule verify CAPSULE_DIR` never opens the mission store.

## Explicit non-claims

Until captured on the current committed implementation, Graphene does not
claim:

- live Gemini Orders completion;
- a real model-child kill and completed selective recovery;
- Codex start/disconnect/reattach behavior;
- authenticated human approval;
- exact-SHA installed artifact proof;
- Cloud Run, real Firestore, Docker, or general repository support;
- benchmark improvements; or
- submission media.

The replay and scripted/fake paths remain plainly labelled fixtures.

## Isolation and compatibility boundaries

A Git worktree provides edit isolation; it is not a security sandbox.
Skills are not resource-isolation units.
Stateless MCP is sessionless, not processless.
No public evidence contains prompts, raw model output, hidden reasoning, or chain-of-thought.

The default scripted start commits a validated proposal. `--auto-approve` is
always `simulated_fixture`. A replan request creates no replacement; there is
no linked replacement revision. Only the explicit export/edit/revise path
creates one. Automatic expiry and purge are not implemented.
Current mission-plan validation rejects the reserved legacy Auth link.
The cloud viewer uses polling with no shared listener or fan-out.
