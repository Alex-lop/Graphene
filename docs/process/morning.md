# morning.md — 2026-09-29 — the first-light directive

## The brief

**Watch first**
- No rough cut: its takes are live (rung 7), and live runs refused in this session (below).

**What ran live** — $0.0012 of $10, all of it yours (`.graphene/practice/progress.json`)
- Rung 1 access: PASS 01:14 (you). Sandboxes: `ForbiddenError: You do not have permission to perform this action`.
- Rung 2 local leaf: PASS 01:16 (you). Graphene has made a runtime call to Token Factory.
- Rungs 3-7: not run. `GRAPHENE_AGENT_LIVE_USD` was not in the environment this session started with, so every live path refused, as the directive says; the commands are below the brief.

**New tonight** (in progress)

**Decide** (in progress)

**Broken or risky**
- Sandboxes refuse this project (rung 1): rungs 3, 4 and 7 need that access first.

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
