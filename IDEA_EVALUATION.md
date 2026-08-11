# Idea Evaluation — Provenance-First Collaborative Agent

Evaluation date: August 10, 2026.

## Verdict

The pain is real. The first framing is not differentiated enough.

| Framing | Honest score | Why |
|---|---:|---|
| “A graph of everything an agent did” | **4/10** | Useful, but established observability products already trace tool calls, agents, and execution graphs. It sounds like a feature. |
| “Git blame for autonomous work” | **8/10** | A user can trace a claim, decision, or artifact to evidence, tools, agent handoffs, versions, and approvals—and repair only the affected work. |
| Horizontal observability startup | **5/10** | Crowded market, high integration burden, expensive trace storage, and difficult differentiation. |
| Provenance product for one high-stakes workflow | **8/10** | A narrow buyer and consequence make lineage operational rather than decorative. |

**Recommendation:** pursue it for the hackathon, but do not pitch “a prettier trace graph.” Build a collaborative agent that uses provenance to explain its work, ask for approval, flag unsupported outputs, and selectively repair downstream work.

## The sharper pitch

> A source-control graph for long-running agent work: click any claim, file, or decision to see the evidence, tool calls, agent handoffs, versions, and approvals that produced it; when evidence fails, the agent marks the affected work and asks before repairing only that branch.

This promises observable provenance, not private chain-of-thought or “everything the model thought.”

## Track decision

The rules require one track, even if the product borrows ideas from all three.

| Track | Fit | Decision rule |
|---|---|---|
| **Collaborative Partner** | Best after the reframe | Choose this when the agent asks clarifying questions, remembers preferences and feedback, guides review, and uses lineage to adapt future work. |
| Fortified Enterprise Fleet | Natural fit for the raw graph idea | Choose this only if the core product is organization-wide agent discovery, observability, governance, identity, and multi-agent operations. That scope is much larger. |
| Taskmaster | Secondary | Choose this only if the graph supports one autonomous workflow and collaboration/memory are not central. |

**Recommended submission:** Collaborative Partner. Make the graph the agent’s shared memory and steering surface, not the product’s only feature.

Brutal caveat: if the finished demo is mainly traces, dashboards, or fleet administration, it belongs in Fortified Enterprise Fleet. Do not force the Collaborative Partner label onto a passive observability tool.

## Why the plain graph is not enough

- [Langfuse Agent Graphs](https://langfuse.com/docs/observability/features/agent-graphs) already offers aggregated and exact-execution graph views.
- [LangSmith](https://docs.langchain.com/langsmith/view-traces) exposes threads, model interactions, tools, failures, and nested subagents.
- [MLflow](https://mlflow.org/docs/latest/genai/tracing/integrations) offers automatic tracing across many agent frameworks, including Google ADK and long-running coding agents.
- [Google Cloud](https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-overview) already accepts OpenTelemetry-compatible agent traces and can collect prompts and responses.

Those tools mostly answer **“what ran?”** The opportunity is to answer:

- Why does this exact output exist?
- Which evidence supports or contradicts it?
- Which agent or human accepted responsibility?
- What changed between artifact versions?
- What downstream work becomes suspect when a source, tool result, or approval is invalidated?
- Can the agent repair that blast radius without rerunning everything?

Use [W3C PROV-O](https://www.w3.org/TR/prov-o/) as inspiration for the minimum provenance vocabulary rather than inventing a grand ontology.

## Best hackathon workflow

Use one long-running research-to-decision workflow because sources, claims, revisions, and approvals are easy for judges to see.

1. The user asks for a decision brief and gives constraints.
2. The agent asks one or two material clarifying questions.
3. A coordinator delegates research and verification.
4. Observable events update a live, collapsed lineage view.
5. The final Markdown brief contains claim-level provenance links.
6. A stale or contradictory source makes one claim and its recommendation suspect.
7. The agent explains the blast radius and requests approval.
8. It reruns only the affected branch, creates a new artifact version, and remembers the user’s review preference.

Preload a realistic longer history, then run one short repair live. A truly long-running stage demo is unnecessary risk.

## Minimum product

### Nodes

- Goal
- Task
- Agent
- Source
- Tool call
- Claim
- Artifact version
- Human decision

### Edges

- spawned
- used
- produced
- supports
- contradicts
- revised
- approved

### Views

1. Collapsed run summary.
2. An output-first view: “Why is this claim or file here?”
3. A small live activity timeline.

### Recommended stack

- Gemini 3.5+ for planning, synthesis, verification, and explanations.
- Google ADK for orchestration.
- Cloud Run for the backend.
- Firestore for append-only events, persistent state, nodes, and edges.
- Existing ADK/OpenTelemetry events for low-level execution; record only the semantic claim, artifact, approval, and invalidation edges that ordinary traces lack.

A graph database is unnecessary for this demo. Store events and explicit edges in Firestore and derive the displayed graph.

## Acceptance test

The demo is ready only if it proves all eight:

1. A user gives a meaningful goal.
2. The agent asks a useful clarifying question.
3. It completes at least three observable autonomous steps.
4. Instrumented events create the graph; an LLM does not reconstruct history after the fact.
5. A final claim or artifact traces to its source, tool call, agent, and approval.
6. Feedback on one node changes a later action.
7. State survives a restart or later session.
8. One failed or invalidated step is visible and safely resumed, retried, or selectively repaired.

## Likely judge score

Directional estimate before bonus points:

| Criterion | Weight | Passive graph | Refined agent |
|---|---:|---:|---:|
| Innovation and Operational Utility | 40% | 2/5 | 4.5/5 |
| Architectural Discipline and Tech Stack | 30% | 3/5 | 4/5 |
| Demo and Production Readiness | 30% | 3/5 | 4.5/5 |
| **Weighted result** | **100%** | **2.6/5** | **4.35/5** |

The difference is not visual polish. It is whether lineage causes useful action.

## Biggest risks

1. **“This is Langfuse with another graph.”** Start from a final claim or artifact and walk backward through explicit evidence, versions, and approvals. Then show targeted repair.
2. **Passive observability.** The agent must act on the graph: explain progress, request approval, flag unsupported work, or repair an affected branch.
3. **False causality.** Timing and parent-child spans do not prove that a source supports a claim. Record semantic edges explicitly and distinguish `observed-before` from `supports` or `derived-from`.
4. **Graph hairballs.** Default to a collapsed summary and output-first questions. Never open on every raw event.
5. **Sensitive-data leakage.** Redact secrets and personal data before persistence. Provide a clear mode that records metadata without prompt, response, or source contents.
6. **Hidden-reasoning overclaim.** Do not market chain-of-thought capture. Show actions, tool results, stated decisions, citations, artifact derivations, and human approvals.
7. **Stage failure.** Preload the long history and live-run only a short, reliable branch repair.
8. **Track ambiguity.** Ensure clarifying questions, persistent feedback, and adaptation are visible if submitting to Collaborative Partner.

## Three venture wedges

| Wedge | Strength | Weakness |
|---|---|---|
| Research and decision evidence | Fastest, clearest hackathon demo; claim lineage is intuitive. | Lower willingness to pay unless decisions are consequential. |
| Coding-agent change provenance | Directly matches the stated personal pain; file changes and approvals are concrete. | Developer-agent observability is already crowded. |
| Regulated evidence and approval trails | Strongest potential buyer need in compliance, finance, healthcare, or legal operations. | Slow sales, sensitive data, and domain expertise are unavoidable. |

Build the research workflow for the hackathon. Afterward, interview five heavy users of long-running coding or research agents before choosing the commercial wedge. Do not build multi-framework ingestion until those interviews identify a buyer and a must-have workflow.

## Cut list

- Support for every agent framework.
- A custom graph database or ontology service.
- Deterministic replay of arbitrary agents.
- Full enterprise RBAC, agent registry, marketplace, or multi-tenancy.
- Real-time multi-user editing.
- Storage of “every event forever.”
- Private chain-of-thought capture.
- Autonomous prompt rewriting.
- Extra Google models added only for bonus points.
- A generic chatbot beside the graph.

Choose the project name yourself. The hackathon FAQ explicitly warns that generic AI-generated names blend together.

## Decision

**Go**, with this boundary: ship an output-first, provenance-native Collaborative Partner for one workflow. If the build becomes a general trace viewer or enterprise fleet platform, cut scope or change tracks—do not submit a vague combination of all three.

## Sources

- [Hackathon overview and current track definitions](https://allthingsagentichackathon.devpost.com/)
- [Official Rules and judging criteria](https://allthingsagentichackathon.devpost.com/rules)
- [Hackathon resources and track deep-dives](https://allthingsagentichackathon.devpost.com/resources)
- [Hackathon FAQ](https://allthingsagentichackathon.devpost.com/details/faqs)
- [Langfuse Agent Graphs](https://langfuse.com/docs/observability/features/agent-graphs)
- [LangSmith trace views](https://docs.langchain.com/langsmith/view-traces)
- [MLflow tracing integrations](https://mlflow.org/docs/latest/genai/tracing/integrations)
- [Google Cloud agent instrumentation](https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-overview)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
