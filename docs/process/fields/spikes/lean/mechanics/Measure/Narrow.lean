import Mathlib.Tactic.NormNum.Basic

theorem clean (a b : ℤ) (ha : a % 4 = 1) (hb : b % 4 = 2) : (a * b) % 4 = 2 := by
  rw [Int.mul_emod, ha, hb]; norm_num

#print axioms clean
