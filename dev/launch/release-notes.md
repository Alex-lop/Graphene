# Graphene 0.6.0

The first release on PyPI since 0.5.0, which was built on 7 October. 0.5.1 was tagged on 16 October and never
published: its release run failed its tests, so nothing was uploaded. Everything that was in it is in 0.6.0.

Install: `uv tool install graphene-map` (over 0.5.0, `uv tool upgrade graphene-map`). Or try it with nothing
installed: `uvx graphene-map demo`, a recorded run replayed on the new screen (no key, nothing written to your
project).

## What you get that 0.5.0 did not have

- **The watch is a cockpit.** `graphene watch` is one screen for talking to your agents: a row a task, the agent
  on it by number, files written of files allowed, checks passed, how long it has been quiet. What needs you
  comes first, and ⏎ takes it. `g` draws the plan as a graph from your goal down, `m` maps the folders each task
  may write. `graphene watch --classic` keeps the old outline.
- **Talk to an agent while it works.** `t` tells it a line, and a Claude Code session hears it with its next
  write or command. `w` widens a task to the path the gate stopped; `x` hands it back, or reopens a finished one
  with what is wrong.
- **It says when you're needed.** A question, a task that came back, a sign-off or a stopped write rings the
  terminal, with a notification saying why where your terminal shows one. `notify: off` turns it off.
- **Read every diff before it lands, if you want.** `review: every` (in `graphene config edit`) holds each task
  whose check passed for your sign-off: `i` then `c` shows its diff, ⏎ lands it. By default the check decides.
- **Green alone, red together, never lands.** A task whose branch moved while it ran is checked on the merge with
  what landed since, and so is a sign-off; one that fails stays in review.
- **Watch the locks hold.** `graphene demo --cheat` plays a script that tries seven ways round them against the
  real hook, git and check: six refused, one flagged. It is a script, not a model.
- **Know the cost first, and cap it.** A run says its worst case before it starts, `--max-usd N` starts nothing
  past N dollars, and a Claude Code attempt stops at $2.
- **Stop, undo, leave.** `graphene run --stop` from any terminal; `graphene node show` prints the
  `git revert -m 1` that takes a landed task back; `graphene init --remove` takes the hooks out.
- **A demo worth watching.** `graphene demo` replays a plan of two sub-goals and four tasks: three agents at
  once, one that comes back with its reason and is widened and tried again, and one that waits on two.

## What it does not do

- A write outside a task's files is refused before it happens only with Claude Code; with Codex, git finds it
  when the task says it is done.
- Its hook fails open if it cannot run; git catches the change at done.
- A task allowed to edit the test its own check runs can weaken it: it is flagged, not refused.
- Codex has no cap of its own, and `--max-usd` stops starts, not an attempt that is going.
- No person has been timed on it. It's early, and I'm building it in the open: if you try it on a real repo,
  the first-hour form on the issues page takes two minutes, and where the plan misread you is what I most want
  to hear.

Everything, change by change: CHANGELOG.md. How it compares, gaps included: docs/COMPARE.md.
