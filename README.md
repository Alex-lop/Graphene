# Graphene

![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)

A plan you and your coding agents share: you shape it, they are held to it.

I let agents work on my repos for hours. The way I steer them is a paragraph at the start and a diff
at the end. I type, I hope it was understood, and I find out later. That is a batch job, and after
enough of them you start to wonder why a person is there at all.

The person is there because agents carry out goals and do not own them. Who the software is for,
what "good" means in this codebase, what must never be touched: that is yours, and a paragraph is a
poor way to hand it over. Graphene gives you a better one. The work is cut into **nodes**. Each node
says what it should achieve, which paths it may touch, the command that shows it is done, what it
waits on, and whose it is: an agent's, or yours. You edit that plan before anything is spent, and you
change the next node when the last one finishes. The agents are held to it by mechanisms you can
name and test, not by asking nicely. For every node there is a record of what was really done.

```
$ graphene
the plan: 3 nodes, 1 done, 0 running
  slug   done      slug() turns a title into a url slug  agent  app/text.py     ·
  rate   open      set the rate                          alex   app/pricing.py  ·  ready
  price  waiting   price() uses the rate                 agent  app/pricing.py  ·  waits on rate (alex's)
waiting on a person: rate (yours to do)
```

![The same kind of plan in `graphene ui`: owners as lanes, what waits on you at the top, a node's contract on the right](docs/assets/plan.png)

## What works today

All of this runs in a terminal, and each line was shown on a real agent, not only in tests
([docs/proof/](docs/proof/) has three scripts you can run and their recorded output):

- **A write outside the node's scope is refused before it happens**, with the reason and the way
  out, in every permission mode and inside subagents. The agent was told, in the same breath as the
  plan, to fix a typo in a file no node covered. The file stayed byte-identical.
- **A node is done only when Graphene says so.** `graphene node done` runs the node's check itself
  and asks git what changed since the node was started. A change outside the scope keeps the node
  open however the file was written, and nothing that waits on it can start. This part needs no
  vendor: it held a Claude Code agent, a Codex agent and a person doing a node by hand.
- **You change the next node at the boundary and the agent honours it.** While the first node ran,
  the person rewrote the second (another file, another check). The agent, which had already read the
  old plan, did the new one: a node's contract is printed fresh when it is started.
- **An agent is held to a node it holds.** Its stop is refused until the node is done or handed
  back with a reason you can read. Claude Code lets a session end after about 8 refusals in a row;
  the node then stays `running` on the plan, where you see it.
- **You are in the graph.** A node can be yours. Agents cannot take it, what waits on it waits, the
  plan says "waiting on a person: rate (yours to do)", and before a run you are told which nodes
  agents can reach alone and which will wait for whom.
- **Refused work turns into a proposal.** Told no, the agent proposed a node for the typo with its
  own scope and check, and asked the person to accept, change or reject it. Agents propose; only a
  person accepts, edits a contract, signs off, reopens or overrules.
- **`graphene run` for when you are not watching.** Graphene takes each ready node, hands its
  contract and nothing else to the executor you name (`claude -p …`, `codex exec …`), and decides
  itself whether it is done, sending a refused executor back. It stops where a person is needed and
  says who.

What it is not yet: the map (`graphene ui`) shows the plan and lets you edit it, and it is a first
version; there is no worktree per node and no running nodes in parallel; the hooks exist for Claude
Code only (the boundary works for anyone). [docs/DIRECTION.md](docs/DIRECTION.md) has what
comes next and why.

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
- "Only a person" means someone at a terminal, and it rests on the environment. Inside an agent's
  shell the variable a script uses to speak for a person changes nothing. An agent that first strips
  its own markers and then sets it passes for a person, and the log shows that act as made with no
  terminal, which yours never are.
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
record only: no `plan`, no `node`, no `run`. They arrive there with 0.3.0.

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

In a repo with some work to do:

```
graphene node add "emails() returns lower-case emails" \
    --scope 'src/api/**' --scope 'tests/**' \
    --check "python3 -m unittest -q tests.test_users"
graphene node add "say what emails() returns" --scope docs/api.md --needs n1 \
    --check "grep -q lower-case docs/api.md"
graphene                 # the plan
graphene plan accept     # nothing to accept here, but it says what agents can reach without you
```

Or ask your agent to draft the plan: *"propose a plan for this: one `graphene node add` per node,
with a scope, a check and what it needs. Do not start it."* What an agent adds is a proposal, which
binds nobody and which nobody can start. Read it with `graphene plan`, change it with
`graphene node set n2 --scope … --check … --owner me`, drop what you do not want, then:

```
graphene plan accept
```

It answers with what agents can reach alone and what will wait for you. Now either tell the agent
in your session to *work the plan*, or leave:

```
graphene run
```

While a node runs you can still change any node that has not started; the change is what its
executor is told. When you come back:

```
graphene                 # where the work stands, and what is waiting on you
graphene node show n1    # its contract, who held it, what was refused, what the check said
graphene plan log        # everything that happened, oldest first
```

If a node is not what you wanted, `graphene node reopen n1 --note "return a dict, not a list"` sends
it back with your words. The note is a comment to whoever takes it next; the contract is what binds,
so when the note changes what is wanted, change the goal or the check too (`graphene node set n1
--goal …`), or a careful agent will hand the node back over the contradiction. A node that is yours you do like anyone else: `graphene node start rate`,
the work, `graphene node done rate`. A finished plan stays in force, so agents write nothing in the
repo outside a node, until you add a node, `graphene plan archive`, or `graphene plan pause`.

## The record

Everything Graphene built before the plan is still here, and from now on it serves it.

`graphene why src/app/auth.py:42` names the prompt, the agent and the task that wrote a line, and
how that is known.

![graphene why PATH:LINE](docs/assets/why-line.svg)

`graphene --session ID` prints the card of one session: what changed, what was tried and abandoned,
what was written outside the repo, and a coverage line that is never one number:

```
12 committed files · 9 traced to a recorded write (6 edit, 3 shell) · 2 only to an agent's commit · 1 to nothing
```

`graphene ui` opens the map in your browser, served to this machine only: the plan, and behind it
the record of a run as lanes of agents over rows of files, with the files nothing accounts for drawn
as such. `graphene ui --export FILE` writes the page as one file that opens offline; it carries
paths, counts, commit subjects, your prompts, each agent's task, your user name, and the plan itself
(each node's goal, scope and check, without its log), and no file contents, diffs or tool output. Read it before you send it. `graphene sessions` lists what is recorded. How each number
is computed, and where it can be wrong, is in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Privacy

- Nothing leaves your machine. Graphene calls no model and sends nothing anywhere. `graphene run`
  starts the executor you name, with the permissions you give it, and that is all.
- The store is `.graphene/` inside the repo: local, created `0700`, and it ignores itself in git
  (a `.gitignore` inside it), so your own `.gitignore` is never edited. On `init` Graphene also writes
  `.claude/settings.local.json` (or the `.claude/settings.json` an earlier version already put its
  hook in) and one line in `.git/info/exclude`. Graphene never commits, merges or pushes.
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
