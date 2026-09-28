# Tonight's own plan, shaped by the coordinator in the person's seat

The directive puts tonight's own plan in Graphene and has the coordinator be the person on it: write
the paragraph, prune, take or refuse the offers. Lane B (settings a person states once) went through
Graphene this way, in a clone of this repository at `~/graphene-night` (branch `night-b`), with Claude
Code as planner and executors. Every friction felt there is a finding for lane A, logged here as it
happened, in the order it happened.

How the coordinator stood in: its shell carries Claude Code's markers (`CLAUDECODE`,
`CLAUDE_CODE_SESSION_ID`, …), so Graphene takes it for an agent, as it should. For the person's acts it
dropped those markers and set `GRAPHENE_AS=person:alex`, which is the stand-in's mechanism
(`docs/test/newrun.sh`); the plan's log marks each such act "(no terminal)". A clone, not a worktree:
a worktree shares the main checkout's store, and a plan in force there would have held every other
lane's sub-agent to it.

## Findings

