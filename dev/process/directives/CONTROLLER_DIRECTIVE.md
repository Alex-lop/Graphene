# Graphene: the controller directive

*For the agent that runs on this repo next. Written 14 October 2026 by the session Alex opened after the direction run. Its inputs: the previous agent's handoff (it arrived cut off mid-sentence, after "the hook refuses before the"; what survived is two rules, one orchestrating session per checkout and reviews sized to quota), thirteen read-only readers (controller gaps, the diff, CI and hygiene, the market, a stranger's first ten minutes from PyPI, the launch kit, a crash test, a bench) and a README tournament (four drafts, six cold persona readers, a fact-check, a cold re-read). Every reader is a stand-in for a person, not a person; each number below says where it came from. Alex has read this and hands it over. The working rules of the earlier directives hold except where this one says otherwise.*

---

## What kind of run this is

Alex's aim, in their words: Graphene should be the controller people reach for when they hand work to coding agents, and everyone should know it; the README should be short and for people who are not all engineers; and the agent that gets there should be relentless.

Five findings set the order. None was in the last handoff.

1. **The published wheel is not the product.** PyPI's `graphene-map 0.5.0` was uploaded on 13 October from the `v0.5.0` tag, which is the commit of 7 October (`a96fb48`), 184 commits behind `main`. A stranger who follows the README gets no `init --remove`, no `node diff`, no spend cap, no timeline view, none of the feel pass's words (checked on 14 October with `uvx --isolated`; plain `uvx` on Alex's machine resolves to the tool installed from git and hides this). Nothing below is seen by anyone until 0.5.1 is on PyPI. `first-things` prepares it; the tag is Alex's.
2. **"See the plan first" is no longer what is different.** Plan approval ships in Claude Code, Cursor, Kiro, Cline and Spec Kit (141,309 stars on 14 October). What the market scan could not refute, scoped to Claude Code: a plan where every piece names the files it may change and the check it must pass, a write outside those files refused as it happens, the check run by the tool in a clean copy, and a piece landed only when it passes, on your machine with no account. The words people use for the problem are "Claude modified files I didn't ask it to modify" (the first option on Anthropic's own bug form) and "reports ALL PASSED when tests are FAILING". Say "the only" nowhere: a per-task file limit with checks exists for the Pi agent (my-pi) and a static write lock for nine agents (Ralon).
3. **The controller is not complete, and a stranger finds that out in ten minutes.** There is no `graphene stop`; no cap on a whole run, and Codex has no cap at all; `--signoff` merges the leaf into your branch before it asks you; nothing says how to take a landed leaf back; `plan pause` lifts the rules and does not stop the agents. Two holes under them: the refusing hook fails open (Claude Code 2.1.295 can make it fail closed), and a leaf that may edit the test its own check runs can weaken it and `done` accepts it without a flag.
4. **It has never been shown.** Everything the crash test needs exists as parts. The screen is designed: 25 lines, six moves refused, one flagged, one honest sentence on what a script does not prove.
5. **No stranger has been timed**, and the only way to get that number is to make it easy for strangers to send it.

Be relentless about finishing and verifying. Be stingy about adding: one new flag (`--cheat`, with `run --stop`), no new top-level command, and every line of the README earned.

## How to work

- **One orchestrating session per checkout.** At the start and after every merge: `ListAgents`, `git reflog -5`, `graphene plan`, `gh run list -L 3`. A second live copy of the session means stop and tell Alex; it cost a night on 11 October. Lanes and fixers get a clone with no `origin`: the push and any PR stay the orchestrator's, and there is no push in this directive at all.
- **Everything goes through leaves.** Plan first auto holds you: propose, `graphene node start <id>`, do it, run its check, `graphene node done <id>`, commit as Alex (the repository's own git identity) with the Co-Authored-By trailer, one commit a change, at most 50 commits a run. The gate's grammar, learned on 13 and 14 October: a scope is split at spaces, so keep such files out; a directory needs a path under it (`dir/**`); `node done` wants a change inside the scope in the current hold; the Stop hook blocks the end of a session that holds a leaf; **two live leaves never share a path, `needs:` or not**, so a file wanted twice is wanted in turn; a checkout with an uncommitted change no node made refuses `node start`, and the refusal says to put it back, which the gate then refuses because no leaf is held (a read-only reader left a zero-byte `uv-….lock` at the root and held up the first leaf until Alex removed it: give readers a scratch `TMPDIR` and `UV_CACHE_DIR`; the deadlock is a finding, `put-it-back` below); a command that names the store's directory is refused whole; `timeout` is not on macOS; use Python heredocs for text work and `set -o pipefail` in zsh. Dry-run a proposal first: `git clone --local`, remove `origin`, and run `graphene plan propose -` there.
- **Relentless means never idle, never silent, never stuck.** When a leaf blocks: read the refusal and make the smallest fix once; then split it (propose its children under it) or release it with `--why`; then take the next ready leaf (`graphene plan`). When nothing is ready: write the test a landed leaf lacks, read your own diff at its seams (one skeptic call per seam, not one agent per finding), keep the brief true. Stop only for the clock (stop starting leaves seven hours in or at 07:00 local, then the closing sequence), the quota (the first 429, and no new lane past what Alex's plan can bear), a red you made, an outward-facing act (these are commands for Alex in `dev/process/morning.md`), or an empty queue.
- **Quota.** The session's model is the one Alex set with `/model` (Sonnet 5.5 on 14 October); subagents inherit it. Cap findings at eight a reader, argue them in one skeptic call per seam, never an agent per finding per lens. A cut-off agent is resumed with `SendMessage`, not relaunched. The 96-agent review of 12 October cost 12.5M tokens and hit the weekly limit; the two workflows of 14 October (13 and 18 agents) cost 1.1M tokens each.
- **Evidence.** Red first for every leaf (its check fails on the base). Before and after numbers on the same scripts. A stand-in is labelled a stand-in. No `NOT PROVEN` label flips without machine evidence in the same commit. A decision that is Alex's goes in the commit message and the brief with how to undo it in one commit.
- **Never:** push, tag, publish to PyPI, edit GitHub settings, close a PR, delete a branch, touch `~/.claude/settings.json`, spend Nebius money, run `uv tool install` onto Alex's PATH (give each build its own `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR`), or write inside the plan's store by name.

## The queue

Graphene refuses two live leaves that write one path, `needs:` or not (run `graphene plan propose` on a tree that breaks it and it names the pair). Three files (`plan_cli.py`, `tui.py`, `plan.py`) are wanted by half the work, so the queue is waves: wave 1 is in the plan with disjoint scopes and may run three at a time; each later leaf is proposed when the leaf holding its files is done. Waves are an order, not a clock.

| wave | leaf | what it does | files it holds | needs | what proves it |
|---|---|---|---|---|---|
| 0 | `first-things` | main green on Linux; the README for everyone; 0.5.1 prepared (version, changelog split at the tag); this directive | `tests/test_demo.py`, `README.md`, `tests/test_tui.py`, version files, `CHANGELOG.md` | | its own check; done in the session that wrote this file |
| 1 | `packaging-and-ci` | the suite in parallel (xdist; an autouse fixture clears COLUMNS and LINES), one CI run per change, PyPI in plain words, a `graphene-map` entry point so `uvx graphene-map demo` works | `pyproject.toml`, `uv.lock`, `tests/conftest.py`, `ci.yml` | | `-n 4` passes the two files that failed under it; the CI time is in the commit |
| 1 | `account-honest` | the run's account says what its evidence says, moves under `dev/process/`, and the stray lock goes | `WHAT_THIS_RUN_DID.md` | | no "37 products", no "8 readers" |
| 1 | `market-table` | the market table follows October | `dev/PRODUCT_THESIS.md` | | four names are in it |
| 1 | `done-says-more` | a leaf marked for sign-off waits on its own branch until you sign it off; a changed test the leaf's own check runs is flagged; `node show` says how to take a landed leaf back | `run.py`, `plan.py`, `node_record.py` | | two new tests; HEAD unchanged until `y` |
| 1 | `cheat-demo` | `graphene demo --cheat`: seven moves, the real gate, $0 | `cheat.py`, `plan_cli.py` | `done-says-more` | its test, and the same test fails when the gate is stubbed to allow everything |
| 1 | `diff-in-watch` | `c` shows the whole diff, in colour, before and after it lands; help names `:stop` | `tui.py`, `tests/test_tui.py` | | the six test ids in its contract |
| 1 | `pictures` | `watch.gif` and `meter.svg` re-shot from a committed `vhs` tape | `docs/assets/` | `diff-in-watch` | the tape exists, the GIF is under 1.5 MB |
| 1 | `community` | SECURITY, CONTRIBUTING, a bug form, and the first-hour form: how strangers send the one number nobody has | `.github/`, root files | | files exist; the form has six questions |
| 1 | `bench-tasks`, `bench-scripted` | four tasks that tempt, the rule written first, scripted agents that prove the scorers; $0 | `dev/held/` | | `uv run pytest dev/held` |
| 2 | `unattended` | `graphene run --stop`; the first line says the worst case or "no cap"; `plan pause` stops a live run or says what it does; a bell when a leaf needs you | `plan_cli.py` | `cheat-demo` done | a new test |
| 2 | `free-path-words` | bare `graphene` says `init` first and exits 0; "every leaf is done"; the replay's bill under "no model ran" says it is a stand-in's | `plan_cli.py`, `cli.py` | `unattended` done | the pinned tests move with their words, one new test |
| 2 | `put-it-back` | the start refusal and the gate agree: a session may remove an untracked file its own record shows it made, with no leaf held; or the refusal stops telling it to | `gate.py`, `hooks.py` | | a new test: a session that made a stray file removes it and starts a leaf |
| 2 | `launch-kit` | pitch lines, a first comment, a 90-second shot list, the hard questions answered; drafts for Alex to post | `dev/launch/` | `cheat-demo`, `diff-in-watch` done | no banned claim |
| 3 | `follow-docs` | CHANGELOG, the reference, the README lines the new features earned (the cheat demo, the picture, the first-hour form, "approving a diff before it lands" once it is true), the brief | `CHANGELOG.md`, `docs/HOW_IT_WORKS.md`, `README.md` | everything above | the two doc test files |
| 3 | `release-prep` | 0.5.2: version, dated heading, plain release notes; the tag is Alex's | `pyproject.toml`, `CHANGELOG.md` | `follow-docs`, `packaging-and-ci` done | tomllib; the heading |

On the board, both with a default: whether to run the live bench (about $30 of Claude at list price, 72 runs on Sonnet, held against plain Claude Code with the same rule as a deny setting; the scripted layer is $0), and whether the refusing hook should fail closed where Claude Code supports it (an answer adds a leaf under `proof` or `holds`).

## Gates

- Before each commit: the leaf's check, `uv run ruff check`, and the test files the change touched. Before the last commit of a run: the whole suite once (`uv run pytest -q -n auto` after `packaging-and-ci`; about 18 minutes serial before).
- CI is the judge of Linux: this run began with main red on ubuntu for one test that assumed the machine's temp directory was not `/tmp`. After Alex pushes, `gh run watch` until all six jobs are green, and fix what is red first.
- The README is held to its tournament: at most 420 words outside `<details>` and code (386 on 14 October, against 564 for the page before), every command in it was run, every image an absolute URL (PyPI does not serve relative paths), and a cold re-read by six personas understands it at least as well as that one did (mean 7.2 of 10, five "maybe" and one "yes", against 4.9 and no "yes" for the old page read blind beside the drafts).

## For Alex, not for the agent

Commands, in the order that makes sense. None is run by an agent.

1. `git push origin main` (after reading the commits; every commit is authored as you), then `git tag v0.5.1 && git push origin v0.5.1`. The Release workflow builds, smokes the wheel and publishes (`docs/RELEASING.md`). Check what a stranger gets: `uvx --isolated --from graphene-map graphene init --help | grep remove`. Then `uv tool install --force graphene-map` replaces the build on your PATH.
2. `gh release edit v0.5.0 --title "Graphene 0.5.0" --notes "The meter and what came before it; see 0.5.1 for the rest."` and a release for v0.5.1 from the plain notes.
3. Close as superseded or evidence-only, with a one-line comment: #32, #35, #41, #42; #13 to #22 (check #12's LICENSE line first); merge or close #25 (imgbot) after `pictures` lands. Closing a PR keeps its branch, and the `*-before-fold`, `*-full-history`, `timeline-before-shape` and `main-before-reshape` branches hold SHAs the evidence cites: do not delete them.
4. `gh repo edit --description "A shared plan for you and your coding agents. Claude Code hooks keep them to it."`
5. `graphene plan archive`, then `graphene plan goal "…"` in your words: the plan's goal still describes the direction run.
6. Post nothing before: 0.5.1 is on PyPI and the README's commands work from it, `graphene demo --cheat` has landed, and three strangers' first hours have come back through the form with no blocker.

## What is Alex's to decide

The README's "Why I built this" paragraph, shortened by deleting words and sentences, never rewording, and now inside a fold (restore it from git if you want it whole and visible); the headline, which says the agent "stays inside" the files and not "changes only" them, because with Codex the stray write happens and is only caught when the leaf finishes; whether `--signoff` waiting is the default (the flag's name and the pane already say it); whether the hook fails closed; whether the live bench runs and what it costs; whether `graphene demo --cheat` exits 1 when a move gets through; and every rewritten sentence, which is a draft in your voice.
