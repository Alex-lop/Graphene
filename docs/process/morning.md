# morning.md — 2026-10-05 — the cut

Rollback: `main` is untouched at `4e5a2a9`. To drop the night: close the PR, `git push origin --delete cut`.

## The brief

**1. Before → after.** Commands shown: 13 → 9 at the top, 18 → 8 under `plan`, 13 → 9 under `node`.
- Python source 22,591 → 21,082 lines, and `ui/` (5,500 lines of TypeScript) is gone. Tests 1,626 → 1,575.
  Tracked files 1,214 → 299. A `--depth 1` clone: 22 MB → 8.3 MB on disk; its download 5.3 → 2.7 MB.
- Lane 0, before: `M app.py` ("sneaky" 3 times) and `?? README.md` in your checkout. After: `git status`
  is empty and the attempt waits on `graphene/readme`. Both in `docs/process/cut/before/` and `after/`.

**2. Run in five minutes** (its own tool dir): `UV_TOOL_DIR=/tmp/g UV_TOOL_BIN_DIR=/tmp/g/bin uv tool
  install 'git+https://github.com/Alex-lop/Graphene@cut'`, then `git show origin/cut:docs/process/cut/lane0.sh
  | PATH=/tmp/g/bin:$PATH bash`. Then `graphene --help`, and `graphene plan first` in /tmp/scratch: `auto`.

**3. The experiment** — `docs/test/PROVE.md`: 4 runs, about 20-60 min and $3-10 each (estimates).
  The rehearsal, no model: trip-all scores 5 traps, trip-none 0, both clocks set. I predict the
  paragraph ties or wins on traps and minutes (`docs/test/PREREG-statements.md`).

**4. Dogfood** — 22 min for a 14-node tree of lane 2. It caught what I missed: without the web UI,
  nothing filled the commits `node show` credits (fixed). Plan-first stopped helping at minute 11.

**5. Decide** (my default first). 1. The web UI: deleted; `git revert 659c89e` brings it back.
  `direction`: hidden. 2. `plan first`: `auto`. Under it the feeds paragraph became one leaf, not a
  tree, and was right. 3. Want back: the demo page, `docs/assets/plan.png`, Privacy's 2 dropped bullets?

**6. Broken or risky.** Store schema 5: the older `graphene` on your PATH refuses a store this branch
  opened. A Claude Code executor in a run worktree is fixed by tests only. Lane 4's rehearsal counted
  4 of 5 traps once in CI (1 of 24 jobs), never in 15 local runs; its failure now says why.

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
- **01:20** The visible surface and the help text merged: 21 commands hidden, every help string
  under a test, the root help 23 rows at 80 columns. README Privacy in two lines. CHANGELOG folded
  into one group. DIRECTION gained decisions 137-150. `docs/assets/plan.png` (the page) removed.
- **01:38** The dead-code sweep merged: two unreferenced names and three docstrings that named the page.
- **01:55** Final full suite at `6b96280`: 1,554 passed, 21 skipped. Ruff clean. The wheel installs in a
  fresh venv and `graphene demo --once` runs from it. Lane 0 on the final wheel: checkout clean. Lane 4's
  rehearsal on the final code: 5 and 0.
- **02:30** CI failed once on the PR (Ubuntu, 3.14): the trip-all tree rehearsal counted 4 traps. The same
  code passed all six jobs on the push before it. No local repro in 15 runs; the test now prints each
  run's traps and its `graphene run` output when it fails.

## Not done, or not verified

- No live Claude Code executor ran in a run worktree. The hook fix is proven by tests.
- `docs/test/wheel_smoke.sh` and the 21 Docker tests: Docker was down here. CI's Linux jobs run the tests.
- The experiment's wall time and spend are estimates. Tuning the task's size to 1-3 hours needs a live run.
- `last-with-ui` is a local tag on `66125f0`. Pushing it is yours: `git push origin last-with-ui`.

## Branches

- `cut`: this night, pushed. One PR into `main`. `main` is untouched at `4e5a2a9`.
- `process`: the orphan archive at `fb6a408`, pushed.
- `cut-l1`, `cut-l4`, `cut-ui`, `cut-process`, `cut-nemotron`, `cut-l5`, `cut-surface`, `cut-dead`:
  local only, each merged into `cut`. Delete them when the PR is merged.

Rollback: close the PR and `git push origin --delete cut process`. `main` never moved.
