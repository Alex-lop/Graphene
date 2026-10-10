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
  drops the titles, folds finished sub-goals, then lists each sub-goal's leaves down.
- `dag` (`view_dag.py`) draws only leaves, left to right, by the chain of `needs` before each. One column can run at
  once. The critical path is bold.
- `time` (`view_time.py`) draws a lane for each leaf that has been held, under one for your acts. Each cell is what
  the executor mostly did then: editing █, running ▓, reading ▒, talking ░, idle ─; a hold the meter cannot see is ━.
  Marks: ! refused, ✓ ✗ the check, ↩ came back, ◆ landed, ● running. In the outline, ∅ after a title flags a
  check: it passes at the base, or fails outside its scope.

## Plan first

Plan first decides what happens when you ask a Claude Code session for something. Set it with `graphene plan first
on|auto|off`, or `P` in `graphene watch`. `graphene init` asks at a terminal, one line per setting, and sets it to on when it cannot ask; a repository
already on auto stays auto. Accepting, `plan first off` and the other acts that are only yours happen in a terminal outside
Claude Code: inside one, Graphene takes the caller for the agent.

- **On**: every ask is proposed in the plan first, and waits for you. The session cannot write until it holds a leaf.
  One leaf proposed is one row in `graphene watch`: `y` takes it, and runs it when an executor is chosen.
- **Auto**: every ask is proposed. One leaf with a scope and a check, no board item and at most 8 paths is yours at
  once, accepted "by their prompt in the session". Anything else waits for you in `graphene watch`.
- **Off**: a quick change is done at once, as a leaf made from your prompt while a plan is in force; the session
  still proposes bigger work, or an asked-for plan, first.

Graphene reads none of your words to decide this.

## Ask

`graphene ask "…"` sends your paragraph to the planner, which reads the repository with read-only tools and answers
with a tree; Graphene adds it as proposals. `graphene node split ID` asks it to cut a leaf;
`--about ID` asks about one.

The planner's prompt (`ask.RULES`, and the Nemotron planner's system prompt, version 6) tells it to read the
repository first, ask only what the code cannot settle, and put up at most three items, each a question or a risk. An
assumption it is sure of goes in the goal of the leaf it bears on.

The Nemotron planner answers in a strict JSON schema. Graphene repairs what needs no judgement; other faults go
back together, at most twice. A Claude Code or Nemotron ask then names its planner, calls and dollars at list price.
When every answer is refused, the last proposal is kept, and the ask prints the commands that add it, once mended.

How many leaves it is asked for follows the repository's size; the `size` setting makes that finer or coarser.

## Run

`graphene run` starts the ready leaves, one at a time by default, `--parallel N` for more. For each leaf it:

1. cuts a worktree, `.graphene/worktrees/<id>` on branch `graphene/<id>`, from where your checkout stands;
2. starts the executor there, with the leaf's contract and `GRAPHENE_NODE` set;
3. when the executor ends, looks at the leaf, not the exit code. If it is not done, Graphene runs `done` itself;
   refused, the executor tries again, up to three attempts;
4. commits the leaf's paths on its branch (`--no-verify`: your pre-commit and commit-msg hooks skip it) and merges
   it `--no-ff` into the branch you have checked out (your merge hooks run). The merge's message says what landed:
   the check and its result, the executor, its attempts and dollars, and the note a reopened leaf was sent back with.

The run's first line says where it lands, with what, how wide and under what cap; `graphene watch` in another
terminal follows it live. Then ready leaves' checks run at the base: one that passes there proves nothing; one whose
runner is missing cannot run here; an editable install a check would import is named; a reopened leaf's, which
passed when it landed, is said so. Each is a warning, said before the leaf starts anyway (`--no-precheck` skips them).

**Done** is the gate. Graphene asks git what changed since the leaf started; a path outside the scope is refused. Then
it runs the check in a fresh worktree of the leaf's state, so nothing the check writes lands in yours. If nothing in
the scope changed, it is not done; otherwise the leaf is done, or in review.

A leaf that comes back says why and offers the fix: `w` widens its scope, `b` adds a sibling leaf for the paths it
needed, `r` reopens the done leaf it found wrong and waits on it. Leaves whose scopes overlap never run at once; a
leaf waits until what it needs has landed; if git cannot merge, the leaf stops in review with its branch named.

Ctrl-C stops the executors and hands back every leaf that had not passed; `graphene run --here` runs one leaf in your
own checkout and commits nothing.

**What the scopes buy and cost.** A path has one writer, and a check runs only what its leaf owns or what exists at
the base: that is the contract, and it caps the width. The typical shape is a few leaves side by side, then a chain.

## The executors

`graphene init` chooses one planner and one executor for the repository. `--with` overrides it for one command.

- **Claude Code**: `claude -p --permission-mode acceptEdits --strict-mcp-config --max-budget-usd 2`, with
  `--output-format stream-json` for the meter. Its shell runs only `graphene node` and `graphene plan`, and it is
  told so. The hooks refuse its writes outside the scope before they happen. Your user-level plugins and hooks still
  reach it; `--setting-sources project,local` in `--with` keeps them out, and your user-level settings with them.
- **Codex**: `codex exec --json --sandbox workspace-write`. Its sandbox keeps it to the checkout, not the scope; the
  scope holds at `done`.
- **Nemotron**: Graphene's own executor and planner on NVIDIA Nemotron through Nebius Token Factory, an optional
  extra (`graphene-map[nemotron]`). Its tools refuse a write outside the scope; in a Token Factory Sandbox it runs as
  a user who can write only the scope.
- **Any command**: `--with 'my-agent --flag'` gets the contract as its last argument; nothing holds it before the
  write.

Whoever executes, a person included, is held at `done` by the check and git.

## The meter

The meter reads each executor's own event stream as it runs (`src/graphene_map/meter.py`): Claude Code's
`stream-json` and Codex's `--json` line by line; Nemotron writes its own rows. Any other command has no meter: it
shows time and its log's tail, and says "no meter".

It logs rows on the leaf: `usage` for each turn (model, tokens, dollars at list price), `did` for each tool call
(reading, editing, running, searching), `said` for what the agent says, and `ended` with the exit and seconds.
Claude Code's final report settles the dollars to what it says it cost. A Codex model with no list price says so.

**In `graphene watch`**, each running leaf has a live row: executor and model, time, dollars, turns, files touched
(and how many outside the scope), tokens, and what it did last.

**The two clocks**, in the status line:

- **agents**: how many run now, their minutes summed over every attempt, and the plan's dollars at list price;
- **you**: your acts (accepted, dropped, edited, answered, a setting) and the minutes that hold at least one: what
  you did, not what you read.

**The bill line**: `graphene run` ends with one line, for every executor:
`run: 3 done · agents 41 min, $2.8700 at list price · width 2 of 3 · you 4 acts, 2 min`. `width 2 of 3`: three leaves
ran, at most two at once. `you` counts your acts since the plan's last run, or since it began. With no meter, the
dollars say "no meter". `graphene plan log` keeps the line as a row, and the goal's pane in `graphene watch` shows
the last.

**`graphene node show`** lists each attempt: executor and model, time, turns, tokens, dollars, exit, then what it
read, edited and ran, what was refused, and what it said last.

**Which record wins.** A Claude Code executor is seen by the hooks and by its stream. For the meter the stream wins
(turns, tokens, dollars, tool calls); for the gate the hooks win (what was refused and written). A refused shell
write may count twice. A session of yours, with no stream, has only the hooks' record.

## Where each mechanism ends

- A script that opens files itself, or a write through an MCP server, is not seen by the hooks. Git catches both at
  `done`, but only while a leaf is held.
- A hook that crashes or times out lets the call through: the vendor's rule.
- "Only a person" rests on the environment: an agent that unsets its CLI's variables passes for you.
- The store is a file; a script that writes it directly is neither stopped nor noticed.
- What git ignores, nobody audits: an executor can write anything under an ignored directory.
- A check runs on what git tracks, with your PATH. A `.venv/bin/pytest` or a `.env` is not there. A `python3` whose
  venv holds this repository installed editable imports your checkout, not the leaf's tree: red first names it, and
  `uv run pytest …` builds the tree's own environment.
- Two scopes that overlap only on a file that does not exist yet are not seen until one leaf's `done`.
- `.claude/settings*.json` is not protected. An agent that removes the hook has removed it; `done` still holds.
- A board answer changes the tree only through its `then:` lines. Otherwise it is told, not enforced.
- A `never:` setting is told to the planner and checked nowhere.
- A protected path is kept from the model where Graphene reads for it. A local Nemotron command, or a planner without
  the hooks, can still read it.
- A Claude Code session holding a leaf is told once, when it tries to stop, that the leaf still runs; then it may
  stop. `graphene run`'s executors are held until their leaf is done or handed back.

## The record

`graphene node show ID` prints a leaf's contract and then its record: each time it was held (who, from when to when,
how it ended); what changed, from git, and the commit that landed it (`graphene node diff ID` prints the diff); its
attempts, from the meter, with the agent's last words whole; the writes the hooks refused and, apart from them, the
commands the executor was refused; the check's result and its last line, and whether it also passed at the base; and
your acts on it. It works for any executor, because it stands on the log, on git, and on the check Graphene ran itself.

Claude Code's hooks add one thing: which changed path traces to a recorded write. Without them every path is graded
"to git alone"; a count that cannot be supported says "not computed" and why.

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

`graphene config` also names the planner, the executor and plan first; the Token Factory key lives in
`NEBIUS_API_KEY` or the keychain (`graphene key set`), never in a file.

## Privacy

- With Claude Code or Codex, Graphene sends nothing anywhere.
- Nemotron on Token Factory is an optional extra; what it sends is in [HACKATHON.md](HACKATHON.md).

## FAQ

**Isn't this just a plan in a markdown file, or a todo list?** A todo list is flat. Here every leaf hangs from the goal
it serves, names its files and its check, says what it waits on, and the executors are held to it.

**Isn't a tree overkill for a one-line fix?** Ask for "fix the typo in the header" and the agent proposes one leaf:
one row in `graphene watch`, and `y` takes it. Under auto it is yours at once. `P` turns plan first off.

**How do I turn it off?** `graphene plan first off`, at a terminal, lets a quick change through at once (bigger work
is still proposed); `graphene init --remove` takes the hooks out, and the recording with them.

**What doesn't it catch?** Every limit is listed under "Where each mechanism ends".

## The rest

`graphene --help` lists nine commands. These work too, and `--help` after any of them says more.

- `graphene plan propose -` adds a tree, written as `graphene plan --text` prints it.
- `graphene node diff <id>` prints what a leaf changed: its landed merge, its branch in review, or the files it
  finished in your checkout.
- `graphene init --remove` takes Graphene's hooks out of the repository's Claude Code settings.
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
- Nemotron extra only: `graphene key set|check|remove` keeps the Token Factory key in the keychain; `graphene plan
  cover` asks Nano which leaf carries each clause of your paragraph; `graphene plan note` asks which leaf a note
  constrains; `graphene plan precheck` runs each check before any work; `graphene board lookup` asks which open
  questions the repo answers.
