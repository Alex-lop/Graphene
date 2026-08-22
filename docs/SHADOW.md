# Shadow Agent

> **"Your agent said the tests passed. Graphene knows whether they actually ran."**

Status: v0 design accepted 2026-08-22. The implementation lands in the commits that follow this document; the README proof table and [`contracts/product_proof.json`](../contracts/product_proof.json) flip to a verified label only in the same change as the tests that earn it. Until then the Shadow Agent is **NOT PROVEN**.

## Who it is for

A two-to-eight-person team that already runs Claude Code, Gemini CLI, or Cursor every day. They will not adopt a new orchestrator on day one; switching costs are real, and their agent was never trained on anyone's orchestrator anyway. What they feel acutely is different: an agent session produces hundreds of tool calls, a wall of edits, and a cheerful "All tests pass", and nobody on the team can efficiently audit whether that sentence is true. Code review of agent output is the new bottleneck, and today it is done by vibes.

## What it is

The Shadow Agent is **code review for agent sessions**. Point Graphene at a session transcript the agent already produced. Graphene reconstructs the work as a typed graph (inferred tasks, files touched, commands run, checks executed) and lints the session for the exact failure modes that Graphene's governed mission mode makes impossible: claims with no check behind them, edits no check ever covered, overlapping writes, scope drift, unverified deletes, and unreviewed network or install activity.

```text
transcript ──ingest──▶ shadow.event.v1 stream ──reconstruct──▶ segments + paths + DAG
                                                                       │
                                                             lint ──▶ findings + ratios
                                                                       │
                                                         report / graph / export capsule
```

The pipeline is observe → reconstruct → lint → report. Nothing in it talks to a model, changes the agent, or adds latency to the session.

## Why it wins adoption

Zero behavior change. The model does not need to be trained on Graphene; the developer does not need to change tools; the session is not slowed down. It is pure downside-free observability, and it is the first rung of an explicit adoption ladder:

| Rung | What Graphene does | Status |
|---|---|---|
| **Observe** | Ingest a finished session and reconstruct the typed graph | v0 ships this |
| **Advise** | Lint the reconstruction and report findings with evidence references | v0 ships this |
| **Gate** | Apply policy to a live session before an effect lands | Future work |
| **Execute** | Run the work under leases, fences, trusted checks, and exact verification | The governed Taskmaster mission in this repository |

The ladder is drawn so users can see where the road goes. v0 is deliberately the bottom two rungs.

## Why it is honest

A shadow graph is a **reconstruction**, and Graphene's culture demands the label. Every shadow record carries a provenance class:

- `observed`: the event is literally present in the transcript (a tool call, a tool result, a message).
- `inferred`: the record is a product of a heuristic (a task boundary, an extracted claim, a file edit parsed out of a shell command, a coverage mapping, a dependency edge).

The report never presents inference as evidence. Inferred records say so, and the findings that depend on them say so. This discipline is itself the feature: it is exactly what harness vendors publishing token-efficiency curves do not do.

## Source trust caveat

Shadow ingestion is **not** tamper-evident about its source. A transcript is only as trustworthy as the program that wrote it, and an agent harness can omit, reorder, or invent records. Graphene content-addresses every normalized event and records the digest of the source file, so two people holding the same transcript will get the same shadow ID and the same report; Graphene cannot tell you whether the transcript is a faithful record of what the agent did. That guarantee belongs to the governed mission mode, where Graphene itself is the author of the evidence.

## Observation and authority do not mix

Shadow data lives in its own SQLite file, `shadow.sqlite3`, beside the mission store under the Graphene state directory, with its own `PRAGMA user_version`, its own schema ledger, and the same fail-closed behavior on an unknown or altered schema. **Shadow reconstructions are never written into the authoritative mission store, and nothing in the mission trust chain may ever cite a shadow record as evidence.** A `graphene why`, a `FinalResultBundleV2`, or a trusted check attestation will never reference a shadow event. Observation is a lens on someone else's work; authority is Graphene's own record of work it governed.

## What v0 ships

```bash
graphene shadow ingest PATH --format claude-code|ndjson [--repo PATH]   # -> SHADOW_ID
graphene shadow report SHADOW_ID [--json]
graphene shadow lint   SHADOW_ID [--rule RULE ...] [--json]
graphene shadow graph  SHADOW_ID --json|--dot
graphene shadow export SHADOW_ID --output DIR                           # -> redacted .graphene-shadow capsule
```

Two adapters, exactly:

- `claude-code` parses a local Claude Code session transcript (the JSONL file under `~/.claude/projects/<project>/<session>.jsonl`). It was written against real session files produced on the maintainer's machine and is versioned against the observed record shapes. An unrecognized structure fails closed with an error that names the record and the field that did not match.
- `ndjson` is the documented open format in [the adapter specification](SHADOW_ADAPTER_SPEC.md). Any agent, wrapper, or CI harness can emit `shadow.event.v1` records directly. The specification is the integration surface; Gemini CLI and Cursor reach Graphene through it rather than through bespoke adapters.

The normalized schema is `shadow.event.v1`. Redaction happens at ingest, not at export: hidden reasoning is never ingested, command text is reduced to a digest plus a bounded redacted excerpt, file contents are never stored, and secrets matched by the redaction patterns are replaced before anything is persisted.

## Trust Lint v0

Six named rules. Each finding carries a rule ID, a severity, one human sentence, and the event IDs it references.

| Rule | Fires when | Severity |
|---|---|---|
| `claimed-without-evidence` | A success claim has no observed check run with exit code 0 after the last edit that precedes the claim | high |
| `edit-without-check` | A file was edited and no observed check ran afterwards before the session ended | warn |
| `write-overlap` | The same path was edited from different inferred segments in interleaved order | warn |
| `scope-drift` | A write landed outside the repository, or on a sensitive path (`.env*`, secret-like names, CI configuration, lockfiles) | high |
| `destructive-unverified` | A delete or rename had no observed check after it | warn |
| `network-or-install` | An `install_op` or `network_op` was observed (surfaced, not judged) | info |

There is **no composite trust score** in v0. A single opaque number is exactly the fake-precision marketing this project exists to oppose. The report leads with three honest ratios, each defined in one line of the report itself:

- changed files with a subsequent observed passing check: `M / N`
- success claims backed by observed check evidence: `J / K`
- inferred segments with write-overlap conflicts: `C / S`

Coverage is coarse in v0. The heuristic is "an observed passing check ran after the file's last edit"; the report footer says exactly that. Coarse and stated beats precise and imagined.

The governed-run diff is qualitative and static. Each high-severity finding maps to one sentence of the form "Under Graphene's governed mode, this claim would have required a trusted output-bound check attestation and could not have reached DONE." No numeric estimate of tokens, time, or cost is fabricated.

## Claim extraction

A conservative, versioned matcher (`claims.v1`) scans agent messages for success assertions ("tests pass", "all green", "verified", "fixed", "build succeeds", and close variants) and emits `kind=claim` events with `provenance=inferred`. Precision is preferred over recall: hedged, negated, conditional, and question forms are excluded, and text inside code fences is ignored. A missed claim is a shrug; a hallucinated claim in a trust report is a scandal.

## Graph reconstruction

From the normalized stream Graphene reconstructs inferred task segments (boundaries at human prompts, long gaps, and explicit plan or task-list markers), the set of paths each segment touched, the command and check timeline, and a DAG of segment dependencies inferred from read-after-write on paths. Every node and edge carries `provenance=inferred` unless it is a direct event. `graphene shadow graph` exports the reconstruction as JSON or Graphviz DOT.

## v0 non-goals

- Live wrapping or interception of a running agent.
- Gemini CLI or Cursor adapters; the ndjson specification is their path.
- Any claim that ingestion is tamper-evident about the source transcript.
- A trust score, a token or cost estimate, or any numeric "governed run would have saved X" figure.
- Semantic understanding of what an edit does; coverage is by path and order only.
- Writing anything into the mission store, or citing a shadow record from mission evidence.

## Relationship to the thesis

Every other harness ships a graph that implies the agent got better. Graphene's graphs are instruments of verification and provenance: a reconstruction of behavior that already occurred, with every edge either backed by an observed event or labeled as inference. The governed mission proves work Graphene ran; the Shadow Agent audits work Graphene did not run. Both answer the same question: what actually happened, what was verified versus merely claimed, and why the result deserves trust.
