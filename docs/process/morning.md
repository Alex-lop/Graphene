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
- The branch has about 70 commits; reshape it to about 40 before you merge (a force-push, backup branch first)? Default: yes, on your word.
- Rungs 3-7 by an agent: start Claude Code from a shell with `export GRAPHENE_AGENT_LIVE_USD=10` once Sandboxes let the project in? Default: yes.
- A run started from `watch` goes on after the watch's terminal closes, as after `q`. Default: keep.

**Broken or risky**
- Sandboxes refuse this project (403): rungs 3, 4, 6 and 7 wait; ask at tokenfactory.nebius.com/sandboxes/about.
- Keys in two agents' tests, none of yours left the machine: a fake key went to the real ConTree (403), and a rehearsal sent your ~/.zshenv key to the local stand-in on 127.0.0.1. Both paths are closed.
- My integration worktree was deleted during a test run at 03:04; the same test files, rerun one by one, deleted nothing. Cause unknown.

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

## Rollback

`first-light` was cut from `origin/main` at `cbfbe0f` (the merge of PR #33). Nothing on `main` moved.
To drop everything this run did: close the draft PR and `git push origin --delete first-light`.
