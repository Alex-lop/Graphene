# Graphene for the Nebius × NVIDIA Global AI Hackathon: the Devpost fields (a draft)

*A draft for Alex, first written 2026-09-26 by the agent that ran the winning directive, and turned
around shaping on 2026-09-28 as `docs/process/field.md` asks ("Where Graphene differs" and "Claims the
submission must not make"). Put it in your own words before it goes anywhere. Track: Coding and
Agentic Engineering. Every sentence is meant to be true and traceable, and every number names its
source. **No number here comes from a live run.** No session that wrote this had a Token Factory
key, so the Nemotron path has run only against a scripted stand-in for Token Factory
(`tests/fake_tokenfactory.py`) and a Docker stand-in for Sandboxes. The fields that need the evidence
run say so and are left empty until it exists.*

<!-- For the coordinator: the board, the views, talking on the tree, the settings and the three
Nemotron prototypes are on `integ` tonight (at 50f12e7), not yet on `shaping` or `main`. Every
command that exists only there is marked "integ only" in a comment where it first appears. Check
each one after the merge, and send this text only once it is on main. -->

## Inspiration

The limit on building software with agents will not be tokens or their price. It will be the human
intervention the work takes. Token Factory sells tokens cheap enough to spend in bulk, but a cheap
model you cannot trust does not save your attention. It spends it: on reading diffs, and on cleaning
up after them. So the question a Token Factory customer is really asking is *how do I hand real work
to a cheap model and trust what comes back?*

Our bet is to spend your attention before anything runs (the board, our first try at that moment,
does not yet save it: see What we learned). However many
tokens an agent gets, it still has to guess what you meant, and with most agents you find out what it
guessed from the diff at the end. Graphene makes the moment between your paragraph and the first
line of code a place of its own. The plan is on screen as a tree. What the agent would otherwise have
guessed is on a board, as a question with a default. You shape both before anything is spent, and
then every leaf is held to the files it may change and a check that proves it done, and the check,
not the model, decides what lands.

We found no other entry where a person prunes the plan an agent proposed before anything runs
(`docs/process/field.md`, "Where Graphene differs", item 1). That moment is the product.

## What it does

You tell Graphene what you want in a paragraph. Nemotron 3 Ultra, through Token Factory, reads the
repository and proposes a tree: the goal at the top, sub-goals under it, and leaves, each with the
files it may change (its scope) and the command that proves it done (its check). Then you shape it.

**The board: the planner asks instead of guessing.** Beside the tree, the planner puts up what the
code cannot answer: questions, each with a default and its options, the assumptions it made, the
risks it sees and what it left out. You answer each with one command:
`graphene board take ID` for the default, `pick ID N` for an option, `drop`, `park` or `unpark`,
`answer ID …` in your own words, and `note …` for something of yours.
<!-- integ only: graphene board and every subcommand above (board_cli.py). -->
An option can carry an effect (`then: scope xml-reader + pyproject.toml`), and picking it edits the
plan as your own act, which `graphene plan undo` takes back. Every answer reaches the executors'
contracts as a `decided:` line, so the leaf's executor is told what you chose. Only the person
answers: an agent that tries is refused in one line (`tests/test_board.py`). Both planners, Claude
Code's and Nemotron's, were changed to ask this way (prompt version 2; for Nemotron,
`test_nemotron_is_told_to_ask_and_its_board_lands`, against the scripted stand-in).

**The graph: what runs at once and what waits.** You read the plan in `graphene watch`, a terminal
screen with vim keys. Tab cycles the outline, a top-down tree, and a left-to-right graph of the
leaves' needs, with the critical path drawn heavy and a note under it:
`2 at once · 2 wait · critical path: xml-reader > xml-wire > xml-e2e (3)` on a scratch plan of four
leaves. `graphene plan --view tree`, `dag`, `outline` or `auto` prints the same as text, and the page
`graphene ui` draws the same three.
<!-- integ only: Tab between views in graphene watch, graphene plan --view, graphene watch --view,
and the page's three layouts. -->

**You prune.** Drop a leaf you did not mean, take a path out of a scope, accept the rest, each with a
key (`d`, `e`, `y`).

**Talking on the tree.** `?` on a node asks the planner about it: `w` why, `s` split, `m` merge the
nodes you selected, `a` another way, or your own words. A why comes back as the planner's note on the
board. A merge or another way comes back as proposed leaves and a question on the board whose default
drops the way not taken, all one act you can undo. A row someone else changed since you last looked
reads `+` or `~` before its id, `graphene plan changes` lists what changed and by whom, and `m`
marks it seen.
<!-- integ only: ? on a node in graphene watch, graphene talk why|split|merge|another, graphene plan
changes, graphene plan seen, the m key. -->

**Settings you state once.** `graphene key set` keeps the Token Factory key in the system keychain,
read from a hidden prompt, and `graphene key check` says whether Token Factory answered and never
prints the key. `graphene config edit` holds the paths no scope may cover, the globs no leaf may
write, the lines the planner must never propose, and the plan's size (`auto`, `finer` or `coarser`).
A scope that covers a protected or read-only path is refused when it is proposed, edited or started,
a change to a read-only path is refused at `done`, and `graphene ask "…" --finer` sizes one ask.
<!-- integ only: graphene key set|check|remove, graphene config, graphene config edit, graphene ask
--finer/--coarser. -->

**Nemotron works for you while you shape.** Three prototypes, each a command and each run after a
proposal lands when `GRAPHENE_SHAPE` names it. Each makes one Nano call with a JSON schema. They are
built and tested against the scripted stand-in, and **none has run live yet**:
<!-- integ only: graphene plan cover, graphene plan note, graphene plan precheck, GRAPHENE_SHAPE. -->

- `graphene plan cover`: Nano reads your paragraph beside the plan and names the parts no leaf
  carries. Each comes back in your own words, with the command that puts it on the nearest leaf. A
  clause the model made up is dropped, because Graphene keeps only words that are in your paragraph
  (`tests/test_cover.py`).
- `graphene plan note "…"`: a loose sentence finds the one leaf it constrains and comes back as the
  exact `graphene node set` that would change that leaf. Graphene checks the change before showing
  it, and nothing changes until you run it (`tests/test_note.py`).
- `graphene plan precheck`: every proposed check runs at the starting commit, in a sandbox fork,
  before `R`. A check that passes already, or cannot run, says "done" of nothing, and is flagged.
  Nano reads only a red whose reason the exit code does not say. The fork has been a scripted runner
  and a Docker container, not yet a Token Factory Sandbox (`tests/test_precheck.py`).

They are the top three of 32 ideas, 20 after merging, scored by three judges
(`docs/process/ideas.md`).

**Then you press `R`.** Each ready leaf gets a Nemotron Nano executor, in a Token Factory Sandbox
forked from one checkpoint of your repository. A leaf that needs a file outside its scope comes back
with the reason and the fix already written: one key widens its scope, another makes a sibling leaf
for the file. When the tree is green, `git log --graph` reads as the tree, one merge per leaf with its
why in the message. Each leaf's bill is priced from Token Factory's own usage at list price.

Forks are there, and they are not the headline. `--forks N` runs N attempts at the same leaf from
that checkpoint, and the first whose check passes lands. When an attempt is refused, the next one
steps up to Nemotron Super. Forking candidates from one checkpoint and letting the check pick is the
most common pattern in this track (`docs/process/field.md`, "Where Graphene differs", item 3). On
screen, each fork is a row under its leaf, with its model and state. A step up the ladder is named on
the bottom line. The leaf's pane shows its sandbox and its bill, and its record says which fork won
and why the others did not (`docs/process/winning/screens/`, taken against the scripted stand-in).

A person who already has an agent never has to sign up for anything: `graphene init` lists what it
finds (Claude Code, Codex, a Token Factory key), each with what it needs, and none comes first.

## How we built it

- **Token Factory's API.** Two endpoints, called from the Python standard library
  (`src/graphene_map/tokenfactory.py`). No model id is written in the code: `GET
  /v1/models?verbose=true` names the Nemotron Ultra, Super and Nano, and its `pricing` prices every
  call's `usage`. When a model is retired, a stale id falls back to the nearest listed Nemotron, and
  one line says which was used instead of which. A 429, a 5xx and a timeout are retried, then
  reported with what to do. A ledger can cap the night's spend, refusing the next call before it is
  sent.
- **Nemotron's roles.** Ultra is the planner (`planner.py`). It has read-only tools (list, glob, grep,
  read) that run on the person's machine and read only what git shows, and it answers in Graphene's
  plan text. Nano, then Super, is the executor (`executor.py`). Graphene's own loop asks for one tool
  call at a time: view, edit, write, run, done, or release. The reasoning budget is each call's
  `max_tokens`, doubled up to 32,768 when a reply is cut off at the limit. Any other model parameter
  passes through with `--param`. Nemotron's `<TOOLCALL>` text and common tool-name spellings are read
  as the calls they mean. Since prompt version 2, Ultra is also told to read the repository first,
  never to ask what a file answers, and to put up the rest as questions with a default, assumptions,
  risks and leave-outs, about five at most (`planner.py`, `PROMPT_VERSION`).
- **Nano, while you shape.** Each of the three prototypes is one Nano call through
  `tokenfactory.chat`, with a JSON schema for its answer. Graphene checks the answer before showing
  anything: a clause must be in your paragraph, a leaf must exist and be open, a glob must match a
  tracked file, and a check's verdict comes from its exit code before any model reads it (`cover.py`,
  `note.py`, `precheck.py`). What reaches a leaf is your own words or a command you run, never text
  the model wrote.
- **Sandboxes' checkpoints and forks.** A clean commit is uploaded and set up once, as a checkpoint
  (`sandbox.py`, contree-sdk 0.3.6). Every leaf at that commit forks it and adds only its own
  permissions, and `--forks N` forks one leaf's sandbox N times. The executor's commands run there
  as a user who can write only the files the leaf's scope covers, through `setpriv`. What a command
  changes outside the scope is never brought back. The leaf's check runs in a fresh fork, on only
  what came back. At most fifty sandbox operations run at once from one machine, the beta's cap.
- **The boundary, three layers deep.** Layer one: the executor's write tools refuse a path outside
  the scope before touching it, in the same words the Claude Code hooks use. Layer two: in a
  sandbox, the operating system refuses it too. Layer three: a leaf is done only when Graphene runs
  the check itself and git shows nothing outside the scope. An escape test tries every way out (a
  redirect, `sed -i`, `python open(w)`, `mv`, `rm`, git, a symlink, `chmod`). Each fails, and every
  write inside the scope succeeds. So far that test has run in the Docker stand-in, not in ConTree
  (`tests/test_escape.py`).
- **The board and the views.** The board is kept in the plan's store beside the nodes, so `graphene
  plan undo` takes back an answer together with every edit its effects made, and the plan's text form
  carries the board through `graphene plan edit`. A view is drawn from the plan's nodes and never
  reads the store. In the graph, a leaf's column is the longest chain of needs before it, and a test
  traces every line back from its arrow on 150 random plans to show that none runs through a cell
  and each says a real need (`tests/test_view_dag.py`). The tree's layout is checked at 22 widths
  from 20 to 167 columns: every line fits and no two cells overlap (`tests/test_view_tree.py`).
- **The rest of the product.** `graphene watch` is built with Textual, and the plan is a SQLite
  store in the repository, ignored by git. The plan has a text form that round-trips through
  `$EDITOR`. Leaves run in parallel, each in a git worktree of its own, and are merged `--no-ff`.
  The exported page (`graphene ui --export`) is React, and draws the outline, the tree or the graph.
  The test suite runs in CI on Linux and macOS, on Python 3.12, 3.13 and 3.14.

## Challenges we ran into

- **Where the agent loop runs decides what can be refused.** We spiked both placements
  (`docs/test/spikes/harness_there/RESULTS.md`, against the stand-ins). With our own loop on the
  person's machine and the tools in the sandbox, an out-of-scope write was refused in Graphene's
  words before it happened, 3 runs of 3. With a harness inside the sandbox (OpenCode 1.18.31),
  Graphene never heard of it in 3 of 3. That harness also put the key where model-written code could
  read it, and sent 5.2 to 6.1 times the characters per leaf.
- **POSIX grants "may create" per directory, not per file.** So a sandboxed command can create a
  file the scope does not name, in a directory where the scope names another. Graphene never brings
  that file back, logs it as a breach, and removes it before the next command (decision 57 in
  `docs/DIRECTION.md`).
- **The judging period outlives model ids.** Judges may test until 15 December, and Token Factory
  retires models on notice. So roles come from the live list, and a retired id falls back within
  the family (decision 71).
- **A beta service, from the outside.** The SDK's docs describe an API no release has (below).
- **The one honest comparison we have did not favour the tree.** On 23 September, eight stand-in
  runs of the feeds task compared a plain paragraph with the tree, both on a frontier agent. The
  paragraph also passed 20 of 20 hidden acceptance checks and 12 of 12 held-out checks, and it cost
  less of the person's modelled time: 2,626 modelled person-seconds against 3,869, medians of two
  runs (`docs/test/results-2026-09-23.md`). A frontier agent does not need a tree to get a small task
  right. So the claim is not that a tree beats a paragraph by itself. We then measured the moment
  before anything runs, the board against the outline, and the board cost more (What we learned).
  What is left to test is the board against the paragraph, and a cheap model with the person's prune
  against the same paragraph sent to Nano with no tree (`docs/test/results-2026-09-28-live-prereg.md`).
- **The planner's questions were prose, and scrolled away.** On 28 September we put our own work
  through Graphene, with Claude Code as planner and executors and an agent standing in for the
  person (`docs/process/shaping/as-the-person.md`). After its tree the planner wrote about 250 words
  in five paragraphs that were really decisions for the person: a gap it could not close, a choice
  it made, a default it assumed, a collision, and what it left out. None was stored, and answering
  them meant holding them in your head while reading the tree (item 2). That is where the board came
  from.

## Accomplishments that we're proud of

- A complete product, not a demo. It has a terminal screen with vim keys, a board the planner asks
  on, the plan as an outline, a tree and a graph, a text form that round-trips, parallel leaves
  in worktrees, hand-backs that offer their own fix, a record for each leaf, a read-only web page,
  and docs that list what does not bind.
- Containment that is tested, not asserted. The escape test above holds in the Docker stand-in, and
  running it in ConTree is the first thing a key is for.
- Failure that reads as a sentence. A 429 storm, a 5xx, a timeout, a model that stops calling tools,
  a sandbox killed mid-leaf and a check that hangs each bring the leaf back with its cause and what
  to do. The run goes on, and nothing is left running (`tests/test_faults.py`, against the
  stand-ins).
- The board caught what went unasked. The same paragraph, sent again in a fresh clone to the planner
  that asks, came back with five items instead of five paragraphs: three questions with a default
  each, one assumption, and one risk the stand-in person had not seen, that an executor's own shell
  can read Graphene's keychain item. Each of the five was a decision the executors had made silently
  in the first run (`docs/process/shaping/as-the-person.md`, item 12). One run, by an agent in the
  person's seat, with Claude Code as planner: it shows what the board is for, not how often it helps.
- A replay for judges with no key. `graphene demo` plays a recorded run in the real screen with no
  key, no Docker and no network. It runs no model-written code, and it says on screen what it is
  replaying.

## What we learned

(The live evidence run fills in the rest.)

**The chart goes here.** One panel per pre-registered question, drawn from its table as registered
and never tuned to a target:

- *Shaping, with stand-ins* (`docs/test/results-2026-09-28-shaping.md`): the person's attention in
  modelled person-seconds, for the board, the outline and the paragraph, beside whether the work was
  accepted.
- *Live on Nemotron* (`docs/test/results-2026-09-28-live-prereg.md`): the same paragraph, a pruned
  tree from Ultra with Nano on the leaves against the paragraph sent to Nano alone, in correctness,
  the person's attention and dollars.

The shaping panel has a number, and it goes against the board. With Claude model stand-ins shaping
one Claude Code proposal per task, and nothing run, answering the board first cost more modelled
attention than pruning the outline alone on all four tasks: +356.7 to +637.3 person-seconds (study
2), and still +272.8 to +398.6 once the planner put up one or two items instead of five or six
(study 3, exploratory), mostly in reading. The shaped plan was at least as faithful to the task's
card on all four, one run each (`docs/test/results-2026-09-28-shaping.md`). The board against the
paragraph, and the live Nemotron panel, have not run. The chart goes in the README, the video, the
demo page and here, whatever it says.

## What's next for Graphene

- The evidence runs and their chart, in the README, the video, the demo page and here, whatever it
  says.
- Nemotron's three shaping prototypes run live, each measured as `docs/process/ideas.md` sets out:
  for `cover`, the clauses a blind judge says the tree dropped; for `note`, how often a note finds the
  right leaf; for `precheck`, its verdicts against hand labels and the seconds per fork.
- The board as keys in `graphene watch`. Tonight it is answered by command; the screen does not yet
  show it or count its open items.
- The escape test live in ConTree, and a live leaf recorded and replayed in CI.
- A real open-source repository's issue done through the tree, with the patch offered upstream by a
  person.
- The same containment around any executor in a Sandbox: Claude Code or Codex, held to a leaf's scope
  on the sponsor's service.

## Built with

python · textual · rich · typer · sqlite · git · nvidia-nemotron (3 Ultra, Super, Nano) ·
nebius-token-factory · token-factory-sandboxes (contree-sdk) · react · vite · github-actions

## What changed during the Submission Period

The Submission Period opened on 26 August 2026 at 09:00 Pacific (16:00 UTC). The repository's first
commit is 10 August 2026.

- **Every line in `src/` was written after the period opened.** `git blame` over the 14,474 lines of
  Python in `src/` at `0334168` dates none of them before 2026-08-26 16:00 UTC (checked at the end of
  the run of 26 September; at its start, `94ce837`, it was 13,540 lines, also none).
- **Before the period** (last commit `cc50a62`, 26 August 06:32 EDT), the repository was a different
  product, *Graphene Taskmaster*, with its model path on Gemini through Vertex AI. It was reset to an
  empty package on 17 September (`c8a8f6c`), and none of that code survives.
- **Since then:** 0.2.0 (19 September), a local record of what coding agents did. 0.3.0 (20
  September), the shared plan with a gate. 0.4.0 (21 September), the plan as a tree, run in parallel.
  23 September: paragraph in, tree out, prune, run. 24 September: polish. 25 September: Nemotron on
  Token Factory and the sandbox placement. 25 to 26 September: failure paths, forks on screen, the
  replay, and the front door. 27 to 28 September: shaping: the board, the tree and graph views,
  talking on the tree, settings you state once, and three Nemotron prototypes for the moment before
  anything runs.
  <!-- integ only: everything in the 27 to 28 September line; the line counts above are still those
  at 0334168 and were not measured again. -->
- 181 commits predate the period, and 421 were made after it opened, at `0334168`.

Commands: `git rev-list --count --until='2026-08-26T16:00:00Z' HEAD`, `git rev-list --count
--since='2026-08-26T16:00:00Z' HEAD`, and `git blame --line-porcelain` over `git ls-files 'src/*.py'`,
counting `author-time` before 1787760000 (2026-08-26 16:00 UTC).

## Feedback on Token Factory, Sandboxes and Nemotron

Written from what we actually hit. Where a thing is only unverified, it says so. (Checked
2026-09-25, before any live call: this session had no key, so nothing below was observed on the
service itself.)

1. **The Sandboxes SDK's Getting Started describes an API no release has.** It says `Contree` and
   `ContreeSync` "just take an already-constructed `contree_client` client". On PyPI, both
   `contree-sdk` 0.3.6 and 0.4.0.dev5 take `(config=None, *, base_url, token)`. We pinned 0.3.6
   and built its auth from the environment.
2. **`contree-sdk` 0.4.0.dev5 and the latest `contree-cli` (0.9.4) cannot be installed together.** The
   SDK needs `contree-client~=0.2.1`, and the CLI `~=0.4.0`. `contree-cli` 0.9.3 installs beside it.
3. **The project variable has three names.** The CLI's auth page reads `NEBIUS_AI_PROJECT`, and the
   SDK's `IAMAuth` and the mini-swe-agent page read `NEBIUS_PROJECT_ID`.
4. **The mini-swe-agent integration page's example is a stub.** It raises "mini-swe-agent's
   ContreeEnvironment does not support user-provided contree_client clients". The page says so, but
   the one integration an agent builder would copy does not run.
5. **There is no run-as-user option.** For an agent sandbox, the useful default is that the agent's
   commands are not root. We drop privileges with `setpriv` inside the image. A `user=` on `run`
   would make the safe thing the easy thing.
6. **Pricing in the model list, as documented, is exactly what an agent needs**, because every
   call's usage can be priced per leaf. *Not yet observed:* the field's presence and its units, and
   whether those are the prices billed.
7. **The SDK has no way to delete a checkpoint.** An agent that keeps each command's image
   (`disposable=False`) leaves one image per command, and the overview says untagged images are kept
   180 days.
8. **Model retirement needs a machine-readable signal.** An agent that writes model ids into a
   repository's config can fall back when an id disappears from `/v1/models`, which is what we built.
   A `deprecated_at` or `replaced_by` field in the list would let it warn *before* the id goes.

## Every number, and where it comes from

| Number | Source |
| --- | --- |
| 20/20 and 12/12, 2,626 against 3,869 modelled person-seconds | `docs/test/results-2026-09-23.md` (stand-in runs, frontier agent) |
| 3 of 3 against 0 of 3; 5.2 to 6.1 times the characters | `docs/test/spikes/harness_there/RESULTS.md` (stand-ins) |
| fifty operations at once; a peak of 50, or 56 without the slots | `tests/test_faults.py`, the thirty-leaf test (a counting fake box); 56 with `sandbox.CAP` raised to 1000, which is 8 executors × 7 forks |
| 14,474 lines, none before the period; 181 and 421 commits | git, the commands above, at `0334168` |
| about 250 words in five paragraphs; five items instead; each a decision made silently | `docs/process/shaping/as-the-person.md`, items 2 and 12 (Claude Code as planner and executors, an agent in the person's seat) |
| 32 ideas, 20 after merging, three judges, the top three built | `docs/process/ideas.md` |
| `2 at once · 2 wait · critical path … (3)` | `graphene plan --view dag --width 80` on a scratch plan of four leaves from a scripted planner, at `integ` 50f12e7 |
| 150 random plans; 22 widths from 20 to 167 | `tests/test_view_dag.py`, `tests/test_view_tree.py` |
| the tree against the paragraph with Nemotron | none yet: the evidence run's ledger |
| the board against the outline: +356.7 to +637.3 modelled person-seconds (study 2), +272.8 to +398.6 (study 3), board higher on 4 of 4 tasks | `docs/test/results-2026-09-28-shaping.md`, H1 of studies 2 and 3 (Claude model stand-ins, one Claude Code proposal per task, nothing run, one run each) |
| the board against the paragraph | none yet: `docs/test/results-2026-09-28-shaping.md`, pre-registered |

## Testing instructions

No key, no Docker, and no model is called:

```
uv tool install git+https://github.com/Alex-lop/Graphene
graphene demo              # a recorded run, replayed in graphene watch
graphene demo --once       # its last state, printed
git clone https://github.com/Alex-lop/Graphene && cd Graphene
SHOW_DEMO=1 uv run pytest -s tests/test_demo_script.py   # nemotron.sh against a scripted stand-in
uv run pytest tests/test_board.py tests/test_cover.py tests/test_note.py tests/test_precheck.py
                           # the board, and Nemotron's three shaping prototypes against the stand-in
```

In the replay, Tab shows the same plan as a tree and then as a graph. The recorded plan has two
leaves and neither waits on the other, so its graph is two rows.
<!-- integ only: Tab in the replay, and the four test files. Checked at integ 50f12e7: Tab in the
replay at 80x24 showed "graphene watch --view tree: 1 sub-goal · 2 leaves", then "graphene watch
--view dag: every leaf done", and the four files with test_view_dag, test_view_tree and test_talk
gave 233 passed. test_precheck.py runs one test in Docker where Docker runs and skips it
elsewhere, so the line keeps its promise of no Docker. -->

With the agent you have (Claude Code or Codex, no Token Factory key), in a repository of yours:

```
graphene init
graphene ask "…what you want…"    # the planner proposes a tree and puts up its board
graphene board                    # what it asks you; answer with take, pick, drop, park or answer
graphene watch                    # Tab for the tree and the graph
```
<!-- integ only: graphene board, Tab in graphene watch. -->

With a key for Token Factory (it spends at list price, and prints the bill at the end):

```
export NEBIUS_API_KEY=…    # for Sandboxes, NEBIUS_PROJECT_ID too, and install with [sandbox]
docs/proof/nemotron.sh     # in the clone: the feeds task, from nothing to git log --graph
```
