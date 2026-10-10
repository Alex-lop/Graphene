# The morning after the prove-it night (10 October 2026)

Read this first, then `after.md` (every before/after pair with its file and its n), then the PR. Everything ran in a
clone under the session's scratchpad on branch `night/prove-it`; your checkout, the tag `statements-prereg-2`,
PREREG and PROVE were not opened. Nothing is published, tagged or re-described.

## Read first: the decisions, each one line to flip

The plan named these as yours to veto before anything ran. The PR opens with them.

1. **Plan first for new repos.** `init` now asks the mode at a terminal, one line per mode, and keeps `on` when it
   cannot ask (decision 176 holds; X7 re-takes the auto-against-on count on the branch). Veto: silent `on`, or `auto`.
2. **The shipped executor** gains `--strict-mcp-config` and `--max-budget-usd 2` ("an attempt": the probe X0(b)
   showed the cap counts the invocation, not the resumed session). `--setting-sources project,local` stays out of the
   defaults: it would drop a stranger's user-level auth and model settings; it also drops your plugins and hooks from
   the executor, which `--strict-mcp-config` alone does not (X0(c)). Veto: the flag, the number, or both.
3. **The schema planner (A1) was not built.** X1 measured 40 of 40 Sonnet asks accepted on the first answer on
   907a7d0, so by the rule written before the run there was nothing for it to fix; the histogram is in `before.md`.
   What shipped instead ends the dead end when a refusal does happen: the ask's cost line, the kept proposal with
   its next step, every fault at once from `plan propose -`.
4. **Keys.** `?` is help on every row, `t` talks to the planner, a run that could start more than one leaf asks first
   (`R`, and `r` on the goal or a sub-goal). Veto: any of the three.
5. **The Stop hook** blocks an interactive session once; `graphene run`'s executors keep the repeated block.
6. **The bill line's `you`** counts your acts since the plan's last run, or since it began. README:38 is left as you
   wrote it.
7. **HOW_IT_WORKS' cap** 3,000 → 3,300 words, in its own commit (words no claim pinned were cut first). Veto: drop
   that commit and the docs commit after it, or ask for a second page.
8. **The demo** stays the scripted stand-in and the README calls it a scripted replay; the replay ends with the next
   command. Veto: swap in a clean recording from the night (re-pins two test files by hand).
9. **The README lines** under "Try it on your repo" are a draft in your voice; rewrite them.
10. **The clean tree reads content, not the copied index's stat data** (one line in `plan._clean_tree`). This is a
    correctness fix found by the harness, not in the plan: a leaf's check could pass on the committed file when the
    executor's edit kept the size and landed in the same second as the checkout (X5 on 907a7d0, under `uv run`). It
    is its own commit; `probes/racy.md` reproduces it outside Graphene.

## The numbers

`after.md` holds every pair. The one-line version is written there once the after arms have run on the frozen SHA.

## Your own timed first hour, at $0 to the night's ledger

No human was measured tonight: every planner, executor, walker and reader was a Sonnet session. This is the hour
only you can take. Pick a repository of yours that none of tonight's fixtures touched (not `feeds`, `report`,
`statements`, not pytest-bdd), small enough that `uv run pytest -q` is green in a minute, with one change you
actually want. Start a stopwatch and write the minute at each step, and every point where you did not know the next
key or command:

```
mkdir -p ~/graphene-morning && cd ~/graphene-morning
env UV_TOOL_DIR=$PWD/tools UV_TOOL_BIN_DIR=$PWD/bin uv tool install 'git+https://github.com/Alex-lop/Graphene@night/prove-it'
export PATH=$PWD/bin:$PATH && graphene --version          # the branch, in its own directory: your checkout's hooks still run af3da2c5
cd <your repo> && graphene init                            # it asks the plan-first mode; read what it says about the hooks and the record
graphene ask "<the change you want, in a paragraph>"      # the last line is the planner, its calls and its dollars
graphene watch                                            # y on the goal, R: it asks before it starts; ? is help; Esc closes it
graphene node show <a landed leaf> && graphene node diff <it>   # the check's last line, the at-base verdict, the landed sha, the diff
git log --format='%s%n%b' -3                              # the merge's body: the check, the executor, the attempts, the dollars
graphene init --remove                                    # the hooks come out; the plan is yours to keep or delete
```

Write the minutes and the stalls into `dev/process/prove/your-hour.md` and commit it on the branch. That file is
the one first-hour number with a person in it; the walks (`before.md`, `after.md`) are the scripted person's.

## Noticed, not changed

Design questions the night wrote up and left, with where they bite:

- The command guard refuses read-only commands that merely name the store directory (`gate.py:536-552`): the
  stranger in X6 hit it with a `ls`. It decides what an agent may read in a store that holds recorded prompts and
  file contents; your call.
- A subagent of a Claude Code session carries the session's id (`gate.py:357-358`): a `/batch` or agent-team worker
  is judged against whatever leaf the main session holds. X2(c) found `/batch` declines to batch on feeds, so it was
  not exercised.
- A session's writes in another worktree block `done` with "put it back" (`plan.py:2137-2149`).
- Plan mode is mentioned nowhere.
- There is no way to stop the recording short of `graphene init --remove`; `init` now says what is recorded.
- A run lands into the branch you have checked out; every competitor puts a diff or a PR in front of the person
  first. The `node diff` command is the night's smallest step toward that.
- The `b` sibling Graphene offers has the check `true`, the very kind red first calls "proves nothing".
- `permissions.allow` for `Bash(graphene plan *)` and `Bash(graphene node *)` at init would spare the person a
  permission prompt per in-session proposal; it is your settings file.
- `graphene node show` on a sub-goal prints an empty `scope:` and `done:` line (the walks' transcripts).
- The planner writes `python3 -m pytest` as a check on a repo whose pytest lives in a venv (X1: 24 of 111 checks;
  X4 and X6: every check): with the person's PATH that check cannot run. The branch names it before the run (C3)
  and tells the planner about the clean tree (A5); only you can decide whether Graphene should run checks through
  the repo's own runner.

## What the night did to this machine, and undid

- The stranger transcripts (X6) ran `uv tool install <wheel>` with no tool directory of their own, so each replaced
  the `graphene` on your default PATH (`~/.local/bin/graphene`, the uv tool `graphene-map`): first with 907a7d0's
  wheel, then with the branch's. The plan's rule was never to touch it; the harness let the stranger's shell do what
  the person's would. It was put back at 19:2xZ from `git+https://github.com/Alex-lop/Graphene@af3da2c5`, the commit
  it had held (the receipt's source string now names that commit rather than whatever yours named). Check with
  `uv tool list` and `cat ~/.local/share/uv/tools/graphene-map/uv-receipt.toml`. Your checkout's hooks ran the
  replaced builds for about two and a half hours; nothing in their path changed the store's schema.
- Everything else lived under the session's scratchpad: the clone, the worktrees, the two tool directories, every
  fixture and run.

## Yours: publishing and the stale words

- The tag and PyPI are yours: `0.5.0` is in CHANGELOG as "not published yet". PyPI still has 0.2.0 with the map-era
  description.
- The GitHub repository description is the taskmaster-era sentence.
- `docs/HACKATHON.md` still says react/vite and quotes 2 October numbers.
- Your checkout holds `tests/test_probe_seam.py` (the loop night's stray) untracked, and the `graphene` on your PATH
  is a uv tool built from af3da2c5; your checkout's hooks run that build. After merging, `uv tool install --force
  git+https://github.com/Alex-lop/Graphene` brings it to main.

## Rollback

Every decision above is one commit or one line; `git log --oneline main..night/prove-it` names them, one commit per
change with its test. The backup branch `night/prove-it-before-fold` keeps the unfolded history so every SHA the
evidence names still resolves.
