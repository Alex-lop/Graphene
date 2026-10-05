import Proofs.SetForm

/-! Gate for leaf `set_form`, written from the tree, never by a leaf. It does not compile unless the
leaf's theorem has the type below (up to unfolding, so the same proposition); `check-leaf.sh`
reads the axioms it prints. -/

example : S_root → S_root_set := set_form

#print axioms set_form
