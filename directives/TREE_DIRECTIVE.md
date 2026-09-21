# Graphene: the tree directive

*For the agent that runs on this repo next. Written 2026-09-21 with Alex, after reading the first night's work (`docs/process/reports/2026-09-20-collaboration.md`, `docs/test/results-2026-09-20.md`). The first directive, `docs/process/directives/COLLABORATION_DIRECTIVE.md`, still holds; this one says what changed and what matters now. Read both, then `docs/DIRECTION.md`, before you touch anything.*

## Before anything else: how you work here

Everything the first directive said about how to work still stands: you are the strongest agent there is, Alex believes in what you can do, there is no token budget, doubt your work and never your capacity, decide at every fork and write down why. Two things change.

**There is no clock tonight.** Alex wants this run to go as long as it takes. Work through the ranked list below until it is exhausted or until the next item could not end with `main` green before you would have to stop. Use sub-agents in parallel wherever items are independent; the cuts and the test at the end of the list can run beside the main line from the start. Keep `docs/process/morning.md` current at the end of every milestone, not only at the end of the run, so it is true whenever Alex reads it.

**Nothing waits on Alex.** He has been busy and has not run the ten-minute test; he may not tonight either. Do not design around his answer to anything. Decide, record the decision in `docs/DIRECTION.md` for him to strike, and build. If you find yourself writing a question, write the decision instead and the question under it.

## What the first night proved, and what it found

The mechanism is done. A node binds at the boundary by a check Graphene runs itself and a diff git computes, and that held a Claude Code agent, a Codex agent and a person. Refused a write, an agent proposed a node for it. The person is on the plan with their own lane. That work stays, and nothing tonight may make it less true.

The night also found three things, and this directive exists because of them:

1. **On small attended tasks Graphene is overhead.** Twelve stand-in runs: the plan arm typed half again as much, cost more and took twice as long, for no measured gain. The one sloppy one-line prompt outside the protocol touched two files outside intent and failed a third of its checks. So the value is real and conditional: it appears when the task is too big for a paragraph to name the files, when the run is unattended, and when the person's paragraph is an ordinary Tuesday's rather than a dense one. It does not appear on a three-file change someone is watching.
2. **A plan in force is a ceremony tax during the day.** Propose, accept in a second terminal, then do, for a one-word fix. People will pause the plan and never unpause it.
3. **The graph's reason to exist is not exercised.** One node at a time, one checkout, no worktrees. Today the plan is a checklist with dependencies. The picture nobody else draws, several agents working leaves of one plan while the person sleeps, does not exist yet.

## The premise: spend tokens, save attention

The price of agent work falls every few months and its quality rises. A person's attention does neither. Anything that spends a person's attention to save tokens is on the wrong side of that curve, and the first night's ceremony tax is exactly that. Graphene's purpose, said plainly: let a person delegate more work to agents than they could before, with the same or less attention, without losing the thread of why any of it is being done.

Every design question tonight is decided by that sentence. Agents propose and decompose (tokens) so the person edits instead of writes (attention). Agents run in parallel (tokens) so the person reviews boundaries instead of watching (attention). The record is computed so the person reads a line. A control that makes the person do something an agent could have done is wrong by construction, however safe it feels.

The measure, which morning.md states in numbers wherever it can: how much work a person can hand off per unit of their own attention, and whether they still know why each piece is being done.

## The plan is a tree

Today the plan is a flat list of nodes with dependency edges. That answers "what" and "in what order" and never "why". Alex wants the plan to be a tree, and he is right, for a reason that matters more than tidiness: a tree is where the *why* lives.

At the level of meaning, not schema:

- **The root is the goal, in the person's words.** Why any of this is being done.
- **A node's children are how it will be achieved.** An internal node is a sub-goal; a leaf is work someone will do, with a scope and a check exactly as today. Branching is whatever the work needs; nothing is gained by forcing it to two.
- **Hierarchy is meaning; edges are order.** Dependencies (`needs`) stay, among leaves and among siblings, for what must finish before what. The two are different questions and both are kept.
- **Every executor is told the path from its leaf to the root.** What it is doing, under what, toward what, in the person's words. That is what it means for an agent to understand what it is doing, and it is the thing a paragraph cannot carry past the first turn.
- **Agents decompose; the person prunes.** A leaf too big to do becomes an internal node with proposed children; a proposal is a subtree. The person accepts, splits, merges or drops at any level, and accepting a subtree accepts its leaves. This is how delegation scales: the person stays near the root, shaping intent, and the agents fill in the leaves. It is the recursion that spends tokens well.
- **Done rolls up.** An internal node is done when its children are; if it carries a check of its own, that check runs then, which is where integration lives.
- **The record hangs off leaves and rolls up the same way.** Coverage per leaf, per subtree, per plan.

This changes the data model, so it comes first: everything else on the list is built on it. Migrate the store additively as before; a flat plan from 0.3 is a tree with one implicit root.

## Terminal first

The terminal is the primary surface from tonight. The page (`graphene ui`) stays as it is and gets nothing tonight beyond what the tree forces. The reasons: the agent works in the terminal, so a plan the person shapes there is a plan in the same words the agent reads; a browser tab is the one step too many at the come-back moment; and a person who never leaves the terminal is a person who stays in the work.

What this means in practice is yours to decide, within these:

- The person can shape the tree without leaving the terminal: read it, prune it, split a leaf, accept a subtree, claim a node, change the next node while another runs. Commands are the floor.
- A live view of the tree in the terminal, leaves lighting as they start and finish, what is waiting on the person shown first, is the ambition of this run. Whether that is a full-screen interface or a refreshing view is your call on the evidence; what is not acceptable is the terminal being the poor cousin of the page.
- The tree is printed collapsed to what needs the person, and expands on request. A fifty-leaf plan fits a screen because most of it is folded.
- The same words for the person and the agent. What `graphene` prints to the person is what `graphene node start` prints to the agent, with the path to the root.

## What matters this run, in order

Each item says why it is where it is. Later items may start in parallel on sub-agents when they do not depend on earlier ones.

1. **The tree.** Above. The data model, the path told to every executor, decomposition as proposal, done rolling up, the record rolling up. First because everything below stands on it.
2. **Free on a Tuesday.** A plan in force must feel like nothing on a small attended task. The person's own prompt, typed at their terminal, is a person's act, and the `UserPromptSubmit` hook sees it: "yes, do n3" typed into the session can be the acceptance; one line typed into the session can be a leaf. The second terminal disappears for the common case. The target: a one-file change under a plan costs the person zero keystrokes more than the paragraph did. Second because adoption dies without it, and the first night's numbers say so.
3. **Scale in worktrees.** Ready leaves run in parallel, each executor in its own worktree, merged at the boundary when the merge is clean and left for the person when it is not. This is where the tokens go, it is the overnight run, and it is the recording. Verify it on real agents, two at once, before the page draws it. Third because it is the value; it is not first because it needs the tree to know what is ready and the boundary to know what is done.
4. **The tree, live, in the terminal.** Above. Fourth because a live view of a tree that cannot run leaves in parallel has nothing to light up.
5. **The test a paragraph can lose.** The auditor's list in `docs/test/results-2026-09-20.md` is the spec: a task spanning five or more directories; stand-ins that write ordinary sloppy prompts as well as dense ones; a quality measure beyond the hidden acceptance (inputs the code was never shown); the three harness defects fixed; arms run one at a time with their own `TMPDIR`; the check may state the answer, and both arms are capped alike or neither is. Run it, report it the way the first one was reported, and leave Alex the ten-minute recipe. Do not wait for his run. Fifth because it measures what the items above build, and it can run on a sub-agent as soon as item 2 lands.
6. **The cuts.** The session product becomes a node's record: cut `debrief.py`, `attribute.py` and `graph.py` to what a leaf's record needs, and make that record, coverage line included, work for any executor, not only a Claude Code session. Drop the banned-words test; it is a hackathon scar now shaping vocabulary, and `ponytail` becomes `TODO` in every file. Person authority: the page's token is the model; the TTY test is a fallback that must never turn a person's command into a proposal they cannot accept. Sixth because none of it blocks the items above, and all of it can run in parallel from the start.

If you finish the list, the next things are Codex hooks and the vendor's sandbox as a third layer for scope, in that order, from `docs/DIRECTION.md`.

## Principles that still decide arguments

The first directive's principles all hold: the graph binds, executor-agnostic, verification is not optional, mechanism before surface, users not revenue, Alex authors the direction. Three gain a nuance tonight.

**Mechanism before surface, now.** The boundary is proven. What is unproven is the person's experience: that shaping a tree is faster than writing a paragraph for a real task, and that a plan in force is free on a small one. Prove those in the terminal, on real agents and with stand-ins, before the live view is beautiful.

**The feel is the product.** The first night built a contract-and-permission layer, which is the moat and stays. But its words lean on the fence: held, refused, does not bind. Alex did not describe wanting a leash; he described wanting to be in the work. Write the product's words, in the README and in every message an agent or a person reads, for the person who wants to delegate more, not for the auditor. The holes stay printed where they are; they do not have to be the voice.

**Spend tokens, save attention.** Above. When two designs are equally true by mechanism, the one that asks less of the person wins, even if it costs more agent work.

## The decisions that are yours

- **How a proposal is accepted from inside the conversation**, and how a one-line leaf is made from a prompt, without reviving the deleted guess at scope from prose. A leaf needs a scope and a check; decide how a person gives them in one line, and what the default is when they give none.
- **What the tree does when a merge is not clean.** Two leaves in two worktrees touched one file. The graph knows their scopes overlapped or it did not; decide what the person sees and what an executor is told.
- **Whether the live view is a full-screen interface or a refreshing print.** Decide on what you can verify tonight; the floor is commands that work.
- **What "why" looks like on the page** the tree forces changes on. The minimum, not a redesign.

## The README and DIRECTION.md

Update the README for the tree and the terminal, in the voice described above, as a person would write it; Alex will edit it. `docs/DIRECTION.md` is his: add every decision you take tonight with its reason, and strike nothing he wrote.

## The morning

Alex is going to start working in this codebase himself, daily, and he wants to ramp up. `docs/process/morning.md` is for that, and it leads with:

1. What he can run in five minutes: the tree on a real plan, the parallel run in worktrees, the live view.
2. What is waiting on him, and the decisions he can strike in `docs/DIRECTION.md`.
3. **A map of the code for a person about to work in it every day**: which module does what, where its tests are, what to read first, and which parts you think a person should own from here. He should be able to make a change and know where its test goes by the end of that section.
4. What was verified and how, what was not, and at most three questions, each only if it blocks the next step.

Then, as before, the rollback SHA and the state of every branch.

## Ground rules

Unchanged from the first directive: nothing leaves the machine; `~/.claude/settings.json` is his; tags, PyPI and the name are his; `main` is green at every stop; keep the machine awake; record the rollback SHA before your first change.

One addition: work on a branch, push it after every green milestone so CI runs, do not push `main`, and leave one PR for him to merge, as the last run did. Every milestone that lands on the branch is a state he could merge on its own.

Now go. There is no clock, and nothing waits on him. Decide like it is yours, because tonight it is.
