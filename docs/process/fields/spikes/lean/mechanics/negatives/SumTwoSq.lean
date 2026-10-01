import Challenge

/-! Negative: an extra hypothesis (`Odd a`) weakens the statement. A drop-in replacement for
`Proofs/SumTwoSq.lean`. -/

theorem sumTwoSq : S_sqMod4 → ∀ a b : ℤ, Odd a → (a ^ 2 + b ^ 2) % 4 ≠ 3 := by
  intro h a b _
  rcases h a with ha | ha <;> rcases h b with hb | hb <;> omega
