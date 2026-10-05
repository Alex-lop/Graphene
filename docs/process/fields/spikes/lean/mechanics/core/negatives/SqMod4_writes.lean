import Challenge

/-! Negative: a correct proof whose file also writes outside `.lake` while it is compiled (here, it
rewrites the challenge stub the checker reads next). Under comparator's landrun sandbox the write
must fail; without a sandbox it succeeds. -/

#eval IO.FS.writeFile "Spec/SqMod4.lean" "import Challenge\n\ntheorem sqMod4 : True := sorry\n"

theorem sqMod4 : S_sqMod4 := by
  intro n
  rw [Nat.mul_mod]
  have h : n % 4 < 4 := Nat.mod_lt _ (by decide)
  generalize n % 4 = k at *
  match k, h with
  | 0, _ | 1, _ | 2, _ | 3, _ => decide
