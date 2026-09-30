# Pre-registration: the person's layer over provers, in Lean (the fields pilot)

*Written and committed on 2026-09-30, before any evaluation run. No arm below has run, no target has been
sent to a prover, and no person has reviewed a statement for this study. It is the evaluation design the fields
directive asks for (`docs/process/directives/FIELDS_DIRECTIVE.md`, "Evaluation design"). The commit that adds
this file is the registration. Once the first evaluation run starts, this file is not edited. Anything learned
afterwards goes in a results file, marked as after the fact.*

*The spikes of the same night (`spikes/lean/`, `spikes/redteam/`) are mechanics, not evaluation. They ran a
theorem already in Mathlib, with no model and no person, and nothing in them is a row of any table below.*

## The questions

1. **Does an explicit tree help?** Arm A against arm B.
2. **Does the person help?** Arm B against arm C. This is Graphene's claim.
3. **What does the person catch that the machine does not?** Seeded and natural misstatements, counted for the
   machine alone, the person alone, and both.
4. **Is reading a statement cheaper than writing it?** Two readers: one fluent in Lean, one who knows the
   mathematics and not Lean.
5. **What does a proven leaf cost, tier by tier?** Automation, a cheap model, a frontier model or Aristotle,
   then the person.

All five are answered by a **pilot**. The table under "Sample size" shows why a one-person study cannot confirm
an effect of the size we could hope for. Every result is reported as a pilot, with its n, and the kill
criteria are decision rules for the product, not statistical claims.

## The arms

The three arms share the targets and the gate. B and C share the leaf executor and the machine's tree. Where
arm A has an executor, it is the same one.

| Arm | Who shapes the work | Who proves | The person's part |
|---|---|---|---|
| **A. End to end** | nobody visible: the executor decomposes on its own | the executor, given the target statement and its informal proof | none until the end |
| **B. Machine tree** | a planner model proposes the tree (statements, definitions, needs); automated review and cheap falsification check it (below); what they flag is fixed by the planner or dropped, never by a person | the executor, leaf by leaf, cheapest tier first *(clarified before any run, 2026-09-30: the $0 automation baseline, then the executor; any tier of kill criterion 5 that is not the executor runs on the same leaves apart from the arms)* | none until the end |
| **C. Person-shaped tree** | B's tree, **the same tree B started from**, then the person answers the board's questions and approves or edits each statement and definition in Graphene before any leaf is sent | as B | reads, answers, edits, signs off |

- **Pairing.** C starts from the very tree B started from, so B against C isolates the person. A, B and C run
  on the same targets, so every comparison is paired by target.
- **The executor** is not chosen here: it is a question for Alex (`PLAN.md`, questions). Whatever is chosen is
  frozen before the first run as a numbered decision in `docs/DIRECTION.md`, with its version, and every row
  carries it. No harness is built for this study: the arms run on an existing prover or harness, and Graphene
  drives it as an executor through a check command.
- **Automated review and cheap falsification** (the machine's side, in B and in C before the person sees
  anything), each a command whose exit code is its verdict:
  1. `plausible` on every decidable leaf (a counterexample is a catch);
  2. `decide` on bounded instances where the statement quantifies over ℕ, ℤ or `Fin n`;
  3. a vacuity test: try to derive `False` from the hypotheses with `simp`, `omega` and `grind` under a
     time limit (success is a catch);
  4. the automation baseline (`decide`, `norm_num`, `simp`, `omega`, `aesop`, `exact?`, `grind`) under a
     time limit: a leaf that closes in under a second is flagged "suspiciously easy" for review, not caught;
  5. Batteries' `unusedArguments` linter on each automatically closed leaf: an unused hypothesis is a flag;
  6. a model's back-translation of each statement into English, shown beside the Lean. This is an aid, not a
     check, and it never counts as a catch.

## The gate (what "proven" means)

A target or leaf counts as proven only if every layer passes, in this order, from a trusted copy of
`lean-toolchain`, `lakefile.toml` and `lake-manifest.json` restored before the build:
1. `lake build` of the proof modules;
2. `#print axioms` of the target showing only `propext`, `Classical.choice` and `Quot.sound`;
3. the kernel replay, `lake env leanchecker` (shipped with the toolchain since Lean v4.28.0);
4. comparator against the challenge module the person approved, which holds the statements and every
   definition they use, run under its Linux sandbox;
5. *(added before any run, 2026-09-30)* at least two external kernels besides Lean's own, through
   comparator's external-kernel option: for example lean4lean and con-leche, which the Lean v4.35 toolchain
   bundles. Why: 2026 brought kernel soundness bugs (#14576, #14847), Lean 4.34.0 and 4.34.1 fixed more
   soundness bugs *(corrected before any run, 2026-09-30: it said "Lean 4.33 and 4.34 fixed kernel soundness
   bugs", which the release notes do not show)*, and nanoda, comparator's default external
   kernel, had its own bug then and two wrong rejects in the Kernel Arena (`landscape.md` §4).
6. *(added before any run, 2026-09-30)* SafeVerify against the same challenge. It is the one tool that
   caught matcher-auxiliary shadowing in LeanParanoia's comparison (`landscape.md` §4). Where it cannot run
   for memory, the row says so, and the target does not count as proven until it has.

`spikes/lean/gate/` holds the gate as it was measured on 2026-09-30, and `spikes/redteam/` holds what it
was attacked with.

## The targets, and contamination

Models have read Mathlib and the 2025 benchmarks, and several benchmarks are saturated (miniF2F at 100%,
PutnamBench at 672 of 672 for five systems; `landscape.md`, section 3). Contamination distorts the prover's
numbers far more than the person's. So:

- **The person's side** (questions 3 and 4) may use familiar theorems: undergraduate number theory and group
  theory, the courses Alex took, in trees of five to twelve leaves.
- **The prover's side** (questions 1, 2 and 5) uses only held-out targets:
  - open nodes of an active blueprint, taken only with the lead's agreement (the RLMEval precedent; the
    sphere-packing team objected to "drive-by proving");
  - lemmas from papers posted after the executor's training cutoff (ArXivLean's method);
  - LeanEval's active problems with no accepted solution on the day the set is frozen.
- **Freezing the set.** The set is frozen, and its list and hashes committed, before the first run. A target
  whose statement changes after that is void.
- **Pilot size.** 10 to 12 targets on the prover's side. On the person's side, 40 unseeded statements plus
  the seeded ones.

## Seeded misstatements

- **Planting.** Defects of the five kinds the directive names are planted in the machine's tree, one kind per
  statement, by a script from a list sealed before the run (the list's hash is committed; the list is opened
  after):
  1. a missing hypothesis;
  2. an off-by-one (natural-number subtraction, a 0-indexed range, `Fin` wraparound);
  3. a vacuous or totalized statement (unsatisfiable hypotheses; a `tsum`, `sSup` or `limsup` that Mathlib
     totalizes to 0);
  4. a swapped or misscoped quantifier;
  5. a definition of the wrong strength.
- **Where.** They go into about one statement in five, placed at random, and the reviewer is not told which.
- **What is counted.** For each seeded defect, whether the machine's review catches it, whether the person
  catches it, and whether both do. The person reviews after the machine has run and sees its flags, as in
  arm C.
- **The machine alone.** This is also recorded on a copy of the tree the person never sees.

## The metrics

For every run, one row:
- target id, arm, executor and model ids, graphene SHA, Lean and Mathlib versions;
- **targets proven**, by the gate;
- **cost:** tokens by tier; dollars at list price, with the price sheet's date; CPU-seconds for automation
  and for the gate; wall-clock time;
- **misstatements that reached compute:** leaves sent to a prover whose statement was defective.
  - Seeded ones are known.
  - Natural ones count once confirmed by adjudication: a Lean-fluent adjudicator who did not take part, or a
    proof of the negation.
  - The denominator is leaves sent.
- **hand-backs** *(added before any run, 2026-09-30)*: every leaf handed back, with its reason and whether it
  carries a witness the gate verifies (a proof of `¬ S_leaf`, or `False` from its hypotheses);
- **restarts:** the number of times after the first leaf was sent that more than a third of the tree's leaves
  were replaced or dropped;
- **the person's effort, counted:** statements read, board questions answered, edits made, sign-offs;
- **the person's effort, timed:** active seconds per statement, from the Graphene log's timestamps plus a
  stopwatch for reading that makes no keystroke.

For question 4, the **write** and **review** conditions:
- **write:** the reader produces the Lean statement for an informal lemma with any help except Graphene's
  proposal. A reader not fluent in Lean will usually use a general agent. They stop when they would sign it.
- **review:** the reader reads Graphene's proposed statement with its aids (English beside it, the board's
  questions, the machine's flags, examples and non-examples) and approves or edits it.
- Statements are assigned to the two conditions at random, 20 each per reader. *(Added before any run,
  2026-09-30.)* The 20 in the review condition are drawn from kill criterion 1's 40 unseeded statements.
  The 20 in the write condition are a separate set, since one reader cannot both write and review the same
  statement.
- Every result is judged against a gold statement by the adjudicator, so a fast wrong answer is visible.

## Sample size (from `prereg_power.py`, standard library only; rerun with `python3 prereg_power.py`)

**1. Arm C against arm A or B on targets proven** (exact McNemar, two-sided α = 0.05). The table gives the
power to detect C ahead. Columns are the share of targets only C proves, then the share only the other arm
proves.

| targets | C 0.20 / other 0.05 | C 0.15 / 0.05 | C 0.10 / 0.02 | C 0.10 / 0.05 |
|---|---|---|---|---|
| 10 | 0.00 | 0.00 | 0.00 | 0.00 |
| 20 | 0.10 | 0.03 | 0.01 | 0.01 |
| 30 | 0.24 | 0.10 | 0.05 | 0.02 |
| 50 | 0.48 | 0.24 | 0.20 | 0.07 |
| 80 | 0.74 | 0.44 | 0.44 | 0.13 |
| 120 | 0.90 | 0.63 | 0.67 | 0.22 |

A person-shaped tree that wins 15 points more of the targets than it loses needs 80 to 120 targets to be
seen reliably. **A 10-to-12-target pilot can show a direction and the size of costs. It cannot show an
effect.**

**2. Kill criterion 1** fires when marginal catches per statement fall below 0.10. The table gives the chance
it fires, by statements reviewed n and the true marginal catch rate r.

| n | r = 0.02 | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
|---|---|---|---|---|---|---|
| 20 | 0.94 | 0.74 | 0.39 | 0.18 | 0.07 | 0.01 |
| 40 | 0.99 | 0.86 | 0.42 | 0.13 | 0.03 | 0.00 |
| 60 | 1.00 | 0.92 | 0.44 | 0.10 | 0.01 | 0.00 |
| 100 | 1.00 | 0.97 | 0.45 | 0.06 | 0.00 | 0.00 |

At 40 statements the rule separates a person who adds 1 catch in 20 (fires 86% of the time) from one who adds
1 in 7 (fires 13%). Near the threshold itself it is a coin toss, which is what a threshold means.

**3. Kill criterion 2** fires when median review time over median write time exceeds 0.5. Times are
lognormal with σ = 0.8 on the log scale; that σ is an assumption, typical of task times, and the realised σ
will be reported. The table gives the chance it fires, by statements per condition and the true ratio.

| n per condition | ratio 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.8 |
|---|---|---|---|---|---|---|
| 10 | 0.01 | 0.11 | 0.28 | 0.49 | 0.67 | 0.87 |
| 20 | 0.00 | 0.05 | 0.23 | 0.49 | 0.72 | 0.93 |
| 30 | 0.00 | 0.02 | 0.20 | 0.50 | 0.77 | 0.97 |

Published ratios for Lean-fluent readers are about 0.4 (PutnamBench, 10 against 25 minutes) and 0.29 to 0.64
(IndiMathBench); `landscape.md`, section 6. At 20 statements per condition, a true 0.3 fires 5% of the time
and a true 0.6 fires 72%.

**4. Seeded defects.** The 95% Wilson interval on a catch rate is 0.30 to 0.70 for 10 of 20, and 0.33 to 0.67
for 15 of 30. With eight seeds per kind, per-kind rates are anecdotes, and they are reported as counts.

## Kill criteria, registered before any result

These are the directive's defaults. Three are made precise below (kill criteria 1, 3 and 5; corrected from "Two" before any run). Each change is written here, with its
reason, before any data exists.

1. **The person's statement review.** Suppose the person adds fewer than 1 real catch per 10 statements
   reviewed, beyond what the machine's review and falsification already caught, over at least 40
   **unseeded** statements. Then the person's statement review is not the product: narrow to intent and
   conventions (the board's questions only), or stop.
   - A **real catch** is a defect the person flags that the machine's steps above did not flag, and that the
     adjudicator confirms.
   - *Change, and why:* the directive's rule does not say which statements count. If seeded statements
     counted, the seeding rate would set the answer. So the rate is computed on unseeded statements, and the
     seeded ones are reported separately as detection rates by kind.
2. **Reading cost.** For either reader, if the median review time exceeds half the median write time over 20
   statements per condition, the attention claim fails for that reader.
   - Correctness is reported beside the time for both conditions. It does not change the rule.
3. **The person-shaped tree.** On the pilot targets, suppose arm A or arm B:
   - proves at least as many targets as C;
   - at no more model and compute dollars at list price;
   - letting no more misstatements reach compute than C.

   Then the person-shaped tree adds nothing there.
   - The person's minutes are reported beside the result and never converted into dollars for this rule.
   - *Change, and why:* "cost" in the directive's rule is read as model and compute dollars. Counting the
     person's time as cost would make C lose by construction.
4. **Faking the gate.** Suppose any exploit passes the whole gate above on a proof counted as proven, and no
   check command closes it. Then stop every evaluation run until one does.
   - This also applies to an exploit found by the red team or discovered in a run.
   - *(Clarified before any run, 2026-09-30.)* An exploit here is a faked proof of the approved statement:
     the gate should reject it and does not. An honest proof of a statement that does not say what was meant
     is a misstatement, counted under "misstatements that reached compute", not here. The red team's cases
     20 and 21 are of that kind (`spikes/redteam/README.md`).
5. **Cheap models.** On the leaves automation could not close, suppose a cheap model costs more dollars per
   proven leaf at list price than a frontier model on the same leaves. Then the cheap-model claim fails in
   mathematics.
   - *Change, and why:* the directive's rule also compares against Aristotle. On 2026-09-24 Aristotle's
     terms say "Harmonic does not presently charge fees" (`landscape.md`, section 1), so in dollars it would
     beat every paid tier by definition.
   - Against Aristotle the comparison is therefore on wall-clock time per proven leaf and is reported with
     its data terms. It is not part of the rule.
   - Token Factory publishes no cached-input price (`landscape.md`, section 5), so long agent loops are
     priced at the full input rate and say so.

## What earns the next phase

- **K1 does not fire, and K2 does not fire for at least one reader.** The person's layer has a reader it
  serves. The next step is the same design on more targets, with a second person.
- **K1 fires, K2 does not.** Keep only the board's convention questions and the sign-off record, and measure
  those alone.
- **K2 fires for the reader who does not know Lean.** The mathematician persona is not served by statement
  review. Look at the formalization lead instead, who reads Lean.
- **K3 fires.** Graphene adds nothing to proving these targets. Its remaining role in mathematics would be the
  record and the gate.
- **K4 fires.** Nothing else runs until the exploit is closed.
- **K5 fires.** Drop the cheap tier on proof leaves. Keep automation, then frontier or Aristotle, then the
  person.

## Amended before any run: the reader has a stake

*Added on 2026-09-30, after the registration commit and before any evaluation run exists. A review of
the plan found this bias unnamed.*

The one reader planned for the non-Lean side is Alex, who builds Graphene and wants the person's layer to
earn its place. So his results are read with these controls, and reported apart:
- **Seeded defects score themselves.** Each seed is on the sealed list, so "caught" is a fact about his
  edits, not a judgment.
- **The adjudicator does not know the condition.** Whoever confirms a natural misstatement does not know
  which condition, write or review, a statement came from.
- **Times come from logs.** Graphene's timestamps, plus a stopwatch only for reading that makes no
  keystroke. They are never estimated afterwards.
- **A second reader.** Someone outside the project who knows the mathematics and not Lean repeats the
  person's side on the same statements, when one can be found (November, `PLAN.md` §8).
  - Until then, every result from this side is labelled "the builder as reader".
  - Kill criteria 1 and 2 are read on his results only as a pilot.

## What is not fixed here

- **The executor**, and whether Aristotle is used (questions for Alex).
- **The planner model** for B's tree. It is resolved by role from the live list at run time, frozen before the
  first run, and recorded.
- **The adjudicator.** Recruiting a Lean-fluent adjudicator is part of November's plan. Until one exists, no
  natural misstatement counts as confirmed, and question 3 reports seeded defects only.
