# Graphene: the meter directive

*For the Opus 5.5 agent that runs on this repo next. Written 6 October 2026, after the cut directive landed as PR #39 (`main` at `af3da2c`). Commit this file at `dev/process/directives/METER_DIRECTIVE.md` before you start. The working rules of the earlier directives hold: a branch, small green commits, one PR, `dev/process/morning.md` current at every milestone. Where the cut directive said "no new mechanism", this one allows exactly one: the meter.*

---

## A note from Alex (me) 

I believe in this project and I believe in you. You have real autonomy tonight: decide, act, and write down why. You can spend up to $50 on live testing, and I want you to use it. Run the real thing, many times, on Claude Code, Codex and Nemotron, locally and in Sandboxes, and find out what Graphene can actually do. Don't be scared to spend. Don't give up on a lane because the first run broke; a broken run is information, so fix the thing and run it again. Be relentless about finishing and verifying, not about adding. If something blocks you (a key, a 403, Docker down), route around it; if you still can't, write the exact command for me in the brief and keep going. I need this to work, and I think it can.

---

## Note to keep in mind for this run ok: 

- Spend cap: **$50** hard, nothing new started past $45, one ledger for the night.
- The registered arms of the statements experiment (PROVE.md): **still Alex's** (default). Set to "the agent runs them as practice" if you'd rather have numbers than wait.
- The README: **the agent drafts it in Alex's voice** from the voice guide below (default). Alex edits after.
- `docs/` → `dev/` move: **yes** (default).
- Lane order if the night runs short: **1, 2, 3**, with lane 4 throughout (default).

---

## What kind of run this is

The cut made the surface small and the default safe. Two things came out of it that this run fixes, and one thing it builds.

**It fixes `plan first: auto`.** As the cut built it, the agent decides whether the person gets to see the plan. Live, the full feeds paragraph (the one the README's "A real run" is built on) became one leaf, no tree, no board question, under the default. The product's premise is "see what it understood before the work", so the agent can't be the judge of whether you see it. Lane 1.

**It fixes the black box.** For Claude Code and Codex executors (the main path), Graphene knows when a leaf started, when it ended, the exit code, what git says changed, and the check's output. It doesn't know turns, tokens, cost, model, or anything the agent said while working. `watch` shows "attempt 1 … the executor ended (exit 0)". The `usage` rows that `watch` already sums into "the plan: $X at list price" exist only for Nemotron. Lane 2 builds the meter: the record and the live bill, for every executor.

**It rewrites the README in Alex's voice**, short, one speaker. Lane 3.

**And it spends to learn.** Up to $50 of live runs, on all three executors, locally and in Sandboxes, to verify lanes 1 and 2 and to find out what works. Lane 4 is not last; it is how the other lanes are tested.

One new mechanism (the meter). No new visible command: the meter lives in `watch`, in `run`'s output and in `node show`. Net source lines may go up tonight for the meter and only for the meter.

## How to write tonight

The rules from the cut directive hold for everything you write: short sentences, concrete nouns, "it" refers to the previous sentence's subject, imperative for commands, commit subjects under 72 characters. The README has its own voice guide in lane 3.

## The budget

- One ledger for the night at `~/.graphene/night/`, locked with `flock`, as first-light did. Every live call reserves before it spends. Token Factory at list price from the live model list; Claude Code from the `total_cost_usd` its result reports; Codex from its token counts at the model's list price, or tokens alone if no price is known, said so.
- Each row says its purpose: `meter`, `auto`, `statements-practice`, `nemotron-take`, `dogfood`.
- Hard cap $50. Start nothing live past $45. The brief prints the bill by purpose.
- Spend in this order: lane 1's evidence (~$5), lane 2's live verification on all three executors (~$10), the statements task tuned live with stand-ins as practice (~$15), three Nemotron takes for the video (~$10), the rest in reserve for whatever a run reveals.
- The key stays in the environment. Never printed, copied, written to a file or sent anywhere but Token Factory. Leak checks count and never print.

## Lane 1: `plan first: auto`, fixed

Under `auto` the agent always proposes before it writes, as under `on`. Whether the person is interrupted is decided by observable facts about the proposal, never by the agent's judgment and never by the words of the request:

- One leaf, no board item, no protected or read-only path in its scope, and a scope no wider than a few files: it is the person's at once (today's one-line-ask rule) and the agent proceeds.
- Anything else, a board item included, waits for the person in `graphene watch`.

Decide the scope threshold from what the live runs show and write the number and why in DIRECTION. Make `graphene ask` always propose (it's the unattended route; there is nothing else it could sensibly do).

Evidence, live, with Sonnet as the 23 September study used (`dev/process/cut/lane5-evidence.md` has the exact command): the feeds paragraph under `auto` produces a tree the person sees, with its board question, or a one-leaf proposal with a board item that waits. The four Tuesday messages produce one leaf each, taken at once. Run each at least twice. Transcripts in the brief. If the planner still proposes one leaf with no board item for the feeds paragraph, say so plainly, do not tune the wording to force a tree, and report it as the finding it is.

## Lane 2: the meter

### What it is

Two clocks and a bill, on the screen while the work happens, and in the record after.

For every leaf an executor holds, `watch` shows a live row: the executor and its model, elapsed, turns, the last thing it did ("editing validate/rules.py", "running pytest", "reading cli/main.py"), how many seconds ago, files touched (in scope / out of scope), tokens in and out, dollars so far at list price, the attempt number. The dollars climb as the run goes, turn by turn.

For the run, the status line shows the two clocks: `agents: 4 running · 38 min · $2.41` and `you: 3 acts · ~2 min`. The agents' side comes from the executors' streams. Your side comes from what the plan already records about the person: acts (keys in `watch`, commands typed) and attended minutes (a minute in which the person did something). Say "by your keys" somewhere so nobody mistakes it for a measure of reading.

In the tree and DAG views, a running or finished leaf carries a small dim annotation: `$0.42 · 6m`. The plan and the bill in one picture.

At the end, `graphene run` prints one bill line for every executor type, the way it already does for Nemotron: `run: 3 done · agents 41 min, $2.87 at list price · you 4 acts, 2 min`.

In `node show`, each attempt gets its record: model, turns, tokens, dollars, elapsed, what it read, edited and ran, what was refused, what it said last. The transcript's tail, trimmed to `TAIL`, so a came-back leaf says what it tried instead of "exit 1, no output".

### How it works

Not more hooks. Read the executor's own event stream:

- Claude Code: add `--output-format stream-json --verbose` to `DEFAULT_WITH` in `run.py`. Each assistant message carries `usage`; each tool call is a content block; the final `result` object reports `total_cost_usd`, `num_turns`, `duration_ms`, `usage` and the model. Parse it line by line from the stdout you already stream to the attempt's log file.
- Codex: `codex exec --json` emits JSONL (`item.completed` for command executions, file changes and agent messages; `turn.completed` with token usage). Verify the shapes against a real run before writing the parser. Do not assume mine.
- Nemotron: already writes `usage` rows. Add the per-turn rows it lacks so its live row matches the others.
- Any other command: time and the log's tail, as today. The meter knows what the executor tells it, and the row says "no meter" rather than inventing numbers.

Write the parsed events into the leaf's log in the shapes that exist: `usage` rows with `dollars`, `prompt_tokens`, `completion_tokens`, `calls` (so `watch`'s existing sum works unchanged), and event rows for tool calls and said-text. A Claude Code executor in a run worktree is also recorded by the hooks; a tool call is counted once. Decide which record wins where they overlap and write it down.

Nothing new leaves the machine. The record lives in `.graphene/` as today, is `0700`, and git ignores it.

### Why it is worth a mechanism

This is instrumentation. It will not make the tree beat the paragraph, and the README must not claim it does. What it does:

1. It puts the product's own claim on the screen of every run. Graphene's bet is that attention is the scarce thing and agent work is cheap. The two clocks are that bet as a number, measured on the person's own repo, every time.
2. It ends the black box. A leaf idle for six minutes on "running pytest" is visible while it is stuck, not after.
3. It makes a came-back leaf readable: what it tried, what it spent, where it was refused.
4. It is the part of a demo people watch: numbers climbing while trees fill in.

### Evidence

Live, on the feeds task: `graphene run --parallel 2` with Claude Code, then with Codex, then with Nemotron, each at least twice. For each: the `watch` screen mid-run captured at 80 and 120 columns, the final bill line, and `node show` of one leaf. The dollars in the bill line must match the ledger's rows for that run within rounding. A run with an unparseable stream must still finish and land its leaves; the meter degrades, the run does not.

## Lane 3: the README, in Alex's voice

### The voice

Read Alex's site first: https://alex-lop.github.io/Alex_Lopez_Website/. That is the register. Casual, direct, first person, a little self-deprecating, concrete numbers, the occasional parenthetical, "Ok," to start a sentence when he's changing gear, "honestly" when he means it. He says "I know this sounds a little wild" and keeps going. He writes "not claiming it magically saves 397% of your tokens but (ideally) it should help". He writes "Chief Code Reviewer." under a photo of his rabbit. He does not write "the one that", "its" chains, or definitions by apposition, and he does not lecture.

The thesis, in his words from the site, is the only argument the README makes, in under 120 words: the limit on building software won't be tokens or cost, it'll be the human direction it takes to get the software out; no matter how many tokens you have, if you don't say which direction the application should go, the agent has to infer it; Graphene tries to bridge that.

Casual is not sloppy. Every command and every number in the README is true and reproducible tonight.

### The shape, under 900 words

1. **Title, one line, install.** The one-liner says what it does in under 12 words, no metaphor. Then `uv tool install …` and `graphene demo`. One image: the GIF, or a short clip of the board question if you can make one from a live run tonight.
2. **Why I built this.** The thesis above, under 120 words, his voice.
3. **What it looks like.** The feeds run cut to about fifteen lines of real transcript: the paragraph (trimmed to one line), the board question, the tree, `git log --graph`. Two sentences on the result (18 of 20, 12 of 12, six protected files untouched). One honest sentence on the data (three comparisons so far, a plain paragraph did as well for less; the bet is on when you find out), linking to the results.
4. **What's different.** Three bullets, one line each: held by git and the check, not by the model's cooperation; runs any executor (Claude Code, Codex, a command); history reads like the plan.
5. **The meter**, two lines and one screenshot, once lane 2 is real.
6. **Try it on your repo.** Four commands and three keys.
7. **Where it's at.** Three lines: early, built in the open, what he most wants to hear. Links to HOW_IT_WORKS, HACKATHON, the site, Issues. License.

The FAQ, the privacy section and the "How it works" prose move to `docs/HOW_IT_WORKS.md`. The essay's extra paragraphs go to `dev/PRODUCT_THESIS.md`.

### The repo a visitor sees

Move everything that is about building Graphene out of `docs/` into `dev/`: `DIRECTION.md`, `PRODUCT_THESIS.md`, `process/`, `proof/`, `test/`, `screens/`, `demo/` (the build tooling; `graphene demo` reads `src/graphene_map/demo.jsonl` and is unaffected). `dev/README.md` is five lines: this is how Graphene gets built; you don't need it to use Graphene. `docs/` keeps `HOW_IT_WORKS.md` (cut to under 3,000 words, reference not prose, the FAQ and privacy folded in), `HACKATHON.md`, `RELEASING.md`, `assets/`. Update every path: `pyproject`'s `testpaths`, CI, README links, HACKATHON, PROVE, the directives. The suite is green after the move.

Also write `dev/site-blurb.md`: about 100 words for the Graphene card on Alex's site, in the same voice, with the current one-liner and the current stack (Python 3.12+, Typer, Rich, Textual, SQLite, git). The site still says FastAPI and Cytoscape.js. The README and the site should agree; the site is his to change.

## Lane 4: spend to learn

Throughout the night, under the ledger. In this order unless a result changes the order, and say so when it does:

1. **Lane 1's evidence**, as described.
2. **Lane 2 live on all three executors**, as described. This is where the meter gets found out; expect two rounds.
3. **The statements task, tuned.** The brief said sizing it to one to three hours needs a live run. Run it with stand-ins as the person (the 23 September harness) as practice, never registered, two or three times with three parallel executors. Tune the existing code's size until a run lands in the hour-to-three range. Check that cross-cutting constraints ("half-even everywhere", "don't touch vendor/") reach every executor as standing conditions; the agent that built the task predicted the tree loses because they don't. If they don't, make them, and say what changed. Record what the meter showed. Leave the registered arms to Alex unless he flipped the line above.
4. **Three Nemotron takes for the video.** The smallest task where Ultra plans a readable tree, Nano or Super doing the leaves in Sandboxes when ConTree accepts the project, locally when it doesn't. Record each with `graphene demo --record`. Keep the best, say honestly which model did what, and put the recording in `tests/recordings/` with the leak check. If no take is clean, say so and say why.
5. **Whatever a run reveals.** A broken thing found by a live run is fixed and run again before the night ends. Write each one down: what broke, what you did, what it cost.

Dogfood too: build lanes 1 to 3 through Graphene with `plan first on` and the meter on itself. The first real bill of Graphene building Graphene goes in the brief: agent minutes, dollars, your acts.

## What not to do

- No new visible command. The meter lives in `watch`, `run`'s output and `node show`.
- No change to what the registered experiment measures; `PREREG-statements.md` is pre-registered. Tuning the task's size and the standing conditions is allowed and written down.
- Do not run the registered arms unless Alex's line above says so.
- Do not touch `~/.claude/settings.json`. Do not push `main`. Do not force-push. Do not tag or publish.
- Do not claim in the README that the meter changes outcomes, or that the tree beats a paragraph.
- Do not stop at the first broken run.

## Verification before the PR

1. Full suite green on the CI matrix, `ruff check` clean, `uv build`, the wheel smoke test, `graphene demo --once` from the wheel.
2. Lane 1's transcripts, both message kinds, at least two runs each.
3. Lane 2's screens and bill lines on Claude Code, Codex and Nemotron; the bill matches the ledger.
4. The lane 0 scenario from the cut directive (`dev/process/cut/lane0.sh`) still leaves the checkout clean.
5. The README under 900 words, every command in it run tonight.
6. The suite green after the `dev/` move; no dangling path anywhere (`grep -r "docs/test\|docs/process\|docs/proof\|docs/DIRECTION\|PRODUCT_THESIS"` finds only `dev/`).
7. The ledger total under $50, printed by purpose.

## The decisions that are yours

- The `auto` scope threshold and how it reads in the status line.
- Which record wins where hooks and stream overlap, and the exact row shapes.
- The README's one-liner and image.
- How the live row fits at 80 columns.
- The statements task's final size.

## The decisions that are Alex's, with your defaults

In the brief, each with the default you took: anything in the README you were unsure was his voice (quote the line); whether the Nemotron take is good enough for the video; whether the registered arms should now run; what the meter should show that it doesn't yet.

## The morning

`dev/process/morning.md`, current at every milestone. At most twenty lines, no paragraphs:

1. **Watch first:** the best `watch` screen with the meter live, and the best Nemotron take, with the commands to play them.
2. **The bill:** the night's spend by purpose against $50.
3. **`auto`:** what the feeds paragraph did, what the Tuesday messages did, in one line each.
4. **Run in five minutes:** the commands that show the meter on your own repo.
5. **The README:** its word count, and the three lines you're least sure are his.
6. **Decide:** at most three questions, each with your default.
7. **Broken or risky:** three lines at most.

Below the brief: DIRECTION.md gets "Decisions taken on the night of the meter directive", at most fifteen, each at most three lines. The dogfood bill. The state of every branch and the rollback SHA (`main`'s HEAD when you start).

## When to stop

- At 07:15, start nothing new and start nothing live.
- By 07:45, everything is merged into the `meter` branch and green.
- By 07:55, it is pushed, with the PR description current.

A lane not reached stops where it stands, with its state written down.

Now go. Make the agents legible, give the person back the plan, say what this is in Alex's words, and run it until it works.
