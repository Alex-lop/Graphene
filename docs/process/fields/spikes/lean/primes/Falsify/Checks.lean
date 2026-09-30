import Plausible

/-!
# Checks before spend: a counterexample search and a vacuity test, for any leaf statement

`#falsify S_x`: `plausible` on the statement as written (its definition unfolded). Prints
`FALSIFY S_x counterexample <ms> <witness>`, `FALSIFY S_x none-found <ms>`,
`FALSIFY S_x gave-up <ms> …` (random values never met the hypotheses: a hint of vacuity) or
`FALSIFY S_x cannot-test <ms> <why>` (plausible needs every part of the statement to be decidable).

`#vacuity S_x`: are the statement's hypotheses satisfiable at all? It builds `∀ xs, ¬ (H₁ ∧ … ∧ Hₖ)`
from `∀ xs, H₁ → … → Hₖ → C` and runs `plausible` on that: a counterexample is an example where every
hypothesis holds (`satisfiable`). If none is found it tries to prove that no example exists
(`omega`, `decide`, `simp_all`, `grind`): `VACUOUS` when one does. Prints `VACUITY S_x ...`.
-/

open Lean Elab Command Meta Tactic

private def emit (s : String) : IO Unit := do
  let out ← IO.getStdout
  out.putStrLn s
  out.flush

private def oneLine (e : Exception) : MetaM String := do
  let s ← e.toMessageData.toString
  let all := " ".intercalate ((s.splitOn "\n").map (·.trimAscii.toString) |>.filter (· ≠ ""))
  return (all.take 300).toString

/-- The body of a `def S_x : Prop := body`. -/
private def body (id : Ident) : MetaM Expr := do
  let c ← realizeGlobalConstNoOverload id
  let some v := (← getConstInfo c).value? | throwError "{c} has no body"
  return v

/-- Run `tac` on a fresh goal `goal`; `none` when it closed the goal with no `sorry`, else the error
(or "admitted" when the tactic closed it with `sorry`, as plausible does when it finds nothing). -/
private def runOn (goal : Expr) (tac : Syntax) : TermElabM (Option String) := do
  let mvar ← mkFreshExprMVar goal
  tryCatchRuntimeEx (do
    let gs ← Term.withoutErrToSorry <| Tactic.run mvar.mvarId! (evalTactic tac)
    if !gs.isEmpty then return some "goals remain"
    let v ← instantiateMVars mvar
    if !(v.hasSyntheticSorry || v.hasSorry) then return none
    -- plausible admits both when it found nothing and when it gave up (a warning says which)
    let log := (← getThe Core.State).messages
    for m in log.unreported.toList do
      let said ← m.data.toString
      if (said.splitOn "Gave up").length > 1 then return some said
    return some "admitted")
    (fun e => return some (← oneLine e))

private def timed (x : TermElabM α) : TermElabM (α × Nat) := do
  let t0 ← IO.monoMsNow
  let a ← x
  return (a, (← IO.monoMsNow) - t0)

elab "#falsify " id:ident : command => liftTermElabM do
  let stmt ← body id
  let (r, ms) ← timed <| runOn stmt (← `(tactic| plausible))
  let name := id.getId
  match r with
  | some e =>
    if (e.splitOn "Found a counter-example").length > 1 then
      emit s!"FALSIFY {name} counterexample {ms} {e}"
    else if (e.splitOn "Gave up").length > 1 then
      emit s!"FALSIFY {name} gave-up {ms} {e}"
    else if e == "admitted" then emit s!"FALSIFY {name} none-found {ms}"
    else emit s!"FALSIFY {name} cannot-test {ms} {e}"
  | none => emit s!"FALSIFY {name} none-found {ms} (plausible closed it)"

/-- `∀ xs, ¬ (H₁ ∧ … ∧ Hₖ)` from `∀ xs, H₁ → … → Hₖ → C`; the conclusion is kept out even when it is
a `¬`, because the telescope does not unfold `Not`. -/
private def noExample (stmt : Expr) : MetaM (Option Expr) :=
  forallTelescope stmt fun xs _ => do
    let mut vars := #[]
    let mut hyps := #[]
    for x in xs do
      let t ← inferType x
      if ← isProp t then hyps := hyps.push t else vars := vars.push x
    if hyps.isEmpty then return none
    let conj := hyps.pop.foldr mkAnd hyps.back!
    return some (← mkForallFVars vars (mkNot conj))

elab "#vacuity " id:ident : command => liftTermElabM do
  let name := id.getId
  match ← noExample (← body id) with
  | none => emit s!"VACUITY {name} no-hypotheses 0"
  | some q =>
    let (r, ms) ← timed <| runOn q (← `(tactic| plausible))
    if let some e := r then
      if (e.splitOn "Found a counter-example").length > 1 then
        emit s!"VACUITY {name} satisfiable {ms} {e}"
        return
    let provers := [("omega", ← `(tactic| omega)), ("decide", ← `(tactic| decide)),
      ("simp_all", ← `(tactic| simp_all)), ("grind", ← `(tactic| grind))]
    for (tacName, tac) in provers do
      let (r2, ms2) ← timed <| runOn q tac
      if r2.isNone then
        emit s!"VACUITY {name} VACUOUS {ms + ms2} its hypotheses cannot all hold: proved by {tacName}"
        return
    emit s!"VACUITY {name} unknown {ms} no example found, and no proof that none exists"
