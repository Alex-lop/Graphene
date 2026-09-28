# Graphene: the shaping directive

*For the agent that runs on this repo tonight, from Alex's send until 08:00 his time (America/New_York). Written 2026-09-28 with Alex, after the winning run (PR #30, merged) and its field scan. The earlier directives hold wherever this one is silent. The winning directive's rules on integrity, claims and secrets carry over word for word, and the "claims the submission must not make" in `docs/process/field.md` are binding. Read `docs/DIRECTION.md` (70 to 80 first), `docs/process/morning.md`, `docs/process/field.md`, `docs/HACKATHON.md` and this file before you touch anything.*

## What kind of run this is

Everything the earlier directives said about how to work holds: doubt your work and never your capacity, decide at every fork and write down why, push green after each milestone, leave one PR, and nothing waits on Alex. Three things are different tonight.

**There is a clock.** Alex wakes at 08:00. Work until then. Start nothing new after 07:15, and have the last push and the brief done by 07:55.

**There is no key.** Alex puts his Nebius key in tomorrow morning and starts running practice tests himself. Nothing tonight touches Token Factory or a Sandbox. You never look for, read or print a credential. Everything that needs the key is made ready for his first hour with it.

**There is a lot of room.** Alex has most of this week's Claude usage left, and it resets mid-morning. Do as much real work as you humanly can:
- spawn a sub-agent for every independent piece;
- keep every lane full, and when one empties, start the next thing;
- if you hit a usage limit, lower the parallelism and keep going.

Tokens are not the measure; what Alex can use at 08:00 is. Never let a limit lose work: commit and push often, and keep the brief current.

## Why tonight is about shaping

1. **It is the only ground that is ours.** The field scan found that the track's most common pattern is the one Graphene's forks use: fork N candidates from one checkpoint and let the tests pick. Arborist, Coppice, ARCHON, PortVerdict and six more do it, several already live with numbers. Escalation ladders, scope gates and replays exist too. What we found no entry doing is letting a person shape the plan an agent proposed, before anything runs. That moment is Graphene's product and its uncopied edge. Everything that makes it faster, clearer and more visual moves both the product and the submission.
2. **It is the vision.** On 17 September Alex described Graphene as visual collaboration with agents: an editable graph where the person changes direction and adds the conditions agents run under. The tree got the shaping right. Tonight brings back the rest: the visual half (a board for ideas, a graph for the plan) and the conditions (settings a person states once).
3. **It is where the claim is weakest.** On 23 September a plain paragraph passed as many checks as the tree, with less of the person's time. "Spend tokens, save attention" becomes true only when shaping costs less attention than the paragraph and the diff it replaces. Every lane below is judged by that.
4. **It is where Nemotron can be non-obvious.** Forks after the plan are table stakes. Cheap open models working *for the person while they shape* are a different thing: answering the planner's questions from the repo, trying options before the person chooses, starting the obvious leaves while pruning goes on. That is affordable only at open-model prices, safe only in sandboxes, and something we found no entry doing.

## What does not change

- **The keep list:** the README's opening and hand-back copy; the one row grammar (a new view reuses its states and colours); plan first; the text form (anything new round-trips through `graphene plan edit`); `--with`; check-plus-git; "what does not bind"; the gif; `graphene-map`.
- **Every key is a command you could type.** A new key maps to a command, and the bottom line says which.
- **The terminal comes first.** 80×24 must work. The page may be richer, never required.
- **One source of truth.** The board, the graph and the outline are views of one plan in one store.

## How to run the night

You are the coordinator. Plan the night backwards from 08:00. Keep as many sub-agents working as the work allows (aim for eight or more at once), each in its own worktree on a lane below. You integrate, review and merge.

Give lanes files they own so they do not collide: new views live in their own modules, `tui.py` only wires them, and one lane holds `tui.py` at a time.

Put tonight's own plan in Graphene. It is the third real plan lane A's designs are tried on. Where a lane's work splits into leaves, run it through Graphene with Claude Code executors (`graphene run --parallel N --with claude`), and be the person: write the paragraph, prune, take or refuse the offers. Every friction you feel doing that is a finding for lane A; log it.

## The lanes

### A. Shaping, made visual (the heart of the run)

**Why.** See the section above: this is the product, the vision and the edge.

**What.** You decide the design, with evidence.

- **The board.** Before and beside the tree, a place where the person and the planner put ideas.
  - The planner puts up its questions (each with the default it would assume), options where it sees more than one way, assumptions, risks, and what it would leave out.
  - The person puts up quick notes of their own.
  - The person answers with a key: take the default, pick an option, drop it, park it.
  - Answers become the tree's constraints: a scope, a check, a leaf, a condition.
  - The planner asks instead of guessing, and brings only what the repo cannot answer. Both planners, Claude's and Nemotron's, learn to do this.
- **The graph.** The outline stays. Add the views the plan's shape calls for:
  - a top-down tree (root at the top, branches down to the leaves, the way Alex draws it);
  - a left-to-right directed graph where `needs` and order matter (what runs in parallel, what waits, the critical path);
  - or both.

  Choose automatically from the plan's shape and the terminal's size, let one key switch, and fall back to the outline when a view will not fit. The views can be richer in `graphene ui`, which already draws with d3.
- **Talking on the tree.** Ask the planner about the node under the cursor: why this leaf, split it, merge these, show me another way. When the planner revises, the person sees what changed since they last looked.
- **How to decide.**
  - Build at least two candidates for the board and two for the graph.
  - Render them at 80×24 and 120×36 on three real plans: feeds, the thirty-leaf plan, and tonight's own.
  - Put three sub-agents in the person's seat (a stand-in Alex, a first-time user, a judge) through the same shaping task on each, and record what they did and where they stalled.
  - Keep what cut their effort, write the decision with its evidence, and delete the loser.

**Done when** lane D shows a person going from a paragraph to a pruned plan with less effort than the outline alone, and every new view round-trips and reads at 80×24.

### B. Settings a person states once

**Why.** A condition the person repeats in every paragraph ("don't touch vendored or legacy files" is in the README's own example) costs attention every time; a setting costs it once. Judges and users also bring their own keys, repos and taste. Build what earns its place, and write a decision for what does not.

**What.**
- **Keys.**
  - Where Graphene finds each provider's key: the environment, then the system keychain if there is one, never a file in a repo.
  - How a person sets, checks and removes one.
  - A check that says "Token Factory: reached, N NVIDIA models" and never shows the key.
  - Setting and checking keys is person-only, like `init`'s choice: no planner or executor can run it.
  - The keymap too, if remapping earns its place for vim users.
- **Standing conditions.** Protected paths no scope may include, read-only globs, and what the planner must never propose. They show at the root of the board and the graph. The planner reads them, and the gate refuses any scope that breaks them.
- **How big the plan is.**
  - The planner sizes the tree to the repo and the ask: files, lines, the test layout, how many directories the ask touches.
  - The person sets a default (auto, finer or coarser), and one key re-asks a single plan for finer or coarser.
  - Measure it: proposed tree size against repo size on the four tasks, Graphene itself and two public repos of different sizes, and whether the stand-ins pruned less.
- **One place.** `graphene config` shows every setting in text form and edits them the way `plan edit` edits the plan: refused by line number, applied in one transaction. `init` writes it, and `?` in the screen shows it.

**Done when** each setting has a test, a line in the README, and a decision saying who needs it.

### C. Ready for the key

**Why.** Alex's first hour with the key should be practice, not debugging. First contact with a beta service will break something, and seeing what should take minutes.

**What.**
- **`docs/test/practice.sh`, a ladder Alex climbs one rung at a time.** Each rung has its own small spend cap, a pass or fail line, the bill so far, and the next command. The rungs:
  1. access (Alex types it himself; the last run found the session's classifier refuses it to an agent);
  2. one leaf local;
  3. one leaf in a Sandbox;
  4. the escape test in ConTree;
  5. a recorded leaf;
  6. one run each of arms A and B on feeds;
  7. the demo run, recorded.

  It stops at the first failure and says what that most likely means and what to try.
- **A dry run tonight.** Climb the whole ladder against the fake and Docker, so only the live calls are new tomorrow.
- **`docs/test/PRACTICE.md`.** Ten lines: what to type, in what order, how long each takes, and what it costs.
- **The winning directive's item 2, wherever it needs no key.** A stand-in writes the sealed paragraph for each task from the card (you never read it). The pre-registration is committed, and the fixed-tree protocol is ready.
- **A draft of the next run's directive, the live one**, for Alex to review: first contact, the arms, the chart, the demo run, and whatever tonight adds (lane D's study with Nemotron, lane E's prototypes live).

**Done when** the ladder passes end to end against the fake and Docker, and `PRACTICE.md` fits on one screen.

### D. Measure shaping tonight

**Why.** The claim is about attention. The protocol, the stand-ins and `attention.py` can measure it tonight, with the planner Alex already has, before any Nemotron number exists.

**What.**
- Once A and B land, run the stand-in protocol on the four tasks in three arms: the paragraph, the outline, and the board with the graph. Keep the planner, the executor (Claude Code) and the card the same across arms.
- Count person-seconds, keystrokes, words read, and accept and quality.
- Pre-register it first, and report it as registered, null results included.
- It is evidence about shaping, not about Nemotron, and it says so.

**Done when** `docs/test/results-<date>-shaping.md` holds the table and one sentence on what it shows.

### E. Nemotron in the shaping loop: ideas, then prototypes

**Why.** Submissions close on 30 October, so there is time. The winning use of Token Factory is one that makes the person's moment better, and that is still open.

**What.**
- Put a small team of sub-agents on ideas: at least twenty. Score each on:
  - fit with Graphene;
  - what a judge would see;
  - uniqueness against `field.md`;
  - cost;
  - whether it can be built and measured by 20 October.
- Prototype the best two or three behind a flag against the fake, with tests, ready to run live tomorrow.
- Rank them on one screen in `docs/process/ideas.md`.

Some to start from, not to follow:
- **Speculative leaves.** While the person is still pruning, Nano starts the obvious leaves in forked Sandboxes. A leaf whose contract changes is thrown away; one that survives lands when `R` is pressed. By the time you have pruned, much of the tree is done, and what you cut cost only cheap tokens.
- **Questions the repo answers.** Ultra asks, Nano answers what it can from the code, and only the rest reaches the board.
- **Options with evidence.** Two ways to do a branch, each tried cheaply in a fork, shown side by side before you choose.
- **A critic before `R`.** Super reads the pruned plan for overlapping scopes, weak checks and leaves too big for Nano, and marks them on the graph.
- **The bill before `R`.** Each branch's expected cost and time on the graph, from past records.
- **Learning your prunes.** What a person cuts and narrows is kept per repo and given to the planner next time.
- **Whatever the platform offers that we have not used yet.** Read `llms.txt` again: structured output for trees, batch, embeddings, fine-tuning on Graphene's check-verified leaves. Use them only where they serve the shaping.

### F. Polish everything

**Why.** Design is a quarter of the score, and a product people choose is polished wherever they touch it.

**What.**
- Put sub-agents in the seats of a first-time user, Alex and a judge. They walk the whole path at 80×24 and 120×36: install, `init`, keys, `ask`, the board, the graph, pruning, `R`, a hand-back, `demo`, the page. They file every rough edge, and you fix it.
- Update README and HOW_IT_WORKS for everything new.
- Reposition `docs/HACKATHON.md` and the storyboard around shaping, as the field's verdict says: "we found no other entry where a person prunes the plan before anything runs", never "nobody".
- Take before and after screens of every changed view.

### G. The closing review, from 06:00

- Five adversaries go over tonight's diff: the board, the graph, settings and keys, the practice ladder, and the claims.
- A skeptic reproduces each finding.
- Collect every finding before fixing any, and give each fix a test.
- Keys and conditions get the hardest look: a key must never reach a log, a prompt, a sandbox, a recording or the screen.

## What not to do

- No live call, no looking for credentials, no key read or printed, and nothing from a stand-in shown as live.
- No second source of truth: a view that keeps its own state is wrong.
- No knob without a decision saying who needs it.
- No claim that `field.md` forbids.
- No tag, PyPI release, Devpost entry, Pages switch, About text or repository setting: those are Alex's.

## The decisions that are yours

The board's design, the graph's views and when each shows, every setting and its default, the ladder's rungs, and which ideas get prototyped. Each goes in `DIRECTION.md` from 81, with its evidence.

## Commits and ground rules

- Commits are many and small: one logical change each, green before it is pushed, pushed after each milestone. Never pad.
- Work on branch `shaping`, cut from `main`, with one draft PR whose description stays current.
- Record the rollback SHA first. Move `docs/process/morning.md` to `morning-2026-09-26.md` and start a new one.
- Never push `main`, and never force-push.
- `~/.claude/settings.json` is Alex's. Keep the machine awake.
- Nothing leaves the machine except what Claude Code sends to do its work: this repo, the synthetic task repos, and the public repos you clone for lane B.

## The brief: the top of morning.md, and the only thing Alex reads at 08:00

Keep it current at every milestone, so that a run cut off early still leaves a true brief. At most twenty lines, and no paragraphs:

1. **Do first**, with the time each step takes: the key in `~/.zshenv`, the access check typed by him with `!`, and the first rungs of the ladder.
2. **New tonight:** five lines at most, each with the one command that shows it.
3. **Decide:** at most three questions, each with your default.
4. **Broken or risky:** three lines at most.

Below the brief goes everything else, as usual: decisions, evidence, screens, the state of every branch, and the rollback SHA.

## When to stop

- At 07:15, start nothing new.
- By 07:45, everything is merged into `shaping`, the suite and CI are green, and the brief is final.
- By 07:55, it is pushed.

A lane that is not done stops where it stands, with its state written down.

Now go. Make the moment before anything runs the best part of working with agents.
