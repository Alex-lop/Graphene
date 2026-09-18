# Changelog

## 0.1.0 (unreleased)

First release. Graphene reads the transcripts Claude Code keeps on your machine and answers
which prompt changed a file or a line.

- `graphene` prints a short card of the latest session: files changed, commits, what was changed
  outside the scope you named, what was tried and abandoned.
- `graphene why PATH` and `graphene why PATH:LINE` list the prompts that changed a file or wrote a line.
- `graphene debrief --full` is the whole reconstruction; `--json` the structure; `--md FILE` writes it.
- `graphene init` installs hooks so sessions are recorded live; without it Graphene reads transcripts.
- Explanations are factual templates by default; `--explain claude` asks Claude Code once per prompt.
