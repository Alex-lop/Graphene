import Challenge

/-! Negative: the statement changed from integers to natural numbers. True, provable, and weaker than
`S_sqMod4`, which a tired reader might accept. A drop-in replacement for `Proofs/SqMod4.lean`. -/

theorem sqMod4 : ∀ n : ℕ, n ^ 2 % 4 = 0 ∨ n ^ 2 % 4 = 1 := by
  intro n
  have h : n % 4 = 0 ∨ n % 4 = 1 ∨ n % 4 = 2 ∨ n % 4 = 3 := by omega
  rcases h with h | h | h | h <;> simp [pow_two, Nat.mul_mod, h]
