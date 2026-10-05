#!/usr/bin/env bash
# A leaf's own file rewrites what its gate file says. Core Lean only (no Mathlib): about 15 s.
# Expected: the gate file compiles and prints a clean axiom line for a proof of 1 = 2;
# GateCheck (which reads the compiled environment) refuses it.
set -uo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.elan/bin:$PATH"
lake build Proofs.FalseLeaf Proofs.Honest 2>&1 | tail -1
echo "--- lake env lean Gate/FalseLeaf.lean"
lake env lean Gate/FalseLeaf.lean; echo "exit=$?"
echo "--- lake env lean --run ../GateCheck.lean Proofs.FalseLeaf false_leaf=S_false_leaf"
lake env lean --run ../GateCheck.lean Proofs.FalseLeaf false_leaf=S_false_leaf; echo "exit=$?"
echo "--- an honest proof, and a statement the leaf defined itself"
lake env lean --run ../GateCheck.lean Proofs.Honest honest=S_true_leaf honest=S_other; echo "exit=$?"
