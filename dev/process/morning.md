# morning.md — 2026-10-07 — the meter

Rollback: `main` is untouched at `af3da2c`. To drop the night: close the PR, `git push origin --delete meter`.

## The brief

**1. Watch first:** `graphene demo tests/recordings/meter-claude.jsonl`: the feeds run on Claude Code, recorded
  at 02:30 on the final code, each leaf's live row climbing (screens at 80 and 120: `dev/process/meter/screens/`).
  Nemotron: `graphene demo tests/recordings/meter-nemotron-take-11.jsonl` (Ultra planned; Nano landed 2 of 4).
**2. The bill:** $36.17 of $50 at 02:45. `meter` $12.76 · `statements-practice` $7.01 · `nemotron-take` $6.69 ·
  `dogfood` $5.77 · `auto` $3.94. ($1.83 of the statements rows were written with no purpose.)
**3. `auto`:** Tuesday asks: 8 of 12 yours at once and done; 4 waited on a board item they put up.
  The feeds paragraph: a tree once in three; twice one leaf of 8 paths, no question, taken at once.
**4. Run in five minutes:** `uv tool install --force git+https://github.com/Alex-lop/Graphene@meter`, then in
  your repo `graphene init`, `graphene ask "…"`, `graphene watch` (`y`, then `R`), `graphene node show <leaf>`.
**5. The README:** 790 words. Least sure are yours: "which is exactly what I'd have checked first"; "the
  second number is the one I care about"; "because that's the whole game".
**6. Decide:** 1. Take 11 for the video? Default: no; none of 19 ran clean. 2. Run the registered arms? Default:
  not yet: a run lasts minutes, not hours, and the doubled task needs a commit named for them. 3. What should
  the meter show next? Default: the planner's dollars (the ledger holds its worst case).
**7. Broken or risky:** Codex's ChatGPT login is revoked: `codex logout && codex login` (Codex ran on Nemotron
  Super tonight). Most runs that stopped had a leaf whose check runs a file another leaf writes. CI's
  statements rehearsal fails 1 Ubuntu job in about 3 pushes, never locally; it now prints why.

---

## The dogfood bill

Graphene wrote its own `docs/HOW_IT_WORKS.md` with plan first on and the meter on itself: 7 acts of mine
(~4 min), 8 agent-minutes, $4.27, plus the planner's $1.50 worst case. One leaf came back once (its check
had no `.venv` in the run's worktree) and landed after `node set --check`. Lanes 1 and 2 were built by
sub-agents outside Graphene. `dev/process/meter/dogfood.md`.

## Branches

- `main`: `af3da2c`, untouched, local and on GitHub.
- `meter`: the night, pushed; the PR is the only one. 67 commits, 39 on its first-parent line.
- In this run's clone only, all merged into `meter`: `meter-core`, `meter-l1`, `meter-l1b`, `meter-move`,
  `meter-record`, `meter-run`, `meter-size`, `meter-watch`, `dogfood`.

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
  on the cut night; never here (3 rehearsals, the trip-all suite 40 times, 6 rehearsals in Linux containers).
  The test now runs a came-back leaf's check again and prints what it said.
- **02:05** The brief's five minutes, from GitHub `@meter`: install, init, ask (two board questions, so it
  waited), accept, run (`run: 1 done · agents <1 min, $0.2359`), node show. `dev/process/meter/five-minutes.md`.
- **02:25** A replay drew no meter strip: Graphene's own recording predates the meter. Turned on, the strip
  said "no meter" before a leaf's first turn and "-2706 s ago", and `.` stalled at change 31 of 63. All
  three fixed at the root; the Claude Code recording made again at 02:30 on the final code ($0.3230).
- **02:00-03:00** Takes 9 to 21: Ultra planned a tree in 4 of 11; take 11 replaces take 6. Each stopped where a leaf's check or code
  needed a file another leaf writes. `nemotron.sh` now widens and runs again up to three times.
