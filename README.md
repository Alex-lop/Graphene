<p align="center">
  <img src="docs/assets/Graphene_main_img.png" alt="Graphene" width="720">
</p>

# Agents write. Graphene decides what survives.

**Repository publication control for parallel coding agents.**

[![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml)

## After a coding worker fails, which repository changes are safe to keep?

Within one fixed plan revision, Graphene keeps only artifacts admitted under declared scopes and monotonically increasing fences. Accepted sibling artifacts remain immutable; failed or stale attempts cannot publish. Assembly consumes accepted artifacts only, verification binds the exact candidate, policy-authorized finalization creates an isolated Git ref, and `why` reconstructs causality. Graphene never pushes, merges, deploys, or mutates the supplied checkout.

## Why not just LangGraph?

LangGraph checkpoints workflow state, retries nodes, and preserves successful
parallel writes.

Graphene governs a different boundary: repository publication.

Each coding attempt is bound to a base SHA, declared write scope, attempt
identity, and current fencing token. Workers may propose patches, but they
cannot publish them. Graphene admits eligible artifacts, refuses superseded
attempts, assembles accepted artifacts only, verifies the exact candidate
tree, and publishes that same tree to an isolated Git ref.

Graphene does not replace LangGraph. A LangGraph controller may invoke
Graphene.

Use LangGraph to decide what runs next. Use Graphene to decide which bytes
may ship.

Here, “ship” means admission into Graphene's verified isolated result ref. It
does not mean pushing, merging, or deploying a user repository.

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

`graphene-mcp` serves the durable goal, decision, status, summary, and `why`
surface over stdio; the full nine-tool schema is in the [command map](docs/COMMANDS.md).
`start_goal` returns after durable acceptance, and a detached supervisor lets a
later MCP process reattach. `why` reconstructs through candidate approval;
compose it with `graphene mission result show` to bind the isolated result
receipt and ref.

The committed [`.mcp.json`](.mcp.json) launches the source; an installed artifact
launches `graphene-mcp`. Python fixtures test protocol and disconnect behavior.
Live Codex and Gemini MCP proof remains `NOT PROVEN`.

```toml
# Example Codex configuration — documented, not exercised as proof.
[mcp_servers.graphene]
command = "graphene-mcp"
args = []
```

The `gemini-adk` default requires explicit criteria and credentials; there is no silent fallback
to a fixture. `driver="scripted-local"` accepts only its credential-free fixture.

## Authorization and recovery boundary

`policy_pre_authorized` is a request, not authority. Graphene validates the
compiled plan against committed policy and records the decision. Anything
outside policy becomes `review_required`; MCP approval is `server_derived`
relay evidence, not authenticated human attestation.

Live Gemini work runs in a private framed child with no repository API. After a
durable dispatch barrier, Graphene can target its exact process identity. A
killed child is retryable `provider_interrupted` work with known-absent
repository effect. This is locally tested; a real Gemini kill is not proven.

## The Orders hero target

[`demo/north_star`](demo/north_star) materializes a Pydantic v2 Orders migration.
Policy allows five files, no network, two workers, and isolated auto-finalization.
The target is tested; no current credentialed mission has completed it.

## Installed-artifact check

```bash
python scripts/verify_installed_artifacts.py
```

The verifier installs wheel and sdist separately outside the checkout and checks
entry points, replay, UI, Orders materialization, and MCP reattachment. The
exact-SHA driver adds clean-tree and remote-revision gates, then writes the
SHA-named proof manifest outside the checkout.

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
