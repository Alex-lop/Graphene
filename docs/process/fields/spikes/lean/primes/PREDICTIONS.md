# Predictions, written before each measurement

Each entry is written before the command it predicts ran; the result is appended under it afterwards
("Result:"). Times are local (EDT) on 2026-09-30. Where a prediction is a guess, it says so.

## P1. 2026-09-30 00:58 — the tree and Graphene's text form (before any graphene command)

- `graphene plan propose -` with the tree text (8 leaves under one sub-goal, `needs:` by id, one scope
  and one check each, the sub-goal carrying its own check): accepted as proposals. 65%. Most likely
  refusal if any: the sub-goal's `check:` (a sub-goal with a check and no scope), or `needs:` on a
  node that is a proposal in the same text.
- `graphene plan edit` (as the person) with the same text: accepted. 70%.
- `graphene plan --text` round-trips it: the same lines back, plus `#` notes and `[id]`s. 75%. Guess:
  the goal prose under a leaf (the English statement) may be re-wrapped or moved.

## P2. 2026-09-30 00:58 — the Lean checks (before any lake command in this project)

- `lake build` of Challenge.lean (Mathlib import, eight Prop definitions): 5-30 s the first time.
- `check-leaf.sh <Leaf>` once Challenge is built: 6-20 s per leaf, dominated by loading Mathlib's
  .olean files twice (the proof module and the gate). Root: 10-30 s.
- `#print axioms` on each hand proof: `[propext, Classical.choice, Quot.sound]` or a subset; none
  shows `sorryAx` or `Lean.ofReduceBool`. 90%.

## P3. 2026-09-30 00:58 — the automation baseline (before the script exists)

Goal x tactic, 60 s wall each, needs in context as hypotheses, statements unfolded first.
Guesses, with my confidence that the cell is right:

| goal | expected to close | expected to fail |
|---|---|---|
| whole theorem (S_root) | none (85%); exact? finding Dirichlet's theorem in Mathlib: 15% (Mathlib states it with a `ZMod` cast, not `% 4`) | all |
| prime_mod_four (p prime, p ≠ 2 → p%4 ∈ {1,3}) | none (60%): oddness of p needs one lemma; grind or aesop might (30%) | omega, decide, simp, norm_num |
| mul_one_mod_four (a%4=1 → a*b%4 = b%4) | grind (40%); simp with Nat.mul_mod is not plain simp | omega (nonlinear), decide |
| factor_three_mod_four (the key lemma, needs 2 above) | none (90%): needs strong induction | all |
| euclid_mod_four (0<P → (4P-1)%4 = 3, the ℕ-subtraction leaf) | omega (95%), grind (80%), in under 1 s | decide, exact? (70%) |
| not_dvd_euclid (0<P, p prime, p∣P → ¬ p∣4P-1) | none (65%); grind 25% | omega |
| dvd_factorial (0<p ≤ n → p ∣ n!) | exact? (90%, it is Nat.dvd_factorial), aesop 30% | omega, decide |
| euclid (the argument from the four needs) | none (85%) | all |
| set_form (∀n ∃p>n form → Set.Infinite form) | exact? 30% | most |

Overall guess: the whole theorem closes under nothing; 2-4 of the 8 leaves close under some tactic.
If that holds, the tree turns "nothing closes" into "a few leaves close for $0", but the key lemma and
the argument still need a prover or a person: the thesis would hold only in its weak form.

Hammers (45-minute box): Duper built against Lean v4.34.1: 40%. Canonical with a binary for this
toolchain: 50%. LeanHammer with a local premise selector: 25%.

## P4. 2026-09-30 00:58 — the seeded false leaf (before any run)

- `plausible` on `∀ n, n % 2 = 1 → 1 < n → ∃ p, p.Prime ∧ p ∣ n ∧ p % 4 = 3`: fails to run at all
  because the unbounded `∃ p` has no decision procedure (60%); on the bounded form (`∃ p ≤ n` or
  `∃ p ∈ n.primeFactors`) it finds n = 5 (or 13, 17, 25...) in under 2 s (80%).
- `decide` on `∀ n < 20, ...` (bounded): says the proposition is false in 1-20 s, if the kernel's
  primality evaluation does not hit the recursion limit (50% it hits a limit and needs `n < 10`).
- the vacuity test (are the hypotheses satisfiable?): passes (n = 3 satisfies them), so it does NOT
  flag this leaf. That is the right answer: the leaf is false, not vacuous.

Result P2 (01:02-01:06): `lake build Challenge Seeded`, the first build in this project (a fresh APFS
clone of the base .lake): **211.5 s wall, 9.5 s user, 51.2 s sys** (logs/build-challenge.log). My 5-30 s
was wrong by an order of magnitude; the time is I/O on the first read of the cloned Mathlib .olean
files (the base project's first build took 148 s the same way). The leaf checks' results are under
P9: each took 2-10 minutes, not 6-20 s, for the same reason. `#print axioms` on every hand proof was
a subset of the standard three, never `sorryAx` or a native-decide axiom: right (90%).

## P5. 2026-09-30 01:23 — hammers (45-minute box starts now), revised after reading notes/provers.md

provers.md (another agent, read 01:22) says: Duper has a v4.34.1 tag, lean-auto too, same batteries SHA as
Mathlib v4.34.1; Canonical has a v4.34.0 release with a prebuilt darwin_aarch64 library; LeanHammer
supports only up to v4.33.0 and its default premise selector is a cloud server.
- Duper v4.34.1 resolves beside Mathlib v4.34.1 with no manifest conflict: 80%. Builds from source in
  5-20 minutes on this (memory-starved) machine: 60%.
- Canonical v4.34.0 loads under Lean v4.34.1: 50% (a .olean or dynlib built for 4.34.0 may be refused).
- LeanHammer: not installable on v4.34.1 (90%); a separate v4.33.0 project with a local MePo selector
  would not fit in what remains of the 45 minutes (80%).
- Local zero-install relatives (`grind +suggestions`, `try?`, both in core with a local selector): add
  them as columns; they close nothing that `grind`/`exact?` do not (60%).

## P6. 2026-09-30 01:32 — the baseline run itself (before `python3 Auto/run.py`)

14 goals x 10 tactics (the 8 of P3 plus `grind +suggestions` and `try?`), one Lean process.
- Wall time: 25-60 minutes (most cells fail fast; exact?, aesop, grind+suggestions and try? may use
  the full 60 s on the goals they cannot close).
- The vacuous seeded leaf (even_three_mod_four) closes under omega and grind in under 1 s: 90%. That is
  the "suspiciously easy" alarm firing on a statement that says nothing.
- The two false seeded leaves close under nothing: 99% (they are false; a closure would be a bug).
- `try?` closes what some single tactic closes, no more: 70%.

Result P5 (hammers, 01:23-01:46, 23 of the 45 minutes):
- Duper v4.34.1 + lean-auto v4.34.1 + Canonical v4.34.0: `lake update Duper Canonical` resolved with
  no conflict in 30.6 s; `lake build Duper Canonical` built in 110 s wall (163 s user). Right.
- Duper works: `duper [*]` closed a propositional and an equality smoke goal with standard axioms.
- Canonical loads under v4.34.1 only through `lake lean` (plain `lake env lean` aborts: "Could not find
  native implementation of external declaration 'Canonical.canonical'", the precompiled dynlib is not
  passed). When it finds a proof it **closes the goal with `sorry` and prints `Try this: exact ...`**:
  both smoke theorems showed `sorryAx` under `#print axioms`. A Canonical "success" is a suggestion to
  paste and recheck, never a proof. My 50% guess was about loading; the admit-by-design I did not predict.
- LeanHammer v4.33.0 beside Mathlib v4.34.1: `lake update LeanHammer` resolved (exit 0) by taking
  Mathlib's aesop instead of LeanHammer's pinned aesop v4.33.0, then `lake build Hammer` failed after
  267 s: lean-smt's `Smt/Tactic/WHNFConfigurable.lean:445:46: Invalid field canUnfold?: The environment
  does not contain Lean.Meta.Context.canUnfold?` (removed in Lean 4.34). Not attempted further: fixing
  lean-smt, or a second Mathlib at v4.33 (7.6 GB) with a local MePo selector, would not fit the box.
  My 90% "not installable on v4.34.1" was right in outcome but for a different reason than the aesop pin.

## P7. 2026-09-30 01:48 — Duper and Canonical on the 14 goals (before the run)

- `duper [*]` (hypotheses only, no Mathlib premises): closes nothing (80%). Duper needs the lemmas
  it uses handed to it, and the leaves need number theory, not first-order logic over the context.
- `canonical 55`: suggests a term for nothing that needs a Mathlib lemma (80%); if it suggests
  anything, the suggestion is for the vacuous seeded leaf or `set_form`-like plumbing. Whatever it
  "closes" shows `sorryAx` (it admits by design, P5).

Result P3 + P6 (the baseline, 01:32-01:49; `Auto/baseline.md`, `logs/baseline-20260930-013204.log`):
- Whole theorem: closed by nothing, in both forms (10 tactics each). Right (85%). `exact?` did not find
  Dirichlet's theorem in Mathlib (failed in 3.2 s and 0.4 s): right (85%).
- Leaves: 3 of 8 closed by some tactic. Inside my "2-4" guess.
  - `euclid_mod_four`: omega 0.08 s, grind 0.18 s, grind +suggestions 0.45 s, try? 1.46 s. Right.
  - `dvd_factorial`: exact? 0.015 s (`Nat.dvd_factorial`), grind +suggestions 0.79 s, try? 0.51 s. Right
    for exact?; wrong for aesop (30%): aesop failed.
  - `mul_one_mod_four`: plain grind failed; `grind +suggestions` (0.58 s) and try? (1.49 s, which
    suggests `grind only [Int.mul_emod]`) closed it. Half right: I gave grind 40% and did not think
    of the suggestion engine.
  - `prime_mod_four`, `factor_three_mod_four` (with or without its needs), `not_dvd_euclid`, `euclid`,
    `set_form`: nothing. Right for all five; `set_form`'s exact? (30%) failed too.
- Seeded: the two false leaves closed under nothing (right, 99%); the vacuous leaf closed under omega
  (0.07 s), grind (0.26 s), grind +suggestions and try? (right, 90%).
- `try?` closed exactly the goals some other column closed, no more (right, 70%).
- Wall time 1047 s (17.5 min), under my 25-60 minutes: most failures take under a second; the
  timeouts were only `grind +suggestions` and `try?` on the key lemma (both forms), the false leaf, and
  `try?` on the ℕ-subtraction off-by-one.

## P8. 2026-09-30 01:57 — `Falsify/Run.lean` (before it ran; after a core-only test of the two commands)

- `#falsify` on each honest leaf: `none-found` for the leaves with only decidable parts
  (prime_mod_four, mul_one_mod_four, euclid_mod_four, not_dvd_euclid, dvd_factorial) and
  `cannot-test` for those with an unbounded `∃` (root, factor_three_mod_four) (70%).
- `#falsify S_odd_factor_three`: cannot-test (the `∃ p`), as in P4 (60%); on the bounded restatement,
  a counterexample (5, 13, 17 or 25) in under 2 s (80%).
- `#falsify S_euclid_mod_four_any`: counterexample P = 0 in under 1 s (90%).
- `#falsify S_even_three_mod_four`: gave-up (plausible never meets the hypotheses) (70%).
- `#vacuity`: satisfiable with an example for every honest leaf and for the false one; VACUOUS by
  omega for even_three_mod_four; no-hypotheses for euclid_mod_four_any (90%).
- the Dirichlet one-liner `root_by_dirichlet` compiles with the standard axioms (85%).

## P9. 2026-09-30 02:01 — the leaf checks, rerun through GateCheck.lean (before the rerun)

A core-only test (scratchpad/tmp/hijack) showed a leaf's own file can make `S_leaf` a keyword that
means `True` and give `#print axioms` a clean fake line: compiling `Gate/<Leaf>.lean` printed
"'false_leaf' depends on axioms: [propext]" and exited 0 for a proof of `1 = 2`. GateCheck.lean
(which imports the compiled module at run time and asks the environment) failed it: "false_leaf :
True, not S_false_leaf". Predictions for the rerun of `check-all.sh`:
- every honest leaf and Root pass; OddFactorThree fails with sorryAx (95%);
- each check costs one Mathlib load (GateCheck's `importModules`) plus a cached `lake build`:
  1-6 minutes each on this machine tonight, 20-60 s on a quiet one (a guess).

Result P7, first try (01:47-02:05, logs/hammers-first-try-stuck.log): Duper failed on both whole-theorem
goals in 0.1-0.4 s; Canonical used its whole 55 s on each and found nothing ("No proof found. Supply
constant symbols with `canonical [name, ...]`"). Then `duper [*]` on prime_mod_four ran past 3 minutes
of CPU: Duper splits `maxHeartbeats` among its portfolio instances and stops on heartbeats, and the
harness had set `maxHeartbeats 0`, so it had no limit, and it did not stop at the cancellation token.
I stopped the run and reran with `set_option maxHeartbeats 1000000 in duper [*]` (five times Lean's
default), which did not take effect (second try, below).

Result P4 + P8 (`Falsify/Run.lean`, 01:56-02:04, 467 s wall of which about 7 minutes loading Mathlib;
the times below are inside Lean; `logs/falsify-run.log`):
- `plausible` on `S_odd_factor_three` as written: cannot test ("Failed to create a `testable`
  instance", the unbounded `∃ p`), 0.020 s. Right (60%). The same for `S_root`, the key lemma and,
  unexpectedly to me, the vacuous `S_even_three_mod_four` (its conclusion has the same `∃ p`): I
  predicted gave-up (70%), wrong.
- on the bounded restatement (`∃ p ≤ n`): counterexample **n = 5 in 0.142 s**. Right (80%, < 2 s).
  The bounded key lemma: none found, 0.096 s.
- `decide` on `∀ n < 30, …` (bounded): "Tactic `decide` proved that the proposition … is false" in
  **0.042 s**; n < 10 in 0.031 s. No recursion limit (my 50% on a limit: wrong). The true bounded key
  lemma for n < 30 closed by decide in 0.043 s (kernel-checked, standard axioms).
- `plausible` on `S_euclid_mod_four_any`: counterexample **P = 0 in 0.064 s**; `decide` on P < 10 said
  false in 0.002 s. Right (90%).
- `#vacuity`: every honest leaf and the false leaf satisfiable, each with an example (p = 3; a = 1;
  n = 3; P = 1; P = 12, p = 2; p = n = 1; n = 3) in 0.06-0.18 s; `S_even_three_mod_four` **VACUOUS, proved
  by omega in 0.150 s**; `S_euclid_mod_four_any` has no hypotheses. Right (90%).
- `#falsify` on the decidable honest leaves: none found in 0.07-0.21 s; cannot-test for the two with
  `∃`. Right (70%).
- The witness list below 60: [5, 13, 17, 25, 29, 37, 41, 53]; `Nat.primeFactorsList 5 = [5]`.
  `odd_factor_three_false : ¬ S_odd_factor_three` checks with the standard axioms.
- `root_by_dirichlet` (Mathlib's Dirichlet in one application) checks with the standard axioms. Right.

Result P1 (Graphene on the text, 01:21-01:36; `logs/graphene/`):
- `graphene plan propose -`: accepted as it is, the goal and 9 nodes proposed, exit 0. Right (65%);
  neither refusal I expected happened (a sub-goal's `check:` and `needs:` between new proposals are
  both read).
- `graphene plan edit` as the person: accepted, exit 0 (all `?` made `-`; and, in a fresh repository,
  the text pasted as it is). Right (70%).
- `graphene plan --text` round-trips: `diff` empty once Graphene's `#` notes and blank lines are
  removed and `?` read as `-`. Right (75%); my guess that prose would be re-wrapped was wrong: every
  prose line, Unicode included, came back byte for byte.

Second try (02:04-02:11, logs/hammers-second-try-stuck.log): stuck the same way. A tactic-level
`set_option maxHeartbeats N in` changes the options but not `Core.Context.maxHeartbeats`
(`CoreM.withOptions` updates only `options`, `diag` and `maxRecDepth`), which is what Duper reads, so
the harness's 0 still held. Third try: the hammers' copy of the harness (`hammers/Harness.lean`) sets
`maxHeartbeats := 1000000 * 1000` (1,000,000 in `set_option` units, five times the default) for every
attempt instead of 0; Canonical keeps its own 55 s timeout.

Result P7, third try (02:11-02:29, `logs/hammers-20260930-021145.log`, `Auto/hammers.md`): Duper and
Canonical closed **none** of the 14 goals, and Canonical suggested no term for any. Duper said "failed
to solve the goal and determined that it will be unable to do so with the current configuration of
options and selection of premises" in 0.03-0.34 s on 13 goals, and hit its heartbeat budget in 9.7 s
on the key lemma with its needs; Canonical used its whole 55 s on every goal ("No proof found. Supply
constant symbols with `canonical [name, ...]`"). Right on both (80%, 80%); I had allowed that
Canonical might suggest a term for the vacuous leaf or `set_form`, and it did not.

## P10. 2026-09-30 02:30 — ../gate/gate.sh on the eight leaves and the root (before the run)

The hijack through gate.sh (02:19, core Lean) failed at (e) SafeVerify and comparator, and passed
(a)-(d); that is measured, not predicted. For the honest tree:
- every layer passes for all nine (80%); the likeliest failure is tooling, not proof: comparator or
  SafeVerify on a module that imports Mathlib (the gate agent's own tests may have used smaller
  projects), or the `Root` spec, whose theorem `root` is proved in `Proofs.Root` from the others.
- wall time 15-40 minutes tonight (a guess: several Mathlib loads per layer, three at a time).

Result P9 (the final pass, 02:19-02:39, `logs/check-final.log`): every honest leaf and Root proven
through GateCheck, OddFactorThree not proven ("GateCheck odd_factor_three: FAIL: odd_factor_three uses
axioms beyond the standard three: [sorryAx]"). Right (95%). Wall per check 32-165 s for the proven ones
and 456 s for the false leaf (which also compiled its proof module): inside my "1-6 minutes tonight"
guess. The quiet-machine guess (20-60 s) was not tested.

Result P10 (gate.sh on the nine, 02:45-03:09, `logs/gate-primes.log`): (a) trusted inputs, the trusted
build, (b) lake build (366 s), (c) type + axioms (321 s) and (d) leanchecker (427 s) passed for all
nine. (e) never finished: SafeVerify ran three at a time, each loading Mathlib, swap reached 30.3 of
30.7 GB and free disk 13-14 GB, and the integrator stopped the run at 03:09. My "15-40 minutes" was on
the way to being wrong on the long side; the memory limit I did not foresee.

## P11. 2026-09-30 03:12 — SafeVerify on ONE leaf (EuclidModFour), alone, with a watchdog

- it passes (85%) in 2-8 minutes, most of it loading Mathlib twice (the spec's and the proof's
  environments) (a guess);
- swap rises 1-3 GB at its peak (a guess); the watchdog stops it at +4 GB.

Result P11 (`logs/safeverify-one.log`): stopped by the watchdog after 36 s, before a verdict: swap went
from 20.7 GB to 25.6 GB (+4.9 GB) and free disk from 22 GB to 17 GB (macOS swap files live on the
same disk). My "+1-3 GB" was wrong. Following the integrator's rule (skip SafeVerify if one run pushes
swap up by more than a few GB), I did not run SafeVerify or comparator again on the primes tree
tonight. On the core-Lean hijack they ran in about 2 s each (section 7).

Result P10 (the gate on the honest tree; `logs/gate-primes-*.log`, `logs/safeverify-one.log`):
(a)-(d) passed for all nine (trusted inputs, the sandboxed build, type and axioms, leanchecker's kernel
replay), 18.6 minutes for (b)-(d) three leaves at a time. Layer (e) has no verdict: SafeVerify three at
a time filled swap (30.3 of 30.7 GB) and pushed free disk under the 15 GB floor, and the integrator
stopped the run at 03:09; one SafeVerify alone, under a watchdog, added 4.9 GB of swap in 36 s and was
stopped before a verdict. So "every layer passes" is right for (a)-(d) and untested for (e); the
failure was the one I named second (the tools with Mathlib), but as memory, not as an error. The wall
time (a guess of 15-40 minutes) was about right for the part that ran. Two failed attempts before it were
mine and the environment's: a gate.sh saved mid-run (a torn read, "syntax error near unexpected token
`)'"), and my adapter renaming Mathlib's `Nat.dvd_factorial`.

Correction to Result P11 (03:16): the swap rise was not one SafeVerify's. Another agent process was
running SafeVerify and comparator by hand, three at a time, on the same build from 03:10:00
(`logs/gate-primes-layer-e-killed.log`); its jobs were running when mine did, and I killed them at 03:12
thinking they were leftovers of the stopped gate run. The measurement is void.

## P12. 2026-09-30 03:17 — the gate on ONE leaf, alone, under watchdog.py (nothing else running)

Swap 19.3 GB used, disk 24 GB free, no Lean process running, at 03:15.
- all layers (a)-(e) pass for EuclidModFour: 75% (the doubt is the tools on a Mathlib project, not
  the proof);
- the peak swap rise is 2-5 GB (a guess); the watchdog stops the run at +6 GB or under 16 GB of disk;
- 8-20 minutes of wall time (five or six Mathlib loads, one after another).
