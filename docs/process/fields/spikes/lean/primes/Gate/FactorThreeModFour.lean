import Proofs.FactorThreeModFour

/-! Gate for leaf `factor_three_mod_four`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := factor_three_mod_four

#print axioms factor_three_mod_four
