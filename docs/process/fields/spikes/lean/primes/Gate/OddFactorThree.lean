import Proofs.OddFactorThree

/-! Gate for leaf `odd_factor_three`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_odd_factor_three := odd_factor_three

#print axioms odd_factor_three
