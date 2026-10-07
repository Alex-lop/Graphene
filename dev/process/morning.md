# morning.md — 2026-10-07 — the meter

Rollback: `main` is untouched at `af3da2c`. To drop the night: close the PR, `git push origin --delete meter`.

## The brief

**1. Watch first:** `graphene demo tests/recordings/meter-claude.jsonl`: the feeds run on Claude Code, each leaf's
  live row climbing; the live screen at 80 columns is `dev/process/meter/screens/claude-80.txt`.
  Nemotron: `graphene demo tests/recordings/meter-nemotron-take-11.jsonl` (Ultra planned; Nano landed 2 of 4).
**2. The bill:** $41.22 of $50, final. `meter` $17.28 · `nemotron-take` $7.22 · `statements-practice` $7.01 ·
  `dogfood` $5.77 · `auto` $3.94. $15.00 of it is planners held at their worst case: they report no cost.
**3. `auto`:** Tuesday asks: 8 of 12 yours at once and done; 4 waited on a board item they put up.
  The feeds paragraph: a tree once in three; twice one leaf of 8 paths, no question, taken at once.
  Transcripts, both kinds, every run: `dev/process/meter/auto-evidence.md`.
**4. Run in five minutes:** `uv tool install --force git+https://github.com/Alex-lop/Graphene@meter`, then in
  your repo `graphene init`, `graphene ask "…"`, `graphene watch` (`y`, then `R`), `graphene node show <leaf>`.
  Run as written from GitHub at 02:05: `dev/process/meter/five-minutes.md`.
**5. The README:** 790 words. Least sure are yours: "which is exactly what I'd have checked first"; "the
  second number is the one I care about"; "because that's the whole game".
**6. Decide:** 1. Take 11 for the video? Default: no; none of 19 ran clean. 2. Run the registered arms? Default:
  not yet: a run lasts minutes, not hours, and the doubled task needs a commit named for them. 3. What should
  the meter show next? Default: the planner's dollars (the ledger holds its worst case).
**7. Broken or risky:** Codex's ChatGPT login is revoked: `codex logout && codex login` (Codex ran on Nemotron
  Super tonight). Most runs that stopped had a leaf whose check runs a file another leaf writes. CI's
  statements rehearsal failed 1 Ubuntu job on 2 of 13 runs, never here; it now prints why when it does.

---

The decisions taken tonight are in `dev/DIRECTION.md`, 151 to 165. Every review finding, fixed or left:
`dev/process/meter/review.md`.

## Verified before the PR, the directive's list

1. The suite on the CI matrix (Ubuntu and macOS, Python 3.12 to 3.14): 6 of 6 jobs green on the final code
   (`5a8c091`); of the night's 13 runs, 2 lost one Ubuntu job each to the statements rehearsal. `ruff check` clean;
   `uv build`; the wheel installed outside the source tree runs `graphene demo --once`.
2. Lane 1's transcripts, both kinds, every run: `dev/process/meter/auto-evidence.md`.
3. Lane 2's screens at 80 and 120 on Claude Code, Codex and Nemotron, the bill lines, each beside its ledger rows:
   `dev/process/meter/meter-evidence.md`. Again on the final code at 05:27: Claude $0.4582, ledger $0.4582.
4. The cut's lane 0 still leaves the checkout clean, on the wheel of 05:27 (`722f71a`): `dev/process/meter/lane0.txt`.
5. The README is 790 words, and every command in it ran tonight.
6. The suite is green after the move. The grep for the old paths finds only links into the `process` branch, the
   two pre-registered records (decision 163) and the directives' own words.
7. The ledger is under $50, by purpose in the brief.

## The dogfood bill

Graphene wrote its own `docs/HOW_IT_WORKS.md` with plan first on and the meter on itself: 7 acts of mine
(~4 min), 8 agent-minutes, $4.27, plus the planner's $1.50 worst case. One leaf came back once (its check
had no `.venv` in the run's worktree) and landed after `node set --check`. Lanes 1 and 2 were built by
sub-agents outside Graphene. `dev/process/meter/dogfood.md`.

## Branches

- `main`: `af3da2c`, untouched, local and on GitHub. Rollback: close PR #40.
- `meter`: the night, pushed; PR #40 is the only one. 120 commits, 71 on its first-parent line, more than the
  30 to 50 you like; the directive rules out a force-push, so a reshape is yours to ask for.
- In this run's clone only, all merged into `meter`: `meter-core`, `meter-l1`, `meter-l1b`, `meter-move`,
  `meter-record`, `meter-run`, `meter-size`, `meter-watch`, `dogfood`, and the reviews' `meter-fix-ledger`,
  `meter-fix-screens`, `meter-fix-edges`, `meter-fix-ledger2`, `meter-fix-codexpath`, `meter-fix-toolcall`.

## What was done, in order

- **23:26** Read the directive. Branch `meter` from origin/main `af3da2c`, in a clone outside your checkout.
  The directive is committed at `dev/process/directives/METER_DIRECTIVE.md`.
- **23:40** The night's ledger: $50 cap, nothing new past $45, a purpose on every row. The session was not
  started with `GRAPHENE_AGENT_LIVE_USD`; the directive's $50 line is the opening, so this run sets it to 50
  for its own live commands.
- **23:45** Real stream shapes, live: Claude Code 2.1.292 `stream-json` (Sonnet 5.5, 4 turns, $0.0623) and
  `codex exec --json` 0.151.0 (Nemotron Super on Token Factory, $0.0150).
- **00:03** The statements check: one tree-arm planning session put "half-even" and "vendor/" in the plan's
  goal and three conflicts on the board as plan-wide items, so all four conditions reached every leaf's
  contract. Nothing was changed. `dev/process/meter/standing-check.md`.
- **00:18** Lane 1 merged: under `auto` every ask is proposed; one leaf with no board item and at most 8
  paths is yours at once.
- **00:20** Live, the old node count made a leaf in a sub-goal of its own wait. Fixed: the rule counts
  leaves (`c0d8379`). Three more rounds ran on the fix.
- **00:25** The move: `docs/` keeps what you need to use Graphene, `dev/` holds how it gets built.
- **00:30** `meter` pushed for CI.
- **00:31** Statements practice 1, at the registered size: planned in 2.5 min, ran 9.5 min, 0 traps, 19/24
  and 8/12. Two hand-backs, both real conflicts. The task is about 8 times short of its 1-3 hours.
- **00:58** The meter merged: run reads each executor's stream; watch has a live row per leaf and two
  clocks; node show has each attempt; Nemotron writes a row per call.
- **01:04** Live, Claude Code: `run: 3 done · agents 2 min, $0.4560 at list price`; Claude Code's own report
  and the ledger both say $0.456. Codex on Nemotron Super: $0.3669, ledger $0.3669. Nemotron: $0.2258,
  ledger $0.2258.
- **01:10** The dogfood: Graphene wrote its own HOW_IT_WORKS (2,849 words) with plan first on: 7 acts of
  mine, 8 agent-minutes, $4.27. `dev/process/meter/dogfood.md`.
- **01:12** Fixed what the runs showed: Claude's output tokens settle at its result; Nemotron's per-call
  rows broke arm A; Ultra's `<tool_call>` text was read as its answer, so the planner proposed nothing.
- **01:15** The statements task at twice the size (2,658 lines, eight subsystems).
- **01:17** Practice 2: the planner kept the new code out with a board default; it stopped at 3 of 7 leaves
  on a test file another leaf owned.
- **01:00-01:40** Eight Nemotron takes. Ultra planned a tree in 3; take 6 was the best. `dev/process/meter/takes.md`.
- **01:35** Practice 3 asked for every report per currency: 6 leaves in 4 minutes, the biggest 16 files in
  2. Size does not set a run's length. `dev/process/meter/statements-practice.md`.
- **01:40** A recording hid your home directory as a path but not as Claude Code spells it, with dashes.
  Fixed, and `meter-claude.jsonl` hidden again: the leak check counts nothing.
- **01:42** The full suite: 1,589 passed in parallel; the 11 width tests that fail only in parallel pass alone.
- **01:55** The README gets the run's `git log --graph`, as the directive's shape has it.
- **02:00** PR #40 opened. CI: the statements rehearsal failed 1 Ubuntu job on two pushes running, as once
  on the cut night. Never here: 3 rehearsals, the trip-all suite 40 times, and in Linux containers 6
  rehearsals and the whole suite twice (Python 3.13 and 3.14, 1,602 passed each). The test now runs a
  came-back leaf's check again and prints what it said, so the next failure says why.
- **02:05** The brief's five minutes, from GitHub `@meter`: install, init, ask (two board questions, so it
  waited), accept, run (`run: 1 done · agents <1 min, $0.2359`), node show. `dev/process/meter/five-minutes.md`.
- **02:25** A replay drew no meter strip: Graphene's own recording predates the meter. Turned on, the strip
  said "no meter" before a leaf's first turn and "-2706 s ago", and `.` stalled at change 31 of 63. All
  three fixed at the root; the Claude Code recording made again at 02:30 on the code of that hour ($0.3230).
- **02:00-03:00** Takes 9 to 21: Ultra planned a tree in 4 of 11; take 11 replaces take 6. Each tree stopped
  where a leaf's check or code needed a file another leaf writes. `nemotron.sh` now widens and runs again up
  to three times, as a person pressing `w` again would.
- **02:50** On a wheel of that hour: the cut's lane 0 still leaves the checkout clean (`dev/process/meter/lane0.txt`,
  unchanged), and the wheel installed outside the source tree runs `graphene demo --once`.
- **03:00-04:15** A review of the whole branch: four readers, a skeptic each for the top six, 19 distinct
  findings, none refuted. 17 fixed, each with a test that fails without its fix; the worst two were the
  ledger's: a stopped attempt settled its hold at $0, and a run killed outright left its holds in flight all
  night. The 2 left, and why: `dev/process/meter/review.md`. A resumed result's `usage` was checked live first.
- **04:30-05:20** A second review, of the fixes themselves: 7 findings, none refuted, all fixed. Two were
  regressions of the dead-run fix, caught before they shipped: a dead run's hold was settled into the next
  night's ledger, and an orphaned executor that had already finished escaped the sweep.
- **05:27** On the final meter code (`722f71a`; after it only the auto rule changed): live, Claude's bill line,
  its ledger rows and its own report all say $0.4582; lane 0 leaves the checkout clean; the wheel replays
  `graphene demo --once`.
- **05:30-06:00** A third review, of the second round's fixes: one finding refuted, one fixed. One leaf whose new
  question reused a settled item's [id] was taken at once, its question never on the board; it waits now.
