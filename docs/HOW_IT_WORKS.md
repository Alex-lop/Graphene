# How Graphene works

Graphene keeps a plan that you and your coding agents share, holds the agents to it, and keeps a record of each piece.

## The plan

The plan is a tree. Its root is your goal, one sentence (`graphene plan goal`). Each node under it is a row in the
store, `.graphene/graphene.db`, which git ignores.

A node with children is a **sub-goal**: it needs only a title, and nobody takes it. A node without children is a
**leaf**, the work (a **task**, on the screens). A leaf has:

- a **goal**: what it should achieve, in words;
- a **scope**: the globs it may write. `**` crosses directories, `*` stays in one, a plain name covers what is under
  it, `!glob` takes paths back out, and the last match decides;
- a **check**: a shell command that exits 0 only when the leaf is done;
- what it **needs**: other nodes that must be done first;
- an **owner**: any agent, or a person's name; and whether a person must **sign it off**.

A leaf waits on what it needs and on what every node above it needs; a cycle is refused. Two leaves never write one
path, except by an offer you take. A check that runs another leaf's file waits on that leaf (a directory names every
file under it); one that runs a file only a later leaf makes is refused. When the last leaf under a sub-goal is done,
the sub-goal's own check runs, if it has one.

| State | Means |
| --- | --- |
| `proposed` | an agent suggested it; it binds nobody until you accept it |
| `open` | in the plan: ready when what it needs is done, waiting otherwise |
| `running` | someone holds it |
| `review` | its check passed and it waits for your sign-off: it asked for one, or `review: every` is set |
| `done` | finished |
| `dropped`, `archived` | out of the plan |

Agents propose. Only a person accepts, edits a contract, signs off, reopens, pauses or archives. Graphene tells an
agent from you by the variables its CLI sets: `CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CODEX_SESSION_ID`,
`CODEX_SANDBOX`, `AI_AGENT`, `GEMINI_CLI`, `CURSOR_AGENT`, and Graphene's own `GRAPHENE_NODE` and
`GRAPHENE_PLANNER`. `graphene plan log` lists every change and who made it.

`graphene plan --text` prints the plan as text; `graphene plan edit` opens it in your editor; an agent proposes
with `graphene plan propose -`. `-` is in the plan and `?` a proposal, indentation is the tree, and `[id]`
keeps an edit on its node; under a leaf, `scope:`, `check:`, `needs:`, `owner:` and `signoff:` are its contract,
and any other line is its goal. The board comes first:

```
goal: customers download their invoices as PDF
question: which PDF library?  [lib]
    default: weasyprint
    option: reportlab
    then: scope render + vendor/reportlab/**
risk: the invoice template has no test  [untested]
- the PDF renderer  [pdf]
  ? the invoice template  [template]
      scope: templates/invoice.html
      check: make lint
  ? render one invoice to PDF bytes  [render]
      scope: src/pdf/**, tests/pdf/**
      check: pytest tests/pdf
      needs: template
```

`graphene plan undo` puts back your last act.

## The board

Beside the tree, the planner puts up what the repository cannot answer: a `question` with the `default` it would
take and `option` lines, an `assume`, a `risk` or a `leave out`. Anyone may put up a `note`.

Only you answer:

| Command | Key | The item becomes |
| --- | --- | --- |
| `graphene board take ID` | `⏎` | `taken`: its default |
| `graphene board pick ID N` | `1`..`9` | `picked`: option N |
| `graphene board answer ID WORDS` | `a` | `answered`, in your words |
| `graphene board drop ID` | `d` | `dropped`: told to no one |
| `graphene board note WORDS --about ID` | `t` on a task | a note, told to its agent |

A default or an option may carry `then:` lines that change the plan when it is chosen: widen a scope, set a check,
add to a goal, drop a node, add a leaf. What you decide reaches every leaf it is about as a `decided:` line in that
leaf's contract.

You can answer nothing. What is left open takes its default when you accept the whole tree, start a run, or type
`graphene board take` with no id. A question with no default stays open, and so does a default that drops a node: it
waits for your own key.

`board: auto` (the default) shows it only while a question is open, `board: on` while any item is. In
`graphene watch` the open items are the first rows under the goal.

## The views

`graphene watch` opens the cockpit (`c`): what needs you first, then a row a task with its agent's number, kept
through a retry, and in numbers whether it is on track: activity, files written of allowed, checks passed,
seconds quiet. A write the gate stopped needs you too. Anything new that needs you rings the terminal, with a
desktop notice saying why (`notify: off` quiets it).

The key bar says what the keys do to the selected row: `⏎` its own move (accept, take the default, try again,
sign off), `A` accept every proposal, `t` tell its agent a line (a Claude Code session hears it with its next
write or command; a task nobody is on yet reads it when it starts), `w` widen the scope to the path the gate
stopped, `x` hand back a running task or reopen a finished one, `i` details (panes `1` to `4`; `c` there is the
diff). `g` is the graph from your goal down, `m` the map of the folders each task may write, its lens following
the plan's stage until `v` turns it. `Tab` goes on, `Esc` comes back, `?` lists every key and what the marks mean.

`--classic` (or a `--view`) opens the older screen: `graphene plan`'s outline, a row a node with its state's word
(∅ after a title: its check passes at the base, or fails outside its scope). `Tab` there, or `graphene plan
--view NAME`, shows the others:

- `tree` (`view_tree.py`) draws the plan top-down; too wide, it drops the titles, folds finished sub-goals, then
  lists each sub-goal's leaves down.
- `dag` (`view_dag.py`) draws the leaves left to right by their `needs`, the critical path bold.
- `time` (`view_time.py`) draws a lane for each held leaf, under one for your moves; a cell is what its executor
  mostly did then.

## Plan first

Plan first decides what happens when you ask a Claude Code session for something. Set it with `graphene plan first
on|auto|off`, or `P` in `graphene watch`. `graphene init` asks at a terminal and sets it to on when it cannot ask; a
repository already on auto stays auto. Accepting, `plan first off` and the other acts only you may do happen in a
terminal outside Claude Code: inside one, Graphene takes the caller for the agent.

- **On**: every ask is proposed and waits for you; the session cannot write until it holds a leaf. One leaf is one
  row in `graphene watch`: `⏎` accepts it; `R` runs what is ready.
- **Auto**: every ask is proposed. One leaf with a scope and a check, no board item and at most 8 paths is yours at
  once, accepted "by their prompt in the session". Anything else waits for you in `graphene watch`.
- **Off**: a quick change is done at once, as a leaf made from your prompt while a plan is in force; the session
  still proposes bigger work, or an asked-for plan, first.

Graphene reads none of your words to decide this.

## Ask

`graphene ask "…"` sends your paragraph to the planner, which reads the repository with read-only tools and answers
with a tree; Graphene adds it as proposals. `graphene node split ID` asks it to cut a leaf;
`--about ID` asks about one. In `graphene watch`, `:ask` alone opens your editor for the paragraph.

The planner's prompt (Nemotron's system prompt, version 6) tells it to read the
repository first, ask only what the code cannot settle, and put up at most three items, each a question or a risk. What
it is sure of goes in the leaf's goal.

The Nemotron planner answers in a strict JSON schema; Graphene repairs what needs no judgement and sends other
faults back, at most twice. An ask names its planner, calls and dollars at list price.
If every answer is refused, the last proposal is kept and the commands that add it are printed.

## Run

`graphene run` starts the ready leaves, one at a time by default, `--parallel N` for more. For each leaf it:

1. cuts a worktree, `.graphene/worktrees/<id>` on branch `graphene/<id>`, from where your checkout stands;
2. starts the executor there, with the leaf's contract and `GRAPHENE_NODE` set;
3. when the executor ends, looks at the leaf, not the exit code. If it is not done, Graphene runs `done` itself;
   refused, the executor tries again, up to three attempts;
4. commits the leaf's paths on its branch (`--no-verify`: your pre-commit and commit-msg hooks skip it) and merges
   it `--no-ff` into the branch you have checked out (your merge hooks run). The merge's message says what landed:
   the check and its result, the executor, its attempts and dollars, and the note a reopened leaf was sent back with.
   If other leaves landed since this one was cut, its check and theirs run on the merge first; one that
   fails leaves it in review. A leaf that needs a sign-off, or every leaf under `review: every`, is committed on
   its branch and waits in review: `⏎` in the cockpit, or `graphene node signoff`, makes the merge, checked the
   same way: a red check keeps it in review.

The run's first line says where it lands, with what, how wide and under what cap; its second says the worst case
(leaves, attempts, the cap) or that the executor has no cap. `--max-usd N` starts nothing past N dollars (each attempt
is held at its worst case, then settled at what it spent).
Then ready leaves' checks run at the base: one that passes there tests nothing; one whose runner is missing cannot
run here; an editable install a check would import is named; a reopened leaf's, which passed when it landed, is said
so. Each is a warning, said before the leaf starts anyway (`--no-precheck` skips them).

**Done** is the gate. Graphene asks git what changed since the leaf started; a path outside the scope is refused. Then
it runs the check in a fresh worktree of the leaf's state, so nothing the check writes lands in yours. If nothing in
the scope changed, it is not done; otherwise the leaf is done, or in review.

A leaf that comes back says why and offers the fix: `w` widens its scope, `b` adds a sibling leaf for the paths it
needed, `r` reopens the done leaf it found wrong and waits on it. Leaves whose scopes overlap never run at once; a
leaf waits until what it needs has landed; if git cannot merge, the leaf stops in review with its branch named.

What you say while a Claude Code session holds a leaf (`graphene board note --about ID`, or an answer) reaches
it with its next write or shell command, once; `node show` records it as told.

Ctrl-C, or `graphene run --stop` from another terminal, stops the executors and hands back every leaf that had not
passed; `graphene run --here` runs one leaf in your own checkout and commits nothing.

**What the scopes cost.** A path has one writer, and a check runs only what its leaf owns or what exists at the
base: that caps the width.

## The executors

`graphene init` chooses one planner and one executor for the repository. `--with` overrides it for one command.

- **Claude Code**: `claude -p --permission-mode acceptEdits --strict-mcp-config --max-budget-usd 2`, with
  `--output-format stream-json` for the meter. Its shell runs only `graphene node` and `graphene plan`, and it is
  told so; the hooks refuse its writes outside the scope before they happen. Your user-level plugins and hooks still
  reach it: `--setting-sources project,local` in `--with` keeps them, and your user settings, out.
- **Codex**: `codex exec --json --sandbox workspace-write`. Its sandbox keeps it to the checkout, not the scope; the
  scope holds at `done`.
- **Nemotron**: Graphene's own executor and planner on NVIDIA Nemotron through Nebius Token Factory (the optional
  extra `graphene-map[nemotron]`). Its tools refuse a write outside the scope; in a Sandbox it can write only the scope.
- **Any command**: `--with 'my-agent --flag'` gets the contract as its last argument; nothing holds it before the
  write.

Whoever executes, a person included, is held at `done` by the check and git.

## The meter

The meter reads each executor's own event stream as it runs: Claude Code's
`stream-json` and Codex's `--json` line by line; Nemotron writes its own rows. Any other command has no meter: it
shows time and its log's tail.

It logs rows on the leaf: `usage` for each turn (model, tokens, dollars at list price), `did` for each tool call,
`said` for what the agent says, and `ended` with the exit and seconds.
Claude Code's final report settles the dollars to what it says it cost. A Codex model with no list price says so.

The classic watch shows these on a running leaf's row, with two clocks: the agents' (how many run, their minutes,
the plan's dollars) and yours (your moves and their minutes).

**The bill line**: `graphene run` ends with one line, for every executor:
`run: 3 done · agents 41m, $2.8700 at list price · 2 of 3 at once · you: 4 moves, 2m`. `2 of 3 at once`: three
leaves ran, at most two together. With no meter, the dollars say "no meter". `graphene plan log` keeps the line as a
row.

`graphene node show` lists each attempt: executor, model, time, turns, tokens, dollars, exit, the cache it wrote
and read (Claude Code), what it read, edited and ran, and what was refused. A Claude Code executor is seen by the
hooks and by its stream: for the meter the stream wins, for the gate the hooks do, so a refused shell write may
count twice.

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
- A board answer changes the tree only through its `then:` lines, and a `never:` setting is told to the planner and
  checked nowhere.
- A protected path is kept from the model where Graphene reads for it. A local Nemotron command, or a planner without
  the hooks, can still read it.
- A Claude Code session holding a leaf is told once, when it tries to stop, that the leaf still runs; then it may
  stop. `graphene run`'s executors are held until their leaf is done or handed back.
- A write outside the repository is not limited, and a check runs with your environment: a file written there can
  change what it sees.
- A leaf that may edit a file its own check runs can make the check agree: `done` flags it, in the run and the
  record, and does not refuse it. Mark the leaf for sign-off, or set `review: every`, to read the diff first.
- `--max-usd` stops starts, not an attempt going: Claude Code may end a turn past its $2; Codex with no cap counts
  $3 an attempt until it is metered.
- The merge is not checked for a sandboxed leaf.
- Sign-offs take turns: one given while another runs waits for it to end.
- Under `review: every`, what needs a task waits for your sign-off, so an unattended run stops after the tasks that
  need nothing.

## The record

`graphene node show ID` prints a leaf's contract and then its record: each time it was held (who, when,
how it ended); what changed, from git, and the commit that landed it, with the `git revert -m 1` that takes it back
(`graphene node diff ID` prints the diff); its attempts, from the meter, with the agent's last words whole; the writes
the hooks refused and, apart from them, the commands the executor was refused; the check's result and its last line,
whether it also passed at the base, and a file the check runs that the leaf changed; and your moves on it. `graphene plan record` opens with one row a leaf: what it changed, where it landed, what it cost. It works for any executor.

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
| `review: off\|every` | `every`: a task whose check passes waits for your sign-off before it lands |
| `notify: on\|off` | Whether `graphene watch` rings, with a desktop notice, when something new needs you |

`graphene config` also names the planner, the executor and plan first.

## Privacy

- With Claude Code or Codex, Graphene sends nothing anywhere.
- Nemotron on Token Factory is an optional extra; what it sends is in [HACKATHON.md](HACKATHON.md).

## FAQ

**Isn't this just a todo list?** A todo list is flat. Here every leaf hangs from its goal, names its files, its
check and what it waits on, and holds its executor to them.

**Isn't a tree overkill for a one-line fix?** The agent proposes one leaf: one row in `graphene watch`, and `⏎`
accepts it. Under auto it is yours at once.

**How do I turn it off?** `graphene plan first off` lets a quick change through at once; `graphene init --remove`
takes the hooks out, and the recording with them.

## The rest

`graphene --help` lists nine commands. These work too, and `--help` after any of them says more.

- `graphene demo --cheat` plays a script that tries seven ways round the locks against the real hook, git and check:
  six refused, one flagged, at $0. A script, not a model.
- `graphene plan goal` sets the plan's goal, or prints it.
- `graphene plan prompts leaf|strict` sets what a prompt typed into a session means.
- `graphene plan ack` makes the uncommitted changes no leaf made yours.
- `graphene node start <id>` takes a node and prints its contract.
- `graphene node signoff <id>` signs off a node that waits for a person.
- `graphene node reopen <id>` sends a finished node back, with what is wrong.
- `graphene node split <id>` asks the planner to cut a leaf into smaller leaves.
- `graphene board park <id>` sets an item aside, told to nobody; `graphene board unpark <id>` opens it again.
- `graphene talk why|split|merge|another` asks the planner about a node.
- `graphene direction` prints the goals above your plans. Its subcommands change them.
- Nemotron extra only: `graphene key set|check|remove` keeps the Token Factory key; `plan cover`, `plan note`,
  `plan precheck` and `board lookup` put a question to Nano ([HACKATHON.md](HACKATHON.md)).
