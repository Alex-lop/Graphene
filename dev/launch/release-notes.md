# Graphene 0.5.1

Everything since 0.5.0, which was built on 7 October. If you installed 0.5.0 from PyPI you have none of what
follows. Install or upgrade: `uv tool install --force graphene-map`. Or try it with nothing installed:
`uvx --from graphene-map graphene demo` (a scripted replay: no key, nothing written to your project).

## What you can do now

- **See a leaf's whole diff** before you sign it off: `c` in `graphene watch`.
- **Mark a leaf for sign-off** and it waits on its own branch until you press `y`, which merges it.
- **Watch the locks hold**: `graphene demo --cheat` runs a script that tries seven ways round them against the real
  hook, git and check. It is a script, not a model.
- **Stop a run by name**: `graphene run --stop`. A run now says its worst case before it starts.
- **Take a landed leaf back**: `graphene node show <leaf>` prints the `landed:` id; `git revert -m 1 <id>`.
- **Get out cleanly**: `graphene init --remove`; **read a change**: `graphene node diff <leaf>`.
- **Say what you saw**: a first-hour form on the issues page takes two minutes.

## What changed under it

- A leaf that changes a file its own check runs is flagged, in the run and in the record. Not refused.
- A run says the plan's worst case first, and `graphene` with nothing planned starts with `graphene init`.
- The suite runs in parallel in CI, and a tag push gets a run.
- A write outside a leaf's files is refused before it happens with Claude Code; with Codex git finds it at done.

## What it does not do

- It does not cap a whole run's cost (an attempt stops at $2 with Claude Code; Codex has no cap).
- Its hook fails open if it cannot run; git catches the change at done.
- A leaf allowed to edit the test its own check runs can weaken it; it is flagged so you can read the diff.
- No person has been timed. It is early.

Full list: CHANGELOG.md. How it compares, with its gaps: docs/COMPARE.md.
