# The worked tree: infinitely many primes ≡ 3 mod 4

A spike for the fields directive (`docs/process/directives/FIELDS_DIRECTIVE.md`, "A spike: local, with
no model spend"), run on 2026-09-30 from 00:55 to 03:30 EDT. It asks four things of one real
theorem: does Graphene's plan text carry a Lean tree as it is; can the tree be a Lean project whose
leaves are checked apart and composed; what does $0 of automation close (the directive's "zero-spend
test of the thesis"); and do the checks a machine can run before spend catch a false leaf. Nothing
here called a model, a paid prover or a remote server. Every prediction was written before its
measurement, in `PREDICTIONS.md`, with the result appended beside it.

**Versions.** Lean 4.34.1 (`leanprover/lean4:v4.34.1`, commit 5045d005) and its Lake; Mathlib v4.34.1
(rev d13f23b723b8a846827a245b89c10fc7d3f11612, which pins plausible 118aa17e, aesop 355695d5,
batteries f2effa3d). In scratch projects outside this directory: Duper v4.34.1 (9e09cd05) with
lean-auto v4.34.1 (6b2774cd), Canonical v4.34.0 (0f557d23), LeanArchitect v4.34.0 (561e57d7).
Graphene from the `fields` worktree at bcf00bd, run with `uv run --project`.

**The machine, which shapes every wall time below.** Apple silicon, 11 cores, 18 GB RAM, Darwin 25.5.0.
Several agents built Lean at once, Docker Desktop's VM was given 8 GB, and swap stood at 13-26 GB used
all night (30.3 GB at the worst, section 7). A Lean process that imports Mathlib spent 30 s to 7
minutes of wall time loading it, with 3-16 s of user CPU; the rest was waiting (my reading: on the
disk, under memory pressure; APFS clones share disk blocks, so every project clone had to read
Mathlib again). Treat the wall time of a whole process as this night's, not Lean's; times measured
*inside* one process (each tactic, each check before spend) start after Mathlib is loaded and are
far less affected.

## In brief

- **The tree**: eight leaves and a root, Euclid's argument with `4·n! − 1`; two leaves carry ℕ
  subtraction (`4·0 − 1 = 0`). Graphene's plan text took it **as it is**, from the agent
  (`propose -`) and from the person (`plan edit`), and `graphene plan --text` gave it back byte for
  byte (section 2).
- **Lean**: every leaf proven by hand and checked apart (`check-leaf.sh`), the root composed from them;
  the gate's build, type/axiom and `leanchecker` layers pass on all nine. SafeVerify and comparator on
  this tree are **not verified**: the full run was stopped by the integrator for memory (swap 30.3 of
  30.7 GB), and one leaf alone was stopped by a watchdog at +6.3 GB of swap (section 7).
- **The zero-spend test**: the whole theorem closes under none of 12 tactics and hammers; 3 of 8
  leaves close for $0 in under 1.5 s (`omega`/`grind`, `exact?`, `grind +suggestions`); the key lemma
  and the argument do not. No tactic found Mathlib's own Dirichlet theorem (section 5).
- **The false leaf** ("every odd n > 1 has a prime factor ≡ 3 mod 4"): `plausible` cannot test it as
  written; on the bounded form it finds **n = 5 in 0.14 s**, and `decide` refutes n < 30 in 0.04 s. The
  vacuity test is the only check that flags a vacuous leaf (section 6).
- **Surprises**: a leaf can fake the gate file from inside its own file (fixed with `GateCheck.lean`);
  Graphene accepts a hand-back of "too hard" and offers "wait on" for a disproof (sections 2, 6, 8).
  A second agent process wrote to this directory while I worked; section 7 has the record.

## 1. The tree

Eight leaves under one sub-goal, written by hand as Graphene's planner would propose them. The proof
is Euclid's: for any n, the number 4·n! − 1 is 3 mod 4, so it has a prime factor p that is 3 mod 4,
and p cannot be ≤ n because then p would divide n! and so could not divide 4·n! − 1.

| id | leaf | needs | where Lean's conventions bite |
|---|---|---|---|
| `prime_mod_four` | a prime other than 2 is 1 or 3 mod 4 | | |
| `mul_one_mod_four` | a ≡ 1 (mod 4) ⇒ ab ≡ b (mod 4) | | |
| `factor_three_mod_four` | the key lemma: n ≡ 3 (mod 4) has a prime factor ≡ 3 (mod 4) | the two above | |
| `euclid_mod_four` | 4P − 1 ≡ 3 (mod 4) when P > 0 | | ℕ subtraction: 4·0 − 1 = 0, so without `0 < P` it is false at P = 0 |
| `not_dvd_euclid` | a prime dividing P does not divide 4P − 1 | | ℕ subtraction again: at P = 0, 4P − 1 = 0 and every p divides 0 |
| `dvd_factorial` | 0 < p ≤ n ⇒ p ∣ n! | | |
| `euclid` | the argument: the root from the four leaves it needs | key lemma, both ℕ-subtraction leaves, `dvd_factorial` | |
| `set_form` | "for every n there is a larger one" gives "the set is infinite" | `euclid` | |

The root is stated the way a person asks it, `S_root : ∀ n : ℕ, ∃ p, n < p ∧ p.Prime ∧ p % 4 = 3`, and
also in the form Mathlib states such results, `S_root_set : {p : ℕ | p.Prime ∧ p % 4 = 3}.Infinite`.
Mathlib already contains the theorem, as a corollary of Dirichlet's theorem (section 5): the spike
tests mechanics, not a prover.

The text form is `tree.txt`, the file Graphene was given, unchanged. Each leaf's scope is its own
`Proofs/<Leaf>.lean` and its check is `./check-leaf.sh <Leaf>`; the sub-goal's check is
`./check-leaf.sh Root`, which Graphene runs when the last leaf is done (the roll-up, HOW_IT_WORKS P1a):
that is where the composition is checked. Each leaf's prose carries its Lean statement on one line,
`Lean: S_x := <statement>`, which Graphene reads as "what it should achieve" and `tree2lean.py` reads
as Lean.

```
goal: a machine-checked proof in Lean 4 that there are infinitely many primes congruent to 3 mod 4: for every n there is a prime p > n with p % 4 = 3

- there are infinitely many primes congruent to 3 mod 4  [primes-3-mod-4]
    past every n there is a prime p with p % 4 = 3, and so the set of such primes is infinite
    Lean: S_root := ∀ n : ℕ, ∃ p, n < p ∧ p.Prime ∧ p % 4 = 3
    Lean: S_root_set := {p : ℕ | p.Prime ∧ p % 4 = 3}.Infinite
    Proofs/Root.lean is written from this tree (each leaf applied to the leaves it needs), never by a leaf
    check: ./check-leaf.sh Root
  - a prime other than 2 is 1 or 3 mod 4  [prime_mod_four]
      Lean: S_prime_mod_four := ∀ p : ℕ, p.Prime → p ≠ 2 → p % 4 = 1 ∨ p % 4 = 3
      scope: Proofs/PrimeModFour.lean
      check: ./check-leaf.sh PrimeModFour
  - multiplying by a number that is 1 mod 4 keeps the residue mod 4  [mul_one_mod_four]
      Lean: S_mul_one_mod_four := ∀ a b : ℕ, a % 4 = 1 → a * b % 4 = b % 4
      scope: Proofs/MulOneModFour.lean
      check: ./check-leaf.sh MulOneModFour
  - a number that is 3 mod 4 has a prime factor that is 3 mod 4  [factor_three_mod_four]
      the key lemma, proved with its needs taken as hypotheses
      Lean: S_factor_three_mod_four := ∀ n : ℕ, n % 4 = 3 → ∃ p, p.Prime ∧ p ∣ n ∧ p % 4 = 3
      scope: Proofs/FactorThreeModFour.lean
      check: ./check-leaf.sh FactorThreeModFour
      needs: prime_mod_four, mul_one_mod_four
  - Euclid's number 4P - 1 is 3 mod 4 when P > 0  [euclid_mod_four]
      the convention that bites: subtraction in ℕ stops at 0, so 4 * 0 - 1 = 0, and without 0 < P the statement is false at P = 0
      Lean: S_euclid_mod_four := ∀ P : ℕ, 0 < P → (4 * P - 1) % 4 = 3
      scope: Proofs/EuclidModFour.lean
      check: ./check-leaf.sh EuclidModFour
  - a prime that divides P does not divide 4P - 1  [not_dvd_euclid]
      the same convention: at P = 0, 4P - 1 is 0 in ℕ and every p divides 0, so 0 < P is needed here too
      Lean: S_not_dvd_euclid := ∀ P p : ℕ, 0 < P → p.Prime → p ∣ P → ¬ p ∣ 4 * P - 1
      scope: Proofs/NotDvdEuclid.lean
      check: ./check-leaf.sh NotDvdEuclid
  - every p with 0 < p ≤ n divides n!  [dvd_factorial]
      Lean: S_dvd_factorial := ∀ p n : ℕ, 0 < p → p ≤ n → p ∣ Nat.factorial n
      scope: Proofs/DvdFactorial.lean
      check: ./check-leaf.sh DvdFactorial
  - Euclid's argument: 4·n! - 1 has a prime factor that is 3 mod 4, and it cannot be ≤ n  [euclid]
      Lean: S_root, the statement of the sub-goal above
      scope: Proofs/Euclid.lean
      check: ./check-leaf.sh Euclid
      needs: factor_three_mod_four, euclid_mod_four, not_dvd_euclid, dvd_factorial
  - the "for every n" form gives the "infinite set" form  [set_form]
      Lean: S_root_set, the second statement of the sub-goal above
      scope: Proofs/SetForm.lean
      check: ./check-leaf.sh SetForm
      needs: euclid
```

## 2. What Graphene said about the text

All in scratch repositories under `scratchpad/graphene-scratch/` (git clones of this Lean project, no
`.lake`, no hooks: `graphene init` was never run). Transcripts are in `logs/graphene/`.

**The person's acts.** For the person's commands in those scratch repositories only, I followed
decision 95's precedent: `logs/graphene/as-person.sh` drops every agent mark the source names
(`CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_ENTRYPOINT`, `CODEX_SESSION_ID`, `CODEX_SANDBOX`,
`AI_AGENT`, `GEMINI_CLI`, `CURSOR_AGENT`, `GRAPHENE_NODE`, `GRAPHENE_PLANNER`; `plan.caller` and
`night.MARKS`) and sets `GRAPHENE_AS=person:alex`, so the log marks those acts "(no terminal)". The
agent's acts ran in my own shell, which carries Claude Code's marks. `$EDITOR` for `plan edit` was a
script (`accept-all.sh` turns every `? ` into `- `; `paste.sh` replaces the buffer with `tree.txt`).

| act | who | result |
|---|---|---|
| `graphene plan propose - < tree.txt` | agent | accepted as it is: the goal and 9 nodes proposed, exit 0 (`01-propose-agent.txt`) |
| `graphene plan edit`, every `?` made `-` | person | all 9 accepted, exit 0 (`03-edit-accept-person.txt`) |
| `graphene plan edit` in a fresh repository, `tree.txt` pasted as it is | person | the goal and 9 nodes added, exit 0 (`05-edit-fresh-person.txt`) |
| the same two with the final `tree.txt` (one `Lean:` line per statement) | both | accepted, exit 0 (`10-v2-agent.txt`, `11-v2-person.txt`) |
| `graphene plan --text` after each | | **round-trips**: with Graphene's `#` notes and blank lines removed and `?` read as `-`, `diff` against `tree.txt` is empty, all four times |

**No refusal on the tree itself.** To find where the grammar bites a mathematician, I proposed eight
Lean-flavoured variants (`12-grammar-probes.txt`). Four were refused, verbatim:

- `needs: Nat.Prime.eq_two_or_odd` (a Mathlib lemma where Graphene wants a node id): "line 5: needs:
  'Nat.Prime.eq_two_or_odd' is not the id of a node (the line was read as needs:, which names the [id]s
  it waits on)". A mathematician's "uses" is not Graphene's `needs:`.
- A prose line that begins with a minus sign, `- 1 is subtracted in ℕ, where 0 - 1 = 0`: read as a
  child node, so the next key line was refused: "line 4: 'scope: Proofs/En.lean' is not indented under
  [1 is subtracted in ℕ, where 0 - 1 = 0], the node just above it (a Tab counts as 4 columns). A node's
  own lines go right under its line, before its children". A mathematician's note may well start
with a minus sign (a guess about how often).
- `Test: plausible finds no counterexample for P < 100`: "line 2: 'test:' is not read; say it with
  check:".
- A leaf with only its Lean statement: "line 1: 'Euclid number' is a new leaf with no scope and no check
  ('Lean: S_en := ∀ P : ℕ, 0 < P →' was read as what it should achieve; the keys are scope: and check:)".

Accepted as prose: a full `theorem … := by omega` line, a `statement:` line, a `/-- … -/` docstring, a
numbered hypothesis list.

**What Graphene did with the accepted tree** (`04-plan-after-accept.txt`): `factor_three_mod_four`,
`euclid` and `set_form` show `waiting`. `needs:` is order in Graphene (P1a), but in this layout a leaf
takes its needs as hypotheses and can be proven before them; all eight leaves could run at once. With
today's Graphene the way to say that is to leave `needs:` out and let the sub-goal's own check
(`./check-leaf.sh Root`, run at the roll-up) be the integration; the logical dependency then lives
only in the Lean types (the gates). I kept `needs:` in `tree.txt` because it carries the dependency
into Lean (section 4) and into LeanArchitect's graph; it costs parallelism, not correctness.

**A leaf through the gate.** In the scratch repository the agent took the seeded false leaf
(section 6), wrote a `sorry` proof and ran `graphene node done odd_factor_three`
(`09-done-seeded.txt`). Graphene ran `./check-leaf.sh OddFactorThree` in a clean worktree of the
leaf's state, which has no `.lake` (git ignores it); `check-leaf.sh` (its first version, section 3)
borrowed the main checkout's Mathlib by symlinking `.lake/packages`, and rebuilt `Seeded`, the proof
and the gate there. Refused, in **903 s** of wall time (15.9 s user) under this night's memory
pressure: "odd_factor_three is not done: `./check-leaf.sh OddFactorThree` failed: / check-leaf OddFactorThree: uses axioms beyond the
standard three: sorryAx". Then, with the scratch repository moved to the final `check-leaf.sh`
(GateCheck, section 3), the agent took `euclid_mod_four`, wrote its two-line proof and ran `graphene
node done euclid_mod_four` (`15-done-true-leaf.txt`): "euclid_mod_four is done (check passed, nothing
outside its scope)", in **432 s** of wall time (13.5 s user). So the check runs inside Graphene's gate
unchanged, both ways, and each `done` pays three Mathlib loads in a fresh worktree (`Challenge` or
`Seeded`, the proof, and the check); a warm Lean server, or a worktree that shares a trusted build, is
what would make it cheap.

**The hand-back is not asked for a defect.** The contract Graphene printed at `node start` says
"stuck: graphene node release odd_factor_three --why '<what is in the way>'". `plan.release` refuses
only an empty reason. `13-escape-hatch.txt`: the agent took `dvd_factorial`, the leaf `exact?` closes
in 0.015 s (section 5), and handed it back with `--why "too hard"`; Graphene accepted it and shows
"↩ … came back · handed back: too hard". LeanMarathon's escape-hatch problem is open in Graphene as
it stands.

Two small things seen on the way: a node's goal written over several lines is printed in the
contract (`why:` and `goal:`) with its second and later lines at the left margin (`08-accept-start-seeded.txt`); and a
prose line of Lean is carried faithfully, Unicode included, through propose, edit, `--text` and the
contract.

## 3. The Lean project

Option 4 of the directive, as the integrator specified it:

| file | written by | read-only to leaves | what it holds |
|---|---|---|---|
| `lean-toolchain`, `lakefile.toml`, `lake-manifest.json` | the tree | yes | the pinned toolchain and Mathlib |
| `Challenge.lean` | the tree | yes | every statement as `def S_<leaf> : Prop := …`, and `S_root`, `S_root_set` |
| `Seeded.lean` | the tree | yes | the three seeded defects (section 6), apart from the honest tree |
| `Proofs/<Leaf>.lean` | the leaf | its only writable file | `theorem <leaf> : S_<need₁> → … → S_<leaf>`; imports `Challenge` only |
| `Gate/<Leaf>.lean` | `write-gates.sh`, from the tree | yes | `example : <the type> := <leaf>` and `#print axioms <leaf>` |
| `Proofs/Root.lean`, `Gate/Root.lean` | the tree | yes | `root := euclid (factor_three_mod_four prime_mod_four mul_one_mod_four) …`, `root_set := set_form root` |
| `check-leaf.sh LEAF`, `GateCheck.lean` | the tree | yes | the fast check (below) |
| `trusted.sha256` | the tree | yes | SHA-256 of the read-only files above, except `check-leaf.sh` (which reads it) and itself |

Because `euclid` is itself a leaf (the argument, from four hypotheses), `Proofs/Root.lean` is pure
application and can be written from the tree, so no leaf writes it.

**`check-leaf.sh LEAF`** exits 0 only when: the read-only files (with `GateCheck.lean`) match
`trusted.sha256`; the proof file imports only `Challenge`, `Seeded` or Mathlib (never another leaf's
proof; skipped for `Root`); `lake build Proofs.LEAF` succeeds; and `GateCheck.lean`, run on the
compiled module, finds each theorem that `Gate/LEAF.lean` names declared in `Proofs.LEAF`, of the type
`Gate/LEAF.lean` states (`S_need₁ → … → S_leaf`, by the kernel's definitional equality, with every
`S_…` from `Challenge` or `Seeded`), and depending on no axiom beyond `propext`, `Classical.choice`,
`Quot.sound` (so `sorry`, a declared axiom and `native_decide` fail it).

*Why not just compile `Gate/LEAF.lean`*, as the first version did and as the layout suggested: the
gate file imports the leaf, so the leaf's own syntax is in force when the gate is parsed. In
`hijack/` (core Lean, `hijack/run.sh`, 15 s) a leaf's file declares `macro "S_false_leaf" : term =>
`(True)` and a higher-priority `#print axioms` syntax; its gate file then compiles and prints
"'false_leaf' depends on axioms: [propext]", exit 0, for a statement that is `1 = 2`. `GateCheck.lean`
is parsed before anything of the leaf is loaded (it imports the compiled module at run time) and says
"GateCheck false_leaf: FAIL: false_leaf : True, not S_false_leaf". I rewrote `check-leaf.sh` at 02:00
and reran every check through it. `Gate/<Leaf>.lean` stays as the human-readable statement of each
type, the text GateCheck reads, and the file `../gate` compiles.

What the fast check does not claim to catch (not tested here; the red team's spike tests them): a
proof term the kernel never checked (an option such as `debug.skipKernelTC` in the leaf's own
module), and a build under `.lake` changed behind git's back.
Both are the gate's job (`leanchecker`, `comparator`; section 7). The second is specific to running
under Graphene: in a worktree with no `.lake` the check borrows the packages of the checkout the
worktree was cut from (or `$PRIMES_LAKE`) by symlink; that build is git-ignored, so outside every
scope, and a leaf that wrote into it would not be seen by Graphene's boundary.

**Every leaf proven by hand**: the eight proofs are 64 lines from `theorem` to the end (the key lemma
is 29 of them: strong induction on n through `Nat.minFac`), and `Proofs/Root.lean` is two terms. `check-all.sh` runs every check in turn:

| leaf | result | wall | axioms (`collectAxioms`) |
|---|---|---|---|
| `PrimeModFour` | proven | 140 s | `prime_mod_four`: propext, Quot.sound |
| `MulOneModFour` | proven | 114 s | `mul_one_mod_four`: propext |
| `FactorThreeModFour` | proven | 50 s | `factor_three_mod_four`: propext, Classical.choice, Quot.sound |
| `EuclidModFour` | proven | 66 s | `euclid_mod_four`: propext, Quot.sound |
| `NotDvdEuclid` | proven | 60 s | `not_dvd_euclid`: propext, Quot.sound |
| `DvdFactorial` | proven | 38 s | `dvd_factorial`: propext |
| `Euclid` | proven | 32 s | `euclid`: propext |
| `SetForm` | proven | 60 s | `set_form`: propext, Classical.choice, Quot.sound |
| `Root` | proven | 165 s | `root`: propext, Classical.choice, Quot.sound; `root_set`: propext, Classical.choice, Quot.sound |
| `OddFactorThree` | **not proven** (the seeded false leaf: its `sorry`) | 456 s | `odd_factor_three` uses `sorryAx` |

`logs/check-final.log`, 02:19-02:39, every check through the final `check-leaf.sh`. The walls are this
night's: a leaf's check was one `lake build` that found the proof already built plus one Mathlib
load for GateCheck, 32-140 s depending on what else was reading the disk; Root and the false leaf
first compiled their proof module, a second load (165 s and 456 s). Earlier passes, with the
first check-leaf.sh and with GateCheck's first version, are in `logs/check-all.log` (115-634 s a
leaf there, while the automation baseline and other agents' builds ran beside them).

## 4. Do the three forms round-trip?

**Graphene text → Lean: yes, mechanically, under one convention.** `tree2lean.py` reads `tree.txt`
with Graphene's own parser (`graphene_map.plan_text.parse`) and prints the `def S_x : Prop := …` of
every `Lean: S_x := …` line and one `File|theorem|type` row per leaf, the type built from `needs:` in
order. Both match what is in the project: the eight definitions equal `Challenge.lean`'s line for line
(`diff` empty) and the eight rows equal `write-gates.sh`'s table (`diff` empty) (`logs/tree2lean.out`).
The chain through Graphene closes too: `tree2lean.py` run on the text `graphene plan --text` printed
from the store (`logs/graphene/10-v2-agent.txt`, proposals, notes and all) gives output identical to
`tree2lean.py` on `tree.txt` (`diff` empty).

**Lean → Graphene text: by the same convention, with loss; argued from the files, not scripted.**
Statements come back from `Challenge.lean`, scope and check from the file names, and `needs:` from
the gate types, except that a type names statements (`S_root`), not leaves (`euclid`), so a table
from statement to leaf is needed where two leaves share one; titles would come from the docstrings,
which say the same thing in other words. What Graphene alone carries is lost: the goal sentence
(unless kept as a module docstring), `owner:`, `signoff:`, proposal or accepted, the state and the log, the board's questions
and answers, and the difference between order (`needs:`) and meaning (the hypotheses).

**LeanArchitect: in part.** I wrote the tree as LeanArchitect `@[blueprint]` attributes, added after
the fact (`attribute [blueprint "label" (title := …) (statement := /-- LaTeX -/) (uses := […])] name`, in
`blueprint/Blueprint.lean`) so the challenge and the proofs stay as the gate checks them. With
LeanArchitect v4.34.0 in a scratch project, the whole thing compiled as one file
(`blueprint/BlueprintAll.lean`: Challenge, the proofs, Root and the attributes; 328 s, nearly all of
it loading Mathlib), and `#show_blueprint` printed nine nodes, each `\leanok` because no `sorryAx`
is among the constants it uses (`blueprint/nodes.tex`). Two things did not carry over by themselves.
First, **LeanArchitect infers no edge between leaves in this layout**: a leaf never mentions another
leaf, only its needs' statements (`S_…`, untagged definitions), so the edges
`factor_three_mod_four → prime_mod_four, mul_one_mod_four`, `euclid → its four` and
`set_form → euclid` exist only because I wrote `uses := [...]` by hand, the same list as Graphene's
`needs:`. It did infer that the root's proof uses all eight leaves, through `Proofs/Root.lean`.
Second, it put those `uses` on the statement (`\uses` inside `\begin{theorem}`), which leanblueprint
reads as "needed to state it"; that is defensible here, since the leaf's type names its needs'
statements, but it is not what Graphene's `needs:` says. Graphene text → LeanArchitect is therefore
mechanical (id = label, title = title, `needs:` = `uses`); the English goal line → a LaTeX
`statement` is not, and LeanArchitect → Graphene gives no scope and no check. The time box was 30
minutes; the build ran a few minutes past it, unattended.

What each form carries that the others lose:

| | Graphene text | Lean challenge | LeanArchitect |
|---|---|---|---|
| the person's goal sentence, owner, sign-off, state, log, the board | yes | no (a docstring at most) | no |
| scope (what a leaf may write) and check (what makes it done) | yes | by convention (file names) | no |
| the statement as a typed, checked object; the definitions under it | only as prose | yes | yes (it is Lean) |
| which need feeds which hypothesis | no (`needs:` names the ids, not which hypothesis each fills) | yes (the type) | no (`uses` is a set of labels) |
| dependency as order (what waits) vs as meaning (what is used) | order only | meaning only | meaning, inferred from constants used |
| proven or not | state, from Graphene's own run of the check | the build and `#print axioms` | `\leanok`, inferred from no `sorryAx` |
| English (or LaTeX) beside the Lean | titles and prose | docstrings | `statement :=` LaTeX, rendered |

## 5. The zero-spend test of the thesis: what automation closes

`Auto/run.py` writes `Auto/Baseline.lean`, one theorem per goal and tactic, and runs it in one Lean
process (Mathlib loaded once). Each attempt goes through `attempt` (`Auto/Harness.lean`): the goal
is the statement as written with its definition unfolded, and for a leaf its needs' statements are
hypotheses in context (`intro h0 h1 …; unfold …`). **The limit is 60 s of wall clock per tactic per
goal**, enforced inside Lean by a cancellation token the harness sets after 60 s (a tactic stops at its
next interrupt check; the theorem is then abandoned, which is how a timeout shows). **Heartbeats:
`maxHeartbeats 0` (unlimited) inside each attempt**, so the wall clock is the only limit;
`synthInstance.maxHeartbeats` stays at its default. A cell counts as closed only if the tactic left
no goal, logged no error, and `#print axioms` on its theorem showed nothing beyond the standard three
(every closed cell below passed that; a failed one was closed with `sorry` so the file went on, and
shows `sorryAx`). Tactics: the directive's seven, plus `simp_all` (the `simp` that uses the
hypotheses) and core's two local relatives of a hammer, `grind +suggestions` and `try?` (Lean 4.34's
library-suggestion engine, a local selector: nothing leaves the machine). The first `exact?` in the
process builds its index of Mathlib: 40.6 s, paid once, on a warm-up goal outside the table.

Seconds when closed, x failed, T timed out at 60 s (full cells with each error's first line:
`Auto/baseline.md`; run 01:32-01:49, 1047 s for all 140 cells):

| goal | decide | norm_num | simp | simp_all | omega | aesop | exact? | grind | grind+suggestions | try? |
|---|---|---|---|---|---|---|---|---|---|---|
| `root` | x | x | x | x | x | x | x | x | x | x |
| `root_set` | x | x | x | x | x | x | x | x | x | x |
| `prime_mod_four` | x | x | x | x | x | x | x | x | x | x |
| `mul_one_mod_four` | x | x | x | x | x | x | x | x | **0.58** | **1.49** |
| `factor_three_mod_four` | x | x | x | x | x | x | x | x | T | T |
| `factor_three_mod_four_bare` | x | x | x | x | x | x | x | x | T | T |
| `euclid_mod_four` | x | x | x | x | **0.08** | x | x | **0.18** | **0.45** | **1.46** |
| `not_dvd_euclid` | x | x | x | x | x | x | x | x | x | x |
| `dvd_factorial` | x | x | x | x | x | x | **0.01** | x | **0.79** | **0.51** |
| `euclid` | x | x | x | x | x | x | x | x | x | x |
| `set_form` | x | x | x | x | x | x | x | x | x | x |
| `odd_factor_three` | x | x | x | x | x | x | x | x | T | T |
| `euclid_mod_four_any` | x | x | x | x | x | x | x | x | x | T |
| `even_three_mod_four` | x | x | x | x | **0.07** | x | x | **0.26** | **0.64** | **1.52** |

**The whole theorem** closes under nothing, in either form. **Three of the eight leaves close, for
$0, in under 1.5 s each**: the ℕ-subtraction leaf `euclid_mod_four` (omega 0.08 s, grind 0.18 s),
`dvd_factorial` (`exact?` in 0.015 s, finding `Nat.dvd_factorial`), and `mul_one_mod_four` (only
`grind +suggestions`, 0.58 s, and `try?`, which proposes `grind only [Int.mul_emod]`). **Five do not**:
the key lemma (with or without its needs as hypotheses), `prime_mod_four`, `not_dvd_euclid`, the
argument `euclid`, and `set_form`. So the thesis holds here in its weak form: the tree turned work no
cheap tool could do into some work cheap tools do for nothing, but the leaves that carry the proof
(the key lemma and the argument) still need a prover or a person. By hand, `prime_mod_four` is one
Mathlib lemma and `omega` (`Nat.Prime.eq_two_or_odd`), and `not_dvd_euclid` is six tactic lines around
`Nat.dvd_sub`; no tactic found either.

**Hammers, installed locally** (the 45-minute install box ran 01:23-01:46; `PREDICTIONS.md` P5,
P7). Duper v4.34.1 (with lean-auto v4.34.1) and Canonical v4.34.0 resolved beside Mathlib with no conflict in 31 s and
built in 110 s. LeanHammer did not: it supports Lean up to v4.33.0, and against Mathlib v4.34.1 its
build failed after 267 s in lean-smt ("Invalid field `canUnfold?`: The environment does not contain
`Lean.Meta.Context.canUnfold?`", an API Lean 4.34 removed); its default premise selector is a remote
server (`../../../landscape.md` §3), so I would not have used it that way anyway. I did not try a second
Mathlib at v4.33 (7.6 GB more, and the box). Duper and Canonical ran in a separate project on the same
14 goals (`Auto/hammers.md`, `logs/hammers-20260930-021145.log`), with `duper [*]` (the hypotheses
only: Duper takes no premises from the library unless it is handed them) and `canonical 55` (its own
timeout, 55 s). Duper needed a heartbeat budget: it splits `maxHeartbeats` among its portfolio
instances and stops on heartbeats, not on the harness's cancellation token, so with the baseline's
`maxHeartbeats 0` it ran on `prime_mod_four` for more than three minutes of CPU, twice, before I
stopped it (`logs/hammers-first-try-stuck.log`, `logs/hammers-second-try-stuck.log`; a tactic-level
`set_option maxHeartbeats` does not reach `Core.Context.maxHeartbeats`, which is what Duper reads).
The run that counts gave every attempt 1,000,000 heartbeats (five times Lean's default):

| hammer | closed | time per goal | what it said |
|---|---|---|---|
| `duper [*]` | **0 of 14** | 0.03-0.34 s; 9.7 s on the key lemma with its needs | "Duper failed to solve the goal and determined that it will be unable to do so with the current configuration of options and selection of premises"; on the key lemma, "Duper encountered a (deterministic) timeout. The maximum number of heartbeats 1000000 has been reached" |
| `canonical 55` | **0 of 14**, and no term suggested | 55.1-56.1 s (its whole timeout) | "No proof found. Supply constant symbols with `canonical [name, ...]`" |

Neither is surprising for goals that need number theory and a library: Duper proves first-order
consequences of what it is handed, and here it was handed only the hypotheses; Canonical searches
type-theoretic terms from the local context and whatever constants it is given. Given the right
Mathlib lemmas, either might close a leaf (untested), but choosing them is premise selection, which
is exactly the part a person or a model would supply. Run 02:11-02:29, 1037 s.

**Contamination by the library.** Mathlib contains the theorem: Dirichlet's theorem is
`Nat.forall_exists_prime_gt_and_modEq` (Mathlib/NumberTheory/LSeries/PrimesInAP.lean), and
`root_by_dirichlet` in `Falsify/Run.lean` closes `S_root` with it in one application
(it checks with the standard three axioms). **No tactic found it**: `exact?` failed on `S_root` in 3.2 s and on `S_root_set` in
0.4 s, and neither `grind +suggestions` nor `try?` suggested it (both failed). Mathlib states it with `p ≡ a [MOD q]` (a `Nat.ModEq`) and with `(p : ZMod q) = a`; the person's `p % 4 = 3`
matches neither syntactically, and my guess (not tested) is that this is why `exact?`'s index missed
it. So the table's "the whole theorem fails" is a fact about these tactics and this phrasing, not
about what the library knows: a model that remembers the lemma's name would close the root in one
line and learn nothing about the tree (an inference; no model was run). `dvd_factorial` is
contaminated in the small: it *is* `Nat.dvd_factorial`.

**Closed suspiciously easily** (by a tactic in under a second):

| leaf | by | why it was easy | trivial, or wrong? |
|---|---|---|---|
| `euclid_mod_four` | omega 0.08 s, grind 0.18 s | linear arithmetic once `0 < P` is a hypothesis | trivial and right; its hypotheses are satisfiable (section 6), and dropping `0 < P` makes it false, which omega does not prove |
| `dvd_factorial` | exact? 0.015 s | it is a Mathlib lemma, word for word | trivial and right |
| `mul_one_mod_four` | grind +suggestions 0.58 s | one lemma (`Int.mul_emod`) and arithmetic | trivial and right |
| `even_three_mod_four` (seeded) | omega 0.07 s, grind 0.26 s | **its hypotheses contradict each other** | **vacuous**: true and says nothing; the vacuity test flags it (section 6) |

The ease alarm alone cannot tell the vacuous leaf from the three honest ones: all four close in under
a second. The vacuity test can.

## 6. The seeded false leaf, and two other seeded defects

`Seeded.lean` holds three statements a tired planner might write, apart from the honest tree:

- **`odd_factor_three`**, FALSE at n = 5: `∀ n : ℕ, n % 2 = 1 → 1 < n → ∃ p, p.Prime ∧ p ∣ n ∧ p % 4 = 3`,
  "every odd n > 1 has a prime factor that is 3 mod 4". It would replace the key lemma and make
  Euclid's argument look easier. `tree-seeded.txt` proposes it as a leaf.
- **`euclid_mod_four_any`**, FALSE at P = 0: the ℕ-subtraction off-by-one, `euclid_mod_four` without
  `0 < P`.
- **`even_three_mod_four`**, VACUOUS: `∀ n, n % 4 = 3 → n % 2 = 0 → …`; no n meets both hypotheses,
  so it holds and says nothing.

The checks a machine can run before any spend are in `Falsify/Run.lean`, with the two commands of
`Falsify/Checks.lean` (which imports only Plausible, and compiles in 3 s). `#falsify` runs
`plausible` on the statement as written. `#vacuity` runs `plausible` on `∀ xs, ¬ (H₁ ∧ … ∧ Hₖ)`,
whose counterexample is an example where every hypothesis holds; if none turns up, it asks
`omega`, `decide`, `simp_all` and `grind` to prove that none exists. `decide` runs on bounded
instances. Times are inside Lean, after Mathlib was loaded (`logs/falsify-run.log`, run 01:56-02:04):

| check before spend | `odd_factor_three` (false) | `euclid_mod_four_any` (false) | `even_three_mod_four` (vacuous) | the honest leaves |
|---|---|---|---|---|
| `plausible` on the statement as written | **cannot test**, 0.020 s: "Failed to create a `testable` instance" (the `∃ p` is unbounded) | **counterexample P = 0**, 0.064 s | cannot test, 0.019 s (same `∃ p`) | none found on the five decidable ones (0.07-0.21 s); cannot test the key lemma or `S_root` (`euclid`'s conclusion) |
| `plausible` on the bounded form (`∃ p ≤ n`, a rewrite by the machine) | **counterexample n = 5**, 0.142 s | | | bounded key lemma: none found, 0.096 s |
| `decide` on small instances | bounded form **false** for n < 30 in 0.042 s, n < 10 in 0.031 s | **false** for P < 10 in 0.002 s | | bounded key lemma for n < 30 **proved** in 0.043 s; `euclid_mod_four` for P < 10 in 0.003 s |
| vacuity test | hypotheses satisfiable (n = 3), 0.090 s | no hypotheses | **VACUOUS**: no example; `omega` proves none exists, 0.150 s | the six with hypotheses of their own: all satisfiable, each with an example, 0.06-0.18 s |
| automation (section 5) | closes under nothing | closes under nothing | **closes** under omega in 0.07 s | 3 of 8 close |

So each defect is caught by the machine, before any proof attempt, in well under a second of Lean
time, but not by one check alone: the false leaf needs the bounded rewrite (or `decide` on it)
because `plausible` cannot test an unbounded `∃`; the off-by-one is caught by plain `plausible`
(omega fails on it, but a failure is not a counterexample); no falsification check flags the vacuous
leaf (there is nothing false to find, and plausible cannot even test it), only the vacuity test
does, while automation closes it as fast as the honest leaves that close (0.07 s against 0.015–0.58 s; corrected by the integrator from "faster than any honest leaf"). The bounded rewrite is the machine's, and it is equivalent to the statement only by
the fact that a divisor of a positive n is at most n: a person, or a proof, has to accept that step.

**The hand-back.** In the scratch repository the agent took `odd_factor_three`, its `done` was refused
(section 2), and it handed the leaf back with the witness (`logs/graphene/14-handback-seeded.txt`):

> false as stated, so no proof exists. Counterexample n = 5: 5 is odd and > 1, its only prime factor
> is 5 (5 = 5), and 5 % 4 = 1, so no prime factor of 5 is 3 mod 4. Found before any proof attempt:
> plausible on the bounded form (∃ p ≤ n) found n = 5 in 0.14 s (it cannot test the statement as
> written: the ∃ p is unbounded); decide proved the bounded form false for n < 30 in 0.04 s; the
> negation is proved in Falsify/Run.lean (odd_factor_three_false, standard axioms). Every
> counterexample below 60: 5, 13, 17, 25, 29, 37, 41, 53, the odd n whose prime factors are all 1 mod
> 4. What holds instead: n % 4 = 3 in place of n odd, which is factor_three_mod_four, already in the
> plan.

Graphene kept it whole in `node show` and cut it after 97 characters on the plan's row ("↩ … came
back · handed back: false as stated, so no proof exists. Counterexample n = 5: 5 is odd and > 1, its
only prime facto…"). Then it **offered the wrong fix**: because the reason names a node id,
`plan.offers` proposed "make odd_factor_three wait on factor_three_mod_four: `graphene node set
odd_factor_three --needs factor_three_mod_four`" (decision 32's third offer). Waiting cannot repair
a false statement; the fix is to drop the leaf or replace its statement, which is the person's act.
And the same screen shows `dvd_factorial` "came back · handed back: too hard" with the same glyph and
the same word: Graphene today cannot tell a hand-back that carries a checkable witness from one that
carries none. A Lean-shaped hand-back would carry the witness as something a check runs (here
`odd_factor_three_false : ¬ S_odd_factor_three`, compiled like a leaf), and Graphene would accept
"false" only when that check passes.

## 7. The gate from `../gate`

`../gate/gate.sh` existed when I finished; I ran its versions of 02:08, 02:25 (md5
5608679374befd825b85ebf58471d11b), 02:36 and 03:14 (md5 7a52aa6e…). Its layout differs
from this one in two ways: each leaf also has `Spec/<Leaf>.lean`, its statement with `sorry` (the
challenge SafeVerify and comparator compare the solution against), and a leaf's theorem is named after its file with a
lower-case first letter (`PrimeModFour` → `primeModFour`). `to-gate-layout.sh DEST` makes such a copy
mechanically: it renames the theorems, writes each `Spec/` file from its gate type, commits the
trusted tree, then copies the proofs in as the candidate. It also puts the project one directory
down, because **gate.sh failed with the project at the repository root**: my first run printed
"fatal: empty string is not a valid pathspec. please use . instead if you meant to match all paths",
then "(a) trusted inputs FAIL … Challenge.lean (not in the trusted tree) … FalseLeaf: a Proofs/Spec/Gate
file is missing" (`git rev-parse --show-prefix` is empty at the root, and `git ls-tree -- ""` refuses
it), and every later layer failed on "no default toolchain configured". Moving the project into a
subdirectory fixed it; the gate's author should know.

**The hijack through the gate** (`hijack/gate-layout/run-gate.sh`, core Lean, 7 s;
`logs/hijack-gate.log`, the 02:25 version; the 02:08 version gave the same lines), the same leaf
file as in section 3 in the gate's layout:

```
(a) trusted inputs   pass      0.2s  5 files from e5dd9532…; none differed; .lake cloned
    trusted build    pass      1.8s  Challenge, Spec.* (reused from the trusted .lake when unchanged)
(b) lake build       pass      0.4s  Proofs.FalseLeaf (sandboxed; sorry warnings: 0)
(c) type + axioms    pass      0.3s  falseLeaf: [propext];
(d) kernel replay    pass      0.7s  leanchecker Proofs.FalseLeaf
(e) SafeVerify       FAIL      2.0s  rejected FalseLeaf: Found a problem in .lake/build/lib/lean/Proofs/FalseLeaf.olean with declaration falseLeaf: theorem type mismatch
(e) comparator       FAIL      1.6s  rejected FalseLeaf: uncaught exception: Challenge and solution theorem statement do not match: 'falseLeaf'
gate: FAIL
```

So the gate as a whole holds: its layer (c), which compiles the gate file after importing the leaf,
is fooled exactly as my first check was, and `leanchecker` has nothing to object to (`falseLeaf :
True` is a correct theorem); SafeVerify and comparator, which compare the compiled statement with
the trusted `Spec`, both reject it.

**The honest tree through the gate.** Two attempts failed before the one below, neither on a proof:
the first (02:30) died after the trusted build with "gate.sh: line 125: syntax error near unexpected
token `)'", most likely because the gate's author saved a new gate.sh while bash was still reading
the old one (its modification time, 02:36, falls inside my run; `logs/gate-primes-first-try.log`);
I then ran a snapshot of the gate directory (gate.sh md5 f1d5f1581405befb555c03b59111d2ba, the
02:36 version), with the trusted `.lake` that first attempt had
built from the trusted commit alone. The second (02:40) failed at (b) with "Unknown constant
`Nat.dvdFactorial`": my `to-gate-layout.sh` had renamed Mathlib's `Nat.dvd_factorial` along with the
leaf (`logs/gate-primes-second-try.log`); the rename now spares names after a dot. The third, on all
eight leaves and the root, three leaves at a time (`GATE_JOBS=3`), `logs/gate-primes-third-try-killed.log`
(of the gate's own per-layer logs, those saved for `EuclidModFour` are in `logs/gate-primes-logs/`):

```
(a) trusted inputs   pass     27.9s  22 files from 2e03594b…; none differed; .lake cloned
    trusted build    pass      8.7s  Challenge, Spec.* (reused from the trusted .lake when unchanged)
(b) lake build       pass    366.1s  Proofs.PrimeModFour … Proofs.Root (sandboxed; sorry warnings: 0)
(c) type + axioms    pass    321.4s  primeModFour: [propext, Quot.sound]; mulOneModFour: [propext];
                                     factorThreeModFour: [propext, Classical.choice, Quot.sound];
                                     euclidModFour: [propext, Quot.sound]; notDvdEuclid: [propext, Quot.sound];
                                     dvdFactorial: [propext]; euclid: [propext];
                                     setForm: [propext, Classical.choice, Quot.sound];
                                     root: [propext, Classical.choice, Quot.sound]
(d) kernel replay    pass    427.2s  leanchecker Proofs.PrimeModFour … Proofs.Root
(e) SafeVerify, comparator: no result (stopped, below)
```

**The full-gate run was stopped by the integrator for memory.** Layer (e) started SafeVerify on
three leaves at once, each loading Mathlib; swap reached 30.3 of 30.7 GB and free disk fell to 13-14
GB (the run's floor is 15), and the integrator stopped the run at 03:09 (after the kill: 22 GB free,
swap 21 GB).

**What happened next was muddled, and not all of it was mine; here is the record.** A second agent
process was writing to this directory and to my scratch files at the same time, in this README's
voice; I did not start it and could not reach it, and I found it only from its files. In order:
- 03:09-03:10, the other process ran layer (e) by hand on the killed run's build (`tmp/layer-e.sh`,
  SafeVerify and comparator, **three at a time**, `logs/gate-primes-layer-e-killed.log`).
- 03:10:26, I ran SafeVerify alone on `EuclidModFour` under a watchdog (`one-safeverify.sh`: stop at
  +4 GB of swap, under 16 GB of disk, or 900 s). It was stopped after 36 s, before a verdict: swap
  went from 20.7 to 25.6 GB and disk from 22 to 17 GB (`logs/safeverify-one.log`). **That rise is not
  one SafeVerify's**: the other process's three were running beside it.
- 03:11, I deleted the gate's work directory, so the other process's later jobs failed at once
  ("No such file or directory"), and at 03:12 I killed its three running jobs, taking them for
  leftovers of the stopped gate run. Its log shows them "exit=143 119s".
- 03:12:29, the other process relaunched the full gate from another copy and stopped it itself 18 s
  in, during layer (a) (`logs/gate-primes-fourth-try-aborted.log`, its words). It also renamed my
  `logs/gate-primes.log` to `logs/gate-primes-third-try-killed.log`.

So no SafeVerify or comparator verdict on the primes tree exists from tonight, and no clean
measurement of what one SafeVerify costs here either. Then, with no other Lean process running,
I ran the gate on one leaf, `EuclidModFour`, under `watchdog.py` (stop at +6 GB of swap or under 16 GB
of disk), from a snapshot of the gate directory (gate.sh md5 7a52aa6ef16a1a35ad6cf7e1f9aa8f0f, whose
header now says SafeVerify "loads four Mathlib environments per leaf"; `logs/gate-one-leaf.log`):

```
(a) trusted inputs   pass     23.4s  22 files from d1f4b0a2…; none differed; .lake cloned
    trusted build    pass    143.5s  Challenge, Spec.* (reused from the trusted .lake when unchanged)
(b) lake build       pass     79.3s  Proofs.EuclidModFour (sandboxed; sorry warnings: 0)
(c) type + axioms    pass     68.9s  euclidModFour: [propext, Quot.sound];
(d) kernel replay    pass     62.8s  leanchecker Proofs.EuclidModFour
watchdog: end 03:25:18 after 500 s, exit -15; swap peak 25074 MB (+6.3 GB), disk low 18.7 GB; STOPPED: swap rose 6.3 GB
```

SafeVerify had replayed the Spec module ("Finished replay. Found 1 declarations.") and was replaying
the proof module when it was stopped (`logs/gate-one-leaf-logs/safeverify.EuclidModFour.log`). One
SafeVerify on one Mathlib leaf raised swap use by more than 6 GB before reaching a verdict, and by the
integrator's rule I ran no more of the gate. So: **SafeVerify and comparator on the honest
primes tree are not verified tonight**; the integrator can rerun one leaf at a time on a machine
with room, or with `GATE_SAFEVERIFY=off` for comparator alone.

What stands: on the honest tree, layers (a)-(d) of the gate pass for all nine; on the core-Lean
hijack, layer (e) is what rejects it. The costs from these lines: the fast check (`check-leaf.sh`) was
32-165 s a leaf tonight; the gate's (b)-(d) for all nine took 18.6 minutes, three at a time.

## 8. What surprised me, and what it means for Graphene

- **The fast check could be faked from inside the leaf's own file.** A leaf that writes
  `macro "S_leaf" : term => `(True)` and a higher-priority `#print axioms` syntax makes its gate file
  compile and print a clean axiom line for a proof of `1 = 2` (`hijack/`, `logs/hijack.log`; core Lean,
  15 s to rerun). Scope cannot see this: the attack is inside the one file the leaf may write. Any
  check that compiles a trusted file *after* importing the leaf has the hole; that includes my first
  `check-leaf.sh` and, as I read it at 02:08, layer (c) of `../gate/gate.sh`; its layer (e) compares
  compiled types and should catch it (section 7 says what running it showed). `GateCheck.lean` closes
  it by asking the compiled environment instead (section 3). It belongs to the red team's
  "notation/macro redefinition" class (LeanParanoia's catalog, `../../../landscape.md` §4).
- **A "closed" that is not a proof.** Canonical, when it finds a term, admits the goal with `sorry`
  and prints `Try this: exact …`; `plausible`, when it finds nothing, also admits. Both left no goal
  and no error; only `#print axioms` (or `collectAxioms`) told them apart from a proof. Every
  automation rung in a cascade needs the axiom check, not a clean exit.
- **Automation does not find the library's own theorem when the phrasing differs.** Mathlib proves
  this theorem (Dirichlet, `Nat.forall_exists_prime_gt_and_modEq`), and nothing found it from
  `p % 4 = 3`. Contamination here would sit in a model's memory of lemma names, not in the tactics
  (an inference; no model was run).
- **The machine catches misstatements cheaply, but only as a portfolio.** No single check caught
  all three seeded defects: `plausible` cannot test an unbounded `∃` (so it missed the false key
  lemma until the statement was bounded), and nothing but the vacuity test flags a vacuous leaf,
  which automation "proves" as fast as the honest leaves that close (corrected by the integrator from "faster than any honest leaf").
- **Graphene's `needs:` is order, a Lean hypothesis is meaning.** With needs as hypotheses every leaf
  can be checked at once; `needs:` made three of eight wait. And a hand-back's offer read a node id in
  a disproof as "wait on it".
- **The cost of a check is Mathlib's load, and Graphene's clean worktree pays it three times.** On
  this starved machine one load took 2-6 minutes; `graphene node done` on one leaf took 903 s.
  GateCheck costs the same one load the gate file did (it imports the module at run time instead of
  compiling a file that imports it). A warm Lean server, or a worktree that shares a trusted build,
  is what a Lean executor would need; APFS clones share disk, not the page cache.
- **The gold-standard layer is the expensive one.** `leanchecker` replayed nine modules in 7 minutes
  here, but SafeVerify, three at a time with Mathlib, took the machine to 30.3 of 30.7 GB of swap.
  Alone, on one leaf, SafeVerify raised swap by more than 6 GB before a verdict and was stopped (section 7). In a Graphene check the fast check belongs in the agent's loop and the
  challenge-against-solution check at the gate, one leaf at a time, on a machine with room.
- **Two agents in one directory.** A second agent process wrote to this directory and my scratch
  files while I worked (section 7); each of us undid part of the other's run. A spike that runs heavy
  jobs needs one owner per directory, or a lock (compare decision 95, which ran a plan in a clone
  because a worktree shares its checkout's store).
- **Hammers:** Duper and Canonical install cleanly for v4.34 and closed nothing here; LeanHammer
  cannot be built on v4.34.1 today (lean-smt uses an API Lean 4.34 removed), and its default premise
  selector is a remote server.

## Files

| path | what |
|---|---|
| `tree.txt`, `tree-seeded.txt` | the tree in Graphene's text form; the seeded false leaf as a proposal under it |
| `Challenge.lean`, `Seeded.lean`, `Proofs/`, `Gate/`, `GateCheck.lean` | the Lean project (section 3) |
| `check-leaf.sh`, `check-all.sh`, `write-gates.sh`, `trusted.sha256` | the checks and how the gates are written |
| `tree2lean.py` | tree.txt → the Lean statements and gate types, with Graphene's own parser (section 4) |
| `Auto/Harness.lean`, `Auto/run.py`, `Auto/Baseline.lean`, `Auto/baseline.md`, `Auto/hammers.md` | the automation baseline: harness, driver, the generated file that ran, the tables |
| `Falsify/Checks.lean`, `Falsify/Run.lean` | `#falsify` and `#vacuity`, and every check before spend (section 6) |
| `hammers/` | the hammers' Lake project file, their harness copy, the smoke test |
| `blueprint/` | the LeanArchitect form: attributes, the one-file build, the nine nodes it printed |
| `hijack/` | the gate-file hijack, in this layout (`run.sh`) and in `../gate`'s (`gate-layout/run-gate.sh`) |
| `to-gate-layout.sh`, `watchdog.py`, `one-safeverify.sh` | this project in `../gate`'s layout, for `gate.sh`; a command under a swap and disk watchdog; SafeVerify on one leaf under one |
| `PREDICTIONS.md` | every prediction, written before its measurement, with the result beside it |
| `logs/` | every run's output; `logs/graphene/` the Graphene transcripts and the person's scripts |

## Rerun

Everything below runs from this directory with elan on the PATH (`export PATH=$HOME/.elan/bin:$PATH`),
Lean 4.34.1, and a `.lake` holding Mathlib v4.34.1's build. macOS has no GNU `timeout`; the time
limits here are inside Lean (the harness's cancellation token, Canonical's own timeout, a heartbeat
budget for Duper) and Python's `subprocess` timeout (`Auto/run.py`'s backstop). Wall times on another
machine will differ a lot from this night's (see the top).

```sh
# 0. The Lake project: Mathlib's build, cloned copy-on-write from a base project that has it
#    (a base is `lake new base math` then `lake exe cache get`; or copy the three config files here).
cp -cR <base>/.lake .lake && rm -rf .lake/build          # 22-26 s here; almost no disk
lake build Challenge Seeded                              # 211 s here (the first read of Mathlib)

# 1. Every leaf and the root, one after another (OddFactorThree, the seeded false leaf, must fail)
./check-all.sh                                           # or ./check-leaf.sh EuclidModFour
./write-gates.sh                                         # only if the tree changes; then:
shasum -a 256 lean-toolchain lakefile.toml lake-manifest.json Challenge.lean Seeded.lean \
  GateCheck.lean Gate/*.lean Proofs/Root.lean > trusted.sha256
hijack/run.sh                                            # the gate-file hijack, core Lean, ~15 s

# 2. Graphene on the text, in a scratch clone (never a real repository; <fields> is the worktree).
#    Commit lakefile.toml lean-toolchain lake-manifest.json Challenge.lean Seeded.lean GateCheck.lean
#    Gate/ Proofs/Root.lean check-leaf.sh trusted.sha256 tree.txt, then, in the clone:
uv run --project <fields> graphene plan propose - < tree.txt             # the agent's act
EDITOR=<here>/logs/graphene/accept-all.sh <here>/logs/graphene/as-person.sh \
  uv run --project <fields> graphene plan edit                           # the person's act
uv run --project <fields> graphene plan --text                           # the round trip
uv run --project <fields> python <here>/tree2lean.py tree.txt            # text -> Lean
#    For `graphene node done`, give the clone a .lake/packages (a symlink to this one's is enough).

# 3. The automation baseline (one Lean process; 17.5 min here)
lake build Auto.Harness && python3 Auto/run.py                           # -> Auto/baseline.md
python3 Auto/run.py --parse logs/baseline-<time>.log                     # the tables again, from a log

# 4. Hammers: a Lake project requiring Duper v4.34.1 and Canonical v4.34.0 (hammers/lakefile.toml),
#    with Challenge.lean, Seeded.lean and hammers/Harness.lean as Bench/Harness.lean (its only change:
#    maxHeartbeats 1,000,000 instead of 0, which Duper needs to stop). Canonical needs `lake lean`.
python3 Auto/run.py --project <hammers> --harness Bench.Harness --lake-lean \
  --imports Challenge,Seeded,Duper,Canonical --tactics duper,canonical --out Bench/Hammers

# 5. Checks before spend, the seeded leaves' witnesses and the Dirichlet one-liner
lake env lean -o .lake/build/lib/lean/Falsify/Checks.olean -i .lake/build/lib/lean/Falsify/Checks.ilean \
  Falsify/Checks.lean                                                   # 3 s: it imports Plausible only
lake env lean Falsify/Run.lean

# 6. The gate from ../gate, on a copy in its layout (Spec/ files, camelCase names, one directory down).
#    ONE leaf at a time: nine at once, three SafeVerify processes in parallel, filled 30 GB of swap here.
ref=$(./to-gate-layout.sh /tmp/primes-gate) && \
  GATE_TRUSTED_REF=$ref GATE_TRUSTED_LAKE=<a .lake with Mathlib's packages only> GATE_TOOLS=<tools> \
  python3 watchdog.py --swap-rise-gb 6 --min-disk-gb 16 -- \
  ../gate/gate.sh /tmp/primes-gate/primes EuclidModFour                  # then each other leaf, and Root
GATE_TOOLS=<tools> hijack/gate-layout/run-gate.sh                       # the hijack through the gate
```

The LeanArchitect form was built in a scratch project (`blueprint/lakefile.toml`: `LeanArchitect`
v4.34.0 required before `mathlib`, Lake's own advice after the first `lake update` failed in Mathlib's
cache hook) with `lake env lean BlueprintAll.lean`; `blueprint/BlueprintAll.lean` is `Challenge.lean`,
the proofs, `Proofs/Root.lean` and the attribute block of `blueprint/Blueprint.lean`, concatenated.
