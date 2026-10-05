import Challenge

theorem sqMod4 : S_sqMod4 := by
  intro n
  rw [Nat.mul_mod]
  have h : n % 4 < 4 := Nat.mod_lt _ (by decide)
  generalize n % 4 = k at *
  match k, h with
  | 0, _ | 1, _ | 2, _ | 3, _ => decide
