# Proof — current implementation boundary

This page distinguishes code and credential-free checks from external proof.
The machine-readable twin is
[`contracts/product_proof.json`](../contracts/product_proof.json). A historical
run against an earlier implementation does not prove the current recovery
runtime.

## Current table

| Path | Status | What is established |
|---|---|---|
| `graphene mission replay taskmaster` | `VERIFIED_LOCAL` | A SHA-256-checked generated fixture reconstructs the read-only projection and UI. It runs no agent or test |
| `scripted-local` | `VERIFIED_LOCAL` where the configured sandbox is supported | Scheduler, detached supervisor, controller disconnect, higher-generation supervisor replacement, policy authorization, retry, exact candidate verification, and isolated auto-finalization on the fixed fixture |
| SQLite authority | `VERIFIED_LOCAL` | Typed events, idempotency, plan revision/digest binding, leases, fencing, stale-result refusal, accepted-publication fan-in, and final-bundle checks |
| Policy pre-authorization | `VERIFIED_LOCAL` | The store records a recomputed `PlanPolicyDecisionV1` and policy-authoritative approval atomically. A requested mode alone grants nothing |
| MCP stdio | `VERIFIED_LOCAL` | The official Python MCP client initializes the nine-tool server. Fixture tests show `start_goal` returns promptly and a fresh stdio process can reattach after the initiating controller exits |
| Gemini child boundary | `VERIFIED_LOCAL` protocol/fake tests | Canonical bounded frames, no repository API in the child, provider-dispatch barrier, exact owned process identity, retryable interruption, and known-absent repository effect |
| Model-child failure laboratory | `VERIFIED_LOCAL` mechanics only | Fake/protocol tests cover identity-checked signalling and higher-fence recovery mechanics. No real Gemini process has been killed in the current implementation |
| Orders target | `VERIFIED_LOCAL` target tests | Materialization, immutable acceptance suite, exact five-file write policy, network deny, two-worker cap, and Pydantic v2 migration contract |
| Installed wheel and sdist | `VERIFIER IMPLEMENTED` | The verifier builds and separately installs the sdist-derived wheel and sdist outside the source tree, then checks entry points, replay, UI, MCP, packaged resources, Orders materialization, and reattachment |
| Current live Gemini Orders mission | `NOT PROVEN` | No credentialed current-tree run reached `completed` with provider receipts and an isolated result |
| Current live Gemini model kill and recovery | `NOT PROVEN` | No captured run killed a barrier-acknowledged real model child, preserved its accepted sibling, retried under a higher fence, and completed |
| Codex MCP hero flow | `NOT PROVEN` | Configuration is documented; Codex has not started, disconnected from, reattached to, and observed a current mission through completion |
| Clean exact-SHA artifact proof | `EXTERNAL SHA MANIFEST REQUIRED` | The proof driver requires an expected clean SHA and matching canonical remote ref, then writes its SHA-named result outside the checkout; the external manifest or CI result establishes a particular run |
| Cloud Run and real Firestore | `NOT DEPLOYED — NOT PROVEN` | Emulator and protocol checks are not authenticated deployment proof |
| Docker, benchmark, screenshot/GIF, and film | `NOT PROVEN` | No responsive-daemon smoke, repeated equal-gate measurement, or current hero capture exists |

## Credential-free replay

```bash
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

The replay is useful for inspecting the UI and event projection. Its recorded
continuation remains simulated and must not be described as a fresh result.
The one-shot equivalent is
`uv run --frozen graphene ui --replay taskmaster --once`.

## Scripted fixture

```bash
uv run --frozen graphene init --repo /absolute/path/to/disposable-repo
uv run --frozen graphene mission start --repo /absolute/path/to/disposable-repo \
  --goal "Add redacted JSON and Markdown status reports." \
  --driver scripted-local
uv run --frozen graphene mission approve-plan MISSION_ID --revision 1

# Explicit credential-free automation is still simulated fixture truth:
uv run --frozen graphene mission start --repo /absolute/path/to/disposable-repo \
  --goal "Add redacted JSON and Markdown status reports." \
  --driver scripted-local --auto-approve
```

> **SCRIPTED LOCAL MISSION FIXTURE — NOT GEMINI, ARBITRARY-REPOSITORY, OR CLOUD PROOF**

The supervisor/MCP process test uses this fixture because it is deterministic
and credential-free. It proves mission lifetime can outlive the initiating
stdio controller; it does not prove provider availability or model behavior.

## Installed artifacts

```bash
python scripts/verify_installed_artifacts.py
```

The script builds the sdist, builds a wheel from that sdist, installs both
separately, changes to a directory outside the checkout, removes
`PYTHONPATH`/`PYTHONHOME`/`VIRTUAL_ENV`, and uses private HOME/state/runtime
directories. It checks:

- `graphene` and `graphene-mcp` entry points;
- verified demo replay, mission replay, and one-shot terminal UI;
- bare mission MCP and legacy MCP initialization/tool listing;
- the supported legacy CLI bootstrap resources;
- installed North Star materialization and supported legacy resources; and
- absence of pytest from package runtime requirements.

For commit-bound proof, run `scripts/reliability/exact_sha_proof.py` with an
expected SHA, its canonical remote ref, and `--require-clean`. It writes the
SHA-named manifest outside the checkout by design, avoiding a self-referential
proof commit.

## Live proof gate

The runtime pins `google-adk==2.5.0` and requests
`gemini-3.5-flash`. These identifiers were source-checked on 2026-08-27. Before
changing either live status, re-check current hackathon eligibility, requested
and returned model identity, ADK version, access mode, and endpoint.

A complete current live proof must use the Orders target and capture all of:

1. an exact committed Graphene SHA and a clean artifact build;
2. a real MCP controller returning promptly after durable acceptance;
3. controller disconnect followed by reattachment;
4. two real Gemini child processes with evidence-bound identities;
5. an identity-checked kill after the provider-dispatch barrier;
6. unchanged accepted sibling publication and a higher-fence retry only for the
   interrupted task;
7. exact assembly, verification, automatic isolated finalization, `completed`,
   `mission_summary`, and `why`; and
8. no push, merge, deploy, or mutation of the target checkout.

Earlier evidence under `evidence/` remains historical evidence for the code it
ran. It is not promoted to current recovery-runtime proof.
