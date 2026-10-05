# morning.md — 2026-10-05 — the cut

Rollback: `main` is untouched at `4e5a2a9`. To drop the night: close the PR, `git push origin --delete cut`.

## The brief

**1. Before and after**
- Before (`4e5a2a9`): 13 root commands, 18 under `plan`, 13 under `node`. 22,591 source lines.
  1,626 tests. 1,214 tracked files. A `--depth 1` clone is 22 MB.
- Lane 0, before: `graphene run` left `M app.py` ("sneaky" 3 times) and `?? README.md`
  in the person's checkout. Transcript: `docs/process/cut/before/lane0-transcript.txt`.
- After: not yet.

**2. Run in five minutes** — not yet.
**3. The experiment** — not yet.
**4. Dogfood** — not yet.
**5. Decide** — not yet.
**6. Broken or risky** — not yet.

---

## What was done, in order

- **00:00** Branch `cut` from origin/main `4e5a2a9`, in a worktree of its own. The directive is
  committed at `docs/process/directives/CUT_DIRECTIVE.md`. Its "Alex decides" block was still in
  the file, so every default holds: delete the web UI, hide `direction`, `plan first` auto,
  Nemotron as an extra, lanes 1 to 5.
- **00:10** Lane 0. The wheel from `4e5a2a9` is installed as a tool in its own directory. The five
  `--help` outputs, the counts and the transcript are in `docs/process/cut/before/`.
