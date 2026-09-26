# Graphene: the Nemotron directive

*For the agent that runs on this repo next. Written 2026-09-25 with Alex, after an outside review of PR #28 and a second read of that review against the code and the hackathon's official rules. Where the review and this file disagree, this file was checked against both; follow it. The earlier directives in `docs/process/directives/` still hold wherever this one is silent. Read them, `docs/DIRECTION.md`, `docs/HOW_IT_WORKS.md` and this file before you touch anything.*

## What kind of run this is

Everything the earlier directives said about how to work holds: there is no clock, doubt your work and never your capacity, decide at every fork and write down why, keep `docs/process/morning.md` current at every milestone, push the branch green after each, leave one PR, use sub-agents in parallel wherever items are independent, and nothing waits on Alex.

What is new is an outside judge and a date. Graphene is going into the Nebius × NVIDIA Global AI Hackathon, Coding and Agentic Engineering track. Submissions close Friday 30 October 2026, 10:00 PT. As it stands, Graphene is out of scope for it: the planner is `claude -p`, the executors are Claude Code or Codex, and nothing touches Nebius or an NVIDIA model. The product is already more finished than most entries will be. What it lacks is the one thing the rules require and the one thing the judges will look at first.

So, unlike the polish run, this run builds mechanism: one mechanism, and the evidence for it. Most of the night goes to item 2. Everything else in the queue is what a judge meets on the way to it.

The run ends when the queue and the backlog are done or blocked in writing and the final audit passes, not when it feels finished. Spend effort where it buys evidence: real runs, repeated runs, a second harness, an adversarial test of the boundary, a fresh-eyes review. Never pad. When you think you are done, you are at the backlog.

## What the rules require

Verified 2026-09-25 against https://nebiusglobalaihackathon.devpost.com/rules. Read them yourself before item 8.

- **Runs on Nebius, uses NVIDIA.** A runtime call to the Token Factory inference API (or running on Nebius AI Cloud compute), and at least one NVIDIA open model.
- **The track.** Its stated goal is coding agents and developer tools: agents that write, run and test code in Token Factory Sandboxes. Stage One is pass/fail on whether an entry is a genuine attempt at that goal and not a rebrand of something else. Sandboxes are part of the entry, not decoration, and Nemotron has to be how Graphene works, not a fourth `--with`.
- **Stage Two**, equal weights, ties to the first: Technological Implementation (how well it is built, how effectively it uses Token Factory and Nemotron); Design (a complete, coherent product, not a proof of concept); Potential Impact (a specific real problem for a real audience, addressed in what is shown); Quality of the Idea (a creative, non-obvious use of Token Factory and Nemotron).
- **The submission.** A working demo URL (a test build counts); the public repo with its licence visible; a README with setup and how Nemotron and Token Factory are used; a public video of three minutes or less whose audio covers how Token Factory and Nemotron are used; feedback on the tools; and, because the first commit is 10 August and the Submission Period opened 26 August, a written account of what changed during the period.
- **Judges may test until 15 December.** What the README says must still run then.

## The thesis, in the sponsor's words

Graphene's claim is that a person shapes the tree and agents are held to it by mechanism. In Token Factory's terms: Nemotron 3 Ultra proposes the tree, once per paragraph, where reasoning is worth paying for. Nano or Super do the leaves, fast and many. Each leaf runs in a Sandbox forked from the same checkpoint of the repo. The scope and the check are what make a cheap model safe to use in bulk: when a leaf fails, fork it again or step up a size, and let the check decide. The tree the person pruned is the tree of sandboxes that ran.

That is the non-obvious use the fourth criterion asks for, and it is true only if the numbers say so. Item 2 finds out.

## What does not change

The review's keep list is Alex's too: the sentence and everything under it; the goal row and the one row grammar; plan first as a visible mode; the offers; the boundary as check-plus-git, out of process; the text form; `--with` on `run` and `ask`; "what does not bind"; the recorded gif; the PyPI distribution `graphene-map`. Claude Code and Codex keep working exactly as they do. Nemotron becomes what a new repo is offered first, not the only choice: executor-agnostic has been a principle, and tonight it becomes evidence.

## Before your first change

1. Record the rollback SHA. Branch `nemotron` from `main`. Move `docs/process/morning.md` to `morning-2026-09-24.md`, as earlier runs did, and start a new one.
2. Check access without ever printing a secret.
   - **Token Factory.** `NEBIUS_API_KEY` is set, and `GET /v1/models` answers on the OpenAI-compatible base URL the docs give for Alex's project. Write the exact ids you see for Nemotron 3 Ultra, Super and Nano (and any newer NVIDIA open model) into morning.md; never hardcode an id you did not see in that list. Make one real tool call per model (the docs' function-calling page) and note which misfire. Read the rate-limits page; back off on 429s.
   - **Sandboxes** (ConTree; beta; access by request). Start at https://docs.tokenfactory.nebius.com/llms.txt. Authenticate as the docs say, then smoke it: import a Python image, run a command, fork from the resulting image, run two forks at once. Time each step; the times feed item 2a.
   - **Spend.** Cap at `GRAPHENE_SPEND_CAP_USD`, 30 if unset. Every Token Factory call's `usage`, at list price, goes to a running total in the ledger (item 2c). At 80% start no new benchmark runs; at 100% stop calling Token Factory and carry on with everything that does not need it. Sandboxes are free during the beta; count their operations anyway.
3. If inference access fails, do every item that does not need it, build the executor and the planner against a recorded fake endpoint with tests, and put the blocker at the top of morning.md. If only Sandboxes fail, build and measure the local-worktree placement fully, put the sandbox placement behind the same interface against a test double, and say so at the top.
4. Some tests fail for the environment, not the code: the TTY-prompt test (`test_reopen_and_release_ask_at_a_terminal_and_refuse_in_one_line_without_one`) without a terminal, and the hook time-budget tests (a 60 ms wall-clock budget) on a slow or loaded machine, which yours will be while benchmarks run. Do not chase them, never loosen them, note them.

## The queue, in order

### 1. The rename, first

Everything after this writes new files, so the rename goes first, as one mechanical commit. `graphene_debrief` becomes `graphene_map`, matching the distribution. Not `graphene`: that import name belongs to the GraphQL library on PyPI, and a person with both installed gets whichever wins. Every reference moves: `pyproject.toml` (the script and the wheel's package), CI's check of the committed page (`src/graphene_debrief/ui/static`), the UI build's output directory, `docs/RELEASING.md`, the tests (the forged hook command in `tests/test_gate.py` included), the docs, a CHANGELOG line. The command stays `graphene`; hooks already installed call `graphene ingest hook` and keep working. Suite green, ruff clean, the wheel smoke passes.

### 2. A Nemotron executor that lands leaves

Most of the night. The question: on a real task, what share of leaves does a Nemotron executor land, how right is the result, and what does a landed leaf cost?

**2a. Placement.** There are two ways to put an executor in a sandbox. Build the smallest version of each and decide with numbers.

- *The loop here, the tools there.* Graphene's own executor loop runs locally against Token Factory (chat completions with tools), and every tool call it makes (view, edit, run) executes inside the leaf's sandbox. It can check scope before a write and answer with Graphene's own refusal, it talks to the store directly for done and hand-back, and the inference key never enters the machine where model-written code runs.
- *The harness there.* A harness runs inside the sandbox. OpenCode headless is the likeliest: the public repo `kreuzhofer/nebius-token-factory-sandboxes-demos` already runs it that way with Token Factory inference. A local wrapper, given to `--with`, uploads the leaf's snapshot, runs it, brings the diff back into the leaf's worktree, and speaks `graphene node done` or `release` for it.

Whichever wins also gets a local-worktree placement, for people without Sandboxes and as tonight's fallback. Measure on three to five feeds leaves: latency per tool call, wall time per leaf, whether a hand-back carries its reason and its offered fix, what the gate can see. Write the choice as the next numbered decision in `DIRECTION.md`, with the numbers. Pin every SDK and harness version and keep ConTree behind one module of ours: it is in beta, and the docs' own mini-swe-agent page currently says that integration no longer matches the SDK.

**2b. The benchmark, before any tuning.** A runner that, for one task, builds the repo with `docs/test/make_task.py`; runs `graphene init` with a named planner and executor; loads the task's fixed tree; runs `graphene run --parallel N`; and tallies from git, the store and `.graphene/runs/` (reuse `tally.py`; nothing is estimated). The runner plays the person mechanically: it takes an offer whose added paths all fall inside the task's `intent_globs.txt`, refuses any other, and logs each as a person action.

The fixed trees: generate one per task with the Nemotron planner (build item 4's minimum first), have a stand-in sub-agent prune it with the task's card (the stand-in is the card's only reader, as `standin.py` has it; you, tuning the executor, never open `intent.md`), and commit the pruned text as `docs/test/trees/<task>.plan`. Every configuration runs the same tree. A check that already passes at the base commit is not a check: fix or prune it, and count it.

**2c. What is counted.** Per leaf: landed (Graphene merged it, check passing, diff in scope, no person), handed back (with its reason, and whether its offer, taken, then landed), failed (crash, timeout), attempts, writes refused before they happened, tokens in and out, dollars, wall time. Per run: the task's hidden `accept.py` and held-out `quality.py`. One JSONL row for each in `docs/test/runs-2026-09-25.jsonl`, and `results-2026-09-25.md` generated from it. A configuration that lands more and passes accept less is worse.

**2d. Tune until most land.** Target: 80% or more of feeds leaves land without a person, over three runs of one configuration, and accept passes at the end of every run. Each lever is an experiment with its own rows: what the leaf prompt carries (the goal, the path to the root, scope, check, a repo map, the files in scope inlined for a small model); a tool set small models use well (view, a str-replace edit, run); the check's output fed back before a hand-back is allowed; native tool calls against a fenced-text protocol for a model whose calls misfire; reasoning on, low or off per step; temperature; N forks per leaf from one sandbox checkpoint, the check picking the winner; Nano first and Super only on failure. Report cost per landed leaf for Nano alone, Super alone, Nano best-of-3, and Nano then Super. When three experiments in a row gain less than five points, freeze the best and move on; the backlog comes back to it.

**2e. Held out.** Tune on feeds and inventory. Run report and logs only with the frozen configuration, and report them apart. The executor's prompt is the same for every task. No executor, planner or harness code, prompt or config reads anything under `docs/test/tasks/`.

**2f. Integrity.** Never weaken a check, a scope, the gate, `accept.py`, `quality.py`, a task repo or a test to move a number. If the best honest number is low, report it low, say what would raise it, and keep going.

### 3. Held to it before the write

The Nemotron executor gets three layers:

1. its write tools refuse an out-of-scope path before writing, with the three-line refusal the hooks use (what, paths, commands), reusing Graphene's own scope matching and the gate's wording rather than a second copy;
2. in the sandbox, it runs as an unprivileged user with everything outside the leaf's scope read-only, so a shell command cannot write what the tool refused;
3. `done`'s check and git, as today.

A harness plugin (OpenCode's `tool.execute.before`) is a courtesy, never the gate: it has been reported to miss tool calls made by subagents and, in one release, not to fire at all. Layer 2 is what makes the claim true, for any harness.

Prove it with a scripted executor that tries every way out: the edit and write tools, a shell redirect, `sed -i`, `python -c "open(...,'w')"`, `mv`, `rm`, `git checkout --`, a symlink, `chmod`. Every one is refused or fails; every in-scope write and every new file in scope succeeds. In CI against a fake sandbox, and once live. README and HOW_IT_WORKS then say, in one table, which executors are held before the write and how.

### 4. Ultra plans the tree

A Nemotron planner for `graphene ask`, `node split`, `--about` and `:ask`. Its read-only tools (list, read, grep, glob) run locally against the repo, since a planner writes nothing, and it prints the fenced `plan` block that `ask.py` already parses. Score it on the four tasks: scopes cover `intent_globs.txt` without reaching past it; checks fail at base and pass after; no two leaves share a path. Report per task, and version the planner's prompt.

### 5. `graphene init` asks once

Which planner and which executor, once per repo: asked at a terminal, flags when not; kept in the repo's config; used by `run`, `ask`, `node split` and `:ask`; `--with` still overrides one command. A new repo is offered Nemotron on Token Factory first (the sandbox placement when ConTree is configured, the local worktree otherwise), then Claude Code and Codex as today. `init` checks the key and the model list and says in one line what it could not reach.

### 6. The check in a clean tree

Decision 48's real fix. Locally, the check runs in a temporary worktree of the leaf's commit; in a sandbox, in a fresh fork of the leaf's final state. Nothing a check writes lands in the executor's tree. The test is a check that writes files, and the leaf's commit unchanged. Update decision 48.

### 7. Folding

A thirty-leaf plan reads at 80×24. Done subtrees fold by default; vim's fold keys, where they fit the existing grammar and the help; a folded row, in the one row grammar, says how many leaves are inside and in which states. Before and after at 80×24 and 120×36 in morning.md, taken with the screen harness the polish run left.

### 8. What a judge meets

- **README.** The opening and the hand-back copy stay exactly as they are. The setup line that begins "You need Claude Code" becomes the Nemotron path: install, key, `graphene init`, and what runs where (Ultra plans, Nano or Super do the leaves, each in a Sandbox, the check decides). Claude Code and Codex follow as alternatives. List every README change in morning.md; Alex will put them in his own words.
- **`docs/HACKATHON.md`, a draft.** What Graphene is; how Token Factory, Sandboxes and Nemotron are used, with tonight's numbers; what changed during the Submission Period, taken from git and not from memory (the first commit is 10 August and the period opened 26 August: say what predates it and what was built since); and the feedback the rules ask for, written from tonight's real friction (errors, latencies, docs gaps, SDK changes), concrete enough to be useful to the people who read it.
- **The demo, reproducible.** One script from nothing to the end on feeds: build the repo, `init`, the paragraph, Ultra's tree, a scripted prune, `R` with four Nemotron executors, a hand-back and its offer taken with `w`, done, `git log --graph` reading as the tree, the bill. Then a storyboard for the video: three minutes, the loop on screen, narration that says how Token Factory and Nemotron are used (the rules require it) and nothing about philosophy. If VHS is available, render a draft of the terminal parts from a tape (one is in `docs/proof/`).
- **The bill on screen.** Per leaf and per run, from the usage Token Factory returns, in the record and on the status line: small, factual, labelled as list price.
- **The demo URL.** A static, read-only export of the demo run's record (the page already draws a run from its records) that GitHub Pages can host, and the workflow for it. Do not enable Pages.

### 9. What a stranger carries

The session-era modules are not dead code: `gate.py` imports `bash_written_paths` from `attribute.py`; `commits.py` imports `shell_segments` from it; the record pane and `plan_cli.py` import `node_record.py`; `graph.py` and `server.py` draw the page item 8 turns into the demo URL; `sources/claude_code.py` holds the live hooks next to the transcript backfill. So "cut" means: move what the plan, the gate, the record and the page use into modules named for what they do; delete what only the transcript world uses, with its tests; stop topping up the store from Claude Code's transcripts unless a command still needs it. Green at every step.

The process diary stays whole but leaves the shipped tree. Move the tools still in use (the screen harness) out of `docs/process/` first. Then put `docs/process/` on a branch of its own, `process-archive`, with `git subtree split` so its history comes too, and push it. Write in morning.md the one command that removes the diary from `main`; Alex runs it.

## When the queue is done: the backlog, in order

1. Rerun the frozen configuration on all four tasks, five runs each. Report spreads, not only means.
2. The cost curves: cost per landed leaf against N forks, and the escalation ladder against a single model.
3. A fifth task from outside the four (a small open-source Python repo and one of its real issues) to catch overfitting.
4. `--parallel 8` on a thirty-leaf plan in sandboxes: rate limits, the beta's cap of fifty operations at once, what the screen shows while it happens.
5. A fresh-eyes review of the whole branch by a sub-agent that has not seen the run, given the rules and the criteria and asked to score it as a judge would. Fix what it finds.
6. Sit in the whole demo at 80×24 as Alex would, every key, and fix what is rough.
7. Python 3.14 in the CI matrix (the suite passes on 3.14.4 apart from the environment tests above), and the sqlite DeprecationWarnings from numbered `?N` placeholders bound to sequences, gone.
8. A Nemotron planner *session* for the left pane, once `:ask` has proved the planner.
9. Tavily, only if it makes the planner's trees measurably better on a task that needs outside docs. A bolt-on costs more on the fourth criterion than the bonus is worth.

## What not to do

- No provider framework: one planner module, one executor module, one sandbox module, and the config.
- No Claude or Codex anywhere in the Nemotron benchmark's planner or executor path. The stand-in person may be anything.
- No change to the row grammar, the palette, the README's opening or the hand-back copy.
- No deleting the diary; it moves.
- No tag, no PyPI, no Devpost, no YouTube, no Pages.

## The decisions that are yours

The placement (2a) and the harness; the default executor model and the escalation ladder; the config's format and where it lives; the fold keys; the export format for the demo page; the planner's prompt. Each goes in `DIRECTION.md` as a numbered decision, with its evidence.

## Ground rules

Unchanged, with one exception: nothing leaves the machine except what Token Factory and Sandboxes need tonight, which is the synthetic task repos, Graphene's own public source, and prompts about them. Nothing from Alex's other repos, his home directory or `~/.claude`, and no personal data (Nebius asks for none during the beta). Secrets never appear in a commit, a log, morning.md, a fixture, a prompt or a sandbox image. `~/.claude/settings.json` is his; tags, PyPI, the Devpost entry, Pages and the product name are his; the import-package rename in item 1 is decided here. Branch `nemotron`, pushed green after each milestone, one draft PR whose description stays current; never push `main`, never force-push; the rollback SHA first; keep the machine awake.

## The morning

`docs/process/morning.md`, current at every milestone, leads with:

1. The number. For the frozen configuration on each task: landed, handed back, failed; accept and quality; cost per landed leaf. Then a small table of how it moved over the night.
2. What he can run in five minutes: the Nemotron path end to end on feeds.
3. What waits on him (access, keys, Pages, PyPI, the video) and the decisions to strike.
4. Tonight's decisions, each with its evidence.
5. A dated plan from tomorrow to 30 October: what is left, in order, with the risk of each.
6. The map of the code, where it moved.
7. At most three questions, each only if it blocks the next step.

Then the rollback SHA and the state of every branch.

## When to stop

When every item in the queue and the backlog is done, or blocked with the blocker written down, and the audit passes: the suite green, ruff clean, the wheel smoke, the adversarial gate test fake and live, one live end-to-end demo run on feeds with the frozen configuration, morning.md complete, the PR description current. If your context is compacted mid-run, re-read this file and morning.md before your next change.

Now go. Make the cheap model safe to trust, and prove it.
