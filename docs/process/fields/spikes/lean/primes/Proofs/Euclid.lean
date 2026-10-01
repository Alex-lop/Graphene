import Challenge

/-- Euclid's argument: given `n`, the number `4 * n! - 1` is 3 mod 4, so it has a prime factor
`p` that is 3 mod 4; if `p ≤ n` then `p ∣ n!`, and then `p` cannot divide `4 * n! - 1`. -/
theorem euclid (hkey : S_factor_three_mod_four) (hmod : S_euclid_mod_four)
    (hnd : S_not_dvd_euclid) (hfac : S_dvd_factorial) : S_root := by
  intro n
  have hP : 0 < Nat.factorial n := Nat.factorial_pos n
  obtain ⟨p, hp, hpN, hp3⟩ := hkey _ (hmod _ hP)
  refine ⟨p, ?_, hp, hp3⟩
  by_contra hle
  push_neg at hle
  exact hnd _ p hP hp (hfac p n hp.pos hle) hpN
