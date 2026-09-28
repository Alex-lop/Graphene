# morning.md — 2026-09-28 — the shaping directive

## The brief

**Do first**
1. (10 s) Remove a fake key a test left in your keychain: `security delete-generic-password -s graphene -a token-factory`
2. (2 min) The key in `~/.zshenv`: `export NEBIUS_API_KEY=… NEBIUS_PROJECT_ID=…`, then a new shell.
3. (10 min) In a terminal of your own, not Claude Code: `docs/test/practice.sh`, rungs 1-3 (`docs/test/PRACTICE.md`).

**New tonight**
- The planner asks, you answer with a key: `graphene board` (rows under the goal in `graphene watch`)
- The plan as a tree and a graph of what waits: `graphene plan --view dag` (Tab in `watch`)
- Settings you state once: `graphene config`, `graphene key check`
- Talking on the tree: `?` on a node in `graphene watch`; `graphene plan changes`
- Ready for the key: `docs/test/practice.sh --dry` climbs all seven rungs on stand-ins (3 min)

**Decide**
- Keep the board on by default though it cost more attention than the outline? Default: yes (DIRECTION 98-99).
- Run the full study (with executors) inside the live run, `graphene run` starting them? Default: yes.
- Re-asking with `+`/`-` moves your answers about dropped leaves to the whole plan. Default: keep.

**Broken or risky**
- The board does not yet save attention: about twice the modelled seconds (study 2), less with 1-2 items (study 3).
- CI fails now and then on the last run's stop-timing tests (see "The closing review" below).
- The keychain item in step 1. Every test now runs with the keychain off.

---

(Everything below the brief: what was decided, the evidence, the screens, the state of every branch.
The winning run's morning is `morning-2026-09-26.md`.)

## What was decided, and why

Every decision is in `docs/DIRECTION.md`, 81 to 99, each with its evidence. Read 84, 98 and 99 first.

- **81-84, the board.** The planner puts up questions (each with the default it would assume),
  options, risks and what it would leave out, before the tree; you answer each with one key (`y`
  take, `1`..`9` pick, `d` drop, `p` park, Enter your words). An answer reaches the executors as a
  `decided:` line, and an option's `then:` lines change the tree (scope, check, goal, drop, a leaf, a
  condition) as your edit, undone by `u`. On the screen it is rows of the outline under the goal. Two
  screens were built and tried by three stand-ins; they tied, and rows won the tie
  (`docs/process/shaping/evaluation.md`).
- **85-87, the views.** Tab cycles the outline, a top-down tree and a left-to-right graph of `needs`
  with the critical path; `auto` picks one only where it shows more than the outline. The outline
  stays the default: in the trials it answered most questions on the first screen.
- **88, talking on the tree.** `?` on a node: why, split, merge, another way, answered by the planner
  onto the board; `+`/`~` mark what someone else changed since you pressed `m`.
- **89-92, settings you state once.** Keys (environment, then the keychain, never a file; person
  only), standing conditions (protected, read-only, never propose; held at propose, edit, start,
  every write and done), plan size (`+`/`-` re-ask finer or coarser), one text form in `graphene
  config`. No keymap setting: nobody needs one yet.
- **93, the ladder.** Seven rungs, each with its cap, PASS or FAIL, the bill and the next command.
- **94, Nemotron while you shape.** Twenty ideas ranked (`docs/process/ideas.md`); three prototypes
  (cover, note, precheck) behind `GRAPHENE_SHAPE`, each also a command, run only against the stand-in.
- **95-99, how the night ran and what the evidence says.** Lane B went through Graphene itself
  (`docs/process/shaping/as-the-person.md`: ten leaves in 29 minutes, and the planner's questions
  scrolling away as prose were the board's case); the keychain incident; the pinned study build; the
  board's cost; prompt version 4.

## The evidence

- **The suite:** 1288 passed, 2 skipped, locally at `1770539` (the full suite, 18 min). ruff clean;
  the page's build equals its committed assets.
- **The evaluation:** 12 board trials and 3 graph trials by three stand-ins in a logged tmux seat, at
  80x24 and 120x36, on feeds, tonight's plan and the thirty-leaf plan (`evaluation.md`, `screens/`).
- **The shaping studies** (`docs/test/results-2026-09-28-shaping.md`, each registered before its
  runs): study 1 never ran (the classifier); study 2, shaping only, eight runs; study 3, exploratory.
- **The live pre-registration** (`docs/test/results-2026-09-28-live-prereg.md`), the sealed
  paragraphs, arm A's harness, the B′ harness, and `docs/test/evidence.py` for the table and chart.
- **The next run's directive, a draft for you to edit:** `docs/process/directives/LIVE_DIRECTIVE_DRAFT.md`.
- **Screens** before and after every changed view: `docs/process/shaping/screens/{before,after}/`.
- **Not verified:** anything on Token Factory or in a Sandbox (no key tonight); the board on a real
  person; the prototypes' cost and use live.

## The closing review

Five adversaries (the board, the views, settings and keys, the ladder, the claims) went over
`cb2ce54..2111115`, each finding reproduced from scratch by a skeptic before any fix: 48 findings,
45 confirmed, 3 refuted. Six were blockers, all fixed with a test each (DIRECTION 100): a re-ask that
lost the tree when the planner failed, a re-ask that took a split's proposals with it, a crash on a
joined emoji, a shell write to a git-ignored protected path that nothing saw, a key echoed back in a
Token Factory error, and `HACKATHON.md` hiding the studies' result. Before it, three walkers of the
whole path filed 72 rough edges (`docs/process/shaping/walks.md`); 18 were fixed and 3 in part (lane F).

## State of every branch

- **`shaping`:** this run, pushed; draft PR #31.
- **Merged into `shaping`** and kept (`git branch -d` drops them): every lane, fix and study branch
  tonight (`lane-*`, `integ`, `a-final*`, `f-*`, `g-*`, `study3`, `scribe`, `cover-fix`, `note-fix`,
  `precheck-fix`, `worktree-*`), and `lane-b` from `~/graphene-night`.
- **Not merged, deleted by decision 84:** `lane-a-board-view` (its screens stay in `screens/view-*`).
- **`main` (GitHub):** `cb2ce54`, untouched. Local `main`: behind, untouched.
- **Outside the repo:** `~/graphene-night` (lane B's run), `~/graphene-shaping-runs`,
  `~/graphene-shaping3-runs` and their venvs (the studies' run directories, which hold the cards'
  briefs: do not publish them).

## Rollback

Before the first change, `main` on GitHub was `cb2ce54` (your merge of PR #30). This run is the
branch `shaping`, cut from there; nothing touches `main`.

```
git checkout main && git reset --hard cb2ce54
```
