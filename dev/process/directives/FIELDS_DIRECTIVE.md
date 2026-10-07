# Graphene: the fields directive

*For the agent that plans Graphene's first steps beyond software. Written 2026-09-29 with Alex and revised the same night after a review. Read `README.md`, `docs/HOW_IT_WORKS.md`, `dev/DIRECTION.md` (the decisions on the plan's grammar, scope, checks, executors, sandboxes, the board and the direction), `docs/process/field.md` and this file before you write anything.*

## What this run is

This is a planning run. Its product is a plan Alex can act on: who outside software would use Graphene and why, where its idea travels and where it does not, what the first step is, what that step costs, and how we will know it worked. You may research, run small local spikes and write documents. You do not change Graphene's product code, you do not spend on Token Factory or call any other paid model or prover, and you do not touch `main`.

Alex is asleep while you work, and nothing waits on him. When you need a decision, take the default you would recommend, write it down as an assumption, and add it to the questions in `PLAN.md`.

**Doubt your work, never your capacity.**
- Every claim about another tool, benchmark or model carries a link and the date you read it.
- Every claim about Graphene carries a file or a decision number.
- Everything you ran is written down with its command, its versions and its result.
- Before each measurement, write what you expect; then write what happened.
- Where you are guessing, say so.

Use sub-agents in parallel for the research and the spikes; you integrate and write. A split that fits: the landscape; Lean install, mechanics and the gate; the red team; the worked tree and the automation baseline; biology; other fields and Token Factory. Where a finding contradicts something in this directive, the finding wins; say so.

## Start from the people

A field is worth entering only if someone there has a problem Graphene solves better than what they use today. So this plan starts from people, not from Graphene's machinery, and every section answers to these four. Each description is a hypothesis to test, not a claim.

**The mathematician with a paper proof.** Knows the mathematics; is not fluent in Lean. Wants a machine-checked version of a result, or to learn whether an argument holds. Today they spend months learning Lean, find a formalizer, or give the paper to an end-to-end prover and cannot tell whether what comes back proves what they meant. Graphene would make statements the only thing they read — English beside Lean, with the machine's questions about conventions ("does ℕ start at 0 here?", "is this series assumed summable?") — and leave everything else to the kernel. A false lemma comes back with a counterexample before anyone spends a night on it.

**The formalization lead.** Runs a blueprint project with many contributors. Today: open nodes nobody wants to grind, statements that drift, review that eats the week. Graphene would send the blueprint's open nodes to existing provers overnight, cheapest first, through a gate that lets no statement or definition change, and return every node they could not do with a reason.

**The computational biologist.** Runs pipelines on a cluster. Snakemake or Nextflow run the steps; nothing stops a pipeline that is wrong in a plausible way — a variant numbered against a different isoform than the structure, a reference-build mismatch, a control that never ran — until a reviewer or a failed follow-up finds it, after the GPU hours are spent. Graphene would put the checks a careful bioinformatician writes on each step before spend, turn the judgments only a scientist can make into explicit sign-offs, and keep the record a methods section needs.

**The developer already using Graphene.** Lean is a laboratory for the software product: a field where the check is perfect shows what a check needs. The developer would get checks the agent cannot edit, checks that were attacked before they were trusted, and wrong specifications caught before spend.

For each person, the plan says what they would hand Graphene, what they would get back, why they would choose it over what they use now, what would make them stop, and what evidence — tonight or in November — would show the hypothesis false.

## The idea to test

Graphene's thesis travels wherever four things are true:

1. The work splits into a tree a person can read, in their own terms, and shape before anything is spent.
2. Each piece has a cheap check that cannot be faked.
3. Passing the checks means what the person meant, or the gap between the two is small and visible.
4. An agent's attempt costs far less than the person's attention.

The third condition says where the person's attention belongs: on the gap the check cannot reach. In Lean the kernel settles whether a proof is right, so the gap is whether the statements, and the definitions under them, say what the person meant — narrow and fully visible. In software, tests pass on wrong code, so the gap is wider. In biology a pipeline can pass every check and still not measure what the scientist thinks it measures.

Formal mathematics may meet all four better than software does. Computational biology meets the first and fourth and struggles with the second and third. Wet-lab work meets almost none of them.

Test this; do not assume it.

## What a first look found

A first pass over the landscape (see "Leads" below, read 2026-09-29) changes the questions. Verify each point before you rely on it.

- **The architecture already travels to Lean, without a person.** LeanMarathon (June 2026, code published) formalizes research papers with a blueprint as the system of record, agents whose edit scope is mechanically enforced, a deterministic CI gate, issues instead of silent failure, and parallel leaves. It reports finishing papers where a commercial end-to-end agent did not. This is validation and competition at once: Graphene's design works where the check is perfect, and a version without a person exists.
- **End-to-end provers are public.** Harmonic's Aristotle has a command-line tool to fill the sorries in a Lean project or to formalize a LaTeX paper.
- **Checkers exist.** The Lean reference recommends `lean4checker` in CI and names the Lean FRO's `comparator` as the gold standard for checking a proof against a trusted statement. SafeVerify and LeanParanoia do related jobs. Evaluate these; do not design a checker from scratch.
- **The machine may catch some misstatements better than the person.** LeanMarathon reports that Mathlib's conventions (a non-summable series sums to 0; the limsup of an unbounded count is 0) made some targets vacuous, that its agents found these, and that a human tends to read such statements charitably. In the other direction, a paper that used Aristotle reports the prover choosing a stronger definition than the authors meant when their prompt left it open.

So the question is no longer whether a tree helps. It is **what the person adds that the machine does not, and whether Graphene is the cheapest way to add it.** The candidates: intent (which theorem, how general), definitions and conventions (the board: the machine asks, the person answers), judging the machine's flags, and reshaping a tree that drifts.

**Decided (Alex, 2026-09-30): Graphene does not become a proof harness.** Building one would take engineering the evidence has not earned, and good ones exist. In mathematics Graphene is the person's layer — intent, statements, conventions, sign-offs and the record — over existing provers, harnesses and checkers, which it drives as executors and gates. Plan within that decision; do not reopen it.

## Why now, and the limits

Alex wants this in the hackathon submission, as where Graphene goes next, and as a real initiative after it. This month's evidence sets two limits.

- **Start small.** The product has grown faster than it has been proven: every attention study so far came back without a gain. This plan starts small, earns each step with evidence, and names when to stop.
- **Protect the entry.** Submissions close on 30 October, and nothing here may pull the main entry off course. Anything proposed before then is at most a day of work, and Alex is there for anything live.

Two more limits. Nothing tonight touches a Token Factory Sandbox (access was still pending on 29 September): measure local proxies and read the documented limits. And any spend proposed for later stays within Alex's standing cap for overnight runs ($10–20 of credits a night), with live tests run while he is present.

## Order of work

Work in this order. Commit and push after each item, open the draft PR with the first commit, and keep the brief current, so that if the night ends early what exists is still coherent.

- **P0.** The Lean spike: install, mechanics, the gate and the red team; the worked tree, the automation baseline and the seeded false leaf. The brief.
- **P1.** The mathematics landscape, models and money, the evaluation design and `PREREG.md`. The four people. The draft "What's next" paragraph.
- **P2.** Biology, with the check spike if time allows. The other-fields table. What Graphene would need. What this teaches the software product.
- **P3.** The phases, the risks, the questions, and `LEAN_DIRECTIVE_DRAFT.md`.

If the Mathlib cache cannot be fetched, do the spike on core Lean with a statement that needs no Mathlib, and say so in the brief.

## What to find out

### 1. Mathematics, first and in depth

**The mapping.** Map each Graphene concept to Lean, say where it maps cleanly and where it breaks, and fill the last column from the landscape. Where a row is fully covered by an existing tool, say what Graphene adds there, or that it adds nothing.

| Graphene | Lean | Already done by |
|---|---|---|
| goal | the target theorems, fixed by the person | |
| leaf | a lemma whose needs are proven, or taken as hypotheses | |
| needs | the lemma's dependencies | |
| scope | the files, or spans, an agent may edit | |
| hand-back | an issue with a witness: a counterexample, a proof of the negation, or a contradiction from the hypotheses — never "too hard" | |
| offer | a revised statement the person approves, with its effect on the parents | |
| forks | several attempts at a leaf; any that passes the gate is valid | |
| the board | the machine's questions about definitions and conventions, answered by the person | |
| the direction | the targets file the person owns: the tree may change, the targets may not without the person | |

**The check that cannot be faked.** Say exactly what must pass, and where:
- `lake build`;
- no `sorry` and no `admit`;
- `#print axioms` showing only `propext`, `Classical.choice` and `Quot.sound`;
- no statement changed, and no definition that a statement depends on changed;
- the kernel replay (`lean4checker`) and a challenge-against-solution check (`comparator` or SafeVerify).

Measure what each layer costs. A fast check inside an agent's loop and the gold-standard check at the gate may be different tools; say which runs where.

Scope today is file paths, so decide how the statement is protected. Weigh at least these options, pick one, and give your reasons:
- each lemma's statement in a read-only file and its proof in a writable one;
- a check that compares the elaborated statement with the approved one — this is what `comparator` and SafeVerify do, so test them rather than reimplement them;
- scope at the level of a declaration or a span (LeanMarathon enforces spans with a patched edit tool);
- statements as `Prop`-valued definitions in a read-only challenge module that also holds every definition they use; one proof file per leaf; and each leaf proving `needs → statement`, so leaves can be checked in parallel before their needs are proven, and the root composes them.

First test whether today's file-path scope plus a check command already gives full protection. If it does, the answer is "no new feature"; say so.

**The red team.** "Cannot be faked" is a claim, so attack it. Under `spikes/redteam/`, write one small cheating solution per exploit and record which layer rejects it — scope, `#print axioms`, `lean4checker`, `comparator` or SafeVerify — or that none does. At least:
- `sorry`, `admit`, and a declared `axiom`;
- `native_decide`;
- `set_option debug.skipKernelTC true`;
- redefining or shadowing a definition the statement uses, through a namespace, a notation or a macro;
- editing the challenge file, the lakefile, `lake-manifest.json` or `lean-toolchain` (for instance, pointing Mathlib at a fork);
- a dummy structure standing in for missing theory, so leaf statements type-check and prove nothing (LeanMarathon reports its own harness did this); say at which level it is caught;
- a vacuous statement, whose hypotheses cannot all hold. Expect no gate to catch this one; only a check before spend can.

Start from the exploit lists published with LeanParanoia and the OEIS Open benchmark, and add any you find.

**The person's part.** Reviewing statements is where the person's attention goes. Answer for two readers, one fluent in Lean and one who knows the mathematics but not Lean:
- Is reading a lemma tree cheaper than writing it?
- What makes statements reviewable for the second reader: English beside Lean, generated examples and non-examples, a counterexample search, a back-translation? Which of these are checks, and which are only aids?
- How are misstated lemmas caught before compute is spent? Separate what the machine catches cheaply — `plausible` (formerly `slim_check`), `decide` on small cases, a vacuity test, an alarm when a lemma closes suspiciously easily — from what only the person can catch, which is intent.
- What does a hand-back look like when a lemma is false, and what keeps it from becoming an escape hatch? LeanMarathon's workers gamed a "too long to formalize" rule until it was removed; a hand-back must name a concrete defect.

**The landscape.** Find out what exists, where Graphene is redundant, and where it is the missing piece: the person shaping the tree before spend, the boundary, and the economics of cheap models. Your training data is likely older than this field's last year: search, do not recall. Cover at least:
- agents and harnesses that formalize whole papers or projects: LeanMarathon, Aristotle, Gauss (Math Inc), AxiomProver, AlphaProof Nexus, and whatever has appeared since;
- blueprints: `leanblueprint`, LeanArchitect, and the large projects that coordinate people through a dependency graph (FLT, PFR, Carleson, the Equational Theories Project);
- Mathlib's workflow;
- provers for single goals: DeepSeek-Prover-V2, Kimina-Prover, Goedel-Prover-V2, Seed-Prover and their successors; LeanDojo and Lean Copilot;
- verification infrastructure: `lean4checker`, `comparator`, SafeVerify, LeanParanoia, the Lean REPL, Kimina Lean Server, AXLE;
- the benchmarks: miniF2F, ProofNet, PutnamBench, and newer held-out sets (OEIS Open, Formal Conjectures, research-paper sets).

**Models and money.**
- Which models on Token Factory can write Lean? Read its live model list and docs; do not assume. A first look found general open models (DeepSeek, Qwen, Kimi, GLM, Nemotron, GPT-OSS) and no Lean-specialized prover; confirm or correct that.
- Which open provers could run there? Token Factory hosts custom fine-tuned models: check whether an open prover's base model is supported, and at what price.
- What would one proven lemma cost through a cascade — automation first at $0, then a cheap open model, then a frontier model or Aristotle, then the person? For a reference point, LeanMarathon's tables work out to roughly $2–6 per proof node at GPT-5.5 API-equivalent prices (our arithmetic; check it).
- Would the sandbox's set-up-once, fork-many pattern fit Mathlib, whose setup is heavy? Measure the local proxies — the size of the toolchain and the cache, the time to fetch them, a cold check against a warm Lean server — and read the sandbox's documented limits.

**A spike: local, with no model spend.**
- Install Lean with `elan` and make a small project. Pin the toolchain and the Mathlib revision, and record both.
- Measure:
  - the size of the toolchain and the Mathlib cache, and the time to get them;
  - `lake build` with and without `sorry`;
  - what `#print axioms` shows;
  - a one-lemma check, cold (`lake env lean`) and warm (a REPL or server kept running);
  - the gate (`comparator` or SafeVerify) on one challenge and its solution.
- Write by hand the tree Graphene would propose for one real theorem Alex can read. He has taken group theory and number theory, so pick from there: five to twelve leaves, at least one where Lean's conventions bite (ℕ subtraction, `ZMod`, division by zero). Fermat's little theorem through Lagrange's theorem joins his two courses; the infinitude of primes congruent to 3 mod 4 has leaves that automation should close. A theorem already in Mathlib is fine here, because the spike tests mechanics, not a prover; say so.
- Write the tree in Graphene's plan text form, with scopes and checks, in a scratch repository, and say whether `graphene plan edit` accepts it as it is. Write the same tree as a Lean challenge module (and, if it is cheap, in LeanArchitect's format), and say whether the forms round-trip.
- **The zero-spend test of the thesis.** Run the automation tactics — `decide`, `norm_num`, `simp`, `omega`, `aesop`, `exact?`, `grind`, and any hammer you can install — under a time limit, first on the whole theorem, then on each leaf. If the whole theorem fails and most leaves close, the tree turned work no cheap tool could do into work cheap tools can do, for nothing. That table is the thesis.
- **A seeded false leaf.** Add one leaf that is false in a way a tired reader might miss; for the primes example, "every odd n > 1 has a prime factor congruent to 3 mod 4", which fails at 5. Record whether the checks before spend catch it, how fast, and what the hand-back says.

**Evaluation design.** Say how to measure this honestly, and write it so it can be pre-registered: put it in `PREREG.md` and commit it before any evaluation run exists.
- The arms, holding the leaf executor and model fixed where they apply:
  - A, end to end: the theorem and its informal proof to a prover that decomposes on its own (Aristotle, or the same model in a single Lean loop);
  - B, machine tree: a model proposes the tree; automated review and cheap falsification check it; no person;
  - C, person-shaped tree: B, plus the person answers the board's questions and approves or edits statements in Graphene before spend.

  A against B tests whether an explicit tree helps. B against C tests whether the person does, which is Graphene's claim. Arms B and C run on the same existing harness or prover — LeanMarathon's published code, for example, or Aristotle per leaf — and differ only by Graphene's layer in C. Do not build a harness to run them.
- The metrics: targets proven; cost in tokens and CPU; misstatements that reach compute, natural and seeded; restarts of the tree; and the person's effort, counted (statements read, questions answered, edits made) as well as timed.
- Seeded misstatements: plant defects of known kinds — a missing hypothesis, an off-by-one, a vacuous or totalized statement, a swapped quantifier, a definition of the wrong strength — without telling the reviewer where, and compare how many the machine, the person, and both together catch.
- The theorem set and contamination. Models have read Mathlib. Contamination distorts the prover's numbers far more than the person's, so familiar theorems can serve for the person's side; the prover's side needs held-out targets, such as results published after the model's cutoff, open nodes of active blueprints, or conjectures resolved after the cutoff.
- Say what sample size detects what effect, and call a one-person study a pilot.

### 2. Biology, honestly

**Computational biology.** Pipelines are already DAGs (Snakemake, Nextflow), and nf-core pipelines already validate their inputs and ship tests (check). Graphene should not be another workflow engine: if it enters, it wraps the pipeline the person already has. Say what a leaf would be and what its check could be:
- reproducing a known control;
- schema and range checks;
- invariants that cost nothing to check, such as a variant's wild-type residue matching the sequence of the structure used;
- statistical sanity bounds;
- agreement with a reference.

Then say what breaks:
- long jobs on clusters (SLURM) or GPUs;
- data too big for git;
- results that are plausible rather than right, which is the third condition;
- provenance.

**A case Alex knows.** In 2023 he ran an AlphaFold and NetSurfP pipeline on HPC that classified over 10,000 oncogenic protein variants. Use it as a thought experiment. You know nothing about it beyond this paragraph, so label every detail you assume and list what Alex must confirm.
- What would the tree have been?
- Which checks would have caught real mistakes?
- Where would Graphene have saved attention, and where would it have cost attention?
- Which nodes could only a scientist sign off, and on what evidence?

**A check spike with no compute (P2, if time allows, at most two hours).** Take a small public slice: a handful of well-studied cancer genes, their missense variants from ClinVar, UniProt sequences, AlphaFold DB's precomputed structures, and precomputed pathogenicity scores such as AlphaMissense's (check the licenses and access). Write each check as a script whose exit code is the check: each variant's stated wild-type residue matches the structure's sequence at that position; a few known controls come out as the chosen method says they should (state the method and cite why); confidence at the site is high enough to interpret; agreement with the reference is reported, and disagreement is flagged for sign-off rather than counted as failure. Report what fraction fails each check, and why. No GPU, no spend.

**What would have to change in Graphene.** Before proposing anything, try to express it with what Graphene has today — a check command, a scope, a hand-back — and say exactly where that fails:
- scope over data and compute budgets;
- checks beyond an exit code, including a person's sign-off as an explicit kind of check;
- executors that submit a job and wait for hours;
- provenance in the record.

Also say whether Nebius AI Cloud could host such runs (its GPU offerings and any Slurm service), and whether NVIDIA's hosted biology models could act as an executor that sidesteps cluster jobs for a first test. Check; do not assume.

**Wet lab.** Write a paragraph, not a plan: why it does or does not fit now.

### 3. A short scan of other fields

Score a handful of fields on the four conditions, in one table with one line each. Include at least:
- numerical methods, with manufactured solutions and convergence-order tests;
- verified software in Dafny, Verus, Coq or Lean, the bridge back to Graphene's own users;
- data analysis;
- one field where checks are easy to game, such as backtested trading strategies, as a warning;
- anything else you find.

No deep dives.

## What to write

Everything goes in `docs/process/fields/`.

**`PLAN.md`, the plan.** It opens with a brief of at most fifteen lines: for each field, the verdict and who would use it, in a sentence; the first step, its cost and time; and what Alex decides. Then these sections, in order:

1. Who would use this, and why: the four people, each with the evidence for and against.
2. The four conditions, scored per field, with the evidence.
3. Mathematics: the mapping, the check, the red team, the person's part, the landscape and where Graphene differs, models and cost, the spike's results beside your predictions, the worked tree, and the evaluation design.
4. Biology: the same questions, shorter, with the case study and the check spike if it ran.
5. Other fields: the table.
6. What Graphene would need, in order, smallest first, each with what it would prove and what you tried with today's Graphene first.
7. What this teaches the software product: which lessons from Lean — checks the agent cannot edit, checks attacked before they are trusted, falsification before spend, hand-backs that must name a defect, the machine asking and the person answering — would change Graphene's checks for code, each with the test that would show it. Nothing here is built before 30 October.
8. The phases: before 30 October (at most a day, and only if it helps the submission), November, and after. Give each its goal, its cost and time, what Alex does himself, and the evidence that earns the next phase. The natural candidate for the day before 30 October is a rerunnable demo of the spike: the whole theorem failing under automation, the leaves closing, the false leaf coming back with its counterexample, and the red-team table; plus, if Alex approves, one capped live run of a Token Factory model on the leaves automation could not close, with him present. November names the first real users to approach — a Lean formalizer, the lab where the 2023 pipeline ran, and a developer using Graphene — and drafts the messages for Alex to send. Do not send anything.
9. Risks, and when to stop: named, measurable kill criteria, with numbers, committed in `PREREG.md` before any result exists. Start from these defaults, and change one only with a reason written down first:
   - the person adds fewer than one real catch per ten statements reviewed beyond what the machine's review and falsification already caught → the person's statement review is not the product: narrow to intent and conventions, or stop;
   - reviewing the median statement takes more than half as long as writing it → the attention claim fails for that reader;
   - arm A or B proves the pilot targets at no more cost than C and lets no more misstatements through → the person-shaped tree adds nothing there;
   - the red team finds an exploit that no check command closes → stop until it is closed;
   - on the leaves automation cannot close, cheap models cost more per proven leaf than a frontier model or Aristotle → the cheap-model claim fails in mathematics.
10. At most five questions for Alex, each with your recommended answer. Graphene's role in mathematics is decided (the person's layer, not a harness), so do not ask it again. Include whether to get an Aristotle API key for November, and which existing harness or prover the November arms should run on.
11. A draft paragraph for the "What's next" section of `docs/HACKATHON.md`. It is honest and specific, and claims only what the spike showed. Do not apply it.

**`landscape.md`.** Every source, with its link, the date you read it, and one line on what it showed.

**`PREREG.md`.** The evaluation design and the kill criteria, committed before any evaluation run.

**`spikes/`.** Every command you ran and its output, with pinned versions, enough for Alex to repeat it: `spikes/lean/`, `spikes/redteam/`, and `spikes/bio/` if it ran.

**The next directive.** `dev/process/directives/LEAN_DIRECTIVE_DRAFT.md` is a draft directive for the first build step, for Alex to edit, in the style of the directives before it. That step builds the layer, not a harness: Graphene driving an existing prover or harness on one small tree, with the gate as a check command.

## What not to do

- No change to `src/`, `tests/` or anything the product ships, and no merge to `main`. Use one branch, `fields`, with one draft PR.
- No Token Factory or Sandbox spend, no call to any paid or external model or prover (Aristotle included), no account created, and no key read or printed.
- No claim about a tool, model or benchmark without a source, and no guess presented as a finding. The leads below are leads: open each one before you rely on it.
- No detail about Alex's 2023 pipeline that is not labeled as an assumption.
- No plan that grows Graphene before evidence asks for it: every proposed feature names the result that would justify it, and what you tried with today's Graphene first.
- No plan that turns Graphene into a proof harness. Provers, harnesses and checkers are executors and gates that Graphene drives.
- Nothing that competes with the hackathon entry for Alex's time before 30 October, beyond the day this directive allows.

## When it is done

It is done when:
- the brief in `PLAN.md` can be read in a minute and acted on;
- each of the four people has a verdict, and the evidence that would change it;
- every claim in the plan traces to a source, a spike or a decision;
- the spike and the red team can be rerun from `spikes/`.

Push, and put the brief in the PR description.

## Leads (read 2026-09-29; verify before relying on any)

- LeanMarathon: https://arxiv.org/pdf/2606.05400 — a multi-agent Lean harness: blueprint as system of record, contract-scoped agents with enforced edit spans, a CI gate, parallel leaves. Reports two 2026 papers (four Erdős problems) formalized in three runs costing about $190–$620 each, and a commercial agent failing on the same inputs; also reports its harness faking missing theory, and workers gaming a size-based escape hatch.
- Aristotle's command-line tool: https://pypi.org/project/aristotlelib/ — fills the sorries in a Lean project; formalizes a LaTeX paper.
- A paper proved with Aristotle: https://arxiv.org/pdf/2604.18869 — the prover chose a stronger definition than intended when the prompt left it open.
- The Lean reference on validating proofs: https://lean-lang.org/doc/reference/4.29.0/ValidatingProofs/ — `lean4checker` in CI; `comparator` as the gold standard.
- `comparator`: https://github.com/leanprover/comparator. SafeVerify: https://github.com/GasStationManager/SafeVerify. LeanParanoia: https://reservoir.lean-lang.org/@oOo0oOo/paranoia — exploit detection and a comparison of verifiers.
- OEIS Open: https://arxiv.org/pdf/2608.11941 — a benchmark of conjectures verified with SafeVerify; lists exploits, including redefining a definition a statement depends on.
- AXLE: https://arxiv.org/pdf/2606.26442 — fast proof verification, compared against SafeVerify, Comparator and Kimina Lean Server.
- The Lean FRO's timeline: https://lean-lang.org/fro/about/ — 2026 developments, including AlphaProof Nexus and AxiomProver.
- Formalizing Erdős problems: https://xenaproject.wordpress.com/2025/12/05/formalization-of-erdos-problems/ — novices formalizing with LLMs and, later, Aristotle.
- Token Factory: https://docs.tokenfactory.nebius.com/post-training/models, https://github.com/nebius/token-factory-cookbook and https://nebius.com/services/token-factory/inference-service — models, fine-tuning, and custom model hosting.

Now go. Find out who would really use this, where the idea really travels, and be honest about where it doesn't.
