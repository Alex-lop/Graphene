# The before numbers, taken on 907a7d0 (`$A`)

Every number here was taken with a script under `dev/process/prove/` on the wheel built from 907a7d0, installed
into its own tool directory, before any change. The same scripts run on the branch in `after.md`. No human is
measured anywhere in this file: every planner, executor, walker and reader is a Sonnet session.

## X4: pytest-bdd issue #476 through the tree (n = 1, a fact)

`x4.sh`, 2026-10-10 16:30Z, repo pinned at 0e04014f, `uv sync` then the venv first on PATH, the planner Sonnet
through `--with`, the executor 907a7d0's DEFAULT_WITH plus `--model sonnet --max-budget-usd 2 --strict-mcp-config
--setting-sources project,local`, `run --parallel 2`.

| measure | 907a7d0 |
|---|---|
| ask: proposal by first answer | yes (23 s, $0.0718, 5 calls) |
| the tree | 1 sub-goal, 2 leaves (`tags-output` needs → `tags-tests`), 2 board items (a question with two options and `then:` lines; a risk with a `then: check` line) |
| checks written | 3 × `python3 -m pytest …`; 0 × `uv run` |
| red first | `tags-output: its check passes at the base commit 0e04014: it proves nothing` (its check is the existing reporter test file); `tags-tests` red (its test file does not exist yet) |
| editable install reaches everywhere | yes: with the venv first on PATH, `python3 -c 'import pytest_bdd'` from `/tmp` imports `repo/src/pytest_bdd/__init__.py`; and pytest-bdd is a pytest plugin loaded from the installed distribution, so a check in a clean worktree runs the checkout's plugin code |
| run | both leaves landed on their first attempt, 53 s, $0.1936 (13 calls); `width 1 of 2`; no hand-back |
| the repo's own suite afterwards | 148 passed in 8.86 s (146 before: the two new tests) |
| the issue's ask, as a judgement | the tags line is printed in both `-v` and `-vv` branches when a scenario has tags, with a README note and a CHANGES entry; not reviewed against #807's reference diff |
| total | 87 s wall, $0.2654 at list price |

What a stranger would meet here on 907a7d0: the run printed the red-first warning and started the leaf anyway (a
warning, by decision); nothing said that the venv's python would test the checkout rather than the leaf's tree;
the bill line read `you 0 acts, 0 min` after the person had accepted the tree; `plan record` gave coverage and the
bill but no landed shas, and `git log` carries two merges with empty bodies.
