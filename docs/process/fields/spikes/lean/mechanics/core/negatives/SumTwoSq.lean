import Challenge

/-! Negative: an extra hypothesis (`a % 2 = 1`) weakens the statement. -/

theorem sumTwoSq : S_sqMod4 → ∀ a b : Nat, a % 2 = 1 → (a * a + b * b) % 4 ≠ 3 := by
  intro h a b _
  rcases h a with ha | ha <;> rcases h b with hb | hb <;> omega
