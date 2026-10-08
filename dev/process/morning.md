# morning.md — 2026-10-08 — the timeline

Rollback: `main` is untouched at `a96fb48`. To drop the night: close the PR, `git push origin --delete timeline`.

## Your 30 minutes

Not ready yet. This file is rewritten at every milestone; this section is written once the branch is pushed,
and run once from the pushed branch before 07:55.

## Your practice run

Written with the 30 minutes.

## The brief

1. **The three numbers**, before (last night's records, `dev/process/timeline/before.md`) and after
   (`dev/process/timeline/after.md`):
   - hand-backs over another leaf's file: 8 in 10 trees (6 over a test file) · tonight, so far: 3 in 8 trees (1
     over a test file). The statements task: 20 of 22 leaves landed in 3 runs, none left unrun.
   - Nemotron proposals: 7 in 34 asks (21%) · tonight: 10 in 20 (50%), then the round on the fixed schema (running).
   - the feeds paragraph under `on`: a tree, waiting for you, 3 times in 3 · under `auto`: 1 in 3.
2. **Watch first:** `graphene demo tests/recordings/timeline-claude.jsonl`, then Tab three times: the timeline.
3. **The bill:** $17 of $40 so far (see the end of the night for the final figure).
4. **Decide:** written at the end.
5. **Broken or risky:** written at the end.

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
- **02:06** Lane 4 merged: the `time` view. Its review found one high and two medium faults (the pane hid its
  newest row; a pane of bare headings for an executor with no meter; a replay never drew the recording's person),
  all fixed with tests. Two more fixed after: an attempt the meter cannot read is a held bar, not an idle one, and
  a leaf that waits on you keeps its usual pane.
- **02:10** Lane 3 merged: plan first `on` for new repos, one row for a one-leaf proposal, the Claude Code
  planner's stream on the ledger. Its review found five medium faults (among them: `y` would start a paid run on
  the last leaf of a pruned tree), all fixed with tests.
- **02:14** Lane 1 merged before its review ended, to start the live work; its review's fixes follow.
- **02:16** The live measurements started on build `b4fbf60`.
- **02:18** The first Ultra ask proposed take 9's shape again: the tests leaf waited on the code, and the code's check
  ran the tests leaf's new file. The rule let it through. Stopped everything, refused that case (`4490656`), and
  started again. The stopped session's hold settled at its own turns' list price, $0.18.
- **02:22-02:46** Lane 1 measured: three statements runs (20 of 22 leaves landed, 1 hand-back over another leaf's
  test file), two feeds runs (6 of 6). Lane 3: the paragraph under `on` was a tree three times in three; one Tuesday
  ask was one row, `y`, done in 40 seconds.
- **02:24** Ultra with `anyOf` in a strict schema wrote spaces to the token limit; with `pattern` it broke a
  string. Types and enums hold. The schema stays plain.
- **02:40** Lane 2's first round: 10 proposals in 20 asks. 12 of 41 answers had stuck after the nodes, because the
  schema asked for `says` last. Fixed (`674754d`): `says` first, and a board item's unreadable id made readable.
  The second round started.
