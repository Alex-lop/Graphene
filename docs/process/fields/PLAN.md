# Graphene beyond software: the plan

*Written by the agent that ran `docs/process/directives/FIELDS_DIRECTIVE.md` on 2026-09-30 (00:45 onwards, EDT), for Alex. Every link was read on 2026-09-30; `landscape.md` holds each source with its one-line finding. Decisions are numbered as in `docs/DIRECTION.md`. A pointer written `landscape.md` §N is to the sources file; a bare §N is a section of this plan.*

## Brief

- **Mathematics: worth a pilot, not a build.** Who: a formalization lead scoping and freezing statements before AI runs (the grinding is already done by AI), and perhaps a mathematician who does not read Lean. That second one holds only if the machine's convention questions help them, which nobody has measured. Prove2Me, Verso Blueprint and Tau Ceti already cover the rest of a person's layer (§1, §3.5).
- **The Lean spike:** Graphene carried the tree as written; automation closed 3 of 8 leaves for $0 and not the theorem, so the thesis holds only in its weak form; a false leaf came back with n = 5 in 0.14 s, before any spend (§3.4, §3.8).
- **The red team:** 21 attacks, run on core Lean. Every attack that faked a proof was rejected by at least one layer, and none by all. Wrong statements pass every gate. Comparator's real sandbox never ran on a Mathlib project (§3.2, §3.3).
- **What Lean found in Graphene itself:** it accepts "too hard" as a hand-back, and its local check runs a leaf's code unsandboxed. Both matter for code too (§6, §7).
- **Biology: not now.** Who: a computational biologist wanting sign-offs on a pipeline. None has been found, and Claude Science and Nextflow's agent are there first. Four cheap checks caught 17 records numbered on another isoform in 6,227, and a correct check also drops BRAF V600E (§4).
- **Other fields:** numerical methods is the closest fit outside mathematics; verified software is the bridge back to Graphene's developers; backtested trading is the warning (§5).
- **Before 30 October, optional:** a replayed demo of the spike. It costs $0, half a day of an agent's time and half an hour of yours. If you want it, also a live Nemotron run on the five open leaves, capped at $2, with you present (§8).
- **November:** `PREREG.md`'s pilot. The person's side comes first, with you as the reader, about 12–25 hours over two weeks. Then 10–12 held-out targets on a Linux gate, within $10–20 a night (§8).
- **You decide** (§10):
  - an Aristotle key: yes, with the opt-out on;
  - the executor: Aristotle for all three arms, plus one cheap and one frontier tier;
  - the demo, if the entry is done by 25 October;
  - the 2023 pipeline's assumptions, and whether to ask the lab;
  - which lead to ask first.

## 1. Who would use this, and why

Each person is a hypothesis. For each: what they would hand Graphene, what they would get back, why they
would choose it over what they use today, what would make them stop, the evidence on each side, and what
would show the hypothesis false. A pointer written `landscape.md` §N is to that section of the sources file,
where the links are; a bare §N is a section of this plan.

### The mathematician with a paper proof

**Verdict: plausible, unproven, and narrower than the directive's picture.** No tool we found puts the
machine's questions about conventions to the person as a durable board before proving; Aristotle asks during
a run, with a 15-minute timeout (`landscape.md` §1). We found no measurement of any statement-review aid for
a reader who does not know Lean (`landscape.md` §6).

- **They hand Graphene:** the paper or its informal proof, the target theorems in their own words, and
  answers to the board's questions ("does ℕ start at 0 here?", "is this series assumed summable?", "C∞ or
  analytic?").
- **They get back:**
  - the challenge file they approved: the statements and every definition under them, English beside Lean;
  - each leaf proven by the gate, or handed back with a witness: a counterexample, a proof of the negation, or
    `False` from the hypotheses;
  - the record of what they signed.
- **Why they would choose it:** each of today's options leaves a gap Graphene might fill.
  - *A general coding agent plus discipline* has produced results for people who can read Lean statements.
    Tao's Sendov formalization took 4 days, with an 87-line `Challenge.lean` as "the statement of record".
    Ilin, who wrote no Lean himself, took 10 days and about 50 hours of supervision with Claude Code and
    Aristotle, and the `ContDiff ℝ ⊤` trap got past him (`landscape.md` §6).
  - *Aristotle's `formalize`* takes no prompt and asks nothing. Aristotle's separate `submit --wait` asks
    questions with a 15-minute timeout, then goes "with its best guess"; as far as the client source shows,
    the answers are not kept as a record (`landscape.md` §1).
  - *Prove2Me* has a person click to confirm each core statement and compares a blind read-back. It is
    hosted, and its convention checks are written rules for the captain ("know what total functions return
    on bad input"), not questions the machine generates (`landscape.md` §1; the researcher's reading).
- **What the person adds, and whether Graphene is the cheapest way to add it** (the directive's four
  candidates; each verdict is this plan's reading, and none is measured):
  - *Intent* (which theorem, how general; evidence below): for a reader of Lean, a challenge file carries it
    at no tool cost, and Graphene adds nothing there (§3.5).
  - *Definitions and conventions:* the board is the one place Graphene differs from every tool found (§3.5).
    Whether it is cheaper than a person's own check is open: Miller caught `ContDiff ℝ ⊤` with "a
    thirty-second #check" (`landscape.md` §6).
  - *Judging the machine's flags:* the best catches in the record pair a machine flag with a person's verdict
    (§3.4). Formal Conjectures does this with maintainers and an AI audit, without Graphene
    (`landscape.md` §6).
  - *Reshaping a tree that drifts:* Ilin's main theorem gathered 42 hypotheses before the final 12
    (`landscape.md` §6). Graphene's offers reshape a code tree (decision 32); nobody has tried them on Lean.
- **What would make them stop:**
  - reviewing a statement takes more than half as long as writing it (kill criterion 2, `PREREG.md`);
  - the questions are noise;
  - a general agent with a challenge file is already enough.

  EconCSLib is the warning. Its author built a review dashboard, and by v2 of its paper 10 of 865 paper
  statements had been reviewed (researcher's count, `landscape.md` §6).
- **Evidence for:**
  - Each mathematician-led case we read kept a person on statements and definitions: Tao, Ilin, Miller,
    Bloom and the AlphaProof Nexus experts (`landscape.md` §1, §3, §6). Large efforts that did not either
    spot-checked (Gloeckle et al., `landscape.md` §1) or barely reviewed (EconCSLib, `landscape.md` §6).
  - `ContDiff ℝ ⊤` means *analytic* in today's Mathlib. It silently broke two independent projects in 2026,
    and in one of them neither the agent nor the mathematician caught it in 10 days (`landscape.md` §6).
  - Intent needed people: which version of Erdős #728 was meant. And a convention was decided silently: when
    the prompt left a definition open, Aristotle adopted a stronger one (harmless: the authors noticed, and
    Lean proves the two equivalent) (`landscape.md` §6).
- **Evidence against:**
  - The "months learning Lean" premise is dated: 2026 mathematician-led formalizations took 4 days to about
    a month with general agents (`landscape.md` §6).
  - The strongest users (Tao, Ilin, Miller) did it with a general agent plus discipline and no dedicated
    review tool (`landscape.md` §6). Inference: Graphene competes with that.
  - Where review is optional, it can go unused (EconCSLib, above). Where it is required, as for Prove2Me's
    captain and in Formal Conjectures' mandatory review, it happens (`landscape.md` §1, §6).
  - Inference: machines are strong *falsifiers*. In MechGeo a kernel-checked counterexample search refuted 22
    of 157 geometry statements that a three-expert majority had judged faithful, though Tao found machine
    sweeps "far from comprehensive" (`landscape.md` §6).
- **What would show it false:**
  - Tonight: nothing can; the spike has no person in it.
  - November: kill criterion 2 fires for the reader who does not know Lean. Kill criterion 1 (fewer than 1
    real catch per 10 unseeded statements beyond what the machine's review and falsification caught) would
    narrow the product to the board's convention questions, or stop it; if only it fires, `PREREG.md` keeps
    the board's questions and measures them alone. No kill criterion for the board itself is registered yet.

### The formalization lead

**Verdict: the pain the directive names first is largely gone; the other two are real, and Graphene
addresses one of them.**

- **They hand Graphene:** the blueprint's open nodes they choose to send, with the statements and
  definitions frozen in a challenge module.
- **They get back** (proposed; none of it exists in Graphene today): proofs that passed the gate
  (`spikes/lean/gate/`) against those statements; every node handed back with a witness that names a defect;
  and the rest marked "budget exhausted, no defect found" (§3.4). Runs would be overnight, cheapest prover
  first. Graphene's cap today, the night's ledger, covers Token Factory calls only and stops a night at $10
  at most (decision 102).
- **Why they would choose it:** the proposed layer scopes and freezes before the AI runs. They choose which
  nodes, in which form, and nothing drives by. Against what they would use today:
  - Verso Blueprint's work queue hands out nodes, with no statement-freezing gate, spend control or
    hand-back with a witness (§3.5);
  - comparator checks a proof against a lead's own challenge file, and the Lean FRO plans to ship it with
    Lean (`landscape.md` §2, §4);
  - Aristotle is free, but keeps no durable record and does not guarantee that given statements come back
    unchanged (§3.5).

  This plan's reading: what is left for Graphene is one layer over all three, with a cap and witnesses.
  Nobody has asked a lead whether they want it.
- **What the evidence says about the three pains:**
  - *Open nodes nobody wants to grind: mostly obsolete.* Tao, 21 June 2026, on his blueprint: "virtually every
    formalization task I had issued could be completed within hours", and the queue is "essentially empty"
    (`landscape.md` §2).
    - Gauss produced a sorry-free proof of sphere packing's dimension-8 main theorem in 5 days; whether it
      follows the intended proof path is still being checked, and the public blueprint was not updated.
      Anthropic proved FLT end to end in 11 days by a different route from Buzzard's blueprint, which still
      shows 103 of 240 nodes open (`landscape.md` §1, §2).
    - Leads did not always want it: "drive-by proving", and Avigad's "The formalization, on its own, is close
      to worthless" (`landscape.md` §2).
  - *Statements that drift: real.* Carleson changed definitions, hypotheses and constants. PFR missed a
    2-torsion hypothesis (`landscape.md` §2). Autoformalizers in Tao's project "exploited misformalized
    sorried statements from the literature that were false", usually caught because "the proof was
    suspiciously easy" (`landscape.md` §6).
  - *Review that eats the week: real, but not Graphene's to solve.* PNT+ opens its PR guide with "Reviewer time
    is the scarcest resource on this project". The 691 Mathlib PRs on the review queue had been in review a
    median of 28 days (researcher's count from one snapshot, which favours long waits; the Mathlib Initiative
    states about two weeks) (`landscape.md` §2). The proposed gate would make a proof acceptable as
    *correct*. It would not make it mergeable into a curated library.
- **What would make them stop:** the pieces already exist without Graphene.
  - Verso Blueprint (Lean FRO): owners, priorities, statuses computed from Lean, and an agent work-queue.
  - Prove2Me: audited statements.
  - LeanArchitect: computed status.
  - comparator, which the Lean FRO plans to ship with Lean (`landscape.md` §1, §2, §4).
- **Evidence for:** Tao expects to "spend more time scoping the IEANTN formalization tasks in anticipation of
  rapidly receiving an AI-generated proof" (`landscape.md` §2). That is the tree shaped before spend.
- **Evidence against:** the competition above. A guess: a lead who reads Lean may value English beside Lean
  less, though blueprints, which are English beside Lean, are the leads' own tool (leanblueprint in about 38
  projects, LeanArchitect in 226 repositories; `landscape.md` §2).
- **What would show it false:** in November, a lead declines because Verso Blueprint, the `intentions` bot
  and Aristotle already do what they need. Or their statements need no freeze once comparator ships in the
  toolchain.

### The computational biologist

**Verdict: not now as a product. The spike supports the idea's middle, not its ends.**

- **They hand Graphene:** the pipeline they already run, and its steps as leaves.
- **They get back:** checks a careful bioinformatician would write, run before the next step spends. Their
  judgments become explicit sign-offs, with the flags as evidence. A record for the methods section.
- **Why they would choose it:** pipelines' own tests do not check the biology. nf-core's module tests may
  "produce nonsense output", and nf-schema checks parameters and samplesheets, not biology. Point tools
  check a few invariants: bcftools `norm --check-ref` for a reference-build mismatch, somalier for sample
  swaps (`landscape.md` §7).
  - The spike's wild-type check flagged 16 of 213 KRAS records: ClinVar numbers KRAS on K-Ras4B, UniProt and
    AlphaFold on K-Ras4A. None is a data error. A pipeline that joined the two without the check would score
    those records against the wrong residue, silently (§4.4).
  - That check is not enough alone: it catches 16 of the 32 mis-numbered KRAS variants, and a per-protein
    sequence-identity check or a genomic join catches all 32. A separate measurement (M2) found that joining
    by the protein-change string gives 13 of 213 KRAS variants another codon's score, four of them
    pathogenic, with no error raised (§4.3; `landscape.md` §7).
- **What would make them stop:**
  - The checks are cheap but interpretation is not checkable. A correct confidence check drops BRAF V600E
    (§4.4).
  - Inference: for human canonical proteins, structures and AlphaMissense scores are precomputed and free
    (AlphaFold DB v6), so a check before spend saves little GPU spend; the cost of an error lands in
    interpretation (`landscape.md` §7).
  - A Graphene check is capped at 30 minutes (`CHECK_TIMEOUT` in `src/graphene_map/plan.py`;
    `docs/HOW_IT_WORKS.md` P2 step 3), and git-ignored data is absent from the check's worktree. An executor
    that waits hours for a cluster job is untested, and data outside git has to be verified against
    committed hashes (§4.2).
- **Evidence for:**
  - "The most consequential challenge in agentic genomics is not generating analyses but verifying them"
    (Cell Genomics 2026, `landscape.md` §7).
  - Nextflow's own design record for its new `agent` primitive lists two gaps: enforcing validation tiers
    ("the most consequential unaddressed item") and diffing the registered plan against what ran ("Nothing
    implements the comparison"). It declares cost tracking and token budgets non-goals (`landscape.md` §7).
    The two gaps are close to Graphene's layer.
- **Evidence against:** Claude Science (Anthropic, beta since 2026-06-30) already drafts a plan, asks before
  new resources, submits to the person's own HPC over SSH, and runs a reviewer agent. Seqera AI executes "with
  your approval" (`landscape.md` §7).
- **What would show it false:** the 2023 lab says the errors that hurt them were interpretive, which
  invariants cannot catch. Or Nextflow ships tier enforcement and the plan diff.

### The developer already using Graphene

**Verdict: the most immediate beneficiary, through lessons, not features.** Lean is the laboratory: a field
where the check is perfect shows what a check needs. §7 lists each lesson with the test that would show it.

- **They hand Graphene:** what they hand it today, their repository and a plan of leaves, each with a scope
  and a check command (`docs/HOW_IT_WORKS.md` P1).
- **They get back:**
  - *today:* scopes, `readonly:` and `protected:` globs (decision 90), and leaves that come back with offers
    (decision 32) or with their cause (decision 68);
  - *if the lessons hold (proposed, §7):* checks the agent cannot edit, extending `readonly:` to the files a
    leaf's own check reads; checks attacked before they are trusted; wrong specifications caught before
    spend; hand-backs that must name a defect.
- **Why they would choose it over what they use now:** today a planner can give a leaf the test file its own
  check runs, so the executor can edit what judges it (§7, lesson 1). Other fields hide the tests instead,
  which brings cheating near zero but degrades performance on the task itself (ImpossibleBench,
  `landscape.md` §8). Inference: making a check's files read-only to its own leaf is the cheaper step.
  Untested for code.
- **What would make them stop:** a guess: each new rule adds reading, and reading is what made the board
  cost more than the outline (decisions 98, 108).
- **Evidence for, from other fields:**
  - Read-only tests stop test edits but not other cheating. A `flag_for_human_intervention` exit cut GPT-5's
    cheating on impossible tasks from 54% to 9%, though it did less for Claude Opus 4.1 (ImpossibleBench,
    `landscape.md` §8).
  - VeruSAGE's cheat checker cut Verus cheating from 14%, 7% and 2% (by model) to under 1.5%
    (`landscape.md` §8).
  - nf-core's snapshot check is one the agent may regenerate, guarded only by an instruction
    (`landscape.md` §7).
- **Evidence against:** no registered attention comparison Graphene has run showed a gain.
  - The board cost more modelled person-seconds than the outline in studies 2, 3 and 4: on every task in
    studies 2 and 3, and on three of four tasks and in total in study 4, 2,428 against 1,714 (decisions 98,
    99, 108; `docs/test/results-2026-09-28-shaping.md`, `docs/test/results-2026-09-29-board.md`).
  - As registered, the direction took longer than `morning.md` (median 143.9 against 105.4 modelled
    seconds). An exploratory pass after a fix was slightly faster (104.1 against 107.4), which can show a
    direction, not confirm a gain (decision 115).

  These lessons are about checks, not attention, and must be tested on their own.
- **What would show it false:** the tests in §7 find that today's scope and check already catch what the
  lessons target.

## 2. The four conditions, scored per field

The conditions, from the directive:
1. The work splits into a tree a person can read, in their own terms, and shape before anything is spent.
2. Each piece has a cheap check that cannot be faked.
3. Passing the checks means what the person meant, or the gap between the two is small and visible.
4. An agent's attempt costs far less than the person's attention.

"Strong", "partial" and "weak" are judgments from the evidence named in each cell. The field column names
which of the four people (§1) each row is about.

| Field | 1 Tree | 2 Check | 3 Meaning | 4 Economics |
|---|---|---|---|---|
| **Lean mathematics** (the mathematician, the formalization lead) | strong for a Lean reader: blueprints are already dependency trees (leanblueprint, LeanArchitect, Verso Blueprint; `landscape.md` §2), and Graphene's text carried the spike's tree as it is (§3.8). For a reader who does not know Lean, in their own terms: unmeasured (§3.4) | strong once layered, for proofs: no single tool covers the exploit catalog. Build, axioms, kernel replay and a challenge checker together cover its proof-level exploits in the verifiers researcher's matrix, except matcher-auxiliary shadowing (SafeVerify only) and kernel bugs (a second kernel only); no gate catches a dummy or vacuous statement (`landscape.md` §4). Red-teamed on core Lean: every attack that faked a proof was rejected by at least one layer and none by all; a dummy or vacuous statement passes every gate (§3.3) | partial: the gap is the statements and the definitions under them. Human-written benchmark statements were wrong 16–40% of the time, and reviewed ones were still fixed later (`landscape.md` §6). For a reader who does not know Lean: unmeasured (§3.4) | strong in a cost model with labelled assumptions: automation is free; cheap models cost cents per competition leaf; the person's minutes dominate the competition and research profiles, and cost about what the frontier tier does in the textbook one (§3.6). No research-level cost evidence exists for cheap models (§3.6) |
| **Software** (Graphene today, for comparison; the developer) | strong: the plan is a tree under the person's goal sentence, shaped in prose (decision 13) | partial: tests pass wrong code (GPT-5 cheated on 76% of one-off SWE tasks, ImpossibleBench, `landscape.md` §8), and a leaf's scope can include the test that judges it (§7, lesson 1) | partial: the goal is prose, so the gap between passing and meaning is wide; a judgment, not measured here (§7, "The larger lesson") | strong: one live leaf on Nemotron Nano billed $0.000366 (`docs/test/first-light.md`, rung 2); shaping one plan took 293–1,277 modelled person-seconds (decision 98) |
| **Computational biology** (the computational biologist) | strong: pipelines are DAGs already (Snakemake, Nextflow; `landscape.md` §7) | partial: invariants are cheap and catch real errors; interpretation is not checkable (§4.4, the spike) | weak: BRAF V600E and EGFR L858R fail a correct confidence check; 83% of the six-gene slice's sites have no ClinVar pathogenic or benign call (uncertain, conflicting or unclassified; §4.4) | partial: for canonical human proteins the GPU spend is now avoidable (AlphaFold DB v6 and AlphaMissense precomputed; `landscape.md` §7); isoforms, mutant and complex structures still need a GPU (§4.6) |
| **Wet lab** (none of the four; inferred from one cloud lab, `landscape.md` §7) | strong for protocol-level plans only (§4.7) | weak: it holds for format and inventory only; a schema checked each design before it ran, and 2 of 480 plates still ran flawed (§4.7) | weak: a readout is a proxy (§4.7) | weak outside cloud labs: each attempt spends reagents and instrument time (§4.7) |

Section 5 scores ten more fields.

## 3. Mathematics

Everything in this section that was measured ran on 2026-09-30 on one MacBook: Apple silicon, 11 cores,
18 GiB RAM. The versions were Lean 4.34.1 and Mathlib v4.34.1 (rev `d13f23b7`). Several agents built Lean at
once, and swap stood at 13–30 GB used all night. **So a whole process's wall time is this night's, not
Lean's.** Times measured inside one Lean process, after Mathlib was loaded, are much less affected. The
spikes' own READMEs, under `spikes/lean/` (`mechanics/`, `gate/`, `primes/`), give every command and version.

### 3.1 The mapping

| Graphene | Lean | Already done by | What Graphene adds there |
|---|---|---|---|
| **goal** | the target theorems, fixed by the person (`S_root` in `Challenge.lean`) | LeanMarathon's "canonical target statements", written in LaTeX by people; Prove2Me's audited mission goal; a comparator challenge (`landscape.md` §1, §4) | nothing new: the root sentence (decision 13) maps cleanly |
| **leaf** | a lemma whose needs are hypotheses: `theorem leaf : S_need₁ → … → S_leaf` in its own file | Prove2Me's proof-sketches import open children, and "Theorem 4.1 is verified if all imported child lemmas are verified"; LeanMarathon's `sorry_using` nodes (`landscape.md` §1) | the leaf's contract (goal, why, scope, check) told to any executor (decision 17). **Maps cleanly**, and the spike ran it |
| **needs** | the hypotheses a leaf takes | leanblueprint's hand-kept `\uses`; LeanArchitect infers `\uses` from the Lean; Verso Blueprint computes statuses from Lean and, per the researcher's notes on its README and MANUAL, has an `autoDeps` option for inferred edges (`landscape.md` §2) | **Maps with a cost.** Graphene's `needs:` is order (decision 14, HOW_IT_WORKS P1a); in this layout a leaf takes its needs as hypotheses and can be proven first. In the spike `needs:` made 3 of 8 leaves wait for nothing. It costs parallelism, not correctness, and leaving `needs:` out works today (`primes/README.md` §2). LeanArchitect inferred no edge between leaves here, because each names only its needs' statements (`primes/README.md` §4). Graphene adds nothing to the edges: the Lean types carry them, and the sub-goal's check at the roll-up (decision 15) is the integration |
| **scope** | the files, or spans, an agent may edit | LeanMarathon enforces spans with a patched edit tool; AlphaProof Nexus marks editable spans (`landscape.md` §1) | **Maps cleanly:** file-path scope with the boundary at `done`, for any executor (decision 1). One proof file per leaf makes spans unnecessary (§3.2). The spike's true leaf passed the boundary ("nothing outside its scope"); no run tried an out-of-scope write through Graphene (`primes/README.md` §2) |
| **hand-back** | an issue with a witness: a counterexample, a proof of the negation, or `False` from the hypotheses | LeanMarathon's issue template ("do not use a size estimate as issue evidence"); Aristotle's disproofs; NEAR AI's `disproved()`, which demands a Lean proof of `False` from the statement (`landscape.md` §1, §3) | **Breaks today.** `graphene node release --why` refuses only an empty reason (`src/graphene_map/plan.py`, `release`). The spike handed back a leaf `exact?` closes in 0.015 s with "too hard", and Graphene accepted it (`primes/README.md` §2). For the false leaf Graphene offered the wrong fix, "wait on `factor_three_mod_four`" (`primes/README.md` §6) |
| **offer** | a revised statement the person approves, with its effect on the parents | LeanMarathon's Refiner rewrites nodes with no person (`landscape.md` §1); in Prove2Me, editing a draft clears its confirmation (`landscape.md` §1) | **Breaks.** Offers today widen a scope, add a sibling, or wait on the nodes the reason names (decision 32); none changes a statement, and the third was the spike's wrong fix. A statement change is the person's edit (`plan edit`), or a board answer's `then: goal`, which can only append (decision 83). The effect on parents could be computed from the types (an inference; not built) |
| **forks** | several attempts at a leaf; any that passes the gate is valid | pass@k; AlphaProof Nexus's evolutionary search (`landscape.md` §1, §3) | `--forks N`, the check picks, and a second `--model` steps up a size (decision 60). **Maps cleanly:** the gate is the judge. Graphene adds little a prover's own sampling lacks: forks are whole executor runs under one check |
| **the board** | the machine's questions about definitions and conventions, answered by the person | Aristotle's agent questions, with a 15-minute timeout and then "its best guess", with no record that we found (inferred from the client source); LeanMarathon's worker audit asks the model itself; Prove2Me's captain rules, written practice (`landscape.md` §1) | **Maps cleanly in form, and is the one piece no tool found does:** durable questions, before spend, whose answers bind the leaves through `then:` lines (decisions 81–83, 99). Unmeasured for mathematics. In software shaping studies it cost more modelled attention than the outline (decisions 98, 99) |
| **the direction** | the targets file the person owns: the tree may change, the targets may not without the person | Tao's `Challenge.lean`, "the statement of record: 87 lines"; Carleson's 170-line statement file; Tau Ceti's human-owned roadmaps (`landscape.md` §2, §6) | **Maps in part:** the challenge module under `readonly:` (decision 90) plays this role. Graphene's direction (decision 112) stays goals in prose |

### 3.2 The check that cannot be faked

**What must pass, and where.**

| Layer | Runs | What it catches that the layers above miss | Measured cost (tonight) |
|---|---|---|---|
| trusted `lean-toolchain`, `lakefile.toml`, `lake-manifest.json` and challenge, restored or hash-checked first | the fast check (a hash check) and the gate (layer a) | a leaf that edits the toolchain, lakefile, manifest or challenge, which are also outside its scope (decisions 1, 90). Tested against an edited `Challenge.lean` in the gate (`gate/README.md`), and through the real Graphene against an edited `Challenge.lean` and `lean-toolchain`, refused before the check ran (§3.3); the lakefile and manifest follow the same rule and were not run through it | 0.2–0.5 s on core Lean; 30–34 s with Mathlib, nearly all the clone of the trusted `.lake` (`gate/cost.md`) |
| `lake build` of the leaf's module | both | a proof that does not compile. It **passes a `sorry`** (exit 0, a warning) unless run with `--wfail` (rc 1 in 5.6 s) | 153–194 s for one Mathlib leaf; 3.8–5.6 s when Lake finds it built; 0.4–4.6 s in the core-Lean layout (`gate/cost.md`; `mechanics/README.md` rows 3, 5) |
| the type and axioms, read from the **compiled environment** (`GateCheck.lean`): definitionally equal to `S_need₁ → … → S_leaf`, and axioms ⊆ {`propext`, `Classical.choice`, `Quot.sound`} | the fast check, in the agent's loop | a proof of another statement; `sorry` and `admit` (both show as `sorryAx`); a declared axiom; `native_decide`, which on 4.34.1 shows as `<thm>._native.native_decide.ax_1_1` and **not** as `Lean.ofReduceBool`, so a deny-list of axiom names misses it and an allow-list catches it. Run through GateCheck: another statement and `sorry`. By design only, checked with `#print axioms`: `native_decide` and a declared axiom. `admit`: not run here | not timed apart: one Mathlib load, most of the fast check's 32–165 s a leaf (below). Its Gate-file form: 9.3 s with Mathlib still in memory, 0.3–0.6 s on core Lean (`gate/cost.md`). A warm REPL answers a lemma in 0.011 s, but GateCheck in a REPL was not measured, and a REPL is feedback, not a verdict (§3.7; `gate/cost.md`) |
| kernel replay: `lake env leanchecker`, shipped with Lean since v4.28.0 (the archived `lean4checker`) | the gate | a declaration the kernel never checked (`debug.skipKernelTC`, environment forging; run on v4.34.1 in the verifiers researcher's notes, E17–E19, and in lean4's leanchecker tests, `landscape.md` §4; not attacked in the spikes). It passed a changed statement and a `sorry`, as designed | 0.8–2.2 s default / 39.8 s `--fresh` on core Lean; 37 s for one Mathlib leaf; 173–219 s for two or three leaves in one run |
| SafeVerify against the approved `Spec` | the gate | a changed statement; `sorry`; matcher-auxiliary shadowing, which no other tool found catches (`landscape.md` §4) | 1.9–3.9 s a leaf on core Lean; on a Mathlib leaf, stopped before a verdict each time (below) |
| comparator against the person-approved challenge, **in its Linux sandbox** | the gate | a changed or shadowed statement or definition; with its sandbox, a build that writes outside its directory (shown on core Lean only); kernel bugs, with external kernels configured (not run here) | 2.3–14.6 s per leaf on core Lean with real landrun in Docker, + 15–43 s container setup per run; 300 s on one Mathlib leaf without its sandbox (below) |

**Which runs where.**
- **In the agent's loop:** the build plus the environment-level type and axiom check (`primes/check-leaf.sh`).
  - It took 32–165 s a leaf tonight with `import Mathlib` (`primes/README.md` §3, §7). A narrow import
    checked one lemma cold in 1.78 s (median of 5), against 146.6 s for `import Mathlib` (one run), so a
    narrow challenge would likely bring it to seconds (inferred, not measured).
  - It is feedback, not a verdict. It runs unsandboxed, and a proof's build can rewrite the files read
    after it (`mechanics/README.md` finding 6). Its axiom walk, like `#print axioms`, trusts the leaf's own
    `.olean` (finding 2).
  - It is hand-written (64 lines) because no light tool found checks both the type and the axioms;
    SafeVerify and comparator do, at several Mathlib loads each. axiom-audit checks axioms, not the type
    (`landscape.md` §4; not tried). Kimina Lean Server's `is_valid` means no error and no `sorry`, and its
    image pins Lean v4.26.0. The Lean REPL has known false accepts. AXLE is hosted and needs an API key,
    which the rules forbid (`landscape.md` §4; `mechanics/README.md`, "What did not work").
- **At the gate:** comparator in its sandbox, on Linux, and SafeVerify, one leaf at a time, on a machine
  with room; `leanchecker` while it is cheap.
  - The gate is each leaf's check at `done` (all of `gate.sh`, `gate/cost.md`), and the root's at the
    roll-up (decision 15). The spike's leaves were "done" on the unsandboxed fast check instead.
  - SafeVerify stays for matcher-auxiliary shadowing: in LeanParanoia's comparison only it caught it, and
    comparator panicked (`landscape.md` §4).
  - `leanchecker` goes first if the gate is too slow: it passed every negative, and SafeVerify replays the
    same declarations (`gate/cost.md`).
- **SafeVerify** built after a four-line port. It ran on core Lean and rejected the hijack
  (`primes/README.md` §7). On a Mathlib leaf it never finished here.
  - By its source it builds four environments of the import closure per run.
  - Every run on one Mathlib leaf was stopped by a guard before a verdict: swap grew 4.2 GB in 61 s in
    one, 6.3 GB in another (`mechanics/README.md`, "The memory incident"; `primes/README.md` §7).
  - Three Mathlib-loading checks at once took free disk under the night's 15 GB floor, twice.
- **LeanParanoia**, ported to 4.34.1, falsely rejected a correct proof. Likely cause (unverified): it reads
  one `.olean` part per module, while 4.34 splits Init's modules into parts. With `--trust-modules
  Init,Std,Lean` it passes, but it has no reference statement and passed a changed one
  (`mechanics/README.md` finding 7). It is not usable as is.

**Comparator's sandbox is the part that matters, and it did not run on a Mathlib project tonight.**
- Under real landrun in Docker, a proof whose own build rewrites its challenge file was refused
  ("permission denied"; `mechanics/README.md` row 13).
- Under comparator's no-op macOS shim, the same proof passed, *and rewrote the challenge on disk*.
- On Docker Desktop's bind mount (a "fakeowner" filesystem), Landlock denied every file of the Mathlib
  project, so comparator stopped at its first build. Running it would need the toolchain and Mathlib, about
  10.6 GB, on the container's own disk. With the night's disk that was not safe to try.
- The macOS-built Mathlib `.lake` was accepted as is on Linux ("All targets up-to-date (8923 jobs)" in 63 s),
  so one trusted build should serve both (only Lake's up-to-date check ran on Linux).
- **So a real gate for Mathlib projects needs a Linux machine or a larger Docker disk.** That is a
  November item.

**How the statement is protected: the decision.** The four options, weighed with the spikes and the red team
(§3.3):

1. *Each lemma's statement in a read-only file, its proof in a writable one.* This is what today's
   file-path scope already does: the challenge is outside every leaf's scope, or under `readonly:`
   (decisions 1, 90).
   - The boundary refuses an out-of-scope edit at `done` **before the check runs** (HOW_IT_WORKS P2 steps
     2–3), so a leaf's edited lakefile or toolchain never executes under Graphene's check. Shown on the real
     Graphene for `Challenge.lean` and `lean-toolchain`: refused in 0.18 s and 0.17 s, before the check ran
     (§3.3).
   - **Necessary, not sufficient.** The one file a leaf may write can change how anything compiled after
     it is read (next point), and can run code while it builds (`mechanics/README.md` finding 6).
   - What git ignores is outside every scope: the `.lake` a check borrows or clones, and the tools, can be
     edited between runs (HOW_IT_WORKS P5; `gate/README.md`, "Limits"; `primes/README.md` §3).
2. *A check that compares the elaborated statement with the approved one* (comparator, SafeVerify).
   **Needed.**
   - The spike's first fast check compiled a trusted gate file after importing the leaf. A leaf that
     declared `macro "S_false_leaf" : term => `(True)` and a louder `#print axioms` made that gate print a
     clean axiom line, exit 0, for a proof of `1 = 2`.
   - SafeVerify and comparator both rejected it. So did the rewritten fast check, which reads the compiled
     environment instead of parsing a file (`primes/README.md` §3, §7).
3. *Scope at the level of a declaration or a span.* **Not needed** in this layout: one proof file per
   leaf. It would become needed only if leaves had to share a file, Mathlib-style. Nothing tonight asked
   for it.
4. *Statements as `Prop`-valued definitions in a read-only challenge module that holds every definition
   they use; one proof file per leaf; each leaf proves `needs → statement`.* **The layout.** The spike ran
   the fast check and the gate's layers (a)–(d) on all eight leaves and the root, composed by application,
   with `Proofs/Root.lean` written from the tree and never by a leaf. SafeVerify and comparator did not run
   on this tree (`primes/README.md` §7).

**Decision: option 4 as the layout, protected by option 1 (today's scope) and checked by option 2: a check
that reads the compiled environment in the agent's loop, and the sandboxed gate as each leaf's check.**
- *Why:* on the cases the spikes ran, each layer closes something the others leave open. The core-Lean
  hijack was rejected by SafeVerify, comparator and GateCheck (`primes/README.md` §3, §7). A proof that
  rewrites its challenge was refused under real landrun (`mechanics/README.md` finding 6). A changed
  statement and a `sorry` failed the core gate (`gate/README.md`). The red team's attacks that faked a proof
  were each rejected by at least one layer and none by all, and a stored axiom list altered after compilation
  fooled `#print axioms` but not comparator or SafeVerify, so the verdict comes from their own walk (§3.3).
- **So the answer to "does today's file-path scope plus a check command already give full protection" is:
  no new Graphene feature was needed for this layout, but full protection is not shown.** It can hold only
  if the check command brings a sandbox around everything that loads candidate code (landrun on Linux,
  `sandbox-exec` on macOS) and a trusted `.lake` no leaf can write. A naive check (compile a gate file;
  grep for `sorry`) is fakeable from inside the leaf's own file. Not shown yet:
  - Comparator in its sandbox never ran on a Mathlib project.
  - The trusted `.lake` and the tools outside git are unguarded between runs (`gate/README.md`, "Limits").
  - Without a sandbox, a leaf's own build rewrote the challenge at check time, which the boundary does not
    see (`mechanics/README.md` finding 6). On macOS `gate.sh`'s `sandbox-exec` profile stopped it, and
    nobody has reviewed that profile (`gate/README.md`).
- What no gate closes: a vacuous statement, a dummy definition, intent (§3.4), and a kernel bug without a
  second kernel (`landscape.md` §4). Untested: code that runs when a checker imports a leaf, and a shared build
  changed by one check and reused by the next (§3.3).


### 3.3 The red team

`spikes/redteam/`: 21 attacks, each the smallest change that tries to fake a proof, run against seven
layers. A read-only critic then checked the record against its own logs, and a second round tested one
hole the first left open.
- **Core Lean, not Mathlib.** It ran on a core-Lean copy of the layout of §3.2, because every layer per
  exploit on Mathlib would not fit this machine's memory (§3.2). Most attacks are mechanisms of Lean's
  elaborator, kernel or tools, not of Mathlib. On Mathlib only a few were run: `sorry`, a changed
  statement, a challenge edit, the gate-file hijack and a proof that writes files (the review in
  `spikes/redteam/README.md`).
- **Where the list came from.** It started from LeanParanoia's test suite and OEIS Open's attack list
  (`landscape.md` §3, §4).
- **Predictions first.** They were written before the run (`spikes/redteam/PREDICTIONS.md`).

R rejects it, P lets it through, n/a could not run. "Scope" is Graphene's boundary.

| # | attack | scope | build | fast check | leanchecker | comparator | SafeVerify | LeanParanoia |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 01–05 | `sorry`, `admit`, a declared axiom, `native_decide`, `implemented_by` with `native_decide` | P | P | **R** | P | **R** | **R** | **R** |
| 06–07 | `set_option debug.skipKernelTC true`; a theorem added by metaprogramming (`addDeclCore`) | P | P | P | **R** | **R** | **R** | **R** |
| 08–10 | a `sorry` hidden in an `opaque`, in `debug.byAsSorry`, in a helper lemma | P | P | **R** | P | **R** | **R** | **R** |
| 11 | an unused `unsafe def` beside an honest proof (fakes nothing) | P | P | P | P | P | **R** | P |
| 12 | the gate-file hijack: a macro makes `S_target` mean `True`, and a louder `#print axioms` prints a clean line | P | P | **R** | P | **R** | **R** | P |
| 13 | a namespace shadow used through `show` (fails to build in any layout) | P | **R** | n/a | n/a | n/a | n/a | n/a |
| 14 | an unused local notation and instance beside an honest proof (fakes nothing) | P | P | P | P | P | P | **R** |
| 15 | code that runs while the proof compiles (an honest proof whose compile-time `#eval` writes a file) | P | P | P | P | P | P | P |
| 16 | editing `Challenge.lean` | **R** | P | P | P | P | P | P |
| 17 | editing `lakefile.toml` (its payload never took effect) | **R** | P | P | P | P | P | P |
| 18–19 | editing `lean-toolchain`; pointing `lake-manifest.json` at a fork | **R** | n/a | n/a | n/a | n/a | n/a | n/a |
| 20 | a dummy structure standing in for missing theory (a true, non-vacuous statement) | **R**\* | P | P | P | P | P | P |
| 21 | a vacuous statement | **R**\* | P | P | P | P | P | P |

\* Scope rejected 20 and 21 only because the red team put the defect in `Challenge.lean`, where a leaf may
not write. If the tree's author writes the same defect into the approved tree, every layer lets it through.

**What it shows:**
- **No single layer rejects every faked proof.**
  - `#print axioms` says "does not depend on any axioms" for a declaration whose kernel check was skipped
    (06, 07); only a kernel replay catches those.
  - `leanchecker` passes `sorry` and every declared axiom (01–05, 08–10), because it replays and does not
    judge.
  - comparator and SafeVerify pass a rewritten challenge (16): editing `Challenge.lean` alone was enough,
    because they compare a solution with *its* challenge. **They protect the statement only when the
    challenge is pinned out of the leaf's reach.**
- **Round two:** a compiled module's stored axiom list, altered after compilation, fooled `#print axioms` in
  a compiled gate file (`gate.sh`'s layer (c)). GateCheck, SafeVerify, comparator and LeanParanoia caught
  it (`spikes/redteam/round2/`). So a layer that reads the stored list is never the verdict. comparator's
  or SafeVerify's own walk over the proof is.
- **Shadowing: the layout helps, and the test was thin.** The statement is a constant in `Challenge.lean`,
  elaborated before any leaf exists; a leaf cannot redeclare it, and GateCheck checks the exact name and
  definitional equality. But 13 fails in any layout and 14 shadows nothing, so the variant that matters,
  a leaf declaring its own shadow of `S_target` or `Doubles`, was not tried.
- **Graphene's boundary works as designed, and in the right order.**
  - An edited `Challenge.lean` or `lean-toolchain` was refused by `graphene node done` in 0.18 s and 0.17 s,
    before the check ran; an in-scope `sorry` was refused by the check in 7.1 s.
  - `done` refuses a tracked change outside the scope before it runs the check (`finish` in
    `src/graphene_map/plan.py`). So a leaf-written lakefile or toolchain never executes under Graphene's
    check.
  - Only these two out-of-scope edits went through the real Graphene. The lakefile and manifest rows follow
    from the same rule, and were not run through it.
- **Graphene's check is itself an attack surface (15).**
  - An honest proof whose file also ran a compile-time `#eval` wrote a file outside the repository while
    `graphene node done` compiled it, and Graphene reported "done (check passed, nothing outside its scope)".
  - A local check runs in a throwaway worktree, not a sandbox (`run_check` in `plan.py`); the same is true
    of a test file for code.
  - A sandbox around the build denied the write. The profile tested was the red team's own; `gate.sh`'s
    narrower one was not run on it. **The sandbox belongs in the check command.**
- **Open, not tested** (`spikes/redteam/round2/README.md`): code that runs when a checker imports a leaf's
  module, and a shared build changed by one check and reused by the next. What would close both: a sandbox
  around every step that loads candidate code, and a trusted build no check can write.

**Kill criterion 4** (`PREREG.md`: "any exploit passes the whole gate and no check command closes it"):
- **For faked proofs, not met.** Every attack that fakes a proof was rejected by at least one check command
  in the gate.
  - The sandbox is part of the check command (15). A lakefile or toolchain edit is also refused before the
    check by the boundary, or by the gate's trusted-inputs step outside Graphene (16–19).
  - Caveats: this rests on core Lean; comparator's real sandbox never ran on Mathlib; and the two hazards
    above are untested.
- **For wrong statements, it cannot be met by any gate.** 20 and 21 are honest proofs of statements that
  do not say what was meant. No check command can close them, by the directive's own third condition.
  What catches them is before spend: falsification (the worked tree's vacuity test flagged a vacuous leaf
  in 0.15 s, §3.4, though no falsifier flags a true, non-vacuous dummy like 20), and the person.
- **This plan's reading:** kill criterion 4 does not fire on tonight's evidence. It is a decision for Alex
  whether the untested hazards and the Mathlib gap must be closed before November's pilot. The
  recommendation is yes, as milestone A of `LEAN_DIRECTIVE_DRAFT.md`.

### 3.4 The person's part

**Is reading a lemma tree cheaper than writing it?**
- *For a reader fluent in Lean:* probably yes. The published ratios of review time to writing time are
  about 0.4 (PutnamBench: 10 against 25 minutes) and 0.29–0.64 (IndiMathBench, one annotator) (`landscape.md`
  §6). Reviewed statements still fail later, though: 27.8% of PutnamBench's double-checked statements later
  received fixes (187 of 672; a third-party count, not confirmed by the maintainers).
- *For a reader who knows the mathematics and not Lean:* **we found no measurement.** The nearest, a 7-person
  2025 study, measured tool-assisted formalization, not review against writing (`landscape.md` §6). That is
  the pilot's kill criterion 2 (`PREREG.md`), and the question the whole mathematician persona rests on.

**What makes statements reviewable for the second reader, and which of those are checks.**
- **Checks** (they can fail mechanically, and a failure is evidence):
  - a counterexample search, which is one-sided;
  - `decide` on bounded instances;
  - a vacuity test ("the hypotheses cannot all hold"), one-sided;
  - a non-vacuity witness ("here is an example where every hypothesis holds"), the only one that shows the
    hypotheses can hold;
  - person-approved examples and non-examples as test lemmas. Formal Conjectures keeps 467 test statements;
    AlphaProof Nexus proved the first terms of each OEIS sequence first (`landscape.md` §1, §6).
- **Aids** (they help a person judge and prove nothing):
  - English beside the Lean;
  - a model's back-translation. Judges are unreliable: 97% "correct" by an LLM judge against 66% by
    humans, on the same statements (`landscape.md` §6);
  - the board's convention questions;
  - the "suspiciously easy" alarm.

**What the machine catches cheaply, measured tonight** (`spikes/lean/primes/README.md` §6, times inside Lean
after Mathlib loaded):

| Seeded defect | Caught by | Time | Not flagged by |
|---|---|---|---|
| **false:** "every odd n > 1 has a prime factor that is 3 mod 4" | `plausible` on a bounded restatement written by hand (`∃ p ≤ n`): **n = 5**; `decide` proved the bounded form false for n < 30 | 0.142 s; 0.042 s | `plausible` on the statement as written ("Failed to create a `testable` instance": the unbounded `∃`); automation (8 tactics fail, 2 time out at 60 s; a failure is not a counterexample) |
| **off-by-one:** `(4P − 1) % 4 = 3` without `0 < P` (ℕ subtraction) | `plausible` as written: **P = 0**; `decide` for P < 10 | 0.064 s; 0.002 s | automation (9 tactics fail, `try?` times out) |
| **vacuous:** hypotheses `n % 4 = 3` and `n % 2 = 0` | the vacuity test: `omega` proves no n meets both | 0.150 s | `plausible` (cannot test it); every falsifier, since there is nothing false to find. **Automation "proves" it** (omega, 0.07 s), inside the range of the honest leaves that close (0.015–0.58 s) |

- **No single check caught all three.** The machine's catches are a portfolio.
- **The bounded rewrite was written by hand** (`Falsify/Run.lean`). In a real run a planner model, or a rule
  that bounds an `∃ p` with `p ∣ n` by n, would have to write it. Neither was tried, and a model call is spend.
  The rewrite is equivalent to the original only by a fact (a divisor of a positive n is at most n) that a
  person or a proof has to accept.
- **The "suspiciously easy" alarm cannot stand alone:** four leaves closed in under a second, and three of
  them were honest (`euclid_mod_four`, `dvd_factorial`, `mul_one_mod_four`). Only the vacuity test told the
  vacuous one apart.
- **This is a textbook tree over ℕ.** Mathlib has no Plausible instance for ℝ or ℂ that we found
  (`landscape.md` §6), so cheap falsification will be weaker for analysis.

**What only the person catches is intent:**
- which theorem, and how general: the tree states the root two ways, "for every n a larger prime" and "the
  set is infinite", and which one was meant is not a fact about Lean;
- conventions that make a statement true for the wrong reason (`ContDiff ℝ ⊤` is analytic; a non-summable
  `tsum` is 0);
- whether a machine's restatement is faithful.

**Which reader can do what** (inference; no reader was tested):
- The machine's catches need no Lean from either reader. A counterexample comes in the statement's own
  variables (n = 5, P = 0), and a hand-back whose witness a check verifies is settled by the kernel.
- Accepting a restatement (the bounded rewrite above) and judging that the Lean says what the English says
  both need Lean. The Lean-fluent reader can do both; the other reader has only the aids.
- A hand-back with no witness ("too hard") gives the second reader nothing to judge; the first can at least
  try the leaf.

In the record, the best catches combine a machine flag with a person's verdict (`landscape.md` §6):
- after Formal Conjectures' September model audit began, 225 misformalization fixes were merged in 23 days,
  and 139 of the 144 closed audit issues were closed as completed (GitHub counts);
- Tao's "suspiciously easy", then a human review;
- a counterexample search, then expert repair (MechGeo).

**What a hand-back looks like when a lemma is false.** The spike's, verbatim from Graphene:

> false as stated, so no proof exists. Counterexample n = 5: 5 is odd and > 1, its only prime factor is 5
> (5 = 5), and 5 % 4 = 1, so no prime factor of 5 is 3 mod 4. Found before any proof attempt: plausible on
> the bounded form (∃ p ≤ n) found n = 5 in 0.14 s …; decide proved the bounded form false for n < 30 in
> 0.04 s; the negation is proved in Falsify/Run.lean (odd_factor_three_false, standard axioms). … What
> holds instead: n % 4 = 3 in place of n odd, which is factor_three_mod_four, already in the plan.

**What keeps it from becoming an escape hatch.**
- Accept a proof leaf's hand-back as "false" only when a witness passes the same gate as a proof: a Lean
  file proving `¬ S_leaf`, or `False` from the hypotheses. The spike's `odd_factor_three_false` is such a
  witness (it compiles with the standard axioms; it was not run through the gate).
- "Budget exhausted, no defect found" is a separate status that does not block, and is never a hand-back
  to the person. This is LeanMarathon's rule, made mechanical.
  - In both cases found, a size or difficulty exit was gamed: LeanMarathon's line budget ("exceeds 1000
    physical lines", at nearly one issue per worker PR), and the Grothendieck project's "blocked" and
    "genuine mathlib gap", which its prompts had to forbid (`landscape.md` §1, §6).
  - In one mathematician's project (VML, 220 Aristotle jobs), the commonest non-success was a sorry after
    the budget: 66 jobs (30%), median 5.6 hours (arXiv 2603.15929 §6.2, `landscape.md` §6).
- **Graphene today accepts "too hard".** `release` refuses only an empty reason (`src/graphene_map/plan.py`),
  and the spike's agent handed back a leaf `exact?` closes in 0.015 s with `--why "too hard"`
  (`spikes/lean/primes/README.md` §2; §3.8). So hand-backs are one of the two places the mapping breaks;
  `needs:` is the other, and leaving it out works around it (§3.1). §6 row 2 orders the fix.

### 3.5 The landscape, and where Graphene differs

The directive's first look found a harness without a person (LeanMarathon). The research found
**people's layers too**, which the directive does not mention (`landscape.md` §1, §2):

| System | The person's part | What it lacks that Graphene would add |
|---|---|---|
| **Prove2Me** (hosted; used for Anthropic's FLT) | the captain clicks to confirm each core statement; a blind read-back in LaTeX; statements immutable; proof-sketches = needs → statement | machine-generated convention questions before the audit; a private repository and budget; several executors cheapest first |
| **Verso Blueprint** (Lean FRO, 2026) | owners, priorities, statuses computed from Lean, an agent work-queue | a statement-freezing gate; spend control; hand-backs with witnesses |
| **Tau Ceti** | people own roadmaps and review rubrics; AI writes and reviews all code | per-statement sign-off; Prove2Me's paper says Tau Ceti "explicitly disavows frontier results" |
| **LeanMarathon** (research harness) | people write the LaTeX targets; nobody approves a Lean statement | the approval, a statement-level gate (its CI has no `#print axioms` and no comparator, and bans axioms by keyword, which the `"ax" ++ "iom"` trick seen on FormalQualBench would likely defeat; not tested on LeanMarathon), and a question channel |
| **Aristotle** (free today) | agent questions with a 15-minute timeout, then "its best guess" | a durable record; a guarantee that given statements come back unchanged (FormalQualBench excluded its results for lack of comparator validation) |
| **Tao's Sendov practice** (a general agent plus discipline) | an 87-line `Challenge.lean` as "the statement of record", compared under `pp.all` | nothing a Lean-fluent person needs, in our judgment. This is what Graphene competes with for such readers |

**Where Graphene is redundant:** decomposition, parallel leaves, falsification by the executor, span scope,
the gate itself (comparator is going into the Lean distribution). **Where it is the missing piece, as far as
anyone found:**
- the machine's convention questions put to the person **before** spend, with answers that bind the leaves;
- one layer across executors (Aristotle, an open model, a frontier agent), cheapest first, with the person's
  own budget and repository;
- a hand-back whose witness one check verifies, the same way for every executor. Single harnesses already
  demand witnesses (LeanMarathon's issues, NEAR AI's `disproved()`; `landscape.md` §1, §3);
- the same layer for software.

None of these has been measured on a real person.

**The rest of the landscape, placed** (`landscape.md` §1–§4):

| What | Where it sits for Graphene |
|---|---|
| Gauss (closed), AxiomProver (no public access), AlphaProof Nexus (results only, no agent code), OpenGauss (MIT; needs Claude Code or Codex) | harnesses: redundant with decomposition and proving. Only OpenGauss could be driven as an executor today |
| DeepSeek-Prover-V2, Kimina, Goedel-Prover-V2, Pythagoras, Leanstral 1.5 (Seed-Prover released no weights) | single-goal provers: executors for a leaf. Graphene adds nothing to them |
| LeanDojo (v1 deprecated, v2 needs a CUDA GPU), LeanCopilot (~5.5 GB of models) | tools for a person working in Lean. The layer does not need them |
| Lean REPL, Kimina Lean Server, AXLE (hosted, API key) | fast feedback in the agent's loop. None is a gate: Kimina's `is_valid` checks no axiom or statement, AXLE does not replay the environment, and the REPL has an open false accept |
| Mathlib's review (3,128 open PRs, 689 awaiting review) | its bottleneck is reviewers for shared library code; Graphene reviews the person's own statements. No overlap, in our judgment |
| miniF2F, ProofNet, PutnamBench (saturated); OEIS Open, Formal Conjectures, FrontierMath Erdős, LeanEval, AnnalsChallenge, ArXivLean (held out) | test sets. The pilot takes its prover-side targets from LeanEval, post-cutoff papers (ArXivLean's method) and blueprint open nodes (`PREREG.md`) |

**What the person adds, and whether Graphene is the cheapest way to add it.** The directive's four candidates:

| Candidate | Evidence it matters | Cheapest way found today | Graphene |
|---|---|---|---|
| **intent:** which theorem, how general | Erdős #728 was proved in the small-C version when a large C was meant (`landscape.md` §6); the spike's root is stated two ways (§3.4) | a Lean-fluent person writes the challenge (Tao's 87 lines); otherwise Prove2Me's captain confirms each statement against a blind LaTeX read-back | the same act (`plan edit`, a sign-off); not shown cheaper |
| **conventions** (the board) | `ContDiff ℝ ⊤` is analytic, caught by an expert (VML) and by "a thirty-second #check" (Miller); a non-summable `tsum` is 0, found by LeanMarathon's reviewer agent (`landscape.md` §1, §6) | an agent's own audit; Aristotle asks for 15 minutes, then guesses | the one piece no tool found does: questions before spend whose answers bind the leaves (§3.1). Unmeasured |
| **judging the machine's flags** | Formal Conjectures' audit, Tao's "suspiciously easy", MechGeo (§3.4) | an issue tracker (Formal Conjectures files audit issues) | a place for the verdict in the record; not a cheaper verdict |
| **reshaping a tree that drifts** | VML's hypotheses crept to 42, then back to 12; Carleson's statements, constants and definitions changed on the way; LeanMarathon's Refiner rewrites targets that Stage 2 never re-audits (`landscape.md` §1, §2, §6, Corrections) | Prove2Me clears a statement's confirmation when it is edited | an agent's change is a proposal that binds nobody until the person accepts it (HOW_IT_WORKS P1); statements under `readonly:` (decision 90). The spike's tree never drifted, so this is untested; `PREREG.md` counts restarts |

**Verdict:** Graphene is not shown to be the cheapest way to add any of the four. Against Tao's practice (a
Lean-fluent reader, a general agent and a `Challenge.lean`) it would add only the board and the record, in our
judgment. Against Prove2Me it would add the board, a private repository and budget, and several executors.
Whether that is worth the person's minutes is what kill criteria 1 and 2 measure (§3.9).

### 3.6 Models and cost

Sources: `landscape.md` §1 (LeanMarathon), §3 and §5. The arithmetic is in `models/`: `python3 cost_model.py`
and `python3 reprice_near.py` (`models/README.md` says what each prints). The rest was measured here.

- **Token Factory hosts no Lean prover.** Its public catalog lists 25 models, and "lean", "prover" and
  "theorem" occur 0 times. It is general open models only: DeepSeek, Qwen, Kimi, GLM, Nemotron, GPT-OSS,
  and also MiniMax, Hermes, Gemma and MiniCPM.
  - **An open prover could run there only as custom weights on a dedicated endpoint.** For fine-tuned models,
    "Deployment options currently only include via Dedicated endpoints", billed per GPU-hour, and custom
    weights are "in beta and available on request".
  - **Fine-tuning is a separate question:** most open provers are Qwen fine-tunes whose bases Token Factory
    can fine-tune (Goedel-Prover-V2, Kimina, Pythagoras); DeepSeek-Prover-V2-7B's and Leanstral's bases it
    cannot.
  - **Price: not public** (a login wall). The nearest public figure is Nebius AI Cloud's on-demand H200 at
    $4.50 an hour. Goedel-Prover-V2-32B needed 2 H200s in one study, so about $9 an hour, a proxy only.
    Whether that beats serverless per attempt depends on keeping the endpoint busy (inference).
- **Token Factory publishes no cached-input price.** Agent loops are mostly cached input: 99.3% of NEAR AI's
  PutnamBench input tokens (`reprice_near.py`; `landscape.md` §3 quotes ~99.8%), at least ~93% of
  LeanMarathon's (`landscape.md`, Corrections). NEAR's run cost $111.85 as its `costs.tsv` reports it, with DeepSeek's cache prices. Our
  repricing of the same tokens at Token Factory's list prices for DeepSeek-V4-Flash-0731 and DeepSeek-V4-Pro
  is $11,527, about 100 times more (`reprice_near.py`). **Short whole-proof sampling suits the cheap tier
  there; long agent loops do not, until cached input is priced.**
- **The cascade, per leaf:**

  | Tier | Cost |
  |---|---|
  | automation | $0, and closed 3 of 8 leaves here in under 1.5 s each |
  | a cheap open model | whole-proof sampling: Nemotron 3 Super under $0.01 per correct miniF2F proof on Token Factory. An agent loop: open DeepSeek V4 solved all 672 PutnamBench problems at a $0.04 median with DeepSeek's cache prices; at Token Factory's list price the same single-run solves cost a median of $0.19 and a mean of $0.83 (637 solves; our count from the same `costs.tsv`) |
  | a frontier harness | $2.32–$6.05 per new proof node at GPT-5.5 API-equivalent prices (LeanMarathon; the directive's "$2–6" holds, $4.15 pooled; `cost_model.py`) |
  | Aristotle | $0 in fees: its terms, last modified 2026-09-24, say "Harmonic does not presently charge fees"; it trains on customer data unless the person opts out |
  | the person | the rest |

  **Expected cost of a proven leaf through the cascade** (`cost_model.py`; every leaf ends proven, because
  the person closes what reaches them). The person's rate ($100 an hour) and minutes per leaf, and every
  success rate without a named source, are assumptions:

  | Leaf profile | Expected | Of which the person | Frontier first | Person only |
  |---|---|---|---|---|
  | textbook | $0.56 | $0.24 (the frontier tier $0.27) | $5.32 | $50 |
  | competition (Putnam-like) | $10.30 | $8.55 | $65.64 | $300 |
  | research (LeanMarathon-like) | $28.53 | $24.70 | $44.15 | $400 |

  - The **person's minutes dominate the competition and research profiles**; in the textbook profile the
    frontier tier and the person cost about the same. A cascade is worth what it keeps from the person, not
    what it saves in tokens.
  - The textbook profile assumes automation closes 60% of leaves. On the spike's tree it closed 3 of 8,
    37.5% (`models/README.md`).
  - **We found no research-level cost-per-proof evidence for cheap models on Token Factory.** The numbers
    found are on benchmarks (miniF2F, miniCTX, PutnamBench), heavily studied and at risk of contamination. The
    nearest is Leanstral 1.5 (open weights, not on Token Factory) on FLTEval, built from real FLT pull
    requests: pass@8 43.2 (a secondary source).
- **The fit with the Sandbox pattern** (`landscape.md` §5; nothing touched a Sandbox):
  - **Disk:** the toolchain measured 2.7G on macOS and 3.0 GB on Linux, and Mathlib's `.lake/packages`
    7.6G (`du -h`, which counts in GiB). If all are GiB, Linux needs about 10.6 GiB of the 12 GiB default
    writable layer, about 1.4 GiB spare, before `~/.cache/mathlib` (448 MB), the project's own build, and
    any REPL or checker build (`spikes/lean/mechanics/README.md`).
  - **Set-up once works on Linux aarch64 in Docker:** the macOS-built `.lake` was accepted there as is. On a
    Sandbox, whose CPU and RAM are not documented, it is untested.
  - **Fork many works for files, not for a warm server:** "Process memory, running services, and network
    state are not preserved". Every fork pays a cold Mathlib load.
  - **Measured cold and warm, on this loaded machine:**

    | Check | Time |
    |---|---|
    | `import Mathlib`, cold | 146.6 s (quieter) to 326 s (median of 5, under load) |
    | a narrow import | 1.78 s |
    | a warm REPL, after its one-time 347 s import | 0.011 s per lemma |

  - So a Lean executor on Sandboxes should batch a tree's leaves in one instance with a warm REPL, not
    fork one instance per check.

### 3.7 The spike: predictions beside results

Each prediction was written, with its time, before its measurement: `spikes/lean/primes/PREDICTIONS.md`,
`spikes/lean/mechanics/PREDICTIONS.md` and `spikes/lean/mechanics/install/predictions-install.md`. The times
are the writers' own; the files were committed after the runs. The red team's are in `spikes/redteam/PREDICTIONS.md` and
`spikes/redteam/round2/PREDICTIONS.md`; several first-round rows were confirmed in scratch runs before
they were written down.

| Measurement | Predicted | Happened |
|---|---|---|
| toolchain download and size | 1–3 min, 0.8–1.6 GB | 17 s, **2.7 GB** |
| Mathlib cache fetch and size | 2–6 min, 4–7 GB | 81 s (with `lake update`), 7.6 GB, 8,908 files; `~/.cache/mathlib` 448 MB |
| first `lake build` of a one-file project importing Mathlib | 10–40 s | **260 s** (`Spike.Basic` 148 s, `Spike` 106 s: reading the `.olean` files) |
| `lake build` of a leaf with `sorry` | rc 0 with a warning | rc 0, "declaration uses `sorry`"; `--wfail` makes it rc 1 |
| `#print axioms` of `native_decide` | `Lean.ofReduceBool` | **`withNative._native.native_decide.ax_1_1`**: a deny-list by name would pass it |
| one-lemma check, cold (`import Mathlib`) | 120–240 s | median 326 s under load; 146.6 s quieter; **1.78 s with a narrow import** |
| the same, warm REPL | 0.1–1.5 s per lemma | **0.011 s** (median of 5) |
| comparator with its real sandbox, Mathlib project in Docker | pass the positive, fail the negative | **could not run:** Landlock denies Docker Desktop's bind mount. On the core-Lean layout, verdicts as predicted; 2.3–14.6 s per leaf (predicted < 10 s), plus 15–43 s of container setup |
| `gate.sh` on the primes tree, all nine, then one leaf | every layer passes (80%; 75% for one leaf) | layers (a)–(d) pass on all nine; **no SafeVerify or comparator verdict:** both runs were stopped for memory (`primes/README.md` §7) |
| whole theorem under automation | closes under nothing (85%) | closes under nothing, both forms; `exact?` did not find Mathlib's Dirichlet corollary |
| leaves closed by automation | 2–4 of 8 | **3 of 8**, each under 1.5 s |
| hammers (Duper, Canonical, LeanHammer) | LeanHammer not installable (90%) | LeanHammer fails to build on 4.34.1; Duper and Canonical built and **closed 0 of 14**; Canonical "closes" with `sorry` by design |
| the false leaf, before spend | a counterexample in under 2 s on a bounded form | n = 5 in 0.142 s, on a bounded form written by hand; `plausible` cannot test the statement as written |
| Graphene on the tree text | accepted (65–70%) | **accepted as it is**; `plan --text` gave it back unchanged once its own `#` notes, blank lines and `?` marks are normalised |
| the red team, 21 attacks × 7 layers | a layer for each attack (some after scratch runs) | the matrix agreed with the written predictions; the review found five of its claims wrong, not its cells (§3.3) |
| round two: an altered stored axiom list | fools `#print axioms` and GateCheck (85%); comparator catches it | `#print axioms` fooled; **GateCheck not fooled**, for a reason not established; comparator, SafeVerify and LeanParanoia caught it |

### 3.8 The worked tree

**Infinitely many primes congruent to 3 mod 4**, Euclid's proof, 8 leaves under one sub-goal
(`spikes/lean/primes/tree.txt`, the file Graphene was given):
- **The convention that bites is ℕ subtraction.** `4 · 0 − 1 = 0`, so two leaves need `0 < P`, and the seeded
  off-by-one drops it.
- **It is already in Mathlib**, as a corollary of Dirichlet's theorem (`Nat.forall_exists_prime_gt_and_modEq`):
  the spike tests mechanics, not a prover. `root_by_dirichlet` closes the root in one application. **No
  tactic found it.** Mathlib states it with `Nat.ModEq` and `ZMod`, not `% 4`, which is probably why (a guess,
  not tested).
- **Graphene accepted the text as it is:** as an agent's proposal (`plan propose`) and as the person's edit
  (`plan edit`, with the precedent of decision 95 in a scratch clone). `plan --text` gave it back unchanged
  once its own `#` notes, blank lines and `?` marks are normalised; every prose line, Unicode included, came
  back byte for byte. `needs:` made three of the eight leaves wait (`factor_three_mod_four`, `euclid`,
  `set_form`), though each takes its needs as hypotheses and could run at once.
- **Of eight Lean-flavoured variants, four were refused:**
  - `needs:` naming a Mathlib lemma instead of a node;
  - a prose line beginning with "- " (a minus sign, as a mathematician writes one), read as a child node, so the next key line was refused;
  - `test:`;
  - a leaf with only its Lean statement.

  Four were accepted as prose: a `theorem` line, a `statement:` line, a docstring, a numbered list.
- **Through Graphene's `done`** (the leaf's own check, `check-leaf.sh`, not the gate of §3.2): the false leaf's
  `done` was refused ("uses axioms beyond the standard three: sorryAx") by the check's first version, the one
  the spike later showed could be faked; a true leaf's passed the final version ("check passed, nothing
  outside its scope"). They took 15 and 7 minutes tonight: Graphene's fresh worktree pays three Mathlib loads.
- **The hand-backs** (`spikes/lean/primes/README.md` §2, §6):
  - the agent handed back `dvd_factorial`, which `exact?` closes in 0.015 s, with `--why "too hard"`, and
    Graphene accepted it: `release` refuses only an empty reason (`src/graphene_map/plan.py`);
  - for the false leaf's hand-back, which carried its witness, Graphene offered "make odd_factor_three wait
    on factor_three_mod_four" (decision 32's third offer). Waiting cannot repair a false statement;
  - both showed with the same glyph and word, so today's Graphene cannot tell a hand-back with a witness from
    one without.
- **No gold-standard verdict exists for this tree.** The gate's layers (a)–(d) passed on all nine; SafeVerify
  and comparator never reached a verdict, stopped for memory (§3.7). The gold-standard check ran only on the
  mechanics spike's three-node tree: comparator with its sandbox on core Lean, and without it on a Mathlib
  leaf (§3.2).
- **The three forms round-trip** as follows:
  - Graphene text → the Lean challenge, mechanically (`tree2lean.py`, with Graphene's own parser; `diff`
    empty).
  - Lean → text: argued from the files, not run. It would lose the goal sentence, owners, sign-offs, state and
    the board.
  - Text → LeanArchitect: written by hand. A script would map id, title and `needs:` to label, title and
    `uses`, but LeanArchitect infers no edge between leaves in this layout, only root → leaves.

| Goal | closed by (time) |
|---|---|
| the whole theorem, either form | nothing (10 tactics) |
| `euclid_mod_four` (ℕ subtraction) | omega 0.08 s, grind 0.18 s |
| `dvd_factorial` | exact? 0.015 s (it is `Nat.dvd_factorial`) |
| `mul_one_mod_four` | grind +suggestions 0.58 s, try? 1.49 s |
| `prime_mod_four`, `factor_three_mod_four` (the key lemma), `not_dvd_euclid`, `euclid` (the argument), `set_form` | nothing; the key lemma timed out at 60 s under grind +suggestions and try? |

**The zero-spend test of the thesis holds only in its weak form.** The whole theorem fails and three of eight
leaves close for $0. The leaves that carry the proof, the key lemma and the argument, still need a prover or
a person. "Most leaves close" did not happen.

### 3.9 The evaluation design

`PREREG.md`, committed before any evaluation run. In short:
- **Arms:** A end to end; B a machine tree with automated review and cheap falsification; C the same tree
  shaped by the person. All on one existing executor, and C starts from B's very tree.
- **Metrics:** targets proven through the gate; cost at list price; misstatements that reached compute;
  restarts; the person's effort, counted and timed.
- **Targets:** seeded defects of the five kinds, placed blind. Held-out targets on the prover's side;
  familiar ones on the person's side.
- **Power:** a 10-to-12-target pilot cannot show an effect. It takes 80–120 targets to see C win 15 points
  more than it loses.
- **Kill criteria:** the directive's five, three made precise with their reasons before any data: unseeded
  statements for kill criterion 1; cost as model and compute dollars, with the person's minutes reported
  beside, for kill criterion 3; Aristotle compared on time, not dollars, for kill criterion 5.

## 4. Biology

### 4.1 What a leaf and its check would be

Graphene should not be another workflow engine. Snakemake and Nextflow run the steps. nf-core validates
inputs with nf-schema and tests pipelines with nf-test, but its testing spec says "It is OK for a test to
produce nonsense output, or find 'nothing', as long as the tool does not crash or produce an error"
([nf-core module testing](https://nf-co.re/docs/specifications/components/modules/testing); `landscape.md` §7). If
Graphene enters, it wraps the pipeline the person already has.

**Who is already here** (`landscape.md` §7):
- Nextflow 26.08.0-edge has an `agent` primitive, as a preview. Its design record lists as unaddressed the
  enforcing of validation tiers ("the most consequential unaddressed item") and a diff of the registered plan
  against what ran ("Nothing implements the comparison"); cost and token budgets are non-goals.
- Claude Science (Anthropic, beta since 2026-06-30) drafts a plan, asks before reaching new resources, submits
  to the person's HPC over SSH and runs a reviewer agent. Seqera AI's CLI executes commands "with your
  approval" and writes nf-tests.
- NVIDIA's BioNeMo Agent Toolkit keeps its validation and "Blocking Conditions" in skill files the agent
  reads, so they are advisory. nf-core/agents tells agents they "MUST NOT edit snapshots manually" but lets
  them regenerate snapshots: an instruction, not a mechanism.
- Inference: Graphene's difference would be checks the agent cannot edit, a person-shaped tree with explicit
  sign-off nodes, and the plan-against-run diff. None of the products read claims all three; each is a
  feature request away.

A leaf is one step or one claim of that pipeline. Its checks can be:

| Kind | Example | Exit code? | Evidence |
|---|---|---|---|
| reproducing a known control | KRAS G12D, TP53 R175H, R248Q and R273H come out likely pathogenic; benign polymorphisms come out benign | yes | the spike: 10 of 11 controls pass (§4.4) |
| schema and range | samplesheet schema; RSA in [0, 1]; row counts | yes | nf-schema does the samplesheet part; range and row-count checks on outputs would be written as check commands (not in the spike) |
| free invariants | the sequence the variants are numbered on equals the sequence of the structure used; each stated wild-type residue matches | yes | per-variant wild type: the spike, 17 of 6,227 records mismatch, all explained (§4.4). Per-protein sequence identity: not in the spike; a researcher's KRAS run caught 32 of 32 mis-numberings with it, against 16 of 32 for the wild-type check (§4.3) |
| statistical sanity bounds | the fraction of sites under pLDDT 70; flag rates per gene | yes, with a threshold someone chose | none in the spike. Its check 3 is a per-site threshold (exit 1 if any site is below 70) that reports the fraction without gating on it |
| agreement with a reference | AlphaMissense class against ClinVar | yes: exit 3 means a sign-off is needed, and it never exits 1; disagreement is **flagged, not failed** (today's Graphene treats exit 3 as a fail, §4.5) | the spike, check 4: 76 of 1,038 flagged |

### 4.2 What breaks

- **Long jobs.** A Graphene check has a 30-minute cap, the making of its worktree included
  (`docs/HOW_IT_WORKS.md` P2, step 3). An AlphaFold run on a cluster does not fit. The job belongs to the
  executor. Whether an executor that submits a SLURM job and waits for hours works today is **not tested**.
- **Data too big for git.** A check runs in a worktree of the leaf's state as git sees it, and what git
  ignores is not there (HOW_IT_WORKS P2, step 3). The spike's `data/` is git-ignored. From the code, not run
  under Graphene: its checks would find no data and exit 2.
  - What today's Graphene should allow, also from the code and not tested: the check reads data from a path
    outside the repository (reads are never scoped, decision 8) and first verifies it against SHA-256
    hashes committed with the check (the spike's `inputs.sha256`).
  - The spike showed why that verification matters. Deleting the 16 failing KRAS records made check 1 on
    KRAS pass; only the pinned hashes in `inputs.sha256` caught it.
- **Plausible rather than right.** This is the third condition. §4.4 (the spike) shows it.
- **Provenance.** A leaf's record keeps who held it, what git changed, what was refused and the last 2,000
  characters of the check's output (`TAIL` in `src/graphene_map/plan.py`, line 35). The spike's list of 76
  flags was 8,459 characters. The evidence for a sign-off has to be a file in the leaf's scope, committed
  with it, not the log.

### 4.3 A case Alex knows: the 2023 variant pipeline (a thought experiment)

What I know: in 2023 Alex ran an AlphaFold and NetSurfP pipeline on HPC that classified over 10,000 oncogenic
protein variants. **Every other detail below is an assumption, marked A1 to A9, for Alex to confirm or
correct.**

NetSurfP-3.0 is **sequence-based**. It predicts solvent accessibility, secondary structure and disorder from
ESM-1b embeddings, not from a structure
([NetSurfP-3.0, NAR 2022](https://academic.oup.com/nar/article/50/W1/W510/6596854); `landscape.md` §7).
Which version Alex used is not known (see the list below). Inference: if it was 3.0, AlphaFold and NetSurfP
give two largely separate views of burial and disorder, and comparing them is a cheap check.

**The tree Graphene would have proposed** (A1: the variants came from a public source such as COSMIC,
ClinVar or OncoKB as protein changes on RefSeq or MANE transcripts):

```
goal: classify >10,000 oncogenic variants (A5: missense) by predicted structural effect (A6)
question: which isoform is each gene numbered on, and is it the one the structures use?  [q-isoform]
    default: MANE Select for numbering; refuse any variant whose protein differs from the structure's
    option: UniProt canonical for both, and re-number the variants
question: model the mutants, or read the wild-type structure at the site?  [q-mutants]
    default: wild type only (AlphaFold is not validated for mutation effects)
    option: model every mutant (GPU hours; A3)
- inputs are sound  [inputs]
  - parse the variant list to (gene, transcript, position, wild type, mutant)  [parse]
      check: every protein's numbering sequence equals the structure's sequence; every wild type matches
  - pin sequences and structures by release and hash  [pin]
      check: shasum -a 256 -c inputs.sha256
- structures  [structures]
  - wild-type structures: AlphaFold DB where it has them, AlphaFold on the cluster where not (A2)  [af-wt]
      check: structure sequence = input sequence; per-residue pLDDT recorded
- features  [features]
  - NetSurfP on wild type (A7: and mutant) sequences  [netsurfp]
      check: schema and ranges; one row per variant
  - confidence at the site  [site]
      check: pLDDT >= 70 at every site, exit 1 if any is below; the fraction below reported per gene
- classification  [classify]
  - apply the classification rule  [rule]
      signoff: the scientist, on the rule's biological meaning (A4)
  - controls come out as the method says  [controls]
      check: named hotspots and benign polymorphisms, evidence from an independent source
  - agreement with a reference (A9: whether 2023 compared with one)  [agree]
      check: report agreement; write disagreements to a file for sign-off
- the record (A8: for a methods section)  [record]
      check: every tool version, database release and threshold is in provenance.json
```

**Which checks would have caught real mistakes.**
- The numbering check is the one with evidence behind it. The two measurements below were run tonight by a
  researcher, beside the spike; their scripts and how to rerun them are in `spikes/bio/research/` (M1 and
  M2), and the data they read is public and not committed.
- MANE against UniProt (no prediction written first): MANE v1.5 (`MANE.GRCh38.v1.5.summary.txt.gz` and
  `.ensembl_protein.faa.gz`) against UniProt release 2026_03 (REST search `(organism_id:9606) AND
  (reviewed:true)` with `xref_mane-select`). Of 18,599 MANE Select transcripts that a reviewed UniProt entry
  cross-references, **1,017 (5.47%)** encode a protein different from that entry's canonical sequence, KRAS
  and EZH2 among them (`landscape.md` §7, MANE row).
- KRAS (a prediction was written first, in the researcher's working notes): ClinVar esearch `KRAS[gene] AND
  "missense variant"[molecular consequence] AND single_gene[prop]` (235 records) against AlphaFold DB's
  AF-P01116-F1 model and its AlphaMissense `-hg38.csv`. ClinVar numbers on K-Ras4B while UniProt canonical,
  the AlphaFold DB model and its AlphaMissense file are K-Ras4A. Joining by the protein-change string gave
  13 of 213 KRAS missense SNVs **a different codon's score, with no error raised**, four of them pathogenic
  or likely pathogenic in ClinVar (`landscape.md`, "Corrections the research made").
- In the same run, the directive's wild-type check caught only 16 of the 32 mis-numbered KRAS variants. A
  per-protein sequence-identity check, or a join on genomic coordinates, caught all 32. That is why
  `[parse]` above checks both.
- **Whether the 2023 pipeline had this problem depends on A1 and A2.** Which transcripts, and which
  structures?

**Where Graphene would have saved attention.**
- `[q-isoform]` puts the isoform decision to the scientist once, before the results are used, and before any
  GPU hour if any were spent (A2, A3).
- `[q-mutants]` puts the most expensive choice up front. A **guess** made tonight for a run that models
  every mutant: about 5 models per variant at 1 to 3 GPU-minutes each (Jumper et al. 2021, "around one GPU
  minute per model for 384 residues") gives 800 to 2,500 GPU-hours, $3,000 to $11,000 at Nebius H100 prices
  of $3.85 now and $4.50 from 2026-10-01, before MSA CPU time. Separately, the AlphaFold DB FAQ says AlphaFold
  "has not been validated for predicting the effect of mutations" (quoted through Pak et al. 2023, Europe
  PMC PMC10019719, because the FAQ page could not be fetched), and Pak et al. found "very weak or no
  correlation between AlphaFold output metrics and change of protein stability or fluorescence". That is
  why the default models wild type only (`landscape.md` §5 and §7).
- If the results were published (A8), the record answers the methods section's questions without
  reconstructing them.

**Where it would have cost attention.**
- Writing the checks: the whole spike, checks included, took an agent about 25 minutes (00:50 to 01:15).
  Guess: a person would take longer.
- The sign-off queue: 76 flags in six genes. For 10,000 variants the flags must be summarised by cause, or
  nobody reads them.
- If any step ran longer than 30 minutes or read data git ignores, Graphene's check cap and data rules
  (§4.2) would have forced workarounds.

**Nodes only a scientist can sign off, and on what evidence.**
- The isoform per gene: expression data and the literature, e.g. EZH2's Y641/Y646 naming
  ([CIViC](https://civicdb.org/variants/165), read through a search summary; `landscape.md` §7).
- Whether a structural feature measures the claimed effect: benchmarks of AlphaFold on mutations (Pak et
  al. 2023, above).
- The thresholds (pLDDT, RSA, the AlphaMissense cut-off). ClinGen's calibration puts the supporting-evidence
  line at 0.792, not the developer's 0.564
  ([Bergquist et al. 2025](https://www.ccs.neu.edu/home/radivojac/papers/bergquist_genetmed_2025.pdf);
  `landscape.md` §7).
- Which reference axis to compare against: germline pathogenicity or somatic oncogenicity.
- What counts as a control.
- How to read each disagreement.

**What Alex must confirm.**
- A1, the source and transcripts of the variant list.
- A2, whether structures came from AlphaFold DB or were computed, and on which cluster.
- A3, whether mutants were modelled.
- A4, the classification rule.
- A5, whether the variants were missense only.
- A6, whether they were classified by predicted structural effect, and into which classes.
- A7, whether NetSurfP ran on mutant sequences as well as wild type, and which NetSurfP version.
- A8, what the results were used for: a publication with a methods section, or something else.
- A9, whether the pipeline compared its calls with controls or a reference such as ClinVar.
- Whether any error was found after the fact, and how.
- Which lab ran it, and whether they would talk.

### 4.4 The check spike (it ran: `spikes/bio/`)

- **What it covered:** six cancer genes (TP53, KRAS, BRAF, PIK3CA, EGFR, PTEN) and all 6,400 of their
  ClinVar missense SNV records. It used UniProt 2026_03 sequences, AlphaFold DB v6 models and AlphaMissense
  from AlphaFold DB, with cancerhotspots.org as independent evidence for the controls.
- **Cost:** no GPU, no key, no spend. 65 s and 22 MB cold, and 2.5 s for all four checks once cached.
- **Records:** every command, version and license is in its README, and every prediction was written before
  its run in `PREDICTIONS.md`.

| Check | Result | Why |
|---|---|---|
| 1. wild type matches UniProt canonical and the AlphaFold model | 17 of 6,227 fail (0.27%): KRAS 16, BRAF 1 | KRAS: ClinVar numbers on K-Ras4B, UniProt and AlphaFold on K-Ras4A; they diverge at residue 151. BRAF: an 807-residue RefSeq isoform. None is a data error. 173 more records (2.7%) could not be checked, most of them missense only on another isoform; all are reported by reason, not dropped |
| 2. controls | 10 of 11 pass | PIK3CA H1047R, the commonest PIK3CA hotspot, scores 0.538 (ambiguous, under 0.564). The method, applied as stated, does not reproduce this control |
| 3. pLDDT ≥ 70 at the site (exit 1 if any site is below) | 1,672 of 6,210 sites fail (26.9%) | runs of low-confidence residues (inference: disordered termini and linkers), and **BRAF V600 (49.1) and EGFR L858 (51.2)**: two of the best-known actionable cancer variants fail a correct confidence check |
| 4. agreement with ClinVar | 962 of 1,038 classified sites agree (92.7%); 76 flagged for sign-off | Among the 76, in overlapping groups: 20 rest on expert-panel records (8 TP53 benign calls AlphaMissense disputes); 17 PIK3CA pathogenic variants (mostly overgrowth-syndrome records) scored ambiguous or benign; 3 start-codon changes, which AlphaMissense scores as substitutions (likely benign) although their effect is loss of the start codon; 43 on weak records; 12 below pLDDT 70 |

**Predictions beside results** (`PREDICTIONS.md`; written at 00:53, P2b at 01:00, before the runs they
predict).

| Prediction | Result |
|---|---|
| P0: about 6,400 records, at least 97% parsable | 6,400; 97.3% |
| P1: under 3% fail the wild-type check; KRAS 5–25%, from about residue 151 | 0.27%; KRAS 7.5%, residues 153–188 |
| P2: all 8 positive controls likely pathogenic, exit 0 (guess: a miss would be PIK3CA H1047R or EGFR L858R) | exit 1: H1047R ambiguous; the guess held |
| P2b: the negative controls likely benign (guess: one ambiguous); at least 90% of hotspot alleles likely pathogenic | all 3 benign; 96.4% |
| P3: 10–15% of sites below pLDDT 70; exit 1 on every gene | 26.9%, about double; exit 1 on every gene |
| P4: 15–25% of classified sites flagged; about 70% unclassified; exit 3 on every gene | 7.3% flagged; 83.3% unclassified; exit 3 on every gene |

**What it shows about the conditions.**
- **Condition 2: cheap, yes.**
- **Condition 2: cannot be faked, only with pinned inputs.** In an uncommitted copy of the spike, deleting
  the 16 failing KRAS records fooled check 1 on KRAS; only the pinned hashes in `inputs.sha256` caught it.
- **Condition 3: no.** Every check is correct as written, and a pipeline that passes them all still drops
  BRAF V600E from structural interpretation. It still compares against a germline axis where the commonest
  named traits of BRAF's pathogenic records are RASopathies (non-small cell lung carcinoma is on 11 of
  119), and it has no reference for the 83% of this slice's sites that ClinVar leaves uncertain,
  conflicting or unclassified.
- The gap is visible only because the checks report counts, causes and flags, not one bit.

**What it did not test:** a cluster, a GPU, a long job, a reference-build question (everything was
protein-level), NetSurfP, or anyone's attention.

**How a biology step would be judged: not designed.** `PREREG.md` covers mathematics only. The spike's
discipline is a start: predictions written before each run, and control evidence from a source independent
of the method (cancerhotspots.org), which its README calls the biological version of a pre-registration.
Proposal: replay a pipeline whose errors are already known, the 2023 one if the lab recorded what it found
after the fact, and count which errors the checks catch before the results are used and how many flags a
scientist reads to get there. That needs the lab (§8).

### 4.5 What would have to change in Graphene, with today's Graphene tried on paper

The middle column is read from the code and docs; none of it was run under Graphene.

| Need | What today's Graphene does | Where it fails |
|---|---|---|
| scope over data and compute budgets | scope is git paths (HOW_IT_WORKS P1); data outside git can be read (decision 8), and a check can verify it against hashes committed with it (the spike's `inputs.sha256`) | no budget per leaf for cluster hours; the night's ledger (decision 102) counts Token Factory calls and ConTree operations, not cluster or GPU hours |
| a sign-off as an explicit kind of check | `signoff:` stops a node in `review` after its check passes (decision 6) | only exit 0 passes (`run_check` in `plan.py`), so "exit 3: needs a sign-off" is just a failure; an unconditional sign-off asks for review even with no flags |
| executors that submit a job and wait hours | `graphene run` waits for the executor's process (HOW_IT_WORKS P4); the check runs after | not tested; the check itself is capped at 30 minutes (HOW_IT_WORKS P2 step 3) |
| provenance in the record | commits, check tail, scope verdicts (HOW_IT_WORKS P6) | 2,000 characters of output; data versions only if the leaf commits a provenance file |

**Nothing here should be built before the mathematics pilot reports.**

### 4.6 Nebius AI Cloud and NVIDIA's hosted models

Sources: `landscape.md` §5 (Nebius prices) and §7.

- **Nebius GPUs.** On-demand H100 is $3.85 an hour, rising to $4.50 on 2026-10-01
  ([prices](https://nebius.com/prices)).
- **Managed Soperator (Slurm).** The service itself is free, but worker GPUs "require capacity block groups
  that reserve GPUs", arranged through a Nebius manager. Inference: not a pay-as-you-go path for a first test.
- **Serverless AI Jobs.** One container per job, per-second billing and a timeout. Inference, not tested:
  this maps onto an executor that submits and waits.
- **NVIDIA's hosted biology NIMs** (AlphaFold2, OpenFold2 and 3, Boltz-2 and others on build.nvidia.com) need
  an NGC key. NVIDIA's NIM FAQ (forum, 2024-09-11) calls the API catalog as a whole "a trial experience …
  designed to serve evaluation and prototyping needs only".
- **The first test needs neither.** For canonical human proteins, AlphaFold DB v6 already has the model and
  AlphaMissense scores, under CC BY 4.0. Inference: a GPU becomes worth it for isoforms AlphaFold DB lacks,
  for mutant and complex structures (where AlphaFold's validity for mutation effects is itself doubtful,
  §4.3), and for cluster-scale NGS.

### 4.7 Wet lab

It does not fit now. The strongest 2026 example is a GPT-5-driven cloud lab that tested 36,000 reaction
compositions on over 580 plates and cut the specific cost ($/g protein) of cell-free protein synthesis by 40%
against the state of the art
([OpenAI and Ginkgo](https://cdn.openai.com/pdf/5a12a3bc-96b7-4e07-9386-db6ee5bb2ed9/using-a-gpt-5-driven-autonomous-lab-to-optimize-the-cost-and-titer-of-cell-free-protein-synthesis.pdf);
`landscape.md` §7). Its pre-execution check was a Pydantic schema over plate layouts and volumes. Even so,
two of 480 plates ran flawed: a model overwrote a required volume, and a unit bug left wells with only
glucose and ribose. That is Graphene's pattern in miniature, a cheap check before spend and a defect turned
into a new check. But it held only inside "a predefined operational envelope of Ginkgo's cloud laboratory"
(one assay, cell-free protein synthesis), and the lab's own validator is what did it. On the four
conditions (inference):
- The tree holds for protocols.
- The check holds for format and inventory, not for biology.
- A readout is a proxy, so passing is not meaning.
- Outside cloud labs, each attempt spends reagents and instrument time, so it is not cheap next to attention.

Dual-use risk is one more reason to stay out: agentic scaffolds such as Biomni and K-Dense helped with
dual-use tasks that base models block ([BioVeil MATRIX](https://arxiv.org/abs/2605.00927); `landscape.md` §7).

## 5. Other fields

One line each. The scores are the other-fields researcher's judgements, strong, partial or weak on the four
conditions in order; "(inference)" marks a score that rests on the researcher's reasoning, not a source. The
evidence is in `landscape.md` §8. Only verified software and SQL rewrites touch one of the four people (§1),
the developer; every other row would need a new person, and none is proposed in §8.

| Field | Tree, check, meaning, economics | Verdict |
|---|---|---|
| Numerical methods (manufactured solutions, convergence order) | strong (inference), strong, strong at the leaf (the equations are the gap), strong at small scale (inference) | **Closest fit outside mathematics (inference: no study of person-shaped trees or of agents gaming MMS was found).** In a blind test the method caught 10 of 10 order-of-accuracy mistakes among 21 seeded ones ([SAND2000-1444](https://www.osti.gov/biblio/759450)). The manufactured solution must stay out of the agent's reach |
| Verified software (Dafny, Verus, Lean; no Coq source read) | strong, strong only with a cheat checker and read-only specs, partial, strong | **The bridge back to Graphene's users.** Without a cheat checker, models cheated on 2–14% of tasks; with one, under 1.5% ([VeruSAGE](https://arxiv.org/abs/2512.18436)). About 9% of "successes" rested on specs that were too weak ([vericoding](https://arxiv.org/abs/2509.22908)) |
| Data analysis | strong (the forking paths are the tree), weak, weak, strong | **Partial fit.** Pruning before spend is pre-registration: 96% against 44% positive results, a correlational comparison ([Scheel et al.](https://research.tue.nl/en/publications/an-excess-of-positive-results-comparing-the-standard-psychology-l-2/)). No known check settles an inference: agent analyses with opposite conclusions passed human expert review 78% of the time ([2607.01507](https://arxiv.org/abs/2607.01507)) |
| Backtested trading | partial (inference), weak, weak, "strong" is the harm | **The warning.** A leaky oracle with a Sharpe ratio of 35 survives deflated-Sharpe and overfitting tests; under honest evaluation every LLM-found strategy failed ([2608.27734](https://arxiv.org/abs/2608.27734), a single-author preprint). One idea transfers: a complete ledger of every attempt |
| Hardware RTL (formal equivalence) | strong (inference), strong with a golden model, strong for re-implementation, partial (inference) | **Good where a golden model exists.** 66% of equivalence failures were errors in the spec, not the code ([VeriThoughts](https://arxiv.org/abs/2505.20302)) |
| SQL rewrites and migration | partial (inference), partial, strong for rewrites, strong | **Good for rewrite and migration leaves.** An optimizer-based verifier proved about 37% of LLM rewrites equivalent, and about 32% changed results ([CIDR 2026](https://www.vldb.org/cidrdb/papers/2026/p33-narasayya.pdf)) |
| Compilers (translation validation) | partial, strong, strong, strong | **A strong fit, but narrow.** Trivet settled 147 of 148 LLVM transformations ([2609.19583](https://arxiv.org/abs/2609.19583)). Few users, mature tools (inference) |
| Cryptographic protocols (Tamarin, ProVerif) | partial (inference), strong given the model, weak to partial, partial (inference) | **The model's fidelity is the gap.** Tamarin's manual has modellers prove exists-trace lemmas first, a vacuity test by practice ([manual](https://tamarin-prover.com/manual/master/book/010_modeling-issues.html)) |
| Legal compliance (Catala) | partial, weak, weak, partial | **Not now.** LLM translation of law to code has had no great success so far, and checking relies on lawyer–programmer pairs ([Catala book](https://book.catala-lang.org/en/4-1-general.html)) |
| Chemistry and materials (DFT agents) | partial, partial, weak, partial | **Like biology.** An unguarded run got a nearly correct answer with only 81% of its essential steps succeeding ([2507.14267](https://arxiv.org/abs/2507.14267)) |

The pattern across fields: where the check becomes exact, **the reference is the bug**.
- In text-to-SQL, the gold SQL was wrong "more often than not" in a 50-query sample
  ([SpotIt](https://arxiv.org/abs/2510.26840)).
- Alive2's work led to eight patches to the LLVM Language Reference
  ([Alive2](https://users.cs.utah.edu/~regehr/alive2-pldi21.pdf)).
- In hardware, spec errors outnumbered code errors four to one: 66% against 16% of 50 failures
  ([VeriThoughts](https://arxiv.org/abs/2505.20302)).
- In Lean benchmarks, 16.4% of miniF2F's and 38.5% of ProofNet's human-written statements were wrong
  ([ReForm](https://arxiv.org/abs/2510.24592)); 31.8% of ProofNet's Lean 4 entries by a separate count
  ([ProofNet#](https://arxiv.org/abs/2406.07222); `landscape.md` §6).

Hardware, SQL and compiler verification show the directive's third condition this way, as Lean benchmarks
do. It says where the person's attention belongs.

## 6. What Graphene would need, in order, smallest first

Each item says what was tried with today's Graphene first, what the change would prove, and the result
that would justify building it. **Nothing here is built by this run.** The first build step is
`docs/process/directives/LEAN_DIRECTIVE_DRAFT.md`. Smallest first means by the change to Graphene: none
for 0 and 1, a convention before any change for 2, a prompt for 3, the parser for 4, and what `needs:`
means for 5.

| # | What | For (§1) | Tried with today's Graphene | What it would prove | Built only if |
|---|---|---|---|---|---|
| 0 | **Nothing, to carry a Lean tree.** The layout of §3.2; the challenge out of every scope or under `readonly:`; each leaf's check is `check-leaf.sh`, the fast check (build, type and axioms). The full `gate.sh` was not run through `node done`: on this tree it never finished (stopped for memory), and it needs the project one directory below the repository root (`spikes/lean/primes/README.md` §7) | the mathematician, the lead | `plan propose` and `plan edit` accepted the tree as it is, and `--text` round-tripped it; `node done` refused the false leaf ("sorryAx") and passed a true one (`spikes/lean/primes/README.md` §2). An out-of-scope edit was not tried under Graphene: the boundary refuses one at `done` by design (decision 1; HOW_IT_WORKS P2 step 2), and the gate's layer (a) refused an edited `Challenge.lean` inside the check (`spikes/lean/gate/README.md`) | that today's Graphene holds a Lean tree | (done tonight, with the fast check only) |
| 1 | **A check that is cheap enough.** A trusted `.lake` shared by the check's worktree; a narrow import in the challenge; a warm Lean server for the agent's loop. All of it lives in the check script and the executor, not in Graphene | the mathematician, the lead | each `done` took 7–15 minutes tonight: the fresh worktree pays three Mathlib loads (§3.8). A narrow import checked a lemma in 1.78 s (median of 5) against 146.6 s for one `import Mathlib` run at 02:30 (326 s, median of 5, earlier in the night; `spikes/lean/gate/cost.md`) | that a gate per leaf costs seconds to a minute, not a quarter hour | the first build step measures the gate per leaf above Graphene's 30-minute check cap (`CHECK_TIMEOUT = 1800` in `src/graphene_map/plan.py`; HOW_IT_WORKS P2 step 3), or above the attention it saves |
| 2 | **A hand-back that must carry a witness**, for proof leaves. First as a contract line and a `--witness FILE` convention the check verifies; as a Graphene change (`release` refusing a proof leaf's reason with no witness, and no "wait on" offer for a disproof) only later | the mathematician, the lead; the developer (§7, lesson 4) | `release --why "too hard"` was accepted for a leaf `exact?` closes in 0.015 s. The false leaf's witness-carrying hand-back got the offer "wait on `factor_three_mod_four`", which cannot repair a false statement (`spikes/lean/primes/README.md` §2, §6) | that every hand-back names a defect, and that false leaves come back as disproofs | the first build step, which records every hand-back (`LEAN_DIRECTIVE_DRAFT.md` D; and `PREREG.md`'s hand-back count, added before any run), shows hand-backs with no witness, or an executor takes the free-text exit on a leaf another executor proves |
| 3 | **Board questions from a conventions catalog** for Lean trees: ℕ subtraction, `tsum` of a non-summable series, real `sSup` and `limsup`, `ContDiff ⊤`, `deriv` and `∫` off-domain, `Nat.card` of an infinite type, "sufficiently large", density, induced subgraphs. Each has a documented 2025–26 failure (`landscape.md` §1 and §6): ℕ subtraction in Lean-GAP; `tsum`, `sSup` and `limsup` in LeanMarathon and Prim; `ContDiff ⊤` in Ilin and Miller; `deriv`, `∫` and `Nat.card` in PutnamBench 2005 A3, 1967 A4 and 1977 B6; "sufficiently large" and induced subgraphs in Formal Conjectures (Erdős 510 and 128); density in AlphaProof Nexus (Erdős #125, #741). A planner prompt addition, not code | the mathematician | not tried: no planner ran tonight, and no board question was written by hand. The spike's tree carried its one convention, ℕ subtraction, as a sentence in the leaf's goal, the form decision 99 gives an assumption the planner is sure of (`spikes/lean/primes/tree.txt`) | that the person answers once what would otherwise reach compute wrong | kill criterion 2 does not fire for at least one reader, whether or not 1 does (`PREREG.md`, "What earns the next phase": when 1 fires, the convention questions are what is kept), or the board's convention questions catch a seeded convention defect |
| 4 | **Grammar for mathematicians:** a prose line may begin with `- ` (a hyphen-minus, read today as a child node); a `uses:` key that names Lean or Mathlib declarations, recorded but not ordering | the mathematician | four refusals, each by its line (§3.8). Two are these; the other two, `test:` and a leaf with no scope and no check, ask for what every leaf needs and should stay | that a mathematician's text is accepted as they write it | a person hits them |
| 5 | **`needs:` as meaning, not order**, where a leaf takes its needs as hypotheses | the lead | not tried. By decision 15 the sub-goal's check (`./check-leaf.sh Root`) would do the integration if `needs:` were left out; `tree.txt` kept `needs:`, and the roll-up never ran (1 of 9 leaves done; `spikes/lean/primes/README.md` §2). Leaving it out costs the dependency record, and LeanArchitect then has no edges between leaves | full parallelism with the dependency kept | a tree where the waiting costs real time; tonight `needs:` made 3 of 8 leaves wait (§3.1), and what that cost was not measured |
| — | declaration- or span-level scope | the lead | not needed: one proof file per leaf | — | leaves must share files |
| — | for biology: a sign-off exit code, data outside git, checks that wait hours (§4.5) | the biologist | exit 3 is a plain failure today; data is absent from the check's worktree | that a scientist's judgement is a recorded sign-off, not a failed check | the biology conversation in November finds a pipeline that wants it |

## 7. What this teaches the software product

Five lessons from Lean. Each names what Graphene does today, where that stops, and the test that would show
whether the lesson changes anything for code. None was tried on code tonight: each "Today" line is read from
the code and the decisions, not run. The tests run on the four software tasks' fixed trees
(`docs/test/trees/`), which are not made yet: each needs the live planner, a key and a capped spend
(decision 128; `docs/test/trees/README.md`). Nothing here is built before 30 October.

**1. The check reads nothing the agent can write.**
- *Lean:* the statement lives in a module no leaf may edit, and the gate compares the proof against it
  (§3.2). The exception is the trusted build outside git (`.lake`, `GATE_TOOLS`), which an executor running
  as the same user can still edit between runs (`spikes/lean/gate/README.md`, "Limits I know of").
- *Today:* scope keeps a leaf off every path outside its globs (decision 1), and `readonly:` keeps named
  globs off every leaf (decision 90). Unless the person sets a `readonly:` glob over the tests, a leaf's
  scope may include the test its own check runs, and the planner is told each leaf's check can be its own
  test file (`src/graphene_map/sizing.py`), so the executor can edit the test that judges it.
- *Elsewhere:* read-only tests stop test edits but not special-casing, and hiding the tests brings cheating
  near zero at a cost in performance ([ImpossibleBench](https://arxiv.org/abs/2510.20270)). nf-core lets an
  agent regenerate its own snapshot tests, guarded only by an instruction (`landscape.md` §7).
- *The test:*
  1. Over the fixed trees, count the leaves whose check reads a file inside their own scope.
  2. For each, run a scripted executor that edits that file so the check passes, and count what Graphene
     lands.
  3. If it lands any, the rule "the files a check reads are read-only to the leaf it judges" has earned a
     place.

**2. A check is attacked before it is trusted.**
- *Lean:* the spike's first fast check was faked from inside a leaf's own file (a macro made a proof of
  `1 = 2` print a clean axiom line), and was rewritten to read the compiled environment. Through the gate,
  SafeVerify and comparator rejected the same hijack; layer (c) and `leanchecker` passed it
  (`spikes/lean/primes/README.md` §3, §7). The red team's 21 attacks: no single layer
  rejected every faked proof, and a stored axiom list altered after compilation fooled `#print axioms`
  (§3.3).
- *Today:* `graphene plan precheck` runs each check on the untouched commit and flags one that passes already
  or cannot run (decision 94): a proposed leaf's check only in a sandbox fork, and automatically only with
  `GRAPHENE_SHAPE=precheck` (`src/graphene_map/precheck.py`). That catches a vacuous check, not a weak one.
- *Elsewhere:* a cheat checker cut Verus cheating from 2–14% to under 1.5% (`landscape.md` §8).
- *The test:*
  1. A mutation pass. For each leaf, a scripted executor lands a wrong but plausible change: delete the body,
     return a constant, skip the new branch.
  2. The leaf's check runs on it. A check that passes a mutant is weak.
  3. The share of weak checks on the fixed trees is the number, before and after the planner is told about
     it.

**3. Falsify before spending.**
- *Lean:* on the machine's bounded rewrite of the false leaf, `plausible` found its counterexample (n = 5) in
  0.14 s and `decide` refuted it for n < 30 in 0.04 s, times inside Lean after Mathlib loaded; a person, or a
  proof, has to accept the rewrite. A vacuity test flagged the vacuous leaf in 0.15 s (`spikes/lean/primes/README.md`
  §6).
- *Today:* precheck tests the check, never the goal (decision 94). Nothing tries a leaf's goal on an example
  before an executor is paid.
- *The test:*
  1. Seed false goals of known kinds into the fixed trees: a wrong default, a unit mix-up, a boundary the
     paragraph excludes.
  2. Count how many a cheap property run (hypothesis-style generation from the goal's own examples) catches
     before any executor starts, against how many reach an executor.

**4. A hand-back names a defect.**
- *Lean:* LeanMarathon's workers gamed a size-based "cannot formalize" rule (a budget of Lean lines), filing
  blocked-node issues "at nearly one block per Worker PR". A charter and issue template that allow an issue
  only on a concrete defect took size-based issues from 14 to 0
  ([2606.05400](https://arxiv.org/abs/2606.05400) §4.7). That fix is in the prompt and the template; no gate
  rejects a size-based issue (the researcher's reading).
  - A counterweight: ImpossibleBench's `flag_for_human_intervention` exit *cut* GPT-5's cheating from 54% to
    9% (`landscape.md` §8), though it did less for Claude Opus 4.1
    ([2510.20270](https://arxiv.org/abs/2510.20270)).
  - So a hand-back must exist, and must carry evidence.
- *Today:* a leaf comes back with offers built from what it tried to write outside its scope (decision 32),
  or with the cause when it could not work at all (decision 68). `graphene node release --why` takes any
  reason that is not empty; it accepted "too hard" (`spikes/lean/primes/README.md` §2).
- *The test:*
  1. Classify every hand-back in the recorded runs: does its reason name a file, a line, a failing input or
     a missing need?
  2. Then give an executor a "hand back if the task is too big" line on leaves another executor finished, and
     count how often it takes the exit.

**5. The machine asks; the person answers.**
- *Lean:* convention questions have short, checkable answers that change a statement a gate then enforces
  ("is this series summable?").
- *Today:* the board puts up at most three items (decisions 81, 99, 107, 108). Three stand-in studies (2, 3
  and 4; study 1 never ran) found the board costs more modelled attention than the outline: on 4 of 4 tasks
  in studies 2 and 3, and on 3 of 4 in study 4 (decisions 97, 98, 99, 108;
  `docs/test/results-2026-09-29-board.md`).
- *The test:* rerun study 4's board-against-outline design (`docs/test/results-2026-09-29-board.md`) on the
  fixed trees, with the board's items split by whether their answer changes a check (`then: check`) or only
  a goal's prose (`then: goal`; HOW_IT_WORKS P1d), and compare modelled seconds per split. The Lean pilot's
  kill criteria 1 and 2 (`PREREG.md`) measure the person's statement review, not this, and need a person.

**The larger lesson** is the one hardware, SQL and compiler verification repeat in §5, as Lean benchmarks
do. Where the check is exact, the reference is the bug (sources in §5):
- 16.4% and 38.5% of the human-written statements in two Lean benchmarks were wrong;
- spec errors outnumbered code errors four to one in hardware;
- in text-to-SQL, the gold SQL was wrong more often than not in a 50-query sample.

For code, that says the person's attention belongs on a leaf's goal and check, the spec, more than on its
diff. That is Graphene's bet already (`docs/DIRECTION.md`, "What Graphene is"), and it is unmeasured on real
people: the board studies used Claude stand-ins (decisions 98, 108).

## 8. The phases

### Before 30 October: at most a day, and only if it helps the submission

**Goal.** A rerunnable demo of tonight's spike that a judge can watch in two minutes. It shows:
1. the whole theorem failing under automation;
2. three leaves closing for $0;
3. the false leaf coming back with its counterexample, n = 5, before any proof attempt. `plausible` found
   it only on the machine's bounded rewrite of the statement, and `decide` refutes that form for n < 30
   (`spikes/lean/primes/README.md` §6). Graphene's offer on that hand-back is still "wait on", which
   cannot repair a false statement (§6, item 2);
4. the vacuous leaf flagged;
5. the red-team table (§3.3), with its review's corrections, and the gate-file hijack rerun live on core
   Lean (`spikes/lean/primes/hijack/`).

It says only what the spike showed, and it is the "What's next" evidence (§11).
- **How.** A script to write, `spikes/lean/demo.sh`, replays the recorded logs, as `graphene demo` replays
  a run (`src/graphene_map/demo.py`). It reruns live only the hijack, on core Lean (7–15 s). The
  falsifiers run in under a second inside Lean, but only after Mathlib has loaded, which took minutes on
  this machine (`spikes/lean/primes/README.md` §6, `spikes/lean/gate/cost.md`). So the demo replays their
  log, or runs them against a Lean server warmed before it starts.
- **Cost:** $0.
- **Time:** half a day of an agent's work, and half an hour of Alex's to watch and approve it (a guess).

**Optional, if Alex approves, with him present.** One capped live run of a Token Factory model on the five
leaves automation could not close.
- **What runs:** Graphene's own Nemotron executor (decision 54), its tools running in the leaf's checkout
  on this machine, not in a Sandbox (decisions 55, 104). Each leaf's scope is its proof file and its check
  is `check-leaf.sh`, so the check, not the model, decides.
- **Cost:**
  - Nemotron 3 Super, at $0.30 / $0.90 per million tokens in and out (decision 105). The executor's default
    is the smallest Nemotron listed, Nano (decision 56), so Super is named for this run.
  - The cap sets the spend: an opening of $2 in the night's ledger (decision 102), and Alex starts it
    himself (decision 103).
  - For scale: 5 leaves × 8 attempts at the cost model's whole-proof assumption (2,000 tokens in and 7,000
    out an attempt, `models/cost_model.py`) is about $0.28. The executor is a tool loop that pays for its
    whole context on every call, and Token Factory prices no cached input (decision 55, `landscape.md`
    §5). So $0.28 is a lower bound, and the real figure is not measured.
- **What it would add to the submission:** a real Nemotron call doing real work under a check it cannot
  edit. Mathlib already proves the root in one application of Dirichlet's theorem, and the `euclid` leaf
  states the root (`spikes/lean/primes/README.md` §5). A leaf closed by citing it is a lookup, and is
  reported as one.
- **What it risks:** time. Stop at the cap or at an hour, whichever comes first. Each `done` took 7–15
  minutes tonight (§6, item 1), and this machine checks one Mathlib leaf at a time
  (`spikes/lean/gate/cost.md`). So an hour holds four to eight checked attempts, not forty, and the hour
  will likely end the run first (an inference).

**What Alex does:**
- watches the demo, and says yes or no to including it;
- decides on the live run;
- is present for it if yes.

**What earns November:** nothing here. November is earned by the submission being in.

### November: the pilot, and the first people

**Goal.** Run `PREREG.md`'s pilot, the person's side first because it is the cheaper one, and ask three
people.

1. **The person's side:**
   - Alex as the reader who knows the mathematics and not Lean.
   - 40 unseeded statements plus the seeded ones (about one in five), from undergraduate number theory and
     group theory trees.
   - Kill criteria 1 and 2.
   - **Time, a guess:** about 12 to 25 hours of Alex's, over two weeks.
     - About 50 statements reviewed at 4–14 minutes each, Lean experts' published times (IndiMathBench,
       `landscape.md` §6).
     - For kill criterion 2, 20 statements written at about 25 minutes each (PutnamBench's formalizing time,
       same section). The 20 reviewed for it are among the 40; the 20 written are extra (`PREREG.md`).
     - A reader new to Lean is likely slower.
   - **Cost:** $0 apart from the planner's calls, which Alex starts himself (decision 103). A few dollars
     (a guess), within the ledger's $10 a night (decision 102).
2. **The prover's side:**
   - 10 to 12 held-out targets, 30 to 36 target runs across the three arms, on the executor Alex chooses
     (question 2).
   - **Who shapes arm C's trees:** on a blueprint's nodes, the lead whose nodes they are, if they agree. On
     arXiv and LeanEval targets, Alex, only where he can read the mathematics. Whether he can is not known
     until the set is frozen.
   - **The gate** runs on a Linux machine with comparator's real sandbox. It needs about 11 GB of disk for
     the toolchain and Mathlib (§3.6), 1.7–2.7 GB of RAM per Lean process that loads Mathlib, and a tmpfs
     of about 4 GB for comparator's sandbox. SafeVerify's peak was not measured (`spikes/lean/gate/cost.md`).
     - A Nebius CPU VM starts at $0.05 an hour, $0.06 from 1 October (`models/cost_model.py`; the price
       page is in `landscape.md` §5). That is the smallest instance, and whether it has that room was not
       checked.
     - Alex creates and pays for it himself. If he has a Linux machine with that room, it would do.
   - **Cost:** Token Factory spend within Alex's standing $10–20 a night (the directive). Graphene's ledger
     enforces at most $10 a night, and starts nothing new past $8 (decision 102). Live runs happen with Alex
     present. Aristotle is $0 in fees if chosen.
   - **Time:** not estimated in total, since it depends on the leaves per target, which freezing the set
     fixes. The gate took about 9 minutes per leaf here with SafeVerify off (`spikes/lean/gate/cost.md`).
     Two to three weeks of nights is a guess.
3. **The people** (`messages.md`, drafts only):
   - a Lean formalization lead with open nodes whose definitions exist. First choice: the Brownian motion
     blueprint's lead (question 5);
   - the lab where the 2023 pipeline ran. Alex names it;
   - a developer using Graphene. None was identified in any source this run read.
   - **A Lean-fluent adjudicator** who takes no part in the arms, and a Lean-fluent second reader for kill
     criterion 2. `PREREG.md` makes recruiting the adjudicator part of November. Until one exists, no catch
     counts as real and no natural misstatement as confirmed, so kill criterion 1 cannot be scored. None
     has been found, and no draft in `messages.md` asks for one yet. The lead above is the first place to
     ask.

   Alex sends them himself.

**What earns the next phase:**
- kill criteria 1 and 2 not firing for at least one reader;
- a lead saying yes to a trial on their nodes;
- the gate holding on the prover side, kill criterion 4.

What follows each outcome is in `PREREG.md`, "What earns the next phase".

### After

- **If the pilot earns it:**
  - the same design with a second person and more targets;
  - item 3 of §6, the conventions catalog, if kill criterion 2 does not fire for at least one reader.
    `PREREG.md` keeps the board's convention questions whether or not kill criterion 1 fires;
  - item 2 of §6, the witness hand-back, only once hand-backs are counted. `PREREG.md` counts them, each
    with whether it carries a witness the gate verifies (added before any run).
- **If the lead says yes:** an overnight run on their chosen nodes, with their review.
- **Biology waits for a real pipeline** that wants sign-offs.
- **Software** (§7). None of these tests waits on November, so they can run any time after 30 October:
  - Tests 1 to 3, and step 1 of test 4, need no person: scripted executors on the fixed trees. The fixed
    trees themselves need the live planner, a key and a capped spend once (§7; decision 128).
  - Step 2 of test 4 needs a live model, so a key and Alex present.
  - Test 5 is the November pilot's own design.
- **Cost:** the same caps: at most $10 a night through the ledger (decision 102), and Aristotle $0 in fees
  today. Add a second person's time.
- **Time:** not estimated; it depends on which outcome the pilot gives.
- **What Alex does:** finds the second person, runs the lead's trial with them, and decides each item of §6
  on its evidence.
- **What earns the step beyond:** the pilot's direction holding at the size `PREREG.md` says can show an
  effect: 80 to 120 targets, registered like the pilot.

## 9. Risks, and when to stop

**Kill criteria** (registered in `PREREG.md` before any result; the directive's defaults, with the three
changes written there, each with its reason: K1, K3 and K5):
1. Over at least 40 unseeded statements, the person adds fewer than 1 real catch per 10 beyond the
   machine's review and falsification. A real catch is one the adjudicator confirms. Then narrow to the
   board's convention questions, or stop.
2. For a reader, over 20 statements per condition, reviewing the median statement takes more than half as
   long as writing it. Then the attention claim fails for that reader.
3. Arm A or B proves at least as many pilot targets as C, at no more model and compute dollars at list
   price, and lets no more misstatements reach compute. Then the person-shaped tree adds nothing there.
4. Any exploit passes the whole gate and no check command closes it. Then stop until one does. **Tonight's
   reading: it does not fire.** Every attack that faked a proof was rejected by at least one check
   command; wrong statements are beyond any gate by the third condition; two hazards and the Mathlib
   gate stay untested (§3.3).
5. On the leaves automation cannot close, a cheap model costs more dollars per proven leaf, at list price,
   than a frontier model on the same leaves. Then the cheap-model claim fails in mathematics. Aristotle is
   compared on time, not dollars, since it charges no fees.

**Other risks, each with what would show it:**
- **Incumbents close the gap first.** Prove2Me or Aristotle (`landscape.md` §1), or Verso Blueprint
  (`landscape.md` §2), adds convention questions before spend. Watch their changelogs; if one ships it, the
  mathematician persona's one unique piece is gone.
- **Aristotle's terms change.** Today they say Harmonic "does not presently charge fees", and they take a
  perpetual licence to customer data, used for training unless the person opts out (`landscape.md` §5).
  As that line reads, the opt-out stops training, not the licence. Read the terms before each use; never
  send an unpublished result without the opt-out, or a lead's nodes before the lead knows of the licence
  (questions 1 and 5).
- **Token Factory churn.** Ten serverless models were retired on 2026-08-31, eleven on 2026-06-22, and
  cached input has no price (`landscape.md` §5). Resolve Nemotron by role from the live list (decision 56).
  Any other model is kept by its id, retired or not (`src/graphene_map/tokenfactory.py`, `resolve`), so
  check it against the live list before each run. Record the price sheet's date with every row.
- **The gate needs Linux** for comparator's sandbox, which ran tonight only on core Lean (§3.2). A Mathlib
  project in Docker Desktop needs about 11 GB on the container's disk (`spikes/lean/gate/cost.md`).
  Without a Linux gate, nothing counts as "proven" in November.
- **This machine.** Its 18 GB of RAM ran one Mathlib-loading build or check at a time. SafeVerify on one
  Mathlib leaf was stopped before a verdict every time it ran. Three checks at once took free disk under
  15 GB twice (`spikes/lean/gate/cost.md`; `spikes/lean/primes/README.md` §7). Narrow imports should help
  (inferred, not measured end to end). Otherwise parallel leaves need a bigger machine.
- **The kernel itself.** Lean 4.34.0 and 4.34.1 fixed kernel soundness bugs, and the #14576 postmortem
  records one surfaced by an AI-assisted proof (`landscape.md` §4).
  - nanoda, comparator's default external kernel, had a separate bug then, and it has 2 wrong rejects in
    the Kernel Arena (same section). So one external kernel is not enough.
  - Stay on 4.34.1 or later, and run several kernels at the gate: `lake check --paranoid` is on the FRO's
    roadmap, and v4.35 bundles the external checkers (`landscape.md` §2, §4).
  - `PREREG.md`'s gate now asks for at least two external kernels besides Lean's own, and SafeVerify
    (amended before any run).
- **The reader has a stake.** Alex builds Graphene and is the only planned reader who does not know Lean.
  `PREREG.md` names this and its controls (amended before any run):
  - seeded defects score themselves;
  - the adjudicator does not know the condition;
  - times come from logs;
  - his results are labelled "the builder as reader" until a second reader repeats them.

  The controls limit what he can claim to catch, not how fast he reads. Only the second reader removes the
  stake.
- **The attention record.** Every registered attention study so far found no gain by its own rule
  (decisions 98, 99, 108, 115). One exploratory pass leaned the other way (decision 115: 104.1 against 107.4
  modelled seconds), which shows a direction, not a result. The pilot may find no gain too, which is what
  the kill criteria are for.
- **Distraction from the entry.** Nothing here runs before 30 October beyond the one day, and that day is
  optional.

## 10. Questions for Alex

Each has the answer I recommend, taken as the default if he does not answer, except where question 4 says
otherwise. The assumptions taken on his behalf follow the questions.

1. **An Aristotle API key for November?** *Recommended: yes, created by you, with the training opt-out
   switched on before the first submission, and used only on public or held-out targets.*
   - It costs $0 in fees today (`landscape.md` §5). In one project it proved 111 of 220 submissions and
     disproved 28 (`landscape.md` §6).
   - It is free and returns disproofs, which suits a per-leaf executor. Leanstral 1.5's free API is the
     other $0 option (`landscape.md` §3).
   - How strong it is on research targets is open: it scored 0/3 and 0/1 on LeanMarathon's papers
     (`landscape.md` §1).
   - The terms are the risk (§9).
2. **Which existing prover or harness should November's arms run on?** *Recommended:*
   - **Aristotle** for all three arms: end to end for A, per leaf for B and C. All arms then share the
     executor, as `PREREG.md` requires, and B and C differ only by the person's layer.
     - LeanEval dropped every problem one Aristotle query could solve (`landscape.md` §3), so its targets
       are selected against Aristotle. The arms still compare fairly, since all share it (an inference).
     - With Aristotle at $0 in every arm, kill criterion 3's dollar condition nearly always holds for A.
       K3 is then decided by targets proven and misstatements (an inference).
   - **One cheap tier beside it** on the same leaves: Nemotron 3 Super (decision 105), or
     `deepseek-ai/DeepSeek-V4-Flash-0731` at $0.14 / $0.28. That is the DeepSeek V4 Flash left in Token
     Factory's catalog, since the plain id was retired on 2026-08-31 (`landscape.md` §5).
     - Graphene's own executor runs it. That executor is a tool loop (decision 55), so it is priced as a
       loop, at the full input rate (`PREREG.md`, K5).
     - The DeepSeek id is pinned by hand: roles pick only Nemotron sizes (decision 56).
   - **One frontier tier** on the same leaves, capped, so kill criterion 5 can be decided: Claude Code on
     Opus 5.5, which Graphene already starts as an executor (decision 54), at $4 / $20 per million tokens
     (`landscape.md` §5).
     - Its spend is outside Graphene's ledger, which counts Token Factory and Sandboxes (decision 102). So
       keeping it within the standing $10–20 a night is Alex's job.
     - Without it, K5 is not tested in November, and the results say so.
   - **Not LeanMarathon:** it needs Codex with GPT-5.5, a GitHub token and a Slurm cluster (`landscape.md`
     §1).
3. **The one day before 30 October: the recorded demo, and the capped live Nemotron run?** *Recommended:
   the demo if the submission's own work is done by 25 October; the live run only if the video (decision
   118) still lacks a live Nemotron scene.*
4. **The 2023 pipeline:** will you confirm the assumptions in §4.3 (A1 to A9), and may the lab be asked
   (`messages.md`, draft 2)? *Recommended: yes to both.*
   - If you do not answer, the default is not yes. A1 to A9 stay assumptions until you confirm them, and the
     lab draft waits for you.
   - Without the lab's own account of what went wrong, the 2023 case stays a thought experiment.
5. **Which formalization lead to ask first?** *Recommended: the lead of a blueprint whose definitions exist
   and whose open nodes are formally stated.*
   - Brownian motion had 39 such nodes by blueprint colour (`landscape.md` §2). It was last active on
     2026-09-22 (`messages.md`).
   - Blueprint colours can be stale (con-nf, same section).
   - FLT shows as many open nodes, but an end-to-end AI proof of FLT is already public (`landscape.md` §1).
   - Ask before any prover touches their project.

**Assumptions taken for you.** Each stands until you change it.
- The kill criteria as `PREREG.md` changed them, each with its reason:
  - K1 is counted on unseeded statements only;
  - K3's cost is read as model and compute dollars;
  - K5 compares Aristotle on time, not dollars.
- You are the pilot's reader who knows the mathematics and not Lean (§8, §9).
- The worked theorem is the infinitude of primes ≡ 3 mod 4, already in Mathlib (`spikes/lean/primes/`).
- The Lean layout is option 4 of §3.2, protected by today's scope and checked by the gate in `PREREG.md`:
  comparator in its sandbox, two external kernels and SafeVerify.
- Nothing counts as proven in November without a gate on Linux with comparator's sandbox (§3.2, §9).
- On a blueprint's nodes, the person in arm C is the lead whose nodes they are (§8).

## 11. A draft paragraph for "What's next" in `docs/HACKATHON.md`

Not applied. For Alex to edit. It claims only what the spikes showed, and says which machine and which
limits:

> **Beyond software.** Graphene's bet is that a person shapes the plan before an agent spends, and that
> every piece has a check the agent cannot edit. On 30 September we tried it for one night on formal
> mathematics in Lean, where the kernel is the check, with no model and no spend
> (`docs/process/fields/`).
>
> A textbook theorem's tree, infinitely many primes congruent to 3 mod 4 in eight leaves, went into
> Graphene's plan as written. Automation closed three of the leaves for nothing and did not close the
> theorem. A seeded false leaf came back with its counterexample, n = 5, found in under a second before
> any prover ran. Of 21 attacks on the gate that decides a leaf is proven, every one that faked a proof was
> rejected by at least one check, though no single check caught them all.
>
> The same night showed what no gate can catch, a statement that does not say what was meant. It also
> showed that Graphene's own check has to run in a sandbox, because a Lean proof can run code while it is
> checked.
>
> In November we test the claim that matters, registered before any run with the numbers that would make
> us stop: whether a person, helped by the machine's questions about conventions, catches misstatements the
> machine does not. We found no tool that asks those questions before spend, and no measurement of how a
> mathematician who does not read Lean reviews a statement.

Every sentence traces to a section above:
- the tree and automation: §3.8;
- the false leaf: §3.4;
- the red team: §3.3;
- what no gate catches, and the sandbox: §3.3;
- the November test: `PREREG.md`;
- no tool and no measurement: §3.5 and §3.4.

What it leaves out on purpose:
- It names no incumbent and no other entry.
- It claims no gain in attention: none was measured.
- It gives no biology result. The check spike's finding, that cheap checks catch real errors and a correct
  check still drops BRAF V600E, is in §4.4 if Alex wants a sentence.

## 12. How this run went: what ran, what was assumed, what went wrong

This section is the run's own record, for Alex. The spikes' READMEs hold every command and version.

**What ran** (every command, version and output is in the files named):

| Part | Where | When (EDT, 2026-09-30) |
|---|---|---|
| Lean install: elan 4.2.4, Lean v4.34.1, Mathlib v4.34.1 (`d13f23b7`) | `spikes/lean/mechanics/install/` | 00:46–00:52 |
| research, eight researchers in parallel | `landscape.md`; the notes stay in the scratchpad | 00:53–01:40 |
| the biology check spike | `spikes/bio/` | 00:50–01:15 |
| the Lean mechanics and the gate | `spikes/lean/mechanics/`, `spikes/lean/gate/` | 00:59–03:14 |
| the worked tree, automation baseline, hammers, false leaf | `spikes/lean/primes/` | 00:58–03:14 |
| the red team: 21 attacks × 7 layers, the real Graphene boundary | `spikes/redteam/` | 03:15–03:55 |
| a critic's review of the red team; round two (one hole tested, two left open) | `spikes/redteam/` (Review), `spikes/redteam/round2/` | 04:00–04:25 |
| the plan checked claim by claim (six verifiers and a directive-compliance critic, 222 findings), fixed by section, cross-checked by the integrator | this file | 03:20–04:30 |
| `PREREG.md`, registered before any evaluation run | commit `65cd69d` | 01:43 |

No model or prover was called by any spike, no key was read, no account was made, and nothing was spent.
- The only network use was public: downloads of tools, Lean packages and public databases, and web reading.
- Research agents read Aristotle's public wheel source, and did not run it.

**Assumptions taken, since Alex was asleep** (each is also a question in section 10, or recorded where it
applies):
- **The theorem for the worked tree** was the one the directive suggested: primes ≡ 3 mod 4, over Fermat
  through Lagrange. It has leaves automation should close, and a convention that bites (ℕ subtraction).
- **The layout under test** was the directive's option 4, as the starting hypothesis. The spike and the red
  team tested it; they did not assume it.
- **The person's acts in the scratch repositories** followed decision 95's precedent: the agent's marks were
  dropped and `GRAPHENE_AS=person:alex` was set there only, and the log marks them "(no terminal)".
- **Mathlib at the release** tagged for the newest stable Lean (v4.34.1), not master.
- **This planning run's work was committed as it finished.** `PREREG.md` came before the Lean spike did, so
  that its registration time is as early as possible.

**What went wrong, and what was done:**
- **Memory.** This machine has 18 GB of RAM. Several agents loaded Mathlib at once, swap reached 30.3 GB, and
  free disk fell to 13 GB at 03:08, below the 15 GB floor the agents were given.
  - The coordinator stopped the tree agent's gate run: three SafeVerify processes at once, each loading
    Mathlib four times. Free disk went back to 22 GB within a minute.
  - The gate now runs one leaf at a time, and `gate/cost.md` says why.
  - Every wall time that includes loading Mathlib is this night's machine, not Lean. That is said wherever a
    number appears.
- **Duplicated agents.** The coordinator's messages at 03:09 resumed a second copy of each running
  Lean agent, and for a few minutes two copies of each wrote into the same directories.
  - The mechanics copies agreed: the first checked the second's entries against their logs and kept them.
  - The tree copies did not. The second ran SafeVerify and comparator three at a time again at 03:10, and
    the first stopped those jobs at 03:12, taking them for leftovers.
  - `spikes/lean/primes/README.md`, section 7, records which runs were whose. One measurement made while
    both ran is marked void there.
  - After that the coordinator sent no more messages to running agents.
- **Files in Alex's checkout.** The browser tool one researcher used to read a JavaScript page wrote six
  capture files into the git-ignored `.playwright-mcp/` of `~/Desktop/AllThingsAgenticHackathon`. The
  researcher moved exactly those six files into the scratchpad. `git status` there was unchanged. Nothing
  else in the checkout was touched.
- **Predictions that missed.** Each is kept beside its prediction in the spikes' `PREDICTIONS.md` files, and
  none was edited after the result. The toolchain's size, the first build's time, the Mathlib-bound check
  times, `native_decide`'s axiom name, and comparator's sandbox on Docker Desktop's bind mount all missed.
