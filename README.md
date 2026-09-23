# Graphene

![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)

Paragraph in, tree out, prune, run.

You tell your coding agent what you want, the way you always have: a paragraph. Before it writes a
line of code it shows you what it understood, as a tree. The goal sits at the top, then the
pieces of work under it, each with the files it may change and the command that shows it is done.
You read that, cut what you did not mean, and press `R`. Agents do the leaves in parallel, each in a
worktree of its own. A leaf that finds it needs more than you gave it comes back with the fix
already written: one key to take it.

I let agents work on my repos for hours. However many tokens you give an agent, it still has to
guess what you meant, and I found out what it guessed from the diff at the end. Graphene is where I
see the guess before anything is spent, and correct it with a keystroke instead of a restart.
Agent work gets cheaper every few months. My attention does not.

Two kinds of agent are involved. The **planner** is the session you talk to (or `graphene ask`); it
proposes the tree and writes no code. The **executors** are what `graphene run` starts, one per leaf;
each is held to its leaf's files and its check.

![graphene watch, at 80 columns](docs/assets/watch.gif)

## You are here

```
graphene                     where the work stands in this repository, and what waits on you
graphene watch               the tree on one screen: j k to move, y accept, d drop, R run, ? for the rest
graphene run --parallel 4    what is ready, at once, a worktree each, landed here as each passes
graphene node show <id>      why a leaf failed or came back, and what was really done for it
graphene plan edit           the whole plan as text, in your editor
```

Graphene works on the repository you are standing in, and every command that changes the plan
says which one.

## The first ten minutes

You need Claude Code, git, and a repository with some work to do in it: one of your own.
Install and set up the repository, once:

```
uv tool install git+https://github.com/Alex-lop/Graphene
cd ~/src/your-repo
graphene init
```

Open two panes in WezTerm: your agent on the left, the plan on the right (it reads best at 80
columns or more, so give the window room). In the pane you are in:

```
wezterm cli split-pane --right --percent 50 --cwd "$PWD" -- graphene watch
claude
```

(To have it on a key, add this to the `keys` in your `~/.wezterm.lua`:
`{ key = 'g', mods = 'CMD|SHIFT', action = wezterm.action.SplitPane { direction = 'Right', size = { Percent = 50 }, command = { args = { 'graphene', 'watch' } } } }`.)

Now say what you want, on the left, in a paragraph. On the 22nd I typed this about a small loader:

> Look at this repo. I want the new Northwind XML feed to load the same way csv and json already
> do: same load command, same JSONL out. Prices in that feed are already in cents. The summary line
> at the end is not a product. A price of 0 means skip it, for every supplier. Don't touch vendored
> or legacy files that aren't ours this week.

Graphene asks the agent to plan a paragraph before it writes anything, and holds its writes until
you have accepted the tree and a leaf of it is taken. On the right, a tree
appears, every line marked `?`: a proposal. The agent also says what it could not settle. That run
flagged that the legacy importer skips the zero-price rule, which I had just told it not to touch.
That is a misunderstanding caught before any code, and exactly what the tree is for. A single line
("fix the typo in the header") is still just done (with a plan in force, it is on the plan as a leaf
with a record of what it touched). "just do it", "do it now" or "skip the plan" in a paragraph skip
the tree, and so does a paragraph that names a ready leaf or carries the CLI's `--scope`.

Prune it on the right:

- `j` `k` move, `za` folds, `Enter` shows everything about a node.
- `d` drops a leaf you did not mean. `e` opens its contract in your editor. `E` opens a whole
  subtree as text. `a` adds a line, and `s` asks the planner to split a leaf.
- `y` accepts. `V`, a few `j`, then `y` accepts several.
- `R` runs everything that is ready.

Leaves light up as executors take them. The node pane shows which executor, in which worktree, what
it did last and how many seconds ago; `l` shows its output. Each leaf lands on your branch as a merge
when its check passes and it touched nothing outside its files. If a leaf comes back, the node pane
says why and what it wanted outside its scope, and offers the fix:

```
came back: USAGE lives in cli/main.py (line 18), outside scope. Enabling xml in config makes
tests/test_contract.py fail until USAGE names xml, so the done check cannot pass without cli/main.py.
  w  widen wire-xml's scope to cli/main.py   graphene node widen wire-xml
  b  a sibling leaf for cli/main.py; wire-xml waits on it   graphene node sibling wire-xml
  ?  ask the planner, when neither is right
```

Press one of them, then `R` again. When it is all done, `git log --graph` reads as the tree: one
merge per leaf, with its why in the message.

Everything the keys do is a command you can type yourself; the bottom line of the screen says which
command each key just ran. Agents and scripts use the same commands. `graphene watch --once` prints
the plan instead of taking the screen.

## What works today

Each of these was run for real on the feeds task. The executors were Claude Code agents, not
tests of Graphene's own:

- **A paragraph becomes a tree before any code.** The paragraph above, typed into a Claude Code
  session in a fresh copy of that repository with the hooks installed: 35 seconds, four leaves under
  three sub-goals, `needs` set between them, and no file touched. Before Graphene asked for the tree
  at the prompt, the same paragraph got its code written straight away, in 48 seconds. (One run of
  each, 23 September.)
- **The tree runs in parallel and lands.** Accepted as proposed, `graphene run --parallel 4` did all
  four leaves in 50 seconds, each a merge on the branch. The result passes 18 of the task's 20 hidden
  acceptance checks (the 2 it misses want something the paragraph never said) and 12 of its 12
  held-out checks, against 10 and 0 for the repository as it was. (One run.)
- **`graphene ask "<what you want>"`** plans without a session. The planner has read-only tools and
  none of your MCP servers, and what it prints becomes the proposal. On the same paragraph: 44 seconds, seven nodes, first try.
- **Ctrl-C hands back what the run started**, in place and in worktrees, and stops its executors.
  The next run takes those leaves again.
- **Hand-backs offer their fix** (`w`, `b`, and waiting on the leaves the reason names).
- **The plan as text round-trips.** `graphene plan edit` applies what you changed and nothing else,
  in one transaction. A line it cannot read is refused by its number, with what to do. 54 adversarial
  agents tried to break it: what they found is fixed, and each finding has a test.

What it is not yet: the hooks are for Claude Code only (the plan, `run` and the worktrees work with
any executor that has a shell); the page (`graphene ui`) shows the tree and is otherwise as it was.
[docs/DIRECTION.md](docs/DIRECTION.md) has what was decided, why, and what comes next.

## What does not bind

A control you cannot trust is worse than none, so here is where each one ends.

- "A paragraph becomes a tree" is a rule about length (240 characters). A long request you meant to
  have done at once needs "just do it" in it. A short one that deserved a plan is done at once; with
  a plan in force it is on the plan as a leaf made from your prompt, and with none it leaves no trace.
- Tools that write through an MCP server (a document, a ticket, a message) are seen neither by the
  paragraph's wait nor by a leaf's scope: the hooks read Claude Code's own write tools and the shell.
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
  carries none is taken for you. An agent that strips its marks, or one from a vendor that sets none,
  passes for a person; the log marks every act made with no terminal.
- A request typed into a session is taken as yours, and so is a "yes". An agent that starts another
  agent writes its prompt. The log names every leaf made from a prompt and every acceptance made by
  one. A leaf made from a one-line prompt with no `--scope` may touch anything (never the plan's
  store or the hooks' settings): it is a record, not a fence.
- During `graphene run --parallel`, a change you make by hand in the checkout it merges into can
  make a leaf wait or keep it from landing. It is sent back or waits for you; nothing is lost.
- The plan's store is a file in your repo that git ignores. The hook refuses commands that name it;
  a script that opens it directly is neither stopped nor noticed.

## Install

```
uv tool install git+https://github.com/Alex-lop/Graphene
```

`uv tool install graphene-map` installs the last release on PyPI, 0.2.0, which is the record only:
no plan, no watch, no run. Then, once per repository, inside it, `graphene init`. That adds
Graphene's hook to `.claude/settings.local.json` (yours, not the team's `settings.json`) and keeps
the file out of `git add` through `.git/info/exclude`. The hook holds agents to the plan and keeps
the record; the agent waits about 40 ms for it on each tool call. Graphene never edits your own
`~/.claude/settings.json`.

## The record

`graphene node show <id>` prints a node's contract and then what was really done for it:
- who held it and when;
- what git says changed and whether that was inside its scope;
- what was refused;
- what Graphene's own run of the check said;
- the commits made while it was held.

Every line names the record it was read from. A count that nothing supports says `not computed`, and
why. `graphene ui` is the plan and that record as a page in your browser, served to this machine
only; how each number is computed is in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Privacy

- Nothing leaves your machine. Graphene itself calls no model and sends nothing anywhere. `graphene
  run` and `graphene ask` start the executor or planner you name, with the permissions you give it.
- The store is `.graphene/` inside the repo: local, created `0700`, and it ignores itself in git.
  Graphene never pushes. It commits and merges only in `graphene run --parallel`, on
  `graphene/<leaf>` branches of its own, merged into the checkout you started it from when the merge
  is clean.
- Delete `.graphene/` to forget everything, the plan included.

## Requirements

macOS or Linux, [uv](https://docs.astral.sh/uv/), Python 3.12 or later (uv fetches it), and git. The
screen (`graphene watch`) is [Textual](https://textual.textualize.io/) and works in any modern
terminal; it was checked in WezTerm at 80 columns. The hooks are for Claude Code.

## License

Apache-2.0.
