import Proofs.PrimeModFour

/-! Gate for leaf `prime_mod_four`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_prime_mod_four := prime_mod_four

#print axioms prime_mod_four
