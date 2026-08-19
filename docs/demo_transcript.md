# Redacted demo transcript shapes

These are representative, redacted output shapes—not copied execution logs and
not proof that a hosted run or external model occurred. Executable process
tests are under `tests/process/`; current proof truth is machine-readable in
[`../contracts/product_proof.json`](../contracts/product_proof.json).

## Taskmaster verified mission replay

```text
$ uv run --frozen graphene mission replay taskmaster

VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION,
NEW TEST EXECUTION, GEMINI, OR CLOUD
Mission Control: http://127.0.0.1:<free-port>/mission-control/<mission-id>
```

The digest-verified generated fixture illustrates two concurrent workers, dependency blocking,
one denied unsafe action, a failed check and bounded retry, one decision,
accepted-only fan-in, assembly, verification, and the final result. It executes
nothing new and is not a capture of the scripted run below.

## Taskmaster scripted local fixture

```text
$ uv run --frozen graphene mission start \
    --repo <initialized-disposable-repo> \
    --goal "Add redacted JSON and Markdown status reports to the fixture CLI." \
    --driver scripted-local

PLAN <mission-id> VALID tasks=6
Approve this bounded scripted plan? [y/N] n
status=proposed
driver=scripted-local
plan_revision=1
review_required=true

$ uv run --frozen graphene mission approve-plan <mission-id> --revision 1

status=awaiting_result
driver=scripted-local
candidate_sha256=<sha256>
verification_sha256=<sha256>
parallel_overlap_observed=true
approval_truth=human_attested
proof="scripted fixture; no Gemini or cloud execution"
```

The first command only proposes in a non-TTY. The explicit approval runs the
durable mission scheduler and real bounded fixture checks. An interactive TTY
can instead approve at the prompt. `--auto-approve` is always
`simulated_fixture`. The explicit interactive command shown is
`human_attested`; the same command under automation or piped I/O is
`server_derived`. The run does not edit the supplied repository. An exact-digest
rejection creates no commit; exact-digest approval creates only a Graphene-owned
isolated local commit.

## Preserved Auth protocol tour

The remaining shapes document the legacy v2 Auth review/handoff regression
tour. They remain supported under `graphene demo`, but are not the Taskmaster
hero or mission authority.

### Auth protocol verified replay

```text
$ uv run --frozen graphene demo --driver verified-replay

VERIFIED REPLAY — NO LIVE AGENT, HUMAN ATTESTATION, OR NEW TEST EXECUTION
Authoritative lineage writes: 0
Human-attested decisions: 0
Live agent executions: 0
New test executions: 0
Google ADK Runner: not used
Gemini calls: 0
Viewer: http://127.0.0.1:<free-port>/viewer/<root-run-id>
```

The replay opens the same read-only decision surface from a checked-in event fixture materialized through v2 verification, with simulated decisions visibly labeled. It demonstrates the Review Brief, candidate-pending attention checkpoint, typed verified-support paths, explicit `open_evidence` context reference, unknowns, and interaction design. It cannot demonstrate a captured live process, human choice, ADK, Gemini, or a new test result.

### Auth protocol scripted local workflow fixture

Supported only on macOS with executable `/usr/bin/sandbox-exec`:

```text
$ uv run --frozen graphene demo --driver scripted-local

SCRIPTED LOCAL WORKFLOW FIXTURE — NOT INDEPENDENT-AGENT OR GOOGLE ADK PROOF
Google ADK Runner: not used
Gemini calls: 0
Evidence source: committed and verified v2 SQLite lineage
Viewer: http://127.0.0.1:<free-port>/viewer/<source-run-id>
Private runtime: <owner-private-runtime>

DECISION — CORRECTION SCOPE
Candidate: <public-candidate-id>
1. Every app/auth/** change
2. Only rate-limiter changes
Choice: 1
Decision recorded: all_auth
Truth: human_attested

DECISION — MEMORY REVISION
Candidate: <public-memory-revision-id>
Scope: all_auth
Digest: <sha256>
1. Approve for bounded handoff
2. Reject; no approved-context claim
Choice: 1
Decision recorded: approved
Truth: human_attested

Billing handoff: denied
Model dispatch count: 0
Auth handoff: bounded included/excluded evidence recorded
Fresh isolated consumer runtime: <different-run-id>
Bound fixed-test receipt: <receipt-id> sha256=<sha256> passed=true

DECISION — FINAL CANDIDATE
Candidate: <public-candidate-id>
Changed paths: app/auth/limiter.py, tests/test_security_policy.py
1. Approve and create isolated local commit
2. Reject; keep evidence without a commit
Choice: 1

DEMO COMPLETE — committed lineage verified
Origin run: <source-run-id>
Consumer run: <consumer-run-id>
Promotion state: PROMOTED
Outcome: local_isolated_commit
Local commit SHA: <git-sha>
Local isolated commit — not pushed / no PR / no deployment
Viewer: http://127.0.0.1:<free-port>/viewer/<source-run-id>
Runtime retained: <owner-private-runtime>
```

Only an interactive TTY decision can be stored as `human_attested`. Piped input, automation, and replay cannot mint that truth level. A test-only simulated seam is repeatedly labeled `simulated_fixture`; it proves downstream branch mechanics, not a human decision.

### Legitimate branch outcomes

- **Narrow scope:** records `rate_limiter_only` and changes the bounded handoff surface; it is not an error.
- **Memory rejection:** records a durable rejection, creates no approved memory, makes no injected-approved-context claim, and exits cleanly inspectable.
- **Candidate rejection:** records the rejection, creates no completion/local-commit receipt, and leaves the isolated evidence inspectable.
- **Invalid evidence:** stops normal rendering as `EVIDENCE_INVALID`; no pending or successful decision may replace it.

### Auth protocol Google ADK fake-model integration

```text
$ uv run --frozen graphene demo --driver adk-fake

REAL ADK RUNNER + DETERMINISTIC FAKE MODEL — NOT GEMINI OR INDEPENDENT-AGENT PROOF
Runner: real Google ADK 2.5.0
Model: deterministic fake
External model calls: 0
```

The source and consumer tool steps traverse the real ADK Runner/session and Graphene adapter before the same terminal review branches. The deterministic fake model makes the path reproducible; it is not evidence of Gemini, autonomous intelligence, or model quality. The driver never falls back to scripted execution or replay.

## What every mode leaves explicit

The browser sees only a bounded sanitized projection. It cannot submit a database path, mutate lineage, or expose raw source, diffs, prompts, test stdout, secrets, or private artifact bytes. Billing zero-dispatch is an explicit denial result. Live drivers and the replay fixture record context compilation, inclusion, injection, opening/reference, and later operations at their labeled proof levels. Graphene does not claim that context caused or improved a later edit.

For advanced manual integration, use the current commands in [`../README.md`](../README.md). The root Docker image and mutable legacy HTTP demo are compatibility-only and are not represented by these v2 transcript shapes.
