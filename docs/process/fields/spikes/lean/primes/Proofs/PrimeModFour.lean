import Challenge

theorem prime_mod_four : S_prime_mod_four := by
  intro p hp h2
  rcases hp.eq_two_or_odd with h | h
  · exact absurd h h2
  · omega
