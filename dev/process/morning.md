# morning.md — 2026-10-08 — the timeline

Rollback: `main` is untouched at `a96fb48`. To drop the night: close the PR, `git push origin --delete timeline`.

## Your 30 minutes

Not ready yet. This file is rewritten at every milestone; this section is written once the branch is pushed,
and run once from the pushed branch before 07:55.

## Your practice run

Written with the 30 minutes.

## The brief

1. **The three numbers**, before (from last night's records, `dev/process/timeline/before.md`) and after:
   - hand-backs over another leaf's file: 8 in last night's 10 trees (6 over a test file) · after: not run yet
   - Nemotron proposals: 7 in 34 asks (21%) · after: not run yet
   - the feeds paragraph as a tree under `auto`: 1 in 3 · under `on`: not run yet
2. **Watch first:** nothing new to watch yet.
3. **The bill:** $0.0016 of $40 (`planner`: one probe of Ultra with a strict JSON schema).
4. **Decide:** nothing yet.
5. **Broken or risky:** nothing found yet.

---

## Branches

- `main`: `a96fb48`, untouched, local and on GitHub.
- `timeline`: the night, in a clone outside your checkout. Not pushed yet.

## What was done, in order

- **00:13** Read the directive. Branch `timeline` from origin/main `a96fb48`, in a clone outside your checkout.
  The directive is committed at `dev/process/directives/TIMELINE_DIRECTIVE.md`.
- **00:20** The night's ledger: $40 cap. Nothing new starts past $35 (Graphene's own stop is 90%, $36: the
  run checks the bill before it starts anything). The session was not started with `GRAPHENE_AGENT_LIVE_USD`;
  the directive's $40 line is the opening, as decision 151 read last night's, so this run sets it to 40 for its
  own live commands.
- **00:30** Lane 0, from last night's records: `dev/process/timeline/before.md`.
- **00:34** The suite on `main` as it is: 1,631 passed, 21 skipped, in 17.6 minutes.
- **00:38** Ultra with a strict JSON schema, live: it answers JSON in the schema. With tools in the same request it
  calls no tool, so the schema goes on the final answer only. $0.0016.
- **00:42** Lanes 1 to 4 started, one builder each in a worktree of their own, each reviewed from two sides before
  it merges.
- **00:45** Token Factory reached, 4 NVIDIA models; Sandboxes work (`graphene key check`).
- **01:55** Lane 2 merged: the Nemotron planner answers in a strict JSON schema, tried by Graphene's own validator
  before it prints, sent back once with Graphene's words. Its review found one real fault (a node's goal of two
  lines was written as one), fixed with a test.
