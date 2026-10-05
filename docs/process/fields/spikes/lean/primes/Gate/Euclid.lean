import Proofs.Euclid

/-! Gate for leaf `euclid`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := euclid

#print axioms euclid
