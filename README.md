<p align="center">
  <img src="docs/assets/Graphene_main_img.png" alt="Graphene" width="720">
</p>

# Agents write. Graphene decides what survives.

**Repository publication control for parallel coding agents: bounded writes, exact candidates, traceable history.**

[![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml)

Graphene binds one approved plan revision to its base SHA and SHA-256 digest. Parallel workers may propose changes, but only scoped artifacts carrying the current fence can enter the exact candidate Graphene verifies; stale attempts cannot publish. `why` preserves traceable history, and policy-authorized finalization creates an isolated Git ref. Graphene never pushes, merges, deploys, or mutates the supplied checkout.

## Run the verified path

```bash
git clone https://github.com/Alex-lop/Graphene.git && cd Graphene
uv sync --frozen
uv run --frozen graphene mission replay taskmaster
```

> **VERIFIED MISSION REPLAY — GENERATED SCRIPTED FIXTURE; NO LIVE AGENT, HUMAN ATTESTATION, NEW TEST EXECUTION, GEMINI, OR CLOUD**

The replay is SHA-256 checked, read-only, and credential-free. Open the same mission once in the terminal UI:

```bash
uv run --frozen graphene ui --replay taskmaster --once
```

![Graphene terminal UI showing a signed plan, retry evidence, and lineage](docs/assets/ui-terminal.png)

## Where Graphene fits

Use the agent runtime you already trust. Graphene governs the repository handoff after agents propose changes.

| Project | Primary job | Control boundary | Where Graphene fits |
|---|---|---|---|
| **Graphene** | Repository publication control | Approved plan → scoped attempts → accepted artifacts → exact verified candidate | The SHA-256-bound decision layer, with fences and traceable history |
| [Graft](https://github.com/trailhq/Graft) | Current codebase context and blast-radius mapping | Keeps a local repository map available to coding agents | Use Graft to understand the code; Graphene to govern the candidate result |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Durable, stateful agent orchestration | Defines, runs, pauses, and resumes the workflow | Keep LangGraph as the runtime; add Graphene where work becomes repository artifacts |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Agent and multi-agent workflows | Coordinates agents and functions with checkpoints and human input | Keep Agent Framework as the runtime; add Graphene for repository admission and exact-candidate verification |

These are complementary layers. See the [primary-source comparison notes](docs/reports/2026-08-28-readme-comparison-research.md).

## Connect a controller

The committed [`.mcp.json`](.mcp.json) launches the source server; installed packages expose `graphene-mcp` over stdio. Call `start_goal`, read `get_digest`, relay it through `approve_plan`, poll `mission_status`, then inspect `why` and `graphene mission result show`.

The live `gemini-adk` path requires explicit success criteria and credentials; there is no silent fallback to a fixture. See the [nine-tool command map](docs/COMMANDS.md) for setup and the full loop.

## Proven / waiting

| Status | Evidence boundary |
|---|---|
| `VERIFIED_LOCAL` — replay and terminal UI | SHA-256-checked generated fixture; no live agent or new test run |
| `VERIFIED_LOCAL` — scheduler, policy, recovery, and exact candidate | Scripted/fake local coverage, including isolated auto-finalization |
| `VERIFIED_LOCAL` — MCP and reconnect | Official Python MCP client plus scripted controller flow; approval is `server_derived` relay evidence, not human attestation; no Codex, Claude Code, or Gemini CLI run |
| `NOT PROVEN` — live execution | Current credentialed Gemini Orders mission, real model kill/recovery, and Codex controller |
| `NOT PROVEN` — external proof | Exact-SHA proof needs a SHA-named external manifest or CI result; cloud is not deployed; Docker, benchmark, and film remain unproven |

The benchmark remains deferred: there is no token-efficiency claim, and no speed or cost comparison. See [Proof boundaries](docs/PROOF.md) for the full evidence ledger.

## Read deeper

[Documentation](docs/README.md) · [Command map](docs/COMMANDS.md) · [Product contract](docs/PRODUCT.md) · [Known limitations](docs/KNOWN_LIMITATIONS.md) · [Machine-readable truth](contracts/product_proof.json) · [License](LICENSE)
