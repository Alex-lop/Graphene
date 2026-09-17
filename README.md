# Graphene

![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=rebuild)

I run Claude Code on a repo, come back hours later or the next morning, and can't account for the
changes. The diff doesn't tell me which request produced which change, what the agent touched that I
never asked for, or what it tried and then abandoned. Graphene answers those three questions from the
agent's own records, grouped by what I asked for, and lets me ask "why is this line here?" weeks later.

## Install

```
uv tool install git+https://github.com/Alex-lop/Graphene@rebuild
```

Python 3.13 (uv fetches it if needed). Claude Code on your PATH is optional: with it, Graphene can ask
it for one explanation sentence per changed file; without it, the sentences are factual templates.

## Use

### `graphene init`, once per repo

Run it inside the repo. It adds one hook to the repo's `.claude/settings.json`, keeping whatever is
already there, so Claude Code reports every session start, prompt, tool call and turn end to a local
SQLite file under `.graphene/` (added to `.gitignore` when missing).

```
$ graphene init
hooks added to .claude/settings.json: SessionStart, UserPromptSubmit, PostToolUse, PostToolUseFailure, Stop
```

Sessions that ran before the hook existed can be loaded from Claude Code's own transcripts:

```
$ graphene ingest --backfill
added 25, refreshed 0, already present 1, other repos 2
  0d1ef43a-3794-4277-aee3-760d5933f148
  155c08d3-13e5-483b-ade0-9d85f92dcc98
  …
```

### `graphene debrief`, when you come back

```
$ graphene debrief
```

With no arguments it covers everything since the last debrief, or the latest session. `graphene debrief
SESSION_ID` (a prefix is enough), `--since 6h`, `--since 2026-09-16`, `--json`, `--md FILE` and
`--full` also work; `--explain none` skips the model. Below is the debrief of the session that built
Graphene, with lines left out where marked. The sentence after each dash came from one `claude -p`
call for the whole prompt; the `[unrequested]` flag means the prompt text named neither the file nor
its directory, which flags a lot when the prompt only names a directive.

```
# Graphene debrief

**Sessions:** 1 (9982bcf7) 2026-09-17 01:43 → 2026-09-17 05:54
**Wall time:** 4h 10m · **Prompts:** 1 · **Files changed:** 23 (+3350/−191)
**Commits during the sessions:** 6
- e33780e why: `graphene why PATH` and `graphene why PATH:LINE`
- 655b35a debrief, explain: `graphene debrief` with template or claude explanations
…

## What you asked, and what happened

### 1. 2026-09-17 04:53
> Please implement : REBUILD_DIRECTIVE.md to the best of your abilites. You are the smartest and most capable agent so I really need you to belive in yourself the way I belive in you and your abilities

- `.github/workflows/ci.yml` modified +8/−154 **[unrequested]** — Replaces the old multi-job pipeline (installed-artifact proof, macOS sandbox, Linux fail-closed and CLI smoke jobs) with a single job that sets up uv and runs the tests on every push and pull request.
- `pyproject.toml` created +38/−0 **[unrequested]** — Defines the new `graphene-debrief` package, built with hatchling for Python 3.13 or later, with Typer and Rich as dependencies, a `graphene` console script, pytest and ruff for development, and ruff and pytest settings.
- `tests/test_hooks.py` created +238/−0 **[unrequested]** — Tests live hook ingestion for each event type, that the hook never fails, and that installing hooks and adding `.graphene/` to `.gitignore` both work.
…

## Tried and abandoned

- failed Edit: `src/graphene_debrief/sources/claude_code.py` (prompt 1) — Error: String to replace not found in file.
- check `uv run pytest -q 2>&1` failed under prompt 1, rerun under prompt 1: passed
…

Run `graphene why <path>` for one file's history, or `graphene why <path>:<line>` for one line.
```

### `graphene why`, for one file or one line, across sessions

```
$ graphene why src/graphene_debrief/store.py
src/graphene_debrief/store.py  1 prompt(s), newest first

2026-09-17 04:53  session 9982bcf7  prompt 1  created +281/−0
  > Please implement : REBUILD_DIRECTIVE.md to the best of your abilites. You are the smartest and most
capable agent so I really need you to belive in yourself the way I belive in you and your abilities
  Implements the SQLite store at `.graphene/graphene.db` in WAL mode with a busy timeout, with tables for
sessions, prompts, tool events, explanations and debrief runs, and caps on stored response and content size.
```

```
$ graphene why src/graphene_debrief/store.py:12
src/graphene_debrief/store.py:12  CONTENT_CAP = 2 * 1024 * 1024
committed in 5c03283 (2026-09-17 05:39) · exactly one recorded edit added this line

2026-09-17 04:53  session 9982bcf7  prompt 1  created +281/−0
  > Please implement : REBUILD_DIRECTIVE.md to the best of your abilites. You are the smartest and most
capable agent so I really need you to belive in yourself the way I belive in you and your abilities
  Implements the SQLite store at `.graphene/graphene.db` in WAL mode with a busy timeout, with tables for
sessions, prompts, tool events, explanations and debrief runs, and caps on stored response and content size.
```

## What it doesn't do

- It does not run agents.
- It does not orchestrate anything.
- It does not push, commit, or touch your git history.
- It does not phone home: nothing leaves your machine except the optional `claude -p` call your own Claude Code makes.

## How it works

A hook installed by `graphene init` records each prompt and tool call as Claude Code makes them, and
`graphene ingest --backfill` reads Claude Code's transcript files for sessions that ran without the
hook. Every tool call is grouped under the prompt whose turn it happened in. For `Edit` and `Write`
calls Claude Code's payload carries the file before and after, so the diff per prompt and file is
computed directly; for files a shell command wrote, the session's git diff is credited to the last
prompt that touched them. A file is "unrequested" when the prompt names neither it nor its directory;
"abandoned" covers files restored to their session-start content, failed calls, and test or lint
commands that failed and were rerun. The only model involvement is the optional one-sentence
explanation per file, written from that diff and stored so it is never asked twice. The heuristics and
their failure modes are spelled out in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).
