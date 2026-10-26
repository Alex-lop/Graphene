# What may be said, and what may not

Each claim names the file that shows it and how strong the showing is: **measured** (a number from a run that
could have gone the other way), **shown** (a test or a command anyone can run), **stand-in** (a scripted or model
reader, not a person), or **not shown**. Written 15 October 2026 for the 0.5.1 launch, with the hackathon's
Nemotron claims added on 18 October; re-read before posting.

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
| On the Nemotron path, Ultra plans, Nano does the tasks and Super takes a retry, through Token Factory | `graphene init --planner nemotron --executor nemotron`; tests/nemotron/ | shown against a scripted Token Factory; live in practice and takes |
| On the build of 9 October, Nemotron 3 Ultra's answer became a plan in 35 of 40 asks | dev/process/loop/after.md, the Nemotron planner | measured live: two small tasks, one night |
| Of 31 live demo takes on two small repositories, 7 to 9 October, 4 ran clean and 2 landed every task | dev/process/meter, timeline and loop, takes.md | measured live: two small repositories |
| Each Nemotron call is priced from Token Factory's usage at list price, so each task has a bill | tests/nemotron/test_tokenfactory.py; `i` on a task in `graphene demo tests/recordings/loop-nemotron-take-2.jsonl` | shown; whether the list price is what is billed is not observed |
| A task can run as several agents at once, and the check decides which is kept, by a rule written before any fork ran; the person can pick another | src/graphene_map/pick.py (the rule, dated in its docstring); tests/test_pick.py; tests/test_forks_run.py (`node pick`) | shown, with scripted agents; no live forked run |
| With `auto: on`, a proposal that fits the envelope (every task with a scope and a check, the board settled, within `tasks`) is accepted at once as the person's stand-in, and `graphene plan undo` takes it back; `graphene auto` plans, runs, checks the goal and plans the fix for `rounds` rounds, and stops with a reason at the envelope's edge | tests/test_auto_envelope.py, tests/test_auto_run.py, tests/test_auto_nemotron.py | shown; the planner and executors are scripts, or the scripted Token Factory; no live auto run |
| The envelope never takes a task whose scope reaches `.claude/`, `.codex/`, `.cursor/`, `.gemini/` or `.github/workflows/`, nor one whose check is not one plain command (or not among `checks:`), and while auto is on every run counts against its budget, an agent's own `graphene run` included; no scope reaches `.git/` | tests/test_auto_envelope.py, tests/test_auto_checks.py, tests/test_git_dir_is_nobodys.py | shown, with scripted agents |
| Auto mode on the Nemotron path ran end to end against the scripted Token Factory: three tasks, nine forks at once, the goal's check red, Ultra's fix, the suite green, $0.0193 at the stand-in's prices | tests/test_demo_auto.py; `graphene demo --auto` | shown; a scripted stand-in, no model ran; no live auto run |
| Every agent's row names its model, and each fork its own, with its dollars | tests/test_race_read.py, tests/test_race_rows.py | shown, with scripted agents and the recordings |
| Graphene for VS Code shows the plan as a graph and runs a `graphene` command for every change; it activated and registered its commands in VS Code 1.143 | editors/vscode/test/*.test.ts, editors/vscode/test/smoke.cjs; tests/test_vscode_cli.py | shown; not on the Marketplace, not tried in Cursor |
| The same Nemotron loop runs on NVIDIA NIM, Ollama or any OpenAI-compatible host, writes refused the same way; an agent's call to a paid host off this machine is refused without the opening | tests/test_anymodel_endpoints.py | shown against the scripted host; no live call to NIM, Ollama or another host |
| Every agent a run starts gets a `PORT` of its own, per task and per fork, given to its check too | tests/test_anymodel_ports.py | shown, with scripted agents |

## May not be said

- That a tree beats a paragraph, saves time or tokens, or makes the work better. The repository says the opposite so far.
- That forks make the work better, that the kept fork is the best, or that forks save tokens, dollars or time. The
  check decides, by a rule written before any fork ran; nothing has measured what it keeps against one agent's work.
- "The only tool that...", "nobody else does this", "best controller". A per-task file scope with checks exists for
  another agent (my-pi) and a kernel write lock for nine agents (Ralon): docs/COMPARE.md, dev/PRODUCT_THESIS.md.
- Anything about real people's speed or ease. No person has been timed: dev/process/first-hour.md is how to get one.
- That the demo is a real model run, or that the replay's dollars are real costs.
- That a hook cannot be bypassed. It fails open if it cannot run on a Claude Code before 2.1.295, or where `graphene
  init` ran from a script (from 2.1.295, `init` at a terminal makes it fail closed); git catches the change at done
  either way.
- That unattended runs are safe. Codex has no spend cap of its own, and a whole run's total is capped only by
  `graphene run --max-usd`, which starts no attempt past it and stops none that is going. `graphene auto`'s
  `budget` holds Claude Code and Codex attempts the same way, reads Nemotron's bills only between rounds, and
  cannot hold an executor that reports no cost (it counts attempts instead, and says so first).
- That every leaf is approved before it lands. Only a leaf marked for sign-off waits.
- That Nemotron is broadly tested live (docs/HACKATHON.md).
- That a Nemotron agent hears `t` mid-task. It is told the next time its task starts; Claude Code hears it with its
  next write.
- That a live run always ends in a plan. On 9 October 5 of 40 asks did not, and on 7 October 12 of 19 takes.
