# Drafts for November: the first people to ask

*Drafts only. Nothing here has been sent, and nothing should be sent by an agent. Alex edits, picks the
recipient and sends each one himself, after 30 October. Each draft claims only what the spike and the
research showed (`PLAN.md`, `landscape.md`); where a line depends on what November's pilot has not yet run,
it says so.*

## 1. A Lean formalization lead with open nodes

**Whom.** A lead of an active blueprint whose open nodes are formally stated and whose definitions already
exist, since a statement-freezing gate helps only there. Candidates from the research (`landscape.md` §2),
with open, formally stated nodes counted on 2026-09-30 from their published blueprint graphs:
- Brownian motion: 39 nodes, active on 2026-09-22.
- ExtremeValueProject: 36, last push 2026-07-25.
- FormalBook: 37. Its theorems are well known, so less useful to a prover evaluation.
- The IEANTN tasks: issues sized XS to XL.

Ask before sending anything to a prover. RLMEval got the authors' agreement, and the sphere-packing team
objected to "drive-by proving".

**Draft.**

> Subject: would you try a statement gate on a few of [project]'s open nodes?
>
> Hi [name],
>
> I build Graphene, a tool where a person shapes the plan an AI agent works from before anything runs, and
> each piece has a check the agent cannot edit. I'm trying it on Lean, and [project]'s blueprint is the kind
> of place I think it could help or clearly not.
>
> What it would do: you pick a handful of open nodes whose statements and definitions you trust. They go
> into a challenge module that no agent can touch. An existing prover (not ours) attempts each node
> overnight, cheapest first. A proof counts only if it passes comparator against your statements, uses only
> the three standard axioms, and replays in the kernel. A node that fails comes back either with a proof,
> checked by the same gate, that its statement is false or that its hypotheses cannot all hold, or marked
> "budget exhausted, no defect found". Never just "too hard".
>
> What I'd ask of you: about an hour to pick the nodes and read what comes back, and your permission. I
> would not run anything on your project without it.
>
> What I can show today is small. On a textbook tree (infinitely many primes that are 3 mod 4) I measured the
> mechanics: automation closed 3 of its 8 leaves for nothing; a seeded false leaf's counterexample turned up
> in under a second once its statement was bounded by hand; and of 21 attacks on the gate, run on core Lean
> rather than Mathlib, each of the 15 that faked a proof was rejected by some layer, though no single layer
> caught them all. The
> results are here: [link to PR 36 or the spike README]. Nothing has been measured on a research blueprint
> yet. That is what I'm asking to try.
>
> Would you be open to it, or is there a reason it would not help [project]?
>
> Alex

## 2. The lab where the 2023 variant pipeline ran

**Whom.** Alex knows. The draft asks about their experience, not about a product.

**Draft.**

> Subject: a question about the 2023 AlphaFold/NetSurfP variant pipeline
>
> Hi [name],
>
> I'm looking back at the pipeline I ran with you in 2023, the one that classified over 10,000 oncogenic
> variants with AlphaFold and NetSurfP on [cluster]. I'm studying where cheap automatic checks catch real
> mistakes in pipelines like that before compute is spent, and where only a scientist can judge.
>
> Two questions, if you have ten minutes:
> 1. Did anything go wrong in that work, or in similar work since, that was only found late (in review, in a
>    follow-up, or never)? Numbering against a different isoform than the structure, a reference mismatch, a
>    threshold that did not mean what we thought?
> 2. When a result was questioned, how did you reconstruct what had been run?
>
> For context, on 30 September I ran four such checks on public data for six cancer genes (6,400 ClinVar
> records):
> - A string comparison found 17 variants numbered on a different KRAS or BRAF isoform than the AlphaFold
>   model uses.
> - A correct confidence check would have excluded BRAF V600E from structural interpretation.
>
> The details are here: [link]. I'm not selling anything; I'm trying to learn whether this is worth building.
>
> Thanks,
> Alex

## 3. A developer already using Graphene

**Whom.** Whoever has run Graphene on a repository of their own: Alex knows who, if anyone yet.

**Draft.**

> Subject: does your Graphene check ever judge a file the agent can edit?
>
> Hi [name],
>
> A question from a side project. In Lean, the statement a proof must meet lives in a file no agent can
> touch, and a gate compares the proof against it. I'm checking whether Graphene's checks for code need the
> same rule.
>
> Could you look at one plan you ran and tell me:
> 1. Did any leaf's check run a test file that was inside that leaf's own scope?
> 2. Did any leaf come back with a reason that named no file, line or failing input?
>
> If the answer to either is yes, I'd like to see the plan (`graphene plan --text`), if you're willing to
> share it. I'll send you what I learn.
>
> Thanks,
> Alex
