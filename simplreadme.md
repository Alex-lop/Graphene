# Graphene in 90 seconds

Graphene is local-first mission control for one bounded multi-agent coding job.
It turns an outcome into a validated dependency graph, dispatches only ready
non-conflicting tasks, records fenced attempts and evidence, assembles accepted
outputs, verifies the exact candidate, and requires an explicit final decision.

## Judge path

```bash
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

The replay is cross-platform, deterministic, and SHA-256 verified. It runs no
new worker, test, model, or cloud call. Its permanent label is:

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

In Mission Control, check four things:

1. The task table shows fan-out, two concurrent workers, a failed Markdown
   check, one retry, fan-in, assembly, and verification.
2. `Needs you` shows one bounded choice with consequences.
3. Task detail links contracts, scopes, attempts, accepted publications, test
   receipts, and explicit unknowns without exposing prompts or secrets.
4. The secondary graph is only `Goal -> Tasks -> Workers/Gates -> Integration
   -> Verification -> Result`; committed relationships, not animation, drive it.

## What is real

| Path | Truth |
|---|---|
| Mission replay | Shipped generated UI/projection fixture; not captured execution |
| Scripted local | Shipped durable scheduler + real sandboxed fixture checks |
| ADK fake planner | Shipped real ADK Runner plumbing; no Gemini |
| Gemini | Credential-gated proposal code exists; live call **NOT PROVEN** |
| Docker executor | Hardened boundary tests pass; live daemon run **NOT PROVEN** |
| Cloud Run + Firestore | Reproducible packaging/adapter tests; **NOT DEPLOYED** |

The actual scripted fixture is macOS-only. Its default command validates and
persists a proposal; explicit plan approval performs the run:

```bash
uv run --frozen graphene init --repo /path/to/disposable-repo
uv run --frozen graphene mission start \
  --repo /path/to/disposable-repo \
  --goal "Add redacted JSON and Markdown status reports to the fixture CLI." \
  --driver scripted-local
uv run --frozen graphene mission approve-plan MISSION_ID --revision 1
```

An interactive TTY may approve at the proposal prompt instead. Adding
`--auto-approve` is deterministic automation labeled `simulated_fixture`, not a
human decision. The fixture never edits the supplied repository; it operates in
Graphene-owned fixture worktrees. Rejection makes no commit. Exact-digest
approval creates one isolated local commit under `refs/graphene/results/...`;
neither path pushes, opens a PR, deploys, or moves a user branch.

## Trust boundary

- The validated mission DAG and SQLite store—not a model or graph—are authority.
- Transactional leases use monotonic fencing; stale effects are rejected.
- Worktrees isolate edits but are not security sandboxes. Unsupported execution
  fails closed.
- No arbitrary shell, ambient credentials, user-checkout mount, or public raw
  prompt/environment/argv/output is allowed.
- Skills are not resource-isolation units. Stateless MCP is sessionless, not
  processless. Remote/shared CPU and RAM remain advisory or unavailable.
- A tested optional governor lets only measured Graphene-owned isolated pressure
  throttle new dispatch; the fixture does not exercise the full live loop.

The full product narrative, commands, proof matrix, and limitations are in the
[README](README.md). The accepted authority and transition contract is
[`docs/TASKMASTER_PRODUCT_CONTRACT.md`](docs/TASKMASTER_PRODUCT_CONTRACT.md).
