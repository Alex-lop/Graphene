# Graphene: the loop directive

*For the Opus 5.5 agent that runs on this repo next. Written 9 October 2026 by the reviewer Alex works with, from a reading of `main` at `af6ff38` (PR #43 merged): the brief, `dev/process/timeline/before.md` and `after.md`, the screens, and the code in `plan.py` (`one_writer`, `check_paths`, `wait_on_checks`, `offers`, `reopen`), `view_time.py` and `nemotron/precheck.py`. Alex has read this and hands it over as it is. Commit it at `dev/process/directives/LOOP_DIRECTIVE.md` before you start. The working rules of the earlier directives hold: a branch named `loop`, small green commits, one PR, `dev/process/morning.md` current at every milestone, the voice rules of the cut directive for everything you write.*

---

## How to work tonight

Alex's instruction, passed on in substance: you have $50 of live testing and he wants it spent. The money is for running the real thing until each change is proven by a number, on Claude Code, Codex and Nemotron, locally and in Token Factory Sandboxes. A run that breaks is the finding, not the end of a lane: fix what broke and run it again. Don't save the budget; don't stop at the first failure; don't leave a lane at "it should work". If something blocks you (a key, a 403, a revoked login, Docker down), route around it; if you still can't, write the exact command for Alex in the brief and go on with the rest. He believes in your autonomy. Decide, act, write down why.

Be relentless about running and verifying. Be stingy about adding: one new key, one new pre-run step, no new visible command, and the README untouched.

## What kind of run this is

The timeline night cut hand-backs from 8 of 10 trees to 4 of 13 and got Nemotron from 21% to 50%. Reading what came back shows the next four things, in order:

1. **The loop has no closing move.** Nemotron takes 1 and 3 came back because the tests leaf found the reader's field names wrong and price 0 not skipped. That is the system working: an integration leaf caught a landed leaf's mistake. But the only way to act on it is a person typing the hidden `graphene node reopen` on the owner. The hand-back offers are `w` and `b`; the one that turns Graphene from a plan with a gate into a system that converges is `r`: reopen the owner with the reason. Lane 1.
2. **The propose-time check reads words, not behaviour.** `check_paths` sees `pytest tests/test_x.py` and not `pytest`, `make test` or `npm test`. Neither remaining hand-back was catchable by it: statements 2 was a stale figure in a file the owner held, statements 3 a scope too narrow. The check that catches all of these needs no model: run each accepted leaf's check at the base commit before anything starts. It exists as `plan precheck` in the Nemotron extra, wrapped around a Nano call. The model-free half belongs in core. Lane 2.
3. **Nemotron at 50% is a coin flip.** `graphene ask --with nemotron` fails every other time. The validator reports one fault per answer and allows one send-back; the mechanical faults (a `needs:` naming no node, a cycle, a `then:` naming a file) can be repaired rather than sent back. Lane 3.
4. **Parallelism is bounded by the repo's files**, and nothing says so. Exclusive scopes plus `needs:` give the shape in the Nemotron screen: reader ∥ validate → wire → e2e. That is correct, and the win is the contract and the visibility, not N× speed. Measure the width and say it. Lane 4.

Then the small things the screens showed (lane 5), the registered arms made ready for Alex on Saturday (lane 6), dogfood (lane 7), and the morning (lane 8).

Net source lines may go up for lanes 1 and 2 and for nothing else. Say the number.

## The budget

One ledger at `~/.graphene/night/`, as the last three nights. Purposes: `planner`, `reopen`, `precheck`, `width`, `takes`, `dogfood`, `verify`. Hard cap $50, nothing new started past $45. Spend in this order: lane 3's measurement (~$20, the biggest line and the one that decides the pitch), lane 1 live (~$8), lane 2 live (~$5), lane 5's takes (~$8), the rest wherever a run says. The key is never printed, copied, written to a file or sent anywhere but Token Factory. Leak checks count and never print.

If `~/graphene-timeline/practice.md` exists (Alex's own practice run), read it before anything else. Every line under "Where the tree misread me" and "What I looked for and could not find" is a finding: fix it tonight if it is small, or answer it in the brief with what you would do.

## Lane 0: the numbers to beat

In `dev/process/loop/before.md`, from last night's records:

- Nemotron proposals by ask, with its one send-back: 15 of 20. By answer: 15 of 30.
- Trees that stopped on another leaf's file: 4 of 13. The two integration hand-backs (takes 1 and 3) by name: they are lane 1's test cases.
- Width: not measured. Lane 4 measures it on last night's recordings first, so there is a before.

## Lane 1: `r` reopens the owner

### What it is

A leaf that came back saying another leaf's work is wrong gets a third offer, beside `w` and `b`: `r` reopens the owner of the path the reason names, with the reason as its note, and makes the came-back leaf wait on it if it doesn't already. Then `R` runs the owner again in a fresh worktree on top of what has landed, its executor reads the note, fixes it, lands a new commit, and the came-back leaf runs after it. Nobody types an id.

### How it works

- `release` already carries `why` and `wants`, and `offers` already computes `owners(node, everything, wanted(...))`. When a wanted path is held by a leaf that is done, offer `r`: `("r", f"reopen {owner} with this reason; {node.id} waits on it", ["node", "reopen", owner, "--note", …])`. When several owners are named, one `r` reopens all of them; say so in the offer.
- `reopen` already puts a done leaf back to open with a note and a new revision. Check what happens to its landed merge: nothing is reverted; the fix lands as a new commit on top. Say that in the record (`reopened after landing; the fix is a new commit`).
- The executor is told the note first, above its contract, in the words the person would use: "came back from `test-e2e`: the reader's field names are wrong (sku, name, price)".
- The executor's side: the release prompt tells an executor that when the leaf cannot pass because another leaf's landed work is wrong, it releases with `--wants <that path>` and a why that names the fault. Add that sentence to the executor's prompt in `run.py` and to the Nemotron executor's system prompt. Nothing else in either changes.
- `w`, `b` and `r` are three rows of one shape in `watch` and in `node show`. A came-back leaf with no owner to reopen shows two rows, as today.

### Measure it

Live, with the two cases from last night rebuilt: feeds on Nemotron (Ultra plans, Nano and Super do the leaves) until a tests leaf comes back on a landed leaf's fault, then `r`, then `R`, and the tree finishes. At least two full loops closed, on Nemotron and on Claude Code (Sonnet executors, a planted fault if a natural one doesn't appear in three runs: say when it was planted). The timeline of each loop in the screens. Count: loops closed, attempts per owner, dollars per loop.

## Lane 2: red first, in core, with no model

### What it is

Before `graphene run` (and `R`) starts anything, every accepted leaf's check is run once at the base commit, in a scratch worktree, in parallel, under `CHECK_TIMEOUT`. Three verdicts:

- **passes at base:** the check proves nothing. The leaf still runs; `run` prints one line per such leaf, `watch` marks the leaf, and `e` is the fix.
- **fails at base on files outside the leaf's scope** (the output names a path, or the command names one, that no scope of the leaf's covers): said in one line with the paths. When another leaf owns them, the existing `wait_on_checks` already adds `needs:`; this is where the whole-suite case (`pytest`, `make test`) is finally caught, by behaviour.
- **fails at base inside its scope:** red first, as it should be. Nothing said.

A verdict is a `precheck` row on the leaf with its revision and the base commit, as the extra already writes it; an edit or a new base runs it again, and nothing else does. `--no-precheck` skips it. A proposed leaf's check is never run on this machine (the extra's rule stays; at `run` time every leaf is accepted).

### How it works

Move the model-free part of `nemotron/precheck.py` into `plan.py` (or a `precheck.py` in core), called from `run.py` before the first leaf starts. The extra keeps its `plan precheck` command, its sandbox fork for proposals, and the Nano reading of a red whose reason the output doesn't say; it calls the core for everything else. The boundary test for the extra still passes.

### Measure it

The statements task, three practice runs as last night (`statements_practice.py`, `--parallel 3`, Sonnet), with precheck on. Count the leaves it flagged, what it said, and whether a flagged check would have come back later. Then feeds twice. Then one run with a planted whole-suite check (`python3 -m pytest -q`) on a leaf whose scope excludes a failing test file: the flag names the file. Wall time of the precheck itself per run, in the brief.

## Lane 3: the Nemotron planner to 80%

- The validator reports every fault of an answer at once, by line or by field, in the words the text form's refusals use.
- Mechanical faults are repaired, not sent back, and each repair is one line on the answer: a `needs:` naming no node is dropped; a cycle is broken at its last edge; a `then:` naming a file is dropped; an id with bad characters is slugged. A repaired proposal says `repaired: …` under the board so the person sees it.
- Semantic faults (a leaf with no scope, a check that is a sentence, a question with no default) are sent back, up to two times, with every fault listed.
- Measure over 20 asks on feeds and 20 on report, Ultra planning. Proposal rate by ask against lane 0's 15 of 20. If it reaches 80%, HACKATHON.md's planner line stays. If it doesn't, HACKATHON.md says, in one sentence, that Nemotron executes and Claude Code or Codex plans, with Ultra planning as the stretch, and the rate measured tonight beside it. Either way the number goes in the brief.

## Lane 4: width, and the honest line

- The timeline computes width: the most lanes with a running attempt at one instant, and the share of agent minutes spent with one lane running. The bill line gains it: `run: 4 done · agents 31 min, $2.41 at list price · width 2 of 3 · you 4 acts, 2 min`. `node show` and `plan record` carry it too.
- Measure it on every run tonight and on last night's four recordings for the before.
- `docs/HOW_IT_WORKS.md` gets one paragraph, in the cut directive's voice, that says what the scopes buy and what they cost: a path has one writer, a check runs only what its leaf owns or what exists at the base, so a plan's width is set by how the repo's files split, and the typical shape is a few leaves side by side then a chain. The README is untouched.

## Lane 5: what the screens showed

- **Ids are never cut.** The time view's label column fits the longest id; titles elide, ids don't. At 80 columns with a 32-character id the time column is 45 cells, which is enough.
- **`node show` says "against base".** When a leaf's check ran against the base version of a file another leaf then rewrote (the cycle case in `wait_on_checks`), the record says so in one line, with the file and the base commit.
- **The `~` mark.** A `needs:` that Graphene added to a person's contract (`plan edit`, `node set --check`) shows as a change in `watch` and in `plan changes`, and the `waits on` line is printed at the command. Verify with a transcript; fix if not.
- **Re-judge after a board answer.** `judge` has two call sites (accept, the text form). A board `then:` line that widens a scope or changes a check must be judged too. Verify with a test that answers a board item whose `then:` widens a scope onto another leaf's file, and fix if the `needs:` doesn't appear.
- **A mid-run screen that is mid-run.** `claude-mid-80.txt` shows both leaves landed. Capture one with a lane still growing.
- **Takes.** After lane 3, up to six takes with `dev/proof/nemotron.sh`, Nano and Super in Sandboxes when ConTree accepts the project, each recorded. The take that ships as the Nemotron demo recording is the cleanest; if none beats take 6, take 6 stays. Say which model did what.

## Lane 6: the registered arms, ready for Saturday

Alex runs the registered arms himself on Saturday. Do not run them. Make them impossible to get wrong:

- Tag the commit the arms run against: `statements-prereg-2`, on `loop` once lanes 1 and 2 are in, and name it in `PREREG-statements.md` with the new blob hashes of `make_task.py`, `accept.py`, `quality.py`, `traps.py`. The old blobs stay in the file as history. A run on any other commit is void, as the file already says.
- `PROVE.md` is current: the wheel built from that tag, its path and version, `newrun.sh` from the same tag, the order P1, T1, T2, P2, the clocks, and the one page he reads once (`intent.md`). Every command in it run once tonight, from a fresh tool install, with the output pasted beside it.
- The rehearsal (`prove.py rehearse`) on the tag reads 5, 5, 0, 0.
- His predictions block in PREREG is still blank and stays blank.

## Lane 7: dogfood

Build lanes 1 and 2 through Graphene with `plan first on`, the meter on, and `watch` on `time`. If a leaf comes back on a landed leaf's fault, press `r`. The bill in the brief: acts, agent minutes, dollars, width, and whether `r` was used on Graphene itself.

## What not to do

- Do not touch the README.
- One new key (`r`), one new pre-run step (precheck). No new visible command.
- Do not run the registered arms. Do not change what `PREREG-statements.md` measures; adding the tag and the blobs is allowed.
- Do not tune a planner's words until a paragraph becomes a tree. Measure, report.
- Do not touch `~/.claude/settings.json`. Do not push `main`. Do not force-push. Do not tag or publish anything but `statements-prereg-2`.
- Do not stop at the first broken run, and do not leave money unspent that a run could have used.

## Verification before the PR

1. Full suite on the CI matrix, `ruff check` clean, `uv build`, the wheel smoke test, `graphene demo --once` from the wheel. The extra's boundary test.
2. Lane 1: two loops closed live, their timelines, and the counts.
3. Lane 2: the three verdicts under tests, the planted whole-suite case flagged live, precheck's wall time per run.
4. Lane 3: the rate over 40 asks, beside lane 0's; the HACKATHON.md sentence it decided.
5. Lane 4: width on every run tonight and on last night's recordings.
6. Lane 5: each item with its transcript or screen.
7. Lane 6: `PROVE.md` run as written from the tag, the rehearsal's 5, 5, 0, 0.
8. The cut's lane 0 (`dev/process/cut/lane0.sh`) still leaves the checkout clean.
9. The ledger under $50, by purpose.
10. `Your 30 minutes` run as written from the pushed branch, at the end, with the time it took.

## The decisions that are yours

- The shape of the `r` row and the executor's release sentence.
- Where precheck lives in core and how its rows and `--no-precheck` are named.
- Which faults count as mechanical.
- How width is defined at the edges (an attempt that ends in the same second another starts).

## The decisions already taken

- `auto` stays as an opt-in. `on` is the default.
- Take 6 is the Nemotron demo recording unless a cleaner take appears tonight.
- The registered arms are Alex's, on Saturday, on the tag.

## The morning

`dev/process/morning.md`, in this order:

**Your 30 minutes**, first, as last night's: a fresh terminal, nothing but `uv` and `git`, nothing that needs a key, each step with what it prints. It covers: installing `loop` as a tool in its own directory; the numbers before and after; `graphene demo` of a closed loop, Tab to `time`, and the `r` row in a came-back leaf's pane; precheck's line on the scratch repo; the three decisions; the merge command.

**Saturday**, second: the three commands that start `PROVE.md`, and the sentence that says what to read first.

**The brief**, at most twenty lines, no paragraphs:

1. The numbers, before → after: proposal rate, trees stopped on another leaf's file, width, loops closed.
2. Watch first: the closed loop's replay, and the best take.
3. The bill, by purpose, against $50.
4. Alex's practice notes: each finding, fixed or answered.
5. Decide: at most three questions, each with your default.
6. Broken or risky: three lines at most.

Below the brief: DIRECTION.md gets "Decisions taken on the night of the loop directive", at most fifteen, each at most three lines. The dogfood bill. The state of every branch and the rollback SHA (`main`'s HEAD when you start).

## When to stop

- At 07:15, start nothing new and nothing live.
- By 07:45, everything is merged into `loop` and green.
- By 07:55, it is pushed, with the PR description current and `Your 30 minutes` run once from the pushed branch.

A lane not reached stops where it stands, with its state written down.

Now go. Close the loop, run red first, get the planner to a number worth printing, and leave Saturday ready.
