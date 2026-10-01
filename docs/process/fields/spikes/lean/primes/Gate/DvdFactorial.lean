import Proofs.DvdFactorial

/-! Gate for leaf `dvd_factorial`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_dvd_factorial := dvd_factorial

#print axioms dvd_factorial
