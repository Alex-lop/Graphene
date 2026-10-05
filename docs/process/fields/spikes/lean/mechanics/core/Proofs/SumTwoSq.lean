import Challenge

theorem sumTwoSq : S_sqMod4 → S_sumTwoSq := by
  intro h a b
  rcases h a with ha | ha <;> rcases h b with hb | hb <;> omega
