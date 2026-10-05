import Auto.Harness
set_option Elab.async false

theorem t_closed : 2 + 2 = 4 := by attempt "t/closed" 5 (decide)
#print axioms t_closed
theorem t_failed : ∀ n : Nat, n + 0 = n + 1 := by attempt "t/failed" 5 (omega)
#print axioms t_failed
theorem t_left : ∀ n : Nat, n = n + 0 ∧ n = 5 := by attempt "t/left" 5 (simp)
#print axioms t_left
theorem t_timeout : ∀ n : Nat, n = n := by attempt "t/timeout" 3 (repeat (first | (have : True := trivial) | skip))
#print axioms t_timeout
theorem t_after : 1 = 1 := by attempt "t/after" 5 (rfl)
#print axioms t_after
