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

## X5: the editable-install hole, no model (three combinations, each a fact)

`x5.sh`, 2026-10-10 16:45Z. A src-layout fixture (`pyproject`, `src/pkg`, `tests/`) installed editable by `uv sync`;
leaf `a` owns `src/pkg/__init__.py` with the check `python3 -m pytest -q tests` (it names `tests/`, outside its
scope); leaf `b` owns `src/pkg/b.py` and `tests/test_b.py` with the check `python3 -m pytest -q tests/test_b.py`. A
fake executor breaks the leaf's function in its worktree and calls `done`.

| combination | red first said | `pkg` imported from, in the worktree | `b` (broken) landed | attempts |
|---|---|---|---|---|
| `python3 -m pytest`, no pytest on PATH | `a: its check names tests, outside its scope`; `b`: red, `No module named pytest` (the gist is kept in the log row only) | nothing: no pytest | no: `b came back after 3 attempts`, each refused with the same `No module named pytest` | 3 |
| `python3 -m pytest`, the fixture's `.venv/bin` first on PATH | `a` and `b`: `its check passes at the base commit: it proves nothing` | the checkout, for both leaves | **yes** | 1 |
| `uv run pytest`, the same PATH | the same two lines | its worktree, for both leaves | **yes** | 1 |

Two holes, then, on 907a7d0, and the run said nothing about either:

1. **The editable install.** With the venv first on PATH, `python3 -m pytest` in the clean worktree imports `pkg`
   from the checkout, so the check never saw the leaf's broken function and `b` landed.
2. **The copied index.** Under `uv run pytest` the worktree's own `pkg` was imported, and `b` landed anyway. The
   clean tree is built from a copy of the worktree's index, dated when it is copied; git then trusts every entry's
   stat data, and an edit of the same size made in the second the file was written out reads as the committed
   file. Reproduced outside Graphene in `dev/process/prove/probes/racy.md`: commit, edit the file in the same second
   keeping its size, copy the index with a later date, `git add -A` on the copy writes the committed content; dating
   the copy at epoch+1 makes every entry racily clean and the content is read (a zero date disables git's racy
   check; `git update-index --really-refresh` does not help). The executor's own `done` in the same second as the
   edit failed correctly; the run's own `done` a second later passed, and the leaf landed broken.
