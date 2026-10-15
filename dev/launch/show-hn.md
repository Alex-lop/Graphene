# Show HN

**Title** (68 characters): Show HN: Graphene – keep Claude Code inside the files you agreed to

**First comment** (about 190 words, Alex's voice):

Hi HN, I'm Alex. I kept finding out what my coding agent had decided only in the diff, after the time and money
were spent: files I never asked it to touch, and "all tests pass" when they didn't.

Graphene sits between you and Claude Code or Codex, on your machine, no account. Before any code you see the
agent's plan as small pieces, each naming the files it may change and a check. With Claude Code a hook refuses a
write to any other file before it happens; git checks again when a piece is declared done. Graphene runs the check
itself, in a clean copy, and lands the piece as its own merge only when it passes.

`uvx --from graphene-map graphene demo` plays a scripted replay, no key. `graphene demo --cheat` runs a script that
tries seven ways round the locks against the real hook, git and check: six refused, one flagged. That is a script,
not a model: it shows the locks, not what a real agent will try.

Honestly, in the three comparisons so far a plain paragraph to the same agent did just as well for less, and no
person has been timed yet. What I most want to hear is where the plan misread you. The page that compares it with
Claude Code's own plan mode, Cursor, Kiro and the rest, gaps included, is docs/COMPARE.md.

**Before posting:** 0.5.1 is on PyPI and `uvx --isolated --from graphene-map graphene init --help` shows `--remove`;
the first-hour form is live; do not claim "the only".
