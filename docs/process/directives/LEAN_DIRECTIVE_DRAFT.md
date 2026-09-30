# Graphene: the Lean directive (a draft for Alex to edit)

*A draft, written 2026-09-30 by the agent that ran `FIELDS_DIRECTIVE.md`, for the first build step in mathematics. Nothing here runs before 30 October. Alex edits it, fills in the answers it asks for, and sends it. Where this draft and `docs/DIRECTION.md` disagree, DIRECTION wins.*

*Read before you write anything:*
- *`docs/process/fields/PLAN.md` (sections 3, 6, 9 and 10)*
- *`docs/process/fields/spikes/lean/primes/README.md`*
- *`docs/process/fields/spikes/lean/gate/README.md` and `cost.md`*
- *`docs/process/fields/spikes/redteam/README.md`*
- *`docs/process/fields/PREREG.md`*
- *`docs/DIRECTION.md` (decisions 1, 6, 15, 17, 29, 32, 54, 60, 62, 68, 81 to 83, 90, 99, 102, 103)*
- *this file*

## What this run is

The first build step of Graphene in mathematics. **It builds the person's layer, not a harness.**
- Graphene drives **one existing prover** on **one small tree**, with the gate as each leaf's check command.
- Every leaf either lands proven or comes back with a witness.
- The run measures what each step cost.

What it is not:
- It is not the evaluation. `PREREG.md`'s arms need Alex as the reader and an adjudicator, and they wait for
  him.
- It does not decompose, search, or retry on its own. Graphene's attempts and forks (decisions 60, 68) are
  the only loop.
- If you find yourself writing a proof-search policy, stop. That is a harness.

**Alex's answers, filled in before you start** (from `PLAN.md`, section 10):
- The executor: `[Aristotle per leaf, with his key and the training opt-out on | Graphene's Nemotron executor on Token Factory, local placement | both, Aristotle first]`.
- The night's spend cap: `[$ … , at most $20]`, on one ledger (decision 102). Alex opens it himself (decision
  103).
- The Linux machine for comparator's sandbox: `[host]`.
- The tree after the primes tree, if any: `[none | a held-out tree Alex chose, with the lead's agreement]`.

## How you work

- **Before any change.** Work in your own worktree cut from `origin/main`, on one branch with one draft PR.
  Alex's checkout is his. Write the rollback SHA into the brief before the first change.
- **Predictions first.** Before each measurement, write what you expect; then what happened. Every claim in
  the brief carries the command that shows it.
- **Machine limits.**
  - On an 18 GB machine with `import Mathlib`, run **one** Lean process that loads Mathlib at a time. Three at
    once took free disk under 15 GB twice on 30 September; macOS swap lives on the same disk.
  - Check free disk before each such step and stop under 16 GB.
- **Spend.**
  - Every live call goes through the night's ledger. Stop at 80% of the cap.
  - Live runs happen with Alex present.
  - Never read, print or copy a key.
- **Commits.** Commit and push after each milestone, and keep the brief true at each.

## The brief: the top of `docs/process/morning.md`

Keep the brief current at every milestone, so a run cut off early still leaves a true one. At most twenty
lines, no paragraphs, under the first-light directive's headings:
1. **Watch first.**
2. **What ran live:** each run, pass or fail, and the bill against the cap.
3. **New tonight:** five lines at most, each with the command that shows it.
4. **Decide:** at most three questions, each with your default.
5. **Broken or risky:** three lines at most.

Below it go the decisions, the evidence, the state of the branch and the rollback SHA.

## The milestones, in order

### A. The gate, hardened into one check command

`spikes/lean/gate/gate.sh` held on the core-Lean layout and on one Mathlib leaf. Make it the check a leaf
carries:
- **Read the compiled environment, never parse a file compiled after the leaf.** Replace layer (c)'s compiled
  `Gate/<Leaf>.lean` with `GateCheck.lean` from `spikes/lean/primes/`.
  - A leaf's own macros can rewrite a gate file that imports it. The spike printed a clean axiom line for a
    proof of `1 = 2` that way.
  - `GateCheck` asks the environment instead.
- **Take the trusted inputs from the approved commit** (`git show <ref>:path`), as layer (a) does. Keep the
  trusted `.lake` where no executor can write: another user, or a read-only mount.
  - The spike's check borrowed the shared build through a symlink outside git, so outside every scope.
- **Narrow the challenge's imports** to the Mathlib modules its statements need. One lemma checked cold in
  1.78 s this way, against 146.6 s with `import Mathlib`.
- **Run the gate `PREREG.md` registers, on Linux:**
  - comparator in its real sandbox;
  - at least two external kernels besides Lean's own (lean4lean and con-leche ship with Lean v4.35; nanoda
    alone had wrong rejects);
  - SafeVerify, one leaf at a time, on a machine with the memory for it.

  On macOS keep `sandbox-exec` around every layer that loads a leaf's code, and say in the brief which
  sandbox ran. Never report the no-op shim as a sandbox, or a skipped layer as passed.
- **Fix what the spike found in `gate.sh`:**
  - it fails when the project sits at the repository root, because an empty `--show-prefix` is passed to
    `git ls-tree` (`spikes/lean/primes/README.md` §7);
  - it trusts a `.lake` and tools that an executor running as the same user can edit between runs
    (`spikes/lean/gate/README.md`, "Limits").
- **Run the red-team suite** (`spikes/redteam/run_all.sh`) against the hardened gate. Every exploit must be
  rejected, and the honest tree must pass.

**Done when:**
- `run_all.sh` rejects every exploit it lists and passes the honest primes tree, on the Linux machine;
- the brief gives each layer's time per leaf.

### B. The witness hand-back, as a convention first

The spike showed Graphene accepting `graphene node release --why "too hard"` for a leaf `exact?` closes in
0.015 s. It also showed Graphene offering "wait on another leaf" for a false one. Fix both without touching
Graphene first:
- **The leaf's goal says how to hand back.** A proof leaf hands back only with a witness file in its scope:
  `Witness/<Leaf>.lean`, proving `¬ S_<leaf>` or `False` from the leaf's hypotheses. The reason names that
  file.
- **The check verifies the witness.** `gate.sh --witness <Leaf>` runs the same layers on the witness as on a
  proof.
- **"Budget exhausted, no defect found"** is recorded in the reason as its own words and never as "false".

**Done when:**
- the seeded false leaf (`odd_factor_three`, false at n = 5) comes back with a witness the gate verifies;
- a hand-back without one is visibly different on `graphene watch` from one with.

If that last point cannot be done without a Graphene change, write the change as a proposal in the brief. Do
not make it.

### C. The executor, driven by Graphene

A wrapper script named with `--with` (HOW_IT_WORKS P4c). It takes the leaf's contract, the statement with its
needs as hypotheses, and the scope file.

**This is glue, not a harness.** It calls existing tools in a fixed order, each once, with that tool's own
limits. It holds no search over tactics or proofs, no decomposition, and no retries beyond Graphene's own
attempts and forks. The order is the plan's cascade, cheapest first (`docs/process/fields/PLAN.md` §3.6).

It runs, in order, stopping at the first that settles the leaf:
1. **The falsifiers**, `$0` and seconds each: `plausible` on the statement; `decide` on bounded instances;
   the vacuity test (`spikes/lean/primes/Falsify/`). A counterexample writes the witness and hands back
   before any spend.
2. **Automation**, `$0`: `omega`, `grind`, `grind +suggestions`, `exact?`, `try?`, under a time limit.
3. **The chosen prover.** It writes only `Proofs/<Leaf>.lean`.

- Graphene's own `done` decides, not the wrapper (decision 7).
- Record per leaf which rung settled it, its wall time and its cost at list price.

**Done when:** a leaf runs through all three rungs under `graphene run`, and the record says which rung
settled it.

### D. One small tree, end to end, with Alex present

- **The tree:** the primes tree of `spikes/lean/primes/tree.txt`, with the seeded false leaf proposed under
  it.
- **How:** Alex accepts it in `graphene watch`, answers what the board asks (if anything), and presses `R`.
- **What should happen:**
  - the three leaves automation closes land for $0;
  - the false leaf comes back with its witness before any prover is paid;
  - the rest go to the prover;
  - the root's check (the sub-goal's own, decision 15) runs comparator on the whole.
- **What to record:** wall time and cost per leaf, the person's actions counted, and every hand-back.

**Done when:** the tree is proven, or every leaf that is not has a witness-backed hand-back. The brief has the
table.

### E. (Only if Alex chose one.) A held-out tree of 5 to 8 leaves

The same run, on the tree Alex chose with its lead's agreement. This is not the evaluation. It shows whether
D's mechanics survive a statement nobody has proved in Mathlib.

## What not to do

- No harness: no decomposition, search, retry or scheduling beyond what Graphene already does.
- No evaluation arm, and nothing that enters `PREREG.md`'s tables. Anything measured here is mechanics.
- No change to `src/`, `tests/` or the UI, unless a milestone cannot be reached without one. Then propose it
  in the brief and stop.
- No call to any prover or model outside the ledger and the cap, and none without Alex present.
- No run on anyone's project without their agreement.
- Never report the fake-landrun shim as comparator's sandbox, or a skipped layer as passed.
- Nothing on `main`.

## When it is done

- The brief says, with a command each:
  - what the gate costs per leaf;
  - that the red-team suite is rejected in full;
  - which rung settled each leaf of the primes tree;
  - what the false leaf's hand-back looked like;
  - what the run cost.
- Anything that needs Graphene to change is written as a proposal with the result that justifies it, and not
  built.
