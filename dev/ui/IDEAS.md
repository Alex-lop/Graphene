# Graphene, talking to your agents with almost no text

The feel was judged in `dev/ui/playground/` (`uv run python dev/ui/playground/app.py`), which stays a simulator to
try ideas in. What you liked is now `graphene watch` (`src/graphene_map/cockpit/`), on the real plan, with the older
outline behind `--classic`. The shots below are the playground's; the README has the real ones.

## The problem, in one line

"I tell an AI what I want, it fills in the blanks itself, and I only learn which blanks when the work is done."
Graphene asks before (the plan, the board) and checks after (proof). **In between, you watch a gauge you cannot
talk to**, on a screen made for engineers: about 145 words a frame, nine state words, ids and paths.

## What jcode gets right, and what it never does

- It names every agent (fox, oak, river) and gives each a live line: a spinner, `3/9`, "stalled 12s".
- Its own notes call agent chat "the wrong shape" and say "the dependency edge IS the data channel": a graph.
  Its screen never draws that graph, only counters like `nodes 4/9`.
- It never asks you anything: "needs you" is whatever the worker says about itself.

Copy the **feel**, skip the twelve overlapping surfaces. (Read from its code, not run.)

## Three screens, one selection

Move the cursor in one and the others follow.

**1. Cockpit.** Numbers, not paragraphs: `✎ 9/42` files touched of allowed, `✓ 1/3` proofs, `!2` writes stopped,
`⏸ 79s` quiet, a live tail. The verbs sit on the row: `⏎` take the default, `t` tell it one line, `w` give it the
folder it was stopped at, `x` pull back. Measured on the shipped recording at 80x24, frame by frame: the cockpit shows a median of 56 words (at most 88),
the classic screen 98 (at most 135).

![cockpit](playground/shots/cockpit.png)

*Found while building it:* real plans have sentence-long titles; the screen needs a three-word name per task.

**2. Territory.** Which folders each task may write. Only Graphene can show this, because scopes never overlap.
Before you accept a plan: "13 of 636 files may be touched (2%)". Live: touches, stopped writes, "tests waits
for agent 1: it owns the same files". After: what changed, and anything outside. Press `p`, click a folder: given or taken.

![territory](playground/shots/territory-real.png)

**3. Flow.** The plan as boxes and arrows, from a small layout of mine (stable positions, loops in a lane,
two-way arrows, click a box). Your pasted diagram lays out on its own: 10 nodes, 13 edges, 136 columns.

![flow](playground/shots/flow-pasted.png)

Honest limits: busier than your hand-drawn one (terminals want right angles); it needs about 120 columns, and
at 80 shows a node and its neighbours. jcode's prettier diagrams are images, which break in tmux.

## The graph idea, straight

I get it: a graph is the shortest form of direction. Two cautions. There are **two graphs**: *execution* (tasks
and what they wait on; Graphene has it, without loops) and *intent* (what you care about and how it relates; your
diagram). Start with execution, live, agents on the boxes; the planner proposes it and you reshape it with single
keys. No free-form editor, no rebuilding LangGraph: our edge is that each box is file-scoped, proof-checked work
with you on the loop.

## What is proven, and what is not

**Tell works, mostly.** Real `claude -p` agents (Haiku, half a cent a run) followed a note on their next step in
12 runs of 14 when it came with their next write, and in 1 of 12 when it came as a command ended
(`dev/ui/playground/probe/`; the gate now tells only with the next write). A cheap
model sometimes ignores a note, so the screen shows "heard" and the live tail, not "done". Not proven: a live
agent on these screens (a simulator drives the numbers), and Codex.

## Decided while you slept

You said to do what I think is best. Each flips with one line; the new watch follows all five.

1. **Carry on, and say so.** An unanswered question takes its default, as today; its row shows the default beside
   Enter, and Tell reaches the agent if you change your mind. Stopping an unattended run costs the night.
2. **One window, many agents,** one repository.
3. **Plain words on the new screens** (task, may touch, proof, stuck); the engine and docs keep leaf, scope, check.
4. **Agents go by numbers** (your call, 18 October, over my "keep the names"): agent 1 is the first to take a
   task of the plan, a retry is a new number, and "agent 2 is stuck" is sayable.
5. **Execution graph first,** intent graph after.

## Next

Not done: sub-goal boxes in the flow view; an hour of real agents on these screens (recordings and throwaway
plans only); Tell on Codex.
