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

## Decisions taken on 2026-09-21 (the tree directive)

Taken by the agent that ran `docs/process/directives/TREE_DIRECTIVE.md`, each with its reason and,
under it, the question I would otherwise have asked. Strike any of them. Where one changes a decision
above, the old one is left as written and the change is named here.

13. **The plan is a tree, and the root is a sentence of yours.** `graphene plan goal '…'` is the
    root: why any of this is being done. A node's `parent` says what it helps achieve; a node with
    children is a **sub-goal** and needs only a title; a node without is a **leaf**, with a scope
    and a check exactly as before. A node from 0.3 has no parent and sits under the root; nothing
    in the store was migrated, a node is a JSON document and gained two fields. *Why a sentence and
    not a root node:* one goal a plan is what the directive describes, and a row nobody can take,
    finish or drop would need an exception in every operation. *Question:* do you want several
    goals in one repo at once? Today that is several sub-goals under one sentence.
14. **Hierarchy is meaning, `needs` is order, and what a sub-goal needs its leaves wait on.** A
    cycle through needs, through the tree, or through both is refused when the plan is edited.
15. **Done rolls up, and a sub-goal's own check is where integration lives.** When the last leaf
    under a sub-goal is done Graphene runs the sub-goal's check, if it has one, in the checkout
    where the leaves' work is together. Failing, the sub-goal stays open, the plan says "its leaves
    are done and its own check fails", what waits on it waits, and the way on is a leaf under it
    for what is missing. A new or reopened child reopens a finished sub-goal.
16. **A proposal is a subtree; you accept at any level.** `graphene plan propose` takes nested
    `children`. Accepting a node accepts the proposals under it, and the proposals it sits under (a
    leaf is never in the plan without its why). A leaf too big to do is split by proposing children
    under it (`--parent`) and handing it back; dropping the children makes it a leaf again, which
    is how a split is undone. Dropping a sub-goal drops what is under it.
17. **Every executor is told the path from the goal to its leaf**, above its contract, as `why:`
    lines, root first: `graphene node start`, `graphene node show`, and the prompt `graphene run`
    hands over are the same words. The person reads the same lines in `graphene plan`.
18. **A request you type into a session is a leaf. This changes decision 4.** With a plan in force
    and no node held, the first write of a turn makes a leaf from your prompt, held by that session.
    You run nothing. If you typed the CLI's flags in the prompt (`--scope 'src/db/**' --check 'make
    test'`), they bind like any
    leaf's; if you did not, it may touch anything, it ends when the turn ends, and its record is
    git's list of what it changed. The scope is never guessed from the prose. No edit, no leaf.
    A session that holds a planned leaf is still held to it. `graphene run`'s executors never get
    one. `graphene plan prompts strict` gives decision 4 back as written. *Why:* the first night's
    numbers: a plan in force cost a second terminal for a one-word fix, and people pause a plan that
    taxes them and never unpause it. What you asked for in your own words is not scope creep; it is
    now on the plan with a record instead of refused. Shown on a real agent:
    `docs/proof/tuesday.sh`. *Question:* is "anything, until the turn ends" too loose a default for
    you? The alternative I can defend is "anything no other open leaf claims".
19. **A plain yes typed into the session accepts. This changes decision 5 in one place.** A short
    prompt that starts with yes / ok / go ahead / accept (80 characters at most, no question mark, no
    "but", "not", "drop" and the like) accepts what that
    session proposed, or the proposals it names, or everything when it says so, as you, and the log
    says "by their prompt in the session". Everything else in decision 5 stands. *The hole:* an
    agent that starts a second agent chooses its prompt. `graphene run` marks its executors so they
    are never read this way; nothing marks an agent your agent starts by hand.
20. **Whoever carries no agent's mark is the person, terminal or not. This changes decision 5's
    last two sentences.** Claude Code, Codex and `graphene run`'s executors mark their shells, and a
    mark outranks everything. No terminal (an editor task, a pipe) no longer turns your `add` into a
    proposal you then cannot accept; the log says "(no terminal)" and that is all the terminal
    decides. *The cost, said plainly:* an agent of a vendor Graphene has never heard of, which sets
    none of the marks, is taken for you. It was refused before. The page's token is still the model
    for the page.
21. **`graphene run --parallel N` commits and merges, on branches of its own. This changes decision
    9 for that one command.** Each ready leaf runs in `.graphene/worktrees/<id>` on `graphene/<id>`.
    A leaf that passes its boundary is committed there by Graphene (your git identity; the message
    is the title, the goal, the why path and `Graphene-Node: <id>`) and merged `--no-ff` into the
    checkout you started the run from. Plain `graphene run` is unchanged and commits nothing.
    Graphene still never pushes and never calls a model. *Why:* work in a worktree can only reach
    your branch as a commit, and a commit a leaf with its why in the message is how `git log` reads
    as the tree. Shown on two real agents at once: `docs/proof/parallel.sh`.
22. **When a merge is not clean, nothing of yours is touched and the leaf waits for you.** Leaves
    whose scopes overlap are never in flight together (the second starts when the first has
    landed, on top of it), and a write outside a scope is refused, so two leaves cannot have
    written one file. What is left is your own work in the way. Then the merge is aborted, the leaf
    stops in `review` with its work on `graphene/<id>`, what needs it waits with it, and you are
    told the two commands: `git merge graphene/<id>`, `graphene node signoff <id>`; or `reopen` it
    to have it done again on top of what is there. An executor is never asked to resolve a conflict.
23. **The live view is a refreshing print: `graphene watch`.** It redraws the lines `graphene plan`
    prints, once a second, with the last few events under them; what waits on you is first. *Why not
    a full-screen interface with keys:* I could verify a print tonight (it is the same function, and
    it is tested) and not a key-driven interface; shaping is done with the commands, which agents
    and you share. `graphene plan` folds finished work once the tree is longer than a dozen lines;
    `--all` unfolds.
24. **The banned-words test is gone**, and deliberate shortcuts in the code are marked `TODO:`.

25. **The session product is cut down to a node's record. This replaces decision 12.** `graphene
    why`, the session card and `graphene sessions` are gone, with `debrief.py` and `why.py` (the
    three files the directive named went from 2,181 lines to 966). A leaf's coverage line is
    computed for any executor from the node's log, git and the check Graphene ran; Claude Code's
    records, where a session held the leaf, add which path traces to a recorded write. *Why cut
    rather than keep:* both commands rested wholly on Claude Code's edit payloads, and could answer
    nothing for Codex, `graphene run --with …` or you. The record rolls up the way done does:
    `graphene node show <sub-goal>` adds up the leaves under it, `graphene plan record` the whole
    plan, and a leaf that could not be counted is named, never counted as zero. *Left for a
    follow-up:* four store methods only the card called (`add_debrief_run`, `last_debrief_run`,
    `recent_paths`, `recorded_path_count`).
26. **On the page, "why" is the path, in a node's detail.** The goal is in the header, the plan is
    an indented outline above the unchanged canvas, a sub-goal shows `n/m done`, and a node's detail
    opens with the same `why:` lines an executor is told. Nothing else on the page changed.

27. **What the closing review changed** (two adversaries, 47 findings, each reproduced twice; the
    reports are in `local/reviews/`, untracked). The ones that changed a decision above: the check
    Graphene runs is never the person (decision 20 had made a test file the person, because pytest
    takes the terminal away); a proposal binds nobody, so a proposed child does not turn the leaf it
    is under into a sub-goal (16); a leaf in a run's own worktree does not answer for what changes in
    your checkout meanwhile, so you can work there during a run (21; this gives up noticing an
    executor that writes into your checkout by absolute path from its worktree, which the hooks
    still refuse when outside its scope); scopes that *could* meet are kept apart, not only scopes
    that share a tracked file (22); a merge of your own in progress is never aborted; a run on a
    detached HEAD, and a second run at once, are refused in words; a killed run's leaves are handed
    back by the next one; you can overrule a sub-goal's check with a reason; and the terminal print
    folds any sub-goal with nothing moving under it, so sixty leaves just accepted are a dozen lines.

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
  (`graphene run --parallel N` gives each leaf a worktree of its own: decision 21.)
- A prompt is taken as yours (decisions 18 and 19). An agent that starts another agent writes its
  prompt. The log names every acceptance made "by their prompt", and every leaf made from one.
- A leaf made from a prompt with no `--scope` may touch anything but the plan's store and the hooks'
  settings; it is a record, not a fence. Its record lists what changed in the checkout during the
  turn, which includes what you changed by hand meanwhile.
- Both rest on the vendor being the only caller of the hook. An agent that pipes a hand-written
  event into `graphene ingest hook` is refused by the ordinary spelling and not by a determined one.
  Found by the closing review, which did it; the acts are logged "(no terminal) … by their prompt".
- Every request that became a leaf is on the plan in your words, and `graphene ui --export` carries
  the plan.
- Whoever carries no agent's mark is taken for you (decision 20).
- While a parallel run is going, a commit of your own on the branch it merges into can make a leaf
  in another worktree look as if it changed your files, and its `done` is refused. It is sent back,
  and says so; nothing is lost. Work in the same checkout through a session (a leaf made from your
  prompt answers for it), or let the run finish.

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
