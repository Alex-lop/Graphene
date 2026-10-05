import Challenge

/-- Strong induction on `n`: take the least prime factor `q = n.minFac`. If `q % 4 = 3`, done.
Otherwise `q` is odd (n is), so `q % 4 = 1`, and `n = q * m` with `m % 4 = 3` and `m < n`. -/
theorem factor_three_mod_four (h1 : S_prime_mod_four) (h2 : S_mul_one_mod_four) :
    S_factor_three_mod_four := by
  intro n
  induction n using Nat.strong_induction_on with
  | _ n ih =>
    intro hn
    have hq : n.minFac.Prime := Nat.minFac_prime (by omega)
    obtain ⟨m, hm⟩ : n.minFac ∣ n := Nat.minFac_dvd n
    by_cases h3 : n.minFac % 4 = 3
    · exact ⟨n.minFac, hq, ⟨m, hm⟩, h3⟩
    · have hq2 : n.minFac ≠ 2 := by
        intro h
        rw [h] at hm
        omega
      have hq1 : n.minFac % 4 = 1 := by
        rcases h1 _ hq hq2 with h | h <;> omega
      have hm3 : m % 4 = 3 := by
        have := h2 _ m hq1
        rw [← hm] at this
        omega
      have hm0 : 0 < m := by omega
      have hmn : m < n := by
        have := hq.two_le
        rw [hm]
        nlinarith
      obtain ⟨p, hp, hpm, hp3⟩ := ih m hmn hm3
      refine ⟨p, hp, ?_, hp3⟩
      rw [hm]
      exact Dvd.dvd.mul_left hpm _
