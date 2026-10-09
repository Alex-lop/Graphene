# How Graphene works

Graphene keeps a plan that you and your coding agents share, holds the agents to it, and keeps a record of each piece.
This is the reference to read after the README.

## The plan

The plan is a tree. Its root is your goal, one sentence (`graphene plan goal`). Each node under it is a row in the
store, `.graphene/graphene.db`, which git ignores.

A node with children is a **sub-goal**: it needs only a title, and nobody takes it. A node without children is a
**leaf**, the work. A leaf has:

- a **goal**: what it should achieve, in words;
- a **scope**: the globs it may write. `**` crosses directories, `*` stays in one, a plain name covers what is under
  it, `!glob` takes paths back out, and the last match decides;
- a **check**: a shell command that exits 0 only when the leaf is done;
- what it **needs**: other nodes that must be done first;
- an **owner**: any agent, or a person's name; and whether a person must **sign it off**.

A leaf waits on what it needs and on what every node above it needs. A cycle is refused. Two leaves never write one
path, except by an offer you take. A check that runs another leaf's file waits on that leaf, and the plan
says so; a directory names every file under it. A check that runs a file only a later leaf makes is refused. When
the last leaf under a sub-goal is done, the sub-goal's own check runs, if it has one, and it is done too.

| State | Means |
| --- | --- |
| `proposed` | an agent suggested it; it binds nobody until you accept it |
| `open` | in the plan: ready when what it needs is done, waiting otherwise |
| `running` | someone holds it |
| `review` | its check passed and it waits for your sign-off |
| `done` | finished |
| `dropped`, `archived` | out of the plan |

Agents propose. Only a person accepts, edits a contract, signs off, reopens, pauses or archives. Graphene tells an
agent from you by the variables its CLI sets (`CLAUDECODE`, `CODEX_SESSION_ID`, `GRAPHENE_NODE`). `graphene plan
log` lists every change and who made it.

`graphene plan --text` prints the plan as text: `- title  [id]` is in the plan, `? title  [id]` a proposal, and
indentation is the tree. `graphene plan edit` opens it in your editor. `graphene plan undo` puts back your last act.

## The board

Beside the tree, the planner puts up what the repository cannot answer: a `question` with the `default` it would
take and `option` lines, an `assume`, a `risk` or a `leave out`. Anyone may put up a `note`. The planner is told to
put up at most three items, most important first.

Only you answer:

| Command | Key | The item becomes |
| --- | --- | --- |
| `graphene board take ID` | `y` | `taken`: its default |
| `graphene board pick ID N` | `1`..`9` | `picked`: option N |
| `graphene board answer ID WORDS` | `Enter` | `answered`, in your words |
| `graphene board drop ID` | `d` | `dropped`: told to no one |
| `graphene board note WORDS` | `a` | a note of yours |

A default or an option may carry `then:` lines that change the plan when it is chosen: widen a scope, set a check,
add to a goal, drop a node, add a leaf. What you decide reaches every leaf it is about as a `decided:` line in that
leaf's contract.

You can answer nothing. What is left open takes its default when you accept the whole tree, start a run, or type
`graphene board take` with no id. A question with no default stays open. So does a default that drops a node: it
waits for your own key, and the line that says what took its default names it.

When it shows is the `board` setting. Unset, `board: auto`: only while a question is open. `board: on`: while any
item is open. In `graphene watch` the open items are the first rows under the goal.

## The views

The outline is `graphene plan`'s print and `graphene watch`'s tree: one row a node, indented, with the word its state
reads as (proposed, ready, waiting, running, came back, review, done). Finished sub-goals fold into one row. `Tab` in
`graphene watch`, or `graphene plan --view NAME`, shows the others:

- `tree` (`view_tree.py`) draws the plan top-down, each parent centred over its children. When it is too wide it
  drops the titles, then folds sub-goals whose leaves are all done, then lists each sub-goal's leaves down, and only
  then gives up.
- `dag` (`view_dag.py`) draws only leaves, left to right, by the chain of `needs` before each. One column can run at
  once. The critical path is bold.
- `time` (`view_time.py`) draws a lane for each leaf that has been held, under one for your acts. Each cell is what
  the executor mostly did then: editing █, running ▓, reading ▒, talking ░, idle ─; a hold the meter cannot see is ━.
  Marks: ! refused, ✓ ✗ the check, ↩ came back, ◆ landed, ● running.

## Plan first

Plan first decides what happens when you ask a Claude Code session for something. Set it with `graphene plan first
on|auto|off`, or `P` in `graphene watch`. `graphene init` sets it to on; a repository already on auto stays auto.

- **On**: every ask is proposed in the plan first, and waits for you. The session cannot write until it holds a leaf.
  One leaf proposed is one row in `graphene watch`: `y` takes it, and runs it when an executor is chosen.
- **Auto**: every ask is proposed. One leaf with a scope and a check, no board item and at most 8 paths is yours at
  once, accepted "by their prompt in the session". Anything else waits for you in `graphene watch`.
- **Off**: nothing is proposed. What you ask for is done at once and recorded as a leaf made from your prompt.

Nothing reads your words to decide this.

## Ask

`graphene ask "…"` sends your paragraph to the planner. The planner reads the repository with read-only tools and
prints a tree in the plan's text. Graphene adds it as proposals. `graphene node split ID` asks it to cut a leaf;
`--about ID` asks about one.

The planner's prompt (`ask.RULES`, and the Nemotron planner's system prompt, version 6) tells it to read the
repository first, ask only what the code cannot settle, and put up at most three items, each a question or a risk. An
assumption it is sure of goes in the goal of the leaf it bears on.

The Nemotron planner answers in a strict JSON schema. Graphene repairs what needs no judgement; other faults go
back together, at most twice. The Claude Code planner's stream says what it cost.

How many leaves it is asked for follows the repository's size: 1 to 3 under 2,000 lines, up to 6 under 20,000, up to
10 past that. The `size` setting makes that finer or coarser.

## Run

`graphene run` starts the ready leaves, one at a time by default, `--parallel N` for more. For each leaf it:

1. cuts a worktree, `.graphene/worktrees/<id>` on branch `graphene/<id>`, from where your checkout stands;
2. starts the executor there, with the leaf's contract and `GRAPHENE_NODE` set;
3. when the executor ends, looks at the leaf, not the exit code. If the leaf is not done, Graphene runs `done`
   itself. Refused, the executor gets the refusal and tries again, up to three attempts;
4. commits the leaf's paths on its branch and merges it `--no-ff` into your checkout, with the leaf's why in the
   message.

**Done** is the gate. Graphene asks git what changed since the leaf started. A path outside the scope is refused. Then
it runs the check in a fresh worktree of the leaf's state, so nothing the check writes lands in yours. If nothing in
the scope changed, it is not done. Otherwise the leaf is done, or in review.

A leaf that comes back says why, and offers the fix: `w` widens its scope, `b` adds a sibling leaf for the paths it
needed. Two leaves whose scopes overlap never run at once. A leaf waits until what it needs has landed. If git cannot
merge, the leaf stops in review with its branch named.

Ctrl-C stops the executors and hands back every leaf that had not passed. `graphene run --here` runs one leaf in your own
checkout and commits nothing.

**What the scopes buy and cost.** A path has one writer. A check runs only what its leaf owns or what exists at the
base. That is the contract. It caps the width. How the repository's files split decides how many leaves run at once.
The typical shape is a few leaves side by side, then a chain.

## The executors

`graphene init` chooses one planner and one executor for the repository. `--with` overrides it for one command.

- **Claude Code**: `claude -p --permission-mode acceptEdits`, with `--output-format stream-json` for the meter. The
  hooks refuse its writes outside the scope before they happen.
- **Codex**: `codex exec --json --sandbox workspace-write`. Its sandbox keeps it to the checkout, not the scope; the
  scope holds at `done`.
- **Nemotron**: Graphene's own executor and planner, on NVIDIA Nemotron through Nebius Token Factory. An optional
  extra (`graphene-map[nemotron]`). Its tools refuse a write outside the scope. It can run in a Token Factory Sandbox,
  as a user who can write only the scope.
- **Any command**: `--with 'my-agent --flag'`. It gets the contract as its last argument. Nothing holds it before the
  write.

Whoever executes, a person included, is held at `done` by the check and git.

## The meter

The meter reads each executor's own event stream as it runs (`src/graphene_map/meter.py`). Claude Code's
`stream-json` and Codex's `--json` are read line by line. Nemotron writes its own rows. Any other command has no
meter: it shows time and its log's tail, and says "no meter".

It logs rows on the leaf: `usage` for each turn (model, tokens, dollars at list price), `did` for each tool call
(reading, editing, running, searching), `said` for what the agent says, and `ended` with the exit and seconds.
Claude Code's final report settles the dollars to what it says it cost. A Codex model with no list price says so.

**In `graphene watch`**, each running leaf has a live row: executor and model, time, dollars, turns, files touched
(and how many outside the scope), tokens, and what it did last.

**The two clocks**, in the status line:

- **agents**: how many run now, their minutes summed over every attempt, and the plan's dollars at list price;
- **you**: your acts (accepted, dropped, edited, answered, a setting) and the minutes that hold at least one. It is
  counted by your keys: what you did, not what you read.

**The bill line**: `graphene run` ends with one line, for every executor:
`run: 3 done · agents 41 min, $2.8700 at list price · width 2 of 3 · you 4 acts, 2 min`. `width 2 of 3`: three leaves
ran, at most two at once. With no meter, the dollars say "no meter".

**`graphene node show`** lists each attempt: executor and model, time, turns, tokens, dollars, exit, then what it
read, edited and ran, what was refused, and what it said last.

**Which record wins.** A Claude Code executor is seen by the hooks and by its stream. For the meter, the stream
wins: turns, tokens, dollars and tool calls are counted from the stream only. For the gate, the hooks win: what was
refused and what was written are theirs. So each tool call is counted once. A session of yours, with no stream, has
only the hooks' record, and the meter says nothing about it.

## Where each mechanism ends

- A script that opens files itself, or a write through an MCP server, is not seen by the hooks. Git catches both at
  `done`, but only while a leaf is held.
- A hook that crashes or times out lets the call through. That is the vendor's rule.
- "Only a person" rests on the environment. An agent that unsets its CLI's variables passes for you.
- The store is a file. A script that writes it directly is neither stopped nor noticed.
- What git ignores, nobody audits: an executor can write anything under an ignored directory.
- A check runs on what git tracks. A check that calls `.venv/bin/pytest` or reads a `.env` finds nothing; it makes
  its own environment (`uv run`, `npm ci`).
- Two scopes that overlap only on a file that does not exist yet are not seen until one leaf's `done`.
- `.claude/settings*.json` is not protected. An agent that removes the hook has removed it; `done` still holds.
- A board answer changes the tree only through its `then:` lines. Otherwise it is told, not enforced.
- A `never:` setting is told to the planner and checked nowhere.
- A protected path is kept from the model where Graphene reads for it. A local Nemotron command, or a planner without
  the hooks, can still read it.
- Claude Code ends a session after about 8 refused stops in a row. The leaf then stays running.

## The record

`graphene node show ID` prints a leaf's contract and then its record: each time it was held (who, from when to when,
how it ended); what changed, from git; its attempts, from the meter; what was refused; the check's result; and your
acts on it. It works for any executor, because it stands on the log, on git, and on the check Graphene ran itself.

Claude Code's hooks add one thing: which changed path traces to a write someone was recorded making. Without them,
every path is graded "to git alone". Where a count cannot be supported, it says "not computed" and why. It never
prints a zero it cannot stand behind.

The hooks write one row per event and exit 0 whatever happens; their errors go to `.graphene/ingest.log`. Graphene
reads no transcript.

## The settings

`graphene config` prints what you state once; `graphene config edit` changes it. Only you can.

| Setting | Does |
| --- | --- |
| `protected: GLOB, …` | No scope may cover it, and the planner is told never to read it |
| `readonly: GLOB, …` | No leaf may write it |
| `never: SENTENCE` | Told to the planner. Nothing enforces it |
| `size: auto\|finer\|coarser` | How many leaves the planner is asked for |
| `board: auto\|on` | When the board shows |

`graphene config` also names the planner, the executor and plan first. The Token Factory key lives in
`NEBIUS_API_KEY` or the system keychain (`graphene key set`), never in a file.

## Privacy

- With Claude Code or Codex, Graphene sends nothing anywhere.
- Nemotron on Token Factory is an optional extra; what it sends is in [HACKATHON.md](HACKATHON.md).

## FAQ

**Isn't this just a plan in a markdown file, or a todo list?** A plan in prose is read once. A todo list is flat: it
does not say why an item is there, what it may touch, or what proves it finished. Here every leaf hangs from the goal
it serves, names its files and its check, and says what it waits on. The executors are held to all of it.

**Isn't a tree overkill for a one-line fix?** Ask for "fix the typo in the header" and the agent proposes one leaf:
one row in `graphene watch`, and `y` takes it. Under auto it is yours at once. `P` turns plan first off if you would
rather it just act.

**What doesn't it catch?** Every limit is listed under "Where each mechanism ends".

## The rest

`graphene --help` lists nine commands. These work too, and `--help` after any of them says more.
Agents call some of them, such as `plan propose` and `node start`.

- `graphene plan propose -` adds a tree, written as `graphene plan --text` prints it.
- `graphene plan goal` sets the plan's goal, or prints it.
- `graphene plan record` prints the record of the whole plan.
- `graphene plan prompts leaf|strict` sets what a prompt typed into a session means.
- `graphene plan ack` makes the uncommitted changes no leaf made yours.
- `graphene plan seen` marks the plan as seen by you.
- `graphene plan changes` lists what others changed since you marked it seen.
- `graphene node start <id>` takes a node and prints its contract. An executor runs it first.
- `graphene node signoff <id>` signs off a node that waits for a person.
- `graphene node reopen <id>` sends a finished node back, with what is wrong.
- `graphene node split <id>` asks the planner to cut a leaf into smaller leaves.
- `graphene board park <id>` sets an item aside, told to nobody.
- `graphene board unpark <id>` opens a parked item again.
- `graphene talk why|split|merge|another` asks the planner about a node.
- `graphene direction` prints the goals above your plans. Its subcommands change them.
- `graphene ingest hook` records one hook event. The installed hooks call it.
- `graphene key set|check|remove` keeps the Token Factory key in the keychain. Nemotron extra only.
- `graphene plan cover` asks Nano which leaf carries each clause of your paragraph. Nemotron extra only.
- `graphene plan note` asks a model which leaf a note constrains. Nemotron extra only.
- `graphene plan precheck` runs each leaf's check before any work. Nemotron extra only.
- `graphene board lookup` asks Nano which open questions the repo answers. Nemotron extra only.
