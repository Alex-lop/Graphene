# How Graphene works

Graphene keeps a plan that a person and their coding agents share, holds executors to it, and
keeps a record of what was done for each node. No model is involved at any point: everything here
is computed from the plan's own rows, from git, and from what Claude Code already records.

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
terminal (`alex (no terminal)`). `graphene ui` gives its page the person's rights only when a person
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
check, if it has one, is run by Graphene in the checkout where the children's work is together; that
is where integration lives. Passing (or having no check), the sub-goal is done, or in `review` if it
asks for a sign-off, and what needs it can start. Failing, it stays open, the log has the output,
`graphene plan` says "its leaves are done and its own check fails", and the way on is a leaf under
it for what is missing; `graphene node done <sub-goal>` runs the check again. A child added or
reopened under a finished sub-goal reopens it.

**A proposal is a subtree.** `graphene plan propose` reads nested `"children"`, and `"parent"` puts
a node under one already there. Accepting a node accepts every proposal under it and every proposal
it sits under. A leaf too big to do is split by proposing children under it and handing it back
(children cannot be accepted under a leaf someone holds); dropping the children makes it a leaf
again; dropping a sub-goal drops what is under it, unless something outside waits on any of it.

**The path to the root is told to every executor.** `plan.trail` is the goal and then each sub-goal
above the leaf, with its own goal; `plan.contract` prints it as `why:` lines above the leaf's goal.
`graphene node start`, `graphene node show` and the prompt `graphene run` hands over all use it.

**In the terminal** (`plan_cli.plan_lines`): the goal, a count of leaves, what waits on a person
(a proposed subtree is asked about once, at its top), then the tree indented by depth. Once it is
longer than a dozen lines, finished nodes fold into one `✓ n done here` line per level; `--all`
unfolds. `graphene watch` redraws the same lines once a second with the last six log entries under
them. It reads the store and nothing else.

## P1b. A request typed into a session

With a plan in force, the `UserPromptSubmit` hook remembers the session's latest prompt. When that
session holds no node and is about to write (`PreToolUse`), Graphene makes a leaf from the prompt
and starts it for the session: title and goal are the person's words; its scope and check are what
they wrote after `scope:` and `check:`, if anything, and otherwise `**` and no check. Nothing is
inferred from the prose. At `Stop` the leaf closes (`plan.close_aside`): git says what changed, the
check runs if there is one (failing, the stop is refused with its output), and a leaf under which
nothing changed is dropped. It is a record rather than a gate: it does not run the looks at other
worktrees that `done` runs. A session that holds a planned leaf is held to it as before; an executor
`graphene run` started never gets such a leaf; `graphene plan prompts strict` turns them off.

The same hook reads a short prompt (240 characters at most) that begins with yes, ok, sure, accept,
go ahead, do it or lgtm as the person accepting proposals: the ones it names by id, all of them if
it says "all" or "everything", else the ones this session proposed. The log entry carries
`by: prompt` and the words. The agent is told, as added context, what was accepted and what is
ready. An agent that starts a second agent writes that agent's prompt: that is the hole.

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
   started from). The node stays `running`.
3. It runs the check in the node's checkout (30 minute cap) and keeps the tail of the output in the
   log. Non-zero: refused. What the check itself leaves behind (a cache, a coverage file) is taken
   as it is, so a second `done` is not refused over it.
4. If nothing inside the scope has changed at all, it is not done either: a check that already
   passed shows nothing (an executor that crashed at once was once reported done this way). An
   executor with nothing to do hands the node back and says so.
5. Otherwise the node is `done`, or `review` when it needs a sign-off; what git said had changed,
   and the `HEAD` it ended at, go into the log for the node's record; and the tree as it stands is
   remembered as this checkout's **boundary**.

Between nodes nobody owns the repo. Whatever differs from the last boundary at the next `start`,
outside the scope of every node started since, is a change no node owned: an agent's `start` is
refused until it is put back, a person sees it on `graphene plan` and can accept it with
`graphene plan ack`. This exists because a real agent did exactly that (next section).

A person can overrule the gate with `graphene node done <id> --override "reason"`; the log keeps the
reason, the stray paths and whether the check had failed. `graphene node release <id> --why "…"`
hands a node back unfinished, and `graphene node reopen <id> --note "…"` sends a finished one back
with the person's words, which the next executor is shown.

None of this involves a vendor. On 2026-09-20 the same gate refused, and then accepted, a Claude
Code agent, a Codex agent (`codex exec`) and a person editing by hand.

## P3. What the Claude Code hooks add

`graphene init` registers one command, `graphene ingest hook`, on eight events. With a plan in
force it answers as well as records (`src/graphene_debrief/gate.py`), in the vendor's documented
JSON:

| Event | Answer |
| --- | --- |
| `PreToolUse` on `Edit`, `Write`, `MultiEdit`, `NotebookEdit` | a path outside the scope of the node(s) this session holds is **denied**, with the reason and the way out; a session that holds no node is denied every write in the repo and told to take a node, or to propose one. Inside the scope it says nothing, so your own permission rules still apply. Paths outside the repo are not the plan's business. |
| `PreToolUse` on `Bash` | the writes the shell parser can read (`>`, `>>`, `tee`, `sed -i`, `mv`, `cp`, `rm`, `touch`, following `cd`) are checked the same way, links resolved first; a target git ignores passes; a command that mentions `GRAPHENE_AS` or reaches into `.graphene/` is denied whatever the scope; a command over 64,000 characters is not parsed at all (the parser is superlinear, and a hook that runs out of time lets the call through) |
| `PostToolUse` on `Bash` | when Claude Code reports which files the command changed (`bashEditDiff`) and one is outside the scope: logged as a **breach**, and the agent is told to put it back. Claude Code does not fire this event for a command that exits non-zero, so this layer can be dodged; the boundary cannot |
| `Stop` | refused while the session holds a running node: finish it, or hand it back saying why |
| `SessionStart` | one paragraph of context: there is a plan, and how to take a node |

The deny applies in every permission mode, `bypassPermissions` included, and inside subagents (both
checked with Graphene's own gate on a real session). The hook reads the node's row on every call,
so tightening a scope binds the very next write. It adds about 40 ms to each event it runs on
(`tests/test_hook_budget.py` holds the median under 60 ms for recording and for refusing); in a
repo with no plan the gate is not even imported.

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
command you gave (`--with`, default `claude -p --permission-mode acceptEdits`) with the node's
contract as its last argument and `GRAPHENE_NODE` in its environment, waits for the process to end,
and then looks at the node, not at the exit code. If the executor ran `graphene node done` itself
and the gate agreed, fine. If it handed the node back, the reason is printed and the run moves on.
Otherwise Graphene runs the gate; refused, the executor is sent back with the refusal (Claude Code
is given a session id on the first attempt, so the hooks hold it to the node from its first call,
and is resumed in that session afterwards; any other command gets the refusal in a fresh prompt).
After `--attempts` (3) the node is handed back with the last refusal as the reason. A person's node
is never handed to an executor. The run ends by saying what is waiting and for whom. Output of each
attempt is kept under `.graphene/runs/`. One node at a time, in the checkout you ran it from, and
nothing is committed.

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
graphene/<id>` and `graphene node signoff <id>` finish it by hand; `graphene node reopen` sends it
round again. An executor is never asked to resolve a conflict. If the worktree has no copy of your
Claude Code hook settings (they are usually untracked), the hooks do not run there; the boundary does.

## P5. Where each mechanism ends

- A shell command can write a file in a way no parser reads (a script that opens files itself).
  That is caught only at `done`, by git; until then the change is on disk.
- A file made outside the scope and moved out of the repo before `done` is invisible to git. It is
  caught when it comes back, as a change no node owned.
- Claude Code ends a session after about 8 refused stops in a row (its docs say 8; 9 were observed
  on 2.1.278), and a headless run that hits `--max-turns` never fires `Stop`. The node then stays
  `running` on the plan. `graphene run` does not depend on `Stop` at all.
- A hook that crashes or times out lets the call through. That is the vendor's rule.
- The person-only rule rests on the environment, and no command line can do better. Inside an
  agent's environment `GRAPHENE_AS` changes nothing; an agent that first strips its own markers
  (`env -u CLAUDECODE …`) and then sets it passes for a person. The log shows such an act as made
  with no terminal, which a person's own acts at a terminal never are.
- The plan's store is a file in the repo that git ignores. The hook refuses the commands that
  name it; a script that opens it directly is neither stopped nor noticed. Nothing here defends
  the store against an executor that sets out to rewrite it.
- What git ignores, nobody audits: an executor can write anything under an ignored directory.
- The boundary asks git about every working tree of the repo that exists when the node ends (a
  path changed in another worktree is refused with the tree named), not about clones or copies of
  the repo somewhere else on the disk.
- Scope overlap between two running nodes is checked against tracked files and the globs as
  spelled; two globs that would both match a file that does not exist yet are not seen until one
  of the nodes is refused at `done`.
- `.claude/settings*.json` is not protected by anything here. An agent that removes the hook from
  it has removed the hook; the boundary still holds.

## P6. A node's record

`graphene node show <id>` prints the contract, then, from records only: each **window** the node was
held (who, from when to when, how it ended); what changed in it (the files of commits whose time
falls inside the window, and for a running node the working tree, each path with the record it came
from, and paths outside the scope called out); the **coverage** three-count for the node's commits;
what was **refused** (denied writes, breaches, refused stops, refused `done` attempts with their
stray paths, failed checks); and the person's acts on it with their words.

The coverage line is graded over every commit the holding sessions are recorded for and the node's
commits are selected afterwards, because grading a list cut to the window would flatter its first
commit; and a write counts only when it was recorded inside one of the node's windows. Where a
count cannot be supported (a person held the node, so there is no session to trace), it says
"not computed" with the reason and how many commits and files it leaves out. It never prints a zero
it cannot stand behind.

# Part two: the record

## 1. Where the data comes from

### Live hooks

`graphene init` adds one command hook, `graphene ingest hook`, to eight Claude Code events in the
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
holds the database lock (a backfill, a second session) it gives up after 250 ms and logs the
missed event rather than stalling the agent.

What each event contributes:

| Event | Recorded |
| --- | --- |
| `SessionStart` | the session, its repo, the time, and `git rev-parse HEAD` at that moment |
| `UserPromptSubmit` | the prompt text verbatim, with Claude Code's `prompt_id`; a slash command (`/model`, a skill) is skipped, as in the transcripts |
| `PostToolUse` | the tool name, input, response, and for file tools the file's content before and after |
| `PostToolUseFailure` | the same call marked failed, with the error text |
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
the session; calls made before any recorded prompt appear in the debrief under their own heading,
"Before the first recorded prompt". Subagent calls carry `agent_id` and are grouped the same way.

### Transcript backfill

`graphene ingest --backfill` reads the JSONL transcripts Claude Code keeps under
`~/.claude/projects/<encoded repo path>/`, plus any directory whose name starts with that prefix
(sessions launched from a subdirectory of the repo), under the repo's path as given and as
resolved through symlinks. A transcript is used only if its recorded `cwd` lies inside the repo. Facts the parser relies on, observed on Claude Code 2.1.27x:

- One JSON object per line. `type` is `user`, `assistant`, or bookkeeping (`attachment`,
  `system`, `file-history-snapshot`, `queue-operation`, `mode`, ...). Only `user` and `assistant`
  records carry prompts and tool calls; every other type is counted and listed after a backfill
  as "other record types", so a new type Claude Code starts writing is at least visible.
- A prompt is a `user` record whose content is a string (or text blocks) and that is not
  `isMeta`, not `isSidechain`, not a compaction summary, and not a slash-command echo wrapped in
  `<command-name>` or `<local-command-stdout>` tags.
- A tool call is a `tool_use` block in an `assistant` record. Its result is a `tool_result` block
  in a later `user` record; `is_error` marks failure, and that record's `toolUseResult` holds the
  structured result. That record also carries the `promptId` of the turn it ran in, which is how
  calls are grouped; a call without one is grouped under the last prompt before its timestamp.
- Subagent transcripts live in `<transcript dir>/<session id>/subagents/**/*.jsonl` and are
  merged into the session, keeping their `agentId`.
- The transcript never records the git HEAD at session start, so backfilled sessions store it as
  unknown; the git fallback below then uses the last commit made before the session started
  (or git's empty tree when there is none), so commits made during or after the session do not
  hide its changes.

A transcript is only parsed when it might have changed: the store keeps the file's size and
modification time from the last time it was read, and a transcript matching both is skipped
without being opened. One that grew is parsed and its session reloaded. A transcript that cannot
be read is reported and skipped; the others still load. Injected context blocks
(`<system-reminder>…</system-reminder>`) are stripped from prompt text, and a message that
consists only of them is not a prompt.

A session the hooks recorded is left alone, because the hooks saw more than the transcript does
(the content before and after each call, and the git HEAD at the start). There is one exception:
if the hooks are installed in this repo and the transcript holds more tool calls than the store
has events for that session — which means they were installed part-way through it — the session
is rebuilt from the transcript automatically, keeping the HEAD the hook captured and the earlier
of the two start times, and is reported as refreshed. `--replace` forces that rebuild for every
session the hooks recorded, installed or not.

### The store

`.graphene/graphene.db` carries a schema version in SQLite's `user_version`. A hook-recorded
session can outlive its transcript, and the plan lives nowhere else, so the store is never rebuilt
from scratch: an older store is migrated in place, by additive steps only, by whichever process
opens it first (the hook included). A store written by a *newer* Graphene is left exactly as it is
and the command says to upgrade. Only a file SQLite refuses to read at all is moved aside, to
`.graphene/graphene.db.corrupt.bak` (with its `-wal`/`-shm` sidecars, and a numeric suffix rather
than overwriting an existing backup), and replaced by an empty store that is backfilled from the
transcripts. A locked database is not that case and is never moved. The hook path never moves
anything: on a store it cannot use it skips the event, writes one line to `.graphene/ingest.log`,
and exits 0.

## 2. File content: what is known and what is not

For `Edit`, `MultiEdit` and `Write`, Claude Code's response carries `originalFile`, the content
before the call, and either the new content (`Write`) or the strings replaced (`Edit`), from which
Graphene derives the content after the call. Both are stored (up to 2 MB each) so a diff can be
computed later without touching the working tree. A `Write` whose response says `create` counts
as known with no prior content. For a file outside the repo (a dotfile in your home directory,
say) only the path is kept, never the contents, not even inside the raw tool payload the store
keeps for every call: the debrief lists such files by name and nothing else. A file inside another git checkout below the repo root (a worktree under
`.claude/worktrees/`, a vendored clone) counts as outside too: it belongs to that checkout.

What is not known from the payload: anything a shell command does to a file, and notebook edits.
For `Bash`, Graphene recognises only the obvious write forms: `>` and `>>` redirections, `tee`,
`sed -i`, `mv`, `cp`, `rm` and `touch`. Relative paths follow `cd` segments earlier in the same
command; heredoc bodies are ignored so a `>` inside a script fed to `python` is not a
redirection. A script that rewrites files, a formatter, a `git checkout`, or a `python -c` that
writes are all invisible to it.

## 3. Attribution: prompt → file → hunks

Per session and file, Graphene lines up the file-touching calls in time order and splits them by
prompt.

**Payload strategy** (used when every call on the file carries content): for each prompt, the
diff is between the file before that prompt's first call and after its last call, computed with
Python's `difflib` in unified form with three lines of context. Line counts and the enclosing
definitions (`def`, `class`, `function`, `fn`, ...) of the changed lines come from that diff.
Failure modes: a change made outside the tools between two calls (you, a formatter, a shell
script) makes the next call's `originalFile` differ from the previous call's result; the diff for
that prompt then includes the outside change. Across 19 consecutive edits checked on real
transcripts, 17 chained exactly and 2 had such interference.

**Bridged strategy** (a shell write between two payload calls): whatever a shell command left
in the file is exactly what the next `Edit` or `Write` reports as `originalFile`, so the
shell-writing prompt gets the diff between the previous payload's result and that `originalFile`.
No git involved, and the payload diffs of the other prompts are untouched.

**Git strategy** (a shell write at the start or the end of the file's history in the session):
the missing boundary comes from `git show <HEAD at session start>:<path>` at the start, or from
the working tree now at the end. Several consecutive prompts writing a file through shell
commands with no payload in between form one span credited to the last of them; the earlier ones
are listed with no hunks. A deleted or moved directory is expanded to the files it held at the
base revision, one change each. A file that is absent from the base revision reads as created;
an untracked file that already existed and was then changed by a shell command therefore shows
its whole content as added, while one whose modification time predates the session is dropped as
untouched. Failure modes: changes made after the session by anything else are blamed on its last
prompt; for backfilled sessions the base is the commit before the session's first record, which
misses work committed within the same second.

**Deferred**: a prompt inside such a span, other than the last, is listed as touching the file
with no hunks and the sentence "its diff for this session is credited to a later prompt", never as
having changed zero lines.

**No strategy**: without git (or with git unavailable), a file a shell command wrote is listed as
modified with no hunks, since created cannot be told from modified, and a file a shell command
removed is listed as deleted with no content. In a repository with no commits yet, git's empty
tree is the base, so files the agent wrote read as created.

The effect per prompt is `created` (no content before), `deleted` (no content after),
`reverted` (before and after identical), otherwise `modified`.

## 4. Tried and abandoned

- **Reverted files**: the file's content at the end of the session equals its content at the
  start (payload strategy), or the git diff against the session-start HEAD is empty (git
  strategy), and at least one call changed it in between.
- **Failed calls**: every tool call whose result was an error is recorded, but a failed call is
  not abandoned work, so the default view shows only one line with their count by tool and how
  many were refused before running (the permission system, the auto mode classifier, or the
  user). `--json` carries every one.
- **Checks that failed and were rerun**: a shell segment whose command word is a test or lint
  runner (`pytest`, `npm test`, `cargo test`, `go test`, `make`, `ruff`, `mypy`, `tsc`, `jest`,
  `vitest`, `eslint`, ...) that failed and whose check segment (`uv run pytest -q`, say) was run
  again later, whatever surrounded it in the command, reporting the last rerun's outcome.

## 4a. What you see

The record's commands (`graphene` when it prints the card, `why`, `sessions`, `ui`) first top the
store up from the repo's transcripts (a transcript that has not changed since it was last read
costs one `stat`), so a session run without the hooks still shows up the next time you look; the
plan's commands read only the store. Plain `graphene` prints the plan when the repo has one (part
one). Otherwise, and always with `--session`, `--since` or `--json`, it prints a short card: the sessions covered,
their span, wall time and prompt count; files changed with added and removed lines; the commits
made during the sessions; a net list of files (created, modified, deleted or reverted over the
whole span, biggest change first, capped at 30 rows); and then only the sections that have
something in them: abandoned work (§4), a one-line failure count, files written outside the repo.
`--session ID` picks one session and `--since 6h` a window; `--json` is the whole structure behind
the card, prompt by prompt.

In a terminal that card is drawn in columns: one bold header line, dim metadata, one accent
colour for paths and commands, green for `+N`, red for `−N`, no boxes and no emoji. Rows never
wrap — paths are shortened in the middle, commit subjects at the end — and the terminal card
shows at most 5 commits and 20 files before "… N more", so a session fits in 40 rows at 80
columns. `NO_COLOR` turns the colour off and keeps the layout. When stdout is not a terminal
(`graphene > out.txt`, a pipe, CI) the markdown text is written as it is, with no rendering at
all; `--json` is always plain. `graphene why` and `graphene sessions` follow the same rules.

Graphene writes nothing until it has something to record: in a repo with neither a store nor a
transcript the empty state is printed and `.graphene/` and `.gitignore` are left alone (`graphene
init` creates them, and says so). Every dead end is one line on stderr and a non-zero exit (plain text when it is merely empty,
red when it is an error; word-wrapped on a terminal, one line when piped): outside a git repository, inside your
home directory, no transcripts for this repo (naming the directory it searched), a session that
changed nothing, a store another Graphene process has locked, `why` on a path nothing touched,
and `why` with no path at all, which first lists the five files that changed most recently.

## 5. `graphene why`

`graphene why PATH` runs the attribution for every session that touched the file and lists the
prompts newest first, each with its diff summary and a sentence built from that diff: "Edited 2
definitions in auth.py: login and refresh_token (+12/−4)."

`graphene why PATH:LINE` reads the line from disk, asks `git blame` which commit last touched it,
then looks for prompts whose recorded diff added a line with the same text, preferring an edit at
the same line number and falling back to the same text elsewhere. If the line is committed, prompts
that ran after the commit are excluded even when they added identical text. One match is reported
as the answer; several are listed newest first; none is explained: committed before any recorded
session, committed before any matching edit, or changed by something Graphene did not see.

All commands except the hook refuse to run outside a git repository, and never treat your home
directory as one, so `~/.claude/settings.json` (Claude Code's user-level settings) is never
written.

## 6. What Graphene never does

It never calls a model, never sends anything anywhere, and never commits, merges or pushes.
`graphene run` starts the executor you name, with the permissions you give it, and nothing else in
Graphene starts an agent. Transcripts can contain secrets; the store stays in `.graphene/` inside
the repo, a directory that is made private to your user (`0700`, the database `0600`) and that
ignores itself in git through a `.gitignore` of its own, so the repo's `.gitignore` is never edited.

## 7. The page

`graphene ui` serves one page to this machine only (loopback, `Host` and `Origin` checked). Its
first screen is the plan: columns are how deep a node sits in what it waits on, lanes are owners
(agents first, then each person), and every position is computed in Python
(`src/graphene_debrief/plan_view.py`, tested in pytest) so the page decides no layout. The second
screen is the record of a run: lanes of agents over rows of files (`graph.py`).

The page can change the plan only when a person started `graphene ui` (started from an agent's
shell it is read-only and says so). A write needs the page's own origin and a token made for that
launch, sent in a header a cross-site form cannot set. Each control calls the same function in
`plan.py` as the command line does, a refusal is shown verbatim, and beside the scope, check and
sign-off fields the page prints where that mechanism ends (P5).

`graphene ui --export FILE` writes the same page as one file with its data inlined: paths, counts,
commit subjects, prompts, each agent's task, and the plan without its nodes' logs (a log can hold
the output of a check). It carries no token and cannot write. Every piece of text reaches the page
through `textContent`, and `</` is escaped inside the JSON, so nothing recorded can turn into markup.
