# The red team: attacking "cannot be faked"

A spike for the fields directive (`docs/process/directives/FIELDS_DIRECTIVE.md`, "The red team"). The
directive's second condition is that each leaf has *a cheap check that cannot be faked*. "Cannot be
faked" is a claim, so this attacks it: 21 cheating solutions, each the smallest change that fakes a
proof, run against every layer a Graphene-driven Lean gate would use, recording which layer rejects each
one. Run 2026-09-30. Nothing here called a model, a paid prover, or a remote server; the one fictitious
"fork" URL is never fetched.

The layout under test is option 4 of the directive (the challenge-module layout), the same shape the
gate and the worked tree use (`../lean/gate/`, `../lean/primes/`): a read-only `Challenge.lean` holds
every definition and each statement as `def S_<leaf> : Prop`; one writable `Proofs/<Leaf>.lean` per leaf
proves `S_<leaf>` by name; read-only `Spec/<Leaf>.lean` (the challenge stub the comparison tools use) and
`Gate/<Leaf>.lean` (the type assertion) are written from the tree, never by a leaf.

## Why this ran on core Lean, not Mathlib

The directive and the task ask for the primes/gate Mathlib layout. **It does not fit this machine, and
the finding wins (directive: "Where a finding contradicts something in this directive, the finding
wins").** Two agents tonight had their Mathlib gate runs killed at the 15 GB disk floor: one Mathlib
gate layer holds Mathlib's ~5 GB of oleans in memory (each check 2–7 min), SafeVerify builds four such
environments per leaf and grew swap ~4 GB in 36 s, and three parallel checks took free disk under 12 GB
(`../lean/mechanics/README.md`, "The memory incident"; `../lean/primes/README.md` §7). Running the full
7-layer matrix per-exploit on Mathlib, 21 times, was infeasible and would have crossed the floor
repeatedly.

**Every exploit here is a library-independent mechanism** — a property of Lean's elaborator, kernel, and
the checkers, not of Mathlib. So the matrix runs on a core-Lean copy of the identical layout, where each
layer takes seconds, the whole matrix runs in **1 min 45 s** with no memory pressure (free disk flat at
25 GB), and every layer runs to a real verdict for every exploit. The core↔Mathlib equivalence was
already established for the cases both agents could run on both: the gate's negatives fail at the same
layers on core and Mathlib (`../lean/gate/README.md`), and the gate-file hijack is caught at the same
layer on both (`../lean/primes/README.md` §7). Where a verdict is Mathlib-specific (the `lake-manifest`
fork), it is marked and reasoned, not run.

The **scope** layer (Graphene's boundary) is about file paths, not Lean, so it *is* shown with the real
Graphene, on a core plan, cheaply — see "The scope layer" below.

## Versions

- Lean `leanprover/lean4:v4.34.1` (commit 5045d005), its Lake and `leanchecker` (ships with the toolchain).
- comparator `leanprover/comparator` tag v4.34.0 (d03acab1), toolchain bumped to v4.34.1; run with the
  `fake-landrun.sh` shim (macOS has no landrun — the shim runs the *comparison* unsandboxed; the sandbox
  is tested separately, exploit 15).
- SafeVerify `GasStationManager/SafeVerify` (b291b588) with the four-line `CollectAxioms.collect`→
  `Lean.collectAxioms` port (`../lean/gate/install-tools.sh`).
- LeanParanoia `oOo0oOo/LeanParanoia` (11c2385a) with the `Lean.Replay` port; run with
  `--trust-modules Init,Std,Lean` (without it, it false-fails honest core proofs — `../lean/mechanics/`
  finding 7).
- Graphene from the `fields` worktree, run with `uv run --project`.

## The matrix

21 exploits × 7 layers. **R** = the layer rejects it, **P** = the layer passes it (does not catch it),
**n/a** = could not be run (reason given). Layers left to right are the order a gate applies them:

- **SCOPE** — Graphene's boundary; a leaf's scope is only `Proofs/<Leaf>.lean`. Rejected iff the exploit
  changes any other file. Validated against the real `graphene node done` (below).
- **build** — `lake build Proofs.Target`.
- **check-leaf** — the fast per-leaf check: the type assertion + `#print axioms` allowlist, via
  `GateCheck.lean` (which reads the *compiled* environment, not text the leaf wrote).
- **leanchecker** — kernel replay of the proof's oleans.
- **comparator** / **SafeVerify** — challenge (`Spec`) vs solution (`Proofs`): kernel-identical type + axiom allowlist.
- **paranoia** — LeanParanoia, reference-free source + replay scan.

| # | exploit | SCOPE | build | check-leaf | leanchecker | comparator | SafeVerify | paranoia |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 01 | sorry | P | P | **R** | P | **R** | **R** | **R** |
| 02 | admit | P | P | **R** | P | **R** | **R** | **R** |
| 03 | declared-axiom | P | P | **R** | P | **R** | **R** | **R** |
| 04 | native-decide | P | P | **R** | P | **R** | **R** | **R** |
| 05 | implemented-by + native | P | P | **R** | P | **R** | **R** | **R** |
| 06 | skipKernelTC | P | P | P | **R** | **R** | **R** | **R** |
| 07 | metaprogram addDeclCore | P | P | P | **R** | **R** | **R** | **R** |
| 08 | opaque-sorry | P | P | **R** | P | **R** | **R** | **R** |
| 09 | debug.byAsSorry | P | P | **R** | P | **R** | **R** | **R** |
| 10 | sorried-helper | P | P | **R** | P | **R** | **R** | **R** |
| 11 | unsafe def (unused) | P | P | P | P | P | **R** | P |
| 12 | macro gate-file hijack | P | P | **R** | P | **R** | **R** | P |
| 13 | shadow via namespace | P | **R** | n/a | n/a | n/a | n/a | n/a |
| 14 | shadow notation + instance | P | P | P | P | P | P | **R** |
| 15 | compile-time IO | P | P | P | P | P | P | P |
| 16 | edit Challenge.lean | **R** | P | P | P | P | P | P |
| 17 | edit lakefile.toml | **R** | P | P | P | P | P | P |
| 18 | edit lean-toolchain | **R** | n/a | n/a | n/a | n/a | n/a | n/a |
| 19 | edit lake-manifest.json | **R** | n/a | n/a | n/a | n/a | n/a | n/a |
| 20 | dummy structure | **R** | P | P | P | P | P | P |
| 21 | vacuous statement | **R** | P | P | P | P | P | P |

n/a reasons: 13 — the proof does not build (the shadow cannot be substituted), so later layers have
nothing to check. 18/19 — building would fetch another toolchain or a dependency; scope refuses the edit
first, so the Lean layers never run.

### The messages behind the cells (representative)

- **03 declared-axiom** — check-leaf `axioms beyond the standard three: [cheat]`; comparator `Illegal
  axiom detected: 'cheat'`; SafeVerify `used disallowed axioms. #[cheat]`; paranoia `Uses disallowed
  axiom: cheat`. leanchecker **passes** (an honestly declared axiom is a valid environment).
- **04 native-decide** — the axiom shown on v4.34.1 is `target._native.native_decide.ax_1_1` (a
  per-computation axiom, *not* `Lean.ofReduceBool`), caught by every axiom-allowlist layer.
  **leanchecker passes it** — the native axiom is a valid env, so kernel replay has nothing to object to.
- **06 skipKernelTC / 07 addDeclCore** — check-leaf **passes**: `#print axioms target` reports
  `[]` ("does not depend on any axioms") for a decl whose kernel type-check was skipped. leanchecker
  catches it: `declaration type mismatch, 'target' has type True but ... S_target`; comparator `Lean
  default kernel rejects the solution`; SafeVerify + paranoia the same via replay. **This is the case
  where `#print axioms` lies and only a kernel replay is the backstop.**
- **11 unsafe def** — the target is proven *honestly*; an unused `unsafe def sketchy` sits in the file.
  Only SafeVerify flags it (`unsafe constant sketchy detected`) because it replays the whole submission
  olean; check-leaf/comparator/paranoia look at the target's closure, which is clean. (It proves nothing
  false — it shows what each layer *scans*.)
- **12 macro gate-file hijack** — the leaf makes `S_target` a macro meaning `True` and hijacks `#print
  axioms` to print a clean line, so **compiling `Gate/Target.lean` is fooled** (its axiom line reads
  `[propext]`). check-leaf is not fooled because `GateCheck.lean` asks the compiled environment
  (`target : True`, not `S_target`); comparator/SafeVerify catch the type mismatch. **paranoia misses it**
  (reference-free: `target : True` is a valid, axiom-clean theorem).
- **16 edit Challenge.lean** — comparator `Your solution is okay!`, SafeVerify `check passed`. **The
  challenge/solution checkers pass**, because the attacker rewrote `Challenge.lean` *and* the matching
  `Spec` stub, so the tools compare two statements that agree — both trivial. Only SCOPE (or the gate's
  trusted-inputs layer, which takes `Challenge`/`Spec` from the approved commit) catches it.

## The scope layer, with the real Graphene

Shown in the scratch repo `scratchpad/redteam-graphene` (a scratch git repo: the core red-team project + a one-leaf
plan; `graphene init` not run, so no hooks — the boundary is enforced at `graphene node done`). Person
acts follow decision 95's precedent (agent marks dropped, `GRAPHENE_AS=person:alex`). Full transcript:
`logs/graphene/scope-demo.md`. Four runs:

- **A. in-scope cheat (`sorry`)** — scope passes (only `Proofs/Target.lean` changed), the check runs and
  refuses, in **7.1 s**: `target is not done: ./check-leaf.sh Target failed: ... [sorryAx]`.
- **B. out-of-scope cheat (edit `Challenge.lean`, honest proof)** — SCOPE refuses in **0.18 s**: `changed
  outside its scope (Proofs/Target.lean), which only the person widens / Challenge.lean`. The 0.18 s vs
  7.1 s proves the check never ran.
- **C. out-of-scope cheat (edit `lean-toolchain`)** — SCOPE refuses in **0.17 s**, before any build or
  toolchain download.
- **D. in-scope compile-time IO (honest proof + `#eval` writing an absolute-path file)** — `target is
  done (check passed, nothing outside its scope)`, **and the leaf's `#eval` wrote a file outside the repo
  while Graphene's check compiled it.**

**The order (`src/graphene_map/plan.py:finish`, behind `graphene node done`), confirmed by reading and by
the timings:** `changed_since` (git) → standing conditions → `stray = outside_scope | links_out |
elsewhere` → **if any tracked stray, refuse (≈ line 2129), before the check** → only then `run_check`
(≈ line 2134). Untracked out-of-scope files are set aside and the check runs without them.

**So the task's question — does the check run files the leaf wrote before the out-of-scope change is
refused?** Two answers:
1. **Out-of-scope config (`lakefile`, `lean-toolchain`, `lake-manifest`, `Challenge`): no.** They are
   tracked and outside the leaf's one-file scope, so `done` refuses at the scope step *before* the check
   runs (Tests B, C). A leaf-written `lean-toolchain` naming another toolchain is never resolved; a
   leaf-written lakefile is never read. Scope closes exploits 16–21 without running anything.
2. **The in-scope proof file: yes — and that is an exploit of the check itself (Test D, exploit 15).**
   The one file a leaf may write is compiled by the check, and Lean runs arbitrary code at compile time.
   `graphene node done` ran it with the user's full permissions and marked the node **done**, because
   `plan.run_check` (`_clean_tree`) runs the candidate in a throwaway git worktree with **no OS sandbox**
   unless the leaf ran in a Nemotron sandbox (`plan.sandboxed`). **The gate must sandbox candidate code.**
   `../lean/gate/gate.sh` does (macOS `sandbox-exec`): in `logs/15-compile-time-io/sandbox.log` the same
   `#eval` write is `operation not permitted` under the sandbox and the sentinel file is not created,
   while unsandboxed it is. Graphene's local check does not sandbox; a Lean gate must add it (restore
   trusted config first, then run in a no-network, write-confined sandbox).

## Conclusions

**(a) Does today's file-path scope plus a check command already give full protection?**

Almost — for everything a *proof* can do, yes; for two things a check cannot reach, no. With this
layout, `graphene node done`'s scope (leaf = one `Proofs/<Leaf>.lean`) plus a check command that runs
**check-leaf (type + `#print axioms` allowlist) AND leanchecker (kernel replay) AND a challenge/solution
check (comparator or SafeVerify)** rejects every faked *proof*: exploits 01–14 and 16–21 are each caught,
most by more than one layer. Two gaps, both closable, neither a new Graphene *feature*:

- **The check itself is an attack surface (exploit 15 / Test D).** Compiling the leaf runs its code.
  Graphene's `run_check` isolates the *filesystem* to a throwaway worktree but does **not** sandbox
  network/exec/reads. The check command must bring an OS sandbox (gate.sh's `sandbox-exec`), and must
  restore the trusted config into the sandbox rather than trust the worktree's copy. This is a property
  of the *check command*, not of Graphene's boundary — the boundary did its job (the leaf changed only
  its one file).
- **No single check command is enough; you need the trio, in order, and the read-only boundary is
  load-bearing.** leanchecker alone passes sorry, every declared axiom, and every statement-shadow
  (exploits 01–05, 08–10 leanchecker = P). `#print axioms` alone passes skipKernelTC/addDeclCore
  (06/07 check-leaf = P). comparator/SafeVerify alone pass a rewritten `Challenge` (16) — they only
  guarantee `Spec ≡ Proofs`, so **they protect the statement only when `Challenge` and `Spec` are pinned
  to a trusted source**, which in Graphene is exactly the scope boundary keeping them out of the leaf.

**(b) Is there an exploit that NO check command closes?** (This is a kill criterion in the plan — stated
precisely, not overstated.)

**No exploit here is a soundness hole in a correct kernel, and no exploit escapes *all* of {scope,
sandbox, trusted-inputs, before-spend check}. But three of them close under *no proof check command* —
they are closed by a different layer, and it matters which:**

- **15 compile-time IO** — closed by the **sandbox**, not by any proof check. A `lake build && …` check
  without a sandbox does not close it.
- **16–19 config/challenge tampering** — closed by **scope** (Graphene's boundary) or, for a check run
  outside Graphene, by the check's **trusted-inputs** step (`git show <approved>:file | cmp`, gate.sh
  layer (a)). No proof check looks at the config.
- **20 dummy structure and 21 vacuous statement** — closed by **no gate at all**. The statement is
  well-typed, axiom-clean, and kernel-valid; the proof is honest; every one of the seven layers passes
  (20/21: all P except SCOPE, and SCOPE only because these examples put the defect in `Challenge`, out of
  the leaf's scope — a defect the tree author could equally have committed *with* the approved tree). The
  only defenses are **a check before spend** (`plausible`/`decide`/a vacuity probe — the worked tree
  found the false and vacuous leaves in <0.2 s, `../lean/primes/README.md` §6) and **the person reviewing
  the statement**. This is the directive's condition-3 gap, and it is real: it is why Graphene's value in
  mathematics is the person's review of statements, not a new checker.

So: **the kill criterion "an exploit that no check command closes, full stop" is not met** — every
exploit is closed by *some* layer. **The precise, true statement is: no proof-checking layer closes the
compile-time-IO, config-tampering, dummy-theory, or vacuous/mis-strength classes; they need the sandbox,
the scope boundary, trusted-inputs, and before-spend falsification + human review respectively.**

**(c) Which layer is needed where.**

| Attack class (exploits) | Closed by | Belongs in |
|---|---|---|
| sorry / admit / declared axiom / native_decide / implemented_by / opaque / byAsSorry / sorried-helper (01–05,08–10) | `#print axioms` allowlist (check-leaf), also comparator/SafeVerify/paranoia | the fast in-loop check |
| kernel-TC bypass: skipKernelTC, addDeclCore (06,07) | **kernel replay** (leanchecker) + comparator/SafeVerify; **not** `#print axioms` | the gate |
| statement shadow via macro / gate-file hijack (12) | GateCheck (compiled-env read) + comparator/SafeVerify; **not** paranoia, **not** a compiled Gate file | check-leaf must read the env, not compile a gate file the leaf can rewrite |
| unused unsafe/partial in the module (11) | SafeVerify (whole-env scan) | the gate, if you care about inert unsafe decls |
| shadow via namespace (13) | build (the pre-elaborated statement can't be substituted) | free — the layout defeats it |
| statement / config tampering: Challenge, Spec, lakefile, toolchain, manifest (16–19) | **scope** (Graphene) or **trusted-inputs** (gate.sh layer a) | the boundary; the check must re-pin config when run outside Graphene |
| compile-time IO / arbitrary code (15) | **OS sandbox** (gate.sh `sandbox-exec`) | the check command — Graphene's `run_check` does not sandbox |
| dummy theory (20), vacuous / mis-strength (21) | **no gate** — `plausible`/`decide`/vacuity before spend, then the **person** | before spend, and the person's review (condition 3) |
| kernel soundness bug (not exploited here) | an *independent* kernel (comparator `--paranoid` / external kernels) | the gate, for high-stakes targets |

**One structural win of option 4, seen here and worth carrying forward:** the challenge-module layout
*defeats the whole statement-shadowing class at the source* (exploit 13 fails to build; namespace/
notation/instance shadows can't change a statement that is a constant already elaborated in the read-only
`Challenge`). This is the class that plagues the flat "restate-the-theorem" layout (the DeepMind swarm's
`local notation "LinearIndependent" => fun _ _ => False`, LongCat's patterns 1/4/7/9). The leaf never
restates the theorem, so it cannot redefine what the theorem means — the residual shadow risk is only the
gate-file hijack (12), which `GateCheck` closes by reading the compiled environment.

## Rerun

From this directory, with elan on the PATH and the gate's tools built (`../lean/gate/install-tools.sh
repl comparator safeverify paranoia`; ~50 s):

```sh
export PATH=$HOME/.elan/bin:$PATH
./run_all.sh                      # writes logs/matrix.tsv and logs/<exploit>/, prints the matrix (~1m45s)
# tool paths default to <scratchpad>/tools; override with REDTEAM_TOOLS=<dir> if built elsewhere.
```

The scope layer, with the real Graphene (core plan, no Mathlib):

```sh
S=<scratchpad>; F=$S/fields; GP=$F/docs/process/fields/spikes/lean/primes/logs/graphene
RG=$S/redteam-graphene; rm -rf $RG; mkdir $RG
cp clean/{lakefile.toml,lean-toolchain,Challenge.lean,GateCheck.lean,check-leaf.sh} $RG/
mkdir $RG/Proofs $RG/Spec $RG/Gate
cp clean/Proofs/Target.lean $RG/Proofs/; cp clean/Spec/Target.lean $RG/Spec/; cp clean/Gate/Target.lean $RG/Gate/
cp logs/graphene/tree.txt $RG/ 2>/dev/null || true    # or the tree.txt in scope-demo.md
cd $RG && printf '.lake/\n*.olean\n*.ilean\n' > .gitignore
git init -q && git add -A && git -c user.email=a@b -c user.name=a commit -qm init && lake build >/dev/null
EDITOR=$GP/accept-all.sh $GP/as-person.sh uv run --project $F graphene plan propose - < tree.txt
uv run --project $F graphene node start target
printf 'import Challenge\ntheorem target : S_target := sorry\n' > Proofs/Target.lean
uv run --project $F graphene node done target      # refused by the check (sorryAx)
# then: honest proof + an edit to Challenge.lean -> refused by SCOPE before the check runs.
```

## Files

| path | what |
|---|---|
| `clean/` | the core-Lean project: `Challenge.lean`, `Proofs/Target.lean` (honest), `Spec/`, `Gate/`, `GateCheck.lean`, `check-leaf.sh`, `lakefile.toml`, `lean-toolchain` |
| `exploits/<nn>-<name>/` | one cheating solution each: the minimal files it changes + a one-line README |
| `run_all.sh` | clones the clean project copy-on-write per exploit, overlays it, runs every layer, writes `logs/matrix.tsv` |
| `PREDICTIONS.md` | the per-exploit layer predictions, written before the run, with what happened appended |
| `logs/matrix.tsv`, `logs/<exploit>/` | the matrix and every layer's raw output per exploit (incl. `15-compile-time-io/sandbox.log`) |
| `logs/graphene/scope-demo.md` | the four real-Graphene scope transcripts and the `finish` order |

The exploit list starts from LeanParanoia's test suite and OEIS Open's published attack list
(`../../../../notes/verifiers.md` part B, `../../../../notes/provers.md` §6.4–6.5); the mapping of each to
this layout, and the two additions specific to it (the gate-file hijack 12 and the compile-time-IO/check
finding 15), are the red team's.
