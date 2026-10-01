#!/usr/bin/env bash
# check-leaf.sh LEAF: the fast per-leaf check (layer 3), core-Lean copy of spikes/lean/primes.
#   1. `lake build Proofs.LEAF` succeeds.
#   2. GateCheck.lean, run on the COMPILED module (it parses nothing the leaf wrote), finds each
#      theorem Gate/LEAF.lean names: declared in Proofs.LEAF, of the type Gate/LEAF.lean states,
#      depending on no axiom beyond propext, Classical.choice, Quot.sound.
# Gate/LEAF.lean is read as text for the expected type; it is not compiled (compiling it after
# importing the leaf lets the leaf's own macros/notation rewrite it: the gate-file hijack).
set -uo pipefail
leaf=${1:?usage: check-leaf.sh LEAF}
cd "$(dirname "$0")"
export PATH="$HOME/.elan/bin:$PATH"
say() { echo "check-leaf $leaf: $*"; }
[ -f "Gate/$leaf.lean" ] || { say "no Gate/$leaf.lean"; exit 2; }
build=$(lake build "Proofs.$leaf" 2>&1) || { echo "$build" | tail -20; say "does not build"; exit 1; }
specs=()
while IFS= read -r line; do
  thm=${line##*:= }; type=${line#example : }; type=${type% := *}
  specs+=("$thm=${type// → /,}")
done < <(grep -E '^example : .* := [A-Za-z_][A-Za-z0-9_]*$' "Gate/$leaf.lean")
[ ${#specs[@]} -gt 0 ] || { say "Gate/$leaf.lean states no type"; exit 1; }
out=$(lake env lean --run GateCheck.lean "Proofs.$leaf" "${specs[@]}" 2>&1) || { echo "$out"; say "not proven"; exit 1; }
say "proven; $out"
