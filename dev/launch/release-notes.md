# Graphene 0.7.0

Install: `uv tool install graphene-map` (over 0.6.0, `uv tool upgrade graphene-map`). Or try it with nothing
installed: `uvx graphene-map demo`, a scripted replay of a run, a fork race in it (no key, nothing written to your
project).

## What you get that 0.6.0 did not have

- **Fork a task.** `graphene run --forks 3` puts three agents on each task at once, each in its own copy of your
  repository and held to the task's files like any agent. `graphene run --with claude:opus --with claude:sonnet
  --with codex` gives each fork its own agent, `--first` keeps the first fork that passes and stops the rest,
  `forks: 3` on a task in the plan forks only that one, and `forks:` in `graphene config edit` forks every task.
- **The check keeps one, by a rule written before any fork ran.** Among the forks whose check passed: the one
  that passes the most of the other forks' tests, then the one that left the check's own files alone, then the
  smallest change, the cheapest, the first to finish. The run says why in one line (`stats kept a of 3: 10 lines
  against 12`), lands that fork alone as one merge, and keeps every fork's work on a ref: `graphene node diff
  <task> --fork b` shows it, `graphene node show <task>` lists them, and on a task waiting for your sign-off
  `graphene node pick <task> c` lands another. Three Haiku forks of one task cost $0.02 in a live run.
- **Forks in `graphene watch`.** `f` forks the task you're on; a forked task opens to a line a fork (`3a`, `3b`,
  `3c`), each with its own moves; a note you tell it reaches every fork; a digit picks another fork of a task in
  review; the details' record has a table of the forks.
- **The graph flows into your goal.** `g` draws the goal as the last box, every arrow meaning "lands before":
  each column a wave of tasks that can run at once, each band a part of the goal with its count, the double line
  the longest chain the goal waits on.
- **The gate fails closed.** On Claude Code 2.1.295 or later, `graphene init` in your terminal makes a hook that
  cannot run refuse the call instead of letting it through; and a call the hook cannot judge is refused.
- **The gate reads more of the shell.** A write after a `#` comment, a quoted `<<EOF`, `$((1<<n))` or a
  here-string; after `cd -P`, `cd -`, `cd $PWD/…` or inside a subshell; to `>&`, `<>`, `&>>`, `|&`, `dd of=`,
  `install` or a variable the command set; under `nice -n 1`, `env -i` or `command -p`: each is refused before
  it happens now, where git found it at done. A log written to /tmp beside a write outside the task no longer
  lets that write through.
- **A cap that is too small says so.** `graphene run --max-usd` under one attempt's worst case says how much
  starts one.

## What it does not do

- A write outside a task's files is refused before it happens by Claude Code's hooks and by Nemotron's edit and
  write; with Codex, or a write the hook cannot read (a target in a variable it was not given, a glob, a command
  substitution, a script that opens a file itself), git finds it when the task says it is done.
- The rule keeps one fork by the check and a few counts; it does not read the code. A fork it keeps is not shown
  to be the best one, and `graphene node pick` is yours when you disagree.
- Whether forks land more tasks is not measured yet. `dev/held/rules.md` says how it will be.
- A task allowed to edit the test its own check runs can weaken it: it is flagged, not refused.
- Codex has no cap of its own, and `--max-usd` stops starts, not an attempt that is going.
