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

## Provider receipts and check executors

Every attempt whose worker returned a provider completion binds a sanitized `worker-provider-receipt` artifact (model names, credential mode, byte and token counts, the wall-clock `call_started_at`/`call_ended_at` window the runtime stamps around the model run; never prompts, outputs, environment values, or credentials) into its terminal evidence event and `Attempt.evidence_refs`, on success and on failure alike. A failed receipt write can never produce a completed attempt. `store.verify()` and the materialized-integrity check resolve the receipt bytes by digest, so a tampered receipt fails closed, and a replayed `gemini-adk` result rebuilds `provider_receipts` from evidence rather than memory (`provider_receipt_references` cites each one; `receipt_unknowns` lists anything unresolvable instead of guessing). Worker overlap is reported as `parallel_overlap` on three bases: `attempt_timestamps` and `lease_timestamps` intersect attempt lifetimes on the mission store clock (claim to completion, which proves simultaneous leases, not concurrent execution, and which coincide for terminal attempts), while `provider_call_timestamps` intersects the call windows from the evidence-resolved receipts; a live real-agent overlap claim must cite `provider_call_observed` / `provider_call_max_window_ms`, never the lifetime bases alone.

`fixture-tests` checks on the Gemini/ADK path (local approval and the outbound `executor connect` loop alike) are routed by `GRAPHENE_CHECK_EXECUTOR`: `docker` (default) uses the container executor; `host-sandbox` runs the frozen command on macOS under `/usr/bin/sandbox-exec`, honours the template's timeout up to the fixture policy's 60 second cap, and registers the check subprocess in the owned-process registry that `graphene mission cancel` reaps, which is what makes the failure laboratory's kill strongly identified. Any other value, and `host-sandbox` on a host without `sandbox-exec`, fails closed before a worker runs; Graphene never falls back silently between the two. `graphene doctor` reports the requested executor under `check_executor` without echoing unrecognised values. Two limits stay as they were: a cancel issued while an attempt is in its model phase has no owned process to reap and aborts rather than guessing, and a check group killed by an operator before the cancel event lands is attested by the check runner as a signal exit (`acceptance_check_failed`), not as a cancellation.

## Proof gates

Deterministic fake-ADK tests may prove routing and contracts, never Gemini behavior. A real-agent claim requires two distinct returned model/session/invocation identities, measured provider-call overlap, no fixture overlay, scoped tool receipts, accepted-only fan-in, exact verification, and unchanged user checkout evidence.

The literal demo entrypoint is `graphene mission demo`. It selects only `gemini-adk`, defaults to two workers, creates a Graphene-owned Taskmaster repository, and still requires explicit plan approval. It has no fake or replay fallback. Its live outcome is **NOT PROVEN**.

## Failure laboratory

`tests/unit/orchestration/test_failure_laboratory.py` (macOS only: it needs the `host-sandbox` check runner) is the deterministic regression for directive A2 on the `gemini-adk` path, driven with fake ADK workers on a two-task plan with deterministic assembly and verification. On the ADK path workers run in-process; the strongly identified Graphene-owned process is the attempt's check subprocess, which is registered in the owned-process registry only while `GRAPHENE_CHECK_EXECUTOR=host-sandbox` runs the frozen `fixture-tests` command. The laboratory takes its kill target from that durable registry record (pid equals pgid, bound to the spawned group leader by `record`), never from a process name.

Expected observable sequence, every step causally recorded in mission events:

1. Worker B's first attempt holds a live lease when its check process group is SIGKILLed. The trusted `test-receipt` minted by the check runner records `exit_code -9` with `acceptance_check_failed`, the attempt ends `failed`, its lease releases with reason `failed`, and no publication exists for it.
2. Worker A's accepted `ArtifactEnvelopeV2` publication row is byte-for-byte unchanged before and after the kill.
3. Assembly and verification have no attempts until B's replacement attempt has committed; their accepted inputs are A's publication and the retry's publication only, and `DEPENDENCY_SATISFIED` for B's task names the retry attempt.
4. Bounded recovery is automatic: `complete_attempt` records `TASK_RETRIED` and marks the task `retrying`, and the scheduler's next tick re-dispatches it as `attempt_number 2` under a strictly higher `fencing_token`. `store.assert_fence` and a `complete_attempt` publication under the old dispatch are both rejected with `StaleWorker` and leave the mission head unchanged. No operator `graphene mission retry` is driven; that command exists only for tasks that ended `failed` after exhausting retryable attempts.
5. The mission reaches `awaiting_result`, `store.verify` matches the snapshot head, and every WORK attempt, the killed one included, binds one resolvable `worker-provider-receipt`; measured overlap between A and B's first attempt is positive.
6. `graphene why .graphene/generated/b.txt` names the retry as the producer attempt with its worker, fence, and attempt number, and the snapshot keeps both attempts in B's task history; `why` on A's path names A's single attempt.

Operator script: `uv run --frozen python scripts/failure_lab.py list MISSION_ID` prints the registry's records for the mission (attempt, worker from the mission snapshot, pid, pgid, started_at, executable). `uv run --frozen python scripts/failure_lab.py kill MISSION_ID --attempt ATTEMPT_ID` sends SIGKILL through `OwnedProcessRegistry.signal`, refuses (exit 2, nothing signalled) when the registry has no record for the attempt, when the record belongs to a different mission, or when the attempt is not running under a live lease, and prints exactly what it signalled.

`sandbox-exec` replaces its own image with the frozen command immediately after spawn (same pid, pgid, and start time; `ps comm` changes from `/usr/bin/sandbox-exec` to the interpreter). The registry's liveness re-check therefore binds identity to pid, process group, and start time, and accepts an executable change only for a child recorded under that one documented exec-in-place wrapper; any other recorded executable still fails closed on a `comm` change. The regression test kills through `scripts/failure_lab.py kill` itself (store lookup of the live-leased dispatch, registry identity re-check, `killpg`), so the operator path, the `graphene mission cancel` reap, and the check timeout `SIGKILL` all act on the exec'd check group. The host runner reports `cleanup_complete` only when the owned record is gone, and rejects a template whose timeout exceeds the fixture policy's 60 second cap instead of clamping it.

**NOT PROVEN:** the live Gemini run of steps 1–6 with real workers; every kill above was exercised against fake ADK workers on macOS.
