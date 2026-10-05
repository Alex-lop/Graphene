# Red team, round two: what the first round left open

Run by the integrator on 2026-09-30. A read-only critic checked the first round against its own logs, and
its findings are folded into `../README.md` under "Review". This round tested one of the three holes that
the critic and the mechanics agent raised. The other two stay open, with what would close them. The files
of the one test were scratch and are not committed; `PREDICTIONS.md` has the prediction, written first,
and each layer's verdict.

## Tested: a stored axiom list that says less than the proof uses

In Lean v4.34.1 each compiled module carries a precomputed list of the axioms its declarations use.
`collectAxioms` and `#print axioms` read that list for an imported declaration instead of walking the
proof (`src/lean/Lean/Util/CollectAxioms.lean`). With the list altered after compilation, for a proof
that uses `sorry`:
- `#print axioms` in a compiled gate file (`gate.sh` layer (c)) was **fooled**.
- `leanchecker` passed, as designed.
- GateCheck, SafeVerify, comparator and LeanParanoia caught it.
- Lake did not notice the changed file.

**So the gate's verdict must come from a layer that walks the proof itself** (comparator, SafeVerify or
LeanParanoia), never from `#print axioms` alone. GateCheck caught it here, but why is not established, so
it is not relied on for this.

## Open, not tested

| Hole | Why it matters | What would close it (from the source and the first round) |
|---|---|---|
| code that runs when a checker imports a leaf's module (an `initialize` block, or a process it leaves behind) | the checker's own process or its output could be affected | run every step that loads candidate code in the sandbox, and decide by exit code, never by printed text |
| a shared build (`.lake/packages`) changed by one check and reused by a later one | a later gate would trust what an earlier leaf changed; `check-leaf.sh` borrows the main checkout's packages by symlink, outside every scope | a trusted build no check can write (another user, or a read-only mount), verified against Mathlib's cache before each gate; rebuild the challenge from source inside the sandbox |
| the stored-list alteration made from inside a leaf, under `gate.sh`'s sandbox, which lets a leaf write its own build outputs | layer (c) would be fooled from inside the gate | the same: comparator's or SafeVerify's own walk decides |
