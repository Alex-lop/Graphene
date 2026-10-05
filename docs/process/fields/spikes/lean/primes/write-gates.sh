#!/usr/bin/env bash
# Writes Gate/<Leaf>.lean for each leaf from the table below (the tree's leaves, each with the type
# its theorem must have: its needs' statements as hypotheses, its own statement as the conclusion).
# Gates are read-only to every leaf; rerun this only when the person changes the tree.
set -euo pipefail
cd "$(dirname "$0")"
while IFS='|' read -r file thm type; do
  [ -z "$file" ] && continue
  cat > "Gate/$file.lean" <<EOF
import Proofs.$file

/-! Gate for leaf \`$thm\`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); \`check-leaf.sh\`
reads the axioms it prints. -/

example : $type := $thm

#print axioms $thm
EOF
done <<'EOF'
PrimeModFour|prime_mod_four|S_prime_mod_four
MulOneModFour|mul_one_mod_four|S_mul_one_mod_four
FactorThreeModFour|factor_three_mod_four|S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four
EuclidModFour|euclid_mod_four|S_euclid_mod_four
NotDvdEuclid|not_dvd_euclid|S_not_dvd_euclid
DvdFactorial|dvd_factorial|S_dvd_factorial
Euclid|euclid|S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root
SetForm|set_form|S_root → S_root_set
OddFactorThree|odd_factor_three|S_odd_factor_three
EOF
