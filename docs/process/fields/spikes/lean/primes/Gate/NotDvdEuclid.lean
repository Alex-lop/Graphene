import Proofs.NotDvdEuclid

/-! Gate for leaf `not_dvd_euclid`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_not_dvd_euclid := not_dvd_euclid

#print axioms not_dvd_euclid
