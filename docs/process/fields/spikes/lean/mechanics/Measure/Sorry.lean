import Mathlib

theorem withSorry (a b : ℤ) (ha : a % 4 = 1) (hb : b % 4 = 2) : (a * b) % 4 = 2 := by
  sorry

#print axioms withSorry
