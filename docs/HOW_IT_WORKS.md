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

Agents propose. Only a person accepts, edits a contract, signs off, reopens, pauses or archives; with `auto: on`,
Graphene accepts for you what fits the envelope you set, logged as yours (`by: auto`). Graphene tells an
agent from you by the variables its CLI sets: `CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CODEX_SESSION_ID`,
`CODEX_SANDBOX`, `AI_AGENT`, `GEMINI_CLI`, `CURSOR_AGENT`, and Graphene's own `GRAPHENE_NODE` and
`GRAPHENE_PLANNER`. `graphene plan log` lists every change and who made it.

`graphene plan --text` prints the plan as text; `graphene plan edit` opens it in your editor; an agent proposes
with `graphene plan propose -`. `-` is in the plan and `?` a proposal, indentation is the tree, and `[id]`
keeps an edit on its node; under a leaf, `scope:`, `check:`, `needs:`, `owner:`, `signoff:` and `forks:` are its
contract, and any other line is its goal. The board comes first:

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

`board: auto` (the default) shows it while a question, or a note an agent put up, is open; `board: on` while any
item is. In `graphene watch` the open items are the first rows under the goal.

## The views

`graphene watch` opens the cockpit (`c`): what needs you first, then a row a task, numbered in the order the tasks
were taken and kept through a retry, and in numbers whether it is on track: activity, files written of allowed,
checks passed, seconds quiet. A write the gate stopped needs you too. A new question, a task that came back, a
sign-off or a stopped write rings the terminal, with a desktop notice saying why where the terminal shows one
(iTerm2, WezTerm, Ghostty; Terminal.app only rings); a batch of proposals that brings no question rings once
(`notify: off` quiets it).

The key bar says what the keys do to the selected row: `⏎` its own move (accept, take the default, try again,
sign off), `A` accept every proposal, `t` tell its agent a line (a Claude Code session hears it with its next
write or command; a task nobody is on yet reads it when it starts), `w` widen the scope to the path the gate
stopped, `x` hand back a running task or reopen a finished one, `f` fork it (N agents at once, the check keeps
one), `i` details (panes `1` to `4`; `c` there is the diff). `g` is the graph: what must land before what,
flowing into your goal at the right (columns are waves, sub-goals lanes, the longest chain double); `m` the map
of the folders each task may write, its lens following the plan's stage until `v` turns it. On the graph `+`
adds a step after the selected task, and `L` on one task, then on another, makes the second wait on the first.
`Tab` goes on, `Esc` comes back, `?` lists every key and what the marks mean.

`--classic` (or a `--view`) opens the older screen: `graphene plan`'s outline, a row a node with its state's word
(∅ after a title: its check passes at the base, or fails outside its scope). `Tab` there, or `graphene plan
--view NAME`, shows the others:

- `tree` (`view_tree.py`) draws the plan top-down; too wide, it drops the titles, folds finished sub-goals, then
  lists each sub-goal's leaves down.
- `dag` (`view_dag.py`) draws the leaves left to right by their `needs`, the critical path bold; `time`
  (`view_time.py`) a lane for each held leaf under one for your moves, a cell what its executor mostly did then.

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

The planner's prompt (Nemotron's system prompt, version 7) tells it to read the
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
   the check and its result, the executor, attempts and dollars, and a reopened leaf's note.
   If other leaves landed since this one was cut, its check and theirs run on the merge first; one that
   fails leaves it in review. A leaf that needs a sign-off, or every leaf under `review: every`, is committed on
   its branch and waits in review: `⏎` in the cockpit, or `graphene node signoff`, makes the merge, checked the
   same way: a red check keeps it in review.

The run's first line says where it lands, with what, how wide and under what cap; its second says the worst case
(leaves, attempts, the cap) or that the executor has no cap. `--max-usd N` starts nothing past N dollars (each attempt
is held at its worst case, then settled at what it spent).
Then each ready leaf's check runs at the base, and a warning names one that passes there (it tests nothing), a
runner that is missing, an editable install it would import, or a reopened leaf's that passed when it landed;
the leaf starts anyway (`--no-precheck` skips them).

**Done** is the gate. Graphene asks git what changed since the leaf started; a path outside the scope is refused. Then
it runs the check in a fresh worktree of the leaf's state, so nothing the check writes lands in yours. If nothing in
the scope changed, it is not done; otherwise the leaf is done, or in review.

A leaf that comes back says why and offers the fix: `w` widens its scope, `b` adds a new task for the paths it
needed, `r` reopens the done leaf it found wrong and waits on it (it asks first). Leaves whose scopes overlap never run at once; a
leaf waits until what it needs has landed; if git cannot merge, the leaf stops in review with its branch named.

Ctrl-C, or `graphene run --stop` from another terminal, stops the executors and hands back every leaf that had not
passed; `graphene run --here` runs the leaves one at a time in your own checkout (`--node ID` for one) and commits
nothing.

One run goes in a repository at a time: a second `graphene run`, or `R` in the cockpit, hands its leaves to the
run going (one with its own `--with`, `--attempts` or `--max-usd` is refused). A leaf that came back is taken again
once you widen it, reopen it, or press `⏎` on it.

**What the scopes cost.** A path has one writer, and a check runs only what its leaf owns or what exists at the
base: that caps the width.

## Forks

A leaf can run as several agents at once, each in a copy of its own; its check keeps one. `forks: 3` under the
leaf in `graphene plan edit` (or `graphene node set ID --forks 3`), `graphene run --forks 3` for a run, or
`forks: 3` in `graphene config edit` for every leaf: the leaf's number counts first, then the run's, then the
setting; never fewer than the `--with`s; 8 at most. A leaf with no check runs as one agent; forks with a
sign-off alone, and `--here`, are refused. `--with` more than once gives each fork its executor, round robin;
`claude:MODEL` and `codex:MODEL` name a model.

A fork is a worktree, `.graphene/worktrees/<id>.<letter>`, with its own session, attempts and meter rows, told
`This is fork b of 3`. It is held as a leaf is, in its own copy alone (with Claude Code, a write into the leaf's
tree, another fork's copy or your checkout is refused): its `graphene node done` judges its own tree and changes
no state, its `release` is its giving up, what you tell the task reaches each fork, and its tree is judged as it
stands when its executor ends.

Then the rule in `src/graphene_map/pick.py`, written before any fork ran, keeps one. Only a fork whose check
passed, inside its scope, can be kept; each step breaks only the ties of the step before, and the reason names
the step:

1. agreement: it passes the most of the other passing forks' tests (its test files laid over another's tree,
   under the leaf's check; a fork's own tests count for nobody): `passes a's tests (a and c fail b's)`;
2. the check left alone: it changed no file its check ran at the base: `left the check's own files as they were
   (c changed tests/test_ids.py)`;
3. smaller: the fewest lines changed outside tests: `2 lines against 11`;
4. cheaper: the fewest dollars, to the cent; no meter, no step: `$0.52 against $0.61`;
5. sooner: `finished first`.

The run says `n1 kept b of 3: 2 lines against 11`, copies that fork's changes inside the scope into the leaf's
tree and finishes it there once, so it lands as any leaf does (the merge says `3 forks, kept b`); `--first`
keeps the first fork whose check passes and stops the rest; none passed, the leaf comes back with each fork's
reason. What each fork changed stays on `refs/graphene/forks/<id>/<letter>`, and `graphene node diff ID --fork
c` prints it; on a leaf in review, `graphene node pick ID c` makes its branch fork c's work, and the sign-off
lands it. The worst-case line multiplies by the forks (`1 leaf x 3 forks x 1 attempt x $2 = $6`).

In `graphene watch`, `f` on a task still to do sets `forks: N` (the setting's number when it is 2 or more, else
3) and runs it; its row says `3 forks` and opens to a line a fork; once one landed, a dim line says `kept b ·
<the reason>`; in review the digits pick another (`1-3 pick`); the record pane has the forks table; the graph's
box says `3 ×3` while they run.

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
  The same loop runs on another host with `--endpoint`: `nim` (NVIDIA's API catalog, `NVIDIA_API_KEY`), `ollama`
  (this machine, no key) or `openai` (any OpenAI-compatible URL in `GRAPHENE_OPENAI_BASE_URL`, key
  `GRAPHENE_OPENAI_API_KEY` or `OPENAI_API_KEY`: vLLM, OpenRouter, LM Studio), as `--with 'nemotron --endpoint nim'`
  or `graphene init --executor 'nemotron --endpoint nim'`; `graphene key set --endpoint nim` keeps that host's key.
  A host that lists no Nemotron uses `--model`, else the first model it lists, and says which. A model with no list
  price is billed as "no list price", not $0, and counts $0 against every cap. NIM and any URL off this machine
  spend, so an agent's call to them is refused without your opening, as Token Factory's is; Ollama and a local
  URL are stand-ins. Every row names the host that answered.
- **Any command**: `--with 'my-agent --flag'` gets the contract as its last argument. A command that takes it
  elsewhere says where: `{prompt}` is replaced by the contract, `{prompt_file}` by the path of a file holding it,
  written under `.graphene/runs/`, outside every scope. Recipes, not tested here: `aider --yes --message-file
  {prompt_file}`, `gemini --yolo -p {prompt}`, `opencode run {prompt}`, `goose run -t {prompt}`. Nothing holds
  such an agent before the write: the scope holds at `done`, when git says what changed, and a write outside it
  is refused there, with the paths named, before the check runs.

Every executor a run starts gets `PORT` and `GRAPHENE_PORT`, a port of its own (distinct per running task and per
fork, free when it is handed out), said in its contract and given to its check, so a task that starts a server
binds one no other task has.

Whoever executes, a person included, is held at `done` by the check and git.

## The meter

The meter reads each executor's own event stream as it runs: Claude Code's
`stream-json` and Codex's `--json` line by line; Nemotron writes its own rows. Any other command has no meter: it
shows time and its log's tail.

It logs rows on the leaf: `usage` for each turn (model, tokens, dollars at list price), `did` for each tool call,
`said` for what the agent says, and `ended` with the exit and seconds.
Claude Code's final report settles the dollars to what it says it cost. A Codex model with no list price says so.

The classic watch shows them on a running leaf's row.

**The bill line**: `graphene run` ends with one line, for every executor:
`run: 3 done · agents 41m, $2.8700 at list price · 2 of 3 at once · you: 4 moves, 2m`. `2 of 3 at once`: three
leaves ran, at most two together. With no meter, the dollars say "no meter". `graphene plan log` keeps the line as a
row.

A Claude Code executor is seen by the hooks and by its stream: for the meter the stream wins, for the gate the
hooks do, so a refused shell write may count twice.

## Where each mechanism ends

- A script that opens files itself, or a write through an MCP server, is not seen by the hooks. Git catches both at
  `done`, but only while a leaf is held.
- A hook that crashes or times out lets the call through on a Claude Code before 2.1.295, or where `graphene
  init` ran from a script: the vendor's rule. From 2.1.295, `init` at a terminal makes the gate fail closed
  (`"onFailure": "block"`) and says so. A call the hook cannot judge is refused either way (`Graphene could not
  judge this call …`), with its error logged.
- The hook reads a shell command as written: `cd`, comments, heredocs, the redirects and the usual writers
  (`tee`, `cp`, `mv`, `dd`, `install`, `sed -i`), under `sudo`, `env` or `nice`, to `$PWD`, `$HOME` or a variable
  the command set. A target in another variable, a glob or `$(…)`, a link in the scope that leads out of it, or
  a cwd that is a checkout of its own is not seen before the write; git finds each at `done`. A target outside
  the repository (`> /tmp/pytest.log`) is nobody's to judge; the rest still is.
- "Only a person" rests on the environment: an agent that unsets its CLI's variables passes for you.
- The store is a file; a script that writes it directly is neither stopped nor noticed.
- What git ignores, nobody audits: an executor can write anything under an ignored directory.
- A check runs on what git tracks, with your PATH. A `.venv/bin/pytest` or a `.env` is not there. A `python3` whose
  venv holds this repository installed editable imports your checkout, not the leaf's tree: red first names it, and
  `uv run pytest …` builds the tree's own environment.
- Two scopes that overlap only on a file that does not exist yet are not seen until one leaf's `done`.
- `.claude/settings*.json` is not protected. An agent that removes the hook has removed it; `done` still holds.
  The envelope never takes a task that reaches it, and `.git/` is nobody's: no scope reaches it, and no write there
  is let through, since a hook planted in `.git/hooks/` would run on your next commit.
- A board answer changes the tree only through its `then:` lines, and a `never:` setting is told to the planner and
  checked nowhere.
- A protected path is kept from the model where Graphene reads for it. A local Nemotron command, or a planner without
  the hooks, can still read it.
- A Claude Code session holding a leaf is told once, when it tries to stop, that the leaf still runs; then it may
  stop. `graphene run`'s executors are held until their leaf is done or handed back.
- A write outside the repository is not limited, and a check runs with your environment: a file written there can
  change what it sees.
- The envelope decides what is accepted, not whether the work is good: the checks do, and they are as good as your
  tests. Nemotron bills a call after it ends, so `graphene auto` reads its budget between rounds; an executor that
  reports no cost is counted in attempts.
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
how it ended; forked, `forked 3 ways · kept b: …` and a line a fork); what changed, from git, and the commit
that landed it, with the `git revert -m 1` that takes it back (`graphene node diff ID` prints the diff); its
attempts, from the meter, with the agent's last words whole; the writes the hooks refused and, apart from them,
the commands the executor was refused; the check's result and its last line, whether it also passed at the
base, and a file the check runs that the leaf changed; and your moves on it. `graphene plan record` opens with
one row a leaf: what it changed, where it landed (`3 forks, kept b`), what it cost. It works for any executor.

Claude Code's hooks add one thing: which changed path traces to a recorded write. Without them every path is graded
"to git alone"; a count that cannot be supported says "not computed" and why.

The hooks write one row per event and exit 0 whatever happens; their errors go to `.graphene/ingest.log`. Graphene
reads no transcript.

## The settings

`graphene config` prints what you state once; `graphene config edit` changes it, and `graphene config set KEY VALUE` changes one. Only you can.

| Setting | Does |
| --- | --- |
| `protected: GLOB, …` | No scope may cover it, and the planner is told never to read it |
| `readonly: GLOB, …` | No leaf may write it |
| `never: SENTENCE` | Told to the planner. Nothing enforces it |
| `size: auto\|finer\|coarser` | How many leaves the planner is asked for |
| `board: auto\|on` | When the board shows |
| `review: off\|every` | `every`: a task whose check passes waits for your sign-off before it lands |
| `notify: on\|off` | Whether `graphene watch` rings, with a desktop notice where the terminal shows one, when something new needs you |
| `forks: 1\|2\|3\|4\|5\|6\|7\|8` | Agents at once on each leaf that says nothing itself; its check keeps one |
| `auto: off\|on` | `on`: a proposal that fits the envelope (every task with a scope and a check, the board settled, under `tasks`, no scope reaching `.claude/`, `.codex/`, `.cursor/`, `.gemini/` or `.github/workflows/`) is accepted for you at once, from any agent; `graphene auto` turns it on |
| `budget: DOLLARS` | What every run may spend while `auto` is on, `graphene auto`'s, an agent's own `graphene run` and `R` alike |
| `tasks: N` | How many tasks the envelope may accept for you, all told, since `auto` went on (12 unset) |
| `rounds: N` | Fix rounds `graphene auto` takes after the goal's check fails (2 unset) |
| `checks: COMMAND, …` | The commands the envelope runs as a task's check without you; unset, any one plain command (no `;`, `&&`, `\|`, redirect or `$(…)`) |

`graphene config` also names the planner, the executor and plan first.

`graphene auto "<goal>"` turns `auto` on (its flags set `budget`, `tasks`, `rounds` and `forks`) and runs the
loop: the planner's tree hangs under a root task that carries the goal's check (`--check`, else every task's
check together); what fits the envelope is accepted at once, run and landed, unless its check passes before any
work (it would land with nothing done, so it waits for you); a red goal check is planned again, for `rounds` rounds. Exit 0 when the goal's check passes, 1 when it is still red, the budget is spent or you
stopped it, 3 when something waits for you. With no goal it goes on with the plan in force. Each stage is a row
of the plan's log (`graphene plan log`), and the cockpit's head says the round, its stage and the budget. In
`graphene watch`, `:auto <goal>` starts it as a process of its own, and `:stop` stops it. `--plan` plans and
accepts inside the envelope, runs nothing, and leaves the round for `graphene auto` to run.

## Privacy

- With Claude Code or Codex, Graphene sends nothing anywhere.
- Nemotron on Token Factory is an optional extra; what it sends is in [HACKATHON.md](HACKATHON.md).
- Another host named with `--endpoint` (NVIDIA NIM, an OpenAI-compatible URL) is sent the same: the contract, the
  files the model reads, the output of the commands it runs. Ollama on this machine sends nothing off it.

## FAQ

**Isn't this just a todo list?** A todo list is flat. Here every leaf hangs from its goal, names its files, its
check and what it waits on, and holds its executor to them.

**Isn't a tree overkill for a one-line fix?** The agent proposes one leaf: one row in `graphene watch`, and `⏎`
accepts it. Under auto it is yours at once.

**How do I turn it off?** `graphene plan first off` lets a quick change through at once; `graphene init --remove`
takes the hooks out, which ends the recording; what they recorded stays until you delete it.

## The rest

`graphene --help` lists nine commands. These work too; `--help` after any says more.

- `graphene state --json`: one JSON snapshot for an editor; `plan log --json --since ID`: the log's rows after ID.

- `graphene demo --cheat` plays a script, not a model, that tries seven ways round the locks against the real hook,
  git and check: six refused, one flagged, at $0. `graphene demo --live` replays a live run on Nemotron through
  Token Factory (9 October), as it ran.
- `graphene plan prompts leaf|strict` sets what a prompt typed into a session means.
- `graphene plan ack` makes the uncommitted changes no leaf made yours.
- `graphene node start <id>` takes a node and prints its contract.
- `graphene node done <id>` finishes a leaf. One whose owner is you is done on your word, once its check passes.
- `graphene node signoff <id>` signs off a node that waits for a person.
- `graphene node reopen <id>` sends a finished node back, with what is wrong.
- `graphene node pick <id> <letter>` keeps another fork of a leaf in review, for its sign-off.
- `graphene node split <id>` asks the planner to cut a leaf into smaller leaves.
- `graphene board park <id>` sets an item aside, told to nobody; `graphene board unpark <id>` opens it again.
- `graphene talk why|split|merge|another` asks the planner about a node.
- `graphene direction` prints the goals above your plans. Its subcommands change them.
- Nemotron extra only: `graphene key set|check|remove` keeps the Token Factory key (`--endpoint nim|openai`,
  another host's); `plan cover`, `plan note`, `plan precheck` and `board lookup` put a question to Nano
  ([HACKATHON.md](HACKATHON.md)).
