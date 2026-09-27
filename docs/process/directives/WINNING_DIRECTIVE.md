# Graphene: the winning directive

*For the agent that runs on this repo next. Written 2026-09-25 with Alex, after the Nemotron run (PR #29) and an outside read of it against the hackathon's rules and against what Graphene is for. The earlier directives still hold wherever this one is silent, and the Nemotron directive's rules on integrity, secrets and spend carry over word for word. Read `docs/DIRECTION.md` (decisions 53 to 69 first), the Nemotron run's `docs/process/morning.md`, `docs/HACKATHON.md`, `docs/demo/STORYBOARD.md`, the official rules (https://nebiusglobalaihackathon.devpost.com/rules) and this file before you touch anything.*

## What kind of run this is

Everything the earlier directives said about how to work holds: there is no clock, doubt your work and never your capacity, decide at every fork and write down why, keep `docs/process/morning.md` current at every milestone, push the branch green after each, leave one PR, use sub-agents in parallel wherever work is independent, and nothing waits on Alex.

The Nemotron run built the path. This run makes it win. One question sits under every item: *what will a judge see, and is every word of it true?* The last run never touched a real model. This one starts with a key, and nearly everything that matters is live. Submissions close on 30 October at 10:00 PT. Most of what decides the result can be built or measured tonight, so expect this to be the longest run yet.

## Why we are doing this

### This hackathon is Graphene's argument, not a detour

Alex's thesis, from his own site: the limit on building software will not be tokens or cost but the human intervention it takes, and Graphene bridges the person and the agent so the agent does not have to guess. Token Factory sells the other half of that sentence: tokens cheap enough to spend in bulk. But a cheap model you cannot trust does not save attention. It spends it, on reading diffs and cleaning up after them.

So the question every Token Factory customer is really asking is the one Graphene answers: *how do I hand real work to a cheap model and trust what comes back?* The tree, the scope, the check and the sandbox are that answer. This is the stage where the thesis is most testable and most valuable, in front of the people who build the models and sell the tokens.

### Why Graphene can win

- **The field.** Over 11,000 people registered. Most entries will be a chat over code, a wrapper around one model call, or a demo that stops at a proof of concept. The Design criterion asks for a complete, coherent product, and Graphene already is one: a terminal app with vim keys, a plan as text that round-trips, 758 tests, CI on three Pythons and two platforms, a package, and docs that say what does not work.
- **The idea is non-obvious in the sponsor's own terms.** Sandboxes branch like git, and Graphene's plan is a tree. Each leaf forks from one checkpoint, a cheap model gets several tries in parallel microVMs, and the check, not the model, decides what lands. Nobody else maps a person's pruned tree onto a tree of sandboxes.
- **The boundary is real.** A write outside the scope is refused before it happens, the sandbox's own permissions hold what the tool refused, and the check runs in a clean tree on only what came back. Most agent tools trust the model. Graphene proves containment, and can show the log.
- **The judges.** They are NVIDIA's software and AI engineers, Token Factory's product marketing and developer relations, and Nebius's product and ML research leads. Engineers reward real integration and rigour. Product and DevRel people reward a story their customers would act on. Researchers reward honest evaluation. Everything below is aimed at all three.

### Why it would lose today, and which item fixes each

1. **Nothing has run on Token Factory or in a Sandbox.** Stage One is pass/fail on a runtime call and a genuine attempt at the track's goal. A strict screener fails a project with no live run, and every number in the submission is empty. → Items 1 and 2.
2. **Its central claim is unproven by its own tests.** On 23 September a plain paragraph passed as many hidden checks as the tree, with less of the person's time. Potential Impact is scored on what is demonstrated. → Item 2, the arms.
3. **The non-obvious part is invisible.** The screen shows no forks, no escalation and no sandbox, and the storyboard has neither the evidence nor the forks. Quality of the Idea is scored on what judges see. → Items 3 and 4.
4. **The front door reads wrong either way.** Today a Nebius key is required in the first ten minutes: that reads as an ad, and it turns away every user who already has an agent. The opposite mistake, Nemotron as one `--with` among three, reads as a bolt-on. → Item 7.
5. **A judge without a key has nothing to run,** and judges may score on the video and the text alone. → Items 4, 7 and 9.
6. **First contact will break things.** ConTree's docs describe an API its released SDK does not have, Docker is not ConTree, and judges may test until 15 December while models get retired. → Items 1 and 8.

### Why this must also be good for Graphene after October

The Google hackathon's Firestore requirement bent the product around a sponsor's stack, and Alex says it killed the product. It does not happen twice. Graphene stays the shared plan between a person and whatever agents they use. Nemotron on Token Factory is how this submission proves the claim, and a first-class path any user can choose, never a requirement.

The rule for every item: if it helps the submission and hurts the product, it does not ship. This is also how it wins. Stage One fails "a superficial rebrand", and Design rewards a product people would use without the sponsor in the room.

## The claim, and the one chart that carries it

The submission makes one claim: *Graphene makes a cheap open model safe to hand real work.* A person prunes the tree Nemotron 3 Ultra proposes; Nemotron Nano does the leaves in Token Factory Sandboxes forked from one checkpoint; the check decides what lands.

One chart carries it: the same paragraph, the same model, with the tree and without it. It measures correctness (hidden acceptance and held-out quality), the person's attention, and dollars.

If the chart says yes, it is the centrepiece of the README, the video, the demo page and the Devpost text. If it says no, it is reported as plainly, and the run says what it learned. It is never cooked. A chart that survives an NVIDIA engineer's second look is worth more than a prettier one that does not.

## What does not change

- **The keep list:** the README's opening and hand-back copy, the row grammar, the palette, plan first, the text form, `--with` on `run` and `ask`, the boundary as check-plus-git out of process, "what does not bind", the gif, and the distribution `graphene-map`.
- **The integrity rule, word for word:** never weaken a check, a scope, the gate, `accept.py`, `quality.py`, a task repo or a test to move a number.
- **The card stays sealed.** As `docs/test/trees/README.md` has it, whoever tunes the executor never reads a task's card, its paragraph or its scorers.
- **The executor stays a reference executor.** What helps every executor (the leaf's contract, the check's feedback, forks, escalation) goes into Graphene. What helps only Nemotron stays small, in `tokenfactory.py` and `executor.py`.

## Before your first change

1. Record the rollback SHA. Branch `submission` from `main`. Move `docs/process/morning.md` to `morning-2026-09-25.md`, and start a new one.
2. **Access is the gate.** Alex ran `uv run python docs/test/access.py` before sending this. Run it again first thing, and put its output, redacted, at the top of morning.md: the model ids, one tool call per model, and ConTree's timings for make, run, fork and two forks at once.
3. **If access fails, do not spend the night on stand-ins.** The path against the fake already exists, and another night of it adds nothing a judge sees. Do only what needs no key: item 3's screen work against a recording, item 7, item 9's skeleton, items 11 and 12, and item 8's fault tests against the fake. Then stop, with the blocker as morning.md's first line.
4. **Spend.** The cap is `GRAPHENE_SPEND_CAP_USD`, 50 if unset, with the same ledger and the same rules at 80% and 100%. Spend in this order: first contact; tuning on Nano; the arms on feeds; the arms on the other tasks; the demo run; everything else. Arm C (item 2) runs on Alex's own agent, not Token Factory: five runs on feeds, at most one on each other task.
5. **The environment tests** (the TTY prompt, the hook time budget) are handled as before: note them, never loosen them.

## The queue

Each item says why, what, and when it is done. Items run in lanes (below), so the wall clock the benchmarks take is never idle.

### 1. First contact (serves 1 and 6)

**Why.** Every other item needs the path to work for real, and first contact with a beta service is where things break. Better tonight than on camera.

**What.**
- Run one live leaf on feeds in the local placement, then one in a Sandbox.
- Fix what breaks, one commit and one test each: the SDK against the service, the image and `--prepare`, the sandbox's users and `setpriv`, output caps, timeouts, 429s, and network from inside the sandbox.
- Record the live leaf in the fake's replay format, sanitised, and replay it in CI, so the real behaviour is pinned from tonight on.
- Run the escape test live in ConTree. The containment claim has to hold on the sponsor's service, not only in Docker.

**Done when** one leaf has landed live in a real Sandbox, the escape test passes live, and the recording replays green in CI.

### 2. The evidence (serves 1 and 2)

**Why.** Two criteria turn on this. Potential Impact asks whether the solution addresses the problem *based on what's demonstrated*. Technological Implementation asks how effectively it uses Token Factory and Nemotron. One honest comparison answers both. It is also the thing Graphene has never had: proof that the tree is worth the person's time.

**What.**

- **Pre-register.** Before the first evidence run, write the hypotheses, the arms, the metrics and the table you will report in a new `docs/test/results-<date>.md`, and commit it. Later analyses are welcome, labelled as after the fact. Engineers believe a table that was written before the data.
- **One paragraph per task feeds every arm.** A stand-in writes it once from the card, and it is kept with the card, sealed as above.
- **The arms:**
  - **A. The paragraph to Nano, no tree.** This is the protocol's prompt arm, with a Nemotron session as the agent: the same tools and budget, the whole repo, no plan and no check. The stand-in reads the diff and may follow up as `PROTOCOL.md` allows.
  - **B. Graphene.** Ultra proposes from the paragraph, and the stand-in prunes with `graphene watch`'s commands. Nano, with the frozen forks and escalation, does the leaves in Sandboxes, and the mechanical person takes offers.
  - **B′. Graphene without the prune.** The tree is accepted as proposed. B against B′ is what the person's prune is worth, which is the vision's own question.
  - **C. A frontier agent, for reference.** The prompt arm with Alex's own coding agent. It is a point on the map and never part of the Nemotron path. It answers the question a Token Factory customer asks: how close, and at what cost?
- **Tasks and runs:** feeds (five runs an arm), inventory, logs and report (three each), and item 5's real repository, as many as the budget allows.
- **Counted for every run:** accept, quality, modelled person-seconds (`attention.py`, from the log, as the protocol does), dollars and wall time. For B and B′, also landed, handed back, failed, forks and escalations.
- **Tuning comes first.** It uses fixed trees (made as `docs/test/trees/README.md` says), on feeds and inventory only, until the configuration is frozen as a numbered decision. Report, logs and the real repository run only with the frozen configuration. The executor's prompt is the same for every task, and nothing that runs as the planner or the executor reads `docs/test/tasks/`.
- **The chart** is generated by a script from the ledger (`docs/assets/evidence.svg`), and every surface uses that one file.

**Done when** the pre-registered table is filled from the ledger for every arm and task, with spreads, the chart builds from it, and morning.md opens with both, whatever they say.

### 3. Make the non-obvious visible (serves 3)

**Why.** Judges score the idea they can see, and today the screen shows none of it.

**What.**
- In `graphene watch`, in the one row grammar, a leaf with forks shows them under it: which fork, its state, its model.
- An escalation is a state change that names the model.
- The node pane shows the leaf's sandbox (its checkpoint, operations and seconds) and its bill.
- The record says which fork won and why the others lost.
- The exported page draws the tree of sandboxes: each leaf with its forks under it, the winner marked.
- Take before and after screens at 80×24 and 120×36.

**Done when** a live run at 80×24 shows forks and an escalation that a stranger can read without being told.

### 4. The demo run and the video (serves 3, 5 and every criterion)

**Why.** Judges may score on the video and the text alone. For most of them the video *is* the product.

**What.**
- **The scenario, chosen and justified as a decision.** Pick the repository and paragraph that show the whole loop inside three minutes: a trap the tree catches, forks, one hand-back and its offer, a green tree, `git log --graph` reading as the tree, and the bill. Use item 5's real repository if it serves; feeds if not.
- **The live demo run,** recorded scene by scene with VHS from the frozen configuration. Waits are cut, and every cut says so on screen (×8). Nothing on screen comes from the stand-in.
- **The storyboard, rewritten to win.** In order:
  - fifteen seconds of the problem, specific: cheap models are cheap, and nobody hands one a paragraph and walks away;
  - the paragraph, then Ultra's tree, then the prune, then `R`;
  - the forks scene, the non-obvious use in eight seconds: one checkpoint, N microVMs, the check picks;
  - a hand-back and `w`, then the tree going green;
  - the chart, the bill, the end card.

  The narration covers what the rules require, how Token Factory and Nemotron are used. It stays under 400 words for 2:50 and reads its numbers off the screen.
- **A draft cut.** Assemble `docs/demo/draft.mp4` with ffmpeg from the scenes and the chart, with the narration burned in as subtitles and silence where Alex's voice goes.
  - No music and no logos: the rules forbid third-party marks and copyrighted music without permission.
  - Do not commit the video. Commit what rebuilds it (`docs/demo/build.sh`).

**Done when** the draft is under three minutes, every frame is from the live run or the generated chart, and Alex's remaining steps are written out with the time each takes.

### 5. A real repository (serves 2)

**Why.** Synthetic tasks prove the mechanism. A real repository proves the audience.

**What.**
- Choose a small, active, permissively licensed Python repository, and an open, well-specified issue that a tree of three to six leaves can resolve. Work in a local clone.
- Run arms A and B on it with the frozen configuration, and record the run for the demo page.
- If B's result is good, write the patch and a pull-request description for Alex to open upstream. Never open it yourself.

**Done when** `docs/test/real/<repo>/` holds the paragraph, the tree, the ledger rows, the patch and the draft PR text.

### 6. Graphene builds part of itself on Nemotron (serves 2 and 3)

**Why.** The most credible demo is the tool shipping its own work. A git log where a feature's leaves were written by Nemotron Nano, held to their scope and checked in a Sandbox, is evidence no slide can match.

**What.**
- Once item 1 passes, take one real, well-scoped feature from this run and do it through Graphene. Good candidates: a test suite, the replay command's tests, the chart script, docs.
- You write the paragraph, Ultra proposes, you prune, you press `R`, and you take or refuse the offers.
- The boundary's own code (the gate, layer 2, the clean-tree check) stays hand-written and reviewed.
- Review every landed leaf before the milestone push.
- Export its record as the demo page's second view: *the tree that built part of this submission*.

**Done when** at least one real feature has landed this way, and morning.md says how many of the run's commits Nemotron landed, and at what cost.

### 7. The front door, for users and for judges (serves 4 and 5)

**Why.** Three constraints meet here. The rules require the README to highlight Nemotron and Token Factory. Stage One rejects a rebrand. And a user who already has an agent should never meet a signup first. One door with two paths satisfies all three.

**What.**
- **The README.** The opening stays. Directly under it goes *Graphene on Nemotron*: the claim, the chart, three sentences on what runs where, and a link to `docs/HACKATHON.md`. The first ten minutes then offers two paths side by side: with the agent you have, or on Nemotron through Token Factory. The first path needs no key.
- **`graphene init`** offers what it finds (a key in the environment, `claude` or `codex` on the path), asks once, and says in one line what each choice needs. Nothing is "offered first" by fiat, and `init --help` says so. This revises decision 61; write the new one.
- **`graphene demo`, for a judge with no key.** It replays the recorded live demo run in `graphene watch`, exactly what Nemotron did, with a line saying it is a replay. It needs no key, no Docker and no network, and runs no model-written code on the judge's machine. It ships in the wheel.
- **The demo URL:** the exported page of the live demo run, with the dogfood tree as its second view, and the Pages workflow ready for Alex to start.
- **Testing instructions** for judges, in ten lines: the no-key path first, then the key path.

**Done when** a clean container can install the built wheel, run `graphene demo` with no key, and, given a key, run the Nemotron path on feeds.

### 8. Survive the judging period (serves 6)

**Why.** Judges may test until 15 December. Token Factory retires models on notice (it published notices in June and August 2026), Sandboxes are in beta, and the rules require the project to run consistently.

**What.**
- Roles resolve from the live model list and fall back within the family with a one-line warning, never a crash. Test it with a list that has lost Ultra.
- Each of these faults gets a test and a message a person can act on:
  - 429 storms, 5xx errors and timeouts;
  - a reply cut off, or a malformed or text-only tool call;
  - a sandbox operation killed mid-leaf, and the beta's cap of fifty operations at once;
  - a check that hangs.
- In every case the leaf comes back with its cause, the run goes on, nothing is left running, and the screen says what happened.
- Then run `--parallel 8` on a thirty-leaf plan, live, inside the cap.

**Done when** every fault above has its test, and the thirty-leaf live run finishes or fails cleanly.

### 9. The submission text (serves every criterion)

**Why.** The form is the first thing every judge reads, and the only thing some read.

**What.**
- `docs/HACKATHON.md` becomes the Devpost fields: Inspiration, What it does, How we built it (Token Factory's API, Sandboxes' forks, Nemotron's roles and reasoning budgets), Challenges, Accomplishments, What we learned, What's next, Built with, and the testing instructions.
- The account of what changed during the Submission Period comes from git, checked again with `git blame` at the end of the run.
- The feedback on Token Factory, Sandboxes and Nemotron is concrete and reproducible, drawn from tonight's real friction. It is also judged for a prize of its own.
- Every number links to its ledger row. Alex will put it all in his own words; your job is that every sentence is true and specific.

**Done when** every field has a draft, and the judges' seats (item 10) find no claim they cannot trace.

### 10. The judges' seats (serves every criterion)

**Why.** It is the cheapest way to see what a judge will see and we will not.

**What.**
- Run one sub-agent per judging role on the hackathon's page: an NVIDIA software engineer, a Token Factory product marketer, a Nebius developer-relations lead, a Nebius ML researcher.
- Give each only what that judge gets: the draft video, the Devpost text, the README, the repository.
- Each runs the Stage One check and scores the four criteria out of ten, with reasons.
- Fix the three findings that matter most, score again, and report both rounds.

They are a proxy. Evidence outranks them, and their taste never overrides the vision.

### 11. Know the field (serves 3 and 4)

**Why.** Judges compare, and a claim of "the only one" that turns out false costs more than it ever earned.

**What.** Search GitHub and the project gallery for public Coding-track entries. Keep a short private note under `docs/process/` with three things:
- what each entry shows;
- where Graphene differs: the person's prune, containment proven on the service, forks as the tree, the evidence;
- which claims the submission therefore must not make.

### 12. Release readiness (serves 5 and 6)

**Why.** The rules require that the project install and run consistently. A git URL is fragile, and judges may install in December.

**What.**
- Prepare 0.5.0: `pyproject.toml`, `__version__`, the CHANGELOG and release notes.
- Build the wheel, install it in clean containers on Python 3.12, 3.13 and 3.14, and run `graphene demo` and the Nemotron path from it.
- Alex publishes.

## Lanes

The benchmarks are bound by the wall clock, so use the wait.

- **The main line:** item 1, then tuning and the frozen configuration, then item 2, then item 4's live run.
- **In parallel once item 1 passes:** items 3 and 6, and item 7's replay and front door, each in its own worktree.
- **In parallel from the start (no key needed):** item 8's fault tests against the fake, items 11 and 12, and item 9's skeleton.
- **Last:** item 4's cut, item 9's numbers, then item 10, then a final pass on everything item 10 found.

## When the queue is done: the backlog, in order

1. More runs wherever the spreads are wide.
2. The cost curves: dollars per correct leaf against the number of forks; the escalation ladder against Super alone; and Graphene with Nano against the paragraph to Ultra, which is the sponsor's own question of when to reach for the big model.
3. Reasoning budgets per role: Ultra's effort against tree quality (`score_tree.py`), and Nano's against landing.
4. The planner with Token Factory's structured output, if it cuts parse failures, measured against the text form.
5. A second real repository.
6. Layer 2 around any `--with` executor in a Sandbox: containment for Claude Code or Codex on the sponsor's service. It is the on-vision generalisation of what the last run built for one executor, and a story Sandboxes' own team would tell.
7. Tavily, only if it makes the planner's trees measurably better on a task that needs outside docs. A bonus award can stack with a track award, but a bolt-on costs more on Quality of the Idea than the bonus is worth.

## What not to do

- Nothing from the stand-in shown as live, anywhere: screen, video, README or Devpost. Every time-lapse is labelled.
- No number without a ledger row, and no claim without a source.
- No change to the README's opening, the row grammar, the palette or the hand-back copy.
- No provider framework, and no Nebius-only idea in the plan, the store or the gate.
- No video, no recording that holds a secret, no key and no sandbox or project id in a commit.
- No tag, PyPI release, Devpost entry, YouTube upload, Pages switch, upstream pull request or repository setting: all Alex's.

## The decisions that are yours

The frozen configuration; the demo scenario and repository; the real repository and its issue; how forks look on screen; the replay's format; the chart's design; which feature is built on Nemotron. Each is a numbered decision in `DIRECTION.md`, from 70, with its evidence.

## Commits

Make them many and small. Alex reviews by commit, a live regression is found by bisecting, and the git log is itself demo material.

- One logical change a commit, in the repo's style: a sentence saying what is now true.
- Green before it is pushed, and pushed after each milestone.
- One PR, whose description stays current.

Never pad: a commit that changes nothing a person or a test would notice is not made.

## Ground rules

Carried over, with one widening. What leaves the machine is what Token Factory and Sandboxes need for the task repos, Graphene's own source and item 5's public repository; and, for arm C, the synthetic tasks' prompts to Alex's own agent. Nothing leaves from his other repositories, his home directory or `~/.claude`, and no personal data.

Secrets never appear in a commit, a log, morning.md, a fixture, a recording, a prompt or a sandbox image. `~/.claude/settings.json` is his. Work on branch `submission` with green pushes and one draft PR. Never push `main` and never force-push. Record the rollback SHA first, and keep the machine awake.

## The morning

`docs/process/morning.md`, current at every milestone, leads with:

1. The chart and the pre-registered table, and what they say in one sentence, whatever it is.
2. First contact: what broke, how it is fixed, and the escape test live.
3. What a judge sees: the draft video, the demo page export, the README section, the Devpost draft, and the judges' seats before and after.
4. What only Alex can do, in order, with the time each takes: the voice-over, Pages, PyPI, the About text, the Devpost form, the diary command.
5. Decisions from 70, each with its evidence.
6. The plan to 30 October: what is left, in order, with its risk, and what is frozen.
7. At most three questions.

Then the rollback SHA and the state of every branch.

## When to stop

Stop when the queue and the backlog are done or blocked in writing, and the audit passes:

- the suite and CI green on every job;
- live: a leaf in a Sandbox, the escape test, and the demo run;
- the evidence table filled from the ledger;
- `draft.mp4` built;
- `graphene demo` working from a clean container;
- morning.md complete, and the PR description current.

If your context is compacted, re-read this file and morning.md before your next change.

Now go. Show them the loop, show them the number, and make every word of it true.
