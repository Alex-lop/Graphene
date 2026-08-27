<p align="center">
  <img src="docs/assets/Graphene_main_img.png" alt="Graphene" width="720">
</p>

# Graphene

**Agents stop. The mission doesn't.**

[![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml)

## What Graphene does

Graphene is a terminal-native recovery runtime for bounded coding missions. A goal becomes a typed graph with scopes, checks, budgets, leases, and fences. Graphene preserves accepted sibling work when an attempt fails, retries only the failed work under a higher fence, assembles an exact candidate, and records causal evidence for `graphene why`. The intended low-risk path is authorized by an explicit checked-in policy and can finalize only to an isolated local result ref. Graphene never pushes, merges, deploys, or mutates the supplied checkout.

## Quickstart: verified replay, no credentials

```bash
git clone https://github.com/Alex-lop/Graphene.git && cd Graphene
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

The replay is SHA-256 checked and read-only. It demonstrates Mission Control,
not a new agent run. Render the same fixture once with
`uv run --frozen graphene ui --replay taskmaster --once`.

## Connect an MCP controller

`graphene-mcp` serves seven tools over stdio: `start_goal`, the deprecated
`plan_goal` alias, `get_digest`, `approve_plan`, `mission_status`, `why`, and
`mission_summary`. `start_goal` durably accepts a request and returns without
waiting for planning or execution. A detached supervisor owns the mission, so
a later MCP process can reattach and poll it.

The committed [`.mcp.json`](.mcp.json) launches the source checkout. A packaged
installation can launch `graphene-mcp` directly. The stdio protocol and
controller-disconnect behavior are fixture-tested with the official MCP Python
client. Claude Code, Codex CLI, and Gemini CLI have not been driven through the
current recovery flow; their presence in configuration examples is not proof.

```toml
# Example Codex configuration — documented, not exercised as proof.
[mcp_servers.graphene]
command = "graphene-mcp"
args = []
```

The ordinary MCP default is `gemini-adk` and requires explicit success
criteria plus valid credentials. It never falls back to a fixture. For
credential-free development, select `driver="scripted-local"`; that path only
accepts its exact checked-in fixture and is always labelled simulated.
There is no silent fallback from a live request to replay or fake work.

## Authorization and recovery boundary

`policy_pre_authorized` is not established because a caller requested it.
Graphene first compiles the proposal, validates the exact plan against the
committed policy revision, and records a policy-authoritative decision. A plan
outside policy becomes `review_required`. MCP review approval is
`server_derived` relay evidence, not proof that a human signed in a chat client.

Live Gemini work is designed to run in a private length-framed child process
with no repository API. After the child durably acknowledges provider dispatch,
the owned-process registry can target that exact pid/process-group/start-time
identity. A killed child is a retryable `provider_interrupted` attempt whose
repository effect is known absent. This mechanism is locally tested; killing a
real Gemini child and completing the Orders mission has not yet been proven.

## The Orders hero target

[`demo/north_star`](demo/north_star) materializes a small Orders API migration:
replace Pydantic v1 compatibility APIs with native v2 APIs and freeze exact
dependency declarations while preserving immutable behavior. Its policy
allows only five named files, denies network access, caps concurrency at two,
and authorizes isolated auto-finalization. The target and policy are tested;
no credentialed current-tree mission has completed it.

## Installed-artifact check

```bash
python scripts/verify_installed_artifacts.py
```

The verifier builds an sdist, builds a wheel from that sdist, installs each
into a separate environment, clears Python source-path overrides, changes to a
directory outside the checkout, and checks entry points, replay, UI, MCP
initialization, legacy resource consumers, installed Orders materialization,
and no-key MCP start/disconnect/reattachment. The checked-in exact-SHA driver
adds a clean-tree, expected-revision, and canonical-remote-ref gate, then emits
a SHA-named manifest outside the checkout. Run-specific proof is intentionally
not committed into the tree it claims to prove. Pytest remains a development
dependency, not a runtime dependency.

## Proven vs. pending

| Path | Current truth |
|---|---|
| Replay and UI | `VERIFIED_LOCAL` fixture; no live execution |
| Detached supervisor and MCP reconnect | `VERIFIED_LOCAL` scripted fixture; not Codex and not Gemini |
| Policy authorization and isolated auto-finalization | `VERIFIED_LOCAL` contracts/fixture |
| Gemini child isolation and kill semantics | `VERIFIED_LOCAL` protocol/fake tests; real model kill not proven |
| Live Gemini Orders mission | `NOT PROVEN` on the current implementation |
| Wheel/sdist outside-tree execution | Verifier and clean/remote-bound exact-SHA gate implemented; a SHA-named external manifest or CI result is the run-specific proof |
| Codex, Google Cloud, Docker, benchmark, and film | `NOT PROVEN`; cloud not deployed |

The benchmark remains deferred: there is no token-efficiency claim, and no speed or cost comparison.

The runtime pins `google-adk==2.5.0` and requests `gemini-3.5-flash`. Those
identifiers were source-checked on 2026-08-27; eligibility and returned model
identity must be revalidated before any live proof claim.

[Proof boundaries](docs/PROOF.md) · [Command map](docs/COMMANDS.md) · [Runbook](docs/NORTH_STAR_RUNBOOK.md) · [Known limitations](docs/KNOWN_LIMITATIONS.md) · [License](LICENSE)
