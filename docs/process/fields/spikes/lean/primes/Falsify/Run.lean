import Challenge
import Seeded
import Falsify.Checks
import Auto.Harness

/-!
# The checks a machine can run before any spend, on every leaf and on the seeded defects

Run: `lake env lean Falsify/Run.lean`. Every line of the form `FALSIFY`, `VACUITY`, `START`/`RESULT`
is a result; see the README for the table.
-/

set_option Elab.async false

/-! ## 1. `plausible` on each statement as written, and the vacuity test on its hypotheses -/

#falsify S_root
#falsify S_prime_mod_four
#falsify S_mul_one_mod_four
#falsify S_factor_three_mod_four
#falsify S_euclid_mod_four
#falsify S_not_dvd_euclid
#falsify S_dvd_factorial
#falsify S_odd_factor_three
#falsify S_euclid_mod_four_any
#falsify S_even_three_mod_four

#vacuity S_prime_mod_four
#vacuity S_mul_one_mod_four
#vacuity S_factor_three_mod_four
#vacuity S_euclid_mod_four
#vacuity S_not_dvd_euclid
#vacuity S_dvd_factorial
#vacuity S_odd_factor_three
#vacuity S_euclid_mod_four_any
#vacuity S_even_three_mod_four

/-! ## 2. The unbounded `∃ p` has no decision procedure, so bound it (a prime factor of n > 0 is ≤ n).
These restatements stand in for a machine's rewrite (written by hand here; no planner or rule was
tried), not the person's statement: each is equivalent to the
original only by the one-line fact that a divisor of a positive n is at most n. -/

def S_factor_three_mod_four_le : Prop := ∀ n : ℕ, n % 4 = 3 → ∃ p ≤ n, p.Prime ∧ p ∣ n ∧ p % 4 = 3
def S_odd_factor_three_le : Prop := ∀ n : ℕ, n % 2 = 1 → 1 < n → ∃ p ≤ n, p.Prime ∧ p ∣ n ∧ p % 4 = 3

#falsify S_factor_three_mod_four_le
#falsify S_odd_factor_three_le

/-! ## 3. `decide` on small bounded instances -/

theorem d_odd_30 : ∀ n < 30, n % 2 = 1 → 1 < n → ∃ p ≤ n, p.Prime ∧ p ∣ n ∧ p % 4 = 3 := by
  attempt "decide/odd_factor_three n<30" 60 (decide)
theorem d_odd_10 : ∀ n < 10, n % 2 = 1 → 1 < n → ∃ p ≤ n, p.Prime ∧ p ∣ n ∧ p % 4 = 3 := by
  attempt "decide/odd_factor_three n<10" 60 (decide)
theorem d_key_30 : ∀ n < 30, n % 4 = 3 → ∃ p ≤ n, p.Prime ∧ p ∣ n ∧ p % 4 = 3 := by
  attempt "decide/factor_three_mod_four n<30" 60 (decide)
#print axioms d_key_30
theorem d_euclid_any_10 : ∀ P < 10, (4 * P - 1) % 4 = 3 := by
  attempt "decide/euclid_mod_four_any P<10" 60 (decide)
theorem d_euclid_10 : ∀ P < 10, 0 < P → (4 * P - 1) % 4 = 3 := by
  attempt "decide/euclid_mod_four P<10" 60 (decide)
#print axioms d_euclid_10

/-! ## 4. The witness a hand-back carries: every counterexample below 60, and a proof of the negation -/

#eval (List.range 60).filter fun n => n % 2 = 1 && 1 < n && (n.primeFactorsList.all fun p => p % 4 != 3)
#eval Nat.primeFactorsList 5

theorem odd_factor_three_false : ¬ S_odd_factor_three := by
  intro h
  obtain ⟨p, hp, hpd, h3⟩ := h 5 (by norm_num) (by norm_num)
  rcases (Nat.dvd_prime (by norm_num)).mp hpd with rfl | rfl
  · exact Nat.not_prime_one hp
  · norm_num at h3
#print axioms odd_factor_three_false

theorem euclid_mod_four_any_false : ¬ S_euclid_mod_four_any := fun h => by
  have := h 0
  norm_num at this
#print axioms euclid_mod_four_any_false

theorem even_three_mod_four_vacuous : ¬ ∃ n : ℕ, n % 4 = 3 ∧ n % 2 = 0 := by
  rintro ⟨n, h1, h2⟩
  omega
#print axioms even_three_mod_four_vacuous

/-! ## 5. Library contamination: the whole theorem is one application of Dirichlet's theorem

Mathlib states Dirichlet's theorem as `Nat.forall_exists_prime_gt_and_modEq` (and, with `ZMod`, as
`Nat.forall_exists_prime_gt_and_eq_mod`). Whoever knows the name closes the root in one line; the
automation table says whether any tactic finds it without being told. -/

theorem root_by_dirichlet : S_root := fun n => by
  obtain ⟨p, hpn, hp, h⟩ :=
    Nat.forall_exists_prime_gt_and_modEq n (q := 4) (a := 3) (by norm_num) (by norm_num)
  exact ⟨p, hpn, hp, h⟩
#print axioms root_by_dirichlet
