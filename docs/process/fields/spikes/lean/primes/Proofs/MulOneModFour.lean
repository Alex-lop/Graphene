import Challenge

theorem mul_one_mod_four : S_mul_one_mod_four := by
  intro a b ha
  rw [Nat.mul_mod, ha, one_mul, Nat.mod_mod]
