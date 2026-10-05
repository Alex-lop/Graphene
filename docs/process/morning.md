# morning.md — 2026-10-05 — the cut

Rollback: `main` is untouched at `4e5a2a9`. To drop the night: close the PR, `git push origin --delete cut`.

## The brief

**1. Before and after**
- Before (`4e5a2a9`): 13 root commands, 18 under `plan`, 13 under `node`. 22,591 source lines.
  1,626 tests. 1,214 tracked files. A `--depth 1` clone is 22 MB.
- Lane 0, before: `graphene run` left `M app.py` ("sneaky" 3 times) and `?? README.md`
  in the person's checkout. Transcript: `docs/process/cut/before/lane0-transcript.txt`.
- After lane 1: `git status --short` is empty. The attempt sits on `graphene/readme` in
  `.graphene/worktrees/readme`. `docs/process/cut/after/lane0-transcript.txt`.
- After the archive move: 307 tracked files. The rest is on the orphan branch `process` (`fb6a408`).

**2. Run in five minutes** — not yet.
**3. The experiment** (`docs/test/PROVE.md`, `docs/test/PREREG-statements.md`)
- `statements`: a 1,328-line service, 5 traps, 24 hidden checks, 12 held out. Estimate: 20-60 min
  and $3-10 a run, 4 runs. The rehearsal, no model: trip-all scores 5, trip-none 0, both clocks set.
- My prediction, pre-registered: the paragraph ties or wins on traps and minutes. The tree wins only
  on time to the first wrong inference, and only if its board names the rounding conflict.
**4. Dogfood** (`docs/process/cut/dogfood.md`)
- 22 min for a 14-node tree of lane 2; the first answer was unreadable. It caught one thing I missed:
  without `graphene ui`, nothing refreshes the commits `node show` credits. Plan-first stopped
  helping at minute 11, when I started the work without its tree.
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
- **00:15** Wave one started: five worktrees off `cut`, one agent each (lane 1, lane 4, the UI,
  the archive, Nemotron). Lane 5 started at 00:20 in a sixth.
- **00:26** The dogfood tree arrived. `docs/process/cut/dogfood.md`.
- **00:27** Lane 1 and the archive move merged into `cut` (`c4a25cd`). Lane 1 also fixed the hook:
  a Claude Code executor could not write in a run's worktree. `process` and `cut` pushed.
- **00:31** The web UI deletion merged: one commit, `659c89e`, that `git revert` undoes. The tag
  `last-with-ui` marks its parent `66125f0` (local; not pushed). `node show` now fills the commits it
  credits, which only the page did before (the dogfood's catch).
- **00:36** Full suite at `c4a25cd` (lane 1 + archive): 1,605 passed, 21 skipped. Ruff clean.
- **00:39** Nemotron merged as an extra behind `extra.py`. Without `[nemotron]`, no Token Factory
  module loads; a boundary test fails on any other import.
- **00:41** Lane 5 merged. `plan first` is `on`, `auto` or `off`; `auto` is the default and an old
  `on` reads as `auto`. The four Tuesday messages each became one leaf, done. The feeds paragraph
  also became one leaf, not a tree, and was done right (18/20, 12/12). `docs/process/cut/lane5-evidence.md`.
- **00:43** Wave two started: the visible surface and the help text, one agent.
- **01:05** Lane 4 merged: the `statements` task, its checks, `tally.py --traps`, the
  pre-registration and the runbook. Full suite at `22ee8f9`: 1,540 passed, 21 skipped.
