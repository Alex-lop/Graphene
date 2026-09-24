# Graphene: the polish directive

*For the agent that runs on this repo next. Written 2026-09-24 with Alex, after he used `graphene watch` for real and after an outside review drove the same screen by keys at 80 and 120 columns. The three earlier directives in `docs/process/directives/` still hold; read them, `docs/DIRECTION.md` and this file before you touch anything.*

## Before anything else: what kind of run this is

Everything the earlier directives said about how to work holds: you are the strongest agent there is, there is no token budget and no clock, doubt your work and never your capacity, decide at every fork and write down why, keep `docs/process/morning.md` current at every milestone, push the branch green after each, leave one PR, and nothing waits on Alex.

But this run is a different kind of run, and the difference decides everything below.

The last three runs built mechanisms, and they are built: the boundary, the tree, the text form, the screen, the planner, the offers, the parallel run. Alex used the result and said it feels nice and needs polish in the commands, the logic and the display. **This run adds no mechanism.** It makes what exists feel finished, and the judge of finished is a person's eye and hand, not a count of findings. The last run spent 54 adversarial agents and a 78-finding review on the text parser and a third stand-in test that said no again; a person found a dozen rough edges in ten minutes at the screen. That is the lesson: for this product, at this stage, the only review that matters is sitting in it as the person.

So: no stand-in attention test this run. No adversarial swarm on the parser. No new commands unless one is the only way to remove a rough edge. Every hour goes to the screen, the messages and the logic a person meets, and every fix is verified by the fixed screen or the fixed transcript, before and after, in `morning.md`.

## What Graphene is, said once more, because polish has to know what it is polishing

Paragraph in, tree out, prune, run. The person types what they want, the way they always have. The agent proposes the tree: the goal at the root, sub-goals under it, leaves with the files they may touch and the command that shows they are done. The person reads it and cuts what they did not mean, in the terminal, with vim keys, and presses `R`. Executors do the leaves in parallel, each held to its scope and check; a leaf that needs more comes back with the fix already written, one key to take it. The person stays near the root and spends attention only where the agent's guess was wrong. Agent work gets cheaper every few months; attention does not.

Everything on the screen and in the messages should read as that, to someone who has never seen it. Where it does not, it is on this run's list.

## How to review this run

Sit in it. Build a real plan (the feeds task from `docs/proof/try.sh`, with real executors), and drive `graphene watch` through the WezTerm mux at 80×24 and at 120×36, the way Alex will: every key, every state a node can be in (proposed, open, waiting, running, came back, in review, done, yours), every pane, the help, the command line, the record, a `:ask`, a split, an undo. Read every message the CLI prints as the person or the agent who receives it, in the moment they receive it. Then fix what is ugly, confusing, redundant or wrong, and look again.

The list below is the seed of what to fix, not the ceiling. Everything on it was found by a person or by driving the screen for ten minutes; assume there is as much again that has not been found, and go find it the same way.

## The display

- **One row grammar, everywhere.** The tree rows are three ragged columns today: the title, `[id]` wherever the title happens to end, a state word; long rows overflow into a horizontal scrollbar and cut ids in half. Fixed columns: glyph, title truncated at a word with an ellipsis, id dim, state word; never a horizontal scroll in a tree. Decide the order once and use it in the screen, in `graphene plan` (which puts the id first today) and in the text form's comments, so a person reads the same line in all three places.
- **The goal is a row.** It is the root of the tree and the reason for everything under it. Today it is a truncated top bar with no ellipsis and no row. Make it the first row, folded like any other, its text wrapped or elided at a word.
- **The node pane has sections, and none of them is blank.** A sub-goal today shows its title, two empty lines and "1/2 done". Each kind of node gets a designed pane: a sub-goal shows its goal, its children with their states and what is waiting; a leaf shows why (the path to the root, short), contract, state, and what happened; a came-back leaf shows the reason and the offers first. No empty lines where content failed to render, no field twice ("running" appears twice on a running leaf today).
- **The record is a pane, not a paste.** Enter shows `node show`'s terminal text dumped into the widget: wrapped mid-word, backticks, commands spelled out twice. Lay it out: sections with aligned keys, wrapped at words, the commands in the status line when a key would run them rather than repeated in the text, and say that it scrolls.
- **The offers line up.** `w` and its command, `b` and its command, `?`: three rows, same shape. Today `w`'s command wraps onto its own line and `b`'s is missing.
- **The running leaf shows the executor.** Which executor, which worktree, the last thing it did and how many seconds ago, and `l` for the tail; when the executor was not started by `run` (a session holding the leaf), show what is known and say what is not, in one line, not by leaving fields out.
- **Colour means state, not alarm.** A leaf that came back is the loop working; it should not be the only red thing on the screen. Proposed, running, came back, review, done: one palette, used the same way in the tree, the pane and the status line.
- **The status line tells the truth.** "planner: claude:abc" today names whichever agent last proposed; if that is what it means, say it in words a person would use, or show what a person wants there: what is waiting on them, how many executors are running, what `R` would start. At 80 columns the second line is cut mid-word ("q q"); fit it.
- **Use the width.** At 120 columns half the screen is empty while the tree pane truncates. Give the tree what its rows need and the pane the rest; at 80 columns the pane below the tree is right, keep it.
- **Help is two columns and fits.** The overlay is right; it is a wall. Group it as the README does (move, shape, run, see, a leaf that came back, `:`), in two columns at 120 and one at 80.

## The commands and the logic

- **`parent:` places or is refused.** A proposal that says `parent: wire` is accepted today and lands at the root. Either the line places the node under `wire`, or the parser refuses it by line number as the README promises for any line it cannot honour. The same for every key the text form accepts: nothing is read and silently dropped.
- **The check's own leftovers never count.** `done` was refused because `python -m unittest` wrote `tests/__pycache__`, so in a Python repository without a `.gitignore` the first leaf fails `done` on its own check. What changed outside the scope is measured before the check runs; what the check creates is not the executor's change. Files git ignores never count either.
- **A person's commit is not a loose change.** Adding a `.gitignore` and committing it blocked every `start` until `plan ack`; a `git pull` would do the same. Loose changes are uncommitted writes nobody owned; a commit made by the person (or pulled) is the repository moving, and the plan follows it. Decide what `ack` still means after this and say it.
- **Refusals are short, structured, and said once.** "changed outside its scope (a, b): c. Put those back as they were (…), or say why the scope is wrong: (…). Only the person widens a scope, and only they decide a build leftover belongs in .gitignore" is four sentences where three lines will do: what was refused, the paths, the one or two commands. The same refusal never lectures twice in a session. Read every message in `plan_cli.py`, `run.py` and `gate.py` this way.
- **A command never tells you to run itself.** `start` on a waiting leaf prints "waits on xml-reader (running)" and then "`graphene node start wire-xml` takes it". The second line is for a different state; print the line for the state the node is in.
- **`next:` is one line.** A release prints a 500-character sentence naming every leaf and why it is not ready. Say what is ready or that nothing is, and that `graphene plan` has the rest.
- **`reopen` takes its note the way `release` takes its why**: an option with a clear name, or a prompt, never a usage box for a missing required option. Walk every command's required options the same way.
- **Which repository, on every write.** Already true for most; make it true for all, and make the screen's top line and the CLI's trailer say it the same way.

## The paragraph rule becomes a mode

Decision 28 works: the instruction at the prompt is what made a session propose a tree in 35 seconds instead of writing code in 48. Keep that. What does not hold is the gate: 240 characters, "just do it" and "no plan" read out of the person's prose. It is a heuristic about how Alex writes, it caused the hold in decision 40, and it costs eight lines of caveats in the README's "What does not bind."

Make it a state the person can see and set: on the status line, one key in the screen, one command outside it, on by default while a plan is in force, and the hook's instruction to propose first goes with the state, not with a character count. The one-line ask stays free: a proposal of one leaf made from the person's own prompt in their own session is theirs by construction (the hook saw them type it), and `leaf` prompts already say what that means. No rule reads the person's prose for length or for magic words, anywhere. Rewrite the README's caveats to match; they should get shorter.

## What not to do

- No new mechanism. If a rough edge seems to need one, write the smallest thing that removes the edge and say in `DIRECTION.md` what a real fix would be.
- No stand-in test. The measure this run is the screen and the transcript, before and after.
- No adversarial swarm. A test per fix, yes; a hunt, no.
- Do not touch the page.
- Do not re-word what already reads well. The README's opening and the hand-back copy in it are right; match them, do not replace them.

## The decisions that are yours

- The row grammar (id first or last), used everywhere.
- The palette.
- What the status line says at 80 and at 120 columns.
- How the record pane is laid out.
- What `ack` means once a person's commits no longer need it.
- The name and the key of the plan-first mode.

## The morning

`docs/process/morning.md`, current at every milestone:

1. Before and after. For each item above that changed the screen, the two screenshots (the mux at 80 and at 120); for each that changed a message, the two transcripts. This is the verification for this run, and it is what Alex reads first.
2. What he can run in five minutes, unchanged in shape from last time.
3. What is waiting on him, and the decisions to strike.
4. The map of the code, updated where the layout moved.
5. At most three questions, each only if it blocks the next step.

Then the rollback SHA and the state of every branch.

## Ground rules

Unchanged: nothing leaves the machine; `~/.claude/settings.json` is his; tags, PyPI and the name are his; `main` green at every stop; branch, green pushes, one PR; keep the machine awake; the rollback SHA first.

Now go. Sit in it as him, and make it feel finished.
