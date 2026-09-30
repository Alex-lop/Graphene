import Mathlib

axiom cheat : ∀ a b : ℤ, a % 4 = 1 → b % 4 = 2 → (a * b) % 4 = 2

theorem withAxiom (a b : ℤ) (ha : a % 4 = 1) (hb : b % 4 = 2) : (a * b) % 4 = 2 :=
  cheat a b ha hb

#print axioms withAxiom
