# Demo script — one take, one command

> A change appears, Graphene proposes a route, **you change the route**, the
> new revision is linted and diffed and approved on its own digest, and then
> two real Gemini workers follow the graph you approved — surviving a check
> failing, handing over a result that runs, and proving why it should be
> trusted.

The edit beat is the point of the film. Everything a judge needs is in one
moment: they watch the graph change, they watch a new digest appear, and then
they watch the workers obey the changed route.

Everything below was executed live. The sequence including the edit beat ran
four times on 2026-08-24 on the commit that carries this file — three
consecutive clean rehearsals captured in
[`evidence/contract/2026-08-24-rehearsals/`](../evidence/contract/2026-08-24-rehearsals/README.md),
plus one timed run — and three more times on 2026-08-25 through the interactive
edit prompt itself, driven by a scripted operator
([`evidence/contract/2026-08-25-rehearsals/`](../evidence/contract/2026-08-25-rehearsals/README.md)).
No beat here is a splice. The captured transcript of the live run is
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

Cost: **$0.09–$0.12 per run** on 2026-08-24, from evidence-bound receipts
across four runs. Three rehearsals plus a take is under $0.50.

**Timing, measured rather than estimated.** One full run, timed end to end with
the edit applied by a script: **77 seconds**, of which the mission itself —
approval to `awaiting_result` — was 47 seconds. That leaves roughly 30 seconds
for everything around it: materializing the target, the inbox trigger, the plan
table, one node's full contract, revise/lint/diff, the result, the generated
feature, and `why`. The one variable is you: on camera the scripted edit is
replaced by however long you take to type one, and the budget for that inside
§9's two minutes is about 40 seconds. Rehearse the edit itself, not just the
command.

Beat by beat — the exact frames, which of those timings a machine measured and
which a person did, and what each beat is and is not proof of — is in
[`docs/SHOT_LIST.md`](SHOT_LIST.md).

## The take (measured: 1:17 with a scripted edit)

```bash
uv run --frozen graphene demo --live
```

That is the whole demo. It materializes its own target, drops its own trigger,
shows the proposed plan and one node's full contract, **stops once for your
edit**, compiles it into revision 2, lints and diffs it, approves the new
digest under a pre-authorized bounded policy, runs the mission while it renders
the dashboard, and finishes with the result, the feature, and `why`. One
terminal, one pause, no `sed`, no hand-driven steps.

For a rehearsal that does not wait on a person, hand it a command that makes
the edit. The command is run as `COMMAND <exported-plan>`, so it transforms the
plan the live planner actually returned — which is the only thing that can
work, because that plan is not known until the run is underway. Everything
after the edit is the same code the filmed take runs:

```bash
uv run --frozen graphene demo --live \
  --plan-edit "uv run --frozen python scripts/demo_plan_edit.py"
```

`scripts/demo_plan_edit.py` gives one worker read access to the file another
worker owns — a scope expansion, which is exactly what `plan diff` is built to
make impossible to miss. If the command leaves the plan unchanged, or exits
non-zero, the demo stops rather than approving anything.

### What appears, and what to say over it

The cue times below are **narration pacing for the take, not the measured run.**
They were written before the sequence was timed and they assume a person typing
the edit, which is why they run past the 1:17 above: that measurement is the
floor, with the edit applied by a script. Machine-measured timings — the eleven
dashboard counters, `ELAPSED 00:00` to `00:47` — are in
[`docs/SHOT_LIST.md`](SHOT_LIST.md), which also marks the beats no rehearsal has
covered.

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

**0:20 — one node, in full.** The frontier node's whole contract prints: the
outcome it owns, what it requires, what it may read and write, the commands it
may run, its acceptance checks, its budget, and the exact mission, base commit,
revision and digest it is bound to.

> "This is the entire authority of one node. Nothing here is advisory."

**0:25 — you change the route.** The plan is exported as canonical YAML. Edit
it — add a node, rewire an edge, widen or tighten a scope — and Graphene
compiles it into **revision 2** with a new digest.

> "The agent proposed a route. I'm changing it. That is not a suggestion to the
> model; it is the contract the runtime will be held to."

**0:35 — lint, diff, and a new approval.** `plan lint` re-validates the whole
revision atomically. `plan diff 1 2` names the changed nodes and edges and
flags any scope that only grew as a **SCOPE EXPANSION**. The old approval is
already void; the new digest needs its own.

> "Every scope I widened is called out, and the approval I gave a minute ago no
> longer covers this graph. I approve revision 2, and only revision 2 can run."

The credential-free proof that the runtime obeys the revision rather than the
proposal is `tests/integration/test_plan_edit_path.py`; these beats are that
same property, live.

**0:50 — two real workers, obeying revision 2.** The dashboard shows both work tasks `● running` at
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
uv run --frozen graphene demo --driver verified-replay --no-open --exit-after-demo
uv run --frozen graphene demo --no-open --exit-after-demo --automated-fixture
bash scripts/morning_verify.sh
```

Neither demo spends anything or contacts a provider.

`--driver verified-replay` is the zero-setup one: a hash-checked replay that
prints its own truth counters — `Live agent executions: 0`, `Gemini calls: 0`,
`Authoritative lineage writes: 0` — and creates no authoritative state. It is
the mode CI smokes, so it cannot rot.

The default driver (`scripted-local`, macOS only) runs the deterministic
fixture workflow end to end and finishes on `DEMO COMPLETE — committed lineage
verified`, `Promotion state: PROMOTED`, and `Local isolated commit — not pushed
/ no PR / no deployment`. Its operator gate is labelled on screen as
`SIMULATED OPERATOR — NOT HUMAN ATTESTATION`; say that out loud if you show it.

`morning_verify.sh` re-runs the locked environment, the full credential-free
matrix, the locked ruff, the location-only secret scan, `store.verify` on every
mission, capsule cold verification from a fresh clone, and the proof table. It
is the only thing allowed to print `ALL PASS`.

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
