# Night one: the truthful record and the first map (2026-09-19)

Branch `graph`, made from `origin/strategy` with `origin/main` merged in. Started 2026-09-18 23:38
-0400. Every number here came from a command run that night; where a number comes from a real
repo, only numbers, paths and ids are given.

## What was built

| Milestone | What | Proof |
| --- | --- | --- |
| N2.0 | Schema version 2 by additive migration: `agents`, `commits`, `commit_files`, `tool_events.cwd`. An older store is migrated in place by whoever opens it, the hook included; a store a newer Graphene wrote is refused in one line and left alone; only a file SQLite cannot read is moved aside. The migration forgets that transcripts were read, so the next command reads again those that still exist | `tests/test_store.py`: `test_an_older_store_is_migrated_in_place_and_keeps_its_sessions`, `test_migrating_makes_the_next_command_read_the_transcripts_again` |
| N0 | Distribution `graphene-map` 0.2.0, command `graphene`, import package unchanged. Cut: `--explain`, `--model`, `explain.py`, `--md`, `--full`. Hidden: `debrief`, `ingest`. `tests/test_words.py` | a wheel installed into a clean tool directory prints `graphene 0.2.0`; `graphene --help` lists `why`, `init`, `ui`, `sessions` |
| N1 | `graph.py`: the contract, with every position computed in Python. `tests/fixtures/make_run_fixture.py`: one synthetic run described once, from which both the transcripts and the rows a correct ingester must reach are derived, plus a real git repo with fixed SHAs | the golden `tests/fixtures/run_graph.json`; the no-jitter property over every prefix of the run, for one and two sessions; every mark and link has a grade and a record |
| N2-A | Subagent files read as units: `agents` filled from `meta.json`, the parent call, the `wf_` directory, the handback; `cwd` per event; worktree copies mapped to repo paths; sessions in a worktree found by identity; `SubagentStart` and `SubagentStop` hooks; the hook inside a linked worktree writes to the main repo's store | `tests/test_ingest_run.py` (18) |
| N2-B | `commits.py`: one git call per window over every ref, credit by the recorded call whose response names the SHA, cherry-picks tied to their origin, one change credited to one session | `tests/test_commits.py` (18) |
| N2-C | No `Read` responses stored; strings over 8 KB kept as first and last 4 KB; the hook's cost measured | `tests/test_hook_budget.py`: median 39 to 41 ms, p95 42 to 45 ms over six runs of twenty, budget 60 ms |
| N3 | `ui/` (Vite, React, TypeScript, d3-zoom, d3-selection), built page committed under `src/graphene_debrief/ui/static`, `server.py` on 127.0.0.1 with `Host` and `Origin` checks, `graphene ui`, `--export`. `export_html.py`, its template, `--html` and its tests deleted in the commit that proved the export | browser runs below; `tests/test_server.py`; `npm --prefix ui run check` (14 unit tests) |
| Integration | The round trip: transcripts on disk and a real git repo in, the golden graph out, byte for byte. `why` names the agent, its task and the grade, prints the file's own coverage, and says "changed in N commits during session X; no recorded write" when that is the case. Coverage on the card and in `sessions` | `tests/test_round_trip.py` (10) |

227 Python tests pass in 28 s; lint and format clean; `npm --prefix ui run check` green; the
committed page equals what the source builds.

## Acceptance on real data

Through the real CLI, on the live stores, after the documented one-time
`graphene ingest --backfill --replace` (needed only because an interim build of mine had migrated
these two stores before the new parser existed; a 0.1 store migrating to 0.2 re-reads by itself):

- **This repo, session `9e5f295d`.** `graphene --session 9e5f295d` prints
  `40 committed files · 40 traced to a recorded write (22 edit, 18 shell) · 0 only to an agent's commit · 0 to nothing`.
  That is the directive's dry run exactly. 29 commits on every ref in the window, 24 credited to a
  recorded call. `graphene why src/graphene_debrief/cli.py` names sessions `9e5f295d`, `9982bcf7`
  and tonight's. An independent throwaway script of mine, written before the product code existed,
  gave the same 40 = 22 + 18.
- **Nemisis, session `0dc016bf`.** Plain `graphene`, which printed "no file changes recorded" on
  2026-09-18, now opens that session:
  `86 committed files · 36 traced to a recorded write (36 edit, 0 shell) · 35 only to an agent's commit · 15 to nothing`.
  `graphene why` on the three files that answered nothing now answers: `crashcheck.py` 25 commits,
  1 traced to a write, 23 only to an agent's commit, 1 to nothing; `cli.py` and `report.py`
  "changed in N commits during session X ...; no recorded write".
- **The difference from the directive's dry run (86 = 48 + 12 + 26), with counts, nothing tuned.**
  The denominator is the same. Edit is 36, not 48: 9 of the 12 were edited only inside hand-made
  worktrees under the session's scratchpad (`wt-mcp`, `wt-map`, `wt-pin`, `wt-final`), since
  removed. No record gives their roots as a path: the agents' `cwd` was the repo root, `meta.json`
  has no `worktreePath`, git no longer lists them, and 16 of the 18 recorded `git worktree add`
  calls pass the path through a shell variable. Mapping them would be inference, so they stay
  unmapped; 3 of the 12 I could not explain. Commit-only and nothing moved as the credit rule was
  made right: 36/24/26 at first (40 commits credited); 36/47/3 once every line of a response was
  read (80); 36/35/15 once a call could no longer be credited with a commit that existed before it
  started (67).
- **Timings.** Backfill of the 28 sessions here 2.4 s, of Nemisis's 8 (7,810 calls in one) 3.1 s;
  commit sync 0.10 s and 0.34 s; `graphene sessions` with coverage for 21 sessions 0.48 s;
  `build_graph` on the 7,810-call, 467-agent session 0.75 s (was 5.8 s until each call was
  classified once instead of nine times).

## The page, looked at

At 1440x900, light and dark. On the synthetic run: 11 lanes, the six Workflow members hidden until
opened; coverage 12 / 9 / 2 / 1; the caption verbatim; `pyproject.toml` in the block of files that
trace to nothing; selecting the agent that worked in the worktree outside the repo shows its task,
what it was told, `/home/dev/wt/api`, `app/api.py` and `tests/test_api.py` as repo paths, commit
`2d04541`, "worktree copy" and its closing message; `app/util.py` and the closed `app/` row carry
the collision; 4 requests, all to the page's own origin; 0 console messages. The exported file
(351 KB) drew 11 lanes and 71 marks from inline data and fetched nothing.

On this repo's real session `9e5f295d` through `graphene ui`: the main agent and 16 agent lanes,
each labelled with its task; 29 commit marks; coverage 40 / 40 / 0 / 0; 4 failed checks, 4 rerun
green, 2 refused, 2 collisions; DOM ready in 79 ms with 912 marks. Selecting a real agent fills the
inspector with what it was asked, its worktree, 7 files each "a recorded edit, worktree copy" with
its record, 1 commit, 3 checks and what it said when it stopped. Screenshots are under
`.playwright-mcp/n3-final/` (git-ignored; they show real task text).

## What the reviewers found

Each of N2-A, N2-B and N3 was built by one sub-agent, attacked by a fresh one that reran the
done-test and had to reproduce whatever it reported, and fixed by a third. 33 findings; every
blocker and every "wrong" fixed with a test that fails without the fix.

- **N2-B.** A SHA at the start of a later output line was never read (`json.dumps` writes a
  newline as backslash-n and the letter kills the word boundary): over this repo's 18 busy
  sessions, credited commits went from 114 to 199 of 432. A merge contributed no paths, so the
  denominator was short (15 paths over 6 merges here). `credit_once` ranked by time before
  evidence.
- **N2-A.** A `worktreePath` in a `meta.json` was trusted without asking git, so a vendored
  clone's files could be filed as the repo's, contents included. The gone-directory rule admitted
  every path under a directory once one matched, and on this repo stored a write to
  `evidence/.../README.md` as a write to `README.md`.
- **N3.** `graph.marks` came out as two sorted runs (my sort key), so one zoom culled every repo
  mark; a step mark swallowed the click on 8 of 9 commit marks; the wrong `omitted` field was
  shown; selection painted the collision out; axis labels scrolled away; contrast under 4.5:1.
- **Found by the integrator on top.** The credit rule had no time guard: 13 of 80 credits in one
  real session and 5 of 29 in another went to a call that started after the commit existed (it
  only listed it). Collisions counted a worktree copy and the main copy as one file: 15, now 2, on
  the real session. A prose slash ("broad/high level") was read as a directory scope, the real
  cause of the false "not what you asked for" in the thesis. `graphene ui --no-open` printed its
  address into a buffer that emptied only when the server ended. On a long run the axis labels
  printed over each other.
- **The closing review (truth lens) and the two walkthroughs: 29 findings, 4 blockers.** The
  fixture graph was fully honest (all 71 marks and 43 links resolved to a record). On real data: a
  check mark drawn for a call in which no check ran (a commit message quoting a check, split at
  its newlines); both of the real session's collisions resting only on change lists the vendor
  marks `shared`, stated as fact; the card running its own `git log` without `--all` (25 commits
  where the map and git said 29), so a new user's first card said "Commits: 1" beside "no commits
  in the window"; `why` holding a commit in whichever window it fell in, so a file the card
  counted showed 0 commits. All four fixed at the root with tests through real ingestion
  (`tests/test_round_trip.py`), and seen afterwards in a browser: 0 collisions (was 2), 72 check
  marks none with prose in its label (was 73), span and duration equal on card, rail and header.
  Also fixed: a commit's time is git's, with the call's beside it; the inspector counts distinct
  files, agents and commits rather than links; the card lists files known only from Claude
  Code's shell lists and names the files behind its last two coverage counts.

## The finding of the night

Tonight's own session is poorly covered, and the cause is outside the code. Not one of the main
agent's shell calls carries Claude Code's list of the files it changed (0 of 174 at 01:16; the
session the night before carried 144; the strategist's session, on 2.1.277, carried 0). The
vendor's settings reference (https://code.claude.com/docs/en/settings-reference#basheditdiffenabled,
fetched 2026-09-19 01:17) says: with `bashEditDiffEnabled` unset, the lists are recorded in auto
and bypass mode only "when it directs Claude to edit files through Bash", and a `true` counts only
from user or managed settings. The key is absent from the user settings here. So a file written
with a heredoc or a script traces to a commit at best, and to nothing when the agent that
committed it never printed the SHA. `graphene init` now prints the one line a person has to add,
and the card says so when a window's shell calls carry no list.

## Budgets

Non-test Python is 5,279 lines against 4,700: 579 over. The directive estimated the additions at
about 1,350 lines; they came to about 2,150 (5,279 minus the 3,125 left after the cuts: `sources/claude_code.py` +342, `graph.py` 629,
`record.py` 218, `commits.py` 165, `server.py` 117, `store.py` +171, `why.py` +55, the rest in
`cli.py` and `debrief.py`), against cuts of 517. What could go: the old shell-command parser in
`attribute.py` (about 170 lines) once the vendor's lists are on for every session; the markdown
card that mirrors the terminal card (about 120); the scope heuristics behind "not what you asked
for" (about 100). None was cut tonight: each is used and covered by tests. TypeScript is 1,318 of
1,500 and CSS 266 of 450 (the night-two ceilings).

## Not verified, and not done

See `morning.md`, which is the list Alex reads.
