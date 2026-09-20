# Graphene: what it is, and what has been decided

*Alex, this file is yours. Edit anything here and the next agent that works on this repo treats your
edit as binding: it reads this before it reads the code. It is the same shape as the product: you
shape the plan, the agents execute it. Last written 2026-09-20 by the agent that ran the
collaboration directive (`docs/process/directives/COLLABORATION_DIRECTIVE.md`).*

## What Graphene is

Graphene is the shared plan between a person and their coding agents: a graph of the work, which
both can see, which the person shapes, and which the agents are held to.

You let agents work on your repo for hours. Today the only ways to steer them are a paragraph at the
start and a diff at the end. Graphene puts a plan in between: the work is cut into **nodes**, each
saying what it should achieve, which paths it may touch, how anyone will know it is done, what it
waits on, and whose it is. You edit that plan before anything is spent. You change the next node
when the last one finishes. And for every node there is a **record** of what was really done for it
and how much of that can be verified.

- A **node** is a unit of work someone will do: an agent of any vendor, or you.
- The **plan** (the graph) is the nodes and what they wait on. It is about what will happen.
- The **record** is what did happen, per node: who held it, what was refused, what the check said,
  and an honest count of what cannot be accounted for.

## Decisions taken so far

Each has its reason, so you can tell when it no longer applies. Strike any of them.

1. **One mechanism binds, whoever executes: the boundary.** A node is done only when Graphene
   itself has run the node's check and has asked git what changed since the node was started. A
   change outside the scope keeps the node open, however the file was written, and nothing that waits
   on it can start. *Why:* it needs no vendor. On 2026-09-20 the same gate held a Claude Code agent,
   a Codex agent and a person doing a node by hand.
2. **Two routes sit on that core, and both ship.** Inside a Claude Code session, the hooks refuse a
   write outside the scope before it happens, refuse a stop while a node is open, and the next
   node's contract is read fresh when it is started. For unattended work, `graphene run` takes each
   ready node, hands its contract (and nothing else) to an executor, and decides itself whether it
   is done, sending a refused executor back. *Why both:* the directive leaned to the first route, and
   it is the one a person sits in. The spikes showed its stop refusal is a nag with a ceiling (the
   vendor ends the turn after about 8 refusals, and a headless run that hits `--max-turns` never
   fires the stop hook at all). What held every time was a check made out of process after the
   agent was gone. That check is decision 1, so the second route cost 125 lines.
3. **The plan's surface is the command line, not an MCP server.** `graphene plan`, `graphene node
   start|done|release`. *Why:* every executor has a shell, including Codex and you; every real agent
   tonight (Claude Code and Codex) used it correctly from its help and its refusals alone. An MCP server would add typed tools for one vendor and no
   binding power. Revisit if agents start fumbling the commands.
4. **While a plan is in force, work happens inside nodes, and a finished plan stays in force** until
   you archive or pause it. A session that holds no node writes nothing in the repo. *Why:* the first
   real agent run did both nodes properly, waited until no node was open, then made the edit no node
   allowed, and said so ("no node was open. Graphene accepted the write"). With this rule the same
   agent, refused, proposed a node for the edit and asked you to accept it. That is the behaviour
   the product wants: scope creep becomes a proposal you can see.
5. **Agents propose; only a person disposes.** Accepting a proposal, editing a contract, signing
   off, reopening, overruling the gate, pausing, archiving and acknowledging loose changes are a
   person's. A person is someone at a terminal, or the map started from one. Anything without a
   terminal is treated as an agent.
6. **When "done" needs a person, nothing is surprised.** A node that is yours is never handed to an
   agent. A node with a sign-off stops in `review` after its check passes, and what waits on it
   waits. `graphene plan accept` says before the run which nodes agents can reach alone and which
   will wait for whom; an agent that runs out of ready nodes is told it can stop, and `graphene plan`
   shows "waiting on a person" with what is asked of you.
7. **Graphene runs the check, not the executor.** "It passed" is then a fact about the repo, not a
   sentence in an agent's summary.
8. **Only writes are scoped. Reads never are.** A node that depends on another has to read what that
   one did.
9. **Graphene never commits, merges or pushes, and never calls a model itself.** `graphene run`
   starts the executor *you* name, with the permissions *you* give it. The old law "Graphene never
   runs an agent" is replaced by that sentence.
10. **Every hole is printed next to the control it weakens** (README, `docs/HOW_IT_WORKS.md`, the
    map). The known ones are in "What does not bind" below.
11. **The name, the package and PyPI are yours.** I renamed nothing and published nothing (0.2.0 on
    PyPI is yours, from 2026-09-20). The import package is still `graphene_debrief`.
12. **What was demoted.** `graphene why`, the session card, `graphene sessions` and the session map
    stay as commands because they are verified and useful; none of them is the product. The
    guess at "not what you asked for" from prompt text is deleted: scope is a fact of the node now.

## What does not bind (say it wherever you sell it)

- A shell command can write a file in a way nothing reads beforehand (a script that opens files
  itself). The hook refuses the forms it can parse (`>`, `>>`, `tee`, `sed -i`, `mv`, `cp`, `rm`);
  the rest is caught only at `done`, by git. Until then the stray change is on disk.
- A file created outside the scope and moved out of the repo before `done` is invisible to git. It
  is caught when it comes back, at the next start, as a change no node owned.
- Claude Code lets a session end after about 8 refused stops in a row. The node then stays
  `running` on the plan, which is how you see it. `graphene run` has no such ceiling.
- A hook that crashes or times out lets the call through (the vendor's rule). The boundary holds
  without it.
- "A person" rests on the environment. Inside an agent's shell `GRAPHENE_AS` changes nothing; an agent
  that first strips its own markers and then sets it passes for a person, and the log marks the act
  "(no terminal)". No command line can do better than that.
- The plan's store is a file in the repo that git ignores: a script that opens it directly is
  neither stopped nor noticed. What git ignores, nobody audits.
- `graphene run` works in one checkout, one node at a time. Two agents at once in one checkout are
  kept off each other's paths by scope; they are not isolated from each other's half-written files.

## What comes next, in the order I would do it

1. You run the test (`docs/test/PROTOCOL.md`, ten minutes) on a task of your own. Everything below
   waits on whether you would rather shape a plan than type a paragraph.
2. The recording: you shaping a plan in the map, an agent doing one node and stopping at the
   boundary, you changing the next node. `docs/proof/proof.sh` is that scene in a terminal.
3. The same hooks for Codex. Its hook JSON has the same shape as Claude Code's (checked against its
   docs on 2026-09-20), so `graphene init --codex` is mostly a settings file.
4. A worktree per node in `graphene run`, then nodes in parallel. It buys isolation: refused work
   never reaches your branch. It costs branches, merges and conflicts the person has to understand.
5. The vendor's sandbox as a third layer for scope when it is on: the only thing that stops a
   script from opening a file itself.

## How this file is used

An agent starting work here reads this file first, then `docs/HOW_IT_WORKS.md`. Where this file and
a directive disagree, this file wins, because it is the one you edit. Where the agent disagrees
with you, it says so in writing, with evidence, in `docs/process/morning.md`, and then does what
you decided.
