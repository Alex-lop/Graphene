import Challenge

/-! Negative: a changed constant (mod 3 instead of mod 4). True and provable; not `S_sqMod4`. -/

theorem sqMod4 : ∀ n : Nat, n * n % 3 = 0 ∨ n * n % 3 = 1 := by
  intro n
  rw [Nat.mul_mod]
  have h : n % 3 < 3 := Nat.mod_lt _ (by decide)
  generalize n % 3 = k at *
  match k, h with
  | 0, _ | 1, _ | 2, _ => decide
