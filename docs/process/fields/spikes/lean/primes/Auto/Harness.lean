import Lean

/-!
# `attempt`: one automation tactic on one goal, under a wall-clock limit

`attempt "label" secs (tac)` runs `tac` on the main goal and prints one line to stdout:
- `RESULT label closed <ms> <heartbeats>`: `tac` left no goal and logged no error;
- `RESULT label failed <ms> <first line of the error>`: it threw, or left goals, or logged an error;
  when it threw, `DETAIL label <the whole message on one line>` follows.

On failure the goal is closed with `sorry`, so the file goes on (and `#print axioms` on that theorem
shows `sorryAx`). After `secs` seconds a cancellation token is set: the tactic is interrupted at its
next check, the whole command is abandoned, and the line `START label` is left with no `RESULT`: that
is a timeout. Interrupts are not catchable inside the elaborator (`Core.tryCatch`), which is why a
timeout shows as a missing line rather than a line of its own.
-/

open Lean Elab Tactic Meta

syntax (name := attempt) "attempt " str num " (" tacticSeq ")" : tactic

private def emit (s : String) : IO Unit := do
  let out ← IO.getStdout
  out.putStrLn s
  out.flush

private def errorCount : CoreM Nat := do
  let log := (← getThe Core.State).messages
  return (log.reported.toList ++ log.unreported.toList).filter (·.severity == .error) |>.length

/-- The error's first line, and the next one too when the first only introduces it (`...:`). -/
private def firstLine (s : String) : String :=
  let ls := (s.splitOn "\n").map (·.trimAscii.toString) |>.filter (· ≠ "")
  match ls with
  | a :: b :: _ => if a.endsWith ":" then s!"{a} {b}" else a
  | [a] => a
  | [] => ""

@[tactic attempt] def evalAttempt : Tactic := fun stx => do
  let some label := stx[1].isStrLit? | throwUnsupportedSyntax
  let some secs := stx[2].isNatLit? | throwUnsupportedSyntax
  let tac := stx[4]
  let tk ← IO.CancelToken.new
  let _ ← IO.asTask (prio := .dedicated) do
    IO.sleep (secs * 1000).toUInt32
    tk.set
  emit s!"START {label}"
  let saved ← saveState
  let errs0 ← errorCount
  let hb0 ← IO.getNumHeartbeats
  let t0 ← IO.monoMsNow
  let err? ← withTheReader Core.Context (fun c => { c with cancelTk? := some tk, maxHeartbeats := 0 }) do
    tryCatchRuntimeEx (do evalTactic tac; pure none) (fun e => pure (some e))
  let ms := (← IO.monoMsNow) - t0
  let hb := ((← IO.getNumHeartbeats) - hb0) / 1000
  let left ← getUnsolvedGoals
  let errs ← errorCount
  let why? : Option String ← match err? with
    | some e => pure (some (firstLine (← e.toMessageData.toString)))
    | none =>
      if errs > errs0 then pure (some "the tactic logged an error")
      else if !left.isEmpty then
        pure (some s!"goals remain: {firstLine (toString (← ppGoal left.head!))}")
      else pure none
  match why? with
  | none => emit s!"RESULT {label} closed {ms} {hb}"
  | some why =>
    emit s!"RESULT {label} failed {ms} {why}"
    if let some e := err? then  -- the whole message on one line: a counterexample's witness lives here
      let all := " ".intercalate (((← e.toMessageData.toString).splitOn "\n").map (·.trimAscii.toString))
      emit s!"DETAIL {label} {all.take 400}"
    saved.restore
    for g in ← getUnsolvedGoals do
      admitGoal g
    setGoals []
