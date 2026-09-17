# Graphene

![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=rebuild)

I run Claude Code on a repo, come back hours later or the next morning, and can't account for the
changes. The diff doesn't tell me which request produced which change, what the agent touched that I
never asked for, or what it tried and then abandoned. Graphene answers "why is this line here?" from
the agent's own records, across sessions, and gives me a short card of what happened when I come back.

## Install

```
uv tool install git+https://github.com/Alex-lop/Graphene@rebuild
```

Python 3.13 (uv fetches it if needed). Nothing else is required: Graphene reads the transcripts
Claude Code already keeps on your machine.

## Use

Run Claude Code on the repo as you normally do. When you come back, inside the repo:

```
$ graphene
```

The first time, Graphene reads Claude Code's transcripts for the repo (26 sessions here, about two
seconds), then prints a card for the latest session, or for everything since you last looked. This is
the card for the session that built Graphene, with lines left out where marked:

```
# Graphene

**Session 9982bcf7** · 2026-09-17 01:43 → 2026-09-17 13:58 · 12h 15m · 2 prompts · 25 files (+5101/−386)
**Commits during the session:** 22
- 9abff1e cli, debrief: a short card by default, why first, templates by default, self-backfilling store
- 0f94ca0 attribute: flag a file as unrequested only when a named scope excludes it
…

**Files changed**
- `src/graphene_debrief/debrief.py` created +559/−0
- `tests/test_attribute.py` created +519/−0
- `src/graphene_debrief/cli.py` created +388/−111
- `.github/workflows/ci.yml` modified +8/−154
…

**Abandoned**
- check `uv run pytest -q 2>&1` failed under prompt 1, rerun under prompt 2: passed
- 66 tool failures (58 Bash, 5 StructuredOutput, 2 Write, 1 Edit; 14 refused before running); `graphene debrief --full` lists them

Ask `graphene why <path>` for who changed a file and why, or `graphene why <path>:<line>` for one line.
```

A section appears only when there is something in it: files the agent changed outside the scope the
prompt named, files it put back to how they were, checks that failed and were rerun.

### `graphene why`, the question the diff cannot answer

Which prompts changed this file, newest first, and which one wrote this line:

```
$ graphene why src/graphene_debrief/why.py
src/graphene_debrief/why.py  1 prompt(s), newest first

2026-09-17 04:53  session 9982bcf7  prompt 1  created +138/−0
  > Please implement : REBUILD_DIRECTIVE.md to the best of your abilites. You are the smartest and most
capable agent so I really need you to belive in yourself the way I belive in you and your abilities
  Adds intent-blame: `why_path` lists every prompt that changed a file, newest first, and `why_line` uses git
blame and recorded edits to find the prompt that wrote a specific line.
```

```
$ graphene why src/graphene_debrief/why.py:1
src/graphene_debrief/why.py:1  """Intent-blame: which prompts changed a file, and which one last wrote a given
line."""
committed in 655b35a (2026-09-17 05:51) · exactly one recorded edit added this line

2026-09-17 04:53  session 9982bcf7  prompt 1  created +138/−0
  > Please implement : REBUILD_DIRECTIVE.md to the best of your abilites. You are the smartest and most
capable agent so I really need you to belive in yourself the way I belive in you and your abilities
  Adds intent-blame: `why_path` lists every prompt that changed a file, newest first, and `why_line` uses git
blame and recorded edits to find the prompt that wrote a specific line.
```

The sentence under each prompt is a factual template built from the diff, or, if you once ran
`graphene debrief --explain claude`, the sentence Claude Code wrote for that file (stored, never asked
twice).

### When you want more

- `graphene debrief --full`: the whole reconstruction, prompt by prompt, every file with a sentence,
  every failure (refusals grouped by reason). `--json` is the structure behind it. `--md FILE` writes
  either view to a file.
- `graphene debrief --explain claude`: one `claude -p` call per prompt writes the per-file sentences.
  Off by default.
- `graphene debrief SESSION_ID`, `graphene debrief --since 6h`, `graphene sessions`.
- `graphene init`: installs hooks in the repo's `.claude/settings.json` so sessions are recorded live
  (exact prompt boundaries and the git HEAD each session started from). Optional; without it Graphene
  keeps reading the transcripts.

## What it doesn't do

- It does not run agents.
- It does not orchestrate anything.
- It does not push, commit, or touch your git history.
- It does not phone home: nothing leaves your machine except the optional `claude -p` call your own Claude Code makes.

## How it works

Graphene reads Claude Code's transcript files for the repo (or the events its hook recorded live) and
groups every tool call under the prompt whose turn it happened in. For `Edit` and `Write` calls Claude
Code's payload carries the file before and after, so the diff per prompt and file is computed directly;
a shell write in between is recovered from the next call's before-image, and only the edges of a file's
history fall back to git. A file is flagged as not asked for only when the prompt named a file scope,
such as `auth.py` or `src/app/`, that does not cover it or one of its companions (its test, its package,
its directory); a prompt that names no file flags nothing. "Abandoned" means files restored to their
session-start content and test or lint commands that failed and were rerun; other failed calls are a
count. The only model involvement is the optional one-sentence explanation per file. The heuristics and
their failure modes are spelled out in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).
