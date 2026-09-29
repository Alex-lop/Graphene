# morning.md — 2026-09-29 — the first-light directive

## The brief

**Watch first**
- No rough cut: its takes are live, and nothing live ran (below). The same cut on the stand-ins, REHEARSAL on every frame: `open ~/graphene-first-light/rehearsal.mp4` (2 min 26 s; subtitles: View > Subtitles).

**What ran live** — $0.0029 of $10, all yours (12 ledger rows: three access checks and one leaf)
- Rung 1 PASS 01:14, rung 2 PASS 01:16: Graphene has made a runtime call to Token Factory. Sandboxes answered 403 (ForbiddenError).
- Rungs 3-7: not run. `GRAPHENE_AGENT_LIVE_USD` was not in this session's environment, so I ran nothing live; your commands are under "Your commands".

**New tonight**
- An agent practises live only in a session you start with `GRAPHENE_AGENT_LIVE_USD` set, on one locked night's bill: `docs/test/practice.sh night`
- The board asks only while a question is open, and accepting takes every default (`board: auto` by study 4): `graphene board`
- The direction: Graphene's goals above its plans, sessions hung from them: `graphene direction` (`D` in watch)
- A closed terminal now ends `watch`, `demo` and a run's executors and checks: `tests/test_teardown.py`
- The video, filmed scene by scene and refused unless the run was live: `docs/demo/build.sh --rehearsal`

**Decide**
- The branch has 110 commits; reshape it to about 40 before you merge (a force-push, backup branch first)? Default: yes, on your word.
- Rungs 3-7 by an agent: start Claude Code from a shell with `export GRAPHENE_AGENT_LIVE_USD=10` once Sandboxes let the project in? Default: yes.
- In the registered runs a stand-in's `as_me` drops Claude Code's marks, so `arm_a.py` spends your key under `GRAPHENE_SPEND_CAP_USD` only, not the night's cap. Default: allow it, set that cap by hand, and start `arm_bprime.py` from your own terminal (`docs/test/LIVE_SESSION.md`).

**Broken or risky**
- Your checkout's repository was marked bare at 04:45 (a test run under my `git bisect run` inherited GIT_DIR; guarded since): `git status` fails there until you type `git -C ~/Desktop/AllThingsAgenticHackathon config core.bare false`. The classifier refused it to me. Nothing else in its config changed; your edits are as you left them.
- Sandboxes refuse this project (403): rungs 3, 4, 6 and 7 wait; ask at tokenfactory.nebius.com/sandboxes/about.
- Other harness slips, none spent or took your key off the machine: a fake key reached the real ConTree (403); shells that read `~/.zshenv` gave stand-ins your key (only the local stand-in saw it); Playwright files in your git-ignored `.playwright-mcp/`, removed; my integration worktree deleted at 03:04, cause unknown.

---

(Everything below the brief: what was decided, the evidence, the screens, the state of every branch.
The shaping run's morning is `morning-2026-09-28.md`.)

## What I found at the start (01:30 EDT)

- `GRAPHENE_AGENT_LIVE_USD` is unset in this session (`env | grep -c GRAPHENE_AGENT_LIVE_USD` gave 0).
  I did not set it. A desktop notification went to you at 01:40 in case you were still up.
- Your checkout was on `fix-replay-teardown` with uncommitted edits to `README.md` and
  `docs/process/morning.md` (a formatting pass, and a new opening for the README), not to
  `tests/test_demo.py`: the replay-teardown commits were already merged as PR #33. I carried the
  README's new opening into `first-light` as your edit, and left the rest of your checkout untouched.

## Your commands

Nothing live ran in this session. These are the commands for what the directive meant to run:

- **Sandboxes first.** Rung 1 met `ForbiddenError` (403). What the key lacks, a read that spends
  nothing: `uv run --frozen --extra sandbox python -c "from graphene_map import sandbox; print(sandbox.refused() or 'Sandboxes do not refuse this project')"`.
  Access is asked at tokenfactory.nebius.com/sandboxes/about. A made-up key also gets a 403, so check
  `NEBIUS_PROJECT_ID` names the key's project.
- **An agent practising, as tonight meant to:** in your terminal `export GRAPHENE_AGENT_LIVE_USD=10`,
  then `claude` in a checkout of `first-light`; the agent (or you, with `!`) runs
  `docs/test/practice.sh 5` (no Sandbox needed), then `3`, `4` and `7` once Sandboxes let the project
  in, `docs/test/practice.sh prototypes`, and `docs/test/practice.sh night` for the bill (at most $10,
  nothing new past $8). The opening only opens the ladder; `ask`, `talk` and the prototypes' own
  commands stay yours.
- **From your own terminal** the same commands work; with the export they go on the same night's bill.
  Unset it before any registered run: `evidence.py` refuses whatever was made under it.
- **Rung 5's recording into CI:** `cp .graphene/practice/leaf.jsonl tests/recordings/first-light-rung-5.jsonl`, commit; CI replays it and counts it for secrets.
- **The rough cut:** `caffeinate -i env EXECUTOR='nemotron --placement local' docs/demo/build.sh`
  (15 to 35 minutes, up to $3), then `open docs/demo/rough.mp4`; drop `EXECUTOR` once rung 3 passes.
- **The session with Alex** (the registered arms, rung 6, the shaping study with executors, the final
  recording): `docs/test/LIVE_SESSION.md`.

## What was decided

`docs/DIRECTION.md` 101 to 127, each with its evidence. Read 101-103 (the opening, the night's bill,
spending as your act), 108 (the board's default, by study 4), 112-115 (the direction and its study)
and 109 (the teardown) first.

## The evidence

- **The suite and CI:** 1,543 passed, 3 skipped, with every extra, at `f68c0a3` (21 min, the machine
  loaded); CI green on all seven jobs at `f68c0a3`. Later commits are said where they land.
- **Studies on stand-ins** (Claude sub-agents, not people; n = 1 a cell): study 4, the board after
  tonight's changes against the outline, registered and its build pinned before any run
  (`docs/test/results-2026-09-29-board.md`): as faithful or more on 4 of 4 tasks, more modelled
  attention on 3 of 4, so `board: auto`. The direction against `morning.md`
  (`docs/test/results-2026-09-29-direction.md`, 12 runs): no advantage shown (143.9 against 105.4
  modelled person-seconds, all right); after the naming fix, an exploratory pass: 104.1 against 107.4.
- **The ladder, dry:** all seven rungs PASS in 2 min 16 s against the stand-ins (bill $0.0049, the fake's).
- **The walks:** the 72 findings of 28 September all fixed or closed with a reason
  (`docs/process/shaping/walks.md`, "First light's verdicts"); 46 new ones from tonight's three
  walkers, 38 about the product, each fixed with a test or closed with a reason (DIRECTION 119-127).
- **Screens:** `docs/process/shaping/screens/first-light/` (the terminal before and after at 80x24 and
  120x36, the page at 1280 and 390, the direction), and the rehearsal video at
  `~/graphene-first-light/rehearsal.mp4`.

## What went wrong in the harness (none of it spent, and no key of yours left the machine)

- `GRAPHENE_AGENT_LIVE_USD` did not reach this session, so the night's live half did not happen.
- About 02:00, a lane's test ran `docs/proof/nemotron.sh` against the fake with a made-up project id
  and the sandbox extra: its leaves called the real ConTree with the fake's key "fake-key" (403). The
  chokepoint now refuses ConTree to any process with an agent's mark and no opening.
- The rehearsal's tmux stage and the walkers' seats started shells that read `~/.zshenv`, so your key
  was in their environment: the rehearsal sent it to the local stand-in on 127.0.0.1 (which keeps no
  headers); no walker chose Nemotron or ran a live command. The stage now starts `/bin/bash` directly.
- Playwright MCP wrote three snapshot and console files into your checkout's git-ignored
  `.playwright-mcp/`; I removed exactly those three.
- At 03:04 my integration worktree was deleted, all but part of `src/` and `tests/`, during a test run;
  the same files rerun one by one deleted nothing, and the cause is not known. The branch was intact.
  The closing review had an adversary on it.
- At 04:45:51 your main repository's `core.bare` became `true`. I had run `git bisect run` over a test
  in one of my worktrees; git exports GIT_DIR there, and before the guard (`499a6da`, both conftests
  now drop git's location variables) a test's `git -C tmp init` re-initialised the shared repository.
  Only `core.bare` changed (every other local key is as it was; no identity was written). The fix,
  `git -C ~/Desktop/AllThingsAgenticHackathon config core.bare false`, was refused to me by the
  classifier, so it is yours. The closing review's destructive-operations adversary found the same
  hazard independently (finding 34) and reproduced it in a throwaway clone.
- This session's classifier refused one stand-in's commands in study 4 (rerun under its rule, the
  failed run kept) and my own look at a process's environment (I did not pursue it).

## State of every branch

- **`first-light`:** this run, pushed; draft PR #34. Its lanes were cherry-picked onto it
  (`fl-open`, `fl-a`, `fl-b`, `fl-board`, `fl-teardown`, `fl-keyguard`, `fl-hook`, `fl-walks-tui`,
  `fl-walks-page`, `fl-dir`, `fl-e`, `fl-docs`: local only, `git branch -D` drops them).
- **`main`:** `cbfbe0f`, untouched. Your checkout: on `fix-replay-teardown`, its uncommitted edits
  as you left them.
- **Outside the repo:** `~/graphene-board4-runs` and `~/graphene-board4-venv` (study 4; they hold the
  cards' briefs: do not publish), `~/graphene-direction-runs` (the direction study), and
  `~/graphene-first-light/rehearsal.mp4`.

## Rollback

`first-light` was cut from `origin/main` at `cbfbe0f` (the merge of PR #33). Nothing on `main` moved.
To drop everything this run did: close the draft PR and `git push origin --delete first-light`.
