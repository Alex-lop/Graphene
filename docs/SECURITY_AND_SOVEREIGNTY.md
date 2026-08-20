# Security and sovereignty

## Repository ownership

The supplied repository is an input, not a worker workspace. Graphene verifies its exact base identity, creates private owned workspaces, disables/removes remotes for worker execution, and keeps result commits under Graphene-owned refs. It never silently pushes, opens a pull request, deploys, or moves the user's branch.

In the generic ADK `WorkerRuntime` path, actual changed paths are measured independently after the model adapter returns and before publication; declared paths are not evidence. The bounded workspace auditor snapshots the exact Git base/admin digest, rejects unsafe path and mode shapes, rechecks for concurrent mutation, and produces content-addressed change/patch evidence. Traversal, symlink, Git metadata, submodule, untracked-secret, case-alias, out-of-policy, and out-of-lease changes fail closed in its local test matrix. The scripted fixture uses its separate frozen patch/check path and must not inherit the workspace-auditor claim.

Current Gemini worker intent can write bounded text files only. It does not express delete, rename, executable-mode, symlink, or submodule mutations, and the full scripted assembly path has not proven deletion staging. Auditor detection is not proof that those mutation types can be produced and preserved end to end.

## Isolation

A Git worktree provides edit isolation. It is not a security sandbox. Model-written code may run only through an independently proven OS/container boundary with exact command templates, bounded input/output, no network by default, non-root execution, process/resource limits, and owner-checked cleanup.

The verified scripted fixture uses macOS `/usr/bin/sandbox-exec` around a frozen sanitized test view. The generic Docker executor has hardened argument and ownership tests but no captured live daemon smoke; it remains **NOT PROVEN**. Unsupported hosts stop before executing repository code.

Only strongly identified Graphene-owned process groups may be signaled. CLI, scheduler, and live-browser cancellation prepare/reap exact owned children before the terminal state mutation; cleanup failure aborts cancellation. Unrelated processes are never targets.

## Lease and effect boundary

Every claim, heartbeat, write, command, publication, completion, cancellation, and recovery effect must bind `mission_id + task_id + attempt_id + worker_id + lease_id + fencing_token`. Stale workers cannot act.

Dispatch is at least once. Durable idempotency can establish exactly-once committed Graphene state and receipted Graphene-owned effects. It cannot establish exactly-once provider calls or external process effects across a crash when no authoritative receipt exists.

## Evidence authority

The authority is immutable initial contracts, ordered hash-chained events, and their bound content-addressed records. The v2 SQLite worktree stores immutable canonical record bytes and a verified schema-ledger digest. Full verification must reconstruct/compare every execution-relevant projection, verify artifact bytes before dependency use, and bind snapshots to the committed head.

`graphene.tree.v2` uses a domain-separated, length-prefixed entry manifest with count, path, content, type, and mode. It eliminates the prior NUL-delimiter encoding collision; it does not turn SHA-256 into proof of authorship or execution. Trusted deterministic success requires a `check.completed` event authored by the check runner and a receipt bound to the mission, plan/policy, attempt/fence, command template, inputs, candidate tree, result, and output digest. Worker-authored pass claims are rejected.

Canonical `ArtifactEnvelopeV2` is required for every successful publication and accepted dependency. After exact verification, Graphene builds, stores, and registers an immutable pending `FinalResultBundleV2`; Mission Control and both terminal decisions bind its exact ID. Rejection creates no commit. Approval first commits durable authority, then creates and verifies the isolated result, allowing safe restart recovery. Bundle export uses create-only mode-`0600` files and never overwrites a path or mutates the checkout.

Invalid evidence places reads in quarantine and freezes downstream mutation. Graphene must not append a repair event to a ledger it no longer trusts.

## Public and private data

Public Mission Control data is bounded metadata: task/dependency/worker/gate labels, safe reason codes, template/artifact identifiers, digests, test/resource/result summaries, and explicit unknowns.

Private or excluded data includes raw prompts and context, hidden reasoning and chain-of-thought, credentials, unrestricted environment variables, raw command arguments, full source/diffs, stdout/stderr, and private artifacts. Authorized bounded source or test output may enter a private worker interaction without becoming public projection data.

Local SQLite/artifacts persist until operator removal. Automatic expiry, purge, secure erase, and a complete data-subject deletion workflow are not implemented. Firestore deployment residency, backup, encryption-key, TTL, and deletion choices remain owner-controlled and **NOT PROVEN** until configured and tested.

## Resource truth

Managed process CPU/RSS/wall time, estimated context footprint, and authoritative provider telemetry are separate categories. Skills are not resource-isolation units. Stateless MCP is sessionless, not processless. Remote/shared CPU and RAM remain advisory or unavailable and cannot justify a fabricated kill decision.

The detailed legacy Auth fixture controls remain in the superseded [fixed-test executor threat model](EXECUTOR_THREAT_MODEL.md) and [data-residency matrix](data_residency.md).
