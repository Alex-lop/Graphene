# What Graphene is becoming

Alex, 24 November 2026. This is the direction. The prompt that carries it out is
[prompts/sessions.md](prompts/sessions.md). It replaces the direction of 16 November (a canvas you
plan on, and scope you can see), whose last copy is at `c82d5bd3`, with SCOPE.md and
prompts/workflow.md beside it: their seven leaves landed in PR #67.

## In one paragraph

Install the extension, start Claude Code or Codex the way you always do, and a Graphene page shows
that session's work as a graph. Click a card to see that agent's terminal. When it finishes, each
card carries a receipt: what it changed and whether its tests passed. Nothing in the default path
refuses, delays or holds an agent, and nothing needs setting up.

## Why it changed

After three and a half months nobody outside uses Graphene. The graph is the useful part, and
everything in front of it got in the way: Python, uv, a CLI, a downloaded .vsix, `graphene init` in
each repository, then hooks that stop an agent until a plan is filed, refuse writes outside a task's
files, refuse a checkout with uncommitted changes, and hold the session's end. Each of those has
stopped real work.

## The words

- **session**: one agent conversation, as Claude Code or Codex records it on disk
- **page**: one Graphene graph tab in the editor
- **card**: one piece of work on a page
- **receipt**: what a card says about the work after it happened
- **strict mode**: Graphene as it was (plan first, scopes, checks, hooks), now opt-in

## A handful of cards, four questions

Other tools draw every tool call, which looks alive and tells a person little. Graphene draws a
handful of cards at the level a person thinks at, and every mark on the page answers one of four
questions: what is it doing, does it need me, what did it change, did it work. A mark that answers
none of them comes off.

## Where cards come from

From what the agent already wrote, with nothing forced. The first of these a session has:

1. its own task list or plan;
2. the subagents and workflows it launched, one card each, fanning out from the request that
   launched them;
3. one card per request the person made, titled from their words.

Tool calls are never cards. They are the activity inside a card.

## Receipts

After the fact, from the transcript and from git: the files a card changed, each opening its diff;
the tests and checks it ran, the last run of each deciding; and anything worth a second look (a push,
a delete, a force flag, a hard reset, a test edited after it failed, a write outside the folder).

- Three honest states for tests: passed, failed, ran none. A tick only for a pass that was seen.
- A flag is a fact with the line that shows it, never a verdict. A guess is labelled as a guess.
- "Needs you" shows only when the file proves it. Otherwise "idle".

## The look

PR #67's canvas with PR #68 and #69's readability: the flow left to right with a curved edge from
each card's port, a tile for who is working, colour for a card's state, one line of status under it,
motion only where work is happening; the whole graph fitted on open, at sizes that read.

## Strict mode

The engine under `src/` and its tests stay as they are. A folder with a Graphene plan works as it
did: plan first, scopes, checks, hooks. It is one short section of the README now, and nobody has to
pass through it to see a graph.

## What it is not, and how it is judged

Not a guardrail anyone must set up before the graph appears, not a general automation tool, not a
web app. The extension reads local session files and sends nothing anywhere. It is judged by real
runs, by honest labels, and by how it feels in the hand: a claim proven only on a scripted stand-in
says so.
