# Demo script — one take, one command

> A change appears, Graphene wakes up, coordinates two real Gemini workers,
> survives a check failing, hands over a result that runs, and proves why it
> should be trusted.

Everything below was executed on 2026-08-23 on the commit that carries this
file. The captured transcript of the live run is
[`evidence/convergence/2026-08-23-demo-live/run-1.txt`](../evidence/convergence/2026-08-23-demo-live/run-1.txt);
the completion-gate numbers are in
[`evidence/convergence/2026-08-23-completion-gate/`](../evidence/convergence/2026-08-23-completion-gate/README.md).
No beat here is a rehearsal or a splice.

## Before you press record

One shell, one command block. Paste it whole — do **not** append trailing
`# comments` to a pasted line; interactive zsh does not treat `#` as a comment
start and `graphene` will reject the extra arguments.

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
export GOOGLE_CLOUD_LOCATION=global
export GRAPHENE_CHECK_EXECUTOR=host-sandbox
export GRAPHENE_STATE_DIR="$HOME/.graphene/demo-state"
mkdir -p -m 700 "$GRAPHENE_STATE_DIR"
```

`GOOGLE_CLOUD_LOCATION=global` is the only location serving `gemini-3.5-flash`
for this project; regional endpoints 404. Check the project is the funded one
before going further.

Cost: **$0.17 per run**, from evidence-bound receipts — roughly $0.07 planner
and $0.10 for the two workers. Three rehearsals plus a take is about $0.70.

## The take (about three minutes)

```bash
uv run --frozen graphene demo --live
```

That is the whole demo. It materializes its own target, drops its own trigger,
approves under a pre-authorized bounded policy, runs the mission while it
renders the dashboard, and finishes with the result, the feature, and `why`.
No second terminal, no `sed`, no hand-driven steps.

### What appears, and what to say over it

**0:00 — a change arrives.** The target is materialized and its own suite is
green; a `mission.yaml` lands in an inbox and a mission is proposed from it.

> "A change lands in a folder Graphene is watching. That drop is the first
> event in the record — `why` will start there."

**0:15 — a bounded plan you approve.** Four tasks printed as plain text: two
disjoint work tasks with their exact write scopes, a deterministic assembly,
and a verification tail.

> "The plan is typed and validated before anything runs. Each task's write
> scope is a lease — a worker that touches anything else is rejected, not
> warned. Assembly isn't a model's job here; it already ships in the target."

**0:30 — two real workers.** The dashboard shows both work tasks `● running` at
attempt 1, fence 1, and SPEND starts moving from real provider receipts.

> "Two real Gemini workers, in parallel, on disjoint files. The cost you see is
> read out of the provider's own receipts, not estimated."

**1:00 — the failure, and this is the line that matters.**
`↻ retrying`, and `Latest: check failed → retry authorized with diagnostic`.

> "One of the **check processes** fails — deterministically, on purpose. Not
> the model, not the network: Graphene's own check process, made to fail so you
> can watch what happens next."

**Never say "the Gemini worker died."** The failure is injected by
`--inject-check-fault` and stamped `simulated_fixture` in evidence. Saying
otherwise would be the one dishonest sentence in the demo.

**1:15 — the retry learns.** The task comes back at **attempt 2, fence 2**, and
its sibling stays `✓ accepted`, untouched.

> "The retry runs under a strictly higher fence — the old attempt can no longer
> write anything, even if it comes back. And it carries a redacted diagnostic:
> which checks failed, and why. Retrying without that is just rolling the dice
> twice. If the second attempt fails the same way, Graphene stops instead of
> buying a third."

**2:00 — the result is isolated.** `Result approved and isolated: commit … on
refs/graphene/results/…; nothing was pushed anywhere.`

> "The result is one commit on a private ref. Approving it required the store to
> rebuild the patch, the mutation manifest and the resulting tree from the
> repository and agree — the store checks its own caller."

**2:15 — the feature runs.** The generated Markdown report prints: a real
table, a note redacted to `[REDACTED]`, a pipe escaped inside a cell, an item
flagged below its reorder level.

> "And here is the thing it built, running. Not a hash that says it would work."

**2:30 — why.** `why` chains trigger → target → producer attempt →
**prior_attempts**, which names the failed attempt, its fence and its receipts →
assembly → verification → committed approval.

> "Every line comes from hash-chained events and evidence you can resolve.
> Where Graphene doesn't know, it says so. It never guesses."

## The two commands to show after the take

```bash
uv run --frozen graphene demo                       # free, replay-backed, no credentials
bash scripts/morning_verify.sh                      # release verification, spends nothing
```

`graphene demo` in its default mode contacts no provider and creates no
authoritative state — it prints its own truth counters (`Live agent executions:
0`, `Gemini calls: 0`). `morning_verify.sh` re-runs the locked environment, the
full credential-free matrix, ruff, the location-only secret scan, `store.verify`
on every mission, capsule cold verification from a fresh clone, and the proof
table, and only it may print `ALL PASS`.

## What this demo does not claim

- The check failure is injected by Graphene, not a real infrastructure failure.
  The night's SIGKILL laboratory is the real-process variant and is a separate,
  narrower claim.
- Nothing here involves Cloud Run or Firestore. There is no cloud claim in this
  script.
- 9/10 is this target, this contract test, this model, on one day. It is not a
  claim about any model's general ability.
- Approval is operator-delegated (`server_derived`), not human-attested; the
  pre-authorized bounded policy is what keeps the take continuous.
