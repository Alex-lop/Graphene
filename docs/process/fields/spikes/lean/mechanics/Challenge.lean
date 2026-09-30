import Mathlib

/-!
# Challenge: read-only for every leaf

Every definition the statements use, and each node's statement as a `Prop`-valued definition.
The tree: `root` needs `sumTwoSq`, which needs `sqMod4`.
-/

/-- Every integer square is 0 or 1 modulo 4. -/
def S_sqMod4 : Prop := ∀ n : ℤ, n ^ 2 % 4 = 0 ∨ n ^ 2 % 4 = 1

/-- A sum of two integer squares is never 3 modulo 4. Needs: `sqMod4`. -/
def S_sumTwoSq : Prop := ∀ a b : ℤ, (a ^ 2 + b ^ 2) % 4 ≠ 3

/-- The root: a natural number that is 3 modulo 4 is not a sum of two integer squares. -/
def S_root : Prop := ∀ n : ℕ, n % 4 = 3 → ¬ ∃ a b : ℤ, a ^ 2 + b ^ 2 = n
