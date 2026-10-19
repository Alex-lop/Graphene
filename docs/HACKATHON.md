# Graphene for the Nebius × NVIDIA Global AI Hackathon: the Devpost fields (a draft)

**Submissions close Friday 30 October 2026, 10:00 PT.** Devpost takes no edits after that. Judging runs from 1 to
15 December, and the project has to stay free to try until it ends.

*A draft for Alex to put in his own words before it goes anywhere: first written on 26 September, brought up to
the cockpit on 18 October. Track: Coding and Agentic Engineering. Every sentence is meant to be true and
traceable, and every number names its source.*

**What ran live on Token Factory, and what did not.** Each live run is written down in the repository, most with
what it cost at list price. They were practice and takes for the video; none was a pre-registered study.
- 29 September: Graphene's first runtime call to Token Factory. Ultra, Super and Nano each made one tool call, and
  a practice task landed on Nano for $0.0004 (`dev/test/first-light.md`).
- 2 October: Nemotron 3 Ultra planned and Nano executed, each task in a Token Factory Sandbox. 2 of 5 demo takes
  ran to the end, neither doing all the paragraph asked, and the planner's plan was readable on 2 of 9 asks. The
  night cost $1.80 (`dev/test/first-light.md`).
- 7 to 9 October: 31 more takes of the same demo run on two small repositories (19, then 6, then 6), three runs
  that pressed a key on every task that came back, and 80 asks of the planner alone. 4 of the 31 takes ran clean,
  2 of them with every task landed, and on the build of 9 October the planner's answer became a plan in 35 of 40
  asks (`dev/process/meter/takes.md`, `dev/process/timeline/takes.md`, `dev/process/loop/takes.md`,
  `dev/process/loop/after.md`).
- Everything else on the Nemotron path has run only against a scripted stand-in for Token Factory
  (`tests/fake_tokenfactory.py`) and a Docker stand-in for Sandboxes. The replay `graphene demo` ships is the
  stand-in's, and its top line says "a scripted stand-in, no model ran".

<!-- For Alex: send this only once PyPI serves the cockpit (`uvx --refresh --from 'graphene-map==0.6.0' graphene
--version` says 0.6.0; without --refresh, uvx may answer from an environment it made before): the testing
instructions at the end depend on it. -->

## Inspiration

The limiting factor for innovation in software development won't be the next model or harness. It's going to be
you, the human, and the direction you give it. If you don't say which direction the application should go, the
agent has to infer most of it, and you find out what it inferred in the diff. With several agents at once it gets
worse: you don't know what any of them is doing until it says it's done, and "done" is its own word for it.

Token Factory sells tokens cheap enough to spend in bulk: Nemotron 3 Nano is $0.06 in and $0.24 out per million
tokens on the live list (`dev/test/first-light.md`). But a cheap model you can't trust doesn't save your
attention, it spends it, on reading diffs and cleaning up after them. So the question I kept asking was how to
hand real work to a cheap model, stay the one who decides where it goes, and trust what comes back.

## What it does

Graphene is the plan you and your coding agents share. You set the direction, they work inside it, and you can see
every one of them while they do.

**On NVIDIA Nemotron, through Nebius Token Factory: the path built for this hackathon.** `graphene init --planner
nemotron --executor nemotron` reads Token Factory's live model list: Nemotron 3 Ultra plans, Nano does the tasks,
and when an attempt is refused the next steps up to Super. It is not a wrapper around another agent: the planner
reads the repository with read-only tools and answers in a strict JSON schema, and the executor is Graphene's own
tool loop. Every call's usage is priced at Token Factory's list price, so each task has its own bill, which `i`
shows (in the recording of 9 October, Nano did one task in 4 calls for $0.0009). Claude Code and Codex work the
same way, as planner or executor.

1. **You say what you want**, in a paragraph, with `graphene ask`, or to Claude Code, which proposes a plan before
   it writes. The planner reads the repository and proposes tasks, each with the files it may change and a check:
   a command that passes only when the task is done.
2. **You watch and steer from one screen.** `graphene watch` is the cockpit: one row a task, the agent on it by
   number, and in numbers whether it is alive and on track (files touched of files allowed, checks passed, writes
   stopped, seconds quiet). What needs you is on top: a question, a proposed task, a task that came back with its
   reason, a task waiting for your sign-off. One key each:
   - `⏎` makes the row's own move: take the default, accept, try again, sign off.
   - `t` tells a task one line. A Claude Code agent hears it with its next write or command, and the row says
     when it has; any other executor is told it the next time the task starts.
   - `w` widens a task to the path its gate stopped, and `x` hands a running task back, or reopens a finished
     one with what is wrong.
   - `i` opens the details (contract, output, changes, record), `g` the graph of what waits on what, `m` the map
     of the folders each task may write.
3. **Held to its files.** Nemotron's executor refuses a write outside its task's files in its own write tools, and
   in a Sandbox the operating system refuses it too. With Claude Code a hook refuses it before it happens. With
   Codex git finds it when the task is declared done, and the task comes back instead of landing.
4. **Done means proven.** Graphene runs the check itself, in a clean copy, and only a task whose check passed
   lands, as one merge `git revert -m 1` takes back. A task marked for sign-off waits on its own branch until you
   press `⏎`; `c` in its details shows the whole diff first.

**The planner asks instead of guessing.** Beside its tasks, the planner is told to put up only what the code
cannot answer and what changes the plan, at most three items: questions with a default and their options, and
risks. In `graphene watch` the items are the first rows under the goal: `⏎` takes the default, `1`-`9` picks an
option, `a` answers in your own words, `d` drops it. Once the whole plan is accepted, or a run you start begins,
every open item with a default takes it as yours, said in one line that `graphene plan undo` takes back, so a
person who agrees with every default answers nothing. A default that drops a node is the exception: it waits for
your own key. What you take, pick or answer in your own words, and every note of yours, reaches the executors'
contracts as a `decided:` line; a dropped or parked item is told to no one. Only the person answers: an agent
that tries is refused (`tests/test_board.py`).

**Nemotron works for you while you shape.** Four small commands lean on Nano, one call with a JSON schema at a
time, and Graphene checks each answer before anything is shown: `graphene plan cover` names the parts of your
paragraph no task carries, in your own words; `graphene plan note "…"` finds the one task a loose sentence
constrains; `graphene plan precheck` runs every check before any work and asks Nano only about a red its exit
code does not explain; `graphene board lookup` settles the open questions the repository already answers, quoting
the line. Cover and precheck passed twice live, as practice on 2 October, and note routed one of two notes once;
lookup has run only against the stand-in (`dev/test/first-light.md`, `tests/nemotron/`).

**What it sends.** Nemotron is an optional extra: `uv tool install --python 3.12 'graphene-map[nemotron]'`. Without it, no
Token Factory code loads, and with Claude Code or Codex Graphene itself sends nothing anywhere. With NVIDIA
Nemotron as planner or executor, Graphene sends Nebius Token Factory your prompts and the files the model reads,
and in a sandbox it sends Sandboxes the task's checkout. The key lives in your environment or the system keychain,
never in a file. The Nemotron commands above are the exception, whatever the planner: `plan cover`, `plan note`
and `graphene board lookup` ask Nemotron Nano, and `plan precheck` uploads your checkout to Sandboxes when
ConTree's credentials are set (and asks Nano about a failing check whose output doesn't say why). None of them
runs unless you run it, or set `GRAPHENE_SHAPE` to run them after each `graphene ask`.

## How we built it

- **Token Factory's API**, from the Python standard library (`src/graphene_map/nemotron/tokenfactory.py`). No
  model id is written in the code: `GET /v1/models?verbose=true` names the Nemotron Ultra, Super and Nano, and
  its `pricing` prices every call's `usage`. A retired id falls back to the nearest listed Nemotron, and one line
  says which was used instead of which. A 429, a 5xx and a timeout are retried, then reported with what to do.
- **Nemotron's roles.** Ultra is the planner (`planner.py`): its tools (list, glob, grep, read) run on your machine
  and read only what git shows. Since prompt version 5 it answers in a strict JSON schema, and a check runs only
  its own task's files. Since prompt version 6, Ultra hears the faults of an answer together, one per node, at most
  twice, and Graphene repairs what needs no judgement itself (`planner.py`, `PROMPT_VERSION`). Nano, then Super,
  is the executor (`executor.py`): Graphene's own loop asks for one tool call at a time (view, edit, write, run,
  done or release). The reasoning budget is each call's `max_tokens`, doubled up to 32,768 when a reply is cut
  off. Nemotron's `<TOOLCALL>` text and common tool-name spellings are read as the calls they mean.
- **Spending is the person's act.** A process that carries a vendor's agent mark (`CLAUDECODE`, Codex's) is
  refused a call to the real host, and any Sandbox, before anything is sent, unless the person started its session
  with `GRAPHENE_AGENT_LIVE_USD` set. Then every call goes on one ledger for the night: a call reserves its worst
  case at list price before it is sent and settles to its usage after, and one that would pass the cap is refused
  unsent (`night.py`, `tests/nemotron/test_night.py`). `graphene run --max-usd N` starts no attempt past N
  dollars.
- **Sandboxes' checkpoints and forks.** A clean commit is uploaded and set up once, as a checkpoint
  (`sandbox.py`, contree-sdk 0.3.6), and every task at that commit forks it. The executor's commands run there as a
  user who can write only the files the task may change, through `setpriv`, and what a command changes outside
  them is never brought back. The check runs in a fresh fork, on only what came back. Before `graphene init`
  places tasks in Sandboxes it asks ConTree's whoami, a read: a project Sandboxes refuse gets its tasks on this
  machine, with one line saying why and where access is asked for.
- **The boundary, three layers deep.** The executor's write tools refuse a path outside the task's files before
  touching it, in the same words the Claude Code hooks use; in a sandbox, the operating system refuses it too; and
  a task is done only when Graphene runs the check itself and git shows nothing outside its files. An escape test
  tries every way out (a redirect, `sed -i`, `python open(w)`, `mv`, `rm`, git, a symlink, `chmod`) and each fails
  (`tests/nemotron/test_escape.py`, in the Docker stand-in). It passed once in ConTree too, as practice on 2
  October: 10 ways out failed or were refused, 2 ways in came back (`dev/test/first-light.md`).
- **The cockpit** is built with Textual over the plan's SQLite store, which lives in the repository, ignored by
  git. It reads a plan in a few milliseconds (53 ms at 22,000 log rows, `CHANGELOG.md`). Every key is an ordinary
  `graphene` command, and the line under the rows says which one ran. Tasks run in parallel, each in a git
  worktree of its own, and are merged `--no-ff`. CI runs the suite on Linux and macOS, on Python 3.12, 3.13 and
  3.14.
- **Built the way it is meant to be used.** I set the direction and coding agents do much of the writing, in lanes,
  overnight; each night's plan, readers' reports and brief are in `dev/process/`. On 9 October two of those lanes
  were built through Graphene itself: five tasks, four agents at once, all five proven on their first attempt
  ($2.07 with Claude Sonnet as the agents, `dev/process/loop/after.md`).

## Challenges we ran into

- **Ultra's answers broke the plan's format.** On 7 October Ultra planned a readable plan in 7 of 19 takes; the
  other twelve broke the format or never answered (`dev/process/meter/takes.md`). Its answer moved to a strict JSON
  schema on 8 October, and on 9 October every fault went back at once while Graphene repaired the mechanical ones:
  35 of 40 asks then ended in a plan (`dev/process/loop/after.md`).
- **A task that needs a file another task writes.** Every plan of 7 October stopped where one task needed a file
  another one writes, mostly a test file its check runs. So a task that comes back says what it wanted, and its row
  offers the fix: `w` widens it, `b` adds a new task for the file, `n` waits on the task that owns it, `r`
  reopens that owner.
- **A check that cannot fail on the wrong work.** Take 1 on 2 October landed code that read prices already in
  cents as dollars (`129900` for `1299`), under checks that ran the command and asserted nothing about a price
  (`dev/test/first-light.md`). Graphene cannot tell a weak check from a strong one. It can show it: every check
  runs once before any work and one that already passes is flagged, and a task that changes its own check's file
  is flagged too.
- **Where the agent loop runs decides what can be refused.** With Graphene's own loop on your machine and the
  tools in the sandbox, an out-of-scope write was refused in Graphene's words before it happened, 3 runs of 3.
  With a harness inside the sandbox (OpenCode 1.18.31), Graphene never heard of it in 3 of 3, the key sat where
  model-written code could read it, and each task sent 5.2 to 6.1 times the characters
  (`dev/test/spikes/harness_there/RESULTS.md`, against the stand-ins).
- **The judging period outlives model ids.** Judges may test until 15 December, and Token Factory retires models on
  notice, so the roles come from the live list and a retired id falls back within the family.
- **The one honest comparison we have did not favour the plan.** On 23 September, with a frontier agent on a small
  task, a plain paragraph passed 20 of 20 hidden acceptance checks and 12 of 12 held-out ones, and cost less of the
  person's modelled time than the plan: 2,626 modelled person-seconds against 3,869, medians of two runs
  (`dev/test/results-2026-09-23.md`). So the claim is not that a plan beats a paragraph. What I'm betting on is
  when you find out what the agent understood: before the work, not after.

## Accomplishments that we're proud of

- **Nemotron, end to end, live.** On 8 October Ultra planned two tasks and Nano landed both in Sandboxes on their
  first attempts, in 203 seconds, for about $0.10; on 9 October it planned three, and Nano landed all three on their
  first attempts, for $0.11 with the planner (`dev/process/timeline/takes.md`, `dev/process/loop/takes.md`).
  Both runs replay with no key in today's cockpit, and their top line says "as it ran, live".
- **A product, not a demo.** One screen for every agent, a plan the person shapes before anything runs, tasks in
  parallel worktrees, hand-backs that offer their own fix, a record for each task, and docs that list what does
  not bind (`docs/HOW_IT_WORKS.md`).
- **Containment that is tested, not asserted.** `graphene demo --cheat` runs a script that tries seven ways round
  the locks against the real hook, git and check: six are refused, one is flagged, none gets through. It is a
  script, not a model, and it says so.
- **Failure that reads as a sentence.** A 429 storm, a 5xx, a timeout, a model that stops calling tools, a
  sandbox killed mid-task and a check that hangs each bring the task back with its cause and what to do; the run
  goes on, and nothing is left running (`tests/nemotron/test_faults.py`, against the stand-ins).
- **Talking to an agent mid-task works, mostly.** With Claude Code (Haiku, half a cent a run), a note told with the
  agent's next write was followed on its next step in 12 runs of 14; told as a command ended, in 1 of 12
  (`dev/ui/IDEAS.md`). So `t` waits for the next write, and the row says "heard", never "done".

## What we learned

**Nemotron 3 Ultra as a planner, live.** Each line ran on Token Factory:

| when | what was counted | what came of it | source |
| --- | --- | --- | --- |
| 2 October | asks in five demo takes, two at most a take | 2 of 9 a plan Graphene could read | `dev/test/first-light.md` |
| 7 October | demo takes | 7 of 19 a readable plan; none ran clean to the end | `dev/process/meter/takes.md` |
| 8 October | demo takes | 3 of 6 clean, one with every task landed | `dev/process/timeline/takes.md` |
| 9 October | asks alone, every fault sent back at once, twice at most | 35 of 40 a plan (87%) | `dev/process/loop/after.md` |
| 9 October | demo takes, bigger plans | 1 of 6 clean, every task landed | `dev/process/loop/takes.md` |

Ultra is most of the bill: $1.70 of the $1.80 that 2 October cost (`dev/test/first-light.md`). Nano, which does
the tasks, is cheap enough to retry, and Super takes the second attempt.

**How many agents run at once is set by how the files split, not by a flag.** On the feeds task, with four
allowed, the planners' plans (Claude Code's and Nemotron's) ran one or two tasks at once in 10 of 11 runs, because
the wiring waits on the reader and the tests on both (`dev/process/loop/after.md`).

**The moment before anything runs costs attention too.** With Claude model stand-ins shaping one Claude Code
proposal per task, and nothing run, answering the planner's questions first cost more modelled attention than
editing the plan alone on all four tasks: +356.7 to +637.3 person-seconds (study 2), and still +272.8 to +398.6
once the planner put up one or two items instead of five or six (study 3, exploratory), mostly in reading
(`dev/test/results-2026-09-28-shaping.md`). By the rule registered before study 4, the questions are shown only
while one the repository cannot answer is open (`dev/test/results-2026-09-29-board.md`).

## What's next for Graphene

- A live take filmed on the cockpit for the video, and an hour of a real person on it, timed: no person has been
  timed yet.
- `t` heard mid-task by Nemotron's executor, as Claude Code hears it; today it is told at the task's next start.
- The questions against the paragraph, registered and not yet run (`dev/test/results-2026-09-28-shaping.md`).
- The same containment around Claude Code or Codex inside a Sandbox.

## Built with

python · textual · rich · typer · sqlite · git · nvidia-nemotron (3 Ultra, Super, Nano) · nebius-token-factory ·
token-factory-sandboxes (contree-sdk) · claude-code · codex · github-actions

## What changed during the Submission Period

The Submission Period opened on 26 August 2026 at 09:00 Pacific (16:00 UTC). The repository's first commit is 10
August 2026.

- **Every line in `src/` was written after the period opened.** `git blame` over the 27,469 lines of Python in
  `src/` at `921834de` (18 October, the merge that made the cockpit `graphene watch` on main) dates none of
  them before 2026-08-26 16:00 UTC.
- **Before the period** (last commit `cc50a62`, 26 August 06:32 EDT), the repository was a different product,
  *Graphene Taskmaster*, with its model path on Gemini through Vertex AI. It was reset to an empty package on 17
  September (`c8a8f6c`), and none of that code survives.
- **181 commits predate the period, and 971 were made after it opened**, at `921834de`.
- **September.** 0.2.0 (19 September), a local record of what coding agents did; 20 September, the shared plan
  with a gate; 21 September, the plan as a tree, run in parallel; 23 September, paragraph in, plan out; 25
  September, Nemotron on Token Factory and the sandbox placement; 25 to 29 September, failure paths, the replay, the
  planner's questions, and Nano's four commands; 29 September, the first runtime call to Token Factory.
- **October.** 2 October, the live half of first light. 5 October, Nemotron became an optional extra
  (`graphene-map[nemotron]`). 7 to 9 October, 31 live takes, a running task's turns and dollars as it works, the
  planner's JSON schema and its repairs, every check run once before any work, and `r`, which reopens the task
  that owns a fault; 0.5.0, tagged on 7 October, went to PyPI on 13 October. 14 and 15 October, a task marked for
  sign-off waits on its own branch, `graphene demo --cheat`, `graphene run --stop` and `--max-usd`, and a task
  whose branch moved is checked on the merge before it lands. 16 October, a note reaches a Claude Code agent with
  its next write. 17 and 18 October, `graphene watch` became the cockpit, and agents go by numbers, kept by their
  task through a retry.

Commands: `git rev-list --count --until='2026-08-26T16:00:00Z' 921834de`, `git rev-list --count
--since='2026-08-26T16:00:00Z' 921834de`, and `git blame --line-porcelain 921834de` over its `src/*.py`, counting
`author-time` before 1787760000 (2026-08-26 16:00 UTC).

## Feedback on Token Factory, Sandboxes and Nemotron

Written from what we actually hit. Where a thing is only unverified, it says so. Items 1 to 8 were checked on 25
September, before any live call, from the docs and PyPI; items 9 to 11, and what item 6 says was observed, come
from the practice of 29 September, and items 12 to 14 from that of 2 October (`dev/test/first-light.md`); items 15
and 16 from the takes of 7 to 9 October (`dev/process/meter/takes.md`, `dev/process/loop/after.md`). None was
checked again since.

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
   call's usage can be priced per task. *Observed on 29 September (practice):* the live list carries
   each model's price, and rung 2's three usage rows, priced at it, add up to what the ladder recorded.
   *Not yet observed:* whether those are the prices billed.
7. **The SDK has no way to delete a checkpoint.** An agent that keeps each command's image
   (`disposable=False`) leaves one image per command, and the overview says untagged images are kept
   180 days.
8. **Model retirement needs a machine-readable signal.** An agent that writes model ids into a
   repository's config can fall back when an id disappears from `/v1/models`, which is what we built.
   A `deprecated_at` or `replaced_by` field in the list would let it warn *before* the id goes.
9. **Sandboxes' 403 names neither the missing grant nor the way in.** For rung 1's call, contree-sdk
   0.3.6 raised `ForbiddenError` with "You do not have permission to perform this action". It does not
   say which permission the key lacks, nor that the beta is by request (contree.dev says to request
   access at tokenfactory.nebius.com/sandboxes/about). Graphene now says both itself, and asks ConTree's
   whoami before it places a task there.
10. **A made-up key and a made-up project got a 403, not a 401, once**, when a test of ours reached the
    real ConTree by mistake (about 02:00 on 29 September; not repeated, no log kept), so a 403 alone may
    not tell a key without the grant from a `NEBIUS_PROJECT_ID` that is not the key's project.
11. **The three Nemotron 3 ids are cased three ways:** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`,
    `nvidia/Nemotron-3-Ultra-550b-a55b` and `nvidia/nemotron-3-super-120b-a12b`. An agent that matches
    ids as spelled misses two of them; Graphene reads them case-blind. The fourth NVIDIA model listed,
    `nvidia/Nemotron-3_5-Lightning`, names no size, so no rule by size can place it.
12. **On ConTree, a `cat` whose output is a file leaves that file unwritable** (2 October, practice;
    kernel 7.0.6, coreutils 9.7 in `python:3.12`). `{ cat FILE; echo after; } > OUT` fails at the echo
    with an I/O error, while `$(cat FILE)` and `cat FILE | cat` write whole. Docker does not do this.
    Every sandbox command of ours read as exit 1 until our list stopped taking a `cat` into a file, and a
    command's own output was cut at its first `cat` until we opened it for append (`>>`).
13. **whoami's `token_expiration` is a token minted for 300 seconds on every read**, and contree-sdk
    warns "Token expires in 0 hours" on every client. It reads as the key expiring; it misled us into
    asking for a new key.
14. **On ten calls of Nano's commands, Nemotron 3 Nano used 174 to 2,048 completion tokens for JSON answers of
    about 100 tokens** (2 October, practice), and a 2,048-token cap was hit once. Whether this is reasoning, and
    whether it can be turned off, the docs we read do not say.
15. **Nemotron 3 Ultra sometimes writes its tool call as text.** On 7 October it answered with
    `<tool_call>{…}</tool_call>` in the reply's content instead of a tool call, twice in one take, and a client
    that reads only `tool_calls` takes that for its final answer. Graphene now reads a tool call written as text.
16. **Ultra's ways of not answering cost the most.** It read for 30 tool calls and never answered (7 October, take
    1, $0.29), and 12 of 82 of its answers on 9 October ran to the token limit without ending, against 2 of 62 once
    the faults we sent back were said once each. An answer that runs to the limit is a whole call billed for
    nothing usable.

## Every number, and where it comes from

| Number | Source |
| --- | --- |
| $0.0004 for the first task on Nano; $1.80 for 2 October, $1.70 of it Ultra; 2 of 5 takes, 2 of 9 asks | `dev/test/first-light.md` (practice) |
| 31 takes on 7 to 9 October; 7 of 19, 3 of 6, 1 of 6; 4 clean, 2 with every task landed | `dev/process/meter/takes.md`, `dev/process/timeline/takes.md`, `dev/process/loop/takes.md` |
| 35 of 40 asks a plan (87%) on the build of 9 October; 12 of 82 and 2 of 62 answers to the token limit | `dev/process/loop/after.md`, the Nemotron planner |
| 203 seconds and about $0.10; $0.11; Nano's task in 4 calls for $0.0009 | `dev/process/timeline/takes.md` take 6; `dev/process/loop/takes.md` take 2; `tests/recordings/loop-nemotron-take-2.jsonl` |
| 1 or 2 tasks at once in 10 of 11 feeds runs; five tasks, four at once, $2.07 | `dev/process/loop/after.md`, width and the dogfood |
| 12 of 14 against 1 of 12 | `dev/ui/IDEAS.md` (real `claude -p` runs, Haiku) |
| 20/20 and 12/12, 2,626 against 3,869 modelled person-seconds | `dev/test/results-2026-09-23.md` (stand-in runs, frontier agent) |
| 3 of 3 against 0 of 3; 5.2 to 6.1 times the characters | `dev/test/spikes/harness_there/RESULTS.md` (stand-ins) |
| the questions against editing the plan: +356.7 to +637.3 modelled person-seconds (study 2), +272.8 to +398.6 (study 3), board higher on 4 of 4 tasks | `dev/test/results-2026-09-28-shaping.md`, H1 of studies 2 and 3 (Claude model stand-ins, one Claude Code proposal per task, nothing run, one run each) |
| 53 ms at 22,000 log rows | `CHANGELOG.md`, 0.6.0 |
| 27,469 lines, none before the period; 181 and 971 commits | git, the commands above, at `921834de` |
| the questions against the paragraph; the plan against the paragraph with Nemotron | none yet: registered in `dev/test/results-2026-09-28-shaping.md` and `dev/test/results-2026-09-28-live-prereg.md` |

## Testing instructions

No key, and nothing spent: the replays and the locks.

```
uvx --from graphene-map graphene demo          # the scripted stand-in's run of the Nemotron path, in the cockpit
uvx --from graphene-map graphene demo --cheat  # a script tries seven ways round the locks; the real ones answer
```

In the cockpit, `j` and `k` move, `i` opens the details, `g` the graph, `m` the map, `c` the cockpit again, `?`
lists the keys and `q` leaves; in a replay, space pauses, `.` steps and `r` plays it again. Keys that would change
the plan say "a replay: nothing runs here".

Two live Nemotron runs on Token Factory, replayed with no key, from a clone:

```
git clone https://github.com/Alex-lop/Graphene && cd Graphene
uv run graphene demo tests/recordings/loop-nemotron-take-2.jsonl      # 9 October: three tasks, all landed
uv run graphene demo tests/recordings/timeline-nemotron-take-6.jsonl  # 8 October: two tasks, both landed
uv run pytest tests/nemotron -q -n auto         # the Nemotron path against the scripted Token Factory
```

With a Token Factory key, in a git repository of your own (it spends at list price: an ask cost $0.08 to $0.55 in
the takes of 8 and 9 October, and a take's tasks $0.005 to $0.15):

```
uv tool install --python 3.12 'graphene-map[nemotron]'
graphene key set            # kept in the system keychain; or export NEBIUS_API_KEY=…
graphene key check          # says whether Token Factory answers it
graphene init --planner nemotron --executor nemotron
graphene ask "what you want, in a paragraph"
graphene watch              # ⏎ on each question and each proposed task, then R runs what is ready
```

With Claude Code or Codex instead (no key): `graphene init`, then tell Claude Code what you want and it proposes
the plan first; `graphene watch` beside it.
