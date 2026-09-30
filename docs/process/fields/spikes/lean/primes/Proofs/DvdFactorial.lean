import Challenge

theorem dvd_factorial : S_dvd_factorial := by
  intro p n hp hpn
  exact Nat.dvd_factorial hp hpn
