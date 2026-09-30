import Challenge

theorem not_dvd_euclid : S_not_dvd_euclid := by
  intro P p hP hp hpP hpN
  have h4 : p ∣ 4 * P := Dvd.dvd.mul_left hpP 4
  have h1 : p ∣ 4 * P - (4 * P - 1) := Nat.dvd_sub h4 hpN
  have : 4 * P - (4 * P - 1) = 1 := by omega
  rw [this] at h1
  exact hp.one_lt.ne' (Nat.dvd_one.mp h1)
