#!/usr/bin/env bash
# check-leaf.sh LEAF: exits 0 only when leaf LEAF is proven. The fast check an agent runs in its loop.
#   1. The read-only files (toolchain, lakefile, manifest, challenge, gates, root) match trusted.sha256.
#   2. Proofs/LEAF.lean imports only Challenge, Seeded or Mathlib: never another leaf's proof.
#   3. `lake build Proofs.LEAF` succeeds with that trusted configuration.
#   4. GateCheck.lean, run on the compiled module (it parses nothing the leaf wrote), finds each
#      theorem Gate/LEAF.lean names: declared in Proofs.LEAF, of the type Gate/LEAF.lean states
#      (S_need₁ → … → S_leaf, up to unfolding, the S_… from Challenge or Seeded), and depending on no
#      axiom beyond propext, Classical.choice and Quot.sound (so no sorry, no declared axiom, no
#      native_decide). Gate/LEAF.lean is read as text for the expected type; it is not compiled,
#      because compiling it after importing the leaf lets the leaf's own syntax rewrite it.
# What it does not catch (a kernel-checking option, a changed build under .lake) is the gate's job:
# leanchecker and comparator, in ../gate.
set -euo pipefail
leaf=${1:?usage: check-leaf.sh LEAF (a file name under Gate/, e.g. EuclidModFour)}
cd "$(dirname "$0")"
export PATH="$HOME/.elan/bin:$PATH"
start=$SECONDS
say() { echo "check-leaf $leaf: $*"; }
[[ $leaf =~ ^[A-Z][A-Za-z0-9]*$ && -f Gate/$leaf.lean ]] || { say "no such leaf (no Gate/$leaf.lean)"; exit 2; }

shasum -a 256 -c --quiet trusted.sha256 || { say "a read-only file differs from trusted.sha256"; exit 1; }

if [ "$leaf" != Root ]; then
  bad=$(grep -E '^[[:space:]]*import[[:space:]]' "Proofs/$leaf.lean" \
    | grep -vE '^[[:space:]]*import[[:space:]]+(Challenge|Seeded|Mathlib(\.[A-Za-z0-9.]+)?)[[:space:]]*$' || true)
  [ -z "$bad" ] || { say "Proofs/$leaf.lean imports what a leaf may not: $bad"; exit 1; }
fi

# A worktree Graphene cut for the check has no .lake (git ignores it): borrow the packages of the
# checkout it was cut from, or of PRIMES_LAKE. The borrowed build is outside git, so outside every
# scope: see the README's holes.
if [ ! -d .lake/packages/mathlib ]; then
  src=${PRIMES_LAKE:-}
  if [ -z "$src" ]; then
    common=$(git rev-parse --path-format=absolute --git-common-dir)
    src="$(dirname "$common")/$(git rev-parse --show-prefix).lake"
  fi
  [ -d "$src/packages/mathlib" ] || { say "no built Mathlib at $src/packages"; exit 1; }
  mkdir -p .lake && ln -s "$src/packages" .lake/packages
fi

build=$(lake build "Proofs.$leaf" 2>&1) || { echo "$build" | tail -40; say "does not build"; exit 1; }
specs=()
while IFS= read -r line; do  # example : S_a → S_b → S_leaf := theorem
  thm=${line##*:= }
  type=${line#example : }
  type=${type% := *}
  specs+=("$thm=${type// → /,}")
done < <(grep -E '^example : .* := [A-Za-z_][A-Za-z0-9_]*$' "Gate/$leaf.lean")
[ ${#specs[@]} -gt 0 ] || { say "Gate/$leaf.lean states no type"; exit 1; }
out=$(lake env lean --run GateCheck.lean "Proofs.$leaf" "${specs[@]}" 2>&1) || { echo "$out"; say "not proven"; exit 1; }
say "proven in $((SECONDS - start)) s; $(echo $out)"
