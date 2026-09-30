import Duper
import Canonical
import Bench.Harness
set_option Elab.async false

theorem s_duper (p q : Prop) (hp : p) (hpq : p → q) : q := by attempt "smoke/duper" 60 (duper [*])
#print axioms s_duper
theorem s_canonical (p q : Prop) (hp : p) (hpq : p → q) : q := by attempt "smoke/canonical" 60 (canonical 10)
#print axioms s_canonical
theorem s_canonical_nat (a b : Nat) : a + b = b + a := by attempt "smoke/canonical-induction" 60 (canonical 10)
#print axioms s_canonical_nat
theorem s_duper_nat (a b : Nat) (h : a = b) : b = a := by attempt "smoke/duper-eq" 60 (duper [*])
#print axioms s_duper_nat
