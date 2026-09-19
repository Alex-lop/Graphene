# Graphene

![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)

Why did my coding agent change this line? Graphene answers that from Claude Code's own records,
across sessions, and prints a short card of what happened when you come back to a repo.

I run Claude Code on a repo, come back hours later or the next morning, and can't account for the
changes. The diff doesn't tell me which request produced which change, what the agent touched that I
never asked for, or what it tried and then abandoned. Graphene does.

![The card: what one session changed](docs/assets/card.svg)

## Install

Once the package is on PyPI (not yet: see the line below for today):

```
uv tool install graphene-map
```

Today, from GitHub:

```
uv tool install git+https://github.com/Alex-lop/Graphene
```

## Use

Run Claude Code on the repo as you normally do. When you come back, inside the repo:

```
graphene
```

Graphene reads the transcripts Claude Code keeps for the repo (the first time takes a couple of
seconds; after that only what changed) and prints the card: the latest session, or every session
that ended since the last time you ran it. In a repo where Claude Code has not run yet it says so,
and where it looked.

```
graphene why src/app/auth.py
```

Which prompts changed this file, newest first, each with what it did to the file.

![graphene why PATH](docs/assets/why-path.svg)

```
graphene why src/app/auth.py:42
```

Which prompt wrote this line.

![graphene why PATH:LINE](docs/assets/why-line.svg)

When you want more: `graphene --json` is the structure behind the card; `graphene debrief --html
FILE` writes a self-contained page, a timeline of prompts and files that opens offline and is safe
to send to a teammate. `graphene --since 6h` covers a window, `graphene --session ID` one session,
and `graphene sessions` lists what is recorded.
`graphene init` installs hooks in the repo's `.claude/settings.local.json` (yours, not the team's
`settings.json`) so sessions are recorded live, with exact prompt boundaries and the commit each
session started from; without it Graphene keeps reading the transcripts.

## How it works

Graphene reads Claude Code's transcript files for the repo, or the events its hook recorded live,
and groups every tool call under the prompt whose turn it ran in. Claude Code's own payloads carry
the file before and after each edit, so the diff per prompt and file is computed directly; only a
file's first or last state in a session, when a shell command wrote it, is read from git. A file is
flagged as not asked for only when the prompt named a path (`auth.py`, `src/app/`) that does not
cover it; a prompt that names no path flags nothing.
"Abandoned" means files restored to their session-start content and checks that failed and were
rerun. No model is involved at any point. The heuristics and their failure modes are spelled out in
[docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## What it doesn't do

- It does not run agents.
- It does not orchestrate anything.
- It does not push, commit, or touch your git history.
- It does not phone home: nothing leaves your machine, and it calls no model.

## Privacy

- The store is `.graphene/` inside the repo: local, created `0700`, and it ignores itself in git
  (a `.gitignore` inside it), so your own `.gitignore` is never edited. The only other file Graphene
  writes is `.claude/settings.local.json`, on `init`.
- Transcripts can contain secrets, so files outside the repo are recorded by path only: their content
  is dropped before it reaches the store.
- Delete `.graphene/` to forget everything; Graphene rebuilds it from the transcripts next time.

## Requirements

macOS or Linux, [uv](https://docs.astral.sh/uv/) to install it, Python 3.12 or later (uv fetches it if
needed), and Claude Code. Run it inside the repo you ran Claude Code in.

## Where this is going

This release is the record: what happened, and why, attributable to the request that caused it. Next
come rules a person sets on a repo, enforced through the same hooks and landing in the same record,
and after that the agent's plan as something you can see and shape. The order and the reasons are in
[docs/ROADMAP.md](docs/ROADMAP.md).

## License

Apache-2.0.
