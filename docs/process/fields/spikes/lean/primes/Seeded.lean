import Mathlib

/-!
# Seeded defects: statements a tired planner might write, each wrong in a known way

Not part of the honest tree (`Challenge.lean`). Read-only, like the challenge.
-/

/-- FALSE (n = 5): "every odd n > 1 has a prime factor that is 3 mod 4". It would replace the key
lemma and make Euclid's argument look easier. -/
def S_odd_factor_three : Prop := ∀ n : ℕ, n % 2 = 1 → 1 < n → ∃ p, p.Prime ∧ p ∣ n ∧ p % 4 = 3

/-- FALSE (P = 0), the ℕ-subtraction off-by-one: `S_euclid_mod_four` without `0 < P`. -/
def S_euclid_mod_four_any : Prop := ∀ P : ℕ, (4 * P - 1) % 4 = 3

/-- VACUOUS: no n is both 3 mod 4 and even, so this holds and says nothing. -/
def S_even_three_mod_four : Prop :=
  ∀ n : ℕ, n % 4 = 3 → n % 2 = 0 → ∃ p, p.Prime ∧ p ∣ n ∧ p % 4 = 1
