# README comparison research — 2026-08-28

## Recommendation

Replace “Why not just LangGraph?” with a small **Where Graphene fits** table.
Use four rows total: Graphene, Graft, LangGraph, and Microsoft Agent Framework.
They cover three distinct layers without turning the README into a framework
catalog:

- **Graft** gives a coding agent a current map of the repository.
- **LangGraph** and **Microsoft Agent Framework** define and run agent workflows.
- **Graphene** controls which scoped repository artifacts enter an exact,
  verified candidate result and records why.

This is a complementary comparison, not a leaderboard. Do not say another
project “has no approvals,” “has no provenance,” or “cannot” enforce a boundary
unless its first-party contract says so. State each project’s documented primary
job, then state the repository-specific contract Graphene adds.

## Which Graft?

The intended project is the former **NanoNets/Graft**, now **TrailHQ/Graft**.
Graphene’s own historical report says its Graft comparison and figures were
attributed to NanoNets, which distinguishes it from unrelated repositories with
the same name ([Graphene contract report](2026-08-24-contract-report.md#contract-report--2026-08-24)).
The old [`NanoNets/Graft`](https://github.com/NanoNets/Graft) URL now redirects
to the current [`trailhq/Graft`](https://github.com/trailhq/Graft) repository;
the package name remains `@nanonets/graft` in its official setup instructions
([Graft README](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L250-L260)).

This Graft is a useful comparison because it is adjacent, not because it does
the same job. It builds linked Markdown/code-graph context from repository
sources, tracks those sources by content hash, exposes search and blast-radius
tools, and refreshes answers against the current worktree, including uncommitted
edits ([nodes and source hashes](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L218-L236),
[MCP tools](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L288-L307),
[worktree refresh](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L309-L327)).
Graphene instead binds planned and accepted work to repository identities and an
exact candidate result ([Graphene product contract](../PRODUCT.md#product-loop),
[Graphene architecture](../ARCHITECTURE.md#runtime-boundaries)).

## Evidence matrix

| Project | Primary job | Who defines and runs the workflow? | Human control / binding described by first-party sources | Provenance or explanation surface | How Graphene complements it |
|---|---|---|---|---|---|
| **Graphene** | Repository publication control for parallel coding work: scoped attempts, accepted-only assembly, exact verification, and an isolated result ([README](../../README.md#agents-write-graphene-decides-what-survives), [product contract](../PRODUCT.md#product-loop)). | Graphene compiles and validates the mission plan; its durable scheduler dispatches ready, non-conflicting work under leases and fences, then assembles and verifies the candidate ([product contract](../PRODUCT.md#product-loop)). | Plan approval binds a revision and digest; the final decision binds an immutable `FinalResultBundleV2` ID ([proof contract](../PROOF.md#current-table), [product contract](../PRODUCT.md#supported-scope)). The implementation names the canonical plan digest `plan_sha256`; retain the concise “SHA-256-bound plan” wording ([contract report index](README.md#session-reports)). | Hash-chained events and `graphene why` reconstruct accepted producers, attempts, fences, checks, assembly, and approval; the isolated-result receipt is shown separately ([architecture](../ARCHITECTURE.md#local-store), [Taskmaster contract](../TASKMASTER_PRODUCT_CONTRACT.md#evidence-and-queries)). | This is the repository-specific control layer being compared. Keep its `VERIFIED_LOCAL` and `NOT PROVEN` labels adjacent to the claims ([proof contract](../PROOF.md#current-table)). |
| **Graft** | A local code-context layer: linked repository nodes, source hashes, repository maps, search, call tracing, and blast radius ([node format](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L218-L236), [MCP tools](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L288-L307)). | The coding-agent host performs the work; Graft wires context, MCP tools, and optional hooks into that host and keeps the map fresh ([agent integration](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L250-L290), [Claude Code integration](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L309-L327)). | Its README emphasizes explicit integration selection and dry-run setup; in noninteractive environments `init` writes nothing unless the selection is explicit ([setup controls](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L250-L274)). Source content hashes bind context nodes to the code used to build them ([node sources](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L218-L236)). | Its map explains repository structure, call relationships, hotspots, freshness, and change blast radius ([MCP tools](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L288-L307), [CLI](https://github.com/trailhq/Graft/blob/afb2553097f1514f2e7f555bc6981f2bd2c60d0e/README.md#L331-L380)). | Graft can help an agent understand what to change; Graphene can bind the resulting work to an approved plan, admit only eligible artifacts, verify the exact candidate, and preserve a causal decision history. |
| **LangGraph** | Low-level orchestration for long-running, stateful agents, including durable execution, human-in-the-loop state inspection/modification, memory, tracing, and deployment ([official README](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/README.md#L24-L43)). | The application author defines nodes and edges with the Graph API or control flow with the Functional API; LangGraph compiles and runs that workflow ([official quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart)). | Its documented human-control unit is persisted agent/workflow state: execution can pause, a person can inspect or modify state, and the run can resume ([official README](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/README.md#L35-L43)). | LangSmith is the documented debugging surface for execution paths, state transitions, and runtime metrics ([official README](https://github.com/langchain-ai/langgraph/blob/11ee185999b86bfea2d8c0e69cef9a5e37acf686/README.md#L35-L46)). | LangGraph can decide and durably resume what runs next; Graphene can wrap coding work in commit-, plan-digest-, scope-, artifact-, and candidate-bound repository decisions. |
| **Microsoft Agent Framework** | Production-grade agents and multi-agent workflows with graph patterns, checkpointing, streaming, human-in-the-loop control, and observability ([official README](https://github.com/microsoft/agent-framework/blob/edfe115ea06bca57ae5a123d0fac5b3fdda13603/README.md#L12-L14), [features](https://github.com/microsoft/agent-framework/blob/edfe115ea06bca57ae5a123d0fac5b3fdda13603/README.md#L31-L55)). | The application author defines functional or graph workflows; the framework connects agents and functions through explicit execution paths and coordinates their execution ([Microsoft Learn overview](https://learn.microsoft.com/en-us/agent-framework/overview/), [workflow concepts](https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/)). | Workflows support external request/response gates and approval-required tool calls; checkpoints retain pending requests so the workflow can restore and resume ([HITL](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop), [checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)). | Its documented observability surface is workflow/executor events and OpenTelemetry-based distributed tracing ([workflow concepts](https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/), [official README](https://github.com/microsoft/agent-framework/blob/edfe115ea06bca57ae5a123d0fac5b3fdda13603/README.md#L50-L55)). | Agent Framework can run the multi-agent workflow; Graphene can add the repository-specific admission, fencing, exact-candidate verification, and causal `why` contract around coding outputs. |

### Why Microsoft Agent Framework, not AutoGen

AutoGen remains relevant historically, but its official repository now says it
is in maintenance mode and directs new projects to Microsoft Agent Framework as
its supported successor ([AutoGen README](https://github.com/microsoft/autogen/blob/027ecf0a379bcc1d09956d46d12d44a3ad9cee14/README.md#L175-L202)).
Using both rows would add density without adding a new comparison boundary.

## README-ready comparison

The evidence above can be reduced to this table without flattening the products
into a feature checklist:

| Project | Primary job | Control boundary | Where Graphene fits |
|---|---|---|---|
| **Graphene** | Repository publication control for parallel coding agents | Approved plan → scoped attempts → accepted artifacts → exact verified candidate | The commit-bound decision layer, with SHA-256 plan binding, fences, and traceable history |
| **Graft** | Current codebase context and blast-radius mapping | Keeps a local repository map available to the coding agent | Use Graft to understand the code; Graphene to govern the candidate result |
| **LangGraph** | Durable stateful agent orchestration | Defines, runs, pauses, and resumes the workflow | Keep LangGraph as the runtime; add Graphene where work becomes repository artifacts |
| **Microsoft Agent Framework** | Production multi-agent applications and workflows | Coordinates agents/functions with checkpoints, HITL, and observability | Keep Agent Framework as the runtime; add Graphene for repository admission and exact-candidate verification |

Immediately below the table, one sentence is enough:

> Graphene complements agent runtimes and context layers; it governs which
> candidate result is authorized and verified. Push, merge, and deploy remain
> with you.

That last qualification matters because Graphene’s current contract says it
does not push, merge, deploy, or mutate the supplied checkout
([README](../../README.md#agents-write-graphene-decides-what-survives)).

## Copy and density guidance

- Prefer **“traceable history,” “accepted-only assembly,” “exact candidate,”
  “stale-attempt refusal,”** and **“commit-bound control”**. Each phrase names a
  concrete mechanism already represented in Graphene’s contracts
  ([architecture](../ARCHITECTURE.md), [proof contract](../PROOF.md)).
- Keep the SHA-256 point to one clause. The README needs the consequence—an
  approval cannot silently slide to a different plan—not the canonicalization
  algorithm.
- Keep the terminal image and the compact proven/pending table. Both make the
  product and its truth boundary legible without moving implementation detail
  back into the README.
- Omit competitor benchmark numbers. Graft’s numbers are maintainer-reported
  and answer a context-efficiency question, while Graphene’s benchmark remains
  explicitly deferred; placing them together would imply a comparison the
  repository has not run ([Graphene proof contract](../PROOF.md#current-table)).

## Source snapshot

External repository claims were checked against these first-party revisions on
2026-08-28:

- TrailHQ/Graft: `afb2553097f1514f2e7f555bc6981f2bd2c60d0e`
- LangGraph: `11ee185999b86bfea2d8c0e69cef9a5e37acf686`
- Microsoft Agent Framework: `edfe115ea06bca57ae5a123d0fac5b3fdda13603`
- AutoGen: `027ecf0a379bcc1d09956d46d12d44a3ad9cee14`
