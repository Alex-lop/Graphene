<p align="center">
  <img src="docs/assets/Graphene_main_img.png" alt="Graphene" width="720">
</p>

# Graphene Taskmaster

**Graphene is a local-first mission control for bounded multi-agent coding work. Give it one engineering outcome; it validates a dependency-aware work graph, dispatches only policy-allowed isolated work, adapts to bounded failures, assembles accepted artifacts, verifies the result, and creates an isolated local commit only after explicit approval.**

The primary user is a solo developer or small technical lead who otherwise becomes the scheduler for two to five coding agents. The product outcome is a verified review bundle and optional Graphene-owned local commit—not a transcript, decorative agent animation, or autonomous push.

> Shipped proof: deterministic mission replay and a macOS scripted fixture through the real durable scheduler. **NOT PROVEN:** a live Gemini mission, real Docker execution on a responsive daemon, a deployed Cloud Run/Firestore service, arbitrary-repository execution, or hackathon submission readiness.

## See the product in one command

After `uv sync --frozen`:

```bash
uv run --frozen graphene mission replay taskmaster
```

This opens Mission Control from a checked-in, SHA-256-verified generated fixture. It creates no mission state and executes no worker, test, model, or cloud call. The page and terminal stay labeled:

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

The default surface is a keyboard-accessible task table and one `Needs you` brief. A secondary graph shows only:

```text
Goal -> Tasks -> Workers/Gates -> Integration -> Verification -> Result
```

Every edge is an explicit committed relationship. Timing and visual proximity never imply causality, importance, correctness, or hidden reasoning.

## Run the scripted mission

The executable fixture requires macOS, Python 3.13, Git, `uv`, and executable `/usr/bin/sandbox-exec`. Initialize a policy in any disposable Git repository, then propose the exact checked-in scenario:

```bash
uv run --frozen graphene init --repo /path/to/disposable-repo
uv run --frozen graphene mission start \
  --repo /path/to/disposable-repo \
  --goal "Add redacted JSON and Markdown status reports to the fixture CLI." \
  --driver scripted-local
```

The default command persists a validated `proposed` mission and returns its ID. In an interactive TTY it also offers a plan-approval prompt. Otherwise, review the proposal and execute it explicitly:

```bash
uv run --frozen graphene mission approve-plan MISSION_ID --revision 1
```

For deterministic automation, adding `--auto-approve` executes immediately but records `simulated_fixture`, never human attestation. `scripted-local` deliberately operates on Graphene's small checked-in status-report fixture, not the supplied repository. The repository argument supplies an explicit initialized policy gate; the fixture has its own frozen policy and base. After approval, the run proves that the operational DAG blocks prerequisites, dispatches two disjoint workers concurrently, records fenced leases and accepted artifacts, performs one genuine failing check followed by one bounded repair, fans in through assembly, and verifies that exact candidate.

> **SCRIPTED LOCAL MISSION FIXTURE — NOT GEMINI, ARBITRARY-REPOSITORY, OR CLOUD PROOF**

Approved execution stops at `awaiting_result`. Rejecting creates no commit; approval requires the exact candidate digest and creates one commit only under a durable `refs/graphene/results/...` ref in Graphene's private fixture repository:

```bash
uv run --frozen graphene mission reject-result MISSION_ID --candidate-sha SHA256
uv run --frozen graphene mission approve-result MISSION_ID --candidate-sha SHA256
```

Neither path changes the submitted repository branch or working tree. Graphene never pushes, opens a pull request, deploys, or mutates a user branch.

## Product loop and authority

```text
outcome + ProjectPolicy
          |
          v
 model/scripted Plan proposal --> deterministic validator
                                  |
                                  v
                  SQLite mission/event authority
                    |       |          |
              fenced DAG  resource   read-only
              scheduler   governor   Mission Control
                    |
          isolated scripted workers
                    |
          generic attempt evidence
                    |
          assembly -> bound verification
                    |
          reject OR approved isolated local commit
```

- `backend/graphene/orchestration/` is the versioned mission, scheduler, evidence, projection, runtime, and cloud boundary.
- The SQLite store atomically appends canonical hash-chained events with materialized mission/task/attempt/lease/publication/gate state. Normal polling reads that indexed state and incremental tails.
- Claims are transactional; fencing tokens increase monotonically. Dispatch is at least once, while committed attempt effects and publications are idempotent and stale workers are rejected.
- Plans are immutable after approval. Cycles, missing artifacts, overlapping parallel write scopes, forbidden paths/commands, policy excess, and missing assembly/verification outcomes fail validation.
- Mission Control is authenticated and read-only. Operator decisions use the same durable store semantics through the CLI; no browser command plane ships in this slice.
- Generic attempts use mission evidence v1. The typed legacy-v2 link is reserved for a future trusted Auth bridge; current mission-plan validation rejects it.
- `backend/graphene/app.py`, root `frontend/`, and the root `Dockerfile` remain compatibility-only legacy surfaces; they are not Mission Control or mission authority.

The accepted boundary and transition tables are in [`docs/TASKMASTER_PRODUCT_CONTRACT.md`](docs/TASKMASTER_PRODUCT_CONTRACT.md). Machine-readable product truth is in [`contracts/product_proof.json`](contracts/product_proof.json).

## Proof matrix

| Path | What it establishes | What it does not establish |
|---|---|---|
| `graphene mission replay taskmaster` | Hash-verified deterministic generated projection, deltas, task evidence drill-down, accessibility contracts, and the complete illustrative product story | Captured execution history, new execution, live workers, human attestation, Gemini, Docker, or cloud |
| scripted proposal + `graphene mission approve-plan ...` | Real durable scheduler, two concurrent fixture workers, sandboxed fixture checks, retry, fan-in, assembly, verification, and optional isolated result | Independent model behavior, arbitrary repositories, Gemini, or cloud |
| ADK fake planner tests | Real Google ADK Runner/session, typed `Plan`, one-call bound, deterministic validator, and sanitized receipts with a deterministic fake model | Gemini or model-worker quality |
| Gemini ADK planner | Credential-gated proposal path for exact `gemini-3.5-flash`, with no fallback | A completed live call or full live worker mission; not run on this host |
| Docker executor | Frozen hardened container arguments, scoped repository view, output/time/resource limits, and owner-bound cleanup tests | A real container run; the available daemon did not respond |
| Cloud Run + Firestore packaging | Reproducible private read-only control-plane image and transactional Firestore adapter tests | Deployment, authenticated remote smoke, or repository execution in Cloud Run |
| `graphene demo ...` | Preserved Auth evidence/review/handoff protocol tour | The Taskmaster product loop |

The real ADK/Gemini path never substitutes replay, a fake model, or scripted output. Its credential-gated smoke is skipped as `NOT PROVEN` unless explicitly enabled with valid credentials.

## Mission Control

Mission Control answers from committed state:

- the goal and explicit success criteria;
- queued, ready, running, blocked, retrying, verifying, failed, cancelled, and done work;
- the critical blocker path, worker and fenced attempt ownership;
- one consequential decision or `No decision needed`;
- measured/estimated/unavailable resource semantics and dispatch headroom;
- assembly, bound verification, final outcome, supporting evidence, and unknowns.

Task detail includes its contract, dependencies, scopes, command-template IDs, attempts, publications, resource references, and generic evidence. Raw prompts, environment variables, command arguments, secrets, private artifacts, stdout/stderr, and chain-of-thought are excluded from the public projection. The old v2 viewer is linked only for an actual legacy-v2 attempt.

The task table is the primary interface; the Cytoscape graph is secondary. Both have non-color status labels, keyboard paths, narrow-width behavior, deterministic replay, stale-state messaging, and snapshot recovery.

## Safety and Resource Sentinel

- `graphene init` writes a deny-by-default, narrowly scoped policy template. Review its read/write globs and exact argv-form command templates before real work.
- A Git worktree provides edit isolation. **It is not a security sandbox.** Model-written code may run only through a separately proven OS/container boundary; unsupported hosts fail before execution.
- The scripted fixture reuses the existing macOS `sandbox-exec` boundary. The generic Docker boundary uses no network, non-root execution, a read-only root, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs/output/time, and a scoped no-symlink repository view. A live Docker smoke remains unproven.
- No arbitrary shell is granted. Shells, interpreter `-c`, installers, Git hooks/config, extra argv, host mounts, ambient credentials, and policy-template drift are rejected.
- Resource samples are bounded. Only strongly identified Graphene-owned process groups can be signaled, after PID creation identity and ownership checks.
- Managed process resources, estimated context footprint, and MCP/provider telemetry are separate. Remote/shared CPU or RAM is advisory or unavailable and cannot trigger an automatic kill.
- **Skills are not resource-isolation units.** Instruction and schema bytes can be measured and token counts estimated; per-skill CPU/RAM is not fabricated.
- **Stateless MCP is sessionless, not processless.** Remote CPU/RAM stays unavailable without an authoritative receipt. Owned idle STDIO MCP lifecycle cleanup is not implemented in this slice.
- The scheduler has a tested optional governor that can reduce or stop only new dispatch from measured isolated managed-memory pressure. The scripted fixture does not continuously feed that governor or exercise hard termination; that end-to-end Resource Sentinel loop remains partial. Unrelated, shared, remote, and cloud processes are never targets.

See the existing [executor threat model](docs/EXECUTOR_THREAT_MODEL.md) and [data residency boundary](docs/data_residency.md). They retain the legacy Auth details; the Taskmaster-specific boundary is the product contract above.

## Google path and submission truth

The selected category is [The Taskmaster](https://allthingsagentichackathon.devpost.com/). Collaborative Partner is the bounded decision interaction; Fortified Enterprise Fleet is the lease, policy, isolation, budget, and evidence layer—not two additional product modes.

The repository pins Google ADK 2.5 and implements a typed one-turn planner with content capture disabled. The eligible model is explicitly `gemini-3.5-flash`. The credentialed product path persists only a model-proposed plan for review; it does not execute workers:

```bash
uv run --frozen graphene mission start \
  --repo PATH \
  --goal GOAL \
  --success-criterion CRITERION \
  --driver gemini-adk
```

No credential was available for a live call, so Gemini remains **NOT PROVEN**. Missing or invalid credentials fail without scripted or replay fallback.

`deploy/cloudrun/` packages an authenticated read-only Mission Control backed by explicit Firestore configuration. Cloud Run cannot access a developer's local repository; the required authenticated outbound local-executor claim/heartbeat/result protocol is not complete. No project was authorized and `gcloud` was unavailable, so the service is **NOT DEPLOYED**. Reproducible instructions are in [`deploy/cloudrun/README.md`](deploy/cloudrun/README.md).

Cloud streaming currently polls Firestore once per client at a two-second interval; there is no shared listener or fan-out, so that runtime remains **NOT PROVEN**.

## CLI

Run `graphene doctor --repo PATH` first. It reports availability without echoing credentials and never treats configuration as live proof.

| Command | Purpose |
|---|---|
| `graphene init --repo PATH` | Create one explicit bounded project policy |
| `graphene doctor --repo PATH` | Report policy, isolation, driver, telemetry, and cloud readiness |
| `graphene mission replay taskmaster` | Launch the portable verified Mission Control replay |
| `graphene mission start ...` | Persist a scripted or Gemini plan proposal; scripted execution requires review, explicit approval, or simulated `--auto-approve` |
| `graphene mission status MISSION` | Print one committed mission snapshot |
| `graphene mission watch MISSION` | Emit committed mission state/events according to its flags |
| `graphene mission open MISSION` | Open authenticated local Mission Control |
| `graphene mission pause MISSION` | Pause new mission dispatch |
| `graphene mission resume MISSION` | Resume a paused mission |
| `graphene mission cancel MISSION` | Cancel bounded work; requires exact mission-ID confirmation |
| `graphene mission retry MISSION --task TASK` | Retry one eligible failed task within its cap |
| `graphene mission approve-plan MISSION --revision N` | Approve exactly one immutable plan revision |
| `graphene mission decide-gate MISSION --gate GATE --decision VALUE` | Record an allowed gate decision |
| `graphene mission approve-result ...` | Approve the exact candidate and create its isolated local result |
| `graphene mission reject-result ...` | Reject the exact candidate and create no commit |
| `graphene mission replan ...` | Record a replan request and pause dispatch; no linked replacement revision is generated |

Legacy `graphene run`, `graphene watch`, `graphene inspect`, `graphene why`, `graphene replay`, `graphene review`, `graphene feedback`, `graphene answer`, `graphene memory`, `graphene handoff`, `graphene promote`, and `graphene demo` remain available for the Auth protocol tour. `graphene-mcp` still exposes that tour's six scoped operations; it is not the mission scheduler.

## Verification

The default suite is deterministic and credential-free:

```bash
uv lock --check
uv sync --frozen
uv run --frozen pytest -q tests/unit tests/integration tests/process tests/adversarial --ignore=tests/process/test_mcp_stdio.py
uv run --frozen pytest -q tests/process/test_mcp_stdio.py
uv run --frozen graphene mission replay taskmaster --no-open --exit-after-replay
node --test frontend/test/*.test.mjs
node --test tests/frontend/*.mjs
node --check frontend/src/app.mjs frontend/src/graph.mjs frontend/src/workflow.mjs
node --check backend/graphene/viewer/static/reducer.mjs backend/graphene/viewer/static/viewer.mjs backend/graphene/orchestration/static/mission_reducer.mjs backend/graphene/orchestration/static/mission_control.mjs
git diff --check
```

Opt-in live smokes are proof gates, not default passing substitutes:

```bash
GRAPHENE_RUN_LIVE_GEMINI=1 uv run --frozen pytest -q tests/process/test_gemini_live.py
docker build -f docker/executor.Dockerfile -t graphene-executor:py313-pytest .
GRAPHENE_RUN_DOCKER_SMOKE=1 uv run --frozen pytest -q tests/unit/orchestration/test_sandbox.py
```

## What this sprint actually shipped

- A separate strict mission/event/evidence contract, SQLite materialized store, validator, fenced deterministic scheduler, recovery and operator commands.
- A six-task non-Auth fixture with fan-out/fan-in, actual overlap, a failed check plus bounded repair, assembly, exact verification, rejection, and isolated local approval.
- A table-first authenticated Mission Control, deterministic SHA-verified replay, NDJSON deltas, stale recovery, and task-to-attempt evidence drill-down.
- A real ADK Runner planner seam, a fail-closed hardened Docker boundary, truthful Resource Sentinel semantics, Firestore transactions, and private Cloud Run packaging.
- Preservation of the legacy Auth evidence viewer and protocol tour without weakening its frozen contracts.

Still missing for a final hackathon submission: captured real Gemini worker proof, a responsive proven execution container, an authorized deployed Cloud Run/Firestore smoke, the local-executor cloud protocol, linked replan-revision generation, automatic retention/purge, an unedited public demo video, and the five-person comprehension study. See [`simplreadme.md`](simplreadme.md) for the short judge path and [`docs/HISTORY.md`](docs/HISTORY.md) for historical versus current authority.
