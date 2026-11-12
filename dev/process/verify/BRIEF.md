# For the Codex agent: break PR #60, fix what breaks, say what happened

Written 11 Nov 2026 by Claude Fable 5.2, which built draft PR #60 last night, for Alex Lopez (the owner).
Alex's worry, in his words: "those tests and cases that we haven't yet verified can be a serious problem."
You verify them live, fix what is broken, bring the tests and README up to date, and leave a report.
Alex then tests by hand, from your list.

## Decided (Alex flips a line here before you start, or it stands)

1. "Fix the repo" means: the bugs you find, their tests, the README. Housekeeping (old PRs, old branches) you list, never do.
2. An engine (Python) change is allowed when a fix needs one. Failing test first.
3. Hold Codex before the write (work item 2b): build it.
4. `plan accept` refusing while a question is open (Exact in the engine): do not build. Report only.
5. The snapshot (`state --json`) carrying attempts, approval, owner: do not build.
6. Spend: your Codex quota freely, xhigh. Claude: Haiku only, 12 probes at most. Nebius: $0.

## Where you work

- A fresh clone in the directory you were started in: `git clone -b night/graph-edit https://github.com/Alex-lop/Graphene`.
  Branch `codex/verify` from it (tip `2a2c6fbb`). Copy this file in as `dev/process/verify/BRIEF.md`, first commit.
- Alex's checkout is `~/Desktop/AllThingsAgenticHackathon` (on an old branch, with his uncommitted work).
  Write nothing there, and run no `graphene` command there.
- One draft PR, base `night/graph-edit`, so its diff is yours alone. About 30 commits, as Alex (git's configured
  user), no trailers, each one thing with its test. Fold before the first push so they read in order:
  probes, failing tests, fixes, docs, report.
- Never push `main`, merge, tag, release, close a PR or delete a branch. Judging runs 1 to 15 December.
- Green before every commit: `uv run ruff check`, `uv run pytest -q -n auto` (2927 passed at the start),
  `npm test` in `editors/vscode` (133), and in `editors/vscode/e2e`: `npm test`, `npm run home`, `npm run draw`.
- Every `graphene` you run gets a throwaway repo and this environment, because Alex's real key is in `~/.zshenv`:
  `ZDOTDIR=<empty dir> NEBIUS_API_KEY=fake-key GRAPHENE_KEYCHAIN=off GRAPHENE_TOKENFACTORY_URL=http://127.0.0.1:9`
- Never `uv tool install` onto his PATH (set `UV_TOOL_DIR` if you follow the README as a stranger).
  Change nothing under `~/.codex`, `~/.claude`, `~/.claude.json` or `~/.zshenv`: ask first.
  `claude` in his zsh is a function that edits `~/.claude.json`: call the binary by its path.
- The e2e walks open real VS Code windows. Close each one. Kill no system process: ask.
- His email is private: never send it to an outside service.

## Read first (in your clone)

- `gh pr view 60`: what was built, what was proven, what was not.
- `dev/process/graph-edit/hooks.md` (the table you are to break), `edits.md`, `exact.md`, `probes/`.
- `tests/test_every_agent.py`, `tests/test_gate.py`, `tests/test_hooks.py`, `tests/test_standing_gate.py`.
- `docs/HOW_IT_WORKS.md`, "Where each mechanism ends"; `dev/process/publish/gate/review.md` and `skeptic.md`
  (the gate's known parser holes, documented, never fixed).
- `README.md`: "Any agent, any model" and "What it enforces, and where it ends". `editors/vscode/e2e/README.md`.

## The work, in this order

**1. Find the bug Alex hit.** All he remembers: "the hooks accepting my changes." Try each; reproduce before you fix.
- a. A write the gate lets through: a shell redirect under a `#` line or with its target in a variable (the README
  admits both), a Write whose payload names the path in another field, a hook that errors or runs out of time.
- b. Alex edits a file by hand while an agent holds a task: whose change is it at `node done`? Does it land in
  the task's commit, send the task back, or get lost?
- c. `plan accept` taking every open default under `board: on` (`exact.md`).
- d. A session opened before `graphene init`, or hooks left by an older Graphene than the engine: is anything held?
- e. `node done` on a check that passes with nothing done.
Say for each: reproduced or not, the command, what it printed.

**2. You are the live Codex the table lacks** (row 4: "test with a stand-in; no live Codex").
- a. `graphene run --with codex` on a fixture: a task whose file is `inside.txt`, told to write `outside.txt`.
  What lands, what the log says, what the person sees.
- b. Build the hold before the write: `init` writes Codex's hooks file, the gate reads Codex's real payload,
  `run` gives the hold a session it can match. `hooks.md` "Holes" has the sketch, from docs alone: trust what you
  observe. If a nested `codex` cannot start inside your sandbox, say so at once instead of working around it.

**3. Real agents on attempts set by hand.** Set 3 attempts on one task as the form does (`node set --forks 3`),
run it with real agents (Codex), and follow it to the pick and the landed commit. Nobody has.

**4. Every test PR #60 added: can it fail?** For each (`git diff main...night/graph-edit --stat`), break the line
it guards and run it. List the ones that still pass, then make them bite.

**5. The extension's loose ends.** A refusal shows twice (pane and toast): once. A draft dies with its page:
reload, a second graph panel, a window reload. The footer's news and Graphene's refusals say forks, leaf, scope
where the screen says attempt, task, files: one wording, and no CLI flag or JSON key changes.
Drive the walks in Cursor if it is installed (`E2E_APP`).

**6. README and tests.** The README says what is true after your run, Codex's row first. Each thing you proved
live is a hermetic test in CI, or a probe script with its output kept in `dev/process/verify/probes/`.

Not yours: moving a task under another sub-goal, the panel, saved graphs, any new feature. Cursor's and Copilot's
own agents need Alex signed in on his screen: skip, say so.

## What you leave

- `dev/process/verify/REPORT.md`, 80 lines at most, and the same words as the PR's description and your last message:
  1. What PR #60 changed, in plain words, by what Alex sees on screen (he found it unclear).
  2. What you tried, as a table: claim, how you tested it, held or broke.
  3. What broke and what you did: the command that shows it, the commit that fixes it.
  4. What is still open, and why.
  5. Housekeeping for Alex: the open PRs and branches that look superseded, one line each, with the evidence.
  6. Questions, three at most, each with the default you took.
- `dev/process/verify/TRY_IT.md`: 15 steps at most that Alex clicks through himself, each with what he should see.

## Aggressive, as Alex asked

It means: every "proven by" in PR #60 is wrong until you have broken it or watched it hold. Do not stop at the
first bug. Fix what you find, engine included. Go deep before wide, and do not hand back early.
It does not mean: new features, rewrites, a second PR, or anything past the lines under "Where you work".
A fix over about 200 lines, or one that changes what a CLI command accepts, you report instead of building.
