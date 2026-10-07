# Graphene: the cut directive

*For the agent that runs on this repo next. Written 4 October 2026 from an outside review of `main` at `4e5a2a9`. Commit this file at `dev/process/directives/CUT_DIRECTIVE.md` before you start. The working rules of the earlier directives still hold (branch, small green commits, one PR, `dev/process/morning.md` current at every milestone). Where an earlier directive told you to build something this one tells you to remove, this one wins.*

---

## Alex decides before sending this (edit, then delete this block)

- Web UI (`graphene ui`, `ui/`, `server.py`, `graph.py`, the static bundle): **delete** (default) or hide.
- `graphene direction`: **hide** (default) or keep visible.
- `plan first` default for new repos: **auto** (default, defined in lane 5), or stay `on`.
- The Nemotron work: **becomes an optional extra in its own subpackage** (default), or moves to a branch.
- Lane order if the night runs short: **1, 2, 3, 4, 5** (default).

---

## What kind of run this is

Every run so far added a mechanism. This run removes more than it adds. Success tonight is measured by what is gone, by a default that is safe without being asked, by help text a stranger can read, and by an experiment Alex can run himself on a weekend.

The diff should be net negative in source lines. When you are unsure whether to build something, do not. If something seems to need a new command, write down why in the brief and do not add it. The earlier directives told you there is no clock and no budget. Tonight there is a budget, and it is on scope: nothing new, only less and safer.

Two things from the review decide every argument below:

1. **The product's own data says a paragraph wins.** On 23 September the paragraph arm beat the tree arm on every attention measure (modelled seconds 2626 vs 3869, words read 3304 vs 6879, cost $0.97 vs $1.47) with the same outcome, and "misunderstandings caught before code" came out at 0 or 1. The README says so. Until there is a task where a paragraph alone fails, Graphene is a bet with no evidence. Lane 4 builds that task.
2. **Nobody uses it, and the surface is huge.** 0 stars. PyPI is at 0.2.0 with the description of a different product. 13 top-level commands, 18 under `plan`, 13 under `node`, a TUI and a web UI, 22.6k lines of source, 26.7k of tests, 1,058 files of docs of which 11 MB is logs and spikes, 136 decisions in DIRECTION.md, ~3,700 lines for an executor that finished 2 of 5 plans. Lanes 2 and 3 cut.

The other findings, each one line, so you know the why: `graphene run` defaults to the mode that dirties the person's checkout (lane 1); plan-first taxes every small attended ask (lane 5); the CLI help is written in a voice a new user cannot scan (lane 3); Claude Code now ships plan mode, `--worktree` and worktree-isolated subagents, so "see the tree first" is table stakes and what is unique is the contract enforced out of process by git, across executors (the README's facts, lane 2).

## How to write tonight

This applies to help strings, the CHANGELOG, DIRECTION.md, commit messages and the brief. The current voice is one agent's house style: long sentences held together by "it", "its" and "the one that", and definitions by apposition. It does not scan. The rules:

- Short sentences. One idea each.
- Concrete nouns. "The executor writes outside its scope" not "a write it was not given".
- "It" and "its" refer to the previous sentence's subject, never further back.
- Imperative for commands: "Run every ready leaf." Present tense for behaviour: "Graphene runs the check."
- No colons chaining three clauses. No parentheses inside parentheses.
- Commit subjects ≤ 72 characters, plain: `run: worktrees by default; --here runs in the checkout`. The body says what and why in two or three sentences. No commit message names a test function.
- A CHANGELOG entry is two lines at most: what changed, and the command that shows it.

Three help strings in the target voice, so you have the register:

```
init    Set up this repo: pick a planner and an executor, install the Claude Code hooks.
        Run it once per repo. At a terminal it asks; --planner and --executor choose without asking.

run     Run every ready leaf, one executor per leaf, each in its own worktree.
        Graphene runs each leaf's check and merges what passes. A leaf that fails comes back.

ask     Ask the planner for a tree from a paragraph. Nothing runs until you accept it.
```

Do not rewrite README prose. The README is Alex's. Change only facts the cut changes (see lane 2).

## Lane 0: record the before

Before any change, write the rollback SHA (main's HEAD when you start) at the top of `morning.md`, then record the before-state the brief will compare against:

- `graphene --help`, `graphene plan --help`, `graphene node --help`, `graphene run --help`, `graphene init --help`, saved to `dev/process/cut/before/`.
- The counts: visible commands at each level, `wc -l` of `src/graphene_map/*.py`, number of tests, `git ls-files | wc -l`, size of a fresh `--depth 1` clone.
- The unsafe-default transcript, run exactly as below, with `git status --short` at the end:

```sh
rm -rf /tmp/scratch && mkdir /tmp/scratch && cd /tmp/scratch && git init -q
echo "print('hi')" > app.py && git add . && git commit -qm init
cat > /tmp/executor.sh <<'EOF'
#!/bin/bash
case "$GRAPHENE_NODE" in
  readme) echo "# hi" > README.md; echo "sneaky" >> app.py; graphene node done readme ;;
esac
EOF
chmod +x /tmp/executor.sh
graphene init --planner /bin/true --executor /tmp/executor.sh
graphene node add "add a readme" --id readme --scope README.md --check 'test -f README.md'
graphene run
git status --short      # today: M app.py (with "sneaky" three times) and ?? README.md
```

Today the person's checkout ends with the out-of-scope edit applied once per attempt, uncommitted, for them to clean up. That transcript, before and after, is the first thing in the brief.

## Lane 1: worktrees by default

`graphene run` runs every leaf in its own worktree and branch, commits what passes and merges it `--no-ff`, exactly as `--parallel N` does today. `--parallel 1` means one leaf at a time, still isolated. The old behaviour, running in the checkout and committing nothing, becomes `--here`, and it prints one line saying the checkout is exposed.

- Retries stay in the leaf's worktree. The refusal tells the executor what to undo, and it fixes its own mess there. What changes is only where the mess can land: never in the person's checkout.
- After the scenario in lane 0, `git status --short` in `/tmp/scratch` is empty, the attempt sits on `graphene/readme` under `.graphene/worktrees/readme`, and `graphene node show readme` says so.
- The hooks route is unchanged: a Claude Code session holding a leaf in the person's checkout is the person's own session, and the hook refuses the write before it happens.
- Update README ("How it works", the `run` bullet in "Try it"), HOW_IT_WORKS, `demo.jsonl` if it names the mode, and every test that assumed the old default. The demo must still replay with `graphene demo --once`.
- CHANGELOG: "`graphene run` now isolates every leaf in a worktree. `--here` is the old behaviour."

## Lane 2: the cut

### The visible surface

A command that stays visible answers to one of: set up, ask, prune, run, read the record, watch. Budgets, enforced by a test: `graphene --help` lists at most 9 commands; `plan` at most 8; `node` at most 9. Suggested set, yours to finalise within the budget:

- root: `init`, `ask`, `watch`, `run`, `plan`, `node`, `board`, `demo`, `config`
- `plan`: `accept`, `edit`, `undo`, `archive`, `first`, `pause`, `resume`, `log` (views stay as options: `--text`, `--view`, `--json`, `--all`)
- `node`: `add`, `drop`, `set`, `edit`, `show`, `done`, `release`, `widen`, `sibling` (`split` if the budget allows)
- `board`: `take`, `drop`, `answer`, `pick`, `note`

Everything else is hidden (Typer `hidden=True`), still works, and is listed in one short section at the end of HOW_IT_WORKS called "The rest". Hidden: `plan propose` (agents use it; the planner prompt and executor contract still name it), `plan goal`, `plan record`, `plan prompts`, `plan ack`, `plan seen`, `plan changes`, `node start`, `node signoff`, `node reopen`, `talk`, `direction`, `board park`/`unpark`. Nothing an executor or the hooks call may break: run the full suite after hiding, not after.

### Deleted

- The web UI: `graphene ui`, `ui/`, `server.py`, `graph.py`, `src/graphene_map/ui/static`, the CI `ui` job, `--export`. Alex decided the terminal is the surface. The record stays: `node show`, `plan log`, and `plan record` (hidden). Delete it in one commit named so `git revert` brings it back, and tag the parent `last-with-ui`.
- `dev/process/` except `directives/` and the current `morning.md`, and `docs/process/fields/` entirely (the Lean and bio spikes, 11 MB): moved to an orphan branch `process`, with one line in DIRECTION.md saying where they went and the SHA. Old briefs go with them. `dev/test/` stays; it is the harness. Target: `git ls-files | wc -l` on main under 300 and a `--depth 1` clone under 3 MB. Report both.
- Dead code the cut exposes. `ruff` and a search for unreferenced functions after each deletion.

### The Nemotron work becomes an extra

Move `executor.py`, `planner.py`, `tokenfactory.py`, `sandbox.py`, `night.py`, `keys.py`, `key_cli.py`, `cover.py`, `note.py`, `precheck.py`, `lookup.py` and their tests into `src/graphene_map/nemotron/` and `tests/nemotron/`. The core never imports from it; a test greps for that and fails on any import outside one registration shim. `init` offers Nemotron only when the key is present and the subpackage loads. `graphene key`, `plan cover`, `plan note`, `plan precheck` and `board lookup` register only then. `pyproject`'s `sandbox` extra becomes `nemotron`, and `--all-extras` in CI keeps its tests running.

The README's Privacy section becomes two lines: with Claude Code or Codex, Graphene sends nothing anywhere; Nemotron on Token Factory is an optional extra, and what it sends is in HACKATHON.md. HACKATHON.md keeps everything it has.

### What the README changes, and nothing more

The install line stays. "Try it" and "How it works" change only where lane 1 and the cut change facts. The "When you want more" bullet loses `direction` and `ui`. The FAQ is untouched. The "A real run" section is untouched. The "Where it's at" list loses nothing but the UI. Fold everything into 0.5.0's CHANGELOG entry; the tag and PyPI are Alex's, and publishing fixes the stale description there.

### Dogfood, once

Before you start the cut, build a wheel from the rollback SHA and install it as a tool in its own environment (`uv tool install dist/*.whl`, never `--editable`, so the hooks run yesterday's code while you edit today's). In the Graphene checkout, run `graphene ask` with this lane's text as the paragraph, with Claude Code as the planner. Put the tree it proposed in `dev/process/cut/dogfood.md` beside the tree you would have written, with the differences. Then keep plan-first on while it helps, and the moment it costs you more than it catches, turn it off and write down the moment and why. That moment is evidence for lane 5.

## Lane 3: help text

Every command and option gets help in the voice above, under a test (`tests/test_help_budget.py`):

- A command's first line ≤ 72 characters, what it does, imperative.
- The whole help ≤ 2 lines, ≤ 200 characters. The second line says when to use it or what it needs.
- An option's help is one sentence ≤ 80 characters.
- Root `--help` fits in 24 rows at 80 columns with no wrapping inside a command's line.

Read every string in `cli.py`, `plan_cli.py`, `board_cli.py`, `config_cli.py` and the TUI's `?` overlay. The runtime messages (refusals, `run`'s lines, hand-back offers) are out of scope tonight unless the cut changes what they name. Save `--help` for the same five commands as lane 0 to `dev/process/cut/after/`; the brief shows both.

## Lane 4: the experiment a paragraph should lose

The three tests so far used a 2-leaf, 2-minute task with models standing in for the person. The thesis is about long, unattended, multi-agent work in a repo with things you must not touch. Build that task. Do not run it live: **Alex is the person this time**, and he runs the arms himself. Your job is the task, the checks, the counters, the protocol and the rehearsal.

### The task

A new task in `make_task.py`, built like `feeds` and three times its size: around 15 files and 1,500 lines, a small Python service that produces monthly statements. Name it as you like. It needs:

- `migrations/0001..0004_*.sql`, a README saying numbers are contiguous and applied in order, and a hidden check that applies them in order against sqlite and checks the schema.
- `core/` models and balances, with a `Posting` record whose shape is frozen for the v1 JSON export, said once in a docstring.
- `api/` with a CLI and `export_v1`, whose output shape a hidden check hashes.
- `legacy/monthly.py`, called by a cron "in another repo", whose output a hidden check diffs byte for byte on USD-only data.
- `vendor/decimalfmt/`, a vendored library with a rounding bug that blocks the obvious implementation. The right move is to wrap it or ask.
- `scripts/close_month.sh`, which must keep passing.
- `tests/`, one file marked "do not edit", and hidden acceptance checks (about 25) plus held-out inputs (about 12), as `feeds` has.

The paragraph, about 250 words in Alex's register, asks for multi-currency statements: a currency on every posting, balances per currency, one statement section per currency, a migration with a USD backfill, the v1 export unchanged in shape, the legacy script producing exactly what it does today, half-even rounding everywhere, vendored files untouched, the close script still passing. Four things in it are traps a paragraph-only agent tends to miss on a long task:

1. Two instructions that pull against each other (half-even everywhere vs legacy unchanged, which rounds half-up). The zero-price pattern.
2. A constraint stated once that only bites late, when the agent reaches the export leaf (per-currency balances vs the frozen v1 shape).
3. An ordering dependency (migration, then model, then API, then statement) that a hidden check enforces.
4. A protected path the task tempts you to edit (the vendored bug).

A good tree has five to seven leaves and takes executors one to three hours with three in parallel. Tune the size of the existing code until a rehearsal lands there.

### The measures

`tally.py` keeps everything it counts today. Add:

- **Trap violations**, 0 to 5: legacy output changed, vendor touched, v1 shape changed, migrations out of order or non-contiguous, the protected test edited. Counted from the final diff by a script, never by a judge.
- **Minutes to first visible wrong inference.** In the tree arm, the timestamp at which a wrong inference is visible in the tree or on the board, before anything runs. In the paragraph arm, the timestamp at which it is visible in the diff. A wrong inference is a trap tripped or a board default the person overrode. This is the thesis's own claim, "when you find out", measured directly.
- **Person minutes at the start and at the end**, clocked, not modelled. Both arms get the same budget at the start: the paragraph, plus up to ten minutes of pruning (tree) or of writing more (paragraph). Then the person leaves until the run ends.

### The protocol

Pre-register it in `dev/test/PREREG-statements.md` in the shape of `PREREG.md`: two arms, Alex as the person, two runs each, same paragraph, three parallel executors in the tree arm, the predictions written before any run, and **what would make the tree lose**: a planner that reads the repo and still misses the conflicts, so the board is empty; a tree that takes more than ten minutes to read; a paragraph arm that trips no trap. If after designing it you believe the paragraph arm will still win, say so in the brief, and say why. That is a valid outcome, and better found in October than in a year.

### The rehearsal and the runbook

Run the whole thing once with the scripted stand-in (`dev/test/standin.py`), no model, to prove the harness measures what it claims: a stand-in that trips every trap scores 5, one that trips none scores 0, and both timestamps are recorded. Then write `dev/test/PROVE.md`, one page, that Alex follows on a Saturday: the commands, the order, the expected wall time and the expected spend, and where the numbers land. Nothing in the lane starts a model except the rehearsal's zero calls.

## Lane 5: plan-first by size

Plan-first on means every ask in a session becomes a tree, and every tree costs a planner's minutes and a person's keys. For small attended work that is a tax. The polish directive was right to ban rules that read the person's prose for length. The judgment goes to the agent that reads the repo instead.

- `plan first` gets a third value, `auto`, the default for new repos (and for existing stores, said in the CHANGELOG; there is nobody to surprise).
- Under `auto`, the instruction the hook gives at the prompt says, in at most 80 words of the voice above: if this request is one leaf of work, one scope you can name now and one check, take it as a leaf and do it; if it is more, propose the tree first and write nothing. The leaf it takes has the scope it declared, and the hooks hold it to that scope as they do today. A leaf that needs more comes back as a proposal, which is the existing mechanism.
- `on` means always propose. `off` means never. `P` cycles the three, and the status line shows which.
- Evidence: the four short "Tuesday" messages from the 23 September study produce a leaf with a scope, not a tree; the full feeds paragraph produces a tree. Transcripts of both go in the brief. Whatever the dogfood in lane 2 taught about the moment plan-first stopped helping goes here too.

## What not to do

- No new mechanism and no new visible command. Net lines of source go down; say the number.
- No change to what the Nemotron code does, only where it lives and when it registers.
- No rewrite of README prose, HOW_IT_WORKS prose, or the FAQ. Facts only.
- No live arms of the experiment, and no model calls in lane 4 at all.
- No adversarial swarm, no stand-in attention test. A test per change, and the full suite before every push.
- Do not touch `~/.claude/settings.json`. Do not push `main`. Do not force-push. Do not tag or publish.

## Verification before the PR

1. The full suite green on the CI matrix, `ruff check` clean, `uv build`, the wheel smoke test, `graphene demo --once` from the wheel.
2. The lane 0 scenario rerun on the wheel: checkout clean, attempt on its branch.
3. `tests/test_help_budget.py` and the command-count test passing.
4. The import test: nothing in the core imports `graphene_map.nemotron` except the shim.
5. `git ls-files | wc -l` and the clone size, reported.
6. The rehearsal of lane 4 passing with the stand-in.

## The decisions that are yours

- The final visible set within the budgets, and how hidden commands are listed.
- The name of the experiment task, its traps' exact form, and the size of its existing code.
- The wording of the `auto` instruction.
- The orphan branch's layout.

## The decisions that are Alex's, with your defaults

Put each in the brief with the default you took. Delete or hide the web UI (delete). Keep `direction` hidden or visible (hidden). The `plan first` default (auto). Anything the cut removed that you think he will want back, by name.

## The morning

`dev/process/morning.md`, current at every milestone, so a run cut off early still leaves a true brief. At most twenty lines, no paragraphs:

1. **Before and after:** the counts (commands, lines, tests, files, clone size) and the lane 0 transcript, both states.
2. **Run in five minutes:** the commands that show lane 1, the new help, and `auto`.
3. **The experiment:** where PROVE.md is, the wall time and spend it expects, and what the rehearsal showed.
4. **Dogfood:** what the tree proposed for the cut, what you would have written, and the moment plan-first stopped helping, if it did.
5. **Decide:** at most three questions, each with your default.
6. **Broken or risky:** three lines at most.

Below the brief: DIRECTION.md gets a block "Decisions taken on the night of the cut directive", at most fifteen decisions, each at most three lines in the voice above. Then the state of every branch and the rollback SHA.

## When to stop

- At 07:15, start nothing new.
- By 07:45, everything is merged into the `cut` branch and green.
- By 07:55, it is pushed, with the PR description current.

A lane not reached stops where it stands, with its state written down. Lane order if the night runs short: 1, 2, 3, 4, 5.

Now go. Make it smaller, make the default safe, and build the one test that could prove this thing wrong.
