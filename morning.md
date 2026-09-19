# morning.md — 2026-09-19 — night 1 of 3

## 30-second version
- main: untouched when this was committed; this line is rewritten once the gate's CI finishes
- What you can open right now: `cd ~/Desktop/AllThingsAgenticHackathon && graphene ui --session 9e5f295d`
- Coverage on last night's own session: 87 committed files · 33 traced to a recorded write ·
  30 only to an agent's commit · 24 to nothing. **Poor, and the finding of the night:** not one of
  its 1,100 shell calls carries Claude Code's list of changed files (the night before: 144 did).
  With `bashEditDiffEnabled` unset the vendor records that list only when it routes edits through
  Bash, and I write through heredocs and scripts. Step 1 below fixes every future run.
- Publishable today: no — blocked on: night two (README for a stranger, the recording), then your
  PyPI publisher and the tag.
- Biggest risk: the record leans on a vendor list that is "best effort and in public beta" and is
  off by default for a session like mine. Without it the honest map is mostly "commit only".
- Budgets: Python 5,279/4,700 — **over by 579**. I would cut the old shell-command parser in
  `attribute.py` (~170, once step 1 is the norm), the markdown card that mirrors the terminal one
  (~120) and the scope heuristics behind "not what you asked for" (~100). I cut none: each is used
  and tested. TypeScript 1,318/1,500, CSS 266/450.
- Next night starts at: L1 (live). Night one's plan is finished; its gate result is on line one.

## Do these today (in order, minutes in brackets)
1. [1] `~/.claude/settings.json`: add `"bashEditDiffEnabled": true`. Only user settings can turn it
   on and I may not edit that file. `graphene init` prints this line too. (`cleanupPeriodDays` is
   already there.)
2. [10] (after night two) THE KILL CRITERION. Run `graphene ui` on a real run of yours. Answer the
   five come-back questions once with the map and once with `graphene`, `graphene why` and
   `git log`, and time each. Then fill in this line, which night three reads:
   KILL CRITERION: map won / map lost — <n> of 5 faster with the map — <one sentence>
3. [5] PyPI: add a pending trusted publisher: project graphene-map, owner Alex-lop, repo Graphene,
   workflow release.yml, environment pypi
4. [1] (after night two's gate) git tag v0.2.0 && git push origin v0.2.0 — then watch Actions → release
5. [10] (after night two) Post the recording; turn on GitHub Pages for docs/demo if you want it
6. [2] Look at your own night: open `local/maps/2026-09-19-night-one.html` (git-ignored, 1.2 MB).

## What changed
- Store: schema 2 by additive migration (agents, commits, commit_files, cwd); an older store is
  migrated in place and re-read, a newer one refused in one line, nothing dropped — `tests/test_store.py`
- N0: `graphene-map` 0.2.0; `--explain`, `--model`, `--md`, `--full`, `--html` gone; `debrief`,
  `ingest` hidden; banned-word test — wheel in a clean tool dir prints `graphene 0.2.0`
- The contract: `graph.py`, every position from Python; golden graph; no mark, lane, row or tick
  moves over every prefix of the run — `tests/test_graph.py` (15)
- The record: agents with task, parent, worktree, closing message; worktree copies mapped; sessions
  in a worktree found; hooks for subagent start and stop; commits credited by record; one change,
  one session — `tests/test_ingest_run.py` (18), `tests/test_commits.py` (18)
- The round trip: transcripts and a real git repo in, the golden graph out, byte for byte; and the
  card, `why` and the map agree with each other — `tests/test_round_trip.py` (10)
- Acceptance, real CLI, live store: `graphene --session 9e5f295d` →
  `40 committed files · 40 traced to a recorded write (22 edit, 18 shell) · 0 · 0` (the directive's
  number); `graphene why src/graphene_debrief/cli.py` names `9e5f295d`
- Nemisis: plain `graphene` (blank on 09-18) → `0dc016bf`, `86 · 36 (36 edit) · 35 · 15`. The dry run
  said 48/12/26; the report explains the 12 with counts (9 are hand-made scratchpad worktrees whose
  roots no record gives as a path; 3 unexplained). Nothing was tuned.
- The map: `graphene ui`, `--export`; seen by me in a browser at 1440x900, light and dark, on the
  synthetic run and on `9e5f295d` (17 lanes, 29 commits, inspector on a real agent) — screenshots
  under `.playwright-mcp/n3-final/`
- Card, `sessions`, `why`: coverage everywhere, local time with offset, latest session that did
  something (the one that finished last), five commits, agent + task + grade in `why`, honest
  answers for a file with no recorded write — `graphene sessions` 0.48 s on your 75 MB store
- Hook: median 39–41 ms, p95 42–45 ms (budget 60) — `uv run pytest -q -s tests/test_hook_budget.py`
- `graphene init` here: added SubagentStart, SubagentStop to `.claude/settings.json` in place
- The false "not what you asked for" is fixed at its cause (the prose "broad/high" was read as a
  directory; the prompt never named the file): Nemisis `0dc016bf` 1 → 0
- Reviews: 33 findings on N2-A/N2-B/N3, then 29 in the closing truth review and walkthroughs; all
  7 blockers fixed with failing-first tests (report: `docs/reports/2026-09-19-record-and-map.md`)

## Not verified / not done
- Walkthroughs, fresh HOME, built wheel, README followed literally. With no transcripts: no
  blocker (one-sentence empty state that says where it looked; nothing written that should not
  be; hook exits 0 and prints nothing). With synthetic transcripts: first pass found 2 blockers
  (a first card that contradicted itself; `why` saying 0 commits for a file the card counted), both
  fixed; a second, fresh agent with a rebuilt wheel: **no blocker**, install to first card about
  1 s, every number reconciled with git by hand. Its leftovers, not fixed: a card over several
  sessions sums a create and a later edit into one row (`created +6/−1`); the card does not
  mention a collision the map counts; the README's "what I never asked for" shows nothing when
  the prompt names no path and the card does not say why; backgrounded without a terminal,
  `graphene ui` stops on TERM, not INT.
- Not verified: the map in any browser but the Playwright Chromium; `graphene ui` opening a browser
  by itself (I always ran `--no-open`); Linux beyond CI; a store larger than Nemisis's.
- Not done, stated: no keyboard navigation of the map; 11 lanes + 13 rows do not fit 1280x800
  without scrolling; `--with-diffs` (the graph carries no hunks at all, so there is nothing to
  gate); "abandoned" (reverted files) is on the card but not a counter on the map; the rail shows
  calls, agents and files edited per run, not coverage per run.
- Known limits, not loosened: a commit whose SHA the agent never printed is credited to nobody
  (24 of tonight's 87 files are that: sub-agents that committed quietly); a cherry-pick by branch
  name has no origin on record (4 in `9e5f295d`); a 7-digit all-decimal SHA prefix can match a
  number in output; `git log --since` can skip an in-window commit under older descendants; a
  cherry-pick shows its origin's grade; the old shell-command parser does not know worktrees, so
  the card lists 2 of tonight's worktree files under "outside the repo"; a never-committed,
  since-deleted subdirectory holding a file named like a repo path is still re-rooted.
- Left over on this machine: about 25 worktrees under `.claude/worktrees/` and the sub-agents'
  local branches (`n0-ground`, `n1-fixture`, `n2*`, `n3-map*`, `trial-integration`), all merged or
  superseded. I did not delete them: `git worktree prune` and `git branch -d` are yours to run.

## Decisions to check
1. Root command has `--session`, `--since`, `--json` because `debrief` is hidden.
2. A file SQLite cannot read is still moved aside; older stores migrate in place; newer refused.
3. `agents` also stores the prompt (capped) and the worktree root: `meta.json` really carries
   `worktreePath`, a better record than `cwd`.
4. Worktrees are recognised from git's own files (`.git` → `gitdir` → `commondir`), not from
   `git worktree list`: same facts, no subprocess, usable on the hook path.
5. The fixture is a sibling module (`make_run_fixture.py`); it has a second session in the outside
   worktree's own project folder, because on this machine a worktree subagent's transcript sits in
   its PARENT's project folder, never its own. That second session also serves night two.
6. Grades: law 8's five for files; `record` for a mark or link that is itself a recorded call;
   `why` alone has a third word for a write, "read from the recorded command" (old sessions).
7. y is relative to its region (lanes, rows), or a new lane would push every repo row down.
   Opening a group adds numbers Python gave (`dy`, `extra`); the page decides no order or size.
8. Evidence is graded per (commit, path) from records up to that commit, so a mark never changes
   later; coverage counts each path once under its best grade.
9. The run's commits exclude commits another, unselected session is recorded making.
10. Collision = a second agent wrote the file in the SAME checkout before the first stopped, or
    within ten minutes of its last write; a list the vendor marks `shared` never counts. The rule
    is printed on the page. Real session: 15 → 2 → 0 as each of those was made true.
11. Credit needs the commit not to exist when the call started (one second's grace): naming a
    commit in `git log --oneline -3` is not making it. 13 of 80 and 5 of 29 credits were that.
12. Latest session = the one that finished last, not started last.
13. An exit code of 1 for "nothing recorded yet" is kept (scripts can tell); `why` exits 0 whenever
    it has an answer, including "changed in N commits; no recorded write".
14. `why` for a file no session touched asks git for its last commit (a read-only `git log`).
15. Playwright is not an npm dependency; browser acceptance ran through the browser tool.
16. `@vitejs/plugin-react` is the one dev dependency beyond the directive's list (Vite tooling).
17. I ran `graphene ingest --backfill --replace` here and in Nemisis once, because my interim build
    had migrated both stores before the new parser existed; copies of the old stores are in the
    session scratchpad. A 0.1 store upgrading to 0.2 re-reads by itself.
- Disagreement with the thesis, noted as the directive asks: the thesis says shell change lists
  are "recorded in auto and bypass modes by default". The vendor's reference says: only "when it
  directs Claude to edit files through Bash". On 2.1.277/278 here, in auto mode, none were recorded.

## Rollback
git checkout main && git reset --hard 165343b && git push --force origin main

## Last night's session, as Graphene sees it
```
# Graphene

**Session cef392c4** · 2026-09-18 23:36 → 2026-09-19 02:23 -0400 · 2h 47m · 1 prompt · 43 files written (+9939/−680)  
**Commits during the session:** 50
- a7a9195 second walkthrough (no blocker): why's clock, the list that stopped at five, and words that meant two things
- 7a07c5f ui: the outside and collision chips carry their rule as a tooltip
- 5dde638 closing review, part two: a shared list proves no writer, and the page counts what it says it counts
- e6c7773 closing review, part one: a check is a command, one commit list, and why never contradicts itself
- 07ce007 ingest, commits: four minors the first reviews left open
- … 45 more; `git log` has them all

**Coverage:** 87 committed files · 33 traced to a recorded write (33 edit, 0 shell) · 30 only to an agent's commit · 24 to nothing (24 committed in the window by no identifiable agent)
- only in an agent's commit: `.github/workflows/ci.yml`, `.gitignore`, `docs/assets/replay_fixture.py`, `pyproject.toml`, `src/graphene_debrief/__init__.py` … 25 more; `graphene ui` lists them all
- traced to nothing: `tests/conftest.py`, `tests/fixtures/run/-home-dev-project/22222222-3333-4444-8555-666666666666.jsonl`, `tests/fixtures/run/-home-dev-project/22222222-3333-4444-8555-666666666666/subagents/agent-6a7b8c9daebfc0d7.jsonl`, `tests/fixtures/run/-home-dev-project/22222222-3333-4444-8555-666666666666/subagents/agent-6a7b8c9daebfc0d7.meta.json`, `tests/fixtures/run/-home-dev-project/22222222-3333-4444-8555-666666666666/subagents/agent-7a8b9cadbecfd0e8.jsonl` … 19 more; `graphene ui` lists them all

**Files changed**
- `tests/fixtures/run_graph.json` created +2354/−0
- `tests/fixtures/make_run_fixture.py` created +1494/−0
- `src/graphene_debrief/graph.py` created +648/−0
- `src/graphene_debrief/sources/claude_code.py` modified +421/−79
- `src/graphene_debrief/debrief.py` modified +211/−214
- `tests/test_ingest_run.py` created +403/−0
- `ui/src/Map.tsx` created +363/−0
- `tests/test_commits.py` created +336/−0
- `tests/test_graph.py` created +300/−0
- `ui/src/app.css` created +266/−0
- `ui/src/model.ts` created +257/−0
- `ui/src/Inspector.tsx` created +253/−0
- `src/graphene_debrief/cli.py` modified +160/−84
- `src/graphene_debrief/store.py` modified +211/−33
- `tests/test_run_fixture.py` created +236/−0
- `morning.md` modified +116/−115
- `src/graphene_debrief/record.py` created +218/−0
- `tests/test_store.py` modified +180/−15
- `src/graphene_debrief/commits.py` created +186/−0
- `ui/src/Chrome.tsx` created +177/−0
- `ui/src/model.test.ts` created +134/−0
- `src/graphene_debrief/why.py` modified +113/−15
- `docs/reports/2026-09-19-record-and-map.md` created +126/−0
- `src/graphene_debrief/attribute.py` modified +96/−17
- `src/graphene_debrief/server.py` created +109/−0
- `tests/test_server.py` created +97/−0
- `ui/src/App.tsx` created +84/−0
- `tests/test_cli.py` modified +34/−46
- `tests/test_hook_budget.py` created +78/−0
- `docs/HOW_IT_WORKS.md` modified +28/−44
- … 13 more; `graphene why <path>` for any of them

**Abandoned**
- check `uv run pytest tests/test_words.py -q` failed and was rerun under prompt 1: passed
- check `uv run pytest -q` failed and was rerun under prompt 1: passed
- check `uv run ruff check` failed and was rerun under prompt 1: passed
- check `uv run ruff format src tests -q` failed and was rerun under prompt 1: passed
- 77 tool failures (57 Bash, 6 mcp__plugin_playwright_playwright__browser_navigate, 5 mcp__plugin_playwright_playwright__browser_resize, 4 Read, 3 StructuredOutput, 2 mcp__plugin_playwright_playwright__browser_click)

**Written outside the repo:** `/Users/alexlopez/Desktop/AllThingsAgenticHackathon/.claude/worktrees/wf_4329c035-518-3/ui/src/ (2 files)`, `/private/tmp/claude-501/-Users-alexlopez-Desktop-AllThingsAgenticHackathon/cef392c4-3c12-4968-b67f-a7d2f630ca68/scratchpad/ (102 files)`, `/tmp/a.txt`, `/tmp/b.txt`, `/tmp/cc.bak`, `/tmp/cc_backup.py`, `/tmp/claude-501/ (2 files)`

_Note: none of this window's 1100 shell calls carries Claude Code's list of the files it changed, so a file written through the shell traces to a commit at best; `graphene init` says how to turn the lists on_

Ask `graphene why <path>` for who changed a file and why, or `graphene why <path>:<line>` for one line.
```

The exported map: `local/maps/2026-09-19-night-one.html` (git-ignored; 50 commits at 02:23).

## Questions (at most 3, only ones that block the next step)
1. None blocks night two. One for your ten minutes in step 2: if the map loses, night three
   becomes "the card carries everything"; if it wins, do you want rules (R1–R3) before Codex (C1),
   or both tracks at once as written?
