# Round two: predictions and results (the integrator, 2026-09-30)

## R22. The stored axiom list

**What the source says** (v4.34.1, `src/lean/Lean/Util/CollectAxioms.lean`): each compiled module carries
a precomputed list of the axioms its declarations use, written when the module is compiled.
`collectAxioms` and `#print axioms` read that list for any imported declaration instead of walking its
body.

**Prediction** (04:12 EDT, before the run): if that stored list were altered after compilation, the checks
that read it would be fooled, and the checks that walk the proof term themselves would not.
- `#print axioms` in a compiled gate file (gate.sh layer (c)): fooled.
- GateCheck: fooled.
- leanchecker: passes, since it does not judge axioms.
- comparator, SafeVerify and LeanParanoia: catch it.

**Result** (04:15 EDT, a scratch copy of `clean/` with a `sorry` proof whose stored list was altered to
say "no axioms"; the scratch files were deleted afterwards and are not committed):

| Layer | Verdict |
|---|---|
| Lake's rebuild check | did not notice the changed file |
| `#print axioms` in the compiled gate file (gate.sh layer (c)) | **fooled**: "does not depend on any axioms" |
| GateCheck | caught it (sorryAx). Why is not established, and it may be an accident of how it loads modules |
| leanchecker | passed (as designed) |
| SafeVerify | caught it: "uses disallowed axioms" |
| comparator | caught it: "Illegal axiom detected: 'sorryAx'", from its own walk over the exported term |
| LeanParanoia | caught it: "contains sorry" |

**What it means:**
- A layer that reads the stored axiom list is not a verdict on its own. That covers `#print axioms` in a
  compiled file, and possibly `collectAxioms`.
- The gate's verdict must come from a layer that walks the proof term itself: comparator, SafeVerify or
  LeanParanoia.
- How such an alteration could be made from inside a leaf, and under which sandbox profile, was not tested.

## Not tested in this run

- **Code that runs when a checker imports a leaf's module**, such as an `initialize` block.
- **A shared build** (`.lake/packages`) altered by one check and reused by a later one.

The source reading and the first round point to the same closures for both:
- run every step that loads candidate code inside the sandbox;
- keep the trusted build where no check can write;
- decide by exit code, never by printed text.

They are open risks for the gate's hardening (`LEAN_DIRECTIVE_DRAFT.md`, milestone A).
