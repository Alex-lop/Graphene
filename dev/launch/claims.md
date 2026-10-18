# What may be said, and what may not

Each claim names the file that shows it and how strong the showing is: **measured** (a number from a run that
could have gone the other way), **shown** (a test or a command anyone can run), **stand-in** (a scripted or model
reader, not a person), or **not shown**. Written 15 October 2026 for the 0.5.1 launch; re-read before posting.

## May be said

| Claim | Where it is shown | Strength |
|---|---|---|
| Before any code the agent proposes a plan as a tree you can change | `graphene demo`; dev/process/prove/after.md X1: 40 of 40 asks ended in a proposal | measured, one planner (Sonnet), no person timed |
| With Claude Code, a write outside a leaf's files is refused before it happens | tests/test_gate.py; `graphene demo --cheat` (moves 1, 2 and 4) | shown; the demo's agent is a script |
| With Codex or any command, a change outside the files is caught when the leaf is declared done, by git | docs/HOW_IT_WORKS.md "The executors"; `graphene demo --cheat` move 3 | shown |
| Graphene runs the check itself, in a clean copy, not on the agent's word | plan.finish; dev/process/prove/after.md X5 | shown in the suite; one hole closed, one named |
| A leaf that changes the test its own check runs is flagged, not refused | tests/test_check_touched.py; `graphene demo --cheat` move 7 | shown |
| A leaf marked for sign-off waits on its own branch; `i` then `c` in watch shows its diff; `y` merges it | tests/test_signoff_holds.py, tests/test_signoff_seams.py, tests/test_tui.py, tests/test_cockpit_details.py | shown |
| Each leaf lands as one merge, and `git revert -m 1 <id>` takes it back | `graphene node show`; docs/A_RUN.md | shown |
| A run can be stopped by name (`graphene run --stop`) and says its worst case before it starts | tests/test_run_stop.py, tests/test_free_words.py | shown; the worst case is a number, not a cap |
| The record answers more of eight factual morning-after questions than `git log -p` (7 against 5) | dev/process/prove/after.md X3 | stand-in: three runs, one AI reader each |
| On small tasks a plain paragraph to the same agent did as well for less | dev/test/results-2026-09-23.md; after.md X2 | measured, stand-in readers; person-seconds are modelled |
| The suite runs in about 4 to 5 minutes in parallel on an 11-core Mac | `uv run pytest -n auto` | measured locally; not measured on GitHub's runners |

## May not be said

- That a tree beats a paragraph, saves time or tokens, or makes the work better. The repository says the opposite so far.
- "The only tool that...", "nobody else does this", "best controller". A per-task file scope with checks exists for
  another agent (my-pi) and a kernel write lock for nine agents (Ralon): docs/COMPARE.md, dev/PRODUCT_THESIS.md.
- Anything about real people's speed or ease. No person has been timed: dev/process/first-hour.md is how to get one.
- That the demo is a real model run, or that the replay's dollars are real costs.
- That a hook cannot be bypassed. It fails open if it cannot run; git catches the change at done.
- That unattended runs are safe. Codex has no spend cap, and nothing caps a whole run's total.
- That every leaf is approved before it lands. Only a leaf marked for sign-off waits.
- That Nemotron is broadly tested live (docs/HACKATHON.md).
