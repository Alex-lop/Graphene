# Proposal: harness-agnostic tool-call observability — fit assessment

Status: proposal only, 2026-08-23. Nothing in this document is implemented, and nothing here changes any other document's truth label. This assesses one suggested new capability against what Graphene has already built and already decided, so the next unit of work is chosen deliberately instead of by enthusiasm.

## The ask, restated

A tool, independent of ponytail-style code-terseness plugins, that lets you see the tools being used by any agent harness of your choosing — the way a benchmark harness shows every call a model made during a task.

## Verdict

It fits the vision, because it is not a new capability. It is [Shadow Agent](SHADOW.md), which shipped v0 on 2026-08-22:

> "Your agent said the tests passed. Graphene knows whether they actually ran."

Shadow Agent already is "watch which tools a harness used, on a session you didn't run yourself." It ingests a finished transcript, reconstructs a typed graph of tool calls, edits, commands, and checks, and lints it for exactly the failure modes an unaudited "all tests pass" message hides (`claimed-without-evidence`, `edit-without-check`, `scope-drift`, `write-overlap`, `destructive-unverified`, `network-or-install`). The pipeline — observe → reconstruct → lint → report — is a CLI today: `graphene shadow ingest|report|lint|graph|export|verify`. This is not aspirational; the ndjson path is tested against a checked-in fixture.

The real question isn't "should this exist." You already answered that. The question is whether to build a second, separately branded version of it, or finish the one with a name, a spec, and tests already in this repo.

## Where the "any harness of your choosing" framing needs correcting

That phrasing implies building N bespoke per-harness adapters. Graphene already considered and rejected that shape. The [adapter specification](SHADOW_ADAPTER_SPEC.md) defines one open format, `shadow.event.v1` NDJSON, and the project's stated position is explicit:

> "Gemini CLI and Cursor reach Graphene through it rather than through bespoke adapters."

Only one harness gets a first-party parser at all: Claude Code, because it's the one whose transcripts live on disk in a proprietary shape Graphene has to translate. Every other harness is expected to emit the open format itself. Re-opening "any harness" as a design question would mean building a second integration surface next to one that already exists and is documented — that's not generalization, it's duplication, and it fragments the single evidence-backed story the truth-label doctrine depends on.

## The one gap that actually matches the ask

`docs/KNOWN_LIMITATIONS.md` already tracks this as the named, open item:

> "Shadow Agent — ndjson path verified on a synthetic fixture; the claude-code adapter is not implemented and fails closed; ingestion is never tamper-evident about its source → **What closes it:** A real Claude Code transcript, then the adapter and its scrubbed fixture."

`SHADOW.md` confirms the same thing at the implementation level: `graphene shadow ingest --format claude-code` fails closed today with `unsupported shadow format: claude-code`, pending a parser for `~/.claude/projects/<project>/<session>.jsonl` built against a real transcript.

That transcript format is sitting on this machine right now — this conversation is writing one. Building this adapter would let `graphene shadow ingest --format claude-code` point at the session that burned 30% of a weekly allowance and hand back, for free, everything the ndjson path already does: a reconstructed graph of every tool call and check, lint findings, and the three honest ratios (checked files with a passing check after, claims backed by evidence, write-overlap). That is a direct, evidence-backed answer to "where did the budget go" — not a guess about reasoning effort, an actual reconstruction.

## The tempting move that would be premature

Watching a harness live, instead of after the fact, is a real idea — but it's already named and deliberately deferred. It's the **Gate** rung of Shadow's own adoption ladder (Observe → Advise → Gate → Execute), and "live wrapping or interception of a running agent" is listed as an explicit v0 non-goal.

That deferral isn't scope-timidity, it's a harder problem than it looks: batch ingestion makes every provenance, redaction, and fail-closed decision once, over a complete file. Live watching has to make the same decisions per event, in real time, without ever letting an unredacted secret or an unvalidated inference through, and without the shadow store ever touching mission authority while a mission might be running concurrently. That deserves its own design pass — the way Shadow itself got a dated design-acceptance line before code landed — not a feature bolted onto whichever adapter ships first.

If and when it is tackled, Claude Code is the best first live target available, for a reason specific to this harness: it already exposes hooks (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, configured in `settings.json`) as a sanctioned, first-party event stream. That's a legitimate interception point, not a reverse-engineered wrapper — which matters, because a wrapper is exactly the kind of fragile, per-harness hack the ndjson spec exists to avoid.

## Recommendation

1. Do not start a new, separately branded tool. It would duplicate a spec, a CLI surface, and a redaction/provenance discipline that already exist and are tested.
2. Build the `claude-code` adapter next, scoped to what `KNOWN_LIMITATIONS.md` already says closes it:
   - Parse a real local transcript (`~/.claude/projects/<project>/<session>.jsonl`) into `shadow.event.v1` records.
   - Fail closed on any record shape the parser doesn't recognize, naming the record and field, per the standing doctrine.
   - Ship a scrubbed fixture derived from a real transcript, not a synthetic one.
   - Non-goals for this step: no live interception, no second ndjson dialect, no special-casing for any other harness.
3. Only after that adapter ships and earns its own truth-label flip, write a dated design doc for the Gate rung on Claude Code specifically, built on its hook system rather than process wrapping.

## Why this matters for the question that started this

The session that prompted this — "why did one prompt cost 30% of a weekly allowance" — is exactly the case Shadow Agent was built to answer, and exactly the harness it doesn't support yet. The honest move is to close that one named gap, not to open a second, broader, unspecified one next to it.
