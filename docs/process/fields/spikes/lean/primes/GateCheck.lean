import Lean

/-!
# The leaf's type and axioms, asked of the environment, never of text the leaf could have changed

    lake env lean --run GateCheck.lean MODULE THEOREM=S_need₁,…,S_leaf [THEOREM=… …]

`Gate/<Leaf>.lean` states the expected type as Lean source, and compiling it is not a check: the
leaf's own file is imported *before* the gate file is parsed, so a `macro "S_leaf" : term => `(True)`
or a higher-priority `#print axioms` syntax in the leaf rewrites what the gate says (shown in the
README, section 3). This program is parsed before anything of the leaf is loaded: it imports MODULE's
compiled environment at run time and, for each THEOREM, checks that
1. it exists, was declared in MODULE, and is a `theorem`;
2. every `S_…` named was declared in `Challenge` or `Seeded`, the read-only modules;
3. its type is `S_need₁ → … → S_leaf` up to unfolding, by the kernel's `isDefEq`;
4. `collectAxioms` finds nothing beyond `propext`, `Classical.choice` and `Quot.sound`.
It prints one line per theorem and exits 0 only when every check holds for every theorem.
-/

open Lean Meta

def allowed : List Name := [``propext, ``Classical.choice, ``Quot.sound]
def readOnly : List Name := [`Challenge, `Seeded]

def moduleOf (env : Environment) (n : Name) : Option Name :=
  (env.getModuleIdxFor? n).bind fun i => env.header.moduleNames[i.toNat]?

/-- `none` when every check holds, else what failed. -/
def checkOne (env : Environment) (mod thm : Name) (stmts : List Name) : MetaM (Option String) := do
  let some info := env.find? thm | return some s!"{thm} does not exist"
  unless moduleOf env thm == some mod do return some s!"{thm} was not declared in {mod}"
  unless info matches .thmInfo _ do return some s!"{thm} is not a theorem"
  for s in stmts do
    unless (moduleOf env s).any (readOnly.contains ·) do
      return some s!"{s} is not a statement of the read-only modules {readOnly}"
  let some last := stmts.getLast? | return some "no statement given"
  let expected := stmts.dropLast.foldr (fun s acc => .forallE `_ (.const s []) acc .default) (.const last [])
  -- the kernel's definitional equality: no unification hints, instances or attributes of the leaf's
  unless (Kernel.isDefEq env {} info.type expected) matches .ok true do
    return some s!"{thm} : {← ppExpr info.type}, not {← ppExpr expected}"
  let bad := (← collectAxioms thm).toList.filter (!allowed.contains ·)
  unless bad.isEmpty do return some s!"{thm} uses axioms beyond the standard three: {bad}"
  return none

def main (args : List String) : IO UInt32 := do
  let mod :: specs@(_ :: _) := args
    | IO.eprintln "usage: GateCheck.lean MODULE THEOREM=S_a,S_b,…,S_leaf …"; return 2
  initSearchPath (← findSysroot)
  let mod := mod.toName
  let env ← importModules #[{ module := mod }] {} (trustLevel := 0)
  let mut failed := false
  for spec in specs do
    let thm :: rest :: _ := spec.splitOn "=" | IO.eprintln s!"not THEOREM=S_…: {spec}"; return 2
    let stmts := (rest.splitOn ",").map (·.toName)
    let ctx : Core.Context := { fileName := "<GateCheck>", fileMap := default, maxHeartbeats := 0 }
    let (r, _) ← (MetaM.run' (checkOne env mod thm.toName stmts)).toIO ctx { env }
    match r with
    | none =>
      let (axs, _) ← (collectAxioms thm.toName : CoreM _).toIO ctx { env }
      IO.println s!"GateCheck {thm}: ok; axioms {axs.toList}"
    | some why =>
      IO.println s!"GateCheck {thm}: FAIL: {why}"
      failed := true
  return if failed then 1 else 0
