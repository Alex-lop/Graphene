import Mathlib

theorem withNative : (2 : ℕ) ^ 20 % 7 = 4 := by native_decide

#print axioms withNative
