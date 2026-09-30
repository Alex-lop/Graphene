import Seeded

/-! The seeded false leaf. It cannot be proven (n = 5 is a counterexample); this file is what an
executor that tried and gave up would leave. `check-leaf.sh OddFactorThree` must fail on it. -/

theorem odd_factor_three : S_odd_factor_three := by
  sorry
