# Changelog

## 0.1.0 (unreleased)

First release: Graphene reads the transcripts Claude Code keeps on your machine and answers which prompt changed a file or a line.
- `graphene`: a short card of the latest session (files changed, commits, changes outside the scope you named, what was tried and abandoned).
- `graphene why PATH` and `graphene why PATH:LINE`: the prompts that changed a file, or the one that wrote a line.
- `graphene debrief --full`, `--json`, `--md FILE` and `--html FILE` (a self-contained page that opens offline).
- `graphene init` installs hooks so sessions are recorded live; without it Graphene reads the transcripts.
- Explanations are factual templates by default; `--explain claude` asks Claude Code once per prompt (`--model NAME`, default `haiku`).
