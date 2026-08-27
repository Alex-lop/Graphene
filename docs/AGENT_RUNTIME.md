# Agent runtime

## Lifecycle ownership

The current MCP path separates controller lifetime from mission lifetime.
`start_goal` writes a private canonical supervisor request and signals a
detached, session-leading Python process. The tool returns after durable
acceptance; it does not await planning, workers, or finalization. A later stdio
client reads the same state root and can poll the mission.

Supervisor files are private, canonical, digest-bound, and tied to the exact
mission request. Process ownership is verified by pid, process group, start
time, and executable. If the exact owner is dead while the mission is
nonterminal, recovery may start one higher supervisor generation. Credential-
free process tests prove prompt return, idempotent duplicate acceptance,
controller disconnect, reattachment, and generation replacement using the
scripted fixture. No credentialed current-tree provider run proves this path.

## Authorization

The requested authorization mode is input, not authority. For
`policy_pre_authorized`, Graphene compiles a plan and recomputes
`PlanPolicyDecisionV1` against the exact base SHA, policy revision/digest,
scopes, command templates, concurrency, retries, budgets, network rule, and
risk gates. Only an allowed decision atomically records policy-authoritative
plan approval. Otherwise the mission enters `review_required` before dispatch.

The MCP `approve_plan` path remains available for review mode and requires the
current plan digest/revision. Its truth is `server_derived` relay evidence; it
does not establish that a human signed inside Codex, Claude Code, Gemini CLI,
or another chat client.

`auto_finalize_isolated` is similarly policy-bounded. It can approve the exact
registered final bundle and create an isolated local result ref. It cannot
merge, push, deploy, publish, or mutate the supplied checkout.

## Planner and workers

The live path pins `google-adk==2.5.0` and requests
`gemini-3.5-flash` (source-checked 2026-08-27). The planner receives bounded
Git-object manifests/excerpts and proposes typed work intent; deterministic
code assigns identifiers, validates the graph, and controls readiness.

Live planning runs in its own `python -I` child. A private fsynced journal binds
the request, strong process identity, provider transport acknowledgement, and
result. Recovery distinguishes death before dispatch from provider/billing
uncertainty after dispatch and permits at most one bounded replacement attempt;
the child has no repository mutation authority.

Each live model attempt crosses a private child-process boundary. The parent
starts `python -I -m graphene.orchestration.workers.gemini_child`, sends one
canonical size-limited frame, closes stdin, and retains all repository and
effect authority. The child receives bounded source text and task contract but
no repository path, tool, shell, store, Git, or credential-export API. It runs
one ADK call with content capture disabled and returns framed intent/receipt or
a sanitized typed error.

The child emits a `provider_dispatched` barrier only after the ADK invocation
identity exists and transport begins. The parent then binds the child to the
mission/task/attempt/lease/fence and records its exact owned-process identity.
Before that barrier, failure is a provider/runtime failure with no kill claim.
After the barrier, an external `SIGKILL` can be represented as retryable
`provider_interrupted`: provider outcome unknown, repository effect known
absent. Repository mutation happens later in the owning parent worker.

This framing and interruption classification are locally tested with protocol
and fake seams. No current proof kills a real Gemini child or validates the
returned live model identity.

## Selective recovery

Accepted publications are durable inputs. A failed sibling does not erase
them. A retryable interrupted attempt releases its lease, publishes nothing,
and may be claimed again under a higher fencing token with a bounded diagnostic
covering prior attempt, fence, result code, and receipt digest. Stale fences
are rejected. Assembly consumes accepted publications only; verification binds
the exact candidate and pending final bundle.

The legacy check-process failure fixture still proves check-stage selective
retry on macOS. The new `failure_lab.py auto` path targets only a live Gemini
model child after its provider-dispatch barrier. Its logic is tested; the live
Orders choreography is not.

## Orders hero contract

The North Star target is now the Orders API migration under
[`demo/north_star`](../demo/north_star). Its plan should have two disjoint work
roots, a dependency-file integration node, deterministic assembly, and immutable
verification. The policy permits five exact write files, denies network,
allows two workers and one retry, and selects policy pre-authorization plus
isolated auto-finalization. Target materialization and policy constraints are
locally tested. A live mission has not completed it.

## Proof labels

- `scripted-local`: deterministic fixture, never Gemini proof.
- Fake ADK/protocol tests: ADK wiring and recovery contracts, never model proof.
- Historical live evidence: evidence for its historical implementation only.
- Current live Gemini, model kill, Codex controller, and cloud behavior:
  `NOT PROVEN` until the runbook's complete evidence set exists.
