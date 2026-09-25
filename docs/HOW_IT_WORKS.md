# How Graphene works

Graphene keeps a plan that a person and their coding agents share, holds executors to it, and
keeps a record of what was done for each node. No model decides anything here: the plan, the boundary
and the record are computed from the plan's own rows, from git, and from what the executors record. A
model is called only by the planner and the executor you name, Graphene's Nemotron ones included
(P4b).

Part one is the plan and what makes it bind. Part two is the record underneath it.

# Part one: the plan

## P1. Nodes

A node is one JSON document in the repo's store (`.graphene/graphene.db`, table `nodes`): an id, a
title, a goal, a **scope** (globs: `**` crosses directories, `*` and `?` stay inside one level, a
plain name with no wildcard covers what is beneath it, `!glob` takes paths back out, the last match
decides, and git's spelling of a path is the one that counts, upper and lower case included), a
**check** (a shell command), whether a person must **sign it off**, what it **needs** (other node
ids), an **owner** (`agent`, meaning any agent, or a person's name) and a state:

| State | Means |
| --- | --- |
| `proposed` | an agent suggested it; nobody can start it and it binds nobody |
| `open` | in the plan; "ready" when everything it needs is done, "waiting" otherwise |
| `running` | someone holds it: who, since when, in which checkout, from which commit |
| `review` | its check passed and it waits for a person's sign-off; what needs it still waits |
| `done` | finished |
| `dropped`, `archived` | taken out, or put away by the person; no longer part of the plan |

Every change to a node is a row in `node_log` with who made it: `graphene plan log` prints it all,
`graphene node show <id>` one node's. A plan is **in force** while any node is open, running, in
review or done, and the person has not paused it. Done counts on purpose (see P3).

Who may do what. Anyone may propose and start a node they are allowed to take; only whoever holds a
running node finishes it or hands it back (a Claude Code session is known by its session id, an
executor `graphene run` started by the node it was given, anyone else by the name they took it
under; a person always may). Only a person may accept a proposal, edit a contract, sign off, reopen, overrule
the gate, pause, archive, or acknowledge loose changes. "A person" is a caller without an agent's
mark: Codex exports `CODEX_SESSION_ID`, Claude Code `CLAUDECODE` and `CLAUDE_CODE_SESSION_ID`,
`graphene run` gives every executor `GRAPHENE_NODE`, and a mark outranks everything. A caller with
no mark and no terminal (an editor task, a pipe) is still the person, and the log says `(no
terminal)`: a person's `add` must never turn into a proposal they cannot accept. An agent of a
vendor that sets none of these marks is therefore taken for the person. A script that
stands in for a person sets `GRAPHENE_AS=person:<name>`; inside an agent's environment that variable
changes nothing, however it is spelled, and every act made through it is logged as made with no
terminal (`alex (no terminal)`). The one exception is `graphene watch`, which sets `GRAPHENE_WATCH=1`
on the commands the person types there when its own input is a terminal; an agent's command that
carries it is refused by the hook, the same way `GRAPHENE_AS` is. `graphene ui` gives its page the person's rights only when a person
started it.

## P1a. The tree

The plan is a tree. Its **root** is one sentence of the person's, `graphene plan goal '…'` (kept in
the store's `meta`, not as a node): why any of this is being done. A node's `parent` names the node
it helps achieve; no parent means directly under the root, which is what every node from 0.3 is.
A node with children is a **sub-goal**: it needs only a title, nobody takes it, and its row shows
`n/m done` over the leaves under it. A node without children is a **leaf**: the work, with a scope
and a check as above. A title with nothing else is a sub-goal whose children are still to come.

Hierarchy is meaning and `needs` is order, and both are kept. A leaf waits on what it needs *and*
on what every node above it needs. A cycle through needs, through the tree, or through both (a leaf
that needs its own sub-goal) is refused when the plan is edited.

**Done rolls up** (`plan.roll_up`). When the last child of a sub-goal is done, the sub-goal's own
check, if it has one, is run by Graphene on the checkout where the children's work is together (in
a worktree of its state, as a leaf's is: P2 step 3); that is where integration lives. Passing (or
having no check), the sub-goal is done, or in `review` if it asks for a sign-off, and what needs it
can start. Failing, it stays open, the log has the output, `graphene plan` says "its leaves are done
and its own check fails", and the way on is a leaf under it for what is missing; `graphene node done
<sub-goal>` runs the check again. A child added or reopened under a finished sub-goal reopens it.

**A proposal is a subtree.** `graphene plan propose` reads the plan's text (P1c; JSON with nested
`"children"` is still read), and a line with the id of a node already there is where new lines hang. Accepting a node accepts every proposal under it and every proposal
it sits under. A leaf too big to do is split by proposing children under it and handing it back
(children cannot be accepted under a leaf someone holds); dropping the children makes it a leaf
again; dropping a sub-goal drops what is under it, unless something outside waits on any of it.

**The path to the root is told to every executor.** `plan.trail` is the goal and then each sub-goal
above the leaf, with its own goal; `plan.contract` prints it as `why:` lines above the leaf's goal.
`graphene node start`, `graphene node show` and the prompt `graphene run` hands over all use it.

**In the terminal** (`plan_cli.plan_lines`): the goal, a count of leaves, what waits on you (a
proposed subtree is asked about once, at its top; a leaf that came back, one in review, one of
yours), then the tree indented by depth, one row a node: glyph, title cut at a word, id, and the
word its state reads as (`plan.reads`: proposed, ready, waiting, running, came back, review, done,
yours, to fill in; a sub-goal reads `2/3 done`), then what the print adds (scope, what it waits on,
the command that is the person's). Once it is longer than a dozen lines, finished nodes fold into
one `✓ n done here` line per level; `--all` unfolds. `graphene watch` is the same plan on one screen
(`tui.py`, Textual): the goal as the first row, the tree in the same rows and colours (`plan.look`:
the colour says whose move it is), a pane for the node under the cursor laid out by kind, vim keys,
every key a `graphene` command, which the bottom line names: run in its process, or, for what takes
time (`run`, `ask`, `node split`, `node done`, `node signoff`), in a process of its own. It polls
the store once a second; a store too busy to open leaves the screen as it was and says so; `--once`
prints `plan_lines` instead. The text form's `#` notes say a node's state in the same words. A
subtree whose leaves are all done is folded, when the screen opens and when it finishes; a tree
still taller than its pane (`tree_room`: at 80x24 the ten rows above the node pane) opens as its
outline, each sub-goal one row, and a sub-goal that arrives in such a tree while the screen is open
comes in folded, while what the person opened stays open. A leaf with a proposal under it is a leaf:
it stays open, and a count counts it. A folded row keeps the grammar, and its word is what is inside
(`tui.inside`): how many leaves in which states, whose move first, as many whole states as fit 20
columns and the rest counted (`1 came back, 4 more`, `6 done`). `za` `zo` `zc` `zR` `zM` are vim's;
`zx` puts the folds back as the screen opened them.

## P1c. The plan as text

`plan_text.py`. One line a node: `- title  [id]` is in the plan, `? title  [id]` a proposal;
indentation is the tree; under a node's line, at one column, `scope:` `check:` `needs:` `owner:`
`signoff:`, `parent: <id>` (puts the node under that one, in the text or the plan, and is refused by
its line when it names none or disagrees with the indentation), `id:` (the node's id, when the line
has no `[id]`) and any other line (what it should achieve); `title:` and `children:` are refused by
their line (the title is the node's line, children are indentation), never swallowed as prose. `#`
lines are notes Graphene writes and never reads. `render` writes a plan (or a subtree, or one node) so that `parse` reads it back as it is, and
`apply` makes the plan say what a text says, as the operations `plan.py` already has (add, edit,
accept, drop, reorder) in one transaction. A text that was opened is compared three ways: only what
the person changed against the text as it was opened is changed, and a node someone else changed
meanwhile is refused (its line named) rather than written over. A line that fits nowhere is refused
by its number with what to do, never given to a node it was not written under; an edited text is
read strictly (a key written twice, or words after a node's keys, are what a deleted node line leaves
behind). From an agent (`propose`) only new lines count, every one a proposal, and a new leaf needs a
scope or a check. `graphene plan edit [id]` and `graphene node edit <id>` open it in `$EDITOR` (a
file of its own under `.graphene/edits/`); a refused save goes back to the editor with the reason
under its line. `graphene plan undo` puts back the person's last act (snapshots of the rows it
changed, kept in the store; refused when something it touched moved on since).

## P1b. A request typed into a session

With a plan in force, the `UserPromptSubmit` hook remembers the session's latest prompt. When that
session holds no node and is about to write (`PreToolUse`), Graphene makes a leaf from the prompt
and starts it for the session: title and goal are the person's words; its scope and check are what
the CLI's own flags when they typed them into the prompt (`--scope 'src/db/**'`, repeatable, and a
quoted `--check 'make test'`), and otherwise `**` and no check. (The first spelling was `scope:` and
`check:` anywhere in the text; a review typed "double check: ./deploy.sh is never called" and the
script ran.) A prompt that names a leaf that is ready makes no leaf: that one is there to be taken. A
leaf made from a prompt never reaches `.graphene/` or the hooks' own settings file. Nothing is
inferred from the prose. At `Stop` the leaf closes (`plan.close_aside`): git says what changed, the
check runs if there is one (failing, the stop is refused with its output), and a leaf under which
nothing changed is dropped. It is a record rather than a gate: it does not run the looks at other
worktrees that `done` runs. A session that holds a planned leaf is held to it as before; an executor
`graphene run` started never gets such a leaf; `graphene plan prompts strict` turns them off.

**Plan first** is a setting of the person's (`graphene plan first on|off`, `P` in `graphene watch`;
`graphene init` sets it on, and never set it is on while a plan is in force; `plan.plan_first`). On,
a session that holds no leaf is told beside every prompt to propose what it will do in the plan's
text before it writes, a piece of work as a tree the person prunes and a one-line ask as one leaf,
and its writes (and the commands that reach round `graphene`) are refused until it holds a leaf; the
refusal says how the person turns it off (`gate._first_refused`). One leaf with a scope and a check,
proposed by a Claude Code session after the person's last prompt there and before any other
proposal of that session since, is what that prompt asked for: it is accepted at once, as the
person's, logged "by their prompt in the session" (`gate.one_line_ask`); a tree waits for them. A
prompt that types the CLI's own `--scope` and a quoted `--check` has planned its leaf, which is made
at its first write. Off, what decision 18 says above holds. Nothing reads the person's words to
decide any of this: not their length, not "just do it", not "yes". What the vendor sends as a prompt
on its own (a finished background task, a reminder, a slash command) is never the person's.

A `--check` that fails refuses the stop once, with its output; asked to stop again, the leaf closes
and its record says the check failed. A session is never trapped by it.

## P2. The boundary: what makes a node done

`graphene node start <id>` refuses unless the node is open, everything it needs is done, the caller
may take it, no running node in the same checkout claims a path it claims, and nothing has changed
in the checkout while no node owned it (below). It then records `HEAD`, and every path git calls
modified, staged, deleted or untracked **with a hash of its content**, and prints the contract as it
stands at that moment. That last part is how a person's edit to the next node reaches an agent that
read the plan an hour ago.

`graphene node done <id>` is the gate, and Graphene runs all of it:

0. It checks that git can still answer: a path marked `assume-unchanged` or `skip-worktree`, or an
   edit to the clone's `.git/info/exclude`, since the node was started is refused by name.
1. It asks git what differs from the start: `git diff --name-only <start HEAD> HEAD`, plus
   everything dirty now, minus paths whose content hash is what it was at the start. So committing a
   stray change does not hide it, and a file that was already dirty is held against the node only if
   it changed again (an agent that wipes your uncommitted edit is caught). Paths inside the scope of
   a node that ran beside this one in the same checkout are that node's, not this one's.
2. Any path left that the scope does not cover: refused, with the list. So is a changed path that
   is a symbolic link out of the repo, and so is a path changed in any *other* working tree of the
   repo since the node was started (a worktree made later is compared with the commit the node
   started from). The worktrees of `graphene run --parallel` are not asked: each one's leaf answers
   for it at its own `done`. The node stays `running`.
3. It runs the check (30 minute cap, the making of its worktree included) and keeps the tail of the
   output in the log. Non-zero: refused. The check never runs in the checkout itself
   (`plan.run_check`, the one place a check is run). Graphene commits the node's state as git sees
   it, committed or not (what git tracks, as it is on disk, and the new files git does not ignore),
   on no branch; cuts a worktree from that commit under `.graphene/worktrees/`, running none of your
   git hooks; runs the check there; and removes the worktree however the check ends, a timeout, a
   Ctrl-C or a stopped run included, with everything git or the check started. So nothing the check
   writes (a cache, a coverage file, an edit, a `.venv`) lands in the executor's tree, is counted as
   its change, or is committed with its leaf. What git ignores (a `.venv`, `node_modules`, `.env`) is
   not in that worktree: the check makes its own environment (`uv run` makes a `.venv` there from
   uv's cache, in under a second for this repository). When the only paths step 2 found are new
   untracked files, the check runs without them, and what it makes again (the `__pycache__` an
   executor's own test run left, in a repository with no `.gitignore`) is the check's: it stays in
   the checkout as the executor left it, it is not counted, and it is left out of what the leaf's
   commit takes. The rest are refused as in step 2. A sub-goal's check (P1a) and a prompt leaf's
   (P1b) run the same way.
4. If nothing inside the scope has changed at all, it is not done either: a check that already
   passed shows nothing (an executor that crashed at once was once reported done this way). An
   executor with nothing to do hands the node back and says so.
5. Otherwise the node is `done`, or `review` when it needs a sign-off; what git said had changed,
   and the `HEAD` it ended at, go into the log for the node's record; and the tree as it stands is
   remembered as this checkout's **boundary**.

Between nodes nobody owns the repo. An uncommitted change that differs from the last boundary at
the next `start`, outside the scope of every node started since, is a change no node owned: an
agent's `start` is refused until it is put back, a person sees it on `graphene plan` and makes it
theirs with `graphene plan ack` (or by committing it). A commit is not such a change: it is the
repository moving (a `.gitignore` of yours, a `git pull`), and the plan follows it. This exists
because a real agent did exactly that (next section).

A person can overrule the gate with `graphene node done <id> --override "reason"`; the log keeps the
reason, the stray paths and whether the check had failed. `graphene node release <id> --why "…"`
hands a node back unfinished, and `graphene node reopen <id> --note "…"` sends a finished one back
with the person's words, which the next executor is shown.

None of this involves a vendor. On 2026-09-20 the same gate refused, and then accepted, a Claude
Code agent, a Codex agent (`codex exec`) and a person editing by hand.

## P3. What the Claude Code hooks add

`graphene init` registers one command, `graphene ingest hook`, on eight events. With a plan in
force it answers as well as records (`src/graphene_map/hooks.py` records, `gate.py` answers), in
the vendor's documented JSON:

| Event | Answer |
| --- | --- |
| `PreToolUse` on `Edit`, `Write`, `MultiEdit`, `NotebookEdit` | a path outside the scope of the node(s) this session holds is **denied**, with the reason and the way out; a session that holds no node is denied every write in the repo and told to take a node, or to propose one. Inside the scope it says nothing, so your own permission rules still apply. Paths outside the repo are not the plan's business. |
| `PreToolUse` on `Bash` | the writes the shell parser can read (`>`, `>>`, `tee`, `sed -i`, `mv`, `cp`, `rm`, `touch`, following `cd`) are checked the same way, links resolved first; a target git ignores passes; a command that mentions `GRAPHENE_AS` or reaches into `.graphene/` is denied whatever the scope; a command over 64,000 characters is not parsed at all (the parser is superlinear, and a hook that runs out of time lets the call through) |
| `PostToolUse` on `Bash` | when Claude Code reports which files the command changed (`bashEditDiff`) and one is outside the scope: logged as a **breach**, and the agent is told to put it back. Claude Code does not fire this event for a command that exits non-zero, so this layer can be dodged; the boundary cannot |
| `Stop` | refused while the session holds a running node: finish it, or hand it back saying why |
| `SessionStart` | with or without a plan: the plan's text form, and plan first's instruction when it is on; with a plan in force, how to take a leaf. Not for an executor or a planner Graphene started |
| `UserPromptSubmit` | the prompt is remembered (a leaf may be made from it, or a one-leaf proposal accepted as its ask); with plan first on and no leaf held, the instruction to propose first |

The deny applies in every permission mode, `bypassPermissions` included, and inside subagents (both
checked with Graphene's own gate on a real session). The hook reads the node's row on every call,
so tightening a scope binds the very next write. It adds about 40 ms to each event it runs on
(`tests/test_hook_budget.py` holds the median under 60 ms for recording and for refusing); in a
repo with no plan the gate is imported only when a session starts, when a prompt is typed, and while
plan first is on.

A finished plan stays in force. The first real agent run against an earlier build did both nodes
inside their scopes, waited until no node was open, then made the edit no node allowed, and said so:
"no node was open. Graphene accepted the write." Since then a session that holds no node writes
nothing while the plan exists, and the refusal tells it to propose a node. The same agent, refused,
proposed one and asked the person to accept it. You end a plan with `graphene plan archive`, or
suspend it with `graphene plan pause`.

Recording and deciding fail apart. If the gate crashes, the call goes through, the traceback goes to
`.graphene/ingest.log`, and the event is still recorded; the boundary does not depend on the hook.

## P4. `graphene run`

For each node an agent can reach, in order: Graphene starts the node itself, runs the executor
command you gave (`--with`, else the one `graphene init` chose (P4c), else `claude -p --permission-mode acceptEdits --allowedTools
'Bash(graphene *)'`: it may edit and run its own `done` and `release`) with the node's contract as
its last argument and `GRAPHENE_NODE` in its environment (and `GRAPHENE_EXECUTOR`, the command's
name, so the executor's own `done` is logged as `run:<name>`, as the run's acts are), waits for the
process to end,
and then looks at the node, not at the exit code. If the executor ran `graphene node done` itself
and the gate agreed, fine. If it handed the node back, the reason is printed and the run moves on.
Otherwise Graphene runs the gate; refused, the executor is sent back with the refusal (Claude Code
is given a session id on the first attempt, so the hooks hold it to the node from its first call,
and is resumed in that session afterwards; any other command gets the refusal in a fresh prompt).
After `--attempts` (3) the node is handed back with the last refusal as the reason. A person's node
is never handed to an executor. The run ends by saying what is waiting and for whom. Each attempt's
output streams to `.graphene/runs/<leaf>-<time>-<n>.txt`, and an `attempt` entry in the log names it
with the executor's pid and the run's; `graphene watch` reads its tail, and a Claude Code executor's
last tool call from the hooks' record. Executors and checks run in sessions of their own: Ctrl-C
reaches the run (and so do a closed terminal and a `kill`), which ends the checks it started, hands
back every leaf it started that had not passed, and stops the executors (exit 130); a leaf that had
passed and not yet landed waits in `review`, and says so. A leaf the person releases or drops stops
its executor within half a second. A leaf still held by a run that is gone (its pid ended, or names
a process that began at another time) is handed back by the next run, after its executor is stopped,
TERM then KILL. A leaf whose need is done but whose work is not in the checkout it would start in
(never landed, landed out of its history, uncommitted where it was done) waits, and says why
(`plan.not_here`); a need whose files were committed after it finished counts as here, even when
the content was edited again before that commit. One node at a time, in the checkout you ran it from, and nothing is committed.

A leaf that comes back offers its fix (`plan.offers`), from what it tried to write outside its scope
(`plan.wanted`: refused writes, a refused `done`, what it changed): `graphene node widen <id>`,
`graphene node sibling <id>` (a leaf for those paths, which it then waits on), or making it wait on
the nodes its reason names.

`graphene run --parallel N` runs up to N ready leaves at once. Each gets a worktree,
`.graphene/worktrees/<id>` on branch `graphene/<id>`, cut from where your checkout stands at that
moment, so it holds everything that has already landed. The executor works there and meets the same
boundary there. Then, one leaf at a time, Graphene commits the leaf's changed paths on its branch
(your git identity; the message is the title, the goal, the why path and `Graphene-Node: <id>`) and
merges it `--no-ff` into your checkout; the worktree and the branch are removed; sub-goals roll up
*there*, after the merge, and never while a sibling that is done in its worktree has not landed.
Two rules keep merges clean: a leaf does not start while something it needs has not landed, and a
leaf whose scope overlaps that of a leaf in flight waits for it to land. Since a write outside a
scope is refused, two leaves cannot have written one file. If git still will not merge (your own
uncommitted work is in the way), the merge is aborted, your checkout is as it was, the leaf stops in
`review` with a log entry `unlanded` naming its branch, and what needs it waits. `git merge
graphene/<id>` and `graphene node signoff <id>` (or the page's sign-off) finish it by hand; `graphene node reopen` sends it
round again. An executor is never asked to resolve a conflict. Your untracked Claude Code hook settings
(`.claude/settings.local.json`, which git ignores in every worktree) are copied into each worktree,
so the hooks hold a leaf there as they do in your checkout.

## P4a. `graphene ask`

A planner is an executor whose scope is the plan (`ask.py`). It is started as `run` starts an
executor, with the command the person names (`--with`, else the one `graphene init` chose, else `claude -p --tools Read,Grep,Glob
--strict-mcp-config`: it can read and nothing else, and none of the person's MCP servers reach it), `GRAPHENE_PLANNER` in its environment, and a prompt holding the sentence,
the plan's text and the rules for a leaf. What it prints is read as the plan's text (the last fenced
block, or else from the first line that reads as one) and added as its proposals; a proposal
Graphene cannot read goes back to it once, with the refusal. The hooks refuse it a write and
`start` refuses it a leaf. Asking is the person's: it spends. `graphene node split <id>` asks it to cut
a leaf; `--about <id>` asks it about a leaf that came back.

## P4b. Nemotron on Token Factory: the executor, the planner, the sandbox

`--with nemotron` names Graphene's own executor (`executor.py`) to `graphene run`, and its own planner
(`planner.py`) to `graphene ask`, `node split` and `:ask`. Both call Nebius Token Factory's
OpenAI-compatible API (`tokenfactory.py`, the standard library only) with the key in
`NEBIUS_API_KEY`. The key is sent in one header and written nowhere. No model id is written into
Graphene: `tokenfactory.roles` reads the NVIDIA Nemotron models from the live list (`GET /v1/models`),
by size (Ultra, Super, Nano). Every call's usage is priced at the list price that same list gives. It
goes into the leaf's record as a `usage` row (calls, tokens in and out, dollars, writes refused) and,
when `GRAPHENE_LEDGER` names a file, into that ledger, which `GRAPHENE_SPEND_CAP_USD` caps: at the cap
the next call is refused before it is sent. A 429 or a 5xx is waited out (`Retry-After`, else doubling).

**The executor** is started by `graphene run` like any other: in the leaf's checkout, with
`GRAPHENE_NODE` and the contract as its last argument. Its loop runs here. It asks a model for one
tool call at a time (view, edit, write, run, done, release) and runs the call in the leaf's
**placement**: the checkout itself (`--placement local`), or a Token Factory Sandbox
(`--placement sandbox`). `done` is `graphene node done`: git and the check decide, never the model.
`--model` given twice or more is a ladder: attempt *k* uses the *k*-th model. `--forks N` runs N
conversations at once from one checkpoint, each in a copy of the checkout. A fork's `done` runs the
check in its copy; the first whose check passes is copied in (what its scope covers, nothing else) and
Graphene's own `done` decides. `--protocol text` takes tool calls written as fenced text, for a model
whose native calls misfire; Nemotron's own `<TOOLCALL>` text is read in either protocol, and a tool
called by another common name (`read_file`, `str_replace`, `bash`) is the tool it means. A reply cut
off at the token limit is asked again with more room. `view` reads only what git shows. A command the
model runs, and every check, get an environment without the key. An executor that cannot work at all
(no key, a refused key, no sandbox, the spend cap) hands the leaf back itself, with the cause.

**The sandbox** (`sandbox.py`) is ConTree, through `contree-sdk` 0.3.6 (the `sandbox` extra), with the
SDK's own credentials (`NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID`, or a `contree auth` profile). Without
them it refuses in words before anything is sent.

**The checkpoint.** For a checkout that is exactly a commit, the repository is uploaded and set up once:
- git tracks it, or does not ignore it;
- it is unpacked at `/work` in a sandbox from `python:3.12` (`--image` names another);
- a git baseline is made, and the user `leaf`;
- `--prepare` runs once, as root (`pip install -e .[test]`, say).

That checkpoint is kept in the store's meta. Every leaf started at that commit forks it. A leaf with
uncommitted work of its own gets a checkpoint of its own. Each fork then gets its leaf's permissions
(`layer2`):

- `/work` is root's and nobody else may write it;
- `leaf` owns the files the scope covers, and every directory the scope covers whole;
- a directory where the scope names a file, existing or not, is writable with the sticky bit, so
  `leaf` can create a file there and replace its own, and cannot delete, rename or change anyone
  else's.

`--forks N` makes one sandbox for the leaf and forks the others from it (`Sandbox.fork`).

**Edits, commands and the record.** The checkout here stays what the boundary reads. The executor's
edits land here after the scope check, and are pushed into the sandbox before its next command. After
each command, the command's exit code and a list of every file under `/work` with its hash are
written to a file in the sandbox, closed by an end line, and read back whole. Never from the command's
output, which is capped. A list that does not come back whole changes nothing here.

What the scope covers is brought back here. Anything else, such as a new file in a shared directory
or a link, is never brought back, and neither is what git ignores (a check's `__pycache__`). Such a
path is logged on the leaf as a breach, the model is told, and it is removed before the next command.
The executor records each write it made, its own edits and what its commands changed here, in its
usage row, and the leaf's record is graded by them.

**The check.** The leaf's check runs in a fresh fork of the leaf's first image, holding the checkout as
Graphene holds it, as `leaf` (`sandbox.check_in_fork`). So a file a command left outside the scope
cannot change its result. `GRAPHENE_SANDBOX=docker` puts the same sandbox in a local Docker container
(`sandbox.Docker`): the tests' and CI's stand-in for ConTree, with the same users and permissions.

**The planner** reads the repository with list, glob, grep and read. They run here and read only what
git shows: never a file git ignores (a `.env`), never `.graphene/`. A planner writes nothing. It prints the fenced `plan` block that `ask.py` reads. It defaults to the
largest Nemotron the list has; its bill goes into the plan's log.

**Which executors are held before the write, and how:**

| Executor | Before the write | While it runs | At `done` |
| --- | --- | --- | --- |
| Nemotron, in a sandbox | its edit and write tools refuse a path outside the scope, in the hook's words, and log it for the offers | its commands run as a user who can write only the scope; what a command makes outside it is never brought back | Graphene's check, in a fork of the sandbox, and git |
| Nemotron, local | the same tools refuse | nothing: a command can write where your user can | the check, and git |
| Claude Code, with the hooks | `PreToolUse` denies Edit, Write, MultiEdit and NotebookEdit outside the scope, and the shell forms the parser reads (`>`, `tee`, `sed -i`, `mv`, `cp`, `rm`) | nothing more | the check, and git |
| Codex, or any command | nothing | its own sandbox if you give it one (Codex's `workspace-write` keeps it to the checkout, not the scope) | the check, and git |
| A person | nothing | nothing | the check, and git |

## P4c. Which planner and which executor

`graphene init` chooses both, once per repository, and keeps them in the store's meta (`planner`,
`executor`), each spelled as `--with` takes it. At a terminal it asks the person, numbered: Nemotron
on Token Factory first and the default, then Claude Code, Codex, or a command of your own (read as
`--with` reads one; one that cannot be read is said so and asked again). Run again, it shows what is
set, and Enter keeps it. Without a terminal it takes `--planner` and `--executor` and changes only
what they name; with neither it keeps what is set, and gives what is not Nemotron when Token Factory
answers, else Claude Code.

Nemotron, chosen at the terminal or as plain `nemotron` in a flag, is written with the ids Token
Factory's model list gave: the largest of Ultra and Super plans (`nemotron --model <ultra>`), as the
planner picks when it runs, and the two smallest listed do the leaves, the second on a second attempt
(`nemotron --model <nano> --model <super> --placement local`). The menu names the sizes it found.
The placement is `sandbox` when ConTree is set up here (`sandbox.configured`: the SDK imports, and
`NEBIUS_API_KEY` with `NEBIUS_PROJECT_ID`, or a `contree auth` profile), `local` otherwise. When the
list could not be read it is plain `nemotron`, which finds its models when it runs. Token Factory is
asked once, with no retry, and a try waits 10 seconds at most (`tokenfactory.LISTED`). What could not
be reached (no key, a refused key, no answer, no Nemotron listed) is one line.

`run`, `ask` and `node split` start what was chosen, and so do the screen's `R`, `:ask` and `s`;
`--with` overrides it for one command. Choosing is the person's, since what is chosen runs with the
person's permissions and spends on their key: an agent's `--planner` or `--executor` is refused, and
an agent is never asked, at a terminal or not. An agent's plain `graphene init` still fills a choice
that is not set with the offer above. The screen's status line names what `R` starts (`R runs 3 ready
with nemotron`) only where the long form still fits with it.

## P5. Where each mechanism ends

- A shell command can write a file in a way no parser reads (a script that opens files itself).
  That is caught only at `done`, by git; until then the change is on disk.
- A file made outside the scope and moved out of the repo before `done` is invisible to git. It is
  caught when it comes back, as a change no node owned.
- Claude Code ends a session after about 8 refused stops in a row (its docs say 8; 9 were observed
  on 2.1.278), and a headless run that hits `--max-turns` never fires `Stop`. The node then stays
  `running` on the plan. `graphene run` does not depend on `Stop` at all.
- A hook that crashes or times out lets the call through. That is the vendor's rule.
- Writes through an MCP server's tools are not seen by the hooks at all, a filesystem server's
  included: under a held leaf `done` asks git and catches them; in a session that holds no leaf,
  nothing does.
- The person-only rule rests on the environment, and no command line can do better. Inside an
  agent's environment `GRAPHENE_AS` changes nothing; an agent that first strips its own markers
  (`env -u CLAUDECODE …`) and then sets it passes for a person. The log shows such an act as made
  with no terminal, which a person's own acts at a terminal never are, unless it also set
  `GRAPHENE_WATCH=1` in a way the hook cannot read.
- The plan's store is a file in the repo that git ignores. The hook refuses the commands that
  name it; a script that opens it directly is neither stopped nor noticed. Nothing here defends
  the store against an executor that sets out to rewrite it.
- What git ignores, nobody audits: an executor can write anything under an ignored directory.
- A check runs on the node's state as git sees it (P2 step 3), and nothing git ignores is there: a
  check that calls `.venv/bin/pytest` or reads a `.env` finds nothing, and one that needs an
  environment makes it (`uv run`, `npm ci`). Linking the checkout's `.venv` in was tried: `uv run`
  in the worktree re-installed the project into it, and left the checkout's `.venv` pointing at a
  directory that was then deleted. The worktree lies under the checkout's `.graphene/`, so a tool
  that looks in the folders above it finds the checkout's (Node's `require` finds its
  `node_modules`); and a check inherits the environment Graphene was started in, so a `python` on
  that PATH (an active virtualenv, `uv run graphene`) imports the project from where that
  environment installed it, which for an editable install is the checkout itself. A check that
  names the checkout by an absolute path reads and writes the checkout itself. What git does not
  carry is not there (an empty directory, a submodule's files). A leaf of `graphene run --parallel`
  works in a worktree cut fresh, which has nothing git ignores either.
- Every check pays for a whole checkout: 0.3 s on this repository (about 330 files), 19 s on one of
  100,000 files, on a loaded machine. What it runs on is written into the repository's objects (the
  changed and new files, once for each content), where nothing refers to it until `git gc` clears
  it (after two weeks, by default): a new 100 MB file git does not ignore added 97 MB there, and 2 s
  to the first check that saw it. A Graphene killed outright (`kill -9`) during a check leaves that
  check's worktree under `.graphene/worktrees/.check-*`; `git worktree remove --force --force
  <path>` removes it.
- The boundary asks git about every working tree of the repo that exists when the node ends (a
  path changed in another worktree is refused with the tree named), except the worktrees of
  `graphene run --parallel`, whose own leaves answer for them; a node in your checkout that writes
  into one of those by absolute path is not seen. Nor does it ask about clones or copies of
  the repo somewhere else on the disk.
- Scope overlap between two running nodes is checked against tracked files and the globs as
  spelled; two globs that would both match a file that does not exist yet are not seen until one
  of the nodes is refused at `done`.
- `.claude/settings*.json` is not protected by anything here. An agent that removes the hook from
  it has removed the hook; the boundary still holds.

## P6. A node's record

`graphene node show <id>` prints the contract, then, from records only: each **window** the node was
held (who, from when to when, how it ended); what changed in it (git's own answer when the window
ended, or the working tree for a node still running, plus the files of commits whose time falls
inside the window, each path with the record it came from, and paths outside the scope called out);
the **coverage** block; what was **refused** (denied writes, breaches, refused stops, refused
`done` attempts with their stray paths, failed checks); and the person's acts on it with their
words.

The coverage block works for any executor, because the three things it stands on need no vendor:

1. **The node's log.** `start` records the base sha and the checkout; `done` and `release` record
   git's HEAD at that moment and the paths git said had changed since the base. That list is the
   node's change set, and it is the denominator.
2. **Git.** The commits whose committer time falls inside each window are asked of git directly,
   not read out of the store: the store holds a commit only when a recorded session's window
   covered it, so for Codex, `graphene run --with …` or a person there would be none, and a count
   of zero would read as "nothing was committed".
3. **The check Graphene ran itself**, with its command, its result and when — printed in the block,
   because it is what verifies the change set.

Claude Code's records, where a session held the node, add exactly one thing: which changed path
traces to a write somebody recorded making (`edit`, or the vendor's shell change list). Where they
do not exist, every path is graded `to git alone` and the block names what it was read from. The
commit grading is the run's (see §3): it is computed over every commit the holding sessions are
recorded for and the node's are selected afterwards, because grading a list cut to the window would
flatter its first commit; and a write counts only when it was recorded inside one of the node's
windows. Where a count cannot be supported at all — nobody has held the node, or a window ended
before its change set was logged and none is open to read — it says "not computed" with the reason.
It never prints a zero it cannot stand behind.

# Part two: the record

## 1. Where the data comes from

### Live hooks

`hooks.py`. `graphene init` adds one command hook, `graphene ingest hook`, to eight Claude Code events in the
repo's `.claude/settings.local.json` (the personal file; the team's `settings.json` is never
written, though hooks found there are recognised, and a repo whose hooks live there gets new events
added there): `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`,
`SubagentStart`, `SubagentStop` and `Stop`. `PreToolUse` is never recorded (a call that has not
happened is not a record); it exists for the plan (P3). Existing settings and hooks are kept; the hook is added once, and
the file is rewritten atomically (through a symlink to its target) so a crash cannot truncate it.
Claude Code runs the command with the event JSON on stdin. The command writes one row to
`.graphene/graphene.db` and exits 0 whatever happens; internal errors go to
`.graphene/ingest.log`, and stdout carries nothing except the plan's answer when a plan is in
force (P3), so a broken Graphene can never block the agent. It takes
about 40 ms (a median of twenty runs on the author's machine, measured by `tests/test_hook_budget.py`
and held under 60 ms there) because it imports only the standard library on that path, and if another process
holds the database lock (a command, a second session) it gives up after 250 ms and logs the
missed event rather than stalling the agent.

What each event contributes:

| Event | Recorded |
| --- | --- |
| `SessionStart` | the session, its repo, the time, and `git rev-parse HEAD` at that moment |
| `UserPromptSubmit` | the prompt text verbatim, with Claude Code's `prompt_id`; a slash command (`/model`, a skill) is skipped |
| `PostToolUse` | the tool name, input, response, and for file tools the file's content before and after |
| `PostToolUseFailure` | the same call marked failed, with the error text |
| `SubagentStart`, `SubagentStop` | the subagent, its type, its start and end, its working directory and, when that lies in a worktree of the repo (asked of git's own files while it exists), the worktree |
| `Stop` | the session's end time (updated on every turn end) |

Not all of a response is worth keeping. A `Read` is recorded as the call, the path and whether it
worked: its response is the file itself, and nothing here reads it back. Any other recorded string
longer than 8 KB keeps its first and last 4 KB with a count of the characters between them, so a
command is remembered by how its output started and how it ended — a `git commit … && git log
--oneline -1` prints the new SHA on the very last line. Paths, names, the list of files a command
changed and the error of a failed call are never cut, and a file edit's before and after content
keeps its own 2 MB budget in its own columns.

A tool call is grouped under the prompt whose `prompt_id` it carries. When that id is unknown
(hooks installed mid-session, older Claude Code), it falls back to the latest recorded prompt in
the session. Subagent calls carry `agent_id`, which is the lane they are drawn on. The rest of a
subagent is in other calls: the `Agent` call that spawned it names it in its response (`agentId`)
and carries its task and its prompt, and its spawn link starts there; the `SubagentHandback` call it
makes carries its closing words. The map reads them off those calls. A command's list of changed
files names a worktree's copy of a file, and the worktree `SubagentStart` recorded maps it to the
repo's file, drawn as a copy.

### What is not read

Graphene reads no transcript: nothing under `~/.claude/projects/`, where Claude Code keeps them.
What it knows of a session is what the hooks recorded while it ran, so a session is on the record
from the moment `graphene init` installed them, and one run before that, or in a checkout without
them, is not. What no hook event carries, the record does not have: the Workflow run a subagent
belongs to, so a Workflow's agents are not drawn as one group. A store written by an earlier
version, which read the transcripts, keeps what it read, and the map still draws it.

### The store

`.graphene/graphene.db` carries a schema version in SQLite's `user_version`. What the hooks
recorded and the plan live nowhere else, so the store is never rebuilt from scratch: an older store is migrated in place, by additive steps only, by whichever process
opens it first (the hook included). A store written by a *newer* Graphene is left exactly as it is
and the command says to upgrade. Only a file SQLite refuses to read at all is moved aside, to
`.graphene/graphene.db.corrupt.bak` (with its `-wal`/`-shm` sidecars, and a numeric suffix rather
than overwriting an existing backup), and replaced by an empty store. A locked database is not that case and is never moved. The hook path never moves
anything: on a store it cannot use it skips the event, writes one line to `.graphene/ingest.log`,
and exits 0.

## 2. File content: what is known and what is not

For `Edit`, `MultiEdit` and `Write`, Claude Code's response carries `originalFile`, the content
before the call, and either the new content (`Write`) or the strings replaced (`Edit`), from which
Graphene derives the content after the call. Both are stored (up to 2 MB each) so a diff can be
computed later without touching the working tree. A `Write` whose response says `create` counts
as known with no prior content. For a file outside the repo (a dotfile in your home directory,
say) only the path is kept, never the contents, not even inside the raw tool payload the store
keeps for every call: the map lists such files by name and nothing else. A file inside another git checkout below the repo root (a worktree under
`.claude/worktrees/`, a vendored clone) counts as outside too: it belongs to that checkout.

What is not known from the payload: anything a shell command does to a file, and notebook edits.
For `Bash`, Graphene recognises only the obvious write forms: `>` and `>>` redirections, `tee`,
`sed -i`, `mv`, `cp`, `rm` and `touch`. Relative paths follow `cd` segments earlier in the same
command; heredoc bodies are ignored so a `>` inside a script fed to `python` is not a
redirection. A script that rewrites files, a formatter, a `git checkout`, or a `python -c` that
writes are all invisible to it.


## 3. What a path traces to

There is no prompt-to-hunk reconstruction any more. What the record answers is narrower and can be
checked: for a path, what is the best evidence that somebody's recorded write put it there?

- **`edit`** — the payload of an `Edit`, `Write`, `MultiEdit` or `NotebookEdit` call.
- **`shell`** — the file appears in Claude Code's `bashEditDiff` list for a `Bash` call. Turn the
  lists on with `"bashEditDiffEnabled": true` in `~/.claude/settings.json`; a repo's settings
  cannot. When the vendor marks a list as possibly a concurrent command's (`shared`) and another
  agent's payload edit of that file falls inside the call's span, the payload edit is the better
  record and the shared entry gives way to it.
- **`commit`** — an agent is recorded making the commit that changed it, and no write is recorded.
- **`window` / "to git alone"** — git says it changed and nothing else does.

A commit's path is graded by the writes recorded since the previous commit of that path and no
later than this one, so the grade depends only on records up to the commit and never changes
afterwards. A recorded `git cherry-pick` copies its origin's grade. A path counts once, under the
best grade any of its commits reached. Every path of every commit is graded: there are no
exclusions, so the denominator is git's, not Graphene's.

The counts are never collapsed into one number, and where a session's records do not exist the
grading is simply absent rather than being guessed at from something else (P6).

## 4. What you see

`graphene` with no command prints the plan when the repo has one, and otherwise one line saying how
to start one. `graphene watch` is the plan on one screen (P1a); `graphene plan --text` the plan as
text (P1c). `graphene node show <id>` is a node's record (P6). `graphene ui` is the plan and, behind
it, the map of a recorded run. `graphene plan log` is every log entry, oldest first.

`graphene ui` draws what the store holds, the plan and the sessions the hooks recorded, and asks git
for the commits inside those sessions (all of them the first time, afterwards the ones still running
or ended within a day). `--session ID` picks a session by
id or unique prefix and can be repeated to put several on one axis; with none, the session that
finished last and did something is drawn. `--json` prints the graph the page draws.

Output rules: plain text, never wrapped or cut, so an agent reads a contract as its contract and a
person greps it. In a terminal a line is word-wrapped at the width; piped or redirected it is one
line with no escape codes. `NO_COLOR` turns colour off and keeps the layout. Every dead end is one
line on stderr and a non-zero exit (plain when it is merely empty, red when it is an error):
outside a git repository, inside your home directory, nothing to draw (no plan and no session
recorded), a store another Graphene process has locked, no plan in this repo yet.

Graphene writes nothing until it has something to record: in a repo with no store the empty state
is printed and `.graphene/` and `.gitignore` are left alone (`graphene
init` creates them, and says so).

All commands except the hook refuse to run outside a git repository, and never treat your home
directory as one, so `~/.claude/settings.json` (Claude Code's user-level settings) is never
written.

## 5. What Graphene never does

It calls a model only when you name its Nemotron planner or executor (P4b). Then it sends Token Factory
the prompts about your repository and the files the model reads, and Sandboxes the leaf's checkout, and
nothing else, anywhere. The key is read from your environment at each call and written nowhere. It
never pushes, and it commits and merges only in `graphene run --parallel`, on branches of its own (P4).
`graphene run` starts the executors you name and `graphene ask` the planner you name, with the
permissions you give them; nothing else in Graphene starts an agent. It reads nothing Claude Code keeps under `~/.claude/`
but the one setting `graphene init` looks for (and never writes). What the hooks record can contain
secrets; the store stays in `.graphene/` inside
the repo, a directory that is made private to your user (`0700`, the database `0600`) and that
ignores itself in git through a `.gitignore` of its own, so the repo's `.gitignore` is never edited.

## 6. The page

`graphene ui` serves one page to this machine only (loopback, `Host` and `Origin` checked). Its
first screen is the plan: columns are how deep a node sits in what it waits on, lanes are owners
(agents first, then each person), and every position is computed in Python
(`src/graphene_map/plan_view.py`, tested in pytest) so the page decides no layout. The second
screen is the record of a run: lanes of agents over rows of files (`graph.py`).

The page can change the plan only when a person started `graphene ui` (started from an agent's
shell it is read-only and says so). A write needs the page's own origin and a token made for that
launch, sent in a header a cross-site form cannot set. Each control calls the same function in
`plan.py` as the command line does, a refusal is shown verbatim, and beside the scope, check and
sign-off fields the page prints where that mechanism ends (P5).

`graphene ui --export FILE` writes the same page as one file with its data inlined: paths, counts,
commit subjects, prompts, each agent's task, and the plan with each node's whole log as its record.
In the file a check is named by its command and result and never by what it printed, and a reason
keeps only its first line (the reason `graphene run` hands a leaf back with quotes the refusal, and
a failed check's output is under it); where a sentence names the checkout's path, the file names the
repository instead. A run by executors that keep no records of their own is drawn
from those logs alone; the second screen, drawn from Claude Code's sessions, is shut when there are
none. It carries no token and cannot write. `docs/demo/README.md` says how the demo page is made
from it and hosted. Every piece of text reaches the page
through `textContent`, and `</` is escaped inside the JSON, so nothing recorded can turn into markup.
