/-! Challenge (core Lean only): read-only for every leaf. -/

/-- The square of a natural number is 0 or 1 modulo 4. -/
def S_sqMod4 : Prop := ∀ n : Nat, n * n % 4 = 0 ∨ n * n % 4 = 1

/-- A sum of two squares of natural numbers is never 3 modulo 4. Needs: `sqMod4`. -/
def S_sumTwoSq : Prop := ∀ a b : Nat, (a * a + b * b) % 4 ≠ 3
