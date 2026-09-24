# Graphene: the terminal directive

*For the agent that runs on this repo next. Written 2026-09-23 with Alex, after he sat down as the person for the first time. The two earlier directives in `docs/process/directives/` still hold; this one says what his afternoon taught us and what matters now. Read both of them, `docs/DIRECTION.md`, the two test results in `docs/test/`, and `docs/test/findings/` before you touch anything.*

## Before anything else: how you work here

You are running as Opus 5.5, the strongest agent Alex has ever handed this repo to, and he is more excited about this run than any before it. Everything the earlier directives said about how to work holds: there is no token budget, there is no clock, doubt your work and never your capacity, decide at every fork and write down why, keep `docs/process/morning.md` current at every milestone, and nothing waits on Alex. Use sub-agents in parallel wherever items are independent. Push the branch green after each milestone; leave one PR.

What is new is that the person has now used the product. His findings are in this directive and in the record of his session; they outrank the stand-ins. Where a stand-in's number and his afternoon disagree, his afternoon is the evidence.

## What his afternoon taught us

He shaped a tree, accepted it, added a leaf of his own, ran two executors in parallel, and watched real hand-backs. Two things were true at once:

- **The mechanism works and it felt right.** Watching `--parallel` spin real agents, and then watching a leaf come back with a reason, is the moment the product taught him what it is: the boundary is the scope and the check, not the executor's opinion. Editing the plan at a high level was good.
- **Typing the tree is the expensive part.** Adding a node was cumbersome. The first ten minutes were more ceremony than the README admits. And both stand-in tests said the same thing in numbers: a person authoring nodes loses to a person authoring a paragraph on effort, every time.

Both tests and his afternoon measured the same mistake, and it is ours, not his: they had the person author the tree. A contract is more information than a sentence; of course it costs more to type.

## The reframe this run is built on

**The person never types the tree.**

The paragraph stays the input, in both worlds. The agent proposes the tree *from* the paragraph. The tree is the agent's echo of what it understood, made editable. The person's job becomes reading and pruning, which is cheap when the surface is right, and which catches a misunderstanding before any tokens are spent on it. That is the one win the first test actually showed (two reject-on-sight items removed from a proposal before code existed), and it is the sentence on Alex's site: no matter how many tokens you have, the agent has to infer direction, and Graphene is where you see the inference and correct it.

Said as the product: **paragraph in, tree out, prune, run.** That is the README's first line, and every design question tonight is decided by whether it makes that sentence more true. The premise from the tree directive still governs the ties: spend tokens, save attention.

## Terminal, for real this time

The tree directive said terminal first and the run built `watch` on an alternate screen that could not scroll, cropped a leaf off the bottom, and wrapped every row twice. Alex works in WezTerm and wants to do all of this there, with vim-style movement, seeing the decisions as they are made, before anything is put into production. The page stays as the shareable export and gets nothing tonight. This is what terminal means now.

### 1. The plan as text, before anything else

A plain-text form of the tree that round-trips. One line per node; indentation is hierarchy; scope, check, needs and owner readable on the line or under it; proposals marked so a person sees them at a glance; ids stable, so an edit applies to the node it was made on. `graphene plan edit` opens the whole tree, or a subtree, in `$EDITOR`; the person adds a line, reorders, deletes a subtree, saves, and Graphene diffs and applies, the way `git rebase -i` and `kubectl edit` work. A line Graphene cannot read is refused with its line number, nothing applied.

Agents propose in the same text, not JSON. The SessionStart hook teaches the form in a few lines. `propose -` on a terminal with no pipe refuses in one line and says what to do instead; waiting forever is indistinguishable from a hang and it happened to him.

This is first because it is the floor the TUI cannot fall below, it works in nvim on day one, and it is the largest single fix for "adding a node is cumbersome." The exact grammar is yours; the tests are that a person can write it without a manual and an agent can write it without a mistake.

### 2. The TUI, one screen, vim keys

Textual. Not Rich `Live`, not curses by hand. One screen: a tree pane and a pane for the selected node (its contract; and when it is running, done or handed back, its record). A status line that always says which repository and which plan, so a stray `cd` cannot fool anyone again. Proper scrolling. A `--once` print for people who do not want the full screen yet.

The keys, as the floor; change one only for a reason you write down:

- move: `j` `k`, `gg` `G`, `/` search, `n` next match
- fold: `za` toggle, `zo` open, `zc` close, `zR` all open, `zM` all closed
- shape: `a` add a sibling, `A` add a child, `e` edit this node's contract in `$EDITOR`, `E` edit this subtree as text, `d` drop, `s` split (below), `y` accept a proposal, `u` undo the last person act (the plan log already makes this trivial)
- run: `R` run everything ready, `r` run this subtree, `x` release or reopen, `l` the executor's tail (below), `Enter` open the record
- select: `V` visual, so several leaves are accepted or dropped at once
- `:` a command line that takes every existing `graphene` command verbatim, plus `:ask` (below); `?` help

Every key is a command that exists on its own. The TUI is a view over commands and text, never the only way to do anything, because agents, scripts and the test harness use the commands.

### 3. The agent in the loop: two panes, one store

Do not build a chat widget. Claude Code is a better conversation than anything Graphene can build. The layout is the person's session in one pane and the Graphene TUI in the other, sharing the store: they talk on the left; proposals appear on the right, marked, as the agent writes them; `y`; `R`; executors spin in worktrees and leaves light up. Ship this as the recorded demo and as the recipe in the README, with the WezTerm layout written out.

The TUI names the two agents on screen, because the person confused them and so will everyone: the **planner** is the session that proposes; the **executors** are what `run` starts. The README says it in one sentence.

For when the person is not in a session: `:ask <sentence>` sends a one-shot planner invocation whose only output is a proposal, and `s` on a leaf asks the planner to decompose it into children. A planner is an executor whose scope is the plan, started by the same mechanism as `run --with`, with the command the person names. Decision 9 in `docs/DIRECTION.md` gains one word: Graphene starts the planners and executors the person names, and never holds a key.

### 4. Hand-backs that offer their own fix

The best thing in his afternoon. When a leaf comes back because its scope was too narrow, Graphene already knows the exact paths outside it. The refusal carries two offers, one keystroke each: widen this scope to these paths, or make a sibling leaf for them; and `?` to ask the planner when neither is right. The loop he described, inspect, edit the contract, run again, becomes about four keystrokes, and the boundary becomes the thing that helps rather than the thing that stops.

### 5. Live means executors, not only states

Per running leaf: which executor, which worktree, the last tool call, seconds since it did anything. `run` currently captures executor output and throws it away; keep a tail per leaf and show it on `l`. Tool calls and files, on demand, under the leaf they served: that is where the record earns its place now.

While you are in `run`: Ctrl-C releases the leaf it started, in place as well as in a worktree; a leaf whose `needs` are still in flight in another worktree waits, the same idea as the overlap delay already there; and the write lock held around `git status` of every worktree is a scale bug to fix before anyone runs twenty leaves on a large repository. Some of his findings were fixed in the last merge; check each against `docs/test/findings/` and his session's list, and fix the rest rather than assuming.

### 6. The first ten minutes, rewritten for paragraph-in

The README's opening changes to the sentence above and the recipe changes with it: a paragraph typed to the session, the tree appearing in the TUI, one prune, `R`, a hand-back, the offer taken, done. Never send a first user through `/var/folders`; the scratch repository lives somewhere a person recognises as a repository. A five-line "you are here" card near the top: where you are standing, `graphene`, `graphene node show` on a failure, `run --parallel`, the TUI. Spell out the two agents. Say which repository on every write, the way `plan goal` already does.

### 7. The third test measures attention

The first two tests counted characters and the paragraph won. Count what the product claims to save: person-seconds from the paragraph to the run, keystrokes, and misunderstandings caught before code (proposal items the person removed or changed that would have cost a restart). Same task shape as before, stand-ins who write ordinary sloppy prompts as well as dense ones, arms one at a time. Report it the way the first two were reported, without flattering the tool, and leave Alex the ten-minute recipe. Do not wait for his run.

## What not to do

- Do not build the TUI before the text form. The hackathon died of surface; the text form is the floor.
- Do not make the TUI the only path.
- Do not touch the page beyond what the tree already forced.
- Do not put a conversation inside the TUI.
- Do not make `strict` prompts the default; `leaf` is the right Tuesday.
- Do not revive a guess at scope from prose. When the person gives no scope, the planner proposes one and the person sees it.

## Principles that still decide arguments

All of them from the two earlier directives: the graph binds, executor-agnostic, verification is not optional, mechanism before surface, users not revenue, Alex authors the direction, spend tokens to save attention, the feel is the product. One gains its final form tonight:

**The person never types the tree.** When a design would have the person author a contract that an agent could have proposed for them to prune, the design is wrong, however clean it looks.

## The decisions that are yours

- The grammar of the text form, and how proposals, ids and owners appear in it.
- How `E` and `plan edit` apply a text diff to the store when a line was moved, split or deleted, and what the person sees when the diff is ambiguous.
- What the `:ask` planner is told, and what it is refused, so its only output is a proposal.
- Whether the executor tail comes from the hooks record, the process output, or both.
- The Textual layout at 80 columns, since WezTerm will not always be wide.

## The README and DIRECTION.md

Rewrite the README for paragraph in, tree out, prune, run, in the voice the earlier directives asked for, as a person would write it; Alex will edit it. `docs/DIRECTION.md` is his: the question it asked, whether he would rather shape a tree than type a paragraph, now has his answer, and it is neither. Record that answer, amend decision 9, add every decision you take with its reason, and strike nothing he wrote.

## The morning

`docs/process/morning.md`, current at every milestone, leads with:

1. What he can run in five minutes: the two-pane layout, a paragraph, the tree appearing, a prune, `R`, a hand-back and its offer.
2. What is waiting on him, and the decisions he can strike.
3. The map of the code for a person working in it daily, updated for the text form and the TUI: which module does what, where its tests are, what to read first.
4. What was verified and how, what was not, and at most three questions, each only if it blocks the next step.

Then the rollback SHA and the state of every branch.

## Ground rules

Unchanged: nothing leaves the machine; `~/.claude/settings.json` is his; tags, PyPI and the name are his; `main` is green at every stop; work on a branch, push it green after every milestone, do not push `main`, leave one PR; keep the machine awake; record the rollback SHA before your first change.

Now go. Paragraph in, tree out, prune, run. Decide like it is yours, because tonight it is.
