#!/usr/bin/env bash
# Makes a copy of this project in the layout ../gate/gate.sh expects, in a new git repository DEST:
# theorem names are the file stem with a lower-case first letter (PrimeModFour -> primeModFour), and
# each leaf has Spec/<Leaf>.lean, its statement with `sorry`, for SafeVerify and comparator. The first
# commit holds the trusted tree (no proofs); the proofs are then copied in, uncommitted: the candidate.
# The project goes in DEST/primes: gate.sh (as of 02:08) fails when the project is the repository root.
#   to-gate-layout.sh DEST   ->  prints the trusted commit; the project is DEST/primes
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
dest=${1:?usage: to-gate-layout.sh DEST}
mkdir -p "$dest"/primes/{Proofs,Gate,Spec}
cd "$dest"
git init -q
printf '.lake/\n' > .gitignore
cd primes
cp "$src"/{lean-toolchain,lake-manifest.json,Challenge.lean} .
cat > lakefile.toml <<'EOF'
name = "primes"
defaultTargets = ["Challenge"]

[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4.git"
rev = "v4.34.1"

[[lean_lib]]
name = "Challenge"

[[lean_lib]]
name = "Spec"
globs = ["Spec.+"]

[[lean_lib]]
name = "Proofs"
globs = ["Proofs.+"]
EOF
rename() { perl -pe 's/(?<![.\w])prime_mod_four\b/primeModFour/g; s/(?<![.\w])mul_one_mod_four\b/mulOneModFour/g;
  s/(?<![.\w])factor_three_mod_four\b/factorThreeModFour/g; s/(?<![.\w])euclid_mod_four\b/euclidModFour/g;
  s/(?<![.\w])not_dvd_euclid\b/notDvdEuclid/g; s/(?<![.\w])dvd_factorial\b/dvdFactorial/g;
  s/(?<![.\w])set_form\b/setForm/g' "$1"; }  # not after a dot: Nat.dvd_factorial is Mathlib's
for f in "$src"/Gate/*.lean; do
  leaf=$(basename "$f" .lean)
  [ "$leaf" = OddFactorThree ] && continue
  rename "$f" > "Gate/$leaf.lean"
  if [ "$leaf" = Root ]; then
    printf 'import Challenge\n\ntheorem root : S_root := sorry\n' > Spec/Root.lean
  else
    type=$(grep '^example : ' "Gate/$leaf.lean" | sed -E 's/^example : (.*) := [A-Za-z]+$/\1/')
    thm=$(grep '^#print axioms ' "Gate/$leaf.lean" | awk '{print $3}')
    printf 'import Challenge\n\ntheorem %s : %s := sorry\n' "$thm" "$type" > "Spec/$leaf.lean"
  fi
done
git add -A && git -c user.name=gate -c user.email=gate@localhost commit -qm "trusted tree"
git rev-parse HEAD
for f in "$src"/Proofs/*.lean; do
  leaf=$(basename "$f" .lean)
  [ "$leaf" = OddFactorThree ] && continue
  rename "$f" > "Proofs/$leaf.lean"
done
