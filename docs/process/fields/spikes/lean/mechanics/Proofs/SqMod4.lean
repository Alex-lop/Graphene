import Challenge

theorem sqMod4 : S_sqMod4 := by
  intro n
  have h : n % 4 = 0 ∨ n % 4 = 1 ∨ n % 4 = 2 ∨ n % 4 = 3 := by omega
  rcases h with h | h | h | h <;> simp [pow_two, Int.mul_emod, h]
