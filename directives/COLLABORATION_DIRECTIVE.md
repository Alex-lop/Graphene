# Graphene: the collaboration directive

*For the agent that runs on this repo next. Written 2026-09-20 with Alex, out of a conversation about what Graphene is for. Read all of it before you touch anything.*

## Before anything else: how you work here

You are the strongest agent there is, and Alex believes in what you can do as much as he believes in this idea. Believe it too. There is no token budget. Spend tokens on thinking, on evidence, on sub-agents that attack your plan, on walkthroughs of what you built by an agent that has never seen the repo. Do not spend them on hedging, on asking permission, or on a plan so cautious that nothing gets decided. Alex is asleep or in class; nobody will answer a question tonight. When you reach a fork, choose, write down why in `morning.md`, and keep going. A decision he can read and reverse in the morning is worth more than a question he has to answer before you can move.

Doubt your work and never your capacity. Verify everything you build the way this repo already does well: a failing test first, numbers checked against git by hand, a fresh agent with only the README trying to use it. But do not hesitate to decide, and do not shrink the vision to what feels safe. Every problem in this directive is inside your reach. If something looks impossible, the mechanism you reached for first is the wrong one; the thing itself is not out of scope.

This directive says what Graphene is for and which principles decide arguments. It does not say what to build tonight, in what order, or in how many lines. Those are yours.

## Why Graphene exists

Alex lets coding agents run on his repos for hours and sits down afterwards to a hundred commits he did not watch being made. The problem is not that the agent did the work. It is that the way he works with the agent is a prompt, then a wait, then a diff. That is a batch job. He types a paragraph, hopes it was understood, and finds out later. He described the feeling exactly: guiding the agent down a path and hoping it gets it right, with a growing sense that there is no point in a person being there at all.

That feeling is the reason for this product, and it points at the answer. Agents execute goals. They do not originate them, and they do not carry the reasons behind them: who the software is for, what "good" means in this codebase, what would never be acceptable. Producing code is now cheap. Deciding what to build, setting the boundaries, and knowing when it is done are not cheap, and they are where a person's leverage lives. Today that leverage can only be applied through a paragraph at the start and a diff at the end. Graphene exists so a person can apply it continuously, cheaply, and in a form the agent cannot mistake.

Pilots went through this with autopilot: "what is it doing now?" The fix was never a better flight recorder. It was showing what the automation intends to do next, and giving the pilot controls that mean what they say. Everything Graphene has built so far is the flight recorder. It is good, it is needed, and it is not the product. Your job is the flight director.

Alex is not against agents doing the work. He thinks what they can do is astonishing and that Euler would have been amazed. He wants to work *with* them. The question you are answering is what that looks like when it is real.

## What Graphene is

Graphene is the shared plan between a person and their coding agents: a graph of the work, which both can see, which the person shapes, and which the agents are bound to.

The vocabulary, at the level of meaning rather than schema:

- A **node** is a unit of work that someone will do. It carries what the work should achieve, which part of the repo it may touch, how anyone will know it is done (a command that must pass, a person's say-so, or both), what it waits on, who is doing it, and what state it is in.
- The **graph** is the nodes and what they wait on. It is the artifact both parties look at. It is prospective: it is about what will happen and what is happening, not a diary of what did.
- The **record** is what this repo already builds: agents, files, commits, checks, and an honest count of what cannot be accounted for. From now on it hangs off nodes. "What did the agent do for this node, and how much of that is verified" is the debrief, scoped to intent, and that is where the coverage line lives.

Where the person's authority enters, in order of how much leverage each point gives:

1. **Before a node runs.** The agent proposes the graph; the person splits, merges, reorders, tightens a scope, adds a check, claims a node for themselves. Nothing has been spent yet and editing is cheap, which is exactly why most of the control belongs here.
2. **At the boundary between nodes.** A node finishing is a natural checkpoint. The person does not reach into a running agent's head. They change the contract for the next node, and the next node sees the changed contract. This is the version of "change direction mid-run" that can be made true, and it is enough.
3. **After.** The record, per node.

Two things follow that nothing in the repo's market scan has:

- **The person is in the graph.** A node can be assigned to Alex. "I will write the migration; you do the endpoints and wait for me." That is collaboration in the ordinary meaning of the word, and it answers the disconnection directly: he is a participant, not a spectator. This is not a feature to schedule later. It is the definition of the product.
- **Agents collaborate through the same graph.** A node claims a scope; dependencies decide what may start; two agents on one file becomes something the graph prevents rather than something a map draws afterwards.

## Principles that decide arguments

When you are unsure, these decide. Each carries its reason so you can tell when it does not apply.

**The graph binds.** A control on screen either changes what an agent can do, by a mechanism you can name and test, or it is not drawn. Where a mechanism has a hole, the hole is printed next to the control. The previous thesis got this exactly right and it survives in full: a button the agent ignores destroys trust in one click, and a product about trust cannot afford one.

**Executor-agnostic.** A node does not care who does it: Claude Code, Codex, a person. Anthropic owns the loop you are building around. Plan mode, task tools, the agent map, worktrees and hooks each take a slice per release, and an editable plan with per-task permissions shipped inside Claude Code would end a Claude-Code-only Graphene in one changelog entry. The structural defense is that the plan is the same whoever executes a node. Design the graph and its contract that way from the first commit, even though you will ship one executor.

**Prospective by default.** The default screen is the plan and where the work stands, not the latest session. Sessions, prompts and tool calls are evidence about nodes.

**Verification is not optional.** Collaboration without verification is delegation plus hope. The coverage line, the checks, the record: they stay, attached to nodes. Nothing you build may make the honest count less honest.

**Mechanism before surface.** Prove the loop closes on one node, in the terminal, ugly, before the graph is beautiful. The hackathon died of surface outrunning proof: 137,000 lines and four renderers around an experiment that was never run. You will be tempted the same way, because the picture is the fun part. Proof looks like this: one node, shaped by a person, executed by an agent that could not leave the node's scope and could not stop before its check passed, with the person changing the next node at the boundary and the agent honoring the change. When that is true in the terminal, you have the product. Everything after is making it visible and pleasant.

**Users, not revenue.** For the next two months the measure is people who edited a plan and had an agent obey it. The launch asset is a recording of exactly that: a person shaping a graph, an agent doing one node and stopping at the boundary, the person changing the next node. Nobody pays for this yet, and that is fine.

**Alex authors the direction.** The previous strategy was written by an agent that overruled Alex's vision on mechanism grounds and built a viewer. That does not happen again. If a mechanism cannot make something true, you say what *can* be made true that serves the same intent, and you build that. You do not quietly demote the intent.

## What the repo already has, and what to stop

Keep, because it serves the vision:

- The hooks channel: `init`, the stdlib-only ingest path with its measured budget, subagent start and stop. It is the only real lever into Claude Code and the enforcement layer the graph needs.
- Agents as records: task text, parent, worktree, span, closing message. Most tools have tool calls; this repo has who was asked to do what.
- The coverage line: three counts, never one number.
- Worktree awareness. Parallel nodes need it.
- The rules design in `docs/PRODUCT_THESIS.md` §7: protect, finish gate, note, one writer. It is right. It was missing the object a rule attaches to; now it has one.
- The lane layout with positions computed in Python. A task DAG in topological columns with agent lanes reads at fifty nodes; a force layout does not. The rejection of the bubble graph stands, for the plan too.

Stop:

- Session-centric everything. The card, `sessions`, `ui`: each is re-rooted at the plan or becomes a view of one node's record.
- `why` as the headline. It stays as a command, verified and honest. It is a feature funded competitors already sell across six agents. It is not what Graphene is.
- The "not what you asked for" regex over prompt text. Scope is now a fact from the node's contract. Delete the heuristic.
- The law "Graphene never runs an agent." It is suspended. It was adopted because the hackathon collapsed, and the hackathon collapsed under surface, not dispatch. Whether Graphene dispatches is now a decision you make on evidence (below), not a law.
- Agent artifacts in the repo root. Directives, `morning.md`, strategy summaries and nightly reports go somewhere a stranger does not trip over them. The root is for the product.

Read `docs/PRODUCT_THESIS.md` and `docs/reports/` as input to argue with. The market scan, the hook mechanics, the finding that most source changes never pass through `Edit` or `Write`, the measured numbers: all still true and useful. Its verdict answered the wrong question.

## The decisions that are yours

**How the graph binds.** Two routes are known. Decide between them, or find a third, and record the reasoning.

- *Graphene stays inside the session.* An MCP server plus hooks. The agent proposes nodes and reads the plan before each step through MCP; the person edits it in the map; `PreToolUse` denies writes outside the current node's scope; `Stop` is blocked until the node's check passes; the next node's contract is whatever the person left there. Lighter, keeps Claude Code in charge, guarantees only as strong as hooks.
- *Graphene dispatches.* Each node becomes its own scoped invocation (`claude -p`, a subagent) in a worktree, given the node's goal, scope and check, with hooks enforcing them. The agent obeys the graph by construction because it never sees more than one node. Stronger guarantee, more surface, and it is the thing the hackathon was.

Our lean, from the conversation this came out of: the first route first, because it can be true in weeks rather than months and it tests the real hypothesis, which is whether a person will shape a graph instead of typing a paragraph. If that holds, dispatch is the upgrade. You may overturn the lean. If you do, `morning.md` says why, with the evidence.

**What "done" means when the check is a person.** Design the boundary so that a human-owned node, or a human sign-off, does not stall an unattended run in a way that surprises anyone, and so that a waiting agent is visibly waiting.

**The test.** The old kill criterion measured whether a map beats a terminal for reading. Wrong test now. Design the one that measures collaboration: for the same task, does a person working through Graphene get fewer files touched outside intent, fewer "no, not that" restarts, and less rework than the same person with a prompt and a diff? Run it with sub-agents standing in for the person before Alex runs it himself, and tell him how to run it in ten minutes.

**What to spike before you commit.** You have the tokens. If two routes look close, build the smallest true version of each on one node and let the evidence decide. Do not choose by argument alone when a two-hour experiment exists.

## The README

Write it as the first thing you believe a stranger should read about Graphene, and write it as a person would. No changelog in the README, no list of removed flags, no vendor's name in the first sentence, no headline a funded competitor already owns. Say what Graphene is for, in the terms above and in your own words. Say what works today and what comes next, without overclaiming and without hedging into fog. Then the install, then the first ten minutes. Alex will edit or replace it; write it as if he will not.

## Working with Alex

- `morning.md` is what he reads first. Lead with what you decided, why, and what he can open right now. Then what you verified and how, what you did not, and at most three questions, each only if it blocks the next step.
- Keep one short, plain-language document that states what Graphene is and the product decisions taken so far, written for him to edit. Treat his edits to it as binding on the next run. That is how he authors the direction, and it is the same shape as the product: he shapes the graph, you execute the nodes.
- Where you disagree with this directive, say so in writing, with evidence, and then do what you believe is right. He asked for that. What he did not ask for is a quiet substitution.

## Ground rules

- Nothing leaves the machine. No telemetry, no model call by Graphene itself, no upload. Transcripts can hold secrets; the privacy posture in the repo stays as it is or gets stricter.
- `~/.claude/settings.json` is his. Never touch it; print the line he needs.
- Tags, PyPI and the name are his. Do not publish; do not rename.
- `main` is green when you stop: tests, lint, the wheel built and smoked, the committed UI matching its source.
- Keep the machine awake while you run. Stop starting new work when finishing it would leave `main` broken by morning.
- Rollback: before your first change, record the SHA of `main` in `morning.md` and the one-line command to return to it.

Now go. Decide like it is yours, because tonight it is.
