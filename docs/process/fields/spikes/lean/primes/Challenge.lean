import Mathlib

/-!
# Challenge: infinitely many primes are congruent to 3 mod 4

Read-only for every leaf. Each leaf's statement is a `Prop`-valued definition `S_<leaf>`; the leaf
proves `S_<need₁> → … → S_<leaf>` in `Proofs/<Leaf>.lean`, and `Gate/<Leaf>.lean` asserts that type.
Everything is in `ℕ`, where `a - b = 0` when `a ≤ b` and `a % 0 = a`.
-/

/-- The root, as a person asks it: past every `n` there is a prime `p` with `p % 4 = 3`. -/
def S_root : Prop := ∀ n : ℕ, ∃ p, n < p ∧ p.Prime ∧ p % 4 = 3

/-- The root in the form Mathlib usually states such results: the set of those primes is infinite. -/
def S_root_set : Prop := {p : ℕ | p.Prime ∧ p % 4 = 3}.Infinite

/-- A prime other than 2 is 1 or 3 mod 4. -/
def S_prime_mod_four : Prop := ∀ p : ℕ, p.Prime → p ≠ 2 → p % 4 = 1 ∨ p % 4 = 3

/-- Multiplying by a number that is 1 mod 4 keeps the residue mod 4. -/
def S_mul_one_mod_four : Prop := ∀ a b : ℕ, a % 4 = 1 → a * b % 4 = b % 4

/-- The key lemma: a number that is 3 mod 4 has a prime factor that is 3 mod 4. -/
def S_factor_three_mod_four : Prop := ∀ n : ℕ, n % 4 = 3 → ∃ p, p.Prime ∧ p ∣ n ∧ p % 4 = 3

/-- Euclid's number `4P - 1` is 3 mod 4. In `ℕ`, `4 * 0 - 1 = 0`, so this needs `0 < P`. -/
def S_euclid_mod_four : Prop := ∀ P : ℕ, 0 < P → (4 * P - 1) % 4 = 3

/-- A prime dividing `P` does not divide `4P - 1`. In `ℕ`, `P = 0` makes `4P - 1 = 0`, which every
`p` divides, so this needs `0 < P` too. -/
def S_not_dvd_euclid : Prop := ∀ P p : ℕ, 0 < P → p.Prime → p ∣ P → ¬ p ∣ 4 * P - 1

/-- Every `p` with `0 < p ≤ n` divides `n!`. -/
def S_dvd_factorial : Prop := ∀ p n : ℕ, 0 < p → p ≤ n → p ∣ Nat.factorial n
