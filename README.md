# Graphene

![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)

A plan you and your coding agents share. You say why; they work out how, in parallel, while you do
something else; and you still know why every piece was done.

I let agents work on my repos for hours. The way I steered them was a paragraph at the start and a
diff at the end. That is fine for a change I can watch. It stops working when the job is too big for
a paragraph to name the files, when I am not there, or when it is Tuesday and the paragraph I type
is not a careful one. Agent work gets cheaper and better every few months. My attention does not.
So Graphene spends theirs to save mine.

The plan is a **tree**. The root is the goal, in your words. Under it are sub-goals, and under those
the **leaves**: pieces of work someone will do, each with the paths it may touch and the command
that shows it is done. You stay near the root. The agents propose the branches and fill in the
leaves, and you prune: accept a subtree, split a leaf, drop what you do not want, change the next
leaf while another runs. Every agent that takes a leaf is told the path from the goal down to it,
which is the one thing a paragraph cannot carry past the first turn. Ready leaves run at the same
time, each agent in its own worktree, and land on your branch as they pass. For every leaf there is
a record of what was really done.

```
$ graphene
the plan: a toy service whose listings are safe to show to a customer
3 leaves, 2 done, 1 running
  clean     done      the listing functions return clean values  agent                 ·  2/2 done
    emails  done      emails() returns lower-case emails         agent  src/emails.py  ·
    names   done      names() returns upper-case names           agent  src/names.py   ·
  readme    running   say what the two functions return          agent  README.md      ·  run:claude since 05:50Z
```

`graphene watch` is that, live. `graphene ui` is the same plan in a browser.

![The plan in `graphene ui`](docs/assets/plan.png)

## What works today

Each of these was shown on real agents, not only in tests. [docs/proof/](docs/proof/) has the
scripts, which you can run, and what they printed.

- **Two agents at once on one tree** (`docs/proof/parallel.sh`, about 30 seconds). `graphene run
  --parallel 2` gave two leaves a worktree each, both agents worked at the same time, each leaf
  landed on the branch as a merge with its why in the commit message, the sub-goal above them was
  done only when its own check passed on the merged result, and the leaf that waited on it started
  then.
- **A plan in force costs nothing on a small job** (`docs/proof/tuesday.sh`). With a plan in force
  you type an ordinary request into your session, the same words you would have typed without
  Graphene. The agent does it. The request is on the plan as a leaf with a record of what it
  touched, and you ran no command. Write the CLI's own flags, `--scope 'src/db/**' --check 'make test'`, in the request and
  those bind it like any leaf. When an agent proposes something, "yes" in the session accepts it.
- **A leaf is done only when Graphene says so.** `graphene node done` runs the leaf's check itself
  and asks git what changed since the leaf was started. A change outside the scope keeps it open
  however the file was written, and nothing that waits on it can start. This needs no vendor: it
  held a Claude Code agent, a Codex agent and a person doing a leaf by hand.
- **Done rolls up, and integration has a place to live.** A sub-goal can carry a check of its own.
  It runs when the leaves under it are done and together, and until it passes, what waits on the
  sub-goal waits.
- **While an agent holds a leaf, a write outside its scope is refused before it happens**, with the
  reason and the way out, in every permission mode and inside subagents. Its stop is refused until
  the leaf is done or handed back with a reason you can read.
- **You change the next leaf while this one runs, and the agent honours it.** A leaf's contract is
  printed fresh when it is started.
- **You are in the tree.** A leaf can be yours. Agents cannot take it, what waits on it waits, and
  the plan says so first: "waiting on a person: rate (yours to do)". Before a run you are told what
  agents can reach alone and what will wait for whom.
- **A leaf too big to do gets split, by the agent.** It proposes children under the leaf and hands
  it back; you accept the subtree or prune it. Agents propose. Only you accept, edit a contract,
  sign off, reopen or overrule.

What it is not yet: the hooks exist for Claude Code only (the boundary, `graphene run` and the
worktrees work for any executor with a shell); the live view is a print that redraws, not an
interface with keys; the page shows the tree and is otherwise as it was.
[docs/DIRECTION.md](docs/DIRECTION.md) has what was decided, why, and what comes next.

## What does not bind

A control you cannot trust is worse than none, so here is where each one ends.

- A shell command can write a file in a way nothing reads beforehand (a script that opens files
  itself). The hook refuses the forms it can parse (`>`, `>>`, `tee`, `sed -i`, `mv`, `cp`, `rm`).
  The rest is caught at `done`, by git; until then the stray change is on disk.
- A file made outside the scope and moved out of the repo before `done` is invisible to git. It is
  caught when it comes back, as a change no node owned, and the next node will not start over it.
- Claude Code lets a session end after about 8 refused stops in a row. The node then stays `running`
  on the plan, where you see it. `graphene run` has no such ceiling.
- A hook that crashes or times out lets the call through. That is the vendor's rule. The boundary
  does not depend on the hook.
- "Only a person" rests on the environment: an agent's shell carries its vendor's marks, and whoever
  carries none is taken for you, with or without a terminal. An agent that strips its marks, or one
  from a vendor that sets none, passes for a person; the log marks every act made with no terminal.
- A request typed into a session is taken as yours, and so is a "yes". An agent that starts another
  agent writes its prompt. The log names every leaf made from a prompt and every acceptance made by
  one. A leaf made from a prompt with no `--scope` may touch anything (never the plan's store or the hooks' settings): it is a record, not a fence.
- During `graphene run --parallel`, a change you make by hand in the checkout it merges into can
  make a leaf's `done` refuse (it sees a change it cannot account for) or keep it from landing. It
  is sent back or waits for you; nothing is lost.
- The plan's store is a file in your repo that git ignores. The hook refuses commands that name it;
  a script that opens it directly is neither stopped nor noticed.
- What git ignores, nobody audits. The gate asks git about every working tree of the repo, not
  about a copy of it somewhere else.

## Install

From GitHub, which is where the plan is:

```
uv tool install git+https://github.com/Alex-lop/Graphene
```

`uv tool install graphene-map` installs the last release on PyPI. Today that is 0.2.0, which is the
record only: no `plan`, no `node`, no `run`. They arrive there when 0.4.0 is released.

Then, once per repo, inside it:

```
graphene init
```

This adds Graphene's hook to the repo's `.claude/settings.local.json` (yours, not the team's
`settings.json`; if an earlier version put it in `settings.json`, it is upgraded there, and a repo
set up before 0.3 gets the one new event, `PreToolUse`, added). The hook does two jobs: it holds
agents to the plan, and it keeps the record. Each time it runs, before and after every tool call,
the agent waits about 40 ms for it (measured in the test suite). It keeps that file out of `git add` through
`.git/info/exclude`, never through your `.gitignore`. When your own `~/.claude/settings.json` does
not yet make Claude Code record which files each shell command changed, `init` prints the one line
to add there; Graphene never edits that file.

## The first ten minutes

In a repo with some work to do, say what it is for and ask your agent for the tree:

```
graphene plan goal "customers can download their invoices as PDF"
```

Then, in your agent session: *"Propose a plan for this goal with `graphene plan propose -`: sub-goals
with leaves under them, each leaf with a scope and a check. Do not start it."* What an agent adds is
a proposal. It binds nobody and nobody can start it. Read it and prune it:

```
graphene                                  # the tree; what waits on you is first
graphene node set pdf --scope 'src/pdf/**' --check 'pytest tests/pdf'
graphene node add "the template" --parent pdf --scope 'templates/**' --check 'make lint' --owner me
graphene node drop emailing               # with everything under it
graphene plan accept                      # or one subtree: graphene plan accept pdf
```

`accept` answers with what agents can reach alone and what will wait for you. (Or type "yes" in the
session.) You can also build the tree by hand: `graphene node add "the API" --id api` is a sub-goal,
and `graphene node add … --parent api --scope … --check …` is a leaf under it.

Now either tell the agent in your session to *work the plan*, or leave:

```
graphene run --parallel 3       # ready leaves at once, a worktree each, merged here as they pass
graphene run                    # or one at a time in this checkout, committing nothing
graphene watch                  # the tree, live, from another terminal
```

While a leaf runs you can still change any leaf that has not started; the change is what its
executor is told. When you come back:

```
graphene                 # where the work stands, and what is waiting on you
graphene node show pdf   # why it exists, its contract, who held it, what was refused, what the check said
graphene plan log        # everything that happened, oldest first
git log --graph          # with --parallel: one merge a leaf, its why in the message
```

If a leaf is not what you wanted, `graphene node reopen n1 --note "return a dict, not a list"` sends
it back with your words. The note is a comment to whoever takes it next; the contract is what binds,
so when the note changes what is wanted, change the goal or the check too (`graphene node set n1
--goal …`). A leaf that is yours you do like anyone else: `graphene node start rate`, the work,
`graphene node done rate`. If a parallel leaf could not be merged because your own work was in the
way, it waits in `review` on its branch and the plan tells you the two commands that finish it.

A finished plan stays in force until you `graphene plan archive` or `graphene plan pause`. That no
longer gets in your way: what you ask for in a session is done and recorded as a leaf of its own.
`graphene plan prompts strict` brings back the older rule, under which a session that holds no leaf
writes nothing and has to propose.

## The record

The record hangs off a node. `graphene node show n1` prints its contract and then what was really
done for it: who held it and when, what git says changed under it and whether that was inside its
scope, what was refused, what Graphene's own run of the check said, and the commits made inside its
windows. Every line names the record it was read from, and a count nothing supports says `not
computed` and why instead of showing a number.

```
coverage: of the 3 paths git said had changed under this node, 3 inside its scope; 2 to a recorded
edit, 0 to a recorded shell command, 1 to git alone
  read from: the node's log, git, and Claude Code's records for session 4f2a91c7
  check: `uv run pytest -q` passed at 2026-09-21T02:14:08.112Z, run by Graphene itself
```

None of that needs a vendor. A node done by Codex, by `graphene run --with <anything>` or by you at
the terminal gets the same line, read from the node's log, git and the check; where Claude Code's
hooks were running they add which path traces to a write somebody recorded making, and where they
were not, the line says so rather than reporting nothing.

`graphene ui` opens the map in your browser, served to this machine only: the plan, and behind it
the record of a run as lanes of agents over rows of files, with the files nothing accounts for drawn
as such. `graphene ui --export FILE` writes the page as one file that opens offline; it carries
paths, counts, commit subjects, your prompts (every request that became a leaf is on the plan in your words, as its title and goal), each agent's task, your user name, and the plan itself
(each node's goal, scope and check, without its log), and no file contents, diffs or tool output. Read it before you send it. The page's own rail lists the sessions that are recorded. How each number
is computed, and where it can be wrong, is in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Privacy

- Nothing leaves your machine. Graphene calls no model and sends nothing anywhere. `graphene run`
  starts the executor you name, with the permissions you give it, and that is all.
- The store is `.graphene/` inside the repo: local, created `0700`, and it ignores itself in git
  (a `.gitignore` inside it), so your own `.gitignore` is never edited. On `init` Graphene also writes
  `.claude/settings.local.json` (or the `.claude/settings.json` an earlier version already put its
  hook in) and one line in `.git/info/exclude`. Graphene never pushes. It commits and merges in one
  case only: `graphene run --parallel`, on `graphene/<leaf>` branches of its own, merged into the
  checkout you started it from when the merge is clean.
- Transcripts can contain secrets, so files outside the repo are recorded by path only, the content
  a `Read` call returned is not stored, and any output or input string over 8 KB is kept as its
  first and last 4 KB.
- Delete `.graphene/` to forget everything, the plan included. Graphene rebuilds what the
  transcripts still hold next time.

## Requirements

macOS or Linux, [uv](https://docs.astral.sh/uv/) to install it, Python 3.12 or later (uv fetches it
if needed), and git. The hooks are for Claude Code; the plan and its boundary work with any executor
that has a shell.

## License

Apache-2.0.
