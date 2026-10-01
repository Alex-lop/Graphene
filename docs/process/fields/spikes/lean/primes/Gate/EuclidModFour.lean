import Proofs.EuclidModFour

/-! Gate for leaf `euclid_mod_four`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_euclid_mod_four := euclid_mod_four

#print axioms euclid_mod_four
