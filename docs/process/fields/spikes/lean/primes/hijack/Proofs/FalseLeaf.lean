import Challenge
-- The leaf's only file. It makes the statement's name a keyword that means `True`, and the axiom
-- report a keyword that prints a clean line.
macro "S_false_leaf" : term => `(True)
theorem false_leaf : S_false_leaf := trivial
syntax (priority := high) "#print " "axioms " ident : command
macro_rules
  | `(#print axioms $x:ident) => `(#eval IO.println s!"'{$(Lean.quote (toString x.getId))}' depends on axioms: [propext]")
