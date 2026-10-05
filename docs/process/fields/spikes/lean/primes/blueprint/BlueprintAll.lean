import Architect
import Mathlib

/-! The tree in LeanArchitect's form, in one file (Challenge.lean, the proofs, Root.lean and the attributes
concatenated by the README's command), so that Mathlib is loaded once. -/

-- from Challenge.lean

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

-- from Proofs/PrimeModFour.lean

theorem prime_mod_four : S_prime_mod_four := by
  intro p hp h2
  rcases hp.eq_two_or_odd with h | h
  · exact absurd h h2
  · omega

-- from Proofs/MulOneModFour.lean

theorem mul_one_mod_four : S_mul_one_mod_four := by
  intro a b ha
  rw [Nat.mul_mod, ha, one_mul, Nat.mod_mod]

-- from Proofs/FactorThreeModFour.lean

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

-- from Proofs/EuclidModFour.lean

theorem euclid_mod_four : S_euclid_mod_four := by
  intro P hP
  omega

-- from Proofs/NotDvdEuclid.lean

theorem not_dvd_euclid : S_not_dvd_euclid := by
  intro P p hP hp hpP hpN
  have h4 : p ∣ 4 * P := Dvd.dvd.mul_left hpP 4
  have h1 : p ∣ 4 * P - (4 * P - 1) := Nat.dvd_sub h4 hpN
  have : 4 * P - (4 * P - 1) = 1 := by omega
  rw [this] at h1
  exact hp.one_lt.ne' (Nat.dvd_one.mp h1)

-- from Proofs/DvdFactorial.lean

theorem dvd_factorial : S_dvd_factorial := by
  intro p n hp hpn
  exact Nat.dvd_factorial hp hpn

-- from Proofs/Euclid.lean

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

-- from Proofs/SetForm.lean

theorem set_form (h : S_root) : S_root_set := by
  apply Set.infinite_of_forall_exists_gt
  intro n
  obtain ⟨p, hnp, hp, hp3⟩ := h n
  exact ⟨p, ⟨hp, hp3⟩, hnp⟩

-- from Proofs/Root.lean

/-! Written from the tree, not by a leaf: each leaf applied to the leaves it needs. -/

theorem root : S_root :=
  euclid (factor_three_mod_four prime_mod_four mul_one_mod_four) euclid_mod_four not_dvd_euclid
    dvd_factorial

theorem root_set : S_root_set := set_form root

attribute [blueprint "prime_mod_four" (title := /-- Odd primes mod 4 -/)
  (statement := /-- A prime $p \neq 2$ satisfies $p \equiv 1$ or $p \equiv 3 \pmod 4$. -/)]
  prime_mod_four

attribute [blueprint "mul_one_mod_four"
  (statement := /-- If $a \equiv 1 \pmod 4$ then $ab \equiv b \pmod 4$. -/)]
  mul_one_mod_four

attribute [blueprint "factor_three_mod_four" (title := /-- Key lemma -/)
  (statement := /-- Every $n \equiv 3 \pmod 4$ has a prime factor $p \equiv 3 \pmod 4$. -/)
  (uses := ["prime_mod_four", "mul_one_mod_four"])]
  factor_three_mod_four

attribute [blueprint "euclid_mod_four"
  (statement := /-- For $P > 0$, $4P - 1 \equiv 3 \pmod 4$ (in $\mathbb{N}$, $4 \cdot 0 - 1 = 0$). -/)]
  euclid_mod_four

attribute [blueprint "not_dvd_euclid"
  (statement := /-- For $P > 0$, a prime $p \mid P$ does not divide $4P - 1$. -/)]
  not_dvd_euclid

attribute [blueprint "dvd_factorial"
  (statement := /-- Every $p$ with $0 < p \le n$ divides $n!$. -/)]
  dvd_factorial

attribute [blueprint "euclid" (title := /-- Euclid's argument -/)
  (statement := /-- For every $n$ there is a prime $p > n$ with $p \equiv 3 \pmod 4$. -/)
  (uses := ["factor_three_mod_four", "euclid_mod_four", "not_dvd_euclid", "dvd_factorial"])]
  euclid

attribute [blueprint "set_form"
  (statement := /-- The set of primes $p \equiv 3 \pmod 4$ is infinite. -/) (uses := ["euclid"])]
  set_form

attribute [blueprint "root" (title := /-- Infinitely many primes $\equiv 3 \pmod 4$ -/)
  (statement := /-- There are infinitely many primes congruent to $3$ mod $4$. -/)]
  root_set

#show_blueprint
