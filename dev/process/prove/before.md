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

## X1: the first ask (n = 40: feeds 20, report 20)

`x1.sh`, 2026-10-10 16:5xZ, the planner `claude -p --tools Read,Grep,Glob --strict-mcp-config --output-format
stream-json --verbose --model sonnet --max-budget-usd 1.5 --setting-sources project,local`, two tries as shipped, four
asks at a time, each in a fresh `make_task.py` repo as the person.

| measure | feeds (20) | report (20) | all (40), Wilson 95% |
|---|---|---|---|
| proposals by ask | 20 of 20 | 20 of 20 | 40 of 40 [0.91, 1.00] |
| proposals by first answer | 20 of 20 | 20 of 20 | 40 of 40 [0.91, 1.00] |
| asks lost | 0 | 0 | 0 of 40 [0.00, 0.09] |
| first refusals, by class | none | none | none |
| `repaired:` lines; leaves sharing a check | 0; 0 | 0; 0 | 0; 0 |
| checks by runner | unittest 61, pytest 3, other 7 | unittest 18, pytest 21, other 1 | unittest 79, pytest 24, other 8 |
| median seconds; median planner dollars | 38.0; $0.108 | 17.5; $0.050 | 26.5; $0.077 |

**The A1 gate, by the rule written before the run: the schema planner is deferred.** Not one of 40 Sonnet asks was
refused on 907a7d0, so there is no first-refusal class for a schema to reach. The loop night's loss (1 of 4 on the
account's default model, before c4bb66d sent every fault back at once) is not what Sonnet does here on these two
tasks. The record's 37 first refusals and 15 lost asks were Nemotron Ultra's, already on the schema. What A2 and A3
still fix is the dead end when a refusal does happen: the kept proposal, the next step, every fault at once.

## X2 (b) and (c): the plain session and `/batch` on feeds, build-independent (n = 3 and n = 2)

`x2_plain.sh` and `x2_batch.sh`, 2026-10-10 ~17:00Z. Each session: `claude -p --model sonnet --permission-mode
acceptEdits --allowedTools Read Edit Write Glob Grep 'Bash(python3 *)' 'Bash(git *)' 'Bash(ls *)' 'Bash(cat *)'
--output-format json --max-budget-usd 3`, the isolation flags, the feeds paragraph (prefixed `/batch ` for (c), with
`Agent Task EnterWorktree ExitWorktree` allowed and a $5 cap); the harness commits the session's uncommitted change
as one commit, plants `code`→`xcode` in `normalize/fields.py` as the person, and sends the one follow-up sentence
("I broke something after your change: XML records now come out empty. Find it, fix it in the file that owns it, and
say why.") with `--resume`.

| run | accept | held-out | the six untouched | seconds (main; plant) | dollars | denials | turns | the fix changed the owner file | the reply says why |
|---|---|---|---|---|---|---|---|---|---|
| plain 1 | 18 of 20 | 12 of 12 | 6 of 6 | 47; 12 | $0.353 | 2 | 21 | yes | yes |
| plain 2 | 18 of 20 | 12 of 12 | 6 of 6 | 46; 13 | $0.337 | 5 | 17 | yes | yes |
| plain 3 | 18 of 20 | 12 of 12 | 6 of 6 | 52; 12 | $0.383 | 5 | 26 | yes | yes |
| `/batch` 1 | 18 of 20 | 12 of 12 | 6 of 6 | 58; 17 | $0.456 | 6 | 30 | yes | yes |
| `/batch` 2 | 18 of 20 | 12 of 12 | 6 of 6 | 60; 16 | $0.458 | 6 | 30 | yes | yes |

The two misses in `accept` are the same in every run: "`--source` is optional now: xml by extension / csv by
extension", the change of mind the person never sent (as on every prior night). Zero files outside the intent in
every run. "The reply says why" means the follow-up's answer names the cause (every one did: the `sku` key mapped to
`xcode`, so `normalize` returned `None` and every record was dropped); nothing but the session's transcript records
it, and the plain sessions left their fix uncommitted ("that one line is the only edit, and it is not committed").
**`/batch` did not batch:** both runs read the repo, then said "I made the change directly in this checkout rather than
running the batch/worker flow, since it is eight small edits to tightly coupled files"; no subagent, no branch, no
worktree, no PR. On this task the vendor's loop is a plain session with a longer preamble (23 turns, $0.20 against
$0.16 for the plain session's first message).
