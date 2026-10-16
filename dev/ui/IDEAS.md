# Graphene, talking to your agents with almost no text

A three-minute read. All of it is built in `dev/ui/playground/` so you can judge the feel:
`uv run python dev/ui/playground/app.py` (`--repo .` for this repo's real plan, `--graph pasted` for your diagram).

## The problem, in one line

"I tell an AI what I want, it fills in the blanks itself, and I only learn which blanks when the work is done."
Graphene asks before (the plan, the board) and checks after (proof). **In between, you watch a gauge you cannot
talk to**, on a screen made for engineers: about 145 words a frame, nine state words, ids and paths.

## What jcode gets right, and what it never does

- It names every agent (fox, oak, river) and gives each a live line: a spinner, `3/9`, "stalled 12s". You feel
  the swarm at a glance.
- Its own notes call agent chat "the wrong shape" and say "the dependency edge IS the data channel": a graph.
  Its screen never draws that graph, only counters like `nodes 4/9`.
- It never asks you anything: "needs you" is whatever the worker says about itself. Twelve overlapping surfaces.

Copy the **feel**, skip the surfaces. (Read from its code, not run.)

## Three screens, one selection

Move the cursor in one and the others follow.

**1. Cockpit.** Numbers, not paragraphs: `✎ 9/42` files touched of allowed, `✓ 1/3` proofs, `!2` writes stopped,
`⏸ 79s` quiet, a live tail. The verbs sit on the row: `⏎` take the default, `t` tell it one line, `w` give it the
folder it was stopped at, `x` pull back. About 50 words at 80x24; the watch screen runs about 145.

![cockpit](playground/shots/cockpit.png)

*Found while building it:* real plans have sentence-long titles; the screen needs a three-word name per
task, which the planner can write.

**2. Territory.** Which folders each task may write. Only Graphene can show this, because scopes never overlap.
Before you accept a plan: "13 of 636 files may be touched (2%)", plus where new files may appear. Live: touches,
stopped writes, "oak waits for fox: it owns the same files". After: what changed, and anything outside. Press `p`
and click a folder to give it or take it away (the widen and edit-scope Graphene already has).

![territory](playground/shots/territory-real.png)

**3. Flow.** The plan as boxes and arrows, from a small layout of mine (stable positions, loops in a lane,
two-way arrows, click a box). Your pasted diagram lays out on its own: 10 nodes, 13 edges, 136 columns.

![flow](playground/shots/flow-pasted.png)

Honest limits: busier than your hand-drawn one (terminals want right angles); it needs about 120 columns, and
at 80 shows one node and its neighbours. jcode's prettier diagrams are images (Kitty, Sixel), which break in tmux.

## The graph idea, straight

I get it: a graph is the shortest form of direction. Two cautions. There are **two graphs**: *execution* (tasks
and what they wait on; Graphene has it, without loops) and *intent* (what you care about and how it relates; your
diagram). Start with execution, live, agents on the boxes; the planner proposes it and you reshape it with single
keys. No free-form editor, no rebuilding LangGraph's state machinery: our edge is that each box is file-scoped,
proof-checked work with you on the loop. Later, opt-in: bounded loops.

## Not proven

Nothing here talks to a live agent; the numbers come from a simulator. **Tell** (a note that reaches a running
agent) rests on Claude Code's hook docs ("next to the tool result"), which do not say it holds for `claude -p`:
it needs one cheap probe. Dollars are parked; nothing here counts them.

## What I need from you

1. If you don't answer a question, should the agent **stop or carry on** with its default? Today it carries on.
   This is the thesis switch.
2. One person with one window, or many sessions at once?
3. Plain words on screen (task, may touch, proof) instead of leaf, scope, check?
4. Agent names: charm or whistle? Try it.
5. Execution graph first, intent graph second?

## Next, if you like it

An added screen in `graphene watch` behind a key, not a new default (124 tests pin today's 80-column strings):
Look, then Answer (rows drive the existing take and sign-off), then Tell.
