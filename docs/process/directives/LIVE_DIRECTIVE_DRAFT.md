# Graphene: the live directive (DRAFT)

**This is a draft. Alex edits it before it is sent, and nothing in it is in force until he does.** It was written on 2026-09-28 by lane C of the shaping run (`SHAPING_DIRECTIVE.md`, lane C's last item), from what that run built on `integ` and `shaping`. Where it needs his choice, it says so under "Before you send this".

**(first light)** Updated on 2026-09-29 by the first-light run with what first light taught. Every sentence that changed or is new says **(first light)**; the rest is the 28 September text. What waits for Alex, with each command, cost and time, is one screen: `docs/test/LIVE_SESSION.md`.

*For the agent that runs on this repo once Alex has a Token Factory key in his shell. The earlier directives hold wherever this one is silent. The winning directive's rules on integrity, claims, secrets and spend carry over word for word, and the "claims the submission must not make" in `docs/process/field.md` are binding. Read `docs/DIRECTION.md` (70 on first), `docs/process/morning.md`, `docs/process/field.md`, `docs/test/results-2026-09-28-live-prereg.md`, `docs/test/results-2026-09-28-shaping.md`, `docs/test/PRACTICE.md`, `docs/process/ideas.md` and this file before you touch anything.*

## Before you send this (Alex)

1. **Merge the shaping PR.** Everything below assumes the board, the views, the settings, the ladder, `arm_a.py` and the three prototypes are on `main`.
2. **Climb rungs 1 to 5 yourself** (`docs/test/practice.sh`, one rung at a time, about 10 to 24 minutes and at most $1.80 by `PRACTICE.md`'s guesses). Live rungs 2 to 7 refuse an agent's shell, so this hour is yours, not the agent's. Rungs 6 and 7 can wait for the run.
   **(first light)** Rungs 1 and 2 passed live on 29 September (01:14 and 01:16; the whole ledger $0.0029, `docs/test/first-light.md`). Rung 1 also met Sandboxes' `ForbiddenError` (403): the project has no Sandboxes access, so rungs 3, 4, 6 and 7, and every leaf placed in a Sandbox, wait for it (ask at tokenfactory.nebius.com/sandboxes/about; `docs/test/LIVE_SESSION.md` has the one-line check). Rungs 2 and 5 need none. Sandboxes are free in the beta by Nebius's page (decision 104).
3. **Choose:** is there a clock (default: none, as in the winning directive), what is the spend cap (default: `GRAPHENE_SPEND_CAP_USD`, 50 if unset), and may the agent spend the key through `bench.py` and `arm_a.py` from its own shell (default: yes, as the winning directive allowed; the ladder's refusal covers only the ladder)?
   **(first light)** The last question is answered in code (decisions 101 to 103): a process with a vendor's agent mark is refused a real Token Factory call and any ConTree sandbox before anything is sent, unless you started its session with `GRAPHENE_AGENT_LIVE_USD` set. That is the opening: every live call and Sandbox operation made under it goes on one night's ledger (`~/.graphene/night/<date>.jsonl`), capped at the lower of that figure and $10, nothing new started past 80% of it, and every row is practice, which `evidence.py` refuses. So the opening lets an agent climb the ladder and practise the prototypes, and the registered runs need it unset. What is left to choose: how a registered run may spend. Unset, the agent's shell is refused; the stand-ins' `as_me` (`newrun.sh`'s `env.sh`) removes Claude Code's marks, so arm A's `arm_a.py` spends under `GRAPHENE_SPEND_CAP_USD` alone, with no night's cap (default: allow it, set `GRAPHENE_SPEND_CAP_USD` yourself, and start `arm_bprime.py` from your own terminal).
4. **(first light) Say whether the opening is set, from the run's first command.** The first-light directive said "Alex set it before sending this", and the variable did not reach that session's environment, so its live half did not happen. The next directive's first command is `docs/test/practice.sh night`: it says whether `GRAPHENE_AGENT_LIVE_USD` is set and prints the night's bill, and nothing else from the environment. The agent writes that line at the top of morning.md and never prints any other variable.

## What kind of run this is

Everything the earlier directives said about how to work holds: doubt your work and never your capacity, decide at every fork and write down why, push green after each milestone, leave one PR, keep `docs/process/morning.md` current, and nothing waits on Alex.

This is the first run with a key. Every Nemotron run so far was against the scripted fake (`tests/fake_tokenfactory.py`) and Docker, and the pre-registered table in `results-2026-09-28-live-prereg.md` has no row. This run fills it, whatever it says.

**(first light)** Two things did run live, both practice: rung 1 (Token Factory listed 25 models; Ultra, Super and Nano each made the one tool call asked of them) and rung 2 (one Nano leaf landed on this machine for $0.000366). The live list's prices replace the fake's placeholders, per million tokens in/out: Nano $0.06/$0.24 (the fake's $0.05/$0.20), Super $0.30/$0.90 ($0.20/$0.80), Ultra $1.00/$3.00 ($0.60/$2.40). Every bill uses the live list (decision 105); the live prices are 1.125 to 1.67 times the placeholders, so any cost worked out at the placeholders is low.

**(first light)** Since this draft: the board's default is `auto` (decision 108): it shows only while a question the repository cannot answer is open, and `board: on` in `graphene config` brings every item back; study 4 chose it by its registered rule. The direction (decisions 112 to 115) is a small tree of goals above the plans in `.graphene/direction.txt`: an agent proposes (`graphene direction propose`), only Alex accepts, a hook refuses an agent's write into `.graphene/` (116), and there is no MCP server (114). As registered it did not answer "what waits on me" faster than `morning.md`; after it named every waiting item, an exploratory pass did.

Submissions close on 30 October at 10:00 PT. The prototypes must be measured by 20 October (`ideas.md`), so anything this run cannot finish is written down as the next run's first step, with its cost.

## Why tonight is about live numbers

1. **Stage One needs a runtime call, and every claim waits on one.** `field.md` forbids any live claim that has not happened: Nemotron planning or executing on Token Factory, a leaf in a Sandbox, landed share, cost per landed leaf, fork timings, the tree against the paragraph. Each becomes sayable only when a ledger row shows it.
2. **The shaping ground is ours only if it holds with Nemotron.** The shaping run changed both planners to ask instead of guessing (prompt version 2), and the board showed, on our own plan, five items that lane B's executors had decided silently (`docs/process/shaping/as-the-person.md`). Nemotron's planner has asked only the fake so far. Whether Ultra puts up questions worth a key press is unknown.
3. **Containment on the service is unproven.** The escape test has passed only against Docker (`field.md`, "Where Graphene differs", 2). Until rung 4 passes on ConTree, no surface says containment holds in Sandboxes, and Docker is never described as Sandboxes. **(first light)** Rung 4 cannot run until the project has Sandboxes access (the 403 above). Meanwhile `graphene init` asks ConTree's whoami and places Nemotron's leaves on this machine, with one line saying why, when it refuses (decision 104): a leaf that ran is not evidence of containment in a Sandbox.

## What does not change

- **The keep list,** as the shaping directive has it.
- **The integrity rule, word for word:** never weaken a check, a scope, the gate, `accept.py`, `quality.py`, a task repo or a test to move a number.
- **The card stays sealed.** You never open `docs/test/tasks/*/intent.md`, `paragraph.md`, `change.md`, `accept.py`, `quality.py` or `intent_globs.txt`. A stand-in reads the card; the paragraph goes from file to command without passing through you, as `practice.py`'s rung 6 does.
- **Nothing tuned once an evidence run has started** (`results-2026-09-28-live-prereg.md`, analysis rule 7).
- **The prototypes are off in every evidence run.** `GRAPHENE_SHAPE` is unset for arms A, B, B′ and C. They are measured on their own rows.

## Before your first change

0. **(first light)** `docs/test/practice.sh night`, first of all: whether the opening is set, and the night's bill. Its line goes at the top of morning.md (item 4 above).
1. Record the rollback SHA. Branch `live` from `main`. Move `docs/process/morning.md` to `morning-2026-09-28.md` and start a new one.
2. **Read the ladder, never the key.** `docs/test/practice.sh status` lists each rung's result and the bill so far. Each rung's log is `.graphene/practice/rung-N.log`, masked by `practice.py` (`mask`, `seal`). Put the status, as printed, at the top of morning.md.
3. **If rung 1 or 3 failed, fix before anything else.** One commit and one test for each cause, then write in the brief which rung Alex climbs again. If rung 4 printed `ESCAPED`, run no leaf in a Sandbox until it is understood (`practice.py`, `MEANS`), and do only the work that needs no Sandbox. **(first light)** Rung 3 failing on the 403 is not a code fault: no commit fixes it, and the work that needs no Sandbox goes on.

## The queue

### 1. First contact: the ladder as the run's first hour

**Why.** First contact with a beta service breaks things, and the ladder was built so that seeing what broke takes minutes. A dry climb passes against the fake and Docker (`practice.sh --dry`, 99 s here, 169 s in the skeptic's climb: `PRACTICE.md`), so only the live calls are new on the ladder's own path (not on the arms' harnesses: below).

**What each failure most likely means** (from `practice.py`'s `MEANS`; the first match wins):

| rung | most likely failure | what it means | what to do |
|---|---|---|---|
| 1 access | `NEBIUS_API_KEY is not set`; 401; 404 | no key in that shell; the key refused; a model id retired | the key in `~/.zshenv` and a new shell; a new key; rung 1 lists today's ids |
| 1 access **(first light)** | Sandboxes `ForbiddenError: You do not have permission to perform this action` (403); rung 1 still passes | the project has no Sandboxes access | ask at tokenfactory.nebius.com/sandboxes/about; rungs 3, 4, 6 and 7 wait; met live on 29 September |
| 2 local leaf | 429; cut off; `did not land` | rate limit; max tokens; the model did not finish | wait a minute; `--max-tokens 8192`; `graphene node show hello`, a finding about the model, not the plumbing |
| 3 Sandbox | `No module named 'contree_sdk'`; `ConTree is not configured`; `AttributeError` | SDK missing; no `NEBIUS_PROJECT_ID`; SDK and service disagree | `uv sync --extra sandbox`; the project id in `~/.zshenv`; read the traceback against `sandbox.Contree`, which speaks contree-sdk 0.3.6 (decision 59) |
| 3 Sandbox | image pull; `setpriv` or `useradd` | `python:3.12` not pulled; the image's users differ from Docker's | the log has the service's words; the sandbox needs bash, git, useradd and setpriv |
| 4 escape | `ESCAPED` | a way out of the scope worked in the Sandbox | stop, as above; this is the finding, and it goes in the brief first |
| 5 recorded | the replay does not end with the leaf done | the recorder or the replay disagrees with a live run | `graphene demo .graphene/practice/leaf.jsonl --once`; the top line must say "as it ran, live" |
| 6 A leaf + B′ | `no sealed paragraph`; `did not land` | the paragraph missing; the model did not finish | the sealer's file; a finding about the model |
| 7 demo | `did not reach the bill`; timed out | `nemotron.sh` stopped early; a slow call | the log's last command is the slow one |

**Rung 6 is not the evidence runs' arms.** Its arm A is one Graphene leaf over the whole repo, not `arm_a.py`; its arm B is B′ (the tree accepted as proposed) through `graphene run`, not `arm_bprime.py`. So `arm_a.py`, `arm_bprime.py` and `evidence.py add` first meet the live service in the first evidence run: watch that run's first minutes. Rungs 6 and 7 are practice: none of their rows enter the table.

**Also:** record rung 5's live leaf in the replay format, sanitised, and replay it in CI, so the live behaviour is pinned (the winning directive's item 1).

**Done when** rungs 1 to 5 pass live, the recording replays green in CI, and morning.md says what broke and what fixed it. **(first light)** Rungs 1 and 2 have passed; 3 and 4 wait for Sandboxes access; 5 does not.

### 2. What is still missing before the arms run

The pre-registration fixed the arms (A, B, B′, C), the tasks, the runs per cell, the metrics and the analysis rules. Two pieces it asked for are built: arm A's harness (`docs/test/arm_a.py`, `docs/test/test_arm_a.py`: 4 passed against the fake) and the forks and escalations counter (`tally.py`, `bench.py`, decision 75). Five are not, and each is committed, with a test, before the first evidence run: **(first light)** 4 and 5 are now built (`docs/test/arm_bprime.py`, `docs/test/evidence.py`, each with its test against the fake, green in first light's full suite: 1543 passed on `f68c0a3`); 1, 2 and arm B's half of 3 are not (`docs/test/trees/` still holds only its README, no decision freezes a configuration, and `standin.py`'s tree and board arms still run Claude Code).

1. **The fixed trees.** `docs/test/trees/` holds only its README. Make `feeds.plan` and `inventory.plan` by that README's procedure: Ultra proposes from the sealed paragraph, a stand-in prunes against the card, every leaf's check fails at the base commit (`bench.py --checks-only`). Keep each `proposed.plan` too: idea 1 (`cover`) is measured on them.
2. **The frozen configuration, as a numbered decision.** Tune on the fixed trees, feeds and inventory only, with `bench.py`. Then freeze in `DIRECTION.md`, at the next free number: the executor prompt version, models by role (resolved from the live list, decision 56), forks, the escalation ladder, `--parallel`, `--rounds`, timeouts, and arm A's budget (one B leaf's frozen budget times the leaves in B's median feeds tree, as the pre-registration says). Tuning rows never enter the table.
3. **The stand-in briefs for arms A and B.** `standin.py` prints briefs for the paragraph, outline and board arms, all with Claude Code. Arm A's brief sends through `arm_a.py` (`--paragraph-file`, then `--follow-up-file`) and reads the bill with `logline.py … --from-json`. Arm B's is the outline arm's with `--with nemotron` for the planner and `nemotron --placement sandbox` for the executor. A diff of any two briefs shows only the arm section.
4. **The B′ harness.** `bench.py` loads a fixed tree and runs no planner (its `--planner` is only recorded). B′ needs: `graphene ask` from the sealed paragraph with Nemotron, `plan accept` whole, the change of mind sent verbatim, offers by decision 65's rule, no reopen, and the same rows as B.
5. **The table and chart script.** `results.py` prints the 25 September shape, one configuration at a time. Write the script that fills the pre-registered table and the hypothesis rows from the rows and the ledger, and draws `docs/assets/evidence.svg`. Test it on hand-built rows before the first evidence run, so the chart's design is fixed before the data exists.

**Done when** all five are committed, `bench.py --checks-only` passes on both fixed trees, and a dry evidence run of each arm on feeds passes against the fake.

### 3. The arms, as pre-registered

Run them exactly as `results-2026-09-28-live-prereg.md` says: feeds five runs an arm, inventory, logs and report three each (C at most one), the order rotating, one run at a time, a different stand-in every run. Arm C is Alex's own Claude Code with Graphene's hooks removed; its cost is Claude Code's reported total and never charted with A, B or B′ as if it were one of them.

Fill the table from the rows by the script, never by hand. Say "higher" or "lower" only where the ranges do not overlap. A void run stays in the file with its reason, and a cell the cap stopped says `not run (cap)`.

**Done when** the table and the hypothesis rows are filled for every cell run, with one sentence under them on what they show, whatever it is.

### 4. The chart

`docs/assets/evidence.svg`, generated by item 2's script from the rows. The README's "Graphene on Nemotron", `docs/HACKATHON.md` and the storyboard use that one file. If it says no, it is reported as plainly, and the one-sentence claim is made only if H1 and H2 both hold on feeds (analysis rule 11).

**Done when** `evidence.svg` rebuilds from the rows with one command, and every surface that shows a number links to its row.

### 5. The demo run, recorded

**What.** Choose the scenario as a numbered decision: a paragraph where Ultra's board has a question worth a key, a trap the tree catches, forks, one hand-back and its offer, a green tree, and the bill. Run it from the frozen configuration with `docs/proof/nemotron.sh`, `RECORD=src/graphene_map/demo.jsonl`, and the tape (`docs/proof/nemotron.tape`) scene by scene. Every cut says so on screen. Then `graphene demo`'s top line says "as it ran, live", not "a scripted stand-in".

**Done when** `graphene demo` replays the live run with no key, and the before and after screens are committed at 80×24 and 120×36.

### 6. New: the shaping study again, with Nemotron as the planner

**Why.** Tonight's study (`results-2026-09-28-shaping.md`) holds the planner (Claude Code) and the executor (Claude Code) equal across the paragraph, the outline and the board. The product's claim on Token Factory is that Nemotron's planner asks good questions. That is a different measurement.

**What.**
- Pre-register it in a new `docs/test/results-<date>-shaping-nemotron.md` before its first run, with tonight's hypotheses and one more: how many board items Ultra puts up per plan, of which kinds, and how many the stand-in changed from the default.
- Change only the planner: `graphene ask --with nemotron` in the outline and board arms. The executor stays Claude Code, as tonight, so the two studies differ in one thing. Run the paragraph arm again, since a different night has different stand-ins.
- **(first light)** The board is `auto` now (decision 108): it shows only while a question the repository cannot answer is open. Count what Ultra puts up with `graphene board --all`, whatever `auto` shows, and say in the registration whether the board arm runs on `auto` or `board: on`.
- **(first light)** Study 1 of 28 September, the one with executors, built nothing: Claude Code's auto-mode classifier refused every stand-in's `claude -p` (seven runs void, four never started, one valid with nothing built). Start the stand-ins where that command may run, or the study repeats that failure (`docs/test/LIVE_SESSION.md`).
- Four tasks, three arms, n = 1 a cell, as tonight. Report it next to tonight's, labelled as a second pilot, never pooled with it.

**Done when** its results file holds the table, the board counts and one sentence.

### 7. New: lane E's prototypes, run live

The three prototypes sit behind `GRAPHENE_SHAPE` and are each a command (`docs/process/ideas.md`). Each read the fake until now. Run each live, and pre-register how it is measured before its first live call. The costs below are from `ideas.md`, at the fake's placeholder Nano price ($0.05 in, $0.20 out per million tokens); the live list prices them.

| prototype | cost (placeholder; **(first light)** at the live Nano price, 1.2 times) | measured by 20 October |
|---|---|---|
| **cover**: your words, accounted for | about $0.0003 a plan; **(first light)** $0.00036 | on each task's `proposed.plan` (item 2.1): a blind judge labels the dropped clauses once, as ground truth for recall and precision; typed characters with the command and without. What counts as a clause is registered before the live planner runs. |
| **note**: notes find their leaf | about $0.0002 a note; **(first light)** $0.00024 | routing accuracy on a correction set built fresh (the 23 September runlogs are outside the repo); characters and person-seconds for a note and its command against an `e` edit of the same change |
| **precheck**: red first | under $0.002 of Nano for a 10-leaf plan, plus one Sandbox fork a distinct check (ConTree's price not in the docs read); **(first light)** under $0.0024, and Sandboxes free in the beta (decision 104) | the share of flagged checks on Nemotron-planned trees, which must agree with `score_tree.py`'s base-run verdicts on "passes already"; Nano's verdicts against hand labels on about 40 red tails; seconds a fork |

**Done when** each has its live rows, its cost from the ledger, and a line in `ideas.md` saying what the live run changed about its rank.

**(first light)** `docs/test/practice.sh prototypes` practises all three on a fixed plan in a throwaway feeds, 4 or 5 Nano calls and one sandbox fork (skipped, and said, without Sandboxes access), under a $0.05 cap. It is practice: its rows never measure a prototype.

## Spend

The cap and the rules at 80% and 100% are the winning directive's. Spend in this order: the ladder (at most $7.80 for all seven rungs, `PRACTICE.md`); the fixed trees and tuning; the arms on feeds; the arms on the other tasks; the demo run; the Nemotron shaping study; the prototypes. The prototypes cost cents, and nothing waits on them.

**(first light)** Practice spends under the opening, on the night's ledger: the lower of `GRAPHENE_AGENT_LIVE_USD` and $10, nothing new past 80% of it, a call whose worst case would pass it refused unsent, and no reset on a rerun (decisions 101 to 103); `practice.sh night` prints it. The ladder's own caps add up to $7.80 at most, so one night's $10 holds it. Registered runs spend with the opening unset, under `GRAPHENE_SPEND_CAP_USD` (the pre-registration says 50 if unset; `bench.py` and `arm_bprime.py` say 30: set it), on the ledger named by `--ledger` or `GRAPHENE_LEDGER` (`bench.py`'s default is a file of 25 September: name one). The estimates for each piece are in `docs/test/LIVE_SESSION.md`.

## What not to do

**(first light) Two harness hazards found on first light, each a rule now:**
- A test suite run from `git bisect run`, a hook or `rebase --exec` inherits `GIT_DIR` and its kin, and a task repo's init, add and commit then went into the repository running the suite. The suite now hands none of it to its tests (`tests/test_git_location.py::test_a_suite_started_with_git_location_set_hands_none_of_it_to_its_tests`). Start any harness that builds repos without those variables.
- Every zsh reads `~/.zshenv`, so any shell a harness starts (a tmux seat, a rehearsal's stage, a stand-in's) has the real key: the rehearsal sent it to the local stand-in on 127.0.0.1. The chokepoint refusal (103) is what stops an agent, not the key's absence. Start stand-in stages with `/bin/bash`, and run tests and stand-ins with `env -u NEBIUS_API_KEY -u NEBIUS_PROJECT_ID` wherever nothing is meant to spend.

- No looking for, reading or printing a credential. `graphene key check` shows that the key is reached, never the key.
- Nothing from a stand-in shown as live, and no Docker footage shown or described as Sandboxes.
- No claim that `field.md` forbids. The one it allows is "we found no other entry where a person prunes the plan", never "nobody".
- No number without a ledger row, and no row from a practice rung or a tuning run in the table.
- No tag, PyPI release, Devpost entry, YouTube upload, Pages switch, About text or repository setting: those are Alex's.

## The decisions that are yours

The frozen configuration, the demo scenario, the chart's design, the Nemotron shaping study's extra hypothesis, and how each prototype's measure is registered. Each goes in `DIRECTION.md` at the next free number, with its evidence.

## Commits and ground rules

- Many small commits, one logical change each, green before it is pushed, pushed after each milestone.
- Work on branch `live`, cut from `main`, with one draft PR whose description stays current.
- Never push `main`, and never force-push.
- `~/.claude/settings.json` is Alex's. Keep the machine awake.
- What leaves the machine: what Token Factory and Sandboxes need for the task repos and Graphene's own source, and for arm C and the shaping study, the synthetic tasks' prompts to Claude Code.

## The brief: the top of morning.md

Current at every milestone, twenty lines at most:

1. **The ladder:** each rung's result as `practice.sh status` prints it, and what broke. **(first light)** Above it, `practice.sh night`'s line: whether the opening is set, and the night's bill.
2. **The table and the chart,** and one sentence on what they show, whatever it is.
3. **New:** five lines at most, each with the command that shows it.
4. **Decide:** at most three questions, each with your default.
5. **Broken or risky:** three lines at most.

Below it, as usual: decisions, evidence, screens, the state of every branch, and the rollback SHA.

## When to stop

When the queue is done or blocked in writing, and the suite and CI are green on every job. A piece that is not done stops where it stands, with its state and its next command written down.

Now go. Make the first live numbers true, whichever way they point.
