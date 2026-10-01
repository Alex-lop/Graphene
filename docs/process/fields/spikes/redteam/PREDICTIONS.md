# Red-team predictions (written before the full matrix run)

Layers: SCOPE (Graphene boundary, file-path) · build (`lake build`) · check-leaf (type assertion +
`#print axioms` via GateCheck) · leanchecker (kernel replay) · comparator · SafeVerify · LeanParanoia.
Legend: R = rejects, P = passes (does not catch), n/a = cannot run.

Some mechanics were confirmed in scratch first (`$S/tmp/rtscratch`, noted "[scratch-confirmed]"); the
full matrix with rc capture and every layer had not run when these were written.

| # | exploit | SCOPE | build | check-leaf | leanchecker | comparator | SafeVerify | paranoia |
|---|---|---|---|---|---|---|---|---|
| 01 | sorry | P | P | R | P | R | R | R |
| 02 | admit | P | P | R | P | R | R | R |
| 03 | declared-axiom | P | P | R | P | R | R | R |
| 04 | native-decide | P | P | R | P* | R | R | R | [scratch: leanchecker P — the v4.34 native axiom is a valid env] |
| 05 | implemented-by-native | P | P | R | P | R | R | R |
| 06 | skip-kernel-tc | P | P | **P** | R | R | R | R | [scratch: build P, #print axioms lies "no axioms", leanchecker R] |
| 07 | metaprogram-adddecl | P | P | **P** | R | R | R | R | [scratch: same as 06] |
| 08 | opaque-sorry | P | P | R | P | R | R | R |
| 09 | debug-byassorry | P | P | R | P | R | R | R |
| 10 | sorried-helper | P | P | R | P | R | R | R |
| 11 | unsafe-def (unused) | P | P | P | P | P | **R** | P | [scratch: only SafeVerify's whole-env scan flags it; target is honest] |
| 12 | macro-gate-hijack | P | P | R | P | R | R | **P** | [scratch: naive gate-file compile fooled; GateCheck/CM/SV catch; paranoia misses] |
| 13 | shadow-namespace | P | **R** | n/a | n/a | n/a | n/a | n/a | [scratch: `show` fails to build — statement is pre-elaborated] |
| 14 | shadow-notation-instance | P | P | P | P | P | P | R? | paranoia may flag "local notation/instance" by source scan though the proof is honest |
| 15 | compile-time-io | P | P | P | P | P | P | P | no verifier catches it; the SANDBOX does. Graphene's run_check does not sandbox arbitrary code |
| 16 | edit-challenge | **R** | P | P | P | **P** | **P** | P | only SCOPE / trusted-inputs; checkers pass because attacker owns the challenge |
| 17 | edit-lakefile | **R** | P | P | P | P | P | P | only SCOPE / trusted-inputs |
| 18 | edit-lean-toolchain | **R** | n/a | n/a | n/a | n/a | n/a | n/a | would fetch another toolchain; SCOPE refuses the edit first |
| 19 | edit-lake-manifest | **R** | n/a | n/a | n/a | n/a | n/a | n/a | core has no deps; would fetch a fork; SCOPE/trusted-inputs |
| 20 | dummy-structure | **R** | P | P | P | P | P | P | no gate catches; tree-author defect, review before spend |
| 21 | vacuous | **R** | P | P | P | P | P | P | no gate catches; vacuity check before spend / person |

Predicted kill-criterion candidates (an exploit no *check command* closes): 15 (needs a sandbox, not a
check), 16/17/18/19 (need scope or trusted-inputs, not a proof check), 20, 21 (need review/falsification
before spend). None is a *soundness* hole in a correct kernel: each is closed by scope, the sandbox,
trusted-inputs, or a before-spend check — the question is which layer, not whether.

## What happened (appended after the run, 2026-09-30 ~03:50 EDT)

The matrix (logs/matrix.tsv) matched these predictions. Notes where reality refined them:

- **04/05 native_decide: leanchecker = P, confirmed.** On v4.34.1 native_decide introduces a
  per-computation axiom that IS a valid environment, so the kernel replay accepts it; only the axiom
  allowlist (check-leaf/comparator/SafeVerify/paranoia) rejects it. This corrects LeanParanoia's
  comparison table, which lists leanchecker as catching native_decide (that held when the compiled
  `_nativeDecide` aux decl was absent from the replay; on 4.34.1 it is a declared axiom present in the env).
- **06/07 skipKernelTC & addDeclCore: check-leaf = P (it does NOT catch them), leanchecker = R.** As
  predicted: `#print axioms` reports "no axioms" for an ill-typed decl that skipped the kernel; only the
  kernel replay (leanchecker/comparator/SafeVerify/paranoia-replay) catches it. The fast in-loop check
  is not a substitute for the kernel replay.
- **12 macro-gate-hijack: paranoia = P (misses it).** Reference-free, so it cannot see that `target :
  True` is not `S_target`; GateCheck/comparator/SafeVerify catch it. The naive "compile Gate/Target.lean"
  is fooled (the leaf's macros are in force); check-leaf uses GateCheck, which reads the compiled env.
- **14 shadow-notation-instance: paranoia = R on an HONEST proof.** Its source blacklist flags "local
  notation"/"local instance" even though the statement is fixed in Challenge and the proof is honest — a
  false positive. Every other layer passes it.
- **15 compile-time-io: first design self-destructed.** My first version rewrote Challenge.lean, which
  broke its own second build, so the verifiers "rejected" it incidentally. I rewrote the leaf to keep the
  proof honest; then every verifier passes (they check the proof, which is honest) and only the OS sandbox
  stops the write. That is the true finding.
