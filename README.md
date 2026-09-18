# Graphene

![CI](https://github.com/Alex-lop/Graphene/actions/workflows/ci.yml/badge.svg?branch=main)

Why did my coding agent change this line? Graphene answers that from Claude Code's own records,
across sessions, and prints a short card of what happened when you come back to a repo.

I run Claude Code on a repo, come back hours later or the next morning, and can't account for the
changes. The diff doesn't tell me which request produced which change, what the agent touched that I
never asked for, or what it tried and then abandoned. Graphene does.

![The card: what one session changed](docs/assets/card.svg)

## Install

```
uv tool install graphene-debrief
```

That line works once the package is on PyPI. Until then, install from GitHub:

```
uv tool install git+https://github.com/Alex-lop/Graphene
```

## Use

Run Claude Code on the repo as you normally do. When you come back, inside the repo:

```
graphene
```

Graphene reads the transcripts Claude Code keeps for the repo (the first time takes a couple of
seconds; after that only what changed) and prints the card for the latest session, or for everything
since you last looked.

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

When you want more: `graphene debrief --full` is the whole reconstruction, prompt by prompt;
`--json` is the structure behind it; `--md FILE` writes either to a file; `--html FILE` writes a
self-contained page (a timeline of prompts and files, opens offline, safe to send to a teammate).
`graphene init` installs hooks so sessions are recorded live (exact prompt boundaries and the commit
each session started from); without it Graphene keeps reading the transcripts.

## How it works

Graphene reads Claude Code's transcript files for the repo, or the events its hook recorded live,
and groups every tool call under the prompt whose turn it ran in. Claude Code's own payloads carry
the file before and after each edit, so the diff per prompt and file is computed directly, and only
the edges of a file's history fall back to git. A file is flagged as not asked for only when the
prompt named a file scope that does not cover it; a prompt that names no file flags nothing.
"Abandoned" means files restored to their session-start content and checks that failed and were
rerun. No model is involved unless you ask for explanation sentences with `--explain claude`. The
heuristics and their failure modes are spelled out in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## What it doesn't do

- It does not run agents.
- It does not orchestrate anything.
- It does not push, commit, or touch your git history.
- It does not phone home: nothing leaves your machine unless you opt into `--explain claude`, and then only through your own Claude Code.

## Privacy

- The store is `.graphene/` inside the repo: local, created `0700`, git-ignored automatically.
- Transcripts can contain secrets, so files outside the repo are recorded by path only, never by content.
- Delete `.graphene/` to forget everything; Graphene rebuilds it from the transcripts next time.

## Requirements

macOS or Linux, Python 3.12 or later (uv fetches it if needed), and Claude Code.

## Where this is going

This release is the record: what happened, and why, attributable to the request that caused it. Next
come rules a person sets on a repo, enforced through the same hooks and landing in the same record,
and after that the agent's plan as something you can see and shape. The order and the reasons are in
[docs/ROADMAP.md](docs/ROADMAP.md).

## License

Apache-2.0.
