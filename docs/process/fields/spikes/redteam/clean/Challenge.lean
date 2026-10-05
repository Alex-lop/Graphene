/-! Challenge (core Lean only): read-only for every leaf. Holds every definition the statements use
    and each statement as a `Prop`-valued definition. A leaf never restates this; it proves `S_<leaf>`
    by name, so the statement is a constant already elaborated against these trusted definitions. -/

/-- A definition a statement depends on. The shadowing exploits try to redefine this. -/
def Doubles (n : Nat) : Prop := n + n = 2 * n

/-- The target: doubling is adding to itself. True; provable; depends on `Doubles`. -/
def S_target : Prop := ∀ n : Nat, Doubles n
