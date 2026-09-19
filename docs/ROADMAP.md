# Where Graphene is going

The problem: I let an agent run on my repo, came back, and could not account for the changes.
Agents now run for hours, in parallel, overnight, so it is getting more common. The north star is
that people and agents working on the same codebase can see, trust and steer each other's work.
Graphene gets there in three layers, in this order, each built only once the one before has users.

## 1. The record (this release)

What happened, and why, attributable to the request that caused it. `graphene why PATH:LINE`
answers "which prompt wrote this line"; `graphene` prints the short card of what a session
changed, what it changed that you never asked for, and what it tried and abandoned. Everything
comes from Claude Code's own transcripts and hook events; no model is involved at any point.

## 2. The rules (next)

Deterministic conditions a person sets on a repo: do not touch this directory, ask before that,
run the tests before committing. They are enforced through the same hook mechanism Graphene
already installs, and every firing lands in the record so a refusal is as visible as a change.
Not built yet. Files and directories stay first-class in the data and in every view because
rules will attach to them.

## 3. The plan (later)

The agent's intended work as a graph the person can see and eventually shape before it runs.
Not built, and not to be built until the first two layers have users. Prompts stay first-class
in the data because plans will attach to them.

## A second agent source

Today the only source is `src/graphene_debrief/sources/claude_code.py`: it turns Claude Code's
JSONL transcripts and hook events into the three things the store holds, sessions, prompts and
tool events (with the file path and, when the log carries it, the file content before and after
a call). Another CLI's session logs plug in as a second module under `sources/` that produces
the same three things from its own format; the store, the attribution, `why` and the card do
not change, since they never look at the raw logs. What a new source must know is spelled out in
[HOW_IT_WORKS.md](HOW_IT_WORKS.md): which records are prompts, which are tool calls, how a call
is tied to its prompt, and where file contents come from.
